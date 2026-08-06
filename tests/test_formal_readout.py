from __future__ import annotations

import inspect
import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from tradingagents import formal_readout
from tradingagents.formal_readout import (
    FormalReadoutIntegrityError,
    build_formal_readout,
    materialize_final_verification_manifest,
    require_final_verification_manifest,
)
from tradingagents.outcome_semantics import (
    OutcomeSemanticsResolutionError,
    outcome_semantics_id,
)
from tradingagents.paper_trading import formal_price_capture_window, next_session_date
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)

RUN_ID = "global-event-v2-confirmatory-test"
STRATEGIES = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
TICKERS = list(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"])
BENCHMARK = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["benchmark"]
OUTCOME_SEMANTICS_ID = outcome_semantics_id()
CONFIGURATION_BINDING = {
    "configuration_manifest_id": "config_" + "1" * 24,
    "collector_configuration_id": "config_" + "2" * 24,
    "paper_decision_configuration_id": "config_" + "3" * 24,
    "paper_marker_configuration_id": "config_" + "4" * 24,
}


def _registration() -> dict:
    analysis = GLOBAL_EVENT_V2_PROTOCOL["analysis"]
    base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": RUN_ID,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "analysis_id": content_id(analysis, prefix="analysis_"),
        "review_gates_id": content_id(GLOBAL_EVENT_V2_PROTOCOL["review_gates"], prefix="reviews_"),
        "decision_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["forecast"][
            "expected_decision_semantics_id"
        ],
        "outcome_semantics_id": OUTCOME_SEMANTICS_ID,
        "configuration_binding": dict(CONFIGURATION_BINDING),
        "registered_strategies": STRATEGIES,
        "confirmatory_family": list(analysis["multiplicity"]["confirmatory_family"]),
        "secondary_family": list(analysis["multiplicity"]["secondary_family"]),
        "trial_clock": analysis["trial_clock"],
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    return {**base, "registration_id": content_id(base, prefix="registration_")}


class _OutcomeSemanticsGuardStore:
    def __init__(self, mutation: str):
        registration = _registration()
        self.config = {
            "outcome_semantics_id": OUTCOME_SEMANTICS_ID,
            "configuration_binding": dict(CONFIGURATION_BINDING),
            "trial_registration_id": registration["registration_id"],
        }
        self.registration = {
            "label": "confirmatory-trial",
            "created_utc": 1.0,
            "details": registration,
        }
        self.outcome_reads = 0
        if mutation == "missing":
            self.config.pop("outcome_semantics_id")
        elif mutation == "registration_disagreement":
            self.registration["details"]["outcome_semantics_id"] = (
                "outcome_semantics_" + "0" * 64
            )
        elif mutation == "installed_drift":
            drifted = "outcome_semantics_" + "0" * 64
            self.config["outcome_semantics_id"] = drifted
            self.registration["details"]["outcome_semantics_id"] = drifted
        else:
            raise AssertionError(mutation)

    def run_config(self, run_id):
        assert run_id == RUN_ID
        return deepcopy(self.config)

    def confirmatory_registration(self, run_id):
        assert run_id == RUN_ID
        return deepcopy(self.registration)

    def __getattr__(self, name):
        self.outcome_reads += 1
        raise AssertionError(
            f"outcome-semantics failure reached stored outcome access {name!r}"
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda store: build_formal_readout(store, RUN_ID),
            id="readout",
        ),
        pytest.param(
            lambda store: materialize_final_verification_manifest(
                store,
                RUN_ID,
                100.0,
            ),
            id="materialize-verification",
        ),
        pytest.param(
            lambda store: require_final_verification_manifest(
                store,
                RUN_ID,
                [],
            ),
            id="require-verification",
        ),
    ],
)
@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        ("missing", FormalReadoutIntegrityError, "disagree on outcome semantics"),
        (
            "registration_disagreement",
            FormalReadoutIntegrityError,
            "disagree on outcome semantics",
        ),
        (
            "installed_drift",
            OutcomeSemanticsResolutionError,
            "differ from preregistration",
        ),
    ],
)
def test_public_readout_paths_reject_outcome_semantics_before_outcome_reads(
    operation,
    mutation,
    error,
    message,
):
    store = _OutcomeSemanticsGuardStore(mutation)

    with pytest.raises(error, match=message):
        operation(store)

    assert store.outcome_reads == 0


