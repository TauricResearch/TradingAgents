# Portfolio Graph Validation Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the portfolio graph reject contradictory analysis, enforce executable buy constraints, and prevent invalid downstream trades from scanner reports.

**Architecture:** Add deterministic validation at each graph boundary: final-decision parsing, scan-candidate admission, PM order schema, postcheck projection, and executor enforcement. The PM graph remains the same LangGraph topology, but the data contract becomes stricter so hallucinated or stale prose cannot become executable orders.

**Tech Stack:** Python 3, pytest, Pydantic, LangGraph, existing `tradingagents` portfolio modules.

---

## File Structure

- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/output_validation.py`
  - Owns final-decision structured extraction from prose.
  - Add explicit recommendation parsing that does not match substrings inside words like `selloff`.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_output_validation.py`
  - Regression tests for final decision action extraction.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`
  - Owns candidate admission, PM postcheck, cash sweep, and trade execution node wiring.
  - Add structured candidate consistency checks.
  - Require live buy prices in postcheck.
  - Enforce order guard fields before execution.
  - Make cash sweep respect configured portfolio caps.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`
  - Regression tests for candidate gating, missing live prices, max chase, and cash sweep.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/portfolio/pm_decision_agent.py`
  - Owns PM structured output schema and prompt.
  - Add executable order fields: `entry_price`, `limit_price`, `max_chase_price`, `order_type`, and `valid_as_of`.

- Create: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_pm_decision_schema.py`
  - Schema-level regression tests for required PM buy order fields.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/portfolio/trade_executor.py`
  - Owns final execution against the portfolio repository.
  - Reject BUYs that violate limit/max-chase/risk-level constraints.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_trade_executor.py`
  - Regression tests for executor order guard enforcement.

- Modify: `/Users/Ahmet/Repo/TradingAgents/agent_os/backend/routes/runs.py`
  - Owns run task lifecycle and rerun/resume controls.
  - Add lightweight protection against redundant rerun starts for the same active run node.

- Modify: `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_run_controls.py`
  - Regression tests for rerun/resume idempotency.

---

