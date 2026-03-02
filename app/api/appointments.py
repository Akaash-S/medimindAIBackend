from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db, firestore
from app.core.security import get_current_user, get_current_patient
import uuid, hashlib, time

router = APIRouter()


@router.get("/doctor/{doctor_id}/slots")
async def get_doctor_slots(doctor_id: str, current_user: dict = Depends(get_current_patient)):
    """
    Patient-accessible endpoint: returns free consultation slots for the patient's
    assigned doctor.

    Slot sources (merged, de-duped, sorted by date+time):
    1. Manual one-off slots from users/{doctor_id}/availability (status=="free")
    2. Auto-generated slots from the doctor's weekly working_hours for the next 14 days,
       with 30-minute intervals — excluding dates that already have appointments.
    """
    from datetime import date, timedelta, datetime

    # Security: patient must be assigned to this doctor
    if current_user.get("assigned_doctor") != doctor_id:
        raise HTTPException(status_code=403, detail="You are not assigned to this doctor")

    # ── 1. Manual one-off slots ──────────────────────────────────────────────
    manual_slots = []
    slots_ref = (
        db.collection("users")
        .document(doctor_id)
        .collection("availability")
        .stream()
    )
    for doc in slots_ref:
        slot = doc.to_dict()
        if slot.get("status", "free") == "free":
            slot["id"] = doc.id
            slot["source"] = "manual"
            manual_slots.append(slot)

    # ── 2. Auto-generate from weekly working hours ───────────────────────────
    doctor_doc = db.collection("users").document(doctor_id).get()
    working_hours: list = []
    consultation_duration = 30  # minutes
    if doctor_doc.exists:
        data = doctor_doc.to_dict()
        working_hours = data.get("working_hours", [])
        # Support custom duration stored as string or int
        try:
            consultation_duration = int(data.get("consultation_duration", 30))
        except (ValueError, TypeError):
            consultation_duration = 30

    # Build a map: day_name → {start, end} for active days
    day_schedule: dict = {}
    for wh in working_hours:
        if wh.get("active") and wh.get("day") and wh.get("start") and wh.get("end"):
            day_schedule[wh["day"].lower()] = {
                "start": wh["start"],  # "HH:MM"
                "end": wh["end"],
            }

    # Get existing UPCOMING appointments for this doctor (to block those times)
    existing_times: set = set()
    try:
        appt_docs = (
            db.collection("appointments")
            .where("doctor_id", "==", doctor_id)
            .where("status", "==", "upcoming")
            .stream()
        )
        for appt in appt_docs:
            ad = appt.to_dict()
            if ad.get("date") and ad.get("time"):
                existing_times.add(f"{ad['date']}_{ad['time']}")
    except Exception:
        pass  # Non-blocking

    # Day-name mapping (Python weekday: 0=Mon, 6=Sun)
    WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    generated_slots = []
    today = date.today()
    for delta in range(0, 14):
        day = today + timedelta(days=delta)
        day_name = WEEKDAY_NAMES[day.weekday()]
        if day_name not in day_schedule:
            continue

        sched = day_schedule[day_name]
        try:
            start_dt = datetime.strptime(f"{day.isoformat()} {sched['start']}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{day.isoformat()} {sched['end']}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        current_dt = start_dt
        while current_dt + timedelta(minutes=consultation_duration) <= end_dt:
            slot_start = current_dt.strftime("%H:%M")
            slot_end = (current_dt + timedelta(minutes=consultation_duration)).strftime("%H:%M")
            time_key = f"{day.isoformat()}_{slot_start} - {slot_end}"

            if time_key not in existing_times:
                generated_slots.append({
                    "id": f"gen_{day.isoformat()}_{slot_start}",
                    "date": day.isoformat(),
                    "start_time": slot_start,
                    "end_time": slot_end,
                    "status": "free",
                    "source": "schedule",
                })
            current_dt += timedelta(minutes=consultation_duration)

    # ── 3. Merge, de-dupe by (date, start_time), sort ───────────────────────
    seen = set()
    all_slots = []
    for slot in manual_slots + generated_slots:
        key = (slot.get("date", ""), slot.get("start_time", ""))
        if key not in seen:
            seen.add(key)
            all_slots.append(slot)

    all_slots.sort(key=lambda x: (x.get("date", ""), x.get("start_time", "")))
    return all_slots



@router.post("/book")
async def book_appointment(booking_data: dict, current_user: dict = Depends(get_current_patient)):
    """
    Patient-friendly appointment booking shorthand.
    Requires: doctor_id, date, time, reason. Optional: slot_id, report_id.
    """
    uid = current_user["uid"]
    doctor_id = booking_data.get("doctor_id", "")
    slot_id = booking_data.get("slot_id")

    if not doctor_id:
        raise HTTPException(status_code=400, detail="doctor_id is required")

    # Verify patient is assigned to this doctor
    if current_user.get("assigned_doctor") != doctor_id:
        raise HTTPException(status_code=403, detail="You are not assigned to this doctor")

    # Look up doctor name
    doctor_doc = db.collection("users").document(doctor_id).get()
    if not doctor_doc.exists:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doctor_data = doctor_doc.to_dict()

    appt_id = str(uuid.uuid4())
    consultation_id = str(uuid.uuid4())
    room_hash = hashlib.sha256(f"{consultation_id}{int(time.time())}".encode()).hexdigest()[:12]
    room_name = f"medimind-{room_hash}"
    room_url = f"https://meet.jit.si/{room_name}"

    appt = {
        "id": appt_id,
        "patient_id": uid,
        "patient_name": current_user.get("full_name", "Patient"),
        "doctor_id": doctor_id,
        "doctor_name": doctor_data.get("full_name", "Doctor"),
        "specialization": doctor_data.get("specialization", ""),
        "date": booking_data.get("date", ""),
        "time": booking_data.get("time", ""),
        "type": "video",
        "reason": booking_data.get("reason", "General consultation"),
        "status": "upcoming",
        "notes": "",
        "report_id": booking_data.get("report_id", ""),
        "consultation_id": consultation_id,
        "room_name": room_name,
        "room_url": room_url,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    db.collection("appointments").document(appt_id).set(appt)

    # Store consultation record
    db.collection("consultations").document(consultation_id).set({
        "id": consultation_id,
        "appointment_id": appt_id,
        "patient_id": uid,
        "doctor_id": doctor_id,
        "report_id": booking_data.get("report_id", ""),
        "recommendation_id": booking_data.get("recommendation_id", ""),
        "room_name": room_name,
        "room_url": room_url,
        "status": "scheduled",
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    # Mark the availability slot as booked if slot_id provided
    if slot_id:
        try:
            slot_ref = (
                db.collection("users")
                .document(doctor_id)
                .collection("availability")
                .document(slot_id)
            )
            if slot_ref.get().exists:
                slot_ref.update({"status": "booked"})
        except Exception as e:
            print(f"Failed to mark slot as booked: {e}")

    return {
        "message": "Appointment booked successfully",
        "appointment_id": appt_id,
        "consultation_id": consultation_id,
        "room_url": room_url,
        "date": appt["date"],
        "time": appt["time"],
        "doctor_name": doctor_data.get("full_name", "Doctor"),
    }


@router.get("/")
async def get_appointments(current_user: dict = Depends(get_current_user)):
    """Get all appointments for the current user (as patient or doctor)."""
    uid = current_user["uid"]
    role = current_user.get("role", "patient")

    # Query by patient_id or doctor_id depending on role
    field = "patient_id" if role == "patient" else "doctor_id"
    docs = db.collection("appointments").where(field, "==", uid).stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        # Convert timestamps
        for ts_field in ["created_at", "updated_at"]:
            ts = data.get(ts_field)
            if ts and hasattr(ts, "isoformat"):
                data[ts_field] = ts.isoformat()
        results.append(data)

    # Sort by date descending
    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results

@router.post("/")
async def create_appointment(appointment_data: dict, current_user: dict = Depends(get_current_user)):
    """Create a new appointment. Works for both patients and doctors."""
    uid = current_user["uid"]
    role = current_user.get("role", "patient")
    appt_id = str(uuid.uuid4())

    if role == "doctor":
        # Doctor creating appointment for a patient
        patient_id = appointment_data.get("patient_id", "")
        if not patient_id:
            raise HTTPException(status_code=400, detail="patient_id is required")
        
        # Look up patient name
        patient_doc = db.collection("users").document(patient_id).get()
        if not patient_doc.exists:
            raise HTTPException(status_code=404, detail="Patient not found")
        patient_data = patient_doc.to_dict()
        
        # Verify patient is assigned to this doctor
        if patient_data.get("assigned_doctor") != uid:
            raise HTTPException(status_code=403, detail="Patient not assigned to you")
        
        appt = {
            "id": appt_id,
            "patient_id": patient_id,
            "patient_name": patient_data.get("full_name", "Patient"),
            "doctor_id": uid,
            "doctor_name": current_user.get("full_name") or current_user.get("name", "Doctor"),
            "specialization": current_user.get("specialization", ""),
            "date": appointment_data.get("date", ""),
            "time": appointment_data.get("time", ""),
            "type": appointment_data.get("type", "video"),
            "reason": appointment_data.get("reason", ""),
            "status": "upcoming",
            "notes": appointment_data.get("notes", ""),
            "created_at": firestore.SERVER_TIMESTAMP,
        }

        # Generate consultation record for video appointments
        if appt["type"] == "video":
            consultation_id = str(uuid.uuid4())
            room_hash = hashlib.sha256(f"{consultation_id}{int(time.time())}".encode()).hexdigest()[:12]
            room_name = f"medimind-{room_hash}"
            room_url = f"https://meet.jit.si/{room_name}"

            appt.update({
                "consultation_id": consultation_id,
                "room_name": room_name,
                "room_url": room_url,
            })

            # Store consultation
            db.collection("consultations").document(consultation_id).set({
                "id": consultation_id,
                "appointment_id": appt_id,
                "patient_id": patient_id,
                "doctor_id": uid,
                "report_id": appointment_data.get("report_id", ""),
                "room_name": room_name,
                "room_url": room_url,
                "status": "scheduled",
                "created_at": firestore.SERVER_TIMESTAMP,
            })
    else:
        # Patient creating appointment
        appt = {
            "id": appt_id,
            "patient_id": uid,
            "patient_name": current_user.get("full_name") or current_user.get("name", "Patient"),
            "doctor_id": appointment_data.get("doctor_id", ""),
            "doctor_name": appointment_data.get("doctor_name", ""),
            "specialization": appointment_data.get("specialization", ""),
            "date": appointment_data.get("date", ""),
            "time": appointment_data.get("time", ""),
            "type": appointment_data.get("type", "video"),
            "reason": appointment_data.get("reason", ""),
            "status": "upcoming",
            "notes": "",
            "created_at": firestore.SERVER_TIMESTAMP,
        }

        # Generate consultation record for video appointments
        if appt["type"] == "video":
            consultation_id = str(uuid.uuid4())
            room_hash = hashlib.sha256(f"{consultation_id}{int(time.time())}".encode()).hexdigest()[:12]
            room_name = f"medimind-{room_hash}"
            room_url = f"https://meet.jit.si/{room_name}"

            appt.update({
                "consultation_id": consultation_id,
                "room_name": room_name,
                "room_url": room_url,
            })

            # Store consultation
            db.collection("consultations").document(consultation_id).set({
                "id": consultation_id,
                "appointment_id": appt_id,
                "patient_id": uid,
                "doctor_id": appointment_data.get("doctor_id", ""),
                "report_id": appointment_data.get("report_id", ""),
                "room_name": room_name,
                "room_url": room_url,
                "status": "scheduled",
                "created_at": firestore.SERVER_TIMESTAMP,
            })

    db.collection("appointments").document(appt_id).set(appt)

    # Re-read to get resolved timestamps
    created = db.collection("appointments").document(appt_id).get().to_dict()
    created["id"] = appt_id
    # Convert timestamps
    for ts_field in ["created_at", "updated_at"]:
        ts = created.get(ts_field)
        if ts and hasattr(ts, "isoformat"):
            created[ts_field] = ts.isoformat()
    return created

@router.patch("/{appointment_id}")
async def update_appointment(appointment_id: str, update_data: dict, current_user: dict = Depends(get_current_user)):
    """Update an appointment (e.g. cancel, reschedule, complete, add notes)."""
    uid = current_user["uid"]
    ref = db.collection("appointments").document(appointment_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appt = doc.to_dict()
    # Allow update if user is the patient or doctor
    if appt.get("patient_id") != uid and appt.get("doctor_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Only allow safe fields to be updated
    allowed_fields = {"status", "date", "time", "reason", "notes", "type"}
    safe_update = {k: v for k, v in update_data.items() if k in allowed_fields}
    safe_update["updated_at"] = firestore.SERVER_TIMESTAMP

    ref.update(safe_update)
    updated = ref.get().to_dict()
    updated["id"] = appointment_id
    # Convert timestamps
    for ts_field in ["created_at", "updated_at"]:
        ts = updated.get(ts_field)
        if ts and hasattr(ts, "isoformat"):
            updated[ts_field] = ts.isoformat()
    return updated

@router.delete("/{appointment_id}")
async def delete_appointment(appointment_id: str, current_user: dict = Depends(get_current_user)):
    """Delete an appointment."""
    uid = current_user["uid"]
    ref = db.collection("appointments").document(appointment_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appt = doc.to_dict()
    # Allow delete if user is the patient or the doctor
    if appt.get("patient_id") != uid and appt.get("doctor_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    ref.delete()
    return {"message": "Appointment deleted"}
