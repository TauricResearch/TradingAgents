"""Formal price capture migration identity, clock, and direct-write contracts."""

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from tradingagents import ops_cli
from tradingagents.dataflows.media_store import _normalize_pg_url
from tradingagents.paper_trading import (
    FORMAL_PRICE_ATTEMPT_FAILURE_REASON_CODES,
    FORMAL_PRICE_INTEGRITY_FAILURE_REASON_CODES,
    PaperStore,
    _build_formal_price_batch,
    _price_batch_identity_payload,
    _price_receipt_identity_payload,
    _return_vector_identity_payload,
    _vendor_snapshot_identity_payload,
    formal_price_capture_window,
)
from tradingagents.research_protocol import build_identity, canonical_json, content_id

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "008_formal_price_capture_integrity.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _function_source(sql: str, name: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\(\).*?"
        r"AS \$\$(.*?)\$\$;",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


@pytest.mark.unit
def test_price_migration_is_atomic_append_only_and_least_privilege(migration_sql):
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    for table in (
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
    ):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in migration_sql
        assert "require_formal_primary_run BEFORE INSERT ON public.%I" in migration_sql
    assert "'CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON public.%I '" in migration_sql
    assert "GRANT SELECT, INSERT ON TABLE" in migration_sql
    assert 'TO "tradingagents-paper"' in migration_sql
    assert "GRANT UPDATE" not in migration_sql
    assert "GRANT DELETE" not in migration_sql


@pytest.mark.unit
def test_database_recomputes_every_price_identity_and_exact_universe(migration_sql):
    for prefix, identity_column in (
        ("price_batch_", "capture_identity_json"),
        ("return_vector_", "return_vector_identity_json"),
        ("price_receipt_", "receipt_identity_json"),
        ("price_snapshot_", "vendor_snapshot_identity_json"),
    ):
        assert f"'{prefix}' || pg_catalog.substr(pg_catalog.encode(" in migration_sql
        assert f"NEW.{identity_column}, 'UTF8'" in migration_sql
    assert "manifest_universe IS DISTINCT FROM expected_universe" in migration_sql
    assert "formal price batch universe is not exact sorted-unique" in migration_sql
    assert "jsonb_array_elements_text(run_config -> 'tickers')" in migration_sql
    assert "SELECT run_config ->> 'benchmark'" in migration_sql
    assert "NEW.paper_build_id !~ '^build_[0-9a-f]{24}$'" in migration_sql
    assert "capture_identity ->> 'paper_build_id'" in migration_sql


@pytest.mark.unit
def test_action_cash_live_clock_and_atomic_completion_are_database_enforced(
    migration_sql,
):
    assert "NEW.observed_utc := EXTRACT(" in migration_sql
    assert "formal price attempt time is not server-current" in migration_sql
    assert "NEW.persisted_utc := EXTRACT(" in migration_sql
    assert "formal price batch was not persisted in its live window" in migration_sql
    assert "receipt action fields disagree with return vector" in migration_sql
    for field in ("current_adjusted_open", "current_raw_open", "cash_dividend", "split_ratio"):
        assert field in migration_sql
    assert "formal return vector cash component is malformed" in migration_sql
    assert "annual_yield_percent" in migration_sql
    assert "observation_session" in migration_sql
    assert "CREATE CONSTRAINT TRIGGER complete_formal_price_capture_batch" in migration_sql
    assert "DEFERRABLE INITIALLY DEFERRED" in migration_sql
    assert "did not atomically commit exact receipts" in migration_sql
    assert "did not atomically bind its champion mark" in migration_sql
    assert "validate_formal_mark_price_batch" in migration_sql


@pytest.mark.unit
def test_terminal_halt_covers_decision_attempts_and_reason_codes(migration_sql):
    activity = migration_sql.split("FOREACH table_name IN ARRAY ARRAY[", maxsplit=1)[1].split(
        "]", maxsplit=1
    )[0]
    assert "'paper_decision_attempt_events'" in activity
    assert "'paper_price_capture_attempt_events'" in activity
    assert "'paper_price_capture_batches'" in activity
    tokens = set(re.findall(r"'([a-z_]+)'", migration_sql))
    assert tokens >= FORMAL_PRICE_ATTEMPT_FAILURE_REASON_CODES
    assert tokens >= FORMAL_PRICE_INTEGRITY_FAILURE_REASON_CODES
    assert "missing_official_open" not in migration_sql


