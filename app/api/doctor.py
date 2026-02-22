from fastapi import APIRouter, Depends
from app.core.security import get_current_doctor
from app.core.firebase import db

router = APIRouter()

@router.get("/me")
async def get_doctor_profile(current_user: dict = Depends(get_current_doctor)):
    return current_user

@router.patch("/me")
async def update_doctor_profile(profile_data: dict, current_user: dict = Depends(get_current_doctor)):
    user_ref = db.collection("users").document(current_user["uid"])
    update_data = {**profile_data, "profile_complete": True}
    user_ref.update(update_data)
    return {"message": "Profile updated", "profile": update_data}

@router.get("/patients")
async def get_doctor_patients(current_user: dict = Depends(get_current_doctor)):
    """Fetch patients assigned to this doctor from Firestore."""
    patients_ref = db.collection("users").where("role", "==", "patient").where("assigned_doctor", "==", current_user["uid"])
    docs = patients_ref.stream()
    patients = []
    for doc in docs:
        patient_data = doc.to_dict()
        # Don't expose sensitive fields
        patients.append({
            "uid": patient_data.get("uid"),
            "full_name": patient_data.get("full_name", "Unknown"),
            "email": patient_data.get("email"),
            "conditions": patient_data.get("conditions", ""),
            "age": patient_data.get("age"),
        })
    return {"patients": patients}

@router.get("/dashboard")
async def get_doctor_dashboard(current_user: dict = Depends(get_current_doctor)):
    """Compute live dashboard stats from Firestore."""
    # Count assigned patients
    patients_ref = db.collection("users").where("role", "==", "patient").where("assigned_doctor", "==", current_user["uid"])
    patients = list(patients_ref.stream())
    total_patients = len(patients)

    # Count pending reports for this doctor's patients
    patient_uids = [p.to_dict().get("uid") for p in patients]
    pending_reports = 0
    if patient_uids:
        for uid in patient_uids[:10]:  # Limit to avoid excessive reads
            reports = db.collection("reports").where("user_id", "==", uid).where("status", "==", "pending").stream()
            pending_reports += len(list(reports))

    return {
        "stats": {
            "total_patients": total_patients,
            "pending_reports": pending_reports,
        }
    }
