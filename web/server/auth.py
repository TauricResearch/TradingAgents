from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, status
from itsdangerous import URLSafeTimedSerializer

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = int(timedelta(days=30).total_seconds())

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_serializer: URLSafeTimedSerializer | None = None
_allowed_emails: list[str] = []


def is_auth_disabled() -> bool:
    import os
    val = os.environ.get("AUTH_DISABLED", "")
    print(f"[DEBUG] AUTH_DISABLED={val!r}")
    return val.lower() in ("true", "1", "yes")


def _get_serializer() -> URLSafeTimedSerializer | None:
    global _serializer
    if _serializer is None:
        secret = os.environ.get("AUTH_SECRET", "")
        if not secret:
            if is_auth_disabled():
                return None
            raise RuntimeError("AUTH_SECRET environment variable is required")
        _serializer = URLSafeTimedSerializer(secret, salt="session")
    return _serializer


def get_allowed_emails() -> list[str]:
    global _allowed_emails
    if not _allowed_emails:
        raw = os.environ.get("ALLOWED_EMAILS", "")
        _allowed_emails = [e.strip() for e in raw.split(",") if e.strip()]
    return _allowed_emails


def make_session_cookie(email: str, name: str = "", picture: str = "") -> str:
    data = {"email": email, "name": name, "picture": picture}
    serializer = _get_serializer()
    if serializer is None:
        return ""
    return serializer.dumps(data)


def read_session(request: Request) -> dict | None:
    if is_auth_disabled():
        return {"email": "dev@local.dev", "name": "Dev User", "picture": ""}
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    serializer = _get_serializer()
    if serializer is None:
        return None
    try:
        data = serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        if isinstance(data, dict) and "email" in data:
            return data
    except Exception:
        pass
    return None


def read_session_from_ws(websocket: WebSocket) -> dict | None:
    if is_auth_disabled():
        return {"email": "dev@local.dev", "name": "Dev User", "picture": ""}
    cookie = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None
    serializer = _get_serializer()
    if serializer is None:
        return None
    try:
        data = serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        if isinstance(data, dict) and "email" in data:
            return data
    except Exception:
        pass
    return None


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    if is_auth_disabled():
        return {"auth_url": "", "disabled": True}

    redirect_uri = os.environ.get(
        "OAUTH_REDIRECT_URI",
        str(request.base_url).rstrip("/") + "/api/auth/callback",
    )
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/callback")
async def callback(code: str, request: Request):
    redirect_uri = os.environ.get(
        "OAUTH_REDIRECT_URI",
        str(request.base_url).rstrip("/") + "/api/auth/callback",
    )
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="OAuth not configured")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        if "access_token" not in token_data:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        access_token = token_data["access_token"]
        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo = user_resp.json()

    email = userinfo.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="No email from Google")

    allowed = get_allowed_emails()
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    response = Response(status_code=302)
    response.headers["Location"] = "/"
    cookie_value = make_session_cookie(
        email=email,
        name=userinfo.get("name", ""),
        picture=userinfo.get("picture", ""),
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return response


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, httponly=True, samesite="lax", secure=True)
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    if is_auth_disabled():
        return {"email": "dev@local.dev", "name": "Dev User", "picture": ""}
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session
