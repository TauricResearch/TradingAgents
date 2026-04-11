"""Smart Money Scanner — runs sequentially after sector_scanner.

Runs three Finviz screeners to find institutional footprints:
  1. Insider buying (open-market purchases by insiders)
  2. Unusual volume (2x+ normal, price > $10)
  3. Breakout accumulation (52-week highs on 2x+ volume)

Positioned after sector_scanner so it can use sector rotation data as context
when interpreting and prioritizing Finviz signals. Each screener tool has no
parameters — filters are hardcoded to prevent LLM hallucinations.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.scanner_tools import (
    get_breakout_accumulation_stocks,
    get_insider_buying_stocks,
    get_unusual_volume_stocks,
)
from tradingagents.agents.utils.tool_runner import run_tool_loop
from tradingagents.agents.utils.report_quality import tag_report
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    save_node_report,
)


def create_smart_money_scanner(llm):
    def smart_money_scanner_node(state):
        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "smart_money_report")
        if existing_report:
            return {
                "smart_money_report": existing_report,
                "sender": "smart_money_scanner",
            }

        scan_date = state["scan_date"]
        tools = [
            get_insider_buying_stocks,
            get_unusual_volume_stocks,
            get_breakout_accumulation_stocks,
        ]

        # Inject sector rotation context — available because this node runs
        # after sector_scanner completes.
        sector_context = state.get("sector_performance_report", "")
        sector_section = (
            f"\n\nSector rotation context from the Sector Scanner:\n{sector_context}"
            if sector_context
            else ""
        )

        system_message = (
            "You are a Senior Quantitative Analyst and Systems Architect hunting for institutional footprints. "
            "Your objective is to identify 'Smart Money' signals through insider activity and volume anomalies. "
            "STRICT CONSTRAINTS: Output only bulleted quantitative analysis. NO conversational filler. "
            "You MUST call these tools exactly once: "
            "1. get_insider_buying_stocks, 2. get_unusual_volume_stocks, 3. get_breakout_accumulation_stocks. "
            "Report must include: "
            "(1) Top 5-8 primary tickers with anomalous footprints, "
            "(2) Sector classification for each ticker, "
            "(3) Footprint anomaly rationale (e.g., 'heavy insider buying in leading sector'), "
            "(4) Conflict/Confirmation deltas vs current sector rotation. "
            f"Sector Context: {sector_context[:500]}..."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants.\n{system_message}"
                    "\nFor your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=scan_date)

        chain = prompt | llm.bind_tools(tools)
        initial_messages = state["messages"][:1] if state["messages"] else []
        result = run_tool_loop(
            chain,
            initial_messages,
            tools,
            require_tool_result=True,
            node_name="smart_money_scanner",
            min_report_length=800,
            max_tool_output_chars=1200,
        )
        report_body = (result.content or "").strip()
        provenance_header = (
            "Source: Finviz Smart Money Scanner\n"
            f"Scan Date: {scan_date}\n"
            f"[Source: Finviz Smart Money Scanner | Scan Date: {scan_date}]"
        )
        raw_report = f"{provenance_header}\n\n{report_body}" if report_body else provenance_header
        tool_names = ", ".join(t.name for t in tools)
        report = tag_report(
            raw_report,
            node_name="smart_money_scanner",
            tools_used=tool_names,
        )

        # 3. Resumability: Save after completion
        if report:
            save_node_report(state, "smart_money_report", report)

        return {
            "messages": [result],
            "smart_money_report": report,
            "sender": "smart_money_scanner",
        }

    return smart_money_scanner_node
