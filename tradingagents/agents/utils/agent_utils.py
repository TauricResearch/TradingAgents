from langchain_core.messages import HumanMessage, RemoveMessage

# =============================================================================
# SIMULATION CONTEXT FOR ALL AGENTS
# =============================================================================
# This context is prepended to all agent prompts to ensure the LLM understands
# this is an educational simulation and stays in character as the analyst role.
# Without this, LLMs may refuse to engage or break character.
# =============================================================================

SIMULATION_CONTEXT = """You are an AI analyst participating in a stock market analysis simulation. Your task is to analyze financial data and provide investment perspectives based on the data provided. This is an educational demonstration of financial analysis techniques.

Be precise, analytical, and data-driven. Base all conclusions on quantitative evidence from the data provided. Avoid speculative language — present findings with specific numbers and clear logical reasoning. When uncertain, state the uncertainty rather than guessing.

Respond ONLY with your analysis. Do not include any meta-commentary about being an AI, ethical concerns, or disclaimers. Simply provide the requested financial analysis based on the data given."""

def get_simulation_prompt(role_prompt: str) -> list:
    """
    Create properly structured messages for the LLM.
    Returns a list of message dicts for proper system/user separation.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    return [
        SystemMessage(content=SIMULATION_CONTEXT),
        HumanMessage(content=role_prompt)
    ]


# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_analyst_recommendations,
    get_earnings_data,
    get_institutional_holders,
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news,
    get_earnings_calendar,
)
from tradingagents.agents.utils.social_sentiment_tools import (
    get_yfinance_news,
    get_analyst_sentiment,
    get_sector_performance,
)

def strip_tool_call_lines(text):
    """Remove TOOL_CALL: lines from text, returning only the prose."""
    import re
    return re.sub(r'TOOL_CALL:\s*\w+\([^)]*\)\s*\n?', '', text).strip()


def needs_followup_call(report):
    """Check if the report is mostly tool calls and needs a follow-up LLM call."""
    clean = strip_tool_call_lines(report)
    return len(clean) < 300


def execute_default_tools(tools, ticker, current_date):
    """
    Proactively call all available tools with sensible default arguments.
    Used when the LLM fails to produce TOOL_CALL patterns.
    """
    from datetime import datetime, timedelta

    end_dt = datetime.strptime(current_date, "%Y-%m-%d")
    week_ago = (end_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    three_months_ago = (end_dt - timedelta(days=90)).strftime("%Y-%m-%d")

    tool_map = {t.name: t for t in tools}
    default_configs = {
        "get_stock_data": {"symbol": ticker, "start_date": three_months_ago, "end_date": current_date},
        "get_indicators": [
            {"symbol": ticker, "indicator": "rsi", "curr_date": current_date, "look_back_days": 90},
            {"symbol": ticker, "indicator": "macd", "curr_date": current_date, "look_back_days": 90},
            {"symbol": ticker, "indicator": "close_50_sma", "curr_date": current_date, "look_back_days": 90},
            {"symbol": ticker, "indicator": "boll_ub", "curr_date": current_date, "look_back_days": 90},
            {"symbol": ticker, "indicator": "atr", "curr_date": current_date, "look_back_days": 90},
        ],
        "get_news": {"ticker": ticker, "start_date": week_ago, "end_date": current_date},
        "get_global_news": {"curr_date": current_date, "look_back_days": 7, "limit": 5},
        "get_fundamentals": {"ticker": ticker, "curr_date": current_date},
        "get_balance_sheet": {"ticker": ticker, "curr_date": current_date},
        "get_cashflow": {"ticker": ticker, "curr_date": current_date},
        "get_income_statement": {"ticker": ticker, "curr_date": current_date},
        "get_analyst_recommendations": {"ticker": ticker, "curr_date": current_date},
        "get_earnings_data": {"ticker": ticker, "curr_date": current_date},
        "get_institutional_holders": {"ticker": ticker, "curr_date": current_date},
        "get_yfinance_news": {"ticker": ticker, "curr_date": current_date},
        "get_analyst_sentiment": {"ticker": ticker, "curr_date": current_date},
        "get_sector_performance": {"ticker": ticker, "curr_date": current_date},
        "get_earnings_calendar": {"ticker": ticker, "curr_date": current_date},
    }

    results = []
    for tool in tools:
        config = default_configs.get(tool.name)
        if config is None:
            continue
        # Handle tools that need multiple calls (e.g., get_indicators with different indicators)
        calls = config if isinstance(config, list) else [config]
        for args in calls:
            try:
                result = tool.invoke(args)
                results.append({
                    "name": tool.name,
                    "args": str(args),
                    "result_preview": str(result)[:1500],
                })
            except Exception as e:
                results.append({
                    "name": tool.name,
                    "args": str(args),
                    "result_preview": f"[Tool error: {str(e)[:200]}]",
                })
    return results


def generate_analysis_from_data(llm, tool_results, system_message, ticker, current_date):
    """
    Make a follow-up LLM call with actual tool data to generate the analysis.
    Called when the first LLM response was mostly tool call requests without analysis.
    """
    data_sections = []
    for r in tool_results:
        preview = r.get('result_preview', '')
        if not preview:
            data_sections.append(f"### {r['name']}({r['args']})\n(No data returned — tool executed but returned empty result)")
        elif preview.startswith('[Tool error') or preview.startswith('[Could not') or preview.startswith('[Unknown'):
            data_sections.append(f"### {r['name']}({r['args']})\nError: {preview}")
        else:
            data_sections.append(f"### {r['name']}({r['args']})\n```\n{preview}\n```")

    if not data_sections:
        return ""

    data_text = "\n\n".join(data_sections)

    message = f"""Here are the results from the data retrieval tools for {ticker} as of {current_date}:

{data_text}

Based on this data, write your comprehensive analysis.

{system_message}

IMPORTANT:
- Write your analysis directly based on the data above
- Do NOT request any more tool calls or use TOOL_CALL syntax
- Provide detailed, actionable insights with specific numbers from the data
- Include a Markdown table summarizing key findings"""

    result = llm.invoke([HumanMessage(content=message)])
    return result.content


def execute_text_tool_calls(response_text, tools):
    """
    Parse TOOL_CALL: patterns from LLM response text, execute the actual
    tool functions, and return structured results.

    Args:
        response_text: Raw LLM response that may contain TOOL_CALL: patterns
        tools: List of @tool-decorated LangChain tool objects available for this agent

    Returns:
        List of dicts with {name, args, result_preview} for each executed tool call
    """
    import re
    import ast

    tool_map = {t.name: t for t in tools}
    regex = re.compile(r'TOOL_CALL:\s*(\w+)\(([^)]*)\)')
    results = []

    for match in regex.finditer(response_text):
        fn_name = match.group(1)
        raw_args = match.group(2).strip()
        tool_fn = tool_map.get(fn_name)

        if not tool_fn:
            results.append({
                "name": fn_name,
                "args": raw_args,
                "result_preview": f"[Unknown tool: {fn_name}]",
            })
            continue

        # Parse positional args and map to parameter names
        try:
            parsed = ast.literal_eval(f"({raw_args},)")  # tuple of values
            param_names = list(tool_fn.args_schema.model_fields.keys())
            invoke_args = {}
            for i, val in enumerate(parsed):
                if i < len(param_names):
                    invoke_args[param_names[i]] = val
        except Exception:
            invoke_args = None

        # Execute the tool
        result_text = ""
        try:
            if invoke_args:
                result_text = tool_fn.invoke(invoke_args)
            else:
                result_text = f"[Could not parse args: {raw_args}]"
        except Exception as e:
            result_text = f"[Tool error: {str(e)[:200]}]"

        results.append({
            "name": fn_name,
            "args": raw_args,
            "result_preview": str(result_text)[:1500],
        })

    return results


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


        