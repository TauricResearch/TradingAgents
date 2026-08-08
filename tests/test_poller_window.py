"""Independent fetch receipts retain late discoveries without shared-cursor gaps."""
import json
import logging
from datetime import datetime, timezone

import pytest

from tradingagents import poller
from tradingagents.dataflows.media_sources import (
    ProviderResponseError,
    ProviderTransientError,
    _google_news_content_vintage,
    _row,
)
from tradingagents.dataflows.media_store import SqliteMediaStore
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES,
    global_news_query_slot_label,
)


@pytest.mark.unit
def test_poll_once_stores_older_items_first_discovered_now(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")

    def fake_source(ticker, now):
        return [_row("x", "a", ticker, now, created_utc=9995.0),   # in window
                _row("x", "b", ticker, now, created_utc=9000.0)]   # too old

    monkeypatch.setattr(poller, "FETCHERS", {"x": fake_source})
    poller.poll_once(store, ["NVDA"], ["x"])

    stored = store.window("NVDA", "2100-01-01", days=400000)
    assert {r["external_id"] for r in stored} == {"a", "b"}
    runs = store.fetch_runs(provider="x")
    assert runs[0]["status"] == "success"
    assert runs[0]["item_count"] == 2
    store.close()


@pytest.mark.unit
def test_meta_roundtrip_persists_last_poll(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    assert store.get_meta("last_poll_utc") is None
    store.set_meta("last_poll_utc", 12345.0)
    assert store.get_meta("last_poll_utc") == 12345.0
    store.set_meta("last_poll_utc", 67890.0)       # upsert
    assert store.get_meta("last_poll_utc") == 67890.0
    store.close()


@pytest.mark.unit
def test_x_only_cycle_does_not_advance_shared_poll_cursor(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")
    store.set_meta("last_poll_utc", 100.0)
    monkeypatch.setattr(poller, "poll_x_topics_once", lambda *args, **kwargs: None)

    poller.run_cycle(
        store,
        tickers=["IGNORED"],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert store.get_meta("last_poll_utc") == 100.0
    store.close()


@pytest.mark.unit
def test_run_cycle_uses_database_clock_for_coverage_bounds(monkeypatch):
    observed = {"meta": []}

    class Store:
        def __init__(self):
            self.clock = iter((100.0, 101.0))

        def server_observed_utc(self):
            return next(self.clock)

        def set_meta(self, key, value):
            observed["meta"].append((key, value))

    def capture_coverage(_store, **kwargs):
        observed.update(kwargs)
        return {"complete": True}

    monkeypatch.setattr(poller.time, "time", lambda: 999_999.0)
    monkeypatch.setattr(poller, "_check_cycle_query_coverage", capture_coverage)

    result = poller.run_cycle(
        Store(), tickers=[], sources=[], macro_themes={}, x_enabled=False
    )

    assert result == {"complete": True}
    assert observed["cycle_started_utc"] == 100.0
    assert observed["cycle_completed_utc"] == 101.0
    assert observed["meta"] == [("poller:last_cycle_utc", 101.0)]


@pytest.mark.unit
def test_failed_and_empty_fetches_do_not_advance_independent_watermark(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")

    with pytest.raises(RuntimeError):
        poller._run_fetch(
            store, provider="x", query_key="global topic",
            fetch_fn=lambda _: (_ for _ in ()).throw(RuntimeError("auth failed")),
            cost_units=1.0,
            budget_limits={"test:x:total": 1.0, "test:x:request": 1.0},
            budget_metadata={"budget_category": "search"},
        )
    assert store.get_meta(poller._watermark_key("x", "global topic")) is None
    failed = store.fetch_runs(provider="x")[0]
    assert failed["status"] == "failed"
    assert failed["error"] == "RuntimeError"
    assert "auth failed" not in failed["error"]

    count, inserted, status = poller._run_fetch(
        store, provider="globalnews", query_key="world", fetch_fn=lambda _: [],
    )
    assert (count, inserted, status) == (0, 0, "empty")
    assert store.get_meta(poller._watermark_key("globalnews", "world")) is None
    store.close()


@pytest.mark.unit
def test_formal_news_receipt_binds_exact_eligible_evidence_ids(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    theme, queries = next(iter(GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES.items()))
    query = queries[0]
    label = global_news_query_slot_label(theme, query)

    count, _, status = poller._run_fetch(
        store,
        provider="globalnews",
        query_key=f"{theme}:{query}",
        labels=[f"@{theme}", label],
        fetch_fn=lambda captured: [_row(
            "globalnews", "story-1", f"@{theme}", captured,
            author="Reuters", created_utc=captured - 1,
            title="Independent global policy report",
            metadata={
                "article_url": "https://news.google.com/articles/story-1",
                "publisher_domain": "reuters.com",
            },
        )],
    )

    assert (count, status) == (1, "success")
    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["formal_eligible_item_count"] == 1
    assert len(receipt["formal_eligible_evidence_ids"]) == 1
    assert receipt["formal_eligible_evidence_ids"][0].startswith("evidence_")
    metadata = json.loads(receipt["metadata_json"])
    assert metadata["protocol_id"].startswith("protocol_")
    assert metadata["collector_semantics_id"].startswith("collector_")
    store.close()


@pytest.mark.unit
def test_google_news_cluster_revision_is_appended_without_poisoning_receipt(tmp_path):
    store = SqliteMediaStore(tmp_path / "google-revision.db")
    theme, queries = next(iter(GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES.items()))
    query = queries[0]
    label = global_news_query_slot_label(theme, query)

    def row(captured, title):
        metadata_base = {
            "article_url": "https://news.google.com/articles/provider-cluster",
            "publisher_domain": "reuters.com",
        }
        external_id, metadata = _google_news_content_vintage(
            "provider-cluster",
            published_utc=captured - 1,
            publisher="Reuters",
            title=title,
            body="Independent report",
            provenance=metadata_base,
        )
        return _row(
            "globalnews",
            external_id,
            f"@{theme}",
            captured,
            author="Reuters",
            created_utc=captured - 1,
            title=title,
            body="Independent report",
            metadata=metadata,
        )

    for title in ("Original headline", "Corrected headline"):
        count, _, status = poller._run_fetch(
            store,
            provider="globalnews",
            query_key=f"{theme}:{query}",
            labels=[f"@{theme}", label],
            fetch_fn=lambda captured, value=title: [row(captured, value)],
        )
        assert (count, status) == (1, "success")

    assert store.conn.execute("SELECT COUNT(*) FROM media_posts").fetchone()[0] == 2
    receipts = store.fetch_runs(provider="globalnews")
    assert [receipt["status"] for receipt in receipts] == ["success", "success"]
    assert len({
        receipt["formal_eligible_evidence_ids"][0] for receipt in receipts
    }) == 2
    store.close()


@pytest.mark.unit
def test_one_response_cannot_contain_conflicting_google_cluster_revisions(tmp_path):
    store = SqliteMediaStore(tmp_path / "ambiguous-google-revision.db")
    theme, queries = next(iter(GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES.items()))
    query = queries[0]

    def revision(captured, title):
        external_id, metadata = _google_news_content_vintage(
            "provider-cluster",
            published_utc=captured - 1,
            publisher="Reuters",
            title=title,
            body="Independent report",
            provenance={
                "article_url": "https://news.google.com/articles/provider-cluster",
                "publisher_domain": "reuters.com",
            },
        )
        return _row(
            "globalnews", external_id, f"@{theme}", captured,
            author="Reuters", created_utc=captured - 1, title=title,
            body="Independent report", metadata=metadata,
        )

    with pytest.raises(ValueError, match="ambiguous provider revisions"):
        poller._run_fetch(
            store,
            provider="globalnews",
            query_key=f"{theme}:{query}",
            fetch_fn=lambda captured: [
                revision(captured, "Original headline"),
                revision(captured, "Corrected headline"),
            ],
        )

    assert store.conn.execute("SELECT COUNT(*) FROM media_posts").fetchone()[0] == 0
    receipts = store.fetch_runs(provider="globalnews")
    assert len(receipts) == 1
    assert receipts[0]["status"] == "failed"
    assert receipts[0]["error"] == "ValueError"
    store.close()


@pytest.mark.unit
def test_globalnews_exception_retries_have_independent_receipts_then_succeed(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "globalnews-retry.db")
    attempts = []
    sleeps = []

    def fetch_news(query, captured, theme, *, limit):
        attempts.append((query, theme, limit))
        if len(attempts) < 3:
            raise ProviderTransientError("provider credential=must-not-persist")
        return [_row(
            "globalnews",
            "event-1",
            f"@{theme}",
            captured,
            author="Reuters",
            created_utc=captured - 1,
            title="Independent global policy report",
            metadata={"publisher_domain": "reuters.com"},
        )]

    monkeypatch.setattr(poller, "fetch_global_news", fetch_news)
    count, inserted, status = poller._run_globalnews_query(
        store, "world", "global policy", sleep_fn=sleeps.append
    )

    assert (count, inserted, status) == (1, 1, "success")
    assert len(attempts) == 3
    assert sleeps == [1.0, 4.0]
    receipts = list(reversed(store.fetch_runs(provider="globalnews")))
    assert [receipt["status"] for receipt in receipts] == ["failed", "failed", "success"]
    assert [json.loads(receipt["metadata_json"])["attempt_ordinal"]
            for receipt in receipts] == [1, 2, 3]
    assert all("must-not-persist" not in (receipt["error"] or "") for receipt in receipts)

    coverage = store.coverage_report(
        max(receipt["server_terminal_utc"] for receipt in receipts) + 1,
        [],
        expected_query_slots=[("globalnews", "world:global policy")],
        require_lineage_query_slots=[("globalnews", "world:global policy")],
        min_started_utc=min(receipt["server_started_utc"] for receipt in receipts),
    )
    assert coverage["complete"] is True
    assert coverage["query_slots"][0]["run"]["status"] == "success"
    store.close()


@pytest.mark.unit
def test_globalnews_retry_is_bounded_and_reraises_final_exception(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "globalnews-bounded.db")
    calls = []
    sleeps = []

    def unavailable(*_args, **_kwargs):
        calls.append(1)
        raise ProviderTransientError("secret response")

    monkeypatch.setattr(poller, "fetch_global_news", unavailable)
    with pytest.raises(ProviderTransientError, match="secret response"):
        poller._run_globalnews_query(
            store, "world", "global policy", sleep_fn=sleeps.append
        )

    assert len(calls) == 3
    assert sleeps == [1.0, 4.0]
    receipts = store.fetch_runs(provider="globalnews")
    assert len(receipts) == 3
    assert {receipt["status"] for receipt in receipts} == {"failed"}
    assert {receipt["error"] for receipt in receipts} == {"ProviderTransientError"}
    store.close()


@pytest.mark.unit
def test_globalnews_response_or_persistence_failures_are_never_refetched(
    tmp_path, monkeypatch,
):
    for failure_kind in ("response", "persistence"):
        store = SqliteMediaStore(tmp_path / f"globalnews-no-retry-{failure_kind}.db")
        calls = []

        def fetch_news(
            *_args, observed_calls=calls, selected_failure=failure_kind, **_kwargs
        ):
            observed_calls.append(1)
            if selected_failure == "response":
                raise ProviderResponseError("invalid provider envelope")
            return []

        if failure_kind == "persistence":
            monkeypatch.setattr(
                store,
                "complete_fetch",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    ValueError("schema invariant failed")
                ),
            )
        monkeypatch.setattr(poller, "fetch_global_news", fetch_news)

        with pytest.raises((ProviderResponseError, ValueError)):
            poller._run_globalnews_query(
                store, "world", "global policy", sleep_fn=lambda _seconds: None
            )

        assert calls == [1]
        receipts = store.fetch_runs(provider="globalnews")
        assert len(receipts) == 1
        assert receipts[0]["status"] == "failed"
        store.close()


@pytest.mark.unit
def test_post_commit_watermark_failure_does_not_duplicate_success_receipt(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "globalnews-watermark.db")
    calls = []
    original_set_meta = store.set_meta

    def fail_watermark(key, value):
        if key.startswith("watermark:globalnews:"):
            raise RuntimeError("watermark storage unavailable")
        original_set_meta(key, value)

    def fetch_news(_query, captured, theme, *, limit):
        calls.append(1)
        assert limit == 25
        return [_row(
            "globalnews", "watermark-story", f"@{theme}", captured,
            author="Reuters", created_utc=captured - 1,
            title="Independent global policy report",
            metadata={"publisher_domain": "reuters.com"},
        )]

    monkeypatch.setattr(store, "set_meta", fail_watermark)
    monkeypatch.setattr(poller, "fetch_global_news", fetch_news)

    assert poller._run_globalnews_query(
        store, "world", "global policy", sleep_fn=lambda _seconds: None
    ) == (1, 1, "success")
    assert calls == [1]
    receipts = store.fetch_runs(provider="globalnews")
    assert len(receipts) == 1
    assert receipts[0]["status"] == "success"
    store.close()


@pytest.mark.unit
def test_globalnews_cycle_circuit_bounds_provider_outage_fanout(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "globalnews-circuit.db")
    calls = []
    alerts = []

    def unavailable(*_args, **_kwargs):
        calls.append(1)
        raise ProviderTransientError("provider unavailable")

    monkeypatch.setattr(poller, "fetch_global_news", unavailable)
    monkeypatch.setattr(poller.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: alerts.append(
            (component, event, kwargs)
        ) or True,
    )
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={
            "world": {"queries": ["one", "two", "three", "four"]}
        },
    )

    assert len(calls) == 6  # two failed slots, three bounded attempts each
    assert len(store.fetch_runs(provider="globalnews")) == 6
    assert coverage["complete"] is False
    assert [slot["reason"] for slot in coverage["missing_query_slots"]] == [
        "failed", "failed", "not_run", "not_run",
    ]
    assert [event for _, event, _ in alerts] == ["query_slot_coverage_incomplete"]
    store.close()


@pytest.mark.unit
def test_globalnews_observed_empty_is_terminal_and_not_retried(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "globalnews-empty.db")
    calls = []
    sleeps = []

    def observed_empty(*_args, **_kwargs):
        calls.append(1)
        return []

    monkeypatch.setattr(poller, "fetch_global_news", observed_empty)
    result = poller._run_globalnews_query(
        store, "world", "global policy", sleep_fn=sleeps.append
    )

    assert result == (0, 0, "empty")
    assert calls == [1]
    assert sleeps == []
    assert [row["status"] for row in store.fetch_runs(provider="globalnews")] == ["empty"]
    store.close()


@pytest.mark.unit
def test_fetch_receipt_fails_on_provider_source_mismatch(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    with pytest.raises(ValueError, match="mismatched source provenance"):
        poller._run_fetch(
            store,
            provider="globalnews",
            query_key="rates:query",
            fetch_fn=lambda captured: [_row(
                "trendnews", "wrong-provider", "@RATES", captured,
                created_utc=captured - 1,
            )],
        )
    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["status"] == "failed"
    assert receipt["formal_eligible_evidence_ids"] is None
    assert store.stats() == []
    store.close()


@pytest.mark.unit
def test_lost_singleton_lease_blocks_provider_before_receipt_or_call(tmp_path):
    store = SqliteMediaStore(tmp_path / "lease-lost.db")
    calls = []

    class LostLease:
        is_held = False

        def assert_held(self):
            raise RuntimeError("credential=must-not-log")

    store._collector_lease_guard = LostLease()
    with pytest.raises(RuntimeError, match="must-not-log"):
        poller._run_fetch(
            store,
            provider="globalnews",
            query_key="world:global event",
            fetch_fn=lambda _captured: calls.append(1) or [],
        )

    assert calls == []
    assert store.fetch_runs(limit=100) == []
    store.close()


@pytest.mark.unit
def test_lease_loss_after_provider_call_discards_rows_and_fails_receipt(tmp_path):
    store = SqliteMediaStore(tmp_path / "lease-lost-after-call.db")

    class LeaseLostAfterCall:
        is_held = True

        def __init__(self):
            self.calls = 0

        def assert_held(self):
            self.calls += 1
            if self.calls == 3:
                self.is_held = False
                raise RuntimeError("lease lost")

    lease = LeaseLostAfterCall()
    store._collector_lease_guard = lease
    with pytest.raises(RuntimeError, match="lease lost"):
        poller._run_fetch(
            store,
            provider="globalnews",
            query_key="world:global event",
            fetch_fn=lambda captured: [_row(
                "globalnews",
                "discarded",
                "@WORLD",
                captured,
                created_utc=captured - 1,
                title="Substantive global event",
            )],
        )

    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["status"] == "failed"
    assert receipt["error"] == "RuntimeError"
    assert store.stats() == []
    store.close()


@pytest.mark.unit
def test_fetch_receipt_rejects_conflicting_duplicate_identity_before_storage(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    theme, queries = next(iter(GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES.items()))
    query = queries[0]
    label = global_news_query_slot_label(theme, query)
    with pytest.raises(ValueError, match="conflicting duplicate provenance"):
        poller._run_fetch(
            store,
            provider="globalnews",
            query_key=f"{theme}:{query}",
            labels=[f"@{theme}", label],
            fetch_fn=lambda captured: [
                _row(
                    "globalnews", "same-id", f"@{theme}", captured,
                    author="Local Blog", created_utc=captured - 1,
                    metadata={"publisher_domain": "local.example"},
                ),
                _row(
                    "globalnews", "same-id", f"@{theme}", captured,
                    author="Reuters", created_utc=captured - 1,
                    metadata={"publisher_domain": "reuters.com"},
                ),
            ],
        )
    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["status"] == "failed"
    assert store.stats() == []
    store.close()


@pytest.mark.unit
def test_fetch_receipt_collapses_exact_duplicate_and_merges_topic_labels(tmp_path):
    store = SqliteMediaStore(tmp_path / "duplicate-discovery.db")

    def fetch(captured):
        common = {
            "author": "Reuters",
            "created_utc": captured - 1,
            "title": "Shared discovery headline",
            "body": "Independent report",
            "metadata": {
                "publisher_domain": "reuters.com",
                "provider_external_id": "provider-cluster",
            },
        }
        return [
            _row("trendnews", "same-vintage", "@TREND_WORLD", captured, **common),
            _row(
                "trendnews", "same-vintage", "@TREND_TECHNOLOGY", captured, **common
            ),
        ]

    count, inserted, status = poller._run_fetch(
        store,
        provider="trendnews",
        query_key="ranked-global-discovery",
        fetch_fn=fetch,
    )

    assert (count, inserted, status) == (1, 1, "success")
    receipt = store.fetch_runs(provider="trendnews")[0]
    assert receipt["item_count"] == 1
    assert len(store.fetch_items(receipt["fetch_run_id"])) == 1
    assert store.conn.execute(
        "SELECT label FROM media_labels ORDER BY label"
    ).fetchall() == [("@TREND_TECHNOLOGY",), ("@TREND_WORLD",)]
    store.close()


@pytest.mark.unit
def test_atomic_storage_failure_rolls_back_rows_then_records_failed_receipt(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    store.conn.execute(
        """
        CREATE TRIGGER reject_success_for_test
        BEFORE UPDATE ON fetch_runs
        WHEN NEW.status = 'success'
        BEGIN
            SELECT RAISE(ABORT, 'injected terminal receipt failure');
        END
        """
    )
    store.conn.commit()

    with pytest.raises(Exception, match="injected terminal receipt failure"):
        poller._run_fetch(
            store, provider="x", query_key="topic",
            fetch_fn=lambda captured: [
                _row("x", "must-rollback", "@WORLD", captured, body="reaction")
            ],
        )

    receipt = store.fetch_runs(provider="x")[0]
    assert receipt["status"] == "failed"
    assert receipt["item_count"] == 0
    assert store.fetch_items(receipt["fetch_run_id"]) == []
    assert store.history_asof("2026-01-01", "2027-01-01", sources=["x"]) == []
    store.close()


@pytest.mark.unit
def test_nonempty_odds_fetch_is_not_subject_to_media_source_field(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    count, inserted, status = poller._run_fetch(
        store,
        provider="polymarket",
        query_key="rates:fed",
        odds=True,
        fetch_fn=lambda _: [{
            "theme": "rates", "topic": "fed", "market_id": "market-1",
            "question": "Will rates fall?", "probability": 0.5, "volume": 10.0,
            "resolution_utc": None,
        }],
    )
    assert (count, inserted, status) == (1, 1, "success")
    store.close()


@pytest.mark.unit
def test_globalnews_receipt_eligibility_is_bound_to_its_exact_query_label(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    slots = [
        (theme, query)
        for theme, queries in GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES.items()
        for query in queries
    ][:2]
    (theme, query), (wrong_theme, wrong_query) = slots
    wrong_label = global_news_query_slot_label(wrong_theme, wrong_query)
    _, _, status = poller._run_fetch(
        store,
        provider="globalnews",
        query_key=f"{theme}:{query}",
        labels=[f"@{theme}", wrong_label],
        fetch_fn=lambda captured: [_row(
            "globalnews", "wrong-slot", f"@{theme}", captured,
            author="Reuters", created_utc=captured - 1,
            metadata={"publisher_domain": "reuters.com"},
        )],
    )
    assert status == "success"
    receipt = store.fetch_runs(provider="globalnews")[0]
    assert receipt["formal_eligible_item_count"] == 0
    assert receipt["formal_eligible_evidence_ids"] == []
    store.close()


@pytest.mark.unit
def test_cycle_alerts_for_each_missing_query_slot_without_leaking_payloads(
    tmp_path, monkeypatch, caplog,
):
    store = SqliteMediaStore(tmp_path / "m.db")
    sensitive_query = "technology launches credential=secret-query-token"
    safe_query = "global policy developments"
    secret_url = "https://api.example.invalid/path?bearer=secret-provider-token"
    alerts = []

    def fetch_news(query, captured, theme, *, limit):
        assert limit == 25
        if query == sensitive_query:
            raise ProviderResponseError(f"request failed for {secret_url}")
        return [_row(
            "globalnews", "success", f"@{theme}", captured,
            created_utc=captured, title="Global policy update",
        )]

    def capture_alert(component, event, **kwargs):
        alerts.append((component, event, kwargs))
        return True

    monkeypatch.setattr(poller, "fetch_global_news", fetch_news)
    monkeypatch.setattr(poller.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(poller, "emit_alert", capture_alert)
    with caplog.at_level(logging.INFO):
        poller.run_cycle(
            store,
            tickers=[],
            sources=[],
            macro_themes={"global": {"queries": [safe_query, sensitive_query]}},
        )

    runs = {run["query_key"]: run for run in store.fetch_runs()}
    assert runs[f"global:{safe_query}"]["status"] == "success"
    assert runs[f"global:{sensitive_query}"]["status"] == "failed"
    assert runs[f"global:{sensitive_query}"]["error"] == "ProviderResponseError"
    assert store.get_meta("poller:last_failure_utc") is not None
    assert store.get_meta("poller:last_success_utc") is None

    assert len(alerts) == 1
    component, event, kwargs = alerts[0]
    assert (component, event) == ("collector", "query_slot_coverage_incomplete")
    assert kwargs["severity"] == "warning"
    assert kwargs["details"]["expected_query_slot_count"] == 2
    assert kwargs["details"]["missing_query_slot_count"] == 1
    assert kwargs["details"]["reason_counts"] == {"failed": 1}
    rendered_alert = json.dumps(kwargs, sort_keys=True)
    assert sensitive_query not in rendered_alert
    assert "secret-query-token" not in rendered_alert
    assert secret_url not in rendered_alert
    assert "secret-provider-token" not in rendered_alert
    assert sensitive_query not in caplog.text
    assert secret_url not in caplog.text
    assert "secret-provider-token" not in caplog.text
    store.close()


@pytest.mark.unit
def test_coverage_alerts_once_per_transition_then_reminder_and_recovery(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "m.db")
    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: alerts.append(
            (component, event, kwargs)
        ) or True,
    )
    incomplete = {
        "complete": False,
        "query_slots": [{"provider": "globalnews", "query_key": "world"}],
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
        "missing_source_groups": [],
    }

    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=100.0
    )
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=200.0
    )
    assert [event for _, event, _ in alerts] == [
        "query_slot_coverage_incomplete"
    ]

    changed = {
        **incomplete,
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "empty"}
        ],
    }
    poller._update_coverage_alert_state(
        store, coverage=changed, observed_utc=300.0
    )
    poller._update_coverage_alert_state(
        store,
        coverage=changed,
        observed_utc=300.0 + poller._COVERAGE_ALERT_REMINDER_SECONDS,
    )
    complete = {
        "complete": True,
        "query_slots": incomplete["query_slots"],
        "missing_query_slots": [],
        "missing_source_groups": [],
    }
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=90_000.0
    )
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=90_100.0
    )

    assert [event for _, event, _ in alerts] == [
        "query_slot_coverage_incomplete",
        "query_slot_coverage_incomplete",
        "query_slot_coverage_recovered",
    ]
    assert [kwargs["severity"] for _, _, kwargs in alerts] == [
        "warning", "warning", "info"
    ]
    occurrence_keys = [kwargs["dedupe_key"] for _, _, kwargs in alerts]
    assert len(set(occurrence_keys)) == 3
    assert all(key.startswith("coverage-v2:") for key in occurrence_keys)
    assert alerts[1][2]["details"]["reminder_ordinal"] == 1
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0
    store.close()


@pytest.mark.unit
def test_coverage_alert_retries_after_webhook_delivery_failure(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")
    delivered = iter([False, True])
    alerts = []

    def capture(component, event, **kwargs):
        alerts.append((component, event, kwargs))
        return next(delivered)

    monkeypatch.setattr(poller, "emit_alert", capture)
    incomplete = {
        "complete": False,
        "query_slots": [{"provider": "globalnews", "query_key": "world"}],
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
        "missing_source_groups": [],
    }

    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=100.0
    )
    poller._update_coverage_alert_state(
        store,
        coverage={**incomplete, "complete": True, "missing_query_slots": []},
        observed_utc=150.0,
    )
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=200.0
    )
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=300.0
    )

    assert [event for _, event, _ in alerts] == [
        "query_slot_coverage_incomplete",
        "query_slot_coverage_incomplete",
    ]
    occurrence_keys = [kwargs["dedupe_key"] for _, _, kwargs in alerts]
    assert len(set(occurrence_keys)) == 2
    assert all(key.startswith("coverage-v2:") for key in occurrence_keys)
    assert store.get_meta(poller._COVERAGE_ALERT_LAST_UTC_KEY) == 200.0
    store.close()


@pytest.mark.unit
def test_new_coverage_incident_does_not_inherit_prior_alert_timer(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "m.db")
    deliveries = iter([True, True, False, True])
    alerts = []

    def capture(_component, event, **kwargs):
        alerts.append((event, kwargs["dedupe_key"]))
        return next(deliveries)

    monkeypatch.setattr(poller, "emit_alert", capture)
    incomplete = {
        "complete": False,
        "query_slots": [{"provider": "globalnews", "query_key": "world"}],
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
        "missing_source_groups": [],
    }
    complete = {**incomplete, "complete": True, "missing_query_slots": []}

    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=100.0
    )
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=200.0
    )
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=300.0
    )
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=400.0
    )

    assert [event for event, _ in alerts] == [
        "query_slot_coverage_incomplete",
        "query_slot_coverage_recovered",
        "query_slot_coverage_incomplete",
        "query_slot_coverage_incomplete",
    ]
    assert len({key for _, key in alerts[:3]}) == 3
    assert alerts[2][1] == alerts[3][1]
    assert store.get_meta(poller._COVERAGE_ALERT_LAST_UTC_KEY) == 400.0
    store.close()


