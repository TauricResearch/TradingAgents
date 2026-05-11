# Expandable Analyst Reports — Design Spec

**Date:** 2026-05-11
**Status:** Approved

---

## Overview

Add a collapsible "REPORTS" section to each ticker card. When analysis completes, per-agent report text is bundled into the `analysis_complete` WebSocket event. The frontend stores the reports in `state[ticker].reports` and renders them as nested collapsible blocks, one per agent. A toggle button at the bottom of each card shows/hides the section.

---

## Architecture

```
backend.py     ← capture final_state, extract reports dict, include in analysis_complete
dashboard.html ← REPORT_ORDER constant, toggle button, renderReports(), applyResult update
```

No new endpoints. No new backend state. Frontend-only rendering after `analysis_complete`.

---

## Backend — `backend.py`

### `_run_real_analysis`

Change the propagate call from discarding `final_state`:
```python
# before
_, decision_raw = ta.propagate(ticker, analysis_date, on_node=node_callback)

# after
final_state, decision_raw = ta.propagate(ticker, analysis_date, on_node=node_callback)
```

Define `_extract_reports` at **module level** in `backend.py` (not nested inside `_run_real_analysis`) so it is independently testable:

```python
def _extract_reports(state) -> dict:
    def join_list(v):
        if isinstance(v, list):
            return "\n\n".join(str(item) for item in v)
        return str(v) if v else ""

    ids = state.get("investment_debate_state") or {}
    rds = state.get("risk_debate_state") or {}
    return {
        "market":           str(state.get("market_report") or ""),
        "sentiment":        str(state.get("sentiment_report") or ""),
        "news":             str(state.get("news_report") or ""),
        "fundamentals":     str(state.get("fundamentals_report") or ""),
        "bull":             join_list(ids.get("bull_history")),
        "bear":             join_list(ids.get("bear_history")),
        "research_manager": str(ids.get("judge_decision") or ""),
        "trader":           str(state.get("trader_investment_plan") or ""),
        "risk":             join_list(rds.get("history")),
        "final_decision":   str(state.get("final_trade_decision") or ""),
    }
```

Include `reports` in the returned result dict:

```python
return {
    "decision": action,
    "confidence": confidence,
    "reasoning": reasoning,
    "timestamp": datetime.now().isoformat(),
    "reports": _extract_reports(final_state),
}
```

### Demo mode

`_demo_analysis` returns no `final_state`. Add `"reports": None` to its return dict so the frontend guard `result.reports &&` works uniformly.

### `analysis_complete` event

The event payload already spreads `result`, so `reports` flows through automatically:

```python
await broadcast({
    "type": "analysis_complete",
    "ticker": ticker,
    "result": result,          # now includes reports
    "last_updated": ...,
})
```

`watched_tickers[ticker]["last_result"]` also stores `result` (including `reports`), so reports survive page reconnects via the `init` event.

---

## Frontend — `dashboard.html`

### `REPORT_ORDER` constant

Add alongside `AGENT_SEQUENCE` and `AGENT_SHORT`:

```js
const REPORT_ORDER = [
  { key: "fundamentals",     label: "Fundamentals Analyst" },
  { key: "sentiment",        label: "Sentiment Analyst" },
  { key: "news",             label: "News Analyst" },
  { key: "market",           label: "Market Analyst" },
  { key: "bull",             label: "Bull Researcher" },
  { key: "bear",             label: "Bear Researcher" },
  { key: "research_manager", label: "Research Manager" },
  { key: "trader",           label: "Trader" },
  { key: "risk",             label: "Risk Manager" },
  { key: "final_decision",   label: "Portfolio Manager" },
];
```

### State

`initTicker` initialises `state[ticker]` with `reports: null`:

```js
function initTicker(ticker) {
  state[ticker] = { status: 'pending', currentAgent: null, result: null,
                    logs: [], completedAgents: new Set(), reports: null };
  ...
}
```

`applyResult` sets `state[ticker].reports = result.reports || null`.

### Card markup addition

In `renderCard()`, after the `.card-decision` div and before the closing card template backtick, add:

```html
<!-- Reports toggle -->
<button class="reports-toggle" id="reports-toggle-${ticker}"
        onclick="toggleReports('${ticker}')" style="display:none">
  REPORTS <span class="reports-arrow" id="reports-arrow-${ticker}">▾</span>
</button>

<!-- Reports section -->
<div class="reports-section" id="reports-section-${ticker}" style="display:none">
</div>
```

