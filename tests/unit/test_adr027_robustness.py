import pytest


def test_circuit_breaker_opens_after_threshold_within_window(tmp_path):
    from tradingagents.agents.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

    now = 1_000.0
    breaker = CircuitBreaker(
        state_path=tmp_path / "breaker.json",
        threshold=3,
        window_sec=86_400,
        clock=lambda: now,
    )

    breaker.record_failure("pm_decision_agent", "first")
    breaker.record_failure("pm_decision_agent", "second")
    breaker.assert_available("pm_decision_agent")

    with pytest.raises(CircuitBreakerOpen, match="pm_decision_agent.*pause auto-runs"):
        breaker.record_failure("pm_decision_agent", "third")


def test_circuit_breaker_counts_nonconsecutive_failures_within_window(tmp_path):
    from tradingagents.agents.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

    breaker = CircuitBreaker(
        state_path=tmp_path / "breaker.json",
        threshold=3,
        window_sec=86_400,
        clock=lambda: 1_000.0,
    )

    breaker.record_failure("pm_decision_agent", "first")
    breaker.record_success("pm_decision_agent")

    assert breaker.failure_count("pm_decision_agent") == 1
    breaker.record_failure("pm_decision_agent", "second")
    with pytest.raises(CircuitBreakerOpen, match="pm_decision_agent.*pause auto-runs"):
        breaker.record_failure("pm_decision_agent", "third")


def test_event_mapper_raises_when_node_wall_clock_budget_exceeded(monkeypatch, caplog):
    import logging

    from agent_os.backend.services.event_mapper import EventMapper, NodeWallClockBudgetExceeded

    mapper = EventMapper(node_wall_clock_budget_sec=3)
    mapper.register_run("run-1", "MARKET")
    monkeypatch.setattr(
        "agent_os.backend.services.event_mapper.time.monotonic",
        iter([10.0, 13.5]).__next__,
    )

    start_event = {
        "event": "on_chain_start",
        "run_id": "node-run",
        "parent_ids": ["graph"],
        "metadata": {"langgraph_node": "pm_decision_agent"},
    }
    end_event = {
        "event": "on_chain_end",
        "run_id": "node-run",
        "parent_ids": ["graph"],
        "metadata": {"langgraph_node": "pm_decision_agent"},
        "data": {"output": {"pm_decision": "{}"}},
    }

    assert mapper.map_event("run-1", start_event)["node_id"] == "pm_decision_agent"

    with caplog.at_level(logging.ERROR, logger="agent_os.engine"):
        with pytest.raises(NodeWallClockBudgetExceeded, match="pm_decision_agent.*3.50s.*3.00s"):
            mapper.map_event("run-1", end_event)

    assert any("wall-clock budget exceeded" in r.message for r in caplog.records)


def test_vendor_health_reports_unknown_configured_vendor():
    from tradingagents.dataflows.vendor_health import check_vendor_health

    warnings = check_vendor_health(
        {
            "data_vendors": {"scanner_data": "not-a-vendor"},
            "tool_vendors": {},
        },
        critical_methods=("get_market_movers",),
    )

    assert warnings == [
        {
            "type": "vendor_health_warning",
            "method": "get_market_movers",
            "category": "scanner_data",
            "vendor": "not-a-vendor",
            "status": "degraded",
            "reason": "configured vendor is not available for method",
        }
    ]


def test_vendor_health_uses_supplied_probe_without_crashing():
    from tradingagents.dataflows.vendor_health import check_vendor_health

    def probe(vendor: str, method: str):
        assert vendor == "yfinance"
        assert method == "get_market_movers"
        return False, "temporary auth failure"

    warnings = check_vendor_health(
        {"data_vendors": {"scanner_data": "yfinance"}, "tool_vendors": {}},
        critical_methods=("get_market_movers",),
        probe=probe,
    )

    assert warnings[0]["status"] == "degraded"
    assert warnings[0]["reason"] == "temporary auth failure"


def test_vendor_health_default_probe_reports_missing_required_credentials(monkeypatch):
    from tradingagents.dataflows.vendor_health import check_vendor_health

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    warnings = check_vendor_health(
        {"data_vendors": {}, "tool_vendors": {"get_earnings_calendar": "finnhub"}},
        critical_methods=("get_earnings_calendar",),
    )

    assert warnings[0]["status"] == "degraded"
    assert "FINNHUB_API_KEY" in warnings[0]["reason"]


def test_resume_guidance_mentions_failure_node_and_action():
    from agent_os.backend.services.run_helpers import build_resume_guidance

    message = build_resume_guidance(
        run_kind="pipeline",
        failing_node="risk_synthesis",
        identifier="AAPL",
    )

    assert "risk_synthesis" in message
    assert "resume_from_latest_snapshot" in message
    assert "AAPL" in message


def test_default_config_has_adr027_runtime_guard_defaults():
    from tradingagents.default_config import build_default_config

    cfg = build_default_config(load_dotenv=False, environ={})

    assert cfg["circuit_breaker_enabled"] is True
    assert cfg["circuit_breaker_threshold"] == 3
    assert cfg["circuit_breaker_window_sec"] == 86_400
    assert cfg["node_wall_clock_budget_sec"] == 300.0
    assert cfg["vendor_health_probes_enabled"] is True
