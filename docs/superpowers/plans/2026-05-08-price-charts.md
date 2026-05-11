# Price Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lazy-loaded 30-day close+volume Chart.js chart to each ticker card, with a signal overlay point when a BUY/SELL/HOLD result exists.

**Architecture:** A new `GET /api/tickers/{ticker}/chart` FastAPI endpoint fetches OHLCV from yfinance and returns `{dates, close, volume}`. The frontend loads Chart.js from CDN, adds a `<canvas>` to each card, and calls the endpoint once per ticker on first render. Chart instances are tracked in `chartInstances` for cleanup.

**Tech Stack:** Python/FastAPI (backend), Chart.js 4 via CDN (frontend), yfinance, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend.py` | Modify | Add `GET /api/tickers/{ticker}/chart` endpoint |
| `dashboard.html` | Modify | Chart.js CDN, state vars, canvas markup, `loadChart()`, cleanup, signal update |
| `tests/test_chart_endpoint.py` | Create | Backend endpoint unit tests |

---

## Task 1: Backend `/api/tickers/{ticker}/chart` endpoint

**Files:**
- Create: `tests/test_chart_endpoint.py`
- Modify: `backend.py` (add endpoint after `get_status()`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chart_endpoint.py`:

```python
# tests/test_chart_endpoint.py
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


def _make_history(n=30):
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    return pd.DataFrame({
        "Close": [100.0 + i for i in range(n)],
        "Volume": [1_000_000 + i * 10_000 for i in range(n)],
        "Open": [99.0 + i for i in range(n)],
        "High": [101.0 + i for i in range(n)],
        "Low":  [98.0 + i for i in range(n)],
    }, index=dates)


@pytest.fixture
def client():
    from backend import app
    return TestClient(app)


class TestChartEndpoint:
    def test_returns_dates_close_volume(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _make_history(30)
            r = client.get("/api/tickers/NVDA/chart")
        assert r.status_code == 200
        data = r.json()
        assert "dates" in data
        assert "close" in data
        assert "volume" in data
        assert len(data["dates"]) == 30
        assert len(data["close"]) == 30
        assert len(data["volume"]) == 30

    def test_dates_are_iso_strings(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _make_history(5)
            r = client.get("/api/tickers/AAPL/chart")
        from datetime import datetime
        for d in r.json()["dates"]:
            datetime.strptime(d, "%Y-%m-%d")   # must not raise

    def test_empty_data_returns_404(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = pd.DataFrame()
            r = client.get("/api/tickers/DELISTED/chart")
        assert r.status_code == 404
        assert r.json()["error"] == "No data"

    def test_ticker_uppercased(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _make_history(10)
            r = client.get("/api/tickers/nvda/chart")
        assert r.status_code == 200
        mock_ticker.assert_called_once_with("NVDA")
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_chart_endpoint.py -v
```

Expected: `404 Not Found` for the endpoint (route doesn't exist yet).

- [ ] **Step 3: Add the endpoint to `backend.py`**

Add `import yfinance as yf` near the top imports if not already present, then add this endpoint after the `get_status()` function (around line 311):

```python
@app.get("/api/tickers/{ticker}/chart")
def get_chart(ticker: str):
    t = ticker.upper()
    try:
        df = yf.Ticker(t).history(period="30d")
    except Exception:
        return JSONResponse({"error": "No data"}, status_code=404)
    if df.empty:
        return JSONResponse({"error": "No data"}, status_code=404)
    return JSONResponse({
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "close": [round(float(v), 4) for v in df["Close"]],
        "volume": [int(v) for v in df["Volume"]],
    })
```

- [ ] **Step 4: Check yfinance import**

`backend.py` already imports yfinance indirectly via TradingAgents, but the endpoint needs a direct import. Check the top of `backend.py` for an existing `import yfinance` or `import yfinance as yf`. If absent, add it after the other stdlib imports:

```python
import yfinance as yf
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_chart_endpoint.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```
git add backend.py tests/test_chart_endpoint.py
git commit -m "feat(dashboard): add GET /api/tickers/{ticker}/chart endpoint"
```

---

## Task 2: Frontend — Chart.js CDN, state variables, canvas markup, CSS

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add Chart.js CDN**

In `dashboard.html`, find the closing `</style>` tag followed by `</head>` (around line 424). Insert the CDN script between them:

```html
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
</head>
```

- [ ] **Step 2: Add chart state variables**

Find the state section (around line 525):

```js
// ── State ──────────────────────────────────────────────────────────────────
const state = {};     // ticker -> { status, currentAgent, result, logs, completedAgents }
```

Add two lines immediately after:

```js
// ── State ──────────────────────────────────────────────────────────────────
const state = {};     // ticker -> { status, currentAgent, result, logs, completedAgents }
const chartInstances = {};        // ticker → Chart instance
const chartsLoaded = new Set();   // tickers whose chart data has been fetched
```

- [ ] **Step 3: Add chart CSS**

Find the closing `</style>` tag (same location as Step 1, now just before the Chart.js script). Add these styles inside `<style>` before `</style>`:

```css
.chart-container {
  margin-top: 8px;
  padding: 0 4px;
  width: 100%;
}
.chart-container canvas {
  width: 100% !important;
  height: 120px !important;
  display: block;
}
.chart-no-data {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-dim);
  font-family: var(--mono);
  letter-spacing: 0.05em;
}
```

- [ ] **Step 4: Add canvas to `renderCard()`**

Find the closing of the card template in `renderCard()`. The last section before the closing backtick is `<!-- Decision -->`. Insert the chart container between the agent pills and the log terminal:

Find this block (around line 742):
```html
    <!-- Agent pills -->
    <div class="agent-pills" id="pills-${ticker}">
      ${AGENT_SEQUENCE.map(a => `
        <div class="agent-pill" id="pill-${ticker}-${a.replace(/\s+/g,'-')}">${AGENT_SHORT[a]}</div>
      `).join('')}
    </div>

    <!-- Log terminal -->
