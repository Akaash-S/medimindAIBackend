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
    created_at: datetime
    processed_at: Optional[datetime] = None
    analysis: Optional[Dict[str, Any]] = None
    risk_level: Optional[str] = None
    summary: Optional[str] = None

class SignedUrlResponse(BaseModel):
    upload_url: str
    file_path: str
    report_id: str
