"""Phase 1 — the check_event_pricing tool: wiring and BRK-B end-to-end.

The tool is what the news analyst calls before attributing a price move to
an event. These tests pin the tool's contract: its schema, the NOT_YET_
OBSERVABLE verdict on the frozen BRK-B weekend case (mocked vendor frame,
no network), and the guidance text it returns.
"""

from __future__ import annotations

import pandas as pd
import pytest

import tradingagents.agents.tools as tools_mod
from tradingagents.agents.analysts.news_analyst import TOOLS as NEWS_TOOLS
from tradingagents.agents.tools import check_event_pricing


def _sessions_frame(dates):
    """A minimal OHLCV frame whose Date column is the market calendar."""
    return pd.DataFrame({
        "Date": pd.to_datetime(dates),
        "Open": [1.0] * len(dates),
        "High": [1.0] * len(dates),
        "Low": [1.0] * len(dates),
        "Close": [1.0] * len(dates),
        "Volume": [1] * len(dates),
    })


@pytest.mark.unit
def test_tool_is_offered_to_the_news_analyst():
    assert check_event_pricing in NEWS_TOOLS


@pytest.mark.unit
def test_tool_schema_takes_event_date_and_description():
    props = set(check_event_pricing.tool_call_schema.model_json_schema()["properties"])
    # symbol, trade_date are injected from state; the model passes the rest.
    assert {"event_date", "event_description", "curr_date"} <= props


@pytest.mark.unit
def test_brk_b_weekend_release_verdict_is_not_yet_observable(monkeypatch):
    """The frozen regression case: Sat release, Sun run -> NOT_YET_OBSERVABLE.

    The vendor frame ends at Friday 11-06 (the last settled session), so the
    calendar the tool derives has no post-event session.
    """
    monkeypatch.setattr(
        tools_mod, "load_ohlcv",  # imported inside the tool's body
        lambda *a, **k: _sessions_frame(["2026-11-04", "2026-11-05", "2026-11-06"]),
        raising=False,
    )
    # The tool imports load_ohlcv locally; patch the source module too.
    from tradingagents.dataflows.vendors.yahoo import ohlcv as ohlcv_mod

    monkeypatch.setattr(
        ohlcv_mod, "load_ohlcv",
        lambda *a, **k: _sessions_frame(["2026-11-04", "2026-11-05", "2026-11-06"]),
    )
    out = check_event_pricing.invoke({
        "symbol": "BRK-B",
        "event_date": "2026-11-07",
        "event_description": "Q3 2026 earnings release",
        "curr_date": "2026-11-08",
        "trade_date": "2026-11-08",
    })
    assert "NOT_YET_OBSERVABLE" in out
    assert "2026-11-06" in out          # last session before the event
    assert "Do NOT claim" in out        # the guidance the analyst must follow


@pytest.mark.unit
def test_observable_case_cites_the_first_post_event_session(monkeypatch):
    """Once Monday has traded, the tool reports it as the reaction window."""
    from tradingagents.dataflows.vendors.yahoo import ohlcv as ohlcv_mod

    monkeypatch.setattr(
        ohlcv_mod, "load_ohlcv",
        lambda *a, **k: _sessions_frame(
            ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
        ),
    )
    out = check_event_pricing.invoke({
        "symbol": "BRK-B",
        "event_date": "2026-11-07",
        "event_description": "Q3 2026 earnings release",
        "curr_date": "2026-11-09",
        "trade_date": "2026-11-09",
    })
    assert "OBSERVABLE" in out
    assert "2026-11-09" in out
    assert "must cite prices from 2026-11-09" in out


@pytest.mark.unit
def test_vendor_failure_degrades_to_insufficient_data(monkeypatch):
    """No calendar -> the tool still answers, it does not crash the run."""
    from tradingagents.dataflows.errors import NoMarketDataError
    from tradingagents.dataflows.vendors.yahoo import ohlcv as ohlcv_mod

    def boom(*a, **k):
        raise NoMarketDataError("BRK-B", "BRK-B", "no rows")

    monkeypatch.setattr(ohlcv_mod, "load_ohlcv", boom)
    out = check_event_pricing.invoke({
        "symbol": "BRK-B",
        "event_date": "2026-11-07",
        "event_description": "Q3 2026 earnings release",
        "curr_date": "2026-11-08",
        "trade_date": "2026-11-08",
    })
    assert "NOT_YET_OBSERVABLE" in out  # empty calendar: no session after the event


@pytest.mark.unit
def test_unknown_event_date_blocks_the_claim(monkeypatch):
    from tradingagents.dataflows.vendors.yahoo import ohlcv as ohlcv_mod

    monkeypatch.setattr(
        ohlcv_mod, "load_ohlcv",
        lambda *a, **k: _sessions_frame(["2026-11-06"]),
    )
    out = check_event_pricing.invoke({
        "symbol": "BRK-B",
        "event_date": "unknown",
        "event_description": "mystery event",
        "curr_date": "2026-11-08",
        "trade_date": "2026-11-08",
    })
    assert "UNKNOWN" in out
    assert "INSUFFICIENT_DATA" in out
    assert "cannot be checked" in out
