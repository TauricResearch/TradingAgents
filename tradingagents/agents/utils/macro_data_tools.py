from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_macro_indicators(
    indicator: Annotated[
        str,
        "Macro indicator: a supported friendly alias such as 'cpi', 'core_cpi', "
        "'core_pce', 'unemployment', 'fed_funds_rate', '10y_treasury', "
        "'yield_curve', 'real_gdp', 'gdp', 'industrial_production', 'payrolls', "
        "'initial_claims', 'm2', 'vix', 'dollar_index', 'consumer_sentiment', "
        "'housing_starts', 'retail_sales', or a raw FRED series ID such as "
        "'CPIAUCSL'. Avoid descriptive names like 'bank of japan rate'.",
    ],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format; the end of the window"],
    look_back_days: Annotated[
        int | None, "Trailing window length in days; omit for a 1-year window"
    ] = None,
) -> str:
    """
    Retrieve a macroeconomic indicator time series from FRED (Federal Reserve
    Economic Data): policy rates, Treasury yields, inflation, labor, and growth.
    Returns the series title, units, frequency, the latest value, the change
    over the window, and a recent observation table. Uses the configured
    macro_data vendor.

    Args:
        indicator (str): Friendly alias or raw FRED series ID
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Trailing window length; omit for a 1-year window

    Returns:
        str: A formatted markdown report of the macro series
    """
    return route_to_vendor("get_macro_indicators", indicator, curr_date, look_back_days)
