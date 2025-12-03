class TestInvestDebateState:
    """Test suite for InvestDebateState TypedDict."""

    def test_invest_debate_state_structure(self):
        """Test that InvestDebateState can be instantiated with all required fields."""
        state = {
            "bull_history": "Bull argument 1\nBull argument 2",
            "bear_history": "Bear argument 1\nBear argument 2",
            "history": "Combined history",
            "current_response": "Latest response",
            "judge_decision": "Final decision",
            "count": 3,
        }

        assert state["bull_history"] == "Bull argument 1\nBull argument 2"
        assert state["bear_history"] == "Bear argument 1\nBear argument 2"
        assert state["history"] == "Combined history"
        assert state["current_response"] == "Latest response"
        assert state["judge_decision"] == "Final decision"
        assert state["count"] == 3

    def test_invest_debate_state_empty_strings(self):
        """Test InvestDebateState with empty strings."""
        state = {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        }

        assert state["bull_history"] == ""
        assert state["bear_history"] == ""
        assert state["count"] == 0

    def test_invest_debate_state_count_variations(self):
        """Test InvestDebateState with various count values."""
        for count in [0, 1, 5, 10, 100]:
            state = {
                "bull_history": f"History for count {count}",
                "bear_history": f"Bear history for count {count}",
                "history": "Combined",
                "current_response": "Response",
                "judge_decision": "Decision",
                "count": count,
            }
            assert state["count"] == count

    def test_invest_debate_state_multiline_histories(self):
        """Test InvestDebateState with multiline conversation histories."""
        bull_history = "\n".join([f"Bull point {i}" for i in range(5)])
        bear_history = "\n".join([f"Bear point {i}" for i in range(5)])

        state = {
            "bull_history": bull_history,
            "bear_history": bear_history,
            "history": "Combined history",
            "current_response": "Latest",
            "judge_decision": "Final",
            "count": 5,
        }

        assert state["bull_history"].count("\n") == 4
        assert state["bear_history"].count("\n") == 4


