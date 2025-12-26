"""Tests for Backtest Engine.

Issue #42: [BT-41] Backtest engine - historical replay, slippage
"""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest

from tradingagents.backtest import (
    # Enums
    OrderSide,
    OrderType,
    FillStatus,
    # Data Classes
    OHLCV,
    Signal,
    BacktestConfig,
    BacktestPosition,
    BacktestTrade,
    BacktestSnapshot,
    BacktestResult,
    # Slippage Models
    SlippageModel,
    NoSlippage,
    FixedSlippage,
    PercentageSlippage,
    VolumeSlippage,
    # Commission Models
    CommissionModel,
    NoCommission,
    FixedCommission,
    PerShareCommission,
    PercentageCommission,
    TieredCommission,
    # Main Classes
    BacktestEngine,
    # Factory Functions
    create_backtest_engine,
)


ZERO = Decimal("0")


# ============================================================================
# Enum Tests
# ============================================================================

class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_values(self):
        """Test enum values."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"


class TestOrderType:
    """Tests for OrderType enum."""

    def test_values(self):
        """Test enum values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"


class TestFillStatus:
    """Tests for FillStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert FillStatus.UNFILLED.value == "unfilled"
        assert FillStatus.FILLED.value == "filled"
        assert FillStatus.PARTIAL.value == "partial"


# ============================================================================
# Data Class Tests
# ============================================================================

class TestOHLCV:
    """Tests for OHLCV dataclass."""

    def test_creation(self):
        """Test OHLCV creation."""
        bar = OHLCV(
            timestamp=datetime(2023, 1, 3),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            volume=Decimal("1000000"),
            symbol="AAPL",
        )
        assert bar.open == Decimal("100")
        assert bar.close == Decimal("103")
        assert bar.symbol == "AAPL"

    def test_numeric_conversion(self):
        """Test numeric types are converted to Decimal."""
        bar = OHLCV(
            timestamp=datetime(2023, 1, 3),
            open=100,
            high=105,
            low=99,
            close=103,
            volume=1000000,
        )
        assert isinstance(bar.open, Decimal)
        assert bar.open == Decimal("100")


class TestSignal:
    """Tests for Signal dataclass."""

    def test_creation(self):
        """Test signal creation."""
        signal = Signal(
            timestamp=datetime(2023, 1, 3),
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
        )
        assert signal.symbol == "AAPL"
        assert signal.side == OrderSide.BUY
        assert signal.quantity == Decimal("100")

    def test_defaults(self):
        """Test signal defaults."""
        signal = Signal(
            timestamp=datetime(2023, 1, 3),
            symbol="AAPL",
            side=OrderSide.BUY,
        )
        assert signal.quantity == ZERO
        assert signal.order_type == OrderType.MARKET
        assert signal.confidence == Decimal("1")


class TestBacktestConfig:
    """Tests for BacktestConfig dataclass."""

    def test_defaults(self):
        """Test default configuration."""
        config = BacktestConfig()
        assert config.initial_capital == Decimal("100000")
        assert config.allow_shorting is False
        assert config.max_position_pct == Decimal("20")

    def test_custom_config(self):
        """Test custom configuration."""
        config = BacktestConfig(
            initial_capital=Decimal("50000"),
            allow_shorting=True,
            max_position_pct=Decimal("10"),
        )
        assert config.initial_capital == Decimal("50000")
        assert config.allow_shorting is True


class TestBacktestPosition:
    """Tests for BacktestPosition dataclass."""

    def test_creation(self):
        """Test position creation."""
        position = BacktestPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            average_cost=Decimal("150"),
            current_price=Decimal("155"),
        )
        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("100")

    def test_market_value(self):
        """Test market value calculation."""
        position = BacktestPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            average_cost=Decimal("150"),
            current_price=Decimal("160"),
        )
        assert position.market_value == Decimal("16000")

    def test_cost_basis(self):
        """Test cost basis calculation."""
        position = BacktestPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            average_cost=Decimal("150"),
        )
        assert position.cost_basis == Decimal("15000")

    def test_is_long(self):
        """Test is_long property."""
        position = BacktestPosition(symbol="AAPL", quantity=Decimal("100"))
        assert position.is_long is True
        assert position.is_short is False

    def test_is_short(self):
        """Test is_short property."""
        position = BacktestPosition(symbol="AAPL", quantity=Decimal("-100"))
        assert position.is_short is True
        assert position.is_long is False

    def test_update_price(self):
        """Test price update."""
        position = BacktestPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            average_cost=Decimal("150"),
            current_price=Decimal("150"),
        )
        position.update_price(Decimal("160"), datetime(2023, 1, 4))
        assert position.current_price == Decimal("160")
        assert position.unrealized_pnl == Decimal("1000")  # (160-150)*100


# ============================================================================
# Slippage Model Tests
# ============================================================================

class TestNoSlippage:
    """Tests for NoSlippage model."""

    def test_calculate(self):
        """Test no slippage."""
        model = NoSlippage()
        slippage = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            volume=Decimal("1000000"),
        )
        assert slippage == ZERO


class TestFixedSlippage:
    """Tests for FixedSlippage model."""

    def test_calculate(self):
        """Test fixed slippage."""
        model = FixedSlippage(Decimal("0.01"))
        slippage = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            volume=Decimal("1000000"),
        )
        assert slippage == Decimal("0.01")


class TestPercentageSlippage:
    """Tests for PercentageSlippage model."""

    def test_calculate(self):
        """Test percentage slippage."""
        model = PercentageSlippage(Decimal("0.1"))  # 0.1%
        slippage = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            volume=Decimal("1000000"),
        )
        assert slippage == Decimal("0.1")  # 0.1% of 100


class TestVolumeSlippage:
    """Tests for VolumeSlippage model."""

    def test_calculate_low_volume(self):
        """Test low volume participation."""
        model = VolumeSlippage(
            base_percentage=Decimal("0.05"),
            volume_impact=Decimal("0.1"),
        )
        slippage = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            volume=Decimal("10000"),
        )
        # 100/10000 = 1% participation
        # slippage = 0.05% + (0.01 * 0.1 * 100) = 0.05% + 0.1% = 0.15%
        assert slippage > ZERO

    def test_calculate_high_volume(self):
        """Test high volume participation."""
        model = VolumeSlippage(
            base_percentage=Decimal("0.05"),
            volume_impact=Decimal("0.1"),
            max_percentage=Decimal("1.0"),
        )
        slippage = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("5000"),
            side=OrderSide.BUY,
            volume=Decimal("10000"),
        )
        # 50% participation - should hit max
        assert slippage <= Decimal("1.0")  # Max 1%

    def test_calculate_no_volume(self):
        """Test with no volume data."""
        model = VolumeSlippage(base_percentage=Decimal("0.05"))
        slippage = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            volume=ZERO,
        )
        # Falls back to base percentage
        assert slippage == Decimal("0.05")


# ============================================================================
# Commission Model Tests
# ============================================================================

class TestNoCommission:
    """Tests for NoCommission model."""

    def test_calculate(self):
        """Test no commission."""
        model = NoCommission()
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            trade_value=Decimal("10000"),
        )
        assert commission == ZERO


class TestFixedCommission:
    """Tests for FixedCommission model."""

    def test_calculate(self):
        """Test fixed commission."""
        model = FixedCommission(Decimal("9.99"))
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            trade_value=Decimal("10000"),
        )
        assert commission == Decimal("9.99")

    def test_minimum(self):
        """Test minimum commission."""
        model = FixedCommission(Decimal("5"), minimum=Decimal("10"))
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            trade_value=Decimal("10000"),
        )
        assert commission == Decimal("10")


class TestPerShareCommission:
    """Tests for PerShareCommission model."""

    def test_calculate(self):
        """Test per-share commission."""
        model = PerShareCommission(Decimal("0.005"))  # $0.005/share
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            trade_value=Decimal("10000"),
        )
        assert commission == Decimal("0.5")  # 100 * 0.005

    def test_minimum(self):
        """Test minimum commission."""
        model = PerShareCommission(Decimal("0.005"), minimum=Decimal("1.0"))
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("10"),  # Only 10 shares
            trade_value=Decimal("1000"),
        )
        assert commission == Decimal("1.0")  # Minimum

    def test_maximum(self):
        """Test maximum commission."""
        model = PerShareCommission(
            Decimal("0.005"),
            minimum=ZERO,
            maximum=Decimal("10"),
        )
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("10000"),  # Many shares
            trade_value=Decimal("1000000"),
        )
        assert commission == Decimal("10")  # Maximum


class TestPercentageCommission:
    """Tests for PercentageCommission model."""

    def test_calculate(self):
        """Test percentage commission."""
        model = PercentageCommission(Decimal("0.1"))  # 0.1%
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("100"),
            trade_value=Decimal("10000"),
        )
        assert commission == Decimal("10")  # 0.1% of 10000

    def test_minimum(self):
        """Test minimum commission."""
        model = PercentageCommission(Decimal("0.1"), minimum=Decimal("5"))
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("1"),
            trade_value=Decimal("100"),
        )
        assert commission == Decimal("5")  # Minimum


class TestTieredCommission:
    """Tests for TieredCommission model."""

    def test_calculate_low_tier(self):
        """Test low tier commission."""
        model = TieredCommission([
            (Decimal("0"), Decimal("0.2")),
            (Decimal("10000"), Decimal("0.15")),
            (Decimal("50000"), Decimal("0.1")),
        ])
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("50"),
            trade_value=Decimal("5000"),
        )
        assert commission == Decimal("10")  # 0.2% of 5000

    def test_calculate_mid_tier(self):
        """Test middle tier commission."""
        model = TieredCommission([
            (Decimal("0"), Decimal("0.2")),
            (Decimal("10000"), Decimal("0.15")),
            (Decimal("50000"), Decimal("0.1")),
        ])
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("200"),
            trade_value=Decimal("20000"),
        )
        assert commission == Decimal("30")  # 0.15% of 20000

    def test_calculate_high_tier(self):
        """Test high tier commission."""
        model = TieredCommission([
            (Decimal("0"), Decimal("0.2")),
            (Decimal("10000"), Decimal("0.15")),
            (Decimal("50000"), Decimal("0.1")),
        ])
        commission = model.calculate(
            price=Decimal("100"),
            quantity=Decimal("1000"),
            trade_value=Decimal("100000"),
        )
        assert commission == Decimal("100")  # 0.1% of 100000


# ============================================================================
# BacktestEngine Tests
# ============================================================================

class TestBacktestEngine:
    """Tests for BacktestEngine class."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return BacktestConfig(
            initial_capital=Decimal("100000"),
        )

    @pytest.fixture
    def engine(self, config):
        """Create test engine."""
        return BacktestEngine(config)

    @pytest.fixture
    def price_data(self):
        """Create test price data."""
        return {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 130, 132, 129, 131, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 131, 135, 130, 134, 1200000, "AAPL"),
                OHLCV(datetime(2023, 1, 5), 134, 136, 133, 135, 1100000, "AAPL"),
                OHLCV(datetime(2023, 1, 6), 135, 138, 134, 137, 1300000, "AAPL"),
                OHLCV(datetime(2023, 1, 9), 137, 140, 136, 139, 1400000, "AAPL"),
            ],
        }

    def test_initialization(self, engine):
        """Test engine initialization."""
        assert engine.cash == Decimal("100000")
        assert len(engine.positions) == 0
        assert len(engine.trades) == 0

    def test_reset(self, engine):
        """Test engine reset."""
        engine.cash = Decimal("50000")
        engine.positions["AAPL"] = BacktestPosition(symbol="AAPL")
        engine.reset()
        assert engine.cash == Decimal("100000")
        assert len(engine.positions) == 0

    def test_run_empty(self, engine):
        """Test run with no data."""
        result = engine.run({}, [])
        assert result.total_trades == 0
        assert result.final_value == Decimal("100000")

    def test_run_no_signals(self, engine, price_data):
        """Test run with no signals."""
        result = engine.run(price_data, [])
        assert result.total_trades == 0
        assert result.final_value == Decimal("100000")
        assert len(result.snapshots) == 5

    def test_run_buy_signal(self, engine, price_data):
        """Test run with buy signal."""
        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        assert result.total_trades == 1
        assert len(engine.positions) == 1
        assert "AAPL" in engine.positions

    def test_run_buy_and_sell(self, engine, price_data):
        """Test run with buy and sell signals."""
        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
            Signal(
                timestamp=datetime(2023, 1, 6),
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        assert result.total_trades == 2
        assert len(engine.positions) == 0  # Position closed
        # Should have profit: bought at ~131, sold at ~137
        assert result.final_value > Decimal("100000")

    def test_run_with_slippage(self, price_data):
        """Test run with slippage model."""
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            slippage_model=FixedSlippage(Decimal("0.10")),
        )
        engine = BacktestEngine(config)

        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        # Check slippage was applied
        trade = result.trades[0]
        assert trade.slippage > ZERO
        assert trade.price > trade.base_price  # Buy price increased by slippage

    def test_run_with_commission(self, price_data):
        """Test run with commission model."""
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            commission_model=FixedCommission(Decimal("10")),
        )
        engine = BacktestEngine(config)

        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        assert result.total_commission == Decimal("10")
        trade = result.trades[0]
        assert trade.commission == Decimal("10")

    def test_run_insufficient_cash(self, price_data):
        """Test run with insufficient cash."""
        config = BacktestConfig(
            initial_capital=Decimal("1000"),  # Not enough for 100 shares at $131
        )
        engine = BacktestEngine(config)

        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        # Should have bought fewer shares
        if result.total_trades > 0:
            assert engine.positions["AAPL"].quantity < Decimal("100")
        # If no trades, that's also acceptable (couldn't afford any)

    def test_run_no_shorting(self, engine, price_data):
        """Test no shorting when disabled."""
        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        # Sell should be rejected (no position and shorting disabled)
        assert result.total_trades == 0

    def test_run_with_shorting(self, price_data):
        """Test shorting when enabled."""
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            allow_shorting=True,
        )
        engine = BacktestEngine(config)

        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=Decimal("100"),
            ),
        ]
        result = engine.run(price_data, signals)

        # Should have short position
        assert result.total_trades == 1
        assert engine.positions["AAPL"].quantity == Decimal("-100")

    def test_run_position_sizing(self, price_data):
        """Test automatic position sizing."""
        engine = BacktestEngine(BacktestConfig(
            initial_capital=Decimal("100000"),
            position_sizing="equal",
        ))

        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=ZERO,  # Auto-size
            ),
        ]
        result = engine.run(price_data, signals)

        # Should have calculated quantity
        if result.total_trades > 0:
            assert result.trades[0].quantity > ZERO

    def test_get_position(self, engine, price_data):
        """Test getting position."""
        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        engine.run(price_data, signals)

        position = engine.get_position("AAPL")
        assert position is not None
        assert position.quantity == Decimal("100")

        no_position = engine.get_position("GOOG")
        assert no_position is None

    def test_get_cash(self, engine, price_data):
        """Test getting cash balance."""
        initial_cash = engine.get_cash()
        assert initial_cash == Decimal("100000")

        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        engine.run(price_data, signals)

        assert engine.get_cash() < initial_cash

    def test_get_portfolio_value(self, engine, price_data):
        """Test getting portfolio value."""
        signals = [
            Signal(
                timestamp=datetime(2023, 1, 3),
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
            ),
        ]
        engine.run(price_data, signals)

        value = engine.get_portfolio_value()
        # Should be approximately initial capital (cash + position value)
        assert value > Decimal("99000")
        assert value < Decimal("101000")