@pytest.mark.unit
def test_coverage_incident_identity_is_durable_before_delivery(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")
    attempts = []
    incomplete = {
        "complete": False,
        "query_slots": [{"provider": "globalnews", "query_key": "world"}],
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
        "missing_source_groups": [],
    }

    def interrupted_delivery(_component, _event, **kwargs):
        attempts.append(kwargs["dedupe_key"])
        assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 1.0
        assert store.get_meta(poller._COVERAGE_ALERT_STARTED_UTC_KEY) == 100.0
        occurrence = store.get_meta(poller._COVERAGE_ALERT_INCIDENT_KEY)
        assert kwargs["dedupe_key"] == f"coverage-v2:{int(occurrence)}"
        raise RuntimeError("process interrupted after receiver accepted the alert")

    monkeypatch.setattr(poller, "emit_alert", interrupted_delivery)
    with pytest.raises(RuntimeError, match="process interrupted"):
        poller._update_coverage_alert_state(
            store, coverage=incomplete, observed_utc=100.0
        )

    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda _component, _event, **kwargs: attempts.append(
            kwargs["dedupe_key"]
        ) or True,
    )
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=200.0
    )

    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert store.get_meta(poller._COVERAGE_ALERT_LAST_UTC_KEY) == 200.0
    store.close()


