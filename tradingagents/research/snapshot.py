"""Build immutable point-in-time evidence snapshots.

This phase can read the collector database.  It never imports price or outcome
providers and never invokes a model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from tradingagents.global_research import (
    bind_receipt_coverage_to_selection,
    evidence_selection_manifest,
    evidence_window,
    formal_globalnews_selection_coverage,
)
from tradingagents.research.artifacts import ArtifactRef, FilesystemArtifactStore
from tradingagents.research.contracts import (
    EvidenceSnapshot,
    SnapshotSlice,
    require_strict_evidence_availability,
)
from tradingagents.research.x_availability import (
    bind_x_availability_to_selection,
    project_x_cycle_availability,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    build_identity,
)

EvidenceLoader = Callable[[str], list[dict[str, Any]]]
SelectionBuilder = Callable[[list[dict[str, Any]], float], dict[str, Any]]
ReceiptCoverageLoader = Callable[[date, datetime, dict[str, Any]], dict[str, Any]]


def _decision_cutoff(decision_date: date) -> datetime:
    """The V2 after-session boundary: following UTC midnight."""
    return datetime.combine(decision_date + timedelta(days=1), time.min, timezone.utc)


def _require_xnys_sessions(decision_dates: tuple[date, ...]) -> None:
    """Reject weekend, holiday, or out-of-calendar experimental dates."""
    if not decision_dates:
        raise ValueError("snapshot requires at least one decision date")
    try:
        import exchange_calendars as xcals
    except ImportError as exc:  # pragma: no cover - exercised by clean-install smoke
        raise RuntimeError(
            "media snapshots require exchange-calendars; install tradingagents[poller]"
        ) from exc
    calendar = xcals.get_calendar("XNYS")
    sessions = {
        value.date()
        for value in calendar.sessions_in_range(
            min(decision_dates).isoformat(), max(decision_dates).isoformat()
        )
    }
    invalid = [value.isoformat() for value in decision_dates if value not in sessions]
    if invalid:
        raise ValueError("decision dates must be XNYS sessions: " + ",".join(invalid))


def _default_selection(rows: list[dict[str, Any]], cutoff: float) -> dict[str, Any]:
    return evidence_selection_manifest(rows, as_of_utc=cutoff)


def _default_coverage(selection: dict[str, Any]) -> dict[str, Any]:
    return formal_globalnews_selection_coverage(selection)


def build_snapshot(
    *,
    run_id: str,
    decision_dates: Iterable[date],
    universe: Iterable[str],
    sectors: Mapping[str, str],
    evidence_loader: EvidenceLoader,
    benchmark: str = "SPY",
    protocol_id: str = GLOBAL_EVENT_V2_PROTOCOL_ID,
    collection_policy_id: str = GLOBAL_EVENT_V2_PROTOCOL["evidence"][
        "expected_collector_semantics_id"
    ],
    selection_builder: SelectionBuilder = _default_selection,
    coverage_builder: Callable[[dict[str, Any]], dict[str, Any]] = _default_coverage,
    receipt_coverage_loader: ReceiptCoverageLoader | None = None,
) -> EvidenceSnapshot:
    """Read each cutoff independently and freeze exactly what was observable."""
    requested_dates = tuple(decision_dates)
    if any(isinstance(value, datetime) or not isinstance(value, date) for value in requested_dates):
        raise TypeError("decision dates must be date values")
    dates = tuple(sorted(set(requested_dates)))
    if not dates:
        raise ValueError("snapshot requires at least one decision date")
    symbols = tuple(symbol.strip().upper() for symbol in universe)
    slices = []
    for decision_date in dates:
        cutoff = _decision_cutoff(decision_date)
        rows = evidence_loader(decision_date.isoformat())
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise TypeError("evidence loader must return a list of mappings")
        # Reject future or duplicate rows before even pure selection code sees
        # them; SnapshotSlice repeats the check at the artifact boundary.
        require_strict_evidence_availability(rows, cutoff)
        selection = selection_builder(rows, cutoff.timestamp())
        selection_coverage = coverage_builder(selection)
        if receipt_coverage_loader is None:
            coverage = selection_coverage
        else:
            receipt_coverage = receipt_coverage_loader(decision_date, cutoff, selection)
            bound_coverage = bind_receipt_coverage_to_selection(
                receipt_coverage, selection
            )
            coverage = {
                "complete": bool(
                    receipt_coverage.get("complete") is True
                    and selection_coverage.get("complete") is True
                    and bound_coverage.get("complete") is True
                ),
                "receipt_coverage": receipt_coverage,
                "selection_coverage": selection_coverage,
                "receipt_selection_binding": bound_coverage,
            }
        x_availability = selection.get("x_cycle_availability")
        if isinstance(x_availability, dict):
            # X is optional public reaction.  Its exact missing/incomplete/empty
            # state remains visible without turning a healthy editorial-news
            # snapshot into a failed interval.
            coverage = {**coverage, "x_cycle_availability": x_availability}
        slices.append(
            SnapshotSlice(
                decision_date=decision_date,
                decision_cutoff=cutoff,
                raw_evidence=tuple(rows),
                selection_manifest=selection,
                coverage=coverage,
            )
        )
    return EvidenceSnapshot(
        run_id=run_id,
        build_id=build_identity(),
        protocol_id=protocol_id,
        collection_policy_id=collection_policy_id,
        universe=symbols,
        sectors={symbol.strip().upper(): str(sector) for symbol, sector in sectors.items()},
        benchmark=benchmark,
        slices=tuple(slices),
    )


def build_media_snapshot(
    *,
    db_url: str,
    run_id: str,
    decision_dates: Iterable[date],
) -> EvidenceSnapshot:
    """Production adapter over the existing append-only media repository."""
    from tradingagents.dataflows.media_store import open_store

    dates = tuple(decision_dates)
    _require_xnys_sessions(dates)
    protocol_universe = GLOBAL_EVENT_V2_PROTOCOL["universe"]
    symbols = tuple(protocol_universe["symbols"])
    sectors = dict(protocol_universe["sectors"])
    store = open_store(db_url, auto_migrate=False)
    try:
        evidence_policy = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
        query_slots = list(
            dict.fromkeys(
                ("globalnews", f"{theme}:{query}")
                for theme, queries in evidence_policy["broad_news_queries"].items()
                for query in queries
            )
        )
        cycle_policy = evidence_policy["query_cycle"]
        interval = int(cycle_policy["collector_interval_seconds"])
        grace = int(cycle_policy["cycle_start_grace_seconds"])
        x_availability_by_cutoff: dict[float, dict[str, Any]] = {}

        def load_evidence(decision_date: str) -> list[dict[str, Any]]:
            parsed_date = date.fromisoformat(decision_date)
            cutoff = _decision_cutoff(parsed_date)
            candidates = evidence_window(store, decision_date)
            availability, rows = project_x_cycle_availability(
                store, cutoff=cutoff, candidate_rows=candidates
            )
            x_availability_by_cutoff[cutoff.timestamp()] = availability
            return rows

        def select_evidence(
            rows: list[dict[str, Any]], cutoff_utc: float
        ) -> dict[str, Any]:
            try:
                availability = x_availability_by_cutoff[float(cutoff_utc)]
            except KeyError as exc:
                raise ValueError("X availability was not resolved before selection") from exc
            selection = evidence_selection_manifest(rows, as_of_utc=cutoff_utc)
            return bind_x_availability_to_selection(selection, availability)

        def receipt_coverage(
            _decision_date: date,
            cutoff: datetime,
            _selection: dict[str, Any],
        ) -> dict[str, Any]:
            window = interval + grace
            report = store.coverage_report(
                cutoff.timestamp(),
                evidence_policy["required_source_groups"],
                max_age_seconds=float(window),
                expected_query_slots=query_slots,
                require_lineage_query_slots=query_slots,
                min_started_utc=(cutoff - timedelta(seconds=window)).timestamp(),
            )
            return {
                **report,
                "collector_interval_seconds": interval,
                "cycle_start_grace_seconds": grace,
                "cycle_lower_bound_utc": (
                    cutoff - timedelta(seconds=window)
                ).timestamp(),
            }

        return build_snapshot(
            run_id=run_id,
            decision_dates=dates,
            universe=symbols,
            sectors=sectors,
            evidence_loader=load_evidence,
            selection_builder=select_evidence,
            receipt_coverage_loader=receipt_coverage,
        )
    finally:
        store.close()


def commit_snapshot(
    artifact_store: FilesystemArtifactStore, snapshot: EvidenceSnapshot
) -> ArtifactRef:
    return artifact_store.commit("snapshot", snapshot.model_dump(mode="json"))
