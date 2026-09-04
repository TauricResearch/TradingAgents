"""Optional news vendor contract; no network or MCP dependency needed here."""

import asyncio
import builtins
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tradingagents.dataflows import parallel_news as news
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import VendorNotConfiguredError


def article(title="Inside", published="2025-05-09", **fields):
    return {
        "title": title,
        "url": f"https://example.com/{title}",
        "publish_date": published,
        "excerpts": ["A financial news excerpt"],
        **fields,
    }


def response(results, **fields):
    return SimpleNamespace(
        isError=False, structuredContent={"results": results, **fields}, content=[]
    )


@pytest.fixture
def search(monkeypatch):
    call = Mock(return_value=response([article()]))

    async def run(arguments):
        return call(arguments)

    monkeypatch.setattr(news, "_search", run)
    return call


def test_historical_filter_and_limit_apply_after_filtering(search):
    set_config({"news_article_limit": 2})
    search.return_value = response([
        article("Future", "2025-05-10T00:00:00Z"),
        article("Old", "2025-04-30"),
        article("Unknown", None),
        article("BadDate", "not-a-date"),
        article("Inside"),
        article("Inside"),
        article("Offset", "2025-05-10T01:00:00+05:00"),
        article("OverLimit"),
    ])
    result = news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")
    assert "Inside" in result and "Offset" in result
    assert "https://example.com/Inside" in result
    assert result.count("### Inside") == 1
    for excluded in ("Future", "Old", "Unknown", "BadDate", "OverLimit"):
        assert excluded not in result
    arguments = search.call_args.args[0]
    assert arguments["search_queries"] == ["AAPL company news 2025-05-01 2025-05-09"]
    assert "2025-05-09" in arguments["objective"]


def test_live_window_keeps_undated_news(search):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    search.return_value = response([article("Undated", None)])
    assert "### Undated" in news.get_news_parallel("AAPL", today, today)


@pytest.mark.parametrize("articles", [[], [article("Future", "2025-05-10")]])
def test_empty_success_is_explicit(search, articles):
    search.return_value = response(articles)
    assert "No news found within" in news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")


def test_tool_error_is_not_empty_success(search):
    search.return_value.isError = True
    with pytest.raises(RuntimeError, match="tool error"):
        news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")


@pytest.mark.parametrize("payload", [{}, {"results": None}, {"results": [None]}, {"results": [{"url": "bad"}]}])
def test_malformed_payload_is_not_empty_success(search, payload):
    search.return_value.structuredContent = payload
    with pytest.raises(ValueError):
        news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")


def test_text_representation_and_warning(search, caplog):
    search.return_value.structuredContent = None
    search.return_value.content = [SimpleNamespace(type="text", text=json.dumps({
        "results": [article()], "warnings": [{"type": "warning", "message": "Partial"}]
    }))]
    result = news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")
    assert "### Inside" in result and "warnings" in result
    assert "Partial" in caplog.text


def test_output_bound_preserves_citation(search):
    search.return_value = response([article(excerpts=["x" * 100_000])])
    result = news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")
    assert len(result) <= news.MAX_REPORT_CHARS
    assert "https://example.com/Inside" in result
    assert "[Excerpt truncated.]" in result


def test_reversed_dates_rejected_before_request(search):
    with pytest.raises(ValueError, match="start_date"):
        news.get_news_parallel("AAPL", "2025-05-09", "2025-05-01")
    search.assert_not_called()


def test_missing_optional_dependency(monkeypatch):
    original = builtins.__import__

    def without_mcp(name, *args, **kwargs):
        if name == "mcp":
            raise ImportError("optional MCP is absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_mcp)
    with pytest.raises(VendorNotConfiguredError, match=r"tradingagents\[parallel\]"):
        news.get_news_parallel("AAPL", "2025-05-01", "2025-05-09")


@pytest.mark.parametrize("vendor", ["default", "yfinance", "yfinance,alpha_vantage"])
def test_existing_routes_never_invoke_parallel(monkeypatch, vendor):
    from tradingagents.dataflows import interface

    methods = copy.deepcopy(interface.VENDOR_METHODS)
    av = Mock(side_effect=RuntimeError("AV failed"))
    yf = Mock(side_effect=RuntimeError("Yahoo failed"))
    parallel = Mock(return_value="unexpected")
    methods["get_news"].update(alpha_vantage=av, yfinance=yf, parallel=parallel)
    monkeypatch.setattr(interface, "VENDOR_METHODS", methods)
    set_config({"tool_vendors": {"get_news": vendor}})
    with pytest.raises(RuntimeError):
        interface.route_to_vendor("get_news", "AAPL", "2025-05-01", "2025-05-09")
    parallel.assert_not_called()
    assert yf.called
    assert av.called == (vendor != "yfinance")


def test_explicit_parallel_failure_falls_back_in_order(monkeypatch, caplog):
    from tradingagents.dataflows import interface

    calls = []

    def parallel(*args):
        calls.append("parallel")
        raise RuntimeError("Search failed")

    def yahoo(*args):
        calls.append("yfinance")
        return "Yahoo news"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_news", {"parallel": parallel, "yfinance": yahoo})
    set_config({"tool_vendors": {"get_news": "parallel,yfinance"}})
    assert interface.route_to_vendor("get_news", "AAPL", "2025-05-01", "2025-05-09") == "Yahoo news"
    assert calls == ["parallel", "yfinance"]
    assert "parallel" in caplog.text and "Search failed" in caplog.text


def test_http_response_limit_stops_before_remaining_chunks(monkeypatch):
    httpx = pytest.importorskip("httpx")
    consumed = []
    closed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for i in range(10):
                consumed.append(i)
                yield b"abcd"

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(news, "MAX_RESPONSE_BYTES", 8)

    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=Body()))
        async with news._http_client(transport=transport, headers=None) as client:
            with pytest.raises(ValueError, match="response exceeded"):
                await client.get(news.ENDPOINT)

    asyncio.run(run())
    assert consumed == [0, 1, 2]
    assert closed


def test_http_redirect_does_not_forward_request():
    httpx = pytest.importorskip("httpx")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://other.example/search"})

    async def run():
        async with news._http_client(transport=httpx.MockTransport(respond), headers=None) as client:
            result = await client.post(news.ENDPOINT, json={"query": "ticker news"})
            assert result.status_code == 307

    asyncio.run(run())
    assert len(requests) == 1
    assert "authorization" not in requests[0].headers
    assert "x-api-key" not in requests[0].headers
    assert requests[0].headers["accept-encoding"] == "identity"


def test_compressed_response_rejected_before_decoding():
    httpx = pytest.importorskip("httpx")

    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"compressed")
        ))
        async with news._http_client(transport=transport) as client:
            with pytest.raises(ValueError, match="compressed response"):
                await client.get(news.ENDPOINT)

    asyncio.run(run())
