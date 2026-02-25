from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.security import get_current_doctor, get_current_user
from app.core.firebase import db, firestore

router = APIRouter()


@router.get("/me")
async def get_doctor_profile(current_user: dict = Depends(get_current_doctor)):
    return current_user


@router.patch("/me")
async def update_doctor_profile(profile_data: dict, current_user: dict = Depends(get_current_user)):
    """Update doctor profile — uses get_current_user (not get_current_doctor) 
    so new users completing onboarding can update before role check blocks them."""
    user_ref = db.collection("users").document(current_user["uid"])
    update_data = {**profile_data, "profile_complete": True}
    user_ref.update(update_data)
    
    # Return the full merged document
    updated_doc = user_ref.get()
    return updated_doc.to_dict()


# ==================== PATIENTS ====================


def _compute_risk(conditions: str, health_score: int) -> str:
    """Derive risk level from conditions and health score."""
    high_risk_conditions = [
        "hypertension", "diabetes", "coronary", "heart", "kidney", 
        "cancer", "stroke", "copd", "liver", "hiv"
    ]
    conditions_lower = conditions.lower() if conditions else ""
    has_high_risk = any(c in conditions_lower for c in high_risk_conditions)
    
    if health_score < 60 or has_high_risk:
        return "high"
    elif health_score < 75:
        return "medium"
    return "low"


def _get_initials(name: str) -> str:
    """Get initials from a name."""
    if not name:
        return "?"
    parts = name.strip().split()
    return "".join(p[0] for p in parts[:2]).upper()


@router.get("/patients")
async def get_doctor_patients(current_user: dict = Depends(get_current_doctor)):
    """Fetch patients assigned to this doctor with enriched data."""
    doctor_uid = current_user["uid"]
    
    patients_ref = db.collection("users").where(
        "role", "==", "patient"
    ).where("assigned_doctor", "==", doctor_uid)
    docs = list(patients_ref.stream())
    
    patients = []
    for doc in docs:
        pd = doc.to_dict()
        uid = pd.get("uid", doc.id)
        
        # Get report count and latest report
        reports_ref = db.collection("reports").where(
            "user_id", "==", uid
        ).order_by("created_at", direction=firestore.Query.DESCENDING).limit(1)
        report_docs = list(reports_ref.stream())
        
        report_count_ref = db.collection("reports").where("user_id", "==", uid)
        report_count = len(list(report_count_ref.stream()))
        
        last_report_date = None
        last_report_risk = None
        health_score = 75  # default
        
        if report_docs:
            latest = report_docs[0].to_dict()
            ts = latest.get("created_at")
            if ts:
                last_report_date = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            
            # Get AI analysis health score if available
            ai = latest.get("ai_analysis", {})
            if isinstance(ai, dict):
                health_score = ai.get("health_score", 75)
                last_report_risk = ai.get("risk_level")
        
        conditions = pd.get("conditions", "")
        risk = last_report_risk or _compute_risk(conditions, health_score)
        
        patients.append({
            "uid": uid,
            "full_name": pd.get("full_name", "Unknown"),
            "email": pd.get("email", ""),
            "age": pd.get("age"),
            "phone": pd.get("phone", ""),
            "gender": pd.get("gender", ""),
            "blood_group": pd.get("blood_group", ""),
            "address": pd.get("address", ""),
            "photo_url": pd.get("photo_url", ""),
            "conditions": conditions,
            "allergies": pd.get("allergies", ""),
            "avatar": _get_initials(pd.get("full_name", "")),
            "health_score": health_score,
            "risk": risk,
            "report_count": report_count,
            "last_report_date": last_report_date,
            "assigned_at": str(pd.get("assigned_at", "")) if pd.get("assigned_at") else None,
        })
    
    # Sort by risk (high first) then name
    risk_order = {"high": 0, "medium": 1, "low": 2}
    patients.sort(key=lambda p: (risk_order.get(p["risk"], 3), p["full_name"]))
    
    return {"patients": patients, "total": len(patients)}


