from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, normalize_agent_output
from tradingagents.dataflows.config import get_config
from tradingagents.utils.logger import app_logger as logger



from tradingagents.utils.anonymizer import TickerAnonymizer

# Initialize anonymizer
anonymizer = TickerAnonymizer()

def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        real_ticker = state["company_of_interest"]
        # BLINDFIRE PROTOCOL: Anonymize Ticker
        ticker = anonymizer.anonymize_ticker(real_ticker)

        tools = [
            get_news,
        ]

        system_message = (
            "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
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
""",
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
                    "For your reference, the current date is {current_date}. The current company we want to analyze is {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        logger.info(f"Social Media Analyst Prompt: {prompt}")
        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": normalize_agent_output(report),
        }

    return social_media_analyst_node
