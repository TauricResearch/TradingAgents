import functools
import time
import json
from tradingagents.agents.utils.schemas import TraderOutput


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        
        # Build Context (Summarized for Brevity in Code, assuming full text is passed)
        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        market_regime = state.get("market_regime", "UNKNOWN")
        volatility_score = state.get("volatility_score", "UNKNOWN")

        system_msg = f"""You are the Portfolio Manager. You have final authority to PROPOSE a trade.
The Execution Gatekeeper will validate your proposal against strict risk rules.

CURRENT MARKET REGIME: {market_regime}
VOLATILITY SCORE: {volatility_score}

CRITICAL MENTAL MODELS FOR HYPERSCALE TECH ANALYSIS:
1. CAPEX IS DEFENSE, NOT WASTE (Moat-widening vs Decay).
2. INVENTORY LOGIC DOES NOT APPLY to IP/Service monopolies.
3. VALUATION PEERS: Benchmark against Monopoly Durability, not S&P 500 avg.
4. REGULATORY OVERHANG: Chronic Condition (size risk), not Terminal Disease (panic).

DECISION LOGIC:
1. IF Regime == 'VOLATILE' OR 'TRENDING_DOWN':
   - FALLING KNIFE: High probability action is HOLD or SELL.
   - Only BUY if RSI < 30 AND Regime is reversing.
2. IF Regime == 'TRENDING_UP':
   - MOMENTUM: Prioritize Bullish signals. Buy dips.
3. IF Regime == 'SIDEWAYS':
   - Buy Support, Sell Resistance.

FINAL OUTPUT FORMAT (STRICT JSON):
You must end your response with a JSON block exactly like this:
```json
{{
  "action": "BUY", 
  "confidence": 0.85, 
  "rationale": "Strong trend + undervaluation"
}}
```
Possible actions: BUY, SELL, HOLD. Confidence must be 0.0 to 1.0. 
Do not forget to utilize lessons from past decisions: {past_memory_str}
"""

        context_msg = f"Based on analysis for {company_name}, propose your final decision.\nPlan: {investment_plan}\n"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": context_msg}
        ]

        # Call structured LLM
        # trader.py
        structured_llm = llm.with_structured_output(TraderOutput)
        
        result = structured_llm.invoke(messages)
        content = result.rationale
        
        trader_decision = {
            "action": result.action.upper(),
            "confidence": result.confidence,
            "rationale": result.rationale
        }

        return {
            "messages": [AIMessage(content=json.dumps(trader_decision))], # Storing JSON for audit
            "trader_investment_plan": content,
            "trader_decision": trader_decision,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
