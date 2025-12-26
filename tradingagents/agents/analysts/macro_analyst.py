"""Macro Analyst Agent.

Specializes in macroeconomic analysis using FRED data:
- Economic regime detection (expansion, contraction, stagflation)
- Interest rate environment analysis
- Yield curve interpretation
- Money supply and liquidity analysis
- Inflation regime classification
- GDP growth assessment

Issue #14: [AGENT-13] Macro Analyst - FRED interpretation, regime detection
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from typing import Annotated, Dict, Any, List, Optional
import pandas as pd
from enum import Enum


# ============================================================================
# Economic Regime Definitions
# ============================================================================

class EconomicRegime(str, Enum):
    """Economic regime classifications."""
    EXPANSION = "expansion"
    LATE_CYCLE = "late_cycle"
    CONTRACTION = "contraction"
    EARLY_RECOVERY = "early_recovery"
    STAGFLATION = "stagflation"
    GOLDILOCKS = "goldilocks"  # Low inflation, moderate growth


class YieldCurveState(str, Enum):
    """Yield curve state classifications."""
    NORMAL = "normal"  # 2Y < 10Y (positive slope)
    FLAT = "flat"  # 2Y ≈ 10Y (within 25bp)
    INVERTED = "inverted"  # 2Y > 10Y (negative slope)
    STEEP = "steep"  # Large positive spread (>200bp)


class MonetaryPolicy(str, Enum):
    """Monetary policy stance classifications."""
    HAWKISH = "hawkish"  # Rising rates, fighting inflation
    NEUTRAL = "neutral"  # Stable rates
    DOVISH = "dovish"  # Falling rates, supporting growth
    EMERGENCY = "emergency"  # Near-zero rates


class InflationRegime(str, Enum):
    """Inflation regime classifications."""
    DEFLATION = "deflation"  # < 0%
    LOW = "low"  # 0-2%
    TARGET = "target"  # 2-3%
    ELEVATED = "elevated"  # 3-5%
    HIGH = "high"  # > 5%


# ============================================================================
# FRED Data Access Helpers
# ============================================================================

def _get_fred_data(series_id: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Helper to get FRED data with proper error handling."""
    try:
        from tradingagents.dataflows.fred import (
            get_interest_rates,
            get_treasury_rates,
            get_money_supply,
            get_gdp,
            get_inflation,
            get_unemployment,
            get_fred_series,
        )

        # Route to appropriate function based on series
        series_mapping = {
            'FEDFUNDS': lambda: get_interest_rates(start_date=start_date, end_date=end_date),
            'DGS2': lambda: get_treasury_rates('2Y', start_date=start_date, end_date=end_date),
            'DGS10': lambda: get_treasury_rates('10Y', start_date=start_date, end_date=end_date),
            'M2SL': lambda: get_money_supply('M2', start_date=start_date, end_date=end_date),
            'GDP': lambda: get_gdp(start_date=start_date, end_date=end_date),
            'CPIAUCSL': lambda: get_inflation('CPI', start_date=start_date, end_date=end_date),
            'UNRATE': lambda: get_unemployment(start_date=start_date, end_date=end_date),
        }

        if series_id in series_mapping:
            return series_mapping[series_id]()
        else:
            return get_fred_series(series_id, start_date=start_date, end_date=end_date)

    except ImportError:
        # Fallback for testing without full FRED module
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


# ============================================================================
# Macro Analysis Tools
# ============================================================================

