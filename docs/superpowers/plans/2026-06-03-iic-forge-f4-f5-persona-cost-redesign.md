# IIC-FORGE F4/F5 Persona-Cost Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the default approved-analysis architecture, tighten the F4/F5 approval and delivery gate, add reusable analysis packs for follow-up runs, recover the unmerged F2 backtest work safely, and reduce token waste.

**Architecture:** The default approved event runs one enriched TradingAgents graph with all native TradingAgents roles active, using a balanced IIC persona injected inside the graph. Multi-persona committee runs become an explicit follow-up mode, and follow-ups reuse a persisted analysis pack instead of rerunning shared discovery from zero. F4 adds a strict structured alert evaluator before light-alert delivery, and F5 verifies approval-to-study lineage, delivery audit rows, full-brief completion, and follow-up actions.

**Tech Stack:** Python 3, SQLite, LangGraph, Pydantic, YAML, pytest, existing IIC-FORGE persistence/store helpers, existing TradingAgents graph/agent factories.

---

## Non-Negotiables

- Do not read, modify, commit, or print `.env`.
- Do not push to or open PRs against the original upstream TradingAgents project.
- Do not merge `origin/feat/iic-forge-05-f2` directly. It predates current F3/F4/F5 work and would delete newer files. Restore selected files or reimplement selected commits only.
- Create a fresh branch or worktree at execution time before touching code.
- Keep every schema change append-only: new tables or `ALTER TABLE ADD COLUMN` only.
- Keep the legacy outer persona fan-out callable for explicit committee mode, but remove it from default event-alert and morning-digest production paths.

## File Structure

### Persona Injection

