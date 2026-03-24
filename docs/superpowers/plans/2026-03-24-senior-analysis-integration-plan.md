# Senior Analysis Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate selected upstream PR capabilities, add senior underwriting roles for stocks, merge the full Polymarket module, and standardize final outputs under a chief-analyst summary layer without touching the current dirty `main` checkout.

**Architecture:** Work in isolated in-repo worktrees on a branch family. First stabilize shared stock infrastructure from upstream PRs, then add structured senior stock roles, then integrate the full Polymarket product in parallel, and finally unify outputs with a chief-analyst terminal layer. Prefer salvaging behavior over replaying upstream diffs literally.

**Tech Stack:** Python 3.11, LangGraph, LangChain, Typer CLI, pytest, markdown report generation, optional frontend/API surfaces from upstream PRs.

---

## File Structure

### Existing files to modify repeatedly

- `tradingagents/default_config.py`
  - Global config, routing, analyst toggles, debate settings
- `tradingagents/graph/setup.py`
  - Node wiring and graph order
- `tradingagents/graph/trading_graph.py`
  - Tool node construction, graph init, shared LLM setup
- `tradingagents/agents/utils/agent_states.py`
  - Shared graph state and new structured report fields
- `tradingagents/agents/utils/agent_utils.py`
  - Shared helper/tool imports
- `cli/main.py`
  - CLI entry flow and reporting
- `cli/utils.py`
  - LLM selection, analyst selection, mode selection

### Existing files likely touched by stock-upstream salvage

- `tradingagents/agents/analysts/fundamentals_analyst.py`
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/analysts/social_media_analyst.py`
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/managers/portfolio_manager.py`
- `tradingagents/graph/conditional_logic.py`
- `README.md`

### New files expected from stock-upstream salvage

- `tradingagents/dataflows/macro_utils.py`
- `tradingagents/agents/analysts/macro_analyst.py`
- `tradingagents/agents/utils/macro_data_tools.py`
- `tradingagents/agents/analysts/factor_rule_analyst.py`
- `tradingagents/agents/utils/factor_rules.py`
- `tradingagents/examples/factor_rules.json`
- `tradingagents/agents/utils/social_data_tools.py`
- `tradingagents/dataflows/ttm_analysis.py`
- `tradingagents/dataflows/peer_comparison.py`
- `tradingagents/dataflows/macro_regime.py`

### New files expected for senior stock roles

- `tradingagents/agents/analysts/valuation_analyst.py`
- `tradingagents/agents/analysts/segment_analyst.py`
- `tradingagents/agents/analysts/scenario_catalyst_analyst.py`
- `tradingagents/agents/analysts/position_sizing_analyst.py`
- `tradingagents/agents/utils/valuation_tools.py`
- `tradingagents/agents/utils/segment_tools.py`
- `tradingagents/agents/utils/scenario_tools.py`
- `tradingagents/agents/utils/sizing_tools.py`

### New files expected for chief analyst

- `tradingagents/agents/managers/chief_analyst.py`
- `tests/test_chief_analyst.py`

### New files expected from Polymarket integration

- `tradingagents/prediction_market/` subtree from upstream `#432`
- `POLYMARKET.md`

### Tests to add or expand

- `tests/test_llm_routing.py`
- `tests/test_macro_analyst.py`
- `tests/test_social_data_tools.py`
- `tests/test_factor_rules.py`
- `tests/test_ttm_analysis.py`
- `tests/test_peer_comparison.py`
- `tests/test_macro_regime.py`
- `tests/test_stock_role_wiring.py`
- `tests/test_valuation_analyst.py`
- `tests/test_segment_analyst.py`
- `tests/test_scenario_catalyst_analyst.py`
- `tests/test_position_sizing_analyst.py`
- `tests/test_polymarket_*`

---

### Task 1: Create branch family and clean worktree baseline

**Files:**
- Modify: `.git/info/exclude`
- Create: `.worktrees/integration-upstream-stock/`
- Create later: `.worktrees/integration-senior-stock-roles/`
- Create later: `.worktrees/integration-polymarket-full/`
- Create later: `.worktrees/integration-chief-analyst-final/`
- Create later: `.worktrees/integration-final/`

- [ ] **Step 1: Verify `.worktrees/` is locally ignored**

