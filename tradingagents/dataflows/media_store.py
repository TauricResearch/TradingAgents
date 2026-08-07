"""Storage backend for accumulated social/news media (the poller's data store).

The poller appends one row per message/post and dedups on ``(source,
external_id)`` so overlapping polls don't double-count. For local use the
default is a SQLite file (stdlib, zero extra dependencies). For cloud hosting —
where a container's local disk is ephemeral — point ``MEDIA_DB_URL`` at a
managed database (e.g. Postgres) and the same code persists there instead:

    MEDIA_DB_URL=postgresql+psycopg://user:pass@host:5432/trading

Non-SQLite URLs require the optional extra: ``pip install 'tradingagents[poller]'``.

Both backends expose the same interface — including ``complete_fetch()``,
``store()``, ``stats()``, and ``window()`` — so the poller and backtest loader
are agnostic to where the data lives. ``complete_fetch()`` is the collector's
atomic response/item-lineage/terminal-receipt boundary. ``window()`` returns
the look-ahead-safe slice a backtest at a given trade date should feed analysts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradingagents.evidence_lineage import evidence_id, raw_content_id

logger = logging.getLogger(__name__)

# Core post columns shared by both backends. Fetchers may also emit ``labels``
# and ``metadata``; those are normalized into append-only association tables.
COLUMNS = (
    "source", "external_id", "ticker", "subreddit", "author", "sentiment",
    "created_utc", "title", "body", "fetched_utc",
)

# Prediction-market odds are a time series: the same market is re-captured each
# cycle, so the row key is (market_id, captured_utc), not a static id.
ODDS_COLUMNS = (
    "theme", "topic", "market_id", "captured_utc",
    "question", "probability", "volume", "resolution_utc",
)

FETCH_RUN_COLUMNS = (
    "fetch_run_id", "provider", "query_key", "started_utc", "received_utc",
    "completed_utc", "status", "item_count", "inserted_count", "error",
    "formal_eligible_item_count", "formal_eligible_evidence_ids_json",
    "formal_eligible_lineage_json", "cost_units", "cursor_before", "cursor_after",
    "metadata_json", "collection_cycle_id", "server_started_utc",
    "server_terminal_utc", "collector_build_id",
)

COLLECTION_CYCLE_COLUMNS = (
    "collection_cycle_id", "cycle_kind", "period_key", "protocol_id",
    "collector_semantics_id", "identity_json", "started_utc", "completed_utc",
    "status", "manifest_id", "manifest_json", "server_started_utc",
    "server_terminal_utc", "collector_build_id",
)

COLLECTION_CYCLE_SLOT_COLUMNS = (
    "collection_cycle_id", "provider", "query_key", "slot_kind", "declared_utc",
)

_FORMAL_EVIDENCE_ID = re.compile(r"evidence_[0-9a-f]{24}")
_FORMAL_RAW_CONTENT_ID = re.compile(r"raw_[0-9a-f]{24}")
_COLLECTION_CYCLE_ID = re.compile(r"cycle_[0-9a-f]{24}")
_COLLECTION_CYCLE_MANIFEST_ID = re.compile(r"cycle_manifest_[0-9a-f]{24}")
_COLLECTION_CYCLE_KIND = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_COLLECTOR_BUILD_ID = re.compile(r"build_[0-9a-f]{24}")
_FORMAL_MEDIA_SOURCES = frozenset({"globalnews", "trendnews", "x"})
_IMMUTABLE_MEDIA_FIELDS = ("created_utc", "title", "body")
_IMMUTABLE_NEWS_PROVENANCE_FIELDS = (
    "publisher_domain",
    "article_url",
    "provider_external_id",
    "content_vintage_id",
    "content_vintage_schema_version",
)
# One session-level PostgreSQL advisory lock prevents accidental scale-out or a
# manual one-shot from issuing provider requests beside the production daemon.
_COLLECTOR_ADVISORY_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"tradingagents:global-collector:v1").digest()[:8], "big"
) & ((1 << 63) - 1)
_COLLECTOR_PREFLIGHT_ADVISORY_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"tradingagents:global-collector:preflight:v1").digest()[:8],
    "big",
) & ((1 << 63) - 1)
_COLLECTOR_LEASE_HEARTBEAT_SECONDS = 30.0
_POSTGRES_POOL_RECYCLE_SECONDS = 540
_FLY_MPG_POOL_HOST = re.compile(
    r"pgbouncer\.(?P<cluster>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.flympg\.net"
)
_FLY_MPG_DIRECT_HOST = re.compile(
    r"direct\.(?P<cluster>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.flympg\.net"
)
_LOCAL_POSTGRES_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# Every digest is copied from, and statically checked against, the normalized
# pg_proc.prosrc body in migrations 006/007/009.  Preflight verifies both the
# independently stored comment and the live body hash so renaming a stale or
# altered function cannot satisfy the contract.
_COLLECTOR_FUNCTION_CONTRACTS = {
    "public.canonical_jsonb_text(jsonb)": (
        "tradingagents.canonical-jsonb-text.v1;"
        "normalized-prosrc-sha256="
        "5d530ed30c769012e3ec4cc7650ae6f276ea0019ddaf8d13f2c4d165f6e7c78f",
        "5d530ed30c769012e3ec4cc7650ae6f276ea0019ddaf8d13f2c4d165f6e7c78f",
        "i",
    ),
    "public.enforce_fetch_run_lifecycle()": (
        "tradingagents.fetch-run-lifecycle.v3;"
        "normalized-prosrc-sha256="
        "e69793ca6965e8ddccd178088b0506c178f369a88d2d501b05d0ca7d9e2e2b84",
        "e69793ca6965e8ddccd178088b0506c178f369a88d2d501b05d0ca7d9e2e2b84",
        "v",
    ),
    "public.enforce_fetch_run_item_lifecycle()": (
        "tradingagents.fetch-run-item-lifecycle.v1;"
        "normalized-prosrc-sha256="
        "3b09b817e4945f2fe39b831a7695ad2c8ee0acd7e19084ed1ff31ee7b2d989fa",
        "3b09b817e4945f2fe39b831a7695ad2c8ee0acd7e19084ed1ff31ee7b2d989fa",
        "v",
    ),
    "public.enforce_fetch_run_content_completion()": (
        "tradingagents.fetch-run-content-completion.v1;"
        "normalized-prosrc-sha256="
        "26e4ec999f2e0a92b95e2d5c0dfa93373a40ebf2c0301a309afa6fa32f616514",
        "26e4ec999f2e0a92b95e2d5c0dfa93373a40ebf2c0301a309afa6fa32f616514",
        "v",
    ),
    "public.enforce_collection_cycle_lifecycle()": (
        "tradingagents.collection-cycle-lifecycle.v2;"
        "normalized-prosrc-sha256="
        "ba161044134abafec2cc38b27ee790d1772a8ac68857d54158f1237a79c7cab8",
        "ba161044134abafec2cc38b27ee790d1772a8ac68857d54158f1237a79c7cab8",
        "v",
    ),
    "public.enforce_collection_cycle_slot_lifecycle()": (
        "tradingagents.collection-cycle-slot-lifecycle.v1;"
        "normalized-prosrc-sha256="
        "e64e3c6c91b954edc370fae0db4d2b6f585935c134389f8a7f3d1e4f578dfce4",
        "e64e3c6c91b954edc370fae0db4d2b6f585935c134389f8a7f3d1e4f578dfce4",
        "v",
    ),
    "public.enforce_fetch_run_cycle_binding()": (
        "tradingagents.fetch-run-cycle-binding.v2;"
        "normalized-prosrc-sha256="
        "d340d1423c67392398e9d949c0494304db608acaeb5d3f3e6275540f11cb5c1c",
        "d340d1423c67392398e9d949c0494304db608acaeb5d3f3e6275540f11cb5c1c",
        "v",
    ),
}

# Constraint definitions whose structure is essential to deduplication and
# parent/lineage integrity. Every CHECK body is hash-pinned below; primary,
# unique, and foreign keys are matched by exact ordered columns/targets.
_COLLECTOR_CONSTRAINT_CONTRACTS = {
    ("media_posts", "media_posts_pkey"): ("p", ("source", "external_id"), None, ()),
    ("media_labels", "media_labels_pkey"): (
        "p", ("source", "external_id", "label"), None, (),
    ),
    ("media_observations", "media_observations_pkey"): (
        "p", ("source", "external_id", "observed_utc"), None, (),
    ),
    ("macro_odds", "macro_odds_pkey"): (
        "p", ("market_id", "captured_utc"), None, (),
    ),
    ("poll_state", "poll_state_pkey"): ("p", ("key",), None, ()),
    ("collection_cycles", "collection_cycles_pkey"): (
        "p", ("collection_cycle_id",), None, (),
    ),
    ("collection_cycle_slots", "collection_cycle_slots_pkey"): (
        "p", ("collection_cycle_id", "provider", "query_key"), None, (),
    ),
    ("fetch_runs", "fetch_runs_pkey"): ("p", ("fetch_run_id",), None, ()),
    ("fetch_run_items", "fetch_run_items_pkey"): (
        "p", ("fetch_run_id", "source", "external_id"), None, (),
    ),
    ("fetch_runs", "fetch_runs_cycle_slot_unique"): (
        "u", ("collection_cycle_id", "provider", "query_key"), None, (),
    ),
    ("fetch_run_items", "fetch_run_items_run_raw_unique"): (
        "u", ("fetch_run_id", "raw_content_id"), None, (),
    ),
    ("collection_cycle_slots", "collection_cycle_slots_cycle_fk"): (
        "f", ("collection_cycle_id",), "collection_cycles",
        ("collection_cycle_id",),
    ),
    ("fetch_runs", "fetch_runs_collection_cycle_fk"): (
        "f", ("collection_cycle_id",), "collection_cycles",
        ("collection_cycle_id",),
    ),
    ("fetch_run_items", "fetch_run_items_run_fk"): (
        "f", ("fetch_run_id",), "fetch_runs", ("fetch_run_id",),
    ),
    ("fetch_run_items", "fetch_run_items_media_fk"): (
        "f", ("source", "external_id"), "media_posts",
        ("source", "external_id"),
    ),
    ("fetch_runs", "fetch_runs_terminal_receipt_coherence"): (
        "c", None, None, (),
    ),
    ("fetch_runs", "fetch_runs_formal_eligible_content_lineage"): (
        "c", None, None, (),
    ),
    ("fetch_runs", "fetch_runs_server_observation_shape"): (
        "c", None, None, (),
    ),
    ("collection_cycles", "collection_cycles_terminal_shape"): (
        "c", None, None, (),
    ),
    ("collection_cycles", "collection_cycles_server_observation_shape"): (
        "c", None, None, (),
    ),
    ("collection_cycle_slots", "collection_cycle_slots_fields_valid"): (
        "c", None, None, (),
    ),
}
_COLLECTOR_NOT_VALID_CONSTRAINTS = frozenset({
    ("fetch_runs", "fetch_runs_terminal_receipt_coherence"),
    ("fetch_runs", "fetch_runs_formal_eligible_content_lineage"),
})
_COLLECTOR_CHECK_CONSTRAINT_HASHES = {
    ("collection_cycles", "collection_cycles_server_observation_shape"):
        frozenset({
            # SQLAlchemy-created unbounded VARCHAR columns.
            "10edb2266b9cb3fd0b95b9b3c65047d6a7f079714cb3ba1e9c8633f78f28612d",
            # Migration-created TEXT columns. PostgreSQL renders otherwise
            # identical string casts differently for the two base types.
            "5a7d186cbedb49381bbd640248bc8995ba879b17b3272fc16c10f73b381f5cb5",
        }),
    ("collection_cycles", "collection_cycles_terminal_shape"):
        frozenset({
            "a10c6d5b9ab0c2bd5a0049d01d99b8196d3180e843b8786fd6d8a63276aeec0f",
            "5f7ed45574b1478a90542be46737165e889ee1b26d5a71fc06982d93b338ef2d",
        }),
    ("collection_cycle_slots", "collection_cycle_slots_fields_valid"):
        frozenset({
            "a9539e59e23a965d7e4cd7766543a8c65a243b1b3df19c86b5f20e35464d681b",
            "c5bf085bba9e3cabf3c608711a145d626f03583a40e2fc95b53a5dd88eff429c",
        }),
    ("fetch_runs", "fetch_runs_formal_eligible_content_lineage"):
        frozenset({
            "cce57858327c1a555793cb56a548abe914cd2fb7085b367e7f84178a3e4bfb14",
        }),
    ("fetch_runs", "fetch_runs_server_observation_shape"):
        frozenset({
            "d4a50f6846927101030e26dd4e4dc339245b127356a7dd4043d0ca0fc3d32d5e",
            "6888a83094963c822b6eaaae750a7dc442a5ab1292f8b74e9cf93798d1e1c2a1",
        }),
    ("fetch_runs", "fetch_runs_terminal_receipt_coherence"):
        frozenset({
            "fec7f88bbbacf42f911e29a97640b6c19d5110a30fd151671074fb66035ecd98",
        }),
}

# Exact built-in PostgreSQL OIDs are stable catalog identifiers. Matching OIDs
# (rather than rendered names or coercible SQL types) rejects domains and custom
# types. TEXT and unbounded VARCHAR are one semantic family because the
# historical migrations and fresh SQLAlchemy schema use those representations
# interchangeably. Bounded VARCHAR is rejected by its nonnegative typmod.
_COLLECTOR_POSTGRES_TYPE_FAMILIES = {
    "unbounded_text": frozenset({(25, -1), (1043, -1)}),
    "float8": frozenset({(701, -1)}),
    "int4": frozenset({(23, -1)}),
    "bool": frozenset({(16, -1)}),
}


def _collector_postgres_type_family(column_type) -> str:
    """Map a trusted SQLAlchemy model type to its PostgreSQL type family."""
    visit_name = getattr(column_type, "__visit_name__", None)
    if visit_name in {"string", "text"}:
        if getattr(column_type, "length", None) is not None:
            raise ValueError("collector string columns must be unbounded")
        return "unbounded_text"
    family = {
        "double": "float8",
        "integer": "int4",
        "boolean": "bool",
    }.get(visit_name)
    if family is None:
        raise ValueError("unsupported collector PostgreSQL column type")
    return family


def _collector_postgres_column_contract_valid(column, actual: dict) -> bool:
    """Authenticate one live column against the trusted collector model."""
    family = _collector_postgres_type_family(column.type)
    expected_types = _COLLECTOR_POSTGRES_TYPE_FAMILIES[family]
    return (
        (int(actual["type_oid"]), int(actual["type_modifier"]))
        in expected_types
        and bool(actual["default_collation"])
        and bool(actual["not_null"]) == (not bool(column.nullable))
        and column.server_default is None
        and not bool(actual["has_default"])
        and actual["identity_kind"] == ""
        and actual["generated_kind"] == ""
    )


def _safe_exception_kind(exc: BaseException) -> str:
    kind = type(exc).__name__
    return kind if kind.isidentifier() and len(kind) <= 64 else "Exception"


_POSTGRES_TRANSACTION_SETTINGS = (
    "SET LOCAL lock_timeout=5000",
    "SET LOCAL statement_timeout=60000",
    "SET LOCAL idle_in_transaction_session_timeout=60000",
    "SET LOCAL search_path=pg_catalog,public",
)
_COLLECTOR_PREFLIGHT_FAILURE_TYPES = frozenset({
    "ContractMismatch",
    "DataError",
    "DatabaseError",
    "Exception",
    "ImportError",
    "IntegrityError",
    "InterfaceError",
    "InternalError",
    "ModuleNotFoundError",
    "NotSupportedError",
    "OperationalError",
    "ProgrammingError",
    "RuntimeError",
    "TimeoutError",
    "ValueError",
})
_COLLECTOR_PREFLIGHT_FAILURE_STAGES = frozenset({
    "primary_connection",
    "primary_contract",
    "direct_resolution",
    "session_affinity",
    "advisory_lock",
})


def _set_postgres_transaction_settings(connection) -> None:
    """Apply bounded, schema-pinned settings to the current transaction.

    Fly MPG uses PgBouncer transaction pooling and rejects libpq's ``options``
    startup parameter. ``SET LOCAL`` works through that pool, is applied on
    every SQLAlchemy transaction, and resets automatically at transaction end.
    """
    for statement in _POSTGRES_TRANSACTION_SETTINGS:
        connection.exec_driver_sql(statement)


def _install_postgres_transaction_settings(engine) -> None:
    from sqlalchemy import event

    event.listen(engine, "begin", _set_postgres_transaction_settings)


def _collector_preflight_failure_type(exc: BaseException) -> str:
    kind = _safe_exception_kind(exc)
    return (
        kind
        if kind in _COLLECTOR_PREFLIGHT_FAILURE_TYPES
        else "Exception"
    )


def _collector_preflight_contract_failure_stage(report: dict) -> str:
    if not report["connected"]:
        return "primary_connection"
    primary_contract_fields = (
        "database_clock_valid",
        "search_path_valid",
        "relation_resolution_valid",
        "tables_selectable",
        "column_contracts_valid",
        "privileges_valid",
        "role_attributes_valid",
        "integrity_triggers_valid",
        "function_contracts_valid",
        "constraints_valid",
        "indexes_valid",
        "cycle_parent_lock_authority_valid",
    )
    if not all(report[field] for field in primary_contract_fields):
        return "primary_contract"
    if not report["direct_endpoint_resolved"]:
        return "direct_resolution"
    if not report["session_affinity_valid"]:
        return "session_affinity"
    return "advisory_lock"


def _postgres_connect_args(*, read_only: bool = False) -> dict:
    args = {
        # Transaction-pooled PgBouncer can hand a later transaction to a
        # backend where psycopg's automatically named prepared statement does
        # not exist (or where the same generated name already exists). Keep
        # ordinary pooled traffic on the unnamed protocol path.
        "prepare_threshold": None,
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        "tcp_user_timeout": 30000,
    }
    if read_only:
        # Only direct, session-affine engines use startup options. The ordinary
        # engine can point at PgBouncer and receives its safeguards from the
        # transaction-begin hook instead.
        args["options"] = (
            "-c lock_timeout=5000 "
            "-c statement_timeout=60000 "
            "-c idle_in_transaction_session_timeout=60000 "
            "-c search_path=pg_catalog,public "
            "-c default_transaction_read_only=on"
        )
    return args


def _advisory_lock_is_held_statement():
    from sqlalchemy import text

    return text(
        "SELECT pg_catalog.pg_backend_pid() AS backend_pid, "
        "EXISTS (SELECT 1 FROM pg_catalog.pg_locks AS held "
        "WHERE held.locktype = 'advisory' AND held.granted "
        "AND held.pid = pg_catalog.pg_backend_pid() "
        "AND held.objsubid = 1 "
        "AND held.classid::BIGINT * 4294967296 + held.objid::BIGINT = :lock_id) "
        "AS lock_held"
    )


class _PostgresCollectorLease:
    """A monitored session-level advisory lock on a dedicated direct engine."""

    def __init__(
        self,
        connection,
        engine,
        lock_id: int,
        backend_pid: int,
        *,
        heartbeat_interval_seconds: float,
        on_loss=None,
    ):
        self._connection = connection
        self._engine = engine
        self._lock_id = lock_id
        self._backend_pid = backend_pid
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._on_loss = on_loss
        self._io_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._closed = False
        self._failure_type: str | None = None
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="collector-lease-heartbeat",
            daemon=True,
        )
        self._thread.start()

    @property
    def is_held(self) -> bool:
        with self._state_lock:
            return not self._closed and not self._lost.is_set()

    @property
    def failure_type(self) -> str | None:
        with self._state_lock:
            return self._failure_type

    def wait_until_lost(self, timeout: float | None = None) -> bool:
        return self._lost.wait(timeout)

    def assert_held(self) -> None:
        if not self.is_held:
            raise RuntimeError("collector singleton lease is no longer held")

    def _mark_lost(self, failure_type: str) -> None:
        callback = None
        with self._state_lock:
            if self._closed or self._lost.is_set():
                return
            self._failure_type = (
                failure_type
                if failure_type.isidentifier() and len(failure_type) <= 64
                else "Exception"
            )
            self._lost.set()
            callback = self._on_loss
        if callback is not None:
            try:
                callback(self._failure_type)
            except Exception as exc:  # noqa: BLE001 - callback cannot kill monitor
                logger.error(
                    "Collector lease loss callback failed (%s)",
                    _safe_exception_kind(exc),
                )

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_interval_seconds):
            try:
                with self._io_lock:
                    connection = self._connection
                    if connection is None:
                        return
                    row = connection.execute(
                        _advisory_lock_is_held_statement(),
                        {"lock_id": self._lock_id},
                    ).mappings().one()
                    connection.commit()
                if (
                    int(row["backend_pid"]) != self._backend_pid
                    or not bool(row["lock_held"])
                ):
                    self._mark_lost("CollectorLeaseOwnershipLost")
                    return
            except Exception as exc:  # noqa: BLE001 - convert to sanitized state
                self._mark_lost(_safe_exception_kind(exc))
                return

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=5.0)

        from sqlalchemy import text

        with self._io_lock:
            connection, self._connection = self._connection, None
            engine, self._engine = self._engine, None
            if connection is not None:
                try:
                    if not self._lost.is_set():
                        unlocked = bool(connection.execute(
                            text("SELECT pg_catalog.pg_advisory_unlock(:lock_id)"),
                            {"lock_id": self._lock_id},
                        ).scalar_one())
                        connection.commit()
                        if not unlocked:
                            logger.warning(
                                "Collector singleton lease was absent during cleanup"
                            )
                except Exception as exc:  # noqa: BLE001 - teardown is best effort
                    logger.warning(
                        "Could not release collector singleton lease (%s)",
                        _safe_exception_kind(exc),
                    )
                finally:
                    try:
                        connection.close()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Could not close collector lease connection (%s)",
                            _safe_exception_kind(exc),
                        )
            if engine is not None:
                try:
                    engine.dispose()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Could not dispose collector lease engine (%s)",
                        _safe_exception_kind(exc),
                    )


def _validated_collection_cycle_id(value: str | None) -> str | None:
    if value is not None and (
        not isinstance(value, str) or _COLLECTION_CYCLE_ID.fullmatch(value) is None
    ):
        raise ValueError("collection cycle ID must be a canonical cycle ID")
    return value


def _collector_build_id(metadata: dict | None = None) -> str:
    """Return the immutable collector build identity stored on a new receipt."""
    value = (metadata or {}).get("collector_build_id")
    if value is None:
        # Lazy import keeps the storage module independent from protocol import
        # order while preserving the production image-ref/source-tree fallback.
        from tradingagents.research_protocol import build_identity

        value = build_identity()
    if not isinstance(value, str) or _COLLECTOR_BUILD_ID.fullmatch(value) is None:
        raise ValueError("collector build identity must be a canonical build ID")
    return value


def _sqlite_server_observed_utc(conn: sqlite3.Connection) -> float:
    """Read SQLite's clock inside the transaction that owns the observation."""
    value = conn.execute("SELECT server_observed_utc()").fetchone()[0]
    observed = float(value)
    if not math.isfinite(observed):
        raise RuntimeError("database returned a non-finite observation time")
    return observed


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _content_addressed_json_id(prefix: str, value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:24]}"


def _content_addressed_json_text_id(prefix: str, value: str) -> str | None:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return _content_addressed_json_id(prefix, payload)


def _validated_cycle_text(value: object, label: str, *, max_bytes: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"collection cycle {label} must be a non-empty string")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"collection cycle {label} is too long")
    return value


def _cycle_slot_payloads(slots: list[tuple[str, str]] | None) -> list[dict[str, str]]:
    normalized = sorted(_normalize_query_slots(slots))
    if len(normalized) > 100:
        raise ValueError("collection cycles support at most 100 query slots")
    payloads = []
    for provider, query_key in normalized:
        _validated_cycle_text(provider, "slot provider", max_bytes=64)
        _validated_cycle_text(query_key, "slot query key", max_bytes=2048)
        payloads.append({"provider": provider, "query_key": query_key})
    return payloads


