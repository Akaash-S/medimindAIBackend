import html
import hashlib
import secrets
import base64
import io
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.firebase import db
from firebase_admin import firestore
from app.core.security import get_current_user
import uuid
import pyotp
import qrcode

router = APIRouter()


# ===================== TOTP 2FA =====================

@router.post("/security/2fa/setup")
async def setup_2fa(current_user: dict = Depends(get_current_user)):
    """Generate TOTP secret and QR code URI for authenticator app setup."""
    uid = current_user["uid"]
    email = current_user.get("email", "user@medimind.ai")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    existing = doc.to_dict() if doc.exists else {}

    # If already enabled and verified, don't regenerate
    if existing.get("two_factor_enabled") and existing.get("totp_verified"):
        raise HTTPException(status_code=400, detail="2FA is already enabled. Disable it first to reconfigure.")

    # Generate new TOTP secret
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=email, issuer_name="MediMind AI")

    # Generate QR code as base64 image
    qr = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Store secret (not yet verified)
    ref.set({
        "totp_secret": secret,
        "totp_verified": False,
    }, merge=True)

    _log_activity(uid, "security", "Started 2FA setup")

    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "qr_code": f"data:image/png;base64,{qr_base64}",
    }


@router.post("/security/2fa/verify")
async def verify_2fa_setup(body: dict, current_user: dict = Depends(get_current_user)):
    """Verify the TOTP code during initial setup. On success, enable 2FA + generate recovery codes."""
    uid = current_user["uid"]
    code = str(body.get("code", "")).strip()

    if not code or len(code) != 6:
        raise HTTPException(status_code=400, detail="Please enter a valid 6-digit code")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="2FA setup not started")

    data = doc.to_dict()
    secret = data.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="2FA setup not started. Please setup first.")

    # Verify the code
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code. Check your authenticator app and try again.")

    # Generate 10 recovery codes
    recovery_codes = [secrets.token_hex(4).upper() for _ in range(10)]  # 8-char hex codes
    hashed_codes = [hashlib.sha256(c.encode()).hexdigest() for c in recovery_codes]

    ref.set({
        "two_factor_enabled": True,
        "totp_verified": True,
        "recovery_codes_hashed": hashed_codes,
        "recovery_codes_count": len(hashed_codes),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    _log_activity(uid, "security", "Enabled two-factor authentication")

    return {
        "message": "2FA enabled successfully",
        "recovery_codes": recovery_codes,
    }


@router.post("/security/2fa/disable")
async def disable_2fa(body: dict, current_user: dict = Depends(get_current_user)):
    """Disable 2FA. Requires current TOTP code or a recovery code."""
    uid = current_user["uid"]
    code = str(body.get("code", "")).strip()

    if not code:
        raise HTTPException(status_code=400, detail="Please enter your authenticator code or a recovery code")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="2FA is not configured")

    data = doc.to_dict()
    if not data.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA is not currently enabled")

    secret = data.get("totp_secret", "")
    verified = False

    # Try TOTP verification first
    if len(code) == 6 and code.isdigit():
        totp = pyotp.TOTP(secret)
        verified = totp.verify(code, valid_window=1)

    # Try recovery code
    if not verified:
        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        stored_hashes = data.get("recovery_codes_hashed", [])
        if code_hash in stored_hashes:
            verified = True

    if not verified:
        raise HTTPException(status_code=400, detail="Invalid code. Enter your authenticator code or a recovery code.")

    # Disable 2FA
    ref.set({
        "two_factor_enabled": False,
        "totp_verified": False,
        "totp_secret": firestore.DELETE_FIELD,
        "recovery_codes_hashed": firestore.DELETE_FIELD,
        "recovery_codes_count": 0,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    _log_activity(uid, "security", "Disabled two-factor authentication")

    return {"message": "2FA disabled successfully"}


@router.post("/security/2fa/validate")
async def validate_2fa_code(body: dict, current_user: dict = Depends(get_current_user)):
    """Validate a TOTP code (used during login or sensitive operations)."""
    uid = current_user["uid"]
    code = str(body.get("code", "")).strip()

    if not code:
        raise HTTPException(status_code=400, detail="Code is required")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    if not doc.exists:
        return {"valid": False}

    data = doc.to_dict()
    if not data.get("two_factor_enabled"):
        return {"valid": True, "message": "2FA not enabled, no validation needed"}

    secret = data.get("totp_secret", "")
    totp = pyotp.TOTP(secret)

    if totp.verify(code, valid_window=1):
        return {"valid": True}

    return {"valid": False, "message": "Invalid code"}


@router.post("/security/password")
async def set_medimind_password(body: dict, current_user: dict = Depends(get_current_user)):
    """Set or update the custom MediMind password (used for 2FA)."""
    uid = current_user["uid"]
    password = body.get("password")
    current_password = body.get("current_password")
    
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    
    data = doc.to_dict() if doc.exists else {}

    if doc.exists:
        stored_hash = data.get("medimind_password_hash")
        salt = data.get("medimind_password_salt")

        # If a password already exists, require the current password
        if stored_hash and salt:
            if not current_password:
                raise HTTPException(status_code=400, detail="Current password is required to set a new password")
            
            current_hash = hashlib.sha256((current_password + salt).encode()).hexdigest()
            if current_hash != stored_hash:
                raise HTTPException(status_code=401, detail="Incorrect current password")

    new_salt = secrets.token_hex(16)
    hashed_password = hashlib.sha256((password + new_salt).encode()).hexdigest()

    ref.set({
        "medimind_password_hash": hashed_password,
        "medimind_password_salt": new_salt,
        "updated_at": firestore.SERVER_TIMESTAMP
    }, merge=True)

    action = "Updated" if data.get("medimind_password_hash") else "Set"
    _log_activity(uid, "security", f"{action} custom MediMind password")
    return {"message": "Password set successfully"}


@router.post("/security/2fa/verify-password")
async def verify_medimind_password(body: dict, current_user: dict = Depends(get_current_user)):
    """Verify the custom MediMind password (step 1 of 2FA)."""
    uid = current_user["uid"]
    password = body.get("password")

    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="Security profile not found")

    data = doc.to_dict()
    stored_hash = data.get("medimind_password_hash")
    salt = data.get("medimind_password_salt")

    if not stored_hash or not salt:
        raise HTTPException(status_code=400, detail="Password not set for this account")

    current_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    if current_hash != stored_hash:
        raise HTTPException(status_code=401, detail="Incorrect password")

    return {"valid": True}


# ===================== Recovery Codes =====================

@router.post("/security/2fa/recovery-codes")
async def regenerate_recovery_codes(body: dict, current_user: dict = Depends(get_current_user)):
    """Regenerate recovery codes. Requires current TOTP code to authorize."""
    uid = current_user["uid"]
    code = str(body.get("code", "")).strip()

    if not code or len(code) != 6:
        raise HTTPException(status_code=400, detail="Enter your current authenticator code")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="2FA not configured")

    data = doc.to_dict()
    if not data.get("two_factor_enabled"):
        raise HTTPException(status_code=400, detail="2FA must be enabled first")

    # Verify TOTP code
    secret = data.get("totp_secret", "")
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")

    # Generate new recovery codes
    recovery_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    hashed_codes = [hashlib.sha256(c.encode()).hexdigest() for c in recovery_codes]

    ref.set({
        "recovery_codes_hashed": hashed_codes,
        "recovery_codes_count": len(hashed_codes),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    _log_activity(uid, "security", "Regenerated recovery codes")

    return {
        "message": "Recovery codes regenerated",
        "recovery_codes": recovery_codes,
    }


@router.post("/security/2fa/recover")
async def use_recovery_code(body: dict, current_user: dict = Depends(get_current_user)):
    """Use a recovery code to authenticate (consumes the code)."""
    uid = current_user["uid"]
    code = str(body.get("code", "")).strip().upper()

    if not code:
        raise HTTPException(status_code=400, detail="Recovery code is required")

    ref = db.collection("user_security").document(uid)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=400, detail="No 2FA configuration found")

    data = doc.to_dict()
    stored_hashes = data.get("recovery_codes_hashed", [])
    code_hash = hashlib.sha256(code.encode()).hexdigest()

    if code_hash not in stored_hashes:
        raise HTTPException(status_code=400, detail="Invalid recovery code")

    # Remove the used code
    stored_hashes.remove(code_hash)
    ref.set({
        "recovery_codes_hashed": stored_hashes,
        "recovery_codes_count": len(stored_hashes),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    _log_activity(uid, "security", "Used a recovery code to authenticate")

    return {"valid": True, "remaining_codes": len(stored_hashes)}


# ===================== Security Settings =====================

@router.get("/security/settings")
async def get_security_settings(current_user: dict = Depends(get_current_user)):
    """Get user's security/privacy settings."""
    uid = current_user["uid"]
    ref = db.collection("user_security").document(uid)
    doc = ref.get()

    defaults = {
        "two_factor_enabled": False,
        "totp_verified": False,
        "biometric_enabled": False,
        "login_alerts": True,
        "share_reports_with_doctors": True,
        "share_trends_with_doctors": True,
        "allow_ai_analysis": True,
        "anonymous_research_data": False,
        "recovery_codes_count": 0,
        "has_medimind_password": False,
    }

    if doc.exists:
        data = doc.to_dict()
        defaults["has_medimind_password"] = "medimind_password_hash" in data
        # Never expose secret or hashed codes via GET
        safe_data = {k: v for k, v in data.items()
                     if k not in ("totp_secret", "recovery_codes_hashed", "medimind_password_hash", "medimind_password_salt")}
        return {**defaults, **safe_data}
    return defaults


@router.patch("/security/settings")
async def update_security_settings(update_data: dict, current_user: dict = Depends(get_current_user)):
    """Update user's security/privacy settings (toggles only)."""
    uid = current_user["uid"]

    allowed_fields = {
        "biometric_enabled", "login_alerts",
        "share_reports_with_doctors", "share_trends_with_doctors",
        "allow_ai_analysis", "anonymous_research_data",
    }

    safe_update = {k: v for k, v in update_data.items() if k in allowed_fields}
    if not safe_update:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    safe_update["updated_at"] = firestore.SERVER_TIMESTAMP

    ref = db.collection("user_security").document(uid)
    ref.set(safe_update, merge=True)

    # Log specific changes
    changed = ", ".join(f"{k}={'on' if v else 'off'}" for k, v in safe_update.items() if k != "updated_at")
    _log_activity(uid, "security", f"Updated settings: {changed}")

    response = {k: v for k, v in safe_update.items() if k != "updated_at"}
    response["message"] = "Settings updated"
    return response


@router.get("/security/sharing-status")
async def get_sharing_status(current_user: dict = Depends(get_current_user)):
    """Get a summary of data sharing preferences."""
    uid = current_user["uid"]
    ref = db.collection("user_security").document(uid)
    doc = ref.get()

    defaults = {
        "share_reports_with_doctors": True,
        "share_trends_with_doctors": True,
        "allow_ai_analysis": True,
        "anonymous_research_data": False,
    }

    if doc.exists:
        data = doc.to_dict()
        for key in defaults:
            if key in data:
                defaults[key] = data[key]

    enabled_count = sum(1 for v in defaults.values() if v)
    return {
        **defaults,
        "enabled_count": enabled_count,
        "total_count": len(defaults),
        "summary": f"{enabled_count} of {len(defaults)} sharing options enabled",
    }


# ===================== Activity Log =====================

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


# ===================== Session Management =====================

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

    results.sort(key=lambda x: x.get("last_active", "") or "", reverse=True)
    return results


@router.post("/security/sessions/register")
async def register_session(session_data: dict, request: Request, current_user: dict = Depends(get_current_user)):
    """Register a new login session with auto-detected device info."""
    uid = current_user["uid"]
    session_id = str(uuid.uuid4())

    # Auto-detect from request headers
    user_agent = request.headers.get("user-agent", "Unknown")
    forwarded_ip = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_ip.split(",")[0].strip() if forwarded_ip else (request.client.host if request.client else "Unknown")

    # Parse device/browser from user-agent
    device = _parse_device(user_agent)
    browser = _parse_browser(user_agent)

    session = {
        "id": session_id,
        "user_id": uid,
        "device": html.escape(session_data.get("device", device).strip()[:100]),
        "browser": html.escape(session_data.get("browser", browser).strip()[:50]),
        "location": html.escape(session_data.get("location", "Unknown").strip()[:100]),
        "ip": html.escape(client_ip[:45]),
        "is_current": True,
        "user_agent": user_agent[:300],
        "last_active": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    # Mark all other sessions as not current
    existing = db.collection("user_sessions") \
        .where("user_id", "==", uid) \
        .where("is_current", "==", True) \
        .stream()

    for doc in existing:
        doc.reference.update({"is_current": False})

    db.collection("user_sessions").document(session_id).set(session)

    # Login alert
    _send_login_alert(uid, session)

    response = {k: v for k, v in session.items()
                if k not in ("last_active", "created_at", "user_agent")}
    response["session_id"] = session_id
    return response


@router.patch("/security/sessions/{session_id}/heartbeat")
async def session_heartbeat(session_id: str, current_user: dict = Depends(get_current_user)):
    """Update the last_active timestamp for a session (keepalive)."""
    uid = current_user["uid"]
    ref = db.collection("user_sessions").document(session_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = doc.to_dict()
    if data.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    ref.update({"last_active": firestore.SERVER_TIMESTAMP})
    return {"message": "Heartbeat recorded"}


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


# ===================== Helpers =====================

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


def _send_login_alert(user_id: str, session: dict):
    """If login alerts are enabled, log a login event."""
    ref = db.collection("user_security").document(user_id)
    doc = ref.get()
    if doc.exists:
        data = doc.to_dict()
        if data.get("login_alerts", True):
            device = session.get("device", "Unknown device")
            ip = session.get("ip", "Unknown")
            _log_activity(
                user_id, "login",
                f"New sign-in detected from {device} (IP: {ip})"
            )


def _parse_device(user_agent: str) -> str:
    """Parse device info from User-Agent string."""
    ua = user_agent.lower()
    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android Device"
    if "macintosh" in ua or "mac os" in ua:
        return "Mac"
    if "windows" in ua:
        return "Windows PC"
    if "linux" in ua:
        return "Linux PC"
    return "Unknown Device"


def _parse_browser(user_agent: str) -> str:
    """Parse browser name from User-Agent string."""
    ua = user_agent.lower()
    if "edg" in ua:
        return "Edge"
    if "chrome" in ua and "safari" in ua:
        return "Chrome"
    if "firefox" in ua:
        return "Firefox"
    if "safari" in ua:
        return "Safari"
    if "opera" in ua or "opr" in ua:
        return "Opera"
    return "Unknown Browser"