@pytest.mark.unit
def test_price_trigger_bodies_match_preflight_contract_hashes(migration_sql):
    for function_name, (
        expected_hash,
        expected_contract,
    ) in ops_cli._FORMAL_PRICE_CONTRACTS.items():
        assert (
            ops_cli._normalized_pg_prosrc_sha256(_function_source(migration_sql, function_name))
            == expected_hash
        )
        assert (
            f"COMMENT ON FUNCTION public.{function_name}() IS\n    '{expected_contract}';"
        ) in migration_sql


def _registered_run(admin: PaperStore, token: str) -> str:
    run_id = f"price-direct-{token}"
    protocol_id = f"protocol-price-direct-{token}"
    registration_id = f"registration-price-direct-{token}"
    admin.create_run(
        run_id,
        {
            "engine": "formal-global-v2",
            "protocol_id": protocol_id,
            "trial_registration_id": registration_id,
            "tickers": ["A"],
            "benchmark": "SPY",
            "cost_bps": 0.0,
            "slippage_bps": 0.0,
            "annual_borrow_bps": 0.0,
        },
        time.time(),
    )
    admin.register_confirmatory_trial(
        run_id,
        time.time(),
        {
            "protocol_id": protocol_id,
            "run_id": run_id,
            "registration_type": "confirmatory",
            "registration_id": registration_id,
            "outcomes_accessed_before_registration": False,
        },
    )
    return run_id


def _active_capture_session(now: datetime) -> tuple[str, float, float]:
    from tradingagents.paper_trading import _calendar

    calendar = _calendar()
    session = calendar.date_to_session(pd.Timestamp(now.date()), direction="previous")
    for _ in range(3):
        label = session.date().isoformat()
        scheduled, deadline = formal_price_capture_window(label)
        if scheduled <= now < deadline:
            return label, scheduled.timestamp(), deadline.timestamp()
        session = calendar.previous_session(session)
    pytest.skip("no active XNYS price-capture window for direct PostgreSQL test")


def _direct_price_batch(
    *,
    session: str,
    scheduled: float,
    started: float,
    completed: float,
    deadline: float,
) -> dict:
    from tradingagents.paper_trading import _calendar

    calendar = _calendar()
    previous = calendar.previous_session(pd.Timestamp(session)).date().isoformat()
    snapshots = []
    for ticker, offset in (("A", 0.0), ("SPY", 10.0)):
        rows = {}
        for row_session, raw_open in ((previous, 100.0 + offset), (session, 101.0 + offset)):
            rows[row_session] = {
                "session_date": row_session,
                "raw_open": raw_open,
                "close": raw_open,
                "adjusted_close": raw_open,
                "adjustment_factor": 1.0,
                "adjusted_open": raw_open,
                "dividend": 1.0 if ticker == "A" and row_session == session else 0.0,
                "split_ratio": 0.0,
            }
        snapshot_base = {
            "schema_version": 1,
            "provider": "yfinance",
            "requested_ticker": ticker,
            "from_session": previous,
            "to_session": session,
            "requested_utc": started + 0.01,
            "received_utc": started + 0.02,
            "rows": rows,
        }
        snapshots.append(
            {
                **snapshot_base,
                "vendor_snapshot_id": content_id(snapshot_base, prefix="price_snapshot_"),
            }
        )
    accrual_days = (datetime.fromisoformat(session) - datetime.fromisoformat(previous)).days
    annual_yield = 5.0
    cash_component = {
        "instrument": "USD",
        "annual_yield_proxy": "^IRX",
        "observation_session": (datetime.fromisoformat(previous) - pd.Timedelta(days=1))
        .date()
        .isoformat(),
        "annual_yield_percent": annual_yield,
        "accrual_days": accrual_days,
        "day_count_basis": 360,
        "open_return": annual_yield / 100.0 * accrual_days / 360.0,
    }
    return _build_formal_price_batch(
        symbols=["A", "SPY"],
        previous_session=previous,
        session_date=session,
        attempt_ordinal=1,
        scheduled_utc=scheduled,
        started_utc=started,
        completed_utc=completed,
        deadline_utc=deadline,
        vendor_snapshots=snapshots,
        cash_component=cash_component,
    )


