from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List, Dict, Any
import json
from datetime import datetime

from ..models.schemas import ConfigPreset

router = APIRouter(prefix="/api/config", tags=["config"])

# Store configs in a simple JSON file (could use a database in production)
CONFIG_FILE = Path("backend/config_presets.json")


def load_presets() -> List[Dict[str, Any]]:
    """Load configuration presets from file."""
    if not CONFIG_FILE.exists():
        return []
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_presets(presets: List[Dict[str, Any]]):
    """Save configuration presets to file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(presets, f, indent=2)


@router.get("/presets", response_model=List[ConfigPreset])
async def list_config_presets():
    """List all saved configuration presets."""
    presets = load_presets()
    return [ConfigPreset(**preset) for preset in presets]


@router.post("/save", response_model=ConfigPreset)
async def save_config_preset(preset: ConfigPreset):
    """Save a configuration preset."""
    presets = load_presets()
    
    # Check if preset with same name exists
    for i, existing in enumerate(presets):
        if existing["name"] == preset.name:
            presets[i] = preset.model_dump()
            save_presets(presets)
            return preset
    
    # Add new preset
    presets.append(preset.model_dump())
    save_presets(presets)
    return preset


@router.delete("/presets/{name}")
async def delete_config_preset(name: str):
    """Delete a configuration preset."""
    presets = load_presets()
    original_count = len(presets)
    presets = [p for p in presets if p["name"] != name]
    
    if len(presets) == original_count:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    save_presets(presets)
    return {"message": "Preset deleted"}

