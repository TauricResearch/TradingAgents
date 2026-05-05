# Historical Report Reuse — Staged Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make past reports and reflexion actually useful by feeding prior decisions and analyses into new agent runs in stages, starting with a 5-minute cut and growing toward full as-of-date provenance.

**Architecture:** Add a thin `historical_context` helper module that scans `reports/daily/{date}/{run_id}/` directories for the most recent prior artifact for a given ticker/portfolio (capped to a lookback window). Inject the resulting summary string into Trader → Research Manager → Bull/Bear → PM prompts via existing `AgentState`. Later stages add real P&L wiring into reflexion, as-of-date filtering, and persistence of PM decisions into the `micro_reflexion` BM25 store so the existing memory retrieval picks them up automatically.

**Tech Stack:** Python 3.11+, pytest, LangGraph, existing `ReportStore` / `FinancialSituationMemory` infrastructure.

---

## Stage Map

- **Stage 1 (5-min cut):** Trader sees the prior trader plan + last PM decision for the same ticker. ✅ Done
- **Stage 1.5:** Trader, Research Manager, PM, and Risk debaters all see prior execution failures (insufficient cash, constraint violations) so they can course-correct on re-runs.
- **Stage 2:** Research Manager and PM also see prior analysis context (analyst reports).
- **Stage 3:** Replace hardcoded `reflect_and_remember(1000)` with real realised P&L from `execution_result.json`; tag execution failures into `complete_report.json` so historical context carries outcome signals.
- **Stage 4:** Add `as_of_date` filtering everywhere (lookback window, no future leakage in backtests).
- **Stage 5:** Persist PM decisions into the `portfolio_manager_memory` (BM25) store after each run so future similarity retrieval picks them up.

Each stage ships a working, committable change. Do not start Stage N+1 until Stage N is merged.

---

# Stage 1 — 5-Minute Cut: Wire prior trader plan + PM decision into the Trader prompt

**Goal:** When Trader runs for ticker `T` on date `D`, find the most recent prior date `D' < D` that has a `complete_report.json` for `T` and the most recent prior `pm_decision.json`, and inject them into the Trader's system prompt.

**Files:**
- Create: `tradingagents/agents/utils/historical_context.py`
- Create: `tests/agents/utils/test_historical_context.py`
- Modify: `tradingagents/agents/trader/trader.py`
- Modify: `tests/agents/trader/test_trader.py` (or create if missing)

---

### Task 1.1: Create historical-context loader with failing test

**Files:**
- Create: `tests/agents/utils/test_historical_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/utils/test_historical_context.py
import json
from datetime import date
from pathlib import Path

import pytest

from tradingagents.agents.utils.historical_context import (
    find_latest_prior_analysis,
    find_latest_prior_pm_decision,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_find_latest_prior_analysis_returns_most_recent_before_target(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-25" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "OLD plan"},
    )
    _write(
        base / "2026-04-28" / "RUN2" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "NEW plan"},
    )

    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"
    assert found["data"]["trader_investment_plan"] == "NEW plan"


def test_find_latest_prior_analysis_excludes_target_date(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-05-01" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "TODAY"},
    )
    _write(
        base / "2026-04-28" / "RUN2" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "PRIOR"},
    )

    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"


def test_find_latest_prior_analysis_respects_lookback(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-01-01" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "ANCIENT"},
    )

    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is None


def test_find_latest_prior_analysis_returns_none_when_missing(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    found = find_latest_prior_analysis(
        ticker="AAPL",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )
    assert found is None


def test_find_latest_prior_pm_decision(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_pm_decision.json",
        {"decision": "BUY AAPL 100 shares"},
    )

    found = find_latest_prior_pm_decision(
        portfolio_id="default",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"
    assert found["data"]["decision"] == "BUY AAPL 100 shares"
```

- [ ] **Step 2: Run test, confirm it fails**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: ImportError — module does not exist.

- [ ] **Step 3: Implement the module**

Create `tradingagents/agents/utils/historical_context.py`:

```python
"""Lookup helpers for prior-run reports (read-only, filesystem-backed).

These are intentionally tiny and pure: they walk the
``reports/daily/{date}/{run_id}/...`` tree looking for the most recent
artifact that predates ``as_of_date`` and falls within ``lookback_days``.

The functions never raise on missing files — they return ``None`` so callers
can fall back gracefully.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.report_paths import REPORTS_ROOT


def _parse_iso(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _candidate_dates(
    reports_root: Path,
    as_of_date: str,
    lookback_days: int,
) -> list[str]:
    target = _parse_iso(as_of_date)
    if target is None or not reports_root.exists():
        return []
    earliest = target - timedelta(days=lookback_days)
    out: list[date] = []
    for child in reports_root.iterdir():
        if not child.is_dir():
            continue
        d = _parse_iso(child.name)
        if d is None:
            continue
        if earliest <= d < target:
            out.append(d)
    out.sort(reverse=True)
    return [d.isoformat() for d in out]


def _load_latest_in_date(
    date_dir: Path,
    relative_subpath: str,
    suffix: str,
) -> dict[str, Any] | None:
    if not date_dir.exists():
        return None
    matches: list[Path] = []
    for run_dir in date_dir.iterdir():
        if not run_dir.is_dir():
            continue
        scan_dir = run_dir / relative_subpath
        if not scan_dir.exists():
            continue
        matches.extend(p for p in scan_dir.glob(f"*{suffix}") if p.is_file())
    if not matches:
        return None
    matches.sort(key=lambda p: p.name, reverse=True)
    try:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_latest_prior_analysis(
    ticker: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent ``complete_report.json`` strictly before ``as_of_date``.

    Returns ``{"date": "YYYY-MM-DD", "data": {...}}`` or ``None``.
    """
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            f"{ticker.upper()}/report",
            "complete_report.json",
        )
        if data is not None:
            return {"date": d, "data": data}
    return None


def find_latest_prior_pm_decision(
    portfolio_id: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent ``{portfolio_id}_pm_decision.json`` strictly before ``as_of_date``."""
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            "portfolio/report",
            f"{portfolio_id}_pm_decision.json",
        )
        if data is not None:
            return {"date": d, "data": data}
    return None
```

