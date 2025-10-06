from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_economic_indicators, get_yield_curve, get_fed_calendar
from tradingagents.dataflows.config import get_config


def create_macro_analyst(llm):
    def macro_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_economic_indicators,
            get_yield_curve,
            get_fed_calendar,
        ]

        system_message = (
            "You are a macro economic analyst tasked with analyzing Federal Reserve data, economic indicators, and macroeconomic trends. "
            "Your objective is to write a comprehensive report detailing current economic conditions, monetary policy implications, and their impact on financial markets. "
            "Analyze key indicators such as:\n"
            "- Federal Funds Rate and monetary policy trajectory\n"
            "- Inflation indicators (CPI, PPI)\n"
            "- Employment data (unemployment rate, payrolls)\n"
            "- Treasury yield curve and inversion signals\n"
            "- Economic growth indicators (GDP, PMI)\n"
            "- Market volatility (VIX)\n\n"
            "Provide detailed analysis of:\n"
            "1. Current economic cycle positioning\n"
            "2. Federal Reserve policy stance and likely direction\n"
            "3. Inflation and employment trends\n"
            "4. Yield curve implications for recession risk\n"
            "5. Market implications and trading considerations\n\n"
            "Use the available tools: `get_economic_indicators` for comprehensive economic data, "
            "`get_yield_curve` for Treasury yields and inversion analysis, and `get_fed_calendar` for FOMC schedule and policy trajectory. "
            "Make sure to provide detailed, actionable insights rather than generic summaries. "
            "Append a Markdown table at the end summarizing key macro indicators and their implications."
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
            "macro_report": report,
        }

    return macro_analyst_node
