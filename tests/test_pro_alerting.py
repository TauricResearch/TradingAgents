"""Operational alerting (OBS-02): sinks, fan-out isolation, service wiring."""

import json

import pytest

from tests.test_pro_e2e_service import LIMITS, ScriptedSnapshots
from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM
from tradingagents.pro.alerting import (
    Alert,
    AlertManager,
    MemoryAlertSink,
    WebhookAlertSink,
)
from tradingagents.pro.dashboard.app import DashboardState
from tradingagents.pro.execution import (
    VENUES,
    AuditLog,
    CircuitBreaker,
    ExecutionRouter,
    KillSwitch,
    PaperVenueAdapter,
)
from tradingagents.pro.memory import ProMemory
from tradingagents.pro.observability import MetricsRegistry
from tradingagents.pro.service import PaperTradingService


class TestAlertManager:
    def test_invalid_severity_refused(self):
        with pytest.raises(ValueError):
            Alert(severity="page-me", event="x", text="y")

    def test_emit_counts_and_fans_out(self):
        metrics = MetricsRegistry()
        sink = MemoryAlertSink()
        manager = AlertManager(sinks=[sink], metrics=metrics)
        manager.emit("critical", "unit_test", "boom", symbol="XAUUSD")
        assert sink.alerts[0].event == "unit_test"
        assert sink.alerts[0].labels == {"symbol": "XAUUSD"}
        assert metrics.counter("alerts_total",
                               severity="critical", event="unit_test") == 1

    def test_failing_sink_is_isolated(self):
        class Broken:
            def deliver(self, alert):
                raise ConnectionError("pager down")

        metrics = MetricsRegistry()
        healthy = MemoryAlertSink()
        manager = AlertManager(sinks=[Broken(), healthy], metrics=metrics)
        manager.emit("warning", "unit_test", "still delivered")
        assert len(healthy.alerts) == 1  # broken sink did not block delivery
        assert metrics.counter("alert_delivery_failures_total", sink="Broken") == 1

    def test_memory_sink_bounded(self):
        sink = MemoryAlertSink(capacity=3)
        for i in range(5):
            sink.deliver(Alert(severity="info", event="e", text=str(i)))
        assert [a.text for a in sink.alerts] == ["2", "3", "4"]

    def test_default_sink_logs(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="tradingagents.pro.alerting"):
            AlertManager().emit("warning", "unit_test", "logged")
        assert any("ALERT unit_test" in r.message for r in caplog.records)


class TestWebhookSink:
    def test_posts_json_and_filters_severity(self, monkeypatch):
        posted = []

        class FakeResponse:
            def close(self):
                pass

        def fake_urlopen(request, timeout):
            posted.append(json.loads(request.data))
            return FakeResponse()

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        sink = WebhookAlertSink("https://hooks.example/x", min_severity="warning")
        sink.deliver(Alert(severity="info", event="quiet", text="below threshold"))
        sink.deliver(Alert(severity="critical", event="loud", text="page"))
        assert [p["event"] for p in posted] == ["loud"]
        assert posted[0]["severity"] == "critical"


def make_alerting_service(closes, kill_reason=None):
    memory = ProMemory()
    router = ExecutionRouter(
        adapter=PaperVenueAdapter(VENUES["mt5"], starting_cash=100_000.0),
        limits=LIMITS,
        kill_switch=KillSwitch(),
        breaker=CircuitBreaker(LIMITS, equity_base=100_000.0),
        audit=AuditLog(),
    )
    if kill_reason:
        router.kill_switch.engage(kill_reason)
    sink = MemoryAlertSink()
    service = PaperTradingService(
        FakePipelineLLM(), CONFIG, ScriptedSnapshots(closes),
        router=router, memory=memory,
        dashboard_state=DashboardState(memory=memory),
        alerts=AlertManager(sinks=[sink]),
    )
    return service, sink


class TestServiceAlerts:
    def test_clean_iteration_emits_nothing(self):
        service, sink = make_alerting_service([130.0])
        service.run_once()
        assert sink.alerts == []

    def test_kill_switch_refusal_is_critical(self):
        service, sink = make_alerting_service([130.0], kill_reason="drill")
        summary = service.run_once()
        assert summary["order_status"] == "rejected"
        alert = next(a for a in sink.alerts if a.event == "order_rejected")
        assert alert.severity == "critical"
        assert "kill_switch" in alert.text

    def test_iteration_error_is_warning(self):
        service, sink = make_alerting_service([130.0])

        def boom():
            raise RuntimeError("data outage")

        service.run_once = boom
        service.run_forever(interval_seconds=0.0, max_iterations=1,
                            sleep=lambda s: None)
        alert = next(a for a in sink.alerts if a.event == "iteration_error")
        assert alert.severity == "warning"
        assert "RuntimeError" in alert.text

    def test_quarantined_news_is_critical(self):
        service, sink = make_alerting_service([130.0])
        plain = service.snapshot_source

        def poisoned():
            snapshot = plain()
            return snapshot.model_copy(
                update={"missing_feeds": ["news:quarantined:0"]}
            )

        service.snapshot_source = poisoned
        service.run_once()
        alert = next(a for a in sink.alerts if a.event == "injection_quarantined")
        assert alert.severity == "critical"
