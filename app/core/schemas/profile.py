from pydantic import BaseModel
from typing import Optional

class ProfileBase(BaseModel):
    default_ticker: str = "SPY"
    preferred_research_depth: int = 3
    preferred_shallow_thinker: str = "gpt-4o-mini"
    preferred_deep_thinker: str = "gpt-4o"

class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(ProfileBase):
    openai_api_key: Optional[str] = None

class Profile(ProfileBase):
    has_openai_api_key: bool

    class Config:
        orm_mode = True
