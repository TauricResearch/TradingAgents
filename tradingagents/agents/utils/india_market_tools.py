"""LangChain tools for IndiaMarketAgents."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.india.bse import (
    get_bse_corporate_actions,
    get_bse_corporate_announcements,
    get_bse_results,
    get_bse_shareholding,
)
from tradingagents.dataflows.india.filings import get_local_filing_notes as read_local_filing_notes
from tradingagents.dataflows.india.flows import (
    get_fii_dii_cash_flows,
    get_fno_oi_summary,
    get_index_breadth,
    get_india_vix,
)
from tradingagents.dataflows.india.macro import get_india_macro_context as read_india_macro_context
from tradingagents.dataflows.india.nse import (
    get_nse_corporate_actions,
    get_nse_corporate_announcements,
    get_nse_financial_results,
    get_nse_shareholding_pattern,
)
from tradingagents.dataflows.india.quality import unavailable_response
from tradingagents.dataflows.india.sector_context import render_sector_context
from tradingagents.dataflows.india.yfinance_india import (
    get_india_fundamentals as read_india_fundamentals,
    get_india_indicator,
    get_india_stock_data as read_india_stock_data,
)


def _guarded(source: str, symbol: str, func, *args, **kwargs) -> str:
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - tool output should be friendly.
        return unavailable_response(source, symbol, str(exc))


@tool
def get_india_stock_data(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve India stock OHLCV data with India ticker validation."""
    return _guarded("india_yfinance", symbol, read_india_stock_data, symbol, start_date, end_date)


@tool
def get_india_technical_snapshot(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve India OHLCV plus common technical indicators."""
    parts = [
        "# India Technical Snapshot",
        get_india_stock_data.func(symbol, start_date, end_date),
    ]
    for indicator in ("close_20_sma", "close_50_sma", "close_200_sma", "rsi", "macd", "boll", "atr"):
        parts.append(_guarded("india_yfinance", symbol, get_india_indicator, symbol, indicator, end_date, 90))
    return "\n\n".join(parts)


@tool
def get_india_fundamentals(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve India-aware fundamentals via the configured yfinance wrapper."""
    return _guarded("india_yfinance", symbol, read_india_fundamentals, symbol, curr_date)


@tool
def get_india_financial_results(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve official financial results when verified sources are available."""
    return "\n\n".join(
        [
            get_nse_financial_results(symbol, curr_date, curr_date),
            get_bse_results(symbol),
        ]
    )


@tool
def get_india_shareholding_pattern(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
) -> str:
    """Retrieve promoter/FII/DII/public shareholding data when available."""
    return "\n\n".join(
        [
            get_nse_shareholding_pattern(symbol),
            get_bse_shareholding(symbol),
        ]
    )


@tool
def get_india_corporate_announcements(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve NSE/BSE corporate announcements when verified sources are available."""
    return "\n\n".join(
        [
            get_nse_corporate_announcements(symbol, start_date, end_date),
            get_bse_corporate_announcements(symbol, start_date, end_date),
        ]
    )


@tool
def get_india_corporate_actions(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve NSE/BSE corporate actions when verified sources are available."""
    return "\n\n".join(
        [
            get_nse_corporate_actions(symbol),
            get_bse_corporate_actions(symbol),
        ]
    )


@tool
def get_india_macro_context(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Days to look back"] = 7,
) -> str:
    """Return India macro and policy context with data-quality notes."""
    return read_india_macro_context(curr_date, look_back_days)


@tool
def get_india_flows_context(
    curr_date: Annotated[str, "Current analysis date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Days to look back"] = 7,
) -> str:
    """Return India flows and positioning context with explicit data gaps."""
    date_range = f"{look_back_days} days ending {curr_date}"
    return "\n\n".join(
        [
            get_fii_dii_cash_flows(date_range),
            get_index_breadth(curr_date),
            get_india_vix(curr_date),
            get_fno_oi_summary(curr_date),
        ]
    )


@tool
def get_india_sector_context(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
    sector: Annotated[str | None, "Optional sector name"] = None,
) -> str:
    """Return an India-specific sector checklist."""
    return render_sector_context(symbol, sector)


@tool
def get_local_filing_notes(
    symbol: Annotated[str, "NSE/BSE ticker such as RELIANCE.NS"],
) -> str:
    """Read user-supplied local filing notes for an India ticker."""
    return _guarded("local_filings", symbol, read_local_filing_notes, symbol)
