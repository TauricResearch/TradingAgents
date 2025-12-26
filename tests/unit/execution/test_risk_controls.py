"""Tests for Risk Controls implementation.

Issue #28: [EXEC-27] Risk controls - position limits, loss limits
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta, date
import pytest

from tradingagents.execution import (
    RiskManager,
    RiskCheckResult,
    RiskRuleType,
    RiskViolation,
    RiskCheckResponse,
    PositionLimits,
    LossLimits,
    PortfolioState,
    OrderRequest,
    OrderSide,
    Position,
    PositionSide,
)


class TestRiskViolation:
    """Test RiskViolation dataclass."""

    def test_violation_creation(self):
        """Test creating a violation."""
        violation = RiskViolation(
            rule_type=RiskRuleType.POSITION_SIZE,
            rule_name="max_position_size",
            message="Position too large",
            current_value=Decimal("1500"),
            limit_value=Decimal("1000"),
        )
        assert violation.rule_type == RiskRuleType.POSITION_SIZE
        assert violation.current_value == Decimal("1500")
        assert violation.severity == "error"

    def test_violation_with_warning_severity(self):
        """Test violation with warning severity."""
        violation = RiskViolation(
            rule_type=RiskRuleType.DAILY_LOSS,
            rule_name="potential_loss",
            message="Potential loss warning",
            current_value=Decimal("100"),
            limit_value=Decimal("200"),
            severity="warning",
        )
        assert violation.severity == "warning"


class TestRiskCheckResponse:
    """Test RiskCheckResponse dataclass."""

    def test_default_passed(self):
        """Test default response is passed."""
        response = RiskCheckResponse()
        assert response.passed is True
        assert response.violations == []
        assert response.warnings == []

    def test_add_violation(self):
        """Test adding violation fails response."""
        response = RiskCheckResponse()
        violation = RiskViolation(
            rule_type=RiskRuleType.POSITION_SIZE,
            rule_name="test",
            message="Test violation",
            current_value=Decimal("100"),
            limit_value=Decimal("50"),
        )
        response.add_violation(violation)
        assert response.passed is False
        assert len(response.violations) == 1

    def test_add_warning(self):
        """Test adding warning keeps passed."""
        response = RiskCheckResponse()
        violation = RiskViolation(
            rule_type=RiskRuleType.DAILY_LOSS,
            rule_name="test",
            message="Test warning",
            current_value=Decimal("100"),
            limit_value=Decimal("200"),
            severity="warning",
        )
        response.add_violation(violation)
        assert response.passed is True
        assert len(response.warnings) == 1

    def test_rejection_message(self):
        """Test rejection message formatting."""
        response = RiskCheckResponse()
        violation = RiskViolation(
            rule_type=RiskRuleType.POSITION_SIZE,
            rule_name="test",
            message="Position too large",
            current_value=Decimal("100"),
            limit_value=Decimal("50"),
        )
        response.add_violation(violation)
        assert "Position too large" in response.rejection_message

    def test_rejection_message_none_when_passed(self):
        """Test rejection message is None when passed."""
        response = RiskCheckResponse()
        assert response.rejection_message is None


class TestPositionLimits:
    """Test PositionLimits dataclass."""

    def test_default_limits(self):
        """Test default limits are None."""
        limits = PositionLimits()
        assert limits.max_position_size is None
        assert limits.max_position_value is None
        assert limits.max_concentration_percent is None

    def test_custom_limits(self):
        """Test setting custom limits."""
        limits = PositionLimits(
            max_position_size=Decimal("1000"),
            max_position_value=Decimal("50000"),
            max_concentration_percent=Decimal("20"),
        )
        assert limits.max_position_size == Decimal("1000")
        assert limits.max_position_value == Decimal("50000")
        assert limits.max_concentration_percent == Decimal("20")

    def test_per_symbol_limits(self):
        """Test per-symbol limits."""
        limits = PositionLimits(
            max_position_size=Decimal("1000"),
            per_symbol_limits={
                "AAPL": {"max_position_size": Decimal("500")},
            },
        )
        assert limits.get_limit_for_symbol("AAPL", "max_position_size") == Decimal("500")
        assert limits.get_limit_for_symbol("MSFT", "max_position_size") == Decimal("1000")


class TestLossLimits:
    """Test LossLimits dataclass."""

    def test_default_limits(self):
        """Test default limits are None."""
        limits = LossLimits()
        assert limits.max_daily_loss is None
        assert limits.max_drawdown is None
        assert limits.cooling_off_period_minutes == 0

    def test_custom_limits(self):
        """Test setting custom limits."""
        limits = LossLimits(
            max_daily_loss=Decimal("500"),
            max_daily_loss_percent=Decimal("5"),
            max_drawdown_percent=Decimal("20"),
            cooling_off_period_minutes=30,
        )
        assert limits.max_daily_loss == Decimal("500")
        assert limits.max_daily_loss_percent == Decimal("5")
        assert limits.cooling_off_period_minutes == 30


class TestPortfolioState:
    """Test PortfolioState dataclass."""

    def test_default_state(self):
        """Test default state."""
        state = PortfolioState()
        assert state.cash == Decimal("0")
        assert state.equity == Decimal("0")
        assert state.daily_pnl == Decimal("0")

    def test_drawdown_calculation(self):
        """Test drawdown calculation."""
        state = PortfolioState(
            equity=Decimal("90000"),
            peak_equity=Decimal("100000"),
        )
        assert state.current_drawdown == Decimal("10000")
        assert state.current_drawdown_percent == Decimal("10")

    def test_no_drawdown_without_peak(self):
        """Test no drawdown without peak."""
        state = PortfolioState(equity=Decimal("100000"))
        assert state.current_drawdown == Decimal("0")
        assert state.current_drawdown_percent == Decimal("0")


class TestRiskManagerInit:
    """Test RiskManager initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        manager = RiskManager()
        assert manager.enabled is True
        assert manager.position_limits is not None
        assert manager.loss_limits is not None

    def test_disabled_initialization(self):
        """Test disabled initialization."""
        manager = RiskManager(enabled=False)
        assert manager.enabled is False

    def test_with_limits(self):
        """Test initialization with limits."""
        pos_limits = PositionLimits(max_position_size=Decimal("1000"))
        loss_limits = LossLimits(max_daily_loss=Decimal("500"))
        manager = RiskManager(
            position_limits=pos_limits,
            loss_limits=loss_limits,
        )
        assert manager.position_limits.max_position_size == Decimal("1000")
        assert manager.loss_limits.max_daily_loss == Decimal("500")


