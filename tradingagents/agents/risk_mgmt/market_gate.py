"""Pre-trade market state verification gate.

Checks whether the target exchange is open before the Portfolio Manager
approves a trade. Uses the Headless Oracle free demo endpoint — no API
key or account required.

Resolves: https://github.com/TauricResearch/TradingAgents/issues/514
"""

import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# Map common ticker suffixes to ISO 10383 Market Identifier Codes.
# Tickers without a suffix are assumed to be US equities (XNYS).
SUFFIX_TO_MIC = {
    "": "XNYS",       # US equities (default)
    ".TO": "XNYS",    # TMX — route through NYSE hours as proxy
    ".L": "XLON",     # London Stock Exchange
    ".HK": "XHKG",    # Hong Kong
    ".T": "XJPX",     # Tokyo
    ".PA": "XPAR",    # Euronext Paris
    ".SI": "XSES",    # Singapore
    ".AX": "XASX",    # Australia
    ".BO": "XBOM",    # BSE India
    ".NS": "XNSE",    # NSE India
    ".SS": "XSHG",    # Shanghai
    ".SZ": "XSHE",    # Shenzhen
    ".KS": "XKRX",    # Korea
    ".JO": "XJSE",    # Johannesburg
    ".SA": "XBSP",    # B3 Brazil
    ".SW": "XSWX",    # SIX Swiss
    ".MI": "XMIL",    # Borsa Italiana
    ".IS": "XIST",    # Borsa Istanbul
    ".SR": "XSAU",    # Saudi Exchange
    ".NZ": "XNZE",    # New Zealand
    ".HE": "XHEL",    # Nasdaq Helsinki
    ".ST": "XSTO",    # Nasdaq Stockholm
}

ORACLE_URL = "https://headlessoracle.com/v5/demo"


def _ticker_to_mic(ticker: str) -> str:
    """Derive the exchange MIC from a ticker's suffix."""
    upper = ticker.upper()
    for suffix, mic in SUFFIX_TO_MIC.items():
        if suffix and upper.endswith(suffix):
            return mic
    # No suffix -> US equity
    return "XNYS"


def check_market_state(ticker: str, timeout: int = 10) -> dict:
    """Fetch a signed market-state receipt for the ticker's exchange.

    Returns a dict with at least:
        status   - "OPEN", "CLOSED", "HALTED", or "UNKNOWN"
        mic      - the exchange MIC that was checked
        blocked  - True if the trade should not proceed
        reason   - human-readable explanation (empty string when OPEN)

    On network failure the status defaults to "UNKNOWN" (fail-closed).
    """
    mic = _ticker_to_mic(ticker)
    url = f"{ORACLE_URL}?mic={mic}"

    try:
        req = Request(url, headers={"User-Agent": "TradingAgents/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except (URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Market gate: oracle unreachable (%s), defaulting to UNKNOWN", exc)
        data = {"status": "UNKNOWN", "mic": mic}

    status = data.get("status", "UNKNOWN")
    blocked = status != "OPEN"
    reason = "" if not blocked else f"BLOCK TRADE — market {mic} is {status}"

    return {
        "status": status,
        "mic": mic,
        "blocked": blocked,
        "reason": reason,
    }


def create_market_gate():
    """Create a graph node that gates trade execution on market state.

    When the market is not OPEN, the node injects a blocking advisory into
    the risk debate history so the Portfolio Manager sees it before deciding.
    """

    def market_gate_node(state) -> dict:
        ticker = state["company_of_interest"]
        result = check_market_state(ticker)

        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")

        if result["blocked"]:
            advisory = (
                f"\n\n[MARKET GATE] {result['reason']}. "
                f"Exchange {result['mic']} status is {result['status']}. "
                "Do NOT approve execution — the market is not open for trading."
            )
            logger.info("Market gate blocked trade: %s", result["reason"])
        else:
            advisory = (
                f"\n\n[MARKET GATE] Exchange {result['mic']} is OPEN. "
                "Market state verified — safe to proceed with execution."
            )

        new_risk_debate_state = {
            **risk_debate_state,
            "history": history + advisory,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return market_gate_node
