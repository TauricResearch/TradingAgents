"""Forward paper-ledger immutability, calendar timing, and accounting."""

import argparse
import json
import multiprocessing
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.formal_activation import (
    RELEASE_RECEIPT_TYPES,
    build_trial_authorization,
    image_attestation,
)
from tradingagents.paper_trading import (
    CONFIRMATORY_TRIAL_LABEL,
    PaperStore,
    _cycle_with_retries,
    _mark_formal_once,
    _postgres_formal_operation_lock,
    advance_mark,
    current_decision_date,
    cycle,
    decide,
    decision_window,
    formal_operation_lock,
    mark_formal_strategies,
    mark_next,
    next_daemon_run,
    next_worker_run,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)


def _acquire_formal_lock_in_child(
    db_url, run_id, started, acquired, release
):
    """Spawn-safe process target used to exercise the SQLite flock."""
    from tradingagents.paper_trading import formal_operation_lock

    started.set()
    with formal_operation_lock(db_url, run_id):
        acquired.set()
        release.wait(10)


def _config():
    return {
        "tickers": ["A", "B"],
        "benchmark": "SPY",
        "cost_bps": 5.0,
        "slippage_bps": 5.0,
        "annual_borrow_bps": 300.0,
    }


def _install_formal_price_fakes(monkeypatch, paper_trading, opens):
    clock = {"value": 0.0}
    snapshot_calls = []

    monkeypatch.setattr(
        paper_trading, "build_identity", lambda: "build_" + "a" * 24
    )
    monkeypatch.setattr(
        paper_trading, "_formal_capture_clock", lambda: clock["value"]
    )

    def fake_batch(symbols, previous_session, session_date, *, clock_fn):
        snapshots = []
        for ticker in symbols:
            snapshot_calls.append((ticker, previous_session, session_date))
            rows = {}
            for endpoint in (
                [session_date] if previous_session is None
                else [previous_session, session_date]
            ):
                value = opens[endpoint][ticker]
                rows[endpoint] = {
                    "session_date": endpoint,
                    "raw_open": value,
                    "close": value,
                    "adjusted_close": value,
                    "adjustment_factor": 1.0,
                    "adjusted_open": value,
                    "dividend": 0.0,
                    "split_ratio": 0.0,
                }
            base = {
                "schema_version": 1,
                "provider": "yfinance",
                "requested_ticker": ticker,
                "from_session": previous_session,
                "to_session": session_date,
                "requested_utc": clock_fn(),
                "received_utc": clock_fn(),
                "rows": rows,
            }
            snapshots.append({
                **base,
                "vendor_snapshot_id": content_id(
                    base, prefix="price_snapshot_"
                ),
            })
        return snapshots

    monkeypatch.setattr(paper_trading, "_capture_price_vendor_batch", fake_batch)
    return clock, snapshot_calls


def _decisions():
    return [
        {
            "ticker": "A", "replicate": 0, "action": "Buy", "score": 1.0,
            "data_fingerprint": "data-a", "signal_fingerprint": "signal-v1",
            "final_decision": "Rating: Buy",
        },
        {
            "ticker": "B", "replicate": 0, "action": "Hold", "score": 0.0,
            "data_fingerprint": "data-b", "signal_fingerprint": "signal-v1",
            "final_decision": "Rating: Hold",
        },
    ]


def _mark(session_date, *, target_decision_date=None, nav=1.0):
    return {
        "session_date": session_date,
        "captured_utc": 1.0,
        "nav": nav,
        "benchmark_nav": 1.0,
        "period_return": 0.0,
        "benchmark_period_return": 0.0,
        "turnover": 0.0,
        "trading_cost": 0.0,
        "borrow_cost": 0.0,
        "weights": {"A": 0.5, "B": 0.5},
        "opens": {"A": 100.0, "B": 100.0},
        "benchmark_open": 100.0,
        "target_decision_date": target_decision_date,
    }


def _insert_mark_raw(store, run_id, mark, *, strategy_id=None):
    """Seed status-only fixtures without invoking confirmatory lifecycle checks."""
    values = dict(mark)
    values["weights_json"] = json.dumps(values.pop("weights"), sort_keys=True)
    values["opens_json"] = json.dumps(values.pop("opens"), sort_keys=True)
    if strategy_id is None:
        store.conn.execute(
            "INSERT INTO paper_marks "
            "(run_id,session_date,captured_utc,nav,benchmark_nav,period_return,"
            "benchmark_period_return,turnover,trading_cost,borrow_cost,weights_json,"
            "opens_json,benchmark_open,target_decision_date) VALUES "
            "(:run_id,:session_date,:captured_utc,:nav,:benchmark_nav,:period_return,"
            ":benchmark_period_return,:turnover,:trading_cost,:borrow_cost,:weights_json,"
            ":opens_json,:benchmark_open,:target_decision_date)",
            {"run_id": run_id, **values},
        )
    else:
        store.conn.execute(
            "INSERT INTO paper_strategy_marks "
            "(run_id,strategy_id,session_date,captured_utc,nav,benchmark_nav,"
            "period_return,benchmark_period_return,turnover,trading_cost,borrow_cost,"
            "weights_json,opens_json,benchmark_open,target_decision_date) VALUES "
            "(:run_id,:strategy_id,:session_date,:captured_utc,:nav,:benchmark_nav,"
            ":period_return,:benchmark_period_return,:turnover,:trading_cost,:borrow_cost,"
            ":weights_json,:opens_json,:benchmark_open,:target_decision_date)",
            {"run_id": run_id, "strategy_id": strategy_id, **values},
        )
    store.conn.commit()


def _formal_config():
    return {
        "engine": "formal-global-v2",
        "protocol_id": "protocol-1",
        "tickers": ["A", "B"],
        "benchmark": "SPY",
        "cost_bps": 5.0,
        "slippage_bps": 5.0,
        "annual_borrow_bps": 0.0,
    }


def _all_formal_targets():
    return {
        strategy: {
            "weights": {"A": 0.0, "B": 0.0},
            "diagnostics": {"turnover": 0.0},
        }
        for strategy in GLOBAL_EVENT_V2_PROTOCOL["strategies"]
    }


def _formal_authorization_row() -> tuple[dict, dict]:
    images = {
        "collector": image_attestation(
            app_name="tradagent",
            image_ref=(
                "registry.fly.io/tradagent:"
                "deployment-01KZAE0P4ER12SS2215QXBSN0H"
            ),
            image_digest="sha256:" + "1" * 64,
        ),
        "paper_decision": image_attestation(
            app_name="tradagent-paper-decision",
            image_ref=(
                "registry.fly.io/tradagent-paper-decision:"
                "deployment-01KZAD8T2KXJJJXAM2JJW8E447"
            ),
            image_digest="sha256:" + "2" * 64,
        ),
        "paper_marker": image_attestation(
            app_name="tradagent-paper-marker",
            image_ref=(
                "registry.fly.io/tradagent-paper-marker:"
                "deployment-01KZAF9N3MYKKKYCY3KKX9F558"
            ),
            image_digest="sha256:" + "3" * 64,
        ),
    }
    configuration_binding = {
        "configuration_manifest_id": "config_" + "1" * 24,
        "collector_configuration_id": "config_" + "2" * 24,
        "paper_decision_configuration_id": "config_" + "3" * 24,
        "paper_marker_configuration_id": "config_" + "4" * 24,
    }
    authorization = build_trial_authorization(
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        run_id="formal-runtime-test",
        registration_id="registration_" + "4" * 24,
        outcome_semantics_id="outcome_semantics_" + "5" * 64,
        configuration_binding=configuration_binding,
        collector_image=images["collector"],
        paper_decision_image=images["paper_decision"],
        paper_marker_image=images["paper_marker"],
        release_receipt_ids={
            receipt_type: "release_" + f"{index:024x}"
            for index, receipt_type in enumerate(RELEASE_RECEIPT_TYPES, start=1)
        },
    )
    row = {
        "protocol_id": authorization["protocol_id"],
        "run_id": authorization["run_id"],
        "registration_id": authorization["registration_id"],
        "authorization_id": authorization["authorization_id"],
        "authorized_utc": 1_786_000_000.0,
        "outcome_semantics_id": authorization["outcome_semantics_id"],
        **authorization["configuration_binding"],
        "collector_build_id": authorization["images"]["collector"]["build_id"],
        "paper_decision_build_id": authorization["images"]["paper_decision"][
            "build_id"
        ],
        "paper_marker_build_id": authorization["images"]["paper_marker"]["build_id"],
        "authorization_json": canonical_json(authorization),
    }
    return authorization, row


