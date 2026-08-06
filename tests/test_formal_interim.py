from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import date, timedelta

import pytest

from tests.test_formal_readout import (
    BENCHMARK,
    CONFIGURATION_BINDING,
    OUTCOME_SEMANTICS_ID,
    RUN_ID,
    STRATEGIES,
    TICKERS,
    FakeStore,
)
from tradingagents import formal_interim, formal_verifier, paper_trading
from tradingagents.formal_interim import (
    INTERIM_REVIEW_LABELS,
    load_formal_interim_report,
    materialize_due_formal_interims,
)
from tradingagents.formal_readout import FormalReadoutIntegrityError
from tradingagents.outcome_semantics import OutcomeSemanticsResolutionError
from tradingagents.paper_trading import formal_price_capture_window, next_session_date
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)


def _registration(run_id: str) -> dict:
    analysis = GLOBAL_EVENT_V2_PROTOCOL["analysis"]
    base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": run_id,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "analysis_id": content_id(analysis, prefix="analysis_"),
        "review_gates_id": content_id(GLOBAL_EVENT_V2_PROTOCOL["review_gates"], prefix="reviews_"),
        "decision_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["forecast"][
            "expected_decision_semantics_id"
        ],
        "outcome_semantics_id": OUTCOME_SEMANTICS_ID,
        "configuration_binding": dict(CONFIGURATION_BINDING),
        "registered_strategies": list(GLOBAL_EVENT_V2_PROTOCOL["strategies"]),
        "confirmatory_family": list(analysis["multiplicity"]["confirmatory_family"]),
        "secondary_family": list(analysis["multiplicity"]["secondary_family"]),
        "trial_clock": analysis["trial_clock"],
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    return {**base, "registration_id": content_id(base, prefix="registration_")}


def _sessions(count: int) -> list[str]:
    values = ["2024-01-03"]
    while len(values) <= count:
        values.append(next_session_date(values[-1]))
    return values


def _assignments(run_id: str, gate: int, *, successful: set[int]) -> list[dict]:
    sessions = _sessions(gate)
    decisions = ["2024-01-02", *sessions[:-1]]
    rows = []
    for index in range(1, gate + 1):
        decision = decisions[index - 1]
        applied = index in successful
        scheduled, _deadline = formal_price_capture_window(sessions[index])
        rows.append(
            {
                "run_id": run_id,
                "interval_index": index,
                "from_session_date": sessions[index - 1],
                "session_date": sessions[index],
                "scheduled_decision_date": decision,
                "created_utc": scheduled.timestamp() + 60.0,
                "disposition": ("target_applied" if applied else "carry_forward_missing_decision"),
                "applied_target_decision_date": decision if applied else None,
                "return_vector_id": f"return_vector_{index:024d}",
            }
        )
    return rows


def _config(run_id: str) -> tuple[dict, dict]:
    registration = _registration(run_id)
    portfolio = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
    return (
        {
            "engine": "formal-global-v2",
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "tickers": list(TICKERS),
            "benchmark": BENCHMARK,
            "cost_bps": portfolio["trading_cost_bps"],
            "slippage_bps": portfolio["slippage_bps"],
            "annual_borrow_bps": 0.0,
            "cash_policy": portfolio["cash"],
            "outcome_semantics_id": OUTCOME_SEMANTICS_ID,
            "configuration_binding": dict(CONFIGURATION_BINDING),
            "trial_registration_id": registration["registration_id"],
        },
        registration,
    )


class _OutcomeSemanticsGuardStore:
    run_id = "interim-semantics-guard"

    def __init__(self, mutation: str):
        registration = _registration(self.run_id)
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
            self.registration["details"].pop("outcome_semantics_id")
        elif mutation == "installed_drift":
            drifted = "outcome_semantics_" + "0" * 64
            self.config["outcome_semantics_id"] = drifted
            self.registration["details"]["outcome_semantics_id"] = drifted
        else:
            raise AssertionError(mutation)

    def run_config(self, run_id):
        assert run_id == self.run_id
        return deepcopy(self.config)

    def confirmatory_registration(self, run_id):
        assert run_id == self.run_id
        return deepcopy(self.registration)

    def __getattr__(self, name):
        self.outcome_reads += 1
        raise AssertionError(
            f"outcome-semantics failure reached stored interim access {name!r}"
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda store: materialize_due_formal_interims(
                store,
                store.run_id,
                100.0,
            ),
            id="materialize",
        ),
        pytest.param(
            lambda store: load_formal_interim_report(
                store,
                store.run_id,
                20,
                100.0,
            ),
            id="load",
        ),
    ],
)
@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        ("missing", FormalReadoutIntegrityError, "disagree on outcome semantics"),
        (
            "installed_drift",
            OutcomeSemanticsResolutionError,
            "differ from preregistration",
        ),
    ],
)
def test_public_interim_paths_reject_outcome_semantics_before_outcome_reads(
    operation,
    mutation,
    error,
    message,
):
    store = _OutcomeSemanticsGuardStore(mutation)

    with pytest.raises(error, match=message):
        operation(store)

    assert store.outcome_reads == 0


