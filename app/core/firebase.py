import firebase_admin
from firebase_admin import credentials, firestore, auth
from app.core.config import settings
import json

def initialize_firebase():
    cert_dict = {
        "type": "service_account",
        "project_id": settings.FIREBASE_PROJECT_ID,
        "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
        "client_email": settings.FIREBASE_CLIENT_EMAIL,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    
    cred = credentials.Certificate(cert_dict)
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    return firestore.client()

db = initialize_firebase()
