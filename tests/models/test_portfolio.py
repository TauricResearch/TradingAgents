from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from tradingagents.models.portfolio import (
    PortfolioConfig,
    PortfolioSnapshot,
    CashTransaction,
    TransactionType,
)
from tradingagents.models.trading import OrderSide, Fill, Position


class TestPortfolioConfig:
    def test_default_config(self):
        config = PortfolioConfig()
        assert config.initial_cash == Decimal("100000")
        assert config.commission_per_share == Decimal("0")
        assert config.slippage_percent == Decimal("0")

    def test_custom_config(self):
        config = PortfolioConfig(
            initial_cash=Decimal("50000"),
            commission_per_trade=Decimal("5.00"),
            slippage_percent=Decimal("0.1"),
        )
        assert config.initial_cash == Decimal("50000")
        assert config.commission_per_trade == Decimal("5.00")

    def test_calculate_commission_flat(self):
        config = PortfolioConfig(commission_per_trade=Decimal("5.00"))
        commission = config.calculate_commission(100, Decimal("150.00"))
        assert commission == Decimal("5.00")

    def test_calculate_commission_per_share(self):
        config = PortfolioConfig(commission_per_share=Decimal("0.01"))
        commission = config.calculate_commission(100, Decimal("150.00"))
        assert commission == Decimal("1.00")

    def test_calculate_commission_percent(self):
        config = PortfolioConfig(commission_percent=Decimal("0.1"))
        commission = config.calculate_commission(100, Decimal("100.00"))
        assert commission == Decimal("10.00")

    def test_calculate_commission_minimum(self):
        config = PortfolioConfig(
            commission_per_trade=Decimal("1.00"),
            min_commission=Decimal("5.00"),
        )
        commission = config.calculate_commission(10, Decimal("10.00"))
        assert commission == Decimal("5.00")

    def test_calculate_commission_maximum(self):
        config = PortfolioConfig(
            commission_percent=Decimal("1"),
            max_commission=Decimal("50.00"),
        )
        commission = config.calculate_commission(1000, Decimal("100.00"))
        assert commission == Decimal("50.00")

    def test_calculate_slippage_buy(self):
        config = PortfolioConfig(slippage_percent=Decimal("0.1"))
        price = config.calculate_slippage(Decimal("100.00"), OrderSide.BUY)
        assert price == Decimal("100.10")

    def test_calculate_slippage_sell(self):
        config = PortfolioConfig(slippage_percent=Decimal("0.1"))
        price = config.calculate_slippage(Decimal("100.00"), OrderSide.SELL)
        assert price == Decimal("99.90")


class TestPortfolioSnapshot:
    def test_new_portfolio(self):
        portfolio = PortfolioSnapshot(cash=Decimal("100000"))
        assert portfolio.cash == Decimal("100000")
        assert portfolio.position_count == 0
        assert len(portfolio.positions) == 0

    def test_get_position_creates_new(self):
        portfolio = PortfolioSnapshot(cash=Decimal("100000"))
        position = portfolio.get_position("AAPL")
        assert position.ticker == "AAPL"
        assert position.quantity == 0
        assert "AAPL" in portfolio.positions

    def test_positions_value(self):
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            positions={
                "AAPL": Position(ticker="AAPL", quantity=100, avg_cost=Decimal("150")),
                "GOOGL": Position(ticker="GOOGL", quantity=50, avg_cost=Decimal("100")),
            },
        )
        prices = {"AAPL": Decimal("160"), "GOOGL": Decimal("110")}
        assert portfolio.positions_value(prices) == Decimal("21500")

    def test_total_equity(self):
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            positions={
                "AAPL": Position(ticker="AAPL", quantity=100, avg_cost=Decimal("150")),
            },
        )
        prices = {"AAPL": Decimal("160")}
        assert portfolio.total_equity(prices) == Decimal("66000")

    def test_total_unrealized_pnl(self):
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            positions={
                "AAPL": Position(ticker="AAPL", quantity=100, avg_cost=Decimal("150")),
            },
        )
        prices = {"AAPL": Decimal("160")}
        assert portfolio.total_unrealized_pnl(prices) == Decimal("1000")

    def test_apply_buy_fill(self):
        portfolio = PortfolioSnapshot(cash=Decimal("100000"))
        fill = Fill(
            order_id=uuid4(),
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("5.00"),
        )
        portfolio.apply_fill(fill)
        assert portfolio.cash == Decimal("84995.00")
        assert portfolio.positions["AAPL"].quantity == 100
        assert portfolio.total_commission_paid == Decimal("5.00")

    def test_apply_sell_fill_with_profit(self):
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            positions={
                "AAPL": Position(ticker="AAPL", quantity=100, avg_cost=Decimal("150")),
            },
        )
        fill = Fill(
            order_id=uuid4(),
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            price=Decimal("160.00"),
            commission=Decimal("5.00"),
        )
        portfolio.apply_fill(fill)
        assert portfolio.cash == Decimal("65995.00")
        assert portfolio.positions["AAPL"].quantity == 0
        assert portfolio.total_realized_pnl == Decimal("1000.00")

    def test_add_deposit(self):
        portfolio = PortfolioSnapshot(cash=Decimal("100000"))
        transaction = CashTransaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("10000"),
        )
        portfolio.add_cash_transaction(transaction)
        assert portfolio.cash == Decimal("110000")
        assert len(portfolio.cash_transactions) == 1

    def test_add_withdrawal(self):
        portfolio = PortfolioSnapshot(cash=Decimal("100000"))
        transaction = CashTransaction(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=Decimal("10000"),
        )
        portfolio.add_cash_transaction(transaction)
        assert portfolio.cash == Decimal("90000")

    def test_can_afford(self):
        portfolio = PortfolioSnapshot(cash=Decimal("10000"))
        config = PortfolioConfig(commission_per_trade=Decimal("5"))

        assert portfolio.can_afford("AAPL", 10, Decimal("100"), config)
        assert not portfolio.can_afford("AAPL", 100, Decimal("100"), config)

    def test_max_shares_affordable(self):
        portfolio = PortfolioSnapshot(cash=Decimal("10000"))
        config = PortfolioConfig(commission_per_trade=Decimal("0"))

        max_shares = portfolio.max_shares_affordable("AAPL", Decimal("100"), config)
        assert max_shares == 100

    def test_max_shares_affordable_with_commission(self):
        portfolio = PortfolioSnapshot(cash=Decimal("10050"))
        config = PortfolioConfig(commission_per_trade=Decimal("50"))

        max_shares = portfolio.max_shares_affordable("AAPL", Decimal("100"), config)
        assert max_shares == 100

    def test_to_dict(self):
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            positions={
                "AAPL": Position(ticker="AAPL", quantity=100, avg_cost=Decimal("150")),
            },
        )
        prices = {"AAPL": Decimal("160")}
        result = portfolio.to_dict(prices)

        assert result["cash"] == 50000.0
        assert result["positions_value"] == 16000.0
        assert result["total_equity"] == 66000.0
        assert result["position_count"] == 1
