"""Tests for Signal to Order Converter.

Issue #36: [STRAT-35] Signal to order converter
"""

from datetime import datetime
from decimal import Decimal
import pytest

from tradingagents.strategy.signal_to_order import (
    # Enums
    SignalType,
    SignalStrength,
    PositionSizingMethod,
    StopLossType,
    TakeProfitType,
    OrderValidationError,
    # Data Classes
    TradingSignal,
    PositionSizingConfig,
    StopLossConfig,
    TakeProfitConfig,
    ConversionConfig,
    OrderValidationResult,
    ConversionResult,
    # Main Class
    SignalToOrderConverter,
)
from tradingagents.execution.broker_base import OrderSide, OrderType


# ============================================================================
# Enum Tests
# ============================================================================

class TestSignalType:
    """Tests for SignalType enum."""

    def test_all_signal_types_defined(self):
        """Verify all signal types exist."""
        assert SignalType.BUY
        assert SignalType.SELL
        assert SignalType.HOLD
        assert SignalType.CLOSE
        assert SignalType.SCALE_IN
        assert SignalType.SCALE_OUT

    def test_signal_values(self):
        """Verify signal type values."""
        assert SignalType.BUY.value == "buy"
        assert SignalType.SELL.value == "sell"


class TestSignalStrength:
    """Tests for SignalStrength enum."""

    def test_all_strengths_defined(self):
        """Verify all strengths exist."""
        assert SignalStrength.STRONG
        assert SignalStrength.MODERATE
        assert SignalStrength.WEAK


class TestPositionSizingMethod:
    """Tests for PositionSizingMethod enum."""

    def test_all_methods_defined(self):
        """Verify all sizing methods exist."""
        assert PositionSizingMethod.FIXED_QUANTITY
        assert PositionSizingMethod.FIXED_VALUE
        assert PositionSizingMethod.PERCENT_PORTFOLIO
        assert PositionSizingMethod.RISK_BASED
        assert PositionSizingMethod.VOLATILITY_BASED


class TestStopLossType:
    """Tests for StopLossType enum."""

    def test_all_stop_types_defined(self):
        """Verify all stop loss types exist."""
        assert StopLossType.FIXED_PERCENT
        assert StopLossType.FIXED_AMOUNT
        assert StopLossType.ATR_BASED
        assert StopLossType.TRAILING


class TestTakeProfitType:
    """Tests for TakeProfitType enum."""

    def test_all_tp_types_defined(self):
        """Verify all take profit types exist."""
        assert TakeProfitType.FIXED_PERCENT
        assert TakeProfitType.FIXED_AMOUNT
        assert TakeProfitType.RISK_REWARD


# ============================================================================
# Data Class Tests
# ============================================================================

class TestTradingSignal:
    """Tests for TradingSignal dataclass."""

    def test_default_creation(self):
        """Test creating signal with defaults."""
        signal = TradingSignal()
        assert signal.signal_id is not None
        assert signal.timestamp is not None
        assert signal.signal_type == SignalType.HOLD
        assert signal.strength == SignalStrength.MODERATE
        assert signal.confidence == Decimal("0.5")

    def test_with_all_fields(self):
        """Test creating signal with all fields."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            entry_price=Decimal("150.00"),
            target_price=Decimal("165.00"),
            stop_price=Decimal("145.00"),
            confidence=Decimal("0.85"),
            reason="Bullish breakout",
        )
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.entry_price == Decimal("150.00")


class TestPositionSizingConfig:
    """Tests for PositionSizingConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = PositionSizingConfig()
        assert config.method == PositionSizingMethod.PERCENT_PORTFOLIO
        assert config.percent_portfolio == Decimal("0.05")
        assert config.max_risk_per_trade == Decimal("0.01")

    def test_custom_config(self):
        """Test creating custom config."""
        config = PositionSizingConfig(
            method=PositionSizingMethod.RISK_BASED,
            max_risk_per_trade=Decimal("0.02"),
        )
        assert config.method == PositionSizingMethod.RISK_BASED