def _sessions() -> list[str]:
    required = GLOBAL_EVENT_V2_PROTOCOL["analysis"]["trial_clock"]["holding_intervals"]
    sessions = ["2024-01-03"]
    while len(sessions) <= required:
        sessions.append(next_session_date(sessions[-1]))
    return sessions


def _decision_dates(sessions: list[str]) -> list[str]:
    return ["2024-01-02", *sessions[:-1]]


def _uniform_weights() -> dict[str, float]:
    return {ticker: 1.0 / len(TICKERS) for ticker in TICKERS}


def _raw_mark(
    session: str,
    *,
    captured: float,
    nav: float,
    benchmark_nav: float,
    period_return: float,
    benchmark_return: float,
    turnover: float,
    cost: float,
    weights: dict[str, float],
    target_decision_date: str | None,
    strategy: str | None,
    opens: dict[str, float] | None = None,
    benchmark_open: float = 400.0,
) -> dict:
    row = {
        "run_id": RUN_ID,
        "session_date": session,
        "captured_utc": captured,
        "nav": nav,
        "benchmark_nav": benchmark_nav,
        "period_return": period_return,
        "benchmark_period_return": benchmark_return,
        "turnover": turnover,
        "trading_cost": cost,
        "borrow_cost": 0.0,
        "weights_json": canonical_json(weights),
        "opens_json": canonical_json(opens or dict.fromkeys(TICKERS, 100.0)),
        "benchmark_open": benchmark_open,
        "target_decision_date": target_decision_date,
    }
    if strategy is not None:
        row["strategy_id"] = strategy
    return row


def _return_vector(start: str, end: str, captured: float, ordinal: int) -> dict:
    components = {}
    for symbol_index, symbol in enumerate([*TICKERS, BENCHMARK]):
        raw_return = ((ordinal + symbol_index) % 9 - 4) * 0.0002
        previous = 100.0 + symbol_index
        current = previous * (1.0 + raw_return)
        components[symbol] = {
            "price_receipt_id": content_id(
                {"session": end, "symbol": symbol, "kind": "receipt"},
                prefix="price_receipt_",
            ),
            "vendor_snapshot_id": content_id(
                {"session": end, "symbol": symbol, "kind": "snapshot"},
                prefix="price_snapshot_",
            ),
            "previous_adjusted_open": previous,
            "current_adjusted_open": current,
            "current_raw_open": current,
            "cash_dividend": 0.0,
            "split_ratio": 0.0,
            "open_return": current / previous - 1.0,
        }
    accrual_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    annual_yield = 3.6
    cash = {
        "instrument": "USD",
        "annual_yield_proxy": "^IRX",
        "observation_session": (date.fromisoformat(start) - timedelta(days=7)).isoformat(),
        "annual_yield_percent": annual_yield,
        "accrual_days": accrual_days,
        "day_count_basis": 360,
        "open_return": annual_yield / 100.0 * accrual_days / 360.0,
    }
    scheduled, deadline = formal_price_capture_window(end)
    captured = scheduled.timestamp() + 60.0
    base = {
        "schema_version": 2,
        "from_session": start,
        "to_session": end,
        "captured_utc": float(captured),
        "scheduled_utc": scheduled.timestamp(),
        "deadline_utc": deadline.timestamp(),
        "vendor": "yfinance",
        "components": components,
        "cash_component": cash,
    }
    return {"return_vector_id": content_id(base, prefix="return_vector_"), **base}


