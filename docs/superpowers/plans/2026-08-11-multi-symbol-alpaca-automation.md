# Multi-Symbol Alpaca Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-interactive seven-symbol, 30-minute automation path that preserves the existing single-symbol graph, sizes long and short targets by conviction within a hard 30%-of-cash cap, and reconciles those targets through Alpaca paper or explicitly enabled live trading.

**Architecture:** Pure configuration, allocation, and SQLite state modules feed a cycle service that calls `TradingAgentsGraph.propagate()` sequentially for the next persisted two- or three-symbol batch. A narrow broker protocol isolates Alpaca SDK calls, while one-shot and foreground scheduler entry points share the same idempotent service and leave the existing interactive `analyze` path untouched.

**Tech Stack:** Python 3.10+, Typer, SQLite (`sqlite3`), `decimal.Decimal`, existing LangGraph analysis, optional `alpaca-py>=0.43.5`, pytest, Ruff.

## Global Constraints

- The watchlist comes only from config/environment and contains exactly seven unique symbols.
- Batch size is `2` or `3`; seven symbols rotate as `2, 2, 3` or `3, 2, 2`.
- Analysis and position tracking default to 30-minute intervals.
- The sum of absolute managed target notionals is at most 30% of current positive Alpaca cash.
- `Buy`, `Overweight`, `Hold`, `Underweight`, and `Sell` map to `+1`, `+0.5`, `0`, `-0.5`, and `-1`.
- Alpaca paper mode is the default; live submission needs explicit mode, auto-execute, and acknowledgment.
- Alpaca asset capabilities remain authoritative; unsupported shorts are skipped without weight redistribution.
- The existing `TradingAgentsGraph.propagate()` implementation and graph topology are not modified.
- The existing interactive `tradingagents analyze` command retains its behavior.
- Default automated tests make no network, LLM, or brokerage calls and submit no orders.
- Do not modify or discuss provider setup flows unrelated to this feature.

---

## File Map

- `tradingagents/default_config.py`: typed automation defaults and env mappings.
- `tradingagents/automation.py`: validated settings, batch partitioning, graph orchestration, and cycle results.
- `tradingagents/automation_state.py`: SQLite decisions, cursor, snapshots, order intents, task timestamps, and leases.
- `tradingagents/allocation.py`: conviction targets and target-delta order intents.
- `tradingagents/execution.py`: broker data contracts, mode safety, symbol conversion, and Alpaca SDK adapter.
- `tradingagents/scheduler.py`: service construction, due-task checks, one-shot run, and foreground loop.
- `cli/main.py`: lazy `batch` and `automate` Typer commands.
- `tests/test_automation_config.py`: config and partition tests.
- `tests/test_allocation.py`: score, cap, and reconciliation tests.
- `tests/test_automation_state.py`: persistent state and lease tests.
- `tests/test_alpaca_execution.py`: environment, capability, conversion, and idempotency tests.
- `tests/test_automation_cycle.py`: fake-graph/fake-broker cycle tests.
- `tests/test_scheduler.py`: cadence and CLI delegation tests.
- `pyproject.toml`: optional Alpaca dependency.
- `.env.example`: complete inactive automation configuration.
- `README.md`: dry-run, paper, live, local loop, cron, state, and limitations.

---

### Task 1: Environment Configuration and Deterministic Batch Partitions

**Files:**
- Modify: `tradingagents/default_config.py`
- Create: `tradingagents/automation.py`
- Create: `tests/test_automation_config.py`
- Modify: `tests/test_env_overrides.py`

**Interfaces:**
- Consumes: existing `_ENV_OVERRIDES`, `_coerce()`, and `DEFAULT_CONFIG`.
- Produces: `AutomationSettings.from_config(config: Mapping[str, object]) -> AutomationSettings` and `partition_watchlist(symbols: tuple[str, ...], preferred_size: int) -> tuple[tuple[str, ...], ...]`.

- [ ] **Step 1: Write failing env and settings tests**

```python
from pathlib import Path

import pytest

from tradingagents.automation import AutomationSettings, partition_watchlist


def _config(**overrides):
    base = {
        "watchlist": "AAPL,MSFT,NVDA,AMZN,META,GOOG,TSLA",
        "batch_size": 3,
        "analysis_interval_minutes": 30,
        "position_interval_minutes": 30,
        "max_cash_allocation": 0.30,
        "decision_max_age_minutes": 120,
        "rebalance_threshold_usd": 10.0,
        "automation_state_path": "/tmp/tradingagents-state.db",
        "auto_execute": False,
        "alpaca_mode": "paper",
        "live_trading_ack": "",
    }
    base.update(overrides)
    return base


def test_settings_require_exactly_seven_unique_symbols():
    with pytest.raises(ValueError, match="exactly 7 unique symbols"):
        AutomationSettings.from_config(_config(watchlist="AAPL,AAPL,MSFT"))


def test_settings_normalize_watchlist_and_keep_hard_cap():
    settings = AutomationSettings.from_config(
        _config(watchlist=" aapl, msft,nvda,amzn,meta,goog,tsla ")
    )
    assert settings.watchlist == ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA")
    assert settings.max_cash_allocation == 0.30
    assert settings.state_path == Path("/tmp/tradingagents-state.db")


def test_settings_reject_allocation_above_thirty_percent():
    with pytest.raises(ValueError, match="no greater than 0.30"):
        AutomationSettings.from_config(_config(max_cash_allocation=0.31))


def test_partition_patterns_cover_every_symbol_once():
    symbols = ("A", "B", "C", "D", "E", "F", "G")
    assert partition_watchlist(symbols, 3) == (("A", "B", "C"), ("D", "E"), ("F", "G"))
    assert partition_watchlist(symbols, 2) == (("A", "B"), ("C", "D"), ("E", "F", "G"))
```

