"""Google News RSS fetcher scoped to Malaysia — a keyless news vendor aimed
at Bursa Malaysia (KLSE) tickers and MYR-relevant macro news.

Neither of Bursa's two dominant retail sources exposes anything this codebase
can call directly: The Edge Malaysia (theedgemalaysia.com, the domain
theedgemarkets.com now redirects to) is a Next.js app with no RSS feed, no
public REST API, and no discoverable per-company endpoint; klse.i3investor.com
serves its forum/news pages behind Cloudflare bot-protection that returns an
empty body to non-browser clients. Google News' Malaysia-localized RSS search
(``news.google.com/rss/search?...&gl=MY``) aggregates The Edge, The Star, NST,
Bernama, BusinessToday and others under one keyless, un-blocked endpoint, so
this module queries that instead of scraping either site directly.

Google's feed is published "for the purpose of rendering Google News results
within a personal feed reader for personal, non-commercial use" per its own
copyright notice (see the feed's ``<copyright>`` element) — worth being aware
of if this vendor's output leaves personal/research use.

Google News' ``after:``/``before:`` query operators genuinely bound results
to a historical date range server-side (verified against real dates), which
is what makes this usable for point-in-time-safe historical runs rather than
just "recent news" like a plain keyword search would give.

Ticker-specific search needs a company name, not a bare KLSE code — Malaysian
coverage never writes "1155.KL" in prose. The name is resolved via yfinance's
``Ticker.info`` (best-effort, process-local cache, falls back to the bare
ticker on failure).

Degrades gracefully like the other optional dataflow sources: never raises,
returns a placeholder string when a fetch fails so callers don't special-case
missing data, and distinguishes "fetch failed" from "searched and found
nothing" (the two are different claims — see reddit.py's #1295 note for why
that distinction matters to the agents reading this output).
"""

from __future__ import annotations

import http.client
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .date_window import in_window
from .stockstats_utils import yf_retry
from .symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)

_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-MY&gl=MY&ceid=MY:en"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# MY-focused macro/market search terms, parallel in spirit to the default
# ``global_news_queries`` config but scoped to what actually moves
# KLSE-listed names and a dividend holder's returns: the index and foreign
# fund flows, BNM rate policy, the ringgit, bond yields (the yield a dividend
# stock competes with), palm oil and crude oil (planters, Petronas and the
# fiscal position), the budget, the economy, and the US Fed as the external
# backdrop that drives foreign flows into Bursa. Each wording was checked
# against the live feed: short queries return far more relevant articles
# than long ones (e.g. "Bank Negara Malaysia OPR interest rate" matched 3
# articles in a week, "OPR Bank Negara" 7). Override with the
# ``my_news_queries`` config key.
DEFAULT_MY_QUERIES = (
    "Bursa Malaysia KLCI",
    "foreign funds Bursa",
    "OPR Bank Negara",
    "ringgit",
    "Malaysia bond yields",
    "palm oil prices",
    "oil prices Petronas",
    "Malaysia budget",
    "Malaysia economy",
    "Federal Reserve interest rates",
)

# Publishers (as Google News names them in each item's <source>) whose
# reporting is first-hand and edited: Malaysia's business and general press,
# the national news agency, regional and international wires, and official
# bodies. Matching is case-insensitive on the whole name. Google's MY feed
# also carries machine-written stock blurbs (e.g. AD HOC NEWS), broker and
# crypto pages (Moomoo, TradingView, CoinGecko), and aggregators that only
# re-post other outlets (Newswav, KLSE Screener); about a third of a typical
# week's results came from such sources, so they are filtered out by
# default. Override with ``trusted_news_sources``, or set
# ``trusted_news_only`` to False to keep every publisher.
TRUSTED_MY_NEWS_SOURCES = (
    # Malaysian business press
    "The Edge Malaysia", "The Edge Markets", "The Star", "NST Online",
    "New Straits Times", "Business Times", "The Malaysian Reserve",
    "BusinessToday Malaysia", "Focus Malaysia", "BFM 89.9",
    # National news agency
    "Bernama", "BernamaBiz",
    # Malaysian general press
    "Malay Mail", "Free Malaysia Today", "Malaysiakini", "The Sun",
    "The Vibes", "Astro Awani", "Sinar Daily", "Borneo Post",
    # Regional and international
    "Reuters", "Bloomberg", "Nikkei Asia", "CNA", "The Business Times",
    "The Straits Times", "South China Morning Post", "Financial Times",
    # Official sources
    "Bank Negara Malaysia", "Bursa Malaysia", "Securities Commission Malaysia",
    "Department of Statistics Malaysia", "Ministry of Finance Malaysia",
    "Malaysian Palm Oil Board",
)

