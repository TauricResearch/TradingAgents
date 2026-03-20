# Data Models — Full Specification

<!-- Last verified: 2026-03-20 -->

All models live in `tradingagents/portfolio/models.py` as Python `dataclass` types.
They must be fully type-annotated and support lossless `to_dict` / `from_dict`
round-trips.

---

## `Portfolio`

Represents a single managed portfolio (one user may eventually have multiple).

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `portfolio_id` | `str` | Yes | UUID, primary key |
| `name` | `str` | Yes | Human-readable name, e.g. "Main Portfolio" |
| `cash` | `float` | Yes | Available cash balance in USD |
| `initial_cash` | `float` | Yes | Starting capital (immutable after creation) |
| `currency` | `str` | Yes | ISO 4217 code, default `"USD"` |
| `created_at` | `str` | Yes | ISO-8601 UTC datetime string |
| `updated_at` | `str` | Yes | ISO-8601 UTC datetime string |
| `report_path` | `str \| None` | No | Filesystem path to today's portfolio report dir |
| `metadata` | `dict` | No | Free-form JSON for agent notes / tags |

### Computed / Derived Fields (not stored in DB)

| Field | Type | Description |
|-------|------|-------------|
| `total_value` | `float` | `cash` + sum of all holding `current_value` |
| `equity_value` | `float` | sum of all holding `current_value` |
| `cash_pct` | `float` | `cash / total_value` |

### Methods

```python
def to_dict(self) -> dict:
    """Serialise all stored fields to a flat dict suitable for JSON / Supabase insert."""

def from_dict(cls, data: dict) -> "Portfolio":
    """Deserialise from a DB row or JSON dict. Missing optional fields default gracefully."""

def enrich(self, holdings: list["Holding"]) -> "Portfolio":
    """Compute total_value, equity_value, cash_pct from the provided holdings list."""
```

---

## `Holding`

Represents a single open position within a portfolio.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `holding_id` | `str` | Yes | UUID, primary key |
| `portfolio_id` | `str` | Yes | FK → portfolios.portfolio_id |
| `ticker` | `str` | Yes | Stock ticker symbol, e.g. `"AAPL"` |
| `shares` | `float` | Yes | Number of shares held |
| `avg_cost` | `float` | Yes | Average cost basis per share (USD) |
| `sector` | `str \| None` | No | GICS sector name |
| `industry` | `str \| None` | No | GICS industry name |
| `created_at` | `str` | Yes | ISO-8601 UTC datetime string |
| `updated_at` | `str` | Yes | ISO-8601 UTC datetime string |

### Runtime-Computed Fields (not stored in DB)

These are populated by `enrich()` and available for agent/analysis use:

| Field | Type | Description |
|-------|------|-------------|
| `current_price` | `float \| None` | Latest market price per share |
| `current_value` | `float \| None` | `current_price * shares` |
| `cost_basis` | `float` | `avg_cost * shares` |
| `unrealized_pnl` | `float \| None` | `current_value - cost_basis` |
| `unrealized_pnl_pct` | `float \| None` | `unrealized_pnl / cost_basis` (0 if cost_basis == 0) |
| `weight` | `float \| None` | `current_value / portfolio_total_value` |

### Methods

```python
def to_dict(self) -> dict:
    """Serialise stored fields only (not runtime-computed fields)."""

def from_dict(cls, data: dict) -> "Holding":
    """Deserialise from DB row or JSON dict."""

def enrich(self, current_price: float, portfolio_total_value: float) -> "Holding":
    """
    Populate runtime-computed fields in-place and return self.

    Args:
        current_price: Latest market price for this ticker.
        portfolio_total_value: Total portfolio value (cash + equity) for weight calc.
    """
```

---

## `Trade`

Immutable record of a single mock trade execution. Never modified after creation.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trade_id` | `str` | Yes | UUID, primary key |
| `portfolio_id` | `str` | Yes | FK → portfolios.portfolio_id |
| `ticker` | `str` | Yes | Stock ticker symbol |
| `action` | `str` | Yes | `"BUY"` or `"SELL"` |
| `shares` | `float` | Yes | Number of shares traded |
| `price` | `float` | Yes | Execution price per share (USD) |
| `total_value` | `float` | Yes | `shares * price` |
| `trade_date` | `str` | Yes | ISO-8601 UTC datetime of execution |
| `rationale` | `str \| None` | No | PM agent rationale for this trade |
| `signal_source` | `str \| None` | No | `"scanner"`, `"holding_review"`, `"pm_agent"` |
| `metadata` | `dict` | No | Free-form JSON |

### Methods

```python
def to_dict(self) -> dict:
    """Serialise all fields."""

def from_dict(cls, data: dict) -> "Trade":
    """Deserialise from DB row or JSON dict."""
```

---

## `PortfolioSnapshot`

Point-in-time immutable record of the portfolio state. Taken after every trade
execution session (Phase 5 of the workflow). Used for performance tracking.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `snapshot_id` | `str` | Yes | UUID, primary key |
| `portfolio_id` | `str` | Yes | FK → portfolios.portfolio_id |
| `snapshot_date` | `str` | Yes | ISO-8601 UTC datetime |
| `total_value` | `float` | Yes | Cash + equity at snapshot time |
| `cash` | `float` | Yes | Cash balance at snapshot time |
| `equity_value` | `float` | Yes | Sum of position values at snapshot time |
| `num_positions` | `int` | Yes | Number of open positions |
| `holdings_snapshot` | `list[dict]` | Yes | Serialised list of holding dicts (as-of) |
| `metadata` | `dict` | No | Free-form JSON (e.g. PM decision path) |

### Methods

```python
def to_dict(self) -> dict:
    """Serialise all fields. `holdings_snapshot` is already a list[dict]."""

def from_dict(cls, data: dict) -> "PortfolioSnapshot":
    """Deserialise. `holdings_snapshot` parsed from JSON string if needed."""
```

---

## Serialisation Contract

### `to_dict()`

- Returns a flat `dict[str, Any]`
- All values must be JSON-serialisable (str, int, float, bool, list, dict, None)
- `datetime` objects → ISO-8601 string (`isoformat()`)
- `Decimal` values → `float`
- Runtime-computed fields (`current_price`, `weight`, etc.) are **excluded**
- Complex nested fields (`metadata`, `holdings_snapshot`) are included as-is

### `from_dict()`

- Class method; must be callable as `Portfolio.from_dict(row)`
- Handles missing optional fields with `data.get("field", default)`
- Does **not** raise on extra keys in `data`
- Does **not** populate runtime-computed fields (call `enrich()` separately)

---

## Enrichment Logic

### `Holding.enrich(current_price, portfolio_total_value)`

```python
self.current_price = current_price
self.current_value = current_price * self.shares
self.cost_basis = self.avg_cost * self.shares
self.unrealized_pnl = self.current_value - self.cost_basis
if self.cost_basis > 0:
    self.unrealized_pnl_pct = self.unrealized_pnl / self.cost_basis
else:
    self.unrealized_pnl_pct = 0.0
if portfolio_total_value > 0:
    self.weight = self.current_value / portfolio_total_value
else:
    self.weight = 0.0
return self
```

### `Portfolio.enrich(holdings)`

```python
self.equity_value = sum(h.current_value or 0 for h in holdings)
self.total_value = self.cash + self.equity_value
if self.total_value > 0:
    self.cash_pct = self.cash / self.total_value
else:
    self.cash_pct = 1.0
return self
```

---

## Type Alias Reference

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
```

All `metadata` fields use `dict[str, Any]` with `field(default_factory=dict)`.
All optional fields default to `None` unless noted otherwise.
