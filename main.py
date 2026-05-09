"""Small argparse entry point for one TradingAgents run.

Examples:
    python main.py --ticker NVDA --date 2024-05-10
    python main.py --ticker SPY --date 2024-01-02 --trading-mode backtest \
        --ps-profile conservative --ps-trade-frequency low
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from back_test.policy_config import (
    add_portfolio_state_policy_args,
    portfolio_state_policy_config_from_args,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one TradingAgents analysis.")
    parser.add_argument("--ticker", default="NVDA", help="Ticker to analyze.")
    parser.add_argument("--date", default="2024-05-10", help="Analysis date, YYYY-MM-DD.")
    parser.add_argument(
        "--trading-mode",
        choices=["live", "backtest"],
        default="live",
        help="Use live manager or backtest PortfolioState manager.",
    )
    parser.add_argument("--provider", default=DEFAULT_CONFIG["llm_provider"])
    parser.add_argument("--quick-model", default="gpt-5.4-mini")
    parser.add_argument("--deep-model", default="gpt-5.4-mini")
    parser.add_argument("--backend-url", default=DEFAULT_CONFIG["backend_url"])
    parser.add_argument("--debate-rounds", type=int, default=1)
    parser.add_argument(
        "--analysts",
        default="market,social,news,fundamentals",
        help="Comma-separated analyst keys.",
    )
    add_portfolio_state_policy_args(parser)
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()

    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = args.deep_model
    config["quick_think_llm"] = args.quick_model
    config["max_debate_rounds"] = args.debate_rounds
    config["max_risk_discuss_rounds"] = args.debate_rounds
    config["llm_provider"] = args.provider.lower()
    config["backend_url"] = args.backend_url
    config["portfolio_state_policy"] = portfolio_state_policy_config_from_args(args)

    # Configure data vendors (default uses yfinance, no extra API keys needed).
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }

    selected_analysts = [
        analyst.strip()
        for analyst in args.analysts.split(",")
        if analyst.strip()
    ]
    ta = TradingAgentsGraph(
        selected_analysts=selected_analysts,
        debug=True,
        config=config,
        trading_mode=args.trading_mode,
    )

    _, decision = ta.propagate(args.ticker, args.date, trading_mode=args.trading_mode)
    print(decision)


if __name__ == "__main__":
    main()
