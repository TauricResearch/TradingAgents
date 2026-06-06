from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
from tradingagents.personas.prompt_overlay import apply_fragment


AGGRESSIVE_RISK_SYSTEM_PROMPT = """As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on potential upside, growth potential, and innovative benefits, even when these come with elevated risk.

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances. Incorporate insights from the sources provided in the next message. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing specific concerns raised, refuting weaknesses in opposing logic, and asserting the benefits of risk-taking to outpace market norms. Output conversationally as if you are speaking without special formatting."""


def build_aggressive_risk_user_prompt(state: dict) -> str:
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
            ("Last Conservative Argument", risk.get("current_conservative_response", "")),
            ("Last Neutral Argument", risk.get("current_neutral_response", "")),
            ("Current Task", "Deliver the aggressive risk argument."),
        ]
    )


def create_aggressive_debator(llm, persona=None):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        system_prompt = apply_fragment(
            AGGRESSIVE_RISK_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_aggressive_risk_user_prompt(state)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.invoke(messages)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
