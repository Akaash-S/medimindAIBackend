import html
from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db
from firebase_admin import firestore
from app.core.security import get_current_user
import uuid

router = APIRouter()


# ---------- Security Settings ----------

@router.get("/security/settings")
async def get_security_settings(current_user: dict = Depends(get_current_user)):
    """Get user's security/privacy settings."""
    uid = current_user["uid"]
    ref = db.collection("user_security").document(uid)
    doc = ref.get()

    defaults = {
        "two_factor_enabled": False,
        "biometric_enabled": False,
        "login_alerts": True,
        "share_reports_with_doctors": True,
        "share_trends_with_doctors": True,
        "allow_ai_analysis": True,
        "anonymous_research_data": False,
    }

    if doc.exists:
        data = doc.to_dict()
        return {**defaults, **data}
    return defaults


@router.patch("/security/settings")
async def update_security_settings(update_data: dict, current_user: dict = Depends(get_current_user)):
    """Update user's security/privacy settings."""
    uid = current_user["uid"]

    allowed_fields = {
        "two_factor_enabled", "biometric_enabled", "login_alerts",
        "share_reports_with_doctors", "share_trends_with_doctors",
        "allow_ai_analysis", "anonymous_research_data",
    }

    safe_update = {k: v for k, v in update_data.items() if k in allowed_fields}
    safe_update["updated_at"] = firestore.SERVER_TIMESTAMP

    ref = db.collection("user_security").document(uid)
    ref.set(safe_update, merge=True)

    # Log the settings change
    _log_activity(uid, "security", "Updated security settings")

    return {**safe_update, "message": "Settings updated"}


# ---------- Activity Log ----------

@router.get("/security/activity")
async def get_activity_log(current_user: dict = Depends(get_current_user)):
    """Get user's security activity log."""
    uid = current_user["uid"]

    docs = db.collection("user_activity") \
        .where("user_id", "==", uid) \
        .limit(50) \
        .stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)

    # Sort by created_at descending
    results.sort(key=lambda x: x.get("created_at", "") or "", reverse=True)
    return results


@router.post("/security/activity")
async def create_activity_entry(entry_data: dict, current_user: dict = Depends(get_current_user)):
    """Log a security-related activity."""
    uid = current_user["uid"]

    action = html.escape((entry_data.get("action", "")).strip()[:200])
    activity_type = entry_data.get("type", "security")
    who = html.escape((entry_data.get("who", "You")).strip()[:50])

    if not action:
        raise HTTPException(status_code=400, detail="Action is required")

    _log_activity(uid, activity_type, action, who)
    return {"message": "Activity logged"}


# ---------- Active Sessions ----------

@router.get("/security/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    """Get user's active sessions."""
    uid = current_user["uid"]

    docs = db.collection("user_sessions") \
        .where("user_id", "==", uid) \
        .stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)

    # Sort by last_active descending
    results.sort(key=lambda x: x.get("last_active", "") or "", reverse=True)
    return results


@router.post("/security/sessions/register")
async def register_session(session_data: dict, current_user: dict = Depends(get_current_user)):
    """Register a new login session."""
    uid = current_user["uid"]
    session_id = str(uuid.uuid4())

    session = {
        "id": session_id,
        "user_id": uid,
        "device": html.escape((session_data.get("device", "Unknown device")).strip()[:100]),
        "browser": html.escape((session_data.get("browser", "")).strip()[:50]),
        "location": html.escape((session_data.get("location", "Unknown")).strip()[:100]),
        "ip": html.escape((session_data.get("ip", "")).strip()[:45]),
        "is_current": session_data.get("is_current", False),
        "last_active": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    db.collection("user_sessions").document(session_id).set(session)
    _log_activity(uid, "login", f"New login from {session['device']}")
    return session


@router.delete("/security/sessions/{session_id}")
async def revoke_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Revoke an active session."""
    uid = current_user["uid"]
    ref = db.collection("user_sessions").document(session_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = doc.to_dict()
    if data.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    ref.delete()
    _log_activity(uid, "security", f"Revoked session {data.get('device', 'unknown')}")
    return {"message": "Session revoked"}


@router.post("/security/sessions/revoke-all")
async def revoke_all_other_sessions(current_user: dict = Depends(get_current_user)):
    """Revoke all sessions except the current one."""
    uid = current_user["uid"]

    docs = db.collection("user_sessions") \
        .where("user_id", "==", uid) \
        .stream()

    revoked = 0
    for doc in docs:
        data = doc.to_dict()
        if not data.get("is_current"):
            doc.reference.delete()
            revoked += 1

    _log_activity(uid, "security", f"Revoked {revoked} other sessions")
    return {"message": f"Revoked {revoked} sessions", "count": revoked}


# ---------- Helpers ----------

def _log_activity(user_id: str, activity_type: str, action: str, who: str = "You"):
    """Internal helper to log security activities."""
    entry_id = str(uuid.uuid4())
    db.collection("user_activity").document(entry_id).set({
        "id": entry_id,
        "user_id": user_id,
        "type": activity_type,
        "action": action,
        "who": who,
        "created_at": firestore.SERVER_TIMESTAMP,
    })