Extend `tests/test_env_overrides.py` with this concrete reload test:

```python
def test_automation_overrides(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_WATCHLIST="AAPL,MSFT,NVDA,AMZN,META,GOOG,TSLA",
        TRADINGAGENTS_BATCH_SIZE="2",
        TRADINGAGENTS_ANALYSIS_INTERVAL_MINUTES="30",
        TRADINGAGENTS_POSITION_INTERVAL_MINUTES="30",
        TRADINGAGENTS_MAX_CASH_ALLOCATION="0.25",
        TRADINGAGENTS_AUTO_EXECUTE="true",
        TRADINGAGENTS_ALPACA_MODE="live",
    )
    assert dc.DEFAULT_CONFIG["watchlist"].startswith("AAPL,MSFT")
    assert dc.DEFAULT_CONFIG["batch_size"] == 2
    assert dc.DEFAULT_CONFIG["analysis_interval_minutes"] == 30
    assert dc.DEFAULT_CONFIG["position_interval_minutes"] == 30
    assert dc.DEFAULT_CONFIG["max_cash_allocation"] == 0.25
    assert dc.DEFAULT_CONFIG["auto_execute"] is True
    assert dc.DEFAULT_CONFIG["alpaca_mode"] == "live"
```

- [ ] **Step 2: Run tests and verify the feature is absent**

Run: `pytest tests/test_automation_config.py tests/test_env_overrides.py -q`

Expected: collection fails because `tradingagents.automation` and the automation defaults do not exist.

- [ ] **Step 3: Add defaults, mappings, validation, and partitioning**

Add these defaults and `_ENV_OVERRIDES` rows using the exact keys from the design:

```python
"watchlist": "",
"batch_size": 3,
"analysis_interval_minutes": 30,
"position_interval_minutes": 30,
"max_cash_allocation": 0.30,
"decision_max_age_minutes": 120,
"rebalance_threshold_usd": 10.0,
"automation_state_path": os.path.join(_TRADINGAGENTS_HOME, "automation", "state.db"),
"auto_execute": False,
"alpaca_mode": "paper",
"live_trading_ack": "",
```

Create `AutomationSettings` as a frozen dataclass with the fields exercised above. Its factory uppercases symbols, rejects blanks/duplicates/non-seven cardinality, accepts only batch sizes 2/3 and Alpaca modes paper/live, requires positive intervals/age, requires non-negative rebalance threshold, and enforces `0 < max_cash_allocation <= 0.30`.

Implement partitioning without a generic bin-packing abstraction:

```python
def partition_watchlist(symbols, preferred_size):
    if len(symbols) != 7 or preferred_size not in (2, 3):
        raise ValueError("seven symbols and a preferred batch size of 2 or 3 are required")
    cut_points = (2, 4) if preferred_size == 2 else (3, 5)
    first, second = cut_points
    return (symbols[:first], symbols[first:second], symbols[second:])
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_automation_config.py tests/test_env_overrides.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the configuration slice**

```bash
git add tradingagents/default_config.py tradingagents/automation.py tests/test_automation_config.py tests/test_env_overrides.py
git commit -m "feat: configure seven-symbol automation"
```

---

### Task 2: Pure Conviction Allocation and Reconciliation

**Files:**
- Create: `tradingagents/allocation.py`
- Create: `tests/test_allocation.py`

**Interfaces:**
- Consumes: canonical rating strings returned by `TradingAgentsGraph.propagate()` and Decimal-compatible cash/config values.
- Produces: `OrderIntent`, `conviction_targets()`, and `reconcile_targets()` for the cycle service and broker adapter.

- [ ] **Step 1: Write failing allocation tests**

```python
from decimal import Decimal

from tradingagents.allocation import (
    OrderIntent,
    conviction_targets,
    reconcile_targets,
)


def test_conviction_targets_normalize_signed_weights_with_thirty_percent_cap():
    targets = conviction_targets(
        {"AAPL": "Buy", "MSFT": "Overweight", "TSLA": "Sell", "META": "Hold"},
        cash=Decimal("10000"),
        max_cash_allocation=Decimal("0.30"),
    )
    assert targets == {
        "AAPL": Decimal("1200"),
        "MSFT": Decimal("600"),
        "TSLA": Decimal("-1200"),
        "META": Decimal("0"),
    }
    assert sum(abs(value) for value in targets.values()) == Decimal("3000")


def test_non_positive_cash_and_all_hold_produce_zero_targets():
    assert conviction_targets({"AAPL": "Buy"}, Decimal("0"), Decimal("0.30"))["AAPL"] == 0
    assert conviction_targets({"AAPL": "Hold"}, Decimal("1000"), Decimal("0.30"))["AAPL"] == 0


def test_reconciliation_includes_signed_open_order_exposure_and_threshold():
    intents = reconcile_targets(
        targets={"AAPL": Decimal("1000"), "TSLA": Decimal("-500")},
        positions={"AAPL": Decimal("600"), "TSLA": Decimal("-200")},
        open_orders={"AAPL": Decimal("100"), "TSLA": Decimal("-100")},
        threshold=Decimal("50"),
    )
    assert intents == [
        OrderIntent("AAPL", "buy", Decimal("300"), Decimal("1000")),
        OrderIntent("TSLA", "sell", Decimal("200"), Decimal("-500")),
    ]
