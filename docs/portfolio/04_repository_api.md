# Repository Layer API

<!-- Last verified: 2026-03-20 -->

This document is the authoritative API reference for all classes in
`tradingagents/portfolio/`.

---

## Exception Hierarchy

Defined in `tradingagents/portfolio/exceptions.py`.

```
PortfolioError                  # Base exception for all portfolio errors
├── PortfolioNotFoundError      # Requested portfolio_id does not exist
├── HoldingNotFoundError        # Requested holding (portfolio_id, ticker) does not exist
├── DuplicatePortfolioError     # Portfolio name or ID already exists
├── InsufficientCashError       # Not enough cash for a BUY trade
├── InsufficientSharesError     # Not enough shares for a SELL trade
├── ConstraintViolationError    # PM constraint breached (position size, sector, cash)
└── ReportStoreError            # Filesystem read/write failure
```

### Usage

```python
from tradingagents.portfolio.exceptions import (
    PortfolioError,
    PortfolioNotFoundError,
    InsufficientCashError,
    InsufficientSharesError,
)

try:
    repo.add_holding(portfolio_id, "AAPL", shares=100, price=195.50)
except InsufficientCashError as e:
    print(f"Cannot buy: {e}")
```

---

## `SupabaseClient`

Location: `tradingagents/portfolio/supabase_client.py`

Thin wrapper around the `supabase-py` client that:
- Manages a singleton connection
- Translates HTTP / Supabase errors into domain exceptions
- Converts raw DB rows into model instances

### Constructor / Singleton

```python
client = SupabaseClient.get_instance()
# or
client = SupabaseClient(url=SUPABASE_URL, key=SUPABASE_KEY)
```

### Portfolio Methods

```python
def create_portfolio(self, portfolio: Portfolio) -> Portfolio:
    """Insert a new portfolio row.

    Raises:
        DuplicatePortfolioError: If portfolio_id already exists.
    """

def get_portfolio(self, portfolio_id: str) -> Portfolio:
    """Fetch a portfolio by ID.

    Raises:
        PortfolioNotFoundError: If no portfolio has that ID.
    """

def list_portfolios(self) -> list[Portfolio]:
    """Return all portfolios ordered by created_at DESC."""

def update_portfolio(self, portfolio: Portfolio) -> Portfolio:
    """Update mutable fields (cash, report_path, metadata, updated_at).

    Raises:
        PortfolioNotFoundError: If portfolio_id does not exist.
    """

def delete_portfolio(self, portfolio_id: str) -> None:
    """Delete a portfolio and all its holdings, trades, and snapshots (CASCADE).

    Raises:
        PortfolioNotFoundError: If portfolio_id does not exist.
    """
```

### Holdings Methods

```python
def upsert_holding(self, holding: Holding) -> Holding:
    """Insert or update a holding row (upsert on portfolio_id + ticker).

    Returns the holding with updated DB-assigned fields (updated_at).
    """

def get_holding(self, portfolio_id: str, ticker: str) -> Holding | None:
    """Return the holding for (portfolio_id, ticker), or None if not found."""

def list_holdings(self, portfolio_id: str) -> list[Holding]:
    """Return all holdings for a portfolio ordered by cost_basis DESC."""

def delete_holding(self, portfolio_id: str, ticker: str) -> None:
    """Delete the holding for (portfolio_id, ticker).

    Raises:
        HoldingNotFoundError: If no such holding exists.
    """
```

### Trades Methods

```python
def record_trade(self, trade: Trade) -> Trade:
    """Insert a new trade record. Immutable — no update method.

    Returns the trade with DB-assigned trade_id and trade_date.
    """

def list_trades(
    self,
    portfolio_id: str,
    ticker: str | None = None,
    limit: int = 100,
) -> list[Trade]:
    """Return recent trades for a portfolio, newest first.

    Args:
        portfolio_id: Filter by portfolio.
        ticker: Optional additional filter by ticker symbol.
        limit: Maximum number of rows to return.
    """
```

### Snapshots Methods

```python
def save_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
    """Insert a new snapshot. Immutable — no update method."""

def get_latest_snapshot(self, portfolio_id: str) -> PortfolioSnapshot | None:
    """Return the most recent snapshot, or None if none exist."""

def list_snapshots(
    self,
    portfolio_id: str,
    limit: int = 30,
) -> list[PortfolioSnapshot]:
    """Return snapshots newest-first up to limit."""
```

---

## `ReportStore`