Run: `git -C /Users/garrick/codes/TradingAgents check-ignore -v .worktrees/.ignore-check`
Expected: `.git/info/exclude` reports `.worktrees/`

- [ ] **Step 2: Verify clean baseline in first worktree**

Run: `cd /Users/garrick/codes/TradingAgents/.worktrees/integration-upstream-stock && /Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q`
Expected: PASS on current baseline suite

- [ ] **Step 3: Add remaining worktrees as phases begin**

Run:
```bash
git -C /Users/garrick/codes/TradingAgents worktree add .worktrees/integration-senior-stock-roles -b integration/senior-stock-roles integration/upstream-stock
git -C /Users/garrick/codes/TradingAgents worktree add .worktrees/integration-polymarket-full -b integration/polymarket-full origin/main
git -C /Users/garrick/codes/TradingAgents worktree add .worktrees/integration-chief-analyst-final -b integration/chief-analyst-final integration/senior-stock-roles
git -C /Users/garrick/codes/TradingAgents worktree add .worktrees/integration-final -b integration/final integration/chief-analyst-final
```
Expected: each worktree checks out a dedicated branch cleanly

- [ ] **Step 4: Commit only if setup changes beyond local exclude are needed**

Run: `git status --short`
Expected: no tracked-file modifications in repo root checkout

### Task 2: Integrate role-based LLM routing from `#401`

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `cli/utils.py`
- Modify: `cli/main.py`
- Test: `tests/test_llm_routing.py`

- [ ] **Step 1: Write the failing routing test**

```python
def test_role_specific_llm_config_overrides_default():
    config = {
        "llm_routing": {
            "default": {"provider": "openai", "model": "gpt-5-mini"},
            "roles": {"portfolio_manager": {"provider": "openai", "model": "gpt-5.2"}},
        }
    }
    # build graph and assert portfolio manager resolves the override
```

- [ ] **Step 2: Run targeted test to verify it fails**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_llm_routing.py`
Expected: FAIL because `llm_routing` is not wired yet

- [ ] **Step 3: Implement minimal routing support**

Add `llm_routing` config shape and role-resolution logic in `trading_graph.py` and `setup.py`, while preserving backward compatibility with `llm_provider`, `quick_think_llm`, and `deep_think_llm`.

- [ ] **Step 4: Re-run routing test**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_llm_routing.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tradingagents/graph/trading_graph.py tradingagents/graph/setup.py cli/utils.py cli/main.py tests/test_llm_routing.py
git commit -m "feat: add role-based llm routing"
```

### Task 3: Salvage Macro Analyst from `#244`

**Files:**
- Create: `tradingagents/dataflows/macro_utils.py`
- Create: `tradingagents/agents/analysts/macro_analyst.py`
- Create: `tradingagents/agents/utils/macro_data_tools.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/test_macro_analyst.py`

- [ ] **Step 1: Write failing tests for macro routing and graph wiring**
- [ ] **Step 2: Run them to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_macro_analyst.py`
Expected: FAIL because macro tools and node do not exist

- [ ] **Step 3: Add FRED-backed macro data module and analyst wiring**
- [ ] **Step 4: Re-run macro tests**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_macro_analyst.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/interface.py tradingagents/dataflows/macro_utils.py tradingagents/agents/analysts/macro_analyst.py tradingagents/agents/utils/macro_data_tools.py tradingagents/agents/__init__.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/test_macro_analyst.py
git commit -m "feat: add macro analyst"
```

### Task 4: Salvage social sentiment tool from `#399`

**Files:**
- Create: `tradingagents/agents/utils/social_data_tools.py`
- Modify: `tradingagents/agents/analysts/social_media_analyst.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `README.md`
- Test: `tests/test_social_data_tools.py`

- [ ] **Step 1: Write failing tests for optional sentiment tool gating**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_social_data_tools.py`
Expected: FAIL because `get_social_sentiment` is absent

- [ ] **Step 3: Add optional social sentiment tool and hook it into the social analyst**
- [ ] **Step 4: Re-run social tests**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_social_data_tools.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/social_data_tools.py tradingagents/agents/analysts/social_media_analyst.py tradingagents/graph/trading_graph.py tradingagents/agents/utils/agent_utils.py README.md tests/test_social_data_tools.py
git commit -m "feat: add optional social sentiment tool"
```

### Task 5: Salvage Factor Rule Analyst from `#359`

