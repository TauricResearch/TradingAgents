from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)
from tradingagents.agents.schemas import DebateTurn
from tradingagents.agents.structured import bind_structured
from tradingagents.agents.utils.debate_skel import (
    build_debate_instructions,
    invoke_debate_turn,
    render_debate_turn,
)
from tradingagents.dataflows.config import get_config


def create_bear_researcher(llm):
    structured_llm = bind_structured(llm, DebateTurn, "Bear Analyst")

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        # Keep this import local to avoid the graph-package import cycle.
        from tradingagents.graph.context_budget import compact_from_config

        config = get_config()
        bounded = compact_from_config(history, config)
        injected_history = bounded.text

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""),
            "bull analyst",
        )
        market_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(
            state["fundamentals_report"], "fundamentals"
        )
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        current_round = investment_debate_state["count"] // 2 + 1
        is_final_turn = current_round >= config["max_debate_rounds"]
        debate_instructions = build_debate_instructions(
            "bear",
            is_final_turn=is_final_turn,
        )

        prompt = f"""You are a Bear Analyst evaluating risks in the {target_label}.
Build an evidence-based bearish case. Consider risks, competitive weaknesses,
negative indicators, and weaknesses in the bull analyst's reasoning.
Revise your view when the evidence warrants it.

Resources available:
{instrument_context}
Market research report: {market_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}

Conversation history of the debate: {injected_history}
Last bull argument: {current_response}

{debate_instructions}
""" + get_language_instruction()

        turn = invoke_debate_turn(llm, structured_llm, prompt)
        rendered = render_debate_turn(
            turn,
            is_final_turn=is_final_turn,
        )
        argument = f"Bear Analyst: {rendered}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "debate_context_stats": bounded.metrics(),
        }

    return bear_node
