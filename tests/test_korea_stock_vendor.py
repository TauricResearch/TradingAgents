"""Korean market data vendor behavior."""

from __future__ import annotations

import copy
import io
import sys
import types
import zipfile

import pandas as pd
import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows import interface
from tradingagents.dataflows import korea_stock


@pytest.fixture(autouse=True)
def reset_config():
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))


def test_korea_stock_vendor_is_registered_for_core_news_and_fundamentals():
    assert "korea_stock" in interface.VENDOR_LIST
    for method in [
        "get_stock_data",
        "get_news",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    ]:
        assert "korea_stock" in interface.VENDOR_METHODS[method]


def test_korea_stock_routes_stock_data_with_yahoo_suffix(monkeypatch):
    calls = []

    def fake_yfinance(ticker: str, start_date: str, end_date: str) -> str:
        calls.append((ticker, start_date, end_date))
        return "YF DATA"

    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_stock_data"], "korea_stock", fake_yfinance
    )
    set_config({"tool_vendors": {"get_stock_data": "korea_stock"}})

    result = interface.route_to_vendor("get_stock_data", "005930.KS", "2026-05-15", "2026-05-22")

    assert result == "YF DATA"
    assert calls == [("005930.KS", "2026-05-15", "2026-05-22")]


def test_default_benchmark_map_contains_kospi_and_kosdaq():
    assert default_config.DEFAULT_CONFIG["benchmark_map"][".KS"] == "^KS11"
    assert default_config.DEFAULT_CONFIG["benchmark_map"][".KQ"] == "^KQ11"


def test_korean_ticker_auto_prefers_korea_stock_when_default_vendor_is_yfinance(monkeypatch):
    calls = []

    def fake_korea(ticker: str, start_date: str, end_date: str) -> str:
        calls.append(("korea", ticker, start_date, end_date))
        return "KOREA DATA"

    def fake_yfinance(ticker: str, start_date: str, end_date: str) -> str:
        calls.append(("yfinance", ticker, start_date, end_date))
        return "YF DATA"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "korea_stock", fake_korea)
    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "yfinance", fake_yfinance)

    result = interface.route_to_vendor("get_stock_data", "005930.KS", "2026-05-15", "2026-05-22")

    assert result == "KOREA DATA"
    assert calls == [("korea", "005930.KS", "2026-05-15", "2026-05-22")]


def test_non_korean_ticker_keeps_default_yfinance_route(monkeypatch):
    calls = []

    def fake_korea(ticker: str, start_date: str, end_date: str) -> str:
        calls.append(("korea", ticker, start_date, end_date))
        return "KOREA DATA"

    def fake_yfinance(ticker: str, start_date: str, end_date: str) -> str:
        calls.append(("yfinance", ticker, start_date, end_date))
        return "YF DATA"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "korea_stock", fake_korea)
    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "yfinance", fake_yfinance)
    set_config({"tool_vendors": {"get_stock_data": "yfinance"}})

    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-05-15", "2026-05-22")

    assert result == "YF DATA"
    assert calls == [("yfinance", "AAPL", "2026-05-15", "2026-05-22")]


def _install_fake_pykrx(monkeypatch, stock_module):
    """Register a fake ``pykrx.stock`` so ``from pykrx import stock`` succeeds."""
    pykrx_pkg = types.ModuleType("pykrx")
    pykrx_pkg.stock = stock_module
    monkeypatch.setitem(sys.modules, "pykrx", pykrx_pkg)
    monkeypatch.setitem(sys.modules, "pykrx.stock", stock_module)


def _sample_ohlcv_frame():
    index = pd.DatetimeIndex(["2026-05-15", "2026-05-18"], name="날짜")
    return pd.DataFrame(
        {
            "시가": [78000.0, 78500.0],
            "고가": [79000.0, 79100.0],
            "저가": [77500.0, 78200.0],
            "종가": [78800.0, 78900.0],
            "거래량": [12_345_678, 11_111_111],
            "거래대금": [970_000_000_000, 870_000_000_000],
            "등락률": [0.51, 0.13],
        },
        index=index,
    )


