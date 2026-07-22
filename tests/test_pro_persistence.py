"""Go-live Phase 0: durable-write helpers + cold-restart recovery.

Before this phase, restart recovery only worked in-process: the paper
venue book and production memory were memory-only, so a real container
restart recovered nothing despite ``service.rehydrate()``. These tests
construct genuinely NEW objects from the same on-disk paths.
"""

import json

from tests.test_pro_e2e_service import LIMITS, ScriptedSnapshots
from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM
from tradingagents.pro.execution import (
    VENUES,
    AuditLog,
    CircuitBreaker,
    ExecutionRouter,
    KillSwitch,
    PaperVenueAdapter,
)
from tradingagents.pro.execution.interface import OrderRequest
from tradingagents.pro.memory import ProMemory
from tradingagents.pro.persistence import (
    append_line_fsync,
    atomic_write_json,
    atomic_write_text,
)
from tradingagents.pro.service import PaperTradingService


class TestHelpers:
    def test_atomic_write_creates_parents_and_replaces(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "doc.json"
        atomic_write_json(target, {"a": 1})
        atomic_write_json(target, {"a": 2})
        assert json.loads(target.read_text()) == {"a": 2}
        assert list(target.parent.glob("*.tmp")) == []  # no debris

    def test_atomic_write_text(self, tmp_path):
        atomic_write_text(tmp_path / "t.txt", "hello")
        assert (tmp_path / "t.txt").read_text() == "hello"

    def test_append_line_fsync(self, tmp_path):
        log = tmp_path / "log.jsonl"
        append_line_fsync(log, "one")
        append_line_fsync(log, "two\n")  # trailing newline normalized
        assert log.read_text() == "one\ntwo\n"


def _order(key="rec-1", qty=1.0, price=4000.0):
    return OrderRequest(
        idempotency_key=key, symbol="XAUUSD", side="BUY",
        quantity=qty, reference_price=price,
    )


class TestPaperAdapterDurability:
    def test_book_survives_restart(self, tmp_path):
        path = tmp_path / "paper_state.json"
        first = PaperVenueAdapter(VENUES["mt5"], state_path=path)
        result = first.submit(_order())
        assert result.status == "filled"

        reborn = PaperVenueAdapter(VENUES["mt5"], state_path=path)
        assert [p.symbol for p in reborn.positions()] == ["XAUUSD"]
        assert reborn.account().equity == first.account().equity
        # idempotency cache survives too: a resubmit after restart dedupes
        assert reborn.submit(_order()).status == "duplicate"

    def test_close_persists(self, tmp_path):
        path = tmp_path / "paper_state.json"
        first = PaperVenueAdapter(VENUES["mt5"], state_path=path)
        first.submit(_order())
        first.close_position("XAUUSD", reference_price=4010.0)
        assert PaperVenueAdapter(VENUES["mt5"], state_path=path).positions() == []

    def test_corrupt_state_starts_fresh(self, tmp_path):
        path = tmp_path / "paper_state.json"
        path.write_text("{nope", encoding="utf-8")
        adapter = PaperVenueAdapter(VENUES["mt5"], state_path=path)
        assert adapter.positions() == []
        assert adapter.account().cash == 100_000.0

    def test_default_stays_in_memory(self, tmp_path):
        adapter = PaperVenueAdapter(VENUES["mt5"])
        adapter.submit(_order())
        assert list(tmp_path.iterdir()) == []  # nothing written anywhere


# routing/persistence/audit tests need a trade to flow, not a quality
# opinion: the fixture's ATR (2.5 on a 4000 tape = 0.125% stop) is far
# inside the cost gate's floor, so disable that gate here — entry-quality
# behavior has its own suite (test_pro_strategy_quality.py)
ROUTING_CONFIG = CONFIG.model_copy(update={
    "risk": CONFIG.risk.model_copy(update={"min_stop_to_cost_ratio": 0.0}),
})


def _build_service(tmp_path, closes):
    """Production-shaped wiring: every stateful piece backed by tmp_path."""
    memory = ProMemory(store_path=tmp_path / "memory.jsonl")
    router = ExecutionRouter(
        adapter=PaperVenueAdapter(VENUES["mt5"], starting_cash=100_000.0,
                                  state_path=tmp_path / "paper_state.json"),
        limits=LIMITS,
        kill_switch=KillSwitch(tmp_path / "KILL"),
        breaker=CircuitBreaker(LIMITS, equity_base=100_000.0),
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )
    service = PaperTradingService(
        FakePipelineLLM(), ROUTING_CONFIG, ScriptedSnapshots(closes),
        router=router, memory=memory,
    )
    return service


class TestColdRestartRecovery:
    def test_open_position_rehydrates_across_processes(self, tmp_path):
        # session 1: pipeline fills a BUY, then the "process" dies
        first = _build_service(tmp_path, closes=[4000.0])
        summary = first.run_once()
        assert summary["order_status"] == "filled"
        assert list(first.open_positions) == ["XAUUSD"]

        # session 2: all-new objects, state only from disk
        second = _build_service(tmp_path, closes=[4001.0])
        assert list(second.open_positions) == ["XAUUSD"], (
            "rehydrate() must rebuild the open position from the persisted "
            "venue book + memory records"
        )
        report = second.router.reconcile()
        assert report.in_sync
        assert second.router.audit.verify()

    def test_audit_chain_survives_restart(self, tmp_path):
        first = _build_service(tmp_path, closes=[4000.0])
        first.run_once()
        entries_before = len(first.router.audit)

        reloaded = AuditLog(tmp_path / "audit.jsonl")
        assert len(reloaded) == entries_before
        assert reloaded.verify()