```

Replace with:
```html
    <!-- Agent pills -->
    <div class="agent-pills" id="pills-${ticker}">
      ${AGENT_SEQUENCE.map(a => `
        <div class="agent-pill" id="pill-${ticker}-${a.replace(/\s+/g,'-')}">${AGENT_SHORT[a]}</div>
      `).join('')}
    </div>

    <!-- Price chart -->
    <div class="chart-container" id="chart-container-${ticker}">
      <canvas id="chart-${ticker}"></canvas>
    </div>

    <!-- Log terminal -->
```

- [ ] **Step 5: Trigger `loadChart` after card insertion**

Find the end of `renderCard()` (around line 764):

```js
  grid.appendChild(card);
}
```

Replace with:

```js
  grid.appendChild(card);
  if (!chartsLoaded.has(ticker)) {
    chartsLoaded.add(ticker);
    loadChart(ticker);
  }
}
```

- [ ] **Step 6: Verify markup in browser**

Restart the backend (`python F:/TradingAgents/backend.py`), open `http://localhost:8000`, add a ticker. The card should now have a grey-bordered 120px chart area below the agent pills (empty/blank until `loadChart` is implemented in Task 3).

- [ ] **Step 7: Commit**

```
git add dashboard.html
git commit -m "feat(dashboard): add chart canvas to ticker cards"
```

---

## Task 3: Frontend — `loadChart()` function

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add `loadChart()` after the state section**

Find this block (around line 530):

```js
// ── Clock ──────────────────────────────────────────────────────────────────
```

Insert `loadChart` and its helper `_signalDataset` immediately before it:

```js
// ── Charts ─────────────────────────────────────────────────────────────────
function _signalDataset(decision, signalDate, closeValues) {
  if (!decision || decision === 'PENDING') return null;
  const priceAtSignal = closeValues[closeValues.length - 1];
  const color = decision === 'BUY' ? '#00e676' : decision === 'SELL' ? '#ff1744' : '#888888';
  const style = decision === 'SELL' ? 'triangle' : decision === 'BUY' ? 'triangle' : 'circle';
  const rotation = decision === 'SELL' ? 180 : 0;
  return {
    type: 'scatter',
    label: 'Signal',
    data: [{ x: signalDate, y: priceAtSignal }],
    yAxisID: 'y',
    pointStyle: style,
    rotation: rotation,
    backgroundColor: color,
    borderColor: color,
    pointRadius: 8,
    pointHoverRadius: 8,
  };
}

async function loadChart(ticker) {
  const container = document.getElementById('chart-container-' + ticker);
  if (!container) return;

  let data;
  try {
    const r = await fetch(`${API}/tickers/${ticker}/chart`);
    if (!r.ok) throw new Error('no data');
    data = await r.json();
  } catch {
    container.innerHTML = '<div class="chart-no-data">NO CHART DATA</div>';
    return;
  }

  const canvas = document.getElementById('chart-' + ticker);
  if (!canvas) return;
  canvas.style.height = '120px';

  const signalDate = data.dates[data.dates.length - 1];
  const s = state[ticker];
  const decision = s && s.result ? s.result.decision : null;
  const signalDs = _signalDataset(decision, signalDate, data.close);

  const datasets = [
    {
      type: 'line',
      label: 'Close',
      data: data.close,
      yAxisID: 'y',
      borderColor: 'rgba(255,255,255,0.85)',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
    },
    {
      type: 'bar',
      label: 'Volume',
      data: data.volume,
      yAxisID: 'y2',
      backgroundColor: 'rgba(255,255,255,0.12)',
      borderWidth: 0,
    },
  ];
  if (signalDs) datasets.push(signalDs);

  chartInstances[ticker] = new Chart(canvas, {
    type: 'bar',
    data: { labels: data.dates, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: { display: false, position: 'left' },
        y2: { display: false, position: 'right', grid: { drawOnChartArea: false } },
      },
    },
  });
}

// ── Clock ──────────────────────────────────────────────────────────────────
```

- [ ] **Step 2: Verify in browser**

