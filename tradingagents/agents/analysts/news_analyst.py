from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news, get_earnings_calendar, execute_text_tool_calls, needs_followup_call, execute_default_tools, generate_analysis_from_data
from tradingagents.dataflows.config import get_config

from tradingagents.log_utils import add_log, step_timer, symbol_progress

ANALYST_RESPONSE_FORMAT = """

RESPONSE FORMAT (follow this structure exactly):

## EXECUTIVE SUMMARY
2-3 sentences: Key news finding and directional bias (BULLISH / BEARISH / NEUTRAL).

## KEY DATA POINTS
- Bullet list of the 5 most significant news items with specific details
- Include company-specific news, macro factors, upcoming catalysts

## SIGNAL ASSESSMENT
Your overall reading: BULLISH / BEARISH / NEUTRAL
1-2 sentences explaining why, referencing specific news events.

## RISK FACTORS
2-3 specific risks from the news landscape.

## CONFIDENCE: HIGH / MEDIUM / LOW
1 sentence justifying your confidence level.

| News Item | Impact | Direction | Timing |
|-----------|--------|-----------|--------|
| (fill with key news events and their expected impact) |

RULES:
- Maximum 3000 characters total
- Do NOT repeat raw data verbatim — summarize trends and insights
- Complete your ENTIRE analysis in a SINGLE response"""


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_news,
            get_global_news,
            get_earnings_calendar,
        ]

        system_message = (
            "You are a news and macro analyst tasked with analyzing recent news, global trends, and upcoming catalysts. "
            "Use ALL available tools:\n"
            "- `get_news(ticker, start_date, end_date)`: Company-specific news from Google News\n"
            "- `get_global_news(curr_date, look_back_days, limit)`: Broader macroeconomic and market news\n"
            "- `get_earnings_calendar(ticker, curr_date)`: Upcoming earnings dates, ex-dividend dates, and dividend info\n\n"
            "Focus on: (1) company-specific catalysts, (2) macro headwinds/tailwinds, (3) upcoming events that could move the stock. "
            "Quantify impact where possible. Do not simply state trends are mixed — provide specific, actionable insights."
            + ANALYST_RESPONSE_FORMAT
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

        chain = prompt | llm.bind_tools(tools)

        step_timer.start_step("news_analyst")
        add_log("agent", "news_analyst", f"📰 News Analyst calling LLM for {ticker}...")
        t0 = time.time()
        result = chain.invoke(state["messages"])
        elapsed = time.time() - t0

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content
            add_log("llm", "news_analyst", f"LLM responded in {elapsed:.1f}s ({len(report)} chars)")
            tool_results = execute_text_tool_calls(report, tools)
            if tool_results:
                add_log("data", "news_analyst", f"Executed {len(tool_results)} tool calls: {', '.join(t['name'] for t in tool_results)}")
            else:
                add_log("agent", "news_analyst", f"🔄 No tool calls found, proactively fetching data for {ticker}...")
                tool_results = execute_default_tools(tools, ticker, current_date)
                add_log("data", "news_analyst", f"Proactively fetched {len(tool_results)} data sources")

            if tool_results and needs_followup_call(report):
                add_log("agent", "news_analyst", f"🔄 Generating analysis from {len(tool_results)} tool results...")
                t1 = time.time()
                followup = generate_analysis_from_data(llm, tool_results, system_message, ticker, current_date)
                elapsed2 = time.time() - t1
                if followup and len(followup) > 100:
                    report = followup
                    add_log("llm", "news_analyst", f"Follow-up analysis generated in {elapsed2:.1f}s ({len(report)} chars)")

            add_log("agent", "news_analyst", f"✅ News report ready: {report[:300]}...")
            step_timer.end_step("news_analyst", "completed", report[:200])
            symbol_progress.step_done(ticker, "news_analyst")
            step_timer.update_details("news_analyst", {
                "system_prompt": system_message[:2000],
                "user_prompt": f"Analyze news and macro trends for {ticker} on {current_date}",
                "response": report[:3000],
                "tool_calls": tool_results if tool_results else [],
            })
        else:
            tool_call_info = [{"name": tc["name"], "args": str(tc.get("args", {}))[:200]} for tc in result.tool_calls]
            step_timer.set_details("news_analyst", {
                "system_prompt": system_message[:2000],
                "user_prompt": f"Analyze news and macro trends for {ticker} on {current_date}",
                "response": "(Pending - tool calls in progress)",
                "tool_calls": tool_call_info,
            })
            add_log("data", "news_analyst", f"LLM requested {len(result.tool_calls)} tool calls in {elapsed:.1f}s: {', '.join(tc['name'] for tc in result.tool_calls)}")

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