- Create `tradingagents/personas/prompt_overlay.py`: append an active IIC persona fragment to native TradingAgents role prompts.
- Create `tradingagents/personas/risk_weights.py`: render persona-weighted aggressive/conservative/neutral risk debate for the portfolio manager.
- Create `tradingagents/personas/balanced.yaml`: default balanced IIC profile for one full TradingAgents graph.
- Modify `tradingagents/default_config.py`: add `default_analysis_persona_id`, `committee_persona_ids`, and `committee_mode_enabled`.
- Modify `tradingagents/graph/trading_graph.py`: load the configured persona once and pass it into `GraphSetup`.
- Modify `tradingagents/graph/setup.py`: accept `persona` and pass it to every agent factory.
- Modify all native role factories to accept `persona=None` and call `apply_fragment` on system prompts:
  - `tradingagents/agents/analysts/market_analyst.py`
  - `tradingagents/agents/analysts/sentiment_analyst.py`
  - `tradingagents/agents/analysts/news_analyst.py`
  - `tradingagents/agents/analysts/fundamentals_analyst.py`
  - `tradingagents/agents/analysts/derivative_analyst.py`
  - `tradingagents/agents/researchers/bull_researcher.py`
  - `tradingagents/agents/researchers/bear_researcher.py`
  - `tradingagents/agents/managers/research_manager.py`
  - `tradingagents/agents/trader/trader.py`
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py`
  - `tradingagents/agents/risk_mgmt/conservative_debator.py`
  - `tradingagents/agents/risk_mgmt/neutral_debator.py`
  - `tradingagents/agents/managers/portfolio_manager.py`

### Default Runner and Follow-Ups

- Create `tradingagents/secretary/analysis_runner.py`: one default balanced graph runner plus explicit committee/follow-up runners.
- Modify `tradingagents/secretary/persona_runner.py`: keep as compatibility wrapper for explicit committee mode only.
- Modify `tradingagents/secretary/service.py`: `compose_event_alert`, `compose_morning_digest`, and `compose_refinement` call the new runner.
- Modify `tradingagents/secretary/morning.py`: one balanced run per ticker by default; committee only when config enables it.
- Modify `cli/deepdive.py`: default one balanced run; add explicit committee option.
- Modify `tradingagents/secretary/synthesis.py`: stop assuming exactly three persona teams.

### Alert Strictness and Approval Lineage

- Create `tradingagents/orchestrator/alert_evaluator.py`: structured pass/reject evaluator for F4 light alerts.
- Modify `tradingagents/orchestrator/promoter.py`: evaluate candidate groups before composing light alerts.
- Modify `tradingagents/persistence/schema.sql`: add `alert_evaluations`; add `brief_actions.result_job_id`, `brief_actions.dispatched_ts`, `brief_actions.error`.
- Modify `tradingagents/persistence/store.py`: add alert-evaluation helpers and action-dispatch helpers.
- Modify `tradingagents/orchestrator/action_handler.py`: record the queued job id instead of using parent light brief as a sentinel.
- Modify `tradingagents/orchestrator/dispatch.py`: link full briefs by action/job lineage, not only latest light brief for an event.
- Modify `tradingagents/delivery/base.py`: apply quiet hours to both `event_alert` and `event_alert_light`.

### Analysis Packs and Cache Hygiene

- Create `tradingagents/analysis_pack/__init__.py`
- Create `tradingagents/analysis_pack/model.py`
- Create `tradingagents/analysis_pack/store.py`
- Create `tradingagents/analysis_pack/builder.py`
- Create `tradingagents/analysis_pack/prompting.py`
- Modify `tradingagents/persistence/schema.sql`: add `analysis_packs`, `briefs.analysis_pack_id`, `runs.analysis_pack_id`.
- Modify `tradingagents/dataflows/y_finance.py`: remove prompt-visible dynamic retrieval timestamps.
- Add optional dataflow memoization only after tests exist for deterministic cache keys.

### Backtest Recovery and Exit Gates

- Restore selected files from `origin/feat/iic-forge-05-f2`:
  - `tradingagents/backtest/**`
  - `tests/backtest/**`
- Modify `scripts/f4_exit_gate.py` or replace with `scripts/f4_f5_exit_gate.py`: combined F4/F5 gate.
- Modify `scripts/f5_exit_gate.py`: count `event_alert_light` and full `event_alert` lineage correctly.
- Modify smoke tests so synthetic approval covers light alert -> approval -> queued job -> worker/full brief -> delivery/actions.

---

## Task 1: Branch, Safety, and Baseline Audit

**Files:**
- Read only: git metadata and repository tree

- [ ] **Step 1: Create an isolated branch or worktree**

Run one of these at execution time:

```bash
git checkout -b feat/f4-f5-persona-cost-redesign
```

Expected: branch switches successfully from current fork `main`.

- [ ] **Step 2: Confirm no accidental upstream work**

Run:

```bash
git remote -v
```

Expected: the worker identifies the fork remote before any push. Do not push to the original TradingAgents upstream.

- [ ] **Step 3: Confirm `.env` stays untouched**

Run:

```bash
git status --short -- .env
```

Expected: no output.

- [ ] **Step 4: Confirm F2 branch is not merged directly**

Run:

```bash
git branch -a --no-merged main
```

Expected: `origin/feat/iic-forge-05-f2` may appear. Treat it as a source for selective file restore only.

---

## Task 2: Add Persona Overlay Helpers and Balanced Persona

**Files:**
- Create: `tradingagents/personas/prompt_overlay.py`
- Create: `tradingagents/personas/risk_weights.py`
- Create: `tradingagents/personas/balanced.yaml`
- Modify: `tradingagents/default_config.py`
- Test: `tests/personas/test_prompt_overlay_and_risk_weights.py`

- [ ] **Step 1: Write failing tests**

Create `tests/personas/test_prompt_overlay_and_risk_weights.py`:

```python
from tradingagents.personas.loader import load_persona_from_string
from tradingagents.personas.prompt_overlay import apply_fragment
from tradingagents.personas.risk_weights import format_weighted_risk_debate


BALANCED_YAML = """
id: balanced
name: Balanced IIC
description: Balanced default profile for approved full studies.
system_prompt_fragment: |
  IIC persona overlay: weigh evidence across growth, valuation, macro,
  momentum, and risk. Preserve material disagreement instead of forcing
  false consensus.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
analysts:
  include: [market, news, fundamentals, derivatives, social]
  exclude: []
risk_debate:
  weights:
    aggressive: 1.0
    conservative: 1.0
    neutral: 1.0
memory_scope: hybrid
"""


def test_apply_fragment_appends_persona_fragment():
    persona = load_persona_from_string(BALANCED_YAML)
    prompt = apply_fragment("Base role prompt.", persona)
    assert prompt.startswith("Base role prompt.")
    assert "IIC persona overlay" in prompt


def test_apply_fragment_passthrough_without_persona():
    assert apply_fragment("Base role prompt.", None) == "Base role prompt."


def test_format_weighted_risk_debate_labels_all_sides():
    persona = load_persona_from_string(BALANCED_YAML)
    rendered = format_weighted_risk_debate(
        {
            "aggressive_history": "Aggressive case",
            "conservative_history": "Conservative case",
            "neutral_history": "Neutral case",
        },
        persona,
    )
    assert "Aggressive (weight 1.00)" in rendered
    assert "Conservative (weight 1.00)" in rendered
    assert "Neutral (weight 1.00)" in rendered
    assert "Aggressive case" in rendered
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```bash
pytest tests/personas/test_prompt_overlay_and_risk_weights.py -q
```

Expected: FAIL with import errors for `prompt_overlay` and `risk_weights`.

- [ ] **Step 3: Create `prompt_overlay.py`**

Use this implementation:

```python
"""Persona system-prompt overlay helper."""

from __future__ import annotations

from typing import Optional

from tradingagents.personas.loader import Persona


def apply_fragment(base_prompt: str, persona: Optional[Persona]) -> str:
    """Append the active persona fragment to a native TradingAgents prompt."""
    if persona is None:
        return base_prompt
    fragment = (persona.system_prompt_fragment or "").strip()
    if not fragment:
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{fragment}".rstrip()
```

- [ ] **Step 4: Create `risk_weights.py`**

Use this implementation:

```python
"""Persona-weighted risk-debate formatter."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from tradingagents.personas.loader import Persona


def _section(label: str, body: str, weight: Optional[float]) -> str:
    body = (body or "").strip() or "(no entries)"
    if weight is None:
        return f"### {label}\n{body}"
    return f"### {label} (weight {weight:.2f})\n{body}"


def format_weighted_risk_debate(
    state: Mapping[str, Any],
    persona: Optional[Persona],
) -> str:
    weights = persona.risk_debate.weights if persona is not None else {}
    return (
        _section("Aggressive", state.get("aggressive_history", ""), weights.get("aggressive"))
        + "\n\n"
        + _section("Conservative", state.get("conservative_history", ""), weights.get("conservative"))
        + "\n\n"
        + _section("Neutral", state.get("neutral_history", ""), weights.get("neutral"))
    )
```

- [ ] **Step 5: Create `balanced.yaml`**

Use this YAML:

```yaml
id: balanced
name: Balanced IIC
description: Balanced default profile for approved full studies.
system_prompt_fragment: |
  IIC persona overlay: weigh evidence across growth, valuation, macro,
  momentum, sentiment, derivatives, and risk. Preserve material disagreement
  between internal TradingAgents roles instead of forcing false consensus.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [market, news, fundamentals, derivatives, social]
  exclude: []
risk_debate:
  weights:
    aggressive: 1.0
    conservative: 1.0
    neutral: 1.0
memory_scope: hybrid
```

- [ ] **Step 6: Add default config keys**

In `tradingagents/default_config.py`, add these keys near the existing LLM/persona-adjacent config:

```python
    "default_analysis_persona_id": "balanced",
    "committee_persona_ids": ["value", "momentum", "macro"],
    "committee_mode_enabled": False,
```

- [ ] **Step 7: Run tests**

Run:

```bash
pytest tests/personas/test_prompt_overlay_and_risk_weights.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/personas/prompt_overlay.py tradingagents/personas/risk_weights.py tradingagents/personas/balanced.yaml tradingagents/default_config.py tests/personas/test_prompt_overlay_and_risk_weights.py
git commit -m "feat(personas): add balanced graph persona overlay helpers"
```

---

## Task 3: Inject IIC Persona Inside the Native TradingAgents Graph

**Files:**
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: all agent factory files listed in File Structure
- Test: `tests/personas/test_graph_persona_injection.py`

- [ ] **Step 1: Write failing graph-load test**

Create `tests/personas/test_graph_persona_injection.py`:

```python
from tradingagents.graph.trading_graph import _load_persona_from_config


def test_load_persona_from_config_loads_balanced_profile():
    persona = _load_persona_from_config({"persona_id": "balanced"})
    assert persona is not None
    assert persona.id == "balanced"
    assert "Preserve material disagreement" in persona.system_prompt_fragment


def test_load_persona_from_config_returns_none_for_missing_profile():
    assert _load_persona_from_config({"persona_id": "does-not-exist"}) is None
```

- [ ] **Step 2: Run the graph-load test to verify failure**

Run:

```bash
pytest tests/personas/test_graph_persona_injection.py -q
```

Expected: FAIL because `_load_persona_from_config` is missing on current `main`.

- [ ] **Step 3: Add persona loading to `trading_graph.py`**

Add imports:

```python
from tradingagents.personas.loader import Persona, load_persona_from_file
```

Add helper near imports:

```python
def _load_persona_from_config(config: Dict[str, Any]) -> Optional[Persona]:
    pid = config.get("persona_id")
    if not pid:
        return None
    yaml_path = Path(__file__).resolve().parent.parent / "personas" / f"{pid}.yaml"
    if not yaml_path.exists():
        return None
    return load_persona_from_file(str(yaml_path))
```

Inside `TradingAgentsGraph.__init__`, after `self.config = config or DEFAULT_CONFIG`, add:

```python
        self.persona = _load_persona_from_config(self.config)
```

When constructing `GraphSetup`, pass:

```python
            persona=self.persona,
```

- [ ] **Step 4: Update `GraphSetup` constructor**

In `tradingagents/graph/setup.py`, add imports:

```python
from typing import Optional
from tradingagents.personas.loader import Persona
```

Change `GraphSetup.__init__` signature to include:

```python
        persona: Optional[Persona] = None,
```

Store it:

```python
        self.persona = persona
```

Pass `persona=self.persona` to each factory call:

```python
            "market": lambda: create_market_analyst(self.quick_thinking_llm, persona=self.persona),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm, persona=self.persona),
            "news": lambda: create_news_analyst(self.quick_thinking_llm, persona=self.persona),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm, persona=self.persona),
            "derivatives": lambda: create_derivative_analyst(self.quick_thinking_llm, persona=self.persona),
```

And:

```python
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm, persona=self.persona)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm, persona=self.persona)
        research_manager_node = create_research_manager(self.deep_thinking_llm, persona=self.persona)
        trader_node = create_trader(self.quick_thinking_llm, persona=self.persona)
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm, persona=self.persona)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm, persona=self.persona)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm, persona=self.persona)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm, persona=self.persona)
```

- [ ] **Step 5: Update every agent factory signature and prompt**

For each listed agent factory, change:

```python
def create_<role>(llm):
```

to:

```python
def create_<role>(llm, persona=None):
```

Add:

```python
from tradingagents.personas.prompt_overlay import apply_fragment
```

Immediately after the base system prompt string is built, add:

```python
        system_prompt = apply_fragment(system_prompt, persona)
```

For factories that use a `base_instructions` variable instead of `system_prompt`, add:

```python
        base_instructions = apply_fragment(base_instructions, persona)
```

- [ ] **Step 6: Update portfolio manager risk-debate formatting**

In `tradingagents/agents/managers/portfolio_manager.py`, add:

```python
from tradingagents.personas.risk_weights import format_weighted_risk_debate
```

Change the factory signature:

```python
def create_portfolio_manager(llm, persona=None):
```

Replace:

```python
        history = state["risk_debate_state"]["history"]
```

with:

```python
        history = format_weighted_risk_debate(state["risk_debate_state"], persona)
```

Keep the existing user prompt section name `**Risk Analysts Debate History:**`.

- [ ] **Step 7: Run persona tests**

Run:

```bash
pytest tests/personas -q
```

Expected: PASS.

- [ ] **Step 8: Run existing agent import tests**

Run:

```bash
pytest tests/test_memory_log.py tests/test_model_validation.py -q
```

Expected: PASS. If a legacy test asserts factory arity, update it to assert that old one-argument construction still works.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/graph/trading_graph.py tradingagents/graph/setup.py tradingagents/agents tradingagents/personas tests/personas tests/test_memory_log.py
git commit -m "feat(graph): inject IIC persona into native TradingAgents roles"
```

---

## Task 4: Replace Default Outer Fan-Out With One Balanced Graph

**Files:**
- Create: `tradingagents/secretary/analysis_runner.py`
- Modify: `tradingagents/secretary/persona_runner.py`
- Modify: `tradingagents/secretary/service.py`
- Modify: `tradingagents/secretary/morning.py`
- Modify: `cli/deepdive.py`
- Test: `tests/secretary/test_analysis_runner_modes.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/secretary/test_analysis_runner_modes.py`:

```python
from dataclasses import dataclass


@dataclass
class Call:
    config: dict
    selected_analysts: list[str]


def test_run_default_analysis_uses_one_balanced_graph(monkeypatch):
    from tradingagents.secretary import analysis_runner

    calls = []

    class FakeGraph:
        def __init__(self, config, selected_analysts):
            calls.append(Call(config=config, selected_analysts=selected_analysts))
            self.run_id = "run-balanced"

        def propagate(self, ticker, trade_date):
            assert ticker == "NVDA"
            assert trade_date == "2026-06-01"

    monkeypatch.setattr(analysis_runner, "TradingAgentsGraph", FakeGraph)

    run_ids = analysis_runner.run_default_analysis(
        ticker="NVDA",
        trade_date="2026-06-01",
        config={"default_analysis_persona_id": "balanced"},
        event_context="event text",
        queue_job_id=7,
    )

    assert run_ids == ["run-balanced"]
    assert len(calls) == 1
    assert calls[0].config["persona_id"] == "balanced"
    assert calls[0].config["event_context"] == "event text"
    assert calls[0].config["queue_job_id"] == 7


def test_run_committee_analysis_keeps_explicit_multi_persona_mode(monkeypatch):
    from tradingagents.secretary import analysis_runner

    calls = []

    class FakeGraph:
        def __init__(self, config, selected_analysts):
            calls.append(config["persona_id"])
            self.run_id = f"run-{config['persona_id']}"

        def propagate(self, ticker, trade_date):
            pass

    monkeypatch.setattr(analysis_runner, "TradingAgentsGraph", FakeGraph)

    run_ids = analysis_runner.run_committee_analysis(
        persona_ids=["value", "momentum"],
        ticker="AAPL",
        trade_date="2026-06-01",
        config={},
        parallel=False,
    )

    assert run_ids == ["run-value", "run-momentum"]
    assert calls == ["value", "momentum"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/secretary/test_analysis_runner_modes.py -q
```

Expected: FAIL because `analysis_runner` does not exist.

- [ ] **Step 3: Create `analysis_runner.py`**

Use this implementation:

```python
"""Secretary analysis runners.

Default approved studies run one enriched TradingAgents graph. Committee mode
is explicit and opt-in.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.personas.loader import load_persona_from_file


log = logging.getLogger(__name__)


def _persona_yaml_path(persona_id: str):
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "personas" / f"{persona_id}.yaml"


def _analysts_for_persona(persona_id: str) -> list[str]:
    persona = load_persona_from_file(_persona_yaml_path(persona_id))
    return list(persona.analysts.include)


def _run_one_graph(
    *,
    persona_id: str,
    ticker: str,
    trade_date: str,
    config: dict,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> str:
    overlay = dict(config)
    overlay["persona_id"] = persona_id
    if event_context is not None:
        overlay["event_context"] = event_context
    if queue_job_id is not None:
        overlay["queue_job_id"] = queue_job_id

    graph = TradingAgentsGraph(
        config=overlay,
        selected_analysts=_analysts_for_persona(persona_id),
    )
    graph.propagate(ticker, trade_date)
    return graph.run_id


def run_default_analysis(
    *,
    ticker: str,
    trade_date: str,
    config: dict,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> List[str]:
    persona_id = config.get("default_analysis_persona_id", "balanced")
    return [
        _run_one_graph(
            persona_id=persona_id,
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            event_context=event_context,
            queue_job_id=queue_job_id,
        )
    ]


def run_committee_analysis(
    *,
    persona_ids: Iterable[str],
    ticker: str,
    trade_date: str,
    config: dict,
    parallel: bool = True,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> List[str]:
    ids = list(persona_ids)
    if not ids:
        raise RuntimeError("run_committee_analysis: empty persona list")

    def run_one(pid: str) -> str:
        return _run_one_graph(
            persona_id=pid,
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            event_context=event_context,
            queue_job_id=queue_job_id,
        )

    if not parallel:
        return [run_one(pid) for pid in ids]

    run_ids: list[str] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=len(ids)) as ex:
        future_to_id = {ex.submit(run_one, pid): pid for pid in ids}
        for fut, pid in future_to_id.items():
            try:
                run_ids.append(fut.result())
            except Exception:
                failures += 1
                log.exception("committee persona %s failed for %s", pid, ticker)
    if not run_ids:
        raise RuntimeError("run_committee_analysis: all committee runs failed")
    if failures:
        log.warning("run_committee_analysis: %d/%d failed", failures, len(ids))
    return run_ids
```

- [ ] **Step 4: Keep `persona_runner.py` as compatibility wrapper**

Replace internal implementation with a call to `run_committee_analysis`, or leave the implementation but update the module docstring to state it is only for explicit committee mode.

- [ ] **Step 5: Update event-alert full study path**

In `tradingagents/secretary/service.py`, replace the `load_all_personas` plus `run_personas_parallel` block inside `compose_event_alert` with:

```python
        from tradingagents.secretary.analysis_runner import run_default_analysis, run_committee_analysis

        from tradingagents.default_config import DEFAULT_CONFIG
        config = dict(DEFAULT_CONFIG)

        if config.get("committee_mode_enabled"):
            run_ids = run_committee_analysis(
                persona_ids=config.get("committee_persona_ids", []),
                ticker=ticker,
                trade_date=trade_date,
                config=config,
                parallel=True,
                event_context=raw_text,
                queue_job_id=job_id,
            )
        else:
            run_ids = run_default_analysis(
                ticker=ticker,
                trade_date=trade_date,
                config=config,
                event_context=raw_text,
                queue_job_id=job_id,
            )
```

- [ ] **Step 6: Update morning digest path**

In `tradingagents/secretary/morning.py`, replace `load_all_personas` and `run_personas_parallel` with the same default/committee split. Default must call `run_default_analysis`.

- [ ] **Step 7: Update deepdive CLI**

Change the CLI docstring to explain default balanced run. Add an option:

```python
committee: bool = typer.Option(False, "--committee/--single", help="Run explicit value/momentum/macro committee")
```

When `committee` is false, use `run_default_analysis`. When true, use `run_committee_analysis` with `committee_persona_ids`.

- [ ] **Step 8: Run tests**

Run:

```bash
pytest tests/secretary/test_analysis_runner_modes.py tests/orchestrator/test_compose_event_alert.py tests/cli/test_deepdive.py -q
```

Expected: PASS after updating mocks from `run_personas_parallel` to `run_default_analysis` where the default path is tested.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/secretary/analysis_runner.py tradingagents/secretary/persona_runner.py tradingagents/secretary/service.py tradingagents/secretary/morning.py cli/deepdive.py tests/secretary/test_analysis_runner_modes.py tests/orchestrator/test_compose_event_alert.py tests/cli/test_deepdive.py
git commit -m "feat(secretary): default approved analysis uses one balanced graph"
```

---

## Task 5: Make Secretary Synthesis Work for One Full Analysis or Committee Mode

**Files:**
- Modify: `tradingagents/secretary/synthesis.py`
- Test: `tests/secretary/test_synthesis_modes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/secretary/test_synthesis_modes.py`:

```python
from tradingagents.secretary.synthesis import build_synthesis_prompt


def test_single_analysis_prompt_does_not_claim_three_persona_teams():
    prompt = build_synthesis_prompt(
        ticker="NVDA",
        persona_runs=[
            {
                "persona_id": "balanced",
                "decision": "BUY",
                "final_trade_decision": "Bull and bear debate is material.",
            }
        ],
    )
    assert "Three persona investment teams" not in prompt
    assert "one or more investment analyses" in prompt
    assert "balanced" in prompt


def test_committee_prompt_preserves_disagreement_instruction():
    prompt = build_synthesis_prompt(
        ticker="AAPL",
        persona_runs=[
            {"persona_id": "value", "decision": "HOLD", "final_trade_decision": "valuation risk"},
            {"persona_id": "momentum", "decision": "BUY", "final_trade_decision": "trend strength"},
        ],
    )
    assert "Do NOT smooth over disagreement" in prompt
    assert "value" in prompt
    assert "momentum" in prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/secretary/test_synthesis_modes.py -q
```

Expected: FAIL because the current template says "Three persona investment teams".

- [ ] **Step 3: Update synthesis template**

In `tradingagents/secretary/synthesis.py`, change the first paragraph to:

```python
_SYNTHESIS_TEMPLATE = """You are the IIC Secretary. One or more investment analyses have been produced
for a stock. Your job is to synthesize the reports for a human decision-maker.
If there is only one balanced analysis, surface the important internal
TradingAgents disagreements from that report. If there are multiple committee
analyses, compare them directly.
```

Keep the existing `## Consensus`, `## Divergence`, and `## Recommendation` headings so downstream renderers do not break.

- [ ] **Step 4: Run synthesis tests**

Run:

```bash
pytest tests/secretary/test_synthesis_modes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/secretary/synthesis.py tests/secretary/test_synthesis_modes.py
git commit -m "fix(secretary): synthesize single balanced analysis without committee wording"
```

---

## Task 6: Add Strict Structured Alert Evaluation Before F4 Light Alerts

**Files:**
- Create: `tradingagents/orchestrator/alert_evaluator.py`
- Modify: `tradingagents/orchestrator/promoter.py`
- Modify: `tradingagents/persistence/schema.sql`
- Modify: `tradingagents/persistence/store.py`
- Test: `tests/orchestrator/test_alert_evaluator.py`
- Test: `tests/orchestrator/test_promoter_strict_gate.py`

- [ ] **Step 1: Write evaluator unit tests**

Create `tests/orchestrator/test_alert_evaluator.py`:

```python
from types import SimpleNamespace

from tradingagents.orchestrator.alert_evaluator import evaluate_alert_candidate


class FakeLLM:
    def __init__(self, content):
        self.content = content

    def invoke(self, prompt):
        self.prompt = prompt
        return SimpleNamespace(content=self.content)


def test_alert_evaluator_passes_material_direct_event():
    llm = FakeLLM(
        '{"decision":"pass","score":0.91,"materiality":"earnings surprise",'
        '"actionability":"watchlist thesis may change","ticker_link_evidence":"NVDA named directly",'
        '"novelty":"new filing","disqualifiers":[],"reasons":["direct and material"]}'
    )
    result = evaluate_alert_candidate(
        llm=llm,
        event_text="NVDA raises guidance after earnings.",
        tickers=["NVDA"],
        min_score=0.80,
    )
    assert result.passed is True
    assert result.score == 0.91


def test_alert_evaluator_rejects_invalid_json():
    llm = FakeLLM("not json")
    result = evaluate_alert_candidate(
        llm=llm,
        event_text="generic market chatter",
        tickers=["AAPL"],
        min_score=0.80,
    )
    assert result.passed is False
    assert "invalid_json" in result.disqualifiers
```

- [ ] **Step 2: Run evaluator tests to verify failure**

Run:

```bash
pytest tests/orchestrator/test_alert_evaluator.py -q
```

Expected: FAIL because `alert_evaluator.py` is missing.

- [ ] **Step 3: Implement `alert_evaluator.py`**

Use this implementation:

```python
"""Structured F4 alert strictness evaluator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Literal

from pydantic import BaseModel, Field, ValidationError


class AlertEvaluationPayload(BaseModel):
    decision: Literal["pass", "reject"]
    score: float = Field(ge=0.0, le=1.0)
    materiality: str
    actionability: str
    ticker_link_evidence: str
    novelty: str
    disqualifiers: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AlertEvaluation:
    passed: bool
    score: float
    payload: dict
    disqualifiers: list[str]


def build_alert_evaluation_prompt(*, event_text: str, tickers: list[str]) -> str:
    return (
        "You are the IIC-FORGE alert quality gate. Decide whether this event "
        "is worth sending a light alert to a human investor before any full study. "
        "Reject stale, duplicated, vague, weakly ticker-linked, low-materiality, "
        "or non-actionable events. Pass only when the event has a direct ticker "
        "link and could plausibly change a watchlist thesis or near-term decision.\n\n"
        "Return strict JSON with keys: decision, score, materiality, actionability, "
        "ticker_link_evidence, novelty, disqualifiers, reasons.\n\n"
        f"TICKERS: {', '.join(tickers)}\n\n"
        f"EVENT:\n{event_text[:5000]}"
    )


def evaluate_alert_candidate(
    *,
    llm: Any,
    event_text: str,
    tickers: list[str],
    min_score: float,
) -> AlertEvaluation:
    prompt = build_alert_evaluation_prompt(event_text=event_text, tickers=tickers)
    try:
        resp = llm.invoke(prompt)
        raw = getattr(resp, "content", str(resp))
        payload = AlertEvaluationPayload.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return AlertEvaluation(
            passed=False,
            score=0.0,
            payload={"decision": "reject", "score": 0.0},
            disqualifiers=["invalid_json"],
        )

    passed = (
        payload.decision == "pass"
        and payload.score >= min_score
        and not payload.disqualifiers
    )
    return AlertEvaluation(
        passed=passed,
        score=payload.score,
        payload=payload.model_dump(),
        disqualifiers=list(payload.disqualifiers),
    )
```

- [ ] **Step 4: Add schema and store helpers**

Append to `tradingagents/persistence/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS alert_evaluations (
    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    tickers       TEXT NOT NULL,
    decision      TEXT NOT NULL,
    score         REAL NOT NULL,
    payload       TEXT NOT NULL,
    created_ts    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_evaluations_event
    ON alert_evaluations(event_id);
```

Add to `tradingagents/persistence/store.py`:

```python
def insert_alert_evaluation(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    tickers: list[str],
    decision: str,
    score: float,
    payload: dict,
    created_ts: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO alert_evaluations "
        "(event_id, tickers, decision, score, payload, created_ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (event_id, json.dumps(tickers), decision, score, json.dumps(payload), created_ts),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 5: Write promoter strict-gate test**

Create `tests/orchestrator/test_promoter_strict_gate.py`:

```python
from dataclasses import dataclass
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator.promoter import run_once


@dataclass
class EvalResult:
    passed: bool
    score: float
    payload: dict
    disqualifiers: list[str]


def seed_candidate(conn):
    store.upsert_watchlist(conn, ticker="NVDA", ttl_until=None, tags=["user"])
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.95,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    store.insert_event_ticker(conn, event_id="ev1", ticker="NVDA", confidence=1.0)


def test_promoter_rejects_candidate_when_strict_gate_fails(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    seed_candidate(conn)
    secretary = MagicMock()

    n = run_once(
        conn,
        salience_threshold=0.85,
        ticker_conf_threshold=0.9,
        batch_size=50,
        cooldown_min=60,
        secretary=secretary,
        approval_gate_enabled=True,
        pending_ttl_hours=24,
        alert_evaluator=lambda event_id, tickers: EvalResult(
            passed=False,
            score=0.2,
            payload={"decision": "reject"},
            disqualifiers=["low_materiality"],
        ),
    )

    assert n == 0
    secretary.compose_event_alert_light.assert_not_called()


def test_promoter_composes_when_strict_gate_passes(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    seed_candidate(conn)
    secretary = MagicMock()

    n = run_once(
        conn,
        salience_threshold=0.85,
        ticker_conf_threshold=0.9,
        batch_size=50,
        cooldown_min=60,
        secretary=secretary,
        approval_gate_enabled=True,
        pending_ttl_hours=24,
        alert_evaluator=lambda event_id, tickers: EvalResult(
            passed=True,
            score=0.91,
            payload={"decision": "pass"},
            disqualifiers=[],
        ),
    )

    assert n == 1
    secretary.compose_event_alert_light.assert_called_once()
```

- [ ] **Step 6: Modify promoter run_once**

Add optional parameter:

```python
    alert_evaluator=None,
```

Before `secretary.compose_event_alert_light(...)`, add:

```python
            if alert_evaluator is not None:
                evaluation = alert_evaluator(g["event_id"], fresh)
                store.insert_alert_evaluation(
                    conn,
                    event_id=g["event_id"],
                    tickers=fresh,
                    decision="pass" if evaluation.passed else "reject",
                    score=evaluation.score,
                    payload=evaluation.payload,
                    created_ts=_now_utc().isoformat(),
                )
                if not evaluation.passed:
                    log.info(
                        "light alert rejected event_id=%s tickers=%s disqualifiers=%s",
                        g["event_id"],
                        fresh,
                        evaluation.disqualifiers,
                    )
                    continue
```

- [ ] **Step 7: Wire evaluator in promoter main**

When `gate_enabled`, after constructing the quick LLM, create:

```python
        from tradingagents.orchestrator.alert_evaluator import evaluate_alert_candidate

        def alert_evaluator(event_id, tickers):
            ev = store.get_event(conn, event_id=event_id)
            event_text = ""
            if ev is not None and ev["raw_path"]:
                from pathlib import Path
                p = Path(ev["raw_path"])
                if p.exists():
                    event_text = p.read_text(encoding="utf-8", errors="replace")
            return evaluate_alert_candidate(
                llm=llm,
                event_text=event_text,
                tickers=list(tickers),
                min_score=cfg.get("alert_quality_threshold", 0.80),
            )
```

Add config:

```python
    "alert_quality_threshold": 0.80,
```

Pass `alert_evaluator=alert_evaluator` to `run_once`.

- [ ] **Step 8: Run strict-gate tests**

Run:

```bash
pytest tests/orchestrator/test_alert_evaluator.py tests/orchestrator/test_promoter_strict_gate.py tests/orchestrator/test_promoter_light_alert.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/orchestrator/alert_evaluator.py tradingagents/orchestrator/promoter.py tradingagents/persistence/schema.sql tradingagents/persistence/store.py tradingagents/default_config.py tests/orchestrator/test_alert_evaluator.py tests/orchestrator/test_promoter_strict_gate.py tests/orchestrator/test_promoter_light_alert.py
git commit -m "feat(orchestrator): add strict structured alert quality gate"
```

---

## Task 7: Fix Approval Action Lineage From Light Alert to Full Brief

**Files:**
- Modify: `tradingagents/persistence/schema.sql`
- Modify: `tradingagents/persistence/store.py`
- Modify: `tradingagents/orchestrator/action_handler.py`
- Modify: `tradingagents/orchestrator/dispatch.py`
- Test: `tests/orchestrator/test_action_handler_run_full_study.py`
- Test: `tests/orchestrator/test_dispatch_lineage.py`

- [ ] **Step 1: Add failing action-handler expectation**

Update `tests/orchestrator/test_action_handler_run_full_study.py` so the happy-path test asserts `result_job_id` is set and `result_brief_id` is still null immediately after enqueue:

```python
    row = conn.execute(
        "SELECT result_job_id, result_brief_id, dispatched_ts FROM brief_actions "
        "WHERE action_id = ?",
        (aid,),
    ).fetchone()
    assert row["result_job_id"] == job["job_id"]
    assert row["result_brief_id"] is None
    assert row["dispatched_ts"] is not None
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/orchestrator/test_action_handler_run_full_study.py -q
```

Expected: FAIL because `brief_actions.result_job_id` and `dispatched_ts` do not exist.

- [ ] **Step 3: Add append-only schema columns**

Append to `tradingagents/persistence/schema.sql`:

```sql
ALTER TABLE brief_actions ADD COLUMN result_job_id INTEGER REFERENCES queue_jobs(job_id);
ALTER TABLE brief_actions ADD COLUMN dispatched_ts TEXT;
ALTER TABLE brief_actions ADD COLUMN error TEXT;

CREATE INDEX IF NOT EXISTS idx_brief_actions_result_job
    ON brief_actions(result_job_id);
```

- [ ] **Step 4: Add store helpers**

In `tradingagents/persistence/store.py`, add:

```python
def mark_action_dispatched(
    conn: sqlite3.Connection,
    *,
    action_id: int,
    result_job_id: int,
    dispatched_ts: str,
) -> None:
    conn.execute(
        "UPDATE brief_actions SET result_job_id = ?, dispatched_ts = ? "
        "WHERE action_id = ?",
        (result_job_id, dispatched_ts, action_id),
    )
    conn.commit()


def mark_action_error(
    conn: sqlite3.Connection,
    *,
    action_id: int,
    error: str,
) -> None:
    conn.execute(
        "UPDATE brief_actions SET error = ? WHERE action_id = ?",
        (error[:1000], action_id),
    )
    conn.commit()


def mark_full_study_action_done_for_job(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    result_brief_id: str,
) -> None:
    conn.execute(
        "UPDATE brief_actions SET result_brief_id = ? "
        "WHERE action_type = 'run_full_study' AND result_job_id = ?",
        (result_brief_id, job_id),
    )
    conn.commit()
```

Change `fetch_accepted_undispatched` to:

```python
        "SELECT * FROM brief_actions "
        "WHERE state = 'accepted' "
        "  AND result_backtest_id IS NULL "
        "  AND result_brief_id IS NULL "
        "  AND result_job_id IS NULL "
        "  AND error IS NULL "
        "ORDER BY action_id"
```

- [ ] **Step 5: Update action handler**

In the `run_full_study` branch, capture the insert cursor:

```python
        from datetime import datetime, timezone

        with conn:
            cur = conn.execute(
                "INSERT INTO queue_jobs (job_type, payload, state, "
                "enqueued_ts, trigger_event_id) VALUES (?, ?, 'queued', "
                "datetime('now'), ?)",
                (
                    "event_alert",
                    _j.dumps(
                        {
                            "event_id": event_id,
                            "ticker": ticker,
                            "action_id": row["action_id"],
                            "parent_brief_id": row["brief_id"],
                        }
                    ),
                    event_id,
                ),
            )
            job_id = cur.lastrowid
        store.mark_action_dispatched(
            conn,
            action_id=row["action_id"],
            result_job_id=job_id,
            dispatched_ts=datetime.now(timezone.utc).isoformat(),
        )
```

On malformed action, call:

```python
            store.mark_action_error(
                conn,
                action_id=row["action_id"],
                error=f"missing event_id/ticker event_id={event_id!r} ticker={ticker!r}",
            )
```

Do not set `result_brief_id` to the light brief as a sentinel anymore.

- [ ] **Step 6: Update dispatch parent linkage**

In `tradingagents/orchestrator/dispatch.py`, read optional payload fields:

```python
    action_id = payload.get("action_id")
    parent_brief_id = payload.get("parent_brief_id")
```

Use `parent_brief_id` first. Keep the current event lookup only as fallback:

```python
    if not parent_brief_id:
        parent_row = conn.execute(
            "SELECT brief_id FROM briefs WHERE mode = 'event_alert_light' "
            "AND trigger_event_id = ? ORDER BY generated_ts DESC LIMIT 1",
            (event_id,),
        ).fetchone()
        parent_brief_id = parent_row[0] if parent_row else None
```

After `compose_event_alert(...)` succeeds:

```python
    if action_id is not None:
        from tradingagents.persistence import store
        store.mark_action_done(
            conn,
            action_id=int(action_id),
            result_brief_id=brief_id,
        )
    else:
        from tradingagents.persistence import store
        store.mark_full_study_action_done_for_job(
            conn,
            job_id=job_id,
            result_brief_id=brief_id,
        )
```

- [ ] **Step 7: Write dispatch lineage test**

Create `tests/orchestrator/test_dispatch_lineage.py`:

```python
import json
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator.dispatch import dispatch_event_alert


def test_dispatch_uses_payload_parent_brief_and_marks_action_done(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["NVDA"]',
        generated_ts="2026-06-01T00:00:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
        trigger_event_id="ev1",
    )
    aid = store.insert_brief_action(
        conn,
        brief_id="light1",
        action_type="run_full_study",
        action_params={"ticker": "NVDA"},
        expires_at="2026-06-02T00:00:00+00:00",
    )
    secretary = MagicMock()
    secretary.compose_event_alert.return_value = "full1"
    store.insert_brief(
        conn,
        brief_id="full1",
        mode="event_alert",
        scope="NVDA",
        generated_ts="2026-06-01T00:05:00+00:00",
        content_path="briefs/full1.md",
        run_ids=["r1"],
        parent_brief_id="light1",
        trigger_event_id="ev1",
    )

    result = dispatch_event_alert(
        conn,
        {
            "job_id": 42,
            "payload": json.dumps(
                {
                    "event_id": "ev1",
                    "ticker": "NVDA",
                    "action_id": aid,
                    "parent_brief_id": "light1",
                }
            ),
        },
        secretary=secretary,
    )

    assert result["brief_id"] == "full1"
    secretary.compose_event_alert.assert_called_once_with(
        event_id="ev1",
        ticker="NVDA",
        job_id=42,
        parent_brief_id="light1",
    )
    row = conn.execute(
        "SELECT result_brief_id FROM brief_actions WHERE action_id = ?",
        (aid,),
    ).fetchone()
    assert row["result_brief_id"] == "full1"
```

- [ ] **Step 8: Run lineage tests**

Run:

```bash
pytest tests/orchestrator/test_action_handler_run_full_study.py tests/orchestrator/test_dispatch_lineage.py tests/smoke/test_f4_exit_gate.py -q
```

Expected: PASS after updating smoke expectations for `result_job_id`.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/persistence/schema.sql tradingagents/persistence/store.py tradingagents/orchestrator/action_handler.py tradingagents/orchestrator/dispatch.py tests/orchestrator/test_action_handler_run_full_study.py tests/orchestrator/test_dispatch_lineage.py tests/smoke/test_f4_exit_gate.py
git commit -m "fix(orchestrator): record approval-to-study job lineage"
```

---

## Task 8: Apply Quiet Hours to Light Alerts and Preserve Delivery Audit Rows

**Files:**
- Modify: `tradingagents/delivery/base.py`
- Modify: `tradingagents/secretary/service.py`
- Test: `tests/delivery/test_quiet_hours_light_alert.py`

- [ ] **Step 1: Write failing quiet-hours test**

Create `tests/delivery/test_quiet_hours_light_alert.py`:

```python
from datetime import time
from unittest.mock import patch

from tradingagents.delivery.base import DeliveryChannel
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


class FakeChannel(DeliveryChannel):
    channel_name = "fake"

    def _send_impl(self, brief, mode, body):
        return ("fake:1", None)


def test_light_alert_respects_quiet_hours(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["NVDA"]',
        generated_ts="2026-06-01T04:00:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
    )
    ch = FakeChannel(
        conn=conn,
        config={
            "delivery": {
                "quiet_hours": {
                    "enabled": True,
                    "start": "22:00",
                    "end": "07:00",
                }
            },
            "brief_action_ttl_hours": 24,
        },
    )
    with patch("tradingagents.delivery.base._local_now") as now:
        now.return_value = time(23, 0)
        delivery_id = ch.send(
            brief={"brief_id": "light1"},
            mode="event_alert_light",
            body="body",
        )
    row = conn.execute("SELECT * FROM deliveries WHERE delivery_id = ?", (delivery_id,)).fetchone()
    assert row["status"] == "skipped"
    assert row["skip_reason"] == "quiet_hours"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/delivery/test_quiet_hours_light_alert.py -q
```

Expected: FAIL because quiet hours only apply to `event_alert`.

- [ ] **Step 3: Update delivery base**

In `tradingagents/delivery/base.py`, add:

```python
_QUIET_HOUR_MODES = {"event_alert", "event_alert_light"}
```

Change:

```python
        if mode == "event_alert" and is_quiet_hours(
```

to:

```python
        if mode in _QUIET_HOUR_MODES and is_quiet_hours(
```

Keep `_ensure_pending_action` gated to only `mode == "event_alert"` so light alerts do not create backtest actions.

- [ ] **Step 4: Make light-alert delivery failures visible**

In `Secretary._deliver_light_alert`, replace the final broad `except Exception: pass` with:

```python
            except Exception as exc:  # noqa: BLE001
                store.insert_delivery(
                    self._conn,
                    brief_id=brief_id,
                    channel=name,
                    status="failed",
                    sent_ts=None,
                    channel_ref=str(exc)[:500],
                    skip_reason=None,
                )
```

- [ ] **Step 5: Run delivery tests**

Run:

```bash
pytest tests/delivery/test_quiet_hours_light_alert.py tests/delivery -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/delivery/base.py tradingagents/secretary/service.py tests/delivery/test_quiet_hours_light_alert.py
git commit -m "fix(delivery): apply quiet hours and audit failures for light alerts"
```

---

## Task 9: Add Analysis Pack Persistence for Follow-Up Reuse

**Files:**
- Create: `tradingagents/analysis_pack/__init__.py`
- Create: `tradingagents/analysis_pack/model.py`
- Create: `tradingagents/analysis_pack/builder.py`
- Create: `tradingagents/analysis_pack/store.py`
- Create: `tradingagents/analysis_pack/prompting.py`
- Modify: `tradingagents/persistence/schema.sql`
- Modify: `tradingagents/persistence/store.py`
- Modify: `tradingagents/secretary/service.py`
- Test: `tests/analysis_pack/test_analysis_pack_store.py`
- Test: `tests/analysis_pack/test_analysis_pack_builder.py`

- [ ] **Step 1: Write store tests**

Create `tests/analysis_pack/test_analysis_pack_store.py`:

```python
from pathlib import Path

from tradingagents.analysis_pack.store import create_analysis_pack, load_analysis_pack
from tradingagents.persistence.db import connect


def test_create_and_load_analysis_pack(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    pack_id = create_analysis_pack(
        conn=conn,
        data_dir=data_dir,
        event_id="ev1",
        ticker="NVDA",
        trade_date="2026-06-01",
        source_run_ids=["r1"],
        content={"ticker": "NVDA", "facts": ["guidance raised"]},
    )

    loaded = load_analysis_pack(conn=conn, data_dir=data_dir, pack_id=pack_id)
    assert loaded["event_id"] == "ev1"
    assert loaded["ticker"] == "NVDA"
    assert loaded["content"]["facts"] == ["guidance raised"]
    assert Path(data_dir / loaded["content_path"]).exists()
```

- [ ] **Step 2: Run store test to verify failure**

Run:

```bash
pytest tests/analysis_pack/test_analysis_pack_store.py -q
```

Expected: FAIL because `analysis_pack` package is missing.

- [ ] **Step 3: Add schema**

Append:

```sql
CREATE TABLE IF NOT EXISTS analysis_packs (
    pack_id        TEXT PRIMARY KEY,
    event_id       TEXT REFERENCES events(event_id),
    ticker         TEXT NOT NULL,
    trade_date     TEXT NOT NULL,
    source_run_ids TEXT NOT NULL,
    content_path   TEXT NOT NULL,
    created_ts     TEXT NOT NULL,
    version        INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_analysis_packs_event_ticker
    ON analysis_packs(event_id, ticker);

ALTER TABLE briefs ADD COLUMN analysis_pack_id TEXT REFERENCES analysis_packs(pack_id);
ALTER TABLE runs   ADD COLUMN analysis_pack_id TEXT REFERENCES analysis_packs(pack_id);
```

- [ ] **Step 4: Implement `analysis_pack/store.py`**

Use:

```python
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def create_analysis_pack(
    *,
    conn: sqlite3.Connection,
    data_dir: Path,
    event_id: str | None,
    ticker: str,
    trade_date: str,
    source_run_ids: list[str],
    content: dict[str, Any],
) -> str:
    pack_id = uuid.uuid4().hex
    rel_path = Path("analysis_packs") / f"{pack_id}.json"
    abs_path = data_dir / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
    conn.execute(
        "INSERT INTO analysis_packs "
        "(pack_id, event_id, ticker, trade_date, source_run_ids, content_path, created_ts, version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (
            pack_id,
            event_id,
            ticker,
            trade_date,
            json.dumps(source_run_ids),
            str(rel_path),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return pack_id


def load_analysis_pack(
    *,
    conn: sqlite3.Connection,
    data_dir: Path,
    pack_id: str,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM analysis_packs WHERE pack_id = ?",
        (pack_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"analysis pack not found: {pack_id}")
    content = json.loads((data_dir / row["content_path"]).read_text(encoding="utf-8"))
    return {
        "pack_id": row["pack_id"],
        "event_id": row["event_id"],
        "ticker": row["ticker"],
        "trade_date": row["trade_date"],
        "source_run_ids": json.loads(row["source_run_ids"]),
        "content_path": row["content_path"],
        "created_ts": row["created_ts"],
        "version": row["version"],
        "content": content,
    }
```

- [ ] **Step 5: Implement `analysis_pack/model.py`**

Use:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalysisPackContent(BaseModel):
    version: int = 1
    ticker: str
    trade_date: str
    event_id: str | None = None
    event_context: str = ""
    reports: dict[str, str] = Field(default_factory=dict)
    debates: dict[str, Any] = Field(default_factory=dict)
    final_trade_decisions: list[dict[str, str]] = Field(default_factory=list)
```

- [ ] **Step 6: Write builder test**

Create `tests/analysis_pack/test_analysis_pack_builder.py`:

```python
import json

from tradingagents.analysis_pack.builder import build_pack_content_from_runs
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def test_build_pack_content_from_run_artifact(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    artifact_dir = data_dir / "runs" / "r1"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "pm_synthesis.md").write_text("Final BUY", encoding="utf-8")
    (artifact_dir / "state.json").write_text(
        json.dumps(
            {
                "market_report": "market",
                "news_report": "news",
                "fundamentals_report": "fundamentals",
                "derivatives_report": "derivatives",
                "investment_debate_state": {"history": "bull bear"},
                "risk_debate_state": {"history": "risk"},
            }
        ),
        encoding="utf-8",
    )
    store.insert_run(
        conn,
        run_id="r1",
        ticker="NVDA",
        persona_id="balanced",
        started_ts="2026-06-01T00:00:00+00:00",
        artifact_dir="runs/r1",
    )
    content = build_pack_content_from_runs(
        conn=conn,
        data_dir=data_dir,
        event_id="ev1",
        ticker="NVDA",
        trade_date="2026-06-01",
        event_context="event text",
        run_ids=["r1"],
    )
    assert content["ticker"] == "NVDA"
    assert content["reports"]["market_report"] == "market"
    assert content["final_trade_decisions"][0]["body"] == "Final BUY"
```

- [ ] **Step 7: Implement builder with tolerant artifact reads**

Use:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_pack_content_from_runs(
    *,
    conn: sqlite3.Connection,
    data_dir: Path,
    event_id: str | None,
    ticker: str,
    trade_date: str,
    event_context: str,
    run_ids: list[str],
) -> dict[str, Any]:
    reports: dict[str, str] = {}
    debates: dict[str, Any] = {}
    finals: list[dict[str, str]] = []

    for run_id in run_ids:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            continue
        artifact_dir = data_dir / row["artifact_dir"]
        state_path = artifact_dir / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for key in [
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
                "derivatives_report",
            ]:
                if state.get(key):
                    reports[key] = state[key]
            for key in ["investment_debate_state", "risk_debate_state"]:
                if state.get(key):
                    debates[key] = state[key]
        finals.append(
            {
                "run_id": run_id,
                "persona_id": row["persona_id"] or "default",
                "decision": row["decision"] or "",
                "body": _read_text(artifact_dir / "pm_synthesis.md"),
            }
        )

    return {
        "version": 1,
        "ticker": ticker,
        "trade_date": trade_date,
        "event_id": event_id,
        "event_context": event_context,
        "reports": reports,
        "debates": debates,
        "final_trade_decisions": finals,
    }
```

- [ ] **Step 8: Add brief link helper**

In `tradingagents/persistence/store.py`, add:

```python
def update_brief_analysis_pack(
    conn: sqlite3.Connection,
    *,
    brief_id: str,
    analysis_pack_id: str,
) -> None:
    conn.execute(
        "UPDATE briefs SET analysis_pack_id = ? WHERE brief_id = ?",
        (analysis_pack_id, brief_id),
    )
    conn.commit()
```

- [ ] **Step 9: Link packs from full event alerts**

In `Secretary.compose_event_alert`, after `store.insert_brief(...)`, build and persist a pack:

```python
        from tradingagents.analysis_pack.builder import build_pack_content_from_runs
        from tradingagents.analysis_pack.store import create_analysis_pack

        pack_content = build_pack_content_from_runs(
            conn=self._conn,
            data_dir=self._data_dir,
            event_id=event_id,
            ticker=ticker,
            trade_date=trade_date,
            event_context=raw_text,
            run_ids=run_ids,
        )
        pack_id = create_analysis_pack(
            conn=self._conn,
            data_dir=self._data_dir,
            event_id=event_id,
            ticker=ticker,
            trade_date=trade_date,
            source_run_ids=run_ids,
            content=pack_content,
        )
        store.update_brief_analysis_pack(
            self._conn,
            brief_id=brief_id,
            analysis_pack_id=pack_id,
        )
```

- [ ] **Step 10: Run analysis-pack tests**

Run:

```bash
pytest tests/analysis_pack -q
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add tradingagents/analysis_pack tradingagents/persistence/schema.sql tradingagents/persistence/store.py tradingagents/secretary/service.py tests/analysis_pack
git commit -m "feat(analysis-pack): persist reusable full-study context"
```

---

## Task 10: Use Analysis Packs for Directed Follow-Up Runs

**Files:**
- Modify: `tradingagents/secretary/refinement.py`
- Modify: `tradingagents/secretary/service.py`
- Modify: `tradingagents/secretary/analysis_runner.py`
- Create: `tradingagents/analysis_pack/prompting.py`
- Test: `tests/secretary/test_refinement_uses_analysis_pack.py`

- [ ] **Step 1: Write failing test**

Create `tests/secretary/test_refinement_uses_analysis_pack.py`:

```python
from unittest.mock import MagicMock, patch

from tradingagents.analysis_pack.store import create_analysis_pack
from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.secretary.service import Secretary


def test_compose_refinement_threads_parent_analysis_pack(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    pack_id = create_analysis_pack(
        conn=conn,
        data_dir=data_dir,
        event_id="ev1",
        ticker="NVDA",
        trade_date="2026-06-01",
        source_run_ids=["r1"],
        content={"ticker": "NVDA", "event_context": "event", "reports": {"news_report": "news"}},
    )
    store.insert_brief(
        conn,
        brief_id="full1",
        mode="event_alert",
        scope="NVDA",
        generated_ts="2026-06-01T00:00:00+00:00",
        content_path="briefs/full1.md",
        run_ids=["r1"],
    )
    store.update_brief_analysis_pack(conn, brief_id="full1", analysis_pack_id=pack_id)
    sec = Secretary(conn=conn, data_dir=str(data_dir), llm=MagicMock())

    with patch("tradingagents.secretary.service.run_one_ticker") as run_one:
        run_one.return_value = (["r2"], {"consensus": "c", "divergence": "d", "recommendation": "r"})
        sec.compose_refinement(
            parent_brief_id="full1",
            overrides={"risk_tilt": "more_aggressive"},
            reply_text="more aggressive",
        )

    called_config = run_one.call_args.kwargs["config"]
    assert "prior_analysis_pack" in called_config
    assert called_config["prior_analysis_pack"]["content"]["reports"]["news_report"] == "news"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/secretary/test_refinement_uses_analysis_pack.py -q
```

Expected: FAIL because refinement does not load parent analysis packs.

- [ ] **Step 3: Implement pack prompt rendering**

Create `tradingagents/analysis_pack/prompting.py`:

```python
from __future__ import annotations

from typing import Any


def render_pack_for_followup(pack: dict[str, Any], *, max_chars: int = 12000) -> str:
    content = pack["content"]
    lines = [
        f"Prior analysis pack for {content.get('ticker', pack.get('ticker'))}",
        f"Trade date: {content.get('trade_date', pack.get('trade_date'))}",
        "",
        "Event context:",
        content.get("event_context", ""),
        "",
        "Key reports:",
    ]
    for key, body in content.get("reports", {}).items():
        lines += [f"## {key}", str(body)]
    lines += ["", "Prior final decisions:"]
    for item in content.get("final_trade_decisions", []):
        lines += [
            f"## {item.get('persona_id', 'analysis')} {item.get('decision', '')}",
            item.get("body", ""),
        ]
    return "\n".join(lines)[:max_chars]
```

- [ ] **Step 4: Load pack in refinement**

In `Secretary.compose_refinement`, after `parent = store.load_brief(...)`, add:

```python
        if parent.get("analysis_pack_id"):
            from tradingagents.analysis_pack.store import load_analysis_pack
            config["prior_analysis_pack"] = load_analysis_pack(
                conn=self._conn,
                data_dir=self._data_dir,
                pack_id=parent["analysis_pack_id"],
            )
```

Place this after `config = dict(DEFAULT_CONFIG)` and before calling `run_one_ticker`.

- [ ] **Step 5: Thread pack into graph config**

In `analysis_runner._run_one_graph`, if `config.get("prior_analysis_pack")` exists, add:

```python
    overlay["prior_analysis_pack"] = config["prior_analysis_pack"]
```

- [ ] **Step 6: Add pack context to initial state**

In `tradingagents/graph/trading_graph.py`, before invoking the graph, if `self.config.get("prior_analysis_pack")` exists, set:

```python
        if self.config.get("prior_analysis_pack"):
            from tradingagents.analysis_pack.prompting import render_pack_for_followup
            init_agent_state["prior_analysis_pack_context"] = render_pack_for_followup(
                self.config["prior_analysis_pack"]
            )
```

Use this field in the research manager, trader, and portfolio manager prompts in the next step. Keep analyst prompts unchanged in this task so reused pack context affects decision shaping without bloating every analyst tool loop.

- [ ] **Step 7: Update manager/trader prompts to use pack context**

In `research_manager.py`, `trader.py`, and `portfolio_manager.py`, append to the user prompt when present:

```python
        prior_pack = state.get("prior_analysis_pack_context", "")
        prior_pack_block = (
            f"\n\n**Reusable prior analysis pack:**\n{prior_pack}\n"
            if prior_pack
            else ""
        )
```

Then include `{prior_pack_block}` near existing context blocks.

- [ ] **Step 8: Run refinement tests**

Run:

```bash
pytest tests/secretary/test_refinement_uses_analysis_pack.py tests/secretary -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/analysis_pack/prompting.py tradingagents/secretary/service.py tradingagents/secretary/analysis_runner.py tradingagents/graph/trading_graph.py tradingagents/agents/managers/research_manager.py tradingagents/agents/trader/trader.py tradingagents/agents/managers/portfolio_manager.py tests/secretary/test_refinement_uses_analysis_pack.py
git commit -m "feat(refinement): reuse analysis packs for directed follow-ups"
```

---

## Task 11: Improve Token Cache Determinism and Cost Reporting

**Files:**
- Modify: `tradingagents/dataflows/y_finance.py`
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/graph/run_recorder.py`
- Test: `tests/dataflows/test_prompt_determinism.py`
- Test: `tests/graph/test_cache_ratio_metrics.py`

- [ ] **Step 1: Write deterministic-output test**

Create `tests/dataflows/test_prompt_determinism.py`:

```python
def test_yfinance_outputs_do_not_include_retrieved_on_timestamp():
    import inspect
    import tradingagents.dataflows.y_finance as yfmod

    source = inspect.getsource(yfmod)
    assert "Data retrieved on:" not in source
    assert "Retrieved on:" not in source
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/dataflows/test_prompt_determinism.py -q
```

Expected: FAIL if dynamic retrieval strings remain in `y_finance.py`.

- [ ] **Step 3: Remove prompt-visible dynamic retrieval strings**

In `tradingagents/dataflows/y_finance.py`, remove lines that append current timestamps such as:

```python
data = f"Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n" + data
```

Do not remove actual market dates from tabular data. The goal is only to remove run-time `now` strings from LLM-visible payloads.

- [ ] **Step 4: Add config limits for prompt-heavy news**

In `tradingagents/default_config.py`, add or confirm these keys are present and conservative:

```python
    "news_article_limit": 20,
    "global_news_article_limit": 12,
    "global_news_lookback_days": 7,
```

If the keys already exist with higher values, lower them only after checking existing tests that assert defaults.

- [ ] **Step 5: Add cache ratio helper test**

Create `tests/graph/test_cache_ratio_metrics.py`:

```python
from tradingagents.graph.run_recorder import compute_cache_hit_ratio


def test_compute_cache_hit_ratio_handles_zero_and_nulls():
    assert compute_cache_hit_ratio(None, None) is None
    assert compute_cache_hit_ratio(0, 0) is None
    assert compute_cache_hit_ratio(30, 70) == 0.30
```

- [ ] **Step 6: Implement cache ratio helper**

In `tradingagents/graph/run_recorder.py`, add:

```python
def compute_cache_hit_ratio(cache_hit_tokens, cache_miss_tokens):
    if cache_hit_tokens is None and cache_miss_tokens is None:
        return None
    hit = int(cache_hit_tokens or 0)
    miss = int(cache_miss_tokens or 0)
    total = hit + miss
    if total <= 0:
        return None
    return hit / total
```

Use this helper in any cost dashboard/report code that currently recomputes ratios inline.

- [ ] **Step 7: Run cache tests**

Run:

```bash
pytest tests/dataflows/test_prompt_determinism.py tests/graph/test_cache_ratio_metrics.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/dataflows/y_finance.py tradingagents/default_config.py tradingagents/graph/run_recorder.py tests/dataflows/test_prompt_determinism.py tests/graph/test_cache_ratio_metrics.py
git commit -m "perf(tokens): stabilize prompt-visible data and cache metrics"
```

---

## Task 12: Recover F2 Backtest Implementation Safely

**Files:**
- Restore/create: `tradingagents/backtest/**`
- Restore/create: `tests/backtest/**`
- Modify: `tradingagents/orchestrator/action_handler.py`
- Modify: `tradingagents/delivery/base.py`
- Modify: `scripts/f5_exit_gate.py`

- [ ] **Step 1: Restore only the F2 package and tests**

Run:

```bash
git restore --source origin/feat/iic-forge-05-f2 -- tradingagents/backtest tests/backtest
```

Expected: only `tradingagents/backtest/**` and `tests/backtest/**` are added or modified. No F3/F4/F5 files are restored from that branch.

- [ ] **Step 2: Confirm no accidental branch overwrite**

Run:

```bash
git status --short
```

Expected: changes are limited to `tradingagents/backtest/**` and `tests/backtest/**` before any integration edits.

- [ ] **Step 3: Run restored backtest tests**

Run:

```bash
pytest tests/backtest -q
```

Expected: failures are allowed at this step only if imports or current schema integration changed since the F2 branch. Record exact failures in the task notes.

- [ ] **Step 4: Wire `run_backtest` dispatch to real F2 harness**

Replace stub dispatches with an adapter shaped like:

```python
def dispatch_backtest_from_brief(conn, *, brief_id: str, params: dict) -> int:
    from tradingagents.backtest.harness import run_backtest_for_brief

    return run_backtest_for_brief(
        conn=conn,
        brief_id=brief_id,
        params=params,
    )
```

Use this adapter from the service or CLI that starts `action_handler.tick`.

- [ ] **Step 5: Keep backtest actions on full briefs only**

Confirm `DeliveryChannel._ensure_pending_action` still creates `run_backtest` only for:

```python
if mode == "event_alert":
```

Do not create backtest actions for `event_alert_light`.

- [ ] **Step 6: Run backtest and F5 action tests**

Run:

```bash
pytest tests/backtest tests/orchestrator/test_action_handler.py tests/smoke/test_f5_exit_gate.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/backtest tests/backtest tradingagents/orchestrator/action_handler.py tradingagents/delivery/base.py scripts/f5_exit_gate.py tests/smoke/test_f5_exit_gate.py
git commit -m "feat(backtest): restore F2 harness and wire F5 action dispatch"
```

---

## Task 13: Build the Combined F4/F5 Exit Gate

**Files:**
- Create: `scripts/f4_f5_exit_gate.py`
- Modify: `scripts/f4_exit_gate.py`
- Modify: `scripts/f5_exit_gate.py`
- Test: `tests/scripts/test_f4_f5_exit_gate.py`
- Test: `tests/smoke/test_f4_f5_combined_gate.py`

- [ ] **Step 1: Write combined gate unit test**

Create `tests/scripts/test_f4_f5_exit_gate.py`:

```python
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from scripts.f4_f5_exit_gate import evaluate


def test_combined_gate_passes_complete_approval_flow(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.95,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["NVDA"]',
        generated_ts="2026-06-01T00:02:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
        trigger_event_id="ev1",
    )
    store.insert_delivery(
        conn,
        brief_id="light1",
        channel="telegram",
        status="sent",
        sent_ts="2026-06-01T00:02:01+00:00",
        channel_ref="1",
        skip_reason=None,
    )
    aid = store.insert_brief_action(
        conn,
        brief_id="light1",
        action_type="run_full_study",
        action_params={"ticker": "NVDA"},
        expires_at="2026-06-02T00:00:00+00:00",
    )
    store.update_action_state(
        conn,
        action_id=aid,
        state="accepted",
        responded_at="2026-06-01T00:03:00+00:00",
    )
    conn.execute(
        "INSERT INTO queue_jobs (job_id, job_type, payload, state, enqueued_ts, "
        "finished_ts, trigger_event_id, brief_id) "
        "VALUES (7, 'event_alert', '{}', 'done', "
        "'2026-06-01T00:03:10+00:00', '2026-06-01T00:08:00+00:00', 'ev1', 'full1')"
    )
    conn.commit()
    store.mark_action_dispatched(
        conn,
        action_id=aid,
        result_job_id=7,
        dispatched_ts="2026-06-01T00:03:10+00:00",
    )
    store.insert_brief(
        conn,
        brief_id="full1",
        mode="event_alert",
        scope="NVDA",
        generated_ts="2026-06-01T00:08:00+00:00",
        content_path="briefs/full1.md",
        run_ids=["r1"],
        parent_brief_id="light1",
        trigger_event_id="ev1",
    )
    store.mark_action_done(conn, action_id=aid, result_brief_id="full1")
    store.insert_delivery(
        conn,
        brief_id="full1",
        channel="telegram",
        status="sent",
        sent_ts="2026-06-01T00:08:01+00:00",
        channel_ref="2",
        skip_reason=None,
    )

    report = evaluate(
        conn,
        since=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        window_hours=1,
    )

    assert report["pass"] is True
    assert report["checks"]["light_alert_latency"]["pass"] is True
    assert report["checks"]["approval_lineage"]["pass"] is True
    assert report["checks"]["full_brief_delivery"]["pass"] is True
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/scripts/test_f4_f5_exit_gate.py -q
```

Expected: FAIL because `scripts/f4_f5_exit_gate.py` does not exist.

- [ ] **Step 3: Implement combined evaluator checks**

Create `scripts/f4_f5_exit_gate.py` with:

```python
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f, c = int(k), int(k) + 1
    if c >= len(s):
        return s[-1]
    return s[f] + (s[c] - s[f]) * (k - f)


def _seconds(a: str, b: str) -> float:
    aa = datetime.fromisoformat(a.replace("Z", "+00:00"))
    bb = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return (bb - aa).total_seconds()


def evaluate(conn: sqlite3.Connection, *, since: datetime, window_hours: int) -> dict[str, Any]:
    until = since + timedelta(hours=window_hours)
    checks: dict[str, dict[str, Any]] = {}

    light_rows = list(conn.execute(
        "SELECT b.brief_id, b.generated_ts, e.ingested_ts "
        "FROM briefs b JOIN events e ON e.event_id = b.trigger_event_id "
        "WHERE b.mode = 'event_alert_light' AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))
    latencies = [_seconds(r["ingested_ts"], r["generated_ts"]) for r in light_rows]
    p95 = _percentile(latencies, 0.95) if latencies else 0.0
    checks["light_alert_latency"] = {
        "pass": bool(light_rows) and p95 <= 300,
        "detail": f"{len(light_rows)} light alerts, p95={p95:.1f}s",
    }

    delivered_light = conn.execute(
        "SELECT COUNT(*) FROM briefs b JOIN deliveries d ON d.brief_id = b.brief_id "
        "WHERE b.mode = 'event_alert_light' "
        "AND d.status IN ('sent', 'skipped') "
        "AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]
    checks["light_delivery_audit"] = {
        "pass": delivered_light >= len(light_rows),
        "detail": f"{delivered_light}/{len(light_rows)} light alerts have sent/skipped delivery rows",
    }

    lineage = conn.execute(
        "SELECT COUNT(*) FROM brief_actions a "
        "JOIN queue_jobs q ON q.job_id = a.result_job_id "
        "JOIN briefs full ON full.brief_id = a.result_brief_id "
        "WHERE a.action_type = 'run_full_study' "
        "AND a.state = 'accepted' "
        "AND q.state = 'done' "
        "AND full.mode = 'event_alert' "
        "AND a.responded_at BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]
    accepted = conn.execute(
        "SELECT COUNT(*) FROM brief_actions "
        "WHERE action_type = 'run_full_study' "
        "AND state = 'accepted' "
        "AND responded_at BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]
    checks["approval_lineage"] = {
        "pass": accepted >= 1 and lineage == accepted,
        "detail": f"{lineage}/{accepted} accepted actions completed a done job and full brief",
    }

    full_delivered = conn.execute(
        "SELECT COUNT(*) FROM briefs b JOIN deliveries d ON d.brief_id = b.brief_id "
        "WHERE b.mode = 'event_alert' "
        "AND b.parent_brief_id IS NOT NULL "
        "AND d.status IN ('sent', 'skipped') "
        "AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]
    checks["full_brief_delivery"] = {
        "pass": full_delivered >= lineage,
        "detail": f"{full_delivered}/{lineage} full briefs have sent/skipped delivery rows",
    }

    errors = conn.execute(
        "SELECT COUNT(*) FROM queue_jobs WHERE state = 'error' "
        "AND enqueued_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]
    checks["worker_errors"] = {
        "pass": errors == 0,
        "detail": f"{errors} queue job errors",
    }

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "checks": checks,
        "pass": all(c["pass"] for c in checks.values()),
    }
```

Add `main()` and markdown rendering after tests pass; keep `evaluate()` pure and testable.

- [ ] **Step 4: Run combined gate unit tests**

Run:

```bash
pytest tests/scripts/test_f4_f5_exit_gate.py -q
```

Expected: PASS.

- [ ] **Step 5: Update existing F4/F5 gate scripts**

Make `scripts/f4_exit_gate.py` call or reference `scripts/f4_f5_exit_gate.py` for the combined gate. Update `scripts/f5_exit_gate.py` so event alert checks include:

```sql
b.mode IN ('event_alert_light', 'event_alert')
```

where appropriate, and require full `event_alert` briefs for post-approval checks.

- [ ] **Step 6: Add smoke test for synthetic combined flow**

Create `tests/smoke/test_f4_f5_combined_gate.py` that uses mocks for the LLM and secretary graph runner, then verifies the combined evaluator passes. Reuse the data seeding from `tests/scripts/test_f4_f5_exit_gate.py`.

- [ ] **Step 7: Run gate tests**

Run:

```bash
pytest tests/scripts/test_f4_f5_exit_gate.py tests/smoke/test_f4_f5_combined_gate.py tests/scripts/test_f5_exit_gate.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scripts/f4_f5_exit_gate.py scripts/f4_exit_gate.py scripts/f5_exit_gate.py tests/scripts/test_f4_f5_exit_gate.py tests/smoke/test_f4_f5_combined_gate.py tests/scripts/test_f5_exit_gate.py
git commit -m "feat(gates): add combined F4 F5 approval-delivery exit gate"
```

---

## Task 14: Documentation and Operator Runbook

**Files:**
- Modify: `README.md`
- Create or modify: `docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md`
- Modify: `docs/superpowers/specs/2026-06-01-iic-forge-09-f4-approval-gate-design.md`
- Modify: `docs/superpowers/specs/2026-05-27-iic-forge-08-f5-delivery-operations-design.md`

- [ ] **Step 1: Update README architecture section**

Document this default flow:

```text
triaged event -> strict alert evaluator -> light alert -> user approval
-> one balanced enriched TradingAgents graph -> full brief + analysis pack
-> secretary delivery -> optional directed follow-up using reusable pack
```

Also document that committee mode is explicit:

```text
Committee mode runs value/momentum/macro profiles and should be used only when
the user asks for comparison or disagreement analysis.
```

- [ ] **Step 2: Update phase status**

Clarify that F2 was recovered from an unmerged branch into current `main` only after Task 12 is complete. Before Task 12 lands, do not claim F2 is present on `main`.

- [ ] **Step 3: Add operator gate command**

Document:

```bash
python scripts/f4_f5_exit_gate.py --since 2026-06-03T09:00:00Z --window-hours 12
```

The artifact must include:

- light-alert latency
- alert evaluation pass/reject counts
- delivery audit counts
- accepted approval lineage
- worker errors
- full-brief delivery
- cost/cache summary
- operator false-positive sample sign-off

- [ ] **Step 4: Run docs grep for stale wording**

Run:

```bash
rg -n "Three persona investment teams|run_personas_parallel|event_alert only|F2.*not built" README.md docs tradingagents
```

Expected: any remaining hits are either historical artifacts or explicitly marked legacy/committee-only.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md docs/superpowers/specs/2026-06-01-iic-forge-09-f4-approval-gate-design.md docs/superpowers/specs/2026-05-27-iic-forge-08-f5-delivery-operations-design.md
git commit -m "docs: document F4 F5 persona-cost redesign"
```

---

## Task 15: Final Verification Matrix

**Files:**
- Read/verify only

- [ ] **Step 1: Run focused unit suites**

Run:

```bash
pytest tests/personas tests/secretary tests/orchestrator tests/delivery tests/analysis_pack tests/scripts -q
```

Expected: PASS.

- [ ] **Step 2: Run smoke suites**

Run:

```bash
pytest tests/smoke -q
```

Expected: PASS.

- [ ] **Step 3: Run backtest suite**

Run:

```bash
pytest tests/backtest -q
```

Expected: PASS once Task 12 has recovered F2.

- [ ] **Step 4: Run full test suite**

Run:

```bash
pytest -q
```

Expected: PASS. If live/network tests exist, isolate them behind existing markers rather than letting them hit real APIs.

- [ ] **Step 5: Confirm `.env` was not touched**

Run:

```bash
git status --short -- .env
```

Expected: no output.

- [ ] **Step 6: Confirm F2 branch was not merged wholesale**

Run:

```bash
git diff --name-status origin/feat/iic-forge-05-f2 -- docs tradingagents scripts tests | head
```

Expected: do not use this output as a merge target. It is only a sanity check that current work was selective and did not replace F3/F4/F5 docs/scripts from the old branch.

- [ ] **Step 7: Commit any final test/doc fixes**

```bash
git add README.md docs tradingagents tests scripts cli
git commit -m "test: verify persona-cost redesign gates"
```

Skip this commit if there are no changes after verification.

---

## Exit Criteria

- Default approved event analysis creates one full `event_alert` study run using `balanced` persona injection, not one graph per value/momentum/macro profile.
- Explicit committee mode still works when configured or requested.
- F4 light alerts pass a structured quality evaluator in addition to salience and ticker confidence.
- `event_alert_light` delivery respects quiet hours and records `sent`, `skipped`, or `failed`.
- Accepted `run_full_study` actions link to `queue_jobs.job_id` and then to the produced full brief.
- Full event-alert briefs create analysis packs.
- Directed follow-ups can reuse a parent analysis pack.
- Dynamic retrieval timestamps are removed from prompt-visible dataflow text.
- F2 backtest implementation is present on current branch through selective restore, not direct merge.
- Combined F4/F5 gate can prove light alert -> delivery -> approval -> job -> full brief -> delivery.
- `.env` remains untouched.

## Self-Review Notes

- Spec coverage: persona architecture, F4 strictness, F5 lineage/delivery, analysis-pack reuse, token-cache hygiene, F2 recovery, docs, and exit gates are each mapped to tasks.
- Placeholder scan: no task uses open-ended "handle later" language; optional future deeper memoization is explicitly outside the required V1 implementation.
- Type consistency: `analysis_pack_id`, `result_job_id`, `dispatched_ts`, and `alert_evaluations` are named consistently across schema, store helpers, and tests.
