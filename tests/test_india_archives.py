"""NSE archive files read into rows, and corporate actions into adjustment factors.

The fixtures are slices of real files from archives.nseindia.com (downloaded
2026-10-05): the equity list, the NIFTY 50 list, an old-layout bhavcopy
(5 Jul 2024), a UDiFF bhavcopy and a delivery file (1 Oct 2026), and the PR zip
of 2 Jan 2015 and of 1 Oct 2026, whose layouts differ. No network.
"""

from datetime import date
from pathlib import Path

import pytest

from tradingagents.dataflows.vendors.india import nse
from tradingagents.dataflows.vendors.india.actions import (
    cumulative_factors,
    parse_purpose,
    rights_factor,
)

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).parent / "fixtures" / "india"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_the_equity_list_gives_isin_face_value_and_listing_date():
    rows = {s.symbol: s for s in nse.parse_equity_list(fixture("EQUITY_L.csv"))}
    reliance = rows["RELIANCE"]
    assert reliance.isin == "INE002A01018" and reliance.series == "EQ"
    assert reliance.face_value == 10.0 and reliance.listing_date == "1995-11-29"
    assert rows["20MICRONS"].face_value == 5.0


def test_an_index_list_gives_nse_industry():
    rows = {r["symbol"]: r for r in nse.parse_index_list(fixture("ind_nifty50list.csv"))}
    assert rows["HDFCBANK"]["industry"] == "Financial Services"
    assert rows["RELIANCE"]["isin"] == "INE002A01018"


def test_old_layout_bhavcopy_keeps_equities_with_their_isin():
    rows = nse.parse_cm_bhav(fixture("cm05JUL2024bhav.csv.zip"))
    assert {r.symbol for r in rows} == {"RELIANCE", "TCS", "HDFCBANK", "ITC", "20MICRONS"}  # the bond row is dropped
    r = next(r for r in rows if r.symbol == "RELIANCE")
    assert (r.isin, r.day, r.open, r.close, r.volume) == ("INE002A01018", "2024-07-05", 3107.65, 3177.25, 6134855)


def test_udiff_bhavcopy_reads_the_same_fields_from_its_own_layout():
    rows = nse.parse_udiff_bhav(fixture("BhavCopy_NSE_CM_0_0_0_20261001_F_0000.csv.zip"))
    assert "SGBJUN28" not in {r.symbol for r in rows}  # gold bonds are not equities
    r = next(r for r in rows if r.symbol == "RELIANCE")
    assert (r.isin, r.day, r.high, r.low, r.close, r.volume) == (
        "INE002A01018", "2026-10-01", 1183.9, 1160.8, 1167.7, 16771221)


def test_delivery_file_gives_deliverable_quantity_by_symbol_and_series():
    deliveries = nse.parse_mto(fixture("MTO_01102026.DAT"))
    assert deliveries[("RELIANCE", "EQ")] == 10270423
    assert all(series in nse.EQUITY_SERIES for _, series in deliveries)


@pytest.mark.parametrize("name, day, iso_dates", [("PR011026.zip", date(2026, 10, 1), True),
                                                   ("PR020115.zip", date(2015, 1, 2), False)])
def test_pr_zips_of_both_layouts(name, day, iso_dates):
    data = fixture(name)
    prices = nse.parse_pr_prices(data, day)
    assert prices and all(p.isin is None and p.day == day.isoformat() for p in prices)
    actions = nse.parse_pr_actions(data)
    assert actions and all(a.ex_date and len(a.ex_date) == 10 for a in actions)
    announcements = nse.parse_pr_announcements(data)
    assert announcements and all(a.symbol and a.text for a in announcements)
    meetings = nse.parse_pr_board_meetings(data)
    assert meetings and all(m.meeting_date for m in meetings) and all(m.purpose for m in meetings)
    shares = nse.parse_pr_shares(data)
    assert bool(shares) is iso_dates  # the mcap file came later


def test_2015_split_purposes_and_dates_parse():
    actions = {a.symbol: a for a in nse.parse_pr_actions(fixture("PR020115.zip"))}
    assert actions["BANKBARODA"].ex_date == "2015-01-22"
    assert actions["BANKBARODA"].purpose == "FV SPLT FRM RS 10 TO RS 2"