- [ ] **Step 4: Run tests, confirm pass**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/historical_context.py tests/agents/utils/test_historical_context.py
git commit -m "feat: add historical_context loader for prior-run reports"
```

---

### Task 1.2: Add config knob for lookback window

**Files:**
- Modify: `tradingagents/default_config.py`

- [ ] **Step 1: Add config entry**

In `tradingagents/default_config.py`, find the `DEFAULT_CONFIG` dict and add this line near other tuning knobs:

```python
    "historical_context_lookback_days": 60,
```

- [ ] **Step 2: Verify tests still pass**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add tradingagents/default_config.py
git commit -m "feat: add historical_context_lookback_days config knob"
```

---

### Task 1.3: Build a one-screen summary formatter

**Files:**
- Modify: `tradingagents/agents/utils/historical_context.py`
- Modify: `tests/agents/utils/test_historical_context.py`

- [ ] **Step 1: Write failing test**

Append to `tests/agents/utils/test_historical_context.py`:

```python
from tradingagents.agents.utils.historical_context import format_prior_context_block


def test_format_prior_context_block_renders_compactly() -> None:
    prior_analysis = {
        "date": "2026-04-28",
        "data": {
            "trader_investment_plan": "BUY at $180, stop $170, target $200",
            "final_trade_decision": "BUY",
        },
    }
    prior_pm = {
        "date": "2026-04-28",
        "data": {
            "decision": "BUY 100 AAPL @ market",
            "rationale": "Earnings momentum",
        },
    }

    out = format_prior_context_block(
        ticker="AAPL",
        prior_analysis=prior_analysis,
        prior_pm_decision=prior_pm,
        max_chars=1200,
    )

    assert "AAPL" in out
    assert "2026-04-28" in out
    assert "BUY at $180" in out
    assert "BUY 100 AAPL" in out
    assert len(out) <= 1200


def test_format_prior_context_block_handles_missing() -> None:
    out = format_prior_context_block(
        ticker="AAPL",
        prior_analysis=None,
        prior_pm_decision=None,
        max_chars=1200,
    )
    assert out == ""
```

- [ ] **Step 2: Run, confirm fail**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: ImportError on `format_prior_context_block`.

- [ ] **Step 3: Implement**

Append to `tradingagents/agents/utils/historical_context.py`:

```python
def _truncate(text: str, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def format_prior_context_block(
    ticker: str,
    prior_analysis: dict[str, Any] | None,
    prior_pm_decision: dict[str, Any] | None,
    max_chars: int = 1200,
) -> str:
    """Format prior analysis + PM decision as a compact prompt block.

    Returns an empty string if both inputs are ``None``.
    """
    if not prior_analysis and not prior_pm_decision:
        return ""
    per_section = max(200, (max_chars - 200) // 2)
    parts: list[str] = [f"## Prior Run Context for {ticker.upper()}"]
    if prior_analysis:
        d = prior_analysis.get("date", "?")
        data = prior_analysis.get("data") or {}
        plan = data.get("trader_investment_plan") or data.get("final_trade_decision") or ""
        parts.append(
            f"\n### Last Trader Plan ({d})\n{_truncate(plan, per_section)}"
        )
    if prior_pm_decision:
        d = prior_pm_decision.get("date", "?")
        data = prior_pm_decision.get("data") or {}
        decision = data.get("decision") or ""
        rationale = data.get("rationale") or ""
        body = decision if not rationale else f"{decision}\n\nRationale: {rationale}"
        parts.append(
            f"\n### Last PM Decision ({d})\n{_truncate(body, per_section)}"
        )
    out = "\n".join(parts)
    return _truncate(out, max_chars)
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/historical_context.py tests/agents/utils/test_historical_context.py
git commit -m "feat: add format_prior_context_block for prior-run prompt injection"
```

---

### Task 1.4: Inject prior context into Trader prompt

**Files:**
- Modify: `tradingagents/agents/trader/trader.py`
- Create: `tests/agents/trader/test_trader_prior_context.py`

- [ ] **Step 1: Write failing test**

Create `tests/agents/trader/test_trader_prior_context.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradingagents.agents.trader.trader import create_trader


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_trader_includes_prior_context_when_available(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "PRIOR PLAN: BUY $180 stop $170"},
    )

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="• BUY at $182\n• Stop $172\n• Target $200")
    memory = MagicMock()
    memory.get_memories.return_value = []

    state = {
        "company_of_interest": "AAPL",
        "investment_plan": "Manager says BUY",
        "investment_plan_structured": {"status": "completed"},
        "market_report": "tech setup positive",
        "sentiment_report": "neutral",
        "news_report": "earnings beat",
        "fundamentals_report": "PE 28",
        "trade_date": "2026-05-01",
        "scanner_graph_context_text": "",
    }

    with (
        patch("tradingagents.agents.trader.trader.invoke_with_timeout",
              return_value=(fake_llm.invoke.return_value, None)),
        patch("tradingagents.agents.utils.historical_context.REPORTS_ROOT", str(tmp_path / "reports")),
        patch("tradingagents.agents.trader.trader.build_trader_plan_structured",
              return_value={"status": "completed"}),
    ):
        node = create_trader(fake_llm, memory)
        result = node(state)

    assert "trader_investment_plan" in result
```

- [ ] **Step 2: Run, confirm it fails (or passes only without exercising prior context)**