```

Add these exact edge tests:

```python
import pytest


@pytest.mark.parametrize(
    ("rating", "sign"),
    [("Buy", 1), ("Overweight", 1), ("Hold", 0), ("Underweight", -1), ("Sell", -1)],
)
def test_every_rating_has_the_expected_direction(rating, sign):
    target = conviction_targets({"AAPL": rating}, Decimal("1000"), Decimal("0.30"))["AAPL"]
    assert (target > 0) - (target < 0) == sign


def test_unknown_rating_is_rejected():
    with pytest.raises(ValueError, match="unsupported rating"):
        conviction_targets({"AAPL": "Strong Buy"}, Decimal("1000"), Decimal("0.30"))


@pytest.mark.parametrize(
    ("position", "expected_side"),
    [(Decimal("500"), "sell"), (Decimal("-500"), "buy")],
)
def test_hold_target_closes_long_or_short(position, expected_side):
    intents = reconcile_targets(
        {"AAPL": Decimal("0")}, {"AAPL": position}, {}, Decimal("10")
    )
    assert intents[0].side == expected_side
    assert intents[0].notional == Decimal("500")


def test_delta_below_threshold_is_suppressed():
    assert reconcile_targets(
        {"AAPL": Decimal("100")}, {"AAPL": Decimal("95")}, {}, Decimal("10")
    ) == []
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run: `pytest tests/test_allocation.py -q`

Expected: collection fails because `tradingagents.allocation` does not exist.

- [ ] **Step 3: Implement the minimal pure allocation module**

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

RATING_SCORES = {
    "Buy": Decimal("1"),
    "Overweight": Decimal("0.5"),
    "Hold": Decimal("0"),
    "Underweight": Decimal("-0.5"),
    "Sell": Decimal("-1"),
}


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    notional: Decimal
    target_notional: Decimal


def conviction_targets(decisions, cash, max_cash_allocation):
    scores = {symbol: RATING_SCORES[rating] for symbol, rating in decisions.items()}
    gross_budget = max(Decimal(cash), Decimal("0")) * Decimal(max_cash_allocation)
    score_total = sum(abs(score) for score in scores.values())
    if score_total == 0:
        return {symbol: Decimal("0") for symbol in decisions}
    return {
        symbol: gross_budget * score / score_total
        for symbol, score in scores.items()
    }


def reconcile_targets(targets, positions, open_orders, threshold):
    intents = []
    for symbol, target in targets.items():
        effective = positions.get(symbol, Decimal("0")) + open_orders.get(symbol, Decimal("0"))
        delta = target - effective
        if abs(delta) >= threshold and delta != 0:
            intents.append(OrderIntent(symbol, "buy" if delta > 0 else "sell", abs(delta), target))
    return intents
```

Use `Decimal(str(value))` at public boundaries to avoid binary-float conversion. Preserve watchlist/mapping insertion order so order plans are deterministic.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_allocation.py -q`

Expected: all allocation tests pass.

- [ ] **Step 5: Commit the allocator**

```bash
git add tradingagents/allocation.py tests/test_allocation.py
git commit -m "feat: add conviction weighted allocation"
```

---

### Task 3: SQLite Automation State and Cycle Leases

**Files:**
- Create: `tradingagents/automation_state.py`
- Create: `tests/test_automation_state.py`

**Interfaces:**
- Consumes: filesystem path, UTC-aware timestamps, ratings, report paths, position mappings, and `OrderIntent` objects.
- Produces: `DecisionRecord`, `PositionSnapshot`, and these exact `AutomationState` methods:

```python
def get_batch_index(self) -> int: ...
def advance_batch_index(self, next_index: int) -> None: ...
def save_decision(self, symbol: str, rating: str, analyzed_at: datetime, trade_date: str, report_path: str) -> None: ...
def fresh_decisions(self, symbols: tuple[str, ...], now: datetime, max_age_minutes: int) -> dict[str, DecisionRecord]: ...
def record_position_snapshot(self, captured_at: datetime, cash: Decimal, positions: Mapping[str, Decimal]) -> None: ...
def latest_position_snapshot(self) -> PositionSnapshot | None: ...
def record_order_intents(self, cycle_id: str, created_at: datetime, intents: Sequence[OrderIntent]) -> None: ...
def order_intent_count(self, cycle_id: str) -> int: ...
def update_order_intent(self, cycle_id: str, symbol: str, status: str, client_order_id: str | None = None) -> None: ...
def mark_task_run(self, task: str, ran_at: datetime) -> None: ...
def last_task_run(self, task: str) -> datetime | None: ...
def try_acquire_lease(self, task: str, owner: str, now: datetime, ttl_seconds: int) -> bool: ...
```

- [ ] **Step 1: Write failing state tests**

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tradingagents.allocation import OrderIntent
from tradingagents.automation_state import AutomationState


NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)


def test_cursor_decisions_and_freshness_survive_reopen(tmp_path):
    path = tmp_path / "state.db"
    state = AutomationState(path)
    state.advance_batch_index(1)
    state.save_decision("AAPL", "Buy", NOW, "2026-08-11", "/reports/aapl.md")
    state.close()

    reopened = AutomationState(path)
    assert reopened.get_batch_index() == 1
    fresh = reopened.fresh_decisions(("AAPL",), NOW + timedelta(minutes=30), 120)
    assert fresh["AAPL"].rating == "Buy"
    assert reopened.fresh_decisions(("AAPL",), NOW + timedelta(minutes=121), 120) == {}


