"""Position Sizing Manager.

Specializes in optimal position sizing calculations using:
- Kelly Criterion for edge-based sizing
- Risk Parity for balanced risk allocation
- ATR-based sizing for volatility adjustment
- Fixed fractional position sizing
- Maximum drawdown constraints

Issue #16: [AGENT-15] Position Sizing Manager - Kelly, risk parity, ATR
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from typing import Annotated, Dict, Any, List, Optional
from enum import Enum
import pandas as pd
import numpy as np
from dataclasses import dataclass

from tradingagents.dataflows.interface import route_to_vendor


# ============================================================================
# Position Sizing Enums and Data Classes
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
    position_size: float  # As fraction of portfolio (0-1)
    dollar_amount: float
    shares: int
    risk_per_trade: float  # Dollar risk
    rationale: str


# ============================================================================
# Helper Functions
# ============================================================================

def _calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float
) -> float:
    """
    Calculate Kelly Criterion fraction.

    Kelly % = W - [(1-W) / R]
    Where:
        W = Win probability
        R = Win/Loss ratio (avg_win / avg_loss)
    """
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    win_loss_ratio = abs(avg_win / avg_loss)

    kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

    # Kelly can be negative (don't bet) or very large (reduce)
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
    """
    Calculate Average True Range (ATR).

    True Range = max(H-L, |H-C_prev|, |L-C_prev|)
    ATR = SMA(True Range, period)
    """
    if len(prices) < period + 1:
        return 0.0

    high = prices['high'] if 'high' in prices.columns else prices['High']
    low = prices['low'] if 'low' in prices.columns else prices['Low']
    close = prices['close'] if 'close' in prices.columns else prices['Close']

    # Calculate True Range components
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR is SMA of True Range
    atr = true_range.rolling(window=period).mean()

    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0


def _calculate_position_from_atr(
    account_value: float,
    risk_per_trade: float,  # As fraction (e.g., 0.02 for 2%)
    atr: float,
    atr_multiplier: float = 2.0,
    current_price: float = 1.0
) -> tuple:
    """
    Calculate position size based on ATR.

    Position Size = (Account * Risk%) / (ATR * Multiplier)
    """
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
        vol = vol * np.sqrt(252)  # Annualize daily volatility

    return float(vol)


def _calculate_risk_parity_weights(
    volatilities: Dict[str, float],
    target_vol: float = 0.15
) -> Dict[str, float]:
    """
    Calculate Risk Parity weights.

    Each asset contributes equally to portfolio risk.
    Weight_i = (1/Vol_i) / sum(1/Vol_j for all j)
    """
    if not volatilities or all(v == 0 for v in volatilities.values()):
        # Equal weight fallback
        n = len(volatilities)
        return {k: 1/n for k in volatilities} if n > 0 else {}

    # Inverse volatility weighting
    inv_vols = {k: 1/v if v > 0 else 0 for k, v in volatilities.items()}
    total_inv_vol = sum(inv_vols.values())

    if total_inv_vol == 0:
        n = len(volatilities)
        return {k: 1/n for k in volatilities}

    weights = {k: v/total_inv_vol for k, v in inv_vols.items()}

    # Scale to target volatility
    # Portfolio vol = sqrt(sum(w_i^2 * vol_i^2)) for uncorrelated assets
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
    """
    Calculate fixed fractional position size.

    Position Size = (Account * Risk%) / Stop Loss %
    """
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
    """
    Calculate position size to achieve target volatility.

    Weight = Target Vol / Asset Vol
    """
    if asset_vol == 0 or current_price == 0:
        return 0.0, 0

    weight = target_vol / asset_vol
    weight = min(weight, 1.0)  # Cap at 100%

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
    # Max position size constraint
    constrained = min(position_fraction, max_position)

    # Portfolio risk constraint
    if current_portfolio_risk + constrained > max_portfolio_risk * 10:  # Rough check
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


def _get_risk_parameters(risk_level: RiskLevel) -> Dict[str, float]:
    """Get risk parameters based on risk tolerance."""
    params = {
        RiskLevel.CONSERVATIVE: {
            "max_position": 0.10,
            "risk_per_trade": 0.01,
            "kelly_fraction_used": 0.25,  # Quarter Kelly
            "target_vol": 0.10
        },
        RiskLevel.MODERATE: {
            "max_position": 0.20,
            "risk_per_trade": 0.02,
            "kelly_fraction_used": 0.50,  # Half Kelly
            "target_vol": 0.15
        },
        RiskLevel.AGGRESSIVE: {
            "max_position": 0.30,
            "risk_per_trade": 0.03,
            "kelly_fraction_used": 1.0,  # Full Kelly
            "target_vol": 0.20
        }
    }
    return params.get(risk_level, params[RiskLevel.MODERATE])


# ============================================================================
# Position Sizing Tools
# ============================================================================

@tool
def calculate_kelly_position_size(
    win_rate: Annotated[float, "Historical win rate (0-1)"],
    avg_win_pct: Annotated[float, "Average winning trade return (e.g., 0.05 for 5%)"],
    avg_loss_pct: Annotated[float, "Average losing trade return (e.g., -0.03 for -3%)"],
    account_value: Annotated[float, "Total account value in dollars"],
    current_price: Annotated[float, "Current price of the asset"],
    kelly_fraction: Annotated[float, "Fraction of Kelly to use (0.25, 0.5, or 1.0)"] = 0.5,
) -> str:
    """
    Calculate position size using Kelly Criterion.

    The Kelly Criterion maximizes long-term growth rate but can be volatile.
    Most practitioners use Half-Kelly (0.5) or Quarter-Kelly (0.25) for smoother equity curves.

    Returns optimal position size with risk analysis.
    """
    try:
        # Calculate full Kelly
        full_kelly = _calculate_kelly_fraction(win_rate, avg_win_pct, abs(avg_loss_pct))

        # Apply fraction
        used_kelly = full_kelly * kelly_fraction
        used_kelly = min(used_kelly, 0.25)  # Cap at 25% of account

        # Calculate position
        position_value = account_value * used_kelly
        shares = int(position_value / current_price) if current_price > 0 else 0
        actual_position_value = shares * current_price

        # Risk metrics
        expected_return = (win_rate * avg_win_pct) + ((1 - win_rate) * avg_loss_pct)
        expected_risk = abs(avg_loss_pct) * actual_position_value

        # Interpretation
        interpretation = _interpret_sizing_result(
            SizingMethod.KELLY if kelly_fraction == 1.0 else SizingMethod.HALF_KELLY,
            used_kelly,
            full_kelly
        )

        report = f"""