Run: `pytest tests/agents/trader/test_trader_prior_context.py -v`
Expected: collection passes; the assertion alone is loose. The real verification is in Step 4 below.

- [ ] **Step 3: Modify the trader to fetch + inject prior context**

In `tradingagents/agents/trader/trader.py`:

1. Add import at top:

```python
from tradingagents.agents.utils.historical_context import (
    find_latest_prior_analysis,
    find_latest_prior_pm_decision,
    format_prior_context_block,
)
from tradingagents.default_config import DEFAULT_CONFIG
```

(The `DEFAULT_CONFIG` import already exists — keep one copy.)

2. Inside `trader_node`, after the existing line `past_memory_str = ...` (around line 75) and before the `anonymize_ticker` calls, add:

```python
        prior_analysis = find_latest_prior_analysis(
            ticker=ticker,
            as_of_date=str(state.get("trade_date") or ""),
        )
        prior_pm_decision = find_latest_prior_pm_decision(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "default"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        prior_context_block = format_prior_context_block(
            ticker=ticker,
            prior_analysis=prior_analysis,
            prior_pm_decision=prior_pm_decision,
            max_chars=1200,
        )
        anon_prior_context = (
            anonymize_ticker(prior_context_block, ticker) if prior_context_block else ""
        )
```

3. Replace the system message construction so the prior-context block is appended after `Apply lessons from past decisions:`. Update the system message content to:

```python
                "content": f"""You are a trading execution specialist converting the Research Manager's recommendation into a precise transaction proposal.

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis. NO conversational filler.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives.
- Every proposal must include entry price, stop-loss (5-15% below entry), and take-profit (10-30% above entry).
- For the Catalyst Timeline, use ONLY dates from the Scanner Ground-Truth Data section. Do NOT estimate or invent earnings dates, FOMC dates, CPI dates, or any other event dates.

YOUR TASK:
1. **Research Manager's Verdict**: Restate the recommendation and top evidence.
2. **Entry Setup**: Specific entry price or range with technical justification.
3. **Risk Parameters**: Stop-loss level, take-profit target, position size rationale.
4. **Catalyst Timeline**: Key upcoming dates (earnings, ex-div, macro events) from the ground-truth calendar data ONLY.
5. **FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL****

Apply lessons from past decisions:
{anon_past_memory_str}

{anon_prior_context}""",
```

- [ ] **Step 4: Strengthen the test to assert prior context lands in the prompt**

Replace the body of `test_trader_includes_prior_context_when_available` with a version that captures the messages passed to `invoke_with_timeout`:

```python
def test_trader_includes_prior_context_when_available(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "PRIOR PLAN: BUY $180 stop $170"},
    )

    fake_llm = MagicMock()
    response = MagicMock(content="• BUY at $182\n• Stop $172\n• Target $200")
    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return response, None

    state = {
        "company_of_interest": "AAPL",
        "investment_plan": "Manager says BUY",
        "investment_plan_structured": {"status": "completed"},
        "market_report": "tech setup positive",
        "sentiment_report": "neutral",
        "news_report": "earnings beat",
        "fundamentals_report": "PE 28",
        "trade_date": "2026-05-01",
        "scanner_graph_context_text": "",
    }

    with (
        patch("tradingagents.agents.trader.trader.invoke_with_timeout", side_effect=fake_invoke),
        patch("tradingagents.agents.utils.historical_context.REPORTS_ROOT", str(tmp_path / "reports")),
        patch("tradingagents.agents.trader.trader.build_trader_plan_structured",
              return_value={"status": "completed"}),
    ):
        node = create_trader(fake_llm, memory)
        node(state)

    system_msg = captured["messages"][0]["content"]
    assert "Prior Run Context" in system_msg
    assert "PRIOR PLAN" in system_msg
    assert "2026-04-28" in system_msg
```

- [ ] **Step 5: Run, confirm pass**

Run: `pytest tests/agents/trader/test_trader_prior_context.py -v`
Expected: 1 passed.

- [ ] **Step 6: Run the full suite, confirm no regressions**

Run: `pytest tests/ -v -m "not integration"`
Expected: all green (or pre-existing failures unchanged).

- [ ] **Step 7: Commit**

```bash
git add tradingagents/agents/trader/trader.py tests/agents/trader/test_trader_prior_context.py
git commit -m "feat(trader): inject prior trader plan + PM decision into prompt"
```

**Stage 1 ships here.** Stop, merge, observe one or two real runs before continuing.

---

# Stage 1.5 — Inject execution failures into action-taking nodes

**Goal:** When a prior run produced execution failures (insufficient cash, constraint violations, missing prices, order guard rejections), surface those failures in the prompts of the nodes that make sizing and action decisions — Trader, Research Manager, Portfolio Manager, and Risk debaters. These nodes should see "last time you proposed X and it was rejected because Y" so they self-correct without a human needing to re-prompt.

**Why these four and not others:**
- **Trader** — proposes position sizes; knowing the last plan was rejected for exceeding cash fixes the root cause.
- **Research Manager** — sets direction and conviction; can add explicit sizing caution if prior execution failed.
- **Portfolio Manager** — builds the actual buy/sell list with share counts; most directly responsible for cash/constraint violations.
- **Risk debaters (aggressive, conservative, neutral)** — evaluate trade risk; a prior constraint violation is exactly the risk they should flag.
- **Bull/Bear researchers** — debate stock direction, not portfolio fit. Execution failures don't change whether a stock is a good idea; excluded.

**Execution failures live in:** `reports/daily/{date}/{run_id}/portfolio/report/*_execution_result.json` under the `failed_trades` key. Structure:
```json
{
  "failed_trades": [
    {"action": "BUY", "ticker": "AAPL", "reason": "Constraint violation",
     "violations": ["Insufficient cash: cost $38,000 > available $5,000",
                    "Max position size exceeded: would be 22% > 15% limit"]}
  ]
}
```

