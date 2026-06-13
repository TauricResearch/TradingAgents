"""Best-effort BSE public data interfaces."""

from __future__ import annotations

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.india.quality import unavailable_response
from tradingagents.dataflows.india.symbols import validate_india_symbol_or_raise


def _symbol(symbol: str) -> str:
    return validate_india_symbol_or_raise(symbol, get_config())


def get_bse_corporate_announcements(symbol: str, start_date: str, end_date: str) -> str:
    return unavailable_response("BSE", _symbol(symbol), "BSE announcements source is not verified for automated access in this environment.")


def get_bse_results(symbol: str) -> str:
    return unavailable_response("BSE", _symbol(symbol), "BSE financial results source is not verified for automated access in this environment.")


def get_bse_shareholding(symbol: str) -> str:
    return unavailable_response("BSE", _symbol(symbol), "BSE shareholding source is not verified for automated access in this environment.")


def get_bse_corporate_actions(symbol: str) -> str:
    return unavailable_response("BSE", _symbol(symbol), "BSE corporate actions source is not verified for automated access in this environment.")
