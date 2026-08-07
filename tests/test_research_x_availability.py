"""Exact-cycle guarantees for optional public-reaction evidence."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from tradingagents.dataflows.media_store import collection_cycle_spec
from tradingagents.evidence_lineage import evidence_id, raw_content_id
from tradingagents.global_research import evidence_selection_manifest
from tradingagents.poller import _x_collection_cycle_spec
from tradingagents.research.snapshot import build_media_snapshot
from tradingagents.research.x_availability import (
    bind_x_availability_to_selection,
    project_x_cycle_availability,
    validate_bound_x_selection,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    content_id,
    global_news_query_slot_label,
)

_DECISION_DATE = date(2026, 1, 10)
_CUTOFF = datetime(2026, 1, 11, tzinfo=timezone.utc)
_BUILD_ID = "build_" + "b" * 24
_FETCH_ID = "fetch_" + "f" * 24


def _spec() -> dict:
    maximum = int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]
    )
    return _x_collection_cycle_spec(
        datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp(), maximum
    )


def _compatible_specs() -> list[dict]:
    primary = _spec()["identity"]
    compatible_identities = GLOBAL_EVENT_V2_PROTOCOL["evidence"][
        "compatible_collector_identities"
    ]
    return [
        collection_cycle_spec(
            cycle_kind=primary["cycle_kind"],
            period_key=primary["period_key"],
            protocol_id=compatible["protocol_id"],
            collector_semantics_id=compatible["collector_semantics_id"],
            expected_static_slots=[
                (slot["provider"], slot["query_key"])
                for slot in primary["expected_static_slots"]
            ],
            max_dynamic_slots=primary["max_dynamic_slots"],
        )
        for compatible in compatible_identities
    ]


def _legacy_spec() -> dict:
    return _compatible_specs()[0]


def _x_row(external_id: str, *, age_seconds: int = 900) -> dict:
    return {
        "source": "x",
        "external_id": external_id,
        "ticker": "@TREND_WORLD",
        "labels": ["@TREND_WORLD"],
        "created_utc": _CUTOFF.timestamp() - age_seconds,
        "fetched_utc": _CUTOFF.timestamp() - age_seconds + 10,
        "author": f"public-{external_id}",
        "body": f"A sufficiently detailed public reaction about {external_id}",
        "metadata": {
            "evidence_role": "unverified_public_reaction",
            "author_id": str(1000 + age_seconds),
            "account_created_utc": 1.0,
            "automation_signals_complete": True,
            "verified_type": "none",
            "automation_risk": 0.0,
            "engagement": {
                "like_count": 1,
                "reply_count": 0,
                "retweet_count": 0,
                "quote_count": 0,
            },
            "author_metrics": {
                "followers_count": 100,
                "following_count": 50,
                "tweet_count": 500,
            },
        },
    }


def _news_row() -> dict:
    theme, queries = next(
        iter(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["broad_news_queries"].items())
    )
    query = queries[0]
    return {
        "source": "globalnews",
        "external_id": "news-1",
        "ticker": "@WORLD",
        "labels": ["@WORLD", global_news_query_slot_label(theme, query)],
        "created_utc": _CUTOFF.timestamp() - 600,
        "fetched_utc": _CUTOFF.timestamp() - 590,
        "author": "Reuters",
        "title": "A global event changes risk expectations",
        "body": "Independent editorial evidence.",
        "metadata": {"publisher_domain": "reuters.com"},
    }


def _cycle(*, status: str, lineage: list[dict], spec: dict | None = None) -> dict:
    spec = spec or _spec()
    started = _CUTOFF.timestamp() - 120
    terminal = _CUTOFF.timestamp() - 60
    raw_ids = sorted({item["raw_content_id"] for item in lineage})
    manifest = {
        "schema_version": 2,
        "server_started_utc": started,
        "server_terminal_utc": terminal,
        "collector_build_id": _BUILD_ID,
        "slot_receipts": [
            {
                "provider": "x",
                "fetch_run_id": _FETCH_ID,
                "raw_content_ids": raw_ids,
            }
        ],
    }
    return {
        "identity_valid": True,
        "identity": spec["identity"],
        "status": status,
        "manifest_valid": True,
        "manifest": manifest,
        "manifest_id": "cycle_manifest_" + "c" * 24,
        "collector_semantics_id": spec["identity"]["collector_semantics_id"],
        "collector_build_id": _BUILD_ID,
        "server_started_utc": started,
        "server_terminal_utc": terminal,
    }


class _Store:
    def __init__(self, cycle, lineage=(), *, cycle_id: str | None = None):
        self.cycles = (
            {}
            if cycle is None
            else {(cycle_id or _spec()["collection_cycle_id"]): cycle}
        )
        self.lineage = list(lineage)
        self.requested_cycle_ids = []
        self.lineage_cycle_ids = []
        self.closed = False

    def collection_cycle(self, cycle_id):
        self.requested_cycle_ids.append(cycle_id)
        return self.cycles.get(cycle_id)

    def collection_cycle_formal_lineage(self, cycle_id, *, provider):
        assert cycle_id in self.cycles
        assert provider == "x"
        self.lineage_cycle_ids.append(cycle_id)
        return list(self.lineage)

    def coverage_report(self, *_args, **_kwargs):
        return {
            "complete": True,
            "missing_source_groups": [],
            "missing_query_slots": [],
            "query_slots": [],
        }

    def close(self):
        self.closed = True


def _lineage(row: dict) -> dict:
    return {
        "fetch_run_id": _FETCH_ID,
        "evidence_id": evidence_id(row),
        "raw_content_id": raw_content_id(row),
    }


@pytest.mark.unit
def test_missing_x_cycle_is_explicit_and_preserves_news():
    news = _news_row()
    store = _Store(None)

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, _x_row("unbound")]
    )

    assert availability["state"] == "missing"
    assert availability["period_key"] == "2026-01-10"
    assert availability["eligible_lineage"] == []
    assert rows == [news]
    assert store.requested_cycle_ids == [
        _spec()["collection_cycle_id"],
        *(spec["collection_cycle_id"] for spec in _compatible_specs()),
    ]


@pytest.mark.unit
def test_incomplete_x_cycle_is_explicit_and_preserves_news():
    news = _news_row()
    store = _Store(_cycle(status="incomplete", lineage=[]))

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, _x_row("partial")]
    )

    assert availability["state"] == "incomplete"
    assert availability["cycle_manifest"]["schema_version"] == 2
    assert availability["eligible_lineage"] == []
    assert rows == [news]


@pytest.mark.unit
def test_complete_x_cycle_with_no_eligible_rows_is_valid_observed_empty():
    news = _news_row()
    store = _Store(_cycle(status="complete", lineage=[]))

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, _x_row("not-in-cycle")]
    )

    assert availability["state"] == "complete_zero_eligible"
    assert availability["eligible_lineage"] == []
    assert rows == [news]


@pytest.mark.unit
def test_complete_x_cycle_content_binds_authorized_rows_into_selection():
    news = _news_row()
    current = _x_row("current")
    lineage = [_lineage(current)]
    store = _Store(_cycle(status="complete", lineage=lineage), lineage)

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, current]
    )
    unbound = evidence_selection_manifest(rows, as_of_utc=_CUTOFF.timestamp())
    selection = bind_x_availability_to_selection(unbound, availability)

    assert availability["state"] == "complete_with_eligible"
    assert rows == [news, current]
    assert availability["eligible_lineage"] == [
        {
            "evidence_id": evidence_id(current),
            "raw_content_id": raw_content_id(current),
            "fetch_run_ids": [_FETCH_ID],
        }
    ]
    assert selection["schema_version"] == 3
    assert selection["manifest_id"] != unbound["manifest_id"]
    assert selection["x_cycle_availability"]["availability_id"] == availability[
        "availability_id"
    ]


@pytest.mark.unit
def test_registered_legacy_collector_cycle_remains_exactly_usable():
    news = _news_row()
    historical = _x_row("historical-compatible")
    lineage = [_lineage(historical)]
    spec = _legacy_spec()
    store = _Store(
        _cycle(status="complete", lineage=lineage, spec=spec),
        lineage,
        cycle_id=spec["collection_cycle_id"],
    )

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, historical]
    )

    compatible = GLOBAL_EVENT_V2_PROTOCOL["evidence"][
        "compatible_collector_identities"
    ][0]
    assert availability["state"] == "complete_with_eligible"
    assert rows == [news, historical]
    assert availability["collection_cycle_id"] == spec["collection_cycle_id"]
    assert availability["selected_collection_cycle"] == {
        "collection_cycle_id": spec["collection_cycle_id"],
        "protocol_id": compatible["protocol_id"],
        "collector_semantics_id": compatible["collector_semantics_id"],
        "compatibility_reason": compatible["reason"],
        "primary": False,
    }
    assert store.requested_cycle_ids == [
        _spec()["collection_cycle_id"],
        spec["collection_cycle_id"],
    ]
    assert store.lineage_cycle_ids == [spec["collection_cycle_id"]]
    selection = bind_x_availability_to_selection(
        evidence_selection_manifest(rows, as_of_utc=_CUTOFF.timestamp()),
        availability,
    )
    validate_bound_x_selection(selection, tuple(rows))


@pytest.mark.unit
def test_bound_selection_rejects_an_unregistered_compatible_identity():
    news = _news_row()
    historical = _x_row("historical-compatible")
    lineage = [_lineage(historical)]
    spec = _legacy_spec()
    store = _Store(
        _cycle(status="complete", lineage=lineage, spec=spec),
        lineage,
        cycle_id=spec["collection_cycle_id"],
    )
    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, historical]
    )
    forged = {
        **availability,
        "selected_collection_cycle": {
            **availability["selected_collection_cycle"],
            "protocol_id": "protocol_" + "0" * 24,
        },
    }
    forged_payload = {key: value for key, value in forged.items() if key != "availability_id"}
    forged["availability_id"] = content_id(forged_payload, prefix="xavail_")
    selection = bind_x_availability_to_selection(
        evidence_selection_manifest(rows, as_of_utc=_CUTOFF.timestamp()), forged
    )

    with pytest.raises(ValueError, match="unregistered collector identity"):
        validate_bound_x_selection(selection, tuple(rows))


@pytest.mark.unit
def test_incomplete_primary_cycle_cannot_fall_back_to_compatible_cycle():
    primary = _cycle(status="incomplete", lineage=[])
    legacy_spec = _legacy_spec()
    legacy = _cycle(status="complete", lineage=[], spec=legacy_spec)
    store = _Store(primary)
    store.cycles[legacy_spec["collection_cycle_id"]] = legacy

    availability, rows = project_x_cycle_availability(
        store,
        cutoff=_CUTOFF,
        candidate_rows=[_news_row(), _x_row("must-not-fall-back")],
    )

    assert availability["state"] == "incomplete"
    assert availability["selected_collection_cycle"]["primary"] is True
    assert rows == [_news_row()]
    assert store.requested_cycle_ids == [_spec()["collection_cycle_id"]]


@pytest.mark.unit
def test_research_compatible_precedence_never_falls_through_on_outcome():
    first_spec, second_spec = _compatible_specs()[:2]
    first = _cycle(status="incomplete", lineage=[], spec=first_spec)
    second = _cycle(status="complete", lineage=[], spec=second_spec)
    store = _Store(first, cycle_id=first_spec["collection_cycle_id"])
    store.cycles[second_spec["collection_cycle_id"]] = second

    availability, rows = project_x_cycle_availability(
        store,
        cutoff=_CUTOFF,
        candidate_rows=[_news_row(), _x_row("must-not-select-by-outcome")],
    )

    assert availability["state"] == "incomplete"
    assert availability["collection_cycle_id"] == first_spec["collection_cycle_id"]
    assert rows == [_news_row()]
    assert store.requested_cycle_ids == [
        _spec()["collection_cycle_id"],
        first_spec["collection_cycle_id"],
    ]


@pytest.mark.unit
def test_media_snapshot_rejects_stale_x_outside_exact_prior_day_cycle(monkeypatch):
    news = _news_row()
    current = _x_row("current")
    stale = _x_row("older-cycle", age_seconds=2 * 86400)
    lineage = [_lineage(current)]
    store = _Store(_cycle(status="complete", lineage=lineage), lineage)
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.open_store",
        lambda *_args, **_kwargs: store,
    )
    monkeypatch.setattr(
        "tradingagents.research.snapshot.evidence_window",
        lambda *_args, **_kwargs: [news, stale, current],
    )
    monkeypatch.setattr(
        "tradingagents.research.snapshot.bind_receipt_coverage_to_selection",
        lambda receipt, _selection: {**receipt, "complete": True},
    )
    monkeypatch.setattr(
        "tradingagents.research.snapshot._require_xnys_sessions",
        lambda _dates: None,
    )

    snapshot = build_media_snapshot(
        db_url="postgresql://read-only",
        run_id="x-cycle-snapshot",
        decision_dates=(_DECISION_DATE,),
    )

    snapshot_slice = snapshot.slices[0]
    x_ids = [
        row["external_id"]
        for row in snapshot_slice.raw_evidence
        if row.get("source") == "x"
    ]
    assert x_ids == ["current"]
    assert snapshot_slice.coverage["complete"] is True
    assert snapshot_slice.coverage["x_cycle_availability"]["state"] == (
        "complete_with_eligible"
    )
    assert snapshot_slice.selection_manifest["x_cycle_availability"]["availability_id"]
    assert store.closed is True