class TestRiskManagerPositionLimits:
    """Test RiskManager position limit checks."""

    def test_position_size_within_limit(self):
        """Test position size within limit passes."""
        manager = RiskManager(
            position_limits=PositionLimits(max_position_size=Decimal("1000"))
        )
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("500"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is True

    def test_position_size_exceeds_limit(self):
        """Test position size exceeding limit fails."""
        manager = RiskManager(
            position_limits=PositionLimits(max_position_size=Decimal("1000"))
        )
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("1500"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_position_size" for v in result.violations)

    def test_position_size_with_existing_position(self):
        """Test position size check with existing position."""
        manager = RiskManager(
            position_limits=PositionLimits(max_position_size=Decimal("1000"))
        )
        portfolio = PortfolioState(
            positions={
                "AAPL": Position(
                    symbol="AAPL",
                    quantity=Decimal("600"),
                    side=PositionSide.LONG,
                    avg_entry_price=Decimal("100"),
                    current_price=Decimal("100"),
                    market_value=Decimal("60000"),
                    cost_basis=Decimal("60000"),
                    unrealized_pnl=Decimal("0"),
                    unrealized_pnl_percent=Decimal("0"),
                )
            }
        )
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("500"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False  # 600 + 500 = 1100 > 1000

    def test_position_value_limit(self):
        """Test position value limit."""
        manager = RiskManager(
            position_limits=PositionLimits(max_position_value=Decimal("50000"))
        )
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("1000"))

        # At $100, value is $100,000 which exceeds $50,000 limit
        result = manager.validate_order(order, portfolio, estimated_fill_price=Decimal("100"))
        assert result.passed is False
        assert any(v.rule_name == "max_position_value" for v in result.violations)

    def test_concentration_limit(self):
        """Test concentration limit."""
        manager = RiskManager(
            position_limits=PositionLimits(max_concentration_percent=Decimal("20"))
        )
        portfolio = PortfolioState(equity=Decimal("100000"))
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("300"))

        # At $100, value is $30,000 = 30% of $100,000 equity
        result = manager.validate_order(order, portfolio, estimated_fill_price=Decimal("100"))
        assert result.passed is False
        assert any(v.rule_name == "max_concentration" for v in result.violations)

    def test_total_positions_limit(self):
        """Test total positions limit."""
        manager = RiskManager(
            position_limits=PositionLimits(max_total_positions=2)
        )
        portfolio = PortfolioState(
            positions={
                "AAPL": Position(
                    symbol="AAPL",
                    quantity=Decimal("100"),
                    side=PositionSide.LONG,
                    avg_entry_price=Decimal("100"),
                    current_price=Decimal("100"),
                    market_value=Decimal("10000"),
                    cost_basis=Decimal("10000"),
                    unrealized_pnl=Decimal("0"),
                    unrealized_pnl_percent=Decimal("0"),
                ),
                "MSFT": Position(
                    symbol="MSFT",
                    quantity=Decimal("100"),
                    side=PositionSide.LONG,
                    avg_entry_price=Decimal("100"),
                    current_price=Decimal("100"),
                    market_value=Decimal("10000"),
                    cost_basis=Decimal("10000"),
                    unrealized_pnl=Decimal("0"),
                    unrealized_pnl_percent=Decimal("0"),
                ),
            }
        )
        order = OrderRequest.market("GOOGL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_total_positions" for v in result.violations)


class TestRiskManagerLossLimits:
    """Test RiskManager loss limit checks."""

    def test_daily_loss_within_limit(self):
        """Test daily loss within limit passes."""
        manager = RiskManager(
            loss_limits=LossLimits(max_daily_loss=Decimal("1000"))
        )
        portfolio = PortfolioState(daily_pnl=Decimal("-500"))
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is True

    def test_daily_loss_exceeds_limit(self):
        """Test daily loss exceeding limit fails."""
        manager = RiskManager(
            loss_limits=LossLimits(max_daily_loss=Decimal("1000"))
        )
        portfolio = PortfolioState(daily_pnl=Decimal("-1500"))
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_daily_loss" for v in result.violations)

    def test_daily_loss_percent_limit(self):
        """Test daily loss percentage limit."""
        manager = RiskManager(
            loss_limits=LossLimits(max_daily_loss_percent=Decimal("5"))
        )
        portfolio = PortfolioState(
            equity=Decimal("100000"),
            daily_pnl=Decimal("-6000"),  # 6% loss
        )
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_daily_loss_percent" for v in result.violations)

    def test_drawdown_limit(self):
        """Test drawdown limit."""
        manager = RiskManager(
            loss_limits=LossLimits(max_drawdown=Decimal("15000"))
        )
        portfolio = PortfolioState(
            equity=Decimal("85000"),
            peak_equity=Decimal("100000"),  # 15k drawdown
        )
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        # Exactly at limit should pass
        result = manager.validate_order(order, portfolio)
        assert result.passed is True

        # Beyond limit should fail
        portfolio.equity = Decimal("80000")  # 20k drawdown
        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_drawdown" for v in result.violations)

    def test_drawdown_percent_limit(self):
        """Test drawdown percentage limit."""
        manager = RiskManager(
            loss_limits=LossLimits(max_drawdown_percent=Decimal("20"))
        )
        portfolio = PortfolioState(
            equity=Decimal("75000"),
            peak_equity=Decimal("100000"),  # 25% drawdown
        )
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_drawdown_percent" for v in result.violations)

    def test_consecutive_losses_limit(self):
        """Test consecutive losses limit."""
        manager = RiskManager(
            loss_limits=LossLimits(max_consecutive_losses=5)
        )
        portfolio = PortfolioState(consecutive_losses=5)
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "max_consecutive_losses" for v in result.violations)


