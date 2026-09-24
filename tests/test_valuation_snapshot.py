"""Point-in-time valuation: split adjustment and stale-input guards (#1374).

``get_valuation`` prices a filed cover page share count with the as-traded
close. The two facts come from different clocks — the count from a filing
cover date, the price from a trading day — and every split between them has
to be reconciled before the product means anything. These tests pin the
reconciliation and the guards that keep stale inputs out of the snapshot.
"""

import pandas as pd
import pytest

from tradingagents.dataflows.vendors import sec_edgar


def _facts(dei_shares, us_gaap=None):
    """Facts payload shaped like the SEC company-facts document."""
    units = [{"end": end, "filed": filed, "val": val} for end, filed, val in dei_shares]
    facts = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": units}}}}}
    if us_gaap:
        facts["facts"]["us-gaap"] = us_gaap
    return facts


def _close_series(closes):
    """Close series shaped like yfinance serves it: exchange-local, tz-aware.

    The stub must mirror the real transport — a naive index would never
    exercise the tz-aware comparison the production path runs.
    """
    return pd.Series(
        [price for _, price in closes],
        index=pd.DatetimeIndex([when for when, _ in closes], name="Date", tz="America/New_York"),
    )


@pytest.fixture
def stub_env(monkeypatch):
    """Patch the three network calls get_valuation depends on."""
    state = {"dei_shares": [], "us_gaap": None, "closes": [], "splits": None}

    def fake_facts(ticker, curr_date):
        return curr_date or "2025-01-01", _facts(state["dei_shares"], state["us_gaap"])

    def fake_history(period="5y", auto_adjust=False):
        assert auto_adjust is False, "valuation must price with the as-traded close"
        if not state["closes"]:
            return pd.DataFrame()
        return pd.DataFrame({"Close": _close_series(state["closes"])})

    def fake_splits(ticker):
        return state["splits"]

    monkeypatch.setattr(sec_edgar, "_filer_facts", fake_facts)
    monkeypatch.setattr(sec_edgar, "yf_retry", lambda fn: fn())
    monkeypatch.setattr(
        sec_edgar.yf,
        "Ticker",
        lambda symbol: type(
            "T",
            (),
            {
                "history": staticmethod(fake_history),
                "splits": property(lambda self: state["splits"]),
            },
        )(),
    )
    return state