def collection_cycle_spec(
    *, cycle_kind: str, period_key: str, protocol_id: str,
    collector_semantics_id: str, expected_static_slots: list[tuple[str, str]],
    max_dynamic_slots: int,
) -> dict:
    """Build the immutable content-addressed identity known before collection."""
    cycle_kind = _validated_cycle_text(cycle_kind, "kind", max_bytes=64)
    if _COLLECTION_CYCLE_KIND.fullmatch(cycle_kind) is None:
        raise ValueError("collection cycle kind must be a lowercase slug")
    period_key = _validated_cycle_text(period_key, "period key", max_bytes=128)
    protocol_id = _validated_cycle_text(protocol_id, "protocol ID", max_bytes=128)
    collector_semantics_id = _validated_cycle_text(
        collector_semantics_id, "collector semantics ID", max_bytes=128
    )
    if (
        isinstance(max_dynamic_slots, bool)
        or not isinstance(max_dynamic_slots, int)
        or not 0 <= max_dynamic_slots <= 100
    ):
        raise ValueError("collection cycle dynamic-slot cap must be between 0 and 100")
    static_slots = _cycle_slot_payloads(expected_static_slots)
    if not static_slots:
        raise ValueError("collection cycles require at least one static query slot")
    identity = {
        "schema_version": 1,
        "cycle_kind": cycle_kind,
        "period_key": period_key,
        "protocol_id": protocol_id,
        "collector_semantics_id": collector_semantics_id,
        "expected_static_slots": static_slots,
        "max_dynamic_slots": max_dynamic_slots,
    }
    return {
        "collection_cycle_id": _content_addressed_json_id("cycle_", identity),
        "identity": identity,
    }


def _validated_collection_cycle_spec(spec: dict) -> tuple[str, dict, str]:
    if not isinstance(spec, dict) or set(spec) != {"collection_cycle_id", "identity"}:
        raise ValueError("collection cycle spec has an invalid shape")
    identity = spec.get("identity")
    if not isinstance(identity, dict) or set(identity) != {
        "schema_version", "cycle_kind", "period_key", "protocol_id",
        "collector_semantics_id", "expected_static_slots", "max_dynamic_slots",
    }:
        raise ValueError("collection cycle identity has an invalid shape")
    static = identity.get("expected_static_slots")
    if not isinstance(static, list) or any(
        not isinstance(slot, dict) or set(slot) != {"provider", "query_key"}
        for slot in static
    ):
        raise ValueError("collection cycle static slots have an invalid shape")
    rebuilt = collection_cycle_spec(
        cycle_kind=identity.get("cycle_kind"),
        period_key=identity.get("period_key"),
        protocol_id=identity.get("protocol_id"),
        collector_semantics_id=identity.get("collector_semantics_id"),
        expected_static_slots=[
            (slot.get("provider"), slot.get("query_key")) for slot in static
        ],
        max_dynamic_slots=identity.get("max_dynamic_slots"),
    )
    if rebuilt != spec:
        raise ValueError("collection cycle spec is not canonical or content-addressed")
    return spec["collection_cycle_id"], identity, _canonical_json(identity)


def _finite_cycle_time(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"collection cycle {label} must be finite")
    return float(value)


