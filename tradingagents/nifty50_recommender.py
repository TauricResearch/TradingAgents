"""
Nifty 50 Stock Recommendation System.

This module predicts all 50 Nifty stocks and selects the ones with highest
short-term growth potential using Claude Opus 4.5 via Claude Max subscription.
"""

import os
# Disable CUDA to avoid library issues with embeddings
os.environ["CUDA_VISIBLE_DEVICES"] = ""
# Remove API key to force Claude Max subscription auth
os.environ.pop("ANTHROPIC_API_KEY", None)

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.markets import NIFTY_50_STOCKS, get_nifty_50_list
from tradingagents.claude_max_llm import ClaudeMaxLLM


def verify_claude_cli() -> bool:
    """
    Verify that Claude CLI is available and authenticated.

    Returns:
        True if Claude CLI is available

    Raises:
        RuntimeError: If Claude CLI is not available or not authenticated
    """
    import subprocess

    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass

    raise RuntimeError(
        "Claude CLI is not available.\n\n"
        "To use this recommendation system with Claude Max subscription:\n"
        "1. Install Claude Code: npm install -g @anthropic-ai/claude-code\n"
        "2. Authenticate: claude auth login\n"
    )


def create_claude_config() -> Dict[str, Any]:
    """
    Create a configuration dictionary for using Claude models.

    Returns:
        Configuration dictionary with Anthropic settings
    """
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "anthropic"
    config["deep_think_llm"] = config["anthropic_config"]["deep_think_llm"]
    config["quick_think_llm"] = config["anthropic_config"]["quick_think_llm"]
    config["market"] = "india_nse"

    # Use jugaad_data for NSE stocks
    config["data_vendors"] = {
        "core_stock_apis": "jugaad_data",
        "technical_indicators": "jugaad_data",
        "fundamental_data": "yfinance",
        "news_data": "google",
    }

    return config


