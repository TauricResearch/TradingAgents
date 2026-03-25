import json
import re

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_catalyst_calendar,
    get_scenario_fundamentals,
    get_scenario_news,
)


def _extract_scenario_catalyst_payload(report: str) -> dict:
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


def _build_scenario_catalyst_data(ticker: str, analysis_date: str, report: str) -> dict:
    payload = _extract_scenario_catalyst_payload(report)
    scenario_map = payload.get("scenario_map", [])
    dated_catalyst_map = payload.get("dated_catalyst_map", [])
    invalidation_triggers = payload.get("invalidation_triggers", [])

    if not isinstance(scenario_map, list):
        scenario_map = []
    if not isinstance(dated_catalyst_map, list):
        dated_catalyst_map = []
    if not isinstance(invalidation_triggers, list):
        invalidation_triggers = []

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "scenario_map": scenario_map,
        "dated_catalyst_map": dated_catalyst_map,
        "invalidation_triggers": invalidation_triggers,
    }


def create_scenario_catalyst_analyst(llm):
    def scenario_catalyst_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        tools = [
            get_scenario_fundamentals,
            get_scenario_news,
            get_catalyst_calendar,
        ]

        system_message = (
            "You are a scenario and catalyst analyst focused on bull/base/bear framing and "
            "timed event risk for the instrument. Use `get_scenario_fundamentals` to anchor "
            "fundamental sensitivity, `get_scenario_news` to identify company-specific drivers, "
            "and `get_catalyst_calendar` to map date-based macro/policy events. Deliver a concise "
            "Markdown narrative with bull, base, and bear case probabilities, key signposts, and "
            "thesis invalidation logic. Your response must contain two parts: "
            "(1) a Markdown summary and catalyst table, followed by "
            "(2) a fenced JSON block (```json ... ```) with exactly these top-level keys: "
            "`scenario_map` (list of objects with `name`, `probability_pct`, `thesis`, "
            "`valuation_implication`, `signposts`), `dated_catalyst_map` (list of objects with "
            "`catalyst`, `date_or_window`, `related_scenarios`, `expected_impact`, `confidence`), "
            "and `invalidation_triggers` (list of objects with `trigger`, `affected_scenarios`, "
            "`severity`, `evidence_to_watch`). If data is unavailable, still include all keys "
            "using empty lists."
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
            "scenario_catalyst_report": report,
            "scenario_catalyst_data": _build_scenario_catalyst_data(
                ticker,
                current_date,
                report,
            ),
        }

    return scenario_catalyst_analyst_node
