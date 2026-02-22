import asyncio
from app.core.firebase import db
from app.services.storage_service import storage_service
from app.ai.factory import get_ai_provider
from app.core.firebase import firestore

async def process_report_task(report_id: str, user_id: str, file_path: str):
    """
    Background task to process a report:
    1. Download from Storage
    2. Extract Text (OCR Simulator for now)
    3. Analyze with AI
    4. Update Firestore
    """
    try:
        # Update status to processing
        report_ref = db.collection("reports").document(report_id)
        report_ref.update({"status": "processing"})

        # 1. Download file content (Simulated)
        # file_data = await storage_service.download_file("reports", file_path)
        
        # 2. Extract Text (OCR) 
        # For MVP, we'll simulate extraction. In prod, we'd use Tesseract or Cloud Vision
        extracted_text = "Patient feels dizzy and has high frequency of headaches. Glucose levels are 105 mg/dL. LDL is 145 mg/dL."
        
        # 3. Analyze with AI
        ai_provider = get_ai_provider()
        analysis_result = await ai_provider.analyze_report({"text": extracted_text})
        
        # 4. Update Firestore with final results
        report_ref.update({
            "status": "completed",
            "content": extracted_text,
            "analysis": analysis_result,
            "processed_at": firestore.SERVER_TIMESTAMP,
            "risk_level": analysis_result.get("risk_level", "Unknown"),
            "summary": analysis_result.get("summary", "")
        })
        
    except Exception as e:
        print(f"Error processing report {report_id}: {e}")
        db.collection("reports").document(report_id).update({
            "status": "error",
            "error_detail": str(e)
        })
