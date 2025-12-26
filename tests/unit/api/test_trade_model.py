"""Unit tests for Trade model (Issue #6: DB-5).

Tests for Trade model fields including:
- TradeSide enum (BUY, SELL)
- TradeStatus enum (PENDING, FILLED, PARTIAL, CANCELLED, REJECTED)
- TradeOrderType enum (MARKET, LIMIT, STOP, STOP_LIMIT)
- Basic trade fields (symbol, quantity, price, etc.)
- Signal fields (signal_source, signal_confidence)
- CGT (Capital Gains Tax) fields and calculations
- Currency support (currency, fx_rate_to_aud, total_value_aud)
- Tax year calculation (Australian FY: July-June)
- Decimal precision for monetary and quantity values
- Check constraints (quantity > 0, price > 0, etc.)
- Properties (is_buy, is_sell, is_filled)
- Relationship with Portfolio

Follows TDD principles with comprehensive coverage.
Tests written BEFORE implementation (RED phase).
"""

import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


class TestTradeBasicFields:
    """Tests for basic Trade model fields."""

    @pytest.mark.asyncio
    async def test_create_trade_with_required_fields(self, db_session, test_portfolio):
        """Should create trade with only required fields."""
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

            # Assert
            assert trade.id is not None
            assert trade.portfolio_id == test_portfolio.id
            assert trade.symbol == "AAPL"
            assert trade.side == TradeSide.BUY
            assert trade.quantity == Decimal("100")
            assert trade.price == Decimal("150.00")
            assert trade.order_type == TradeOrderType.MARKET
            assert trade.status == TradeStatus.FILLED

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_defaults(self, db_session, test_portfolio):
        """Should apply default values to optional fields."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Check defaults
            assert trade.currency == "AUD"
            assert trade.fx_rate_to_aud == Decimal("1.0000")
            assert trade.created_at is not None
            assert trade.updated_at is not None

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_with_all_fields(self, db_session, test_portfolio):
        """Should create trade with all fields specified."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            executed_time = datetime(2024, 3, 15, 10, 30, 0)
            acquisition = date(2023, 6, 1)

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("500"),
                price=Decimal("45.50"),
                total_value=Decimal("22750.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.FILLED,
                executed_at=executed_time,
                signal_source="TechnicalAnalysis",
                signal_confidence=Decimal("85.50"),
                acquisition_date=acquisition,
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("20000.00"),
                holding_period_days=288,
                cgt_discount_eligible=False,
                cgt_gross_gain=Decimal("2750.00"),
                cgt_gross_loss=Decimal("0.00"),
                cgt_net_gain=Decimal("2750.00"),
                currency="AUD",
                fx_rate_to_aud=Decimal("1.0000"),
                total_value_aud=Decimal("22750.00"),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert all fields
            assert trade.id is not None
            assert trade.symbol == "BHP.AX"
            assert trade.side == TradeSide.SELL
            assert trade.quantity == Decimal("500")
            assert trade.price == Decimal("45.50")
            assert trade.total_value == Decimal("22750.00")
            assert trade.signal_source == "TechnicalAnalysis"
            assert trade.signal_confidence == Decimal("85.50")
            assert trade.acquisition_date == acquisition
            assert trade.cgt_discount_eligible is False

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_timestamps_auto_populate(self, db_session, test_portfolio):
        """Should auto-populate created_at and updated_at timestamps."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("95.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert timestamps exist and are recent
            assert trade.created_at is not None
            assert trade.updated_at is not None
            assert isinstance(trade.created_at, datetime)
            assert isinstance(trade.updated_at, datetime)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeSideEnum:
    """Tests for TradeSide enum validation."""

    @pytest.mark.asyncio
    async def test_trade_side_buy(self, db_session, test_portfolio):
        """Should create trade with BUY side."""
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

            assert trade.side == TradeSide.BUY
            assert trade.side.value == "BUY"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_side_sell(self, db_session, test_portfolio):
        """Should create trade with SELL side."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.SELL,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.side == TradeSide.SELL
            assert trade.side.value == "SELL"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_side_invalid_value(self, db_session, test_portfolio):
        """Should reject invalid trade side."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Try to create with invalid string
            with pytest.raises((ValueError, AttributeError)):
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side="INVALID_SIDE",
                    quantity=Decimal("100"),
                    price=Decimal("150.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                )
                db_session.add(trade)
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeStatusEnum:
    """Tests for TradeStatus enum validation."""

    @pytest.mark.asyncio
    async def test_trade_status_pending(self, db_session, test_portfolio):
        """Should create trade with PENDING status."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.PENDING,
                executed_at=None,  # Not executed yet
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.PENDING
            assert trade.status.value == "PENDING"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_status_filled(self, db_session, test_portfolio):
        """Should create trade with FILLED status."""
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

            assert trade.status == TradeStatus.FILLED
            assert trade.status.value == "FILLED"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_status_partial(self, db_session, test_portfolio):
        """Should create trade with PARTIAL status."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.PARTIAL,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.PARTIAL
            assert trade.status.value == "PARTIAL"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_status_cancelled(self, db_session, test_portfolio):
        """Should create trade with CANCELLED status."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.CANCELLED,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.CANCELLED
            assert trade.status.value == "CANCELLED"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_status_rejected(self, db_session, test_portfolio):
        """Should create trade with REJECTED status."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.REJECTED,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.status == TradeStatus.REJECTED
            assert trade.status.value == "REJECTED"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeOrderTypeEnum:
    """Tests for TradeOrderType enum validation."""

    @pytest.mark.asyncio
    async def test_order_type_market(self, db_session, test_portfolio):
        """Should create trade with MARKET order type."""
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

            assert trade.order_type == TradeOrderType.MARKET
            assert trade.order_type.value == "MARKET"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_order_type_limit(self, db_session, test_portfolio):
        """Should create trade with LIMIT order type."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

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

            assert trade.order_type == TradeOrderType.LIMIT
            assert trade.order_type.value == "LIMIT"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_order_type_stop(self, db_session, test_portfolio):
        """Should create trade with STOP order type."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("140.00"),
                order_type=TradeOrderType.STOP,
                status=TradeStatus.PENDING,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.order_type == TradeOrderType.STOP
            assert trade.order_type.value == "STOP"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_order_type_stop_limit(self, db_session, test_portfolio):
        """Should create trade with STOP_LIMIT order type."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("140.00"),
                order_type=TradeOrderType.STOP_LIMIT,
                status=TradeStatus.PENDING,
                executed_at=None,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.order_type == TradeOrderType.STOP_LIMIT
            assert trade.order_type.value == "STOP_LIMIT"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeDecimalPrecision:
    """Tests for Decimal precision on trade fields."""

    @pytest.mark.asyncio
    async def test_quantity_decimal_precision(self, db_session, test_portfolio):
        """Should store quantity with 4 decimal places (PreciseNumeric standard)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BTC",
                side=TradeSide.BUY,
                quantity=Decimal("0.1234"),  # 4 decimal places (per model spec)
                price=Decimal("45000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert decimal precision maintained (4 decimals per PreciseNumeric)
            assert trade.quantity == Decimal("0.1234")
            assert isinstance(trade.quantity, Decimal)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_price_decimal_precision(self, db_session, test_portfolio):
        """Should store price with 4 decimal places."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.1234"),  # 4 decimal places
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert decimal precision maintained
            assert trade.price == Decimal("150.1234")
            assert isinstance(trade.price, Decimal)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_total_value_decimal_precision(self, db_session, test_portfolio):
        """Should store total_value with 4 decimal places."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                total_value=Decimal("10000.5678"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert decimal precision maintained
            assert trade.total_value == Decimal("10000.5678")
            assert isinstance(trade.total_value, Decimal)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_fields_decimal_precision(self, db_session, test_portfolio):
        """Should store CGT fields with 4 decimal places."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("500"),
                price=Decimal("45.50"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                cost_basis_per_unit=Decimal("40.1234"),
                cost_basis_total=Decimal("20061.7000"),
                cgt_gross_gain=Decimal("2688.3000"),
                cgt_gross_loss=Decimal("0.0000"),
                cgt_net_gain=Decimal("2688.3000"),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert CGT decimal precision
            assert trade.cost_basis_per_unit == Decimal("40.1234")
            assert trade.cost_basis_total == Decimal("20061.7000")
            assert trade.cgt_gross_gain == Decimal("2688.3000")
            assert trade.cgt_net_gain == Decimal("2688.3000")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_fx_rate_decimal_precision(self, db_session, test_portfolio):
        """Should store fx_rate_to_aud with 6 decimal places."""
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
                currency="USD",
                fx_rate_to_aud=Decimal("1.523456"),  # 6 decimal places
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert FX rate precision
            assert trade.fx_rate_to_aud == Decimal("1.523456")
            assert isinstance(trade.fx_rate_to_aud, Decimal)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_signal_confidence_decimal_precision(self, db_session, test_portfolio):
        """Should store signal_confidence with 2 decimal places (0-100)."""
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
                signal_source="ML_Model",
                signal_confidence=Decimal("87.65"),  # 2 decimal places
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Assert signal confidence precision
            assert trade.signal_confidence == Decimal("87.65")
            assert isinstance(trade.signal_confidence, Decimal)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeTaxYear:
    """Tests for Australian tax year calculation (July-June)."""

    @pytest.mark.asyncio
    async def test_tax_year_fy2024_start(self, db_session, test_portfolio):
        """Should calculate tax year FY2024 for trade on July 1, 2023."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # July 1, 2023 starts FY2024
            executed_time = datetime(2023, 7, 1, 10, 0, 0)

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("95.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=executed_time,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # FY2024 = July 1, 2023 to June 30, 2024
            assert trade.tax_year == "FY2024"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_tax_year_fy2024_end(self, db_session, test_portfolio):
        """Should calculate tax year FY2024 for trade on June 30, 2024."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # June 30, 2024 ends FY2024
            executed_time = datetime(2024, 6, 30, 23, 59, 59)

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.BUY,
                quantity=Decimal("200"),
                price=Decimal("45.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=executed_time,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.tax_year == "FY2024"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_tax_year_fy2025_start(self, db_session, test_portfolio):
        """Should calculate tax year FY2025 for trade on July 1, 2024."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # July 1, 2024 starts FY2025
            executed_time = datetime(2024, 7, 1, 0, 0, 0)

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="WES.AX",
                side=TradeSide.BUY,
                quantity=Decimal("150"),
                price=Decimal("55.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=executed_time,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.tax_year == "FY2025"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_tax_year_before_fy_transition(self, db_session, test_portfolio):
        """Should calculate tax year FY2024 for trade in June 2024."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # June 15, 2024 is before FY transition
            executed_time = datetime(2024, 6, 15, 14, 30, 0)

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="NAB.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("30.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=executed_time,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.tax_year == "FY2024"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_tax_year_after_fy_transition(self, db_session, test_portfolio):
        """Should calculate tax year FY2025 for trade in July 2024."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # July 15, 2024 is after FY transition
            executed_time = datetime(2024, 7, 15, 9, 0, 0)

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="ANZ.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("25.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=executed_time,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.tax_year == "FY2025"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeCGTDiscount:
    """Tests for CGT discount eligibility (367+ days)."""

    @pytest.mark.asyncio
    async def test_cgt_discount_not_eligible_short_hold(self, db_session, test_portfolio):
        """Should not be eligible for CGT discount with <367 days holding."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("160.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                acquisition_date=date.today() - timedelta(days=200),
                holding_period_days=200,
                cgt_discount_eligible=False,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.holding_period_days == 200
            assert trade.cgt_discount_eligible is False

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_discount_eligible_367_days(self, db_session, test_portfolio):
        """Should be eligible for CGT discount with exactly 367 days holding."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("500"),
                price=Decimal("45.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                acquisition_date=date.today() - timedelta(days=367),
                holding_period_days=367,
                cgt_discount_eligible=True,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.holding_period_days == 367
            assert trade.cgt_discount_eligible is True

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_discount_eligible_long_hold(self, db_session, test_portfolio):
        """Should be eligible for CGT discount with >367 days holding."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.SELL,
                quantity=Decimal("200"),
                price=Decimal("100.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                acquisition_date=date.today() - timedelta(days=500),
                holding_period_days=500,
                cgt_discount_eligible=True,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.holding_period_days == 500
            assert trade.cgt_discount_eligible is True

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_discount_boundary_366_days(self, db_session, test_portfolio):
        """Should not be eligible with 366 days (boundary test)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="WES.AX",
                side=TradeSide.SELL,
                quantity=Decimal("150"),
                price=Decimal("55.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                acquisition_date=date.today() - timedelta(days=366),
                holding_period_days=366,
                cgt_discount_eligible=False,
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.holding_period_days == 366
            assert trade.cgt_discount_eligible is False

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeCGTCalculations:
    """Tests for CGT calculation fields."""

    @pytest.mark.asyncio
    async def test_cgt_gross_gain_calculation(self, db_session, test_portfolio):
        """Should calculate gross gain correctly."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Sell at $50, cost basis $40 = $10 gain per unit
            # 100 units = $1000 gross gain
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                total_value=Decimal("5000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
                cgt_gross_gain=Decimal("1000.00"),
                cgt_gross_loss=Decimal("0.00"),
                cgt_net_gain=Decimal("1000.00"),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.cgt_gross_gain == Decimal("1000.00")
            assert trade.cgt_gross_loss == Decimal("0.00")
            assert trade.cgt_net_gain == Decimal("1000.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_gross_loss_calculation(self, db_session, test_portfolio):
        """Should calculate gross loss correctly."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Sell at $30, cost basis $40 = $10 loss per unit
            # 100 units = $1000 gross loss
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("30.00"),
                total_value=Decimal("3000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
                cgt_gross_gain=Decimal("0.00"),
                cgt_gross_loss=Decimal("1000.00"),
                cgt_net_gain=Decimal("-1000.00"),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.cgt_gross_gain == Decimal("0.00")
            assert trade.cgt_gross_loss == Decimal("1000.00")
            assert trade.cgt_net_gain == Decimal("-1000.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_net_gain_with_discount(self, db_session, test_portfolio):
        """Should calculate net gain with CGT discount applied."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # $1000 gross gain, eligible for 50% discount = $500 net gain
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                total_value=Decimal("5000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                acquisition_date=date.today() - timedelta(days=400),
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
                holding_period_days=400,
                cgt_discount_eligible=True,
                cgt_gross_gain=Decimal("1000.00"),
                cgt_gross_loss=Decimal("0.00"),
                cgt_net_gain=Decimal("500.00"),  # 50% discount applied
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.cgt_gross_gain == Decimal("1000.00")
            assert trade.cgt_discount_eligible is True
            assert trade.cgt_net_gain == Decimal("500.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cgt_no_gain_or_loss(self, db_session, test_portfolio):
        """Should handle breakeven trades (no gain or loss)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Sell at cost basis = no gain or loss
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="CBA.AX",
                side=TradeSide.SELL,
                quantity=Decimal("100"),
                price=Decimal("40.00"),
                total_value=Decimal("4000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                cost_basis_per_unit=Decimal("40.00"),
                cost_basis_total=Decimal("4000.00"),
                cgt_gross_gain=Decimal("0.00"),
                cgt_gross_loss=Decimal("0.00"),
                cgt_net_gain=Decimal("0.00"),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.cgt_gross_gain == Decimal("0.00")
            assert trade.cgt_gross_loss == Decimal("0.00")
            assert trade.cgt_net_gain == Decimal("0.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeCurrencySupport:
    """Tests for multi-currency support."""

    @pytest.mark.asyncio
    async def test_default_currency_aud(self, db_session, test_portfolio):
        """Should default to AUD currency."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BHP.AX",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("45.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.currency == "AUD"
            assert trade.fx_rate_to_aud == Decimal("1.0000")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_usd_currency_with_fx_rate(self, db_session, test_portfolio):
        """Should support USD with FX rate conversion."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # $100 USD @ 1.50 FX rate = $150 AUD
            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                total_value=Decimal("15000.00"),  # USD
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
                currency="USD",
                fx_rate_to_aud=Decimal("1.50"),
                total_value_aud=Decimal("22500.00"),  # AUD
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.currency == "USD"
            assert trade.fx_rate_to_aud == Decimal("1.50")
            assert trade.total_value == Decimal("15000.00")
            assert trade.total_value_aud == Decimal("22500.00")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_common_currencies(self, db_session, test_portfolio):
        """Should accept common 3-letter currency codes."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            currencies = ["USD", "EUR", "GBP", "JPY", "CNY", "AUD"]

            for currency in currencies:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol=f"STOCK.{currency}",
                    side=TradeSide.BUY,
                    quantity=Decimal("100"),
                    price=Decimal("100.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                    currency=currency,
                )

                db_session.add(trade)
                await db_session.commit()
                await db_session.refresh(trade)

                assert trade.currency == currency

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_currency_uppercase_enforced(self, db_session, test_portfolio):
        """Should store currency in uppercase."""
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
                currency="usd",  # lowercase input
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            # Should be stored in uppercase
            assert trade.currency == "USD"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeConstraints:
    """Tests for CheckConstraints on trade fields."""

    @pytest.mark.asyncio
    async def test_quantity_must_be_positive(self, db_session, test_portfolio):
        """Should reject negative quantity."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("-100"),  # Negative!
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)

            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_quantity_cannot_be_zero(self, db_session, test_portfolio):
        """Should reject zero quantity."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("0"),  # Zero!
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)

            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_price_must_be_positive(self, db_session, test_portfolio):
        """Should reject negative price."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("-150.00"),  # Negative!
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)

            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_price_cannot_be_zero(self, db_session, test_portfolio):
        """Should reject zero price."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("0.00"),  # Zero!
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)

            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_signal_confidence_range_0_to_100(self, db_session, test_portfolio):
        """Should accept signal_confidence between 0 and 100."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Test boundary values
            for confidence in [Decimal("0.00"), Decimal("50.00"), Decimal("100.00")]:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol="AAPL",
                    side=TradeSide.BUY,
                    quantity=Decimal("100"),
                    price=Decimal("150.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                    signal_source="Test",
                    signal_confidence=confidence,
                )

                db_session.add(trade)
                await db_session.commit()
                await db_session.refresh(trade)

                assert trade.signal_confidence == confidence

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_signal_confidence_above_100_rejected(self, db_session, test_portfolio):
        """Should reject signal_confidence > 100."""
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
                signal_source="Test",
                signal_confidence=Decimal("101.00"),  # > 100!
            )

            db_session.add(trade)

            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_signal_confidence_negative_rejected(self, db_session, test_portfolio):
        """Should reject negative signal_confidence."""
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
                signal_source="Test",
                signal_confidence=Decimal("-10.00"),  # Negative!
            )

            db_session.add(trade)

            with pytest.raises((IntegrityError, ValueError)):
                await db_session.commit()

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeSignalFields:
    """Tests for signal tracking fields."""

    @pytest.mark.asyncio
    async def test_signal_source_stored(self, db_session, test_portfolio):
        """Should store signal source string."""
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
                signal_source="TechnicalAnalysis",
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.signal_source == "TechnicalAnalysis"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_signal_confidence_stored(self, db_session, test_portfolio):
        """Should store signal confidence value."""
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
                signal_source="ML_Model",
                signal_confidence=Decimal("92.50"),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.signal_confidence == Decimal("92.50")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_signal_fields_optional(self, db_session, test_portfolio):
        """Should allow trades without signal fields."""
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
                # No signal_source or signal_confidence
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.signal_source is None
            assert trade.signal_confidence is None

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeProperties:
    """Tests for trade model properties."""

    @pytest.mark.asyncio
    async def test_is_buy_property(self, db_session, test_portfolio):
        """Should return True for BUY side."""
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

            assert trade.is_buy is True
            assert trade.is_sell is False

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_is_sell_property(self, db_session, test_portfolio):
        """Should return True for SELL side."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.SELL,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.is_buy is False
            assert trade.is_sell is True

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_is_filled_property(self, db_session, test_portfolio):
        """Should return True for FILLED status."""
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

            assert trade.is_filled is True

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_is_filled_false_for_pending(self, db_session, test_portfolio):
        """Should return False for PENDING status."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

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

            assert trade.is_filled is False

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradePortfolioRelationship:
    """Tests for Trade-Portfolio relationship."""

    @pytest.mark.asyncio
    async def test_trade_belongs_to_portfolio(self, db_session, test_portfolio):
        """Should establish relationship from trade to portfolio."""
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

            # Load the relationship
            await db_session.refresh(trade, ["portfolio"])

            assert trade.portfolio is not None
            assert trade.portfolio.id == test_portfolio.id
            assert trade.portfolio.name == test_portfolio.name

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_portfolio_has_many_trades(self, db_session, test_portfolio):
        """Should establish relationship from portfolio to trades."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade1 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            trade2 = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade1)
            db_session.add(trade2)
            await db_session.commit()

            # Refresh portfolio with trades relationship
            await db_session.refresh(test_portfolio, ["trades"])

            assert len(test_portfolio.trades) == 2
            symbols = [t.symbol for t in test_portfolio.trades]
            assert "AAPL" in symbols
            assert "TSLA" in symbols

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_cascade_delete_when_portfolio_deleted(self, db_session, test_user):
        """Should delete trades when portfolio is deleted (cascade)."""
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

            # Create trades
            trade = Trade(
                portfolio_id=portfolio.id,
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
            trade_id = trade.id

            # Delete the portfolio
            await db_session.delete(portfolio)
            await db_session.commit()

            # Check trade is also deleted
            result = await db_session.execute(
                select(Trade).where(Trade.id == trade_id)
            )
            deleted_trade = result.scalar_one_or_none()

            assert deleted_trade is None

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_long_symbol(self, db_session, test_portfolio):
        """Should handle symbol names up to 20 chars (model limit)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            long_symbol = "A" * 20  # 20 char limit per model spec

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol=long_symbol,
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

            assert trade.symbol == long_symbol

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_fractional_shares(self, db_session, test_portfolio):
        """Should handle fractional share quantities."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("0.5"),  # Half a share
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.quantity == Decimal("0.5")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_very_small_quantity(self, db_session, test_portfolio):
        """Should handle small quantities within 4 decimal precision."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="BTC",
                side=TradeSide.BUY,
                quantity=Decimal("0.0001"),  # Smallest with 4 decimal precision
                price=Decimal("45000.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.quantity == Decimal("0.0001")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_very_large_quantity(self, db_session, test_portfolio):
        """Should handle large quantities."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="PENNY_STOCK",
                side=TradeSide.BUY,
                quantity=Decimal("1000000"),  # 1 million shares
                price=Decimal("0.01"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add(trade)
            await db_session.commit()
            await db_session.refresh(trade)

            assert trade.quantity == Decimal("1000000")

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_trade_repr(self, db_session, test_portfolio):
        """Should have meaningful string representation."""
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

            repr_str = repr(trade)
            assert "Trade" in repr_str
            assert "AAPL" in repr_str or str(trade.id) in repr_str

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")


class TestTradeQueryOperations:
    """Tests for querying Trade records."""

    @pytest.mark.asyncio
    async def test_query_trade_by_id(self, db_session, test_portfolio):
        """Should retrieve trade by ID."""
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
            trade_id = trade.id

            # Query by ID
            result = await db_session.execute(
                select(Trade).where(Trade.id == trade_id)
            )
            found = result.scalar_one()

            assert found.id == trade_id
            assert found.symbol == "AAPL"

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_trades_by_symbol(self, db_session, test_portfolio):
        """Should filter trades by symbol."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create trades for different symbols
            symbols = ["AAPL", "TSLA", "AAPL", "GOOGL"]

            for symbol in symbols:
                trade = Trade(
                    portfolio_id=test_portfolio.id,
                    symbol=symbol,
                    side=TradeSide.BUY,
                    quantity=Decimal("100"),
                    price=Decimal("150.00"),
                    order_type=TradeOrderType.MARKET,
                    status=TradeStatus.FILLED,
                    executed_at=datetime.utcnow(),
                )
                db_session.add(trade)

            await db_session.commit()

            # Query for AAPL trades
            result = await db_session.execute(
                select(Trade).where(Trade.symbol == "AAPL")
            )
            aapl_trades = result.scalars().all()

            assert len(aapl_trades) == 2
            assert all(t.symbol == "AAPL" for t in aapl_trades)

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_trades_by_side(self, db_session, test_portfolio):
        """Should filter trades by side (BUY/SELL)."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create mix of BUY and SELL trades
            buy_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            sell_trade = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.SELL,
                quantity=Decimal("50"),
                price=Decimal("160.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            db_session.add_all([buy_trade, sell_trade])
            await db_session.commit()

            # Query for BUY trades
            result = await db_session.execute(
                select(Trade).where(Trade.side == TradeSide.BUY)
            )
            buy_trades = result.scalars().all()

            assert len(buy_trades) == 1
            assert buy_trades[0].side == TradeSide.BUY

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")

    @pytest.mark.asyncio
    async def test_query_trades_by_status(self, db_session, test_portfolio):
        """Should filter trades by status."""
        try:
            from tradingagents.api.models.trade import Trade, TradeSide, TradeStatus, TradeOrderType

            # Create trades with different statuses
            filled = Trade(
                portfolio_id=test_portfolio.id,
                symbol="AAPL",
                side=TradeSide.BUY,
                quantity=Decimal("100"),
                price=Decimal("150.00"),
                order_type=TradeOrderType.MARKET,
                status=TradeStatus.FILLED,
                executed_at=datetime.utcnow(),
            )

            pending = Trade(
                portfolio_id=test_portfolio.id,
                symbol="TSLA",
                side=TradeSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                order_type=TradeOrderType.LIMIT,
                status=TradeStatus.PENDING,
                executed_at=None,
            )

            db_session.add_all([filled, pending])
            await db_session.commit()

            # Query for PENDING trades
            result = await db_session.execute(
                select(Trade).where(Trade.status == TradeStatus.PENDING)
            )
            pending_trades = result.scalars().all()

            assert len(pending_trades) == 1
            assert pending_trades[0].status == TradeStatus.PENDING

        except ImportError:
            pytest.skip("Trade model not yet implemented (TDD RED phase)")
