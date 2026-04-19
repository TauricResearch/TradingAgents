# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import get_stock_data
from tradingagents.dataflows.technical_calculator import compute_all_indicators


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        # Layer 1: Pre-compute all technical indicators in pure code
        indicator_summary = compute_all_indicators(ticker, current_date)

        tools = [
            get_stock_data,
        ]

        system_message = (
            f"""You are a trading assistant tasked with analyzing financial markets.
Below are pre-computed technical indicators for {ticker}:

{indicator_summary}

Your task:
1. First, call get_stock_data to retrieve recent OHLCV price data for the stock.
2. Then, analyze the indicators above together with the price data to produce a detailed market analysis report.

Your report should cover:
- Trend direction and strength (moving averages, MACD crossovers)
- Momentum conditions (RSI overbought/oversold, divergences)
- Volatility assessment (Bollinger Bands width, ATR levels)
- Volume confirmation (VWMA vs price trend)
- Key support and resistance levels
- Notable patterns or divergences between indicators

Provide detailed, nuanced, and fine-grained analysis with actionable insights that may help traders make decisions. Do not simply state trends are mixed — explain the specific conditions and their implications."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
