#!/usr/bin/env python3
"""CLI bridge between Claude Code subagents and TradingAgents data/memory infrastructure.

Usage:
    python cc_tools.py <command> [args...]

Data Commands:
    get_stock_data <symbol> <start_date> <end_date>
    get_indicators <symbol> <indicator> <curr_date> [look_back_days]
    get_fundamentals <ticker> <curr_date>
    get_balance_sheet <ticker> [freq] [curr_date]
    get_cashflow <ticker> [freq] [curr_date]
    get_income_statement <ticker> [freq] [curr_date]
    get_news <ticker> <start_date> <end_date>
    get_global_news <curr_date> [look_back_days] [limit]
    get_insider_transactions <ticker>

Memory Commands:
    memory_get <memory_name> <situation_file> [n_matches]
    memory_add <memory_name> <situation_file> <advice_file>
    memory_clear <memory_name>

Results Commands:
    save_results <ticker> <trade_date> <state_json_file>
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _init_config():
    """Initialize the data vendor configuration."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.dataflows.config import set_config
    set_config(DEFAULT_CONFIG)

    # Create data cache directory
    os.makedirs(
        os.path.join(DEFAULT_CONFIG["project_dir"], "dataflows/data_cache"),
        exist_ok=True,
    )


def _route(method, *args, **kwargs):
    """Route a method call through the vendor interface."""
    _init_config()
    from tradingagents.dataflows.interface import route_to_vendor
    return route_to_vendor(method, *args, **kwargs)


# --- Memory persistence helpers ---

MEMORY_DIR = Path("eval_results/.memory")


def _memory_path(name: str) -> Path:
    return MEMORY_DIR / f"{name}.json"


def _load_memory(name: str):
    """Load a FinancialSituationMemory from disk, or create a fresh one."""
    from tradingagents.agents.utils.memory import FinancialSituationMemory

    mem = FinancialSituationMemory(name)
    path = _memory_path(name)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        docs = data.get("documents", [])
        recs = data.get("recommendations", [])
        if docs and recs and len(docs) == len(recs):
            mem.add_situations(list(zip(docs, recs)))
    return mem


