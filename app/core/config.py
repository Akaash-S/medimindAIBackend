from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "MediMind AI Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Firebase
    FIREBASE_PROJECT_ID: str
    FIREBASE_PRIVATE_KEY: str
    FIREBASE_CLIENT_EMAIL: str
    
    # Firestore
    FIRESTORE_DB: str = "(default)"
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    
    # AI Provider
    AI_PROVIDER: str = "groq"  # "groq" or "internal"
    GROQ_API_KEY: Optional[str] = None
    INTERNAL_AI_URL: Optional[str] = None
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8080"]

    # Deployment
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