def _sample_investor_frame():
    index = pd.DatetimeIndex(["2026-05-15", "2026-05-18"], name="날짜")
    return pd.DataFrame(
        {
            "기관합계": [100_000, -50_000],
            "외국인합계": [-20_000, 30_000],
            "개인": [-80_000, 20_000],
        },
        index=index,
    )


def test_to_pykrx_ticker_strips_yahoo_suffix():
    assert korea_stock.to_pykrx_ticker("005930.KS") == "005930"
    assert korea_stock.to_pykrx_ticker("247540.KQ") == "247540"
    assert korea_stock.to_pykrx_ticker("005930.ks") == "005930"
    # Plain symbols pass through unchanged (uppercased).
    assert korea_stock.to_pykrx_ticker("AAPL") == "AAPL"


def test_pykrx_success_returns_markdown_and_skips_yfinance(monkeypatch):
    ohlcv_calls = []
    investor_value_calls = []
    investor_volume_calls = []

    def fake_get_market_ohlcv(start, end, ticker):
        ohlcv_calls.append((start, end, ticker))
        return _sample_ohlcv_frame()

    def fake_trading_value(start, end, ticker):
        investor_value_calls.append((start, end, ticker))
        return _sample_investor_frame()

    def fake_trading_volume(start, end, ticker):
        investor_volume_calls.append((start, end, ticker))
        return _sample_investor_frame()

    stock_module = types.SimpleNamespace(
        get_market_ohlcv=fake_get_market_ohlcv,
        get_market_trading_value_by_date=fake_trading_value,
        get_market_trading_volume_by_date=fake_trading_volume,
    )
    _install_fake_pykrx(monkeypatch, stock_module)

    def explode_yfinance(*args, **kwargs):
        raise AssertionError("yfinance must not be called when pykrx succeeds")

    monkeypatch.setattr(korea_stock, "get_YFin_data_online", explode_yfinance)

    result = korea_stock.get_stock_data("005930.KS", "2026-05-15", "2026-05-18")

    assert ohlcv_calls == [("20260515", "20260518", "005930")]
    assert investor_value_calls == [("20260515", "20260518", "005930")]
    assert investor_volume_calls == [("20260515", "20260518", "005930")]
    # Markdown report should include OHLCV section and the bilingual Close column header.
    assert "OHLCV (pykrx) for 005930.KS" in result
    assert "종가 (Close)" in result
    assert "Investor trading value (KRW)" in result
    assert "Investor trading volume (shares)" in result
    # Korea context preamble is attached around the pykrx report.
    assert "Korean stock price data" in result


def test_pykrx_missing_falls_back_to_yfinance(monkeypatch):
    # Remove any cached pykrx import and block future imports.
    monkeypatch.delitem(sys.modules, "pykrx", raising=False)
    monkeypatch.delitem(sys.modules, "pykrx.stock", raising=False)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pykrx" or name.startswith("pykrx."):
            raise ImportError("pykrx not installed")
        return real_import(name, globals, locals, fromlist, level)

    if isinstance(__builtins__, dict):
        monkeypatch.setitem(__builtins__, "__import__", fake_import)
    else:
        monkeypatch.setattr(__builtins__, "__import__", fake_import)

    yfinance_calls = []

    def fake_yfinance(ticker, start, end):
        yfinance_calls.append((ticker, start, end))
        return "YF FALLBACK DATA"

    monkeypatch.setattr(korea_stock, "get_YFin_data_online", fake_yfinance)

    result = korea_stock.get_stock_data("005930.KS", "2026-05-15", "2026-05-18")

    assert yfinance_calls == [("005930.KS", "2026-05-15", "2026-05-18")]
    assert "YF FALLBACK DATA" in result
    assert "Korean stock price data" in result


