# Trust-First Stream B — Safety & Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make portfolio-graph failures debuggable (decision snapshot + uncapped event payload), eliminate the cash-floor hard failure (deterministic rescale), restore run telemetry counters, and bring PM latency under two minutes.

**Architecture:** Four PRs targeting `tradingagents/graph/portfolio_setup.py`, `tradingagents/agents/portfolio/pm_decision_agent.py`, `agent_os/backend/services/event_mapper.py`, and `tradingagents/observability.py`. Three of them are independent (B1, B3, B4); B2 changes graph topology by inserting a `rescale_buys` node between `cash_sweep` and `pm_decision_postcheck`.

**Tech Stack:** Python 3.11+, LangGraph StateGraph, Pydantic structured output, pytest. Existing observability layer in `tradingagents/observability.py:170-226`.

**Spec:** `docs/superpowers/specs/2026-05-01-trading-agents-trust-first-fixes-design.md`

**Merge order within Stream B:** B1 → B3 → B2 → B4. Rationale: observability lands first so the next failure is debuggable; then B2 changes topology; B4 (latency / model swap) lands last so it operates on the final prompt shape.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `tradingagents/agents/portfolio/pm_decision_agent.py` | Modify | Write `portfolio_decision_snapshot.json` (B1); inject `max_total_buy_notional` into prompt + schema (B2); prompt diet + optional model swap (B4) |
| `agent_os/backend/services/event_mapper.py` | Modify | Whitelist `make_pm_decision` results from `_truncate()` (B1) |
| `tradingagents/graph/portfolio_setup.py` | Modify | Add `_make_rescale_buys_node()` and rewire workflow edges (B2) |
| `tradingagents/observability.py` | Investigate + Modify | Find why summary counters are zero; fix the source (B3) |
| `agent_os/backend/services/langgraph_engine.py` | Possibly Modify | Wire observability logger into LangGraph event stream (B3) |
| `tests/graph/test_portfolio_decision_snapshot.py` | Create | B1 acceptance |
| `tests/graph/test_rescale_buys.py` | Create | B2 acceptance |
| `tests/observability/test_run_log_summary.py` | Create | B3 acceptance |
| `tests/agents/test_pm_decision_latency.py` | Create | B4 acceptance |

---

## Phase B1: Decision snapshot + lift event truncation

### Task B1.1: PM agent writes `portfolio_decision_snapshot.json`

**Files:**
- Modify: `tradingagents/agents/portfolio/pm_decision_agent.py:213-365` (`pm_decision_node` body)
- Create: `tests/graph/test_portfolio_decision_snapshot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_portfolio_decision_snapshot.py
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_pm_decision_writes_snapshot_to_run_path(tmp_path, monkeypatch):
    """After pm_decision_node returns, snapshot exists with full decision JSON."""
    from tradingagents.agents.portfolio import pm_decision_agent as mod

    fake_decision_dict = {
        "macro_regime": "risk-on",
        "buys": [{"ticker": "ET", "shares": 100, "entry_price": 20.19}],
        "sells": [], "holds": [],
    }

    # Stub LLM with structured output returning a Pydantic-like model.
    fake_model = MagicMock()
    fake_model.model_dump_json.return_value = json.dumps(fake_decision_dict)
    fake_chain = MagicMock()
    fake_chain.invoke.return_value = fake_model

    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = MagicMock(
        __or__=lambda self, _: fake_chain
    )
    # Force chain composition: prompt | structured_llm → fake_chain
    monkeypatch.setattr(mod, "ChatPromptTemplate", MagicMock(
        from_messages=MagicMock(return_value=MagicMock(
            partial=MagicMock(return_value=MagicMock(__or__=lambda s, _: fake_chain))
        ))
    ))

    node = mod.create_pm_decision_agent(fake_llm, config={"run_path": str(tmp_path)})
    state = {
        "analysis_date": "2026-05-01",
        "portfolio_data": json.dumps({"portfolio": {"cash": 100000.0, "total_value": 100000.0},
                                       "holdings": []}),
        "macro_brief": "RISK-ON", "micro_brief": "ok",
        "prioritized_candidates": "[]",
    }

    result = node(state)

    snapshot_path = tmp_path / "portfolio_decision_snapshot.json"
    assert snapshot_path.exists(), f"snapshot not written; cwd has {list(tmp_path.iterdir())}"
    written = json.loads(snapshot_path.read_text())
    assert written == fake_decision_dict
    assert result["pm_decision"] == json.dumps(fake_decision_dict)
```

