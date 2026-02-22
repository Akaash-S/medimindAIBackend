from fastapi import APIRouter, Depends
from app.core.security import get_current_patient

router = APIRouter()

@router.get("/me")
async def get_patient_profile(current_user: dict = Depends(get_current_patient)):
    return current_user

@router.patch("/me")
async def update_patient_profile(profile_data: dict, current_user: dict = Depends(get_current_patient)):
    # Logic to update user in Firestore
    return {"message": "Profile updated"}
