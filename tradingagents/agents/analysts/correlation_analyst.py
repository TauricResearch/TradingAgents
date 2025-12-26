"""Correlation Analyst Agent.

Specializes in cross-asset correlation analysis and sector rotation detection:
- Cross-asset correlation (stocks vs bonds, commodities, currencies)
- Sector rotation analysis and leadership changes
- Rolling correlation calculations
- Correlation breakdown detection (regime changes)
- Inter-market analysis for divergence signals

Issue #15: [AGENT-14] Correlation Analyst - cross-asset, sector rotation
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from typing import Annotated, Dict, Any, List, Optional
from enum import Enum
import pandas as pd
import numpy as np

from tradingagents.agents.utils.agent_utils import get_stock_data
from tradingagents.dataflows.interface import route_to_vendor


# ============================================================================
# Correlation Enums
# ============================================================================

class CorrelationStrength(str, Enum):
    """Classification of correlation strength."""
    VERY_STRONG_POSITIVE = "very_strong_positive"
    STRONG_POSITIVE = "strong_positive"
    MODERATE_POSITIVE = "moderate_positive"
    WEAK_POSITIVE = "weak_positive"
    NEGLIGIBLE = "negligible"
    WEAK_NEGATIVE = "weak_negative"
    MODERATE_NEGATIVE = "moderate_negative"
    STRONG_NEGATIVE = "strong_negative"
    VERY_STRONG_NEGATIVE = "very_strong_negative"


class SectorPhase(str, Enum):
    """Economic cycle phase for sector rotation."""
    EARLY_CYCLE = "early_cycle"
    MID_CYCLE = "mid_cycle"
    LATE_CYCLE = "late_cycle"
    RECESSION = "recession"


class SectorLeadership(str, Enum):
    """Sector leadership classification."""
    LEADING = "leading"
    LAGGING = "lagging"
    IMPROVING = "improving"
    WEAKENING = "weakening"


# ============================================================================
# Helper Functions
# ============================================================================

def _calculate_correlation(series1: pd.Series, series2: pd.Series) -> float:
    """Calculate Pearson correlation between two series."""
    if len(series1) < 2 or len(series2) < 2:
        return 0.0
    # Align series lengths
    min_len = min(len(series1), len(series2))
    s1 = series1.iloc[-min_len:].values
    s2 = series2.iloc[-min_len:].values

    # Handle constant series
    if np.std(s1) == 0 or np.std(s2) == 0:
        return 0.0

    return float(np.corrcoef(s1, s2)[0, 1])


def _calculate_rolling_correlation(
    series1: pd.Series,
    series2: pd.Series,
    window: int = 20
) -> pd.Series:
    """Calculate rolling correlation between two series."""
    if len(series1) < window or len(series2) < window:
        return pd.Series([])

    min_len = min(len(series1), len(series2))
    s1 = series1.iloc[-min_len:]
    s2 = series2.iloc[-min_len:]

    rolling_corr = s1.rolling(window=window).corr(s2)
    return rolling_corr.dropna()


def _classify_correlation(corr: float) -> CorrelationStrength:
    """Classify correlation coefficient into strength categories."""
    if corr >= 0.8:
        return CorrelationStrength.VERY_STRONG_POSITIVE
    elif corr >= 0.6:
        return CorrelationStrength.STRONG_POSITIVE
    elif corr >= 0.4:
        return CorrelationStrength.MODERATE_POSITIVE
    elif corr >= 0.2:
        return CorrelationStrength.WEAK_POSITIVE
    elif corr > -0.2:
        return CorrelationStrength.NEGLIGIBLE
    elif corr > -0.4:
        return CorrelationStrength.WEAK_NEGATIVE
    elif corr > -0.6:
        return CorrelationStrength.MODERATE_NEGATIVE
    elif corr > -0.8:
        return CorrelationStrength.STRONG_NEGATIVE
    else:
        return CorrelationStrength.VERY_STRONG_NEGATIVE


def _detect_correlation_breakdown(
    rolling_corr: pd.Series,
    threshold_change: float = 0.3
) -> Dict[str, Any]:
    """Detect significant correlation breakdown events."""
    if len(rolling_corr) < 10:
        return {"detected": False, "details": "Insufficient data"}

    # Calculate correlation changes
    corr_diff = rolling_corr.diff()

    # Look for large changes
    large_changes = corr_diff[abs(corr_diff) > threshold_change]

    if len(large_changes) == 0:
        return {"detected": False, "details": "No significant correlation changes"}

    # Get the most recent significant change
    recent_change = corr_diff.iloc[-20:] if len(corr_diff) >= 20 else corr_diff
    max_change_idx = recent_change.abs().idxmax()
    max_change = recent_change.loc[max_change_idx]

    return {
        "detected": abs(max_change) > threshold_change,
        "change_magnitude": float(max_change),
        "direction": "increasing" if max_change > 0 else "decreasing",
        "current_correlation": float(rolling_corr.iloc[-1]),
        "prior_correlation": float(rolling_corr.iloc[-1] - max_change)
    }


def _calculate_relative_strength(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = 20
) -> pd.Series:
    """Calculate relative strength vs benchmark."""
    if len(returns) < window or len(benchmark_returns) < window:
        return pd.Series([])

    min_len = min(len(returns), len(benchmark_returns))
    ret = returns.iloc[-min_len:]
    bench = benchmark_returns.iloc[-min_len:]

    # Cumulative returns ratio
    cum_ret = (1 + ret).cumprod()
    cum_bench = (1 + bench).cumprod()

    relative_strength = cum_ret / cum_bench
    return relative_strength


def _classify_sector_leadership(
    relative_strength: pd.Series,
    window: int = 20
) -> SectorLeadership:
    """Classify sector leadership based on relative strength trend."""
    if len(relative_strength) < window:
        return SectorLeadership.LAGGING

    recent = relative_strength.iloc[-window:]

    # Calculate trend
    rs_start = recent.iloc[0]
    rs_end = recent.iloc[-1]
    rs_mid = recent.iloc[window//2]

    current_vs_start = (rs_end - rs_start) / rs_start if rs_start != 0 else 0
    current_vs_mid = (rs_end - rs_mid) / rs_mid if rs_mid != 0 else 0

    if rs_end > 1 and current_vs_start > 0.02:
        return SectorLeadership.LEADING
    elif rs_end > 1 and current_vs_start < 0:
        return SectorLeadership.WEAKENING
    elif rs_end < 1 and current_vs_start > 0:
        return SectorLeadership.IMPROVING
    else:
        return SectorLeadership.LAGGING


def _identify_cycle_phase(indicators: Dict[str, float]) -> SectorPhase:
    """Identify economic cycle phase from market indicators."""
    # Simplified cycle identification based on key metrics
    yield_curve_slope = indicators.get('yield_curve_slope', 0)
    leading_index = indicators.get('leading_index', 0)
    pmi = indicators.get('pmi', 50)

    if pmi > 50 and leading_index > 0 and yield_curve_slope > 0:
        return SectorPhase.EARLY_CYCLE
    elif pmi > 50 and leading_index > 0:
        return SectorPhase.MID_CYCLE
    elif pmi > 50 and leading_index < 0:
        return SectorPhase.LATE_CYCLE
    else:
        return SectorPhase.RECESSION


def _get_cycle_sector_recommendations(phase: SectorPhase) -> Dict[str, List[str]]:
    """Get sector recommendations for each cycle phase."""
    recommendations = {
        SectorPhase.EARLY_CYCLE: {
            "overweight": ["XLF", "XLY", "XLI", "XLB"],  # Financials, Consumer Discretionary, Industrials, Materials
            "underweight": ["XLP", "XLU", "XLRE"],  # Consumer Staples, Utilities, Real Estate
            "rationale": "Economic recovery favors cyclical sectors with high operating leverage"
        },
        SectorPhase.MID_CYCLE: {
            "overweight": ["XLK", "XLI", "XLB"],  # Technology, Industrials, Materials
            "underweight": ["XLU", "XLP"],  # Utilities, Consumer Staples
            "rationale": "Sustained growth benefits sectors with secular trends and industrial production"
        },
        SectorPhase.LATE_CYCLE: {
            "overweight": ["XLE", "XLB", "XLI"],  # Energy, Materials, Industrials
            "underweight": ["XLK", "XLY", "XLF"],  # Tech, Consumer Discretionary, Financials
            "rationale": "Inflation hedge and commodity exposure preferred as cycle matures"
        },
        SectorPhase.RECESSION: {
            "overweight": ["XLU", "XLP", "XLV"],  # Utilities, Consumer Staples, Healthcare
            "underweight": ["XLY", "XLI", "XLB"],  # Consumer Discretionary, Industrials, Materials
            "rationale": "Defensive sectors with stable cash flows outperform during contractions"
        }
    }
    return recommendations.get(phase, {"overweight": [], "underweight": [], "rationale": "Unknown phase"})


def _interpret_cross_asset_correlation(
    stock_bond_corr: float,
    stock_gold_corr: float,
    stock_oil_corr: float
) -> str:
    """Interpret cross-asset correlations for market regime."""
    interpretations = []

    # Stock-Bond correlation (typically negative in normal markets)
    if stock_bond_corr > 0.3:
        interpretations.append("RISK-OFF REGIME: Positive stock-bond correlation suggests flight to quality")
    elif stock_bond_corr < -0.3:
        interpretations.append("NORMAL REGIME: Negative stock-bond correlation indicates balanced risk appetite")
    else:
        interpretations.append("TRANSITIONAL REGIME: Low stock-bond correlation may signal regime change")

    # Stock-Gold correlation
    if stock_gold_corr < -0.3:
        interpretations.append("HEDGING ACTIVE: Gold acting as portfolio hedge against equity risk")
    elif stock_gold_corr > 0.3:
        interpretations.append("LIQUIDITY DRIVEN: Both assets rising suggests monetary expansion")

    # Stock-Oil correlation
    if stock_oil_corr > 0.5:
        interpretations.append("GROWTH SENSITIVE: Strong stock-oil correlation reflects economic growth expectations")
    elif stock_oil_corr < -0.3:
        interpretations.append("SUPPLY SHOCK: Negative correlation may indicate energy cost pressure on equities")

    return "\n".join(interpretations) if interpretations else "Normal cross-asset relationships"


def _format_correlation_signal(corr: float) -> str:
    """Format correlation value with directional signal."""
    strength = _classify_correlation(corr)
    if corr > 0:
        return f"+{corr:.3f} ({strength.value.replace('_', ' ').title()})"
    else:
        return f"{corr:.3f} ({strength.value.replace('_', ' ').title()})"


# ============================================================================
# Correlation Analysis Tools
# ============================================================================

# Sector ETFs for rotation analysis
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services"
}

# Cross-asset benchmarks
CROSS_ASSET_SYMBOLS = {
    "SPY": "S&P 500 (Equities)",
    "TLT": "Long-term Treasuries (Bonds)",
    "GLD": "Gold",
    "USO": "Oil",
    "UUP": "US Dollar Index"
}


@tool
def get_cross_asset_correlation_analysis(
    symbol: Annotated[str, "Ticker symbol to analyze correlations for"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    lookback_days: Annotated[int, "Days of history for correlation (default: 60)"] = 60,
) -> str:
    """
    Analyze cross-asset correlations to understand market regime and diversification.

    Examines correlations between the target asset and:
    - Bonds (TLT) - risk-on/off indicator
    - Gold (GLD) - safe haven correlation
    - Oil (USO) - economic growth sensitivity
    - Dollar (UUP) - currency risk exposure

    Returns comprehensive cross-asset correlation analysis with regime interpretation.
    """
    try:
        # Get data for all assets
        assets_data = {}

        # Get target symbol data
        target_data = route_to_vendor("get_stock_data", symbol, curr_date, lookback_days + 20)
        if isinstance(target_data, str) and "error" in target_data.lower():
            return f"Error retrieving data for {symbol}: {target_data}"

        if isinstance(target_data, str):
            from io import StringIO
            assets_data[symbol] = pd.read_csv(StringIO(target_data))
        else:
            assets_data[symbol] = target_data

        # Get cross-asset data
        cross_assets = ["TLT", "GLD", "USO", "UUP"]
        for asset in cross_assets:
            try:
                data = route_to_vendor("get_stock_data", asset, curr_date, lookback_days + 20)
                if isinstance(data, str) and "error" not in data.lower():
                    from io import StringIO
                    assets_data[asset] = pd.read_csv(StringIO(data))
                elif not isinstance(data, str):
                    assets_data[asset] = data
            except Exception:
                continue

        if len(assets_data) < 2:
            return "Insufficient cross-asset data available for correlation analysis."

        # Calculate returns
        returns_data = {}
        for asset, df in assets_data.items():
            close_col = 'close' if 'close' in df.columns else 'Close'
            if close_col in df.columns:
                returns_data[asset] = df[close_col].pct_change().dropna()

        # Calculate correlations with target
        correlations = {}
        rolling_correlations = {}

        target_returns = returns_data.get(symbol)
        if target_returns is None or len(target_returns) < 20:
            return "Insufficient return data for target symbol."

        for asset in cross_assets:
            if asset in returns_data:
                asset_returns = returns_data[asset]
                corr = _calculate_correlation(target_returns, asset_returns)
                correlations[asset] = corr
                rolling_correlations[asset] = _calculate_rolling_correlation(
                    target_returns, asset_returns, window=20
                )

        # Detect correlation breakdowns
        breakdowns = {}
        for asset, rolling in rolling_correlations.items():
            if len(rolling) > 0:
                breakdowns[asset] = _detect_correlation_breakdown(rolling)

        # Interpret regime
        stock_bond_corr = correlations.get("TLT", 0)
        stock_gold_corr = correlations.get("GLD", 0)
        stock_oil_corr = correlations.get("USO", 0)
        regime_interpretation = _interpret_cross_asset_correlation(
            stock_bond_corr, stock_gold_corr, stock_oil_corr
        )

        # Build report
        report = f"""
