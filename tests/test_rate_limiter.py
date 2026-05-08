"""Unit tests for the daily-call rate limiter."""

import json

import pytest

from tradingagents.exchange import rate_limiter


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    """Redirect STATE_FILE to a tmp file so tests never touch the real one."""
    fake_state = tmp_path / "rate_limit.json"
    monkeypatch.setattr(rate_limiter, "STATE_FILE", fake_state)
    monkeypatch.delenv(rate_limiter.ENV_DAILY_LIMIT, raising=False)
    return fake_state


@pytest.mark.unit
def test_default_limit_is_100():
    assert rate_limiter.DEFAULT_DAILY_LIMIT == 100


@pytest.mark.unit
def test_initial_state_not_exceeded():
    assert rate_limiter.is_exceeded() is False


@pytest.mark.unit
def test_record_call_increments():
    assert rate_limiter.record_call() == 1
    assert rate_limiter.record_call() == 2
    assert rate_limiter.record_call() == 3


@pytest.mark.unit
def test_record_call_persists_to_disk(isolated_state):
    rate_limiter.record_call()
    rate_limiter.record_call()
    with isolated_state.open("r") as f:
        state = json.load(f)
    assert state["count"] == 2
    assert state["day"] == rate_limiter._utc_today()


@pytest.mark.unit
def test_is_exceeded_at_cap(monkeypatch):
    """Set a low cap and verify is_exceeded fires correctly."""
    monkeypatch.setenv(rate_limiter.ENV_DAILY_LIMIT, "3")
    rate_limiter.record_call()
    rate_limiter.record_call()
    assert rate_limiter.is_exceeded() is False
    rate_limiter.record_call()
    assert rate_limiter.is_exceeded() is True


@pytest.mark.unit
def test_disabled_when_limit_zero(monkeypatch):
    monkeypatch.setenv(rate_limiter.ENV_DAILY_LIMIT, "0")
    for _ in range(50):
        rate_limiter.record_call()
    assert rate_limiter.is_exceeded() is False


@pytest.mark.unit
def test_invalid_env_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(rate_limiter.ENV_DAILY_LIMIT, "not-a-number")
    assert rate_limiter._resolve_limit() == rate_limiter.DEFAULT_DAILY_LIMIT


@pytest.mark.unit
def test_date_rollover_resets_count(isolated_state):
    """When the UTC date changes, the count resets."""
    with isolated_state.open("w") as f:
        json.dump({"day": "1999-01-01", "count": 9999}, f)
    assert rate_limiter.is_exceeded() is False
    assert rate_limiter.record_call() == 1


@pytest.mark.unit
def test_corrupt_state_file_is_recoverable(isolated_state):
    """Malformed state file falls back to a fresh state."""
    isolated_state.write_text("{not valid json")
    assert rate_limiter.is_exceeded() is False
    assert rate_limiter.record_call() == 1


@pytest.mark.unit
def test_get_status_snapshot(monkeypatch):
    monkeypatch.setenv(rate_limiter.ENV_DAILY_LIMIT, "5")
    rate_limiter.record_call()
    rate_limiter.record_call()
    status = rate_limiter.get_status()
    assert status["count"] == 2
    assert status["limit"] == 5
    assert status["exceeded"] is False
    assert status["day"] == rate_limiter._utc_today()
