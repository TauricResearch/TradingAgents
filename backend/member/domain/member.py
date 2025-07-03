from pydantic import BaseModel
from utils.auth import Role
from datetime import datetime

class Member(BaseModel):
    id: str | None = None
    name: str
    email: str
    password: str
    role: Role
    created_at: datetime
    updated_at: datetime