def _seed_completed_label(labels: dict[str, str], gate: int) -> None:
    labels[INTERIM_REVIEW_LABELS[gate]] = canonical_json(
        {
            "schema_version": 1,
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "review_gate": gate,
            "scope": GLOBAL_EVENT_V2_PROTOCOL["review_gates"][str(gate)]["scope"],
            "report_id": "interim_report_" + f"{gate:024x}",
            "report_artifact_id": "artifact_" + f"{gate:024x}",
            "outcomes_withheld": True,
        }
    )


class Gate20Store:
    run_id = "gate-20-run"

    def __init__(self, completed: int = 20, *, frontier_bundle: bool = True):
        self.config, registration = _config(self.run_id)
        self.registration = {
            "label": "confirmatory-trial",
            "created_utc": 1_699_999_000.0,
            "details": registration,
        }
        self.assignments = _assignments(self.run_id, 20, successful=set(range(1, 21)))
        self.completed = completed
        self.frontier_bundle = frontier_bundle
        decision_dates = [row["scheduled_decision_date"] for row in self.assignments]
        if frontier_bundle:
            decision_dates.append(self.assignments[-1]["from_session_date"])
        self.bundle_dates = list(decision_dates)
        self.attempt_events = [
            {
                "run_id": self.run_id,
                "decision_date": decision_date,
                "entry_date": next_session_date(decision_date),
                "attempt_ordinal": 1,
                "event_type": "started",
                "created_utc": 1_699_000_000.0 + index,
                "reason_code": None,
            }
            for index, decision_date in enumerate(decision_dates)
        ]
        self.invocation_rows: list[dict] = []
        self.labels: dict[str, str] = {}
        self.artifacts: dict[str, dict] = {}
        self.events: list[tuple[str, str]] = []
        self.sql: list[str] = []

    def run_config(self, run_id):
        assert run_id == self.run_id
        return deepcopy(self.config)

    def confirmatory_registration(self, run_id):
        assert run_id == self.run_id
        return deepcopy(self.registration)

    def formal_strategies(self, run_id):
        assert run_id == self.run_id
        return sorted(STRATEGIES)

    def formal_trial_counts(self, run_id):
        assert run_id == self.run_id
        successes = sum(row["disposition"] == "target_applied" for row in self.assignments)
        starts = {
            (row["decision_date"], row["attempt_ordinal"])
            for row in self.attempt_events
            if row["event_type"] == "started"
        }
        failures = {
            (row["decision_date"], row["attempt_ordinal"])
            for row in self.attempt_events
            if row["event_type"] == "failed"
        }
        unmatched = starts - failures
        resolved = {
            (
                decision_date,
                max(
                    ordinal
                    for date_value, ordinal in starts
                    if date_value == decision_date
                ),
            )
            for decision_date in self.bundle_dates
        }
        return {
            "completed_intervals": self.completed,
            "successful_decision_sets": successes,
            "carry_forward_intervals": len(self.assignments) - successes,
            "assignment_indices_contiguous": True,
            "assignment_dates_contiguous": True,
            "attempts_started": len(starts),
            "attempts_failed": len(failures),
            "attempts_without_failure_event": len(unmatched),
            "attempts_resolved_by_decision_bundle": len(resolved),
            "unresolved_attempts_without_terminal_event": len(unmatched - resolved),
        }

    def price_capture_operational_manifest(self, run_id):
        assert run_id == self.run_id
        sessions = [
            self.assignments[0]["from_session_date"],
            *(row["session_date"] for row in self.assignments),
        ]
        vector_ids = {row["session_date"]: row["return_vector_id"] for row in self.assignments}
        symbols = sorted({*TICKERS, BENCHMARK})
        attempts = []
        batches = []
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
                    "capture_batch_id": content_id(
                        {"run_id": self.run_id, "session": session},
                        prefix="price_batch_",
                    ),
                    "attempt_ordinal": 1,
                    "from_session_date": None if index == 0 else sessions[index - 1],
                    "scheduled_utc": scheduled.timestamp(),
                    "started_utc": started,
                    "completed_utc": completed,
                    "persisted_utc": completed + 1.0,
                    "deadline_utc": deadline.timestamp(),
                    "vendor": "yfinance",
                    "paper_build_id": "build_" + "a" * 24,
                    "return_vector_id": vector_ids.get(session),
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
        return {
            "attempt_events": attempts,
            "batches": batches,
            "terminal_failures": [],
        }

    def _rows(self, sql, params):
        self.sql.append(sql)
        forbidden = (
            "paper_forecasts",
            "weights_json",
            "payload_json",
            "period_return",
            "benchmark_period_return",
            "SELECT nav",
            "SELECT * FROM paper_marks",
            "FROM paper_targets",
        )
        assert not any(token in sql for token in forbidden), sql
        if "FROM paper_run_labels" in sql:
            encoded = self.labels.get(params["label"])
            return [{"details_json": encoded}] if encoded is not None else []
        if "FROM experiment_registry" in sql:
            return [{"manifest_json": canonical_json(GLOBAL_EVENT_V2_PROTOCOL)}]
        if "FROM paper_interval_assignments" in sql:
            return deepcopy(self.assignments)
        if "FROM paper_decision_attempt_events" in sql:
            return deepcopy(self.attempt_events)
        if "COUNT(*) AS mark_count" in sql and "FROM paper_marks" in sql:
            return [{"mark_count": 21, "session_count": 21}]
        if "COUNT(*) AS mark_count" in sql and "FROM paper_strategy_marks" in sql:
            return [
                {"strategy_id": strategy, "mark_count": 21, "session_count": 21}
                for strategy in sorted(STRATEGIES)
            ]
        if "FROM paper_decision_bundles" in sql:
            return [
                {
                    "decision_date": decision_date,
                    "attempt_ordinal": max(
                        row["attempt_ordinal"]
                        for row in self.attempt_events
                        if row["decision_date"] == decision_date
                        and row["event_type"] == "started"
                    ),
                }
                for decision_date in sorted(self.bundle_dates)
            ]
        if "FROM paper_price_receipts" in sql:
            return [{"receipt_count": 21 * (len(TICKERS) + 1), "session_count": 21}]
        if "artifact_type IN" in sql:
            return deepcopy(self.invocation_rows)
        if "FROM paper_artifacts" in sql:
            row = self.artifacts.get(params["artifact_id"])
            return [dict(row)] if row is not None else []
        raise AssertionError(sql)

    def record_artifact(self, artifact_type, content, created_utc):
        artifact_id = content_id(
            {"artifact_type": artifact_type, "content": content}, prefix="artifact_"
        )
        self.events.append(("artifact", artifact_type))
        self.artifacts.setdefault(
            artifact_id,
            {
                "artifact_type": artifact_type,
                "content_json": canonical_json(content),
                "created_utc": created_utc,
            },
        )
        return artifact_id

    def label_run(self, run_id, label, created_utc, details):
        assert run_id == self.run_id
        self.events.append(("label", label))
        encoded = canonical_json(details)
        if label in self.labels:
            if self.labels[label] != encoded:
                raise ValueError("different label")
            return False
        self.labels[label] = encoded
        return True


