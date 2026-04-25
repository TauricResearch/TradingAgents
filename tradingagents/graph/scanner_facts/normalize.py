"""Normalization and classification for scanner graph facts.

Pure logic only — no I/O, no LLM. Called by both adapters.

Key functions:
  canonicalize_sector(label)     → canonical sector name
  classify_node_type(label)      → node type string
  is_equity_ticker(label)        → bool
  infer_polarity(*parts)         → "bullish" | "bearish" | ""
  compute_confidence(source, **flags) → float in [0.10, 0.99]
"""

from __future__ import annotations

import enum
import logging
import re

_logger = logging.getLogger(__name__)

# ---------- Sector canonicalization ----------

_SECTOR_CANON: dict[str, str] = {
    # Direct aliases
    "information technology": "Technology",
    "tech": "Technology",
    "it sector": "Technology",
    "financial": "Financials",
    "financial services": "Financials",
    "finance": "Financials",
    "consumer cyclical": "Consumer Discretionary",
    "retail": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "staples": "Consumer Staples",
    "healthcare": "Health Care",
    "health care sector": "Health Care",
    "pharma": "Health Care",
    "biotech": "Health Care",
    "telecom": "Communication Services",
    "telecommunications": "Communication Services",
    "communications": "Communication Services",
    "media": "Communication Services",
    "industrial": "Industrials",
    "industrials sector": "Industrials",
    "basic materials": "Materials",
    "materials sector": "Materials",
    "reits": "Real Estate",
    "real estate sector": "Real Estate",
    "utilities sector": "Utilities",
    "energy sector": "Energy",
    "oil & gas": "Energy",
    # Already canonical — keep as-is
    "technology": "Technology",
    "financials": "Financials",
    "consumer discretionary": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "health care": "Health Care",
    "communication services": "Communication Services",
    "industrials": "Industrials",
    "materials": "Materials",
    "real estate": "Real Estate",
    "utilities": "Utilities",
    "energy": "Energy",
}

# Node types for canonical sector names
_CANONICAL_SECTORS: frozenset[str] = frozenset(_SECTOR_CANON.values())


def canonicalize_sector(label: str) -> str:
    """Return the canonical sector name for *label*, or the original if unknown."""
    key = (label or "").strip().lower()
    canonical = _SECTOR_CANON.get(key)
    if canonical:
        return canonical
    # Warn: this label will fall through to heuristic; needs alias entry
    _logger.warning("normalize: unknown sector label %r — add to aliases.py", label)
    return label.strip()


# ---------- Node type classification ----------

_MARKET_INDEXES: frozenset[str] = frozenset(
    {
        "s&p 500",
        "sp500",
        "s&p500",
        "spx",
        "nasdaq",
        "nasdaq composite",
        "ndx",
        "dow jones",
        "djia",
        "dow",
        "russell 2000",
        "rut",
    }
)

_MACRO_INDICATORS: frozenset[str] = frozenset(
    {
        "vix",
        "cboe volatility index",
        "cpi",
        "pce",
        "fed funds rate",
        "federal funds rate",
        "10y yield",
        "10-year treasury",
        "german cds",
        "us cds",
        "china cds",
        "sovereign cds",
        "dxy",
        "us dollar index",
    }
)

_COMMODITIES: frozenset[str] = frozenset(
    {
        "brent crude",
        "brent",
        "ice brent",
        "wti crude",
        "wti",
        "nymex crude",
        "gold",
        "xauusd",
        "spot gold",
        "silver",
        "xagusd",
        "natural gas",
        "nat gas",
        "copper",
        "comex copper",
    }
)

_FX_PAIRS: frozenset[str] = frozenset(
    {
        "eur/usd",
        "eurusd",
        "jpy/usd",
        "jpyusd",
        "usd/jpy",
        "usdjpy",
        "cny/usd",
        "cnyusd",
        "usd/cny",
        "usdcny",
        "gbp/usd",
        "gbpusd",
    }
)

_CRYPTO: frozenset[str] = frozenset(
    {
        "bitcoin",
        "btc",
        "xbtusd",
        "ethereum",
        "eth",
    }
)

# Short uppercase strings that look like tickers but are not
_TICKER_BLOCKLIST: frozenset[str] = frozenset(
    {
        "AI",
        "US",
        "FX",
        "ETF",
        "CEO",
        "SEC",
        "GDP",
        "CPI",
        "PCE",
        "VIX",
        "FED",
        "BUY",
        "SELL",
        "HOLD",
        "TOP",
        "NET",
        "NEW",
        "HIGH",
        "LOW",
        "ALL",
        "AND",
        "THE",
        "FOR",
        "ARE",
        "NOT",
        "BUT",
        "YTD",
        "YOY",
        "QOQ",
        "MOM",
        "EPS",
        "PE",
        "PB",
        "ROE",
        "ROA",
        "LNG",
        "IPO",
        "M&A",
        "ESG",
        "IT",
        "REIT",
        "IMF",
        "WTO",
        "N/A",
        "NA",
        "SECTOR",
        "THEME",
        "S&P",
        "SPX",
        "NDX",
        "DXY",
        "RUT",
        "VXX",
    }
)

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_FX_RE = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")


