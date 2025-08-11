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
        "get_fundamentals_openai",
        "get_finnhub_company_insider_sentiment",
        "get_finnhub_company_insider_transactions",
    ]

    # Create mock for each method with proper __name__ attribute
    for method_name in tool_methods:
        # Create a real function to satisfy @tool decorator requirements
        def make_mock_func(name):
            def mock_func(*args, **kwargs):
                return f"Mock {name} data"

            mock_func.__name__ = name
            mock_func.__qualname__ = name
            # Add additional attributes that @tool might check
            mock_func.__module__ = "__main__"
            mock_func.__doc__ = f"Mock function for {name}"
            return mock_func

        # Create the actual function (not a Mock)
        # Use the actual function directly without wrapping in Mock
        actual_func = make_mock_func(method_name)

        # Add 'name' attribute for tool compatibility
        actual_func.name = method_name

        # Set it on the toolkit
        setattr(toolkit, method_name, actual_func)

    return toolkit


def patch_toolkit_in_test(mock_toolkit_class):
    """Configure the mock_toolkit patch to return a properly mocked instance.
    
    Args:
        mock_toolkit_class: The patched Toolkit class
        
    Returns:
        The mock toolkit instance that will be used
    """
    mock_instance = create_mock_toolkit_with_tools()
    # Ensure that Toolkit() constructor returns our mock instance
    mock_toolkit_class.return_value = mock_instance
    return mock_instance
