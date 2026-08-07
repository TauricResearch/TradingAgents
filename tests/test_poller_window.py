"""Independent fetch receipts retain late discoveries without shared-cursor gaps."""
import json
import logging

import pytest

from tradingagents import poller
from tradingagents.dataflows.media_sources import _row
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
def test_globalnews_exception_retries_have_independent_receipts_then_succeed(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "globalnews-retry.db")
    attempts = []
    sleeps = []

    def fetch_news(query, captured, theme, *, limit):
        attempts.append((query, theme, limit))
        if len(attempts) < 3:
            raise OSError("provider credential=must-not-persist")
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
        raise TimeoutError("secret response")

    monkeypatch.setattr(poller, "fetch_global_news", unavailable)
    with pytest.raises(TimeoutError, match="secret response"):
        poller._run_globalnews_query(
            store, "world", "global policy", sleep_fn=sleeps.append
        )

    assert len(calls) == 3
    assert sleeps == [1.0, 4.0]
    receipts = store.fetch_runs(provider="globalnews")
    assert len(receipts) == 3
    assert {receipt["status"] for receipt in receipts} == {"failed"}
    assert {receipt["error"] for receipt in receipts} == {"TimeoutError"}
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
            raise RuntimeError(f"request failed for {secret_url}")
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
    assert runs[f"global:{sensitive_query}"]["error"] == "RuntimeError"
    assert store.get_meta("poller:last_failure_utc") is not None
    assert store.get_meta("poller:last_success_utc") is None

    assert len(alerts) == 1
    component, event, kwargs = alerts[0]
    assert (component, event) == ("collector", "query_slot_coverage_incomplete")
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

    captured = {}

    class AuditStore:
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
            return []

        def collection_cycle(self, _cycle_id):
            return None

    poller.print_audit(AuditStore())

    output = capsys.readouterr().out
    assert captured["kwargs"]["expected_query_slots"] == expected
    assert "collector_expected_query_slots=10" in output
    assert "collector_missing_query_slots=10" in output
    assert "collector_x_current_state=missing" in output
    assert "collector_x_prior_state=missing" in output


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
            return {
                "identity_valid": True,
                "identity": spec["identity"],
                "status": "complete",
                "manifest_valid": True,
                "server_terminal_utc": terminal,
                "manifest": {
                    "slot_receipts": [
                        {
                            "provider": "xtrend",
                            "fetch_run_id": "fetch_" + "1" * 24,
                            "item_count": 4,
                        },
                        {
                            "provider": "xtrend",
                            "fetch_run_id": "fetch_" + "2" * 24,
                            "item_count": 5,
                        },
                        {
                            "provider": "x",
                            "fetch_run_id": "fetch_" + "3" * 24,
                            "item_count": 10,
                        },
                        {
                            "provider": "x",
                            "fetch_run_id": "fetch_" + "4" * 24,
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

    assert manifest["schema_version"] == 3
    assert manifest["policy"] == "global-only-editorial-and-trend-reaction-v1"
    assert manifest["collector_semantics_id"] == "collector_cf5b90da1cd4d7db969389ee"
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
            "severity": "warning",
            "details": {
                "schema_version": 1,
                "collector_policy": "global-only-editorial-and-trend-reaction-v1",
            },
        },
    )]
    assert json.loads(capsys.readouterr().out) == {
        "component": "collector",
        "delivered": True,
    }


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
