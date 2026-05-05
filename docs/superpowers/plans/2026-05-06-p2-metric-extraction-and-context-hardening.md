# P2: Metric Extraction & Context Hardening — Next Sprint

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three largest remaining signal-integrity gaps that survive P0/P1 fixes: (1) commodity/timeframe contamination in scanner context, (2) missing analyst summary for PM historical context, (3) prompt-anchored regex fragility in fundamentals extraction.

**Architecture:** Two context-building improvements (P2.1–P2.2) + one output schema refactor (P2.3). Each is independently committable. P2.3 replaces regex with structured output; P2.1–P2.2 enhance context delivery.

**Tech Stack:** Python 3.11+, pytest, Pydantic, existing agent patterns.

**Predecessor:** P0 + P1 fixes must merge first. (P0/P1 adds `## REQUIRED METRICS FORMAT` to analyst prompts; P2.3 validates those metrics at write time.)

---

## Priority Map

| Priority | Fix | Effort | Impact | Blocker For |
|----------|-----|--------|--------|-------------|
| **P2** | Timeframe-tag commodity data in scanner context | 45 min | Stops YoY vs daily signal cross-contamination propagating 12+ nodes | None |
| **P2** | Generate `research_packet_summary` at RM consistency guard | 40 min | Creates compressed analyst memory for PM; enables future cross-run context (hist-reuse Stage 2) | historical-report-reuse plan |
| **P2** | Structured metric extraction in fundamentals analyst | 60 min | Replaces prompt-anchored regex with Pydantic schema; stores pe_ratio/D_E/FCF in key_metrics at write time; eliminates regex drift | future P3 regex consolidation |

---

# P2.1: Timeframe-tag commodity data in scanner context

**Problem:** Scanner context contains price changes for gold, oil, DXY, VIX without timeframe labels. Agents cite "`gold -12%` collapse" when the -12% is YoY; the -1% daily change is ignored. This conflates trend (YoY) with momentum (daily) across the trading graph, causing 12+ nodes to misweight macro signals.

**Approach:** 
1. In scanner context builders, split change_pct fields into separate `*_change_pct_daily` and `*_change_pct_yoy` fields.
2. In the text formatter (scanner_graph_context_text), always label timeframe explicitly: `"Gold: -1.01% (daily), -12.0% (YoY)"`.
3. Add a schema validation step that rejects bare `change_pct` fields without a timeframe suffix.

**Files affected:**
- Scanner output schema (likely `tradingagents/dataflows/scanner_graph_setup.py` or similar)
- Context text formatter that builds `scanner_graph_context_text`
- Tests that verify formatter output contains both daily and YoY labels

---

### Task P2.1: Implement commodity timeframe tagging

**Files:**
- Modify: Scanner graph builders (identify exact file path by grepping for `scanner_graph_context_text`)
- Modify: Context formatter that builds `scanner_graph_context_text` string
- Create: `tests/agents/utils/test_scanner_context_timeframe_labels.py`

- [ ] **Step 1: Find scanner context builders**

```bash
grep -r "scanner_graph_context_text" tradingagents/ --include="*.py" | grep -v test | head -10
```

Identify the file(s) that:
1. Assemble commodity price data (gold, oil, DXY, VIX, etc.)
2. Format them into the `scanner_graph_context_text` string that reaches agents

- [ ] **Step 2: Read the current scanner context formatter**

Open the identified file and find the section that builds price change strings (likely includes lines like `f"Gold {price}"` or similar).

- [ ] **Step 3: Modify schema to split daily/YoY**

Find where commodity data is loaded (e.g., from market data tools). Add logic to fetch or calculate both:
- `change_pct_daily`: today's % change
- `change_pct_yoy`: year-over-year % change

Example (adjust for actual data source):
```python
commodity_data = {
    "gold": {
        "price": 4583,
        "change_pct_daily": -1.01,
        "change_pct_yoy": -12.0,
    },
    ...
}
```

- [ ] **Step 4: Update the context text formatter**

Modify the section that builds the text string to include both timeframes with explicit labels:

