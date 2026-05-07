"""Integration tests for run_id seeding and propagation through PortfolioGraph.

Validates:
- Requirements 4.1: Provided run_id is seeded into initial state
- Requirements 4.2: UUID is generated when run_id not provided
- Requirements 4.3: run_id propagates to all downstream nodes
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.graph.portfolio_setup import PortfolioGraphSetup
from tradingagents.portfolio.models import Portfolio

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Minimal repository stub that satisfies PortfolioGraphSetup requirements."""

    def get_portfolio_with_holdings(self, _portfolio_id, _prices):
        p = Portfolio(
            portfolio_id="portfolio-1",
            name="test",
            cash=2500.0,
            initial_cash=100000.0,
        )
        p.total_value = 100000.0
        return p, []

    def take_snapshot(self, portfolio_id, _prices):
        return SimpleNamespace(
            to_dict=lambda: {
                "portfolio_id": portfolio_id,
                "cash": 0.0,
                "total_value": 0.0,
            }
        )


def _build_graph_with_capture(capture_dict: dict[str, str | None]):
    """Build a compiled portfolio graph where every node captures run_id from state.

    Args:
        capture_dict: Mutable dict that will be populated with
                      {node_name: run_id_value} for each node that executes.
    """

    def _capture_node(name, return_fields):
        def _node(state):
            capture_dict[name] = state.get("run_id")
            return return_fields

        return _node

    agents = {
        "review_holdings": _capture_node(
            "review_holdings", {"holding_reviews": "{}", "sender": "review_holdings"}
        ),
        "macro_summary": _capture_node(
            "macro_summary", {"macro_brief": "macro", "sender": "macro_summary"}
        ),
        "micro_summary": _capture_node(
            "micro_summary", {"micro_brief": "micro", "sender": "micro_summary"}
        ),
        "pm_decision": _capture_node(
            "pm_decision",
            {
                "pm_decision": json.dumps(
                    {
                        "sells": [],
                        "buys": [],
                        "holds": [],
                        "cash_reserve_pct": 100.0,
                    }
                ),
                "sender": "pm_decision",
            },
        ),
    }

    graph = PortfolioGraphSetup(
        agents,
        repo=_FakeRepo(),
        config={
            "max_position_pct": 0.15,
            "max_sector_pct": 0.40,
            "min_cash_pct": 0.10,
            "max_positions": 10,
        },
    ).setup_graph()

    return graph


