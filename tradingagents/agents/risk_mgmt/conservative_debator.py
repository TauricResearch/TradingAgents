from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


CONSERVATIVE_RISK_SYSTEM_PROMPT = """As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility.

Your task is to actively counter the arguments of the aggressive and neutral analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Incorporate insights from the sources provided in the next message. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning optimism and emphasizing potential downsides that may have been overlooked. Output conversationally as if you are speaking without special formatting."""


def build_conservative_risk_user_prompt(state: dict) -> str:
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
            ("Last Neutral Argument", risk.get("current_neutral_response", "")),
            ("Current Task", "Deliver the conservative risk argument."),
        ]
    )


def create_conservative_debator(llm, persona=None):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        system_prompt = apply_fragment(
            CONSERVATIVE_RISK_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_conservative_risk_user_prompt(state)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