@pytest.mark.unit
def test_coverage_occurrences_survive_ack_loss_beyond_two_hours(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "m.db")
    attempts = []
    long_retry_seconds = 3 * 60 * 60 + 1
    incomplete = {
        "complete": False,
        "query_slots": [{"provider": "globalnews", "query_key": "world"}],
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
        "missing_source_groups": [],
    }
    complete = {**incomplete, "complete": True, "missing_query_slots": []}

    def lose_ack(_component, event, **kwargs):
        attempts.append((event, kwargs["dedupe_key"]))
        raise RuntimeError("receiver accepted before the process stopped")

    def acknowledge(_component, event, **kwargs):
        attempts.append((event, kwargs["dedupe_key"]))
        return True

    monkeypatch.setattr(poller, "emit_alert", lose_ack)
    with pytest.raises(RuntimeError, match="receiver accepted"):
        poller._update_coverage_alert_state(
            store, coverage=incomplete, observed_utc=100.0
        )
    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    initial_retry_utc = 100.0 + long_retry_seconds
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=initial_retry_utc
    )

    reminder_utc = initial_retry_utc + poller._COVERAGE_ALERT_REMINDER_SECONDS
    monkeypatch.setattr(poller, "emit_alert", lose_ack)
    with pytest.raises(RuntimeError, match="receiver accepted"):
        poller._update_coverage_alert_state(
            store, coverage=incomplete, observed_utc=reminder_utc
        )
    assert store.get_meta(poller._COVERAGE_ALERT_PENDING_ORDINAL_KEY) == 1.0
    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    reminder_retry_utc = reminder_utc + long_retry_seconds
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=reminder_retry_utc
    )

    recovery_utc = reminder_retry_utc + 100.0
    monkeypatch.setattr(poller, "emit_alert", lose_ack)
    with pytest.raises(RuntimeError, match="receiver accepted"):
        poller._update_coverage_alert_state(
            store, coverage=complete, observed_utc=recovery_utc
        )
    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    poller._update_coverage_alert_state(
        store,
        coverage=complete,
        observed_utc=recovery_utc + long_retry_seconds,
    )

    assert [event for event, _ in attempts] == [
        "query_slot_coverage_incomplete",
        "query_slot_coverage_incomplete",
        "query_slot_coverage_incomplete",
        "query_slot_coverage_incomplete",
        "query_slot_coverage_recovered",
        "query_slot_coverage_recovered",
    ]
    assert attempts[0][1] == attempts[1][1]
    assert attempts[2][1] == attempts[3][1]
    assert attempts[4][1] == attempts[5][1]
    assert len({attempts[0][1], attempts[2][1], attempts[4][1]}) == 3
    assert store.get_meta(poller._COVERAGE_ALERT_REMINDER_ORDINAL_KEY) == 0.0
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0
    store.close()


@pytest.mark.unit
def test_coverage_state_write_gaps_retry_the_same_occurrence(monkeypatch):
    class Store:
        def __init__(self):
            self.values = {}
            self.fail_next_key = None

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            if key == self.fail_next_key:
                self.fail_next_key = None
                raise RuntimeError("simulated state-write gap")
            self.values[key] = value

    store = Store()
    attempts = []
    long_retry_seconds = 3 * 60 * 60 + 1
    incomplete = {
        "complete": False,
        "query_slots": [],
        "missing_query_slots": [],
        "missing_source_groups": [],
    }
    complete = {**incomplete, "complete": True}

    def fail_after_ack(_component, event, **kwargs):
        attempts.append((event, kwargs["dedupe_key"]))
        store.fail_next_key = (
            poller._COVERAGE_ALERT_STATE_KEY
            if event == "query_slot_coverage_recovered"
            else poller._COVERAGE_ALERT_LAST_UTC_KEY
        )
        return True

    def acknowledge(_component, event, **kwargs):
        attempts.append((event, kwargs["dedupe_key"]))
        return True

    monkeypatch.setattr(poller, "emit_alert", fail_after_ack)
    with pytest.raises(RuntimeError, match="state-write gap"):
        poller._update_coverage_alert_state(
            store, coverage=incomplete, observed_utc=100.0
        )
    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    initial_retry_utc = 100.0 + long_retry_seconds
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=initial_retry_utc
    )

    reminder_utc = initial_retry_utc + poller._COVERAGE_ALERT_REMINDER_SECONDS
    monkeypatch.setattr(poller, "emit_alert", fail_after_ack)
    with pytest.raises(RuntimeError, match="state-write gap"):
        poller._update_coverage_alert_state(
            store, coverage=incomplete, observed_utc=reminder_utc
        )
    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    reminder_retry_utc = reminder_utc + long_retry_seconds
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=reminder_retry_utc
    )

    recovery_utc = reminder_retry_utc + 100.0
    monkeypatch.setattr(poller, "emit_alert", fail_after_ack)
    with pytest.raises(RuntimeError, match="state-write gap"):
        poller._update_coverage_alert_state(
            store, coverage=complete, observed_utc=recovery_utc
        )
    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    poller._update_coverage_alert_state(
        store,
        coverage=complete,
        observed_utc=recovery_utc + long_retry_seconds,
    )

    assert attempts[0][1] == attempts[1][1]
    assert attempts[2][1] == attempts[3][1]
    assert attempts[4][1] == attempts[5][1]
    assert len({attempts[0][1], attempts[2][1], attempts[4][1]}) == 3
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0


@pytest.mark.unit
def test_acknowledged_reminder_finishes_an_interrupted_state_commit(monkeypatch):
    class Store:
        def __init__(self):
            self.values = {
                poller._COVERAGE_ALERT_STATE_KEY: 1.0,
                poller._COVERAGE_ALERT_STARTED_UTC_KEY: 100.0,
                poller._COVERAGE_ALERT_SEQUENCE_KEY: 101.0,
                poller._COVERAGE_ALERT_INCIDENT_KEY: 101.0,
                poller._COVERAGE_ALERT_DELIVERED_KEY: 1.0,
                poller._COVERAGE_ALERT_LAST_UTC_KEY: 100.0,
                poller._COVERAGE_ALERT_REMINDER_ORDINAL_KEY: 0.0,
            }
            self.fail_next_key = None

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            if key == self.fail_next_key:
                self.fail_next_key = None
                raise RuntimeError("simulated ordinal-write gap")
            self.values[key] = value

    store = Store()
    attempts = []
    long_retry_seconds = 3 * 60 * 60 + 1

    def acknowledge(_component, _event, **kwargs):
        attempts.append(kwargs["dedupe_key"])
        store.fail_next_key = poller._COVERAGE_ALERT_REMINDER_ORDINAL_KEY
        return True

    monkeypatch.setattr(poller, "emit_alert", acknowledge)
    incomplete = {
        "complete": False,
        "query_slots": [],
        "missing_query_slots": [],
        "missing_source_groups": [],
    }
    with pytest.raises(RuntimeError, match="ordinal-write gap"):
        poller._update_coverage_alert_state(
            store,
            coverage=incomplete,
            observed_utc=100.0 + poller._COVERAGE_ALERT_REMINDER_SECONDS,
        )

    assert store.get_meta(poller._COVERAGE_ALERT_ACKED_REMINDER_KEY) is not None
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *_args, **_kwargs: pytest.fail("acknowledged reminder was resent"),
    )
    poller._update_coverage_alert_state(
        store,
        coverage=incomplete,
        observed_utc=(
            100.0
            + poller._COVERAGE_ALERT_REMINDER_SECONDS
            + long_retry_seconds
        ),
    )

    assert len(attempts) == 1
    assert store.get_meta(poller._COVERAGE_ALERT_REMINDER_ORDINAL_KEY) == 1.0
    assert store.get_meta(poller._COVERAGE_ALERT_REMINDER_KEY) == 0.0
    assert store.get_meta(poller._COVERAGE_ALERT_ACKED_REMINDER_KEY) == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("bad_identity", [None, float("nan"), -1.0, 1.5])
def test_recovery_repairs_and_persists_its_identity_before_delivery(
    monkeypatch, bad_identity,
):
    class Store:
        def __init__(self):
            self.values = {
                poller._COVERAGE_ALERT_STATE_KEY: 1.0,
                poller._COVERAGE_ALERT_STARTED_UTC_KEY: 100.0,
                poller._COVERAGE_ALERT_SEQUENCE_KEY: 101.0,
                poller._COVERAGE_ALERT_INCIDENT_KEY: 101.0,
                poller._COVERAGE_ALERT_RECOVERY_KEY: bad_identity,
                poller._COVERAGE_ALERT_DELIVERED_KEY: 1.0,
                poller._COVERAGE_ALERT_LAST_UTC_KEY: 100.0,
            }

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            self.values[key] = value

    store = Store()
    attempts = []
    deliveries = iter([False, True])
    long_retry_seconds = 3 * 60 * 60 + 1

    def capture(_component, _event, **kwargs):
        persisted = store.get_meta(poller._COVERAGE_ALERT_RECOVERY_KEY)
        attempts.append((kwargs["dedupe_key"], persisted))
        assert kwargs["dedupe_key"] == f"coverage-v2:{int(persisted)}"
        return next(deliveries)

    monkeypatch.setattr(poller, "emit_alert", capture)
    complete = {
        "complete": True,
        "query_slots": [],
        "missing_query_slots": [],
        "missing_source_groups": [],
    }
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=200.0
    )
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=200.0 + long_retry_seconds
    )

    assert attempts[0] == attempts[1]
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0


@pytest.mark.unit
def test_stale_pending_reminder_ordinal_repairs_forward(monkeypatch):
    class Store:
        values = {
            poller._COVERAGE_ALERT_STATE_KEY: 1.0,
            poller._COVERAGE_ALERT_STARTED_UTC_KEY: 100.0,
            poller._COVERAGE_ALERT_SEQUENCE_KEY: 500.0,
            poller._COVERAGE_ALERT_INCIDENT_KEY: 101.0,
            poller._COVERAGE_ALERT_DELIVERED_KEY: 1.0,
            poller._COVERAGE_ALERT_LAST_UTC_KEY: 199.0,
            poller._COVERAGE_ALERT_REMINDER_KEY: 500.0,
            poller._COVERAGE_ALERT_REMINDER_ORDINAL_KEY: 5.0,
            poller._COVERAGE_ALERT_PENDING_ORDINAL_KEY: 1.0,
        }

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            self.values[key] = value

    store = Store()
    attempts = []

    def capture(_component, event, **kwargs):
        attempts.append((event, kwargs))
        assert store.get_meta(poller._COVERAGE_ALERT_PENDING_ORDINAL_KEY) == 6.0
        return True

    monkeypatch.setattr(poller, "emit_alert", capture)
    poller._update_coverage_alert_state(
        store,
        coverage={
            "complete": False,
            "query_slots": [],
            "missing_query_slots": [],
            "missing_source_groups": [],
        },
        observed_utc=200.0,
    )

    assert attempts[0][1]["dedupe_key"] == "coverage-v2:500"
    assert attempts[0][1]["details"]["reminder_ordinal"] == 6
    assert store.get_meta(poller._COVERAGE_ALERT_REMINDER_ORDINAL_KEY) == 6.0


