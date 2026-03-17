# Implementation Plan: Medium-Term Positioning Upgrade

## Lead Architect Overview

Four objectives to upgrade TradingAgents for medium-term (1–3 month) positioning:
1. **Agentic Debate** — Increase debate rounds to 2–3
2. **Fundamental Data** — Extend look-back to 8 quarters with TTM trend computation
3. **Relative Performance** — Sector & peer comparison tools
4. **Macro Regime Flag** — Classify market as risk-on / risk-off / transition

---

## Step 1: Agentic Debate — Increase Rounds (Architect + API Integrator)

**Assigned to: API Integrator Agent**
**Risk: LOW** — Config-only change, conditional logic already supports arbitrary round counts.

### Changes:
- **File:** `tradingagents/default_config.py`
  - Change `"max_debate_rounds": 1` → `"max_debate_rounds": 2`
  - Change `"max_risk_discuss_rounds": 1` → `"max_risk_discuss_rounds": 2`

- **File:** `tradingagents/graph/trading_graph.py` (line 146)
  - Pass config values to `ConditionalLogic`:
    ```python
    self.conditional_logic = ConditionalLogic(
        max_debate_rounds=self.config.get("max_debate_rounds", 2),
        max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 2),
    )
    ```
  - **NOTE:** Currently `ConditionalLogic()` is called with no args, so it uses its own defaults of 1. The config values are never actually wired in. This is a bug fix.

### Verification:
- Investment debate: count threshold = `2 * 2 = 4` → Bull speaks 2×, Bear speaks 2× before judge
- Risk debate: count threshold = `3 * 2 = 6` → Each of 3 analysts speaks 2× before judge
- `max_recur_limit` of 100 is sufficient (was 100, worst case ~20 graph steps)

---

## Step 2: Fundamental Data — 8-Quarter TTM Trend (API Integrator + Economist)

**Assigned to: API Integrator (data layer) + Economist (TTM computation logic)**
**Risk: MEDIUM** — Requires new data tool + prompt update + TTM computation module.

### 2A: New TTM Computation Module (Economist Agent)

- **New file:** `tradingagents/dataflows/ttm_analysis.py`
  - `compute_ttm_metrics(income_df, balance_df, cashflow_df) -> dict`
    - Sum last 4 quarters of income stmt for flow items (Revenue, Net Income, EBITDA, Operating Income, Gross Profit)
    - Use latest quarter for balance sheet (stock items: Total Assets, Total Debt, Equity)
    - Compute key ratios: Revenue Growth (QoQ and YoY), Margin trends (Gross, Operating, Net), ROE trend, Debt/Equity trend, FCF trend
  - `format_ttm_report(metrics: dict, ticker: str) -> str`
    - Markdown report with 8-quarter trend table + TTM summary + quarter-over-quarter trajectory

### 2B: New Tool — `get_ttm_analysis` (API Integrator Agent)

- **File:** `tradingagents/agents/utils/fundamental_data_tools.py`
  - Add new `@tool` function `get_ttm_analysis(ticker, curr_date) -> str`
  - Internally calls existing vendor-routed `get_income_statement`, `get_balance_sheet`, `get_cashflow` with `freq="quarterly"`
  - Passes raw data to `compute_ttm_metrics()` and `format_ttm_report()`

- **File:** `tradingagents/agents/utils/agent_utils.py`
  - Export `get_ttm_analysis` tool

### 2C: Update Fundamentals Analyst Prompt (Economist Agent)

- **File:** `tradingagents/agents/analysts/fundamentals_analyst.py`
  - Add `get_ttm_analysis` to tools list
  - Update system prompt from "past week" to:
    > "You are a researcher tasked with analyzing fundamental information covering the last 8 quarters (2 years) for a company. First call `get_ttm_analysis` to obtain a Trailing Twelve Months (TTM) trend report including revenue growth, margin trajectories, and key ratio trends. Then supplement with `get_fundamentals` for the latest snapshot. Write a comprehensive report covering multi-quarter trends, not just the most recent filing."

- **File:** `tradingagents/graph/trading_graph.py` — `_create_tool_nodes()`
  - Add `get_ttm_analysis` to the `"fundamentals"` ToolNode

### 2D: Data Layer — Ensure 8 Quarters Available

