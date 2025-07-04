from datetime import datetime, timedelta
from fastapi import HTTPException, status, Depends
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
from dotenv import load_dotenv
from enum import StrEnum
from pydantic import BaseModel
from typing import Annotated

from config import get_settings

settings = get_settings()

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

class Role(StrEnum):
    ADMIN = "ADMIN"
    USER = "USER"

class CurrentMember(BaseModel):
    id : str
    role : Role

    def __str__(self):
        return f"{self.id}({self.role})"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/members/login")



def create_access_token(
        payload: dict,
        role: Role,
        expires_delta: timedelta = timedelta(hours=6)
):
    expire = datetime.utcnow() + expires_delta
    payload.update({"exp": expire, "role": role})
    encoded_jwt = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt

def decode_access_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    

# ✅ 수정된 부분: Annotated 올바른 사용법
def get_current_member(token: Annotated[str, Depends(oauth2_scheme)]):
    payload = decode_access_token(token)
    member_id = payload.get("member_id")
    role = payload.get("role")
    if not member_id or not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    
    return CurrentMember(id=member_id, role=Role(role))

def get_admin_member(token: Annotated[str, Depends(oauth2_scheme)]):
    payload = decode_access_token(token)
    member_id = payload.get("member_id")
    role = payload.get("role")
    
    if not role or role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    
    return CurrentMember(id=member_id, role=Role(role))