**Files:**
- Create: `tradingagents/agents/analysts/factor_rule_analyst.py`
- Create: `tradingagents/agents/utils/factor_rules.py`
- Create: `tradingagents/examples/factor_rules.json`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/graph/propagation.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/test_factor_rules.py`

- [ ] **Step 1: Write failing tests for factor rule loading and downstream state propagation**
- [ ] **Step 2: Run factor tests to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_factor_rules.py`
Expected: FAIL because factor-rule modules are absent

- [ ] **Step 3: Implement factor-rule analyst and downstream report plumbing**
- [ ] **Step 4: Re-run factor tests**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_factor_rules.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/factor_rule_analyst.py tradingagents/agents/utils/factor_rules.py tradingagents/examples/factor_rules.json tradingagents/agents/__init__.py tradingagents/agents/utils/agent_states.py tradingagents/agents/researchers/bull_researcher.py tradingagents/agents/researchers/bear_researcher.py tradingagents/agents/managers/research_manager.py tradingagents/agents/managers/portfolio_manager.py tradingagents/default_config.py tradingagents/graph/propagation.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/test_factor_rules.py
git commit -m "feat: add optional factor rule analyst"
```

### Task 6: Salvage medium-term positioning upgrade from `#392`

**Files:**
- Create: `tradingagents/dataflows/ttm_analysis.py`
- Create: `tradingagents/dataflows/peer_comparison.py`
- Create: `tradingagents/dataflows/macro_regime.py`
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/graph/conditional_logic.py`
- Modify: `tradingagents/graph/setup.py`
- Test: `tests/test_ttm_analysis.py`
- Test: `tests/test_peer_comparison.py`
- Test: `tests/test_macro_regime.py`
- Test: `tests/test_debate_rounds.py`

- [ ] **Step 1: Write failing tests for TTM, peer comparison, macro regime, and configurable rounds**
- [ ] **Step 2: Run targeted suite to verify failure**

Run:
```bash
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_ttm_analysis.py tests/test_peer_comparison.py tests/test_macro_regime.py tests/test_debate_rounds.py
```
Expected: FAIL on missing modules and config

- [ ] **Step 3: Implement medium-term positioning modules and wiring**
- [ ] **Step 4: Re-run targeted suite**

Run:
```bash
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_ttm_analysis.py tests/test_peer_comparison.py tests/test_macro_regime.py tests/test_debate_rounds.py
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/ttm_analysis.py tradingagents/dataflows/peer_comparison.py tradingagents/dataflows/macro_regime.py tradingagents/agents/analysts/fundamentals_analyst.py tradingagents/agents/analysts/market_analyst.py tradingagents/default_config.py tradingagents/graph/conditional_logic.py tradingagents/graph/setup.py tests/test_ttm_analysis.py tests/test_peer_comparison.py tests/test_macro_regime.py tests/test_debate_rounds.py
git commit -m "feat: add medium-term positioning upgrade"
```

### Task 7: Create structured senior stock report schema

**Files:**
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/graph/propagation.py`
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Test: `tests/test_stock_role_wiring.py`

- [ ] **Step 1: Write failing test for new structured fields in agent state**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_stock_role_wiring.py`
Expected: FAIL because state lacks senior-role fields

- [ ] **Step 3: Add machine-readable data slots for valuation, segment, scenario, sizing, and chief-analyst outputs**
- [ ] **Step 4: Re-run state wiring test**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_stock_role_wiring.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/agent_states.py tradingagents/graph/propagation.py tradingagents/agents/managers/research_manager.py tradingagents/agents/managers/portfolio_manager.py tests/test_stock_role_wiring.py
git commit -m "refactor: add structured stock underwriting state"
```

### Task 8: Add Valuation Analyst

**Files:**
- Create: `tradingagents/agents/analysts/valuation_analyst.py`
- Create: `tradingagents/agents/utils/valuation_tools.py`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/test_valuation_analyst.py`

- [ ] **Step 1: Write failing valuation-analyst test**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_valuation_analyst.py`
Expected: FAIL because valuation role is absent

- [ ] **Step 3: Implement valuation analyst with structured `valuation_data` output**
- [ ] **Step 4: Re-run valuation test**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_valuation_analyst.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/valuation_analyst.py tradingagents/agents/utils/valuation_tools.py tradingagents/agents/__init__.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/test_valuation_analyst.py
git commit -m "feat: add valuation analyst"
```

### Task 9: Add Segment Analyst

**Files:**
- Create: `tradingagents/agents/analysts/segment_analyst.py`
- Create: `tradingagents/agents/utils/segment_tools.py`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/test_segment_analyst.py`