def test_2026_announcements_keep_their_category():
    first = nse.parse_pr_announcements(fixture("PR011026.zip"))[0]
    assert first.category == "Shareholders meeting" and first.symbol == "MAHICKRA"


def test_mcap_gives_shares_issued():
    shares = {s.symbol: s for s in nse.parse_pr_shares(fixture("PR011026.zip"))}
    assert shares["20MICRONS"].issue_size == 35286502 and shares["20MICRONS"].face_value == 5.0


def test_each_day_reads_prices_from_the_file_that_covers_it():
    assert [k for k, _ in nse.price_sources(date(2015, 6, 1))] == ["pr"]
    assert [k for k, _ in nse.price_sources(date(2019, 6, 3))] == ["cm"]
    assert [k for k, _ in nse.price_sources(date(2024, 3, 1))] == ["udiff", "cm"]
    assert [k for k, _ in nse.price_sources(date(2026, 10, 1))] == ["udiff"]
    assert nse.cm_bhav_url(date(2024, 7, 5)).endswith("/2024/JUL/cm05JUL2024bhav.csv.zip")
    assert nse.pr_url(date(2015, 1, 2)).endswith("/PR020115.zip")


@pytest.mark.parametrize("purpose, expected", [
    ("FV SPLT FRM RS 10 TO RS 2", [("split", 5.0, None)]),
    ("FVSPLT FRM RS 10 TO RS 5", [("split", 2.0, None)]),
    ("FV SPLT FRM RS 2 TO RE 1", [("split", 2.0, None)]),
    ("FACE VALUE SPLIT (SUB-DIVISION) - FROM RS 10/- PER SHARE TO RS 2/- PER SHARE", [("split", 5.0, None)]),
    ("FV CONSOLIDATION FRM RS 1 TO RS 10", [("split", 0.1, None)]),
    ("BONUS 1:1", [("bonus", 2.0, None)]),
    ("BONUS 2:1", [("bonus", 3.0, None)]),
    ("BONUS 1:1/FV SPL 10 TO 2", [("split", 5.0, None), ("bonus", 2.0, None)]),
    ("DIV - RS 1.50 PER SH", [("dividend", None, 1.5)]),
    ("INTDIV - RS 8 PER SH", [("dividend", None, 8.0)]),
    ("AGM/DIV - RS 5 PER SH/SPL DIV - RS 2 PER SH", [("dividend", None, 7.0)]),
    ("SPL DIV - RS 25 PER SH", [("dividend", None, 25.0)]),
    ("DIVIDEND 50%", [("dividend", None, 5.0)]),  # of a Rs 10 face value
    ("RGHTS 2:21 @PRM RS 748/-", [("rights", None, 758.0)]),  # premium plus face value
    ("DEMERGER", [("demerger", None, None)]),
    ("BUY BACK", [("buyback", None, None)]),
    ("ANNUAL GENERAL MEETING", []),
    ("INTEREST PAYMENT", []),
])
def test_purpose_text_becomes_actions(purpose, expected):
    got = [(a.type, a.factor, a.amount) for a in parse_purpose(purpose, face_value=10.0)]
    assert [(t, pytest.approx(f) if f else f, a) for t, f, a in got] == expected


def test_rights_are_adjusted_by_the_theoretical_ex_rights_price():
    # 1 new for 4 held at 80, with the stock at 100 before the ex-date: TERP 96.
    assert rights_factor(1, 4, 80, 100) == pytest.approx(100 / 96)
    assert rights_factor(1, 4, 120, 100) is None  # not worth taking up: no adjustment
    assert rights_factor(1, 4, None, 100) is None


def test_factors_apply_to_days_before_each_ex_date():
    days = ["2024-10-24", "2024-10-25", "2024-10-28", "2024-10-29"]
    assert cumulative_factors(days, [("2024-10-28", 2.0)]) == [2.0, 2.0, 1.0, 1.0]
    assert cumulative_factors(days, [("2024-10-25", 5.0), ("2024-10-28", 2.0)]) == [10.0, 2.0, 1.0, 1.0]
    assert cumulative_factors(days, []) == [1.0] * 4
