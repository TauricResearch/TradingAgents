"""Go-live Phase 3: live risk gates, loss-limit disarm, preflight."""

from datetime import datetime, timezone

import pytest

from tradingagents.contracts import LiveRiskLimits
from tradingagents.pro.execution.live_gates import (
    LiveGateChain,
    LossLimitMonitor,
)


def _chain(**overrides) -> LiveGateChain:
    return LiveGateChain(LiveRiskLimits(**overrides))


class TestLiveRiskLimitsContract:
    def test_leverage_requires_acknowledgement(self):
        with pytest.raises(ValueError, match="multiplies losses"):
            LiveRiskLimits(max_leverage=2.0)
        # explicit acknowledgement makes it valid
        assert LiveRiskLimits(
            max_leverage=2.0,
            i_understand_leverage_multiplies_losses=True).max_leverage == 2.0


class TestGateChain:
    BASE = {"notional": 100.0, "equity": 10_000.0, "open_notional": 0.0,
            "open_positions": 0}

    def test_clean_entry_passes(self):
        assert _chain().check_entry(**self.BASE).ok

    def test_notional_cap(self):
        r = _chain(max_notional_per_trade=50.0).check_entry(**self.BASE)
        assert not r.ok and r.gate == "live_notional_cap"

    def test_account_allocation_ceiling(self):
        r = _chain(live_max_account_allocation_pct=1.0).check_entry(
            notional=200.0, equity=10_000.0, open_notional=0.0,
            open_positions=0)
        assert not r.ok and r.gate == "live_allocation"

    def test_max_open_positions_enforced(self):
        r = _chain().check_entry(notional=10.0, equity=10_000.0,
                                 open_notional=0.0, open_positions=3,
                                 max_open_positions=3)
        assert not r.ok and r.gate == "live_max_positions"

    def test_risk_per_trade_from_stop_distance(self):
        # risk_amount 200 on 10k equity = 2% > default 1% ceiling
        r = _chain().check_entry(**self.BASE, risk_amount=200.0,
                                 max_risk_pct=1.0)
        assert not r.ok and r.gate == "live_risk_per_trade"

    def test_spread_gate(self):
        r = _chain(max_spread_bps=10.0).check_entry(**self.BASE,
                                                    spread_bps=25.0)
        assert not r.ok and r.gate == "live_spread"

    def test_hourly_rate_limit(self):
        chain = _chain(max_orders_per_hour=2)
        now = 1_000_000.0
        for _ in range(2):
            chain.record_order(now)
        r = chain.check_entry(**self.BASE, now=now)
        assert not r.ok and r.gate == "live_rate_hourly"

    def test_venue_error_cooldown(self):
        chain = _chain(venue_error_burst_threshold=2,
                       venue_error_cooldown_seconds=300.0)
        now = 2_000_000.0
        chain.record_venue_error(now)
        chain.record_venue_error(now)
        r = chain.check_entry(**self.BASE, now=now)
        assert not r.ok and r.gate == "live_error_cooldown"

    def test_error_cooldown_expires(self):
        chain = _chain(venue_error_burst_threshold=2,
                       venue_error_cooldown_seconds=300.0)
        chain.record_venue_error(1000.0)
        chain.record_venue_error(1000.0)
        # 400s later the window has cleared
        assert chain.check_entry(**self.BASE, now=1400.0).ok


class TestLossLimitMonitor:
    def _monitor(self, tmp_path, **overrides):
        breaches = []
        limits = LiveRiskLimits(**overrides)
        mon = LossLimitMonitor(limits, tmp_path / "loss.json",
                               on_breach=breaches.append)
        return mon, breaches

    def test_daily_loss_breach_fires_once_and_latches(self, tmp_path):
        mon, breaches = self._monitor(tmp_path, daily_loss_limit_pct=2.0)
        t0 = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
        assert mon.evaluate(10_000.0, now=t0) is None  # anchor set
        # down 3% same day -> breach
        reason = mon.evaluate(9_700.0, now=t0)
        assert reason and "daily loss" in reason
        assert len(breaches) == 1
        # further evaluations don't re-fire (latched)
        assert mon.evaluate(9_600.0, now=t0) is None
        assert len(breaches) == 1

    def test_drawdown_from_hwm(self, tmp_path):
        mon, breaches = self._monitor(tmp_path, max_drawdown_from_hwm_pct=10.0,
                                      daily_loss_limit_pct=99.0,
                                      weekly_loss_limit_pct=99.0)
        t0 = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
        mon.evaluate(10_000.0, now=t0)
        mon.evaluate(12_000.0, now=t0)  # new high-water mark
        reason = mon.evaluate(10_700.0, now=t0)  # -10.8% from 12k
        assert reason and "drawdown" in reason

    def test_breach_persists_across_restart(self, tmp_path):
        mon, _ = self._monitor(tmp_path, daily_loss_limit_pct=2.0)
        t0 = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
        mon.evaluate(10_000.0, now=t0)
        mon.evaluate(9_000.0, now=t0)
        assert mon.breached
        # a fresh monitor from the same file remembers the breach
        reborn, reborn_breaches = self._monitor(tmp_path,
                                                daily_loss_limit_pct=2.0)
        assert reborn.breached
        assert reborn.evaluate(9_000.0, now=t0) is None  # stays latched

    def test_clear_breach_requires_operator(self, tmp_path):
        mon, _ = self._monitor(tmp_path, daily_loss_limit_pct=2.0)
        t0 = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
        mon.evaluate(10_000.0, now=t0)
        mon.evaluate(9_000.0, now=t0)
        with pytest.raises(ValueError):
            mon.clear_breach("")
        mon.clear_breach("operator:ajay")
        assert mon.breached == ""


