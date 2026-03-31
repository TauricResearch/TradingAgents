from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_investment_debate_summary,
)


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
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

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(research_packet, ticker)
        anon_debate_summary = anonymize_ticker(debate_summary, ticker)
        anon_history = anonymize_ticker(history, ticker)
        anon_past_memory_str = anonymize_ticker(past_memory_str, ticker)

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
\"{anon_past_memory_str}\"

{instrument_context}

Compressed research packet:
{anon_research_packet}

Rolling debate summary:
{anon_debate_summary}

Here is the debate:
Debate History:
{anon_history}"""
        response = llm.invoke(prompt)

        # De-anonymize: replace TICKER_A back with the real ticker so downstream
        # nodes (Trader, Portfolio Manager) receive the correct symbol.
        output_content = response.content.replace("TICKER_A", ticker)

        new_investment_debate_state = {
            "judge_decision": output_content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": output_content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": output_content,
        }

    return research_manager_node