class FakeStore:
    def __init__(self):
        sessions = _sessions()
        decisions = _decision_dates(sessions)
        weights = _uniform_weights()
        registration = _registration()
        portfolio = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
        self.config = {
            "engine": "formal-global-v2",
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "tickers": TICKERS,
            "benchmark": BENCHMARK,
            "cost_bps": portfolio["trading_cost_bps"],
            "slippage_bps": portfolio["slippage_bps"],
            "annual_borrow_bps": 0.0,
            "cash_policy": portfolio["cash"],
            "outcome_semantics_id": OUTCOME_SEMANTICS_ID,
            "configuration_binding": dict(CONFIGURATION_BINDING),
            "trial_registration_id": registration["registration_id"],
        }
        self.registration = {
            "label": "confirmatory-trial",
            "created_utc": 1_699_999_000.0,
            "details": registration,
        }
        self.protocol_rows = [{"manifest_json": canonical_json(GLOBAL_EVENT_V2_PROTOCOL)}]
        self.strategy_ids = sorted(STRATEGIES)
        self.assignments = []
        self.vectors = {}
        self.official_targets = []
        self.strategy_targets = []
        self.champion_marks = []
        self.strategy_marks = []
        self.decision_attempt_events = []
        self.artifacts = {}
        self.write_calls = 0

        for session, decision in zip(sessions[:-1], decisions[:-1], strict=True):
            self.official_targets.append(
                {
                    "run_id": RUN_ID,
                    "decision_date": decision,
                    "entry_date": session,
                    "weights_json": canonical_json(weights),
                }
            )
            self.decision_attempt_events.append(
                {
                    "run_id": RUN_ID,
                    "decision_date": decision,
                    "entry_date": session,
                    "attempt_ordinal": 1,
                    "event_type": "started",
                    "created_utc": 1_699_000_000.0 + len(self.official_targets),
                    "reason_code": None,
                }
            )
            for strategy in STRATEGIES:
                self.strategy_targets.append(
                    {
                        "run_id": RUN_ID,
                        "decision_date": decision,
                        "strategy_id": strategy,
                        "entry_date": session,
                        "weights_json": canonical_json(weights),
                    }
                )

        rate = (self.config["cost_bps"] + self.config["slippage_bps"]) / 10_000
        initial_turnover = sum(weights.values())
        initial_cost = initial_turnover * rate
        state = {
            strategy: {
                "nav": 1.0 - initial_cost,
                "weights": dict(weights),
            }
            for strategy in STRATEGIES
        }
        benchmark_nav = 1.0
        initial_by_strategy = {}
        initial_scheduled, _initial_deadline = formal_price_capture_window(sessions[0])
        initial_captured = initial_scheduled.timestamp() + 60.0
        for strategy in STRATEGIES:
            initial_by_strategy[strategy] = _raw_mark(
                sessions[0],
                captured=initial_captured,
                nav=state[strategy]["nav"],
                benchmark_nav=benchmark_nav,
                period_return=-initial_cost,
                benchmark_return=0.0,
                turnover=initial_turnover,
                cost=initial_cost,
                weights=weights,
                target_decision_date=decisions[0],
                strategy=strategy,
            )
            self.strategy_marks.append(initial_by_strategy[strategy])
        self.champion_marks.append(
            deepcopy(
                {
                    key: value
                    for key, value in initial_by_strategy["global_events_champion"].items()
                    if key != "strategy_id"
                }
            )
        )

        for interval_index in range(1, len(sessions)):
            start = sessions[interval_index - 1]
            end = sessions[interval_index]
            captured = 1_700_000_000.0 + interval_index
            vector = _return_vector(start, end, captured, interval_index)
            captured = vector["captured_utc"]
            self.vectors[end] = vector
            self.assignments.append(
                {
                    "run_id": RUN_ID,
                    "interval_index": interval_index,
                    "from_session_date": start,
                    "session_date": end,
                    "scheduled_decision_date": decisions[interval_index - 1],
                    "created_utc": captured,
                    "disposition": "target_applied",
                    "applied_target_decision_date": decisions[interval_index - 1],
                    "return_vector_id": vector["return_vector_id"],
                }
            )
            benchmark_return = vector["components"][BENCHMARK]["open_return"]
            benchmark_nav *= 1.0 + benchmark_return
            end_by_strategy = {}
            for strategy in STRATEGIES:
                start_weights = state[strategy]["weights"]
                holding = sum(
                    start_weights[ticker] * vector["components"][ticker]["open_return"]
                    for ticker in TICKERS
                )
                cash_weight = max(0.0, 1.0 - sum(start_weights.values()))
                holding += cash_weight * vector["cash_component"]["open_return"]
                pre_trade = {
                    ticker: start_weights[ticker]
                    * (1.0 + vector["components"][ticker]["open_return"])
                    / (1.0 + holding)
                    for ticker in TICKERS
                }
                endpoint_has_target = interval_index < len(sessions) - 1
                turnover = (
                    sum(abs(weights[ticker] - pre_trade[ticker]) for ticker in TICKERS)
                    if endpoint_has_target
                    else 0.0
                )
                cost = turnover * rate
                stored_return = (1.0 + holding) * (1.0 - cost) - 1.0
                state[strategy]["nav"] *= 1.0 + stored_return
                state[strategy]["weights"] = dict(weights) if endpoint_has_target else pre_trade
                end_by_strategy[strategy] = _raw_mark(
                    end,
                    captured=captured,
                    nav=state[strategy]["nav"],
                    benchmark_nav=benchmark_nav,
                    period_return=stored_return,
                    benchmark_return=benchmark_return,
                    turnover=turnover,
                    cost=cost,
                    weights=state[strategy]["weights"],
                    target_decision_date=(
                        decisions[interval_index] if endpoint_has_target else None
                    ),
                    strategy=strategy,
                    opens={
                        ticker: vector["components"][ticker]["current_adjusted_open"]
                        for ticker in TICKERS
                    },
                    benchmark_open=vector["components"][BENCHMARK]["current_adjusted_open"],
                )
                self.strategy_marks.append(end_by_strategy[strategy])
            self.champion_marks.append(
                deepcopy(
                    {
                        key: value
                        for key, value in end_by_strategy["global_events_champion"].items()
                        if key != "strategy_id"
                    }
                )
            )

        self.counts = {
            "completed_intervals": len(self.assignments),
            "successful_decision_sets": len(self.assignments),
            "carry_forward_intervals": 0,
            "assignment_indices_contiguous": True,
            "assignment_dates_contiguous": True,
            "synchronized_marks": len(self.assignments),
        }
        decision_dates = [row["applied_target_decision_date"] for row in self.assignments]
        verifications = [
            {
                "decision_date": decision,
                "entry_date": next_session_date(decision),
                "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                "build_id": "build_fixture",
                "artifact_id": f"artifact_{index:024x}",
                "strategies_replayed": len(STRATEGIES),
                "external_calls": 0,
            }
            for index, decision in enumerate(decision_dates, start=1)
        ]
        price_capture_manifest_id = formal_readout._price_capture_operational_identity(
            self, RUN_ID, self.assignments
        )
        base = {
            "schema_version": 1,
            "manifest_type": "global-event-v2-final-offline-verification",
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "run_id": RUN_ID,
            "coverage_rule": "every-successful-applied-decision-exactly-once",
            "successful_applied_decisions": len(decision_dates),
            "decision_dates": decision_dates,
            "verifications": verifications,
            "external_calls_total": 0,
            "exact_coverage": True,
            "price_capture_manifest_id": price_capture_manifest_id,
        }
        manifest = {
            **base,
            "verification_manifest_id": content_id(base, prefix="formal_verification_"),
        }
        manifest_artifact_id = content_id(
            {
                "artifact_type": "formal_final_verification_manifest",
                "content": manifest,
            },
            prefix="artifact_",
        )
        self.artifacts[manifest_artifact_id] = {
            "artifact_id": manifest_artifact_id,
            "artifact_type": "formal_final_verification_manifest",
            "content_json": canonical_json(manifest),
        }

    def run_config(self, run_id):
        assert run_id == RUN_ID
        return deepcopy(self.config)

    def confirmatory_registration(self, run_id):
        assert run_id == RUN_ID
        return deepcopy(self.registration)

    def formal_strategies(self, run_id):
        assert run_id == RUN_ID
        return list(self.strategy_ids)

    def formal_trial_counts(self, run_id):
        assert run_id == RUN_ID
        return deepcopy(self.counts)

    def price_capture_operational_manifest(self, run_id):
        assert run_id == RUN_ID
        sessions = [
            self.assignments[0]["from_session_date"],
            *(assignment["session_date"] for assignment in self.assignments),
        ]
        vectors = {
            assignment["session_date"]: assignment["return_vector_id"]
            for assignment in self.assignments
        }
        batches = []
        attempts = []
        symbols = sorted({*TICKERS, BENCHMARK})
        for index, session in enumerate(sessions):
            scheduled, deadline = formal_price_capture_window(session)
            completed = scheduled.timestamp() + 60.0
            started = completed - 30.0
            attempts.append(
                {
                    "session_date": session,
                    "attempt_ordinal": 1,
                    "event_type": "started",
                    "created_utc": started,
                    "observed_utc": started,
                    "reason_code": None,
                }
            )
            batches.append(
                {
                    "session_date": session,
                    "capture_batch_id": content_id({"session": session}, prefix="price_batch_"),
                    "attempt_ordinal": 1,
                    "from_session_date": None if index == 0 else sessions[index - 1],
                    "scheduled_utc": scheduled.timestamp(),
                    "started_utc": started,
                    "completed_utc": completed,
                    "persisted_utc": completed + 1.0,
                    "deadline_utc": deadline.timestamp(),
                    "vendor": "yfinance",
                    "paper_build_id": "build_" + "a" * 24,
                    "return_vector_id": vectors.get(session),
                    "receipt_manifest": [
                        {
                            "ticker": symbol,
                            "price_receipt_id": content_id(
                                {"session": session, "symbol": symbol, "kind": "receipt"},
                                prefix="price_receipt_",
                            ),
                            "vendor_snapshot_id": content_id(
                                {"session": session, "symbol": symbol, "kind": "snapshot"},
                                prefix="price_snapshot_",
                            ),
                        }
                        for symbol in symbols
                    ],
                }
            )
        return deepcopy(
            {
                "attempt_events": attempts,
                "batches": batches,
                "terminal_failures": [],
            }
        )

    def return_vector_for_session(self, run_id, session_date, symbols):
        assert run_id == RUN_ID
        assert symbols == [*TICKERS, BENCHMARK]
        vector = self.vectors.get(session_date)
        return deepcopy(vector) if vector is not None else None

    def _rows(self, sql, params):
        assert params in (
            {"run_id": RUN_ID},
            {"protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID},
            {"artifact_type": "formal_final_verification_manifest"},
        )
        if "FROM experiment_registry" in sql:
            rows = self.protocol_rows
        elif "FROM paper_interval_assignments" in sql:
            rows = self.assignments
        elif "FROM paper_decision_bundles" in sql:
            rows = [
                {"decision_date": row["decision_date"], "attempt_ordinal": 1}
                for row in self.official_targets
            ]
        elif "FROM paper_decision_attempt_events" in sql:
            rows = self.decision_attempt_events
        elif "FROM paper_artifacts" in sql:
            rows = list(self.artifacts.values())
        elif "FROM paper_strategy_marks" in sql:
            rows = sorted(
                self.strategy_marks,
                key=lambda row: (row["strategy_id"], row["session_date"]),
            )
        elif "FROM paper_marks" in sql:
            rows = sorted(self.champion_marks, key=lambda row: row["session_date"])
        elif "FROM paper_strategy_targets" in sql:
            rows = sorted(
                self.strategy_targets,
                key=lambda row: (row["strategy_id"], row["entry_date"]),
            )
        elif "FROM paper_targets" in sql:
            rows = sorted(self.official_targets, key=lambda row: row["entry_date"])
        else:
            raise AssertionError(f"unexpected query: {sql}")
        return deepcopy(rows)

    def record_artifact(self, *_args, **_kwargs):
        self.write_calls += 1
        raise AssertionError("formal readout must not write")


class WritableVerificationStore(FakeStore):
    def __init__(self):
        super().__init__()
        self.artifacts = {}
        self.recorded_types: list[str] = []

    def record_artifact(self, artifact_type, content, created_utc):
        artifact_id = content_id(
            {"artifact_type": artifact_type, "content": content}, prefix="artifact_"
        )
        if artifact_id not in self.artifacts:
            self.recorded_types.append(artifact_type)
            self.artifacts[artifact_id] = {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "content_json": canonical_json(content),
                "created_utc": created_utc,
            }
        return artifact_id


def _capture_readout(monkeypatch):
    captured = {}

    def fake_complete(
        strategy_returns,
        benchmark_returns,
        *,
        successful_decision_sets,
        synchronized_marks,
    ):
        captured.update(
            {
                "strategy_returns": deepcopy(strategy_returns),
                "benchmark_returns": list(benchmark_returns),
                "successful_decision_sets": successful_decision_sets,
                "synchronized_marks": synchronized_marks,
            }
        )
        return {
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "paired_intervals": len(benchmark_returns),
            "machine_statistical_candidate": False,
            "live_capital_approved": False,
        }

    monkeypatch.setattr(formal_readout, "formal_complete_readout", fake_complete)
    return captured


@pytest.mark.unit
def test_final_readout_reconstructs_start_cost_boundary_and_content_ids(monkeypatch):
    store = FakeStore()
    captured = _capture_readout(monkeypatch)

    result = build_formal_readout(store, RUN_ID)

    first_assignment = store.assignments[0]
    first_vector = store.vectors[first_assignment["session_date"]]
    first_mark = next(
        row
        for row in store.strategy_marks
        if row["strategy_id"] == "global_events_champion"
        and row["session_date"] == first_assignment["from_session_date"]
    )
    endpoint_mark = next(
        row
        for row in store.strategy_marks
        if row["strategy_id"] == "global_events_champion"
        and row["session_date"] == first_assignment["session_date"]
    )
    weights = json.loads(first_mark["weights_json"])
    holding = sum(
        weights[ticker] * first_vector["components"][ticker]["open_return"] for ticker in TICKERS
    )
    expected = (1.0 - first_mark["trading_cost"]) * (1.0 + holding) - 1.0
    reconstructed = captured["strategy_returns"]["global_events_champion"][0]
    assert reconstructed == pytest.approx(expected)
    assert endpoint_mark["trading_cost"] > 0
    assert reconstructed != pytest.approx(endpoint_mark["period_return"])
    assert captured["successful_decision_sets"] == 252
    assert captured["synchronized_marks"] == 252
    assert captured["benchmark_returns"][0] == pytest.approx(
        first_vector["components"][BENCHMARK]["open_return"]
    )

    bundle = result["outcome_bundle"]
    assert result["outcome_bundle_id"] == content_id(bundle, prefix="outcome_bundle_")
    report_base = {
        key: value for key, value in result.items() if key not in {"report_id", "outcome_bundle"}
    }
    assert result["report_id"] == content_id(report_base, prefix="formal_report_")
    assert result["review_gate"] == 252
    assert result["interim"] is False
    assert store.write_calls == 0

    repeated = build_formal_readout(store, RUN_ID)
    assert repeated["report_id"] == result["report_id"]
    assert repeated["outcome_bundle_id"] == result["outcome_bundle_id"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda store: store.vectors[store.assignments[0]["session_date"]]["components"][
                TICKERS[0]
            ].__setitem__("open_return", 0.25),
            "component arithmetic|content identity",
        ),
        (
            lambda store: store.assignments[0].__setitem__(
                "return_vector_id", "return_vector_tampered"
            ),
            "identities disagree|price capture identity",
        ),
        (
            lambda store: store.strategy_marks[1].__setitem__("period_return", 0.75),
            "stored.*return|official-mark",
        ),
        (
            lambda store: store.champion_marks[0].__setitem__("nav", 0.5),
            "official-mark",
        ),
    ],
)
def test_readout_fails_closed_on_vector_and_mark_tampering(monkeypatch, mutate, message):
    store = FakeStore()
    mutate(store)
    _capture_readout(monkeypatch)

    with pytest.raises(FormalReadoutIntegrityError, match=message):
        build_formal_readout(store, RUN_ID)
    assert store.write_calls == 0


