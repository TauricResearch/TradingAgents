# Portfolio Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent portfolio panel (summary stats + positions table) between the controls bar and the card grid, driven by `portfolioState` and always up-to-date via `portfolio_update` WebSocket events.

**Architecture:** `portfolio.py` gains `day_start_value/date`, `check_day_reset()`, and two new `get_state()` fields (`daily_pnl`, `pct_of_portfolio`). Both `GET /api/portfolio` and `POST /api/trade` call `check_day_reset` before computing state. `dashboard.html` gains a panel div, CSS, and `updatePortfolioPanel()` wired into `handlePortfolioUpdate`.

**Tech Stack:** Python (portfolio.py), FastAPI (backend.py), vanilla JS (dashboard.html), pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `portfolio.py` | Modify | `day_start_value/date` in `__init__/load/save`, `check_day_reset()`, `daily_pnl` + `pct_of_portfolio` in `get_state()` |
| `backend.py` | Modify | Call `check_day_reset(today)` at top of `get_portfolio` and `post_trade` |
| `dashboard.html` | Modify | Panel markup, CSS, `updatePortfolioPanel()`, call it from `handlePortfolioUpdate` |
| `tests/test_portfolio.py` | Modify | Add `TestCheckDayReset` class + extend `TestGetState` with new fields |
| `tests/test_trade_endpoint.py` | Modify | Assert `daily_pnl` in `GET /api/portfolio` and `POST /api/trade` responses |

---

## Task 1: `portfolio.py` — day tracking + new `get_state` fields

**Files:**
- Modify: `portfolio.py`
- Modify: `tests/test_portfolio.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_portfolio.py` (after the existing `TestGetState` class):

```python
class TestCheckDayReset:
    def test_no_reset_when_date_unchanged(self, p):
        p.day_start_value = 50_000.0
        p.day_start_date = "2026-05-11"
        p.check_day_reset("2026-05-11")
        assert p.day_start_value == pytest.approx(50_000.0)  # unchanged

    def test_resets_on_new_date(self, p):
        p.day_start_date = "2026-05-10"
        p.day_start_value = 80_000.0
        # cash is 100_000 from fixture, no positions → total_value = 100_000
        p.check_day_reset("2026-05-11")
        assert p.day_start_value == pytest.approx(100_000.0)
        assert p.day_start_date == "2026-05-11"

    def test_resets_with_position_uses_avg_cost_fallback(self, p):
        p.day_start_date = "2026-05-10"
        p.buy("NVDA", 1_000.0, 100.0)   # cash=99_000, 10 shares @ avg 100
        p.check_day_reset("2026-05-11")  # get_state({}) uses avg_cost → total_value=100_000
        assert p.day_start_value == pytest.approx(100_000.0)

    def test_no_reset_does_not_mutate_date(self, p):
        p.day_start_date = "2026-05-11"
        p.check_day_reset("2026-05-11")
        assert p.day_start_date == "2026-05-11"


class TestGetStateDailyPnlAndPct:
    def test_daily_pnl_zero_at_start(self, p):
        state = p.get_state({})
        assert state["daily_pnl"] == pytest.approx(0.0)

    def test_daily_pnl_positive_when_value_above_start(self, p):
        p.day_start_value = 99_000.0
        state = p.get_state({})
        # cash=100_000, no positions → total_value=100_000, daily_pnl=1_000
        assert state["daily_pnl"] == pytest.approx(1_000.0)

    def test_daily_pnl_negative(self, p):
        p.day_start_value = 101_000.0
        state = p.get_state({})
        assert state["daily_pnl"] == pytest.approx(-1_000.0)

    def test_pct_of_portfolio_correct(self, p):
        p.buy("NVDA", 10_000.0, 100.0)   # 100 shares; cash=90_000
        state = p.get_state({"NVDA": 100.0})
        # total_value = 90_000 + 100*100 = 100_000; mkt_val = 10_000 → 10%
        assert state["positions"]["NVDA"]["pct_of_portfolio"] == pytest.approx(10.0)

    def test_pct_of_portfolio_zero_when_total_value_zero(self, p):
        p.cash = 0.0
        p.positions = {"NVDA": {"shares": 0.0, "avg_cost": 100.0}}
        state = p.get_state({})
        assert state["positions"]["NVDA"]["pct_of_portfolio"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_portfolio.py::TestCheckDayReset tests/test_portfolio.py::TestGetStateDailyPnlAndPct -v
```

