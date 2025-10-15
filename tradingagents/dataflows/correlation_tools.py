"""
Correlation Analysis Tools
Calculate and analyze correlations between gold and key macro indicators.
Critical for understanding gold's drivers and filtering trade signals.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import io


class CorrelationAnalyzer:
    """Analyze correlations between assets and indicators."""

    # Expected correlations for gold
    EXPECTED_CORRELATIONS = {
        "DXY": -0.75,      # US Dollar Index (strong negative)
        "10Y_YIELD": -0.45,  # 10Y Treasury Yield (negative when nominal)
        "REAL_YIELD": -0.85,  # Real Yield (very strong negative)
        "VIX": 0.40,       # Volatility Index (positive, safe-haven)
        "SPY": -0.20,      # S&P 500 (slightly negative, risk-off)
        "CPI": 0.60,       # Inflation (positive, inflation hedge)
    }

    def __init__(self):
        """Initialize correlation analyzer."""
        pass

    def calculate_correlation(
        self,
        series1_csv: str,
        series2_csv: str,
        window: Optional[int] = None
    ) -> float:
        """
        Calculate correlation between two time series.

        Args:
            series1_csv: CSV data for first series
            series2_csv: CSV data for second series
            window: Rolling window in days (None = full period correlation)

        Returns:
            Correlation coefficient (-1 to 1)
        """
        # Parse CSV data
        df1 = self._parse_csv(series1_csv)
        df2 = self._parse_csv(series2_csv)

        if df1 is None or df2 is None:
            return 0.0

        # Merge on date
        merged = pd.merge(df1, df2, on='date', how='inner', suffixes=('_1', '_2'))

        if len(merged) < 2:
            return 0.0

        # Get value columns (first numeric column after date)
        val1_col = [c for c in merged.columns if c.endswith('_1')][0]
        val2_col = [c for c in merged.columns if c.endswith('_2')][0]

        if window:
            # Rolling correlation
            corr = merged[val1_col].rolling(window).corr(merged[val2_col])
            return corr.iloc[-1] if not pd.isna(corr.iloc[-1]) else 0.0
        else:
            # Full period correlation
            return merged[val1_col].corr(merged[val2_col])

    def _parse_csv(self, csv_data: str) -> Optional[pd.DataFrame]:
        """Parse CSV string to DataFrame with date and value columns."""
        try:
            # Remove comment lines
            lines = [l for l in csv_data.split('\n') if l and not l.startswith('#')]

            if len(lines) < 2:
                return None

            # Read CSV
            df = pd.read_csv(io.StringIO('\n'.join(lines)))

            # Ensure we have date column
            date_col = None
            for col in df.columns:
                if 'date' in col.lower():
                    date_col = col
                    break

            if not date_col:
                # Assume first column is date
                date_col = df.columns[0]

            # Convert to datetime
            df['date'] = pd.to_datetime(df[date_col])

            # Keep date and first numeric column
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if not numeric_cols:
                return None

            return df[['date'] + numeric_cols[:1]]

        except Exception as e:
            print(f"Error parsing CSV: {e}")
            return None

    def calculate_rolling_correlation(
        self,
        series1_csv: str,
        series2_csv: str,
        windows: List[int] = [30, 60, 90, 180]
    ) -> str:
        """
        Calculate multiple rolling correlation windows.

        Args:
            series1_csv: CSV data for first series (e.g., gold)
            series2_csv: CSV data for second series (e.g., DXY)
            windows: List of rolling window sizes in days

        Returns:
            CSV with date and correlation values for each window
        """
        df1 = self._parse_csv(series1_csv)
        df2 = self._parse_csv(series2_csv)

        if df1 is None or df2 is None:
            return "# Error: Could not parse input data"

        # Merge on date
        merged = pd.merge(df1, df2, on='date', how='inner', suffixes=('_1', '_2'))

        if len(merged) < max(windows):
            return "# Error: Insufficient data for correlation calculation"

        # Get value columns
        val1_col = [c for c in merged.columns if c.endswith('_1')][0]
        val2_col = [c for c in merged.columns if c.endswith('_2')][0]

        # Calculate rolling correlations
        csv_lines = ["# Rolling Correlation Analysis"]
        csv_lines.append(f"# Series 1: {val1_col}")
        csv_lines.append(f"# Series 2: {val2_col}")
        csv_lines.append("")

        header = "date," + ",".join([f"corr_{w}d" for w in windows])
        csv_lines.append(header)

        for i, row in merged.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')
            corr_values = []

            for window in windows:
                if i >= window - 1:
                    # Calculate correlation for this window
                    window_data = merged.iloc[max(0, i-window+1):i+1]
                    corr = window_data[val1_col].corr(window_data[val2_col])
                    corr_values.append(f"{corr:.3f}" if not pd.isna(corr) else "")
                else:
                    corr_values.append("")

            csv_lines.append(f"{date_str}," + ",".join(corr_values))

        return "\n".join(csv_lines)

    def analyze_gold_correlations(
        self,
        gold_csv: str,
        dxy_csv: str,
        yields_csv: str,
        vix_csv: Optional[str] = None
    ) -> str:
        """
        Comprehensive correlation analysis for gold trading.

        Args:
            gold_csv: Gold price CSV data
            dxy_csv: US Dollar Index CSV data
            yields_csv: Treasury yields CSV data
            vix_csv: Optional VIX data

        Returns:
            Analysis report with correlation metrics and interpretation
        """
        # Calculate correlations
        gold_dxy_corr = self.calculate_correlation(gold_csv, dxy_csv, window=90)
        gold_yield_corr = self.calculate_correlation(gold_csv, yields_csv, window=90)

        report_lines = [
            "# Gold Correlation Analysis Report",
            f"# Analysis Date: {datetime.now().strftime('%Y-%m-%d')}",
            "",
            "## Current Correlations (90-day rolling)",
            f"Gold vs DXY: {gold_dxy_corr:.3f}",
            f"Gold vs 10Y Yield: {gold_yield_corr:.3f}",
        ]

        if vix_csv:
            gold_vix_corr = self.calculate_correlation(gold_csv, vix_csv, window=90)
            report_lines.append(f"Gold vs VIX: {gold_vix_corr:.3f}")

        # Interpretation
        report_lines.extend([
            "",
            "## Interpretation",
        ])

        # DXY correlation
        if gold_dxy_corr < -0.6:
            report_lines.append("✓ Gold-DXY correlation is strongly negative (healthy)")
            report_lines.append("  → USD weakness should support gold prices")
        elif gold_dxy_corr > -0.3:
            report_lines.append("⚠ Gold-DXY correlation is weakening")
            report_lines.append("  → Gold may be driven by other factors (geopolitics, inflation)")
        else:
            report_lines.append("• Gold-DXY correlation is moderate")

        # Yield correlation
        if gold_yield_corr < -0.5:
            report_lines.append("✓ Gold negatively correlated with yields (as expected)")
            report_lines.append("  → Rising yields = headwind, Falling yields = tailwind")
        elif gold_yield_corr > 0:
            report_lines.append("⚠ Unusual positive correlation with yields")
            report_lines.append("  → May indicate inflation concerns overriding opportunity cost")

        # Trading implications
        report_lines.extend([
            "",
            "## Trading Implications",
            "1. Monitor DXY: Strong USD = reduce gold longs, Weak USD = increase conviction",
            "2. Watch Real Yields: Negative real yields = structural tailwind for gold",
            "3. Correlation Breakdown: When correlations deviate, identify the dominant driver",
        ])

        return "\n".join(report_lines)

    def detect_correlation_regime_change(
        self,
        series1_csv: str,
        series2_csv: str,
        lookback_days: int = 180
    ) -> str:
        """
        Detect if correlation regime has changed significantly.

        Args:
            series1_csv: First time series
            series2_csv: Second time series
            lookback_days: Days to analyze

        Returns:
            Report on correlation regime changes
        """
        # Calculate short-term vs long-term correlation
        corr_30d = self.calculate_correlation(series1_csv, series2_csv, window=30)
        corr_90d = self.calculate_correlation(series1_csv, series2_csv, window=90)
        corr_180d = self.calculate_correlation(series1_csv, series2_csv, window=180)

        report = [
            "# Correlation Regime Analysis",
            "",
            f"30-day correlation: {corr_30d:.3f}",
            f"90-day correlation: {corr_90d:.3f}",
            f"180-day correlation: {corr_180d:.3f}",
            "",
        ]

        # Detect regime change
        if abs(corr_30d - corr_180d) > 0.3:
            report.append("⚠ REGIME CHANGE DETECTED")
            if corr_30d > corr_180d:
                report.append("  → Correlation strengthening in recent period")
            else:
                report.append("  → Correlation weakening in recent period")
            report.append("  → Adjust trading strategy for new correlation regime")
        else:
            report.append("✓ Correlation regime is stable")
            report.append("  → Trading relationships remain consistent")

        return "\n".join(report)


# Standalone functions for tool integration
_correlation_analyzer = None

def _get_correlation_analyzer():
    """Get or create singleton correlation analyzer."""
    global _correlation_analyzer
    if _correlation_analyzer is None:
        _correlation_analyzer = CorrelationAnalyzer()
    return _correlation_analyzer


def calculate_asset_correlation(
    asset1_data: str,
    asset2_data: str,
    window_days: int = 90
) -> str:
    """
    Calculate correlation between two assets.

    For gold trading, key correlations:
    - Gold vs DXY: Expected ~-0.75 (strong negative)
    - Gold vs Real Yields: Expected ~-0.85 (very strong negative)
    - Gold vs VIX: Expected ~+0.40 (positive during risk-off)

    Args:
        asset1_data: CSV data for first asset
        asset2_data: CSV data for second asset
        window_days: Rolling correlation window in days (default 90)

    Returns:
        Correlation coefficient and interpretation
    """
    analyzer = _get_correlation_analyzer()
    corr = analyzer.calculate_correlation(asset1_data, asset2_data, window=window_days)

    result = [
        f"# Asset Correlation Analysis ({window_days}-day window)",
        f"Correlation: {corr:.3f}",
        "",
        "# Interpretation:",
    ]

    if abs(corr) > 0.7:
        result.append(f"{'Strong positive' if corr > 0 else 'Strong negative'} correlation")
    elif abs(corr) > 0.4:
        result.append(f"{'Moderate positive' if corr > 0 else 'Moderate negative'} correlation")
    else:
        result.append("Weak or no correlation")

    return "\n".join(result)


def analyze_gold_macro_correlations(
    gold_data: str,
    dxy_data: str,
    yields_data: str,
    vix_data: Optional[str] = None
) -> str:
    """
    Comprehensive macro correlation analysis for gold.

    Analyzes gold's relationship with:
    - US Dollar Index (DXY): Primary driver
    - Treasury Yields: Opportunity cost factor
    - VIX: Risk sentiment indicator

    Args:
        gold_data: Gold price CSV data
        dxy_data: DXY CSV data
        yields_data: Treasury yields CSV data
        vix_data: Optional VIX data

    Returns:
        Detailed correlation report with trading implications
    """
    analyzer = _get_correlation_analyzer()
    return analyzer.analyze_gold_correlations(gold_data, dxy_data, yields_data, vix_data)


def check_correlation_regime(
    asset1_data: str,
    asset2_data: str
) -> str:
    """
    Check if correlation regime has changed recently.

    Correlation regime changes indicate shifts in market dynamics.
    E.g., Gold-DXY correlation weakening → other factors driving gold.

    Args:
        asset1_data: First asset CSV data
        asset2_data: Second asset CSV data

    Returns:
        Regime change analysis and recommendations
    """
    analyzer = _get_correlation_analyzer()
    return analyzer.detect_correlation_regime_change(asset1_data, asset2_data)


def get_rolling_correlations(
    asset1_data: str,
    asset2_data: str,
    windows: List[int] = None
) -> str:
    """
    Calculate rolling correlations across multiple time windows.

    Useful for understanding correlation stability and trends.

    Args:
        asset1_data: First asset CSV data
        asset2_data: Second asset CSV data
        windows: List of window sizes in days (default: [30, 60, 90, 180])

    Returns:
        CSV with rolling correlations for each window
    """
    if windows is None:
        windows = [30, 60, 90, 180]

    analyzer = _get_correlation_analyzer()
    return analyzer.calculate_rolling_correlation(asset1_data, asset2_data, windows)