def _normalized_manifest_numbers(value: object) -> object:
    """Match PostgreSQL JSONB's canonical rendering of integral doubles."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_normalized_manifest_numbers(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalized_manifest_numbers(item) for key, item in value.items()
        }
    return value


def _collection_cycle_manifest(
    cycle: dict, slots: list[dict], receipts: list[dict], completed_utc: float,
) -> tuple[str, str, str, dict]:
    """Derive the terminal manifest solely from stored slots and child receipts."""
    # Relational reads have no implicit order.  Canonicalize here so SQLite,
    # PostgreSQL, and the PostgreSQL lifecycle trigger derive byte-identical
    # manifests regardless of query-plan or insertion-order changes.
    slots = sorted(
        slots,
        key=lambda slot: (
            0 if slot.get("slot_kind") == "static" else 1,
            str(slot.get("provider")),
            str(slot.get("query_key")),
        ),
    )
    completed = _finite_cycle_time(completed_utc, "completion time")
    started = _finite_cycle_time(cycle.get("started_utc"), "start time")
    if completed < started:
        raise ValueError("collection cycle completion precedes its start")
    cycle_id = _validated_collection_cycle_id(cycle.get("collection_cycle_id"))
    identity_raw = cycle.get("identity_json")
    try:
        identity = json.loads(identity_raw) if isinstance(identity_raw, str) else identity_raw
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("collection cycle identity is malformed") from exc
    validated_id, validated_identity, _ = _validated_collection_cycle_spec({
        "collection_cycle_id": cycle_id,
        "identity": identity,
    })
    receipt_by_slot: dict[tuple[str, str], dict] = {}
    for receipt in receipts:
        key = (receipt.get("provider"), receipt.get("query_key"))
        if key in receipt_by_slot:
            raise ValueError("collection cycle has duplicate child fetch receipts")
        receipt_by_slot[key] = receipt
    expected_static = []
    expected_dynamic = []
    slot_receipts = []
    seen_slots: set[tuple[str, str]] = set()
    for slot in sorted(
        slots,
        key=lambda item: (
            0 if item.get("slot_kind") == "static" else 1,
            item.get("provider", ""), item.get("query_key", ""),
        ),
    ):
        if slot.get("collection_cycle_id") != validated_id:
            raise ValueError("collection cycle slot has the wrong parent")
        kind = slot.get("slot_kind")
        if kind not in {"static", "dynamic"}:
            raise ValueError("collection cycle slot kind is invalid")
        provider, query_key = _normalize_query_slots([
            (slot.get("provider"), slot.get("query_key"))
        ])[0]
        key = (provider, query_key)
        if key in seen_slots:
            raise ValueError("collection cycle query slots are duplicated")
        seen_slots.add(key)
        payload = {"provider": provider, "query_key": query_key}
        (expected_static if kind == "static" else expected_dynamic).append(payload)
        receipt = receipt_by_slot.pop(key, None)
        fetch_run_id = receipt.get("fetch_run_id") if receipt else None
        receipt_status = receipt.get("status") if receipt else "missing"
        if receipt_status not in {"running", "success", "empty", "failed", "missing"}:
            receipt_status = "invalid"
        raw_ids = receipt.get("raw_content_ids", []) if receipt else []
        if (
            not isinstance(raw_ids, list)
            or any(
                not isinstance(raw_id, str)
                or _FORMAL_RAW_CONTENT_ID.fullmatch(raw_id) is None
                for raw_id in raw_ids
            )
            or raw_ids != sorted(set(raw_ids))
        ):
            raise ValueError("collection cycle receipt raw-content lineage is invalid")
        slot_receipts.append({
            "slot_kind": kind,
            **payload,
            "fetch_run_id": fetch_run_id,
            "status": receipt_status,
            "item_count": receipt.get("item_count") if receipt else None,
            "raw_content_ids": raw_ids,
        })
    if receipt_by_slot:
        raise ValueError("collection cycle has undeclared child fetch receipts")
    if any(item["status"] == "running" for item in slot_receipts):
        raise ValueError(
            "collection cycle cannot finish while a child receipt is running"
        )
    if expected_static != validated_identity["expected_static_slots"]:
        raise ValueError("collection cycle static slots differ from its identity")
    if len(expected_dynamic) > validated_identity["max_dynamic_slots"]:
        raise ValueError("collection cycle exceeded its dynamic-slot cap")
    status = (
        "complete"
        if all(item["status"] in {"success", "empty"} for item in slot_receipts)
        else "incomplete"
    )
    server_started_raw = cycle.get("server_started_utc")
    server_terminal_raw = cycle.get("server_terminal_utc")
    collector_build_id = cycle.get("collector_build_id")
    observed_fields = (
        server_started_raw, server_terminal_raw, collector_build_id
    )
    legacy_manifest = all(value is None for value in observed_fields)
    if not legacy_manifest:
        server_started = _finite_cycle_time(
            server_started_raw, "server start observation"
        )
        server_terminal = _finite_cycle_time(
            server_terminal_raw, "server terminal observation"
        )
        if server_terminal < server_started:
            raise ValueError(
                "collection cycle server terminal observation precedes its start"
            )
        if not isinstance(collector_build_id, str) \
                or _COLLECTOR_BUILD_ID.fullmatch(collector_build_id) is None:
            raise ValueError("collection cycle collector build identity is invalid")
    manifest = {
        "schema_version": 1 if legacy_manifest else 2,
        "collection_cycle_id": validated_id,
        "cycle_kind": cycle.get("cycle_kind"),
        "period_key": cycle.get("period_key"),
        "protocol_id": cycle.get("protocol_id"),
        "collector_semantics_id": cycle.get("collector_semantics_id"),
        "started_utc": started,
        "completed_utc": completed,
        "status": status,
        "expected_static_slots": expected_static,
        "expected_dynamic_slots": expected_dynamic,
        "slot_receipts": slot_receipts,
    }
    if not legacy_manifest:
        manifest.update({
            "server_started_utc": server_started,
            "server_terminal_utc": server_terminal,
            "collector_build_id": collector_build_id,
        })
        manifest = _normalized_manifest_numbers(manifest)
    manifest_json = _canonical_json(manifest)
    manifest_id = _content_addressed_json_id("cycle_manifest_", manifest)
    return status, manifest_id, manifest_json, manifest


def _cycle_receipts_with_lineage(
    receipts: list[dict], item_rows: list[dict],
) -> list[dict]:
    """Attach the exact sorted raw-content projection to each child receipt."""
    by_run: dict[str, list[str]] = {}
    receipt_ids = {receipt.get("fetch_run_id") for receipt in receipts}
    for item in item_rows:
        run_id = item.get("fetch_run_id")
        raw_id = item.get("raw_content_id")
        if run_id not in receipt_ids:
            raise ValueError("collection cycle lineage has an unknown child receipt")
        if not isinstance(raw_id, str) or _FORMAL_RAW_CONTENT_ID.fullmatch(raw_id) is None:
            raise ValueError("collection cycle lineage has an invalid raw-content ID")
        by_run.setdefault(run_id, []).append(raw_id)
    result = []
    for receipt in receipts:
        raw_ids = sorted(by_run.get(receipt.get("fetch_run_id"), []))
        if raw_ids != sorted(set(raw_ids)):
            raise ValueError("collection cycle raw-content lineage is duplicated")
        result.append({**receipt, "raw_content_ids": raw_ids})
    return result


def _verified_cycle_item_rows(rows: list[dict]) -> list[dict]:
    """Recompute each persisted raw ID from its exact point-in-time media row."""
    verified = []
    for item in rows:
        try:
            metadata = (
                json.loads(item["metadata_json"])
                if item.get("metadata_json") is not None else {}
            )
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("collection cycle item metadata is malformed") from exc
        stored = {
            column: item.get(f"stored_{column}") for column in COLUMNS
        }
        if metadata:
            stored["metadata"] = metadata
        if raw_content_id(stored) != item.get("raw_content_id"):
            raise ValueError("collection cycle raw-content replay detected tampering")
        verified.append({
            "fetch_run_id": item.get("fetch_run_id"),
            "raw_content_id": item.get("raw_content_id"),
        })
    return verified


def _attach_collection_cycle_payloads(cycle: dict) -> dict:
    """Decode and verify persisted content addresses without trusting the row."""
    try:
        identity = json.loads(cycle.get("identity_json"))
    except (TypeError, json.JSONDecodeError):
        identity = None
    cycle["identity"] = identity
    cycle["identity_valid"] = False
    try:
        cycle_id, _, _ = _validated_collection_cycle_spec({
            "collection_cycle_id": cycle.get("collection_cycle_id"),
            "identity": identity,
        })
        cycle["identity_valid"] = cycle_id == cycle.get("collection_cycle_id")
    except ValueError:
        pass
    raw_manifest = cycle.get("manifest_json")
    try:
        manifest = json.loads(raw_manifest) if raw_manifest is not None else None
    except (TypeError, json.JSONDecodeError):
        manifest = None
    cycle["manifest"] = manifest
    cycle["manifest_valid"] = bool(
        isinstance(manifest, dict)
        and cycle.get("manifest_id") == _content_addressed_json_id(
            "cycle_manifest_", manifest
        )
        and cycle.get("status") == manifest.get("status")
        and cycle.get("collection_cycle_id") == manifest.get("collection_cycle_id")
    )
    return cycle


def _verify_collection_cycle_relations(
    cycle: dict, slots: list[dict], receipts: list[dict],
) -> dict:
    """Fail closed if a terminal row no longer matches its child relations."""
    attached = _attach_collection_cycle_payloads(cycle)
    if attached.get("status") not in {"complete", "incomplete"}:
        return attached
    try:
        status, manifest_id, manifest_json, manifest = _collection_cycle_manifest(
            attached, slots, receipts, attached.get("completed_utc")
        )
    except (TypeError, ValueError):
        attached["manifest_valid"] = False
        return attached
    attached["manifest_valid"] = bool(
        attached.get("manifest_valid")
        and attached.get("identity_valid")
        and attached.get("status") == status
        and attached.get("manifest_id") == manifest_id
        and attached.get("manifest_json") == manifest_json
        and attached.get("manifest") == manifest
    )
    return attached


def _encoded_formal_evidence_ids(
    count: int | None, evidence_ids: list[str] | None, *, item_count: int
) -> str | None:
    """Validate the exact unique eligible-ID lineage stored on one receipt."""
    if count is None and evidence_ids is None:
        return None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("formal eligible item count must be a non-negative integer")
    if not isinstance(evidence_ids, list) or any(
        not isinstance(value, str) or _FORMAL_EVIDENCE_ID.fullmatch(value) is None
        for value in evidence_ids
    ):
        raise ValueError("formal eligible evidence IDs must be canonical evidence IDs")
    if evidence_ids != sorted(set(evidence_ids)):
        raise ValueError("formal eligible evidence IDs must be sorted and unique")
    if count != len(evidence_ids) or count > item_count:
        raise ValueError("formal eligible item count/list is inconsistent")
    return json.dumps(evidence_ids, separators=(",", ":"))


def _attach_formal_evidence_ids(run: dict) -> dict:
    raw = run.get("formal_eligible_evidence_ids_json")
    if raw is None:
        run["formal_eligible_evidence_ids"] = None
        run["formal_eligible_lineage"] = None
        return run
    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        decoded = None
    run["formal_eligible_evidence_ids"] = decoded
    raw_lineage = run.get("formal_eligible_lineage_json")
    if raw_lineage is None:
        run["formal_eligible_lineage"] = None
        return run
    try:
        lineage = json.loads(raw_lineage) if isinstance(raw_lineage, str) else raw_lineage
    except (TypeError, json.JSONDecodeError):
        lineage = None
    run["formal_eligible_lineage"] = lineage
    return run


def _verified_cycle_formal_lineage(
    receipts: list[dict], items: list[dict],
) -> list[dict]:
    """Replay the exact formally eligible child projection for one provider."""
    items_by_run: dict[str, list[dict]] = {}
    receipt_ids = {receipt.get("fetch_run_id") for receipt in receipts}
    for item in items:
        fetch_run_id = item.get("fetch_run_id")
        if fetch_run_id not in receipt_ids:
            raise ValueError("formal cycle lineage has an unknown child receipt")
        if item.get("evidence_id") != evidence_id(item):
            raise ValueError("formal cycle evidence identity replay detected tampering")
        if item.get("formal_eligible") == 1:
            payload = {
                "evidence_id": item.get("evidence_id"),
                "raw_content_id": item.get("raw_content_id"),
            }
            if (
                _FORMAL_EVIDENCE_ID.fullmatch(str(payload["evidence_id"])) is None
                or _FORMAL_RAW_CONTENT_ID.fullmatch(str(payload["raw_content_id"]))
                is None
            ):
                raise ValueError("formal cycle item lineage is malformed")
            items_by_run.setdefault(str(fetch_run_id), []).append(payload)
    lineage: list[dict] = []
    for raw_receipt in receipts:
        receipt = _attach_formal_evidence_ids(dict(raw_receipt))
        run_id = receipt.get("fetch_run_id")
        actual = sorted(
            items_by_run.get(str(run_id), []),
            key=lambda item: (item["evidence_id"], item["raw_content_id"]),
        )
        if actual != receipt.get("formal_eligible_lineage"):
            raise ValueError("formal cycle receipt projection differs from item lineage")
        if receipt.get("formal_eligible_item_count") != len(actual):
            raise ValueError("formal cycle receipt count differs from item lineage")
        lineage.extend({"fetch_run_id": run_id, **item} for item in actual)
    return sorted(
        lineage,
        key=lambda item: (
            item["evidence_id"], item["raw_content_id"], item["fetch_run_id"],
        ),
    )


def _encoded_formal_lineage(
    count: int | None,
    evidence_ids: list[str] | None,
    lineage: list[dict] | None,
    *,
    item_count: int,
) -> str | None:
    """Validate canonical sorted unique content-bound formal lineage."""
    if count is None and evidence_ids is None and lineage is None:
        return None
    _encoded_formal_evidence_ids(count, evidence_ids, item_count=item_count)
    if not isinstance(lineage, list):
        raise ValueError("formal eligible lineage must be a list")
    normalized: list[dict[str, str]] = []
    for item in lineage:
        if not isinstance(item, dict) or set(item) != {"evidence_id", "raw_content_id"}:
            raise ValueError("formal eligible lineage entries have an invalid shape")
        evidence = item.get("evidence_id")
        raw = item.get("raw_content_id")
        if not isinstance(evidence, str) or _FORMAL_EVIDENCE_ID.fullmatch(evidence) is None:
            raise ValueError("formal eligible lineage has an invalid evidence ID")
        if not isinstance(raw, str) or _FORMAL_RAW_CONTENT_ID.fullmatch(raw) is None:
            raise ValueError("formal eligible lineage has an invalid raw-content ID")
        normalized.append({"evidence_id": evidence, "raw_content_id": raw})
    canonical = sorted(
        normalized, key=lambda item: (item["evidence_id"], item["raw_content_id"])
    )
    if normalized != canonical or len({
        (item["evidence_id"], item["raw_content_id"]) for item in normalized
    }) != len(normalized):
        raise ValueError("formal eligible lineage must be sorted and unique")
    if [item["evidence_id"] for item in normalized] != evidence_ids:
        raise ValueError("formal eligible lineage does not match eligible evidence IDs")
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _build_fetch_item_lineage(
    fetch_run_id: str,
    provider: str,
    rows: list[dict],
    received_utc: float,
    formal_eligible_evidence_ids: list[str] | None,
) -> tuple[list[dict], list[dict] | None]:
    """Build exact per-response lineage and the formal eligible projection."""
    eligible = None if formal_eligible_evidence_ids is None else set(
        formal_eligible_evidence_ids
    )
    items: list[dict] = []
    identities: set[tuple[str, str]] = set()
    observed_evidence_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("source") != provider:
            raise ValueError("fetch item source does not match its receipt provider")
        external_id = row.get("external_id")
        if not isinstance(external_id, str) or not external_id:
            raise ValueError("fetch items require a stable external identity")
        identity = (provider, external_id)
        if identity in identities:
            raise ValueError("fetch response contains a duplicate item identity")
        identities.add(identity)
        fetched = row.get("fetched_utc")
        if (
            isinstance(fetched, bool)
            or not isinstance(fetched, (int, float))
            or not math.isfinite(float(fetched))
            or float(fetched) != float(received_utc)
        ):
            raise ValueError("fetch item receipt time must equal the response receipt time")
        evidence = evidence_id(row)
        observed_evidence_ids.add(evidence)
        items.append({
            "fetch_run_id": fetch_run_id,
            "source": provider,
            "external_id": external_id,
            "raw_content_id": raw_content_id(row),
            "evidence_id": evidence,
            "observed_utc": float(received_utc),
            "formal_eligible": eligible is not None and evidence in eligible,
        })
    if eligible is not None and not eligible.issubset(observed_evidence_ids):
        raise ValueError("formal eligible evidence IDs are not present in the fetch response")
    formal_lineage = None if eligible is None else sorted(
        [
            {"evidence_id": item["evidence_id"], "raw_content_id": item["raw_content_id"]}
            for item in items
            if item["formal_eligible"]
        ],
        key=lambda item: (item["evidence_id"], item["raw_content_id"]),
    )
    return items, formal_lineage


def _media_rows_conflict(existing: dict, observed: dict) -> bool:
    """Detect revisions that would otherwise synthesize a hybrid formal row."""
    source = observed.get("source")
    if source not in _FORMAL_MEDIA_SOURCES or existing.get("source") != source:
        return False
    if any(existing.get(field) != observed.get(field) for field in _IMMUTABLE_MEDIA_FIELDS):
        return True
    existing_metadata = (
        existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
    )
    observed_metadata = (
        observed.get("metadata") if isinstance(observed.get("metadata"), dict) else {}
    )
    if source in {"globalnews", "trendnews"}:
        if existing.get("author") != observed.get("author"):
            return True
        return any(
            existing_metadata.get(field) is not None
            and observed_metadata.get(field) is not None
            and existing_metadata[field] != observed_metadata[field]
            for field in _IMMUTABLE_NEWS_PROVENANCE_FIELDS
        )
    existing_author_id = existing_metadata.get("author_id")
    observed_author_id = observed_metadata.get("author_id")
    if existing_author_id is not None and observed_author_id is not None:
        return existing_author_id != observed_author_id
    return existing.get("author") != observed.get("author")


def _validate_batch_media_coherence(rows: list[dict]) -> list[dict]:
    """Return one representative per identity or reject conflicting duplicates."""
    identities: dict[tuple[object, object], dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("media rows must be mappings")
        identity = (row.get("source"), row.get("external_id"))
        prior = identities.get(identity)
        if prior is not None and _media_rows_conflict(prior, row):
            raise ValueError("formal media identity has conflicting provenance")
        identities.setdefault(identity, row)
    return list(identities.values())


def _validate_fetch_completion(
    *, started_utc: object, status: object, received_utc: object,
    completed_utc: object, item_count: object, inserted_count: object,
    error: object, cost_units: object, cursor_after: object,
) -> None:
    """Reject internally impossible terminal receipts before persistence."""
    if status not in {"success", "empty", "failed"}:
        raise ValueError("fetch completion status must be a terminal status")
    times = (started_utc, received_utc, completed_utc)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in times
    ) or not float(started_utc) <= float(received_utc) <= float(completed_utc):
        raise ValueError("fetch receipt timestamps must be finite and monotonic")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (item_count, inserted_count)
    ) or int(inserted_count) > int(item_count):
        raise ValueError("fetch receipt item counts are inconsistent")
    if (
        isinstance(cost_units, bool)
        or not isinstance(cost_units, (int, float))
        or not math.isfinite(float(cost_units))
        or float(cost_units) < 0.0
    ):
        raise ValueError("fetch receipt cost units must be finite and non-negative")
    if cursor_after is not None and (
        isinstance(cursor_after, bool)
        or not isinstance(cursor_after, (int, float))
        or not math.isfinite(float(cursor_after))
        or not float(started_utc) <= float(cursor_after) <= float(completed_utc)
    ):
        raise ValueError("fetch receipt cursor must fall within the fetch interval")
    if status == "success" and (
        item_count < 1 or error is not None
    ):
        raise ValueError("successful fetch receipts require items and no error")
    if status == "empty" and (
        item_count != 0 or inserted_count != 0 or error is not None
    ):
        raise ValueError("empty fetch receipts require zero counts and no error")
    if status == "failed" and (item_count != 0 or inserted_count != 0):
        raise ValueError("failed fetch receipts require zero item counts")


def _terminal_receipt_reason(run: dict) -> str | None:
    """Return a stable reason if a purported healthy receipt is incoherent."""
    try:
        _validate_fetch_completion(
            started_utc=run.get("started_utc"),
            status=run.get("status"),
            received_utc=run.get("received_utc"),
            completed_utc=run.get("completed_utc"),
            item_count=run.get("item_count"),
            inserted_count=run.get("inserted_count"),
            error=run.get("error"),
            cost_units=run.get("cost_units"),
            cursor_after=run.get("cursor_after"),
        )
    except ValueError:
        return "invalid_receipt"
    return None


class _MetaBudgetExceeded(Exception):
    """Internal transaction sentinel used to roll back every counter increment."""


def _validated_meta_budget(
    limits: dict[str, float], amount: float
) -> tuple[dict[str, float], float]:
    if not limits:
        raise ValueError("at least one persistent budget limit is required")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("persistent budget amount must be numeric")
    amount = float(amount)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("persistent budget amount must be finite and positive")
    normalized = {}
    for key, limit in limits.items():
        if not isinstance(key, str) or not key:
            raise ValueError("persistent budget keys must be non-empty strings")
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            raise ValueError("persistent budget limits must be numeric")
        value = float(limit)
        if not math.isfinite(value) or value < 0:
            raise ValueError("persistent budget limits must be finite and non-negative")
        normalized[key] = value
    return normalized, amount

QuerySlot = tuple[str, str]


def _normalize_query_slots(expected_query_slots: list[QuerySlot] | None) -> list[QuerySlot]:
    """Validate and stably deduplicate exact ``(provider, query_key)`` slots."""
    normalized: list[QuerySlot] = []
    seen: set[QuerySlot] = set()
    for slot in expected_query_slots or []:
        if not isinstance(slot, (list, tuple)) or len(slot) != 2:
            raise ValueError("expected query slots must be (provider, query_key) pairs")
        provider, query_key = slot
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("query-slot provider must be a non-empty string")
        if not isinstance(query_key, str) or not query_key.strip():
            raise ValueError("query-slot key must be a non-empty string")
        pair = (provider, query_key)
        if pair not in seen:
            normalized.append(pair)
            seen.add(pair)
    return normalized


def _coverage_reason(
    run: dict | None, cutoff_utc: float, max_age_seconds: float,
    *, allow_empty: bool = False,
) -> str | None:
    """Return a fixed, alert-safe reason when a receipt cannot prove coverage."""
    if run is None:
        return "not_run"
    status = run.get("status")
    if status != "success" and not (allow_empty and status == "empty"):
        return status if status in {"empty", "failed", "running"} else "unhealthy"
    incoherent = _terminal_receipt_reason(run)
    if incoherent is not None:
        return incoherent
    server_terminal = run.get("server_terminal_utc")
    if isinstance(server_terminal, bool) or not isinstance(
        server_terminal, (int, float)
    ) or not math.isfinite(float(server_terminal)):
        return "untrusted_time"
    server_terminal = float(server_terminal)
    server_started = run.get("server_started_utc")
    if isinstance(server_started, bool) or not isinstance(
        server_started, (int, float)
    ) or not math.isfinite(float(server_started)) \
            or float(server_started) > server_terminal:
        return "untrusted_time"
    collector_build_id = run.get("collector_build_id")
    if not isinstance(collector_build_id, str) \
            or _COLLECTOR_BUILD_ID.fullmatch(collector_build_id) is None:
        return "untrusted_build"
    if server_terminal > cutoff_utc:
        return "incomplete"
    if cutoff_utc - server_terminal > max_age_seconds:
        return "stale"
    return None


def _coverage_result(
    *, cutoff_utc: float, required_source_groups: list[list[str]],
    source_statuses: dict[str, dict | None], query_statuses: list[dict],
    max_age_seconds: float,
) -> dict:
    missing_groups = []
    for group in required_source_groups:
        healthy = [
            provider for provider in group
            if _coverage_reason(source_statuses.get(provider), cutoff_utc, max_age_seconds) is None
        ]
        if not healthy:
            missing_groups.append(group)

    slots = []
    missing_slots = []
    for status in query_statuses:
        reason = _coverage_reason(
            status["run"], cutoff_utc, max_age_seconds,
            allow_empty=status.get("allow_empty", False),
        )
        if reason is None and (
            status.get("require_eligible") or status.get("require_lineage")
        ):
            run = status.get("run") or {}
            eligible = run.get("formal_eligible_item_count")
            evidence_ids = run.get("formal_eligible_evidence_ids")
            lineage = run.get("formal_eligible_lineage")
            evidence_ids_shape_valid = isinstance(evidence_ids, list) and all(
                isinstance(value, str)
                and _FORMAL_EVIDENCE_ID.fullmatch(value) is not None
                for value in evidence_ids
            )
            lineage_shape_valid = isinstance(lineage, list) and all(
                isinstance(item, dict)
                and set(item) == {"evidence_id", "raw_content_id"}
                and isinstance(item.get("evidence_id"), str)
                and _FORMAL_EVIDENCE_ID.fullmatch(item["evidence_id"]) is not None
                and isinstance(item.get("raw_content_id"), str)
                and _FORMAL_RAW_CONTENT_ID.fullmatch(item["raw_content_id"]) is not None
                for item in lineage
            )
            canonical_lineage = (
                sorted(
                    lineage,
                    key=lambda item: (item["evidence_id"], item["raw_content_id"]),
                )
                if lineage_shape_valid else None
            )
            if (
                isinstance(eligible, bool)
                or not isinstance(eligible, int)
                or eligible < 0
                or not evidence_ids_shape_valid
                or evidence_ids != sorted(set(evidence_ids))
                or len(evidence_ids) != eligible
                or canonical_lineage is None
                or lineage != canonical_lineage
                or len({
                    (item.get("evidence_id"), item.get("raw_content_id"))
                    for item in lineage
                }) != len(lineage)
                or [item["evidence_id"] for item in lineage] != evidence_ids
            ):
                reason = "invalid_lineage"
            elif status.get("require_eligible") and eligible < 1:
                reason = "ineligible"
        slot = {**status, "healthy": reason is None, "reason": reason}
        slots.append(slot)
        if reason is not None:
            missing_slots.append({
                "provider": status["provider"],
                "query_key": status["query_key"],
                "reason": reason,
            })
    return {
        "complete": not missing_groups and not missing_slots,
        "sources": source_statuses,
        "missing_source_groups": missing_groups,
        "query_slots": slots,
        "missing_query_slots": missing_slots,
        "cutoff_utc": cutoff_utc,
    }


def _odds_asof_sql(theme_clause: str) -> str:
    """Latest snapshot per market with captured_utc <= :hi. Standard SQL
    (correlated subquery), so it runs unchanged on SQLite and Postgres."""
    return (
        f"SELECT {','.join(ODDS_COLUMNS)} FROM macro_odds o "
        "WHERE captured_utc <= :hi AND captured_utc = "
        "(SELECT MAX(captured_utc) FROM macro_odds o2 "
        " WHERE o2.market_id = o.market_id AND o2.captured_utc <= :hi) "
        f"{theme_clause} ORDER BY volume DESC"
    )


def _midnight_epoch(end: str) -> float:
    """``end`` at 00:00 UTC — the look-ahead-safe upper bound for an as-of read."""
    return datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


_DEFAULT_SQLITE_PATH = Path.home() / ".tradingagents" / "cache" / "media.db"


def _normalize_pg_url(url: str) -> str:
    """Rewrite Postgres URLs to the installed psycopg (v3) driver.

    Fly Managed Postgres / Heroku hand out ``postgres://…``, and a plain
    ``postgresql://…`` makes SQLAlchemy default to psycopg2 (which we don't
    install). Both become ``postgresql+psycopg://…`` so the connection string a
    provider gives you works unedited.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def open_store(url: str | None = None, *, auto_migrate: bool | None = None):
    """Open the media store named by ``url`` (or ``$MEDIA_DB_URL`` /
    ``$DATABASE_URL``, or the local default SQLite file). Bare paths and
    ``sqlite:///…`` URLs use the stdlib SQLite backend; any other scheme uses
    the SQLAlchemy backend. ``DATABASE_URL`` is read so a Fly Managed Postgres
    ``fly mpg attach`` (which sets it) works with no extra config. An explicit
    ``auto_migrate`` value overrides ``MEDIA_AUTO_MIGRATE`` for the SQLAlchemy
    backend so read-only diagnostics cannot accidentally run DDL.
    """
    import os

    url = (url or os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return SqliteMediaStore(_DEFAULT_SQLITE_PATH)
    if url.startswith("sqlite:///"):
        return SqliteMediaStore(Path(url[len("sqlite:///"):]))
    if "://" not in url:  # bare filesystem path
        return SqliteMediaStore(Path(url))
    return SqlAlchemyMediaStore(_normalize_pg_url(url), auto_migrate=auto_migrate)


def _window_bounds(end: str, days: int) -> tuple[float, float]:
    """[end - days, end] as UTC epoch seconds, with ``end`` at 00:00 UTC.

    A decision *made on* the trade date should not see that day's later intraday
    chatter, so the upper bound is midnight of ``end`` — look-ahead-safe.
    """
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (end_dt - timedelta(days=days)).timestamp(), end_dt.timestamp()


def _history_bounds(start: str, end: str) -> tuple[float, float]:
    """UTC bounds for an after-close decision on ``end``.

    The graph's market tools include the ``end`` session's closing bar, so a
    backtest decision is timestamped after that close and entered next session.
    Media published *and fetched* before the next UTC midnight is eligible.
    """
    lo = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    hi = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    return lo.timestamp(), hi.timestamp()


def _matches_requested_labels(
    row: dict,
    *,
    tickers: list[str] | None = None,
    ticker_prefixes: list[str] | None = None,
) -> bool:
    """Recheck requested associations after trusted receipt labels are attached."""
    if not tickers and not ticker_prefixes:
        return True
    labels = {
        str(label).upper()
        for label in row.get("labels", [])
        if isinstance(label, str) and label
    }
    exact = {ticker.upper() for ticker in (tickers or [])}
    prefixes = tuple(prefix.upper() for prefix in (ticker_prefixes or []))
    return bool(labels & exact) or any(
        label.startswith(prefix) for label in labels for prefix in prefixes
    )


class SqliteMediaStore:
    """Local SQLite backend (stdlib ``sqlite3``, no extra dependencies)."""

    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.create_function(
            "content_addressed_json_id", 2, _content_addressed_json_text_id,
            deterministic=True,
        )
        self.conn.create_function(
            "server_observed_utc", 0, lambda: time.time(), deterministic=False,
        )
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_posts (
                source TEXT NOT NULL, external_id TEXT NOT NULL, ticker TEXT NOT NULL,
                subreddit TEXT, author TEXT, sentiment TEXT, created_utc REAL,
                title TEXT, body TEXT, fetched_utc REAL NOT NULL,
                PRIMARY KEY (source, external_id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_labels (
                source TEXT NOT NULL, external_id TEXT NOT NULL, label TEXT NOT NULL,
                linked_utc REAL NOT NULL,
                PRIMARY KEY (source, external_id, label)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_observations (
                source TEXT NOT NULL, external_id TEXT NOT NULL,
                observed_utc REAL NOT NULL, metadata_json TEXT NOT NULL,
                PRIMARY KEY (source,external_id,observed_utc)
            )
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO media_labels (source,external_id,label,linked_utc) "
            "SELECT source,external_id,ticker,fetched_utc FROM media_posts"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticker_time ON media_posts (ticker, created_utc)"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_odds (
                theme TEXT, topic TEXT, market_id TEXT NOT NULL, captured_utc REAL NOT NULL,
                question TEXT, probability REAL, volume REAL, resolution_utc REAL,
                PRIMARY KEY (market_id, captured_utc)
            )
            """
        )
        # Small key/value table for poller bookkeeping (e.g. last_poll_utc), so
        # the incremental window survives process restarts (Fly redeploys/crashes).
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS poll_state (key TEXT PRIMARY KEY, value REAL)"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_cycles (
                collection_cycle_id TEXT PRIMARY KEY,
                cycle_kind TEXT NOT NULL,
                period_key TEXT NOT NULL,
                protocol_id TEXT NOT NULL,
                collector_semantics_id TEXT NOT NULL,
                identity_json TEXT NOT NULL,
                started_utc REAL NOT NULL,
                completed_utc REAL,
                status TEXT NOT NULL,
                manifest_id TEXT,
                manifest_json TEXT,
                server_started_utc REAL,
                server_terminal_utc REAL,
                collector_build_id TEXT,
                CHECK (status IN ('running', 'complete', 'incomplete')),
                CHECK (
                    (status = 'running' AND completed_utc IS NULL
                        AND manifest_id IS NULL AND manifest_json IS NULL)
                    OR
                    (status IN ('complete', 'incomplete') AND completed_utc IS NOT NULL
                        AND manifest_id IS NOT NULL AND manifest_json IS NOT NULL)
                )
            )
            """
        )
        cycle_columns = {
            row[1]
            for row in self.conn.execute(
                "PRAGMA table_info(collection_cycles)"
            ).fetchall()
        }
        for column, declaration in (
            ("server_started_utc", "REAL"),
            ("server_terminal_utc", "REAL"),
            ("collector_build_id", "TEXT"),
        ):
            if column not in cycle_columns:
                self.conn.execute(
                    f"ALTER TABLE collection_cycles ADD COLUMN {column} {declaration}"
                )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_cycle_slots (
                collection_cycle_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                query_key TEXT NOT NULL,
                slot_kind TEXT NOT NULL,
                declared_utc REAL NOT NULL,
                PRIMARY KEY (collection_cycle_id, provider, query_key),
                FOREIGN KEY (collection_cycle_id)
                    REFERENCES collection_cycles(collection_cycle_id),
                CHECK (slot_kind IN ('static', 'dynamic'))
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_runs (
                fetch_run_id TEXT PRIMARY KEY, provider TEXT NOT NULL,
                query_key TEXT NOT NULL, started_utc REAL NOT NULL,
                received_utc REAL, completed_utc REAL, status TEXT NOT NULL,
                item_count INTEGER, inserted_count INTEGER, error TEXT,
                formal_eligible_item_count INTEGER,
                formal_eligible_evidence_ids_json TEXT,
                formal_eligible_lineage_json TEXT,
                cost_units REAL NOT NULL DEFAULT 0, cursor_before REAL,
                cursor_after REAL, metadata_json TEXT NOT NULL DEFAULT '{}',
                collection_cycle_id TEXT,
                server_started_utc REAL,
                server_terminal_utc REAL,
                collector_build_id TEXT
            )
            """
        )
        fetch_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(fetch_runs)").fetchall()
        }
        if "formal_eligible_item_count" not in fetch_columns:
            self.conn.execute(
                "ALTER TABLE fetch_runs ADD COLUMN formal_eligible_item_count INTEGER"
            )
        if "formal_eligible_evidence_ids_json" not in fetch_columns:
            self.conn.execute(
                "ALTER TABLE fetch_runs ADD COLUMN formal_eligible_evidence_ids_json TEXT"
            )
        if "formal_eligible_lineage_json" not in fetch_columns:
            self.conn.execute(
                "ALTER TABLE fetch_runs ADD COLUMN formal_eligible_lineage_json TEXT"
            )
        if "collection_cycle_id" not in fetch_columns:
            self.conn.execute(
                "ALTER TABLE fetch_runs ADD COLUMN collection_cycle_id TEXT"
            )
        for column, declaration in (
            ("server_started_utc", "REAL"),
            ("server_terminal_utc", "REAL"),
            ("collector_build_id", "TEXT"),
        ):
            if column not in fetch_columns:
                self.conn.execute(
                    f"ALTER TABLE fetch_runs ADD COLUMN {column} {declaration}"
                )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_run_items (
                fetch_run_id TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                raw_content_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                observed_utc REAL NOT NULL,
                formal_eligible INTEGER NOT NULL,
                PRIMARY KEY (fetch_run_id, source, external_id),
                UNIQUE (fetch_run_id, raw_content_id),
                FOREIGN KEY (fetch_run_id) REFERENCES fetch_runs(fetch_run_id),
                FOREIGN KEY (source, external_id)
                    REFERENCES media_posts(source, external_id),
                CHECK (substr(raw_content_id, 1, 4) = 'raw_'
                    AND length(raw_content_id) = 28
                    AND substr(raw_content_id, 5) NOT GLOB '*[^0-9a-f]*'),
                CHECK (substr(evidence_id, 1, 9) = 'evidence_'
                    AND length(evidence_id) = 33
                    AND substr(evidence_id, 10) NOT GLOB '*[^0-9a-f]*'),
                CHECK (formal_eligible IN (0, 1))
            )
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_fetch_run_items_update
            BEFORE UPDATE ON fetch_run_items
            BEGIN
                SELECT RAISE(ABORT, 'fetch run item lineage is append-only');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_fetch_run_items_delete
            BEFORE DELETE ON fetch_run_items
            BEGIN
                SELECT RAISE(ABORT, 'fetch run item lineage is append-only');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_fetch_run_item_insert
            BEFORE INSERT ON fetch_run_items
            WHEN NOT EXISTS (
                SELECT 1 FROM fetch_runs AS run
                WHERE run.fetch_run_id = NEW.fetch_run_id
                  AND run.status = 'running'
                  AND run.provider = NEW.source
                  AND NEW.observed_utc >= run.started_utc
            )
            BEGIN
                SELECT RAISE(ABORT, 'fetch run item lacks a matching running receipt');
            END
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fetch_query_time "
            "ON fetch_runs (provider,query_key,started_utc)"
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_fetch_cycle_query_unique "
            "ON fetch_runs (collection_cycle_id,provider,query_key) "
            "WHERE collection_cycle_id IS NOT NULL"
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_collection_cycle_insert
            BEFORE INSERT ON collection_cycles
            WHEN NEW.status <> 'running'
              OR NEW.completed_utc IS NOT NULL
              OR NEW.manifest_id IS NOT NULL
              OR NEW.manifest_json IS NOT NULL
              OR NEW.collection_cycle_id <> content_addressed_json_id(
                    'cycle_', NEW.identity_json
              )
              OR json_extract(NEW.identity_json, '$.schema_version') <> 1
              OR json_extract(NEW.identity_json, '$.cycle_kind') IS NOT NEW.cycle_kind
              OR json_extract(NEW.identity_json, '$.period_key') IS NOT NEW.period_key
              OR json_extract(NEW.identity_json, '$.protocol_id') IS NOT NEW.protocol_id
              OR json_extract(
                    NEW.identity_json, '$.collector_semantics_id'
              ) IS NOT NEW.collector_semantics_id
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle insert violates its identity');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_collection_cycle_delete
            BEFORE DELETE ON collection_cycles
            BEGIN
                SELECT RAISE(ABORT, 'collection cycles are immutable');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_collection_cycle_server_insert
            BEFORE INSERT ON collection_cycles
            WHEN NEW.server_started_utc IS NULL
              OR NEW.server_terminal_utc IS NOT NULL
              OR abs(
                    NEW.server_started_utc
                    - server_observed_utc()
              ) > 10.0
              OR NEW.collector_build_id IS NULL
              OR length(NEW.collector_build_id) <> 30
              OR substr(NEW.collector_build_id, 1, 6) <> 'build_'
              OR substr(NEW.collector_build_id, 7) GLOB '*[^0-9a-f]*'
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle lacks server-owned provenance');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_collection_cycle_update
            BEFORE UPDATE ON collection_cycles
            WHEN OLD.status <> 'running'
              OR NEW.status NOT IN ('complete', 'incomplete')
              OR NEW.collection_cycle_id IS NOT OLD.collection_cycle_id
              OR NEW.cycle_kind IS NOT OLD.cycle_kind
              OR NEW.period_key IS NOT OLD.period_key
              OR NEW.protocol_id IS NOT OLD.protocol_id
              OR NEW.collector_semantics_id IS NOT OLD.collector_semantics_id
              OR NEW.identity_json IS NOT OLD.identity_json
              OR NEW.started_utc IS NOT OLD.started_utc
              OR NEW.completed_utc < NEW.started_utc
              OR NEW.manifest_id <> content_addressed_json_id(
                    'cycle_manifest_', NEW.manifest_json
              )
              OR json_extract(NEW.manifest_json, '$.collection_cycle_id')
                    IS NOT NEW.collection_cycle_id
              OR json_extract(NEW.manifest_json, '$.cycle_kind') IS NOT NEW.cycle_kind
              OR json_extract(NEW.manifest_json, '$.period_key') IS NOT NEW.period_key
              OR json_extract(NEW.manifest_json, '$.protocol_id') IS NOT NEW.protocol_id
              OR json_extract(
                    NEW.manifest_json, '$.collector_semantics_id'
              ) IS NOT NEW.collector_semantics_id
              OR json_extract(NEW.manifest_json, '$.started_utc') IS NOT NEW.started_utc
              OR json_extract(NEW.manifest_json, '$.completed_utc') IS NOT NEW.completed_utc
              OR json_extract(NEW.manifest_json, '$.status') IS NOT NEW.status
              OR json_array_length(
                    json_extract(NEW.manifest_json, '$.expected_static_slots')
              ) <> (
                    SELECT count(*) FROM collection_cycle_slots
                    WHERE collection_cycle_id = OLD.collection_cycle_id
                      AND slot_kind = 'static'
              )
              OR json_array_length(
                    json_extract(NEW.manifest_json, '$.expected_dynamic_slots')
              ) <> (
                    SELECT count(*) FROM collection_cycle_slots
                    WHERE collection_cycle_id = OLD.collection_cycle_id
                      AND slot_kind = 'dynamic'
              )
              OR json_array_length(
                    json_extract(NEW.manifest_json, '$.slot_receipts')
              ) <> (
                    SELECT count(*) FROM collection_cycle_slots
                    WHERE collection_cycle_id = OLD.collection_cycle_id
              )
              OR EXISTS (
                    SELECT 1 FROM collection_cycle_slots AS slot
                    WHERE slot.collection_cycle_id = OLD.collection_cycle_id
                      AND NOT EXISTS (
                          SELECT 1
                          FROM json_each(
                              NEW.manifest_json,
                              CASE slot.slot_kind
                                  WHEN 'static' THEN '$.expected_static_slots'
                                  ELSE '$.expected_dynamic_slots'
                              END
                          ) AS expected
                          WHERE json_extract(expected.value, '$.provider') = slot.provider
                            AND json_extract(expected.value, '$.query_key') = slot.query_key
                      )
              )
              OR EXISTS (
                    SELECT 1 FROM collection_cycle_slots AS slot
                    LEFT JOIN fetch_runs AS run
                      ON run.collection_cycle_id = slot.collection_cycle_id
                     AND run.provider = slot.provider
                     AND run.query_key = slot.query_key
                    WHERE slot.collection_cycle_id = OLD.collection_cycle_id
                      AND NOT EXISTS (
                          SELECT 1
                          FROM json_each(NEW.manifest_json, '$.slot_receipts') AS receipt
                          WHERE json_extract(receipt.value, '$.slot_kind') = slot.slot_kind
                            AND json_extract(receipt.value, '$.provider') = slot.provider
                            AND json_extract(receipt.value, '$.query_key') = slot.query_key
                            AND json_extract(receipt.value, '$.fetch_run_id') IS run.fetch_run_id
                            AND json_extract(receipt.value, '$.status')
                                = coalesce(run.status, 'missing')
                            AND json_extract(receipt.value, '$.item_count') IS run.item_count
                            AND json_array_length(json_extract(
                                receipt.value, '$.raw_content_ids'
                            )) = (
                                SELECT count(*) FROM fetch_run_items AS item
                                WHERE item.fetch_run_id = run.fetch_run_id
                            )
                            AND NOT EXISTS (
                                SELECT 1 FROM fetch_run_items AS item
                                WHERE item.fetch_run_id = run.fetch_run_id
                                  AND NOT EXISTS (
                                      SELECT 1 FROM json_each(
                                          receipt.value, '$.raw_content_ids'
                                      ) AS raw
                                      WHERE raw.value = item.raw_content_id
                                  )
                            )
                      )
              )
              OR EXISTS (
                    SELECT 1 FROM fetch_runs
                    WHERE collection_cycle_id = OLD.collection_cycle_id
                      AND status = 'running'
              )
              OR NEW.status IS NOT CASE WHEN EXISTS (
                    SELECT 1 FROM collection_cycle_slots AS slot
                    LEFT JOIN fetch_runs AS run
                      ON run.collection_cycle_id = slot.collection_cycle_id
                     AND run.provider = slot.provider
                     AND run.query_key = slot.query_key
                    WHERE slot.collection_cycle_id = OLD.collection_cycle_id
                      AND coalesce(run.status, 'missing') NOT IN ('success', 'empty')
              ) THEN 'incomplete' ELSE 'complete' END
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle terminal manifest is invalid');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_collection_cycle_server_update
            BEFORE UPDATE ON collection_cycles
            WHEN NEW.server_started_utc IS NOT OLD.server_started_utc
              OR NEW.collector_build_id IS NOT OLD.collector_build_id
              OR NEW.server_terminal_utc IS NULL
              OR NEW.server_terminal_utc < OLD.server_started_utc
              OR abs(
                    NEW.server_terminal_utc
                    - server_observed_utc()
              ) > 10.0
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle terminal observation is not server-current');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_collection_cycle_slot_insert
            BEFORE INSERT ON collection_cycle_slots
            WHEN NOT EXISTS (
                SELECT 1 FROM collection_cycles AS cycle
                WHERE cycle.collection_cycle_id = NEW.collection_cycle_id
                  AND cycle.status = 'running'
                  AND NEW.declared_utc >= cycle.started_utc
                  AND (
                      (
                          NEW.slot_kind = 'static'
                          AND EXISTS (
                              SELECT 1 FROM json_each(
                                  cycle.identity_json, '$.expected_static_slots'
                              ) AS expected
                              WHERE json_extract(expected.value, '$.provider') = NEW.provider
                                AND json_extract(expected.value, '$.query_key') = NEW.query_key
                          )
                      )
                      OR (
                          NEW.slot_kind = 'dynamic'
                          AND (
                              SELECT count(*) FROM collection_cycle_slots
                              WHERE collection_cycle_id = NEW.collection_cycle_id
                                AND slot_kind = 'dynamic'
                          ) < json_extract(cycle.identity_json, '$.max_dynamic_slots')
                      )
                  )
            )
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle slot is not declared by a running cycle');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_collection_cycle_slot_update
            BEFORE UPDATE ON collection_cycle_slots
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle slots are append-only');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_collection_cycle_slot_delete
            BEFORE DELETE ON collection_cycle_slots
            BEGIN
                SELECT RAISE(ABORT, 'collection cycle slots are append-only');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_fetch_run_cycle_insert
            BEFORE INSERT ON fetch_runs
            WHEN NEW.collection_cycle_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM collection_cycles AS cycle
                  JOIN collection_cycle_slots AS slot
                    ON slot.collection_cycle_id = cycle.collection_cycle_id
                   AND slot.provider = NEW.provider
                   AND slot.query_key = NEW.query_key
                  WHERE cycle.collection_cycle_id = NEW.collection_cycle_id
                    AND cycle.status = 'running'
                    AND NEW.started_utc >= cycle.started_utc
              )
            BEGIN
                SELECT RAISE(ABORT, 'fetch receipt lacks a declared running cycle slot');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_fetch_run_server_insert
            BEFORE INSERT ON fetch_runs
            WHEN NEW.server_started_utc IS NULL
              OR NEW.server_terminal_utc IS NOT NULL
              OR abs(
                    NEW.server_started_utc
                    - server_observed_utc()
              ) > 10.0
              OR NEW.collector_build_id IS NULL
              OR length(NEW.collector_build_id) <> 30
              OR substr(NEW.collector_build_id, 1, 6) <> 'build_'
              OR substr(NEW.collector_build_id, 7) GLOB '*[^0-9a-f]*'
            BEGIN
                SELECT RAISE(ABORT, 'fetch receipt lacks server-owned provenance');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_fetch_run_server_update
            BEFORE UPDATE ON fetch_runs
            WHEN NEW.server_started_utc IS NOT OLD.server_started_utc
              OR NEW.collector_build_id IS NOT OLD.collector_build_id
              OR (
                    OLD.status = 'running'
                    AND NEW.status IN ('success', 'empty', 'failed')
                    AND (
                        NEW.server_terminal_utc IS NULL
                        OR NEW.server_terminal_utc < OLD.server_started_utc
                        OR abs(
                            NEW.server_terminal_utc
                            - server_observed_utc()
                        ) > 10.0
                    )
              )
              OR (
                    NOT (
                        OLD.status = 'running'
                        AND NEW.status IN ('success', 'empty', 'failed')
                    )
                    AND NEW.server_terminal_utc IS NOT OLD.server_terminal_utc
              )
            BEGIN
                SELECT RAISE(ABORT, 'fetch terminal observation is not server-current');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS validate_cycle_fetch_build_identity
            BEFORE INSERT ON fetch_runs
            WHEN NEW.collection_cycle_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM collection_cycles AS cycle
                  WHERE cycle.collection_cycle_id = NEW.collection_cycle_id
                    AND cycle.collector_build_id IS NEW.collector_build_id
                    AND NEW.server_started_utc >= cycle.server_started_utc
              )
            BEGIN
                SELECT RAISE(ABORT, 'fetch receipt build differs from its cycle');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_fetch_run_cycle_binding_update
            BEFORE UPDATE ON fetch_runs
            WHEN NEW.collection_cycle_id IS NOT OLD.collection_cycle_id
            BEGIN
                SELECT RAISE(ABORT, 'fetch receipt cycle binding is immutable');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_terminal_cycle_fetch_update
            BEFORE UPDATE ON fetch_runs
            WHEN OLD.collection_cycle_id IS NOT NULL AND OLD.status <> 'running'
            BEGIN
                SELECT RAISE(ABORT, 'terminal cycle child receipts are immutable');
            END
            """
        )
        self.conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_cycle_fetch_delete
            BEFORE DELETE ON fetch_runs
            WHEN OLD.collection_cycle_id IS NOT NULL
            BEGIN
                SELECT RAISE(ABORT, 'cycle child receipts are immutable');
            END
            """
        )
        self.conn.commit()

    def _store_in_transaction(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        for row in _validate_batch_media_coherence(rows):
            self.conn.row_factory = sqlite3.Row
            existing_row = self.conn.execute(
                f"SELECT {','.join(COLUMNS)} FROM media_posts "
                "WHERE source=? AND external_id=?",
                (row.get("source"), row.get("external_id")),
            ).fetchone()
            self.conn.row_factory = None
            if existing_row is None:
                continue
            existing = dict(existing_row)
            observation = self.conn.execute(
                "SELECT metadata_json FROM media_observations WHERE source=? "
                "AND external_id=? ORDER BY observed_utc DESC LIMIT 1",
                (row.get("source"), row.get("external_id")),
            ).fetchone()
            existing["metadata"] = json.loads(observation[0]) if observation else {}
            if _media_rows_conflict(existing, row):
                raise ValueError("formal media identity changed immutable provenance")
        before = self.conn.total_changes
        self.conn.executemany(
            f"INSERT OR IGNORE INTO media_posts ({','.join(COLUMNS)}) "
            f"VALUES ({','.join(':' + c for c in COLUMNS)})",
            rows,
        )
        inserted = self.conn.total_changes - before
        links = []
        for row in rows:
            labels = row.get("labels") or [row["ticker"]]
            links.extend({
                "source": row["source"], "external_id": row["external_id"],
                "label": label.upper(), "linked_utc": row["fetched_utc"],
            } for label in labels if label)
        self.conn.executemany(
            "INSERT OR IGNORE INTO media_labels (source,external_id,label,linked_utc) "
            "VALUES (:source,:external_id,:label,:linked_utc)",
            links,
        )
        observations = [{
            "source": row["source"], "external_id": row["external_id"],
            "observed_utc": row["fetched_utc"],
            "metadata_json": json.dumps(row["metadata"], sort_keys=True),
        } for row in rows if row.get("metadata")]
        self.conn.executemany(
            "INSERT OR IGNORE INTO media_observations "
            "(source,external_id,observed_utc,metadata_json) VALUES "
            "(:source,:external_id,:observed_utc,:metadata_json)", observations,
        )
        return inserted

    def store(self, rows: list[dict]) -> int:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            inserted = self._store_in_transaction(rows)
            self.conn.commit()
            return inserted
        except Exception:
            self.conn.rollback()
            raise

    def _attach_labels(
        self, rows: list[dict], cutoff_utc: float | None = None,
        *, strict_cutoff: bool = False,
    ) -> list[dict]:
        attached = []
        for row in rows:
            receipt_sql = (
                "SELECT receipt.server_terminal_utc,item.observed_utc,"
                "receipt.metadata_json,observation.metadata_json "
                "FROM fetch_run_items AS item "
                "JOIN fetch_runs AS receipt ON receipt.fetch_run_id=item.fetch_run_id "
                "LEFT JOIN media_observations AS observation "
                "ON observation.source=item.source "
                "AND observation.external_id=item.external_id "
                "AND observation.observed_utc=item.observed_utc "
                "WHERE item.source=? AND item.external_id=? "
                "AND receipt.status='success' AND receipt.server_terminal_utc IS NOT NULL"
            )
            receipt_params: list = [row["source"], row["external_id"]]
            if cutoff_utc is not None:
                receipt_sql += " AND receipt.server_terminal_utc" + (
                    "<?" if strict_cutoff else "<=?"
                )
                receipt_params.append(cutoff_utc)
            receipts = self.conn.execute(
                receipt_sql
                + " ORDER BY receipt.server_terminal_utc DESC,receipt.fetch_run_id DESC",
                receipt_params,
            ).fetchall()
            if receipts:
                latest_observation = (
                    json.loads(receipts[0][3]) if receipts[0][3] else {}
                )
                row["metadata"] = (
                    latest_observation
                    if isinstance(latest_observation, dict) else {}
                )
                trusted_labels: set[str] = set()
                for receipt in receipts:
                    receipt_metadata = json.loads(receipt[2]) if receipt[2] else {}
                    observation_metadata = json.loads(receipt[3]) if receipt[3] else {}
                    for value in (
                        receipt_metadata.get("labels", [])
                        if isinstance(receipt_metadata, dict) else []
                    ):
                        if isinstance(value, str) and value.strip():
                            trusted_labels.add(value.strip().upper())
                    for value in (
                        observation_metadata.get("receipt_labels", [])
                        if isinstance(observation_metadata, dict) else []
                    ):
                        if isinstance(value, str) and value.strip():
                            trusted_labels.add(value.strip().upper())
                if not trusted_labels and row.get("source") == "trendnews" \
                        and isinstance(row.get("ticker"), str):
                    # Pre-receipt-label discovery rows can safely retain the
                    # ticker persisted by their first successful receipt.
                    trusted_labels.add(row["ticker"].strip().upper())
                row["labels"] = sorted(trusted_labels)
                row["latest_observed_utc"] = float(receipts[0][0])
                row["latest_observed_utc_source"] = "server_terminal_utc"
                attached.append(row)
                continue

            lineage_exists = self.conn.execute(
                "SELECT 1 FROM fetch_run_items WHERE source=? AND external_id=? LIMIT 1",
                (row["source"], row["external_id"]),
            ).fetchone()
            if lineage_exists is not None:
                # Receipt lineage exists, but none committed successfully by
                # this cutoff. Falling back to client clocks would leak it.
                continue

            sql = "SELECT label FROM media_labels WHERE source=? AND external_id=?"
            params: list = [row["source"], row["external_id"]]
            if cutoff_utc is not None:
                sql += " AND linked_utc" + ("<?" if strict_cutoff else "<=?")
                params.append(cutoff_utc)
            labels = self.conn.execute(sql + " ORDER BY label", params).fetchall()
            row["labels"] = [label[0] for label in labels]
            observation_sql = (
                "SELECT metadata_json,observed_utc FROM media_observations WHERE source=? "
                "AND external_id=?"
            )
            observation_params: list = [row["source"], row["external_id"]]
            if cutoff_utc is not None:
                observation_sql += " AND observed_utc" + ("<?" if strict_cutoff else "<=?")
                observation_params.append(cutoff_utc)
            observation = self.conn.execute(
                observation_sql + " ORDER BY observed_utc DESC LIMIT 1", observation_params,
            ).fetchone()
            row["metadata"] = json.loads(observation[0]) if observation else {}
            row["latest_observed_utc"] = (
                float(observation[1]) if observation else row.get("fetched_utc")
            )
            row["latest_observed_utc_source"] = (
                "media_observation_utc" if observation else "fetched_utc"
            )
            attached.append(row)
        return attached

    def stats(self) -> list[tuple]:
        return self.conn.execute(
            "SELECT ticker, source, COUNT(*), MIN(created_utc), MAX(created_utc) "
            "FROM media_posts GROUP BY ticker, source ORDER BY ticker, source"
        ).fetchall()

    def window(self, ticker: str, end: str, days: int) -> list[dict]:
        lo, hi = _window_bounds(end, days)
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT p.* FROM media_posts p WHERE EXISTS ("
            "SELECT 1 FROM media_labels l WHERE l.source=p.source "
            "AND l.external_id=p.external_id AND l.label=? AND l.linked_utc<=?) "
            "AND created_utc >= ? "
            "AND created_utc <= ? ORDER BY created_utc",
            (ticker.upper(), hi, lo, hi),
        ).fetchall()
        self.conn.row_factory = None
        attached = self._attach_labels([dict(r) for r in rows], hi)
        return [
            row for row in attached
            if _matches_requested_labels(row, tickers=[ticker])
        ]

    def history_asof(
        self,
        start: str,
        end: str,
        *,
        tickers: list[str] | None = None,
        ticker_prefixes: list[str] | None = None,
        sources: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Rows known by the end-of-day cutoff, newest first.

        Both ``created_utc`` and ``fetched_utc`` are constrained. The latter is
        essential: an old article first discovered today was not available to
        a historical decision and must not leak into a backtest.
        """
        lo, hi = _history_bounds(start, end)
        clauses = ["created_utc >= ?", "created_utc < ?", "fetched_utc < ?"]
        params: list = [lo, hi, hi]
        identity_clauses = []
        if tickers:
            marks = ",".join("?" for _ in tickers)
            identity_clauses.append(
                "EXISTS (SELECT 1 FROM media_labels l WHERE l.source=media_posts.source "
                f"AND l.external_id=media_posts.external_id AND l.label IN ({marks}) "
                "AND l.linked_utc < ?)"
            )
            params.extend(ticker.upper() for ticker in tickers)
            params.append(hi)
        if ticker_prefixes:
            identity_clauses.extend(
                "EXISTS (SELECT 1 FROM media_labels l WHERE l.source=media_posts.source "
                "AND l.external_id=media_posts.external_id AND l.label LIKE ? "
                "AND l.linked_utc < ?)"
                for _ in ticker_prefixes
            )
            for prefix in ticker_prefixes:
                params.extend([prefix.upper() + "%", hi])
        if identity_clauses:
            clauses.append("(" + " OR ".join(identity_clauses) + ")")
        if sources:
            marks = ",".join("?" for _ in sources)
            clauses.append(f"source IN ({marks})")
            params.extend(sources)
        target = max(1, limit)
        query = (
            "SELECT * FROM media_posts WHERE " + " AND ".join(clauses)
            + " ORDER BY created_utc DESC,source,external_id LIMIT ? OFFSET ?"
        )
        matched: list[dict] = []
        offset = 0
        while len(matched) < target:
            self.conn.row_factory = sqlite3.Row
            rows = self.conn.execute(
                query, [*params, target, offset]
            ).fetchall()
            self.conn.row_factory = None
            if not rows:
                break
            attached = self._attach_labels(
                [dict(row) for row in rows], hi, strict_cutoff=True
            )
            matched.extend(
                row for row in attached
                if _matches_requested_labels(
                    row, tickers=tickers, ticker_prefixes=ticker_prefixes
                )
            )
            offset += len(rows)
            if len(rows) < target:
                break
        return matched[:target]

    def _store_odds_in_transaction(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            f"INSERT OR IGNORE INTO macro_odds ({','.join(ODDS_COLUMNS)}) "
            f"VALUES ({','.join(':' + c for c in ODDS_COLUMNS)})",
            rows,
        )
        return self.conn.total_changes - before

    def store_odds(self, rows: list[dict]) -> int:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            inserted = self._store_odds_in_transaction(rows)
            self.conn.commit()
            return inserted
        except Exception:
            self.conn.rollback()
            raise

    def odds_asof(self, end: str, themes: list[str] | None = None) -> list[dict]:
        params = {"hi": _midnight_epoch(end)}
        clause = ""
        if themes:
            marks = ",".join(f":t{i}" for i in range(len(themes)))
            clause = f"AND o.theme IN ({marks})"
            params.update({f"t{i}": t for i, t in enumerate(themes)})
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(_odds_asof_sql(clause), params).fetchall()
        self.conn.row_factory = None
        return [dict(r) for r in rows]

    def odds_stats(self) -> list[tuple]:
        return self.conn.execute(
            "SELECT theme, COUNT(DISTINCT market_id), COUNT(*), "
            "MIN(captured_utc), MAX(captured_utc) "
            "FROM macro_odds GROUP BY theme ORDER BY theme"
        ).fetchall()

    def server_observed_utc(self) -> float:
        """Read the database clock used to bound one collector coverage cycle."""
        return _sqlite_server_observed_utc(self.conn)

    def get_meta(self, key: str) -> float | None:
        row = self.conn.execute(
            "SELECT value FROM poll_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: float) -> None:
        self.conn.execute(
            "INSERT INTO poll_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def reserve_meta_budget(
        self, limits: dict[str, float], *, amount: float = 1.0
    ) -> dict[str, float] | None:
        """Atomically increment all counters, or none if any limit is exhausted."""
        limits, amount = _validated_meta_budget(limits, amount)
        if any(amount > limit for limit in limits.values()):
            return None
        try:
            # A write lock before the first read-modify-write prevents two local
            # workers from both observing the same remaining SQLite allowance.
            self.conn.execute("BEGIN IMMEDIATE")
            reserved = {}
            for key in sorted(limits):
                row = self.conn.execute(
                    "INSERT INTO poll_state (key,value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=poll_state.value+excluded.value "
                    "WHERE poll_state.value>=0 "
                    "AND poll_state.value+excluded.value<=? RETURNING value",
                    (key, amount, limits[key]),
                ).fetchone()
                if row is None:
                    raise _MetaBudgetExceeded
                reserved[key] = float(row[0])
            self.conn.commit()
            return reserved
        except _MetaBudgetExceeded:
            self.conn.rollback()
            return None
        except Exception:
            self.conn.rollback()
            raise

    def start_collection_cycle(self, spec: dict, *, started_utc: float) -> str:
        """Atomically insert a running cycle and every immutable static slot."""
        cycle_id, identity, identity_json = _validated_collection_cycle_spec(spec)
        started = _finite_cycle_time(started_utc, "start time")
        build_id = _collector_build_id()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            server_started = _sqlite_server_observed_utc(self.conn)
            self.conn.execute(
                "INSERT INTO collection_cycles "
                "(collection_cycle_id,cycle_kind,period_key,protocol_id,"
                "collector_semantics_id,identity_json,started_utc,status,"
                "server_started_utc,collector_build_id) "
                "VALUES (?,?,?,?,?,?,?,'running',?,?)",
                (
                    cycle_id, identity["cycle_kind"], identity["period_key"],
                    identity["protocol_id"], identity["collector_semantics_id"],
                    identity_json, started, server_started, build_id,
                ),
            )
            self.conn.executemany(
                "INSERT INTO collection_cycle_slots "
                "(collection_cycle_id,provider,query_key,slot_kind,declared_utc) "
                "VALUES (?,?,?,'static',?)",
                [
                    (cycle_id, slot["provider"], slot["query_key"], started)
                    for slot in identity["expected_static_slots"]
                ],
            )
            self.conn.commit()
            return cycle_id
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ValueError("collection cycle already exists or violates its identity") from exc
        except Exception:
            self.conn.rollback()
            raise

    def declare_collection_cycle_slots(
        self, collection_cycle_id: str, slots: list[tuple[str, str]],
        *, declared_utc: float,
    ) -> None:
        """Append the complete dynamic search set before the first search starts."""
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        payloads = _cycle_slot_payloads(slots)
        declared = _finite_cycle_time(declared_utc, "slot declaration time")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT identity_json,started_utc,status FROM collection_cycles "
                "WHERE collection_cycle_id=?", (cycle_id,),
            ).fetchone()
            if row is None or row[2] != "running":
                raise ValueError("dynamic slots require a running collection cycle")
            identity = json.loads(row[0])
            existing = self.conn.execute(
                "SELECT count(*) FROM collection_cycle_slots "
                "WHERE collection_cycle_id=? AND slot_kind='dynamic'", (cycle_id,),
            ).fetchone()[0]
            if existing or len(payloads) > identity["max_dynamic_slots"]:
                raise ValueError("collection cycle dynamic slots were already declared or exceed cap")
            if declared < float(row[1]):
                raise ValueError("collection cycle slot declaration precedes its start")
            self.conn.executemany(
                "INSERT INTO collection_cycle_slots "
                "(collection_cycle_id,provider,query_key,slot_kind,declared_utc) "
                "VALUES (?,?,?,'dynamic',?)",
                [
                    (cycle_id, slot["provider"], slot["query_key"], declared)
                    for slot in payloads
                ],
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ValueError("collection cycle dynamic slot declaration is invalid") from exc
        except Exception:
            self.conn.rollback()
            raise

    def finish_collection_cycle(
        self, collection_cycle_id: str, *, completed_utc: float,
    ) -> dict:
        """Perform the sole running-to-terminal transition with an exact manifest."""
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.row_factory = sqlite3.Row
            cycle_row = self.conn.execute(
                f"SELECT {','.join(COLLECTION_CYCLE_COLUMNS)} "
                "FROM collection_cycles WHERE collection_cycle_id=?", (cycle_id,),
            ).fetchone()
            if cycle_row is None or cycle_row["status"] != "running":
                raise ValueError("unknown or terminal collection cycle")
            slots = [dict(row) for row in self.conn.execute(
                f"SELECT {','.join(COLLECTION_CYCLE_SLOT_COLUMNS)} "
                "FROM collection_cycle_slots WHERE collection_cycle_id=?",
                (cycle_id,),
            ).fetchall()]
            receipts = [dict(row) for row in self.conn.execute(
                "SELECT fetch_run_id,provider,query_key,status,item_count FROM fetch_runs "
                "WHERE collection_cycle_id=?", (cycle_id,),
            ).fetchall()]
            item_rows = [dict(row) for row in self.conn.execute(
                "SELECT item.fetch_run_id,item.raw_content_id,"
                + ",".join(
                    f"post.{column} AS stored_{column}" for column in COLUMNS
                )
                + ",observation.metadata_json "
                "FROM fetch_run_items AS item JOIN fetch_runs AS run "
                "ON run.fetch_run_id=item.fetch_run_id "
                "JOIN media_posts AS post ON post.source=item.source "
                "AND post.external_id=item.external_id "
                "LEFT JOIN media_observations AS observation "
                "ON observation.source=item.source "
                "AND observation.external_id=item.external_id "
                "AND observation.observed_utc=item.observed_utc "
                "WHERE run.collection_cycle_id=?", (cycle_id,),
            ).fetchall()]
            self.conn.row_factory = None
            server_terminal = _sqlite_server_observed_utc(self.conn)
            terminal_cycle = {
                **dict(cycle_row), "server_terminal_utc": server_terminal,
            }
            status, manifest_id, manifest_json, _ = _collection_cycle_manifest(
                terminal_cycle, slots,
                _cycle_receipts_with_lineage(
                    receipts, _verified_cycle_item_rows(item_rows)
                ), completed_utc,
            )
            result = self.conn.execute(
                "UPDATE collection_cycles SET completed_utc=?,status=?,manifest_id=?,"
                "manifest_json=?,server_terminal_utc=? "
                "WHERE collection_cycle_id=? AND status='running'",
                (
                    completed_utc, status, manifest_id, manifest_json,
                    server_terminal, cycle_id,
                ),
            )
            if result.rowcount != 1:
                raise ValueError("unknown or terminal collection cycle")
            self.conn.commit()
            return self.collection_cycle(cycle_id)
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            self.conn.row_factory = None
            raise ValueError("collection cycle terminal manifest is invalid") from exc
        except Exception:
            self.conn.rollback()
            self.conn.row_factory = None
            raise

    def recover_collection_cycle(
        self, collection_cycle_id: str, *, recovered_utc: float,
        minimum_age_seconds: float,
    ) -> dict:
        """Seal a same-ID orphan without reissuing any external request."""
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        recovered = _finite_cycle_time(recovered_utc, "recovery time")
        minimum_age = _finite_cycle_time(
            minimum_age_seconds, "minimum recovery age"
        )
        if minimum_age <= 0:
            raise ValueError("collection cycle minimum recovery age must be positive")
        cycle = self.collection_cycle(cycle_id)
        if cycle is None:
            raise ValueError("unknown collection cycle")
        if cycle["status"] in {"complete", "incomplete"}:
            if not cycle.get("manifest_valid"):
                raise ValueError("terminal collection cycle manifest is invalid")
            return cycle
        server_started = cycle.get("server_started_utc")
        if not isinstance(server_started, (int, float)) \
                or isinstance(server_started, bool) \
                or not math.isfinite(float(server_started)):
            raise ValueError("running collection cycle lacks a server start observation")
        observed_now = _sqlite_server_observed_utc(self.conn)
        if observed_now - float(server_started) < minimum_age:
            raise ValueError("running collection cycle is not stale enough to recover")
        self.conn.row_factory = sqlite3.Row
        running = self.conn.execute(
            "SELECT fetch_run_id,started_utc,cost_units FROM fetch_runs "
            "WHERE collection_cycle_id=? AND status='running' "
            "ORDER BY started_utc,fetch_run_id", (cycle_id,),
        ).fetchall()
        self.conn.row_factory = None
        for receipt in running:
            terminal_time = max(recovered, float(receipt["started_utc"]))
            self.finish_fetch(
                receipt["fetch_run_id"],
                status="failed",
                received_utc=terminal_time,
                completed_utc=terminal_time,
                item_count=0,
                inserted_count=0,
                error="collector_restart_recovery",
                cost_units=float(receipt["cost_units"]),
            )
        return self.finish_collection_cycle(
            cycle_id, completed_utc=max(recovered, float(cycle["started_utc"]))
        )

    def collection_cycle(self, collection_cycle_id: str) -> dict | None:
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        self.conn.row_factory = sqlite3.Row
        row = self.conn.execute(
            f"SELECT {','.join(COLLECTION_CYCLE_COLUMNS)} FROM collection_cycles "
            "WHERE collection_cycle_id=?", (cycle_id,),
        ).fetchone()
        slots = self.conn.execute(
            f"SELECT {','.join(COLLECTION_CYCLE_SLOT_COLUMNS)} "
            "FROM collection_cycle_slots WHERE collection_cycle_id=?",
            (cycle_id,),
        ).fetchall() if row else []
        receipts = self.conn.execute(
            "SELECT fetch_run_id,provider,query_key,status,item_count FROM fetch_runs "
            "WHERE collection_cycle_id=?", (cycle_id,),
        ).fetchall() if row else []
        item_rows = self.conn.execute(
            "SELECT item.fetch_run_id,item.raw_content_id,"
            + ",".join(
                f"post.{column} AS stored_{column}" for column in COLUMNS
            )
            + ",observation.metadata_json "
            "FROM fetch_run_items AS item JOIN fetch_runs AS run "
            "ON run.fetch_run_id=item.fetch_run_id "
            "JOIN media_posts AS post ON post.source=item.source "
            "AND post.external_id=item.external_id "
            "LEFT JOIN media_observations AS observation "
            "ON observation.source=item.source "
            "AND observation.external_id=item.external_id "
            "AND observation.observed_utc=item.observed_utc "
            "WHERE run.collection_cycle_id=?", (cycle_id,),
        ).fetchall() if row else []
        self.conn.row_factory = None
        return _verify_collection_cycle_relations(
            dict(row), [dict(item) for item in slots],
            _cycle_receipts_with_lineage(
                [dict(item) for item in receipts],
                _verified_cycle_item_rows([dict(item) for item in item_rows]),
            ),
        ) if row else None

    def collection_cycle_identity_pairs(
        self, cycle_kind: str,
    ) -> list[tuple[str, str]]:
        """Return every immutable protocol/collector pair seen for one cycle kind."""
        kind = _validated_cycle_text(cycle_kind, "kind", max_bytes=64)
        if _COLLECTION_CYCLE_KIND.fullmatch(kind) is None:
            raise ValueError("collection cycle kind must be a lowercase slug")
        rows = self.conn.execute(
            "SELECT DISTINCT protocol_id,collector_semantics_id "
            "FROM collection_cycles WHERE cycle_kind=? "
            "ORDER BY protocol_id,collector_semantics_id",
            (kind,),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def collection_cycle_slots(self, collection_cycle_id: str) -> list[dict]:
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            f"SELECT {','.join(COLLECTION_CYCLE_SLOT_COLUMNS)} "
            "FROM collection_cycle_slots WHERE collection_cycle_id=? "
            "ORDER BY CASE slot_kind WHEN 'static' THEN 0 ELSE 1 END,provider,query_key",
            (cycle_id,),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def collection_cycle_formal_lineage(
        self, collection_cycle_id: str, *, provider: str,
    ) -> list[dict]:
        """Return replayed formal item lineage for one complete cycle provider."""
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        cycle = self.collection_cycle(cycle_id)
        if cycle is None or cycle.get("status") != "complete" \
                or not cycle.get("manifest_valid"):
            raise ValueError("formal cycle lineage requires a valid complete cycle")
        self.conn.row_factory = sqlite3.Row
        receipts = self.conn.execute(
            f"SELECT {','.join(FETCH_RUN_COLUMNS)} FROM fetch_runs "
            "WHERE collection_cycle_id=? AND provider=? ORDER BY fetch_run_id",
            (cycle_id, provider),
        ).fetchall()
        items = self.conn.execute(
            "SELECT item.fetch_run_id,item.source,item.external_id,"
            "item.evidence_id,item.raw_content_id,item.formal_eligible "
            "FROM fetch_run_items AS item JOIN fetch_runs AS run "
            "ON run.fetch_run_id=item.fetch_run_id "
            "WHERE run.collection_cycle_id=? AND run.provider=? "
            "ORDER BY item.evidence_id,item.raw_content_id,item.fetch_run_id",
            (cycle_id, provider),
        ).fetchall()
        self.conn.row_factory = None
        return _verified_cycle_formal_lineage(
            [dict(row) for row in receipts], [dict(row) for row in items]
        )

    def _validate_cycle_fetch_binding(
        self, collection_cycle_id: str | None, provider: str,
        query_key: str, started_utc: float,
    ) -> str | None:
        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        if cycle_id is None:
            return None
        row = self.conn.execute(
            "SELECT 1 FROM collection_cycles AS cycle "
            "JOIN collection_cycle_slots AS slot "
            "ON slot.collection_cycle_id=cycle.collection_cycle_id "
            "AND slot.provider=? AND slot.query_key=? "
            "WHERE cycle.collection_cycle_id=? AND cycle.status='running' "
            "AND ?>=cycle.started_utc",
            (provider, query_key, cycle_id, started_utc),
        ).fetchone()
        if row is None:
            raise ValueError("fetch receipt lacks a declared running cycle slot")
        return cycle_id

    def start_fetch(
        self, provider: str, query_key: str, started_utc: float,
        *, cursor_before: float | None = None, metadata: dict | None = None,
        collection_cycle_id: str | None = None,
    ) -> str:
        fetch_run_id = str(uuid.uuid4())
        build_id = _collector_build_id(metadata)
        cycle_id = self._validate_cycle_fetch_binding(
            collection_cycle_id, provider, query_key, started_utc
        )
        try:
            server_started = _sqlite_server_observed_utc(self.conn)
            self.conn.execute(
                "INSERT INTO fetch_runs "
                "(fetch_run_id,provider,query_key,started_utc,status,cost_units,"
                "cursor_before,metadata_json,collection_cycle_id,server_started_utc,"
                "collector_build_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (fetch_run_id, provider, query_key, started_utc, "running", 0.0,
                 cursor_before, json.dumps(metadata or {}, sort_keys=True), cycle_id,
                 server_started, build_id),
            )
            self.conn.commit()
            return fetch_run_id
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ValueError("fetch cycle slot already has a receipt or is invalid") from exc

    def start_budgeted_fetch(
        self, provider: str, query_key: str, started_utc: float,
        *, budget_limits: dict[str, float], budget_amount: float = 1.0,
        cursor_before: float | None = None, metadata: dict | None = None,
        collection_cycle_id: str | None = None,
    ) -> str | None:
        """Atomically reserve durable counters and append the running receipt."""
        limits, amount = _validated_meta_budget(budget_limits, budget_amount)
        if any(amount > limit for limit in limits.values()):
            return None
        if "budget_reservation" in (metadata or {}):
            raise ValueError("budget reservation metadata is store-owned")
        fetch_run_id = str(uuid.uuid4())
        build_id = _collector_build_id(metadata)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            cycle_id = self._validate_cycle_fetch_binding(
                collection_cycle_id, provider, query_key, started_utc
            )
            reserved = {}
            for key in sorted(limits):
                row = self.conn.execute(
                    "INSERT INTO poll_state (key,value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=poll_state.value+excluded.value "
                    "WHERE poll_state.value>=0 "
                    "AND poll_state.value+excluded.value<=? RETURNING value",
                    (key, amount, limits[key]),
                ).fetchone()
                if row is None:
                    raise _MetaBudgetExceeded
                reserved[key] = float(row[0])
            receipt_metadata = {
                **(metadata or {}),
                "budget_reservation": {
                    "amount": amount,
                    "limits": limits,
                    "reserved": reserved,
                },
            }
            server_started = _sqlite_server_observed_utc(self.conn)
            self.conn.execute(
                "INSERT INTO fetch_runs "
                "(fetch_run_id,provider,query_key,started_utc,status,cost_units,"
                "cursor_before,metadata_json,collection_cycle_id,server_started_utc,"
                "collector_build_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fetch_run_id, provider, query_key, started_utc, "running", amount,
                    cursor_before, json.dumps(receipt_metadata, sort_keys=True),
                    cycle_id, server_started, build_id,
                ),
            )
            self.conn.commit()
            return fetch_run_id
        except _MetaBudgetExceeded:
            self.conn.rollback()
            return None
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ValueError("fetch cycle slot already has a receipt or is invalid") from exc
        except Exception:
            self.conn.rollback()
            raise

    def _finish_fetch_in_transaction(
        self, fetch_run_id: str, *, status: str, received_utc: float,
        completed_utc: float, item_count: int, inserted_count: int,
        error: str | None = None, cost_units: float = 0.0,
        cursor_after: float | None = None,
        formal_eligible_item_count: int | None = None,
        formal_eligible_evidence_ids: list[str] | None = None,
        formal_eligible_lineage: list[dict] | None = None,
    ) -> None:
        current = self.conn.execute(
            "SELECT provider,status,started_utc,cost_units FROM fetch_runs "
            "WHERE fetch_run_id=?",
            (fetch_run_id,),
        ).fetchone()
        if current is None or current[1] != "running":
            raise ValueError(f"unknown or completed fetch run {fetch_run_id}")
        _validate_fetch_completion(
            started_utc=current[2], status=status, received_utc=received_utc,
            completed_utc=completed_utc, item_count=item_count,
            inserted_count=inserted_count, error=error, cost_units=cost_units,
            cursor_after=cursor_after,
        )
        if float(cost_units) < float(current[3]):
            raise ValueError("terminal cost units cannot erase a reserved paid request")
        eligible_ids_json = _encoded_formal_evidence_ids(
            formal_eligible_item_count,
            formal_eligible_evidence_ids,
            item_count=item_count,
        )
        eligible_lineage_json = _encoded_formal_lineage(
            formal_eligible_item_count,
            formal_eligible_evidence_ids,
            formal_eligible_lineage,
            item_count=item_count,
        ) if formal_eligible_lineage is not None else None
        if current[0] in {"globalnews", "trendnews"} and status in {"success", "empty"} \
                and eligible_ids_json is None:
            raise ValueError("formal news receipts require exact eligible evidence IDs")
        server_terminal = _sqlite_server_observed_utc(self.conn)
        result = self.conn.execute(
            "UPDATE fetch_runs SET received_utc=?,completed_utc=?,status=?,item_count=?,"
            "inserted_count=?,error=?,formal_eligible_item_count=?,"
            "formal_eligible_evidence_ids_json=?,formal_eligible_lineage_json=?,"
            "cost_units=?,cursor_after=?,server_terminal_utc=? WHERE fetch_run_id=? "
            "AND status='running'",
            (received_utc, completed_utc, status, item_count, inserted_count,
             error, formal_eligible_item_count, eligible_ids_json,
             eligible_lineage_json, cost_units, cursor_after, server_terminal,
             fetch_run_id),
        )
        if result.rowcount != 1:
            raise ValueError(f"unknown or completed fetch run {fetch_run_id}")

    def finish_fetch(
        self, fetch_run_id: str, *, status: str, received_utc: float,
        completed_utc: float, item_count: int, inserted_count: int,
        error: str | None = None, cost_units: float = 0.0,
        cursor_after: float | None = None,
        formal_eligible_item_count: int | None = None,
        formal_eligible_evidence_ids: list[str] | None = None,
        formal_eligible_lineage: list[dict] | None = None,
    ) -> None:
        """Complete a receipt without storing rows (legacy/failure API).

        Successful collector code must use :meth:`complete_fetch` so response
        rows, item lineage, and the terminal receipt share one transaction.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self._finish_fetch_in_transaction(
                fetch_run_id, status=status, received_utc=received_utc,
                completed_utc=completed_utc, item_count=item_count,
                inserted_count=inserted_count, error=error, cost_units=cost_units,
                cursor_after=cursor_after,
                formal_eligible_item_count=formal_eligible_item_count,
                formal_eligible_evidence_ids=formal_eligible_evidence_ids,
                formal_eligible_lineage=formal_eligible_lineage,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def complete_fetch(
        self, fetch_run_id: str, *, rows: list[dict], status: str,
        received_utc: float, completed_utc: float, cost_units: float = 0.0,
        cursor_after: float | None = None,
        formal_eligible_item_count: int | None = None,
        formal_eligible_evidence_ids: list[str] | None = None,
        kind: str = "media",
    ) -> int:
        """Atomically persist a response, exact lineage, and terminal receipt."""
        if kind not in {"media", "odds", "request_receipt"}:
            raise ValueError("unknown fetch persistence kind")
        if not isinstance(rows, list):
            raise TypeError("fetch response rows must be a list")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self.conn.execute(
                "SELECT provider,status FROM fetch_runs WHERE fetch_run_id=?",
                (fetch_run_id,),
            ).fetchone()
            if current is None or current[1] != "running":
                raise ValueError(f"unknown or completed fetch run {fetch_run_id}")
            formal_lineage = None
            if kind == "media":
                items, formal_lineage = _build_fetch_item_lineage(
                    fetch_run_id, current[0], rows, received_utc,
                    formal_eligible_evidence_ids,
                )
                inserted = self._store_in_transaction(rows)
                self.conn.executemany(
                    "INSERT INTO fetch_run_items "
                    "(fetch_run_id,source,external_id,raw_content_id,evidence_id,"
                    "observed_utc,formal_eligible) VALUES "
                    "(:fetch_run_id,:source,:external_id,:raw_content_id,:evidence_id,"
                    ":observed_utc,:formal_eligible)",
                    items,
                )
            elif kind == "odds":
                if formal_eligible_item_count is not None \
                        or formal_eligible_evidence_ids is not None:
                    raise ValueError("odds receipts cannot claim formal media lineage")
                inserted = self._store_odds_in_transaction(rows)
            else:
                if formal_eligible_item_count is not None \
                        or formal_eligible_evidence_ids is not None:
                    raise ValueError("request-only receipts cannot claim media lineage")
                inserted = 0
            self._finish_fetch_in_transaction(
                fetch_run_id, status=status, received_utc=received_utc,
                completed_utc=completed_utc, item_count=len(rows),
                inserted_count=inserted, cost_units=cost_units,
                cursor_after=cursor_after,
                formal_eligible_item_count=formal_eligible_item_count,
                formal_eligible_evidence_ids=formal_eligible_evidence_ids,
                formal_eligible_lineage=formal_lineage,
            )
            self.conn.commit()
            return inserted
        except Exception:
            self.conn.rollback()
            raise

    def fetch_items(self, fetch_run_id: str) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute(
            "SELECT * FROM fetch_run_items WHERE fetch_run_id=? "
            "ORDER BY evidence_id,raw_content_id", (fetch_run_id,),
        ).fetchall()
        self.conn.row_factory = None
        return [dict(row) for row in rows]

    def fetch_runs(self, *, provider: str | None = None, limit: int = 100) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        if provider:
            rows = self.conn.execute(
                "SELECT * FROM fetch_runs WHERE provider=? "
                "ORDER BY started_utc DESC,fetch_run_id DESC LIMIT ?",
                (provider, max(1, limit)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM fetch_runs ORDER BY started_utc DESC,fetch_run_id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        self.conn.row_factory = None
        return [_attach_formal_evidence_ids(dict(row)) for row in rows]

    def coverage_report(
        self, cutoff_utc: float, required_source_groups: list[list[str]],
        *, max_age_seconds: float = 108000.0,
        expected_query_slots: list[QuerySlot] | None = None,
        allow_empty_query_slots: list[QuerySlot] | None = None,
        require_eligible_query_slots: list[QuerySlot] | None = None,
        require_lineage_query_slots: list[QuerySlot] | None = None,
        min_started_utc: float | None = None,
    ) -> dict:
        """Report provider-group and exact query-slot receipt coverage.

        ``expected_query_slots`` closes the ambiguity in provider-only coverage:
        one successful query cannot stand in for another query on the same
        provider. ``min_started_utc`` can constrain every slot to the current
        collector cycle rather than accepting an older success. Explicit
        ``allow_empty_query_slots`` still require a completed, fresh receipt;
        they are for queries (such as prediction-market topics) where no match
        is a valid observation rather than proof of collection failure.
        ``require_lineage_query_slots`` requires an exact canonical eligible-ID
        count/list while accepting ``0``/``[]`` as an observed absence;
        ``require_eligible_query_slots`` additionally requires at least one ID.
        """
        statuses: dict[str, dict | None] = {}
        for group in required_source_groups:
            for provider in group:
                row = self.conn.execute(
                    f"SELECT {','.join(FETCH_RUN_COLUMNS)} FROM fetch_runs "
                    "WHERE provider=? AND server_terminal_utc<=? "
                    "ORDER BY server_terminal_utc DESC,fetch_run_id DESC LIMIT 1",
                    (provider, cutoff_utc),
                ).fetchone()
                statuses[provider] = _attach_formal_evidence_ids(
                    dict(zip(FETCH_RUN_COLUMNS, row, strict=True))
                ) if row else None

        allow_empty = set(_normalize_query_slots(allow_empty_query_slots))
        require_eligible = set(_normalize_query_slots(require_eligible_query_slots))
        require_lineage = set(_normalize_query_slots(require_lineage_query_slots))
        query_statuses = []
        for provider, query_key in _normalize_query_slots(expected_query_slots):
            sql = (
                f"SELECT {','.join(FETCH_RUN_COLUMNS)} FROM fetch_runs "
                "WHERE provider=? AND query_key=? AND server_started_utc<=?"
            )
            params: list = [provider, query_key, cutoff_utc]
            if min_started_utc is not None:
                sql += " AND server_started_utc>=?"
                params.append(min_started_utc)
            row = self.conn.execute(
                sql
                + " ORDER BY server_started_utc DESC,fetch_run_id DESC LIMIT 1",
                params,
            ).fetchone()
            run = (
                _attach_formal_evidence_ids(
                    dict(zip(FETCH_RUN_COLUMNS, row, strict=True))
                )
                if row else None
            )
            query_statuses.append({
                "provider": provider,
                "query_key": query_key,
                "run": run,
                "allow_empty": (provider, query_key) in allow_empty,
                "require_eligible": (provider, query_key) in require_eligible,
                "require_lineage": (provider, query_key) in require_lineage,
            })
        return _coverage_result(
            cutoff_utc=cutoff_utc,
            required_source_groups=required_source_groups,
            source_statuses=statuses,
            query_statuses=query_statuses,
            max_age_seconds=max_age_seconds,
        )

    def daily_cost_units(self, provider: str, start_utc: float, end_utc: float) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_units),0) FROM fetch_runs WHERE provider=? "
            "AND started_utc>=? AND started_utc<?", (provider, start_utc, end_utc),
        ).fetchone()
        return float(row[0])

    def close(self):
        self.conn.close()


class SqlAlchemyMediaStore:
    """SQLAlchemy backend for networked databases (Postgres, etc.).

    Uses dialect-aware ``INSERT … ON CONFLICT DO NOTHING`` for dedup, which
    SQLite (3.24+) and Postgres both support. ``pool_pre_ping`` keeps a
    long-running poller resilient to idle connection drops on managed DBs.
    """

    def __init__(self, url: str, *, auto_migrate: bool | None = None):
        try:
            from sqlalchemy import (  # noqa: I001 — grouped for readability
                Column,
                Boolean,
                CheckConstraint,
                Double,
                ForeignKeyConstraint,
                Index,
                Integer,
                MetaData,
                String,
                Table,
                Text,
                UniqueConstraint,
                create_engine,
            )
        except ImportError as exc:
            raise RuntimeError(
                "The configured MEDIA_DB_URL needs SQLAlchemy and a database driver. "
                "Install the optional extra: pip install 'tradingagents[poller]'"
            ) from exc

        engine_options = {
            "pool_pre_ping": True,
            # Fly's proxy can terminate ten-minute-old connections during a
            # deployment drain. Recycle ordinary pooled connections before it.
            "pool_recycle": _POSTGRES_POOL_RECYCLE_SECONDS,
            "pool_timeout": 10,
        }
        if url.startswith(("postgresql://", "postgresql+")):
            # Bound every database wait so the only collector cannot hang
            # forever behind a dropped connection or an administrative row lock.
            engine_options["connect_args"] = _postgres_connect_args()
        self._database_url = url
        self.engine = create_engine(url, **engine_options)
        self.dialect = self.engine.dialect.name
        if self.dialect == "postgresql":
            _install_postgres_transaction_settings(self.engine)
        if self.dialect not in ("postgresql", "sqlite"):
            logger.warning("media store: dedup-on-conflict is verified for postgresql/"
                           "sqlite; %r may behave differently.", self.dialect)
        # PostgreSQL relations are schema-qualified at compile time. The pinned
        # search path remains a defense-in-depth check, not a routing mechanism.
        md = MetaData(schema="public" if self.dialect == "postgresql" else None)
        self.table = Table(
            "media_posts", md,
            Column("source", String, primary_key=True),
            Column("external_id", String, primary_key=True),
            Column("ticker", String, nullable=False),
            Column("subreddit", String), Column("author", String),
            Column("sentiment", String), Column("created_utc", Double),
            Column("title", String), Column("body", String),
            Column("fetched_utc", Double, nullable=False),
        )
        Index("idx_ticker_time", self.table.c.ticker, self.table.c.created_utc)
        self.labels = Table(
            "media_labels", md,
            Column("source", String, primary_key=True),
            Column("external_id", String, primary_key=True),
            Column("label", String, primary_key=True),
            Column("linked_utc", Double, nullable=False),
        )
        self.observations = Table(
            "media_observations", md,
            Column("source", String, primary_key=True),
            Column("external_id", String, primary_key=True),
            Column("observed_utc", Double, primary_key=True),
            Column("metadata_json", Text, nullable=False),
        )
        self.odds = Table(
            "macro_odds", md,
            Column("theme", String), Column("topic", String),
            Column("market_id", String, primary_key=True),
            Column("captured_utc", Double, primary_key=True),
            Column("question", String), Column("probability", Double),
            Column("volume", Double), Column("resolution_utc", Double),
        )
        self.state = Table(
            "poll_state", md,
            Column("key", String, primary_key=True), Column("value", Double),
        )
        self.cycles = Table(
            "collection_cycles", md,
            Column("collection_cycle_id", String, primary_key=True),
            Column("cycle_kind", String, nullable=False),
            Column("period_key", String, nullable=False),
            Column("protocol_id", String, nullable=False),
            Column("collector_semantics_id", String, nullable=False),
            Column("identity_json", Text, nullable=False),
            Column("started_utc", Double, nullable=False),
            Column("completed_utc", Double),
            Column("status", String, nullable=False),
            Column("manifest_id", String),
            Column("manifest_json", Text),
            Column("server_started_utc", Double),
            Column("server_terminal_utc", Double),
            Column("collector_build_id", String),
            CheckConstraint(
                "status IN ('running','complete','incomplete')",
                name="collection_cycles_status_valid",
            ),
            CheckConstraint(
                "(status='running' AND completed_utc IS NULL "
                "AND manifest_id IS NULL AND manifest_json IS NULL) OR "
                "(status IN ('complete','incomplete') AND completed_utc IS NOT NULL "
                "AND manifest_id IS NOT NULL AND manifest_json IS NOT NULL)",
                name="collection_cycles_terminal_shape",
            ),
        )
        self.cycle_slots = Table(
            "collection_cycle_slots", md,
            Column("collection_cycle_id", String, primary_key=True),
            Column("provider", String, primary_key=True),
            Column("query_key", String, primary_key=True),
            Column("slot_kind", String, nullable=False),
            Column("declared_utc", Double, nullable=False),
            ForeignKeyConstraint(
                ["collection_cycle_id"], ["collection_cycles.collection_cycle_id"],
                name="collection_cycle_slots_cycle_fk",
            ),
            CheckConstraint(
                "slot_kind IN ('static','dynamic')",
                name="collection_cycle_slots_kind_valid",
            ),
        )
        self.fetches = Table(
            "fetch_runs", md,
            Column("fetch_run_id", String, primary_key=True),
            Column("provider", String, nullable=False),
            Column("query_key", String, nullable=False),
            Column("started_utc", Double, nullable=False),
            Column("received_utc", Double), Column("completed_utc", Double),
            Column("status", String, nullable=False),
            Column("item_count", Integer), Column("inserted_count", Integer),
            Column("error", Text), Column("formal_eligible_item_count", Integer),
            Column("formal_eligible_evidence_ids_json", Text),
            Column("formal_eligible_lineage_json", Text),
            Column("cost_units", Double, nullable=False, default=0.0),
            Column("cursor_before", Double), Column("cursor_after", Double),
            Column("metadata_json", Text, nullable=False, default="{}"),
            Column("collection_cycle_id", String),
            Column("server_started_utc", Double),
            Column("server_terminal_utc", Double),
            Column("collector_build_id", String),
            ForeignKeyConstraint(
                ["collection_cycle_id"], ["collection_cycles.collection_cycle_id"],
                name="fetch_runs_collection_cycle_fk",
            ),
            UniqueConstraint(
                "collection_cycle_id", "provider", "query_key",
                name="fetch_runs_cycle_slot_unique",
            ),
        )
        Index(
            "idx_fetch_query_time", self.fetches.c.provider,
            self.fetches.c.query_key, self.fetches.c.started_utc,
        )
        self.fetch_items_table = Table(
            "fetch_run_items", md,
            Column("fetch_run_id", String, primary_key=True),
            Column("source", String, primary_key=True),
            Column("external_id", String, primary_key=True),
            Column("raw_content_id", String, nullable=False),
            Column("evidence_id", String, nullable=False),
            Column("observed_utc", Double, nullable=False),
            Column("formal_eligible", Boolean, nullable=False),
            UniqueConstraint(
                "fetch_run_id", "raw_content_id",
                name="fetch_run_items_run_raw_unique",
            ),
            ForeignKeyConstraint(
                ["fetch_run_id"], ["fetch_runs.fetch_run_id"],
                name="fetch_run_items_run_fk",
            ),
            ForeignKeyConstraint(
                ["source", "external_id"],
                ["media_posts.source", "media_posts.external_id"],
                name="fetch_run_items_media_fk",
            ),
            CheckConstraint(
                "raw_content_id ~ '^raw_[0-9a-f]{24}$'"
                if self.dialect == "postgresql"
                else "length(raw_content_id) = 28",
                name="fetch_run_items_raw_id_format",
            ),
            CheckConstraint(
                "evidence_id ~ '^evidence_[0-9a-f]{24}$'"
                if self.dialect == "postgresql"
                else "length(evidence_id) = 33",
                name="fetch_run_items_evidence_id_format",
            ),
        )
        if auto_migrate is not None and not isinstance(auto_migrate, bool):
            raise TypeError("auto_migrate must be a boolean or None")
        should_migrate = (
            os.getenv("MEDIA_AUTO_MIGRATE", "true").lower()
            in {"1", "true", "yes", "on"}
            if auto_migrate is None
            else auto_migrate
        )
        if should_migrate:
            md.create_all(self.engine)
            with self.engine.begin() as conn:
                if self.dialect == "sqlite":
                    conn.exec_driver_sql(
                        "INSERT OR IGNORE INTO media_labels "
                        "(source,external_id,label,linked_utc) "
                        "SELECT source,external_id,ticker,fetched_utc FROM media_posts"
                    )
                else:
                    conn.exec_driver_sql(
                        "INSERT INTO media_labels (source,external_id,label,linked_utc) "
                        "SELECT source,external_id,ticker,fetched_utc FROM media_posts "
                        "ON CONFLICT (source,external_id,label) DO NOTHING"
                    )

    def _insert_stmt(self, table, conflict_cols):
        if self.dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        return insert(table).on_conflict_do_nothing(index_elements=conflict_cols)

    def _upsert_in_transaction(self, conn, table, conflict_cols, rows: list[dict]) -> int:
        if not rows:
            return 0
        # psycopg may report ``rowcount == -1`` for INSERT ... ON CONFLICT,
        # even when the insert succeeds. RETURNING is reliable on both
        # PostgreSQL and modern SQLite: inserted rows return a key, conflicts
        # return no row.
        stmt = self._insert_stmt(table, conflict_cols).returning(
            table.c[conflict_cols[0]]
        )
        new = 0
        # Row-by-row in the caller's transaction; batches are intentionally small.
        for row in rows:
            if conn.execute(stmt, row).first() is not None:
                new += 1
        return new

    def _upsert(self, table, conflict_cols, rows: list[dict]) -> int:
        with self.engine.begin() as conn:
            return self._upsert_in_transaction(conn, table, conflict_cols, rows)

    def _store_in_transaction(self, conn, rows: list[dict]) -> int:
        from sqlalchemy import and_, select

        representatives = _validate_batch_media_coherence(rows)
        inserted = self._upsert_in_transaction(
            conn, self.table, ["source", "external_id"], rows
        )
        for row in representatives:
            # Re-read after INSERT ... ON CONFLICT. PostgreSQL waits for a
            # concurrent conflicting insert before returning no row, so this
            # check also closes the race between an optimistic pre-read and a
            # concurrent provenance revision.
            existing_row = conn.execute(select(self.table).where(and_(
                self.table.c.source == row.get("source"),
                self.table.c.external_id == row.get("external_id"),
            ))).mappings().first()
            if existing_row is not None:
                existing = dict(existing_row)
                observation = conn.execute(
                    select(self.observations.c.metadata_json).where(and_(
                        self.observations.c.source == row.get("source"),
                        self.observations.c.external_id == row.get("external_id"),
                    )).order_by(self.observations.c.observed_utc.desc()).limit(1)
                ).first()
                existing["metadata"] = json.loads(observation[0]) if observation else {}
                if _media_rows_conflict(existing, row):
                    raise ValueError(
                        "formal media identity changed immutable provenance"
                    )
        links = []
        for row in rows:
            labels = row.get("labels") or [row["ticker"]]
            links.extend({
                "source": row["source"], "external_id": row["external_id"],
                "label": label.upper(), "linked_utc": row["fetched_utc"],
            } for label in labels if label)
        self._upsert_in_transaction(
            conn, self.labels, ["source", "external_id", "label"], links
        )
        observations = [{
            "source": row["source"], "external_id": row["external_id"],
            "observed_utc": row["fetched_utc"],
            "metadata_json": json.dumps(row["metadata"], sort_keys=True),
        } for row in rows if row.get("metadata")]
        self._upsert_in_transaction(
            conn, self.observations,
            ["source", "external_id", "observed_utc"], observations,
        )
        return inserted

    def store(self, rows: list[dict]) -> int:
        with self.engine.begin() as conn:
            return self._store_in_transaction(conn, rows)

    def _store_odds_in_transaction(self, conn, rows: list[dict]) -> int:
        return self._upsert_in_transaction(
            conn, self.odds, ["market_id", "captured_utc"], rows
        )

    def store_odds(self, rows: list[dict]) -> int:
        with self.engine.begin() as conn:
            return self._store_odds_in_transaction(conn, rows)

    def stats(self) -> list[tuple]:
        from sqlalchemy import func, select
        t = self.table
        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(
                select(t.c.ticker, t.c.source, func.count(),
                       func.min(t.c.created_utc), func.max(t.c.created_utc))
                .group_by(t.c.ticker, t.c.source).order_by(t.c.ticker, t.c.source)
            ).all()]

    def window(self, ticker: str, end: str, days: int) -> list[dict]:
        from sqlalchemy import and_, exists, select
        lo, hi = _window_bounds(end, days)
        t = self.table
        label_exists = exists(select(self.labels.c.label).where(and_(
            self.labels.c.source == t.c.source,
            self.labels.c.external_id == t.c.external_id,
            self.labels.c.label == ticker.upper(),
            self.labels.c.linked_utc <= hi,
        )))
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(t).where(label_exists)
                .where(t.c.created_utc >= lo).where(t.c.created_utc <= hi)
                .order_by(t.c.created_utc)
            ).mappings().all()
            payload = [dict(r) for r in rows]
            self._attach_labels_sa(conn, payload, hi)
        return [
            row for row in payload
            if _matches_requested_labels(row, tickers=[ticker])
        ]

    def _attach_labels_sa(
        self, conn, rows: list[dict], cutoff_utc: float | None = None,
        *, strict_cutoff: bool = False,
    ) -> None:
        from sqlalchemy import and_, select
        attached = []
        for row in rows:
            receipt_clauses = [
                self.fetch_items_table.c.source == row["source"],
                self.fetch_items_table.c.external_id == row["external_id"],
                self.fetches.c.status == "success",
                self.fetches.c.server_terminal_utc.is_not(None),
            ]
            if cutoff_utc is not None:
                receipt_clauses.append(
                    self.fetches.c.server_terminal_utc < cutoff_utc
                    if strict_cutoff else self.fetches.c.server_terminal_utc <= cutoff_utc
                )
            receipts = conn.execute(
                select(
                    self.fetches.c.server_terminal_utc,
                    self.fetch_items_table.c.observed_utc,
                    self.fetches.c.metadata_json,
                    self.observations.c.metadata_json,
                ).select_from(
                    self.fetch_items_table.join(
                        self.fetches,
                        self.fetches.c.fetch_run_id
                        == self.fetch_items_table.c.fetch_run_id,
                    ).outerjoin(
                        self.observations,
                        and_(
                            self.observations.c.source
                            == self.fetch_items_table.c.source,
                            self.observations.c.external_id
                            == self.fetch_items_table.c.external_id,
                            self.observations.c.observed_utc
                            == self.fetch_items_table.c.observed_utc,
                        ),
                    )
                ).where(and_(*receipt_clauses)).order_by(
                    self.fetches.c.server_terminal_utc.desc(),
                    self.fetches.c.fetch_run_id.desc(),
                )
            ).all()
            if receipts:
                latest_observation = (
                    json.loads(receipts[0][3]) if receipts[0][3] else {}
                )
                row["metadata"] = (
                    latest_observation
                    if isinstance(latest_observation, dict) else {}
                )
                trusted_labels: set[str] = set()
                for receipt in receipts:
                    receipt_metadata = json.loads(receipt[2]) if receipt[2] else {}
                    observation_metadata = json.loads(receipt[3]) if receipt[3] else {}
                    for value in (
                        receipt_metadata.get("labels", [])
                        if isinstance(receipt_metadata, dict) else []
                    ):
                        if isinstance(value, str) and value.strip():
                            trusted_labels.add(value.strip().upper())
                    for value in (
                        observation_metadata.get("receipt_labels", [])
                        if isinstance(observation_metadata, dict) else []
                    ):
                        if isinstance(value, str) and value.strip():
                            trusted_labels.add(value.strip().upper())
                if not trusted_labels and row.get("source") == "trendnews" \
                        and isinstance(row.get("ticker"), str):
                    trusted_labels.add(row["ticker"].strip().upper())
                row["labels"] = sorted(trusted_labels)
                row["latest_observed_utc"] = float(receipts[0][0])
                row["latest_observed_utc_source"] = "server_terminal_utc"
                attached.append(row)
                continue

            lineage_exists = conn.execute(select(
                self.fetch_items_table.c.fetch_run_id
            ).where(and_(
                self.fetch_items_table.c.source == row["source"],
                self.fetch_items_table.c.external_id == row["external_id"],
            )).limit(1)).first()
            if lineage_exists is not None:
                continue

            clauses = [
                self.labels.c.source == row["source"],
                self.labels.c.external_id == row["external_id"],
            ]
            if cutoff_utc is not None:
                clauses.append(
                    self.labels.c.linked_utc < cutoff_utc
                    if strict_cutoff else self.labels.c.linked_utc <= cutoff_utc
                )
            labels = conn.execute(select(self.labels.c.label).where(and_(
                *clauses
            )).order_by(self.labels.c.label)).all()
            row["labels"] = [label[0] for label in labels]
            observation_clauses = [
                self.observations.c.source == row["source"],
                self.observations.c.external_id == row["external_id"],
            ]
            if cutoff_utc is not None:
                observation_clauses.append(
                    self.observations.c.observed_utc < cutoff_utc
                    if strict_cutoff else self.observations.c.observed_utc <= cutoff_utc
                )
            observation = conn.execute(
                select(
                    self.observations.c.metadata_json,
                    self.observations.c.observed_utc,
                ).where(and_(
                    *observation_clauses
                )).order_by(self.observations.c.observed_utc.desc()).limit(1)
            ).first()
            row["metadata"] = json.loads(observation[0]) if observation else {}
            row["latest_observed_utc"] = (
                float(observation[1]) if observation else row.get("fetched_utc")
            )
            row["latest_observed_utc_source"] = (
                "media_observation_utc" if observation else "fetched_utc"
            )
            attached.append(row)
        rows[:] = attached

    def history_asof(
        self,
        start: str,
        end: str,
        *,
        tickers: list[str] | None = None,
        ticker_prefixes: list[str] | None = None,
        sources: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict]:
        from sqlalchemy import and_, exists, or_, select

        lo, hi = _history_bounds(start, end)
        t = self.table
        stmt = (
            select(t)
            .where(t.c.created_utc >= lo)
            .where(t.c.created_utc < hi)
            .where(t.c.fetched_utc < hi)
        )
        identities = []
        if tickers:
            identities.append(exists(select(self.labels.c.label).where(and_(
                self.labels.c.source == t.c.source,
                self.labels.c.external_id == t.c.external_id,
                self.labels.c.label.in_([ticker.upper() for ticker in tickers]),
                self.labels.c.linked_utc < hi,
            ))))
        if ticker_prefixes:
            identities.extend(
                exists(select(self.labels.c.label).where(and_(
                    self.labels.c.source == t.c.source,
                    self.labels.c.external_id == t.c.external_id,
                    self.labels.c.label.like(prefix.upper() + "%"),
                    self.labels.c.linked_utc < hi,
                ))) for prefix in ticker_prefixes
            )
        if identities:
            stmt = stmt.where(or_(*identities))
        if sources:
            stmt = stmt.where(t.c.source.in_(sources))
        target = max(1, limit)
        stmt = stmt.order_by(
            t.c.created_utc.desc(), t.c.source, t.c.external_id
        )
        matched: list[dict] = []
        offset = 0
        with self.engine.connect() as conn:
            while len(matched) < target:
                rows = conn.execute(
                    stmt.limit(target).offset(offset)
                ).mappings().all()
                if not rows:
                    break
                payload = [dict(row) for row in rows]
                self._attach_labels_sa(conn, payload, hi, strict_cutoff=True)
                matched.extend(
                    row for row in payload
                    if _matches_requested_labels(
                        row, tickers=tickers, ticker_prefixes=ticker_prefixes
                    )
                )
                offset += len(rows)
                if len(rows) < target:
                    break
        return matched[:target]

    def odds_asof(self, end: str, themes: list[str] | None = None) -> list[dict]:
        from sqlalchemy import text
        params = {"hi": _midnight_epoch(end)}
        clause = ""
        if themes:
            marks = ",".join(f":t{i}" for i in range(len(themes)))
            clause = f"AND o.theme IN ({marks})"
            params.update({f"t{i}": t for i, t in enumerate(themes)})
        with self.engine.connect() as conn:
            rows = conn.execute(text(_odds_asof_sql(clause)), params).mappings().all()
        return [dict(r) for r in rows]

    def odds_stats(self) -> list[tuple]:
        from sqlalchemy import distinct, func, select
        o = self.odds
        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(
                select(o.c.theme, func.count(distinct(o.c.market_id)), func.count(),
                       func.min(o.c.captured_utc), func.max(o.c.captured_utc))
                .group_by(o.c.theme).order_by(o.c.theme)
            ).all()]

    def server_observed_utc(self) -> float:
        """Read the database clock used to bound one collector coverage cycle."""
        with self.engine.connect() as conn:
            return self._server_observed_utc(conn)

    def get_meta(self, key: str) -> float | None:
        from sqlalchemy import select
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.state.c.value).where(self.state.c.key == key)
            ).first()
        return row[0] if row else None

    def set_meta(self, key: str, value: float) -> None:
        if self.dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert

        statement = insert(self.state).values(key=key, value=value)
        statement = statement.on_conflict_do_update(
            index_elements=[self.state.c.key],
            set_={"value": statement.excluded.value},
        )
        with self.engine.begin() as conn:
            conn.execute(statement)

    def _collector_direct_database_url(self, direct_url: str | None = None):
        """Resolve a session-affine URL without ever rendering its credentials."""
        from sqlalchemy.engine import make_url

        if direct_url is not None and direct_url.strip():
            candidate = make_url(_normalize_pg_url(direct_url.strip()))
            if candidate.get_backend_name() != "postgresql":
                raise ValueError("collector direct database URL must use PostgreSQL")
            host = (candidate.host or "").lower().rstrip(".")
            if _FLY_MPG_POOL_HOST.fullmatch(host):
                raise ValueError(
                    "MEDIA_DB_DIRECT_URL must not use a Fly MPG pooler hostname"
                )
            return candidate

        candidate = make_url(self._database_url)
        if candidate.get_backend_name() != "postgresql":
            raise ValueError("collector singleton lease requires PostgreSQL")
        host = (candidate.host or "").lower().rstrip(".")
        pooled_match = _FLY_MPG_POOL_HOST.fullmatch(host)
        if pooled_match is not None:
            return candidate.set(
                host=f"direct.{pooled_match.group('cluster')}.flympg.net"
            )
        if _FLY_MPG_DIRECT_HOST.fullmatch(host) or host in _LOCAL_POSTGRES_HOSTS:
            return candidate
        raise ValueError(
            "collector lease needs MEDIA_DB_DIRECT_URL for this database host"
        )

    def _collector_direct_engine(self, direct_url: str | None = None):
        from sqlalchemy import create_engine

        resolved = self._collector_direct_database_url(direct_url)
        return create_engine(
            resolved,
            pool_pre_ping=True,
            pool_recycle=_POSTGRES_POOL_RECYCLE_SECONDS,
            pool_timeout=10,
            pool_size=2,
            max_overflow=0,
            connect_args=_postgres_connect_args(read_only=True),
        )

    @staticmethod
    def _session_affine_connection(engine):
        """Return one proven session-affine connection, or ``None``.

        Holding a transaction on a second client forces a transaction-pooling
        proxy to assign the first client another PostgreSQL backend. A direct or
        session-pooled endpoint keeps both backend PIDs stable.
        """
        from sqlalchemy import text

        primary = None
        secondary = None
        try:
            primary = engine.connect()
            first_pid = int(primary.execute(text(
                "SELECT pg_catalog.pg_backend_pid()"
            )).scalar_one())
            primary.commit()

            secondary = engine.connect()
            second_pid = int(secondary.execute(text(
                "SELECT pg_catalog.pg_backend_pid()"
            )).scalar_one())
            final_pid = int(primary.execute(text(
                "SELECT pg_catalog.pg_backend_pid()"
            )).scalar_one())
            primary.commit()
            if first_pid != final_pid or first_pid == second_pid:
                primary.close()
                primary = None
                return None
            return primary
        except Exception:
            if primary is not None:
                primary.close()
            return None
        finally:
            if secondary is not None:
                secondary.close()

    @staticmethod
    def _advisory_lock_contract_valid(primary, engine) -> bool:
        """Prove cross-session exclusion with an isolated, non-durable test lock."""
        from sqlalchemy import text

        contender = None
        primary_acquired = False
        try:
            primary_acquired = bool(primary.execute(text(
                "SELECT pg_catalog.pg_try_advisory_lock(:lock_id)"
            ), {"lock_id": _COLLECTOR_PREFLIGHT_ADVISORY_LOCK_ID}).scalar_one())
            primary.commit()
            if not primary_acquired:
                return False

            contender = engine.connect()
            contender_acquired = bool(contender.execute(text(
                "SELECT pg_catalog.pg_try_advisory_lock(:lock_id)"
            ), {"lock_id": _COLLECTOR_PREFLIGHT_ADVISORY_LOCK_ID}).scalar_one())
            if contender_acquired:
                # A re-entrant acquisition proves that both logical clients
                # reached one server session. Release every count before exit.
                for _ in range(3):
                    if not bool(contender.execute(text(
                        "SELECT pg_catalog.pg_advisory_unlock(:lock_id)"
                    ), {
                        "lock_id": _COLLECTOR_PREFLIGHT_ADVISORY_LOCK_ID,
                    }).scalar_one()):
                        break
                contender.commit()
                primary_acquired = False
                return False
            contender.commit()

            held = primary.execute(
                _advisory_lock_is_held_statement(),
                {"lock_id": _COLLECTOR_PREFLIGHT_ADVISORY_LOCK_ID},
            ).mappings().one()
            primary.commit()
            return bool(held["lock_held"])
        except Exception:
            return False
        finally:
            if contender is not None:
                contender.close()
            if primary_acquired:
                try:
                    primary.execute(text(
                        "SELECT pg_catalog.pg_advisory_unlock(:lock_id)"
                    ), {
                        "lock_id": _COLLECTOR_PREFLIGHT_ADVISORY_LOCK_ID,
                    })
                    primary.commit()
                except Exception:  # noqa: BLE001 - the probe must fail closed
                    pass

    def acquire_collector_lease(
        self,
        *,
        direct_url: str | None = None,
        heartbeat_interval_seconds: float = _COLLECTOR_LEASE_HEARTBEAT_SECONDS,
        on_loss=None,
    ) -> _PostgresCollectorLease | None:
        """Acquire and monitor the production singleton on a direct PG session."""
        if self.dialect != "postgresql":
            raise ValueError("collector singleton lease requires PostgreSQL")
        if (
            not math.isfinite(heartbeat_interval_seconds)
            or not 0 < heartbeat_interval_seconds <= 60
        ):
            raise ValueError("collector lease heartbeat must be in (0, 60] seconds")
        from sqlalchemy import text

        lease_engine = self._collector_direct_engine(direct_url)
        connection = self._session_affine_connection(lease_engine)
        if connection is None:
            lease_engine.dispose()
            raise RuntimeError(
                "collector singleton lease requires a session-affine direct connection"
            )
        try:
            acquired = bool(connection.execute(
                text("SELECT pg_catalog.pg_try_advisory_lock(:lock_id)"),
                {"lock_id": _COLLECTOR_ADVISORY_LOCK_ID},
            ).scalar_one())
            backend_pid = int(connection.execute(text(
                "SELECT pg_catalog.pg_backend_pid()"
            )).scalar_one())
            # End SQLAlchemy's implicit transaction. PostgreSQL session locks
            # remain held until explicit unlock or connection teardown.
            connection.commit()
            if not acquired:
                connection.close()
                lease_engine.dispose()
                return None
            return _PostgresCollectorLease(
                connection,
                lease_engine,
                _COLLECTOR_ADVISORY_LOCK_ID,
                backend_pid,
                heartbeat_interval_seconds=float(heartbeat_interval_seconds),
                on_loss=on_loss,
            )
        except Exception:
            connection.close()
            lease_engine.dispose()
            raise

    def collector_runtime_preflight(
        self, *, direct_url: str | None = None,
    ) -> dict:
        """Verify the restricted PostgreSQL collector contract without writing.

        The projection is deliberately limited to fixed booleans, counts, and
        diagnostic enums. It never returns connection details, role names, SQL
        text, or database error messages, so callers can safely log it.
        """
        if self.dialect != "postgresql":
            raise ValueError("collector runtime preflight requires PostgreSQL")

        from sqlalchemy import select, text

        collector_tables = (
            self.table,
            self.labels,
            self.observations,
            self.odds,
            self.state,
            self.cycles,
            self.cycle_slots,
            self.fetches,
            self.fetch_items_table,
        )
        mutable_table_names = frozenset({
            "fetch_runs", "poll_state", "collection_cycles",
        })
        required_triggers = {
            (
                "immutable_fetch_runs",
                "fetch_runs",
                "enforce_fetch_run_lifecycle",
            ): 31,
            (
                "immutable_fetch_run_items",
                "fetch_run_items",
                "enforce_fetch_run_item_lifecycle",
            ): 31,
            (
                "validate_fetch_run_content_completion",
                "fetch_runs",
                "enforce_fetch_run_content_completion",
            ): 19,
            (
                "immutable_collection_cycles",
                "collection_cycles",
                "enforce_collection_cycle_lifecycle",
            ): 31,
            (
                "immutable_collection_cycle_slots",
                "collection_cycle_slots",
                "enforce_collection_cycle_slot_lifecycle",
            ): 31,
            (
                "validate_fetch_run_cycle_binding",
                "fetch_runs",
                "enforce_fetch_run_cycle_binding",
            ): 7,
        }
        report = {
            "contract_version": 3,
            "postgresql": True,
            "connected": False,
            "database_clock_valid": False,
            "required_table_count": len(collector_tables),
            "selectable_table_count": 0,
            "resolved_relation_count": 0,
            "exact_column_table_count": 0,
            "required_column_count": sum(len(table.columns) for table in collector_tables),
            "selectable_column_count": 0,
            "authenticated_column_count": 0,
            "required_select_count": 0,
            "required_insert_count": 0,
            "required_update_count": 0,
            "forbidden_update_count": 0,
            "forbidden_delete_count": 0,
            "forbidden_truncate_count": 0,
            "schema_create_count": 0,
            "database_create_violation_count": 0,
            "row_security_violation_count": 0,
            "role_attribute_violation_count": 0,
            "required_trigger_count": len(required_triggers),
            "active_trigger_count": 0,
            "required_function_contract_count": len(_COLLECTOR_FUNCTION_CONTRACTS),
            "authenticated_function_contract_count": 0,
            "required_constraint_count": len(_COLLECTOR_CONSTRAINT_CONTRACTS),
            "active_constraint_count": 0,
            "required_index_count": 1,
            "active_index_count": 0,
            "search_path_valid": False,
            "relation_resolution_valid": False,
            "cycle_parent_lock_authority_valid": False,
            "direct_endpoint_resolved": False,
            "session_affinity_valid": False,
            "advisory_lock_valid": False,
            "tables_selectable": False,
            "column_contracts_valid": False,
            "privileges_valid": False,
            "role_attributes_valid": False,
            "integrity_triggers_valid": False,
            "function_contracts_valid": False,
            "constraints_valid": False,
            "indexes_valid": False,
            "ready": False,
            "failure_stage": None,
            "failure_type": None,
        }
        direct_engine = None
        direct_connection = None
        failure_stage = "primary_connection"
        try:
            with self.engine.connect() as conn:
                # This transaction makes the no-write preflight promise a
                # database-enforced property, not just a code-review claim.
                conn.execute(text("SET TRANSACTION READ ONLY"))
                report["connected"] = True
                failure_stage = "primary_contract"
                database_clock = self._server_observed_utc(conn)
                report["database_clock_valid"] = math.isfinite(database_clock)
                report["search_path_valid"] = bool(conn.execute(text(
                    "SELECT pg_catalog.current_schemas(false)::TEXT[] = "
                    "ARRAY['pg_catalog','public']::TEXT[]"
                )).scalar_one())

                for table in collector_tables:
                    columns = tuple(table.columns)
                    conn.execute(select(*columns).limit(0))
                    report["selectable_table_count"] += 1
                    report["selectable_column_count"] += len(columns)

                    resolved = bool(conn.execute(text(
                        "SELECT pg_catalog.to_regclass(CAST(:unqualified AS TEXT))::OID "
                        "IS NOT DISTINCT FROM "
                        "pg_catalog.to_regclass(CAST(:qualified AS TEXT))::OID"
                    ), {
                        "unqualified": table.name,
                        "qualified": f"public.{table.name}",
                    }).scalar_one())
                    report["resolved_relation_count"] += int(resolved)

                    actual_column_rows = conn.execute(text(
                        "SELECT attribute.attname, "
                        "attribute.atttypid::BIGINT AS type_oid, "
                        "attribute.atttypmod AS type_modifier, "
                        "attribute.attnotnull AS not_null, "
                        "attribute.atthasdef AS has_default, "
                        "attribute.attidentity AS identity_kind, "
                        "attribute.attgenerated AS generated_kind, "
                        "attribute.attcollation = type_record.typcollation "
                        "AS default_collation "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "JOIN pg_catalog.pg_type AS type_record "
                        "ON type_record.oid = attribute.atttypid "
                        "WHERE attribute.attrelid = "
                        "pg_catalog.to_regclass(CAST(:relation AS TEXT)) "
                        "AND attribute.attnum > 0 AND NOT attribute.attisdropped "
                        "ORDER BY attribute.attnum"
                    ), {
                        "relation": f"public.{table.name}",
                    }).mappings().all()
                    actual_columns = tuple(
                        row["attname"] for row in actual_column_rows
                    )
                    expected_columns = tuple(column.name for column in columns)
                    report["exact_column_table_count"] += int(
                        len(actual_columns) == len(expected_columns)
                        and set(actual_columns) == set(expected_columns)
                    )
                    actual_by_name = {
                        row["attname"]: row for row in actual_column_rows
                    }
                    for column in columns:
                        actual = actual_by_name.get(column.name)
                        report["authenticated_column_count"] += int(
                            actual is not None
                            and _collector_postgres_column_contract_valid(
                                column, actual
                            )
                        )

                    privileges = conn.execute(text(
                        "SELECT "
                        "pg_catalog.has_table_privilege(current_user, "
                        "CAST(:relation AS TEXT), 'SELECT') AS can_select, "
                        "pg_catalog.has_table_privilege(current_user, "
                        "CAST(:relation AS TEXT), 'INSERT') AS can_insert, "
                        "pg_catalog.has_table_privilege(current_user, "
                        "CAST(:relation AS TEXT), 'UPDATE') AS can_update"
                    ), {"relation": f"public.{table.name}"}).mappings().one()
                    report["required_select_count"] += int(
                        bool(privileges["can_select"])
                    )
                    report["required_insert_count"] += int(
                        bool(privileges["can_insert"])
                    )
                    if table.name in mutable_table_names:
                        report["required_update_count"] += int(
                            bool(privileges["can_update"])
                        )

                forbidden = conn.execute(text(
                    "SELECT "
                    "pg_catalog.count(*) FILTER (WHERE "
                    "pg_catalog.has_table_privilege(current_user, relation.oid, 'UPDATE') "
                    "AND NOT (namespace.nspname = 'public' AND relation.relname IN "
                    "('fetch_runs', 'poll_state', 'collection_cycles'))) "
                    "AS forbidden_update_count, "
                    "pg_catalog.count(*) FILTER (WHERE "
                    "pg_catalog.has_table_privilege(current_user, relation.oid, 'DELETE')) "
                    "AS forbidden_delete_count, "
                    "pg_catalog.count(*) FILTER (WHERE "
                    "pg_catalog.has_table_privilege(current_user, relation.oid, 'TRUNCATE')) "
                    "AS forbidden_truncate_count "
                    "FROM pg_catalog.pg_class AS relation "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid = relation.relnamespace "
                    "WHERE relation.relkind IN ('r', 'p', 'f') "
                    "AND namespace.nspname <> 'information_schema' "
                    "AND namespace.nspname !~ '^pg_'"
                )).mappings().one()
                for key in (
                    "forbidden_update_count",
                    "forbidden_delete_count",
                    "forbidden_truncate_count",
                ):
                    report[key] = int(forbidden[key])

                report["schema_create_count"] = int(conn.execute(text(
                    "SELECT pg_catalog.count(*) "
                    "FROM pg_catalog.pg_namespace AS namespace "
                    "WHERE namespace.nspname <> 'information_schema' "
                    "AND namespace.nspname !~ '^pg_' "
                    "AND pg_catalog.has_schema_privilege("
                    "current_user, namespace.oid, 'CREATE')"
                )).scalar_one())
                report["database_create_violation_count"] = int(bool(
                    conn.execute(text(
                        "SELECT pg_catalog.has_database_privilege("
                        "current_user, current_database(), 'CREATE')"
                    )).scalar_one()
                ))
                report["row_security_violation_count"] = int(conn.execute(text(
                    "SELECT pg_catalog.count(*) "
                    "FROM pg_catalog.pg_class AS relation "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'public' "
                    "AND relation.relname = ANY(CAST(:relations AS TEXT[])) "
                    "AND (relation.relrowsecurity OR relation.relforcerowsecurity)"
                ), {
                    "relations": [table.name for table in collector_tables],
                }).scalar_one())

                attributes = conn.execute(text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, "
                    "rolreplication "
                    "FROM pg_catalog.pg_roles WHERE rolname = current_user"
                )).mappings().first()
                report["role_attribute_violation_count"] = (
                    sum(bool(attributes[key]) for key in (
                        "rolsuper", "rolcreatedb", "rolcreaterole", "rolbypassrls",
                        "rolreplication",
                    ))
                    if attributes is not None
                    else 5
                )

                trigger_rows = conn.execute(text(
                    "SELECT trigger.tgname, relation.relname, procedure.proname, "
                    "trigger.tgenabled, trigger.tgtype "
                    "FROM pg_catalog.pg_trigger AS trigger "
                    "JOIN pg_catalog.pg_class AS relation "
                    "ON relation.oid = trigger.tgrelid "
                    "JOIN pg_catalog.pg_namespace AS relation_namespace "
                    "ON relation_namespace.oid = relation.relnamespace "
                    "JOIN pg_catalog.pg_proc AS procedure "
                    "ON procedure.oid = trigger.tgfoid "
                    "JOIN pg_catalog.pg_namespace AS procedure_namespace "
                    "ON procedure_namespace.oid = procedure.pronamespace "
                    "WHERE NOT trigger.tgisinternal "
                    "AND relation_namespace.nspname = 'public' "
                    "AND procedure_namespace.nspname = 'public'"
                )).mappings().all()
                report["active_trigger_count"] = sum(
                    1
                    for row in trigger_rows
                    if required_triggers.get((
                        row["tgname"], row["relname"], row["proname"],
                    )) == int(row["tgtype"])
                    and row["tgenabled"] in {"O", "A"}
                )

                for signature, expected in _COLLECTOR_FUNCTION_CONTRACTS.items():
                    expected_comment, expected_hash, expected_volatility = expected
                    function_row = conn.execute(text(
                        "SELECT pg_catalog.obj_description(procedure.oid, 'pg_proc') "
                        "AS contract_comment, "
                        "pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to("
                        "pg_catalog.regexp_replace(pg_catalog.btrim("
                        "procedure.prosrc, E' \\n\\r\\t'), E'[ \\t]+\\n', "
                        "E'\\n', 'g'), 'UTF8')), 'hex') AS source_hash, "
                        "procedure.provolatile, procedure.prosecdef, "
                        "procedure.proconfig, "
                        "pg_catalog.has_function_privilege("
                        "current_user, procedure.oid, 'EXECUTE') AS executable "
                        "FROM pg_catalog.pg_proc AS procedure "
                        "WHERE procedure.oid = "
                        "pg_catalog.to_regprocedure(CAST(:signature AS TEXT))"
                    ), {"signature": signature}).mappings().first()
                    report["authenticated_function_contract_count"] += int(
                        function_row is not None
                        and function_row["contract_comment"] == expected_comment
                        and function_row["source_hash"] == expected_hash
                        and function_row["provolatile"] == expected_volatility
                        and function_row["prosecdef"] is False
                        and list(function_row["proconfig"] or [])
                        == ["search_path=pg_catalog"]
                        and bool(function_row["executable"])
                    )

                constraint_rows = conn.execute(text(
                    "SELECT relation.relname, constraint_record.conname, "
                    "constraint_record.contype, constraint_record.convalidated, "
                    "referenced_relation.relname AS referenced_relation, "
                    "constraint_record.confupdtype, constraint_record.confdeltype, "
                    "constraint_record.confmatchtype, "
                    "pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to("
                    "pg_catalog.regexp_replace(pg_catalog.btrim("
                    "pg_catalog.pg_get_constraintdef(constraint_record.oid, false), "
                    "E' \\n\\r\\t'), E'[ \\t]+\\n', E'\\n', 'g'), "
                    "'UTF8')), 'hex') AS definition_hash, "
                    "ARRAY(SELECT attribute.attname::TEXT "
                    "FROM pg_catalog.unnest(constraint_record.conkey) "
                    "WITH ORDINALITY AS key_column(attnum, ordinal) "
                    "JOIN pg_catalog.pg_attribute AS attribute "
                    "ON attribute.attrelid = constraint_record.conrelid "
                    "AND attribute.attnum = key_column.attnum "
                    "ORDER BY key_column.ordinal) AS local_columns, "
                    "ARRAY(SELECT attribute.attname::TEXT "
                    "FROM pg_catalog.unnest(constraint_record.confkey) "
                    "WITH ORDINALITY AS key_column(attnum, ordinal) "
                    "JOIN pg_catalog.pg_attribute AS attribute "
                    "ON attribute.attrelid = constraint_record.confrelid "
                    "AND attribute.attnum = key_column.attnum "
                    "ORDER BY key_column.ordinal) AS referenced_columns "
                    "FROM pg_catalog.pg_constraint AS constraint_record "
                    "JOIN pg_catalog.pg_class AS relation "
                    "ON relation.oid = constraint_record.conrelid "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid = relation.relnamespace "
                    "LEFT JOIN pg_catalog.pg_class AS referenced_relation "
                    "ON referenced_relation.oid = constraint_record.confrelid "
                    "WHERE namespace.nspname = 'public'"
                )).mappings().all()
                for row in constraint_rows:
                    expected = _COLLECTOR_CONSTRAINT_CONTRACTS.get((
                        row["relname"], row["conname"],
                    ))
                    if expected is None:
                        continue
                    expected_type, expected_columns, expected_relation, expected_refs = (
                        expected
                    )
                    constraint_key = (row["relname"], row["conname"])
                    validation_valid = bool(row["convalidated"]) or (
                        constraint_key in _COLLECTOR_NOT_VALID_CONSTRAINTS
                    )
                    type_and_keys_valid = (
                        row["contype"] == expected_type
                        and validation_valid
                        and (
                            expected_columns is None
                            or tuple(row["local_columns"] or ()) == expected_columns
                        )
                        and row["referenced_relation"] == expected_relation
                        and tuple(row["referenced_columns"] or ()) == expected_refs
                    )
                    if expected_type == "f":
                        type_and_keys_valid = type_and_keys_valid and (
                            row["confupdtype"] == "a"
                            and row["confdeltype"] == "a"
                            and row["confmatchtype"] == "s"
                        )
                    if expected_type == "c":
                        type_and_keys_valid = type_and_keys_valid and (
                            row["definition_hash"]
                            in _COLLECTOR_CHECK_CONSTRAINT_HASHES.get(
                                constraint_key, frozenset()
                            )
                        )
                    report["active_constraint_count"] += int(type_and_keys_valid)

                index_row = conn.execute(text(
                    "SELECT index_record.indisvalid, index_record.indisready, "
                    "index_record.indislive, index_record.indisunique, "
                    "access_method.amname, index_record.indnkeyatts, "
                    "index_record.indnatts, "
                    "index_record.indoption::SMALLINT[] AS key_options, "
                    "index_record.indpred IS NULL AS unfiltered, "
                    "index_record.indexprs IS NULL AS unexpressed, "
                    "ARRAY(SELECT pg_catalog.pg_get_indexdef("
                    "index_record.indexrelid, ordinal, true) "
                    "FROM pg_catalog.generate_series("
                    "1, index_record.indnkeyatts) AS ordinal) AS key_definitions "
                    "FROM pg_catalog.pg_index AS index_record "
                    "JOIN pg_catalog.pg_class AS index_relation "
                    "ON index_relation.oid = index_record.indexrelid "
                    "JOIN pg_catalog.pg_class AS table_relation "
                    "ON table_relation.oid = index_record.indrelid "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid = table_relation.relnamespace "
                    "JOIN pg_catalog.pg_am AS access_method "
                    "ON access_method.oid = index_relation.relam "
                    "WHERE namespace.nspname = 'public' "
                    "AND table_relation.relname = 'fetch_runs' "
                    "AND index_relation.relname = 'idx_fetch_query_server_time'"
                )).mappings().first()
                report["active_index_count"] = int(
                    index_row is not None
                    and bool(index_row["indisvalid"])
                    and bool(index_row["indisready"])
                    and bool(index_row["indislive"])
                    and not bool(index_row["indisunique"])
                    and index_row["amname"] == "btree"
                    and int(index_row["indnkeyatts"]) == 4
                    and int(index_row["indnatts"]) == 4
                    and bool(index_row["unfiltered"])
                    and bool(index_row["unexpressed"])
                    and tuple(index_row["key_definitions"] or ()) == (
                        "provider",
                        "query_key",
                        "server_started_utc",
                        "server_terminal_utc",
                    )
                    and tuple(index_row["key_options"] or ()) == (0, 0, 3, 3)
                )

                # The exact DB trigger contract plus UPDATE authority on the
                # parent table is what permits the runtime's SELECT FOR UPDATE.
                # The preflight transaction itself remains database-read-only.
                report["cycle_parent_lock_authority_valid"] = (
                    report["required_update_count"] == len(mutable_table_names)
                    and report["resolved_relation_count"]
                    == report["required_table_count"]
                )

            failure_stage = "direct_resolution"
            direct_engine = self._collector_direct_engine(direct_url)
            report["direct_endpoint_resolved"] = True
            failure_stage = "session_affinity"
            direct_connection = self._session_affine_connection(direct_engine)
            report["session_affinity_valid"] = direct_connection is not None
            if direct_connection is not None:
                failure_stage = "advisory_lock"
                report["advisory_lock_valid"] = self._advisory_lock_contract_valid(
                    direct_connection, direct_engine
                )
        except Exception as exc:  # noqa: BLE001 - return only sanitized enums
            report["failure_stage"] = failure_stage
            report["failure_type"] = _collector_preflight_failure_type(exc)
        finally:
            if direct_connection is not None:
                with suppress(Exception):
                    direct_connection.close()
            if direct_engine is not None:
                with suppress(Exception):
                    direct_engine.dispose()

        report["tables_selectable"] = (
            report["selectable_table_count"] == report["required_table_count"]
            and report["selectable_column_count"] == report["required_column_count"]
            and report["exact_column_table_count"] == report["required_table_count"]
        )
        report["relation_resolution_valid"] = (
            report["resolved_relation_count"] == report["required_table_count"]
        )
        report["column_contracts_valid"] = (
            report["authenticated_column_count"]
            == report["required_column_count"]
        )
        report["privileges_valid"] = (
            report["required_select_count"] == report["required_table_count"]
            and report["required_insert_count"] == report["required_table_count"]
            and report["required_update_count"] == len(mutable_table_names)
            and report["forbidden_update_count"] == 0
            and report["forbidden_delete_count"] == 0
            and report["forbidden_truncate_count"] == 0
            and report["schema_create_count"] == 0
            and report["database_create_violation_count"] == 0
            and report["row_security_violation_count"] == 0
        )
        report["role_attributes_valid"] = (
            report["role_attribute_violation_count"] == 0
        )
        report["integrity_triggers_valid"] = (
            report["active_trigger_count"] == report["required_trigger_count"]
        )
        report["function_contracts_valid"] = (
            report["authenticated_function_contract_count"]
            == report["required_function_contract_count"]
        )
        report["constraints_valid"] = (
            report["active_constraint_count"] == report["required_constraint_count"]
        )
        report["indexes_valid"] = (
            report["active_index_count"] == report["required_index_count"]
        )
        report["ready"] = all((
            report["connected"],
            report["database_clock_valid"],
            report["search_path_valid"],
            report["relation_resolution_valid"],
            report["tables_selectable"],
            report["column_contracts_valid"],
            report["privileges_valid"],
            report["role_attributes_valid"],
            report["integrity_triggers_valid"],
            report["function_contracts_valid"],
            report["constraints_valid"],
            report["indexes_valid"],
            report["cycle_parent_lock_authority_valid"],
            report["direct_endpoint_resolved"],
            report["session_affinity_valid"],
            report["advisory_lock_valid"],
        ))
        if not report["ready"] and report["failure_stage"] is None:
            report["failure_stage"] = _collector_preflight_contract_failure_stage(
                report
            )
            report["failure_type"] = "ContractMismatch"
        return report

    def reserve_meta_budget(
        self, limits: dict[str, float], *, amount: float = 1.0
    ) -> dict[str, float] | None:
        """Atomically increment all counters, or none if any limit is exhausted."""
        from sqlalchemy import text

        limits, amount = _validated_meta_budget(limits, amount)
        if any(amount > limit for limit in limits.values()):
            return None
        statement = text(
            "INSERT INTO poll_state (key,value) VALUES (:key,:amount) "
            "ON CONFLICT(key) DO UPDATE SET value=poll_state.value+excluded.value "
            "WHERE poll_state.value>=0 "
            "AND poll_state.value+excluded.value<=:limit RETURNING value"
        )
        try:
            # PostgreSQL serializes conflicting upserts on each counter row. Keys
            # are sorted so multi-counter reservations take locks consistently.
            with self.engine.begin() as conn:
                reserved = {}
                for key in sorted(limits):
                    row = conn.execute(statement, {
                        "key": key, "amount": amount, "limit": limits[key],
                    }).first()
                    if row is None:
                        raise _MetaBudgetExceeded
                    reserved[key] = float(row[0])
                return reserved
        except _MetaBudgetExceeded:
            return None

    def _server_observed_utc(self, conn) -> float:
        """Read the database clock in the transaction that owns the row change."""
        from sqlalchemy import text

        expression = (
            "SELECT pg_catalog.date_part('epoch', pg_catalog.clock_timestamp())"
            if self.dialect == "postgresql"
            else "SELECT (julianday('now') - 2440587.5) * 86400.0"
        )
        observed = float(conn.execute(text(expression)).scalar_one())
        if not math.isfinite(observed):
            raise RuntimeError("database returned a non-finite observation time")
        return observed

    def start_collection_cycle(self, spec: dict, *, started_utc: float) -> str:
        from sqlalchemy.exc import IntegrityError

        cycle_id, identity, identity_json = _validated_collection_cycle_spec(spec)
        started = _finite_cycle_time(started_utc, "start time")
        build_id = _collector_build_id()
        try:
            with self.engine.begin() as conn:
                server_started = self._server_observed_utc(conn)
                conn.execute(self.cycles.insert().values(
                    collection_cycle_id=cycle_id,
                    cycle_kind=identity["cycle_kind"],
                    period_key=identity["period_key"],
                    protocol_id=identity["protocol_id"],
                    collector_semantics_id=identity["collector_semantics_id"],
                    identity_json=identity_json,
                    started_utc=started,
                    server_started_utc=server_started,
                    collector_build_id=build_id,
                    status="running",
                ))
                conn.execute(self.cycle_slots.insert(), [{
                    "collection_cycle_id": cycle_id,
                    "provider": slot["provider"],
                    "query_key": slot["query_key"],
                    "slot_kind": "static",
                    "declared_utc": started,
                } for slot in identity["expected_static_slots"]])
            return cycle_id
        except IntegrityError as exc:
            raise ValueError(
                "collection cycle already exists or violates its identity"
            ) from exc

    def declare_collection_cycle_slots(
        self, collection_cycle_id: str, slots: list[tuple[str, str]],
        *, declared_utc: float,
    ) -> None:
        from sqlalchemy import func, select
        from sqlalchemy.exc import IntegrityError

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        payloads = _cycle_slot_payloads(slots)
        declared = _finite_cycle_time(declared_utc, "slot declaration time")
        try:
            with self.engine.begin() as conn:
                cycle = conn.execute(select(self.cycles).where(
                    self.cycles.c.collection_cycle_id == cycle_id
                ).with_for_update()).mappings().first()
                if cycle is None or cycle["status"] != "running":
                    raise ValueError("dynamic slots require a running collection cycle")
                identity = json.loads(cycle["identity_json"])
                existing = conn.execute(select(func.count()).select_from(
                    self.cycle_slots
                ).where(
                    self.cycle_slots.c.collection_cycle_id == cycle_id,
                    self.cycle_slots.c.slot_kind == "dynamic",
                )).scalar_one()
                if existing or len(payloads) > identity["max_dynamic_slots"]:
                    raise ValueError(
                        "collection cycle dynamic slots were already declared or exceed cap"
                    )
                if declared < float(cycle["started_utc"]):
                    raise ValueError("collection cycle slot declaration precedes its start")
                if payloads:
                    conn.execute(self.cycle_slots.insert(), [{
                        "collection_cycle_id": cycle_id,
                        "provider": slot["provider"],
                        "query_key": slot["query_key"],
                        "slot_kind": "dynamic",
                        "declared_utc": declared,
                    } for slot in payloads])
        except IntegrityError as exc:
            raise ValueError("collection cycle dynamic slot declaration is invalid") from exc

    def finish_collection_cycle(
        self, collection_cycle_id: str, *, completed_utc: float,
    ) -> dict:
        from sqlalchemy import select, update
        from sqlalchemy.exc import IntegrityError

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        try:
            with self.engine.begin() as conn:
                cycle = conn.execute(select(self.cycles).where(
                    self.cycles.c.collection_cycle_id == cycle_id
                ).with_for_update()).mappings().first()
                if cycle is None or cycle["status"] != "running":
                    raise ValueError("unknown or terminal collection cycle")
                slots = [dict(row) for row in conn.execute(
                    select(self.cycle_slots).where(
                        self.cycle_slots.c.collection_cycle_id == cycle_id
                    )
                ).mappings()]
                receipts = [dict(row) for row in conn.execute(select(
                    self.fetches.c.fetch_run_id,
                    self.fetches.c.provider,
                    self.fetches.c.query_key,
                    self.fetches.c.status,
                    self.fetches.c.item_count,
                ).where(
                    self.fetches.c.collection_cycle_id == cycle_id
                )).mappings()]
                item_rows = [dict(row) for row in conn.execute(select(
                    self.fetch_items_table.c.fetch_run_id,
                    self.fetch_items_table.c.raw_content_id,
                    *[
                        self.table.c[column].label(f"stored_{column}")
                        for column in COLUMNS
                    ],
                    self.observations.c.metadata_json.label("metadata_json"),
                ).select_from(
                    self.fetch_items_table.join(
                        self.fetches,
                        self.fetches.c.fetch_run_id
                        == self.fetch_items_table.c.fetch_run_id,
                    ).join(
                        self.table,
                        (self.table.c.source == self.fetch_items_table.c.source)
                        & (
                            self.table.c.external_id
                            == self.fetch_items_table.c.external_id
                        ),
                    ).outerjoin(
                        self.observations,
                        (self.observations.c.source == self.fetch_items_table.c.source)
                        & (
                            self.observations.c.external_id
                            == self.fetch_items_table.c.external_id
                        )
                        & (
                            self.observations.c.observed_utc
                            == self.fetch_items_table.c.observed_utc
                        ),
                    )
                ).where(
                    self.fetches.c.collection_cycle_id == cycle_id
                )).mappings()]
                server_terminal = self._server_observed_utc(conn)
                terminal_cycle = {
                    **dict(cycle), "server_terminal_utc": server_terminal,
                }
                status, manifest_id, manifest_json, _ = _collection_cycle_manifest(
                    terminal_cycle, slots,
                    _cycle_receipts_with_lineage(
                        receipts, _verified_cycle_item_rows(item_rows)
                    ), completed_utc,
                )
                result = conn.execute(update(self.cycles).where(
                    self.cycles.c.collection_cycle_id == cycle_id,
                    self.cycles.c.status == "running",
                ).values(
                    completed_utc=completed_utc,
                    status=status,
                    manifest_id=manifest_id,
                    manifest_json=manifest_json,
                    server_terminal_utc=server_terminal,
                ))
                if result.rowcount != 1:
                    raise ValueError("unknown or terminal collection cycle")
            result = self.collection_cycle(cycle_id)
            if result is None:
                raise ValueError("terminal collection cycle disappeared")
            return result
        except IntegrityError as exc:
            raise ValueError("collection cycle terminal manifest is invalid") from exc

    def recover_collection_cycle(
        self, collection_cycle_id: str, *, recovered_utc: float,
        minimum_age_seconds: float,
    ) -> dict:
        """Seal a same-ID orphan without reissuing any external request."""
        from sqlalchemy import select

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        recovered = _finite_cycle_time(recovered_utc, "recovery time")
        minimum_age = _finite_cycle_time(
            minimum_age_seconds, "minimum recovery age"
        )
        if minimum_age <= 0:
            raise ValueError("collection cycle minimum recovery age must be positive")
        cycle = self.collection_cycle(cycle_id)
        if cycle is None:
            raise ValueError("unknown collection cycle")
        if cycle["status"] in {"complete", "incomplete"}:
            if not cycle.get("manifest_valid"):
                raise ValueError("terminal collection cycle manifest is invalid")
            return cycle
        server_started = cycle.get("server_started_utc")
        if not isinstance(server_started, (int, float)) \
                or isinstance(server_started, bool) \
                or not math.isfinite(float(server_started)):
            raise ValueError("running collection cycle lacks a server start observation")
        with self.engine.connect() as conn:
            observed_now = self._server_observed_utc(conn)
        if observed_now - float(server_started) < minimum_age:
            raise ValueError("running collection cycle is not stale enough to recover")
        with self.engine.connect() as conn:
            running = list(conn.execute(select(
                self.fetches.c.fetch_run_id,
                self.fetches.c.started_utc,
                self.fetches.c.cost_units,
            ).where(
                self.fetches.c.collection_cycle_id == cycle_id,
                self.fetches.c.status == "running",
            ).order_by(
                self.fetches.c.started_utc, self.fetches.c.fetch_run_id,
            )).mappings())
        for receipt in running:
            terminal_time = max(recovered, float(receipt["started_utc"]))
            self.finish_fetch(
                receipt["fetch_run_id"],
                status="failed",
                received_utc=terminal_time,
                completed_utc=terminal_time,
                item_count=0,
                inserted_count=0,
                error="collector_restart_recovery",
                cost_units=float(receipt["cost_units"]),
            )
        return self.finish_collection_cycle(
            cycle_id, completed_utc=max(recovered, float(cycle["started_utc"]))
        )

    def collection_cycle(self, collection_cycle_id: str) -> dict | None:
        from sqlalchemy import select

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        with self.engine.connect() as conn:
            row = conn.execute(select(self.cycles).where(
                self.cycles.c.collection_cycle_id == cycle_id
            )).mappings().first()
            slots = list(conn.execute(select(self.cycle_slots).where(
                self.cycle_slots.c.collection_cycle_id == cycle_id
            )).mappings()) if row else []
            receipts = list(conn.execute(select(
                self.fetches.c.fetch_run_id,
                self.fetches.c.provider,
                self.fetches.c.query_key,
                self.fetches.c.status,
                self.fetches.c.item_count,
            ).where(
                self.fetches.c.collection_cycle_id == cycle_id
            )).mappings()) if row else []
            item_rows = list(conn.execute(select(
                self.fetch_items_table.c.fetch_run_id,
                self.fetch_items_table.c.raw_content_id,
                *[
                    self.table.c[column].label(f"stored_{column}")
                    for column in COLUMNS
                ],
                self.observations.c.metadata_json.label("metadata_json"),
            ).select_from(
                self.fetch_items_table.join(
                    self.fetches,
                    self.fetches.c.fetch_run_id
                    == self.fetch_items_table.c.fetch_run_id,
                ).join(
                    self.table,
                    (self.table.c.source == self.fetch_items_table.c.source)
                    & (
                        self.table.c.external_id
                        == self.fetch_items_table.c.external_id
                    ),
                ).outerjoin(
                    self.observations,
                    (self.observations.c.source == self.fetch_items_table.c.source)
                    & (
                        self.observations.c.external_id
                        == self.fetch_items_table.c.external_id
                    )
                    & (
                        self.observations.c.observed_utc
                        == self.fetch_items_table.c.observed_utc
                    ),
                )
            ).where(
                self.fetches.c.collection_cycle_id == cycle_id
            )).mappings()) if row else []
        return _verify_collection_cycle_relations(
            dict(row), [dict(item) for item in slots],
            _cycle_receipts_with_lineage(
                [dict(item) for item in receipts],
                _verified_cycle_item_rows([dict(item) for item in item_rows]),
            ),
        ) if row else None

    def collection_cycle_identity_pairs(
        self, cycle_kind: str,
    ) -> list[tuple[str, str]]:
        """Return every immutable protocol/collector pair seen for one cycle kind."""
        from sqlalchemy import select

        kind = _validated_cycle_text(cycle_kind, "kind", max_bytes=64)
        if _COLLECTION_CYCLE_KIND.fullmatch(kind) is None:
            raise ValueError("collection cycle kind must be a lowercase slug")
        statement = select(
            self.cycles.c.protocol_id,
            self.cycles.c.collector_semantics_id,
        ).where(
            self.cycles.c.cycle_kind == kind
        ).distinct().order_by(
            self.cycles.c.protocol_id,
            self.cycles.c.collector_semantics_id,
        )
        with self.engine.connect() as conn:
            return [tuple(row) for row in conn.execute(statement).all()]

    def collection_cycle_slots(self, collection_cycle_id: str) -> list[dict]:
        from sqlalchemy import case, select

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        stmt = select(self.cycle_slots).where(
            self.cycle_slots.c.collection_cycle_id == cycle_id
        ).order_by(
            case((self.cycle_slots.c.slot_kind == "static", 0), else_=1),
            self.cycle_slots.c.provider,
            self.cycle_slots.c.query_key,
        )
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(stmt).mappings()]

    def collection_cycle_formal_lineage(
        self, collection_cycle_id: str, *, provider: str,
    ) -> list[dict]:
        """Return replayed formal item lineage for one complete cycle provider."""
        from sqlalchemy import select

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        cycle = self.collection_cycle(cycle_id)
        if cycle is None or cycle.get("status") != "complete" \
                or not cycle.get("manifest_valid"):
            raise ValueError("formal cycle lineage requires a valid complete cycle")
        with self.engine.connect() as conn:
            receipts = [dict(row) for row in conn.execute(
                select(self.fetches).where(
                    self.fetches.c.collection_cycle_id == cycle_id,
                    self.fetches.c.provider == provider,
                ).order_by(self.fetches.c.fetch_run_id)
            ).mappings()]
            items = [dict(row) for row in conn.execute(select(
                self.fetch_items_table.c.fetch_run_id,
                self.fetch_items_table.c.source,
                self.fetch_items_table.c.external_id,
                self.fetch_items_table.c.evidence_id,
                self.fetch_items_table.c.raw_content_id,
                self.fetch_items_table.c.formal_eligible,
            ).select_from(
                self.fetch_items_table.join(
                    self.fetches,
                    self.fetches.c.fetch_run_id
                    == self.fetch_items_table.c.fetch_run_id,
                )
            ).where(
                self.fetches.c.collection_cycle_id == cycle_id,
                self.fetches.c.provider == provider,
            ).order_by(
                self.fetch_items_table.c.evidence_id,
                self.fetch_items_table.c.raw_content_id,
                self.fetch_items_table.c.fetch_run_id,
            )).mappings()]
        return _verified_cycle_formal_lineage(receipts, items)

    def _validate_cycle_fetch_binding(
        self, conn, collection_cycle_id: str | None, provider: str,
        query_key: str, started_utc: float,
    ) -> str | None:
        from sqlalchemy import and_, select

        cycle_id = _validated_collection_cycle_id(collection_cycle_id)
        if cycle_id is None:
            return None
        # Slots are append-only; locking them would require unintended UPDATE authority.
        row = conn.execute(select(self.cycles.c.collection_cycle_id).select_from(
            self.cycles.join(
                self.cycle_slots,
                and_(
                    self.cycle_slots.c.collection_cycle_id
                    == self.cycles.c.collection_cycle_id,
                    self.cycle_slots.c.provider == provider,
                    self.cycle_slots.c.query_key == query_key,
                ),
            )
        ).where(and_(
            self.cycles.c.collection_cycle_id == cycle_id,
            self.cycles.c.status == "running",
            self.cycles.c.started_utc <= started_utc,
        )).with_for_update(of=self.cycles)).first()
        if row is None:
            raise ValueError("fetch receipt lacks a declared running cycle slot")
        return cycle_id

    def start_fetch(
        self, provider: str, query_key: str, started_utc: float,
        *, cursor_before: float | None = None, metadata: dict | None = None,
        collection_cycle_id: str | None = None,
    ) -> str:
        from sqlalchemy.exc import IntegrityError

        fetch_run_id = str(uuid.uuid4())
        build_id = _collector_build_id(metadata)
        try:
            with self.engine.begin() as conn:
                cycle_id = self._validate_cycle_fetch_binding(
                    conn, collection_cycle_id, provider, query_key, started_utc
                )
                conn.execute(self.fetches.insert().values(
                    fetch_run_id=fetch_run_id, provider=provider, query_key=query_key,
                    started_utc=started_utc, status="running", cost_units=0.0,
                    cursor_before=cursor_before,
                    metadata_json=json.dumps(metadata or {}, sort_keys=True),
                    collection_cycle_id=cycle_id,
                    server_started_utc=self._server_observed_utc(conn),
                    collector_build_id=build_id,
                ))
            return fetch_run_id
        except IntegrityError as exc:
            raise ValueError("fetch cycle slot already has a receipt or is invalid") from exc

    def start_budgeted_fetch(
        self, provider: str, query_key: str, started_utc: float,
        *, budget_limits: dict[str, float], budget_amount: float = 1.0,
        cursor_before: float | None = None, metadata: dict | None = None,
        collection_cycle_id: str | None = None,
    ) -> str | None:
        """Atomically reserve durable counters and append the running receipt."""
        from sqlalchemy import text

        limits, amount = _validated_meta_budget(budget_limits, budget_amount)
        if any(amount > limit for limit in limits.values()):
            return None
        if "budget_reservation" in (metadata or {}):
            raise ValueError("budget reservation metadata is store-owned")
        statement = text(
            "INSERT INTO poll_state (key,value) VALUES (:key,:amount) "
            "ON CONFLICT(key) DO UPDATE SET value=poll_state.value+excluded.value "
            "WHERE poll_state.value>=0 "
            "AND poll_state.value+excluded.value<=:limit RETURNING value"
        )
        fetch_run_id = str(uuid.uuid4())
        build_id = _collector_build_id(metadata)
        try:
            with self.engine.begin() as conn:
                cycle_id = self._validate_cycle_fetch_binding(
                    conn, collection_cycle_id, provider, query_key, started_utc
                )
                reserved = {}
                for key in sorted(limits):
                    row = conn.execute(statement, {
                        "key": key, "amount": amount, "limit": limits[key],
                    }).first()
                    if row is None:
                        raise _MetaBudgetExceeded
                    reserved[key] = float(row[0])
                receipt_metadata = {
                    **(metadata or {}),
                    "budget_reservation": {
                        "amount": amount,
                        "limits": limits,
                        "reserved": reserved,
                    },
                }
                conn.execute(self.fetches.insert().values(
                    fetch_run_id=fetch_run_id, provider=provider, query_key=query_key,
                    started_utc=started_utc, status="running", cost_units=amount,
                    cursor_before=cursor_before,
                    metadata_json=json.dumps(receipt_metadata, sort_keys=True),
                    collection_cycle_id=cycle_id,
                    server_started_utc=self._server_observed_utc(conn),
                    collector_build_id=build_id,
                ))
            return fetch_run_id
        except _MetaBudgetExceeded:
            return None
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError

            if isinstance(exc, IntegrityError):
                raise ValueError(
                    "fetch cycle slot already has a receipt or is invalid"
                ) from exc
            raise

    def _finish_fetch_in_transaction(
        self, conn, fetch_run_id: str, *, status: str, received_utc: float,
        completed_utc: float, item_count: int, inserted_count: int,
        error: str | None = None, cost_units: float = 0.0,
        cursor_after: float | None = None,
        formal_eligible_item_count: int | None = None,
        formal_eligible_evidence_ids: list[str] | None = None,
        formal_eligible_lineage: list[dict] | None = None,
    ) -> None:
        from sqlalchemy import and_, select, update

        eligible_ids_json = _encoded_formal_evidence_ids(
            formal_eligible_item_count,
            formal_eligible_evidence_ids,
            item_count=item_count,
        )
        eligible_lineage_json = _encoded_formal_lineage(
            formal_eligible_item_count,
            formal_eligible_evidence_ids,
            formal_eligible_lineage,
            item_count=item_count,
        ) if formal_eligible_lineage is not None else None
        current = conn.execute(
            select(
                self.fetches.c.provider,
                self.fetches.c.status,
                self.fetches.c.started_utc,
                self.fetches.c.cost_units,
            ).where(
                self.fetches.c.fetch_run_id == fetch_run_id
            ).with_for_update()
        ).first()
        if current is None or current.status != "running":
            raise ValueError(f"unknown or completed fetch run {fetch_run_id}")
        _validate_fetch_completion(
            started_utc=current.started_utc, status=status,
            received_utc=received_utc, completed_utc=completed_utc,
            item_count=item_count, inserted_count=inserted_count,
            error=error, cost_units=cost_units, cursor_after=cursor_after,
        )
        if float(cost_units) < float(current.cost_units):
            raise ValueError(
                "terminal cost units cannot erase a reserved paid request"
            )
        if current.provider in {"globalnews", "trendnews"} \
                and status in {"success", "empty"} and eligible_ids_json is None:
            raise ValueError("formal news receipts require exact eligible evidence IDs")
        result = conn.execute(update(self.fetches).where(and_(
            self.fetches.c.fetch_run_id == fetch_run_id,
            self.fetches.c.status == "running",
        )).values(
            received_utc=received_utc, completed_utc=completed_utc, status=status,
            item_count=item_count, inserted_count=inserted_count, error=error,
            formal_eligible_item_count=formal_eligible_item_count,
            formal_eligible_evidence_ids_json=eligible_ids_json,
            formal_eligible_lineage_json=eligible_lineage_json,
            cost_units=cost_units, cursor_after=cursor_after,
            server_terminal_utc=self._server_observed_utc(conn),
        ))
        if result.rowcount != 1:
            raise ValueError(f"unknown or completed fetch run {fetch_run_id}")

    def finish_fetch(
        self, fetch_run_id: str, *, status: str, received_utc: float,
        completed_utc: float, item_count: int, inserted_count: int,
        error: str | None = None, cost_units: float = 0.0,
        cursor_after: float | None = None,
        formal_eligible_item_count: int | None = None,
        formal_eligible_evidence_ids: list[str] | None = None,
        formal_eligible_lineage: list[dict] | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            self._finish_fetch_in_transaction(
                conn, fetch_run_id, status=status, received_utc=received_utc,
                completed_utc=completed_utc, item_count=item_count,
                inserted_count=inserted_count, error=error, cost_units=cost_units,
                cursor_after=cursor_after,
                formal_eligible_item_count=formal_eligible_item_count,
                formal_eligible_evidence_ids=formal_eligible_evidence_ids,
                formal_eligible_lineage=formal_eligible_lineage,
            )

    def complete_fetch(
        self, fetch_run_id: str, *, rows: list[dict], status: str,
        received_utc: float, completed_utc: float, cost_units: float = 0.0,
        cursor_after: float | None = None,
        formal_eligible_item_count: int | None = None,
        formal_eligible_evidence_ids: list[str] | None = None,
        kind: str = "media",
    ) -> int:
        """Atomically persist a response, exact lineage, and terminal receipt."""
        from sqlalchemy import select

        if kind not in {"media", "odds", "request_receipt"}:
            raise ValueError("unknown fetch persistence kind")
        if not isinstance(rows, list):
            raise TypeError("fetch response rows must be a list")
        with self.engine.begin() as conn:
            current = conn.execute(select(
                self.fetches.c.provider, self.fetches.c.status,
            ).where(
                self.fetches.c.fetch_run_id == fetch_run_id
            ).with_for_update()).first()
            if current is None or current.status != "running":
                raise ValueError(f"unknown or completed fetch run {fetch_run_id}")
            formal_lineage = None
            if kind == "media":
                items, formal_lineage = _build_fetch_item_lineage(
                    fetch_run_id, current.provider, rows, received_utc,
                    formal_eligible_evidence_ids,
                )
                inserted = self._store_in_transaction(conn, rows)
                if items:
                    conn.execute(self.fetch_items_table.insert(), items)
            elif kind == "odds":
                if formal_eligible_item_count is not None \
                        or formal_eligible_evidence_ids is not None:
                    raise ValueError("odds receipts cannot claim formal media lineage")
                inserted = self._store_odds_in_transaction(conn, rows)
            else:
                if formal_eligible_item_count is not None \
                        or formal_eligible_evidence_ids is not None:
                    raise ValueError("request-only receipts cannot claim media lineage")
                inserted = 0
            self._finish_fetch_in_transaction(
                conn, fetch_run_id, status=status, received_utc=received_utc,
                completed_utc=completed_utc, item_count=len(rows),
                inserted_count=inserted, cost_units=cost_units,
                cursor_after=cursor_after,
                formal_eligible_item_count=formal_eligible_item_count,
                formal_eligible_evidence_ids=formal_eligible_evidence_ids,
                formal_eligible_lineage=formal_lineage,
            )
            return inserted

    def fetch_items(self, fetch_run_id: str) -> list[dict]:
        from sqlalchemy import select

        stmt = select(self.fetch_items_table).where(
            self.fetch_items_table.c.fetch_run_id == fetch_run_id
        ).order_by(
            self.fetch_items_table.c.evidence_id,
            self.fetch_items_table.c.raw_content_id,
        )
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(stmt).mappings()]

    def fetch_runs(self, *, provider: str | None = None, limit: int = 100) -> list[dict]:
        from sqlalchemy import select
        stmt = select(self.fetches)
        if provider:
            stmt = stmt.where(self.fetches.c.provider == provider)
        stmt = stmt.order_by(
            self.fetches.c.started_utc.desc(), self.fetches.c.fetch_run_id.desc()
        ).limit(max(1, limit))
        with self.engine.connect() as conn:
            return [
                _attach_formal_evidence_ids(dict(row))
                for row in conn.execute(stmt).mappings()
            ]

    def coverage_report(
        self, cutoff_utc: float, required_source_groups: list[list[str]],
        *, max_age_seconds: float = 108000.0,
        expected_query_slots: list[QuerySlot] | None = None,
        allow_empty_query_slots: list[QuerySlot] | None = None,
        require_eligible_query_slots: list[QuerySlot] | None = None,
        require_lineage_query_slots: list[QuerySlot] | None = None,
        min_started_utc: float | None = None,
    ) -> dict:
        from sqlalchemy import and_, select
        statuses: dict[str, dict | None] = {}
        for group in required_source_groups:
            for provider in group:
                stmt = select(self.fetches).where(and_(
                    self.fetches.c.provider == provider,
                    self.fetches.c.server_terminal_utc <= cutoff_utc,
                )).order_by(
                    self.fetches.c.server_terminal_utc.desc(),
                    self.fetches.c.fetch_run_id.desc(),
                ).limit(1)
                with self.engine.connect() as conn:
                    row = conn.execute(stmt).mappings().first()
                statuses[provider] = dict(row) if row else None

        allow_empty = set(_normalize_query_slots(allow_empty_query_slots))
        require_eligible = set(_normalize_query_slots(require_eligible_query_slots))
        require_lineage = set(_normalize_query_slots(require_lineage_query_slots))
        query_statuses = []
        for provider, query_key in _normalize_query_slots(expected_query_slots):
            clauses = [
                self.fetches.c.provider == provider,
                self.fetches.c.query_key == query_key,
                self.fetches.c.server_started_utc <= cutoff_utc,
            ]
            if min_started_utc is not None:
                clauses.append(
                    self.fetches.c.server_started_utc >= min_started_utc
                )
            stmt = (
                select(self.fetches)
                .where(and_(*clauses))
                .order_by(
                    self.fetches.c.server_started_utc.desc(),
                    self.fetches.c.fetch_run_id.desc(),
                )
                .limit(1)
            )
            with self.engine.connect() as conn:
                row = conn.execute(stmt).mappings().first()
            query_statuses.append({
                "provider": provider,
                "query_key": query_key,
                "run": _attach_formal_evidence_ids(dict(row)) if row else None,
                "allow_empty": (provider, query_key) in allow_empty,
                "require_eligible": (provider, query_key) in require_eligible,
                "require_lineage": (provider, query_key) in require_lineage,
            })
        return _coverage_result(
            cutoff_utc=cutoff_utc,
            required_source_groups=required_source_groups,
            source_statuses=statuses,
            query_statuses=query_statuses,
            max_age_seconds=max_age_seconds,
        )

    def daily_cost_units(self, provider: str, start_utc: float, end_utc: float) -> float:
        from sqlalchemy import and_, func, select
        stmt = select(func.coalesce(func.sum(self.fetches.c.cost_units), 0.0)).where(and_(
            self.fetches.c.provider == provider,
            self.fetches.c.started_utc >= start_utc,
            self.fetches.c.started_utc < end_utc,
        ))
        with self.engine.connect() as conn:
            return float(conn.execute(stmt).scalar_one())

    def close(self):
        self.engine.dispose()
