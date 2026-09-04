"""Explicitly selected, anonymous Parallel Search MCP ticker news."""

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from urllib.parse import urlsplit

from .config import get_config
from .date_window import in_window
from .errors import VendorNotConfiguredError

logger = logging.getLogger(__name__)
ENDPOINT = "https://search.parallel.ai/mcp"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REPORT_CHARS = 25_000


def _http_client(**kwargs):
    # Imports stay local so the default install does not require the MCP extra.
    import httpx

    class BoundedStream(httpx.AsyncByteStream):
        def __init__(self, stream):
            self.stream = stream

        async def __aiter__(self):
            size = 0
            async for chunk in self.stream:
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("Parallel response exceeded the 2 MiB limit")
                yield chunk

        async def aclose(self):
            await self.stream.aclose()

    async def bound_response(response):
        if response.headers.get("content-encoding", "identity") != "identity":
            raise ValueError("Parallel returned an unexpected compressed response")
        response.stream = BoundedStream(response.stream)

    headers = {"Accept-Encoding": "identity", **(kwargs.pop("headers", None) or {})}
    return httpx.AsyncClient(
        **kwargs,
        follow_redirects=False,
        headers=headers,
        event_hooks={"response": [bound_response]},
    )


async def _search(arguments):
    try:
        import anyio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        raise VendorNotConfiguredError(
            'Parallel news requires the optional dependency: pip install "tradingagents[parallel]"'
        ) from exc

    # Bound the whole exchange, including discovery and resource cleanup.
    with anyio.fail_after(60):
        async with streamablehttp_client(
            ENDPOINT, timeout=15, sse_read_timeout=45, httpx_client_factory=_http_client
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                cursor = None
                while True:
                    listed = await session.list_tools(cursor=cursor)
                    if any(tool.name == "web_search" for tool in listed.tools):
                        break
                    cursor = listed.nextCursor
                    if not cursor:
                        raise RuntimeError("Parallel MCP did not advertise web_search")
                return await session.call_tool("web_search", arguments)


def _payload(result):
    if result.isError:
        raise RuntimeError("Parallel MCP web_search returned a tool error")
    payload = result.structuredContent
    if payload is None:
        text = [block.text for block in result.content if block.type == "text"]
        if len(text) != 1:
            raise ValueError("Parallel MCP returned an invalid search response")
        payload = json.loads(text[0])
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Parallel MCP returned an invalid results list")
    return payload


def get_news_parallel(ticker: str, start_date: str, end_date: str) -> str:
    """Search ticker news, then apply the same UTC date window as other news vendors.

    Publication metadata is not a historical snapshot of a page's contents.
    Results may be incomplete, especially for historical windows.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    if not isinstance(ticker, str) or not ticker.strip() or len(ticker) > 100:
        raise ValueError("ticker must contain 1 to 100 characters")
    limit = get_config()["news_article_limit"]
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("news_article_limit must be a positive integer")

    arguments = {
        "objective": (
            f"Find financial news about ticker {ticker} published from {start_date} "
            f"through {end_date}. Return dated articles with source URLs and excerpts."
        ),
        "search_queries": [f"{ticker} company news {start_date} {end_date}"],
    }
    # Retain the attempted provider in logs even when the router falls back.
    logger.info("Requesting ticker news from Parallel Search MCP")
    payload = _payload(asyncio.run(_search(arguments)))
    report = f"## {ticker} News via Parallel, from {start_date} to {end_date}:\n\n"
    if payload.get("warnings"):
        logger.warning("Parallel Search warnings: %s", payload["warnings"])
        report += "Search returned warnings; results may be incomplete.\n\n"
    count = 0
    seen = set()
    for article in payload["results"]:
        if not isinstance(article, dict):
            raise ValueError("Parallel MCP returned an invalid article")
        url = article.get("url")
        excerpts = article.get("excerpts")
        title = article.get("title") or "Untitled"
        if (
            not isinstance(url, str)
            or urlsplit(url).scheme not in {"http", "https"}
            or not urlsplit(url).netloc
            or not isinstance(title, str)
            or not isinstance(excerpts, list)
            or not all(isinstance(text, str) for text in excerpts)
        ):
            raise ValueError("Parallel MCP returned invalid article fields")
        published = article.get("publish_date")
        pub_dt = None
        if published:
            # Undated content follows the shared live/historical policy.
            with contextlib.suppress(AttributeError, TypeError, ValueError):
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if not in_window(pub_dt, start, end) or url in seen:
            continue
        block = f"### {title}\nPublished: {published or 'unknown'}\nLink: {url}\n"
        remaining = MAX_REPORT_CHARS - len(report) - len(block) - 100
        if remaining < 0:
            return report + "[Further results omitted: output limit.]\n"
        excerpt = "\n".join(excerpts)
        block += excerpt[:remaining]
        if len(excerpt) > remaining:
            block += "\n[Excerpt truncated.]"
        report += block + "\n\n"
        seen.add(url)
        count += 1
        if count >= limit:
            break
    if count == 0:
        report += "No news found within the requested window.\n"
    return report