Expected: `AttributeError: 'Portfolio' object has no attribute 'day_start_value'`

- [ ] **Step 3: Implement changes in `portfolio.py`**

Replace the entire file `F:\TradingAgents\portfolio.py` with:

```python
import json
import os
from datetime import datetime


class Portfolio:
    def __init__(self):
        self.cash: float = 100_000.0
        self.positions: dict = {}   # ticker -> {"shares": float, "avg_cost": float}
        self.trades: list = []
        self.day_start_value: float = 100_000.0
        self.day_start_date: str = datetime.now().strftime("%Y-%m-%d")

    def load(self, path: str = "portfolio.json") -> None:
        if not os.path.exists(path):
            self.cash = 100_000.0
            self.positions = {}
            self.trades = []
            self.day_start_value = 100_000.0
            self.day_start_date = datetime.now().strftime("%Y-%m-%d")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.cash = float(data.get("cash", 100_000.0))
        self.positions = data.get("positions", {})
        self.trades = data.get("trades", [])
        self.day_start_value = float(data.get("day_start_value", 100_000.0))
        self.day_start_date = data.get("day_start_date", datetime.now().strftime("%Y-%m-%d"))

    def save(self, path: str = "portfolio.json") -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cash": self.cash,
                    "positions": self.positions,
                    "trades": self.trades,
                    "day_start_value": self.day_start_value,
                    "day_start_date": self.day_start_date,
                },
                f, indent=2,
            )
        os.replace(tmp, path)

    def check_day_reset(self, current_date: str) -> None:
        """If the date has rolled over, snapshot today's opening value."""
        if current_date != self.day_start_date:
            state = self.get_state({})  # uses avg_cost as price fallback
            self.day_start_value = state["total_value"]
            self.day_start_date = current_date
            self.save()

    def buy(self, ticker: str, amount_usd: float, price: float) -> dict:
        shares = amount_usd / price
        if ticker in self.positions:
            pos = self.positions[ticker]
            total_shares = pos["shares"] + shares
            new_avg = (pos["shares"] * pos["avg_cost"] + shares * price) / total_shares
            self.positions[ticker] = {"shares": total_shares, "avg_cost": round(new_avg, 4)}
        else:
            self.positions[ticker] = {"shares": shares, "avg_cost": round(price, 4)}
        self.cash -= amount_usd
        self.trades.append({
            "ticker": ticker, "side": "BUY",
            "shares": round(shares, 6), "price": round(price, 4),
            "amount": round(amount_usd, 2),
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return dict(self.positions[ticker])

    def sell(self, ticker: str, amount_usd: float, price: float) -> dict:
        pos = self.positions[ticker]
        shares_to_sell = min(amount_usd / price, pos["shares"])
        actual_amount = shares_to_sell * price
        remaining = pos["shares"] - shares_to_sell
        if remaining < 1e-9:
            del self.positions[ticker]
        else:
            self.positions[ticker] = {"shares": remaining, "avg_cost": pos["avg_cost"]}
        self.cash += actual_amount
        self.trades.append({
            "ticker": ticker, "side": "SELL",
            "shares": round(shares_to_sell, 6), "price": round(price, 4),
            "amount": round(actual_amount, 2),
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return {"shares_sold": round(shares_to_sell, 6), "actual_amount": round(actual_amount, 2)}

    def get_state(self, prices: dict) -> dict:
        positions_out = {}
        total_positions_value = 0.0
        for ticker, pos in self.positions.items():
            current_price = prices.get(ticker, pos["avg_cost"])
            unrealised_pnl = (current_price - pos["avg_cost"]) * pos["shares"]
            cost_basis = pos["avg_cost"] * pos["shares"]
            unrealised_pnl_pct = (unrealised_pnl / cost_basis * 100) if cost_basis else 0.0
            mkt_value = current_price * pos["shares"]
            total_positions_value += mkt_value
            positions_out[ticker] = {
                "shares": pos["shares"],
                "avg_cost": pos["avg_cost"],
                "current_price": round(current_price, 4),
                "unrealised_pnl": round(unrealised_pnl, 2),
                "unrealised_pnl_pct": round(unrealised_pnl_pct, 2),
                "pct_of_portfolio": 0.0,  # filled in below once total_value is known
            }
        total_value = self.cash + total_positions_value
        # Fill pct_of_portfolio now that total_value is computed
        if total_value > 0:
            for ticker, pos_data in positions_out.items():
                mkt = positions_out[ticker]["shares"] * positions_out[ticker]["current_price"]
                pos_data["pct_of_portfolio"] = round(mkt / total_value * 100, 2)
        return {
            "cash": round(self.cash, 2),
            "positions": positions_out,
            "total_value": round(total_value, 2),
            "daily_pnl": round(total_value - self.day_start_value, 2),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_portfolio.py -v
```

