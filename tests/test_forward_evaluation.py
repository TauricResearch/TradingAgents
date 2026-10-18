"""Prospective signal evaluation, using a fake clock and synthetic prices only."""

import json
import math
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from statistics import mean, stdev

import pytest

from tradingagents.evaluation import forward
from tradingagents.evaluation.forward import (
    EvaluationConfig,
    ForwardEvaluation,
    ModelDeclaration,
    PriceBar,
)

pytestmark = pytest.mark.unit
DAY = datetime(2026, 10, 1, 21, tzinfo=UTC)
RUN_CONFIG = {"deep_think_llm": "test-deep", "quick_think_llm": "test-quick"}
MODELS = [
    ModelDeclaration("test-deep", "offline", "2026-01-01"),
    ModelDeclaration("test-quick", "offline", None),
]


@pytest.fixture
def clock(monkeypatch):
    current = [DAY]
    monkeypatch.setattr(forward, "_utcnow", lambda: current[0])
    return current


def history(day=DAY, falling=False):
    return [
        PriceBar(
            day.replace(hour=9) - timedelta(days=21 - i),
            100,
            day.replace(hour=16) - timedelta(days=21 - i),
            122 - i if falling else 100 + i,
        )
        for i in range(22)
    ]


def make_ledger(tmp_path, **kwargs):
    return ForwardEvaluation.create(
        tmp_path / "forward.sqlite",
        EvaluationConfig(tickers=("AAA",), **kwargs),
        MODELS,
        RUN_CONFIG,
    )


def record(ledger, day=DAY, action="Buy", bars=None, ticker="AAA", **kwargs):
    return ledger.record(
        ticker,
        day.date().isoformat(),
        action,
        day.replace(hour=9) + timedelta(days=1),
        lambda _: history(day) if bars is None else bars,
        RUN_CONFIG,
        **kwargs,
    )


def outcome(day=DAY, entry=100, exit_=110, horizon=1):
    return [
        PriceBar(day.replace(hour=9) + timedelta(days=1), entry),
        *[PriceBar(day.replace(hour=9) + timedelta(days=1 + i), entry) for i in range(1, horizon)],
        PriceBar(day.replace(hour=9) + timedelta(days=1 + horizon), exit_),
    ]


@pytest.mark.parametrize("offset,retrospective", [(-1, False), (0, True), (1, True)])
def test_retrospective_guard_and_wall_clock(tmp_path, clock, offset, retrospective):
    ledger = make_ledger(tmp_path)
    entry = outcome()[0].open_at
    clock[0] = entry + timedelta(seconds=offset)
    decision = record(ledger)
    assert decision["retrospective"] is retrospective
    assert decision["recorded_at"] == clock[0].isoformat()
    assert decision["models"] == [forward.asdict(m) for m in MODELS]
    assert len(decision["config_fingerprint"]) == 64
    clock[0] = DAY + timedelta(days=4)
    result = ledger.score(lambda _: outcome())
    assert result["retrospective_decisions"] == int(retrospective)
    assert result["metrics"]["signal"]["sessions"] == int(not retrospective)


