"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spektiv.api.database import get_db
from spektiv.api.models import User
from spektiv.api.schemas.auth import LoginRequest, TokenResponse
from spektiv.api.services.auth_service import verify_password, create_access_token


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Authenticate user and return JWT token.

    Args:
        credentials: Username and password
        db: Database session

    Returns:
        TokenResponse: JWT access token

    Raises:
        HTTPException: If credentials are invalid
    """
    # Get user by username
    result = await db.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()

    # Verify user exists and password is correct
    if user is None or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    # Create JWT token
    access_token = create_access_token(data={"sub": user.username})

    return TokenResponse(access_token=access_token, token_type="bearer")
