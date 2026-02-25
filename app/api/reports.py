from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from app.core.security import get_current_user
from app.services.storage_service import storage_service
from app.services.report_service import process_report_task
from app.core.firebase import db, firestore
from app.schemas.report import ReportResponse, SignedUrlResponse
import uuid

router = APIRouter()

@router.post("/upload-url", response_model=SignedUrlResponse)
async def get_report_upload_url(
    file_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    1. Generate a unique report ID
    2. Create a report entry in Firestore with status 'pending'
    3. Generate a signed upload URL for Supabase
    """
    report_id = str(uuid.uuid4())
    file_extension = file_name.split(".")[-1]
    file_path = f"{current_user['uid']}/{report_id}.{file_extension}"
    
    # Create firestore entry
    report_data = {
        "id": report_id,
        "user_id": current_user["uid"],
        "file_name": file_name,
        "file_path": file_path,
        "status": "pending",
        "created_at": firestore.SERVER_TIMESTAMP
    }
    db.collection("reports").document(report_id).set(report_data)
    
    # Generate signed URL
    try:
        res = await storage_service.get_upload_url("reports", file_path)
        
        # Log the result for debugging
        print(f"DEBUG: get_upload_url result: {res}")
        
        if not res or not isinstance(res, dict):
            error_msg = f"Supabase did not return a valid dictionary. Response: {res}"
            print(f"CRITICAL: {error_msg}")
            raise Exception(error_msg)
            
        # Try both camelCase and snake_case
        upload_url = res.get("signedURL") or res.get("signed_url")
        
        if not upload_url:
            error_msg = f"No 'signedURL' or 'signed_url' found in Supabase response: {res}"
            print(f"CRITICAL: {error_msg}")
            raise Exception(error_msg)
            
        final_file_path = res.get("file_path") or file_path
    except Exception as e:
        print(f"CRITICAL: Failed to generate upload URL for report {report_id}: {str(e)}")
        # Delete the pending doc since we can't upload
        db.collection("reports").document(report_id).delete()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to generate upload URL. Please ensure your Supabase storage is configured and the 'reports' bucket is public/accessible. Detail: {str(e)}"
        )
    
    return {
        "upload_url": upload_url,
        "file_path": final_file_path,
        "report_id": report_id
    }

@router.post("/{report_id}/process")
async def trigger_report_processing(
    report_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger the background AI processing task once frontend confirms upload.
    """
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

@router.get("/", response_model=list[ReportResponse])
async def get_reports(current_user: dict = Depends(get_current_user)):
    reports_ref = db.collection("reports").where("user_id", "==", current_user["uid"])
    docs = reports_ref.stream()
    
    results = []
    for doc in docs:
        data = doc.to_dict()
        # Convert timestamp to datetime for pydantic
        if "created_at" in data and data["created_at"]:
             data["created_at"] = data["created_at"]
        results.append(data)
        
    return results

@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a report document from Firestore and its file from storage.
    """
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")
    
    report_data = report_doc.to_dict()
    if report_data["user_id"] != current_user["uid"]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Delete from storage
    try:
        await storage_service.delete_file("reports", report_data["file_path"])
    except Exception as e:
        print(f"Warning: Failed to delete file from storage: {e}")
        # We continue to delete from Firestore even if storage delete fails
        
    # Delete from Firestore
    report_ref.delete()
    
    return {"message": "Report deleted successfully"}