- [ ] **Step 2: Run; expect FAIL** (no snapshot file because no write code exists).

- [ ] **Step 3: Implement snapshot write**

In `pm_decision_agent.py`, edit `pm_decision_node` (lines 213–365). After `decision_str = result.model_dump_json()` and before the `synthetic_msg = AIMessage(...)` line, add:

```python
# Persist the decision JSON before any downstream node can fail. This is
# the canonical artifact for postmortem; do not gate on success of later
# nodes.
run_path = cfg.get("run_path")
if run_path:
    try:
        from pathlib import Path
        snapshot_path = Path(run_path) / "portfolio_decision_snapshot.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(decision_str)
    except Exception as exc:
        logger.warning(
            "pm_decision_agent: failed to persist snapshot at %s: %s",
            run_path, exc,
        )
```

- [ ] **Step 4: Run test; expect PASS.**

- [ ] **Step 5: Verify the path is wired from the engine**

```
grep -n "run_path" tradingagents/graph/portfolio_graph.py agent_os/backend/services/langgraph_engine.py
```
If `run_path` isn't being passed into the PM agent's config, add it where the agent is constructed in `portfolio_graph.py:76`. Concretely, ensure the `config` dict passed to `create_pm_decision_agent` contains `run_path` resolved from the run-scoped report store.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/portfolio/pm_decision_agent.py tradingagents/graph/portfolio_graph.py tests/graph/test_portfolio_decision_snapshot.py
git commit -m "feat(pm-decision): persist portfolio_decision_snapshot.json before postcheck (PR-B1)"
```

---

### Task B1.2: Lift truncation for PM decision result events

**Files:**
- Modify: `agent_os/backend/services/event_mapper.py:16` (constant) and `event_mapper.py:309` (where `_truncate` is called for results).

- [ ] **Step 1: Inspect call sites**

Run:
```
grep -n "_truncate\|_MAX_CONTENT_LEN" agent_os/backend/services/event_mapper.py
```
Confirm the call site that handles `make_pm_decision` results (line 309 area). The condition for whitelisting is "result event for the PM decision node" — which can be detected by checking the source node id or the event type during mapping.

- [ ] **Step 2: Write failing test**

```python
# tests/observability/test_event_mapper_truncation.py
import json
from agent_os.backend.services import event_mapper


def test_pm_decision_result_not_truncated():
    """A make_pm_decision result event must preserve full payload."""
    # Construct a fake LangGraph event with a long pm_decision JSON.
    long_payload = json.dumps({"buys": [{"ticker": "ET"}] * 50})
    assert len(long_payload) > 500
    # Emulate whatever shape event_mapper consumes; adapt to actual API.
    mapped = event_mapper.map_node_result(
        node_id="make_pm_decision",
        output_text=long_payload,
    )
    assert long_payload in mapped["message"], "PM decision payload was truncated"


def test_other_node_result_still_truncated():
    """Non-PM node results still respect _MAX_CONTENT_LEN to keep events small."""
    long_payload = "x" * 1000
    mapped = event_mapper.map_node_result(
        node_id="market_analyst",
        output_text=long_payload,
    )
    assert len(mapped["message"]) <= 350  # 300 + ellipsis
