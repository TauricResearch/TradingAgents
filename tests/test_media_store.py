"""Media store: dedup, stats, look-ahead-safe windowing, and URL routing.

Exercises the default stdlib SQLite backend (no extra deps). The SQLAlchemy
backend shares the same interface and dedup semantics; it's covered indirectly
by the routing test and exercised live against a real DB.
"""
import json
import threading
from collections import Counter
from datetime import datetime, timezone

import pytest

from tradingagents.dataflows import media_store as media_store_module
from tradingagents.dataflows.media_store import (
    SqlAlchemyMediaStore,
    SqliteMediaStore,
    _history_bounds,
    _normalize_pg_url,
    _window_bounds,
    collection_cycle_spec,
    open_store,
)
from tradingagents.evidence_lineage import evidence_id, raw_content_id


def _epoch(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()


def _eid(index: int) -> str:
    return f"evidence_{index:024x}"


def _lineage(evidence_ids: list[str]) -> list[dict]:
    return [
        {"evidence_id": value, "raw_content_id": f"raw_{index:024x}"}
        for index, value in enumerate(evidence_ids, start=1)
    ]


def _fetch_receipt(store, fetch_run_id: str) -> dict:
    return next(
        run for run in store.fetch_runs() if run["fetch_run_id"] == fetch_run_id
    )


def _server_cutoff(store, *fetch_run_ids: str, offset: float = 1.0) -> float:
    terminals = [
        float(_fetch_receipt(store, run_id)["server_terminal_utc"])
        for run_id in fetch_run_ids
    ]
    return max(terminals) + offset


def _row(source, ext_id, ticker, created, **kw):
    base = {"source": source, "external_id": ext_id, "ticker": ticker,
            "subreddit": None, "author": None, "sentiment": None,
            "created_utc": created, "title": None, "body": "", "fetched_utc": 0.0}
    base.update(kw)
    return base


def _complete_x_receipt(
    store, external_id, received, labels, automation_risk,
    *, set_server_time, server_started, server_terminal, created=90.0,
):
    set_server_time(server_started)
    run = store.start_fetch(
        "x",
        f"topic:{labels[0]}",
        received - 1,
        metadata={"kind": "media", "labels": labels},
    )
    row = _row(
        "x", external_id, labels[0], created,
        fetched_utc=received, author="public-user", body="Public reaction",
        labels=labels,
        metadata={"author_id": "42", "automation_risk": automation_risk},
    )
    set_server_time(server_terminal)
    store.complete_fetch(
        run,
        rows=[row],
        status="success",
        received_utc=received,
        completed_utc=received + 1,
    )


def _assert_authenticated_receipt_cutoff(store, set_server_time):
    _complete_x_receipt(
        store, "known", 100.0, ["@WORLD"], 0.1,
        set_server_time=set_server_time, server_started=1_000.0,
        server_terminal=1_001.0,
    )
    _complete_x_receipt(
        store, "known", 200.0, ["@LATE"], 0.9,
        set_server_time=set_server_time, server_started=80_000.0,
        server_terminal=90_000.0,
    )
    _complete_x_receipt(
        store, "straddling-only", 300.0, ["@WORLD"], 0.5,
        set_server_time=set_server_time, server_started=80_010.0,
        server_terminal=90_010.0, created=95.0,
    )

    rows = store.history_asof("1970-01-01", "1970-01-01", sources=["x"])

    assert [row["external_id"] for row in rows] == ["known"]
    assert rows[0]["metadata"]["automation_risk"] == 0.1
    assert rows[0]["labels"] == ["@WORLD"]
    assert rows[0]["latest_observed_utc"] == 1_001.0
    assert rows[0]["latest_observed_utc_source"] == "server_terminal_utc"
    assert [
        row["external_id"]
        for row in store.history_asof(
            "1970-01-01", "1970-01-01",
            tickers=["@WORLD"], sources=["x"], limit=1,
        )
    ] == ["known"]
    assert store.history_asof(
        "1970-01-01", "1970-01-01", tickers=["@LATE"], sources=["x"]
    ) == []


@pytest.fixture
def store(tmp_path):
    s = SqliteMediaStore(tmp_path / "media.db")
    yield s
    s.close()


@pytest.mark.unit
def test_sqlite_server_observed_utc_uses_database_clock(store, monkeypatch):
    monkeypatch.setattr(
        media_store_module, "_sqlite_server_observed_utc", lambda _conn: 1234.5
    )

    assert store.server_observed_utc() == 1234.5


@pytest.mark.unit
def test_store_dedups_on_source_and_external_id(store):
    rows = [_row("stocktwits", "1", "NVDA", _epoch("2026-06-20 10:00")),
            _row("stocktwits", "2", "NVDA", _epoch("2026-06-20 11:00"))]
    assert store.store(rows) == 2          # both new
    assert store.store(rows) == 0          # same ids → no new inserts
    # Same external_id under a different source is a distinct row.
    assert store.store([_row("reddit", "1", "NVDA", _epoch("2026-06-20 12:00"))]) == 1


@pytest.mark.unit
def test_duplicate_evidence_preserves_every_theme_association(store):
    first = _row("globalnews", "same", "@RATES", _epoch("2026-06-20 10:00"),
                 fetched_utc=_epoch("2026-06-20 10:01"))
    second = {**first, "ticker": "@TRADE", "labels": ["@TRADE"]}
    assert store.store([first]) == 1
    assert store.store([second]) == 0
    rates = store.history_asof(
        "2026-06-19", "2026-06-20", tickers=["@RATES"]
    )
    trade = store.history_asof(
        "2026-06-19", "2026-06-20", tickers=["@TRADE"]
    )
    assert rates[0]["labels"] == ["@RATES", "@TRADE"]
    assert trade[0]["external_id"] == "same"


@pytest.mark.unit
def test_formal_identity_rejects_cross_poll_provenance_drift(store):
    first = _row(
        "globalnews", "same-story", "@WORLD", _epoch("2026-06-20 10:00"),
        fetched_utc=_epoch("2026-06-20 10:01"), author="Reuters",
        title="Independent report", body="Original report",
    )
    first["metadata"] = {
        "publisher_domain": "reuters.com",
        "article_url": "https://news.google.com/articles/same-story",
    }
    store.store([first])
    revised = {
        **first,
        "fetched_utc": _epoch("2026-06-20 11:01"),
        "author": "Local Blog",
        "metadata": {
            **first["metadata"],
            "publisher_domain": "nytimes.com",
        },
    }

    with pytest.raises(ValueError, match="immutable provenance"):
        store.store([revised])

    persisted = store.history_asof("2026-06-20", "2026-06-20", sources=["globalnews"])
    assert persisted[0]["author"] == "Reuters"
    assert persisted[0]["metadata"]["publisher_domain"] == "reuters.com"


@pytest.mark.unit
def test_news_vintage_identity_rejects_provider_lineage_drift(store):
    first = _row(
        "globalnews", "google_news_v1_fixed", "@WORLD", 100.0,
        fetched_utc=101.0, author="Reuters", title="Independent report",
        body="Exact report",
        metadata={
            "provider_external_id": "cluster-a",
            "content_vintage_id": "google_news_v1_fixed",
            "content_vintage_schema_version": 1,
            "publisher_domain": "reuters.com",
        },
    )
    drifted = {
        **first,
        "fetched_utc": 102.0,
        "metadata": {**first["metadata"], "provider_external_id": "cluster-b"},
    }

    store.store([first])
    with pytest.raises(ValueError, match="immutable provenance"):
        store.store([drifted])


@pytest.mark.unit
def test_x_username_rename_keeps_immutable_author_identity(store):
    first = _row(
        "x", "post", "@TREND_WORLD", _epoch("2026-06-20 10:00"),
        fetched_utc=_epoch("2026-06-20 10:01"), author="old_name",
        body="Substantive public reaction",
    )
    first["metadata"] = {"author_id": "123", "author_username": "old_name"}
    renamed = {
        **first,
        "fetched_utc": _epoch("2026-06-20 11:01"),
        "author": "new_name",
        "metadata": {"author_id": "123", "author_username": "new_name"},
    }

    assert store.store([first]) == 1
    assert store.store([renamed]) == 0
    persisted = store.history_asof("2026-06-20", "2026-06-20", sources=["x"])[0]
    assert persisted["metadata"]["author_id"] == "123"
    assert persisted["metadata"]["author_username"] == "new_name"


@pytest.mark.unit
def test_public_reaction_metadata_is_point_in_time(store):
    row = _row(
        "x", "post", "@WORLD", _epoch("2026-06-20 10:00"),
        fetched_utc=_epoch("2026-06-20 10:01"),
    )
    row["metadata"] = {"automation_risk": 0.7, "evidence_role": "public_reaction"}
    store.store([row])
    result = store.history_asof(
        "2026-06-19", "2026-06-20", tickers=["@WORLD"]
    )
    assert result[0]["metadata"]["automation_risk"] == 0.7


@pytest.mark.unit
def test_fetch_coverage_requires_recent_success_not_empty(store):
    run = store.start_fetch("globalnews", "world", 100.0)
    store.finish_fetch(
        run, status="empty", received_utc=101.0, completed_utc=102.0,
        item_count=0, inserted_count=0, formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[],
    )
    assert not store.coverage_report(
        _server_cutoff(store, run), [["globalnews"]]
    )["complete"]

    run = store.start_fetch("trendnews", "discovery", 103.0)
    store.finish_fetch(
        run, status="success", received_utc=104.0, completed_utc=105.0,
        item_count=1, inserted_count=1, formal_eligible_item_count=1,
        formal_eligible_evidence_ids=[_eid(1)],
    )
    report = store.coverage_report(
        _server_cutoff(store, run), [["globalnews", "trendnews"]]
    )
    assert report["complete"]
    assert report["sources"]["trendnews"]["item_count"] == 1


@pytest.mark.unit
def test_fetch_coverage_requires_every_exact_query_slot_in_cycle(store, monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    completed = store.start_fetch("globalnews", "rates:core", 100.0)
    clock["now"] = 102.0
    store.finish_fetch(
        completed, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=2, inserted_count=2, formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[],
    )
    clock["now"] = 90.0
    old = store.start_fetch("globalnews", "technology:core", 90.0)
    clock["now"] = 92.0
    store.finish_fetch(
        old, status="success", received_utc=91.0, completed_utc=92.0,
        item_count=1, inserted_count=1, formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[],
    )

    cutoff = 110.0
    report = store.coverage_report(
        cutoff,
        [["globalnews"]],
        expected_query_slots=[
            ("globalnews", "rates:core"),
            ("globalnews", "technology:core"),
            ("globalnews", "rates:core"),
        ],
        min_started_utc=95.0,
    )

    assert not report["complete"]
    assert len(report["query_slots"]) == 2
    assert report["missing_query_slots"] == [{
        "provider": "globalnews",
        "query_key": "technology:core",
        "reason": "not_run",
    }]
    assert report["query_slots"][0]["healthy"] is True


@pytest.mark.unit
def test_fetch_coverage_accepts_successful_observed_zero_eligible_items(store):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    store.finish_fetch(
        run, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=20, inserted_count=20, formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[], formal_eligible_lineage=[],
    )

    cutoff = _server_cutoff(store, run)
    report = store.coverage_report(
        cutoff,
        [],
        expected_query_slots=[("globalnews", "world:core")],
        require_lineage_query_slots=[("globalnews", "world:core")],
    )

    assert report["complete"]
    assert report["missing_query_slots"] == []
    assert report["query_slots"][0]["run"]["formal_eligible_evidence_ids"] == []
    stricter = store.coverage_report(
        cutoff, [], expected_query_slots=[("globalnews", "world:core")],
        require_eligible_query_slots=[("globalnews", "world:core")],
    )
    assert not stricter["complete"]
    assert stricter["missing_query_slots"][0]["reason"] == "ineligible"


@pytest.mark.unit
def test_formal_receipt_persists_exact_ids_and_exposes_them_in_coverage(store):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    evidence_ids = [_eid(1), _eid(2)]
    store.finish_fetch(
        run, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=3, inserted_count=2, formal_eligible_item_count=2,
        formal_eligible_evidence_ids=evidence_ids,
        formal_eligible_lineage=_lineage(evidence_ids),
    )
    report = store.coverage_report(
        _server_cutoff(store, run),
        [],
        expected_query_slots=[("globalnews", "world:core")],
        require_eligible_query_slots=[("globalnews", "world:core")],
    )
    assert report["complete"]
    assert report["query_slots"][0]["run"]["formal_eligible_evidence_ids"] == evidence_ids
    assert json.loads(report["query_slots"][0]["run"][
        "formal_eligible_evidence_ids_json"
    ]) == evidence_ids
    assert report["query_slots"][0]["run"]["formal_eligible_lineage"] == _lineage(
        evidence_ids
    )


@pytest.mark.unit
def test_atomic_fetch_completion_binds_exact_persisted_snapshot(store):
    run = store.start_fetch(
        "globalnews", "world:core", 100.0, metadata={"kind": "media"}
    )
    row = _row(
        "globalnews", "story", "@WORLD", 99.0, fetched_utc=101.0,
        author="Reuters", title="Independent report", body="Exact body",
        labels=["@WORLD"],
    )
    row["metadata"] = {
        "publisher_domain": "reuters.com",
        "article_url": "https://news.google.com/articles/story",
    }
    eligible = [evidence_id(row)]

    inserted = store.complete_fetch(
        run, rows=[row], status="success", received_utc=101.0,
        completed_utc=102.0, cursor_after=101.0,
        formal_eligible_item_count=1,
        formal_eligible_evidence_ids=eligible,
    )

    assert inserted == 1
    item = store.fetch_items(run)[0]
    assert item == {
        "fetch_run_id": run,
        "source": "globalnews",
        "external_id": "story",
        "raw_content_id": raw_content_id(row),
        "evidence_id": eligible[0],
        "observed_utc": 101.0,
        "formal_eligible": 1,
    }
    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["status"] == "success"
    assert receipt["formal_eligible_lineage"] == [{
        "evidence_id": eligible[0],
        "raw_content_id": raw_content_id(row),
    }]


@pytest.mark.unit
def test_latest_successful_receipt_orders_reverted_content_vintage(store, monkeypatch):
    server_clock = {"now": 0.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: server_clock["now"]
    )
    observations = [
        ("v1", "Original report", 101.0),
        ("v2", "Corrected report", 201.0),
        ("v1", "Original report", 301.0),
    ]
    for index, (external_id, title, received) in enumerate(observations):
        server_clock["now"] = 1_000.0 + index * 2
        run = store.start_fetch("globalnews", "world:core", received - 1)
        row = _row(
            "globalnews", external_id, "@WORLD", 90.0,
            fetched_utc=received, author="Reuters", title=title, body="Exact body",
            metadata={
                "provider_external_id": "provider-cluster",
                "publisher_domain": "reuters.com",
            },
        )
        server_clock["now"] = 1_001.0 + index * 2
        store.complete_fetch(
            run,
            rows=[row],
            status="success",
            received_utc=received,
            completed_utc=received + 1,
            formal_eligible_item_count=1,
            formal_eligible_evidence_ids=[evidence_id(row)],
        )

    rows = store.history_asof(
        "1970-01-01", "1970-01-01", sources=["globalnews"]
    )
    by_id = {row["external_id"]: row for row in rows}

    assert by_id["v1"]["fetched_utc"] == 101.0
    assert by_id["v1"]["latest_observed_utc"] == 1_005.0
    assert by_id["v2"]["latest_observed_utc"] == 1_003.0


@pytest.mark.unit
def test_history_uses_authenticated_receipt_cutoff_for_rows_metadata_and_labels(
    store, monkeypatch
):
    server_clock = {"now": 0.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: server_clock["now"]
    )

    _assert_authenticated_receipt_cutoff(
        store, lambda value: server_clock.__setitem__("now", value)
    )


@pytest.mark.unit
def test_raw_content_id_is_stable_across_receipts_but_binds_decision_metadata():
    row = _row(
        "x", "post", "@WORLD", 99.0, fetched_utc=101.0,
        author="public_user", body="reaction", labels=["@WORLD"],
    )
    row["metadata"] = {
        "author_id": "42", "engagement": {"like_count": 10},
        "automation_signals_complete": True,
    }
    repeated = {**row, "fetched_utc": 201.0, "labels": ["@OTHER"]}
    revised = {
        **repeated,
        "metadata": {**row["metadata"], "engagement": {"like_count": 11}},
    }

    assert raw_content_id(repeated) == raw_content_id(row)
    assert raw_content_id(revised) != raw_content_id(row)


@pytest.mark.unit
def test_atomic_fetch_completion_rolls_back_rows_and_lineage_on_receipt_failure(store):
    run = store.start_fetch(
        "globalnews", "world:core", 100.0, metadata={"kind": "media"}
    )
    row = _row(
        "globalnews", "must-rollback", "@WORLD", 99.0,
        fetched_utc=101.0, author="Reuters", title="Report",
    )
    row["metadata"] = {"publisher_domain": "reuters.com"}

    with pytest.raises(ValueError, match="zero counts"):
        store.complete_fetch(
            run, rows=[row], status="empty", received_utc=101.0,
            completed_utc=102.0, formal_eligible_item_count=0,
            formal_eligible_evidence_ids=[],
        )

    assert store.fetch_items(run) == []
    assert store.history_asof("1970-01-01", "1970-01-02") == []
    assert store.fetch_runs(provider="globalnews")[0]["status"] == "running"


@pytest.mark.unit
def test_atomic_empty_receipt_has_explicit_empty_content_lineage(store):
    run = store.start_fetch(
        "globalnews", "world:core", 100.0, metadata={"kind": "media"}
    )
    assert store.complete_fetch(
        run, rows=[], status="empty", received_utc=101.0,
        completed_utc=102.0, formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[],
    ) == 0
    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["formal_eligible_evidence_ids"] == []
    assert receipt["formal_eligible_lineage"] == []
    assert store.fetch_items(run) == []


@pytest.mark.unit
def test_fetch_item_lineage_is_append_only_and_rejects_post_completion_insert(store):
    run = store.start_fetch("x", "topic", 100.0, metadata={"kind": "media"})
    row = _row("x", "post", "@WORLD", 99.0, fetched_utc=101.0, body="reaction")
    store.complete_fetch(
        run, rows=[row], status="success", received_utc=101.0,
        completed_utc=102.0,
    )

    with pytest.raises(Exception, match="append-only"):
        store.conn.execute(
            "UPDATE fetch_run_items SET observed_utc=103 WHERE fetch_run_id=?", (run,)
        )
    store.conn.rollback()
    with pytest.raises(Exception, match="append-only"):
        store.conn.execute("DELETE FROM fetch_run_items WHERE fetch_run_id=?", (run,))
    store.conn.rollback()
    item = store.fetch_items(run)[0]
    with pytest.raises(Exception, match="matching running receipt"):
        store.conn.execute(
            "INSERT INTO fetch_run_items VALUES (?,?,?,?,?,?,?)",
            (
                run, "x", "another", f"raw_{1:024x}", f"evidence_{1:024x}",
                103.0, 0,
            ),
        )
    store.conn.rollback()
    assert store.fetch_items(run) == [item]


@pytest.mark.unit
def test_concurrent_terminal_writers_allow_exactly_one_atomic_completion(tmp_path):
    path = tmp_path / "concurrent.db"
    creator = SqliteMediaStore(path)
    run = creator.start_fetch("x", "topic", 100.0, metadata={"kind": "media"})
    creator.close()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def complete() -> None:
        worker = SqliteMediaStore(path)
        row = _row("x", "post", "@WORLD", 99.0, fetched_utc=101.0, body="reaction")
        barrier.wait()
        try:
            worker.complete_fetch(
                run, rows=[row], status="success", received_utc=101.0,
                completed_utc=102.0,
            )
            outcomes.append("success")
        except ValueError:
            outcomes.append("conflict")
        finally:
            worker.close()

    threads = [threading.Thread(target=complete) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ["conflict", "success"]
    verifier = SqliteMediaStore(path)
    assert verifier.fetch_runs(provider="x")[0]["status"] == "success"
    assert len(verifier.fetch_items(run)) == 1
    verifier.close()


@pytest.mark.unit
def test_formal_receipt_rejects_count_list_mismatch_and_duplicate_ids(store):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    with pytest.raises(ValueError, match="count/list is inconsistent"):
        store.finish_fetch(
            run, status="success", received_utc=101.0, completed_utc=102.0,
            item_count=2, inserted_count=2, formal_eligible_item_count=2,
            formal_eligible_evidence_ids=[_eid(1)],
        )
    with pytest.raises(ValueError, match="sorted and unique"):
        store.finish_fetch(
            run, status="success", received_utc=101.0, completed_utc=102.0,
            item_count=2, inserted_count=2, formal_eligible_item_count=2,
            formal_eligible_evidence_ids=[_eid(1), _eid(1)],
        )
    store.finish_fetch(
        run, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=2, inserted_count=2, formal_eligible_item_count=1,
        formal_eligible_evidence_ids=[_eid(1)],
    )


@pytest.mark.unit
def test_coverage_fails_closed_on_corrupt_eligible_id_lineage(store):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    store.finish_fetch(
        run, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=1, inserted_count=1, formal_eligible_item_count=1,
        formal_eligible_evidence_ids=[_eid(1)],
    )
    store.conn.execute(
        "UPDATE fetch_runs SET formal_eligible_evidence_ids_json='[]' "
        "WHERE fetch_run_id=?",
        (run,),
    )
    store.conn.commit()
    report = store.coverage_report(
        _server_cutoff(store, run),
        [],
        expected_query_slots=[("globalnews", "world:core")],
        require_eligible_query_slots=[("globalnews", "world:core")],
    )
    assert not report["complete"]
    assert report["missing_query_slots"][0]["reason"] == "invalid_lineage"


@pytest.mark.unit
def test_coverage_fails_closed_on_non_string_content_lineage(store):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    evidence_ids = [_eid(1)]
    store.finish_fetch(
        run, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=1, inserted_count=1, formal_eligible_item_count=1,
        formal_eligible_evidence_ids=evidence_ids,
        formal_eligible_lineage=_lineage(evidence_ids),
    )
    store.conn.execute(
        "UPDATE fetch_runs SET formal_eligible_lineage_json=? "
        "WHERE fetch_run_id=?",
        (json.dumps([{"evidence_id": 1, "raw_content_id": f'raw_{1:024x}'}]), run),
    )
    store.conn.commit()

    report = store.coverage_report(
        _server_cutoff(store, run),
        [],
        expected_query_slots=[("globalnews", "world:core")],
        require_lineage_query_slots=[("globalnews", "world:core")],
    )

    assert not report["complete"]
    assert report["missing_query_slots"][0]["reason"] == "invalid_lineage"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"received_utc": 99.0}, "timestamps"),
        ({"completed_utc": 100.5}, "timestamps"),
        ({"item_count": 0, "inserted_count": 0}, "require items"),
        ({"inserted_count": 2}, "item counts"),
        ({"error": "unexpected"}, "no error"),
        ({"cost_units": -1.0}, "cost units"),
    ],
)
def test_fetch_completion_rejects_incoherent_success_receipt(store, patch, message):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    values = {
        "status": "success", "received_utc": 101.0, "completed_utc": 102.0,
        "item_count": 1, "inserted_count": 1, "error": None,
        "cost_units": 0.0, "formal_eligible_item_count": 1,
        "formal_eligible_evidence_ids": [_eid(1)],
    }
    values.update(patch)
    with pytest.raises(ValueError, match=message):
        store.finish_fetch(run, **values)