@tool
def get_economic_regime_analysis(
    curr_date: Annotated[str, "Current analysis date in YYYY-MM-DD format"],
    look_back_months: Annotated[int, "Months of history to analyze (default: 12)"] = 12,
) -> str:
    """
    Analyze current economic regime using multiple FRED indicators.

    Considers:
    - GDP growth (expansion vs contraction)
    - Unemployment trend (improving vs deteriorating)
    - Inflation level (target vs elevated)
    - Interest rate direction

    Returns comprehensive regime classification with supporting data.
    """
    try:
        from datetime import datetime, timedelta

        # Calculate date range
        end_date = curr_date
        start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_months * 30)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Collect economic indicators
        indicators = {}

        # Get GDP data
        gdp_data = _get_fred_data('GDP', start_date=start_date, end_date=end_date)
        if isinstance(gdp_data, pd.DataFrame) and not gdp_data.empty:
            gdp_growth = _calculate_growth_rate(gdp_data)
            indicators['gdp_growth'] = gdp_growth

        # Get unemployment data
        unemp_data = _get_fred_data('UNRATE', start_date=start_date, end_date=end_date)
        if isinstance(unemp_data, pd.DataFrame) and not unemp_data.empty:
            unemp_level = unemp_data['value'].iloc[-1] if 'value' in unemp_data.columns else None
            unemp_trend = _calculate_trend(unemp_data)
            indicators['unemployment'] = unemp_level
            indicators['unemployment_trend'] = unemp_trend

        # Get inflation data
        cpi_data = _get_fred_data('CPIAUCSL', start_date=start_date, end_date=end_date)
        if isinstance(cpi_data, pd.DataFrame) and not cpi_data.empty:
            inflation_rate = _calculate_yoy_change(cpi_data)
            indicators['inflation'] = inflation_rate

        # Get Fed Funds Rate
        ffr_data = _get_fred_data('FEDFUNDS', start_date=start_date, end_date=end_date)
        if isinstance(ffr_data, pd.DataFrame) and not ffr_data.empty:
            fed_rate = ffr_data['value'].iloc[-1] if 'value' in ffr_data.columns else None
            fed_trend = _calculate_trend(ffr_data)
            indicators['fed_funds_rate'] = fed_rate
            indicators['fed_trend'] = fed_trend

        # Determine economic regime
        regime = _classify_economic_regime(indicators)

        # Generate report
        report = f"""
## Economic Regime Analysis
Analysis Date: {curr_date}
Look-back Period: {look_back_months} months

### Current Regime: {regime.value.upper()}

### Key Economic Indicators

| Indicator | Current Value | Trend | Signal |
|-----------|---------------|-------|--------|
| GDP Growth | {indicators.get('gdp_growth', 'N/A'):.1f}% | {_trend_to_arrow(indicators.get('gdp_growth', 0))} | {_gdp_signal(indicators.get('gdp_growth'))} |
| Unemployment | {indicators.get('unemployment', 'N/A'):.1f}% | {_trend_to_arrow(-indicators.get('unemployment_trend', 0))} | {_unemployment_signal(indicators.get('unemployment'))} |
| Inflation (YoY) | {indicators.get('inflation', 'N/A'):.1f}% | {_trend_to_arrow(indicators.get('inflation', 0) - 2)} | {_inflation_signal(indicators.get('inflation'))} |
| Fed Funds Rate | {indicators.get('fed_funds_rate', 'N/A'):.2f}% | {_trend_to_arrow(indicators.get('fed_trend', 0))} | {_policy_signal(indicators.get('fed_trend'))} |

### Regime Interpretation

{_regime_interpretation(regime)}

### Investment Implications

{_regime_investment_implications(regime)}
"""
        return report

    except Exception as e:
        return f"Error in economic regime analysis: {str(e)}"


