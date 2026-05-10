import argparse
from datetime import date
from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TradingAgents non-interactive runner")
    parser.add_argument("--ticker", default="NVDA", help="Ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--date",
        dest="analysis_date",
        default=date.today().isoformat(),
        help="Analysis date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "google", "anthropic", "xai", "deepseek", "qwen", "glm", "openrouter", "ollama", "azure"],
        help="LLM provider override",
    )
    parser.add_argument("--deep-model", help="Override deep_think_llm model id")
    parser.add_argument("--quick-model", help="Override quick_think_llm model id")
    parser.add_argument("--debug", action="store_true", help="Enable verbose graph debug logs")
    return parser


# DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides
# (llm_provider, deep_think_llm, quick_think_llm, backend_url, etc.),
# so users can switch models or endpoints purely via .env without
# editing this script. Override individual keys here only when you
# want a hard-coded value that should ignore the environment.


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = 1

    # Keep yfinance defaults for data APIs so only LLM key is required.
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }

    if args.provider:
        config["llm_provider"] = args.provider
    if args.deep_model:
        config["deep_think_llm"] = args.deep_model
    if args.quick_model:
        config["quick_think_llm"] = args.quick_model

    ta = TradingAgentsGraph(debug=args.debug, config=config)
    _, decision = ta.propagate(args.ticker, args.analysis_date)
    print(decision)


if __name__ == "__main__":
    main()