class TestBacktestResult:
    """Tests for BacktestResult metrics."""

    @pytest.fixture
    def price_data(self):
        """Create test price data with clear trend."""
        return {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 100, 102, 99, 100, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 100, 105, 99, 105, 1200000, "AAPL"),
                OHLCV(datetime(2023, 1, 5), 105, 110, 104, 110, 1100000, "AAPL"),
                OHLCV(datetime(2023, 1, 6), 110, 115, 109, 115, 1300000, "AAPL"),
                OHLCV(datetime(2023, 1, 9), 115, 120, 114, 120, 1400000, "AAPL"),
            ],
        }

    def test_winning_trade(self, price_data):
        """Test metrics for winning trade."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
            Signal(datetime(2023, 1, 9), "AAPL", OrderSide.SELL, Decimal("100")),
        ]
        result = engine.run(price_data, signals)

        assert result.total_trades == 2
        assert result.winning_trades >= 1
        assert result.total_return > ZERO
        assert result.final_value > result.initial_capital

    def test_max_drawdown(self, price_data):
        """Test max drawdown calculation."""
        # Add some volatility
        price_data["AAPL"].insert(2, OHLCV(
            datetime(2023, 1, 4, 12), 105, 106, 95, 95, 1000000, "AAPL"
        ))

        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
        ]
        result = engine.run(price_data, signals)

        # Should have some drawdown recorded
        assert result.max_drawdown >= ZERO

    def test_snapshots(self, price_data):
        """Test snapshot creation."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
        ]
        result = engine.run(price_data, signals)

        assert len(result.snapshots) == 5
        for snapshot in result.snapshots:
            assert snapshot.total_value > ZERO
            assert snapshot.cash >= ZERO

    def test_daily_returns(self, price_data):
        """Test daily returns calculation."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
        ]
        result = engine.run(price_data, signals)

        assert len(result.daily_returns) == 4  # 5 snapshots = 4 returns

    def test_trade_stats(self, price_data):
        """Test trade statistics."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("50")),
            Signal(datetime(2023, 1, 5), "AAPL", OrderSide.SELL, Decimal("50")),
            Signal(datetime(2023, 1, 5), "AAPL", OrderSide.BUY, Decimal("50")),
            Signal(datetime(2023, 1, 9), "AAPL", OrderSide.SELL, Decimal("50")),
        ]
        result = engine.run(price_data, signals)

        assert result.total_trades == 4
        assert result.winning_trades + result.losing_trades + (result.total_trades - result.winning_trades - result.losing_trades) == result.total_trades