Expected: all tests PASS (previous 16 + 9 new = 25 total).

- [ ] **Step 5: Commit**

```
git add portfolio.py tests/test_portfolio.py
git commit -m "feat(panel): add day_start tracking, check_day_reset, daily_pnl, pct_of_portfolio"
```

---

## Task 2: `backend.py` — call `check_day_reset` on both endpoints

**Files:**
- Modify: `backend.py`
- Modify: `tests/test_trade_endpoint.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_trade_endpoint.py` (inside `TestGetPortfolio` and `TestPostTrade` classes):

Add to `TestGetPortfolio`:
```python
    def test_includes_daily_pnl(self, client):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        assert "daily_pnl" in r.json()
        assert r.json()["daily_pnl"] == pytest.approx(0.0)
```

Add a new class after `TestPostTrade`:
```python
class TestDailyPnlInTradeResponse:
    def test_post_trade_response_includes_daily_pnl(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 1000.0})
        assert r.status_code == 200
        data = r.json()
        assert "daily_pnl" in data
        # day_start_value defaults to 100_000; total after buy = 99_000 cash + 10 shares*100 = 100_000
        assert data["daily_pnl"] == pytest.approx(0.0)

    def test_portfolio_response_includes_pct_of_portfolio(self, client):
        import backend
        backend.portfolio.positions = {"NVDA": {"shares": 10.0, "avg_cost": 100.0}}
        backend.portfolio.cash = 90_000.0
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.get("/api/portfolio")
        data = r.json()
        assert "pct_of_portfolio" in data["positions"]["NVDA"]
        # mkt_value = 10 * 100 = 1000; total_value = 90_000 + 1_000 = 91_000
        assert data["positions"]["NVDA"]["pct_of_portfolio"] == pytest.approx(
            1_000.0 / 91_000.0 * 100, abs=0.01
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_trade_endpoint.py::TestGetPortfolio::test_includes_daily_pnl tests/test_trade_endpoint.py::TestDailyPnlInTradeResponse -v
```

Expected: `AssertionError: 'daily_pnl' not in {...}` (field not yet in response)

- [ ] **Step 3: Update `backend.py`**

In `get_portfolio` (around line 341), add `check_day_reset` before the price loop:

Find:
```python
@app.get("/api/portfolio")
def get_portfolio():
    prices = {}
    for t in portfolio.positions:
```

Replace with:
```python
@app.get("/api/portfolio")
def get_portfolio():
    today = datetime.now().strftime("%Y-%m-%d")
    portfolio.check_day_reset(today)
    prices = {}
    for t in portfolio.positions:
```

In `post_trade` (around line 362), add `check_day_reset` before validation:

Find:
```python
@app.post("/api/trade")
async def post_trade(payload: TradePayload):
    t = payload.ticker.upper()
    side = payload.side.upper()
    amount_usd = payload.amount_usd

    if side not in ("BUY", "SELL"):
```

