# Portfolio Panel — Design Spec

**Date:** 2026-05-11
**Status:** Approved

---

## Overview

Add a persistent portfolio panel between the controls bar and the card grid. It shows a summary stats row (Total Value, Cash, Daily P&L, Total Return %) and an open positions table (7 columns). The panel is hidden in the starting state (no positions, no trades) and visible otherwise. All data comes from `portfolioState`, populated by `GET /api/portfolio` on load and `portfolio_update` WebSocket events on trades.

---

## Architecture

```
portfolio.py   ← add day_start_value/day_start_date, check_day_reset(), pct_of_portfolio
backend.py     ← call check_day_reset on GET /api/portfolio and POST /api/trade
dashboard.html ← portfolio-panel markup, CSS, updatePortfolioPanel()
```

---

## Backend

### `portfolio.json` additions

```json
{
  "cash": 100000.0,
  "positions": {},
  "trades": [],
  "day_start_value": 100000.0,
  "day_start_date": "2026-05-11"
}
```

Both fields default to `100000.0` / today when absent from JSON (first load of an existing file).

### `Portfolio` class changes

**`load()`** — After loading JSON, if `day_start_value` or `day_start_date` is absent, initialise:

```python
self.day_start_value = float(data.get("day_start_value", 100_000.0))
self.day_start_date  = data.get("day_start_date", datetime.now().strftime("%Y-%m-%d"))
```

**`save()`** — Include `day_start_value` and `day_start_date` in the serialised dict.

**`check_day_reset(current_date: str) -> None`**

```python
def check_day_reset(self, current_date: str) -> None:
    """If the date has rolled over, snapshot today's opening value."""
    if current_date != self.day_start_date:
        state = self.get_state({})  # uses avg_cost as price fallback — good enough for day snapshot
        self.day_start_value = state["total_value"]
        self.day_start_date  = current_date
        self.save()
```

Called at the top of both `GET /api/portfolio` and `POST /api/trade` before any state computation.

> `check_day_reset` must be called **before** `get_state()` in each endpoint so `daily_pnl` reflects today's delta, not yesterday's.

**`get_state(prices: dict) -> dict`** — Two additions:

1. `daily_pnl` at the top level:

```python
"daily_pnl": round(total_value - self.day_start_value, 2)
```

2. `pct_of_portfolio` per position (guarded against divide-by-zero):

```python
"pct_of_portfolio": round(
    (current_price * pos["shares"]) / total_value * 100, 2
) if total_value > 0 else 0.0,
```

### Endpoint changes

**`GET /api/portfolio`** — Add at top, before price fetch:

```python
today = datetime.now().strftime("%Y-%m-%d")
portfolio.check_day_reset(today)
```

**`POST /api/trade`** — Add at top, before validation:

```python
today = datetime.now().strftime("%Y-%m-%d")
portfolio.check_day_reset(today)
```

---

## Frontend

### Panel markup

Insert between `</div><!-- end .controls -->` and `<main id="grid">`:

```html
<div id="portfolio-panel" style="display:none">
  <div id="portfolio-stats"></div>
  <table id="portfolio-table">
    <thead>
      <tr>
        <th>TICKER</th><th>SHARES</th><th>AVG COST</th><th>PRICE</th>
        <th>P&amp;L $</th><th>P&amp;L %</th><th>MKT VALUE</th><th>% PORT</th>
      </tr>
    </thead>
    <tbody id="portfolio-tbody"></tbody>
  </table>
</div>
```

### Hide / show condition

Panel is hidden when portfolio is in the exact starting state:

```js
const isStartingState =
  Object.keys(portfolioState.positions || {}).length === 0 &&
  Math.abs((portfolioState.total_value || 100000) - (portfolioState.cash || 100000)) < 0.01;
document.getElementById('portfolio-panel').style.display = isStartingState ? 'none' : 'block';
```

### `updatePortfolioPanel()`

Called from `handlePortfolioUpdate` and `loadPortfolio` (after `portfolioState` is set).

**Summary stats row** — renders into `#portfolio-stats`:

```
PORTFOLIO   $101,234.56   CASH $94,872.10   DAY +$84.23   RETURN +1.23%
```

- **PORTFOLIO**: `portfolioState.total_value` formatted as `$N,NNN.NN`
- **CASH**: `portfolioState.cash`
- **DAY**: `portfolioState.daily_pnl` — green if `> 0`, red if `< 0`, dim-white if `=== 0` (shown as `$0.00` on first load)
- **RETURN**: `(total_value - 100000) / 100000 * 100` — green/red/dim-white by same rule. `100000` is the fixed starting capital hardcoded in `Portfolio.__init__`.

**Positions table** — rebuilds `#portfolio-tbody` rows from `portfolioState.positions`:

| Column | Source | Format |
|---|---|---|
| TICKER | key | uppercase |
| SHARES | `pos.shares` | `toFixed(2)` |
| AVG COST | `pos.avg_cost` | `$N.NN` |
| PRICE | `pos.current_price` | `$N.NN` |
| P&L $ | `pos.unrealised_pnl` | `+$N.NN` / `-$N.NN`, green/red |
| P&L % | `pos.unrealised_pnl_pct` | `+N.NN%` / `-N.NN%`, green/red |
| MKT VALUE | `pos.shares * pos.current_price` | `$N,NNN.NN` |
| % PORT | `pos.pct_of_portfolio` | `N.NN%` |

Table hidden when `Object.keys(portfolioState.positions).length === 0`.

### CSS

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

---

## Data flow

```
GET /api/portfolio
  → check_day_reset(today)
  → get_state(prices)  ← includes daily_pnl, pct_of_portfolio
  → JSON response
  → loadPortfolio() → handlePortfolioUpdate(data) → updatePortfolioPanel()

POST /api/trade
  → check_day_reset(today)
  → portfolio.buy/sell → portfolio.save()
  → get_state(prices)  ← includes daily_pnl, pct_of_portfolio
  → broadcast(portfolio_update)
  → handlePortfolioUpdate(ev) → updatePortfolioPanel()
```

---

## Files changed

| File | Action | Responsibility |
|---|---|---|
| `portfolio.py` | Modify | `day_start_value/date` fields, `check_day_reset()`, `daily_pnl` + `pct_of_portfolio` in `get_state()` |
| `backend.py` | Modify | Call `check_day_reset` on both endpoints |
| `dashboard.html` | Modify | Panel markup, CSS, `updatePortfolioPanel()` called from existing hooks |
| `tests/test_portfolio.py` | Modify | Tests for `check_day_reset` and new `get_state` fields |
| `tests/test_trade_endpoint.py` | Modify | Assert `daily_pnl` and `pct_of_portfolio` in response shapes |
