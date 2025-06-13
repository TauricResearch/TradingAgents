from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json


def create_fundamentals_analyst(llm, toolkit):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        if toolkit.config["online_tools"]:
            tools = [toolkit.get_fundamentals_openai]
        else:
            tools = [
                toolkit.get_finnhub_company_insider_sentiment,
                toolkit.get_finnhub_company_insider_transactions,
                toolkit.get_simfin_balance_sheet,
                toolkit.get_simfin_cashflow,
                toolkit.get_simfin_income_stmt,
            ]

        system_message = (
            """You are a fundamental analyst. Your task is to provide a comprehensive report on a given company by analyzing its financial documents, company profile, financial history, insider sentiment, and transactions.

You must output your findings in a structured JSON format. Do not add any text outside the JSON structure.

The JSON object must contain the following keys:
1. `company_overview`: A string with a summary of the company's business and market position.
2. `financial_performance`: An array of objects, each with `metric` and `value` keys (e.g., {"metric": "Earnings Per Share (EPS)", "value": "Increased by 354%"}).
3. `stock_market_info`: An array of objects, each with `metric` and `value` keys (e.g., {"metric": "Current Stock Price", "value": "$380.58"}).
4. `analyst_forecasts`: An array of objects, each with `metric` and `value` keys (e.g., {"metric": "Median Price Target", "value": "$538.00"}).
5. `insider_sentiment`: A string summarizing insider trading activity and sentiment.
6. `summary`: A string providing a final, overall conclusion based on all the fundamental data.

Here is an example of the expected JSON output format:
```json
{
  "company_overview": "Applovin Corporation (APP)은 모바일 앱 개발 및 수익화에 특화된 기술 회사입니다. 지난 한 해 동안 괄목할 만한 재무 성과를 보여주며 시장에서 강력한 입지를 나타냈습니다.",
  "financial_performance": [
    {"metric": "주당 순이익 (EPS)", "value": "지난 1년간 354% 증가"},
    {"metric": "매출 성장률", "value": "전년 대비 43.44% 성장"}
  ],
  "stock_market_info": [
    {"metric": "현재 주가", "value": "$380.58"},
    {"metric": "전일 대비 변동", "value": "-0.74% 감소"}
  ],
  "analyst_forecasts": [
    {"metric": "중간 목표 주가", "value": "$538.00 (현재가 대비 약 75.4% 상승 가능성)"}
  ],
  "insider_sentiment": "제공된 데이터에서는 구체적인 내부자 거래 내역이 자세히 설명되지 않았지만, 임원 및 이사회 구성원의 신뢰도에 대한 통찰력을 제공할 수 있습니다.",
  "summary": "전반적인 재무 건전성은 긍정적이나, 주가 변동성을 고려할 때 신중한 접근이 필요합니다."
}
```

Please ensure all text content within the JSON is written in Korean.
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
            "fundamentals_report": result.content,
        }

    return fundamentals_analyst_node