@pytest.mark.unit
def test_gate20_never_reads_outcomes_and_has_no_access_receipt():
    store = Gate20Store()

    results = materialize_due_formal_interims(store, store.run_id, 100.0)

    assert len(results) == 1
    assert set(results[0]) == {
        "schema_version",
        "protocol_id",
        "review_gate",
        "scope",
        "report_id",
        "report_artifact_id",
        "outcomes_withheld",
        "already_materialized",
    }
    assert results[0]["outcomes_withheld"] is True
    assert all(
        kind != "formal_outcome_access" for action, kind in store.events if action == "artifact"
    )
    report = load_formal_interim_report(store, store.run_id, 20, 200.0)
    assert report["outcomes_read"] is False
    assert report["completed_intervals"] == 20
    assert report["receipt_operations"]["price_receipts"] == 441
    assert report["receipt_operations"]["decision_bundles"] == 21
    assert report["attempt_operations"]["decision_dates_in_scope"] == 21
    assert len(report["attempt_operations"]["decision_dates_with_attempts"]) == 21


@pytest.mark.unit
def test_gate20_accounts_for_failed_and_crashed_dates_through_frontier():
    store = Gate20Store()
    crashed = store.assignments[4]["scheduled_decision_date"]
    store.assignments[4]["disposition"] = "carry_forward_missing_decision"
    store.assignments[4]["applied_target_decision_date"] = None
    store.bundle_dates.remove(crashed)

    retried = store.assignments[1]["scheduled_decision_date"]
    start = next(
        row
        for row in store.attempt_events
        if row["decision_date"] == retried and row["event_type"] == "started"
    )
    store.attempt_events.extend(
        [
            {
                **start,
                "event_type": "failed",
                "created_utc": start["created_utc"] + 0.1,
                "reason_code": "unexpected_failure",
            },
            {
                **start,
                "attempt_ordinal": 2,
                "created_utc": start["created_utc"] + 0.2,
            },
        ]
    )

    def reservation(decision_date, invocation_id):
        content = {
            "schema_version": 2,
            "invocation_id": invocation_id,
            "scope": "formal-global-v2",
            "run_id": store.run_id,
            "decision_date": decision_date,
            "ordinal": 1,
            "stage": "champion",
            "provider": "openai",
            "requested_model": "fixture",
            "input_bundle_id": "bundle_fixture",
        }
        artifact_id = content_id(
            {"artifact_type": "llm_invocation_reserved", "content": content},
            prefix="artifact_",
        )
        return (
            artifact_id,
            {
                "artifact_id": artifact_id,
                "artifact_type": "llm_invocation_reserved",
                "content_json": canonical_json(content),
            },
            content,
        )

    failed_id, failed_row, failed_content = reservation(retried, "invocation_failed")
    _, crashed_row, _ = reservation(crashed, "invocation_crashed")
    result_content = {
        **failed_content,
        "reservation_artifact_id": failed_id,
        "status": "error",
    }
    result_row = {
        "artifact_id": content_id(
            {"artifact_type": "llm_invocation_result", "content": result_content},
            prefix="artifact_",
        ),
        "artifact_type": "llm_invocation_result",
        "content_json": canonical_json(result_content),
    }
    store.invocation_rows = [failed_row, result_row, crashed_row]

    materialize_due_formal_interims(store, store.run_id, 100.0)
    report = load_formal_interim_report(store, store.run_id, 20, 200.0)

    attempts = report["attempt_operations"]
    assert attempts["attempts_failed"] == 1
    assert attempts["unresolved_attempts_without_terminal_event"] == 1
    assert attempts["decision_dates_with_failures"] == [retried]
    assert attempts["decision_dates_with_unresolved_attempts"] == [crashed]
    invocations = report["receipt_operations"]["llm_invocations"]
    assert invocations["reservations"] == 2
    assert invocations["non_success_results"] == 1
    assert invocations["orphan_reservations"] == 1
    assert invocations["decision_dates_with_reservations"] == sorted([crashed, retried])
    assert report["receipt_operations"]["decision_bundles"] == 20
    assert report["attempt_operations"]["decision_dates_in_scope"] == 21
    assert len(report["attempt_operations"]["decision_dates_with_attempts"]) == 21
    assert all(
        kind != "formal_outcome_access" for action, kind in store.events if action == "artifact"
    )