def _make_initial_state(run_id: str) -> dict:
    """Create a minimal initial state dict for the portfolio graph."""
    return {
        "portfolio_id": "portfolio-1",
        "analysis_date": "2026-05-01",
        "run_id": run_id,
        "prices": {},
        "scan_summary": {},
        "ticker_analyses": {},
        "messages": [],
        "portfolio_data": "",
        "risk_metrics": "",
        "holding_reviews": "",
        "prioritized_candidates": "",
        "macro_brief": "",
        "micro_brief": "",
        "macro_memory_context": "",
        "micro_memory_context": "",
        "pm_decision": "",
        "cash_sweep": "",
        "execution_result": "",
        "sender": "",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunIdSeeding:
    """Validates Requirements 4.1 and 4.2: run_id seeding into initial state."""

    def test_generates_uuid_when_run_id_not_provided(self):
        """PortfolioGraph.run() generates a valid UUID4 when run_id is omitted.

        Validates: Requirements 4.2
        """
        captured_state: dict = {}

        def fake_invoke(state):
            captured_state.update(state)
            return state

        pg = object.__new__(PortfolioGraph)
        pg.debug = False
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = fake_invoke
        pg.graph = mock_graph

        pg.run(
            portfolio_id="port-1",
            date="2026-05-01",
            prices={"AAPL": 200.0},
            scan_summary={"executive_summary": "test"},
        )

        run_id = captured_state.get("run_id")
        assert run_id is not None
        assert isinstance(run_id, str)
        assert len(run_id) > 0
        # Must be a valid UUID4
        parsed = uuid.UUID(run_id, version=4)
        assert str(parsed) == run_id

    def test_generates_unique_uuids_across_runs(self):
        """Each call to run() without run_id generates a distinct UUID.

        Validates: Requirements 4.2
        """
        captured_ids: list[str] = []

        def fake_invoke(state):
            captured_ids.append(state["run_id"])
            return state

        pg = object.__new__(PortfolioGraph)
        pg.debug = False
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = fake_invoke
        pg.graph = mock_graph

        for _ in range(5):
            pg.run(
                portfolio_id="port-1",
                date="2026-05-01",
                prices={},
                scan_summary={},
            )

        assert len(set(captured_ids)) == 5

    def test_provided_run_id_is_seeded_into_initial_state(self):
        """PortfolioGraph.run(run_id=...) seeds the exact value into state.

        Validates: Requirements 4.1
        """
        captured_state: dict = {}

        def fake_invoke(state):
            captured_state.update(state)
            return state

        pg = object.__new__(PortfolioGraph)
        pg.debug = False
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = fake_invoke
        pg.graph = mock_graph

        pg.run(
            portfolio_id="port-1",
            date="2026-05-01",
            prices={"AAPL": 200.0},
            scan_summary={"executive_summary": "test"},
            run_id="my-custom-run-id-42",
        )

        assert captured_state["run_id"] == "my-custom-run-id-42"


class TestRunIdPropagation:
    """Validates Requirement 4.3: run_id propagates to all downstream nodes."""

    def test_run_id_propagates_to_all_downstream_nodes(self):
        """run_id set in initial state reaches every node in the graph.

        Validates: Requirements 4.3
        """
        capture: dict[str, str | None] = {}
        graph = _build_graph_with_capture(capture)

        initial_state = _make_initial_state(run_id="propagation-test-run-001")
        graph.invoke(initial_state)

        # All captured nodes must have received the same run_id
        expected_nodes = {"review_holdings", "macro_summary", "micro_summary", "pm_decision"}
        for node_name in expected_nodes:
            assert node_name in capture, f"Node '{node_name}' did not execute"
            assert capture[node_name] == "propagation-test-run-001", (
                f"Node '{node_name}' received run_id={capture[node_name]!r}, "
                f"expected 'propagation-test-run-001'"
            )

    def test_generated_uuid_propagates_to_downstream_nodes(self):
        """Auto-generated UUID propagates consistently to all downstream nodes.

        Validates: Requirements 4.2, 4.3
        """
        capture: dict[str, str | None] = {}
        graph = _build_graph_with_capture(capture)

        # Use PortfolioGraph.run() to generate the UUID, then verify propagation
        captured_initial: dict = {}

        def fake_invoke(state):
            captured_initial.update(state)
            return state

        pg = object.__new__(PortfolioGraph)
        pg.debug = False
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = fake_invoke
        pg.graph = mock_graph

        pg.run(
            portfolio_id="port-1",
            date="2026-05-01",
            prices={},
            scan_summary={},
        )

        generated_run_id = captured_initial["run_id"]

        # Now run the real graph with the generated run_id
        initial_state = _make_initial_state(run_id=generated_run_id)
        graph.invoke(initial_state)

        # All nodes must see the same generated UUID
        for node_name, observed_run_id in capture.items():
            assert observed_run_id == generated_run_id, (
                f"Node '{node_name}' received run_id={observed_run_id!r}, "
                f"expected generated UUID '{generated_run_id}'"
            )

    def test_run_id_survives_parallel_fan_out(self):
        """run_id propagates correctly through parallel macro/micro summary fan-out.

        The portfolio graph has a parallel fan-out where macro_summary and
        micro_summary execute concurrently. run_id must survive this pattern.

        Validates: Requirements 4.3
        """
        capture: dict[str, str | None] = {}
        graph = _build_graph_with_capture(capture)

        initial_state = _make_initial_state(run_id="fan-out-test-run")
        graph.invoke(initial_state)

        # Both parallel branches must receive the same run_id
        assert capture.get("macro_summary") == "fan-out-test-run"
        assert capture.get("micro_summary") == "fan-out-test-run"

        # The fan-in node (pm_decision) must also receive it
        assert capture.get("pm_decision") == "fan-out-test-run"

    def test_run_id_present_in_final_state(self):
        """run_id is present in the final state returned by graph.invoke().

        Validates: Requirements 4.3
        """
        capture: dict[str, str | None] = {}
        graph = _build_graph_with_capture(capture)

        initial_state = _make_initial_state(run_id="final-state-test-run")
        result = graph.invoke(initial_state)

        assert result.get("run_id") == "final-state-test-run"
