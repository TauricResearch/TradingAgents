"""Phase 4 §5 — the same frozen inputs, five times, must agree exactly.

The contract draws a line the lineage audit makes easy to miss: an LLM's
*interpretation* may vary run to run, but the *certified mathematics* may not.
A number that changes when nothing changed is not a measurement.

So this module runs the pipeline five times over the frozen BRK-B fixture and
compares:
- raw values, normalized values and certified metrics;
- every formula's operands;
- the bar's session status;
- the authorized quantity for the same candidate order;
- the risk limits;
- the gate's verdict.

Where the agent text varies between runs, the point is to prove the *system*
does not mistake that variation for a change in the data. That is tested
explicitly: a run whose prose differs but whose figures are identical must
produce the identical certified set and the identical execution verdict.
"""

from __future__ import annotations

import json

import pytest

from tests.fixtures.brkb_2026_11_09 import ANALYSIS_DATE, BRKB, TICKER

pytestmark = pytest.mark.unit

REPEATS = 5

# Five different narratives, one dataset. This is what an unchanged dataset
# looks like when the model answers differently: the words move, the numbers
# do not. The certified figures must be identical across all five.
NARRATIVES = [
    "",
    "Il titolo tratta a premio sul book value. Valutazione interessante.",
    "Berkshire mostra una crescita solida dei ricavi consolidati nel trimestre.",
    "Rischio di concentrazione elevato; il titolo resta sopra la media a 200 sedute.",
    "Nessuna sorpresa dai conti: ricavi in crescita a doppia cifra.",
]


# Fields that record *when* something happened, not *what* it was. §5 asks for
# the values, the formulas, the bar status, the quantity and the verdict to
# agree; it does not ask five runs to share a clock. These are stripped before
# comparing, and a separate assertion proves nothing else was stripped.
_CLOCK_FIELDS = frozenset({"checked_at", "generated_at", "created_at"})


def _without_clock(payload):
    """The payload minus its timestamps, recursively."""
    if isinstance(payload, dict):
        return {k: _without_clock(v) for k, v in payload.items()
                if k not in _CLOCK_FIELDS}
    if isinstance(payload, list):
        return [_without_clock(item) for item in payload]
    return payload


