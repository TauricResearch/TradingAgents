"""Gulf markets: tickers pass through symbol handling, benchmarks resolve, currencies read right.

Yahoo's Gulf index symbols (^TASI.SR, DFMGI.AE, ^GNRI.QA, ^BKA.KW) serve only their latest quote,
never a history, so the benchmark map uses the USD-listed MSCI country ETFs instead. The
``integration`` tests at the end check that against the live feed.
"""

import copy
from unittest import mock

import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.currencies import currency_for_symbol, main_unit, to_main_unit
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.dataflows.vendors.yahoo import fundamentals
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.memory.settlement import resolve_benchmark

TODAY = "2026-09-26"


@pytest.mark.unit
@pytest.mark.parametrize("ticker, benchmark", [
    ("2222.SR", "KSA"),        # Saudi Aramco, Tadawul
    ("1120.SR", "KSA"),
    ("2222.sr", "KSA"),
    ("EMAAR.AE", "UAE"),       # Dubai Financial Market
    ("QNBK.QA", "QAT"),
    ("NBK.KW", "KWT"),
])
def test_gulf_tickers_resolve_to_their_market_benchmark(ticker, benchmark):
    assert resolve_benchmark(ticker, DEFAULT_CONFIG) == benchmark


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["BBK.BH", "ALDAR.AD"])
def test_a_gulf_market_without_a_working_benchmark_falls_to_the_default_not_a_wrong_one(ticker):
    """Yahoo has no Bahrain index history or ETF and no Abu Dhabi suffix: no entry is made up."""
    assert resolve_benchmark(ticker, DEFAULT_CONFIG) == "SPY"
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["benchmark_ticker"] = "KSA"
    assert resolve_benchmark(ticker, config) == "KSA"


@pytest.mark.unit
@pytest.mark.parametrize("ticker, fragment", [
    ("2222.SR", "USD-listed ETF standing in for the local index"),
    ("NBK.KW", "daily beta against it is understated"),
    ("BBK.BH", "no regional benchmark is configured for the .BH market"),
])
def test_gulf_betas_carry_a_caveat_about_their_benchmark(ticker, fragment):
    from tradingagents.dataflows.benchmarks import benchmark_caveat

    benchmark = resolve_benchmark(ticker, DEFAULT_CONFIG)
    assert fragment in benchmark_caveat(ticker, benchmark, DEFAULT_CONFIG)


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["AAPL", "BRK.B", "0700.HK", "AZN.L", "BTC-USD"])
def test_markets_with_a_real_benchmark_get_no_caveat(ticker):
    from tradingagents.dataflows.benchmarks import benchmark_caveat

    assert benchmark_caveat(ticker, resolve_benchmark(ticker, DEFAULT_CONFIG), DEFAULT_CONFIG) is None


@pytest.mark.unit
def test_an_explicit_benchmark_is_not_second_guessed():
    from tradingagents.dataflows.benchmarks import benchmark_caveat

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["benchmark_ticker"] = "KSA"
    assert benchmark_caveat("BBK.BH", "KSA", config) is None


@pytest.mark.unit
def test_the_risk_block_carries_the_benchmark_caution_for_a_saudi_ticker():
    import numpy as np
    import pandas as pd

    from tradingagents.risk_metrics import service

    dates = pd.bdate_range(end="2026-09-25", periods=300)
    close = 26 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, 300))
    bars = pd.DataFrame({"High": close * 1.01, "Low": close * 0.99, "Close": close}, index=dates)
    with mock.patch.object(service, "get_final_bars", return_value=bars), \
            mock.patch.object(service, "get_final_closes", return_value=pd.Series(close, index=dates)), \
            mock.patch.object(service, "get_latest_observation", side_effect=OSError("off")):
        block = service.risk_block("2222.SR", "2026-09-26", "stock", copy.deepcopy(DEFAULT_CONFIG))
    assert "benchmark: KSA" in block and "caution: KSA is a USD-listed ETF" in block


@pytest.mark.unit
def test_the_map_uses_no_gulf_index_symbol_whose_history_yahoo_does_not_serve():
    benchmarks = set(DEFAULT_CONFIG["benchmark_map"].values())
    assert not benchmarks & {"^TASI.SR", "DFMGI.AE", "^GNRI.QA", "^BKA.KW", "^BKP.KW", "^BKM.KW"}


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["2222.SR", "1120.SR", "EMAAR.AE", "QNBK.QA", "NBK.KW", "BBK.BH"])
def test_gulf_tickers_are_left_alone_by_symbol_normalisation(ticker):
    assert normalize_symbol(ticker) == ticker
    assert normalize_symbol(ticker.lower()) == ticker
    assert safe_ticker_component(ticker) == ticker


