# Paper Trading Simulator — Design Spec

**Date:** 2026-05-08
**Status:** Approved

---

## Overview

Add a paper trading simulator to the dashboard. Users start with $100k virtual cash and can BUY/SELL any watched ticker. Portfolio state persists to `portfolio.json`. Trades execute at live yfinance prices. Each card shows BUY/SELL controls and a position summary line. After every trade the backend broadcasts a `portfolio_update` WebSocket event with the full portfolio snapshot so all connected clients update without a follow-up REST call.

---

## Architecture

```
portfolio.py   ←  pure state logic (no HTTP)
backend.py     ←  3 REST endpoints + broadcast after trade
dashboard.html ←  trade bar on each card + portfolio_update handler
portfolio.json ←  persisted state (cash, positions, trades)
```

---

## Data Model

### `portfolio.json`

```json
{
  "cash": 100000.0,
  "positions": {
    "NVDA": { "shares": 12.0, "avg_cost": 112.40 }
  },
  "trades": [
    {
      "ticker": "AAPL",
      "side": "BUY",
      "shares": 8.3,
      "price": 182.10,
      "amount": 1511.43,
      "timestamp": "2026-05-08T14:32:00"
    }
  ]
}
```

If the file is absent on startup, initialise with `cash=100000.0`, empty `positions` and `trades`.

---

## `portfolio.py` — `Portfolio` class

### Methods

**`load(path="portfolio.json")`**
Read and deserialise from disk. If file absent, initialise with `$100k` cash.

**`save(path="portfolio.json")`**
Serialise and write atomically. Called after every `buy` or `sell`.

**`buy(ticker, amount_usd, price) → dict`**
- `shares = amount_usd / price` (fractional shares allowed)
- Update weighted average cost: `new_avg = (old_shares * old_avg + shares * price) / (old_shares + shares)`
- Deduct `amount_usd` from cash (caller must pre-validate cash ≥ amount_usd)
- Append trade record to `trades`
- Return updated position: `{"shares", "avg_cost"}`

**`sell(ticker, amount_usd, price) → dict`**
- `shares_to_sell = amount_usd / price`
- Cap at full position: `shares_to_sell = min(shares_to_sell, position["shares"])`
- Actual amount received: `actual_amount = shares_to_sell * price`
- Add `actual_amount` to cash
- If position reaches zero shares, remove from positions dict
- Append trade record
- Return `{"shares_sold", "actual_amount"}`

**`get_state(prices: dict[str, float]) → dict`**
Compute and return the full snapshot:
```python
{
    "cash": float,
    "positions": {
        ticker: {
            "shares": float,
            "avg_cost": float,
            "current_price": float,          # from prices dict
            "unrealised_pnl": float,          # (current_price - avg_cost) * shares
            "unrealised_pnl_pct": float,      # unrealised_pnl / (avg_cost * shares) * 100
        }
    },
    "total_value": float,   # cash + sum(shares * current_price)
}
```
If a ticker in positions is absent from `prices`, use `avg_cost` as fallback (no P&L change shown).

---

## Backend — `backend.py`

### Module-level

```python
from portfolio import Portfolio
portfolio = Portfolio()
portfolio.load()
```

### New endpoints

**`GET /api/portfolio`**

Fetch live prices for all held tickers via `yf.Ticker(t).fast_info["last_price"]` (one call per held position). Call `portfolio.get_state(prices)`. Return the full state snapshot. Returns `{"cash": 100000.0, "positions": {}, "total_value": 100000.0}` when no positions held.

**`GET /api/price/{ticker}`**

```json
{ "ticker": "NVDA", "price": 134.52 }
```

Fetches `yf.Ticker(ticker.upper()).fast_info["last_price"]`. Returns `404 {"error": "Price unavailable"}` on failure.

**`POST /api/trade`** (`async def` — calls `await broadcast`)

Request body:
```json
{ "ticker": "NVDA", "side": "BUY", "amount_usd": 5000.0 }
```

Steps:
1. Uppercase ticker, validate `side` ∈ `{"BUY", "SELL"}`, validate `amount_usd > 0`
2. Fetch live price via `yf.Ticker(ticker).fast_info["last_price"]` — return `503` on failure
3. **BUY**: validate `amount_usd ≤ portfolio.cash` — return `400 {"error": "Insufficient cash"}` if not
4. **SELL**: validate position exists — return `400 {"error": "No position"}` if not
5. Execute `portfolio.buy` or `portfolio.sell`
6. `portfolio.save()`
7. Fetch prices for all positions, build `portfolio_update` payload (see below)
8. `await broadcast(portfolio_update_payload)`
9. Return the same payload with `status_code=200`

### `portfolio_update` WebSocket event

```json
{
  "type": "portfolio_update",
  "cash": 94872.10,
  "positions": {
    "NVDA": {
      "shares": 37.2,
      "avg_cost": 134.21,
      "current_price": 136.80,
      "unrealised_pnl": 96.35,
      "unrealised_pnl_pct": 1.93
    }
  },
  "total_value": 100961.46,
  "last_trade": {
    "ticker": "NVDA",
    "side": "BUY",
    "shares": 37.2,
    "price": 134.52,
    "amount": 5003.90,
    "timestamp": "2026-05-08T14:32:00"
  }
}
```

