from fastapi import APIRouter, Depends, HTTPException, Body
from app.core.security import get_current_user
from app.core.firebase import db
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UserState(BaseModel):
    uid: str
    email: str
    role: Optional[str] = None
    profile_complete: bool = False

@router.get("/me", response_model=UserState)
async def get_my_state(current_user: dict = Depends(get_current_user)):
    return {
        "uid": current_user.get("uid"),
        "email": current_user.get("email"),
        "role": current_user.get("role"),
        "profile_complete": current_user.get("profile_complete", False)
    }

@router.patch("/role")
async def select_role(
    role: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    if role not in ["patient", "doctor"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'patient' or 'doctor'.")
    
    user_ref = db.collection("users").document(current_user["uid"])
    user_ref.update({"role": role})
    
    return {"message": f"Role set to {role}", "role": role}
