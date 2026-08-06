"""Independent fetch receipts retain late discoveries without shared-cursor gaps."""
import inspect
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
def test_formal_gate_and_audit_require_all_ten_configured_globalnews_slots(capsys):
    from tradingagents.formal_experiment import _formal_evidence_query_slots

    expected = poller._globalnews_query_slots(poller.DEFAULT_CONFIG["macro_themes"])
    assert len(expected) == 10
    assert _formal_evidence_query_slots() == expected

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

    poller.print_audit(AuditStore())

    output = capsys.readouterr().out
    assert captured["kwargs"]["expected_query_slots"] == expected
    assert "formal_expected_query_slots=10" in output
    assert "formal_missing_query_slots=10" in output


@pytest.mark.unit
def test_paper_watchdog_rejects_stale_or_newer_failure_heartbeat(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    store.set_meta("paper:last_success_utc", 100.0)
    assert poller.check_paper_heartbeat(store, now=150.0, max_age=100.0)

    store.set_meta("paper:last_failure_utc", 160.0)
    assert not poller.check_paper_heartbeat(store, now=170.0, max_age=100.0)
    assert not poller.check_paper_heartbeat(store, now=250.0, max_age=100.0)
    store.close()


@pytest.mark.unit
def test_formal_watchdog_reports_pre_authorization_without_legacy_poll_state(
    monkeypatch,
):
    class NoLegacyPollState:
        def get_meta(self, _key):
            pytest.fail("formal health must not read legacy poll_state heartbeats")

    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (
            {"authorized": False, "collector_configuration_id": None},
            [],
        ),
    )

    result = poller.check_formal_runtime_health(
        NoLegacyPollState(),
        now=100.0,
        max_age=60.0,
        protocol_id="protocol_test",
        collector_build_id="build_" + "1" * 24,
        collector_configuration_id="config_" + "2" * 24,
    )

    assert result == {
        "status": "not-yet-authorized",
        "healthy": True,
        "authorized": False,
        "runtime_components": [],
    }


@pytest.mark.unit
def test_formal_watchdog_binds_configuration_and_reports_paused(monkeypatch):
    configuration_id = "config_" + "2" * 24
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (
            {"authorized": True, "collector_configuration_id": configuration_id},
            [
                {
                    "runtime_component": "decision",
                    "event_type": "paused",
                    "observed_utc": 96.0,
                    "latest_success_utc": None,
                    "latest_failure_utc": None,
                    "latest_paused_utc": 96.0,
                },
                {
                    "runtime_component": "marker",
                    "event_type": "success",
                    "observed_utc": 95.0,
                    "latest_success_utc": 95.0,
                    "latest_failure_utc": None,
                    "latest_paused_utc": None,
                },
            ],
        ),
    )

    result = poller.check_formal_runtime_health(
        object(),
        now=100.0,
        max_age=60.0,
        protocol_id="protocol_test",
        collector_build_id="build_" + "1" * 24,
        collector_configuration_id=configuration_id,
    )

    assert result["status"] == "paused"
    assert result["healthy"] is True
    assert result["authorized"] is True
    assert result["runtime_components"] == [
        {"runtime_component": "decision", "status": "paused"},
        {"runtime_component": "marker", "status": "healthy"},
    ]