```

(If `event_mapper.map_node_result` does not exist as a public function, expose it during this task or adapt the test to call the actual mapper entrypoint. Keep the test asserting "PM full, others truncated".)

- [ ] **Step 3: Run; expect FAIL** (PM gets truncated today).

- [ ] **Step 4: Implement whitelist**

Add a small allowlist near the top of `event_mapper.py`:
```python
_FULL_PAYLOAD_NODES = frozenset({"make_pm_decision"})
```

At the truncation site (around line 309), wrap the call:
```python
if node_id in _FULL_PAYLOAD_NODES:
    output_text = _extract_content(output) if output is not None else ""
else:
    output_text = _truncate(_extract_content(output)) if output is not None else ""
```

- [ ] **Step 5: Run test; expect PASS.**

- [ ] **Step 6: Commit**

```bash
git add agent_os/backend/services/event_mapper.py tests/observability/test_event_mapper_truncation.py
git commit -m "feat(events): whitelist make_pm_decision results from 300-char truncation (PR-B1)"
```

**PR-B1 acceptance gate:** Replay the failed run; `portfolio_decision_snapshot.json` exists with full sells/buys/holds, and the event log entry for `make_pm_decision` contains the full JSON.

---

## Phase B3: run_log aggregator fix

### Task B3.1: Diagnose why counters are zero

**Files:**
- Read: `tradingagents/observability.py:170-237`
- Read: `agent_os/backend/services/langgraph_engine.py` (search for the run-finalization path that emits `kind: summary`)

- [ ] **Step 1: Reproduce zero-counter behavior**

```bash
# Find the failed run's summary line (already known empty)
tail -1 reports/daily/2026-05-01/01KQHDVJB2R19S4D7Z7Z6DP9F7/run_log.jsonl
```
Expected: `{"kind":"summary","elapsed_s":2642.5,"llm_calls":0,...}` — confirms zero counters.

- [ ] **Step 2: Locate the writer**

```
grep -rn "write_log\|kind.*summary\|TradingAgentsLogger" tradingagents/ agent_os/ | head -30
```
Determine whether the LangGraph engine event stream feeds `TradingAgentsLogger.events` or whether two separate logging tracks exist (the `run_events.jsonl` is populated; `run_log.jsonl` summary is empty → suggests events go to a different sink).

- [ ] **Step 3: Write failing unit test**

```python
# tests/observability/test_run_log_summary.py
from pathlib import Path
import json

from tradingagents.observability import TradingAgentsLogger


def test_summary_counts_llm_events():
    log = TradingAgentsLogger()
    log.record_llm("gpt-4", tokens_in=100, tokens_out=200)
    log.record_llm("gpt-4", tokens_in=50, tokens_out=75)
    summary = log.summary()
    assert summary["llm_calls"] == 2
    assert summary["tokens_in"] == 150
    assert summary["tokens_out"] == 275
    assert summary["tokens_total"] == 425


def test_write_log_summary_reflects_recorded_events(tmp_path):
    log = TradingAgentsLogger()
    log.record_llm("gpt-4", tokens_in=10, tokens_out=20)
    log.record_vendor("yfinance", method="ohlcv", success=True)
    out = tmp_path / "run_log.jsonl"
    log.write_log(out)
    lines = out.read_text().strip().splitlines()
    summary = json.loads(lines[-1])
    assert summary["kind"] == "summary"
    assert summary["llm_calls"] == 1
    assert summary["vendor_calls"] == 1