# Feeds are small (a page of search results); cap the read so a compromised
# or misbehaving endpoint can't stream an unbounded body into memory before
# it's parsed — same guard reddit.py applies to its feed reads.
_MAX_FEED_BYTES = 5 * 1024 * 1024

# Process-local cache: several tools in one analysis run (get_news,
# sentiment) may resolve the same ticker's name repeatedly in a single
# process: no need to hit yfinance more than once per ticker per run.
_name_cache: dict[str, str] = {}


def _read_capped(resp) -> bytes:
    data = resp.read(_MAX_FEED_BYTES + 1)
    if len(data) > _MAX_FEED_BYTES:
        raise http.client.HTTPException(
            f"Google News feed exceeded {_MAX_FEED_BYTES} bytes; refusing to parse"
        )
    return data


def _resolve_query_name(ticker: str) -> str:
    """Best-effort company name for a ticker, for use as the search query.

    Malaysian coverage refers to companies by name ("Maybank"), never by
    Yahoo's KLSE code ("1155.KL"), so searching the raw ticker returns
    near-nothing for Bursa names. Falls back to the bare ticker (exchange
    suffix stripped) when the yfinance lookup fails.
    """
    if ticker in _name_cache:
        return _name_cache[ticker]

    canonical = normalize_symbol(ticker)
    fallback = canonical.split(".")[0]
    name = None
    try:
        import yfinance as yf

        info = yf_retry(lambda: yf.Ticker(canonical).info)
        name = (info or {}).get("shortName") or (info or {}).get("longName")
    except Exception as e:
        # A name-lookup failure must not block the news search itself — fall
        # back to the bare ticker and carry on.
        logger.warning("Could not resolve company name for %s: %s", ticker, e)

    resolved = name or fallback
    _name_cache[ticker] = resolved
    return resolved


def _parse_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        source_el = item.find("source")

        pub_dt = None
        if pubdate_el is not None and pubdate_el.text:
            try:
                pub_dt = parsedate_to_datetime(pubdate_el.text)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pub_dt = None

        items.append({
            "title": (title_el.text if title_el is not None else "") or "",
            "link": (link_el.text if link_el is not None else "") or "",
            "publisher": (source_el.text if source_el is not None else "") or "Google News",
            "pub_date": pub_dt,
        })
    return items


def _fetch(query: str, timeout: float) -> list[dict] | None:
    """Fetch and parse one search query. ``None`` means the fetch failed
    (distinct from a fetch that succeeded and matched nothing)."""
    url = _RSS_URL.format(query=quote_plus(query))
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return _parse_rss(_read_capped(resp))
    except HTTPError as exc:
        logger.warning("Google News RSS fetch failed for %r: %s", query, exc)
        return None
    except (OSError, http.client.HTTPException, ET.ParseError) as exc:
        logger.warning("Google News RSS fetch failed for %r: %s", query, exc)
        return None


def _format_items(items: list[dict]) -> str:
    lines = []
    for it in items:
        lines.append(f"### {it['title']} (source: {it['publisher']})")
        if it["link"]:
            lines.append(f"Link: {it['link']}")
        lines.append("")
    return "\n".join(lines)


def _trusted_names() -> set[str] | None:
    """Lower-cased trusted publisher names, or ``None`` when filtering is off."""
    from .config import get_config

    config = get_config()
    if not config.get("trusted_news_only", True):
        return None
    names = config.get("trusted_news_sources") or TRUSTED_MY_NEWS_SOURCES
    return {n.strip().lower() for n in names}


def _split_by_trust(items: list[dict], trusted: set[str] | None) -> tuple[list[dict], list[dict]]:
    """Partition items into (trusted, other); everything is trusted when filtering is off."""
    if trusted is None:
        return items, []
    keep = [it for it in items if it["publisher"].strip().lower() in trusted]
    rest = [it for it in items if it["publisher"].strip().lower() not in trusted]
    return keep, rest


