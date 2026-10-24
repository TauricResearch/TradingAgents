from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
import pytest

from tradingagents.paper.conditional import EarningsSnapshot
from tradingagents.paper.autopilot import feeds

NY=ZoneInfo("America/New_York")

def when(d,h,m):
    return datetime.fromisoformat(f"{d}T{h:02d}:{m:02d}:00").replace(tzinfo=NY)

def snapshot(t,day,now,verified=True):
    return EarningsSnapshot(day,"2026-12-01","2026-07-25","issuer+secondary",verified,
                            now.astimezone(timezone.utc).isoformat())

@pytest.mark.parametrize("local,phase",[
    (when("2026-10-22",9,15),"preopen"),
    (when("2026-10-22",17,10),"preclose"),
    (when("2026-10-22",18,10),"close"),
])
def test_ny_wall_clock_phases(local,phase):
    assert feeds.session_cutoff(local,phase)=="2026-10-22"

@pytest.mark.parametrize("local,phase",[
    (when("2026-10-22",7,30),"preopen"),
    (when("2026-10-22",11,30),"preclose"),
    (when("2026-10-22",16,0),"close"),
    (when("2026-10-24",18,10),"close"),
])
def test_wrong_clock_or_weekend_cannot_fake_cutoff(local,phase):
    with pytest.raises(ValueError):feeds.session_cutoff(local,phase)


def test_immutable_preopen_evidence_and_readback(tmp_path):
    now=when("2026-10-22",9,15)
    p=feeds.capture_earnings(tmp_path,"2026-10-22","preopen",["NVDA"],now,
        source=lambda t,d,n:snapshot(t,d,n), completion_clock=lambda:now)
    assert p.exists()
    observations=feeds.read_earnings(tmp_path,"2026-10-22","preopen",{"NVDA"},now)
    assert observations["NVDA"].safe("2026-10-22","preopen")
    with pytest.raises(ValueError,match="already captured"):
        feeds.capture_earnings(tmp_path,"2026-10-22","preopen",["NVDA"],now,
           source=lambda t,d,n:snapshot(t,d,n))


def test_missing_preopen_is_not_retroactively_verified(tmp_path):
    now=when("2026-10-22",18,10)
    obs=feeds.read_earnings(tmp_path,"2026-10-22","preopen",{"NVDA"},now)
    assert obs["NVDA"].verified is False
    assert obs["NVDA"].safe("2026-10-22","preopen") is False
    with pytest.raises(ValueError):feeds.capture_earnings(tmp_path,"2026-10-22","preopen",["NVDA"],now)


def test_no_secondary_confirmation_is_a_veto(monkeypatch):
    monkeypatch.setattr(feeds,"_yahoo_earnings",lambda t,s:("2026-07-25","2026-12-01"))
    monkeypatch.setattr(feeds,"_nasdaq_next_date",lambda t,d:False)
    now=when("2026-10-22",9,15)
    event=feeds.earnings_for("NVDA","2026-10-22",now)
    assert event.verified is False
    assert not event.safe("2026-10-22","preopen")


def test_calendar_snapshots_have_a_real_cutoff_not_issuer_guarantee(monkeypatch):
    monkeypatch.setattr(feeds,"_yahoo_earnings",lambda t,s:("2026-07-25","2026-12-01"))
    monkeypatch.setattr(feeds,"_nasdaq_next_date",lambda t,d:True)
    now=when("2026-10-22",9,15)
    snap=feeds.earnings_for("NVDA","2026-10-22",now)
    assert snap.verified
    assert snap.source=="YAHOO+NASDAQ_CONSENSUS_SECONDARY"
    assert snap.safe("2026-10-22","preopen")
    assert snap.safe("2026-10-22","afterclose") is False


def test_dividend_or_split_refuses_to_invent_a_paper_return():
    import pandas as pd
    def make_day(split=0,div=0):
        index=pd.DatetimeIndex(["2026-10-22"]).tz_localize("America/New_York")
        return pd.DataFrame({"Stock Splits":[split],"Dividends":[div]},index=index)
    with pytest.raises(ValueError,match="UNMODELLED_CORPORATE_ACTION"):
        feeds.reject_unmodelled_corporate_actions({"NVDA"},"2026-10-22","2026-10-22",
            history_provider=lambda *a:make_day(split=2.0))
    with pytest.raises(ValueError,match="UNMODELLED_CORPORATE_ACTION"):
        feeds.reject_unmodelled_corporate_actions({"NVDA"},"2026-10-22","2026-10-22",
            history_provider=lambda *a:make_day(div=.24))
    feeds.reject_unmodelled_corporate_actions({"NVDA"},"2026-10-22","2026-10-22",
            history_provider=lambda *a:make_day())


