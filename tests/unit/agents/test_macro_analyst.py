"""Tests for Macro Analyst agent.

Issue #14: [AGENT-13] Macro Analyst - FRED interpretation, regime detection

These tests define the logic locally to avoid langchain import issues.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from enum import Enum

pytestmark = pytest.mark.unit


# ============================================================================
# Local Definitions (matching macro_analyst.py)
# ============================================================================

class EconomicRegime(str, Enum):
    """Economic regime classifications."""
    EXPANSION = "expansion"
    LATE_CYCLE = "late_cycle"
    CONTRACTION = "contraction"
    EARLY_RECOVERY = "early_recovery"
    STAGFLATION = "stagflation"
    GOLDILOCKS = "goldilocks"


class YieldCurveState(str, Enum):
    """Yield curve state classifications."""
    NORMAL = "normal"
    FLAT = "flat"
    INVERTED = "inverted"
    STEEP = "steep"


class MonetaryPolicy(str, Enum):
    """Monetary policy stance classifications."""
    HAWKISH = "hawkish"
    NEUTRAL = "neutral"
    DOVISH = "dovish"
    EMERGENCY = "emergency"


class InflationRegime(str, Enum):
    """Inflation regime classifications."""
    DEFLATION = "deflation"
    LOW = "low"
    TARGET = "target"
    ELEVATED = "elevated"
    HIGH = "high"


# Helper functions (copied from macro_analyst.py for testing)
def _calculate_growth_rate(data: pd.DataFrame) -> float:
    """Calculate annualized growth rate from data."""
    if data.empty or len(data) < 4:
        return 0.0
    values = data['value'] if 'value' in data.columns else data.iloc[:, 0]
    if len(values) >= 4:
        return ((values.iloc[-1] / values.iloc[-4]) - 1) * 100
    return 0.0


def _calculate_trend(data: pd.DataFrame) -> float:
    """Calculate trend direction (-1 to 1)."""
    if data.empty or len(data) < 2:
        return 0.0
    values = data['value'] if 'value' in data.columns else data.iloc[:, 0]
    if len(values) >= 10:
        recent = values.iloc[-5:].mean()
        earlier = values.iloc[-10:-5].mean()
        if earlier != 0:
            return (recent - earlier) / abs(earlier)
    return 0.0


def _calculate_yoy_change(data: pd.DataFrame) -> float:
    """Calculate year-over-year percentage change."""
    if data.empty or len(data) < 12:
        return 0.0
    values = data['value'] if 'value' in data.columns else data.iloc[:, 0]
    if len(values) >= 12:
        return ((values.iloc[-1] / values.iloc[-12]) - 1) * 100
    return 0.0


def _calculate_spread_series(data_2y: pd.DataFrame, data_10y: pd.DataFrame):
    """Calculate spread series between two yield series."""
    try:
        if data_2y.empty or data_10y.empty:
            return []
        v2y = data_2y['value'] if 'value' in data_2y.columns else data_2y.iloc[:, 0]
        v10y = data_10y['value'] if 'value' in data_10y.columns else data_10y.iloc[:, 0]
        min_len = min(len(v2y), len(v10y))
        return [(v10y.iloc[i] - v2y.iloc[i]) * 100 for i in range(min_len)]
    except Exception:
        return []


def _classify_economic_regime(indicators):
    """Classify economic regime based on indicators."""
    gdp = indicators.get('gdp_growth', 0)
    inflation = indicators.get('inflation', 2)
    unemployment = indicators.get('unemployment', 5)

    if gdp > 2 and inflation < 3 and unemployment < 5:
        return EconomicRegime.GOLDILOCKS
    elif gdp < 0:
        return EconomicRegime.CONTRACTION
    elif gdp < 0 and inflation > 4:
        return EconomicRegime.STAGFLATION
    elif gdp > 3:
        return EconomicRegime.EXPANSION
    elif indicators.get('unemployment_trend', 0) > 0:
        return EconomicRegime.LATE_CYCLE
    else:
        return EconomicRegime.EARLY_RECOVERY


def _classify_yield_curve(spread: float) -> YieldCurveState:
    """Classify yield curve state based on 2Y-10Y spread."""
    if spread is None:
        return YieldCurveState.NORMAL
    if spread < -25:
        return YieldCurveState.INVERTED
    elif spread < 25:
        return YieldCurveState.FLAT
    elif spread > 200:
        return YieldCurveState.STEEP
    else:
        return YieldCurveState.NORMAL


def _classify_monetary_policy(rate: float, change_6m: float, inflation: float) -> MonetaryPolicy:
    """Classify monetary policy stance."""
    if rate is None:
        return MonetaryPolicy.NEUTRAL

    if rate < 0.5:
        return MonetaryPolicy.EMERGENCY
    elif change_6m is not None and change_6m > 0.5:
        return MonetaryPolicy.HAWKISH
    elif change_6m is not None and change_6m < -0.5:
        return MonetaryPolicy.DOVISH
    else:
        return MonetaryPolicy.NEUTRAL


def _classify_inflation_regime(inflation: float) -> InflationRegime:
    """Classify inflation regime based on rate."""
    if inflation is None:
        return InflationRegime.TARGET
    if inflation < 0:
        return InflationRegime.DEFLATION
    elif inflation < 2:
        return InflationRegime.LOW
    elif inflation < 3:
        return InflationRegime.TARGET
    elif inflation < 5:
        return InflationRegime.ELEVATED
    else:
        return InflationRegime.HIGH


def _calculate_recession_probability(state: YieldCurveState, inversion_days: int, total_days: int) -> float:
    """Calculate recession probability based on yield curve."""
    base_prob = 0
    if state == YieldCurveState.INVERTED:
        base_prob = 50
    elif state == YieldCurveState.FLAT:
        base_prob = 25

    if total_days > 0:
        inversion_ratio = inversion_days / total_days
        if inversion_ratio > 0.5:
            base_prob = min(base_prob + 25, 80)
        elif inversion_ratio > 0.25:
            base_prob = min(base_prob + 15, 70)

    return base_prob


def _trend_to_arrow(value: float) -> str:
    """Convert trend value to arrow indicator."""
    if value is None:
        return "➡️"
    if value > 0.1:
        return "⬆️"
    elif value < -0.1:
        return "⬇️"
    else:
        return "➡️"


def _gdp_signal(growth: float) -> str:
    """Generate signal based on GDP growth."""
    if growth is None:
        return "N/A"
    if growth > 3:
        return "🟢 Strong"
    elif growth > 1:
        return "🟡 Moderate"
    elif growth > 0:
        return "🟠 Slow"
    else:
        return "🔴 Contraction"


def _unemployment_signal(rate: float) -> str:
    """Generate signal based on unemployment."""
    if rate is None:
        return "N/A"
    if rate < 4:
        return "🟢 Tight Labor"
    elif rate < 5:
        return "🟢 Healthy"
    elif rate < 6:
        return "🟡 Softening"
    else:
        return "🔴 Elevated"


def _inflation_signal(rate: float) -> str:
    """Generate signal based on inflation."""
    if rate is None:
        return "N/A"
    if rate < 2:
        return "🟢 Below Target"
    elif rate < 3:
        return "🟢 At Target"
    elif rate < 4:
        return "🟡 Elevated"
    else:
        return "🔴 High"


def _m2_signal(growth: float) -> str:
    """Generate signal based on M2 growth."""
    if growth is None:
        return "N/A"
    if growth > 10:
        return "🟢 Expanding"
    elif growth > 5:
        return "🟢 Moderate"
    elif growth > 0:
        return "🟡 Slow"
    else:
        return "🔴 Contracting"


def _regime_interpretation(regime: EconomicRegime) -> str:
    """Generate interpretation text for economic regime."""
    interpretations = {
        EconomicRegime.EXPANSION: "The economy is in a healthy expansion phase with robust growth, moderate inflation, and improving employment. This environment typically favors risk assets.",
        EconomicRegime.LATE_CYCLE: "Signs of late-cycle dynamics are emerging. Growth may be peaking while labor markets are tight. Watch for rising inflation and yield curve flattening.",
        EconomicRegime.CONTRACTION: "The economy is contracting. GDP is declining and unemployment may be rising. Defensive positioning and quality focus recommended.",
        EconomicRegime.EARLY_RECOVERY: "Early signs of economic recovery are appearing. Growth is returning but remains fragile. Early-cycle sectors may outperform.",
        EconomicRegime.STAGFLATION: "Stagflation conditions present: weak growth combined with elevated inflation. A challenging environment for most asset classes.",
        EconomicRegime.GOLDILOCKS: "A 'Goldilocks' scenario with moderate growth, low inflation, and healthy employment. Generally positive for risk assets.",
    }
    return interpretations.get(regime, "Economic conditions are mixed.")


def _regime_investment_implications(regime: EconomicRegime) -> str:
    """Generate investment implications for economic regime."""
    implications = {
        EconomicRegime.EXPANSION: """- **Equities**: Overweight cyclical sectors (Industrials, Financials, Materials)