_UNVERIFIED_NOTE = (
    "Note: none of these articles come from an established news outlet or "
    "official source; treat them as unverified and weigh them lightly.\n"
)


def get_news(ticker: str, start_date: str, end_date: str, timeout: float = 10.0) -> str:
    """Ticker-specific news via MY-localized Google News RSS search.

    Resolves ``ticker`` to a company name and bounds the search server-side
    with Google's ``after:``/``before:`` operators, so a historical/backtest
    ``end_date`` searches that actual window rather than "recent news".
    """
    query_name = _resolve_query_name(ticker)
    # Google's before: appears to be exclusive of the given day in practice;
    # push it one day past end_date so an article published on end_date
    # itself isn't dropped, matching this codebase's half-open window
    # convention (date_window.in_window).
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    before = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    query = f"{query_name} after:{start_date} before:{before}"

    items = _fetch(query, timeout)
    if items is None:
        return (
            f"<Google News unavailable for {ticker}: fetch failed; "
            f"this is not an absence of news>"
        )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    # Belt-and-braces re-filter on the parsed pubDate: the query's after:/
    # before: operators do the real bounding server-side, but re-checking
    # locally costs nothing and guards against a stray off-window result.
    kept = [it for it in items if in_window(it["pub_date"], start_dt, end_dt)]
    if not kept:
        return (
            f"No news found for {ticker} (searched as {query_name!r}) "
            f"between {start_date} and {end_date}"
        )

    # Smaller companies may only be covered by less established sites; show
    # those (flagged) rather than claim there was no news at all.
    trusted, other = _split_by_trust(kept, _trusted_names())
    note = "" if trusted else _UNVERIFIED_NOTE
    header = f"## {ticker} News (searched as {query_name!r}), from {start_date} to {end_date}:\n"
    return header + note + "\n" + _format_items(trusted or other)


def get_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Malaysia-focused macro/market news via Google News RSS.

    Runs each of the configured queries (``my_news_queries``, default
    ``DEFAULT_MY_QUERIES``) bounded to ``[curr_date - look_back_days,
    curr_date]``, keeps trusted publishers, dedupes by title, and caps the
    result at ``limit`` articles. Each topic gets an equal share of ``limit``
    first, so the first broad query cannot fill the whole budget and starve
    the topics after it; any unused share is then filled in query order.
    """
    from .config import get_config

    config = get_config()
    if look_back_days is None:
        look_back_days = config.get("global_news_lookback_days", 7)
    if limit is None:
        limit = config.get("global_news_article_limit", 10)
    queries = list(config.get("my_news_queries") or DEFAULT_MY_QUERIES)
    trusted_names = _trusted_names()

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")
    before = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    seen_titles: set[str] = set()
    per_query: list[list[dict]] = []
    untrusted: list[dict] = []
    any_fetch_succeeded = False

    for q in queries:
        query = f"{q} after:{start_date} before:{before}"
        items = _fetch(query, timeout=10.0)
        if items is None:
            continue
        any_fetch_succeeded = True
        in_range = [it for it in items if in_window(it["pub_date"], start_dt, end_dt)]
        trusted, other = _split_by_trust(in_range, trusted_names)
        fresh = []
        for it in trusted:
            if it["title"] and it["title"] not in seen_titles:
                seen_titles.add(it["title"])
                fresh.append(it)
        per_query.append(fresh)
        untrusted.extend(other)

    if not any_fetch_succeeded:
        return (
            "<Google News unavailable for Malaysia macro news: every query "
            "failed to fetch; this is not an absence of news>"
        )

    share = max(1, -(-limit // max(1, len(queries))))  # ceil(limit / queries)
    kept = [it for items in per_query for it in items[:share]]
    leftovers = [it for items in per_query for it in items[share:]]
    kept = (kept + leftovers)[:limit]

    note = ""
    if not kept and untrusted:
        note = _UNVERIFIED_NOTE
        seen: set[str] = set()
        for it in untrusted:
            if it["title"] and it["title"] not in seen and len(kept) < limit:
                seen.add(it["title"])
                kept.append(it)
    if not kept:
        return f"No Malaysia macro news found between {start_date} and {curr_date}"

    header = f"## Malaysia Market News, from {start_date} to {curr_date}:\n"
    return header + note + "\n" + _format_items(kept)