## Cross-Asset Correlation Analysis for {symbol}
Analysis Date: {curr_date}
Lookback Period: {lookback_days} days

### Correlation Matrix

| Asset | Description | Correlation | Strength |
|-------|-------------|-------------|----------|
"""
        for asset in cross_assets:
            if asset in correlations:
                corr = correlations[asset]
                desc = CROSS_ASSET_SYMBOLS.get(asset, asset)
                strength = _classify_correlation(corr)
                signal = "🟢" if corr > 0.3 else ("🔴" if corr < -0.3 else "⚪")
                report += f"| {asset} | {desc} | {corr:.3f} | {signal} {strength.value.replace('_', ' ')} |\n"

        report += f"""
### Market Regime Interpretation

{regime_interpretation}

### Correlation Breakdown Detection
"""

        for asset, breakdown in breakdowns.items():
            if breakdown.get("detected"):
                direction = breakdown.get("direction", "unknown")
                magnitude = breakdown.get("change_magnitude", 0)
                report += f"\n⚠️ **{asset}**: Significant correlation {direction} (change: {magnitude:.3f})"

        if not any(b.get("detected", False) for b in breakdowns.values()):
            report += "\n✅ No significant correlation breakdowns detected."

        report += f"""

### Portfolio Implications

1. **Diversification**: """

        # Assess diversification
        avg_abs_corr = np.mean([abs(c) for c in correlations.values()])
        if avg_abs_corr < 0.3:
            report += "Strong diversification potential with low cross-asset correlations.\n"
        elif avg_abs_corr < 0.5:
            report += "Moderate diversification - some hedging benefit available.\n"
        else:
            report += "Limited diversification - high correlation with other assets.\n"

        report += "\n2. **Hedging Opportunities**:\n"
        for asset, corr in correlations.items():
            if corr < -0.3:
                report += f"   - {asset} ({CROSS_ASSET_SYMBOLS.get(asset, asset)}): Potential hedge (corr: {corr:.3f})\n"

        if all(c > -0.3 for c in correlations.values()):
            report += "   - No strong negative correlations for hedging.\n"

        return report.strip()

    except Exception as e:
        return f"Error in cross-asset correlation analysis: {str(e)}"


@tool
def get_sector_rotation_analysis(
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    lookback_days: Annotated[int, "Days of history for analysis (default: 60)"] = 60,
) -> str:
    """
    Analyze sector rotation patterns and identify leadership changes.

    Examines all 11 S&P 500 sector ETFs to:
    - Calculate relative strength vs SPY benchmark
    - Identify leading and lagging sectors
    - Detect sector rotation patterns
    - Provide cycle-based sector recommendations

    Returns comprehensive sector rotation analysis with actionable signals.
    """
    try:
        # Get benchmark data (SPY)
        spy_data = route_to_vendor("get_stock_data", "SPY", curr_date, lookback_days + 20)
        if isinstance(spy_data, str) and "error" in spy_data.lower():
            return f"Error retrieving benchmark data: {spy_data}"

        if isinstance(spy_data, str):
            from io import StringIO
            spy_df = pd.read_csv(StringIO(spy_data))
        else:
            spy_df = spy_data

        close_col = 'close' if 'close' in spy_df.columns else 'Close'
        spy_returns = spy_df[close_col].pct_change().dropna()

        # Get sector data
        sector_analysis = {}

        for etf, sector_name in SECTOR_ETFS.items():
            try:
                sector_data = route_to_vendor("get_stock_data", etf, curr_date, lookback_days + 20)

                if isinstance(sector_data, str):
                    if "error" in sector_data.lower():
                        continue
                    from io import StringIO
                    sector_df = pd.read_csv(StringIO(sector_data))
                else:
                    sector_df = sector_data

                if sector_df.empty:
                    continue

                close_col = 'close' if 'close' in sector_df.columns else 'Close'
                sector_returns = sector_df[close_col].pct_change().dropna()

                # Calculate metrics
                relative_strength = _calculate_relative_strength(sector_returns, spy_returns)
                if len(relative_strength) < 5:
                    continue

                leadership = _classify_sector_leadership(relative_strength)
                correlation = _calculate_correlation(sector_returns, spy_returns)

                # Performance metrics
                total_return = (sector_df[close_col].iloc[-1] / sector_df[close_col].iloc[0] - 1) * 100
                spy_total_return = (spy_df[close_col].iloc[-1] / spy_df[close_col].iloc[0] - 1) * 100
                relative_return = total_return - spy_total_return

                sector_analysis[etf] = {
                    "name": sector_name,
                    "leadership": leadership,
                    "relative_strength": float(relative_strength.iloc[-1]) if len(relative_strength) > 0 else 1.0,
                    "correlation": correlation,
                    "total_return": total_return,
                    "relative_return": relative_return
                }

            except Exception:
                continue

        if len(sector_analysis) < 3:
            return "Insufficient sector data available for rotation analysis."

        # Sort sectors by relative strength
        sorted_sectors = sorted(
            sector_analysis.items(),
            key=lambda x: x[1]["relative_strength"],
            reverse=True
        )

        # Identify leaders and laggards
        leaders = [s for s in sorted_sectors[:3]]
        laggards = [s for s in sorted_sectors[-3:]]

        # Determine cycle phase from sector leadership patterns
        # Simplified: if defensives leading -> late cycle/recession, if cyclicals -> early/mid cycle
        defensive_sectors = {"XLU", "XLP", "XLV"}
        cyclical_sectors = {"XLY", "XLF", "XLI", "XLB"}

        defensive_avg_rs = np.mean([
            sector_analysis[s]["relative_strength"]
            for s in defensive_sectors if s in sector_analysis
        ]) if any(s in sector_analysis for s in defensive_sectors) else 1.0

        cyclical_avg_rs = np.mean([
            sector_analysis[s]["relative_strength"]
            for s in cyclical_sectors if s in sector_analysis
        ]) if any(s in sector_analysis for s in cyclical_sectors) else 1.0

        if defensive_avg_rs > cyclical_avg_rs * 1.05:
            inferred_phase = SectorPhase.LATE_CYCLE
        elif cyclical_avg_rs > defensive_avg_rs * 1.05:
            inferred_phase = SectorPhase.EARLY_CYCLE
        else:
            inferred_phase = SectorPhase.MID_CYCLE

        recommendations = _get_cycle_sector_recommendations(inferred_phase)

        # Build report
        report = f"""