def test_pykrx_ohlcv_exception_falls_back_to_yfinance(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("KRX upstream error")

    stock_module = types.SimpleNamespace(get_market_ohlcv=boom)
    _install_fake_pykrx(monkeypatch, stock_module)

    yfinance_calls = []

    def fake_yfinance(ticker, start, end):
        yfinance_calls.append((ticker, start, end))
        return "YF FALLBACK DATA"

    monkeypatch.setattr(korea_stock, "get_YFin_data_online", fake_yfinance)

    result = korea_stock.get_stock_data("247540.KQ", "2026-05-15", "2026-05-18")

    assert yfinance_calls == [("247540.KQ", "2026-05-15", "2026-05-18")]
    assert "YF FALLBACK DATA" in result


def test_pykrx_empty_ohlcv_falls_back_to_yfinance(monkeypatch):
    def empty_ohlcv(*args, **kwargs):
        return pd.DataFrame()

    stock_module = types.SimpleNamespace(get_market_ohlcv=empty_ohlcv)
    _install_fake_pykrx(monkeypatch, stock_module)

    yfinance_calls = []

    def fake_yfinance(ticker, start, end):
        yfinance_calls.append((ticker, start, end))
        return "YF FALLBACK DATA"

    monkeypatch.setattr(korea_stock, "get_YFin_data_online", fake_yfinance)

    result = korea_stock.get_stock_data("005930.KS", "2026-05-15", "2026-05-18")

    assert yfinance_calls == [("005930.KS", "2026-05-15", "2026-05-18")]
    assert "YF FALLBACK DATA" in result


def test_pykrx_supply_demand_failure_does_not_block_price_data(monkeypatch):
    def fake_ohlcv(start, end, ticker):
        return _sample_ohlcv_frame()

    def trading_value_boom(*args, **kwargs):
        raise RuntimeError("supply/demand endpoint down")

    def empty_trading_volume(*args, **kwargs):
        return pd.DataFrame()

    stock_module = types.SimpleNamespace(
        get_market_ohlcv=fake_ohlcv,
        get_market_trading_value_by_date=trading_value_boom,
        get_market_trading_volume_by_date=empty_trading_volume,
    )
    _install_fake_pykrx(monkeypatch, stock_module)

    def explode_yfinance(*args, **kwargs):
        raise AssertionError("yfinance must not be called when pykrx OHLCV succeeds")

    monkeypatch.setattr(korea_stock, "get_YFin_data_online", explode_yfinance)

    result = korea_stock.get_stock_data("005930.KS", "2026-05-15", "2026-05-18")

    # Price section is still produced.
    assert "OHLCV (pykrx) for 005930.KS" in result
    # Supply/demand failure leaves a note, not an exception.
    assert "Supply/demand notes" in result
    assert "trading_value fetch failed" in result
    assert "trading_volume: no rows returned" in result
    # And no investor tables made it through.
    assert "Investor trading value (KRW)" not in result
    assert "Investor trading volume (shares)" not in result


# ---------------------------------------------------------------------------
# DART (OpenDART) augmentation tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_dart_corp_cache():
    """Each test starts with a fresh corp-code cache so monkeypatched env vars apply."""
    korea_stock._load_corp_code_map.cache_clear()
    yield
    korea_stock._load_corp_code_map.cache_clear()


def _build_corp_code_zip(records):
    """Build the OpenDART corpCode.xml ZIP payload from ``records``."""
    root = "<result>" + "".join(
        "<list>"
        f"<corp_code>{r['corp_code']}</corp_code>"
        f"<corp_name>{r['corp_name']}</corp_name>"
        f"<stock_code>{r.get('stock_code', '')}</stock_code>"
        f"<modify_date>{r.get('modify_date', '')}</modify_date>"
        "</list>"
        for r in records
    ) + "</result>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("CORPCODE.xml", root)
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, *, content=b"", json_data=None, status_code=200):
        self.content = content
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _stub_yfinance_baseline(monkeypatch):
    """Stub every yfinance call surface so DART tests do not hit the network."""
    monkeypatch.setattr(korea_stock, "get_yfinance_fundamentals", lambda t, d: "YF FUNDAMENTALS")
    monkeypatch.setattr(korea_stock, "get_yfinance_balance_sheet", lambda t, d: "YF BALANCE")
    monkeypatch.setattr(korea_stock, "get_yfinance_cashflow", lambda t, d: "YF CASHFLOW")
    monkeypatch.setattr(korea_stock, "get_yfinance_income_statement", lambda t, d: "YF INCOME")