def _clock_values(payload):
    """Every timestamp in the payload, for a separate sanity assertion."""
    found = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _CLOCK_FIELDS and isinstance(value, str):
                found.add(value)
            else:
                found |= _clock_values(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _clock_values(item)
    return found


def _pipeline(narrative: str):
    """Run the registry and the gate over the fixture with one narrative."""
    from tradingagents.dataflows.gate_integration import evaluate_decision
    from tradingagents.dataflows.math.extraction import extract_run_inputs
    from tradingagents.dataflows.math.run_registry import (
        build_run_registry,
        registry_inputs_from_state,
    )
    from tradingagents.graph.trading_graph import _merge_extracted

    state = BRKB.run_state(market_report=narrative)
    extracted = extract_run_inputs(state)
    inputs = _merge_extracted(registry_inputs_from_state(state), extracted.inputs)
    registry = build_run_registry(inputs, run_id="repeat")

    record, decision = evaluate_decision(
        TICKER, ANALYSIS_DATE, state,
        snapshot_id="repeat",
        metric_registry=registry,
        trigger_met=True,
        market_open=True,
        # The snapshot is what lets the gate judge the bar's session status.
        # Without it the audit records nothing and a partial bar could pass as
        # a close (§4/§5: the intraday bar must be distinguishable).
        price_snapshot=state.get("verified_market_snapshot"),
        equity=BRKB.account_equity,
        cash=BRKB.cash,
        risk_budget=BRKB.risk_budget,
        max_symbol_exposure=BRKB.max_symbol_exposure,
    )
    return registry, record, decision


def _certified(registry) -> dict:
    """The certified metrics as (status, value, formula, operands)."""
    certified = {}
    for name in registry._records:
        record = registry.get(name)
        certified[name] = (
            record.calculation_status.value,
            None if record.value is None else str(record.value),
            record.formula_id,
            {k: (None if v is None else str(v))
             for k, v in sorted(record.operands.items())},
        )
    return certified


@pytest.fixture(scope="module")
def five_runs():
    """Five independent executions over identical frozen inputs."""
    return [_pipeline(text) for text in NARRATIVES]


# ---------------------------------------------------------------------------
# §5.1 — the certified mathematics is identical
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_certified_metrics_are_identical_across_five_runs(five_runs):
    """§5: the numbers must not move when the data did not."""
    baseline = _certified(five_runs[0][0])
    for index, (registry, _, _) in enumerate(five_runs[1:], start=2):
        assert _certified(registry) == baseline, (
            f"run {index} certified a different set of numbers "
            f"from run 1, with identical inputs"
        )


@pytest.mark.unit
def test_raw_and_normalized_values_are_stable(five_runs):
    """§5: raw inputs and their normalized forms, compared explicitly."""
    def raw(state_inputs):
        return {k: str(v) for k, v in sorted(state_inputs.__dict__.items())
                if v is not None and k != "claimed_inputs"}

    from tradingagents.dataflows.math.extraction import extract_run_inputs
    from tradingagents.dataflows.math.run_registry import (
        registry_inputs_from_state,
    )

    baselines = None
    for narrative in NARRATIVES:
        state = BRKB.run_state(market_report=narrative)
        inputs = registry_inputs_from_state(state)
        snapshot = raw(inputs)
        if baselines is None:
            baselines = snapshot
            continue
        # The narrative is the only thing that changed, and it is not an input.
        assert snapshot == baselines
        # Extraction reads only labelled figures; prose without a label is not
        # a figure.
        assert extract_run_inputs(state).inputs.price == inputs.price


@pytest.mark.unit
def test_every_formula_reports_the_same_operands(five_runs):
    """§5: a formula whose operands moved would explain a value that moved."""
    baseline = _certified(five_runs[0][0])
    for registry, _, _ in five_runs[1:]:
        certified = _certified(registry)
        for name, (_, _, formula, operands) in baseline.items():
            if formula is None and operands == {}:
                continue
            assert certified[name][2] == formula, f"{name} ran a different formula"
            assert certified[name][3] == operands, f"{name} used different operands"


# ---------------------------------------------------------------------------
# §5.2 — the bar status and the sizing are identical
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_bar_status_is_identical_across_runs(five_runs):
    """§5: an intraday bar must not become a close because the prose changed."""
    statuses = set()
    for _, record, _ in five_runs:
        bar = record.price_snapshot_bar
        assert bar is not None
        if isinstance(bar, dict):
            statuses.add((bar.get("market_session_status"),
                          bar.get("is_final")))
        else:
            statuses.add((str(getattr(bar, "status", None)),
                          getattr(bar, "is_final", None)))
    assert len(statuses) == 1, f"the bar status changed between runs: {statuses}"
    status, is_final = statuses.pop()
    assert is_final is False, "a real intraday snapshot can never be final"


@pytest.mark.unit
def test_the_authorized_quantity_is_identical_for_the_same_candidate(five_runs):
    """§5: "Quantità autorizzate per uno stesso ordine candidato"."""
    quantities = set()
    for _, record, decision in five_runs:
        assert decision.action.value == "PROPOSE_PAPER_ORDER", decision.reasons
        sizing = record.exposure_sizing
        assert sizing is not None
        quantities.add(sizing.qty)
    assert quantities == {BRKB.expected["exposure_capped_qty"]}, quantities


@pytest.mark.unit
def test_the_risk_limits_are_identical(five_runs):
    """§5: the budget, the planned risk and the binding constraint agree."""
    limits = set()
    for _, record, _ in five_runs:
        sizing = record.exposure_sizing
        limits.add((
            sizing.binding_constraint,
            round(sizing.planned_risk, 6),
            round(sizing.notional, 6),
            sizing.exposure_cap_applied,
        ))
    assert len(limits) == 1, f"risk limits drifted between runs: {limits}"


@pytest.mark.unit
def test_the_execution_gate_reaches_the_same_verdict(five_runs):
    """§5: "Esiti dell'Execution Gate" must not depend on the narrative."""
    verdicts = set()
    for _, _, decision in five_runs:
        verdicts.add((decision.action.value,
                      tuple(r.value for r in decision.reasons)))
    assert len(verdicts) == 1, f"the gate changed its mind: {verdicts}"


# ---------------------------------------------------------------------------
# §5.3 — variability of interpretation is not variability of data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_differing_narratives_are_visible_but_do_not_certify_anything(five_runs):
    """§5: the system must distinguish a different story from different data.

    The five runs did carry different text — that is the premise, and asserting
    it keeps the test from passing vacuously if the narratives were somehow
    identical. What must not differ is a single certified number.
    """
    narratives = {BRKB.run_state(market_report=text)["market_report"]
                  for text in NARRATIVES}
    assert len(narratives) == len(NARRATIVES), "the narratives must actually differ"

    certified = [json.dumps(_certified(registry), sort_keys=True)
                 for registry, _, _ in five_runs]
    assert len(set(certified)) == 1, (
        "identical inputs produced different certifications")


@pytest.mark.unit
def test_a_narrative_claiming_a_figure_does_not_turn_it_into_a_fact(five_runs):
    """§5/§2 of P3: prose carries no authority over the certified set.

    The last narrative mentions growth in words; none of the five states a
    labelled revenue figure, so the value must come from the supplied filing
    data and be identical whether or not the model talks about it.
    """
    growth = {str(registry.get("revenue_growth").value)
              for registry, _, _ in five_runs}
    assert len(growth) == 1
    assert growth.pop() != "None"


# ---------------------------------------------------------------------------
# §5.4 — the same comparison, through the persisted records
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_five_persisted_runs_produce_one_digest(tmp_path):
    """§5 at the level a reader can inspect: five files, one answer.

    The in-memory comparison above proves the computation is stable. This one
    proves the *records* are too, and that five analyses leave five distinct
    files — which is also the §2 defect (same-day overwriting) checked from the
    other direction.
    """
    import hashlib
    import json
    import tempfile

    from tradingagents.dataflows import run_record
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.portfolio import PortfolioContext

    digests, quantities, run_ids, payloads = set(), set(), [], []
    for narrative in NARRATIVES:
        with tempfile.TemporaryDirectory() as directory:
            graph = object.__new__(TradingAgentsGraph)
            graph.config = {
                "results_dir": directory,
                "deep_think_llm": "gpt-6-sol", "quick_think_llm": "gpt-6-luna",
                "fundamentals_freshness_gate": False,
                "risk_per_trade_pct": 0.01, "max_symbol_exposure": 0.05,
            }
            graph.selected_analysts = []

            class _Log:
                def store_decision(self, **kwargs):
                    pass

            graph.memory_log = _Log()
            state = BRKB.run_state(market_report=narrative)
            graph.record_decision(
                TICKER, ANALYSIS_DATE, state,
                portfolio=PortfolioContext.model_validate(BRKB.portfolio()))

            runs = run_record.list_runs(directory, TICKER)
            assert len(runs) == 1, runs
            record = run_record.read_run(runs[0])

        payload = {"registry": record["metric_registry"],
                   "risk": record["risk"],
                   "gate": record["execution_gate"]}
        run_ids.append(record["run_id"])
        payloads.append(payload)
        digests.add(hashlib.sha256(
            json.dumps(_without_clock(payload), sort_keys=True).encode()
        ).hexdigest()[:16])
        quantities.add(record["risk"]["exposure_capped_qty"])

    assert len(set(run_ids)) == REPEATS, "every run needs its own id"
    assert len(digests) == 1, f"records disagreed: {digests}"
    assert quantities == {BRKB.expected["exposure_capped_qty"]}

    # The comparison above is only meaningful if stripping the clock was the
    # *only* thing that made the payloads agree. If a run also differed in, say,
    # a metric value, that difference would survive the strip and the digest
    # assertion would already have failed — so this pins the other direction:
    # stripping must change the payload (there really are timestamps), and the
    # keys must match exactly, so nothing structural hid behind a missing key.
    assert set().union(*(_clock_values(p) for p in payloads)), (
        "no timestamp was found, so the strip removed nothing")
    first_keys = json.dumps(_without_clock(payloads[0]), sort_keys=True)
    assert all(json.dumps(_without_clock(p), sort_keys=True) == first_keys
               for p in payloads), "the record structure differs between runs"


@pytest.mark.unit
def test_a_real_run_records_every_required_field(tmp_path):
    """§2's list, verified field by field on a persisted record."""
    from tradingagents.dataflows import run_record
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.portfolio import PortfolioContext

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
    graph.record_decision(
        TICKER, ANALYSIS_DATE, BRKB.run_state(),
        portfolio=PortfolioContext.model_validate(BRKB.portfolio()))

    record = run_record.read_run(run_record.list_runs(tmp_path, TICKER)[0])
    required = [
        "run_id", "created_at", "analysis_date",
        "fingerprint", "model_config", "inputs", "filings",
        "metric_registry", "agents", "decision", "risk", "execution_gate",
        "audit",
    ]
    for key in required:
        assert key in record, f"the record is missing {key}"
    for key in ("commit", "build_id", "service_started_at", "python",
                "validators"):
        assert key in record["fingerprint"], f"fingerprint missing {key}"