@pytest.mark.unit
@pytest.mark.parametrize(("clock_skew", "valid"), [(10.0, True), (31.0, False)])
def test_price_manifest_uses_the_database_clock_skew_contract(clock_skew, valid):
    store = FakeStore()
    manifest = store.price_capture_operational_manifest(RUN_ID)
    for batch in manifest["batches"]:
        batch["persisted_utc"] = batch["completed_utc"] - clock_skew
    store.price_capture_operational_manifest = lambda _run_id: deepcopy(manifest)

    if valid:
        manifest_id = formal_readout._price_capture_operational_identity(
            store, RUN_ID, store.assignments
        )
        assert manifest_id.startswith("price_manifest_")
    else:
        with pytest.raises(FormalReadoutIntegrityError, match="timing window"):
            formal_readout._price_capture_operational_identity(store, RUN_ID, store.assignments)


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["assignment", "vector", "strategy_mark"])
def test_readout_rejects_missing_or_asymmetric_outcomes(monkeypatch, missing):
    store = FakeStore()
    if missing == "assignment":
        store.assignments.pop()
        store.counts["completed_intervals"] -= 1
        store.counts["successful_decision_sets"] -= 1
        store.counts["synchronized_marks"] -= 1
    elif missing == "vector":
        store.vectors.pop(store.assignments[-1]["session_date"])
    else:
        store.strategy_marks.pop()
    called = False

    def must_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("an incomplete trial must not expose an interim readout")

    monkeypatch.setattr(formal_readout, "formal_complete_readout", must_not_run)
    with pytest.raises(FormalReadoutIntegrityError):
        build_formal_readout(store, RUN_ID)
    assert called is False
    assert store.write_calls == 0