- **yfinance:** `ticker.quarterly_income_stmt` returns up to 5 quarters. To get 8, we need to combine quarterly + annual or make 2 calls. Actually, yfinance returns the last 4-5 quarters by default. We'll need to fetch 2+ years of data.
  - Approach: Call `ticker.quarterly_income_stmt` which returns available quarters (typically 4-5). Also call `ticker.income_stmt` (annual) for older periods. Combine to reconstruct 8 quarters.
  - **Alternative (preferred):** yfinance `ticker.get_income_stmt(freq="quarterly", as_dict=False)` can return more data. Test this.
  - **Fallback:** Alpha Vantage INCOME_STATEMENT endpoint returns up to 20 quarterly reports — use this as the configured vendor for TTM.

- **File:** `tradingagents/default_config.py`
  - Add to `tool_vendors`: `"get_ttm_analysis": "alpha_vantage,yfinance"` to prefer Alpha Vantage for richer quarterly history

### Data Source Assessment:
| Source | Quarters Available | Notes |
|--------|-------------------|-------|
| yfinance `quarterly_income_stmt` | 4-5 | Limited but free |
| Alpha Vantage `INCOME_STATEMENT` | Up to 20 quarterly | Best option, needs API key |
| Alpha Vantage `BALANCE_SHEET` | Up to 20 quarterly | Same |
| Alpha Vantage `CASH_FLOW` | Up to 20 quarterly | Same |

---

## Step 3: Relative Performance — Sector & Peer Comparison (API Integrator + Economist)

**Assigned to: API Integrator (tools) + Economist (comparison logic)**
**Risk: MEDIUM** — New tools leveraging existing scanner infrastructure.

### 3A: New Peer Comparison Module (Economist Agent)

- **New file:** `tradingagents/dataflows/peer_comparison.py`
  - `get_sector_peers(ticker) -> list[str]`
    - Use yfinance `Ticker.info["sector"]` to identify sector
    - Return top 5-8 peers from same sector (use existing `_SECTOR_TICKERS` mapping from `alpha_vantage_scanner.py`, or yfinance Sector.top_companies)
  - `compute_relative_performance(ticker, peers, period="6mo") -> str`
    - Download price history for ticker + peers via `yf.download()`
    - Compute: 1-week, 1-month, 3-month, 6-month returns for each
    - Rank ticker among peers
    - Compute ticker's alpha vs sector ETF
    - Return markdown table with relative positioning

### 3B: New Tools — `get_peer_comparison` and `get_sector_relative` (API Integrator)

- **File:** `tradingagents/agents/utils/fundamental_data_tools.py`
  - `get_peer_comparison(ticker, curr_date) -> str` — @tool
    - Calls `get_sector_peers()` and `compute_relative_performance()`
    - Returns ranked peer table with ticker highlighted
  - `get_sector_relative(ticker, curr_date) -> str` — @tool
    - Compares ticker vs its sector ETF over multiple time frames
    - Returns outperformance/underperformance metrics

- **File:** `tradingagents/agents/utils/agent_utils.py`
  - Export both new tools

### 3C: Wire Into Fundamentals Analyst (API Integrator)

- **File:** `tradingagents/agents/analysts/fundamentals_analyst.py`
  - Add `get_peer_comparison` and `get_sector_relative` to tools list
  - Update prompt to instruct: "Also analyze how the company performs relative to sector peers and its sector ETF benchmark over 1-week, 1-month, 3-month, and 6-month periods."

- **File:** `tradingagents/graph/trading_graph.py` — `_create_tool_nodes()`
  - Add both tools to `"fundamentals"` ToolNode

### 3D: Vendor Routing

- These tools use yfinance directly (no Alpha Vantage endpoint for peer comparison)
- No vendor routing needed — direct yfinance calls inside the module
- Register in `TOOLS_CATEGORIES` under `"fundamental_data"` for consistency

---

## Step 4: Macro Regime Flag (Economist Agent)

**Assigned to: Economist Agent**
**Risk: MEDIUM** — New module + new state field + integration into Research Manager.

### 4A: Macro Regime Classifier Module (Economist)

