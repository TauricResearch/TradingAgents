from datetime import date

import pytest

from tradingagents.research_platform.data_contracts import InstrumentIdentity
from tradingagents.research_platform.tushare_provider import (
    TushareDataUnavailableError,
    TushareProProvider,
    canonical_tushare_symbol,
)


class FakeProClient:
    def __init__(self):
        self.calls = []

    def daily(self, **kwargs):
        self.calls.append(("daily", kwargs))
        return [
            {
                "trade_date": "20260105",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "vol": 1000,
            },
            {
                "trade_date": "20260102",
                "open": 98,
                "high": 101,
                "low": 97,
                "close": 100,
                "vol": 900,
            },
        ]

    def adj_factor(self, **kwargs):
        self.calls.append(("adj_factor", kwargs))
        return [
            {"trade_date": "20260105", "adj_factor": 1.0},
            {"trade_date": "20260102", "adj_factor": 1.0},
        ]

    def daily_basic(self, **kwargs):
        self.calls.append(("daily_basic", kwargs))
        return [
            {"trade_date": "20260105", "pe": 20.5, "pe_ttm": 21.5, "pb": 3.2, "total_mv": 100000},
        ]

    def stock_basic(self, **kwargs):
        self.calls.append(("stock_basic", kwargs))
        return [
            {
                "ts_code": "600519.SH",
                "name": "Kweichow Moutai",
                "area": "Guizhou",
                "industry": "Liquor",
                "market": "Main board",
                "exchange": "SSE",
                "list_date": "20010827",
            }
        ]

    def income(self, **kwargs):
        self.calls.append(("income", kwargs))
        return [
            {
                "ann_date": "20260104",
                "end_date": "20251231",
                "total_revenue": 1000.0,
                "n_income": 100.0,
                "operate_profit": 110.0,
            }
        ]

    def balancesheet(self, **kwargs):
        self.calls.append(("balancesheet", kwargs))
        return [
            {
                "ann_date": "20260104",
                "end_date": "20251231",
                "total_assets": 500.0,
                "total_liab": 100.0,
                "total_hldr_eqy_exc_min_int": 400.0,
            }
        ]

    def cashflow(self, **kwargs):
        self.calls.append(("cashflow", kwargs))
        return [
            {
                "ann_date": "20260104",
                "end_date": "20251231",
                "n_cashflow_act": 120.0,
                "free_cashflow": 80.0,
            }
        ]

    def fina_indicator(self, **kwargs):
        self.calls.append(("fina_indicator", kwargs))
        return [
            {
                "ann_date": "20260104",
                "end_date": "20251231",
                "roe": 15.0,
                "debt_to_assets": 20.0,
                "current_ratio": 2.0,
            }
        ]

    def forecast(self, **kwargs):
        self.calls.append(("forecast", kwargs))
        return [
            {
                "ann_date": "20260105",
                "end_date": "20251231",
                "type": "pre_increase",
                "p_change_min": 10.0,
                "p_change_max": 20.0,
                "summary": "Fixture earnings forecast.",
            },
            {
                "ann_date": "20260106",
                "end_date": "20251231",
                "type": "pre_increase",
            },
        ]

    def express(self, **kwargs):
        self.calls.append(("express", kwargs))
        return [
            {
                "ann_date": "20260104",
                "end_date": "20251231",
                "revenue": 1000.0,
                "n_income": 100.0,
                "yoy_net_profit": 15.0,
                "perf_summary": "Fixture earnings express.",
            }
        ]

    def dividend(self, **kwargs):
        self.calls.append(("dividend", kwargs))
        return [
            {
                "ann_date": "20260103",
                "end_date": "20251231",
                "cash_div_tax": 3.2,
                "record_date": "20260115",
                "ex_date": "20260116",
                "div_proc": "proposal",
            }
        ]

    def repurchase(self, **kwargs):
        self.calls.append(("repurchase", kwargs))
        return [
            {
                "ann_date": "20260102",
                "end_date": "20251231",
                "proc": "completed",
                "vol": 100.0,
                "amount": 200.0,
            }
        ]

    def fina_audit(self, **kwargs):
        self.calls.append(("fina_audit", kwargs))
        return [
            {
                "ann_date": "20260101",
                "end_date": "20251231",
                "audit_result": "standard unqualified",
                "audit_agency": "Fixture audit firm",
            }
        ]

    def hk_daily_adj(self, **kwargs):
        self.calls.append(("hk_daily_adj", kwargs))
        return [
            {
                "trade_date": "20260105",
                "open": 400,
                "high": 410,
                "low": 395,
                "close": 405,
                "vol": 2000,
                "adj_factor": 2.0,
                "turnover_ratio": 0.4,
                "total_mv": 500000,
            }
        ]


