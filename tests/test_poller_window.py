"""Independent fetch receipts retain late discoveries without shared-cursor gaps."""
import json
import logging

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
def test_within_retains_late_discovered_older_items():
    rows = [
        _row("x", "fresh", "NVDA", 0.0, created_utc=100.0),
        _row("x", "stale", "NVDA", 0.0, created_utc=10.0),
        _row("x", "undated", "NVDA", 0.0, created_utc=None),
    ]
    kept = {r["external_id"] for r in poller._within(rows, since=50.0)}
    assert kept == {"fresh", "stale", "undated"}
    assert len(poller._within(rows, since=None)) == 3


@pytest.mark.unit
def test_poll_once_stores_older_items_first_discovered_now(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")

    def fake_source(ticker, now):
        return [_row("x", "a", ticker, now, created_utc=9995.0),   # in window
                _row("x", "b", ticker, now, created_utc=9000.0)]   # too old

    monkeypatch.setattr(poller, "FETCHERS", {"x": fake_source})
    poller.poll_once(store, ["NVDA"], ["x"], now=10000.0, since=9990.0)

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
def test_coverage_alerts_on_transition_change_reminder_and_recovery(
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
        "query_slot_coverage_incomplete",
        "query_slot_coverage_recovered",
    ]
    assert [kwargs["severity"] for _, _, kwargs in alerts] == [
        "warning", "warning", "warning", "info"
    ]
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
    assert store.get_meta(poller._COVERAGE_ALERT_LAST_UTC_KEY) == 200.0
    store.close()


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
    assert store.get_meta(poller._COVERAGE_ALERT_FINGERPRINT_KEY) == 0.0
    store.close()


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

    poller.print_audit(AuditStore())

    output = capsys.readouterr().out
    assert captured["cutoff"] == database_now
    assert captured["kwargs"]["expected_query_slots"] == expected
    assert captured["kwargs"]["max_age_seconds"] == 4500.0
    assert "collector_expected_query_slots=10" in output
    assert "collector_missing_query_slots=10" in output
    assert "collector_x_current_state=missing" in output
    assert "collector_x_prior_state=missing" in output
    assert "collector_immutable_receipt_history" not in output


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


def _compatible_x_cycle_spec(instant):
    identity = poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"][
        "compatible_collector_identities"
    ][0]
    return poller._x_collection_cycle_spec_for_identity(
        instant,
        3,
        protocol_id=identity["protocol_id"],
        collector_semantics_id=identity["collector_semantics_id"],
    )


def _finish_compatible_x_cycle(store, instant, *, with_receipts):
    spec = _compatible_x_cycle_spec(instant)
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

    assert poller._x_poll_due(store, instant, 86400) is False
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
        lambda: pytest.fail("an incomplete prior attempt must block a fresh paid cycle"),
    )

    assert poller._x_poll_due(store, instant, 86400) is False
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
        lambda: pytest.fail("an invalid prior attempt must block paid work"),
    )
    store = Store()

    assert poller._x_poll_due(store, instant, 86400) is False
    assert poller._x_daily_requirement_state(store, instant, 3) == "invalid"
    with pytest.raises(ValueError, match="not uniquely complete"):
        poller.poll_x_topics_once(store, instant, 10, 3)


@pytest.mark.unit
def test_unlisted_x_cycle_is_not_considered_daily_completion():
    instant = 1_786_080_000.0
    unlisted = poller._x_collection_cycle_spec_for_identity(
        instant,
        3,
        protocol_id="protocol_" + "d" * 24,
        collector_semantics_id="collector_" + "e" * 24,
    )
    queried = []

    class Store:
        def collection_cycle(self, cycle_id):
            queried.append(cycle_id)
            if cycle_id == unlisted["collection_cycle_id"]:
                return {"status": "complete"}
            return None

    store = Store()

    assert poller._x_daily_requirement_state(store, instant, 3) == "missing"
    assert poller._x_poll_due(store, instant, 86400) is True
    assert unlisted["collection_cycle_id"] not in queried


