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
    
    # Return the full merged document
    updated_doc = user_ref.get()
    return updated_doc.to_dict()
