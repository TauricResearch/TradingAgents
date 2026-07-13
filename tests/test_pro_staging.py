"""Go-live Phase 6: staged rollout — mode routing + promotion report."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.test_pro_execution_conformance import CREDS, FakeDeltaHttp
from tests.test_pro_persistence import _build_service
from tradingagents.pro.arming import ArmingStore
from tradingagents.pro.execution import AuditLog, OrderManager
from tradingagents.pro.execution.adapters.delta import DeltaAdapter
from tradingagents.pro.staging import (
    ShadowFillTracker,
    promotion_report,
    render_promotion_report,
)


class _FixedQuote:
    def __init__(self, bid, ask):
        self.bid, self.ask = bid, ask


def _service_with_arming(tmp_path, closes=(4000.0,)):
    service = _build_service(tmp_path, closes=list(closes))
    arming = ArmingStore(tmp_path / "arming.json",
                         audit=service.router.audit)
    service.router.arming = arming
    service.dashboard.arming = arming
    return service, arming


def _live_oms(tmp_path, fake=None):
    fake = fake or FakeDeltaHttp()
    adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
    adapter.instruments.refresh()
    oms = OrderManager(adapter, journal_path=tmp_path / "live_j.jsonl")
    oms.recover()
    return oms, fake


class TestModeRouting:
    def test_paper_default_unchanged(self, tmp_path):
        service, _ = _service_with_arming(tmp_path)
        summary = service.run_once()
        assert summary["order_status"] == "filled"
        # filled on the PAPER venue
        assert service.router.adapter.positions()

    def test_shadow_records_divergence_and_fills_paper(self, tmp_path):
        service, arming = _service_with_arming(tmp_path)
        arming.arm("XAUUSD", "shadow", operator="t")
        recorded = []

        class _Tracker:
            def record(self, **kw):
                recorded.append(kw)

        service.router.shadow_tracker = _Tracker()
        summary = service.run_once()
        assert summary["order_status"] == "filled"
        assert service.router.adapter.positions()   # paper venue holds it
        assert len(recorded) == 1
        assert recorded[0]["symbol"] == "XAUUSD"
        assert recorded[0]["paper_fill_price"] > 0

    def test_armed_without_live_route_is_refused(self, tmp_path):
        service, arming = _service_with_arming(tmp_path)
        arming.arm("XAUUSD", "canary", operator="t")
        summary = service.run_once()
        assert summary["order_status"] == "rejected"
        events = [e["event"] for e in service.router.audit.entries]
        assert "live_route_unavailable" in events
        assert service.router.adapter.positions() == []  # nothing paper-filled

    def test_canary_routes_live_at_minimum_size(self, tmp_path):
        service, arming = _service_with_arming(tmp_path)
        live_oms, fake = _live_oms(tmp_path)
        service.router.live_oms = live_oms
        # canary applies to gold in this test: XAUUSD -> XAUTUSD, 1 contract
        arming.arm("XAUUSD", "canary", operator="t")
        summary = service.run_once()
        # async live venue: order ACKED (submitted), not instant-filled
        assert summary["order_status"] in ("submitted", "filled")
        assert len(fake.orders) >= 1
        entry = next(o for o in fake.orders.values()
                     if not o.get("reduce_only"))
        assert entry["size"] == 1  # venue-minimum contracts, canary clamp
        assert service.router.adapter.positions() == []  # NOT on paper

    def test_live_tier_uses_configured_size(self, tmp_path):
        class _RichVenue(FakeDeltaHttp):
            def _route(self, method, path, params, body):
                if method == "GET" and path.startswith("/v2/wallet"):
                    # validation measures against LIVE venue equity — give
                    # the account room for the configured size
                    return 200, {"result": [{"balance": "100000",
                                             "available_balance": "90000"}]}
                return super()._route(method, path, params, body)

        service, arming = _service_with_arming(tmp_path)
        live_oms, fake = _live_oms(tmp_path, fake=_RichVenue())
        service.router.live_oms = live_oms
        arming.arm("XAUUSD", "live", operator="t")
        service.run_once()
        entry = next(o for o in fake.orders.values()
                     if not o.get("reduce_only"))
        assert entry["size"] > 1  # configured sizing, not the canary clamp

    def test_reconcile_unions_both_venues(self, tmp_path):
        service, arming = _service_with_arming(tmp_path)
        live_oms, fake = _live_oms(tmp_path)
        service.router.live_oms = live_oms
        arming.arm("XAUUSD", "live", operator="t")
        service.run_once()
        # settle the live entry so the venue holds the position
        for coid in fake.orders:
            fake.settle(coid)
        live_oms.poll()
        report = service.router.reconcile()
        assert report.in_sync, (report.missing_on_venue,
                                report.unknown_on_venue,
                                report.quantity_mismatches)


class TestShadowFillTracker:
    def test_divergence_math_and_persistence(self, tmp_path):
        tracker = ShadowFillTracker(
            lambda s: _FixedQuote(bid=3998.0, ask=4002.0),
            store_path=tmp_path / "shadow.jsonl")
        fill = tracker.record(symbol="XAUUSD", side="BUY", quantity=1.0,
                              paper_fill_price=4000.0)
        # BUY at ask 4002 vs paper 4000 -> +5 bps worse
        assert fill.divergence_bps == pytest.approx(5.0)
        sell = tracker.record(symbol="XAUUSD", side="SELL", quantity=1.0,
                              paper_fill_price=4000.0)
        # SELL at bid 3998 -> sign * (3998-4000)/4000 = +5 bps worse
        assert sell.divergence_bps == pytest.approx(5.0)
        assert len(tracker.load()) == 2

    def test_quote_failure_records_nothing_and_never_raises(self, tmp_path):
        def dead(_):
            raise ConnectionError("md down")

        tracker = ShadowFillTracker(dead, store_path=tmp_path / "s.jsonl")
        assert tracker.record(symbol="X", side="BUY", quantity=1.0,
                              paper_fill_price=100.0) is None
        assert tracker.load() == []


class TestPromotionReport:
    def _arming_with_history(self, tmp_path, tier, days_ago):
        audit = AuditLog()
        arming = ArmingStore(tmp_path / "arming.json", audit=audit)
        arming.arm("XAUUSD", tier, operator="t")
        # rewrite the audit ts so the tier looks `days_ago` old
        entry = audit.entries[-1]
        aged = (datetime.now(timezone.utc)
                - timedelta(days=days_ago)).isoformat()
        audit._entries[-1] = {**entry, "ts": aged}
        return arming, audit

    def test_shadow_too_short_blocks(self, tmp_path):
        arming, audit = self._arming_with_history(tmp_path, "shadow", 3)
        report = promotion_report(
            pairs=["XAUUSD"], arming=arming, recorder_runs=[],
            journal={"by_mode": {}}, audit_entries=audit.entries,
            shadow_fills=[], promotion_thresholds={"min_shadow_days": 28})
        info = report["pairs"]["XAUUSD"]
        assert not info["promotion_ready"]
        assert any("shadow" in b for b in info["blockers"])

    def test_shadow_long_enough_is_ready(self, tmp_path):
        arming, audit = self._arming_with_history(tmp_path, "shadow", 30)
        report = promotion_report(
            pairs=["XAUUSD"], arming=arming, recorder_runs=[],
            journal={"by_mode": {}}, audit_entries=audit.entries,
            shadow_fills=[{"symbol": "XAUUSD", "divergence_bps": 4.0}],
            promotion_thresholds={"min_shadow_days": 28,
                                  "max_reconciliation_incidents": 0})
        info = report["pairs"]["XAUUSD"]
        assert info["promotion_ready"] and info["next_tier"] == "canary"
        assert info["mean_abs_divergence_bps"] == 4.0

    def test_reconciliation_incident_blocks_everything(self, tmp_path):
        arming, audit = self._arming_with_history(tmp_path, "shadow", 60)
        audit.append("reconciliation", {"in_sync": False})
        report = promotion_report(
            pairs=["XAUUSD"], arming=arming, recorder_runs=[],
            journal={"by_mode": {}}, audit_entries=audit.entries,
            shadow_fills=[],
            promotion_thresholds={"max_reconciliation_incidents": 0})
        info = report["pairs"]["XAUUSD"]
        assert not info["promotion_ready"]
        assert any("reconciliation" in b for b in info["blockers"])

    def test_render_never_claims_automatic_promotion(self, tmp_path):
        arming, audit = self._arming_with_history(tmp_path, "shadow", 30)
        report = promotion_report(
            pairs=["XAUUSD"], arming=arming, recorder_runs=[],
            journal={"by_mode": {}}, audit_entries=audit.entries,
            shadow_fills=[], promotion_thresholds={})
        text = render_promotion_report(report)
        assert "promotion is never automatic" in text


class TestArmingReload:
    def test_service_store_sees_cli_writes(self, tmp_path):
        import time

        path = tmp_path / "arming.json"
        service_store = ArmingStore(path)
        assert service_store.effective_tier("BTC-USD") == "paper"
        time.sleep(0.02)  # ensure a distinct mtime
        ArmingStore(path).arm("BTC-USD", "shadow", operator="cli")
        assert service_store.effective_tier("BTC-USD") == "shadow"
