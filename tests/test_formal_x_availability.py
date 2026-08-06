"""Exact prior-day X-cycle availability at the formal forecast boundary."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from tradingagents import poller
from tradingagents.dataflows import media_store
from tradingagents.dataflows.media_store import SqliteMediaStore
from tradingagents.evidence_lineage import evidence_id
from tradingagents.formal_experiment import (
    _bind_x_availability_to_selection,
    _finalized_x_cycle_availability,
    _formal_x_cycle_availability,
)
from tradingagents.formal_verifier import _validate_x_cycle_availability
from tradingagents.global_research import evidence_selection_manifest
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL, content_id


def _x_row(cutoff: datetime, external_id: str = "public-reaction") -> dict:
    return {
        "source": "x",
        "external_id": external_id,
        "ticker": "@TREND_WORLD",
        "labels": ["@TREND_WORLD"],
        "subreddit": None,
        "author": "publicvoice",
        "sentiment": None,
        "created_utc": cutoff.timestamp() - 3_600,
        "title": "Public reaction to a consequential global development",
        "body": "Public reaction to a consequential global development",
        "fetched_utc": cutoff.timestamp() - 1_800,
        "metadata": {
            "evidence_role": "unverified_public_reaction",
            "author_id": "123",
            "author_username": "publicvoice",
            "account_created_utc": cutoff.timestamp() - 100_000,
            "automation_signals_complete": True,
            "verified_type": "none",
            "automation_risk": 0.1,
            "engagement": {
                "like_count": 5,
                "reply_count": 1,
                "retweet_count": 1,
                "quote_count": 0,
            },
            "author_metrics": {
                "followers_count": 100,
                "following_count": 40,
                "tweet_count": 500,
            },
        },
    }


def _start_prior_day_cycle(
    store: SqliteMediaStore,
    cutoff: datetime,
    clock: dict[str, float],
    *,
    x_rows: list[dict] | None = None,
    omit_last_static: bool = False,
    terminal_after_cutoff: bool = False,
) -> tuple[dict, list[dict]]:
    period = cutoff.date() - timedelta(days=1)
    period_utc = datetime.combine(
        period, datetime.min.time(), tzinfo=timezone.utc
    ).timestamp()
    spec = poller._x_collection_cycle_spec(
        period_utc,
        int(GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "max_x_search_requests_per_utc_day"
        ]),
    )
    caller_started = cutoff.timestamp() - 2_000
    clock["now"] = cutoff.timestamp() - 1_000
    cycle_id = store.start_collection_cycle(spec, started_utc=caller_started)
    static_slots = [
        (slot["provider"], slot["query_key"])
        for slot in spec["identity"]["expected_static_slots"]
    ]
    for index, (provider, query_key) in enumerate(static_slots):
        if omit_last_static and index == len(static_slots) - 1:
            continue
        started = caller_started + 10 + index * 10
        clock["now"] += 1
        run_id = store.start_fetch(
            provider, query_key, started, collection_cycle_id=cycle_id
        )
        clock["now"] += 1
        store.finish_fetch(
            run_id,
            status="empty",
            received_utc=started + 1,
            completed_utc=started + 2,
            item_count=0,
            inserted_count=0,
            formal_eligible_item_count=0,
            formal_eligible_evidence_ids=[],
            formal_eligible_lineage=[],
        )

    stored_x_rows: list[dict] = []
    if x_rows is not None:
        query_key = "global public reaction query"
        declared = caller_started + 100
        store.declare_collection_cycle_slots(
            cycle_id, [("x", query_key)], declared_utc=declared
        )
        clock["now"] += 1
        run_id = store.start_fetch(
            "x", query_key, declared + 1, collection_cycle_id=cycle_id
        )
        stored_x_rows = [
            {**row, "fetched_utc": declared + 2} for row in x_rows
        ]
        eligible_ids = sorted(evidence_id(row) for row in stored_x_rows)
        clock["now"] += 1
        store.complete_fetch(
            run_id,
            rows=stored_x_rows,
            status="success" if stored_x_rows else "empty",
            received_utc=declared + 2,
            completed_utc=declared + 3,
            formal_eligible_item_count=len(eligible_ids),
            formal_eligible_evidence_ids=eligible_ids,
        )

    clock["now"] = (
        cutoff.timestamp() + 1
        if terminal_after_cutoff
        else cutoff.timestamp() - 100
    )
    cycle = store.finish_collection_cycle(
        cycle_id, completed_utc=caller_started + 500
    )
    return cycle, stored_x_rows


@pytest.fixture
def fixed_clock_store(tmp_path, monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(media_store.time, "time", lambda: clock["now"])
    store = SqliteMediaStore(tmp_path / "formal-x.db")
    yield store, clock
    store.close()


@pytest.mark.unit
def test_exact_prior_day_complete_cycle_admits_only_receipted_eligible_x(
    fixed_clock_store,
):
    store, clock = fixed_clock_store
    cutoff = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    cycle, stored_rows = _start_prior_day_cycle(
        store, cutoff, clock, x_rows=[_x_row(cutoff)]
    )

    availability, filtered = _formal_x_cycle_availability(
        store,
        cutoff,
        stored_rows + [_x_row(cutoff, "unreceipted-stale-row")],
    )

    assert cycle["status"] == "complete"
    assert availability["state"] == "complete_with_eligible"
    assert availability["collection_cycle_id"] == cycle["collection_cycle_id"]
    assert availability["manifest_id"] == cycle["manifest_id"]
    assert availability["collector_build_id"] == cycle["collector_build_id"]
    assert availability["server_terminal_utc"] <= cutoff.timestamp()
    assert [row["external_id"] for row in filtered] == ["public-reaction"]
    assert availability["eligible_lineage"] == [{
        "evidence_id": evidence_id(stored_rows[0]),
        "raw_content_id": media_store.raw_content_id(stored_rows[0]),
        "fetch_run_ids": [
            next(
                receipt["fetch_run_id"]
                for receipt in cycle["manifest"]["slot_receipts"]
                if receipt["provider"] == "x"
            )
        ],
    }]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cycle_mode", "expected_state"),
    [
        ("missing", "missing"),
        ("incomplete", "incomplete"),
        ("complete-zero", "complete_zero_eligible"),
        ("late-terminal", "incomplete"),
    ],
)
def test_unavailable_or_zero_cycle_never_falls_back_to_stale_x(
    fixed_clock_store, cycle_mode, expected_state,
):
    store, clock = fixed_clock_store
    cutoff = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    if cycle_mode == "incomplete":
        _start_prior_day_cycle(store, cutoff, clock, omit_last_static=True)
    elif cycle_mode == "complete-zero":
        _start_prior_day_cycle(store, cutoff, clock)
    elif cycle_mode == "late-terminal":
        _start_prior_day_cycle(
            store, cutoff, clock, terminal_after_cutoff=True
        )

    availability, filtered = _formal_x_cycle_availability(
        store, cutoff, [_x_row(cutoff, "stale-unbound-x")]
    )

    assert availability["state"] == expected_state
    assert availability["eligible_lineage"] == []
    assert filtered == []
    if cycle_mode == "late-terminal":
        assert availability["cycle_manifest"] is None
        assert availability["server_terminal_utc"] is None


@pytest.mark.unit
def test_selection_and_offline_verifier_bind_missing_x_to_neutral_reuse(
    fixed_clock_store,
):
    store, _clock = fixed_clock_store
    cutoff = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    availability, rows = _formal_x_cycle_availability(store, cutoff, [])
    selection = _bind_x_availability_to_selection(
        evidence_selection_manifest(rows, as_of_utc=cutoff.timestamp()),
        availability,
    )
    champion = {"evidence": [], "bundle": "same"}
    coverage = {"x_cycle_availability": availability}
    errors: list[str] = []

    _validate_x_cycle_availability(
        availability,
        cutoff=cutoff,
        selection_manifest=selection,
        coverage=coverage,
        champion=champion,
        without_public=deepcopy(champion),
        public_only=None,
        errors=errors,
    )

    assert selection["schema_version"] == 3
    assert selection["manifest_id"] == content_id(
        {key: value for key, value in selection.items() if key != "manifest_id"},
        prefix="selection_",
    )
    assert errors == []

    tampered = deepcopy(availability)
    tampered["period_key"] = "2026-08-03"
    tampered = _finalized_x_cycle_availability({
        key: value for key, value in tampered.items() if key != "availability_id"
    })
    tamper_errors: list[str] = []
    _validate_x_cycle_availability(
        tampered,
        cutoff=cutoff,
        selection_manifest=selection,
        coverage=coverage,
        champion=champion,
        without_public={"evidence": [], "bundle": "different"},
        public_only={"evidence": []},
        errors=tamper_errors,
    )
    assert "formal X cycle availability identity mismatch" in tamper_errors
    assert "unavailable formal X state did not use the neutral public bundle" in tamper_errors
    assert "unavailable formal X state did not reuse the champion bundle" in tamper_errors
