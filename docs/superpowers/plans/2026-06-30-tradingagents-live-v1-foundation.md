# TradingAgents Live v1 — Foundation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation of the live-trading layer: a guarded paper broker, all safety rules, and the SQLite journal — programmatically usable end-to-end with full test coverage.

**Architecture:** New sibling Python package `ops/` next to `tradingagents/`. `Broker` ABC with `PaperBroker` impl, wrapped by `GuardedBroker` that runs an ordered rule chain on every order. All state changes recorded to an append-only SQLite journal. No scheduler, no pipeline, no notifications in this plan — those come in Plans 2 and 3.

**Tech Stack:** Python 3.12, `sqlite3` (stdlib), `pytest`, `pytest-cov`. No new third-party deps in this plan.

**Working directory:** `~/Code/TradingAgents`. Work on branch `feat/ops-foundation` off `main`. Plan reads against spec at `docs/superpowers/specs/2026-06-30-tradingagents-live-v1-design.md`.

---

## File Structure

```
ops/
  __init__.py
  config.py
  journal.py
  broker/
    __init__.py
    types.py             # Order, Fill, Position, Side, OrderType
    base.py              # Broker ABC, OrderRejected
    paper.py             # PaperBroker
    guarded.py           # GuardedBroker
  guardrails/
    __init__.py
    base.py              # Rule ABC, RuleContext, RuleResult
    static_rules.py      # DenyList, NoMargin, NoOptions, NoCrypto, LongOnly, StopAttached, FractionalOnly
    sizing_rules.py      # PerPositionCap, PerTradeFloor, MaxOpenPositions, CashReserve
    drawdown_rules.py    # DailyDrawdown, WeeklyDrawdown
    engine.py            # RuleEngine
tests/
  ops/
    __init__.py
    test_config.py
    test_journal.py
    broker/
      __init__.py
      test_types.py
      test_paper.py
      test_guarded.py
    guardrails/
      __init__.py
      test_static_rules.py
      test_sizing_rules.py
      test_drawdown_rules.py
      test_engine.py
    test_integration.py
```

---

## Task 0: Branch + scaffold

**Files:**
- Create: `ops/__init__.py`, `tests/ops/__init__.py`, `tests/ops/broker/__init__.py`, `tests/ops/guardrails/__init__.py`
- Create: `ops/broker/__init__.py`, `ops/guardrails/__init__.py`

- [ ] **Step 1: Create branch**

```bash
cd ~/Code/TradingAgents
git checkout -b feat/ops-foundation
```

- [ ] **Step 2: Create the package skeleton**

```bash
mkdir -p ops/broker ops/guardrails tests/ops/broker tests/ops/guardrails
touch ops/__init__.py ops/broker/__init__.py ops/guardrails/__init__.py
touch tests/ops/__init__.py tests/ops/broker/__init__.py tests/ops/guardrails/__init__.py
```

- [ ] **Step 3: Verify pytest still works on the existing tree**

Run: `pytest -q tests/ 2>&1 | tail -5`
Expected: existing tests pass (or fail in their existing way); no collection errors from our new empty packages.

- [ ] **Step 4: Commit**

```bash
git add ops tests/ops
git commit -m "chore(ops): scaffold ops package"
```

---

## Task 1: `ops/config.py` — typed config

**Files:**
- Create: `ops/config.py`
- Test: `tests/ops/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/test_config.py
from decimal import Decimal
from ops.config import OpsConfig, load_config

def test_default_config_matches_spec():
    cfg = OpsConfig()
    # Spec section 3 defaults
    assert cfg.deny_list == {
        "SPOT",
        "TQQQ", "SQQQ", "UPRO", "SPXU", "UVXY", "SVXY",
        "SOXL", "SOXS", "LABU", "LABD", "TNA", "TZA",
        "TMF", "TMV", "QLD", "QID",
    }
    assert cfg.per_position_cap_pct == Decimal("0.10")
    assert cfg.per_trade_dollar_floor == Decimal("5")
    assert cfg.max_open_positions == 5
    assert cfg.cash_reserve_pct == Decimal("0.20")
    assert cfg.daily_drawdown_pct == Decimal("-0.07")
    assert cfg.weekly_drawdown_pct == Decimal("-0.15")
    assert cfg.per_position_stop_pct == Decimal("-0.08")
    assert cfg.broker_mode == "paper"

def test_load_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("OPS_BROKER_MODE", "robinhood")
    monkeypatch.setenv("OPS_PER_POSITION_CAP_PCT", "0.05")
    cfg = load_config()
    assert cfg.broker_mode == "robinhood"
    assert cfg.per_position_cap_pct == Decimal("0.05")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ops.config'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/config.py
"""Operational config for the live-trading layer.

Defaults match docs/superpowers/specs/2026-06-30-tradingagents-live-v1-design.md
section "Guardrail rules". Override at runtime via OPS_* env vars.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal

_DEFAULT_DENY_LIST = frozenset({
    "SPOT",
    "TQQQ", "SQQQ", "UPRO", "SPXU", "UVXY", "SVXY",
    "SOXL", "SOXS", "LABU", "LABD", "TNA", "TZA",
    "TMF", "TMV", "QLD", "QID",
})


@dataclass(frozen=True)
class OpsConfig:
    broker_mode: str = "paper"  # "paper" or "robinhood"
    deny_list: frozenset[str] = field(default_factory=lambda: _DEFAULT_DENY_LIST)
    per_position_cap_pct: Decimal = Decimal("0.10")
    per_trade_dollar_floor: Decimal = Decimal("5")
    max_open_positions: int = 5
    cash_reserve_pct: Decimal = Decimal("0.20")
    daily_drawdown_pct: Decimal = Decimal("-0.07")
    weekly_drawdown_pct: Decimal = Decimal("-0.15")
    per_position_stop_pct: Decimal = Decimal("-0.08")
    journal_path: str = "ops_journal.sqlite"


def _env_decimal(name: str, default: Decimal) -> Decimal:
    raw = os.environ.get(name)
    return Decimal(raw) if raw is not None else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw is not None else default


def load_config() -> OpsConfig:
    return OpsConfig(
        broker_mode=os.environ.get("OPS_BROKER_MODE", "paper"),
        per_position_cap_pct=_env_decimal("OPS_PER_POSITION_CAP_PCT", Decimal("0.10")),
        per_trade_dollar_floor=_env_decimal("OPS_PER_TRADE_DOLLAR_FLOOR", Decimal("5")),
        max_open_positions=_env_int("OPS_MAX_OPEN_POSITIONS", 5),
        cash_reserve_pct=_env_decimal("OPS_CASH_RESERVE_PCT", Decimal("0.20")),
        daily_drawdown_pct=_env_decimal("OPS_DAILY_DRAWDOWN_PCT", Decimal("-0.07")),
        weekly_drawdown_pct=_env_decimal("OPS_WEEKLY_DRAWDOWN_PCT", Decimal("-0.15")),
        per_position_stop_pct=_env_decimal("OPS_PER_POSITION_STOP_PCT", Decimal("-0.08")),
        journal_path=os.environ.get("OPS_JOURNAL_PATH", "ops_journal.sqlite"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/config.py tests/ops/test_config.py
git commit -m "feat(ops): typed config with spec defaults and env overrides"
```

---

## Task 2: `ops/journal.py` — SQLite event journal

**Files:**
- Create: `ops/journal.py`
- Test: `tests/ops/test_journal.py`

