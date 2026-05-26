"""HashiCorp Vault integration helpers for runtime API key management."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


_DEFAULT_VAULT_KEYS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "ZHIPU_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


class VaultError(RuntimeError):
    """Raised when Vault calls fail."""


def _is_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def vault_enabled() -> bool:
    return _is_truthy(os.getenv("VAULT_ENABLED", "false"))


def vault_config() -> dict[str, str]:
    return {
        "addr": (os.getenv("VAULT_ADDR", "") or "").rstrip("/"),
        "token": os.getenv("VAULT_TOKEN", "") or "",
        "mount": os.getenv("VAULT_KV_MOUNT", "secret") or "secret",
        "path": os.getenv("VAULT_KV_PATH", "tradingagents/api-keys") or "tradingagents/api-keys",
    }


def configured_vault_keys() -> list[str]:
    raw = os.getenv("VAULT_KEYS", "")
    if not raw.strip():
        return list(_DEFAULT_VAULT_KEYS)
    keys = []
    for part in raw.split(","):
        key = (part or "").strip().upper()
        if key and key not in keys:
            keys.append(key)
    return keys


def _kv_v2_url(addr: str, mount: str, path: str) -> str:
    quoted_mount = urllib.parse.quote(mount.strip("/"), safe="")
    quoted_path = "/".join(urllib.parse.quote(p, safe="") for p in path.strip("/").split("/"))
    return f"{addr}/v1/{quoted_mount}/data/{quoted_path}"


def fetch_vault_secret_data(timeout_seconds: int = 10) -> dict[str, Any]:
    cfg = vault_config()
    if not cfg["addr"]:
        raise VaultError("VAULT_ADDR is not configured")
    if not cfg["token"]:
        raise VaultError("VAULT_TOKEN is not configured")

    url = _kv_v2_url(cfg["addr"], cfg["mount"], cfg["path"])
    req = urllib.request.Request(url, method="GET", headers={"X-Vault-Token": cfg["token"]})

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise VaultError(f"Vault request failed: HTTP {exc.code}; body={body}") from exc
    except urllib.error.URLError as exc:
        raise VaultError(f"Vault connection failed: {exc}") from exc

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    inner = data.get("data", {}) if isinstance(data, dict) else {}
    if not isinstance(inner, dict):
        raise VaultError("Vault response did not contain KV v2 data")
    return inner


def refresh_runtime_env_from_vault(timeout_seconds: int = 10) -> dict[str, Any]:
    if not vault_enabled():
        return {
            "enabled": False,
            "updated": 0,
            "keys": [],
            "skipped": configured_vault_keys(),
            "message": "Vault integration disabled",
        }

    secret_data = fetch_vault_secret_data(timeout_seconds=timeout_seconds)
    wanted_keys = configured_vault_keys()

    updated_keys: list[str] = []
    skipped_keys: list[str] = []
    for key in wanted_keys:
        value = secret_data.get(key)
        if value is None:
            skipped_keys.append(key)
            continue
        str_value = str(value)
        os.environ[key] = str_value
        updated_keys.append(key)

    return {
        "enabled": True,
        "updated": len(updated_keys),
        "keys": updated_keys,
        "skipped": skipped_keys,
        "message": "Vault refresh completed",
    }
