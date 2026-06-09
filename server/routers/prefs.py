"""Per-user preferences (daily schedule, watchlist, defaults)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import user_prefs
from ..deps import require_auth

router = APIRouter(prefix="/api", tags=["prefs"])


@router.get("/prefs")
def get_prefs(email: str = Depends(require_auth)):
    return user_prefs.load(email)


@router.put("/prefs")
def put_prefs(body: dict, email: str = Depends(require_auth)):
    user_prefs.save(email, body)
    return user_prefs.load(email)