@pytest.mark.unit
def test_the_cli_accepts_a_gulf_ticker_typed_in_lower_case():
    from cli.prompts import detect_asset_type, is_valid_ticker_input, parse_ticker

    assert is_valid_ticker_input("2222.sr")
    assert parse_ticker("2222.sr") == "2222.SR"
    assert detect_asset_type("2222.SR").value == "stock"


@pytest.mark.unit
def test_currency_helpers():
    assert currency_for_symbol("2222.SR") == "SAR" and currency_for_symbol("emaar.ae") == "AED"
    assert currency_for_symbol("QNBK.QA") == "QAR" and currency_for_symbol("NBK.KW") == "KWD"
    assert currency_for_symbol("BBK.BH") == "BHD" and currency_for_symbol("AAPL") is None
    assert main_unit("KWF") == "KWD" and main_unit("GBp") == "GBP" and main_unit("SAR") == "SAR"
    assert to_main_unit(870.0, "KWF") == (0.87, "KWD")           # 870 fils
    assert to_main_unit(250.0, "GBp") == (2.5, "GBP")
    assert to_main_unit(26.16, "SAR") == (26.16, "SAR")


def _fundamentals(ticker, info):
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
            mock.patch.object(fundamentals, "yf_retry", lambda fn: info):
        return fundamentals.get_fundamentals(ticker, TODAY)


@pytest.mark.unit
def test_saudi_fundamentals_are_labelled_in_riyals():
    out = _fundamentals("2222.SR", {"longName": "Saudi Aramco", "currency": "SAR", "financialCurrency": "SAR",
                                    "marketCap": 6.3e12, "trailingEps": 1.86, "fiftyTwoWeekHigh": 27.5,
                                    "totalRevenue": 1.9e12})
    assert "Market Cap: 6300000000000.0 SAR" in out and "EPS (TTM): 1.86 SAR" in out
    assert "52 Week High: 27.5 SAR" in out and "Revenue (TTM): 1900000000000.0 SAR" in out


@pytest.mark.unit
def test_kuwait_prices_are_in_fils_and_per_share_figures_in_dinars():
    """Yahoo quotes Boursa Kuwait in fils (KWF, 1/1000 dinar) but gives market cap and EPS in dinars."""
    out = _fundamentals("NBK.KW", {"longName": "National Bank of Kuwait", "currency": "KWF",
                                   "financialCurrency": "KWD", "marketCap": 7.99e9, "trailingEps": 0.06,
                                   "fiftyTwoWeekHigh": 900.0, "bookValue": 0.506})
    assert "Market Cap: 7990000000.0 KWD" in out and "EPS (TTM): 0.06 KWD" in out
    assert "Book Value: 0.506 KWD" in out and "52 Week High: 900.0 KWF" in out


@pytest.mark.unit
def test_bahrain_gets_its_market_currency_when_yahoo_names_none():
    out = _fundamentals("BBK.BH", {"longName": "Bank of Bahrain and Kuwait", "currency": None,
                                   "financialCurrency": "BHD", "bookValue": 0.337})
    assert "Book Value: 0.337 BHD" in out


@pytest.mark.unit
def test_an_unknown_market_is_not_given_a_guessed_currency():
    out = _fundamentals("ZZZ.XX", {"longName": "Somewhere", "currency": None, "bookValue": 1.5})
    assert out.endswith("Book Value: 1.5") and "None" not in out


@pytest.mark.unit
def test_a_kuwaiti_valuation_converts_the_fils_price_to_dinars():
    from tests.test_valuation_service import AS_OF, _benchmark, _closes, _company
    from tradingagents.valuation import service

    vendor_data = _company(source="yfinance", currency="KWD", quote_currency="KWF")
    with mock.patch.object(service, "route_to_vendor", return_value=vendor_data), \
            mock.patch.object(service, "get_final_closes",
                              side_effect=lambda s, e, d: _benchmark() if s == "KWT" else _closes(870.0)), \
            mock.patch.object(service, "get_latest_observation", return_value=(4.0, "2026-09-25")):
        report = service.dcf_report("NBK.KW", AS_OF)
    assert "divided by 1000 to KWD" in report and "Price: 0.87 KWD" in report


# ---------------------------------------------------------------- live feed (run with -m integration)


@pytest.mark.integration
@pytest.mark.parametrize("ticker", ["2222.SR", "EMAAR.AE", "QNBK.QA", "NBK.KW"])
def test_live_gulf_stocks_return_a_year_of_daily_prices(ticker):
    from tradingagents.dataflows.vendors.yahoo.market import get_final_closes

    closes = get_final_closes(ticker, date_window.get_current_date(), 365)
    assert len(closes) > 150


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".SR", ".AE", ".QA", ".KW"])
def test_live_benchmarks_return_a_year_of_daily_prices(suffix):
    from tradingagents.dataflows.vendors.yahoo.market import get_final_closes

    closes = get_final_closes(DEFAULT_CONFIG["benchmark_map"][suffix], date_window.get_current_date(), 365)
    assert len(closes) > 150
