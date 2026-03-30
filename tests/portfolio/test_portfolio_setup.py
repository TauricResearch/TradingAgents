import json
from unittest.mock import patch

from tradingagents.graph.portfolio_setup import PortfolioGraphSetup


def test_prioritize_candidates_only_uses_completed_ticker_analyses():
    setup = PortfolioGraphSetup(agents={}, config={})
    node = setup._make_prioritize_candidates_node()

    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {
                    "portfolio_id": "p1",
                    "name": "Main",
                    "cash": 100000.0,
                    "initial_cash": 100000.0,
                },
                "holdings": [],
            }
        ),
        "scan_summary": {
            "stocks_to_investigate": [
                {
                    "ticker": "AAPL",
                    "conviction": "high",
                    "thesis_angle": "growth",
                    "sector": "Technology",
                },
                {
                    "ticker": "NVDA",
                    "conviction": "high",
                    "thesis_angle": "momentum",
                    "sector": "Technology",
                },
            ]
        },
        "ticker_analyses": {
            "AAPL": {"final_trade_decision": "Rating: Buy"},
            "NVDA": {"analysis_status": "incomplete", "investment_plan": "partial"},
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    prioritized = json.loads(result["prioritized_candidates"])
    assert [candidate["ticker"] for candidate in prioritized] == ["AAPL"]
    assert prioritized[0]["deep_dive_summary"] == "Rating: Buy"
