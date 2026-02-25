from fastapi import APIRouter, Depends
from app.core.firebase import db
from app.core.security import get_current_patient, get_current_user

router = APIRouter()

@router.get("/me")
async def get_patient_profile(current_user: dict = Depends(get_current_patient)):
    return current_user

@router.patch("/me")
async def update_patient_profile(profile_data: dict, current_user: dict = Depends(get_current_user)):
    """Update patient profile — uses get_current_user (not get_current_patient) 
    so new users completing onboarding can update before role check blocks them."""
    user_ref = db.collection("users").document(current_user["uid"])
    
    # Merge profile data and mark complete
    update_data = {**profile_data, "profile_complete": True}
    user_ref.update(update_data)
    
    # Auto-assign doctor if not already assigned
    current_doc = user_ref.get().to_dict()
    if not current_doc.get("assigned_doctor"):
        try:
            from app.services.assignment_service import assignment_service
            await assignment_service.assign_doctor_to_patient(current_user["uid"])
        except Exception as assign_err:
            print(f"Doctor auto-assignment failed: {assign_err}")

    # Return the full merged document
    updated_doc = user_ref.get()
    return updated_doc.to_dict()
