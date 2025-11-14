from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_sentiment, get_insider_transactions
from tradingagents.agents.utils.logging_utils import log_report_preview
from tradingagents.agents.utils.tool_runner import (
    extract_text_from_content,
    run_chain_with_tools,
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        scheduled_list = state.get("scheduled_analysts", []) or []
        scheduled_plan_list = state.get("scheduled_analysts_plan", []) or []
        scheduled_plan = {item.lower() for item in scheduled_plan_list}
        action = state.get("orchestrator_action", "").lower()
        ticker = state.get("target_ticker") or state["company_of_interest"]
        if (scheduled_plan and "fundamentals" not in scheduled_plan) or action not in ("", "monitor", "escalate", "trade", "execute"):
            try:
                print(f"[Fundamentals Analyst] Skipping for {ticker} | action={action} | scheduled_plan={scheduled_plan}")
            except Exception:
                pass
            return {
                "fundamentals_report": "Fundamentals analyst skipped by orchestrator directive.",
                "scheduled_analysts": [item for item in scheduled_list if item.lower() != "fundamentals"],
                "scheduled_analysts_plan": scheduled_plan_list,
            }
        current_date = state["trade_date"]
        company_name = ticker

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_insider_sentiment,
            get_insider_transactions,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements, plus `get_insider_sentiment` and `get_insider_transactions` for ownership context.",
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

        try:
            print(f"[Fundamentals Analyst] Running analysis for {ticker} | scheduled={scheduled_list}")
        except Exception:
            pass

        try:
            result, message_history, tool_runs = run_chain_with_tools(
                chain,
                tools,
                state["messages"],
            )
        except Exception as exc:
            updated_schedule = [item for item in scheduled_list if item.lower() != "fundamentals"]
            report = f"Fundamentals analyst failed: {exc}"
            return {
                "messages": state["messages"],
                "fundamentals_report": report,
                "scheduled_analysts": updated_schedule,
                "scheduled_analysts_plan": scheduled_plan_list,
            }

        report = extract_text_from_content(getattr(result, "content", "")) or "Fundamentals analyst produced no narrative."
        updated_schedule = [item for item in scheduled_list if item.lower() != "fundamentals"]

        payload = {
            "messages": message_history,
            "fundamentals_report": report,
            "scheduled_analysts": updated_schedule,
            "scheduled_analysts_plan": scheduled_plan_list,
        }
        log_report_preview("Fundamentals Analyst", ticker, report)
        try:
            print(
                f"[Fundamentals Analyst] Completed step for {ticker} | tool_runs={tool_runs} | report_len={len(report) if report else 0}"
            )
        except Exception:
            pass

        return payload

    return fundamentals_analyst_node
