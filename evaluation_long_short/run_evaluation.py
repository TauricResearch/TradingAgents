"""
Main evaluation script to run backtesting and generate results.
Evaluates TradingAgents against baseline strategies for a single ticker.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation_long_short.baseline_strategies import get_all_baseline_strategies
from evaluation_long_short.backtest import BacktestEngine, TradingAgentsBacktester, load_stock_data, standardize_single_ticker
from evaluation_long_short.metrics import calculate_all_metrics, create_comparison_table, print_metrics
from evaluation_long_short.visualize import plot_cumulative_returns_from_results

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

def is_debugging() -> bool:
    try:
        import debugpy
        return debugpy.is_client_connected()
    except Exception:
        return False


def save_strategy_actions_to_json(
    portfolio: pd.DataFrame, 
    strategy_name: str, 
    ticker: str, 
    start_date: str, 
    end_date: str,
    output_dir: str
) -> None:
    """
    Save daily actions from a strategy to a JSON file.
    
    Args:
        portfolio: Portfolio DataFrame with action, position, close, etc.
        strategy_name: Name of the strategy
        ticker: Stock ticker symbol
        start_date: Start date of backtest
        end_date: End date of backtest
        output_dir: Directory to save the JSON file
    """
    out = Path(output_dir) / ticker / strategy_name
    out.mkdir(parents=True, exist_ok=True)
    
    # Build actions list with relevant daily info
    actions = []
    for date, row in portfolio.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        action_record = {
            "date": date_str,
            "action": int(row["action"]) if pd.notna(row["action"]) else 0,  # 1=BUY, 0=HOLD, -1=SELL
            "position": int(row["position"]) if pd.notna(row["position"]) else 0,  # 1=long, 0=flat
            "close_price": float(row["close"]) if pd.notna(row["close"]) else None,
            "portfolio_value": float(row["portfolio_value"]) if pd.notna(row["portfolio_value"]) else None,
            "strategy_return": float(row["strategy_return"]) if pd.notna(row["strategy_return"]) else 0.0,
            "cumulative_return": float(row["cumulative_return"]) if pd.notna(row["cumulative_return"]) else 1.0
        }
        actions.append(action_record)
    
    # Save to JSON
    fp = out / f"actions_{start_date}_to_{end_date}.json"
    with open(fp, "w") as f:
        json.dump({
            "strategy": strategy_name,
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "total_days": len(actions),
            "actions": actions
        }, f, indent=2)
    
    print(f"  ✓ Saved {strategy_name} actions to: {fp}")


def run_evaluation(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000,
    include_tradingagents: bool = True,
    output_dir: str = None,
    config: dict = None
):
    """
    Run complete evaluation: baselines + TradingAgents for a single ticker.
    """
    print(f"\n{'='*80}")
    print(f"EVALUATION: {ticker} from {start_date} to {end_date}")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"{'='*80}\n")

    # Output dir
    if output_dir is None:
        output_dir = f"eval_results/{ticker}/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load data
    print("\n" + "="*80)
    print("STEP 1: Loading Stock Data")
    print("="*80)
    data = load_stock_data(ticker, start_date, end_date)
    data = standardize_single_ticker(data, ticker)

    # Backtest engine
    engine = BacktestEngine(data, initial_capital)

    # Baselines
    print("\n" + "="*80)
    print("STEP 2: Running Baseline Strategies")
    print("="*80)
    baselines = get_all_baseline_strategies(initial_capital)

    for name, strategy in baselines.items():
        try:
            print(f"\nRunning {name}...", end=" ")
            portfolio = engine.run_strategy(strategy, start_date, end_date)
            print("✓ Complete")
            # Save actions to JSON
            save_strategy_actions_to_json(portfolio, name, ticker, start_date, end_date, output_dir)
        except Exception as e:
            print(f"✗ Failed: {e}")

    # TradingAgents
    if include_tradingagents:
        print("\n" + "="*80)
        print("STEP 3: Running TradingAgents")
        print("="*80)
        try:
            cfg = (config or DEFAULT_CONFIG).copy()
            # Fast eval defaults (you can override from CLI)
            cfg["deep_think_llm"] = cfg.get("deep_think_llm", "o4-mini")
            cfg["quick_think_llm"] = cfg.get("quick_think_llm", "gpt-4o-mini")
            cfg["max_debate_rounds"] = cfg.get("max_debate_rounds", 1)
            cfg["max_risk_discuss_rounds"] = cfg.get("max_risk_discuss_rounds", 1)
            # Deterministic-ish decoding for reproducibility
            cfg.setdefault("llm_params", {}).update({"temperature": 0.7, "top_p": 1.0, "seed": 42})

            print(f"\nInitializing TradingAgents...")
            print(f"  Deep Thinking LLM: {cfg['deep_think_llm']}")
            print(f"  Quick Thinking LLM: {cfg['quick_think_llm']}")
            print(f"  Debate Rounds: {cfg['max_debate_rounds']}")

            graph = TradingAgentsGraph(
                selected_analysts=["news"],
                # selected_analysts=["market", "social", "news", "fundamentals"],
                debug=False,
                config=cfg
            )
            ta_backtester = TradingAgentsBacktester(graph, initial_capital, output_dir)
            ta_portfolio = ta_backtester.backtest(ticker, start_date, end_date, data)

            engine.results["TradingAgents"] = ta_portfolio
            print("\n✓ TradingAgents backtest complete")
            
            # Save TradingAgents actions to JSON (in consistent format with baselines)
            save_strategy_actions_to_json(ta_portfolio, "TradingAgents", ticker, start_date, end_date, output_dir)

        except Exception as e:
            print(f"\n✗ TradingAgents failed: {e}")
            import traceback
            traceback.print_exc()

    # Metrics
    print("\n" + "="*80)
    print("STEP 4: Calculating Performance Metrics")
    print("="*80)
    all_metrics = {}
    for name, portfolio in engine.results.items():
        metrics = calculate_all_metrics(portfolio)
        all_metrics[name] = metrics
        print_metrics(metrics, name)

    # Generate cumulative returns comparison plot
    print("\n" + "="*80)
    print("STEP 5: Generating Comparison Plot")
    print("="*80)
    try:
        comparison_plot_path = str(out / ticker / "strategy_comparison.png")
        plot_cumulative_returns_from_results(
            results_dir=str(out / ticker),
            ticker=ticker,
            output_path=comparison_plot_path
        )
        # Also save as PDF
        pdf_path = comparison_plot_path.replace('.png', '.pdf')
        plot_cumulative_returns_from_results(
            results_dir=str(out / ticker),
            ticker=ticker,
            output_path=pdf_path
        )
        print(f"\n✓ Comparison plot saved to:")
        print(f"  - {comparison_plot_path}")
        print(f"  - {pdf_path}")
    except Exception as e:
        print(f"\n✗ Failed to generate comparison plot: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print("EVALUATION COMPLETE")
    print("="*80)
    print(f"\nResults saved to: {out}")
    print(f"\nDaily actions JSON files saved for:")
    for name in engine.results.keys():
        print(f"  ✓ {name}")

    return engine.results, all_metrics


def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents evaluation with baseline comparisons")
    parser.add_argument("--ticker", type=str, help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("--start-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=100000, help="Initial capital (default: 100000)")
    parser.add_argument("--skip-tradingagents", action="store_true", help="Skip TradingAgents evaluation")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for results")
    parser.add_argument("--deep-llm", type=str, default="o4-mini", help="Deep thinking LLM model")
    parser.add_argument("--quick-llm", type=str, default="gpt-4o-mini", help="Quick thinking LLM model")
    parser.add_argument("--debate-rounds", type=int, default=1, help="Number of debate rounds (default: 1)")

    # Used for debugging

    if is_debugging():
        config = DEFAULT_CONFIG.copy()
        config.update({
            "deep_think_llm": "o4-mini",
            "quick_think_llm": "gpt-4o-mini",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "llm_params": {"temperature": 0.7, "top_p": 1.0, "seed": 42},
        })
        run_evaluation(
            ticker="AAPL",
            start_date="2024-01-01",
            end_date="2024-01-10",
            initial_capital=1000,
            include_tradingagents=True,
            output_dir="./evaluation_long_short/results",
            config=config
        )
        return

    # Build config
    args = parser.parse_args()
    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = args.deep_llm
    config["quick_think_llm"] = args.quick_llm
    config["max_debate_rounds"] = args.debate_rounds
    config["max_risk_discuss_rounds"] = args.debate_rounds
    config.setdefault("llm_params", {}).update({"temperature": 0, "top_p": 1.0, "seed": 42})

    run_evaluation(
        ticker=args.ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.capital,
        include_tradingagents=not args.skip_tradingagents,
        output_dir=args.output_dir,
        config=config
    )

if __name__ == "__main__":
    main()