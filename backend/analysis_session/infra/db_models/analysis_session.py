from datetime import datetime,date
from sqlmodel import SQLModel, Field, JSON
import uuid
import enum
from sqlalchemy import Column
from sqlalchemy.dialects import oracle
from utils.auth import Role
import uuid

class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisSession(SQLModel, table=True):
    __tablename__ = "analysis_sessions"
    id: str = Field(default=None, max_length=36, primary_key=True)
    member_id: str = Field(foreign_key="members.id")
    ticker: str
    analysis_date: date
    analysts_selected: list[str] = Field(sa_column=Column(JSON))
    research_depth: int
    llm_provider: str
    backend_url: str
    shallow_thinker: str
    deep_thinker: str
    status: AnalysisStatus = Field(default=AnalysisStatus.PENDING)
    final_report: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None
    created_at : datetime = Field(nullable=False)
    updated_at : datetime = Field(nullable=False)