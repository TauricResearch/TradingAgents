from __future__ import annotations

import json
from unittest.mock import patch

from api.vault import configured_vault_keys, refresh_runtime_env_from_vault


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_configured_vault_keys_deduplicates_and_normalizes(monkeypatch):
    monkeypatch.setenv("VAULT_KEYS", "google_api_key, OPENROUTER_API_KEY, google_api_key")
    assert configured_vault_keys() == ["GOOGLE_API_KEY", "OPENROUTER_API_KEY"]


def test_refresh_runtime_env_from_vault_disabled(monkeypatch):
    monkeypatch.setenv("VAULT_ENABLED", "false")
    summary = refresh_runtime_env_from_vault()
    assert summary["enabled"] is False
    assert summary["updated"] == 0


def test_refresh_runtime_env_from_vault_updates_env(monkeypatch):
    monkeypatch.setenv("VAULT_ENABLED", "true")
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "root")
    monkeypatch.setenv("VAULT_KV_MOUNT", "secret")
    monkeypatch.setenv("VAULT_KV_PATH", "tradingagents/api-keys")
    monkeypatch.setenv("VAULT_KEYS", "GOOGLE_API_KEY,OPENROUTER_API_KEY")

    payload = {
        "data": {
            "data": {
                "GOOGLE_API_KEY": "google-xyz",
                "OPENROUTER_API_KEY": "openrouter-xyz",
            }
        }
    }
    with patch("urllib.request.urlopen", return_value=_DummyResponse(payload)):
        summary = refresh_runtime_env_from_vault()

    assert summary["enabled"] is True
    assert summary["updated"] == 2
    assert "GOOGLE_API_KEY" in summary["keys"]
    assert "OPENROUTER_API_KEY" in summary["keys"]
