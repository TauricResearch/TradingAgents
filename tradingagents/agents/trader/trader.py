import functools

from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.anonymization import anonymize_ticker


def create_trader(llm, memory):
    def trader_node(state, name):
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        scanner_context = state.get("scanner_context_packet", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        # Anonymize data variables to prevent training-data bias
        anon_investment_plan = anonymize_ticker(investment_plan, ticker)
        anon_past_memory_str = anonymize_ticker(past_memory_str, ticker)

        scanner_section = ""
        if scanner_context:
            scanner_section = (
                "\n\n## Scanner Ground-Truth Data\n"
                "The following commodity prices, FX rates, and calendar dates are verified "
                "live data. Use ONLY these values for catalyst dates, commodity references, "
                "and FX levels. Do NOT estimate or hallucinate any dates or prices.\n\n"
                f"{scanner_context}"
            )

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for the stock. {instrument_context} This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {anon_investment_plan}\n\nLeverage these insights to make an informed and strategic decision.{scanner_section}",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a trading execution specialist converting the Research Manager's recommendation into a precise transaction proposal.

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis. NO conversational filler.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives.
- Every proposal must include entry price, stop-loss (5-15% below entry), and take-profit (10-30% above entry).
- For the Catalyst Timeline, use ONLY dates from the Scanner Ground-Truth Data section. Do NOT estimate or invent earnings dates, FOMC dates, CPI dates, or any other event dates.

YOUR TASK:
1. **Research Manager's Verdict**: Restate the recommendation and top evidence.
2. **Entry Setup**: Specific entry price or range with technical justification.
3. **Risk Parameters**: Stop-loss level, take-profit target, position size rationale.
4. **Catalyst Timeline**: Key upcoming dates (earnings, ex-div, macro events) from the ground-truth calendar data ONLY.
5. **FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL****

Apply lessons from past decisions:
{anon_past_memory_str}""",
            },
            context,
        ]

        result = llm.invoke(messages)

        # De-anonymize: replace TICKER_A back with the real ticker.
        output_content = result.content.replace("TICKER_A", ticker)

        return {
            "messages": [result],
            "trader_investment_plan": output_content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