class TestSplitAdjustment:
    """A split between the cover date and the price date rescales the count."""

    def test_split_before_price_rescales_shares(self, stub_env):
        # NVDA-shaped: analysis after the 10:1 split (2024-06-07). The newest
        # cover page by then was still filed pre-split (cover 2024-05-17,
        # 2,470M shares), and the last close is the post-split as-traded price.
        # The count must be scaled x10 before pricing: 131.88 x 24.7B is the
        # ~$3.26T cap that stood, not 131.88 x 2.47B = ~$326B.
        stub_env["dei_shares"] = [("2024-05-17", "2024-05-22", 2_470_000_000)]
        stub_env["closes"] = [("2024-06-13", 131.88)]
        stub_env["splits"] = pd.Series(
            [10.0], index=pd.DatetimeIndex(["2024-06-07"], tz="America/New_York")
        )
        out = sec_edgar.get_valuation("NVDA", "2024-06-14")
        assert "24,700,000,000" in out
        assert "3257" in out  # 131.88 * 24.7 = 3257.4 -> $3.26T

    def test_prepair_analysis_date_not_off_by_split_ratio(self, stub_env):
        # The #1377 rejection case, pinned. Analysis date 2024-05-15 is before
        # the split. Yahoo's Close divides out even splits that happened after
        # the analysis date (117.71 = 1177.10 / 10), so the price must be
        # re-inflated by the splits after the price day before it is priced
        # against the pre-split cover count: 1177.10 x 2.462B = ~$2.90T.
        # The rejected PR priced 117.71 against the filed count and read
        # ~$290B — off by the 10:1 ratio.
        stub_env["dei_shares"] = [("2024-04-26", "2024-04-26", 2_462_000_000)]
        stub_env["closes"] = [("2024-05-15", 117.71)]  # Yahoo-shaped: retro-adjusted
        stub_env["splits"] = pd.Series(
            [10.0], index=pd.DatetimeIndex(["2024-06-07"], tz="America/New_York")
        )
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        assert "1177.10 USD" in out
        assert "2,462,000,000" in out
        assert "2898" in out  # 1177.10 * 2.462 = 2898.1 -> $2.90T
        assert "289.8" not in out  # the split-ratio-off cap must not appear

    def test_no_split_between_dates_leaves_count_untouched(self, stub_env):
        stub_env["dei_shares"] = [("2024-04-26", "2024-04-26", 1_000_000_000)]
        stub_env["closes"] = [("2024-05-15", 100.0)]
        stub_env["splits"] = pd.Series(
            [2.0], index=pd.DatetimeIndex(["2024-01-10"], tz="America/New_York")
        )
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        # Split before the cover date is already inside the count.
        assert "1,000,000,000" in out
        assert "100.00B USD" in out

    def test_split_on_cover_date_is_already_in_count(self, stub_env):
        stub_env["dei_shares"] = [("2024-06-07", "2024-06-10", 24_620_000_000)]
        stub_env["closes"] = [("2024-06-10", 121.79)]
        stub_env["splits"] = pd.Series(
            [10.0], index=pd.DatetimeIndex(["2024-06-07"], tz="America/New_York")
        )
        out = sec_edgar.get_valuation("NVDA", "2024-06-10")
        # The split is on the cover date itself: the count was measured with
        # it in place, so no further scaling applies.
        assert "24,620,000,000" in out
        assert "2998" in out  # 121.79 * 24.62 = 2998.5 -> $3.00T


class TestStaleGuards:
    """Inputs older than the window do not enter the snapshot."""

    def test_stale_share_count_withheld(self, stub_env):
        # Cover count measured 2023-01-01, price date 2024-05-15: 500 days.
        stub_env["dei_shares"] = [("2023-01-01", "2023-01-01", 1_000_000_000)]
        stub_env["closes"] = [("2024-05-15", 100.0)]
        stub_env["splits"] = None
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        assert "over 200 days old" in out
        assert "1,000,000,000" not in out

    def test_stale_price_withheld(self, stub_env):
        # Analysis 2024-05-15 but the last settled close is 400+ days older
        # (a delisted name, say): the close is withheld with its date, not
        # multiplied into a fabricated market cap.
        stub_env["dei_shares"] = [("2024-04-26", "2024-04-26", 1_000_000_000)]
        stub_env["closes"] = [("2023-05-15", 100.0)]
        stub_env["splits"] = None
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        assert "last settled close 2023-05-15 is over 200 days old" in out
        assert "100.00B USD" not in out

    def test_fresh_inputs_flow_through(self, stub_env):
        stub_env["dei_shares"] = [("2024-04-26", "2024-04-16", 1_000_000_000)]
        stub_env["closes"] = [("2024-05-15", 100.0)]
        stub_env["splits"] = None
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        assert "1,000,000,000" in out
        assert "100.00B USD" in out


class TestProvenance:
    """Every row carries dates; unavailable metrics carry reasons."""

    def test_table_carries_as_of_header(self, stub_env):
        stub_env["dei_shares"] = [("2024-04-26", "2024-04-26", 1_000_000_000)]
        stub_env["closes"] = [("2024-05-15", 100.0)]
        stub_env["splits"] = None
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        assert "Point-in-time as of: 2024-05-15" in out
        assert "| Metric | Value | As-of / filed |" in out

    def test_enterprise_value_not_derived(self, stub_env):
        stub_env["dei_shares"] = [("2024-04-15", "2024-04-15", 1_000_000_000)]
        stub_env["closes"] = [("2024-05-15", 100.0)]
        stub_env["splits"] = None
        out = sec_edgar.get_valuation("NVDA", "2024-05-15")
        assert "Enterprise Value" in out
        assert "not derivable" in out
