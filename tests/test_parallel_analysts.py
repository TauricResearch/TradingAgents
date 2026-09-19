import sqlite3
import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph


class TestParallelAnalystsArchitecture(unittest.TestCase):
    def test_agent_state_channel_definitions(self):
        """Verify AgentState defines all four isolated analyst channels."""
        fields = AgentState.__annotations__
        self.assertIn("market_messages", fields)
        self.assertIn("sentiment_messages", fields)
        self.assertIn("news_messages", fields)
        self.assertIn("fundamentals_messages", fields)
        self.assertIn("messages", fields)

    def test_tool_nodes_messages_keys(self):
        """Verify each ToolNode is configured with its dedicated messages_key."""
        nodes = TradingAgentsGraph._create_tool_nodes(None)
        self.assertEqual(nodes["market"]._messages_key, "market_messages")
        self.assertEqual(nodes["social"]._messages_key, "sentiment_messages")
        self.assertEqual(nodes["news"]._messages_key, "news_messages")
        self.assertEqual(nodes["fundamentals"]._messages_key, "fundamentals_messages")

    def test_propagator_initializes_multi_channels(self):
        """Verify create_initial_state populates initial HumanMessages in each channel."""
        propagator = Propagator()
        state = propagator.create_initial_state("TEST", "2026-09-15")

        self.assertIn("market_messages", state)
        self.assertIn("sentiment_messages", state)
        self.assertIn("news_messages", state)
        self.assertIn("fundamentals_messages", state)
        self.assertEqual(state["market_messages"][0], ("human", "TEST"))
        self.assertEqual(state["sentiment_messages"][0], ("human", "TEST"))
        self.assertEqual(state["news_messages"][0], ("human", "TEST"))
        self.assertEqual(state["fundamentals_messages"][0], ("human", "TEST"))

    def test_barrier_conditional_logic(self):
        """Verify should_continue_barrier gates until all active analyst reports exist."""
        logic = ConditionalLogic()
        plan = build_analyst_execution_plan(["market", "social", "news", "fundamentals"])

        partial_state = {
            "market_report": "Market looks bullish",
            "sentiment_report": "Sentiment is positive",
            "news_report": "",  # missing!
            "fundamentals_report": "Strong earnings",
        }
        self.assertEqual(
            logic.should_continue_barrier(partial_state, plan.specs),
            END,
            "Barrier must return END while any active analyst report is missing",
        )

        complete_state = {
            "market_report": "Market looks bullish",
            "sentiment_report": "Sentiment is positive",
            "news_report": "Global affairs calm",
            "fundamentals_report": "Strong earnings",
        }
        self.assertEqual(
            logic.should_continue_barrier(complete_state, plan.specs),
            "Bull Researcher",
            "Barrier must route to Bull Researcher once all active reports are ready",
        )

    def test_barrier_subset_analysts(self):
        """Verify barrier only requires reports for selected analysts (subset)."""
        logic = ConditionalLogic()
        plan = build_analyst_execution_plan(["news", "fundamentals"])

        state = {
            "market_report": "",
            "sentiment_report": "",
            "news_report": "News report ready",
            "fundamentals_report": "Fundamentals report ready",
        }
        self.assertEqual(
            logic.should_continue_barrier(state, plan.specs),
            "Bull Researcher",
            "Barrier must pass when all SELECTED analyst reports are present",
        )

    def test_graph_setup_wiring(self):
        """Verify GraphSetup compiles with fan-out from START and analyst_barrier node."""
        mock_llm = MagicMock()
        tool_nodes = TradingAgentsGraph._create_tool_nodes(None)
        logic = ConditionalLogic()

        setup = GraphSetup(mock_llm, mock_llm, tool_nodes, logic)
        workflow = setup.setup_graph(["market", "social", "news", "fundamentals"])
        app = workflow.compile()

        nodes = app.nodes
        self.assertIn("analyst_barrier", nodes)
        self.assertIn("Market Analyst", nodes)
        self.assertIn("Sentiment Analyst", nodes)
        self.assertIn("News Analyst", nodes)
        self.assertIn("Fundamentals Analyst", nodes)
        self.assertIn("Bull Researcher", nodes)

    @unittest.mock.patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts", return_value="mock reddit")
    @unittest.mock.patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages", return_value="mock stocktwits")
    @unittest.mock.patch("tradingagents.agents.analysts.sentiment_analyst.invoke_structured_or_freetext", return_value="Mock sentiment report")
    def test_parallel_execution_and_checkpointing(self, mock_sentiment, mock_stocktwits, mock_reddit):
        """Simulate a full parallel run through the graph with SQLite checkpointing."""
        mock_quick_llm = MagicMock()
        mock_deep_llm = MagicMock()

        # Set mock returns for all analysts and downstream nodes
        mock_quick_llm.invoke.return_value = AIMessage(content="Mock analysis content")
        mock_quick_llm.bind_tools.return_value = RunnableLambda(
            lambda x: AIMessage(content="Mock tool-free report", tool_calls=[])
        )
        mock_deep_llm.invoke.return_value = AIMessage(content="Mock deep content")

        tool_nodes = TradingAgentsGraph._create_tool_nodes(None)

        def mock_news(ticker: str, start_date: str, end_date: str) -> str:
            return "mock news headlines"

        with unittest.mock.patch.object(tool_nodes["social"].tools_by_name["get_news"], "func", mock_news):
            logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
            setup = GraphSetup(mock_quick_llm, mock_deep_llm, tool_nodes, logic)

        workflow = setup.setup_graph(["market", "social", "news", "fundamentals"])

        # Compile with an in-memory SQLite Checkpointer
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        saver = SqliteSaver(conn)
        app = workflow.compile(checkpointer=saver)

        propagator = Propagator()
        init_state = propagator.create_initial_state("TEST", "2026-09-15")

        config = {"configurable": {"thread_id": "test-thread-parallel"}}
        final_state = app.invoke(init_state, config=config)

        # 1. Check all reports were generated
        self.assertTrue(bool(final_state["market_report"]))
        self.assertTrue(bool(final_state["sentiment_report"]))
        self.assertTrue(bool(final_state["news_report"]))
        self.assertTrue(bool(final_state["fundamentals_report"]))

        # 2. Check each channel has its own messages
        self.assertTrue(len(final_state["market_messages"]) >= 1)
        self.assertTrue(len(final_state["sentiment_messages"]) >= 1)
        self.assertTrue(len(final_state["news_messages"]) >= 1)
        self.assertTrue(len(final_state["fundamentals_messages"]) >= 1)

        # 3. Check downstream debate state ran
        self.assertTrue(final_state["investment_debate_state"]["count"] > 0)

        # 4. Check that SQLite checkpoints were recorded at each step
        checkpoints = list(saver.list(config))
        self.assertTrue(
            len(checkpoints) >= 5,
            f"Expected multiple fine-grained checkpoints, got {len(checkpoints)}",
        )


if __name__ == "__main__":
    unittest.main()