### CSS additions

```css
.reports-toggle {
  width: 100%; padding: 10px 24px;
  background: transparent; border: none; border-top: 1px solid var(--border);
  color: var(--amber); font-family: var(--mono); font-size: 16px;
  letter-spacing: 0.1em; text-transform: uppercase;
  cursor: pointer; text-align: left;
  transition: background 0.15s;
}
.reports-toggle:hover { background: rgba(240,165,0,0.06); }
.reports-arrow { float: right; }

.reports-section {
  border-top: 1px solid var(--border);
  background: #070a14;
}

.report-agent-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 24px;
  font-family: var(--mono); font-size: 16px; letter-spacing: 0.08em;
  text-transform: uppercase; cursor: pointer;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  transition: color 0.15s;
  user-select: none;
}
.report-agent-header:hover { color: var(--text); }
.report-agent-header.open { color: var(--amber); }
.report-agent-arrow { font-size: 12px; }

.report-agent-body {
  display: none;
  border-bottom: 1px solid var(--border);
}
.report-agent-body.open { display: block; }

.report-pre {
  margin: 0; padding: 12px 24px;
  font-family: var(--mono); font-size: 16px; line-height: 1.7;
  color: var(--text); white-space: pre-wrap; word-break: break-word;
  max-height: 300px; overflow-y: auto;
  background: transparent;
}
.report-empty {
  padding: 10px 24px;
  font-family: var(--mono); font-size: 16px;
  color: var(--text-dim); font-style: italic;
}
```

### `toggleReports(ticker)`

```js
function toggleReports(ticker) {
  const section = document.getElementById('reports-section-' + ticker);
  const arrow   = document.getElementById('reports-arrow-' + ticker);
  if (!section) return;
  const isOpen = section.style.display !== 'none';
  section.style.display = isOpen ? 'none' : 'block';
  arrow.textContent = isOpen ? '▾' : '▴';
}
```

### `toggleReportAgent(ticker, key)`

```js
function toggleReportAgent(ticker, key) {
  const header = document.getElementById('report-header-' + ticker + '-' + key);
  const body   = document.getElementById('report-body-'   + ticker + '-' + key);
  const arrow  = document.getElementById('report-arrow-'  + ticker + '-' + key);
  if (!body) return;
  const isOpen = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  header.classList.toggle('open', !isOpen);
  arrow.textContent = isOpen ? '▾' : '▴';
}
```

### `renderReports(ticker)`

Called from `applyResult` after storing reports. Rebuilds `#reports-section-{ticker}` and shows the toggle button.

```js
function renderReports(ticker) {
  const s = state[ticker];
  if (!s || !s.reports) return;

  const decision = s.result ? s.result.decision : null;
  const toggleBtn = document.getElementById('reports-toggle-' + ticker);
  const section   = document.getElementById('reports-section-' + ticker);
  if (!toggleBtn || !section) return;

  toggleBtn.style.display = 'block';

  section.innerHTML = REPORT_ORDER.map(({ key, label }) => {
    const text = s.reports[key] || '';
    const autoOpen = key === 'final_decision' ||
                     (key === 'bull' && decision === 'BUY') ||
                     (key === 'bear' && decision === 'SELL');
    const openClass = autoOpen ? ' open' : '';
    const arrowChar = autoOpen ? '▴' : '▾';
    const body = text
      ? `<pre class="report-pre">${escHtml(text)}</pre>`
      : `<div class="report-empty">— no output —</div>`;
    return `
      <div class="report-agent-header${openClass}"
           id="report-header-${ticker}-${key}"
           onclick="toggleReportAgent('${ticker}','${key}')">
        ${label}
        <span class="report-agent-arrow" id="report-arrow-${ticker}-${key}">${arrowChar}</span>
      </div>
      <div class="report-agent-body${openClass}" id="report-body-${ticker}-${key}">
        ${body}
      </div>`;
  }).join('');
}
```

### `applyResult` update

Add at the end of `applyResult`, after the chart signal update:

```js
if (result.reports) {
    state[ticker].reports = result.reports;
    renderReports(ticker);
}
```

---

## Files Changed

| File | Action | Responsibility |
|---|---|---|
| `backend.py` | Modify | `_extract_reports()` helper, capture `final_state`, add `reports` to result and demo return |
| `dashboard.html` | Modify | `REPORT_ORDER`, CSS, toggle button + section in `renderCard`, `toggleReports`, `toggleReportAgent`, `renderReports`, `applyResult` update |
