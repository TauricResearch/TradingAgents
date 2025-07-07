from typing import Annotated
from pydantic import BaseModel, Field, EmailStr
from utils.auth import Role
from datetime import datetime

class CreateUserBody(BaseModel):
    name : Annotated[str, Field(min_length=1, max_length=32)]
    email : Annotated[EmailStr, Field(max_length=32)]
    password : Annotated[str, Field(max_length=32)]
    role : Annotated[Role, Field(default=Role.USER)]

class MemberResponse(BaseModel):
    id : str 
    name : str | None = None
    email : str
    created_at : datetime
    updated_at : datetime
    role : Role