class TestRiskManagerCoolingOff:
    """Test RiskManager cooling off period."""

    def test_cooling_off_triggered(self):
        """Test cooling off is triggered on loss limit."""
        manager = RiskManager(
            loss_limits=LossLimits(
                max_daily_loss=Decimal("1000"),
                cooling_off_period_minutes=30,
            )
        )
        portfolio = PortfolioState(daily_pnl=Decimal("-1500"))
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert manager._in_cooling_off is True

    def test_order_blocked_during_cooling_off(self):
        """Test orders blocked during cooling off."""
        manager = RiskManager(
            loss_limits=LossLimits(
                max_daily_loss=Decimal("1000"),
                cooling_off_period_minutes=30,
            )
        )
        # Trigger cooling off
        portfolio_loss = PortfolioState(daily_pnl=Decimal("-1500"))
        manager.validate_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100")),
            portfolio_loss,
        )

        # Try another order
        portfolio_ok = PortfolioState(daily_pnl=Decimal("0"))
        result = manager.validate_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100")),
            portfolio_ok,
        )

        assert result.passed is False
        assert any(v.rule_name == "cooling_off_period" for v in result.violations)

    def test_cooling_off_reset(self):
        """Test cooling off can be reset."""
        manager = RiskManager(
            loss_limits=LossLimits(
                max_daily_loss=Decimal("1000"),
                cooling_off_period_minutes=30,
            )
        )
        manager._in_cooling_off = True
        manager._cooling_off_until = datetime.now(timezone.utc)

        manager.reset_daily_limits()

        assert manager._in_cooling_off is False
        assert manager._cooling_off_until is None


class TestRiskManagerDisabled:
    """Test RiskManager when disabled."""

    def test_disabled_passes_all(self):
        """Test disabled manager passes all orders."""
        manager = RiskManager(
            position_limits=PositionLimits(max_position_size=Decimal("100")),
            enabled=False,
        )
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10000"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is True

    def test_enable_disable(self):
        """Test enabling and disabling."""
        manager = RiskManager()
        assert manager.enabled is True

        manager.enabled = False
        assert manager.enabled is False

        manager.enabled = True
        assert manager.enabled is True


