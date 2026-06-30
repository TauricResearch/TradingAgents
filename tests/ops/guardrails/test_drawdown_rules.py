from decimal import Decimal
from unittest.mock import MagicMock
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.drawdown_rules import DailyDrawdownRule, WeeklyDrawdownRule


def _buy_ctx(equity: str) -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    b = MagicMock()
    b.get_equity.return_value = Decimal(equity)
    return RuleContext(order=o, broker=b, config=OpsConfig())


def _sell_ctx(equity: str) -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    b = MagicMock()
    b.get_equity.return_value = Decimal(equity)
    return RuleContext(order=o, broker=b, config=OpsConfig())


def test_daily_drawdown_allows_above_threshold():
    rule = DailyDrawdownRule(start_of_day_equity=lambda: Decimal("250"))
    assert rule.check(_buy_ctx("235")).allowed is True


def test_daily_drawdown_blocks_at_threshold():
    rule = DailyDrawdownRule(start_of_day_equity=lambda: Decimal("250"))
    assert rule.check(_buy_ctx("232.50")).allowed is False


def test_daily_drawdown_does_not_block_sells():
    rule = DailyDrawdownRule(start_of_day_equity=lambda: Decimal("250"))
    assert rule.check(_sell_ctx("200")).allowed is True


def test_weekly_drawdown_allows_above_threshold():
    rule = WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("250"))
    assert rule.check(_buy_ctx("225")).allowed is True


def test_weekly_drawdown_blocks_at_threshold():
    rule = WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("250"))
    assert rule.check(_buy_ctx("212.50")).allowed is False


def test_weekly_drawdown_blocks_sells_too():
    rule = WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("250"))
    assert rule.check(_sell_ctx("200")).allowed is True
