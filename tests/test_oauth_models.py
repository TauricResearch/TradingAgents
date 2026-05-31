"""Test della scoperta dei modelli disponibili (endpoint + probe + cache)."""
import time

import pytest

from tradingagents.llm_clients.oauth import models as models_mod
from tradingagents.llm_clients.oauth.models import (
    ModelAvailabilityCache,
    available_models,
    discover_available_models,
    fetch_models_endpoint,
)
from tradingagents.llm_clients.oauth.store import StoredTokens


def _tokens(account_id="acct_1", exp_offset=3600):
    return StoredTokens("ACCESS", "R", "I", time.time() + exp_offset, account_id)


# --- fetch endpoint --------------------------------------------------------
def test_fetch_endpoint_parses_models_list(monkeypatch):
    class Resp:
        status_code = 200
        def json(self):
            return {"models": [{"id": "gpt-5.5"}, {"slug": "gpt-5.4"}, "gpt-5.2"]}
    monkeypatch.setattr(models_mod.httpx, "get", lambda *a, **k: Resp())
    assert fetch_models_endpoint(_tokens()) == ["gpt-5.5", "gpt-5.4", "gpt-5.2"]


def test_fetch_endpoint_empty_on_error(monkeypatch):
    class Resp:
        status_code = 400
        def json(self):
            return {}
    monkeypatch.setattr(models_mod.httpx, "get", lambda *a, **k: Resp())
    assert fetch_models_endpoint(_tokens()) == []


# --- discover: endpoint preferito ------------------------------------------
def test_discover_uses_endpoint_when_non_empty(monkeypatch):
    monkeypatch.setattr(models_mod, "fetch_models_endpoint", lambda t, **k: ["gpt-5.5", "gpt-5.4"])
    # se l'endpoint risponde, NON deve sondare
    monkeypatch.setattr(models_mod, "probe_model", lambda *a, **k: pytest.fail("non deve sondare"))
    out = discover_available_models(_tokens(), ["gpt-5.4-mini", "gpt-5.5", "gpt-5.4"])
    # i candidati noti per primi, nell'ordine dell'endpoint
    assert out == ["gpt-5.5", "gpt-5.4"]


# --- discover: fallback a probe quando endpoint vuoto ----------------------
def test_discover_probes_when_endpoint_empty(monkeypatch):
    monkeypatch.setattr(models_mod, "fetch_models_endpoint", lambda t, **k: [])
    ok = {"gpt-5.4-mini", "gpt-5.5"}
    monkeypatch.setattr(models_mod, "probe_model", lambda t, m, **k: m in ok)
    out = discover_available_models(_tokens(), ["gpt-5.4-mini", "gpt-5.5", "gpt-5.4", "gpt-5.2"])
    assert out == ["gpt-5.4-mini", "gpt-5.5"]


def test_discover_dedupes_and_skips_custom(monkeypatch):
    monkeypatch.setattr(models_mod, "fetch_models_endpoint", lambda t, **k: [])
    monkeypatch.setattr(models_mod, "probe_model", lambda t, m, **k: True)
    out = discover_available_models(_tokens(), ["gpt-5.4-mini", "gpt-5.4-mini", "custom"])
    assert out == ["gpt-5.4-mini"]


# --- cache ----------------------------------------------------------------
def test_cache_roundtrip_and_ttl(tmp_path):
    c = ModelAvailabilityCache(path=tmp_path / "m.json")
    assert c.get("acct") is None
    c.set("acct", ["gpt-5.4-mini"])
    assert c.get("acct") == ["gpt-5.4-mini"]
    # account diverso -> miss
    assert c.get("other") is None


def test_cache_expires(tmp_path, monkeypatch):
    c = ModelAvailabilityCache(path=tmp_path / "m.json")
    c.set("acct", ["x"])
    # simula entry vecchia oltre il TTL
    import json
    data = json.loads((tmp_path / "m.json").read_text())
    data["acct"]["ts"] = time.time() - models_mod._CACHE_TTL_SECONDS - 10
    (tmp_path / "m.json").write_text(json.dumps(data))
    assert c.get("acct") is None


# --- available_models (cache-aware) ---------------------------------------
def test_available_models_uses_cache(tmp_path, monkeypatch):
    c = ModelAvailabilityCache(path=tmp_path / "m.json")
    c.set("acct_1", ["gpt-5.5"])

    class FakeStore:
        def load(self):
            return _tokens("acct_1")

    monkeypatch.setattr(models_mod, "discover_available_models",
                        lambda *a, **k: pytest.fail("cache hit: non deve scoprire"))
    out = available_models(FakeStore(), ["gpt-5.5"], cache=c)
    assert out == ["gpt-5.5"]


def test_available_models_discovers_and_caches_on_miss(tmp_path, monkeypatch):
    c = ModelAvailabilityCache(path=tmp_path / "m.json")

    class FakeStore:
        def load(self):
            return _tokens("acct_2")

    monkeypatch.setattr(models_mod, "discover_available_models", lambda *a, **k: ["gpt-5.4-mini"])
    out = available_models(FakeStore(), ["gpt-5.4-mini"], cache=c)
    assert out == ["gpt-5.4-mini"]
    assert c.get("acct_2") == ["gpt-5.4-mini"]  # persistito