@pytest.mark.unit
def test_formal_authorization_row_rejects_noncanonical_document_encoding():
    authorization, row = _formal_authorization_row()
    row["authorization_json"] = json.dumps(
        authorization,
        indent=2,
        sort_keys=True,
    )

    with pytest.raises(ValueError, match="JSON is not canonical"):
        PaperStore._validated_authorization_row(
            row,
            run_id=authorization["run_id"],
        )


@pytest.mark.unit
def test_formal_authorization_row_rejects_scalar_document_disagreement():
    authorization, row = _formal_authorization_row()
    row["paper_marker_build_id"] = "build_" + "0" * 24

    with pytest.raises(ValueError, match="columns disagree"):
        PaperStore._validated_authorization_row(
            row,
            run_id=authorization["run_id"],
        )


def _formal_weight_projection_rows(tickers: list[str]) -> list[dict]:
    return [
        {
            "strategy_id": strategy_id,
            "weights_json": json.dumps(
                dict.fromkeys(tickers, (index + 1) / 100),
                sort_keys=True,
                separators=(",", ":"),
            ),
            "source_kind": "strategy_target",
            "source_session_date": None,
            "source_decision_date": "2026-08-04",
        }
        for index, strategy_id in enumerate(
            sorted(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
        )
    ]


@pytest.mark.unit
def test_formal_decision_weight_projection_preserves_exact_strategy_snapshots():
    tickers = ["AAPL", "MSFT"]
    rows = _formal_weight_projection_rows(tickers)
    store = PaperStore.__new__(PaperStore)
    store._sqlite = False

    def projected(sql, params):
        assert "formal_decision_weight_projection" in sql
        assert params == {"run_id": "formal-runtime-test"}
        return rows

    store._rows = projected

    snapshots = store.formal_decision_weight_snapshots(
        "formal-runtime-test",
        tickers,
    )

    assert list(snapshots) == sorted(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    for index, strategy_id in enumerate(snapshots):
        assert snapshots[strategy_id] == {
            "weights": dict.fromkeys(tickers, (index + 1) / 100),
            "source_kind": "strategy_target",
            "source_session_date": None,
            "source_decision_date": "2026-08-04",
        }


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["extra_column", "wrong_order", "wrong_universe"])
def test_formal_decision_weight_projection_rejects_inexact_rows(mutation):
    tickers = ["AAPL", "MSFT"]
    rows = _formal_weight_projection_rows(tickers)
    if mutation == "extra_column":
        rows[0]["nav"] = 1.0
    elif mutation == "wrong_order":
        rows.reverse()
    else:
        rows[0]["weights_json"] = '{"AAPL":0.01,"NVDA":0.01}'
    store = PaperStore.__new__(PaperStore)
    store._sqlite = False
    store._rows = lambda _sql, _params: rows

    with pytest.raises(
        ValueError,
        match="wrong inventory|projection is malformed",
    ):
        store.formal_decision_weight_snapshots(
            "formal-runtime-test",
            tickers,
        )


@pytest.mark.unit
def test_paper_store_freezes_complete_decision_set(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("core", _config(), 100.0)
    store.record_decision_set(
        "core", "2026-07-27", "2026-07-28", 200.0,
        _decisions(), {"A": 1.0, "B": 0.0},
    )

    assert store.target_for_entry("core", "2026-07-28") == {
        "decision_date": "2026-07-27",
        "weights": {"A": 1.0, "B": 0.0},
    }
    legacy_status = store.status("core")
    assert legacy_status["decision_rows"] == 2
    assert set(legacy_status) == {
        "run_id",
        "config",
        "decision_rows",
        "decision_dates",
        "mark_count",
        "start_date",
        "end_date",
        "nav",
        "benchmark_nav",
        "labels",
        "strategy_marks",
    }
    with pytest.raises(sqlite3.IntegrityError):
        store.record_decision_set(
            "core", "2026-07-27", "2026-07-28", 300.0,
            _decisions(), {"A": 0.0, "B": 1.0},
        )
    assert store.target_for_entry("core", "2026-07-28")["weights"] == {
        "A": 1.0, "B": 0.0,
    }
    store.close()


@pytest.mark.unit
def test_paper_run_config_cannot_change(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("core", _config(), 100.0)
    changed = {**_config(), "benchmark": "QQQ"}
    with pytest.raises(ValueError, match="different config"):
        store.create_run("core", changed, 200.0)
    store.close()


@pytest.mark.unit
def test_paper_decisions_are_database_enforced_append_only(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("core", _config(), 100.0)
    store.record_decision_set(
        "core", "2026-07-27", "2026-07-28", 200.0,
        _decisions(), {"A": 1.0, "B": 0.0},
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute("UPDATE paper_targets SET weights_json='{}'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute("DELETE FROM paper_decisions")
    store.close()


@pytest.mark.unit
def test_formal_decision_freezes_bundle_forecasts_and_synchronized_targets(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    config = _formal_config()
    store.create_run("formal", config, 100.0)
    store.register_protocol("protocol-1", {"horizon": 1}, 100.0)
    registration_details = {"protocol_id": "protocol-1", "analysis": "confirmatory"}
    assert store.register_confirmatory_trial(
        "formal", 150.0, registration_details
    ) is True
    assert store.latest_strategy_weight_snapshot(
        "formal", "global_events_champion", ["A", "B"]
    ) == {
        "weights": {"A": 0.0, "B": 0.0},
        "source_kind": "initial_zero",
        "source_session_date": None,
        "source_decision_date": None,
    }
    targets = _all_formal_targets()
    targets["global_events_champion"] = {
        "weights": {"A": 0.4, "B": 0.0}, "diagnostics": {"turnover": 0.4},
    }
    targets["equal_weight"] = {
        "weights": {"A": 0.5, "B": 0.5}, "diagnostics": {"turnover": 1.0},
    }
    artifact = {
        "raw_response": {"id": "response-1"},
        "attempt_ordinal": 1,
        "strategy_targets": targets,
    }
    attempt_started = datetime(2026, 7, 28, 1, tzinfo=timezone.utc).timestamp()
    store.record_formal_attempt_started(
        "formal", "2026-07-27", "2026-07-28", attempt_started
    )
    store.record_formal_decision(
        run_id="formal", decision_date="2026-07-27", entry_date="2026-07-28",
        created_utc=attempt_started + 1, protocol_id="protocol-1", build_id="build-1",
        model_id="model-1", input_bundle_id="input-1",
        artifact_id=content_id(artifact, prefix="artifact_"),
        artifact=artifact, coverage={"complete": True},
        events=[{"event_id": "event-1", "summary": "global event"}],
        forecasts=[{"ticker": "A", "expected_excess_return_bps": 20},
                   {"ticker": "B", "expected_excess_return_bps": -10}],
        strategy_targets=targets,
    )

    assert store.target_for_entry("formal", "2026-07-28")["weights"] == {
        "A": 0.4, "B": 0.0,
    }
    assert store.formal_strategies("formal") == sorted(
        GLOBAL_EVENT_V2_PROTOCOL["strategies"]
    )
    assert store.latest_formal_forecasts("formal")[0]["ticker"] == "A"
    assert store.latest_formal_forecast_snapshot("formal") == {
        "decision_date": "2026-07-27",
        "forecasts": [
            {"ticker": "A", "expected_excess_return_bps": 20},
            {"ticker": "B", "expected_excess_return_bps": -10},
        ],
    }
    target_snapshot = store.latest_strategy_weight_snapshot(
        "formal", "global_events_champion", ["A", "B"]
    )
    assert target_snapshot == {
        "weights": {"A": 0.4, "B": 0.0},
        "source_kind": "strategy_target",
        "source_session_date": None,
        "source_decision_date": "2026-07-27",
    }
    assert store.latest_strategy_weights(
        "formal", "global_events_champion", ["A", "B"]
    ) == {"A": 0.4, "B": 0.0}
    assert store._rows("SELECT COUNT(*) AS n FROM paper_artifacts")[0]["n"] == 1
    snapshot = store.formal_bundle("formal")
    assert snapshot["bundle"]["coverage"] == {"complete": True}
    assert snapshot["artifact"]["content"] == artifact
    assert snapshot["strategy_targets"]["global_events_champion"]["weights"] == {
        "A": 0.4,
        "B": 0.0,
    }
    assert snapshot["champion_target"]["weights"] == {"A": 0.4, "B": 0.0}
    assert snapshot["registration"] == {
        "label": CONFIRMATORY_TRIAL_LABEL,
        "created_utc": 150.0,
        "details": registration_details,
    }
    assert store.register_confirmatory_trial(
        "formal", 999.0, registration_details
    ) is False
    with pytest.raises(ValueError, match="different details"):
        store.register_confirmatory_trial(
            "formal", 999.0, {**registration_details, "analysis": "exploratory"}
        )

    strategy_mark = _mark(
        "2026-07-28", target_decision_date="2026-07-27", nav=1.01
    )
    strategy_mark["weights"] = {"A": 0.3, "B": 0.1}
    _insert_mark_raw(
        store,
        "formal",
        _mark("2026-07-28", target_decision_date="2026-07-27", nav=1.01),
    )
    store.record_strategy_mark(
        "formal", "global_events_champion", strategy_mark
    )
    assert store.latest_strategy_weight_snapshot(
        "formal", "global_events_champion", ["A", "B"]
    ) == {
        "weights": {"A": 0.3, "B": 0.1},
        "source_kind": "strategy_mark",
        "source_session_date": "2026-07-28",
        "source_decision_date": "2026-07-27",
    }
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute("DELETE FROM paper_artifacts")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute(
            "UPDATE paper_run_labels SET details_json='{}' "
            "WHERE run_id='formal'"
        )
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize("activity_kind", ["bundle", "target", "outcome"])
def test_confirmatory_registration_rejects_late_bundle_target_or_outcome(
    tmp_path, activity_kind
):
    store = PaperStore(str(tmp_path / f"{activity_kind}.db"))
    run_id = f"formal-{activity_kind}"
    store.create_run(run_id, _formal_config(), 100.0)
    if activity_kind == "bundle":
        store.conn.execute(
            "INSERT INTO paper_decision_bundles "
            "(run_id,decision_date,attempt_ordinal,created_utc,protocol_id,build_id,model_id,"
            "input_bundle_id,artifact_id,coverage_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                "2026-07-27",
                1,
                200.0,
                "protocol-1",
                "build-1",
                "model-1",
                "input-1",
                "artifact-1",
                "{}",
            ),
        )
        store.conn.commit()
    elif activity_kind == "target":
        store.conn.execute(
            "INSERT INTO paper_targets "
            "(run_id,decision_date,entry_date,created_utc,weights_json) "
            "VALUES (?,?,?,?,?)",
            (run_id, "2026-07-27", "2026-07-28", 200.0, "{}"),
        )
        store.conn.commit()
    else:
        store.record_mark(run_id, _mark("2026-07-28"))

    with pytest.raises(ValueError, match="too late"):
        store.register_confirmatory_trial(
            run_id, 300.0, {"protocol_id": "protocol-1"}
        )
    store.close()


@pytest.mark.unit
def test_confirmatory_label_uses_registration_guard_and_forecast_snapshot_can_be_empty(
    tmp_path,
):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.register_protocol(
        "protocol-1", {"strategies": ["champion", "shadow"]}, 90.0
    )
    store.create_run(
        "formal", {**_formal_config(), "protocol_id": "protocol-1"}, 100.0
    )
    assert store.latest_formal_forecast_snapshot("formal") is None
    assert store.latest_formal_forecasts("formal") == []
    empty_status = store.status("formal")
    assert empty_status["expected_strategies"] == ["champion", "shadow"]
    assert empty_status["strategy_marks"] == {"champion": 0, "shadow": 0}
    assert empty_status["strategy_mark_counts_synchronized"] is True
    assert empty_status["common_completed_outcome_intervals"] == 0
    assert store.label_run(
        "formal",
        CONFIRMATORY_TRIAL_LABEL,
        150.0,
        {"protocol_id": "protocol-1"},
    ) is True
    store.close()

    legacy = PaperStore(str(tmp_path / "legacy.db"))
    legacy.create_run("legacy", _config(), 100.0)
    with pytest.raises(ValueError, match="formal-global-v2"):
        legacy.label_run(
            "legacy",
            CONFIRMATORY_TRIAL_LABEL,
            150.0,
            {"protocol_id": "protocol-1"},
        )
    legacy.close()


@pytest.mark.unit
def test_protocol_has_exactly_one_primary_run_and_registry_is_append_only(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    details = {"protocol_id": "protocol-1"}
    store.create_run("primary", _formal_config(), 100.0)
    store.create_run("alternate", _formal_config(), 100.0)

    assert store.register_confirmatory_trial("primary", 150.0, details) is True
    assert store.register_confirmatory_trial("primary", 999.0, details) is False
    with pytest.raises(ValueError, match="different primary run"):
        store.register_confirmatory_trial("alternate", 160.0, details)
    with pytest.raises(sqlite3.IntegrityError, match="primary registry"):
        store.conn.execute(
            "INSERT INTO paper_run_labels "
            "(run_id,label,created_utc,details_json) VALUES (?,?,?,?)",
            (
                "alternate",
                CONFIRMATORY_TRIAL_LABEL,
                160.0,
                json.dumps(details, sort_keys=True, separators=(",", ":")),
            ),
        )
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        store.conn.execute(
            "INSERT INTO formal_trial_registry "
            "(protocol_id,run_id,registration_id,created_utc,details_json) "
            "VALUES (?,?,?,?,?)",
            ("protocol-1", "alternate", "registration_alternate", 160.0, "{}"),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute(
            "UPDATE formal_trial_registry SET run_id='alternate'"
        )
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize("legacy_kind", ["target", "outcome_access", "label"])
def test_primary_registration_rejects_legacy_same_protocol_activity(
    tmp_path, legacy_kind
):
    store = PaperStore(str(tmp_path / f"{legacy_kind}.db"))
    store.create_run("legacy", _formal_config(), 100.0)
    store.create_run("candidate", _formal_config(), 100.0)
    if legacy_kind == "target":
        store.conn.execute(
            "INSERT INTO paper_targets "
            "(run_id,decision_date,entry_date,created_utc,weights_json) "
            "VALUES (?,?,?,?,?)",
            ("legacy", "2026-07-27", "2026-07-28", 200.0, "{}"),
        )
    elif legacy_kind == "outcome_access":
        store.conn.execute(
            "INSERT INTO paper_artifacts "
            "(artifact_id,created_utc,artifact_type,content_json) VALUES (?,?,?,?)",
            (
                "artifact_legacy_access",
                200.0,
                "formal_outcome_access",
                json.dumps({"run_id": "legacy"}),
            ),
        )
    else:
        # Model a label written by a pre-registry application version.
        store.conn.execute("DROP TRIGGER guard_confirmatory_run_label")
        store.conn.execute(
            "INSERT INTO paper_run_labels "
            "(run_id,label,created_utc,details_json) VALUES (?,?,?,?)",
            (
                "legacy",
                CONFIRMATORY_TRIAL_LABEL,
                200.0,
                '{"protocol_id":"protocol-1"}',
            ),
        )
    store.conn.commit()

    with pytest.raises(ValueError, match="same-protocol trial activity"):
        store.register_confirmatory_trial(
            "candidate", 300.0, {"protocol_id": "protocol-1"}
        )
    assert store._rows("SELECT * FROM formal_trial_registry") == []
    store.close()


@pytest.mark.unit
def test_concurrent_protocol_registration_selects_one_primary(tmp_path):
    path = str(tmp_path / "paper.db")
    seed = PaperStore(path)
    seed.create_run("candidate-a", _formal_config(), 100.0)
    seed.create_run("candidate-b", _formal_config(), 100.0)
    seed.close()

    def register(run_id):
        candidate = PaperStore(path)
        try:
            return candidate.register_confirmatory_trial(
                run_id, 150.0, {"protocol_id": "protocol-1"}
            )
        except ValueError:
            return False
        finally:
            candidate.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, ("candidate-a", "candidate-b")))

    assert sorted(results) == [False, True]
    verifier = PaperStore(path)
    rows = verifier._rows(
        "SELECT protocol_id,run_id FROM formal_trial_registry"
    )
    assert len(rows) == 1
    assert rows[0]["protocol_id"] == "protocol-1"
    assert rows[0]["run_id"] in {"candidate-a", "candidate-b"}
    verifier.close()


@pytest.mark.unit
def test_formal_attempt_events_are_append_only_sanitized_and_ordinal(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.register_protocol("protocol-1", {"horizon": 1}, 90.0)
    store.create_run("formal", _formal_config(), 100.0)
    store.register_confirmatory_trial(
        "formal", 150.0, {"protocol_id": "protocol-1"}
    )
    first_start = datetime(2026, 7, 28, 1, tzinfo=timezone.utc).timestamp()
    first_failure = datetime(2026, 7, 28, 2, tzinfo=timezone.utc).timestamp()
    second_start = datetime(2026, 7, 28, 3, tzinfo=timezone.utc).timestamp()

    assert store.record_formal_attempt_started(
        "formal", "2026-07-27", "2026-07-28", first_start
    ) == 1
    assert store.record_formal_attempt_failed(
        "formal", "2026-07-27", 1, first_failure, "coverage_gate_failed"
    ) is True
    assert store.record_formal_attempt_failed(
        "formal", "2026-07-27", 1, first_failure + 1, "coverage_gate_failed"
    ) is False
    assert store.record_formal_attempt_started(
        "formal", "2026-07-27", "2026-07-28", second_start
    ) == 2

    events = store.formal_attempt_events("formal", "2026-07-27")
    assert [(row["attempt_ordinal"], row["event_type"], row["reason_code"])
            for row in events] == [
        (1, "started", None),
        (1, "failed", "coverage_gate_failed"),
        (2, "started", None),
    ]
    counts = store.formal_trial_counts("formal")
    assert counts["attempts_started"] == 2
    assert counts["attempts_failed"] == 1
    assert counts["unresolved_attempts_without_terminal_event"] == 1

    with pytest.raises(ValueError, match="not allowlisted"):
        store.record_formal_attempt_failed(
            "formal", "2026-07-27", 2, second_start + 1,
            "provider said token=secret",
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO paper_decision_attempt_events "
            "(run_id,decision_date,entry_date,attempt_ordinal,event_type,"
            "created_utc,reason_code) VALUES (?,?,?,?,?,?,?)",
            (
                "formal", "2026-07-27", "2026-07-28", 3, "failed",
                second_start + 2, "https://secret.invalid/token",
            ),
        )
    store.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute(
            "UPDATE paper_decision_attempt_events SET reason_code='llm_failed' "
            "WHERE event_type='failed'"
        )
    store.conn.rollback()
    store.close()


@pytest.mark.unit
def test_formal_bundle_requires_a_live_recorded_attempt(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.register_protocol("protocol-1", {"horizon": 1}, 90.0)
    store.create_run("formal", _formal_config(), 100.0)
    store.register_confirmatory_trial(
        "formal", 150.0, {"protocol_id": "protocol-1"}
    )
    started = datetime(2026, 7, 28, 1, tzinfo=timezone.utc).timestamp()
    kwargs = {
        "run_id": "formal",
        "decision_date": "2026-07-27",
        "entry_date": "2026-07-28",
        "created_utc": started + 2,
        "protocol_id": "protocol-1",
        "build_id": "build-1",
        "model_id": "model-1",
        "input_bundle_id": "input-1",
        "artifact_id": "artifact-1",
        "artifact": {},
        "coverage": {},
        "events": [],
        "forecasts": [],
        "strategy_targets": {},
    }

    with pytest.raises(ValueError, match="recorded attempt start"):
        store.record_formal_decision(**kwargs)

    ordinal = store.record_formal_attempt_started(
        "formal", "2026-07-27", "2026-07-28", started
    )
    store.record_formal_attempt_failed(
        "formal", "2026-07-27", ordinal, started + 1, "llm_failed"
    )
    with pytest.raises(ValueError, match="already failed"):
        store.record_formal_decision(**kwargs)
    assert store._rows("SELECT COUNT(*) AS n FROM paper_artifacts")[0]["n"] == 0
    store.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("artifact_id", "not content-addressed"),
        ("missing_strategy", "exact frozen strategy set"),
        ("extra_strategy", "exact frozen strategy set"),
        ("artifact_targets", "artifact and persisted strategy targets differ"),
    ],
)
def test_formal_persistence_recomputes_artifact_id_and_strategy_inventory(
    tmp_path, tamper, message
):
    store = PaperStore(str(tmp_path / f"{tamper}.db"))
    store.register_protocol("protocol-1", {"horizon": 1}, 90.0)
    store.create_run("formal", _formal_config(), 100.0)
    store.register_confirmatory_trial(
        "formal", 150.0, {"protocol_id": "protocol-1"}
    )
    started = datetime(2026, 7, 28, 1, tzinfo=timezone.utc).timestamp()
    store.record_formal_attempt_started(
        "formal", "2026-07-27", "2026-07-28", started
    )
    targets = _all_formal_targets()
    artifact = {
        "attempt_ordinal": 1,
        "strategy_targets": json.loads(json.dumps(targets)),
    }
    artifact_id = content_id(artifact, prefix="artifact_")
    if tamper == "artifact_id":
        artifact_id = "artifact_intentionally_wrong"
    elif tamper == "missing_strategy":
        targets.pop("momentum")
        artifact["strategy_targets"].pop("momentum")
        artifact_id = content_id(artifact, prefix="artifact_")
    elif tamper == "extra_strategy":
        targets["post_hoc"] = targets["momentum"]
        artifact["strategy_targets"]["post_hoc"] = targets["momentum"]
        artifact_id = content_id(artifact, prefix="artifact_")
    else:
        artifact["strategy_targets"]["momentum"]["weights"]["A"] = 1.0
        artifact_id = content_id(artifact, prefix="artifact_")

    with pytest.raises(ValueError, match=message):
        store.record_formal_decision(
            run_id="formal",
            decision_date="2026-07-27",
            entry_date="2026-07-28",
            created_utc=started + 1,
            protocol_id="protocol-1",
            build_id="build-1",
            model_id="model-1",
            input_bundle_id="input-1",
            artifact_id=artifact_id,
            artifact=artifact,
            coverage={},
            events=[],
            forecasts=[],
            strategy_targets=targets,
        )
    assert store._rows("SELECT COUNT(*) AS n FROM paper_artifacts")[0]["n"] == 0
    assert store._rows("SELECT COUNT(*) AS n FROM paper_decision_bundles")[0]["n"] == 0
    store.close()


@pytest.mark.unit
def test_formal_ledger_stops_targets_and_intervals_at_registered_horizon(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.register_protocol("protocol-1", {"horizon": 1}, 90.0)
    store.create_run("formal", _formal_config(), 100.0)
    store.register_confirmatory_trial(
        "formal", 150.0, {"protocol_id": "protocol-1"}
    )
    store.conn.executemany(
        "INSERT INTO paper_interval_assignments "
        "(run_id,interval_index,from_session_date,session_date,"
        "scheduled_decision_date,created_utc,disposition,"
        "applied_target_decision_date,return_vector_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                "formal", index, f"from-{index}", f"to-{index}",
                f"decision-{index}", float(index), "target_applied",
                f"decision-{index}", f"return_vector_{index}",
            )
            for index in range(1, 252)
        ],
    )
    store.conn.commit()
    started = datetime(2026, 7, 28, 1, tzinfo=timezone.utc).timestamp()

    with pytest.raises(ValueError, match="decision horizon is complete"):
        store.record_formal_attempt_started(
            "formal", "2026-07-27", "2026-07-28", started
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO paper_interval_assignments "
            "(run_id,interval_index,from_session_date,session_date,"
            "scheduled_decision_date,created_utc,disposition,"
            "applied_target_decision_date,return_vector_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "other", 253, "from", "to", "decision", 1.0,
                "carry_forward_missing_decision", None, "return_vector_253",
            ),
        )
    store.conn.rollback()
    store.close()


@pytest.mark.unit
def test_formal_status_reports_synchronized_completed_outcomes_and_gaps(tmp_path):
    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("formal", _formal_config(), 100.0)
    store.register_confirmatory_trial(
        "formal", 150.0, {"protocol_id": "protocol-1"}
    )
    for decision_date in ("2026-07-27", "2026-07-28"):
        store.conn.execute(
            "INSERT INTO paper_decision_bundles "
            "(run_id,decision_date,attempt_ordinal,created_utc,protocol_id,build_id,model_id,"
            "input_bundle_id,artifact_id,coverage_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "formal",
                decision_date,
                1,
                200.0,
                "protocol-1",
                "build-1",
                "model-1",
                f"input-{decision_date}",
                f"artifact-{decision_date}",
                "{}",
            ),
        )
    for strategy_id in ("global_events_champion", "equal_weight"):
        store.conn.execute(
            "INSERT INTO paper_strategy_targets "
            "(run_id,decision_date,strategy_id,entry_date,created_utc,"
            "weights_json,diagnostics_json) VALUES (?,?,?,?,?,?,?)",
            (
                "formal",
                "2026-07-27",
                strategy_id,
                "2026-07-28",
                200.0,
                '{"A":0.5,"B":0.5}',
                "{}",
            ),
        )
    store.conn.commit()

    for index, session_date in enumerate(
        ("2026-07-28", "2026-07-29", "2026-07-30")
    ):
        _insert_mark_raw(
            store, "formal", _mark(session_date, nav=1.0 + index / 100)
        )
        _insert_mark_raw(
            store, "formal", _mark(session_date),
            strategy_id="global_events_champion",
        )
        if session_date != "2026-07-30":
            _insert_mark_raw(
                store, "formal", _mark(session_date), strategy_id="equal_weight"
            )

    status = store.status("formal")
    assert status["decision_rows"] == 2
    assert status["decision_dates"] == 2
    assert status["formal_decision_bundles"] == 2
    assert status["formal_decision_dates"] == 2
    assert status["strategy_marks"] == {
        "equal_weight": 2,
        "global_events_champion": 3,
    }
    assert status["strategy_mark_counts_synchronized"] is False
    assert status["strategy_completed_outcome_intervals"] == {
        "equal_weight": 1,
        "global_events_champion": 2,
    }
    assert status["common_completed_outcome_intervals"] == 1
    assert status["common_completed_outcome_dates"] == ["2026-07-29"]
    assert status["common_outcome_start_date"] == "2026-07-29"
    assert status["common_outcome_end_date"] == "2026-07-29"
    assert status["missing_strategy_outcomes"] == {
        "2026-07-30": ["equal_weight"]
    }
    assert status["asymmetric_strategy_outcomes"] is True
    assert status["confirmatory_registration"]["details"] == {
        "protocol_id": "protocol-1"
    }
    store.close()


@pytest.mark.unit
def test_paper_marks_apply_next_open_costs_and_returns():
    first = advance_mark(
        previous=None,
        session_date="2026-07-28",
        captured_utc=1.0,
        opens={"A": 100.0, "B": 20.0},
        benchmark_open=100.0,
        target={"decision_date": "2026-07-27", "weights": {"A": 1.0, "B": 0.0}},
        trading_cost_bps=5,
        slippage_bps=5,
        annual_borrow_bps=300,
    )
    second = advance_mark(
        previous=first,
        session_date="2026-07-29",
        captured_utc=2.0,
        opens={"A": 110.0, "B": 20.0},
        benchmark_open=105.0,
        target=None,
        trading_cost_bps=5,
        slippage_bps=5,
        annual_borrow_bps=300,
    )

    assert first["nav"] == pytest.approx(0.999)
    assert first["turnover"] == 1.0
    assert second["nav"] == pytest.approx(1.0989)
    assert second["benchmark_nav"] == pytest.approx(1.05)


@pytest.mark.unit
def test_forward_mark_can_use_one_vintage_returns_across_a_split():
    previous = advance_mark(
        previous=None,
        session_date="2026-07-28",
        captured_utc=1.0,
        opens={"A": 100.0},
        benchmark_open=100.0,
        target={"decision_date": "2026-07-27", "weights": {"A": 1.0}},
        trading_cost_bps=0,
        slippage_bps=0,
        annual_borrow_bps=0,
    )

    current = advance_mark(
        previous=previous,
        session_date="2026-07-29",
        captured_utc=2.0,
        # A new adjusted-price vintage may show the post-split open at 50 even
        # though the prior immutable mark captured a pre-split 100.
        opens={"A": 50.0},
        benchmark_open=110.0,
        target=None,
        trading_cost_bps=0,
        slippage_bps=0,
        annual_borrow_bps=0,
        asset_returns={"A": 0.0},
        benchmark_period_return_override=0.10,
    )

    assert current["nav"] == pytest.approx(1.0)
    assert current["benchmark_nav"] == pytest.approx(1.1)


@pytest.mark.unit
def test_uninvested_cash_earns_the_frozen_period_rate():
    first = advance_mark(
        previous=None, session_date="2026-07-28", captured_utc=1.0,
        opens={"A": 100.0}, benchmark_open=100.0,
        target={"decision_date": "2026-07-27", "weights": {"A": 0.25}},
        trading_cost_bps=0, slippage_bps=0, annual_borrow_bps=0,
    )
    second = advance_mark(
        previous=first, session_date="2026-07-29", captured_utc=2.0,
        opens={"A": 110.0}, benchmark_open=100.0, target=None,
        trading_cost_bps=0, slippage_bps=0, annual_borrow_bps=0,
        asset_returns={"A": 0.10}, cash_period_return=0.001,
    )

    assert second["period_return"] == pytest.approx(0.25 * 0.10 + 0.75 * 0.001)
    assert second["nav"] == pytest.approx(1.02575)


@pytest.mark.unit
def test_cash_proxy_uses_only_yield_known_before_held_session(monkeypatch):
    from tradingagents import paper_trading

    frame = pd.DataFrame(
        {"Open": [3.5, 99.0], "Close": [3.6, 99.0]},
        index=pd.to_datetime(["2026-07-27", "2026-07-28"]),
    )
    monkeypatch.setattr(paper_trading.backtest, "_load_prices", lambda *_args: frame)

    component = paper_trading._cash_return_component("2026-07-28", "2026-07-29")

    assert component["observation_session"] == "2026-07-27"
    assert component["annual_yield_percent"] == 3.6
    assert component["open_return"] == pytest.approx(3.6 / 100 / 360)


@pytest.mark.unit
def test_formal_capture_ignores_backdated_caller_clock_and_never_calls_vendor(
    tmp_path, monkeypatch
):
    from tradingagents import paper_trading

    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("formal", {
        "engine": "formal-global-v2", "protocol_id": "protocol-1",
        "tickers": ["A"], "benchmark": "SPY",
        "cost_bps": 0.0, "slippage_bps": 0.0, "annual_borrow_bps": 0.0,
    }, 1.0)
    store.register_confirmatory_trial(
        "formal", 1.5, {"protocol_id": "protocol-1"}
    )
    store.conn.execute(
        "INSERT INTO paper_decision_bundles "
        "(run_id,decision_date,attempt_ordinal,created_utc,protocol_id,build_id,model_id,"
        "input_bundle_id,artifact_id,coverage_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "formal", "2026-07-27", 1, 2.0, "protocol-1", "build", "model",
            "input", "artifact", "{}",
        ),
    )
    store.conn.execute(
        "INSERT INTO paper_targets "
        "(run_id,decision_date,entry_date,created_utc,weights_json) "
        "VALUES (?,?,?,?,?)",
        ("formal", "2026-07-27", "2026-07-28", 2.0, '{"A":1.0}'),
    )
    store.conn.commit()
    _scheduled, deadline = paper_trading.formal_price_capture_window("2026-07-28")
    monkeypatch.setattr(
        paper_trading, "_formal_capture_clock", lambda: deadline.timestamp()
    )
    vendor_calls = []
    monkeypatch.setattr(
        paper_trading,
        "_capture_price_vendor_batch",
        lambda *_args, **_kwargs: vendor_calls.append(True),
    )

    caller_asserted_old_time = datetime(
        2026, 7, 28, 15, 0, tzinfo=timezone.utc
    ).timestamp()
    with pytest.raises(paper_trading.FormalPriceIntegrityError):
        mark_next(store, "formal", caller_asserted_old_time)

    assert vendor_calls == []
    assert store.price_capture_attempt_events("formal", "2026-07-28") == []
    assert store.price_integrity_failure("formal")["reason_code"] \
        == "capture_deadline_expired"
    store.close()


@pytest.mark.unit
def test_formal_shadows_reuse_persisted_return_vector_and_resume(tmp_path, monkeypatch):
    from tradingagents import paper_trading

    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("formal", {
        "engine": "formal-global-v2", "protocol_id": "protocol-1",
        "tickers": ["A", "B"], "benchmark": "SPY",
        "cost_bps": 0.0, "slippage_bps": 0.0, "annual_borrow_bps": 0.0,
    }, 1.0)
    store.register_confirmatory_trial(
        "formal", 1.5, {"protocol_id": "protocol-1"}
    )
    weights = {
        "global_events_champion": {"A": 1.0, "B": 0.0},
        "shadow_a": {"A": 1.0, "B": 0.0},
        "shadow_b": {"A": 0.0, "B": 1.0},
    }
    for decision_date, entry_date in (
        ("2026-07-27", "2026-07-28"),
        ("2026-07-28", "2026-07-29"),
    ):
        store.conn.execute(
            "INSERT INTO paper_decision_bundles "
            "(run_id,decision_date,attempt_ordinal,created_utc,protocol_id,build_id,model_id,"
            "input_bundle_id,artifact_id,coverage_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "formal", decision_date, 1, 1.0, "protocol-1", "build-1", "model-1",
                f"input-{decision_date}", f"artifact-{decision_date}", "{}",
            ),
        )
        store.conn.execute(
            "INSERT INTO paper_targets "
            "(run_id,decision_date,entry_date,created_utc,weights_json) VALUES (?,?,?,?,?)",
            ("formal", decision_date, entry_date, 1.0,
             json.dumps(weights["global_events_champion"], sort_keys=True)),
        )
        for strategy_id, target_weights in weights.items():
            store.conn.execute(
                "INSERT INTO paper_strategy_targets "
                "(run_id,decision_date,strategy_id,entry_date,created_utc,"
                "weights_json,diagnostics_json) VALUES (?,?,?,?,?,?,?)",
                ("formal", decision_date, strategy_id, entry_date, 1.0,
                 json.dumps(target_weights, sort_keys=True), "{}"),
            )
    store.conn.commit()

    opens = {
        "2026-07-28": {"A": 100.0, "B": 50.0, "SPY": 400.0},
        "2026-07-29": {"A": 110.0, "B": 45.0, "SPY": 404.0},
    }

    clock, snapshot_calls = _install_formal_price_fakes(
        monkeypatch, paper_trading, opens
    )
    monkeypatch.setattr(paper_trading, "_cash_return_component", lambda *_: {
        "instrument": "USD", "annual_yield_proxy": "^IRX",
        "observation_session": "2026-07-27", "annual_yield_percent": 3.6,
        "accrual_days": 1, "day_count_basis": 360, "open_return": 0.0001,
    })
    first_capture = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc).timestamp()
    clock["value"] = first_capture
    first = mark_next(store, "formal")
    assert first.get("return_vector_id") is None
    assert store.price_capture_batch("formal", "2026-07-28")["paper_build_id"] \
        == "build_" + "a" * 24
    assert len(mark_formal_strategies(store, "formal", first)) == 3

    second_capture = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc).timestamp()
    clock["value"] = second_capture
    second = mark_next(store, "formal")
    assert [call[0] for call in snapshot_calls] == [
        "A", "B", "SPY", "A", "B", "SPY"
    ]
    vector = store.return_vector_for_session(
        "formal", "2026-07-29", ["A", "B", "SPY"]
    )
    assert vector["return_vector_id"] == second["return_vector_id"]

    # Simulate a crash after one shadow insert. A new call receives only the
    # champion row, authenticates the stored vector, skips the completed row,
    # and finishes without touching the vendor again.
    original_record = store.record_strategy_mark
    writes = 0

    def fail_after_one(run_id, strategy_id, mark):
        nonlocal writes
        if writes == 1:
            raise RuntimeError("worker interrupted")
        writes += 1
        original_record(run_id, strategy_id, mark)

    monkeypatch.setattr(store, "record_strategy_mark", fail_after_one)
    with pytest.raises(RuntimeError, match="interrupted"):
        mark_formal_strategies(store, "formal", store.latest_mark("formal"))
    monkeypatch.setattr(store, "record_strategy_mark", original_record)
    resumed = mark_formal_strategies(store, "formal", store.latest_mark("formal"))
    assert len(resumed) == 2
    assert {row["return_vector_id"] for row in resumed} == {second["return_vector_id"]}
    assert len(snapshot_calls) == 6
    assert mark_formal_strategies(store, "formal", store.latest_mark("formal")) == []
    assert store.latest_strategy_mark("formal", "shadow_a")["period_return"] \
        == pytest.approx(0.10)
    assert store.latest_strategy_mark("formal", "shadow_b")["period_return"] \
        == pytest.approx(-0.10)
    store.close()


