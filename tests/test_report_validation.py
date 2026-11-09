"""Analyst report validation (§7) — the constraint in code, not in a prompt.

Telling a model "do not calculate" is not enforcement. These tests pin what
the code does instead: it reads the report, extracts the figures that carry a
label, and checks them against the run's certified metrics.

Two behaviours are deliberately distinct, because conflating them broke the
valid path during development:

- A figure the engine computed and the report got **wrong** blocks. That is a
  contradiction, and nothing downstream can be trusted.
- A figure with **no** certified counterpart does not block by itself, and is
  reported as `is_validated: False`. Before any metric is registered every
  labelled number would be unverifiable, so blocking on those would fail every
  run — including the valid path the contract requires to work.
"""

from __future__ import annotations

from tradingagents.dataflows.math.metric_record import metric
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.report_validation import validate_analyst_report


def _registry(**metrics) -> MetricRegistry:
    registry = MetricRegistry(run_id="test")
    for name, value in metrics.items():
        unit = "percent" if name.startswith("distance") else "multiple"
        registry.register(metric(name, value, unit=unit, formula_id=f"{name}_formula"))
    return registry


class TestContradictionsBlock:
    def test_a_wrong_price_to_book_blocks(self):
        registry = _registry(price_to_book="1.5877")
        validation = validate_analyst_report(
            "The shares trade at a P/B of 1.35x.", agent="fundamentals",
            registry=registry)
        assert validation.blocks_decision is True
        assert "price_to_book" in validation.codes

    def test_a_wrong_percentage_blocks(self):
        registry = _registry(distance_from_sma="14.7003")
        validation = validate_analyst_report(
            "It sits 4.5% above SMA200.", agent="market", registry=registry)
        assert validation.blocks_decision is True

    def test_a_correct_report_does_not_block(self):
        registry = _registry(price_to_book="1.5877",
                             distance_from_sma="14.7003")
        validation = validate_analyst_report(
            "P/B of 1.5877x and 14.7% above SMA200.",
            agent="fundamentals", registry=registry)
        assert validation.blocks_decision is False
        assert validation.is_validated is True

    def test_the_claim_is_kept_with_both_values(self):
        """The audit shows what was claimed and what was computed."""
        registry = _registry(price_to_book="1.5877")
        validation = validate_analyst_report(
            "P/B of 1.35x.", agent="fundamentals", registry=registry)
        payload = validation.summary()
        claim = payload["claims"][0]
        assert claim["value"] == "1.35"
        assert claim["computed_value"] == "1.5877"
        assert claim["verdict"] == "MISMATCH"


class TestNoRegistryDoesNotOverblock:
    def test_without_a_registry_nothing_blocks(self):
        """The valid path must survive: an empty registry checks nothing."""
        validation = validate_analyst_report(
            "4.5% above SMA200. P/B of 1.35x.", agent="market", registry=None)
        assert validation.blocks_decision is False

    def test_the_report_states_it_was_not_validated(self):
        """An unattempted check is not a pass, and says so."""
        validation = validate_analyst_report(
            "4.5% above SMA200.", agent="market", registry=None)
        assert validation.is_validated is False
        assert validation.summary()["registry_present"] is False

    def test_the_claims_are_still_reported(self):
        validation = validate_analyst_report(
            "4.5% above SMA200.", agent="market", registry=None)
        assert len(validation.claims.results) == 1
        assert validation.claims.results[0].verdict.value == "NOT_CHECKABLE"

    def test_an_empty_registry_behaves_like_none(self):
        validation = validate_analyst_report(
            "P/B of 1.35x.", agent="fundamentals",
            registry=MetricRegistry(run_id="empty"))
        assert validation.blocks_decision is False
        assert validation.is_validated is False


class TestExtractionScope:
    def test_an_unlabelled_figure_is_not_invented(self):
        """A bare number carries no metric identity and is not extracted."""
        validation = validate_analyst_report(
            "The stock rose 3.2 today on heavy volume.", agent="market",
            registry=_registry(price_to_book="1.5877"))
        assert validation.claims.results == []

    def test_an_empty_report_yields_nothing(self):
        for report in (None, ""):
            validation = validate_analyst_report(
                report, agent="market", registry=_registry(price_to_book="1.5"))
            assert validation.claims.results == []
            assert validation.blocks_decision is False

    def test_multiple_contradictions_are_all_reported(self):
        registry = _registry(price_to_book="1.5877",
                             distance_from_sma="14.7003")
        validation = validate_analyst_report(
            "P/B of 1.35x while 4.5% above SMA200.", agent="market",
            registry=registry)
        assert validation.blocks_decision is True
        assert set(validation.codes) == {"price_to_book", "distance_from_sma"}
