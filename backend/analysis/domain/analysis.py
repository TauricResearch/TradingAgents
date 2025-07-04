from pydantic import BaseModel
from datetime import datetime

class Analysis(BaseModel):
    id: str | None = None
    member_id: str
    ticker: str
    status: str
    created_at: datetime
    updated_at: datetime
    # 여기에 더 많은 필드들이 추가될 수 있습니다.