@pytest.mark.unit
def test_missing_formal_decision_is_sealed_as_synchronized_itt_carry_forward(
    tmp_path, monkeypatch
):
    from tradingagents import paper_trading

    store = PaperStore(str(tmp_path / "paper.db"))
    store.create_run("formal", {
        "engine": "formal-global-v2", "protocol_id": "protocol-1",
        "tickers": ["A", "B"], "benchmark": "SPY",
        "cost_bps": 0.0, "slippage_bps": 0.0, "annual_borrow_bps": 0.0,
    }, 1.0)
    store.register_confirmatory_trial(
        "formal", 1.5, {"protocol_id": "protocol-1"}
    )
    store.conn.execute(
        "INSERT INTO paper_decision_bundles "
        "(run_id,decision_date,attempt_ordinal,created_utc,protocol_id,build_id,model_id,"
        "input_bundle_id,artifact_id,coverage_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "formal", "2026-07-27", 1, 2.0, "protocol-1", "build-1", "model-1",
            "input-1", "artifact-1", "{}",
        ),
    )
    store.conn.execute(
        "INSERT INTO paper_targets "
        "(run_id,decision_date,entry_date,created_utc,weights_json) VALUES (?,?,?,?,?)",
        ("formal", "2026-07-27", "2026-07-28", 2.0, '{"A":1.0,"B":0.0}'),
    )
    for strategy_id, weights in {
        "global_events_champion": '{"A":1.0,"B":0.0}',
        "equal_weight": '{"A":0.5,"B":0.5}',
    }.items():
        store.conn.execute(
            "INSERT INTO paper_strategy_targets "
            "(run_id,decision_date,strategy_id,entry_date,created_utc,"
            "weights_json,diagnostics_json) VALUES (?,?,?,?,?,?,?)",
            (
                "formal", "2026-07-27", strategy_id, "2026-07-28", 2.0,
                weights, "{}",
            ),
        )
    store.conn.commit()

    opens = {
        "2026-07-28": {"A": 100.0, "B": 100.0, "SPY": 400.0},
        "2026-07-29": {"A": 110.0, "B": 90.0, "SPY": 404.0},
        "2026-07-30": {"A": 121.0, "B": 81.0, "SPY": 408.0},
    }

    clock, _snapshot_calls = _install_formal_price_fakes(
        monkeypatch, paper_trading, opens
    )
    monkeypatch.setattr(paper_trading, "_cash_return_component", lambda *_: {
        "instrument": "USD", "annual_yield_proxy": "^IRX",
        "observation_session": "2026-07-27", "annual_yield_percent": 3.6,
        "accrual_days": 1, "day_count_basis": 360, "open_return": 0.0001,
    })

    marks = []
    for session_date in ("2026-07-28", "2026-07-29", "2026-07-30"):
        captured = datetime.fromisoformat(
            f"{session_date}T15:00:00+00:00"
        ).timestamp()
        clock["value"] = captured
        mark = mark_next(store, "formal")
        marks.append(mark)
        assert len(mark_formal_strategies(store, "formal", mark)) == 2

    assert marks[1]["target_decision_date"] is None
    assert marks[1]["turnover"] == 0.0
    assert marks[1]["trading_cost"] == 0.0
    first = store.interval_assignment_for_session("formal", "2026-07-29")
    missed = store.interval_assignment_for_session("formal", "2026-07-30")
    assert first["interval_index"] == 1
    assert first["disposition"] == "target_applied"
    assert first["scheduled_decision_date"] == "2026-07-27"
    assert first["applied_target_decision_date"] == "2026-07-27"
    assert missed["interval_index"] == 2
    assert missed["from_session_date"] == "2026-07-29"
    assert missed["scheduled_decision_date"] == "2026-07-28"
    assert missed["disposition"] == "carry_forward_missing_decision"
    assert missed["applied_target_decision_date"] is None
    assert missed["return_vector_id"] == marks[2]["return_vector_id"]

    counts = store.formal_trial_counts("formal")
    assert counts["completed_intervals"] == 2
    assert counts["successful_decision_sets"] == 1
    assert counts["carry_forward_intervals"] == 1
    assert counts["assignment_indices_contiguous"] is True
    assert counts["assignment_dates_contiguous"] is True
    assert store.status("formal")["itt_provenance"] == counts
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute(
            "UPDATE paper_interval_assignments SET disposition='target_applied'"
        )
    store.conn.rollback()
    store.close()