## Sector Rotation Analysis
Analysis Date: {curr_date}
Lookback Period: {lookback_days} days

### Sector Performance Rankings

| Rank | ETF | Sector | Relative Strength | Period Return | vs SPY | Leadership |
|------|-----|--------|-------------------|---------------|--------|------------|
"""
        for i, (etf, data) in enumerate(sorted_sectors, 1):
            rs = data["relative_strength"]
            ret = data["total_return"]
            rel_ret = data["relative_return"]
            leadership = data["leadership"].value.replace("_", " ").title()
            signal = "🟢" if rel_ret > 0 else "🔴"
            report += f"| {i} | {etf} | {data['name']} | {rs:.3f} | {ret:.1f}% | {signal} {rel_ret:+.1f}% | {leadership} |\n"

        report += f"""
### Leadership Analysis

**Current Leaders** (Outperforming):
"""
        for etf, data in leaders:
            report += f"- {data['name']} ({etf}): RS={data['relative_strength']:.3f}, {data['leadership'].value.replace('_', ' ')}\n"

        report += f"""
**Current Laggards** (Underperforming):
"""
        for etf, data in laggards:
            report += f"- {data['name']} ({etf}): RS={data['relative_strength']:.3f}, {data['leadership'].value.replace('_', ' ')}\n"

        report += f"""
