from datetime import datetime
from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    condition: str = Field(..., pattern="^(above|below)$")
    target_price: float = Field(..., gt=0)
    auto_analyze: bool = False


class AlertUpdate(BaseModel):
    enabled: bool | None = None
    target_price: float | None = Field(default=None, gt=0)
    auto_analyze: bool | None = None


class AlertRead(BaseModel):
    id: int
    ticker: str
    condition: str
    target_price: float
    auto_analyze: bool
    enabled: bool
    triggered_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
