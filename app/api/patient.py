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


@router.post("/assign-doctor")
async def manual_assign_doctor(current_user: dict = Depends(get_current_patient)):
    """Allow patient to manually trigger doctor assignment if not already linked."""
    user_uid = current_user["uid"]
    user_ref = db.collection("users").document(user_uid)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
        
    user_data = user_doc.to_dict()
    if user_data.get("assigned_doctor"):
        return {"message": "Doctor already assigned", "doctor_id": user_data["assigned_doctor"]}
        
    from app.services.assignment_service import assignment_service
    doctor_id = await assignment_service.assign_doctor_to_patient(user_uid)
    
    if not doctor_id:
        raise HTTPException(status_code=503, detail="No doctors available at the moment. Please try again later.")
        
    return {"message": "Doctor assigned successfully", "doctor_id": doctor_id}

