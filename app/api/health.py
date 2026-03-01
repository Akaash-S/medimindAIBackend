from fastapi import APIRouter
from app.core.firebase import db
import time

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Check API and basic Firestore connectivity.
    """
    start_time = time.time()
    try:
        # Simple Firestore check
        db.collection("health").document("check").set({"last_check": str(start_time)})
        db_status = "online"
    except Exception:
        db_status = "offline"
        
    return {
        "status": "healthy",
        "database": db_status,
        "latency_ms": round((time.time() - start_time) * 1000, 2)
    }


@router.get("/stats")
async def get_platform_stats():
    """
    Public endpoint — no auth required.
    Returns aggregate counts from Firestore for the landing page stats bar.
    """
    try:
        # Count patients
        patient_docs = list(
            db.collection("users").where("role", "==", "patient").stream()
        )
        total_patients = len(patient_docs)

        # Count doctors
        doctor_docs = list(
            db.collection("users").where("role", "==", "doctor").stream()
        )
        total_doctors = len(doctor_docs)

        # Count all reports & compute avg processing time
        report_docs = list(db.collection("reports").stream())
        total_reports = len(report_docs)

        processing_times = []
        for rdoc in report_docs:
            rd = rdoc.to_dict()
            pt = rd.get("processing_time_ms")
            if pt and isinstance(pt, (int, float)) and pt > 0:
                processing_times.append(pt)

        avg_analysis_ms = (
            round(sum(processing_times) / len(processing_times))
            if processing_times
            else 0
        )

        return {
            "total_patients": total_patients,
            "total_doctors": total_doctors,
            "total_reports": total_reports,
            "avg_analysis_ms": avg_analysis_ms,
        }
    except Exception as e:
        # Return zeros rather than 500 — landing page should never break
        return {
            "total_patients": 0,
            "total_doctors": 0,
            "total_reports": 0,
            "avg_analysis_ms": 0,
            "error": str(e),
        }

