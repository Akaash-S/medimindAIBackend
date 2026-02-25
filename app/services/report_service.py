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

        # 1. Download file content
        file_bytes = await storage_service.download_file("reports", file_path)
        
        # 2. Extract Text (OCR) 
        from app.services.ocr_service import ocr_service
        # Use file_path basename as file_name for extension check
        file_name = file_path.split("/")[-1]
        extracted_text = ocr_service.extract_text(file_bytes, file_name)
        
        if not extracted_text:
            # Fallback if extraction failed but file exists
            extracted_text = "Medical report content could not be cleanly extracted. Please review the original file."
        
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
            "summary": analysis_result.get("summary", ""),
            "health_score": analysis_result.get("health_score", 0)
        })

        # 5. Auto-generate consultation recommendation if risk is elevated
        try:
            from app.api.consultations import auto_recommend_from_report
            auto_recommend_from_report(report_id, user_id, analysis_result)
        except Exception as rec_err:
            print(f"Recommendation generation failed (non-critical): {rec_err}")
        
    except Exception as e:
        print(f"Error processing report {report_id}: {e}")
        db.collection("reports").document(report_id).update({
            "status": "error",
            "error_detail": str(e)
        })
