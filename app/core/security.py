from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth, firestore
from app.core.config import settings
from app.core.firebase import db

security = HTTPBearer()

async def get_current_user(res: HTTPAuthorizationCredentials = Depends(security)):
    token = res.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token["uid"]
        
        # Fetch user from Firestore or create if doesn't exist
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            # Create a base user profile without a role
            user_data = {
                "uid": uid,
                "email": decoded_token.get("email"),
                "role": None,  # Explicitly None until selection
                "profile_complete": False,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(user_data)
            return user_data
            
        return user_doc.to_dict()
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_doctor(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges"
        )
    return current_user

async def get_current_patient(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges"
        )
    return current_user
