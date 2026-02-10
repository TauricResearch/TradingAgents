from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators, execute_text_tool_calls, needs_followup_call, execute_default_tools, generate_analysis_from_data
from tradingagents.dataflows.config import get_config

from tradingagents.log_utils import add_log, step_timer, symbol_progress

# Structured response format for explainability
ANALYST_RESPONSE_FORMAT = """

RESPONSE FORMAT (follow this structure exactly):

## EXECUTIVE SUMMARY
2-3 sentences: Key finding and directional bias (BULLISH / BEARISH / NEUTRAL).

## KEY DATA POINTS
- Bullet list of the 5 most significant data points with specific numbers
- Each point should include the metric name, value, and what it signals

## SIGNAL ASSESSMENT
Your overall reading: BULLISH / BEARISH / NEUTRAL
1-2 sentences explaining why, referencing specific data.

## RISK FACTORS
2-3 specific risks that could invalidate your assessment.

## CONFIDENCE: HIGH / MEDIUM / LOW
1 sentence justifying your confidence level.

| Metric | Value | Signal | Significance |
|--------|-------|--------|-------------|
| (fill with key metrics from your analysis) |

RULES:
- Maximum 3000 characters total
- Do NOT repeat raw data verbatim — summarize trends and insights
- Complete your ENTIRE analysis in a SINGLE response"""


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
            """You are a market/technical analyst tasked with analyzing financial markets. Select up to **8 of the most relevant indicators** for the current market condition. Available indicators by category:

Moving Averages:
- close_5_ema: 5 EMA — ultra-responsive short-term momentum
- close_10_ema: 10 EMA — responsive short-term average
- close_20_sma: 20 SMA — short-term trend (Bollinger baseline)
- close_50_sma: 50 SMA — medium-term trend direction
- close_200_sma: 200 SMA — long-term trend benchmark, golden/death cross

MACD Related:
- macd: MACD line — momentum via EMA differences
- macds: MACD Signal — smoothed MACD for crossover triggers
- macdh: MACD Histogram — momentum strength visualization

Momentum & Oscillators:
- rsi: RSI — overbought(>70)/oversold(<30) momentum
- kdjk: Stochastic %K — momentum oscillator, overbought(>80)/oversold(<20)
- cci: CCI — price deviation from mean, overbought(>100)/oversold(<-100)

Trend Strength:
- adx: ADX — trend strength regardless of direction (>25 = strong trend, <20 = ranging)

Volatility:
- boll: Bollinger Middle (20 SMA) — dynamic price benchmark
- boll_ub: Bollinger Upper — overbought/breakout zone
- boll_lb: Bollinger Lower — oversold/support zone
- atr: ATR — volatility for stop-loss and position sizing

Volume-Based:
- vwma: VWMA — volume-weighted moving average for trend confirmation
- mfi: MFI — money flow index combining price and volume

Strategy: Call `get_stock_data` first, then `get_indicators` with specific indicator names. Select indicators that provide diverse, complementary information — avoid redundancy. Provide specific numbers and quantitative reasoning, not generic statements."""
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

        step_timer.start_step("market_analyst")
        add_log("agent", "market_analyst", f"📊 Market Analyst calling LLM for {ticker}...")
        t0 = time.time()
        result = chain.invoke(state["messages"])
        elapsed = time.time() - t0

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content
            add_log("llm", "market_analyst", f"LLM responded in {elapsed:.1f}s ({len(report)} chars)")
            # Execute any text-based tool calls and capture results
            tool_results = execute_text_tool_calls(report, tools)
            if tool_results:
                add_log("data", "market_analyst", f"Executed {len(tool_results)} tool calls: {', '.join(t['name'] for t in tool_results)}")
            else:
                # LLM didn't produce TOOL_CALL patterns — proactively fetch data
                add_log("agent", "market_analyst", f"🔄 No tool calls found, proactively fetching data for {ticker}...")
                tool_results = execute_default_tools(tools, ticker, current_date)
                add_log("data", "market_analyst", f"Proactively fetched {len(tool_results)} data sources")

            # If report is mostly tool calls / thin prose, make follow-up LLM call with actual data
            if tool_results and needs_followup_call(report):
                add_log("agent", "market_analyst", f"🔄 Generating analysis from {len(tool_results)} tool results...")
                t1 = time.time()
                followup = generate_analysis_from_data(llm, tool_results, system_message, ticker, current_date)
                elapsed2 = time.time() - t1
                if followup and len(followup) > 100:
                    report = followup
                    add_log("llm", "market_analyst", f"Follow-up analysis generated in {elapsed2:.1f}s ({len(report)} chars)")

            add_log("agent", "market_analyst", f"✅ Market report ready: {report[:300]}...")
            step_timer.end_step("market_analyst", "completed", report[:200])
            symbol_progress.step_done(ticker, "market_analyst")
            step_timer.update_details("market_analyst", {
                "system_prompt": system_message[:2000],
                "user_prompt": f"Analyze {ticker} on {current_date} using technical indicators",
                "response": report[:3000],
                "tool_calls": tool_results if tool_results else [],
            })
        else:
            tool_call_info = [{"name": tc["name"], "args": str(tc.get("args", {}))[:200]} for tc in result.tool_calls]
            step_timer.set_details("market_analyst", {
                "system_prompt": system_message[:2000],
                "user_prompt": f"Analyze {ticker} on {current_date} using technical indicators",
                "response": "(Pending - tool calls in progress)",
                "tool_calls": tool_call_info,
            })
            add_log("data", "market_analyst", f"LLM requested {len(result.tool_calls)} tool calls in {elapsed:.1f}s: {', '.join(tc['name'] for tc in result.tool_calls)}")

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
