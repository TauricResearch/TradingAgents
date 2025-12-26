"""Integration tests for Trade model (Issue #6: DB-5).

Tests for Trade model integration with:
- Portfolio model relationships
- CGT calculation workflows (FIFO matching)
- Multi-currency trade scenarios
- Trade lifecycle management
- Complex query scenarios
- Tax year reporting
- Position tracking

Follows TDD principles - tests written BEFORE implementation.
"""

import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


class TestTradePortfolioIntegration:
    """Integration tests for Trade-Portfolio relationships."""

    @pytest.mark.asyncio
    async def test_create_trade_for_portfolio(self, db_session, test_portfolio):
        """Should create trade linked to portfolio."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)
            await db_session.refresh(test_portfolio, ["trades"])

            # Verify both sides of relationship
            assert trade.portfolio_id == test_portfolio.id
            assert trade in test_portfolio.trades

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_with_multiple_trades(self, db_session, test_portfolio):
        """Should allow portfolio to have multiple trades."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trades_data = [
                ("AAPL", Decimal("100"), Decimal("150.00")),
                ("TSLA", Decimal("50"), Decimal("200.00")),
                ("GOOGL", Decimal("25"), Decimal("120.00")),
            ]

            for symbol, quantity, price in trades_data:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol=symbol,
                    side=TradeSide.BUY,
                    quantity=quantity,
                    price=price,
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                )
                db_session.add(trade)

            await db_session.commit()

            # Refresh and verify
            await db_session.refresh(test_portfolio, ["trades"])

            assert len(test_portfolio.trades) == 3

            symbols = {t.symbol for t in test_portfolio.trades}
            assert "AAPL" in symbols
            assert "TSLA" in symbols
            assert "GOOGL" in symbols

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trades_deleted_with_portfolio(self, db_session, test_user):
        """Should cascade delete trades when portfolio is deleted."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create a temporary portfolio
            portfolio = Portfolio(
                user_id=test_user.id,
                name="Temp Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.00"),
            )

            db_session.add(portfolio)
            await db_session.commit()
            await db_session.refresh(portfolio)

            # Create trades for portfolio
            trade1 = Trade(
                portfolio_id=portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            trade2 = Trade(
                portfolio_id=portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add_all([trade1, trade2])
            await db_session.commit()

            trade1_id = trade1.id
            trade2_id = trade2.id

            # Delete the portfolio
            await db_session.delete(portfolio)
            await db_session.commit()

            # Verify trades are deleted
            result = await db_session.execute(
                select(Trade).where(
                    Trade.id.in_([trade1_id, trade2_id])
                )
            )
            remaining = result.scalars().all()

            assert len(remaining) == 0

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_multiple_portfolios_separate_trades(self, db_session, test_user, another_user):
        """Should isolate trades between different portfolios."""
        try:
            from tradingagents.api.models.portfolio import Portfolio, PortfolioType
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create portfolios for different users
            portfolio1 = Portfolio(
                user_id=test_user.id,
                name="User 1 Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.00"),
            )

            portfolio2 = Portfolio(
                user_id=another_user.id,
                name="User 2 Portfolio",
                portfolio_type=PortfolioType.PAPER,
                initial_capital=Decimal("10000.00"),
            )

            db_session.add_all([portfolio1, portfolio2])
            await db_session.commit()

            # Create trades for each portfolio
            trade1 = Trade(
                portfolio_id=portfolio1.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            trade2 = Trade(
                portfolio_id=portfolio2.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("200"),
                price=Decimal("155.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add_all([trade1, trade2])
            await db_session.commit()

            # Query trades for each portfolio
            result1 = await db_session.execute(
                select(Trade).where(Trade.portfolio_id == portfolio1.id)
            )
            trades1 = result1.scalars().all()

            result2 = await db_session.execute(
                select(Trade).where(Trade.portfolio_id == portfolio2.id)
            )
            trades2 = result2.scalars().all()

            assert len(trades1) == 1
            assert len(trades2) == 1
            assert trades1[0].quantity == Decimal("100")
            assert trades2[0].quantity == Decimal("200")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeCGTEndToEnd:
    """Integration tests for full CGT calculation lifecycle."""

    @pytest.mark.asyncio
    async def test_simple_buy_sell_cgt_workflow(self, db_session, test_portfolio):
        """Should calculate CGT for simple buy-then-sell scenario."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Buy 100 shares @ $40
            acquisition = date(2023, 1, 15)
            buy_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("40.00"),
                total_value=Decimal("4000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(acquisition, datetime.min.time()),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
            )

            db_session.add(buy_trade)
            await db_session.commit()

            # Sell 100 shares @ $50 (200 days later, no CGT discount)
            sell_date = date(2023, 8, 3)
            holding_days = (sell_date - acquisition).days

            sell_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                total_value=Decimal("5000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
                holding_period_days=holding_days,
                cgt_discount_eligible=False,  # < 367 days
                cgt_gross_gain=Decimal("1000.00"),  # 100 * ($50 - $40)
                cgt_gross_loss=Decimal("0.00"),
                cgt_net_gain=Decimal("1000.00"),  # No discount
            )

            db_session.add(sell_trade)
            await db_session.commit()

            # Verify CGT calculation
            await db_session.refresh(sell_trade)

            assert sell_trade.holding_period_days == holding_days
            assert sell_trade.cgt_discount_eligible is False
            assert sell_trade.cgt_gross_gain == Decimal("1000.00")
            assert sell_trade.cgt_net_gain == Decimal("1000.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_long_term_hold_cgt_discount(self, db_session, test_portfolio):
        """Should apply 50% CGT discount for >367 day hold."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Buy 100 shares @ $40
            acquisition = date(2022, 1, 1)
            buy_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("40.00"),
                total_value=Decimal("4000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(acquisition, datetime.min.time()),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
            )

            db_session.add(buy_trade)
            await db_session.commit()

            # Sell 100 shares @ $50 (400 days later, eligible for discount)
            sell_date = date(2023, 2, 5)
            holding_days = (sell_date - acquisition).days

            sell_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                total_value=Decimal("5000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
                holding_period_days=holding_days,
                cgt_discount_eligible=True,  # >= 367 days
                cgt_gross_gain=Decimal("1000.00"),  # 100 * ($50 - $40)
                cgt_gross_loss=Decimal("0.00"),
                cgt_net_gain=Decimal("500.00"),  # 50% discount applied
            )

            db_session.add(sell_trade)
            await db_session.commit()

            # Verify CGT discount applied
            await db_session.refresh(sell_trade)

            assert sell_trade.holding_period_days >= 367
            assert sell_trade.cgt_discount_eligible is True
            assert sell_trade.cgt_gross_gain == Decimal("1000.00")
            assert sell_trade.cgt_net_gain == Decimal("500.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_capital_loss_scenario(self, db_session, test_portfolio):
        """Should calculate capital loss correctly."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Buy 100 shares @ $50
            acquisition = date(2023, 3, 1)
            buy_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                total_value=Decimal("5000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(acquisition, datetime.min.time()),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("50.00"),
                cost_basis_total=Decimal("5000.00"),
            )

            db_session.add(buy_trade)
            await db_session.commit()

            # Sell 100 shares @ $30 (100 days later, loss)
            sell_date = date(2023, 6, 9)
            holding_days = (sell_date - acquisition).days

            sell_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("30.00"),
                total_value=Decimal("3000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("50.00"),
                cost_basis_total=Decimal("5000.00"),
                holding_period_days=holding_days,
                cgt_discount_eligible=False,
                cgt_gross_gain=Decimal("0.00"),
                cgt_gross_loss=Decimal("2000.00"),  # 100 * ($50 - $30)
                cgt_net_gain=Decimal("-2000.00"),
            )

            db_session.add(sell_trade)
            await db_session.commit()

            # Verify capital loss
            await db_session.refresh(sell_trade)

            assert sell_trade.cgt_gross_gain == Decimal("0.00")
            assert sell_trade.cgt_gross_loss == Decimal("2000.00")
            assert sell_trade.cgt_net_gain == Decimal("-2000.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeFIFOMatching:
    """Integration tests for FIFO parcel matching."""

    @pytest.mark.asyncio
    async def test_fifo_single_parcel_full_sale(self, db_session, test_portfolio):
        """Should match sell to single buy parcel (FIFO)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Single buy
            buy_date = date(2023, 1, 1)
            buy = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(buy_date, datetime.min.time()),
                acquisition_date=buy_date,
                cost_basis_per_unit=Decimal("100.00"),
                cost_basis_total=Decimal("10000.00"),
            )

            db_session.add(buy)
            await db_session.commit()

            # Sell entire position
            sell_date = date(2023, 6, 1)
            sell = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("120.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                acquisition_date=buy_date,  # Matched to first buy
                cost_basis_per_unit=Decimal("100.00"),
                cost_basis_total=Decimal("10000.00"),
                holding_period_days=(sell_date - buy_date).days,
                cgt_gross_gain=Decimal("2000.00"),
                cgt_net_gain=Decimal("2000.00"),
            )

            db_session.add(sell)
            await db_session.commit()

            # Verify FIFO matching
            await db_session.refresh(sell)

            assert sell.acquisition_date == buy_date
            assert sell.cost_basis_per_unit == Decimal("100.00")
            assert sell.cgt_gross_gain == Decimal("2000.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_fifo_multiple_parcels_oldest_first(self, db_session, test_portfolio):
        """Should match sell to oldest parcel first (FIFO)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # First buy (oldest)
            buy1_date = date(2023, 1, 1)
            buy1 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("40.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(buy1_date, datetime.min.time()),
                acquisition_date=buy1_date,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("2000.00"),
            )

            # Second buy (newer)
            buy2_date = date(2023, 3, 1)
            buy2 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("45.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(buy2_date, datetime.min.time()),
                acquisition_date=buy2_date,
                cost_basis_per_unit=Decimal("45.00"),
                cost_basis_total=Decimal("2250.00"),
            )

            db_session.add_all([buy1, buy2])
            await db_session.commit()

            # Sell 50 shares - should match to buy1 (FIFO)
            sell_date = date(2023, 6, 1)
            sell = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("50"),
                price=Decimal("50.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                acquisition_date=buy1_date,  # Matched to oldest buy
                cost_basis_per_unit=Decimal("40.00"),  # From buy1
                cost_basis_total=Decimal("2000.00"),
                holding_period_days=(sell_date - buy1_date).days,
                cgt_gross_gain=Decimal("500.00"),  # 50 * ($50 - $40)
                cgt_net_gain=Decimal("500.00"),
            )

            db_session.add(sell)
            await db_session.commit()

            # Verify matched to oldest parcel
            await db_session.refresh(sell)

            assert sell.acquisition_date == buy1_date
            assert sell.cost_basis_per_unit == Decimal("40.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_fifo_partial_parcel_matching(self, db_session, test_portfolio):
        """Should handle partial parcel matching across multiple buys."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Buy 100 @ $40
            buy1_date = date(2023, 1, 1)
            buy1 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("40.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(buy1_date, datetime.min.time()),
                acquisition_date=buy1_date,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
            )

            # Buy 100 @ $45
            buy2_date = date(2023, 2, 1)
            buy2 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("45.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(buy2_date, datetime.min.time()),
                acquisition_date=buy2_date,
                cost_basis_per_unit=Decimal("45.00"),
                cost_basis_total=Decimal("4500.00"),
            )

            db_session.add_all([buy1, buy2])
            await db_session.commit()

            # Sell 150 @ $50 - should consume all of buy1 + 50 from buy2
            sell_date = date(2023, 6, 1)

            # In real implementation, this might be split into 2 trade records
            # For this test, we'll use weighted average cost basis
            # 100 @ $40 + 50 @ $45 = $6250 / 150 = $41.67 avg

            sell = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.SELL,
                quantity=Decimal("150"),
                price=Decimal("50.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                acquisition_date=buy1_date,  # Earliest acquisition
                cost_basis_per_unit=Decimal("41.67"),  # Weighted average
                cost_basis_total=Decimal("6250.50"),
                holding_period_days=(sell_date - buy1_date).days,
                cgt_gross_gain=Decimal("1249.50"),  # 150*$50 - $6250.50
                cgt_net_gain=Decimal("1249.50"),
            )

            db_session.add(sell)
            await db_session.commit()

            # Verify FIFO matching
            await db_session.refresh(sell)

            assert sell.quantity == Decimal("150")
            assert sell.acquisition_date == buy1_date

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeMultiCurrency:
    """Integration tests for multi-currency trade scenarios."""

    @pytest.mark.asyncio
    async def test_foreign_stock_with_fx_conversion(self, db_session, test_portfolio):
        """Should handle foreign stock trades with FX conversion."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Buy US stock in USD
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),  # USD
                total_value=Decimal("15000.00"),  # USD
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                currency="USD",
                fx_rate_to_aud=Decimal("1.50"),  # 1 USD = 1.50 AUD
                total_value_aud=Decimal("22500.00"),  # AUD equivalent
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Verify currency conversion
            assert trade.currency == "USD"
            assert trade.total_value == Decimal("15000.00")
            assert trade.total_value_aud == Decimal("22500.00")
            assert trade.fx_rate_to_aud == Decimal("1.50")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_fx_gain_loss_in_cgt_calculation(self, db_session, test_portfolio):
        """Should account for FX gains/losses in CGT."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Buy @ 1.50 FX rate
            buy_date = date(2023, 1, 1)
            buy = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("100.00"),  # USD
                total_value=Decimal("10000.00"),  # USD
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(buy_date, datetime.min.time()),
                currency="USD",
                fx_rate_to_aud=Decimal("1.50"),
                total_value_aud=Decimal("15000.00"),  # AUD
                acquisition_date=buy_date,
                cost_basis_per_unit=Decimal("150.00"),  # AUD per share
                cost_basis_total=Decimal("15000.00"),  # AUD
            )

            db_session.add(buy)
            await db_session.commit()

            # Sell @ 1.40 FX rate (AUD strengthened)
            sell_date = date(2023, 6, 1)
            sell = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("110.00"),  # USD
                total_value=Decimal("11000.00"),  # USD
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.combine(sell_date, datetime.min.time()),
                currency="USD",
                fx_rate_to_aud=Decimal("1.40"),
                total_value_aud=Decimal("15400.00"),  # AUD
                acquisition_date=buy_date,
                cost_basis_per_unit=Decimal("150.00"),  # AUD
                cost_basis_total=Decimal("15000.00"),  # AUD
                holding_period_days=(sell_date - buy_date).days,
                # Small gain in AUD despite USD price increase due to FX
                cgt_gross_gain=Decimal("400.00"),
                cgt_net_gain=Decimal("400.00"),
            )

            db_session.add(sell)
            await db_session.commit()

            # Verify FX impact on CGT
            await db_session.refresh(sell)

            assert sell.total_value_aud == Decimal("15400.00")
            assert sell.cgt_gross_gain == Decimal("400.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_mixed_currency_portfolio(self, db_session, test_portfolio):
        """Should support mixed currency trades in same portfolio."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # AUD trade
            aud_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("45.00"),
                total_value=Decimal("4500.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                currency="AUD",
                fx_rate_to_aud=Decimal("1.0"),
                total_value_aud=Decimal("4500.00"),
            )

            # USD trade
            usd_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                total_value=Decimal("15000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                currency="USD",
                fx_rate_to_aud=Decimal("1.50"),
                total_value_aud=Decimal("22500.00"),
            )

            db_session.add_all([aud_trade, usd_trade])
            await db_session.commit()

            # Calculate total portfolio value in AUD
            result = await db_session.execute(
                select(func.sum(Trade.total_value_aud)).where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.side == TradeSide.BUY,
                        Trade.status == TradeStatus.FILLED
                    )
                )
            )
            total_aud = result.scalar()

            assert total_aud == Decimal("27000.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeComplexQueries:
    """Integration tests for complex trade queries."""

    @pytest.mark.asyncio
    async def test_aggregate_position_by_symbol(self, db_session, test_portfolio):
        """Should calculate current position for a symbol."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Multiple buys and sells for AAPL
            trades = [
                (TradeSide.BUY, Decimal("100")),
                (TradeSide.BUY, Decimal("50")),
                (TradeSide.SELL, Decimal("30")),
                (TradeSide.BUY, Decimal("20")),
            ]

            for side, quantity in trades:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side=side,
                    quantity=quantity,
                    price=Decimal("150.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                )
                db_session.add(trade)

            await db_session.commit()

            # Calculate net position (buys - sells) using case() from sqlalchemy
            from sqlalchemy import case
            result = await db_session.execute(
                select(
                    func.sum(
                        case(
                            (Trade.side == TradeSide.BUY, Trade.quantity),
                            else_=-Trade.quantity
                        )
                    )
                ).where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.symbol == "AAPL",
                        Trade.status == TradeStatus.FILLED
                    )
                )
            )
            net_position = result.scalar()

            # 100 + 50 - 30 + 20 = 140
            assert net_position == Decimal("140")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_trades_by_tax_year(self, db_session, test_portfolio):
        """Should filter trades by Australian tax year."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # FY2024 trades (July 2023 - June 2024)
            fy2024_dates = [
                datetime(2023, 7, 1),
                datetime(2023, 12, 15),
                datetime(2024, 6, 30),
            ]

            # FY2025 trade
            fy2025_date = datetime(2024, 7, 1)

            for exec_date in fy2024_dates:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side=TradeSide.BUY,
                    quantity=Decimal("100"),
                    price=Decimal("150.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=exec_date,
                )
                db_session.add(trade)

            trade_fy2025 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=fy2025_date,
            )
            db_session.add(trade_fy2025)

            await db_session.commit()

            # Query FY2024 trades using tax_year property
            # Note: This requires the model to have a hybrid_property or similar
            # For now, we'll query by date range
            fy2024_start = datetime(2023, 7, 1)
            fy2024_end = datetime(2024, 6, 30, 23, 59, 59)

            result = await db_session.execute(
                select(Trade).where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.executed_at >= fy2024_start,
                        Trade.executed_at <= fy2024_end
                    )
                )
            )
            fy2024_trades = result.scalars().all()

            assert len(fy2024_trades) == 3

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_cgt_eligible_for_discount(self, db_session, test_portfolio):
        """Should filter trades eligible for CGT discount."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Short hold (no discount)
            short_hold = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                holding_period_days=200,
                cgt_discount_eligible=False,
            )

            # Long hold (eligible for discount)
            long_hold = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("45.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                holding_period_days=400,
                cgt_discount_eligible=True,
            )

            db_session.add_all([short_hold, long_hold])
            await db_session.commit()

            # Query eligible trades
            result = await db_session.execute(
                select(Trade).where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.cgt_discount_eligible == True
                    )
                )
            )
            eligible_trades = result.scalars().all()

            assert len(eligible_trades) == 1
            assert eligible_trades[0].symbol == "BHP.AX"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_calculate_total_cgt_for_year(self, db_session, test_portfolio):
        """Should calculate total CGT for tax year."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Multiple sales with CGT
            trades = [
                (Decimal("1000.00"), Decimal("500.00")),  # Gain with discount
                (Decimal("500.00"), Decimal("500.00")),   # Gain no discount
                (Decimal("0.00"), Decimal("-300.00")),    # Loss
            ]

            for gross_gain, net_gain in trades:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side=TradeSide.SELL,
                    quantity=Decimal("100"),
                    price=Decimal("150.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime(2024, 3, 15),
                    cgt_gross_gain=gross_gain,
                    cgt_net_gain=net_gain,
                )
                db_session.add(trade)

            await db_session.commit()

            # Calculate total net CGT
            result = await db_session.execute(
                select(func.sum(Trade.cgt_net_gain)).where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.side == TradeSide.SELL,
                        Trade.status == TradeStatus.FILLED
                    )
                )
            )
            total_cgt = result.scalar()

            # $500 + $500 - $300 = $700
            assert total_cgt == Decimal("700.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeLifecycle:
    """Integration tests for trade lifecycle management."""

    @pytest.mark.asyncio
    async def test_trade_status_progression(self, db_session, test_portfolio):
        """Should support trade status transitions."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create pending order
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.PENDING,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.PENDING

            # Partially fill
            trade.status = TradeStatus.PARTIAL
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.PARTIAL

            # Complete fill
            trade.status = TradeStatus.FILLED
            trade.executed_at = datetime.utcnow()
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.FILLED
            assert trade.executed_at is not None

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cancel_pending_order(self, db_session, test_portfolio):
        """Should support cancelling pending orders."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.PENDING,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Cancel order
            trade.status = TradeStatus.CANCELLED
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.CANCELLED
            assert trade.executed_at is None

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_reject_invalid_order(self, db_session, test_portfolio):
        """Should support rejecting invalid orders."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="INVALID",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("0.01"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.REJECTED,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.REJECTED
            assert trade.executed_at is None

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeReporting:
    """Integration tests for trade reporting scenarios."""

    @pytest.mark.asyncio
    async def test_portfolio_performance_report(self, db_session, test_portfolio):
        """Should generate portfolio performance metrics."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create trades with gains and losses
            trades = [
                (TradeSide.BUY, Decimal("100"), Decimal("40.00"), None, None),
                (TradeSide.SELL, Decimal("100"), Decimal("50.00"), Decimal("1000.00"), Decimal("1000.00")),
                (TradeSide.BUY, Decimal("50"), Decimal("60.00"), None, None),
                (TradeSide.SELL, Decimal("50"), Decimal("55.00"), Decimal("0.00"), Decimal("-250.00")),
            ]

            for side, quantity, price, gross_gain, net_gain in trades:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side=side,
                    quantity=quantity,
                    price=price,
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                    cgt_gross_gain=gross_gain or Decimal("0.00"),
                    cgt_net_gain=net_gain or Decimal("0.00"),
                )
                db_session.add(trade)

            await db_session.commit()

            # Calculate metrics
            result = await db_session.execute(
                select(
                    func.sum(Trade.cgt_gross_gain),
                    func.sum(Trade.cgt_net_gain),
                    func.count(Trade.id)
                ).where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.side == TradeSide.SELL
                    )
                )
            )
            gross_total, net_total, sell_count = result.one()

            assert gross_total == Decimal("1000.00")
            assert net_total == Decimal("750.00")  # 1000 - 250
            assert sell_count == 2

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_symbol_trading_history(self, db_session, test_portfolio):
        """Should retrieve complete trading history for a symbol."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create trading history for AAPL
            trade_dates = [
                datetime(2023, 1, 15),
                datetime(2023, 3, 20),
                datetime(2023, 6, 10),
                datetime(2023, 9, 5),
            ]

            for i, exec_date in enumerate(trade_dates):
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side=TradeSide.BUY if i % 2 == 0 else TradeSide.SELL,
                    quantity=Decimal("100"),
                    price=Decimal(f"{140 + i*10}.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=exec_date,
                )
                db_session.add(trade)

            await db_session.commit()

            # Query trading history ordered by date
            result = await db_session.execute(
                select(Trade)
                .where(
                    and_(
                        Trade.portfolio_id == test_portfolio.id,
                        Trade.symbol == "AAPL"
                    )
                )
                .order_by(Trade.executed_at.asc())
            )
            history = result.scalars().all()

            assert len(history) == 4
            assert history[0].executed_at == trade_dates[0]
            assert history[-1].executed_at == trade_dates[-1]

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")
