"""Results and shareholding XBRL read into the Company page's fields.

The fixtures follow the real NSE formats element for element (namespaces,
context ids, units, rounding) but describe fictional companies with made-up
round figures: ACME INDUSTRIES (an Ind-AS company) and SAMPLE BANK. They carry
the quirks of the real files: the old format's year-to-date context declaring
the quarter's dates, a breakdown member under a dimension, shareholding in
percents (2020 taxonomy) and in fractions (2025 taxonomy).
"""

from pathlib import Path

import pytest

from tradingagents.dataflows import field_aliases
from tradingagents.dataflows.vendors.india import xbrl
from tradingagents.dataflows.vendors.yahoo import company_profile as yahoo

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).parent / "fixtures" / "india"
CR = 1e7
Q4 = "INTEGRATED_FILING_INDAS_1000001_24042026105714_WEB.xml"
OLD_Q3 = "INDAS_100002_200002_16012025081520.xml"
BANK = "INTEGRATED_FILING_BANKING_1000003_18072026040136_WEB.xml"
SHP_2025 = "SHP_1000004_16072026072434_WEB.xml"
SHP_2020 = "SHP_100005_200005_21102021092856_WEB.xml"


def parse(name, **kw):
    return xbrl.parse_filing((FIXTURES / name).read_bytes(), name, **kw)


def fields(filing, period_type):
    return {f: v for _, kind, _, f, v, _ in filing.rows if kind == period_type}


def units(filing):
    return {f: u for _, _, _, f, _, u in filing.rows}


# --- Results ----------------------------------------------------------------------

def test_an_integrated_q4_filing_gives_quarter_year_and_balance_sheet():
    f = parse(Q4)
    assert (f.isin, f.symbol, f.basis, f.format, f.period_end) == (
        "INE999Z01019", "ACME", "consolidated", "indas", "2026-03-31")
    assert {(end, kind, start) for end, kind, start, *_ in f.rows} == {
        ("2026-03-31", "Q", "2026-01-01"), ("2026-03-31", "A", "2025-04-01"), ("2026-03-31", "I", None)}


def test_values_are_rupees_mapped_to_phase_1_fields():
    q = fields(parse(Q4), "Q")
    assert q["sales"] == 12500 * CR and q["other_income"] == 300 * CR
    # Ind-AS "Expenses" includes finance costs; Phase 1's total_expenses does not.
    assert q["total_expenses"] == (10500 - 200) * CR
    assert q["cogs"] == (6000 + 1000 - 100) * CR
    assert (q["interest"], q["depreciation"], q["pbt"], q["tax"]) == (200 * CR, 500 * CR, 2300 * CR, 575 * CR)
    assert q["net_profit"] == 1750 * CR  # minority interest included
    assert q["net_income"] == 1650 * CR  # to the parent's owners
    assert q["eps"] == 164.5 and q["eps_basic"] == 165.0  # diluted first


def test_units_say_what_each_value_is():
    u = units(parse(Q4))
    assert u["sales"] == "INR" and u["eps"] == "INR/share" and u["face_value"] == "INR/share"
    assert u["total_expenses"] == "INR" and u["free_cash_flow"] == "INR"


def test_balance_sheet_fields_follow_phase_1_definitions():
    b = fields(parse(Q4), "I")
    assert b["equity"] == 40100 * CR  # attributable to owners, not total equity
    assert b["total_debt"] == (8000 + 2000) * CR
    assert b["net_ppe"] == (30000 + 4000 + 500 + 0) * CR  # CWIP included, as Phase 1's net PPE
    assert b["cwip"] == (4000 + 500) * CR and b["intangibles"] == (1000 + 2000) * CR
    assert b["investments"] == (6000 + 1500) * CR and b["current_investments"] == 3000 * CR
    assert (b["total_assets"], b["current_assets"], b["current_liabilities"]) == (70000 * CR, 23000 * CR, 16000 * CR)


