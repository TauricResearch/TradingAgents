# Real Data Wiring — Design Spec

**Date:** 2026-05-25  
**Status:** Approved

## Overview

Replace three heuristic values in the report viewer with real data emitted by the agents and the CLI. All changes are backward-compatible: old reports without the new fields fall back to existing heuristics.

---

## Change 1 — Confidence Field (Portfolio Manager)

### Backend (`tradingagents/agents/schemas.py`)

Add `confidence: float` to `PortfolioDecision`:

```python
confidence: float = Field(
    description=(
        "Your conviction in this recommendation, from 0.0 (very uncertain) "
        "to 1.0 (very certain). Base it on: convergence of analyst views, "
        "strength of supporting evidence, clarity of the bull/bear debate "
        "outcome, and degree of risk analyst agreement."
    ),
)
```

Update `render_pm_decision()` to emit the field after Rating:

```
**Confidence**: 0.78
```

### Viewer (`app/data.jsx`)

`parseFieldedMarkdown()` already picks up `**Confidence**` with no changes needed there.

Update `confidenceFromReport()` to prefer the real value:

```js
function confidenceFromReport(report) {
  const real = parseFloat(report.decision["Confidence"]);
  if (!isNaN(real)) return Math.max(0, Math.min(1, real));
  // ... existing heuristic fallback ...
}
```

**Backward compatibility:** old reports lacking the field return `NaN` from `parseFloat`; the `isNaN` guard falls through to the existing heuristic.

---

## Change 2 — Bull Weight (Research Manager)

### Backend (`tradingagents/agents/schemas.py`)

Add `bull_weight: float` to `ResearchPlan`:

```python
bull_weight: float = Field(
    description=(
        "Fraction of weight given to the bull thesis, 0.0 (bear dominates) "
        "to 1.0 (bull dominates). Assign based on the quality and quantity "
        "of compelling arguments on each side of the debate."
    ),
)
```

Update `render_research_plan()` to emit the field:

```
**Bull Weight**: 0.65
```

### Viewer (`app/data.jsx` + `app/StoryView.jsx`)

In `loadReport()`, parse the research manager's output alongside decision and trader:

```js
const researchFields = parseFieldedMarkdown(docs["2_research"]?.manager || "");
return { folder, docs, decision: decisionFields, trader: traderFields, research: researchFields };
```

In `StoryView.jsx`, replace the verdict-based heuristic:

```js
const realBullWeight = parseFloat(report.research?.["Bull Weight"]);
let bullWeight = !isNaN(realBullWeight)
  ? Math.max(0, Math.min(1, realBullWeight))
  : (verdict.kind === "BUY" ? 0.72 : verdict.kind === "SELL" ? 0.28 : 0.5);
```

**Backward compatibility:** old reports without `**Bull Weight**` fall back to the verdict-based estimate.

---

## Change 3 — Live Current Price via meta.json

### CLI (`cli/main.py`)

After `save_report_to_disk()` succeeds, write `meta.json` into the report folder:

```python
import json
meta = {}
try:
    import yfinance as yf
    info = yf.Ticker(selections["ticker"]).fast_info
    price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
    if price:
        meta["current_price"] = round(float(price), 4)
    long_name = yf.Ticker(selections["ticker"]).info.get("longName", "")
    if long_name:
        meta["company"] = long_name
except Exception:
    pass
meta["ticker"] = selections["ticker"]
meta["analysis_date"] = selections["analysis_date"]
(save_path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
```

If yfinance fails or returns no price, `meta.json` is still written without `current_price` — the viewer falls back gracefully.

### Viewer — `app/data.jsx` (`loadReport`)

Add `meta.json` to the parallel fetch batch:

```js
let meta = {};
tasks.push(fetchText(`${base}/meta.json`).then(t => {
  if (t) { try { meta = JSON.parse(t); } catch (e) {} }
}));
// ...after all tasks resolve:
return { folder, docs, decision: decisionFields, trader: traderFields, research: researchFields, meta };
```

### Viewer — `app/App.jsx` (hub index)

Add `meta.json` fetch alongside `decision.md` and `trader.md`:

```js
const metaTxt = await fetchText(`reports/${m.folder}/meta.json`);
const meta = metaTxt ? (() => { try { return JSON.parse(metaTxt); } catch(e) { return {}; } })() : {};
// ...
current: meta.current_price ?? num(trader["Entry Price"]),
```

### Viewer — `app/StoryView.jsx`

Replace `const current = num(report.trader["Entry Price"])` with:

```js
const current = report.meta?.current_price ?? num(report.trader["Entry Price"]);
```

**Backward compatibility:** old reports without `meta.json` → `fetchText` returns null → `meta` stays `{}` → `meta.current_price` is undefined → falls back to trader's Entry Price.

---

## Files Changed

| File | Change |
|---|---|
| `tradingagents/agents/schemas.py` | Add `confidence` to `PortfolioDecision` + `bull_weight` to `ResearchPlan`; update both render functions |
| `cli/main.py` | Write `meta.json` after saving report |
| `app/data.jsx` | Update `loadReport()` to parse research fields + fetch meta.json; update `confidenceFromReport()` |
| `app/App.jsx` | Fetch `meta.json` in hub index build; use `meta.current_price` for `current` |
| `app/StoryView.jsx` | Use real `bull_weight`; use `meta.current_price` for hero price |

## Invariants

- Every change degrades gracefully on old reports (no field = fallback to heuristic).
- `meta.json` is written even if yfinance fails (just missing `current_price`).
- No changes to report markdown parsing contracts or the `**Field**:` header format.
- No changes to the CLI display, memory log, or signal processing — only the saved `.md` and new `meta.json` are affected.
