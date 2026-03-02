from fastapi import APIRouter, Depends, HTTPException
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
    """
    Assign (or re-assign) a doctor to the patient using the smart algorithm:
    - Specialization matching against patient conditions
    - Availability check (working_hours or free slots)
    - Least-loaded selection (fewest patients)
    Fresh search every time — does NOT skip if already assigned.
    """
    user_uid = current_user["uid"]
    user_ref = db.collection("users").document(user_uid)

    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    from app.services.assignment_service import assignment_service
    doctor_id = await assignment_service.assign_doctor_to_patient(user_uid)

    if not doctor_id:
        raise HTTPException(
            status_code=503,
            detail="No doctors available at the moment. Please try again later."
        )

    # Return updated doctor info
    doctor_doc = db.collection("users").document(doctor_id).get()
    doctor_data = doctor_doc.to_dict() if doctor_doc.exists else {}
    return {
        "message": "Doctor assigned successfully",
        "doctor_id": doctor_id,
        "doctor_name": doctor_data.get("full_name", "Unknown"),
        "specialization": doctor_data.get("specialization", ""),
    }


@router.post("/reassign-doctor")
async def reassign_doctor(current_user: dict = Depends(get_current_patient)):
    """
    Force a fresh doctor re-assignment, clearing any previous assignment.
    Triggered per-report when the patient explicitly requests a different doctor.
    Uses the full smart algorithm (specialization + availability + LLA).
    """
    user_uid = current_user["uid"]

    from app.services.assignment_service import assignment_service
    doctor_id = await assignment_service.reassign_doctor(user_uid)

    if not doctor_id:
        raise HTTPException(
            status_code=503,
            detail="No doctors available for re-assignment. Please try again later."
        )

    doctor_doc = db.collection("users").document(doctor_id).get()
    doctor_data = doctor_doc.to_dict() if doctor_doc.exists else {}
    return {
        "message": "Doctor re-assigned successfully",
        "doctor_id": doctor_id,
        "doctor_name": doctor_data.get("full_name", "Unknown"),
        "specialization": doctor_data.get("specialization", ""),
    }


@router.get("/my-doctor")
async def get_my_doctor(current_user: dict = Depends(get_current_patient)):
    """Fetch the full profile of the doctor assigned to the current patient."""
    doctor_id = current_user.get("assigned_doctor")
    if not doctor_id:
        return {"doctor": None, "message": "No doctor assigned yet"}
        
    doc_ref = db.collection("users").document(doctor_id).get()
    if not doc_ref.exists:
        raise HTTPException(status_code=404, detail="Assigned doctor profile not found")
        
    doctor_data = doc_ref.to_dict()
    return {
        "uid": doctor_id,
        "full_name": doctor_data.get("full_name", "Unknown"),
        "email": doctor_data.get("email"),
        "specialization": doctor_data.get("specialization"),
        "bio": doctor_data.get("bio"),
        "photo_url": doctor_data.get("photo_url"),
        "phone": doctor_data.get("phone"),
        "clinic_address": doctor_data.get("clinic_address"),
        "affiliation": doctor_data.get("affiliation"),
        "experience": doctor_data.get("experience"),
    }