@pytest.mark.unit
def test_interim_materialization_is_idempotent_and_missed_gate_fails_closed():
    store = Gate20Store()
    first = materialize_due_formal_interims(store, store.run_id, 100.0)
    event_count = len(store.events)
    second = materialize_due_formal_interims(store, store.run_id, 101.0)
    assert first[0]["report_id"] == second[0]["report_id"]
    assert second[0]["already_materialized"] is True
    assert len(store.events) == event_count

    missed = Gate20Store(completed=21)
    with pytest.raises(ValueError, match="passed registered interim gate 20"):
        materialize_due_formal_interims(missed, missed.run_id, 100.0)
    assert missed.events == []


@pytest.mark.unit
def test_interim_view_rejects_report_artifact_tampering():
    store = Gate20Store()
    details = materialize_due_formal_interims(store, store.run_id, 100.0)[0]
    store.artifacts[details["report_artifact_id"]]["content_json"] = canonical_json(
        {
            "report_id": details["report_id"],
            "nav": 99.0,
        }
    )

    with pytest.raises(ValueError, match="content validation"):
        load_formal_interim_report(store, store.run_id, 20, 200.0)


def _return_vector(assignment: dict, *, asset_return: float, spy_return: float) -> dict:
    components = {}
    for symbol in [*TICKERS, BENCHMARK]:
        returned = spy_return if symbol == BENCHMARK else asset_return
        previous = 100.0
        current = previous * (1.0 + returned)
        components[symbol] = {
            "price_receipt_id": content_id(
                {"session": assignment["session_date"], "symbol": symbol, "kind": "receipt"},
                prefix="price_receipt_",
            ),
            "vendor_snapshot_id": content_id(
                {"session": assignment["session_date"], "symbol": symbol, "kind": "snapshot"},
                prefix="price_snapshot_",
            ),
            "previous_adjusted_open": previous,
            "current_adjusted_open": current,
            "current_raw_open": current,
            "cash_dividend": 0.0,
            "split_ratio": 0.0,
            "open_return": current / previous - 1.0,
        }
    start = date.fromisoformat(assignment["from_session_date"])
    end = date.fromisoformat(assignment["session_date"])
    cash = {
        "instrument": "USD",
        "annual_yield_proxy": "^IRX",
        "observation_session": (start - timedelta(days=1)).isoformat(),
        "annual_yield_percent": 3.6,
        "accrual_days": (end - start).days,
        "day_count_basis": 360,
        "open_return": 0.036 * (end - start).days / 360.0,
    }
    base = {
        "schema_version": 2,
        "from_session": assignment["from_session_date"],
        "to_session": assignment["session_date"],
        "captured_utc": assignment["created_utc"],
        "scheduled_utc": formal_price_capture_window(assignment["session_date"])[0].timestamp(),
        "deadline_utc": formal_price_capture_window(assignment["session_date"])[1].timestamp(),
        "vendor": "yfinance",
        "components": components,
        "cash_component": cash,
    }
    return {"return_vector_id": content_id(base, prefix="return_vector_"), **base}


