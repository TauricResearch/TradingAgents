"""Phase 3 — the deterministic math engine, wired end to end.

The engine's modules were correct and unused: a valuation multiple had no
caller, extraction read state keys no node wrote, and sizing was skipped
without recording why. Every test here therefore drives a *pipeline* — the
graph that builds the registry, the gate that consumes it, the audit that
records it — rather than calling an isolated function. A unit test over a
module nothing loads is a green test over nothing.

§7 of the task mandates sixteen cases; each names the number it covers.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.math.extraction import extract_run_inputs, from_report
from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    SourceStatus,
)
from tradingagents.dataflows.math.run_registry import RunInputs, build_run_registry
from tradingagents.graph.trading_graph import TradingAgentsGraph, _merge_extracted
from tradingagents.portfolio import PortfolioContext

# A run with a certified price and a book value the filing states. The price
# comes from the recorded snapshot, so extraction treats it as a fact.
BRKB_CERTIFIED = {
    "company_of_interest": "BRK-B",
    "trade_date": "2026-11-09",
    "verified_market_snapshot": {"close": 576.74, "sma200": 502.85},
    "market_report": "",
    "sentiment_report": "",
    "news_report": "",
    "fundamentals_report": "",
    "investment_plan": "",
    "investment_debate_state": {
        "bull_history": "", "bear_history": "",
        "history": "", "current_response": "",
    },
    "risk_debate_state": {
        "aggressive_history": "", "conservative_history": "",
        "neutral_history": "", "history": "",
    },
}



def _latest_audit(tmp_path) -> str:
    """The audit of the single run this test made.

    Audits are run-scoped since §2 of P4 (date plus run id), so a test that
    pinned the dated filename would assert the very overwriting behaviour the
    change removed.
    """
    audits = sorted((tmp_path / "BRK-B" / "reliability_audit").glob("audit_*.json"))
    assert len(audits) == 1, f"expected one audit, got {audits}"
    return audits[0].read_text()

def _graph(tmp_path, **overrides) -> TradingAgentsGraph:
    """A graph with only the collaborators the registry path touches."""
    graph = object.__new__(TradingAgentsGraph)
    config = {
        "results_dir": str(tmp_path),
        "deep_think_llm": "m",
        "quick_think_llm": "m",
        "fundamentals_freshness_gate": False,
        "risk_per_trade_pct": 0.01,
        "max_symbol_exposure": 0.05,
    }
    config.update(overrides)
    graph.config = config
    graph.selected_analysts = []

    class _Log:
        def store_decision(self, **kwargs):
            pass

    graph.memory_log = _Log()
    return graph


# ---------------------------------------------------------------------------
# 1-2. Price-to-book: computed from certified inputs, refused when the class
#      or the period disagree.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_1_price_to_book_is_computed_from_certified_inputs(tmp_path):
    """§7.1 — the multiple comes from arithmetic, not from the model.

    The report itself states no P/B at all: the number exists only because the
    engine divided. That is the difference between F2's four inconsistent
    values and one reproducible one.
    """
    state = dict(BRKB_CERTIFIED)
    state.update({
        "equity": 800_000_000_000.0,
        "shares_class_a": 550_000.0,
        "shares_class_b": 1_400_000_000.0,
        "class_a_to_b_ratio": 1500.0,
        "price_class": "B",
        "currency": "USD",
        "book_value_per_share": 359.5599,
    })
    registry = _graph(tmp_path)._build_metric_registry("BRK-B", "2026-11-09", state)

    assert registry is not None
    record = registry.get("price_to_book")
    assert record is not None
    assert record.calculation_status is CalculationStatus.VERIFIED
    assert record.source_status is SourceStatus.VERIFIED
    assert record.is_usable
    # 576.74 / 359.5506: the reported 1.73x does not reproduce.
    assert 1.60 <= float(record.value) <= 1.62


@pytest.mark.unit
def test_2_a_class_mismatched_book_value_is_refused_not_reported(tmp_path):
    """§7.2 — the A/B ratio applied the wrong way yields ~0.001x.

    ``reconcile_valuation`` refuses the pair; the registry must record the
    refusal rather than publish the plausible-looking quotient.
    """
    from tradingagents.dataflows.math.run_registry import build_run_registry

    registry = build_run_registry(RunInputs(
        price=576.74,
        equity=800_000_000_000.0,
        shares_class_a=550_000.0,
        shares_class_b=1_400_000_000.0,
        class_a_to_b_ratio=1500.0,
        price_class="A",
        currency="USD",
        # A class-B book value quoted against a class-A price.
        book_value_per_share=0.2397,
    ), run_id="mismatch")

    record = registry.get("price_to_book")
    assert record is not None
    assert record.is_usable is False
    assert record.calculation_status is not CalculationStatus.VERIFIED


# ---------------------------------------------------------------------------
# 3-4. EPS: reconciled against a GAAP denominator, or refused.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_3_eps_is_reconciled_against_the_weighted_average_count():
    """§7.3 — with a denominator the EPS gets a basis and a formula."""
    registry = build_run_registry(RunInputs(
        price=576.74, eps_ttm=39.76, weighted_average_shares=1_938_732_394.0,
    ), run_id="eps-ok")

    record = registry.get("eps_gaap")
    assert record is not None
    assert record.calculation_status is CalculationStatus.VERIFIED
    assert record.formula_id
    assert record.is_usable


@pytest.mark.unit
def test_4_eps_without_a_denominator_is_unsupported_and_blocks():
    """§7.4 — an unreconciled EPS is not a fact, so neither is its P/E."""
    registry = build_run_registry(RunInputs(
        price=576.74, eps_ttm=39.76,
    ), run_id="eps-missing")

    eps = registry.get("eps_gaap")
    assert eps.calculation_status is CalculationStatus.UNSUPPORTED
    assert eps.is_usable is False

    # F3's second half: the P/E used to be certified from that same EPS.
    multiple = registry.get("pe_trailing")
    assert multiple.is_usable is False
    assert "weighted-average" in multiple.reason
    assert registry.blocks_decision is True


# ---------------------------------------------------------------------------
# 5-6. The formula is recorded, and the registry is populated.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_5_every_certified_metric_carries_its_formula_and_operands():
    """§7.5 — a number without its formula cannot be reproduced."""
    registry = build_run_registry(RunInputs(
        price=576.74, book_value_per_share=359.5599,
        eps_ttm=39.76, eps_forward=22.43,
    ), run_id="formula")

    certified = [r for r in registry._records.values() if r.value is not None]
    assert certified, "the run had inputs, so something must be computable"
    for record in certified:
        assert record.formula_id, f"{record.metric} has no formula"
        assert record.operands, f"{record.metric} has no operands"


@pytest.mark.unit
def test_6_the_registry_is_populated_from_a_real_report(tmp_path):
    """§7.6 — extraction reaches the registry, not just its own test.

    The labelled figures the analysts wrote are the only valuation inputs
    available until they emit structured metrics; before Phase 3 the registry
    read state keys no node ever wrote, so every multiple was NOT_COMPUTABLE.
    """
    state = dict(BRKB_CERTIFIED)
    state["market_report"] = "P/B circa 1,73x. EPS TTM 39,76. EPS forward 22,43."
    state["fundamentals_report"] = "Book value per share 359,5599 USD."

    registry = _graph(tmp_path)._build_metric_registry("BRK-B", "2026-11-09", state)

    assert registry is not None
    assert registry.get("price_to_book").value is not None
    assert registry.get("eps_change").value is not None
    assert len([r for r in registry._records.values() if r.value is not None]) >= 2


# ---------------------------------------------------------------------------
# 7-8. The agents see the registry, and cannot override it numerically.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_7_the_registry_reaches_the_agents_as_tools():
    """§7.7 — a registry the agents cannot read cannot constrain them."""
    from tradingagents.agents import math_tools

    names = {tool.name for tool in math_tools.MATH_TOOLS}
    assert "get_certified_metric" in names
    assert "validate_stated_multiple" in names
    # The run's own registry is what the tool consults.
    assert hasattr(math_tools, "set_run_registry")


@pytest.mark.unit
def test_8_a_model_authored_figure_is_never_a_certified_fact():
    """§7.8 — a BVPS the model wrote is a claim, not a computation.

    This is F2 itself: the engine can divide two numbers the model invented
    and produce a perfect 1.73x. The arithmetic verifies; the *source* does
    not, and ``is_usable`` must say so.
    """
    registry = build_run_registry(RunInputs(
        price=576.74,
        book_value_per_share=359.5599,
        claimed_inputs=("book_value_per_share",),
    ), run_id="claimed")

    record = registry.get("price_to_book")
    assert record.calculation_status is CalculationStatus.VERIFIED
    assert record.source_status is SourceStatus.LLM_CLAIMED
    assert record.is_usable is False, "a model's own number must not certify"


@pytest.mark.unit
def test_8b_claimed_inputs_survive_the_merge_with_state():
    """The provenance must not be lost when the two sources are combined."""
    base = RunInputs(price=576.74)
    extracted = extract_run_inputs({
        "fundamentals_report": "Book value per share 359,5599 USD.",
    })
    assert "book_value_per_share" in extracted.inputs.claimed_inputs

    merged = _merge_extracted(base, extracted.inputs)
    assert "book_value_per_share" in merged.claimed_inputs
    assert merged.book_value_per_share == pytest.approx(359.5599)


# ---------------------------------------------------------------------------
# 9-12. Risk per share, ATR/stop, sizing, concentration.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_9_risk_per_share_is_the_stop_distance():
    """§7.9 — the per-share risk is entry minus stop, exactly."""
    from tradingagents.dataflows.risk_engine import validate_stop

    result = validate_stop(576.0, 555.0, 9.524)
    assert result.blocked is False
    assert result.distance == pytest.approx(21.0)


@pytest.mark.unit
def test_10_a_stop_inside_the_atr_buffer_blocks():
    """§7.10 — a stop closer than the minimum ATR multiple protects nothing."""
    from tradingagents.dataflows.risk_engine import validate_stop

    result = validate_stop(576.0, 574.0, 9.524)
    assert result.blocked is True
    assert result.atr_multiple < result.min_atr


@pytest.mark.unit
def test_11_sizing_produces_a_quantity_from_a_real_book(tmp_path):
    """§7.11 — F4: the quantity exists and reaches the audit.

    Before Phase 3 the audit reported ``qty_proposed: null`` for every run
    because ``PortfolioContext`` had no ``equity`` field and the key was
    dropped in silence, so the engine never received a capital base.
    """
    graph = _graph(tmp_path)
    book = PortfolioContext.model_validate(
        {"cash": 50_000.0, "equity": 100_000.0, "currency": "USD", "positions": []})
    state = dict(BRKB_CERTIFIED)
    state.update({
        "trader_investment_plan": "Entry 576.0, stop 555.0, ATR 9.524.",
        "final_rating": "Overweight",
        "final_trade_decision": "Buy.",
    })

    graph.record_decision("BRK-B", "2026-11-09", state, portfolio=book)

    audit = json.loads(_latest_audit(tmp_path))
    risk = audit["risk"]
    assert risk["qty_proposed"] is not None and risk["qty_proposed"] > 0
    assert risk["planned_risk"] > 0
    assert risk["exposure_capped_qty"] == risk["qty_proposed"]


@pytest.mark.unit
def test_12_the_per_symbol_cap_binds_before_the_risk_budget(tmp_path):
    """§7.12 — concentration, not the stop, decides the size here.

    100k equity, 1% budget, entry 576 stop 555: the stop allows 47 shares,
    the 5% cap allows 8. The cap must win and be named.
    """
    graph = _graph(tmp_path)
    book = PortfolioContext.model_validate(
        {"cash": 100_000.0, "equity": 100_000.0, "currency": "USD", "positions": []})
    state = dict(BRKB_CERTIFIED)
    state.update({
        "trader_investment_plan": "Entry 576.0, stop 555.0, ATR 9.524.",
        "final_rating": "Overweight",
        "final_trade_decision": "Buy.",
    })

    graph.record_decision("BRK-B", "2026-11-09", state, portfolio=book)

    audit = json.loads(_latest_audit(tmp_path))
    risk = audit["risk"]
    assert risk["exposure_capped_qty"] == 8
    assert risk["exposure_binding_constraint"] == "EXPOSURE_CAP"
    assert risk["exposure_cap_applied"] is True


# ---------------------------------------------------------------------------
# 13-16. Fail-closed: no book, impossible action, wrong-side stop, bad metrics.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_13_a_missing_book_blocks_with_its_own_reason(tmp_path):
    """§7.13 — F4's second half: the cause must not hide behind another.

    The gate blocked before Phase 3 too, but on ``ENTRY_TRIGGER_NOT_MET``, so
    nothing distinguished "not yet" from "cannot be sized". The sizing must now
    run, fail, and say why.
    """
    graph = _graph(tmp_path)
    state = dict(BRKB_CERTIFIED)
    state.update({
        "trader_investment_plan": "Entry 576.0, stop 555.0, ATR 9.524.",
        "final_rating": "Overweight",
        "final_trade_decision": "Buy.",
    })

    graph.record_decision("BRK-B", "2026-11-09", state)   # no portfolio

    audit = json.loads(_latest_audit(tmp_path))
    assert audit["execution"]["action"] == "BLOCK"
    assert "PORTFOLIO_RISK_BUDGET_MISSING" in audit["execution"]["reason_codes"]


@pytest.mark.unit
def test_14_reducing_a_long_without_a_position_is_not_a_valid_action():
    """§7.14 — the action must be reachable from the stated position."""
    from tradingagents.dataflows.math.trade_actions import (
        PositionState,
        TradeAction,
        validate_trade_against_rating,
    )

    intent = validate_trade_against_rating(
        TradeAction.REDUCE_LONG, "Overweight",
        position=PositionState(known=True, quantity=0.0),
    )
    assert intent.blocks is True
    assert intent.is_executable is False


@pytest.mark.unit
def test_15_a_short_plan_with_a_stop_below_the_entry_is_refused():
    """§7.15 — a stop under a short protects nothing."""
    from tradingagents.dataflows.risk_engine import validate_stop_side

    result = validate_stop_side(entry=100.0, stop=95.0, direction="SHORT")
    assert result.has_errors


@pytest.mark.unit
def test_16_no_authorization_is_issued_on_an_invalid_metric(tmp_path):
    """§7.16 — the last line: a refused metric cannot become an order."""
    from tradingagents.dataflows.gate_integration import evaluate_decision

    state = dict(BRKB_CERTIFIED)
    state.update({
        "trader_investment_plan": "Entry 576.0, stop 555.0, ATR 9.524.",
        "final_rating": "Overweight",
        "final_trade_decision": "Buy.",
        "market_report": "P/B 1,73x.",
    })
    # A registry whose EPS could not be reconciled: it blocks.
    registry = build_run_registry(RunInputs(
        price=576.74, eps_ttm=39.76, book_value_per_share=359.5599,
        claimed_inputs=("eps_ttm", "book_value_per_share"),
    ), run_id="bad")

    record, decision = evaluate_decision(
        "BRK-B", "2026-11-09", state, snapshot_id="s16",
        metric_registry=registry, trigger_met=True, market_open=True,
        equity=100_000.0, cash=100_000.0, risk_budget=1_000.0,
        max_symbol_exposure=0.05,
    )

    assert decision.action.value == "BLOCK"
    assert record.execution_verdict is not None
    assert list(record.execution_verdict.authorized_orders) == []


# ---------------------------------------------------------------------------
# The extractor's own arithmetic, which every case above depends on.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("text, metric, expected", [
    ("EPS TTM 39,76, EPS Forward 22,43.", "eps_ttm", 39.76),
    ("EPS TTM 39,76, EPS Forward 22,43.", "eps_forward", 22.43),
    ("EPS TTM / Forward | 39,76 / 22,43", "eps_forward", 22.43),
    ("EPS atteso 22,43", "eps_forward", 22.43),
    ("P/B circa 1,73x", "price_to_book", 1.73),
    ("BVPS 359,56", "book_value_per_share", 359.56),
    # Four digits after the comma was read as a thousands group, inflating a
    # per-share value by four orders of magnitude.
    ("Book value per share 359,5599 USD", "book_value_per_share", 359.5599),
    ("Total revenue 105,647 million", "revenue_consolidated", 105_647_000_000.0),
])
def test_the_extractor_reads_labelled_figures_and_respects_scale(
        text, metric, expected):
    found = from_report(text, metric)
    assert found is not None, f"{metric} not read from {text!r}"
    assert found.value == pytest.approx(expected)


@pytest.mark.unit
def test_an_unlabelled_number_is_never_extracted():
    """The fail-closed direction: prose numbers are not facts."""
    assert from_report("The stock trades around 576,74 today.", "book_value_per_share") is None
    assert from_report("Revenue grew nicely.", "revenue_consolidated") is None


@pytest.mark.unit
def test_a_portfolio_with_an_unknown_key_is_rejected(tmp_path):
    """An input that decides sizing must not be dropped in silence.

    ``equity`` used to be an unknown key: Pydantic ignored it, sizing saw no
    capital base, and the only symptom was a null in the audit. A typo now
    fails at the edge.
    """
    path = tmp_path / "book.json"
    path.write_text(json.dumps({"cash": 1000.0, "equty": 50_000.0}))

    from tradingagents.portfolio import load_portfolio

    with pytest.raises(ValueError, match="portfolio"):
        load_portfolio(path)
