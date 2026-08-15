"""Market-session-aware news-window resolution and vendor integration."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import tradingagents.agents.utils.news_data_tools as news_tools
import tradingagents.dataflows.alpha_vantage_news as av_news
import tradingagents.dataflows.yfinance_news as yf_news
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.news_window import resolve_news_window

NY = ZoneInfo("America/New_York")


def _market_config(**overrides):
    config = {
        "mode": "market_session",
        "exchange": "NYSE",
        "start_anchor": "previous_market_close",
        "start_offset_minutes": 60,
        "end_anchor": "current_market_open",
        "end_offset_minutes": -60,
    }
    config.update(overrides)
    return config


@pytest.mark.unit
def test_normal_weekday_window_uses_exchange_local_session_times():
    window = resolve_news_window("2025-06-18", _market_config())

    assert window.previous_session.isoformat() == "2025-06-17"
    assert window.target_session.isoformat() == "2025-06-18"
    assert window.start == datetime(2025, 6, 17, 17, 0, tzinfo=NY)
    assert window.end == datetime(2025, 6, 18, 8, 30, tzinfo=NY)


@pytest.mark.unit
def test_monday_window_uses_friday_close():
    window = resolve_news_window("2025-06-16", _market_config())

    assert window.previous_session.isoformat() == "2025-06-13"
    assert window.start == datetime(2025, 6, 13, 17, 0, tzinfo=NY)


@pytest.mark.unit
def test_nasdaq_uses_the_shared_us_equity_session_calendar():
    nyse = resolve_news_window("2025-06-18", _market_config(exchange="NYSE"))
    nasdaq = resolve_news_window("2025-06-18", _market_config(exchange="NASDAQ"))

    assert (nasdaq.start, nasdaq.end) == (nyse.start, nyse.end)


@pytest.mark.unit
def test_holiday_and_consecutive_closures_use_previous_valid_session():
    # Friday July 4 is a holiday and is followed by a weekend.
    window = resolve_news_window("2025-07-07", _market_config())

    assert window.previous_session.isoformat() == "2025-07-03"
    assert window.target_session.isoformat() == "2025-07-07"


@pytest.mark.unit
def test_early_close_uses_actual_session_close():
    # July 3, 2025 closes at 13:00 ET, not the regular 16:00 ET.
    window = resolve_news_window("2025-07-07", _market_config())

    assert window.start == datetime(2025, 7, 3, 14, 0, tzinfo=NY)


@pytest.mark.unit
def test_dst_boundary_keeps_exchange_times_and_changes_utc_offset():
    # The previous session is before the spring DST transition; Monday is after it.
    window = resolve_news_window("2025-03-10", _market_config())

    assert window.start == datetime(2025, 3, 7, 17, 0, tzinfo=NY)
    assert window.end == datetime(2025, 3, 10, 8, 30, tzinfo=NY)
    assert window.start.astimezone(timezone.utc).hour == 22
    assert window.end.astimezone(timezone.utc).hour == 12


@pytest.mark.unit
def test_non_session_target_uses_latest_session_without_looking_ahead():
    # A Sunday analysis must not move the current-session anchor into Monday.
    window = resolve_news_window("2025-06-15", _market_config())

    assert window.target_session.isoformat() == "2025-06-13"
    assert window.previous_session.isoformat() == "2025-06-12"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("start_offset", "end_offset", "expected_start", "expected_end"),
    [
        (60, -60, (17, 0), (8, 30)),
        (0, -15, (16, 0), (9, 15)),
        (30, 0, (16, 30), (9, 30)),
    ],
)
def test_configurable_offsets(start_offset, end_offset, expected_start, expected_end):
    window = resolve_news_window(
        "2025-06-18",
        _market_config(
            start_offset_minutes=start_offset,
            end_offset_minutes=end_offset,
        ),
    )

    assert (window.start.hour, window.start.minute) == expected_start
    assert (window.end.hour, window.end.minute) == expected_end


@pytest.mark.unit
@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"mode": "unknown"}, "Unsupported news window mode"),
        (_market_config(exchange="LSE"), "Unsupported exchange"),
        (_market_config(start_anchor="midnight"), "Unsupported start anchor"),
        (_market_config(end_anchor="market_close"), "Unsupported end anchor"),
        (_market_config(start_offset_minutes="sixty"), "start_offset_minutes"),
        (
            _market_config(start_offset_minutes=1_440, end_offset_minutes=-1_440),
            "empty or inverted",
        ),
    ],
)
def test_invalid_configuration_fails_clearly(config, message):
    with pytest.raises(ValueError, match=message):
        resolve_news_window("2025-06-18", config)


@pytest.mark.unit
def test_default_get_news_keeps_legacy_vendor_arguments(monkeypatch):
    captured = {}

    def fake_route(method, *args):
        captured["call"] = (method, args)
        return "legacy"

    monkeypatch.setattr(news_tools, "route_to_vendor", fake_route)

    assert news_tools.get_news.func("AAPL", "2025-06-11", "2025-06-18") == "legacy"
    assert captured["call"] == (
        "get_news",
        ("AAPL", "2025-06-11", "2025-06-18"),
    )


@pytest.mark.unit
def test_market_session_get_news_resolves_once_before_vendor_routing(monkeypatch):
    # One-level config merging supplies the documented anchors and offsets.
    set_config({"news_window": {"mode": "market_session"}})
    captured = {}

    def fake_route(method, *args):
        captured["call"] = (method, args)
        return "market"

    monkeypatch.setattr(news_tools, "route_to_vendor", fake_route)

    assert news_tools.get_news.func("AAPL", "ignored", "2025-06-18") == "market"
    method, args = captured["call"]
    assert method == "get_news"
    assert args[0] == "AAPL"
    assert args[1] == datetime(2025, 6, 17, 17, 0, tzinfo=NY)
    assert args[2] == datetime(2025, 6, 18, 8, 30, tzinfo=NY)


@pytest.mark.unit
def test_market_session_global_news_passes_precise_window(monkeypatch):
    set_config({"news_window": _market_config()})
    captured = {}

    def fake_route(method, *args, **kwargs):
        captured["call"] = (method, args, kwargs)
        return "market"

    monkeypatch.setattr(news_tools, "route_to_vendor", fake_route)

    assert news_tools.get_global_news.func("2025-06-18", 7, 10) == "market"
    method, args, kwargs = captured["call"]
    assert method == "get_global_news"
    assert args == ("2025-06-18", 7, 10)
    assert kwargs["start_time"] == datetime(2025, 6, 17, 17, 0, tzinfo=NY)
    assert kwargs["end_time"] == datetime(2025, 6, 18, 8, 30, tzinfo=NY)


@pytest.mark.unit
def test_yfinance_precise_window_post_filters_timestamps(monkeypatch):
    start = datetime(2025, 6, 17, 17, 0, tzinfo=NY)
    end = datetime(2025, 6, 18, 8, 30, tzinfo=NY)

    def article(title, published):
        return {
            "title": title,
            "publisher": "P",
            "link": "l",
            "providerPublishTime": int(published.timestamp()),
        }

    candidates = [
        article("BEFORE", start - timedelta(minutes=1)),
        article("INSIDE", start.astimezone(timezone.utc)),
        article("AT END", end.astimezone(timezone.utc)),
    ]

    class FakeTicker:
        def __init__(self, _symbol):
            pass

        def get_news(self, count):
            return candidates

    monkeypatch.setattr(yf_news.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(yf_news, "yf_retry", lambda fn: fn())

    output = yf_news.get_news_yfinance("AAPL", start, end)

    assert "INSIDE" in output
    assert "BEFORE" not in output
    assert "AT END" not in output


@pytest.mark.unit
def test_yfinance_global_news_uses_the_same_precise_filter(monkeypatch):
    start = datetime(2025, 6, 17, 17, 0, tzinfo=NY)
    end = datetime(2025, 6, 18, 8, 30, tzinfo=NY)

    def article(title, published):
        return {
            "title": title,
            "publisher": "P",
            "link": "l",
            "providerPublishTime": int(published.timestamp()),
        }

    class FakeSearch:
        def __init__(self, *args, **kwargs):
            self.news = [
                article("BEFORE", start - timedelta(minutes=1)),
                article("INSIDE", start),
                article("AT END", end),
            ]

    monkeypatch.setattr(yf_news.yf, "Search", FakeSearch)
    monkeypatch.setattr(yf_news, "yf_retry", lambda fn: fn())

    output = yf_news.get_global_news_yfinance(
        "2025-06-18",
        limit=10,
        start_time=start,
        end_time=end,
    )

    assert "INSIDE" in output
    assert "BEFORE" not in output
    assert "AT END" not in output


@pytest.mark.unit
def test_alpha_vantage_market_window_is_sent_as_utc(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        av_news,
        "_make_api_request",
        lambda function, params: captured.update(function=function, params=params) or {},
    )

    av_news.get_news(
        "AAPL",
        datetime(2025, 6, 17, 17, 0, tzinfo=NY),
        datetime(2025, 6, 18, 8, 30, tzinfo=NY),
    )

    assert captured["params"]["time_from"] == "20250617T2100"
    assert captured["params"]["time_to"] == "20250618T1230"


@pytest.mark.unit
def test_alpha_vantage_global_news_uses_precise_utc_bounds(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        av_news,
        "_make_api_request",
        lambda function, params: captured.update(function=function, params=params) or {},
    )

    av_news.get_global_news(
        "2025-06-18",
        limit=10,
        start_time=datetime(2025, 6, 17, 17, 0, tzinfo=NY),
        end_time=datetime(2025, 6, 18, 8, 30, tzinfo=NY),
    )

    assert captured["params"]["time_from"] == "20250617T2100"
    assert captured["params"]["time_to"] == "20250618T1230"


@pytest.mark.unit
def test_alpha_vantage_direct_global_news_defaults_are_unchanged(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        av_news,
        "_make_api_request",
        lambda function, params: captured.update(function=function, params=params) or {},
    )

    av_news.get_global_news("2025-06-18")

    assert captured["params"]["time_from"] == "20250611T0000"
    assert captured["params"]["time_to"] == "20250618T0000"
    assert captured["params"]["limit"] == "50"