@pytest.mark.unit
def test_coverage_fails_closed_on_corrupt_terminal_receipt(store):
    run = store.start_fetch("globalnews", "world:core", 100.0)
    store.finish_fetch(
        run, status="success", received_utc=101.0, completed_utc=102.0,
        item_count=1, inserted_count=1, formal_eligible_item_count=1,
        formal_eligible_evidence_ids=[_eid(1)],
    )
    store.conn.execute(
        "UPDATE fetch_runs SET received_utc=99,error='corrupt' WHERE fetch_run_id=?",
        (run,),
    )
    store.conn.commit()

    report = store.coverage_report(
        _server_cutoff(store, run), [],
        expected_query_slots=[("globalnews", "world:core")],
        require_eligible_query_slots=[("globalnews", "world:core")],
    )
    assert not report["complete"]
    assert report["missing_query_slots"][0]["reason"] == "invalid_receipt"


@pytest.mark.unit
def test_budget_reservation_and_fetch_receipt_are_one_atomic_transaction(store):
    limits = {"x-budget:search:day:total": 1.0, "x-budget:search:day:request:a": 1.0}

    receipt = store.start_budgeted_fetch(
        "x", "topic", 100.0, budget_limits=limits,
        metadata={"budget_category": "search"},
    )
    denied = store.start_budgeted_fetch(
        "x", "topic", 101.0, budget_limits=limits,
        metadata={"budget_category": "search"},
    )

    assert receipt is not None
    assert denied is None

    # A crash after the reservation still leaves the conservative paid-request
    # unit on the running receipt and in cost reporting.
    running = store.fetch_runs(provider="x")[0]
    assert running["status"] == "running"
    assert running["cost_units"] == 1.0
    assert store.daily_cost_units("x", 0.0, 1_000.0) == 1.0
    assert store.get_meta("x-budget:search:day:total") == 1.0
    runs = store.fetch_runs(provider="x")
    assert len(runs) == 1
    reservation = json.loads(runs[0]["metadata_json"])["budget_reservation"]
    assert reservation["limits"] == limits
    assert set(reservation["reserved"]) == set(limits)


