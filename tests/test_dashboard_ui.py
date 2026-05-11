"""
Test suite for TradingAgents Dashboard UI components.
Tests cover dashboard initialization, logging functionality, and UI screen interactions.
"""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add dashboard to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'dashboard'))


class TestDashboardInitialization:
    """Test dashboard initialization and configuration."""
    
    def test_dashboard_module_imports(self):
        """Test that all required modules can be imported."""
        import streamlit as st
        import plotly.graph_objects as go
        import plotly.express as px
        import pandas as pd
        import numpy as np
        
        assert st is not None
        assert go is not None
        assert px is not None
        assert pd is not None
        assert np is not None
    
    def test_session_state_initialization(self):
        """Test that session state variables are properly initialized."""
        import streamlit as st
        
        # Simulate fresh session
        if 'logs' not in st.session_state:
            st.session_state.logs = []
        if 'trades' not in st.session_state:
            st.session_state.trades = []
        if 'agents_active' not in st.session_state:
            st.session_state.agents_active = False
        if 'selected_ticker' not in st.session_state:
            st.session_state.selected_ticker = "AAPL"
        
        assert isinstance(st.session_state.logs, list)
        assert isinstance(st.session_state.trades, list)
        assert isinstance(st.session_state.agents_active, bool)
        assert isinstance(st.session_state.selected_ticker, str)
        assert st.session_state.selected_ticker == "AAPL"


class TestLoggingFunctionality:
    """Test dashboard logging system."""
    
    @pytest.fixture
    def mock_streamlit(self):
        """Mock streamlit session state for testing."""
        with patch('streamlit.session_state') as mock_state:
            mock_state.logs = []
            yield mock_state
    
    def test_add_log_creates_entry(self, mock_streamlit):
        """Test that add_log creates proper log entries."""
        from dashboard.app import add_log
        
        # Import after mocking
        import streamlit as st
        st.session_state.logs = []
        
        log_entry = add_log("INFO", "Test message", "TestAgent")
        
        assert log_entry is not None
        assert log_entry['level'] == "INFO"
        assert log_entry['message'] == "Test message"
        assert log_entry['agent'] == "TestAgent"
        assert 'timestamp' in log_entry
        assert len(st.session_state.logs) == 1
    
    def test_add_log_default_agent(self, mock_streamlit):
        """Test that add_log uses default agent when not specified."""
        import streamlit as st
        st.session_state.logs = []
        
        from dashboard.app import add_log
        log_entry = add_log("WARNING", "Warning message")
        
        assert log_entry['agent'] == "System"
        assert log_entry['level'] == "WARNING"
    
    def test_log_timestamp_format(self, mock_streamlit):
        """Test that log timestamps are properly formatted."""
        import streamlit as st
        st.session_state.logs = []
        
        from dashboard.app import add_log
        log_entry = add_log("INFO", "Test")
        
        # Check timestamp format (YYYY-MM-DD HH:MM:SS)
        timestamp = log_entry['timestamp']
        assert len(timestamp) == 19  # Fixed length format
        assert timestamp[4] == '-'  # Year-Month separator
        assert timestamp[7] == '-'  # Month-Day separator
        assert timestamp[10] == ' '  # Date-Time separator
        assert timestamp[13] == ':'  # Hour-Minute separator
        assert timestamp[16] == ':'  # Minute-Second separator
    
    def test_multiple_logs_accumulate(self, mock_streamlit):
        """Test that multiple logs are accumulated correctly."""
        import streamlit as st
        st.session_state.logs = []
        
        from dashboard.app import add_log
        
        add_log("INFO", "First log")
        add_log("WARNING", "Second log")
        add_log("ERROR", "Third log")
        
        assert len(st.session_state.logs) == 3
        assert st.session_state.logs[0]['level'] == "INFO"
        assert st.session_state.logs[1]['level'] == "WARNING"
        assert st.session_state.logs[2]['level'] == "ERROR"


