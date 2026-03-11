from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.firebase import db, firestore
from app.core.security import get_current_user
from app.services.email_service import email_service
from datetime import datetime

router = APIRouter()

@router.post("/grant")
async def grant_family_access(data: dict, current_user: dict = Depends(get_current_user)):
    """Grant family access to another user."""
    target_uid = data.get("uid")
    if not target_uid:
        raise HTTPException(status_code=400, detail="Target user UID is required")
    
    if target_uid == current_user["uid"]:
        raise HTTPException(status_code=400, detail="You cannot grant access to yourself")

    # Check if target user exists
    target_ref = db.collection("users").document(target_uid).get()
    if not target_ref.exists:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    target_data = target_ref.to_dict()

    # Check for existing active link
    existing = db.collection("family_links").where("sender_id", "==", current_user["uid"]).where("receiver_id", "==", target_uid).where("status", "==", "active").get()
    if existing:
        raise HTTPException(status_code=400, detail="Access already granted to this user")

    # Create the link
    link_data = {
        "sender_id": current_user["uid"],
        "receiver_id": target_uid,
        "sender_name": current_user.get("full_name", "Unknown"),
        "receiver_name": target_data.get("full_name", "Unknown"),
        "sender_role": current_user.get("role"),
        "receiver_role": target_data.get("role"),
        "created_at": firestore.SERVER_TIMESTAMP,
        "status": "active"
    }
    
    db.collection("family_links").add(link_data)

    # Create notification for target
    notification_data = {
        "type": "family_access",
        "from_name": current_user.get("full_name", "A user"),
        "from_uid": current_user["uid"],
        "message": f"{current_user.get('full_name')} has granted you family access to their health record.",
        "created_at": firestore.SERVER_TIMESTAMP,
        "read": False
    }
    db.collection("users").document(target_uid).collection("notifications").add(notification_data)

    # Optional: Send email via service
    target_email = target_data.get("email")
    if target_email:
        try:
            await email_service.send_family_access_notification(
                to_email=target_email,
                user_name=target_data.get("full_name", "User"),
                patient_name=current_user.get("full_name", "A patient")
            )
        except Exception as e:
            print(f"Failed to send family access email: {e}")

    return {"message": "Access granted successfully"}

@router.get("/sent")
async def get_sent_access(current_user: dict = Depends(get_current_user)):
    """Get list of users this user has granted access to."""
    links = db.collection("family_links").where("sender_id", "==", current_user["uid"]).where("status", "==", "active").stream()
    
    results = []
    for link in links:
        data = link.to_dict()
        data["id"] = link.id
        # Hydrate receiver details if needed
        u_ref = db.collection("users").document(data["receiver_id"]).get()
        if u_ref.exists:
            u_data = u_ref.to_dict()
            data["receiver_photo"] = u_data.get("photo_url")
            data["receiver_email"] = u_data.get("email")
        results.append(data)
    
    return results

@router.get("/received")
async def get_received_access(current_user: dict = Depends(get_current_user)):
    """Get list of users who have granted access to this user."""
    links = db.collection("family_links").where("receiver_id", "==", current_user["uid"]).where("status", "==", "active").stream()
    
    results = []
    for link in links:
        data = link.to_dict()
        data["id"] = link.id
        # Hydrate sender details
        u_ref = db.collection("users").document(data["sender_id"]).get()
        if u_ref.exists:
            u_data = u_ref.to_dict()
            data["sender_photo"] = u_data.get("photo_url")
            data["sender_email"] = u_data.get("email")
        results.append(data)
    
    return results

@router.delete("/links/{link_id}")
async def revoke_access(link_id: str, current_user: dict = Depends(get_current_user)):
    """Revoke a family access link (only sender can revoke)."""
    link_ref = db.collection("family_links").document(link_id)
    link_doc = link_ref.get()
    
    if not link_doc.exists:
        raise HTTPException(status_code=404, detail="Access link not found")
        
    data = link_doc.to_dict()
    if data["sender_id"] != current_user["uid"]:
        raise HTTPException(status_code=403, detail="You are not authorized to revoke this access")
        
    link_ref.delete()
    return {"message": "Access revoked successfully"}

@router.get("/notifications")
async def get_notifications(current_user: dict = Depends(get_current_user)):
    """Get user's notifications."""
    notifs = db.collection("users").document(current_user["uid"]).collection("notifications").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()
    
    results = []
    for n in notifs:
        data = n.to_dict()
        data["id"] = n.id
        if "created_at" in data and data["created_at"]:
            data["created_at"] = data["created_at"].isoformat()
        results.append(data)
    
    return results

@router.patch("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a notification as read."""
    notif_ref = db.collection("users").document(current_user["uid"]).collection("notifications").document(notif_id)
    if not notif_ref.get().exists:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    notif_ref.update({"read": True})
    return {"message": "Notification marked as read"}

@router.get("/members/{uid}/records")
async def get_member_records(uid: str, current_user: dict = Depends(get_current_user)):
    """Fetch all records for a family member if access is granted."""
    # 1. Verify access link exists and is active (current_user is receiver, member is sender)
    access_check = db.collection("family_links").where("sender_id", "==", uid).where("receiver_id", "==", current_user["uid"]).where("status", "==", "active").get()
    
    if not access_check:
        raise HTTPException(status_code=403, detail="You do not have access to this member's records")

    # 2. Fetch member profile
    member_ref = db.collection("users").document(uid).get()
    if not member_ref.exists:
        raise HTTPException(status_code=404, detail="Member not found")
    
    member_data = member_ref.to_dict()
    profile = {
        "full_name": member_data.get("full_name"),
        "email": member_data.get("email"),
        "photo_url": member_data.get("photo_url"),
        "role": member_data.get("role")
    }

    # 3. Fetch reports
    reports_docs = db.collection("reports").where("user_id", "==", uid).stream()
    reports = []
    for doc in reports_docs:
        data = doc.to_dict()
        data["id"] = doc.id
        # Standardize timestamps
        for ts_field in ("created_at", "processed_at", "assigned_at", "reviewed_at"):
            val = data.get(ts_field)
            if val and hasattr(val, "isoformat"):
                data[ts_field] = val.isoformat()
        reports.append(data)
    
    # Sort reports newest first
    reports.sort(key=lambda r: r.get("created_at") or "", reverse=True)

    # 4. Fetch prescriptions
    presc_docs = db.collection("prescriptions").where("patient_uid", "==", uid).stream()
    prescriptions = []
    for doc in presc_docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if "created_at" in data and hasattr(data["created_at"], "isoformat"):
            data["created_at"] = data["created_at"].isoformat()
        data["medication_name"] = data.get("medicine", "Unknown")
        prescriptions.append(data)
    
    # Sort prescriptions newest first
    prescriptions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {
        "profile": profile,
        "reports": reports,
        "prescriptions": prescriptions
    }
