from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db, firestore
from app.core.security import get_current_user
import uuid

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
        results.append(data)

    # Sort by date descending
    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results

@router.post("/")
async def create_appointment(appointment_data: dict, current_user: dict = Depends(get_current_user)):
    """Create a new appointment."""
    uid = current_user["uid"]
    appt_id = str(uuid.uuid4())

    appt = {
        "id": appt_id,
        "patient_id": uid,
        "patient_name": current_user.get("full_name") or current_user.get("name", "Patient"),
        "doctor_name": appointment_data.get("doctor_name", ""),
        "specialization": appointment_data.get("specialization", ""),
        "date": appointment_data.get("date", ""),
        "time": appointment_data.get("time", ""),
        "type": appointment_data.get("type", "video"),  # video or in-person
        "reason": appointment_data.get("reason", ""),
        "status": "upcoming",
        "notes": "",
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    db.collection("appointments").document(appt_id).set(appt)
    return appt

@router.patch("/{appointment_id}")
async def update_appointment(appointment_id: str, update_data: dict, current_user: dict = Depends(get_current_user)):
    """Update an appointment (e.g. cancel, reschedule, add notes)."""
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
    if appt.get("patient_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    ref.delete()
    return {"message": "Appointment deleted"}