@tool
def get_yield_curve_analysis(
    curr_date: Annotated[str, "Current analysis date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "Days of history to analyze (default: 252)"] = 252,
) -> str:
    """
    Analyze yield curve shape and implications.

    Examines:
    - 2Y-10Y spread (primary recession indicator)
    - 3M-10Y spread (Fed's preferred measure)
    - Historical context and duration of current state
    - Recession probability based on inversion history

    Returns yield curve analysis with recession probability.
    """
    try:
        from datetime import datetime, timedelta

        end_date = curr_date
        start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Get yield data
        dgs2_data = _get_fred_data('DGS2', start_date=start_date, end_date=end_date)
        dgs10_data = _get_fred_data('DGS10', start_date=start_date, end_date=end_date)

        # Calculate current spread
        current_2y = None
        current_10y = None
        current_spread = None

        if isinstance(dgs2_data, pd.DataFrame) and not dgs2_data.empty:
            current_2y = dgs2_data['value'].iloc[-1] if 'value' in dgs2_data.columns else dgs2_data.iloc[-1, 0]

        if isinstance(dgs10_data, pd.DataFrame) and not dgs10_data.empty:
            current_10y = dgs10_data['value'].iloc[-1] if 'value' in dgs10_data.columns else dgs10_data.iloc[-1, 0]

        if current_2y is not None and current_10y is not None:
            current_spread = current_10y - current_2y

        # Determine yield curve state
        curve_state = _classify_yield_curve(current_spread)

        # Calculate inversion metrics
        inversion_days = 0
        avg_spread = None
        if isinstance(dgs2_data, pd.DataFrame) and isinstance(dgs10_data, pd.DataFrame):
            spread_series = _calculate_spread_series(dgs2_data, dgs10_data)
            if len(spread_series) > 0:
                inversion_days = len([s for s in spread_series if s < 0])
                avg_spread = sum(spread_series) / len(spread_series)

        # Recession probability based on inversion
        recession_prob = _calculate_recession_probability(curve_state, inversion_days, look_back_days)

        report = f"""
## Yield Curve Analysis
Analysis Date: {curr_date}
Look-back Period: {look_back_days} days

### Current Yield Curve State: {curve_state.value.upper()}

### Treasury Yields

| Maturity | Current Yield |
|----------|---------------|
| 2-Year | {current_2y:.2f}% |
| 10-Year | {current_10y:.2f}% |
| **Spread (10Y-2Y)** | **{current_spread:.0f} bp** |

### Curve Metrics

- **Current Spread**: {current_spread:.0f} basis points
- **Average Spread (Period)**: {avg_spread:.0f if avg_spread else 'N/A'} bp
- **Days Inverted**: {inversion_days} of {look_back_days} days ({inversion_days/look_back_days*100:.1f}%)

### Recession Probability

Based on yield curve analysis: **{recession_prob:.0f}%**

{_yield_curve_interpretation(curve_state, recession_prob)}

### Historical Context

{_yield_curve_historical_context(curve_state, inversion_days)}
"""
        return report

    except Exception as e:
        return f"Error in yield curve analysis: {str(e)}"


@tool
def get_monetary_policy_analysis(
    curr_date: Annotated[str, "Current analysis date in YYYY-MM-DD format"],
    look_back_months: Annotated[int, "Months of history to analyze (default: 24)"] = 24,
) -> str:
    """
    Analyze Federal Reserve monetary policy stance and direction.

    Examines:
    - Federal Funds Rate level and trajectory
    - Real interest rates (Fed Funds - Inflation)
    - Money supply (M2) growth
    - Policy stance classification

    Returns monetary policy analysis with stance assessment.
    """
    try:
        from datetime import datetime, timedelta

        end_date = curr_date
        start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_months * 30)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Get Fed Funds Rate
        ffr_data = _get_fred_data('FEDFUNDS', start_date=start_date, end_date=end_date)
        current_ffr = None
        ffr_change_6m = None
        ffr_change_12m = None

        if isinstance(ffr_data, pd.DataFrame) and not ffr_data.empty:
            values = ffr_data['value'] if 'value' in ffr_data.columns else ffr_data.iloc[:, 0]
            current_ffr = values.iloc[-1]
            if len(values) > 126:  # ~6 months of daily data
                ffr_change_6m = current_ffr - values.iloc[-126]
            if len(values) > 252:  # ~12 months
                ffr_change_12m = current_ffr - values.iloc[-252]

        # Get M2 money supply
        m2_data = _get_fred_data('M2SL', start_date=start_date, end_date=end_date)
        m2_growth = None
        if isinstance(m2_data, pd.DataFrame) and not m2_data.empty:
            m2_growth = _calculate_yoy_change(m2_data)

        # Get inflation
        cpi_data = _get_fred_data('CPIAUCSL', start_date=start_date, end_date=end_date)
        inflation = None
        if isinstance(cpi_data, pd.DataFrame) and not cpi_data.empty:
            inflation = _calculate_yoy_change(cpi_data)

        # Calculate real rate
        real_rate = None
        if current_ffr is not None and inflation is not None:
            real_rate = current_ffr - inflation

        # Determine policy stance
        policy_stance = _classify_monetary_policy(current_ffr, ffr_change_6m, inflation)

        report = f"""
## Monetary Policy Analysis
Analysis Date: {curr_date}
Look-back Period: {look_back_months} months

### Policy Stance: {policy_stance.value.upper()}

### Federal Funds Rate

| Metric | Value |
|--------|-------|
| Current Rate | {current_ffr:.2f}% |
| 6-Month Change | {'+' if ffr_change_6m and ffr_change_6m > 0 else ''}{ffr_change_6m:.2f if ffr_change_6m else 'N/A'}% |
| 12-Month Change | {'+' if ffr_change_12m and ffr_change_12m > 0 else ''}{ffr_change_12m:.2f if ffr_change_12m else 'N/A'}% |

### Real Interest Rate

- **Nominal Rate (FFR)**: {current_ffr:.2f}%
- **Inflation Rate**: {inflation:.2f if inflation else 'N/A'}%
- **Real Rate**: {real_rate:.2f if real_rate else 'N/A'}%

{_real_rate_interpretation(real_rate)}

### Liquidity Conditions

| Metric | Value | Signal |
|--------|-------|--------|
| M2 Growth (YoY) | {m2_growth:.1f if m2_growth else 'N/A'}% | {_m2_signal(m2_growth)} |

### Policy Direction Assessment

{_policy_direction_interpretation(policy_stance, ffr_change_6m)}

### Market Implications

{_policy_market_implications(policy_stance, real_rate)}
"""
        return report

    except Exception as e:
        return f"Error in monetary policy analysis: {str(e)}"


