"""Performance dashboard and reporting utilities."""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PerformanceDashboard:
    """Generate performance dashboards and reports."""
    
    def __init__(self, db, portfolio_id: int):
        """Initialize dashboard.
        
        Args:
            db: TradingDatabase instance
            portfolio_id: Portfolio ID
        """
        self.db = db
        self.portfolio_id = portfolio_id
    
    def generate_summary_report(self) -> Dict:
        """Generate summary performance report.
        
        Returns:
            Summary dictionary
        """
        # Get portfolio
        portfolio = self.db.get_portfolio(self.portfolio_id)
        
        # Get daily snapshots
        snapshots = self.db.execute_query(
            "SELECT * FROM daily_snapshots WHERE portfolio_id = ? ORDER BY date",
            (self.portfolio_id,)
        )
        
        if not snapshots:
            return {"error": "No data"}
        
        # Calculate metrics
        initial_value = portfolio["initial_capital"]
        final_value = snapshots[-1]["total_portfolio_value"]
        total_return = ((final_value - initial_value) / initial_value) * 100
        
        cumulative_alpha = sum(s["alpha"] for s in snapshots)
        avg_daily_return = sum(s["daily_return"] for s in snapshots) / len(snapshots) if snapshots else 0
        
        # Best and worst day
        best_day = max(snapshots, key=lambda x: x["daily_return"])
        worst_day = min(snapshots, key=lambda x: x["daily_return"])
        
        # Win rate (days with positive return)
        positive_days = sum(1 for s in snapshots if s["daily_return"] > 0)
        win_rate = (positive_days / len(snapshots)) * 100 if snapshots else 0
        
        # Trading activity
        transactions = self.db.execute_query(
            "SELECT COUNT(*), SUM(fees) FROM transactions WHERE portfolio_id = ?",
            (self.portfolio_id,)
        )
        
        total_trades = 0
        total_fees = 0
        if transactions and len(transactions) > 0:
            row = transactions[0]
            total_trades = row.get("COUNT(*)", 0) if isinstance(row, dict) else row[0]
            total_fees = row.get("SUM(fees)", 0) if isinstance(row, dict) else row[1]
        
        return {
            "summary": {
                "portfolio_id": self.portfolio_id,
                "trading_days": len(snapshots),
                "start_date": snapshots[0]["date"],
                "end_date": snapshots[-1]["date"],
                "initial_capital": initial_value,
                "final_value": final_value,
                "total_return_pct": total_return,
                "cumulative_alpha_pct": cumulative_alpha,
                "avg_daily_return_pct": avg_daily_return,
                "win_rate_pct": win_rate,
                "best_day_pct": best_day["daily_return"],
                "worst_day_pct": worst_day["daily_return"],
                "total_trades": total_trades,
                "total_fees": total_fees,
            },
            "daily_snapshots": snapshots,
        }
    
    def export_to_csv(self, output_path: str, include_holdings: bool = False):
        """Export performance to CSV.
        
        Args:
            output_path: Path to CSV file
            include_holdings: Include holdings snapshots
        """
        snapshots = self.db.execute_query(
            "SELECT * FROM daily_snapshots WHERE portfolio_id = ? ORDER BY date",
            (self.portfolio_id,)
        )
        
        with open(output_path, "w", newline="") as f:
            fieldnames = [
                "date", "total_portfolio_value", "cash_balance", "total_invested",
                "daily_return_pct", "cumulative_return_pct", "dividend_income",
                "benchmark_return_pct", "alpha_pct"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for snap in snapshots:
                writer.writerow({
                    "date": snap["date"],
                    "total_portfolio_value": snap["total_portfolio_value"],
                    "cash_balance": snap["cash_balance"],
                    "total_invested": snap["total_invested"],
                    "daily_return_pct": snap["daily_return"],
                    "cumulative_return_pct": snap["cumulative_return"],
                    "dividend_income": snap["dividend_income"],
                    "benchmark_return_pct": snap["benchmark_return"],
                    "alpha_pct": snap["alpha"],
                })
        
        logger.info(f"Exported performance report to {output_path}")
    
    def export_to_json(self, output_path: str) -> Dict:
        """Export performance to JSON.
        
        Args:
            output_path: Path to JSON file
            
        Returns:
            Report dictionary
        """
        report = self.generate_summary_report()
        
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Exported performance report to {output_path}")
        return report
    
    def export_transactions(self, output_path: str):
        """Export all transactions to CSV.
        
        Args:
            output_path: Path to CSV file
        """
        transactions = self.db.execute_query(
            "SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY timestamp",
            (self.portfolio_id,)
        )
        
        if not transactions:
            logger.warning("No transactions to export")
            return
        
        with open(output_path, "w", newline="") as f:
            fieldnames = list(transactions[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(transactions)
        
        logger.info(f"Exported {len(transactions)} transactions to {output_path}")
    
    def export_decisions(self, output_path: str):
        """Export AI decisions to CSV.
        
        Args:
            output_path: Path to CSV file
        """
        decisions = self.db.execute_query(
            "SELECT * FROM ai_decisions WHERE portfolio_id = ? ORDER BY timestamp",
            (self.portfolio_id,)
        )
        
        if not decisions:
            logger.warning("No decisions to export")
            return
        
        with open(output_path, "w", newline="") as f:
            fieldnames = [
                "id", "ticker", "decision", "confidence_score",
                "timestamp", "analysis_start_time", "analysis_end_time",
                "executed", "execution_price", "realized_pl",
                "reward_score", "reward_type"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for d in decisions:
                writer.writerow({
                    "id": d["id"],
                    "ticker": d["ticker"],
                    "decision": d["decision"],
                    "confidence_score": d["confidence_score"],
                    "timestamp": d["timestamp"],
                    "analysis_start_time": d["analysis_start_time"],
                    "analysis_end_time": d["analysis_end_time"],
                    "executed": d["executed"],
                    "execution_price": d["execution_price"],
                    "realized_pl": d["realized_pl"],
                    "reward_score": d["reward_score"],
                    "reward_type": d["reward_type"],
                })
        
        logger.info(f"Exported {len(decisions)} decisions to {output_path}")
    
    def get_best_trades(self, top_n: int = 5) -> List[Dict]:
        """Get best performing trades.
        
        Args:
            top_n: Number of trades to return
            
        Returns:
            List of top trades
        """
        transactions = self.db.execute_query("""
            SELECT t.*, d.decision, d.confidence_score
            FROM transactions t
            LEFT JOIN ai_decisions d ON t.ai_decision_id = d.id
            WHERE t.portfolio_id = ? AND t.order_status = 'FILLED'
            ORDER BY ABS(t.price_per_share - 
                    (SELECT current_price FROM holdings 
                     WHERE ticker = t.ticker LIMIT 1)) DESC
            LIMIT ?
        """, (self.portfolio_id, top_n))
        
        return transactions
    
    def get_worst_trades(self, top_n: int = 5) -> List[Dict]:
        """Get worst performing trades.
        
        Args:
            top_n: Number of trades to return
            
        Returns:
            List of worst trades
        """
        # Similar to best_trades but order by worst loss
        transactions = self.db.execute_query(
            "SELECT * FROM transactions WHERE portfolio_id = ? ORDER BY total_value DESC LIMIT ?",
            (self.portfolio_id, top_n)
        )
        
        return transactions
    
    def print_console_summary(self, console=None):
        """Print summary to console.
        
        Args:
            console: Rich console object (optional)
        """
        report = self.generate_summary_report()
        summary = report.get("summary", {})
        
        if console:
            from rich.table import Table
            
            table = Table(title="Trading Performance Summary", show_header=True)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Trading Days", str(summary.get("trading_days", 0)))
            table.add_row("Initial Capital", f"${summary.get('initial_capital', 0):,.2f}")
            table.add_row("Final Value", f"${summary.get('final_value', 0):,.2f}")
            table.add_row("Total Return", f"{summary.get('total_return_pct', 0):.2f}%")
            table.add_row("Cumulative Alpha", f"{summary.get('cumulative_alpha_pct', 0):.2f}%")
            table.add_row("Win Rate", f"{summary.get('win_rate_pct', 0):.1f}%")
            table.add_row("Best Day", f"{summary.get('best_day_pct', 0):.2f}%")
            table.add_row("Worst Day", f"{summary.get('worst_day_pct', 0):.2f}%")
            
            console.print(table)
        else:
            # Print to stdout
            print("\n" + "="*60)
            print("TRADING PERFORMANCE SUMMARY")
            print("="*60)
            for key, value in summary.items():
                print(f"{key:30s}: {value}")
            print("="*60 + "\n")
    
    def to_html(self, output_path: str):
        """Export report as HTML.
        
        Args:
            output_path: Path to HTML file
        """
        report = self.generate_summary_report()
        summary = report.get("summary", {})
        
        html = """
<html>
<head>
    <title>Trading Performance Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .positive { color: green; }
        .negative { color: red; }
    </style>
</head>
<body>
    <h1>Trading Performance Report</h1>
    <table>
"""
        
        for key, value in summary.items():
            style_class = ""
            if isinstance(value, (int, float)) and value < 0:
                style_class = 'class="negative"'
            elif isinstance(value, (int, float)) and value > 0:
                style_class = 'class="positive"'
            
            html += f"<tr><td><b>{key}</b></td><td {style_class}>{value}</td></tr>\n"
        
        html += """
    </table>
</body>
</html>
        """
        
        with open(output_path, "w") as f:
            f.write(html)
        
        logger.info(f"Exported HTML report to {output_path}")
