"""SEC EDGAR fundamentals: statements as they were filed, not as they read today.

Every other fundamentals vendor serves the current value of a past period and
cuts on the fiscal period end, so a run sees figures the company had not yet
filed, and later restatements replace what was actually published. EDGAR carries
the filing date of every fact, so a run can be limited to what was on file by its
own date.
"""

from __future__ import annotations

from unittest import mock

import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import sec_edgar

_REAL_FETCH = sec_edgar._fetch_json

TICKER_MAP = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _fact(end, val, filed, form="10-K", fp="FY", start=None):
    fact = {"end": end, "val": val, "filed": filed, "form": form, "fy": int(end[:4]), "fp": fp}
    if start:
        fact["start"] = start
    return fact


FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {"us-gaap": {
        "Assets": {"units": {"USD": [
            _fact("2008-09-27", 39_572_000_000, "2008-11-05"),
            _fact("2008-09-27", 36_171_000_000, "2010-01-25", form="10-K/A"),
            _fact("2022-03-26", 350_662_000_000, "2022-04-29", form="10-Q", fp="Q2"),
            _fact("2024-09-28", 364_980_000_000, "2024-11-01"),
        ]}},
        "Liabilities": {"units": {"USD": [_fact("2024-09-28", 308_030_000_000, "2024-11-01")]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            _fact("2024-09-28", 6.08, "2024-11-01", start="2023-09-30"),
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            # One filing reports the quarter and the year to date under one end date.
            _fact("2025-12-31", 81_300_000_000, "2026-01-29", form="10-Q", fp="Q2", start="2025-10-01"),
            _fact("2025-12-31", 158_900_000_000, "2026-01-29", form="10-Q", fp="Q2", start="2025-07-01"),
            _fact("2024-09-28", 391_035_000_000, "2024-11-01", start="2023-09-30"),
        ]}},
    }},
}


@pytest.fixture(autouse=True)
def _no_network_or_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(sec_edgar, "_fetch_json", lambda url: TICKER_MAP if "company_tickers" in url else FACTS)


@pytest.mark.unit
def test_a_us_filer_resolves_to_its_cik():
    assert sec_edgar.cik_for("AAPL") == "0000320193"
    assert sec_edgar.cik_for("aapl") == "0000320193"


@pytest.mark.unit
def test_a_non_filer_is_reported_as_such_not_as_missing_data():
    with pytest.raises(NoMarketDataError, match="not a US SEC filer"):
        sec_edgar.get_balance_sheet("0700.HK", "annual", "2026-01-01")


@pytest.mark.unit
def test_a_restated_figure_reads_as_it_did_at_the_time():
    """The value published then, not the correction filed later."""
    as_filed = sec_edgar.get_balance_sheet("AAPL", "annual", "2009-06-30")
    restated = sec_edgar.get_balance_sheet("AAPL", "annual", "2011-01-01")
    assert "39572" in as_filed and "36171" not in as_filed
    assert "36171" in restated


@pytest.mark.unit
def test_a_period_that_ended_but_was_not_filed_yet_is_not_served():
    """The fiscal year ended 2024-09-28; it reached the public on 2024-11-01."""
    before = sec_edgar.get_balance_sheet("AAPL", "annual", "2024-10-15")
    after = sec_edgar.get_balance_sheet("AAPL", "annual", "2024-11-15")
    assert "2024-09-28" not in before
    assert "2024-09-28" in after and "364980" in after


@pytest.mark.unit
def test_the_quarter_is_not_confused_with_the_year_to_date():
    """One filing carries both spans under the same end date (#MSFT-shaped)."""
    out = sec_edgar.get_income_statement("AAPL", "quarterly", "2026-06-01")
    assert "81300" in out
    assert "158900" not in out


@pytest.mark.unit
def test_a_line_the_filer_does_not_tag_is_named_unavailable():
    out = sec_edgar.get_balance_sheet("AAPL", "annual", "2024-11-15")
    assert "Stockholders Equity" in out and "unavailable" in out
    assert "364980" in out  # the rest of the statement still returns


@pytest.mark.unit
def test_the_report_states_the_vintage_rule():
    out = sec_edgar.get_balance_sheet("AAPL", "annual", "2024-11-15")
    assert "filed on or before 2024-11-15" in out


