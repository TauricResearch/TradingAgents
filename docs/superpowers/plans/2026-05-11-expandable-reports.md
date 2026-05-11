# Expandable Analyst Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle per-agent report text into the `analysis_complete` WebSocket event and render a collapsible "REPORTS" section on each card with one nested toggle per agent.

**Architecture:** `backend.py` gains a module-level `_extract_reports()` helper that pulls all 10 report fields from `final_state` (currently discarded). The result dict gains a `reports` field that flows into `analysis_complete` and `watched_tickers["last_result"]` automatically. The frontend stores reports in `state[ticker].reports` and renders them via a `renderReports()` function called from `applyResult`.

**Tech Stack:** Python/FastAPI (backend), vanilla JS (dashboard.html), pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend.py` | Modify | `_extract_reports()`, capture `final_state`, `reports` in result + demo return |
| `dashboard.html` | Modify | `REPORT_ORDER`, `reports: null` in `initTicker`, CSS, card markup, JS functions, `applyResult` update |
| `tests/test_reports.py` | Create | Unit tests for `_extract_reports()` |

---

## Task 1: `backend.py` — `_extract_reports` + wire-up

**Files:**
- Create: `tests/test_reports.py`
- Modify: `backend.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reports.py`:

```python
# tests/test_reports.py
import pytest


class TestExtractReports:
    def test_extracts_basic_string_fields(self):
        from backend import _extract_reports
        state = {
            "market_report": "Market analysis here",
            "sentiment_report": "Sentiment text",
            "news_report": "News text",
            "fundamentals_report": "Fundamentals text",
            "trader_investment_plan": "Trader plan",
            "final_trade_decision": "**Rating**: Buy",
        }
        r = _extract_reports(state)
        assert r["market"] == "Market analysis here"
        assert r["sentiment"] == "Sentiment text"
        assert r["news"] == "News text"
        assert r["fundamentals"] == "Fundamentals text"
        assert r["trader"] == "Trader plan"
        assert r["final_decision"] == "**Rating**: Buy"

    def test_joins_bull_history_list_with_double_newline(self):
        from backend import _extract_reports
        state = {
            "investment_debate_state": {
                "bull_history": ["Message 1", "Message 2", "Message 3"],
                "bear_history": ["Bear msg"],
                "judge_decision": "Research manager decision",
            }
        }
        r = _extract_reports(state)
        assert r["bull"] == "Message 1\n\nMessage 2\n\nMessage 3"
        assert r["bear"] == "Bear msg"
        assert r["research_manager"] == "Research manager decision"

    def test_joins_risk_history_list(self):
        from backend import _extract_reports
        state = {
            "risk_debate_state": {
                "history": ["Risk msg A", "Risk msg B"],
            }
        }
        r = _extract_reports(state)
        assert r["risk"] == "Risk msg A\n\nRisk msg B"

    def test_missing_fields_return_empty_string(self):
        from backend import _extract_reports
        r = _extract_reports({})
        assert r["market"] == ""
        assert r["bull"] == ""
        assert r["risk"] == ""
        assert r["research_manager"] == ""
        assert r["final_decision"] == ""

    def test_none_values_return_empty_string(self):
        from backend import _extract_reports
        state = {
            "market_report": None,
            "final_trade_decision": None,
            "investment_debate_state": {"bull_history": None, "bear_history": None},
        }
        r = _extract_reports(state)
        assert r["market"] == ""
        assert r["final_decision"] == ""
        assert r["bull"] == ""

    def test_returns_all_ten_keys(self):
        from backend import _extract_reports
        r = _extract_reports({})
        expected_keys = {
            "market", "sentiment", "news", "fundamentals",
            "bull", "bear", "research_manager", "trader", "risk", "final_decision"
        }
        assert set(r.keys()) == expected_keys
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_reports.py -v
```

Expected: `ImportError: cannot import name '_extract_reports' from 'backend'`

- [ ] **Step 3: Add `_extract_reports` to `backend.py`**

Find the `class LiveCapture` block (around line 91). Add `_extract_reports` immediately before it:

```python
def _extract_reports(state: dict) -> dict:
    """Extract per-agent report text from graph final_state."""
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

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_reports.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Capture `final_state` in `_run_real_analysis`**

Find (around line 159):

```python
        _, decision_raw = ta.propagate(ticker, analysis_date, on_node=node_callback)
```

Replace with:

```python
        final_state, decision_raw = ta.propagate(ticker, analysis_date, on_node=node_callback)
```

- [ ] **Step 6: Add `reports` to `_run_real_analysis` return dict**

Find the `return` statement at the end of `_run_real_analysis` (around line 177):

```python
    return {
        "decision": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "timestamp": datetime.now().isoformat(),
    }
```

Replace with:

```python
    return {
        "decision": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "timestamp": datetime.now().isoformat(),
        "reports": _extract_reports(final_state),
    }
```

- [ ] **Step 7: Add `reports: None` to `_demo_analysis` return dict**

Find the `return` dict at the end of `_demo_analysis` (around line 135):

```python
    return {
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasons[decision],
        "timestamp": datetime.now().isoformat(),
    }
```

Replace with:

```python
    return {
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasons[decision],
        "timestamp": datetime.now().isoformat(),
        "reports": None,
    }
```

- [ ] **Step 8: Run all backend tests**

```
pytest tests/test_reports.py tests/test_trade_endpoint.py tests/test_portfolio.py tests/test_chart_endpoint.py -q
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```
git add backend.py tests/test_reports.py
git commit -m "feat(reports): add _extract_reports, capture final_state, include reports in analysis_complete"
```

---

## Task 2: Frontend — constants, CSS, card markup

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add `REPORT_ORDER` constant**

Find the constants section (around line 594). After `AGENT_SHORT` and `agentClass`, add:

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

- [ ] **Step 2: Add `reports: null` to `initTicker`**

Find `initTicker` (around line 998):

```js
function initTicker(ticker) {
  state[ticker] = { status: 'pending', currentAgent: null, result: null, logs: [], completedAgents: new Set() };
  renderCard(ticker);
  updateCardPosition(ticker);
  updateEmptyState();
  updateFooter();
}
```

Replace with:

```js
function initTicker(ticker) {
  state[ticker] = { status: 'pending', currentAgent: null, result: null,
                    logs: [], completedAgents: new Set(), reports: null };
  renderCard(ticker);
  updateCardPosition(ticker);
  updateEmptyState();
  updateFooter();
}
```

- [ ] **Step 3: Add CSS**

Find `</style>` just before the Chart.js CDN script tag. Add these styles inside `<style>` immediately before `</style>`:

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
.report-agent-body { display: none; border-bottom: 1px solid var(--border); }
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

- [ ] **Step 4: Add toggle button and reports section to `renderCard()`**

Find the `<!-- Decision -->` section in `renderCard()` and the closing backtick just after it (around line 1165):

```html
    <!-- Decision -->
    <div class="card-decision" id="decision-${ticker}">
      <div class="decision-row">
        <span style="font-family:var(--mono);font-size:11px;color:var(--text-dim);text-transform:uppercase;">Awaiting analysis…</span>
      </div>
    </div>
  `;
```

Replace with:

```html
    <!-- Decision -->
    <div class="card-decision" id="decision-${ticker}">
      <div class="decision-row">
        <span style="font-family:var(--mono);font-size:11px;color:var(--text-dim);text-transform:uppercase;">Awaiting analysis…</span>
      </div>
    </div>

    <!-- Reports toggle -->
    <button class="reports-toggle" id="reports-toggle-${ticker}"
            onclick="toggleReports('${ticker}')" style="display:none">
      REPORTS <span class="reports-arrow" id="reports-arrow-${ticker}">▾</span>
    </button>

    <!-- Reports section -->
    <div class="reports-section" id="reports-section-${ticker}" style="display:none">
    </div>
  `;
```

- [ ] **Step 5: Commit**

```
git add dashboard.html
git commit -m "feat(reports): add REPORT_ORDER, reports:null in initTicker, CSS, card markup"
```

---

## Task 3: Frontend — JS functions + `applyResult` wire-up

**Files:**
- Modify: `dashboard.html`

- [ ] **Step 1: Add `toggleReports`, `toggleReportAgent`, `renderReports` functions**

Find the `// ── Portfolio ──` section comment. Add a new `// ── Reports ──` section immediately before it:

