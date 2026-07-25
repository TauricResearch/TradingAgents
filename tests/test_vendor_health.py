"""Circuit-breaker regression tests for routed provider calls."""

from __future__ import annotations

import requests

from tradingagents.dataflows import interface
from tradingagents.dataflows.errors import VendorRateLimitError
from tradingagents.dataflows.health import VendorHealthRegistry
from tradingagents.dataflows.tavily_news import TavilyUnavailableError


def _registry(clock: list[float]) -> VendorHealthRegistry:
    return VendorHealthRegistry(clock=lambda: clock[0])


def test_rate_limit_cools_only_the_failing_capability_then_recovers(monkeypatch):
    clock = [100.0]
    calls: list[str] = []
    yfinance_attempts = [0]

    def yfinance(*_args, **_kwargs):
        calls.append("yfinance")
        yfinance_attempts[0] += 1
        if yfinance_attempts[0] == 1:
            raise VendorRateLimitError("slow down")
        return "yfinance data"

    monkeypatch.setattr(interface, "_vendor_health", _registry(clock))
    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {"yfinance": yfinance, "alpha_vantage": lambda *_args, **_kwargs: calls.append("alpha") or "fallback"},
    )

    assert interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10") == "fallback"
    assert interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10") == "fallback"
    assert calls == ["yfinance", "alpha", "alpha"]

    clock[0] += 60.0
    assert interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10") == "yfinance data"
    assert calls == ["yfinance", "alpha", "alpha", "yfinance"]


def test_cooldown_does_not_cross_capabilities(monkeypatch):
    clock = [100.0]
    calls: list[str] = []

    def throttled(*_args, **_kwargs):
        calls.append("stock")
        raise VendorRateLimitError("slow down")

    monkeypatch.setattr(interface, "_vendor_health", _registry(clock))
    monkeypatch.setattr(
        interface,
        "get_vendor",
        lambda _category, method=None: "yfinance" if method == "get_stock_data" else "yfinance",
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {"yfinance": throttled, "alpha_vantage": lambda *_args, **_kwargs: "fallback"},
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_indicators",
        {"yfinance": lambda *_args, **_kwargs: calls.append("indicator") or "indicator data"},
    )

    assert interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10") == "fallback"
    assert interface.route_to_vendor("get_indicators", "AAPL", "2026-01-01", "2026-01-10") == "indicator data"
    assert calls == ["stock", "indicator"]


def test_health_state_does_not_cross_markets():
    clock = [100.0]
    registry = _registry(clock)
    registry.record_failure(
        vendor="yfinance",
        market="a_share",
        capability="get_stock_data",
        cooldown_seconds=60,
        reason="rate_limit",
    )

    assert registry.cooldown_for(
        vendor="yfinance", market="a_share", capability="get_stock_data"
    ) is not None
    assert registry.cooldown_for(
        vendor="yfinance", market="global", capability="get_stock_data"
    ) is None


def test_http_403_never_creates_a_cooldown():
    response = requests.Response()
    response.status_code = 403
    error = requests.HTTPError(response=response)

    assert interface._cooldown_for_exception(error) == (0.0, "forbidden")


def test_http_5xx_uses_transient_cooldown():
    response = requests.Response()
    response.status_code = 503
    error = requests.HTTPError(response=response)

    assert interface._cooldown_for_exception(error) == (20.0, "http_503")


def test_legacy_vendor_http_status_text_uses_the_same_policy():
    assert interface._cooldown_for_exception(
        TavilyUnavailableError("Tavily search failed with HTTP 429")
    ) == (60.0, "rate_limit")


def test_observed_cooldown_skip_is_visible_in_existing_data_progress(monkeypatch, tmp_path):
    from tradingagents.observability.observer import DurableRunObserver
    from tradingagents.web.run_models import RunSnapshot
    from tradingagents.web.store import RunStore

    clock = [100.0]
    registry = _registry(clock)
    registry.record_failure(
        vendor="yfinance",
        market="global",
        capability="get_stock_data",
        cooldown_seconds=60,
        reason="rate_limit",
    )
    monkeypatch.setattr(interface, "_vendor_health", registry)
    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {"yfinance": lambda *_args, **_kwargs: "must not be called", "alpha_vantage": lambda *_args, **_kwargs: "fallback"},
    )
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-22")
    store.create_run(snapshot)
    observer = DurableRunObserver(store, snapshot.run_id)
    turn = observer.start_turn(actor_id="analyst.market", graph_task_id="task-health", graph_step=1, turn_index=1)

    with observer.invocation_scope(turn, graph_task_id="task-health", graph_step=1):
        assert interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-10") == "fallback"

    progress = [event for event in store.read_events(snapshot.run_id) if event.type == "data.progress"]
    assert [event.payload["stage"] for event in progress] == ["skipped_cooldown", "started"]
    assert progress[0].payload["data_status"] == "skipped"
    assert progress[0].payload["reason"].startswith("cooldown active")
