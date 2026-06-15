"""FRED (Federal Reserve Economic Data) macro vendor.

Fetches macroeconomic time series — policy rates, Treasury yields, inflation,
labor, growth — from the St. Louis Fed's free API. Used by the news analyst to
ground macro commentary in actual numbers rather than headlines alone.

A free API key (https://fred.stlouisfed.org/docs/api/api_key.html) is read from
``FRED_API_KEY``; if it is unset the vendor raises ``FredNotConfiguredError`` so
the routing layer treats it as "unavailable" rather than a hard crash.
"""
import logging
import os
import re
from datetime import datetime, timedelta

import requests

from .errors import VendorNotConfiguredError

logger = logging.getLogger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"

# Network timeout (seconds) so a stalled request can't hang the agents,
# mirroring the Alpha Vantage client.
REQUEST_TIMEOUT = 30

# Default trailing window when the caller does not specify one. A year captures
# the trend and the year-over-year base for most monthly/quarterly series.
DEFAULT_LOOKBACK_DAYS = 365

# Rows cap for the rendered table: recent values matter most for a decision, and
# daily series (yields, VIX) over a long window would otherwise flood context.
MAX_ROWS = 40

# FRED rejects series_id values longer than 25 alphanumeric characters.
MAX_FRED_SERIES_ID_LEN = 25

# Curated human-friendly aliases -> FRED series IDs. Anything not listed is used
# verbatim as a raw FRED series ID, so power users are never limited to this set.
MACRO_SERIES = {
    # Policy rate & Treasury yields
    "fed_funds_rate": "FEDFUNDS",
    "federal_funds_rate": "FEDFUNDS",
    "fed_funds": "FEDFUNDS",
    "2y_treasury": "DGS2",
    "10y_treasury": "DGS10",
    "30y_treasury": "DGS30",
    "10y_2y_spread": "T10Y2Y",
    "yield_curve": "T10Y2Y",
    # Inflation
    "cpi": "CPIAUCSL",
    "core_cpi": "CPILFESL",
    "pce": "PCEPI",
    "core_pce": "PCEPILFE",
    "inflation_expectations": "T10YIE",
    # Growth & output
    "real_gdp": "GDPC1",
    "gdp": "GDP",
    "industrial_production": "INDPRO",
    # Labor
    "unemployment_rate": "UNRATE",
    "unemployment": "UNRATE",
    "nonfarm_payrolls": "PAYEMS",
    "payrolls": "PAYEMS",
    "initial_claims": "ICSA",
    # Money & markets
    "m2": "M2SL",
    "money_supply": "M2SL",
    "vix": "VIXCLS",
    "dollar_index": "DTWEXBGS",
    # Sentiment & housing
    "consumer_sentiment": "UMCSENT",
    "housing_starts": "HOUST",
    "retail_sales": "RSAFS",
    # Common LLM paraphrases (not literal FRED IDs)
    "interest_rate": "FEDFUNDS",
    "policy_rate": "FEDFUNDS",
    "fed_rate": "FEDFUNDS",
    "inflation": "CPIAUCSL",
    "consumer_price_index": "CPIAUCSL",
    "price_index": "CPIAUCSL",
    "jobs": "PAYEMS",
    "jobless_claims": "ICSA",
    "claims": "ICSA",
    "bond_yield": "DGS10",
    "treasury_yield": "DGS10",
    "treasury": "DGS10",
    "recession": "T10Y2Y",
}

_KNOWN_ALIASES_HELP = ", ".join(sorted(MACRO_SERIES))

# Broad aliases that should lose to more specific indicators in fuzzy matching.
_GENERIC_ALIASES = frozenset({
    "inflation",
    "price_index",
    "interest_rate",
    "policy_rate",
    "fed_rate",
    "bond_yield",
    "treasury_yield",
    "treasury",
    "recession",
    "claims",
    "jobs",
})


class FredNotConfiguredError(VendorNotConfiguredError):
    """Raised when FRED is selected but no API key is configured.

    A VendorNotConfiguredError (and thus still a ValueError), so the routing
    layer's "vendor unavailable" handling and existing ValueError callers both
    keep working.
    """


def get_api_key() -> str:
    """Retrieve the FRED API key from the environment."""
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise FredNotConfiguredError(
            "FRED_API_KEY environment variable is not set. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html."
        )
    return api_key


def _normalize_indicator_key(indicator: str) -> str:
    """Collapse free-text / punctuation into a stable alias lookup key."""
    key = indicator.strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    return key.strip("_")


def _is_valid_fred_series_id(series_id: str) -> bool:
    return (
        bool(series_id)
        and len(series_id) <= MAX_FRED_SERIES_ID_LEN
        and series_id.isalnum()
    )


def _fuzzy_alias_lookup(key: str) -> str | None:
    """Best-effort alias match when the LLM paraphrases an indicator name."""
    if key in MACRO_SERIES:
        return MACRO_SERIES[key]
    # e.g. "us_core_pce_inflation" -> core_pce (prefer compound aliases over "inflation")
    contained = [alias for alias in MACRO_SERIES if alias in key]
    if contained:
        best = max(
            contained,
            key=lambda alias: (
                alias not in _GENERIC_ALIASES,
                alias.count("_"),
                len(alias),
            ),
        )
        return MACRO_SERIES[best]
    # e.g. "pce" -> pce (not core_pce when both match, prefer exact token)
    token_matches = [alias for alias in MACRO_SERIES if key == alias or key in alias.split("_")]
    if token_matches:
        return MACRO_SERIES[min(token_matches, key=len)]
    return None


