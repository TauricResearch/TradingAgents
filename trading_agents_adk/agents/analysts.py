"""Analyst agents built with Google ADK.

Each analyst is an LlmAgent with specialized tools and instructions.
They write their reports to shared session state via output_key.
"""

from google.adk.agents import LlmAgent

from tools.market_tools import get_stock_data, get_technical_indicators
from tools.fundamental_tools import get_fundamentals, get_balance_sheet, get_income_statement
from tools.news_tools import get_news, get_global_news


def create_market_analyst(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Market Analyst agent.

    This agent analyzes technical market data (price action, indicators)
    and writes its report to state['market_report'].
    """
    return LlmAgent(
        name="MarketAnalyst",
        model=model,
        instruction="""You are a Market Analyst specializing in technical analysis.

Your job is to analyze stock price data and technical indicators for the company
specified in {company} as of {trade_date}.

Steps:
1. Use get_stock_data to retrieve recent price data (look back ~30 trading days).
2. Use get_technical_indicators to calculate key indicators (pick up to 8 from:
   rsi, macd, close_50_sma, close_200_sma, close_10_ema, atr, boll_ub, boll_lb, vwma).
3. Write a detailed market analysis report covering:
   - Price trends and patterns
   - Key support/resistance levels
   - Momentum and volatility signals
   - Volume analysis
   - A summary table of key findings

Be specific and actionable. Reference actual numbers from the data.""",
        tools=[get_stock_data, get_technical_indicators],
        output_key="market_report",
    )


def create_fundamentals_analyst(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Fundamentals Analyst agent.

    Analyzes company financials and writes to state['fundamentals_report'].
    """
    return LlmAgent(
        name="FundamentalsAnalyst",
        model=model,
        instruction="""You are a Fundamentals Analyst specializing in company financial analysis.

Your job is to analyze the fundamental data for {company} as of {trade_date}.

Steps:
1. Use get_fundamentals to retrieve key company metrics and ratios.
2. Use get_balance_sheet to examine the company's financial position.
3. Use get_income_statement to analyze revenue and profitability.
4. Write a comprehensive fundamentals report covering:
   - Company overview (sector, industry, market cap)
   - Valuation metrics (PE, PB, EV/Revenue)
   - Profitability (margins, ROE, ROA)
   - Financial health (debt ratios, current ratio)
   - Growth trajectory
   - A summary table of key findings

Provide specific, actionable insights backed by the data.""",
        tools=[get_fundamentals, get_balance_sheet, get_income_statement],
        output_key="fundamentals_report",
    )


def create_news_analyst(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the News Analyst agent.

    Analyzes recent news and writes to state['news_report'].
    """
    return LlmAgent(
        name="NewsAnalyst",
        model=model,
        instruction="""You are a News Analyst specializing in market-moving events and sentiment.

Your job is to analyze recent news for {company} as of {trade_date}.

Steps:
1. Use get_news to retrieve company-specific news (look back ~7 days).
2. Use get_global_news to get broader market/macro context.
3. Write a comprehensive news analysis report covering:
   - Key company-specific news and their market implications
   - Broader market and macroeconomic context
   - Sentiment assessment (positive/negative/neutral)
   - Potential catalysts or risks from current events
   - A summary table of key findings

Be objective and identify both opportunities and risks.""",
        tools=[get_news, get_global_news],
        output_key="news_report",
    )
