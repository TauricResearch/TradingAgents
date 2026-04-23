"""Polymarket prediction market signals — macro event probabilities.

Fetches active prediction markets from Polymarket's public API,
filters for financially relevant events, and returns structured signals
for injection into analyst context and portfolio reports.

No API key required — public endpoint.
"""

import datetime
import json
import re
import sys
from typing import TypedDict

import requests


class PolymarketSignal(TypedDict):
    """A single prediction market signal."""
    event: str          # Market question, e.g. "Fed cuts rates June 2026"
    probability: float  # 0.0–1.0, e.g. 0.72 = 72% chance
    volume: str         # Human-readable, e.g. "$2.1M"
    category: str       # Fed/Rates, Economy, Trade, Regulation, Corporate, Crypto, Energy, Tech, Macro
    end_date: str       # ISO date, e.g. "2026-06-30"


class PolymarketResult(TypedDict):
    """Return type of fetch_polymarket_signals()."""
    signals: list[PolymarketSignal]
    fetched_at: str  # ISO datetime

# Gamma API is the public market listing endpoint (CLOB is the order book)
GAMMA_API_URL = "https://gamma-api.polymarket.com"

# Keywords that indicate financially relevant markets
# Use word boundaries where needed to avoid false positives (e.g. "eth" in "Netherlands")
RELEVANT_KEYWORDS = [
    # Macro / Fed
    "fed ", "federal reserve", "interest rate", "rate cut", "rate hike",
    "inflation", "cpi", " gdp", "recession", "unemployment", "jobs report",
    "tariff", "trade war", "nonfarm",
    # Regulatory / political
    "antitrust", "regulation", "sec ", "ftc ",
    # Tech / earnings
    "earnings", "revenue", "stock price", " ipo ", "acquisition", "merger",
    # Crypto (risk sentiment proxy)
    "bitcoin", " btc ", "ethereum", " eth ", "crypto",
    # Sectors
    "crude oil", "oil price", "semiconductor", " ai ", "artificial intelligence",
]

# Minimum volume in USD to consider a market meaningful
MIN_VOLUME_USD = 100_000

# Minimum probability to include — filters out unlikely events (noise)
MIN_PROBABILITY = 0.40


