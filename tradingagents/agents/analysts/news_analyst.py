from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news, normalize_agent_output
from tradingagents.dataflows.config import get_config
from tradingagents.utils.logger import app_logger as logger



from tradingagents.utils.anonymizer import TickerAnonymizer

# Initialize anonymizer
anonymizer = TickerAnonymizer()

def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        real_ticker = state["company_of_interest"]
        
        # BLINDFIRE PROTOCOL: Anonymize Ticker
        ticker = anonymizer.anonymize_ticker(real_ticker)
        # Note: company name registration happens in market_analyst primarily, 
        # but we can do it here too if not already set, or just use ticker mapping.
        # Since state doesn't always have full company name guaranteed in all flows,
        # we rely on market_analyst or previous steps, or just ticker hashing here.


        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + """
### STRICT COMPLIANCE & PROVENANCE PROTOCOL (NON-NEGOTIABLE)

1. CITATION RULE:
   - Every numeric claim MUST have a source tag: `(Source: [Tool Name] > [Vendor] @ [YYYY-MM-DD])`.
   - Example: "Revenue grew 15% (Source: get_fundamentals > alpha_vantage @ 2026-01-14)."
   - If a number cannot be sourced to a specific tool execution, DO NOT USE IT.

2. UNIT NORMALIZATION:
   - You MUST normalize all currency to USD.
   - You MUST state "Currency converted from [Original] to USD" if applicable.

3. FAILURE HANDLING:
   - If a tool fails (e.g., Rate Limit), you MUST log: "MISSING DATA: [Tool Name] failed."
   - DO NOT hallucinate data to fill the gap.
   - If critical data (Price, Revenue) is missing, output: "INSUFFICIENT DATA TO RATE."

4. "FINAL PROPOSAL" GATING CHECKLIST:
   - You may ONLY emit "FINAL TRANSACTION PROPOSAL" if:
     [ ] Price data is < 24 hours old.
     [ ] At least 3 distinct data sources were queried.
     [ ] No "Compliance Flags" (Insider Trading suspicions) were triggered.
     [ ] Confidence Score is > 70/100.
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
                    "For your reference, the current date is {current_date}. We are looking at the company {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        logger.info(f"News Analyst Prompt: {prompt}")
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": normalize_agent_output(report),
        }

    return news_analyst_node