```python
# OLD (no timeframe label):
f"Gold {price} {change_pct}%"

# NEW (explicit labels):
f"Gold: ${price} ({change_pct_daily:+.2f}% daily, {change_pct_yoy:+.2f}% YoY)"
```

For all commodities (gold, oil, DXY, etc.), use the format: `"Name: $price (±X.XX% daily, ±Y.YY% YoY)"`.

- [ ] **Step 5: Write failing test**

Create `tests/agents/utils/test_scanner_context_timeframe_labels.py`:

```python
"""Test that scanner context labels commodity timeframes explicitly."""


def test_scanner_context_contains_daily_and_yoy_labels():
    """Scanner context must label commodity changes as (daily) and (YoY)."""
    # Import the context builder
    from tradingagents.agents.utils.scanner_context import build_scanner_context_text  # adjust path
    
    # Mock or fetch sample commodity data with both daily and YoY
    scanner_data = {
        "commodities": {
            "gold": {"price": 4583, "change_pct_daily": -1.01, "change_pct_yoy": -12.0},
            "oil": {"price": 72.5, "change_pct_daily": 0.5, "change_pct_yoy": 8.2},
        }
    }
    
    context = build_scanner_context_text(scanner_data)
    
    # Verify both labels are present and separated
    assert "(daily)" in context or "daily" in context.lower(), "Context must label daily changes"
    assert "(yoy)" in context or "yoy" in context.lower(), "Context must label YoY changes"
    
    # Verify no bare change_pct values (e.g., "gold -12%" without timeframe)
    # This is a negative test — ensure we don't have bare percentages
    assert "Gold -12%" not in context, "Bare change_pct without timeframe label is not allowed"


def test_scanner_context_explicit_format():
    """Verify the exact format: 'Name: $price (±X% daily, ±Y% YoY)'."""
    from tradingagents.agents.utils.scanner_context import build_scanner_context_text
    
    scanner_data = {
        "commodities": {
            "gold": {"price": 4583, "change_pct_daily": -1.01, "change_pct_yoy": -12.0},
        }
    }
    
    context = build_scanner_context_text(scanner_data)
    
    # Check for gold entry with both timeframes
    assert "4583" in context, "Price should be present"
    assert "-1.01" in context or "-1.0" in context, "Daily change should be present"
    assert "-12" in context, "YoY change should be present"
```

- [ ] **Step 6: Run test, confirm fail**

```bash
pytest tests/agents/utils/test_scanner_context_timeframe_labels.py -v
```