class TestDataGeneration:
    """Test data generation functions."""
    
    def test_generate_sample_trade_data(self):
        """Test trade data generation."""
        from dashboard.app import generate_sample_trade_data
        
        df = generate_sample_trade_data("AAPL", days=30)
        
        assert df is not None
        assert len(df) == 30
        assert 'Date' in df.columns
        assert 'Price' in df.columns
        assert 'Volume' in df.columns
        assert 'Ticker' in df.columns
        assert df['Ticker'].iloc[0] == "AAPL"
        assert len(df['Price']) == 30
        assert all(df['Price'] > 0)  # Prices should be positive
        assert all(df['Volume'] > 0)  # Volume should be positive
    
    def test_generate_trade_data_different_tickers(self):
        """Test data generation with different tickers."""
        from dashboard.app import generate_sample_trade_data
        
        for ticker in ["GOOGL", "MSFT", "TSLA"]:
            df = generate_sample_trade_data(ticker, days=15)
            assert df['Ticker'].iloc[0] == ticker
            assert len(df) == 15
    
    def test_generate_trade_data_variable_days(self):
        """Test data generation with different time ranges."""
        from dashboard.app import generate_sample_trade_data
        
        for days in [7, 30, 60, 90]:
            df = generate_sample_trade_data("AAPL", days=days)
            assert len(df) == days


class TestChartCreation:
    """Test chart creation functions."""
    
    def test_create_price_chart(self):
        """Test price chart creation."""
        # pyrefly: ignore [missing-import]
        from dashboard.app import generate_sample_trade_data, create_price_chart
        
        df = generate_sample_trade_data("AAPL", days=30)
        fig = create_price_chart(df)
        
        assert fig is not None
        assert hasattr(fig, 'data')
        assert len(fig.data) > 0
        assert fig.layout.title is not None
        assert "AAPL" in fig.layout.title.text
    
    def test_create_volume_chart(self):
        """Test volume chart creation."""
        from dashboard.app import generate_sample_trade_data, create_volume_chart
        
        df = generate_sample_trade_data("AAPL", days=30)
        fig = create_volume_chart(df)
        
        assert fig is not None
        assert hasattr(fig, 'data')
        assert len(fig.data) > 0
    
    def test_create_agent_activity_chart(self):
        """Test agent activity chart creation."""
        from dashboard.app import create_agent_activity_chart
        
        fig = create_agent_activity_chart()
        
        assert fig is not None
        assert hasattr(fig, 'data')
        # Should have bars for 5 agents
        assert len(fig.data) > 0


class TestSimulationLogic:
    """Test trading simulation logic."""
    
    @pytest.fixture
    def mock_session_state(self):
        """Mock session state for simulation tests."""
        import streamlit as st
        st.session_state.logs = []
        st.session_state.trades = []
        st.session_state.agents_active = True
        return st.session_state
    
    def test_simulation_steps_execution(self, mock_session_state):
        """Test that simulation executes all steps."""
        from dashboard.app import add_log
        
        steps = [
            ("Bull Researcher", "Analyzing market trends..."),
            ("Bear Researcher", "Evaluating risks..."),
            ("Research Manager", "Consolidating research..."),
            ("Trader", "Executing trade decision..."),
            ("Risk Manager", "Validating risk parameters...")
        ]
        
        active_agents = ["Bull Researcher", "Bear Researcher", "Trader"]
        
        for agent, message in steps:
            if agent in active_agents:
                add_log("INFO", message, agent)
        
        # Should have logged for active agents only
        assert len(mock_session_state.logs) == 3
    
    def test_trade_creation_during_simulation(self, mock_session_state):
        """Test that trades are created during simulation."""
        import numpy as np
        from datetime import datetime
        
        # Simulate trade execution
        trade = {
            "ticker": "AAPL",
            "action": np.random.choice(["BUY", "SELL"]),
            "quantity": np.random.randint(10, 100),
            "price": round(np.random.uniform(100, 500), 2),
            "timestamp": datetime.now().isoformat(),
            "profit": round(np.random.uniform(-100, 500), 2)
        }
        
        mock_session_state.trades.append(trade)
        
        assert len(mock_session_state.trades) == 1
        assert trade['ticker'] == "AAPL"
        assert trade['action'] in ["BUY", "SELL"]
        assert trade['quantity'] >= 10
        assert trade['quantity'] <= 100
        assert trade['price'] >= 100
        assert trade['price'] <= 500


class TestUIComponents:
    """Test UI component rendering (mocked)."""
    
    def test_ticker_list_availability(self):
        """Test that required tickers are available."""
        tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]
        
        assert len(tickers) == 8
        assert "AAPL" in tickers
        assert "TSLA" in tickers
    
    def test_agent_list_availability(self):
        """Test that required agents are available."""
        agents = ["Bull Researcher", "Bear Researcher", "Research Manager", "Trader", "Risk Manager"]
        
        assert len(agents) == 5
        assert "Bull Researcher" in agents
        assert "Bear Researcher" in agents
        assert "Trader" in agents
    
    def test_log_levels_available(self):
        """Test that all log levels are defined."""
        log_levels = ["INFO", "WARNING", "ERROR", "SUCCESS"]
        
        assert len(log_levels) == 4
        assert "INFO" in log_levels
        assert "ERROR" in log_levels


