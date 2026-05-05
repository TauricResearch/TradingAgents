import inspect

import tradingagents.agents.trader.trader as trader_module


def test_trader_prompt_contains_volatility_sanity_check():
    src = inspect.getsource(trader_module)
    assert "VOLATILITY & STOP-LOSS SANITY CHECK" in src
    assert "ANTI-AIR-POCKET RULE" in src
    assert "structural" in src