class TestStopLossConfig:
    """Tests for StopLossConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = StopLossConfig()
        assert config.type == StopLossType.FIXED_PERCENT
        assert config.percent == Decimal("0.02")
        assert config.enabled is True


class TestTakeProfitConfig:
    """Tests for TakeProfitConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = TakeProfitConfig()
        assert config.type == TakeProfitType.RISK_REWARD
        assert config.risk_reward_ratio == Decimal("3.0")


class TestConversionConfig:
    """Tests for ConversionConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = ConversionConfig()
        assert config.default_order_type == OrderType.MARKET
        assert config.scale_by_strength is True


class TestOrderValidationResult:
    """Tests for OrderValidationResult dataclass."""

    def test_default_is_valid(self):
        """Test default is valid."""
        result = OrderValidationResult()
        assert result.is_valid is True
        assert result.errors == []


class TestConversionResult:
    """Tests for ConversionResult dataclass."""

    def test_default_creation(self):
        """Test creating result with defaults."""
        result = ConversionResult()
        assert result.success is True
        assert result.order_request is None


# ============================================================================
# SignalToOrderConverter Tests
# ============================================================================

class TestSignalToOrderConverter:
    """Tests for SignalToOrderConverter class."""

    @pytest.fixture
    def converter(self):
        """Create default converter."""
        return SignalToOrderConverter(
            portfolio_value=Decimal("100000"),
            current_prices={"AAPL": Decimal("150.00")},
        )

    @pytest.fixture
    def buy_signal(self):
        """Create a buy signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            confidence=Decimal("0.8"),
        )

    @pytest.fixture
    def sell_signal(self):
        """Create a sell signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.SELL,
            strength=SignalStrength.MODERATE,
            confidence=Decimal("0.7"),
        )

    def test_initialization(self, converter):
        """Test converter initialization."""
        assert converter.portfolio_value == Decimal("100000")
        assert "AAPL" in converter.current_prices
        assert converter.config is not None

    def test_custom_config(self):
        """Test converter with custom config."""
        config = ConversionConfig(
            use_limit_orders=True,
        )
        converter = SignalToOrderConverter(config=config)
        assert converter.config.use_limit_orders is True

    def test_convert_buy_signal(self, converter, buy_signal):
        """Test converting a buy signal."""
        result = converter.convert(buy_signal)
        assert result.success is True
        assert result.order_request is not None
        assert result.order_request.side == OrderSide.BUY
        assert result.order_request.symbol == "AAPL"

    def test_convert_sell_signal(self, converter, sell_signal):
        """Test converting a sell signal."""
        result = converter.convert(sell_signal)
        assert result.success is True
        assert result.order_request.side == OrderSide.SELL

    def test_hold_signal_no_order(self, converter):
        """Test that HOLD signals don't generate orders."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.HOLD,
        )
        result = converter.convert(signal)
        assert result.success is False
        assert "HOLD" in result.error_message

    def test_position_sizing_percent_portfolio(self, converter, buy_signal):
        """Test position sizing with percent of portfolio."""
        result = converter.convert(buy_signal)
        # 5% of 100k = 5000, divided by 150 = ~33 shares
        # With strong signal multiplier of 1.0
        assert result.calculated_quantity > 0
        assert result.calculated_quantity <= Decimal("100")  # Reasonable size

    def test_position_sizing_fixed_quantity(self, buy_signal):
        """Test fixed quantity position sizing."""
        config = ConversionConfig(
            position_sizing=PositionSizingConfig(
                method=PositionSizingMethod.FIXED_QUANTITY,
                fixed_quantity=Decimal("50"),
            ),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        # Should use fixed quantity (possibly scaled by strength)
        assert result.calculated_quantity > 0

    def test_position_sizing_fixed_value(self, buy_signal):
        """Test fixed value position sizing."""
        config = ConversionConfig(
            position_sizing=PositionSizingConfig(
                method=PositionSizingMethod.FIXED_VALUE,
                fixed_value=Decimal("7500"),
            ),
            scale_by_strength=False,
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        # 7500 / 150 = 50 shares
        assert result.calculated_quantity == Decimal("50")

    def test_position_sizing_risk_based(self, buy_signal):
        """Test risk-based position sizing."""
        config = ConversionConfig(
            position_sizing=PositionSizingConfig(
                method=PositionSizingMethod.RISK_BASED,
                max_risk_per_trade=Decimal("0.01"),  # 1% = $1000
            ),
            scale_by_strength=False,
        )
        converter = SignalToOrderConverter(
            config=config,
            portfolio_value=Decimal("100000"),
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        assert result.calculated_quantity > 0

    def test_strength_multiplier_strong(self, converter, buy_signal):
        """Test that strong signals get full position size."""
        buy_signal.strength = SignalStrength.STRONG
        result = converter.convert(buy_signal)
        strong_qty = result.calculated_quantity

        buy_signal.strength = SignalStrength.WEAK
        result2 = converter.convert(buy_signal)
        weak_qty = result2.calculated_quantity

        # Strong should be >= weak (multipliers 1.0 vs 0.5)
        assert strong_qty >= weak_qty

    def test_stop_loss_calculated(self, converter, buy_signal):
        """Test stop loss is calculated."""
        result = converter.convert(buy_signal)
        assert result.calculated_stop_price is not None
        # For buy, stop should be below entry
        assert result.calculated_stop_price < Decimal("150.00")

    def test_stop_loss_fixed_percent(self, buy_signal):
        """Test fixed percent stop loss."""
        config = ConversionConfig(
            stop_loss=StopLossConfig(
                type=StopLossType.FIXED_PERCENT,
                percent=Decimal("0.05"),  # 5%
            ),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        # 150 * (1 - 0.05) = 142.50
        assert result.calculated_stop_price == Decimal("142.50")

    def test_stop_loss_atr_based(self, buy_signal):
        """Test ATR-based stop loss."""
        config = ConversionConfig(
            stop_loss=StopLossConfig(
                type=StopLossType.ATR_BASED,
                atr_multiplier=Decimal("2.0"),
            ),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
            volatility_data={"AAPL": Decimal("3.00")},  # $3 ATR
        )
        result = converter.convert(buy_signal)
        # 150 - (3 * 2) = 144
        assert result.calculated_stop_price == Decimal("144.00")

    def test_take_profit_calculated(self, converter, buy_signal):
        """Test take profit is calculated."""
        result = converter.convert(buy_signal)
        assert result.calculated_take_profit is not None
        # For buy, take profit should be above entry
        assert result.calculated_take_profit > Decimal("150.00")

    def test_take_profit_risk_reward(self, buy_signal):
        """Test risk:reward take profit."""
        config = ConversionConfig(
            stop_loss=StopLossConfig(
                type=StopLossType.FIXED_PERCENT,
                percent=Decimal("0.02"),  # 2% stop = $3 risk
            ),
            take_profit=TakeProfitConfig(
                type=TakeProfitType.RISK_REWARD,
                risk_reward_ratio=Decimal("3.0"),  # 3:1
            ),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        # Stop at 147, risk = 3, reward = 9, target = 159
        assert result.calculated_take_profit == Decimal("159.00")

    def test_validation_invalid_symbol(self, converter):
        """Test validation rejects empty symbol."""
        signal = TradingSignal(
            symbol="",
            signal_type=SignalType.BUY,
        )
        result = converter.convert(signal)
        assert result.success is False
        # Empty symbol with no price will fail on entry price first
        # Or validation will catch it
        assert (
            "entry price" in result.error_message.lower() or
            any(e == OrderValidationError.INVALID_SYMBOL for e, _ in result.validation.errors)
        )

    def test_validation_insufficient_price(self, converter):
        """Test validation when price not available."""
        signal = TradingSignal(
            symbol="UNKNOWN",
            signal_type=SignalType.BUY,
        )
        result = converter.convert(signal)
        assert result.success is False

    def test_use_signal_entry_price(self, converter):
        """Test using signal's entry price."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            entry_price=Decimal("152.00"),  # Different from current
        )
        result = converter.convert(signal)
        # Stop should be based on 152, not 150
        # With 2% stop: 152 * 0.98 = 148.96
        assert result.calculated_stop_price == Decimal("148.96")

    def test_use_signal_stop_price(self, converter):
        """Test using signal's stop price."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            stop_price=Decimal("140.00"),
        )
        result = converter.convert(signal)
        assert result.calculated_stop_price == Decimal("140.00")

    def test_use_signal_target_price(self, converter):
        """Test using signal's target price."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            target_price=Decimal("170.00"),
        )
        result = converter.convert(signal)
        assert result.calculated_take_profit == Decimal("170.00")

    def test_min_confidence(self, buy_signal):
        """Test minimum confidence threshold."""
        config = ConversionConfig(
            min_confidence=Decimal("0.9"),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        buy_signal.confidence = Decimal("0.8")
        result = converter.convert(buy_signal)
        assert result.success is False
        assert "confidence" in result.error_message.lower()

    def test_order_metadata(self, converter, buy_signal):
        """Test that order includes signal metadata."""
        result = converter.convert(buy_signal)
        assert result.order_request.metadata["signal_id"] == buy_signal.signal_id
        assert result.order_request.metadata["signal_strength"] == "strong"

    def test_stop_loss_order_created(self, converter, buy_signal):
        """Test separate stop loss order is created."""
        result = converter.convert(buy_signal)
        assert result.stop_loss_order is not None
        assert result.stop_loss_order.side == OrderSide.SELL
        assert result.stop_loss_order.order_type == OrderType.STOP

    def test_take_profit_order_created(self, converter, buy_signal):
        """Test separate take profit order is created."""
        result = converter.convert(buy_signal)
        assert result.take_profit_order is not None
        assert result.take_profit_order.side == OrderSide.SELL
        assert result.take_profit_order.order_type == OrderType.LIMIT

    def test_limit_orders(self, buy_signal):
        """Test using limit orders instead of market."""
        config = ConversionConfig(
            use_limit_orders=True,
            limit_order_offset=Decimal("0.01"),  # 1%
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        assert result.order_request.order_type == OrderType.LIMIT
        # Buy limit should be above current: 150 * 1.01 = 151.50
        assert result.order_request.limit_price == Decimal("151.50")

    def test_convert_batch(self, converter):
        """Test batch conversion."""
        signals = [
            TradingSignal(symbol="AAPL", signal_type=SignalType.BUY),
            TradingSignal(symbol="AAPL", signal_type=SignalType.SELL),
            TradingSignal(symbol="AAPL", signal_type=SignalType.HOLD),
        ]
        results = converter.convert_batch(signals)
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is True
        assert results[2].success is False  # HOLD

    def test_update_portfolio_value(self, converter):
        """Test updating portfolio value."""
        converter.update_portfolio_value(Decimal("200000"))
        assert converter.portfolio_value == Decimal("200000")

    def test_update_price(self, converter):
        """Test updating price."""
        converter.update_price("MSFT", Decimal("300.00"))
        assert converter.current_prices["MSFT"] == Decimal("300.00")

    def test_update_volatility(self, converter):
        """Test updating volatility."""
        converter.update_volatility("AAPL", Decimal("5.00"))
        assert converter.volatility_data["AAPL"] == Decimal("5.00")

    def test_scale_in_signal(self, converter):
        """Test SCALE_IN signal."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.SCALE_IN,
        )
        result = converter.convert(signal)
        assert result.success is True
        assert result.order_request.side == OrderSide.BUY

    def test_scale_out_signal(self, converter):
        """Test SCALE_OUT signal."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.SCALE_OUT,
        )
        result = converter.convert(signal)
        assert result.success is True
        assert result.order_request.side == OrderSide.SELL

    def test_close_signal(self, converter):
        """Test CLOSE signal."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.CLOSE,
        )
        result = converter.convert(signal)
        assert result.success is True
        assert result.order_request.side == OrderSide.SELL

    def test_sell_stop_above_entry(self, converter, sell_signal):
        """Test sell signal stop is above entry."""
        result = converter.convert(sell_signal)
        # For short, stop should be above entry
        assert result.calculated_stop_price > Decimal("150.00")

    def test_sell_take_profit_below_entry(self, converter, sell_signal):
        """Test sell signal take profit is below entry."""
        result = converter.convert(sell_signal)
        # For short, take profit should be below entry
        assert result.calculated_take_profit < Decimal("150.00")

    def test_disabled_stop_loss(self, buy_signal):
        """Test with stop loss disabled."""
        config = ConversionConfig(
            stop_loss=StopLossConfig(enabled=False),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        assert result.calculated_stop_price is None
        assert result.stop_loss_order is None

    def test_disabled_take_profit(self, buy_signal):
        """Test with take profit disabled."""
        config = ConversionConfig(
            take_profit=TakeProfitConfig(enabled=False),
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        assert result.calculated_take_profit is None
        assert result.take_profit_order is None

    def test_lot_size_rounding(self, buy_signal):
        """Test rounding to lot size."""
        config = ConversionConfig(
            position_sizing=PositionSizingConfig(
                method=PositionSizingMethod.FIXED_VALUE,
                fixed_value=Decimal("7555"),  # Would give 50.366...
                lot_size=Decimal("10"),
            ),
            scale_by_strength=False,
        )
        converter = SignalToOrderConverter(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        # Should round down to 50
        assert result.calculated_quantity == Decimal("50")

    def test_max_position_limit(self, buy_signal):
        """Test max position size limit."""
        config = ConversionConfig(
            position_sizing=PositionSizingConfig(
                method=PositionSizingMethod.FIXED_VALUE,
                fixed_value=Decimal("50000"),  # 50% of portfolio
                max_position_percent=Decimal("0.10"),  # But max is 10%
            ),
            scale_by_strength=False,
        )
        converter = SignalToOrderConverter(
            config=config,
            portfolio_value=Decimal("100000"),
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = converter.convert(buy_signal)
        # Max is 10k / 150 = 66 shares
        assert result.calculated_quantity <= Decimal("67")


# ============================================================================
# Integration Tests
# ============================================================================

class TestSignalToOrderIntegration:
    """Integration tests for signal to order conversion."""

    def test_full_workflow(self):
        """Test complete conversion workflow."""
        # Setup converter with realistic config
        config = ConversionConfig(
            position_sizing=PositionSizingConfig(
                method=PositionSizingMethod.RISK_BASED,
                max_risk_per_trade=Decimal("0.01"),  # 1%
            ),
            stop_loss=StopLossConfig(
                type=StopLossType.FIXED_PERCENT,
                percent=Decimal("0.02"),  # 2%
            ),
            take_profit=TakeProfitConfig(
                type=TakeProfitType.RISK_REWARD,
                risk_reward_ratio=Decimal("3.0"),
            ),
        )

        converter = SignalToOrderConverter(
            config=config,
            portfolio_value=Decimal("100000"),
            current_prices={"AAPL": Decimal("150.00")},
        )

        # Generate signal
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            confidence=Decimal("0.85"),
            reason="Bullish breakout with volume",
        )

        # Convert
        result = converter.convert(signal)

        # Verify complete result
        assert result.success is True
        assert result.order_request is not None
        assert result.order_request.symbol == "AAPL"
        assert result.order_request.side == OrderSide.BUY
        assert result.calculated_quantity > 0
        assert result.calculated_stop_price == Decimal("147.00")
        assert result.calculated_take_profit == Decimal("159.00")

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.strategy import (
            SignalType,
            SignalStrength,
            PositionSizingMethod,
            StopLossType,
            TakeProfitType,
            TradingSignal,
            ConversionConfig,
            SignalToOrderConverter,
        )

        # All imports successful
        assert SignalType.BUY is not None
        assert SignalToOrderConverter is not None

    def test_multiple_symbols(self):
        """Test converting signals for multiple symbols."""
        converter = SignalToOrderConverter(
            portfolio_value=Decimal("100000"),
            current_prices={
                "AAPL": Decimal("150.00"),
                "MSFT": Decimal("300.00"),
                "GOOG": Decimal("100.00"),
            },
        )

        signals = [
            TradingSignal(symbol="AAPL", signal_type=SignalType.BUY),
            TradingSignal(symbol="MSFT", signal_type=SignalType.SELL),
            TradingSignal(symbol="GOOG", signal_type=SignalType.BUY),
        ]

        results = converter.convert_batch(signals)

        assert all(r.success for r in results)
        assert results[0].order_request.symbol == "AAPL"
        assert results[1].order_request.symbol == "MSFT"
        assert results[2].order_request.symbol == "GOOG"
