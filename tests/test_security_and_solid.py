import os
import threading
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import db
from backend.app.core.security import (
    mask_secret_key,
    sanitize_date,
    sanitize_sensitive_data,
    sanitize_sensitive_text,
    sanitize_ticker,
)
from backend.app.main import app
from backend.app.workers.runner import run_analysis_task
from backend.app.workers.job_manager import job_manager

client = TestClient(app)

def test_mask_secret_key():
    # Long key (>= 8 chars)
    assert mask_secret_key("sk-proj-1234567890abcdef") == "sk-...cdef"
    assert mask_secret_key("AIzaSyD-1234567890abcdef") == "AIz...cdef"

    # Medium key (3-7 chars)
    assert mask_secret_key("mykey12") == "m...2"
    assert mask_secret_key("1234") == "1...4"

    # Very short or empty
    assert mask_secret_key("ab") == "***"
    assert mask_secret_key("a") == "***"
    assert mask_secret_key("") == ""
    assert mask_secret_key(None) == ""

def test_sanitize_sensitive_text_regex_patterns(monkeypatch):
    # Set a mock active key in environment
    monkeypatch.setenv("OPENAI_API_KEY", "sk-custom-secret-key-987654321")

    # String with OpenAI key format
    text1 = "Error: Invalid OpenAI request with key sk-proj-supersecretkey123456789"
    cleaned1 = sanitize_sensitive_text(text1)
    assert "sk-proj-supersecretkey123456789" not in cleaned1
    assert "[REDACTED_API_KEY]" in cleaned1

    # String with Anthropic key format
    text2 = "Anthropic API rejected token sk-ant-api03-abcdef1234567890123456"
    cleaned2 = sanitize_sensitive_text(text2)
    assert "sk-ant-api03-abcdef1234567890123456" not in cleaned2
    assert "[REDACTED_API_KEY]" in cleaned2

    # String with Google AIza key format
    text3 = "Call failed: https://generativelanguage.googleapis.com?key=AIzaSyD1234567890123456789012345678901"
    cleaned3 = sanitize_sensitive_text(text3)
    assert "AIzaSyD1234567890123456789012345678901" not in cleaned3
    assert "[REDACTED_API_KEY]" in cleaned3

    # String with Bearer token format
    text4 = "Authorization: Bearer my-long-secret-jwt-token-value-12345"
    cleaned4 = sanitize_sensitive_text(text4)
    assert "my-long-secret-jwt-token-value-12345" not in cleaned4
    assert "[REDACTED_API_KEY]" in cleaned4

    # String containing exact env var value
    text5 = "Exception occurred in auth for sk-custom-secret-key-987654321 on host"
    cleaned5 = sanitize_sensitive_text(text5)
    assert "sk-custom-secret-key-987654321" not in cleaned5
    assert "[REDACTED_API_KEY]" in cleaned5

def test_sanitize_sensitive_data_nested():
    raw_payload = {
        "user": "trader1",
        "api_key": "sk-real-live-secret-token-12345",
        "nested": {
            "token": "secret_token_val_1234",
            "log": "Calling upstream with sk-test-key-1234567890123456",
            "normal_field": 42
        },
        "items": [
            "normal string",
            "Bearer auth-bearer-token-1234567890",
            {"secret_password": "super_secret_pw"}
        ]
    }

    sanitized = sanitize_sensitive_data(raw_payload)

    # Dictionary key indicating secret should be masked
    assert "sk-real-live-secret-token-12345" not in str(sanitized)
    assert sanitized["api_key"] == "sk-...2345"

    # Nested secret token
    assert "secret_token_val_1234" not in str(sanitized)
    assert sanitized["nested"]["token"] == "sec...1234"

    # Nested string with pattern
    assert "sk-test-key-1234567890123456" not in sanitized["nested"]["log"]
    assert "[REDACTED_API_KEY]" in sanitized["nested"]["log"]

    # Preserves non-sensitive fields
    assert sanitized["nested"]["normal_field"] == 42
    assert sanitized["items"][0] == "normal string"
    assert "[REDACTED_API_KEY]" in sanitized["items"][1]

