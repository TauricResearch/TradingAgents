# Feature 9: State Field + Propagation

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Add `scanner_graph_context_text: str` to `AgentState` and wire it through `Propagator.create_initial_state()`.

**Dependencies:** None. This is a standalone state plumbing change.

**Files to modify:**
- `tradingagents/agents/utils/agent_states.py`
- `tradingagents/graph/propagation.py`

**Files to create:**
- `tests/graph/test_propagation_scanner_context.py`

---

## Rules

- Add exactly **one** new field: `scanner_graph_context_text: Annotated[str, "..."]`
- Do **not** add `scanner_graph_facts_path` or `scanner_graph_context` dict — these are explicitly excluded per the plan.
- `scanner_context_packet` stays as-is — it is used by operator resume paths.
- `create_initial_state()` gains `scanner_graph_context_text: str = ""` as a keyword argument.
- All existing tests must pass unchanged.

---

## Step 1: Write failing tests

- [ ] Create `tests/graph/test_propagation_scanner_context.py`:

```python
"""Tests for scanner_graph_context_text field in AgentState and Propagator."""
import pytest
from tradingagents.graph.propagation import Propagator


def _make_propagator():
    return Propagator(max_recur_limit=100)


def test_create_initial_state_default_scanner_context():
    """scanner_graph_context_text defaults to empty string."""
    p = _make_propagator()
    state = p.create_initial_state(
        company_name="AAPL",
        trade_date="2026-04-16",
        run_id="TESTRUN",
    )
    assert "scanner_graph_context_text" in state
    assert state["scanner_graph_context_text"] == ""


def test_create_initial_state_with_scanner_context():
    """scanner_graph_context_text is stored when provided."""
    p = _make_propagator()
    ctx = "## Global Market Regime\n- Risk-On\n\n## Ticker Graph Context: ON\n- ON belongs to Technology."
    state = p.create_initial_state(
        company_name="ON",
        trade_date="2026-04-16",
        run_id="TESTRUN",
        scanner_graph_context_text=ctx,
    )
    assert state["scanner_graph_context_text"] == ctx


def test_agent_state_has_scanner_context_field():
    """AgentState TypedDict must include scanner_graph_context_text."""
    from tradingagents.agents.utils.agent_states import AgentState
    # AgentState is a TypedDict — check field is in __annotations__
    annotations = {}
    for cls in type.__mro__(AgentState):
        annotations.update(getattr(cls, "__annotations__", {}))
    assert "scanner_graph_context_text" in annotations


def test_scanner_context_packet_still_present():
    """scanner_context_packet must remain (used by operator resume paths)."""
    from tradingagents.agents.utils.agent_states import AgentState
    annotations = {}
    for cls in type.__mro__(AgentState):
        annotations.update(getattr(cls, "__annotations__", {}))
    assert "scanner_context_packet" in annotations


def test_create_initial_state_scanner_context_does_not_overwrite_other_fields():
    """Adding scanner_graph_context_text must not displace any existing field."""
    p = _make_propagator()
    state = p.create_initial_state(
        company_name="NVDA",
        trade_date="2026-04-16",
        run_id="RUN1",
        scanner_graph_context_text="some context",
    )
    # Essential existing fields must still be present
    assert "run_id" in state
    assert "company_of_interest" in state
    assert "scanner_context_packet" in state
    assert state["run_id"] == "RUN1"
    assert state["company_of_interest"] == "NVDA"
```

## Step 2: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/test_propagation_scanner_context.py -v 2>&1 | head -15
```

Expected: `AssertionError` on `test_agent_state_has_scanner_context_field` and `test_create_initial_state_default_scanner_context` — the field doesn't exist yet.

## Step 3: Add field to AgentState

- [ ] Edit `tradingagents/agents/utils/agent_states.py` — add the field after `scanner_context_packet`:

Current lines (around line 66–67):
```python
    scanner_context_packet: Annotated[str, "Consolidated context from the scanner phase"]

    sender: Annotated[str, "Agent that sent this message"]
```

Replace with:
```python
    scanner_context_packet: Annotated[str, "Consolidated context from the scanner phase"]
    scanner_graph_context_text: Annotated[str, "Prompt-ready ticker graph context rendered from scanner graph facts"]

    sender: Annotated[str, "Agent that sent this message"]
```

## Step 4: Add parameter to `create_initial_state`

- [ ] Edit `tradingagents/graph/propagation.py`:

Current signature (around line 18–28):
```python
    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        run_id: str,
        portfolio_context: str = "candidate",
        scanner_context_packet: str = "",
        market_report: str = "",
        market_report_structured: Optional[Dict[str, Any]] = None,
        macro_regime_report: str = "",
    ) -> Dict[str, Any]:
```

Replace with:
```python
    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        run_id: str,
        portfolio_context: str = "candidate",
        scanner_context_packet: str = "",
        scanner_graph_context_text: str = "",
        market_report: str = "",
        market_report_structured: Optional[Dict[str, Any]] = None,
        macro_regime_report: str = "",
    ) -> Dict[str, Any]:
```

- [ ] Add the field to the return dict — after `"scanner_context_packet": scanner_context_packet,`:

Current lines (around line 37–38):
```python
            "scanner_context_packet": scanner_context_packet,
            "instrument_key": instrument.instrument_key,
```

Replace with:
```python
            "scanner_context_packet": scanner_context_packet,
            "scanner_graph_context_text": scanner_graph_context_text,
            "instrument_key": instrument.instrument_key,
```

## Step 5: Run tests — all must pass

```bash
pytest tests/graph/test_propagation_scanner_context.py -v
```

Expected: all 5 PASS.

## Step 6: Run full suite

```bash
pytest tests/ -v -m "not integration" -x
```

All pre-existing tests must still pass — the new parameter has a default of `""` so all existing callers are unaffected.

## Step 7: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claire/worktrees/silly-meitner-37bb65
git add \
  tradingagents/agents/utils/agent_states.py \
  tradingagents/graph/propagation.py \
  tests/graph/test_propagation_scanner_context.py
git commit -m "feat(scanner-facts): add scanner_graph_context_text to AgentState and Propagator"
```

---

## Done When

- `pytest tests/graph/test_propagation_scanner_context.py -v` → all 5 green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- `AgentState` has `scanner_graph_context_text` field
- `create_initial_state()` accepts and stores `scanner_graph_context_text`
- `scanner_context_packet` still present and unchanged
