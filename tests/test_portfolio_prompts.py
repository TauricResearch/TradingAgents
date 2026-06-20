import unittest

import pytest

from tradingagents.portfolio.models import Holding, Portfolio, Transaction
from tradingagents.portfolio.prompts import (
    _build_transactions_text,
    _format_money,
    build_market_prompt,
    build_pm_prompt,
    build_risk_prompt,
    build_trader_prompt,
)


@pytest.mark.unit
class FormatMoneyTests(unittest.TestCase):
    def test_none(self):
        self.assertEqual(_format_money(None), "N/A")

    def test_yi(self):
        result = _format_money(1_500_000_000)
        self.assertIn("亿", result)
        self.assertIn("15.00", result)

    def test_wan(self):
        result = _format_money(50_000)
        self.assertIn("万", result)
        self.assertIn("5.00", result)

    def test_yuan(self):
        result = _format_money(1234.56)
        self.assertNotIn("亿", result)
        self.assertNotIn("万", result)


@pytest.mark.unit
class BuildTransactionsTextTests(unittest.TestCase):
    def test_empty_when_no_matching_transactions(self):
        result = _build_transactions_text("AAPL", [])
        self.assertEqual(result, "")

    def test_formats_transactions(self):
        txs = [
            Transaction(date="2026-06-01", ticker="AAPL", action="买入", shares=100, price=150.0),
            Transaction(date="2026-06-15", ticker="AAPL", action="卖出", shares=50, price=160.0, fee=5.0),
        ]
        result = _build_transactions_text("AAPL", txs)
        self.assertIn("买入", result)
        self.assertIn("卖出", result)
        self.assertIn("150.000", result)

    def test_tag_and_fee_appear(self):
        txs = [
            Transaction(
                date="2026-06-01", ticker="AAPL", action="买入", shares=100, price=150.0,
                fee=5.0, tag="手动建仓",
            ),
        ]
        result = _build_transactions_text("AAPL", txs)
        self.assertIn("手续费", result)
        self.assertIn("手动建仓", result)

    def test_summary_counts(self):
        txs = [
            Transaction(date="2026-06-01", ticker="AAPL", action="买入", shares=100, price=150.0),
            Transaction(date="2026-06-15", ticker="AAPL", action="卖出", shares=50, price=160.0),
            Transaction(date="2026-06-20", ticker="AAPL", action="分红", shares=0, price=0.0),
        ]
        result = _build_transactions_text("AAPL", txs)
        self.assertIn("买入 1 次，卖出 1 次", result)
        self.assertIn("分红 1 次", result)


@pytest.mark.unit
class BuildMpPrompt(unittest.TestCase):
    def test_empty_when_no_holding(self):
        assert build_pm_prompt("UNKNOWN", None) == ""
        assert build_pm_prompt("UNKNOWN", Portfolio()) == ""

    def test_includes_holding_details(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", name="Apple", shares=100, avg_cost=150.0),
        })
        result = build_pm_prompt("AAPL", p)
        self.assertIn("Apple", result)
        self.assertIn("100", result)
        self.assertIn("150.000", result)

    def test_includes_pnl_and_weight(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, market_price=165.0, pnl_pct=0.10, weight=0.25),
        })
        result = build_pm_prompt("AAPL", p)
        self.assertIn("165.000", result)
        self.assertIn("+10.00%", result)
        self.assertIn("25.00%", result)

    def test_includes_grid_strategy(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, grid_strategy="网格宽度: +3%/-3%"),
        })
        result = build_pm_prompt("AAPL", p)
        self.assertIn("网格宽度", result)


@pytest.mark.unit
class BuildRiskPromptExtended(unittest.TestCase):
    def test_empty_when_no_holding(self):
        assert build_risk_prompt("UNKNOWN", None) == ""

    def test_weight_below_threshold_no_warning(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, weight=0.10),
        })
        result = build_risk_prompt("AAPL", p)
        self.assertNotIn("集中持仓", result)

    def test_negative_pnl_below_threshold_no_warning(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, pnl_pct=-0.10),
        })
        result = build_risk_prompt("AAPL", p)
        self.assertNotIn("止损", result)

    def test_positive_pnl_has_sign(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, pnl_pct=0.05),
        })
        result = build_risk_prompt("AAPL", p)
        self.assertIn("+5.00%", result)


@pytest.mark.unit
class BuildTraderPromptExtended(unittest.TestCase):
    def test_empty_when_no_holding(self):
        assert build_trader_prompt("UNKNOWN", None) == ""

    def test_no_grid_no_price_gap(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0),
        })
        result = build_trader_prompt("AAPL", p)
        self.assertIn("100 股", result)
        self.assertIn("150.000", result)
        self.assertNotIn("网格策略:", result)  # footer always mentions 网格策略

    def test_price_gap_calculation(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, market_price=180.0),
        })
        result = build_trader_prompt("AAPL", p)
        self.assertIn("+20.00%", result)


@pytest.mark.unit
class BuildMarketPromptTests(unittest.TestCase):
    def test_empty_when_no_holding(self):
        assert build_market_prompt("UNKNOWN", None) == ""
        assert build_market_prompt("UNKNOWN", Portfolio()) == ""

    def test_shows_cost_and_price(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, market_price=165.0),
        })
        result = build_market_prompt("AAPL", p)
        self.assertIn("150.000", result)
        self.assertIn("165.000", result)

    def test_positive_gap_uses_support_language(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, market_price=165.0),
        })
        result = build_market_prompt("AAPL", p)
        self.assertIn("构成支撑", result)

    def test_negative_gap_uses_resistance_language(self):
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0, market_price=135.0),
        })
        result = build_market_prompt("AAPL", p)
        self.assertIn("压力位", result)


# =========================================================================
# Edge-case tests merged from test_remaining_coverage.py
# =========================================================================


@pytest.mark.unit
class PromptsEdgeCases(unittest.TestCase):
    """Lines 83, 117, 122, 147-148."""

    def test_pm_includes_invested_amount(self):
        """Line 83: invested_amount is not None -> shown."""
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0,
                            invested_amount=15000.0),
        })
        result = build_pm_prompt("AAPL", p)
        self.assertIn("投入本金", result)

    def test_risk_weight_above_threshold_shows_warning(self):
        """Line 117: weight > 0.15 shows concentration warning."""
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0,
                            weight=0.20),
        })
        result = build_risk_prompt("AAPL", p)
        self.assertIn("集中持仓", result)

    def test_risk_shows_deep_loss_warning(self):
        """Line 122: pnl_pct < -0.20 shows severe loss warning."""
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0,
                            pnl_pct=-0.25),
        })
        result = build_risk_prompt("AAPL", p)
        self.assertIn("亏损超过 20%", result)

    def test_trader_includes_grid_strategy_lines(self):
        """Lines 147-148: grid strategy adds two lines."""
        p = Portfolio(holdings={
            "AAPL": Holding(ticker="AAPL", shares=100, avg_cost=150.0,
                            grid_strategy="网格宽度: +3%/-3%"),
        })
        result = build_trader_prompt("AAPL", p)
        self.assertIn("网格策略: 网格宽度: +3%/-3%", result)
        self.assertIn("参考上述网格区间", result)


if __name__ == "__main__":
    unittest.main()
