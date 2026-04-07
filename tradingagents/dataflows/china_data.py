"""
china_data vendor for TradingAgents dataflows.

NOTE: This stub exists because the actual china_data implementation (akshare-based)
lives in web_dashboard/backend/china_data.py, not here. The tradingagents package
does not currently ship with a china_data vendor implementation.

To use china_data functionality, run analysis through the web dashboard where
akshare is available as a data source.
"""
from typing import Optional

def __getattr__(name: str):
    # Return None for all china_data imports so interface.py can handle them gracefully
    return None

