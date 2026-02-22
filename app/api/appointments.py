from fastapi import APIRouter, Depends
from app.core.security import get_current_user

router = APIRouter()

@router.get("/")
async def get_appointments(current_user: dict = Depends(get_current_user)):
    return {"appointments": []}

@router.post("/")
async def create_appointment(appointment_data: dict, current_user: dict = Depends(get_current_user)):
    return {"message": "Appointment scheduled"}