## Kelly Criterion Position Sizing

### Input Parameters

| Parameter | Value |
|-----------|-------|
| Win Rate | {win_rate:.1%} |
| Avg Win | {avg_win_pct:.2%} |
| Avg Loss | {avg_loss_pct:.2%} |
| Account Value | ${account_value:,.2f} |
| Current Price | ${current_price:.2f} |
| Kelly Fraction Used | {kelly_fraction:.0%} |

### Kelly Calculation

| Metric | Value |
|--------|-------|
| Full Kelly % | {full_kelly:.2%} |
| Adjusted Kelly % | {used_kelly:.2%} |
| Win/Loss Ratio | {abs(avg_win_pct/avg_loss_pct):.2f}x |
| Expected Edge | {expected_return:.2%} per trade |

### Position Size Recommendation

| Metric | Value |
|--------|-------|
| Position Size | {used_kelly:.2%} of account |
| Dollar Amount | ${actual_position_value:,.2f} |
| Number of Shares | {shares:,} |
| Risk at Entry | ${expected_risk:,.2f} |

### Interpretation

{interpretation}

### Risk Warnings
"""
        if full_kelly < 0:
            report += "\n⚠️ **Negative Kelly**: Historical edge is negative. Do not trade."
        if full_kelly > 0.4:
            report += f"\n⚠️ **High Kelly ({full_kelly:.1%})**: Consider reducing position size further."
        if win_rate < 0.4:
            report += f"\n⚠️ **Low Win Rate ({win_rate:.1%})**: Need larger wins to compensate."

        return report.strip()

    except Exception as e:
        return f"Error calculating Kelly position size: {str(e)}"


@tool
def calculate_atr_position_size(
    symbol: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    account_value: Annotated[float, "Total account value in dollars"],
    risk_per_trade: Annotated[float, "Risk per trade as fraction (e.g., 0.02 for 2%)"] = 0.02,
    atr_multiplier: Annotated[float, "ATR multiplier for stop distance (default: 2.0)"] = 2.0,
    atr_period: Annotated[int, "ATR calculation period (default: 14)"] = 14,
) -> str:
    """
    Calculate position size based on ATR (Average True Range).

    ATR-based sizing adjusts position size inversely to volatility:
    - High volatility = smaller position
    - Low volatility = larger position

    This maintains consistent dollar risk across different volatility regimes.
    """
    try:
        # Get price data
        lookback = max(atr_period * 3, 60)
        data = route_to_vendor("get_stock_data", symbol, curr_date, lookback)

        if isinstance(data, str):
            if "error" in data.lower():
                return f"Error retrieving data: {data}"
            from io import StringIO
            df = pd.read_csv(StringIO(data))
        else:
            df = data

        if df.empty or len(df) < atr_period + 1:
            return "Insufficient data for ATR calculation."

        # Calculate ATR
        atr = _calculate_atr(df, atr_period)

        if atr == 0:
            return "ATR calculation returned zero - check data quality."

        # Get current price
        close_col = 'close' if 'close' in df.columns else 'Close'
        current_price = float(df[close_col].iloc[-1])

        # Calculate position size
        dollar_risk = account_value * risk_per_trade
        stop_distance = atr * atr_multiplier

        shares = int(dollar_risk / stop_distance)
        position_value = shares * current_price
        position_fraction = position_value / account_value if account_value > 0 else 0

        # Calculate stop loss level
        stop_loss_price = current_price - stop_distance
        stop_loss_pct = stop_distance / current_price

        # Volatility context
        returns = df[close_col].pct_change().dropna()
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)

        report = f"""
