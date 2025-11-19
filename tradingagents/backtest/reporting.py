"""
Reporting and visualization for backtesting.

This module generates comprehensive HTML reports with interactive charts
showing backtest results, performance metrics, and trade analysis.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import io
import base64

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns

from .performance import PerformanceMetrics
from .exceptions import ReportingError


logger = logging.getLogger(__name__)


# Set style
sns.set_style("darkgrid")
plt.rcParams['figure.figsize'] = (12, 6)


class BacktestReporter:
    """
    Generates comprehensive backtest reports.

    Creates HTML reports with embedded charts and statistics.
    """

    def __init__(self):
        """Initialize reporter."""
        logger.info("BacktestReporter initialized")

    def generate_html_report(
        self,
        output_path: str,
        metrics: PerformanceMetrics,
        equity_curve: pd.Series,
        trades: pd.DataFrame,
        benchmark: Optional[pd.Series] = None,
        positions: Optional[pd.DataFrame] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Generate HTML report with charts and statistics.

        Args:
            output_path: Path to save HTML report
            metrics: Performance metrics
            equity_curve: Portfolio value time series
            trades: DataFrame with trade information
            benchmark: Optional benchmark time series
            positions: Optional positions DataFrame
            config: Optional backtest configuration

        Raises:
            ReportingError: If report generation fails
        """
        try:
            logger.info(f"Generating HTML report: {output_path}")

            # Generate all charts
            charts = self._generate_charts(
                equity_curve,
                trades,
                benchmark,
                positions,
                metrics,
            )

            # Generate HTML
            html = self._create_html(
                metrics,
                charts,
                config,
            )

            # Save to file
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                f.write(html)

            logger.info(f"HTML report saved to {output_path}")

        except Exception as e:
            raise ReportingError(f"Failed to generate HTML report: {e}")

    def _generate_charts(
        self,
        equity_curve: pd.Series,
        trades: pd.DataFrame,
        benchmark: Optional[pd.Series],
        positions: Optional[pd.DataFrame],
        metrics: PerformanceMetrics,
    ) -> Dict[str, str]:
        """Generate all charts and return as base64 encoded images."""
        charts = {}

        # Equity curve
        charts['equity_curve'] = self._plot_equity_curve(equity_curve, benchmark)

        # Drawdown chart
        charts['drawdown'] = self._plot_drawdown(equity_curve)

        # Monthly returns heatmap
        charts['monthly_returns'] = self._plot_monthly_returns(equity_curve)

        # Returns distribution
        charts['returns_dist'] = self._plot_returns_distribution(equity_curve)

        # Trade analysis
        if not trades.empty and 'pnl' in trades.columns:
            charts['trade_pnl'] = self._plot_trade_pnl(trades)
            charts['cumulative_pnl'] = self._plot_cumulative_pnl(trades)

        # Rolling metrics
        charts['rolling_sharpe'] = self._plot_rolling_sharpe(equity_curve)

        return charts

    def _plot_equity_curve(
        self,
        equity_curve: pd.Series,
        benchmark: Optional[pd.Series] = None
    ) -> str:
        """Plot equity curve."""
        fig, ax = plt.subplots(figsize=(14, 7))

        # Normalize to 100
        normalized_equity = equity_curve / equity_curve.iloc[0] * 100
        ax.plot(normalized_equity.index, normalized_equity.values,
                label='Strategy', linewidth=2, color='#2E86AB')

        if benchmark is not None and len(benchmark) > 0:
            normalized_benchmark = benchmark / benchmark.iloc[0] * 100
            ax.plot(normalized_benchmark.index, normalized_benchmark.values,
                    label='Benchmark', linewidth=2, color='#A23B72', alpha=0.7)

        ax.set_title('Equity Curve', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Portfolio Value (Base = 100)', fontsize=12)
        ax.legend(loc='best', fontsize=11)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_drawdown(self, equity_curve: pd.Series) -> str:
        """Plot drawdown chart."""
        fig, ax = plt.subplots(figsize=(14, 6))

        # Calculate drawdown
        cumulative_max = equity_curve.expanding().max()
        drawdown = (equity_curve - cumulative_max) / cumulative_max * 100

        ax.fill_between(drawdown.index, drawdown.values, 0,
                        alpha=0.6, color='#F18F01', label='Drawdown')
        ax.plot(drawdown.index, drawdown.values, color='#C73E1D', linewidth=1.5)

        ax.set_title('Drawdown', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Drawdown (%)', fontsize=12)
        ax.legend(loc='best', fontsize=11)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_monthly_returns(self, equity_curve: pd.Series) -> str:
        """Plot monthly returns heatmap."""
        # Calculate monthly returns
        monthly = equity_curve.resample('M').last()
        monthly_returns = monthly.pct_change().dropna() * 100

        if len(monthly_returns) < 2:
            # Not enough data for heatmap
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.text(0.5, 0.5, 'Insufficient data for monthly returns',
                   ha='center', va='center', fontsize=14)
            ax.axis('off')
            return self._fig_to_base64(fig)

        # Create pivot table
        monthly_df = pd.DataFrame({
            'return': monthly_returns,
            'year': monthly_returns.index.year,
            'month': monthly_returns.index.month,
        })

        pivot = monthly_df.pivot(index='year', columns='month', values='return')

        # Create heatmap
        fig, ax = plt.subplots(figsize=(14, max(6, len(pivot) * 0.5)))

        sns.heatmap(pivot, annot=True, fmt='.1f', cmap='RdYlGn', center=0,
                   cbar_kws={'label': 'Return (%)'}, ax=ax,
                   linewidths=0.5, linecolor='gray')

        ax.set_title('Monthly Returns (%)', fontsize=16, fontweight='bold')
        ax.set_xlabel('Month', fontsize=12)
        ax.set_ylabel('Year', fontsize=12)

        # Month labels
        month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        ax.set_xticklabels(month_labels[:len(pivot.columns)], rotation=0)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_returns_distribution(self, equity_curve: pd.Series) -> str:
        """Plot returns distribution."""
        returns = equity_curve.pct_change().dropna() * 100

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # Histogram
        ax1.hist(returns, bins=50, alpha=0.7, color='#2E86AB', edgecolor='black')
        ax1.axvline(returns.mean(), color='red', linestyle='--',
                   linewidth=2, label=f'Mean: {returns.mean():.2f}%')
        ax1.set_title('Returns Distribution', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Daily Return (%)', fontsize=12)
        ax1.set_ylabel('Frequency', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Q-Q plot
        from scipy import stats
        stats.probplot(returns, dist="norm", plot=ax2)
        ax2.set_title('Q-Q Plot', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_trade_pnl(self, trades: pd.DataFrame) -> str:
        """Plot trade P&L."""
        fig, ax = plt.subplots(figsize=(14, 6))

        pnl = trades['pnl'].values
        colors = ['green' if p > 0 else 'red' for p in pnl]

        ax.bar(range(len(pnl)), pnl, color=colors, alpha=0.7)
        ax.axhline(0, color='black', linewidth=1)
        ax.set_title('Trade P&L', fontsize=16, fontweight='bold')
        ax.set_xlabel('Trade Number', fontsize=12)
        ax.set_ylabel('P&L', fontsize=12)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_cumulative_pnl(self, trades: pd.DataFrame) -> str:
        """Plot cumulative P&L."""
        fig, ax = plt.subplots(figsize=(14, 6))

        cumulative_pnl = trades['pnl'].cumsum()

        ax.plot(cumulative_pnl.index, cumulative_pnl.values,
               linewidth=2, color='#2E86AB')
        ax.fill_between(cumulative_pnl.index, cumulative_pnl.values, 0,
                        alpha=0.3, color='#2E86AB')
        ax.axhline(0, color='black', linewidth=1)

        ax.set_title('Cumulative P&L', fontsize=16, fontweight='bold')
        ax.set_xlabel('Trade Number', fontsize=12)
        ax.set_ylabel('Cumulative P&L', fontsize=12)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _plot_rolling_sharpe(self, equity_curve: pd.Series, window: int = 252) -> str:
        """Plot rolling Sharpe ratio."""
        returns = equity_curve.pct_change().dropna()

        if len(returns) < window:
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.text(0.5, 0.5, 'Insufficient data for rolling Sharpe',
                   ha='center', va='center', fontsize=14)
            ax.axis('off')
            return self._fig_to_base64(fig)

        # Calculate rolling Sharpe
        rolling_sharpe = (
            returns.rolling(window).mean() * 252 /
            (returns.rolling(window).std() * np.sqrt(252))
        )

        fig, ax = plt.subplots(figsize=(14, 6))

        ax.plot(rolling_sharpe.index, rolling_sharpe.values,
               linewidth=2, color='#2E86AB')
        ax.axhline(0, color='black', linewidth=1, linestyle='--')
        ax.axhline(1, color='green', linewidth=1, linestyle='--', alpha=0.5)

        ax.set_title(f'Rolling Sharpe Ratio ({window}-day)', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Sharpe Ratio', fontsize=12)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _fig_to_base64(self, fig) -> str:
        """Convert matplotlib figure to base64 string."""
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close(fig)
        return f"data:image/png;base64,{image_base64}"

    def _create_html(
        self,
        metrics: PerformanceMetrics,
        charts: Dict[str, str],
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create HTML report."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #2E86AB 0%, #A23B72 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            color: #2E86AB;
            border-bottom: 3px solid #2E86AB;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #2E86AB;
        }}
        .metric-label {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #2E86AB;
        }}
        .metric-value.positive {{
            color: #28a745;
        }}
        .metric-value.negative {{
            color: #dc3545;
        }}
        .chart {{
            margin: 20px 0;
            text-align: center;
        }}
        .chart img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #2E86AB;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .footer {{
            text-align: center;
            color: #666;
            margin-top: 30px;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Backtest Report</h1>
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="section">
        <h2>Performance Summary</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Total Return</div>
                <div class="metric-value {'positive' if metrics.total_return > 0 else 'negative'}">
                    {metrics.total_return:+.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Annualized Return</div>
                <div class="metric-value {'positive' if metrics.annualized_return > 0 else 'negative'}">
                    {metrics.annualized_return:+.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">
                    {metrics.sharpe_ratio:.2f}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sortino Ratio</div>
                <div class="metric-value">
                    {metrics.sortino_ratio:.2f}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">
                    {metrics.max_drawdown:.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Volatility</div>
                <div class="metric-value">
                    {metrics.volatility:.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">
                    {metrics.win_rate:.2%}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">
                    {metrics.total_trades}
                </div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Equity Curve</h2>
        <div class="chart">
            <img src="{charts.get('equity_curve', '')}" alt="Equity Curve">
        </div>
    </div>

    <div class="section">
        <h2>Drawdown Analysis</h2>
        <div class="chart">
            <img src="{charts.get('drawdown', '')}" alt="Drawdown">
        </div>
    </div>

    <div class="section">
        <h2>Monthly Returns</h2>
        <div class="chart">
            <img src="{charts.get('monthly_returns', '')}" alt="Monthly Returns">
        </div>
    </div>

    <div class="section">
        <h2>Returns Distribution</h2>
        <div class="chart">
            <img src="{charts.get('returns_dist', '')}" alt="Returns Distribution">
        </div>
    </div>

    {'<div class="section"><h2>Trade Analysis</h2>' if 'trade_pnl' in charts else ''}
    {'<div class="chart"><img src="' + charts.get('trade_pnl', '') + '" alt="Trade PnL"></div>' if 'trade_pnl' in charts else ''}
    {'<div class="chart"><img src="' + charts.get('cumulative_pnl', '') + '" alt="Cumulative PnL"></div>' if 'cumulative_pnl' in charts else ''}
    {'</div>' if 'trade_pnl' in charts else ''}

    <div class="section">
        <h2>Rolling Metrics</h2>
        <div class="chart">
            <img src="{charts.get('rolling_sharpe', '')}" alt="Rolling Sharpe">
        </div>
    </div>

    {'<div class="section"><h2>Detailed Metrics</h2>' + self._create_detailed_metrics_table(metrics) + '</div>'}

    <div class="footer">
        <p>Backtest Report - TradingAgents Framework</p>
    </div>
</body>
</html>
"""
        return html

    def _create_detailed_metrics_table(self, metrics: PerformanceMetrics) -> str:
        """Create detailed metrics table HTML."""
        rows = []

        # Return metrics
        rows.append(("<tr><th colspan='2' style='background:#A23B72;'>Return Metrics</th></tr>"))
        rows.append(f"<tr><td>Total Return</td><td>{metrics.total_return:+.2%}</td></tr>")
        rows.append(f"<tr><td>Annualized Return</td><td>{metrics.annualized_return:+.2%}</td></tr>")
        rows.append(f"<tr><td>Cumulative Return</td><td>{metrics.cumulative_return:+.2%}</td></tr>")

        # Risk-adjusted metrics
        rows.append("<tr><th colspan='2' style='background:#A23B72;'>Risk-Adjusted Metrics</th></tr>")
        rows.append(f"<tr><td>Sharpe Ratio</td><td>{metrics.sharpe_ratio:.2f}</td></tr>")
        rows.append(f"<tr><td>Sortino Ratio</td><td>{metrics.sortino_ratio:.2f}</td></tr>")
        rows.append(f"<tr><td>Calmar Ratio</td><td>{metrics.calmar_ratio:.2f}</td></tr>")
        rows.append(f"<tr><td>Omega Ratio</td><td>{metrics.omega_ratio:.2f}</td></tr>")

        # Risk metrics
        rows.append("<tr><th colspan='2' style='background:#A23B72;'>Risk Metrics</th></tr>")
        rows.append(f"<tr><td>Volatility</td><td>{metrics.volatility:.2%}</td></tr>")
        rows.append(f"<tr><td>Downside Deviation</td><td>{metrics.downside_deviation:.2%}</td></tr>")
        rows.append(f"<tr><td>Max Drawdown</td><td>{metrics.max_drawdown:.2%}</td></tr>")
        rows.append(f"<tr><td>Avg Drawdown</td><td>{metrics.avg_drawdown:.2%}</td></tr>")
        rows.append(f"<tr><td>Max DD Duration (days)</td><td>{metrics.max_drawdown_duration}</td></tr>")

        # Trade statistics
        rows.append("<tr><th colspan='2' style='background:#A23B72;'>Trade Statistics</th></tr>")
        rows.append(f"<tr><td>Total Trades</td><td>{metrics.total_trades}</td></tr>")
        rows.append(f"<tr><td>Winning Trades</td><td>{metrics.winning_trades}</td></tr>")
        rows.append(f"<tr><td>Losing Trades</td><td>{metrics.losing_trades}</td></tr>")
        rows.append(f"<tr><td>Win Rate</td><td>{metrics.win_rate:.2%}</td></tr>")
        rows.append(f"<tr><td>Profit Factor</td><td>{metrics.profit_factor:.2f}</td></tr>")
        rows.append(f"<tr><td>Avg Win</td><td>{metrics.avg_win:.2f}</td></tr>")
        rows.append(f"<tr><td>Avg Loss</td><td>{metrics.avg_loss:.2f}</td></tr>")

        # Benchmark comparison
        if metrics.alpha is not None:
            rows.append("<tr><th colspan='2' style='background:#A23B72;'>Benchmark Comparison</th></tr>")
            rows.append(f"<tr><td>Alpha</td><td>{metrics.alpha:+.2%}</td></tr>")
            rows.append(f"<tr><td>Beta</td><td>{metrics.beta:.2f}</td></tr>")
            rows.append(f"<tr><td>Correlation</td><td>{metrics.correlation:.2f}</td></tr>")
            if metrics.tracking_error is not None:
                rows.append(f"<tr><td>Tracking Error</td><td>{metrics.tracking_error:.2%}</td></tr>")
            if metrics.information_ratio is not None:
                rows.append(f"<tr><td>Information Ratio</td><td>{metrics.information_ratio:.2f}</td></tr>")

        return f"<table>{''.join(rows)}</table>"

    def export_to_csv(
        self,
        output_dir: str,
        equity_curve: pd.Series,
        trades: pd.DataFrame,
        metrics: PerformanceMetrics,
    ) -> None:
        """
        Export backtest results to CSV files.

        Args:
            output_dir: Directory to save CSV files
            equity_curve: Portfolio value time series
            trades: Trades DataFrame
            metrics: Performance metrics
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Export equity curve
        equity_curve.to_csv(output_dir / 'equity_curve.csv', header=['value'])

        # Export trades
        if not trades.empty:
            trades.to_csv(output_dir / 'trades.csv', index=False)

        # Export metrics
        metrics_df = pd.DataFrame([metrics.to_dict()])
        metrics_df.to_csv(output_dir / 'metrics.csv', index=False)

        logger.info(f"Exported results to {output_dir}")
