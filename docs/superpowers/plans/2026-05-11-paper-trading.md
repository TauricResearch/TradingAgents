# Paper Trading Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paper trading simulator with a $100k virtual portfolio, BUY/SELL buttons on each ticker card, live-price execution, and real-time portfolio_update WebSocket broadcasts.

**Architecture:** `portfolio.py` is a pure state class (no HTTP). `backend.py` imports it at module level, adds 3 REST endpoints and an async `POST /api/trade` that broadcasts after each trade. `dashboard.html` adds a trade bar to each card and a `handlePortfolioUpdate` handler that updates all cards from the WebSocket event.

**Tech Stack:** Python/FastAPI, yfinance `fast_info`, pydantic, pytest, vanilla JS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `portfolio.py` | Create | `Portfolio` class — load/save/buy/sell/get_state, no HTTP |
| `backend.py` | Modify | Import Portfolio, `TradePayload` model, 3 endpoints, broadcast on trade |
| `dashboard.html` | Modify | Trade CSS, trade bar in cards, `portfolioState`, `executeTrade`, `handlePortfolioUpdate`, `updateCardPosition`, `loadPortfolio` |
| `tests/test_portfolio.py` | Create | Unit tests for Portfolio class |
| `tests/test_trade_endpoint.py` | Create | Integration tests for all 3 endpoints |

---

## Task 1: `portfolio.py` — Portfolio class

**Files:**
- Create: `portfolio.py`
- Create: `tests/test_portfolio.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_portfolio.py`:

```python
# tests/test_portfolio.py
import json
import os
import pytest


@pytest.fixture
def p():
    from portfolio import Portfolio
    port = Portfolio()
    port.load.__func__ if False else None  # ensure importable
    port.cash = 100_000.0
    port.positions = {}
    port.trades = []
    return port


class TestLoad:
    def test_fresh_portfolio_when_file_absent(self, tmp_path):
        from portfolio import Portfolio
        port = Portfolio()
        port.load(str(tmp_path / "missing.json"))
        assert port.cash == 100_000.0
        assert port.positions == {}
        assert port.trades == []

    def test_loads_existing_file(self, tmp_path):
        from portfolio import Portfolio
        path = tmp_path / "p.json"
        path.write_text(json.dumps({
            "cash": 50000.0,
            "positions": {"NVDA": {"shares": 10.0, "avg_cost": 130.0}},
            "trades": []
        }), encoding="utf-8")
        port = Portfolio()
        port.load(str(path))
        assert port.cash == 50_000.0
        assert port.positions["NVDA"]["shares"] == 10.0


class TestSave:
    def test_round_trip(self, tmp_path, p):
        from portfolio import Portfolio
        path = str(tmp_path / "p.json")
        p.cash = 42_000.0
        p.positions = {"AAPL": {"shares": 5.0, "avg_cost": 180.0}}
        p.save(path)
        p2 = Portfolio()
        p2.load(path)
        assert p2.cash == 42_000.0
        assert p2.positions["AAPL"]["shares"] == 5.0


class TestBuy:
    def test_creates_new_position(self, p):
        result = p.buy("NVDA", 1000.0, 100.0)
        assert result["shares"] == pytest.approx(10.0)
        assert result["avg_cost"] == pytest.approx(100.0)
        assert p.cash == pytest.approx(99_000.0)

    def test_weighted_average_cost(self, p):
        p.buy("NVDA", 1000.0, 100.0)   # 10 shares @ 100
        result = p.buy("NVDA", 1000.0, 200.0)   # 5 shares @ 200 → avg 133.33
        assert result["shares"] == pytest.approx(15.0)
        assert result["avg_cost"] == pytest.approx(133.3333, abs=0.001)
        assert p.cash == pytest.approx(98_000.0)

    def test_trade_appended(self, p):
        p.buy("AAPL", 500.0, 50.0)
        assert len(p.trades) == 1
        assert p.trades[0]["side"] == "BUY"
        assert p.trades[0]["ticker"] == "AAPL"
        assert p.trades[0]["shares"] == pytest.approx(10.0)

    def test_fractional_shares(self, p):
        result = p.buy("TSLA", 1000.0, 300.0)
        assert result["shares"] == pytest.approx(3.3333, abs=0.001)


class TestSell:
    def test_full_position_sell(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares
        result = p.sell("NVDA", 1000.0, 100.0)
        assert result["shares_sold"] == pytest.approx(10.0)
        assert "NVDA" not in p.positions
        assert p.cash == pytest.approx(100_000.0)

    def test_partial_sell(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares
        result = p.sell("NVDA", 500.0, 100.0)  # sell 5
        assert result["shares_sold"] == pytest.approx(5.0)
        assert p.positions["NVDA"]["shares"] == pytest.approx(5.0)

    def test_sell_capped_at_full_position(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares = $1000
        result = p.sell("NVDA", 5000.0, 100.0)  # try to sell $5000 worth
        assert result["shares_sold"] == pytest.approx(10.0)   # capped at full position
        assert "NVDA" not in p.positions

    def test_trade_appended(self, p):
        p.buy("NVDA", 1000.0, 100.0)
        p.sell("NVDA", 500.0, 110.0)
        assert len(p.trades) == 2
        assert p.trades[1]["side"] == "SELL"


class TestGetState:
    def test_empty_portfolio(self, p):
        state = p.get_state({})
        assert state["cash"] == pytest.approx(100_000.0)
        assert state["positions"] == {}
        assert state["total_value"] == pytest.approx(100_000.0)

    def test_unrealised_pnl_positive(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares @ 100
        state = p.get_state({"NVDA": 120.0})  # now worth $1200
        pos = state["positions"]["NVDA"]
        assert pos["unrealised_pnl"] == pytest.approx(200.0)
        assert pos["unrealised_pnl_pct"] == pytest.approx(20.0)
        assert state["total_value"] == pytest.approx(100_200.0)

    def test_unrealised_pnl_negative(self, p):
        p.buy("NVDA", 1000.0, 100.0)
        state = p.get_state({"NVDA": 80.0})
        assert state["positions"]["NVDA"]["unrealised_pnl"] == pytest.approx(-200.0)

    def test_fallback_to_avg_cost_when_price_missing(self, p):
        p.buy("NVDA", 1000.0, 100.0)
        state = p.get_state({})  # no price provided
        assert state["positions"]["NVDA"]["unrealised_pnl"] == pytest.approx(0.0)
        assert state["total_value"] == pytest.approx(100_000.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_portfolio.py -v
```