def test_cycle_lease_allows_only_one_owner_until_expiry(tmp_path):
    state = AutomationState(tmp_path / "state.db")
    assert state.try_acquire_lease("analysis", "owner-a", NOW, 900)
    assert not state.try_acquire_lease("analysis", "owner-b", NOW, 900)
    assert state.try_acquire_lease("analysis", "owner-b", NOW + timedelta(seconds=901), 900)


def test_snapshots_intents_and_task_times_are_persisted(tmp_path):
    state = AutomationState(tmp_path / "state.db")
    state.record_position_snapshot(NOW, Decimal("10000"), {"AAPL": Decimal("500")})
    state.record_order_intents(
        "cycle-1", NOW, [OrderIntent("AAPL", "buy", Decimal("100"), Decimal("600"))]
    )
    state.mark_task_run("positions", NOW)
    assert state.last_task_run("positions") == NOW
```

- [ ] **Step 2: Run tests and verify the state module is missing**

Run: `pytest tests/test_automation_state.py -q`

Expected: collection fails because `tradingagents.automation_state` does not exist.

- [ ] **Step 3: Implement the SQLite schema and narrow methods**

Create tables with concrete responsibilities:

```sql
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
CREATE TABLE IF NOT EXISTS task_runs (task TEXT PRIMARY KEY, ran_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leases (
  task TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at TEXT NOT NULL
);
```

Use `BEGIN IMMEDIATE` in `try_acquire_lease()` so competing processes serialize the read/replace decision. Store decimals as strings, mappings as sorted JSON, and timestamps as timezone-aware ISO 8601 strings. Create the parent directory in `__init__`; provide `close()` and context-manager methods.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_automation_state.py -q`

Expected: all persistence and lease tests pass.

- [ ] **Step 5: Commit persistent automation state**

```bash
git add tradingagents/automation_state.py tests/test_automation_state.py
git commit -m "feat: persist automation cycle state"
```

---

### Task 4: Safe Alpaca Paper/Live Execution Adapter

**Files:**
- Create: `tradingagents/execution.py`
- Create: `tests/test_alpaca_execution.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `AutomationSettings`, `OrderIntent`, Alpaca credentials, and an optional injected SDK client.
- Produces: `Broker` protocol, `AccountSnapshot`, `AssetInfo`, `BrokerPosition`, `BrokerOpenOrder`, `OrderRequestSpec`, `AlpacaBroker`, `validate_execution_mode()`, and `alpaca_symbol()`.

- [ ] **Step 1: Write failing pure safety and adapter tests**

```python
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tradingagents.allocation import OrderIntent
from tradingagents.execution import (
    AlpacaBroker,
    AssetInfo,
    alpaca_symbol,
    validate_execution_mode,
)


def test_symbol_conversion_changes_only_supported_crypto_separator():
    assert alpaca_symbol("BTC-USD") == "BTC/USD"
    assert alpaca_symbol("AAPL") == "AAPL"


def test_live_submission_requires_exact_acknowledgment():
    with pytest.raises(ValueError, match="live acknowledgment"):
        validate_execution_mode("live", auto_execute=True, live_ack="wrong")
    validate_execution_mode(
        "live", auto_execute=True, live_ack="I_UNDERSTAND_LIVE_ORDERS"
    )


def test_paper_is_selected_explicitly_on_sdk_client(monkeypatch):
    calls = []

    class FakeTradingClient:
        def __init__(self, key, secret, paper):
            calls.append((key, secret, paper))

    monkeypatch.setattr("tradingagents.execution._trading_client_class", lambda: FakeTradingClient)
    AlpacaBroker("key", "secret", mode="paper")
    assert calls == [("key", "secret", True)]


def test_unshortable_asset_rejects_negative_target_without_submission():
    client = SimpleNamespace(submit_order=lambda **kwargs: pytest.fail("must not submit"))
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    asset = AssetInfo("BTC/USD", "crypto", True, False, True, Decimal("0.0001"), Decimal("0.0001"))
    intent = OrderIntent("BTC-USD", "sell", Decimal("500"), Decimal("-500"))
    with pytest.raises(ValueError, match="not shortable"):
        broker.prepare_order(intent, asset, Decimal("50000"), "cycle-1")
```

Add concrete assertions using a fake client whose methods return `SimpleNamespace` SDK-shaped
objects:

```python
def test_prepare_order_uses_asset_time_in_force_and_stable_client_id():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    intent = OrderIntent("AAPL", "buy", Decimal("101"), Decimal("1000"))
    equity = AssetInfo("AAPL", "us_equity", True, True, True, Decimal("0.001"), Decimal("0.001"))
    first = broker.prepare_order(intent, equity, Decimal("100"), "cycle-1")
    second = broker.prepare_order(intent, equity, Decimal("100"), "cycle-1")
    assert first.time_in_force == "day"
    assert first.qty == Decimal("1.01")
    assert first.client_order_id == second.client_order_id


def test_crypto_order_uses_gtc_and_trade_increment():
    broker = AlpacaBroker("key", "secret", mode="paper", client=SimpleNamespace())
    crypto = AssetInfo("BTC/USD", "crypto", True, False, True, Decimal("0.0001"), Decimal("0.0001"))
    spec = broker.prepare_order(
        OrderIntent("BTC-USD", "buy", Decimal("51"), Decimal("51")),
        crypto,
        Decimal("50000"),
        "cycle-1",
    )
    assert spec.symbol == "BTC/USD"
    assert spec.time_in_force == "gtc"
    assert spec.qty == Decimal("0.0010")


def test_idempotent_submit_returns_existing_order_before_submit():
    client = SimpleNamespace(
        get_order_by_client_id=lambda client_order_id: SimpleNamespace(id="existing"),
        submit_order=lambda **kwargs: pytest.fail("must not submit a duplicate"),
    )
    broker = AlpacaBroker("key", "secret", mode="paper", client=client)
    spec = SimpleNamespace(client_order_id="stable-id")
    assert broker.submit_idempotent(spec) == "existing"
```

Separate tests construct account, position, and open-order namespaces and assert blocked accounts
raise, long market values stay positive, shorts stay negative, buy orders add positive exposure,
and sell orders add negative exposure.

- [ ] **Step 2: Run tests and verify the adapter is missing**

Run: `pytest tests/test_alpaca_execution.py -q`

Expected: collection fails because `tradingagents.execution` does not exist.

- [ ] **Step 3: Define broker contracts and fail-closed mode validation**

Use frozen dataclasses containing only fields orchestration needs:

```python
@dataclass(frozen=True)
class AccountSnapshot:
    cash: Decimal
    buying_power: Decimal
    trading_blocked: bool
    status: str


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    asset_class: str
    tradable: bool
    shortable: bool
    fractionable: bool
    min_order_size: Decimal
    min_trade_increment: Decimal


@dataclass(frozen=True)
class OrderRequestSpec:
    symbol: str
    qty: Decimal
    side: str
    time_in_force: str
    client_order_id: str
```

`validate_execution_mode()` accepts only paper/live, returns normally for dry-run, and requires the exact acknowledgment for live auto-execution. `AlpacaBroker` lazy-imports the SDK and constructs `TradingClient(key, secret, paper=(mode == "paper"))`; missing credentials or missing optional dependency produce actionable `RuntimeError` messages without echoing secrets.

- [ ] **Step 4: Implement read mappings, capability checks, and idempotent submission**

Implement methods matching this protocol:

```python
class Broker(Protocol):
    def broker_time(self) -> datetime: ...
    def equity_market_is_open(self) -> bool: ...
    def account(self) -> AccountSnapshot: ...
    def asset(self, symbol: str) -> AssetInfo: ...
    def positions(self) -> dict[str, Decimal]: ...
    def open_order_exposure(self, prices: Mapping[str, Decimal]) -> dict[str, Decimal]: ...
    def latest_price(self, symbol: str) -> Decimal: ...
    def submit(self, spec: OrderRequestSpec) -> str: ...
    def find_order_by_client_id(self, client_order_id: str) -> str | None: ...
```

`prepare_order()` divides notional by a positive price, rounds down to the asset increment, rejects inactive/untradable assets and unsupported negative targets, chooses `gtc` for crypto and `day` for equities, and hashes `cycle_id|symbol|side|target_notional` into an Alpaca-safe client ID. `submit_idempotent()` queries by client ID first and returns the existing order ID when found; it submits only when absent.

Map SDK enums to strings defensively with `getattr(value, "value", value)`. Never catch an SDK exception and resubmit in the same call when order existence is unknown.

- [ ] **Step 5: Add the optional dependency and run focused tests**

Add:

```toml
alpaca = [
    "alpaca-py>=0.43.5",
]
```

Run: `pytest tests/test_alpaca_execution.py -q`

Expected: all adapter tests pass without installing or contacting Alpaca because SDK creation is injected/lazy.

- [ ] **Step 6: Commit the Alpaca adapter**

```bash
git add tradingagents/execution.py tests/test_alpaca_execution.py pyproject.toml
git commit -m "feat: add safe alpaca execution adapter"
```

---

### Task 5: Batch Analysis, Warm-Up, Tracking, and Target Execution Cycle

**Files:**
- Modify: `tradingagents/automation.py`
- Modify: `tradingagents/automation_state.py`
- Create: `tests/test_automation_cycle.py`

**Interfaces:**
- Consumes: `AutomationSettings`, `AutomationState`, `Broker`, `conviction_targets()`, `reconcile_targets()`, `detect_asset_type()`, and an injected graph factory.
- Produces: `CycleResult`, `AutomationCycleService.run_analysis_cycle()`, and `AutomationCycleService.track_positions()`.

- [ ] **Step 1: Write failing cycle tests with fakes**

```python
from datetime import datetime, timezone
from decimal import Decimal

from tradingagents.automation import AutomationCycleService


NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)