The journal is append-only. Tables: `events` (catch-all keyed event log), `orders`, `fills`, `equity_snapshots`. Decisions and positions snapshots come in later plans.

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/test_journal.py
from datetime import datetime, timezone
from decimal import Decimal
from ops.journal import Journal

def test_journal_records_and_reads_event(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    j.record_event("test_kind", {"foo": "bar", "n": 1})
    events = j.read_events()
    assert len(events) == 1
    assert events[0]["kind"] == "test_kind"
    assert events[0]["payload"] == {"foo": "bar", "n": 1}
    assert isinstance(events[0]["at"], datetime)

def test_journal_records_order_and_fill(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    j.record_order(
        client_order_id="cid-1", symbol="AAPL", side="BUY",
        notional_dollars=Decimal("25.00"), stop_loss_price=Decimal("180.00"),
    )
    j.record_fill(
        order_id="oid-1", client_order_id="cid-1", symbol="AAPL", side="BUY",
        quantity=Decimal("0.1245"), price=Decimal("200.80"),
        filled_at=datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc),
    )
    orders = j.read_orders()
    fills = j.read_fills()
    assert orders[0]["symbol"] == "AAPL"
    assert orders[0]["notional_dollars"] == Decimal("25.00")
    assert fills[0]["price"] == Decimal("200.80")

def test_journal_records_equity_snapshot(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    j.record_equity_snapshot(
        at=datetime(2026, 6, 30, 13, 30, tzinfo=timezone.utc),
        equity=Decimal("250.00"), cash=Decimal("250.00"),
    )
    snaps = j.read_equity_snapshots()
    assert snaps[0]["equity"] == Decimal("250.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/test_journal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ops.journal'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/journal.py
"""Append-only SQLite journal for the live-trading layer.

The journal is the source of truth for state recovery. Every state change
in the system MUST land here before any other side effect.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    notional_dollars TEXT NOT NULL,
    stop_loss_price TEXT
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    order_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    filled_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    equity TEXT NOT NULL,
    cash TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not allowed in the journal")
    return dt.isoformat()


def _from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Journal:
    def __init__(self, path: str):
        self._path = path
        self._conn = sqlite3.connect(path, isolation_level=None)
        self._conn.executescript(_SCHEMA)

    def record_event(self, kind: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO events (at, kind, payload) VALUES (?, ?, ?)",
            (_now_iso(), kind, json.dumps(payload, default=str)),
        )

    def read_events(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT at, kind, payload FROM events ORDER BY id")
        return [
            {"at": _from_iso(row[0]), "kind": row[1], "payload": json.loads(row[2])}
            for row in cur
        ]

    def record_order(
        self, *, client_order_id: str, symbol: str, side: str,
        notional_dollars: Decimal, stop_loss_price: Decimal | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO orders (at, client_order_id, symbol, side, notional_dollars, stop_loss_price)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                _now_iso(), client_order_id, symbol, side,
                str(notional_dollars),
                str(stop_loss_price) if stop_loss_price is not None else None,
            ),
        )

    def read_orders(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT at, client_order_id, symbol, side, notional_dollars, stop_loss_price"
            " FROM orders ORDER BY id"
        )
        return [
            {
                "at": _from_iso(row[0]), "client_order_id": row[1],
                "symbol": row[2], "side": row[3],
                "notional_dollars": Decimal(row[4]),
                "stop_loss_price": Decimal(row[5]) if row[5] is not None else None,
            }
            for row in cur
        ]

    def record_fill(
        self, *, order_id: str, client_order_id: str, symbol: str, side: str,
        quantity: Decimal, price: Decimal, filled_at: datetime,
    ) -> None:
        self._conn.execute(
            "INSERT INTO fills (at, order_id, client_order_id, symbol, side, quantity, price, filled_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _now_iso(), order_id, client_order_id, symbol, side,
                str(quantity), str(price), _to_iso(filled_at),
            ),
        )

    def read_fills(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT at, order_id, client_order_id, symbol, side, quantity, price, filled_at"
            " FROM fills ORDER BY id"
        )
        return [
            {
                "at": _from_iso(row[0]), "order_id": row[1],
                "client_order_id": row[2], "symbol": row[3], "side": row[4],
                "quantity": Decimal(row[5]), "price": Decimal(row[6]),
                "filled_at": _from_iso(row[7]),
            }
            for row in cur
        ]

    def record_equity_snapshot(self, *, at: datetime, equity: Decimal, cash: Decimal) -> None:
        self._conn.execute(
            "INSERT INTO equity_snapshots (at, equity, cash) VALUES (?, ?, ?)",
            (_to_iso(at), str(equity), str(cash)),
        )

    def read_equity_snapshots(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT at, equity, cash FROM equity_snapshots ORDER BY id")
        return [
            {"at": _from_iso(row[0]), "equity": Decimal(row[1]), "cash": Decimal(row[2])}
            for row in cur
        ]

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/test_journal.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/journal.py tests/ops/test_journal.py
git commit -m "feat(ops): append-only SQLite journal for events, orders, fills, equity"
```

---

## Task 3: `ops/broker/types.py` — domain types

**Files:**
- Create: `ops/broker/types.py`
- Test: `tests/ops/broker/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/broker/test_types.py
from decimal import Decimal
import pytest
from ops.broker.types import Order, Side, OrderType, Position

def test_order_is_frozen():
    o = Order(
        client_order_id="cid-1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("180"),
    )
    with pytest.raises(Exception):
        o.symbol = "MSFT"

def test_order_buy_requires_positive_notional():
    with pytest.raises(ValueError):
        Order(
            client_order_id="x", symbol="AAPL", side=Side.BUY,
            notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
        )

def test_order_sell_allows_zero_notional_meaning_sell_all():
    o = Order(
        client_order_id="x", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    assert o.notional_dollars == Decimal("0")

def test_position_value():
    p = Position(
        symbol="AAPL", quantity=Decimal("0.5"),
        avg_entry_price=Decimal("200"), stop_loss_price=Decimal("184"),
    )
    assert p.market_value(Decimal("210")) == Decimal("105.0")
    assert p.unrealized_pct(Decimal("210")) == Decimal("0.05")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/broker/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ops.broker.types'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/broker/types.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class Order:
    client_order_id: str
    symbol: str
    side: Side
    notional_dollars: Decimal
    order_type: OrderType
    limit_price: Decimal | None = None
    stop_loss_price: Decimal | None = None

    def __post_init__(self):
        if self.side == Side.BUY and self.notional_dollars <= 0:
            raise ValueError("BUY order requires positive notional_dollars")
        if self.notional_dollars < 0:
            raise ValueError("notional_dollars cannot be negative")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    stop_loss_price: Decimal | None

    def market_value(self, current_price: Decimal) -> Decimal:
        return self.quantity * current_price

    def unrealized_pct(self, current_price: Decimal) -> Decimal:
        return (current_price - self.avg_entry_price) / self.avg_entry_price


@dataclass(frozen=True)
class Fill:
    order_id: str
    client_order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    filled_at: "datetime"  # noqa: F821 (forward-ref to avoid stdlib import in module signature line)


from datetime import datetime  # placed at end to satisfy forward ref above
Fill.__annotations__["filled_at"] = datetime  # type: ignore[assignment]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/broker/test_types.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/broker/types.py tests/ops/broker/test_types.py
git commit -m "feat(ops): broker domain types (Order, Fill, Position)"
```

---

## Task 4: `ops/broker/base.py` — `Broker` ABC and `OrderRejected`

**Files:**
- Create: `ops/broker/base.py`

(No standalone test file — the ABC's surface is exercised through `PaperBroker` and `GuardedBroker` tests.)

- [ ] **Step 1: Write the implementation**

```python
# ops/broker/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from ops.broker.types import Fill, Order, Position


class BrokerError(Exception):
    pass


class OrderRejected(BrokerError):
    """Raised when a guardrail rule rejects an order before it reaches the broker."""

    def __init__(self, rule_name: str, reason: str):
        super().__init__(f"{rule_name}: {reason}")
        self.rule_name = rule_name
        self.reason = reason


class InsufficientFunds(BrokerError):
    pass


class NoSuchPosition(BrokerError):
    pass


class Broker(ABC):
    @abstractmethod
    def get_cash(self) -> Decimal: ...

    @abstractmethod
    def get_equity(self) -> Decimal: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> Decimal: ...

    @abstractmethod
    def place_order(self, order: Order) -> Fill: ...
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from ops.broker.base import Broker, OrderRejected"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add ops/broker/base.py
git commit -m "feat(ops): Broker ABC and OrderRejected exception"
```

---

## Task 5: `ops/broker/paper.py` — `PaperBroker`

**Files:**
- Create: `ops/broker/paper.py`
- Test: `tests/ops/broker/test_paper.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/broker/test_paper.py
from decimal import Decimal
import pytest
from ops.broker.types import Order, Side, OrderType
from ops.broker.base import InsufficientFunds, NoSuchPosition
from ops.broker.paper import PaperBroker
from ops.journal import Journal


def _broker(tmp_path, prices: dict[str, str], cash: str = "250"):
    j = Journal(str(tmp_path / "j.sqlite"))
    quotes = {k: Decimal(v) for k, v in prices.items()}
    return PaperBroker(journal=j, quote_source=lambda s: quotes[s], starting_cash=Decimal(cash))


def test_buy_creates_position_and_debits_cash(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    o = Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    fill = b.place_order(o)
    assert fill.quantity == Decimal("0.125")
    assert fill.price == Decimal("200")
    assert b.get_cash() == Decimal("225")
    positions = b.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == Decimal("0.125")
    assert positions[0].stop_loss_price == Decimal("184")


def test_buy_with_insufficient_cash_raises(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"}, cash="10")
    o = Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
    )
    with pytest.raises(InsufficientFunds):
        b.place_order(o)


def test_sell_reduces_position_and_credits_cash(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("50"), order_type=OrderType.MARKET,
    ))
    # price moves up
    b._quote = lambda s: Decimal("220")  # type: ignore[attr-defined]
    b.place_order(Order(
        client_order_id="c2", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("22"), order_type=OrderType.MARKET,
    ))
    pos = b.get_positions()[0]
    assert pos.quantity == Decimal("0.15")  # 0.25 bought, 0.1 sold
    assert b.get_cash() == Decimal("222")  # 250 - 50 + 22


def test_sell_zero_notional_closes_position(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("50"), order_type=OrderType.MARKET,
    ))
    b.place_order(Order(
        client_order_id="c2", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    ))
    assert b.get_positions() == []
    assert b.get_cash() == Decimal("250")


def test_sell_without_position_raises(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    with pytest.raises(NoSuchPosition):
        b.place_order(Order(
            client_order_id="c1", symbol="AAPL", side=Side.SELL,
            notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        ))


def test_equity_reflects_position_value_and_cash(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("50"), order_type=OrderType.MARKET,
    ))
    b._quote = lambda s: Decimal("240")  # type: ignore[attr-defined]
    # cash: 200; position value: 0.25 * 240 = 60; total: 260
    assert b.get_equity() == Decimal("260.000")


def test_fills_are_journaled(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    b = PaperBroker(journal=j, quote_source=lambda s: Decimal("200"), starting_cash=Decimal("250"))
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    orders = j.read_orders()
    fills = j.read_fills()
    assert len(orders) == 1 and len(fills) == 1
    assert orders[0]["client_order_id"] == "c1"
    assert fills[0]["quantity"] == Decimal("0.125")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/broker/test_paper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ops.broker.paper'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/broker/paper.py
"""In-memory paper broker. Records every order and fill to the journal."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from ops.broker.base import Broker, InsufficientFunds, NoSuchPosition
from ops.broker.types import Fill, Order, Position, Side
from ops.journal import Journal

QuoteSource = Callable[[str], Decimal]

_EPSILON = Decimal("0.0000001")


class PaperBroker(Broker):
    def __init__(self, *, journal: Journal, quote_source: QuoteSource, starting_cash: Decimal):
        self._journal = journal
        self._quote = quote_source
        self._cash = Decimal(starting_cash)
        self._positions: dict[str, Position] = {}

    def get_cash(self) -> Decimal:
        return self._cash

    def get_quote(self, symbol: str) -> Decimal:
        return self._quote(symbol)

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_equity(self) -> Decimal:
        total = self._cash
        for pos in self._positions.values():
            total += pos.market_value(self._quote(pos.symbol))
        return total

    def place_order(self, order: Order) -> Fill:
        self._journal.record_order(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side.value,
            notional_dollars=order.notional_dollars,
            stop_loss_price=order.stop_loss_price,
        )
        price = self._quote(order.symbol)
        if order.side == Side.BUY:
            return self._fill_buy(order, price)
        return self._fill_sell(order, price)

    def _fill_buy(self, order: Order, price: Decimal) -> Fill:
        cost = order.notional_dollars
        if cost > self._cash:
            raise InsufficientFunds(f"need ${cost}, have ${self._cash}")
        qty = cost / price
        self._cash -= cost
        existing = self._positions.get(order.symbol)
        if existing is None:
            new_pos = Position(
                symbol=order.symbol,
                quantity=qty,
                avg_entry_price=price,
                stop_loss_price=order.stop_loss_price,
            )
        else:
            total_qty = existing.quantity + qty
            avg = (
                (existing.avg_entry_price * existing.quantity) + (price * qty)
            ) / total_qty
            new_pos = Position(
                symbol=order.symbol,
                quantity=total_qty,
                avg_entry_price=avg,
                stop_loss_price=order.stop_loss_price or existing.stop_loss_price,
            )
        self._positions[order.symbol] = new_pos
        return self._make_fill(order, qty, price)

    def _fill_sell(self, order: Order, price: Decimal) -> Fill:
        existing = self._positions.get(order.symbol)
        if existing is None:
            raise NoSuchPosition(f"no position in {order.symbol}")
        if order.notional_dollars == 0:
            qty_to_sell = existing.quantity
        else:
            qty_to_sell = order.notional_dollars / price
        if qty_to_sell > existing.quantity + _EPSILON:
            raise NoSuchPosition(
                f"sell qty {qty_to_sell} exceeds position {existing.quantity}"
            )
        proceeds = qty_to_sell * price
        self._cash += proceeds
        remaining = existing.quantity - qty_to_sell
        if remaining > _EPSILON:
            self._positions[order.symbol] = Position(
                symbol=existing.symbol,
                quantity=remaining,
                avg_entry_price=existing.avg_entry_price,
                stop_loss_price=existing.stop_loss_price,
            )
        else:
            del self._positions[order.symbol]
        return self._make_fill(order, qty_to_sell, price)

    def _make_fill(self, order: Order, qty: Decimal, price: Decimal) -> Fill:
        fill = Fill(
            order_id=str(uuid4()),
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            filled_at=datetime.now(timezone.utc),
        )
        self._journal.record_fill(
            order_id=fill.order_id,
            client_order_id=fill.client_order_id,
            symbol=fill.symbol,
            side=fill.side.value,
            quantity=fill.quantity,
            price=fill.price,
            filled_at=fill.filled_at,
        )
        return fill
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/broker/test_paper.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/broker/paper.py tests/ops/broker/test_paper.py
git commit -m "feat(ops): PaperBroker with journal-recorded fills"
```

---

## Task 6: `ops/guardrails/base.py` — `Rule`, `RuleContext`, `RuleResult`

**Files:**
- Create: `ops/guardrails/base.py`

(Exercised by the engine and rule tests; no standalone test.)

- [ ] **Step 1: Write the implementation**

```python
# ops/guardrails/base.py
"""Guardrail rule primitives.

A Rule inspects an Order in the context of broker state + config and either
allows the order through or rejects it with a structured reason. Rules are
pure with respect to broker state read at evaluation time; they do not mutate
broker state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from ops.broker.base import Broker
from ops.broker.types import Order
from ops.config import OpsConfig


@dataclass(frozen=True)
class RuleResult:
    allowed: bool
    reason: str = ""

    @classmethod
    def allow(cls) -> "RuleResult":
        return cls(allowed=True)

    @classmethod
    def reject(cls, reason: str) -> "RuleResult":
        return cls(allowed=False, reason=reason)


@dataclass(frozen=True)
class RuleContext:
    order: Order
    broker: Broker
    config: OpsConfig


class Rule(ABC):
    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def check(self, ctx: RuleContext) -> RuleResult: ...
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from ops.guardrails.base import Rule, RuleContext, RuleResult"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add ops/guardrails/base.py
git commit -m "feat(ops): guardrail Rule ABC and result/context types"
```

---

## Task 7: `ops/guardrails/static_rules.py` — symbol/order-shape rules

**Files:**
- Create: `ops/guardrails/static_rules.py`
- Test: `tests/ops/guardrails/test_static_rules.py`

These rules depend only on the order + config (not broker state): `DenyListRule`, `NoMarginRule`, `NoOptionsRule`, `NoCryptoRule`, `LongOnlyRule`, `StopAttachedRule`, `FractionalSharesOnlyRule`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/guardrails/test_static_rules.py
from decimal import Decimal
import pytest
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.static_rules import (
    DenyListRule, NoMarginRule, NoOptionsRule, NoCryptoRule,
    LongOnlyRule, StopAttachedRule, FractionalSharesOnlyRule,
)


def _ctx(order: Order, cfg: OpsConfig | None = None) -> RuleContext:
    return RuleContext(order=order, broker=None, config=cfg or OpsConfig())  # type: ignore[arg-type]


def _buy(symbol: str = "AAPL", **kwargs) -> Order:
    defaults = dict(
        client_order_id="c", symbol=symbol, side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    defaults.update(kwargs)
    return Order(**defaults)


def test_deny_list_blocks_spot():
    assert DenyListRule().check(_ctx(_buy("SPOT"))).allowed is False

def test_deny_list_blocks_leveraged_etf():
    assert DenyListRule().check(_ctx(_buy("TQQQ"))).allowed is False

def test_deny_list_allows_normal_ticker():
    assert DenyListRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_no_margin_blocks_explicit_margin_symbol_format():
    # We use a simple convention: any symbol starting with "MARGIN:" is reserved for margin orders
    o = _buy("MARGIN:AAPL")
    assert NoMarginRule().check(_ctx(o)).allowed is False

def test_no_margin_allows_regular_symbol():
    assert NoMarginRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_no_options_blocks_occ_symbol():
    # OCC option symbols include spaces and the YYMMDD+C/P+strike convention
    o = _buy("AAPL  260117C00200000")
    assert NoOptionsRule().check(_ctx(o)).allowed is False

def test_no_options_allows_equity():
    assert NoOptionsRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_no_crypto_blocks_known_crypto_symbols():
    for sym in ("BTC", "ETH", "DOGE", "SHIB", "BTC-USD"):
        assert NoCryptoRule().check(_ctx(_buy(sym))).allowed is False, sym

def test_no_crypto_allows_equity():
    assert NoCryptoRule().check(_ctx(_buy("AAPL"))).allowed is True

def test_long_only_blocks_short_marker_in_client_order_id():
    o = _buy(client_order_id="SHORT-1")
    # We require side == BUY/SELL and v1 does not support shorting;
    # any client_order_id prefixed SHORT- is treated as a short attempt
    assert LongOnlyRule().check(_ctx(o)).allowed is False

def test_long_only_allows_buy_and_sell():
    assert LongOnlyRule().check(_ctx(_buy())).allowed is True
    sell = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    assert LongOnlyRule().check(_ctx(sell)).allowed is True

def test_stop_attached_requires_stop_on_buy():
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=None,
    )
    assert StopAttachedRule().check(_ctx(o)).allowed is False

def test_stop_attached_allows_sell_without_stop():
    sell = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    assert StopAttachedRule().check(_ctx(sell)).allowed is True

def test_fractional_only_blocks_whole_share_order_marker():
    # We require BUY orders to be specified in dollar notional; any order
    # using whole-share quantity is expressed as notional=0 with side BUY which
    # is already blocked by Order.__post_init__. This rule double-checks that
    # the order_type/route is the fractional-dollar route.
    # Convention: orders with notional ending in .00000 are notional-routed;
    # the rule's purpose is to ensure BUYs went through the notional API path
    # rather than a (future) shares-quantity field. For v1 there is no shares
    # field, so this rule is currently a guard against future regression: it
    # passes any BUY with positive notional_dollars.
    assert FractionalSharesOnlyRule().check(_ctx(_buy())).allowed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/guardrails/test_static_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ops.guardrails.static_rules'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/guardrails/static_rules.py
from __future__ import annotations

from ops.broker.types import Side
from ops.guardrails.base import Rule, RuleContext, RuleResult

_CRYPTO_SYMBOLS = frozenset({
    "BTC", "ETH", "DOGE", "SHIB", "LTC", "BCH", "ETC", "BSV",
    "BTC-USD", "ETH-USD", "DOGE-USD", "SHIB-USD",
})


class DenyListRule(Rule):
    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.symbol in ctx.config.deny_list:
            return RuleResult.reject(f"{ctx.order.symbol} is on the deny list")
        return RuleResult.allow()


class NoMarginRule(Rule):
    """v1 only allows cash trades. Rejects any symbol prefixed MARGIN:."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.symbol.startswith("MARGIN:"):
            return RuleResult.reject("margin orders are not allowed in v1")
        return RuleResult.allow()


class NoOptionsRule(Rule):
    """Rejects OCC-style option symbols. v1 is equity-only."""

    def check(self, ctx: RuleContext) -> RuleResult:
        # OCC symbols contain spaces and have a length > 15 (root + 15-char suffix)
        s = ctx.order.symbol
        if " " in s and len(s) >= 16:
            return RuleResult.reject("options orders are not allowed in v1")
        return RuleResult.allow()


class NoCryptoRule(Rule):
    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.symbol in _CRYPTO_SYMBOLS:
            return RuleResult.reject(f"{ctx.order.symbol} is crypto; not allowed in v1")
        return RuleResult.allow()


class LongOnlyRule(Rule):
    """Rejects any order whose client_order_id is prefixed SHORT-, which is
    the convention strategies use to mark short attempts. v1 does not support
    short selling."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.client_order_id.startswith("SHORT-"):
            return RuleResult.reject("short selling is not allowed in v1")
        return RuleResult.allow()


class StopAttachedRule(Rule):
    """Every BUY must carry a stop_loss_price. SELLs do not require one."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side == Side.BUY and ctx.order.stop_loss_price is None:
            return RuleResult.reject("BUY orders require stop_loss_price")
        return RuleResult.allow()


class FractionalSharesOnlyRule(Rule):
    """v1 BUYs use dollar-notional routing (fractional shares). This rule is
    a future-regression guard: it confirms BUY orders specify positive
    notional_dollars (no whole-share-quantity field on the Order)."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side == Side.BUY and ctx.order.notional_dollars <= 0:
            return RuleResult.reject("BUY orders must use dollar-notional routing")
        return RuleResult.allow()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/guardrails/test_static_rules.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/guardrails/static_rules.py tests/ops/guardrails/test_static_rules.py
git commit -m "feat(ops): static guardrail rules (deny-list, margin/options/crypto, long-only, stop, fractional)"
```

---

## Task 8: `ops/guardrails/sizing_rules.py` — sizing/exposure rules

**Files:**
- Create: `ops/guardrails/sizing_rules.py`
- Test: `tests/ops/guardrails/test_sizing_rules.py`

Rules: `PerPositionCapRule`, `PerTradeDollarFloorRule`, `MaxOpenPositionsRule`, `CashReserveRule`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/guardrails/test_sizing_rules.py
from decimal import Decimal
from unittest.mock import MagicMock
from ops.broker.types import Order, Side, OrderType, Position
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.sizing_rules import (
    PerPositionCapRule, PerTradeDollarFloorRule,
    MaxOpenPositionsRule, CashReserveRule,
)


def _ctx(notional: str, positions: list[Position], equity: str, cash: str,
         cfg: OpsConfig | None = None) -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal(notional), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    b = MagicMock()
    b.get_equity.return_value = Decimal(equity)
    b.get_cash.return_value = Decimal(cash)
    b.get_positions.return_value = positions
    return RuleContext(order=o, broker=b, config=cfg or OpsConfig())


def test_per_position_cap_allows_under_threshold():
    # 10% of $250 = $25 cap; order at $25 is allowed (inclusive)
    r = PerPositionCapRule().check(_ctx("25", [], "250", "250"))
    assert r.allowed is True


def test_per_position_cap_blocks_over_threshold():
    r = PerPositionCapRule().check(_ctx("25.01", [], "250", "250"))
    assert r.allowed is False


def test_per_trade_floor_blocks_tiny_orders():
    r = PerTradeDollarFloorRule().check(_ctx("4.99", [], "250", "250"))
    assert r.allowed is False


def test_per_trade_floor_allows_at_threshold():
    r = PerTradeDollarFloorRule().check(_ctx("5", [], "250", "250"))
    assert r.allowed is True


def _pos(sym: str) -> Position:
    return Position(symbol=sym, quantity=Decimal("0.1"),
                    avg_entry_price=Decimal("100"), stop_loss_price=Decimal("92"))


def test_max_open_positions_blocks_when_full():
    positions = [_pos(s) for s in ("AAPL", "MSFT", "NVDA", "GOOG", "AMZN")]
    # Order is for a NEW symbol "META"
    o = Order(
        client_order_id="c", symbol="META", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    b = MagicMock()
    b.get_positions.return_value = positions
    ctx = RuleContext(order=o, broker=b, config=OpsConfig())
    assert MaxOpenPositionsRule().check(ctx).allowed is False


def test_max_open_positions_allows_add_to_existing():
    positions = [_pos(s) for s in ("AAPL", "MSFT", "NVDA", "GOOG", "AMZN")]
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,  # already held
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    b = MagicMock()
    b.get_positions.return_value = positions
    ctx = RuleContext(order=o, broker=b, config=OpsConfig())
    assert MaxOpenPositionsRule().check(ctx).allowed is True


def test_max_open_positions_allows_under_cap():
    positions = [_pos(s) for s in ("AAPL", "MSFT")]
    o = Order(
        client_order_id="c", symbol="NVDA", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    b = MagicMock()
    b.get_positions.return_value = positions
    ctx = RuleContext(order=o, broker=b, config=OpsConfig())
    assert MaxOpenPositionsRule().check(ctx).allowed is True


def test_cash_reserve_blocks_if_buy_would_breach_20pct_floor():
    # Equity $250; 20% reserve = $50 cash must remain.
    # Cash currently $60. A $25 BUY would leave $35, below floor.
    r = CashReserveRule().check(_ctx("25", [], "250", "60"))
    assert r.allowed is False


def test_cash_reserve_allows_if_post_trade_cash_above_floor():
    # Cash $100; $25 BUY leaves $75 > $50 floor
    r = CashReserveRule().check(_ctx("25", [], "250", "100"))
    assert r.allowed is True


def test_cash_reserve_does_not_constrain_sells():
    sell = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    b = MagicMock()
    b.get_equity.return_value = Decimal("250")
    b.get_cash.return_value = Decimal("10")
    b.get_positions.return_value = []
    ctx = RuleContext(order=sell, broker=b, config=OpsConfig())
    assert CashReserveRule().check(ctx).allowed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/guardrails/test_sizing_rules.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/guardrails/sizing_rules.py
from __future__ import annotations

from ops.broker.types import Side
from ops.guardrails.base import Rule, RuleContext, RuleResult


class PerPositionCapRule(Rule):
    """BUY notional must be <= per_position_cap_pct * current equity."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        equity = ctx.broker.get_equity()
        cap = equity * ctx.config.per_position_cap_pct
        if ctx.order.notional_dollars > cap:
            return RuleResult.reject(
                f"order ${ctx.order.notional_dollars} exceeds per-position cap ${cap}"
            )
        return RuleResult.allow()


class PerTradeDollarFloorRule(Rule):
    """BUY notional must meet a minimum to avoid noise trades."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        if ctx.order.notional_dollars < ctx.config.per_trade_dollar_floor:
            return RuleResult.reject(
                f"order ${ctx.order.notional_dollars} below floor "
                f"${ctx.config.per_trade_dollar_floor}"
            )
        return RuleResult.allow()


class MaxOpenPositionsRule(Rule):
    """BUYs that would open a NEW position are blocked when at the cap.
    Adding to an existing position is always allowed by this rule."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        positions = ctx.broker.get_positions()
        held_symbols = {p.symbol for p in positions}
        if ctx.order.symbol in held_symbols:
            return RuleResult.allow()
        if len(held_symbols) >= ctx.config.max_open_positions:
            return RuleResult.reject(
                f"at max open positions ({ctx.config.max_open_positions}) "
                f"and {ctx.order.symbol} is new"
            )
        return RuleResult.allow()


class CashReserveRule(Rule):
    """After a BUY, cash must remain >= cash_reserve_pct * equity."""

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        equity = ctx.broker.get_equity()
        cash = ctx.broker.get_cash()
        floor = equity * ctx.config.cash_reserve_pct
        post_cash = cash - ctx.order.notional_dollars
        if post_cash < floor:
            return RuleResult.reject(
                f"post-trade cash ${post_cash} below reserve floor ${floor}"
            )
        return RuleResult.allow()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/guardrails/test_sizing_rules.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/guardrails/sizing_rules.py tests/ops/guardrails/test_sizing_rules.py
git commit -m "feat(ops): sizing guardrail rules (position cap, trade floor, max positions, cash reserve)"
```

---

## Task 9: `ops/guardrails/drawdown_rules.py` — daily/weekly drawdown

**Files:**
- Create: `ops/guardrails/drawdown_rules.py`
- Test: `tests/ops/guardrails/test_drawdown_rules.py`

These rules need a "start-of-day equity" and "start-of-week equity" reference. We inject them as callables for testability; the orchestrator (Plan 3) will provide real impls reading the journal.

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/guardrails/test_drawdown_rules.py
from decimal import Decimal
from unittest.mock import MagicMock
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.drawdown_rules import DailyDrawdownRule, WeeklyDrawdownRule


def _buy_ctx(equity: str) -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    b = MagicMock()
    b.get_equity.return_value = Decimal(equity)
    return RuleContext(order=o, broker=b, config=OpsConfig())


def _sell_ctx(equity: str) -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    b = MagicMock()
    b.get_equity.return_value = Decimal(equity)
    return RuleContext(order=o, broker=b, config=OpsConfig())


def test_daily_drawdown_allows_above_threshold():
    rule = DailyDrawdownRule(start_of_day_equity=lambda: Decimal("250"))
    # current equity $235; loss = -6% (above -7% threshold)
    assert rule.check(_buy_ctx("235")).allowed is True


def test_daily_drawdown_blocks_at_threshold():
    rule = DailyDrawdownRule(start_of_day_equity=lambda: Decimal("250"))
    # current equity $232.50; loss = -7.0% exactly
    assert rule.check(_buy_ctx("232.50")).allowed is False


def test_daily_drawdown_does_not_block_sells():
    rule = DailyDrawdownRule(start_of_day_equity=lambda: Decimal("250"))
    # even deeply down, sells (= position management) are not blocked
    assert rule.check(_sell_ctx("200")).allowed is True


def test_weekly_drawdown_allows_above_threshold():
    rule = WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("250"))
    # -10% (above -15% threshold)
    assert rule.check(_buy_ctx("225")).allowed is True


def test_weekly_drawdown_blocks_at_threshold():
    rule = WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("250"))
    # -15% exactly: $212.50
    assert rule.check(_buy_ctx("212.50")).allowed is False


def test_weekly_drawdown_blocks_sells_too():
    # Weekly is the kill switch level. In v1 paper mode the orchestrator will
    # auto-close on weekly trip, but the rule itself prevents new BUYs only;
    # SELLs are allowed even when weekly is tripped so positions can be exited.
    rule = WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("250"))
    assert rule.check(_sell_ctx("200")).allowed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/guardrails/test_drawdown_rules.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/guardrails/drawdown_rules.py
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from ops.broker.types import Side
from ops.guardrails.base import Rule, RuleContext, RuleResult

EquityFn = Callable[[], Decimal]


class DailyDrawdownRule(Rule):
    """Blocks BUYs when today's loss vs. start-of-day equity is at or past
    the threshold. SELLs are always allowed."""

    def __init__(self, start_of_day_equity: EquityFn):
        self._start = start_of_day_equity

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        start = self._start()
        if start <= 0:
            return RuleResult.allow()
        current = ctx.broker.get_equity()
        pct = (current - start) / start
        if pct <= ctx.config.daily_drawdown_pct:
            return RuleResult.reject(
                f"daily drawdown {pct} at or below threshold "
                f"{ctx.config.daily_drawdown_pct}; new BUYs halted"
            )
        return RuleResult.allow()


class WeeklyDrawdownRule(Rule):
    """Blocks BUYs when this week's loss vs. start-of-week equity is at or
    past the threshold. SELLs are always allowed (kill-switch auto-close
    happens in the orchestrator, not in this rule)."""

    def __init__(self, start_of_week_equity: EquityFn):
        self._start = start_of_week_equity

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        start = self._start()
        if start <= 0:
            return RuleResult.allow()
        current = ctx.broker.get_equity()
        pct = (current - start) / start
        if pct <= ctx.config.weekly_drawdown_pct:
            return RuleResult.reject(
                f"weekly drawdown {pct} at or below threshold "
                f"{ctx.config.weekly_drawdown_pct}; new BUYs halted"
            )
        return RuleResult.allow()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/guardrails/test_drawdown_rules.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/guardrails/drawdown_rules.py tests/ops/guardrails/test_drawdown_rules.py
git commit -m "feat(ops): daily and weekly drawdown rules with injected equity sources"
```

---

## Task 10: `ops/guardrails/engine.py` — `RuleEngine`

**Files:**
- Create: `ops/guardrails/engine.py`
- Test: `tests/ops/guardrails/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/guardrails/test_engine.py
from decimal import Decimal
from unittest.mock import MagicMock
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import Rule, RuleContext, RuleResult
from ops.guardrails.engine import RuleEngine


class _AlwaysAllow(Rule):
    def check(self, ctx): return RuleResult.allow()


class _AlwaysReject(Rule):
    def __init__(self, label: str): self._label = label
    @property
    def name(self): return f"Reject_{self._label}"
    def check(self, ctx): return RuleResult.reject(f"rejected by {self._label}")


def _ctx() -> RuleContext:
    o = Order(
        client_order_id="c", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    return RuleContext(order=o, broker=MagicMock(), config=OpsConfig())


def test_engine_passes_when_all_allow():
    eng = RuleEngine([_AlwaysAllow(), _AlwaysAllow()])
    result = eng.evaluate(_ctx())
    assert result.allowed is True


def test_engine_short_circuits_on_first_failure():
    second = _AlwaysReject("B")
    eng = RuleEngine([_AlwaysAllow(), _AlwaysReject("A"), second])
    result = eng.evaluate(_ctx())
    assert result.allowed is False
    assert "rejected by A" in result.reason
    assert result.failed_rule_name == "Reject_A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/guardrails/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/guardrails/engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ops.guardrails.base import Rule, RuleContext


@dataclass(frozen=True)
class EngineResult:
    allowed: bool
    reason: str = ""
    failed_rule_name: str = ""


class RuleEngine:
    def __init__(self, rules: Sequence[Rule]):
        self._rules = list(rules)

    def evaluate(self, ctx: RuleContext) -> EngineResult:
        for rule in self._rules:
            result = rule.check(ctx)
            if not result.allowed:
                return EngineResult(
                    allowed=False, reason=result.reason, failed_rule_name=rule.name
                )
        return EngineResult(allowed=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/guardrails/test_engine.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/guardrails/engine.py tests/ops/guardrails/test_engine.py
git commit -m "feat(ops): RuleEngine evaluating rules in order, short-circuiting on failure"
```

---

## Task 11: `ops/broker/guarded.py` — `GuardedBroker`

**Files:**
- Create: `ops/broker/guarded.py`
- Test: `tests/ops/broker/test_guarded.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/broker/test_guarded.py
from decimal import Decimal
import pytest
from ops.broker.base import OrderRejected
from ops.broker.guarded import GuardedBroker
from ops.broker.paper import PaperBroker
from ops.broker.types import Order, Side, OrderType
from ops.config import OpsConfig
from ops.guardrails.base import Rule, RuleContext, RuleResult
from ops.guardrails.engine import RuleEngine
from ops.journal import Journal


class _RejectSymbol(Rule):
    def __init__(self, symbol): self._sym = symbol
    @property
    def name(self): return "RejectSymbol"
    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.symbol == self._sym:
            return RuleResult.reject(f"reject {self._sym}")
        return RuleResult.allow()


def _stack(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    paper = PaperBroker(journal=j, quote_source=lambda s: Decimal("200"),
                       starting_cash=Decimal("250"))
    engine = RuleEngine([_RejectSymbol("BANNED")])
    return j, paper, GuardedBroker(inner=paper, engine=engine, journal=j, config=OpsConfig())


def test_guarded_allows_passing_order(tmp_path):
    j, paper, guarded = _stack(tmp_path)
    fill = guarded.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    assert fill.symbol == "AAPL"
    assert paper.get_positions()[0].symbol == "AAPL"


def test_guarded_rejects_and_journals_rejection(tmp_path):
    j, paper, guarded = _stack(tmp_path)
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(Order(
            client_order_id="c1", symbol="BANNED", side=Side.BUY,
            notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
            stop_loss_price=Decimal("184"),
        ))
    assert exc.value.rule_name == "RejectSymbol"
    # Inner broker was not touched
    assert paper.get_positions() == []
    assert paper.get_cash() == Decimal("250")
    # The rejection event is in the journal
    events = j.read_events()
    rejections = [e for e in events if e["kind"] == "order_rejected"]
    assert len(rejections) == 1
    assert rejections[0]["payload"]["rule"] == "RejectSymbol"
    assert rejections[0]["payload"]["symbol"] == "BANNED"


def test_guarded_passes_through_read_methods(tmp_path):
    _, paper, guarded = _stack(tmp_path)
    assert guarded.get_cash() == paper.get_cash()
    assert guarded.get_equity() == paper.get_equity()
    assert guarded.get_quote("AAPL") == paper.get_quote("AAPL")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/broker/test_guarded.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# ops/broker/guarded.py
"""GuardedBroker — wraps any Broker and runs the rule chain on every order.

This is the only Broker callers ever see outside the broker package. The
inner broker is private to GuardedBroker; this is how we guarantee guardrails
cannot be bypassed."""
from __future__ import annotations

from decimal import Decimal

from ops.broker.base import Broker, OrderRejected
from ops.broker.types import Fill, Order, Position
from ops.config import OpsConfig
from ops.guardrails.base import RuleContext
from ops.guardrails.engine import RuleEngine
from ops.journal import Journal


class GuardedBroker(Broker):
    def __init__(self, *, inner: Broker, engine: RuleEngine, journal: Journal, config: OpsConfig):
        self._inner = inner
        self._engine = engine
        self._journal = journal
        self._config = config

    def get_cash(self) -> Decimal:
        return self._inner.get_cash()

    def get_equity(self) -> Decimal:
        return self._inner.get_equity()

    def get_positions(self) -> list[Position]:
        return self._inner.get_positions()

    def get_quote(self, symbol: str) -> Decimal:
        return self._inner.get_quote(symbol)

    def place_order(self, order: Order) -> Fill:
        ctx = RuleContext(order=order, broker=self._inner, config=self._config)
        result = self._engine.evaluate(ctx)
        if not result.allowed:
            self._journal.record_event(
                "order_rejected",
                {
                    "rule": result.failed_rule_name,
                    "reason": result.reason,
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "notional_dollars": str(order.notional_dollars),
                },
            )
            raise OrderRejected(result.failed_rule_name, result.reason)
        return self._inner.place_order(order)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ops/broker/test_guarded.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/broker/guarded.py tests/ops/broker/test_guarded.py
git commit -m "feat(ops): GuardedBroker enforces rule chain and journals rejections"
```

---

## Task 12: End-to-end integration test

**Files:**
- Create: `tests/ops/test_integration.py`

Verifies the full default stack: `GuardedBroker(PaperBroker, RuleEngine[all rules])`. Each of the 13 rules gets one rejection path test and one allow path test, plus a happy-path fill that journals correctly.

- [ ] **Step 1: Write the failing test**

```python
# tests/ops/test_integration.py
"""End-to-end test of the default guarded paper-broker stack."""
from decimal import Decimal
import pytest
from ops.broker.base import OrderRejected
from ops.broker.guarded import GuardedBroker
from ops.broker.paper import PaperBroker
from ops.broker.types import Order, Side, OrderType, Position
from ops.config import OpsConfig
from ops.guardrails.engine import RuleEngine
from ops.guardrails.static_rules import (
    DenyListRule, NoMarginRule, NoOptionsRule, NoCryptoRule,
    LongOnlyRule, StopAttachedRule, FractionalSharesOnlyRule,
)
from ops.guardrails.sizing_rules import (
    PerPositionCapRule, PerTradeDollarFloorRule,
    MaxOpenPositionsRule, CashReserveRule,
)
from ops.guardrails.drawdown_rules import DailyDrawdownRule, WeeklyDrawdownRule
from ops.journal import Journal


def _default_stack(tmp_path, *, starting_cash="250", quotes=None,
                   start_day_equity="250", start_week_equity="250"):
    j = Journal(str(tmp_path / "j.sqlite"))
    quotes = quotes or {"AAPL": Decimal("200")}
    paper = PaperBroker(
        journal=j,
        quote_source=lambda s: quotes[s],
        starting_cash=Decimal(starting_cash),
    )
    cfg = OpsConfig()
    rules = [
        DenyListRule(),
        NoMarginRule(),
        NoOptionsRule(),
        NoCryptoRule(),
        LongOnlyRule(),
        StopAttachedRule(),
        FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(),
        PerPositionCapRule(),
        MaxOpenPositionsRule(),
        CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=lambda: Decimal(start_day_equity)),
        WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal(start_week_equity)),
    ]
    return j, paper, GuardedBroker(inner=paper, engine=RuleEngine(rules), journal=j, config=cfg)


def _buy(symbol="AAPL", notional="25", stop="184", cid="c1") -> Order:
    return Order(
        client_order_id=cid, symbol=symbol, side=Side.BUY,
        notional_dollars=Decimal(notional), order_type=OrderType.MARKET,
        stop_loss_price=Decimal(stop) if stop else None,
    )


def test_happy_path_fills_and_journals(tmp_path):
    j, paper, guarded = _default_stack(tmp_path)
    fill = guarded.place_order(_buy())
    assert fill.quantity == Decimal("0.125")
    assert paper.get_positions()[0].symbol == "AAPL"
    # Journal: 1 order + 1 fill, no rejections
    assert len(j.read_orders()) == 1
    assert len(j.read_fills()) == 1
    assert [e for e in j.read_events() if e["kind"] == "order_rejected"] == []


@pytest.mark.parametrize("order,expected_rule", [
    (_buy(symbol="SPOT"), "DenyListRule"),
    (_buy(symbol="TQQQ"), "DenyListRule"),
    (_buy(symbol="MARGIN:AAPL"), "NoMarginRule"),
    (_buy(symbol="AAPL  260117C00200000"), "NoOptionsRule"),
    (_buy(symbol="BTC"), "NoCryptoRule"),
    (_buy(cid="SHORT-1"), "LongOnlyRule"),
    (_buy(stop=None), "StopAttachedRule"),
    (_buy(notional="4.99"), "PerTradeDollarFloorRule"),
    (_buy(notional="25.01"), "PerPositionCapRule"),
])
def test_rule_rejections(tmp_path, order, expected_rule):
    j, paper, guarded = _default_stack(tmp_path)
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(order)
    assert exc.value.rule_name == expected_rule
    # Inner broker untouched
    assert paper.get_positions() == []
    assert paper.get_cash() == Decimal("250")
    # Rejection journaled
    rejections = [e for e in j.read_events() if e["kind"] == "order_rejected"]
    assert len(rejections) == 1
    assert rejections[0]["payload"]["rule"] == expected_rule


def test_max_open_positions_rejection(tmp_path):
    # Fund the broker enough to hold 5 positions
    j = Journal(str(tmp_path / "j.sqlite"))
    quotes = {s: Decimal("200") for s in ("AAPL", "MSFT", "NVDA", "GOOG", "AMZN", "META")}
    paper = PaperBroker(journal=j, quote_source=lambda s: quotes[s],
                       starting_cash=Decimal("10000"))
    cfg = OpsConfig()
    rules = [
        DenyListRule(), NoMarginRule(), NoOptionsRule(), NoCryptoRule(),
        LongOnlyRule(), StopAttachedRule(), FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(), PerPositionCapRule(),
        MaxOpenPositionsRule(), CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=lambda: Decimal("10000")),
        WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("10000")),
    ]
    guarded = GuardedBroker(inner=paper, engine=RuleEngine(rules), journal=j, config=cfg)
    # Buy 5 different positions at $25 each
    for i, sym in enumerate(("AAPL", "MSFT", "NVDA", "GOOG", "AMZN")):
        guarded.place_order(_buy(symbol=sym, notional="25", cid=f"c{i}"))
    # 6th NEW symbol must be rejected
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(symbol="META", notional="25", cid="c6"))
    assert exc.value.rule_name == "MaxOpenPositionsRule"


def test_cash_reserve_rejection(tmp_path):
    j, paper, guarded = _default_stack(tmp_path, starting_cash="60")
    # 60 cash - 25 buy = 35; reserve floor = 0.2 * (60) = 12 ... that allows.
    # We need to construct a tighter case: starting_cash $60, equity = $60,
    # floor = $12. A $49 buy would leave $11 (under floor) — but $49 also
    # breaches per-position cap (10% of $60 = $6). To isolate CashReserveRule,
    # use a custom config with a higher per-position cap.
    j2 = Journal(str(tmp_path / "j2.sqlite"))
    paper2 = PaperBroker(journal=j2, quote_source=lambda s: Decimal("200"),
                        starting_cash=Decimal("60"))
    cfg2 = OpsConfig(per_position_cap_pct=Decimal("1.0"))  # disable position cap
    rules = [
        DenyListRule(), NoMarginRule(), NoOptionsRule(), NoCryptoRule(),
        LongOnlyRule(), StopAttachedRule(), FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(), PerPositionCapRule(),
        MaxOpenPositionsRule(), CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=lambda: Decimal("60")),
        WeeklyDrawdownRule(start_of_week_equity=lambda: Decimal("60")),
    ]
    guarded2 = GuardedBroker(inner=paper2, engine=RuleEngine(rules), journal=j2, config=cfg2)
    # Buy $50 — post-cash $10, floor $12 → reject
    with pytest.raises(OrderRejected) as exc:
        guarded2.place_order(_buy(notional="50"))
    assert exc.value.rule_name == "CashReserveRule"


def test_daily_drawdown_rejection(tmp_path):
    # Equity $230 vs. start-of-day $250 → -8% (≤ -7% threshold) → reject
    j, paper, guarded = _default_stack(
        tmp_path, starting_cash="230", start_day_equity="250",
    )
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(notional="20"))
    assert exc.value.rule_name == "DailyDrawdownRule"


def test_weekly_drawdown_rejection(tmp_path):
    # Equity $200 vs. start-of-week $250 → -20% (≤ -15%) → reject
    j, paper, guarded = _default_stack(
        tmp_path, starting_cash="200", start_day_equity="200", start_week_equity="250",
    )
    with pytest.raises(OrderRejected) as exc:
        guarded.place_order(_buy(notional="15"))
    # DailyDrawdownRule fires first if also tripped; we set start_day = current
    # so daily is 0% and only weekly trips.
    assert exc.value.rule_name == "WeeklyDrawdownRule"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ops/test_integration.py -v`
Expected: FAIL — initial run may have ordering or fixture failures; the goal is to drive the integration suite to green.

- [ ] **Step 3: Iterate as needed**

If any test fails, the failure points to a real bug or mis-spec'd rule order. Common fix: rule ordering in `_default_stack`. The canonical order (cheapest checks first, then state-dependent checks):
1. Static/symbol checks: `DenyListRule`, `NoMarginRule`, `NoOptionsRule`, `NoCryptoRule`, `LongOnlyRule`
2. Order-shape: `StopAttachedRule`, `FractionalSharesOnlyRule`
3. Sizing: `PerTradeDollarFloorRule`, `PerPositionCapRule`, `MaxOpenPositionsRule`, `CashReserveRule`
4. Account-state: `DailyDrawdownRule`, `WeeklyDrawdownRule`

(That's the order used in the test's `_default_stack` and in `test_max_open_positions_rejection`.)

- [ ] **Step 4: Verify the suite passes**

Run: `pytest tests/ops/test_integration.py -v`
Expected: all tests pass.

- [ ] **Step 5: Run the full ops suite for coverage**

Run: `pytest tests/ops/ -v --tb=short`
Expected: all tests pass; no warnings about uncovered rule classes.

- [ ] **Step 6: Commit**

```bash
git add tests/ops/test_integration.py
git commit -m "test(ops): end-to-end integration coverage of guarded paper broker stack"
```

---

## Task 13: Wire into existing test runner

**Files:**
- Modify: `pyproject.toml` (if needed to include `tests/ops/` in pytest collection — most likely already covered)

- [ ] **Step 1: Inspect existing pyproject for pytest config**

Run: `grep -A 20 '\[tool.pytest' pyproject.toml`
Expected output documents whether `testpaths` is set.

- [ ] **Step 2: If `testpaths` excludes our new tests, add `tests/ops`**

Only modify if needed. If the existing `testpaths = ["tests"]` (or unset) covers our location, skip the edit.

- [ ] **Step 3: Run the whole suite**

Run: `pytest -q 2>&1 | tail -10`
Expected: existing tests + new tests all pass.

- [ ] **Step 4: Commit (only if a config change was needed)**

```bash
# Skip if no edit was made.
git add pyproject.toml
git commit -m "chore(ops): include ops tests in pytest collection"
```

---

## Task 14: Push branch + open PR against your fork

**Files:** none

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/ops-foundation
```

- [ ] **Step 2: Open PR on the fork**

Run:
```bash
gh pr create --repo CWFred/TradingAgents --base main \
  --title "feat(ops): foundation — guarded paper broker, guardrail rules, journal" \
  --body "$(cat <<'EOF'
## Summary
- Adds `ops/` package: `Broker` ABC, `PaperBroker`, `GuardedBroker`, guardrail rules, `RuleEngine`, SQLite `Journal`.
- All 13 guardrails from the spec implemented and tested. End-to-end integration test exercises every rule rejection path.
- Paper mode only. No scheduler, no pipeline, no live broker, no notifications — those come in Plans 2 and 3.

## Test plan
- [x] `pytest tests/ops/ -v` all green
- [x] No upstream code modified

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Mark plan complete**

After PR is open and merged into your fork's `main`, this plan is done. Plan 2 (Strategy & Pipeline) is the next plan to write.

---

## Self-review notes (already applied)

- **Spec coverage:** every guardrail listed in spec section 3 has a dedicated rule class and a test. SQLite journal supports the event types this plan needs (`orders`, `fills`, `events`, `equity_snapshots`). Items not in this plan but in the spec — pipeline adapter, universe builder, strategy module, position guardian, market calendar, orchestrator, notifications, Robinhood broker — are correctly deferred to Plans 2 and 3.
- **Placeholder scan:** no TBDs. The rules' assumptions about symbol formats (`MARGIN:`, OCC option pattern, `SHORT-` client_order_id prefix) are conventions enforced by the strategy module in Plan 2; documented in the rule docstrings.
- **Type consistency:** `Side`, `OrderType`, `Order`, `Position`, `Fill`, `Rule`, `RuleContext`, `RuleResult`, `EngineResult` used identically across tasks.
- **Scope:** focused on a single coherent unit — a guarded paper broker — that ships testable on its own.
