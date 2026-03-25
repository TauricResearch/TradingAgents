import json
import re

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_segment_fundamentals,
    get_segment_income_statement,
    get_segment_news,
)


def _extract_segment_payload(report: str) -> dict:
    if not report:
        return {}

    # Prefer fenced JSON payloads (supports ```json, ```JSON, and unlabeled ```).
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

    # Fallback: tolerate raw JSON object embedded in body text.
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


def _build_segment_data(ticker: str, analysis_date: str, report: str) -> dict:
    payload = _extract_segment_payload(report)
    business_unit_decomposition = payload.get("business_unit_decomposition", [])
    segment_economics = payload.get("segment_economics", {})
    value_driver_map = payload.get("value_driver_map", [])

    if not isinstance(business_unit_decomposition, list):
        business_unit_decomposition = []
    if not isinstance(segment_economics, dict):
        segment_economics = {}
    if not isinstance(value_driver_map, list):
        value_driver_map = []

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "business_unit_decomposition": business_unit_decomposition,
        "segment_economics": segment_economics,
        "value_driver_map": value_driver_map,
    }


def create_segment_analyst(llm):
    def segment_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        tools = [
            get_segment_fundamentals,
            get_segment_income_statement,
            get_segment_news,
        ]

        system_message = (
            "You are a segment analyst focused on business-mix quality and revenue durability. "
            "Use `get_segment_fundamentals` to summarize business lines and strategic positioning, "
            "`get_segment_income_statement` to infer segment-level margin direction from reported trends, "
            "and `get_segment_news` to identify demand, pricing, and competitive catalysts for key segments. "
            "Deliver a concise segment-by-segment view, highlight concentration risks, and append a Markdown "
            "table that maps each major segment to growth outlook, margin trend, and trading implication. "
            "Your response must contain two parts: "
            "(1) a Markdown narrative summary and table, followed by "
            "(2) a fenced JSON block (```json ... ```) with exactly these top-level keys: "
            "`business_unit_decomposition` (list of objects with `segment`, `revenue_share_pct`, "
            "`growth_trend`, `strategic_role`), `segment_economics` (object summarizing margin profile, "
            "capital intensity, cyclicality), and `value_driver_map` (list of objects with `driver`, "
            "`impacted_segments`, `direction`, `horizon`, `evidence`). "
            "If data is unavailable, still include all keys using empty lists/objects."
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
            "segment_report": report,
            "segment_data": _build_segment_data(ticker, current_date, report),
        }

    return segment_analyst_node
