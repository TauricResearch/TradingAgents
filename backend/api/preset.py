"""Config preset CRUD — save/load named setting snapshots."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from backend.core.database import get_db
from backend.api.deps import get_current_user
from backend.models.preset import ConfigPreset
from backend.models.settings import AppSettings
from backend.schemas.preset import PresetCreate, PresetRead
from backend.api.settings import _get_or_create_settings

router = APIRouter(prefix="/api/presets", tags=["presets"])
_logger = logging.getLogger(__name__)


@router.get("", response_model=list[PresetRead])
async def list_presets(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(ConfigPreset).order_by(ConfigPreset.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=PresetRead)
async def create_preset(body: PresetCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    existing = await db.execute(select(ConfigPreset).where(ConfigPreset.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"'{body.name}' adında şablon zaten var")
    preset = ConfigPreset(name=body.name, description=body.description, settings_json=body.settings_json)
    db.add(preset)
    await db.flush()
    return preset


@router.delete("/{preset_id}")
async def delete_preset(preset_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(ConfigPreset).where(ConfigPreset.id == preset_id))
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    await db.delete(preset)
    return {"deleted": True}


@router.post("/{preset_id}/apply")
async def apply_preset(preset_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Apply a preset's settings to the global AppSettings row."""
    result = await db.execute(select(ConfigPreset).where(ConfigPreset.id == preset_id))
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")

    settings = await _get_or_create_settings(db)
    try:
        data = json.loads(preset.settings_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Şablon JSON geçersiz")

    for key, value in data.items():
        if hasattr(settings, key) and value is not None:
            if key in ("watchlist", "selected_analysts"):
                setattr(settings, key, value)
            else:
                setattr(settings, key, value)

    return {"applied": True, "preset_name": preset.name}
