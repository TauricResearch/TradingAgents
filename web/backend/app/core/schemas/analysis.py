from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from app.domain.models import AnalysisStatus

class AnalysisSessionBase(BaseModel):
    ticker: str
    analysts_selected: List[str]
    research_depth: int
    llm_provider: str
    backend_url: str
    shallow_thinker: str
    deep_thinker: str

class AnalysisSessionCreate(AnalysisSessionBase):
    pass

class AnalysisSessionUpdate(BaseModel):
    status: Optional[AnalysisStatus] = None
    final_report: Optional[str] = None
    error_message: Optional[str] = None

class AnalysisSessionInDBBase(AnalysisSessionBase):
    id: int
    user_id: int
    analysis_date: date
    status: AnalysisStatus
    final_report: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class AnalysisSession(AnalysisSessionInDBBase):
    pass