@router.get("/patients/{patient_uid}")
async def get_patient_detail(patient_uid: str, current_user: dict = Depends(get_current_doctor)):
    """Get full detail for a single patient assigned to this doctor."""
    doctor_uid = current_user["uid"]
    
    # Verify patient is assigned to this doctor
    patient_ref = db.collection("users").document(patient_uid)
    patient_doc = patient_ref.get()
    if not patient_doc.exists:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    pd = patient_doc.to_dict()
    if pd.get("assigned_doctor") != doctor_uid:
        raise HTTPException(status_code=403, detail="Patient not assigned to you")
    
    # Get patient reports
    reports_ref = db.collection("reports").where(
        "user_id", "==", patient_uid
    ).order_by("created_at", direction=firestore.Query.DESCENDING).limit(20)
    report_docs = list(reports_ref.stream())
    
    reports = []
    health_score = 75
    for i, rdoc in enumerate(report_docs):
        rd = rdoc.to_dict()
        ai = rd.get("ai_analysis", {})
        has_ai = bool(ai) and isinstance(ai, dict)
        risk = ai.get("risk_level", "low") if has_ai else "low"
        
        if i == 0 and has_ai:
            health_score = ai.get("health_score", 75)
        
        ts = rd.get("created_at")
        created_at = ts.isoformat() if ts and hasattr(ts, "isoformat") else str(ts) if ts else None
        
        reports.append({
            "id": rd.get("id", rdoc.id),
            "file_name": rd.get("file_name", ""),
            "status": rd.get("status", "pending"),
            "created_at": created_at,
            "risk_level": risk,
            "has_ai": has_ai,
        })
    
    # Get doctor notes for this patient
    notes_ref = db.collection("doctor_notes").where(
        "patient_uid", "==", patient_uid
    ).where("doctor_uid", "==", doctor_uid).order_by(
        "created_at", direction=firestore.Query.DESCENDING
    ).limit(20)
    
    notes = []
    try:
        for ndoc in notes_ref.stream():
            nd = ndoc.to_dict()
            ts = nd.get("created_at")
            notes.append({
                "id": ndoc.id,
                "text": nd.get("text", ""),
                "created_at": ts.isoformat() if ts and hasattr(ts, "isoformat") else str(ts) if ts else None,
            })
    except Exception:
        pass  # Collection may not exist yet
    
    # Get prescriptions
    rx_ref = db.collection("prescriptions").where(
        "patient_uid", "==", patient_uid
    ).where("doctor_uid", "==", doctor_uid).order_by(
        "created_at", direction=firestore.Query.DESCENDING
    ).limit(20)
    
    prescriptions = []
    try:
        for rxdoc in rx_ref.stream():
            rx = rxdoc.to_dict()
            prescriptions.append({
                "id": rxdoc.id,
                "medicine": rx.get("medicine", ""),
                "dosage": rx.get("dosage", ""),
                "frequency": rx.get("frequency", ""),
                "duration": rx.get("duration", ""),
                "notes": rx.get("notes", ""),
            })
    except Exception:
        pass  # Collection may not exist yet
    
    conditions = pd.get("conditions", "")
    risk = _compute_risk(conditions, health_score)
    
    return {
        "uid": patient_uid,
        "full_name": pd.get("full_name", "Unknown"),
        "email": pd.get("email", ""),
        "age": pd.get("age"),
        "phone": pd.get("phone", ""),
        "gender": pd.get("gender", ""),
        "blood_group": pd.get("blood_group", ""),
        "address": pd.get("address", ""),
        "photo_url": pd.get("photo_url", ""),
        "conditions": conditions,
        "allergies": pd.get("allergies", ""),
        "avatar": _get_initials(pd.get("full_name", "")),
        "health_score": health_score,
        "risk": risk,
        "reports": reports,
        "notes": notes,
        "prescriptions": prescriptions,
    }


# ==================== NOTES ====================


class NoteCreate(BaseModel):
    text: str


@router.post("/patients/{patient_uid}/notes")
async def add_patient_note(
    patient_uid: str, 
    body: NoteCreate,
    current_user: dict = Depends(get_current_doctor)
):
    """Add a doctor note for a patient."""
    doctor_uid = current_user["uid"]
    
    # Verify assignment
    patient_doc = db.collection("users").document(patient_uid).get()
    if not patient_doc.exists:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient_doc.to_dict().get("assigned_doctor") != doctor_uid:
        raise HTTPException(status_code=403, detail="Patient not assigned to you")
    
    note_data = {
        "patient_uid": patient_uid,
        "doctor_uid": doctor_uid,
        "doctor_name": current_user.get("full_name", "Doctor"),
        "text": body.text,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    
    doc_ref = db.collection("doctor_notes").add(note_data)
    # Re-read to get actual timestamp
    created = doc_ref[1].get().to_dict()
    ts = created.get("created_at")
    
    return {
        "id": doc_ref[1].id,
        "text": body.text,
        "created_at": ts.isoformat() if ts and hasattr(ts, "isoformat") else str(ts) if ts else None,
    }


# ==================== PRESCRIPTIONS ====================


class PrescriptionCreate(BaseModel):
    medicine: str
    dosage: str
    frequency: str
    duration: str
    notes: Optional[str] = ""


@router.post("/patients/{patient_uid}/prescriptions")
async def add_prescription(
    patient_uid: str,
    body: PrescriptionCreate,
    current_user: dict = Depends(get_current_doctor)
):
    """Add a prescription for a patient."""
    doctor_uid = current_user["uid"]
    
    # Verify assignment
    patient_doc = db.collection("users").document(patient_uid).get()
    if not patient_doc.exists:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient_doc.to_dict().get("assigned_doctor") != doctor_uid:
        raise HTTPException(status_code=403, detail="Patient not assigned to you")
    
    rx_data = {
        "patient_uid": patient_uid,
        "doctor_uid": doctor_uid,
        "doctor_name": current_user.get("full_name", "Doctor"),
        "medicine": body.medicine,
        "dosage": body.dosage,
        "frequency": body.frequency,
        "duration": body.duration,
        "notes": body.notes or "",
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    
    doc_ref = db.collection("prescriptions").add(rx_data)
    
    return {
        "id": doc_ref[1].id,
        "medicine": body.medicine,
        "dosage": body.dosage,
        "frequency": body.frequency,
        "duration": body.duration,
        "notes": body.notes or "",
    }


# ==================== DASHBOARD ====================


@router.get("/dashboard")
async def get_doctor_dashboard(current_user: dict = Depends(get_current_doctor)):
    """Compute live dashboard stats from Firestore."""
    doctor_uid = current_user["uid"]
    
    # Count assigned patients
    patients_ref = db.collection("users").where(
        "role", "==", "patient"
    ).where("assigned_doctor", "==", doctor_uid)
    patients = list(patients_ref.stream())
    total_patients = len(patients)

    # Count pending reports for this doctor's patients
    patient_uids = [p.to_dict().get("uid") for p in patients]
    pending_reports = 0
    if patient_uids:
        for uid in patient_uids[:10]:  # Limit to avoid excessive reads
            reports = db.collection("reports").where(
                "user_id", "==", uid
            ).where("status", "==", "pending").stream()
            pending_reports += len(list(reports))

    return {
        "stats": {
            "total_patients": total_patients,
            "pending_reports": pending_reports,
        }
    }