def test_get_fundamentals_without_dart_api_key_keeps_yfinance_baseline(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    _stub_yfinance_baseline(monkeypatch)

    def explode_requests(*args, **kwargs):
        raise AssertionError("requests.get must not run without an API key")

    monkeypatch.setattr(korea_stock.requests, "get", explode_requests)

    result = korea_stock.get_fundamentals("005930.KS", "2026-05-22")

    assert "Korean fundamentals baseline" in result
    assert "YF FUNDAMENTALS" in result
    assert "DART API key not configured" in result


def test_get_fundamentals_with_dart_api_key_renders_filings_and_financials(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    _stub_yfinance_baseline(monkeypatch)

    corp_zip = _build_corp_code_zip(
        [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "stock_code": "005930",
                "modify_date": "20260101",
            },
            # Unlisted issuer must be filtered out.
            {
                "corp_code": "99999999",
                "corp_name": "비상장회사",
                "stock_code": "",
            },
        ]
    )

    list_payload = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "rcept_no": "20260515000123",
                "report_nm": "분기보고서 (2026.03)",
                "rcept_dt": "20260515",
                "flr_nm": "삼성전자",
            },
            {
                "rcept_no": "20260420000456",
                "report_nm": "주요사항보고서",
                "rcept_dt": "20260420",
                "flr_nm": "삼성전자",
            },
        ],
    }
    fnltt_payload = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "account_id": "ifrs-full_Revenue",
                "sj_div": "IS",
                "thstrm_amount": "300,000,000,000,000",
                "frmtrm_amount": "279,000,000,000,000",
            },
            {
                "account_id": "ifrs-full_ProfitLoss",
                "sj_div": "IS",
                "thstrm_amount": "26,000,000,000,000",
                "frmtrm_amount": "15,000,000,000,000",
            },
            {
                "account_id": "ifrs-full_Assets",
                "sj_div": "BS",
                "thstrm_amount": "450,000,000,000,000",
                "frmtrm_amount": "430,000,000,000,000",
            },
            # Unknown account_id should be ignored.
            {
                "account_id": "ifrs-full_Unrecognized",
                "thstrm_amount": "1",
                "frmtrm_amount": "1",
            },
        ],
    }

    captured = []

    def fake_get(url, params=None, timeout=None):
        captured.append((url, dict(params or {})))
        if url == korea_stock.DART_CORPCODE_URL:
            return _FakeResponse(content=corp_zip)
        if url == korea_stock.DART_LIST_URL:
            return _FakeResponse(json_data=list_payload)
        if url == korea_stock.DART_FNLTT_URL:
            return _FakeResponse(json_data=fnltt_payload)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(korea_stock.requests, "get", fake_get)

    result = korea_stock.get_fundamentals("005930.KS", "2026-05-22")

    # yfinance baseline is preserved.
    assert "YF FUNDAMENTALS" in result
    # corp_code mapping appears.
    assert "corp_code `00126380`" in result
    assert "삼성전자" in result
    # Recent filings table includes the DART viewer link.
    assert "### DART recent filings" in result
    assert "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260515000123" in result
    assert "분기보고서 (2026.03)" in result
    # Financial summary table includes mapped account labels.
    assert "### DART financial summary" in result
    assert "FY2025" in result  # curr_date.year - 1
    assert "Revenue" in result
    assert "300,000,000,000,000" in result
    assert "Total assets" in result
    # Unknown account_id is filtered out of the summary.
    assert "ifrs-full_Unrecognized" not in result

    # list.json was called with the expected window (~365 days) and page_count=10.
    list_calls = [params for url, params in captured if url == korea_stock.DART_LIST_URL]
    assert list_calls, "list.json was not called"
    assert list_calls[0]["corp_code"] == "00126380"
    assert list_calls[0]["page_count"] == 10
    assert list_calls[0]["end_de"] == "20260522"
    assert list_calls[0]["bgn_de"] == "20250522"

    # fnlttSinglAcntAll.json was called for FY2025 with the annual report code.
    fnltt_calls = [params for url, params in captured if url == korea_stock.DART_FNLTT_URL]
    assert fnltt_calls[0]["bsns_year"] == "2025"
    assert fnltt_calls[0]["reprt_code"] == "11011"