@pytest.mark.unit
def test_running_x_cycle_age_uses_database_clock(monkeypatch):
    instant = 1_786_080_000.0
    spec = poller._x_collection_cycle_spec(instant, 3)
    expected_slots = spec["identity"]["expected_static_slots"]

    class Store:
        def collection_cycle(self, cycle_id):
            assert cycle_id == spec["collection_cycle_id"]
            return {
                "identity_valid": True,
                "identity": spec["identity"],
                "status": "running",
                "server_started_utc": instant - 1.0,
            }

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

    class Store:
        def collection_cycle(self, cycle_id):
            assert cycle_id == spec["collection_cycle_id"]
            static_slots = spec["identity"]["expected_static_slots"]
            dynamic_slots = [
                {"provider": "x", "query_key": "global topic one"},
                {"provider": "x", "query_key": "global topic two"},
            ]
            return {
                "identity_valid": True,
                "identity": spec["identity"],
                "status": "complete",
                "manifest_valid": True,
                "server_terminal_utc": terminal,
                "manifest": {
                    "collection_cycle_id": spec["collection_cycle_id"],
                    "cycle_kind": spec["identity"]["cycle_kind"],
                    "period_key": spec["identity"]["period_key"],
                    "protocol_id": spec["identity"]["protocol_id"],
                    "collector_semantics_id": spec["identity"][
                        "collector_semantics_id"
                    ],
                    "status": "complete",
                    "expected_static_slots": static_slots,
                    "expected_dynamic_slots": dynamic_slots,
                    "slot_receipts": [
                        {
                            "provider": "xtrend",
                            "query_key": "woeid:1",
                            "fetch_run_id": "fetch_" + "1" * 24,
                            "status": "success",
                            "item_count": 4,
                        },
                        {
                            "provider": "xtrend",
                            "query_key": "woeid:23424977",
                            "fetch_run_id": "fetch_" + "2" * 24,
                            "status": "success",
                            "item_count": 5,
                        },
                        {
                            "provider": "trendnews",
                            "query_key": "ranked-global-discovery",
                            "fetch_run_id": None,
                            "status": "empty",
                            "item_count": 0,
                        },
                        {
                            "provider": "x",
                            "query_key": "global topic one",
                            "fetch_run_id": "fetch_" + "3" * 24,
                            "status": "success",
                            "item_count": 10,
                        },
                        {
                            "provider": "x",
                            "query_key": "global topic two",
                            "fetch_run_id": "fetch_" + "4" * 24,
                            "status": "success",
                            "item_count": 7,
                        },
                    ]
                },
            }

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
def test_global_only_policy_is_content_addressed_and_excludes_retired_runtime_parts():
    manifest = poller.collector_semantics_manifest()

    assert manifest["schema_version"] == 4
    assert manifest["policy"] == "global-only-editorial-and-trend-reaction-v2"
    assert manifest["collector_semantics_id"] == "collector_8ec4d89bc22ca934e079d6ce"
    assert manifest["semantic_values"]["collection_scope"] == {
        "ticker_watchlist": False,
        "ticker_sources": [],
        "polymarket": False,
        "broad_editorial_news": True,
        "trend_derived_x_reaction": True,
        "news_interval_seconds": 3600,
        "x_interval_seconds": 86400,
    }
    assert not any("release" in name or "paper" in name for name in manifest["components"])


@pytest.mark.unit
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

    class Store:
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
            "collector_semantics_id": poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                "expected_collector_semantics_id"
            ]
        },
    )
    monkeypatch.setattr(poller, "build_identity", lambda: "build_" + "a" * 24)
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
    assert payload["status"] == "ok"
    assert payload["database_contract"]["ready"] is True
    assert payload["alert_webhook_required"] is True
    assert calls == ["open", "preflight", "close"]
    rendered = json.dumps(payload)
    assert secret_db not in rendered
    assert secret_direct_db not in rendered
    assert secret_webhook not in rendered
    assert "x-secret-token" not in rendered


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
            "collector_semantics_id": poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"][
                "expected_collector_semantics_id"
            ]
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
def test_duplicate_daemon_stays_passive_without_restart_alert_storm(monkeypatch):
    expected_direct = "postgresql+psycopg://collector:secret@direct.db/evidence"
    observed = {"waited": 0, "closed": 0, "alerts": []}

    class Store:
        dialect = "postgresql"

        def acquire_collector_lease(self, *, direct_url=None, on_loss=None):
            assert direct_url == expected_direct
            assert callable(on_loss)
            return None

        def close(self):
            observed["closed"] += 1

    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("MEDIA_DB_DIRECT_URL", expected_direct)
    monkeypatch.setenv("X_BEARER_TOKEN", "configured")
    monkeypatch.setattr(poller, "open_store", lambda *_args, **_kwargs: Store())
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: observed["alerts"].append(
            (component, event, kwargs)
        ) or True,
    )
    monkeypatch.setattr(
        poller,
        "_wait_as_duplicate_worker",
        lambda: observed.__setitem__("waited", observed["waited"] + 1),
    )

    poller.main([
        "--global-only",
        "--sources", "x",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
        "--db", "postgresql+psycopg://collector:secret@pool/evidence",
    ])

    assert observed["waited"] == 1
    assert observed["closed"] == 1
    assert [event for _, event, _ in observed["alerts"]] == [
        "duplicate_worker_blocked"
    ]


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