class TestRiskDebateState:
    """Test suite for RiskDebateState TypedDict."""

    def test_risk_debate_state_structure(self):
        """Test that RiskDebateState can be instantiated with all required fields."""
        state = {
            "risky_history": "Risky analysis 1",
            "safe_history": "Safe analysis 1",
            "neutral_history": "Neutral analysis 1",
            "history": "Combined history",
            "latest_speaker": "risky",
            "current_risky_response": "Latest risky response",
            "current_safe_response": "Latest safe response",
            "current_neutral_response": "Latest neutral response",
            "judge_decision": "Portfolio manager decision",
            "count": 2,
        }

        assert state["risky_history"] == "Risky analysis 1"
        assert state["safe_history"] == "Safe analysis 1"
        assert state["neutral_history"] == "Neutral analysis 1"
        assert state["latest_speaker"] == "risky"
        assert state["current_risky_response"] == "Latest risky response"
        assert state["count"] == 2

    def test_risk_debate_state_speaker_variations(self):
        """Test RiskDebateState with different speaker values."""
        speakers = ["risky", "safe", "neutral", "judge"]

        for speaker in speakers:
            state = {
                "risky_history": "Risky",
                "safe_history": "Safe",
                "neutral_history": "Neutral",
                "history": "History",
                "latest_speaker": speaker,
                "current_risky_response": "Risky resp",
                "current_safe_response": "Safe resp",
                "current_neutral_response": "Neutral resp",
                "judge_decision": "Decision",
                "count": 1,
            }
            assert state["latest_speaker"] == speaker

    def test_risk_debate_state_empty_responses(self):
        """Test RiskDebateState with empty response strings."""
        state = {
            "risky_history": "",
            "safe_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "",
            "current_risky_response": "",
            "current_safe_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        }

        assert state["current_risky_response"] == ""
        assert state["current_safe_response"] == ""
        assert state["current_neutral_response"] == ""

    def test_risk_debate_state_long_histories(self):
        """Test RiskDebateState with extended conversation histories."""
        risky_history = "\n".join([f"Risky round {i}" for i in range(10)])
        safe_history = "\n".join([f"Safe round {i}" for i in range(10)])
        neutral_history = "\n".join([f"Neutral round {i}" for i in range(10)])

        state = {
            "risky_history": risky_history,
            "safe_history": safe_history,
            "neutral_history": neutral_history,
            "history": "Combined",
            "latest_speaker": "neutral",
            "current_risky_response": "Latest risky",
            "current_safe_response": "Latest safe",
            "current_neutral_response": "Latest neutral",
            "judge_decision": "Final decision",
            "count": 10,
        }

        assert len(state["risky_history"].split("\n")) == 10
        assert len(state["safe_history"].split("\n")) == 10
        assert len(state["neutral_history"].split("\n")) == 10


class TestAgentState:
    """Test suite for AgentState MessagesState."""

    def test_agent_state_basic_fields(self):
        """Test AgentState with basic required fields."""
        state = {
            "messages": [],
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "sender": "market_analyst",
        }

        assert state["company_of_interest"] == "AAPL"
        assert state["trade_date"] == "2024-01-15"
        assert state["sender"] == "market_analyst"

    def test_agent_state_with_reports(self):
        """Test AgentState with all analyst reports."""
        state = {
            "messages": [],
            "company_of_interest": "TSLA",
            "trade_date": "2024-02-20",
            "sender": "fundamentals_analyst",
            "market_report": "Market analysis for TSLA",
            "sentiment_report": "Social sentiment positive",
            "news_report": "Recent news about Tesla",
            "fundamentals_report": "Strong fundamentals",
        }

        assert state["market_report"] == "Market analysis for TSLA"
        assert state["sentiment_report"] == "Social sentiment positive"
        assert state["news_report"] == "Recent news about Tesla"
        assert state["fundamentals_report"] == "Strong fundamentals"

    def test_agent_state_with_debate_states(self):
        """Test AgentState with nested debate states."""
        invest_debate = {
            "bull_history": "Bull points",
            "bear_history": "Bear points",
            "history": "Combined",
            "current_response": "Response",
            "judge_decision": "Decision",
            "count": 2,
        }

        risk_debate = {
            "risky_history": "Risky analysis",
            "safe_history": "Safe analysis",
            "neutral_history": "Neutral analysis",
            "history": "Combined risk history",
            "latest_speaker": "safe",
            "current_risky_response": "Risky resp",
            "current_safe_response": "Safe resp",
            "current_neutral_response": "Neutral resp",
            "judge_decision": "Portfolio decision",
            "count": 3,
        }

        state = {
            "messages": [],
            "company_of_interest": "NVDA",
            "trade_date": "2024-03-10",
            "sender": "research_manager",
            "investment_debate_state": invest_debate,
            "risk_debate_state": risk_debate,
        }

        assert state["investment_debate_state"]["count"] == 2
        assert state["risk_debate_state"]["count"] == 3
        assert state["risk_debate_state"]["latest_speaker"] == "safe"

    def test_agent_state_with_plans(self):
        """Test AgentState with investment and trade plans."""
        state = {
            "messages": [],
            "company_of_interest": "MSFT",
            "trade_date": "2024-04-05",
            "sender": "trader",
            "investment_plan": "Long position on MSFT based on analysis",
            "trader_investment_plan": "Execute buy order for 100 shares",
            "final_trade_decision": "BUY 100 shares at market price",
        }

        assert "Long position" in state["investment_plan"]
        assert "Execute buy order" in state["trader_investment_plan"]
        assert "BUY 100 shares" in state["final_trade_decision"]

    def test_agent_state_ticker_variations(self):
        """Test AgentState with various ticker symbols."""
        tickers = ["AAPL", "GOOGL", "AMZN", "TSLA", "MSFT", "META", "SPY", "QQQ"]

        for ticker in tickers:
            state = {
                "messages": [],
                "company_of_interest": ticker,
                "trade_date": "2024-01-01",
                "sender": "analyst",
            }
            assert state["company_of_interest"] == ticker

    def test_agent_state_date_formats(self):
        """Test AgentState with different date string formats."""
        dates = [
            "2024-01-15",
            "2024-12-31",
            "2023-06-30",
            "2025-03-20",
        ]

        for date_str in dates:
            state = {
                "messages": [],
                "company_of_interest": "SPY",
                "trade_date": date_str,
                "sender": "system",
            }
            assert state["trade_date"] == date_str

    def test_agent_state_sender_variations(self):
        """Test AgentState with different sender agent types."""
        senders = [
            "market_analyst",
            "social_analyst",
            "news_analyst",
            "fundamentals_analyst",
            "bull_researcher",
            "bear_researcher",
            "research_manager",
            "trader",
            "risky_analyst",
            "safe_analyst",
            "neutral_analyst",
            "portfolio_manager",
        ]

        for sender in senders:
            state = {
                "messages": [],
                "company_of_interest": "AAPL",
                "trade_date": "2024-01-01",
                "sender": sender,
            }
            assert state["sender"] == sender

    def test_agent_state_complete_workflow(self):
        """Test AgentState with a complete workflow scenario."""
        state = {
            "messages": [],
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-15",
            "sender": "portfolio_manager",
            "market_report": "Price trending upward, volume increasing",
            "sentiment_report": "Positive sentiment on social media",
            "news_report": "New product launch announced",
            "fundamentals_report": "Strong earnings, P/E ratio favorable",
            "investment_debate_state": {
                "bull_history": "Strong growth potential",
                "bear_history": "Market saturation concerns",
                "history": "Debate conducted",
                "current_response": "Bull case stronger",
                "judge_decision": "Recommend buy",
                "count": 3,
            },
            "investment_plan": "Enter long position",
            "trader_investment_plan": "Buy 200 shares at limit price",
            "risk_debate_state": {
                "risky_history": "Aggressive position sizing recommended",
                "safe_history": "Conservative approach suggested",
                "neutral_history": "Balanced position preferred",
                "history": "Risk analysis complete",
                "latest_speaker": "neutral",
                "current_risky_response": "Go all in",
                "current_safe_response": "Small position only",
                "current_neutral_response": "Moderate position",
                "judge_decision": "Moderate position approved",
                "count": 2,
            },
            "final_trade_decision": "BUY 200 AAPL @ $150 limit",
        }

        assert state["company_of_interest"] == "AAPL"
        assert "BUY" in state["final_trade_decision"]
        assert state["investment_debate_state"]["judge_decision"] == "Recommend buy"
        assert state["risk_debate_state"]["latest_speaker"] == "neutral"
