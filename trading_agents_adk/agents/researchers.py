"""Research agents: Bull Researcher, Bear Researcher, and Research Manager.

These agents participate in a structured investment debate.
The Bull and Bear take turns arguing, then the Research Manager
synthesizes the debate into an investment plan.
"""

from google.adk.agents import LlmAgent


def create_bull_researcher(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Bull Researcher agent.

    Advocates for investing in the stock based on available reports.
    Reads analyst reports from state and the ongoing debate history.
    Writes its argument to state['bull_argument'].
    """
    return LlmAgent(
        name="BullResearcher",
        model=model,
        instruction="""You are a Bull Analyst advocating for investing in the stock.

Build a strong, evidence-based case emphasizing growth potential, competitive
advantages, and positive market indicators.

Available context from prior analysis:
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Previous debate history: {debate_history}
- Last bear argument: {bear_argument}

Focus on:
1. Growth Potential: Market opportunities, revenue projections, scalability
2. Competitive Advantages: Unique products, branding, market positioning
3. Positive Indicators: Financial health, industry trends, positive news
4. Counter the bear's points with specific data and reasoning

Present your argument conversationally, engaging directly with the bear's points.
Be compelling and specific.""",
        output_key="bull_argument",
    )


def create_bear_researcher(model: str = "gemini-2.5-flash") -> LlmAgent:
    """Create the Bear Researcher agent.

    Argues against investing, highlighting risks and challenges.
    Writes its argument to state['bear_argument'].
    """
    return LlmAgent(
        name="BearResearcher",
        model=model,
        instruction="""You are a Bear Analyst making the case against investing in the stock.

Present a well-reasoned argument emphasizing risks, challenges, and negative indicators.

Available context from prior analysis:
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Previous debate history: {debate_history}
- Last bull argument: {bull_argument}

Focus on:
1. Risks and Challenges: Market saturation, financial instability, macro threats
2. Competitive Weaknesses: Declining innovation, competitor threats
3. Negative Indicators: Concerning financial data, adverse news
4. Counter the bull's points with specific data and reasoning

Present your argument conversationally, engaging directly with the bull's points.
Be thorough and evidence-based.""",
        output_key="bear_argument",
    )


def create_research_manager(model: str = "gemini-2.5-pro") -> LlmAgent:
    """Create the Research Manager agent.

    Judges the bull/bear debate and creates an investment plan.
    Writes its decision to state['investment_plan'].
    """
    return LlmAgent(
        name="ResearchManager",
        model=model,
        instruction="""You are the Research Manager and debate judge.

Evaluate the bull vs. bear debate and make a definitive investment decision.
Do NOT default to Hold simply because both sides have valid points.

Context:
- Market report: {market_report}
- Fundamentals report: {fundamentals_report}
- News report: {news_report}
- Bull argument: {bull_argument}
- Bear argument: {bear_argument}
- Debate history: {debate_history}

Your output must include:
1. **Recommendation**: Buy, Sell, or Hold (be decisive)
2. **Rationale**: Why these arguments lead to your conclusion
3. **Investment Plan**: Concrete strategic actions for the trader

Commit to a stance grounded in the debate's strongest arguments.
Present naturally without special formatting.""",
        output_key="investment_plan",
    )