Replace with:
```python
@app.post("/api/trade")
async def post_trade(payload: TradePayload):
    today = datetime.now().strftime("%Y-%m-%d")
    portfolio.check_day_reset(today)
    t = payload.ticker.upper()
    side = payload.side.upper()
    amount_usd = payload.amount_usd

    if side not in ("BUY", "SELL"):
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_trade_endpoint.py tests/test_portfolio.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```
git add backend.py tests/test_trade_endpoint.py
git commit -m "feat(panel): call check_day_reset on portfolio and trade endpoints"
```

---

## Task 3: `dashboard.html` — panel markup, CSS, `updatePortfolioPanel()`

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add panel CSS**

Find `</style>` just before the Chart.js CDN `<script>` tag. Add these styles inside `<style>` immediately before `</style>`:

```css
#portfolio-panel {
  background: var(--bg-card, #111);
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
}
#portfolio-stats {
  display: flex;
  gap: 24px;
  align-items: center;
  font-family: var(--mono);
  font-size: 12px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.pstat-label { color: var(--text-dim); letter-spacing: 0.08em; margin-right: 4px; }
.pstat-value { color: var(--text); }
.pstat-value.pos { color: var(--green); }
.pstat-value.neg { color: var(--red); }
.pstat-value.zero { color: var(--text-dim); }
#portfolio-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--mono);
  font-size: 11px;
}
#portfolio-table th {
  color: var(--text-dim);
  text-align: right;
  padding: 2px 8px;
  font-weight: 400;
  letter-spacing: 0.06em;
  border-bottom: 1px solid var(--border);
}
#portfolio-table th:first-child { text-align: left; }
#portfolio-table td {
  text-align: right;
  padding: 3px 8px;
  color: var(--text);
}
#portfolio-table td:first-child { text-align: left; }
#portfolio-table td.pos { color: var(--green); }
#portfolio-table td.neg { color: var(--red); }
```

- [ ] **Step 2: Add panel markup between controls and grid**

Find (around line 503):
```html
  </div>

  <!-- ── Main grid ─────────────────────────────────────────── -->
  <main id="grid">
```

Replace with:
```html
  </div>

  <!-- ── Portfolio panel ───────────────────────────────────── -->
  <div id="portfolio-panel" style="display:none">
    <div id="portfolio-stats"></div>
    <table id="portfolio-table" style="display:none">
      <thead>
        <tr>
          <th>TICKER</th><th>SHARES</th><th>AVG COST</th><th>PRICE</th>
          <th>P&amp;L $</th><th>P&amp;L %</th><th>MKT VALUE</th><th>% PORT</th>
        </tr>
      </thead>
      <tbody id="portfolio-tbody"></tbody>
    </table>
  </div>

  <!-- ── Main grid ─────────────────────────────────────────── -->
  <main id="grid">
```

- [ ] **Step 3: Add `updatePortfolioPanel()` to the Portfolio section**

Find the `// ── Portfolio ──` section (around line 571). Add `updatePortfolioPanel` as the last function in the section, just before `// ── Charts ──`:

```js
function updatePortfolioPanel() {
  const panel = document.getElementById('portfolio-panel');
  const table = document.getElementById('portfolio-table');
  const tbody = document.getElementById('portfolio-tbody');
  const statsEl = document.getElementById('portfolio-stats');
  if (!panel) return;

  const ps = portfolioState;
  const positions = ps.positions || {};
  const totalValue = ps.total_value || 100000;
  const cash = ps.cash || 100000;
  const hasPositions = Object.keys(positions).length > 0;

  // Hide panel in starting state (no positions and total_value ≈ cash)
  const isStartingState =
    !hasPositions && Math.abs(totalValue - cash) < 0.01;
  panel.style.display = isStartingState ? 'none' : 'block';
  if (isStartingState) return;

  // Helper: format dollar amount with commas
  function fmtUsd(n) {
    return '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function pnlClass(n) {
    return n > 0 ? 'pos' : n < 0 ? 'neg' : 'zero';
  }
  function pnlSign(n) { return n >= 0 ? '+' : '-'; }

  // Summary stats row
  const dailyPnl = ps.daily_pnl || 0;
  const returnPct = (totalValue - 100000) / 100000 * 100;
  statsEl.innerHTML = `
    <span><span class="pstat-label">PORTFOLIO</span><span class="pstat-value">${fmtUsd(totalValue)}</span></span>
    <span><span class="pstat-label">CASH</span><span class="pstat-value">${fmtUsd(cash)}</span></span>
    <span><span class="pstat-label">DAY</span><span class="pstat-value ${pnlClass(dailyPnl)}">${pnlSign(dailyPnl)}${fmtUsd(dailyPnl)}</span></span>
    <span><span class="pstat-label">RETURN</span><span class="pstat-value ${pnlClass(returnPct)}">${pnlSign(returnPct)}${Math.abs(returnPct).toFixed(2)}%</span></span>
  `;

  // Positions table
  if (!hasPositions) {
    table.style.display = 'none';
    return;
  }
  table.style.display = '';
  tbody.innerHTML = Object.entries(positions).map(([ticker, pos]) => {
    const mktValue = pos.shares * pos.current_price;
    const pnlDollarClass = pnlClass(pos.unrealised_pnl);
    const pnlPctClass = pnlClass(pos.unrealised_pnl_pct);
    return `<tr>
      <td>${ticker}</td>
      <td>${pos.shares.toFixed(2)}</td>
      <td>$${pos.avg_cost.toFixed(2)}</td>
      <td>$${pos.current_price.toFixed(2)}</td>
      <td class="${pnlDollarClass}">${pnlSign(pos.unrealised_pnl)}${fmtUsd(pos.unrealised_pnl)}</td>
      <td class="${pnlPctClass}">${pnlSign(pos.unrealised_pnl_pct)}${Math.abs(pos.unrealised_pnl_pct).toFixed(2)}%</td>
      <td>${fmtUsd(mktValue)}</td>
      <td>${(pos.pct_of_portfolio || 0).toFixed(2)}%</td>
    </tr>`;
  }).join('');
}
```

- [ ] **Step 4: Wire `updatePortfolioPanel()` into `handlePortfolioUpdate`**

Find `handlePortfolioUpdate`:
```js
function handlePortfolioUpdate(ev) {
  portfolioState = ev;
  for (const ticker of Object.keys(state)) {
    updateCardPosition(ticker);
  }
  if (ev.last_trade) {
```

Replace with:
```js
function handlePortfolioUpdate(ev) {
  portfolioState = ev;
  updatePortfolioPanel();
  for (const ticker of Object.keys(state)) {
    updateCardPosition(ticker);
  }
  if (ev.last_trade) {
```

- [ ] **Step 5: Smoke test in browser**

1. Kill port 8000: `Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }`
2. Start backend: run `python F:/TradingAgents/backend.py` in the background
3. Open `http://localhost:8000` — panel should be **hidden** (no trades yet)
4. Add NVDA, type `2000` in the input, click BUY — panel should appear with PORTFOLIO / CASH / DAY / RETURN stats and NVDA row in the table
5. Verify DAY shows `$0.00` in dim-white on first load (day_start_value = 100000, total_value = 100000 after balanced buy)
6. Verify % PORT column shows a non-zero value

- [ ] **Step 6: Run all backend tests**

```
pytest tests/test_portfolio.py tests/test_trade_endpoint.py tests/test_chart_endpoint.py -q
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```
git add dashboard.html
git commit -m "feat(panel): add portfolio panel with stats row and positions table"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `day_start_value` / `day_start_date` in `__init__`, `load`, `save` | Task 1 |
| `check_day_reset(current_date)` — resets on date change, saves | Task 1 |
| `daily_pnl` in `get_state()` output | Task 1 |
| `pct_of_portfolio` per position, guarded against divide-by-zero | Task 1 |
| `check_day_reset` called before state compute in `GET /api/portfolio` | Task 2 |
| `check_day_reset` called before validation in `POST /api/trade` | Task 2 |
| Panel markup between controls and grid, hidden by default | Task 3 |
| Float epsilon hide condition (`< 0.01`) | Task 3 |
| Summary stats: PORTFOLIO, CASH, DAY (daily_pnl), RETURN (vs 100k) | Task 3 |
| DAY dim-white when `daily_pnl === 0` | Task 3 (`pnlClass` returns `'zero'`) |
| Positions table with all 8 columns | Task 3 |
| Table hidden when no positions | Task 3 |
| `updatePortfolioPanel()` called from `handlePortfolioUpdate` | Task 3 |
| CSS for panel, stats row, table | Task 3 |
