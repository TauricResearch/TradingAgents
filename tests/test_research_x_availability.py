"""Exact-cycle guarantees for optional public-reaction evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone

import pytest

from tradingagents import poller
from tradingagents.dataflows import media_store
from tradingagents.evidence_lineage import evidence_id, raw_content_id
from tradingagents.global_research import evidence_selection_manifest
from tradingagents.research import x_availability
from tradingagents.research.snapshot import build_media_snapshot
from tradingagents.research.x_availability import (
    _accepted_cycles,
    _select_cycle_x_rows,
    bind_x_availability_to_selection,
    project_x_cycle_availability,
    validate_bound_x_selection,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
    GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
    GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES,
    GLOBAL_EVENT_V2_PROTOCOL,
    content_id,
    global_news_query_slot_label,
)

_DECISION_DATE = date(2026, 1, 9)
_CUTOFF = datetime(2026, 1, 10, tzinfo=timezone.utc)
_BUILD_ID = "build_" + "b" * 24
_FETCH_ID = "ffffffff-ffff-4fff-bfff-ffffffffffff"


def _spec() -> dict:
    return _accepted_cycles(_CUTOFF)[2][0]["spec"]


def _compatible_specs() -> list[dict]:
    return [candidate["spec"] for candidate in _accepted_cycles(_CUTOFF)[2][1:]]


def _legacy_spec() -> dict:
    return _compatible_specs()[0]


@pytest.mark.unit
def test_primary_cycle_uses_the_collection_compatibility_identity():
    identity = _spec()["identity"]
    assert identity["protocol_id"] == GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID
    assert identity["collector_semantics_id"] == (
        GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID
    )


@pytest.mark.unit
def test_legacy_cycle_specs_use_their_frozen_historical_shape(monkeypatch):
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    monkeypatch.setitem(evidence, "x_trend_woeids", [42])
    monkeypatch.setitem(evidence, "max_x_search_requests_per_utc_day", 1)

    legacy = _legacy_spec()["identity"]

    assert [
        (slot["provider"], slot["query_key"])
        for slot in legacy["expected_static_slots"]
    ] == [
        ("trendnews", "ranked-global-discovery"),
        ("xtrend", "woeid:1"),
        ("xtrend", "woeid:23424977"),
    ]
    assert legacy["max_dynamic_slots"] == 3


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
            "profile_screening_complete": True,
            "organization_signals": [],
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
    started = _CUTOFF.timestamp() - 1800
    terminal = _CUTOFF.timestamp() - 60
    raw_ids = sorted({item["raw_content_id"] for item in lineage})
    decision_item = None
    dynamic_slots = [{"provider": "x", "query_key": "ranked-topic"}]
    if spec["identity"]["protocol_id"] == GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID:
        headline = {
            "external_id": "discovery-headline",
            "title": "Bordeaux Wildfires Force Evacuations - Reuters",
            "created_utc": started - 60,
            "publisher": "Reuters",
            "category": "world",
            "region": "US",
            "rank": 0,
            "metadata": {"publisher_domain": "reuters.com"},
        }
        topics = poller._formally_grounded_discovery_topics(
            poller.discover_x_topics(
                max_topics=3, headlines=[headline], trends=[]
            ),
            started,
        )
        requests = poller._group_x_search_topics(topics)
        decision = poller._x_discovery_decision_manifest(
            collection_cycle_id=spec["collection_cycle_id"],
            captured_utc=started,
            max_topics=3,
            headlines=[headline],
            trends=[],
            topics=topics,
            search_requests=requests,
        )
        decision_row = poller.x_discovery_decision_row(decision)
        decision_item = {
            "fetch_run_id": None,
            "raw_content_id": raw_content_id(decision_row),
            "row": {
                **decision_row,
                "latest_observed_utc": terminal,
                "latest_observed_utc_source": "server_terminal_utc",
            },
        }
        dynamic_slots = [
            {"provider": "x", "query_key": request["query_key"]}
            for request in requests
        ]
    slot_receipts = []
    for index, slot in enumerate(spec["identity"]["expected_static_slots"]):
        failed = status == "incomplete" and slot["provider"] == "trendnews"
        is_decision = slot["provider"] == "trendnews" and decision_item is not None
        fetch_run_id = f"00000000-0000-4000-8000-{index + 1:012x}"
        if is_decision:
            decision_item["fetch_run_id"] = fetch_run_id
        slot_receipts.append({
            "slot_kind": "static",
            **slot,
            "fetch_run_id": fetch_run_id,
            "status": "failed" if failed else "success",
            "item_count": 0 if failed else 1,
            "raw_content_ids": (
                [decision_item["raw_content_id"]]
                if is_decision and not failed else []
            ),
        })
    slot_receipts.append({
        "slot_kind": "dynamic",
        **dynamic_slots[0],
        "fetch_run_id": _FETCH_ID,
        "status": "success" if raw_ids else "empty",
        "item_count": len(raw_ids),
        "raw_content_ids": raw_ids,
    })
    manifest = {
        "schema_version": 2,
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": spec["identity"]["cycle_kind"],
        "period_key": spec["identity"]["period_key"],
        "protocol_id": spec["identity"]["protocol_id"],
        "collector_semantics_id": spec["identity"]["collector_semantics_id"],
        "started_utc": started,
        "completed_utc": terminal,
        "status": status,
        "expected_static_slots": spec["identity"]["expected_static_slots"],
        "expected_dynamic_slots": dynamic_slots,
        "slot_receipts": slot_receipts,
        "server_started_utc": started,
        "server_terminal_utc": terminal,
        "collector_build_id": _BUILD_ID,
    }
    return {
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": spec["identity"]["cycle_kind"],
        "period_key": spec["identity"]["period_key"],
        "protocol_id": spec["identity"]["protocol_id"],
        "collector_semantics_id": spec["identity"]["collector_semantics_id"],
        "identity_valid": True,
        "identity": spec["identity"],
        "started_utc": started,
        "completed_utc": terminal,
        "status": status,
        "manifest_valid": True,
        "manifest": manifest,
        "manifest_id": content_id(manifest, prefix="cycle_manifest_"),
        "collector_build_id": _BUILD_ID,
        "server_started_utc": started,
        "server_terminal_utc": terminal,
        "_decision_item": decision_item,
    }


class _Store:
    def __init__(
        self, cycle, lineage=(), *, cycle_id: str | None = None, rows=(),
    ):
        self.cycles = (
            {}
            if cycle is None
            else {(cycle_id or _spec()["collection_cycle_id"]): cycle}
        )
        self.lineage = list(lineage)
        self.rows = {raw_content_id(row): row for row in rows}
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

    def collection_cycle_item_rows(self, cycle_id, *, provider, query_key):
        cycle = self.cycles[cycle_id]
        if provider == "trendnews":
            item = cycle.get("_decision_item")
            return [item] if item is not None else []
        receipt = next(
            item for item in cycle["manifest"]["slot_receipts"]
            if item["provider"] == provider and item["query_key"] == query_key
        )
        return [
            {
                "fetch_run_id": receipt["fetch_run_id"],
                "raw_content_id": raw_id,
                "row": {
                    **self.rows[raw_id],
                    "metadata": {
                        **self.rows[raw_id]["metadata"],
                        "receipt_labels": self.rows[raw_id]["labels"],
                    },
                    "latest_observed_utc": cycle["server_terminal_utc"],
                    "latest_observed_utc_source": "server_terminal_utc",
                },
            }
            for raw_id in receipt["raw_content_ids"]
        ]

    def coverage_report(
        self,
        cutoff_utc,
        required_source_groups,
        *,
        max_age_seconds,
        expected_query_slots,
        require_lineage_query_slots,
        min_started_utc,
        **_kwargs,
    ):
        runs = []
        for index, (provider, query_key) in enumerate(
            expected_query_slots, start=1
        ):
            started = min_started_utc + float(index)
            runs.append({
                "fetch_run_id": f"00000000-0000-4000-8000-{index:012x}",
                "provider": provider,
                "query_key": query_key,
                "started_utc": started,
                "received_utc": started + 0.25,
                "completed_utc": started + 0.5,
                "status": "success",
                "item_count": 1,
                "inserted_count": 1,
                "error": None,
                "formal_eligible_item_count": 0,
                "formal_eligible_evidence_ids_json": "[]",
                "formal_eligible_lineage_json": "[]",
                "cost_units": 1.0,
                "cursor_before": None,
                "cursor_after": None,
                "metadata_json": "{}",
                "collection_cycle_id": None,
                "server_started_utc": started,
                "server_terminal_utc": started + 0.75,
                "collector_build_id": "build_" + "0" * 24,
                "formal_eligible_evidence_ids": [],
                "formal_eligible_lineage": [],
            })
        require_lineage = set(require_lineage_query_slots)
        query_statuses = [
            {
                "provider": run["provider"],
                "query_key": run["query_key"],
                "run": run,
                "allow_empty": False,
                "require_eligible": False,
                "require_lineage": (
                    run["provider"], run["query_key"]
                ) in require_lineage,
            }
            for run in runs
        ]
        source_statuses = {
            provider: next(
                (
                    run
                    for run in reversed(runs)
                    if run["provider"] == provider
                ),
                None,
            )
            for group in required_source_groups
            for provider in group
        }
        return media_store._coverage_result(
            cutoff_utc=cutoff_utc,
            required_source_groups=required_source_groups,
            source_statuses=source_statuses,
            query_statuses=query_statuses,
            max_age_seconds=max_age_seconds,
        )

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
    assert availability["period_key"] == "2026-01-09"
    assert availability["eligible_lineage"] == []
    assert rows == [news]
    assert store.requested_cycle_ids == [
        _spec()["collection_cycle_id"],
        *(spec["collection_cycle_id"] for spec in _compatible_specs()),
    ]


@pytest.mark.unit
def test_compatibility_explanations_do_not_change_x_availability_identity(
    monkeypatch,
):
    baseline, _ = project_x_cycle_availability(
        _Store(None), cutoff=_CUTOFF, candidate_rows=[]
    )
    reworded = tuple(
        {**dict(identity), "reason": f"operator note {index}"}
        for index, identity in enumerate(
            GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES
        )
    )
    monkeypatch.setattr(
        x_availability,
        "GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES",
        reworded,
    )
    changed, _ = project_x_cycle_availability(
        _Store(None), cutoff=_CUTOFF, candidate_rows=[]
    )

    assert changed["availability_id"] == baseline["availability_id"]
    assert all(
        "compatibility_reason" not in identity
        for identity in changed["accepted_collection_cycles"]
    )


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
@pytest.mark.parametrize(
    "mutation",
    ["schema", "provenance", "build", "fetch_id", "raw_id", "manifest_id"],
)
def test_operational_and_research_cycle_structure_reject_the_same_mutations(
    mutation,
):
    spec = _spec()
    cycle = deepcopy(_cycle(status="complete", lineage=[]))
    if mutation == "schema":
        cycle["manifest"]["schema_version"] = 1
    elif mutation == "provenance":
        cycle["manifest"]["server_terminal_utc"] += 1
    elif mutation == "build":
        cycle["collector_build_id"] = "build_invalid"
        cycle["manifest"]["collector_build_id"] = "build_invalid"
    elif mutation == "fetch_id":
        cycle["manifest"]["slot_receipts"][0]["fetch_run_id"] = "not-a-uuid"
    elif mutation == "raw_id":
        cycle["manifest"]["slot_receipts"][-1]["raw_content_ids"] = ["raw_invalid"]
    else:
        cycle["manifest_id"] = "cycle_manifest_" + "0" * 24
    if mutation != "manifest_id":
        cycle["manifest_id"] = content_id(
            cycle["manifest"], prefix="cycle_manifest_"
        )

    assert poller._x_collection_cycle_state(spec, cycle) == "invalid"
    with pytest.raises(ValueError, match="cycle structure is invalid"):
        project_x_cycle_availability(
            _Store(cycle), cutoff=_CUTOFF, candidate_rows=[_news_row()]
        )


@pytest.mark.unit
def test_complete_x_cycle_content_binds_authorized_rows_into_selection():
    news = _news_row()
    current = _x_row("current")
    lineage = [_lineage(current)]
    store = _Store(
        _cycle(status="complete", lineage=lineage), lineage, rows=[current]
    )

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, current]
    )
    unbound = evidence_selection_manifest(rows, as_of_utc=_CUTOFF.timestamp())
    selection = bind_x_availability_to_selection(unbound, availability)

    assert availability["state"] == "complete_with_eligible"
    assert [row["external_id"] for row in rows] == ["news-1", "current"]
    assert rows[-1]["labels"] == ["@TREND_WORLD"]
    assert availability["eligible_lineage"] == [
        {
            "evidence_id": evidence_id(current),
            "raw_content_id": raw_content_id(current),
            "fetch_run_ids": [_FETCH_ID],
            "labels": ["@TREND_WORLD"],
        }
    ]
    assert selection["schema_version"] == 3
    assert selection["manifest_id"] != unbound["manifest_id"]
    assert selection["x_cycle_availability"]["availability_id"] == availability[
        "availability_id"
    ]


@pytest.mark.unit
def test_exact_cycle_replay_removes_cross_cycle_labels_and_newer_content():
    news = _news_row()
    exact = _x_row("repeated-post")
    contaminated = deepcopy(exact)
    contaminated["labels"] = ["@TREND_BUSINESS"]
    contaminated["metadata"]["engagement"]["like_count"] = 99
    lineage = [_lineage(exact)]
    store = _Store(
        _cycle(status="complete", lineage=lineage),
        lineage,
        rows=[exact],
    )

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, contaminated]
    )

    selected = rows[-1]
    assert availability["state"] == "complete_with_eligible"
    assert selected["external_id"] == exact["external_id"]
    assert selected["labels"] == ["@TREND_WORLD"]
    assert selected["metadata"]["engagement"]["like_count"] == 1
    assert availability["eligible_lineage"][0]["raw_content_id"] == raw_content_id(
        exact
    )


@pytest.mark.unit
def test_bound_selection_replays_exact_x_labels_times_and_formal_eligibility():
    news = _news_row()
    exact = _x_row("bound-post")
    lineage = [_lineage(exact)]
    store = _Store(_cycle(status="complete", lineage=lineage), lineage, rows=[exact])
    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, exact]
    )
    selection = bind_x_availability_to_selection(
        evidence_selection_manifest(rows, as_of_utc=_CUTOFF.timestamp()),
        availability,
    )
    validate_bound_x_selection(selection, tuple(rows))

    for mutate in (
        lambda row: row.__setitem__("labels", ["@TREND_BUSINESS"]),
        lambda row: row.__setitem__("latest_observed_utc_source", "client_clock"),
        lambda row: row.__setitem__(
            "latest_observed_utc", availability["server_terminal_utc"] + 1
        ),
    ):
        tampered = deepcopy(rows)
        mutate(tampered[-1])
        rebound = bind_x_availability_to_selection(
            evidence_selection_manifest(
                tampered, as_of_utc=_CUTOFF.timestamp()
            ),
            availability,
        )
        with pytest.raises(ValueError, match="labels|observation time"):
            validate_bound_x_selection(rebound, tuple(tampered))

    ineligible = deepcopy(rows)
    ineligible[-1]["metadata"]["automation_risk"] = 1.0
    forged = deepcopy(availability)
    new_raw_id = raw_content_id(ineligible[-1])
    old_raw_id = forged["eligible_lineage"][0]["raw_content_id"]
    forged["eligible_lineage"][0]["raw_content_id"] = new_raw_id
    for receipt in forged["cycle_manifest"]["slot_receipts"]:
        receipt["raw_content_ids"] = [
            new_raw_id if value == old_raw_id else value
            for value in receipt["raw_content_ids"]
        ]
    forged["manifest_id"] = content_id(
        forged["cycle_manifest"], prefix="cycle_manifest_"
    )
    availability_payload = {
        key: value for key, value in forged.items() if key != "availability_id"
    }
    forged["availability_id"] = content_id(availability_payload, prefix="xavail_")
    rebound = bind_x_availability_to_selection(
        evidence_selection_manifest(ineligible, as_of_utc=_CUTOFF.timestamp()),
        forged,
    )
    with pytest.raises(ValueError, match="not formally eligible"):
        validate_bound_x_selection(rebound, tuple(ineligible))


@pytest.mark.unit
def test_exact_cycle_selection_uses_one_latest_vintage_per_provider_identity():
    older = _x_row("same-provider-id")
    newer = deepcopy(older)
    newer["metadata"]["engagement"]["like_count"] = 5
    evidence = evidence_id(older)
    older_pair = (evidence, raw_content_id(older))
    newer_pair = (evidence, raw_content_id(newer))
    receipt_runs = {
        older_pair: {"00000000-0000-4000-8000-000000000001"},
        newer_pair: {"00000000-0000-4000-8000-000000000002"},
    }
    cycle_rows = {
        older_pair: {
            "row": older,
            "labels": ["@TREND_WORLD"],
            "order": (1.0, 1.0, "00000000-0000-4000-8000-000000000001"),
        },
        newer_pair: {
            "row": newer,
            "labels": ["@TREND_WORLD"],
            "order": (2.0, 2.0, "00000000-0000-4000-8000-000000000002"),
        },
    }

    selected, pairs = _select_cycle_x_rows(
        [newer], receipt_runs, cycle_rows, cutoff_utc=_CUTOFF.timestamp()
    )

    assert selected == [newer]
    assert pairs == {newer_pair}


@pytest.mark.unit
def test_exact_cycle_selection_never_falls_back_from_a_newer_ineligible_vintage():
    older = _x_row("same-provider-id")
    newer = deepcopy(older)
    newer["metadata"]["automation_risk"] = 1.0
    evidence = evidence_id(older)
    older_pair = (evidence, raw_content_id(older))
    newer_pair = (evidence, raw_content_id(newer))
    cycle_rows = {
        older_pair: {
            "row": older,
            "labels": ["@TREND_WORLD"],
            "order": (1.0, 1.0, "00000000-0000-4000-8000-000000000001"),
        },
        newer_pair: {
            "row": newer,
            "labels": ["@TREND_WORLD"],
            "order": (2.0, 2.0, "00000000-0000-4000-8000-000000000002"),
        },
    }

    selected, pairs = _select_cycle_x_rows(
        [newer],
        {older_pair: {"00000000-0000-4000-8000-000000000001"}},
        cycle_rows,
        cutoff_utc=_CUTOFF.timestamp(),
    )

    assert selected == []
    assert pairs == set()


@pytest.mark.unit
def test_legacy_cycle_without_replayable_discovery_is_explicitly_neutral():
    news = _news_row()
    historical = _x_row("historical-compatible")
    lineage = [_lineage(historical)]
    spec = _legacy_spec()
    store = _Store(
        _cycle(status="complete", lineage=lineage, spec=spec),
        lineage,
        cycle_id=spec["collection_cycle_id"],
        rows=[historical],
    )

    availability, rows = project_x_cycle_availability(
        store, cutoff=_CUTOFF, candidate_rows=[news, historical]
    )

    compatible = GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES[0]
    assert availability["state"] == "incomplete"
    assert rows == [news]
    assert availability["collection_cycle_id"] == spec["collection_cycle_id"]
    assert availability["selected_collection_cycle"] == {
        "collection_cycle_id": spec["collection_cycle_id"],
        "protocol_id": compatible["protocol_id"],
        "collector_semantics_id": compatible["collector_semantics_id"],
        "primary": False,
    }
    assert store.requested_cycle_ids == [
        _spec()["collection_cycle_id"],
        spec["collection_cycle_id"],
    ]
    assert store.lineage_cycle_ids == []
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
        rows=[historical],
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
    store = _Store(
        _cycle(status="complete", lineage=lineage), lineage, rows=[current]
    )
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