def classify_node_type(label: str) -> str:
    """Return the best-match node type for *label*.

    Logs a warning when falling back to heuristic Ticker classification
    so the alias registry can be updated.
    """
    norm = (label or "").strip()
    lower = norm.lower()

    if lower in _MARKET_INDEXES:
        return "MarketIndex"
    if lower in _MACRO_INDICATORS:
        return "MacroIndicator"
    if lower in _COMMODITIES:
        return "Commodity"
    if lower in _FX_PAIRS or _FX_RE.match(norm):
        return "CurrencyPair"
    if lower in _CRYPTO:
        return "CryptoAsset"
    if lower in {s.lower() for s in _CANONICAL_SECTORS}:
        return "Sector"

    # Multi-word labels not matched above → Theme
    if " " in norm or "-" in norm or "/" in norm:
        return "Theme"

    # Single uppercase token — likely a Ticker
    if _TICKER_RE.match(norm) and norm not in _TICKER_BLOCKLIST:
        _logger.debug("normalize: %r classified as Ticker by heuristic", norm)
        return "Ticker"

    # Final fallback → Theme
    return "Theme"


# ---------- Equity ticker guard ----------

_NOT_EQUITY: frozenset[str] = (
    _TICKER_BLOCKLIST
    | {s.upper() for s in _MARKET_INDEXES}
    | {s.upper() for s in _MACRO_INDICATORS}
    | {s.upper() for s in _COMMODITIES}
    | {s.upper() for s in _CRYPTO}
    | {"NOT APPLICABLE", "N/A", "NA", "SECTOR/THEME"}
)


def is_equity_ticker(label: str) -> bool:
    """Return True if *label* looks like a real equity ticker symbol."""
    norm = (label or "").strip()
    if not norm:
        return False
    upper = norm.upper()
    if upper in _NOT_EQUITY:
        return False
    if not _TICKER_RE.match(upper):
        return False
    return True


# ---------- Polarity inference ----------

_BULLISH_RE = re.compile(
    r"\b(bullish|outperform|accumulation|breakout|tailwind|momentum|strong|surge|rally|"
    r"recovery|gainer|buy|positive|growth|upward|acceleration|high.conviction|insider buying|"
    r"insider purchases|insider optimism|revival|confirms|strength)\b",
    re.IGNORECASE,
)
_BEARISH_RE = re.compile(
    r"\b(bearish|underperform|headwind|risk|tension|concern|lagging|decline|drag|"
    r"decliner|sell|caution|weak|deteriorat|outflow|decelerat|negative|reversal|"
    r"laggard|stress|disruption)\b",
    re.IGNORECASE,
)


def infer_polarity(*parts: str) -> str:
    """Return 'bullish', 'bearish', or '' based on *parts* combined text."""
    joined = " ".join(p or "" for p in parts)
    bull = bool(_BULLISH_RE.search(joined))
    bear = bool(_BEARISH_RE.search(joined))
    if bear and not bull:
        return "bearish"
    if bull and not bear:
        return "bullish"
    if bull and bear:
        # Both present: context-specific terms win; default to bearish (conservative)
        return "bearish"
    return ""


# ---------- Confidence computation ----------


class ConfidenceSource(enum.Enum):
    MACRO_JSON_STRUCTURED = "macro_json_structured"  # base 0.90
    MACRO_JSON_FREE_TEXT = "macro_json_free_text"  # base 0.70
    MD_PIPE_FULL = "md_pipe_full"  # base 0.95 (5-col row, evidence present)
    MD_PIPE_PARTIAL = "md_pipe_partial"  # base 0.75 (3–4 col, evidence present)
    MD_FREE_BULLET = "md_free_bullet"  # base 0.55 (no pipes, anchored)
    INFERRED_EDGE = "inferred_edge"  # base 0.50 (edge from implication phrasing)


_BASE_CONFIDENCE: dict[ConfidenceSource, float] = {
    ConfidenceSource.MACRO_JSON_STRUCTURED: 0.90,
    ConfidenceSource.MACRO_JSON_FREE_TEXT: 0.70,
    ConfidenceSource.MD_PIPE_FULL: 0.95,
    ConfidenceSource.MD_PIPE_PARTIAL: 0.75,
    ConfidenceSource.MD_FREE_BULLET: 0.55,
    ConfidenceSource.INFERRED_EDGE: 0.50,
}


def compute_confidence(
    source: ConfidenceSource,
    *,
    hedging: bool = False,
    polarity_empty: bool = False,
    heuristic_only: bool = False,
    corroborated: bool = False,
) -> float:
    """Return confidence in [0.10, 0.99] for an emission.

    Args:
        source: Base confidence source (see ConfidenceSource enum).
        hedging: Text contains hedge words ("may", "could", "potential", "uncertain").
        polarity_empty: Edge has no polarity on a sentiment-style edge.
        heuristic_only: Node was classified by lexical heuristic, not registry.
        corroborated: Same (source, relation, target) found in ≥2 distinct provenance files.
    """
    c = _BASE_CONFIDENCE[source]
    if hedging:
        c -= 0.10
    if polarity_empty:
        c -= 0.05
    if heuristic_only:
        c -= 0.15
    if corroborated:
        c += 0.05
    return round(max(0.10, min(0.99, c)), 4)
