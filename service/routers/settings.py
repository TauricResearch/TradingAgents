"""GUI configuration: API keys + run defaults + Ollama model discovery."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests
from fastapi import APIRouter, HTTPException

from gui.config import (
    GUI_CONFIG_PATH,
    PROVIDER_KEYS,
    PROVIDER_LABELS,
    load,
    save,
)
from service.schemas import ProviderKey, SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])


def _ollama_api_base(url: str) -> str:
    """Strip a trailing ``/v1`` if present so we can hit ``/api/tags`` cleanly."""
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _detect_ollama_models(url: str, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Hit ``<url>/api/tags`` and return the list of installed models.

    Raises ``HTTPException`` on connection or HTTP errors with a message
    the UI can render.
    """
    base = _ollama_api_base(url)
    try:
        resp = requests.get(f"{base}/api/tags", timeout=timeout)
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"could not reach Ollama at {base}: {e}",
        )
    if not resp.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama returned {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Ollama returned non-JSON; is the URL pointing at Ollama?",
        )
    out: List[Dict[str, Any]] = []
    for m in (data.get("models") or []):
        out.append({
            "name": m.get("name") or m.get("model") or "",
            "size": m.get("size"),
            "modified_at": m.get("modified_at"),
            "parameter_size": (m.get("details") or {}).get("parameter_size"),
            "family": (m.get("details") or {}).get("family"),
        })
    return out


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


@router.get("/ollama/models")
def ollama_models(url: str | None = None) -> Dict[str, Any]:
    """List the models installed on the configured (or supplied) Ollama instance.

    If ``url`` is provided, test that URL — otherwise read ``defaults.ollama_base_url``
    from the saved config.
    """
    cfg = load()
    target = url or (cfg.get("defaults", {}) or {}).get("ollama_base_url") or ""
    if not target:
        raise HTTPException(
            status_code=400,
            detail="no Ollama URL configured. Set ollama_base_url in Settings or pass ?url=...",
        )
    models = _detect_ollama_models(target)
    return {"url": target, "models": models, "count": len(models)}


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