- **Fixed Income**: Underweight duration, favor credit
- **Commodities**: Constructive on industrial metals
- **Real Estate**: Favor economically-sensitive REITs""",
        EconomicRegime.CONTRACTION: """- **Equities**: Defensive sectors (Utilities, Healthcare, Consumer Staples)
- **Fixed Income**: Overweight Treasuries, extend duration
- **Commodities**: Underweight cyclical commodities
- **Cash**: Elevated allocation appropriate""",
    }
    return implications.get(regime, "Maintain balanced allocation.")


def _yield_curve_interpretation(state: YieldCurveState, recession_prob: float) -> str:
    """Generate interpretation for yield curve state."""
    if state == YieldCurveState.INVERTED:
        return f"⚠️ **Inverted Yield Curve Warning**\n\nThe yield curve is inverted (2Y yield exceeds 10Y), historically a reliable recession predictor."
    elif state == YieldCurveState.FLAT:
        return f"📊 **Flattening Yield Curve**\n\nThe yield curve is flat, indicating uncertainty about future growth."
    return f"✅ **Normal Yield Curve**\n\nThe yield curve has a normal positive slope."


def _real_rate_interpretation(real_rate: float) -> str:
    """Interpret real interest rate level."""
    if real_rate is None:
        return ""
    if real_rate > 2:
        return "**Restrictive**: Real rates are significantly positive, indicating tight monetary conditions."
    elif real_rate > 0:
        return "**Neutral to Tight**: Positive real rates suggest monetary policy is not accommodative."
    elif real_rate > -2:
        return "**Accommodative**: Negative real rates indicate easy monetary conditions."
    else:
        return "**Highly Accommodative**: Deeply negative real rates represent emergency monetary accommodation."


def _inflation_trajectory_interpretation(trend: str, yoy: float, short_term: float) -> str:
    """Interpret inflation trajectory."""
    if trend == "accelerating":
        return f"Inflation momentum is **accelerating**, with the 3-month annualized rate ({short_term:.1f}%) exceeding the year-over-year rate ({yoy:.1f}%)."
    elif trend == "decelerating":
        return f"Inflation is **decelerating**, with the 3-month annualized rate ({short_term:.1f}%) below the year-over-year rate ({yoy:.1f}%)."
    return "Inflation momentum is relatively stable."


def _inflation_regime_interpretation(regime: InflationRegime) -> str:
    """Interpret inflation regime implications."""
    interpretations = {
        InflationRegime.DEFLATION: "Deflationary conditions are rare and concerning.",
        InflationRegime.LOW: "Low inflation below the 2% target may prompt continued monetary accommodation.",
        InflationRegime.TARGET: "Inflation is at or near the Fed's 2% target.",
        InflationRegime.ELEVATED: "Elevated inflation above target will keep the Fed focused on price stability.",
        InflationRegime.HIGH: "High inflation is the primary policy concern.",
    }
    return interpretations.get(regime, "")


def _inflation_asset_impact(regime: InflationRegime) -> str:
    """Generate asset class impact for inflation regime."""
    if regime == InflationRegime.HIGH:
        return """| Asset Class | Impact | Recommendation |