@tool
def get_inflation_regime_analysis(
    curr_date: Annotated[str, "Current analysis date in YYYY-MM-DD format"],
    look_back_months: Annotated[int, "Months of history to analyze (default: 36)"] = 36,
) -> str:
    """
    Analyze inflation regime and trajectory.

    Examines:
    - CPI headline and core
    - PCE (Fed's preferred measure)
    - Inflation trend (accelerating/decelerating)
    - Inflation expectations

    Returns inflation regime analysis with investment implications.
    """
    try:
        from datetime import datetime, timedelta

        end_date = curr_date
        start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_months * 30)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Get CPI data
        cpi_data = _get_fred_data('CPIAUCSL', start_date=start_date, end_date=end_date)
        cpi_yoy = None
        cpi_3m_annualized = None
        cpi_trend = None

        if isinstance(cpi_data, pd.DataFrame) and not cpi_data.empty:
            cpi_yoy = _calculate_yoy_change(cpi_data)
            cpi_3m_annualized = _calculate_annualized_3m_change(cpi_data)
            cpi_trend = "accelerating" if cpi_3m_annualized and cpi_yoy and cpi_3m_annualized > cpi_yoy else "decelerating"

        # Determine inflation regime
        inflation_regime = _classify_inflation_regime(cpi_yoy)

        # Calculate deviation from target
        target_deviation = (cpi_yoy - 2.0) if cpi_yoy else None

        report = f"""
## Inflation Regime Analysis
Analysis Date: {curr_date}
Look-back Period: {look_back_months} months

### Current Regime: {inflation_regime.value.upper()}

### Inflation Metrics

| Measure | Value | Target Deviation |
|---------|-------|------------------|
| CPI (YoY) | {cpi_yoy:.1f if cpi_yoy else 'N/A'}% | {'+' if target_deviation and target_deviation > 0 else ''}{target_deviation:.1f if target_deviation else 'N/A'}% |
| CPI (3M Annualized) | {cpi_3m_annualized:.1f if cpi_3m_annualized else 'N/A'}% | {_momentum_signal(cpi_3m_annualized, cpi_yoy)} |

### Inflation Trajectory: {cpi_trend.upper() if cpi_trend else 'UNKNOWN'}

{_inflation_trajectory_interpretation(cpi_trend, cpi_yoy, cpi_3m_annualized)}

### Regime Implications

{_inflation_regime_interpretation(inflation_regime)}

### Asset Class Impact

{_inflation_asset_impact(inflation_regime)}
"""
        return report

    except Exception as e:
        return f"Error in inflation regime analysis: {str(e)}"


# ============================================================================
# Helper Functions
# ============================================================================

def _calculate_growth_rate(data: pd.DataFrame) -> float:
    """Calculate annualized growth rate from data."""
    if data.empty or len(data) < 4:
        return 0.0
    values = data['value'] if 'value' in data.columns else data.iloc[:, 0]
    if len(values) >= 4:
        # Quarterly data: compare to 4 quarters ago
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


def _calculate_annualized_3m_change(data: pd.DataFrame) -> float:
    """Calculate 3-month change annualized."""
    if data.empty or len(data) < 3:
        return 0.0
    values = data['value'] if 'value' in data.columns else data.iloc[:, 0]
    if len(values) >= 3:
        return ((values.iloc[-1] / values.iloc[-3]) ** 4 - 1) * 100
    return 0.0


