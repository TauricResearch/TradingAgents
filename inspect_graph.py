from unittest.mock import MagicMock
from langchain_openai import ChatOpenAI
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.conditional_logic import ConditionalLogic

def inspect_graph_methods():
    # Mock dependencies
    mock_llm = MagicMock(spec=ChatOpenAI)
    mock_memory = MagicMock()
    mock_tools = {
        "market": MagicMock(),
        "social": MagicMock(),
        "news": MagicMock(),
        "fundamentals": MagicMock(),
        "screening": MagicMock(),
        "pump_detection": MagicMock(),
    }
    
    conditional_logic = ConditionalLogic()
    
    # Initialize GraphSetup
    graph_setup = GraphSetup(
        quick_thinking_llm=mock_llm,
        deep_thinking_llm=mock_llm,
        tool_nodes=mock_tools,
        bull_memory=mock_memory,
        bear_memory=mock_memory,
        trader_memory=mock_memory,
        invest_judge_memory=mock_memory,
        risk_manager_memory=mock_memory,
        conditional_logic=conditional_logic,
    )
    
    # Setup graph
    workflow = graph_setup.setup_graph(
        selected_analysts=["market"],
        include_screening=True,
        include_pump_detection=True
    )
    
    graph = workflow.get_graph()
    print("Available methods on graph:")
    for method in dir(graph):
        if "draw" in method:
            print(method)

if __name__ == "__main__":
    inspect_graph_methods()
