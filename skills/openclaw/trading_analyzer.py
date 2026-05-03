"""OpenClaw Trading Analysis Skill

This skill enables OpenClaw users to analyze stocks directly from Telegram,
WhatsApp, Discord, Slack, or any other integrated chat app.

Installation:
1. Copy this skill to your OpenClaw skills directory
2. Or install directly:
   openclaw skill add trading-analyzer

Usage:
   - "Analyze NVDA"
   - "What's the trading setup for TSLA?"
   - "Do market analysis for BTC"
   - "Trading outlook for AAPL as of 2024-05-10"

The skill will return:
   - Market & technical analysis
   - Fundamental insights
   - Risk assessment
   - Investment recommendation (Buy/Hold/Sell)
   - Detailed rationale

Prerequisites:
   - OpenClaw running with trading-agents installed
   - LLM endpoint configured (OpenAI, Anthropic, Google, etc.)
   - Optional: tradingagents pip package for local setup
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
import traceback


def parse_trading_command(user_input: str) -> tuple[str, Optional[str]]:
    """Parse user input to extract ticker and optional date.

    Args:
        user_input: e.g., "Analyze NVDA" or "TSLA as of 2024-05-10"

    Returns:
        (ticker, date_str) tuple
    """
    parts = user_input.strip().split()

    # Try to extract ticker (usually a word with 1-5 chars that's all uppercase)
    ticker = None
    for part in parts:
        cleaned = part.upper().replace(",", "").replace(".", "")
        if 1 <= len(cleaned) <= 5 and cleaned.isalpha() and cleaned not in {"THE", "AND", "FOR", "WITH", "THIS", "THAT", "HELP"}:
            ticker = cleaned
            break

    # Try to extract date (YYYY-MM-DD format)
    date_str = None
    for part in parts:
        if (
            len(part) == 10
            and part[4] == "-"
            and part[7] == "-"
            and part[:4].isdigit()
        ):
            date_str = part
            break

    return ticker, date_str


def analyze_stock(
    ticker: str,
    date: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> str:
    """Analyze a stock using TradingAgents.

    Args:
        ticker: Stock ticker symbol (e.g., "NVDA")
        date: Optional analysis date in YYYY-MM-DD format
        llm_provider: LLM provider (defaults to env OPENCLAW_LLM_PROVIDER)
        llm_model: LLM model (defaults to env OPENCLAW_LLM_MODEL)

    Returns:
        Formatted analysis report as string
    """
    try:
        from tradingagents.graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
    except ImportError:
        return (
            "⚠️ Trading Agents library not found.\n\n"
            "To enable full analysis, install tradingagents:\n"
            "```\npip install tradingagents\n```\n\n"
            "Or use the cloud API endpoint by setting OPENCLAW_TRADING_API_URL"
        )

    try:
        # Use provided LLM provider or default to OpenClaw
        provider = llm_provider or os.getenv("OPENCLAW_LLM_PROVIDER", "openclaw")
        model = llm_model or os.getenv("OPENCLAW_LLM_MODEL", "gpt-4")

        # Use today's date if not specified
        if not date:
            from datetime import timezone
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Create trading graph with specified provider
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = provider
        config["deep_think_llm"] = model
        config["quick_think_llm"] = model

        ta = TradingAgentsGraph(debug=False, config=config)

        # Run analysis
        print(f"🔄 Analyzing {ticker} as of {date}...")
        state, decision = ta.propagate(ticker, date)

        # Format the response
        report = format_trading_report(state, decision)
        return report

    except Exception as e:
        error_msg = f"Error analyzing {ticker}: {str(e)}"
        return f"❌ {error_msg}\n\nPlease check the application logs for more details."


def format_trading_report(state: Dict[str, Any], decision: Dict[str, Any]) -> str:
    """Format trading analysis results for chat display.

    Args:
        state: Trading graph state
        decision: Final trading decision

    Returns:
        Formatted markdown report
    """
    lines = []

    # Header
    ticker = state.get("company_of_interest", "?")
    trade_date = state.get("trade_date", "?")
    lines.append(f"📊 **Stock Analysis: {ticker} ({trade_date})**\n")

    # Analyst reports (if available)
    if "market_report" in state:
        lines.append("### Market Analysis")
        report = state["market_report"]
        lines.append(f"{report[:500]}...\n" if len(report) > 500 else f"{report}\n")

    if "fundamentals_report" in state:
        lines.append("### Fundamentals")
        lines.append(state["fundamentals_report"][:500] + "...\n")

    if "news_report" in state:
        lines.append("### News & Events")
        lines.append(state["news_report"][:500] + "...\n")

    # Investment recommendation
    if isinstance(decision, dict):
        if "recommendation" in decision:
            rec = decision["recommendation"]
            emoji = {
                "Buy": "🟢",
                "Overweight": "🟡",
                "Hold": "🤐",
                "Underweight": "🟠",
                "Sell": "🔴",
            }.get(rec, "❓")
            lines.append(f"### Recommendation: {emoji} {rec}")

        if "rationale" in decision:
            lines.append(f"\n{decision['rationale'][:300]}...\n")

    lines.append("\n💡 *Get detailed analysis in TradingAgents dashboard*")
    return "\n".join(lines)


async def handle_trading_query(
    message: str,
    user_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Handle incoming trading query from OpenClaw.

    This is the main entry point for the OpenClaw skill.

    Args:
        message: User message (e.g., "Analyze NVDA")
        user_context: Optional context about the user/conversation

    Returns:
        Trading analysis response
    """
    # Parse the command
    ticker, date = parse_trading_command(message)

    if not ticker:
        return (
            "📈 I can help you analyze stocks!\n\n"
            "Try:\n"
            "- \"Analyze NVDA\"\n"
            "- \"TSLA trading setup\"\n"
            "- \"Market analysis for SPY as of 2024-05-10\"\n"
            "- \"What's the outlook for AAPL?\"\n\n"
            "Supported tickers: Any publicly traded stock symbol"
        )

    # Run analysis
    import asyncio
    report = await asyncio.to_thread(analyze_stock, ticker, date)
    return report


# OpenClaw skill manifest
SKILL_MANIFEST = {
    "name": "trading-analyzer",
    "display_name": "Stock Trading Analyzer",
    "description": "Multi-agent LLM stock analysis via TradingAgents",
    "version": "1.0.0",
    "author": "TradingAgents Contributors",
    "repository": "https://github.com/dkoul/TradingAgents",
    "keywords": ["trading", "stocks", "analysis", "finance", "agents"],
    "triggers": ["analyze", "trading", "stock", "market"],
    "requires": {
        "llm_provider": ["openai", "anthropic", "google", "openclaw", "deepseek"],
        "python_packages": ["tradingagents"],
    },
    "entry_point": "handle_trading_query",
}

if __name__ == "__main__":
    # Quick test
    import asyncio

    test_queries = [
        "Analyze NVDA",
        "What about TSLA?",
        "Trading setup for SPY as of 2024-01-15",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")
        result = asyncio.run(handle_trading_query(query))
        print(result)
