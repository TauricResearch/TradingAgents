"""Phase 4 §4 — the whole pipeline on a frozen BRK-B run.

The fixture in ``fixtures/brkb_2026_11_09.py`` supplies the inputs and the
expected values; the tests drive the real graph, the real registry and the real
gate. Nothing is stubbed except what the network would otherwise supply, and no
test asserts on prose an agent wrote: every assertion is on a number the code
computed or on a verdict the code reached.

That last constraint is the whole point. The lineage audit showed a report whose
narrative described "l'ultima chiusura verificata" while the bar was 3h20m short
of the close, and a P/B of 1.73x with no computation behind it. Reading the
narrative would have passed both. These tests read the numbers.
"""

from __future__ import annotations

import json

import pytest

from tests.fixtures.brkb_2026_11_09 import (
    ANALYSIS_DATE,
    BRKB,
    Q3_2025,
    Q3_2026,
    REVENUE_Q3_2025,
    REVENUE_Q3_2026,
    REVENUE_Q3_2026_NARROW,
    TICKER,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers: the pipeline, driven the way the graph drives it
# ---------------------------------------------------------------------------


def _registry(state: dict):
    """The registry the graph builds for this state."""
    from tradingagents.dataflows.math.extraction import extract_run_inputs
    from tradingagents.dataflows.math.run_registry import (
        build_run_registry,
        registry_inputs_from_state,
    )
    from tradingagents.graph.trading_graph import _merge_extracted

    extracted = extract_run_inputs(state)
    base = registry_inputs_from_state(state)
    return build_run_registry(
        _merge_extracted(base, extracted.inputs), run_id="p4-e2e")


def _gate(state: dict, registry, **kwargs):
    """The gate's decision and audit for this state."""
    from tradingagents.dataflows.gate_integration import evaluate_decision

    return evaluate_decision(
        TICKER, ANALYSIS_DATE, state,
        snapshot_id="p4-e2e",
        metric_registry=registry,
        equity=BRKB.account_equity,
        cash=BRKB.cash,
        risk_budget=BRKB.risk_budget,
        max_symbol_exposure=BRKB.max_symbol_exposure,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# §4.1 — consolidated revenue, and its growth
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_q3_2026_consolidated_revenue_is_the_consolidated_figure():
    """§4: revenue is 105,647 million, not the 74,322 component.

    The defective tag order took ``RevenueFromContractWithCustomerExcluding
    AssessedTax`` first, which reports the narrower scope. The fixture carries
    both values, exactly as the filing does, so a regression that flips the
    preference shows up here rather than in a reader's trust.
    """
    state = BRKB.run_state()
    registry = _registry(state)

    record = registry.get("revenue_growth")
    assert record is not None
    # The growth is only right if the numerator is the consolidated figure.
    assert REVENUE_Q3_2026 == 105_647_000_000.0
    assert REVENUE_Q3_2026 != REVENUE_Q3_2026_NARROW
    operands = record.operands
    assert float(operands["revenue"]) == REVENUE_Q3_2026
    assert float(operands["revenue_prior"]) == REVENUE_Q3_2025


@pytest.mark.unit
def test_q3_revenue_growth_matches_the_independent_calculation():
    """§4: (105,647 - 94,972) / 94,972 = 11.24%, computed here by hand."""
    registry = _registry(BRKB.run_state())

    record = registry.get("revenue_growth")
    assert record.is_usable, record.reason
    assert float(record.value) == pytest.approx(
        BRKB.expected["revenue_growth_pct"], abs=1e-3)


@pytest.mark.unit
def test_the_narrow_revenue_concept_would_give_a_different_answer():
    """The defect is detectable: the two concepts do not agree.

    If they did, this whole check would be unfalsifiable and worth nothing.
    """
    narrow_growth = (REVENUE_Q3_2026_NARROW - REVENUE_Q3_2025) / REVENUE_Q3_2025 * 100
    assert narrow_growth != pytest.approx(
        BRKB.expected["revenue_growth_pct"], abs=0.1)


# ---------------------------------------------------------------------------
# §4.2 — price-to-book from equity and share classes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_book_value_per_share_comes_from_equity_and_both_classes():
    """§4: 800e9 / 2.225e9 class-B-equivalent shares = 359.55."""
    registry = _registry(BRKB.run_state())

    record = registry.get("book_value_per_share_B")
    assert record is not None
    assert record.is_usable, record.reason
    assert float(record.value) == pytest.approx(
        BRKB.expected["book_value_per_share"], abs=0.01)


@pytest.mark.unit
def test_price_to_book_is_computed_and_disagrees_with_the_model():
    """§4: the computed 1.604x is not the 1.73x the report asserted.

    Both the 1.73x and the 0.00116x in the original report are reproduced here
    as the *claims*, so the test proves the gap is real rather than rounding.
    """
    registry = _registry(BRKB.run_state())

    computed = registry.get("price_to_book")
    assert computed.is_usable, computed.reason
    assert float(computed.value) == pytest.approx(
        BRKB.expected["price_to_book"], abs=1e-3)

    # The A/B conversion applied backwards yields ~0.00107x, and the report
    # carried "0,00116x": the same order of magnitude, and not even the exact
    # quotient — the model was doing its own arithmetic, which is the finding.
    inverted = BRKB.expected["class_ratio_inversion"]
    assert inverted == pytest.approx(0.0010694, abs=1e-6)
    assert inverted != pytest.approx(
        BRKB.expected["reported_price_to_book_ratio_error"], abs=1e-5)
    assert float(computed.value) != pytest.approx(
        BRKB.expected["reported_price_to_book"], abs=0.05)


# ---------------------------------------------------------------------------
# §4.3 — EPS: verified, or explicitly unverified
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_eps_without_a_share_count_is_reported_unverified_not_guessed():
    """§4: "EPS TTM verificato o UNVERIFIED".

    Two distinct absences, both honest: no EPS reported at all is
    NOT_COMPUTABLE, and an EPS with no denominator to reconcile it against is
    UNSUPPORTED. Neither may become a certified number.
    """
    from tradingagents.dataflows.math.metric_record import CalculationStatus
    from tradingagents.dataflows.math.run_registry import RunInputs, build_run_registry

    # No EPS in the run at all.
    absent = _registry(BRKB.run_state()).get("eps_gaap")
    assert absent.calculation_status is CalculationStatus.NOT_COMPUTABLE
    assert absent.is_usable is False

    # An EPS the model stated, with no weighted-average count behind it.
    unreconciled = build_run_registry(
        RunInputs(price=BRKB.price, eps_ttm=39.76), run_id="eps-no-count"
    ).get("eps_gaap")
    assert unreconciled.calculation_status is CalculationStatus.UNSUPPORTED
    assert unreconciled.value is None
    assert unreconciled.is_usable is False
    assert "weighted-average" in unreconciled.reason


@pytest.mark.unit
def test_a_supplied_share_count_makes_the_eps_verifiable():
    """The same run with a denominator certifies the EPS — both paths tested."""
    from tradingagents.dataflows.math.run_registry import RunInputs, build_run_registry

    registry = build_run_registry(RunInputs(
        price=BRKB.price, eps_ttm=39.76, weighted_average_shares=1_938_732_394.0,
    ), run_id="eps-ok")

    assert registry.get("eps_gaap").is_usable


# ---------------------------------------------------------------------------
# §4.4 — indicators, and the intraday bar
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_distance_from_the_200_day_average_is_arithmetically_right():
    """§4: indicators must be mathematically correct, not merely plausible."""
    registry = _registry(BRKB.run_state())

    record = registry.get("distance_from_sma200")
    assert record.is_usable
    expected = (BRKB.price - BRKB.sma200) / BRKB.sma200 * 100
    assert float(record.value) == pytest.approx(expected, abs=1e-4)


@pytest.mark.unit
def test_the_intraday_bar_is_not_certified_as_an_end_of_day_close():
    """§4: 12:37 New York is mid-session, so the Close is not a close.

    The original report called this "l'ultima chiusura verificata" and derived
    +24.2% and every indicator from it.
    """
    from tradingagents.dataflows.math.session import (
        SessionStatus,
        assess_bar,
        market_session_status,
    )

    status = market_session_status(
        BRKB.snapshot_instant, tz="America/New_York")
    assert status is SessionStatus.OPEN

    bar = assess_bar(BRKB.snapshot_instant, tz="America/New_York",
                     analysis_time=BRKB.snapshot_instant)
    assert bar.is_final is False
    assert bar.usable_as_close is False
    assert bar.blocks_confirmed_close_strategies is True


# ---------------------------------------------------------------------------
# §4.5 — the registry, the size, the authorization
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_metric_registry_is_populated_and_reports_its_verdicts():
    """§4: a registry with nothing in it cannot constrain a decision."""
    registry = _registry(BRKB.run_state())
    summary = registry.summary()

    assert summary["run_id"] == "p4-e2e"
    assert summary["metrics"], "the registry must list every metric it considered"
    names = {m["metric"] for m in summary["metrics"]}
    assert {"price_to_book", "revenue_growth", "eps_gaap"} <= names
    certified = [m for m in summary["metrics"]
                 if m.get("calculation_status") == "VERIFIED"]
    assert certified, "at least the multiples with inputs must certify"


@pytest.mark.unit
def test_the_quantity_is_determined_by_the_risk_engine_and_capped():
    """§4: floor(5000 / 576) = 8, not the 47 the stop distance alone allows."""
    state = BRKB.run_state()
    record, _ = _gate(state, _registry(state))

    sizing = record.exposure_sizing
    assert sizing is not None
    assert sizing.qty == BRKB.expected["exposure_capped_qty"]
    assert sizing.binding_constraint == BRKB.expected["binding_constraint"]
    # The stop-distance budget alone would have allowed 47: the cap is what
    # makes 8 the answer, and that is why both limits must run.
    assert BRKB.expected["risk_budget_qty"] == 47
    assert sizing.qty < BRKB.expected["risk_budget_qty"]


@pytest.mark.unit
def test_the_execution_gate_states_its_authorization_explicitly():
    """§4: the gate must answer, not merely not-crash.

    A plan with certified metrics can still wait: this run's trigger is unmet,
    which is a legitimate WAIT, not a refusal. What must never happen is an
    approval with no reasons or a block with no reasons.
    """
    from tradingagents.dataflows.gate_integration import evaluate_decision

    state = BRKB.run_state()
    registry = _registry(state)
    _, decision = _gate(state, registry)

    assert decision.action.value in {"WAIT", "BLOCK", "PROPOSE_PAPER_ORDER"}
    assert decision.reasons, "a verdict without reasons cannot be audited"

    # With the trigger met and the numbers sound, the same plan proposes.
    record, approved = evaluate_decision(
        TICKER, ANALYSIS_DATE, state,
        snapshot_id="p4-trigger", metric_registry=registry,
        trigger_met=True, market_open=True,
        equity=BRKB.account_equity, cash=BRKB.cash,
        risk_budget=BRKB.risk_budget,
        max_symbol_exposure=BRKB.max_symbol_exposure,
    )
    assert approved.action.value == "PROPOSE_PAPER_ORDER", approved.reasons
    verdict = record.execution_verdict
    assert verdict.execution_action == "PROPOSE_PAPER_ORDER"
    assert verdict.blocking_reasons == ()
    assert verdict.authorized_orders


# ---------------------------------------------------------------------------
# §4.6 — persistence: one record per run, nothing overwritten
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_finished_run_writes_an_independent_audit_record(tmp_path):
    """§4/§2: the run leaves a record that can be read back and reproduced."""
    from tradingagents.dataflows import run_record
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "results_dir": str(tmp_path),
        "deep_think_llm": "gpt-6-sol", "quick_think_llm": "gpt-6-luna",
        "fundamentals_freshness_gate": False,
        "risk_per_trade_pct": 0.01, "max_symbol_exposure": 0.05,
    }
    graph.selected_analysts = []

    class _Log:
        def store_decision(self, **kwargs):
            pass

    graph.memory_log = _Log()

    from tradingagents.portfolio import PortfolioContext

    book = PortfolioContext.model_validate(BRKB.portfolio())
    state = BRKB.run_state()
    graph.record_decision(TICKER, ANALYSIS_DATE, state, portfolio=book)

    runs = run_record.list_runs(tmp_path, TICKER)
    assert len(runs) == 1
    record = run_record.read_run(runs[0])

    # Everything §2 requires a run to keep.
    assert record["run_id"]
    assert record["created_at"]
    assert record["fingerprint"]["commit"]
    assert record["fingerprint"]["build_id"]
    assert record["fingerprint"]["service_started_at"]
    assert record["fingerprint"]["python"]
    assert record["fingerprint"]["validators"]
    assert record["model_config"]["deep_think_llm"] == "gpt-6-sol"
    assert record["inputs"]["portfolio"]["equity"] == BRKB.account_equity
    assert record["metric_registry"]["metrics"]
    assert record["decision"]["execution_action"]
    assert record["risk"]
    assert record["execution_gate"]
    assert record["audit"]["ticker"] == TICKER


@pytest.mark.unit
def test_two_runs_on_the_same_day_both_survive(tmp_path):
    """§2: this is the defect the phase exists to remove.

    Two analyses of one instrument on one date used to leave a single file.
    """
    from tradingagents.dataflows import run_record

    first = run_record.RunRecord(run_id=run_record.new_run_id(TICKER),
                                 ticker=TICKER, analysis_date=ANALYSIS_DATE)
    second = run_record.RunRecord(run_id=run_record.new_run_id(TICKER),
                                  ticker=TICKER, analysis_date=ANALYSIS_DATE)

    path_a = run_record.write_run(tmp_path, first)
    path_b = run_record.write_run(tmp_path, second)

    assert path_a != path_b
    assert path_a.exists() and path_b.exists()
    assert len(run_record.list_runs(tmp_path, TICKER)) == 2


@pytest.mark.unit
def test_a_run_record_is_never_overwritten(tmp_path):
    """A duplicate id is a bug; losing the earlier analysis is worse."""
    from tradingagents.dataflows import run_record

    record = run_record.RunRecord(run_id="fixed-id", ticker=TICKER,
                                  analysis_date=ANALYSIS_DATE)
    run_record.write_run(tmp_path, record)

    with pytest.raises(FileExistsError):
        run_record.write_run(tmp_path, record)


@pytest.mark.unit
def test_credentials_never_reach_a_run_record(tmp_path):
    """§2: redaction, including under an innocent key name."""
    from tradingagents.dataflows import run_record

    record = run_record.RunRecord(
        run_id=run_record.new_run_id(TICKER), ticker=TICKER,
        analysis_date=ANALYSIS_DATE,
        model_config={"llm_provider": "openai", "api_key": "sk-live-abcdef123456"},
        inputs={"note": "ghp_0123456789abcdefghij"},
    )
    path = run_record.write_run(tmp_path, record)
    text = path.read_text(encoding="utf-8")

    assert "sk-live-abcdef123456" not in text
    assert "ghp_0123456789abcdefghij" not in text
    assert run_record.REDACTED in text


@pytest.mark.unit
def test_a_huge_agent_report_is_truncated_visibly(tmp_path):
    """§2: bounded space, and the truncation is recorded rather than hidden."""
    from tradingagents.dataflows import run_record

    record = run_record.RunRecord(
        run_id=run_record.new_run_id(TICKER), ticker=TICKER,
        analysis_date=ANALYSIS_DATE,
        agents={"market": "x" * 5_000},
    )
    path = run_record.write_run(tmp_path, record, max_text_chars=100)
    stored = json.loads(path.read_text(encoding="utf-8"))["agents"]["market"]

    assert stored["truncated"] is True
    assert stored["chars"] == 5_000
    assert len(stored["text"]) == 100


@pytest.mark.unit
def test_retention_prunes_only_when_asked_and_never_the_newest(tmp_path):
    """§2: retention is explicit, and the latest evidence is never deleted."""
    from tradingagents.dataflows import run_record

    for _ in range(4):
        run_record.write_run(tmp_path, run_record.RunRecord(
            run_id=run_record.new_run_id(TICKER), ticker=TICKER,
            analysis_date=ANALYSIS_DATE))

    assert len(run_record.list_runs(tmp_path, TICKER)) == 4

    report = run_record.prune_runs(tmp_path, TICKER, keep=2)
    remaining = run_record.list_runs(tmp_path, TICKER)
    assert len(remaining) == 2
    assert len(report.deleted) == 2

    # Even a nonsensical limit cannot delete the only surviving evidence.
    run_record.prune_runs(tmp_path, TICKER, keep=0)
    assert len(run_record.list_runs(tmp_path, TICKER)) == 1


@pytest.mark.unit
def test_run_files_are_not_world_readable(tmp_path):
    """§2: an audit holds the caller's positions."""
    import os

    from tradingagents.dataflows import run_record

    path = run_record.write_run(tmp_path, run_record.RunRecord(
        run_id=run_record.new_run_id(TICKER), ticker=TICKER,
        analysis_date=ANALYSIS_DATE))

    mode = os.stat(path).st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# Fixture integrity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_fixture_periods_are_what_the_labels_claim():
    """A fixture that mislabels its own quarters would test nothing."""
    assert Q3_2026 == {"start": "2026-07-01", "end": "2026-09-30"}
    assert Q3_2025 == {"start": "2025-07-01", "end": "2025-09-30"}
    assert BRKB.revenue_q3_2026 > BRKB.revenue_q3_2025