Expected: `ModuleNotFoundError: No module named 'portfolio'`

- [ ] **Step 3: Implement `portfolio.py`**

Create `portfolio.py` in the project root (`F:\TradingAgents\portfolio.py`):

```python
import json
import os
from datetime import datetime


class Portfolio:
    def __init__(self):
        self.cash: float = 100_000.0
        self.positions: dict = {}   # ticker -> {"shares": float, "avg_cost": float}
        self.trades: list = []

    def load(self, path: str = "portfolio.json") -> None:
        if not os.path.exists(path):
            self.cash = 100_000.0
            self.positions = {}
            self.trades = []
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.cash = float(data.get("cash", 100_000.0))
        self.positions = data.get("positions", {})
        self.trades = data.get("trades", [])

    def save(self, path: str = "portfolio.json") -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"cash": self.cash, "positions": self.positions, "trades": self.trades},
                f, indent=2,
            )
        os.replace(tmp, path)

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
            total_positions_value += current_price * pos["shares"]
            positions_out[ticker] = {
                "shares": pos["shares"],
                "avg_cost": pos["avg_cost"],
                "current_price": round(current_price, 4),
                "unrealised_pnl": round(unrealised_pnl, 2),
                "unrealised_pnl_pct": round(unrealised_pnl_pct, 2),
            }
        return {
            "cash": round(self.cash, 2),
            "positions": positions_out,
            "total_value": round(self.cash + total_positions_value, 2),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_portfolio.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```
git add portfolio.py tests/test_portfolio.py
git commit -m "feat(trading): add Portfolio class with buy/sell/get_state"
```

---

## Task 2: Backend — 3 endpoints + broadcast

**Files:**
- Create: `tests/test_trade_endpoint.py`
- Modify: `backend.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trade_endpoint.py`:

```python
# tests/test_trade_endpoint.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_portfolio():
    """Give each test a clean in-memory portfolio."""
    import backend
    from portfolio import Portfolio
    backend.portfolio = Portfolio()
    backend.portfolio.cash = 100_000.0
    yield


@pytest.fixture
def client():
    from backend import app
    return TestClient(app)


def _mock_price(price: float):
    m = MagicMock()
    m.fast_info = {"last_price": price}
    return m