## ATR-Based Position Sizing for {symbol}
Analysis Date: {curr_date}

### Volatility Analysis

| Metric | Value |
|--------|-------|
| ATR ({atr_period}-day) | ${atr:.2f} |
| ATR as % of Price | {(atr/current_price)*100:.2f}% |
| Daily Volatility | {daily_vol:.2%} |
| Annual Volatility | {annual_vol:.2%} |

### Position Size Calculation

| Parameter | Value |
|-----------|-------|
| Account Value | ${account_value:,.2f} |
| Risk Per Trade | {risk_per_trade:.2%} (${dollar_risk:,.2f}) |
| ATR Multiplier | {atr_multiplier}x |
| Stop Distance | ${stop_distance:.2f} ({stop_loss_pct:.2%}) |

### Position Size Recommendation

| Metric | Value |
|--------|-------|
| Position Size | {position_fraction:.2%} of account |
| Dollar Amount | ${position_value:,.2f} |
| Number of Shares | {shares:,} |
| Current Price | ${current_price:.2f} |
| Stop Loss Level | ${stop_loss_price:.2f} |

### Risk Profile

- Max Loss at Stop: ${dollar_risk:,.2f} ({risk_per_trade:.2%} of account)
- Position volatility contribution: {position_fraction * annual_vol:.2%} annual

