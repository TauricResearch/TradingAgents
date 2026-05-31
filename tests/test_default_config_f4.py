import pytest


@pytest.mark.unit
def test_default_config_has_f4_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    # Orchestrator master switch + cadences
    assert C["orchestrator_enabled"] is False
    assert C["promoter_poll_interval_s"] == 10
    assert C["promoter_batch_size"] == 50
    assert C["alert_cooldown_min"] == 60
    assert C["alert_salience_threshold"] == 0.7
    assert C["alert_ticker_confidence_threshold"] == 0.8
    assert C["worker_poll_interval_s"] == 2
    assert C["worker_job_timeout_min"] == 20
    assert C["max_concurrent_jobs"] == 1
    # Cost guards — all off
    assert C["trigger_backpressure_enabled"] is False
    assert C["trigger_backpressure_max_pending"] == 20
    assert C["trigger_daily_rate_enabled"] is False
    assert C["trigger_daily_rate_max_jobs"] == 200
    assert C["daily_budget_enabled"] is False
    assert C["daily_budget_usd"] == 10.0


@pytest.mark.unit
def test_env_override_orchestrator_enabled(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_ORCHESTRATOR_ENABLED", "1")
    # Re-import to re-evaluate env overrides (DEFAULT_CONFIG is built at import).
    import importlib
    import tradingagents.default_config as m
    importlib.reload(m)
    assert m.DEFAULT_CONFIG["orchestrator_enabled"] is True