def _rehash_direct_batch(batch: dict) -> None:
    vector = batch["return_vector"]
    vector["return_vector_id"] = content_id(
        _return_vector_identity_payload(vector), prefix="return_vector_"
    )
    batch["return_vector_id"] = vector["return_vector_id"]
    batch["capture_batch_id"] = content_id(
        _price_batch_identity_payload(batch), prefix="price_batch_"
    )
    for receipt in batch["receipts"]:
        component = vector["components"][receipt["ticker"]]
        receipt["capture_batch_id"] = batch["capture_batch_id"]
        receipt["return_vector"] = {
            "return_vector_id": vector["return_vector_id"],
            "schema_version": vector["schema_version"],
            "from_session": vector["from_session"],
            "to_session": vector["to_session"],
            "captured_utc": vector["captured_utc"],
            "scheduled_utc": vector["scheduled_utc"],
            "deadline_utc": vector["deadline_utc"],
            "vendor": vector["vendor"],
            "cash_component": vector["cash_component"],
            **component,
        }


def _insert_direct_batch(conn, run_id: str, batch: dict) -> None:
    payload = {
        key: value for key, value in batch.items() if key not in {"receipts", "return_vector"}
    }
    conn.execute(
        text(
            "INSERT INTO paper_price_capture_batches "
            "(run_id,session_date,capture_batch_id,attempt_ordinal,from_session_date,"
            "scheduled_utc,started_utc,completed_utc,deadline_utc,vendor,"
            "paper_build_id,return_vector_id,receipt_manifest_json,capture_identity_json,"
            "return_vector_identity_json,payload_json) VALUES "
            "(:run_id,:session_date,:capture_batch_id,:attempt_ordinal,"
            ":from_session_date,:scheduled_utc,:started_utc,:completed_utc,"
            ":deadline_utc,:vendor,:paper_build_id,:return_vector_id,"
            ":receipt_manifest_json,"
            ":capture_identity_json,:return_vector_identity_json,:payload_json)"
        ),
        {
            "run_id": run_id,
            **payload,
            "receipt_manifest_json": canonical_json(batch["receipt_manifest"]),
            "capture_identity_json": canonical_json(_price_batch_identity_payload(batch)),
            "return_vector_identity_json": canonical_json(
                _return_vector_identity_payload(batch["return_vector"])
            ),
            "payload_json": canonical_json(payload),
        },
    )


def _insert_direct_receipt(conn, run_id: str, receipt: dict) -> None:
    conn.execute(
        text(
            "INSERT INTO paper_price_receipts "
            "(run_id,session_date,ticker,captured_utc,vendor,raw_open,adjusted_open,"
            "dividend,split_ratio,capture_batch_id,price_receipt_id,"
            "vendor_snapshot_id,receipt_identity_json,vendor_snapshot_identity_json,"
            "payload_json) VALUES (:run_id,:session_date,:ticker,:captured_utc,:vendor,"
            ":raw_open,:adjusted_open,:dividend,:split_ratio,:capture_batch_id,"
            ":price_receipt_id,:vendor_snapshot_id,:receipt_identity_json,"
            ":vendor_snapshot_identity_json,:payload_json)"
        ),
        {
            "run_id": run_id,
            **receipt,
            "receipt_identity_json": canonical_json(_price_receipt_identity_payload(receipt)),
            "vendor_snapshot_identity_json": canonical_json(
                _vendor_snapshot_identity_payload(receipt["vendor_snapshot"])
            ),
            "payload_json": canonical_json(receipt),
        },
    )


