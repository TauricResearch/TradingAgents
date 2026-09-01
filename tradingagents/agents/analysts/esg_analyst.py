"""ESG analyst agent module."""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.esg_data_tools import get_esg_news, get_esg_scores


def create_esg_analyst(llm):
    """Create an ESG analyst node for the trading graph."""

    def esg_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = get_instrument_context_from_state(state)

        tools = [get_esg_scores, get_esg_news]

        system_message = (
            "You are an ESG (Environmental, Social, Governance) analyst tasked "
            f"with analyzing a {asset_label}'s sustainability profile and ESG risk "
            "factors. Cover environmental impact, social responsibility, governance "
            "quality, controversies, regulatory exposure, and how these factors may "
            "affect long-term investment value and risk. Use the available tools: "
            "`get_esg_scores` for current ESG ratings where point-in-time safe, and "
            "`get_esg_news` for ESG-related news and controversies up to the analysis "
            "date. If point-in-time ESG scores are unavailable, say so explicitly and "
            "do not infer current scores into historical analysis. Append a Markdown "
            "table summarizing key ESG signals, risk direction, evidence, and trading "
            "relevance."
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
        if not result.tool_calls:
            report = result.content

        return {
            "messages": [result],
            "esg_report": report,
        }

    return esg_analyst_node
