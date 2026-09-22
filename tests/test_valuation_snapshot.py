"""Point-in-time valuation: what was public, when it was public (#1374).

Vendors withhold market cap and multiples on a past analysis date (#1300) —
they move with today's quote. A backtest is then left with statements but no
valuation at all. This builds one instead from what was on file: the last
settled close, the cover page share count, filed diluted EPS and filed
stockholders equity, each carrying its own as-of date, and each unbuildable
metric reported unavailable with a reason instead of a fabricated number.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import sec_edgar
from tradingagents.dataflows.errors import NoMarketDataError

TICKER_MAP = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _fact(end, val, filed, form="10-K", fp="FY", start=None):
    fact = {"end": end, "val": val, "filed": filed, "form": form, "fy": int(end[:4]), "fp": fp}
    if start:
        fact["start"] = start
    return fact


def _cover(end, val, filed):
    return {"end": end, "val": val, "filed": filed}


FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            _cover("2022-10-21", 15_634_856_000, "2022-10-28"),
            _cover("2023-09-30", 15_550_061_000, "2023-11-03"),
            _cover("2023-09-30", 15_510_074_000, "2023-12-08"),  # amended cover
            _cover("2024-09-21", 15_115_823_000, "2024-11-01"),
        ]}}},
        "us-gaap": {
            "StockholdersEquity": {"units": {"USD": [
                _fact("2022-09-24", 50_672_000_000, "2022-10-28"),
                _fact("2023-09-30", 62_146_000_000, "2023-11-03"),
                _fact("2024-09-28", 56_950_000_000, "2024-11-01"),
            ]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [
                _fact("2023-09-30", 6.13, "2023-11-03", start="2022-09-25"),
                _fact("2024-09-28", 6.08, "2024-11-01", start="2023-10-01"),
            ]}},
        },
    },
}

# 2023-11-15 close, six sessions back to 2023-11-08. The analysis date sits
# after the FY2023 filing (2023-11-03) and before the FY2024 one (2024-11-01),
# so the run must read the 2023 cover page, equity and EPS — never 2024's.
_PRICE_ROWS = [
    ("2023-11-08", 182.89), ("2023-11-09", 182.41), ("2023-11-10", 186.40),
    ("2023-11-13", 185.56), ("2023-11-14", 187.44), ("2023-11-15", 188.01),
]
PRICE_FRAME = pd.DataFrame(
    {"Date": pd.to_datetime([r[0] for r in _PRICE_ROWS]), "Close": [r[1] for r in _PRICE_ROWS]}
)


@pytest.fixture(autouse=True)
def _no_network_or_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sec_edgar, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(
        sec_edgar, "_fetch_json",
        lambda url: TICKER_MAP if "company_tickers" in url else FACTS,
    )
    monkeypatch.setattr(
        sec_edgar, "load_ohlcv",
        lambda symbol, curr_date, fill_gaps=True: PRICE_FRAME.copy(),
    )


@pytest.mark.unit
def test_market_cap_multiplies_the_close_by_the_public_share_count():
    out = sec_edgar.get_valuation("AAPL", "2023-11-15")
    # 188.01 * 15,550,061,000 = 2.9236...e12 → "2923.57B USD"
    assert "2923.57B USD" in out
    assert "15,550,061,000" in out
    assert "measured 2023-09-30" in out
    assert "filed 2023-11-03" in out  # when the count became public


@pytest.mark.unit
def test_an_amended_cover_counts_from_its_filing_date():
    # Two covers restate the same cover date (2023-09-30): the original filed
    # 2023-11-03 and the amendment 2023-12-08. A run between them must read
    # the original; a run after the amendment must read the revised count.
    before = sec_edgar.get_valuation("AAPL", "2023-12-01")
    assert "15,550,061,000" in before
    assert "15,510,074,000" not in before

    after = sec_edgar.get_valuation("AAPL", "2023-12-15")
    assert "15,510,074,000" in after
    assert "15,550,061,000" not in after
    # 188.01 * 15,510,074,000 = 2.9160...e12 → "2916.05B USD"
    assert "2916.05B USD" in after


@pytest.mark.unit
def test_a_2024_fact_does_not_leak_into_a_2023_run():
    out = sec_edgar.get_valuation("AAPL", "2023-11-15")
    assert "2024-11-01" not in out
    assert "6.08" not in out  # FY2024 diluted EPS
    assert "56,950,000,000" not in out
    assert "15,115,823,000" not in out  # FY2024 cover page


@pytest.mark.unit
def test_multiples_carry_their_own_as_of_dates():
    out = sec_edgar.get_valuation("AAPL", "2023-11-15")
    # P/E = 188.01 / 6.13 = 30.67; P/B = 188.01 / (62146/15550.061) = 47.04
    assert "30.67" in out
    assert "47.04" in out
    assert "equity as of 2023-09-30" in out
    assert "EPS for period ending 2023-09-30" in out


@pytest.mark.unit
def test_no_filing_yet_reports_unavailable_not_a_number():
    out = sec_edgar.get_valuation("AAPL", "2010-06-30")
    assert "unavailable" in out
    assert "B USD" not in out  # no market cap without filed facts


@pytest.mark.unit
def test_the_us_filer_error_type_is_preserved_for_the_router():
    with pytest.raises(NoMarketDataError, match="not a US SEC filer"):
        sec_edgar.get_valuation("0700.HK", "2023-11-15")


@pytest.mark.unit
def test_missing_price_leaves_filing_facts_served():
    def _no_price(symbol, curr_date, fill_gaps=True):
        raise NoMarketDataError(symbol, symbol, "no price rows")

    from unittest import mock
    with mock.patch.object(sec_edgar, "load_ohlcv", _no_price):
        out = sec_edgar.get_valuation("AAPL", "2023-11-15")
    assert "unavailable" in out
    assert "15,550,061,000" in out  # the share count is still served
    assert "no settled close" in out


@pytest.mark.unit
def test_a_non_filer_valuation_via_the_router_reports_no_data_not_a_crash():
    from tradingagents.dataflows.interface import route_to_vendor
    out = route_to_vendor("get_valuation", "0700.HK", "2023-11-15")
    assert out.startswith("NO_DATA_AVAILABLE")


@pytest.mark.unit
def test_the_withhold_notice_points_at_the_valuation_tool():
    from tradingagents.dataflows.date_window import withhold_live_profile
    notice = withhold_live_profile("2023-11-15", "AAPL")
    assert "get_valuation" in notice


@pytest.mark.unit
def test_a_loss_making_period_reports_not_meaningful_not_a_negative_multiple():
    # Negative diluted EPS (a loss quarter): P/E must not print as a negative
    # number an agent would read as "cheap".
    loss_facts = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                _cover("2023-09-30", 15_550_061_000, "2023-11-03"),
            ]}}},
            "us-gaap": {
                "EarningsPerShareDiluted": {"units": {"USD/shares": [
                    _fact("2023-09-30", -1.44, "2023-11-03", start="2022-09-25"),
                ]}},
            },
        },
    }
    from unittest import mock
    with mock.patch.object(sec_edgar, "_fetch_json",
                           lambda url: TICKER_MAP if "company_tickers" in url else loss_facts):
        out = sec_edgar.get_valuation("AAPL", "2023-11-15")
    assert "not meaningful" in out
    assert "diluted EPS is -1.44" in out


@pytest.mark.unit
def test_negative_equity_reports_not_meaningful_not_a_negative_multiple():
    # Negative stockholders equity (insolvency): P/B must not print as a
    # negative number an agent would read as "cheap".
    insolvent_facts = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                _cover("2023-09-30", 15_550_061_000, "2023-11-03"),
            ]}}},
            "us-gaap": {
                "StockholdersEquity": {"units": {"USD": [
                    _fact("2023-09-30", -4_000_000_000, "2023-11-03"),
                ]}},
                "EarningsPerShareDiluted": {"units": {"USD/shares": [
                    _fact("2023-09-30", 6.13, "2023-11-03", start="2022-09-25"),
                ]}},
            },
        },
    }
    from unittest import mock
    with mock.patch.object(sec_edgar, "_fetch_json",
                           lambda url: TICKER_MAP if "company_tickers" in url else insolvent_facts):
        out = sec_edgar.get_valuation("AAPL", "2023-11-15")
    assert "not meaningful" in out
    assert "book value per share is -0.26" in out  # -4e9 / 15.55B shares