@pytest.mark.unit
def test_decision_window_is_after_cutoff_and_before_next_open():
    pytest.importorskip("exchange_calendars")
    cutoff, next_open, entry_date = decision_window("2026-07-27")
    assert cutoff == datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc)
    assert next_open == datetime(2026, 7, 28, 13, 30, tzinfo=timezone.utc)
    assert entry_date == "2026-07-28"
    assert current_decision_date(
        datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)
    ) == "2026-07-27"


@pytest.mark.unit
def test_formal_operation_lock_is_reentrant_in_one_thread(tmp_path):
    db_path = str(tmp_path / "nested.db")
    entered = []

    with formal_operation_lock(db_path, "run-1"):
        entered.append("outer")
        with formal_operation_lock(db_path, "run-1"):
            entered.append("inner")

    assert entered == ["outer", "inner"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "start_method",
    [
        method
        for method in ("spawn", "fork")
        if method in multiprocessing.get_all_start_methods()
    ],
)
def test_sqlite_formal_operation_lock_serializes_processes(tmp_path, start_method):
    db_path = str(tmp_path / "process-lock.db")
    context = multiprocessing.get_context(start_method)
    started = context.Event()
    acquired = context.Event()
    release = context.Event()

    with formal_operation_lock(db_path, "run-1"):
        process = context.Process(
            target=_acquire_formal_lock_in_child,
            args=(db_path, "run-1", started, acquired, release),
        )
        process.start()
        assert started.wait(10)
        assert not acquired.wait(0.25)

    assert acquired.wait(10)
    release.set()
    process.join(10)
    if process.is_alive():
        process.terminate()
        process.join(5)
    assert process.exitcode == 0