### Cycle Phase Assessment

**Inferred Phase**: {inferred_phase.value.replace('_', ' ').title()}
- Defensive vs Cyclical RS Ratio: {defensive_avg_rs:.3f} vs {cyclical_avg_rs:.3f}

**Cycle-Based Recommendations**:
- Overweight: {', '.join(recommendations.get('overweight', []))}
- Underweight: {', '.join(recommendations.get('underweight', []))}
- Rationale: {recommendations.get('rationale', 'N/A')}

### Rotation Signals
"""

        # Identify rotation signals
        improving = [s for s, d in sector_analysis.items() if d["leadership"] == SectorLeadership.IMPROVING]
        weakening = [s for s, d in sector_analysis.items() if d["leadership"] == SectorLeadership.WEAKENING]

        if improving:
            report += f"\n🔄 **Improving Sectors** (potential rotation into):\n"
            for etf in improving:
                report += f"   - {sector_analysis[etf]['name']} ({etf})\n"

        if weakening:
            report += f"\n⚠️ **Weakening Sectors** (potential rotation out of):\n"
            for etf in weakening:
                report += f"   - {sector_analysis[etf]['name']} ({etf})\n"

        if not improving and not weakening:
            report += "\n✅ Stable sector dynamics - no clear rotation signals.\n"

        return report.strip()

    except Exception as e:
        return f"Error in sector rotation analysis: {str(e)}"


@tool
def get_correlation_matrix(
    symbols: Annotated[str, "Comma-separated list of ticker symbols"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    lookback_days: Annotated[int, "Days of history for correlation (default: 60)"] = 60,
) -> str:
    """
    Generate correlation matrix for a set of securities.

    Calculates pairwise correlations between all provided symbols,
    useful for portfolio construction and diversification analysis.

    Returns correlation matrix with strength classifications.
    """
    try:
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(",")]

        if len(symbol_list) < 2:
            return "Please provide at least 2 symbols for correlation analysis."

        if len(symbol_list) > 10:
            return "Maximum 10 symbols supported for matrix analysis."

        # Get data for all symbols
        returns_data = {}

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
                returns_data[symbol] = df[close_col].pct_change().dropna()

            except Exception:
                continue

        if len(returns_data) < 2:
            return "Insufficient data available for requested symbols."

        # Build correlation matrix
        available_symbols = list(returns_data.keys())
        n = len(available_symbols)
        corr_matrix = np.zeros((n, n))

        for i, sym1 in enumerate(available_symbols):
            for j, sym2 in enumerate(available_symbols):
                if i == j:
                    corr_matrix[i, j] = 1.0
                elif i < j:
                    corr = _calculate_correlation(returns_data[sym1], returns_data[sym2])
                    corr_matrix[i, j] = corr
                    corr_matrix[j, i] = corr

        # Calculate portfolio metrics
        avg_correlation = np.mean(corr_matrix[np.triu_indices(n, k=1)])
        max_corr = np.max(corr_matrix[np.triu_indices(n, k=1)])
        min_corr = np.min(corr_matrix[np.triu_indices(n, k=1)])

        # Find most/least correlated pairs
        upper_tri = np.triu_indices(n, k=1)
        corr_pairs = [(available_symbols[i], available_symbols[j], corr_matrix[i, j])
                      for i, j in zip(upper_tri[0], upper_tri[1])]
        corr_pairs.sort(key=lambda x: x[2], reverse=True)

        # Build report
        report = f"""
