from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.dataflows.cot_data import get_cot_positioning, analyze_cot_extremes
from tradingagents.dataflows.etf_flows import get_gold_etf_summary, get_gold_etf_flows

def create_xau_positioning_analyst(llm):
    """
    Create and configure an XAU (Gold) Positioning Analyst node that synthesizes COT reports and ETF flow data.
    
    Constructs a tool-assisted prompt chain focused on Gold (XAU/USD) positioning using Commitment of Traders (COT) data and major gold ETF flows, and returns a node function that performs the analysis for a given state.
    
    Returns:
        xau_positioning_analyst_node (callable): A node function that accepts a `state` dict and returns a dict containing analysis messages and a generated `xau_positioning_report`.
    """
    """
    Execute the XAU Positioning Analyst on a given state.
    
    Parameters:
        state (dict): Execution state containing at least:
            - "trade_date": date or date-like string used as the prompt's current_date.
            - "messages": list of messages to pass into the prompt chain.
    
    Returns:
        dict: {
            "messages": [result_message],               # list containing the chain result message
            "xau_positioning_report": report (str)      # report text when no tool calls were made, otherwise empty string
        }
    """

    system_message = (
        "You are a specialized Market Positioning Analyst for Gold (XAU/USD). Your task is to analyze sentiment and capital flows from institutional and speculative traders. "
        "Ignore social media. Your analysis must be based on hard data."
        "\n\n1.  **Commitment of Traders (COT) Report**: Use the `get_cot_positioning` and `analyze_cot_extremes` tools. What is the net positioning of Large Speculators vs. Commercials? Is the positioning at a historical extreme? Extreme positioning is often a strong contrarian indicator."
        "\n2.  **Gold ETF Flows**: Use the `get_gold_etf_summary` tool. Are major gold ETFs (like GLD and IAU) seeing inflows or outflows? Explain what this indicates about institutional investor sentiment."
        "\n3.  **Synthesis**: Combine the insights from both COT data and ETF flows. For example, are speculators heavily long while ETFs are seeing outflows? This could be a major divergence."
        "\n\nSynthesize your findings into a comprehensive report. Conclude with a Markdown table summarizing the positioning data and its likely impact on gold (Bullish, Bearish, or Neutral)."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " The asset of interest is Gold (XAU/USD)."
                " For your reference, the current date is {current_date}."
                "\n\nTool Names: {tool_names}"
                "\n\n{system_message}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    tools = [
        get_cot_positioning,
        analyze_cot_extremes,
        get_gold_etf_summary,
        get_gold_etf_flows,
    ]

    prompt = prompt.partial(
        system_message=system_message,
        tool_names=", ".join([tool.name for tool in tools]),
    )

    chain = prompt | llm.bind_tools(tools)

    def xau_positioning_analyst_node(state):
        """
        Execute the XAU positioning analyst chain for the given state and produce a positioning report.
        
        Parameters:
            state (dict): Runtime state containing:
                - "trade_date" (str or date): Trade date to bind into the analyst chain.
                - "messages" (list): Messages to pass into the analyst chain.
        
        Returns:
            dict: {
                "messages": [result],  # list containing the chain invocation result object
                "xau_positioning_report": str  # report text extracted from result.content when no tool calls were made, otherwise an empty string
            }
        """
        current_date = state["trade_date"]
        chain_with_date = chain.partial(current_date=current_date)
        result = chain_with_date.invoke(state["messages"])

        report = ""
        if not result.tool_calls:
            report = result.content

        return {
            "messages": [result],
            "xau_positioning_report": report,
        }

    return xau_positioning_analyst_node