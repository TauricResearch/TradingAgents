from typing import Any, Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.report_quality import tag_report
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    save_node_report,
)
from tradingagents.agents.utils.scanner_tools import (
    get_bitcoin_price,
    get_cny_usd_rate,
    get_eur_usd_rate,
    get_gold_price,
    get_jpy_usd_rate,
    get_oil_prices,
    get_todays_sovereign_cds,
    get_topic_news,
)
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_geopolitical_scanner(llm: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def geopolitical_scanner_node(state: dict[str, Any]) -> dict[str, Any]:
        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "geopolitical_report")
        if existing_report:
            return {
                "geopolitical_report": existing_report,
                "sender": "geopolitical_scanner",
            }

        scan_date = state["scan_date"]

        tools = [
            get_topic_news,
            get_todays_sovereign_cds,
            get_gold_price,
            get_oil_prices,
            get_bitcoin_price,
            get_eur_usd_rate,
            get_jpy_usd_rate,
            get_cny_usd_rate,
        ]

        system_message = (
            "You are a Senior Macro Strategist and Economist performing geopolitical risk assessment. "
            "Use the provided tools to identify global risks and opportunities affecting financial markets. "
            "Your objective is to produce a clinical, data-dense report on geopolitical deltas. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "Treat tool output as the ONLY source of truth. "
            "Report must include: "
            "(1) Major geopolitical events and quantified market impact, "
            "(2) Central bank policy signals (rates, liquidity, bias), "
            "(3) Trade/sanctions developments and structural friction, "
            "(4) Energy/commodity supply chain risks, "
            "(5) Asset validation: state whether Gold, Oil, Bitcoin, and Sovereign CDS confirm or contradict the news narrative. "
            "(6) FX Analysis: evaluate EUR/USD, JPY/USD, and CNY/USD trends and their geopolitical drivers. "
            "(7) Macro Predictions: Based on current data, provide specific 30-day directional predictions for "
            "Gold, Oil, and major FX pairs (EUR, JPY, CNY) with conviction levels. "
            "If CDS data is stale, state 'CDS confirmation unavailable'. "
            "Include a quantitative risk assessment table."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=scan_date)

        chain = prompt | llm.bind_tools(tools)
        initial_messages = state["messages"][:1] if state["messages"] else []
        result = run_tool_loop(
            chain,
            initial_messages,
            tools,
            require_tool_result=True,
            node_name="geopolitical_scanner",
            min_report_length=800,
            max_tool_output_chars=5000,
        )

        tool_names = ", ".join(t.name for t in tools)
        report = tag_report(
            result.content or "",
            node_name="geopolitical_scanner",
            tools_used=tool_names,
        )

        # 3. Resumability: Save after completion
        if report:
            save_node_report(state, "geopolitical_report", report)

        return {
            "messages": [result],
            "geopolitical_report": report,
            "sender": "geopolitical_scanner",
        }

    return geopolitical_scanner_node
