from unittest.mock import MagicMock, patch

from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst


def test_fundamentals_analyst_prefetches_tools():
    llm = MagicMock()
    node = create_fundamentals_analyst(llm)
    state = {"trade_date": "2024-01-01", "company_of_interest": "AAPL", "messages": []}

    with patch(
        "tradingagents.agents.analysts.fundamentals_analyst.prefetch_tools_parallel"
    ) as mock_prefetch:
        mock_prefetch.return_value = {}  # Return empty prefetched data
        with patch("tradingagents.agents.analysts.fundamentals_analyst.run_tool_loop") as mock_run:
            mock_run.return_value = MagicMock(content="Report")
            node(state)
            assert mock_prefetch.called
            # Verify specific tools are in prefetch
            args, _ = mock_prefetch.call_args
            tools_called = [t["tool"].name for t in args[0]]
            assert "get_ttm_analysis" in tools_called
            assert "get_fundamentals" in tools_called
            assert "get_peer_comparison" in tools_called
            assert "get_sector_relative" in tools_called
