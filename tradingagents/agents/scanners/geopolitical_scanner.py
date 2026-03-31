from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.scanner_tools import (
    get_bitcoin_price,
    get_gold_price,
    get_oil_prices,
    get_todays_sovereign_cds,
    get_topic_news,
)
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_geopolitical_scanner(llm):
    def geopolitical_scanner_node(state):
        scan_date = state["scan_date"]

        tools = [
            get_topic_news,
            get_todays_sovereign_cds,
            get_gold_price,
            get_oil_prices,
            get_bitcoin_price,
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
        result = run_tool_loop(chain, state["messages"], tools)

        report = result.content or ""

        return {
            "messages": [result],
            "geopolitical_report": report,
            "sender": "geopolitical_scanner",
        }

    return geopolitical_scanner_node
