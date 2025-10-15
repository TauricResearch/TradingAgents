from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.dataflows.fred_api import get_dxy_data, get_real_yields, get_inflation_data, get_fred_series

def create_xau_macro_analyst(llm):
    """
    Create a node factory that builds an XAU (gold) macroeconomic analyst agent.
    
    The returned node analyzes macro drivers of XAU/USD (DXY, 10-year real yields, inflation metrics, and optionally Fed policy/VIX) using bound data-fetching tools, and synthesizes a comprehensive report that concludes with a Markdown table summarizing each factor's likely impact (Bullish, Bearish, or Neutral).
    
    Returns:
        callable: A node function that accepts a `state` dict and returns a dict containing:
            - "messages": a list with the agent's final message/result.
            - "xau_macro_report": the agent's textual report (empty string if the result contains tool calls).
    """
    """
    Execute the XAU macro analyst for a given state.
    
    Parameters:
        state (dict): Execution state expected to include:
            - "trade_date": date string used as the chain's current_date.
            - "messages": conversation messages supplied to the chain.
    
    Returns:
        dict: {
            "messages": [result],            # list containing the chain result object
            "xau_macro_report": report_str,  # string report produced when no tool calls were made
        }
    """

    system_message = (
        "You are a specialized Macroeconomic Analyst for Gold (XAU/USD). Your mission is to provide a detailed analysis of the key macro drivers affecting gold's price. "
        "DO NOT analyze company fundamentals. Instead, focus exclusively on the following:"
        "\n\n1.  **US Dollar Index (DXY)**: Analyze its recent trend (e.g., past 90 days). Is it strengthening or weakening? Explain how this trend typically impacts gold."
        "\n2.  **Real Yields**: Analyze the trend in 10-year real yields. Are they rising or falling? Explain the inverse relationship between real yields and gold (i.e., opportunity cost)."
        "\n3.  **Inflation Data**: Review the latest inflation metrics (CPI, PCE). Is inflation running hot or cooling down? Explain how inflation expectations affect gold's appeal as a hedge."
        "\n4.  **Fed Policy & VIX (Optional)**: Briefly mention the current Federal Reserve stance (if known) and the VIX level as a measure of market fear."
        "\n\nUse the available tools to fetch the necessary data. Synthesize your findings into a comprehensive report. "
        "Conclude your report with a Markdown table summarizing the key macro factors and their likely impact on gold (Bullish, Bearish, or Neutral)."
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
        get_dxy_data,
        get_real_yields,
        get_inflation_data,
        get_fred_series, # For VIX or other specific series
    ]

    prompt = prompt.partial(
        system_message=system_message,
        tool_names=", ".join([tool.name for tool in tools]),
    )

    chain = prompt | llm.bind_tools(tools)

    def xau_macro_analyst_node(state):
        """
        Run the XAU Macro Analyst chain for a given trading state and return the chain result plus a produced macro report.
        
        Parameters:
        	state (dict): Execution state containing:
        		- "trade_date": date or string used as the chain's current date.
        		- "messages": list of messages to pass into the chain.
        
        Returns:
        	dict: Contains:
        		- "messages": list with the chain invocation result as its single element.
        		- "xau_macro_report": the report string; set to the chain result's content if the result performed no tool calls, otherwise an empty string.
        """
        current_date = state["trade_date"]
        # The ticker is XAU, but the tools are specific to macro data.
        chain_with_date = chain.partial(current_date=current_date)
        result = chain_with_date.invoke(state["messages"])

        report = ""
        if not result.tool_calls:
            report = result.content

        return {
            "messages": [result],
            "xau_macro_report": report,
        }

    return xau_macro_analyst_node