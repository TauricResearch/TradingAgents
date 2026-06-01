import argparse
import json

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.experiments.backtest import AgentBacktestRunner
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main():
    parser = argparse.ArgumentParser(description="Run a historical TradingAgents simulation.")
    parser.add_argument("ticker")
    parser.add_argument("start_date")
    parser.add_argument("end_date")
    parser.add_argument("--rebalance-days", type=int, default=5)
    args = parser.parse_args()

    graph = TradingAgentsGraph(config=DEFAULT_CONFIG.copy())
    result = AgentBacktestRunner(graph, rebalance_days=args.rebalance_days).run(
        args.ticker, args.start_date, args.end_date
    )
    print(json.dumps({"metrics": result.metrics, "actions": result.actions}, indent=2))


if __name__ == "__main__":
    main()
