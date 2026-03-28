"""API consumption estimation for TradingAgents.

Provides static estimates of how many external API calls each command
(analyze, scan, pipeline) will make, broken down by vendor. This helps
users decide whether they need an Alpha Vantage premium subscription.

Alpha Vantage tiers
-------------------
- **Free**: 25 API calls per day
- **Premium (30 $/month)**: 75 calls per minute, unlimited daily

Each ``get_*`` method that hits Alpha Vantage counts as **1 API call**,
regardless of how much data is returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
# Alpha Vantage tier limits
# ──────────────────────────────────────────────────────────────────────────────

AV_FREE_DAILY_LIMIT = 25
AV_PREMIUM_PER_MINUTE = 75

# ──────────────────────────────────────────────────────────────────────────────
# Per-method AV call cost.
# When Alpha Vantage is the vendor, each invocation of a route_to_vendor
# method triggers exactly one AV HTTP request — except get_indicators,
# which the LLM may call multiple times (once per indicator).
# ──────────────────────────────────────────────────────────────────────────────

_AV_CALLS_PER_METHOD: dict[str, int] = {
    "get_stock_data": 1,             # TIME_SERIES_DAILY_ADJUSTED
    "get_indicators": 1,             # SMA / EMA / RSI / MACD / BBANDS / ATR (1 call each)
    "get_fundamentals": 1,           # OVERVIEW
    "get_balance_sheet": 1,          # BALANCE_SHEET
    "get_cashflow": 1,               # CASH_FLOW
    "get_income_statement": 1,       # INCOME_STATEMENT
    "get_news": 1,                   # NEWS_SENTIMENT
    "get_global_news": 1,            # NEWS_SENTIMENT (no ticker)
    "get_insider_transactions": 1,   # INSIDER_TRANSACTIONS
    "get_market_movers": 1,          # TOP_GAINERS_LOSERS
    "get_market_indices": 1,         # multiple quote calls
    "get_sector_performance": 1,     # SECTOR
    "get_industry_performance": 1,   # sector ETF lookup
    "get_topic_news": 1,             # NEWS_SENTIMENT (topic filter)
}


@dataclass
class VendorEstimate:
    """Estimated API call counts per vendor for a single operation."""

    yfinance: int = 0
    alpha_vantage: int = 0
    finnhub: int = 0
    finviz: int = 0

    @property
    def total(self) -> int:
        return self.yfinance + self.alpha_vantage + self.finnhub + self.finviz


@dataclass
class UsageEstimate:
    """Full API usage estimate for a command."""

    command: str
    description: str
    vendor_calls: VendorEstimate = field(default_factory=VendorEstimate)
    # Breakdown of calls by method → count (only for non-zero vendors)
    method_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def av_fits_free_tier(self) -> bool:
        """Whether the Alpha Vantage calls fit within the free daily limit."""
        return self.vendor_calls.alpha_vantage <= AV_FREE_DAILY_LIMIT

    def av_daily_runs_free(self) -> int:
        """How many times this command can run per day on the free AV tier."""
        if self.vendor_calls.alpha_vantage == 0:
            return -1  # unlimited (doesn't use AV)
        return AV_FREE_DAILY_LIMIT // self.vendor_calls.alpha_vantage


# ──────────────────────────────────────────────────────────────────────────────
# Estimators for each command type
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_vendor(config: dict, method: str) -> str:
    """Determine which vendor a method will use given the config."""
    from tradingagents.dataflows.interface import (
        get_category_for_method,
    )

    if method == "get_gap_candidates":
        return "finviz"

    # Tool-level override first
    tool_vendors = config.get("tool_vendors", {})
    if method in tool_vendors:
        return tool_vendors[method]

    # Category-level
    try:
        category = get_category_for_method(method)
    except ValueError:
        # Method not in any category — may be a new/unknown method.
        # Return "unknown" so estimation can continue gracefully.
        import logging
        logging.getLogger(__name__).debug(
            "Method %r not found in TOOLS_CATEGORIES — skipping vendor resolution", method
        )
        return "unknown"
    return config.get("data_vendors", {}).get(category, "yfinance")


def estimate_analyze(
    config: dict | None = None,
    selected_analysts: list[str] | None = None,
    num_indicators: int = 6,
) -> UsageEstimate:
    """Estimate API calls for a single stock analysis.

    Args:
        config: TradingAgents config dict (uses DEFAULT_CONFIG if None).
        selected_analysts: Which analysts are enabled.
            Defaults to ``["market", "social", "news", "fundamentals"]``.
        num_indicators: Expected number of indicator calls from the market
            analyst (LLM decides, but 4-8 is typical).

    Returns:
        :class:`UsageEstimate` with per-vendor breakdowns.
    """
    if config is None:
        from tradingagents.default_config import DEFAULT_CONFIG
        config = DEFAULT_CONFIG

    if selected_analysts is None:
        selected_analysts = ["market", "social", "news", "fundamentals"]

    est = UsageEstimate(
        command="analyze",
        description="Single stock analysis",
    )

    breakdown: dict[str, dict[str, int]] = {}

    def _add(method: str, count: int = 1) -> None:
        vendor = _resolve_vendor(config, method)
        if vendor == "yfinance":
            est.vendor_calls.yfinance += count
        elif vendor == "alpha_vantage":
            est.vendor_calls.alpha_vantage += count
        elif vendor == "finnhub":
            est.vendor_calls.finnhub += count
        # Track breakdown
        if vendor not in breakdown:
            breakdown[vendor] = {}
        breakdown[vendor][method] = breakdown[vendor].get(method, 0) + count

    # Market Analyst
    if "market" in selected_analysts:
        _add("get_stock_data")
        for _ in range(num_indicators):
            _add("get_indicators")
        est.notes.append(
            f"Market analyst: 1 stock data + ~{num_indicators} indicator calls "
            f"(LLM chooses which indicators; actual count may vary)"
        )

    # Fundamentals Analyst
    if "fundamentals" in selected_analysts:
        _add("get_fundamentals")
        _add("get_income_statement")
        _add("get_balance_sheet")
        _add("get_cashflow")
        _add("get_insider_transactions")
        est.notes.append(
            "Fundamentals analyst: overview + 3 financial statements + insider transactions"
        )

    # News Analyst
    if "news" in selected_analysts:
        _add("get_news")
        _add("get_global_news")
        est.notes.append("News analyst: ticker news + global news")

    # Social Media Analyst (uses same news tools)
    if "social" in selected_analysts:
        _add("get_news")
        est.notes.append("Social analyst: ticker news/sentiment")

    est.method_breakdown = breakdown
    return est


def estimate_scan(config: dict | None = None) -> UsageEstimate:
    """Estimate API calls for a market-wide scan.

    Args:
        config: TradingAgents config dict (uses DEFAULT_CONFIG if None).

    Returns:
        :class:`UsageEstimate` with per-vendor breakdowns.
    """
    if config is None:
        from tradingagents.default_config import DEFAULT_CONFIG
        config = DEFAULT_CONFIG

    est = UsageEstimate(
        command="scan",
        description="Market-wide macro scan (3 phases)",
    )
    breakdown: dict[str, dict[str, int]] = {}

    def _add(method: str, count: int = 1) -> None:
        vendor = _resolve_vendor(config, method)
        if vendor == "yfinance":
            est.vendor_calls.yfinance += count
        elif vendor == "alpha_vantage":
            est.vendor_calls.alpha_vantage += count
        elif vendor == "finnhub":
            est.vendor_calls.finnhub += count
        elif vendor == "finviz":
            est.vendor_calls.finviz += count
        if vendor not in breakdown:
            breakdown[vendor] = {}
        breakdown[vendor][method] = breakdown[vendor].get(method, 0) + count

    # Phase 1A: Geopolitical Scanner — ~4 topic news calls
    topic_news_calls = 4
    for _ in range(topic_news_calls):
        _add("get_topic_news")
    est.notes.append(f"Phase 1A (Geopolitical): ~{topic_news_calls} topic news calls")

    # Phase 1B: Gatekeeper universe — 1 bounded yfinance query
    _add("get_gatekeeper_universe")
    est.notes.append("Phase 1B (Gatekeeper): 1 bounded yfinance universe query")

    # Phase 1C: Market regime scanner — 1 indices call
    _add("get_market_indices")
    est.notes.append("Phase 1C (Market Regime): 1 indices call")

    # Phase 1D: Sector Scanner — 1 sector performance
    _add("get_sector_performance")
    est.notes.append("Phase 1D (Sector): 1 sector performance call")

    # Phase 1E: Factor Alignment — bounded global revision/sentiment checks
    _add("get_topic_news", 2)
    _add("get_earnings_calendar")
    est.notes.append("Phase 1E (Factor Alignment): ~2 topic news + 1 earnings calendar")

    # Phase 1F: Drift Scanner — bounded gap subset + continuation checks
    _add("get_gap_candidates")
    _add("get_topic_news")
    _add("get_earnings_calendar")
    est.notes.append("Phase 1F (Drift): 1 Finviz gap scan + ~1 topic news + 1 earnings calendar")

    # Phase 2: Industry Deep Dive — ~3 industry perf + ~3 topic news
    industry_calls = 3
    _add("get_industry_performance", industry_calls)
    _add("get_topic_news", industry_calls)
    est.notes.append(
        f"Phase 2 (Industry Deep Dive): ~{industry_calls} industry perf + "
        f"~{industry_calls} topic news calls"
    )

    # Phase 3: Macro Synthesis — pure LLM reasoning, no external tools
    est.notes.append("Phase 3 (Macro Synthesis): no external tool calls")

    est.method_breakdown = breakdown
    return est


def estimate_pipeline(
    config: dict | None = None,
    num_tickers: int = 5,
    selected_analysts: list[str] | None = None,
    num_indicators: int = 6,
) -> UsageEstimate:
    """Estimate API calls for a full pipeline (scan → filter → analyze).

    Args:
        config: TradingAgents config dict.
        num_tickers: Expected number of tickers after filtering (typically 3-7).
        selected_analysts: Analysts for each ticker analysis.
        num_indicators: Expected indicator calls per ticker.

    Returns:
        :class:`UsageEstimate` with per-vendor breakdowns.
    """
    scan_est = estimate_scan(config)
    analyze_est = estimate_analyze(config, selected_analysts, num_indicators)

    est = UsageEstimate(
        command="pipeline",
        description=f"Full pipeline: scan + {num_tickers} ticker analyses",
    )

    # Scan phase
    est.vendor_calls.yfinance += scan_est.vendor_calls.yfinance
    est.vendor_calls.alpha_vantage += scan_est.vendor_calls.alpha_vantage
    est.vendor_calls.finnhub += scan_est.vendor_calls.finnhub
    est.vendor_calls.finviz += scan_est.vendor_calls.finviz

    # Analyze phase × num_tickers
    est.vendor_calls.yfinance += analyze_est.vendor_calls.yfinance * num_tickers
    est.vendor_calls.alpha_vantage += analyze_est.vendor_calls.alpha_vantage * num_tickers
    est.vendor_calls.finnhub += analyze_est.vendor_calls.finnhub * num_tickers
    est.vendor_calls.finviz += analyze_est.vendor_calls.finviz * num_tickers

    # Merge breakdowns
    merged: dict[str, dict[str, int]] = {}
    for vendor, methods in scan_est.method_breakdown.items():
        merged.setdefault(vendor, {})
        for method, count in methods.items():
            merged[vendor][method] = merged[vendor].get(method, 0) + count
    for vendor, methods in analyze_est.method_breakdown.items():
        merged.setdefault(vendor, {})
        for method, count in methods.items():
            merged[vendor][method] = merged[vendor].get(method, 0) + count * num_tickers
    est.method_breakdown = merged

    est.notes.append(f"Scan phase: {scan_est.vendor_calls.total} calls")
    est.notes.append(
        f"Analyze phase: {analyze_est.vendor_calls.total} calls × {num_tickers} tickers "
        f"= {analyze_est.vendor_calls.total * num_tickers} calls"
    )

    return est


# ──────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────────────

def format_estimate(est: UsageEstimate) -> str:
    """Format an estimate as a human-readable multi-line string."""
    lines = [
        f"API Usage Estimate — {est.command}",
        f"  {est.description}",
        "",
        f"  Vendor calls (estimated):",
    ]

    vc = est.vendor_calls
    if vc.yfinance:
        lines.append(f"    yfinance:      {vc.yfinance:>4} calls  (free, no key needed)")
    if vc.alpha_vantage:
        lines.append(f"    Alpha Vantage:  {vc.alpha_vantage:>3} calls  (free tier: {AV_FREE_DAILY_LIMIT}/day)")
    if vc.finnhub:
        lines.append(f"    Finnhub:        {vc.finnhub:>3} calls  (free tier: 60/min)")
    if vc.finviz:
        lines.append(f"    Finviz:         {vc.finviz:>3} calls  (HTML scrape, bounded use)")
    lines.append(f"    Total:         {vc.total:>4} vendor API calls")

    # Alpha Vantage assessment
    if vc.alpha_vantage > 0:
        lines.append("")
        lines.append("  Alpha Vantage Assessment:")
        if est.av_fits_free_tier():
            daily_runs = est.av_daily_runs_free()
            lines.append(
                f"    ✓ Fits FREE tier ({vc.alpha_vantage}/{AV_FREE_DAILY_LIMIT} daily calls). "
                f"~{daily_runs} run(s)/day possible."
            )
        else:
            lines.append(
                f"    ✗ Exceeds FREE tier ({vc.alpha_vantage} calls > {AV_FREE_DAILY_LIMIT}/day limit). "
                f"Premium required ($30/month → {AV_PREMIUM_PER_MINUTE}/min)."
            )
    else:
        lines.append("")
        lines.append(
            "  Alpha Vantage Assessment:"
        )
        lines.append(
            "    ✓ No Alpha Vantage calls — AV subscription NOT needed with current config."
        )

    return "\n".join(lines)


def format_vendor_breakdown(summary: dict) -> str:
    """Format a RunLogger summary dict into a per-vendor breakdown string.

    This is called *after* a run completes, using the actual (not estimated)
    vendor call counts from ``RunLogger.summary()``.
    """
    vendors_used = summary.get("vendors_used", {})
    if not vendors_used:
        return ""

    parts: list[str] = []
    for vendor in ("yfinance", "alpha_vantage", "finnhub", "finviz"):
        counts = vendors_used.get(vendor)
        if counts:
            ok = counts.get("ok", 0)
            fail = counts.get("fail", 0)
            label = {
                "yfinance": "yfinance",
                "alpha_vantage": "AV",
                "finnhub": "Finnhub",
                "finviz": "Finviz",
            }.get(vendor, vendor)
            parts.append(f"{label}:{ok}ok/{fail}fail")

    return " | ".join(parts) if parts else ""


def format_av_assessment(summary: dict) -> str:
    """Return a one-line Alpha Vantage assessment from actual run data."""
    vendors_used = summary.get("vendors_used", {})
    av = vendors_used.get("alpha_vantage")
    if not av:
        return "AV: not used (no subscription needed with current config)"

    av_total = av.get("ok", 0) + av.get("fail", 0)
    if av_total <= AV_FREE_DAILY_LIMIT:
        daily_runs = AV_FREE_DAILY_LIMIT // max(av_total, 1)
        return (
            f"AV: {av_total} calls — fits free tier "
            f"({AV_FREE_DAILY_LIMIT}/day, ~{daily_runs} runs/day)"
        )
    return (
        f"AV: {av_total} calls — exceeds free tier! "
        f"Premium needed ($30/mo → {AV_PREMIUM_PER_MINUTE}/min)"
    )
