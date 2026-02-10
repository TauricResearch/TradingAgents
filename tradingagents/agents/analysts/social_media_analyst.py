from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_yfinance_news, get_analyst_sentiment, get_sector_performance, execute_text_tool_calls, needs_followup_call, execute_default_tools, generate_analysis_from_data
from tradingagents.dataflows.config import get_config

from tradingagents.log_utils import add_log, step_timer, symbol_progress

ANALYST_RESPONSE_FORMAT = """

RESPONSE FORMAT (follow this structure exactly):

## EXECUTIVE SUMMARY
2-3 sentences: Key sentiment finding and directional bias (BULLISH / BEARISH / NEUTRAL).

## KEY DATA POINTS
- Bullet list of the 5 most significant sentiment signals with specific numbers
- Include analyst consensus, price target implied upside, sector positioning

## SIGNAL ASSESSMENT
Your overall sentiment reading: BULLISH / BEARISH / NEUTRAL
1-2 sentences explaining why, referencing specific data.

## RISK FACTORS
2-3 specific risks or sentiment divergences.

## CONFIDENCE: HIGH / MEDIUM / LOW
1 sentence justifying your confidence level.

| Signal Source | Finding | Sentiment | Weight |
|--------------|---------|-----------|--------|
| (fill with key sentiment signals) |

RULES:
- Maximum 3000 characters total
- Do NOT repeat raw data verbatim — summarize trends and insights
- Complete your ENTIRE analysis in a SINGLE response"""


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        tools = [
            get_yfinance_news,
            get_analyst_sentiment,
            get_sector_performance,
        ]

        system_message = (
            "You are a sentiment and market perception analyst. Your job is to assess the overall market sentiment around a company "
            "by synthesizing multiple signal sources:\n"
            "- `get_yfinance_news`: Curated news from Yahoo Finance (multiple publishers) — analyze headlines, publishers, recency, and tone\n"
            "- `get_analyst_sentiment`: Wall Street consensus — price targets, buy/sell/hold distribution, implied upside/downside\n"
            "- `get_sector_performance`: Sector context — how the stock is positioned vs moving averages, 52-week range, beta, and index\n\n"
            "Synthesize these into a unified sentiment assessment. Quantify sentiment where possible (e.g., '70% of analysts rate Buy', "
            "'trading at 85% of 52-week range', 'implied upside of 15%'). Identify sentiment divergences (e.g., analysts bullish but "
            "price below moving averages). Do not simply state trends are mixed — provide specific, actionable insights."
            + ANALYST_RESPONSE_FORMAT,
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

        chain = prompt | llm.bind_tools(tools)

        step_timer.start_step("social_media_analyst")
        add_log("agent", "social_analyst", f"💬 Social Media Analyst calling LLM for {ticker}...")
        t0 = time.time()
        result = chain.invoke(state["messages"])
        elapsed = time.time() - t0

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content
            add_log("llm", "social_analyst", f"LLM responded in {elapsed:.1f}s ({len(report)} chars)")
            tool_results = execute_text_tool_calls(report, tools)
            if tool_results:
                add_log("data", "social_analyst", f"Executed {len(tool_results)} tool calls: {', '.join(t['name'] for t in tool_results)}")
            else:
                add_log("agent", "social_analyst", f"🔄 No tool calls found, proactively fetching data for {ticker}...")
                tool_results = execute_default_tools(tools, ticker, current_date)
                add_log("data", "social_analyst", f"Proactively fetched {len(tool_results)} data sources")

            if tool_results and needs_followup_call(report):
                add_log("agent", "social_analyst", f"🔄 Generating analysis from {len(tool_results)} tool results...")
                t1 = time.time()
                followup = generate_analysis_from_data(llm, tool_results, system_message, ticker, current_date)
                elapsed2 = time.time() - t1
                if followup and len(followup) > 100:
                    report = followup
                    add_log("llm", "social_analyst", f"Follow-up analysis generated in {elapsed2:.1f}s ({len(report)} chars)")

            add_log("agent", "social_analyst", f"✅ Sentiment report ready: {report[:300]}...")
            step_timer.end_step("social_media_analyst", "completed", report[:200])
            symbol_progress.step_done(ticker, "social_media_analyst")
            step_timer.update_details("social_media_analyst", {
                "system_prompt": system_message[:2000],
                "user_prompt": f"Analyze social media sentiment for {ticker} on {current_date}",
                "response": report[:3000],
                "tool_calls": tool_results if tool_results else [],
            })
        else:
            tool_call_info = [{"name": tc["name"], "args": str(tc.get("args", {}))[:200]} for tc in result.tool_calls]
            step_timer.set_details("social_media_analyst", {
                "system_prompt": system_message[:2000],
                "user_prompt": f"Analyze social media sentiment for {ticker} on {current_date}",
                "response": "(Pending - tool calls in progress)",
                "tool_calls": tool_call_info,
            })
            add_log("data", "social_analyst", f"LLM requested {len(result.tool_calls)} tool calls in {elapsed:.1f}s: {', '.join(tc['name'] for tc in result.tool_calls)}")

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