@pytest.mark.unit
def test_fetch_receipt_reserves_canonical_parent_cycle_extension_point(store):
    spec = collection_cycle_spec(
        cycle_kind="x-daily",
        period_key="2026-08-05",
        protocol_id="protocol_test",
        collector_semantics_id="collector_test",
        expected_static_slots=[("x", "topic")],
        max_dynamic_slots=0,
    )
    cycle_id = store.start_collection_cycle(spec, started_utc=99.0)
    run = store.start_fetch(
        "x", "topic", 100.0, collection_cycle_id=cycle_id
    )
    assert store.fetch_runs(provider="x")[0]["collection_cycle_id"] == cycle_id
    with pytest.raises(ValueError, match="canonical cycle ID"):
        store.start_fetch("x", "topic", 101.0, collection_cycle_id="unsafe")
    assert len(store.fetch_runs(provider="x")) == 1
    store.finish_fetch(
        run, status="failed", received_utc=101.0, completed_utc=102.0,
        item_count=0, inserted_count=0, error="test_failure",
    )
    cycle = store.finish_collection_cycle(cycle_id, completed_utc=103.0)
    assert cycle["status"] == "incomplete"
    assert cycle["manifest"]["slot_receipts"][0]["status"] == "failed"


@pytest.mark.unit
def test_query_slot_completion_after_cutoff_cannot_backfill_past_coverage(
    store, monkeypatch
):
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    run = store.start_fetch("globalnews", "world:core", 100.0)
    clock["now"] = 120.0
    store.finish_fetch(
        run, status="success", received_utc=111.0, completed_utc=120.0,
        item_count=1, inserted_count=1, formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[],
    )

    report = store.coverage_report(
        110.0,
        [],
        expected_query_slots=[("globalnews", "world:core")],
        min_started_utc=95.0,
    )

    assert not report["complete"]
    assert report["missing_query_slots"][0]["reason"] == "incomplete"