class TestGetPortfolio:
    def test_empty_portfolio(self, client):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert data["cash"] == pytest.approx(100_000.0)
        assert data["positions"] == {}
        assert data["total_value"] == pytest.approx(100_000.0)

    def test_with_position(self, client):
        import backend
        backend.portfolio.positions = {"NVDA": {"shares": 10.0, "avg_cost": 100.0}}
        with patch("backend.yf.Ticker", return_value=_mock_price(120.0)):
            r = client.get("/api/portfolio")
        data = r.json()
        assert "NVDA" in data["positions"]
        assert data["positions"]["NVDA"]["current_price"] == pytest.approx(120.0)
        assert data["total_value"] == pytest.approx(100_000.0 + 200.0)


class TestGetPrice:
    def test_returns_price(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(134.52)):
            r = client.get("/api/price/NVDA")
        assert r.status_code == 200
        assert r.json()["price"] == pytest.approx(134.52)
        assert r.json()["ticker"] == "NVDA"

    def test_ticker_uppercased(self, client):
        with patch("backend.yf.Ticker") as mock_t:
            mock_t.return_value = _mock_price(100.0)
            client.get("/api/price/nvda")
        mock_t.assert_called_once_with("NVDA")

    def test_price_unavailable_returns_404(self, client):
        with patch("backend.yf.Ticker") as mock_t:
            mock_t.side_effect = Exception("network error")
            r = client.get("/api/price/BADINPUT")
        assert r.status_code == 404
        assert r.json()["error"] == "Price unavailable"