## Correlation Matrix Analysis
Analysis Date: {curr_date}
Lookback Period: {lookback_days} days
Symbols Analyzed: {', '.join(available_symbols)}

### Correlation Matrix

|        | {' | '.join(available_symbols)} |
|--------|{'|'.join(['--------' for _ in available_symbols])}|
"""
        for i, sym in enumerate(available_symbols):
            row = [f"{corr_matrix[i, j]:.2f}" for j in range(n)]
            report += f"| **{sym}** | {' | '.join(row)} |\n"

        report += f"""
### Summary Statistics

- **Average Correlation**: {avg_correlation:.3f}
- **Highest Correlation**: {max_corr:.3f}
- **Lowest Correlation**: {min_corr:.3f}

### Most Correlated Pairs (Top 3)
"""
        for sym1, sym2, corr in corr_pairs[:3]:
            strength = _classify_correlation(corr)
            report += f"- {sym1} ↔ {sym2}: {corr:.3f} ({strength.value.replace('_', ' ')})\n"

        report += f"""
### Least Correlated Pairs (Diversification Opportunities)
"""
        for sym1, sym2, corr in corr_pairs[-3:]:
            strength = _classify_correlation(corr)
            report += f"- {sym1} ↔ {sym2}: {corr:.3f} ({strength.value.replace('_', ' ')})\n"

        report += f"""
