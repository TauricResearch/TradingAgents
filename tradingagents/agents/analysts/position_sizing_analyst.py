import json
import re
from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_sizing_fundamentals,
    get_sizing_indicator,
    get_sizing_price_history,
)


def _extract_position_sizing_payload(report: str) -> dict:
    if not report:
        return {}

    for match in re.finditer(
        r"```(?:\s*([A-Za-z]+))?\s*(\{.*?\})\s*```",
        report,
        re.DOTALL,
    ):
        label = (match.group(1) or "").strip().lower()
        if label and label != "json":
            continue
        try:
            payload = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    decoder = json.JSONDecoder()
    for brace_match in re.finditer(r"\{", report):
        candidate = report[brace_match.start() :].lstrip()
        try:
            payload, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    return {}


def _build_position_sizing_data(ticker: str, analysis_date: str, report: str) -> dict:
    payload = _extract_position_sizing_payload(report)

    conviction = payload.get("conviction", "")
    target_weight_pct = payload.get("target_weight_pct")
    initial_weight_pct = payload.get("initial_weight_pct")
    max_loss_pct = payload.get("max_loss_pct")
    sizing_rationale = payload.get("sizing_rationale", "")

    if not isinstance(conviction, str):
        conviction = ""
    if not isinstance(target_weight_pct, (int, float)):
        target_weight_pct = None
    if not isinstance(initial_weight_pct, (int, float)):
        initial_weight_pct = None
    if not isinstance(max_loss_pct, (int, float)):
        max_loss_pct = None
    if not isinstance(sizing_rationale, str):
        sizing_rationale = ""

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "conviction": conviction,
        "target_weight_pct": target_weight_pct,
        "initial_weight_pct": initial_weight_pct,
        "max_loss_pct": max_loss_pct,
        "sizing_rationale": sizing_rationale,
    }


def create_position_sizing_analyst(llm):
    def position_sizing_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        current_dt = datetime.strptime(current_date, "%Y-%m-%d")
        start_date = (current_dt - timedelta(days=60)).strftime("%Y-%m-%d")

        tools = [
            get_sizing_fundamentals,
            get_sizing_indicator,
            get_sizing_price_history,
        ]

        system_message = (
            "You are a position sizing analyst focused on translating conviction into a disciplined "
            "trade size. Use `get_sizing_fundamentals` to anchor thesis quality, "
            "`get_sizing_indicator` to retrieve ATR or other volatility context for stop placement, "
            "and `get_sizing_price_history` to inspect recent price behavior over the last 60 days. "
            "Deliver a concise Markdown narrative with target size, starter size, max loss budget, "
            "and the core rationale behind the sizing plan. Your response must contain two parts: "
            "(1) a Markdown summary, followed by "
            "(2) a fenced JSON block (```json ... ```) with exactly these top-level keys: "
            "`conviction` (string), `target_weight_pct` (number), `initial_weight_pct` (number), "
            "`max_loss_pct` (number), and `sizing_rationale` (string). If data is unavailable, "
            "still include all keys using empty strings or nulls. "
            f"Use `{start_date}` as the default start date when requesting recent stock data unless the "
            "conversation requires a different window."
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
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join(tool.name for tool in tools))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        tool_calls = getattr(result, "tool_calls", None) or []
        report = result.content if len(tool_calls) == 0 else ""

        return {
            "messages": [result],
            "position_sizing_report": report,
            "position_sizing_data": _build_position_sizing_data(
                ticker,
                current_date,
                report,
            ),
        }

    return position_sizing_analyst_node