def test_tushare_provider_normalizes_a_share_daily_and_basic_snapshot():
    client = FakeProClient()
    provider = TushareProProvider(pro_client=client)
    identity = InstrumentIdentity(symbol="600519")

    bars = provider.get_price_bars(identity, date(2026, 1, 1), date(2026, 1, 5))
    fundamentals = provider.get_fundamentals(identity, as_of_date=date(2026, 1, 5))

    assert [bar.date for bar in bars] == [date(2026, 1, 2), date(2026, 1, 5)]
    assert bars[-1].currency == "CNY"
    assert bars[-1].adjusted_close == 103
    assert bars[-1].adjustment_factor == 1.0
    assert bars[-1].adjustment_method == "forward_adjusted"
    assert bars[-1].provenance.source == "tushare.pro.daily+adj_factor"
    assert client.calls[0] == (
        "daily",
        {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"},
    )
    assert client.calls[1] == (
        "adj_factor",
        {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"},
    )
    assert client.calls[2] == (
        "daily_basic",
        {"ts_code": "600519.SH", "start_date": "20241201", "end_date": "20260105"},
    )
    assert client.calls[3] == (
        "stock_basic",
        {
            "ts_code": "600519.SH",
            "fields": "ts_code,name,area,industry,market,exchange,list_date",
        },
    )
    assert fundamentals[0].metrics["pe_ratio_ttm"] == 21.5
    assert fundamentals[0].metrics["company_name"] == "Kweichow Moutai"
    assert fundamentals[0].metrics["company_industry"] == "Liquor"
    assert fundamentals[0].metrics["total_market_value_10k_cny"] == 100000
    assert fundamentals[1].period_end == date(2025, 12, 31)
    assert fundamentals[1].metrics["reported_total_revenue"] == 1000.0
    assert fundamentals[1].metrics["operating_cashflow_to_net_income_ratio"] == 1.2
    assert client.calls[-4:] == [
        ("income", {"ts_code": "600519.SH", "start_date": "20240106", "end_date": "20260105"}),
        (
            "balancesheet",
            {"ts_code": "600519.SH", "start_date": "20240106", "end_date": "20260105"},
        ),
        ("cashflow", {"ts_code": "600519.SH", "start_date": "20240106", "end_date": "20260105"}),
        (
            "fina_indicator",
            {"ts_code": "600519.SH", "start_date": "20240106", "end_date": "20260105"},
        ),
    ]


def test_tushare_provider_forward_adjusts_across_a_corporate_action():
    class CorporateActionClient(FakeProClient):
        def daily(self, **kwargs):
            self.calls.append(("daily", kwargs))
            return [
                {
                    "trade_date": "20260105",
                    "open": 50,
                    "high": 52,
                    "low": 49,
                    "close": 50,
                    "vol": 1000,
                },
                {
                    "trade_date": "20260102",
                    "open": 99,
                    "high": 101,
                    "low": 98,
                    "close": 100,
                    "vol": 900,
                },
            ]

        def adj_factor(self, **kwargs):
            self.calls.append(("adj_factor", kwargs))
            return [
                {"trade_date": "20260105", "adj_factor": 2.0},
                {"trade_date": "20260102", "adj_factor": 1.0},
            ]

    bars = TushareProProvider(pro_client=CorporateActionClient()).get_price_bars(
        InstrumentIdentity(symbol="600519"),
        date(2026, 1, 1),
        date(2026, 1, 5),
    )

    assert [bar.close for bar in bars] == [100, 50]
    assert [bar.adjusted_close for bar in bars] == [50, 50]
    assert all(bar.adjustment_method == "forward_adjusted" for bar in bars)


def test_tushare_provider_keeps_raw_prices_when_adjustment_endpoint_is_unavailable():
    class NoAdjustmentClient(FakeProClient):
        def adj_factor(self, **kwargs):
            raise RuntimeError("permission denied")

    bars = TushareProProvider(pro_client=NoAdjustmentClient()).get_price_bars(
        InstrumentIdentity(symbol="600519"), date(2026, 1, 1), date(2026, 1, 5)
    )
    assert all(bar.adjusted_close is None for bar in bars)
    assert all(bar.adjustment_method is None for bar in bars)
    assert all(bar.provenance.source == "tushare.pro.daily" for bar in bars)


def test_tushare_provider_uses_hk_adjusted_endpoint_and_hkd_currency():
    client = FakeProClient()
    provider = TushareProProvider(pro_client=client)

    bars = provider.get_price_bars(
        InstrumentIdentity(symbol="700.HK"), date(2026, 1, 1), date(2026, 1, 5)
    )
    fundamentals = provider.get_fundamentals(
        InstrumentIdentity(symbol="700.HK"), as_of_date=date(2026, 1, 5)
    )

    assert client.calls[0][0] == "hk_daily_adj"
    assert client.calls[0][1]["ts_code"] == "00700.HK"
    assert bars[0].currency == "HKD"
    assert bars[0].adjusted_close == 405
    assert fundamentals[0].metrics["total_market_value_raw"] == 500000


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("600519.SS", "600519.SH"), ("000001", "000001.SZ"), ("0700.HK", "00700.HK")],
)
def test_tushare_symbol_normalization(symbol, expected):
    assert canonical_tushare_symbol(InstrumentIdentity(symbol=symbol)) == expected