- [ ] **Step 1: Write failing segment-analyst test**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_segment_analyst.py`
Expected: FAIL because segment role is absent

- [ ] **Step 3: Implement segment analyst with structured `segment_data` output**
- [ ] **Step 4: Re-run segment test**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_segment_analyst.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/segment_analyst.py tradingagents/agents/utils/segment_tools.py tradingagents/agents/__init__.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/test_segment_analyst.py
git commit -m "feat: add segment analyst"
```

### Task 10: Add Scenario & Catalyst Analyst

**Files:**
- Create: `tradingagents/agents/analysts/scenario_catalyst_analyst.py`
- Create: `tradingagents/agents/utils/scenario_tools.py`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/test_scenario_catalyst_analyst.py`

- [ ] **Step 1: Write failing scenario/catalyst test**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_scenario_catalyst_analyst.py`
Expected: FAIL because scenario role is absent

- [ ] **Step 3: Implement scenario/catalyst analyst with structured `scenario_catalyst_data` output**
- [ ] **Step 4: Re-run scenario test**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_scenario_catalyst_analyst.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/scenario_catalyst_analyst.py tradingagents/agents/utils/scenario_tools.py tradingagents/agents/__init__.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/test_scenario_catalyst_analyst.py
git commit -m "feat: add scenario and catalyst analyst"
```

### Task 11: Add Position Sizing Analyst

**Files:**
- Create: `tradingagents/agents/analysts/position_sizing_analyst.py`
- Create: `tradingagents/agents/utils/sizing_tools.py`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/test_position_sizing_analyst.py`

- [ ] **Step 1: Write failing position-sizing test**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_position_sizing_analyst.py`
Expected: FAIL because sizing role is absent

- [ ] **Step 3: Implement position-sizing analyst with structured `position_sizing_data` output**
- [ ] **Step 4: Re-run sizing test**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_position_sizing_analyst.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/position_sizing_analyst.py tradingagents/agents/utils/sizing_tools.py tradingagents/agents/__init__.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py tests/test_position_sizing_analyst.py
git commit -m "feat: add position sizing analyst"
```

### Task 12: Upgrade stock synthesis to consume structured outputs

**Files:**
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Test: `tests/test_stock_role_wiring.py`

- [ ] **Step 1: Extend failing tests to assert downstream roles consume structured fields**
- [ ] **Step 2: Run tests to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_stock_role_wiring.py`
Expected: FAIL because downstream prompts ignore structured data

- [ ] **Step 3: Refactor researcher, risk, and manager prompts to prioritize numeric/structured fields**
- [ ] **Step 4: Re-run stock wiring tests**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_stock_role_wiring.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/researchers/bull_researcher.py tradingagents/agents/researchers/bear_researcher.py tradingagents/agents/managers/research_manager.py tradingagents/agents/risk_mgmt/aggressive_debator.py tradingagents/agents/risk_mgmt/conservative_debator.py tradingagents/agents/risk_mgmt/neutral_debator.py tradingagents/agents/managers/portfolio_manager.py tests/test_stock_role_wiring.py
git commit -m "refactor: consume structured stock underwriting outputs"
```

### Task 13: Integrate full Polymarket module from `#432`

**Files:**
- Create: `tradingagents/prediction_market/` subtree
- Modify: `cli/main.py`
- Modify: `cli/models.py`
- Modify: `cli/utils.py`
- Create: `POLYMARKET.md`
- Test: `tests/test_polymarket_cli.py`
- Test: `tests/test_polymarket_graph.py`

- [ ] **Step 1: In the `integration/polymarket-full` worktree, write failing tests for Polymarket mode and graph init**
- [ ] **Step 2: Run tests to verify failure**

Run:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-polymarket-full
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_polymarket_cli.py tests/test_polymarket_graph.py
```
Expected: FAIL because Polymarket mode is absent

- [ ] **Step 3: Salvage `#432` as a parallel product module**
- [ ] **Step 4: Re-run Polymarket tests**

