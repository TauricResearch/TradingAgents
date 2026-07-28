from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.evaluation.source_alignment import render_source_alignment_summary
from tradingagents.skills import (
    build_role_skill_prompt,
    build_skill_trigger_context,
    emit_methodology_artifact,
)


def _build_bull_prompt(
    *,
    target_label: str,
    instrument_context: str,
    alignment_line: str,
    market_research_report: str,
    sentiment_report: str,
    news_report: str,
    fundamentals_label: str,
    fundamentals_report: str,
    history: str,
    opposing_response: str,
    skill_prompt: str,
    language_instruction: str,
) -> str:
    """Build the bull researcher prompt, branching on opening vs rebuttal turn.

    On the opening turn (no opposing argument exists yet), the prompt asks
    for an opening case only. On subsequent turns it asks for a rebuttal and
    includes the bear's argument. The rebuttal instruction is never issued
    against an empty opposing argument, since that contradiction induces the
    model to invent the other side's dialogue so it has something to refute.
    """
    is_opening = not opposing_response.strip()

    if is_opening:
        task_section = f"""Your task is to deliver the opening bull case for investing in the {target_label}. Build a strong, evidence-based argument emphasizing growth potential, competitive advantages, and positive market indicators.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Single speaker: Write only as the Bull Analyst. Do not fabricate dialogue for any other participant, and do not address a moderator — this is a direct exchange with the bear analyst.
- No self-label: Do not prepend a speaker label such as "Bull Analyst:" — your role is already known from context."""
        history_line = ""
        opposing_line = ""
    else:
        task_section = f"""Your task is to rebut the bear analyst's latest argument and strengthen the bull case for investing in the {target_label}.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Respond directly to the bear analyst's points. Debate effectively rather than just listing data.
- Single speaker: Write only as the Bull Analyst. Do not fabricate dialogue for any other participant, and do not address a moderator — this is a direct exchange.
- No self-label: Do not prepend a speaker label such as "Bull Analyst:" — your role is already known from context."""
        history_line = f"Conversation history of the debate:\n{history}\n"
        opposing_line = f"Last bear analyst argument:\n{opposing_response}\n"

    return f"""You are the Bull Analyst in a direct debate with the Bear Analyst.
{task_section}

Resources available:
{instrument_context}
{alignment_line}Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
{history_line}{opposing_line}Use the information above to deliver your argument.
""" + language_instruction + skill_prompt


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )
        skill_trigger_text = build_skill_trigger_context(
            market_research_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            history,
            current_response,
        )
        emit_methodology_artifact("bull_researcher", trigger_text=skill_trigger_text)

        alignment_summary = render_source_alignment_summary(state.get("evidence_ledger"))
        alignment_line = (
            f"Evidence source alignment: {alignment_summary}\n"
            if alignment_summary is not None
            else ""
        )

        prompt = _build_bull_prompt(
            target_label=target_label,
            instrument_context=instrument_context,
            alignment_line=alignment_line,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_label=fundamentals_label,
            fundamentals_report=fundamentals_report,
            history=history,
            opposing_response=current_response,
            skill_prompt=build_role_skill_prompt(
                "bull_researcher", trigger_text=skill_trigger_text
            ),
            language_instruction=get_language_instruction(),
        )

        response = llm.invoke(prompt)
        raw_response = response.content

        labelled = f"Bull Analyst: {raw_response}"

        new_investment_debate_state = {
            "history": history + "\n" + labelled,
            "bull_history": bull_history + "\n" + raw_response,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": raw_response,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
