"""Alpha Vantage ``vwma``: declared but unimplemented.

The ``supported_indicators`` table declared ``vwma``, but the dispatch below
had no branch for it, so every ``vwma`` request fell to the generic
``NoMarketDataError`` — the message then claimed "Alpha Vantage does not serve
vwma; it serves [vwma, ...]", contradicting itself, and the capability table
advertised an endpoint Alpha Vantage does not actually offer (their technical
indicator API has no VWMA function).

These tests pin the corrected contract: ``vwma`` is no longer declared, and a
request for it raises ``NoMarketDataError`` so the router can fall back to a
vendor that computes it (yfinance does).
"""

import pytest

import tradingagents.dataflows.vendors.alpha_vantage.indicator as avi
from tradingagents.dataflows.errors import NoMarketDataError


@pytest.mark.unit
def test_vwma_not_declared_supported():
    """The capability table must not advertise what dispatch can't serve."""
    import inspect

    src = inspect.getsource(avi.get_indicator)
    assert '"vwma"' not in src, (
        "vwma is declared in supported_indicators but no dispatch branch "
        "implements it (Alpha Vantage has no VWMA endpoint)"
    )


@pytest.mark.unit
def test_vwma_request_raises_no_market_data():
    """vwma must raise NoMarketDataError so the router tries the next vendor."""
    with pytest.raises(NoMarketDataError) as exc_info:
        avi.get_indicator("AAPL", "vwma", "2025-06-10", 30)
    msg = str(exc_info.value)
    # Honest message: states it's not served; must not list vwma among served
    assert "vwma" in msg
    assert "it serves" in msg
    assert '"vwma"' not in msg.split("it serves")[-1], (
        "error message listed vwma among the served indicators — self-contradicting"
    )
