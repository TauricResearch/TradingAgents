"""
Simplified Nifty 50 Stock Recommendation System.

This module uses Claude Max subscription (via CLI) to analyze pre-fetched stock data
and provide recommendations. It bypasses the complex agent framework to work with
Claude Max subscription without API keys.
"""

import os
# Disable CUDA to avoid library issues with embeddings
os.environ["CUDA_VISIBLE_DEVICES"] = ""
# Remove API key to force Claude Max subscription auth
os.environ.pop("ANTHROPIC_API_KEY", None)

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

from tradingagents.dataflows.markets import NIFTY_50_STOCKS, get_nifty_50_list
from tradingagents.claude_max_llm import ClaudeMaxLLM

# Import data fetching tools
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_news,
)


def fetch_stock_data(symbol: str, trade_date: str) -> Dict[str, str]:
    """
    Fetch all relevant data for a stock.

    Args:
        symbol: Stock symbol (e.g., 'TCS', 'RELIANCE')
        trade_date: Date for analysis (YYYY-MM-DD)

    Returns:
        Dictionary with stock data, indicators, fundamentals, and news
    """
    # Calculate date range (10 days before trade date)
    end_date = trade_date
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")

    data = {}

    # Fetch stock price data
    try:
        data["price_data"] = get_stock_data.invoke({
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date
        })
    except Exception as e:
        data["price_data"] = f"Error fetching price data: {e}"

    # Fetch technical indicators
    try:
        data["indicators"] = get_indicators.invoke({
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date
        })
    except Exception as e:
        data["indicators"] = f"Error fetching indicators: {e}"

    # Fetch fundamentals
    try:
        data["fundamentals"] = get_fundamentals.invoke({
            "symbol": symbol
        })
    except Exception as e:
        data["fundamentals"] = f"Error fetching fundamentals: {e}"

    # Fetch news
    try:
        company_name = NIFTY_50_STOCKS.get(symbol, symbol)
        data["news"] = get_news.invoke({
            "symbol": symbol,
            "company_name": company_name
        })
    except Exception as e:
        data["news"] = f"Error fetching news: {e}"

    return data


def analyze_stock(symbol: str, data: Dict[str, str], llm: ClaudeMaxLLM) -> Dict[str, Any]:
    """
    Use Claude to analyze a stock based on pre-fetched data.

    Args:
        symbol: Stock symbol
        data: Pre-fetched stock data
        llm: ClaudeMaxLLM instance

    Returns:
        Analysis result with decision and reasoning
    """
    company_name = NIFTY_50_STOCKS.get(symbol, symbol)

    prompt = f"""You are an expert stock analyst. Analyze the following data for {symbol} ({company_name}) and provide:
1. A trading decision: BUY, SELL, or HOLD
2. Confidence level: High, Medium, or Low
3. Key reasoning (2-3 sentences)
4. Risk assessment: High, Medium, or Low

## Price Data (Last 30 days)
{data.get('price_data', 'Not available')[:2000]}

## Technical Indicators
{data.get('indicators', 'Not available')[:2000]}

## Fundamentals
{data.get('fundamentals', 'Not available')[:2000]}

## Recent News
{data.get('news', 'Not available')[:1500]}

Provide your analysis in this exact format:
DECISION: [BUY/SELL/HOLD]
CONFIDENCE: [High/Medium/Low]
REASONING: [Your 2-3 sentence reasoning]
RISK: [High/Medium/Low]
TARGET: [Expected price movement in next 1-2 weeks, e.g., "+5%" or "-3%"]
"""

    try:
        response = llm.invoke(prompt)
        analysis_text = response.content

        # Parse the response
        result = {
            "symbol": symbol,
            "company_name": company_name,
            "raw_analysis": analysis_text,
            "error": None
        }

        # Extract structured data (handle markdown formatting like **DECISION:**)
        import re
        text_upper = analysis_text.upper()

        # Look for DECISION
        decision_match = re.search(r'\*?\*?DECISION:?\*?\*?\s*([A-Z]+)', text_upper)
        if decision_match:
            result["decision"] = decision_match.group(1).strip()

        # Look for CONFIDENCE
        confidence_match = re.search(r'\*?\*?CONFIDENCE:?\*?\*?\s*([A-Z]+)', text_upper)
        if confidence_match:
            result["confidence"] = confidence_match.group(1).strip()

        # Look for RISK
        risk_match = re.search(r'\*?\*?RISK:?\*?\*?\s*([A-Z]+)', text_upper)
        if risk_match:
            result["risk"] = risk_match.group(1).strip()

        return result

    except Exception as e:
        return {
            "symbol": symbol,
            "company_name": company_name,
            "decision": None,
            "error": str(e)
        }


