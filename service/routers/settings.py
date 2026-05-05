"""GUI configuration: API keys + run defaults."""

from __future__ import annotations

import os
from typing import Dict

from fastapi import APIRouter

from gui.config import (
    GUI_CONFIG_PATH,
    PROVIDER_KEYS,
    PROVIDER_LABELS,
    load,
    save,
)
from service.schemas import ProviderKey, SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])


def _provider_keys_view(cfg_keys: Dict[str, str]) -> list[ProviderKey]:
    out = []
    for provider, env_name in PROVIDER_KEYS.items():
        out.append(
            ProviderKey(
                provider=provider,
                env_name=env_name,
                label=PROVIDER_LABELS.get(provider, provider),
                set_in_env=bool(os.environ.get(env_name)),
                set_in_config=bool(cfg_keys.get(env_name)),
            )
        )
    return out


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    cfg = load()
    return SettingsResponse(
        api_keys=_provider_keys_view(cfg.get("api_keys", {})),
        defaults=cfg.get("defaults", {}),
        config_path=str(GUI_CONFIG_PATH),
    )


@router.put("", response_model=SettingsResponse)
def update_settings(req: SettingsUpdateRequest) -> SettingsResponse:
    cfg = load()
    if req.api_keys is not None:
        cfg.setdefault("api_keys", {})
        for env_name, value in req.api_keys.items():
            if value:
                cfg["api_keys"][env_name] = value
            elif env_name in cfg["api_keys"]:
                del cfg["api_keys"][env_name]
    if req.defaults is not None:
        cfg.setdefault("defaults", {}).update(req.defaults)
    save(cfg)
    return SettingsResponse(
        api_keys=_provider_keys_view(cfg.get("api_keys", {})),
        defaults=cfg.get("defaults", {}),
        config_path=str(GUI_CONFIG_PATH),
    )
