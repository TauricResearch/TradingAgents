"""OTP email login → HttpOnly session cookie. Reuses auth.py pure functions."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response

import auth as _auth
from ..config import settings
from ..deps import require_auth
from ..schemas import Me, OkMessage, OtpRequest, OtpVerify

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/request-otp", response_model=OkMessage)
def request_otp(body: OtpRequest):
    ok, message = _auth.send_otp(body.email)
    if not ok:
        raise HTTPException(status_code=403, detail=message)
    return OkMessage(ok=True, message=message)


@router.post("/verify-otp", response_model=Me)
def verify_otp(body: OtpVerify, response: Response):
    if not _auth.verify_otp(body.email, body.code):
        raise HTTPException(status_code=400, detail="invalid or expired code")
    email = body.email.strip().lower()
    token = _auth.issue_token(email)
    ttl_days = int(os.getenv("SESSION_TTL_DAYS", "7"))
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return Me(email=email)


@router.get("/me", response_model=Me)
def me(email: str = Depends(require_auth)):
    return Me(email=email)


@router.post("/logout", response_model=OkMessage)
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/")
    return OkMessage(ok=True)