### Diversification Assessment

"""
        if avg_correlation < 0.3:
            report += "✅ **Excellent Diversification**: Low average correlation provides strong risk reduction benefits."
        elif avg_correlation < 0.5:
            report += "⚠️ **Moderate Diversification**: Some diversification benefit, but consider adding uncorrelated assets."
        else:
            report += "❌ **Poor Diversification**: High average correlation - portfolio may behave like single asset."

        # Clustering warning
        high_corr_count = sum(1 for _, _, c in corr_pairs if c > 0.7)
        if high_corr_count > 0:
            report += f"\n\n⚠️ Warning: {high_corr_count} pair(s) with correlation > 0.7 - consider consolidating positions."

        return report.strip()

    except Exception as e:
        return f"Error in correlation matrix analysis: {str(e)}"


@tool
def get_rolling_correlation_trend(
    symbol1: Annotated[str, "First ticker symbol"],
    symbol2: Annotated[str, "Second ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    lookback_days: Annotated[int, "Days of history (default: 120)"] = 120,
    window: Annotated[int, "Rolling window size (default: 20)"] = 20,
) -> str:
    """
    Analyze rolling correlation trend between two securities.

    Tracks how correlation evolves over time to detect:
    - Correlation breakdowns (regime changes)
    - Correlation convergence/divergence
    - Hedging relationship stability

    Returns time-series analysis of correlation dynamics.
    """
    try:
        # Get data for both symbols
        data1 = route_to_vendor("get_stock_data", symbol1, curr_date, lookback_days + window)
        data2 = route_to_vendor("get_stock_data", symbol2, curr_date, lookback_days + window)

        if isinstance(data1, str) and "error" in data1.lower():
            return f"Error retrieving data for {symbol1}: {data1}"
        if isinstance(data2, str) and "error" in data2.lower():
            return f"Error retrieving data for {symbol2}: {data2}"

        # Parse data
        if isinstance(data1, str):
            from io import StringIO
            df1 = pd.read_csv(StringIO(data1))
        else:
            df1 = data1

        if isinstance(data2, str):
            from io import StringIO
            df2 = pd.read_csv(StringIO(data2))
        else:
            df2 = data2

        # Calculate returns
        close1 = df1['close'] if 'close' in df1.columns else df1['Close']
        close2 = df2['close'] if 'close' in df2.columns else df2['Close']

        returns1 = close1.pct_change().dropna()
        returns2 = close2.pct_change().dropna()

        # Calculate rolling correlation
        rolling_corr = _calculate_rolling_correlation(returns1, returns2, window)

        if len(rolling_corr) < 10:
            return "Insufficient data for rolling correlation analysis."

        # Analyze trends
        current_corr = rolling_corr.iloc[-1]
        avg_corr = rolling_corr.mean()
        std_corr = rolling_corr.std()
        min_corr = rolling_corr.min()
        max_corr = rolling_corr.max()

        # Recent trend
        recent_corr = rolling_corr.iloc[-20:] if len(rolling_corr) >= 20 else rolling_corr
        trend_direction = "increasing" if recent_corr.iloc[-1] > recent_corr.iloc[0] else "decreasing"

        # Detect breakdowns
        breakdown = _detect_correlation_breakdown(rolling_corr)

        # Stability analysis
        if std_corr < 0.1:
            stability = "STABLE - Correlation remains consistent over time"
        elif std_corr < 0.2:
            stability = "MODERATE - Some variation but generally predictable"
        else:
            stability = "UNSTABLE - High correlation volatility, unreliable for hedging"

        # Build report
        report = f"""
