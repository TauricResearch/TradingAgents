import json
import os
from pathlib import Path
from api.models.settings import Settings

SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", "api/settings.json"))


def load_settings() -> Settings:
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text())
        return Settings(**data)
    return Settings()


def save_settings(settings: Settings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(settings.model_dump_json(indent=2))
