"""Backtest execution timing, costs, and safety checks."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents import backtest


def _prices(opens, closes):
    dates = pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07"])
    return pd.DataFrame({"Open": opens, "Close": closes}, index=dates)


@pytest.mark.unit
def test_signal_enters_next_session_and_applies_round_trip_costs():
    prices = _prices([90, 100, 105, 111], [95, 101, 110, 112])
    benchmark = _prices([190, 200, 205, 211], [195, 202, 210, 212])

    result = backtest.evaluate_signal(
        ticker="NVDA",
        decision_date="2026-07-01",
        action="Buy",
        prices=prices,
        benchmark_prices=benchmark,
        holding_sessions=2,
        cost_bps_per_side=5,
    )

    assert result.entry_date == "2026-07-02"
    assert result.exit_date == "2026-07-06"
    assert result.asset_return == pytest.approx(0.10)
    assert result.benchmark_return == pytest.approx(0.05)
    assert result.net_return == pytest.approx(0.099)
    assert result.excess_return == pytest.approx(0.049)


@pytest.mark.unit
def test_sell_signal_is_short_and_hold_has_no_cost():
    prices = _prices([90, 100, 105, 111], [95, 101, 110, 112])
    benchmark = _prices([190, 200, 205, 211], [195, 202, 210, 212])
    sell = backtest.evaluate_signal(
        ticker="NVDA", decision_date="2026-07-01", action="Sell",
        prices=prices, benchmark_prices=benchmark, holding_sessions=2,
    )
    hold = backtest.evaluate_signal(
        ticker="NVDA", decision_date="2026-07-01", action="Hold",
        prices=prices, benchmark_prices=benchmark, holding_sessions=2,
    )
    assert sell.net_return == pytest.approx(-0.101)
    assert hold.net_return == 0.0


@pytest.mark.unit
def test_unresolved_signal_does_not_guess_future_prices():
    prices = _prices([90, 100, 105, 111], [95, 101, 110, 112])
    result = backtest.evaluate_signal(
        ticker="NVDA", decision_date="2026-07-07", action="Buy",
        prices=prices, benchmark_prices=prices, holding_sessions=2,
    )
    assert result.entry_date is None
    assert result.net_return is None


@pytest.mark.unit
def test_cli_blocks_non_point_in_time_fundamentals():
    with pytest.raises(SystemExit):
        backtest.main([
            "--tickers", "NVDA", "--start", "2026-07-01", "--end", "2026-07-01",
            "--analysts", "market,fundamentals", "--dry-run",
        ])


@pytest.mark.unit
def test_global_topics_only_blocks_ticker_specific_social_analyst():
    with pytest.raises(SystemExit):
        backtest.main([
            "--tickers", "NVDA", "--start", "2026-07-01", "--end", "2026-07-01",
            "--analysts", "market,social,news", "--global-topics-only", "--dry-run",
        ])


@pytest.mark.unit
def test_configuration_fingerprint_is_stable_and_sensitive():
    first = backtest._fingerprint({"model": "a", "temperature": 0})
    reordered = backtest._fingerprint({"temperature": 0, "model": "a"})
    changed = backtest._fingerprint({"model": "b", "temperature": 0})
    assert first == reordered
    assert first != changed


@pytest.mark.unit
def test_decision_code_fingerprint_includes_media_feature_implementation(monkeypatch):
    original = backtest.Path.read_bytes
    initial = backtest._decision_code_fingerprint()

    def changed_bytes(path):
        content = original(path)
        return content + b"# changed" if path.name == "media_features.py" else content

    monkeypatch.setattr(backtest.Path, "read_bytes", changed_bytes)

    assert backtest._decision_code_fingerprint() != initial


@pytest.mark.unit
def test_signal_manifest_includes_effective_decision_config(monkeypatch):
    args = SimpleNamespace(db="postgresql://u:p@db.example/research")
    initial = backtest._signal_manifest(args, ("market", "news"))

    monkeypatch.setitem(backtest.DEFAULT_CONFIG, "global_news_article_limit", 99)

    changed = backtest._signal_manifest(args, ("market", "news"))
    assert changed["decision_config"]["global_news_article_limit"] == 99
    assert backtest._fingerprint(changed) != backtest._fingerprint(initial)


@pytest.mark.unit
def test_signal_manifest_never_persists_backend_credentials(monkeypatch):
    secret = "must-not-enter-artifacts"
    monkeypatch.setitem(
        backtest.DEFAULT_CONFIG,
        "backend_url",
        f"https://user:password@llm.invalid/v1/{secret}?token={secret}",
    )

    manifest = backtest._signal_manifest(
        SimpleNamespace(db="sqlite:///research.db"), ("market", "news")
    )

    serialized = json.dumps(manifest)
    assert secret not in serialized
    assert "password" not in serialized
    assert "backend_url" not in manifest["decision_config"]
    assert manifest["decision_config"]["backend_id"]


@pytest.mark.unit
def test_signal_manifest_rejects_untrusted_provider_text(monkeypatch):
    monkeypatch.setitem(backtest.DEFAULT_CONFIG, "llm_provider", "provider\nsecret")

    with pytest.raises(ValueError, match="unsupported LLM provider"):
        backtest._signal_manifest(SimpleNamespace(db="sqlite:///research.db"), ("news",))


@pytest.mark.unit
def test_operational_build_change_does_not_fork_signal_identity(monkeypatch):
    args = SimpleNamespace(db="postgresql://u:p@db.example/research")
    initial = backtest._signal_manifest(args, ("market", "news"))
    changed = {**initial, "build_id": "different-container"}
    assert backtest._signal_fingerprint(changed) == backtest._signal_fingerprint(initial)


@pytest.mark.unit
def test_database_identity_ignores_rotated_credentials():
    first = backtest._database_identity("postgresql+psycopg://old:one@db.example:5432/research")
    rotated = backtest._database_identity("postgresql+psycopg://new:two@db.example:5432/research")
    other_database = backtest._database_identity(
        "postgresql+psycopg://new:two@db.example:5432/other"
    )
    assert first == rotated
    assert first != other_database


@pytest.mark.unit
def test_ticker_mask_uses_stable_nonsemantic_aliases():
    assert backtest._identity_aliases(["NVDA", "AAPL"], "ticker-mask") == {
        "AAPL": "ASSET_001",
        "NVDA": "ASSET_002",
    }
    assert backtest._identity_aliases(["NVDA"], "none") == {"NVDA": "NVDA"}


@pytest.mark.unit
def test_cached_decision_outcomes_are_recomputed_for_current_horizon_and_cost():
    frame = _prices([90, 100, 105, 111], [95, 101, 110, 112])
    records = [{
        "ticker": "NVDA", "decision_date": "2026-07-01", "action": "Buy",
        "net_return": 999.0, "holding_sessions": 99,
    }]

    evaluated = backtest._reevaluate_records(
        records,
        prices={"NVDA": frame},
        benchmark_prices=frame,
        holding_sessions=2,
        cost_bps_per_side=10,
    )

    assert evaluated[0]["holding_sessions"] == 2
    assert evaluated[0]["net_return"] == pytest.approx(0.098)


@pytest.mark.unit
def test_jsonl_resume_fails_closed_on_partial_crash_line(tmp_path):
    path = tmp_path / "signals.jsonl"
    path.write_text('{"ticker":"A","decision_date":"2026-07-01"}\n{"ticker":',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON on line 2"):
        backtest._load_records(path)


@pytest.mark.unit
def test_append_jsonl_flushes_one_complete_record(tmp_path):
    path = tmp_path / "signals.jsonl"
    row = {"ticker": "A", "decision_date": "2026-07-01"}

    backtest._append_jsonl(path, row)

    assert backtest._load_records(path) == [row]
    assert path.read_bytes().endswith(b"\n")


@pytest.mark.unit
def test_cached_signals_can_recalculate_portfolio_without_llm(tmp_path, monkeypatch):
    from tradingagents.dataflows import media_history

    output = tmp_path / "signals.jsonl"
    frame = _prices([90, 100, 105, 111], [95, 101, 110, 112])
    monkeypatch.setattr(backtest, "_load_prices", lambda *args, **kwargs: frame)
    monkeypatch.setattr(backtest, "_signal_manifest", lambda *args: {"test": "manifest"})
    monkeypatch.setattr(
        media_history, "collected_window_fingerprint", lambda *args, **kwargs: "data-v1"
    )
    signal_fingerprint = backtest._fingerprint({"test": "manifest"})
    output.write_text(
        '{"ticker":"NVDA","decision_date":"2026-07-01","action":"Buy",'
        f'"replicate":0,"signal_fingerprint":"{signal_fingerprint}",'
        '"data_fingerprint":"data-v1","net_return":0.01,"excess_return":0.0}\n',
        encoding="utf-8",
    )

    backtest.main([
        "--tickers", "NVDA", "--start", "2026-07-01", "--end", "2026-07-01",
        "--db", "sqlite:///unused.db", "--output", str(output),
        "--max-weight", "1", "--tail-sessions", "1",
    ])

    assert output.with_suffix(".portfolio.json").exists()
    assert output.with_suffix(".equity.csv").exists()