## Rolling Correlation Analysis: {symbol1} ↔ {symbol2}
Analysis Date: {curr_date}
Lookback Period: {lookback_days} days
Rolling Window: {window} days

### Current State

- **Current Correlation**: {current_corr:.3f}
- **Strength**: {_classify_correlation(current_corr).value.replace('_', ' ').title()}
- **Recent Trend**: {trend_direction.title()}

### Historical Statistics

| Metric | Value |
|--------|-------|
| Average | {avg_corr:.3f} |
| Std Dev | {std_corr:.3f} |
| Maximum | {max_corr:.3f} |
| Minimum | {min_corr:.3f} |
| Range | {max_corr - min_corr:.3f} |

### Stability Assessment

{stability}

### Correlation Dynamics
"""

        # Show correlation at key intervals
        intervals = [5, 10, 20, 40, 60]
        report += "\n| Days Ago | Correlation | vs Current |\n|----------|-------------|------------|\n"

        for days in intervals:
            if len(rolling_corr) > days:
                past_corr = rolling_corr.iloc[-(days+1)]
                diff = current_corr - past_corr
                signal = "🟢↑" if diff > 0.1 else ("🔴↓" if diff < -0.1 else "⚪→")
                report += f"| {days} | {past_corr:.3f} | {signal} {diff:+.3f} |\n"

        report += "\n### Breakdown Detection\n"

        if breakdown.get("detected"):
            report += f"""
