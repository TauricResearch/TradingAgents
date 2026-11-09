from unittest.mock import Mock

import pandas as pd
import pytest
import requests

pytest.importorskip("exchange_calendars")

from tradingagents.dataflows.vendors.eodhd import EODHDClient, EODHDError, normalize_daily


def row(day, **overrides):
    return {
        "date": day,
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "adjusted_close": 101,
        "volume": 1000,
        **overrides,
    }


def test_holiday_early_close_and_incomplete_bars():
    rows = [row("2025-11-26"), row("2025-11-28")]
    result = normalize_daily(rows, "2025-11-26", "2025-11-28", "2025-11-28T17:59:00Z")
    assert len(result.bars) == 1
    assert result.metadata["missing_sessions"] == []
    result = normalize_daily(rows, "2025-11-26", "2025-11-28", "2025-11-28T18:01:00Z")
    assert result.bars.index[-1] == pd.Timestamp("2025-11-28T18:00:00Z")
    assert result.metadata["point_in_time_certified"] is False


def test_dst_gap_and_adjustment_break():
    result = normalize_daily(
        [row("2025-03-07", adjusted_close=50.5), row("2025-03-11")],
        "2025-03-07",
        "2025-03-11",
        "2025-03-12T00:00:00Z",
    )
    assert result.bars.index[0].hour == 21
    assert result.bars.index[1].hour == 20
    assert result.metadata["missing_sessions"] == ["2025-03-10"]
    assert bool(result.bars.iloc[1].gap_before)
    assert bool(result.bars.iloc[1].adjustment_break)
    assert result.bars.iloc[0].close == 101  # Raw values were not retrospectively adjusted.


@pytest.mark.parametrize(
    "rows",
    [
        [],
        {"error": "denied"},
        [row("2025-03-07", high=1)],
        [row("2025-03-07", volume=-1)],
        [row("2025-03-07", close=float("inf"))],
        [row("2025-03-07"), row("2025-03-07")],
        [row("2025-03-08")],
        [row("bad")],
    ],
)
def test_normalization_rejects_malformed(rows):
    with pytest.raises(EODHDError):
        normalize_daily(rows, "2025-03-07", "2025-03-10", "2025-03-12T00:00:00Z")


def test_token_cache_refresh_and_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("EODHD_API_TOKEN", "test-secret")
    response = Mock(status_code=200)
    response.json.return_value = [row("2025-03-07")]
    request = Mock(return_value=response)
    monkeypatch.setattr("tradingagents.dataflows.vendors.eodhd.get_scrubbed", request)
    client = EODHDClient(tmp_path, min_request_seconds=0)
    first = client.daily("SPY.US", "2025-03-07", "2025-03-07", now="2025-03-08T00:00:00Z")
    cached = client.daily("SPY.US", "2025-03-07", "2025-03-07", now="2025-03-08T01:00:00Z")
    assert request.call_count == 1
    assert cached.metadata["cache_hit"]
    assert cached.metadata["retrieved_at"] == first.metadata["retrieved_at"]
    assert request.call_args.kwargs["params"]["api_token"] == "test-secret"
    assert "test-secret" not in next(tmp_path.glob("*.json")).read_text()
    response.json.return_value = [row("2025-03-07", adjusted_close=50.5)]
    revised = client.daily(
        "SPY.US", "2025-03-07", "2025-03-07", refresh=True, now="2025-03-08T01:00:00Z"
    )
    assert request.call_count == 2
    assert revised.bars.adjusted_close.iloc[0] == 50.5


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_account_denial_no_retry(tmp_path, monkeypatch, status):
    monkeypatch.setenv("EODHD_API_TOKEN", "test-secret")
    request = Mock(return_value=Mock(status_code=status))
    monkeypatch.setattr("tradingagents.dataflows.vendors.eodhd.get_scrubbed", request)
    with pytest.raises(EODHDError, match="plan/budget"):
        EODHDClient(tmp_path).daily(
            "SPY.US", "2025-03-07", "2025-03-07", now="2025-03-08T00:00:00Z"
        )
    assert request.call_count == 1
    assert not list(tmp_path.glob("*.json"))


def test_missing_token_and_safe_errors(tmp_path, monkeypatch):
    client = EODHDClient(tmp_path, min_request_seconds=0)
    monkeypatch.delenv("EODHD_API_TOKEN", raising=False)
    with pytest.raises(EODHDError, match="EODHD_API_TOKEN"):
        client.daily("SPY.US", "2025-03-07", "2025-03-07")
    monkeypatch.setenv("EODHD_API_TOKEN", "test-secret")
    monkeypatch.setattr(
        "tradingagents.dataflows.vendors.eodhd.get_scrubbed",
        Mock(side_effect=requests.ConnectionError("url?api_token=test-secret")),
    )
    with pytest.raises(EODHDError) as error:
        client.daily("SPY.US", "2025-03-07", "2025-03-07")
    assert "test-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_symbol_and_date_validation(tmp_path):
    client = EODHDClient(tmp_path)
    for symbol in ("../SPY.US", "SPY", "SPY.US?api_token=bad"):
        with pytest.raises(ValueError):
            client.daily(symbol, "2025-03-07", "2025-03-07")
    with pytest.raises(ValueError):
        client.daily("SPY.US", "2025-03-08", "2025-03-07")


def test_full_mocked_vertical_slice(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    import exchange_calendars as xcals

    from tests.test_surge_engine import pattern_bars
    from tradingagents.surge.chart import zone_chart
    from tradingagents.surge.engine import detect_zones

    bars = pattern_bars("DBR")
    sessions = xcals.get_calendar("XNYS").sessions_in_range("2025-01-02", "2025-03-01")
    sessions = sessions[: len(bars)]
    rows = [
        row(session.strftime("%Y-%m-%d"), **bar.to_dict(), adjusted_close=bar.close)
        for session, (_, bar) in zip(sessions, bars.iterrows(), strict=True)
    ]
    monkeypatch.setenv("EODHD_API_TOKEN", "test-secret")
    monkeypatch.setattr(
        "tradingagents.dataflows.vendors.eodhd.get_scrubbed",
        Mock(return_value=Mock(status_code=200, json=Mock(return_value=rows))),
    )
    snapshot = EODHDClient(tmp_path).daily(
        "SPY.US", "2025-01-02", sessions[-1].strftime("%Y-%m-%d"), now="2025-03-02T00:00:00Z"
    )
    zones = detect_zones(snapshot.bars, "SPY.US")
    assert len(zones) == 1
    assert zones[0].pattern == "DBR"
    assert len(zone_chart(snapshot.bars, zones).data) == 3


def test_expiry_and_failed_refresh_preserve_good_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("EODHD_API_TOKEN", "test-secret")
    request = Mock(return_value=Mock(status_code=200, json=Mock(return_value=[row("2025-03-07")])))
    monkeypatch.setattr("tradingagents.dataflows.vendors.eodhd.get_scrubbed", request)
    client = EODHDClient(tmp_path, ttl_seconds=60, min_request_seconds=0)
    client.daily("SPY.US", "2025-03-07", "2025-03-07", now="2025-03-08T00:00:00Z")
    cache = next(tmp_path.glob("*.json"))
    original = cache.read_text()
    request.side_effect = requests.Timeout("private request details")
    with pytest.raises(EODHDError):
        client.daily("SPY.US", "2025-03-07", "2025-03-07", now="2025-03-08T00:02:00Z")
    assert request.call_count == 2
    assert cache.read_text() == original
