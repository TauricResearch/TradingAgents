# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Dashboard builder that generates self-contained HTML dashboards with Plotly.js charts."""

import html
import json
import os
from datetime import datetime
from typing import List, Optional

from tradingagents.backtest.models import (
    BacktestResult,
    PerformanceMetrics,
    TradeRecord,
)

_PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


class DashboardBuilder:
    """Generates self-contained HTML performance dashboards with Plotly.js charts.

    The generated dashboard includes:
    - KPI cards (cumulative return, Sharpe ratio, max drawdown, win rate)
    - Equity curve chart with drawdown overlay
    - Monthly returns bar chart
    - Performance metrics table
    - Trade history table with debate detail toggles
    - Backtest comparison table (optional)
    """

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir or os.path.join(".", "results", "dashboard")

    def build(
        self,
        metrics: PerformanceMetrics,
        trades: List[TradeRecord],
        backtest_results: Optional[List[BacktestResult]] = None,
        title: str = "TradingAgents Performance Dashboard",
    ) -> str:
        """Build an HTML dashboard and write it to disk.

        Args:
            metrics: Aggregated performance statistics.
            trades: List of trade records to display.
            backtest_results: Optional list of backtest results for comparison.
            title: Dashboard page title.

        Returns:
            Absolute path to the generated HTML file.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dashboard_{timestamp}.html"
        filepath = os.path.join(self.output_dir, filename)

        html_content = self._render_html(metrics, trades, backtest_results, title)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        return os.path.abspath(filepath)

    def _render_html(
        self,
        metrics: PerformanceMetrics,
        trades: List[TradeRecord],
        backtest_results: Optional[List[BacktestResult]],
        title: str,
    ) -> str:
        """Generate the full HTML string for the dashboard."""
        equity_dates = json.dumps([p["date"] for p in metrics.equity_curve])
        equity_values = json.dumps([p["equity"] for p in metrics.equity_curve])
        drawdown_values = json.dumps([p["drawdown"] for p in metrics.equity_curve])

        monthly_months = json.dumps([m["month"] for m in metrics.monthly_returns])
        monthly_returns = [m["return_pct"] for m in metrics.monthly_returns]
        monthly_colors = json.dumps(
            ["#22c55e" if r >= 0 else "#ef4444" for r in monthly_returns]
        )
        monthly_values = json.dumps(monthly_returns)

        trades_table = self._render_trades_table(trades)
        backtest_section = self._render_backtest_comparison(
            backtest_results, metrics
        )

        safe_title = html.escape(title)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<script src="{_PLOTLY_CDN}"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    padding: 24px;
    line-height: 1.6;
  }}
  h1 {{
    font-size: 1.75rem;
    margin-bottom: 24px;
    color: #f1f5f9;
    border-bottom: 1px solid #334155;
    padding-bottom: 12px;
  }}
  h2 {{
    font-size: 1.25rem;
    margin: 32px 0 16px 0;
    color: #cbd5e1;
  }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .kpi-card {{
    background: #1e293b;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    border: 1px solid #334155;
  }}
  .kpi-card .label {{
    font-size: 0.85rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
  }}
  .kpi-card .value {{
    font-size: 1.75rem;
    font-weight: 700;
  }}
  .kpi-card .value.positive {{ color: #22c55e; }}
  .kpi-card .value.negative {{ color: #ef4444; }}
  .kpi-card .value.neutral {{ color: #e2e8f0; }}
  .chart-container {{
    background: #1e293b;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 24px;
    border: 1px solid #334155;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #1e293b;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #334155;
  }}
  th {{
    background: #334155;
    padding: 10px 14px;
    text-align: left;
    font-size: 0.85rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  td {{
    padding: 10px 14px;
    border-top: 1px solid #1e293b;
    font-size: 0.9rem;
  }}
  tr:hover {{ background: #253048; }}
  .pnl-positive {{ color: #22c55e; }}
  .pnl-negative {{ color: #ef4444; }}
  .detail-toggle {{
    cursor: pointer;
    color: #60a5fa;
    font-weight: 600;
    user-select: none;
  }}
  .detail-toggle:hover {{ color: #93c5fd; }}
  .trade-detail {{
    display: none;
    padding: 12px 14px;
    background: #0f172a;
    font-size: 0.85rem;
    white-space: pre-wrap;
    color: #94a3b8;
    border-top: 1px solid #334155;
  }}
  .trade-detail.visible {{ display: table-row; }}
  .empty-msg {{
    padding: 24px;
    text-align: center;
    color: #64748b;
    font-style: italic;
  }}
  .footer {{
    margin-top: 40px;
    padding-top: 16px;
    border-top: 1px solid #334155;
    font-size: 0.8rem;
    color: #475569;
    text-align: center;
  }}
</style>
</head>
<body>
<h1>{safe_title}</h1>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">Cumulative Return</div>
    <div class="value {_css_class(metrics.cumulative_return)}">{metrics.cumulative_return}%</div>
  </div>
  <div class="kpi-card">
    <div class="label">Sharpe Ratio</div>
    <div class="value {_css_class(metrics.sharpe_ratio)}">{metrics.sharpe_ratio}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Max Drawdown</div>
    <div class="value {_css_class(metrics.max_drawdown)}">{metrics.max_drawdown}%</div>
  </div>
  <div class="kpi-card">
    <div class="label">Win Rate</div>
    <div class="value neutral">{metrics.win_rate}%</div>
  </div>
</div>

<!-- Equity Curve -->
<h2>Equity Curve</h2>
<div class="chart-container">
  <div id="equity-chart"></div>
</div>

<!-- Monthly Returns -->
<h2>Monthly Returns</h2>
<div class="chart-container">
  <div id="monthly-chart"></div>
</div>

<!-- Performance Metrics Table -->
<h2>Performance Metrics</h2>
<table>
  <thead>
    <tr>
      <th>Metric</th>
      <th>Value</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Total Trades</td><td>{metrics.total_trades}</td></tr>
    <tr><td>Win Rate</td><td>{metrics.win_rate}%</td></tr>
    <tr><td>Average Return</td><td>{metrics.avg_return}%</td></tr>
    <tr><td>Cumulative Return</td><td>{metrics.cumulative_return}%</td></tr>
    <tr><td>Sharpe Ratio</td><td>{metrics.sharpe_ratio}</td></tr>
    <tr><td>Max Drawdown</td><td>{metrics.max_drawdown}%</td></tr>
    <tr><td>Max Drawdown Duration</td><td>{metrics.max_drawdown_duration} days</td></tr>
    <tr><td>Alpha</td><td>{metrics.alpha}</td></tr>
    <tr><td>Beta</td><td>{metrics.beta}</td></tr>
    <tr><td>Profit Factor</td><td>{metrics.profit_factor}</td></tr>
    <tr><td>Avg Holding Days</td><td>{metrics.avg_holding_days}</td></tr>
  </tbody>
</table>

<!-- Trade History -->
<h2>Trade History (Last 20)</h2>
{trades_table}

<!-- Backtest Comparison -->
{backtest_section}

<div class="footer">
  Generated by TradingAgents Dashboard Builder &mdash; {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</div>

<script>
// Equity Curve Chart
var equityDates = {equity_dates};
var equityValues = {equity_values};
var drawdownValues = {drawdown_values};

if (equityDates.length > 0) {{
  var traceEquity = {{
    x: equityDates,
    y: equityValues,
    name: 'Equity',
    type: 'scatter',
    mode: 'lines+markers',
    line: {{ color: '#60a5fa', width: 2 }},
    marker: {{ size: 5 }},
  }};
  var traceDrawdown = {{
    x: equityDates,
    y: drawdownValues,
    name: 'Drawdown %',
    type: 'scatter',
    mode: 'lines',
    line: {{ color: '#ef4444', width: 1, dash: 'dot' }},
    fill: 'tozeroy',
    fillcolor: 'rgba(239,68,68,0.1)',
    yaxis: 'y2',
  }};
  Plotly.newPlot('equity-chart', [traceEquity, traceDrawdown], {{
    paper_bgcolor: '#1e293b',
    plot_bgcolor: '#1e293b',
    font: {{ color: '#e2e8f0' }},
    margin: {{ t: 20, r: 60, b: 40, l: 60 }},
    xaxis: {{ gridcolor: '#334155' }},
    yaxis: {{ title: 'Equity ($)', gridcolor: '#334155' }},
    yaxis2: {{
      title: 'Drawdown (%)',
      overlaying: 'y',
      side: 'right',
      gridcolor: '#334155',
      showgrid: false,
    }},
    legend: {{ x: 0, y: 1.1, orientation: 'h' }},
  }}, {{ responsive: true }});
}}

// Monthly Returns Chart
var monthlyMonths = {monthly_months};
var monthlyValues = {monthly_values};
var monthlyColors = {monthly_colors};

if (monthlyMonths.length > 0) {{
  var traceMonthly = {{
    x: monthlyMonths,
    y: monthlyValues,
    type: 'bar',
    marker: {{ color: monthlyColors }},
  }};
  Plotly.newPlot('monthly-chart', [traceMonthly], {{
    paper_bgcolor: '#1e293b',
    plot_bgcolor: '#1e293b',
    font: {{ color: '#e2e8f0' }},
    margin: {{ t: 20, r: 20, b: 40, l: 60 }},
    xaxis: {{ gridcolor: '#334155' }},
    yaxis: {{ title: 'Return (%)', gridcolor: '#334155', zeroline: true, zerolinecolor: '#475569' }},
  }}, {{ responsive: true }});
}}

// Toggle trade detail rows
function toggleDetail(id) {{
  var row = document.getElementById(id);
  if (row) {{
    row.classList.toggle('visible');
  }}
}}
</script>
</body>
</html>"""

    def _render_trades_table(self, trades: List[TradeRecord]) -> str:
        """Render HTML rows for the last 20 trades with PnL coloring and detail toggle."""
        if not trades:
            return '<div class="empty-msg">No trades to display.</div>'

        display_trades = trades[-20:]
        rows = []
        for idx, trade in enumerate(display_trades):
            pnl_str = ""
            pnl_class = ""
            if trade.pnl is not None:
                pnl_class = "pnl-positive" if trade.pnl >= 0 else "pnl-negative"
                sign = "+" if trade.pnl >= 0 else ""
                pnl_str = f'{sign}{trade.pnl:.2f}'

            pnl_pct_str = ""
            if trade.pnl_pct is not None:
                sign = "+" if trade.pnl_pct >= 0 else ""
                pnl_pct_str = f' ({sign}{trade.pnl_pct:.2f}%)'

            detail_id = f"detail-{idx}"
            has_detail = bool(trade.debate_summary or trade.risk_decision)
            toggle_cell = (
                f'<span class="detail-toggle" onclick="toggleDetail(\'{detail_id}\')">[?]</span>'
                if has_detail
                else ""
            )

            exit_price_str = f"{trade.exit_price:.2f}" if trade.exit_price is not None else "\u2014"

            row_html = f"""    <tr>
      <td>{html.escape(trade.ticker)}</td>
      <td>{html.escape(trade.signal)}</td>
      <td>{html.escape(trade.trade_date)}</td>
      <td>{trade.entry_price:.2f}</td>
      <td>{exit_price_str}</td>
      <td>{html.escape(trade.exit_date or '\u2014')}</td>
      <td class="{pnl_class}">{pnl_str}{pnl_pct_str}</td>
      <td>{toggle_cell}</td>
    </tr>"""
            rows.append(row_html)

            if has_detail:
                detail_parts = []
                if trade.debate_summary:
                    detail_parts.append(
                        f"Debate Summary:\n{html.escape(trade.debate_summary)}"
                    )
                if trade.risk_decision:
                    detail_parts.append(
                        f"Risk Decision: {html.escape(trade.risk_decision)}"
                    )
                detail_text = "\n\n".join(detail_parts)
                rows.append(
                    f'    <tr id="{detail_id}" class="trade-detail"><td colspan="8">{detail_text}</td></tr>'
                )

        return f"""<table>
  <thead>
    <tr>
      <th>Ticker</th>
      <th>Signal</th>
      <th>Date</th>
      <th>Entry</th>
      <th>Exit</th>
      <th>Exit Date</th>
      <th>PnL</th>
      <th>Detail</th>
    </tr>
  </thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>"""

    def _render_backtest_comparison(
        self,
        backtest_results: Optional[List[BacktestResult]],
        live_metrics: PerformanceMetrics,
    ) -> str:
        """Render a backtest vs live comparison table, or empty string if no results."""
        if not backtest_results:
            return ""

        rows = []
        for bt in backtest_results:
            m = bt.metrics
            persona = bt.config_snapshot.get("persona", "N/A") or "N/A"
            rows.append(f"""    <tr>
      <td>{html.escape(bt.ticker)}</td>
      <td>{html.escape(persona)}</td>
      <td>{html.escape(bt.start_date)} &mdash; {html.escape(bt.end_date)}</td>
      <td>{html.escape(bt.benchmark)}</td>
      <td>{m.cumulative_return}%</td>
      <td>{m.sharpe_ratio}</td>
      <td>{m.max_drawdown}%</td>
      <td>{m.win_rate}%</td>
    </tr>""")

        return f"""
<h2>Backtest Comparison</h2>
<table>
  <thead>
    <tr>
      <th>Ticker</th>
      <th>Persona</th>
      <th>Period</th>
      <th>Benchmark</th>
      <th>Cum. Return</th>
      <th>Sharpe</th>
      <th>Max DD</th>
      <th>Win Rate</th>
    </tr>
  </thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>

<h2>Live vs Backtest</h2>
<table>
  <thead>
    <tr>
      <th>Metric</th>
      <th>Live</th>
      <th>Backtest (Latest)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Cumulative Return</td>
      <td>{live_metrics.cumulative_return}%</td>
      <td>{backtest_results[-1].metrics.cumulative_return}%</td>
    </tr>
    <tr>
      <td>Sharpe Ratio</td>
      <td>{live_metrics.sharpe_ratio}</td>
      <td>{backtest_results[-1].metrics.sharpe_ratio}</td>
    </tr>
    <tr>
      <td>Max Drawdown</td>
      <td>{live_metrics.max_drawdown}%</td>
      <td>{backtest_results[-1].metrics.max_drawdown}%</td>
    </tr>
    <tr>
      <td>Win Rate</td>
      <td>{live_metrics.win_rate}%</td>
      <td>{backtest_results[-1].metrics.win_rate}%</td>
    </tr>
  </tbody>
</table>"""


def _css_class(value: float) -> str:
    """Return a CSS class based on whether the value is positive, negative, or zero."""
    if value > 0:
        return "positive"
    elif value < 0:
        return "negative"
    return "neutral"
