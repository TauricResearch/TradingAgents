from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


BULL_RESEARCHER_SYSTEM_PROMPT = """You are a Bull Analyst advocating for investing in the instrument. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight market opportunities, revenue or adoption prospects, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning.
- Engagement: Present your argument conversationally and engage directly with the bear analyst's points.

Use the resources provided in the next message to deliver a compelling bull argument, refute the bear's concerns, and demonstrate the strengths of the bull position."""


def build_bull_researcher_user_prompt(state: dict) -> str:
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
            ("Last Bear Argument", debate.get("current_response", "")),
            (
                "Current Task",
                "Deliver the next bull argument in the investment debate.",
            ),
        ]
    )


def create_bull_researcher(llm, persona=None):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        system_prompt = apply_fragment(
            BULL_RESEARCHER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_bull_researcher_user_prompt(state)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