class TestPostTrade:
    def test_buy_happy_path(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 1000.0})
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "portfolio_update"
        assert "NVDA" in data["positions"]
        assert data["cash"] == pytest.approx(99_000.0)
        assert data["last_trade"]["side"] == "BUY"

    def test_sell_happy_path(self, client):
        import backend
        backend.portfolio.positions = {"NVDA": {"shares": 10.0, "avg_cost": 100.0}}
        backend.portfolio.cash = 99_000.0
        with patch("backend.yf.Ticker", return_value=_mock_price(110.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "SELL", "amount_usd": 500.0})
        assert r.status_code == 200
        data = r.json()
        assert data["last_trade"]["side"] == "SELL"

    def test_buy_insufficient_cash(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 200_000.0})
        assert r.status_code == 400
        assert r.json()["error"] == "Insufficient cash"

    def test_sell_no_position(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "SELL", "amount_usd": 500.0})
        assert r.status_code == 400
        assert r.json()["error"] == "No position"

    def test_price_unavailable_returns_503(self, client):
        with patch("backend.yf.Ticker") as mock_t:
            mock_t.side_effect = Exception("network error")
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 1000.0})
        assert r.status_code == 503

    def test_invalid_side_returns_400(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "HOLD", "amount_usd": 1000.0})
        assert r.status_code == 400

    def test_zero_amount_returns_400(self, client):
        r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 0.0})
        assert r.status_code == 400

    def test_ticker_uppercased(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "nvda", "side": "BUY", "amount_usd": 500.0})
        assert r.status_code == 200
        assert "NVDA" in r.json()["positions"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_trade_endpoint.py -v
```

Expected: routes not yet registered → 404 / 405 errors.

- [ ] **Step 3: Add Portfolio to `backend.py`**

Add the import and module-level initialisation. Find the block just after all imports and before `DEMO_MODE` (around line 32):

```python
# existing imports end here...
import uvicorn
import yfinance as yf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
```

Add immediately after the imports (before `DEMO_MODE = False`):

```python
from portfolio import Portfolio
```

Then find the block where `app` is created and `executor` is initialised (around line 44-50). After `executor = ThreadPoolExecutor(max_workers=4)`, add:

```python
portfolio = Portfolio()
portfolio.load()
```

- [ ] **Step 4: Add `TradePayload` Pydantic model**

Find the existing Pydantic models in `backend.py`:

```python
class TickerPayload(BaseModel):
    ticker: str
```

Add a new model directly after `ConfigPayload`:

```python
class TradePayload(BaseModel):
    ticker: str
    side: str
    amount_usd: float
```

- [ ] **Step 5: Add the 3 endpoints**

Add all three endpoints after the existing `get_chart` endpoint (after line 328, before the `@app.websocket` line):

```python
@app.get("/api/portfolio")
def get_portfolio():
    prices = {}
    for t in portfolio.positions:
        try:
            prices[t] = float(yf.Ticker(t).fast_info["last_price"])
        except Exception:
            pass
    return JSONResponse(portfolio.get_state(prices))


@app.get("/api/price/{ticker}")
def get_price(ticker: str):
    t = ticker.upper()
    try:
        price = float(yf.Ticker(t).fast_info["last_price"])
        return JSONResponse({"ticker": t, "price": price})
    except Exception:
        return JSONResponse({"error": "Price unavailable"}, status_code=404)


@app.post("/api/trade")
async def post_trade(payload: TradePayload):
    t = payload.ticker.upper()
    side = payload.side.upper()
    amount_usd = payload.amount_usd

    if side not in ("BUY", "SELL"):
        return JSONResponse({"error": "side must be BUY or SELL"}, status_code=400)
    if amount_usd <= 0:
        return JSONResponse({"error": "amount_usd must be positive"}, status_code=400)

    try:
        price = float(yf.Ticker(t).fast_info["last_price"])
    except Exception:
        return JSONResponse({"error": "Price unavailable"}, status_code=503)

    if side == "BUY":
        if amount_usd > portfolio.cash:
            return JSONResponse({"error": "Insufficient cash"}, status_code=400)
        portfolio.buy(t, amount_usd, price)
    else:
        if t not in portfolio.positions:
            return JSONResponse({"error": "No position"}, status_code=400)
        portfolio.sell(t, amount_usd, price)

    portfolio.save()

    prices = {}
    for ticker in portfolio.positions:
        try:
            prices[ticker] = float(yf.Ticker(ticker).fast_info["last_price"])
        except Exception:
            pass
    state = portfolio.get_state(prices)
    last_trade = portfolio.trades[-1] if portfolio.trades else None
    update_payload = {"type": "portfolio_update", **state, "last_trade": last_trade}

    await broadcast(update_payload)
    return JSONResponse(update_payload)
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_trade_endpoint.py tests/test_portfolio.py -v
```

Expected: all 24 tests PASS (16 portfolio + 8 trade endpoint).

- [ ] **Step 7: Commit**

```
git add backend.py tests/test_trade_endpoint.py
git commit -m "feat(trading): add /api/portfolio, /api/price, /api/trade endpoints"
```

---

## Task 3: Frontend — trade bar markup + CSS + state

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add `portfolioState` to the state section**

Find the state section (around line 547):

```js
const state = {};     // ticker -> { status, currentAgent, result, logs, completedAgents }
const chartInstances = {};        // ticker → Chart instance
const chartsLoaded = new Set();   // tickers whose chart data has been fetched
```

Add one line after `chartsLoaded`:

```js
const state = {};     // ticker -> { status, currentAgent, result, logs, completedAgents }
const chartInstances = {};        // ticker → Chart instance
const chartsLoaded = new Set();   // tickers whose chart data has been fetched
let portfolioState = { cash: 100000, positions: {}, total_value: 100000 };
```

- [ ] **Step 2: Add trade bar CSS**

Find `</style>` (just before the Chart.js CDN script tag). Add these styles inside `<style>` immediately before `</style>`:

```css
.trade-bar { padding: 6px 8px; border-top: 1px solid var(--border); }
.trade-controls { display: flex; align-items: center; gap: 6px; }
.trade-currency { color: var(--text-dim); font-family: var(--mono); font-size: 12px; }
.trade-input { width: 90px; background: var(--bg-input, #1a1a1a); border: 1px solid var(--border);
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

- [ ] **Step 3: Add trade bar to `renderCard()`**

Find the price chart block inside `renderCard()`:

```html
    <!-- Price chart -->
    <div class="chart-container" id="chart-container-${ticker}">
      <canvas id="chart-${ticker}"></canvas>
    </div>

    <!-- Log terminal -->
```

Replace with:

```html
    <!-- Price chart -->
    <div class="chart-container" id="chart-container-${ticker}">
      <canvas id="chart-${ticker}"></canvas>
    </div>

    <!-- Trade bar -->
    <div class="trade-bar" id="trade-bar-${ticker}">
      <div class="trade-controls">
        <span class="trade-currency">$</span>
        <input type="number" class="trade-input" id="trade-input-${ticker}"
               placeholder="Amount" min="1" step="1" />
        <button class="btn-buy" id="btn-buy-${ticker}" onclick="executeTrade('${ticker}','BUY')">BUY</button>
        <button class="btn-sell" id="btn-sell-${ticker}" onclick="executeTrade('${ticker}','SELL')" disabled>SELL</button>
      </div>
      <div class="trade-position" id="trade-position-${ticker}" style="display:none"></div>
    </div>

    <!-- Log terminal -->
```

- [ ] **Step 4: Add `portfolio_update` case to `handleEvent`**

Find the `switch` block in `handleEvent` (around line 685). Add a new case before the closing brace:

```js
    case 'portfolio_update':
      handlePortfolioUpdate(ev);
      break;
```

So the switch ends:

```js
    case 'ticker_error':
      if (!state[ev.ticker]) return;
      state[ev.ticker].status = 'error';
      state[ev.ticker].error = ev.error;
      updateCardStatus(ev.ticker);
      toast(`Error analyzing ${ev.ticker}`, 'error');
      break;
    case 'portfolio_update':
      handlePortfolioUpdate(ev);
      break;
  }
}
```

- [ ] **Step 5: Commit**

```
git add dashboard.html
git commit -m "feat(trading): add trade bar markup, CSS, portfolioState, portfolio_update dispatch"
```

---

## Task 4: Frontend — `loadPortfolio`, `executeTrade`, `handlePortfolioUpdate`, `updateCardPosition`

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add `loadPortfolio()` and call it on WebSocket open**

Find the `// ── Charts ──` section header. Insert a new `// ── Portfolio ──` section immediately before it:

```js
// ── Portfolio ─────────────────────────────────────────────────────────────
async function loadPortfolio() {
  try {
    const r = await fetch(`${API}/portfolio`);
    if (!r.ok) return;
    const data = await r.json();
    handlePortfolioUpdate(data);
  } catch (e) {
    console.warn('[loadPortfolio]', e);
  }
}

function updateCardPosition(ticker) {
  const pos = portfolioState.positions && portfolioState.positions[ticker];
  const el = document.getElementById('trade-position-' + ticker);
  const sellBtn = document.getElementById('btn-sell-' + ticker);
  if (!el) return;
  if (!pos || pos.shares <= 0) {
    el.style.display = 'none';
    if (sellBtn) sellBtn.disabled = true;
    return;
  }
  const sign = pos.unrealised_pnl >= 0 ? '+' : '';
  const pnlClass = pos.unrealised_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
  el.className = 'trade-position ' + pnlClass;
  el.style.display = 'block';
  el.textContent = `${pos.shares.toFixed(2)} shares · avg $${pos.avg_cost.toFixed(2)} · ${sign}$${pos.unrealised_pnl.toFixed(2)} (${sign}${pos.unrealised_pnl_pct.toFixed(1)}%)`;
  if (sellBtn) sellBtn.disabled = false;
}

function handlePortfolioUpdate(ev) {
  portfolioState = ev;
  for (const ticker of Object.keys(state)) {
    updateCardPosition(ticker);
  }
  if (ev.last_trade) {
    const t = ev.last_trade;
    const kind = t.side === 'BUY' ? 'success' : 'error';
    toast(`${t.side} ${t.shares.toFixed(2)} ${t.ticker} @ $${t.price.toFixed(2)}`, kind);
  }
}

async function executeTrade(ticker, side) {
  const input = document.getElementById('trade-input-' + ticker);
  const buyBtn = document.getElementById('btn-buy-' + ticker);
  const sellBtn = document.getElementById('btn-sell-' + ticker);

  let amount_usd = parseFloat(input.value);

  // SELL with empty input → full position value
  if (side === 'SELL' && (!input.value || isNaN(amount_usd))) {
    const pos = portfolioState.positions && portfolioState.positions[ticker];
    if (pos) amount_usd = pos.shares * pos.current_price;
  }

  if (!amount_usd || amount_usd <= 0) {
    toast('Enter an amount', 'error');
    return;
  }

  // Cash validation
  if (side === 'BUY' && amount_usd > portfolioState.cash) {
    toast('Insufficient cash', 'error');
    return;
  }

  // 30% concentration warning
  if (side === 'BUY') {
    const pos = portfolioState.positions && portfolioState.positions[ticker];
    const existing = pos ? pos.shares * pos.current_price : 0;
    const projected = (existing + amount_usd) / (portfolioState.total_value || 1);
    if (projected > 0.30) {
      const confirmed = await new Promise(resolve => {
        // Use two toasts: warning + buttons via a small inline confirm
        if (!confirm(`${ticker} would exceed 30% of portfolio. Proceed?`)) {
          resolve(false);
        } else {
          resolve(true);
        }
      });
      if (!confirmed) return;
    }
  }

  // Button lockout
  const origBuyText = buyBtn ? buyBtn.textContent : 'BUY';
  const origSellText = sellBtn ? sellBtn.textContent : 'SELL';
  if (buyBtn) { buyBtn.disabled = true; buyBtn.textContent = '…'; }
  if (sellBtn) { sellBtn.disabled = true; sellBtn.textContent = '…'; }

  // 10s timeout to re-enable buttons if portfolio_update never arrives
  const lockoutTimer = setTimeout(() => {
    if (buyBtn) { buyBtn.disabled = false; buyBtn.textContent = origBuyText; }
    if (sellBtn) { sellBtn.disabled = false; sellBtn.textContent = origSellText; }
  }, 10000);

  // Re-enable function called on portfolio_update or error
  function unlock() {
    clearTimeout(lockoutTimer);
    if (buyBtn) { buyBtn.disabled = false; buyBtn.textContent = origBuyText; }
    // SELL button state set by updateCardPosition via handlePortfolioUpdate
    if (sellBtn) sellBtn.textContent = origSellText;
    input.value = '';
  }

  // Patch handlePortfolioUpdate to unlock after this trade
  const origHandler = handlePortfolioUpdate;
  // eslint-disable-next-line no-global-assign — intentional one-shot wrap
  window._tradeUnlock = unlock;

  try {
    const r = await fetch(`${API}/trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, side, amount_usd }),
    });
    const data = await r.json();
    if (!r.ok) {
      toast(data.error || 'Trade failed', 'error');
      unlock();
    }
    // On success: portfolio_update WebSocket event will fire handlePortfolioUpdate
    // which updates positions before toast. Unlock is triggered by the WS event.
  } catch (e) {
    console.warn('[executeTrade]', e);
    toast('Cannot reach backend', 'error');
    unlock();
  }
}
```

**Note on unlock timing:** The buttons are re-enabled by the 10s timeout fallback. On the success path, the WebSocket `portfolio_update` event arrives and `handlePortfolioUpdate` updates the position lines (which also calls `updateCardPosition` which resets the SELL button state). The `unlock()` call in the error path restores button labels explicitly.

- [ ] **Step 2: Call `loadPortfolio()` on WebSocket open**

Find the `ws.onopen` callback (around line 656):

```js
  ws.onopen = () => {
    setStatus('connected');
    clearTimeout(wsReconnectTimer);
  };
