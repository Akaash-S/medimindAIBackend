from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from app.core.firebase import db, firestore
from app.core.security import get_current_patient, get_current_user
from app.services.email_service import email_service
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

@router.get("/family/search")
async def search_users_for_family(q: str = Query(..., min_length=2), current_user: dict = Depends(get_current_patient)):
    """Search for doctors or patients by name or email to add to family."""
    # Note: For large DBs, use Algolia/Typesense. Since it's a small dataset, fetch all and filter.
    users_ref = db.collection("users").stream()
    results = []
    q_lower = q.lower()
    
    for u in users_ref:
        data = u.to_dict()
        uid = data.get("uid", u.id)
        if uid == current_user.get("uid"):
            continue
            
        full_name = data.get("full_name", "").lower()
        email = data.get("email", "").lower()
        
        if q_lower in full_name or q_lower in email:
            results.append({
                "uid": uid,
                "full_name": data.get("full_name"),
                "email": data.get("email"),
                "role": data.get("role"),
                "photo_url": data.get("photo_url")
            })
            
    return results[:10]  # Return top 10

@router.get("/family")
async def get_family_members(current_user: dict = Depends(get_current_patient)):
    """Retrieve all linked family members."""
    family_ref = db.collection("users").document(current_user["uid"]).collection("family_members").stream()
    members = []
    
    for f in family_ref:
        f_data = f.to_dict()
        f_data["id"] = f.id
        
        # Hydrate user data
        u_ref = db.collection("users").document(f_data.get("uid")).get()
        if u_ref.exists:
            u_data = u_ref.to_dict()
            f_data.update({
                "full_name": u_data.get("full_name"),
                "email": u_data.get("email"),
                "role": u_data.get("role"),
                "photo_url": u_data.get("photo_url")
            })
        members.append(f_data)
        
    return members

@router.post("/family")
async def add_family_member(data: dict, current_user: dict = Depends(get_current_patient)):
    """Add a user to family access and notify them."""
    target_uid = data.get("uid")
    if not target_uid:
        raise HTTPException(status_code=400, detail="Missing uid")
        
    target_ref = db.collection("users").document(target_uid).get()
    if not target_ref.exists:
        raise HTTPException(status_code=404, detail="User not found")
        
    target_data = target_ref.to_dict()
    family_col = db.collection("users").document(current_user["uid"]).collection("family_members")
    
    # Check duplicate
    existing = family_col.where("uid", "==", target_uid).get()
    if existing:
        raise HTTPException(status_code=400, detail="User already in family")
        
    # Store
    new_doc = family_col.document()
    new_doc.set({
        "uid": target_uid,
        "added_at": firestore.SERVER_TIMESTAMP
    })
    
    # Notify target
    patient_name = current_user.get("full_name", "A patient")
    target_email = target_data.get("email")
    target_name = target_data.get("full_name", "User")
    
    if target_email:
        await email_service.send_family_access_notification(
            to_email=target_email,
            user_name=target_name,
            patient_name=patient_name
        )
        
    return {"message": "Family member added successfully", "id": new_doc.id}

@router.delete("/family/{member_id}")
async def remove_family_member(member_id: str, current_user: dict = Depends(get_current_patient)):
    """Remove a linked family member."""
    doc_ref = db.collection("users").document(current_user["uid"]).collection("family_members").document(member_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Family member not found")
        
    doc_ref.delete()
    return {"message": "Removed successfully"}
