"""
Paper Trading Performance Dashboard
Real-time monitoring and analytics
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from dataclasses import asdict


class PaperTradingDashboard:
    """
    Performance dashboard for paper trading.

    Features:
    - Real-time metrics display
    - Performance analytics
    - Trade history analysis
    - Risk metrics
    """

    def __init__(self, engine):
        """
        Initialize dashboard.

        Args:
            engine: PaperTradingEngine instance
        """
        self.engine = engine

    def print_live_status(self):
        """Print real-time trading status."""
        portfolio_value = self.engine.get_portfolio_value()
        total_return = (portfolio_value - self.engine.initial_capital) / self.engine.initial_capital

        print("\n" + "="*80)
        print(f"{'PAPER TRADING DASHBOARD':^80}")
        print("="*80)

        # Portfolio Overview
        print("\n📊 PORTFOLIO OVERVIEW")
        print(f"  Portfolio Value:    ${portfolio_value:,.2f}")
        print(f"  Initial Capital:    ${self.engine.initial_capital:,.2f}")
        print(f"  Cash:               ${self.engine.cash:,.2f}")
        print(f"  Total Return:       {total_return:+.2%}")
        print(f"  Daily P&L:          {self.engine.daily_pnl:+.2%}")

        # Positions
        print("\n📈 OPEN POSITIONS")
        if self.engine.positions:
            for symbol, pos in self.engine.positions.items():
                price = self.engine.current_prices.get(symbol, pos.current_price)
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.entry_price) * pos.amount
                pos.unrealized_pnl_pct = (price / pos.entry_price - 1)

                emoji = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                print(f"  {emoji} {symbol:12s} | Amount: {pos.amount:.6f} | Entry: ${pos.entry_price:,.2f} | Current: ${price:,.2f} | P&L: {pos.unrealized_pnl_pct:+.2%} (${pos.unrealized_pnl:+,.2f})")
        else:
            print("  No open positions")

        # Recent Orders
        print("\n📋 RECENT ORDERS (Last 5)")
        recent_orders = self.engine.orders[-5:] if len(self.engine.orders) >= 5 else self.engine.orders
        if recent_orders:
            for order in reversed(recent_orders):
                emoji = "🟢" if order.side.value == "buy" else "🔴"
                time_str = order.timestamp.strftime("%H:%M:%S")
                print(f"  {emoji} [{time_str}] {order.side.value.upper():4s} {order.amount:.6f} {order.symbol:12s} @ ${order.price:,.2f}")
                if order.reason:
                    print(f"     └─ {order.reason}")
        else:
            print("  No orders yet")

        # Statistics
        print("\n📊 STATISTICS")
        print(f"  Total Orders:       {len(self.engine.orders)}")
        print(f"  Buy Orders:         {sum(1 for o in self.engine.orders if o.side.value == 'buy')}")
        print(f"  Sell Orders:        {sum(1 for o in self.engine.orders if o.side.value == 'sell')}")
        print(f"  Updates:            {len(self.engine.portfolio_value_history)}")

        # Risk Metrics
        print("\n⚠️  RISK METRICS")
        print(f"  Max Position Size:  {self.engine.max_position_size:.1%}")
        print(f"  Max Daily Loss:     {self.engine.max_daily_loss:.1%}")
        print(f"  Stop Loss:          {self.engine.stop_loss_pct:.1%}")
        print(f"  Take Profit:        {self.engine.take_profit_pct:.1%}")

        print("\n" + "="*80 + "\n")

    def get_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics."""
        if not self.engine.portfolio_value_history:
            return {}

        # Get portfolio values
        values = [h['portfolio_value'] for h in self.engine.portfolio_value_history]

        # Calculate returns
        returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

        # Current metrics
        current_value = values[-1]
        total_return = (current_value - self.engine.initial_capital) / self.engine.initial_capital

        # Calculate max drawdown
        peak = self.engine.initial_capital
        max_dd = 0
        for value in values:
            if value > peak:
                peak = value
            dd = (value - peak) / peak
            if dd < max_dd:
                max_dd = dd

        # Win rate
        winning_trades = 0
        losing_trades = 0
        total_profit = 0
        total_loss = 0

        for order in self.engine.orders:
            if order.side.value == "sell" and "P&L:" in order.reason:
                # Extract P&L from reason
                pnl_str = order.reason.split("P&L: $")[1].split(" ")[0].replace(",", "")
                pnl = float(pnl_str)

                if pnl > 0:
                    winning_trades += 1
                    total_profit += pnl
                else:
                    losing_trades += 1
                    total_loss += abs(pnl)

        total_trades = winning_trades + losing_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # Average win/loss
        avg_win = total_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = total_loss / losing_trades if losing_trades > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # Sharpe ratio (annualized, simplified)
        if returns:
            import numpy as np
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0
        else:
            sharpe = 0

        return {
            'current_value': current_value,
            'initial_capital': self.engine.initial_capital,
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'max_drawdown': max_dd,
            'max_drawdown_pct': max_dd * 100,
            'sharpe_ratio': sharpe,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'win_rate_pct': win_rate * 100,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'num_updates': len(self.engine.portfolio_value_history),
        }

    def print_performance_report(self):
        """Print comprehensive performance report."""
        metrics = self.get_performance_metrics()

        if not metrics:
            print("No performance data yet.")
            return

        print("\n" + "="*80)
        print(f"{'PERFORMANCE REPORT':^80}")
        print("="*80)

        # Returns
        print("\n💰 RETURNS")
        print(f"  Current Value:      ${metrics['current_value']:,.2f}")
        print(f"  Initial Capital:    ${metrics['initial_capital']:,.2f}")
        print(f"  Total Return:       {metrics['total_return']:+.2%} (${metrics['current_value'] - metrics['initial_capital']:+,.2f})")
        print(f"  Max Drawdown:       {metrics['max_drawdown']:.2%}")
        print(f"  Sharpe Ratio:       {metrics['sharpe_ratio']:.2f}")

        # Trading Stats
        print("\n📊 TRADING STATISTICS")
        print(f"  Total Trades:       {metrics['total_trades']}")
        print(f"  Winning Trades:     {metrics['winning_trades']} ({metrics['win_rate_pct']:.1f}%)")
        print(f"  Losing Trades:      {metrics['losing_trades']} ({100 - metrics['win_rate_pct']:.1f}%)")
        print(f"  Win Rate:           {metrics['win_rate_pct']:.1f}%")

        # P&L
        print("\n💵 PROFIT & LOSS")
        print(f"  Total Profit:       ${metrics['total_profit']:,.2f}")
        print(f"  Total Loss:         ${metrics['total_loss']:,.2f}")
        print(f"  Net P&L:            ${metrics['total_profit'] - metrics['total_loss']:+,.2f}")
        print(f"  Avg Win:            ${metrics['avg_win']:,.2f}")
        print(f"  Avg Loss:           ${metrics['avg_loss']:,.2f}")
        print(f"  Profit Factor:      {metrics['profit_factor']:.2f}")

        # Data
        print("\n📈 DATA COVERAGE")
        print(f"  Total Updates:      {metrics['num_updates']}")
        print(f"  Update Interval:    {self.engine.update_interval}s")
        duration_seconds = metrics['num_updates'] * self.engine.update_interval
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        print(f"  Trading Duration:   {hours}h {minutes}m")

        print("\n" + "="*80 + "\n")

    def export_to_csv(self, filename: Optional[str] = None):
        """Export trading data to CSV."""
        if not filename:
            filename = f"paper_trading_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Prepare data
        data = []
        for order in self.engine.orders:
            data.append({
                'timestamp': order.timestamp,
                'order_id': order.order_id,
                'symbol': order.symbol,
                'side': order.side.value,
                'amount': order.amount,
                'price': order.price,
                'status': order.status.value,
                'reason': order.reason,
            })

        if data:
            df = pd.DataFrame(data)
            filepath = os.path.join(self.engine.data_dir, filename)
            df.to_csv(filepath, index=False)
            print(f"✓ Exported {len(data)} orders to: {filepath}")
        else:
            print("No orders to export")

    def export_portfolio_history(self, filename: Optional[str] = None):
        """Export portfolio value history to CSV."""
        if not filename:
            filename = f"portfolio_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        if self.engine.portfolio_value_history:
            df = pd.DataFrame(self.engine.portfolio_value_history)
            filepath = os.path.join(self.engine.data_dir, filename)
            df.to_csv(filepath, index=False)
            print(f"✓ Exported portfolio history to: {filepath}")
        else:
            print("No portfolio history to export")

    def generate_html_report(self, filename: Optional[str] = None):
        """Generate HTML dashboard report."""
        if not filename:
            filename = f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        metrics = self.get_performance_metrics()

        if not metrics:
            print("No performance data yet.")
            return

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Paper Trading Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
        h1 {{ color: #333; text-align: center; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .metric-value {{ font-size: 32px; font-weight: bold; color: #007bff; }}
        .metric-label {{ font-size: 14px; color: #666; margin-top: 10px; }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #007bff; color: white; }}
        .section {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Paper Trading Dashboard</h1>
        <p style="text-align: center; color: #666;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="section">
            <h2>Portfolio Overview</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-value">${metrics['current_value']:,.2f}</div>
                    <div class="metric-label">Current Value</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value {'positive' if metrics['total_return'] >= 0 else 'negative'}">{metrics['total_return']:+.2%}</div>
                    <div class="metric-label">Total Return</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['sharpe_ratio']:.2f}</div>
                    <div class="metric-label">Sharpe Ratio</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Trading Statistics</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-value">{metrics['total_trades']}</div>
                    <div class="metric-label">Total Trades</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['win_rate_pct']:.1f}%</div>
                    <div class="metric-label">Win Rate</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics['profit_factor']:.2f}</div>
                    <div class="metric-label">Profit Factor</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Risk Metrics</h2>
            <table>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Max Drawdown</td>
                    <td class="negative">{metrics['max_drawdown']:.2%}</td>
                </tr>
                <tr>
                    <td>Average Win</td>
                    <td class="positive">${metrics['avg_win']:,.2f}</td>
                </tr>
                <tr>
                    <td>Average Loss</td>
                    <td class="negative">${metrics['avg_loss']:,.2f}</td>
                </tr>
            </table>
        </div>

        <div class="section">
            <h2>Recent Orders</h2>
            <table>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Amount</th>
                    <th>Price</th>
                    <th>Reason</th>
                </tr>
"""

        for order in reversed(self.engine.orders[-10:]):
            side_class = "positive" if order.side.value == "buy" else "negative"
            html += f"""
                <tr>
                    <td>{order.timestamp.strftime('%H:%M:%S')}</td>
                    <td>{order.symbol}</td>
                    <td class="{side_class}">{order.side.value.upper()}</td>
                    <td>{order.amount:.6f}</td>
                    <td>${order.price:,.2f}</td>
                    <td>{order.reason}</td>
                </tr>
"""

        html += """
            </table>
        </div>
    </div>
</body>
</html>
"""

        filepath = os.path.join(self.engine.data_dir, filename)
        with open(filepath, 'w') as f:
            f.write(html)

        print(f"✓ Generated HTML dashboard: {filepath}")
        return filepath