```

(Adapt method names if the actual API differs from `record_llm`/`record_vendor`.)

- [ ] **Step 4: Run; expect either PASS (proves logger works in isolation, problem is wiring) or FAIL (logger itself broken).**

- [ ] **Step 5: Identify and fix the wiring gap**

Two likely causes:
1. **Engine uses a different logger instance.** The LangGraph engine emits events via its own event stream that is mapped to `run_events.jsonl` but never feeds `TradingAgentsLogger`. Fix: subscribe `TradingAgentsLogger.record_*` to the engine's event callbacks at the appropriate point in `langgraph_engine.py`.
2. **Logger instance is created per-call but written from a different one.** Fix: ensure the run-scoped logger is the one passed to nodes and the one written at finalization.

Implementation depends on what Step 2 finds. The fix is at most a handful of lines wiring the engine's event callbacks (or LangChain callbacks) into `TradingAgentsLogger.record_*`. Add a passing integration test.

```python
# tests/observability/test_run_log_summary.py — append
def test_engine_run_writes_nonzero_counters(tmp_path, monkeypatch):
    """End-to-end: run a tiny graph; resulting run_log.jsonl summary has nonzero llm_calls."""
    # Use the existing portfolio smoke fixtures or a minimal stub graph.
    # Mock the LLM to return a fixed response and confirm the summary captures it.
    ...
```

(Sketch the integration test; concrete shape depends on existing test fixtures.)

- [ ] **Step 6: Run unit + integration tests**

```
pytest tests/observability/test_run_log_summary.py -v
```
Expected: all pass with nonzero counters.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/observability.py agent_os/backend/services/langgraph_engine.py tests/observability/test_run_log_summary.py
git commit -m "fix(observability): wire run telemetry counters from engine event stream (PR-B3)"
```

**PR-B3 acceptance gate:** After any portfolio run, `run_log.jsonl` summary shows `llm_calls > 0`, `tokens_total > 0`, `vendor_calls > 0`.

---

## Phase B2: Cash ceiling in prompt + `rescale_buys` node

### Task B2.1: Inject `max_total_buy_notional` into PM prompt and schema

**Files:**
- Modify: `tradingagents/agents/portfolio/pm_decision_agent.py:206-211` (constraints_str), `:240-246` (context block)

- [ ] **Step 1: Write failing test**

```python
# tests/agents/test_pm_decision_cash_ceiling.py
import json
from unittest.mock import MagicMock

from tradingagents.agents.portfolio.pm_decision_agent import _build_pm_context


def test_context_includes_resolved_cash_ceiling():
    state = {
        "portfolio_data": json.dumps({
            "portfolio": {"cash": 25000.0, "total_value": 100000.0},
            "holdings": [],
        }),
    }
    cfg = {"min_cash_pct": 0.10}
    ctx = _build_pm_context(state, cfg)
    # max_total_buy_notional = 25000 - 0.10 * 100000 = 15000
    assert "max_total_buy_notional" in ctx
    assert "15000" in ctx
```

- [ ] **Step 2: Run; expect FAIL** (`_build_pm_context` not yet exposed as a helper).

- [ ] **Step 3: Refactor + implement**

In `pm_decision_agent.py`, extract context construction into a helper `_build_pm_context(state, cfg) -> str`:

```python
def _build_pm_context(state: dict, cfg: dict) -> str:
    portfolio_data_str = state.get("portfolio_data") or "{}"
    try:
        pd_raw = json.loads(portfolio_data_str)
        portfolio = pd_raw.get("portfolio") or {}
        holdings = pd_raw.get("holdings") or []
        cash = float(portfolio.get("cash", 0.0))
        total_value = float(portfolio.get("total_value") or cash)
        n_positions = len(holdings)
    except Exception:
        cash, total_value, n_positions = 0.0, 0.0, 0

    min_cash_pct = float(cfg.get("min_cash_pct", 0.05))
    max_total_buy_notional = max(0.0, cash - min_cash_pct * total_value)

    constraints_str = (
        f"- Max position size: {cfg.get('max_position_pct', 0.15):.0%}\n"
        f"- Max sector exposure: {cfg.get('max_sector_pct', 0.35):.0%}\n"
        f"- Minimum cash reserve: {min_cash_pct:.0%}\n"
        f"- Max total positions: {cfg.get('max_positions', 15)}\n"
        f"- max_total_buy_notional: ${max_total_buy_notional:,.2f} "
        f"(HARD CEILING — sum of all BUY shares*entry_price MUST NOT EXCEED this)\n"
    )
    compressed_str = json.dumps({
        "cash": cash, "n_positions": n_positions, "total_value": total_value,
        "max_total_buy_notional": max_total_buy_notional,
    })
    macro_brief = state.get("macro_brief") or ""
    micro_brief = state.get("micro_brief") or "No micro brief available."
    candidate_deep_dive_context = _build_candidate_deep_dive_context(
        state.get("prioritized_candidates") or "[]"
    )
    return (
        f"## Portfolio Constraints\n{constraints_str}\n\n"
        f"## Portfolio Summary\n{compressed_str}\n\n"
        f"## Input A — Macro Context & Memory\n{macro_brief}\n\n"
        f"## Input B — Direct Candidate Final Trade Decision Summaries\n{candidate_deep_dive_context}\n\n"
        f"## Input C — Micro Context & Memory\n{micro_brief}\n"
    )
```

