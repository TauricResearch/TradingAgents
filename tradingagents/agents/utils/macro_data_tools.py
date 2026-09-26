from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_macro_indicators(
    indicator: Annotated[
        str,
        "Macro indicator: a friendly alias. Malaysia (Bank Negara): 'opr' "
        "(Overnight Policy Rate), 'usd_myr' (ringgit), 'malaysia_cpi', "
        "'malaysia_gdp', 'malaysia_10y'. US (FRED): 'cpi', 'core_pce', "
        "'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve', "
        "'real_gdp', 'vix'. A raw FRED series ID such as 'CPIAUCSL' also works.",
    ],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format; the end of the window"],
    look_back_days: Annotated[
        int | None, "Trailing window length in days; omit for a 1-year window"
    ] = None,
) -> str:
    """
    Retrieve a macroeconomic indicator time series: policy rates, exchange
    rates, inflation, labor, and growth. Malaysian series ('opr', 'usd_myr')
    come from Bank Negara Malaysia; US and global series come from FRED
    (Federal Reserve Economic Data). Returns the series title, units,
    frequency, the latest value, the change over the window, and a recent
    observation table. Uses the configured macro_data vendor.

    For a Bursa Malaysia (.KL) instrument, 'opr' is Malaysia's policy rate —
    'fed_funds_rate' is the US one and is not a substitute for it.

    Args:
        indicator (str): Friendly alias or raw FRED series ID
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Trailing window length; omit for a 1-year window

    Returns:
        str: A formatted markdown report of the macro series
    """
    return route_to_vendor("get_macro_indicators", indicator, curr_date, look_back_days)