```js
// ── Reports ──────────────────────────────────────────────────────────────
function toggleReports(ticker) {
  const section = document.getElementById('reports-section-' + ticker);
  const arrow   = document.getElementById('reports-arrow-' + ticker);
  if (!section) return;
  const isOpen = section.style.display !== 'none';
  section.style.display = isOpen ? 'none' : 'block';
  arrow.textContent = isOpen ? '▾' : '▴';
}

function toggleReportAgent(ticker, key) {
  const header = document.getElementById('report-header-' + ticker + '-' + key);
  const body   = document.getElementById('report-body-'   + ticker + '-' + key);
  const arrow  = document.getElementById('report-arrow-'  + ticker + '-' + key);
  if (!body) return;
  const isOpen = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  if (header) header.classList.toggle('open', !isOpen);
  if (arrow)  arrow.textContent = isOpen ? '▾' : '▴';
}

function renderReports(ticker) {
  const s = state[ticker];
  if (!s || !s.reports) return;

  const decision  = s.result ? s.result.decision : null;
  const toggleBtn = document.getElementById('reports-toggle-' + ticker);
  const section   = document.getElementById('reports-section-' + ticker);
  if (!toggleBtn || !section) return;

  toggleBtn.style.display = 'block';

  section.innerHTML = REPORT_ORDER.map(({ key, label }) => {
    const text     = s.reports[key] || '';
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

- [ ] **Step 2: Update `applyResult` to call `renderReports`**

Find `applyResult` (around line 1022). After the chart signal update block at the end of the function, add:

```js
  if (result.reports) {
    state[ticker].reports = result.reports;
    renderReports(ticker);
  }
```

The full end of `applyResult` should look like:

```js
  // Update signal overlay if chart already loaded
  const chart = chartInstances[ticker];
  if (chart && result) {
    const labels = chart.data.labels;
    const closeDs = chart.data.datasets.find(d => d.label === 'Close');
    const closeValues = closeDs ? closeDs.data : [];
    chart.data.datasets = chart.data.datasets.filter(d => d.label !== 'Signal');
    const signalDs = _signalDataset(result.decision, closeValues);
    if (signalDs) chart.data.datasets.push(signalDs);
    chart.update();
  }
  if (result.reports) {
    state[ticker].reports = result.reports;
    renderReports(ticker);
  }
}
```

- [ ] **Step 3: Run all backend tests**

```
pytest tests/ -q --ignore=tests/backtesting
```

Expected: all tests PASS.

- [ ] **Step 4: Smoke test in browser**

1. Verify backend is running (port 8000 active): `curl -s http://localhost:8000/api/status`
2. Open `http://localhost:8000`, add any watched ticker
3. After analysis completes, a "REPORTS ▾" button should appear at the bottom of the card
4. Click it — the reports section expands showing 10 collapsible agent blocks
5. "Portfolio Manager" and (BUY→ "Bull Researcher" / SELL→ "Bear Researcher") should be open by default
6. Click any collapsed agent header — it expands showing the preformatted text
7. Click again — it collapses
8. Click "REPORTS ▴" again — the whole section collapses

- [ ] **Step 5: Commit**

```
git add dashboard.html
git commit -m "feat(reports): add toggleReports, toggleReportAgent, renderReports, wire into applyResult"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `_extract_reports` at module level, testable | Task 1 |
| `join_list` joins lists with `"\n\n"`, strings as-is, None → `""` | Task 1 |
| All 10 report keys with empty-string defaults | Task 1 |
| `final_state, decision_raw = ta.propagate(...)` | Task 1 |
| `"reports": _extract_reports(final_state)` in real result | Task 1 |
| `"reports": None` in demo result | Task 1 |
| `REPORT_ORDER` constant with 10 `{key, label}` entries | Task 2 |
| `reports: null` in `initTicker` state | Task 2 |
| CSS: `.reports-toggle`, `.reports-section`, `.report-agent-header`, `.report-agent-body`, `.report-pre`, `.report-empty` | Task 2 |
| Toggle button hidden by default (`style="display:none"`) | Task 2 |
| Reports section hidden by default | Task 2 |
| `toggleReports` — shows/hides section, flips arrow | Task 3 |
| `toggleReportAgent` — expands/collapses individual agent | Task 3 |
| `renderReports` — shows toggle button, builds 10 agent blocks | Task 3 |
| Auto-expand: `final_decision` always, `bull` if BUY, `bear` if SELL | Task 3 |
| Empty report → `"— no output —"` dim italic | Task 3 |
| `max-height: 300px; overflow-y: auto` on `.report-pre` | Task 2 (CSS) |
| `applyResult` calls `renderReports` after chart signal update | Task 3 |