In `pm_decision_node`, replace the inline context-construction block with `context = _build_pm_context(state, cfg)`. Update the system_message to mention the hard ceiling explicitly (e.g., "Sum of all (shares × entry_price) for BUYs must not exceed max_total_buy_notional shown in Portfolio Constraints").

- [ ] **Step 4: Run test; expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/portfolio/pm_decision_agent.py tests/agents/test_pm_decision_cash_ceiling.py
git commit -m "feat(pm-decision): inject max_total_buy_notional into prompt (PR-B2)"
```

---

### Task B2.2: Add deterministic `rescale_buys` node

**Files:**
- Modify: `tradingagents/graph/portfolio_setup.py` (add factory near `_make_pm_decision_postcheck_node` at line 350; rewire workflow at line ~895)
- Create: `tests/graph/test_rescale_buys.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/graph/test_rescale_buys.py
import json
import math

import pytest


def _state(decision: dict, *, cash: float, total_value: float, min_cash_pct: float = 0.10):
    return {
        "pm_decision": json.dumps(decision),
        "portfolio_data": json.dumps({
            "portfolio": {"cash": cash, "total_value": total_value},
            "holdings": [],
        }),
    }


def test_noop_when_within_budget():
    from tradingagents.graph.portfolio_setup import GraphSetup
    node = GraphSetup._make_rescale_buys_node({"min_cash_pct": 0.10})
    decision = {"buys": [{"ticker": "ET", "shares": 100, "entry_price": 20.0}],
                "sells": [], "holds": []}
    state = _state(decision, cash=25_000.0, total_value=100_000.0)
    out = node(state)
    rewritten = json.loads(out["pm_decision"])
    assert rewritten["buys"][0]["shares"] == 100  # untouched


def test_proportional_scale_when_over_budget():
    """Buy notional 30K against budget 15K → scale to 50%."""
    from tradingagents.graph.portfolio_setup import GraphSetup
    node = GraphSetup._make_rescale_buys_node({"min_cash_pct": 0.10})
    decision = {"buys": [
        {"ticker": "A", "shares": 100, "entry_price": 100.0},  # 10K
        {"ticker": "B", "shares": 200, "entry_price": 100.0},  # 20K
    ], "sells": [], "holds": []}
    state = _state(decision, cash=25_000.0, total_value=100_000.0)  # ceiling 15K
    out = node(state)
    rewritten = json.loads(out["pm_decision"])
    # Expect each buy scaled by 15/30 = 0.5; floor.
    assert rewritten["buys"][0]["shares"] == 50
    assert rewritten["buys"][1]["shares"] == 100


