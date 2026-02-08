from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators, execute_text_tool_calls, needs_followup_call, execute_default_tools, generate_analysis_from_data
from tradingagents.dataflows.config import get_config

from tradingagents.log_utils import add_log, step_timer, symbol_progress

# Verbosity format appended to analyst prompts
ANALYST_RESPONSE_FORMAT = """

RESPONSE FORMAT RULES:
- Keep your analysis concise: maximum 3000 characters total
- Use a compact markdown table to organize key findings
- Do NOT repeat raw data values verbatim — summarize trends and insights
- Complete your ENTIRE analysis in a SINGLE response — do not split across multiple messages"""


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
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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