def fetch_polymarket_signals(max_signals: int = 20) -> PolymarketResult:
    """Fetch financially relevant prediction market signals from Polymarket.

    Returns structured signal list:
        {
            "signals": [{"event": str, "probability": float, "volume": str, "category": str, "end_date": str}],
            "fetched_at": str (ISO),
        }
    """
    try:
        markets = _fetch_active_markets()
    except Exception as e:
        print(f"  ⚠️ Polymarket fetch failed: {e}", file=sys.stderr)
        return {"signals": [], "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}

    signals = _filter_relevant(markets, max_signals)
    result: PolymarketResult = {
        "signals": signals,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    return result


def _fetch_active_markets() -> list[dict]:
    """Fetch active markets from Polymarket Gamma API.

    Uses server-side filters to reduce payload:
    - volume_num_min: only markets with meaningful liquidity (>$100k)
    - end_date_max: only markets resolving within 6 months
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    markets = []
    offset = 0
    limit = 100
    max_pages = 10  # up to 1000 markets — enough for keyword filtering
    with requests.Session() as session:
        for _ in range(max_pages):
            resp = session.get(
                f"{GAMMA_API_URL}/markets",
                params={
                    "limit": limit,
                    "offset": offset,
                    "active": "true",
                    "closed": "false",
                    "volume_num_min": MIN_VOLUME_USD,
                    "end_date_max": cutoff,
                },
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            markets.extend(batch)
            if len(batch) < limit:
                break
        offset += limit
    return markets


def _parse_volume(market: dict) -> float:
    """Extract volume as float USD from market data."""
    vol = market.get("volume") or market.get("volumeNum") or 0
    try:
        return float(vol)
    except (TypeError, ValueError):
        return 0.0


def _format_volume(vol: float) -> str:
    """Format volume as human-readable string."""
    if vol >= 1_000_000:
        return f"${vol / 1_000_000:.1f}M"
    if vol >= 1_000:
        return f"${vol / 1_000:.0f}K"
    return f"${vol:.0f}"


def _is_relevant(question: str) -> str | None:
    """Check if a market question matches relevant keywords. Returns category or None."""
    q = f" {question.lower()} "  # pad for word-boundary matching
    matched = False
    for kw in RELEVANT_KEYWORDS:
        if kw in q:
            matched = True
            break
    if not matched:
        return None
    # Categorize by first matching group
    if any(k in q for k in ("fed ", "rate cut", "rate hike", "interest rate", "federal reserve")):
        return "Fed/Rates"
    if any(k in q for k in ("recession", " gdp", "inflation", "cpi", "unemployment", "jobs report", "nonfarm")):
        return "Economy"
    if any(k in q for k in ("tariff", "trade war")):
        return "Trade"
    if any(k in q for k in ("antitrust", "regulation", "sec ", "ftc ")):
        return "Regulation"
    if any(k in q for k in ("earnings", "revenue", "stock price", " ipo ", "acquisition", "merger")):
        return "Corporate"
    if any(k in q for k in ("bitcoin", " btc ", "ethereum", " eth ", "crypto")):
        return "Crypto"
    if any(k in q for k in ("crude oil", "oil price")):
        return "Energy"
    if any(k in q for k in ("semiconductor", " ai ", "artificial intelligence")):
        return "Tech"
    return "Macro"


def _extract_probability(market: dict) -> float:
    """Extract the 'Yes' probability from market data."""
    # Gamma API returns outcomePrices as JSON string: '["0.72","0.28"]'
    prices = market.get("outcomePrices")
    if prices:
        try:
            if isinstance(prices, str):
                prices = json.loads(prices)
            return float(prices[0])
        except (json.JSONDecodeError, IndexError, TypeError, ValueError):
            pass
    # Fallback fields
    for field in ("bestBid", "lastTradePrice"):
        val = market.get(field)
        if val:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def _filter_relevant(markets: list[dict], max_signals: int) -> list[PolymarketSignal]:
    """Filter and rank markets by relevance and volume.

    Server-side filters (volume_num_min, end_date_max) already applied in
    _fetch_active_markets. This does keyword-based category matching and ranking.
    """
    candidates = []

    for m in markets:
        question = m.get("question") or m.get("title") or ""
        if not question:
            continue

        category = _is_relevant(question)
        if not category:
            continue

        vol = _parse_volume(m)
        if vol < MIN_VOLUME_USD:
            continue  # safety net — should already be filtered server-side

        prob = _extract_probability(m)
        if prob < MIN_PROBABILITY:
            continue

        end = m.get("endDate") or m.get("end_date_iso") or ""
        candidates.append({
            "event": question,
            "probability": round(prob, 2),
            "volume": _format_volume(vol),
            "volume_raw": vol,
            "category": category,
            "end_date": end[:10] if end else "",
        })

    # Sort by volume descending (highest liquidity = most meaningful signal)
    candidates.sort(key=lambda c: c["volume_raw"], reverse=True)

    # Drop internal field
    for c in candidates[:max_signals]:
        c.pop("volume_raw", None)
    return candidates[:max_signals]


def format_signals_text(result: PolymarketResult) -> str:
    """Format signals as plain text for LLM context injection."""
    signals = result.get("signals", [])
    if not signals:
        return ""
    lines = ["Current prediction market signals (Polymarket):"]
    for s in signals:
        lines.append(f"- {s['event']}: {s['probability']:.0%} probability ({s['volume']} volume) [{s['category']}]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ticker relevance mapping
# ---------------------------------------------------------------------------

# Category → keyword patterns → affected sectors/tickers
# Maps Polymarket signal categories + event keywords to portfolio tickers
_SECTOR_MAP: dict[str, list[str]] = {
    # Tech / growth
    "tech": ["AAPL", "MSFT", "GOOG", "GOOGL", "META", "AMZN", "NVDA", "AMD", "INTC", "AVGO",
             "CRM", "NOW", "ADBE", "ORCL", "PLTR", "SNOW", "NET", "DDOG", "MDB", "CRWD"],
    # Semiconductors
    "semiconductor": ["NVDA", "AMD", "INTC", "AVGO", "TSM", "QCOM", "MU", "MRVL", "KLAC", "LRCX", "AMAT"],
    # AI
    "ai": ["NVDA", "MSFT", "GOOG", "GOOGL", "META", "AMZN", "AMD", "AVGO", "PLTR", "CRM", "NOW"],
    # Growth / rate-sensitive
    "rates": ["MSFT", "CRM", "NOW", "ADBE", "SNOW", "NET", "DDOG", "CRWD", "MDB"],
    # Cyclical / recession-sensitive
    "cyclical": ["AMZN", "HD", "LOW", "NKE", "SBUX", "DIS", "BA"],
    # Trade / tariff / China supply chain
    "trade": ["AAPL", "NVDA", "AMD", "INTC", "AVGO", "TSM", "QCOM", "NKE"],
    # Regulation / antitrust
    "regulation": ["META", "GOOG", "GOOGL", "AAPL", "AMZN", "MSFT"],
    # Crypto / risk sentiment
    "crypto": ["COIN", "MSTR", "SQ", "PYPL", "HOOD"],
    # Energy
    "energy": ["XOM", "CVX", "COP", "SLB", "OXY", "DVN", "EOG"],
    # Financials
    "financials": ["JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "SCHW"],
}

# Map Polymarket categories to sector keys
_CATEGORY_SECTOR_MAP: dict[str, list[str]] = {
    "Fed/Rates": ["rates", "financials", "tech"],
    "Economy": ["cyclical", "financials"],
    "Trade": ["trade", "semiconductor"],
    "Regulation": ["regulation"],
    "Corporate": ["tech"],
    "Crypto": ["crypto"],
    "Energy": ["energy"],
    "Tech": ["tech", "ai", "semiconductor"],
    "Macro": ["cyclical", "financials", "rates"],
}

# Extra keyword → sector overrides for event text matching
_EVENT_KEYWORD_SECTORS: list[tuple[str, str]] = [
    ("semiconductor", "semiconductor"),
    (" ai ", "ai"),
    ("artificial intelligence", "ai"),
    ("tariff", "trade"),
    ("trade war", "trade"),
    ("antitrust", "regulation"),
    ("rate cut", "rates"),
    ("rate hike", "rates"),
    ("recession", "cyclical"),
    ("oil", "energy"),
    ("crude", "energy"),
    ("bitcoin", "crypto"),
    ("crypto", "crypto"),
]


def map_signals_to_tickers(signals: list[PolymarketSignal], held_tickers: set[str]) -> dict[int, list[str]]:
    """Map each signal (by index) to relevant held tickers.

    Returns {signal_index: [ticker, ...]} — only tickers actually in the portfolio.
    """
    result: dict[int, list[str]] = {}
    held_upper = {t.upper() for t in held_tickers}

    for i, s in enumerate(signals):
        sectors: set[str] = set()

        # 1. Category-based mapping
        cat = s.get("category", "")
        for sector_key in _CATEGORY_SECTOR_MAP.get(cat, []):
            sectors.add(sector_key)

        # 2. Event keyword overrides
        event_lower = f" {s.get('event', '').lower()} "
        for kw, sector_key in _EVENT_KEYWORD_SECTORS:
            if kw in event_lower:
                sectors.add(sector_key)

        # 3. Direct ticker mention in event text
        direct = [t for t in held_upper if re.search(rf"\b{re.escape(t)}\b", event_lower.upper())]

        # 4. Collect all tickers from matched sectors, intersect with held
        matched = set(direct)
        for sector_key in sectors:
            for t in _SECTOR_MAP.get(sector_key, []):
                if t in held_upper:
                    matched.add(t)

        if matched:
            result[i] = sorted(matched)

    return result


# ---------------------------------------------------------------------------
# Per-ticker contract discovery via Gamma Search API
# ---------------------------------------------------------------------------


class TickerContract(TypedDict):
    """A Polymarket contract relevant to a specific ticker."""
    id: str
    slug: str
    question: str
    title: str          # Parent event title
    tags: list[str]
    volume24hr: float
    liquidity: float
    end_date: str       # ISO date
    probability: float  # 0.0–1.0
    active: bool
    source: str         # "ticker" or "company_name" — which search found it


def search_ticker_contracts(ticker: str, company_name: str = "", max_events: int = 5) -> list[TickerContract]:
    """Search Polymarket for contracts related to a specific ticker/company.

    Performs two searches via Gamma `GET /public-search`:
    1. By ticker symbol (e.g. "AMZN")
    2. By company name (e.g. "Amazon") if provided

    Events are scored by relevance, then the top `max_events` are expanded:
    each event's full market list is fetched via `/events/{id}` to ensure
    all associated markets are included (search results may truncate).

    Results are deduplicated by market id and returned as a unified list.
    """
    # Collect raw events from search (not yet expanded into markets)
    raw_events: list[tuple[dict, str]] = []  # (event_dict, source)
    _search_and_collect_events(ticker, "ticker", raw_events)
    if company_name and company_name.upper() != ticker.upper():
        _search_and_collect_events(company_name, "company_name", raw_events)

    # Score events by relevance to ticker, take top N
    scored_events = _score_events(raw_events, ticker, company_name)
    top_events = scored_events[:max_events]

    # Expand top events: fetch full event detail to get all embedded markets
    # Falls back to search-embedded markets if event detail fetch fails
    seen_ids: set[str] = set()
    contracts: list[TickerContract] = []
    for event, source, _score in top_events:
        event_id = event.get("id", "")
        full_event = _fetch_event_detail(event_id) if event_id else None
        # Use full event if it has markets, otherwise fall back to search-embedded
        expanded = full_event if full_event and full_event.get("markets") else event
        event_title = expanded.get("title", "") or event.get("title", "")
        event_tags = _normalize_tags(expanded.get("tags", []) or event.get("tags", []))
        for m in expanded.get("markets", []):
            mid = m.get("id", "")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            contracts.append(_normalize_market(m, event_title, event_tags, source))

    # Task 15: filter active, exclude low-liquidity, score & return top N
    contracts = filter_ticker_contracts(contracts, ticker, company_name, top_n=5)

    return contracts


# Minimum liquidity (total volume) to include a per-ticker contract
MIN_TICKER_LIQUIDITY_USD = 50_000


def filter_ticker_contracts(contracts: list[TickerContract], ticker: str, company_name: str = "", top_n: int = 5) -> list[TickerContract]:
    """Filter to active contracts with ≥$50k liquidity, score by relevance, return top N.

    Task 15: active=true, exclude low-liquidity (<$50k), return top 5 per ticker.
    """
    filtered = [c for c in contracts if c.get("active") and c.get("liquidity", 0) >= MIN_TICKER_LIQUIDITY_USD]
    scored = score_ticker_contracts(filtered, ticker, company_name)
    # Strip internal score key from output
    for c in scored:
        c.pop("_relevance_score", None)
    return scored[:top_n]


def _normalize_market(m: dict, event_title: str, event_tags: list[str], source: str) -> TickerContract:
    """Normalize a single Gamma API market object into a TickerContract.

    Field mapping from Gamma API → TickerContract:
      id           ← m["id"]
      slug         ← m["slug"]
      question     ← m["question"]
      title        ← parent event title
      tags         ← parent event tags (label strings)
      volume24hr   ← m["volume1wk"] / 7  (API has no daily field)
      liquidity    ← m["volumeNum"] (total volume as liquidity proxy)
      end_date     ← m["endDateIso"] or m["endDate"][:10]
      probability  ← outcomePrices[0] or lastTradePrice
      active       ← m["active"] and not m["closed"]
      source       ← "ticker" or "company_name"
    """
    return TickerContract(
        id=m.get("id", ""),
        slug=m.get("slug", ""),
        question=m.get("question", ""),
        title=event_title,
        tags=event_tags,
        volume24hr=_safe_float(m.get("volume1wk", 0)) / 7,
        liquidity=_safe_float(m.get("volumeNum", 0)),
        end_date=m.get("endDateIso") or (m.get("endDate") or "")[:10],
        probability=_extract_probability(m),
        active=bool(m.get("active")) and not bool(m.get("closed")),
        source=source,
    )


def _search_and_collect_events(query: str, source: str, out: list[tuple[dict, str]]):
    """Execute a Gamma public-search and collect raw events (not yet expanded into markets).

    Appends (event_dict, source) tuples to out. Deduplication by event id.
    """
    try:
        resp = requests.get(
            f"{GAMMA_API_URL}/public-search",
            params={"q": query},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️ Polymarket search '{query}' failed: {e}", file=sys.stderr)
        return

    seen_event_ids = {e.get("id") for e, _ in out}
    for event in data.get("events", []):
        eid = event.get("id", "")
        if eid and eid not in seen_event_ids:
            seen_event_ids.add(eid)
            out.append((event, source))


def _score_events(raw_events: list[tuple[dict, str]], ticker: str, company_name: str = "") -> list[tuple[dict, str, float]]:
    """Score and rank raw events by relevance to ticker. Returns sorted (event, source, score)."""
    ticker_upper = ticker.upper()
    company_lower = company_name.lower().strip() if company_name else ""
    scored = []
    for event, source in raw_events:
        score = 0.0
        title = event.get("title", "")
        title_upper = title.upper()
        tags = _normalize_tags(event.get("tags", []))
        tags_upper = [t.upper() for t in tags]

        # Ticker in title/tags
        if ticker_upper in title_upper.split():
            score += 50
        elif ticker_upper in title_upper:
            score += 40
        if ticker_upper in tags_upper:
            score += 30

        # Company name in title/tags
        if company_lower and len(company_lower) > 2:
            if company_lower in title.lower():
                score += 25
            if company_lower in [t.lower() for t in tags]:
                score += 20

        # Source bonus
        if source == "ticker":
            score += 10

        # Volume boost
        vol = _safe_float(event.get("volume", 0))
        if vol > 0:
            import math
            score += min(10, math.log10(max(vol, 1)) * 1.5)

        # Strongly prefer open events — closed markets have no actionable signal
        if event.get("closed"):
            score -= 100
        elif event.get("active"):
            score += 5

        scored.append((event, source, round(score, 1)))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored


def _fetch_event_detail(event_id: str) -> dict:
    """Fetch full event detail from Gamma API to get all embedded markets.

    Falls back to empty dict on failure (caller uses search-embedded markets).
    """
    try:
        resp = requests.get(f"{GAMMA_API_URL}/events/{event_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # API returns either a dict or a list with one element
        if isinstance(data, list):
            return data[0] if data else {}
        return data
    except Exception as e:
        print(f"  ⚠️ Polymarket event {event_id} fetch failed: {e}", file=sys.stderr)
        return {}


def _normalize_tags(raw_tags) -> list[str]:
    """Extract tag label strings from Gamma API tag objects or raw strings.

    Gamma returns tags as list of dicts: [{"id": "...", "label": "AMZN", ...}]
    or occasionally as a JSON string or comma-separated string.
    """
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except (ValueError, TypeError):
            return [t.strip() for t in raw_tags.split(",") if t.strip()]
    if not isinstance(raw_tags, list):
        return []
    labels = []
    for tag in raw_tags:
        if isinstance(tag, dict):
            label = tag.get("label", "")
            if label:
                labels.append(label)
        elif isinstance(tag, str) and tag.strip():
            labels.append(tag.strip())
    return labels


def _safe_float(val) -> float:
    """Convert value to float, defaulting to 0.0."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Per-ticker relevance scoring
# ---------------------------------------------------------------------------

# Weights for relevance scoring (higher = more relevant)
_SCORE_TICKER_IN_QUESTION = 50   # Ticker symbol appears in market question
_SCORE_TICKER_IN_TITLE = 40      # Ticker symbol appears in event title
_SCORE_TICKER_IN_TAGS = 30       # Ticker symbol appears in event tags
_SCORE_COMPANY_IN_QUESTION = 35  # Company name appears in market question
_SCORE_COMPANY_IN_TITLE = 25     # Company name appears in event title
_SCORE_COMPANY_IN_TAGS = 20      # Company name appears in event tags
_SCORE_SOURCE_TICKER = 10        # Found via ticker search (vs company name search)
_SCORE_LIQUIDITY_SCALE = 10      # Max bonus for liquidity (log-scaled)
_SCORE_VOLUME_SCALE = 5          # Max bonus for 24h volume (log-scaled)


def macro_signals_for_ticker(signals: list[PolymarketSignal], ticker: str, held_tickers: set[str]) -> list[TickerContract]:
    """Convert macro/sector signals relevant to a ticker into TickerContract dicts.

    Uses map_signals_to_tickers to find which macro signals affect this ticker,
    then wraps them as TickerContract with source="macro".
    """
    mapping = map_signals_to_tickers(signals, held_tickers)
    contracts: list[TickerContract] = []
    seen: set[str] = set()
    for i, tickers_list in mapping.items():
        if ticker.upper() not in [t.upper() for t in tickers_list]:
            continue
        s = signals[i]
        key = s.get("event", "")
        if key in seen:
            continue
        seen.add(key)
        # Parse volume string back to float for liquidity field
        vol_str = s.get("volume", "$0")
        vol = 0.0
        try:
            v = vol_str.replace("$", "").replace(",", "").strip()
            if v.endswith("M"):
                vol = float(v[:-1]) * 1_000_000
            elif v.endswith("K"):
                vol = float(v[:-1]) * 1_000
            else:
                vol = float(v)
        except (ValueError, TypeError):
            pass
        contracts.append(TickerContract(
            id=f"macro-{i}",
            slug="",
            question=f"[{s.get('category', 'Macro')}] {s['event']}",
            title=s.get("event", ""),
            tags=[s.get("category", "Macro")],
            volume24hr=0,
            liquidity=vol,
            end_date=s.get("end_date", ""),
            probability=s.get("probability", 0),
            active=True,
            source="macro",
        ))
    return contracts


def score_ticker_contracts(contracts: list[TickerContract], ticker: str, company_name: str = "") -> list[TickerContract]:
    """Score and sort contracts by weighted relevance to a ticker.

    Scoring hierarchy:
      1. Direct ticker mention in question/title/tags (highest)
      2. Company name mention in question/title/tags
      3. Source bonus (found via ticker search > company name search)
      4. Liquidity/volume boost (log-scaled, capped)

    Adds '_relevance_score' key to each contract dict. Returns sorted descending.
    """
    import math

    ticker_upper = ticker.upper()
    company_lower = company_name.lower().strip() if company_name else ""

    scored = []
    for c in contracts:
        score = 0.0
        q_upper = c.get("question", "").upper()
        t_upper = c.get("title", "").upper()
        tags_upper = [t.upper() for t in c.get("tags", [])]

        # Direct ticker mention
        if ticker_upper in q_upper.split():
            score += _SCORE_TICKER_IN_QUESTION
        elif ticker_upper in q_upper:
            score += _SCORE_TICKER_IN_QUESTION * 0.8
        if ticker_upper in t_upper.split():
            score += _SCORE_TICKER_IN_TITLE
        elif ticker_upper in t_upper:
            score += _SCORE_TICKER_IN_TITLE * 0.8
        if ticker_upper in tags_upper:
            score += _SCORE_TICKER_IN_TAGS

        # Company name mention
        if company_lower and len(company_lower) > 2:
            q_lower = c.get("question", "").lower()
            t_lower = c.get("title", "").lower()
            tags_lower = [t.lower() for t in c.get("tags", [])]
            if company_lower in q_lower:
                score += _SCORE_COMPANY_IN_QUESTION
            if company_lower in t_lower:
                score += _SCORE_COMPANY_IN_TITLE
            if company_lower in tags_lower:
                score += _SCORE_COMPANY_IN_TAGS

        # Source bonus
        if c.get("source") == "ticker":
            score += _SCORE_SOURCE_TICKER

        # Liquidity boost (log-scaled, 0–10 points)
        liq = c.get("liquidity", 0)
        if liq > 0:
            score += min(_SCORE_LIQUIDITY_SCALE, math.log10(max(liq, 1)) * 1.5)

        # Volume boost (log-scaled, 0–5 points)
        vol = c.get("volume24hr", 0)
        if vol > 0:
            score += min(_SCORE_VOLUME_SCALE, math.log10(max(vol, 1)))

        c_scored = dict(c)
        c_scored["_relevance_score"] = round(score, 1)
        scored.append(c_scored)

    scored.sort(key=lambda x: x["_relevance_score"], reverse=True)
    return scored
