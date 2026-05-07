"""ESG (Environmental, Social, Governance) Analyst agent module."""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.esg_data_tools import (
    get_esg_scores,
    get_esg_news,
)


def create_esg_analyst(llm):
    """Create an ESG (Environmental, Social, Governance) analyst agent.

    This agent analyzes a company's sustainability performance and ESG risk factors,
    covering environmental impact, social responsibility, and governance quality.

    Args:
        llm: The language model instance to use for analysis.

    Returns:
        A node function that processes graph state and returns ESG report updates.
    """
    def esg_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_esg_scores, get_esg_news]

        system_message = (
            "You are an ESG (Environmental, Social, Governance) analyst tasked with "
            "analyzing a company's sustainability performance and ESG risk factors. "
            "Please write a comprehensive report covering: "
            "1) Environmental impact: carbon emissions, resource usage, climate risks, environmental compliance; "
            "2) Social responsibility: labor practices, employee relations, community impact, diversity and inclusion; "
            "3) Governance: board structure, executive compensation, transparency, ethics and compliance programs. "
            "Use the available tools to retrieve ESG scores and ESG-related news. "
            "Provide specific, actionable insights on how ESG factors affect "
            "long-term investment value and risk profile. "
            "Highlight any controversies or red flags that could impact stock performance."
            + " Make sure to append a Markdown table at the end of the report to organize key points, making it easy to read."
            + " Use the available tools: `get_esg_scores` for ESG ratings and scores, `get_esg_news` for ESG-related news and controversies."
            + get_language_instruction()
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
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "esg_report": report,
        }

    return esg_analyst_node