"""Observation-only research feed ingestion; NEVER access a portfolio.

All tests use in-memory or temporary fake sources and never contact networks,
AI models, or an actual broker.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from tradingagents.paper.autopilot import cli, observe
from tradingagents.paper.conditional import EarningsSnapshot
from tradingagents.paper.engine import Bar


NY = ZoneInfo("America/New_York")


def when(day: str, hour: int, minute: int) -> datetime:
    return datetime.fromisoformat(
        f"{day}T{hour:02d}:{minute:02d}:00"
    ).replace(tzinfo=NY)


def earnings(ticker: str, day: str, stamp: datetime) -> EarningsSnapshot:
    return EarningsSnapshot(
        day, "2026-12-02", "2026-07-25",
        "TWO_SECONDARY_SOURCES_TEST_ONLY", True,
        stamp.astimezone(timezone.utc).isoformat(),
    )


def market_data(day: str):
    return {
        "AAPL": {day: Bar(200.0, 204.0, 199.0, 202.0)},
        "MSFT": {day: Bar(400.0, 405.0, 397.0, 401.0)},
        "SPY": {day: Bar(600.0, 602.0, 595.0, 601.0)},
        "GBPUSD=X": {day: Bar(1.33, 1.34, 1.32, 1.33)},
    }


def prices(symbols, start, end):
    assert set(symbols) == {"AAPL", "MSFT"}
    assert start == end == "2026-10-23"
    return market_data(end), lambda rate_bars, day: (0.75, 0.75)


def test_observation_waits_until_actual_ny_window_without_side_effects(tmp_path):
    result = observe.capture(tmp_path / "research", ["AAPL"], now=when("2026-10-23", 12, 0))
    assert result["status"] == "WAITING_FOR_NY_WINDOW"
    assert result["mode"] == "OBSERVE_ONLY"
    assert result["orders"] == 0
    assert not (tmp_path / "research").exists()


def test_preopen_earnings_capture_is_immutable_and_brokerless(tmp_path):
    root = tmp_path / "research"
    result = observe.capture(
        root, ["AAPL", "MSFT"], now=when("2026-10-23", 9, 10),
        earnings_source=earnings, completion_clock=lambda: when("2026-10-23", 9, 11),
    )
    assert result["phase"] == "preopen"
    assert result["verified"] == ["AAPL", "MSFT"]
    assert result["orders"] == 0
    evidence = root / "calendar" / "2026-10-23" / "preopen.json"
    initial_bytes = evidence.read_bytes()
    second = observe.capture(
        root, ["AAPL", "MSFT"], now=when("2026-10-23", 9, 15),
        earnings_source=lambda *_: (_ for _ in ()).throw(AssertionError("must not re-fetch")),
    )
    assert second["status"] == "ALREADY_CAPTURED"
    assert evidence.read_bytes() == initial_bytes


def test_evening_earnings_records_do_not_authorise_orders(tmp_path):
    root = tmp_path / "research"
    result = observe.capture(
        root, ["AAPL"], now=when("2026-10-23", 17, 12),
        earnings_source=earnings, completion_clock=lambda: when("2026-10-23", 17, 13),
    )
    assert result["phase"] == "preclose"
    assert result["orders"] == 0
    assert (root / "calendar" / "2026-10-23" / "preclose.json").exists()
    assert not (root / "portfolio.json").exists()


def test_completed_market_snapshot_is_source_labelled_and_immutable(tmp_path):
    root = tmp_path / "research"
    result = observe.capture(
        root, ["MSFT", "AAPL"], now=when("2026-10-23", 18, 10),
        prices_source=prices, corporate_guard=lambda names, start, end: None,
    )
    assert result["phase"] == "close"
    assert result["orders"] == 0
    path = root / "market" / "2026-10-23.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["mode"] == "OBSERVE_ONLY"
    assert payload["source"] == "YAHOO_SECONDARY_NOT_EXCHANGE_CERTIFIED"
    assert payload["ohlc_usd"]["AAPL"]["close"] == 202.0
    assert "NVDA" not in payload["ohlc_usd"]
    assert payload["fx_gbp_per_usd_open"] == 0.75
    assert payload["orders"] == []
    original = path.read_bytes()
    second = observe.capture(
        root, ["AAPL", "MSFT"], now=when("2026-10-23", 18, 12),
        prices_source=lambda *_: (_ for _ in ()).throw(AssertionError("source must be immutable")),
    )
    assert second["status"] == "ALREADY_CAPTURED"
    assert path.read_bytes() == original


def test_missing_symbol_blocks_capture_instead_of_inventing_prices(tmp_path):
    root = tmp_path / "research"
    def broken_source(*_):
        data = market_data("2026-10-23")
        data.pop("MSFT")
        return data, lambda fx, day: (0.75, 0.75)
    with pytest.raises(ValueError, match="Missing mandatory source"):
        observe.capture(
            root, ["AAPL", "MSFT"], now=when("2026-10-23", 18, 0),
            prices_source=broken_source, corporate_guard=lambda *_: None,
        )
    assert not (root / "market" / "2026-10-23.json").exists()


def test_bad_ohlc_cannot_be_archived_as_an_approved_daily_candle(tmp_path):
    root = tmp_path / "research"
    def corrupt_source(*_):
        data = market_data("2026-10-23")
        data["AAPL"]["2026-10-23"] = Bar(202.0, 199.0, 201.0, 202.0)
        return data, lambda fx, day: (0.75, 0.75)
    with pytest.raises(ValueError, match="invalid complete"):
        observe.capture(
            root, ["AAPL", "MSFT"], now=when("2026-10-23", 18, 0),
            prices_source=corrupt_source, corporate_guard=lambda *_: None,
        )


def test_corporate_action_blocks_unadjusted_observation(tmp_path):
    def halt(*_):
        raise ValueError("UNMODELLED_CORPORATE_ACTION for AAPL")
    root = tmp_path / "research"
    with pytest.raises(ValueError, match="UNMODELLED_CORPORATE_ACTION"):
        observe.capture(
            root, ["AAPL", "MSFT"], now=when("2026-10-23", 18, 0),
            prices_source=prices, corporate_guard=halt,
        )
    assert not (root / "market" / "2026-10-23.json").exists()


def test_account_or_credential_directory_is_not_an_observation_destination(tmp_path):
    root = tmp_path / "account"
    root.mkdir()
    (root / "portfolio.json").write_text('{"confidential": true}')
    with pytest.raises(ValueError, match="account or credentials"):
        observe.capture(root, ["AAPL"], now=when("2026-10-23", 17, 5),
                        earnings_source=earnings)
    assert (root / "portfolio.json").read_text() == '{"confidential": true}'


def test_account_state_bytes_remain_identical_after_full_observation(tmp_path):
    book = tmp_path / "paper" / "v3_autopilot" / "portfolio.json"
    book.parent.mkdir(parents=True)
    book.write_bytes(b"SIGNED_AND_IMMUTABLE_FAKE_LEDGER")
    observation = tmp_path / "research"
    observe.capture(
        observation, ["AAPL"], now=when("2026-10-23", 17, 10),
        earnings_source=earnings, completion_clock=lambda: when("2026-10-23", 17, 11),
    )
    assert book.read_bytes() == b"SIGNED_AND_IMMUTABLE_FAKE_LEDGER"
    assert not any(p.name == "portfolio.json" for p in observation.rglob("*"))


def test_observe_once_cli_never_requires_the_paper_account(monkeypatch, tmp_path, capsys):
    called = []
    def fake_monitor(directory, symbols, **kwargs):
        called.append((directory, symbols, kwargs))
        return {"mode": "OBSERVE_ONLY", "status": "WAITING_FOR_NY_WINDOW", "orders": 0}
    monkeypatch.setattr(observe, "monitor", fake_monitor)
    assert cli.main([
        "--state", str(tmp_path / "never-initialized.json"),
        "observe", "--once", "--dir", str(tmp_path / "observations"),
        "--tickers", "AAPL", "MSFT",
    ]) == 0
    assert called and called[0][1] == ["AAPL", "MSFT"]
    assert called[0][2]["once"] is True
    assert '"orders": 0' in capsys.readouterr().out


@pytest.mark.parametrize("invalid", [["AAPL;rm"], ["AAPL"] * 9, []])
def test_observation_rejects_invalid_universe(tmp_path, invalid):
    with pytest.raises(ValueError):
        observe.capture(tmp_path / "research", invalid,
                        now=when("2026-10-23", 9, 10),
                        earnings_source=earnings)


def test_saved_calendar_for_different_tickers_does_not_satisfy_new_watchlist(tmp_path):
    home = tmp_path / "research"
    observe.capture(
        home, ["AAPL"], now=when("2026-10-23", 9, 10),
        earnings_source=earnings, completion_clock=lambda: when("2026-10-23", 9, 11),
    )
    with pytest.raises(ValueError, match="different symbol set"):
        observe.capture(
            home, ["MSFT"], now=when("2026-10-23", 9, 15),
            earnings_source=earnings,
        )


def test_saved_market_for_different_tickers_is_not_considered_complete(tmp_path):
    home = tmp_path / "research"
    def aapl_only(symbols, start, end):
        assert symbols == {"AAPL"}
        data = market_data(end)
        return data, lambda *_: (0.75, 0.75)
    observe.capture(
        home, ["AAPL"], now=when("2026-10-23", 18, 0),
        prices_source=aapl_only, corporate_guard=lambda *_: None,
    )
    with pytest.raises(ValueError, match="different symbol set"):
        observe.capture(
            home, ["AAPL", "MSFT"], now=when("2026-10-23", 18, 10),
            prices_source=prices, corporate_guard=lambda *_: None,
        )


def test_observation_cannot_be_forced_before_safe_us_close(tmp_path):
    assert observe.active_phase(when("2026-10-23", 16, 0)) is None
    assert observe.active_phase(when("2026-10-24", 18, 0)) is None
    assert observe.active_phase(when("2026-10-23", 18, 0)) == "close"


def test_bad_fx_does_not_create_a_market_snapshot(tmp_path):
    home = tmp_path / "research"
    def invalid_fx(*_):
        return market_data("2026-10-23"), lambda *_: (50.0, 50.0)
    with pytest.raises(ValueError, match="GBP conversion"):
        observe.capture(
            home, ["AAPL"], now=when("2026-10-23", 18, 5),
            prices_source=invalid_fx, corporate_guard=lambda *_: None,
        )
    assert not (home / "market" / "2026-10-23.json").exists()


def test_slow_earnings_provider_must_not_backdate_post_cutoff_results(tmp_path):
    home = tmp_path / "research"
    with pytest.raises(ValueError, match="finished outside"):
        observe.capture(
            home, ["AAPL"], now=when("2026-10-23", 17, 24),
            earnings_source=earnings,
            completion_clock=lambda: when("2026-10-23", 17, 26),
        )
    assert not (home / "calendar" / "2026-10-23" / "preclose.json").exists()


def test_archived_earnings_timestamp_marks_completion_not_request_start(tmp_path):
    home = tmp_path / "research"
    done = when("2026-10-23", 17, 22)
    observe.capture(
        home, ["AAPL"], now=when("2026-10-23", 17, 10),
        earnings_source=earnings, completion_clock=lambda: done,
    )
    data = json.loads((home / "calendar" / "2026-10-23" / "preclose.json").read_text())
    assert data["observed_utc"] == done.astimezone(timezone.utc).isoformat()
    assert (data["earnings"]["AAPL"]["observed_at_utc"]
            != data["observed_utc"])
