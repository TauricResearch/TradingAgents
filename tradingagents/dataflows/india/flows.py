"""India flows and positioning interfaces."""

from __future__ import annotations

from tradingagents.dataflows.india.quality import unavailable_response


def get_fii_dii_cash_flows(date_range: str) -> str:
    return unavailable_response("India flows", "FII_DII", f"FII/DII cash flows for {date_range} are not available from a verified offline-safe source.")


def get_index_breadth(curr_date: str) -> str:
    return unavailable_response("India flows", "INDEX_BREADTH", f"Index breadth for {curr_date} is not available from a verified offline-safe source.")


def get_india_vix(curr_date: str) -> str:
    return unavailable_response("India flows", "INDIA_VIX", f"India VIX for {curr_date} is not available from a verified offline-safe source.")


def get_fno_oi_summary(curr_date: str) -> str:
    return unavailable_response("India flows", "FNO_OI", f"F&O open-interest summary for {curr_date} is not available from a verified offline-safe source.")
