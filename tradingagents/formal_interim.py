"""Frozen, access-labeled interim reviews for the Global Event V2 trial.

There are deliberately no public analysis parameters.  The only automatic
entry point observes the immutable trial clock and materializes a registered
review at exactly 20, 60, or 126 completed holding intervals.  Reports never
change trial behavior and routine callers receive identities, not outcomes.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date
from statistics import fmean
from typing import Any

from tradingagents.formal_readout import (
    _assert_json_finite,
    _fail,
    _finite_number,
    _price_capture_operational_identity,
    _read_rows,
    _require_registered_outcome_semantics,
    _validate_decision_attempt_bindings,
    _validate_run,
    _validate_vector,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)

INTERIM_REVIEW_GATES = (20, 60, 126)
INTERIM_REVIEW_LABELS = {
    20: "formal-review-20-operations",
    60: "formal-review-60-calibration",
    126: "formal-review-126-descriptive",
}
_REPORT_ARTIFACT_TYPES = {
    20: "formal_interim_operations_report",
    60: "formal_interim_calibration_report",
    126: "formal_interim_operational_integrity_report",
}
_REPORT_TYPES = {
    20: "global-event-v2-operations-only-interim",
    60: "global-event-v2-data-calibration-interim",
    126: "global-event-v2-blinded-operational-integrity-interim",
}
_SCOPES = {
    20: "operations-only",
    60: "data-and-calibration-only",
    126: "locked-descriptive-nonconclusive",
}
_OUTCOME_GATES = frozenset({60})
_TOLERANCE = 1e-12


def _timestamp(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise ValueError("formal interim timestamp must be finite")
    return float(value)


def _gate(value: Any) -> int:
    if type(value) is not int or value not in INTERIM_REVIEW_GATES:
        raise ValueError("formal interim gate must be exactly 20, 60, or 126")
    return value


def _nonnegative_count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        _fail(f"{label} must be a nonnegative integer")
    return value


def _completion(store: Any, run_id: str, gate: int) -> dict | None:
    label = INTERIM_REVIEW_LABELS[gate]
    rows = store._rows(
        "SELECT details_json FROM paper_run_labels "
        "WHERE run_id=:run_id AND label=:label",
        {"run_id": run_id, "label": label},
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("formal run has multiple labels for one interim gate")
    try:
        details = json.loads(rows[0]["details_json"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("formal interim label is malformed") from exc
    expected_keys = {
        "schema_version",
        "protocol_id",
        "review_gate",
        "scope",
        "report_id",
        "report_artifact_id",
        "outcomes_withheld",
    }
    if set(details) != expected_keys \
            or details.get("schema_version") != 1 \
            or details.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID \
            or details.get("review_gate") != gate \
            or details.get("scope") != _SCOPES[gate] \
            or details.get("outcomes_withheld") is not True:
        raise ValueError("formal interim label differs from the frozen contract")
    if not isinstance(details["report_id"], str) \
            or not isinstance(details["report_artifact_id"], str) \
            or re.fullmatch(
                r"interim_report_[0-9a-f]{24}", details["report_id"]
            ) is None or re.fullmatch(
                r"artifact_[0-9a-f]{24}", details["report_artifact_id"]
            ) is None:
        raise ValueError("formal interim label has a malformed identity")
    return details


def _require_exact_clock(store: Any, run_id: str, gate: int) -> dict:
    counts = store.formal_trial_counts(run_id)
    if not isinstance(counts, dict) \
            or counts.get("completed_intervals") != gate \
            or counts.get("assignment_indices_contiguous") is not True \
            or counts.get("assignment_dates_contiguous") is not True:
        raise ValueError(
            f"formal interim {gate} is available only at exactly {gate} "
            "contiguous completed intervals"
        )
    return counts


def _validate_assignments_at_gate(
    store: Any, run_id: str, gate: int
) -> tuple[list[dict], dict]:
    """Validate the exact immutable prefix without admitting a partial horizon."""
    rows = _read_rows(
        store,
        "SELECT run_id,interval_index,from_session_date,session_date,"
        "scheduled_decision_date,created_utc,disposition,"
        "applied_target_decision_date,return_vector_id "
        "FROM paper_interval_assignments WHERE run_id=:run_id "
        "ORDER BY interval_index",
        {"run_id": run_id},
    )
    if len(rows) != gate:
        _fail(f"formal interim requires exactly {gate} immutable assignments")

    from tradingagents.paper_trading import next_session_date

    assignments: list[dict] = []
    prior_end = None
    successes = 0
    for expected_index, raw in enumerate(rows, start=1):
        if raw.get("run_id") != run_id or type(raw.get("interval_index")) is not int \
                or raw["interval_index"] != expected_index:
            _fail("formal interim assignment indices are not contiguous from one")
        start = raw.get("from_session_date")
        end = raw.get("session_date")
        scheduled = raw.get("scheduled_decision_date")
        if not all(isinstance(value, str) and value for value in (start, end, scheduled)):
            _fail("formal interim assignment dates are malformed")
        try:
            dates_valid = next_session_date(start) == end \
                and next_session_date(scheduled) == start
        except (TypeError, ValueError):
            dates_valid = False
        if not dates_valid or (prior_end is not None and prior_end != start):
            _fail("formal interim assignments are not consecutive XNYS intervals")
        prior_end = end
        created = _finite_number(raw.get("created_utc"), "assignment timestamp")
        disposition = raw.get("disposition")
        applied = raw.get("applied_target_decision_date")
        if disposition == "target_applied":
            if applied != scheduled:
                _fail("formal target-applied assignment is not linked to its decision")
            successes += 1
        elif disposition == "carry_forward_missing_decision":
            if applied is not None:
                _fail("formal carry-forward assignment unexpectedly names a decision")
        else:
            _fail("formal interim assignment disposition is invalid")
        vector_id = raw.get("return_vector_id")
        if not isinstance(vector_id, str) or not vector_id.startswith("return_vector_"):
            _fail("formal interim return-vector identity is malformed")
        assignments.append({
            "interval_index": expected_index,
            "from_session_date": start,
            "session_date": end,
            "scheduled_decision_date": scheduled,
            "created_utc": created,
            "disposition": disposition,
            "applied_target_decision_date": applied,
            "return_vector_id": vector_id,
        })

    counts = _require_exact_clock(store, run_id, gate)
    recorded_successes = _nonnegative_count(
        counts.get("successful_decision_sets"), "successful decision sets"
    )
    recorded_carries = _nonnegative_count(
        counts.get("carry_forward_intervals"), "carry-forward intervals"
    )
    if recorded_successes != successes or recorded_carries != gate - successes:
        _fail("formal interim counts disagree with immutable assignments")
    return assignments, counts


def _operational_invocation_counts(
    store: Any, run_id: str, decision_dates: set[str]
) -> dict:
    """Count receipt state without loading a forecast, target, mark, or return."""
    rows = _read_rows(
        store,
        "SELECT artifact_id,artifact_type,content_json FROM paper_artifacts "
        "WHERE artifact_type IN "
        "('llm_invocation_reserved','llm_invocation_result')",
        {},
    )
    reservations: dict[str, dict] = {}
    results: list[dict] = []
    for row in rows:
        try:
            content = json.loads(row.get("content_json"))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(content, dict) or content.get("run_id") != run_id:
            continue
        if content.get("decision_date") not in decision_dates:
            _fail("formal invocation receipt falls outside the gate-20 frontier")
        artifact_type = row.get("artifact_type")
        expected_id = content_id(
            {"artifact_type": artifact_type, "content": content}, prefix="artifact_"
        )
        if row.get("artifact_id") != expected_id:
            _fail("formal invocation receipt content identity is invalid")
        if artifact_type == "llm_invocation_reserved":
            if row["artifact_id"] in reservations:
                _fail("formal invocation reservation is duplicated")
            reservations[row["artifact_id"]] = content
        elif artifact_type == "llm_invocation_result":
            results.append(content)

    paired: set[str] = set()
    reservation_dates: set[str] = set()
    result_dates: set[str] = set()
    successful = failed = orphan_results = 0
    for result in results:
        reservation_id = result.get("reservation_artifact_id")
        reservation = reservations.get(reservation_id)
        if reservation is None or reservation_id in paired:
            orphan_results += 1
            continue
        identity_fields = (
            "schema_version", "invocation_id", "scope", "run_id",
            "decision_date", "ordinal", "stage", "provider",
            "requested_model", "input_bundle_id",
        )
        if any(
            canonical_json(result.get(field)) != canonical_json(reservation.get(field))
            for field in identity_fields
        ):
            _fail("formal invocation receipt pair has inconsistent identity")
        paired.add(reservation_id)
        result_dates.add(result["decision_date"])
        if result.get("status") == "success":
            successful += 1
        else:
            failed += 1
    reservation_dates.update(
        reservation["decision_date"] for reservation in reservations.values()
    )
    return {
        "reservations": len(reservations),
        "results": len(results),
        "successful_results": successful,
        "non_success_results": failed,
        "orphan_reservations": len(set(reservations) - paired),
        "orphan_results": orphan_results,
        "decision_dates_with_reservations": sorted(reservation_dates),
        "decision_dates_with_results": sorted(result_dates),
    }


def _operational_attempt_counts(
    store: Any,
    run_id: str,
    *,
    decision_dates: set[str],
    bundle_dates: list[str],
) -> dict:
    """Reconcile starts, failures, crashes, and successes through the frontier."""
    rows = _read_rows(
        store,
        "SELECT run_id,decision_date,entry_date,attempt_ordinal,event_type,"
        "created_utc,reason_code FROM paper_decision_attempt_events "
        "WHERE run_id=:run_id ORDER BY decision_date,attempt_ordinal,event_type",
        {"run_id": run_id},
    )
    starts: dict[tuple[str, int], dict] = {}
    failures: dict[tuple[str, int], dict] = {}
    for row in rows:
        if row.get("run_id") != run_id:
            _fail("formal attempt event belongs to another run")
        decision_date = row.get("decision_date")
        entry_date = row.get("entry_date")
        ordinal = row.get("attempt_ordinal")
        event_type = row.get("event_type")
        if decision_date not in decision_dates:
            _fail("formal attempt event falls outside the gate-20 frontier")
        if type(ordinal) is not int or ordinal < 1 \
                or event_type not in {"started", "failed"}:
            _fail("formal attempt event identity is malformed")
        # Canonical date and timestamp validation without loading target/outcome rows.
        try:
            if date.fromisoformat(decision_date).isoformat() != decision_date \
                    or date.fromisoformat(entry_date).isoformat() != entry_date:
                raise ValueError
        except (TypeError, ValueError):
            _fail("formal attempt event dates are malformed")
        created = _finite_number(row.get("created_utc"), "formal attempt timestamp")
        key = (decision_date, ordinal)
        destination = starts if event_type == "started" else failures
        if key in destination:
            _fail("formal attempt event is duplicated")
        destination[key] = {
            "entry_date": entry_date,
            "created_utc": created,
            "reason_code": row.get("reason_code"),
        }
    for key, failure in failures.items():
        start = starts.get(key)
        if start is None or failure["entry_date"] != start["entry_date"] \
                or failure["created_utc"] < start["created_utc"] \
                or not isinstance(failure["reason_code"], str) \
                or not failure["reason_code"]:
            _fail("formal failed attempt lacks a coherent start event")
    bundle_rows = _read_rows(
        store,
        "SELECT decision_date,attempt_ordinal FROM paper_decision_bundles "
        "WHERE run_id=:run_id ORDER BY decision_date",
        {"run_id": run_id},
    )
    if [row.get("decision_date") for row in bundle_rows] != bundle_dates:
        _fail("formal decision bundle set changed during interim reconstruction")
    attempt_state = _validate_decision_attempt_bindings(
        rows, bundle_rows, run_id=run_id
    )
    unmatched = attempt_state["unmatched_attempts"]
    resolved = attempt_state["successful_attempts"]
    unresolved = attempt_state["unresolved_attempts"]
    return {
        "attempts_started": len(starts),
        "attempts_failed": len(failures),
        "attempts_without_failure_event": len(unmatched),
        "attempts_resolved_by_decision_bundle": len(resolved),
        "unresolved_attempts_without_terminal_event": len(unresolved),
        "decision_dates_in_scope": len(decision_dates),
        "decision_dates_with_attempts": sorted({date for date, _ in starts}),
        "decision_dates_with_failures": sorted({date for date, _ in failures}),
        "decision_dates_with_unresolved_attempts": sorted(
            {date for date, _ in unresolved}
        ),
    }


def _require_mark_matrix_counts(
    store: Any, run_id: str, gate: int, strategies: list[str]
) -> dict:
    expected_marks = gate + 1
    champion_counts = _read_rows(
        store,
        "SELECT COUNT(*) AS mark_count, "
        "COUNT(DISTINCT session_date) AS session_count "
        "FROM paper_marks WHERE run_id=:run_id",
        {"run_id": run_id},
    )
    strategy_counts = _read_rows(
        store,
        "SELECT strategy_id,COUNT(*) AS mark_count,"
        "COUNT(DISTINCT session_date) AS session_count "
        "FROM paper_strategy_marks WHERE run_id=:run_id "
        "GROUP BY strategy_id ORDER BY strategy_id",
        {"run_id": run_id},
    )
    if len(champion_counts) != 1:
        _fail(f"gate-{gate} champion mark completeness is invalid")
    champion_mark_count = _nonnegative_count(
        champion_counts[0].get("mark_count"), "champion mark count"
    )
    champion_session_count = _nonnegative_count(
        champion_counts[0].get("session_count"), "champion session count"
    )
    if champion_mark_count != expected_marks \
            or champion_session_count != expected_marks:
        _fail(f"gate-{gate} champion mark completeness is invalid")
    observed = {}
    for row in strategy_counts:
        strategy = row.get("strategy_id")
        if strategy in observed:
            _fail(f"gate-{gate} strategy mark count is duplicated")
        observed[strategy] = {
            "marks": _nonnegative_count(row.get("mark_count"), "strategy mark count"),
            "sessions": _nonnegative_count(
                row.get("session_count"), "strategy session count"
            ),
        }
    if set(observed) != set(strategies) or any(
        value != {"marks": expected_marks, "sessions": expected_marks}
        for value in observed.values()
    ):
        _fail(f"gate-{gate} strategy mark completeness is asymmetric")
    return {
        "champion_marks": expected_marks,
        "registered_strategies": len(strategies),
        "marks_per_strategy": expected_marks,
        "strategy_mark_rows": expected_marks * len(strategies),
    }


def _require_exact_bundle_dates(
    store: Any, run_id: str, assignments: list[dict], gate: int
) -> list[str]:
    bundle_rows = _read_rows(
        store,
        "SELECT decision_date,attempt_ordinal FROM paper_decision_bundles "
        "WHERE run_id=:run_id ORDER BY decision_date",
        {"run_id": run_id},
    )
    bundle_dates = [row.get("decision_date") for row in bundle_rows]
    expected = [
        row["applied_target_decision_date"]
        for row in assignments if row["disposition"] == "target_applied"
    ]
    # At an interim endpoint, the already-frozen target entering at that open
    # belongs to the *next* interval.  Its decision date is the endpoint's
    # previous session, which is the last completed interval's start.  It may
    # be absent after a failed decision, but no other out-of-cohort bundle is
    # permissible.  Calibration below deliberately excludes this frontier.
    frontier = assignments[-1]["from_session_date"]
    allowed = (sorted(expected), sorted([*expected, frontier]))
    if bundle_dates not in allowed or len(bundle_dates) != len(set(bundle_dates)):
        _fail(f"gate-{gate} decision bundles disagree with immutable assignments")
    return bundle_dates


def _build_gate20(store: Any, run_id: str) -> dict:
    """Build the operations-only gate without reading any outcome-bearing field."""
    _, registration, tickers, _ = _validate_run(store, run_id)
    assignments, counts = _validate_assignments_at_gate(store, run_id, 20)
    _price_capture_operational_identity(store, run_id, assignments)
    strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])

    mark_counts = _require_mark_matrix_counts(store, run_id, 20, strategies)
    bundle_dates = _require_exact_bundle_dates(store, run_id, assignments, 20)
    frontier = assignments[-1]["from_session_date"]
    decision_dates = {
        *(row["scheduled_decision_date"] for row in assignments),
        frontier,
    }
    attempt_counts = _operational_attempt_counts(
        store,
        run_id,
        decision_dates=decision_dates,
        bundle_dates=bundle_dates,
    )
    count_keys = (
        "attempts_started", "attempts_failed", "attempts_without_failure_event",
        "attempts_resolved_by_decision_bundle",
        "unresolved_attempts_without_terminal_event",
    )
    if any(counts.get(key) != attempt_counts[key] for key in count_keys):
        _fail("gate-20 attempt accounting disagrees with immutable attempt events")

    price_rows = _read_rows(
        store,
        "SELECT COUNT(*) AS receipt_count,"
        "COUNT(DISTINCT session_date) AS session_count "
        "FROM paper_price_receipts WHERE run_id=:run_id",
        {"run_id": run_id},
    )
    expected_price_receipts = mark_counts["champion_marks"] * (len(tickers) + 1)
    if len(price_rows) != 1:
        _fail("gate-20 price-receipt completeness is invalid")
    receipt_count = _nonnegative_count(
        price_rows[0].get("receipt_count"), "price receipt count"
    )
    receipt_sessions = _nonnegative_count(
        price_rows[0].get("session_count"), "price receipt session count"
    )
    if receipt_count != expected_price_receipts \
            or receipt_sessions != mark_counts["champion_marks"]:
        _fail("gate-20 price-receipt completeness is invalid")

    invocation_counts = _operational_invocation_counts(
        store, run_id, decision_dates
    )
    report_base = {
        "schema_version": 1,
        "report_type": _REPORT_TYPES[20],
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": run_id,
        "registration_id": registration["registration_id"],
        "review_gate": 20,
        "interim": True,
        "scope": _SCOPES[20],
        "outcomes_read": False,
        "completed_intervals": 20,
        "assignment_completeness": {
            "target_applied": counts["successful_decision_sets"],
            "carry_forward": counts["carry_forward_intervals"],
            "indices_contiguous": True,
            "dates_contiguous": True,
        },
        "attempt_operations": dict(attempt_counts),
        "mark_completeness": {
            **mark_counts,
        },
        "receipt_operations": {
            "price_receipts": expected_price_receipts,
            "decision_bundles": len(bundle_dates),
            "llm_invocations": invocation_counts,
        },
        "interpretation": "operations-only; no efficacy outcomes were accessed",
    }
    _assert_json_finite(report_base, "gate-20 report")
    return {**report_base, "report_id": content_id(report_base, prefix="interim_report_")}


def _probability_bin(probability: float) -> int:
    for index, upper in enumerate((0.2, 0.4, 0.6, 0.8)):
        if probability < upper:
            return index
    return 4


def _build_gate60(store: Any, run_id: str) -> dict:
    config, registration, tickers, benchmark = _validate_run(store, run_id)
    assignments, counts = _validate_assignments_at_gate(store, run_id, 60)
    _price_capture_operational_identity(store, run_id, assignments)
    strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    _require_mark_matrix_counts(store, run_id, 60, strategies)
    _require_exact_bundle_dates(store, run_id, assignments, 60)
    vector_symbols = [*tickers, benchmark]
    source_counts = Counter(dict.fromkeys(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["allowed_sources"], 0
    ))
    query_slots = [
        f"{theme}:{query}"
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "broad_news_queries"
        ].items()
        for query in queries
    ]
    query_counts = Counter(dict.fromkeys(query_slots, 0))
    x_topics = list(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_formal_policy"]["topic_labels"]
    )
    x_topic_counts = Counter(dict.fromkeys(x_topics, 0))
    probabilities: list[float] = []
    outcomes: list[float] = []
    expected_bps: list[float] = []
    realized_bps: list[float] = []
    abstentions = active = event_count = event_citations = asset_event_refs = 0
    decision_sets_with_x = 0

    from tradingagents.formal_verifier import verify_formal

    for assignment in assignments:
        if assignment["disposition"] != "target_applied":
            continue
        vector = store.return_vector_for_session(
            run_id, assignment["session_date"], vector_symbols
        )
        vector = _validate_vector(vector, assignment, symbols=vector_symbols)
        decision_date = assignment["applied_target_decision_date"]
        verification = verify_formal(store, run_id, decision_date)
        if not isinstance(verification, dict) or verification.get("ok") is not True \
                or verification.get("decision_date") != decision_date:
            _fail("gate-60 formal decision replay did not authenticate")
        snapshot = store.formal_bundle(run_id, decision_date)
        if snapshot.get("bundle", {}).get("decision_date") != decision_date:
            _fail("gate-60 assignment is not linked to its decision bundle")
        artifact = snapshot.get("artifact", {}).get("content")
        champion = artifact.get("champion") if isinstance(artifact, dict) else None
        evidence = champion.get("evidence") if isinstance(champion, dict) else None
        if not isinstance(evidence, list):
            _fail("gate-60 champion evidence is malformed")
        evidence_ids: set[str] = set()
        has_x = False
        for item in evidence:
            if not isinstance(item, dict):
                _fail("gate-60 champion evidence item is malformed")
            evidence_id = item.get("evidence_id")
            source = item.get("source")
            if not isinstance(evidence_id, str) or not evidence_id \
                    or evidence_id in evidence_ids or source not in source_counts:
                _fail("gate-60 champion evidence identity/source is invalid")
            evidence_ids.add(evidence_id)
            source_counts[source] += 1
            if source == "globalnews":
                slot = item.get("query_slot")
                if slot not in query_counts:
                    _fail("gate-60 selected global news has an invalid query slot")
                query_counts[slot] += 1
            if source == "x":
                topic = item.get("public_reaction_topic")
                if topic not in x_topic_counts:
                    _fail("gate-60 selected X evidence has an invalid topic")
                x_topic_counts[topic] += 1
                has_x = True
        decision_sets_with_x += int(has_x)

        events = snapshot.get("events")
        forecasts = snapshot.get("forecasts")
        if not isinstance(events, list) or not isinstance(forecasts, list) \
                or len(forecasts) != len(tickers):
            _fail("gate-60 champion forecast cross-section is incomplete")
        event_map: dict[str, dict] = {}
        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("event_id"), str) \
                    or event["event_id"] in event_map:
                _fail("gate-60 event identity is malformed or duplicated")
            citations = event.get("evidence_ids")
            if not isinstance(citations, list) or not citations \
                    or any(citation not in evidence_ids for citation in citations):
                _fail("gate-60 event has an invalid evidence citation")
            event_map[event["event_id"]] = event
            event_citations += len(citations)
        event_count += len(event_map)

        by_ticker: dict[str, dict] = {}
        for forecast in forecasts:
            if not isinstance(forecast, dict) \
                    or forecast.get("ticker") not in tickers \
                    or forecast["ticker"] in by_ticker:
                _fail("gate-60 forecast identity is malformed or duplicated")
            by_ticker[forecast["ticker"]] = forecast
        if set(by_ticker) != set(tickers):
            _fail("gate-60 forecast universe is asymmetric")
        benchmark_return = vector["components"][benchmark]["open_return"]
        for ticker in tickers:
            forecast = by_ticker[ticker]
            probability = _finite_number(
                forecast.get("probability_positive"), "forecast probability"
            )
            estimate = _finite_number(
                forecast.get("expected_excess_return_bps"), "forecast expected excess"
            )
            if not 0.0 <= probability <= 1.0:
                _fail("gate-60 forecast probability is outside [0,1]")
            abstain = forecast.get("abstain")
            references = forecast.get("event_ids")
            if type(abstain) is not bool or not isinstance(references, list) \
                    or any(reference not in event_map for reference in references):
                _fail("gate-60 abstention or event references are malformed")
            confidence = _finite_number(forecast.get("confidence"), "forecast confidence")
            if abstain:
                if estimate != 0.0 or probability != 0.5 or confidence != 0.0:
                    _fail("gate-60 abstention is not exactly neutral")
                abstentions += 1
            else:
                coherent = (estimate > 0.0 and probability > 0.5) or (
                    estimate < 0.0 and probability < 0.5
                )
                if not references or confidence <= 0.0 or not coherent:
                    _fail("gate-60 active forecast is ungrounded or incoherent")
                active += 1
                asset_event_refs += len(references)
            actual_bps = (
                vector["components"][ticker]["open_return"] - benchmark_return
            ) * 10_000.0
            probabilities.append(probability)
            outcomes.append(float(actual_bps > 0.0))
            expected_bps.append(estimate)
            realized_bps.append(actual_bps)

    successful = counts["successful_decision_sets"]
    if len(probabilities) != successful * len(tickers):
        _fail("gate-60 forecast observations disagree with successful assignments")
    bins = [{
        "interval": label,
        "count": 0,
        "mean_forecast_probability": None,
        "realized_positive_rate": None,
    } for label in ("[0.0,0.2)", "[0.2,0.4)", "[0.4,0.6)", "[0.6,0.8)", "[0.8,1.0]")]
    binned_probabilities = [[] for _ in bins]
    binned_outcomes = [[] for _ in bins]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        index = _probability_bin(probability)
        binned_probabilities[index].append(probability)
        binned_outcomes[index].append(outcome)
    for index, result in enumerate(bins):
        result["count"] = len(binned_probabilities[index])
        if result["count"]:
            result["mean_forecast_probability"] = fmean(binned_probabilities[index])
            result["realized_positive_rate"] = fmean(binned_outcomes[index])

    observation_count = len(probabilities)
    report_base = {
        "schema_version": 1,
        "report_type": _REPORT_TYPES[60],
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": run_id,
        "registration_id": registration["registration_id"],
        "review_gate": 60,
        "interim": True,
        "scope": _SCOPES[60],
        "completed_intervals": 60,
        "successful_decision_sets": successful,
        "forecast_observations": observation_count,
        "calibration": {
            "brier_score_all_forecasts": (
                fmean((probability - outcome) ** 2 for probability, outcome in zip(
                    probabilities, outcomes, strict=True
                )) if observation_count else None
            ),
            "expected_excess_mae_bps_all_forecasts": (
                fmean(abs(estimate - actual) for estimate, actual in zip(
                    expected_bps, realized_bps, strict=True
                )) if observation_count else None
            ),
            "probability_bins": bins,
        },
        "forecast_integrity": {
            "abstentions": abstentions,
            "active_forecasts": active,
            "valid_neutral_abstentions": abstentions,
            "invalid_abstentions": 0,
            "valid_forecasts": observation_count,
            "invalid_forecasts": 0,
            "events": event_count,
            "event_evidence_citations": event_citations,
            "valid_event_evidence_citations": event_citations,
            "invalid_event_evidence_citations": 0,
            "active_asset_event_references": asset_event_refs,
            "valid_active_asset_event_references": asset_event_refs,
            "invalid_asset_event_references": 0,
        },
        "selected_evidence_occurrence_balance": {
            "by_source": dict(source_counts),
            "globalnews_by_query_slot": dict(query_counts),
            "x_by_topic": dict(x_topic_counts),
            "decision_sets_with_x": decision_sets_with_x,
        },
        "missingness": {
            "carry_forward_intervals_have_no_forecast_observations": counts[
                "carry_forward_intervals"
            ],
            "zero_observation_metrics_are_null": observation_count == 0,
            "imputation": "none",
        },
        "interpretation": "diagnostic-only; no strategy-return comparison or inference",
    }
    _assert_json_finite(report_base, "gate-60 report")
    return {**report_base, "report_id": content_id(report_base, prefix="interim_report_")}


def _build_gate126(store: Any, run_id: str) -> dict:
    """Publish aggregate integrity only; strategy identities/efficacy stay blind."""
    _, registration, _, _ = _validate_run(store, run_id)
    strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    assignments, counts = _validate_assignments_at_gate(store, run_id, 126)
    _price_capture_operational_identity(store, run_id, assignments)
    mark_counts = _require_mark_matrix_counts(store, run_id, 126, strategies)
    bundle_dates = _require_exact_bundle_dates(store, run_id, assignments, 126)

    final_counts = store.formal_trial_counts(run_id)
    stable_keys = (
        "completed_intervals", "successful_decision_sets", "carry_forward_intervals",
        "assignment_indices_contiguous", "assignment_dates_contiguous",
    )
    if not isinstance(final_counts, dict) or any(
        final_counts.get(key) != counts.get(key) for key in stable_keys
    ):
        _fail("formal trial ledger changed during gate-126 reconstruction")
    report_base = {
        "schema_version": 1,
        "report_type": _REPORT_TYPES[126],
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": run_id,
        "registration_id": registration["registration_id"],
        "review_gate": 126,
        "interim": True,
        "scope": _SCOPES[126],
        "completed_intervals": 126,
        "successful_decision_sets": counts["successful_decision_sets"],
        "outcomes_read": False,
        "strategy_identities_withheld": True,
        "efficacy_statistics_withheld": True,
        "aggregate_integrity": {
            "registered_strategy_paths": len(strategies),
            "completed_intervals_per_path": 126,
            "marks_per_path": mark_counts["marks_per_strategy"],
            "strategy_mark_rows": mark_counts["strategy_mark_rows"],
            "target_applied_assignments": counts["successful_decision_sets"],
            "carry_forward_assignments": counts["carry_forward_intervals"],
            "decision_bundles_through_frontier": len(bundle_dates),
            "assignment_indices_contiguous": True,
            "assignment_dates_contiguous": True,
        },
        "interpretation": (
            "operational-integrity-only; strategy identity and efficacy remain blinded"
        ),
    }
    _assert_json_finite(report_base, "gate-126 report")
    return {**report_base, "report_id": content_id(report_base, prefix="interim_report_")}


def _build_gate_report(store: Any, run_id: str, gate: int) -> dict:
    if gate == 20:
        return _build_gate20(store, run_id)
    if gate == 60:
        return _build_gate60(store, run_id)
    if gate == 126:
        return _build_gate126(store, run_id)
    raise AssertionError("unreachable formal interim gate")


def _validate_loaded_report_contract(report: dict, gate: int) -> None:
    common = {
        "schema_version", "report_type", "protocol_id", "run_id",
        "registration_id", "review_gate", "interim", "scope",
        "completed_intervals", "interpretation", "report_id",
    }
    if gate == 20:
        if set(report) != common | {
            "outcomes_read", "assignment_completeness", "attempt_operations",
            "mark_completeness", "receipt_operations",
        } or report.get("outcomes_read") is not False:
            raise ValueError("formal gate-20 report schema is invalid")
        if set(report.get("assignment_completeness", {})) != {
            "target_applied", "carry_forward", "indices_contiguous", "dates_contiguous",
        } or set(report.get("attempt_operations", {})) != {
            "attempts_started", "attempts_failed", "attempts_without_failure_event",
            "attempts_resolved_by_decision_bundle",
            "unresolved_attempts_without_terminal_event",
            "decision_dates_in_scope", "decision_dates_with_attempts",
            "decision_dates_with_failures",
            "decision_dates_with_unresolved_attempts",
        } or set(report.get("mark_completeness", {})) != {
            "champion_marks", "registered_strategies", "marks_per_strategy",
            "strategy_mark_rows",
        } or set(report.get("receipt_operations", {})) != {
            "price_receipts", "decision_bundles", "llm_invocations",
        } or set(report.get("receipt_operations", {}).get("llm_invocations", {})) != {
            "reservations", "results", "successful_results", "non_success_results",
            "orphan_reservations", "orphan_results",
            "decision_dates_with_reservations", "decision_dates_with_results",
        }:
            raise ValueError("formal gate-20 report fields are invalid")
    elif gate == 60:
        if set(report) != common | {
            "successful_decision_sets", "forecast_observations", "calibration",
            "forecast_integrity", "selected_evidence_occurrence_balance", "missingness",
        } or set(report.get("calibration", {})) != {
            "brier_score_all_forecasts", "expected_excess_mae_bps_all_forecasts",
            "probability_bins",
        } or set(report.get("forecast_integrity", {})) != {
            "abstentions", "active_forecasts", "valid_neutral_abstentions",
            "invalid_abstentions", "valid_forecasts", "invalid_forecasts", "events",
            "event_evidence_citations", "valid_event_evidence_citations",
            "invalid_event_evidence_citations", "active_asset_event_references",
            "valid_active_asset_event_references", "invalid_asset_event_references",
        } or set(report.get("selected_evidence_occurrence_balance", {})) != {
            "by_source", "globalnews_by_query_slot", "x_by_topic",
            "decision_sets_with_x",
        } or set(report.get("missingness", {})) != {
            "carry_forward_intervals_have_no_forecast_observations",
            "zero_observation_metrics_are_null", "imputation",
        }:
            raise ValueError("formal gate-60 report schema is invalid")
        expected_bins = (
            "[0.0,0.2)", "[0.2,0.4)", "[0.4,0.6)",
            "[0.6,0.8)", "[0.8,1.0]",
        )
        bins = report["calibration"].get("probability_bins")
        if not isinstance(bins, list) or len(bins) != len(expected_bins) or any(
            not isinstance(row, dict)
            or set(row) != {
                "interval", "count", "mean_forecast_probability",
                "realized_positive_rate",
            }
            or row.get("interval") != interval
            for row, interval in zip(bins, expected_bins, strict=True)
        ):
            raise ValueError("formal gate-60 probability bins are invalid")
        balance = report["selected_evidence_occurrence_balance"]
        expected_query_slots = {
            f"{theme}:{query}"
            for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                "broad_news_queries"
            ].items()
            for query in queries
        }
        expected_topics = set(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_formal_policy"]["topic_labels"]
        )
        if set(balance.get("by_source", {})) != set(
            GLOBAL_EVENT_V2_PROTOCOL["evidence"]["allowed_sources"]
        ) or set(balance.get("globalnews_by_query_slot", {})) != expected_query_slots \
                or set(balance.get("x_by_topic", {})) != expected_topics:
            raise ValueError("formal gate-60 balance fields are invalid")
    elif gate == 126:
        if set(report) != common | {
            "successful_decision_sets", "outcomes_read",
            "strategy_identities_withheld", "efficacy_statistics_withheld",
            "aggregate_integrity",
        }:
            raise ValueError("formal gate-126 report schema is invalid")
        integrity_fields = {
            "registered_strategy_paths", "completed_intervals_per_path",
            "marks_per_path", "strategy_mark_rows", "target_applied_assignments",
            "carry_forward_assignments", "decision_bundles_through_frontier",
            "assignment_indices_contiguous", "assignment_dates_contiguous",
        }
        if report.get("outcomes_read") is not False \
                or report.get("strategy_identities_withheld") is not True \
                or report.get("efficacy_statistics_withheld") is not True \
                or not isinstance(report.get("aggregate_integrity"), dict) \
                or set(report["aggregate_integrity"]) != integrity_fields \
                or report.get("interpretation") != (
                    "operational-integrity-only; strategy identity and efficacy remain blinded"
                ):
            raise ValueError("formal gate-126 blinded integrity fields are invalid")
    else:
        raise AssertionError("unreachable formal interim gate")
    _assert_json_finite(report, f"loaded gate-{gate} report")


def _materialize_gate(store: Any, run_id: str, gate: int, created: float) -> dict:
    existing = _completion(store, run_id, gate)
    if existing is not None:
        return {**existing, "already_materialized": True}
    _require_exact_clock(store, run_id, gate)

    access_artifact_id = None
    if gate in _OUTCOME_GATES:
        access_artifact_id = store.record_artifact(
            "formal_outcome_access",
            {
                "schema_version": 1,
                "run_id": run_id,
                "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                "review_gate": gate,
                "access_kind": f"automatic_interim_{gate}_materialization",
                "accessed_utc": created,
                "outcomes_may_be_read_after_this_receipt": True,
            },
            created,
        )
    try:
        report = _build_gate_report(store, run_id, gate)
    except Exception as exc:
        try:
            failure = {
                "schema_version": 1,
                "run_id": run_id,
                "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                "review_gate": gate,
                "reason_code": "integrity_validation_failed",
            }
            if access_artifact_id is not None:
                failure["access_artifact_id"] = access_artifact_id
            store.record_artifact(
                "formal_interim_integrity_failure", failure, created
            )
        except Exception:
            exc.add_note("formal interim failure receipt could not be appended")
        raise

    report_artifact_id = store.record_artifact(
        _REPORT_ARTIFACT_TYPES[gate], report, created
    )
    details = {
        "schema_version": 1,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "review_gate": gate,
        "scope": _SCOPES[gate],
        "report_id": report["report_id"],
        "report_artifact_id": report_artifact_id,
        "outcomes_withheld": True,
    }
    store.label_run(run_id, INTERIM_REVIEW_LABELS[gate], created, details)
    return {**details, "already_materialized": False}


def materialize_due_formal_interims(
    store: Any, run_id: str, created_utc: float
) -> list[dict]:
    """Materialize only the exact review due at the current immutable clock."""
    created = _timestamp(created_utc)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("formal interim run ID must be a non-empty string")
    _require_registered_outcome_semantics(store, run_id)
    counts = store.formal_trial_counts(run_id)
    if not isinstance(counts, dict) or type(counts.get("completed_intervals")) is not int:
        raise ValueError("formal interim trial counts are malformed")
    completed = counts["completed_intervals"]
    for gate in INTERIM_REVIEW_GATES:
        if completed > gate and _completion(store, run_id, gate) is None:
            raise ValueError(
                f"formal run passed registered interim gate {gate} without its "
                "immutable report"
            )
    if completed not in INTERIM_REVIEW_GATES:
        return []
    return [_materialize_gate(store, run_id, completed, created)]


def load_formal_interim_report(
    store: Any, run_id: str, review_gate: int, accessed_utc: float
) -> dict:
    """Access one already-materialized exact interim under the frozen contract."""
    gate = _gate(review_gate)
    accessed = _timestamp(accessed_utc)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("formal interim run ID must be a non-empty string")
    _require_registered_outcome_semantics(store, run_id)
    details = _completion(store, run_id, gate)
    if details is None:
        raise ValueError(f"formal interim gate {gate} has not been materialized")
    if gate in _OUTCOME_GATES:
        store.record_artifact(
            "formal_outcome_access",
            {
                "schema_version": 1,
                "run_id": run_id,
                "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                "review_gate": gate,
                "access_kind": f"explicit_interim_{gate}_report_view",
                "accessed_utc": accessed,
                "report_id": details["report_id"],
                "outcomes_may_be_read_after_this_receipt": True,
            },
            accessed,
        )
    rows = store._rows(
        "SELECT artifact_type,content_json FROM paper_artifacts "
        "WHERE artifact_id=:artifact_id",
        {"artifact_id": details["report_artifact_id"]},
    )
    if len(rows) != 1 or rows[0].get("artifact_type") \
            != _REPORT_ARTIFACT_TYPES[gate]:
        raise ValueError("formal interim report artifact is missing")
    try:
        report = json.loads(rows[0]["content_json"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("formal interim report artifact is malformed") from exc
    if not isinstance(report, dict):
        raise ValueError("formal interim report artifact is malformed")
    base = {key: value for key, value in report.items() if key != "report_id"}
    expected_artifact_id = content_id(
        {"artifact_type": _REPORT_ARTIFACT_TYPES[gate], "content": report},
        prefix="artifact_",
    )
    if report.get("report_id") != details["report_id"] \
            or content_id(base, prefix="interim_report_") != details["report_id"] \
            or expected_artifact_id != details["report_artifact_id"] \
            or report.get("report_type") != _REPORT_TYPES[gate] \
            or report.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID \
            or report.get("run_id") != run_id \
            or report.get("review_gate") != gate \
            or report.get("interim") is not True \
            or report.get("scope") != _SCOPES[gate]:
        raise ValueError("formal interim report artifact failed content validation")
    _validate_loaded_report_contract(report, gate)
    return report


__all__ = [
    "INTERIM_REVIEW_GATES",
    "INTERIM_REVIEW_LABELS",
    "load_formal_interim_report",
    "materialize_due_formal_interims",
]
