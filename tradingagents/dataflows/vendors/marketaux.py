"""Marketaux news vendor — licensed JSON news API covering 80+ markets.

Marketaux (api.marketaux.com) aggregates 5,000+ news sources across 80+
markets, including official disclosure channels for the EU market such as
EQS/DGAP, which are published as news articles here. Authentication is a
plain ``api_token`` query parameter; the token is read from the
``MARKETAUX_API_TOKEN`` environment variable only — never hardcoded, never
logged, never written into reports.

Scope and honest limits (kept in the output header so agents read it):

* This is a **news** vendor: articles, with per-article sentiment scores
  and entity matching. It is **not** a structured PDMR/insider
  transactions dataset — insider *disclosure notices* may surface as
  articles (e.g. from eqs-news.com), but structured insider lists remain
  the separate ``get_insider_transactions`` tool.
* Sentiment here is **news-based** (Marketaux ``sentiment_score`` per
  article), not retail investor sentiment (no StockTwits/Reddit data).
* ``limit`` returns a sample of the matched articles (server-side clamp
  depends on the subscription plan); an empty window is reported as a
  coverage caveat, never as proof that no news exists.

Ticker-agnostic: the user's ticker is used as-is; a known exchange
suffix is mapped to the ISO country for entity disambiguation
(``RHM.DE`` -> ``de``). When entity resolution finds no match, the raw
ticker is passed through as the symbol so coverage gaps stay visible
instead of silently switching symbols.
"""

from __future__ import annotations

import os
from datetime import datetime

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import coverage_gap
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.net import get_scrubbed

API_BASE = "https://api.marketaux.com/v1"
REQUEST_TIMEOUT = 30

# Known exchange suffix -> ISO-3166 alpha-2 country used by Marketaux's
# ``countries`` filter. Unknown suffixes are simply omitted from the query.
_COUNTRY_MAP = {
    ".DE": "de",
    ".US": "us",
    ".AT": "at",
    ".CH": "ch",
    ".FR": "fr",
    ".NL": "nl",
    ".ES": "es",
    ".IT": "it",
    ".UK": "gb",
    ".GB": "gb",
}

_SENTIMENT_NOTE = (
    "Sentiment values are Marketaux news-based sentiment scores, not retail "
    "investor sentiment."
)


def get_marketaux_api_token() -> str:
    """The Marketaux token, or empty when unset (callers raise/branch)."""
    return (os.getenv("MARKETAUX_API_TOKEN") or "").strip()


def _country_for(ticker: str) -> str:
    """ISO-2 country from a known exchange suffix, else '' (no filter)."""
    upper = ticker.upper()
    for suffix, code in _COUNTRY_MAP.items():
        if upper.endswith(suffix):
            return code
    return ""


def _get_json(path: str, params: dict, token: str):
    """GET one Marketaux endpoint, raising VendorUnavailableError on failure.

    The token is injected as the ``api_token`` query param here (callers never
    handle it), and ``get_scrubbed`` keeps it out of every error message by
    passing it as the ``secret``. Auth errors (401/403), rate limits (429),
    and transport errors all map to VendorUnavailableError so the router
    falls back to the next vendor; a 404 means the entity is not covered,
    which the caller treats as a coverage gap (no exception).
    """
    query = dict(params)
    query["api_token"] = token
    try:
        response = get_scrubbed(
            f"{API_BASE}{path}",
            params=query,
            timeout=REQUEST_TIMEOUT,
            secret=token,
            passthrough=(401, 403, 404, 429),
        )
    except Exception as exc:  # HTTP/transport error; scrub the token before re-raising
        msg = str(exc)
        if token:
            msg = msg.replace(token, "***")  # defense in depth on top of get_scrubbed
        raise VendorUnavailableError(f"marketaux request failed: {msg}") from None
    if response.status_code in (401, 403):
        raise VendorUnavailableError(
            "marketaux rejected the API token (401/403) — check "
            "MARKETAUX_API_TOKEN and the subscription plan"
        )
    if response.status_code == 429:
        raise VendorUnavailableError(
            "marketaux rate limit reached (429) — daily request quota exhausted"
        )
    if response.status_code == 404:
        return None  # entity/endpoint not covered — a coverage gap, not a fault
    if not response.ok:
        raise VendorUnavailableError(
            f"marketaux returned HTTP {response.status_code} for {path}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise VendorUnavailableError(f"marketaux returned invalid JSON: {exc}") from None


def _resolve_symbol(token: str, ticker: str, country: str) -> tuple[str, str]:
    """Resolve ``ticker`` to a Marketaux symbol via entity search.

    Strategy (verified against the live API for RHM.DE): Marketaux matches
    the *full symbol string*, so the full ticker (``RHM.DE``) is the primary
    lookup — it returns the exact listing. The bare root (``RHM``) is queried
    second, only when the full lookup yields no exact match and the ticker
    carries an exchange suffix. Returns (symbol, note); on any resolution
    failure the raw ticker is passed through so a guessed symbol never
    silently changes the subject of the analysis.
    """
    root = ticker.split(".")[0]
    terms: list[str] = [ticker]
    if root.upper() != ticker.upper():
        terms.append(root)

    candidates: list[dict] = []
    for term in terms:
        params: dict = {"search": term, "limit": 10}
        if country:
            params["countries"] = country
        payload = _get_json("/entity/search", params, token)
        data = (payload or {}).get("data") or []
        data = [c for c in data if isinstance(c, dict)]
        candidates.extend(data)
        # Early exit: an exact full-ticker match is unambiguous.
        for cand in data:
            if (cand.get("symbol") or "").upper() == ticker.upper():
                return (
                    cand.get("symbol") or ticker,
                    f"entity search confirmed exact symbol {cand.get('symbol')}",
                )

    if not candidates:
        return ticker, f"entity search found no entity for {ticker}; queried raw symbol"

    equities = [c for c in candidates if c.get("type") in (None, "equity")]
    if not equities:
        return ticker, f"entity search matched no suitable equity for {ticker}; queried raw symbol"

    # No exact match: rank by match_score when present, tie-break on root affinity.
    def rank(c: dict):
        score = c.get("match_score")
        score = float(score) if score is not None else -1.0
        root_affine = 1 if (c.get("symbol") or "").split(".")[0].upper() == root.upper() else 0
        return (score, root_affine)

    best = max(equities, key=rank)
    sym = best.get("symbol") or ticker
    note = f"entity search resolved {ticker} to {sym} ({best.get('name') or 'n/a'})"
    if best.get("match_score") is not None:
        note += f" (match_score {float(best['match_score']):.2f})"
    else:
        note += " (no match_score returned; listing chosen by root affinity)"
    return sym, note


def _fmt_sentiment(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):+.3f}"
    except (TypeError, ValueError):
        return "n/a"


