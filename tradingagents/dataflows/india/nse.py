"""Best-effort NSE public data interfaces.

These functions intentionally return explicit unavailable messages until a
public endpoint is verified in this environment. Do not replace these with
fragile scraping that violates terms or rate limits.
"""

from __future__ import annotations

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.india.quality import unavailable_response
from tradingagents.dataflows.india.symbols import validate_india_symbol_or_raise


def _symbol(symbol: str) -> str:
    return validate_india_symbol_or_raise(symbol, get_config())


def get_nse_corporate_announcements(symbol: str, start_date: str, end_date: str) -> str:
    return unavailable_response("NSE", _symbol(symbol), "NSE announcements source is not verified for automated access in this environment.")


def get_nse_financial_results(symbol: str, start_date: str, end_date: str) -> str:
    return unavailable_response("NSE", _symbol(symbol), "NSE financial results source is not verified for automated access in this environment.")


def get_nse_shareholding_pattern(symbol: str) -> str:
    return unavailable_response("NSE", _symbol(symbol), "NSE shareholding pattern source is not verified for automated access in this environment.")


def get_nse_corporate_actions(symbol: str) -> str:
    return unavailable_response("NSE", _symbol(symbol), "NSE corporate actions source is not verified for automated access in this environment.")


def get_nse_option_chain(symbol_or_index: str) -> str:
    return unavailable_response("NSE", _symbol(symbol_or_index), "NSE option-chain source is not verified for automated access in this environment.")


def get_nse_daily_reports(date: str) -> str:
    return unavailable_response("NSE", "NSE_DAILY_REPORTS", f"NSE daily reports for {date} are not wired to a verified public endpoint.")


def get_nse_fii_dii_flows(date_range: str) -> str:
    return unavailable_response("NSE", "FII_DII", f"FII/DII flows for {date_range} are unavailable from a verified endpoint.")