def predict_stock(
    graph: TradingAgentsGraph,
    symbol: str,
    trade_date: str
) -> Dict[str, Any]:
    """
    Run prediction for a single stock.

    Args:
        graph: The TradingAgentsGraph instance
        symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
        trade_date: Date for the prediction (YYYY-MM-DD format)

    Returns:
        Dictionary containing prediction results including decision,
        market report, fundamentals report, news report, investment plan,
        and final trade decision
    """
    try:
        final_state, decision = graph.propagate(symbol, trade_date)

        return {
            "symbol": symbol,
            "company_name": NIFTY_50_STOCKS.get(symbol, symbol),
            "decision": decision,
            "market_report": final_state.get("market_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "news_report": final_state.get("news_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
            "investment_debate": {
                "bull_history": final_state.get("investment_debate_state", {}).get("bull_history", ""),
                "bear_history": final_state.get("investment_debate_state", {}).get("bear_history", ""),
                "judge_decision": final_state.get("investment_debate_state", {}).get("judge_decision", ""),
            },
            "risk_debate": {
                "risky_history": final_state.get("risk_debate_state", {}).get("risky_history", ""),
                "safe_history": final_state.get("risk_debate_state", {}).get("safe_history", ""),
                "neutral_history": final_state.get("risk_debate_state", {}).get("neutral_history", ""),
                "judge_decision": final_state.get("risk_debate_state", {}).get("judge_decision", ""),
            },
            "error": None,
        }
    except Exception as e:
        return {
            "symbol": symbol,
            "company_name": NIFTY_50_STOCKS.get(symbol, symbol),
            "decision": None,
            "error": str(e),
        }


def predict_all_nifty50(
    trade_date: str,
    config: Optional[Dict[str, Any]] = None,
    stock_subset: Optional[List[str]] = None,
    on_progress: Optional[callable] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Run predictions for all 50 Nifty stocks (or a subset).

    Args:
        trade_date: Date for the predictions (YYYY-MM-DD format)
        config: Optional configuration dictionary. If None, uses Claude config
        stock_subset: Optional list of stock symbols to analyze. If None, analyzes all 50
        on_progress: Optional callback function(current_index, total, symbol, result)

    Returns:
        Dictionary mapping stock symbols to their prediction results
    """
    if config is None:
        config = create_claude_config()

    # Verify Claude CLI is available for Max subscription
    verify_claude_cli()

    # Initialize the graph
    graph = TradingAgentsGraph(
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config=config
    )

    # Get list of stocks to analyze
    stocks = stock_subset if stock_subset else get_nifty_50_list()
    total = len(stocks)

    predictions = {}

    for i, symbol in enumerate(stocks, 1):
        result = predict_stock(graph, symbol, trade_date)
        predictions[symbol] = result

        if on_progress:
            on_progress(i, total, symbol, result)

    return predictions


def format_predictions_for_prompt(predictions: Dict[str, Dict[str, Any]]) -> str:
    """
    Format all predictions into a comprehensive prompt for Claude.

    Args:
        predictions: Dictionary of prediction results

    Returns:
        Formatted string containing all predictions
    """
    formatted_parts = []

    for symbol, pred in predictions.items():
        if pred.get("error"):
            formatted_parts.append(f"""
=== {symbol} ({pred.get('company_name', symbol)}) ===
ERROR: {pred['error']}
""")
            continue

        formatted_parts.append(f"""
=== {symbol} ({pred.get('company_name', symbol)}) ===

DECISION: {pred.get('decision', 'N/A')}

MARKET ANALYSIS:
{pred.get('market_report', 'N/A')[:1000]}

FUNDAMENTALS:
{pred.get('fundamentals_report', 'N/A')[:1000]}

NEWS & SENTIMENT:
{pred.get('news_report', 'N/A')[:500]}
{pred.get('sentiment_report', 'N/A')[:500]}

INVESTMENT PLAN:
{pred.get('investment_plan', 'N/A')[:500]}

FINAL TRADE DECISION:
{pred.get('final_trade_decision', 'N/A')[:500]}

BULL/BEAR DEBATE SUMMARY:
Bull: {pred.get('investment_debate', {}).get('bull_history', 'N/A')[:300]}
Bear: {pred.get('investment_debate', {}).get('bear_history', 'N/A')[:300]}
Judge: {pred.get('investment_debate', {}).get('judge_decision', 'N/A')[:300]}

RISK ASSESSMENT:
{pred.get('risk_debate', {}).get('judge_decision', 'N/A')[:300]}

---
""")

    return "\n".join(formatted_parts)


def parse_ranking_response(response_text: str) -> Dict[str, Any]:
    """
    Parse the ranking response from Claude.

    Args:
        response_text: Raw response text from Claude

    Returns:
        Dictionary containing parsed ranking results
    """
    return {
        "raw_response": response_text,
        "parsed": True,
    }


def rank_stocks_for_growth(
    predictions: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Use Claude Opus 4.5 to rank stocks by short-term growth potential.

    Args:
        predictions: Dictionary of prediction results for all stocks

    Returns:
        Dictionary containing ranking results with top picks and stocks to avoid
    """
    # Initialize Claude Opus via Max subscription
    llm = ClaudeMaxLLM(model="opus")

    # Filter out stocks with errors
    valid_predictions = {
        k: v for k, v in predictions.items()
        if not v.get("error")
    }

    if not valid_predictions:
        return {
            "error": "No valid predictions to rank",
            "top_picks": [],
            "stocks_to_avoid": [],
        }

    # Format predictions for prompt
    formatted = format_predictions_for_prompt(valid_predictions)

    prompt = f"""You are an expert stock analyst specializing in the Indian equity market.
Analyze the following predictions for Nifty 50 stocks and select the TOP 3 stocks with
the highest short-term growth potential (1-2 weeks timeframe).

For each stock, consider:
1. BUY/SELL/HOLD decision and the confidence level
2. Technical indicators and price momentum
3. Fundamental strength (earnings, revenue, valuations)
4. News sentiment and potential catalysts
5. Risk factors and volatility

STOCK PREDICTIONS:
{formatted}

Based on your comprehensive analysis, provide your recommendations in the following format:

## TOP 3 PICKS FOR SHORT-TERM GROWTH

### 1. TOP PICK: [SYMBOL]
**Company:** [Company Name]
**Recommendation:** [BUY/STRONG BUY]
**Target Upside:** [X%]
**Reasoning:** [2-3 sentences explaining why this is the top pick, citing specific data points]
**Key Catalysts:** [List 2-3 near-term catalysts]
**Risk Level:** [Low/Medium/High]

### 2. SECOND PICK: [SYMBOL]
**Company:** [Company Name]
**Recommendation:** [BUY/STRONG BUY]
**Target Upside:** [X%]
**Reasoning:** [2-3 sentences]
**Key Catalysts:** [List 2-3 near-term catalysts]
**Risk Level:** [Low/Medium/High]

### 3. THIRD PICK: [SYMBOL]
**Company:** [Company Name]
**Recommendation:** [BUY/STRONG BUY]
**Target Upside:** [X%]
**Reasoning:** [2-3 sentences]
**Key Catalysts:** [List 2-3 near-term catalysts]
**Risk Level:** [Low/Medium/High]

## STOCKS TO AVOID

List any stocks that show concerning signals and should be avoided:
- [SYMBOL]: [Brief reason - e.g., "Bearish technical setup, negative news flow"]
- [SYMBOL]: [Brief reason]

## MARKET CONTEXT

Provide a brief (2-3 sentences) overview of the current market conditions affecting these recommendations.

## DISCLAIMER

Include a brief investment disclaimer.
"""

    # Use Claude Opus 4.5's large context window
    response = llm.invoke(prompt)

    return {
        "ranking_analysis": response.content,
        "total_stocks_analyzed": len(valid_predictions),
        "stocks_with_errors": len(predictions) - len(valid_predictions),
        "timestamp": datetime.now().isoformat(),
    }


def run_recommendation(
    trade_date: str,
    stock_subset: Optional[List[str]] = None,
    save_results: bool = True,
    results_dir: Optional[str] = None,
    verbose: bool = True
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """
    Main entry point for running the Nifty 50 recommendation system.

    Args:
        trade_date: Date for the predictions (YYYY-MM-DD format)
        stock_subset: Optional list of stock symbols to analyze. If None, analyzes all 50
        save_results: Whether to save results to disk
        results_dir: Directory to save results. If None, uses default
        verbose: Whether to print progress updates

    Returns:
        Tuple of (predictions dict, ranking results dict)
    """
    def progress_callback(current, total, symbol, result):
        if verbose:
            status = "✓" if not result.get("error") else "✗"
            decision = result.get("decision", "ERROR") if not result.get("error") else "ERROR"
            print(f"[{current}/{total}] {symbol}: {status} {decision}")

    if verbose:
        print(f"\n{'='*60}")
        print(f"NIFTY 50 STOCK RECOMMENDATION SYSTEM")
        print(f"{'='*60}")
        print(f"Date: {trade_date}")
        stocks = stock_subset if stock_subset else get_nifty_50_list()
        print(f"Analyzing {len(stocks)} stocks...")
        print(f"{'='*60}\n")

    # Run predictions for all stocks
    predictions = predict_all_nifty50(
        trade_date=trade_date,
        stock_subset=stock_subset,
        on_progress=progress_callback
    )

    if verbose:
        successful = sum(1 for p in predictions.values() if not p.get("error"))
        print(f"\n{'='*60}")
        print(f"Predictions Complete: {successful}/{len(predictions)} successful")
        print(f"{'='*60}\n")
        print("Ranking stocks with Claude Opus 4.5...")

    # Rank stocks using Claude Opus 4.5
    ranking = rank_stocks_for_growth(predictions)

    if verbose:
        print(f"\n{'='*60}")
        print("RECOMMENDATION RESULTS")
        print(f"{'='*60}\n")
        print(ranking.get("ranking_analysis", "No ranking available"))

    # Save results if requested
    if save_results:
        if results_dir is None:
            results_dir = Path(DEFAULT_CONFIG["results_dir"]) / "nifty50_recommendations"
        else:
            results_dir = Path(results_dir)

        results_dir.mkdir(parents=True, exist_ok=True)

        # Save predictions
        predictions_file = results_dir / f"predictions_{trade_date}.json"
        with open(predictions_file, "w") as f:
            # Convert to serializable format
            serializable_predictions = {}
            for symbol, pred in predictions.items():
                serializable_predictions[symbol] = {
                    k: str(v) if not isinstance(v, (str, dict, list, type(None))) else v
                    for k, v in pred.items()
                }
            json.dump(serializable_predictions, f, indent=2)

        # Save ranking
        ranking_file = results_dir / f"ranking_{trade_date}.json"
        with open(ranking_file, "w") as f:
            json.dump(ranking, f, indent=2)

        # Save readable report
        report_file = results_dir / f"report_{trade_date}.md"
        with open(report_file, "w") as f:
            f.write(f"# Nifty 50 Stock Recommendation Report\n\n")
            f.write(f"**Date:** {trade_date}\n\n")
            f.write(f"**Stocks Analyzed:** {ranking.get('total_stocks_analyzed', 0)}\n\n")
            f.write(f"**Generated:** {ranking.get('timestamp', 'N/A')}\n\n")
            f.write("---\n\n")
            f.write(ranking.get("ranking_analysis", "No ranking available"))

        if verbose:
            print(f"\nResults saved to: {results_dir}")

    return predictions, ranking