def _start_direct_attempt(conn, run_id: str, session: str, started: float) -> None:
    conn.execute(
        text(
            "INSERT INTO paper_price_capture_attempt_events "
            "(run_id,session_date,attempt_ordinal,event_type,created_utc,reason_code) "
            "VALUES (:run_id,:session,1,'started',:started,NULL)"
        ),
        {"run_id": run_id, "session": session, "started": started},
    )


@pytest.mark.integration
def test_postgres_runtime_rejects_backdating_forgery_partial_batch_and_halt_bypass():
    admin_url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL")
    paper_url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_PAPER_URL")
    if not admin_url or not paper_url:
        pytest.skip("direct PostgreSQL URLs are not configured")
    admin = PaperStore(admin_url)
    paper_engine = create_engine(_normalize_pg_url(paper_url))
    token = uuid.uuid4().hex[:12]
    run_id = _registered_run(admin, token)
    session, scheduled, deadline = _active_capture_session(datetime.now(timezone.utc))

    with pytest.raises(Exception, match="server-current"), paper_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO paper_price_capture_attempt_events "
                "(run_id,session_date,attempt_ordinal,event_type,created_utc,reason_code) "
                "VALUES (:run_id,:session,1,'started',1.0,NULL)"
            ),
            {"run_id": run_id, "session": session},
        )

    started = time.time()
    with paper_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO paper_price_capture_attempt_events "
                "(run_id,session_date,attempt_ordinal,event_type,created_utc,reason_code) "
                "VALUES (:run_id,:session,1,'started',:started,NULL)"
            ),
            {"run_id": run_id, "session": session, "started": started},
        )
    manifest = [
        {
            "ticker": ticker,
            "price_receipt_id": f"price_receipt_{index:024x}",
            "vendor_snapshot_id": f"price_snapshot_{index:024x}",
        }
        for index, ticker in enumerate(("A", "SPY"), start=1)
    ]
    completed = time.time()
    base = {
        "schema_version": 1,
        "session_date": session,
        "from_session_date": None,
        "attempt_ordinal": 1,
        "scheduled_utc": scheduled,
        "started_utc": started,
        "completed_utc": completed,
        "deadline_utc": deadline,
        "vendor": "yfinance",
        "paper_build_id": build_identity(),
        "return_vector_id": None,
        "receipt_manifest": manifest,
    }

    def insert_batch(conn, capture_id, identity):
        conn.execute(
            text(
                "INSERT INTO paper_price_capture_batches "
                "(run_id,session_date,capture_batch_id,attempt_ordinal,from_session_date,"
                "scheduled_utc,started_utc,completed_utc,deadline_utc,vendor,"
                "paper_build_id,return_vector_id,receipt_manifest_json,"
                "capture_identity_json,"
                "return_vector_identity_json,payload_json) VALUES "
                "(:run_id,:session,:capture_id,1,NULL,:scheduled,:started,:completed,"
                ":deadline,'yfinance',:paper_build_id,NULL,:manifest,:identity,"
                "NULL,:payload)"
            ),
            {
                "run_id": run_id,
                "session": session,
                "capture_id": capture_id,
                "scheduled": scheduled,
                "started": started,
                "completed": completed,
                "deadline": deadline,
                "paper_build_id": identity["paper_build_id"],
                "manifest": canonical_json(identity["receipt_manifest"]),
                "identity": canonical_json(identity),
                "payload": canonical_json({"capture_batch_id": capture_id, **identity}),
            },
        )

    with pytest.raises(Exception, match="content-addressed"), paper_engine.begin() as conn:
        insert_batch(conn, "price_batch_" + "f" * 24, base)

    wrong_build = {**base, "paper_build_id": "caller-selected-release"}
    with pytest.raises(Exception, match="content-addressed"), paper_engine.begin() as conn:
        insert_batch(
            conn, content_id(wrong_build, prefix="price_batch_"), wrong_build
        )

    unsorted = {**base, "receipt_manifest": list(reversed(manifest))}
    with pytest.raises(Exception, match="sorted-unique"), paper_engine.begin() as conn:
        insert_batch(conn, content_id(unsorted, prefix="price_batch_"), unsorted)

    with (
        pytest.raises(Exception, match="atomically commit exact receipts"),
        paper_engine.begin() as conn,
    ):
        insert_batch(conn, content_id(base, prefix="price_batch_"), base)

    halted_run = _registered_run(admin, uuid.uuid4().hex[:12])
    detected = time.time()
    failure_base = {
        "schema_version": 1,
        "run_id": halted_run,
        "session_date": "2020-01-02",
        "detected_utc": detected,
        "scheduled_utc": detected - 120.0,
        "deadline_utc": detected - 60.0,
        "last_attempt_ordinal": 0,
        "reason_code": "capture_deadline_expired",
    }
    failure = {
        **failure_base,
        "failure_id": content_id(failure_base, prefix="price_failure_"),
    }
    with paper_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO paper_price_integrity_failures "
                "(run_id,session_date,failure_id,detected_utc,scheduled_utc,deadline_utc,"
                "last_attempt_ordinal,reason_code,payload_json) VALUES "
                "(:run_id,:session,:failure_id,:detected,:scheduled,:deadline,0,"
                "'capture_deadline_expired',:payload)"
            ),
            {
                "run_id": halted_run,
                "session": "2020-01-02",
                "failure_id": failure["failure_id"],
                "detected": detected,
                "scheduled": detected - 120.0,
                "deadline": detected - 60.0,
                "payload": canonical_json(failure),
            },
        )
    with pytest.raises(Exception, match="terminal price failure"), paper_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO paper_decision_attempt_events "
                "(run_id,decision_date,entry_date,attempt_ordinal,event_type,"
                "created_utc,reason_code) VALUES "
                "(:run_id,'2026-08-05','2026-08-06',1,'started',:created,NULL)"
            ),
            {"run_id": halted_run, "created": time.time()},
        )
    admin.close()
    paper_engine.dispose()