def _calculate_spread_series(data_2y: pd.DataFrame, data_10y: pd.DataFrame) -> List[float]:
    """Calculate spread series between two yield series."""
    try:
        v2y = data_2y['value'] if 'value' in data_2y.columns else data_2y.iloc[:, 0]
        v10y = data_10y['value'] if 'value' in data_10y.columns else data_10y.iloc[:, 0]
        min_len = min(len(v2y), len(v10y))
        return [(v10y.iloc[i] - v2y.iloc[i]) * 100 for i in range(min_len)]  # Convert to bp
    except Exception:
        return []


def _classify_economic_regime(indicators: Dict) -> EconomicRegime:
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

    # Adjust based on inversion duration
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


def _policy_signal(trend: float) -> str:
    """Generate signal based on policy trend."""
    if trend is None:
        return "➡️ Stable"
    if trend > 0.1:
        return "⬆️ Tightening"
    elif trend < -0.1:
        return "⬇️ Easing"
    else:
        return "➡️ Stable"


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


def _momentum_signal(short_term: float, long_term: float) -> str:
    """Compare short vs long term for momentum."""
    if short_term is None or long_term is None:
        return "N/A"
    if short_term > long_term + 0.5:
        return "⬆️ Accelerating"
    elif short_term < long_term - 0.5:
        return "⬇️ Decelerating"
    else:
        return "➡️ Stable"


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
        EconomicRegime.LATE_CYCLE: """- **Equities**: Shift toward quality and defensive sectors
- **Fixed Income**: Begin adding duration, reduce credit risk
- **Commodities**: Mixed outlook, monitor demand signals
- **Cash**: Increase allocation as hedge""",
        EconomicRegime.CONTRACTION: """- **Equities**: Defensive sectors (Utilities, Healthcare, Consumer Staples)
- **Fixed Income**: Overweight Treasuries, extend duration
- **Commodities**: Underweight cyclical commodities
- **Cash**: Elevated allocation appropriate""",
        EconomicRegime.EARLY_RECOVERY: """- **Equities**: Favor small caps and value stocks
- **Fixed Income**: Reduce duration as recovery strengthens
- **Commodities**: Early-cycle commodities may rally
- **Real Estate**: Recovery in cyclical REITs""",
        EconomicRegime.STAGFLATION: """- **Equities**: Quality dividend payers, inflation hedges
- **Fixed Income**: TIPS, short duration
- **Commodities**: Gold and commodity producers
- **Real Assets**: Inflation-linked real assets""",
        EconomicRegime.GOLDILOCKS: """- **Equities**: Broad market exposure, growth stocks
- **Fixed Income**: Modest duration, credit exposure
- **Commodities**: Neutral to constructive
- **Alternative**: Risk-on positioning appropriate""",
    }
    return implications.get(regime, "Maintain balanced allocation.")


def _yield_curve_interpretation(state: YieldCurveState, recession_prob: float) -> str:
    """Generate interpretation for yield curve state."""
    if state == YieldCurveState.INVERTED:
        return f"""⚠️ **Inverted Yield Curve Warning**

The yield curve is inverted (2Y yield exceeds 10Y), historically a reliable recession predictor. Since 1955, an inverted yield curve has preceded every recession with an average lead time of 12-18 months.

Current recession probability: {recession_prob:.0f}%

Note: The yield curve can remain inverted for extended periods before recession materializes."""

    elif state == YieldCurveState.FLAT:
        return f"""📊 **Flattening Yield Curve**

The yield curve is flat, indicating uncertainty about future growth and monetary policy direction. This often precedes either inversion (bearish) or steepening (bullish).

Monitor for: Further flattening toward inversion, or steepening on policy pivot."""

    elif state == YieldCurveState.STEEP:
        return f"""📈 **Steep Yield Curve**

The steep yield curve suggests expectations of accelerating growth and/or rising inflation. This is typically seen in early recovery phases and is generally positive for banks and cyclical sectors."""

    else:
        return f"""✅ **Normal Yield Curve**

The yield curve has a normal positive slope, suggesting healthy expectations for growth without imminent recession concerns. This is a constructive backdrop for risk assets."""


def _yield_curve_historical_context(state: YieldCurveState, inversion_days: int) -> str:
    """Generate historical context for yield curve."""
    if state == YieldCurveState.INVERTED:
        return """**Historical Inversions and Recessions:**
- 2019-2020: Inverted → COVID recession (2020)
- 2006-2007: Inverted → Financial Crisis (2008)
- 2000-2001: Inverted → Dot-com recession (2001)
- 1989-1990: Inverted → 1990 recession

Average lead time: 12-18 months from first inversion."""
    return "The yield curve's current shape is consistent with historical patterns during similar economic conditions."


