"""Tests for deterministic Reflexion/Macro outcome back-fill."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from tradingagents.memory.macro_memory import MacroMemory
from tradingagents.memory.reflexion import ReflexionMemory


def _stock_csv(rows: list[tuple[str, float]]) -> str:
    body = "\n".join(f"{date},1,1,1,{close},100" for date, close in rows)
    return "# comment\nDate,Open,High,Low,Close,Volume\n" + body


def test_pending_selection_uses_horizon_and_skips_skip_decisions(tmp_path):
    from tradingagents.memory.reflexion_backfill import select_pending_reflexion_records

    mem = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    mem.record_decision("AAPL", "2026-04-01", "BUY", "old")
    mem.record_decision("MSFT", "2026-04-05", "BUY", "too new")
    mem.record_decision("TSLA", "2026-04-01", "SKIP", "not evaluated")
    mem.record_outcome("AAPL", "2026-04-01", {"already": True})
    mem.record_decision("NVDA", "2026-04-01", "SELL", "pending")

    pending = select_pending_reflexion_records(
        mem,
        evaluation_date="2026-04-07",
        horizon_days=5,
        batch_size=10,
    )

    assert [rec["ticker"] for rec in pending] == ["NVDA"]


def test_reflexion_evaluation_parses_prices_and_scores_buy():
    from tradingagents.memory.reflexion_backfill import evaluate_reflexion_record

    outcome = evaluate_reflexion_record(
        {
            "ticker": "AAPL",
            "decision_date": "2026-04-01",
            "decision": "BUY",
        },
        evaluation_date="2026-04-06",
        price_loader=lambda ticker, start, end: _stock_csv(
            [("2026-04-01", 100.0), ("2026-04-06", 102.0)]
        ),
    )

    assert outcome.outcome == {
        "evaluation_date": "2026-04-06",
        "price_at_decision": 100.0,
        "price_at_evaluation": 102.0,
        "price_change_pct": pytest.approx(2.0),
        "correct": True,
    }
    assert outcome.skip_reason is None


def test_reflexion_evaluation_requires_exact_decision_endpoint():
    from tradingagents.memory.reflexion_backfill import evaluate_reflexion_record

    outcome = evaluate_reflexion_record(
        {
            "ticker": "AAPL",
            "decision_date": "2026-04-01",
            "decision": "BUY",
        },
        evaluation_date="2026-04-06",
        price_loader=lambda ticker, start, end: _stock_csv(
            [("2026-04-02", 100.0), ("2026-04-06", 102.0)]
        ),
    )

    assert outcome.outcome is None
    assert "missing endpoint price rows" in outcome.skip_reason


def test_reflexion_evaluation_requires_exact_evaluation_endpoint():
    from tradingagents.memory.reflexion_backfill import evaluate_reflexion_record

    outcome = evaluate_reflexion_record(
        {
            "ticker": "AAPL",
            "decision_date": "2026-04-01",
            "decision": "BUY",
        },
        evaluation_date="2026-04-06",
        price_loader=lambda ticker, start, end: _stock_csv(
            [("2026-04-01", 100.0), ("2026-04-05", 102.0)]
        ),
    )

    assert outcome.outcome is None
    assert "missing endpoint price rows" in outcome.skip_reason


def test_backfill_dry_run_does_not_write_outcome(tmp_path):
    from tradingagents.memory.reflexion_backfill import run_backfill

    reflexion_path = tmp_path / "reflexion.json"
    macro_path = tmp_path / "macro.json"
    mem = ReflexionMemory(fallback_path=reflexion_path)
    mem.record_decision("AAPL", "2026-04-01", "BUY", "old")

    result = run_backfill(
        config={
            "mongo_uri": None,
            "mongo_db": "tradingagents",
            "reflexion_evaluation_horizon_days": 5,
            "macro_evaluation_horizon_days": 21,
            "reflexion_backfill_batch_size": 100,
            "reflexion_fallback_path": reflexion_path,
            "macro_memory_fallback_path": macro_path,
        },
        evaluation_date="2026-04-07",
        dry_run=True,
        price_loader=lambda ticker, start, end: _stock_csv(
            [("2026-04-01", 100.0), ("2026-04-07", 103.0)]
        ),
    )

    assert result.reflexion_evaluated == 1
    assert result.reflexion_updated == 0
    records = json.loads(reflexion_path.read_text())
    assert records[0]["outcome"] is None


def test_macro_evaluation_uses_vix_and_sector_proxy_returns():
    from tradingagents.memory.reflexion_backfill import evaluate_macro_record

    data = {
        "^VIX": _stock_csv([("2026-04-01", 20.0), ("2026-04-22", 22.0)]),
        "XLY": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 106.0)]),
        "XLI": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 104.0)]),
        "XLP": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 101.0)]),
        "XLU": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 100.0)]),
    }

    result = evaluate_macro_record(
        {
            "regime_date": "2026-04-01",
            "macro_call": "risk-on",
            "run_id": "run-1",
        },
        evaluation_date="2026-04-22",
        price_loader=lambda ticker, start, end: data[ticker],
    )

    assert result.outcome is not None
    assert result.outcome["evaluation_date"] == "2026-04-22"
    assert result.outcome["vix_at_evaluation"] == 22.0
    assert result.outcome["vix_delta_pct"] == pytest.approx(10.0)
    assert result.outcome["regime_confirmed"] is True
    assert result.skip_reason is None


def test_macro_risk_off_evaluation_is_exclusive_when_risk_on_conditions_hold():
    from tradingagents.memory.reflexion_backfill import evaluate_macro_record

    data = {
        "^VIX": _stock_csv([("2026-04-01", 20.0), ("2026-04-22", 22.0)]),
        "XLY": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 106.0)]),
        "XLI": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 104.0)]),
        "XLP": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 101.0)]),
        "XLU": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 100.0)]),
    }

    result = evaluate_macro_record(
        {
            "regime_date": "2026-04-01",
            "macro_call": "risk-off",
            "run_id": "run-1",
        },
        evaluation_date="2026-04-22",
        price_loader=lambda ticker, start, end: data[ticker],
    )

    assert result.outcome is not None
    assert result.outcome["regime_confirmed"] is False


def test_macro_evaluation_requires_exact_regime_and_evaluation_endpoints():
    from tradingagents.memory.reflexion_backfill import evaluate_macro_record

    data = {
        "^VIX": _stock_csv([("2026-04-02", 20.0), ("2026-04-22", 22.0)]),
        "XLY": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 106.0)]),
        "XLI": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 104.0)]),
        "XLP": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 101.0)]),
        "XLU": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 100.0)]),
    }

    result = evaluate_macro_record(
        {
            "regime_date": "2026-04-01",
            "macro_call": "risk-on",
            "run_id": "run-1",
        },
        evaluation_date="2026-04-22",
        price_loader=lambda ticker, start, end: data[ticker],
    )

    assert result.outcome is None
    assert "missing endpoint price rows" in result.skip_reason


def test_price_parser_rejects_blank_date_header():
    from tradingagents.memory.reflexion_backfill import evaluate_reflexion_record

    bad_csv = " ,Open,High,Low,Close,Volume\n2026-04-01,1,1,1,100,100\n2026-04-06,1,1,1,102,100"
    result = evaluate_reflexion_record(
        {
            "ticker": "AAPL",
            "decision_date": "2026-04-01",
            "decision": "BUY",
        },
        evaluation_date="2026-04-06",
        price_loader=lambda ticker, start, end: bad_csv,
    )

    assert result.outcome is None
    assert "missing date or close column" in result.skip_reason


def test_macro_backfill_passes_run_id_when_recording_outcome(tmp_path):
    from tradingagents.memory.reflexion_backfill import run_backfill

    macro_path = tmp_path / "macro.json"
    reflexion_path = tmp_path / "reflexion.json"
    mem = MacroMemory(fallback_path=macro_path)
    mem.record_macro_state("2026-04-01", 20.0, "risk-off", "old", [], run_id="run-1")
    mem.record_macro_state("2026-04-01", 20.0, "risk-on", "old", [], run_id="run-2")

    data = {
        "^VIX": _stock_csv([("2026-04-01", 20.0), ("2026-04-22", 22.0)]),
        "XLY": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 99.0)]),
        "XLI": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 98.0)]),
        "XLP": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 101.0)]),
        "XLU": _stock_csv([("2026-04-01", 100.0), ("2026-04-22", 102.0)]),
    }

    result = run_backfill(
        config={
            "mongo_uri": None,
            "mongo_db": "tradingagents",
            "reflexion_evaluation_horizon_days": 5,
            "macro_evaluation_horizon_days": 21,
            "reflexion_backfill_batch_size": 1,
            "reflexion_fallback_path": reflexion_path,
            "macro_memory_fallback_path": macro_path,
        },
        evaluation_date="2026-04-22",
        dry_run=False,
        price_loader=lambda ticker, start, end: data[ticker],
    )

    assert result.macro_updated == 1
    records = sorted(json.loads(macro_path.read_text()), key=lambda rec: rec["run_id"])
    assert records[0]["outcome"] is not None
    assert records[1]["outcome"] is None


def test_cli_reflexion_commands_are_registered_and_invoke_core(monkeypatch):
    import cli.main as main

    calls: list[tuple[str, bool]] = []

    class Result:
        reflexion_pending = 0
        reflexion_evaluated = 0
        reflexion_updated = 0
        reflexion_skipped = 0
        macro_pending = 0
        macro_evaluated = 0
        macro_updated = 0
        macro_skipped = 0
        skip_reasons = []

    def fake_run_backfill(*, evaluation_date, dry_run, config):
        calls.append((evaluation_date, dry_run))
        return Result()

    monkeypatch.setattr(main, "run_reflexion_backfill", fake_run_backfill)
    result = CliRunner().invoke(
        main.app, ["reflexion", "backfill", "--date", "2026-04-07", "--dry-run"]
    )

    assert result.exit_code == 0
    assert calls == [("2026-04-07", True)]


def test_reflexion_backfill_config_defaults_and_env_overrides():
    from tradingagents.default_config import build_default_config

    defaults = build_default_config(load_dotenv=False, environ={})
    assert defaults["reflexion_evaluation_horizon_days"] == 5
    assert defaults["macro_evaluation_horizon_days"] == 21
    assert defaults["reflexion_backfill_batch_size"] == 100

    overridden = build_default_config(
        load_dotenv=False,
        environ={
            "TRADINGAGENTS_REFLEXION_EVALUATION_HORIZON_DAYS": "8",
            "TRADINGAGENTS_MACRO_EVALUATION_HORIZON_DAYS": "34",
            "TRADINGAGENTS_REFLEXION_BACKFILL_BATCH_SIZE": "12",
        },
    )
    assert overridden["reflexion_evaluation_horizon_days"] == 8
    assert overridden["macro_evaluation_horizon_days"] == 34
    assert overridden["reflexion_backfill_batch_size"] == 12
