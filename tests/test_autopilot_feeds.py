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
        source=lambda t,d,n:snapshot(t,d,n))
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