@pytest.mark.unit
def test_a_filer_with_no_usable_facts_reads_differently_from_a_non_filer(monkeypatch):
    monkeypatch.setattr(sec_edgar, "_fetch_json",
                        lambda url: TICKER_MAP if "company_tickers" in url else {"facts": {}})
    with pytest.raises(NoMarketDataError, match="no us-gaap facts"):
        sec_edgar.get_balance_sheet("AAPL", "annual", "2026-01-01")


@pytest.mark.unit
def test_company_facts_are_fetched_once_per_company_not_once_per_date(tmp_path, monkeypatch):
    """A sweep asks for many dates; the filing history is the same file."""
    calls = []
    monkeypatch.setattr(sec_edgar, "_fetch_json",
                        lambda url: calls.append(url) or (TICKER_MAP if "company_tickers" in url else FACTS))
    for date in ("2024-11-15", "2025-01-15", "2025-06-15"):
        sec_edgar.get_balance_sheet("AAPL", "annual", date)
    assert len([u for u in calls if "companyfacts" in u]) == 1


@pytest.mark.unit
def test_it_works_unconfigured_and_takes_the_caller_s_own_contact(monkeypatch):
    """SEC returns 403 for a User-Agent with no contact address, so the default
    carries one; a caller who sets their own replaces it."""
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    assert "@" in sec_edgar._user_agent()

    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "MyDesk research@example.com")
    assert sec_edgar._user_agent() == "MyDesk research@example.com"


@pytest.mark.unit
def test_a_throttle_lets_the_next_vendor_try(monkeypatch):
    """SEC throttles by refusing the request; the router then tries yfinance."""
    import requests

    from tradingagents.dataflows.errors import VendorRateLimitError

    def _throttled(*a, **k):
        raise requests.HTTPError(response=mock.Mock(status_code=429))

    monkeypatch.setattr(sec_edgar.requests, "get", _throttled)
    with pytest.raises(VendorRateLimitError):
        _REAL_FETCH("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")


@pytest.mark.unit
def test_values_do_not_break_the_columns():
    """Figures run to the billions; a thousands separator would split the field."""
    out = sec_edgar.get_balance_sheet("AAPL", "annual", "2024-11-15")
    body = [row for row in out.splitlines() if row.startswith("Total Assets")][0]
    assert body.count(",") == out.splitlines()[3].count(",")


@pytest.mark.unit
def test_a_per_share_figure_keeps_its_own_unit():
    """Statements are reported in millions, but EPS is dollars per share: scaling
    it the same way prints a real figure as zero."""
    out = sec_edgar.get_income_statement("AAPL", "annual", "2024-11-15")
    row = [r for r in out.splitlines() if r.startswith("Diluted EPS")][0]
    assert "6.08" in row
    assert "USD/shares" in row or "per share" in row


@pytest.mark.unit
def test_every_row_has_one_cell_per_period():
    """An untagged line still has to line up with the columns, or the table is
    misread by position."""
    out = sec_edgar.get_balance_sheet("AAPL", "annual", "2024-11-15")
    table = [r for r in out.splitlines() if r and not r.startswith("#")]
    widths = {row.count(",") for row in table}
    assert len(widths) == 1, table


@pytest.mark.unit
def test_a_server_error_lets_the_next_vendor_try(monkeypatch):
    import requests

    from tradingagents.dataflows.errors import VendorError

    def _server_error(*a, **k):
        raise requests.HTTPError(response=mock.Mock(status_code=503))

    monkeypatch.setattr(sec_edgar.requests, "get", _server_error)
    with pytest.raises(VendorError):  # not a bare HTTPError
        _REAL_FETCH("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")