Run:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-polymarket-full
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_polymarket_cli.py tests/test_polymarket_graph.py
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/prediction_market cli/main.py cli/models.py cli/utils.py POLYMARKET.md tests/test_polymarket_cli.py tests/test_polymarket_graph.py
git commit -m "feat: add polymarket analysis module"
```

### Task 14: Salvage Chief Analyst from `#452`

**Files:**
- Create: `tradingagents/agents/managers/chief_analyst.py`
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `cli/main.py`
- Possibly modify frontend/API files if adopted from upstream branch later
- Test: `tests/test_chief_analyst.py`

- [ ] **Step 1: Write failing chief-analyst summary test**
- [ ] **Step 2: Run test to verify failure**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_chief_analyst.py`
Expected: FAIL because chief analyst is absent

- [ ] **Step 3: Implement chief-analyst terminal node and structured final summary schema**
- [ ] **Step 4: Re-run chief-analyst tests**

Run: `/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_chief_analyst.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/managers/chief_analyst.py tradingagents/agents/utils/agent_states.py tradingagents/graph/setup.py tradingagents/graph/trading_graph.py cli/main.py tests/test_chief_analyst.py
git commit -m "feat: add chief analyst summary layer"
```

### Task 15: Merge validated Polymarket branch into chief-analyst branch

**Files:**
- Modify only conflict files after branch merge
- Test: stock and Polymarket smoke suites

- [ ] **Step 1: Merge `integration/polymarket-full` into `integration/chief-analyst-final`**

Run:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-chief-analyst-final
git merge integration/polymarket-full
```
Expected: merge with manageable conflicts

- [ ] **Step 2: Resolve conflicts in shared CLI/config/reporting files**
- [ ] **Step 3: Run mixed smoke suite**

Run:
```bash
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q tests/test_chief_analyst.py tests/test_stock_role_wiring.py tests/test_polymarket_cli.py tests/test_polymarket_graph.py
```
Expected: PASS

- [ ] **Step 4: Commit merge-resolution changes**

```bash
git add .
git commit -m "merge: reconcile polymarket with chief analyst output"
```

### Task 16: Final stabilization and validation

**Files:**
- Modify: any remaining conflict files
- Modify: `README.md`
- Modify: docs as needed

- [ ] **Step 1: Merge `integration/chief-analyst-final` into `integration/final`**
- [ ] **Step 2: Run full available pytest suite**

Run:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-final
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m pytest -q
```
Expected: PASS

- [ ] **Step 3: Run compile check**

Run:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-final
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m compileall tradingagents tests
```
Expected: PASS without syntax errors

- [ ] **Step 4: Run CLI smoke checks**

Run stock smoke:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-final
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m cli.main --help
```

Run Polymarket smoke:
```bash
cd /Users/garrick/codes/TradingAgents/.worktrees/integration-final
/Users/garrick/anaconda3/envs/tradingagents/bin/python -m cli.main
```
Expected: stock and Polymarket modes are reachable without immediate crashes

- [ ] **Step 5: Commit final stabilization**

```bash
git add .
git commit -m "feat: complete senior analysis and polymarket integration"
```

### Task 17: Push branch family to fork

**Files:**
- No file edits

- [ ] **Step 1: Push each integration branch to `guanghan`**

Run:
```bash
git -C /Users/garrick/codes/TradingAgents/.worktrees/integration-upstream-stock push -u guanghan integration/upstream-stock
git -C /Users/garrick/codes/TradingAgents/.worktrees/integration-senior-stock-roles push -u guanghan integration/senior-stock-roles
git -C /Users/garrick/codes/TradingAgents/.worktrees/integration-polymarket-full push -u guanghan integration/polymarket-full
git -C /Users/garrick/codes/TradingAgents/.worktrees/integration-chief-analyst-final push -u guanghan integration/chief-analyst-final
git -C /Users/garrick/codes/TradingAgents/.worktrees/integration-final push -u guanghan integration/final
```
Expected: all branches are available on the fork

- [ ] **Step 2: Verify remote branch list**

Run: `git ls-remote --heads guanghan`
Expected: integration branches visible on fork

---

## Verification Notes

- Prefer targeted tests after each phase and a full suite only at the end.
- If additional linters or type checkers are installed later, run them in the final branch before declaring completion.
- If any upstream PR cannot be applied cleanly, salvage behavior into the current file layout rather than replaying the upstream diff mechanically.