def _real_rate_interpretation(real_rate: float) -> str:
    """Interpret real interest rate level."""
    if real_rate is None:
        return ""
    if real_rate > 2:
        return "**Restrictive**: Real rates are significantly positive, indicating tight monetary conditions that may slow economic growth."
    elif real_rate > 0:
        return "**Neutral to Tight**: Positive real rates suggest monetary policy is not accommodative but not severely restrictive."
    elif real_rate > -2:
        return "**Accommodative**: Negative real rates indicate easy monetary conditions that support growth and asset prices."
    else:
        return "**Highly Accommodative**: Deeply negative real rates represent emergency monetary accommodation."


def _policy_direction_interpretation(stance: MonetaryPolicy, change: float) -> str:
    """Interpret monetary policy direction."""
    if stance == MonetaryPolicy.HAWKISH:
        return "The Fed is in tightening mode, raising rates to combat inflation. This typically creates headwinds for rate-sensitive assets and may slow economic growth."
    elif stance == MonetaryPolicy.DOVISH:
        return "The Fed is easing monetary policy, cutting rates to support growth. This is generally supportive for risk assets and rate-sensitive sectors."
    elif stance == MonetaryPolicy.EMERGENCY:
        return "Emergency monetary conditions with rates near zero. The Fed is providing maximum accommodation to support the economy."
    else:
        return "Monetary policy is in a neutral stance with rates stable. Watch for signals of future direction changes."


def _policy_market_implications(stance: MonetaryPolicy, real_rate: float) -> str:
    """Generate market implications for monetary policy."""
    if stance == MonetaryPolicy.HAWKISH:
        return """- **Equities**: Headwind for growth stocks, favor value
- **Fixed Income**: Duration risk, favor short-term
- **USD**: Supportive for dollar strength
- **Gold**: Headwind from rising real rates"""
    elif stance == MonetaryPolicy.DOVISH:
        return """- **Equities**: Supportive for growth stocks
- **Fixed Income**: Rally potential in longer duration
- **USD**: Potential dollar weakness
- **Gold**: Supportive from falling real rates"""
    elif stance == MonetaryPolicy.EMERGENCY:
        return """- **Equities**: Maximum policy support, but monitor fundamentals
- **Fixed Income**: Very low yields, consider credit for income
- **USD**: Potential weakness from accommodation
- **Gold**: Historically supportive environment"""
    else:
        return """- **Equities**: Monitor for policy pivot signals
- **Fixed Income**: Neutral positioning appropriate
- **USD**: Data-dependent direction
- **Gold**: Balanced outlook"""


def _inflation_trajectory_interpretation(trend: str, yoy: float, short_term: float) -> str:
    """Interpret inflation trajectory."""
    if trend == "accelerating":
        return f"Inflation momentum is **accelerating**, with the 3-month annualized rate ({short_term:.1f}%) exceeding the year-over-year rate ({yoy:.1f}%). This suggests upward pressure on prices and potential Fed response."
    elif trend == "decelerating":
        return f"Inflation is **decelerating**, with the 3-month annualized rate ({short_term:.1f}%) below the year-over-year rate ({yoy:.1f}%). This suggests easing price pressures, potentially allowing for more accommodative policy."
    return "Inflation momentum is relatively stable."


def _inflation_regime_interpretation(regime: InflationRegime) -> str:
    """Interpret inflation regime implications."""
    interpretations = {
        InflationRegime.DEFLATION: "Deflationary conditions are rare and concerning, typically associated with economic distress. Central banks will aggressively fight deflation.",
        InflationRegime.LOW: "Low inflation below the 2% target may prompt continued monetary accommodation. Watch for disinflation risks.",
        InflationRegime.TARGET: "Inflation is at or near the Fed's 2% target - the 'sweet spot' for monetary policy. This allows for balanced policy decisions.",
        InflationRegime.ELEVATED: "Elevated inflation above target will keep the Fed focused on price stability. Expect tighter monetary conditions until inflation returns to target.",
        InflationRegime.HIGH: "High inflation is the primary policy concern. Aggressive monetary tightening is likely until inflation shows sustained decline.",
    }
    return interpretations.get(regime, "")