def test_sanitize_ticker_path_traversal():
    assert sanitize_ticker("AAPL") == "AAPL"
    assert sanitize_ticker("btc-usd") == "BTC-USD"
    assert sanitize_ticker("nvda_2") == "NVDA_2"

    # Path traversal attempts
    assert sanitize_ticker("../../etc/passwd") == "ETCPASSWD"
    assert sanitize_ticker("..\\..\\windows\\system32") == "WINDOWSSYSTEM32"
    assert sanitize_ticker("AAPL; rm -rf /") == "AAPL"
    assert sanitize_ticker("", default="FALLBACK") == "FALLBACK"
    assert sanitize_ticker(None, default="FALLBACK") == "FALLBACK"

def test_sanitize_date_path_traversal():
    assert sanitize_date("2026-09-18") == "2026-09-18"
    assert sanitize_date("20260918") == "20260918"

    # Path traversal attempts
    assert sanitize_date("../../2026") == "2026"
    assert sanitize_date("2026-09-18; DROP TABLE jobs;") == "2026-09-18"
    assert sanitize_date("", default="DEFAULT") == "DEFAULT"
    assert sanitize_date(None, default="DEFAULT") == "DEFAULT"

def test_runner_exception_redacts_api_keys(monkeypatch):
    # Setup job record
    job_id = str(uuid.uuid4())
    job_dict = {
        "id": job_id,
        "ticker": "TSLA",
        "trade_date": "2024-05-10",
        "asset_type": "stock",
        "analysts": ["market"],
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.6",
        "quick_think_llm": "gpt-5.6-luna",
    }
    db.create_job(job_dict)

    # Set mock secret key in environment
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-secret-never-expose-999")

    emitted_events = []
    def mock_event_cb(event_type: str, data: dict):
        emitted_events.append((event_type, data))

    # Mock TradingAgentsGraph to raise an exception containing a secret key
    def fake_init(*args, **kwargs):
        raise ValueError("Authentication failed for key sk-live-secret-never-expose-999!")

    import backend.app.workers.runner as runner_module
    monkeypatch.setattr(runner_module, "TradingAgentsGraph", fake_init)

    # Run runner task
    result = run_analysis_task(job_dict, event_callback=mock_event_cb)

    assert result["status"] == "failed"
    # Verify the secret is NOT in error_message
    assert "sk-live-secret-never-expose-999" not in result["error_message"]
    assert "[REDACTED_API_KEY]" in result["error_message"]

    # Verify emitted event also has redacted message
    failed_events = [e for e in emitted_events if e[0] == "job_failed"]
    assert len(failed_events) == 1
    event_data = failed_events[0][1]
    assert "sk-live-secret-never-expose-999" not in event_data["error_message"]
    assert "sk-live-secret-never-expose-999" not in event_data["traceback"]
    assert "[REDACTED_API_KEY]" in event_data["error_message"]

    # Clean up test job
    db.delete_job(job_id)

def test_job_manager_broadcast_event_scrubs_secrets():
    job_id = str(uuid.uuid4())
    job_dict = {
        "id": job_id,
        "ticker": "NVDA",
        "trade_date": "2024-05-10",
        "asset_type": "stock",
        "analysts": ["market"],
        "status": "running",
        "progress": 20,
        "current_stage": "Running",
        "created_at": "2026-09-18T10:00:00Z"
    }
    db.create_job(job_dict)

    # Broadcast event containing an API key in data
    sensitive_event_data = {
        "stage": "Auth Check",
        "api_key": "sk-proj-super-secret-key-12345",
        "detail": "Connected using sk-proj-super-secret-key-12345"
    }
    job_manager._broadcast_event(job_id, "stage_change", sensitive_event_data)

    # Verify event stored in DB was sanitized
    events = db.get_events(job_id)
    assert len(events) >= 1
    last_event = events[-1]
    event_data = last_event["data"]

    # Key should be masked, text should have [REDACTED_API_KEY]
    assert "sk-proj-super-secret-key-12345" not in str(event_data)
    assert event_data["api_key"] == "sk-...2345"
    assert "[REDACTED_API_KEY]" in event_data["detail"]

    # Clean up
    db.delete_job(job_id)

def test_api_keys_endpoint_masks_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-confidential-prod-key-12345")
    res = client.get("/api/v1/config/keys")
    assert res.status_code == 200
    data = res.json()
    openai_key = next((k for k in data["keys"] if k["provider"] == "openai"), None)
    assert openai_key is not None
    assert openai_key["configured"] is True
    # Verify preview is masked
    assert openai_key["preview"] == "sk-...2345"
    assert "confidential-prod-key" not in openai_key["preview"]
