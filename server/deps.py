"""Shared FastAPI dependencies — auth gate reusing auth.py's pure functions."""
from __future__ import annotations

from fastapi import Cookie, HTTPException
from typing import Optional

import auth as _auth
from .config import settings


def require_auth(ta_session: Optional[str] = Cookie(default=None)) -> str:
    """Return the authed email from the session cookie, or 401.

    Reuses auth.verify_token unchanged, so whitelist-shrink revocation still
    invalidates live sessions.
    """
    email = _auth.verify_token(ta_session) if ta_session else None
    if not email:
        raise HTTPException(status_code=401, detail="not authenticated")
    return email


__all__ = ["require_auth", "settings"]
