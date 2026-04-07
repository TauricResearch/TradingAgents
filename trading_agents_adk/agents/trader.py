"""Trader agent that makes the trading decision.

Takes the investment plan from the Research Manager and all analyst reports
to produce a specific BUY/HOLD/SELL recommendation.
"""

from google.adk.agents import LlmAgent


def create_trader(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Trader agent.

    Receives the investment plan and all reports, then makes a trade decision.
    Writes to state['trader_decision'].
    """
    return LlmAgent(
        name="Trader",
        model=model,
        instruction="""You are a professional trading agent analyzing market data to make
investment decisions.

Based on comprehensive analysis by a team of analysts, here is the context:
- Company: {company}
- Trade date: {trade_date}
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Investment plan from Research Manager: {investment_plan}

Your job:
1. Evaluate all the evidence and the proposed investment plan
2. Consider risk/reward, timing, and market conditions
3. Provide a specific recommendation with rationale

You MUST end your response with exactly one of:
FINAL TRANSACTION PROPOSAL: **BUY**
FINAL TRANSACTION PROPOSAL: **HOLD**
FINAL TRANSACTION PROPOSAL: **SELL**

Be decisive and justify your recommendation with specific evidence.""",
        output_key="trader_decision",
    )