@pytest.mark.unit
def test_readout_rejects_target_disposition_and_long_only_tampering(monkeypatch):
    store = FakeStore()
    store.assignments[0]["disposition"] = "carry_forward_missing_decision"
    store.assignments[0]["applied_target_decision_date"] = None
    store.counts["successful_decision_sets"] -= 1
    store.counts["carry_forward_intervals"] += 1
    _capture_readout(monkeypatch)
    with pytest.raises(FormalReadoutIntegrityError, match="verification cohort"):
        build_formal_readout(store, RUN_ID)

    store = FakeStore()
    row = store.strategy_marks[0]
    weights = json.loads(row["weights_json"])
    weights[TICKERS[0]] = -0.01
    row["weights_json"] = canonical_json(weights)
    with pytest.raises(FormalReadoutIntegrityError, match="long-only"):
        build_formal_readout(store, RUN_ID)


@pytest.mark.unit
def test_readout_rejects_a_post_horizon_endpoint_target(monkeypatch):
    store = FakeStore()
    final_session = _sessions()[-1]
    final_decision = _decision_dates(_sessions())[-1]
    weights = canonical_json(_uniform_weights())
    store.official_targets.append(
        {
            "run_id": RUN_ID,
            "decision_date": final_decision,
            "entry_date": final_session,
            "weights_json": weights,
        }
    )
    for strategy in STRATEGIES:
        store.strategy_targets.append(
            {
                "run_id": RUN_ID,
                "decision_date": final_decision,
                "strategy_id": strategy,
                "entry_date": final_session,
                "weights_json": weights,
            }
        )
    _capture_readout(monkeypatch)

    with pytest.raises(FormalReadoutIntegrityError, match="verification cohort|extend beyond"):
        build_formal_readout(store, RUN_ID)


