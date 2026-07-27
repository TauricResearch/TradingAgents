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
    return any(r.strip() for r in responses)


def _build_conservative_prompt(
    *,
    trader_decision: str,
    instrument_context: str,
    market_research_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_report: str,
    history: str,
    aggressive_response: str,
    neutral_response: str,
    language_instruction: str,
) -> str:
    has_opponents = _has_any_opposing_response(aggressive_response, neutral_response)

    if not has_opponents:
        task_intro = f"""Your task is to deliver the opening conservative-risk argument. Prioritize stability, security, and risk mitigation, carefully assessing potential losses and market volatility. Draw from the available data to build your case.
"""
        history_section = ""
        opponent_section = ""
    else:
        task_intro = f"""Your task is to protect assets, minimize volatility, and counter the arguments of the Aggressive and Neutral Analysts. Point out where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, building a convincing case for a low-risk approach.
"""
        history_section = f"Conversation history:\n{history}\n"
        opponent_lines = []
        if aggressive_response.strip():
            opponent_lines.append(f"Last aggressive analyst argument:\n{aggressive_response}")
        if neutral_response.strip():
            opponent_lines.append(f"Last neutral analyst argument:\n{neutral_response}")
        opponent_section = "\n".join(opponent_lines) + "\n"

    return f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth in a direct three-way debate with the Aggressive and Neutral Analysts.

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
Ground your argument in the data above. Question the optimism of other views and emphasize potential downsides they may have overlooked. Address each counterpoint to showcase why a conservative stance is the safest path.

Single speaker: Write only as the Conservative Analyst. Do not fabricate dialogue for any other participant, and do not address a moderator — this is a direct three-way exchange.
No self-label: Do not prepend a speaker label such as "Conservative Analyst:" — your role is already known from context.
Output conversationally as if you are speaking without any special formatting.
""" + language_instruction


def create_conservative_debator(llm):
    structured_llm = bind_risk_debator_output(llm, "conservative")

    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        prompt = _build_conservative_prompt(
            trader_decision=trader_decision,
            instrument_context=instrument_context,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            aggressive_response=current_aggressive_response,
            neutral_response=current_neutral_response,
            language_instruction=get_language_instruction(),
        )

        response_text, signal = invoke_risk_debator_output(
            structured_llm,
            llm,
            prompt + public_signal_instruction("conservative"),
            "conservative",
        )

        labelled = f"Conservative Analyst: {response_text}"

        new_risk_debate_state = {
            "history": history + "\n" + labelled,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + response_text,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": response_text,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "risk_signals": replace_risk_signal(
                risk_debate_state.get("risk_signals"), signal
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