@pytest.mark.unit
def test_postgres_formal_operation_lock_uses_one_autocommit_session(monkeypatch):
    import sqlalchemy

    calls = []

    class Connection:
        def execution_options(self, **options):
            calls.append(("options", options))
            return self

        def execute(self, statement, params):
            calls.append(("execute", str(statement), params))

        def close(self):
            calls.append(("close",))

    connection = Connection()

    class Engine:
        def connect(self):
            calls.append(("connect",))
            return connection

        def dispose(self):
            calls.append(("dispose",))

    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_args, **_kwargs: Engine())

    with _postgres_formal_operation_lock(
        "postgresql://paper@example.invalid/db", "run-1"
    ):
        calls.append(("body",))

    assert calls[1] == ("options", {"isolation_level": "AUTOCOMMIT"})
    executions = [call for call in calls if call[0] == "execute"]
    assert "pg_advisory_lock" in executions[0][1]
    assert "pg_advisory_unlock" in executions[1][1]
    assert executions[0][2] == executions[1][2] == {
        "lock_key": "tradingagents:formal-operation:run-1"
    }
    assert calls[-2:] == [("close",), ("dispose",)]


@pytest.mark.unit
def test_formal_entrypoints_hold_one_outer_operation_lock(monkeypatch):
    from tradingagents import formal_experiment, paper_trading

    events = []

    @contextmanager
    def tracked_lock(db_url, run_id):
        events.append(("enter", db_url, run_id))
        try:
            yield
        finally:
            events.append(("exit", db_url, run_id))

    monkeypatch.setattr(paper_trading, "formal_operation_lock", tracked_lock)
    monkeypatch.setattr(
        paper_trading,
        "_cycle_locked",
        lambda args, now: events.append(("cycle",)) or {"cycle": True},
    )
    args = SimpleNamespace(
        db="paper.db", run_id="run-1", engine="formal-global-v2"
    )
    assert paper_trading.cycle(args, None) == {"cycle": True}
    assert events == [
        ("enter", "paper.db", "run-1"),
        ("cycle",),
        ("exit", "paper.db", "run-1"),
    ]

    events.clear()
    monkeypatch.setattr(
        formal_experiment,
        "_decide_formal_locked",
        lambda args, now, clock=None: events.append(("decide",)) or {"decision": True},
    )
    assert formal_experiment.decide_formal(args) == {"decision": True}
    assert events == [
        ("enter", "paper.db", "run-1"),
        ("decide",),
        ("exit", "paper.db", "run-1"),
    ]

    events.clear()
    monkeypatch.setattr(
        paper_trading,
        "_mark_formal_once_locked",
        lambda store, run_id, captured: events.append(("mark",)) or {"mark": True},
    )
    fake_store = SimpleNamespace(url="paper.db")
    assert _mark_formal_once(fake_store, "run-1") == {"mark": True}
    assert events == [
        ("enter", "paper.db", "run-1"),
        ("mark",),
        ("exit", "paper.db", "run-1"),
    ]