@pytest.mark.unit
@pytest.mark.parametrize("tamper", ["protocol", "registration", "strategies"])
def test_readout_requires_exact_run_registration_and_eight_strategies(monkeypatch, tamper):
    store = FakeStore()
    if tamper == "protocol":
        store.config["protocol_id"] = "protocol_wrong"
    elif tamper == "registration":
        store.registration["details"]["outcomes_accessed_before_registration"] = True
    else:
        store.strategy_ids.pop()
    _capture_readout(monkeypatch)

    with pytest.raises(FormalReadoutIntegrityError):
        build_formal_readout(store, RUN_ID)


@pytest.mark.unit
def test_formal_readout_has_no_caller_tunable_analysis_knobs(monkeypatch):
    signature = inspect.signature(build_formal_readout)
    assert list(signature.parameters) == ["store", "run_id"]
    assert all(
        parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values()
    )
    store = FakeStore()
    with pytest.raises(TypeError):
        build_formal_readout(store, RUN_ID, alpha=0.05)

    store.counts["successful_decision_sets"] = 240
    captured = _capture_readout(monkeypatch)
    # The count cannot be supplied by a caller or drift from assignments.
    with pytest.raises(FormalReadoutIntegrityError, match="counts disagree"):
        build_formal_readout(store, RUN_ID)
    assert captured == {}


