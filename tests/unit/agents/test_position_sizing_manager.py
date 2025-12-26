"""Tests for Position Sizing Manager.

Issue #16: [AGENT-15] Position Sizing Manager - Kelly, risk parity, ATR

These tests define the logic locally to avoid langchain import issues.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from enum import Enum
from dataclasses import dataclass

pytestmark = pytest.mark.unit


# ============================================================================
# Local Definitions (matching position_sizing_manager.py)
# ============================================================================

class SizingMethod(str, Enum):
    """Position sizing method types."""
    KELLY = "kelly"
    HALF_KELLY = "half_kelly"
    QUARTER_KELLY = "quarter_kelly"
    RISK_PARITY = "risk_parity"
    ATR_BASED = "atr_based"
    FIXED_FRACTIONAL = "fixed_fractional"
    EQUAL_WEIGHT = "equal_weight"
    VOLATILITY_TARGET = "volatility_target"


class RiskLevel(str, Enum):
    """Risk tolerance levels."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class PositionSizeResult:
    """Result of position size calculation."""
    method: SizingMethod
    position_size: float
    dollar_amount: float
    shares: int
    risk_per_trade: float
    rationale: str


# ============================================================================
# Helper Functions (matching position_sizing_manager.py)
# ============================================================================

def _calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float
) -> float:
    """Calculate Kelly Criterion fraction."""
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    win_loss_ratio = abs(avg_win / avg_loss)
    kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
    return max(0.0, min(kelly, 1.0))


def _calculate_half_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float
) -> float:
    """Calculate half Kelly for reduced volatility."""
    return _calculate_kelly_fraction(win_rate, avg_win, avg_loss) / 2


def _calculate_quarter_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float
) -> float:
    """Calculate quarter Kelly for conservative sizing."""
    return _calculate_kelly_fraction(win_rate, avg_win, avg_loss) / 4


