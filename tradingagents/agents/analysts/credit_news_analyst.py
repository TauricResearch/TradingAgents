"""
/**
 * @module: TradingAgents
 * @file: credit_news_analyst.py
 * @description: Credit news analyst agent (issuer news, rating actions, covenant amendments)
 * @author: Maíra Pontin
 * @created: 2026-09-28T10:46:55
 * @updated: 2026-09-28T11:05:32
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_news,
    get_instrument_context_from_state,
    get_language_instruction,
)


def create_credit_news_analyst(llm):
    """Create a credit news analyst node.
    
    Monitors issuer news, rating agency actions, covenant amendments,
    and restructuring events affecting creditworthiness.
    """
    def credit_news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_news,
        ]

        system_message = (
            "You are a credit news analyst monitoring Brazilian corporate bond issuers. "
            "Scan for material events affecting the issuer's creditworthiness:\n\n"
            "1. **CVM filings:** Fatos Relevantes, Avisos aos Acionistas\n"
            "2. **Rating agency actions:** S&P, Moody's, Fitch upgrades/downgrades/outlook changes\n"
            "3. **Covenant amendments:** Waiver requests, consent solicitations\n"
            "4. **Restructuring news:** M&A, divestitures, refinancing, asset sales\n\n"
            "Focus on events that impact **default risk** and **recovery rate**. "
            "Summarize material events and their credit implications (positive/negative/neutral).\n\n"
            "Use the available tool: `get_news` for issuer news and CVM filings."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other analysts."
                    " Use the provided tools to scan for credit-relevant news."
                    " If you are unable to fully answer, that's OK; another analyst with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the credit decision."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
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
            "news_report": report,
        }

    return credit_news_analyst_node