@pytest.mark.unit
@pytest.mark.parametrize("bad_timestamp", [float("nan"), float("inf"), "bad"])
def test_corrupt_coverage_alert_timestamps_cannot_suppress_delivery(
    monkeypatch, bad_timestamp,
):
    class Store:
        values = {
            poller._COVERAGE_ALERT_STATE_KEY: 1.0,
            poller._COVERAGE_ALERT_STARTED_UTC_KEY: 100.0,
            poller._COVERAGE_ALERT_SEQUENCE_KEY: 101.0,
            poller._COVERAGE_ALERT_INCIDENT_KEY: 101.0,
            poller._COVERAGE_ALERT_DELIVERED_KEY: 1.0,
            poller._COVERAGE_ALERT_LAST_UTC_KEY: bad_timestamp,
        }

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            self.values[key] = value

    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda _component, event, **kwargs: alerts.append(
            (event, kwargs["dedupe_key"])
        ) or True,
    )

    poller._update_coverage_alert_state(
        Store(),
        coverage={
            "complete": False,
            "query_slots": [],
            "missing_query_slots": [],
            "missing_source_groups": [],
        },
        observed_utc=200.0,
    )

    assert alerts == [("query_slot_coverage_incomplete", "coverage-v2:201")]


@pytest.mark.unit
def test_coverage_alert_clock_rollback_does_not_duplicate_an_active_incident(monkeypatch):
    class Store:
        def __init__(self):
            self.values = {
                poller._COVERAGE_ALERT_STATE_KEY: 1.0,
                poller._COVERAGE_ALERT_STARTED_UTC_KEY: 300.0,
                poller._COVERAGE_ALERT_SEQUENCE_KEY: 301.0,
                poller._COVERAGE_ALERT_INCIDENT_KEY: 301.0,
                poller._COVERAGE_ALERT_DELIVERED_KEY: 1.0,
                poller._COVERAGE_ALERT_LAST_UTC_KEY: 300.0,
            }

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            self.values[key] = value

    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *_args, **_kwargs: alerts.append(True) or True,
    )

    poller._update_coverage_alert_state(
        Store(),
        coverage={
            "complete": False,
            "query_slots": [],
            "missing_query_slots": [],
            "missing_source_groups": [],
        },
        observed_utc=200.0,
    )

    assert alerts == []


@pytest.mark.unit
def test_coverage_recovery_retries_only_after_a_delivered_incident(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "m.db")
    deliveries = iter([True, False, True])
    events = []

    def capture(_component, event, **_kwargs):
        events.append(event)
        return next(deliveries)

    monkeypatch.setattr(poller, "emit_alert", capture)
    incomplete = {
        "complete": False,
        "query_slots": [{"provider": "globalnews", "query_key": "world"}],
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
        "missing_source_groups": [],
    }
    complete = {
        **incomplete,
        "complete": True,
        "missing_query_slots": [],
    }

    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=100.0
    )
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=200.0
    )
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 1.0
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=300.0
    )
    poller._update_coverage_alert_state(
        store, coverage=complete, observed_utc=400.0
    )

    assert events == [
        "query_slot_coverage_incomplete",
        "query_slot_coverage_recovered",
        "query_slot_coverage_recovered",
    ]
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0
    assert store.get_meta(poller._COVERAGE_ALERT_DELIVERED_KEY) == 0.0
    store.close()


@pytest.mark.unit
def test_recovery_commits_the_incident_boundary_before_auxiliary_cleanup(monkeypatch):
    class Store:
        def __init__(self):
            self.values = {
                poller._COVERAGE_ALERT_STATE_KEY: 1.0,
                poller._COVERAGE_ALERT_STARTED_UTC_KEY: 100.0,
                poller._COVERAGE_ALERT_DELIVERED_KEY: 1.0,
                poller._COVERAGE_ALERT_LAST_UTC_KEY: 100.0,
            }
            self.fail_cleanup = True

        def get_meta(self, key):
            return self.values.get(key)

        def set_meta(self, key, value):
            self.values[key] = value
            if self.fail_cleanup and key == poller._COVERAGE_ALERT_DELIVERED_KEY:
                raise RuntimeError("simulated disconnect during cleanup")

    store = Store()
    events = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda _component, event, **kwargs: events.append(
            (event, kwargs["dedupe_key"])
        ) or True,
    )
    complete = {
        "complete": True,
        "query_slots": [],
        "missing_query_slots": [],
        "missing_source_groups": [],
    }
    incomplete = {
        **complete,
        "complete": False,
        "missing_query_slots": [
            {"provider": "globalnews", "query_key": "world", "reason": "failed"}
        ],
    }

    with pytest.raises(RuntimeError, match="simulated disconnect"):
        poller._update_coverage_alert_state(
            store, coverage=complete, observed_utc=200.0
        )
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0

    store.fail_cleanup = False
    poller._update_coverage_alert_state(
        store, coverage=incomplete, observed_utc=300.0
    )

    assert [event for event, _ in events] == [
        "query_slot_coverage_recovered",
        "query_slot_coverage_incomplete",
    ]
    assert events[0][1] != events[1][1]


@pytest.mark.unit
def test_complete_cycle_sets_success_heartbeat_without_alert(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")
    alerts = []
    monkeypatch.setattr(
        poller,
        "fetch_global_news",
        lambda query, captured, theme, *, limit: [
            _row(
                "globalnews", query, f"@{theme}", captured,
                created_utc=captured, title="Global update",
            )
        ],
    )
    monkeypatch.setattr(poller, "emit_alert", lambda *args, **kwargs: alerts.append((args, kwargs)))
    monkeypatch.setattr(poller, "fetch_polymarket_odds", lambda *args, **kwargs: [])

    poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={
            "global": {
                "queries": ["policy", "technology"],
                "prediction_topics": ["no matching market is valid"],
            }
        },
    )

    assert store.get_meta("poller:last_success_utc") is not None
    assert store.get_meta("poller:last_failure_utc") is None
    assert store.fetch_runs(provider="polymarket")[0]["status"] == "empty"
    assert alerts == []
    store.close()


@pytest.mark.unit
def test_collector_audit_requires_all_ten_globalnews_slots(capsys):
    expected = poller._globalnews_query_slots(poller._global_only_news_themes())
    assert len(expected) == 10
    database_now = 1_786_080_000.0

    captured = {}

    class AuditStore:
        def server_observed_utc(self):
            return database_now

        def coverage_report(self, cutoff, groups, **kwargs):
            captured.update(cutoff=cutoff, groups=groups, kwargs=kwargs)
            slots = kwargs["expected_query_slots"]
            return {
                "complete": False,
                "query_slots": [{"provider": provider, "query_key": query}
                                for provider, query in slots],
                "missing_query_slots": [{"provider": provider, "query_key": query}
                                        for provider, query in slots],
            }

        def fetch_runs(self, limit):
            pytest.fail("current-health audit must not read historical receipts")

        def collection_cycle(self, _cycle_id):
            return None

        def collection_cycle_identities(self, cycle_kind, *, period_key):
            assert cycle_kind == "x-daily"
            assert period_key
            return []

    poller.print_audit(AuditStore())

    output = capsys.readouterr().out
    assert captured["cutoff"] == database_now
    assert captured["kwargs"]["expected_query_slots"] == expected
    assert captured["kwargs"]["max_age_seconds"] == 4500.0
    assert "collector_expected_query_slots=10" in output
    assert "collector_missing_query_slots=10" in output
    assert "collector_x_current_state=scheduled" in output
    assert "collector_x_prior_state=missing" in output
    assert "collector_immutable_receipt_history" not in output


@pytest.mark.unit
@pytest.mark.parametrize(
    ("database_now", "expected_state", "expected_complete"),
    [
        (
            datetime(2026, 8, 5, 20, 59, tzinfo=timezone.utc).timestamp(),
            "scheduled",
            True,
        ),
        (
            datetime(2026, 8, 5, 23, 46, tzinfo=timezone.utc).timestamp(),
            "missing",
            False,
        ),
    ],
)
def test_collector_audit_combines_news_and_scheduled_x_health(
    capsys, database_now, expected_state, expected_complete,
):
    class AuditStore:
        def server_observed_utc(self):
            return database_now

        def coverage_report(self, cutoff, groups, **kwargs):
            return {
                "complete": True,
                "query_slots": [
                    {"provider": provider, "query_key": query}
                    for provider, query in kwargs["expected_query_slots"]
                ],
                "missing_query_slots": [],
            }

        def collection_cycle(self, _cycle_id):
            return None

        def collection_cycle_identities(self, _cycle_kind, *, period_key):
            assert period_key
            return []

    poller.print_audit(AuditStore())

    output = capsys.readouterr().out
    assert f"collector_coverage_complete={str(expected_complete).lower()}" in output
    assert f"collector_x_current_state={expected_state}" in output
    assert "collector_x_prior_state=missing" in output


@pytest.mark.unit
def test_collector_audit_history_is_opt_in_and_clearly_delimited(capsys):
    expected = poller._globalnews_query_slots(poller._global_only_news_themes())

    class AuditStore:
        def server_observed_utc(self):
            return 1_786_080_000.0

        def coverage_report(self, cutoff, groups, **kwargs):
            return {
                "complete": True,
                "query_slots": [
                    {"provider": provider, "query_key": query}
                    for provider, query in kwargs["expected_query_slots"]
                ],
                "missing_query_slots": [],
            }

        def fetch_runs(self, limit):
            assert limit == 25
            return [{
                "started_utc": 100.0,
                "provider": "globalnews",
                "status": "failed",
                "item_count": 0,
                "inserted_count": 0,
                "cost_units": 0.0,
                "query_key": expected[0][1],
            }]

        def collection_cycle(self, _cycle_id):
            return None

        def collection_cycle_identities(self, _cycle_kind, *, period_key):
            assert period_key
            return []

    poller.print_audit(AuditStore(), include_history=True)

    output = capsys.readouterr().out
    begin = output.index("collector_immutable_receipt_history_begin")
    note = output.index(
        "collector_immutable_receipt_history_note="
        "historical_receipts_do_not_override_current_health"
    )
    receipt = output.index("globalnews failed items=0")
    end = output.index("collector_immutable_receipt_history_end")
    assert begin < note < receipt < end


@pytest.mark.unit
@pytest.mark.parametrize(
    ("flag", "include_history"),
    [("--audit", False), ("--audit-history", True)],
)
def test_collector_audit_cli_selects_history_explicitly(
    monkeypatch, flag, include_history,
):
    class Store:
        def close(self):
            return None

    store = Store()
    calls = []
    monkeypatch.setattr(poller, "open_store", lambda _db: store)
    monkeypatch.setattr(
        poller,
        "print_audit",
        lambda selected, **kwargs: calls.append((selected, kwargs)),
    )
    monkeypatch.setattr(
        poller,
        "print_stats",
        lambda *_args, **_kwargs: pytest.fail("audit command printed stats"),
    )

    poller.main([flag])

    assert calls == [(store, {"include_history": include_history})]


def _compatible_x_cycle_spec(instant, index=0):
    identity = poller.GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES[index]
    return poller._x_collection_cycle_spec_for_identity(instant, identity)


def _running_x_cycle(spec, started):
    identity = spec["identity"]
    return {
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": identity["cycle_kind"],
        "period_key": identity["period_key"],
        "protocol_id": identity["protocol_id"],
        "collector_semantics_id": identity["collector_semantics_id"],
        "identity_valid": True,
        "identity": identity,
        "started_utc": started,
        "completed_utc": None,
        "status": "running",
        "manifest_id": None,
        "manifest": None,
        "manifest_valid": False,
        "server_started_utc": started,
        "server_terminal_utc": None,
        "collector_build_id": "build_" + "b" * 24,
    }


