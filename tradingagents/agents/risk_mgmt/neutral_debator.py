from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


NEUTRAL_RISK_SYSTEM_PROMPT = """As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.

Your task is to challenge both aggressive and conservative analysts, pointing out where each perspective may be overly optimistic or overly cautious. Incorporate insights from the sources provided in the next message. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically and advocating for a moderate risk strategy when warranted. Output conversationally as if you are speaking without special formatting."""


def build_neutral_risk_user_prompt(state: dict) -> str:
    risk = state["risk_debate_state"]
    return stable_join_sections(
        [
            ("Trader Decision", state.get("trader_investment_plan", "")),
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
                "Latest World Affairs Report",
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
                "Risk Debate History",
                budgeted_dynamic_text(
                    risk.get("history", ""),
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "risk debate history",
                ),
            ),
            ("Last Aggressive Argument", risk.get("current_aggressive_response", "")),
            ("Last Conservative Argument", risk.get("current_conservative_response", "")),
            ("Current Task", "Deliver the neutral risk argument."),
        ]
    )


def create_neutral_debator(llm, persona=None):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        system_prompt = apply_fragment(
            NEUTRAL_RISK_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_neutral_risk_user_prompt(state)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
