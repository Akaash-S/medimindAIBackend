"""
Consultation recommendation & video-room management.

Use-cases covered:
1. Post-report consultation  – AI suggests after risky analysis
2. Follow-up monitoring      – repeated elevated risk triggers suggestion
3. Prescription discussion   – doctor adds Rx → suggestion auto-created
4. AI escalation trigger     – high/critical risk → urgent recommendation
5. Second opinion            – patient shares report with another doctor
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db, firestore
from app.core.security import get_current_user
import uuid, hashlib, time

router = APIRouter()


# ===================== Recommendation Engine =====================

def generate_recommendation(
    user_id: str,
    doctor_id: str,
    report_id: str | None,
    reason_type: str,
    risk_level: str,
    summary: str,
    doctor_name: str = "",
    patient_name: str = "",
):
    """
    Create a consultation recommendation in Firestore.
    reason_type: post_report | follow_up | prescription | ai_escalation | second_opinion
    """
    rec_id = str(uuid.uuid4())
    urgency = "urgent" if risk_level.lower() == "high" else (
        "normal" if risk_level.lower() == "low" else "follow_up"
    )
    rec = {
        "id": rec_id,
        "patient_id": user_id,
        "doctor_id": doctor_id,
        "report_id": report_id,
        "reason_type": reason_type,
        "risk_level": risk_level,
        "urgency": urgency,
        "summary": summary,
        "doctor_name": doctor_name,
        "patient_name": patient_name,
        "status": "active",          # active | dismissed | booked
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection("consultation_recommendations").document(rec_id).set(rec)
    return rec_id


def auto_recommend_from_report(report_id: str, user_id: str, analysis: dict):
    """
    Called after AI analysis completes.  Decides whether to create a recommendation.
    """
    risk = (analysis.get("risk_level") or "").lower()
    if risk not in ("medium", "high"):
        return  # no recommendation for low-risk

    # Find assigned doctor
    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        return
    user_data = user_doc.to_dict()
    doctor_id = user_data.get("assigned_doctor", "")
    if not doctor_id:
        return

    doctor_doc = db.collection("users").document(doctor_id).get()
    doctor_name = doctor_doc.to_dict().get("full_name", "Doctor") if doctor_doc.exists else "Doctor"
    patient_name = user_data.get("full_name", "Patient")

    reason_type = "ai_escalation" if risk == "high" else "post_report"
    summary_text = analysis.get("summary", "Abnormal values detected in your report.")

    # Check for follow-up pattern (≥ 2 medium/high reports in last 30 days)
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_reports = (
        db.collection("reports")
        .where("user_id", "==", user_id)
        .where("status", "==", "completed")
        .stream()
    )
    elevated_count = 0
    for doc in recent_reports:
        d = doc.to_dict()
        r = (d.get("risk_level") or "").lower()
        if r in ("medium", "high"):
            elevated_count += 1
    if elevated_count >= 2:
        reason_type = "follow_up"
        summary_text = f"Multiple reports with elevated risk in the past 30 days. Follow-up recommended."

    generate_recommendation(
        user_id=user_id,
        doctor_id=doctor_id,
        report_id=report_id,
        reason_type=reason_type,
        risk_level=risk.capitalize(),
        summary=summary_text,
        doctor_name=doctor_name,
        patient_name=patient_name,
    )


# ===================== API Endpoints =====================

@router.get("/recommendations")
async def get_recommendations(current_user: dict = Depends(get_current_user)):
    """Get active consultation recommendations for the current user."""
    uid = current_user["uid"]
    role = current_user.get("role", "patient")

    field = "patient_id" if role == "patient" else "doctor_id"
    docs = (
        db.collection("consultation_recommendations")
        .where(field, "==", uid)
        .where("status", "==", "active")
        .stream()
    )

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        for ts in ["created_at"]:
            t = data.get(ts)
            if t and hasattr(t, "isoformat"):
                data[ts] = t.isoformat()
        results.append(data)

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results


from datetime import datetime, timedelta

def get_slots_for_day(date_obj: datetime, start_str: str, end_str: str):
    """Generate 30-min slots between start and end times."""
    slots = []
    try:
        current_time = datetime.strptime(f"{date_obj.date()} {start_str}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{date_obj.date()} {end_str}", "%Y-%m-%d %H:%M")
        
        while current_time + timedelta(minutes=30) <= end_time:
            next_time = current_time + timedelta(minutes=30)
            slots.append({
                "date": date_obj.strftime("%Y-%m-%d"),
                "start_time": current_time.strftime("%H:%M"),
                "end_time": next_time.strftime("%H:%M")
            })
            current_time = next_time
    except Exception as e:
        print(f"Error generating slots: {e}")
    return slots


@router.get("/slots/{doctor_id}")
async def get_doctor_slots(doctor_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch available slots (manual + dynamic) for a specific doctor."""
    # 1. Get manual slots (priority)
    manual_slots_ref = db.collection("users").document(doctor_id).collection("availability").where("status", "==", "free").stream()
    manual_slots = []
    for doc in manual_slots_ref:
        s = doc.to_dict()
        s["id"] = doc.id
        s["type"] = "manual"
        manual_slots.append(s)
        
    # 2. Get Doctor profile for working hours
    doc_ref = db.collection("users").document(doctor_id).get()
    doctor_data = doc_ref.to_dict() or {}
    working_hours = doctor_data.get("working_hours", [])
    
    # 3. Get existing appointments to filter
    appointments_ref = db.collection("appointments").where("doctor_id", "==", doctor_id).where("status", "==", "upcoming").stream()
    booked_times = []
    for appt in appointments_ref:
        ad = appt.to_dict()
        booked_times.append({
            "date": ad.get("date"),
            "time": ad.get("time") # e.g. "09:00 - 09:30"
        })
        
    dynamic_slots = []
    if working_hours:
        now = datetime.now()
        for i in range(14): # Look ahead 14 days
            day_obj = now + timedelta(days=i)
            day_name = day_obj.strftime("%A").lower()
            
            # Find working config for this day
            config = next((h for h in working_hours if h["day"] == day_name and h.get("active", False)), None)
            if config:
                day_candidates = get_slots_for_day(day_obj, config["start"], config["end"])
                for candidate in day_candidates:
                    # Filter if already exists in manual slots
                    if any(s["date"] == candidate["date"] and s["start_time"] == candidate["start_time"] for s in manual_slots):
                        continue
                    
                    # Filter if booked in appointments
                    time_range = f"{candidate['start_time']} - {candidate['end_time']}"
                    if any(bt["date"] == candidate["date"] and bt["time"] == time_range for bt in booked_times):
                        continue
                        
                    # Filter if in the past
                    slot_start_dt = datetime.strptime(f"{candidate['date']} {candidate['start_time']}", "%Y-%m-%d %H:%M")
                    if slot_start_dt < now:
                        continue
                        
                    candidate["id"] = f"dynamic_{candidate['date']}_{candidate['start_time']}"
                    candidate["status"] = "free"
                    candidate["type"] = "dynamic"
                    dynamic_slots.append(candidate)
                    
    all_slots = manual_slots + dynamic_slots
    all_slots.sort(key=lambda x: (x["date"], x["start_time"]))
    return all_slots


