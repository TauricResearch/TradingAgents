import argparse
import json

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.experiments.portfolio import PortfolioCoordinator
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main():
    parser = argparse.ArgumentParser(description="Analyze a correlation-aware portfolio.")
    parser.add_argument("trade_date")
    parser.add_argument("tickers", nargs="+")
    args = parser.parse_args()

    graph = TradingAgentsGraph(config=DEFAULT_CONFIG.copy())
    result = PortfolioCoordinator(graph).analyze(args.tickers, args.trade_date)
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    main()