class Gate60Store(Gate20Store):
    run_id = "gate-60-run"

    def __init__(self):
        self.config, registration = _config(self.run_id)
        self.registration = {
            "label": "confirmatory-trial",
            "created_utc": 1_699_999_000.0,
            "details": registration,
        }
        self.assignments = _assignments(self.run_id, 60, successful={1})
        self.vectors = {}
        for assignment in self.assignments:
            vector = _return_vector(assignment, asset_return=0.01, spy_return=0.0)
            assignment["return_vector_id"] = vector["return_vector_id"]
            self.vectors[assignment["session_date"]] = vector
        self.completed = 60
        self.labels = {}
        _seed_completed_label(self.labels, 20)
        self.artifacts = {}
        self.events = []
        self.sql = []
        slot = next(
            iter(
                f"{theme}:{query}"
                for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                    "broad_news_queries"
                ].items()
                for query in queries
            )
        )
        x_topic = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_formal_policy"]["topic_labels"][0]
        evidence = [
            {
                "evidence_id": "evidence_news",
                "source": "globalnews",
                "query_slot": slot,
                "public_reaction_topic": None,
            },
            {
                "evidence_id": "evidence_x",
                "source": "x",
                "query_slot": None,
                "public_reaction_topic": x_topic,
            },
        ]
        event = {"event_id": "event_1", "evidence_ids": ["evidence_news", "evidence_x"]}
        forecasts = [
            {
                "ticker": ticker,
                "expected_excess_return_bps": 100.0,
                "probability_positive": 0.6,
                "confidence": 0.8,
                "abstain": False,
                "event_ids": ["event_1"],
                "rationale": "fixture",
            }
            for ticker in TICKERS
        ]
        decision_date = self.assignments[0]["scheduled_decision_date"]
        self.snapshot = {
            "bundle": {"decision_date": decision_date},
            "artifact": {"content": {"champion": {"evidence": evidence}}},
            "events": [event],
            "forecasts": forecasts,
        }

    def formal_trial_counts(self, run_id):
        assert run_id == self.run_id
        return {
            "completed_intervals": 60,
            "successful_decision_sets": 1,
            "carry_forward_intervals": 59,
            "assignment_indices_contiguous": True,
            "assignment_dates_contiguous": True,
        }

    def return_vector_for_session(self, run_id, session_date, symbols):
        assert run_id == self.run_id
        assert symbols == [*TICKERS, BENCHMARK]
        assert self.events and self.events[0] == ("artifact", "formal_outcome_access")
        return deepcopy(self.vectors[session_date])

    def formal_bundle(self, run_id, decision_date):
        assert run_id == self.run_id
        assert decision_date == self.snapshot["bundle"]["decision_date"]
        assert self.events and self.events[0] == ("artifact", "formal_outcome_access")
        return deepcopy(self.snapshot)

    def _rows(self, sql, params):
        self.sql.append(sql)
        if "FROM paper_run_labels" in sql:
            encoded = self.labels.get(params["label"])
            return [{"details_json": encoded}] if encoded is not None else []
        if "FROM experiment_registry" in sql:
            return [{"manifest_json": canonical_json(GLOBAL_EVENT_V2_PROTOCOL)}]
        if "FROM paper_interval_assignments" in sql:
            return deepcopy(self.assignments)
        if "COUNT(*) AS mark_count" in sql and "FROM paper_marks" in sql:
            return [{"mark_count": 61, "session_count": 61}]
        if "COUNT(*) AS mark_count" in sql and "FROM paper_strategy_marks" in sql:
            return [
                {"strategy_id": strategy, "mark_count": 61, "session_count": 61}
                for strategy in sorted(STRATEGIES)
            ]
        if "FROM paper_decision_bundles" in sql:
            return [
                {"decision_date": decision_date}
                for decision_date in sorted(
                    {
                        self.assignments[0]["scheduled_decision_date"],
                        self.assignments[-1]["from_session_date"],
                    }
                )
            ]
        if "FROM paper_artifacts" in sql:
            row = self.artifacts.get(params["artifact_id"])
            return [dict(row)] if row is not None else []
        raise AssertionError(sql)