@pytest.mark.unit
def test_weekend_still_maps_to_friday_decision_window():
    pytest.importorskip("exchange_calendars")
    assert current_decision_date(
        datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    ) == "2026-07-24"


@pytest.mark.unit
def test_daemon_runs_just_after_daily_data_cutoff():
    assert next_daemon_run(
        datetime(2026, 7, 27, 23, 0, tzinfo=timezone.utc)
    ) == datetime(2026, 7, 28, 0, 5, tzinfo=timezone.utc)
    assert next_daemon_run(
        datetime(2026, 7, 28, 0, 6, tzinfo=timezone.utc)
    ) == datetime(2026, 7, 29, 0, 5, tzinfo=timezone.utc)


@pytest.mark.unit
def test_worker_also_wakes_shortly_after_executable_open():
    pytest.importorskip("exchange_calendars")
    assert next_worker_run(
        datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    ) == datetime(2026, 7, 28, 13, 45, tzinfo=timezone.utc)
    # After today's open mark, the next evidence cutoff comes before tomorrow's open.
    assert next_worker_run(
        datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)
    ) == datetime(2026, 7, 29, 0, 5, tzinfo=timezone.utc)


@pytest.mark.unit
def test_combined_formal_cycle_fails_closed_even_when_decisions_are_paused(tmp_path):
    args = SimpleNamespace(
        db=str(tmp_path / "paper.db"),
        run_id="new-formal-run",
        engine="formal-global-v2",
        decisions_enabled=False,
    )

    with pytest.raises(ValueError, match="combined formal cycle is retired"):
        cycle(args, datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc))


