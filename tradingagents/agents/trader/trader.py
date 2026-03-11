import functools
from tradingagents.agents.utils.korean_prompt import (
    KOREAN_INVESTOR_GUIDE,
    KOREAN_FINAL_DECISION_GUIDE,
    SWING_TRADING_CONTEXT,
    SWING_PORTFOLIO_CONTEXT,
)


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        market_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        screening_context = state.get("screening_context", "")
        portfolio_context = state.get("portfolio_context", "")

        # Build situation for memory lookup
        curr_situation = f"{market_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for rec in past_memories:
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "과거 유사 사례 메모리가 없습니다."

        # Build context message
        reports_section = f"""## 기술적 분석 (Market Analyst)
{market_report}

## 뉴스 분석 (News Analyst)
{news_report}

## 기본적 분석 (Fundamentals Analyst)
{fundamentals_report}"""

        screening_section = ""
        if screening_context:
            screening_section = f"\n## 스크리닝 선정 사유\n{screening_context}"

        portfolio_section = ""
        if portfolio_context:
            portfolio_section = f"\n## 현재 포트폴리오 상태\n{portfolio_context}"

        context = {
            "role": "user",
            "content": f"""{company_name}에 대한 애널리스트 분석 리포트입니다. 이를 기반으로 스윙 트레이딩 매매 결정을 내려주세요.

{reports_section}{screening_section}{portfolio_section}""",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a swing trading agent. You receive analyst reports and make direct BUY/SELL/PASS decisions for swing trades (2-20 day holding period).

Your options:
- **BUY**: Enter a new long position now.
- **SELL**: Exit an existing position (only if portfolio context shows an open position).
- **PASS**: Skip this trade.

Decision framework:
1. Technical setup (Market Analyst) — Is the chart showing a favorable entry/exit?
2. News check (News Analyst) — Any catalysts or red flags?
3. Fundamentals sanity check — Is the company fundamentally sound?
4. Risk management — Define stop loss, take profit, position size.

You MUST end your response with a structured order block:

```
SWING_ORDER:
  ACTION: BUY|SELL|PASS
  ENTRY_PRICE: 현재가 또는 목표 진입가
  STOP_LOSS: 손절가
  TAKE_PROFIT: 익절가
  POSITION_SIZE_PCT: 총 자본 대비 비중 (0.05~0.20)
  MAX_HOLD_DAYS: 최대 보유일 (2~20)
  RATIONALE: 한 줄 요약
```

Also conclude with: FINAL TRANSACTION PROPOSAL: **BUY/SELL/PASS**

Lessons from past similar trades:
{past_memory_str}
{KOREAN_INVESTOR_GUIDE}
{SWING_TRADING_CONTEXT}
{SWING_PORTFOLIO_CONTEXT}
{KOREAN_FINAL_DECISION_GUIDE}""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_decision": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