@pytest.mark.unit
def test_formal_watchdog_distinguishes_missing_from_explicit_paused(monkeypatch):
    configuration_id = "config_" + "2" * 24
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (
            {"authorized": True, "collector_configuration_id": configuration_id},
            [
                {
                    "runtime_component": "marker",
                    "event_type": "paused",
                    "observed_utc": 96.0,
                    "latest_success_utc": None,
                    "latest_failure_utc": None,
                    "latest_paused_utc": 96.0,
                }
            ],
        ),
    )

    result = poller.check_formal_runtime_health(
        object(),
        now=100.0,
        max_age=60.0,
        protocol_id="protocol_test",
        collector_build_id="build_" + "1" * 24,
        collector_configuration_id=configuration_id,
    )

    assert result["status"] == "unhealthy"
    assert result["healthy"] is False
    assert result["runtime_components"] == [
        {"runtime_component": "decision", "status": "missing"},
        {"runtime_component": "marker", "status": "paused"},
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("latest_success_utc", "latest_failure_utc", "latest_paused_utc", "expected"),
    [
        (None, 90.0, 96.0, "failure"),
        (80.0, 90.0, 96.0, "failure"),
        (92.0, 90.0, 96.0, "paused"),
        (20.0, 10.0, 30.0, "stale"),
    ],
)
def test_formal_watchdog_pause_cannot_mask_failure_or_staleness(
    monkeypatch,
    latest_success_utc,
    latest_failure_utc,
    latest_paused_utc,
    expected,
):
    configuration_id = "config_" + "2" * 24
    rows = []
    for component in ("decision", "marker"):
        rows.append(
            {
                "runtime_component": component,
                "event_type": "paused",
                "observed_utc": latest_paused_utc,
                "latest_success_utc": latest_success_utc,
                "latest_failure_utc": latest_failure_utc,
                "latest_paused_utc": latest_paused_utc,
            }
        )
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (
            {"authorized": True, "collector_configuration_id": configuration_id},
            rows,
        ),
    )

    result = poller.check_formal_runtime_health(
        object(),
        now=100.0,
        max_age=60.0,
        protocol_id="protocol_test",
        collector_build_id="build_" + "1" * 24,
        collector_configuration_id=configuration_id,
    )

    assert result["runtime_components"] == [
        {"runtime_component": "decision", "status": expected},
        {"runtime_component": "marker", "status": expected},
    ]
    assert result["healthy"] is (expected == "paused")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("release", "rows"),
    [
        ({"authorized": False, "collector_configuration_id": "config_bad"}, []),
        (
            {"authorized": True, "collector_configuration_id": "config_" + "2" * 24},
            [{"runtime_component": "decision"}],
        ),
        (
            {"authorized": True, "collector_configuration_id": "config_" + "2" * 24},
            [
                {
                    "runtime_component": "decision",
                    "event_type": "unknown",
                    "observed_utc": 1.0,
                    "latest_success_utc": None,
                    "latest_failure_utc": None,
                    "latest_paused_utc": None,
                }
            ],
        ),
        (
            {"authorized": True, "collector_configuration_id": "config_" + "2" * 24},
            [
                {
                    "runtime_component": "decision",
                    "event_type": "success",
                    "observed_utc": float("nan"),
                    "latest_success_utc": float("nan"),
                    "latest_failure_utc": None,
                    "latest_paused_utc": None,
                }
            ],
        ),
        (
            {"authorized": True, "collector_configuration_id": "config_" + "2" * 24},
            [
                {
                    "runtime_component": "decision",
                    "event_type": "paused",
                    "observed_utc": 10.0,
                    "latest_success_utc": 11.0,
                    "latest_failure_utc": None,
                    "latest_paused_utc": 10.0,
                }
            ],
        ),
    ],
)
def test_formal_health_projection_contract_fails_closed(release, rows):
    with pytest.raises(ValueError):
        poller._validated_formal_runtime_health_projection(release, rows)


@pytest.mark.unit
def test_formal_watchdog_rejects_future_heartbeat(monkeypatch):
    configuration_id = "config_" + "2" * 24
    monkeypatch.setattr(
        poller,
        "_formal_runtime_health_projection",
        lambda *_args, **_kwargs: (
            {"authorized": True, "collector_configuration_id": configuration_id},
            [
                {
                    "runtime_component": component,
                    "event_type": "success",
                    "observed_utc": 401.0,
                    "latest_success_utc": 401.0,
                    "latest_failure_utc": None,
                    "latest_paused_utc": None,
                }
                for component in ("decision", "marker")
            ],
        ),
    )

    result = poller.check_formal_runtime_health(
        object(),
        now=100.0,
        max_age=60.0,
        protocol_id="protocol_test",
        collector_build_id="build_" + "1" * 24,
        collector_configuration_id=configuration_id,
    )

    assert result["status"] == "unhealthy"
    assert result["healthy"] is False
    assert result["runtime_components"] == [
        {"runtime_component": "decision", "status": "future"},
        {"runtime_component": "marker", "status": "future"},
    ]


@pytest.mark.unit
def test_formal_watchdog_uses_only_migration_013_projections():
    source = inspect.getsource(poller._formal_runtime_health_projection)

    assert "RUNTIME_HEALTH_PROJECTION_SQL" in source
    assert "_FORMAL_COLLECTOR_RELEASE_PROJECTION_SQL" in source
    assert "formal_collector_release_projection" in (
        poller._FORMAL_COLLECTOR_RELEASE_PROJECTION_SQL
    )
    assert "paper_marks" not in source
    assert "paper_decisions" not in source
    assert "poll_state" not in source


@pytest.mark.unit
def test_formal_daemon_never_falls_back_to_legacy_poll_state_watchdog(monkeypatch):
    calls = []
    identity = {
        "protocol_id": "protocol_test",
        "collector_build_id": "build_" + "1" * 24,
        "collector_configuration_id": "config_" + "2" * 24,
    }
    monkeypatch.setattr(poller.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(poller, "run_cycle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        poller,
        "check_formal_runtime_health",
        lambda *_args, **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(
        poller,
        "check_paper_heartbeat",
        lambda *_args, **_kwargs: pytest.fail("formal mode used legacy poll_state"),
    )
    monkeypatch.setattr(
        poller,
        "_sleep",
        lambda _seconds, stop: stop.update(flag=True),
    )

    poller.poll_forever(
        object(),
        [],
        [],
        3600,
        {},
        paper_heartbeat_max_age=93_600.0,
        formal_runtime_identity=identity,
    )

    assert calls == [identity]


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