def _resolve_series_id(indicator: str) -> str:
    """Map a friendly alias to a FRED series ID, or pass a raw ID through."""
    raw = indicator.strip()
    if not raw:
        return ""
    key = _normalize_indicator_key(raw)
    resolved = _fuzzy_alias_lookup(key)
    if resolved:
        return resolved
    # Pull embedded tokens such as "series CPIAUCSL" out of longer LLM strings.
    for token in sorted(re.findall(r"[A-Za-z0-9]{1,25}", raw), key=len, reverse=True):
        upper = token.upper()
        if _is_valid_fred_series_id(upper) and upper in MACRO_SERIES.values():
            return upper
    # Not a known alias: treat short inputs as raw FRED series IDs.
    return raw.upper()


def _invalid_indicator_response(indicator: str, series_id: str, reason: str) -> str:
    """Return a tool-visible message instead of crashing the research graph."""
    return (
        f"INVALID_FRED_INDICATOR: {reason}\n"
        f"- Requested: {indicator!r}\n"
        f"- Resolved series_id: {series_id!r}\n"
        f"- Supported aliases: {_KNOWN_ALIASES_HELP}\n"
        f"- Or pass a raw FRED series ID (≤{MAX_FRED_SERIES_ID_LEN} alphanumeric characters).\n"
        f"Pick a supported alias and do not retry the same invalid indicator."
    )


def _request(path: str, params: dict) -> dict:
    """GET a FRED endpoint, surfacing FRED's JSON error body on a bad request."""
    api_params = {**params, "api_key": get_api_key(), "file_type": "json"}
    response = requests.get(
        f"{FRED_API_BASE}/{path}", params=api_params, timeout=REQUEST_TIMEOUT
    )
    # FRED returns 400 with a JSON {"error_message": ...} for unknown series IDs
    # or malformed params; turn that into a clear, actionable error.
    if response.status_code == 400:
        try:
            message = response.json().get("error_message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"FRED request failed: {message}")
    response.raise_for_status()
    return response.json()


def get_macro_data(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Fetch a FRED macroeconomic series as a formatted markdown report.

    Args:
        indicator: A friendly alias (e.g. "cpi", "unemployment", "10y_treasury")
            or a raw FRED series ID (e.g. "CPIAUCSL", "DGS10").
        curr_date: End of the window (yyyy-mm-dd); no later observations are
            returned, so a past date never leaks future data.
        look_back_days: Trailing window length; ``None`` uses DEFAULT_LOOKBACK_DAYS.

    Returns:
        A markdown report with the series title, units, frequency, the latest
        value, the change over the window, and a recent observation table.
    """
    if look_back_days is None:
        look_back_days = DEFAULT_LOOKBACK_DAYS

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    series_id = _resolve_series_id(indicator)
    if not _is_valid_fred_series_id(series_id):
        return _invalid_indicator_response(
            indicator,
            series_id,
            "series_id must be at most 25 alphanumeric characters.",
        )

    try:
        meta = _request("series", {"series_id": series_id}).get("seriess") or []
    except ValueError as exc:
        # LLM-chosen indicators should degrade gracefully; only config/network
        # issues should bubble up and fail the whole research task.
        message = str(exc)
        if "series_id" in message.lower() or "fred request failed" in message.lower():
            return _invalid_indicator_response(indicator, series_id, message)
        raise

    if not meta:
        return _invalid_indicator_response(
            indicator,
            series_id,
            f"FRED series '{series_id}' not found.",
        )
    info = meta[0]
    title = info.get("title", series_id)
    units = info.get("units_short") or info.get("units", "")
    frequency = info.get("frequency", "")
    seasonal = info.get("seasonal_adjustment_short", "")

    observations = _request(
        "series/observations",
        {
            "series_id": series_id,
            "observation_start": start_date,
            "observation_end": curr_date,
            "sort_order": "asc",
        },
    ).get("observations", [])

    # FRED encodes a missing observation as ".".
    points = [
        (o["date"], o["value"])
        for o in observations
        if o.get("value") not in (".", None, "")
    ]

    header = (
        f"## FRED: {title} ({series_id})\n"
        f"- Units: {units}\n"
        f"- Frequency: {frequency}"
        f"{f' ({seasonal})' if seasonal else ''}\n"
        f"- Window: {start_date} to {curr_date}\n"
    )

    if not points:
        return header + (
            f"\nNo observations for {series_id} in this window. The series may "
            f"report less frequently than the window length; widen look_back_days."
        )

    first_date, first_val = points[0]
    last_date, last_val = points[-1]
    try:
        delta = float(last_val) - float(first_val)
        base = float(first_val)
        pct = f" ({delta / base * 100:+.2f}%)" if base != 0 else ""
        summary = (
            f"\n**Latest:** {last_val} ({last_date}) | "
            f"**Change over window:** {delta:+.2f}{pct} "
            f"from {first_val} ({first_date})\n"
        )
    except ValueError:
        summary = f"\n**Latest:** {last_val} ({last_date})\n"

    shown = points
    note = ""
    if len(points) > MAX_ROWS:
        shown = points[-MAX_ROWS:]
        note = f"\n_(showing the most recent {MAX_ROWS} of {len(points)} observations)_\n"

    table = (
        "\n| Date | Value |\n| --- | --- |\n"
        + "\n".join(f"| {d} | {v} |" for d, v in shown)
        + "\n"
    )

    return header + summary + note + table
