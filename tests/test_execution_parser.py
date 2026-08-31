"""Parser tests for rating, prices, horizon, and cash-percent sizing."""

from __future__ import annotations

from tradingagents.execution.parser import extract_cash_allocation_pct, parse_trade_decision

PM_BUY = """
**Rating**: Buy

**Executive Summary**: Enter NVDA around 120 with a stop at 110. Allocate 50% of available cash. Hold 3-6 months.

**Investment Thesis**: Strong setup.

**Price Target**: 150

**Time Horizon**: 3-6 months
"""

TRADER_FALLBACK = """
**Action**: Buy

**Reasoning**: Setup looks clean.

**Entry Price**: 118.5

**Stop Loss**: 108

**Position Sizing**: 25% of available cash

FINAL TRANSACTION PROPOSAL: **BUY**
"""


class TestParseTradeDecision:
    def test_buy_rating_entry_stop_horizon(self):
        decision = parse_trade_decision(PM_BUY)
        assert decision.rating == "Buy"
        assert decision.action == "buy"
        assert decision.entry_price == 120
        assert decision.stop_loss == 110
        assert decision.price_target == 150
        assert decision.time_horizon == "3-6 months"
        assert decision.cash_allocation_pct == 50

    def test_overweight_maps_to_buy(self):
        decision = parse_trade_decision("**Rating**: Overweight\n\n**Executive Summary**: Add.")
        assert decision.action == "buy"

    def test_underweight_maps_to_sell(self):
        decision = parse_trade_decision("**Rating**: Underweight\n\n**Executive Summary**: Trim.")
        assert decision.action == "sell"

    def test_hold_is_default_for_unparseable(self):
        decision = parse_trade_decision("No rating here.")
        assert decision.action == "hold"

    def test_trader_price_and_sizing_fallback(self):
        pm = "**Rating**: Buy\n\n**Executive Summary**: Go."
        decision = parse_trade_decision(pm, TRADER_FALLBACK)
        assert decision.entry_price == 118.5
        assert decision.stop_loss == 108
        assert decision.cash_allocation_pct == 25
        assert decision.price_source == "trader_fallback"


class TestCashPercent:
    def test_prefers_available_cash_language(self):
        text = "Use 40% of available cash, not 15% of the portfolio."
        assert extract_cash_allocation_pct(text) == 40

    def test_position_sizing_line(self):
        text = "**Position Sizing**: 10% of cash"
        assert extract_cash_allocation_pct(text) == 10

    def test_rejects_out_of_range(self):
        assert extract_cash_allocation_pct("Allocate 0% of cash") is None
        assert extract_cash_allocation_pct("Allocate 150% of cash") is None
