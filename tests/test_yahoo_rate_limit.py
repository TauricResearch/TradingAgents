"""A Yahoo rate limit is retried, then reported as a rate limit.

When the limit outlasts the retries, the agent must hear that the vendor is
throttled. "The symbol may be invalid or delisted" is a claim about the company
that nobody checked, and an exception out of a tool ends the run.
"""

import pandas as pd
import pytest
import yfinance as yf
from yfinance.data import YfData
from yfinance.exceptions import YFRateLimitError

from tradingagents.agents.tools import (
    get_global_news,
    get_indicators,
    get_insider_transactions,
    get_news,
    get_stock_data,
    get_verified_market_snapshot,
)
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo import fundamentals, ohlcv

DAY = "2026-09-18"


def _rate_limited(*args, **kwargs):
    raise YFRateLimitError()


@pytest.fixture
def yahoo(monkeypatch, tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.time, "sleep", lambda seconds: None)
    for module in (ohlcv, fundamentals):
        monkeypatch.setattr(module, "vendor_reachable", lambda url: True)
    return monkeypatch


@pytest.mark.unit
@pytest.mark.parametrize("tool, args", [
    pytest.param(get_stock_data, ("AAPL", "2026-09-10", DAY), id="stock_data"),
    pytest.param(get_indicators, ("AAPL", "rsi", DAY, 5), id="indicators"),
    pytest.param(get_verified_market_snapshot, ("AAPL", DAY), id="snapshot"),
    pytest.param(get_news, ("AAPL", "2026-09-10", DAY), id="news"),
    pytest.param(get_global_news, (DAY, 7, 5), id="global_news"),
    pytest.param(get_insider_transactions, ("AAPL",), id="insider"),
])
def test_a_rate_limit_that_outlasts_the_retries_is_reported_as_one(yahoo, tool, args):
    for name in ("history", "get_news"):
        yahoo.setattr(yf.Ticker, name, _rate_limited)
    yahoo.setattr(yf.Ticker, "insider_transactions", property(_rate_limited))
    yahoo.setattr(yf, "Search", _rate_limited)

    out = tool.func(*args, trade_date=DAY)

    assert out.startswith("DATA_UNAVAILABLE"), out
    assert "delisted" not in out


@pytest.mark.unit
def test_the_indicator_path_retries_a_rate_limit(yahoo):
    """The prices behind every indicator were fetched with ``yf.download``, which
    returns an empty frame for a 429, so they were never retried."""
    bar = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
                        "Volume": [100]}, index=pd.DatetimeIndex([DAY], name="Date"))
    answers = [YFRateLimitError(), bar]

    def history(self, **kwargs):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    yahoo.setattr(yf.Ticker, "history", history)

    assert ohlcv.load_ohlcv("AAPL", DAY)["Close"].tolist() == [1.0]


@pytest.mark.unit
def test_yfinance_raises_the_rate_limit_from_history(yahoo):
    yahoo.setattr(YfData, "_make_request", _rate_limited)

    with pytest.raises(VendorUnavailableError, match="rate limited"):
        ohlcv.load_ohlcv("AAPL", DAY)


@pytest.mark.unit
def test_fundamentals_ask_a_new_ticker_after_a_rate_limit(yahoo):
    """A Ticker keeps a failed ``info`` fetch as done, so asking the same one
    again reads an empty profile, which looks like a symbol with no data."""

    class Ticker:
        def __init__(self, symbol):
            self.fetched = False

        @property
        def info(self):
            if self.fetched:
                return {}
            self.fetched = True
            raise YFRateLimitError()

    yahoo.setattr(yf, "Ticker", Ticker)

    out = router.route_to_vendor("get_fundamentals", "AAPL", None)

    assert out.startswith("DATA_UNAVAILABLE"), out


@pytest.mark.unit
def test_a_price_request_that_raises_is_unavailable_whether_or_not_yahoo_answers(yahoo):
    """An unknown symbol comes back from ``Ticker.history`` as an empty frame, so
    a request that raised failed in transit, and says nothing about the symbol."""

    def refused(self, **kwargs):
        raise ConnectionError("curl: (7) Failed to connect to query2.finance.yahoo.com")

    yahoo.setattr(yf.Ticker, "history", refused)
    for reachable in (False, True):
        yahoo.setattr(ohlcv, "vendor_reachable", lambda url, _r=reachable: _r)
        with pytest.raises(VendorUnavailableError, match="request failed"):
            ohlcv.load_ohlcv("AAPL", DAY)


@pytest.mark.unit
def test_a_price_request_that_fails_is_unavailable_even_when_yahoo_answers(monkeypatch, tmp_path):
    """A timeout says nothing about the symbol; a reachable host does not make it one."""
    def timed_out(**kwargs):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda s: type("T", (), {"history": lambda self, **k: timed_out(**k)})())
    monkeypatch.setattr(ohlcv, "vendor_reachable", lambda url: True)

    with pytest.raises(VendorUnavailableError):
        ohlcv.load_ohlcv("NVDA", "2026-09-23")


class _Unreachable:
    """A Ticker whose every request fails in transit."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        raise TimeoutError("read timed out")


def _yahoo_calls():
    from tradingagents.dataflows.date_window import get_current_date
    from tradingagents.dataflows.vendors.yahoo import market, news

    today = get_current_date()
    return [
        pytest.param(lambda: fundamentals.get_fundamentals("AAPL", today), id="fundamentals"),
        pytest.param(lambda: fundamentals.get_balance_sheet("AAPL", "quarterly", today), id="statement"),
        pytest.param(lambda: fundamentals.get_insider_transactions("AAPL", today), id="insider"),
        pytest.param(lambda: fundamentals.get_company_profile("AAPL"), id="profile"),
        pytest.param(lambda: news.get_news_yfinance("AAPL", "2026-09-10", DAY), id="news"),
        pytest.param(lambda: news.get_global_news_yfinance(DAY, 7, 5), id="global_news"),
        pytest.param(lambda: market.get_YFin_data_online("AAPL", "2026-09-10", DAY), id="stock_data"),
        pytest.param(lambda: market.get_closes("AAPL", "2026-09-10", DAY), id="closes"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize("call", _yahoo_calls())
def test_a_yahoo_request_that_fails_is_unavailable_not_absent(yahoo, call):
    """An unknown symbol comes back empty, so a request that raised failed in transit."""
    yahoo.setattr(yf, "Ticker", _Unreachable)
    yahoo.setattr(yf, "Search", _Unreachable)

    with pytest.raises(VendorUnavailableError):
        call()
