from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlmodel import Session

from app.core.config import settings
from app.infrastructure.database import get_db
from app.domain.models import User
from app.infrastructure.repositories.user import UserRepository
from app.core.services.trading_analysis import TradingAnalysisService

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")

class TokenData(BaseModel):
    username: Optional[str] = None

def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)

def get_user_from_token(token: str, db: Session) -> Optional[User]:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenData(username=payload.get("sub"))
    except JWTError:
        return None
    
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(email=token_data.username)
    return user

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> User:
    user = get_user_from_token(token=token, db=db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_active_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user

def get_analysis_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user)
) -> TradingAnalysisService:
    return TradingAnalysisService(user=user, db=db)
