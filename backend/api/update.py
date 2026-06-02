"""In-app self-update endpoints: check for new commits and apply them."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend.models.user import User
from backend.api.deps import get_current_user
from backend.services import update_service

router = APIRouter(prefix="/api/update", tags=["update"])


@router.get("/status")
async def update_status(_: User = Depends(get_current_user)):
    """Whether a newer commit exists upstream + current update state."""
    return await asyncio.to_thread(update_service.get_status)


@router.post("/apply")
async def update_apply(_: User = Depends(get_current_user)):
    """Trigger an in-place update + service restart (runs out-of-process)."""
    try:
        return await asyncio.to_thread(update_service.request_update)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
