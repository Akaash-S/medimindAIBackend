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
        email = decoded_token.get("email")
        
        # Check if this UID already has a document
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            return user_doc.to_dict()
        
        # UID doesn't exist — check if there's an existing doc with the same email
        # (handles Google sign-in after email/password sign-up or vice versa)
        if email:
            existing_query = db.collection("users").where("email", "==", email).limit(1).stream()
            existing_docs = list(existing_query)
            
            if existing_docs:
                # Found an existing user with the same email but different UID
                old_doc = existing_docs[0]
                old_data = old_doc.to_dict()
                old_uid = old_doc.id
                
                # Migrate: copy old data to new UID doc, update the uid field
                migrated_data = {**old_data, "uid": uid}
                user_ref.set(migrated_data)
                
                # Delete the old orphaned document
                db.collection("users").document(old_uid).delete()
                
                return migrated_data
        
        # Completely new user — create a fresh profile
        user_data = {
            "uid": uid,
            "email": email,
            "role": None,
            "profile_complete": False,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        user_ref.set(user_data)
        return user_data
        
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
