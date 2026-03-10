from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from app.core.security import get_current_user, get_current_patient
from app.services.storage_service import storage_service
from app.services.report_service import process_report_task
from app.core.firebase import db, firestore
from app.schemas.report import SignedUrlResponse
import uuid

router = APIRouter()


@router.post("/upload-url", response_model=SignedUrlResponse)
async def get_report_upload_url(
    file_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    1. Generate a unique report ID
    2. Create a report entry in Firestore with status 'pending' and consultation_status 'unassigned'
    3. Generate a signed upload URL for Supabase
    """
    report_id = str(uuid.uuid4())
    file_extension = file_name.split(".")[-1]
    file_path = f"{current_user['uid']}/{report_id}.{file_extension}"

    # Create firestore entry — now includes per-report doctor fields
    report_data = {
        "id":                   report_id,
        "user_id":              current_user["uid"],
        "file_name":            file_name,
        "file_path":            file_path,
        "status":               "pending",
        # Per-report doctor assignment fields
        "consultation_status":  "unassigned",  # unassigned | assigned | in_consultation | completed
        "doctor_id":            None,
        "doctor_name":          None,
        "doctor_specialization": None,
        "assigned_at":          None,
        "created_at":           firestore.SERVER_TIMESTAMP,
    }
    db.collection("reports").document(report_id).set(report_data)

    # Generate signed URL
    try:
        res = await storage_service.get_upload_url("reports", file_path)
        print(f"DEBUG: get_upload_url result: {res}")

        if not res or not isinstance(res, dict):
            raise Exception(f"Supabase did not return a valid dictionary. Response: {res}")

        upload_url = res.get("signedURL") or res.get("signed_url") or res.get("upload_url")
        if not upload_url:
            raise Exception(f"No signed URL key found in Supabase response: {res}")

        final_file_path = res.get("file_path") or res.get("path") or file_path

    except Exception as e:
        print(f"CRITICAL: Failed to generate upload URL for report {report_id}: {str(e)}")
        db.collection("reports").document(report_id).delete()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate upload URL. Detail: {str(e)}"
        )

    return {
        "upload_url":  upload_url,
        "file_path":   final_file_path,
        "report_id":   report_id,
    }


@router.post("/{report_id}/process")
async def trigger_report_processing(
    report_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Trigger the background AI processing task once frontend confirms upload."""
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()

    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data = report_doc.to_dict()
    if report_data["user_id"] != current_user["uid"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    background_tasks.add_task(
        process_report_task,
        report_id,
        current_user["uid"],
        report_data["file_path"]
    )
    return {"message": "Processing started"}


@router.get("/")
async def get_reports(current_user: dict = Depends(get_current_user)):
    """
    Get all reports for the current user.
    Each report now includes per-report doctor assignment fields:
    doctor_id, doctor_name, doctor_specialization, consultation_status.
    Also includes doctor-review fields: reviewed, reviewed_at.
    """
    reports_ref = db.collection("reports").where("user_id", "==", current_user["uid"])
    docs = reports_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        # Normalise timestamps
        for ts_field in ("created_at", "processed_at", "assigned_at", "reviewed_at"):
            val = data.get(ts_field)
            if val and hasattr(val, "isoformat"):
                data[ts_field] = val.isoformat()
            elif val is None:
                data[ts_field] = None
        # Ensure per-report doctor fields always present
        data.setdefault("doctor_id", None)
        data.setdefault("doctor_name", None)
        data.setdefault("doctor_specialization", None)
        data.setdefault("consultation_status", "unassigned")
        # Ensure doctor-review fields always present
        data.setdefault("reviewed", False)
        data.setdefault("reviewed_at", None)
        results.append(data)

    # Sort newest first in Python (avoid composite index requirement)
    results.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return results


@router.post("/{report_id}/assign-doctor")
async def assign_doctor_to_report(
    report_id: str,
    current_user: dict = Depends(get_current_patient)
):
    """
    Assign the best-matching doctor to a specific report using the smart algorithm:
      - Specialization match against patient conditions + report AI summary
      - Availability check (working_hours / free slots)
      - Least-loaded by active report count (LLA)

    Writes doctor_id, doctor_name, consultation_status='assigned' to the report doc.
    A fresh search is done every time — no caching.
    """
    patient_uid = current_user["uid"]

    # Verify report belongs to this patient
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")
    if report_doc.to_dict().get("user_id") != patient_uid:
        raise HTTPException(status_code=403, detail="Not your report")

    from app.services.assignment_service import assignment_service
    result = await assignment_service.assign_doctor_to_report(report_id, patient_uid)

    if not result:
        raise HTTPException(
            status_code=503,
            detail="No suitable doctors available. Please try again later."
        )

    return {
        "message":        "Doctor assigned to report successfully",
        "report_id":      report_id,
        "doctor_id":      result["doctor_id"],
        "doctor_name":    result["doctor_name"],
        "specialization": result["specialization"],
        "spec_score":     result["spec_score"],
    }


@router.patch("/{report_id}/complete-consultation")
async def complete_report_consultation(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Mark a report's consultation as completed.
    Doctor or patient can call this when the consultation is done.
    Frees up the doctor for new assignments.
    """
    uid  = current_user["uid"]
    role = current_user.get("role", "")

    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    rd = report_doc.to_dict()
    # Allow the patient who owns the report OR the assigned doctor
    if rd.get("user_id") != uid and rd.get("doctor_id") != uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    if rd.get("consultation_status") == "completed":
        return {"message": "Consultation already completed", "report_id": report_id}

    from app.services.assignment_service import assignment_service
    ok = await assignment_service.complete_report_consultation(
        report_id=report_id,
        doctor_uid=rd.get("doctor_id", uid)
    )

    if not ok:
        raise HTTPException(status_code=500, detail="Failed to complete consultation")

    return {"message": "Consultation marked as completed", "report_id": report_id}


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a report document from Firestore and its file from storage."""
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()

    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data = report_doc.to_dict()
    if report_data["user_id"] != current_user["uid"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        await storage_service.delete_file("reports", report_data["file_path"])
    except Exception as e:
        print(f"Warning: Failed to delete file from storage: {e}")

    report_ref.delete()
    return {"message": "Report deleted successfully"}
