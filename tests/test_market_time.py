"""Market calendar "today" vs host date.today() (PT/ET midnight skew)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from cli import prompts
from tradingagents import market_time


@pytest.mark.unit
def test_market_today_follows_configured_tz(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MARKET_TZ", "America/New_York")
    assert market_time.market_today() == datetime.now(ZoneInfo("America/New_York")).date()


@pytest.mark.unit
def test_parse_analysis_date_accepts_ny_today_when_host_still_yesterday(monkeypatch):
    """Reproduce the site failure window: NY already on D+1 while host PT is still D."""
    ny = date(2026, 10, 28)
    monkeypatch.setattr(prompts, "market_today", lambda: ny, raising=False)
    # parse_analysis_date imports market_today inside the function.
    monkeypatch.setattr(market_time, "market_today", lambda: ny)
    assert prompts.parse_analysis_date("2026-10-28") == "2026-10-28"
    with pytest.raises(ValueError, match="future"):
        prompts.parse_analysis_date((ny + timedelta(days=1)).isoformat())