### Adjustments for Volatility
"""

        if annual_vol > 0.40:
            report += "\n⚠️ **High Volatility**: Position automatically reduced. Consider wider stops."
        elif annual_vol < 0.15:
            report += "\n✅ **Low Volatility**: Larger position size appropriate for risk budget."
        else:
            report += "\n✅ **Normal Volatility**: Standard position sizing applied."

        return report.strip()

    except Exception as e:
        return f"Error calculating ATR position size: {str(e)}"


@tool
def calculate_risk_parity_allocation(
    symbols: Annotated[str, "Comma-separated list of ticker symbols"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    account_value: Annotated[float, "Total account value in dollars"],
    target_volatility: Annotated[float, "Target portfolio volatility (e.g., 0.15 for 15%)"] = 0.15,
    lookback_days: Annotated[int, "Days of history for volatility calculation"] = 60,
) -> str:
    """
    Calculate Risk Parity allocation across multiple assets.

    Risk Parity equalizes the risk contribution from each asset,
    so lower volatility assets get higher weights and vice versa.

    Returns optimal allocation with individual position sizes.
    """
    try:
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(",")]

        if len(symbol_list) < 2:
            return "Risk Parity requires at least 2 assets."

        # Get data and calculate volatilities
        volatilities = {}
        prices = {}

        for symbol in symbol_list:
            try:
                data = route_to_vendor("get_stock_data", symbol, curr_date, lookback_days + 20)

                if isinstance(data, str):
                    if "error" in data.lower():
                        continue
                    from io import StringIO
                    df = pd.read_csv(StringIO(data))
                else:
                    df = data

                if df.empty:
                    continue

                close_col = 'close' if 'close' in df.columns else 'Close'
                returns = df[close_col].pct_change().dropna()

                vol = _calculate_volatility(returns, annualize=True)
                volatilities[symbol] = vol
                prices[symbol] = float(df[close_col].iloc[-1])

            except Exception:
                continue

        if len(volatilities) < 2:
            return "Insufficient data for Risk Parity calculation."

        # Calculate weights
        weights = _calculate_risk_parity_weights(volatilities, target_volatility)

        # Calculate position sizes
        allocations = {}
        total_allocated = 0

        for symbol in weights:
            weight = weights[symbol]
            dollar_value = account_value * weight
            price = prices.get(symbol, 1)
            shares = int(dollar_value / price)
            actual_value = shares * price
            total_allocated += actual_value

            allocations[symbol] = {
                "weight": weight,
                "volatility": volatilities[symbol],
                "dollar_value": actual_value,
                "shares": shares,
                "price": price
            }

        # Portfolio metrics
        port_vol = np.sqrt(sum((weights[s]**2) * (volatilities[s]**2) for s in weights))

        # Calculate risk contribution
        risk_contributions = {}
        for s in weights:
            # Marginal contribution to risk (simplified for uncorrelated)
            risk_contributions[s] = (weights[s]**2 * volatilities[s]**2) / (port_vol**2) if port_vol > 0 else 0

        report = f"""
## Risk Parity Allocation
Analysis Date: {curr_date}
Target Volatility: {target_volatility:.1%}

### Asset Volatilities

| Symbol | Annual Vol | Inverse Weight |
|--------|------------|----------------|
"""
        for symbol in sorted(volatilities.keys(), key=lambda x: volatilities[x]):
            vol = volatilities[symbol]
            inv_weight = (1/vol) / sum(1/v if v > 0 else 0 for v in volatilities.values()) if vol > 0 else 0
            report += f"| {symbol} | {vol:.1%} | {inv_weight:.2%} |\n"

        report += f"""
### Risk Parity Weights

| Symbol | Weight | Vol | Dollar Value | Shares | Risk Contrib |
|--------|--------|-----|--------------|--------|--------------|
"""
        for symbol, alloc in sorted(allocations.items(), key=lambda x: x[1]["weight"], reverse=True):
            weight = alloc["weight"]
            vol = alloc["volatility"]
            value = alloc["dollar_value"]
            shares = alloc["shares"]
            risk_c = risk_contributions.get(symbol, 0)
            report += f"| {symbol} | {weight:.2%} | {vol:.1%} | ${value:,.0f} | {shares:,} | {risk_c:.1%} |\n"

        report += f"""
### Portfolio Summary

| Metric | Value |
|--------|-------|
| Total Account | ${account_value:,.2f} |
| Total Allocated | ${total_allocated:,.2f} |
| Cash Reserve | ${account_value - total_allocated:,.2f} |
| Portfolio Volatility | {port_vol:.1%} |
| Target Volatility | {target_volatility:.1%} |

### Risk Parity Benefits

1. **Equal Risk Contribution**: Each asset contributes similarly to portfolio risk
2. **Volatility Balance**: Lower volatility assets get higher weights
3. **Drawdown Control**: More balanced risk reduces concentration risk