- **New file:** `tradingagents/dataflows/macro_regime.py`
  - `classify_macro_regime(curr_date: str = None) -> dict`
    - Returns: `{"regime": "risk-on"|"risk-off"|"transition", "confidence": float, "signals": dict, "summary": str}`
  - Signal sources (all via yfinance — free, no API key needed):
    1. **VIX level**: `yf.Ticker("^VIX")` → <16 risk-on, 16-25 transition, >25 risk-off
    2. **VIX trend**: 5-day vs 20-day SMA — rising = risk-off signal
    3. **Credit spread proxy**: `yf.Ticker("HYG")` vs `yf.Ticker("LQD")` — HYG/LQD ratio declining = risk-off
    4. **Yield curve proxy**: `yf.Ticker("TLT")` (20yr) vs `yf.Ticker("SHY")` (1-3yr) — TLT outperforming = risk-off (flight to safety)
    5. **Market breadth**: S&P 500 (`^GSPC`) above/below 200-SMA
    6. **Sector rotation signal**: Defensive sectors (XLU, XLP, XLV) outperforming cyclicals (XLY, XLK, XLI) = risk-off
  - Scoring: Each signal contributes -1 (risk-off), 0 (neutral), or +1 (risk-on). Aggregate:
    - Sum >= 3: "risk-on"
    - Sum <= -3: "risk-off"
    - Otherwise: "transition"
  - `format_macro_report(regime_data: dict) -> str`
    - Markdown report with signal breakdown, regime classification, and confidence level

### 4B: New Tool — `get_macro_regime` (API Integrator)

- **File:** `tradingagents/agents/utils/fundamental_data_tools.py` (or new `macro_tools.py`)
  - `get_macro_regime(curr_date) -> str` — @tool
  - Calls `classify_macro_regime()` and `format_macro_report()`

- **File:** `tradingagents/agents/utils/agent_utils.py`
  - Export `get_macro_regime`

### 4C: Add Macro Regime to Agent State

- **File:** `tradingagents/agents/utils/agent_states.py`
  - Add to `AgentState`:
    ```python
    macro_regime_report: Annotated[str, "Macro regime classification (risk-on/risk-off/transition)"]
    ```

### 4D: Wire Into Market Analyst (API Integrator)

- **File:** `tradingagents/agents/analysts/market_analyst.py`
  - Add `get_macro_regime` to tools list
  - Update prompt to include: "Before analyzing individual stock technicals, call `get_macro_regime` to determine the current market environment (risk-on, risk-off, or transition). Interpret all subsequent technical signals through this macro lens."
  - Return `macro_regime_report` in output dict

- **File:** `tradingagents/graph/trading_graph.py` — `_create_tool_nodes()`
  - Add `get_macro_regime` to `"market"` ToolNode

### 4E: Feed Macro Regime Into Downstream Agents

- **File:** `tradingagents/agents/managers/research_manager.py`
  - Add `macro_regime_report` to the `curr_situation` string that gets passed to the judge
  - Update prompt to reference macro regime in decision-making

- **File:** `tradingagents/agents/managers/risk_manager.py`
  - Include macro regime context in risk assessment prompt

- **File:** `tradingagents/graph/trading_graph.py` — `_log_state()`
  - Add `macro_regime_report` to logged state

---

## Step 5: Integration Tests (Tester Agent)

**Assigned to: Tester Agent**

### 5A: Test Debate Rounds — `tests/test_debate_rounds.py`
- Test `ConditionalLogic` with `max_debate_rounds=2`:
  - Verify bull/bear alternate correctly for 4 turns
  - Verify routing to "Research Manager" after count >= 4
- Test `ConditionalLogic` with `max_risk_discuss_rounds=2`:
  - Verify aggressive→conservative→neutral rotation for 6 turns
  - Verify routing to "Risk Judge" after count >= 6
- Test config values are properly wired from `TradingAgentsGraph` config to `ConditionalLogic`

### 5B: Test TTM Analysis — `tests/test_ttm_analysis.py`
- Unit test `compute_ttm_metrics()` with mock 8-quarter DataFrames
  - Verify TTM revenue = sum of last 4 quarters
  - Verify margin calculations
  - Verify QoQ and YoY growth rates
- Unit test `format_ttm_report()` output contains expected sections
- Integration test `get_ttm_analysis` tool with real ticker (mark `@pytest.mark.integration`)