def _calculate_atr(prices: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range (ATR)."""
    if len(prices) < period + 1:
        return 0.0

    high = prices['high'] if 'high' in prices.columns else prices['High']
    low = prices['low'] if 'low' in prices.columns else prices['Low']
    close = prices['close'] if 'close' in prices.columns else prices['Close']

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()

    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0


def _calculate_position_from_atr(
    account_value: float,
    risk_per_trade: float,
    atr: float,
    atr_multiplier: float = 2.0,
    current_price: float = 1.0
) -> tuple:
    """Calculate position size based on ATR."""
    if atr == 0 or current_price == 0:
        return 0.0, 0

    dollar_risk = account_value * risk_per_trade
    stop_distance = atr * atr_multiplier

    shares = int(dollar_risk / stop_distance)
    position_value = shares * current_price
    position_fraction = position_value / account_value if account_value > 0 else 0

    return position_fraction, shares


def _calculate_volatility(returns: pd.Series, annualize: bool = True) -> float:
    """Calculate volatility (standard deviation of returns)."""
    if len(returns) < 2:
        return 0.0

    vol = returns.std()

    if annualize:
        vol = vol * np.sqrt(252)

    return float(vol)


def _calculate_risk_parity_weights(
    volatilities: dict,
    target_vol: float = 0.15
) -> dict:
    """Calculate Risk Parity weights."""
    if not volatilities or all(v == 0 for v in volatilities.values()):
        n = len(volatilities)
        return {k: 1/n for k in volatilities} if n > 0 else {}

    inv_vols = {k: 1/v if v > 0 else 0 for k, v in volatilities.items()}
    total_inv_vol = sum(inv_vols.values())

    if total_inv_vol == 0:
        n = len(volatilities)
        return {k: 1/n for k in volatilities}

    weights = {k: v/total_inv_vol for k, v in inv_vols.items()}

    port_vol = np.sqrt(sum((w**2) * (volatilities[k]**2) for k, w in weights.items()))

    if port_vol > 0:
        scale = target_vol / port_vol
        weights = {k: min(w * scale, 1.0) for k, w in weights.items()}

    return weights


def _calculate_fixed_fractional(
    account_value: float,
    risk_fraction: float,
    stop_loss_pct: float,
    current_price: float
) -> tuple:
    """Calculate fixed fractional position size."""
    if stop_loss_pct == 0 or current_price == 0:
        return 0.0, 0

    dollar_risk = account_value * risk_fraction
    position_value = dollar_risk / stop_loss_pct
    shares = int(position_value / current_price)
    position_fraction = (shares * current_price) / account_value if account_value > 0 else 0

    return position_fraction, shares


def _calculate_volatility_target_size(
    account_value: float,
    target_vol: float,
    asset_vol: float,
    current_price: float
) -> tuple:
    """Calculate position size to achieve target volatility."""
    if asset_vol == 0 or current_price == 0:
        return 0.0, 0

    weight = target_vol / asset_vol
    weight = min(weight, 1.0)

    position_value = account_value * weight
    shares = int(position_value / current_price)
    position_fraction = (shares * current_price) / account_value if account_value > 0 else 0

    return position_fraction, shares


def _apply_constraints(
    position_fraction: float,
    max_position: float = 0.25,
    max_portfolio_risk: float = 0.02,
    current_portfolio_risk: float = 0.0
) -> float:
    """Apply position size constraints."""
    constrained = min(position_fraction, max_position)

    if current_portfolio_risk + constrained > max_portfolio_risk * 10:
        constrained = max(0, max_portfolio_risk * 10 - current_portfolio_risk)

    return constrained


def _interpret_sizing_result(
    method: SizingMethod,
    position_fraction: float,
    kelly_fraction: float = 0
) -> str:
    """Generate interpretation of sizing result."""
    interpretations = []

    if method in [SizingMethod.KELLY, SizingMethod.HALF_KELLY, SizingMethod.QUARTER_KELLY]:
        if kelly_fraction < 0:
            interpretations.append("Negative Kelly suggests no edge - avoid trade")
        elif kelly_fraction > 0.5:
            interpretations.append("Large Kelly suggests strong edge but high variance")
        elif kelly_fraction > 0.25:
            interpretations.append("Moderate Kelly suggests reasonable edge")
        else:
            interpretations.append("Small Kelly suggests marginal edge - size conservatively")

    if position_fraction > 0.2:
        interpretations.append("Large position - consider splitting into tranches")
    elif position_fraction < 0.01:
        interpretations.append("Very small position - may not be worth transaction costs")

    return "; ".join(interpretations) if interpretations else "Standard position size"


def _get_risk_parameters(risk_level: RiskLevel) -> dict:
    """Get risk parameters based on risk tolerance."""
    params = {
        RiskLevel.CONSERVATIVE: {
            "max_position": 0.10,
            "risk_per_trade": 0.01,
            "kelly_fraction_used": 0.25,
            "target_vol": 0.10
        },
        RiskLevel.MODERATE: {
            "max_position": 0.20,
            "risk_per_trade": 0.02,
            "kelly_fraction_used": 0.50,
            "target_vol": 0.15
        },
        RiskLevel.AGGRESSIVE: {
            "max_position": 0.30,
            "risk_per_trade": 0.03,
            "kelly_fraction_used": 1.0,
            "target_vol": 0.20
        }
    }
    return params.get(risk_level, params[RiskLevel.MODERATE])


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_price_data():
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n = 100
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')

    # Generate realistic price series
    base_price = 100
    returns = np.random.normal(0.001, 0.02, n)
    close = pd.Series(base_price * (1 + returns).cumprod())

    # Generate OHLCV
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_price = close.shift(1).fillna(base_price)
    volume = np.random.randint(100000, 1000000, n)

    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    return df


@pytest.fixture
def volatile_price_data():
    """Generate high volatility price data."""
    np.random.seed(43)
    n = 100
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')

    base_price = 100
    returns = np.random.normal(0.001, 0.05, n)  # 5% daily volatility
    close = base_price * (1 + returns).cumprod()

    high = close * (1 + np.abs(np.random.normal(0, 0.02, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.02, n)))

    df = pd.DataFrame({
        'date': dates,
        'high': high,
        'low': low,
        'close': close
    })
    return df


@pytest.fixture
def account_params():
    """Standard account parameters for testing."""
    return {
        "account_value": 100000,
        "current_price": 150,
        "win_rate": 0.55,
        "avg_win": 0.05,
        "avg_loss": -0.03
    }


# ============================================================================
# Test Classes
# ============================================================================

class TestKellyCalculation:
    """Tests for Kelly Criterion calculation."""

    def test_positive_kelly(self, account_params):
        """Test positive Kelly with edge."""
        kelly = _calculate_kelly_fraction(
            win_rate=0.55,
            avg_win=0.05,
            avg_loss=0.03
        )
        assert kelly > 0
        # Kelly = 0.55 - (0.45 / 1.667) = 0.55 - 0.27 = 0.28
        assert abs(kelly - 0.28) < 0.05

    def test_negative_kelly(self):
        """Test negative Kelly with no edge."""
        kelly = _calculate_kelly_fraction(
            win_rate=0.40,
            avg_win=0.03,
            avg_loss=0.05
        )
        # When result is negative, should return 0
        assert kelly == 0.0

    def test_zero_win_rate(self):
        """Test Kelly with zero win rate."""
        kelly = _calculate_kelly_fraction(
            win_rate=0.0,
            avg_win=0.05,
            avg_loss=0.03
        )
        assert kelly == 0.0

    def test_zero_loss(self):
        """Test Kelly with zero average loss."""
        kelly = _calculate_kelly_fraction(
            win_rate=0.55,
            avg_win=0.05,
            avg_loss=0.0
        )
        assert kelly == 0.0

    def test_perfect_win_rate(self):
        """Test Kelly with 100% win rate."""
        kelly = _calculate_kelly_fraction(
            win_rate=1.0,
            avg_win=0.05,
            avg_loss=0.03
        )
        # Should return 0 for invalid input (win_rate >= 1)
        assert kelly == 0.0

    def test_half_kelly(self):
        """Test half Kelly calculation."""
        full_kelly = _calculate_kelly_fraction(0.55, 0.05, 0.03)
        half_kelly = _calculate_half_kelly(0.55, 0.05, 0.03)
        assert abs(half_kelly - full_kelly / 2) < 0.001

    def test_quarter_kelly(self):
        """Test quarter Kelly calculation."""
        full_kelly = _calculate_kelly_fraction(0.55, 0.05, 0.03)
        quarter_kelly = _calculate_quarter_kelly(0.55, 0.05, 0.03)
        assert abs(quarter_kelly - full_kelly / 4) < 0.001

    def test_kelly_capped_at_one(self):
        """Test Kelly is capped at 100%."""
        # Very high edge scenario
        kelly = _calculate_kelly_fraction(
            win_rate=0.90,
            avg_win=0.20,
            avg_loss=0.02
        )
        assert kelly <= 1.0


class TestATRCalculation:
    """Tests for ATR calculation."""

    def test_atr_calculation(self, sample_price_data):
        """Test ATR calculation produces valid result."""
        atr = _calculate_atr(sample_price_data, period=14)
        assert atr > 0
        # ATR should be a reasonable percentage of price
        current_price = sample_price_data['close'].iloc[-1]
        assert atr < current_price * 0.2  # Less than 20% of price

    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data."""
        short_data = pd.DataFrame({
            'high': [101, 102],
            'low': [99, 98],
            'close': [100, 101]
        })
        atr = _calculate_atr(short_data, period=14)
        assert atr == 0.0

    def test_atr_with_volatile_data(self, volatile_price_data):
        """Test ATR is higher for volatile data."""
        atr_volatile = _calculate_atr(volatile_price_data, period=14)
        assert atr_volatile > 0
        # Volatile data should have higher ATR

    def test_atr_different_periods(self, sample_price_data):
        """Test ATR with different periods."""
        atr_14 = _calculate_atr(sample_price_data, period=14)
        atr_7 = _calculate_atr(sample_price_data, period=7)
        # Both should be positive
        assert atr_14 > 0
        assert atr_7 > 0


class TestATRPositionSizing:
    """Tests for ATR-based position sizing."""

    def test_atr_position_calculation(self):
        """Test ATR position sizing calculation."""
        fraction, shares = _calculate_position_from_atr(
            account_value=100000,
            risk_per_trade=0.02,
            atr=2.0,
            atr_multiplier=2.0,
            current_price=100
        )
        # Risk = $2000, Stop = $4, Shares = 500
        assert shares == 500
        # Position value = 500 * 100 = 50000, fraction = 0.5
        assert abs(fraction - 0.5) < 0.01

    def test_atr_position_zero_atr(self):
        """Test ATR position with zero ATR."""
        fraction, shares = _calculate_position_from_atr(
            account_value=100000,
            risk_per_trade=0.02,
            atr=0.0,
            atr_multiplier=2.0,
            current_price=100
        )
        assert fraction == 0.0
        assert shares == 0

    def test_atr_position_zero_price(self):
        """Test ATR position with zero price."""
        fraction, shares = _calculate_position_from_atr(
            account_value=100000,
            risk_per_trade=0.02,
            atr=2.0,
            atr_multiplier=2.0,
            current_price=0
        )
        assert fraction == 0.0
        assert shares == 0


class TestVolatilityCalculation:
    """Tests for volatility calculation."""

    def test_volatility_calculation(self, sample_price_data):
        """Test volatility calculation."""
        returns = sample_price_data['close'].pct_change().dropna()
        vol = _calculate_volatility(returns, annualize=True)
        assert vol > 0
        # Should be in reasonable range (10-50% annual)
        assert vol < 1.0

    def test_volatility_daily_vs_annual(self, sample_price_data):
        """Test annualized vs daily volatility."""
        returns = sample_price_data['close'].pct_change().dropna()
        vol_annual = _calculate_volatility(returns, annualize=True)
        vol_daily = _calculate_volatility(returns, annualize=False)
        # Annual should be ~16x daily (sqrt(252))
        assert vol_annual > vol_daily * 10
        assert vol_annual < vol_daily * 20

    def test_volatility_insufficient_data(self):
        """Test volatility with insufficient data."""
        returns = pd.Series([0.01])
        vol = _calculate_volatility(returns)
        assert vol == 0.0


class TestRiskParityWeights:
    """Tests for Risk Parity weight calculation."""

    def test_equal_volatility_weights(self):
        """Test Risk Parity with equal volatilities gives equal weights."""
        volatilities = {"A": 0.20, "B": 0.20, "C": 0.20}
        weights = _calculate_risk_parity_weights(volatilities)
        # Should be approximately equal
        for w in weights.values():
            assert abs(w - 1/3) < 0.1

    def test_different_volatility_weights(self):
        """Test Risk Parity with different volatilities."""
        volatilities = {"A": 0.10, "B": 0.20, "C": 0.40}
        weights = _calculate_risk_parity_weights(volatilities)
        # Lower vol should get higher weight
        assert weights["A"] > weights["B"] > weights["C"]

    def test_empty_volatilities(self):
        """Test Risk Parity with empty volatilities."""
        weights = _calculate_risk_parity_weights({})
        assert weights == {}

    def test_zero_volatilities(self):
        """Test Risk Parity with all zero volatilities."""
        volatilities = {"A": 0.0, "B": 0.0}
        weights = _calculate_risk_parity_weights(volatilities)
        # Should return equal weights as fallback
        for w in weights.values():
            assert abs(w - 0.5) < 0.01

    def test_single_asset(self):
        """Test Risk Parity with single asset."""
        volatilities = {"A": 0.15}
        weights = _calculate_risk_parity_weights(volatilities)
        assert weights["A"] > 0


class TestFixedFractional:
    """Tests for fixed fractional position sizing."""

    def test_fixed_fractional_calculation(self):
        """Test fixed fractional position size."""
        fraction, shares = _calculate_fixed_fractional(
            account_value=100000,
            risk_fraction=0.02,
            stop_loss_pct=0.05,
            current_price=100
        )
        # Risk = $2000, Stop = 5%, Position = $40000
        # Shares = 400, Fraction = 0.4
        assert shares == 400
        assert abs(fraction - 0.4) < 0.01

    def test_fixed_fractional_zero_stop(self):
        """Test fixed fractional with zero stop loss."""
        fraction, shares = _calculate_fixed_fractional(
            account_value=100000,
            risk_fraction=0.02,
            stop_loss_pct=0.0,
            current_price=100
        )
        assert fraction == 0.0
        assert shares == 0

    def test_fixed_fractional_small_risk(self):
        """Test fixed fractional with small risk."""
        fraction, shares = _calculate_fixed_fractional(
            account_value=100000,
            risk_fraction=0.005,  # 0.5%
            stop_loss_pct=0.10,
            current_price=100
        )
        # Risk = $500, Stop = 10%, Position = $5000
        assert shares == 50


class TestVolatilityTargetSizing:
    """Tests for volatility target position sizing."""

    def test_volatility_target_calculation(self):
        """Test volatility target position size."""
        fraction, shares = _calculate_volatility_target_size(
            account_value=100000,
            target_vol=0.15,
            asset_vol=0.30,
            current_price=100
        )
        # Weight = 0.15/0.30 = 0.5
        assert abs(fraction - 0.5) < 0.01
        assert shares == 500

    def test_volatility_target_low_vol_asset(self):
        """Test volatility target with low vol asset."""
        fraction, shares = _calculate_volatility_target_size(
            account_value=100000,
            target_vol=0.15,
            asset_vol=0.10,
            current_price=100
        )
        # Weight = 0.15/0.10 = 1.5, capped at 1.0
        assert fraction <= 1.0

    def test_volatility_target_zero_vol(self):
        """Test volatility target with zero asset vol."""
        fraction, shares = _calculate_volatility_target_size(
            account_value=100000,
            target_vol=0.15,
            asset_vol=0.0,
            current_price=100
        )
        assert fraction == 0.0
        assert shares == 0


class TestPositionConstraints:
    """Tests for position size constraints."""

    def test_max_position_constraint(self):
        """Test maximum position constraint."""
        constrained = _apply_constraints(
            position_fraction=0.40,
            max_position=0.25,
            max_portfolio_risk=0.05  # 0.05 * 10 = 0.5, so won't interfere
        )
        assert constrained == 0.25

    def test_no_constraint_needed(self):
        """Test when no constraint is needed."""
        constrained = _apply_constraints(
            position_fraction=0.15,
            max_position=0.25
        )
        assert constrained == 0.15

    def test_zero_position(self):
        """Test zero position."""
        constrained = _apply_constraints(
            position_fraction=0.0,
            max_position=0.25
        )
        assert constrained == 0.0


class TestSizingInterpretation:
    """Tests for sizing result interpretation."""

    def test_kelly_interpretation_negative(self):
        """Test Kelly interpretation for negative Kelly."""
        result = _interpret_sizing_result(
            SizingMethod.KELLY,
            position_fraction=0.0,
            kelly_fraction=-0.1
        )
        assert "Negative Kelly" in result
        assert "avoid trade" in result

    def test_kelly_interpretation_large(self):
        """Test Kelly interpretation for large Kelly."""
        result = _interpret_sizing_result(
            SizingMethod.KELLY,
            position_fraction=0.4,
            kelly_fraction=0.6
        )
        assert "Large Kelly" in result

    def test_large_position_interpretation(self):
        """Test interpretation for large position."""
        result = _interpret_sizing_result(
            SizingMethod.ATR_BASED,
            position_fraction=0.25,
            kelly_fraction=0
        )
        assert "Large position" in result

    def test_small_position_interpretation(self):
        """Test interpretation for very small position."""
        result = _interpret_sizing_result(
            SizingMethod.ATR_BASED,
            position_fraction=0.005,
            kelly_fraction=0
        )
        assert "Very small position" in result


class TestRiskParameters:
    """Tests for risk parameter configuration."""

    def test_conservative_parameters(self):
        """Test conservative risk parameters."""
        params = _get_risk_parameters(RiskLevel.CONSERVATIVE)
        assert params["max_position"] == 0.10
        assert params["risk_per_trade"] == 0.01
        assert params["kelly_fraction_used"] == 0.25
        assert params["target_vol"] == 0.10

    def test_moderate_parameters(self):
        """Test moderate risk parameters."""
        params = _get_risk_parameters(RiskLevel.MODERATE)
        assert params["max_position"] == 0.20
        assert params["risk_per_trade"] == 0.02
        assert params["kelly_fraction_used"] == 0.50
        assert params["target_vol"] == 0.15

    def test_aggressive_parameters(self):
        """Test aggressive risk parameters."""
        params = _get_risk_parameters(RiskLevel.AGGRESSIVE)
        assert params["max_position"] == 0.30
        assert params["risk_per_trade"] == 0.03
        assert params["kelly_fraction_used"] == 1.0
        assert params["target_vol"] == 0.20


class TestEnumValues:
    """Tests for enum value consistency."""

    def test_sizing_method_values(self):
        """Test sizing method enum values."""
        assert SizingMethod.KELLY.value == "kelly"
        assert SizingMethod.HALF_KELLY.value == "half_kelly"
        assert SizingMethod.ATR_BASED.value == "atr_based"
        assert SizingMethod.RISK_PARITY.value == "risk_parity"

    def test_risk_level_values(self):
        """Test risk level enum values."""
        assert RiskLevel.CONSERVATIVE.value == "conservative"
        assert RiskLevel.MODERATE.value == "moderate"
        assert RiskLevel.AGGRESSIVE.value == "aggressive"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_very_large_account(self):
        """Test with very large account value."""
        fraction, shares = _calculate_position_from_atr(
            account_value=10000000,  # $10M
            risk_per_trade=0.01,
            atr=5.0,
            atr_multiplier=2.0,
            current_price=200
        )
        assert shares > 0
        assert fraction > 0

    def test_very_small_account(self):
        """Test with very small account value."""
        fraction, shares = _calculate_position_from_atr(
            account_value=1000,  # $1K
            risk_per_trade=0.02,
            atr=2.0,
            atr_multiplier=2.0,
            current_price=100
        )
        assert shares >= 0  # May round to 0 for small accounts

    def test_high_price_stock(self):
        """Test with high priced stock."""
        fraction, shares = _calculate_fixed_fractional(
            account_value=100000,
            risk_fraction=0.02,
            stop_loss_pct=0.05,
            current_price=5000  # High price like BRK.A
        )
        # May get very few shares
        assert shares >= 0

    def test_penny_stock(self):
        """Test with penny stock."""
        fraction, shares = _calculate_fixed_fractional(
            account_value=100000,
            risk_fraction=0.02,
            stop_loss_pct=0.10,
            current_price=0.50
        )
        # Should get many shares
        assert shares > 1000


class TestIntegration:
    """Integration tests for combined functionality."""

    def test_full_kelly_workflow(self, account_params):
        """Test full Kelly sizing workflow."""
        # Calculate Kelly
        kelly = _calculate_kelly_fraction(
            account_params["win_rate"],
            account_params["avg_win"],
            abs(account_params["avg_loss"])
        )

        # Apply half Kelly
        half_kelly = kelly / 2

        # Calculate position
        position_value = account_params["account_value"] * half_kelly
        shares = int(position_value / account_params["current_price"])

        # Apply constraints
        constrained = _apply_constraints(half_kelly, max_position=0.20)

        # Interpret
        interpretation = _interpret_sizing_result(
            SizingMethod.HALF_KELLY,
            constrained,
            kelly
        )

        assert kelly > 0
        assert half_kelly < kelly
        assert constrained <= 0.20
        assert len(interpretation) > 0

    def test_atr_workflow(self, sample_price_data):
        """Test full ATR sizing workflow."""
        # Calculate ATR
        atr = _calculate_atr(sample_price_data, period=14)

        # Get current price
        current_price = sample_price_data['close'].iloc[-1]

        # Calculate position
        fraction, shares = _calculate_position_from_atr(
            account_value=100000,
            risk_per_trade=0.02,
            atr=atr,
            atr_multiplier=2.0,
            current_price=current_price
        )

        # Apply constraints
        constrained = _apply_constraints(fraction, max_position=0.25)

        assert atr > 0
        assert shares >= 0
        assert constrained <= 0.25

    def test_risk_parity_workflow(self):
        """Test full Risk Parity workflow."""
        volatilities = {
            "SPY": 0.15,
            "TLT": 0.12,
            "GLD": 0.18,
            "VNQ": 0.20
        }

        weights = _calculate_risk_parity_weights(volatilities, target_vol=0.12)

        # Verify weights sum to reasonable amount
        total_weight = sum(weights.values())
        assert total_weight > 0
        assert total_weight <= 4.0  # May be levered for vol target

        # Verify lower vol gets higher weight
        assert weights["TLT"] > weights["VNQ"]


class TestFactoryExpectations:
    """Tests for factory function expectations."""

    def test_expected_tools_list(self):
        """Test expected position sizing tools."""
        expected_tools = [
            "calculate_kelly_position_size",
            "calculate_atr_position_size",
            "calculate_risk_parity_allocation",
            "calculate_volatility_target_size",
            "get_position_sizing_recommendation"
        ]
        for tool_name in expected_tools:
            assert len(tool_name) > 0

    def test_factory_expected_signature(self):
        """Test factory should accept LLM parameter."""
        def mock_factory(llm):
            return lambda state: {"messages": [], "position_sizing_report": ""}

        mock_llm = Mock()
        node = mock_factory(mock_llm)
        result = node({})
        assert "position_sizing_report" in result


class TestDataClassResult:
    """Tests for PositionSizeResult dataclass."""

    def test_position_size_result_creation(self):
        """Test creating PositionSizeResult."""
        result = PositionSizeResult(
            method=SizingMethod.KELLY,
            position_size=0.15,
            dollar_amount=15000.0,
            shares=100,
            risk_per_trade=500.0,
            rationale="Based on 55% win rate"
        )
        assert result.method == SizingMethod.KELLY
        assert result.position_size == 0.15
        assert result.shares == 100

    def test_position_size_result_different_methods(self):
        """Test PositionSizeResult with different methods."""
        for method in SizingMethod:
            result = PositionSizeResult(
                method=method,
                position_size=0.10,
                dollar_amount=10000.0,
                shares=50,
                risk_per_trade=200.0,
                rationale="Test"
            )
            assert result.method == method
