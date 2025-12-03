from datetime import date

from tradingagents.graph.propagation import Propagator


class TestPropagator:
    def setup_method(self):
        self.propagator = Propagator(max_recur_limit=50)

    def test_create_initial_state_basic(self):
        state = self.propagator.create_initial_state("AAPL", "2024-01-15")

        assert state["company_of_interest"] == "AAPL"
        assert state["trade_date"] == "2024-01-15"
        assert state["market_report"] == ""
        assert state["fundamentals_report"] == ""
        assert state["sentiment_report"] == ""
        assert state["news_report"] == ""

    def test_create_initial_state_messages(self):
        state = self.propagator.create_initial_state("MSFT", "2024-01-15")

        assert "messages" in state
        assert len(state["messages"]) == 1
        assert state["messages"][0] == ("human", "MSFT")

    def test_create_initial_state_debate_states(self):
        state = self.propagator.create_initial_state("GOOGL", "2024-01-15")

        assert "investment_debate_state" in state
        invest_state = state["investment_debate_state"]
        assert invest_state["history"] == ""
        assert invest_state["current_response"] == ""
        assert invest_state["count"] == 0

        assert "risk_debate_state" in state
        risk_state = state["risk_debate_state"]
        assert risk_state["history"] == ""
        assert risk_state["count"] == 0

    def test_create_initial_state_with_date_object(self):
        trade_date = date(2024, 1, 15)
        state = self.propagator.create_initial_state("TSLA", trade_date)

        assert state["trade_date"] == "2024-01-15"

    def test_get_graph_args(self):
        args = self.propagator.get_graph_args()

        assert "stream_mode" in args
        assert args["stream_mode"] == "values"
        assert "config" in args
        assert "recursion_limit" in args["config"]
        assert args["config"]["recursion_limit"] == 50

    def test_custom_recursion_limit(self):
        custom_propagator = Propagator(max_recur_limit=200)
        args = custom_propagator.get_graph_args()

        assert args["config"]["recursion_limit"] == 200

    def test_state_is_dict(self):
        state = self.propagator.create_initial_state("NVDA", "2024-01-15")
        assert isinstance(state, dict)

    def test_multiple_states_independent(self):
        state1 = self.propagator.create_initial_state("AAPL", "2024-01-15")
        state2 = self.propagator.create_initial_state("MSFT", "2024-01-16")

        assert state1["company_of_interest"] != state2["company_of_interest"]
        assert state1["trade_date"] != state2["trade_date"]

        state1["market_report"] = "Modified"
        assert state2["market_report"] == ""