@pytest.mark.unit
def test_store_empty_is_noop(store):
    assert store.store([]) == 0


@pytest.mark.unit
def test_stats_groups_by_ticker_and_source(store):
    store.store([
        _row("news", "a", "NVDA", _epoch("2026-06-18 09:00")),
        _row("news", "b", "NVDA", _epoch("2026-06-20 09:00")),
        _row("reddit", "c", "MU", _epoch("2026-06-19 09:00")),
    ])
    stats = {(t, s): (n, lo, hi) for t, s, n, lo, hi in store.stats()}
    assert stats[("NVDA", "news")][0] == 2
    assert stats[("NVDA", "news")][1] == _epoch("2026-06-18 09:00")  # min
    assert stats[("NVDA", "news")][2] == _epoch("2026-06-20 09:00")  # max
    assert stats[("MU", "reddit")][0] == 1


@pytest.mark.unit
def test_window_is_lookahead_safe(store):
    # end=2026-06-28 cuts off at midnight UTC, so a post at 20:58 that day is
    # OUTSIDE the window (a decision made on the 28th can't see the 28th's later
    # intraday chatter); a post within the prior 7 days is inside.
    store.store([
        _row("reddit", "in", "NVDA", _epoch("2026-06-24 09:00")),
        _row("reddit", "edge_before", "NVDA", _epoch("2026-06-28 00:00")),  # == midnight, included
        _row("stocktwits", "same_day_intraday", "NVDA", _epoch("2026-06-28 20:58")),
        _row("reddit", "too_old", "NVDA", _epoch("2026-06-10 09:00")),
    ])
    ids = {r["external_id"] for r in store.window("nvda", "2026-06-28", days=7)}
    assert ids == {"in", "edge_before"}