---

## Frontend — `dashboard.html`

### Page load

Call `GET /api/portfolio` once after WebSocket connects. Store result in `portfolioState = {}`. Update all visible cards from the response.

### Trade bar markup (inside each card, below `.chart-container`)

```html
<div class="trade-bar" id="trade-bar-{ticker}">
  <div class="trade-controls">
    <span class="trade-currency">$</span>
    <input type="number" class="trade-input" id="trade-input-{ticker}"
           placeholder="Amount" min="1" step="1" />
    <button class="btn-buy" id="btn-buy-{ticker}" onclick="executeTrade('{ticker}','BUY')">BUY</button>
    <button class="btn-sell" id="btn-sell-{ticker}" onclick="executeTrade('{ticker}','SELL')" disabled>SELL</button>
  </div>
  <div class="trade-position" id="trade-position-{ticker}" style="display:none"></div>
</div>
```

### `executeTrade(ticker, side)`

1. Read `amount_usd` from `#trade-input-{ticker}`
2. **SELL with empty input**: if `side === 'SELL'` and input is empty, use `position.shares * position.current_price` as `amount_usd` (full position value)
3. **Cash validation**: if `side === 'BUY'` and `amount_usd > portfolioState.cash`, show error toast `"Insufficient cash"` and return
4. **Button lockout**: disable both BUY and SELL buttons, set button text to `"…"` while awaiting response
5. **30% warning**: if `side === 'BUY'`:
   - `existing = portfolioState.positions[ticker]?.shares * portfolioState.positions[ticker]?.current_price ?? 0`
   - `projected = (existing + amount_usd) / portfolioState.total_value`
   - If `projected > 0.30`, show yellow toast `"{ticker} would exceed 30% of portfolio"` with Confirm/Cancel. On Cancel, re-enable buttons and return
6. `POST /api/trade` with `{ticker, side, amount_usd}`
7. On error response: show error toast with message, re-enable buttons
8. On success: buttons re-enabled (state updated via `portfolio_update` WebSocket event)

### `handlePortfolioUpdate(ev)`

Called from `handleEvent` when `ev.type === 'portfolio_update'`. Steps:
1. `portfolioState = ev` (store full payload)
2. For each watched ticker card: update position summary line and SELL button state **immediately** (before any toast clears)
3. If `ev.last_trade`: show green/red toast `"BUY 37.2 NVDA @ $134.52"` after position lines updated

### Position summary line

Updated by `updateCardPosition(ticker)`:
- If no position for ticker: hide `#trade-position-{ticker}`
- If position exists:
  - Show: `"{shares} shares · avg ${avg_cost} · {+/-}${pnl} ({pct}%)"`
  - Green text if `unrealised_pnl ≥ 0`, red if negative

### SELL button state

Enabled when `portfolioState.positions[ticker]` exists and has `shares > 0`. Disabled otherwise.

---

## Guards

| Guard | Where | Behaviour |
|---|---|---|
| `amount_usd > cash` | `executeTrade()` client-side | Error toast, no POST sent |
| Button lockout | `executeTrade()` | Both buttons disabled + "…" text until `portfolio_update` received or 10s timeout |
| SELL empty input | `executeTrade()` | Auto-fill with full position value |
| Position summary before toast | `handlePortfolioUpdate()` | Update summary lines first, toast second |

---

## CSS additions

```css
.trade-bar { padding: 6px 8px; border-top: 1px solid var(--border); }
.trade-controls { display: flex; align-items: center; gap: 6px; }
.trade-currency { color: var(--text-dim); font-family: var(--mono); font-size: 12px; }
.trade-input { width: 90px; background: var(--bg-input); border: 1px solid var(--border);
               color: var(--text); font-family: var(--mono); font-size: 12px; padding: 3px 6px; }
.btn-buy  { background: #00c853; color: #000; font-size: 11px; font-weight: 700;
            padding: 3px 10px; border: none; cursor: pointer; letter-spacing: 0.08em; }
.btn-sell { background: #d50000; color: #fff; font-size: 11px; font-weight: 700;
            padding: 3px 10px; border: none; cursor: pointer; letter-spacing: 0.08em; }
.btn-buy:disabled, .btn-sell:disabled { opacity: 0.35; cursor: not-allowed; }
.trade-position { font-family: var(--mono); font-size: 11px; margin-top: 4px; }
.trade-position.pnl-positive { color: var(--green); }
.trade-position.pnl-negative { color: var(--red); }
```

---

## Files Changed

| File | Action | Responsibility |
|---|---|---|
| `portfolio.py` | Create | `Portfolio` class — all state logic, no HTTP |
| `backend.py` | Modify | Import Portfolio, 3 endpoints, broadcast on trade |
| `dashboard.html` | Modify | Trade bar markup, `executeTrade()`, `handlePortfolioUpdate()`, `updateCardPosition()` |
| `tests/test_portfolio.py` | Create | Unit tests for Portfolio class |
| `tests/test_trade_endpoint.py` | Create | Integration tests for `/api/trade`, `/api/portfolio`, `/api/price/{ticker}` |