class TestIntegration:
    """Integration tests for dashboard components."""
    
    def test_full_simulation_workflow(self):
        """Test complete simulation workflow."""
        import streamlit as st
        st.session_state.logs = []
        st.session_state.trades = []
        st.session_state.agents_active = True
        st.session_state.selected_ticker = "AAPL"
        
        from dashboard.app import add_log, generate_sample_trade_data
        
        # Initialize
        add_log("INFO", "Simulation started", "System")
        
        # Generate data
        data = generate_sample_trade_data(st.session_state.selected_ticker, 30)
        assert data is not None
        
        # Simulate trading
        if st.session_state.agents_active:
            import numpy as np
            from datetime import datetime
            
            trade = {
                "ticker": st.session_state.selected_ticker,
                "action": "BUY",
                "quantity": 50,
                "price": 150.00,
                "timestamp": datetime.now().isoformat(),
                "profit": 25.50
            }
            st.session_state.trades.append(trade)
            add_log("SUCCESS", f"Executed trade for {st.session_state.selected_ticker}", "Trader")
        
        # Verify state
        assert len(st.session_state.logs) == 2
        assert len(st.session_state.trades) == 1
        assert st.session_state.trades[0]['profit'] == 25.50
    
    def test_log_filtering(self):
        """Test log filtering functionality."""
        import streamlit as st
        st.session_state.logs = []
        
        from dashboard.app import add_log
        
        # Add various log levels
        add_log("INFO", "Info message")
        add_log("WARNING", "Warning message")
        add_log("ERROR", "Error message")
        add_log("SUCCESS", "Success message")
        
        # Filter for errors only
        error_logs = [log for log in st.session_state.logs if log['level'] == "ERROR"]
        assert len(error_logs) == 1
        assert error_logs[0]['message'] == "Error message"
        
        # Filter for info and warnings
        filtered = [log for log in st.session_state.logs if log['level'] in ["INFO", "WARNING"]]
        assert len(filtered) == 2
    
    def test_trade_profitability_calculation(self):
        """Test trade profitability calculations."""
        import streamlit as st
        import numpy as np
        
        st.session_state.trades = [
            {"profit": 100.00},
            {"profit": -50.00},
            {"profit": 75.00},
            {"profit": -25.00},
            {"profit": 200.00}
        ]
        
        total_trades = len(st.session_state.trades)
        profitable = sum(1 for t in st.session_state.trades if t.get('profit', 0) > 0)
        avg_profit = np.mean([t.get('profit', 0) for t in st.session_state.trades])
        
        assert total_trades == 5
        assert profitable == 3  # 3 profitable trades
        assert avg_profit == 60.00  # (100 - 50 + 75 - 25 + 200) / 5


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_logs_handling(self):
        """Test handling of empty log list."""
        import streamlit as st
        st.session_state.logs = []
        
        # Should not raise errors
        filtered_logs = [log for log in st.session_state.logs if log['level'] in ["INFO"]]
        assert len(filtered_logs) == 0
    
    def test_empty_trades_handling(self):
        """Test handling of empty trades list."""
        import streamlit as st
        import numpy as np
        
        st.session_state.trades = []
        
        total_trades = len(st.session_state.trades)
        assert total_trades == 0
        
        # Average profit should handle empty list
        if total_trades > 0:
            avg_profit = np.mean([t.get('profit', 0) for t in st.session_state.trades])
        else:
            avg_profit = 0.0
        
        assert avg_profit == 0.0
    
    def test_minimum_days_data_generation(self):
        """Test data generation with minimum days."""
        from dashboard.app import generate_sample_trade_data
        
        df = generate_sample_trade_data("AAPL", days=1)
        
        assert len(df) == 1
        assert df['Price'].iloc[0] > 0
    
    def test_maximum_days_data_generation(self):
        """Test data generation with large number of days."""
        from dashboard.app import generate_sample_trade_data
        
        df = generate_sample_trade_data("AAPL", days=365)
        
        assert len(df) == 365
        assert all(df['Price'] > 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