def test_cash_flows_and_free_cash_flow_come_from_the_year():
    a = fields(parse(Q4), "A")
    assert (a["operating"], a["investing"], a["financing"]) == (9000 * CR, -7200 * CR, -1300 * CR)
    assert a["capex"] == 7000 * CR and a["free_cash_flow"] == 2000 * CR
    assert a["sales"] == 47000 * CR and a["eps"] == 588.0


def test_a_breakdown_under_a_dimension_is_never_read_as_the_total():
    assert fields(parse(Q4), "Q")["other_expenses"] == 2000 * CR  # not the 1,200 of one breakdown member


def test_unknown_tags_are_counted_not_fatal():
    f = parse(Q4)
    assert f.unknown == {"SomeNewlyIntroducedMetric": 1}


def test_the_old_formats_year_to_date_context_is_read_by_its_own_dates():
    """in-bse-fin's FourD declares the quarter's dates but holds nine months."""
    f = parse(OLD_Q3)
    assert f.isin is None and f.symbol == "ACME" and f.basis == "standalone"
    assert fields(f, "Q")["sales"] == 11000 * CR
    nine = [(start, v) for _, kind, start, field, v, _ in f.rows if kind == "N" and field == "sales"]
    assert nine == [("2024-04-01", 33000 * CR)]
    assert fields(f, "Q")["net_income"] == fields(f, "Q")["net_profit"]  # standalone: no owners' line


def test_a_bank_gets_net_revenue_and_its_own_lines():
    f = parse(BANK)
    assert f.format == "banking" and f.financial and f.basis == "standalone"
    q = fields(f, "Q")
    assert q["interest_income"] == 30000 * CR and q["interest"] == 17000 * CR
    assert q["net_interest_income"] == 13000 * CR
    assert q["sales"] == (13000 + 8000) * CR  # net interest income plus other income, as Phase 1's bank rows
    assert q["gross_npa_ratio"] == 0.0125 and units(f)["gross_npa_ratio"] == "pure"
    assert q["eps"] == 9.85
    b = fields(f, "I")
    assert b["equity"] == (760 + 450000) * CR and b["total_debt"] == 500000 * CR
    assert b["deposits"] == 2500000 * CR and b["advances"] == 2400000 * CR


# --- When a filing became public ------------------------------------------------------

def test_the_file_names_submission_time_is_read_on_a_12_hour_clock():
    # 10:57:14 or 22:57:14; the board meeting ended at 19:11, so the evening one.
    assert parse(Q4).filed_at == "2026-04-24T22:57:14"
    assert parse(OLD_Q3).filed_at == "2025-01-16T20:15:20"
    assert parse(BANK).filed_at == "2026-07-18T16:01:36"


def test_without_a_meeting_the_later_reading_is_taken():
    f = parse(SHP_2025)
    assert f.filed_at == "2026-07-16T19:24:34" and "later" in f.filed_at_basis


def test_a_file_without_nses_name_falls_back_to_the_board_meeting():
    data = (FIXTURES / Q4).read_bytes()
    f = xbrl.parse_filing(data, "acme_q4_results.xml")
    assert f.filed_at == "2026-04-24T19:41:00" and "30 minutes" in f.filed_at_basis
    assert f.url is None


def test_a_filing_with_no_date_at_all_is_refused_unless_one_is_given():
    data = (FIXTURES / SHP_2025).read_bytes()
    with pytest.raises(xbrl.FilingError, match="--filed-at"):
        xbrl.parse_filing(data, "shareholding.xml")
    assert xbrl.parse_filing(data, "shareholding.xml", "2026-07-20").filed_at == "2026-07-20T23:59:59"