@pytest.mark.unit
def test_paused_split_formal_cycles_make_no_provider_or_store_calls(monkeypatch):
    from tradingagents import formal_experiment, paper_trading

    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("paused worker attempted an external or store call")

    monkeypatch.setattr(formal_experiment, "decide_formal", forbidden)
    monkeypatch.setattr(paper_trading, "PaperStore", forbidden)
    decision_args = SimpleNamespace(
        db="unused",
        run_id="new-formal-run",
        engine="formal-global-v2",
        decisions_enabled=False,
    )
    marker_args = SimpleNamespace(
        db="unused",
        run_id="new-formal-run",
        engine="formal-global-v2",
        marks_enabled=False,
    )

    decision_result = paper_trading.decision_cycle(decision_args)
    marker_result = paper_trading.marker_cycle(marker_args)

    assert decision_result == {
        "run_id": "new-formal-run",
        "worker_role": "paper_decision",
        "decision_recorded": False,
        "paused": True,
    }
    assert marker_result == {
        "run_id": "new-formal-run",
        "worker_role": "paper_marker",
        "mark_recorded": False,
        "paused": True,
    }
    assert calls == []


@pytest.mark.unit
def test_split_decision_cycle_treats_an_existing_window_as_idempotent(monkeypatch):
    from tradingagents import formal_experiment, paper_trading

    monkeypatch.setattr(
        formal_experiment,
        "decide_formal",
        lambda _args, _now: {
            "decision_date": "2026-07-24",
            "entry_date": "2026-07-27",
            "protocol_id": "protocol-test",
            "already_recorded": True,
            "portfolio_outputs_withheld": True,
        },
    )
    args = SimpleNamespace(
        db="unused",
        run_id="formal-run",
        engine="formal-global-v2",
        decisions_enabled=True,
    )

    result = paper_trading.decision_cycle(
        args, datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    )

    assert result["decision_recorded"] is False
    assert result["already_recorded"] is True
    assert result["paused"] is False
    assert result["decision"]["decision_date"] == "2026-07-24"


