from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class AnalysisResult(BaseModel):
    summary: str
    risk_level: str
    recommendations: List[str]

class ReportBase(BaseModel):
    file_name: str
    file_path: str

class ReportCreate(ReportBase):
    pass

class ReportResponse(ReportBase):
    id: str
    user_id: str
    status: str
    # Both timestamps are Optional — Firestore SERVER_TIMESTAMP resolves
    # asynchronously and may be None on freshly written documents.
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    analysis: Optional[Dict[str, Any]] = None
    risk_level: Optional[str] = None
    summary: Optional[str] = None

    model_config = {"extra": "ignore"}   # silently ignore extra Firestore fields

class SignedUrlResponse(BaseModel):
    upload_url: str
    file_path: str
    report_id: str
