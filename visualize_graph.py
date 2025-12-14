import os
from unittest.mock import MagicMock
from langchain_openai import ChatOpenAI
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.conditional_logic import ConditionalLogic

def visualize_graph():
    """
    Visualizes the agentic architecture graph using LangGraph's draw_mermaid_png.
    """
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
    
    # Setup graph with all analysts and optional agents to see the full architecture
    workflow = graph_setup.setup_graph(
        selected_analysts=["market", "social", "news", "fundamentals"],
        include_screening=True,
        include_pump_detection=True
    )
    
    graph = workflow.get_graph()

    # 1. Generate Mermaid Code
    try:
        mermaid_code = graph.draw_mermaid()
        with open("agent_architecture.mmd", "w") as f:
            f.write(mermaid_code)
        print("Saved Mermaid code to agent_architecture.mmd")
    except Exception as e:
        print(f"Failed to generate Mermaid code: {e}")

    # 2. Generate Mermaid PNG (existing)
    try:
        png_data = graph.draw_mermaid_png()
        with open("agent_architecture_mermaid.png", "wb") as f:
            f.write(png_data)
        print("Saved Mermaid PNG to agent_architecture_mermaid.png")
    except Exception as e:
        print(f"Failed to generate Mermaid PNG: {e}")

    # 3. Generate Graphviz PNG (if available)
    try:
        png_data = graph.draw_png()
        with open("agent_architecture_graphviz.png", "wb") as f:
            f.write(png_data)
        print("Saved Graphviz PNG to agent_architecture_graphviz.png")
    except Exception as e:
        print(f"Failed to generate Graphviz PNG: {e}")

if __name__ == "__main__":
    visualize_graph()
