"""Go-live Phase 5: Telegram sink, health model, dead-man, exports."""

import json

import pytest

from tradingagents.pro.alerting import Alert, AlertManager, TelegramAlertSink


class _FakeUrlopen:
    """Records the last urllib request; optionally raises."""

    def __init__(self, raise_exc=None):
        self.calls = []
        self.raise_exc = raise_exc

    def __call__(self, request, timeout=None):
        self.calls.append(request)
        if self.raise_exc:
            raise self.raise_exc

        class _Resp:
            def close(self_inner):
                pass

        return _Resp()


class TestTelegramAlertSink:
    def test_builds_bot_api_request(self, monkeypatch):
        fake = _FakeUrlopen()
        monkeypatch.setattr("urllib.request.urlopen", fake)
        sink = TelegramAlertSink("secret-token", "chat-42")
        sink.deliver(Alert("critical", "kill_switch", "halted"))
        assert len(fake.calls) == 1
        req = fake.calls[0]
        assert "bot" in req.full_url and "sendMessage" in req.full_url
        body = json.loads(req.data)
        assert body["chat_id"] == "chat-42"
        assert "kill_switch" in body["text"]

    def test_min_severity_filters_info(self, monkeypatch):
        fake = _FakeUrlopen()
        monkeypatch.setattr("urllib.request.urlopen", fake)
        TelegramAlertSink("t", "c", min_severity="warning").deliver(
            Alert("info", "feeds", "degraded"))
        assert fake.calls == []

    def test_failure_is_fail_closed_and_redacted(self, monkeypatch):
        fake = _FakeUrlopen(raise_exc=RuntimeError("boom with secret-token in it"))
        monkeypatch.setattr("urllib.request.urlopen", fake)
        sink = TelegramAlertSink("secret-token", "c")
        # the AlertManager isolates sink failures; the token must not leak
        mgr = AlertManager(sinks=[sink])
        mgr.emit("critical", "x", "y")  # must not raise
        with pytest.raises(RuntimeError) as exc:
            sink.deliver(Alert("critical", "x", "y"))
        assert "secret-token" not in str(exc.value)