### 5C: Test Peer Comparison — `tests/test_peer_comparison.py`
- Unit test `get_sector_peers()` returns valid tickers for known sectors
- Unit test `compute_relative_performance()` with mock price data
  - Verify correct return calculations
  - Verify ranking logic
- Integration test with real ticker (mark `@pytest.mark.integration`)

### 5D: Test Macro Regime — `tests/test_macro_regime.py`
- Unit test `classify_macro_regime()` with mocked yfinance data:
  - All risk-on signals → "risk-on"
  - All risk-off signals → "risk-off"
  - Mixed signals → "transition"
- Unit test `format_macro_report()` output format
- Unit test scoring edge cases (VIX at boundaries, missing data gracefully handled)
- Integration test with real market data (mark `@pytest.mark.integration`)

### 5E: Test Config Wiring — `tests/test_config_wiring.py`
- Test that `TradingAgentsGraph(config={...})` properly passes debate rounds to `ConditionalLogic`
- Test that new tools appear in the correct ToolNodes
- Test that new state fields exist in `AgentState`

---

## File Change Summary

| File | Action | Objective |
|------|--------|-----------|
| `tradingagents/default_config.py` | EDIT | #1 debate rounds, #2 tool vendor |
| `tradingagents/graph/trading_graph.py` | EDIT | #1 wire config, #2/#3/#4 add tools to ToolNodes, #4 log macro |
| `tradingagents/graph/conditional_logic.py` | NO CHANGE | Already supports arbitrary rounds |
| `tradingagents/agents/utils/agent_states.py` | EDIT | #4 add macro_regime_report |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | EDIT | #2/#3 new tools + prompt |
| `tradingagents/agents/analysts/market_analyst.py` | EDIT | #4 macro regime tool + prompt |
| `tradingagents/agents/managers/research_manager.py` | EDIT | #4 include macro in decision |
| `tradingagents/agents/managers/risk_manager.py` | EDIT | #4 include macro in risk assessment |
| `tradingagents/agents/utils/fundamental_data_tools.py` | EDIT | #2/#3 new tool functions |
| `tradingagents/agents/utils/agent_utils.py` | EDIT | #2/#3/#4 export new tools |
| `tradingagents/agents/__init__.py` | NO CHANGE | Tools don't need agent-level export |
| `tradingagents/dataflows/ttm_analysis.py` | NEW | #2 TTM computation |
| `tradingagents/dataflows/peer_comparison.py` | NEW | #3 peer comparison logic |
| `tradingagents/dataflows/macro_regime.py` | NEW | #4 macro regime classifier |
| `tradingagents/dataflows/interface.py` | EDIT | #2/#3 register new tools in TOOLS_CATEGORIES |
| `tests/test_debate_rounds.py` | NEW | #1 tests |
| `tests/test_ttm_analysis.py` | NEW | #2 tests |
| `tests/test_peer_comparison.py` | NEW | #3 tests |
| `tests/test_macro_regime.py` | NEW | #4 tests |
| `tests/test_config_wiring.py` | NEW | Integration wiring tests |

---

## Execution Order

1. **Step 1** (Debate Rounds) — Independent, can start immediately
2. **Step 4A** (Macro Regime Module) — Independent, can start in parallel
3. **Step 2A** (TTM Module) — Independent, can start in parallel
4. **Step 3A** (Peer Comparison Module) — Independent, can start in parallel
5. **Step 2B–2D** (TTM Integration) — Depends on 2A
6. **Step 3B–3D** (Peer Integration) — Depends on 3A
7. **Step 4B–4E** (Macro Integration) — Depends on 4A
8. **Step 5** (All Tests) — Depends on all above

Steps 1, 2A, 3A, 4A can all run in parallel.

---

## Risk Mitigation

- **yfinance quarterly data limit:** If yfinance returns <8 quarters, TTM module gracefully computes with available data and notes the gap. Alpha Vantage fallback provides full 20 quarters.
- **New state field (macro_regime_report):** Default empty string. All existing agents that don't produce it will leave it empty — no reducer conflicts.
- **Rate limits:** Macro regime and peer comparison both call yfinance which has no rate limit. Sector performance via Alpha Vantage is already rate-limited at 75/min.
- **Backward compatibility:** All changes are additive. `max_debate_rounds=1` still works. New tools are optional in prompts. `macro_regime_report` defaults to empty.