class TestBreachResponse:
    def test_cancels_flattens_and_engages_kill_switch(self, tmp_path):
        from tests.test_pro_execution_conformance import CREDS, FakeDeltaHttp
        from tradingagents.pro.execution import KillSwitch, OrderManager
        from tradingagents.pro.execution.adapters.delta import DeltaAdapter
        from tradingagents.pro.execution.live_gates import breach_response
        from tradingagents.pro.execution.orders import BracketSpec, ExecutionPlan

        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        adapter.instruments.refresh()
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl")
        oms.recover()
        plan = ExecutionPlan(run_id="r", decision_hash="d" * 64,
                             symbol="BTC-USD", side="BUY", quantity=0.01,
                             reference_price=4000.0,
                             bracket=BracketSpec(stop_loss_price=3900.0))
        entry = oms.execute(plan)
        fake.settle(entry.client_order_id)
        oms.poll()

        kill = KillSwitch()
        respond = breach_response(
            oms, kill, adapter.positions,
            reference_prices={"BTC-USD": 4000.0})
        respond("daily loss 3% >= 2%")

        assert kill.engaged
        assert fake.positions.get("BTCUSD", 0) == 0 or any(
            o.leg == "flatten" for o in oms.orders.values())


class TestPreflight:
    def test_open_dashboard_fails_auth_check(self, monkeypatch):
        from tradingagents.pro.preflight import ReadinessReport, check_auth

        monkeypatch.delenv("PRO_DASHBOARD_TOKEN", raising=False)
        report = ReadinessReport()
        check_auth(report)
        assert not report.ok
        assert report.checks[0].status == "fail"

    def test_weak_token_fails(self, monkeypatch):
        from tradingagents.pro.preflight import ReadinessReport, check_auth

        monkeypatch.setenv("PRO_DASHBOARD_TOKEN", "short")
        report = ReadinessReport()
        check_auth(report)
        assert not report.ok

    def test_strong_token_passes(self, monkeypatch):
        from tradingagents.pro.preflight import ReadinessReport, check_auth

        monkeypatch.setenv("PRO_DASHBOARD_TOKEN", "x" * 32)
        report = ReadinessReport()
        check_auth(report)
        assert report.ok

    def test_clock_skew_failure_blocks(self, monkeypatch):
        from tradingagents.pro.execution import AdapterError
        from tradingagents.pro.preflight import ReadinessReport, check_clock

        class SkewedAdapter:
            def check_clock(self):
                raise AdapterError("skew +9.0s exceeds 2.0s budget")

        report = ReadinessReport()
        check_clock(report, SkewedAdapter())
        assert not report.ok

    def test_no_adapter_fails_venue_checks(self, monkeypatch):
        from tradingagents.pro.preflight import go_live_readiness

        monkeypatch.setenv("PRO_DASHBOARD_TOKEN", "x" * 32)
        report = go_live_readiness(adapter=None)
        assert not report.ok
        gates = {c.name: c.status for c in report.checks}
        assert gates["venue_key_scope"] == "fail"

    def test_report_signed_into_audit(self, monkeypatch):
        from tradingagents.pro.execution import AuditLog
        from tradingagents.pro.preflight import go_live_readiness

        monkeypatch.setenv("PRO_DASHBOARD_TOKEN", "x" * 32)
        audit = AuditLog()
        go_live_readiness(adapter=None, audit=audit)
        assert any(e["event"] == "go_live_readiness" for e in audit.entries)
        assert audit.verify()


class TestSecrets:
    def test_file_convention_wins_over_env(self, tmp_path, monkeypatch):
        from tradingagents.pro.secrets import get_secret

        secret_file = tmp_path / "key"
        secret_file.write_text("from-file\n")
        monkeypatch.setenv("MY_SECRET_FILE", str(secret_file))
        monkeypatch.setenv("MY_SECRET", "from-env")
        assert get_secret("MY_SECRET") == "from-file"

    def test_required_missing_raises(self, monkeypatch):
        from tradingagents.pro.secrets import SecretUnavailable, get_secret

        monkeypatch.delenv("ABSENT_SECRET", raising=False)
        with pytest.raises(SecretUnavailable):
            get_secret("ABSENT_SECRET", required=True)

    def test_permission_check(self, tmp_path):
        import os

        from tradingagents.pro.secrets import file_permissions_ok

        p = tmp_path / "s"
        p.write_text("x")
        os.chmod(p, 0o600)
        assert file_permissions_ok(p)
        os.chmod(p, 0o644)
        assert not file_permissions_ok(p)


class TestRouterLiveGateIntegration:
    def test_live_gate_rejection_is_audited(self, tmp_path):
        from tests.test_pro_persistence import _build_service

        service = _build_service(tmp_path, closes=[4000.0])
        # a tiny notional cap makes the standard fixture order fail the gate
        service.router.live_gates = LiveGateChain(
            LiveRiskLimits(max_notional_per_trade=1.0))
        summary = service.run_once()
        assert summary["order_status"] == "rejected"
        events = [e["event"] for e in service.router.audit.entries]
        assert "live_notional_cap" in events
        assert service.router.audit.verify()
