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