@pytest.mark.unit
def test_x_cycle_trend_requirement_comes_from_candidate_identity():
    spec = poller._x_collection_cycle_spec_for_identity(
        1_786_080_000.0,
        {
            "protocol_id": "protocol_" + "d" * 24,
            "collector_semantics_id": "collector_" + "e" * 24,
            "x_daily_static_slots": (
                ("xtrend", "woeid:42"),
                ("trendnews", "ranked-global-discovery"),
            ),
            "x_daily_max_dynamic_slots": 1,
        },
    )
    identity = spec["identity"]
    started = 1_786_080_000.0
    completed = started + 10
    build_id = "build_" + "b" * 24
    receipts = [
        {
            "slot_kind": "static",
            "provider": "trendnews",
            "query_key": "ranked-global-discovery",
            "fetch_run_id": "00000000-0000-4000-8000-000000000001",
            "status": "success",
            "item_count": 1,
            "raw_content_ids": [],
        },
        {
            "slot_kind": "static",
            "provider": "xtrend",
            "query_key": "woeid:42",
            "fetch_run_id": "00000000-0000-4000-8000-000000000002",
            "status": "success",
            "item_count": 1,
            "raw_content_ids": [],
        },
    ]
    manifest = {
        "schema_version": 2,
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": "x-daily",
        "period_key": identity["period_key"],
        "protocol_id": identity["protocol_id"],
        "collector_semantics_id": identity["collector_semantics_id"],
        "started_utc": started,
        "completed_utc": completed,
        "status": "complete",
        "expected_static_slots": identity["expected_static_slots"],
        "expected_dynamic_slots": [],
        "slot_receipts": receipts,
        "server_started_utc": started,
        "server_terminal_utc": completed,
        "collector_build_id": build_id,
    }
    cycle = {
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": "x-daily",
        "period_key": identity["period_key"],
        "protocol_id": identity["protocol_id"],
        "collector_semantics_id": identity["collector_semantics_id"],
        "identity_valid": True,
        "identity": identity,
        "started_utc": started,
        "completed_utc": completed,
        "status": "complete",
        "manifest_valid": True,
        "manifest": manifest,
        "manifest_id": poller.content_id(manifest, prefix="cycle_manifest_"),
        "server_started_utc": started,
        "server_terminal_utc": completed,
        "collector_build_id": build_id,
    }

    assert poller._x_collection_cycle_state(spec, cycle) == "complete"


def _finish_compatible_x_cycle(store, instant, *, with_receipts, index=0):
    spec = _compatible_x_cycle_spec(instant, index)
    cycle_id = store.start_collection_cycle(spec, started_utc=instant)
    if with_receipts:
        for woeid in poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "x_trend_woeids"
        ]:
            query_key = f"woeid:{int(woeid)}"
            poller._run_fetch(
                store,
                provider="xtrend",
                query_key=query_key,
                fetch_fn=lambda captured, location=woeid: [
                    _row(
                        "xtrend",
                        f"trend-{int(location)}",
                        f"@X_TREND_{int(location)}",
                        captured,
                        title=f"Global trend {int(location)}",
                    )
                ],
                collection_cycle_id=cycle_id,
            )
        poller._run_fetch(
            store,
            provider="trendnews",
            query_key="ranked-global-discovery",
            fetch_fn=lambda _captured: [],
            collection_cycle_id=cycle_id,
        )
    store.finish_collection_cycle(cycle_id, completed_utc=instant)
    return spec


def _forbid_x_provider_calls(monkeypatch):
    for provider_name in (
        "fetch_top_news_headlines", "fetch_x_trends", "fetch_x_topic",
    ):
        monkeypatch.setattr(
            poller,
            provider_name,
            lambda *_args, selected=provider_name, **_kwargs: pytest.fail(
                f"compatible handoff called {selected}"
            ),
        )


@pytest.mark.unit
def test_x_search_budget_stops_paid_cycle_without_a_redundant_alert(
    monkeypatch, caplog,
):
    now = 1_786_080_000.0
    headlines = [
        {
            "category": "technology",
            "external_id": "news-1",
            "title": "Independent technology report",
            "body": "",
            "publisher": "Reuters",
            "created_utc": now,
            "region": "US",
            "rank": 0,
            "metadata": {"publisher_domain": "reuters.com"},
        },
        {
            "category": "world",
            "external_id": "news-2",
            "title": "Independent world report",
            "body": "",
            "publisher": "Associated Press",
            "created_utc": now,
            "region": "US",
            "rank": 0,
            "metadata": {"publisher_domain": "apnews.com"},
        },
    ]
    topics = poller._formally_grounded_discovery_topics(
        poller.discover_x_topics(max_topics=3, headlines=headlines, trends=[]), now
    )
    cycle_id = "cycle_" + "1" * 24
    attempted_searches = []

    class Store:
        def declare_collection_cycle_slots(
            self, collection_cycle_id, slots, *, declared_utc,
        ):
            assert collection_cycle_id == cycle_id
            assert declared_utc > 0
            self.slots = slots

    store = Store()

    def run_fetch(_store, *, provider, fetch_fn, **kwargs):
        if provider == "trendnews":
            rows = fetch_fn(now)
            assert len(rows) == len(topics) + 1
            return len(rows), len(rows), "success"
        if provider == "x":
            attempted_searches.append(kwargs["query_key"])
            raise poller._FetchBudgetExceeded("budget exhausted")
        return 0, 0, "empty"

    monkeypatch.setattr(poller, "_run_fetch", run_fetch)
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *_args, **_kwargs: pytest.fail("budget exhaustion sent an alert"),
    )

    with caplog.at_level(logging.INFO):
        slots = poller._poll_x_cycle_children(
            store,
            now=now,
            limit=10,
            max_topics=3,
            collection_cycle_id=cycle_id,
            expected_slots=[],
            discovery_headlines=headlines,
        )

    expected = [
        ("x", request["query_key"])
        for request in poller._group_x_search_topics(topics)
    ]
    assert slots == expected
    assert store.slots == expected
    assert attempted_searches == [expected[0][1]]
    assert "X daily search budget reached; stopping paid cycle" in caplog.text


@pytest.mark.unit
def test_complete_compatible_x_cycle_handoffs_without_duplicate_paid_work(
    tmp_path, monkeypatch,
):
    instant = 1_786_080_000.0
    monkeypatch.setattr(poller.time, "time", lambda: instant)
    store = SqliteMediaStore(tmp_path / "compatible-x.db")
    monkeypatch.setattr(store, "server_observed_utc", lambda: instant)
    compatible_spec = _finish_compatible_x_cycle(
        store, instant, with_receipts=True
    )
    current_spec = poller._x_collection_cycle_spec(instant, 3)
    initial_receipts = store.fetch_runs(limit=100)

    _forbid_x_provider_calls(monkeypatch)

    assert poller._x_daily_requirement_state(store, instant, 3) == "complete"
    assert set(poller.poll_x_topics_once(store, instant, 10, 3)) == {
        (slot["provider"], slot["query_key"])
        for slot in compatible_spec["identity"]["expected_static_slots"]
    }
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert coverage["complete"] is True
    assert coverage["periodic_requirements"] == {"x_daily": "complete"}
    assert store.collection_cycle(current_spec["collection_cycle_id"]) is None
    assert store.fetch_runs(limit=100) == initial_receipts
    store.close()


@pytest.mark.unit
def test_first_present_compatible_x_cycle_wins_with_multiple_prior_cycles(
    tmp_path, monkeypatch,
):
    instant = 1_786_080_000.0
    monkeypatch.setattr(poller.time, "time", lambda: instant)
    store = SqliteMediaStore(tmp_path / "multiple-compatible-x.db")
    monkeypatch.setattr(store, "server_observed_utc", lambda: instant)
    second_spec = _finish_compatible_x_cycle(
        store, instant, with_receipts=False, index=2
    )
    first_spec = _finish_compatible_x_cycle(
        store, instant, with_receipts=True, index=1
    )
    initial_receipts = store.fetch_runs(limit=100)
    _forbid_x_provider_calls(monkeypatch)

    resolution = poller._x_daily_cycle_resolution(store, instant, 3)

    assert resolution["origin"] == "compatible"
    assert resolution["spec"] == first_spec
    assert resolution["state"] == "complete"
    assert resolution["cycle"]["collection_cycle_id"] \
        == first_spec["collection_cycle_id"]
    assert second_spec["collection_cycle_id"] \
        != first_spec["collection_cycle_id"]
    assert set(poller.poll_x_topics_once(store, instant, 10, 3)) == {
        (slot["provider"], slot["query_key"])
        for slot in first_spec["identity"]["expected_static_slots"]
    }
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert coverage["complete"] is True
    assert coverage["periodic_requirements"] == {"x_daily": "complete"}
    assert store.fetch_runs(limit=100) == initial_receipts
    store.close()


@pytest.mark.unit
def test_compatible_precedence_never_falls_through_based_on_outcome(
    tmp_path, monkeypatch,
):
    instant = 1_786_080_000.0
    monkeypatch.setattr(poller.time, "time", lambda: instant)
    store = SqliteMediaStore(tmp_path / "compatible-precedence-x.db")
    monkeypatch.setattr(store, "server_observed_utc", lambda: instant)
    second_spec = _finish_compatible_x_cycle(
        store, instant, with_receipts=True, index=2
    )
    first_spec = _finish_compatible_x_cycle(
        store, instant, with_receipts=False, index=1
    )
    initial_receipts = store.fetch_runs(limit=100)
    _forbid_x_provider_calls(monkeypatch)

    resolution = poller._x_daily_cycle_resolution(store, instant, 3)

    assert resolution["origin"] == "compatible"
    assert resolution["spec"] == first_spec
    assert resolution["state"] == "incomplete"
    assert resolution["cycle"]["collection_cycle_id"] \
        == first_spec["collection_cycle_id"]
    assert second_spec["collection_cycle_id"] \
        != first_spec["collection_cycle_id"]
    with pytest.raises(ValueError, match="not uniquely complete"):
        poller.poll_x_topics_once(store, instant, 10, 3)
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert coverage["complete"] is False
    assert coverage["periodic_requirements"] == {"x_daily": "incomplete"}
    assert store.fetch_runs(limit=100) == initial_receipts
    store.close()


@pytest.mark.unit
def test_current_x_cycle_precedes_a_complete_compatible_cycle(
    tmp_path, monkeypatch,
):
    instant = 1_786_080_000.0
    monkeypatch.setattr(poller.time, "time", lambda: instant)
    store = SqliteMediaStore(tmp_path / "current-precedence-x.db")
    monkeypatch.setattr(store, "server_observed_utc", lambda: instant)
    compatible_spec = _finish_compatible_x_cycle(
        store, instant, with_receipts=True
    )
    current_spec = poller._x_collection_cycle_spec(instant, 3)
    current_cycle_id = store.start_collection_cycle(
        current_spec, started_utc=instant
    )
    store.finish_collection_cycle(current_cycle_id, completed_utc=instant)
    initial_receipts = store.fetch_runs(limit=100)
    _forbid_x_provider_calls(monkeypatch)

    resolution = poller._x_daily_cycle_resolution(store, instant, 3)

    assert resolution["origin"] == "current"
    assert resolution["spec"] == current_spec
    assert resolution["state"] == "incomplete"
    assert compatible_spec["collection_cycle_id"] \
        != current_spec["collection_cycle_id"]
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert coverage["complete"] is False
    assert coverage["periodic_requirements"] == {"x_daily": "incomplete"}
    assert store.fetch_runs(limit=100) == initial_receipts
    store.close()


@pytest.mark.unit
def test_incomplete_compatible_x_cycle_blocks_force_but_stays_unhealthy(
    tmp_path, monkeypatch,
):
    instant = 1_786_080_000.0
    monkeypatch.setattr(poller.time, "time", lambda: instant)
    store = SqliteMediaStore(tmp_path / "incomplete-compatible-x.db")
    monkeypatch.setattr(store, "server_observed_utc", lambda: instant)
    _finish_compatible_x_cycle(store, instant, with_receipts=False)
    current_spec = poller._x_collection_cycle_spec(instant, 3)
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: pytest.fail(
            "an incomplete prior attempt must block a fresh paid cycle"
        ),
    )

    assert poller._x_daily_requirement_state(store, instant, 3) == "incomplete"
    with pytest.raises(ValueError, match="not uniquely complete"):
        poller.poll_x_topics_once(store, instant, 10, 3)
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert coverage["complete"] is False
    assert coverage["periodic_requirements"] == {"x_daily": "incomplete"}
    assert store.collection_cycle(current_spec["collection_cycle_id"]) is None
    assert store.fetch_runs(limit=100) == []
    store.close()


@pytest.mark.unit
def test_invalid_compatible_x_cycle_is_blocked_and_never_accepted(monkeypatch):
    instant = 1_786_080_000.0
    compatible_spec = _compatible_x_cycle_spec(instant)
    current_spec = poller._x_collection_cycle_spec(instant, 3)

    class Store:
        def collection_cycle(self, cycle_id):
            if cycle_id == current_spec["collection_cycle_id"]:
                return None
            if cycle_id == compatible_spec["collection_cycle_id"]:
                return {
                    "identity_valid": False,
                    "identity": compatible_spec["identity"],
                    "status": "complete",
                    "manifest_valid": True,
                    "manifest": {},
                }
            return None

    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: pytest.fail(
            "an invalid prior attempt must block paid work"
        ),
    )
    store = Store()

    assert poller._x_daily_requirement_state(store, instant, 3) == "invalid"
    with pytest.raises(ValueError, match="not uniquely complete"):
        poller.poll_x_topics_once(store, instant, 10, 3)


