"""AgentFeed crypto-derivatives vendor.

Adds perpetual-futures context to a crypto run for the coin under analysis. Two
sources stand behind it:

- Hyperliquid perps: price, funding, open interest, whale tilt and the largest
  positions.
- AgentFeed's cross-venue liquidation tape: last-hour liquidation sums and their
  z-score, the nearest liquidation clusters around price, and the 15-minute
  liquidation-cascade model.

Prices, news and social posts say what a coin did; this says how the market is
positioned in it.

AgentFeed (https://x402.ochinimus.app) is a paid API. A prepaid key from
https://x402.ochinimus.app/keys is read from ``AGENTFEED_API_KEY`` and each call
draws from its balance. Without the key the tool is not offered at all (see
``is_configured``), so a run is exactly as it was; called anyway, the vendor
raises ``AgentFeedNotConfiguredError`` and nothing is sent.

AgentFeed serves the current state only, with no historical vintage, so a run
dated before today is told so and no request is made.
"""
import logging
import os

import requests

from tradingagents import __version__
from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

AGENTFEED_BASE = "https://x402.ochinimus.app"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 30

# Identifies the caller, as the SEC EDGAR and Reddit clients do.
_UA = f"TradingAgents/{__version__} (+https://github.com/TauricResearch/TradingAgents)"


class AgentFeedNotConfiguredError(VendorNotConfiguredError):
    """Raised when AgentFeed is selected but no API key is configured."""


def is_configured() -> bool:
    """Whether an AgentFeed key is set, so a call would be sent."""
    return bool(os.getenv("AGENTFEED_API_KEY"))


def get_api_key() -> str:
    """Retrieve the AgentFeed API key from the environment."""
    api_key = os.getenv("AGENTFEED_API_KEY")
    if not api_key:
        raise AgentFeedNotConfiguredError("AGENTFEED_API_KEY is not set.")
    return api_key


