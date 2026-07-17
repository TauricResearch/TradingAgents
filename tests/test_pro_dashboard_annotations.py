"""Chart annotations aggregation (chart Phase 1)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tradingagents.pro.dashboard.annotations import chart_annotations
from tradingagents.pro.memory import MemoryKind, MemoryRecord, ProMemory

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _rec(rec_id: str, action: str = "SELL", entry: float = 4000.0):
    return SimpleNamespace(
        id=rec_id,
        action=SimpleNamespace(value=action),
        confidence=70,
        market_regime=SimpleNamespace(value="trending"),
        entry_price=entry if action != "HOLD" else None,
        stop_loss=entry * 1.01 if action != "HOLD" else None,
        invalidation_price=entry * 1.012 if action != "HOLD" else None,
        take_profits=(
            [SimpleNamespace(price=entry * 0.98, size_fraction=0.5)]
            if action != "HOLD" else []
        ),
    )


def _run(run_id: str, at: datetime, symbol: str = "XAUUSD",
         rec=None, rejection=None):
    return SimpleNamespace(
        run_id=run_id, started_at=at, symbol=symbol,
        recommendation=rec, rejection=rejection,
    )


def _trade_and_outcome(memory: ProMemory, rec_id: str, symbol: str,
                       opened: datetime, closed: datetime,
                       pnl: float, mode: str = "paper") -> None:
    trade = memory._add(MemoryRecord(
        kind=MemoryKind.TRADE, text=f"trade {rec_id}", symbol=symbol,
        payload={"recommendation_id": rec_id, "entry_price": 4000.0},
        event_time=opened,
    ))
    memory._add(MemoryRecord(
        kind=MemoryKind.OUTCOME, text=f"outcome {rec_id}", symbol=symbol,
        ref_id=trade.id,
        payload={"pnl": pnl, "won": pnl > 0, "mode": mode,
                 "closed_at": closed.isoformat(), "fill_price": 3990.0},
        event_time=closed,
    ))


def test_span_rules_closed_superseded_open():
    memory = ProMemory()
    runs = [
        _run("r1", T0, rec=_rec("rec1")),
        _run("r2", T0 + timedelta(hours=2), rec=_rec("rec2")),
        _run("r3", T0 + timedelta(hours=4), rec=_rec("rec3")),
    ]
    # r1's trade closed at +1h -> span "closed"; r2 unclosed but followed
    # by r3 -> "superseded"; r3 unclosed and last -> "open"
    _trade_and_outcome(memory, "rec1", "XAUUSD",
                       T0, T0 + timedelta(hours=1), pnl=120.0)
    out = chart_annotations(runs, memory, "XAUUSD")

    spans = {v["run_id"]: v["span"] for v in out["runs"]}
    assert spans["r1"]["reason"] == "closed"
    assert spans["r1"]["to"] == int((T0 + timedelta(hours=1)).timestamp())
    assert spans["r2"]["reason"] == "superseded"
    assert spans["r2"]["to"] == spans["r3"]["from"]
    assert spans["r3"] == {"from": int((T0 + timedelta(hours=4)).timestamp()),
                           "to": None, "reason": "open"}

    fill = out["fills"][0]
    assert fill["run_id"] == "r1" and fill["link"] == "exact"
    assert fill["pnl"] == 120.0 and fill["won"] is True


def test_rejected_and_hold_runs_have_no_geometry():
    out = chart_annotations(
        [
            _run("rj", T0, rejection={"stage": "event_gate"}),
            _run("rh", T0 + timedelta(hours=1), rec=_rec("h1", action="HOLD")),
        ],
        ProMemory(), "XAUUSD",
    )
    by_id = {v["run_id"]: v for v in out["runs"]}
    assert by_id["rj"]["geometry"] is None
    assert by_id["rj"]["rejected_at"] == "event_gate"
    assert by_id["rj"]["span"] is None
    assert by_id["rh"]["geometry"] is None
    assert by_id["rh"]["action"] == "HOLD"


def test_inferred_link_for_legacy_records_is_labeled():
    memory = ProMemory()
    # legacy TRADE without recommendation_id: only time-window inference
    trade = memory._add(MemoryRecord(
        kind=MemoryKind.TRADE, text="legacy", symbol="XAUUSD",
        payload={"entry_price": 4000.0},
        event_time=T0 + timedelta(minutes=10),
    ))
    memory._add(MemoryRecord(
        kind=MemoryKind.OUTCOME, text="legacy outcome", symbol="XAUUSD",
        ref_id=trade.id,
        payload={"pnl": -50.0, "won": False,
                 "closed_at": (T0 + timedelta(hours=1)).isoformat()},
        event_time=T0 + timedelta(hours=1),
    ))
    out = chart_annotations([_run("r1", T0, rec=_rec("recX"))],
                            memory, "XAUUSD")
    fill = out["fills"][0]
    assert fill["run_id"] == "r1"
    assert fill["link"] == "inferred"


def test_retro_outcomes_and_other_symbols_excluded():
    memory = ProMemory()
    _trade_and_outcome(memory, "rec1", "XAUUSD", T0,
                       T0 + timedelta(hours=1), pnl=10.0, mode="retro")
    _trade_and_outcome(memory, "rec2", "BTC-USD", T0,
                       T0 + timedelta(hours=1), pnl=10.0)
    out = chart_annotations(
        [_run("r1", T0, rec=_rec("rec1")),
         _run("rb", T0, symbol="BTC-USD", rec=_rec("rec2"))],
        memory, "XAUUSD",
    )
    assert out["fills"] == []
    assert [v["run_id"] for v in out["runs"]] == ["r1"]


def test_empty_history():
    out = chart_annotations([], ProMemory(), "XAUUSD",
                            cadence_seconds=1800.0)
    assert out == {"symbol": "XAUUSD", "cadence_seconds": 1800.0,
                   "runs": [], "fills": []}