⚠️ **Correlation Breakdown Detected**
- Direction: {breakdown.get('direction', 'unknown').title()}
- Magnitude: {breakdown.get('change_magnitude', 0):.3f}
- Current: {breakdown.get('current_correlation', 0):.3f}
- Prior: {breakdown.get('prior_correlation', 0):.3f}
"""
        else:
            report += "✅ No significant correlation breakdowns detected.\n"

        report += f"""
### Implications

"""
        if current_corr > 0.7:
            report += "- **High Positive Correlation**: Assets move together; limited diversification benefit.\n"
            report += "- Consider reducing one position if seeking diversification.\n"
        elif current_corr < -0.5:
            report += "- **Strong Negative Correlation**: Excellent hedging pair.\n"
            report += "- Can be used for portfolio protection.\n"
        elif abs(current_corr) < 0.2:
            report += "- **Low Correlation**: Independent movements provide diversification.\n"
            report += "- Good for portfolio construction.\n"
        else:
            report += "- **Moderate Correlation**: Some relationship but not dominant.\n"

        return report.strip()

    except Exception as e:
        return f"Error in rolling correlation analysis: {str(e)}"


# ============================================================================
# Correlation Analyst Factory
# ============================================================================

def create_correlation_analyst(llm):
    """
    Factory function to create the Correlation Analyst agent.

    Args:
        llm: Language model to use for the agent

    Returns:
        Callable node function for the agent graph
    """
    tools = [
        get_cross_asset_correlation_analysis,
        get_sector_rotation_analysis,
        get_correlation_matrix,
        get_rolling_correlation_trend
    ]

    tool_names = ", ".join([t.name for t in tools])

    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are a specialized Correlation Analyst focusing on cross-asset
relationships and sector rotation dynamics.

You have access to these tools: {tool_names}

Your expertise includes:
1. Cross-asset correlation analysis (stocks, bonds, commodities, currencies)
2. Sector rotation patterns and leadership identification
3. Portfolio diversification assessment
4. Correlation breakdown detection for regime changes
5. Rolling correlation trend analysis

When analyzing correlations:
- Consider both current state and historical trends
- Identify correlation breakdowns that may signal regime changes
- Assess diversification implications for portfolio construction
- Provide actionable sector rotation recommendations

Always provide:
- Current correlation metrics with classification
- Historical context and trends
- Diversification and hedging implications
- Specific recommendations based on findings

Be quantitative and precise in your analysis."""),
        MessagesPlaceholder(variable_name="messages"),
    ])

    chain = prompt | llm.bind_tools(tools)

    def correlation_analyst_node(state):
        """Execute the Correlation Analyst agent."""
        messages = state.get("messages", [])
        trade_date = state.get("trade_date", "")
        company = state.get("company_of_interest", "")

        # Add context if not in messages
        if trade_date and company:
            context_msg = f"Analyze correlations for {company} as of {trade_date}."
            from langchain_core.messages import HumanMessage
            if not any(context_msg in str(m) for m in messages):
                messages = [HumanMessage(content=context_msg)] + list(messages)

        response = chain.invoke({"messages": messages})

        # Extract report from tool responses
        report = ""
        if hasattr(response, 'tool_calls') and response.tool_calls:
            report = "Correlation analysis executed. See tool results for details."
        elif hasattr(response, 'content'):
            report = response.content

        return {
            "messages": [response],
            "correlation_report": report
        }

    return correlation_analyst_node
