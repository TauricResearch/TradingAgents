"""
Google OAuth authentication routes
"""
import os
import logging
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.db import get_db, User, UserSettings
from backend.app.services.auth_utils import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Google OAuth Configuration - read at request time for dynamic updates
def get_google_client_id():
    return os.getenv("GOOGLE_CLIENT_ID", "")

def get_google_client_secret():
    return os.getenv("GOOGLE_CLIENT_SECRET", "")

def get_frontend_url():
    url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    logger.info(f"FRONTEND_URL resolved to: {url}")
    return url

# Google OAuth URLs
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.get("/google/login")
async def google_login():
    """
    Redirect to Google OAuth login page
    """
    client_id = get_google_client_id()
    frontend_url = get_frontend_url()
    
    if not client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    # Build the authorization URL
    redirect_uri = f"{frontend_url}/api/auth/callback/google"
    
    # For backend-handled callback (alternative):
    # redirect_uri = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/api/auth/google/callback"
    
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{GOOGLE_AUTH_URL}?{query_string}"
    
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Google OAuth callback (backend-handled flow)
    Exchange authorization code for tokens and create/update user
    """
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    frontend_url = get_frontend_url()
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    # Determine redirect URI (must match what was used in the login request)
    redirect_uri = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/api/auth/google/callback"
    
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=400, 
                detail=f"Failed to exchange code: {token_response.text}"
            )
        
        tokens = token_response.json()
        access_token = tokens.get("access_token")
        
        # Get user info from Google
        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if userinfo_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")
        
        userinfo = userinfo_response.json()
    
    # Find or create user
    google_id = userinfo["id"]
    email = userinfo["email"]
    name = userinfo.get("name")
    avatar_url = userinfo.get("picture")
    
    # Check if user exists
    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Update existing user
        user.last_login_at = datetime.utcnow()
        user.name = name
        user.avatar_url = avatar_url
    else:
        # Create new user
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            last_login_at=datetime.utcnow()
        )
        db.add(user)
    
    await db.commit()
    await db.refresh(user)
    
    # Create JWT token
    jwt_token = create_access_token({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
    })
    
    # Redirect to frontend with token
    redirect_url = f"{frontend_url}/auth/callback?token={jwt_token}"
    return RedirectResponse(url=redirect_url)

from pydantic import BaseModel

class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str

@router.post("/google/token")
async def exchange_google_token(
    request: TokenExchangeRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Exchange Google authorization code for JWT token (frontend-handled flow)
    This is called by the frontend after receiving the code from Google
    """
    client_id = get_google_client_id()
    client_secret = get_google_client_secret()
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": request.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": request.redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        
        if token_response.status_code != 200:
            error_detail = token_response.json() if token_response.headers.get("content-type", "").startswith("application/json") else token_response.text
            raise HTTPException(
                status_code=400, 
                detail=f"Failed to exchange code: {error_detail}"
            )
        
        tokens = token_response.json()
        access_token = tokens.get("access_token")
        
        # Get user info from Google
        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if userinfo_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")
        
        userinfo = userinfo_response.json()
    
    # Find or create user
    google_id = userinfo["id"]
    email = userinfo["email"]
    name = userinfo.get("name")
    avatar_url = userinfo.get("picture")
    
    # Check if user exists
    result = await db.execute(
        select(User).where(User.google_id == google_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Update existing user
        user.last_login_at = datetime.utcnow()
        user.name = name
        user.avatar_url = avatar_url
    else:
        # Create new user
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            last_login_at=datetime.utcnow()
        )
        db.add(user)
    
    await db.commit()
    await db.refresh(user)
    
    # Create JWT token
    jwt_token = create_access_token({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
    })
    
    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
        }
    }


@router.get("/me")
async def get_current_user(
    authorization: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user info from JWT token
    Returns None if not authenticated (optional auth)
    """
    from backend.app.services.auth_utils import verify_access_token
    
    if not authorization or not authorization.startswith("Bearer "):
        return {"user": None}
    
    token = authorization.replace("Bearer ", "")
    payload = verify_access_token(token)
    
    if not payload:
        return {"user": None}
    
    return {
        "user": {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "avatar_url": payload.get("avatar_url"),
        }
    }