def test_first_cycle_analyzes_three_but_does_not_trade_before_warmup(service):
    result = service.run_analysis_cycle(NOW)
    assert result.analyzed_symbols == ("AAPL", "MSFT", "NVDA")
    assert result.order_intents == ()
    assert result.trade_suppressed_reason == "waiting for fresh decisions for all 7 symbols"
    assert service.broker.submitted == []


def test_three_cycles_rotate_3_2_2_then_allocate_all_fresh_decisions(service):
    assert service.run_analysis_cycle(NOW).analyzed_symbols == ("AAPL", "MSFT", "NVDA")
    assert service.run_analysis_cycle(NOW.replace(minute=30)).analyzed_symbols == ("AMZN", "META")
    third = service.run_analysis_cycle(NOW.replace(hour=15, minute=0))
    assert third.analyzed_symbols == ("GOOG", "TSLA")
    assert sum(abs(intent.target_notional) for intent in third.order_intents) <= Decimal("3000")


def test_stale_or_failed_symbol_suppresses_every_order(service):
    service.graph_failures.add("META")
    service.seed_other_decisions(NOW)
    result = service.run_analysis_cycle(NOW)
    assert result.order_intents == ()
    assert "META" in result.trade_suppressed_reason


def test_dry_run_persists_plan_without_submission(warmed_service):
    result = warmed_service.run_analysis_cycle(NOW)
    assert result.order_intents
    assert warmed_service.state.order_intent_count(result.cycle_id) == len(result.order_intents)
    assert warmed_service.broker.submitted == []