def test_missing_corporate_action_fields_fail_closed():
    import pandas as pd
    empty_frame=pd.DataFrame({"Close":[200.]},index=pd.DatetimeIndex(["2026-10-22"]))
    with pytest.raises(ValueError,match="Corporate action fields unavailable"):
        feeds.reject_unmodelled_corporate_actions({"NVDA"},"2026-10-22","2026-10-22",
            history_provider=lambda *a:empty_frame)


@pytest.mark.parametrize("ny_day,hour,minute,phase,uk_clock", [
    ("2026-10-26", 8, 45, "preopen", "12:45 GMT"),
    ("2026-10-26", 17, 10, "preclose", "21:10 GMT"),
    ("2026-10-26", 17, 40, "close", "21:40 GMT"),
    ("2026-11-02", 8, 45, "preopen", "13:45 GMT"),
    ("2026-11-02", 17, 40, "close", "22:40 GMT"),
])
def test_october_november_2026_uk_us_dst_asymmetry(ny_day,hour,minute,phase,uk_clock):
    """UK and New York clocks change on DIFFERENT Sundays; never hardcode an offset."""
    local_ny=when(ny_day,hour,minute)
    actual_uk=local_ny.astimezone(ZoneInfo("Europe/London"))
    assert actual_uk.strftime("%H:%M %Z")==uk_clock
    assert feeds.session_cutoff(actual_uk,phase)==ny_day


@pytest.mark.parametrize("ticker,previous,next_release,permitted", [
    ("AAPL","2026-07-30","2026-11-02",False),
    ("MSFT","2026-07-29","2026-10-28",False),
    ("COST","2026-09-24","2026-12-10",True),
    ("JPM","2026-10-13","2027-01-14",True),
    ("WMT","2026-08-20","2026-11-19",True),
])
def test_monday_research_date_policy_only_not_real_source_approval(
    ticker,previous,next_release,permitted,
):
    """A mocked verified calendar tests date arithmetic, NOT actual vendor agreement."""
    clock=when("2026-10-26",17,10)
    fake=EarningsSnapshot(
        "2026-10-26",next_release,previous,
        "SYNTHETIC_DATE_MATH_TEST_NOT_A_VERIFIED_SOURCE",True,
        clock.astimezone(timezone.utc).isoformat(),
    )
    assert fake.safe("2026-10-26","afterclose") is permitted


def test_monday_without_verified_earnings_remains_blocked():
    """Official investor calendar alone cannot bypass dual-secondary validation."""
    clock=when("2026-10-26",17,10)
    fake=EarningsSnapshot(
        "2026-10-26","2026-12-10","2026-09-24",
        "UNVERIFIED_SECONDARY_FEEDS",False,
        clock.astimezone(timezone.utc).isoformat(),
    )
    assert not fake.safe("2026-10-26","afterclose")


def test_future_earnings_row_cannot_be_used_as_preclose_snapshot(tmp_path):
    recorded_at = when("2026-10-22", 17, 10)
    later = when("2026-10-22", 17, 20)
    feeds.capture_earnings(
        tmp_path, "2026-10-22", "preclose", ["NVDA"], recorded_at,
        source=lambda t , d, n: snapshot(t, d, later, completion_clock=lambda: recorded_at,
    )
    result = feeds.read_earnings(
        tmp_path, "2026-10-22", "preclose", {"NVDA"},
        when("2026-10-22", 18, 10),
    )
    assert result["NVDA"].verified is False
    assert result["NVDA"].safe("2026-10-22", "afterclose") is False


def test_future_or_wrong_window_calendar_envelope_fails_closed(tmp_path):
    recorded_at = when("2026-10-22", 17, 10)
    file = feeds.capture_earnings(
        tmp_path, "2026-10-22", "preclose", ["NVDA"], recorded_at,
        source=lambda t , d, n: snapshot(t, d, n, completion_clock=lambda: recorded_at,
    )
    actual = json.loads(file.read_text())
    actual["observed_utc"] = when("2026-10-22", 9, 10).astimezone(timezone.utc).isoformat()
    file.write_text(json.dumps(actual))
    result = feeds.read_earnings(
        tmp_path, "2026-10-22", "preclose", {"NVDA"},
        when("2026-10-22", 18, 10),
    )
    assert result["NVDA"].verified is False


def test_calendar_envelope_from_the_future_is_not_verified(tmp_path):
    recorded_at = when("2026-10-22", 9, 15)
    feeds.capture_earnings(
        tmp_path, "2026-10-22", "preopen", ["NVDA"], recorded_at,
        source=lambda t , d, n: snapshot(t, d, n, completion_clock=lambda: recorded_at,
    )
    result = feeds.read_earnings(
        tmp_path, "2026-10-22", "preopen", {"NVDA"},
        when("2026-10-22", 9, 10),
    )
    assert result["NVDA"].verified is False