### Rebalancing Triggers
"""
        # Check if rebalancing needed
        avg_risk_contrib = 1.0 / len(risk_contributions) if risk_contributions else 0
        max_drift = max(abs(rc - avg_risk_contrib) for rc in risk_contributions.values()) if risk_contributions else 0

        if max_drift > 0.1:
            report += f"\n⚠️ **Rebalancing Recommended**: Risk contribution drift of {max_drift:.1%} exceeds threshold."
        else:
            report += "\n✅ **Balanced**: Risk contributions are within acceptable range."

        return report.strip()

    except Exception as e:
        return f"Error calculating Risk Parity allocation: {str(e)}"


@tool
def calculate_volatility_target_size(
    symbol: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    account_value: Annotated[float, "Total account value in dollars"],
    target_volatility: Annotated[float, "Target position volatility (e.g., 0.15 for 15%)"] = 0.15,
    lookback_days: Annotated[int, "Days of history for volatility calculation"] = 60,
) -> str:
    """
    Calculate position size to achieve target volatility contribution.

    Volatility targeting sizes positions so each contributes a consistent
    amount of volatility to the portfolio, regardless of the asset's inherent vol.

    Returns position size scaled to target volatility.
    """
    try:
        # Get price data
        data = route_to_vendor("get_stock_data", symbol, curr_date, lookback_days + 20)

        if isinstance(data, str):
            if "error" in data.lower():
                return f"Error retrieving data: {data}"
            from io import StringIO
            df = pd.read_csv(StringIO(data))
        else:
            df = data

        if df.empty or len(df) < 20:
            return "Insufficient data for volatility calculation."

        # Calculate asset volatility
        close_col = 'close' if 'close' in df.columns else 'Close'
        current_price = float(df[close_col].iloc[-1])
        returns = df[close_col].pct_change().dropna()

        asset_vol = _calculate_volatility(returns, annualize=True)

        if asset_vol == 0:
            return "Asset volatility is zero - cannot calculate target size."

        # Calculate position size
        position_fraction, shares = _calculate_volatility_target_size(
            account_value, target_volatility, asset_vol, current_price
        )

        position_value = shares * current_price

        # Calculate expected contribution
        position_vol_contribution = position_fraction * asset_vol

        # Historical volatility metrics
        vol_20d = returns.iloc[-20:].std() * np.sqrt(252) if len(returns) >= 20 else asset_vol
        vol_60d = returns.iloc[-60:].std() * np.sqrt(252) if len(returns) >= 60 else asset_vol

        report = f"""
## Volatility Target Position Sizing for {symbol}
Analysis Date: {curr_date}

### Volatility Analysis

| Period | Annualized Volatility |
|--------|----------------------|
| 20-day | {vol_20d:.1%} |
| 60-day | {vol_60d:.1%} |
| Full Period | {asset_vol:.1%} |

### Volatility Targeting Calculation

| Parameter | Value |
|-----------|-------|
| Target Volatility | {target_volatility:.1%} |
| Asset Volatility | {asset_vol:.1%} |
| Scaling Factor | {target_volatility/asset_vol:.2f}x |

### Position Size Recommendation

| Metric | Value |
|--------|-------|
| Position Size | {position_fraction:.2%} of account |
| Dollar Amount | ${position_value:,.2f} |
| Number of Shares | {shares:,} |
| Current Price | ${current_price:.2f} |
| Vol Contribution | {position_vol_contribution:.1%} |

### Volatility Regime Assessment
"""
        # Volatility regime
        if vol_20d > vol_60d * 1.3:
            report += "\n⚠️ **Rising Volatility**: Recent vol higher than historical. Consider reducing size."
            report += f"\n   Suggested adjustment: {(vol_60d/vol_20d)*100:.0f}% of calculated size."
        elif vol_20d < vol_60d * 0.7:
            report += "\n📈 **Declining Volatility**: Recent vol lower than historical. Current size appropriate."
        else:
            report += "\n✅ **Stable Volatility**: No regime change detected."

        report += f"""