class TestRiskManagerCustomRules:
    """Test RiskManager custom rules."""

    def test_custom_rule_passing(self):
        """Test custom rule that passes."""
        def custom_rule(order, portfolio):
            return None  # Pass

        manager = RiskManager(custom_rules=[custom_rule])
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is True
        assert "custom_rule_0" in result.checked_rules

    def test_custom_rule_failing(self):
        """Test custom rule that fails."""
        def custom_rule(order, portfolio):
            return RiskViolation(
                rule_type=RiskRuleType.CUSTOM,
                rule_name="custom_test",
                message="Custom rule failed",
                current_value=Decimal("0"),
                limit_value=Decimal("0"),
            )

        manager = RiskManager(custom_rules=[custom_rule])
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        result = manager.validate_order(order, portfolio)
        assert result.passed is False
        assert any(v.rule_name == "custom_test" for v in result.violations)

    def test_custom_rule_error_handled(self):
        """Test custom rule error doesn't break validation."""
        def bad_rule(order, portfolio):
            raise Exception("Rule error")

        manager = RiskManager(custom_rules=[bad_rule])
        portfolio = PortfolioState()
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))

        # Should not raise
        result = manager.validate_order(order, portfolio)
        assert result.passed is True

    def test_add_custom_rule(self):
        """Test adding custom rule after init."""
        manager = RiskManager()

        def custom_rule(order, portfolio):
            return None

        manager.add_custom_rule(custom_rule)
        assert len(manager._custom_rules) == 1


class TestRiskManagerTracking:
    """Test RiskManager tracking methods."""

    def test_update_daily_pnl(self):
        """Test updating daily P&L."""
        manager = RiskManager()
        today = date.today()

        manager.update_daily_pnl(Decimal("100"), today)
        assert manager.get_daily_pnl(today) == Decimal("100")

        manager.update_daily_pnl(Decimal("50"), today)
        assert manager.get_daily_pnl(today) == Decimal("150")

    def test_update_peak_equity(self):
        """Test updating peak equity."""
        manager = RiskManager()

        manager.update_peak_equity(Decimal("100000"))
        assert manager._peak_equity == Decimal("100000")

        # Higher should update
        manager.update_peak_equity(Decimal("110000"))
        assert manager._peak_equity == Decimal("110000")

        # Lower should not update
        manager.update_peak_equity(Decimal("105000"))
        assert manager._peak_equity == Decimal("110000")

    def test_reset_all(self):
        """Test resetting all state."""
        manager = RiskManager()
        manager.update_daily_pnl(Decimal("100"), date.today())
        manager.update_peak_equity(Decimal("100000"))
        manager._in_cooling_off = True

        manager.reset_all()

        assert manager.get_daily_pnl(date.today()) == Decimal("0")
        assert manager._peak_equity is None
        assert manager._in_cooling_off is False


class TestRiskManagerRuleChecking:
    """Test that all rules are checked."""

    def test_all_rules_checked(self):
        """Test all rules appear in checked list."""
        manager = RiskManager(
            position_limits=PositionLimits(
                max_position_size=Decimal("1000"),
                max_position_value=Decimal("50000"),
                max_concentration_percent=Decimal("20"),
                max_total_positions=10,
            ),
            loss_limits=LossLimits(
                max_daily_loss=Decimal("1000"),
                max_drawdown=Decimal("10000"),
                max_single_trade_loss=Decimal("500"),
                max_consecutive_losses=5,
            ),
        )
        portfolio = PortfolioState(equity=Decimal("100000"))
        order = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))

        result = manager.validate_order(order, portfolio, estimated_fill_price=Decimal("100"))

        expected_rules = [
            "position_size",
            "position_value",
            "concentration",
            "total_positions",
            "daily_loss",
            "drawdown",
            "single_trade_loss",
            "consecutive_losses",
        ]
        for rule in expected_rules:
            assert rule in result.checked_rules


class TestRiskRuleTypeEnum:
    """Test RiskRuleType enum."""

    def test_all_types_defined(self):
        """Test all expected types are defined."""
        expected = [
            "POSITION_SIZE",
            "POSITION_VALUE",
            "CONCENTRATION",
            "DAILY_LOSS",
            "DRAWDOWN",
            "CUSTOM",
        ]
        for type_name in expected:
            assert hasattr(RiskRuleType, type_name)


class TestRiskCheckResultEnum:
    """Test RiskCheckResult enum."""

    def test_all_results_defined(self):
        """Test all expected results are defined."""
        expected = ["PASSED", "FAILED", "WARNING", "SKIPPED"]
        for result_name in expected:
            assert hasattr(RiskCheckResult, result_name)
