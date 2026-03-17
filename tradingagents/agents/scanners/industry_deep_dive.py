from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import get_industry_performance, get_topic_news
from tradingagents.agents.utils.tool_runner import run_tool_loop


def create_industry_deep_dive(llm):
    def industry_deep_dive_node(state):
        scan_date = state["scan_date"]

        tools = [get_industry_performance, get_topic_news]

        # Inject Phase 1 context so the LLM can decide which sectors to drill into
        phase1_context = f"""## Phase 1 Scanner Reports (for your reference)

### Geopolitical Report:
{state.get("geopolitical_report", "Not available")}

### Market Movers Report:
{state.get("market_movers_report", "Not available")}

### Sector Performance Report:
{state.get("sector_performance_report", "Not available")}
"""

        system_message = (
            "You are a senior research analyst performing an industry deep dive. "
            "You have received reports from three parallel scanners (geopolitical, market movers, sector performance). "
            "Review these reports and identify the 2-3 most promising sectors/industries to investigate further. "
            "Use get_industry_performance to drill into those sectors and get_topic_news for sector-specific news. "
            "Write a detailed report covering: "
            "(1) Why these industries were selected, "
            "(2) Top companies within each industry and their recent performance, "
            "(3) Industry-specific catalysts and risks, "
            "(4) Cross-references between geopolitical events and sector opportunities."
            f"\n\n{phase1_context}"
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
            "industry_deep_dive_report": report,
            "sender": "industry_deep_dive",
        }

    return industry_deep_dive_node