@pytest.mark.unit
def test_gate60_records_access_first_and_uses_fixed_all_sample_calibration(monkeypatch):
    store = Gate60Store()
    monkeypatch.setattr(
        formal_verifier,
        "verify_formal",
        lambda _store, _run, decision: {"ok": True, "decision_date": decision},
    )

    result = materialize_due_formal_interims(store, store.run_id, 100.0)[0]
    assert store.events[0] == ("artifact", "formal_outcome_access")
    assert result["outcomes_withheld"] is True
    report = load_formal_interim_report(store, store.run_id, 60, 200.0)
    assert store.events[-1] == ("artifact", "formal_outcome_access")
    assert report["forecast_observations"] == len(TICKERS)
    assert report["calibration"]["brier_score_all_forecasts"] == pytest.approx(0.16)
    assert report["calibration"]["expected_excess_mae_bps_all_forecasts"] == pytest.approx(
        0.0, abs=1e-9
    )
    assert [row["interval"] for row in report["calibration"]["probability_bins"]] == [
        "[0.0,0.2)",
        "[0.2,0.4)",
        "[0.4,0.6)",
        "[0.6,0.8)",
        "[0.8,1.0]",
    ]
    assert report["calibration"]["probability_bins"][3]["count"] == len(TICKERS)
    assert report["forecast_integrity"]["invalid_forecasts"] == 0
    balance = report["selected_evidence_occurrence_balance"]
    assert balance["by_source"] == {
        source: int(source in {"globalnews", "x"})
        for source in GLOBAL_EVENT_V2_PROTOCOL["evidence"]["allowed_sources"]
    }
    assert sum(balance["globalnews_by_query_slot"].values()) == 1
    assert sum(balance["x_by_topic"].values()) == 1
    serialized = canonical_json(report).lower()
    for forbidden in ("strategy_returns", "strategy ranking", "p_value", "promotion"):
        assert forbidden not in serialized


