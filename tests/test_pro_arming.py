"""Go-live Phase 4: arming ceremony state, live.yaml loader, flatten."""

from datetime import timedelta

import pytest

from tradingagents.contracts import utc_now
from tradingagents.pro.arming import DEFAULT_TTL_DAYS, ArmingStore, PairArming
from tradingagents.pro.execution import AuditLog


class TestArmingStore:
    def test_defaults_to_paper(self, tmp_path):
        store = ArmingStore(tmp_path / "arming.json")
        assert store.effective_tier("BTC-USD") == "paper"
        assert not store.is_live("BTC-USD")

    def test_arm_disarm_roundtrip(self, tmp_path):
        audit = AuditLog()
        store = ArmingStore(tmp_path / "arming.json", audit=audit)
        store.arm("BTC-USD", "canary", operator="ajay")
        assert store.is_live("BTC-USD")
        assert store.effective_tier("XAUUSD") == "paper"  # per-pair
        store.disarm("BTC-USD", "manual")
        assert not store.is_live("BTC-USD")
        events = [e["event"] for e in audit.entries]
        assert "arming_armed" in events and "arming_disarmed" in events
        assert audit.verify()

    def test_arm_requires_operator_and_valid_tier(self, tmp_path):
        store = ArmingStore(tmp_path / "arming.json")
        with pytest.raises(ValueError):
            store.arm("BTC-USD", "canary", operator="")
        with pytest.raises(ValueError):
            store.arm("BTC-USD", "bogus", operator="x")
        with pytest.raises(ValueError):
            store.arm("DOGE-USD", "live", operator="x")

    def test_arming_persists_across_restart(self, tmp_path):
        path = tmp_path / "arming.json"
        ArmingStore(path).arm("XAUUSD", "live", operator="ajay")
        assert ArmingStore(path).is_live("XAUUSD")

    def test_expiry_demotes_to_paper(self, tmp_path):
        store = ArmingStore(tmp_path / "arming.json")
        store.arm("BTC-USD", "canary", operator="ajay", ttl_days=30)
        future = utc_now() + timedelta(days=31)
        assert store.effective_tier("BTC-USD", now=future) == "paper"
        assert not store.is_live("BTC-USD", now=future)
        view = store.status(now=future)["BTC-USD"]
        assert view["expired"] and "expired" in view["label"].lower()

    def test_status_labels(self, tmp_path):
        store = ArmingStore(tmp_path / "arming.json")
        assert store.status()["BTC-USD"]["label"] == "PAPER"
        store.arm("BTC-USD", "canary", operator="ajay")
        assert "ARMED (canary)" in store.status()["BTC-USD"]["label"]
        store.disarm("BTC-USD", "loss limit")
        assert "DISARMED (loss limit)" in store.status()["BTC-USD"]["label"]

    def test_pair_arming_default_ttl(self):
        assert DEFAULT_TTL_DAYS == 30
        assert PairArming(pair="BTC-USD").tier == "paper"