### Leverage Implications
"""
        if position_fraction > 1.0:
            report += f"\n⚠️ **Leverage Required**: Target vol requires {position_fraction:.1%} position."
            report += "\nConsider reducing target volatility or accepting lower contribution."
        else:
            report += f"\n✅ **No Leverage**: Position is within account bounds."

        return report.strip()

    except Exception as e:
        return f"Error calculating volatility target size: {str(e)}"


@tool
def get_position_sizing_recommendation(
    symbol: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    account_value: Annotated[float, "Total account value in dollars"],
    win_rate: Annotated[float, "Historical win rate (0-1)"] = 0.5,
    avg_win_pct: Annotated[float, "Average winning trade return"] = 0.05,
    avg_loss_pct: Annotated[float, "Average losing trade return"] = -0.03,
    risk_level: Annotated[str, "Risk tolerance: conservative, moderate, aggressive"] = "moderate",
) -> str:
    """
    Get comprehensive position sizing recommendation using multiple methods.

    Compares Kelly, ATR, Volatility Target, and Fixed Fractional sizing
    to provide a balanced recommendation based on risk tolerance.

    Returns comparison of sizing methods with final recommendation.
    """
    try:
        # Get risk parameters
        try:
            risk = RiskLevel(risk_level.lower())
        except ValueError:
            risk = RiskLevel.MODERATE

        params = _get_risk_parameters(risk)

        # Get price data
        data = route_to_vendor("get_stock_data", symbol, curr_date, 90)

        if isinstance(data, str):
            if "error" in data.lower():
                return f"Error retrieving data: {data}"
            from io import StringIO
            df = pd.read_csv(StringIO(data))
        else:
            df = data

        if df.empty or len(df) < 20:
            return "Insufficient data for position sizing."

        close_col = 'close' if 'close' in df.columns else 'Close'
        current_price = float(df[close_col].iloc[-1])
        returns = df[close_col].pct_change().dropna()
        asset_vol = _calculate_volatility(returns, annualize=True)
        atr = _calculate_atr(df)

        # Calculate each method
        methods = {}

        # Kelly
        full_kelly = _calculate_kelly_fraction(win_rate, avg_win_pct, abs(avg_loss_pct))
        kelly_size = full_kelly * params["kelly_fraction_used"]
        kelly_size = min(kelly_size, params["max_position"])
        methods["Kelly"] = {
            "fraction": kelly_size,
            "value": kelly_size * account_value,
            "shares": int((kelly_size * account_value) / current_price)
        }

        # ATR-based
        if atr > 0:
            atr_fraction, atr_shares = _calculate_position_from_atr(
                account_value, params["risk_per_trade"], atr, 2.0, current_price
            )
            atr_fraction = min(atr_fraction, params["max_position"])
            methods["ATR"] = {
                "fraction": atr_fraction,
                "value": atr_shares * current_price,
                "shares": atr_shares
            }

        # Volatility Target
        if asset_vol > 0:
            vol_fraction, vol_shares = _calculate_volatility_target_size(
                account_value, params["target_vol"], asset_vol, current_price
            )
            vol_fraction = min(vol_fraction, params["max_position"])
            methods["Vol Target"] = {
                "fraction": vol_fraction,
                "value": vol_shares * current_price,
                "shares": vol_shares
            }

        # Fixed Fractional
        ff_fraction, ff_shares = _calculate_fixed_fractional(
            account_value, params["risk_per_trade"], 0.05, current_price
        )
        ff_fraction = min(ff_fraction, params["max_position"])
        methods["Fixed Frac"] = {
            "fraction": ff_fraction,
            "value": ff_shares * current_price,
            "shares": ff_shares
        }

        # Calculate consensus (average of non-zero methods)
        valid_fractions = [m["fraction"] for m in methods.values() if m["fraction"] > 0]
        consensus_fraction = np.mean(valid_fractions) if valid_fractions else 0
        consensus_fraction = min(consensus_fraction, params["max_position"])
        consensus_value = consensus_fraction * account_value
        consensus_shares = int(consensus_value / current_price) if current_price > 0 else 0

        report = f"""
## Comprehensive Position Sizing for {symbol}
Analysis Date: {curr_date}
Risk Level: {risk.value.title()}

### Asset Analysis

| Metric | Value |
|--------|-------|
| Current Price | ${current_price:.2f} |
| Annual Volatility | {asset_vol:.1%} |
| 14-day ATR | ${atr:.2f} ({(atr/current_price)*100:.1f}% of price) |

### Trading Edge Analysis

