from fastapi import APIRouter, Depends
from app.core.firebase import db
from app.core.security import get_current_user

router = APIRouter()

@router.get("/")
async def get_my_prescriptions(current_user: dict = Depends(get_current_user)):
    """Fetch all prescriptions for the currently authenticated patient."""
    uid = current_user["uid"]
    
    docs = (
        db.collection("prescriptions")
        .where("patient_uid", "==", uid)
        .stream()
    )
    
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        
        # Handle timestamp
        if "created_at" in data and hasattr(data["created_at"], "isoformat"):
            data["created_at"] = data["created_at"].isoformat()
            
        # Standardize naming for Patient interface
        # The frontend expects medication_name, so we map medicine -> medication_name
        data["medication_name"] = data.get("medicine", "Unknown")
        
        # Default status if not set
        if "status" not in data:
            data["status"] = "active"
            
        results.append(data)
        
    # Sort descending by creation date if available
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results