def test_position_tracking_persists_cash_and_positions(service):
    service.track_positions(NOW)
    assert service.state.latest_position_snapshot().cash == Decimal("10000")


def test_position_tracking_waits_when_only_equity_market_is_closed(service):
    service.broker.market_open = False
    service.track_positions(NOW)
    assert service.state.latest_position_snapshot() is None
```

Use these explicit fake boundaries, extending only their data fields inside the fixture:

```python
class FakeGraph:
    def __init__(self, ratings, failures):
        self.ratings = ratings
        self.failures = failures

    def propagate(self, symbol, trade_date, asset_type="stock"):
        if symbol in self.failures:
            raise RuntimeError(f"analysis failed for {symbol}")
        return {"final_trade_decision": self.ratings[symbol]}, self.ratings[symbol]

    def save_reports(self, final_state, symbol, save_path=None):
        return Path(f"/reports/{symbol}.md")


class FakeBroker:
    def __init__(self):
        self.cash = Decimal("10000")
        self.buying_power = Decimal("10000")
        self.market_open = True
        self.submitted = []

    def equity_market_is_open(self):
        return self.market_open

    def account(self):
        return AccountSnapshot(self.cash, self.buying_power, False, "ACTIVE")

    def positions(self):
        return {}

    def open_order_exposure(self, prices):
        return {}

    def latest_price(self, symbol):
        return Decimal("100")
```

Add named tests for equity-closed partition deferral, continuous crypto eligibility, one-symbol
eligibility deferral, blocked accounts, insufficient buying power, unsupported shorts without
redistribution, auto-execute paper submission, and exact live acknowledgment enforcement. Each
test asserts both the returned `CycleResult` and `broker.submitted` so it proves behavior rather
than only mock calls.

- [ ] **Step 2: Run tests and verify orchestration is absent**

Run: `pytest tests/test_automation_cycle.py -q`

Expected: tests fail because `AutomationCycleService` and required state query methods do not exist.

- [ ] **Step 3: Implement cycle result and graph execution boundary**

```python
@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    analyzed_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    order_intents: tuple[OrderIntent, ...]
    submitted_order_ids: tuple[str, ...]
    trade_suppressed_reason: str | None
```

`AutomationCycleService` receives all dependencies in its constructor. Cache one graph per
analyst tuple within a cycle: stock uses `("market", "social", "news", "fundamentals")`; crypto
uses `("market", "social", "news")`. Call `propagate(symbol, broker_date, asset_type)` sequentially,
then `save_reports(final_state, symbol)`, and store only successful ratings.

The cycle receives a timezone-aware due time for scheduling, but obtains `broker_date` and the
position-snapshot timestamp from `broker.broker_time()` so persisted trading records use Alpaca's
clock rather than the workstation wall clock.

Select the current persisted partition. An equity is eligible only when
`broker.equity_market_is_open()`; a crypto symbol is always eligible. If fewer than two symbols
in the current partition are eligible, return without advancing the cursor. Otherwise advance
to `(index + 1) % 3` after all eligible symbol attempts finish.

- [ ] **Step 4: Implement warm-up, allocation, planning, and submission**

After analysis, request all seven fresh decisions. When any are missing/stale, set the explicit
suppression reason and return without broker account/order reads beyond eligibility. Otherwise:

1. Read and validate the account.
2. Snapshot positions.
3. Calculate targets from current cash.
4. Fetch prices for managed symbols and incorporate signed open-order exposure.
5. Reconcile and persist every intent before submission.
6. In dry-run, mark intents `planned` and return.
7. In auto-execute, validate mode, capabilities, buying power, and request specs.
8. Submit idempotently one symbol at a time; record `submitted`, `skipped`, or `error` per intent.

Capability failures do not redistribute weights. A broker read failure suppresses all submission.
An individual capability failure records that symbol and allows already validated independent
targets to proceed. Never retry an ambiguous submit directly.

- [ ] **Step 5: Run cycle and lower-level tests**

Run: `pytest tests/test_automation_cycle.py tests/test_automation_state.py tests/test_allocation.py tests/test_alpaca_execution.py -q`

Expected: all orchestration and dependency tests pass.

- [ ] **Step 6: Commit the cycle service**

```bash
git add tradingagents/automation.py tradingagents/automation_state.py tests/test_automation_cycle.py
git commit -m "feat: orchestrate multi-symbol trading cycles"
```

---

### Task 6: Thirty-Minute Scheduler and Non-Interactive CLI Commands

**Files:**
- Create: `tradingagents/scheduler.py`
- Modify: `cli/main.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `AutomationSettings`, `AutomationState`, `AlpacaBroker`, `AutomationCycleService`, `DEFAULT_CONFIG`, and injectable clock/sleep functions.
- Produces: `AutomationScheduler.run_once()`, `AutomationScheduler.run_forever()`, `build_service_from_config()`, `run_batch_from_config()`, and `run_automation_from_config()`.