def _save_memory(name: str, mem):
    """Persist a FinancialSituationMemory to disk."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _memory_path(name)
    data = {
        "documents": mem.documents,
        "recommendations": mem.recommendations,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- Command handlers ---

def cmd_get_stock_data(args):
    result = _route("get_stock_data", args.symbol, args.start_date, args.end_date)
    print(result)


def cmd_get_indicators(args):
    look_back = int(args.look_back_days) if args.look_back_days else 30
    result = _route("get_indicators", args.symbol, args.indicator, args.curr_date, look_back)
    print(result)


def cmd_get_fundamentals(args):
    result = _route("get_fundamentals", args.ticker, args.curr_date)
    print(result)


def cmd_get_balance_sheet(args):
    freq = args.freq or "quarterly"
    curr_date = args.curr_date or None
    result = _route("get_balance_sheet", args.ticker, freq, curr_date)
    print(result)


def cmd_get_cashflow(args):
    freq = args.freq or "quarterly"
    curr_date = args.curr_date or None
    result = _route("get_cashflow", args.ticker, freq, curr_date)
    print(result)


def cmd_get_income_statement(args):
    freq = args.freq or "quarterly"
    curr_date = args.curr_date or None
    result = _route("get_income_statement", args.ticker, freq, curr_date)
    print(result)


def cmd_get_news(args):
    result = _route("get_news", args.ticker, args.start_date, args.end_date)
    print(result)


def cmd_get_global_news(args):
    look_back = int(args.look_back_days) if args.look_back_days else 7
    limit = int(args.limit) if args.limit else 5
    result = _route("get_global_news", args.curr_date, look_back, limit)
    print(result)


def cmd_get_insider_transactions(args):
    result = _route("get_insider_transactions", args.ticker)
    print(result)


def cmd_memory_get(args):
    situation_text = Path(args.situation_file).read_text(encoding="utf-8")
    n_matches = int(args.n_matches) if args.n_matches else 2

    mem = _load_memory(args.memory_name)
    results = mem.get_memories(situation_text, n_matches=n_matches)

    if not results:
        print("No past memories found.")
    else:
        for i, rec in enumerate(results, 1):
            print(f"--- Memory Match {i} (score: {rec['similarity_score']:.2f}) ---")
            print(rec["recommendation"])
            print()


def cmd_memory_add(args):
    situation_text = Path(args.situation_file).read_text(encoding="utf-8")
    advice_text = Path(args.advice_file).read_text(encoding="utf-8")

    mem = _load_memory(args.memory_name)
    mem.add_situations([(situation_text, advice_text)])
    _save_memory(args.memory_name, mem)
    print(f"Memory added to '{args.memory_name}'. Total entries: {len(mem.documents)}")


def cmd_memory_clear(args):
    path = _memory_path(args.memory_name)
    if path.exists():
        path.unlink()
    print(f"Memory '{args.memory_name}' cleared.")


def cmd_save_results(args):
    state_data = json.loads(Path(args.state_json_file).read_text(encoding="utf-8"))

    log_entry = {
        str(args.trade_date): {
            "company_of_interest": state_data.get("company_of_interest", args.ticker),
            "trade_date": args.trade_date,
            "market_report": state_data.get("market_report", ""),
            "sentiment_report": state_data.get("sentiment_report", ""),
            "news_report": state_data.get("news_report", ""),
            "fundamentals_report": state_data.get("fundamentals_report", ""),
            "investment_debate_state": state_data.get("investment_debate_state", {}),
            "trader_investment_decision": state_data.get("trader_investment_plan", ""),
            "risk_debate_state": state_data.get("risk_debate_state", {}),
            "investment_plan": state_data.get("investment_plan", ""),
            "final_trade_decision": state_data.get("final_trade_decision", ""),
        }
    }

    directory = Path(f"eval_results/{args.ticker}/TradingAgentsStrategy_logs/")
    directory.mkdir(parents=True, exist_ok=True)

    out_path = directory / f"full_states_log_{args.trade_date}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=4, ensure_ascii=False)

    print(f"Results saved to {out_path}")


# --- Argument parser ---

def build_parser():
    parser = argparse.ArgumentParser(
        description="TradingAgents CLI tools for Claude Code subagents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # get_stock_data
    p = subparsers.add_parser("get_stock_data", help="Get OHLCV stock price data")
    p.add_argument("symbol", help="Ticker symbol (e.g., AAPL)")
    p.add_argument("start_date", help="Start date (yyyy-mm-dd)")
    p.add_argument("end_date", help="End date (yyyy-mm-dd)")
    p.set_defaults(func=cmd_get_stock_data)

    # get_indicators
    p = subparsers.add_parser("get_indicators", help="Get technical indicators")
    p.add_argument("symbol", help="Ticker symbol")
    p.add_argument("indicator", help="Indicator name (e.g., rsi, macd)")
    p.add_argument("curr_date", help="Current trading date (yyyy-mm-dd)")
    p.add_argument("look_back_days", nargs="?", default=None, help="Lookback days (default: 30)")
    p.set_defaults(func=cmd_get_indicators)

    # get_fundamentals
    p = subparsers.add_parser("get_fundamentals", help="Get company fundamentals")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("curr_date", help="Current date (yyyy-mm-dd)")
    p.set_defaults(func=cmd_get_fundamentals)

    # get_balance_sheet
    p = subparsers.add_parser("get_balance_sheet", help="Get balance sheet data")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("freq", nargs="?", default=None, help="Frequency: annual/quarterly (default: quarterly)")
    p.add_argument("curr_date", nargs="?", default=None, help="Current date (yyyy-mm-dd)")
    p.set_defaults(func=cmd_get_balance_sheet)

    # get_cashflow
    p = subparsers.add_parser("get_cashflow", help="Get cash flow statement")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("freq", nargs="?", default=None, help="Frequency: annual/quarterly (default: quarterly)")
    p.add_argument("curr_date", nargs="?", default=None, help="Current date (yyyy-mm-dd)")
    p.set_defaults(func=cmd_get_cashflow)

    # get_income_statement
    p = subparsers.add_parser("get_income_statement", help="Get income statement")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("freq", nargs="?", default=None, help="Frequency: annual/quarterly (default: quarterly)")
    p.add_argument("curr_date", nargs="?", default=None, help="Current date (yyyy-mm-dd)")
    p.set_defaults(func=cmd_get_income_statement)

    # get_news
    p = subparsers.add_parser("get_news", help="Get company news")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("start_date", help="Start date (yyyy-mm-dd)")
    p.add_argument("end_date", help="End date (yyyy-mm-dd)")
    p.set_defaults(func=cmd_get_news)

    # get_global_news
    p = subparsers.add_parser("get_global_news", help="Get global macroeconomic news")
    p.add_argument("curr_date", help="Current date (yyyy-mm-dd)")
    p.add_argument("look_back_days", nargs="?", default=None, help="Lookback days (default: 7)")
    p.add_argument("limit", nargs="?", default=None, help="Max articles (default: 5)")
    p.set_defaults(func=cmd_get_global_news)

    # get_insider_transactions
    p = subparsers.add_parser("get_insider_transactions", help="Get insider transactions")
    p.add_argument("ticker", help="Ticker symbol")
    p.set_defaults(func=cmd_get_insider_transactions)

    # memory_get
    p = subparsers.add_parser("memory_get", help="Retrieve memories matching a situation")
    p.add_argument("memory_name", help="Memory name (e.g., bull_memory)")
    p.add_argument("situation_file", help="Path to file containing the situation text")
    p.add_argument("n_matches", nargs="?", default=None, help="Number of matches (default: 2)")
    p.set_defaults(func=cmd_memory_get)

    # memory_add
    p = subparsers.add_parser("memory_add", help="Add a situation+advice to memory")
    p.add_argument("memory_name", help="Memory name (e.g., bull_memory)")
    p.add_argument("situation_file", help="Path to file containing the situation text")
    p.add_argument("advice_file", help="Path to file containing the advice text")
    p.set_defaults(func=cmd_memory_add)

    # memory_clear
    p = subparsers.add_parser("memory_clear", help="Clear all entries from a memory")
    p.add_argument("memory_name", help="Memory name to clear")
    p.set_defaults(func=cmd_memory_clear)

    # save_results
    p = subparsers.add_parser("save_results", help="Save analysis results to JSON log")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("trade_date", help="Trade date (yyyy-mm-dd)")
    p.add_argument("state_json_file", help="Path to JSON file containing the full state")
    p.set_defaults(func=cmd_save_results)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
