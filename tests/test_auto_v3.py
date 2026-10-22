"""V3 no-broker paper runner tests: offline fixtures only."""
import json
import pytest
from tradingagents.paper.auto_v3 import init, run_day, read, verify


def day(session="2026-10-23"):
    return {"day":session, "source":"OFFLINE_TEST_FIXTURE",
            "captured_at_utc":session+"T23:00:00+00:00",
            "bars":{}, "gbp_per_usd_open":.75, "gbp_per_usd_close":.75,
            "spy_close_usd":600.0, "earnings_preopen":{},
            "earnings_afterclose":{}}


def make_feed(tmp_path, obj):
    path=tmp_path/"fixture.json"
    path.write_text(json.dumps(obj),encoding="utf-8")
    return path


def test_separate_v3_book_never_reinitialized(tmp_path):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    original=(home/"portfolio.json").read_bytes()
    with pytest.raises(ValueError,match="exists"):
        init(home,"2026-10-22")
    assert (home/"portfolio.json").read_bytes()==original


def test_completed_day_replayed_once_only(tmp_path):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    result=run_day(home,make_feed(tmp_path,day()))
    assert result["mode"]=="PAPER_ADVANCED"
    assert read(home).book.last_session=="2026-10-23"
    verify(home)
    with pytest.raises(ValueError,match="Duplicate"):
        run_day(home,make_feed(tmp_path,day()))


def test_preview_is_nonmutating(tmp_path):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    before=(home/"portfolio.json").read_bytes()
    log_before=(home/"journal.jsonl").read_bytes()
    result=run_day(home,make_feed(tmp_path,day()),preview=True)
    assert result["mode"]=="PREVIEW"
    assert (home/"portfolio.json").read_bytes()==before
    assert (home/"journal.jsonl").read_bytes()==log_before


def test_malformed_ohlc_rejected_without_changing_book(tmp_path):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    original=(home/"portfolio.json").read_bytes()
    bad=day()
    bad["bars"]={"NVDA":{"open":100.0,"high":90.0,"low":99.0,"close":100.0}}
    with pytest.raises(ValueError,match="OHLC"):
        run_day(home,make_feed(tmp_path,bad))
    assert (home/"portfolio.json").read_bytes()==original


@pytest.mark.parametrize("bad_fx",[0,-1,.1,3.0])
def test_bad_fx_fails_closed(tmp_path,bad_fx):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    bad=day()
    bad["gbp_per_usd_open"]=bad_fx
    with pytest.raises(ValueError,match="GBP/USD"):
        run_day(home,make_feed(tmp_path,bad))


def test_journal_mismatch_rejected(tmp_path):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    run_day(home,make_feed(tmp_path,day()))
    (home/"portfolio.json").write_text("{}")
    with pytest.raises(ValueError,match="mismatch"):
        verify(home)


def test_no_model_rating_to_buy_shortcut(tmp_path):
    home=tmp_path/"account"
    init(home,"2026-10-22")
    run_day(home,make_feed(tmp_path,day()))
    assert read(home).book.positions=={}
    assert read(home).book.orders==[]