class TestLiveConfigLoader:
    def _valid(self):
        return {
            "venue": "delta",
            "pairs": {"BTC-USD": {"mode": "shadow"}},
            "risk": {
                "live_max_account_allocation_pct": 5.0,
                "max_notional_per_trade": 250.0,
                "max_orders_per_hour": 4,
                "max_orders_per_day": 12,
                "daily_loss_limit_pct": 2.0,
                "weekly_loss_limit_pct": 5.0,
                "max_drawdown_from_hwm_pct": 10.0,
                "venue_error_cooldown_seconds": 300,
                "venue_error_burst_threshold": 3,
                "max_spread_bps": 25.0,
                "market_order_notional_cap": 100.0,
                "max_cross_bps": 10.0,
                "max_leverage": 1.0,
                "i_understand_leverage_multiplies_losses": False,
            },
            "breach_action": "cancel_and_flatten",
        }

    def _write(self, tmp_path, doc):
        import yaml

        p = tmp_path / "live.yaml"
        p.write_text(yaml.safe_dump(doc), encoding="utf-8")
        return p

    def test_valid_config_loads(self, tmp_path):
        from tradingagents.pro.live_config import load_live_config

        cfg = load_live_config(self._write(tmp_path, self._valid()))
        assert cfg.venue == "delta"
        assert cfg.mode_for("BTC-USD") == "shadow"
        assert cfg.risk.max_notional_per_trade == 250.0

    def test_missing_risk_key_refuses_and_names_it(self, tmp_path):
        from tradingagents.pro.live_config import LiveConfigError, load_live_config

        doc = self._valid()
        del doc["risk"]["daily_loss_limit_pct"]
        with pytest.raises(LiveConfigError, match="daily_loss_limit_pct"):
            load_live_config(self._write(tmp_path, doc))

    def test_missing_file_refuses(self, tmp_path):
        from tradingagents.pro.live_config import LiveConfigError, load_live_config

        with pytest.raises(LiveConfigError, match="not found"):
            load_live_config(tmp_path / "absent.yaml")

    def test_leverage_without_ack_refuses(self, tmp_path):
        from tradingagents.pro.live_config import LiveConfigError, load_live_config

        doc = self._valid()
        doc["risk"]["max_leverage"] = 3.0
        with pytest.raises(LiveConfigError):
            load_live_config(self._write(tmp_path, doc))

    def test_bad_mode_refuses(self, tmp_path):
        from tradingagents.pro.live_config import LiveConfigError, load_live_config

        doc = self._valid()
        doc["pairs"]["BTC-USD"]["mode"] = "yolo"
        with pytest.raises(LiveConfigError, match="mode"):
            load_live_config(self._write(tmp_path, doc))

    def test_example_file_is_valid(self):
        from pathlib import Path

        from tradingagents.pro.live_config import load_live_config

        example = Path("deploy/live.yaml.example")
        if example.exists():
            cfg = load_live_config(example)
            assert cfg.breach_action in ("cancel_and_flatten", "cancel_only")


class TestEmergencyFlatten:
    def _armed_service(self, tmp_path):
        from tests.test_pro_execution_conformance import CREDS, FakeDeltaHttp
        from tradingagents.pro.execution import (
            AuditLog,
            CircuitBreaker,
            ExecutionRouter,
            KillSwitch,
            OrderManager,
        )
        from tradingagents.pro.execution.adapters.delta import DeltaAdapter
        from tradingagents.pro.execution.orders import BracketSpec, ExecutionPlan

        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        adapter.instruments.refresh()
        from tradingagents.contracts import RiskLimits

        limits = RiskLimits()
        audit = AuditLog()
        router = ExecutionRouter(
            adapter=adapter, limits=limits,
            kill_switch=KillSwitch(tmp_path / "KILL"),
            breaker=CircuitBreaker(limits, equity_base=10_000.0), audit=audit)
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl",
                           audit=audit)
        oms.recover()
        router.oms = oms
        plan = ExecutionPlan(run_id="r", decision_hash="d" * 64,
                             symbol="BTC-USD", side="BUY", quantity=0.01,
                             reference_price=4000.0,
                             bracket=BracketSpec(stop_loss_price=3900.0))
        entry = oms.execute(plan)
        fake.settle(entry.client_order_id)
        oms.poll()
        return router, fake

    def test_flatten_cancels_closes_kills_and_disarms(self, tmp_path):
        from tradingagents.pro.flatten import emergency_flatten

        router, fake = self._armed_service(tmp_path)
        arming = ArmingStore(tmp_path / "arming.json", audit=router.audit)
        arming.arm("BTC-USD", "live", operator="ajay")

        summary = emergency_flatten(router, arming=arming, operator="tester")
        # position flattened on the venue once the reduce-only close settles
        flatten_orders = [o for o in router.oms.orders.values()
                          if o.leg == "flatten"]
        for o in flatten_orders:
            fake.settle(o.client_order_id)
        router.oms.poll()
        assert fake.positions.get("BTCUSD", 0) == 0
        assert router.kill_switch.engaged
        assert not arming.is_live("BTC-USD")  # disarmed
        assert "BTC-USD" in summary["flattened"]
        assert any(e["event"] == "emergency_flatten"
                   for e in router.audit.entries)


class TestFlattenEndpoint:
    def test_requires_confirmation_and_router(self):
        import pytest

        fastapi = pytest.importorskip("fastapi")  # noqa: F841
        from fastapi.testclient import TestClient

        from tradingagents.pro.dashboard.app import DashboardState, create_app
        from tradingagents.pro.memory import ProMemory

        bare = TestClient(create_app(DashboardState(memory=ProMemory())))
        # no router attached -> 503
        assert bare.post("/api/flatten", json={"confirm": "FLATTEN"}
                         ).status_code == 503