@pytest.mark.unit
def test_unlisted_x_cycle_is_not_considered_daily_completion():
    instant = 1_786_080_000.0
    unlisted = poller._x_collection_cycle_spec_for_identity(
        instant,
        {
            "protocol_id": "protocol_" + "d" * 24,
            "collector_semantics_id": "collector_" + "e" * 24,
            "x_daily_static_slots": (
                ("xtrend", "woeid:1"),
                ("xtrend", "woeid:23424977"),
                ("trendnews", "ranked-global-discovery"),
            ),
            "x_daily_max_dynamic_slots": 3,
        },
    )
    queried = []

    class Store:
        def collection_cycle(self, cycle_id):
            queried.append(cycle_id)
            if cycle_id == unlisted["collection_cycle_id"]:
                return {"status": "complete"}
            return None

        def collection_cycle_identities(self, cycle_kind, *, period_key):
            assert cycle_kind == "x-daily"
            assert period_key == unlisted["identity"]["period_key"]
            return [{
                "collection_cycle_id": unlisted["collection_cycle_id"],
                "protocol_id": "protocol_" + "d" * 24,
                "collector_semantics_id": "collector_" + "e" * 24,
            }]

    store = Store()

    assert poller._x_daily_requirement_state(store, instant, 3) == "invalid"
    with pytest.raises(ValueError, match="not recognized"):
        poller.poll_x_topics_once(store, instant, 10, 3)
    assert unlisted["collection_cycle_id"] not in queried


@pytest.mark.unit
def test_running_x_cycle_age_uses_database_clock(monkeypatch):
    instant = 1_786_080_000.0
    spec = poller._x_collection_cycle_spec(instant, 3)
    expected_slots = spec["identity"]["expected_static_slots"]

    class Store:
        def collection_cycle(self, cycle_id):
            assert cycle_id == spec["collection_cycle_id"]
            return _running_x_cycle(spec, instant - 1.0)

        def server_observed_utc(self):
            return instant

        def collection_cycle_slots(self, cycle_id):
            assert cycle_id == spec["collection_cycle_id"]
            return expected_slots

        def recover_collection_cycle(self, *_args, **_kwargs):
            pytest.fail("application clock skew must not trigger recovery")

    monkeypatch.setattr(poller.time, "time", lambda: instant + 100_000.0)

    assert poller.poll_x_topics_once(Store(), instant, 10, 3) == [
        (slot["provider"], slot["query_key"]) for slot in expected_slots
    ]


@pytest.mark.unit
def test_collector_x_audit_reports_exact_cycle_request_counts():
    from datetime import date, datetime, timezone

    period = date(2026, 8, 5)
    instant = datetime(2026, 8, 5, tzinfo=timezone.utc).timestamp()
    spec = poller._x_collection_cycle_spec(instant, 3)
    terminal = instant + 100.0
    build_id = "build_" + "b" * 24
    static_slots = spec["identity"]["expected_static_slots"]
    dynamic_slots = [
        {"provider": "x", "query_key": "global topic one"},
        {"provider": "x", "query_key": "global topic two"},
    ]
    slots = [*static_slots, *dynamic_slots]
    item_counts = [0, 4, 5, 10, 7]
    receipts = [
        {
            "slot_kind": "static" if slot in static_slots else "dynamic",
            **slot,
            "fetch_run_id": f"00000000-0000-4000-8000-{index + 1:012x}",
                "status": "success" if item_counts[index] else "empty",
            "item_count": item_counts[index],
            "raw_content_ids": [],
        }
        for index, slot in enumerate(slots)
    ]
    manifest = {
        "schema_version": 2,
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": spec["identity"]["cycle_kind"],
        "period_key": spec["identity"]["period_key"],
        "protocol_id": spec["identity"]["protocol_id"],
        "collector_semantics_id": spec["identity"]["collector_semantics_id"],
        "started_utc": instant,
        "completed_utc": terminal,
        "status": "complete",
        "expected_static_slots": static_slots,
        "expected_dynamic_slots": dynamic_slots,
        "slot_receipts": receipts,
        "server_started_utc": instant,
        "server_terminal_utc": terminal,
        "collector_build_id": build_id,
    }
    terminal_cycle = {
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": spec["identity"]["cycle_kind"],
        "period_key": spec["identity"]["period_key"],
        "protocol_id": spec["identity"]["protocol_id"],
        "collector_semantics_id": spec["identity"]["collector_semantics_id"],
        "identity_valid": True,
        "identity": spec["identity"],
        "started_utc": instant,
        "completed_utc": terminal,
        "status": "complete",
        "manifest_valid": True,
        "manifest": manifest,
        "manifest_id": poller.content_id(manifest, prefix="cycle_manifest_"),
        "server_started_utc": instant,
        "server_terminal_utc": terminal,
        "collector_build_id": build_id,
    }

    class Store:
        def collection_cycle(self, cycle_id):
            assert cycle_id == spec["collection_cycle_id"]
            return terminal_cycle

    projection = poller._x_cycle_audit_projection(Store(), period)

    assert projection == {
        "period": "2026-08-05",
        "state": "complete",
        "terminal_utc": datetime.fromtimestamp(terminal, timezone.utc).isoformat(),
        "trend_requests": 2,
        "search_requests": 2,
        "posts_returned": 17,
    }


@pytest.mark.unit
def test_poller_exposes_the_stable_declarative_collector_contract():
    manifest = poller.collector_semantics_manifest()

    assert manifest["collector_semantics_id"] == (
        poller.GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID
    )
    assert set(manifest) == {
        "schema_version", "normalization", "receipts", "wire_formats",
        "collector_semantics_id",
    }
    manifest["wire_formats"]["fetch_receipt_metadata"] = -1
    assert poller.collector_semantics_manifest()["wire_formats"][
        "fetch_receipt_metadata"
    ] == 1


def test_global_only_themes_have_news_but_no_prediction_market_queries():
    themes = poller._global_only_news_themes()

    assert len(poller._globalnews_query_slots(themes)) == 10
    assert all(spec["queries"] for spec in themes.values())
    assert all(spec["prediction_topics"] == [] for spec in themes.values())


@pytest.mark.unit
def test_alert_test_has_no_database_or_provider_access(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: calls.append((component, event, kwargs)) or True,
    )
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: pytest.fail("alert test opened the database"),
    )

    poller.main(["--test-alert"])

    assert calls == [(
        "collector",
        "delivery_test",
        {
            "severity": "info",
            "details": {
                "schema_version": 1,
                "collector_policy": "global-only-editorial-and-trend-reaction-v2",
            },
        },
    )]
    assert json.loads(capsys.readouterr().out) == {
        "component": "collector",
        "delivered": True,
    }


@pytest.mark.unit
def test_preflight_is_read_only_sanitized_and_checks_production_contract(
    monkeypatch, capsys,
):
    secret_db = "postgresql+psycopg://collector:secret@db.internal/evidence"
    secret_direct_db = (
        "postgresql+psycopg://collector:direct-secret@direct.db.internal/evidence"
    )
    secret_webhook = "https://hooks.example.invalid/private-token"
    calls = []
    server_now = 1_786_080_000.0
    observed_spec = _compatible_x_cycle_spec(server_now)
    old_manifest = {
        "schema_version": 1,
        "collection_cycle_id": observed_spec["collection_cycle_id"],
        "status": "complete",
    }
    observed_cycle = {
        **_running_x_cycle(observed_spec, server_now - 10),
        "status": "complete",
        "completed_utc": server_now - 5,
        "server_terminal_utc": server_now - 5,
        "manifest": old_manifest,
        "manifest_id": poller.content_id(old_manifest, prefix="cycle_manifest_"),
    }
    assert poller._x_collection_cycle_state(observed_spec, observed_cycle) == "invalid"

    class Store:
        def server_observed_utc(self):
            return server_now

        def collector_runtime_preflight(self, *, direct_url=None):
            assert direct_url == secret_direct_db
            calls.append("preflight")
            return {
                "schema_version": 1,
                "contract": "collector-runtime-v1",
                "ready": True,
                "required_table_count": 9,
                "required_trigger_count": 6,
            }

        def collection_cycle_identities(self, cycle_kind, *, period_key):
            assert cycle_kind == "x-daily"
            assert period_key == observed_spec["identity"]["period_key"]
            calls.append("identities")
            return [{
                "collection_cycle_id": observed_spec["collection_cycle_id"],
                "protocol_id": observed_spec["identity"]["protocol_id"],
                "collector_semantics_id": observed_spec["identity"][
                    "collector_semantics_id"
                ],
            }]

        def collection_cycle(self, cycle_id):
            assert cycle_id == observed_spec["collection_cycle_id"]
            calls.append("cycle")
            return observed_cycle

        def close(self):
            calls.append("close")

    def fake_open_store(url, *, auto_migrate):
        assert url == secret_db
        assert auto_migrate is False
        calls.append("open")
        return Store()

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_AUTO_MIGRATE", "false")
    monkeypatch.setenv("MEDIA_DB_DIRECT_URL", secret_direct_db)
    monkeypatch.setenv("MEDIA_REQUIRE_ALERT_WEBHOOK", "true")
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", secret_webhook)
    monkeypatch.setenv("X_BEARER_TOKEN", "x-secret-token")
    monkeypatch.setattr(poller, "open_store", fake_open_store)
    monkeypatch.setattr(
        poller,
        "collector_semantics_manifest",
        lambda: {
            "collector_semantics_id": poller.GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID
        },
    )
    monkeypatch.setattr(poller, "build_identity", lambda: "build_" + "a" * 24)

    def fake_probe():
        calls.append("probe")
        return True

    monkeypatch.setattr(poller, "probe_alert_webhook", fake_probe)
    for provider_name in (
        "fetch_global_news", "fetch_x_topic", "fetch_x_trends",
    ):
        monkeypatch.setattr(
            poller,
            provider_name,
            lambda *_args, **_kwargs: pytest.fail("preflight called a provider"),
        )

    poller.main([
        "--global-only",
        "--preflight",
        "--sources", "x",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
        "--health-port", "5500",
        "--db", secret_db,
    ])

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 4
    assert payload["status"] == "ok"
    assert payload["database_contract"]["ready"] is True
    assert payload["x_identity_inventory_valid"] is True
    assert payload["x_identity_cycle_count"] == 1
    assert payload["x_repair_compatible_cycle_count"] == 1
    assert payload["x_evidence_health_validated"] is False
    assert payload["collection_protocol_id"] == (
        poller.GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID
    )
    assert payload["alert_webhook_required"] is True
    assert payload["alert_probe_delivered"] is True
    assert calls == [
        "open", "preflight", "identities", "cycle", "probe", "close"
    ]
    rendered = json.dumps(payload)
    assert secret_db not in rendered
    assert secret_direct_db not in rendered
    assert secret_webhook not in rendered
    assert "x-secret-token" not in rendered


@pytest.mark.unit
def test_preflight_repair_boundary_rejects_unauthenticated_cycle_content():
    server_now = 1_786_080_000.0
    spec = _compatible_x_cycle_spec(server_now)
    manifest = {
        "schema_version": 1,
        "collection_cycle_id": spec["collection_cycle_id"],
        "status": "incomplete",
    }
    cycle = {
        **_running_x_cycle(spec, server_now - 10),
        "status": "incomplete",
        "completed_utc": server_now - 5,
        "server_terminal_utc": server_now - 5,
        "manifest": manifest,
        "manifest_id": poller.content_id(manifest, prefix="cycle_manifest_"),
    }

    assert poller._preflight_x_cycle_is_known(spec, cycle) is True
    assert poller._preflight_x_cycle_is_known(
        spec, {**cycle, "manifest_id": "cycle_manifest_" + "0" * 24}
    ) is False
    assert poller._preflight_x_cycle_is_known(
        spec, {**cycle, "identity_valid": False}
    ) is False


@pytest.mark.unit
def test_required_preflight_fails_when_sanitized_alert_probe_is_not_delivered(
    monkeypatch, capsys,
):
    secret_db = "postgresql+psycopg://collector:secret@db.internal/evidence"
    calls = []

    class Store:
        def server_observed_utc(self):
            return 1_786_080_000.0

        def collector_runtime_preflight(self, *, direct_url=None):
            assert direct_url is None
            calls.append("preflight")
            return {"contract_version": 3, "ready": True}

        def collection_cycle_identities(self, cycle_kind, *, period_key):
            assert cycle_kind == "x-daily"
            assert period_key
            calls.append("identities")
            return []

        def close(self):
            calls.append("close")

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_AUTO_MIGRATE", "false")
    monkeypatch.setenv("MEDIA_REQUIRE_ALERT_WEBHOOK", "true")
    monkeypatch.setenv(
        "TRADINGAGENTS_ALERT_WEBHOOK_URL",
        "https://hooks.example.invalid/private-token",
    )
    monkeypatch.setenv("X_BEARER_TOKEN", "x-secret-token")
    monkeypatch.delenv("MEDIA_DB_DIRECT_URL", raising=False)
    monkeypatch.setattr(
        poller,
        "collector_semantics_manifest",
        lambda: {
            "collector_semantics_id": poller.GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID
        },
    )
    monkeypatch.setattr(poller, "build_identity", lambda: "build_" + "b" * 24)
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: calls.append("open") or Store(),
    )
    monkeypatch.setattr(
        poller,
        "probe_alert_webhook",
        lambda: calls.append("probe") or False,
    )
    for provider_name in (
        "fetch_global_news", "fetch_x_topic", "fetch_x_trends",
    ):
        monkeypatch.setattr(
            poller,
            provider_name,
            lambda *_args, **_kwargs: pytest.fail("preflight called a provider"),
        )

    with pytest.raises(SystemExit):
        poller.main([
            "--global-only",
            "--preflight",
            "--sources", "x",
            "--no-trading-hours",
            "--interval", "3600",
            "--x-interval", "86400",
            "--health-port", "5500",
            "--db", secret_db,
        ])

    captured = capsys.readouterr()
    assert calls == ["open", "preflight", "identities", "probe", "close"]
    assert captured.out == ""
    assert "collector preflight failed (RuntimeError)" in captured.err
    assert secret_db not in captured.err
    assert "secret" not in captured.err