### Task 1: Fix Final Decision Action Inference

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/output_validation.py`
- Test: `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_output_validation.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_output_validation.py`:

```python
class TestFinalDecisionStructuredContract:
    def test_build_final_decision_structured_does_not_treat_selloff_as_sell(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        report = (
            "RIG experienced an energy selloff, but the final rating is Buy. "
            "Rating: Buy. Stop-loss at $3.80. Target price at $6.00."
        )

        structured = build_final_decision_structured(
            ticker="RIG",
            as_of_date="2026-04-28",
            final_decision=report,
        )

        assert structured["action"] == "BUY"

    def test_build_final_decision_structured_prefers_final_transaction_proposal(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        report = (
            "The bear case says sell if dayrates weaken. "
            "FINAL TRANSACTION PROPOSAL: **HOLD** until earnings confirm guidance."
        )

        structured = build_final_decision_structured(
            ticker="RIG",
            as_of_date="2026-04-28",
            final_decision=report,
        )

        assert structured["action"] == "HOLD"

    def test_build_final_decision_structured_uses_word_boundaries(self):
        from tradingagents.agents.utils.output_validation import build_final_decision_structured

        report = "The company completed a buyback. Rating: Hold."

        structured = build_final_decision_structured(
            ticker="AAPL",
            as_of_date="2026-04-28",
            final_decision=report,
        )

        assert structured["action"] == "HOLD"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest tests/unit/test_output_validation.py::TestFinalDecisionStructuredContract -v
```

Expected: at least one failure where the current implementation returns `SELL` for text containing `selloff` or chooses the wrong action because it scans unanchored prose.

- [ ] **Step 3: Replace `_infer_recommendation`**

In `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/output_validation.py`, replace the current `_infer_recommendation` function with:

```python
def _infer_recommendation(text: str) -> str:
    """Return BUY/SELL/HOLD from explicit decision fields, not incidental prose."""
    raw = str(text or "")
    patterns = [
        r"FINAL\s+TRANSACTION\s+PROPOSAL\s*:\s*\**\s*(BUY|SELL|HOLD)\b",
        r"FINAL\s+RECOMMENDATION\s*:\s*\**\s*(BUY|SELL|HOLD)\b",
        r"RECOMMENDATION\s*:\s*\**\s*(BUY|SELL|HOLD)\b",
        r"RATING\s*:\s*\**\s*(BUY|SELL|HOLD)\b",
        r"ACTION\s*:\s*\**\s*(BUY|SELL|HOLD)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    word_counts = {
        "BUY": len(re.findall(r"\bBUY\b", raw, re.IGNORECASE)),
        "SELL": len(re.findall(r"\bSELL\b", raw, re.IGNORECASE)),
        "HOLD": len(re.findall(r"\bHOLD\b", raw, re.IGNORECASE)),
    }
    if word_counts["BUY"] > word_counts["SELL"] and word_counts["BUY"] >= word_counts["HOLD"]:
        return "BUY"
    if word_counts["SELL"] > word_counts["BUY"] and word_counts["SELL"] >= word_counts["HOLD"]:
        return "SELL"
    if word_counts["HOLD"] > 0:
        return "HOLD"
    return "HOLD"
```

- [ ] **Step 4: Run the focused tests and verify pass**

Run:

```bash
pytest tests/unit/test_output_validation.py::TestFinalDecisionStructuredContract -v
```

Expected: all tests in `TestFinalDecisionStructuredContract` pass.

- [ ] **Step 5: Run the full output validation suite**

Run:

```bash
pytest tests/unit/test_output_validation.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tests/unit/test_output_validation.py
git commit -m "fix: parse final trade actions from explicit decision fields"
```

---

### Task 2: Reject Contradictory or Non-Buy Candidate Decisions

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`
- Test: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`

- [ ] **Step 1: Write the failing tests**

Append these tests near the existing candidate prioritization tests in `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`:

```python
def test_prioritize_candidates_rejects_structured_sell_even_when_prose_says_buy():
    setup = PortfolioGraphSetup(agents={}, config={})
    node = setup._make_prioritize_candidates_node()

    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {
                    "portfolio_id": "p1",
                    "name": "Main",
                    "cash": 100000.0,
                    "initial_cash": 100000.0,
                },
                "holdings": [],
            }
        ),
        "scan_summary": {"stocks_to_investigate": [{"ticker": "RIG"}]},
        "ticker_analyses": {
            "equity:RIG": {
                "analysis_status": "completed",
                "final_trade_decision": "Rating: Buy after the selloff.",
                "final_trade_decision_structured": {
                    "status": "completed",
                    "action": "SELL",
                },
            }
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    assert json.loads(result["prioritized_candidates"]) == []


def test_prioritize_candidates_keeps_completed_structured_buy():
    setup = PortfolioGraphSetup(agents={}, config={})
    node = setup._make_prioritize_candidates_node()

    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {
                    "portfolio_id": "p1",
                    "name": "Main",
                    "cash": 100000.0,
                    "initial_cash": 100000.0,
                },
                "holdings": [],
            }
        ),
        "scan_summary": {"stocks_to_investigate": [{"ticker": "RMAX"}]},
        "ticker_analyses": {
            "equity:RMAX": {
                "analysis_status": "completed",
                "final_trade_decision": "Rating: Buy with strict entry discipline.",
                "final_trade_decision_structured": {
                    "status": "completed",
                    "action": "BUY",
                },
            }
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    prioritized = json.loads(result["prioritized_candidates"])
    assert [candidate["ticker"] for candidate in prioritized] == ["RMAX"]
    assert prioritized[0]["candidate_final_trade_decision_structured"]["action"] == "BUY"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py::test_prioritize_candidates_rejects_structured_sell_even_when_prose_says_buy tests/portfolio/test_portfolio_setup.py::test_prioritize_candidates_keeps_completed_structured_buy -v
```

Expected: the first test fails because the current implementation admits a candidate based on prose alone.

- [ ] **Step 3: Add structured candidate helpers**

In `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`, replace `_analysis_has_deep_dive` with:

```python
def _analysis_has_deep_dive(analysis: Any) -> bool:
    """Return True when a ticker analysis has a completed deep-dive decision."""
    if not isinstance(analysis, dict):
        return False
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status:
        return status == "completed"
    return bool(str(analysis.get("final_trade_decision") or "").strip())
```

Then add this helper directly below it:

```python
def _structured_action_allows_candidate(analysis: dict[str, Any]) -> bool:
    """Only completed structured BUY decisions may become new buy candidates."""
    structured = analysis.get("final_trade_decision_structured") or {}
    if not isinstance(structured, dict):
        return False
    status = str(structured.get("status") or "").strip().lower()
    action = str(structured.get("action") or "").strip().upper()
    return status == "completed" and action == "BUY"
```

- [ ] **Step 4: Update candidate admission**

In `_completed_scan_candidates`, after the `_analysis_has_deep_dive(analysis)` check, insert this check and structured payload propagation:

```python
        if not _structured_action_allows_candidate(analysis):
            continue
        candidate["ticker"] = ticker
        candidate["instrument_key"] = instrument_key
        candidate["candidate_final_trade_decision_summary"] = str(
            analysis.get("final_trade_decision") or ""
        ).strip()
        candidate["candidate_final_trade_decision_structured"] = dict(
            analysis.get("final_trade_decision_structured") or {}
        )
        completed.append(candidate)
```

Remove the previous duplicate block that appended the candidate without checking `final_trade_decision_structured`.

- [ ] **Step 5: Run the focused tests and verify pass**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py::test_prioritize_candidates_rejects_structured_sell_even_when_prose_says_buy tests/portfolio/test_portfolio_setup.py::test_prioritize_candidates_keeps_completed_structured_buy -v
```

Expected: both tests pass.

- [ ] **Step 6: Update existing candidate tests**

Modify the existing `test_prioritize_candidates_only_uses_completed_ticker_analyses` and `test_prioritize_candidates_ignores_running_analyses_even_with_stray_decisions` fixtures so completed analyses include:

```python
"final_trade_decision_structured": {"status": "completed", "action": "BUY"}
```

For the incomplete or running analyses, use:

```python
"final_trade_decision_structured": {"status": "completed", "action": "BUY"}
```

The running analysis should still be rejected because `analysis_status` is `running`.

- [ ] **Step 7: Run the portfolio setup suite**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/graph/portfolio_setup.py tests/portfolio/test_portfolio_setup.py
git commit -m "fix: gate portfolio candidates on structured buy decisions"
```

---

### Task 3: Add Executable Buy Order Fields to PM Schema

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/portfolio/pm_decision_agent.py`
- Create: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_pm_decision_schema.py`

- [ ] **Step 1: Write the failing schema tests**

Create `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_pm_decision_schema.py`:

```python
import pytest

from tradingagents.agents.portfolio.pm_decision_agent import BuyOrder


def _valid_buy_order_payload():
    return {
        "ticker": "RMAX",
        "shares": 300.0,
        "entry_price": 9.94,
        "limit_price": 10.25,
        "max_chase_price": 10.25,
        "order_type": "limit",
        "valid_as_of": "2026-04-28",
        "price_target": 12.92,
        "stop_loss": 8.45,
        "take_profit": 12.92,
        "sector": "Real Estate",
        "rationale": "Merger spread only works below the max chase level.",
        "thesis": "Event-driven upside with strict execution discipline.",
        "macro_alignment": "Low duration exposure.",
        "memory_note": "Avoid chasing stale event spreads.",
        "position_sizing_logic": "Small starter position under portfolio caps.",
    }


def test_buy_order_requires_executable_price_fields():
    order = BuyOrder(**_valid_buy_order_payload())

    assert order.entry_price == 9.94
    assert order.limit_price == 10.25
    assert order.max_chase_price == 10.25
    assert order.order_type == "limit"
    assert order.valid_as_of == "2026-04-28"


def test_buy_order_rejects_missing_max_chase_price():
    payload = _valid_buy_order_payload()
    del payload["max_chase_price"]

    with pytest.raises(Exception):
        BuyOrder(**payload)
```

- [ ] **Step 2: Run the schema tests and verify failure**

Run:

```bash
pytest tests/portfolio/test_pm_decision_schema.py -v
```

Expected: tests fail because `BuyOrder` does not expose the new executable order fields.

- [ ] **Step 3: Update the `BuyOrder` schema**

In `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/portfolio/pm_decision_agent.py`, replace the `BuyOrder` class with:

```python
class BuyOrder(_PMBaseModel):
    """A fully justified buy order with executable entry and risk parameters."""

    ticker: str
    shares: float
    entry_price: float
    limit_price: float
    max_chase_price: float
    order_type: Literal["limit"]
    valid_as_of: str
    price_target: float
    stop_loss: float
    take_profit: float
    sector: str
    rationale: str
    thesis: str
    macro_alignment: str
    memory_note: str
    position_sizing_logic: str
```

- [ ] **Step 4: Update the PM prompt required field list**

In the `STRICT OUTPUT REQUIREMENTS` section for every BUY in `/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/portfolio/pm_decision_agent.py`, replace the BUY field bullets with:

```python
            "- ticker\n"
            "- shares\n"
            "- entry_price (numeric float; price used for sizing and risk/reward)\n"
            "- limit_price (numeric float; execution must not buy above this level)\n"
            "- max_chase_price (numeric float; same as or lower than limit_price)\n"
            "- order_type (must be the literal string 'limit')\n"
            "- valid_as_of (YYYY-MM-DD date matching the analysis date)\n"
            "- price_target (numeric float)\n"
            "- stop_loss (numeric float)\n"
            "- take_profit (numeric float)\n"
            "- sector\n"
            "- rationale (DETAILED string)\n"
            "- thesis (DETAILED string)\n"
            "- macro_alignment (how it fits the current regime)\n"
            "- memory_note (any relevant historical lesson)\n"
            "- position_sizing_logic (why you chose this amount of shares)\n\n"
```

- [ ] **Step 5: Add explicit execution discipline to the PM prompt**

Immediately after the existing paragraph that says `For every BUY: set stop_loss`, add:

```python
            "Every BUY must be executable as a limit order. "
            "Set entry_price to the price assumed by the candidate thesis, limit_price to the highest allowed execution price, "
            "and max_chase_price to the highest price where the risk/reward still matches the thesis. "
            "If the candidate summary says not to chase above a level, max_chase_price and limit_price must not exceed that level. "
            "Never use price_target as an entry price.\n\n"
```

- [ ] **Step 6: Run the schema tests and verify pass**

Run:

```bash
pytest tests/portfolio/test_pm_decision_schema.py -v
```

Expected: both tests pass.

- [ ] **Step 7: Run PM-related tests**

Run:

```bash
pytest tests/portfolio/test_pm_decision_schema.py tests/portfolio/test_portfolio_setup.py -v
```

Expected: all tests pass after Task 4 updates the PM decision fixtures with the required fields.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/agents/portfolio/pm_decision_agent.py tests/portfolio/test_pm_decision_schema.py
git commit -m "feat: require executable PM buy order fields"
```

---

### Task 4: Make PM Postcheck Use Live Prices and Enforce Order Guards

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`
- Test: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`

- [ ] **Step 1: Write the failing postcheck tests**

Append these tests to `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`:

```python
def test_postcheck_rejects_buy_when_live_price_missing():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    buy = {
        "ticker": "RIG",
        "shares": 100.0,
        "entry_price": 4.20,
        "limit_price": 4.30,
        "max_chase_price": 4.30,
        "order_type": "limit",
        "valid_as_of": "2026-04-28",
        "price_target": 5.50,
        "stop_loss": 3.78,
        "take_profit": 5.50,
        "sector": "Energy",
    }

    with pytest.raises(RuntimeError, match="missing live price.*RIG"):
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0},
                "prioritized_candidates": _make_prioritized_candidates("RIG"),
            }
        )


def test_postcheck_rejects_buy_above_max_chase_price():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    buy = {
        "ticker": "RMAX",
        "shares": 300.0,
        "entry_price": 9.94,
        "limit_price": 10.25,
        "max_chase_price": 10.25,
        "order_type": "limit",
        "valid_as_of": "2026-04-28",
        "price_target": 12.92,
        "stop_loss": 8.45,
        "take_profit": 12.92,
        "sector": "Real Estate",
    }

    with pytest.raises(RuntimeError, match="max_chase_price violated.*RMAX"):
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0, "RMAX": 11.29},
                "prioritized_candidates": _make_prioritized_candidates("RMAX"),
            }
        )


def test_postcheck_rejects_take_profit_not_above_live_price():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    buy = {
        "ticker": "MSFT",
        "shares": 10.0,
        "entry_price": 300.0,
        "limit_price": 305.0,
        "max_chase_price": 305.0,
        "order_type": "limit",
        "valid_as_of": "2026-04-28",
        "price_target": 304.0,
        "stop_loss": 270.0,
        "take_profit": 304.0,
        "sector": "Technology",
    }

    with pytest.raises(RuntimeError, match="take_profit must be above live price.*MSFT"):
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0, "MSFT": 305.0},
                "prioritized_candidates": _make_prioritized_candidates("MSFT"),
            }
        )
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py::test_postcheck_rejects_buy_when_live_price_missing tests/portfolio/test_portfolio_setup.py::test_postcheck_rejects_buy_above_max_chase_price tests/portfolio/test_portfolio_setup.py::test_postcheck_rejects_take_profit_not_above_live_price -v
```

Expected: tests fail because postcheck currently falls back to `price_target` and does not enforce max-chase or risk-level sanity.

- [ ] **Step 3: Add postcheck buy validation helper**

In `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`, add this helper near the other top-level helper functions:

```python
def _validate_buy_order_against_live_price(buy: dict[str, Any], prices: dict[str, Any]) -> float:
    """Return live buy price after validating executable order guard fields."""
    ticker = str(buy.get("ticker") or "").strip().upper()
    if not ticker:
        raise RuntimeError("pm_decision_postcheck: buy has empty ticker")
    if ticker not in prices or prices.get(ticker) is None:
        raise RuntimeError(f"pm_decision_postcheck: missing live price for {ticker}")

    live_price = float(prices[ticker])
    if live_price <= 0:
        raise RuntimeError(f"pm_decision_postcheck: non-positive live price for {ticker}")

    order_type = str(buy.get("order_type") or "").strip().lower()
    if order_type != "limit":
        raise RuntimeError(
            f"pm_decision_postcheck: order_type for {ticker} must be 'limit', got {order_type!r}"
        )

    limit_price = float(buy.get("limit_price") or 0.0)
    max_chase_price = float(buy.get("max_chase_price") or 0.0)
    stop_loss = float(buy.get("stop_loss") or 0.0)
    take_profit = float(buy.get("take_profit") or 0.0)

    if limit_price <= 0:
        raise RuntimeError(f"pm_decision_postcheck: limit_price must be positive for {ticker}")
    if max_chase_price <= 0:
        raise RuntimeError(f"pm_decision_postcheck: max_chase_price must be positive for {ticker}")
    if live_price > limit_price:
        raise RuntimeError(
            f"pm_decision_postcheck: limit_price violated for {ticker} — "
            f"live_price={live_price:.2f} > limit_price={limit_price:.2f}"
        )
    if live_price > max_chase_price:
        raise RuntimeError(
            f"pm_decision_postcheck: max_chase_price violated for {ticker} — "
            f"live_price={live_price:.2f} > max_chase_price={max_chase_price:.2f}"
        )
    if stop_loss <= 0 or stop_loss >= live_price:
        raise RuntimeError(
            f"pm_decision_postcheck: stop_loss must be below live price for {ticker}"
        )
    if take_profit <= live_price:
        raise RuntimeError(
            f"pm_decision_postcheck: take_profit must be above live price for {ticker}"
        )
    return live_price
```

- [ ] **Step 4: Use the helper in postcheck projection**

In `_make_pm_decision_postcheck_node`, replace this line inside the buy projection loop:

```python
                buy_price = float(prices.get(ticker) or buy.get("price_target") or 0.0)
```

with:

```python
                is_cash_sweep = (
                    ticker == "SGOV"
                    and str(buy.get("sector") or "").strip().casefold() == "cash equivalent"
                )
                if is_cash_sweep:
                    if ticker not in prices or prices.get(ticker) is None:
                        raise RuntimeError("pm_decision_postcheck: missing live price for SGOV")
                    buy_price = float(prices[ticker])
                else:
                    buy_price = _validate_buy_order_against_live_price(buy, prices)
```

- [ ] **Step 5: Update existing buy fixtures with new required fields**

For each non-SGOV `buy` dict in `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`, add fields matching the live test price. Example for a `$100` MSFT buy:

```python
{
    "ticker": "MSFT",
    "shares": 500.0,
    "entry_price": 100.0,
    "limit_price": 101.0,
    "max_chase_price": 101.0,
    "order_type": "limit",
    "valid_as_of": "2026-04-28",
    "price_target": 120.0,
    "stop_loss": 90.0,
    "take_profit": 120.0,
    "sector": "Technology",
}
```

Keep SGOV cash sweep fixtures without these fields because SGOV is the explicit cash-equivalent exception.

- [ ] **Step 6: Run focused tests and verify pass**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py::test_postcheck_rejects_buy_when_live_price_missing tests/portfolio/test_portfolio_setup.py::test_postcheck_rejects_buy_above_max_chase_price tests/portfolio/test_portfolio_setup.py::test_postcheck_rejects_take_profit_not_above_live_price -v
```

Expected: all three tests pass.

- [ ] **Step 7: Run the full portfolio setup suite**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/graph/portfolio_setup.py tests/portfolio/test_portfolio_setup.py
git commit -m "fix: enforce live buy prices in portfolio postcheck"
```

---

### Task 5: Enforce Order Guards in the Trade Executor

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/portfolio/trade_executor.py`
- Test: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_trade_executor.py`

- [ ] **Step 1: Write failing executor tests**

Append these tests to `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_trade_executor.py`:

```python
def test_execute_buy_rejects_price_above_max_chase():
    portfolio = _make_portfolio(cash=50_000.0, total_value=60_000.0)
    repo = _make_repo(portfolio=portfolio)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [
            {
                "ticker": "MSFT",
                "shares": 5.0,
                "sector": "Technology",
                "rationale": "Do not chase above $305.",
                "entry_price": 300.0,
                "limit_price": 305.0,
                "max_chase_price": 305.0,
                "order_type": "limit",
                "valid_as_of": "2026-04-28",
                "stop_loss": 270.0,
                "take_profit": 360.0,
            }
        ],
    }

    result = executor.execute_decisions("p1", decisions, {"MSFT": 310.0})

    repo.add_holding.assert_not_called()
    assert result["failed_trades"][0]["ticker"] == "MSFT"
    assert "max_chase_price" in result["failed_trades"][0]["reason"]


def test_execute_buy_rejects_stop_loss_above_execution_price():
    portfolio = _make_portfolio(cash=50_000.0, total_value=60_000.0)
    repo = _make_repo(portfolio=portfolio)
    executor = TradeExecutor(repo=repo, config=_DEFAULT_CONFIG)

    decisions = {
        "sells": [],
        "buys": [
            {
                "ticker": "MSFT",
                "shares": 5.0,
                "sector": "Technology",
                "rationale": "Invalid risk levels.",
                "entry_price": 300.0,
                "limit_price": 305.0,
                "max_chase_price": 305.0,
                "order_type": "limit",
                "valid_as_of": "2026-04-28",
                "stop_loss": 310.0,
                "take_profit": 360.0,
            }
        ],
    }

    result = executor.execute_decisions("p1", decisions, {"MSFT": 300.0})

    repo.add_holding.assert_not_called()
    assert result["failed_trades"][0]["ticker"] == "MSFT"
    assert "stop_loss" in result["failed_trades"][0]["reason"]
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
pytest tests/portfolio/test_trade_executor.py::test_execute_buy_rejects_price_above_max_chase tests/portfolio/test_trade_executor.py::test_execute_buy_rejects_stop_loss_above_execution_price -v
```

Expected: tests fail because executor currently ignores `limit_price`, `max_chase_price`, and risk-level validity.

- [ ] **Step 3: Add executor order guard helper**

In `/Users/Ahmet/Repo/TradingAgents/tradingagents/portfolio/trade_executor.py`, add this private function above `class TradeExecutor`:

```python
def _buy_order_guard_violation(buy: dict[str, Any], execution_price: float) -> str | None:
    """Return a rejection reason when a BUY violates executable order constraints."""
    order_type = str(buy.get("order_type") or "").strip().lower()
    if order_type and order_type != "limit":
        return f"Unsupported order_type {order_type!r}; only limit orders are allowed"

    limit_price_raw = buy.get("limit_price")
    if limit_price_raw is not None:
        limit_price = float(limit_price_raw)
        if execution_price > limit_price:
            return (
                f"limit_price violated: execution_price={execution_price:.2f} "
                f"> limit_price={limit_price:.2f}"
            )

    max_chase_raw = buy.get("max_chase_price")
    if max_chase_raw is not None:
        max_chase_price = float(max_chase_raw)
        if execution_price > max_chase_price:
            return (
                f"max_chase_price violated: execution_price={execution_price:.2f} "
                f"> max_chase_price={max_chase_price:.2f}"
            )

    stop_loss_raw = buy.get("stop_loss")
    if stop_loss_raw is not None and float(stop_loss_raw) >= execution_price:
        return "stop_loss must be below execution price"

    take_profit_raw = buy.get("take_profit")
    if take_profit_raw is not None and float(take_profit_raw) <= execution_price:
        return "take_profit must be above execution price"

    return None
```

- [ ] **Step 4: Invoke executor order guard before constraint checks**

In the BUY loop, immediately after the missing-price check and before `repo.get_portfolio_with_holdings`, insert:

```python
            guard_violation = _buy_order_guard_violation(buy, float(price))
            if guard_violation:
                failed_trades.append(
                    {
                        "action": "BUY",
                        "ticker": ticker,
                        "reason": guard_violation,
                    }
                )
                logger.warning("BUY %s rejected — %s", ticker, guard_violation)
                continue
```

- [ ] **Step 5: Run focused tests and verify pass**

Run:

```bash
pytest tests/portfolio/test_trade_executor.py::test_execute_buy_rejects_price_above_max_chase tests/portfolio/test_trade_executor.py::test_execute_buy_rejects_stop_loss_above_execution_price -v
```

Expected: both tests pass.

- [ ] **Step 6: Run trade executor suite**

Run:

```bash
pytest tests/portfolio/test_trade_executor.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/portfolio/trade_executor.py tests/portfolio/test_trade_executor.py
git commit -m "fix: enforce executable buy guards in trade executor"
```

---

### Task 6: Make Cash Sweep Constraint-Aware

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`
- Test: `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`

- [ ] **Step 1: Write failing cash sweep tests**

Append these tests to `/Users/Ahmet/Repo/TradingAgents/tests/portfolio/test_portfolio_setup.py`:

```python
def test_cash_sweep_does_not_add_sgov_when_it_would_violate_position_cap():
    setup = PortfolioGraphSetup(agents={}, config={**_BASE_CONFIG, "max_position_pct": 0.15})
    node = setup._make_cash_sweep_node()

    state = {
        "portfolio_data": _make_portfolio_data(),
        "pm_decision": _make_decision(),
        "prices": {"AAPL": 200.0, "SGOV": 100.0},
    }

    result = node(state)
    decision = json.loads(result["pm_decision"])

    assert decision["buys"] == []
    assert "Skipped SGOV sweep" in result["cash_sweep"]


def test_cash_sweep_adds_sgov_when_caps_allow_it():
    setup = PortfolioGraphSetup(
        agents={},
        config={**_BASE_CONFIG, "max_position_pct": 1.0, "max_sector_pct": 1.0},
    )
    node = setup._make_cash_sweep_node()

    state = {
        "portfolio_data": _make_portfolio_data(),
        "pm_decision": _make_decision(),
        "prices": {"AAPL": 200.0, "SGOV": 100.0},
    }

    result = node(state)
    decision = json.loads(result["pm_decision"])

    assert decision["buys"][0]["ticker"] == "SGOV"
    assert decision["buys"][0]["sector"] == "Cash Equivalent"
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py::test_cash_sweep_does_not_add_sgov_when_it_would_violate_position_cap tests/portfolio/test_portfolio_setup.py::test_cash_sweep_adds_sgov_when_caps_allow_it -v
```

Expected: the first test fails because cash sweep currently appends SGOV without checking caps.

- [ ] **Step 3: Import `check_constraints`**

In `/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py`, add:

```python
from tradingagents.portfolio.risk_evaluator import check_constraints, compute_portfolio_risk
```

and remove the old single-function import:

```python
from tradingagents.portfolio.risk_evaluator import compute_portfolio_risk
```

- [ ] **Step 4: Check constraints before appending SGOV**

Inside `_make_cash_sweep_node`, immediately before `decisions["buys"].append(sweep_buy)`, insert:

```python
                            violations = check_constraints(
                                portfolio,
                                holdings,
                                self._config,
                                new_ticker=sweep_etf,
                                new_shares=float(shares_to_buy),
                                new_price=float(sweep_etf_price),
                                new_sector="Cash Equivalent",
                            )
                            if violations:
                                sweep_details = (
                                    "Skipped SGOV sweep because it would violate constraints: "
                                    + "; ".join(violations)
                                )
                                logger.info("CashSweep: %s", sweep_details)
                                return {
                                    "pm_decision": pm_decision_str,
                                    "cash_sweep": sweep_details,
                                    "sender": "cash_sweep",
                                }
```

- [ ] **Step 5: Run focused tests and verify pass**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py::test_cash_sweep_does_not_add_sgov_when_it_would_violate_position_cap tests/portfolio/test_portfolio_setup.py::test_cash_sweep_adds_sgov_when_caps_allow_it -v
```

Expected: both tests pass.

- [ ] **Step 6: Run portfolio setup suite**

Run:

```bash
pytest tests/portfolio/test_portfolio_setup.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/graph/portfolio_setup.py tests/portfolio/test_portfolio_setup.py
git commit -m "fix: make cash sweep respect portfolio constraints"
```

---

### Task 7: Add Rerun Start Idempotency Guard

**Files:**
- Modify: `/Users/Ahmet/Repo/TradingAgents/agent_os/backend/routes/runs.py`
- Test: `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_run_controls.py`

- [ ] **Step 1: Write failing run-control test**

Append this test to `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_run_controls.py`:

```python
def test_set_run_task_cancels_existing_active_task_before_replacement():
    run_id = "run-replace-active-task"

    class _Task:
        def __init__(self) -> None:
            self.cancel_called = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancel_called = True

    async def _gen():
        if False:
            yield {}

    old_task = _Task()
    runs_route.run_tasks[run_id] = old_task

    try:
        runs_route._set_run_task(run_id, _gen())
    finally:
        new_task = runs_route.run_tasks.pop(run_id, None)
        if new_task is not None:
            new_task.cancel()

    assert old_task.cancel_called is True
```

- [ ] **Step 2: Run the existing test and verify current behavior**

Run:

```bash
pytest tests/unit/test_run_controls.py::test_set_run_task_cancels_existing_active_task_before_replacement -v
```

Expected: this test may already pass. If it passes, keep it as a locking regression test because the run artifact showed repeated portfolio starts and this behavior must not regress.

- [ ] **Step 3: Write failing duplicate rerun marker test**

Append this test to `/Users/Ahmet/Repo/TradingAgents/tests/unit/test_run_controls.py`:

```python
def test_active_rerun_key_blocks_duplicate_node_start():
    run_id = "run-active-rerun-key"

    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31", "portfolio_id": "p1"},
        "events": [],
        "rerun_seq": 3,
        "active_rerun_key": "portfolio:p1:make_pm_decision",
    }

    try:
        assert (
            runs_route._claim_active_rerun_key(
                run_id,
                phase="portfolio",
                identifier="p1",
                node_id="make_pm_decision",
            )
            is False
        )
        assert (
            runs_route._claim_active_rerun_key(
                run_id,
                phase="portfolio",
                identifier="p1",
                node_id="pm_decision_postcheck",
            )
            is True
        )
        assert runs_route.runs[run_id]["active_rerun_key"] == "portfolio:p1:pm_decision_postcheck"
    finally:
        runs_route.runs.pop(run_id, None)
```

- [ ] **Step 4: Run duplicate marker test and verify failure**

Run:

```bash
pytest tests/unit/test_run_controls.py::test_active_rerun_key_blocks_duplicate_node_start -v
```

Expected: failure because `_claim_active_rerun_key` does not exist.

- [ ] **Step 5: Add rerun key helper**

In `/Users/Ahmet/Repo/TradingAgents/agent_os/backend/routes/runs.py`, add this helper near `_set_run_task`:

```python
def _claim_active_rerun_key(
    run_id: str,
    *,
    phase: str,
    identifier: str,
    node_id: str,
) -> bool:
    """Return False when the same rerun node is already active for this run."""
    run = runs.get(run_id)
    if not isinstance(run, dict):
        return True
    key = f"{phase}:{identifier}:{node_id}"
    if run.get("active_rerun_key") == key and run.get("status") == "running":
        return False
    run["active_rerun_key"] = key
    return True
```

- [ ] **Step 6: Use helper in rerun entrypoint**

In `trigger_rerun_node`, before queuing the rerun task, insert:

```python
    if not _claim_active_rerun_key(
        run_id,
        phase=phase,
        identifier=identifier or "",
        node_id=node_id,
    ):
        raise HTTPException(status_code=409, detail="Rerun node is already active")
```

- [ ] **Step 7: Clear active rerun key when replacing or stopping a task**

In `_set_run_task`, after cancelling an existing task, add:

```python
        if isinstance(runs.get(run_id), dict):
            runs[run_id].pop("active_rerun_key", None)
```

In `stop_run`, after a task cancellation succeeds, add:

```python
        run.pop("active_rerun_key", None)
```

- [ ] **Step 8: Run run-control tests**

Run:

```bash
pytest tests/unit/test_run_controls.py -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add agent_os/backend/routes/runs.py tests/unit/test_run_controls.py
git commit -m "fix: guard duplicate active rerun starts"
```

---

### Task 8: Full Verification and Graphify Rebuild

**Files:**
- No source edits in this task.
- Rebuilds generated graph metadata under `/Users/Ahmet/Repo/TradingAgents/graphify-out/` if code changed.

- [ ] **Step 1: Run focused regression suites**

Run:

```bash
pytest \
  tests/unit/test_output_validation.py \
  tests/portfolio/test_pm_decision_schema.py \
  tests/portfolio/test_portfolio_setup.py \
  tests/portfolio/test_trade_executor.py \
  tests/unit/test_run_controls.py \
  -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader graph and portfolio tests**

Run:

```bash
pytest tests/portfolio tests/unit/test_portfolio_graph_state.py tests/unit/test_graph_runtime_fixes.py -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run deterministic scanner-context tests**

Run:

```bash
pytest tests/graph tests/integration/test_scanner_context_filtering.py tests/unit/test_scanner_graph_context_prompt.py -v
```

Expected: all selected tests pass or skip only tests already marked as live/vendor-dependent. Any failure related to missing `scan_date`, `run_id`, or upstream graph evidence must be fixed before completion.

- [ ] **Step 4: Rebuild graphify code graph**

Run:

```bash
PYTHONPATH=. /opt/miniconda3/bin/python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

Expected: command exits with status `0`.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git diff --stat
git diff -- tradingagents/agents/utils/output_validation.py tradingagents/graph/portfolio_setup.py tradingagents/agents/portfolio/pm_decision_agent.py tradingagents/portfolio/trade_executor.py agent_os/backend/routes/runs.py
```

Expected: diff only contains the validation, schema, postcheck, executor, cash-sweep, and rerun-idempotency changes described in this plan.

- [ ] **Step 6: Commit graph rebuild if generated files changed**

Run:

```bash
git status --short graphify-out
git add graphify-out
git commit -m "chore: rebuild graphify graph"
```

Expected: commit only if `git status --short graphify-out` shows generated graph changes. If no graphify files changed, do not create an empty commit.

---

## Self-Review

**Spec coverage:** This plan covers the bad downstream report causes found in the run review: substring action hallucination, structured/prose mismatch, missing executable entry limits, postcheck/executor price mismatch, invalid SGOV sweep, and repeated rerun-start risk.

**Placeholder scan:** The plan contains concrete file paths, tests, commands, and implementation snippets. It does not use open-ended implementation placeholders.

**Type consistency:** The added PM fields are consistently named `entry_price`, `limit_price`, `max_chase_price`, `order_type`, and `valid_as_of` across schema, postcheck, executor, and tests.