def test_dart_failures_do_not_break_get_fundamentals(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    _stub_yfinance_baseline(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("DART upstream is down")

    monkeypatch.setattr(korea_stock.requests, "get", boom)

    result = korea_stock.get_fundamentals("005930.KS", "2026-05-22")

    # The yfinance baseline is still rendered.
    assert "YF FUNDAMENTALS" in result
    # And the DART section degrades to a note (no exception).
    assert "No corp_code mapping" in result


def test_get_balance_sheet_appends_dart_financial_summary_only(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    _stub_yfinance_baseline(monkeypatch)

    corp_zip = _build_corp_code_zip(
        [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "stock_code": "005930",
            }
        ]
    )
    fnltt_payload = {
        "status": "000",
        "list": [
            {
                "account_id": "ifrs-full_Assets",
                "thstrm_amount": "450,000,000,000,000",
                "frmtrm_amount": "430,000,000,000,000",
            }
        ],
    }

    seen_urls = []

    def fake_get(url, params=None, timeout=None):
        seen_urls.append(url)
        if url == korea_stock.DART_CORPCODE_URL:
            return _FakeResponse(content=corp_zip)
        if url == korea_stock.DART_FNLTT_URL:
            return _FakeResponse(json_data=fnltt_payload)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(korea_stock.requests, "get", fake_get)

    result = korea_stock.get_balance_sheet("005930.KS", "2026-05-22")

    assert "YF BALANCE" in result
    assert "### DART financial summary" in result
    assert "Total assets" in result
    # Balance sheet view skips the filings section to keep output focused.
    assert "### DART recent filings" not in result
    assert korea_stock.DART_LIST_URL not in seen_urls


def test_resolve_corp_code_strips_yahoo_suffix(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)

    corp_zip = _build_corp_code_zip(
        [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "stock_code": "005930",
            },
            {
                "corp_code": "00164779",
                "corp_name": "에코프로비엠",
                "stock_code": "247540",
            },
        ]
    )

    def fake_get(url, params=None, timeout=None):
        assert url == korea_stock.DART_CORPCODE_URL
        assert params == {"crtfc_key": "test-key"}
        return _FakeResponse(content=corp_zip)

    monkeypatch.setattr(korea_stock.requests, "get", fake_get)

    kospi = korea_stock._resolve_corp_code("005930.KS")
    kosdaq = korea_stock._resolve_corp_code("247540.KQ")
    missing = korea_stock._resolve_corp_code("000000.KS")

    assert kospi == {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "stock_code": "005930",
        "modify_date": "",
    }
    assert kosdaq["corp_code"] == "00164779"
    assert missing is None


# ---------------------------------------------------------------------------
# Korean-language news augmentation tests
# ---------------------------------------------------------------------------


def _stub_news_baseline(monkeypatch):
    monkeypatch.setattr(korea_stock, "get_news_yfinance", lambda t, s, e: "YF NEWS BASELINE")


def test_get_news_without_naver_credentials_keeps_yfinance_baseline(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("NAVER_NEWS_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_NEWS_CLIENT_SECRET", raising=False)
    _stub_news_baseline(monkeypatch)

    def explode_requests(*args, **kwargs):
        raise AssertionError("requests.get must not run without Naver credentials")

    monkeypatch.setattr(korea_stock.requests, "get", explode_requests)

    result = korea_stock.get_news("005930.KS", "2026-05-15", "2026-05-22")

    assert "YF NEWS BASELINE" in result
    assert "Korean-language news (Naver)" in result
    assert "Naver Search API credentials not configured" in result


def test_get_news_with_naver_credentials_sanitizes_html_and_links(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver-secret")
    monkeypatch.delenv("NAVER_NEWS_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_NEWS_CLIENT_SECRET", raising=False)
    # Corp-name lookup should use DART only when DART key exists; keep this path code-only.
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    _stub_news_baseline(monkeypatch)

    captured = []

    def fake_get(url, params=None, headers=None, timeout=None):
        captured.append((url, dict(params or {}), dict(headers or {})))
        assert url == korea_stock.NAVER_NEWS_URL
        return _FakeResponse(
            json_data={
                "items": [
                    {
                        "title": "<b>삼성전자</b> AI 반도체 &amp; 실적",
                        "description": "<b>외국인</b> 순매수 확대 &quot;기대&quot;",
                        "originallink": "https://news.example.com/original",
                        "link": "https://news.naver.com/wrapped",
                        "pubDate": "Fri, 22 May 2026 10:00:00 +0900",
                    }
                ]
            }
        )

    monkeypatch.setattr(korea_stock.requests, "get", fake_get)

    result = korea_stock.get_news("005930.KS", "2026-05-15", "2026-05-22")

    assert "YF NEWS BASELINE" in result
    assert "Query: `005930 주식`" in result
    assert "Requested analysis window: 2026-05-15 → 2026-05-22" in result
    assert "does not provide strict date-range filtering" in result
    assert "[삼성전자 AI 반도체 & 실적](https://news.example.com/original)" in result
    assert "외국인 순매수 확대 \"기대\"" in result
    assert "<b>" not in result
    assert captured[0][1] == {"query": "005930 주식", "display": 10, "sort": "date"}
    assert captured[0][2]["X-Naver-Client-Id"] == "naver-id"
    assert captured[0][2]["X-Naver-Client-Secret"] == "naver-secret"


def test_get_news_uses_dart_corp_name_when_available(monkeypatch):
    monkeypatch.setenv("NAVER_NEWS_CLIENT_ID", "news-id")
    monkeypatch.setenv("NAVER_NEWS_CLIENT_SECRET", "news-secret")
    monkeypatch.setenv("DART_API_KEY", "dart-key")
    _stub_news_baseline(monkeypatch)
    korea_stock._load_corp_code_map.cache_clear()

    corp_zip = _build_corp_code_zip(
        [{"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"}]
    )
    captured = []

    def fake_get(url, params=None, headers=None, timeout=None):
        captured.append((url, dict(params or {})))
        if url == korea_stock.DART_CORPCODE_URL:
            return _FakeResponse(content=corp_zip)
        if url == korea_stock.NAVER_NEWS_URL:
            return _FakeResponse(json_data={"items": []})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(korea_stock.requests, "get", fake_get)

    result = korea_stock.get_news("005930.KS", "2026-05-15", "2026-05-22")

    assert "Query: `삼성전자 005930 주식`" in result
    naver_calls = [params for url, params in captured if url == korea_stock.NAVER_NEWS_URL]
    assert naver_calls[0]["query"] == "삼성전자 005930 주식"


def test_get_news_naver_request_failure_keeps_yfinance_baseline(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "naver-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver-secret")
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)
    _stub_news_baseline(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("Naver upstream down")

    monkeypatch.setattr(korea_stock.requests, "get", boom)

    result = korea_stock.get_news("005930.KS", "2026-05-15", "2026-05-22")

    assert "YF NEWS BASELINE" in result
    assert "Naver news API call failed: RuntimeError: Naver upstream down" in result
