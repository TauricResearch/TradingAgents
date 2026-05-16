from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.fusion_prompt import (
    FusionPromptConfig,
    render_fusion_prompt_parts,
)
from tradingagents.dataflows.config import get_config


def create_bear_researcher(llm):
    cfg = get_config() or {}
    fusion_cfg = FusionPromptConfig(
        compress_threshold=float(cfg.get("signal_fusion_compress_threshold", 0.10)),
        compress_to_sentences=int(cfg.get("signal_fusion_compress_to_sentences", 3)),
    )

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")

        parts = render_fusion_prompt_parts(
            market_report=state.get("market_report", ""),
            sentiment_report=state.get("sentiment_report", ""),
            news_report=state.get("news_report", ""),
            fundamentals_report=state.get("fundamentals_report", ""),
            analyst_signals=state.get("analyst_signals") or {},
            signal_weights=state.get("signal_weights") or {},
            composite_score=state.get("composite_score", 0.0),
            disagreement_axes=state.get("disagreement_axes") or [],
            config=fusion_cfg,
        )

        fusion_section = (
            f"{parts.fusion_preamble}\n\n---\n\n" if parts.fusion_preamble else ""
        )

        prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

{fusion_section}Resources available:

Market research report: {parts.market_block}
Social media sentiment report: {parts.sentiment_block}
Latest world affairs news: {parts.news_block}
Company fundamentals report: {parts.fundamentals_block}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock.
""" + get_language_instruction()

        response = llm.invoke(prompt)

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
