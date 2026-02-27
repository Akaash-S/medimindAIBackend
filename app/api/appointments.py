from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db, firestore
from app.core.security import get_current_user
import uuid, hashlib, time

router = APIRouter()

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
