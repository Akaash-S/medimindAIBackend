from fastapi import APIRouter, Depends
from app.core.security import get_current_doctor

router = APIRouter()

@router.get("/patients")
async def get_doctor_patients(current_user: dict = Depends(get_current_doctor)):
    # Logic to fetch patients assigned to this doctor
    return {"patients": []}

@router.get("/dashboard")
async def get_doctor_dashboard(current_user: dict = Depends(get_current_doctor)):
    return {"stats": {"total_patients": 0, "pending_reports": 0}}