def _request(coin: str) -> dict:
    """GET the coin's signal, with every failure raised as VendorUnavailableError.

    The key travels in a header, never in the URL, and no message built here
    quotes the request or the response headers. The error is raised outside the
    ``except`` block with nothing chained, so no traceback carries the request.
    """
    api_key = get_api_key()
    try:
        response = requests.get(
            f"{AGENTFEED_BASE}/api/coin-signal/{coin}",
            headers={"X-AgentFeed-Key": api_key, "User-Agent": _UA, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            # AgentFeed wraps every answer as {"tool": ..., "data": {...}, "paid": ...}.
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, dict):
                return data
            message = f"AgentFeed answered {coin} without a data object"
        else:
            message = f"AgentFeed answered HTTP {response.status_code} for {coin}{_reason(response)}"
    except requests.exceptions.JSONDecodeError:
        message = f"AgentFeed answered {coin} with a body that is not JSON"
    except requests.Timeout:
        message = f"AgentFeed timed out after {REQUEST_TIMEOUT}s for {coin}"
    except requests.RequestException as exc:
        message = f"AgentFeed could not be reached for {coin} ({type(exc).__name__})"
    raise VendorUnavailableError(message.replace(api_key, "***"))


def _reason(response) -> str:
    """The short reason AgentFeed gives in an error body, if any."""
    try:
        message = response.json().get("error")
    except (ValueError, AttributeError):
        return ""
    return f": {str(message)[:160]}" if message else ""


def _usd(value) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    value = abs(value)
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= size:
            return f"{sign}${value / size:.2f}{unit}"
    return f"{sign}${value:,.0f}"


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _num(value) -> str:
    return "n/a" if value is None else f"{value:g}"


def _px(value) -> str:
    return "n/a" if value is None else f"{value:,.6g}"


def _cluster(label: str, cluster: dict | None) -> str:
    if not cluster:
        return f"{label}: none holding 10% of the last 24 h of liquidations"
    return (
        f"{label}: {_px(cluster.get('price_low'))}-{_px(cluster.get('price_high'))}, "
        f"{_usd(cluster.get('usd'))}, {_pct(cluster.get('distance_pct'))} from mark"
    )


def _render(data: dict) -> str:
    coin = data.get("coin", "?")
    flags = ", ".join(data.get("flags") or []) or "none"
    tilt = data.get("whale_tilt")
    tilt_str = "n/a" if tilt is None else f"{tilt:+.2f} (net {_usd(data.get('whale_net_usd'))})"
    whales = "; ".join(
        f"{w.get('side')} {_usd(w.get('size_usd'))} entry {_px(w.get('entry_px'))} "
        f"liq {_px(w.get('liquidation_px'))}"
        for w in data.get("whale_top") or []
    ) or "none"
    cascade = data.get("cascade_15m") or {}
    if cascade.get("p") is not None:
        cascade_str = f"{cascade['p']:.1%}"
        if cascade.get("threshold_usd"):
            cascade_str += f" (of over {_usd(cascade['threshold_usd'])} liquidated)"
    else:
        cascade_str = f"unavailable ({cascade.get('reason') or 'no forecast'})"
    as_of = ", ".join(
        f"{name} {(src or {}).get('as_of') or 'n/a'}"
        for name, src in (data.get("sources") or {}).items()
    )

    return (
        f"## Crypto derivatives: {coin} perpetual, as of {data.get('as_of', 'n/a')}\n"
        f"Current perpetual-futures positioning, not a forecast; OI rank {data.get('oi_rank', 'n/a')} "
        f"on Hyperliquid.\n"
        f"- Mark {_px(data.get('mark'))}; 1h {_pct(data.get('chg_1h_pct'))}, "
        f"24h {_pct(data.get('chg_24h_pct'))}\n"
        f"- Funding {_pct(data.get('funding_ann_pct'))} annualized\n"
        f"- Open interest {_usd(data.get('oi_usd'))}; 1h {_pct(data.get('oi_chg_1h_pct'))}, "
        f"24h {_pct(data.get('oi_chg_24h_pct'))}\n"
        f"- Liquidations last hour: longs {_usd(data.get('liq_1h_long_usd'))}, "
        f"shorts {_usd(data.get('liq_1h_short_usd'))}; z-score {_num(data.get('liq_z'))} "
        f"against the coin's last 7 days\n"
        f"- Flags: {flags}\n"
        f"- Whale tilt (top 250 Hyperliquid accounts, -1 all short to +1 all long): {tilt_str}\n"
        f"- {_cluster('Liquidation cluster above', data.get('liq_cluster_above'))}\n"
        f"- {_cluster('Liquidation cluster below', data.get('liq_cluster_below'))}\n"
        f"- Largest positions: {whales}\n"
        f"- 15-minute liquidation cascade probability: {cascade_str}\n"
        f"Source: AgentFeed (x402.ochinimus.app): Hyperliquid perps for price, funding, open "
        f"interest and positions; AgentFeed's cross-venue liquidation tape for liquidations, "
        f"clusters and the cascade model.\n"
        f"Inputs as of: {as_of}\n"
    )


def get_crypto_derivatives(symbol: str, curr_date: str | None = None) -> str:
    """Return perpetual-futures context for a crypto symbol as a compact report.

    Args:
        symbol: The instrument under analysis, e.g. ``BTC-USD``, ``BTCUSD`` or
            ``BTC-USDT``. A symbol that is not a known crypto pair gets a
            not-applicable notice and no request is made.
        curr_date: The analysis date. AgentFeed serves only the current state,
            so a date before today withholds it and no request is made.

    Returns:
        A short markdown block: funding, open interest, liquidations, flags,
        whale positioning, liquidation clusters and the cascade probability.
    """
    coin = crypto_base(symbol)
    if coin is None:
        return (
            f"Crypto derivatives data does not apply to {symbol}: it covers the "
            f"perpetual futures of crypto pairs such as BTC-USD only."
        )
    if is_historical(curr_date):
        return (
            f"Crypto derivatives data is withheld for {curr_date}. AgentFeed serves "
            f"only the current state of the {coin} perpetual, with no historical "
            f"vintage, so serving it would put post-decision information into a "
            f"{curr_date} analysis."
        )
    return _render(_request(coin))