def test_slow_history_fetch_cannot_backdate_record(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    entry = outcome()[0].open_at
    clock[0] = entry - timedelta(seconds=1)

    def slow_prices(_):
        clock[0] = entry + timedelta(seconds=1)
        return history()

    decision = ledger.record("AAA", DAY.date().isoformat(), "Buy", entry, slow_prices, RUN_CONFIG)
    assert decision["retrospective"]
    assert decision["recorded_at"] == clock[0].isoformat()


def test_lazy_fills_ignore_future_and_past_opens_and_never_reprice(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    record(ledger)
    bars = [*history(), *outcome()]
    assert ledger.score(lambda _: bars)["metrics"]["signal"]["sessions"] == 0
    assert not any(kind in ("entry", "exit") for kind, _ in ledger._events())
    clock[0] = outcome()[0].open_at
    ledger.score(lambda _: bars)
    events = ledger._events()
    key = next(key for kind, key in events if kind == "decision")
    assert events[("entry", key)]["price"] == 100
    assert ("exit", key) not in events
    clock[0] = DAY + timedelta(days=3)
    revised = [*history(), *outcome(entry=999, exit_=110)]
    result = ledger.score(lambda _: revised)
    assert result["metrics"]["signal"]["returns"] == pytest.approx([0.1 - 0.0004])
    ledger.score(lambda _: outcome(entry=5, exit_=5))
    assert ledger._events()[("entry", key)] == events[("entry", key)]
    assert ledger._events()[("exit", key)]["price"] == 110


def test_missing_entry_does_not_shift_fill(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    record(ledger)
    clock[0] = DAY + timedelta(days=5)
    result = ledger.score(lambda _: outcome()[1:])
    assert result["pending_sessions"] == [DAY.date().isoformat()]
    assert not any(kind == "entry" for kind, _ in ledger._events())


def test_skipping_actual_next_open_is_excluded(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    ledger.record(
        "AAA", DAY.date().isoformat(), "Buy", outcome()[1].open_at, lambda _: history(), RUN_CONFIG
    )
    clock[0] = DAY + timedelta(days=4)
    result = ledger.score(lambda _: outcome())
    assert result["invalid_decisions"] == 1
    assert result["unscored_sessions"] == [DAY.date().isoformat()]
    assert result["metrics"]["signal"]["sessions"] == 0


def test_horizon_counts_sessions_not_calendar_days(tmp_path, clock):
    ledger = make_ledger(tmp_path, horizon_sessions=2)
    record(ledger)
    entry = outcome()[0].open_at
    # A weekend-sized gap is still just one intervening session.
    bars = [
        PriceBar(entry, 100),
        PriceBar(entry + timedelta(days=3), 150),
        PriceBar(entry + timedelta(days=4), 110),
    ]
    clock[0] = entry + timedelta(days=3)
    assert ledger.score(lambda _: bars)["metrics"]["signal"]["sessions"] == 0
    clock[0] = entry + timedelta(days=4)
    assert ledger.score(lambda _: bars)["metrics"]["signal"]["returns"] == pytest.approx([0.0996])


@pytest.mark.parametrize(
    "action,direction",
    [("Buy", 1), ("Overweight", 1), ("Hold", 0), ("Underweight", -1), ("Sell", -1)],
)
def test_ratings_baselines_costs_and_hit_rate(tmp_path, clock, action, direction):
    ledger = make_ledger(tmp_path, cost_bps_per_side=10)
    bars = [*history(falling=True), *outcome()]
    record(ledger, action=action, bars=bars, size=500, confidence=0.7)
    # Future closes in the supplied series cannot set the momentum sign.
    assert (
        next(d for (kind, _), d in ledger._events().items() if kind == "decision")["momentum_21"]
        < 0
    )
    clock[0] = DAY + timedelta(days=4)
    metrics = ledger.score(lambda _: bars)["metrics"]
    assert metrics["signal"]["returns"] == pytest.approx(
        [direction * 0.1 - 0.002 if direction else 0]
    )
    assert metrics["equal_weight_long"]["returns"] == pytest.approx([0.098])
    assert metrics["momentum_21"]["returns"] == pytest.approx([-0.102])
    assert metrics["signal"]["hit_rate"] == (float(direction > 0) if direction else None)
    assert metrics["equal_weight_long"]["hit_rate"] == 1
    assert metrics["momentum_21"]["hit_rate"] == 0


def test_baseline_uses_only_completed_closes_at_recording(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    future = PriceBar(DAY.replace(hour=20), 100, DAY.replace(hour=22), 1)
    decision = record(ledger, bars=[*history(), future])
    assert decision["momentum_21"] == pytest.approx(0.21)


def test_zero_momentum_flat_baseline_pays_no_cost(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    record(ledger, bars=[replace(b, close=100) for b in history()])
    clock[0] = DAY + timedelta(days=4)
    metrics = ledger.score(lambda _: outcome())["metrics"]
    assert metrics["momentum_21"]["returns"] == [0]
    assert metrics["momentum_21"]["positions"] == 0


@pytest.mark.parametrize("action,bars", [("REVIEW", history()), ("Buy", history()[:21])])
def test_unknown_rating_or_momentum_is_unscored_not_flat(tmp_path, clock, action, bars):
    ledger = make_ledger(tmp_path)
    record(ledger, action=action, bars=bars)
    clock[0] = DAY + timedelta(days=4)
    result = ledger.score(lambda _: outcome())
    assert result["unscored_sessions"] == [DAY.date().isoformat()]
    assert all(s["sessions"] == 0 for s in result["metrics"].values())


def test_full_universe_same_days_and_equal_weights_including_hold(tmp_path, clock):
    ledger = ForwardEvaluation.create(
        tmp_path / "two.sqlite", EvaluationConfig(("AAA", "BBB")), MODELS, RUN_CONFIG
    )
    record(ledger, action="Hold", ticker="AAA")
    clock[0] = DAY + timedelta(days=4)
    assert ledger.score(lambda _: outcome())["metrics"]["signal"]["sessions"] == 0
    clock[0] = DAY
    record(ledger, action="Buy", ticker="BBB")
    clock[0] = DAY + timedelta(days=4)
    result = ledger.score(lambda _: outcome())
    assert result["metrics"]["signal"]["returns"] == pytest.approx([0.0996 / 2])
    assert all(s["sessions"] == 1 for s in result["metrics"].values())


def experiment(tmp_path, clock, returns, **config):
    ledger = make_ledger(tmp_path, **config)
    bars = []
    price = 100
    for i, ret in enumerate(returns):
        day = DAY + timedelta(days=i)
        clock[0] = day
        record(ledger, day, "Sell" if ret < 0 else "Buy")
        bars.append(PriceBar(outcome(day)[0].open_at, price))
        price *= 1 + ret
    bars.append(PriceBar(outcome(DAY + timedelta(days=len(returns) - 1))[1].open_at, price))
    clock[0] = DAY + timedelta(days=len(returns) + 2)
    return ledger, bars


def test_preregistered_verdict_minimum_and_baselines(tmp_path, clock):
    ledger, bars = experiment(tmp_path, clock, [-0.03, 0.02, -0.01, 0.04], min_sessions=4)
    early = ledger.score(lambda _: bars[:-1])
    assert early["verdict"] == "insufficient"
    result = ledger.score(lambda _: bars)
    assert result["verdict"] == "passed"
    expected = [0.0296, 0.0196, 0.0096, 0.0396]
    assert result["metrics"]["signal"]["sharpe"] == pytest.approx(
        mean(expected) / stdev(expected) * math.sqrt(252)
    )
    assert result["metrics"]["signal"]["sharpe"] > result["metrics"]["equal_weight_long"]["sharpe"]
    assert result["metrics"]["signal"]["sharpe"] > result["metrics"]["momentum_21"]["sharpe"]
    assert ForwardEvaluation(ledger.path).summary()["verdict"] == "passed"


def test_default_rule_requires_40_completed_sessions(tmp_path, clock):
    ledger, bars = experiment(tmp_path, clock, [-0.03, 0.02, -0.01, 0.04] * 10)
    early = ledger.score(lambda _: bars[:-1])
    assert early["metrics"]["signal"]["sessions"] == 39
    assert early["verdict"] == "insufficient"
    result = ledger.score(lambda _: bars)
    assert result["verdict"] == "passed"
    assert len(result["verdict_sessions"]) == 40
    assert result["verdict_sharpes"]["signal"] >= 1.0


@pytest.mark.parametrize(
    "rule,expected",
    [({}, "failed"), ({"must_beat_baselines": False}, "passed"), ({"min_sharpe": 1000}, "failed")],
)
def test_verdict_requires_strictly_beating_both_and_threshold(tmp_path, clock, rule, expected):
    ledger, bars = experiment(tmp_path, clock, [0.01, 0.02, 0.03], min_sessions=3, **rule)
    assert ledger.score(lambda _: bars)["verdict"] == expected


def test_undefined_baseline_sharpe_cannot_count_as_a_win(tmp_path, clock):
    ledger, bars = experiment(tmp_path, clock, [-0.01, 0.02], min_sessions=2)
    # This is a separate experiment whose preregistered momentum baseline is flat.
    flat = make_ledger(tmp_path / "flat", min_sessions=2)
    for i in range(2):
        day = DAY + timedelta(days=i)
        clock[0] = day
        record(
            flat,
            day,
            "Sell" if i == 0 else "Buy",
            bars=[replace(b, close=100) for b in history(day)],
        )
    clock[0] = DAY + timedelta(days=5)
    assert ledger.score(lambda _: bars)["verdict"] == "passed"
    assert flat.score(lambda _: bars)["verdict"] == "failed"


def test_verdict_sample_does_not_expand_to_a_later_winning_endpoint(tmp_path, clock):
    ledger, bars = experiment(tmp_path, clock, [0.01, 0.02, -0.5], min_sessions=2)
    assert ledger.score(lambda _: bars)["verdict"] == "failed"
    assert len(ledger.summary()["verdict_sessions"]) == 2
    assert ledger.summary()["metrics"]["signal"]["sessions"] == 3


def test_pending_earlier_session_blocks_verdict(tmp_path, clock):
    ledger, bars = experiment(tmp_path, clock, [-0.03, 0.02, -0.01], min_sessions=2)
    clock[0] = DAY - timedelta(days=1)
    record(ledger, ticker="AAA", day=DAY - timedelta(days=1))
    clock[0] = DAY + timedelta(days=6)
    assert ledger.score(lambda _: bars)["verdict"] == "insufficient"


def test_overlapping_horizons_are_descriptive_not_verdict_samples(tmp_path, clock):
    ledger, bars = experiment(
        tmp_path, clock, [-0.03, 0.02, -0.01, 0.04], min_sessions=2, horizon_sessions=2
    )
    result = ledger.score(lambda _: bars)
    assert result["overlapping_windows"]
    assert result["verdict"] == "insufficient"


def test_protocol_and_decisions_append_only_and_config_change_rejected(tmp_path, clock):
    ledger = make_ledger(tmp_path)
    record(ledger)
    with pytest.raises(sqlite3.IntegrityError):
        record(ledger, action="Sell")
    with pytest.raises(FileExistsError):
        make_ledger(tmp_path)
    with (
        sqlite3.connect(ledger.path) as db,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        db.execute("DELETE FROM events")
    with (
        sqlite3.connect(ledger.path) as db,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        db.execute("UPDATE events SET payload = '{}' WHERE kind = 'protocol'")
    with pytest.raises(ValueError, match="settings changed"):
        ledger.record(
            "AAA",
            DAY.date().isoformat(),
            "Buy",
            outcome()[0].open_at,
            lambda _: history(),
            {"different": "model"},
        )


@pytest.mark.parametrize(
    "config",
    [
        {"min_sessions": 1},
        {"horizon_sessions": 0},
        {"cost_bps_per_side": -1},
        {"min_sharpe": float("nan")},
        {"tickers": ["AAA", "AAA"]},
        {"min_sessions": 2.5},
    ],
)
def test_invalid_protocol_rejected(config):
    with pytest.raises(ValueError):
        EvaluationConfig(**{"tickers": ("AAA",), **config})


def test_naive_timestamps_and_duplicate_prices_rejected(tmp_path, clock):
    with pytest.raises(ValueError, match="timezone"):
        PriceBar(DAY.replace(tzinfo=None), 100)
    ledger = make_ledger(tmp_path)
    with pytest.raises(ValueError, match="duplicate"):
        record(ledger, bars=[history()[0], history()[0]])


def test_thin_cli_round_trip(tmp_path, clock, capsys):
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "evaluation": {"tickers": ["AAA"]},
                "models": [forward.asdict(m) for m in MODELS],
                "run_config": RUN_CONFIG,
            }
        )
    )
    ledger = str(tmp_path / "cli.sqlite")
    forward.main(["init", ledger, "--protocol", str(protocol)])
    assert json.loads(capsys.readouterr().out)["version"] == 1
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "AAA": [
                    {
                        "open_at": b.open_at.isoformat(),
                        "open": b.open,
                        "close_at": b.close_at.isoformat() if b.close_at else None,
                        "close": b.close,
                    }
                    for b in [*history(), *outcome()]
                ]
            }
        )
    )
    decision = tmp_path / "decision.json"
    decision.write_text(
        json.dumps(
            {
                "ticker": "AAA",
                "decision_date": DAY.date().isoformat(),
                "action": "Buy",
                "next_open": outcome()[0].open_at.isoformat(),
                "run_config": RUN_CONFIG,
            }
        )
    )
    forward.main(["record", ledger, "--decision", str(decision), "--prices", str(prices)])
    assert not json.loads(capsys.readouterr().out)["retrospective"]
    clock[0] = DAY + timedelta(days=4)
    forward.main(["score", ledger, "--prices", str(prices)])
    assert json.loads(capsys.readouterr().out)["metrics"]["signal"]["sessions"] == 1
    forward.main(["summary", ledger])
    assert json.loads(capsys.readouterr().out)["verdict"] == "insufficient"