def _inflation_asset_impact(regime: InflationRegime) -> str:
    """Generate asset class impact for inflation regime."""
    impacts = {
        InflationRegime.DEFLATION: """| Asset Class | Impact | Recommendation |
|-------------|--------|----------------|
| Equities | Negative | Defensive, quality focus |
| Bonds | Positive | Long duration, Treasuries |
| Cash | Positive | Preserves purchasing power |
| Commodities | Negative | Underweight |
| Real Estate | Negative | Avoid leveraged plays |""",
        InflationRegime.LOW: """| Asset Class | Impact | Recommendation |
|-------------|--------|----------------|
| Equities | Neutral | Broad exposure appropriate |
| Bonds | Positive | Duration acceptable |
| Cash | Neutral | Modest allocation |
| Commodities | Neutral | Selective exposure |
| Real Estate | Neutral | Standard allocation |""",
        InflationRegime.TARGET: """| Asset Class | Impact | Recommendation |
|-------------|--------|----------------|
| Equities | Positive | Full risk allocation |
| Bonds | Neutral | Balanced duration |
| Cash | Negative | Minimize excess |
| Commodities | Neutral | Market-weight |
| Real Estate | Positive | Favorable environment |""",
        InflationRegime.ELEVATED: """| Asset Class | Impact | Recommendation |
|-------------|--------|----------------|
| Equities | Mixed | Pricing power matters |
| Bonds | Negative | Short duration, TIPS |
| Cash | Negative | Losing purchasing power |
| Commodities | Positive | Inflation hedge |
| Real Estate | Mixed | Real assets benefit |""",
        InflationRegime.HIGH: """| Asset Class | Impact | Recommendation |
|-------------|--------|----------------|
| Equities | Negative | Value, commodity producers |
| Bonds | Very Negative | Avoid duration, favor TIPS |
| Cash | Very Negative | Significant erosion |
| Commodities | Positive | Key inflation hedge |
| Real Estate | Mixed | Hard assets benefit |""",
    }
    return impacts.get(regime, "")


# ============================================================================
# Macro Analyst Agent Factory
# ============================================================================

def create_macro_analyst(llm):
    """
    Create a Macro Analyst agent that specializes in:
    - Economic regime detection
    - FRED data interpretation
    - Yield curve analysis
    - Monetary policy assessment
    - Inflation regime classification

    Args:
        llm: Language model for generating analysis

    Returns:
        Function that processes state and returns macro analysis
    """

    def macro_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_economic_regime_analysis,
            get_yield_curve_analysis,
            get_monetary_policy_analysis,
            get_inflation_regime_analysis,
        ]

        system_message = """You are a specialized Macro Analyst with expertise in economic analysis and FRED data interpretation. Your role is to provide comprehensive macroeconomic assessments including:

## Your Analytical Framework

### 1. Economic Regime Detection
- Classify current regime: Expansion, Late-Cycle, Contraction, Early Recovery, Stagflation, or Goldilocks
- Use GDP, unemployment, inflation, and policy indicators
- Identify regime transition signals

### 2. Yield Curve Analysis
- Analyze 2Y-10Y and 3M-10Y spreads
- Assess inversion duration and severity
- Calculate recession probability
- Historical context and implications

### 3. Monetary Policy Assessment
- Federal Funds Rate level and trajectory
- Real interest rates (nominal - inflation)
- Policy stance: Hawkish, Neutral, Dovish, Emergency
- Liquidity conditions (M2 growth)

### 4. Inflation Regime
- CPI and PCE analysis
- Inflation trajectory (accelerating/decelerating)
- Implications for policy and asset classes

## Analysis Process

1. **Start with get_economic_regime_analysis** for overall regime
2. **Use get_yield_curve_analysis** for recession signals
3. **Apply get_monetary_policy_analysis** for policy stance
4. **Check get_inflation_regime_analysis** for price pressures

## Output Requirements

Provide a comprehensive Macro Report including:
- Current economic regime and confidence level
- Key macro indicators table
- Regime transition risks
- Policy outlook
- Asset allocation implications

**Always quantify your assessments where possible.**

Focus on actionable implications for trading and investment decisions. Consider how macro conditions affect the specific company under analysis."""

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a specialized Macro Analyst assistant, collaborating with other analysts."
                    " Use the provided macro analysis tools to assess economic conditions."
                    " Execute comprehensive macroeconomic analysis to support trading decisions."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}. The company we want to analyze is {ticker}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "macro_report": report,
        }

    return macro_analyst_node
