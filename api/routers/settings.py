from fastapi import APIRouter
from api.models.settings import Settings
from api.services.settings_service import load_settings, save_settings

router = APIRouter()


@router.get("", response_model=Settings)
def get_settings():
    return load_settings()


@router.put("", response_model=Settings)
def update_settings(settings: Settings):
    save_settings(settings)
    return settings
