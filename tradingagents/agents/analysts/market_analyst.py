from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            """You are a Technical Market Analyst focused on SHORT-TERM (1-2 weeks) swings. Your role is to select the **most relevant indicators** for a given market condition or trading strategy to predict the price direction for the next 5-10 days. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy.
            
            **GOAL:** Analyze price action, volume, and momentum to determine a clear LONG, SHORT, or HOLD signal for the next 2 weeks.

            Categories and each category's indicators are:
            Moving Averages: close_50_sma, close_200_sma, close_10_ema (Use to identify trend direction).
            MACD Related: macd, macds, macdh (Use to find momentum crossovers and divergence).
            Momentum Indicators: rsi (Use to flag overbought/oversold conditions).
            Volatility Indicators: boll, boll_ub, boll_lb, atr (Use to spot breakouts or mean reversion).
            Volume-Based Indicators: vwma (Use to confirm trends).

            **DECISION LOGIC:**
            - LONG: Confirmed Uptrend (Higher Highs), Bullish breakout with volume, or bounce off Key Support.
            - SHORT: Confirmed Downtrend (Lower Lows), Bearish breakdown, or rejection at Key Resistance.
            - HOLD: Choppy/Sideways market, decreasing volume, or conflicting indicators.

            Select indicators that provide diverse and complementary information. Avoid redundancy. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + "\n\nYOU MUST CONCLUDE YOUR REPORT WITH: 'SIGNAL: [LONG/SHORT/HOLD]'"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **LONG/HOLD/SHORT** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **LONG/HOLD/SHORT** so the team knows to stop."
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

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content
       
        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