@pytest.mark.unit
def test_split_worker_records_liveness_when_no_exchange_action_is_due(monkeypatch):
    from tradingagents import paper_trading

    heartbeats = []
    monkeypatch.setattr(
        paper_trading,
        "marker_cycle",
        lambda _args, _now: (_ for _ in ()).throw(
            paper_trading.DecisionWindowClosedError("next marker is not due")
        ),
    )
    monkeypatch.setattr(
        paper_trading,
        "_record_formal_worker_heartbeat",
        lambda _args, *, role, event_type: heartbeats.append((role, event_type)),
    )

    result = paper_trading._formal_worker_with_retries(
        SimpleNamespace(run_id="formal-run"),
        role="paper_marker",
        attempts=1,
        retry_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert result is None
    assert heartbeats == [("paper_marker", "success")]


@pytest.mark.unit
def test_split_formal_worker_flags_default_to_paused(monkeypatch):
    from tradingagents import paper_trading

    monkeypatch.delenv("PAPER_DECISIONS_ENABLED", raising=False)
    monkeypatch.delenv("PAPER_MARKS_ENABLED", raising=False)

    decision_parser = argparse.ArgumentParser()
    paper_trading._decision_arguments(decision_parser)
    decision_args = decision_parser.parse_args(
        ["--run-id", "formal-run", "--db", "paper.db", "--tickers", "AAPL"]
    )
    marker_parser = argparse.ArgumentParser()
    paper_trading._marker_arguments(marker_parser)
    marker_args = marker_parser.parse_args(
        ["--run-id", "formal-run", "--db", "paper.db"]
    )

    assert decision_args.decisions_enabled is False
    assert marker_args.marks_enabled is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("command", "pause_name"),
    [
        ("decision-release-material", "PAPER_DECISIONS_ENABLED"),
        ("marker-release-material", "PAPER_MARKS_ENABLED"),
    ],
)
@pytest.mark.parametrize("configured", (None, "true"))
def test_split_release_material_requires_explicit_action_pause(
    monkeypatch, capsys, command, pause_name, configured
):
    from tradingagents import paper_trading

    if configured is None:
        monkeypatch.delenv(pause_name, raising=False)
    else:
        monkeypatch.setenv(pause_name, configured)

    with pytest.raises(SystemExit):
        paper_trading.main(
            [
                command,
                "--run-id",
                "formal-run",
                "--db",
                "postgresql://example.invalid/formal",
                "--tickers",
                "AAPL",
            ]
        )

    assert f"{pause_name} must be explicitly false" in capsys.readouterr().err


@pytest.mark.unit
def test_forward_decision_manifest_accepts_paper_arguments(tmp_path, monkeypatch):
    pytest.importorskip("exchange_calendars")
    from tradingagents.dataflows import media_history
    from tradingagents.graph import trading_graph

    class FakeGraph:
        def __init__(self, **kwargs):
            self.curr_state = {}

        def propagate(self, ticker, decision_date):
            self.curr_state = {"final_trade_decision": f"Rating: Buy for {ticker}"}
            return {}, "Buy"

    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", FakeGraph)
    monkeypatch.setattr(
        media_history, "collected_window_fingerprint", lambda *args, **kwargs: "data-v1"
    )
    args = SimpleNamespace(
        run_id="paper-regression",
        db=str(tmp_path / "paper.db"),
        tickers="NVDA,MSFT",
        benchmark="SPY",
        analysts="market,social,news",
        replicates=1,
        portfolio_mode="long-only",
        gross_limit=1.0,
        max_weight=0.5,
        cost_bps=5.0,
        slippage_bps=5.0,
        annual_borrow_bps=300.0,
        results_dir=str(tmp_path / "results"),
        debug=False,
        global_topics_only=False,
    )

    result = decide(args, datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc))

    assert result["decision_date"] == "2026-07-27"
    assert result["decision_rows"] == 2
    assert result["weights"] == {"MSFT": 0.5, "NVDA": 0.5}


@pytest.mark.unit
def test_daemon_retries_transient_failure_and_records_success(monkeypatch):
    from tradingagents import paper_trading

    calls = {"cycles": 0, "heartbeats": []}

    def fake_cycle(args, now):
        calls["cycles"] += 1
        if calls["cycles"] < 3:
            raise RuntimeError("temporary provider failure")
        return {"decision_recorded": True}

    monkeypatch.setattr(paper_trading, "cycle", fake_cycle)
    monkeypatch.setattr(
        paper_trading,
        "_record_daemon_heartbeat",
        lambda db, key, captured: calls["heartbeats"].append(key),
    )

    result = _cycle_with_retries(
        SimpleNamespace(db="unused"), attempts=3, retry_seconds=0, sleep_fn=lambda _: None
    )

    assert result == {"decision_recorded": True}
    assert calls["cycles"] == 3
    assert calls["heartbeats"] == [
        "paper:last_failure_utc", "paper:last_failure_utc", "paper:last_success_utc"
    ]


@pytest.mark.unit
def test_daemon_retries_data_integrity_value_error_and_crashes_after_exhaustion(monkeypatch):
    from tradingagents import paper_trading

    heartbeats = []

    def bad_cycle(args, now):
        raise ValueError("bad NAV")

    monkeypatch.setattr(paper_trading, "cycle", bad_cycle)
    monkeypatch.setattr(
        paper_trading,
        "_record_daemon_heartbeat",
        lambda db, key, captured: heartbeats.append(key),
    )

    with pytest.raises(RuntimeError, match="failed after 2 attempts"):
        _cycle_with_retries(
            SimpleNamespace(db="unused"), attempts=2, retry_seconds=0, sleep_fn=lambda _: None
        )
    assert heartbeats == ["paper:last_failure_utc", "paper:last_failure_utc"]