@pytest.mark.unit
def test_window_bounds_midnight_cutoff():
    lo, hi = _window_bounds("2026-06-28", 7)
    assert hi == _epoch("2026-06-28 00:00")
    assert lo == _epoch("2026-06-21 00:00")


@pytest.mark.unit
def test_history_asof_requires_both_publish_and_fetch_before_cutoff(store):
    store.store([
        _row("news", "known", "NVDA", _epoch("2026-06-28 12:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
        _row("news", "late_discovery", "NVDA", _epoch("2026-06-27 12:00"),
             fetched_utc=_epoch("2026-06-29 01:00")),
        _row("news", "future_post", "NVDA", _epoch("2026-06-29 01:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
        _row("stocktwits", "wrong_source", "NVDA", _epoch("2026-06-28 14:00"),
             fetched_utc=_epoch("2026-06-28 14:01")),
    ])

    rows = store.history_asof(
        "2026-06-21", "2026-06-28", tickers=["nvda"], sources=["news"]
    )

    assert [row["external_id"] for row in rows] == ["known"]


def _assert_exact_cutoff_associations_are_excluded(store):
    before = _epoch("2026-06-28 23:59")
    cutoff = _epoch("2026-06-29 00:00")
    base = _row(
        "trendnews", "event", "@WORLD", _epoch("2026-06-28 12:00"),
        fetched_utc=before,
        metadata={"revision": "before-cutoff"},
    )
    store.store([base])
    store.store([{
        **base,
        "ticker": "@LATE",
        "labels": ["@LATE"],
        "fetched_utc": cutoff,
        "metadata": {"revision": "at-cutoff"},
    }])

    rows = store.history_asof(
        "2026-06-21", "2026-06-28", tickers=["@WORLD"]
    )
    assert len(rows) == 1
    assert rows[0]["labels"] == ["@WORLD"]
    assert rows[0]["metadata"] == {"revision": "before-cutoff"}
    assert store.history_asof(
        "2026-06-21", "2026-06-28", tickers=["@LATE"]
    ) == []

    # Legacy ``window`` is inclusive at midnight; only strict PIT history reads
    # change semantics.
    window = store.window("@LATE", "2026-06-29", days=7)
    assert window[0]["metadata"] == {"revision": "at-cutoff"}


@pytest.mark.unit
def test_history_asof_excludes_exact_cutoff_labels_and_metadata(store):
    _assert_exact_cutoff_associations_are_excluded(store)


@pytest.mark.unit
def test_history_asof_supports_pseudo_ticker_prefixes(store):
    store.store([
        _row("trendnews", "trend", "@TREND_WORLD", _epoch("2026-06-28 12:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
        _row("news", "ticker", "NVDA", _epoch("2026-06-28 12:00"),
             fetched_utc=_epoch("2026-06-28 13:00")),
    ])
    rows = store.history_asof(
        "2026-06-21", "2026-06-28", ticker_prefixes=["@trend"], limit=10
    )
    assert [row["external_id"] for row in rows] == ["trend"]


@pytest.mark.unit
def test_history_bounds_include_full_decision_session():
    lo, hi = _history_bounds("2026-06-21", "2026-06-28")
    assert lo == _epoch("2026-06-21 00:00")
    assert hi == _epoch("2026-06-29 00:00")


def _odds(market_id, captured, prob, theme="rates", volume=1000.0):
    return {"theme": theme, "topic": "Fed rate cut", "market_id": market_id,
            "captured_utc": captured, "question": f"q{market_id}",
            "probability": prob, "volume": volume, "resolution_utc": None}


@pytest.mark.unit
def test_store_odds_is_a_time_series_keyed_by_capture(store):
    # Same market re-captured at different times → distinct snapshots.
    assert store.store_odds([_odds("m1", _epoch("2026-06-20 10:00"), 0.40)]) == 1
    assert store.store_odds([_odds("m1", _epoch("2026-06-21 10:00"), 0.55)]) == 1
    # Re-inserting an existing (market_id, captured_utc) is a no-op.
    assert store.store_odds([_odds("m1", _epoch("2026-06-21 10:00"), 0.55)]) == 0


@pytest.mark.unit
def test_odds_asof_returns_latest_snapshot_before_cutoff(store):
    store.store_odds([
        _odds("m1", _epoch("2026-06-20 10:00"), 0.40),
        _odds("m1", _epoch("2026-06-25 10:00"), 0.60),   # latest before 06-28
        _odds("m1", _epoch("2026-06-28 09:00"), 0.90),   # same-day → excluded (midnight cutoff)
        _odds("m2", _epoch("2026-06-24 10:00"), 0.30, theme="trade"),
    ])
    asof = {r["market_id"]: r["probability"] for r in store.odds_asof("2026-06-28")}
    assert asof == {"m1": 0.60, "m2": 0.30}        # newest pre-cutoff per market
    # Theme filter narrows the set.
    only_rates = store.odds_asof("2026-06-28", themes=["rates"])
    assert {r["market_id"] for r in only_rates} == {"m1"}


@pytest.mark.unit
def test_normalize_pg_url_forces_psycopg_driver():
    # Fly Managed Postgres / Heroku give postgres://; plain postgresql:// would
    # default to psycopg2. Both must become postgresql+psycopg://.
    assert _normalize_pg_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert _normalize_pg_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    # Already-qualified and non-Postgres URLs pass through untouched.
    assert _normalize_pg_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert _normalize_pg_url("sqlite:///x.db") == "sqlite:///x.db"


@pytest.mark.unit
def test_open_store_routing(tmp_path):
    # Bare path and sqlite:/// URLs both resolve to the stdlib SQLite backend.
    s1 = open_store(str(tmp_path / "bare.db"))
    s2 = open_store(f"sqlite:///{tmp_path / 'scheme.db'}")
    try:
        assert isinstance(s1, SqliteMediaStore)
        assert isinstance(s2, SqliteMediaStore)
    finally:
        s1.close()
        s2.close()


@pytest.mark.unit
def test_sqlalchemy_store_explicit_no_migrate_overrides_process_environment(
    tmp_path, monkeypatch
):
    from sqlalchemy import inspect

    monkeypatch.setenv("MEDIA_AUTO_MIGRATE", "true")
    database = tmp_path / "read-only-preflight.db"
    store = open_store(
        f"sqlite+pysqlite:///{database}",
        auto_migrate=False,
    )
    try:
        assert inspect(store.engine).get_table_names() == []
    finally:
        store.close()


@pytest.mark.unit
def test_missing_sqlalchemy_error_does_not_expose_database_url(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def without_sqlalchemy(name, *args, **kwargs):
        if name == "sqlalchemy":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_sqlalchemy)
    secret_url = "postgresql://collector:super-secret@db.example/media"
    with pytest.raises(RuntimeError) as error:
        SqlAlchemyMediaStore(secret_url)
    assert secret_url not in str(error.value)
    assert "super-secret" not in str(error.value)


@pytest.mark.unit
def test_postgres_pooled_engine_uses_transaction_local_settings(monkeypatch):
    import sqlalchemy

    observed = {}

    class FakeEngine:
        class dialect:
            name = "postgresql"

        @staticmethod
        def dispose():
            observed["disposed"] = True

    engine = FakeEngine()

    def fake_create_engine(url, **kwargs):
        observed["url"] = url
        observed["engine_options"] = kwargs
        return engine

    def fake_listen(target, event_name, callback):
        observed.setdefault("listeners", []).append(
            (target, event_name, callback)
        )

    monkeypatch.setattr(sqlalchemy, "create_engine", fake_create_engine)
    monkeypatch.setattr(sqlalchemy.event, "listen", fake_listen)
    store = SqlAlchemyMediaStore(
        "postgresql+psycopg://collector@example.invalid/evidence",
        auto_migrate=False,
    )
    try:
        connect_args = observed["engine_options"]["connect_args"]
        assert connect_args == {
            "prepare_threshold": None,
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "tcp_user_timeout": 30000,
        }
        target, event_name, callback = next(
            listener
            for listener in observed["listeners"]
            if listener[0] is engine and listener[1] == "begin"
        )
        assert target is engine
        assert event_name == "begin"
        assert callback is media_store_module._set_postgres_transaction_settings

        class Connection:
            def __init__(self):
                self.statements = []

            def exec_driver_sql(self, statement):
                self.statements.append(statement)

        first = Connection()
        second = Connection()
        callback(first)
        callback(second)
        expected = list(media_store_module._POSTGRES_TRANSACTION_SETTINGS)
        assert first.statements == expected
        assert second.statements == expected
        assert all(statement.startswith("SET LOCAL ") for statement in expected)
    finally:
        store.close()


@pytest.mark.unit
def test_postgres_direct_engine_retains_read_only_startup_fail_safe():
    pooled = media_store_module._postgres_connect_args()
    direct = media_store_module._postgres_connect_args(read_only=True)

    assert pooled["prepare_threshold"] is None
    assert direct["prepare_threshold"] is None
    assert "options" not in pooled
    assert "default_transaction_read_only=on" in direct["options"]
    assert "search_path=pg_catalog,public" in direct["options"]


@pytest.mark.unit
def test_sqlalchemy_store_reports_insert_count_with_conflict_ignore(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'sa.db'}")
    rows = [
        _row("news", "1", "NVDA", _epoch("2026-07-23 10:00")),
        _row("news", "2", "NVDA", _epoch("2026-07-23 11:00")),
    ]
    try:
        assert store.store(rows) == 2
        assert store.store(rows) == 0
    finally:
        store.close()


@pytest.mark.unit
def test_sqlalchemy_meta_set_inserts_and_overwrites(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'meta-sa.db'}")
    try:
        assert store.engine.pool._recycle == 540
        assert store.get_meta("collector:state") is None
        store.set_meta("collector:state", 1.0)
        assert store.get_meta("collector:state") == 1.0
        store.set_meta("collector:state", 2.0)
        assert store.get_meta("collector:state") == 2.0
    finally:
        store.close()


@pytest.mark.unit
def test_fly_mpg_direct_url_is_derived_without_changing_credentials_or_query():
    store = object.__new__(SqlAlchemyMediaStore)
    store._database_url = (
        "postgresql+psycopg://collector:p%40ss@"
        "pgbouncer.cluster-123.flympg.net:5432/evidence?sslmode=require"
    )

    resolved = store._collector_direct_database_url()

    assert resolved.host == "direct.cluster-123.flympg.net"
    assert resolved.username == "collector"
    assert resolved.password == "p@ss"
    assert resolved.port == 5432
    assert resolved.database == "evidence"
    assert dict(resolved.query) == {"sslmode": "require"}


@pytest.mark.unit
def test_collector_direct_url_fails_closed_for_unknown_or_pooled_override():
    store = object.__new__(SqlAlchemyMediaStore)
    store._database_url = "postgresql+psycopg://collector@db.example/evidence"

    with pytest.raises(ValueError, match="MEDIA_DB_DIRECT_URL"):
        store._collector_direct_database_url()
    with pytest.raises(ValueError, match="must not use a Fly MPG pooler"):
        store._collector_direct_database_url(
            "postgresql://collector@pgbouncer.cluster-123.flympg.net/evidence"
        )

    explicit = store._collector_direct_database_url(
        "postgresql://collector@direct-db.example/evidence"
    )
    assert explicit.host == "direct-db.example"


@pytest.mark.unit
def test_collector_runtime_preflight_rejects_non_postgres(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'preflight-sa.db'}")
    try:
        with pytest.raises(ValueError, match="requires PostgreSQL"):
            store.collector_runtime_preflight()
    finally:
        store.close()


@pytest.mark.unit
def test_collector_check_hashes_allow_only_reviewed_type_renderings():
    hashes = media_store_module._COLLECTOR_CHECK_CONSTRAINT_HASHES
    dual_renderings = {
        ("collection_cycles", "collection_cycles_server_observation_shape"),
        ("collection_cycles", "collection_cycles_terminal_shape"),
        ("collection_cycle_slots", "collection_cycle_slots_fields_valid"),
        ("fetch_runs", "fetch_runs_server_observation_shape"),
    }

    assert set(hashes) == {
        key for key, value in media_store_module._COLLECTOR_CONSTRAINT_CONTRACTS.items()
        if value[0] == "c"
    }
    assert all(
        len(approved) == (2 if key in dual_renderings else 1)
        for key, approved in hashes.items()
    )
    assert all(
        len(digest) == 64 and set(digest) <= set("0123456789abcdef")
        for approved in hashes.values()
        for digest in approved
    )


@pytest.mark.unit
def test_collector_column_contract_covers_all_columns_and_fails_closed(tmp_path):
    store = SqlAlchemyMediaStore(
        f"sqlite+pysqlite:///{tmp_path / 'column-contract.db'}"
    )
    tables = (
        store.table,
        store.labels,
        store.observations,
        store.odds,
        store.state,
        store.cycles,
        store.cycle_slots,
        store.fetches,
        store.fetch_items_table,
    )
    try:
        columns = [column for table in tables for column in table.columns]
        families = Counter(
            media_store_module._collector_postgres_type_family(column.type)
            for column in columns
        )
        assert len(columns) == 75
        assert families == {
            "unbounded_text": 48,
            "float8": 23,
            "int4": 3,
            "bool": 1,
        }
        assert all(column.server_default is None for column in columns)

        column = store.table.c.author
        valid = {
            "type_oid": 25,
            "type_modifier": -1,
            "default_collation": True,
            "not_null": False,
            "has_default": False,
            "identity_kind": "",
            "generated_kind": "",
        }
        assert media_store_module._collector_postgres_column_contract_valid(
            column, valid
        )
        assert media_store_module._collector_postgres_column_contract_valid(
            column, {**valid, "type_oid": 1043}
        )

        invalid_mutations = (
            {"type_oid": 999_999},       # domain or custom type
            {"type_modifier": 68},       # bounded VARCHAR(64)
            {"default_collation": False},
            {"not_null": True},
            {"has_default": True},
            {"identity_kind": "d"},
            {"generated_kind": "s"},
        )
        for mutation in invalid_mutations:
            assert not media_store_module._collector_postgres_column_contract_valid(
                column, {**valid, **mutation}
            )
    finally:
        store.close()


@pytest.mark.unit
def test_collector_runtime_preflight_failure_projection_is_sanitized(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'failed-preflight.db'}")
    real_engine = store.engine
    sensitive = "postgresql://collector:secret@example.invalid/database"

    class BrokenEngine:
        @staticmethod
        def connect():
            raise RuntimeError(sensitive)

    store.dialect = "postgresql"
    store.engine = BrokenEngine()
    try:
        report = store.collector_runtime_preflight()
    finally:
        real_engine.dispose()

    assert report["postgresql"] is True
    assert report["connected"] is False
    assert report["ready"] is False
    assert report["failure_stage"] == "primary_connection"
    assert report["failure_type"] == "RuntimeError"
    assert report["failure_stage"] in (
        media_store_module._COLLECTOR_PREFLIGHT_FAILURE_STAGES
    )
    assert report["failure_type"] in (
        media_store_module._COLLECTOR_PREFLIGHT_FAILURE_TYPES
    )
    assert sensitive not in repr(report)


@pytest.mark.unit
def test_collector_runtime_preflight_failure_type_has_fixed_vocabulary():
    class CredentialNamedFailure(Exception):
        pass

    assert media_store_module._collector_preflight_failure_type(
        CredentialNamedFailure("private connection details")
    ) == "Exception"


@pytest.mark.unit
def test_sqlalchemy_server_observed_utc_uses_database_clock(tmp_path, monkeypatch):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'server-clock.db'}")
    try:
        monkeypatch.setattr(store, "_server_observed_utc", lambda _conn: 5678.25)
        assert store.server_observed_utc() == 5678.25
    finally:
        store.close()


@pytest.mark.unit
def test_sqlalchemy_atomic_fetch_completion_matches_sqlite(tmp_path, monkeypatch):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'atomic-sa.db'}")
    try:
        server_clock = iter([1_000.0, 1_001.0])
        monkeypatch.setattr(
            store, "_server_observed_utc", lambda _conn: next(server_clock)
        )
        run = store.start_fetch(
            "globalnews", "world:core", 100.0, metadata={"kind": "media"}
        )
        row = _row(
            "globalnews", "story", "@WORLD", 99.0, fetched_utc=101.0,
            author="Reuters", title="Report", body="body",
        )
        row["metadata"] = {"publisher_domain": "reuters.com"}
        eligible = [evidence_id(row)]
        assert store.complete_fetch(
            run, rows=[row], status="success", received_utc=101.0,
            completed_utc=102.0, formal_eligible_item_count=1,
            formal_eligible_evidence_ids=eligible,
        ) == 1
        assert store.fetch_items(run)[0]["raw_content_id"] == raw_content_id(row)
        assert store.fetch_runs(provider="globalnews")[0][
            "formal_eligible_lineage"
        ] == [{"evidence_id": eligible[0], "raw_content_id": raw_content_id(row)}]
        history = store.history_asof(
            "1970-01-01", "1970-01-01", sources=["globalnews"]
        )
        assert history[0]["latest_observed_utc"] == 1_001.0
    finally:
        store.close()


@pytest.mark.unit
def test_sqlalchemy_history_uses_authenticated_receipt_cutoff(tmp_path, monkeypatch):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'receipt-cutoff.db'}")
    try:
        server_clock = {"now": 0.0}
        monkeypatch.setattr(
            store, "_server_observed_utc", lambda _conn: server_clock["now"]
        )
        _assert_authenticated_receipt_cutoff(
            store, lambda value: server_clock.__setitem__("now", value)
        )
    finally:
        store.close()


@pytest.mark.unit
def test_sqlalchemy_budget_and_receipt_transaction_matches_sqlite(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'budgeted.db'}")
    limits = {"x-budget:trend:day:total": 1.0, "x-budget:trend:day:request:a": 1.0}
    try:
        receipt = store.start_budgeted_fetch(
            "xtrend", "woeid:1", 100.0, budget_limits=limits,
            metadata={"budget_category": "trend"},
        )
        denied = store.start_budgeted_fetch(
            "xtrend", "woeid:1", 101.0, budget_limits=limits,
            metadata={"budget_category": "trend"},
        )
        assert receipt is not None
        assert denied is None
        assert len(store.fetch_runs(provider="xtrend")) == 1
        assert store.get_meta("x-budget:trend:day:total") == 1.0
    finally:
        store.close()


@pytest.mark.unit
def test_sqlalchemy_coverage_matches_exact_query_slots(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'coverage.db'}")
    try:
        run = store.start_fetch("globalnews", "world:core", 100.0)
        store.finish_fetch(
            run, status="success", received_utc=101.0, completed_utc=102.0,
            item_count=1, inserted_count=1, formal_eligible_item_count=0,
            formal_eligible_evidence_ids=[],
        )
        receipt = _fetch_receipt(store, run)
        report = store.coverage_report(
            float(receipt["server_terminal_utc"]) + 1.0,
            [],
            expected_query_slots=[
                ("globalnews", "world:core"),
                ("globalnews", "technology:core"),
            ],
            min_started_utc=float(receipt["server_started_utc"]) - 1.0,
        )
        assert not report["complete"]
        assert [slot["reason"] for slot in report["query_slots"]] == [None, "not_run"]
    finally:
        store.close()


@pytest.mark.unit
def test_sqlalchemy_history_excludes_exact_cutoff_labels_and_metadata(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'history-cutoff.db'}")
    try:
        _assert_exact_cutoff_associations_are_excluded(store)
    finally:
        store.close()