def test_filename_stamps():
    day, readings = xbrl.filename_stamp("INDAS_117297_1348248_16012025081520.xml")
    assert str(day) == "2025-01-16" and [r.hour for r in readings] == [8, 20]
    assert [r.hour for r in xbrl.filename_stamp("X_16012025201520_WEB.xml")[1]] == [20]
    assert [r.hour for r in xbrl.filename_stamp("X_16012025121520.xml")[1]] == [0, 12]
    assert xbrl.filename_stamp("results.xml") is None


# --- Refusals -----------------------------------------------------------------------

def test_money_in_another_currency_is_refused():
    data = (FIXTURES / Q4).read_bytes().replace(b"iso4217:INR</xbrli:measure></xbrli:unit>",
                                                b"iso4217:USD</xbrli:measure></xbrli:unit>", 1)
    with pytest.raises(xbrl.FilingError, match="USD"):
        xbrl.parse_filing(data, Q4)


def test_figures_that_contradict_their_rounding_are_refused():
    """A filing in crores declared as rupees rounded to crores would read 10^7 too small."""
    text = (FIXTURES / Q4).read_text(encoding="utf-8")
    import re
    shrunk = re.sub(r'(decimals="-7">)(-?\d+)0000000<', lambda m: f"{m.group(1)}{m.group(2)}<", text)
    with pytest.raises(xbrl.FilingError, match="rounding"):
        xbrl.parse_filing(shrunk.encode(), Q4)


def test_a_filing_that_does_not_say_its_basis_is_refused():
    data = (FIXTURES / Q4).read_bytes().replace(b">Consolidated<", b">Unknown<")
    with pytest.raises(xbrl.FilingError, match="standalone or consolidated"):
        xbrl.parse_filing(data, Q4)


def test_other_documents_are_not_taken_for_filings():
    with pytest.raises(xbrl.FilingError):
        xbrl.parse_filing(b"<html><body>not xbrl</body></html>", "page.xml")
    with pytest.raises(xbrl.FilingError):
        xbrl.parse_filing(b"<broken", "broken.xml")


# --- Shareholding -------------------------------------------------------------------

def test_2025_shareholding_in_fractions_is_read_as_percent():
    f = parse(SHP_2025)
    v = f.values
    assert f.quarter_end == "2026-06-30" and f.isin == "INE999Z01019"
    assert (v["promoter_pct"], v["fii_pct"], v["dii_pct"], v["govt_pct"], v["public_pct"]) == (55, 18, 15, 0.5, 11.5)
    assert v["pledged_pct"] == 10 and v["encumbered_pct"] == 12
    assert v["num_shareholders"] == 250000 and v["total_shares"] == 100_000_000
    assert f.warnings == []


def test_one_shareholders_own_row_is_not_the_categorys_total():
    assert parse(SHP_2025).values["promoter_pct"] == 55  # not the 30% of the promoter with a second dimension


def test_2020_shareholding_in_percents_derives_domestic_institutions():
    v = parse(SHP_2020).values
    assert v["promoter_pct"] == 56 and v["fii_pct"] == 19 and v["dii_pct"] == 11  # institutions 30 less FPIs 19
    assert v["govt_pct"] == 0.5 and v["public_pct"] == 13.5
    assert v["pledged_pct"] is None and v["encumbered_pct"] == 5  # reported together before 2025


# --- One alias table ------------------------------------------------------------------

def test_yahoo_and_the_filings_share_one_alias_table():
    assert yahoo.ALIASES is field_aliases.ALIASES["yahoo"]
    phase1_income = set(field_aliases.ALIASES["yahoo"]["income"])
    xbrl_fields = set(field_aliases.ALIASES["xbrl"]["income"]) | {"total_expenses", "net_interest_income"}
    # Every income field Phase 1's rows read, except operating income (derived from sales and
    # total expenses), is filled from the filings too.
    assert phase1_income - {"operating_income"} <= xbrl_fields
    assert set(field_aliases.ALIASES["yahoo"]["cashflow"]) <= set(field_aliases.ALIASES["xbrl"]["cashflow"]) | {
        "free_cash_flow"}
