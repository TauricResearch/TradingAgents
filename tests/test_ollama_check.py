"""Unit tests for ollama_check — all HTTP calls are mocked."""
from unittest.mock import patch, MagicMock
import pytest
import requests as req
from tradingagents.llm_clients.ollama_check import (
    _resolve_base_url,
    ping_ollama,
    list_local_models,
    check_model_available,
    run_ollama_check,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

# backend_url as returned by select_llm_provider() when user picks Ollama
FAKE_CONFIG = {
    "llm_provider":    "ollama",
    "backend_url":     "http://localhost:11434/v1",  # includes /v1 — real value from utils.py
    "deep_think_llm":  "qwen3:latest",
    "quick_think_llm": "glm-4.7-flash:latest",
}

FAKE_RESPONSE_BODY = {
    "models": [
        {"name": "qwen3:latest"},
        {"name": "glm-4.7-flash:latest"},
        {"name": "gpt-oss:latest"},
    ]
}

def _mock_ok(url, timeout=5):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = FAKE_RESPONSE_BODY
    return m

def _mock_conn_error(url, timeout=5):
    raise req.exceptions.ConnectionError

def _mock_timeout(url, timeout=5):
    raise req.exceptions.Timeout

# ── _resolve_base_url ─────────────────────────────────────────────────────────

def test_resolve_strips_v1_suffix():
    """backend_url from select_llm_provider() has /v1 — must be stripped."""
    cfg = {"backend_url": "http://localhost:11434/v1"}
    assert _resolve_base_url(cfg) == "http://localhost:11434"

def test_resolve_no_suffix_unchanged():
    cfg = {"backend_url": "http://localhost:11434"}
    assert _resolve_base_url(cfg) == "http://localhost:11434"

def test_resolve_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://192.168.1.10:11434")
    cfg = {"backend_url": None}
    assert _resolve_base_url(cfg) == "http://192.168.1.10:11434"

def test_resolve_falls_back_to_localhost(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    cfg = {"backend_url": None}
    assert _resolve_base_url(cfg) == "http://localhost:11434"

# ── ping_ollama ───────────────────────────────────────────────────────────────

def test_ping_true_on_200():
    with patch("requests.get", side_effect=_mock_ok):
        assert ping_ollama("http://localhost:11434") is True

def test_ping_false_on_connection_error():
    with patch("requests.get", side_effect=_mock_conn_error):
        assert ping_ollama("http://localhost:11434") is False

def test_ping_false_on_timeout():
    with patch("requests.get", side_effect=_mock_timeout):
        assert ping_ollama("http://localhost:11434") is False

# ── list_local_models ─────────────────────────────────────────────────────────

def test_list_models_parsed_correctly():
    with patch("requests.get", side_effect=_mock_ok):
        models = list_local_models("http://localhost:11434")
    assert "qwen3:latest" in models
    assert "glm-4.7-flash:latest" in models
    assert len(models) == 3

def test_list_models_empty_on_failure():
    with patch("requests.get", side_effect=_mock_conn_error):
        assert list_local_models("http://localhost:11434") == []

# ── check_model_available ─────────────────────────────────────────────────────

def test_exact_match():
    assert check_model_available("qwen3:latest", ["qwen3:latest"]) is True

def test_prefix_match():
    assert check_model_available("qwen3", ["qwen3:latest"]) is True

def test_case_insensitive():
    assert check_model_available("Qwen3", ["qwen3:latest"]) is True

def test_no_match():
    assert check_model_available("command-r", ["qwen3:latest"]) is False

# ── run_ollama_check ──────────────────────────────────────────────────────────

def test_run_true_all_present():
    with patch("requests.get", side_effect=_mock_ok):
        assert run_ollama_check(FAKE_CONFIG) is True

def test_run_false_server_down():
    with patch("requests.get", side_effect=_mock_conn_error):
        assert run_ollama_check(FAKE_CONFIG) is False

def test_run_false_model_missing():
    cfg = {**FAKE_CONFIG, "deep_think_llm": "command-r"}
    with patch("requests.get", side_effect=_mock_ok):
        assert run_ollama_check(cfg) is False

def test_run_exits_on_failure_when_flag_set():
    with patch("requests.get", side_effect=_mock_conn_error):
        with pytest.raises(SystemExit) as exc:
            run_ollama_check(FAKE_CONFIG, exit_on_failure=True)
        assert exc.value.code == 1

def test_run_skips_none_models():
    """Should not crash when deep/quick model keys are None."""
    cfg = {**FAKE_CONFIG, "deep_think_llm": None, "quick_think_llm": None}
    with patch("requests.get", side_effect=_mock_ok):
        assert run_ollama_check(cfg) is True

def test_run_uses_root_url_not_v1():
    """Verify the health check hits /api/tags at root, not /v1/api/tags."""
    called_urls = []
    def capture(url, timeout=5):
        called_urls.append(url)
        return _mock_ok(url, timeout)
    with patch("requests.get", side_effect=capture):
        run_ollama_check(FAKE_CONFIG)
    assert all("/v1" not in u for u in called_urls), \
        f"URL should not contain /v1 — got: {called_urls}"
