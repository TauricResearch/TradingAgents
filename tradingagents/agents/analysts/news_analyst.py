from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.agents.utils.prompts import get_news_analyst_prompt, get_agent_role_instruction, get_context_message
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm, language: str = "zh-TW"):
    """
    建立一個新聞分析師節點。

    Args:
        llm: 用於分析的語言模型。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        一個處理新聞分析的節點函式。
    """
    def news_analyst_node(state):
        """
        分析最近的新聞和趨勢。

        Args:
            state: 當前的代理狀態。

        Returns:
            更新後的代理狀態，包含新聞分析報告和訊息。
        """
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state.get("company_name", ticker)

        tools = [
            get_news,
            get_global_news,
        ]

        # Get language-specific prompts
        system_message = get_news_analyst_prompt(language)
        role_instruction = get_agent_role_instruction(language)
        context_msg = get_context_message(language, current_date, company_name, ticker)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"{role_instruction}"
                    " 您可以使用以下工具：{tool_names}。\n{system_message}"
                    f" {context_msg}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        # Report logic: only save report when LLM gives final response
        report = state.get("news_report", "")

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node