class TestSinkWiring:
    def test_no_optional_sinks_without_env(self, monkeypatch):
        from tradingagents.pro.dashboard.events import EventBroadcaster
        from tradingagents.pro.main import _build_alert_sinks

        for var in ("PRO_TELEGRAM_BOT_TOKEN", "PRO_TELEGRAM_CHAT_ID",
                    "PRO_ALERT_WEBHOOK_URL"):
            monkeypatch.delenv(var, raising=False)
        sinks = _build_alert_sinks(EventBroadcaster())
        names = {type(s).__name__ for s in sinks}
        assert names == {"LogAlertSink", "BroadcastAlertSink"}

    def test_telegram_and_webhook_added_with_env(self, monkeypatch):
        from tradingagents.pro.dashboard.events import EventBroadcaster
        from tradingagents.pro.main import _build_alert_sinks

        monkeypatch.setenv("PRO_TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("PRO_TELEGRAM_CHAT_ID", "c")
        monkeypatch.setenv("PRO_ALERT_WEBHOOK_URL", "https://example/hook")
        names = {type(s).__name__ for s in _build_alert_sinks(EventBroadcaster())}
        assert "TelegramAlertSink" in names and "WebhookAlertSink" in names


class TestLiveHealth:
    def _state(self, tmp_path, missing=(), last_run_age=0.0):
        import time

        from tradingagents.pro.dashboard.app import DashboardState
        from tradingagents.pro.memory import ProMemory
        from tradingagents.pro.observability import MetricsRegistry

        state = DashboardState(memory=ProMemory())
        metrics = MetricsRegistry()
        metrics.set_gauge("last_run_ts", time.time() - last_run_age)
        state.metrics = metrics
        return state

    def test_ok_when_clean(self, tmp_path):
        from tradingagents.pro.health import live_health

        report = live_health(self._state(tmp_path))
        assert report.ok

    def test_stale_run_is_degraded(self, tmp_path):
        from tradingagents.pro.health import live_health

        report = live_health(self._state(tmp_path, last_run_age=99_999),
                             max_run_age_seconds=5400)
        assert not report.ok and "run_recency" in report.degraded

    def test_venue_unreachable_is_degraded(self, tmp_path):
        from tradingagents.pro.health import live_health

        state = self._state(tmp_path)

        class _DeadRouter:
            class adapter:
                @staticmethod
                def account():
                    raise ConnectionError("down")

            class kill_switch:
                engaged = False
                reason = ""

        state.router = _DeadRouter()
        report = live_health(state)
        assert not report.ok and "venue" in report.degraded

    def test_endpoint_503_when_degraded(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from tradingagents.pro.dashboard.app import create_app

        state = self._state(tmp_path, last_run_age=99_999)
        client = TestClient(create_app(state))
        resp = client.get("/health/live")
        assert resp.status_code == 503
        assert resp.json()["ok"] is False

    def test_endpoint_200_clean(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from tradingagents.pro.dashboard.app import create_app

        client = TestClient(create_app(self._state(tmp_path)))
        assert client.get("/health/live").status_code == 200


class TestDeadManSwitch:
    def test_fresh_heartbeat_no_trip(self):
        from tradingagents.pro.deadman import DeadManSwitch

        healthy = type("H", (), {"ok": True})()
        tripped = []
        dm = DeadManSwitch(lambda: healthy, tripped.append,
                           timeout_seconds=600, now=lambda: 1000.0)
        assert dm.tick(now=2000.0) is False  # healthy refreshes heartbeat
        assert tripped == []

    def test_stale_health_trips_once(self):
        from tradingagents.pro.deadman import DeadManSwitch

        unhealthy = type("H", (), {"ok": False})()
        tripped = []
        dm = DeadManSwitch(lambda: unhealthy, tripped.append,
                           timeout_seconds=600, now=lambda: 1000.0)
        assert dm.tick(now=1000.0) is False   # within timeout
        assert dm.tick(now=1700.0) is True    # 700s > 600s -> trip
        assert dm.tick(now=1800.0) is False   # latched
        assert tripped == ["health unconfirmed for 700s (timeout 600s)"] or \
            len(tripped) == 1

    def test_cancel_resting_orders_action(self, tmp_path):
        from tests.test_pro_execution_conformance import CREDS, FakeDeltaHttp
        from tradingagents.contracts import RiskLimits
        from tradingagents.pro.deadman import cancel_resting_orders
        from tradingagents.pro.execution import (
            AuditLog,
            CircuitBreaker,
            ExecutionRouter,
            KillSwitch,
            OrderManager,
        )
        from tradingagents.pro.execution.adapters.delta import DeltaAdapter

        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        adapter.instruments.refresh()
        limits = RiskLimits()
        audit = AuditLog()
        router = ExecutionRouter(
            adapter=adapter, limits=limits, kill_switch=KillSwitch(),
            breaker=CircuitBreaker(limits, equity_base=10_000.0), audit=audit)
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl",
                           audit=audit)
        oms.recover()
        router.oms = oms
        # a resting limit order (stays open on the fake venue)
        from tradingagents.pro.execution.orders import ExecutionPlan

        oms.execute(ExecutionPlan(
            run_id="r", decision_hash="d" * 64, symbol="BTC-USD", side="BUY",
            quantity=0.01, reference_price=4000.0, order_type="limit",
            limit_price=1000.0))
        resting = [o for o in oms.orders.values()
                   if o.sent and not o.state.terminal]
        assert resting  # something is working on the venue

        cancel_resting_orders(router)("test")
        still_open = [o for o in oms.orders.values()
                      if o.sent and not o.state.terminal]
        assert still_open == []                 # cancelled
        assert router.kill_switch.engaged       # and halted
        assert any(e["event"] == "deadman_tripped" for e in audit.entries)


class TestJournalExportColumns:
    def test_by_mode_and_venue_fields(self):
        # reuse the pipeline's real recommendation so the trade record is
        # contract-valid, then close it with venue details + a mode tag
        from tests.test_pro_pipeline_graph import (
            CONFIG,
            FakePipelineLLM,
            pipeline_snapshot,
            run_pipeline,
        )
        from tradingagents.pro.dashboard.service import trade_journal
        from tradingagents.pro.memory import ProMemory

        memory = ProMemory()
        result = run_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot())
        rec = result["recommendation"]
        trade = memory.record_trade(rec, regime=result.get("regime"))
        memory.close_trade(trade.id, pnl=12.0, details={
            "mode": "canary", "commission": 0.5,
            "venue_order_id": "ta-abc", "fill_price": 4010.0,
            "entry_price": 4000.0})
        journal = trade_journal(memory)
        entry = journal["entries"][0]
        assert entry["mode"] == "canary"
        assert entry["commission"] == 0.5
        assert entry["venue_order_id"] == "ta-abc"
        assert journal["by_mode"]["canary"]["n_trades"] == 1
        assert journal["by_mode"]["canary"]["win_rate"] == 1.0