Expected: FAIL (context builder doesn't yet split/label timeframes).

- [ ] **Step 7: Run test, confirm pass**

After modifying the context builder in Step 4:

```bash
pytest tests/agents/utils/test_scanner_context_timeframe_labels.py -v
```

Expected: PASS.

- [ ] **Step 8: Verify downstream agents still work**

Run a subset of tests that exercise scanner context (market analyst, macro synthesis, etc.):

```bash
pytest tests/agents/analysts/ -v -k "market or macro" -m "not integration"
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/agents/utils/ tests/agents/utils/test_scanner_context_timeframe_labels.py
git commit -m "feat(scanner-context): split commodity changes into daily and YoY with explicit labels"
```

---

# P2.2: Generate `research_packet_summary` at RM consistency guard

**Problem:** After RM consistency guard passes, the `research_packet_summary` field remains empty. PM has no compressed memory of what the analyst chain concluded. This also blocks the historical-report-reuse plan's Stage 2 (prior analysis context injection).

**Approach:**
1. After the consistency guard node returns `status: "ok"`, invoke a lightweight summarization step (can be another LLM call or a simple token-budget formatter).
2. Generate a 400-token structured summary containing: ticker, trade date, top 3 bull points (with numbers), top 3 bear points (with numbers), final RM rating, key risk levels, confidence.
3. Store the summary as `research_packet_summary` in AgentState.
4. PM prompt receives this summary as a structured header above the full research packet.

**Files affected:**
- `tradingagents/agents/managers/rm_consistency_guard.py` (or wherever consistency guard node is)
- `tradingagents/agents/utils/agent_states.py` (ensure `research_packet_summary` field exists in AgentState)
- Tests validating summary field is populated and non-empty

---

### Task P2.2: Implement research packet summary generation

**Files:**
- Modify: `tradingagents/agents/managers/rm_consistency_guard.py` (add summary generation step)
- Verify: `tradingagents/agents/utils/agent_states.py` (confirm `research_packet_summary` field exists)
- Create: `tests/agents/managers/test_rm_consistency_guard_summary.py`

- [ ] **Step 1: Verify `research_packet_summary` field exists in AgentState**

```bash
grep -n "research_packet_summary" tradingagents/agents/utils/agent_states.py
```

If not present, add to the AgentState TypedDict:
```python
"research_packet_summary": str,  # compressed analyst summary for PM
```

- [ ] **Step 2: Read RM consistency guard node**

```bash
grep -n "def.*consistency_guard\|return {" tradingagents/agents/managers/rm_consistency_guard.py | head -20
```

Understand the current return structure. Find where the node returns `{ "status": "ok", ... }`.

- [ ] **Step 3: Write failing test**

Create `tests/agents/managers/test_rm_consistency_guard_summary.py`:

```python
"""Test that RM consistency guard generates research_packet_summary."""

from unittest.mock import MagicMock, patch


def test_rm_consistency_guard_generates_summary():
    """After consistency guard passes, research_packet_summary must be populated."""
    from tradingagents.agents.managers.rm_consistency_guard import create_rm_consistency_guard
    
    # Mock LLM
    mock_llm = MagicMock()
    
    # Sample state
    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-05",
        "investment_debate_state": {
            "bull_thesis": "Strong demand, margin expansion",
            "bear_thesis": "Valuation at 40x earnings",
            "bull_conviction": 7,
            "bear_conviction": 6,
            "unresolved_conflict": None,
        },
        "investment_plan": {
            "ticker": "AAPL",
            "rating": "BUY",
            "entry_price": 150,
            "target_price": 180,
            "confidence_score": 0.72,
        },
        "research_packet_summary": "",  # empty at input
    }
    
    # Mock consistency guard logic
    with patch("tradingagents.agents.managers.rm_consistency_guard.validate_research_consistency") as mock_validate:
        mock_validate.return_value = MagicMock(
            is_valid=True,
            status="ok",
            reason="All checks passed"
        )
        
        guard_node = create_rm_consistency_guard(mock_llm)
        result = guard_node(state)
    
    # Verify summary is generated
    summary = result.get("research_packet_summary") or ""
    assert summary, "research_packet_summary must be non-empty"
    assert len(summary) > 100, "Summary should be substantive (>100 chars)"
    assert "AAPL" in summary, "Summary should include ticker"
    assert "BUY" in summary or "rating" in summary.lower(), "Summary should mention rating"


def test_rm_consistency_guard_summary_contains_key_metrics():
    """Summary must include numbers and decision points."""
    from tradingagents.agents.managers.rm_consistency_guard import create_rm_consistency_guard
    
    mock_llm = MagicMock()
    
    state = {
        "company_of_interest": "NVDA",
        "trade_date": "2026-05-05",
        "investment_debate_state": {
            "bull_thesis": "AI leadership, 40% YoY growth",
            "bear_thesis": "High valuation at 50x",
            "bull_conviction": 8,
            "bear_conviction": 5,
            "unresolved_conflict": None,
        },
        "investment_plan": {
            "ticker": "NVDA",
            "rating": "BUY",
            "entry_price": 850,
            "target_price": 1050,
            "confidence_score": 0.78,
        },
        "research_packet_summary": "",
    }
    
    with patch("tradingagents.agents.managers.rm_consistency_guard.validate_research_consistency") as mock_validate:
        mock_validate.return_value = MagicMock(is_valid=True, status="ok", reason="")
        
        guard_node = create_rm_consistency_guard(mock_llm)
        result = guard_node(state)
    
    summary = result.get("research_packet_summary") or ""
    
    # Summary should contain at least one number (price target, growth %, etc.)
    assert any(char.isdigit() for char in summary), "Summary should contain numeric data"
```

- [ ] **Step 4: Run test, confirm fail**

```bash
pytest tests/agents/managers/test_rm_consistency_guard_summary.py -v
```

Expected: FAIL (no summary generation yet).

- [ ] **Step 5: Implement summary generation**

In the RM consistency guard node, after validation passes, add:

```python
# After consistency validation returns status: "ok"
research_packet_summary = _generate_research_summary(
    ticker=state["company_of_interest"],
    date=state["trade_date"],
    investment_plan=state.get("investment_plan", {}),
    debate_state=state.get("investment_debate_state", {}),
)
```

Define `_generate_research_summary()` in the same file:

```python
def _generate_research_summary(ticker: str, date: str, investment_plan: dict, debate_state: dict) -> str:
    """
    Generate a 300–400 token compressed summary of the research for PM context.
    
    Includes: ticker, date, top bull/bear points (with numbers), rating, confidence, key risks.
    """
    rating = investment_plan.get("rating", "HOLD")
    confidence = investment_plan.get("confidence_score", 0.5)
    entry = investment_plan.get("entry_price", 0)
    target = investment_plan.get("target_price", 0)
    
    bull = debate_state.get("bull_thesis", "")
    bear = debate_state.get("bear_thesis", "")
    
    summary = (
        f"{ticker} ({date}): {rating} \n"
        f"Confidence: {confidence:.0%} | Entry: ${entry:.2f} | Target: ${target:.2f} (Upside: {(target/entry-1)*100:.1f}%) \n\n"
        f"Bull Case: {bull} \n"
        f"Bear Case: {bear} \n\n"
        f"Key Risk: [extracted from weakest un-rebutted fundamental] \n"
        f"Catalyst: [nearest catalyst date from calendar]"
    )
    return summary
```

Adjust the template to match your state structure.

- [ ] **Step 6: Run test, confirm pass**

```bash
pytest tests/agents/managers/test_rm_consistency_guard_summary.py -v
```

Expected: PASS.

- [ ] **Step 7: Verify PM can consume the summary**

Create a simple test that verifies PM prompt includes the summary:

```bash
grep -n "research_packet_summary" tradingagents/agents/portfolio/pm_decision_agent.py
```

If not present, add to PM system prompt:
```python
f"## Prior Research Summary\n{state.get('research_packet_summary', '')}\n\n"
```

- [ ] **Step 8: Run full suite**

```bash
pytest tests/ -v -m "not integration"
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add tradingagents/agents/managers/rm_consistency_guard.py tests/agents/managers/test_rm_consistency_guard_summary.py
git commit -m "feat(rm-guard): generate research_packet_summary for PM historical context"
```

---

# P2.3: Structured metric extraction in fundamentals analyst

**Problem:** Current implementation uses prompt-anchored regex on the raw `fundamentals_report` text (P1.1 fix). This is fragile — if the LLM's prose format drifts or the regex pattern misses a variant, the extraction silently fails and downstream regex has no fallback. Also, regex extraction happens at context-build time, not at write time, creating a lag.

**Approach:**
1. In the fundamentals analyst node, after the LLM returns, add explicit Pydantic validation step that extracts and validates PE ratio, D/E ratio, FCF %, operating margin, current ratio, working capital.
2. Store these extracted metrics in `fundamentals_report_structured.key_metrics` as typed fields (pe_ratio: float, debt_equity_ratio: float, fcf_change_pct: float, etc.), not just `numeric_mentions`.
3. This gives downstream consumers (research_packet_summary, debate brief, research packet) direct access to validated numbers instead of regex hunting.

**Files affected:**
- `tradingagents/agents/analysts/fundamentals_analyst.py` (add extraction step after LLM invocation)
- `tradingagents/agents/utils/output_validation.py` (extend `build_fundamentals_report_structured` to store metrics)
- Tests validating metrics are extracted and stored at write time

---

### Task P2.3: Implement structured fundamentals metric extraction

**Files:**
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py` (add metric extraction after LLM)
- Modify: `tradingagents/agents/utils/output_validation.py` (update `build_fundamentals_report_structured` to store metrics)
- Modify: `tradingagents/agents/utils/summary_context.py` (_fundamentals_risk_block now reads structured metrics, not regex)
- Create: `tests/agents/analysts/test_fundamentals_metric_extraction.py`

- [ ] **Step 1: Read current fundamentals analyst node**

```bash
grep -n "def create_fundamentals_analyst\|return {" tradingagents/agents/analysts/fundamentals_analyst.py | head -20
```

Understand where the LLM result is captured and returned.

- [ ] **Step 2: Read current `build_fundamentals_report_structured`**

```bash
grep -n "def build_fundamentals_report_structured" tradingagents/agents/utils/output_validation.py
```

Examine the current structure of `key_metrics`. It likely has `numeric_mentions`, `summary_table_rows`, `report_char_count`. We will add `pe_ratio`, `debt_equity_ratio`, `fcf_change_pct`, `operating_margin_pct`, `current_ratio`, `working_capital_str`.

- [ ] **Step 3: Write failing test**

Create `tests/agents/analysts/test_fundamentals_metric_extraction.py`:

```python
"""Test that fundamentals analyst extracts and stores metrics in structured output."""

from unittest.mock import MagicMock, patch
import json


def test_fundamentals_metrics_extracted_from_llm_output():
    """Fundamentals analyst must extract PE, D/E, FCF, etc. into key_metrics."""
    from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
    
    mock_llm = MagicMock()
    
    # LLM returns a report with mandated metric format (from P1)
    llm_report = (
        "AAPL Fundamentals Summary\n"
        "P/E ratio: 28.5x\n"
        "D/E ratio: 1.23\n"
        "Free cash flow: +12% YoY\n"
        "Operating margin: 29.0%\n"
        "Current ratio: 1.89\n"
        "Working capital: $45.2b (positive)\n\n"
        "Apple maintains strong profitability with improving margins..."
    )
    
    with patch("tradingagents.agents.analysts.fundamentals_analyst.invoke_with_timeout") as mock_invoke:
        mock_invoke.return_value = (
            MagicMock(content=llm_report),
            None,
        )
        
        node = create_fundamentals_analyst(mock_llm)
        state = {
            "company_of_interest": "AAPL",
            "trade_date": "2026-05-05",
            "messages": [],
            # ... other required state fields
        }
        
        result = node(state)
    
    structured = result.get("fundamentals_report_structured") or {}
    key_metrics = structured.get("key_metrics") or {}
    
    # Verify metrics are extracted and typed
    assert key_metrics.get("pe_ratio") == 28.5, "PE ratio should be extracted"
    assert key_metrics.get("debt_equity_ratio") == 1.23, "D/E ratio should be extracted"
    assert key_metrics.get("fcf_change_pct") == 12.0, "FCF % should be extracted"
    assert key_metrics.get("operating_margin_pct") == 29.0, "Operating margin should be extracted"
    assert key_metrics.get("current_ratio") == 1.89, "Current ratio should be extracted"
    assert "45.2" in key_metrics.get("working_capital_str", ""), "Working capital should be stored"


def test_fundamentals_metrics_partial_data():
    """If only some metrics are available, extraction should still work."""
    from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
    
    mock_llm = MagicMock()
    
    llm_report = (
        "P/E ratio: 35.0x\n"
        "D/E ratio: 0.5\n"
        "Current ratio: 2.1\n"
        # FCF, operating margin, working capital missing
    )
    
    with patch("tradingagents.agents.analysts.fundamentals_analyst.invoke_with_timeout") as mock_invoke:
        mock_invoke.return_value = (MagicMock(content=llm_report), None)
        
        node = create_fundamentals_analyst(mock_llm)
        state = {"company_of_interest": "TEST", "trade_date": "2026-05-05", "messages": []}
        
        result = node(state)
    
    structured = result.get("fundamentals_report_structured") or {}
    key_metrics = structured.get("key_metrics") or {}
    
    # Verify available metrics are extracted
    assert key_metrics.get("pe_ratio") == 35.0
    assert key_metrics.get("debt_equity_ratio") == 0.5
    assert key_metrics.get("current_ratio") == 2.1
    # Missing metrics should have None or not present
    assert key_metrics.get("fcf_change_pct") is None or "fcf" not in key_metrics


def test_fundamentals_metrics_parsed_into_research_packet():
    """Metrics extracted at write time should be available downstream."""
    from tradingagents.agents.utils.summary_context import build_research_packet
    
    state = {
        "fundamentals_report": "P/E ratio: 22.0x\nD/E ratio: 1.5\nFree cash flow: -15% YoY\n",
        "fundamentals_report_structured": {
            "ticker": "TSLA",
            "key_metrics": {
                "pe_ratio": 22.0,
                "debt_equity_ratio": 1.5,
                "fcf_change_pct": -15.0,
                "operating_margin_pct": None,
                "current_ratio": None,
                "working_capital_str": None,
            }
        },
    }
    
    packet = build_research_packet(state)
    
    # Metrics should appear in packet (via _fundamentals_risk_block reading structured data)
    assert "22" in packet or "P/E" in packet.upper(), "PE should be in packet"
    assert "1.5" in packet or "D/E" in packet.upper(), "D/E should be in packet"
    assert "-15" in packet, "FCF should be in packet"
```

- [ ] **Step 4: Run test, confirm fail**

```bash
pytest tests/agents/analysts/test_fundamentals_metric_extraction.py -v
```

Expected: FAIL (no extraction yet).

- [ ] **Step 5: Implement metric extraction**

In `fundamentals_analyst.py`, after the LLM invocation, add:

```python
import re as _re
from typing import Optional

# After invoke_with_timeout returns
report_text = result.content or ""

# Extract metrics from the report text
def _extract_metrics(text: str) -> dict:
    """Extract structured metrics from fundamentals report."""
    import re
    text_lower = text.lower()
    
    metrics = {
        "pe_ratio": None,
        "debt_equity_ratio": None,
        "fcf_change_pct": None,
        "operating_margin_pct": None,
        "current_ratio": None,
        "working_capital_str": None,
    }
    
    # P/E ratio: 28.5x or price-to-earnings: 28.5x
    pe_match = re.search(r'(?:p/?e|price.to.earnings)\s*(?:ratio)?[:\s]+([0-9]+(?:\.[0-9]+)?)\s*x?', text_lower)
    if pe_match:
        metrics["pe_ratio"] = float(pe_match.group(1))
    
    # D/E ratio: 1.23
    de_match = re.search(r'(?:d/?e|debt.to.equity|debt/equity)\s*(?:ratio)?[:\s]+([0-9]+(?:\.[0-9]+)?)', text_lower)
    if de_match:
        metrics["debt_equity_ratio"] = float(de_match.group(1))
    
    # Free cash flow: +12% YoY or FCF: -15% YoY
    fcf_match = re.search(r'(?:free\s+cash\s+flow|fcf)[^.\n]{0,40}?([+-]?[0-9]+(?:\.[0-9]+)?)', text_lower)
    if fcf_match:
        metrics["fcf_change_pct"] = float(fcf_match.group(1))
    
    # Operating margin: 29.0% or op margin: 29.0%
    om_match = re.search(r'op(?:erating)?\s+margin[:\s]+([+-]?[0-9]+(?:\.[0-9]+)?)', text_lower)
    if om_match:
        metrics["operating_margin_pct"] = float(om_match.group(1))
    
    # Current ratio: 1.89
    cr_match = re.search(r'current\s+ratio[:\s]+([0-9]+(?:\.[0-9]+)?)', text_lower)
    if cr_match:
        metrics["current_ratio"] = float(cr_match.group(1))
    
    # Working capital: $45.2b (positive) or $2.3b (negative)
    wc_match = re.search(r'working\s+capital[:\s]+([^.\n]{1,50}?)(?:\s*\(|\s*$|,|\n)', text_lower)
    if wc_match:
        metrics["working_capital_str"] = wc_match.group(1).strip()
    
    return metrics

extracted_metrics = _extract_metrics(report_text)
```

Then pass `extracted_metrics` to `build_fundamentals_report_structured()`:

```python
structured = build_fundamentals_report_structured(
    ticker=ticker,
    as_of_date=current_date,
    fundamentals_report=report_text,
    extracted_metrics=extracted_metrics,  # NEW
)
```

- [ ] **Step 6: Update `build_fundamentals_report_structured` to accept and store metrics**

In `output_validation.py`, update the function signature and logic:

```python
def build_fundamentals_report_structured(
    ticker: str,
    as_of_date: str,
    fundamentals_report: str,
    extracted_metrics: dict | None = None,
) -> dict:
    """Build fundamentals report structured output with optional pre-extracted metrics."""
    
    if not fundamentals_report.strip():
        return {
            "ticker": ticker,
            "date": as_of_date,
            "key_metrics": {},
            "summary_table_rows": [],
            "report_char_count": 0,
        }
    
    # Use provided extracted_metrics or build empty
    key_metrics = extracted_metrics or {}
    
    return {
        "ticker": ticker,
        "date": as_of_date,
        "key_metrics": key_metrics,  # Now includes pe_ratio, debt_equity_ratio, etc.
        "summary_table_rows": [],
        "report_char_count": len(fundamentals_report),
    }
```

- [ ] **Step 7: Update `_fundamentals_risk_block` to read structured metrics**

In `summary_context.py`, update `_fundamentals_risk_block` to prefer structured metrics over regex:

```python
def _fundamentals_risk_block(state: dict) -> str:
    """Extract fundamentals risk metrics from structured output OR raw text fallback."""
    structured = state.get("fundamentals_report_structured") or {}
    key_metrics = structured.get("key_metrics") or {}
    
    lines = []
    
    # Try structured metrics first
    if key_metrics.get("pe_ratio"):
        lines.append(f"P/E ratio: {key_metrics['pe_ratio']}x")
    if key_metrics.get("debt_equity_ratio"):
        lines.append(f"D/E ratio: {key_metrics['debt_equity_ratio']}")
    # ... etc for all metrics
    
    # Fallback to regex on raw report if structured is incomplete
    if not lines:
        fund_text = str(state.get("fundamentals_report") or "").lower()
        # ... existing regex logic ...
    
    if not lines:
        return ""
    
    return "### Fundamentals Risk Metrics\n" + "\n".join(lines) + "\n\n"
```

- [ ] **Step 8: Run test, confirm pass**

```bash
pytest tests/agents/analysts/test_fundamentals_metric_extraction.py -v
```

Expected: PASS.

- [ ] **Step 9: Run full suite**

```bash
pytest tests/ -v -m "not integration"
```

Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add tradingagents/agents/analysts/fundamentals_analyst.py tradingagents/agents/utils/output_validation.py tradingagents/agents/utils/summary_context.py tests/agents/analysts/test_fundamentals_metric_extraction.py
git commit -m "feat(fundamentals): extract and structure metrics in output, eliminate regex-only dependency"
```

---

# Acceptance Criteria — P2

After completion of all P2 tasks:

1. **P2.1 (Commodity timeframe tagging):**
   - Scanner context includes explicit `(daily)` and `(YoY)` labels for all commodity changes
   - No bare percentage changes without timeframe labels
   - Market analyst, macro synthesis agents test suite all green

2. **P2.2 (Research packet summary):**
   - `research_packet_summary` is non-empty after RM consistency guard passes
   - PM prompt receives summary as structured header
   - Summary includes: ticker, rating, confidence, entry/target, key bull/bear points
   - PM/trader downstream nodes all green

3. **P2.3 (Structured metric extraction):**
   - Fundamentals analyst extracts PE, D/E, FCF, operating margin, current ratio, working capital into typed fields
   - `fundamentals_report_structured.key_metrics` contains extracted metrics at write time
   - `_fundamentals_risk_block` reads structured metrics (with regex fallback)
   - Research packet, debate brief, RM/Trader/PM all receive metrics correctly
   - `pytest tests/ -v -m "not integration"` — all green (2100+ tests)

---

# Links

- Source: `docs/superpowers/plans/2026-05-05-graph-quality-hardening.md` (P0/P1 parent plan)
- Blocked by: P0/P1 fixes must merge first
- Blocks: P3 (Research Judge, Portfolio Correlation node)
- Related: `docs/superpowers/plans/2026-05-04-historical-report-reuse.md` (P2.2 summary unblocks Stage 2)