Location: `tradingagents/portfolio/report_store.py`

Filesystem document store for all non-transactional portfolio artifacts.
Integrates with the existing `tradingagents/report_paths.py` path conventions.

### Constructor

```python
store = ReportStore(base_dir: str | Path = "reports")
```

`base_dir` defaults to `"reports"` (relative to CWD). Override via
`PORTFOLIO_DATA_DIR` env var or config.

### Scan Methods

```python
def save_scan(self, date: str, data: dict) -> Path:
    """Save macro scan summary JSON.

    Path: {base_dir}/daily/{date}/market/macro_scan_summary.json

    Returns the path written.
    """

def load_scan(self, date: str) -> dict | None:
    """Load macro scan summary. Returns None if file doesn't exist."""
```

### Analysis Methods

```python
def save_analysis(self, date: str, ticker: str, data: dict) -> Path:
    """Save per-ticker analysis report as JSON.

    Path: {base_dir}/daily/{date}/{TICKER}/complete_report.json
    """

def load_analysis(self, date: str, ticker: str) -> dict | None:
    """Load per-ticker analysis JSON. Returns None if file doesn't exist."""
```

### Holding Review Methods

```python
def save_holding_review(self, date: str, ticker: str, data: dict) -> Path:
    """Save holding reviewer output for one ticker.

    Path: {base_dir}/daily/{date}/portfolio/{TICKER}_holding_review.json
    """

def load_holding_review(self, date: str, ticker: str) -> dict | None:
    """Load holding review. Returns None if file doesn't exist."""
```

### Risk Metrics Methods

```python
def save_risk_metrics(
    self,
    date: str,
    portfolio_id: str,
    data: dict,
) -> Path:
    """Save risk computation results.

    Path: {base_dir}/daily/{date}/portfolio/{portfolio_id}_risk_metrics.json
    """

def load_risk_metrics(self, date: str, portfolio_id: str) -> dict | None:
    """Load risk metrics. Returns None if file doesn't exist."""
```

### PM Decision Methods

```python
def save_pm_decision(
    self,
    date: str,
    portfolio_id: str,
    data: dict,
    markdown: str | None = None,
) -> Path:
    """Save PM agent decision.

    JSON path: {base_dir}/daily/{date}/portfolio/{portfolio_id}_pm_decision.json
    MD path:   {base_dir}/daily/{date}/portfolio/{portfolio_id}_pm_decision.md
               (written only when markdown is not None)

    Returns JSON path.
    """

def load_pm_decision(self, date: str, portfolio_id: str) -> dict | None:
    """Load PM decision JSON. Returns None if file doesn't exist."""

def list_pm_decisions(self, portfolio_id: str) -> list[Path]:
    """Return all saved PM decision JSON paths for portfolio_id, newest first.

    Scans {base_dir}/daily/*/portfolio/{portfolio_id}_pm_decision.json
    """
```

---

## `PortfolioRepository`

Location: `tradingagents/portfolio/repository.py`

Unified façade that combines `SupabaseClient` and `ReportStore`.
This is the **primary interface** for all portfolio operations — callers should
not interact with `SupabaseClient` or `ReportStore` directly.

### Constructor

```python
repo = PortfolioRepository(
    client: SupabaseClient | None = None,   # uses singleton if None
    store: ReportStore | None = None,       # uses default if None
    config: dict | None = None,             # uses get_portfolio_config() if None
)
```

### Portfolio Lifecycle

```python
def create_portfolio(
    self,
    name: str,
    initial_cash: float,
    currency: str = "USD",
) -> Portfolio:
    """Create a new portfolio with the given starting capital.

    Generates a UUID for portfolio_id. Sets cash = initial_cash.

    Raises:
        DuplicatePortfolioError: If name is already in use.
        ValueError: If initial_cash <= 0.
    """

def get_portfolio(self, portfolio_id: str) -> Portfolio:
    """Fetch portfolio by ID.

    Raises:
        PortfolioNotFoundError: If not found.
    """

def get_portfolio_with_holdings(
    self,
    portfolio_id: str,
    prices: dict[str, float] | None = None,
) -> tuple[Portfolio, list[Holding]]:
    """Fetch portfolio + all holdings, optionally enriched with current prices.

    Args:
        portfolio_id: Target portfolio.
        prices: Optional dict of {ticker: current_price}. When provided,
                holdings are enriched and portfolio.total_value is computed.

    Returns:
        (Portfolio, list[Holding]) — Portfolio.enrich() called if prices given.
    """
```

