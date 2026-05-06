"""Integration tests for PortfolioGraph run_id seeding and propagation.

Validates: Requirements 4.1, 4.2, 4.3

- PortfolioGraph.run() generates UUID when run_id not provided
- Provided run_id is seeded into initial state
- run_id propagates to downstream nodes
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from tradingagents.graph.portfolio_graph import PortfolioGraph


class TestRunIdSeeding:
    """Tests for run_id seeding in PortfolioGraph.run()."""

    @patch.object(PortfolioGraph, "__init__", lambda self, **kwargs: None)
    def test_generates_uuid_when_run_id_not_provided(self):
        """PortfolioGraph.run() must generate a UUID when run_id is not provided.

        Validates: Requirement 4.2
        """
        pg = PortfolioGraph()
        pg.debug = False
        pg.graph = MagicMock()
        pg.graph.invoke = MagicMock(return_value={"run_id": "will-be-overwritten"})

        pg.run(
            portfolio_id="test-portfolio",
            date="2026-03-20",
            prices={"AAPL": 185.0},
            scan_summary={"stocks_to_investigate": []},
            run_id=None,
        )

        # Verify invoke was called with a state containing a valid UUID run_id
        call_args = pg.graph.invoke.call_args
        initial_state = call_args[0][0]
        assert "run_id" in initial_state
        # Should be a valid UUID
        parsed = uuid.UUID(initial_state["run_id"])
        assert str(parsed) == initial_state["run_id"]

    @patch.object(PortfolioGraph, "__init__", lambda self, **kwargs: None)
    def test_uses_provided_run_id(self):
        """PortfolioGraph.run() must use the provided run_id when given.

        Validates: Requirement 4.1
        """
        pg = PortfolioGraph()
        pg.debug = False
        pg.graph = MagicMock()
        pg.graph.invoke = MagicMock(return_value={})

        custom_run_id = "my-custom-run-id-12345"
        pg.run(
            portfolio_id="test-portfolio",
            date="2026-03-20",
            prices={"AAPL": 185.0},
            scan_summary={"stocks_to_investigate": []},
            run_id=custom_run_id,
        )

        call_args = pg.graph.invoke.call_args
        initial_state = call_args[0][0]
        assert initial_state["run_id"] == custom_run_id

    @patch.object(PortfolioGraph, "__init__", lambda self, **kwargs: None)
    def test_run_id_in_initial_state_propagates(self):
        """run_id seeded in initial state is available to downstream nodes.

        Validates: Requirement 4.3
        """
        pg = PortfolioGraph()
        pg.debug = False

        # Capture the initial state passed to graph.invoke
        captured_state = {}

        def capture_invoke(state):
            captured_state.update(state)
            return state

        pg.graph = MagicMock()
        pg.graph.invoke = capture_invoke

        pg.run(
            portfolio_id="test-portfolio",
            date="2026-03-20",
            prices={"AAPL": 185.0, "MSFT": 420.0},
            scan_summary={"stocks_to_investigate": ["AAPL"]},
            run_id="propagation-test-id",
        )

        # Verify run_id is in the state that gets passed to the graph
        assert captured_state["run_id"] == "propagation-test-id"
        # Verify other expected fields are also present
        assert captured_state["portfolio_id"] == "test-portfolio"
        assert captured_state["analysis_date"] == "2026-03-20"

    @patch.object(PortfolioGraph, "__init__", lambda self, **kwargs: None)
    def test_generated_run_id_is_unique_across_calls(self):
        """Each call to run() without run_id should generate a unique UUID.

        Validates: Requirement 4.2
        """
        pg = PortfolioGraph()
        pg.debug = False
        pg.graph = MagicMock()
        pg.graph.invoke = MagicMock(return_value={})

        run_ids = set()
        for _ in range(5):
            pg.run(
                portfolio_id="test-portfolio",
                date="2026-03-20",
                prices={"AAPL": 185.0},
                scan_summary={"stocks_to_investigate": []},
                run_id=None,
            )
            call_args = pg.graph.invoke.call_args
            initial_state = call_args[0][0]
            run_ids.add(initial_state["run_id"])

        # All 5 generated run_ids should be unique
        assert len(run_ids) == 5

    @patch.object(PortfolioGraph, "__init__", lambda self, **kwargs: None)
    def test_empty_string_run_id_generates_uuid(self):
        """Empty string run_id should trigger UUID generation (falsy value).

        Validates: Requirement 4.2
        """
        pg = PortfolioGraph()
        pg.debug = False
        pg.graph = MagicMock()
        pg.graph.invoke = MagicMock(return_value={})

        pg.run(
            portfolio_id="test-portfolio",
            date="2026-03-20",
            prices={"AAPL": 185.0},
            scan_summary={"stocks_to_investigate": []},
            run_id="",
        )

        call_args = pg.graph.invoke.call_args
        initial_state = call_args[0][0]
        # Empty string is falsy, so a UUID should be generated
        assert initial_state["run_id"] != ""
        # Should be a valid UUID
        parsed = uuid.UUID(initial_state["run_id"])
        assert str(parsed) == initial_state["run_id"]

    @patch.object(PortfolioGraph, "__init__", lambda self, **kwargs: None)
    def test_initial_state_contains_all_required_fields(self):
        """Initial state must contain all fields needed by downstream nodes.

        Validates: Requirement 4.3
        """
        pg = PortfolioGraph()
        pg.debug = False
        pg.graph = MagicMock()
        pg.graph.invoke = MagicMock(return_value={})

        pg.run(
            portfolio_id="test-portfolio",
            date="2026-03-20",
            prices={"AAPL": 185.0},
            scan_summary={"stocks_to_investigate": ["AAPL"]},
            run_id="test-run-id",
        )

        call_args = pg.graph.invoke.call_args
        initial_state = call_args[0][0]

        # Verify all expected fields are present
        expected_fields = [
            "portfolio_id",
            "analysis_date",
            "run_id",
            "prices",
            "scan_summary",
            "messages",
        ]
        for field in expected_fields:
            assert field in initial_state, f"Missing field: {field}"
