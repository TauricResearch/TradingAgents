"""
Shared dependencies for API routes
"""
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Header
from backend.app.services.trading_service import TradingService, trading_service
from backend.app.services.auth_utils import verify_access_token


def get_trading_service() -> TradingService:
    """Dependency to get trading service instance"""
    return trading_service


async def get_current_user_optional(
    authorization: Optional[str] = Header(None)
) -> Optional[Dict[str, Any]]:
    """
    Get current user from JWT token (optional - returns None if not authenticated)
    
    Use this for endpoints that work both with and without authentication.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    payload = verify_access_token(token)
    
    if not payload:
        return None
    
    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "avatar_url": payload.get("avatar_url"),
    }


async def get_current_user_required(
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Get current user from JWT token (required - raises 401 if not authenticated)
    
    Use this for endpoints that require authentication.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please login to use this feature.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.replace("Bearer ", "")
    payload = verify_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "avatar_url": payload.get("avatar_url"),
    }
