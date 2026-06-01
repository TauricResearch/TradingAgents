from datetime import datetime
from pydantic import BaseModel


class LogRead(BaseModel):
    id: int
    level: str
    source: str
    message: str
    details: str | None
    created_at: datetime

    class Config:
        from_attributes = True
