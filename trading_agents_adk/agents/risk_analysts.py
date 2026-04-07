"""Risk management debate agents.

Three analysts with different risk perspectives debate the trader's proposal:
- Aggressive: favors higher risk/reward
- Conservative: favors capital preservation
- Neutral: balances both perspectives
"""

from google.adk.agents import LlmAgent


def create_aggressive_analyst(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Aggressive Risk Analyst."""
    return LlmAgent(
        name="AggressiveAnalyst",
        model=model,
        instruction="""You are an Aggressive Risk Analyst. You favor higher risk/reward strategies.

Context:
- Trader's decision: {trader_decision}
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Risk debate history: {risk_debate_history}

Argue for:
1. Taking larger positions when opportunity is clear
2. Higher leverage when fundamentals support it
3. Earlier entry points to capture more upside
4. Accepting more volatility for greater returns

Counter conservative viewpoints with data. Engage conversationally.
Present your argument in 2-3 focused paragraphs.""",
        output_key="aggressive_argument",
    )


def create_conservative_analyst(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Conservative Risk Analyst."""
    return LlmAgent(
        name="ConservativeAnalyst",
        model=model,
        instruction="""You are a Conservative Risk Analyst. You prioritize capital preservation.

Context:
- Trader's decision: {trader_decision}
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Risk debate history: {risk_debate_history}

Argue for:
1. Smaller position sizes to limit downside
2. Strict stop-loss levels
3. Waiting for better entry points
4. Hedging strategies to protect capital

Counter aggressive viewpoints with data. Engage conversationally.
Present your argument in 2-3 focused paragraphs.""",
        output_key="conservative_argument",
    )


def create_neutral_analyst(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Neutral Risk Analyst."""
    return LlmAgent(
        name="NeutralAnalyst",
        model=model,
        instruction="""You are a Neutral Risk Analyst. You balance risk and reward objectively.

Context:
- Trader's decision: {trader_decision}
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Risk debate history: {risk_debate_history}

Your role:
1. Acknowledge valid points from both aggressive and conservative positions
2. Propose a balanced approach with appropriate position sizing
3. Suggest risk management guardrails that don't overly limit upside
4. Focus on risk-adjusted returns rather than absolute returns

Synthesize both perspectives constructively. Engage conversationally.
Present your argument in 2-3 focused paragraphs.""",
        output_key="neutral_argument",
    )