@pytest.mark.unit
def test_older_periods_fall_back_to_the_tag_the_filer_used_then():
    """Filers renamed lines when the revenue standard changed, so one tag covers
    only recent years. Each period takes one tag, never a sum of two."""
    facts = {"Revenues": {"units": {"USD": [_fact("2015-09-26", 233_715_000_000, "2015-10-28",
                                                 start="2014-09-28")]}},
             "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                 _fact("2024-09-28", 391_035_000_000, "2024-11-01", start="2023-09-30")]}}}
    values, unit = sec_edgar._as_of(facts, ("RevenueFromContractWithCustomerExcludingAssessedTax",
                                            "Revenues"), "2026-01-01", (300, 400))
    assert values == {"2015-09-26": 233_715_000_000, "2024-09-28": 391_035_000_000}
    assert unit == "USD"


@pytest.mark.unit
def test_a_period_reported_under_two_tags_takes_the_preferred_one_not_both():
    facts = {"Revenues": {"units": {"USD": [_fact("2024-09-28", 111, "2024-11-01", start="2023-09-30")]}},
             "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                 _fact("2024-09-28", 999, "2024-11-01", start="2023-09-30")]}}}
    values, _ = sec_edgar._as_of(facts, ("RevenueFromContractWithCustomerExcludingAssessedTax",
                                         "Revenues"), "2026-01-01", (300, 400))
    assert values == {"2024-09-28": 999}


@pytest.mark.unit
def test_the_default_identification_tracks_the_installed_version(monkeypatch):
    """A release should identify itself, not a version frozen in the source."""
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    monkeypatch.setattr(sec_edgar.metadata, "version", lambda name: "9.9.9")
    assert sec_edgar._user_agent() == "TradingAgents/9.9.9 (contact@example.com)"


@pytest.mark.unit
def test_an_uninstalled_checkout_still_identifies_itself(monkeypatch):
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)

    def _missing(name):
        raise sec_edgar.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(sec_edgar.metadata, "version", _missing)
    assert "@" in sec_edgar._user_agent()


@pytest.mark.unit
def test_capital_expenditure_is_found_under_either_tag_filers_use(monkeypatch):
    """NVIDIA and Amazon report purchases of productive assets, not of property and equipment."""
    facts = {"facts": {"us-gaap": {"PaymentsToAcquireProductiveAssets": {"units": {"USD": [
        _fact("2024-12-31", 70_000_000, "2025-02-10", start="2024-01-01")]}}}}}
    monkeypatch.setattr(sec_edgar, "_fetch_json",
                        lambda url: TICKER_MAP if "company_tickers" in url else facts)
    out = sec_edgar.get_cashflow("AAPL", "annual", "2025-03-01")
    assert [r for r in out.splitlines() if r.startswith("Capital Expenditure")] == ["Capital Expenditure,70"]


def _columns(out):
    return [line for line in out.splitlines() if line.startswith(",")][0].split(",")[1:]


@pytest.mark.unit
def test_an_annual_balance_sheet_has_no_quarter_end_columns():
    """A balance has no span, so a 10-Q's quarter-end balance passed as annual."""
    annual = _columns(sec_edgar.get_balance_sheet("AAPL", "annual", "2024-11-15"))
    quarterly = _columns(sec_edgar.get_balance_sheet("AAPL", "quarterly", "2024-11-15"))
    assert "2022-03-26" not in annual and "2024-09-28" in annual
    assert "2022-03-26" in quarterly


@pytest.mark.unit
def test_a_twelve_month_total_from_a_quarterly_report_is_not_a_fiscal_year(monkeypatch):
    """Amazon's 10-Qs report trailing twelve months, which passed the annual span
    check and read as fiscal years overlapping the real ones."""
    facts = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
        _fact("2024-12-31", 115_000_000_000, "2025-02-07", start="2024-01-01"),
        _fact("2025-03-31", 113_000_000_000, "2025-05-02", form="10-Q", fp="Q1", start="2024-04-01"),
    ]}}}}}
    monkeypatch.setattr(sec_edgar, "_fetch_json",
                        lambda url: TICKER_MAP if "company_tickers" in url else facts)
    assert _columns(sec_edgar.get_cashflow("AAPL", "annual", "2025-06-01")) == ["2024-12-31"]


@pytest.mark.unit
def test_a_recast_outside_the_annual_report_still_counts_from_its_filing(monkeypatch):
    """Filers recast past years in an 8-K after a split or spin-off. The annual
    report decides the columns; the value is the latest filing of any form."""
    facts = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {"USD/shares": [
        _fact("2017-03-31", 16.97, "2017-06-15", form="20-F", start="2016-04-01"),
        _fact("2017-03-31", 2.12, "2019-09-30", form="6-K", start="2016-04-01"),
    ]}}}}}
    monkeypatch.setattr(sec_edgar, "_fetch_json",
                        lambda url: TICKER_MAP if "company_tickers" in url else facts)

    def eps(date):
        out = sec_edgar.get_income_statement("AAPL", "annual", date)
        return [line for line in out.splitlines() if line.startswith("Diluted EPS")][0].split(",")[1]

    assert eps("2019-01-01") == "16.97"
    assert eps("2020-01-01") == "2.12"
