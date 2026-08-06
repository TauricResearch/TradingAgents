"""Forward-only paper portfolio with immutable decisions and price marks."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from tradingagents import backtest
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.operations import emit_alert
from tradingagents.portfolio_backtest import rating_score, target_weights
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    build_identity,
    canonical_json,
    content_id,
)

logger = logging.getLogger(__name__)

_FORMAL_OPERATION_MUTEX_GUARD = threading.Lock()
_FORMAL_OPERATION_MUTEXES: dict[tuple[int, str, str], threading.RLock] = {}
_FORMAL_OPERATION_LOCAL = threading.local()
_BUILD_ID_PATTERN = re.compile(r"build_[0-9a-f]{24}")

CONFIRMATORY_TRIAL_LABEL = "confirmatory-trial"
FORMAL_ATTEMPT_FAILURE_REASON_CODES = frozenset(
    {
        "configuration_failed",
        "coverage_gate_failed",
        "decision_window_expired",
        "llm_failed",
        "market_data_failed",
        "persistence_failed",
        "target_construction_failed",
        "unexpected_failure",
    }
)
FORMAL_INTERVAL_DISPOSITIONS = frozenset(
    {
        "target_applied",
        "carry_forward_missing_decision",
    }
)
FORMAL_PRICE_ATTEMPT_FAILURE_REASON_CODES = frozenset(
    {
        "market_data_failed",
        "capture_window_expired",
        "persistence_failed",
        "unexpected_failure",
    }
)
FORMAL_PRICE_INTEGRITY_FAILURE_REASON_CODES = frozenset(
    {
        "capture_deadline_expired",
        "capture_crossed_deadline",
        "missing_provider_daily_open",
        "unsupported_corporate_action",
        "invalid_vendor_snapshot",
    }
)
FORMAL_HOLDING_INTERVALS = int(
    GLOBAL_EVENT_V2_PROTOCOL["analysis"]["trial_clock"]["holding_intervals"]
)
_LLM_RESERVATION_SPEC_FIELDS = frozenset(
    {
        "scope",
        "run_id",
        "decision_date",
        "stage",
        "provider",
        "requested_model",
        "input_bundle_id",
        "prompt_id",
        "prompt_bytes",
        "max_prompt_bytes",
        "max_completion_tokens",
    }
)
_LLM_INVOCATION_IDENTITY_FIELDS = (
    "scope",
    "run_id",
    "decision_date",
    "ordinal",
    "stage",
    "provider",
    "requested_model",
    "input_bundle_id",
)


class DecisionWindowClosedError(ValueError):
    """Expected control flow when it is unsafe to freeze a new decision."""


class FormalPriceIntegrityError(ValueError):
    """The primary trial can no longer obtain a protocol-valid price capture."""


class FormalPriceCaptureError(RuntimeError):
    """A retryable formal price-adapter or persistence failure."""


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _formal_operation_mutex(identity: tuple[int, str, str]) -> threading.RLock:
    with _FORMAL_OPERATION_MUTEX_GUARD:
        return _FORMAL_OPERATION_MUTEXES.setdefault(identity, threading.RLock())


@contextmanager
def _sqlite_formal_operation_lock(db_url: str, run_id: str):
    """Hold an OS-backed lock without keeping a SQLite transaction open."""
    raw = db_url[len("sqlite:///") :] if db_url.startswith("sqlite:///") else db_url
    database_path = Path(raw).expanduser().resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    run_digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:24]
    lock_path = database_path.with_name(f".{database_path.name}.formal-operation-{run_digest}.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextmanager
def _postgres_formal_operation_lock(db_url: str, run_id: str):
    """Hold a session advisory lock on a dedicated autocommit connection."""
    from sqlalchemy import create_engine, text

    from tradingagents.dataflows.media_store import _normalize_pg_url

    engine = create_engine(_normalize_pg_url(db_url), pool_pre_ping=True)
    connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    lock_key = f"tradingagents:formal-operation:{run_id}"
    try:
        connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                {"lock_key": lock_key},
            )
    finally:
        connection.close()
        engine.dispose()


@contextmanager
def formal_operation_lock(db_url: str, run_id: str):
    """Serialize one complete formal operation across threads and processes.

    Nested formal helpers in the same thread reuse the outer lock. PostgreSQL
    uses a session advisory lock, not a transaction lock, so provider latency
    never leaves a database transaction open.
    """
    if not isinstance(db_url, str) or not db_url.strip():
        raise ValueError("formal operation database URL must be non-empty")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("formal operation run ID must be non-empty")
    db_url = db_url.strip()
    run_id = run_id.strip()
    identity = (
        os.getpid(),
        hashlib.sha256(db_url.encode("utf-8")).hexdigest(),
        run_id,
    )
    active = getattr(_FORMAL_OPERATION_LOCAL, "active", set())
    if identity in active:
        yield
        return
    mutex = _formal_operation_mutex(identity)
    with mutex:
        active = set(getattr(_FORMAL_OPERATION_LOCAL, "active", set()))
        active.add(identity)
        _FORMAL_OPERATION_LOCAL.active = active
        try:
            is_sqlite = db_url.startswith("sqlite:///") or "://" not in db_url
            lock = (
                _sqlite_formal_operation_lock(db_url, run_id)
                if is_sqlite
                else _postgres_formal_operation_lock(db_url, run_id)
            )
            with lock:
                yield
        finally:
            active = set(getattr(_FORMAL_OPERATION_LOCAL, "active", set()))
            active.discard(identity)
            _FORMAL_OPERATION_LOCAL.active = active


class PaperStore:
    """Small SQLite/Postgres ledger; all decision and mark rows are append-only."""

    _DDL = (
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            component TEXT NOT NULL, version INTEGER NOT NULL,
            applied_utc DOUBLE PRECISION NOT NULL, PRIMARY KEY (component,version)
        )""",
        """CREATE TABLE IF NOT EXISTS poll_state (
            key TEXT PRIMARY KEY, value DOUBLE PRECISION NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS formal_llm_budget_counters (
            counter_key TEXT PRIMARY KEY, scope TEXT NOT NULL,
            protocol_id TEXT NOT NULL, run_id TEXT NOT NULL,
            counter_kind TEXT NOT NULL, bucket_date DATE NOT NULL,
            reserved_calls INTEGER NOT NULL, frozen_limit INTEGER NOT NULL,
            first_reserved_utc DOUBLE PRECISION NOT NULL,
            last_reserved_utc DOUBLE PRECISION NOT NULL,
            CHECK (counter_kind IN ('decision','utc_day')),
            CHECK (reserved_calls > 0),
            CHECK (frozen_limit > 0),
            CHECK (reserved_calls <= frozen_limit),
            UNIQUE (scope,protocol_id,run_id,counter_kind,bucket_date)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_runs (
            run_id TEXT PRIMARY KEY, created_utc DOUBLE PRECISION NOT NULL,
            config_json TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS paper_decisions (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, ticker TEXT NOT NULL,
            replicate INTEGER NOT NULL, created_utc DOUBLE PRECISION NOT NULL,
            action TEXT NOT NULL, score DOUBLE PRECISION NOT NULL,
            data_fingerprint TEXT NOT NULL,
            signal_fingerprint TEXT NOT NULL, final_decision TEXT NOT NULL,
            PRIMARY KEY (run_id, decision_date, ticker, replicate)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_targets (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, entry_date TEXT NOT NULL,
            created_utc DOUBLE PRECISION NOT NULL, weights_json TEXT NOT NULL,
            PRIMARY KEY (run_id, decision_date)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_marks (
            run_id TEXT NOT NULL, session_date TEXT NOT NULL,
            captured_utc DOUBLE PRECISION NOT NULL,
            nav DOUBLE PRECISION NOT NULL, benchmark_nav DOUBLE PRECISION NOT NULL,
            period_return DOUBLE PRECISION NOT NULL,
            benchmark_period_return DOUBLE PRECISION NOT NULL,
            turnover DOUBLE PRECISION NOT NULL,
            trading_cost DOUBLE PRECISION NOT NULL, borrow_cost DOUBLE PRECISION NOT NULL,
            weights_json TEXT NOT NULL, opens_json TEXT NOT NULL,
            benchmark_open DOUBLE PRECISION NOT NULL, target_decision_date TEXT,
            PRIMARY KEY (run_id, session_date)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_paper_target_entry ON paper_targets (run_id, entry_date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_target_entry "
        "ON paper_targets (run_id, entry_date)",
        """CREATE TABLE IF NOT EXISTS experiment_registry (
            protocol_id TEXT PRIMARY KEY, created_utc DOUBLE PRECISION NOT NULL,
            manifest_json TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS formal_trial_registry (
            protocol_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
            registration_id TEXT NOT NULL UNIQUE,
            created_utc DOUBLE PRECISION NOT NULL, details_json TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS paper_run_labels (
            run_id TEXT NOT NULL, label TEXT NOT NULL,
            created_utc DOUBLE PRECISION NOT NULL,
            details_json TEXT NOT NULL, PRIMARY KEY (run_id,label)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_artifacts (
            artifact_id TEXT PRIMARY KEY, created_utc DOUBLE PRECISION NOT NULL,
            artifact_type TEXT NOT NULL, content_json TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS paper_decision_bundles (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL,
            attempt_ordinal INTEGER NOT NULL,
            created_utc DOUBLE PRECISION NOT NULL, protocol_id TEXT NOT NULL,
            build_id TEXT NOT NULL, model_id TEXT NOT NULL,
            input_bundle_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
            coverage_json TEXT NOT NULL,
            PRIMARY KEY (run_id,decision_date),
            CHECK (attempt_ordinal > 0)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_events (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, event_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id,decision_date,event_id)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_forecasts (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, ticker TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id,decision_date,ticker)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_strategy_targets (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, strategy_id TEXT NOT NULL,
            entry_date TEXT NOT NULL, created_utc DOUBLE PRECISION NOT NULL,
            weights_json TEXT NOT NULL, diagnostics_json TEXT NOT NULL,
            PRIMARY KEY (run_id,decision_date,strategy_id)
        )""",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_target_entry "
        "ON paper_strategy_targets (run_id,strategy_id,entry_date)",
        """CREATE TABLE IF NOT EXISTS paper_strategy_marks (
            run_id TEXT NOT NULL, strategy_id TEXT NOT NULL,
            session_date TEXT NOT NULL, captured_utc DOUBLE PRECISION NOT NULL,
            nav DOUBLE PRECISION NOT NULL, benchmark_nav DOUBLE PRECISION NOT NULL,
            period_return DOUBLE PRECISION NOT NULL,
            benchmark_period_return DOUBLE PRECISION NOT NULL,
            turnover DOUBLE PRECISION NOT NULL, trading_cost DOUBLE PRECISION NOT NULL,
            borrow_cost DOUBLE PRECISION NOT NULL, weights_json TEXT NOT NULL,
            opens_json TEXT NOT NULL, benchmark_open DOUBLE PRECISION NOT NULL,
            target_decision_date TEXT,
            PRIMARY KEY (run_id,strategy_id,session_date)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_price_capture_attempt_events (
            run_id TEXT NOT NULL, session_date TEXT NOT NULL,
            attempt_ordinal INTEGER NOT NULL, event_type TEXT NOT NULL,
            created_utc DOUBLE PRECISION NOT NULL, observed_utc DOUBLE PRECISION,
            reason_code TEXT,
            PRIMARY KEY (run_id,session_date,attempt_ordinal,event_type),
            CHECK (attempt_ordinal > 0),
            CHECK (event_type IN ('started','failed')),
            CHECK (
                (event_type = 'started' AND reason_code IS NULL)
                OR (event_type = 'failed' AND reason_code IN (
                    'market_data_failed','capture_window_expired',
                    'persistence_failed','unexpected_failure'
                ))
            )
        )""",
        """CREATE TABLE IF NOT EXISTS paper_price_capture_batches (
            run_id TEXT NOT NULL, session_date TEXT NOT NULL,
            capture_batch_id TEXT NOT NULL UNIQUE, attempt_ordinal INTEGER NOT NULL,
            from_session_date TEXT, scheduled_utc DOUBLE PRECISION NOT NULL,
            started_utc DOUBLE PRECISION NOT NULL,
            completed_utc DOUBLE PRECISION NOT NULL,
            persisted_utc DOUBLE PRECISION,
            deadline_utc DOUBLE PRECISION NOT NULL, vendor TEXT NOT NULL,
            paper_build_id TEXT NOT NULL,
            return_vector_id TEXT, receipt_manifest_json TEXT NOT NULL,
            capture_identity_json TEXT NOT NULL,
            return_vector_identity_json TEXT,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id,session_date),
            CHECK (attempt_ordinal > 0),
            CHECK (scheduled_utc <= started_utc),
            CHECK (started_utc <= completed_utc),
            CHECK (completed_utc < deadline_utc)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_price_integrity_failures (
            run_id TEXT NOT NULL, session_date TEXT NOT NULL,
            failure_id TEXT NOT NULL UNIQUE, detected_utc DOUBLE PRECISION NOT NULL,
            scheduled_utc DOUBLE PRECISION NOT NULL,
            deadline_utc DOUBLE PRECISION NOT NULL,
            last_attempt_ordinal INTEGER NOT NULL, reason_code TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id,session_date),
            UNIQUE (run_id),
            CHECK (last_attempt_ordinal >= 0),
            CHECK (detected_utc >= deadline_utc),
            CHECK (reason_code IN (
                'capture_deadline_expired','capture_crossed_deadline',
                'missing_provider_daily_open','unsupported_corporate_action',
                'invalid_vendor_snapshot'
            ))
        )""",
        """CREATE TABLE IF NOT EXISTS paper_price_receipts (
            run_id TEXT NOT NULL, session_date TEXT NOT NULL, ticker TEXT NOT NULL,
            captured_utc DOUBLE PRECISION NOT NULL, vendor TEXT NOT NULL,
            raw_open DOUBLE PRECISION NOT NULL, adjusted_open DOUBLE PRECISION NOT NULL,
            dividend DOUBLE PRECISION NOT NULL, split_ratio DOUBLE PRECISION NOT NULL,
            capture_batch_id TEXT, price_receipt_id TEXT, vendor_snapshot_id TEXT,
            receipt_identity_json TEXT, vendor_snapshot_identity_json TEXT,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id,session_date,ticker)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_decision_attempt_events (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, entry_date TEXT NOT NULL,
            attempt_ordinal INTEGER NOT NULL, event_type TEXT NOT NULL,
            created_utc DOUBLE PRECISION NOT NULL, reason_code TEXT,
            PRIMARY KEY (run_id,decision_date,attempt_ordinal,event_type),
            CHECK (attempt_ordinal > 0),
            CHECK (event_type IN ('started','failed')),
            CHECK (
                (event_type = 'started' AND reason_code IS NULL)
                OR (event_type = 'failed' AND reason_code IN (
                    'configuration_failed','coverage_gate_failed',
                    'decision_window_expired','llm_failed','market_data_failed',
                    'persistence_failed','target_construction_failed',
                    'unexpected_failure'
                ))
            )
        )""",
        """CREATE TABLE IF NOT EXISTS paper_interval_assignments (
            run_id TEXT NOT NULL, interval_index INTEGER NOT NULL,
            from_session_date TEXT NOT NULL, session_date TEXT NOT NULL,
            scheduled_decision_date TEXT NOT NULL,
            created_utc DOUBLE PRECISION NOT NULL,
            disposition TEXT NOT NULL, applied_target_decision_date TEXT,
            return_vector_id TEXT NOT NULL,
            PRIMARY KEY (run_id,interval_index),
            UNIQUE (run_id,session_date),
            CHECK (interval_index > 0 AND interval_index <= 252),
            CHECK (disposition IN (
                'target_applied','carry_forward_missing_decision'
            )),
            CHECK (
                (disposition = 'target_applied'
                    AND applied_target_decision_date IS NOT NULL)
                OR (disposition = 'carry_forward_missing_decision'
                    AND applied_target_decision_date IS NULL)
            )
        )""",
    )

    _IMMUTABLE_TABLES = (
        "paper_decisions",
        "paper_targets",
        "paper_marks",
        "experiment_registry",
        "formal_trial_registry",
        "paper_run_labels",
        "paper_artifacts",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_strategy_targets",
        "paper_strategy_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_decision_attempt_events",
        "paper_interval_assignments",
    )
    _TRIAL_ACTIVITY_TABLES = (
        "paper_decisions",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_targets",
        "paper_strategy_targets",
        "paper_marks",
        "paper_strategy_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_decision_attempt_events",
        "paper_interval_assignments",
    )

    def __init__(self, url: str, *, auto_migrate: bool | None = None):
        if not url:
            raise ValueError("paper ledger database URL is required")
        self.url = url
        self._sqlite = False
        self._media_store = None
        self._formal_runtime_contexts: dict[tuple[str, str], dict] = {}
        if url.startswith("sqlite:///") or "://" not in url:
            raw = url[len("sqlite:///") :] if url.startswith("sqlite:///") else url
            path = Path(raw).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path))
            self.conn.row_factory = sqlite3.Row
            self._sqlite = True
            for statement in self._DDL:
                self.conn.execute(statement)
            self._ensure_price_capture_columns()
            self.conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (component,version,applied_utc) "
                "VALUES ('paper',2,?)",
                (datetime.now(timezone.utc).timestamp(),),
            )
            self._install_immutability()
            self._install_formal_registration_guards()
            self.conn.commit()
        else:
            from sqlalchemy import create_engine

            from tradingagents.dataflows.media_store import _normalize_pg_url

            self.engine = create_engine(_normalize_pg_url(url), pool_pre_ping=True)
            migrations_enabled = (
                os.getenv("PAPER_AUTO_MIGRATE", "true").lower()
                in {"1", "true", "yes", "on"}
                if auto_migrate is None
                else bool(auto_migrate)
            )
            if migrations_enabled:
                with self.engine.begin() as conn:
                    for statement in self._DDL:
                        conn.exec_driver_sql(statement)
                    for column in (
                        "capture_batch_id TEXT",
                        "price_receipt_id TEXT",
                        "vendor_snapshot_id TEXT",
                        "receipt_identity_json TEXT",
                        "vendor_snapshot_identity_json TEXT",
                    ):
                        conn.exec_driver_sql(
                            "ALTER TABLE public.paper_price_receipts "
                            f"ADD COLUMN IF NOT EXISTS {column}"
                        )
                    for column in (
                        "capture_identity_json TEXT",
                        "return_vector_identity_json TEXT",
                        "persisted_utc DOUBLE PRECISION",
                        "paper_build_id TEXT",
                    ):
                        conn.exec_driver_sql(
                            "ALTER TABLE public.paper_price_capture_batches "
                            f"ADD COLUMN IF NOT EXISTS {column}"
                        )
                    conn.exec_driver_sql(
                        "ALTER TABLE public.paper_price_capture_attempt_events "
                        "ADD COLUMN IF NOT EXISTS observed_utc DOUBLE PRECISION"
                    )
                    conn.exec_driver_sql(
                        "INSERT INTO schema_migrations (component,version,applied_utc) "
                        "VALUES ('paper',2,%s) ON CONFLICT (component,version) DO NOTHING",
                        (datetime.now(timezone.utc).timestamp(),),
                    )
                self._install_immutability()
                self._install_formal_registration_guards()

    def _ensure_price_capture_columns(self) -> None:
        """Upgrade pre-contract SQLite fixtures without rewriting immutable rows."""
        if not self._sqlite:
            return
        receipt_columns = {
            str(row[1]) for row in self.conn.execute("PRAGMA table_info(paper_price_receipts)")
        }
        for name in (
            "capture_batch_id",
            "price_receipt_id",
            "vendor_snapshot_id",
            "receipt_identity_json",
            "vendor_snapshot_identity_json",
        ):
            if name not in receipt_columns:
                self.conn.execute(f"ALTER TABLE paper_price_receipts ADD COLUMN {name} TEXT")
        batch_columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(paper_price_capture_batches)")
        }
        for name in (
            "capture_identity_json",
            "return_vector_identity_json",
            "persisted_utc",
            "paper_build_id",
        ):
            if name not in batch_columns:
                self.conn.execute(
                    "ALTER TABLE paper_price_capture_batches ADD COLUMN "
                    f"{name} {'DOUBLE PRECISION' if name == 'persisted_utc' else 'TEXT'}"
                )
        attempt_columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(paper_price_capture_attempt_events)")
        }
        if "observed_utc" not in attempt_columns:
            self.conn.execute(
                "ALTER TABLE paper_price_capture_attempt_events "
                "ADD COLUMN observed_utc DOUBLE PRECISION"
            )

    def _install_immutability(self) -> None:
        """Enforce append-only evidence at the database layer, not by convention."""
        if self._sqlite:
            for table in self._IMMUTABLE_TABLES:
                for operation in ("UPDATE", "DELETE"):
                    name = f"immutable_{table}_{operation.lower()}"
                    self.conn.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {operation} ON {table} "
                        "BEGIN SELECT RAISE(ABORT, 'append-only table'); END"
                    )
            return
        # Keep the stored ``prosrc`` byte-for-byte aligned with migrations 004/005.
        # ``%%`` is reduced to the intended single PL/pgSQL percent placeholder
        # by psycopg's DBAPI interpolation layer.
        function_sql = """
CREATE OR REPLACE FUNCTION public.reject_append_only_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %% cannot be mutated', TG_TABLE_NAME
        USING ERRCODE = '55000';
END
$$
"""
        with self.engine.begin() as conn:
            conn.exec_driver_sql(function_sql)
            conn.exec_driver_sql(
                "COMMENT ON FUNCTION public.reject_append_only_mutation() IS "
                "'tradingagents.append-only.v1'"
            )
            for table in self._IMMUTABLE_TABLES:
                trigger = f"immutable_{table}"
                conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger} ON public.{table}")
                conn.exec_driver_sql(
                    f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON public.{table} "
                    "FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation()"
                )

    def _install_formal_registration_guards(self) -> None:
        """Install the bootstrap guard without replacing migration 005's contract."""
        if self._sqlite:
            self.conn.execute(
                "CREATE TRIGGER IF NOT EXISTS guard_confirmatory_run_label "
                "BEFORE INSERT ON paper_run_labels "
                f"WHEN NEW.label='{CONFIRMATORY_TRIAL_LABEL}' "
                "BEGIN SELECT CASE WHEN NOT EXISTS ("
                "SELECT 1 FROM formal_trial_registry AS registry "
                "WHERE registry.run_id=NEW.run_id "
                "AND registry.details_json=NEW.details_json "
                "AND registry.created_utc=NEW.created_utc"
                ") THEN RAISE(ABORT, 'confirmatory label requires primary registry') "
                "END; END"
            )
            return
        function_sql = f"""
            CREATE OR REPLACE FUNCTION public.enforce_confirmatory_run_label()
            RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
            BEGIN
                IF NEW.label = '{CONFIRMATORY_TRIAL_LABEL}' AND NOT EXISTS (
                    SELECT 1 FROM public.formal_trial_registry AS registry
                    WHERE registry.run_id = NEW.run_id
                      AND registry.details_json = NEW.details_json
                      AND registry.created_utc = NEW.created_utc
                ) THEN
                    RAISE EXCEPTION 'confirmatory label requires primary registry'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
        """
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "SELECT pg_advisory_xact_lock(hashtextextended("
                "'tradingagents:formal-registration-bootstrap', 0))"
            )
            migrated_guard_exists = conn.exec_driver_sql(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_catalog.pg_trigger AS trigger "
                "JOIN pg_catalog.pg_class AS table_class "
                "ON table_class.oid=trigger.tgrelid "
                "JOIN pg_catalog.pg_namespace AS table_namespace "
                "ON table_namespace.oid=table_class.relnamespace "
                "WHERE table_namespace.nspname='public' "
                "AND table_class.relname='paper_run_labels' "
                "AND trigger.tgname='guard_confirmatory_run_label' "
                "AND NOT trigger.tgisinternal)"
            ).scalar_one()
            if migrated_guard_exists:
                return
            conn.exec_driver_sql(function_sql)
            conn.exec_driver_sql(
                "DROP TRIGGER IF EXISTS guard_confirmatory_run_label ON public.paper_run_labels"
            )
            conn.exec_driver_sql(
                "CREATE TRIGGER guard_confirmatory_run_label "
                "BEFORE INSERT ON public.paper_run_labels FOR EACH ROW "
                "EXECUTE FUNCTION public.enforce_confirmatory_run_label()"
            )

    @contextmanager
    def _transaction(self, *, immediate: bool = False):
        if self._sqlite:
            try:
                if immediate:
                    self.conn.execute("BEGIN IMMEDIATE")
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        else:
            with self.engine.begin() as conn:
                yield conn

    @contextmanager
    def _trial_lifecycle_transaction(self, run_id: str):
        """Serialize trial registration against target and outcome writes."""
        with self._transaction(immediate=True) as conn:
            if not self._sqlite:
                self._execute(
                    conn,
                    "SELECT pg_advisory_xact_lock(hashtext(:lock_key))",
                    {"lock_key": f"tradingagents:paper-trial:{run_id}"},
                )
            yield conn

    @contextmanager
    def _protocol_registration_transaction(self, protocol_id: str, run_id: str):
        """Serialize primary registration across every run of one protocol."""
        with self._transaction(immediate=True) as conn:
            if not self._sqlite:
                self._execute(
                    conn,
                    "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))",
                    {"lock_key": f"tradingagents:formal-protocol:{protocol_id}"},
                )
                self._execute(
                    conn,
                    "SELECT pg_advisory_xact_lock(hashtext(:lock_key))",
                    {"lock_key": f"tradingagents:paper-trial:{run_id}"},
                )
            yield conn

    def _execute(self, conn, sql: str, params: dict | None = None):
        if self._sqlite:
            return conn.execute(sql, params or {})
        from sqlalchemy import text

        return conn.execute(text(sql), params or {})

    def _rows(self, sql: str, params: dict | None = None) -> list[dict]:
        if self._sqlite:
            return [dict(row) for row in self.conn.execute(sql, params or {}).fetchall()]
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]

    def _transaction_rows(self, conn, sql: str, params: dict | None = None) -> list[dict]:
        result = self._execute(conn, sql, params)
        if self._sqlite:
            return [dict(row) for row in result.fetchall()]
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    def _validated_authorization_row(row: dict, *, run_id: str) -> dict:
        """Authenticate a durable release row against its redundant columns.

        Migration 012 deliberately stores the content-addressed authorization
        both as canonical JSON and as indexed scalar columns.  A runtime must
        compare both representations; merely parsing ``authorization_json``
        would let catalog/trigger drift go unnoticed until a later write.
        """
        from tradingagents.formal_activation import validate_trial_authorization

        required = {
            "protocol_id",
            "run_id",
            "registration_id",
            "authorization_id",
            "authorized_utc",
            "outcome_semantics_id",
            "configuration_manifest_id",
            "collector_configuration_id",
            "paper_decision_configuration_id",
            "paper_marker_configuration_id",
            "collector_build_id",
            "paper_decision_build_id",
            "paper_marker_build_id",
            "authorization_json",
        }
        if set(row) != required:
            raise ValueError("formal authorization row has a wrong exact schema")
        try:
            document = json.loads(row["authorization_json"])
        except (TypeError, ValueError) as exc:
            raise ValueError("formal authorization JSON is malformed") from exc
        authorization = validate_trial_authorization(document)
        if authorization["run_id"] != run_id or row["run_id"] != run_id:
            raise ValueError("formal authorization belongs to a different run")
        if canonical_json(authorization) != row["authorization_json"]:
            raise ValueError("formal authorization JSON is not canonical")
        scalar_bindings = {
            "protocol_id": authorization["protocol_id"],
            "run_id": authorization["run_id"],
            "registration_id": authorization["registration_id"],
            "authorization_id": authorization["authorization_id"],
            "outcome_semantics_id": authorization["outcome_semantics_id"],
            **authorization["configuration_binding"],
            "collector_build_id": authorization["images"]["collector"]["build_id"],
            "paper_decision_build_id": authorization["images"]["paper_decision"][
                "build_id"
            ],
            "paper_marker_build_id": authorization["images"]["paper_marker"]["build_id"],
        }
        if any(row[field] != value for field, value in scalar_bindings.items()):
            raise ValueError("formal authorization columns disagree with its document")
        authorized_utc = row["authorized_utc"]
        if (
            isinstance(authorized_utc, bool)
            or not isinstance(authorized_utc, (int, float))
            or not math.isfinite(float(authorized_utc))
        ):
            raise ValueError("formal authorization server time is malformed")
        return authorization

    def formal_trial_authorization(self, run_id: str) -> dict:
        """Load and validate the sole durable authorization for ``run_id``."""
        if self._sqlite:
            raise ValueError("durable formal authorization requires PostgreSQL")
        rows = self._rows(
            "SELECT protocol_id,run_id,registration_id,authorization_id,"
            "authorized_utc,outcome_semantics_id,configuration_manifest_id,"
            "collector_configuration_id,paper_decision_configuration_id,"
            "paper_marker_configuration_id,collector_build_id,"
            "paper_decision_build_id,paper_marker_build_id,authorization_json "
            "FROM public.formal_trial_authorizations WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        if len(rows) != 1:
            raise ValueError("formal runtime requires one durable trial authorization")
        return self._validated_authorization_row(rows[0], run_id=run_id)

    def require_formal_runtime_authorization(
        self,
        run_id: str,
        *,
        role: str,
        component_configuration: dict,
        outcome_semantics_id: str,
        env=None,
    ) -> dict:
        """Fail closed unless this exact Fly image, config, and DB role are active.

        The role probe and authorization read share one physical connection.
        Provider calls happen only after this method succeeds.  Database
        insertion triggers independently re-check the same durable record.
        """
        if self._sqlite:
            raise ValueError("formal production runtime authorization requires PostgreSQL")
        from tradingagents.formal_activation import require_runtime_authorization
        from tradingagents.formal_configuration import validate_component_configuration
        from tradingagents.formal_roles import (
            DECISION_ROLE,
            MARKER_ROLE,
            ROLE_PREFLIGHT_SQL,
            validate_runtime_role_preflight,
        )

        role_to_login = {
            "paper_decision": DECISION_ROLE,
            "paper_marker": MARKER_ROLE,
        }
        expected_login = role_to_login.get(role)
        if expected_login is None:
            raise ValueError("paper runtime role is not allowlisted")
        component = validate_component_configuration(
            component_configuration, expected_role=role
        )
        if component["settings"]["run_id"] != run_id:
            raise ValueError("runtime component configuration belongs to another run")

        with self.engine.connect() as conn:
            preflight_rows = self._transaction_rows(conn, ROLE_PREFLIGHT_SQL)
            authorization_rows = self._transaction_rows(
                conn,
                "SELECT protocol_id,run_id,registration_id,authorization_id,"
                "authorized_utc,outcome_semantics_id,configuration_manifest_id,"
                "collector_configuration_id,paper_decision_configuration_id,"
                "paper_marker_configuration_id,collector_build_id,"
                "paper_decision_build_id,paper_marker_build_id,authorization_json "
                "FROM public.formal_trial_authorizations WHERE run_id=:run_id",
                {"run_id": run_id},
            )
        if len(preflight_rows) != 1:
            raise ValueError("formal database role preflight returned the wrong cardinality")
        validate_runtime_role_preflight(preflight_rows[0], expected_role=expected_login)
        if len(authorization_rows) != 1:
            raise ValueError("formal runtime requires one durable trial authorization")
        authorization = self._validated_authorization_row(
            authorization_rows[0], run_id=run_id
        )
        authorization_id = require_runtime_authorization(
            authorization,
            role=role,
            outcome_semantics_id=outcome_semantics_id,
            component_configuration_id=component["configuration_id"],
            env=env,
        )
        context = {
            "authorization_id": authorization_id,
            "authorization": authorization,
            "build_id": authorization["images"][role]["build_id"],
            "component_configuration": component,
        }
        self._formal_runtime_contexts[(run_id, role)] = context
        return context

    def authenticated_formal_runtime(self, run_id: str, *, role: str) -> dict:
        """Return a context established by this store's fail-closed preflight."""
        context = self._formal_runtime_contexts.get((run_id, role))
        if context is None:
            raise ValueError(f"formal {role} operation has not been authorized")
        return context

    def record_formal_runtime_heartbeat(
        self, run_id: str, *, role: str, event_type: str
    ) -> dict:
        """Append one server-observed heartbeat for an authenticated split worker."""
        if self._sqlite:
            raise ValueError("formal runtime heartbeats require PostgreSQL")
        from tradingagents.formal_roles import (
            DECISION_ROLE,
            MARKER_ROLE,
            RUNTIME_HEARTBEAT_EVENTS,
            RUNTIME_HEARTBEAT_SQL,
        )

        if event_type not in RUNTIME_HEARTBEAT_EVENTS:
            raise ValueError("formal heartbeat event type is not allowlisted")
        runtime = self.authenticated_formal_runtime(run_id, role=role)
        rows = self._rows(
            RUNTIME_HEARTBEAT_SQL,
            {
                "run_id": run_id,
                "event_type": event_type,
                "runtime_build_id": runtime["build_id"],
            },
        )
        required = {
            "heartbeat_id",
            "runtime_role",
            "event_type",
            "observed_utc",
        }
        expected_runtime_role = {
            "paper_decision": DECISION_ROLE,
            "paper_marker": MARKER_ROLE,
        }.get(role)
        if len(rows) != 1 or set(rows[0]) != required:
            raise ValueError("formal heartbeat returned a wrong schema")
        row = rows[0]
        if (
            expected_runtime_role is None
            or row["runtime_role"] != expected_runtime_role
            or row["event_type"] != event_type
            or not isinstance(row["heartbeat_id"], str)
            or re.fullmatch(r"heartbeat_[0-9a-f]{24}", row["heartbeat_id"])
            is None
            or isinstance(row["observed_utc"], bool)
            or not isinstance(row["observed_utc"], (int, float))
            or not math.isfinite(float(row["observed_utc"]))
        ):
            raise ValueError("formal heartbeat identity is inconsistent")
        return dict(row)

    def formal_decision_weight_snapshots(
        self, run_id: str, tickers: list[str]
    ) -> dict[str, dict]:
        """Return the exact strategy-position projection available to decision.

        SQLite is the local simulation harness and uses its ordinary ledger
        reads.  PostgreSQL production goes only through migration 013's narrow
        SECURITY DEFINER projection, so no price, NAV, return, cost, or review
        payload crosses from the marker principal.
        """
        strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
        if self._sqlite:
            return {
                strategy: self.latest_strategy_weight_snapshot(run_id, strategy, tickers)
                for strategy in strategies
            }
        from tradingagents.formal_roles import DECISION_WEIGHT_PROJECTION_SQL

        rows = self._rows(DECISION_WEIGHT_PROJECTION_SQL, {"run_id": run_id})
        required = {
            "strategy_id",
            "weights_json",
            "source_kind",
            "source_session_date",
            "source_decision_date",
        }
        if (
            len(rows) != len(strategies)
            or any(set(row) != required for row in rows)
            or [row["strategy_id"] for row in rows] != sorted(strategies)
        ):
            raise ValueError("formal decision weight projection has a wrong inventory")
        snapshots: dict[str, dict] = {}
        for row in rows:
            try:
                weights = json.loads(row["weights_json"])
            except (TypeError, ValueError) as exc:
                raise ValueError("formal decision weight projection is malformed") from exc
            if (
                not isinstance(weights, dict)
                or set(weights) != set(tickers)
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in weights.values()
                )
                or row["source_kind"]
                not in {"initial_zero", "strategy_target", "strategy_mark"}
                or (
                    row["source_session_date"] is not None
                    and not isinstance(row["source_session_date"], str)
                )
                or (
                    row["source_decision_date"] is not None
                    and not isinstance(row["source_decision_date"], str)
                )
            ):
                raise ValueError("formal decision weight projection is malformed")
            if row["source_kind"] == "initial_zero" and (
                row["source_session_date"] is not None
                or row["source_decision_date"] is not None
                or any(float(value) != 0.0 for value in weights.values())
            ):
                raise ValueError("formal initial weight projection is inconsistent")
            snapshots[row["strategy_id"]] = {
                "weights": {ticker: float(weights[ticker]) for ticker in tickers},
                "source_kind": row["source_kind"],
                "source_session_date": row["source_session_date"],
                "source_decision_date": row["source_decision_date"],
            }
        return snapshots

    def formal_decision_state(self, run_id: str, *, authorization: dict) -> dict:
        """Load the narrow outcome-free state projection for the decision role."""
        if self._sqlite:
            raise ValueError("formal decision state projection requires PostgreSQL")
        rows = self._rows(
            "SELECT run_id,protocol_id,registration_id,authorization_id,"
            "paper_decision_build_id,paper_decision_configuration_id,config_json,"
            "last_decision_date,last_entry_date,last_target_weights_json,"
            "terminal_price_integrity_failure "
            "FROM public.formal_decision_state_projection(:run_id)",
            {"run_id": run_id},
        )
        required = {
            "run_id",
            "protocol_id",
            "registration_id",
            "authorization_id",
            "paper_decision_build_id",
            "paper_decision_configuration_id",
            "config_json",
            "last_decision_date",
            "last_entry_date",
            "last_target_weights_json",
            "terminal_price_integrity_failure",
        }
        if len(rows) != 1 or set(rows[0]) != required:
            raise ValueError("formal decision state projection has a wrong schema")
        row = rows[0]
        expected = {
            "run_id": authorization["run_id"],
            "protocol_id": authorization["protocol_id"],
            "registration_id": authorization["registration_id"],
            "authorization_id": authorization["authorization_id"],
            "paper_decision_build_id": authorization["images"]["paper_decision"][
                "build_id"
            ],
            "paper_decision_configuration_id": authorization[
                "configuration_binding"
            ]["paper_decision_configuration_id"],
        }
        if any(row[field] != value for field, value in expected.items()):
            raise ValueError("formal decision state differs from durable authorization")
        try:
            config = json.loads(row["config_json"])
            target_weights = (
                None
                if row["last_target_weights_json"] is None
                else json.loads(row["last_target_weights_json"])
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("formal decision state JSON is malformed") from exc
        if (
            not isinstance(config, dict)
            or config.get("engine") != "formal-global-v2"
            or config.get("protocol_id") != authorization["protocol_id"]
            or config.get("outcome_semantics_id")
            != authorization["outcome_semantics_id"]
            or config.get("configuration_binding")
            != authorization["configuration_binding"]
            or type(row["terminal_price_integrity_failure"]) is not bool
            or (
                target_weights is not None
                and (
                    not isinstance(target_weights, dict)
                    or set(target_weights) != set(config.get("tickers", []))
                )
            )
        ):
            raise ValueError("formal decision state is inconsistent")
        return {
            **row,
            "config": config,
            "last_target_weights": target_weights,
        }

    def create_run(self, run_id: str, config: dict, created_utc: float) -> bool:
        existing = self._rows(
            "SELECT config_json FROM paper_runs WHERE run_id=:run_id", {"run_id": run_id}
        )
        encoded = _canonical(config)
        if existing:
            if existing[0]["config_json"] != encoded:
                raise ValueError(f"paper run {run_id!r} already exists with different config")
            return False
        with self._transaction() as conn:
            self._execute(
                conn,
                "INSERT INTO paper_runs (run_id,created_utc,config_json) "
                "VALUES (:run_id,:created_utc,:config_json)",
                {"run_id": run_id, "created_utc": created_utc, "config_json": encoded},
            )
        return True

    def register_protocol(self, protocol_id: str, manifest: dict, created_utc: float) -> bool:
        encoded = canonical_json(manifest)
        rows = self._rows(
            "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
            {"protocol_id": protocol_id},
        )
        if rows:
            if rows[0]["manifest_json"] != encoded:
                raise ValueError(f"protocol {protocol_id} already exists with different manifest")
            return False
        with self._transaction() as conn:
            self._execute(
                conn,
                "INSERT INTO experiment_registry "
                "(protocol_id,created_utc,manifest_json) VALUES "
                "(:protocol_id,:created_utc,:manifest_json)",
                {
                    "protocol_id": protocol_id,
                    "created_utc": created_utc,
                    "manifest_json": encoded,
                },
            )
        return True

    def record_artifact(self, artifact_type: str, content: dict, created_utc: float) -> str:
        """Append one content-addressed operational/research artifact."""
        if not isinstance(artifact_type, str) or not artifact_type.strip():
            raise ValueError("artifact type must be a non-empty string")
        if not isinstance(content, dict):
            raise ValueError("artifact content must be an object")
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("artifact timestamp must be finite")
        artifact_id = content_id(
            {"artifact_type": artifact_type, "content": content}, prefix="artifact_"
        )
        encoded = canonical_json(content)
        existing = self._rows(
            "SELECT artifact_type,content_json FROM paper_artifacts WHERE artifact_id=:artifact_id",
            {"artifact_id": artifact_id},
        )
        if existing:
            if (
                len(existing) != 1
                or existing[0]["artifact_type"] != artifact_type
                or existing[0]["content_json"] != encoded
            ):
                raise ValueError("paper artifact identity collision")
            return artifact_id
        with self._transaction() as conn:
            self._execute(
                conn,
                "INSERT INTO paper_artifacts "
                "(artifact_id,created_utc,artifact_type,content_json) VALUES "
                "(:artifact_id,:created_utc,:artifact_type,:content_json)",
                {
                    "artifact_id": artifact_id,
                    "created_utc": created_utc,
                    "artifact_type": artifact_type,
                    "content_json": encoded,
                },
            )
        return artifact_id

    def _frozen_llm_budget_policy(self, conn, run_id: str) -> dict:
        """Read exact call ceilings from both immutable registration surfaces."""
        config = self._require_registered_formal_run(conn, run_id)
        protocol_rows = self._transaction_rows(
            conn,
            "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
            {"protocol_id": config.get("protocol_id")},
        )
        if len(protocol_rows) != 1:
            raise ValueError("formal LLM budget requires one registered protocol manifest")
        try:
            protocol = json.loads(protocol_rows[0]["manifest_json"])
            configured = config["llm_policy"]
            frozen = protocol["forecast"]["invocation_policy"]
            decision_limit = configured["max_calls_per_decision"]
            day_limit = configured["max_calls_per_utc_day"]
            frozen_decision_limit = frozen["max_calls_per_decision"]
            frozen_day_limit = frozen["max_calls_per_utc_day"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("formal LLM budget policy is malformed") from exc
        limits = (
            decision_limit,
            day_limit,
            frozen_decision_limit,
            frozen_day_limit,
        )
        if any(type(value) is not int or value < 0 for value in limits) or (
            decision_limit != frozen_decision_limit or day_limit != frozen_day_limit
        ):
            raise ValueError("formal LLM budget differs from its frozen protocol")
        allowed_models = configured.get("allowed_models")
        if (
            not isinstance(allowed_models, list)
            or not allowed_models
            or any(not isinstance(value, str) or not value for value in allowed_models)
        ):
            raise ValueError("formal LLM model policy is malformed")
        return {
            "protocol_id": config["protocol_id"],
            "allowed_models": allowed_models,
            "max_calls_per_decision": decision_limit,
            "max_calls_per_utc_day": day_limit,
        }

    def _reserve_sqlite_formal_llm_budget(
        self,
        conn,
        *,
        scope: str,
        run_id: str,
        decision_date: str,
        policy: dict,
    ) -> dict:
        """SQLite analogue of migration 011's server-owned reservation function."""
        from tradingagents.llm_guard import LLMCallBudgetExceeded

        server_now = datetime.now(timezone.utc)
        utc_day = server_now.date().isoformat()
        decision_key = f"llm:{scope}:decision:{run_id}:{decision_date}"
        daily_key = (
            f"llm:{scope}:protocol:{policy['protocol_id']}:utc-day:{utc_day}"
        )
        definitions = (
            (
                decision_key,
                "decision",
                decision_date,
                policy["max_calls_per_decision"],
            ),
            (daily_key, "utc_day", utc_day, policy["max_calls_per_utc_day"]),
        )
        existing: dict[str, dict] = {}
        for counter_key, _kind, _bucket, _limit in definitions:
            rows = self._transaction_rows(
                conn,
                "SELECT counter_key,reserved_calls,frozen_limit FROM "
                "formal_llm_budget_counters WHERE counter_key=:counter_key",
                {"counter_key": counter_key},
            )
            if len(rows) > 1:
                raise RuntimeError("formal LLM budget counter identity is ambiguous")
            if rows:
                existing[counter_key] = rows[0]
        if any(
            limit < 1
            or (
                counter_key in existing
                and (
                    int(existing[counter_key]["frozen_limit"]) != limit
                    or int(existing[counter_key]["reserved_calls"]) >= limit
                )
            )
            for counter_key, _kind, _bucket, limit in definitions
        ):
            raise LLMCallBudgetExceeded(
                "persistent LLM call budget is exhausted; refusing another invocation"
            )
        observed = server_now.timestamp()
        counts: dict[str, int] = {}
        for counter_key, kind, bucket, limit in definitions:
            self._execute(
                conn,
                "INSERT INTO formal_llm_budget_counters "
                "(counter_key,scope,protocol_id,run_id,counter_kind,bucket_date,"
                "reserved_calls,frozen_limit,first_reserved_utc,last_reserved_utc) "
                "VALUES (:counter_key,:scope,:protocol_id,:run_id,:counter_kind,"
                ":bucket_date,1,:frozen_limit,:observed_utc,:observed_utc) "
                "ON CONFLICT(counter_key) DO UPDATE SET "
                "reserved_calls=formal_llm_budget_counters.reserved_calls+1,"
                "last_reserved_utc=:observed_utc",
                {
                    "counter_key": counter_key,
                    "scope": scope,
                    "protocol_id": policy["protocol_id"],
                    "run_id": run_id,
                    "counter_kind": kind,
                    "bucket_date": bucket,
                    "frozen_limit": limit,
                    "observed_utc": observed,
                },
            )
            counts[counter_key] = (
                int(existing.get(counter_key, {}).get("reserved_calls", 0)) + 1
            )
        return {
            "reservation_counts": counts,
            "utc_day": utc_day,
            "reserved_utc": observed,
            "max_calls_per_decision": policy["max_calls_per_decision"],
            "max_calls_per_utc_day": policy["max_calls_per_utc_day"],
            "decision_counter_key": decision_key,
            "daily_counter_key": daily_key,
        }

    def _reserve_postgres_formal_llm_budget(
        self, conn, *, reservation_spec: dict
    ) -> dict:
        """Invoke the sole privileged PostgreSQL counter/artifact mutation surface."""
        rows = self._transaction_rows(
            conn,
            "SELECT reservation_artifact_id,reservation_receipt_json,"
            "decision_count,daily_count,utc_day,reserved_utc,"
            "max_calls_per_decision,max_calls_per_utc_day,"
            "decision_counter_key,daily_counter_key "
            "FROM public.reserve_formal_llm_invocation_budget("
            ":run_id,:decision_date,:stage,:provider,:requested_model,"
            ":input_bundle_id,:prompt_id,:prompt_bytes,:max_prompt_bytes,"
            ":max_completion_tokens)",
            reservation_spec,
        )
        if len(rows) != 1:
            raise RuntimeError("formal LLM reservation function returned an invalid result")
        row = rows[0]
        try:
            receipt = json.loads(row["reservation_receipt_json"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "formal LLM reservation function returned malformed JSON"
            ) from exc
        return {
            "reservation_counts": {
                row["decision_counter_key"]: int(row["decision_count"]),
                row["daily_counter_key"]: int(row["daily_count"]),
            },
            "utc_day": str(row["utc_day"]),
            "reserved_utc": float(row["reserved_utc"]),
            "max_calls_per_decision": int(row["max_calls_per_decision"]),
            "max_calls_per_utc_day": int(row["max_calls_per_utc_day"]),
            "decision_counter_key": row["decision_counter_key"],
            "daily_counter_key": row["daily_counter_key"],
            "reservation_receipt": receipt,
            "reservation_artifact_id": row["reservation_artifact_id"],
            "artifact_inserted": True,
        }

    def _before_llm_reservation_artifact_insert(
        self, conn, reservation_receipt: dict, reservation_counts: dict[str, float]
    ) -> None:
        """Test seam immediately before the atomic reservation-receipt insert."""

    def reserve_llm_invocation(self, reservation_spec: dict) -> dict:
        """Atomically reserve persistent counters and append their exact receipt."""
        if (
            not isinstance(reservation_spec, dict)
            or set(reservation_spec) != _LLM_RESERVATION_SPEC_FIELDS
        ):
            raise ValueError("formal LLM reservation specification is malformed")
        string_fields = (
            "scope",
            "run_id",
            "decision_date",
            "stage",
            "provider",
            "requested_model",
            "input_bundle_id",
            "prompt_id",
        )
        if any(
            not isinstance(reservation_spec.get(field), str) or not reservation_spec[field].strip()
            for field in string_fields
        ):
            raise ValueError("formal LLM reservation identity is malformed")
        positive_integer_fields = (
            "prompt_bytes",
            "max_prompt_bytes",
            "max_completion_tokens",
        )
        if (
            any(
                type(reservation_spec.get(field)) is not int or reservation_spec[field] < 1
                for field in positive_integer_fields
            )
            or reservation_spec["prompt_bytes"] > reservation_spec["max_prompt_bytes"]
        ):
            raise ValueError("formal LLM reservation ceilings are malformed")
        scope = reservation_spec["scope"]
        run_id = reservation_spec["run_id"]
        decision_date = reservation_spec["decision_date"]
        try:
            if date.fromisoformat(decision_date).isoformat() != decision_date:
                raise ValueError
        except ValueError as exc:
            raise ValueError("formal LLM reservation decision date is malformed") from exc
        if scope != "formal-global-v2":
            raise ValueError("formal LLM reservation scope is not allowlisted")
        from tradingagents.llm_guard import LLMCallBudgetExceeded

        try:
            with self._trial_lifecycle_transaction(run_id) as conn:
                policy = self._frozen_llm_budget_policy(conn, run_id)
                requested_identity = (
                    f"{reservation_spec['provider'].strip().lower()}:"
                    f"{reservation_spec['requested_model'].strip()}"
                )
                if requested_identity not in policy["allowed_models"]:
                    raise ValueError("formal LLM reservation model differs from its frozen run")
                starts = self._transaction_rows(
                    conn,
                    "SELECT attempt_ordinal FROM paper_decision_attempt_events "
                    "WHERE run_id=:run_id AND decision_date=:decision_date "
                    "AND event_type='started' ORDER BY attempt_ordinal DESC LIMIT 1",
                    {"run_id": run_id, "decision_date": decision_date},
                )
                if len(starts) != 1:
                    raise ValueError("formal LLM reservation requires a started attempt")
                failed = self._transaction_rows(
                    conn,
                    "SELECT 1 AS found FROM paper_decision_attempt_events "
                    "WHERE run_id=:run_id AND decision_date=:decision_date "
                    "AND attempt_ordinal=:attempt_ordinal AND event_type='failed'",
                    {
                        "run_id": run_id,
                        "decision_date": decision_date,
                        "attempt_ordinal": starts[0]["attempt_ordinal"],
                    },
                )
                if failed:
                    raise ValueError("formal LLM reservation attempt is already failed")
                existing_reservations = self._transaction_rows(
                    conn,
                    "SELECT content_json FROM paper_artifacts "
                    "WHERE artifact_type='llm_invocation_reserved'",
                )
                for row in existing_reservations:
                    try:
                        prior = json.loads(row["content_json"])
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            "formal LLM reservation artifact is malformed"
                        ) from exc
                    if (
                        isinstance(prior, dict)
                        and prior.get("run_id") == run_id
                        and prior.get("decision_date") == decision_date
                        and prior.get("stage") == reservation_spec["stage"]
                    ):
                        raise ValueError(
                            "formal LLM invocation stage already has a reservation"
                        )
                server_reservation = (
                    self._reserve_sqlite_formal_llm_budget(
                        conn,
                        scope=scope,
                        run_id=run_id,
                        decision_date=decision_date,
                        policy=policy,
                    )
                    if self._sqlite
                    else self._reserve_postgres_formal_llm_budget(
                        conn, reservation_spec=reservation_spec
                    )
                )
                reservation_counts = server_reservation["reservation_counts"]
                expected_decision_key = server_reservation["decision_counter_key"]
                expected_daily_key = server_reservation["daily_counter_key"]
                ordinal_value = reservation_counts.get(expected_decision_key)
                if (
                    not isinstance(ordinal_value, (int, float))
                    or isinstance(ordinal_value, bool)
                    or not float(ordinal_value).is_integer()
                    or ordinal_value < 1
                ):
                    raise RuntimeError("formal LLM reservation returned an invalid ordinal")
                invocation_identity = {
                    "scope": scope,
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "ordinal": int(ordinal_value),
                    "stage": reservation_spec["stage"],
                    "provider": reservation_spec["provider"],
                    "requested_model": reservation_spec["requested_model"],
                    "input_bundle_id": reservation_spec["input_bundle_id"],
                }
                invocation_id = content_id(invocation_identity, prefix="invocation_")
                expected_reservation_receipt = {
                    "schema_version": 2,
                    "invocation_id": invocation_id,
                    **invocation_identity,
                    "prompt_id": reservation_spec["prompt_id"],
                    "prompt_bytes": reservation_spec["prompt_bytes"],
                    "max_prompt_bytes": reservation_spec["max_prompt_bytes"],
                    "max_completion_tokens": reservation_spec["max_completion_tokens"],
                    "max_calls_per_decision": server_reservation[
                        "max_calls_per_decision"
                    ],
                    "max_calls_per_utc_day": server_reservation[
                        "max_calls_per_utc_day"
                    ],
                    "decision_counter_key": expected_decision_key,
                    "daily_counter_key": expected_daily_key,
                    "utc_day": server_reservation["utc_day"],
                    "reserved_utc": datetime.fromtimestamp(
                        server_reservation["reserved_utc"], timezone.utc
                    ).isoformat(),
                    "reservation_counts": reservation_counts,
                }
                reservation_receipt = server_reservation.get(
                    "reservation_receipt", expected_reservation_receipt
                )
                if canonical_json(reservation_receipt) != canonical_json(
                    expected_reservation_receipt
                ):
                    raise RuntimeError(
                        "formal LLM reservation function returned a forged receipt"
                    )
                if set(reservation_counts) != {expected_decision_key, expected_daily_key} or any(
                    not math.isfinite(float(value))
                    or not float(value).is_integer()
                    or float(value) < 1
                    for value in reservation_counts.values()
                ):
                    raise RuntimeError("formal LLM reservation returned invalid counters")
                expected_reservation_artifact_id = content_id(
                    {
                        "artifact_type": "llm_invocation_reserved",
                        "content": reservation_receipt,
                    },
                    prefix="artifact_",
                )
                reservation_artifact_id = server_reservation.get(
                    "reservation_artifact_id", expected_reservation_artifact_id
                )
                if reservation_artifact_id != expected_reservation_artifact_id:
                    raise RuntimeError(
                        "formal LLM reservation function returned a forged artifact ID"
                    )
                self._before_llm_reservation_artifact_insert(
                    conn, reservation_receipt, reservation_counts
                )
                if not server_reservation.get("artifact_inserted", False):
                    self._execute(
                        conn,
                        "INSERT INTO paper_artifacts "
                        "(artifact_id,created_utc,artifact_type,content_json) VALUES "
                        "(:artifact_id,:created_utc,'llm_invocation_reserved',:content_json)",
                        {
                            "artifact_id": reservation_artifact_id,
                            "created_utc": server_reservation["reserved_utc"],
                            "content_json": canonical_json(reservation_receipt),
                        },
                    )
        except Exception as exc:
            if "formal LLM budget exhausted" in str(exc):
                raise LLMCallBudgetExceeded(
                    "persistent LLM call budget is exhausted; refusing another invocation"
                ) from exc
            raise
        return {
            "reservation_counts": reservation_counts,
            "reservation_receipt": reservation_receipt,
            "reservation_artifact_id": reservation_artifact_id,
        }

    def record_llm_invocation_result(self, result_receipt: dict, created_utc: float) -> str:
        """Append at most one terminal result for one immutable reservation."""
        if not isinstance(result_receipt, dict) or result_receipt.get("schema_version") != 2:
            raise ValueError("formal LLM result receipt is malformed")
        reservation_artifact_id = result_receipt.get("reservation_artifact_id")
        if not isinstance(reservation_artifact_id, str) or not reservation_artifact_id:
            raise ValueError("formal LLM result receipt lacks its reservation identity")
        if result_receipt.get("status") not in {"success", "failed"}:
            raise ValueError("formal LLM result receipt has an invalid status")
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("formal LLM result timestamp must be finite")
        run_id = result_receipt.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("formal LLM result receipt lacks its run identity")
        encoded = canonical_json(result_receipt)
        artifact_id = content_id(
            {"artifact_type": "llm_invocation_result", "content": result_receipt},
            prefix="artifact_",
        )
        with self._trial_lifecycle_transaction(run_id) as conn:
            self._require_registered_formal_run(conn, run_id)
            reservations = self._transaction_rows(
                conn,
                "SELECT content_json FROM paper_artifacts "
                "WHERE artifact_id=:artifact_id "
                "AND artifact_type='llm_invocation_reserved'",
                {"artifact_id": reservation_artifact_id},
            )
            if len(reservations) != 1:
                raise ValueError("formal LLM result has no unique reservation")
            try:
                reservation = json.loads(reservations[0]["content_json"])
            except (TypeError, ValueError) as exc:
                raise ValueError("formal LLM reservation receipt is malformed") from exc
            if (
                not isinstance(reservation, dict)
                or result_receipt.get("invocation_id") != reservation.get("invocation_id")
                or any(
                    canonical_json(result_receipt.get(field))
                    != canonical_json(reservation.get(field))
                    for field in _LLM_INVOCATION_IDENTITY_FIELDS
                )
            ):
                raise ValueError("formal LLM result differs from its reservation")
            result_rows = self._transaction_rows(
                conn,
                "SELECT artifact_id,content_json FROM paper_artifacts "
                "WHERE artifact_type='llm_invocation_result'",
            )
            matching = []
            for row in result_rows:
                try:
                    content = json.loads(row["content_json"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("formal LLM result artifact is malformed") from exc
                if (
                    isinstance(content, dict)
                    and content.get("reservation_artifact_id") == reservation_artifact_id
                ):
                    matching.append((row, content))
            if matching:
                if (
                    len(matching) == 1
                    and matching[0][0]["artifact_id"] == artifact_id
                    and canonical_json(matching[0][1]) == encoded
                ):
                    return artifact_id
                raise ValueError("formal LLM reservation already has a different result")
            self._execute(
                conn,
                "INSERT INTO paper_artifacts "
                "(artifact_id,created_utc,artifact_type,content_json) VALUES "
                "(:artifact_id,:created_utc,'llm_invocation_result',:content_json)",
                {
                    "artifact_id": artifact_id,
                    "created_utc": float(created_utc),
                    "content_json": encoded,
                },
            )
        return artifact_id

    def label_run(
        self, run_id: str, label: str, created_utc: float, details: dict | None = None
    ) -> bool:
        if label == CONFIRMATORY_TRIAL_LABEL:
            return self.register_confirmatory_trial(
                run_id, created_utc, details if details is not None else {}
            )
        rows = self._rows(
            "SELECT details_json FROM paper_run_labels WHERE run_id=:run_id AND label=:label",
            {"run_id": run_id, "label": label},
        )
        encoded = canonical_json(details or {})
        if rows:
            if rows[0]["details_json"] != encoded:
                raise ValueError(f"run label {run_id}/{label} already has different details")
            return False
        with self._transaction() as conn:
            self._execute(
                conn,
                "INSERT INTO paper_run_labels "
                "(run_id,label,created_utc,details_json) VALUES "
                "(:run_id,:label,:created_utc,:details_json)",
                {
                    "run_id": run_id,
                    "label": label,
                    "created_utc": created_utc,
                    "details_json": encoded,
                },
            )
        return True

    def confirmatory_registration(self, run_id: str) -> dict | None:
        """Return the immutable confirmatory registration, if one exists."""
        labels = self._rows(
            "SELECT created_utc,details_json FROM paper_run_labels "
            "WHERE run_id=:run_id AND label=:label",
            {"run_id": run_id, "label": CONFIRMATORY_TRIAL_LABEL},
        )
        registry = self._rows(
            "SELECT protocol_id,registration_id,created_utc,details_json "
            "FROM formal_trial_registry WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        if not labels and not registry:
            return None
        if len(labels) != 1 or len(registry) != 1:
            raise ValueError(f"run {run_id!r} has an incomplete primary registration")
        if (
            labels[0]["created_utc"] != registry[0]["created_utc"]
            or labels[0]["details_json"] != registry[0]["details_json"]
        ):
            raise ValueError(f"run {run_id!r} has inconsistent registration records")
        try:
            details = json.loads(registry[0]["details_json"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"run {run_id!r} has malformed registration details") from exc
        if (
            not isinstance(details, dict)
            or details.get("protocol_id") != registry[0]["protocol_id"]
            or details.get("registration_id", registry[0]["registration_id"])
            != registry[0]["registration_id"]
        ):
            raise ValueError(f"run {run_id!r} has inconsistent registration identity")
        return {
            "label": CONFIRMATORY_TRIAL_LABEL,
            "created_utc": registry[0]["created_utc"],
            "details": details,
        }

    @staticmethod
    def _registration_identity(details: dict) -> str:
        registration_id = details.get("registration_id")
        if registration_id is None:
            return content_id(details, prefix="registration_")
        if not isinstance(registration_id, str) or not registration_id.strip():
            raise ValueError("confirmatory registration ID must be a non-empty string")
        return registration_id

    def _protocol_formal_run_ids(self, conn, protocol_id: str) -> list[str]:
        rows = self._transaction_rows(
            conn, "SELECT run_id,config_json FROM paper_runs ORDER BY run_id"
        )
        run_ids = []
        for row in rows:
            try:
                config = json.loads(row["config_json"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("paper run has malformed immutable configuration") from exc
            if not isinstance(config, dict):
                raise ValueError("paper run has malformed immutable configuration")
            if (
                config.get("engine") == "formal-global-v2"
                and config.get("protocol_id") == protocol_id
            ):
                run_ids.append(row["run_id"])
        return run_ids

    def _legacy_protocol_activity(
        self,
        conn,
        protocol_run_ids: list[str],
        *,
        candidate_run_id: str,
        encoded_details: str,
    ) -> tuple[list[str], dict | None]:
        """Find activity for any same-protocol run before selecting a primary."""
        activity: list[str] = []
        legacy_candidate_label = None
        run_id_set = set(protocol_run_ids)
        for protocol_run_id in protocol_run_ids:
            for table in self._TRIAL_ACTIVITY_TABLES:
                if self._transaction_rows(
                    conn,
                    f"SELECT 1 AS found FROM {table} WHERE run_id=:run_id LIMIT 1",
                    {"run_id": protocol_run_id},
                ):
                    activity.append(f"{protocol_run_id}:{table}")
            labels = self._transaction_rows(
                conn,
                "SELECT label,created_utc,details_json FROM paper_run_labels "
                "WHERE run_id=:run_id ORDER BY label",
                {"run_id": protocol_run_id},
            )
            for label in labels:
                if label["label"] == CONFIRMATORY_TRIAL_LABEL:
                    if protocol_run_id != candidate_run_id:
                        activity.append(f"{protocol_run_id}:alternate-confirmatory-label")
                    elif label["details_json"] != encoded_details:
                        activity.append(f"{protocol_run_id}:different-confirmatory-label")
                    else:
                        legacy_candidate_label = label
                else:
                    activity.append(f"{protocol_run_id}:paper_run_labels")

        artifacts = self._transaction_rows(
            conn, "SELECT artifact_id,content_json FROM paper_artifacts"
        )
        for artifact in artifacts:
            try:
                content = json.loads(artifact["content_json"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("paper artifact has malformed immutable content") from exc
            if isinstance(content, dict) and content.get("run_id") in run_id_set:
                activity.append(f"{content['run_id']}:paper_artifacts")
        return activity, legacy_candidate_label

    def register_confirmatory_trial(self, run_id: str, created_utc: float, details: dict) -> bool:
        """Atomically preregister a formal trial before any target or outcome.

        An exact retry remains idempotent after the trial starts. Any attempt to
        change the registration, or to create it after trial activity, fails.
        """
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("confirmatory run ID must be a non-empty string")
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("confirmatory registration time must be finite")
        if not isinstance(details, dict) or not details:
            raise ValueError("confirmatory registration details must be a non-empty object")
        protocol_id = details.get("protocol_id")
        if not isinstance(protocol_id, str) or not protocol_id.strip():
            raise ValueError("confirmatory protocol ID must be a non-empty string")
        if details.get("run_id", run_id) != run_id:
            raise ValueError("confirmatory registration run ID does not match")
        if details.get("registration_type", "confirmatory") != "confirmatory":
            raise ValueError("confirmatory registration type does not match")
        if details.get("outcomes_accessed_before_registration", False) is not False:
            raise ValueError("confirmatory registration declares prior outcome access")
        registration_id = self._registration_identity(details)
        encoded = canonical_json(details)
        params = {"run_id": run_id, "label": CONFIRMATORY_TRIAL_LABEL}
        with self._protocol_registration_transaction(protocol_id, run_id) as conn:
            runs = self._transaction_rows(
                conn,
                "SELECT config_json FROM paper_runs WHERE run_id=:run_id",
                {"run_id": run_id},
            )
            if len(runs) != 1:
                raise ValueError(f"unknown paper run {run_id!r}")
            config = json.loads(runs[0]["config_json"])
            if config.get("engine") != "formal-global-v2":
                raise ValueError("confirmatory registration requires a formal-global-v2 run")
            if config.get("protocol_id") != protocol_id:
                raise ValueError("confirmatory protocol differs from its paper run")
            if config.get("trial_registration_id", registration_id) != registration_id:
                raise ValueError("confirmatory registration differs from its paper run")

            registry = self._transaction_rows(
                conn,
                "SELECT protocol_id,run_id,registration_id,created_utc,details_json "
                "FROM formal_trial_registry "
                "WHERE protocol_id=:protocol_id OR run_id=:run_id "
                "ORDER BY protocol_id,run_id",
                {"protocol_id": protocol_id, "run_id": run_id},
            )
            if registry:
                if (
                    len(registry) != 1
                    or registry[0]["protocol_id"] != protocol_id
                    or registry[0]["run_id"] != run_id
                ):
                    raise ValueError(
                        f"protocol {protocol_id!r} already has a different primary run"
                    )
                if (
                    registry[0]["registration_id"] != registration_id
                    or registry[0]["details_json"] != encoded
                ):
                    raise ValueError(
                        f"confirmatory registration for {run_id!r} already has different details"
                    )
                labels = self._transaction_rows(
                    conn,
                    "SELECT created_utc,details_json FROM paper_run_labels "
                    "WHERE run_id=:run_id AND label=:label",
                    params,
                )
                if (
                    len(labels) != 1
                    or labels[0]["created_utc"] != registry[0]["created_utc"]
                    or labels[0]["details_json"] != encoded
                ):
                    raise ValueError("primary registration and confirmatory label differ")
                return False

            protocol_run_ids = self._protocol_formal_run_ids(conn, protocol_id)
            if run_id not in protocol_run_ids:
                raise ValueError("confirmatory run is not bound to its protocol")
            activity, legacy_label = self._legacy_protocol_activity(
                conn,
                protocol_run_ids,
                candidate_run_id=run_id,
                encoded_details=encoded,
            )
            if activity:
                raise ValueError(
                    f"confirmatory registration for protocol {protocol_id!r} is too late; "
                    "same-protocol trial activity or outcome access already exists"
                )
            registered_utc = (
                float(legacy_label["created_utc"])
                if legacy_label is not None
                else float(created_utc)
            )
            self._execute(
                conn,
                "INSERT INTO formal_trial_registry "
                "(protocol_id,run_id,registration_id,created_utc,details_json) VALUES "
                "(:protocol_id,:run_id,:registration_id,:created_utc,:details_json)",
                {
                    "protocol_id": protocol_id,
                    "run_id": run_id,
                    "registration_id": registration_id,
                    "created_utc": registered_utc,
                    "details_json": encoded,
                },
            )
            if legacy_label is None:
                self._execute(
                    conn,
                    "INSERT INTO paper_run_labels "
                    "(run_id,label,created_utc,details_json) VALUES "
                    "(:run_id,:label,:created_utc,:details_json)",
                    {
                        **params,
                        "created_utc": registered_utc,
                        "details_json": encoded,
                    },
                )
        return True

    def _require_registered_formal_run(self, conn, run_id: str) -> dict:
        runs = self._transaction_rows(
            conn,
            "SELECT config_json FROM paper_runs WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        if len(runs) != 1:
            raise ValueError(f"unknown paper run {run_id!r}")
        config = json.loads(runs[0]["config_json"])
        if config.get("engine") != "formal-global-v2":
            raise ValueError("formal provenance requires a formal-global-v2 run")
        protocol_id = config.get("protocol_id")
        if not isinstance(protocol_id, str) or not protocol_id:
            raise ValueError("formal provenance requires a protocol-bound run")
        registrations = self._transaction_rows(
            conn,
            "SELECT registry.registration_id,registry.details_json,label.details_json "
            "AS label_details_json FROM formal_trial_registry AS registry "
            "JOIN paper_run_labels AS label ON label.run_id=registry.run_id "
            "AND label.label=:label AND label.created_utc=registry.created_utc "
            "WHERE registry.protocol_id=:protocol_id AND registry.run_id=:run_id",
            {
                "run_id": run_id,
                "protocol_id": protocol_id,
                "label": CONFIRMATORY_TRIAL_LABEL,
            },
        )
        if (
            len(registrations) != 1
            or registrations[0]["details_json"] != registrations[0]["label_details_json"]
            or config.get("trial_registration_id", registrations[0]["registration_id"])
            != registrations[0]["registration_id"]
        ):
            raise ValueError("formal provenance requires the unique primary registration")
        return config

    def _validate_formal_decision_slot(
        self, conn, run_id: str, decision_date: str, entry_date: str
    ) -> dict:
        """Require the next chronological target and stop before interval 253."""
        config = self._require_registered_formal_run(conn, run_id)
        if not self._sqlite:
            from tradingagents.formal_roles import (
                DECISION_SLOT_PROJECTION_SQL,
                validate_decision_slot_projection,
            )

            runtime = self.authenticated_formal_runtime(
                run_id, role="paper_decision"
            )
            rows = self._transaction_rows(
                conn,
                DECISION_SLOT_PROJECTION_SQL,
                {
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "entry_date": entry_date,
                },
            )
            if len(rows) != 1:
                raise ValueError(
                    "formal decision-slot projection returned the wrong cardinality"
                )
            slot = validate_decision_slot_projection(
                rows[0],
                expected_run_id=run_id,
                expected_decision_date=decision_date,
                expected_entry_date=entry_date,
            )
            authorization = runtime["authorization"]
            expected_identities = {
                "protocol_id": authorization["protocol_id"],
                "registration_id": authorization["registration_id"],
                "authorization_id": authorization["authorization_id"],
                "paper_decision_build_id": authorization["images"][
                    "paper_decision"
                ]["build_id"],
                "paper_decision_configuration_id": authorization[
                    "configuration_binding"
                ]["paper_decision_configuration_id"],
            }
            if any(
                slot[field] != expected
                for field, expected in expected_identities.items()
            ):
                raise ValueError(
                    "formal decision slot differs from durable authorization"
                )
            return config

        protocol_rows = self._transaction_rows(
            conn,
            "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
            {"protocol_id": config.get("protocol_id")},
        )
        if len(protocol_rows) != 1:
            raise ValueError("formal decision requires its registered protocol manifest")
        manifest = json.loads(protocol_rows[0]["manifest_json"])
        try:
            holding_intervals = int(manifest["analysis"]["trial_clock"]["holding_intervals"])
        except (KeyError, TypeError, ValueError):
            # Compatibility-only protocol fixtures do not enter production;
            # the database still enforces the V2 ceiling.
            holding_intervals = FORMAL_HOLDING_INTERVALS
        if holding_intervals != FORMAL_HOLDING_INTERVALS:
            raise ValueError("formal decision horizon differs from the supported protocol")

        assignment_rows = self._transaction_rows(
            conn,
            "SELECT COUNT(*) AS count,MAX(interval_index) AS maximum "
            "FROM paper_interval_assignments WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        completed = int(assignment_rows[0]["count"] or 0)
        maximum = assignment_rows[0]["maximum"]
        if maximum is not None and int(maximum) != completed:
            raise ValueError("formal interval assignments are not contiguous")
        # A target entered after N completed intervals governs interval N+2.
        # Once 251 intervals are complete, the target already held at that
        # open is the final registered interval's target.
        if completed >= holding_intervals - 1:
            raise ValueError("formal confirmatory decision horizon is complete")

        marks = self._transaction_rows(
            conn,
            "SELECT session_date FROM paper_marks WHERE run_id=:run_id "
            "ORDER BY session_date DESC LIMIT 1",
            {"run_id": run_id},
        )
        bundles = self._transaction_rows(
            conn,
            "SELECT decision_date FROM paper_decision_bundles "
            "WHERE run_id=:run_id ORDER BY decision_date",
            {"run_id": run_id},
        )
        if not marks:
            if bundles:
                raise ValueError(
                    "formal run must initialize its frozen target before another decision"
                )
            return config

        latest_session = marks[0]["session_date"]
        if decision_date != latest_session or entry_date != next_session_date(latest_session):
            raise ValueError("formal decision is not the next chronological target slot")
        expected_strategies = manifest.get("strategies")
        if isinstance(expected_strategies, list) and expected_strategies:
            shadow_rows = self._transaction_rows(
                conn,
                "SELECT strategy_id FROM paper_strategy_marks "
                "WHERE run_id=:run_id AND session_date=:session_date",
                {"run_id": run_id, "session_date": latest_session},
            )
            if {row["strategy_id"] for row in shadow_rows} != set(expected_strategies) or len(
                shadow_rows
            ) != len(expected_strategies):
                raise ValueError("formal decision requires synchronized latest strategy marks")
        return config

    def record_formal_attempt_started(
        self,
        run_id: str,
        decision_date: str,
        entry_date: str,
        created_utc: float,
    ) -> int:
        """Append an attempt start and return its transactionally allocated ordinal.

        A start is written before fallible decision work. If the process dies,
        the unmatched start remains durable evidence of the interrupted attempt.
        """
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("formal attempt time must be finite")
        cutoff, next_open, expected_entry = decision_window(decision_date)
        if entry_date != expected_entry:
            raise ValueError("formal attempt entry date does not match its decision window")
        created_at = datetime.fromtimestamp(float(created_utc), timezone.utc)
        if not cutoff <= created_at < next_open:
            raise ValueError("formal attempt start is outside its decision window")

        with self._trial_lifecycle_transaction(run_id) as conn:
            self._validate_formal_decision_slot(conn, run_id, decision_date, entry_date)
            if self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_decision_bundles "
                "WHERE run_id=:run_id AND decision_date=:decision_date",
                {"run_id": run_id, "decision_date": decision_date},
            ):
                raise ValueError("formal decision is already frozen")
            rows = self._transaction_rows(
                conn,
                "SELECT MAX(attempt_ordinal) AS ordinal "
                "FROM paper_decision_attempt_events "
                "WHERE run_id=:run_id AND decision_date=:decision_date "
                "AND event_type='started'",
                {"run_id": run_id, "decision_date": decision_date},
            )
            previous = rows[0]["ordinal"] if rows else None
            ordinal = int(previous or 0) + 1
            self._execute(
                conn,
                "INSERT INTO paper_decision_attempt_events "
                "(run_id,decision_date,entry_date,attempt_ordinal,event_type,"
                "created_utc,reason_code) VALUES "
                "(:run_id,:decision_date,:entry_date,:attempt_ordinal,'started',"
                ":created_utc,NULL)",
                {
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "entry_date": entry_date,
                    "attempt_ordinal": ordinal,
                    "created_utc": float(created_utc),
                },
            )
        return ordinal

    def record_formal_attempt_failed(
        self,
        run_id: str,
        decision_date: str,
        attempt_ordinal: int,
        created_utc: float,
        reason_code: str,
    ) -> bool:
        """Append one sanitized terminal failure event for an existing start."""
        if type(attempt_ordinal) is not int or attempt_ordinal < 1:
            raise ValueError("formal attempt ordinal must be a positive integer")
        if reason_code not in FORMAL_ATTEMPT_FAILURE_REASON_CODES:
            raise ValueError("formal attempt failure reason is not allowlisted")
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("formal attempt failure time must be finite")

        params = {
            "run_id": run_id,
            "decision_date": decision_date,
            "attempt_ordinal": attempt_ordinal,
        }
        with self._trial_lifecycle_transaction(run_id) as conn:
            self._require_registered_formal_run(conn, run_id)
            starts = self._transaction_rows(
                conn,
                "SELECT entry_date,created_utc FROM paper_decision_attempt_events "
                "WHERE run_id=:run_id AND decision_date=:decision_date "
                "AND attempt_ordinal=:attempt_ordinal AND event_type='started'",
                params,
            )
            if len(starts) != 1:
                raise ValueError("formal failure event requires exactly one attempt start")
            if float(created_utc) < float(starts[0]["created_utc"]):
                raise ValueError("formal attempt failure precedes its start")
            if self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_decision_bundles "
                "WHERE run_id=:run_id AND decision_date=:decision_date",
                params,
            ):
                raise ValueError("a successful formal decision cannot be marked failed")
            failures = self._transaction_rows(
                conn,
                "SELECT reason_code FROM paper_decision_attempt_events "
                "WHERE run_id=:run_id AND decision_date=:decision_date "
                "AND attempt_ordinal=:attempt_ordinal AND event_type='failed'",
                params,
            )
            if failures:
                if failures[0]["reason_code"] != reason_code:
                    raise ValueError("formal attempt already has a different failure reason")
                return False
            self._execute(
                conn,
                "INSERT INTO paper_decision_attempt_events "
                "(run_id,decision_date,entry_date,attempt_ordinal,event_type,"
                "created_utc,reason_code) VALUES "
                "(:run_id,:decision_date,:entry_date,:attempt_ordinal,'failed',"
                ":created_utc,:reason_code)",
                {
                    **params,
                    "entry_date": starts[0]["entry_date"],
                    "created_utc": float(created_utc),
                    "reason_code": reason_code,
                },
            )
        return True

    def formal_attempt_events(self, run_id: str, decision_date: str | None = None) -> list[dict]:
        params = {"run_id": run_id}
        predicate = "run_id=:run_id"
        if decision_date is not None:
            params["decision_date"] = decision_date
            predicate += " AND decision_date=:decision_date"
        return self._rows(
            "SELECT run_id,decision_date,entry_date,attempt_ordinal,event_type,"
            f"created_utc,reason_code FROM paper_decision_attempt_events WHERE {predicate} "
            "ORDER BY decision_date,attempt_ordinal,event_type DESC",
            params,
        )

    @staticmethod
    def _project_invocation_receipts(
        rows: list[dict], run_id: str, decision_date: str
    ) -> list[dict]:
        projected = []
        for raw_row in rows:
            row = dict(raw_row)
            try:
                content = json.loads(row.pop("content_json"))
            except (KeyError, TypeError, ValueError):
                continue
            if (
                not isinstance(content, dict)
                or content.get("run_id") != run_id
                or content.get("decision_date") != decision_date
            ):
                continue
            row["content"] = content
            projected.append(row)
        return projected

    def formal_invocation_receipts(self, run_id: str, decision_date: str) -> list[dict]:
        """Load only self-identified invocation receipts for one decision."""
        rows = self._rows(
            "SELECT artifact_id,created_utc,artifact_type,content_json "
            "FROM paper_artifacts WHERE artifact_type IN "
            "('llm_invocation_reserved','llm_invocation_result') "
            "ORDER BY created_utc,artifact_type,artifact_id"
        )
        return self._project_invocation_receipts(rows, run_id, decision_date)

    def _validate_invocation_receipts_before_persistence(
        self,
        conn,
        *,
        run_id: str,
        decision_date: str,
        artifact: dict,
    ) -> None:
        """Reject persistence unless every required paid call has one successful pair."""
        if artifact.get("schema_version") != 3:
            raise ValueError("current formal protocol requires artifact schema 3")
        rows = self._transaction_rows(
            conn,
            "SELECT artifact_id,created_utc,artifact_type,content_json "
            "FROM paper_artifacts WHERE artifact_type IN "
            "('llm_invocation_reserved','llm_invocation_result') "
            "ORDER BY created_utc,artifact_type,artifact_id",
        )
        receipts = self._project_invocation_receipts(rows, run_id, decision_date)
        champion = artifact.get("champion")
        without_public = artifact.get("without_public_reaction")
        public_only = artifact.get("public_reaction_only")
        if (
            not isinstance(champion, dict)
            or not isinstance(without_public, dict)
            or (public_only is not None and not isinstance(public_only, dict))
        ):
            raise ValueError("formal decision forecast bundles are malformed")
        expected_by_stage = {"champion": champion}
        if canonical_json(champion.get("evidence")) != canonical_json(
            without_public.get("evidence")
        ):
            expected_by_stage["without_public_reaction"] = without_public
        elif canonical_json(champion) != canonical_json(without_public):
            raise ValueError("formal decision reused evidence without reusing the exact bundle")
        if public_only is not None:
            expected_by_stage["public_reaction_only"] = public_only
        invocation_stage_order = artifact.get("invocation_stage_order")
        if (
            not isinstance(invocation_stage_order, list)
            or any(not isinstance(stage, str) or not stage for stage in invocation_stage_order)
            or len(set(invocation_stage_order)) != len(invocation_stage_order)
            or set(invocation_stage_order) != set(expected_by_stage)
        ):
            raise ValueError("formal decision invocation stage order differs from required calls")
        expected = [
            (ordinal, stage, expected_by_stage[stage])
            for ordinal, stage in enumerate(invocation_stage_order, start=1)
        ]
        if len(receipts) != 2 * len(expected):
            raise ValueError(
                "formal decision invocation receipt set is incomplete or contains extras"
            )
        reservations = {
            row["artifact_id"]: row
            for row in receipts
            if row.get("artifact_type") == "llm_invocation_reserved"
        }
        results = [row for row in receipts if row.get("artifact_type") == "llm_invocation_result"]
        if len(reservations) != len(expected) or len(results) != len(expected):
            raise ValueError("formal decision requires one reservation and result per invocation")
        paired_reservations: set[str] = set()
        expected_by_ordinal = {ordinal: (stage, bundle) for ordinal, stage, bundle in expected}
        for result_row in results:
            result = result_row["content"]
            reservation_id = result.get("reservation_artifact_id")
            reservation_row = reservations.get(reservation_id)
            if reservation_row is None or reservation_id in paired_reservations:
                raise ValueError("formal decision invocation receipts are orphaned or duplicated")
            paired_reservations.add(reservation_id)
            reservation = reservation_row["content"]
            ordinal = reservation.get("ordinal")
            if type(ordinal) is not int:
                raise ValueError("formal decision invocation ordinal is malformed")
            expected_stage = expected_by_ordinal.get(ordinal)
            if expected_stage is None:
                raise ValueError("formal decision invocation ordinal is unexpected")
            stage, forecast_bundle = expected_stage
            identity_fields = (
                "schema_version",
                "invocation_id",
                "scope",
                "run_id",
                "decision_date",
                "ordinal",
                "stage",
                "provider",
                "requested_model",
                "input_bundle_id",
            )
            if (
                reservation.get("schema_version") != 2
                or reservation.get("stage") != stage
                or result.get("status") != "success"
                or any(
                    canonical_json(reservation.get(field)) != canonical_json(result.get(field))
                    for field in identity_fields
                )
                or not isinstance(forecast_bundle, dict)
                or reservation.get("input_bundle_id") != forecast_bundle.get("input_bundle_id")
                or reservation.get("provider") != forecast_bundle.get("provider")
                or reservation.get("requested_model") != forecast_bundle.get("requested_model")
                or not isinstance(forecast_bundle.get("response_id"), str)
                or not forecast_bundle["response_id"].strip()
                or result.get("response_id") != forecast_bundle.get("response_id")
                or result.get("model_id") != forecast_bundle.get("model_id")
                or canonical_json(result.get("usage_metadata"))
                != canonical_json(forecast_bundle.get("usage_metadata"))
                or result.get("forecast_bundle_id") != content_id(forecast_bundle, prefix="bundle_")
            ):
                raise ValueError("formal decision invocation receipts do not match stored bundles")
        if len(paired_reservations) != len(reservations):
            raise ValueError("formal decision has an orphan invocation reservation")

    def record_formal_decision(
        self,
        *,
        run_id: str,
        decision_date: str,
        entry_date: str,
        created_utc: float,
        protocol_id: str,
        build_id: str,
        model_id: str,
        input_bundle_id: str,
        artifact_id: str,
        artifact: dict,
        coverage: dict,
        events: list[dict],
        forecasts: list[dict],
        strategy_targets: dict[str, dict],
    ) -> None:
        """Atomically append the exact evidence bundle and every synchronized target."""
        with self._trial_lifecycle_transaction(run_id) as conn:
            config = self._validate_formal_decision_slot(conn, run_id, decision_date, entry_date)
            if config.get("protocol_id") != protocol_id:
                raise ValueError("formal decision protocol differs from its registered run")
            starts = self._transaction_rows(
                conn,
                "SELECT attempt_ordinal,entry_date,created_utc FROM "
                "paper_decision_attempt_events WHERE run_id=:run_id "
                "AND decision_date=:decision_date AND event_type='started' "
                "ORDER BY attempt_ordinal DESC LIMIT 1",
                {"run_id": run_id, "decision_date": decision_date},
            )
            if len(starts) != 1:
                raise ValueError("formal decision requires a recorded attempt start")
            latest_start = starts[0]
            failures = self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_decision_attempt_events "
                "WHERE run_id=:run_id AND decision_date=:decision_date "
                "AND attempt_ordinal=:attempt_ordinal AND event_type='failed'",
                {
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "attempt_ordinal": latest_start["attempt_ordinal"],
                },
            )
            if failures:
                raise ValueError("latest formal decision attempt is already failed")
            if latest_start["entry_date"] != entry_date:
                raise ValueError("formal decision entry date differs from its attempt")
            if float(created_utc) < float(latest_start["created_utc"]):
                raise ValueError("formal decision persistence precedes its attempt")
            required_strategies = set(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
            if (
                not isinstance(strategy_targets, dict)
                or set(strategy_targets) != required_strategies
            ):
                raise ValueError(
                    "formal decision targets must contain the exact frozen strategy set"
                )
            if not isinstance(artifact, dict) or canonical_json(
                artifact.get("strategy_targets")
            ) != canonical_json(strategy_targets):
                raise ValueError("formal decision artifact and persisted strategy targets differ")
            attempt_ordinal = int(latest_start["attempt_ordinal"])
            if artifact.get("attempt_ordinal") != attempt_ordinal:
                raise ValueError(
                    "formal decision artifact differs from its exact successful attempt"
                )
            expected_artifact_id = content_id(artifact, prefix="artifact_")
            if artifact_id != expected_artifact_id:
                raise ValueError("formal decision artifact ID is not content-addressed")
            if protocol_id == content_id(GLOBAL_EVENT_V2_PROTOCOL, prefix="protocol_"):
                self._validate_invocation_receipts_before_persistence(
                    conn,
                    run_id=run_id,
                    decision_date=decision_date,
                    artifact=artifact,
                )
            self._execute(
                conn,
                "INSERT INTO paper_artifacts "
                "(artifact_id,created_utc,artifact_type,content_json) VALUES "
                "(:artifact_id,:created_utc,'global_forecast_bundle',:content_json)",
                {
                    "artifact_id": artifact_id,
                    "created_utc": created_utc,
                    "content_json": canonical_json(artifact),
                },
            )
            self._execute(
                conn,
                "INSERT INTO paper_decision_bundles "
                "(run_id,decision_date,attempt_ordinal,created_utc,protocol_id,build_id,model_id,"
                "input_bundle_id,artifact_id,coverage_json) VALUES "
                "(:run_id,:decision_date,:attempt_ordinal,:created_utc,:protocol_id,:build_id,:model_id,"
                ":input_bundle_id,:artifact_id,:coverage_json)",
                {
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "attempt_ordinal": attempt_ordinal,
                    "created_utc": created_utc,
                    "protocol_id": protocol_id,
                    "build_id": build_id,
                    "model_id": model_id,
                    "input_bundle_id": input_bundle_id,
                    "artifact_id": artifact_id,
                    "coverage_json": canonical_json(coverage),
                },
            )
            for event in events:
                self._execute(
                    conn,
                    "INSERT INTO paper_events "
                    "(run_id,decision_date,event_id,payload_json) VALUES "
                    "(:run_id,:decision_date,:event_id,:payload_json)",
                    {
                        "run_id": run_id,
                        "decision_date": decision_date,
                        "event_id": event["event_id"],
                        "payload_json": canonical_json(event),
                    },
                )
            for forecast in forecasts:
                self._execute(
                    conn,
                    "INSERT INTO paper_forecasts "
                    "(run_id,decision_date,ticker,payload_json) VALUES "
                    "(:run_id,:decision_date,:ticker,:payload_json)",
                    {
                        "run_id": run_id,
                        "decision_date": decision_date,
                        "ticker": forecast["ticker"],
                        "payload_json": canonical_json(forecast),
                    },
                )
            for strategy_id, target in strategy_targets.items():
                self._execute(
                    conn,
                    "INSERT INTO paper_strategy_targets "
                    "(run_id,decision_date,strategy_id,entry_date,created_utc,"
                    "weights_json,diagnostics_json) VALUES "
                    "(:run_id,:decision_date,:strategy_id,:entry_date,:created_utc,"
                    ":weights_json,:diagnostics_json)",
                    {
                        "run_id": run_id,
                        "decision_date": decision_date,
                        "strategy_id": strategy_id,
                        "entry_date": entry_date,
                        "created_utc": created_utc,
                        "weights_json": canonical_json(target["weights"]),
                        "diagnostics_json": canonical_json(target.get("diagnostics", {})),
                    },
                )
            champion = strategy_targets["global_events_champion"]["weights"]
            self._execute(
                conn,
                "INSERT INTO paper_targets "
                "(run_id,decision_date,entry_date,created_utc,weights_json) VALUES "
                "(:run_id,:decision_date,:entry_date,:created_utc,:weights_json)",
                {
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "entry_date": entry_date,
                    "created_utc": created_utc,
                    "weights_json": canonical_json(champion),
                },
            )

    def formal_bundle(self, run_id: str, decision_date: str | None = None) -> dict:
        """Load one formal decision and every immutable row needed to verify it.

        This is intentionally a read-only projection.  The returned artifact is
        sufficient for an offline target replay; callers do not need the media
        repository, a market-data provider, or an LLM.
        """
        if decision_date is None:
            dates = self._rows(
                "SELECT MAX(decision_date) AS decision_date "
                "FROM paper_decision_bundles WHERE run_id=:run_id",
                {"run_id": run_id},
            )
            decision_date = dates[0]["decision_date"] if dates else None
        if not decision_date:
            raise ValueError(f"formal run {run_id!r} has no decision bundle")

        params = {"run_id": run_id, "decision_date": decision_date}
        bundle_rows = self._rows(
            "SELECT * FROM paper_decision_bundles WHERE run_id=:run_id "
            "AND decision_date=:decision_date",
            params,
        )
        if len(bundle_rows) != 1:
            raise ValueError(
                f"expected one formal bundle for {run_id}/{decision_date}; found {len(bundle_rows)}"
            )
        bundle = bundle_rows[0]
        bundle["coverage"] = json.loads(bundle.pop("coverage_json"))

        artifact_rows = self._rows(
            "SELECT artifact_id,created_utc,artifact_type,content_json "
            "FROM paper_artifacts WHERE artifact_id=:artifact_id",
            {"artifact_id": bundle["artifact_id"]},
        )
        if len(artifact_rows) != 1:
            raise ValueError(
                f"expected one artifact for {run_id}/{decision_date}; found {len(artifact_rows)}"
            )
        artifact_row = artifact_rows[0]
        artifact_row["content"] = json.loads(artifact_row.pop("content_json"))

        # Receipt rows share the content-addressed artifact table across every
        # run.  Their self-identifying run/date fields provide the exact
        # decision projection; the verifier reconciles the complete set.
        invocation_receipts = self.formal_invocation_receipts(run_id, decision_date)

        events = [
            json.loads(row["payload_json"])
            for row in self._rows(
                "SELECT payload_json FROM paper_events WHERE run_id=:run_id "
                "AND decision_date=:decision_date ORDER BY event_id",
                params,
            )
        ]
        forecasts = [
            json.loads(row["payload_json"])
            for row in self._rows(
                "SELECT payload_json FROM paper_forecasts WHERE run_id=:run_id "
                "AND decision_date=:decision_date ORDER BY ticker",
                params,
            )
        ]
        strategy_targets = {}
        for row in self._rows(
            "SELECT strategy_id,entry_date,created_utc,weights_json,diagnostics_json "
            "FROM paper_strategy_targets WHERE run_id=:run_id "
            "AND decision_date=:decision_date ORDER BY strategy_id",
            params,
        ):
            strategy_targets[row["strategy_id"]] = {
                "entry_date": row["entry_date"],
                "created_utc": row["created_utc"],
                "weights": json.loads(row["weights_json"]),
                "diagnostics": json.loads(row["diagnostics_json"]),
            }

        champion_rows = self._rows(
            "SELECT entry_date,created_utc,weights_json FROM paper_targets "
            "WHERE run_id=:run_id AND decision_date=:decision_date",
            params,
        )
        if len(champion_rows) != 1:
            raise ValueError(
                f"expected one champion target for {run_id}/{decision_date}; "
                f"found {len(champion_rows)}"
            )
        champion_target = champion_rows[0]
        champion_target["weights"] = json.loads(champion_target.pop("weights_json"))

        protocol_rows = self._rows(
            "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
            {"protocol_id": bundle["protocol_id"]},
        )
        if len(protocol_rows) != 1:
            raise ValueError(
                f"expected one protocol manifest for {bundle['protocol_id']}; "
                f"found {len(protocol_rows)}"
            )
        return {
            "bundle": bundle,
            "artifact": artifact_row,
            "events": events,
            "forecasts": forecasts,
            "strategy_targets": strategy_targets,
            "champion_target": champion_target,
            "protocol": json.loads(protocol_rows[0]["manifest_json"]),
            "run_config": self.run_config(run_id),
            "registration": self.confirmatory_registration(run_id),
            "invocation_receipts": invocation_receipts,
        }

    def latest_strategy_weight_snapshot(
        self, run_id: str, strategy_id: str, tickers: list[str]
    ) -> dict:
        """Return current strategy weights together with their immutable lineage."""
        mark = self.latest_strategy_mark(run_id, strategy_id)
        if mark is not None:
            if set(mark["weights"]) != set(tickers):
                raise ValueError("stored strategy mark does not match formal universe")
            return {
                "weights": {ticker: float(mark["weights"][ticker]) for ticker in tickers},
                "source_kind": "strategy_mark",
                "source_session_date": mark["session_date"],
                "source_decision_date": mark["target_decision_date"],
            }
        rows = self._rows(
            "SELECT decision_date,weights_json FROM paper_strategy_targets "
            "WHERE run_id=:run_id AND strategy_id=:strategy_id "
            "ORDER BY decision_date DESC LIMIT 1",
            {"run_id": run_id, "strategy_id": strategy_id},
        )
        if not rows:
            return {
                "weights": dict.fromkeys(tickers, 0.0),
                "source_kind": "initial_zero",
                "source_session_date": None,
                "source_decision_date": None,
            }
        weights = json.loads(rows[0]["weights_json"])
        if set(weights) != set(tickers):
            raise ValueError("stored strategy target does not match formal universe")
        return {
            "weights": {ticker: float(weights[ticker]) for ticker in tickers},
            "source_kind": "strategy_target",
            "source_session_date": None,
            "source_decision_date": rows[0]["decision_date"],
        }

    def latest_strategy_weights(
        self, run_id: str, strategy_id: str, tickers: list[str]
    ) -> dict[str, float]:
        return self.latest_strategy_weight_snapshot(run_id, strategy_id, tickers)["weights"]

    def latest_formal_forecast_snapshot(self, run_id: str) -> dict | None:
        """Return the latest forecast cross-section and its decision identity."""
        dates = self._rows(
            "SELECT MAX(decision_date) AS decision_date FROM paper_forecasts WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        if not dates or not dates[0]["decision_date"]:
            return None
        decision_date = dates[0]["decision_date"]
        rows = self._rows(
            "SELECT payload_json FROM paper_forecasts WHERE run_id=:run_id "
            "AND decision_date=:decision_date ORDER BY ticker",
            {"run_id": run_id, "decision_date": decision_date},
        )
        return {
            "decision_date": decision_date,
            "forecasts": [json.loads(row["payload_json"]) for row in rows],
        }

    def latest_formal_forecasts(self, run_id: str) -> list[dict]:
        snapshot = self.latest_formal_forecast_snapshot(run_id)
        return snapshot["forecasts"] if snapshot is not None else []

    def formal_strategies(self, run_id: str) -> list[str]:
        return [
            row["strategy_id"]
            for row in self._rows(
                "SELECT DISTINCT strategy_id FROM paper_strategy_targets WHERE run_id=:run_id "
                "ORDER BY strategy_id",
                {"run_id": run_id},
            )
        ]

    def interval_assignment_for_session(self, run_id: str, session_date: str) -> dict | None:
        rows = self._rows(
            "SELECT run_id,interval_index,from_session_date,session_date,"
            "scheduled_decision_date,created_utc,disposition,"
            "applied_target_decision_date,return_vector_id "
            "FROM paper_interval_assignments WHERE run_id=:run_id "
            "AND session_date=:session_date",
            {"run_id": run_id, "session_date": session_date},
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("formal session has multiple interval assignments")
        return rows[0]

    def formal_trial_counts(self, run_id: str) -> dict:
        """Derive ITT completeness from immutable decisions and held intervals."""
        assignments = self._rows(
            "SELECT interval_index,from_session_date,session_date,"
            "scheduled_decision_date,disposition,applied_target_decision_date "
            "FROM paper_interval_assignments WHERE run_id=:run_id "
            "ORDER BY interval_index",
            {"run_id": run_id},
        )
        indices = [int(row["interval_index"]) for row in assignments]
        index_contiguous = indices == list(range(1, len(indices) + 1))
        dates_contiguous = True
        for index, row in enumerate(assignments):
            if next_session_date(row["from_session_date"]) != row["session_date"]:
                dates_contiguous = False
                break
            if index and assignments[index - 1]["session_date"] != row["from_session_date"]:
                dates_contiguous = False
                break

        events = self.formal_attempt_events(run_id)
        starts = {
            (row["decision_date"], int(row["attempt_ordinal"]))
            for row in events
            if row["event_type"] == "started"
        }
        failures = {
            (row["decision_date"], int(row["attempt_ordinal"]))
            for row in events
            if row["event_type"] == "failed"
        }
        successful_attempts = {
            (row["decision_date"], int(row["attempt_ordinal"]))
            for row in self._rows(
                "SELECT decision_date,attempt_ordinal FROM paper_decision_bundles "
                "WHERE run_id=:run_id",
                {"run_id": run_id},
            )
        }
        unmatched = starts - failures
        resolved = unmatched & successful_attempts
        unresolved = unmatched - resolved
        return {
            "completed_intervals": len(assignments),
            "successful_decision_sets": sum(
                row["disposition"] == "target_applied" for row in assignments
            ),
            "carry_forward_intervals": sum(
                row["disposition"] == "carry_forward_missing_decision" for row in assignments
            ),
            "first_completed_interval_date": (
                assignments[0]["session_date"] if assignments else None
            ),
            "last_completed_interval_date": (
                assignments[-1]["session_date"] if assignments else None
            ),
            "assignment_indices_contiguous": index_contiguous,
            "assignment_dates_contiguous": dates_contiguous,
            "attempts_started": len(starts),
            "attempts_failed": len(failures),
            "attempts_without_failure_event": len(unmatched),
            "attempts_resolved_by_decision_bundle": len(resolved),
            "unresolved_attempts_without_terminal_event": len(unresolved),
        }

    def strategy_target_for_entry(
        self, run_id: str, strategy_id: str, entry_date: str
    ) -> dict | None:
        rows = self._rows(
            "SELECT decision_date,weights_json FROM paper_strategy_targets "
            "WHERE run_id=:run_id AND strategy_id=:strategy_id AND entry_date=:entry_date",
            {"run_id": run_id, "strategy_id": strategy_id, "entry_date": entry_date},
        )
        if not rows:
            return None
        return {
            "decision_date": rows[0]["decision_date"],
            "weights": json.loads(rows[0]["weights_json"]),
        }

    def latest_strategy_mark(self, run_id: str, strategy_id: str) -> dict | None:
        rows = self._rows(
            "SELECT * FROM paper_strategy_marks WHERE run_id=:run_id "
            "AND strategy_id=:strategy_id ORDER BY session_date DESC LIMIT 1",
            {"run_id": run_id, "strategy_id": strategy_id},
        )
        if not rows:
            return None
        row = rows[0]
        row["weights"] = json.loads(row.pop("weights_json"))
        row["opens"] = json.loads(row.pop("opens_json"))
        return row

    def record_strategy_mark(self, run_id: str, strategy_id: str, mark: dict) -> None:
        payload = dict(mark)
        payload.update(
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "weights_json": canonical_json(payload.pop("weights")),
                "opens_json": canonical_json(payload.pop("opens")),
            }
        )
        with self._trial_lifecycle_transaction(run_id) as conn:
            runs = self._transaction_rows(
                conn,
                "SELECT config_json FROM paper_runs WHERE run_id=:run_id",
                {"run_id": run_id},
            )
            if len(runs) != 1:
                raise ValueError(f"unknown paper run {run_id!r}")
            config = json.loads(runs[0]["config_json"])
            registered = self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_run_labels WHERE run_id=:run_id AND label=:label",
                {"run_id": run_id, "label": CONFIRMATORY_TRIAL_LABEL},
            )
            if config.get("engine") == "formal-global-v2" and registered:
                self._require_registered_formal_run(conn, run_id)
                champion_rows = self._transaction_rows(
                    conn,
                    "SELECT captured_utc,target_decision_date FROM paper_marks "
                    "WHERE run_id=:run_id AND session_date=:session_date",
                    {"run_id": run_id, "session_date": mark["session_date"]},
                )
                if len(champion_rows) != 1:
                    raise ValueError("formal strategy mark requires its champion mark")
                champion = champion_rows[0]
                if (
                    float(mark["captured_utc"]) != float(champion["captured_utc"])
                    or mark["target_decision_date"] != champion["target_decision_date"]
                ):
                    raise ValueError("formal strategy mark disagrees with champion timing")
                prior_rows = self._transaction_rows(
                    conn,
                    "SELECT session_date,turnover,trading_cost,target_decision_date "
                    "FROM paper_strategy_marks WHERE run_id=:run_id "
                    "AND strategy_id=:strategy_id ORDER BY session_date DESC LIMIT 1",
                    {"run_id": run_id, "strategy_id": strategy_id},
                )
                assignment_rows = self._transaction_rows(
                    conn,
                    "SELECT from_session_date,created_utc,disposition,"
                    "applied_target_decision_date FROM paper_interval_assignments "
                    "WHERE run_id=:run_id AND session_date=:session_date",
                    {"run_id": run_id, "session_date": mark["session_date"]},
                )
                if not prior_rows:
                    if assignment_rows:
                        raise ValueError("initial formal strategy mark cannot complete an interval")
                else:
                    if len(assignment_rows) != 1:
                        raise ValueError("formal strategy mark requires one interval assignment")
                    prior = prior_rows[0]
                    assignment = assignment_rows[0]
                    if (
                        prior["session_date"] != assignment["from_session_date"]
                        or float(mark["captured_utc"]) != float(assignment["created_utc"])
                        or prior["target_decision_date"]
                        != assignment["applied_target_decision_date"]
                    ):
                        raise ValueError("formal strategy mark disagrees with interval assignment")
                    expected_disposition = (
                        "target_applied"
                        if prior["target_decision_date"] is not None
                        else "carry_forward_missing_decision"
                    )
                    if assignment["disposition"] != expected_disposition:
                        raise ValueError("formal strategy mark has the wrong ITT disposition")
                    if expected_disposition == "carry_forward_missing_decision" and (
                        float(prior["turnover"]) != 0.0 or float(prior["trading_cost"]) != 0.0
                    ):
                        raise ValueError("formal carry-forward interval began with a trade")
            self._execute(
                conn,
                """
                INSERT INTO paper_strategy_marks
                (run_id,strategy_id,session_date,captured_utc,nav,benchmark_nav,
                 period_return,benchmark_period_return,turnover,trading_cost,borrow_cost,
                 weights_json,opens_json,benchmark_open,target_decision_date)
                VALUES (:run_id,:strategy_id,:session_date,:captured_utc,:nav,:benchmark_nav,
                        :period_return,:benchmark_period_return,:turnover,:trading_cost,:borrow_cost,
                        :weights_json,:opens_json,:benchmark_open,:target_decision_date)
            """,
                payload,
            )

    def price_capture_attempt_events(
        self, run_id: str, session_date: str | None = None
    ) -> list[dict]:
        where = "WHERE run_id=:run_id"
        params: dict[str, object] = {"run_id": run_id}
        if session_date is not None:
            where += " AND session_date=:session_date"
            params["session_date"] = session_date
        return self._rows(
            "SELECT run_id,session_date,attempt_ordinal,event_type,created_utc,"
            f"reason_code FROM paper_price_capture_attempt_events {where} "
            "ORDER BY session_date,attempt_ordinal,event_type DESC",
            params,
        )

    def record_price_capture_attempt_started(
        self, run_id: str, session_date: str, created_utc: float
    ) -> int:
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("price capture attempt time must be finite")
        with self._trial_lifecycle_transaction(run_id) as conn:
            self._require_registered_formal_run(conn, run_id)
            if self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_price_integrity_failures WHERE run_id=:run_id",
                {"run_id": run_id},
            ):
                raise FormalPriceIntegrityError(
                    f"formal price capture {run_id}/{session_date} is terminal"
                )
            if self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_price_capture_batches "
                "WHERE run_id=:run_id AND session_date=:session_date",
                {"run_id": run_id, "session_date": session_date},
            ):
                raise ValueError("formal price capture is already complete")
            rows = self._transaction_rows(
                conn,
                "SELECT MAX(attempt_ordinal) AS ordinal "
                "FROM paper_price_capture_attempt_events "
                "WHERE run_id=:run_id AND session_date=:session_date",
                {"run_id": run_id, "session_date": session_date},
            )
            ordinal = int(rows[0]["ordinal"] or 0) + 1
            self._execute(
                conn,
                "INSERT INTO paper_price_capture_attempt_events "
                "(run_id,session_date,attempt_ordinal,event_type,created_utc,"
                "observed_utc,reason_code) VALUES "
                "(:run_id,:session_date,:attempt_ordinal,'started',:created_utc,"
                ":created_utc,NULL)",
                {
                    "run_id": run_id,
                    "session_date": session_date,
                    "attempt_ordinal": ordinal,
                    "created_utc": float(created_utc),
                },
            )
        return ordinal

    def record_price_capture_attempt_failed(
        self,
        run_id: str,
        session_date: str,
        attempt_ordinal: int,
        created_utc: float,
        reason_code: str,
    ) -> bool:
        if reason_code not in FORMAL_PRICE_ATTEMPT_FAILURE_REASON_CODES:
            raise ValueError("price capture failure reason is not allowlisted")
        if type(attempt_ordinal) is not int or attempt_ordinal < 1:
            raise ValueError("price capture attempt ordinal is invalid")
        if (
            isinstance(created_utc, bool)
            or not isinstance(created_utc, (int, float))
            or not math.isfinite(float(created_utc))
        ):
            raise ValueError("price capture failure time must be finite")
        with self._trial_lifecycle_transaction(run_id) as conn:
            self._require_registered_formal_run(conn, run_id)
            starts = self._transaction_rows(
                conn,
                "SELECT created_utc FROM paper_price_capture_attempt_events "
                "WHERE run_id=:run_id AND session_date=:session_date "
                "AND attempt_ordinal=:attempt_ordinal AND event_type='started'",
                {
                    "run_id": run_id,
                    "session_date": session_date,
                    "attempt_ordinal": attempt_ordinal,
                },
            )
            if len(starts) != 1 or float(created_utc) < float(starts[0]["created_utc"]):
                raise ValueError("price capture failure has no valid started event")
            existing = self._transaction_rows(
                conn,
                "SELECT created_utc,reason_code FROM paper_price_capture_attempt_events "
                "WHERE run_id=:run_id AND session_date=:session_date "
                "AND attempt_ordinal=:attempt_ordinal AND event_type='failed'",
                {
                    "run_id": run_id,
                    "session_date": session_date,
                    "attempt_ordinal": attempt_ordinal,
                },
            )
            if existing:
                if len(existing) != 1 or existing[0]["reason_code"] != reason_code:
                    raise ValueError("price capture attempt has a different failure event")
                return False
            self._execute(
                conn,
                "INSERT INTO paper_price_capture_attempt_events "
                "(run_id,session_date,attempt_ordinal,event_type,created_utc,"
                "observed_utc,reason_code) "
                "VALUES (:run_id,:session_date,:attempt_ordinal,'failed',"
                ":created_utc,:created_utc,:reason_code)",
                {
                    "run_id": run_id,
                    "session_date": session_date,
                    "attempt_ordinal": attempt_ordinal,
                    "created_utc": float(created_utc),
                    "reason_code": reason_code,
                },
            )
        return True

    def price_integrity_failure(self, run_id: str, session_date: str | None = None) -> dict | None:
        where = "WHERE run_id=:run_id"
        params: dict[str, object] = {"run_id": run_id}
        if session_date is not None:
            where += " AND session_date=:session_date"
            params["session_date"] = session_date
        rows = self._rows(
            "SELECT run_id,session_date,failure_id,detected_utc,scheduled_utc,"
            "deadline_utc,last_attempt_ordinal,reason_code,payload_json "
            f"FROM paper_price_integrity_failures {where} ORDER BY session_date LIMIT 2",
            params,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("formal run contains multiple terminal price failures")
        row = rows[0]
        row["payload"] = json.loads(row.pop("payload_json"))
        return row

    def record_price_integrity_failure(
        self,
        run_id: str,
        session_date: str,
        *,
        detected_utc: float,
        scheduled_utc: float,
        deadline_utc: float,
        reason_code: str,
    ) -> dict:
        if reason_code not in FORMAL_PRICE_INTEGRITY_FAILURE_REASON_CODES:
            raise ValueError("price integrity failure reason is not allowlisted")
        values = (detected_utc, scheduled_utc, deadline_utc)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ) or float(detected_utc) < float(deadline_utc):
            raise ValueError("terminal price failure timing is invalid")
        attempts = self.price_capture_attempt_events(run_id, session_date)
        last_ordinal = max((int(row["attempt_ordinal"]) for row in attempts), default=0)
        base = {
            "schema_version": 1,
            "run_id": run_id,
            "session_date": session_date,
            "detected_utc": float(detected_utc),
            "scheduled_utc": float(scheduled_utc),
            "deadline_utc": float(deadline_utc),
            "last_attempt_ordinal": last_ordinal,
            "reason_code": reason_code,
        }
        payload = {
            **base,
            "failure_id": content_id(base, prefix="price_failure_"),
        }
        existing = self.price_integrity_failure(run_id, session_date)
        if existing is not None:
            if existing["payload"] != payload:
                raise ValueError("formal price capture already has a different terminal failure")
            return payload
        with self._trial_lifecycle_transaction(run_id) as conn:
            self._require_registered_formal_run(conn, run_id)
            completed = self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_price_capture_batches "
                "WHERE run_id=:run_id AND session_date=:session_date",
                {"run_id": run_id, "session_date": session_date},
            )
            if completed:
                raise ValueError("cannot fail an already completed price capture")
            self._execute(
                conn,
                "INSERT INTO paper_price_integrity_failures "
                "(run_id,session_date,failure_id,detected_utc,scheduled_utc,"
                "deadline_utc,last_attempt_ordinal,reason_code,payload_json) VALUES "
                "(:run_id,:session_date,:failure_id,:detected_utc,:scheduled_utc,"
                ":deadline_utc,:last_attempt_ordinal,:reason_code,:payload_json)",
                {**payload, "payload_json": canonical_json(payload)},
            )
        try:
            emit_alert(
                "paper-worker",
                "formal_price_capture_terminal",
                details={
                    "run_id": run_id,
                    "session_date": session_date,
                    "reason_code": reason_code,
                },
            )
        except Exception:  # noqa: BLE001 - the durable terminal row is authoritative
            logger.exception("Could not deliver formal price terminal alert")
        return payload

    def price_capture_batch(self, run_id: str, session_date: str) -> dict | None:
        rows = self._rows(
            "SELECT * FROM paper_price_capture_batches "
            "WHERE run_id=:run_id AND session_date=:session_date",
            {"run_id": run_id, "session_date": session_date},
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("formal session has multiple price capture batches")
        row = rows[0]
        row["receipt_manifest"] = json.loads(row.pop("receipt_manifest_json"))
        row["payload"] = json.loads(row.pop("payload_json"))
        return row

    def price_capture_operational_manifest(self, run_id: str) -> dict:
        """Return outcome-blind capture identities, timing, and completeness only."""
        batches = self._rows(
            "SELECT session_date,capture_batch_id,attempt_ordinal,from_session_date,"
            "scheduled_utc,started_utc,completed_utc,persisted_utc,deadline_utc,vendor,"
            "paper_build_id,return_vector_id,receipt_manifest_json "
            "FROM paper_price_capture_batches WHERE run_id=:run_id ORDER BY session_date",
            {"run_id": run_id},
        )
        failures = self._rows(
            "SELECT session_date,failure_id,detected_utc,scheduled_utc,deadline_utc,"
            "last_attempt_ordinal,reason_code FROM paper_price_integrity_failures "
            "WHERE run_id=:run_id ORDER BY session_date",
            {"run_id": run_id},
        )
        attempts = self._rows(
            "SELECT session_date,attempt_ordinal,event_type,created_utc,observed_utc,"
            "reason_code "
            "FROM paper_price_capture_attempt_events WHERE run_id=:run_id "
            "ORDER BY session_date,attempt_ordinal,event_type DESC",
            {"run_id": run_id},
        )
        normalized = []
        for row in batches:
            normalized.append(
                {
                    **{key: row[key] for key in row if key != "receipt_manifest_json"},
                    "receipt_manifest": json.loads(row["receipt_manifest_json"]),
                }
            )
        return {
            "attempt_events": attempts,
            "batches": normalized,
            "terminal_failures": failures,
        }

    def record_price_receipts(self, run_id: str, receipts: list[dict]) -> None:
        with self._trial_lifecycle_transaction(run_id) as conn:
            for receipt in receipts:
                self._execute(
                    conn,
                    "INSERT INTO paper_price_receipts "
                    "(run_id,session_date,ticker,captured_utc,vendor,raw_open,"
                    "adjusted_open,dividend,split_ratio,capture_batch_id,"
                    "price_receipt_id,vendor_snapshot_id,receipt_identity_json,"
                    "vendor_snapshot_identity_json,payload_json) VALUES "
                    "(:run_id,:session_date,:ticker,:captured_utc,:vendor,:raw_open,"
                    ":adjusted_open,:dividend,:split_ratio,:capture_batch_id,"
                    ":price_receipt_id,:vendor_snapshot_id,:receipt_identity_json,"
                    ":vendor_snapshot_identity_json,:payload_json)",
                    {
                        "run_id": run_id,
                        **receipt,
                        "capture_batch_id": receipt.get("capture_batch_id"),
                        "price_receipt_id": receipt.get("price_receipt_id"),
                        "vendor_snapshot_id": receipt.get("vendor_snapshot_id"),
                        "receipt_identity_json": (
                            canonical_json(_price_receipt_identity_payload(receipt))
                            if receipt.get("price_receipt_id")
                            else None
                        ),
                        "vendor_snapshot_identity_json": (
                            canonical_json(
                                _vendor_snapshot_identity_payload(receipt["vendor_snapshot"])
                            )
                            if receipt.get("vendor_snapshot_id")
                            else None
                        ),
                        "payload_json": canonical_json(receipt),
                    },
                )

    def return_vector_for_session(
        self, run_id: str, session_date: str, symbols: list[str]
    ) -> dict | None:
        """Rebuild and fully authenticate one immutable price batch/vector v2."""
        expected = list(dict.fromkeys(symbols))
        if (
            len(expected) != len(symbols)
            or not expected
            or any(not isinstance(symbol, str) or not symbol for symbol in expected)
        ):
            raise ValueError("return-vector symbols must be non-empty strings")
        batch_row = self.price_capture_batch(run_id, session_date)
        rows = self._rows(
            "SELECT ticker,captured_utc,vendor,raw_open,adjusted_open,dividend,"
            "split_ratio,capture_batch_id,price_receipt_id,vendor_snapshot_id,"
            "receipt_identity_json,vendor_snapshot_identity_json,"
            "payload_json FROM paper_price_receipts "
            "WHERE run_id=:run_id AND session_date=:session_date ORDER BY ticker",
            {"run_id": run_id, "session_date": session_date},
        )
        if batch_row is None and not rows:
            return None
        if batch_row is None:
            raise ValueError("stored price receipts have no authenticated capture batch")
        if {row["ticker"] for row in rows} != set(expected) or len(rows) != len(expected):
            raise ValueError("stored price receipts do not exactly match the return universe")

        receipts = []
        return_items = {}
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("price-receipt payload is malformed") from exc
            if not isinstance(payload, dict):
                raise ValueError("price-receipt payload is malformed")
            scalar_fields = (
                "captured_utc",
                "vendor",
                "raw_open",
                "adjusted_open",
                "dividend",
                "split_ratio",
                "capture_batch_id",
                "price_receipt_id",
                "vendor_snapshot_id",
            )
            if (
                payload.get("ticker") != row["ticker"]
                or payload.get("session_date") != session_date
                or any(payload.get(field) != row[field] for field in scalar_fields)
            ):
                raise ValueError("price-receipt payload disagrees with its stored row")
            try:
                receipt_identity = canonical_json(_price_receipt_identity_payload(payload))
                snapshot_identity = canonical_json(
                    _vendor_snapshot_identity_payload(payload["vendor_snapshot"])
                )
            except (KeyError, TypeError) as exc:
                raise ValueError("price-receipt identity material is malformed") from exc
            if (
                row["receipt_identity_json"] != receipt_identity
                or row["vendor_snapshot_identity_json"] != snapshot_identity
            ):
                raise ValueError("price-receipt identity material disagrees with payload")
            receipts.append(payload)
            item = payload.get("return_vector")
            if item is not None:
                if not isinstance(item, dict):
                    raise ValueError("return-vector component is malformed")
                return_items[row["ticker"]] = item

        if return_items and len(return_items) != len(rows):
            raise ValueError("stored return vector is only partially populated")
        vector = None
        if return_items:
            first = return_items[expected[0]]
            header_keys = (
                "return_vector_id",
                "schema_version",
                "from_session",
                "to_session",
                "captured_utc",
                "scheduled_utc",
                "deadline_utc",
                "vendor",
                "cash_component",
            )
            header = {key: first.get(key) for key in header_keys}
            for item in return_items.values():
                if any(item.get(key) != header[key] for key in header_keys):
                    raise ValueError("stored return-vector components disagree")
            component_keys = {
                "price_receipt_id",
                "vendor_snapshot_id",
                "previous_adjusted_open",
                "current_adjusted_open",
                "current_raw_open",
                "cash_dividend",
                "split_ratio",
                "open_return",
            }
            components = {
                ticker: {key: return_items[ticker].get(key) for key in component_keys}
                for ticker in expected
            }
            vector = {
                **header,
                "components": components,
            }
        batch = {
            "capture_batch_id": batch_row["capture_batch_id"],
            "schema_version": batch_row["payload"].get("schema_version"),
            "session_date": batch_row["session_date"],
            "from_session_date": batch_row["from_session_date"],
            "attempt_ordinal": int(batch_row["attempt_ordinal"]),
            "scheduled_utc": batch_row["scheduled_utc"],
            "started_utc": batch_row["started_utc"],
            "completed_utc": batch_row["completed_utc"],
            "deadline_utc": batch_row["deadline_utc"],
            "vendor": batch_row["vendor"],
            "paper_build_id": batch_row["paper_build_id"],
            "return_vector_id": batch_row["return_vector_id"],
            "receipt_manifest": batch_row["receipt_manifest"],
            "receipts": receipts,
            "return_vector": vector,
        }
        try:
            expected_batch_identity = canonical_json(_price_batch_identity_payload(batch))
            expected_vector_identity = (
                canonical_json(_return_vector_identity_payload(vector))
                if vector is not None
                else None
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("stored price batch identity material is malformed") from exc
        if (
            batch_row.get("capture_identity_json") != expected_batch_identity
            or batch_row.get("return_vector_identity_json") != expected_vector_identity
        ):
            raise ValueError("stored price batch identity material disagrees with payloads")
        _validate_formal_price_batch_contract(
            batch,
            symbols=expected,
            previous_session=batch["from_session_date"],
            session_date=session_date,
        )
        return vector

    def run_config(self, run_id: str) -> dict:
        rows = self._rows(
            "SELECT config_json FROM paper_runs WHERE run_id=:run_id", {"run_id": run_id}
        )
        if not rows:
            raise ValueError(f"unknown paper run {run_id!r}")
        return json.loads(rows[0]["config_json"])

    def has_decision(self, run_id: str, decision_date: str) -> bool:
        return bool(
            self._rows(
                "SELECT 1 AS found FROM paper_targets "
                "WHERE run_id=:run_id AND decision_date=:decision_date",
                {"run_id": run_id, "decision_date": decision_date},
            )
        )

    def record_decision_set(
        self,
        run_id: str,
        decision_date: str,
        entry_date: str,
        created_utc: float,
        decisions: list[dict],
        weights: dict[str, float],
    ) -> None:
        """Atomically append a complete cross-section; duplicates always fail."""
        with self._trial_lifecycle_transaction(run_id) as conn:
            for row in decisions:
                self._execute(
                    conn,
                    """
                    INSERT INTO paper_decisions
                    (run_id,decision_date,ticker,replicate,created_utc,action,score,
                     data_fingerprint,signal_fingerprint,final_decision)
                    VALUES (:run_id,:decision_date,:ticker,:replicate,:created_utc,:action,
                            :score,:data_fingerprint,:signal_fingerprint,:final_decision)
                """,
                    {
                        **row,
                        "run_id": run_id,
                        "decision_date": decision_date,
                        "created_utc": created_utc,
                    },
                )
            self._execute(
                conn,
                """
                INSERT INTO paper_targets
                (run_id,decision_date,entry_date,created_utc,weights_json)
                VALUES (:run_id,:decision_date,:entry_date,:created_utc,:weights_json)
            """,
                {
                    "run_id": run_id,
                    "decision_date": decision_date,
                    "entry_date": entry_date,
                    "created_utc": created_utc,
                    "weights_json": _canonical(weights),
                },
            )

    def target_for_entry(self, run_id: str, entry_date: str) -> dict | None:
        rows = self._rows(
            "SELECT decision_date,weights_json FROM paper_targets "
            "WHERE run_id=:run_id AND entry_date=:entry_date",
            {"run_id": run_id, "entry_date": entry_date},
        )
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(f"multiple paper targets enter on {entry_date}")
        return {
            "decision_date": rows[0]["decision_date"],
            "weights": json.loads(rows[0]["weights_json"]),
        }

    def first_entry_date(self, run_id: str) -> str | None:
        rows = self._rows(
            "SELECT MIN(entry_date) AS date FROM paper_targets WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        return rows[0]["date"] if rows and rows[0]["date"] else None

    def latest_mark(self, run_id: str) -> dict | None:
        rows = self._rows(
            "SELECT * FROM paper_marks WHERE run_id=:run_id ORDER BY session_date DESC LIMIT 1",
            {"run_id": run_id},
        )
        if not rows:
            return None
        row = rows[0]
        row["weights"] = json.loads(row.pop("weights_json"))
        row["opens"] = json.loads(row.pop("opens_json"))
        return row

    def record_mark(
        self,
        run_id: str,
        mark: dict,
        *,
        price_receipts: list[dict] | None = None,
        price_capture_batch: dict | None = None,
    ) -> None:
        payload = dict(mark)
        # The authenticated vector lives in the receipt payloads.  The ID is
        # returned to callers for observability but is not a paper_marks column.
        return_vector_id = payload.pop("return_vector_id", None)
        payload.update(
            {
                "run_id": run_id,
                "weights_json": _canonical(payload.pop("weights")),
                "opens_json": _canonical(payload.pop("opens")),
            }
        )
        with self._trial_lifecycle_transaction(run_id) as conn:
            runs = self._transaction_rows(
                conn,
                "SELECT config_json FROM paper_runs WHERE run_id=:run_id",
                {"run_id": run_id},
            )
            if len(runs) != 1:
                raise ValueError(f"unknown paper run {run_id!r}")
            config = json.loads(runs[0]["config_json"])
            interval_assignment = None
            registered = self._transaction_rows(
                conn,
                "SELECT 1 AS found FROM paper_run_labels WHERE run_id=:run_id AND label=:label",
                {"run_id": run_id, "label": CONFIRMATORY_TRIAL_LABEL},
            )
            if config.get("engine") == "formal-global-v2" and registered:
                self._require_registered_formal_run(conn, run_id)
                if price_capture_batch is None:
                    raise ValueError("formal mark requires an authenticated price batch")
                receipts = price_capture_batch.get("receipts")
                if not isinstance(receipts, list):
                    raise ValueError("formal price batch receipts are malformed")
                if price_receipts is not None and price_receipts != receipts:
                    raise ValueError("formal mark received conflicting price receipts")
                expected_symbols = {*config.get("tickers", []), config.get("benchmark")}
                receipt_symbols = {receipt.get("ticker") for receipt in receipts}
                if (
                    None in expected_symbols
                    or receipt_symbols != expected_symbols
                    or len(receipts) != len(expected_symbols)
                ):
                    raise ValueError("formal mark requires one receipt per return symbol")
                if any(
                    receipt.get("session_date") != mark["session_date"]
                    or float(receipt.get("captured_utc", math.nan)) != float(mark["captured_utc"])
                    for receipt in receipts
                ):
                    raise ValueError("formal mark receipts disagree with its capture")
                prior_rows = self._transaction_rows(
                    conn,
                    "SELECT session_date,captured_utc,turnover,trading_cost,"
                    "target_decision_date FROM paper_marks WHERE run_id=:run_id "
                    "ORDER BY session_date DESC LIMIT 1",
                    {"run_id": run_id},
                )
                previous_session = prior_rows[0]["session_date"] if prior_rows else None
                _validate_formal_price_batch_contract(
                    price_capture_batch,
                    symbols=[*config.get("tickers", []), config.get("benchmark")],
                    previous_session=previous_session,
                    session_date=mark["session_date"],
                )
                if price_capture_batch.get("return_vector_id") != return_vector_id or float(
                    price_capture_batch["completed_utc"]
                ) != float(mark["captured_utc"]):
                    raise ValueError("formal mark disagrees with its price batch")
                attempt_rows = self._transaction_rows(
                    conn,
                    "SELECT event_type FROM paper_price_capture_attempt_events "
                    "WHERE run_id=:run_id AND session_date=:session_date "
                    "AND attempt_ordinal=:attempt_ordinal",
                    {
                        "run_id": run_id,
                        "session_date": mark["session_date"],
                        "attempt_ordinal": price_capture_batch["attempt_ordinal"],
                    },
                )
                if [row["event_type"] for row in attempt_rows] != ["started"]:
                    raise ValueError("formal price batch has no unresolved started attempt")
                if self._transaction_rows(
                    conn,
                    "SELECT 1 AS found FROM paper_price_integrity_failures WHERE run_id=:run_id",
                    {"run_id": run_id},
                ):
                    raise FormalPriceIntegrityError(
                        "terminal price integrity failure blocks further formal marks"
                    )
                if not prior_rows:
                    if return_vector_id is not None:
                        raise ValueError("formal initialization mark cannot have a return vector")
                    if any(receipt.get("return_vector") is not None for receipt in receipts):
                        raise ValueError(
                            "formal initialization receipts cannot have a return vector"
                        )
                    if mark["target_decision_date"] is None:
                        raise ValueError("formal initialization mark requires a target")
                    expected_decision = (
                        _calendar()
                        .previous_session(pd.Timestamp(mark["session_date"]))
                        .date()
                        .isoformat()
                    )
                    if mark["target_decision_date"] != expected_decision:
                        raise ValueError("formal initialization target has the wrong date")
                    targets = self._transaction_rows(
                        conn,
                        "SELECT 1 AS found FROM paper_targets AS target "
                        "JOIN paper_decision_bundles AS bundle "
                        "ON bundle.run_id=target.run_id "
                        "AND bundle.decision_date=target.decision_date "
                        "WHERE target.run_id=:run_id "
                        "AND target.decision_date=:decision_date "
                        "AND target.entry_date=:entry_date",
                        {
                            "run_id": run_id,
                            "decision_date": expected_decision,
                            "entry_date": mark["session_date"],
                        },
                    )
                    if len(targets) != 1:
                        raise ValueError("formal initialization target is not frozen")
                else:
                    prior = prior_rows[0]
                    if next_session_date(prior["session_date"]) != mark["session_date"]:
                        raise ValueError("formal marks must be consecutive XNYS sessions")
                    if not isinstance(return_vector_id, str) or not return_vector_id.startswith(
                        "return_vector_"
                    ):
                        raise ValueError("formal completed interval requires a return vector")
                    if any(
                        not isinstance(receipt.get("return_vector"), dict)
                        or receipt["return_vector"].get("return_vector_id") != return_vector_id
                        for receipt in receipts
                    ):
                        raise ValueError("formal receipt vector identity is inconsistent")
                    index_rows = self._transaction_rows(
                        conn,
                        "SELECT MAX(interval_index) AS interval_index "
                        "FROM paper_interval_assignments WHERE run_id=:run_id",
                        {"run_id": run_id},
                    )
                    previous_index = index_rows[0]["interval_index"] if index_rows else None
                    interval_index = int(previous_index or 0) + 1
                    if interval_index > FORMAL_HOLDING_INTERVALS:
                        raise ValueError("formal confirmatory holding horizon is already complete")
                    scheduled_decision_date = (
                        _calendar()
                        .previous_session(pd.Timestamp(prior["session_date"]))
                        .date()
                        .isoformat()
                    )
                    applied_target = prior["target_decision_date"]
                    disposition = (
                        "target_applied"
                        if applied_target is not None
                        else "carry_forward_missing_decision"
                    )
                    if disposition not in FORMAL_INTERVAL_DISPOSITIONS:
                        raise ValueError("formal interval disposition is invalid")
                    if applied_target is not None:
                        if applied_target != scheduled_decision_date:
                            raise ValueError("formal interval used a target from the wrong date")
                        targets = self._transaction_rows(
                            conn,
                            "SELECT 1 AS found FROM paper_targets AS target "
                            "JOIN paper_decision_bundles AS bundle "
                            "ON bundle.run_id=target.run_id "
                            "AND bundle.decision_date=target.decision_date "
                            "WHERE target.run_id=:run_id "
                            "AND target.decision_date=:decision_date "
                            "AND target.entry_date=:entry_date",
                            {
                                "run_id": run_id,
                                "decision_date": applied_target,
                                "entry_date": prior["session_date"],
                            },
                        )
                        if len(targets) != 1:
                            raise ValueError("formal interval target is not frozen")
                    elif float(prior["turnover"]) != 0.0 or float(prior["trading_cost"]) != 0.0:
                        raise ValueError("formal carry-forward interval began with a trade")
                    interval_assignment = {
                        "run_id": run_id,
                        "interval_index": interval_index,
                        "from_session_date": prior["session_date"],
                        "session_date": mark["session_date"],
                        "scheduled_decision_date": scheduled_decision_date,
                        "created_utc": float(mark["captured_utc"]),
                        "disposition": disposition,
                        "applied_target_decision_date": applied_target,
                        "return_vector_id": return_vector_id,
                    }
                batch_payload = {
                    key: value
                    for key, value in price_capture_batch.items()
                    if key not in {"receipts", "return_vector"}
                }
                self._execute(
                    conn,
                    "INSERT INTO paper_price_capture_batches "
                    "(run_id,session_date,capture_batch_id,attempt_ordinal,"
                    "from_session_date,scheduled_utc,started_utc,completed_utc,"
                    "persisted_utc,deadline_utc,vendor,paper_build_id,return_vector_id,"
                    "receipt_manifest_json,"
                    "capture_identity_json,return_vector_identity_json,payload_json) "
                    "VALUES (:run_id,:session_date,:capture_batch_id,"
                    ":attempt_ordinal,:from_session_date,:scheduled_utc,:started_utc,"
                    ":completed_utc,:completed_utc,:deadline_utc,:vendor,:paper_build_id,"
                    ":return_vector_id,"
                    ":receipt_manifest_json,:capture_identity_json,"
                    ":return_vector_identity_json,:payload_json)",
                    {
                        "run_id": run_id,
                        **batch_payload,
                        "receipt_manifest_json": canonical_json(
                            price_capture_batch["receipt_manifest"]
                        ),
                        "capture_identity_json": canonical_json(
                            _price_batch_identity_payload(price_capture_batch)
                        ),
                        "return_vector_identity_json": (
                            canonical_json(
                                _return_vector_identity_payload(
                                    price_capture_batch["return_vector"]
                                )
                            )
                            if price_capture_batch["return_vector"] is not None
                            else None
                        ),
                        "payload_json": canonical_json(batch_payload),
                    },
                )
            for receipt in (
                price_capture_batch["receipts"]
                if price_capture_batch is not None
                else (price_receipts or [])
            ):
                self._execute(
                    conn,
                    "INSERT INTO paper_price_receipts "
                    "(run_id,session_date,ticker,captured_utc,vendor,raw_open,"
                    "adjusted_open,dividend,split_ratio,capture_batch_id,"
                    "price_receipt_id,vendor_snapshot_id,receipt_identity_json,"
                    "vendor_snapshot_identity_json,payload_json) VALUES "
                    "(:run_id,:session_date,:ticker,:captured_utc,:vendor,:raw_open,"
                    ":adjusted_open,:dividend,:split_ratio,:capture_batch_id,"
                    ":price_receipt_id,:vendor_snapshot_id,:receipt_identity_json,"
                    ":vendor_snapshot_identity_json,:payload_json)",
                    {
                        "run_id": run_id,
                        **receipt,
                        "capture_batch_id": receipt.get("capture_batch_id"),
                        "price_receipt_id": receipt.get("price_receipt_id"),
                        "vendor_snapshot_id": receipt.get("vendor_snapshot_id"),
                        "receipt_identity_json": (
                            canonical_json(_price_receipt_identity_payload(receipt))
                            if receipt.get("price_receipt_id")
                            else None
                        ),
                        "vendor_snapshot_identity_json": (
                            canonical_json(
                                _vendor_snapshot_identity_payload(receipt["vendor_snapshot"])
                            )
                            if receipt.get("vendor_snapshot_id")
                            else None
                        ),
                        "payload_json": canonical_json(receipt),
                    },
                )
            self._execute(
                conn,
                """
                INSERT INTO paper_marks
                (run_id,session_date,captured_utc,nav,benchmark_nav,period_return,
                 benchmark_period_return,turnover,trading_cost,borrow_cost,
                 weights_json,opens_json,benchmark_open,target_decision_date)
                VALUES (:run_id,:session_date,:captured_utc,:nav,:benchmark_nav,
                        :period_return,:benchmark_period_return,:turnover,:trading_cost,
                        :borrow_cost,:weights_json,:opens_json,:benchmark_open,
                        :target_decision_date)
            """,
                payload,
            )
            if interval_assignment is not None:
                self._execute(
                    conn,
                    "INSERT INTO paper_interval_assignments "
                    "(run_id,interval_index,from_session_date,session_date,"
                    "scheduled_decision_date,created_utc,disposition,"
                    "applied_target_decision_date,return_vector_id) VALUES "
                    "(:run_id,:interval_index,:from_session_date,:session_date,"
                    ":scheduled_decision_date,:created_utc,:disposition,"
                    ":applied_target_decision_date,:return_vector_id)",
                    interval_assignment,
                )

    def status(self, run_id: str) -> dict:
        config = self.run_config(run_id)
        decisions = self._rows(
            "SELECT COUNT(*) AS count, COUNT(DISTINCT decision_date) AS dates "
            "FROM paper_decisions WHERE run_id=:run_id",
            {"run_id": run_id},
        )[0]
        marks = self._rows(
            "SELECT COUNT(*) AS count, MIN(session_date) AS start_date, "
            "MAX(session_date) AS end_date FROM paper_marks WHERE run_id=:run_id",
            {"run_id": run_id},
        )[0]
        latest = self.latest_mark(run_id)
        labels = self._rows(
            "SELECT label,created_utc,details_json FROM paper_run_labels "
            "WHERE run_id=:run_id ORDER BY created_utc",
            {"run_id": run_id},
        )
        strategy_counts = self._rows(
            "SELECT strategy_id,COUNT(*) AS marks FROM paper_strategy_marks "
            "WHERE run_id=:run_id GROUP BY strategy_id ORDER BY strategy_id",
            {"run_id": run_id},
        )
        result = {
            "run_id": run_id,
            "config": config,
            "decision_rows": decisions["count"],
            "decision_dates": decisions["dates"],
            "mark_count": marks["count"],
            "start_date": marks["start_date"],
            "end_date": marks["end_date"],
            "nav": latest["nav"] if latest else 1.0,
            "benchmark_nav": latest["benchmark_nav"] if latest else 1.0,
            "labels": [
                {
                    "label": row["label"],
                    "created_utc": row["created_utc"],
                    "details": json.loads(row["details_json"]),
                }
                for row in labels
            ],
            "strategy_marks": {row["strategy_id"]: row["marks"] for row in strategy_counts},
        }
        if config.get("engine") != "formal-global-v2":
            return result

        # Routine health output must not become an unregistered interim look.
        result.pop("nav", None)
        result.pop("benchmark_nav", None)
        result["outcomes_withheld"] = True

        formal_decisions = self._rows(
            "SELECT COUNT(*) AS count, COUNT(DISTINCT decision_date) AS dates "
            "FROM paper_decision_bundles WHERE run_id=:run_id",
            {"run_id": run_id},
        )[0]
        target_strategies = {
            row["strategy_id"]
            for row in self._rows(
                "SELECT DISTINCT strategy_id FROM paper_strategy_targets WHERE run_id=:run_id",
                {"run_id": run_id},
            )
        }
        protocol_strategies = set()
        protocol_id = config.get("protocol_id")
        if isinstance(protocol_id, str) and protocol_id:
            protocol_rows = self._rows(
                "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
                {"protocol_id": protocol_id},
            )
            if len(protocol_rows) == 1:
                manifest = json.loads(protocol_rows[0]["manifest_json"])
                manifest_strategies = (
                    manifest.get("strategies") if isinstance(manifest, dict) else None
                )
                if isinstance(manifest_strategies, list):
                    protocol_strategies = {
                        strategy_id
                        for strategy_id in manifest_strategies
                        if isinstance(strategy_id, str) and strategy_id
                    }
        strategy_mark_rows = self._rows(
            "SELECT strategy_id,session_date FROM paper_strategy_marks "
            "WHERE run_id=:run_id ORDER BY strategy_id,session_date",
            {"run_id": run_id},
        )
        expected_strategies = sorted(
            protocol_strategies
            | target_strategies
            | {row["strategy_id"] for row in strategy_mark_rows}
        )
        mark_dates_by_strategy = {strategy_id: [] for strategy_id in expected_strategies}
        for row in strategy_mark_rows:
            mark_dates_by_strategy[row["strategy_id"]].append(row["session_date"])
        strategy_mark_counts = {
            strategy_id: len(mark_dates_by_strategy[strategy_id])
            for strategy_id in expected_strategies
        }
        completed_dates_by_strategy = {
            strategy_id: set(mark_dates_by_strategy[strategy_id][1:])
            for strategy_id in expected_strategies
        }
        champion_dates = [
            row["session_date"]
            for row in self._rows(
                "SELECT session_date FROM paper_marks WHERE run_id=:run_id ORDER BY session_date",
                {"run_id": run_id},
            )
        ]
        expected_outcome_dates = set(champion_dates[1:])
        observed_outcome_dates = (
            set().union(*completed_dates_by_strategy.values())
            if completed_dates_by_strategy
            else set()
        )
        outcome_dates = sorted(expected_outcome_dates | observed_outcome_dates)
        common_dates = (
            sorted(set.intersection(*completed_dates_by_strategy.values()))
            if completed_dates_by_strategy
            else []
        )
        missing_outcomes = {
            session_date: [
                strategy_id
                for strategy_id in expected_strategies
                if session_date not in completed_dates_by_strategy[strategy_id]
            ]
            for session_date in outcome_dates
        }
        missing_outcomes = {
            session_date: strategy_ids
            for session_date, strategy_ids in missing_outcomes.items()
            if strategy_ids
        }
        counts_synchronized = len(set(strategy_mark_counts.values())) <= 1

        result.update(
            {
                # Preserve the legacy keys while making their meaning useful for
                # the formal engine, which stores one bundle rather than ticker rows.
                "decision_rows": formal_decisions["count"],
                "decision_dates": formal_decisions["dates"],
                "formal_decision_bundles": formal_decisions["count"],
                "formal_decision_dates": formal_decisions["dates"],
                "expected_strategies": expected_strategies,
                "strategy_marks": strategy_mark_counts,
                "strategy_mark_counts_synchronized": counts_synchronized,
                "strategy_completed_outcome_intervals": {
                    strategy_id: len(completed_dates_by_strategy[strategy_id])
                    for strategy_id in expected_strategies
                },
                "common_completed_outcome_intervals": len(common_dates),
                "common_completed_outcome_dates": common_dates,
                "common_outcome_start_date": common_dates[0] if common_dates else None,
                "common_outcome_end_date": common_dates[-1] if common_dates else None,
                "missing_strategy_outcomes": missing_outcomes,
                "asymmetric_strategy_outcomes": (not counts_synchronized or bool(missing_outcomes)),
                "confirmatory_registration": self.confirmatory_registration(run_id),
                "itt_provenance": self.formal_trial_counts(run_id),
            }
        )
        return result

    def close(self) -> None:
        if self._sqlite:
            self.conn.close()
        else:
            self.engine.dispose()


def _calendar():
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise RuntimeError(
            "paper trading requires exchange_calendars; install tradingagents[poller]"
        ) from exc
    return xcals.get_calendar("XNYS")


def decision_window(decision_date: str) -> tuple[datetime, datetime, str]:
    """Immutable-recording window: data cutoff through the next session open."""
    calendar = _calendar()
    session = pd.Timestamp(decision_date)
    if not calendar.is_session(session):
        raise ValueError(f"{decision_date} is not an XNYS session")
    cutoff = datetime.strptime(decision_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(
        days=1
    )
    next_session = calendar.next_session(session)
    next_open = calendar.session_open(next_session).to_pydatetime().astimezone(timezone.utc)
    return cutoff, next_open, next_session.date().isoformat()


def current_decision_date(now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    calendar = _calendar()
    # Start on the prior calendar date: at 01:00 UTC on a Tuesday, Tuesday is
    # an exchange session label but has not opened yet; Monday is the decision
    # whose immutable recording window is active.
    candidate = calendar.date_to_session(
        pd.Timestamp(now.date() - timedelta(days=1)), direction="previous"
    )
    for _ in range(10):
        date = candidate.date().isoformat()
        cutoff, next_open, _ = decision_window(date)
        if cutoff <= now < next_open:
            return date
        if now >= next_open:
            break
        candidate = calendar.previous_session(candidate)
    raise DecisionWindowClosedError(
        "not inside the safe after-cutoff, before-next-open decision window"
    )


def next_session_date(session_date: str) -> str:
    return _calendar().next_session(pd.Timestamp(session_date)).date().isoformat()


def session_open_utc(session_date: str) -> datetime:
    calendar = _calendar()
    session = pd.Timestamp(session_date)
    if not calendar.is_session(session):
        raise ValueError(f"{session_date} is not an XNYS session")
    return calendar.session_open(session).to_pydatetime().astimezone(timezone.utc)


def formal_price_capture_window(session_date: str) -> tuple[datetime, datetime]:
    """Return the frozen capture boundary for one formal entry/mark session."""
    calendar = _calendar()
    session = pd.Timestamp(session_date)
    if not calendar.is_session(session):
        raise ValueError(f"{session_date} is not an XNYS session")
    delay_minutes = int(
        GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
            "scheduled_delay_after_xnys_session_open_minutes"
        ]
    )
    scheduled = calendar.session_open(session).to_pydatetime().astimezone(timezone.utc) + timedelta(
        minutes=delay_minutes
    )
    next_session = calendar.next_session(session)
    deadline = calendar.session_open(next_session).to_pydatetime().astimezone(timezone.utc)
    return scheduled, deadline


def _formal_capture_clock() -> float:
    """Live wall clock for formal capture; tests may monkeypatch this private seam."""
    return datetime.now(timezone.utc).timestamp()


def advance_mark(
    *,
    previous: dict | None,
    session_date: str,
    captured_utc: float,
    opens: dict[str, float],
    benchmark_open: float,
    target: dict | None,
    trading_cost_bps: float,
    slippage_bps: float,
    annual_borrow_bps: float,
    asset_returns: dict[str, float] | None = None,
    benchmark_period_return_override: float | None = None,
    cash_period_return: float = 0.0,
) -> dict:
    """Advance one immutable open-to-open paper mark."""
    if min(trading_cost_bps, slippage_bps, annual_borrow_bps) < 0:
        raise ValueError("cost, slippage, and borrow rates must be >= 0")
    if (
        isinstance(cash_period_return, bool)
        or not isinstance(cash_period_return, (int, float))
        or not math.isfinite(float(cash_period_return))
    ):
        raise ValueError("cash period return must be finite")
    if previous is None:
        if target is None:
            raise ValueError("the first paper mark requires an entering target")
        nav = benchmark_nav = 1.0
        weights = dict.fromkeys(opens, 0.0)
        period_return = benchmark_period_return = borrow_cost = 0.0
    else:
        if set(previous["weights"]) != set(opens):
            raise ValueError("paper price cross-section does not match existing weights")
        if asset_returns is None:
            asset_returns = {
                ticker: opens[ticker] / previous["opens"][ticker] - 1.0 for ticker in opens
            }
        elif set(asset_returns) != set(opens):
            raise ValueError("paper return cross-section does not match prices")
        gross_return = sum(previous["weights"][ticker] * asset_returns[ticker] for ticker in opens)
        cash_weight = 1.0 - sum(previous["weights"].values())
        cash_return = cash_weight * float(cash_period_return)
        short_exposure = sum(abs(weight) for weight in previous["weights"].values() if weight < 0)
        borrow_cost = short_exposure * annual_borrow_bps / 10_000 / 252
        period_return = gross_return + cash_return - borrow_cost
        nav = previous["nav"] * (1.0 + period_return)
        benchmark_period_return = (
            benchmark_period_return_override
            if benchmark_period_return_override is not None
            else benchmark_open / previous["benchmark_open"] - 1.0
        )
        benchmark_nav = previous["benchmark_nav"] * (1.0 + benchmark_period_return)
        denominator = 1.0 + period_return
        if denominator <= 0:
            raise ValueError("paper portfolio equity was exhausted")
        weights = {
            ticker: previous["weights"][ticker] * (1.0 + asset_returns[ticker]) / denominator
            for ticker in opens
        }

    turnover = trading_cost = 0.0
    target_decision_date = None
    if target is not None:
        target_weights_map = target["weights"]
        if set(target_weights_map) != set(opens):
            raise ValueError("paper target cross-section does not match prices")
        turnover = sum(abs(target_weights_map[ticker] - weights[ticker]) for ticker in opens)
        trading_cost = turnover * (trading_cost_bps + slippage_bps) / 10_000
        nav *= 1.0 - trading_cost
        period_return = (1.0 + period_return) * (1.0 - trading_cost) - 1.0
        weights = target_weights_map
        target_decision_date = target["decision_date"]
    if not math.isfinite(nav) or nav <= 0:
        raise ValueError("invalid paper NAV")
    return {
        "session_date": session_date,
        "captured_utc": captured_utc,
        "nav": nav,
        "benchmark_nav": benchmark_nav,
        "period_return": period_return,
        "benchmark_period_return": benchmark_period_return,
        "turnover": turnover,
        "trading_cost": trading_cost,
        "borrow_cost": borrow_cost,
        "weights": weights,
        "opens": opens,
        "benchmark_open": benchmark_open,
        "target_decision_date": target_decision_date,
    }


def _open_snapshot(ticker: str, session_date: str, captured_utc: float) -> dict:
    start = (datetime.strptime(session_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    end = (datetime.strptime(session_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    frame = backtest.yf.Ticker(ticker).history(
        start=start, end=end, auto_adjust=False, actions=True
    )
    rows = {pd.Timestamp(index).date().isoformat(): row for index, row in frame.iterrows()}
    if session_date not in rows:
        raise RuntimeError(f"no open receipt for {ticker} on {session_date}")
    row = rows[session_date]
    raw_open = float(row["Open"])
    close = float(row["Close"])
    adjusted_close = float(row.get("Adj Close", close))
    adjusted_open = raw_open * adjusted_close / close if close else raw_open
    return {
        "session_date": session_date,
        "ticker": ticker,
        "captured_utc": captured_utc,
        "vendor": "yfinance",
        "raw_open": raw_open,
        "adjusted_open": adjusted_open,
        "dividend": float(row.get("Dividends", 0.0) or 0.0),
        "split_ratio": float(row.get("Stock Splits", 0.0) or 0.0),
    }


def _finite_price_number(value, label: str, *, positive: bool = False) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"vendor returned invalid {label}") from exc
    if not math.isfinite(normalized) or (positive and normalized <= 0):
        raise RuntimeError(f"vendor returned invalid {label}")
    return normalized


def _normalized_vendor_price_row(row, *, ticker: str, session_date: str) -> dict:
    """Normalize one unadjusted/action row without a second vendor read."""
    required = ("Open", "Close", "Adj Close")
    if any(column not in row.index for column in required):
        raise RuntimeError(f"vendor snapshot for {ticker} is missing adjusted OHLC fields")
    raw_open = _finite_price_number(
        row["Open"], f"raw open for {ticker}/{session_date}", positive=True
    )
    close = _finite_price_number(row["Close"], f"close for {ticker}/{session_date}", positive=True)
    adjusted_close = _finite_price_number(
        row["Adj Close"], f"adjusted close for {ticker}/{session_date}", positive=True
    )
    adjustment_factor = adjusted_close / close
    adjusted_open = raw_open * adjustment_factor
    if (
        not math.isfinite(adjustment_factor)
        or adjustment_factor <= 0
        or not math.isfinite(adjusted_open)
        or adjusted_open <= 0
    ):
        raise RuntimeError(f"vendor returned an invalid adjustment for {ticker}/{session_date}")
    dividend = _finite_price_number(
        row.get("Dividends", 0.0) or 0.0,
        f"dividend for {ticker}/{session_date}",
    )
    split_ratio = _finite_price_number(
        row.get("Stock Splits", 0.0) or 0.0,
        f"split ratio for {ticker}/{session_date}",
    )
    if dividend < 0 or split_ratio < 0:
        raise RuntimeError(f"vendor returned an invalid corporate action for {ticker}")
    return {
        "session_date": session_date,
        "raw_open": raw_open,
        "close": close,
        "adjusted_close": adjusted_close,
        "adjustment_factor": adjustment_factor,
        "adjusted_open": adjusted_open,
        "dividend": dividend,
        # Yahoo uses zero for no split and a positive new/old ratio otherwise.
        "split_ratio": split_ratio,
    }


def _capture_symbol_vintage(
    ticker: str,
    previous_session: str | None,
    session_date: str,
    *,
    clock_fn,
) -> dict:
    """Fetch both adjusted endpoints and the current raw/actions in one call."""
    requested_utc = float(clock_fn())
    start_session = previous_session or session_date
    end = (datetime.strptime(session_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    frame = backtest.yf.Ticker(ticker).history(
        start=start_session,
        end=end,
        auto_adjust=False,
        actions=True,
    )
    received_utc = float(clock_fn())
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise RuntimeError(f"no vendor price snapshot for {ticker}/{session_date}")
    indexed: dict[str, list] = {}
    for index, row in frame.iterrows():
        indexed.setdefault(pd.Timestamp(index).date().isoformat(), []).append(row)
    expected_dates = (
        [session_date] if previous_session is None else [previous_session, session_date]
    )
    if any(len(indexed.get(expected, [])) != 1 for expected in expected_dates):
        raise RuntimeError(
            f"vendor snapshot does not contain exactly one required row for {ticker}"
        )
    rows = {
        expected: _normalized_vendor_price_row(
            indexed[expected][0], ticker=ticker, session_date=expected
        )
        for expected in expected_dates
    }
    snapshot_base = {
        "schema_version": 1,
        "provider": "yfinance",
        "requested_ticker": ticker,
        "from_session": previous_session,
        "to_session": session_date,
        "requested_utc": requested_utc,
        "received_utc": received_utc,
        "rows": rows,
    }
    return {
        **snapshot_base,
        "vendor_snapshot_id": content_id(snapshot_base, prefix="price_snapshot_"),
    }


def _capture_price_vendor_batch(
    symbols: list[str],
    previous_session: str | None,
    session_date: str,
    *,
    clock_fn,
) -> list[dict]:
    """Adapter seam; one complete attempt is always rebuilt from one provider."""
    return [
        _capture_symbol_vintage(symbol, previous_session, session_date, clock_fn=clock_fn)
        for symbol in symbols
    ]


def _price_receipt_identity_payload(receipt: dict) -> dict:
    return {
        key: receipt[key]
        for key in (
            "schema_version",
            "session_date",
            "ticker",
            "captured_utc",
            "vendor",
            "raw_open",
            "adjusted_open",
            "dividend",
            "split_ratio",
            "vendor_snapshot_id",
            "vendor_snapshot",
        )
    }


def _vendor_snapshot_identity_payload(snapshot: dict) -> dict:
    return {
        key: snapshot[key]
        for key in (
            "schema_version",
            "provider",
            "requested_ticker",
            "from_session",
            "to_session",
            "requested_utc",
            "received_utc",
            "rows",
        )
    }


def _return_vector_identity_payload(vector: dict) -> dict:
    return {
        key: vector[key]
        for key in (
            "schema_version",
            "from_session",
            "to_session",
            "captured_utc",
            "scheduled_utc",
            "deadline_utc",
            "vendor",
            "components",
            "cash_component",
        )
    }


def _price_batch_identity_payload(batch: dict) -> dict:
    return {
        key: batch[key]
        for key in (
            "schema_version",
            "session_date",
            "from_session_date",
            "attempt_ordinal",
            "scheduled_utc",
            "started_utc",
            "completed_utc",
            "deadline_utc",
            "vendor",
            "paper_build_id",
            "return_vector_id",
            "receipt_manifest",
        )
    }


def _build_formal_price_batch(
    *,
    symbols: list[str],
    previous_session: str | None,
    session_date: str,
    attempt_ordinal: int,
    scheduled_utc: float,
    started_utc: float,
    completed_utc: float,
    deadline_utc: float,
    vendor_snapshots: list[dict],
    cash_component: dict | None,
    paper_build_id: str | None = None,
) -> dict:
    """Build the content-addressed receipt batch and optional return vector v2."""
    paper_build_id = paper_build_id or build_identity()
    if _BUILD_ID_PATTERN.fullmatch(paper_build_id) is None:
        raise ValueError("paper runtime build identity is malformed")
    canonical_symbols = sorted(set(symbols))
    if len(canonical_symbols) != len(symbols) or not canonical_symbols:
        raise ValueError("price vendor universe must be sorted-unique capable")
    symbols = canonical_symbols
    if len(vendor_snapshots) != len(symbols):
        raise ValueError("price vendor batch does not match the return universe")
    by_ticker = {snapshot.get("requested_ticker"): snapshot for snapshot in vendor_snapshots}
    if set(by_ticker) != set(symbols) or len(by_ticker) != len(vendor_snapshots):
        raise ValueError("price vendor batch is duplicated or incomplete")
    receipts: list[dict] = []
    for ticker in symbols:
        snapshot = by_ticker[ticker]
        current = snapshot["rows"][session_date]
        receipt = {
            "schema_version": 2,
            "session_date": session_date,
            "ticker": ticker,
            "captured_utc": completed_utc,
            "vendor": "yfinance",
            "raw_open": current["raw_open"],
            "adjusted_open": current["adjusted_open"],
            "dividend": current["dividend"],
            "split_ratio": current["split_ratio"],
            "vendor_snapshot_id": snapshot["vendor_snapshot_id"],
            "vendor_snapshot": snapshot,
        }
        receipt["price_receipt_id"] = content_id(
            _price_receipt_identity_payload(receipt), prefix="price_receipt_"
        )
        receipts.append(receipt)

    return_vector = None
    if previous_session is not None:
        if not isinstance(cash_component, dict):
            raise ValueError("formal completed interval has no cash-rate component")
        _validate_cash_component(cash_component, previous_session, session_date)
        components = {}
        for receipt in receipts:
            snapshot = receipt["vendor_snapshot"]
            previous_open = snapshot["rows"][previous_session]["adjusted_open"]
            current_open = receipt["adjusted_open"]
            components[receipt["ticker"]] = {
                "price_receipt_id": receipt["price_receipt_id"],
                "vendor_snapshot_id": receipt["vendor_snapshot_id"],
                "previous_adjusted_open": previous_open,
                "current_adjusted_open": current_open,
                "current_raw_open": receipt["raw_open"],
                "cash_dividend": receipt["dividend"],
                "split_ratio": receipt["split_ratio"],
                "open_return": current_open / previous_open - 1.0,
            }
        vector_base = {
            "schema_version": 2,
            "from_session": previous_session,
            "to_session": session_date,
            "captured_utc": completed_utc,
            "scheduled_utc": scheduled_utc,
            "deadline_utc": deadline_utc,
            "vendor": "yfinance",
            "components": components,
            "cash_component": cash_component,
        }
        return_vector = {
            "return_vector_id": content_id(vector_base, prefix="return_vector_"),
            **vector_base,
        }

    receipt_manifest = [
        {
            "ticker": receipt["ticker"],
            "price_receipt_id": receipt["price_receipt_id"],
            "vendor_snapshot_id": receipt["vendor_snapshot_id"],
        }
        for receipt in receipts
    ]
    batch_base = {
        "schema_version": 1,
        "session_date": session_date,
        "from_session_date": previous_session,
        "attempt_ordinal": attempt_ordinal,
        "scheduled_utc": scheduled_utc,
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "deadline_utc": deadline_utc,
        "vendor": "yfinance",
        "paper_build_id": paper_build_id,
        "return_vector_id": (
            return_vector["return_vector_id"] if return_vector is not None else None
        ),
        "receipt_manifest": receipt_manifest,
    }
    capture_batch_id = content_id(batch_base, prefix="price_batch_")
    for receipt in receipts:
        receipt["capture_batch_id"] = capture_batch_id
        if return_vector is not None:
            receipt["return_vector"] = {
                "return_vector_id": return_vector["return_vector_id"],
                "schema_version": return_vector["schema_version"],
                "from_session": return_vector["from_session"],
                "to_session": return_vector["to_session"],
                "captured_utc": return_vector["captured_utc"],
                "scheduled_utc": return_vector["scheduled_utc"],
                "deadline_utc": return_vector["deadline_utc"],
                "vendor": return_vector["vendor"],
                "cash_component": return_vector["cash_component"],
                **return_vector["components"][receipt["ticker"]],
            }
    return {
        "capture_batch_id": capture_batch_id,
        **batch_base,
        "receipts": receipts,
        "return_vector": return_vector,
    }


def _validate_formal_price_batch_contract(
    batch: dict,
    *,
    symbols: list[str],
    previous_session: str | None,
    session_date: str,
) -> None:
    """Authenticate a complete formal capture without consulting the vendor."""
    canonical_symbols = sorted(set(symbols))
    if len(canonical_symbols) != len(symbols) or not canonical_symbols:
        raise ValueError("formal price return universe is duplicated or empty")
    symbols = canonical_symbols
    if (
        not isinstance(batch, dict)
        or batch.get("schema_version") != 1
        or batch.get("session_date") != session_date
        or batch.get("from_session_date") != previous_session
        or _BUILD_ID_PATTERN.fullmatch(str(batch.get("paper_build_id", ""))) is None
        or batch.get("vendor") != "yfinance"
    ):
        raise ValueError("formal price capture batch header is malformed")
    scheduled, deadline = formal_price_capture_window(session_date)
    expected_scheduled = scheduled.timestamp()
    expected_deadline = deadline.timestamp()
    numeric_fields = ("scheduled_utc", "started_utc", "completed_utc", "deadline_utc")
    if (
        any(
            isinstance(batch.get(field), bool)
            or not isinstance(batch.get(field), (int, float))
            or not math.isfinite(float(batch[field]))
            for field in numeric_fields
        )
        or not math.isclose(float(batch["scheduled_utc"]), expected_scheduled, abs_tol=1e-9)
        or not math.isclose(float(batch["deadline_utc"]), expected_deadline, abs_tol=1e-9)
        or not (
            float(batch["scheduled_utc"])
            <= float(batch["started_utc"])
            <= float(batch["completed_utc"])
            < float(batch["deadline_utc"])
        )
    ):
        raise ValueError("formal price capture batch violates its immutable window")
    if type(batch.get("attempt_ordinal")) is not int or batch["attempt_ordinal"] < 1:
        raise ValueError("formal price capture attempt identity is malformed")

    receipts = batch.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != len(symbols):
        raise ValueError("formal price receipts are incomplete")
    by_ticker = {
        receipt.get("ticker"): receipt for receipt in receipts if isinstance(receipt, dict)
    }
    if set(by_ticker) != set(symbols) or len(by_ticker) != len(receipts):
        raise ValueError("formal price receipt universe is ambiguous")
    manifest = []
    for symbol in symbols:
        receipt = by_ticker[symbol]
        snapshot = receipt.get("vendor_snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("formal price receipt has no vendor snapshot")
        try:
            snapshot_base = _vendor_snapshot_identity_payload(snapshot)
        except KeyError as exc:
            raise ValueError("formal vendor snapshot identity is incomplete") from exc
        snapshot_id = content_id(snapshot_base, prefix="price_snapshot_")
        if (
            snapshot.get("vendor_snapshot_id") != snapshot_id
            or receipt.get("vendor_snapshot_id") != snapshot_id
        ):
            raise ValueError("formal vendor snapshot identity is invalid")
        if (
            snapshot.get("provider") != "yfinance"
            or snapshot.get("requested_ticker") != symbol
            or snapshot.get("from_session") != previous_session
            or snapshot.get("to_session") != session_date
        ):
            raise ValueError("formal vendor snapshot header is invalid")
        snapshot_times = (snapshot.get("requested_utc"), snapshot.get("received_utc"))
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in snapshot_times
        ) or not (
            float(batch["started_utc"])
            <= float(snapshot["requested_utc"])
            <= float(snapshot["received_utc"])
            <= float(batch["completed_utc"])
        ):
            raise ValueError("formal vendor snapshot timing is invalid")
        rows = snapshot.get("rows")
        expected_dates = (
            {session_date} if previous_session is None else {previous_session, session_date}
        )
        if not isinstance(rows, dict) or set(rows) != expected_dates:
            raise ValueError("formal vendor snapshot endpoints are incomplete")
        for endpoint, row in rows.items():
            required_row = {
                "session_date",
                "raw_open",
                "close",
                "adjusted_close",
                "adjustment_factor",
                "adjusted_open",
                "dividend",
                "split_ratio",
            }
            if (
                not isinstance(row, dict)
                or set(row) != required_row
                or row.get("session_date") != endpoint
            ):
                raise ValueError("formal vendor snapshot row is malformed")
            numbers = [row[key] for key in required_row if key != "session_date"]
            if (
                any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in numbers
                )
                or min(
                    float(row["raw_open"]),
                    float(row["close"]),
                    float(row["adjusted_close"]),
                    float(row["adjustment_factor"]),
                    float(row["adjusted_open"]),
                )
                <= 0
                or float(row["dividend"]) < 0
                or float(row["split_ratio"]) < 0
            ):
                raise ValueError("formal vendor snapshot values are invalid")
            if not math.isclose(
                float(row["adjustment_factor"]),
                float(row["adjusted_close"]) / float(row["close"]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ) or not math.isclose(
                float(row["adjusted_open"]),
                float(row["raw_open"]) * float(row["adjustment_factor"]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("formal vendor snapshot adjustment is invalid")
        current = rows[session_date]
        scalar_pairs = (
            ("raw_open", "raw_open"),
            ("adjusted_open", "adjusted_open"),
            ("dividend", "dividend"),
            ("split_ratio", "split_ratio"),
        )
        if (
            receipt.get("schema_version") != 2
            or receipt.get("session_date") != session_date
            or receipt.get("vendor") != "yfinance"
            or receipt.get("capture_batch_id") != batch.get("capture_batch_id")
            or not math.isclose(
                float(receipt.get("captured_utc", math.nan)),
                float(batch["completed_utc"]),
                abs_tol=1e-9,
            )
            or any(
                not math.isclose(
                    float(receipt.get(receipt_key, math.nan)),
                    float(current[row_key]),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                for receipt_key, row_key in scalar_pairs
            )
        ):
            raise ValueError("formal price receipt disagrees with its vendor snapshot")
        receipt_id = content_id(_price_receipt_identity_payload(receipt), prefix="price_receipt_")
        if receipt.get("price_receipt_id") != receipt_id:
            raise ValueError("formal price receipt identity is invalid")
        manifest.append(
            {
                "ticker": symbol,
                "price_receipt_id": receipt_id,
                "vendor_snapshot_id": snapshot_id,
            }
        )

    vector = batch.get("return_vector")
    if previous_session is None:
        if vector is not None or batch.get("return_vector_id") is not None:
            raise ValueError("formal initialization capture cannot contain a return vector")
    else:
        if not isinstance(vector, dict) or vector.get("schema_version") != 2:
            raise ValueError("formal completed interval has no return vector v2")
        try:
            vector_base = _return_vector_identity_payload(vector)
        except KeyError as exc:
            raise ValueError("formal return vector identity is incomplete") from exc
        vector_id = content_id(vector_base, prefix="return_vector_")
        if (
            vector.get("return_vector_id") != vector_id
            or batch.get("return_vector_id") != vector_id
        ):
            raise ValueError("formal return vector identity is invalid")
        components = vector.get("components")
        if not isinstance(components, dict) or set(components) != set(symbols):
            raise ValueError("formal return vector universe is incomplete")
        for symbol in symbols:
            receipt = by_ticker[symbol]
            component = components[symbol]
            required_component = {
                "price_receipt_id",
                "vendor_snapshot_id",
                "previous_adjusted_open",
                "current_adjusted_open",
                "current_raw_open",
                "cash_dividend",
                "split_ratio",
                "open_return",
            }
            if (
                not isinstance(component, dict)
                or set(component) != required_component
                or component.get("price_receipt_id") != receipt["price_receipt_id"]
                or component.get("vendor_snapshot_id") != receipt["vendor_snapshot_id"]
            ):
                raise ValueError("formal return component is not receipt-bound")
            previous_open = float(component["previous_adjusted_open"])
            current_open = float(component["current_adjusted_open"])
            returned = float(component["open_return"])
            if (
                previous_open <= 0
                or current_open <= 0
                or not math.isclose(
                    current_open,
                    float(receipt["adjusted_open"]),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or not math.isclose(
                    float(component["current_raw_open"]),
                    float(receipt["raw_open"]),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or not math.isclose(
                    float(component["cash_dividend"]),
                    float(receipt["dividend"]),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or not math.isclose(
                    float(component["split_ratio"]),
                    float(receipt["split_ratio"]),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or not math.isclose(
                    returned,
                    current_open / previous_open - 1.0,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ):
                raise ValueError("formal return component arithmetic is invalid")

    try:
        batch_base = _price_batch_identity_payload(batch)
    except KeyError as exc:
        raise ValueError("formal price batch identity is incomplete") from exc
    if (
        batch.get("receipt_manifest") != manifest
        or batch_base["receipt_manifest"] != manifest
        or batch.get("capture_batch_id") != content_id(batch_base, prefix="price_batch_")
    ):
        raise ValueError("formal price capture batch identity is invalid")


def _open_on(ticker: str, session_date: str) -> float:
    """Compatibility helper for tests and callers that do not need a receipt."""
    return _open_snapshot(ticker, session_date, datetime.now(timezone.utc).timestamp())[
        "adjusted_open"
    ]


def _consistent_vintage_open_return(ticker: str, previous_session: str, session_date: str) -> float:
    """Compute both adjusted opens from one download vintage.

    Corporate-action adjustments can change historical prices. Fetching both
    endpoints together makes the captured forward return internally consistent
    even when a split or dividend occurred since the prior immutable mark.
    """
    return _consistent_vintage_open_component(ticker, previous_session, session_date)["open_return"]


def _consistent_vintage_open_component(
    ticker: str, previous_session: str, session_date: str
) -> dict:
    """Capture both adjusted opens needed for an auditable return component."""
    frame = backtest._load_prices(ticker, previous_session, session_date, 1)
    rows = {pd.Timestamp(index).date().isoformat(): row for index, row in frame.iterrows()}
    missing = [date for date in (previous_session, session_date) if date not in rows]
    if missing:
        raise RuntimeError(f"no adjusted open for {ticker} on {', '.join(missing)}")
    previous_open = float(rows[previous_session]["Open"])
    current_open = float(rows[session_date]["Open"])
    if (
        not math.isfinite(previous_open)
        or not math.isfinite(current_open)
        or previous_open <= 0
        or current_open <= 0
    ):
        raise RuntimeError(f"invalid adjusted open for {ticker}")
    return {
        "previous_adjusted_open": previous_open,
        "current_adjusted_open": current_open,
        "open_return": current_open / previous_open - 1.0,
    }


def _validate_cash_component(component: dict, previous_session: str, session_date: str) -> None:
    required = {
        "instrument",
        "annual_yield_proxy",
        "observation_session",
        "annual_yield_percent",
        "accrual_days",
        "day_count_basis",
        "open_return",
    }
    if (
        set(component) != required
        or component.get("instrument") != "USD"
        or component.get("annual_yield_proxy") != "^IRX"
        or type(component.get("accrual_days")) is not int
        or component.get("day_count_basis") != 360
    ):
        raise ValueError("return-vector cash component is malformed")
    try:
        start = date.fromisoformat(previous_session)
        end = date.fromisoformat(session_date)
        observed = date.fromisoformat(component["observation_session"])
    except (TypeError, ValueError) as exc:
        raise ValueError("return-vector cash dates are malformed") from exc
    annual_yield = component["annual_yield_percent"]
    cash_return = component["open_return"]
    if (
        isinstance(annual_yield, bool)
        or not isinstance(annual_yield, (int, float))
        or isinstance(cash_return, bool)
        or not isinstance(cash_return, (int, float))
        or not math.isfinite(float(annual_yield))
        or not math.isfinite(float(cash_return))
        or not (-20.0 <= float(annual_yield) <= 100.0)
        or observed >= start
        or component["accrual_days"] != (end - start).days
        or component["accrual_days"] <= 0
    ):
        raise ValueError("return-vector cash component is invalid")
    expected = float(annual_yield) / 100.0 * component["accrual_days"] / 360.0
    if not math.isclose(float(cash_return), expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("return-vector cash accrual is invalid")


def _cash_return_component(previous_session: str, session_date: str) -> dict:
    """Return the decision-eligible 13-week T-bill cash accrual.

    The held interval begins at ``previous_session`` open, so the latest safe
    daily yield is a close strictly before that session.  The exact observation
    and conversion are persisted with the shared return vector.
    """
    frame = backtest._load_prices("^IRX", previous_session, previous_session, 0)
    start = date.fromisoformat(previous_session)
    eligible = [
        (pd.Timestamp(index).date(), row)
        for index, row in frame.iterrows()
        if pd.Timestamp(index).date() < start
    ]
    if not eligible:
        raise RuntimeError(f"no point-in-time cash-rate observation before {previous_session}")
    observed, row = max(eligible, key=lambda item: item[0])
    annual_yield = float(row["Close"])
    accrual_days = (date.fromisoformat(session_date) - start).days
    component = {
        "instrument": "USD",
        "annual_yield_proxy": "^IRX",
        "observation_session": observed.isoformat(),
        "annual_yield_percent": annual_yield,
        "accrual_days": accrual_days,
        "day_count_basis": 360,
        "open_return": annual_yield / 100.0 * accrual_days / 360.0,
    }
    _validate_cash_component(component, previous_session, session_date)
    return component


def _capture_return_vector(
    symbols: list[str], previous_session: str, session_date: str, captured_utc: float
) -> dict:
    """Capture one content-addressed vector shared by champion and shadows."""
    ordered = list(dict.fromkeys(symbols))
    if (
        len(ordered) != len(symbols)
        or not ordered
        or any(not isinstance(symbol, str) or not symbol for symbol in ordered)
    ):
        raise ValueError("return-vector symbols must be non-empty strings")
    if (
        isinstance(captured_utc, bool)
        or not isinstance(captured_utc, (int, float))
        or not math.isfinite(float(captured_utc))
    ):
        raise ValueError("return-vector capture time must be finite")
    base = {
        "schema_version": 1,
        "from_session": previous_session,
        "to_session": session_date,
        "captured_utc": captured_utc,
        "vendor": "yfinance",
        "components": {
            symbol: _consistent_vintage_open_component(symbol, previous_session, session_date)
            for symbol in ordered
        },
        "cash_component": _cash_return_component(previous_session, session_date),
    }
    return {
        "return_vector_id": content_id(base, prefix="return_vector_"),
        **base,
    }


def _bind_return_vector(receipts: list[dict], vector: dict) -> None:
    """Embed each authenticated component in its immutable price receipt."""
    by_ticker = {receipt["ticker"]: receipt for receipt in receipts}
    components = vector["components"]
    if set(by_ticker) != set(components) or len(by_ticker) != len(receipts):
        raise ValueError("price receipts do not exactly match the return vector")
    for ticker, component in components.items():
        by_ticker[ticker]["return_vector"] = {
            "return_vector_id": vector["return_vector_id"],
            "schema_version": vector["schema_version"],
            "from_session": vector["from_session"],
            "to_session": vector["to_session"],
            "captured_utc": vector["captured_utc"],
            "vendor": vector["vendor"],
            "cash_component": vector["cash_component"],
            **component,
        }


def mark_next(
    store: PaperStore,
    run_id: str,
    captured_utc: float | None = None,
) -> dict:
    config = store.run_config(run_id)
    formal = (
        config.get("engine") == "formal-global-v2"
        and store.confirmatory_registration(run_id) is not None
    )
    formal_build_id = None
    if formal:
        if not store._sqlite:
            formal_runtime = store.authenticated_formal_runtime(
                run_id, role="paper_marker"
            )
            if (
                not isinstance(formal_runtime.get("authorization"), dict)
                or formal_runtime["authorization"].get("run_id") != run_id
                or formal_runtime.get("build_id")
                != formal_runtime["authorization"]["images"]["paper_marker"][
                    "build_id"
                ]
            ):
                raise ValueError(
                    "formal market capture requires an authorized marker runtime"
                )
            formal_build_id = formal_runtime["build_id"]
        counts = store.formal_trial_counts(run_id)
        if not counts["assignment_indices_contiguous"] or not counts["assignment_dates_contiguous"]:
            raise ValueError("formal interval ledger is not contiguous")
        if counts["completed_intervals"] >= FORMAL_HOLDING_INTERVALS:
            raise ValueError("formal confirmatory holding horizon is complete")
    previous = store.latest_mark(run_id)
    session_date = (
        next_session_date(previous["session_date"]) if previous else store.first_entry_date(run_id)
    )
    if session_date is None:
        raise ValueError("paper run has no target to mark")
    # Formal timeliness can never be asserted by a caller.  PostgreSQL also
    # records and checks its own wall clock in migration 008.  ``captured_utc``
    # remains a compatibility seam for legacy paper runs only.
    clock_fn = (
        _formal_capture_clock
        if formal
        else ((lambda: float(captured_utc)) if captured_utc is not None else _formal_capture_clock)
    )
    captured = float(clock_fn())
    if formal:
        scheduled, deadline = formal_price_capture_window(session_date)
        scheduled_utc = scheduled.timestamp()
        deadline_utc = deadline.timestamp()
        terminal = store.price_integrity_failure(run_id)
        if terminal is not None:
            raise FormalPriceIntegrityError(
                "terminal price integrity failure blocks the formal trial"
            )
        if captured < scheduled_utc:
            raise DecisionWindowClosedError(
                f"formal price capture {session_date} is not due before open+15m"
            )
        if captured >= deadline_utc:
            store.record_price_integrity_failure(
                run_id,
                session_date,
                detected_utc=captured,
                scheduled_utc=scheduled_utc,
                deadline_utc=deadline_utc,
                reason_code="capture_deadline_expired",
            )
            raise FormalPriceIntegrityError(
                f"formal price capture deadline expired for {session_date}; late backfill refused"
            )

        attempt_ordinal = store.record_price_capture_attempt_started(run_id, session_date, captured)
        symbols = sorted({*config["tickers"], config["benchmark"]})
        try:
            vendor_snapshots = _capture_price_vendor_batch(
                symbols,
                previous["session_date"] if previous is not None else None,
                session_date,
                clock_fn=clock_fn,
            )
            cash_component = (
                _cash_return_component(previous["session_date"], session_date)
                if previous is not None
                else None
            )
            completed = float(clock_fn())
            if completed >= deadline_utc:
                store.record_price_capture_attempt_failed(
                    run_id,
                    session_date,
                    attempt_ordinal,
                    completed,
                    "capture_window_expired",
                )
                store.record_price_integrity_failure(
                    run_id,
                    session_date,
                    detected_utc=completed,
                    scheduled_utc=scheduled_utc,
                    deadline_utc=deadline_utc,
                    reason_code="capture_crossed_deadline",
                )
                raise FormalPriceIntegrityError(
                    f"formal price capture crossed the deadline for {session_date}"
                )
            price_batch = _build_formal_price_batch(
                symbols=symbols,
                previous_session=(previous["session_date"] if previous is not None else None),
                session_date=session_date,
                attempt_ordinal=attempt_ordinal,
                scheduled_utc=scheduled_utc,
                started_utc=captured,
                completed_utc=completed,
                deadline_utc=deadline_utc,
                vendor_snapshots=vendor_snapshots,
                cash_component=cash_component,
                paper_build_id=formal_build_id,
            )
        except FormalPriceIntegrityError:
            raise
        except Exception as exc:
            failed_at = float(clock_fn())
            store.record_price_capture_attempt_failed(
                run_id,
                session_date,
                attempt_ordinal,
                failed_at,
                "market_data_failed",
            )
            if failed_at >= deadline_utc:
                store.record_price_integrity_failure(
                    run_id,
                    session_date,
                    detected_utc=failed_at,
                    scheduled_utc=scheduled_utc,
                    deadline_utc=deadline_utc,
                    reason_code="capture_crossed_deadline",
                )
                raise FormalPriceIntegrityError(
                    f"formal price capture failed at its deadline for {session_date}"
                ) from exc
            raise FormalPriceCaptureError(
                f"formal price capture attempt failed for {session_date}"
            ) from exc

        try:
            receipts = price_batch["receipts"]
            by_ticker = {receipt["ticker"]: receipt for receipt in receipts}
            opens = {ticker: by_ticker[ticker]["adjusted_open"] for ticker in config["tickers"]}
            return_vector = price_batch["return_vector"]
            asset_returns = None
            benchmark_return = None
            cash_return = 0.0
            if return_vector is not None:
                asset_returns = {
                    ticker: return_vector["components"][ticker]["open_return"]
                    for ticker in config["tickers"]
                }
                benchmark_return = return_vector["components"][config["benchmark"]]["open_return"]
                cash_return = return_vector["cash_component"]["open_return"]
            target = store.target_for_entry(run_id, session_date)
            mark = advance_mark(
                previous=previous,
                session_date=session_date,
                captured_utc=completed,
                opens=opens,
                benchmark_open=by_ticker[config["benchmark"]]["adjusted_open"],
                target=target,
                trading_cost_bps=config["cost_bps"],
                slippage_bps=config["slippage_bps"],
                annual_borrow_bps=config["annual_borrow_bps"],
                asset_returns=asset_returns,
                benchmark_period_return_override=benchmark_return,
                cash_period_return=cash_return,
            )
            if return_vector is not None:
                mark["return_vector_id"] = return_vector["return_vector_id"]
        except Exception as exc:
            failed_at = float(clock_fn())
            store.record_price_capture_attempt_failed(
                run_id,
                session_date,
                attempt_ordinal,
                failed_at,
                "unexpected_failure",
            )
            if failed_at >= deadline_utc:
                store.record_price_integrity_failure(
                    run_id,
                    session_date,
                    detected_utc=failed_at,
                    scheduled_utc=scheduled_utc,
                    deadline_utc=deadline_utc,
                    reason_code="capture_crossed_deadline",
                )
                raise FormalPriceIntegrityError(
                    f"formal price mark construction crossed the deadline for {session_date}"
                ) from exc
            raise FormalPriceCaptureError(
                f"formal price mark construction failed for {session_date}"
            ) from exc
        try:
            store.record_mark(
                run_id,
                mark,
                price_receipts=receipts,
                price_capture_batch=price_batch,
            )
        except Exception as exc:
            if store.price_capture_batch(run_id, session_date) is not None:
                recovered = store.latest_mark(run_id)
                if recovered is not None and recovered["session_date"] == session_date:
                    return recovered
            store.record_price_capture_attempt_failed(
                run_id,
                session_date,
                attempt_ordinal,
                float(clock_fn()),
                "persistence_failed",
            )
            raise FormalPriceCaptureError(
                f"formal price capture persistence failed for {session_date}"
            ) from exc
        return mark

    if datetime.fromtimestamp(captured, timezone.utc) < session_open_utc(session_date):
        raise ValueError(f"cannot mark {session_date} before its market open")
    target = store.target_for_entry(run_id, session_date)
    receipts = [
        _open_snapshot(ticker, session_date, captured)
        for ticker in [*config["tickers"], config["benchmark"]]
    ]
    by_ticker = {receipt["ticker"]: receipt for receipt in receipts}
    opens = {ticker: by_ticker[ticker]["adjusted_open"] for ticker in config["tickers"]}
    asset_returns = None
    benchmark_return = None
    cash_return = 0.0
    return_vector = None
    if previous is not None:
        return_vector = _capture_return_vector(
            [*config["tickers"], config["benchmark"]],
            previous["session_date"],
            session_date,
            captured,
        )
        _bind_return_vector(receipts, return_vector)
        asset_returns = {
            ticker: return_vector["components"][ticker]["open_return"]
            for ticker in config["tickers"]
        }
        benchmark_return = return_vector["components"][config["benchmark"]]["open_return"]
        cash_return = return_vector["cash_component"]["open_return"]
    mark = advance_mark(
        previous=previous,
        session_date=session_date,
        captured_utc=captured,
        opens=opens,
        benchmark_open=by_ticker[config["benchmark"]]["adjusted_open"],
        target=target,
        trading_cost_bps=config["cost_bps"],
        slippage_bps=config["slippage_bps"],
        annual_borrow_bps=config["annual_borrow_bps"],
        asset_returns=asset_returns,
        benchmark_period_return_override=benchmark_return,
        cash_period_return=cash_return,
    )
    if return_vector is not None:
        mark["return_vector_id"] = return_vector["return_vector_id"]
    store.record_mark(run_id, mark, price_receipts=receipts)
    return mark


def mark_formal_strategies(store: PaperStore, run_id: str, champion_mark: dict) -> list[dict]:
    """Mark every shadow from the champion's immutable return/capture vintage.

    Existing marks are skipped so a retry can finish a partially completed
    strategy set before the champion advances to another session.
    """
    config = store.run_config(run_id)
    session_date = champion_mark["session_date"]
    strategies = store.formal_strategies(run_id)
    return_vector = store.return_vector_for_session(
        run_id, session_date, [*config["tickers"], config["benchmark"]]
    )
    expected_vector_id = champion_mark.get("return_vector_id")
    if expected_vector_id is not None and (
        return_vector is None or return_vector["return_vector_id"] != expected_vector_id
    ):
        raise ValueError("champion mark return-vector identity does not match its receipts")
    results = []
    for strategy_id in strategies:
        previous = store.latest_strategy_mark(run_id, strategy_id)
        if previous is not None and previous["session_date"] == session_date:
            continue
        asset_returns = None
        benchmark_return = None
        cash_return = 0.0
        if previous is not None:
            if next_session_date(previous["session_date"]) != session_date:
                raise ValueError(f"formal strategy {strategy_id} is more than one session behind")
            if return_vector is None or return_vector["from_session"] != previous["session_date"]:
                raise ValueError("formal shadow mark requires the champion's stored return vector")
            asset_returns = {
                ticker: return_vector["components"][ticker]["open_return"]
                for ticker in config["tickers"]
            }
            benchmark_return = return_vector["components"][config["benchmark"]]["open_return"]
            cash_return = return_vector["cash_component"]["open_return"]
        elif session_date != store.first_entry_date(run_id):
            raise ValueError(f"formal strategy {strategy_id} cannot initialize after first entry")
        target = store.strategy_target_for_entry(run_id, strategy_id, session_date)
        mark = advance_mark(
            previous=previous,
            session_date=session_date,
            captured_utc=champion_mark["captured_utc"],
            opens=champion_mark["opens"],
            benchmark_open=champion_mark["benchmark_open"],
            target=target,
            trading_cost_bps=config["cost_bps"],
            slippage_bps=config["slippage_bps"],
            annual_borrow_bps=config["annual_borrow_bps"],
            asset_returns=asset_returns,
            benchmark_period_return_override=benchmark_return,
            cash_period_return=cash_return,
        )
        store.record_strategy_mark(run_id, strategy_id, mark)
        results.append(
            {
                "strategy_id": strategy_id,
                "session_date": session_date,
                "return_vector_id": (return_vector["return_vector_id"] if return_vector else None),
                "outcomes_withheld": True,
            }
        )
    return results


def _safe_review_identity(review: dict) -> dict:
    """Project a materialized review to routine outcome-blind observability."""
    return {
        "review_gate": review["review_gate"],
        "report_id": review["report_id"],
        "report_artifact_id": review["report_artifact_id"],
        "already_materialized": review["already_materialized"],
        "outcomes_withheld": True,
    }


def _formal_marker_runtime_material(args) -> tuple[dict, str]:
    """Resolve and validate marker settings before opening a production store."""
    from tradingagents.formal_runtime import paper_component_configuration
    from tradingagents.outcome_semantics import outcome_semantics_id

    decision_semantics_id = GLOBAL_EVENT_V2_PROTOCOL["forecast"][
        "expected_decision_semantics_id"
    ]
    marker_configuration = paper_component_configuration(
        args,
        role="paper_marker",
        decision_semantics_id=decision_semantics_id,
        env=os.environ,
    )
    return marker_configuration, outcome_semantics_id()


def _formal_decision_runtime_material(args) -> tuple[dict, str]:
    """Resolve the exact decision component for heartbeat authentication."""
    from tradingagents.formal_experiment import formal_decision_semantics
    from tradingagents.formal_runtime import paper_component_configuration
    from tradingagents.outcome_semantics import outcome_semantics_id

    semantics = formal_decision_semantics()
    expected = GLOBAL_EVENT_V2_PROTOCOL["forecast"][
        "expected_decision_semantics_id"
    ]
    if semantics["semantic_id"] != expected:
        raise ValueError("formal decision implementation differs from the protocol")
    configuration = paper_component_configuration(
        args,
        role="paper_decision",
        decision_semantics_id=semantics["semantic_id"],
        env=os.environ,
    )
    return configuration, outcome_semantics_id()


def _record_formal_worker_heartbeat(args, *, role: str, event_type: str) -> dict:
    """Authenticate afresh, then append a narrow role-specific heartbeat."""
    if role == "paper_decision":
        component, outcome_id = _formal_decision_runtime_material(args)
    elif role == "paper_marker":
        component, outcome_id = _formal_marker_runtime_material(args)
    else:
        raise ValueError("formal worker role is not allowlisted")
    store = PaperStore(args.db, auto_migrate=False)
    try:
        store.require_formal_runtime_authorization(
            args.run_id,
            role=role,
            component_configuration=component,
            outcome_semantics_id=outcome_id,
            env=os.environ,
        )
        return store.record_formal_runtime_heartbeat(
            args.run_id, role=role, event_type=event_type
        )
    finally:
        store.close()


def _authorize_formal_marker_runtime(store: PaperStore, args) -> dict:
    """Authenticate marker image/config/role before any market-data request."""
    marker_configuration, resolved_outcome_semantics_id = (
        _formal_marker_runtime_material(args)
    )
    runtime = store.require_formal_runtime_authorization(
        args.run_id,
        role="paper_marker",
        component_configuration=marker_configuration,
        outcome_semantics_id=resolved_outcome_semantics_id,
        env=os.environ,
    )
    authorization = runtime["authorization"]
    registration = store.confirmatory_registration(args.run_id)
    config = store.run_config(args.run_id)
    if (
        registration is None
        or registration["details"].get("registration_id")
        != authorization["registration_id"]
        or registration["details"].get("outcome_semantics_id")
        != resolved_outcome_semantics_id
        or registration["details"].get("configuration_binding")
        != authorization["configuration_binding"]
        or config.get("trial_registration_id") != authorization["registration_id"]
        or config.get("outcome_semantics_id") != resolved_outcome_semantics_id
        or config.get("configuration_binding") != authorization["configuration_binding"]
    ):
        raise ValueError("formal marker differs from its preregistered trial")
    return runtime


def _mark_formal_once_locked(
    store: PaperStore,
    run_id: str,
    captured_utc: float | None = None,
    *,
    runtime_args=None,
) -> dict:
    """Complete one formal mark while the caller holds the operation lock."""
    config = store.run_config(run_id)
    if config.get("engine") != "formal-global-v2":
        raise ValueError("formal mark helper requires a formal-global-v2 run")
    if not store._sqlite:
        if runtime_args is None or getattr(runtime_args, "run_id", None) != run_id:
            raise ValueError("formal marker requires its exact runtime arguments")
        _authorize_formal_marker_runtime(store, runtime_args)
    strategy_mark_count = 0

    # Recover interrupted shadow writes from the same authenticated vector.
    # Outcome reports are deliberately an offline analyzer responsibility and
    # never run under the marker credential.
    latest = store.latest_mark(run_id)
    if latest is not None:
        strategy_mark_count += len(mark_formal_strategies(store, run_id, latest))
    completed = int(store.formal_trial_counts(run_id)["completed_intervals"])
    if completed >= FORMAL_HOLDING_INTERVALS:
        return {
            "run_id": run_id,
            "mark_recorded": False,
            "session_date": latest["session_date"] if latest is not None else None,
            "return_vector_id": None,
            "strategy_marks_recorded": strategy_mark_count,
            "formal_completed_intervals": completed,
            "analysis_materialized": False,
            "outcomes_withheld": True,
        }

    mark = mark_next(
        store,
        run_id,
        captured_utc,
    )
    strategy_mark_count += len(mark_formal_strategies(store, run_id, mark))
    completed = int(store.formal_trial_counts(run_id)["completed_intervals"])
    return {
        "run_id": run_id,
        "mark_recorded": True,
        "session_date": mark["session_date"],
        "return_vector_id": mark.get("return_vector_id"),
        "strategy_marks_recorded": strategy_mark_count,
        "formal_completed_intervals": completed,
        "analysis_materialized": False,
        "outcomes_withheld": True,
    }


def _mark_formal_once(
    store: PaperStore,
    run_id: str,
    captured_utc: float | None = None,
    *,
    runtime_args=None,
) -> dict:
    """Serialize one manual formal mark and every exact-gate side effect."""
    with formal_operation_lock(store.url, run_id):
        if runtime_args is None:
            return _mark_formal_once_locked(store, run_id, captured_utc)
        return _mark_formal_once_locked(
            store, run_id, captured_utc, runtime_args=runtime_args
        )


def _run_config(args, signal_fingerprint: str) -> dict:
    return {
        "tickers": sorted(
            {value.strip().upper() for value in args.tickers.split(",") if value.strip()}
        ),
        "benchmark": args.benchmark.upper(),
        "analysts": [value.strip() for value in args.analysts.split(",") if value.strip()],
        "replicates": args.replicates,
        "portfolio_mode": args.portfolio_mode,
        "gross_limit": args.gross_limit,
        "max_weight": args.max_weight,
        "cost_bps": args.cost_bps,
        "slippage_bps": args.slippage_bps,
        "annual_borrow_bps": args.annual_borrow_bps,
        "signal_fingerprint": signal_fingerprint,
        "global_topics_only": args.global_topics_only,
    }


def decide(args, now_utc: datetime | None = None) -> dict:
    """Run a complete forward cross-section, then atomically freeze it."""
    if getattr(args, "engine", "legacy-ratings") != "legacy-ratings":
        raise ValueError("legacy decide called for a non-legacy engine")
    now = now_utc or datetime.now(timezone.utc)
    decision_date = current_decision_date(now)
    _, _, entry_date = decision_window(decision_date)
    analysts = tuple(value.strip() for value in args.analysts.split(",") if value.strip())
    if "fundamentals" in analysts:
        raise ValueError("fundamentals is not point-in-time safe for paper parity")
    unknown = set(analysts) - {"market", "social", "news"}
    if unknown:
        raise ValueError("unknown analyst(s): " + ", ".join(sorted(unknown)))
    manifest_args = SimpleNamespace(
        db=args.db,
        identity_control="none",
        global_topics_only=args.global_topics_only,
    )
    manifest = backtest._signal_manifest(manifest_args, analysts)
    signal_fingerprint = backtest._signal_fingerprint(manifest)
    run_config = _run_config(args, signal_fingerprint)
    store = PaperStore(args.db)
    try:
        store.create_run(args.run_id, run_config, now.timestamp())
        if store.has_decision(args.run_id, decision_date):
            raise ValueError(f"paper decision {args.run_id}/{decision_date} is already frozen")
        from tradingagents.dataflows.media_history import collected_window_fingerprint
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "backtest_mode": True,
                "checkpoint_enabled": False,
                "collected_media_enabled": True,
                "media_db_url": args.db,
                "results_dir": args.results_dir,
                "global_topics_only": args.global_topics_only,
            }
        )
        graph = TradingAgentsGraph(selected_analysts=analysts, debug=args.debug, config=config)
        decisions = []
        scores: dict[str, list[float]] = {ticker: [] for ticker in run_config["tickers"]}
        for ticker in run_config["tickers"]:
            start_date = (
                datetime.strptime(decision_date, "%Y-%m-%d") - timedelta(days=7)
            ).strftime("%Y-%m-%d")
            data_fingerprint = collected_window_fingerprint(
                ticker, start_date, decision_date, db_url=args.db
            )
            for replicate in range(args.replicates):
                _, action = graph.propagate(ticker, decision_date)
                score = rating_score(action)
                scores[ticker].append(score)
                decisions.append(
                    {
                        "ticker": ticker,
                        "replicate": replicate,
                        "action": action,
                        "score": score,
                        "data_fingerprint": data_fingerprint,
                        "signal_fingerprint": signal_fingerprint,
                        "final_decision": graph.curr_state["final_trade_decision"],
                    }
                )
        averaged = {ticker: sum(values) / len(values) for ticker, values in scores.items()}
        weights = target_weights(
            averaged,
            mode=args.portfolio_mode,
            gross_limit=args.gross_limit,
            max_weight=args.max_weight,
        )
        store.record_decision_set(
            args.run_id, decision_date, entry_date, now.timestamp(), decisions, weights
        )
        return {
            "decision_date": decision_date,
            "entry_date": entry_date,
            "weights": weights,
            "decision_rows": len(decisions),
        }
    finally:
        store.close()


def _common_arguments(parser) -> None:
    default_run_id = os.getenv("PAPER_RUN_ID")
    parser.add_argument("--run-id", default=default_run_id, required=not bool(default_run_id))
    parser.add_argument(
        "--db",
        default=os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL"),
        required=not bool(os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL")),
    )


def _decision_arguments(parser) -> None:
    _common_arguments(parser)
    default_tickers = os.getenv("PAPER_TICKERS")
    parser.add_argument("--tickers", default=default_tickers, required=not bool(default_tickers))
    parser.add_argument("--benchmark", default=os.getenv("PAPER_BENCHMARK", "SPY"))
    parser.add_argument("--analysts", default=os.getenv("PAPER_ANALYSTS", "market,social,news"))
    parser.add_argument("--replicates", type=int, default=int(os.getenv("PAPER_REPLICATES", "1")))
    parser.add_argument(
        "--portfolio-mode",
        default=os.getenv("PAPER_PORTFOLIO_MODE", "long-only"),
        choices=("long-only", "long-short", "market-neutral"),
    )
    parser.add_argument("--gross-limit", type=float, default=1.0)
    parser.add_argument("--max-weight", type=float, default=0.25)
    parser.add_argument(
        "--cost-bps",
        type=float,
        default=float(os.getenv("PAPER_TRADING_COST_BPS", "5")),
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=float(os.getenv("PAPER_SLIPPAGE_BPS", "5")),
    )
    parser.add_argument(
        "--annual-borrow-bps",
        type=float,
        default=float(os.getenv("PAPER_ANNUAL_BORROW_BPS", "300")),
    )
    parser.add_argument("--results-dir", default="results/paper-agent-runs")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--engine",
        default=os.getenv("PAPER_ENGINE", "legacy-ratings"),
        choices=("legacy-ratings", "formal-global-v2"),
    )
    decisions_default = os.getenv("PAPER_DECISIONS_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    parser.add_argument(
        "--decisions-enabled",
        action=argparse.BooleanOptionalAction,
        default=decisions_default,
        help="Allow new decisions; marks continue while disabled",
    )
    parser.add_argument(
        "--llm-model-allowlist",
        default=os.getenv("PAPER_LLM_MODEL_ALLOWLIST"),
        help="Comma-separated exact provider:model identities authorized for formal calls",
    )
    parser.add_argument(
        "--llm-max-calls-per-decision",
        type=int,
        default=int(os.getenv("PAPER_LLM_MAX_CALLS_PER_DECISION", "3")),
        help="Persistent high-level LLM call ceiling for one formal decision",
    )
    parser.add_argument(
        "--llm-max-calls-per-utc-day",
        type=int,
        default=int(os.getenv("PAPER_LLM_MAX_CALLS_PER_UTC_DAY", "3")),
        help="Persistent high-level LLM call ceiling shared by formal runs each UTC day",
    )
    parser.add_argument(
        "--llm-max-prompt-bytes",
        type=int,
        default=int(os.getenv("PAPER_LLM_MAX_PROMPT_BYTES", "160000")),
        help="Hard UTF-8 prompt-size ceiling applied before reserving or invoking a model",
    )
    parser.add_argument(
        "--llm-max-completion-tokens",
        type=int,
        default=int(os.getenv("PAPER_LLM_MAX_COMPLETION_TOKENS", "8000")),
        help="Provider-enforced ceiling including visible output and reasoning tokens",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=int,
        default=int(os.getenv("PAPER_LLM_TIMEOUT_SECONDS", "180")),
        help="Per-invocation model request timeout",
    )
    global_only_default = os.getenv("PAPER_GLOBAL_TOPICS_ONLY", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    parser.add_argument("--global-topics-only", action="store_true", default=global_only_default)


def _marker_arguments(parser) -> None:
    """Arguments needed to reconstruct the exact marker configuration."""
    _common_arguments(parser)
    parser.add_argument("--tickers", default=os.getenv("PAPER_TICKERS"))
    parser.add_argument("--benchmark", default=os.getenv("PAPER_BENCHMARK", "SPY"))
    parser.add_argument(
        "--portfolio-mode",
        default=os.getenv("PAPER_PORTFOLIO_MODE", "long-only"),
        choices=("long-only", "long-short", "market-neutral"),
    )
    parser.add_argument(
        "--cost-bps",
        type=float,
        default=float(os.getenv("PAPER_TRADING_COST_BPS", "5")),
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=float(os.getenv("PAPER_SLIPPAGE_BPS", "5")),
    )
    parser.add_argument(
        "--annual-borrow-bps",
        type=float,
        default=float(os.getenv("PAPER_ANNUAL_BORROW_BPS", "300")),
    )
    parser.add_argument(
        "--engine",
        default=os.getenv("PAPER_ENGINE", "legacy-ratings"),
        choices=("legacy-ratings", "formal-global-v2"),
    )
    marks_default = os.getenv("PAPER_MARKS_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    parser.add_argument(
        "--marks-enabled",
        action=argparse.BooleanOptionalAction,
        default=marks_default,
        help="Allow new formal price captures; durable authorization is still required",
    )


def _cycle_locked(args, now_utc: datetime | None = None) -> dict:
    """Run a paper cycle while the caller holds any required operation lock."""
    now = now_utc or datetime.now(timezone.utc)
    marks = []
    strategy_marks = []
    already_frozen = False
    decision_date = None
    run_exists = False
    formal_completed_intervals = 0
    formal_review = None
    formal_interim_reviews = []
    engine = getattr(args, "engine", "legacy-ratings")
    if engine == "formal-global-v2":
        raise ValueError(
            "combined formal cycle is retired; use decision-cycle or marker-cycle"
        )
    store = PaperStore(
        args.db,
        auto_migrate=(
            False
            if args.command == "mark" and args.engine == "formal-global-v2"
            else None
        ),
    )
    try:
        try:
            store.run_config(args.run_id)
        except ValueError:
            pass
        else:
            run_exists = True
            if engine == "formal-global-v2":
                # A prior process may have committed the champion mark and its
                # return receipts before failing on one shadow insert.  Finish
                # that exact session from stored inputs before advancing.
                latest_champion = store.latest_mark(args.run_id)
                if latest_champion is not None:
                    strategy_marks.extend(
                        mark_formal_strategies(store, args.run_id, latest_champion)
                    )
                terminal_price_failure = store.price_integrity_failure(args.run_id)
                if terminal_price_failure is not None:
                    raise FormalPriceIntegrityError(
                        "terminal price integrity failure blocks formal trial continuation"
                    )
                formal_counts = store.formal_trial_counts(args.run_id)
                formal_completed_intervals = int(formal_counts["completed_intervals"])
                if formal_completed_intervals > FORMAL_HOLDING_INTERVALS:
                    raise ValueError("formal confirmatory holding horizon was exceeded")
                from tradingagents.formal_interim import materialize_due_formal_interims

                due_interims = materialize_due_formal_interims(store, args.run_id, now.timestamp())
                formal_interim_reviews.extend(
                    _safe_review_identity(review) for review in due_interims
                )
            while True:
                if (
                    engine == "formal-global-v2"
                    and formal_completed_intervals >= FORMAL_HOLDING_INTERVALS
                ):
                    break
                previous = store.latest_mark(args.run_id)
                due = (
                    next_session_date(previous["session_date"])
                    if previous
                    else store.first_entry_date(args.run_id)
                )
                due_time = (
                    formal_price_capture_window(due)[0]
                    if engine == "formal-global-v2" and due is not None
                    else (
                        session_open_utc(due) + timedelta(minutes=15) if due is not None else None
                    )
                )
                if due is None or due_time is None or due_time > now:
                    break
                mark = mark_next(store, args.run_id)
                marks.append(mark)
                if engine == "formal-global-v2":
                    strategy_marks.extend(mark_formal_strategies(store, args.run_id, mark))
                    formal_completed_intervals = int(
                        store.formal_trial_counts(args.run_id)["completed_intervals"]
                    )
                    due_interims = materialize_due_formal_interims(
                        store, args.run_id, now.timestamp()
                    )
                    formal_interim_reviews.extend(
                        _safe_review_identity(review) for review in due_interims
                    )
                    # A formal invocation may capture only its single next
                    # session.  Any older missed session is terminal, never a
                    # mutable-vendor catch-up loop.
                    break
            if (
                engine == "formal-global-v2"
                and formal_completed_intervals == FORMAL_HOLDING_INTERVALS
            ):
                from tradingagents.formal_review import materialize_final_formal_review

                review = materialize_final_formal_review(store, args.run_id, now.timestamp())
                formal_review = _safe_review_identity(review)
        try:
            decision_date = current_decision_date(now)
        except DecisionWindowClosedError:
            decision_date = None
        if decision_date is not None and run_exists:
            already_frozen = store.has_decision(args.run_id, decision_date)
    finally:
        store.close()
    if decision_date is None:
        if not marks and not strategy_marks:
            raise DecisionWindowClosedError("not inside a decision window and no open mark is due")
        return {
            "decision_date": None,
            "marks_recorded": [mark["session_date"] for mark in marks],
            "strategy_marks_recorded": strategy_marks,
            "decision_recorded": False,
            "decisions_enabled": getattr(args, "decisions_enabled", True),
            "formal_completed_intervals": formal_completed_intervals,
            "decision_horizon_open": (
                engine != "formal-global-v2"
                or formal_completed_intervals < FORMAL_HOLDING_INTERVALS - 1
            ),
            "formal_review": formal_review,
            "formal_interim_reviews": formal_interim_reviews,
            "engine": engine,
            "decision": None,
        }
    decision = None
    decisions_enabled = getattr(args, "decisions_enabled", True)
    decision_horizon_open = (
        engine != "formal-global-v2" or formal_completed_intervals < FORMAL_HOLDING_INTERVALS - 1
    )
    if not already_frozen and decisions_enabled and decision_horizon_open:
        if engine == "formal-global-v2":
            from tradingagents.formal_experiment import decide_formal

            decision = decide_formal(args, now)
        else:
            decision = decide(args, now)
    return {
        "decision_date": decision_date,
        "marks_recorded": [mark["session_date"] for mark in marks],
        "strategy_marks_recorded": strategy_marks,
        "decision_recorded": decision is not None,
        "decisions_enabled": decisions_enabled,
        "formal_completed_intervals": formal_completed_intervals,
        "decision_horizon_open": decision_horizon_open,
        "formal_review": formal_review,
        "formal_interim_reviews": formal_interim_reviews,
        "engine": engine,
        "decision": decision,
    }


def cycle(args, now_utc: datetime | None = None) -> dict:
    """Mark and decide, serializing the complete formal operation per run."""
    if getattr(args, "engine", "legacy-ratings") == "formal-global-v2":
        with formal_operation_lock(args.db, args.run_id):
            return _cycle_locked(args, now_utc)
    return _cycle_locked(args, now_utc)


def next_daemon_run(now_utc: datetime | None = None) -> datetime:
    """Next 00:05 UTC, immediately after the captured-media daily cutoff."""
    now = now_utc or datetime.now(timezone.utc)
    candidate = now.replace(hour=0, minute=5, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def next_worker_run(now_utc: datetime | None = None) -> datetime:
    """Next evidence-cutoff decision or executable-open receipt, whichever comes first."""
    now = now_utc or datetime.now(timezone.utc)
    return min(next_daemon_run(now), next_marker_run(now))


def next_marker_run(now_utc: datetime | None = None) -> datetime:
    """Next frozen open+delay marker capture window."""
    now = now_utc or datetime.now(timezone.utc)
    calendar = _calendar()
    session = calendar.date_to_session(pd.Timestamp(now.date()), direction="next")
    delay_minutes = int(
        GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
            "scheduled_delay_after_xnys_session_open_minutes"
        ]
    )
    mark_time = calendar.session_open(session).to_pydatetime().astimezone(timezone.utc) + timedelta(
        minutes=delay_minutes
    )
    if mark_time <= now:
        session = calendar.next_session(session)
        mark_time = calendar.session_open(session).to_pydatetime().astimezone(
            timezone.utc
        ) + timedelta(minutes=delay_minutes)
    return mark_time


def decision_cycle(args, now_utc: datetime | None = None) -> dict:
    """Run only the outcome-blind formal decision side once."""
    if getattr(args, "engine", None) != "formal-global-v2":
        raise ValueError("decision-cycle requires formal-global-v2")
    enabled = bool(getattr(args, "decisions_enabled", False))
    if not enabled:
        return {
            "run_id": args.run_id,
            "worker_role": "paper_decision",
            "decision_recorded": False,
            "paused": True,
        }
    from tradingagents.formal_experiment import decide_formal

    decision = decide_formal(args, now_utc)
    already_recorded = decision.get("already_recorded") is True
    return {
        "run_id": args.run_id,
        "worker_role": "paper_decision",
        "decision_recorded": not already_recorded,
        "already_recorded": already_recorded,
        "paused": False,
        "decision": decision,
    }


def marker_cycle(args, now_utc: datetime | None = None) -> dict:
    """Run only the formal market-capture/marking side once."""
    if getattr(args, "engine", None) != "formal-global-v2":
        raise ValueError("marker-cycle requires formal-global-v2")
    enabled = bool(getattr(args, "marks_enabled", False))
    if not enabled:
        return {
            "run_id": args.run_id,
            "worker_role": "paper_marker",
            "mark_recorded": False,
            "paused": True,
        }
    # Prove that migrations are explicitly disabled and every non-secret
    # marker setting matches the protocol before PaperStore can run any
    # constructor-time database behavior.
    _formal_marker_runtime_material(args)
    store = PaperStore(args.db, auto_migrate=False)
    try:
        result = _mark_formal_once(store, args.run_id, runtime_args=args)
    finally:
        store.close()
    return {
        **result,
        "worker_role": "paper_marker",
        "paused": False,
    }


def _record_daemon_heartbeat(db_url: str, key: str, captured_utc: float) -> None:
    from tradingagents.dataflows.media_store import open_store

    store = open_store(db_url)
    try:
        store.set_meta(key, captured_utc)
    finally:
        store.close()


def _cycle_with_retries(
    args,
    *,
    attempts: int = 3,
    retry_seconds: float = 300.0,
    sleep_fn=time.sleep,
) -> dict | None:
    """Run a paper cycle with bounded retries while keeping the daemon alive."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        now = datetime.now(timezone.utc)
        try:
            result = cycle(args, now)
            _record_daemon_heartbeat(args.db, "paper:last_success_utc", now.timestamp())
            return result
        except DecisionWindowClosedError as exc:
            # Expected outside-window control flow; no data or ledger failure.
            logger.warning("Paper cycle skipped: %s", exc)
            return None
        except FormalPriceIntegrityError as exc:
            logger.error("Formal paper trial halted: %s", exc)
            try:
                _record_daemon_heartbeat(args.db, "paper:last_failure_utc", now.timestamp())
            except Exception:  # noqa: BLE001
                logger.exception("Could not record terminal paper failure heartbeat")
            return None
        except Exception:  # noqa: BLE001 — keep the scheduled worker alive
            logger.exception("Paper cycle attempt %d/%d failed", attempt, attempts)
            try:
                _record_daemon_heartbeat(args.db, "paper:last_failure_utc", now.timestamp())
            except Exception:  # noqa: BLE001
                logger.exception("Could not record paper failure heartbeat")
            consumed_formal_invocation = False
            if getattr(args, "engine", "legacy-ratings") == "formal-global-v2":
                try:
                    failed_decision_date = current_decision_date(now)
                    receipt_store = PaperStore(args.db, auto_migrate=False)
                    try:
                        durable_receipts = bool(
                            receipt_store.formal_invocation_receipts(
                                args.run_id, failed_decision_date
                            )
                        )
                        decision_already_persisted = receipt_store.has_decision(
                            args.run_id, failed_decision_date
                        )
                    finally:
                        receipt_store.close()
                    consumed_formal_invocation = (
                        durable_receipts
                    ) and not decision_already_persisted
                except DecisionWindowClosedError:
                    pass
                except Exception:  # noqa: BLE001
                    logger.exception("Could not inspect formal invocation receipts after failure")
            if consumed_formal_invocation:
                logger.error(
                    "Formal decision %s consumed an invocation; suppressing same-day "
                    "retries so its interval carries forward",
                    failed_decision_date,
                )
                emit_alert(
                    "paper-worker",
                    "formal_invocation_consumed_carry_forward",
                    details={
                        "run_id": getattr(args, "run_id", None),
                        "decision_date": failed_decision_date,
                    },
                )
                return None
            if attempt < attempts:
                sleep_fn(retry_seconds)
    emit_alert(
        "paper-worker",
        "cycle_retries_exhausted",
        details={"attempts": attempts, "run_id": getattr(args, "run_id", None)},
    )
    raise RuntimeError(f"paper cycle failed after {attempts} attempts")


def _formal_worker_with_retries(
    args,
    *,
    role: str,
    attempts: int = 3,
    retry_seconds: float = 300.0,
    sleep_fn=time.sleep,
) -> dict | None:
    """Retry exactly one split-worker operation without crossing role boundaries."""
    if role not in {"paper_decision", "paper_marker"}:
        raise ValueError("formal worker role is not allowlisted")
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    operation = decision_cycle if role == "paper_decision" else marker_cycle
    for attempt in range(1, attempts + 1):
        now = datetime.now(timezone.utc)
        try:
            result = operation(args, now)
            heartbeat_event = "paused" if result.get("paused") else "success"
            try:
                _record_formal_worker_heartbeat(
                    args, role=role, event_type=heartbeat_event
                )
            except Exception:  # noqa: BLE001 - heartbeat cannot expose credentials
                logger.exception("Could not record %s %s heartbeat", role, heartbeat_event)
            return result
        except DecisionWindowClosedError as exc:
            logger.warning("%s worker skipped: %s", role, exc)
            # A split worker can wake for its daily liveness check while no
            # exchange action is due (notably the marker over weekends).  That
            # is a healthy authenticated no-op, not a missing heartbeat.
            try:
                _record_formal_worker_heartbeat(
                    args, role=role, event_type="success"
                )
            except Exception:  # noqa: BLE001 - preserve expected idle control flow
                logger.exception("Could not record idle %s heartbeat", role)
            return None
        except FormalPriceIntegrityError as exc:
            logger.error("Formal marker halted: %s", exc)
            try:
                _record_formal_worker_heartbeat(
                    args, role=role, event_type="failure"
                )
            except Exception:  # noqa: BLE001 - preserve terminal causal failure
                logger.exception("Could not record terminal %s heartbeat", role)
            emit_alert(
                role,
                "formal_price_integrity_halt",
                details={"run_id": getattr(args, "run_id", None)},
            )
            return None
        except Exception:  # noqa: BLE001 - bounded daemon retry boundary
            logger.exception("%s attempt %d/%d failed", role, attempt, attempts)
            try:
                _record_formal_worker_heartbeat(
                    args, role=role, event_type="failure"
                )
            except Exception:  # noqa: BLE001 - preserve the causal failure
                logger.exception("Could not record %s failure heartbeat", role)
            if role == "paper_decision":
                consumed = False
                failed_decision_date = None
                try:
                    failed_decision_date = current_decision_date(now)
                    receipt_store = PaperStore(args.db, auto_migrate=False)
                    try:
                        consumed = bool(
                            receipt_store.formal_invocation_receipts(
                                args.run_id, failed_decision_date
                            )
                        ) and not receipt_store.has_decision(
                            args.run_id, failed_decision_date
                        )
                    finally:
                        receipt_store.close()
                except DecisionWindowClosedError:
                    pass
                except Exception:  # noqa: BLE001 - preserve the causal failure
                    logger.exception(
                        "Could not inspect decision invocation receipts after failure"
                    )
                if consumed:
                    emit_alert(
                        role,
                        "formal_invocation_consumed_carry_forward",
                        details={
                            "run_id": getattr(args, "run_id", None),
                            "decision_date": failed_decision_date,
                        },
                    )
                    return None
            if attempt < attempts:
                sleep_fn(retry_seconds)
    emit_alert(
        role,
        "cycle_retries_exhausted",
        details={"attempts": attempts, "run_id": getattr(args, "run_id", None)},
    )
    raise RuntimeError(f"{role} cycle failed after {attempts} attempts")


def _formal_worker_daemon(args, *, role: str) -> None:
    attempts = int(os.getenv("PAPER_RETRY_ATTEMPTS", "3"))
    retry_seconds = float(os.getenv("PAPER_RETRY_SECONDS", "300"))
    while True:
        result = _formal_worker_with_retries(
            args,
            role=role,
            attempts=attempts,
            retry_seconds=retry_seconds,
        )
        if result is not None:
            print(json.dumps(result), flush=True)
        now = datetime.now(timezone.utc)
        # The marker also wakes at the daily cutoff so its health cannot look
        # stale throughout weekends or exchange holidays.  Its cycle fails
        # closed before market-data access when the next open is not yet due.
        wake = next_daemon_run(now) if role == "paper_decision" else next_worker_run(now)
        time.sleep(max(1.0, (wake - datetime.now(timezone.utc)).total_seconds()))


def decision_daemon(args) -> None:
    """Run the outcome-blind formal decision schedule."""
    _formal_worker_daemon(args, role="paper_decision")


def marker_daemon(args) -> None:
    """Run the market-capture-only formal marker schedule."""
    _formal_worker_daemon(args, role="paper_marker")


def daemon(args) -> None:
    """Run one idempotent paper cycle after each UTC data cutoff."""
    if getattr(args, "engine", "legacy-ratings") == "formal-global-v2":
        raise ValueError(
            "combined formal daemon is retired; use decision-daemon or marker-daemon"
        )
    attempts = int(os.getenv("PAPER_RETRY_ATTEMPTS", "3"))
    retry_seconds = float(os.getenv("PAPER_RETRY_SECONDS", "300"))
    while True:
        result = _cycle_with_retries(args, attempts=attempts, retry_seconds=retry_seconds)
        if result is not None:
            print(json.dumps(result), flush=True)
        wake = next_worker_run(datetime.now(timezone.utc))
        time.sleep(max(1.0, (wake - datetime.now(timezone.utc)).total_seconds()))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    decide_parser = commands.add_parser("decide", help="Freeze the current forward decision")
    _decision_arguments(decide_parser)
    cycle_parser = commands.add_parser(
        "cycle", help="Mark due opens and freeze the current decision once"
    )
    _decision_arguments(cycle_parser)
    daemon_parser = commands.add_parser("daemon", help="Run an idempotent cycle daily at 00:05 UTC")
    _decision_arguments(daemon_parser)
    decision_cycle_parser = commands.add_parser(
        "decision-cycle", help="Run one outcome-blind formal decision cycle"
    )
    _decision_arguments(decision_cycle_parser)
    decision_daemon_parser = commands.add_parser(
        "decision-daemon", help="Run only the formal decision worker"
    )
    _decision_arguments(decision_daemon_parser)
    decision_release_parser = commands.add_parser(
        "decision-release-material",
        help="Emit the exact in-image decision configuration and preflight",
    )
    _decision_arguments(decision_release_parser)
    marker_cycle_parser = commands.add_parser(
        "marker-cycle", help="Run one formal market-capture cycle"
    )
    _marker_arguments(marker_cycle_parser)
    marker_daemon_parser = commands.add_parser(
        "marker-daemon", help="Run only the formal marker worker"
    )
    _marker_arguments(marker_daemon_parser)
    marker_release_parser = commands.add_parser(
        "marker-release-material",
        help="Emit the exact in-image marker configuration and preflight",
    )
    _marker_arguments(marker_release_parser)
    marker_rehearsal_parser = commands.add_parser(
        "marker-release-rehearsal",
        help=(
            "Replay one stored marker interval from immutable clone rows with "
            "no provider calls"
        ),
    )
    _marker_arguments(marker_rehearsal_parser)
    marker_rehearsal_parser.add_argument(
        "--session-date",
        help="Completed XNYS interval to replay; defaults to the latest eligible interval",
    )
    mark_parser = commands.add_parser("mark", help="Capture and mark the next portfolio open")
    _marker_arguments(mark_parser)
    status_parser = commands.add_parser("status", help="Show immutable ledger status")
    _common_arguments(status_parser)
    verify_parser = commands.add_parser(
        "verify-formal",
        help="Replay and verify a stored formal decision without external calls",
    )
    _common_arguments(verify_parser)
    verify_parser.add_argument(
        "--decision-date", help="Decision session to verify; defaults to the latest"
    )
    report_parser = commands.add_parser(
        "formal-report",
        help="View the access-labeled final report after exactly 252 intervals",
    )
    _common_arguments(report_parser)
    interim_report_parser = commands.add_parser(
        "formal-interim-report",
        help="View an already-materialized access-labeled 20/60/126 interim report",
    )
    _common_arguments(interim_report_parser)
    interim_report_parser.add_argument(
        "--review-gate", required=True, type=int, choices=(20, 60, 126)
    )
    label_parser = commands.add_parser("label-run", help="Append an immutable run label")
    _common_arguments(label_parser)
    label_parser.add_argument("--label", required=True)
    label_parser.add_argument("--details", default="{}", help="JSON object with label context")
    args = parser.parse_args(argv)

    if args.command in {
        "decision-release-material",
        "marker-release-material",
        "marker-release-rehearsal",
    }:
        from tradingagents.formal_runtime import in_image_preflight_identity

        pause_name = (
            "PAPER_DECISIONS_ENABLED"
            if args.command == "decision-release-material"
            else "PAPER_MARKS_ENABLED"
        )
        action_enabled = (
            args.decisions_enabled
            if args.command == "decision-release-material"
            else args.marks_enabled
        )
        pause_value = os.environ.get(pause_name)
        if (
            not isinstance(pause_value, str)
            or pause_value.strip().lower() not in {"0", "false", "no", "off"}
            or action_enabled
        ):
            parser.error(f"{pause_name} must be explicitly false for release material")
        try:
            if args.command == "decision-release-material":
                component, outcome_id = _formal_decision_runtime_material(args)
            else:
                component, outcome_id = _formal_marker_runtime_material(args)
            material = in_image_preflight_identity(
                component,
                env=os.environ,
                resolved_outcome_semantics_id=outcome_id,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if args.command == "marker-release-rehearsal":
            from tradingagents.formal_marker_rehearsal import (
                verify_formal_marker_rehearsal,
            )

            store = PaperStore(args.db, auto_migrate=False)
            try:
                try:
                    receipt = verify_formal_marker_rehearsal(
                        store,
                        run_id=args.run_id,
                        marker_build_id=material["preflight_payload"]["build_id"],
                        session_date=args.session_date,
                    )
                except ValueError as exc:
                    parser.error(str(exc))
                print(json.dumps(receipt, sort_keys=True))
                return
            finally:
                store.close()
        print(json.dumps(material, sort_keys=True))
        return

    if args.command == "mark" and args.engine == "formal-global-v2":
        if not args.marks_enabled:
            parser.error("new formal price captures are paused")
        try:
            _formal_marker_runtime_material(args)
        except ValueError as exc:
            parser.error(str(exc))

    decision_commands = {
        "decide",
        "cycle",
        "daemon",
        "decision-cycle",
        "decision-daemon",
    }
    if args.command in decision_commands:
        if args.replicates < 1:
            parser.error("--replicates must be >= 1")
        if min(args.cost_bps, args.slippage_bps, args.annual_borrow_bps) < 0:
            parser.error("cost, slippage, and borrow rates must be >= 0")
        analysts = {value.strip() for value in args.analysts.split(",") if value.strip()}
        if args.global_topics_only and "social" in analysts:
            parser.error(
                "--global-topics-only is incompatible with the ticker-specific social analyst"
            )
        if args.command == "daemon":
            daemon(args)
            return
        if args.command == "decision-daemon":
            if args.engine != "formal-global-v2":
                parser.error("decision-daemon requires --engine formal-global-v2")
            decision_daemon(args)
            return
        try:
            if args.command == "decide":
                if not args.decisions_enabled:
                    raise ValueError("new paper decisions are paused")
                if args.engine == "formal-global-v2":
                    from tradingagents.formal_experiment import decide_formal

                    result = decide_formal(args)
                else:
                    result = decide(args)
            elif args.command == "decision-cycle":
                result = decision_cycle(args)
            else:
                result = cycle(args)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return

    if args.command in {"marker-cycle", "marker-daemon", "mark"}:
        if args.engine == "formal-global-v2" and not args.tickers:
            parser.error("PAPER_TICKERS or --tickers is required for a formal marker")
        if min(args.cost_bps, args.slippage_bps, args.annual_borrow_bps) < 0:
            parser.error("cost, slippage, and borrow rates must be >= 0")
        if args.command == "marker-daemon":
            if args.engine != "formal-global-v2":
                parser.error("marker-daemon requires --engine formal-global-v2")
            marker_daemon(args)
            return
        if args.command == "marker-cycle":
            try:
                result = marker_cycle(args)
            except ValueError as exc:
                parser.error(str(exc))
            print(json.dumps(result, indent=2))
            return

    store = PaperStore(
        args.db,
        auto_migrate=(
            False
            if args.command == "mark" and args.engine == "formal-global-v2"
            else None
        ),
    )
    try:
        if args.command == "mark":
            if store.run_config(args.run_id).get("engine") == "formal-global-v2":
                if not args.marks_enabled:
                    raise ValueError("new formal price captures are paused")
                result = _mark_formal_once(
                    store, args.run_id, runtime_args=args
                )
            else:
                result = mark_next(store, args.run_id)
        elif args.command == "verify-formal":
            from tradingagents.formal_verifier import verify_formal

            try:
                result = verify_formal(store, args.run_id, args.decision_date)
            except ValueError as exc:
                parser.error(str(exc))
        elif args.command == "formal-report":
            from tradingagents.formal_review import load_final_formal_report

            try:
                with formal_operation_lock(store.url, args.run_id):
                    result = load_final_formal_report(
                        store,
                        args.run_id,
                        datetime.now(timezone.utc).timestamp(),
                    )
            except ValueError as exc:
                parser.error(str(exc))
        elif args.command == "formal-interim-report":
            from tradingagents.formal_interim import load_formal_interim_report

            try:
                with formal_operation_lock(store.url, args.run_id):
                    result = load_formal_interim_report(
                        store,
                        args.run_id,
                        args.review_gate,
                        datetime.now(timezone.utc).timestamp(),
                    )
            except ValueError as exc:
                parser.error(str(exc))
        elif args.command == "label-run":
            try:
                details = json.loads(args.details)
            except json.JSONDecodeError as exc:
                parser.error(f"--details must be JSON: {exc}")
            if not isinstance(details, dict):
                parser.error("--details must be a JSON object")
            result = {
                "run_id": args.run_id,
                "label": args.label,
                "created": store.label_run(
                    args.run_id, args.label, datetime.now(timezone.utc).timestamp(), details
                ),
            }
        else:
            result = store.status(args.run_id)
    finally:
        store.close()
    if args.command == "status":
        from tradingagents.dataflows.media_store import open_store

        heartbeat_store = open_store(args.db)
        try:
            result["last_success_utc"] = heartbeat_store.get_meta("paper:last_success_utc")
            result["last_failure_utc"] = heartbeat_store.get_meta("paper:last_failure_utc")
        finally:
            heartbeat_store.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
