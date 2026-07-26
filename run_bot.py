"""
Auto-trading bot entry point.

Usage:
    # Run continuously (scheduled jobs at configured times):
    python run_bot.py

    # Run a single ticker right now (useful for testing):
    python run_bot.py --ticker AAPL --once

    # Paper-trade one ticker for a specific historical date:
    python run_bot.py --ticker AAPL --date 2024-05-10 --once

Environment variables (see tradingbot/config.py for full list):
    TRADINGBOT_BROKER       mock | alpaca       (default: mock)
    ALPACA_API_KEY          required for alpaca
    ALPACA_API_SECRET       required for alpaca
    ALPACA_PAPER            true | false        (default: true)
    TRADINGBOT_WATCHLIST    comma-separated tickers
    OPENAI_API_KEY          required for TradingAgents LLM calls
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_bot")


def build_broker(config: dict):
    broker_type = config.get("broker", "mock").lower()
    if broker_type == "alpaca":
        from tradingbot.broker.alpaca import AlpacaBroker
        return AlpacaBroker(
            api_key=config["alpaca_api_key"],
            api_secret=config["alpaca_api_secret"],
            paper=config.get("paper_trading", True),
        )
    from tradingbot.broker.mock import MockBroker
    return MockBroker(starting_cash=100_000.0)


def build_trading_graph(config: dict):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    ta_config = DEFAULT_CONFIG.copy()
    ta_config.update({k: v for k, v in config.items() if k in DEFAULT_CONFIG})
    return TradingAgentsGraph(config=ta_config)


def main():
    parser = argparse.ArgumentParser(description="TradingAgents Auto-Trading Bot")
    parser.add_argument("--ticker", help="Single ticker to analyse (used with --once)")
    parser.add_argument("--date", help="Trade date ISO string, e.g. 2024-05-10 (default: today)")
    parser.add_argument("--once", action="store_true", help="Run once then exit")
    parser.add_argument("--approval", action="store_true", help="Require human approval before each trade")
    args = parser.parse_args()

    from tradingbot.config import TRADINGBOT_CONFIG as config
    from tradingbot.portfolio.database import PortfolioDatabase
    from tradingbot.scheduler.runner import AutoTrader
    from tradingbot.scheduler.scheduler import TradingScheduler

    broker = build_broker(config)
    db = PortfolioDatabase(config["db_path"])
    graph = build_trading_graph(config)

    trader = AutoTrader(
        trading_graph=graph,
        broker=broker,
        db=db,
        config=config,
        require_approval=args.approval,
    )

    if args.once:
        tickers = [args.ticker.upper()] if args.ticker else config.get("watchlist", [])
        outcomes = trader.run_watchlist(tickers=tickers, trade_date=args.date)
        for ticker, result in outcomes.items():
            logger.info("%-8s → %s", ticker, result)
        trader.post_market()
        sys.exit(0)

    # Continuous scheduled mode
    scheduler = TradingScheduler(trader, config)
    logger.info("Starting TradingBot in scheduled mode. Press Ctrl-C to stop.")
    scheduler.start(blocking=True)


if __name__ == "__main__":
    main()