### Holdings Management

```python
def add_holding(
    self,
    portfolio_id: str,
    ticker: str,
    shares: float,
    price: float,
    sector: str | None = None,
    industry: str | None = None,
) -> Holding:
    """Buy shares and update portfolio cash and holdings.

    Business logic:
    - Raises InsufficientCashError if portfolio.cash < shares * price
    - If holding already exists: updates avg_cost = weighted average
    - portfolio.cash -= shares * price
    - Records a BUY trade automatically

    Returns the updated/created Holding.
    """

def remove_holding(
    self,
    portfolio_id: str,
    ticker: str,
    shares: float,
    price: float,
) -> Holding | None:
    """Sell shares and update portfolio cash and holdings.

    Business logic:
    - Raises HoldingNotFoundError if no holding exists for ticker
    - Raises InsufficientSharesError if holding.shares < shares
    - If shares == holding.shares: deletes the holding row, returns None
    - Otherwise: decrements holding.shares (avg_cost unchanged on sell)
    - portfolio.cash += shares * price
    - Records a SELL trade automatically

    Returns the updated Holding (or None if fully sold).
    """
```

### Snapshot Management

```python
def take_snapshot(self, portfolio_id: str, prices: dict[str, float]) -> PortfolioSnapshot:
    """Take an immutable snapshot of the current portfolio state.

    Enriches all holdings with current prices, computes total_value,
    then persists to Supabase via SupabaseClient.save_snapshot().

    Returns the saved PortfolioSnapshot.
    """
```

### Report Convenience Methods

```python
def save_pm_decision(
    self,
    portfolio_id: str,
    date: str,
    decision: dict,
    markdown: str | None = None,
) -> Path:
    """Delegate to ReportStore.save_pm_decision and update portfolio.report_path."""

def load_pm_decision(self, portfolio_id: str, date: str) -> dict | None:
    """Delegate to ReportStore.load_pm_decision."""

def save_risk_metrics(
    self,
    portfolio_id: str,
    date: str,
    metrics: dict,
) -> Path:
    """Delegate to ReportStore.save_risk_metrics."""

def load_risk_metrics(self, portfolio_id: str, date: str) -> dict | None:
    """Delegate to ReportStore.load_risk_metrics."""
```

---

## Avg Cost Basis Calculation

When buying more shares of an existing holding, the average cost basis is updated
using the **weighted average** formula:

```
new_avg_cost = (old_shares * old_avg_cost + new_shares * new_price)
               / (old_shares + new_shares)
```

When **selling** shares, the average cost basis is **not changed** — only `shares`
is decremented. This follows the FIFO approximation used by most brokerages for
tax-reporting purposes.

---

## Cash Management Rules

| Operation | Effect on `portfolio.cash` |
|-----------|---------------------------|
| BUY `n` shares at `p` | `cash -= n * p` |
| SELL `n` shares at `p` | `cash += n * p` |
| Snapshot | Read-only |
| Portfolio creation | `cash = initial_cash` |

Cash can never go below 0 after a trade. `add_holding` raises
`InsufficientCashError` if the trade would exceed available cash.

---

## Example Usage

```python
from tradingagents.portfolio import PortfolioRepository

repo = PortfolioRepository()

# Create a portfolio
portfolio = repo.create_portfolio("Main Portfolio", initial_cash=100_000.0)

# Buy some shares
holding = repo.add_holding(
    portfolio.portfolio_id,
    ticker="AAPL",
    shares=50,
    price=195.50,
    sector="Technology",
)
# portfolio.cash is now 100_000 - 50 * 195.50 = 90_225.00
# holding.avg_cost = 195.50

# Buy more (avg cost update)
holding = repo.add_holding(
    portfolio.portfolio_id,
    ticker="AAPL",
    shares=25,
    price=200.00,
)
# holding.avg_cost = (50*195.50 + 25*200.00) / 75 = 197.00

# Sell half
holding = repo.remove_holding(
    portfolio.portfolio_id,
    ticker="AAPL",
    shares=37,
    price=205.00,
)
# portfolio.cash += 37 * 205.00 = 7_585.00

# Take snapshot
prices = {"AAPL": 205.00}
snapshot = repo.take_snapshot(portfolio.portfolio_id, prices)

# Save PM decision
repo.save_pm_decision(
    portfolio.portfolio_id,
    date="2026-03-20",
    decision={"sells": [], "buys": [...], "rationale": "..."},
)
```
