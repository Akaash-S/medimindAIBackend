from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db, firestore
from app.core.security import get_current_patient, get_current_user

router = APIRouter()


@router.get("/me")
async def get_patient_profile(current_user: dict = Depends(get_current_patient)):
    return current_user


@router.patch("/me")
async def update_patient_profile(profile_data: dict, current_user: dict = Depends(get_current_user)):
    """Update patient profile — uses get_current_user so new users completing onboarding
    can update before role check blocks them."""
    user_ref = db.collection("users").document(current_user["uid"])
    update_data = {**profile_data, "profile_complete": True}
    user_ref.update(update_data)
    updated_doc = user_ref.get()
    return updated_doc.to_dict()


@router.get("/my-doctor")
async def get_my_doctor(current_user: dict = Depends(get_current_patient)):
    """
    Returns the most recently assigned doctor for this patient (for chat).
    For per-report doctor data, use GET /reports/ which includes doctor_id per report.
    """
    doctor_id = current_user.get("assigned_doctor")
    if not doctor_id:
        return {"doctor": None, "message": "No doctor assigned yet"}

    doc_ref = db.collection("users").document(doctor_id).get()
    if not doc_ref.exists:
        raise HTTPException(status_code=404, detail="Assigned doctor profile not found")

    doctor_data = doc_ref.to_dict()
    return {
        "uid":            doctor_id,
        "full_name":      doctor_data.get("full_name", "Unknown"),
        "email":          doctor_data.get("email"),
        "specialization": doctor_data.get("specialization"),
        "bio":            doctor_data.get("bio"),
        "photo_url":      doctor_data.get("photo_url"),
        "phone":          doctor_data.get("phone"),
        "clinic_address": doctor_data.get("clinic_address"),
        "affiliation":    doctor_data.get("affiliation"),
        "experience":     doctor_data.get("experience"),
    }