@router.post("/book")
async def book_consultation(body: dict, current_user: dict = Depends(get_current_user)):
    """
    Book a video consultation.  Creates an appointment + generates a Jitsi room.
    Body: { recommendation_id?, doctor_id, date, time, reason?, slot_id? }
    """
    uid = current_user["uid"]
    role = current_user.get("role", "patient")

    doctor_id = body.get("doctor_id", "")
    patient_id = uid if role == "patient" else body.get("patient_id", "")
    date = body.get("date", "")
    time_slot = body.get("time", "")
    reason = body.get("reason", "Video consultation")
    recommendation_id = body.get("recommendation_id")
    report_id = body.get("report_id")
    slot_id = body.get("slot_id")

    if not doctor_id or not date or not time_slot:
        raise HTTPException(status_code=400, detail="doctor_id, date, and time are required")

    # Mark slot as booked if provided
    if slot_id:
        slot_ref = db.collection("users").document(doctor_id).collection("availability").document(slot_id)
        if slot_ref.get().exists:
            slot_ref.update({"status": "booked"})

    # Get names
    if role == "patient":
        patient_name = current_user.get("full_name") or current_user.get("name", "Patient")
        doc_ref = db.collection("users").document(doctor_id).get()
        doctor_name = doc_ref.to_dict().get("full_name", "Doctor") if doc_ref.exists else "Doctor"
    else:
        doctor_name = current_user.get("full_name") or current_user.get("name", "Doctor")
        pat_ref = db.collection("users").document(patient_id).get()
        patient_name = pat_ref.to_dict().get("full_name", "Patient") if pat_ref.exists else "Patient"

    # Generate Jitsi room
    consultation_id = str(uuid.uuid4())
    room_hash = hashlib.sha256(f"{consultation_id}{int(time.time())}".encode()).hexdigest()[:12]
    room_name = f"medimind-{room_hash}"
    room_url = f"https://meet.jit.si/{room_name}"

    # Create appointment
    appt_id = str(uuid.uuid4())
    appt = {
        "id": appt_id,
        "consultation_id": consultation_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "date": date,
        "time": time_slot,
        "type": "video",
        "reason": reason,
        "status": "upcoming",
        "report_id": report_id or "",
        "room_name": room_name,
        "room_url": room_url,
        "notes": "",
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection("appointments").document(appt_id).set(appt)

    # Store consultation record
    consultation = {
        "id": consultation_id,
        "appointment_id": appt_id,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "report_id": report_id or "",
        "recommendation_id": recommendation_id or "",
        "room_name": room_name,
        "room_url": room_url,
        "status": "scheduled",  # scheduled | in_progress | completed | cancelled
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection("consultations").document(consultation_id).set(consultation)

    # Mark recommendation as booked (if provided)
    if recommendation_id:
        rec_ref = db.collection("consultation_recommendations").document(recommendation_id)
        if rec_ref.get().exists:
            rec_ref.update({"status": "booked", "consultation_id": consultation_id})

    # Re-read appointment with resolved timestamps
    created = db.collection("appointments").document(appt_id).get().to_dict()
    created["id"] = appt_id
    for ts_field in ["created_at", "updated_at"]:
        ts = created.get(ts_field)
        if ts and hasattr(ts, "isoformat"):
            created[ts_field] = ts.isoformat()
    created["consultation_id"] = consultation_id
    created["room_url"] = room_url
    return created


@router.get("/{consultation_id}/room")
async def get_room(consultation_id: str, current_user: dict = Depends(get_current_user)):
    """Get the video room URL and pre-consultation info for a consultation."""
    uid = current_user["uid"]

    doc = db.collection("consultations").document(consultation_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Consultation not found")

    data = doc.to_dict()
    if data.get("patient_id") != uid and data.get("doctor_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Fetch AI summary if a report is attached
    ai_summary = None
    report_id = data.get("report_id")
    if report_id:
        report_doc = db.collection("reports").document(report_id).get()
        if report_doc.exists:
            report_data = report_doc.to_dict()
            analysis = report_data.get("analysis", {})
            ai_summary = {
                "risk_level": report_data.get("risk_level", analysis.get("risk_level", "")),
                "summary": report_data.get("summary", analysis.get("summary", "")),
                "health_score": analysis.get("health_score"),
                "lab_values": analysis.get("lab_values", []),
            }

    return {
        "consultation_id": consultation_id,
        "room_name": data.get("room_name"),
        "room_url": data.get("room_url"),
        "status": data.get("status"),
        "report_id": report_id,
        "ai_summary": ai_summary,
    }


@router.patch("/{consultation_id}")
async def update_consultation(consultation_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    """Update consultation status (join, complete, cancel)."""
    uid = current_user["uid"]
    ref = db.collection("consultations").document(consultation_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Consultation not found")

    data = doc.to_dict()
    if data.get("patient_id") != uid and data.get("doctor_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    allowed = {"status"}
    safe = {k: v for k, v in body.items() if k in allowed}
    if not safe:
        raise HTTPException(status_code=400, detail="No valid fields")

    new_status = safe.get("status", "")
    valid_statuses = {"in_progress", "completed", "cancelled"}
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    safe["updated_at"] = firestore.SERVER_TIMESTAMP
    ref.update(safe)

    # Also update the linked appointment
    appt_id = data.get("appointment_id")
    if appt_id and new_status in ("completed", "cancelled"):
        appt_status = "completed" if new_status == "completed" else "cancelled"
        db.collection("appointments").document(appt_id).update({
            "status": appt_status,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })

    return {"message": f"Consultation {new_status}", "consultation_id": consultation_id}


@router.post("/dismiss")
async def dismiss_recommendation(body: dict, current_user: dict = Depends(get_current_user)):
    """Dismiss a consultation recommendation."""
    rec_id = body.get("recommendation_id", "")
    if not rec_id:
        raise HTTPException(status_code=400, detail="recommendation_id required")

    ref = db.collection("consultation_recommendations").document(rec_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    data = doc.to_dict()
    uid = current_user["uid"]
    if data.get("patient_id") != uid and data.get("doctor_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    ref.update({"status": "dismissed", "dismissed_at": firestore.SERVER_TIMESTAMP})
    return {"message": "Recommendation dismissed"}


@router.post("/second-opinion")
async def request_second_opinion(body: dict, current_user: dict = Depends(get_current_user)):
    """Patient requests a second opinion by sharing a report with another doctor."""
    uid = current_user["uid"]
    report_id = body.get("report_id", "")
    target_doctor_id = body.get("doctor_id", "")
    target_doctor_name = body.get("doctor_name", "")

    if not report_id or not target_doctor_id:
        raise HTTPException(status_code=400, detail="report_id and doctor_id are required")

    # Verify report belongs to user
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")
    if report_doc.to_dict().get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Not your report")

    patient_name = current_user.get("full_name") or current_user.get("name", "Patient")
    summary = report_doc.to_dict().get("summary", "Patient is seeking a second medical opinion on this report.")
    risk = report_doc.to_dict().get("risk_level", "Medium")

    rec_id = generate_recommendation(
        user_id=uid,
        doctor_id=target_doctor_id,
        report_id=report_id,
        reason_type="second_opinion",
        risk_level=risk,
        summary=summary,
        doctor_name=target_doctor_name,
        patient_name=patient_name,
    )

    return {"message": "Second opinion request sent", "recommendation_id": rec_id}


@router.post("/recommend")
async def manual_recommend_consultation(body: dict, current_user: dict = Depends(get_current_user)):
    """Doctor manually recommends a consultation for a report."""
    if current_user.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can recommend consultations")

    doctor_id = current_user["uid"]
    doctor_name = current_user.get("full_name") or current_user.get("name", "Doctor")
    
    report_id = body.get("report_id", "")
    patient_id = body.get("patient_id", "")
    summary = body.get("summary", "Doctor recommends a follow-up consultation to discuss your report.")
    risk_level = body.get("risk_level", "Medium")

    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required")

    pat_ref = db.collection("users").document(patient_id).get()
    patient_name = pat_ref.to_dict().get("full_name", "Patient") if pat_ref.exists else "Patient"

    rec_id = generate_recommendation(
        user_id=patient_id,
        doctor_id=doctor_id,
        report_id=report_id or None,
        reason_type="follow_up",
        risk_level=risk_level,
        summary=summary,
        doctor_name=doctor_name,
        patient_name=patient_name,
    )

    return {"message": "Recommendation sent to patient", "recommendation_id": rec_id}
