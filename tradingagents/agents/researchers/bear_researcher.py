from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


BEAR_RESEARCHER_SYSTEM_PROMPT = """You are a Bear Analyst making the case against investing in the instrument. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:
- Risks and Challenges: Highlight market saturation, financial instability, macroeconomic threats, or other risks that could hinder performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning.
- Engagement: Present your argument conversationally and directly engage with the bull analyst's points.

Use the resources provided in the next message to deliver a compelling bear argument, refute the bull's claims, and demonstrate the risks and weaknesses of investing in the instrument."""


def build_bear_researcher_user_prompt(state: dict) -> str:
    debate = state["investment_debate_state"]
    asset_type = state.get("asset_type", "stock")
    return stable_join_sections(
        [
            (
                "Instrument Context",
                build_instrument_context(state["company_of_interest"], asset_type),
            ),
            (
                "Market Research Report",
                budgeted_dynamic_text(
                    state.get("market_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "market report",
                ),
            ),
            (
                "Social Media Sentiment Report",
                budgeted_dynamic_text(
                    state.get("sentiment_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "sentiment report",
                ),
            ),
            (
                "Latest World Affairs News",
                budgeted_dynamic_text(
                    state.get("news_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "news report",
                ),
            ),
            (
                "Fundamentals Report",
                budgeted_dynamic_text(
                    state.get("fundamentals_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "fundamentals report",
                ),
            ),
            (
                "Derivatives And Options Report",
                budgeted_dynamic_text(
                    state.get("derivatives_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "derivatives report",
                ),
            ),
            (
                "Conversation History Of The Debate",
                budgeted_dynamic_text(
                    debate.get("history", ""),
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "investment debate history",
                ),
            ),
            ("Last Bull Argument", debate.get("current_response", "")),
            (
                "Current Task",
                "Deliver the next bear argument in the investment debate.",
            ),
        ]
    )


def create_bear_researcher(llm, persona=None):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        system_prompt = apply_fragment(
            BEAR_RESEARCHER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_bear_researcher_user_prompt(state)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