def analyze_all_stocks(
    trade_date: str,
    stock_subset: Optional[List[str]] = None,
    on_progress: Optional[callable] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Analyze all Nifty 50 stocks (or a subset).

    Args:
        trade_date: Date for analysis
        stock_subset: Optional list of symbols to analyze
        on_progress: Optional callback(current, total, symbol, result)

    Returns:
        Dictionary of analysis results
    """
    # Initialize Claude LLM
    llm = ClaudeMaxLLM(model="sonnet")

    stocks = stock_subset if stock_subset else get_nifty_50_list()
    total = len(stocks)
    results = {}

    for i, symbol in enumerate(stocks, 1):
        # Fetch data
        data = fetch_stock_data(symbol, trade_date)

        # Analyze with Claude
        analysis = analyze_stock(symbol, data, llm)
        results[symbol] = analysis

        if on_progress:
            on_progress(i, total, symbol, analysis)

    return results


def rank_stocks(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Rank stocks by growth potential using Claude Opus.

    Args:
        results: Analysis results for all stocks

    Returns:
        Ranking with top picks
    """
    llm = ClaudeMaxLLM(model="opus")

    # Build summary of all analyses
    summaries = []
    for symbol, analysis in results.items():
        if analysis.get("error"):
            continue
        summaries.append(f"""
{symbol} ({analysis.get('company_name', symbol)}):
- Decision: {analysis.get('decision', 'N/A')}
- Confidence: {analysis.get('confidence', 'N/A')}
- Risk: {analysis.get('risk', 'N/A')}
- Analysis: {analysis.get('raw_analysis', 'N/A')[:300]}
""")

    if not summaries:
        return {"error": "No valid analyses to rank", "ranking": None}

    prompt = f"""You are an expert stock analyst. Based on the following analyses of Nifty 50 stocks,
identify the TOP 3 stocks with highest short-term growth potential (1-2 weeks).

## Stock Analyses
{''.join(summaries)}

Provide your ranking in this format:

## TOP 3 PICKS

### 1. [SYMBOL] - TOP PICK
**Decision:** [BUY/STRONG BUY]
**Reason:** [2-3 sentences explaining why this is the top pick]
**Risk Level:** [Low/Medium/High]

### 2. [SYMBOL] - SECOND PICK
**Decision:** [BUY]
**Reason:** [2-3 sentences]
**Risk Level:** [Low/Medium/High]

### 3. [SYMBOL] - THIRD PICK
**Decision:** [BUY]
**Reason:** [2-3 sentences]
**Risk Level:** [Low/Medium/High]

## STOCKS TO AVOID
List 2-3 stocks that should be avoided with brief reasons.
"""

    try:
        response = llm.invoke(prompt)
        return {
            "ranking": response.content,
            "stocks_analyzed": len(summaries),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "ranking": None}


def run_recommendation(
    trade_date: str,
    stock_subset: Optional[List[str]] = None,
    save_results: bool = True,
    results_dir: Optional[str] = None,
    verbose: bool = True
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """
    Main entry point for the recommendation system.

    Args:
        trade_date: Date for analysis
        stock_subset: Optional list of symbols
        save_results: Whether to save results to disk
        results_dir: Directory for results
        verbose: Print progress

    Returns:
        Tuple of (analysis results, ranking)
    """
    def progress_callback(current, total, symbol, result):
        if verbose:
            status = "✓" if not result.get("error") else "✗"
            decision = result.get("decision", "ERROR") if not result.get("error") else "ERROR"
            print(f"[{current}/{total}] {symbol}: {status} {decision}")

    if verbose:
        print(f"\n{'='*60}")
        print("NIFTY 50 STOCK RECOMMENDATION SYSTEM (Simple)")
        print(f"{'='*60}")
        print(f"Date: {trade_date}")
        stocks = stock_subset if stock_subset else get_nifty_50_list()
        print(f"Analyzing {len(stocks)} stocks...")
        print(f"Using Claude Max subscription via CLI")
        print(f"{'='*60}\n")

    # Analyze all stocks
    results = analyze_all_stocks(trade_date, stock_subset, progress_callback)

    if verbose:
        successful = sum(1 for r in results.values() if not r.get("error"))
        print(f"\n{'='*60}")
        print(f"Analysis Complete: {successful}/{len(results)} successful")
        print(f"{'='*60}\n")
        print("Ranking stocks with Claude Opus...")

    # Rank stocks
    ranking = rank_stocks(results)

    if verbose:
        print(f"\n{'='*60}")
        print("RECOMMENDATION RESULTS")
        print(f"{'='*60}\n")
        if ranking.get("ranking"):
            print(ranking["ranking"])
        else:
            print(f"Error: {ranking.get('error', 'Unknown error')}")

    # Save results if requested
    if save_results:
        from tradingagents.default_config import DEFAULT_CONFIG
        if results_dir is None:
            results_dir = Path(DEFAULT_CONFIG["results_dir"]) / "nifty50_simple_recommendations"
        else:
            results_dir = Path(results_dir)

        results_dir.mkdir(parents=True, exist_ok=True)

        # Save analysis results
        with open(results_dir / f"analysis_{trade_date}.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

        # Save ranking
        with open(results_dir / f"ranking_{trade_date}.json", "w") as f:
            json.dump(ranking, f, indent=2, default=str)

        # Save readable report
        with open(results_dir / f"report_{trade_date}.md", "w") as f:
            f.write(f"# Nifty 50 Stock Recommendation Report\n\n")
            f.write(f"**Date:** {trade_date}\n\n")
            f.write(f"**Stocks Analyzed:** {ranking.get('stocks_analyzed', 0)}\n\n")
            f.write("---\n\n")
            f.write(ranking.get("ranking", "No ranking available"))

        if verbose:
            print(f"\nResults saved to: {results_dir}")

    return results, ranking