@pytest.mark.integration
def test_postgres_runtime_rejects_cash_arithmetic_and_action_field_tampering():
    admin_url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL")
    paper_url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_PAPER_URL")
    if not admin_url or not paper_url:
        pytest.skip("direct PostgreSQL URLs are not configured")
    admin = PaperStore(admin_url)
    paper_engine = create_engine(_normalize_pg_url(paper_url))
    session, scheduled, deadline = _active_capture_session(datetime.now(timezone.utc))
    try:
        cash_run = _registered_run(admin, uuid.uuid4().hex[:12])
        cash_started = time.time()
        cash_batch = _direct_price_batch(
            session=session,
            scheduled=scheduled,
            started=cash_started,
            completed=cash_started + 0.05,
            deadline=deadline,
        )
        cash_batch["return_vector"]["cash_component"]["open_return"] += 0.01
        _rehash_direct_batch(cash_batch)
        with paper_engine.begin() as conn:
            _start_direct_attempt(conn, cash_run, session, cash_started)
        with (
            pytest.raises(Exception, match="cash component is malformed"),
            paper_engine.begin() as conn,
        ):
            _insert_direct_batch(conn, cash_run, cash_batch)

        action_run = _registered_run(admin, uuid.uuid4().hex[:12])
        action_started = time.time()
        action_batch = _direct_price_batch(
            session=session,
            scheduled=scheduled,
            started=action_started,
            completed=action_started + 0.05,
            deadline=deadline,
        )
        action_batch["return_vector"]["components"]["A"]["cash_dividend"] = 0.0
        _rehash_direct_batch(action_batch)
        with paper_engine.begin() as conn:
            _start_direct_attempt(conn, action_run, session, action_started)
        with (
            pytest.raises(Exception, match="action fields disagree"),
            paper_engine.begin() as conn,
        ):
            _insert_direct_batch(conn, action_run, action_batch)
            receipt = next(item for item in action_batch["receipts"] if item["ticker"] == "A")
            _insert_direct_receipt(conn, action_run, receipt)
    finally:
        admin.close()
        paper_engine.dispose()