def _successful_verification_receipt(run_id: str, decision_date: str) -> dict:
    return {
        "ok": True,
        "run_id": run_id,
        "decision_date": decision_date,
        "entry_date": next_session_date(decision_date),
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "build_id": "build_fixture",
        "artifact_id": "artifact_" + decision_date.replace("-", "").ljust(24, "0"),
        "strategies_replayed": len(STRATEGIES),
        "external_calls": 0,
    }


@pytest.mark.unit
def test_final_verification_manifest_replays_exact_cohort_in_assignment_order(
    monkeypatch,
):
    store = WritableVerificationStore()
    calls: list[str] = []

    def verify(_store, run_id, decision_date):
        assert store.recorded_types == []
        calls.append(decision_date)
        return _successful_verification_receipt(run_id, decision_date)

    monkeypatch.setattr("tradingagents.formal_verifier.verify_formal", verify)
    identities = materialize_final_verification_manifest(store, RUN_ID, 100.0)

    expected = [row["applied_target_decision_date"] for row in store.assignments]
    assert calls == expected
    assert store.recorded_types == ["formal_final_verification_manifest"]
    assert identities == require_final_verification_manifest(store, RUN_ID)
    manifest_row = next(iter(store.artifacts.values()))
    manifest = json.loads(manifest_row["content_json"])
    assert manifest["decision_dates"] == expected
    assert [row["decision_date"] for row in manifest["verifications"]] == expected
    assert manifest["external_calls_total"] == 0
    assert manifest["exact_coverage"] is True


