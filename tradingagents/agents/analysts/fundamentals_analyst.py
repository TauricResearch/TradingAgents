from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json


def create_fundamentals_analyst(llm, toolkit):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        # 判断是否为中国股票
        def is_chinese_stock(ticker):
            clean_ticker = ticker.split('.')[0]
            return len(clean_ticker) == 6 and clean_ticker.isdigit()

        if is_chinese_stock(ticker):
            # 中国股票：使用智能数据源获取基本面信息
            if toolkit.config["online_tools"]:
                tools = [
                    toolkit.get_smart_stock_data,
                    toolkit.get_fundamentals_openai  # 作为补充
                ]
            else:
                tools = [
                    toolkit.get_smart_stock_data_offline,
                ]
        else:
            # 美股：保持原有工具逻辑不变
            if toolkit.config["online_tools"]:
                tools = [toolkit.get_fundamentals_openai]
            else:
                tools = [
                    toolkit.get_finnhub_company_insider_sentiment,
                    toolkit.get_finnhub_company_insider_transactions,
                    toolkit.get_simfin_balance_sheet,
                    toolkit.get_simfin_cashflow,
                    toolkit.get_simfin_income_stmt,
                ]

        # 根据股票类型设置不同的系统提示词
        if is_chinese_stock(ticker):
            # 中国股票专用基本面分析提示词
            system_message = (
                "You are a fundamental analyst specialized in Chinese A-share stocks. You are analyzing a Chinese company with 6-digit stock code format (e.g., 000001, 600036, 300996). "

                "**DATA SOURCE**: Use get_smart_stock_data to retrieve comprehensive Chinese stock data from Tushare API, which includes company fundamentals, financial metrics, and market data. "

                "**REQUIRED PARAMETERS**: When calling get_smart_stock_data, you MUST provide all three parameters: "
                "1. ticker: Chinese stock code (e.g., '300996') "
                "2. start_date: Start date in 'YYYY-MM-DD' format "
                "3. end_date: End date in 'YYYY-MM-DD' format "
                "Example: get_smart_stock_data('300996', '2024-01-01', '2024-12-31') "

                "**ANALYSIS FOCUS**: "
                "- Company profile and business model "
                "- Financial performance and key ratios "
                "- Market position in Chinese A-share market "
                "- Industry analysis within Chinese market context "
                "- Regulatory environment and policy impacts "
                "- Growth prospects and competitive advantages "

                "Write a comprehensive fundamental analysis report tailored for Chinese A-share market characteristics. "
                "Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            )
        else:
            # 美股原有基本面分析提示词（保持不变）
            system_message = (
                "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, company financial history, insider sentiment and insider transactions to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
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
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