def test_zero_budget_zeroes_buys():
    from tradingagents.graph.portfolio_setup import GraphSetup
    node = GraphSetup._make_rescale_buys_node({"min_cash_pct": 0.10})
    decision = {"buys": [{"ticker": "A", "shares": 100, "entry_price": 100.0}],
                "sells": [], "holds": []}
    # cash 5K, NAV 100K, ceiling = 5K - 10K = -5K → clamp 0
    state = _state(decision, cash=5_000.0, total_value=100_000.0)
    out = node(state)
    rewritten = json.loads(out["pm_decision"])
    assert rewritten["buys"][0]["shares"] == 0


def test_replay_failed_run_rescales_to_floor():
    """Reproduce 01KQHDVJB2R19S4D7Z7Z6DP9F7: cash $2,687 needs to become >= $9,992."""
    from tradingagents.graph.portfolio_setup import GraphSetup
    node = GraphSetup._make_rescale_buys_node({"min_cash_pct": 0.10})
    # Synthesize: total NAV 99,923; cash before rescale 2,687.88 → buy notional 7,304.44.
    # Floor 9,992.32; excess = 9,992.32 - 2,687.88 = 7,304.44; scale 0.0 → all buys 0.
    decision = {"buys": [{"ticker": "X", "shares": 1, "entry_price": 7304.44}],
                "sells": [], "holds": []}
    state = _state(decision, cash=10_000.0, total_value=99_923.20)
    # cash 10K, ceiling 9992.32 → budget 7.68; basket 7304.44 → ~zero shares
    out = node(state)
    rewritten = json.loads(out["pm_decision"])
    assert rewritten["buys"][0]["shares"] == 0
```

- [ ] **Step 2: Run; expect FAIL** (`_make_rescale_buys_node` not defined).

- [ ] **Step 3: Implement node**

In `tradingagents/graph/portfolio_setup.py`, near `_make_pm_decision_postcheck_node` at line 350, add:

```python
@staticmethod
def _make_rescale_buys_node(config: dict[str, Any]):
    """Deterministically scale BUY shares down so the cash floor holds.

    Mirrors the projection math in pm_decision_postcheck (lines 480-491) but
    rescales rather than rejects. If the basket already fits, this is a no-op.
    """
    import json
    import math

    min_cash_pct = float(config.get("min_cash_pct", 0.05))

    def rescale_buys_node(state: PortfolioManagerState) -> dict[str, Any]:
        decision_str = state.get("pm_decision") or "{}"
        try:
            decision = json.loads(decision_str)
        except json.JSONDecodeError:
            return {"sender": "rescale_buys"}

        portfolio_data = json.loads(state.get("portfolio_data") or "{}")
        portfolio = portfolio_data.get("portfolio") or {}
        cash = float(portfolio.get("cash", 0.0))
        total_value = float(portfolio.get("total_value") or cash)

        buys = decision.get("buys") or []
        if not buys:
            return {"sender": "rescale_buys"}

        # Apply sells first (they raise projected cash).
        projected_cash = cash
        for sell in decision.get("sells") or []:
            shares = abs(int(sell.get("shares", 0)))
            price = float(sell.get("entry_price") or sell.get("limit_price") or 0.0)
            projected_cash += shares * price

        total_buy_notional = sum(
            int(b.get("shares", 0)) * float(b.get("entry_price", 0.0)) for b in buys
        )
        if total_buy_notional <= 0:
            return {"sender": "rescale_buys"}

        # Project equity post-trade for the floor calculation. Reuse cash as the
        # NAV proxy for the post-trade total value: postcheck uses
        # projected_cash + projected_equity; we approximate with current total_value.
        projected_total_value = total_value
        min_required_cash = projected_total_value * min_cash_pct
        budget = projected_cash - min_required_cash

        if budget >= total_buy_notional:
            return {"sender": "rescale_buys"}  # already fits

        scale = max(0.0, budget / total_buy_notional)
        original = [{"ticker": b.get("ticker"), "shares": b.get("shares")} for b in buys]
        for b in buys:
            b["shares"] = int(math.floor(int(b.get("shares", 0)) * scale))

        decision["buys"] = buys
        return {
            "pm_decision": json.dumps(decision),
            "rescale_audit": {
                "scale": scale, "original": original,
                "rescaled": [{"ticker": b.get("ticker"), "shares": b.get("shares")} for b in buys],
                "min_required_cash": min_required_cash,
                "projected_cash_before": projected_cash,
                "total_buy_notional_before": total_buy_notional,
            },
            "sender": "rescale_buys",
        }

    return rescale_buys_node