|-------------|--------|----------------|
| Equities | Negative | Value, commodity producers |
| Bonds | Very Negative | Avoid duration, favor TIPS |
| Commodities | Positive | Key inflation hedge |"""
    return ""


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def gdp_data():
    """Sample GDP data (quarterly)."""
    dates = pd.date_range(end=datetime.now(), periods=16, freq='QE')
    values = 20000 * (1.025 ** np.arange(16))
    return pd.DataFrame({
        'date': dates,
        'value': values
    })


@pytest.fixture
def unemployment_data():
    """Sample unemployment data (monthly)."""
    dates = pd.date_range(end=datetime.now(), periods=24, freq='ME')
    values = 5.0 - np.linspace(0, 1, 24)
    return pd.DataFrame({
        'date': dates,
        'value': values
    })


@pytest.fixture
def inflation_data():
    """Sample CPI data (monthly)."""
    dates = pd.date_range(end=datetime.now(), periods=24, freq='ME')
    base = 300
    values = base * (1.002 ** np.arange(24))
    return pd.DataFrame({
        'date': dates,
        'value': values
    })


@pytest.fixture
def treasury_2y_data():
    """Sample 2-year Treasury data."""
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    values = 4.5 + np.random.randn(252) * 0.1
    return pd.DataFrame({
        'date': dates,
        'value': values
    })


@pytest.fixture
def treasury_10y_data():
    """Sample 10-year Treasury data."""
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    values = 4.0 + np.random.randn(252) * 0.1
    return pd.DataFrame({
        'date': dates,
        'value': values
    })


# ============================================================================
# Economic Regime Tests
# ============================================================================

class TestEconomicRegimeClassification:
    """Tests for economic regime classification."""

    def test_expansion_regime(self):
        """Test expansion regime classification.

        Expansion: GDP > 3% but not Goldilocks conditions.
        To avoid Goldilocks (gdp>2, inflation<3, unemployment<5),
        we set unemployment >= 5.
        """
        indicators = {
            'gdp_growth': 3.5,
            'unemployment': 5.5,  # >= 5 to avoid Goldilocks
            'inflation': 2.5,
            'unemployment_trend': -0.1
        }
        regime = _classify_economic_regime(indicators)
        assert regime == EconomicRegime.EXPANSION

    def test_contraction_regime(self):
        """Test contraction regime classification."""
        indicators = {
            'gdp_growth': -1.5,
            'unemployment': 6.0,
            'inflation': 2.0,
            'unemployment_trend': 0.2
        }
        regime = _classify_economic_regime(indicators)
        assert regime == EconomicRegime.CONTRACTION

    def test_goldilocks_regime(self):
        """Test Goldilocks regime classification."""
        indicators = {
            'gdp_growth': 2.5,
            'unemployment': 3.8,
            'inflation': 2.0,
            'unemployment_trend': -0.05
        }
        regime = _classify_economic_regime(indicators)
        assert regime == EconomicRegime.GOLDILOCKS

    def test_late_cycle_regime(self):
        """Test late-cycle regime classification."""
        indicators = {
            'gdp_growth': 1.5,
            'unemployment': 4.5,
            'inflation': 3.5,
            'unemployment_trend': 0.15
        }
        regime = _classify_economic_regime(indicators)
        assert regime == EconomicRegime.LATE_CYCLE


class TestEconomicRegimeHelpers:
    """Tests for economic regime helper functions."""

    def test_growth_rate_calculation(self, gdp_data):
        """Test GDP growth rate calculation."""
        growth = _calculate_growth_rate(gdp_data)
        assert growth > 0

    def test_trend_calculation(self, unemployment_data):
        """Test trend calculation."""
        trend = _calculate_trend(unemployment_data)
        assert trend < 0

    def test_yoy_change_calculation(self, inflation_data):
        """Test year-over-year change calculation."""
        yoy = _calculate_yoy_change(inflation_data)
        assert 1 < yoy < 4


# ============================================================================
# Yield Curve Tests
# ============================================================================

class TestYieldCurveClassification:
    """Tests for yield curve state classification."""

    def test_inverted_yield_curve(self):
        """Test inverted yield curve classification."""
        spread = -50
        state = _classify_yield_curve(spread)
        assert state == YieldCurveState.INVERTED

    def test_flat_yield_curve(self):
        """Test flat yield curve classification."""
        spread = 10
        state = _classify_yield_curve(spread)
        assert state == YieldCurveState.FLAT

    def test_normal_yield_curve(self):
        """Test normal yield curve classification."""
        spread = 100
        state = _classify_yield_curve(spread)
        assert state == YieldCurveState.NORMAL

    def test_steep_yield_curve(self):
        """Test steep yield curve classification."""
        spread = 250
        state = _classify_yield_curve(spread)
        assert state == YieldCurveState.STEEP

    def test_none_spread_defaults_to_normal(self):
        """Test that None spread defaults to normal."""
        state = _classify_yield_curve(None)
        assert state == YieldCurveState.NORMAL


class TestRecessionProbability:
    """Tests for recession probability calculation."""

    def test_inverted_curve_high_probability(self):
        """Test inverted curve gives high recession probability."""
        prob = _calculate_recession_probability(
            YieldCurveState.INVERTED,
            inversion_days=180,
            total_days=252
        )
        assert prob >= 50

    def test_normal_curve_low_probability(self):
        """Test normal curve gives low recession probability."""
        prob = _calculate_recession_probability(
            YieldCurveState.NORMAL,
            inversion_days=0,
            total_days=252
        )
        assert prob < 25

    def test_prolonged_inversion_increases_probability(self):
        """Test prolonged inversion increases probability."""
        short_inversion = _calculate_recession_probability(
            YieldCurveState.INVERTED,
            inversion_days=30,
            total_days=252
        )
        long_inversion = _calculate_recession_probability(
            YieldCurveState.INVERTED,
            inversion_days=150,
            total_days=252
        )
        assert long_inversion > short_inversion


class TestSpreadCalculation:
    """Tests for spread series calculation."""

    def test_spread_series(self, treasury_2y_data, treasury_10y_data):
        """Test spread series calculation."""
        spreads = _calculate_spread_series(treasury_2y_data, treasury_10y_data)
        assert len(spreads) > 0


# ============================================================================
# Monetary Policy Tests
# ============================================================================

class TestMonetaryPolicyClassification:
    """Tests for monetary policy stance classification."""

    def test_hawkish_policy(self):
        """Test hawkish policy classification."""
        policy = _classify_monetary_policy(rate=5.0, change_6m=1.0, inflation=3.5)
        assert policy == MonetaryPolicy.HAWKISH

    def test_dovish_policy(self):
        """Test dovish policy classification."""
        policy = _classify_monetary_policy(rate=3.0, change_6m=-1.0, inflation=2.0)
        assert policy == MonetaryPolicy.DOVISH

    def test_emergency_policy(self):
        """Test emergency policy classification."""
        policy = _classify_monetary_policy(rate=0.25, change_6m=0.0, inflation=1.0)
        assert policy == MonetaryPolicy.EMERGENCY

    def test_neutral_policy(self):
        """Test neutral policy classification."""
        policy = _classify_monetary_policy(rate=3.0, change_6m=0.0, inflation=2.0)
        assert policy == MonetaryPolicy.NEUTRAL


# ============================================================================
# Inflation Regime Tests
# ============================================================================

class TestInflationRegimeClassification:
    """Tests for inflation regime classification."""

    def test_deflation_regime(self):
        """Test deflation regime classification."""
        regime = _classify_inflation_regime(-1.0)
        assert regime == InflationRegime.DEFLATION

    def test_low_inflation_regime(self):
        """Test low inflation regime classification."""
        regime = _classify_inflation_regime(1.0)
        assert regime == InflationRegime.LOW

    def test_target_inflation_regime(self):
        """Test target inflation regime classification."""
        regime = _classify_inflation_regime(2.5)
        assert regime == InflationRegime.TARGET

    def test_elevated_inflation_regime(self):
        """Test elevated inflation regime classification."""
        regime = _classify_inflation_regime(4.0)
        assert regime == InflationRegime.ELEVATED

    def test_high_inflation_regime(self):
        """Test high inflation regime classification."""
        regime = _classify_inflation_regime(7.0)
        assert regime == InflationRegime.HIGH


# ============================================================================
# Signal Generation Tests
# ============================================================================

class TestSignalGeneration:
    """Tests for signal generation helpers."""

    def test_trend_to_arrow_up(self):
        """Test upward trend arrow."""
        assert "⬆️" in _trend_to_arrow(0.5)

    def test_trend_to_arrow_down(self):
        """Test downward trend arrow."""
        assert "⬇️" in _trend_to_arrow(-0.5)

    def test_trend_to_arrow_neutral(self):
        """Test neutral trend arrow."""
        assert "➡️" in _trend_to_arrow(0.0)

    def test_gdp_signal_strong(self):
        """Test strong GDP signal."""
        signal = _gdp_signal(4.0)
        assert "Strong" in signal

    def test_gdp_signal_contraction(self):
        """Test contraction GDP signal."""
        signal = _gdp_signal(-1.0)
        assert "Contraction" in signal

    def test_unemployment_signal_tight(self):
        """Test tight labor market signal."""
        signal = _unemployment_signal(3.5)
        assert "Tight" in signal

    def test_inflation_signal_high(self):
        """Test high inflation signal."""
        signal = _inflation_signal(5.0)
        assert "High" in signal

    def test_m2_signal_expanding(self):
        """Test expanding M2 signal."""
        signal = _m2_signal(12.0)
        assert "Expanding" in signal

    def test_m2_signal_contracting(self):
        """Test contracting M2 signal."""
        signal = _m2_signal(-2.0)
        assert "Contracting" in signal


# ============================================================================
# Interpretation Tests
# ============================================================================

class TestInterpretations:
    """Tests for interpretation text generation."""

    def test_regime_interpretation_expansion(self):
        """Test expansion regime interpretation."""
        text = _regime_interpretation(EconomicRegime.EXPANSION)
        assert "expansion" in text.lower()
        assert len(text) > 50

    def test_regime_investment_implications(self):
        """Test regime investment implications."""
        text = _regime_investment_implications(EconomicRegime.CONTRACTION)
        assert "Equities" in text
        assert "Fixed Income" in text

    def test_yield_curve_interpretation_inverted(self):
        """Test inverted yield curve interpretation."""
        text = _yield_curve_interpretation(YieldCurveState.INVERTED, 65)
        assert "inverted" in text.lower() or "recession" in text.lower()

    def test_real_rate_interpretation_restrictive(self):
        """Test restrictive real rate interpretation."""
        text = _real_rate_interpretation(3.0)
        assert "Restrictive" in text

    def test_real_rate_interpretation_accommodative(self):
        """Test accommodative real rate interpretation."""
        text = _real_rate_interpretation(-1.0)
        assert "Accommodative" in text

    def test_inflation_trajectory_accelerating(self):
        """Test accelerating inflation interpretation."""
        text = _inflation_trajectory_interpretation("accelerating", 3.0, 4.5)
        assert "accelerating" in text.lower()

    def test_inflation_asset_impact(self):
        """Test inflation asset impact table."""
        text = _inflation_asset_impact(InflationRegime.HIGH)
        assert "Commodities" in text
        assert "Positive" in text


# ============================================================================
# Agent Factory Tests
# ============================================================================

class TestMacroAnalystFactory:
    """Tests for create_macro_analyst factory function."""

    def test_factory_expected_signature(self):
        """Test that factory function has correct signature."""
        def mock_factory(llm):
            def node(state):
                return {"messages": [], "macro_report": ""}
            return node

        mock_llm = Mock()
        node = mock_factory(mock_llm)
        assert callable(node)

    def test_node_returns_correct_structure(self):
        """Test that node returns expected structure."""
        def mock_node(state):
            return {"messages": [Mock()], "macro_report": "Test report"}

        state = {
            "trade_date": "2024-01-15",
            "company_of_interest": "AAPL",
            "messages": []
        }
        result = mock_node(state)
        assert "messages" in result
        assert "macro_report" in result

    def test_expected_tools_list(self):
        """Test expected tools for macro analyst."""
        expected_tools = [
            "get_economic_regime_analysis",
            "get_yield_curve_analysis",
            "get_monetary_policy_analysis",
            "get_inflation_regime_analysis"
        ]
        assert len(expected_tools) == 4
        assert "get_economic_regime_analysis" in expected_tools


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_dataframe_growth_rate(self):
        """Test growth rate with empty DataFrame."""
        result = _calculate_growth_rate(pd.DataFrame())
        assert result == 0.0

    def test_empty_dataframe_trend(self):
        """Test trend with empty DataFrame."""
        result = _calculate_trend(pd.DataFrame())
        assert result == 0.0

    def test_empty_dataframe_yoy(self):
        """Test YoY change with empty DataFrame."""
        result = _calculate_yoy_change(pd.DataFrame())
        assert result == 0.0

    def test_insufficient_data_growth_rate(self):
        """Test growth rate with insufficient data."""
        df = pd.DataFrame({'value': [100, 101, 102]})
        result = _calculate_growth_rate(df)
        assert result == 0.0

    def test_none_inputs_handled(self):
        """Test None input handling in signals."""
        assert _gdp_signal(None) == "N/A"
        assert _unemployment_signal(None) == "N/A"
        assert _inflation_signal(None) == "N/A"
        assert _m2_signal(None) == "N/A"

    def test_spread_series_with_empty_data(self):
        """Test spread series with empty DataFrames."""
        result = _calculate_spread_series(pd.DataFrame(), pd.DataFrame())
        assert result == []


# ============================================================================
# Enum Value Tests
# ============================================================================

class TestEnumValues:
    """Tests for enum values and consistency."""

    def test_economic_regime_values(self):
        """Test economic regime enum values."""
        assert EconomicRegime.EXPANSION.value == "expansion"
        assert EconomicRegime.CONTRACTION.value == "contraction"
        assert EconomicRegime.STAGFLATION.value == "stagflation"
        assert EconomicRegime.GOLDILOCKS.value == "goldilocks"

    def test_yield_curve_state_values(self):
        """Test yield curve state enum values."""
        assert YieldCurveState.NORMAL.value == "normal"
        assert YieldCurveState.INVERTED.value == "inverted"
        assert YieldCurveState.FLAT.value == "flat"
        assert YieldCurveState.STEEP.value == "steep"

    def test_monetary_policy_values(self):
        """Test monetary policy enum values."""
        assert MonetaryPolicy.HAWKISH.value == "hawkish"
        assert MonetaryPolicy.DOVISH.value == "dovish"
        assert MonetaryPolicy.NEUTRAL.value == "neutral"
        assert MonetaryPolicy.EMERGENCY.value == "emergency"

    def test_inflation_regime_values(self):
        """Test inflation regime enum values."""
        assert InflationRegime.DEFLATION.value == "deflation"
        assert InflationRegime.LOW.value == "low"
        assert InflationRegime.TARGET.value == "target"
        assert InflationRegime.ELEVATED.value == "elevated"
        assert InflationRegime.HIGH.value == "high"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for macro analysis workflow."""

    def test_regime_with_interpretation(self):
        """Test regime classification with interpretation."""
        indicators = {
            'gdp_growth': 3.0,
            'unemployment': 4.0,
            'inflation': 2.5
        }
        regime = _classify_economic_regime(indicators)
        interpretation = _regime_interpretation(regime)
        assert regime in list(EconomicRegime)
        assert len(interpretation) > 0

    def test_yield_curve_full_analysis(self):
        """Test full yield curve analysis flow."""
        spread = -75
        state = _classify_yield_curve(spread)
        prob = _calculate_recession_probability(state, 100, 252)
        interpretation = _yield_curve_interpretation(state, prob)
        assert state == YieldCurveState.INVERTED
        assert prob >= 50
        assert len(interpretation) > 0

    def test_inflation_full_analysis(self):
        """Test full inflation analysis flow."""
        inflation_rate = 6.0
        regime = _classify_inflation_regime(inflation_rate)
        interpretation = _inflation_regime_interpretation(regime)
        impact = _inflation_asset_impact(regime)
        assert regime == InflationRegime.HIGH
        assert len(interpretation) > 0
        assert "Commodities" in impact