Restart backend, add a ticker like NVDA. After a second or two the chart should render: a white price line over grey volume bars, 120px tall, no axes.

- [ ] **Step 3: Commit**

```
git add dashboard.html
git commit -m "feat(dashboard): add loadChart with line+volume Chart.js rendering"
```

---

## Task 4: Frontend — cleanup on remove + signal overlay on result

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add chart cleanup to `removeTicker()`**

Find `removeTicker()` (around line 631):

```js
function removeTicker(ticker) {
  delete state[ticker];
  const card = document.getElementById('card-' + ticker);
  if (card) {
    card.style.animation = 'card-enter 0.3s reverse forwards';
    setTimeout(() => card.remove(), 300);
  }
  updateEmptyState();
  updateFooter();
}
```

Replace with:

```js
function removeTicker(ticker) {
  if (chartInstances[ticker]) {
    chartInstances[ticker].destroy();
    delete chartInstances[ticker];
  }
  chartsLoaded.delete(ticker);
  delete state[ticker];
  const card = document.getElementById('card-' + ticker);
  if (card) {
    card.style.animation = 'card-enter 0.3s reverse forwards';
    setTimeout(() => card.remove(), 300);
  }
  updateEmptyState();
  updateFooter();
}
```

- [ ] **Step 2: Add signal point update to `applyResult()`**

Find `applyResult()` (around line 642):

```js
function applyResult(ticker, result, lastUpdated) {
  const s = state[ticker];
  if (!s) return;
  s.status = 'done';
  s.currentAgent = null;
  s.result = result;
  s.completedAgents = new Set(AGENT_SEQUENCE);
  updateCardDecision(ticker);
  updateAgentBar(ticker);
  updateAgentPills(ticker);
  updateCardStatus(ticker);
  if (lastUpdated) {
    const el = document.getElementById('last-updated-' + ticker);
    if (el) el.textContent = 'Updated ' + new Date(lastUpdated).toLocaleTimeString();
  }
}
```

Replace with:

```js
function applyResult(ticker, result, lastUpdated) {
  const s = state[ticker];
  if (!s) return;
  s.status = 'done';
  s.currentAgent = null;
  s.result = result;
  s.completedAgents = new Set(AGENT_SEQUENCE);
  updateCardDecision(ticker);
  updateAgentBar(ticker);
  updateAgentPills(ticker);
  updateCardStatus(ticker);
  if (lastUpdated) {
    const el = document.getElementById('last-updated-' + ticker);
    if (el) el.textContent = 'Updated ' + new Date(lastUpdated).toLocaleTimeString();
  }
  // Update signal overlay if chart already loaded
  const chart = chartInstances[ticker];
  if (chart && result) {
    const labels = chart.data.labels;
    const signalDate = labels[labels.length - 1];
    const closeDs = chart.data.datasets.find(d => d.label === 'Close');
    const closeValues = closeDs ? closeDs.data : [];
    // Remove existing signal dataset if present
    chart.data.datasets = chart.data.datasets.filter(d => d.label !== 'Signal');
    const signalDs = _signalDataset(result.decision, signalDate, closeValues);
    if (signalDs) chart.data.datasets.push(signalDs);
    chart.update();
  }
}
```

- [ ] **Step 3: Run all backend tests**

```
pytest tests/ -v
```

Expected: all tests PASS (including the 4 new chart endpoint tests and the 52 backtesting tests).

- [ ] **Step 4: End-to-end smoke test**

1. Restart backend: kill port 8000, run `python F:/TradingAgents/backend.py`
2. Open `http://localhost:8000`
3. Add `NVDA` — chart should render within ~1s showing 30 days of price + volume
4. Add `AAPL` — second chart loads independently
5. Remove `NVDA` — card animates out, no console errors about leaked Chart instances
6. Wait for or trigger an analysis to complete — the signal point (triangle or circle) should appear on the chart

- [ ] **Step 5: Commit**

```
git add dashboard.html
git commit -m "feat(dashboard): price charts complete — lazy load, signal overlay, cleanup"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `GET /api/tickers/{ticker}/chart` returns `{dates, close, volume}` | Task 1 |
| 404 on empty data | Task 1 |
| Ticker uppercased | Task 1 |
| Chart.js CDN in `<head>` | Task 2 |
| `chartInstances`, `chartsLoaded` state vars | Task 2 |
| Canvas `height:120px` in markup and JS | Tasks 2 & 3 |
| Lazy load guard with `chartsLoaded` | Task 2 |
| `loadChart` fetches endpoint, handles 404 | Task 3 |
| Line dataset (close, white, no points) | Task 3 |
| Bar dataset (volume, semi-transparent grey) | Task 3 |
| Signal scatter point at `dates[dates.length-1]` | Task 3 |
| BUY green triangle-up, SELL red triangle-down, HOLD grey circle | Task 3 |
| No gridlines, no axes, no legend | Task 3 |
| `chart.destroy()` + `chartsLoaded.delete()` in `removeTicker()` | Task 4 |
| Signal point added/updated in `applyResult()` | Task 4 |
