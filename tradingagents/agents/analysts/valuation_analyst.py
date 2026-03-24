import json
import re

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_states import make_default_valuation_data
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_valuation_inputs,
)


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _coerce_optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_json_payload(raw_text: str):
    text = raw_text.strip()
    if not text:
        return {}

    candidates = [text]
    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidates.extend(block.strip() for block in fenced_blocks if block.strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _parse_valuation_data(content):
    payload = _parse_json_payload(_content_to_text(content))
    valuation_data = make_default_valuation_data()

    fair_value_range = payload.get("fair_value_range")
    if isinstance(fair_value_range, dict):
        valuation_data["fair_value_range"] = {
            "low": _coerce_optional_float(fair_value_range.get("low")),
            "high": _coerce_optional_float(fair_value_range.get("high")),
        }

    valuation_data["expected_return_pct"] = _coerce_optional_float(
        payload.get("expected_return_pct")
    )
    valuation_data["primary_method"] = str(payload.get("primary_method") or "")
    valuation_data["thesis"] = str(payload.get("thesis") or "")

    return valuation_data


def create_valuation_analyst(llm):
    def valuation_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])
        tools = [get_valuation_inputs]

        system_message = (
            "You are a valuation analyst responsible for translating company "
            "fundamentals into a concise underwriting view. Use `get_valuation_inputs` "
            "to gather valuation context, estimate a fair value range, choose the "
            "primary valuation method, and explain the core thesis. Respond with valid "
            "JSON only using this exact schema: "
            '{"fair_value_range":{"low":null,"high":null},"expected_return_pct":null,'
            '"primary_method":"","thesis":""}. '
            "Use null for unknown numeric values and do not add any extra keys."
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

        payload = {"messages": [result]}
        if len(result.tool_calls) == 0:
            payload["valuation_data"] = _parse_valuation_data(result.content)

        return payload

    return valuation_analyst_node