- [ ] **Step 1: Write failing scheduler and CLI tests**

```python
from datetime import datetime, timedelta, timezone

from typer.testing import CliRunner

import cli.main as cli_main
from tradingagents.scheduler import AutomationScheduler


NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)


def test_run_once_executes_only_due_tasks(fake_service, state):
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once()
    assert fake_service.analysis_calls == [NOW]
    assert fake_service.position_calls == [NOW]

    scheduler.run_once(now=NOW + timedelta(minutes=15))
    assert fake_service.analysis_calls == [NOW]
    assert fake_service.position_calls == [NOW]

    scheduler.run_once(now=NOW + timedelta(minutes=30))
    assert fake_service.analysis_calls[-1] == NOW + timedelta(minutes=30)
    assert fake_service.position_calls[-1] == NOW + timedelta(minutes=30)


def test_batch_cli_lazily_delegates_without_prompting(monkeypatch):
    calls = []
    monkeypatch.setattr("tradingagents.scheduler.run_batch_from_config", lambda: calls.append(True))
    result = CliRunner().invoke(cli_main.app, ["batch"])
    assert result.exit_code == 0
    assert calls == [True]


def test_automate_cli_lazily_delegates(monkeypatch):
    calls = []
    monkeypatch.setattr("tradingagents.scheduler.run_automation_from_config", lambda: calls.append(True))
    result = CliRunner().invoke(cli_main.app, ["automate"])
    assert result.exit_code == 0
    assert calls == [True]
```

Add these scheduler behaviors with explicit assertions:

```python
def test_position_interval_can_be_due_before_analysis(fake_service, state):
    state.mark_task_run("analysis", NOW)
    state.mark_task_run("positions", NOW - timedelta(minutes=30))
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once()
    assert fake_service.analysis_calls == []
    assert fake_service.position_calls == [NOW]


def test_held_lease_prevents_duplicate_analysis(fake_service, state):
    assert state.try_acquire_lease("analysis", "other", NOW, 900)
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once(force_analysis=True)
    assert fake_service.analysis_calls == []


def test_foreground_loop_stops_cleanly_on_keyboard_interrupt(fake_service, state):
    scheduler = AutomationScheduler(
        fake_service,
        state,
        now=lambda: NOW,
        sleep=lambda _: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    scheduler.run_forever()
```

An invalid-config CLI test monkeypatches `build_service_from_config` to raise `ValueError("bad
watchlist")`, invokes `batch`, and asserts non-zero exit plus `bad watchlist` with no prompt text.

- [ ] **Step 2: Run tests and verify scheduler symbols are absent**

Run: `pytest tests/test_scheduler.py -q`

Expected: collection fails because `tradingagents.scheduler` does not exist.

- [ ] **Step 3: Implement due checks and the foreground loop**

`AutomationScheduler.run_once(now=None, force_analysis=False)` compares each task's persisted
last-run timestamp to its configured interval. It acquires the task-specific lease before invoking
the service and marks the task time only after the call returns. `force_analysis=True` makes the
one-shot batch command attempt analysis immediately but keeps market eligibility and lease checks.

`run_forever()` repeatedly calls `run_once()`, computes seconds until the next analysis or position
deadline, and sleeps no more than 60 seconds so shutdown remains responsive. Catch only
`KeyboardInterrupt` at the outer entry point; log operational cycle exceptions and try again at the
next due interval, while configuration/construction errors exit immediately.

- [ ] **Step 4: Add thin CLI commands**

Adding a second Typer command disables Typer's single-command shortcut. Preserve the existing bare
`tradingagents` invocation by extracting the current `analyze` body into
`_invoke_analyze(checkpoint, clear_checkpoints)` and configuring the app with
`invoke_without_command=True`. Add a callback that calls `_invoke_analyze(None, False)` only when
`ctx.invoked_subcommand is None`; the existing `analyze` command delegates to the same helper.
Then add the two lazy automation commands:

```python
@app.command()
def batch():
    """Run the next configured automation batch once."""
    from tradingagents.scheduler import run_batch_from_config

    run_batch_from_config()


@app.command()
def automate():
    """Run market-aware analysis and position tracking continuously."""
    from tradingagents.scheduler import run_automation_from_config

    run_automation_from_config()
```

Add a regression test that monkeypatches `run_analysis`, invokes `CliRunner().invoke(app, [])`,
and asserts the interactive analysis delegate was called exactly once. Keep
`tests/test_cli_no_console.py` passing to prove the existing exception translation still applies
to the bare command.

Construction loads credentials with `os.getenv()` only when an Alpaca client is required. Error
messages name missing variables but never print their contents.

- [ ] **Step 5: Run scheduler and existing CLI regression tests**

Run: `pytest tests/test_scheduler.py tests/test_cli_no_console.py tests/test_cli_config_precedence.py -q`

Expected: all scheduler and existing CLI tests pass.

- [ ] **Step 6: Commit scheduler and CLI entry points**

```bash
git add tradingagents/scheduler.py cli/main.py tests/test_scheduler.py
git commit -m "feat: schedule thirty-minute trading cycles"
```

---

### Task 7: Environment Example, README, and Full Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: final env keys and command names from Tasks 1–6.
- Produces: copyable dry-run/paper/live configuration and operating instructions.

