"""Helper to create properly mocked toolkit for test_trading_graph."""

from unittest.mock import Mock


def create_mock_toolkit_with_tools():
    """Create a mock toolkit with all necessary tool methods."""
    toolkit = Mock()
    toolkit.config = {"online_tools": False}

    # List of all methods that need to be mocked
    tool_methods = [
        # Market tools
        "get_YFin_data",
        "get_YFin_data_online",
        "get_stockstats_indicators_report",
        "get_stockstats_indicators_report_online",
        # Social tools
        "get_reddit_stock_info",
        "get_stock_news_openai",
        # News tools
        "get_global_news_openai",
        "get_google_news",
        "get_finnhub_news",
        "get_reddit_news",
        # Fundamentals tools
        "get_simfin_cashflow",
        "get_simfin_income_stmt",
        "get_simfin_balance_sheet",
        "get_finnhub_basic_financials",
    ]

    # Create mock for each method with proper __name__ attribute
    for method_name in tool_methods:
        # Create a function with the right name
        def mock_func():
            return f"Mock {method_name} data"

        # Create Mock wrapping the function
        mock_method = Mock(side_effect=mock_func)
        mock_method.__name__ = method_name
        mock_method.name = method_name

        # Set it on the toolkit
        setattr(toolkit, method_name, mock_method)

    return toolkit


def patch_toolkit_in_test(mock_toolkit):
    """Configure the mock_toolkit patch to return a properly mocked instance."""
    mock_instance = create_mock_toolkit_with_tools()
    mock_toolkit.return_value = mock_instance
    return mock_instance
