import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Set

# Known PERMANENTLY delisted tickers (verified mergers, bankruptcies, delistings)
# NOTE: This list should only contain tickers that are CONFIRMED to be permanently delisted.
PERMANENTLY_DELISTED = {
    "ABMD",  # Acquired by Johnson & Johnson (2022)
    "ATVI",  # Acquired by Microsoft (2023)
    "WWE",  # Merged with UFC to form TKO Group Holdings
    "ANTM",  # Anthem rebranded to Elevance Health (ELV)
    # Unit tickers (SPACs before merger, ending in U)
    "SUMAU",
    "LTGRU",
    "CMIIU",
    "XSLLU",
    "RIKU",
    "OTAIU",
    "LEGOU",
    "GIXXU",
    "SVIVU",
}


# Priority and strategy enums for consistent labeling.
class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Strategy(str, Enum):
    MOMENTUM = "momentum"
    UNDISCOVERED_DD = "undiscovered_dd"
    PRE_EARNINGS_ACCUMULATION = "pre_earnings_accumulation"
    EARLY_ACCUMULATION = "early_accumulation"
    ANALYST_UPGRADE = "analyst_upgrade"
    SHORT_SQUEEZE = "short_squeeze"
    NEWS_CATALYST = "news_catalyst"
    EARNINGS_PLAY = "earnings_play"
    IPO_OPPORTUNITY = "ipo_opportunity"
    CONTRARIAN_VALUE = "contrarian_value"
    MOMENTUM_CHASE = "momentum_chase"
    SOCIAL_HYPE = "social_hype"
    INSIDER_BUYING = "insider_buying"
    OPTIONS_FLOW = "options_flow"
    ML_SIGNAL = "ml_signal"
    SOCIAL_DD = "social_dd"
    SECTOR_ROTATION = "sector_rotation"
    TECHNICAL_BREAKOUT = "technical_breakout"
    MINERVINI = "minervini"


PRIORITY_ORDER = {
    Priority.CRITICAL.value: 0,
    Priority.HIGH.value: 1,
    Priority.MEDIUM.value: 2,
    Priority.LOW.value: 3,
    Priority.UNKNOWN.value: 4,
}


def serialize_for_log(value: Any) -> str:
    """Serialize values for logging without raising."""
    import json

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return repr(value)


def resolve_llm_name(llm: Any) -> str:
    """Best-effort model name resolution for LLM instances."""
    for attr in ("model_name", "model", "model_id", "name"):
        value = getattr(llm, attr, None)
        if value:
            return str(value)
    return llm.__class__.__name__


def build_llm_log_entry(
    *,
    node: str,
    step: str,
    model: str,
    prompt: Any,
    output: Any,
    error: str = "",
) -> Dict[str, Any]:
    """Build a structured LLM log entry."""
    from datetime import datetime

    prompt_str = serialize_for_log(prompt)
    output_str = serialize_for_log(output)
    return {
        "timestamp": datetime.now().isoformat(),
        "type": "llm",
        "node": node,
        "step": step,
        "model": model,
        "prompt": prompt_str,
        "prompt_length": len(prompt_str),
        "output": output_str,
        "output_length": len(output_str),
        "error": error,
    }


def append_llm_log(
    tool_logs: list,
    *,
    node: str,
    step: str,
    model: str,
    prompt: Any,
    output: Any,
    error: str = "",
) -> Dict[str, Any]:
    """Append an LLM log entry to the tool logs list."""
    entry = build_llm_log_entry(
        node=node, step=step, model=model, prompt=prompt, output=output, error=error
    )
    tool_logs.append(entry)
    return entry


def get_delisted_tickers() -> Set[str]:
    """Get combined list of delisted tickers from permanent list + dynamic cache."""
    # Local import to avoid circular dependencies if any
    from tradingagents.dataflows.delisted_cache import DelistedCache

    cache = DelistedCache()
    # Use very high thresholds for dynamic filtering to avoid false positives
    # Only include tickers that have failed 10+ times across 5+ unique days
    dynamic = set(
        ticker
        for ticker in cache.cache.keys()
        if cache.is_likely_delisted(ticker, fail_threshold=10, min_unique_days=5)
    )
    return PERMANENTLY_DELISTED | dynamic


def is_valid_ticker(ticker: str) -> bool:
    """
    Validate if a ticker is tradeable and not junk.

    Filters out:
    - Warrants (ending in W)
    - Units (ending in U)
    - Delisted/acquired companies
    - Invalid formats
    """
    if not ticker or not isinstance(ticker, str):
        return False

    ticker = ticker.upper().strip()

    # Must be 1-5 uppercase letters
    if not re.match(r"^[A-Z]{1,5}$", ticker):
        return False

    # Reject warrants (ending in W, but allow single letter W)
    if len(ticker) > 1 and ticker.endswith("W"):
        return False

    # Reject units (ending in U, but allow single letter U)
    if len(ticker) > 1 and ticker.endswith("U"):
        return False

    # Reject known delisted/acquired tickers
    delisted = get_delisted_tickers()
    if ticker in delisted:
        return False

    return True


def extract_technical_summary(technical_report: str) -> str:
    """Extract key technical signals from verbose indicator report for preliminary ranking."""
    if not technical_report:
        return ""

    signals = []

    # Extract RSI value (look for "Value:" pattern with optional markdown)
    rsi_match = re.search(
        r"RSI.*?\*{0,2}Value\*{0,2}[:\s]*(\d+\.?\d*)", technical_report, re.IGNORECASE | re.DOTALL
    )
    if not rsi_match:
        # Fallback: look for RSI section with a decimal number
        rsi_match = re.search(r"RSI.*?(\d{2,3}\.\d)", technical_report, re.IGNORECASE | re.DOTALL)
    if not rsi_match:
        # Last fallback: any number > 20 near RSI (avoid matching period like "(14)")
        rsi_match = re.search(r"RSI[^0-9]*([2-9]\d\.?\d*)", technical_report, re.IGNORECASE)
    if rsi_match:
        rsi = float(rsi_match.group(1))
        if rsi > 70:
            signals.append(f"RSI:{rsi:.0f}(OB)")
        elif rsi < 30:
            signals.append(f"RSI:{rsi:.0f}(OS)")
        else:
            signals.append(f"RSI:{rsi:.0f}")

    return ", ".join(signals)


def resolve_trade_date(state: Dict[str, Any]) -> datetime:
    """Resolve trade date from state, falling back to now on missing/invalid values."""
    trade_date_str = state.get("trade_date")
    if trade_date_str:
        try:
            return datetime.strptime(trade_date_str, "%Y-%m-%d")
        except ValueError:
            pass
    return datetime.now()


def resolve_trade_date_str(state: Dict[str, Any]) -> str:
    """Resolve trade date as YYYY-MM-DD string."""
    return resolve_trade_date(state).strftime("%Y-%m-%d")