@pytest.mark.unit
def test_gate60_tampered_return_vector_fails_after_access_receipt(monkeypatch):
    store = Gate60Store()
    first_session = store.assignments[0]["session_date"]
    store.vectors[first_session]["components"][TICKERS[0]]["open_return"] = 0.02
    monkeypatch.setattr(
        formal_verifier,
        "verify_formal",
        lambda _store, _run, decision: {"ok": True, "decision_date": decision},
    )

    with pytest.raises(FormalReadoutIntegrityError, match="component arithmetic"):
        materialize_due_formal_interims(store, store.run_id, 100.0)

    assert store.events[0] == ("artifact", "formal_outcome_access")
    assert ("artifact", "formal_interim_integrity_failure") in store.events
    assert INTERIM_REVIEW_LABELS[60] not in store.labels


class Gate126Store(FakeStore):
    def __init__(self):
        super().__init__()
        gate = 126
        self.assignments = self.assignments[:gate]
        sessions = [
            self.assignments[0]["from_session_date"],
            *[row["session_date"] for row in self.assignments],
        ]
        session_set = set(sessions)
        target_sessions = set(sessions)
        self.champion_marks = [
            row for row in self.champion_marks if row["session_date"] in session_set
        ]
        self.strategy_marks = [
            row for row in self.strategy_marks if row["session_date"] in session_set
        ]
        self.official_targets = [
            row for row in self.official_targets if row["entry_date"] in target_sessions
        ]
        self.strategy_targets = [
            row for row in self.strategy_targets if row["entry_date"] in target_sessions
        ]
        self.vectors = {
            row["session_date"]: self.vectors[row["session_date"]] for row in self.assignments
        }
        self.counts = {
            "completed_intervals": gate,
            "successful_decision_sets": gate,
            "carry_forward_intervals": 0,
            "assignment_indices_contiguous": True,
            "assignment_dates_contiguous": True,
            "synchronized_marks": gate,
        }
        self.labels: dict[str, str] = {}
        _seed_completed_label(self.labels, 20)
        _seed_completed_label(self.labels, 60)
        self.artifacts: dict[str, dict] = {}
        self.events: list[tuple[str, str]] = []

    def return_vector_for_session(self, run_id, session_date, symbols):
        assert self.events and self.events[0] == ("artifact", "formal_outcome_access")
        return super().return_vector_for_session(run_id, session_date, symbols)

    def _rows(self, sql, params):
        if "FROM paper_run_labels" in sql:
            encoded = self.labels.get(params["label"])
            return [{"details_json": encoded}] if encoded is not None else []
        if "FROM paper_artifacts" in sql:
            row = self.artifacts.get(params["artifact_id"])
            return [dict(row)] if row is not None else []
        if "COUNT(*) AS mark_count" in sql and "FROM paper_marks" in sql:
            return [{"mark_count": 127, "session_count": 127}]
        if "COUNT(*) AS mark_count" in sql and "FROM paper_strategy_marks" in sql:
            return [
                {
                    "strategy_id": strategy,
                    "mark_count": 127,
                    "session_count": 127,
                }
                for strategy in sorted(STRATEGIES)
            ]
        if "FROM paper_decision_bundles" in sql:
            return [
                {"decision_date": decision_date}
                for decision_date in sorted(
                    {
                        *(row["scheduled_decision_date"] for row in self.assignments),
                        self.assignments[-1]["from_session_date"],
                    }
                )
            ]
        if any(
            table in sql
            for table in (
                "FROM paper_marks",
                "FROM paper_strategy_marks",
                "FROM paper_targets",
                "FROM paper_strategy_targets",
            )
        ):
            assert self.events and self.events[0] == ("artifact", "formal_outcome_access")
        return super()._rows(sql, params)

    def record_artifact(self, artifact_type, content, created_utc):
        artifact_id = content_id(
            {"artifact_type": artifact_type, "content": content}, prefix="artifact_"
        )
        self.events.append(("artifact", artifact_type))
        self.artifacts.setdefault(
            artifact_id,
            {
                "artifact_type": artifact_type,
                "content_json": canonical_json(content),
                "created_utc": created_utc,
            },
        )
        return artifact_id

    def label_run(self, run_id, label, created_utc, details):
        assert run_id == RUN_ID
        self.events.append(("label", label))
        encoded = canonical_json(details)
        if label in self.labels:
            if self.labels[label] != encoded:
                raise ValueError("different label")
            return False
        self.labels[label] = encoded
        return True