```

Replace with:

```js
  ws.onopen = () => {
    setStatus('connected');
    clearTimeout(wsReconnectTimer);
    loadPortfolio();
  };
```

- [ ] **Step 3: Run all backend tests**

```
pytest tests/test_portfolio.py tests/test_trade_endpoint.py tests/test_chart_endpoint.py -q
```

Expected: all 29 tests PASS.

- [ ] **Step 4: Smoke test in browser**

1. Kill any process on port 8000: `Get-NetTCPConnection -LocalPort 8000 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }`
2. Start backend: `python F:/TradingAgents/backend.py`
3. Open `http://localhost:8000`
4. Add NVDA — card shows BUY/SELL buttons with dollar input below the chart
5. Type `1000` in the NVDA input, click BUY — buttons go to `…`, then re-enable; position summary line appears with shares/avg/P&L
6. Leave input empty, click SELL — auto-fills full position value, trade executes, position disappears
7. Verify SELL button is disabled when no NVDA position

- [ ] **Step 5: Commit**

```
git add dashboard.html
git commit -m "feat(trading): paper trading complete — executeTrade, handlePortfolioUpdate, loadPortfolio"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `Portfolio.load/save` with JSON and fallback | Task 1 |
| `Portfolio.buy` weighted avg cost | Task 1 |
| `Portfolio.sell` capped at full position | Task 1 |
| `Portfolio.get_state` with unrealised P&L | Task 1 |
| `GET /api/portfolio` | Task 2 |
| `GET /api/price/{ticker}` | Task 2 |
| `POST /api/trade` BUY/SELL validation + execution | Task 2 |
| `portfolio_update` broadcast after trade | Task 2 |
| `portfolioState` module-level var | Task 3 |
| Trade bar markup with BUY/SELL/input | Task 3 |
| Trade CSS | Task 3 |
| `portfolio_update` case in `handleEvent` | Task 3 |
| `loadPortfolio()` called on WS open | Task 4 |
| `updateCardPosition()` — show/hide summary | Task 4 |
| `handlePortfolioUpdate()` — update all cards, toast | Task 4 |
| `executeTrade()` — all 4 guards | Task 4 |
| SELL empty input → full position value | Task 4 |
| Cash validation client-side | Task 4 |
| Button lockout + 10s timeout | Task 4 |
| 30% concentration warning | Task 4 |
| Position summary before toast | Task 4 (handlePortfolioUpdate updates cards first) |
