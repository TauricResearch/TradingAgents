from tradingagents.agents.risk_mgmt.signals import (
    bind_risk_debator_output,
    invoke_risk_debator_output,
    public_signal_instruction,
    replace_risk_signal,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)


def _has_any_opposing_response(*responses: str) -> bool:
    """True if at least one other debator has already spoken."""
    return any(r.strip() for r in responses)


def _build_aggressive_prompt(
    *,
    trader_decision: str,
    instrument_context: str,
    market_research_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
    history: str,
    conservative_response: str,
    neutral_response: str,
    language_instruction: str,
) -> str:
    has_opponents = _has_any_opposing_response(conservative_response, neutral_response)

    if not has_opponents:
        task_intro = f"""Your task is to deliver the opening aggressive-risk argument. Champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. Draw from the available data to build your case.
"""
        history_section = ""
        opponent_section = ""
    else:
        task_intro = f"""Your task is to actively champion high-reward, high-risk opportunities and challenge the conservative and neutral views. Respond directly to the points made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative.
"""
        history_section = f"Conversation history:\n{history}\n"
        opponent_lines = []
        if conservative_response.strip():
            opponent_lines.append(f"Last conservative analyst argument:\n{conservative_response}")
        if neutral_response.strip():
            opponent_lines.append(f"Last neutral analyst argument:\n{neutral_response}")
        opponent_section = "\n".join(opponent_lines) + "\n"

    return f"""As the Aggressive Risk Analyst, your role is to champion high-reward, high-risk opportunities in a direct three-way debate with the Conservative and Neutral Analysts.

{task_intro}
Here is the trader's decision:
{trader_decision}

Data sources:
{instrument_context}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
{history_section}{opponent_section}
Ground your argument in the data above. Engage actively by addressing specific concerns, refuting weaknesses in opposing logic, and asserting the benefits of risk-taking to outpace market norms.

Single speaker: Write only as the Aggressive Analyst. Do not fabricate dialogue for any other participant, and do not address a moderator — this is a direct three-way exchange.
No self-label: Do not prepend a speaker label such as "Aggressive Analyst:" — your role is already known from context.
Output conversationally as if you are speaking without any special formatting.
""" + language_instruction


def create_aggressive_debator(llm):
    structured_llm = bind_risk_debator_output(llm, "aggressive")

    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        prompt = _build_aggressive_prompt(
            trader_decision=trader_decision,
            instrument_context=instrument_context,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            conservative_response=current_conservative_response,
            neutral_response=current_neutral_response,
            language_instruction=get_language_instruction(),
        )

        response_text, signal = invoke_risk_debator_output(
            structured_llm,
            llm,
            prompt + public_signal_instruction("aggressive"),
            "aggressive",
        )

        labelled = f"Aggressive Analyst: {response_text}"

        new_risk_debate_state = {
            "history": history + "\n" + labelled,
            "aggressive_history": aggressive_history + "\n" + response_text,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": response_text,
            "current_conservative_response": risk_debate_state.get(
                "current_conservative_response", ""
            ),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "risk_signals": replace_risk_signal(
                risk_debate_state.get("risk_signals"), signal
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