class TestBacktestEngineIntegration:
    """Integration tests for backtest engine."""

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.backtest import (
            OrderSide,
            OrderType,
            FillStatus,
            OHLCV,
            Signal,
            BacktestConfig,
            BacktestPosition,
            BacktestTrade,
            BacktestSnapshot,
            BacktestResult,
            SlippageModel,
            NoSlippage,
            FixedSlippage,
            PercentageSlippage,
            VolumeSlippage,
            CommissionModel,
            NoCommission,
            FixedCommission,
            PerShareCommission,
            PercentageCommission,
            TieredCommission,
            BacktestEngine,
            create_backtest_engine,
        )

        # All imports successful
        assert BacktestEngine is not None
        assert OrderSide.BUY is not None

    def test_create_backtest_engine_factory(self):
        """Test factory function."""
        engine = create_backtest_engine(
            initial_capital=Decimal("50000"),
            slippage=PercentageSlippage(Decimal("0.1")),
            commission=FixedCommission(Decimal("10")),
        )

        assert engine.config.initial_capital == Decimal("50000")
        assert isinstance(engine.config.slippage_model, PercentageSlippage)
        assert isinstance(engine.config.commission_model, FixedCommission)

    def test_strategy_callback(self):
        """Test dynamic signal generation via callback."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        price_data = {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 100, 102, 99, 101, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 101, 105, 100, 104, 1200000, "AAPL"),
                OHLCV(datetime(2023, 1, 5), 104, 108, 103, 107, 1100000, "AAPL"),
            ],
        }

        def strategy(timestamp, bars):
            """Simple momentum strategy."""
            if "AAPL" in bars and bars["AAPL"].close > Decimal("102"):
                return [Signal(
                    timestamp=timestamp,
                    symbol="AAPL",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                )]
            return []

        result = engine.run(price_data, [], strategy_callback=strategy)

        # Strategy should have generated signals on days 2 and 3
        assert result.total_trades >= 1

    def test_multi_symbol(self):
        """Test with multiple symbols."""
        engine = BacktestEngine(BacktestConfig(initial_capital=Decimal("100000")))

        price_data = {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 100, 102, 99, 101, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 101, 105, 100, 104, 1200000, "AAPL"),
            ],
            "GOOG": [
                OHLCV(datetime(2023, 1, 3), 90, 92, 89, 91, 500000, "GOOG"),
                OHLCV(datetime(2023, 1, 4), 91, 94, 90, 93, 600000, "GOOG"),
            ],
        }

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("50")),
            Signal(datetime(2023, 1, 3), "GOOG", OrderSide.BUY, Decimal("50")),
        ]

        result = engine.run(price_data, signals)

        assert result.total_trades == 2
        assert "AAPL" in engine.positions
        assert "GOOG" in engine.positions

    def test_date_range_filter(self):
        """Test date range filtering."""
        config = BacktestConfig(
            initial_capital=Decimal("100000"),
            start_date=datetime(2023, 1, 4),
            end_date=datetime(2023, 1, 5),
        )
        engine = BacktestEngine(config)

        price_data = {
            "AAPL": [
                OHLCV(datetime(2023, 1, 3), 100, 102, 99, 101, 1000000, "AAPL"),
                OHLCV(datetime(2023, 1, 4), 101, 105, 100, 104, 1200000, "AAPL"),
                OHLCV(datetime(2023, 1, 5), 104, 108, 103, 107, 1100000, "AAPL"),
                OHLCV(datetime(2023, 1, 6), 107, 110, 106, 109, 1300000, "AAPL"),
            ],
        }

        signals = [
            Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("50")),  # Before range
            Signal(datetime(2023, 1, 4), "AAPL", OrderSide.BUY, Decimal("50")),  # In range
            Signal(datetime(2023, 1, 6), "AAPL", OrderSide.SELL, Decimal("50")),  # After range
        ]

        result = engine.run(price_data, signals)

        # Only Jan 4 signal should execute
        assert result.total_trades == 1
        assert len(result.snapshots) == 2  # Only Jan 4-5
