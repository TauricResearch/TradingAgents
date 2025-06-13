from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json


def create_market_analyst(llm, toolkit):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        if toolkit.config["online_tools"]:
            tools = [
                toolkit.get_YFin_data_online,
                toolkit.get_stockstats_indicators_report_online,
            ]
        else:
            tools = [
                toolkit.get_YFin_data,
                toolkit.get_stockstats_indicators_report,
            ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy.
            
First, call `get_YFin_data` to retrieve the necessary stock data. Then, use `get_stockstats_indicators_report` with the selected indicators.

After analyzing the results, you must output your findings in a structured JSON format. Do not add any text outside the JSON structure.

The JSON object must contain the following keys:
1. `price_summary`: A string containing a detailed analysis of the stock's price movement (최고가, 최저가, 최근 동향 등).
2. `indicator_analysis`: An array of objects, where each object represents a technical indicator and has the following keys:
    - `indicator`: The name of the indicator (e.g., "50 SMA").
    - `value`: The calculated value of the indicator.
    - `interpretation`: A detailed interpretation of what the indicator's value means in the current market context.
3. `overall_conclusion`: A string providing a comprehensive conclusion based on the combined analysis of price trends and technical indicators.

Here is an example of the expected JSON output format:
```json
{
  "price_summary": "APP의 최근 주가는 2025년 6월 12일 기준으로 380.58 달러로 마감하였으며, 최고가는 428.99 달러(2025년 6월 5일), 최저가는 276.8 달러(2025년 5월 1일)입니다. 5월 초에 비해 급격히 상승하였으나, 최근에는 약간의 조정세를 보이고 있습니다.",
  "indicator_analysis": [
    {
      "indicator": "50 SMA",
      "value": "319.97",
      "interpretation": "중기 추세 지표로, 현재 주가가 이 지표를 상회하고 있어 상승 추세를 나타냅니다."
    },
    {
      "indicator": "MACD",
      "value": "18.33",
      "interpretation": "모멘텀 지표로, 양수 값을 유지하고 있어 상승 모멘텀을 나타냅니다."
    }
  ],
  "overall_conclusion": "APP의 주가는 현재 강한 상승세를 보이고 있으나, 단기 조정 가능성이 존재합니다. 따라서, 투자자들은 시장의 변동성을 고려하여 신중한 접근이 필요합니다."
}
```

Available indicators:
Moving Averages:
- close_50_sma: 50 SMA
- close_200_sma: 200 SMA
- close_10_ema: 10 EMA

MACD Related:
- macd: MACD
- macds: MACD Signal
- macdh: MACD Histogram

Momentum Indicators:
- rsi: RSI

Volatility Indicators:
- boll: Bollinger Middle
- boll_ub: Bollinger Upper Band
- boll_lb: Bollinger Lower Band
- atr: ATR

Volume-Based Indicators:
- vwma: VWMA

Please write all text content within the JSON in Korean.
"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "market_report": result.content,
        }

    return market_analyst_node
