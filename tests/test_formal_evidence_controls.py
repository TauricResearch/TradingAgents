"""Leakage, causal-ablation, and collector-cycle controls for formal evidence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradingagents.dataflows.media_store import SqliteMediaStore
from tradingagents.formal_experiment import (
    FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS,
    _formal_collector_cycle_window,
    _formal_coverage,
    _formal_evidence_query_slots,
    _formal_selection_coverage,
    _without_public_reaction_bundle,
)


def _finish(
    store, provider: str, query: str, started: float, status: str = "success",
    *, eligible: int | None = None, server_clock: dict | None = None,
):
    if server_clock is not None:
        server_clock["now"] = started
    run_id = store.start_fetch(provider, query, started)
    eligible_count = 1 if eligible is None and status == "success" else eligible
    eligible_ids = (
        [f"evidence_{int(started):024x}"] if eligible_count == 1 else []
        if eligible_count == 0 else None
    )
    eligible_lineage = (
        [
            {
                "evidence_id": evidence,
                "raw_content_id": f"raw_{int(started):024x}",
            }
            for evidence in eligible_ids
        ]
        if eligible_ids is not None else None
    )
    if server_clock is not None:
        server_clock["now"] = started + 2
    store.finish_fetch(
        run_id,
        status=status,
        received_utc=started + 1,
        completed_utc=started + 2,
        item_count=1 if status == "success" else 0,
        inserted_count=1 if status == "success" else 0,
        formal_eligible_item_count=eligible_count,
        formal_eligible_evidence_ids=eligible_ids,
        formal_eligible_lineage=eligible_lineage,
    )


@pytest.mark.unit
def test_formal_coverage_rejects_slot_success_before_current_cycle_window(
    tmp_path, monkeypatch
):
    store = SqliteMediaStore(tmp_path / "coverage.db")
    clock = {"now": 0.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    cutoff = datetime.fromtimestamp(10_000, timezone.utc)
    interval = 3_600
    _, lower_bound = _formal_collector_cycle_window(cutoff, interval)
    slots = [("globalnews", "world:core"), ("globalnews", "technology:core")]
    _finish(store, *slots[0], lower_bound.timestamp() + 10, server_clock=clock)
    _finish(store, *slots[1], lower_bound.timestamp() - 1, server_clock=clock)

    report = _formal_coverage(store, cutoff, slots, interval_seconds=interval)

    assert not report["complete"]
    assert report["cycle_lower_bound_utc"] == lower_bound.timestamp()
    assert report["missing_query_slots"] == [{
        "provider": "globalnews",
        "query_key": "technology:core",
        "reason": "not_run",
    }]
    store.close()


@pytest.mark.unit
def test_formal_coverage_current_failure_is_not_masked_by_older_success(
    tmp_path, monkeypatch
):
    store = SqliteMediaStore(tmp_path / "outage.db")
    clock = {"now": 0.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    cutoff = datetime.fromtimestamp(20_000, timezone.utc)
    interval = 3_600
    _, lower_bound = _formal_collector_cycle_window(cutoff, interval)
    slot = ("globalnews", "world:core")
    _finish(store, *slot, lower_bound.timestamp() + 10, server_clock=clock)
    _finish(
        store, *slot, cutoff.timestamp() - 100, status="failed",
        server_clock=clock,
    )

    report = _formal_coverage(store, cutoff, [slot], interval_seconds=interval)

    assert not report["complete"]
    assert report["missing_query_slots"][0]["reason"] == "failed"
    store.close()


@pytest.mark.unit
def test_formal_coverage_accepts_every_slot_from_cutoff_cycle(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "complete.db")
    clock = {"now": 0.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    cutoff = datetime.fromtimestamp(30_000, timezone.utc)
    interval = 3_600
    slots = [("globalnews", "world:core"), ("globalnews", "technology:core")]
    for index, slot in enumerate(slots):
        _finish(
            store, *slot, cutoff.timestamp() - 300 + index * 10,
            server_clock=clock,
        )

    report = _formal_coverage(store, cutoff, slots, interval_seconds=interval)

    assert report["complete"]
    assert report["collector_interval_seconds"] == interval
    assert report["cycle_start_grace_seconds"] == FORMAL_COLLECTOR_CYCLE_START_GRACE_SECONDS
    assert all(slot["healthy"] for slot in report["query_slots"])
    store.close()


@pytest.mark.unit
def test_formal_coverage_accepts_successful_observed_absence_of_eligible_news(
    tmp_path, monkeypatch
):
    store = SqliteMediaStore(tmp_path / "ineligible.db")
    clock = {"now": 0.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    cutoff = datetime.fromtimestamp(30_000, timezone.utc)
    slot = ("globalnews", "world:core")
    _finish(
        store, *slot, cutoff.timestamp() - 300, eligible=0,
        server_clock=clock,
    )

    report = _formal_coverage(store, cutoff, [slot], interval_seconds=3_600)

    assert report["complete"]
    assert report["missing_query_slots"] == []
    store.close()


@pytest.mark.unit
def test_formal_coverage_rejects_collector_cadence_drift():
    cutoff = datetime.fromtimestamp(30_000, timezone.utc)

    with pytest.raises(ValueError, match="frozen protocol"):
        _formal_collector_cycle_window(cutoff, 7_200)


@pytest.mark.unit
def test_identical_no_reaction_input_reuses_champion_without_invocation():
    rows = [{
        "source": "globalnews", "external_id": "news", "author": "Reuters",
        "title": "Independent global report", "created_utc": 1.0,
    }]
    champion = object()
    invocations = []

    result = _without_public_reaction_bundle(
        champion, rows, list(rows), lambda value: invocations.append(value)
    )

    assert result is champion
    assert invocations == []


@pytest.mark.unit
def test_formal_selection_coverage_allows_audited_empty_slots_but_not_empty_input():
    slots = _formal_evidence_query_slots()
    query_keys = [query_key for _provider, query_key in slots]
    manifest = {
        "selected_evidence_ids_by_query_slot": {
            query_key: (
                ["evidence_000000000000000000000001"]
                if index == 0 else []
            )
            for index, query_key in enumerate(query_keys)
        }
    }

    report = _formal_selection_coverage(manifest, slots)

    assert report["complete"]
    assert len(report["observed_absent_query_slots"]) == len(query_keys) - 1
    for query_key in query_keys:
        manifest["selected_evidence_ids_by_query_slot"][query_key] = []
    assert not _formal_selection_coverage(manifest, slots)["complete"]


@pytest.mark.unit
def test_distinct_no_reaction_input_invokes_once():
    news = {
        "source": "globalnews", "external_id": "news", "author": "Reuters",
        "title": "Independent global report", "created_utc": 1.0,
    }
    reaction = {
        "source": "x", "external_id": "reaction", "author": "publicvoice",
        "body": "Public reaction to a consequential global event", "created_utc": 2.0,
        "fetched_utc": 3.0,
        "labels": ["@TREND_WORLD"],
        "metadata": {
            "evidence_role": "unverified_public_reaction",
            "author_id": "123",
            "account_created_utc": 1.0,
            "automation_signals_complete": True,
            "automation_risk": 0.0,
            "engagement": {
                "like_count": 1, "reply_count": 0,
                "retweet_count": 0, "quote_count": 0,
            },
            "author_metrics": {
                "followers_count": 10, "following_count": 10, "tweet_count": 10,
            },
        },
    }
    champion = object()
    ablation = object()
    invocations = []

    result = _without_public_reaction_bundle(
        champion,
        [news, reaction],
        [news],
        lambda value: invocations.append(value) or ablation,
    )

    assert result is ablation
    assert invocations == [[news]]
