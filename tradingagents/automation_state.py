import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tradingagents.allocation import OrderIntent


@dataclass(frozen=True)
class DecisionRecord:
    symbol: str
    rating: str
    analyzed_at: datetime
    trade_date: str
    report_path: str


@dataclass(frozen=True)
class PositionSnapshot:
    captured_at: datetime
    cash: Decimal
    positions: Mapping[str, Decimal]


@dataclass(frozen=True)
class UnresolvedOrderLookup:
    client_order_id: str | None
    ambiguous: bool


@dataclass(frozen=True)
class WheelReservationSnapshot:
    cycle_id: str
    captured_at: datetime
    put_collateral: Mapping[str, Decimal]
    covered_shares: Mapping[str, Decimal]


class AutomationState:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
              key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
              symbol TEXT PRIMARY KEY, rating TEXT NOT NULL, analyzed_at TEXT NOT NULL,
              trade_date TEXT NOT NULL, report_path TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS position_snapshots (
              id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, cash TEXT NOT NULL,
              positions_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_intents (
              cycle_id TEXT NOT NULL, symbol TEXT NOT NULL, created_at TEXT NOT NULL,
              side TEXT NOT NULL, notional TEXT NOT NULL, target_notional TEXT NOT NULL,
              status TEXT NOT NULL, client_order_id TEXT,
              PRIMARY KEY (cycle_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS option_order_intents (
              cycle_id TEXT NOT NULL, contract_symbol TEXT NOT NULL,
              underlying TEXT NOT NULL, created_at TEXT NOT NULL,
              position_intent TEXT NOT NULL, quantity TEXT NOT NULL,
              limit_price TEXT NOT NULL, status TEXT NOT NULL,
              client_order_id TEXT NOT NULL,
              PRIMARY KEY (cycle_id, contract_symbol)
            );
            CREATE TABLE IF NOT EXISTS wheel_phases (
              underlying TEXT PRIMARY KEY, phase TEXT NOT NULL,
              fingerprint TEXT NOT NULL, updated_at TEXT NOT NULL,
              stable_observations INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wheel_reservation_snapshots (
              id INTEGER PRIMARY KEY, cycle_id TEXT NOT NULL,
              captured_at TEXT NOT NULL, UNIQUE (cycle_id, captured_at)
            );
            CREATE TABLE IF NOT EXISTS wheel_reservations (
              snapshot_id INTEGER NOT NULL, underlying TEXT NOT NULL,
              kind TEXT NOT NULL, amount TEXT NOT NULL,
              PRIMARY KEY (snapshot_id, underlying, kind),
              FOREIGN KEY (snapshot_id) REFERENCES wheel_reservation_snapshots(id)
            );
            CREATE TABLE IF NOT EXISTS task_runs (
              task TEXT PRIMARY KEY, ran_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_outcomes (
              task TEXT PRIMARY KEY, ran_at TEXT NOT NULL,
              suppression_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS leases (
              task TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "AutomationState":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def get_batch_index(self) -> int:
        row = self._connection.execute(
            "SELECT value FROM metadata WHERE key = 'batch_index'"
        ).fetchone()
        return int(row[0]) if row else 0

    def advance_batch_index(self, next_index: int) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO metadata (key, value) VALUES ('batch_index', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(next_index),),
            )

    def save_decision(
        self,
        symbol: str,
        rating: str,
        analyzed_at: datetime,
        trade_date: str,
        report_path: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO decisions (symbol, rating, analyzed_at, trade_date, report_path)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                  rating = excluded.rating,
                  analyzed_at = excluded.analyzed_at,
                  trade_date = excluded.trade_date,
                  report_path = excluded.report_path
                """,
                (symbol, rating, _timestamp(analyzed_at), trade_date, report_path),
            )

    def fresh_decisions(
        self,
        symbols: tuple[str, ...],
        now: datetime,
        max_age_minutes: int,
    ) -> dict[str, DecisionRecord]:
        _timestamp(now)
        if not symbols:
            return {}
        placeholders = ", ".join("?" for _ in symbols)
        rows = self._connection.execute(
            f"""
            SELECT symbol, rating, analyzed_at, trade_date, report_path
            FROM decisions WHERE symbol IN ({placeholders})
            """,
            symbols,
        ).fetchall()
        cutoff = now - timedelta(minutes=max_age_minutes)
        records = {
            row[0]: DecisionRecord(
                symbol=row[0],
                rating=row[1],
                analyzed_at=datetime.fromisoformat(row[2]),
                trade_date=row[3],
                report_path=row[4],
            )
            for row in rows
        }
        return {
            symbol: records[symbol]
            for symbol in symbols
            if symbol in records and records[symbol].analyzed_at >= cutoff
        }

    def record_position_snapshot(
        self,
        captured_at: datetime,
        cash: Decimal,
        positions: Mapping[str, Decimal],
    ) -> None:
        positions_json = json.dumps(
            {symbol: str(notional) for symbol, notional in positions.items()},
            sort_keys=True,
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO position_snapshots (captured_at, cash, positions_json)
                VALUES (?, ?, ?)
                """,
                (_timestamp(captured_at), str(cash), positions_json),
            )

    def latest_position_snapshot(self) -> PositionSnapshot | None:
        row = self._connection.execute(
            """
            SELECT captured_at, cash, positions_json
            FROM position_snapshots ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        positions = {symbol: Decimal(notional) for symbol, notional in json.loads(row[2]).items()}
        return PositionSnapshot(
            captured_at=datetime.fromisoformat(row[0]),
            cash=Decimal(row[1]),
            positions=positions,
        )

    def record_order_intents(
        self,
        cycle_id: str,
        created_at: datetime,
        intents: Sequence[OrderIntent],
    ) -> None:
        timestamp = _timestamp(created_at)
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO order_intents (
                  cycle_id, symbol, created_at, side, notional, target_notional,
                  status, client_order_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)
                """,
                [
                    (
                        cycle_id,
                        intent.symbol,
                        timestamp,
                        intent.side,
                        str(intent.notional),
                        str(intent.target_notional),
                    )
                    for intent in intents
                ],
            )

    def order_intent_count(self, cycle_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM order_intents WHERE cycle_id = ?", (cycle_id,)
        ).fetchone()
        return row[0]

    def order_intent_statuses(self, cycle_id: str) -> dict[str, str]:
        rows = self._connection.execute(
            "SELECT symbol, status FROM order_intents WHERE cycle_id = ? ORDER BY symbol",
            (cycle_id,),
        ).fetchall()
        return dict(rows)

    def unresolved_client_order_id(self, intent: OrderIntent) -> str | None:
        lookup = self.lookup_unresolved_order_intent(intent)
        return lookup.client_order_id if lookup is not None and not lookup.ambiguous else None

    def lookup_unresolved_order_intent(
        self,
        intent: OrderIntent,
    ) -> UnresolvedOrderLookup | None:
        rows = self._connection.execute(
            """
            SELECT client_order_id FROM order_intents
            WHERE symbol = ? AND side = ? AND notional = ? AND target_notional = ?
              AND status IN ('pending', 'error')
            ORDER BY created_at DESC
            """,
            (intent.symbol, intent.side, str(intent.notional), str(intent.target_notional)),
        ).fetchall()
        return _unresolved_lookup(rows)

    def mark_order_intent_submitted(
        self,
        cycle_id: str,
        symbol: str,
        client_order_id: str,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE order_intents SET status = 'retired'
                WHERE client_order_id = ? AND status IN ('pending', 'error')
                  AND NOT (cycle_id = ? AND symbol = ?)
                """,
                (client_order_id, cycle_id, symbol),
            )
            self._connection.execute(
                """
                UPDATE order_intents SET status = 'submitted', client_order_id = ?
                WHERE cycle_id = ? AND symbol = ?
                """,
                (client_order_id, cycle_id, symbol),
            )

    def update_order_intent(
        self,
        cycle_id: str,
        symbol: str,
        status: str,
        client_order_id: str | None = None,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE order_intents SET status = ?,
                  client_order_id = COALESCE(?, client_order_id)
                WHERE cycle_id = ? AND symbol = ?
                """,
                (status, client_order_id, cycle_id, symbol),
            )

    def record_option_intent(
        self,
        cycle_id: str,
        created_at: datetime,
        contract_symbol: str,
        underlying: str,
        position_intent: str,
        quantity: Decimal,
        limit_price: Decimal,
        client_order_id: str,
    ) -> None:
        _required_option_text(cycle_id, "cycle ID")
        _required_option_text(contract_symbol, "contract symbol")
        _required_option_text(underlying, "underlying")
        _validate_position_intent(position_intent)
        _positive_option_decimal(quantity, "option quantity", whole=True)
        _positive_option_decimal(limit_price, "option limit price")
        _required_option_text(client_order_id, "client order ID")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO option_order_intents (
                  cycle_id, contract_symbol, underlying, created_at, position_intent,
                  quantity, limit_price, status, client_order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    cycle_id,
                    contract_symbol,
                    underlying,
                    _timestamp(created_at),
                    position_intent,
                    str(quantity),
                    str(limit_price),
                    client_order_id,
                ),
            )

    def update_option_intent(
        self,
        cycle_id: str,
        contract_symbol: str,
        status: str,
        client_order_id: str | None = None,
    ) -> None:
        _required_option_text(cycle_id, "cycle ID")
        _required_option_text(contract_symbol, "contract symbol")
        _validate_option_intent_status(status)
        if client_order_id is not None:
            _required_option_text(client_order_id, "client order ID")
        with self._connection:
            if status == "submitted" and client_order_id is not None:
                self._connection.execute(
                    """
                    UPDATE option_order_intents SET status = 'retired'
                    WHERE client_order_id = ? AND status IN ('pending', 'error')
                      AND NOT (cycle_id = ? AND contract_symbol = ?)
                    """,
                    (client_order_id, cycle_id, contract_symbol),
                )
            self._connection.execute(
                """
                UPDATE option_order_intents SET
                  status = ?, client_order_id = COALESCE(?, client_order_id)
                WHERE cycle_id = ? AND contract_symbol = ?
                """,
                (status, client_order_id, cycle_id, contract_symbol),
            )

    def unresolved_option_client_order_id(
        self,
        contract_symbol: str,
        position_intent: str,
        quantity: Decimal,
        limit_price: Decimal,
    ) -> str | None:
        lookup = self.lookup_unresolved_option_intent(
            contract_symbol, position_intent, quantity, limit_price
        )
        return lookup.client_order_id if lookup is not None and not lookup.ambiguous else None

    def lookup_unresolved_option_intent(
        self,
        contract_symbol: str,
        position_intent: str,
        quantity: Decimal,
        limit_price: Decimal,
    ) -> UnresolvedOrderLookup | None:
        _required_option_text(contract_symbol, "contract symbol")
        _validate_position_intent(position_intent)
        _positive_option_decimal(quantity, "option quantity", whole=True)
        _positive_option_decimal(limit_price, "option limit price")
        rows = self._connection.execute(
            """
            SELECT client_order_id FROM option_order_intents
            WHERE contract_symbol = ? AND position_intent = ? AND quantity = ? AND limit_price = ?
              AND status IN ('pending', 'error')
            ORDER BY created_at DESC
            """,
            (contract_symbol, position_intent, str(quantity), str(limit_price)),
        ).fetchall()
        return _unresolved_lookup(rows)

    def record_wheel_reservations(
        self,
        cycle_id: str,
        captured_at: datetime,
        put_collateral: Mapping[str, Decimal],
        covered_shares: Mapping[str, Decimal],
    ) -> None:
        _required_option_text(cycle_id, "cycle ID")
        timestamp = _timestamp(captured_at)
        rows = []
        for kind, reservations in (
            ("put_collateral", put_collateral),
            ("covered_shares", covered_shares),
        ):
            if not isinstance(reservations, Mapping):
                raise ValueError("wheel reservations must be mappings")
            for underlying, amount in reservations.items():
                _required_option_text(underlying, "wheel reservation underlying")
                _nonnegative_decimal(amount, "wheel reservation amount")
                rows.append((underlying, kind, str(amount)))

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO wheel_reservation_snapshots (cycle_id, captured_at)
                VALUES (?, ?)
                ON CONFLICT(cycle_id, captured_at) DO NOTHING
                """,
                (cycle_id, timestamp),
            )
            snapshot_id = self._connection.execute(
                """
                SELECT id FROM wheel_reservation_snapshots
                WHERE cycle_id = ? AND captured_at = ?
                """,
                (cycle_id, timestamp),
            ).fetchone()[0]
            self._connection.execute(
                "DELETE FROM wheel_reservations WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            self._connection.executemany(
                """
                INSERT INTO wheel_reservations (snapshot_id, underlying, kind, amount)
                VALUES (?, ?, ?, ?)
                """,
                [(snapshot_id, underlying, kind, amount) for underlying, kind, amount in rows],
            )

    def latest_wheel_reservations(self) -> WheelReservationSnapshot | None:
        row = self._connection.execute(
            """
            SELECT id, cycle_id, captured_at FROM wheel_reservation_snapshots
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        reservations = self._connection.execute(
            """
            SELECT underlying, kind, amount FROM wheel_reservations
            WHERE snapshot_id = ? ORDER BY underlying, kind
            """,
            (row[0],),
        ).fetchall()
        put_collateral = {
            underlying: Decimal(amount)
            for underlying, kind, amount in reservations
            if kind == "put_collateral"
        }
        covered_shares = {
            underlying: Decimal(amount)
            for underlying, kind, amount in reservations
            if kind == "covered_shares"
        }
        return WheelReservationSnapshot(
            cycle_id=row[1],
            captured_at=datetime.fromisoformat(row[2]),
            put_collateral=put_collateral,
            covered_shares=covered_shares,
        )

    def last_option_entry_date(self) -> date | None:
        row = self._connection.execute(
            "SELECT value FROM metadata WHERE key = 'last_option_entry_date'"
        ).fetchone()
        return date.fromisoformat(row[0]) if row else None

    def mark_option_entry_date(self, entry_date: date) -> None:
        if type(entry_date) is not date:
            raise ValueError("option entry date must be a date")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO metadata (key, value) VALUES ('last_option_entry_date', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (entry_date.isoformat(),),
            )

    def observe_wheel_phase(
        self,
        underlying: str,
        phase: str,
        fingerprint: str,
        observed_at: datetime,
    ) -> None:
        _required_option_text(underlying, "underlying")
        _required_option_text(fingerprint, "wheel fingerprint")
        if phase not in {"short_put", "short_call", "long_shares", "empty"}:
            raise ValueError("unsupported wheel phase")
        timestamp = _timestamp(observed_at)
        row = self._connection.execute(
            """
            SELECT phase, fingerprint, updated_at, stable_observations
            FROM wheel_phases WHERE underlying = ?
            """,
            (underlying,),
        ).fetchone()
        if row is not None and observed_at < datetime.fromisoformat(row[2]):
            raise ValueError("wheel phase observations must not move backwards")

        if phase == "empty" and row is not None and row[0] in {"short_put", "short_call", "settling"}:
            prior_phase, prior_fingerprint, prior_updated_at, prior_stability = row
            if prior_phase == "settling" and fingerprint == prior_fingerprint:
                elapsed = observed_at - datetime.fromisoformat(prior_updated_at)
                if elapsed >= timedelta(minutes=15):
                    next_phase = "put_ready" if prior_stability + 1 >= 2 else "settling"
                    stability = prior_stability + 1
                else:
                    next_phase = "settling"
                    stability = 1
            else:
                next_phase = "settling"
                stability = 1
        elif phase == "empty":
            next_phase = "put_ready"
            stability = 0
        else:
            next_phase = phase
            stability = 0

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO wheel_phases (
                  underlying, phase, fingerprint, updated_at, stable_observations
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(underlying) DO UPDATE SET
                  phase = excluded.phase,
                  fingerprint = excluded.fingerprint,
                  updated_at = excluded.updated_at,
                  stable_observations = excluded.stable_observations
                """,
                (underlying, next_phase, fingerprint, timestamp, stability),
            )

    def wheel_phase(self, underlying: str) -> str:
        _required_option_text(underlying, "underlying")
        row = self._connection.execute(
            "SELECT phase FROM wheel_phases WHERE underlying = ?", (underlying,)
        ).fetchone()
        return row[0] if row else "put_ready"

    def mark_task_run(self, task: str, ran_at: datetime) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO task_runs (task, ran_at) VALUES (?, ?)
                ON CONFLICT(task) DO UPDATE SET ran_at = excluded.ran_at
                """,
                (task, _timestamp(ran_at)),
            )

    def last_task_run(self, task: str) -> datetime | None:
        row = self._connection.execute(
            "SELECT ran_at FROM task_runs WHERE task = ?", (task,)
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def last_task_outcome(self, task: str) -> tuple[datetime, str | None] | None:
        row = self._connection.execute(
            "SELECT ran_at, suppression_reason FROM task_outcomes WHERE task = ?",
            (task,),
        ).fetchone()
        return (datetime.fromisoformat(row[0]), row[1]) if row else None

    def try_acquire_lease(
        self,
        task: str,
        owner: str,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        _timestamp(now)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT expires_at FROM leases WHERE task = ?", (task,)
            ).fetchone()
            if row is not None and datetime.fromisoformat(row[0]) > now:
                self._connection.rollback()
                return False
            expires_at = now + timedelta(seconds=ttl_seconds)
            self._connection.execute(
                """
                INSERT INTO leases (task, owner, expires_at) VALUES (?, ?, ?)
                ON CONFLICT(task) DO UPDATE SET
                  owner = excluded.owner,
                  expires_at = excluded.expires_at
                """,
                (task, owner, _timestamp(expires_at)),
            )
            self._connection.commit()
            return True
        except Exception:
            self._connection.rollback()
            raise

    def renew_lease(
        self,
        task: str,
        owner: str,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        _timestamp(now)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT owner, expires_at FROM leases WHERE task = ?", (task,)
            ).fetchone()
            if row is None or row[0] != owner or datetime.fromisoformat(row[1]) <= now:
                self._connection.rollback()
                return False
            expires_at = now + timedelta(seconds=ttl_seconds)
            self._connection.execute(
                "UPDATE leases SET expires_at = ? WHERE task = ? AND owner = ?",
                (_timestamp(expires_at), task, owner),
            )
            self._connection.commit()
            return True
        except Exception:
            self._connection.rollback()
            raise

    def release_lease(self, task: str, owner: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM leases WHERE task = ? AND owner = ?",
                (task, owner),
            )
        return cursor.rowcount == 1

    def complete_task_run(
        self,
        task: str,
        owner: str,
        ran_at: datetime,
        completed_at: datetime,
        suppression_reason: str | None = None,
    ) -> bool:
        ran_at_text = _timestamp(ran_at)
        _timestamp(completed_at)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT owner, expires_at FROM leases WHERE task = ?", (task,)
            ).fetchone()
            if row is None or row[0] != owner or datetime.fromisoformat(row[1]) <= completed_at:
                self._connection.rollback()
                return False
            self._connection.execute(
                """
                INSERT INTO task_runs (task, ran_at) VALUES (?, ?)
                ON CONFLICT(task) DO UPDATE SET ran_at = excluded.ran_at
                """,
                (task, ran_at_text),
            )
            self._connection.execute(
                """
                INSERT INTO task_outcomes (task, ran_at, suppression_reason)
                VALUES (?, ?, ?)
                ON CONFLICT(task) DO UPDATE SET
                  ran_at = excluded.ran_at,
                  suppression_reason = excluded.suppression_reason
                """,
                (task, ran_at_text, suppression_reason),
            )
            cursor = self._connection.execute(
                "DELETE FROM leases WHERE task = ? AND owner = ?",
                (task, owner),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                return False
            self._connection.commit()
            return True
        except Exception:
            self._connection.rollback()
            raise


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def _required_option_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _positive_option_decimal(value: Decimal, label: str, whole: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{label} must be positive")
    if whole and value != value.to_integral():
        raise ValueError(f"{label} must be a whole number")


def _nonnegative_decimal(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _unresolved_lookup(rows: Sequence[tuple[str | None]]) -> UnresolvedOrderLookup | None:
    if not rows:
        return None
    client_order_ids = {row[0] for row in rows if row[0]}
    ambiguous = any(not row[0] for row in rows) or len(client_order_ids) != 1
    client_order_id = next(iter(client_order_ids)) if not ambiguous else None
    return UnresolvedOrderLookup(client_order_id=client_order_id, ambiguous=ambiguous)


def _validate_position_intent(position_intent: str) -> None:
    if position_intent not in {
        "buy_to_open",
        "buy_to_close",
        "sell_to_open",
        "sell_to_close",
    }:
        raise ValueError("unsupported option position intent")


def _validate_option_intent_status(status: str) -> None:
    if status not in {"pending", "planned", "submitted", "error", "retired"}:
        raise ValueError("unsupported option intent status")