def test_tushare_provider_requires_token_when_not_injected(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(TushareDataUnavailableError, match="TUSHARE_TOKEN"):
        TushareProProvider()


def test_tushare_provider_normalizes_a_share_corporate_events_as_news():
    client = FakeProClient()
    provider = TushareProProvider(pro_client=client)

    news = provider.get_news(
        InstrumentIdentity(symbol="600519"),
        date(2026, 1, 1),
        date(2026, 1, 5),
        as_of_date=date(2026, 1, 5),
    )

    assert [item.title for item in news] == [
        "Earnings forecast announced for period 20251231",
        "Earnings express announced for period 20251231",
        "Dividend plan announced for period 20251231",
        "Share repurchase announced for period 20251231",
        "Audit opinion announced for period 20251231",
    ]
    assert news[0].published_at.isoformat() == "2026-01-05T00:00:00+00:00"
    assert news[0].summary is not None
    assert "profit change minimum (%)" in news[0].summary
    assert news[1].source_id == "tushare:earnings_express:600519.SH:20260104:20251231:base"
    assert "cash dividend per share" in (news[2].summary or "")
    assert "repurchase amount" in (news[3].summary or "")
    assert "audit agency" in (news[4].summary or "")
    assert client.calls == [
        ("forecast", {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"}),
        ("express", {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"}),
        ("dividend", {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"}),
        ("repurchase", {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"}),
        ("fina_audit", {"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260105"}),
    ]


def test_tushare_provider_does_not_infer_hong_kong_corporate_events():
    client = FakeProClient()
    provider = TushareProProvider(pro_client=client)

    news = provider.get_news(
        InstrumentIdentity(symbol="700.HK"), date(2026, 1, 1), date(2026, 1, 5)
    )

    assert news == []
    assert client.calls == []