@pytest.mark.unit
def test_attempt_binding_leaves_earlier_unmatched_start_as_crash():
    decision_date = "2026-08-04"
    entry_date = "2026-08-05"
    events = [
        {
            "run_id": RUN_ID,
            "decision_date": decision_date,
            "entry_date": entry_date,
            "attempt_ordinal": ordinal,
            "event_type": "started",
            "created_utc": float(ordinal),
            "reason_code": None,
        }
        for ordinal in (1, 2)
    ]

    state = formal_readout._validate_decision_attempt_bindings(
        events,
        [{"decision_date": decision_date, "attempt_ordinal": 2}],
        run_id=RUN_ID,
    )

    assert state["successful_attempts"] == {(decision_date, 2)}
    assert state["unresolved_attempts"] == {(decision_date, 1)}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda receipt: receipt.__setitem__("external_calls", 1), "did not authenticate"),
        (lambda receipt: receipt.__setitem__("ok", False), "did not authenticate"),
        (lambda receipt: receipt.__setitem__("strategies_replayed", 7), "did not authenticate"),
    ],
)
def test_final_verification_manifest_rejects_nonoffline_or_incomplete_receipt(
    monkeypatch, mutation, message
):
    store = WritableVerificationStore()

    def verify(_store, run_id, decision_date):
        receipt = _successful_verification_receipt(run_id, decision_date)
        mutation(receipt)
        return receipt

    monkeypatch.setattr("tradingagents.formal_verifier.verify_formal", verify)
    with pytest.raises(FormalReadoutIntegrityError, match=message):
        materialize_final_verification_manifest(store, RUN_ID, 100.0)
    assert store.artifacts == {}


@pytest.mark.unit
def test_final_verification_manifest_requires_exact_bundle_coverage(monkeypatch):
    store = WritableVerificationStore()
    store.official_targets.pop()
    monkeypatch.setattr(
        "tradingagents.formal_verifier.verify_formal",
        lambda *_args: pytest.fail("coverage failure reached the verifier"),
    )

    with pytest.raises(FormalReadoutIntegrityError, match="exactly cover"):
        materialize_final_verification_manifest(store, RUN_ID, 100.0)
    assert store.artifacts == {}


@pytest.mark.unit
def test_final_readout_rejects_missing_or_tampered_manifest_before_outcome_read(
    monkeypatch,
):
    class OutcomeGuardStore(WritableVerificationStore):
        def __init__(self):
            super().__init__()
            self.outcomes_read = False

        def return_vector_for_session(self, *args, **kwargs):
            self.outcomes_read = True
            return super().return_vector_for_session(*args, **kwargs)

        def _rows(self, sql, params):
            if "FROM paper_marks" in sql or "FROM paper_strategy_marks" in sql:
                self.outcomes_read = True
            return super()._rows(sql, params)

    store = OutcomeGuardStore()
    _capture_readout(monkeypatch)
    with pytest.raises(FormalReadoutIntegrityError, match="exactly one"):
        build_formal_readout(store, RUN_ID)
    assert store.outcomes_read is False

    source = FakeStore()
    row = next(iter(source.artifacts.values()))
    manifest = json.loads(row["content_json"])
    manifest["verifications"].reverse()
    artifact_id = content_id(
        {
            "artifact_type": "formal_final_verification_manifest",
            "content": manifest,
        },
        prefix="artifact_",
    )
    store.artifacts = {
        artifact_id: {
            "artifact_id": artifact_id,
            "artifact_type": "formal_final_verification_manifest",
            "content_json": canonical_json(manifest),
        }
    }
    with pytest.raises(FormalReadoutIntegrityError, match="receipt is malformed"):
        build_formal_readout(store, RUN_ID)
    assert store.outcomes_read is False