@pytest.mark.unit
def test_gate126_keeps_strategy_identity_and_efficacy_blinded():
    store = Gate126Store()

    result = materialize_due_formal_interims(store, RUN_ID, 100.0)[0]

    assert all(
        kind != "formal_outcome_access" for action, kind in store.events if action == "artifact"
    )
    assert result["outcomes_withheld"] is True
    report = load_formal_interim_report(store, RUN_ID, 126, 200.0)
    assert report["outcomes_read"] is False
    assert report["strategy_identities_withheld"] is True
    assert report["efficacy_statistics_withheld"] is True
    assert report["aggregate_integrity"]["registered_strategy_paths"] == len(STRATEGIES)
    serialized = canonical_json(report).lower()
    for forbidden in (
        *STRATEGIES,
        "strategy_descriptives",
        "spy_descriptives",
        "cumulative_return",
        "p_value",
        "rank",
        "promotion",
    ):
        assert forbidden not in serialized
    assert all(
        kind != "formal_outcome_access" for action, kind in store.events if action == "artifact"
    )


@pytest.mark.unit
def test_gate126_does_not_read_tampered_nav_or_create_outcome_access():
    store = Gate126Store()
    store.strategy_marks[-1]["nav"] += 0.01

    result = materialize_due_formal_interims(store, RUN_ID, 100.0)

    assert result[0]["review_gate"] == 126
    assert all(
        kind != "formal_outcome_access" for action, kind in store.events if action == "artifact"
    )


@pytest.mark.unit
def test_interim_api_has_no_analysis_knobs_and_marker_never_runs_analyzers():
    assert list(inspect.signature(materialize_due_formal_interims).parameters) == [
        "store",
        "run_id",
        "created_utc",
    ]
    source = inspect.getsource(paper_trading._mark_formal_once_locked)
    assert "materialize_due_formal_interims" not in source
    assert "materialize_final_formal_review" not in source
    assert "build_formal_readout" not in source


@pytest.mark.unit
def test_manual_formal_marker_finishes_shadows_without_running_analyzers(
    monkeypatch,
    tmp_path,
):
    class Store:
        def __init__(self):
            self.url = str(tmp_path / "manual-paper.db")
            self._sqlite = True
            self.completed = 19
            self.latest = {"session_date": "2024-01-30"}

        def run_config(self, run_id):
            assert run_id == "manual-run"
            return {"engine": "formal-global-v2"}

        def latest_mark(self, run_id):
            assert run_id == "manual-run"
            return dict(self.latest)

        def formal_trial_counts(self, run_id):
            assert run_id == "manual-run"
            return {"completed_intervals": self.completed}

    store = Store()
    calls = []

    def shadows(_store, _run_id, mark):
        calls.append(("shadows", mark["session_date"], store.completed))
        return [{"strategy_id": strategy} for strategy in STRATEGIES]

    def mark_next(_store, _run_id, _captured_utc=None):
        store.completed += 1
        store.latest = {"session_date": f"session-{store.completed}"}
        calls.append(("mark", store.completed))
        return {
            "session_date": store.latest["session_date"],
            "return_vector_id": f"return_vector_{store.completed}",
        }

    monkeypatch.setattr(paper_trading, "mark_formal_strategies", shadows)
    monkeypatch.setattr(paper_trading, "mark_next", mark_next)
    monkeypatch.setattr(
        formal_interim,
        "materialize_due_formal_interims",
        lambda *_args: pytest.fail("marker reached the interim analyzer"),
    )
    monkeypatch.setattr(
        "tradingagents.formal_review.materialize_final_formal_review",
        lambda *_args: pytest.fail("manual mark reached the final gate"),
    )

    first = paper_trading._mark_formal_once(store, "manual-run", 100.0)
    second = paper_trading._mark_formal_once(store, "manual-run", 101.0)

    assert [call for call in calls if call[0] == "mark"] == [
        ("mark", 20),
        ("mark", 21),
    ]
    assert first["strategy_marks_recorded"] == 2 * len(STRATEGIES)
    assert second["strategy_marks_recorded"] == 2 * len(STRATEGIES)
    assert first["analysis_materialized"] is second["analysis_materialized"] is False
    assert first["outcomes_withheld"] is second["outcomes_withheld"] is True
    for result in (first, second):
        assert not {"nav", "weights", "period_return"} & set(result)
