from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.fusion_prompt import (
    FusionPromptConfig,
    render_fusion_prompt_parts,
)
from tradingagents.dataflows.config import get_config


def create_bull_researcher(llm):
    cfg = get_config() or {}
    fusion_cfg = FusionPromptConfig(
        compress_threshold=float(cfg.get("signal_fusion_compress_threshold", 0.10)),
        compress_to_sentences=int(cfg.get("signal_fusion_compress_to_sentences", 3)),
    )

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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

        # The fusion preamble is empty when SignalFusion did not run
        # (legacy serial graph or signal_fusion_enabled=False), so the
        # prompt below degrades cleanly to the v0.2.5 shape.
        fusion_section = (
            f"{parts.fusion_preamble}\n\n---\n\n" if parts.fusion_preamble else ""
        )

        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

{fusion_section}Resources available:
Market research report: {parts.market_block}
Social media sentiment report: {parts.sentiment_block}
Latest world affairs news: {parts.news_block}
Company fundamentals report: {parts.fundamentals_block}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()

        response = llm.invoke(prompt)

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