```

Wire into the workflow. In `setup_portfolio_graph` (around line 871–895), add:
```python
workflow.add_node("rescale_buys", self._make_rescale_buys_node(self.config))
```
Replace the existing edge `cash_sweep → pm_decision_postcheck` with:
```python
workflow.add_edge("cash_sweep", "rescale_buys")
workflow.add_edge("rescale_buys", "pm_decision_postcheck")
```

- [ ] **Step 4: Run unit tests**

```
pytest tests/graph/test_rescale_buys.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/portfolio_setup.py tests/graph/test_rescale_buys.py
git commit -m "feat(portfolio): add deterministic rescale_buys node before postcheck (PR-B2)"
```

---

### Task B2.3: Replay-test the failed run end-to-end

**Files:**
- Create: `tests/integration/test_replay_failed_run.py` (mark `@pytest.mark.integration` so default test runs skip it)

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_replay_failed_run.py
import json

import pytest


@pytest.mark.integration
def test_failed_run_rescales_and_passes_postcheck():
    """Replay 01KQHDVJB2R19S4D7Z7Z6DP9F7: with rescale_buys, postcheck passes."""
    # Load the original PM decision snapshot (after PR-B1 lands this is on disk).
    # If snapshot file unavailable for the failed run, reconstruct from the
    # event log's make_pm_decision result.
    # Run rescale_buys node, then pm_decision_postcheck; assert no raise.
    ...
```

(Sketch — implementation depends on whether PR-B1 retroactively gives us the snapshot or whether we synthesize the basket from current data.)

- [ ] **Step 2: Run with `-m integration`; expect PASS once implementation is filled in.**

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_replay_failed_run.py
git commit -m "test(integration): replay failed run through rescale_buys (PR-B2)"
```

**PR-B2 acceptance gate:** Replay the failed run; `rescale_buys` reduces shares so `projected_cash >= 0.10 × NAV`; `pm_decision_postcheck` passes; `execute_trades` sees a smaller basket. Audit event records `original` vs `rescaled`.

---

## Phase B4: PM latency

### Task B4.1: Prompt diet (low-risk first)

**Files:**
- Modify: `tradingagents/agents/portfolio/pm_decision_agent.py:248-292` (system_message)

- [ ] **Step 1: Write latency test**

```python
# tests/agents/test_pm_decision_latency.py
import time
import pytest


@pytest.mark.integration
def test_pm_decision_latency_under_120s(portfolio_smoke_state):
    """End-to-end PM call must complete in under 120s after prompt diet."""
    from tradingagents.agents.portfolio.pm_decision_agent import create_pm_decision_agent
    from tradingagents.default_config import DEFAULT_CONFIG  # adapt as needed

    llm = ...  # use the same LLM the daily run uses
    node = create_pm_decision_agent(llm, config=DEFAULT_CONFIG)
    t0 = time.time()
    node(portfolio_smoke_state)
    elapsed = time.time() - t0
    assert elapsed < 120, f"PM took {elapsed:.1f}s; target <120s"
```

- [ ] **Step 2: Run baseline; expect FAIL** at ~520s.

- [ ] **Step 3: Trim the prompt**

Replace lines 248–292 of `pm_decision_agent.py` with a tighter version. Strip narrative instructions; keep only the rules the schema cannot enforce. Move long input briefs into a `# INPUTS` JSON-ish block. Concretely:

```python
system_message = (
    "You are a portfolio manager. Synthesize the inputs below into a JSON-only "
    "decision matching the structured schema. Every BUY must satisfy: "
    "entry_price > 0; entry_price <= max_chase_price <= limit_price; "
    "stop_loss is 5-15% below entry; take_profit is 10-30% above entry; "
    "valid_as_of is the analysis date in YYYY-MM-DD. "
    "Sum of (shares*entry_price) across BUYs MUST NOT EXCEED "
    "max_total_buy_notional shown in Portfolio Constraints. "
    "Do not buy a ticker absent from Input B (candidate summaries). "
    "Output JSON only.\n\n"
    f"{context}"
)
```

The reduction comes from removing the prose explanation of each field (the schema already enforces them) and from compressing the "STRICT OUTPUT REQUIREMENTS" list (Pydantic schema enforces it).

- [ ] **Step 4: Re-run latency test**

```
pytest tests/agents/test_pm_decision_latency.py -v -m integration
```
Expected target: < 120s. If still > 120s, proceed to Task B4.2.

- [ ] **Step 5: Decision-quality regression check**

Run the daily portfolio smoke against a known-good reference run (e.g., the most recent successful run on the branch). Compare PM decisions:
- Same direction (BUY/HOLD/SELL) for every ticker.
- Share counts within ±10% of the reference.

If decision quality drops, revert and skip to Task B4.2 instead.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/portfolio/pm_decision_agent.py tests/agents/test_pm_decision_latency.py
git commit -m "perf(pm-decision): prompt diet — JSON-only response, schema-enforced fields (PR-B4)"
```

---

### Task B4.2: Optional model swap (if Task B4.1 didn't reach target)

**Files:**
- Modify: PM model config (locate via `grep -rn "deep_thinking_llm\|pm_decision.*llm\|kimi-k2" tradingagents/`)

- [ ] **Step 1: Per-node model override**

In the place where `create_pm_decision_agent(self.deep_thinking_llm, ...)` is constructed (likely `portfolio_graph.py:76`), swap to a Sonnet 4.6 LLM instance for the PM node only. Other graph nodes continue using their existing LLMs.

```python
# Construct a dedicated PM LLM
from langchain_anthropic import ChatAnthropic  # adapt to project's import path
pm_llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.0, max_tokens=4096)

self.agents = {
    ...
    "pm_decision": create_pm_decision_agent(pm_llm, config=self.config, ...),
    ...
}
```

- [ ] **Step 2: Re-run latency + quality regression**

Same harness as Task B4.1 Step 4–5. Target: < 60s with the same direction-and-±10%-sizing quality bar.

- [ ] **Step 3: Commit**

```bash
git add tradingagents/graph/portfolio_graph.py
git commit -m "perf(pm-decision): swap PM node to claude-sonnet-4-6 (PR-B4)"
```

**PR-B4 acceptance gate:** PM latency for the same inputs is under 120s after prompt diet (target 60s after model swap). Decision direction matches a reference run for every ticker; share counts within ±10%.

---

## Stream B self-review checklist

- [ ] Each of the four PRs (B1, B2, B3, B4) has at least one task that produces a runnable test.
- [ ] No "TBD"/"TODO" left in task bodies (the integration-test sketches in B2.3 and B3.1 step 5 are explicitly noted as sketches that depend on prior tasks; that's acceptable as long as the dependencies are spelled out).
- [ ] Helper names are consistent: `_make_rescale_buys_node`, `_build_pm_context`, `_FULL_PAYLOAD_NODES`.
- [ ] Each phase ends with an acceptance gate referencing the actual run id `01KQHDVJB2R19S4D7Z7Z6DP9F7`.
- [ ] Merge order within Stream B (B1 → B3 → B2 → B4) is preserved; B4's prompt-diet task assumes the cash-ceiling injection from B2 is already merged so the trimmed prompt still references `max_total_buy_notional`.