**Files:**
- Modify: `tradingagents/agents/utils/historical_context.py` — add `find_latest_prior_execution_failures` and `format_execution_failures_block`
- Modify: `tests/agents/utils/test_historical_context.py` — add tests for the new functions
- Modify: `tradingagents/agents/trader/trader.py` — append failures block
- Modify: `tradingagents/agents/managers/research_manager.py` — append failures block
- Modify: `tradingagents/agents/managers/portfolio_manager.py` — append failures block
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py` — append failures block
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py` — append failures block
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py` — append failures block
- Create: `tests/agents/managers/test_pm_execution_failures.py`
- Create: `tests/agents/managers/test_research_manager_execution_failures.py`
- Create: `tests/agents/risk_mgmt/test_risk_debater_execution_failures.py`

---

### Task 1.5.1: Add execution-failure loader and formatter to `historical_context.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/agents/utils/test_historical_context.py`:

```python
from tradingagents.agents.utils.historical_context import (
    find_latest_prior_execution_failures,
    format_execution_failures_block,
)


def test_find_latest_prior_execution_failures_returns_failed_trades(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_execution_result.json",
        {
            "failed_trades": [
                {
                    "action": "BUY",
                    "ticker": "AAPL",
                    "reason": "Constraint violation",
                    "violations": ["Insufficient cash: cost $38,000 > available $5,000"],
                }
            ],
            "executed_trades": [],
        },
    )

    found = find_latest_prior_execution_failures(
        portfolio_id="default",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is not None
    assert found["date"] == "2026-04-28"
    assert len(found["failed_trades"]) == 1
    assert found["failed_trades"][0]["ticker"] == "AAPL"


def test_find_latest_prior_execution_failures_skips_empty_failed_trades(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_execution_result.json",
        {"failed_trades": [], "executed_trades": []},
    )

    found = find_latest_prior_execution_failures(
        portfolio_id="default",
        as_of_date="2026-05-01",
        reports_root=base,
        lookback_days=30,
    )

    assert found is None


def test_format_execution_failures_block_renders_violations(tmp_path: Path) -> None:
    failures = {
        "date": "2026-04-28",
        "failed_trades": [
            {
                "action": "BUY",
                "ticker": "AAPL",
                "reason": "Constraint violation",
                "violations": [
                    "Insufficient cash: cost $38,000 > available $5,000",
                    "Max position size exceeded: would be 22% > 15% limit",
                ],
            },
            {
                "action": "BUY",
                "ticker": "MSFT",
                "reason": "No price found for MSFT",
            },
        ],
    }

    out = format_execution_failures_block(failures, max_chars=1200)

    assert "2026-04-28" in out
    assert "AAPL" in out
    assert "Insufficient cash" in out
    assert "MSFT" in out
    assert len(out) <= 1200


def test_format_execution_failures_block_returns_empty_for_none() -> None:
    assert format_execution_failures_block(None, max_chars=1200) == ""
```

- [ ] **Step 2: Run, confirm fail**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: ImportError on `find_latest_prior_execution_failures`.

- [ ] **Step 3: Implement in `historical_context.py`**

Append to `tradingagents/agents/utils/historical_context.py`:

```python
def find_latest_prior_execution_failures(
    portfolio_id: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent execution result that contains at least one failed trade.

    Skips dates where ``failed_trades`` is empty or absent.
    Returns ``{"date": "YYYY-MM-DD", "failed_trades": [...]}`` or ``None``.
    """
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            "portfolio/report",
            f"{portfolio_id}_execution_result.json",
        )
        if data is None:
            continue
        failed = data.get("failed_trades") or []
        if not failed:
            continue
        return {"date": d, "failed_trades": failed}
    return None


def format_execution_failures_block(
    failures: dict[str, Any] | None,
    max_chars: int = 800,
) -> str:
    """Format prior execution failures as a compact warning block.

    Returns an empty string if ``failures`` is ``None`` or has no failed trades.

    Note: does not contain ticker symbols by default — violations are portfolio-level.
    Callers should still anonymize if ticker names appear in violation messages.
    """
    if not failures:
        return ""
    failed_trades = failures.get("failed_trades") or []
    if not failed_trades:
        return ""
    d = failures.get("date", "?")
    lines = [f"## Prior Run Execution Failures ({d})"]
    lines.append("These trades were REJECTED by the execution layer. Do not repeat them.")
    for ft in failed_trades:
        action = ft.get("action", "?")
        ticker = ft.get("ticker", "?")
        reason = ft.get("reason", "unknown")
        violations = ft.get("violations") or []
        lines.append(f"\n- {action} {ticker}: {reason}")
        for v in violations:
            lines.append(f"  • {v}")
    out = "\n".join(lines)
    return _truncate(out, max_chars)
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/agents/utils/test_historical_context.py -v`
Expected: all pass (original tests + 4 new).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/historical_context.py tests/agents/utils/test_historical_context.py
git commit -m "feat(historical-context): add execution-failure loader and formatter"
```

---

### Task 1.5.2: Inject execution failures into Trader prompt

**Files:**
- Modify: `tradingagents/agents/trader/trader.py`

- [ ] **Step 1: Write failing test**

Create `tests/agents/trader/test_trader_execution_failures.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradingagents.agents.trader.trader import create_trader


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_trader_sees_prior_execution_failures_in_prompt(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_execution_result.json",
        {
            "failed_trades": [
                {
                    "action": "BUY",
                    "ticker": "AAPL",
                    "reason": "Constraint violation",
                    "violations": ["Insufficient cash: cost $38,000 > available $5,000"],
                }
            ]
        },
    )

    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return MagicMock(content="• BUY at $182\n• Stop $172\n• Target $200"), None

    state = {
        "company_of_interest": "AAPL",
        "investment_plan": "Manager says BUY",
        "investment_plan_structured": {"status": "completed"},
        "market_report": "tech setup positive",
        "sentiment_report": "neutral",
        "news_report": "earnings beat",
        "fundamentals_report": "PE 28",
        "trade_date": "2026-05-01",
        "scanner_graph_context_text": "",
    }

    with (
        patch("tradingagents.agents.trader.trader.invoke_with_timeout", side_effect=fake_invoke),
        patch("tradingagents.agents.utils.historical_context.REPORTS_ROOT", str(tmp_path / "reports")),
        patch("tradingagents.agents.trader.trader.build_trader_plan_structured",
              return_value={"status": "completed"}),
    ):
        node = create_trader(MagicMock(), memory)
        node(state)

    system_msg = captured["messages"][0]["content"]
    assert "Prior Run Execution Failures" in system_msg
    assert "Insufficient cash" in system_msg
```

- [ ] **Step 2: Run, confirm fail**

Run: `pytest tests/agents/trader/test_trader_execution_failures.py -v`
Expected: FAIL — failures block not injected.

- [ ] **Step 3: Add to `trader.py`**

In `create_trader` → `trader_node`, after the existing `prior_context_block` lookup block, add:

```python
        prior_failures = find_latest_prior_execution_failures(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "default"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        failures_block = (
            anonymize_ticker(
                truncate_text(format_execution_failures_block(prior_failures, max_chars=800), max_chars=800),
                ticker,
            )
            if prior_failures else ""
        )
```

Add the two new imports to the existing `historical_context` import line:

```python
from tradingagents.agents.utils.historical_context import (
    find_latest_prior_analysis,
    find_latest_prior_execution_failures,
    find_latest_prior_pm_decision,
    format_execution_failures_block,
    format_prior_context_block,
)
```

Append `{failures_block}` to the system message after the prior context block:

```python
{anon_prior_context}

{failures_block}""",
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/agents/trader/test_trader_execution_failures.py tests/agents/trader/test_trader_prior_context.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/trader/trader.py tests/agents/trader/test_trader_execution_failures.py
git commit -m "feat(trader): inject prior execution failures into prompt"
```

---

### Task 1.5.3: Inject execution failures into Research Manager

**Files:**
- Modify: `tradingagents/agents/managers/research_manager.py`
- Create: `tests/agents/managers/test_research_manager_execution_failures.py`

- [ ] **Step 1: Write failing test**

Create `tests/agents/managers/test_research_manager_execution_failures.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradingagents.agents.managers.research_manager import create_research_manager


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_research_manager_sees_prior_execution_failures(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_execution_result.json",
        {
            "failed_trades": [
                {
                    "action": "BUY",
                    "ticker": "AAPL",
                    "reason": "Constraint violation",
                    "violations": ["Insufficient cash: cost $38,000 > available $5,000"],
                }
            ]
        },
    )

    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return MagicMock(content="FINAL RECOMMENDATION: BUY"), None

    state = {
        "company_of_interest": "AAPL",
        "investment_debate_state": {"bull_history": "bull", "bear_history": "bear", "judge_decision": "", "count": 2},
        "market_report": "tech positive",
        "sentiment_report": "neutral",
        "news_report": "earnings beat",
        "fundamentals_report": "PE 28",
        "trade_date": "2026-05-01",
        "scanner_graph_context_text": "",
        "macro_regime_report": "",
    }

    with (
        patch("tradingagents.agents.managers.research_manager.invoke_with_timeout", side_effect=fake_invoke),
        patch("tradingagents.agents.utils.historical_context.REPORTS_ROOT", str(tmp_path / "reports")),
        patch("tradingagents.agents.managers.research_manager.build_investment_plan_structured",
              return_value={"status": "completed"}),
    ):
        node = create_research_manager(MagicMock(), memory)
        node(state)

    system_or_user = " ".join(m["content"] for m in captured["messages"] if isinstance(m, dict))
    assert "Prior Run Execution Failures" in system_or_user
    assert "Insufficient cash" in system_or_user
```

- [ ] **Step 2: Run, confirm fail**

Run: `pytest tests/agents/managers/test_research_manager_execution_failures.py -v`
Expected: FAIL.

- [ ] **Step 3: Add to `research_manager.py`**

Add imports:
```python
from tradingagents.agents.utils.historical_context import (
    find_latest_prior_execution_failures,
    format_execution_failures_block,
)
```

In `research_manager_node`, after `past_memory_str` is built, add:
```python
        prior_failures = find_latest_prior_execution_failures(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "default"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        failures_block = (
            anonymize_ticker(
                truncate_text(format_execution_failures_block(prior_failures, max_chars=600), max_chars=600),
                ticker,
            )
            if prior_failures else ""
        )
```

Append `{failures_block}` to the system/user prompt where `anon_past_memory_str` already appears.

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit:** `feat(research-manager): inject prior execution failures into prompt`

---

### Task 1.5.4: Inject execution failures into Portfolio Manager

**Files:**
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Create: `tests/agents/managers/test_pm_execution_failures.py`

The PM is the most important node for this context — it directly creates the buy/sell list that goes to the executor.

- [ ] **Step 1: Write failing test**

Create `tests/agents/managers/test_pm_execution_failures.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pm_sees_prior_execution_failures_in_prompt(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_execution_result.json",
        {
            "failed_trades": [
                {
                    "action": "BUY",
                    "ticker": "AAPL",
                    "reason": "Constraint violation",
                    "violations": [
                        "Insufficient cash: cost $38,000 > available $5,000",
                        "Max position size exceeded: would be 22% > 15% limit",
                    ],
                }
            ]
        },
    )

    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return MagicMock(content="Rating: Hold\n**Executive Summary**: Hold position."), None

    state = {
        "company_of_interest": "AAPL",
        "risk_debate_state": {"history": "risk history", "summary": "risk summary", "judge_decision": ""},
        "risk_synthesis_structured": {},
        "trader_investment_plan": "BUY AAPL",
        "market_report": "positive",
        "sentiment_report": "neutral",
        "news_report": "earnings",
        "fundamentals_report": "PE 28",
        "macro_regime_report": "",
        "trade_date": "2026-05-01",
        "abort_signal": None,
    }

    with (
        patch("tradingagents.agents.managers.portfolio_manager.invoke_with_timeout", side_effect=fake_invoke),
        patch("tradingagents.agents.utils.historical_context.REPORTS_ROOT", str(tmp_path / "reports")),
        patch("tradingagents.agents.managers.portfolio_manager.build_final_decision_structured",
              return_value={"status": "completed"}),
    ):
        node = create_portfolio_manager(MagicMock(), memory)
        node(state)

    all_content = " ".join(
        m if isinstance(m, str) else m.get("content", "") if isinstance(m, dict) else ""
        for m in captured["messages"]
    )
    assert "Prior Run Execution Failures" in all_content
    assert "Insufficient cash" in all_content
    assert "22%" in all_content
```

- [ ] **Step 2: Run, confirm fail**

Run: `pytest tests/agents/managers/test_pm_execution_failures.py -v`
Expected: FAIL.

- [ ] **Step 3: Add to `portfolio_manager.py`**

Add imports:
```python
from tradingagents.agents.utils.historical_context import (
    find_latest_prior_execution_failures,
    format_execution_failures_block,
)
```

In `portfolio_manager_node`, after `past_memory_str`, add:
```python
        prior_failures = find_latest_prior_execution_failures(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "default"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        failures_block = (
            truncate_text(format_execution_failures_block(prior_failures, max_chars=800), max_chars=800)
            if prior_failures else ""
        )
```

(PM prompt does not anonymize tickers — it operates at portfolio level, so ticker names in violation messages are intentional and useful.)

Inject `{failures_block}` into both the normal and critical-abort prompt branches, immediately after the `past_memory_str` section.

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit:** `feat(pm): inject prior execution failures into prompt`

---

### Task 1.5.5: Inject execution failures into Risk debaters

**Files:**
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`
- Create: `tests/agents/risk_mgmt/test_risk_debater_execution_failures.py`

Risk debaters evaluate whether a trade should proceed. Knowing the last identical trade was rejected for cash or concentration reasons is directly relevant to their argument.

- [ ] **Step 1: Write failing test for conservative debater** (most likely to be swayed by execution failures):

Create `tests/agents/risk_mgmt/test_risk_debater_execution_failures.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_conservative_debater_sees_prior_execution_failures(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "portfolio" / "report" / "00_default_execution_result.json",
        {
            "failed_trades": [
                {
                    "action": "BUY",
                    "ticker": "AAPL",
                    "reason": "Constraint violation",
                    "violations": ["Insufficient cash: cost $38,000 > available $5,000"],
                }
            ]
        },
    )

    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return MagicMock(content="Conservative: this trade is risky."), None

    state = {
        "company_of_interest": "AAPL",
        "trader_investment_plan": "BUY AAPL 200 shares",
        "risk_debate_state": {"history": "", "count": 0},
        "market_report": "positive",
        "sentiment_report": "neutral",
        "news_report": "earnings",
        "fundamentals_report": "PE 28",
        "macro_regime_report": "",
        "trade_date": "2026-05-01",
        "scanner_graph_context_text": "",
    }

    with (
        patch("tradingagents.agents.risk_mgmt.conservative_debator.invoke_with_timeout",
              side_effect=fake_invoke),
        patch("tradingagents.agents.utils.historical_context.REPORTS_ROOT", str(tmp_path / "reports")),
    ):
        node = create_conservative_debator(MagicMock())
        node(state)

    all_content = " ".join(
        m.get("content", "") if isinstance(m, dict) else str(m)
        for m in captured["messages"]
    )
    assert "Prior Run Execution Failures" in all_content
    assert "Insufficient cash" in all_content
```

- [ ] **Step 2: Run, confirm fail**

Run: `pytest tests/agents/risk_mgmt/test_risk_debater_execution_failures.py -v`
Expected: FAIL.

- [ ] **Step 3: Add to all three debaters**

In each of `aggressive_debator.py`, `conservative_debator.py`, `neutral_debator.py`, add the same import + lookup block and append `{failures_block}` to the prompt. The pattern is identical to the trader — look for where the prompt string is assembled and append the block at the end.

```python
from tradingagents.agents.utils.historical_context import (
    find_latest_prior_execution_failures,
    format_execution_failures_block,
)
from tradingagents.agents.utils.llm_guard import truncate_text
from tradingagents.default_config import DEFAULT_CONFIG

# inside the node function, before the prompt is assembled:
prior_failures = find_latest_prior_execution_failures(
    portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "default"),
    as_of_date=str(state.get("trade_date") or ""),
)
failures_block = (
    truncate_text(format_execution_failures_block(prior_failures, max_chars=600), max_chars=600)
    if prior_failures else ""
)
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/agents/risk_mgmt/test_risk_debater_execution_failures.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `pytest tests/ -v -m "not integration"`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/risk_mgmt/ tests/agents/risk_mgmt/test_risk_debater_execution_failures.py
git commit -m "feat(risk-debaters): inject prior execution failures into all three debater prompts"
```

**Stage 1.5 ships here.** After this stage, every node that makes a sizing or action decision sees why the last similar run's trades were rejected, without any human intervention.

---

# Stage 2 — Extend prior analysis context to Research Manager and PM

**Goal:** Research Manager and PM see prior analyst reports (market, fundamentals summary) for the same ticker in addition to the prior trader plan and PM decision from Stage 1. Bull/Bear researchers are intentionally excluded — they debate stock direction, not portfolio fit.

**Files:**
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Create one test per agent under the matching `tests/agents/...` path.

---

### Task 2.1: Inject prior analysis context into Research Manager

Research Manager now already gets execution failures (Stage 1.5). This task adds the prior `complete_report.json` summary so it can see what the previous analyst team concluded about the same ticker.

- [ ] **Step 1: Failing test** — assert that when a prior `complete_report.json` exists for the ticker, the Research Manager prompt contains "Prior Run Context".
- [ ] **Step 2: Add `find_latest_prior_analysis` call** in `research_manager.py` (same pattern as `trader.py`). Inject via `format_prior_context_block`.
- [ ] **Step 3: Run, confirm pass.**
- [ ] **Step 4: Commit:** `feat(research-manager): inject prior analyst report context into prompt`

---

### Task 2.2: Inject prior analysis context into Portfolio Manager

> **⚠️ Trading API note (Part 2 — Future Work):** The PM currently reads cash balance from the research packet prose, which is unreliable for hard budget enforcement. When a trading API is integrated (e.g. Alpaca, Interactive Brokers), replace the prose with a structured `## Portfolio Budget` section at the top of the PM prompt containing: exact available cash, max single-position budget (cash × max_position_pct), current sector exposures, and number of open positions vs. the configured maximum. This guarantees the PM anchors sizing decisions to live account data rather than stale report text. Until the API is wired, the execution failures from Stage 1.5 serve as the primary budget signal.

- [ ] **Step 1: Failing test** — assert that when a prior `pm_decision.json` exists, the PM prompt contains the prior decision text.
- [ ] **Step 2: Add `find_latest_prior_pm_decision` + `format_prior_context_block(ticker="PORTFOLIO", ...)` call** in `portfolio_manager.py`.
- [ ] **Step 3: Run, confirm pass.**
- [ ] **Step 4: Commit:** `feat(pm): inject prior PM decision into prompt for continuity`

---

### Task 2.3: Verify Stage 2 with end-to-end smoke test

- [ ] **Step 1: Run full non-integration suite**

Run: `pytest tests/ -v -m "not integration"`
Expected: all green.

- [ ] **Step 2: Run a real CLI analysis on a ticker that has at least one prior report**

Run: `python -m cli.main analyze` (interactively choose a ticker that has a prior report).
Expected: log line or report contains "Prior Run Context for X" in the agent prompts (verify via `reports/daily/.../run_events.jsonl` or by adding a single `logger.info("prior_context_block_chars=%d", len(prior_context_block))` while testing).

- [ ] **Step 3: Commit any logging tweaks** and tag end of stage:

```bash
git tag stage2-prior-context-wired
```

**Stage 2 ships here.**

---

# Stage 3 — Real P&L into reflexion

**Goal:** Replace the hardcoded `ta.reflect_and_remember(1000)` in `main.py` with realised P&L derived from the most recent `execution_result.json` and current price for executed positions. No fake numbers.

**Files:**
- Modify: `tradingagents/graph/trading_graph.py` (add a helper `compute_realised_pnl_for_run`)
- Create: `tests/graph/test_trading_graph_realised_pnl.py`
- Modify: `main.py`

---

### Task 3.1: Add realised-P&L helper

- [ ] **Step 1: Failing test** in `tests/graph/test_trading_graph_realised_pnl.py`:

```python
import json
from pathlib import Path

from tradingagents.graph.trading_graph import compute_realised_pnl_for_run


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_compute_realised_pnl_returns_float_when_execution_present(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily" / "2026-05-01" / "RUN1"
    _write(
        base / "portfolio" / "report" / "00_default_execution_result.json",
        {
            "trades": [
                {"ticker": "AAPL", "side": "BUY", "shares": 10, "fill_price": 180.0},
                {"ticker": "AAPL", "side": "SELL", "shares": 10, "fill_price": 190.0},
            ],
            "realised_pnl": 100.0,
        },
    )

    pnl = compute_realised_pnl_for_run(
        run_dir=base,
        portfolio_id="default",
    )

    assert pnl == 100.0


def test_compute_realised_pnl_returns_zero_when_missing(tmp_path: Path) -> None:
    pnl = compute_realised_pnl_for_run(
        run_dir=tmp_path / "missing",
        portfolio_id="default",
    )
    assert pnl == 0.0
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Implement** `compute_realised_pnl_for_run` in `tradingagents/graph/trading_graph.py`:

```python
def compute_realised_pnl_for_run(run_dir: Path, portfolio_id: str = "default") -> float:
    """Best-effort realised P&L for a single run.

    Reads ``{run_dir}/portfolio/report/*_{portfolio_id}_execution_result.json``
    and returns ``realised_pnl`` if present, else 0.0.
    """
    pdir = Path(run_dir) / "portfolio" / "report"
    if not pdir.exists():
        return 0.0
    matches = sorted(
        pdir.glob(f"*_{portfolio_id}_execution_result.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    if not matches:
        return 0.0
    try:
        data = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    return float(data.get("realised_pnl") or 0.0)
```

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit:** `feat(graph): add compute_realised_pnl_for_run helper`

---

### Task 3.2: Wire real P&L into `main.py`

- [ ] **Step 1: Modify `main.py`** to replace `ta.reflect_and_remember(1000)` with:

```python
from pathlib import Path
from tradingagents.graph.trading_graph import compute_realised_pnl_for_run
from tradingagents.report_paths import get_daily_dir

run_dir = get_daily_dir(trade_date, run_id=ta.run_id)
pnl = compute_realised_pnl_for_run(run_dir=Path(run_dir), portfolio_id="default")
ta.reflect_and_remember(pnl)
```

- [ ] **Step 2: Run a CLI analysis end-to-end** with a portfolio that has at least one trade. Verify reflexion logs show the real P&L number.

- [ ] **Step 3: Commit:** `fix(reflexion): use realised P&L instead of hardcoded 1000`

**Stage 3 ships here.**

---

# Stage 4 — `as_of_date` enforcement & lookback config

**Goal:** Guarantee no future-leakage in backtests by capping every memory + historical-context lookup at `as_of_date - 1 day`.

**Files:**
- Modify: `tradingagents/agents/utils/memory.py` — add optional `as_of_date` filter to `get_memories`.
- Modify: every agent that calls `memory.get_memories(...)` — pass `as_of_date=state["trade_date"]`.
- Modify: `tradingagents/agents/utils/historical_context.py` — already supports `as_of_date`; just verify all call sites pass it.

---

### Task 4.1: Add `as_of_date` parameter to `FinancialSituationMemory.get_memories`

- [ ] **Step 1:** Read `tradingagents/agents/utils/memory.py` to confirm the storage structure includes a writable timestamp on each record. If not, add `recorded_on: str` (ISO date) to record schema in a backwards-compatible way (default to the file's mtime when missing).
- [ ] **Step 2:** Failing test in `tests/agents/utils/test_memory_as_of_date.py` that adds two memories with different `recorded_on` dates and asserts `get_memories(situation, n_matches=5, as_of_date="2026-04-01")` excludes any record dated on or after `2026-04-01`.
- [ ] **Step 3:** Implement the filter — read records, drop any where `recorded_on >= as_of_date`, then run BM25 over the survivors only.
- [ ] **Step 4:** Run, confirm pass.
- [ ] **Step 5:** Commit: `feat(memory): support as_of_date filter on get_memories`

---

### Task 4.2: Pass `as_of_date` from every agent call site

- [ ] **Step 1:** Grep for `memory.get_memories(` across the repo:

Run: `grep -rn "memory.get_memories(" tradingagents/`

- [ ] **Step 2:** For each hit, add `as_of_date=state["trade_date"]` (or equivalent) as a kwarg.

- [ ] **Step 3:** Add a regression test that runs an analyst with a populated memory store containing one "future" record and asserts the agent's prompt does not contain the future record's text.

- [ ] **Step 4:** Run full suite, commit: `fix(agents): forward as_of_date into memory retrieval`

---

# Stage 5 — Persist PM decisions into reflexion store

**Goal:** After each run, write a tuple `(situation_text, pm_decision_text)` into the existing `portfolio_manager_memory` (BM25). This makes the existing `memory.get_memories(...)` retrieval automatically surface prior PM decisions for similar situations — no new prompt wiring needed beyond Stage 4.

**Files:**
- Modify: `tradingagents/graph/reflection.py` — add `record_pm_decision(state, pm_decision_text)` that calls `portfolio_manager_memory.add_situations([(situation, pm_decision_text)])`.
- Modify: `tradingagents/graph/trading_graph.py` — call `record_pm_decision` from `reflect_and_remember`.

---

### Task 5.1: Failing test for `record_pm_decision`

- [ ] **Step 1:** In `tests/graph/test_reflection_pm_record.py`, build a fake `FinancialSituationMemory` with a spy `add_situations`, call `record_pm_decision`, and assert one tuple was added containing the PM decision text.
- [ ] **Step 2:** Implement `record_pm_decision` in `tradingagents/graph/reflection.py`.
- [ ] **Step 3:** Run, confirm pass.
- [ ] **Step 4:** Commit: `feat(reflexion): persist PM decisions into BM25 memory`

---

### Task 5.2: Wire `record_pm_decision` into `reflect_and_remember`

- [ ] **Step 1:** Add a call to `record_pm_decision(curr_state, curr_state.get("final_trade_decision") or curr_state.get("trader_investment_plan") or "")` inside `TradingAgentsGraph.reflect_and_remember`.
- [ ] **Step 2:** Run a real CLI analysis, then a second one against the same ticker on a later date. Verify the PM's `Historical Lessons` section contains the prior decision verbatim.
- [ ] **Step 3:** Commit: `feat(reflexion): wire PM decision recording into post-run reflexion`

---

# Final Acceptance Criteria

After all five stages:

1. Trader, Research Manager, PM, and all three Risk debaters see prior execution failures (cash shortfalls, constraint violations) on every re-run.
2. Trader, Research Manager, and PM also see prior analyst reports and PM decisions for the same ticker.
3. Reflexion runs against real realised P&L, not `1000`.
4. No call to memory or historical-context loader can return data dated on or after the current `trade_date`.
5. PM decisions persist into the BM25 memory and surface automatically for similar future situations via the existing `Historical Lessons` retrieval.

Run: `pytest tests/ -v -m "not integration"` — all green.
Run: `python -m cli.main analyze` against a ticker that has at least one prior report — verify prompts contain prior-run and failure blocks, and that no future-dated content leaks.

---

# Notes & Out of Scope

- **Out of scope:** semantic embeddings to replace BM25, vector store migration, cross-ticker similarity. These are independently valuable but not required for "make past reports useful."
- **Out of scope:** changing the report directory layout. The plan reads what's already there.
- **Future work — Trading API budget section (Part 2):** When a live trading API is integrated (Alpaca, Interactive Brokers, etc.), add a structured `## Portfolio Budget` header to the PM prompt sourced directly from the API: exact available cash, per-position budget ceiling (cash × max_position_pct from config), current sector weights, and open position count vs. configured maximum. This replaces prose-based cash awareness with hard numbers the LLM must anchor to. Until then, Stage 1.5 execution failures serve as the primary budget feedback signal.
- **Coordination with existing plan:** This plan supersedes Tasks 3 and 5 of `docs/superpowers/plans/2026-04-30-memory-as-of-date-and-provenance.md`. After Stage 5 ships, mark those tasks done in the older plan and link to this one.