def get_news_marketaux(ticker: str, start_date: str, end_date: str) -> str:
    """News about ``ticker`` in the window, from the Marketaux API.

    Output follows the other news vendors' conventions (markdown header +
    ``### date — title`` blocks) and carries a provenance header naming the
    vendor, the resolved symbol, the window, and the coverage caveats.
    """
    token = get_marketaux_api_token()
    if not token:
        raise VendorNotConfiguredError(
            "MARKETAUX_API_TOKEN environment variable is not set; "
            "add the token to the profile .env to enable the marketaux news vendor"
        )

    for label, value in (("start_date", start_date), ("end_date", end_date)):
        datetime.strptime(value, "%Y-%m-%d")  # ValueError on malformed dates
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")

    country = _country_for(ticker)
    symbol, note = _resolve_symbol(token, ticker, country)
    resolved = "" if symbol == ticker else f" (resolved to {symbol})"

    payload = _get_json(
        "/news/all",
        {
            "symbols": symbol,
            "filter_entities": "true",
            "published_after": f"{start_date}T00:00",
            "published_before": f"{end_date}T23:59",
            "limit": max(1, int(get_config().get("news_article_limit", 20))),
            "page": 1,
        },
        token,
    )
    if payload is None:
        raise VendorUnavailableError(
            f"marketaux does not cover {symbol} (entity/news endpoint 404)"
        )

    meta = payload.get("meta") or {}
    found = int(meta.get("found") or 0)
    articles = [a for a in (payload.get("data") or []) if isinstance(a, dict)]

    def pub(item: dict) -> str:
        return (item.get("published_at") or "")[:10]

    def pub_dt(item: dict) -> datetime | None:
        # A real datetime (or None) so coverage_gap can bound the observed
        # window; it expects datetime objects, not date strings.
        raw = item.get("published_at") or ""
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    in_range = [a for a in articles if start_date <= pub(a) <= end_date]
    scores = [a.get("sentiment_score") for a in in_range]
    scores = [float(s) for s in scores if s is not None]
    avg = f"{sum(scores) / len(scores):+.3f}" if scores else "n/a"

    lines = [
        f"## Marketaux news: {ticker}{resolved}",
        f"- Source: marketaux.com — licensed JSON news API (5,000+ sources, 80+ markets; "
        f"official EU disclosure channels such as EQS/DGAP appear as published articles). "
        f"Resolution: {note}.",
        f"- Window: {start_date} to {end_date} | {found} matched, {len(in_range)} returned "
        f"(limit-clamped sample; plan limits apply) | average news sentiment {avg}",
        f"- Coverage: news articles only. PDMR/insider disclosures may appear as articles "
        f"but this is not a structured insider-transactions feed. {_SENTIMENT_NOTE}",
        "",
    ]
    if not in_range:
        # A returned string would stop the vendor chain (first string wins),
        # suppressing every other news vendor for a symbol whose real news may
        # sit in a source this clamped sample missed (free plan caps the
        # sample). Raise the typed error so the chain continues; the terminal
        # vendor delivers the user-facing "no news" answer. The coverage
        # caveat, if any, rides in the error detail (visible in the log).
        gap = coverage_gap(
            (pub_dt(a) for a in articles),
            start_date, end_date, "marketaux news",
            f"{ticker} news",
        )
        raise NoMarketDataError(
            ticker,
            symbol,
            (gap or f"no {symbol} articles in window {start_date}..{end_date} "
                    "(limited sample, plan limits apply) — not proof that no "
                    f"{ticker} news exists"),
        )

    in_range.sort(key=lambda a: (pub(a), a.get("title") or ""), reverse=True)
    limit = max(1, int(get_config().get("news_article_limit", 20)))
    for item in in_range[:limit]:
        date = pub(item) or "undated"
        title = (item.get("title") or "untitled").strip()
        source = item.get("source") or "unknown source"
        url = item.get("url") or ""
        desc = (item.get("description") or item.get("snippet") or "").strip()
        lines.append(f"### {date} — {title} (source: {source})")
        lines.append(f"Sentiment: {_fmt_sentiment(item.get('sentiment_score'))}")
        if desc:
            lines.append(desc)
        if url:
            lines.append(f"Link: {url}")
        lines.append("")
    if len(in_range) > limit:
        lines.append(f"_(showing {limit} of {len(in_range)} matched articles)_")
    return "\n".join(lines).strip()
