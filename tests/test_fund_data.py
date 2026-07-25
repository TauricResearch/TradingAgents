from types import SimpleNamespace

import pandas as pd

from tradingagents.agents.utils.fund_data_tools import (
    _snapshot,
    use_preloaded_fund_snapshot,
)
from tradingagents.dataflows.fund_data import fetch_fund_snapshot
from tradingagents.instruments import AssetType, FundType, InstrumentDescriptor


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
        self.info = {
            "category": "Large Blend",
            "legalType": "Exchange Traded Fund",
            "fundFamily": "Example",
            "fundInceptionDate": 946684800,
            "totalAssets": 1000,
            "annualReportExpenseRatio": 0.001,
            "yield": 0.012,
            "navPrice": 100,
            "navPriceDate": 1767225600,
            "regularMarketPrice": 101,
            "regularMarketTime": 1767225600,
        }
        self.funds_data = SimpleNamespace(
            top_holdings=pd.DataFrame(
                {"Name": ["Example Co"], "Holding Percent": [7.5]}, index=["EXM"]
            ),
            sector_weightings={"technology": 32.0},
            asset_classes={"stockPosition": 0.95},
        )

    def history(self, start, end, auto_adjust=False):
        index = pd.date_range("2025-01-01", "2026-01-03", freq="D", tz="UTC")
        values = [100 + i / 100 for i in range(len(index))]
        return pd.DataFrame({"Adj Close": values, "Close": values}, index=index)


def descriptor():
    return InstrumentDescriptor(
        requested_symbol="SPY",
        canonical_symbol="SPY",
        asset_type=AssetType.FUND,
        fund_type=FundType.ETF,
    )


def test_normalizes_complete_fund_and_enforces_date_boundary():
    snapshot = fetch_fund_snapshot(
        descriptor(), "2026-01-01", "QQQ", ticker_factory=FakeTicker
    )
    assert snapshot.profile.category == "Large Blend"
    assert snapshot.profile.expense_ratio == 0.001
    assert snapshot.top_holdings[0].weight == 0.075
    assert snapshot.sectors == {"technology": 0.32}
    assert max(item["date"] for item in snapshot.price_series) == "2026-01-01"
    assert "latest available metadata" in " ".join(snapshot.warnings)


def test_holdings_failure_retains_profile_and_performance():
    class PartialTicker(FakeTicker):
        @property
        def funds_data(self):
            raise RuntimeError("authorization=secret-token")

        @funds_data.setter
        def funds_data(self, value):
            pass

    snapshot = fetch_fund_snapshot(
        descriptor(), "2026-01-01", ticker_factory=PartialTicker
    )
    assert snapshot.profile.category == "Large Blend"
    assert snapshot.price_series
    assert snapshot.top_holdings == []
    assert "secret-token" not in " ".join(snapshot.warnings)


def test_preloaded_normalized_snapshot_is_shared_by_fund_tools():
    normalized = fetch_fund_snapshot(
        descriptor(), "2026-01-01", "QQQ", ticker_factory=FakeTicker
    ).to_dict()
    normalized["analysis_date"] = "2026-01-01"
    normalized["benchmark_symbol"] = "QQQ"
    with use_preloaded_fund_snapshot(normalized):
        first = _snapshot("SPY", "2026-01-01", "QQQ")
        first["profile"]["category"] = "mutated"
        second = _snapshot("SPY", "2026-01-01", "QQQ")
    assert second["profile"]["category"] == "Large Blend"