@pytest.mark.unit
def test_preflight_rejects_accepted_pair_with_wrong_frozen_shape_before_probe(
    monkeypatch, capsys,
):
    calls = []
    server_now = 1_786_080_000.0
    accepted = poller.GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES[0]
    wrong_shape = poller.media_store.collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=poller._x_collection_cycle_spec(server_now, 3)["identity"][
            "period_key"
        ],
        protocol_id=accepted["protocol_id"],
        collector_semantics_id=accepted["collector_semantics_id"],
        expected_static_slots=[("xtrend", "woeid:1")],
        max_dynamic_slots=3,
    )

    class Store:
        def server_observed_utc(self):
            return server_now

        def collector_runtime_preflight(self, *, direct_url=None):
            assert direct_url is None
            calls.append("preflight")
            return {"contract_version": 3, "ready": True}

        def collection_cycle_identities(self, cycle_kind, *, period_key):
            assert cycle_kind == "x-daily"
            assert period_key
            calls.append("identities")
            return [{
                "collection_cycle_id": wrong_shape["collection_cycle_id"],
                "protocol_id": accepted["protocol_id"],
                "collector_semantics_id": accepted["collector_semantics_id"],
            }]

        def close(self):
            calls.append("close")

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_AUTO_MIGRATE", "false")
    monkeypatch.setenv("MEDIA_REQUIRE_ALERT_WEBHOOK", "false")
    monkeypatch.setenv("X_BEARER_TOKEN", "x-secret-token")
    monkeypatch.delenv("MEDIA_DB_DIRECT_URL", raising=False)
    monkeypatch.setattr(
        poller,
        "collector_semantics_manifest",
        lambda: {
            "collector_semantics_id": poller.GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID
        },
    )
    monkeypatch.setattr(
        poller, "open_store", lambda *_args, **_kwargs: calls.append("open") or Store()
    )
    monkeypatch.setattr(
        poller,
        "probe_alert_webhook",
        lambda: pytest.fail(
            "incompatible current identity reached alert probing"
        ),
    )

    with pytest.raises(SystemExit):
        poller.main([
            "--global-only", "--preflight", "--sources", "x",
            "--no-trading-hours", "--interval", "3600",
            "--x-interval", "86400", "--health-port", "5500",
            "--db", "postgresql+psycopg://collector:secret@db/evidence",
        ])

    captured = capsys.readouterr()
    assert calls == ["open", "preflight", "identities", "close"]
    assert captured.out == ""
    assert "collector preflight failed (RuntimeError)" in captured.err
    assert "protocol_" not in captured.err
    assert "collector_" not in captured.err.replace("collector preflight", "")


@pytest.mark.unit
def test_preflight_failure_never_renders_database_exception_text(monkeypatch, capsys):
    secret_db = "postgresql+psycopg://collector:secret@db.internal/evidence"
    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_AUTO_MIGRATE", "false")
    monkeypatch.setenv("X_BEARER_TOKEN", "x-secret-token")
    monkeypatch.setattr(
        poller,
        "collector_semantics_manifest",
        lambda: {
            "collector_semantics_id": poller.GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID
        },
    )
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError(f"could not connect to {secret_db}")
        ),
    )

    with pytest.raises(SystemExit):
        poller.main([
            "--global-only", "--preflight", "--sources", "x",
            "--no-trading-hours", "--interval", "3600",
            "--x-interval", "86400", "--health-port", "5500",
            "--db", secret_db,
        ])

    error = capsys.readouterr().err
    assert "collector preflight failed (RuntimeError)" in error
    assert secret_db not in error
    assert "secret" not in error


