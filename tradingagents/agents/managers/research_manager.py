from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_investment_debate_summary,
)


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        debate_summary = get_investment_debate_summary(state)
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        macro_regime_report = state.get("macro_regime_report", "")
        research_packet = build_research_packet(state)

        investment_debate_state = state["investment_debate_state"]

        macro_section = f"\n\nMacro Regime:\n{macro_regime_report}" if macro_regime_report else ""
        curr_situation = f"{research_packet}{macro_section}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        macro_context = f"\n\nCurrent Macro Regime:\n{macro_regime_report}\nWeight your decision in line with this macro environment — a risk-off regime raises the bar for BUY decisions, while risk-on supports them.\n" if macro_regime_report else ""

        prompt = f"""As the Research Manager and debate facilitator, critically evaluate this round of debate and make a definitive decision: Buy, Sell, or Hold.
{macro_context}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis. NO conversational filler or narrative.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives.
- Weight HIGH-confidence claims from the debate over MED/LOW claims.
- Do NOT default to Hold simply because both sides have valid points. Commit to a stance grounded in the debate's strongest evidence.

YOUR TASK:
1. **Strongest Bull Evidence**: List the top 3 data-backed bull arguments with confidence tags.
2. **Strongest Bear Evidence**: List the top 3 data-backed bear arguments with confidence tags.
3. **Recommendation**: Buy, Sell, or Hold — decisive, grounded in the highest-confidence evidence.
4. **Rationale**: Why the winning evidence outweighs the opposing side.
5. **Strategic Actions**: Concrete implementation steps for the trader.

Take into account past mistakes on similar situations:
\"{past_memory_str}\"

{instrument_context}

Compressed research packet:
{research_packet}

Rolling debate summary:
{debate_summary}

Here is the debate:
Debate History:
{history}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