- [ ] **Step 1: Add a failing documentation/config consistency test**

Add to `tests/test_automation_config.py`:

```python
from pathlib import Path

from tradingagents.default_config import _ENV_OVERRIDES


def test_env_example_documents_every_automation_override():
    text = Path(".env.example").read_text()
    automation_vars = {
        name for name, key in _ENV_OVERRIDES.items()
        if key in {
            "watchlist", "batch_size", "analysis_interval_minutes",
            "position_interval_minutes", "max_cash_allocation",
            "decision_max_age_minutes", "rebalance_threshold_usd",
            "automation_state_path", "auto_execute", "alpaca_mode",
            "live_trading_ack",
        }
    }
    assert automation_vars
    assert all(name in text for name in automation_vars)
```

- [ ] **Step 2: Run the consistency test and verify it fails**

Run: `pytest tests/test_automation_config.py::test_env_example_documents_every_automation_override -q`

Expected: failure listing undocumented automation environment variables.

- [ ] **Step 3: Document inactive defaults and credentials**

Add an `.env.example` section containing commented values for all automation settings plus blank
`ALPACA_API_KEY=` and `ALPACA_SECRET_KEY=` lines. Keep `TRADINGAGENTS_AUTO_EXECUTE=false`,
`TRADINGAGENTS_ALPACA_MODE=paper`, and the live acknowledgment commented/blank.

Add a README section with exact commands:

```bash
pip install -e ".[alpaca]"
cp .env.example .env
tradingagents batch
tradingagents automate
```

Include this cron example and explain that the command itself checks market eligibility and the
SQLite lease:

```cron
*/30 * * * * cd /absolute/path/to/TradingAgents && /absolute/path/to/venv/bin/tradingagents batch >> ~/.tradingagents/automation/cron.log 2>&1
```

Document dry-run first, paper enablement, live credentials plus exact acknowledgment, the 30%-of-
cash hard ceiling, `3,2,2`/`2,2,3` rotation, state DB location, decision freshness warm-up, Alpaca
crypto short limitation, paper/live fill differences, and emergency stop by setting
`TRADINGAGENTS_AUTO_EXECUTE=false` or stopping the process.

Add Alpaca credential names to the test fixture's dummy-key list only where tests construct the
service; never log or snapshot credential values.

- [ ] **Step 4: Run the focused feature suite**

Run:

```bash
pytest \
  tests/test_automation_config.py \
  tests/test_allocation.py \
  tests/test_automation_state.py \
  tests/test_alpaca_execution.py \
  tests/test_automation_cycle.py \
  tests/test_scheduler.py -q
```

Expected: all feature tests pass with no external calls.

- [ ] **Step 5: Run lint on every changed Python file**

Run:

```bash
ruff check \
  tradingagents/default_config.py \
  tradingagents/automation.py \
  tradingagents/automation_state.py \
  tradingagents/allocation.py \
  tradingagents/execution.py \
  tradingagents/scheduler.py \
  cli/main.py \
  tests/test_env_overrides.py \
  tests/test_automation_config.py \
  tests/test_allocation.py \
  tests/test_automation_state.py \
  tests/test_alpaca_execution.py \
  tests/test_automation_cycle.py \
  tests/test_scheduler.py \
  tests/conftest.py
```

Expected: exit code 0 with no findings.

- [ ] **Step 6: Run the complete repository test suite**

Run: `pytest -q`

Expected: exit code 0 with no failed tests. If an existing network-marked test needs credentials,
run the repository's documented marker exclusions and report the exact excluded tests rather than
claiming a complete pass.

- [ ] **Step 7: Inspect the final diff against scope**

Run:

```bash
git status --short
git diff --check
git diff origin/main...HEAD --stat
git diff origin/main...HEAD -- tradingagents/graph cli/main.py
```

Expected: no graph changes; only the two thin new CLI commands in the existing CLI flow; no
unrelated formatting or provider-flow edits.

- [ ] **Step 8: Commit documentation and verification artifacts**

```bash
git add .env.example README.md tests/conftest.py tests/test_automation_config.py
git commit -m "docs: explain alpaca automation workflow"
```

---

## Final Acceptance Checklist

- [ ] Exactly seven env-configured unique symbols are required.
- [ ] Persistent batches rotate `3,2,2` or `2,2,3` without interactive input.
- [ ] Every symbol is analyzed through the unchanged single-symbol graph.
- [ ] Analysis and position tasks default to independent 30-minute cadences.
- [ ] All seven decisions must be fresh before any order is planned or submitted.
- [ ] Conviction targets support positive and negative equity exposure and Hold-to-zero.
- [ ] Managed gross target notional cannot exceed 30% of current positive cash.
- [ ] Current positions and open orders are reconciled instead of accumulating repeated orders.
- [ ] Paper is default; live execution requires exact explicit acknowledgment.
- [ ] Untradable/unshortable assets fail closed without redistributing their allocation.
- [ ] Crypto remains long-or-flat because Alpaca does not permit crypto shorts.
- [ ] Dry-run persists order plans and submits nothing.
- [ ] SQLite leases and deterministic client IDs prevent overlapping/duplicate execution.
- [ ] `tradingagents batch` and `tradingagents automate` run without prompts.
- [ ] Existing `tradingagents analyze` behavior and graph files remain unchanged.
- [ ] `.env.example` and README document local, cron, paper, live, and emergency-stop usage.
- [ ] Focused tests, Ruff, and the complete test suite pass with fresh evidence.