@pytest.mark.unit
def test_runtime_retry_backoff_is_exponential_and_capped():
    assert [poller._collector_retry_delay(attempt) for attempt in range(1, 10)] == [
        5.0,
        10.0,
        20.0,
        40.0,
        80.0,
        160.0,
        300.0,
        300.0,
        300.0,
    ]
    assert poller._collector_retry_delay(1_000_000) == 300.0
    for invalid in (True, 0, -1, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            poller._collector_retry_delay(invalid)


@pytest.mark.unit
def test_incomplete_terminal_cycle_reports_runtime_recovery(monkeypatch):
    stop = {"flag": False}
    observed = {"health": [], "recoveries": 0}
    incomplete = {
        "complete": False,
        "missing_query_slots": [{"provider": "globalnews", "query_key": "slot"}],
        "query_slots": [],
    }

    class Health:
        def mark_cycle(self, coverage, *, completed_utc):
            assert completed_utc > 0
            observed["health"].append(coverage)

    def incomplete_cycle(*_args, **_kwargs):
        stop["flag"] = True
        return incomplete

    def mark_recovery():
        observed["recoveries"] += 1

    monkeypatch.setattr(poller, "run_cycle", incomplete_cycle)

    poller.poll_forever(
        object(), [], [], 3600, {},
        health_state=Health(),
        stop=stop,
        on_cycle_terminal=mark_recovery,
    )

    assert observed == {"health": [incomplete], "recoveries": 1}


@pytest.mark.unit
def test_runtime_incident_retries_and_reminds_with_stable_occurrence_keys():
    now = {"value": 100.0}
    alerts = []
    deliveries = iter([False, True, False, True, True, True, True])

    def capture(component, event, **kwargs):
        alerts.append((component, event, kwargs))
        return next(deliveries)

    incident = poller._CollectorRuntimeIncident(
        clock=lambda: now["value"],
        alert=capture,
    )

    assert incident.mark_failure(
        stage="store_startup", error_type="OperationalError",
        retry_delay_seconds=5.0,
    ) is True
    now["value"] += 1
    assert incident.mark_failure(
        stage="store_startup", error_type="OperationalError",
        retry_delay_seconds=10.0,
    ) is False
    now["value"] += 1
    assert incident.mark_failure(
        stage="lease_acquisition", error_type="OperationalError",
        retry_delay_seconds=20.0,
    ) is False
    now["value"] += poller._RUNTIME_ALERT_MIN_INTERVAL_SECONDS - 1
    assert incident.mark_failure(
        stage="lease_acquisition", error_type="OperationalError",
        retry_delay_seconds=40.0,
    ) is True
    now["value"] += poller._RUNTIME_ALERT_REMINDER_SECONDS
    assert incident.mark_failure(
        stage="lease_acquisition", error_type="OperationalError",
        retry_delay_seconds=80.0,
    ) is True
    now["value"] += 1
    assert incident.mark_failure(
        stage="cycle", error_type="RuntimeError", retry_delay_seconds=160.0,
    ) is False
    now["value"] += poller._RUNTIME_ALERT_MIN_INTERVAL_SECONDS - 1
    assert incident.mark_failure(
        stage="cycle", error_type="RuntimeError", retry_delay_seconds=300.0,
    ) is True
    now["value"] += poller._RUNTIME_ALERT_REMINDER_SECONDS
    assert incident.mark_failure(
        stage="cycle", error_type="RuntimeError", retry_delay_seconds=300.0,
    ) is True
    assert incident.active is True

    incident.mark_recovered()
    assert incident.active is False
    now["value"] += 1
    assert incident.mark_failure(
        stage="cycle", error_type="RuntimeError", retry_delay_seconds=5.0,
    ) is True

    assert [event for _, event, _ in alerts] == [
        "runtime_unhealthy",
        "runtime_unhealthy",
        "runtime_unhealthy",
        "runtime_unhealthy",
        "runtime_unhealthy",
        "runtime_recovered",
        "runtime_unhealthy",
    ]
    unhealthy = [kwargs["details"] for _, event, kwargs in alerts
                 if event == "runtime_unhealthy"]
    assert [details["reminder"] for details in unhealthy] == [
        False, False, True, True, True, False,
    ]
    keys = [kwargs["dedupe_key"] for _, _, kwargs in alerts]
    assert keys[0] == keys[1]
    assert keys[2] == keys[3]
    assert len({keys[0], keys[2], keys[4], keys[5], keys[6]}) == 5
    assert unhealthy[1]["failure_stage"] == "lease_acquisition"
    assert unhealthy[-1]["failure_stage"] == "cycle"


@pytest.mark.unit
def test_runtime_recovery_retries_until_ack_with_latest_failure_state():
    alerts = []
    recovery_outcomes = iter([False, RuntimeError("receiver bug"), True])

    def capture(component, event, **kwargs):
        alerts.append((component, event, kwargs))
        if event == "runtime_unhealthy":
            return True
        outcome = next(recovery_outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    incident = poller._CollectorRuntimeIncident(clock=lambda: 100.0, alert=capture)
    assert incident.mark_failure(
        stage="store_startup", error_type="OperationalError",
        retry_delay_seconds=5.0,
    ) is True
    assert incident.mark_failure(
        stage="lease_lost", error_type="CollectorLeaseLost",
        retry_delay_seconds=10.0,
    ) is False

    incident.mark_recovered()
    assert incident.active is False
    incident.mark_recovered()
    assert incident.active is False
    incident.mark_recovered()
    assert incident.active is False

    incident_key = alerts[0][2]["dedupe_key"]
    recoveries = [kwargs for _, event, kwargs in alerts if event == "runtime_recovered"]
    assert len(recoveries) == 3
    assert len({item["dedupe_key"] for item in recoveries}) == 1
    assert recoveries[0]["dedupe_key"] != incident_key
    assert recoveries[-1]["details"] == {
        "schema_version": 1,
        "prior_failure_stage": "lease_lost",
        "prior_failure_type": "CollectorLeaseLost",
    }


@pytest.mark.unit
def test_new_runtime_failure_supersedes_an_unacknowledged_recovery():
    alerts = []

    def capture(component, event, **kwargs):
        alerts.append((component, event, kwargs))
        return event == "runtime_unhealthy"

    incident = poller._CollectorRuntimeIncident(clock=lambda: 100.0, alert=capture)
    incident.mark_failure(
        stage="store_startup",
        error_type="OperationalError",
        retry_delay_seconds=5.0,
    )
    incident.mark_recovered()
    assert incident.active is False

    incident.mark_failure(
        stage="cycle",
        error_type="RuntimeError",
        retry_delay_seconds=5.0,
    )

    assert [event for _, event, _ in alerts] == [
        "runtime_unhealthy",
        "runtime_recovered",
        "runtime_unhealthy",
    ]
    assert alerts[0][2]["dedupe_key"] != alerts[2][2]["dedupe_key"]


@pytest.mark.unit
def test_runtime_recovery_is_silent_when_incident_was_never_delivered():
    alerts = []

    def reject(component, event, **kwargs):
        alerts.append((component, event, kwargs))
        return False

    incident = poller._CollectorRuntimeIncident(
        clock=lambda: 100.0,
        alert=reject,
    )

    assert incident.mark_failure(
        stage="cycle", error_type="RuntimeError", retry_delay_seconds=5.0,
    ) is True
    incident.mark_recovered()

    assert incident.active is False
    assert [event for _, event, _ in alerts] == ["runtime_unhealthy"]


@pytest.mark.unit
def test_daemon_startup_failures_stay_in_process_unhealthy_and_deduped(
    monkeypatch, caplog,
):
    secret = "postgresql://collector:private-password@db.internal/evidence"
    observed = {
        "attempts": 0,
        "alerts": [],
        "delays": [],
        "health_state": None,
        "health_closed": 0,
    }
    handlers = {}

    class HealthServer:
        def close(self):
            observed["health_closed"] += 1

    def start_health(state, *, port):
        assert port == 5500
        observed["health_state"] = state
        return HealthServer()

    def fail_store(_url):
        observed["attempts"] += 1
        raise RuntimeError(secret)

    def fake_sleep(seconds, stop, **_kwargs):
        observed["delays"].append(seconds)
        if len(observed["delays"]) == 4:
            handlers[poller.signal.SIGTERM](poller.signal.SIGTERM, None)

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setenv("GIT_REVISION", "a" * 40)
    monkeypatch.setenv("FLY_MACHINE_ID", "machine-123")
    monkeypatch.setenv("COLLECTOR_DEPLOYMENT_NONCE", "1" * 32)
    monkeypatch.setattr(poller, "open_store", fail_store)
    monkeypatch.setattr(poller, "start_collector_health_server", start_health)
    monkeypatch.setattr(poller, "_sleep", fake_sleep)
    monkeypatch.setattr(
        poller.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: observed["alerts"].append(
            (component, event, kwargs)
        ) or True,
    )

    with caplog.at_level(logging.INFO):
        poller.main([
            "--global-only",
            "--sources", "x",
            "--no-trading-hours",
            "--interval", "3600",
            "--x-interval", "86400",
            "--health-port", "5500",
            "--db", secret,
        ])

    assert observed["attempts"] == 4
    assert observed["delays"] == [5.0, 10.0, 20.0, 40.0]
    assert observed["health_closed"] == 1
    assert [event for _, event, _ in observed["alerts"]] == [
        "runtime_unhealthy"
    ]
    state = observed["health_state"]
    assert state is not None
    status, payload = state.snapshot(monotonic_now=100.0)
    assert status == 503
    assert payload["reason"] == "cycle_failed"
    assert payload["failure_type"] == "RuntimeError"
    assert payload["build_revision"] == "a" * 40
    assert payload["machine_id"] == "machine-123"
    assert payload["deployment_nonce"] == "1" * 32
    rendered = caplog.text + json.dumps(observed["alerts"])
    assert secret not in rendered
    assert "private-password" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.unit
def test_daemon_recovers_runtime_incident_after_incomplete_terminal_cycle(
    monkeypatch,
):
    observed = {
        "attempts": 0,
        "closed": 0,
        "cycles": 0,
        "alerts": [],
        "delays": [],
    }
    handlers = {}

    class Store:
        dialect = "sqlite"

        def close(self):
            observed["closed"] += 1

    def open_after_invalid_runtime_value(_url):
        observed["attempts"] += 1
        if observed["attempts"] == 1:
            raise ValueError("rotated runtime topology is temporarily invalid")
        return Store()

    def incomplete_cycle(*_args, **_kwargs):
        observed["cycles"] += 1
        handlers[poller.signal.SIGTERM](poller.signal.SIGTERM, None)
        return {
            "complete": False,
            "missing_query_slots": [
                {"provider": "globalnews", "query_key": "missing-slot"}
            ],
            "query_slots": [],
        }

    def fake_sleep(seconds, stop, **_kwargs):
        if not stop["flag"]:
            observed["delays"].append(seconds)

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setattr(poller, "open_store", open_after_invalid_runtime_value)
    monkeypatch.setattr(poller, "run_cycle", incomplete_cycle)
    monkeypatch.setattr(poller, "_sleep", fake_sleep)
    monkeypatch.setattr(
        poller.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: observed["alerts"].append(
            (component, event, kwargs)
        ) or True,
    )

    poller.main([
        "--global-only",
        "--sources", "x",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
        "--db", "postgresql+psycopg://collector:secret@pool/evidence",
    ])

    assert observed["attempts"] == 2
    assert observed["closed"] == 1
    assert observed["cycles"] == 1
    assert observed["delays"] == [5.0]
    assert [event for _, event, _ in observed["alerts"]] == [
        "runtime_unhealthy",
        "runtime_recovered",
    ]
    assert observed["alerts"][0][2]["details"] == {
        "schema_version": 1,
        "failure_stage": "store_startup",
        "failure_type": "ValueError",
        "retry_delay_seconds": 5.0,
        "reminder": False,
    }


@pytest.mark.unit
def test_supervisor_tears_down_failed_cycle_and_alerts_recovery(monkeypatch, caplog):
    secret = "postgresql://collector:cycle-secret@db.internal/evidence"
    observed = {
        "stores": 0,
        "closed": 0,
        "cycles": 0,
        "heartbeats": 0,
        "alerts": [],
        "delays": [],
    }
    handlers = {}

    class Store:
        dialect = "sqlite"

        def __init__(self):
            observed["stores"] += 1

        def set_meta(self, key, _value):
            assert key == "poller:last_failure_utc"
            observed["heartbeats"] += 1

        def close(self):
            observed["closed"] += 1

    def cycle(*_args, **_kwargs):
        observed["cycles"] += 1
        if observed["cycles"] < 3:
            raise RuntimeError(secret)
        handlers[poller.signal.SIGTERM](poller.signal.SIGTERM, None)
        return {"complete": True, "missing_query_slots": [], "query_slots": []}

    def fake_sleep(seconds, stop, **_kwargs):
        if not stop["flag"]:
            observed["delays"].append(seconds)

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setattr(poller, "open_store", lambda _url: Store())
    monkeypatch.setattr(poller, "run_cycle", cycle)
    monkeypatch.setattr(poller, "_sleep", fake_sleep)
    monkeypatch.setattr(
        poller.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: observed["alerts"].append(
            (component, event, kwargs)
        ) or True,
    )

    with caplog.at_level(logging.INFO):
        poller.main([
            "--global-only",
            "--sources", "x",
            "--no-trading-hours",
            "--interval", "3600",
            "--x-interval", "86400",
            "--db", secret,
        ])

    assert observed["stores"] == observed["closed"] == 3
    assert observed["cycles"] == 3
    assert observed["heartbeats"] == 2
    assert observed["delays"] == [5.0, 10.0]
    assert [event for _, event, _ in observed["alerts"]] == [
        "runtime_unhealthy",
        "runtime_recovered",
    ]
    rendered = caplog.text + json.dumps(observed["alerts"])
    assert secret not in rendered
    assert "cycle-secret" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.unit
def test_one_shot_failure_remains_fail_fast(monkeypatch):
    secret = "postgresql://collector:one-shot-secret@db.internal/evidence"
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda _url: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(
        poller,
        "_run_supervised_daemon",
        lambda **_kwargs: pytest.fail("one-shot entered daemon supervision"),
    )

    with pytest.raises(RuntimeError, match="one-shot-secret"):
        poller.main([
            "--global-only",
            "--once",
            "--sources", "x",
            "--no-trading-hours",
            "--interval", "3600",
            "--x-interval", "86400",
            "--db", secret,
        ])


@pytest.mark.unit
def test_one_shot_singleton_lease_uses_exit_status_instead_of_alerting(monkeypatch):
    observed = {"cycles": 0, "lease_closed": 0, "store_closed": 0}

    class Lease:
        is_held = True

        def close(self):
            observed["lease_closed"] += 1

    class Store:
        dialect = "postgresql"

        def acquire_collector_lease(self, *, direct_url=None, on_loss=None):
            assert direct_url is None
            assert on_loss is None
            return Lease()

        def close(self):
            observed["store_closed"] += 1

    def run_cycle(*_args, **_kwargs):
        observed["cycles"] += 1
        return {"complete": True, "missing_query_slots": [], "query_slots": []}

    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.delenv("MEDIA_DB_DIRECT_URL", raising=False)
    monkeypatch.setattr(poller, "open_store", lambda _url: Store())
    monkeypatch.setattr(poller, "run_cycle", run_cycle)
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *_args, **_kwargs: pytest.fail("one-shot lease sent an alert"),
    )

    poller.main([
        "--global-only",
        "--once",
        "--sources", "x",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
    ])

    assert observed == {"cycles": 1, "lease_closed": 1, "store_closed": 1}


@pytest.mark.unit
def test_executable_boundary_exits_without_traceback_or_secret(monkeypatch, caplog):
    secret = "postgresql://collector:entrypoint-secret@db.internal/evidence"
    monkeypatch.setattr(
        poller,
        "main",
        lambda: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as stopped:
        poller._main_entrypoint()

    assert stopped.value.code == 1
    assert "Collector exited (RuntimeError)" in caplog.text
    assert secret not in caplog.text
    assert "entrypoint-secret" not in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.unit
def test_executable_boundary_does_not_swallow_parser_exit(monkeypatch, caplog):
    monkeypatch.setattr(
        poller,
        "main",
        lambda: (_ for _ in ()).throw(SystemExit(2)),
    )

    with pytest.raises(SystemExit) as stopped:
        poller._main_entrypoint()

    assert stopped.value.code == 2
    assert "Collector exited" not in caplog.text


@pytest.mark.unit
def test_duplicate_daemon_retries_without_fetching_until_lease_is_held(monkeypatch):
    expected_direct = "postgresql+psycopg://collector:secret@direct.db/evidence"
    observed = {
        "attempts": 0,
        "closed": 0,
        "lease_closed": 0,
        "fetches": 0,
        "alerts": [],
        "delays": [],
    }
    handlers = {}

    class Lease:
        is_held = True

        def assert_held(self):
            assert self.is_held

        def close(self):
            observed["lease_closed"] += 1

    class Store:
        dialect = "postgresql"

        def __init__(self):
            observed["attempts"] += 1
            self.attempt = observed["attempts"]

        def acquire_collector_lease(self, *, direct_url=None, on_loss=None):
            assert direct_url == expected_direct
            assert callable(on_loss)
            return Lease() if self.attempt == 3 else None

        def close(self):
            observed["closed"] += 1

    def run_once_with_lease(store, *_args, **_kwargs):
        observed["fetches"] += 1
        assert store.attempt == 3
        assert isinstance(store._collector_lease_guard, Lease)
        handlers[poller.signal.SIGTERM](poller.signal.SIGTERM, None)
        return {"complete": True, "missing_query_slots": [], "query_slots": []}

    def fake_sleep(seconds, stop, **_kwargs):
        if not stop["flag"]:
            observed["delays"].append(seconds)

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_DB_DIRECT_URL", expected_direct)
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setattr(poller, "open_store", lambda *_args, **_kwargs: Store())
    monkeypatch.setattr(poller, "run_cycle", run_once_with_lease)
    monkeypatch.setattr(poller, "_sleep", fake_sleep)
    monkeypatch.setattr(
        poller.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: observed["alerts"].append(
            (component, event, kwargs)
        ) or True,
    )

    poller.main([
        "--global-only",
        "--sources", "x",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
        "--db", "postgresql+psycopg://collector:secret@pool/evidence",
    ])

    assert observed["attempts"] == 3
    assert observed["closed"] == 3
    assert observed["lease_closed"] == 1
    assert observed["fetches"] == 1
    assert observed["delays"] == [5.0, 10.0]
    assert [event for _, event, _ in observed["alerts"]] == [
        "runtime_unhealthy",
        "runtime_recovered",
    ]


@pytest.mark.unit
def test_lost_lease_is_torn_down_and_reacquired_before_next_fetch(
    monkeypatch, caplog,
):
    secret = "postgresql://collector:lease-secret@direct.db/evidence"
    expected_direct = (
        "postgresql+psycopg://collector:secret@direct.db/evidence"
    )
    observed = {
        "stores": 0,
        "closed": 0,
        "lease_closed": 0,
        "fetches": 0,
        "alerts": [],
        "delays": [],
    }
    handlers = {}

    class Lease:
        def __init__(self, *, lose_on_first_guard):
            self.is_held = True
            self.lose_on_first_guard = lose_on_first_guard

        def assert_held(self):
            if self.lose_on_first_guard:
                self.lose_on_first_guard = False
                self.is_held = False
                raise RuntimeError(secret)
            assert self.is_held

        def close(self):
            observed["lease_closed"] += 1

    class Store:
        dialect = "postgresql"

        def __init__(self):
            observed["stores"] += 1
            self.attempt = observed["stores"]

        def acquire_collector_lease(self, *, direct_url=None, on_loss=None):
            assert direct_url == expected_direct
            assert callable(on_loss)
            return Lease(lose_on_first_guard=self.attempt == 1)

        def set_meta(self, *_args, **_kwargs):
            pytest.fail("a lost lease must not write a failure heartbeat")

        def close(self):
            observed["closed"] += 1

    def run_only_after_reacquisition(store, *_args, **_kwargs):
        observed["fetches"] += 1
        assert store.attempt == 2
        assert store._collector_lease_guard.is_held
        handlers[poller.signal.SIGTERM](poller.signal.SIGTERM, None)
        return {"complete": True, "missing_query_slots": [], "query_slots": []}

    def fake_sleep(seconds, stop, **_kwargs):
        if not stop["flag"]:
            observed["delays"].append(seconds)

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_DB_DIRECT_URL", expected_direct)
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setattr(poller, "open_store", lambda *_args, **_kwargs: Store())
    monkeypatch.setattr(poller, "run_cycle", run_only_after_reacquisition)
    monkeypatch.setattr(poller, "_sleep", fake_sleep)
    monkeypatch.setattr(
        poller.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: observed["alerts"].append(
            (component, event, kwargs)
        ) or True,
    )

    with caplog.at_level(logging.INFO):
        poller.main([
            "--global-only",
            "--sources", "x",
            "--no-trading-hours",
            "--interval", "3600",
            "--x-interval", "86400",
            "--db", "postgresql+psycopg://collector:secret@pool/evidence",
        ])

    assert observed["stores"] == observed["closed"] == 2
    assert observed["lease_closed"] == 2
    assert observed["fetches"] == 1
    assert observed["delays"] == [5.0]
    assert [event for _, event, _ in observed["alerts"]] == [
        "runtime_unhealthy",
        "runtime_recovered",
    ]
    assert (
        observed["alerts"][0][2]["details"]["failure_stage"] == "lease_lost"
    )
    assert (
        observed["alerts"][0][2]["details"]["failure_type"]
        == "CollectorLeaseLost"
    )
    rendered = caplog.text + json.dumps(observed["alerts"])
    assert secret not in rendered
    assert "lease-secret" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.unit
@pytest.mark.parametrize(
    ("configured_url", "expected"),
    [
        (None, "local SQLite (default)"),
        ("/tmp/media.db", "configured local database"),
        (
            "postgresql+psycopg://collector:super-secret@db.example/media?sslmode=require",
            "configured PostgreSQL database",
        ),
        ("sqlite:////tmp/media.db", "configured SQLite database"),
        ("mysql://collector:super-secret@db.example/media", "configured database"),
    ],
)
def test_store_log_label_never_renders_connection_details(configured_url, expected):
    label = poller._store_log_label(configured_url)
    assert label == expected
    assert "super-secret" not in label
    assert "db.example" not in label