| Metric | Value |
|--------|-------|
| Win Rate | {win_rate:.1%} |
| Avg Win | {avg_win_pct:.2%} |
| Avg Loss | {avg_loss_pct:.2%} |
| Win/Loss Ratio | {abs(avg_win_pct/avg_loss_pct):.2f}x |
| Full Kelly | {full_kelly:.2%} |

### Position Sizing Comparison

| Method | Position % | Dollar Value | Shares |
|--------|-----------|--------------|--------|
"""
        for method_name, result in methods.items():
            report += f"| {method_name} | {result['fraction']:.2%} | ${result['value']:,.0f} | {result['shares']:,} |\n"

        report += f"""| **Consensus** | **{consensus_fraction:.2%}** | **${consensus_value:,.0f}** | **{consensus_shares:,}** |

### Final Recommendation

Based on your {risk.value} risk profile:

| Parameter | Value |
|-----------|-------|
| Max Position Size | {params['max_position']:.0%} |
| Risk Per Trade | {params['risk_per_trade']:.1%} |
| Target Volatility | {params['target_vol']:.0%} |

**Recommended Position**: {consensus_shares:,} shares (${consensus_value:,.0f})
**Recommended Stop Loss**: ${current_price - atr*2:.2f} (2x ATR below entry)

### Method Notes
"""
        # Add specific notes
        if full_kelly < 0:
            report += "\n⚠️ **Kelly Warning**: Negative Kelly suggests no statistical edge."
        if consensus_fraction > params["max_position"] * 0.8:
            report += f"\n⚠️ **Size Warning**: Near maximum position limit ({params['max_position']:.0%})."
        if asset_vol > 0.40:
            report += "\n⚠️ **Volatility Warning**: High volatility asset - consider reduced size."

        return report.strip()

    except Exception as e:
        return f"Error calculating position sizing recommendation: {str(e)}"


# ============================================================================
# Position Sizing Manager Factory
# ============================================================================

def create_position_sizing_manager(llm):
    """
    Factory function to create the Position Sizing Manager agent.

    Args:
        llm: Language model to use for the agent

    Returns:
        Callable node function for the agent graph
    """
    tools = [
        calculate_kelly_position_size,
        calculate_atr_position_size,
        calculate_risk_parity_allocation,
        calculate_volatility_target_size,
        get_position_sizing_recommendation
    ]

    tool_names = ", ".join([t.name for t in tools])

    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are a specialized Position Sizing Manager focused on optimal
position size calculation and risk management.

You have access to these tools: {tool_names}

Your expertise includes:
1. Kelly Criterion calculations for edge-based sizing
2. ATR-based position sizing for volatility adjustment
3. Risk Parity allocation for portfolio balancing
4. Volatility targeting for consistent risk contribution
5. Fixed fractional sizing for controlled risk

When calculating position sizes:
- Always consider the trader's risk tolerance level
- Account for current market volatility
- Provide multiple sizing methods for comparison
- Include stop loss recommendations
- Warn about over-sizing or under-sizing

Key principles:
- Never risk more than 2-3% of account on a single trade
- Use fractional Kelly (half or quarter) to reduce variance
- Adjust size for volatility regime changes
- Consider transaction costs for very small positions

Be precise with numbers and always show your calculations."""),
        MessagesPlaceholder(variable_name="messages"),
    ])

    chain = prompt | llm.bind_tools(tools)

    def position_sizing_node(state):
        """Execute the Position Sizing Manager agent."""
        messages = state.get("messages", [])
        trade_date = state.get("trade_date", "")
        company = state.get("company_of_interest", "")

        # Add context if not in messages
        if trade_date and company:
            context_msg = f"Calculate position sizing for {company} as of {trade_date}."
            from langchain_core.messages import HumanMessage
            if not any(context_msg in str(m) for m in messages):
                messages = [HumanMessage(content=context_msg)] + list(messages)

        response = chain.invoke({"messages": messages})

        # Extract report from tool responses
        report = ""
        if hasattr(response, 'tool_calls') and response.tool_calls:
            report = "Position sizing calculated. See tool results for details."
        elif hasattr(response, 'content'):
            report = response.content

        return {
            "messages": [response],
            "position_sizing_report": report
        }

    return position_sizing_node
