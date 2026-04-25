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

"""Convenience CLI for running backtests and generating dashboards.

Usage:
    python backtest_cli.py --ticker NVDA --start 2024-04-01 --end 2026-04-01
    python backtest_cli.py --ticker 005930 --start 2024-04-01 --end 2026-04-01 --persona warren_buffett
    python backtest_cli.py --ticker NVDA --start 2024-04-01 --end 2026-04-01 --freq weekly --benchmark QQQ
"""

import argparse
import sys

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.backtest.engine import BacktestEngine
from tradingagents.dashboard.builder import DashboardBuilder


def main():
    parser = argparse.ArgumentParser(description="TradingAgents Backtest & Dashboard")
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. NVDA, 005930)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--freq", default="monthly", choices=["monthly", "weekly", "biweekly"])
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker")
    parser.add_argument("--capital", type=float, default=100_000_000, help="Initial capital")
    parser.add_argument("--persona", default=None, choices=["warren_buffett", "ray_dalio", "peter_lynch"])
    parser.add_argument("--provider", default="anthropic", help="LLM provider")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM calls (use cached signals)")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip dashboard generation")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = args.provider
    if args.persona:
        config["persona"] = args.persona

    print(f"Running backtest: {args.ticker} ({args.start} → {args.end}, {args.freq})")
    print(f"Config: provider={args.provider}, persona={args.persona}, benchmark={args.benchmark}")

    engine = BacktestEngine(config)
    result = engine.run(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        rebalance_freq=args.freq,
        benchmark=args.benchmark,
        initial_capital=args.capital,
        skip_llm=args.skip_llm,
    )

    m = result.metrics
    print(f"\n{'='*50}")
    print(f"Results: {result.ticker} ({result.start_date} → {result.end_date})")
    print(f"{'='*50}")
    print(f"  Total Trades:      {m.total_trades}")
    print(f"  Win Rate:          {m.win_rate:.1f}%")
    print(f"  Cumulative Return: {m.cumulative_return:+.2f}%")
    print(f"  Sharpe Ratio:      {m.sharpe_ratio:.2f}")
    print(f"  Max Drawdown:      {m.max_drawdown:.1f}%")
    print(f"  Alpha:             {m.alpha:+.2f}%")
    print(f"  Profit Factor:     {m.profit_factor:.2f}")
    print(f"  Avg Holding Days:  {m.avg_holding_days:.1f}")

    if not args.no_dashboard:
        builder = DashboardBuilder()
        path = builder.build(
            metrics=result.metrics,
            trades=result.trades,
            backtest_results=[result],
            title=f"TradingAgents Backtest: {args.ticker}",
        )
        print(f"\nDashboard: {path}")


if __name__ == "__main__":
    main()
