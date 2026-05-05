# Graph Quality Hardening — Prioritized Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the most impactful signal-integrity and reasoning-quality gaps found in run `01KQSGM0TM04CAT361N3ZQ4RXW` (2026-05-04), prioritised by implementation effort. All P0/P1 fixes are prompt or tiny-code changes — no new nodes, no architectural rewrites.

**Architecture:** Targeted prompt additions to existing agent files + one-line output field fixes. Each task is independently committable and testable in isolation.

**Tech Stack:** Python 3.11+, pytest, existing agent prompt construction patterns.

**Source reviews:** Run analysis reviews from 2026-05-04 (deep systems review + surgical fix proposal).

---

## Priority Map

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | Set `verified: true` on surviving claims in fact checker | 5 min | Eliminates audit blind spot; makes sanitization outcome legible |
| **P0** | Add mandatory conflict-resolution clause to Research Manager | 10 min | Forces RM to address fundamental bearish data, not just dismiss it |
| **P0** | Add ATR/volatility sanity check to Trader prompt | 10 min | Prevents stop-losses sized on stale volatility after gap days |
| **P0** | Constrain `regime_alignment` field in PM output schema | 5 min | Eliminates "nostalgic-interference" hallucination class |
| **P1** | Inject fundamentals worst-case metrics into debate brief | 20 min | PE, D/E, FCF reach Bull/Bear researchers — currently die before debate |
| **P1** | Add source-citation rule to risk debater prompts | 10 min | Stops hallucinated statistical claims ("65% mean-reversion probability") |
| **P1** | Mandate `sentiment_report` in social media analyst | 10 min | Fills empty signal dimension |
| **P1** | Add insider net balance field to news structured output | 20 min | Surfaces insider buy vs sell contradiction at structured level |
| **P2** | Timeframe-tag gold/commodity data in scanner context | 30 min | Eliminates YoY vs daily cross-contamination propagating 12+ nodes |
| **P2** | Generate `research_packet_summary` at RM consistency guard | 30 min | Creates compressed memory artifact for PM; enables future cross-run context |
| **P2** | Structured metric extraction in fundamentals analyst | 45 min | Replaces prompt-anchored regex with Pydantic schema; stores pe_ratio/D_E/FCF in key_metrics at write time; eliminates regex drift risk |
| **P3** | Separate Research Judge from Research Manager | 60 min | Eliminates RM-as-own-judge bias; adds adversarial review layer |
| **P3** | Portfolio correlation check node | 60 min | Surfaces sector concentration risk across simultaneously analyzed instruments |

Do not skip P0 tasks. Do not start P2 until P0+P1 are merged.

---

# P0 Fixes — Do These First (< 30 min total)

---

## Task P0.1: Set `verified: true` on surviving claims in news fact checker

**Problem:** After `sanitize_structured_news_payload` runs, every claim that survives has `"verified": null`. The fact checker IS working (bad claims are removed), but the audit trail doesn't reflect it — all claims look unverified to downstream consumers.

**File:** `tradingagents/agents/managers/news_fact_checker.py`

**Test file:** `tests/agents/managers/test_news_fact_checker_verified_field.py`

- [ ] **Step 1: Write failing test**

```python
# tests/agents/managers/test_news_fact_checker_verified_field.py
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_payload(claims: list[dict]) -> dict:
    return {"claims": claims, "summary": "test", "ticker": "AAPL", "date": "2026-05-05"}


def test_surviving_claims_have_verified_true():
    """Claims that pass sanitization must have verified set to True."""
    from tradingagents.agents.managers.news_fact_checker import create_news_fact_checker
    from tradingagents.memory.news_evidence import NewsEvidenceStore, NewsEvidenceRecord

    store = MagicMock(spec=NewsEvidenceStore)
    store.fetch_records.return_value = [
        MagicMock(
            spec=NewsEvidenceRecord,
            evidence_id="ev-001",
            source="MarketWatch",
            ticker="AAPL",
        )
    ]

    payload = _make_payload([
        {
            "claim": "AAPL reported earnings beat",
            "evidence_id": "ev-001",
            "source": "MarketWatch",
            "verified": None,
            "flagged": None,
        }
    ])

    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-05",
        "run_id": "RUN1",
        "news_report": "AAPL earnings beat.",
        "news_report_structured": payload,
        "abort_signal": None,
    }

    with patch(
        "tradingagents.agents.managers.news_fact_checker.sanitize_structured_news_payload",
        return_value=(payload, []),
    ), patch(
        "tradingagents.agents.managers.news_fact_checker.validate_structured_news_payload",
        return_value=MagicMock(is_valid=True, payload=payload, code="ok", reason=""),
    ), patch(
        "tradingagents.agents.managers.news_fact_checker.render_structured_news_payload",
        return_value="AAPL earnings beat.",
    ), patch(
        "tradingagents.agents.managers.news_fact_checker.validate_news_analysis_detailed",
        return_value=MagicMock(is_valid=True),
    ):
        node = create_news_fact_checker(MagicMock(), store)
        result = node(state)

    structured = result.get("news_report_structured") or {}
    claims = structured.get("claims") or []
    assert len(claims) == 1
    assert claims[0].get("verified") is True, f"expected verified=True, got {claims[0].get('verified')!r}"
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/agents/managers/test_news_fact_checker_verified_field.py -v
```
Expected: FAIL — `verified` is `None`.

- [ ] **Step 3: Fix in `news_fact_checker.py`**

In `news_fact_checker_node`, immediately after `sanitize_structured_news_payload` returns and before the `removed_claims` branch, add:

```python
        # Mark surviving claims as verified (they passed evidence-ID sanitization).
        for claim in (sanitized_payload.get("claims") or []):
            if isinstance(claim, dict):
                claim["verified"] = True
                if claim.get("flagged") is None:
                    claim["flagged"] = False
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/agents/managers/test_news_fact_checker_verified_field.py -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v -m "not integration"
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/managers/news_fact_checker.py tests/agents/managers/test_news_fact_checker_verified_field.py
git commit -m "fix(fact-checker): set verified=True on claims that survive sanitization"
```

---

## Task P0.2: Mandatory conflict-resolution clause in Research Manager

**Problem:** When Fundamentals Analyst outputs catastrophic deterioration (FCF -73%, negative working capital) but the scanner flags "Golden Overlap", the RM dismisses fundamentals without addressing them. The review rates this CRITICAL — it will cause portfolio to buy value traps.

**File:** `tradingagents/agents/managers/research_manager.py`

- [ ] **Step 1: Read current RM system prompt**

```bash
grep -n "system\|MANDATORY\|conflict\|fundamental\|bearish" tradingagents/agents/managers/research_manager.py | head -30
```

- [ ] **Step 2: Locate where the system/user prompt is assembled** in `research_manager_node`. Find the string that contains the RM's role/task instructions.

- [ ] **Step 3: Add the conflict-resolution clause**

Append the following block to the RM system prompt, immediately before the output format instructions:

```
## MANDATORY CONFLICT RESOLUTION

Before writing your final recommendation, you MUST complete this checklist:

1. List every bearish or risk point from the Fundamentals Analyst report (FCF, debt, margins, working capital, peer rank).
2. For each point, provide a data-backed counter-argument explaining why it is NOT a deal-breaker given current conditions.
3. If you cannot provide a data-backed counter-argument for ANY fundamental deterioration flag (e.g. negative working capital, FCF decline >50%, operating margin <0%), you MUST downgrade your rating by at least one level.
4. Scanner Context signals ("Golden Overlap", "Smart Money Drift", institutional accumulation) are SUPPORTING evidence — they CANNOT override actual financial deterioration without a specific catalyst that explains why the deterioration is temporary.
5. Your final rating must be consistent with the weakest un-rebutted fundamental risk you identified.
```

- [ ] **Step 4: Write a prompt-content test**

Create `tests/agents/managers/test_rm_conflict_resolution_clause.py`:

```python
import tradingagents.agents.managers.research_manager as rm_module
import inspect


def test_research_manager_prompt_contains_conflict_resolution():
    src = inspect.getsource(rm_module)
    assert "MANDATORY CONFLICT RESOLUTION" in src, (
        "Research Manager prompt must contain MANDATORY CONFLICT RESOLUTION clause"
    )
    assert "cannot override actual financial deterioration" in src
```

- [ ] **Step 5: Run, confirm pass**

```bash
pytest tests/agents/managers/test_rm_conflict_resolution_clause.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/managers/research_manager.py tests/agents/managers/test_rm_conflict_resolution_clause.py
git commit -m "fix(research-manager): add mandatory conflict-resolution clause for fundamentals vs scanner"
```

---

## Task P0.3: ATR/volatility sanity check in Trader prompt

**Problem:** Trader uses 30-day ATR for stop-loss sizing even after a stock gaps 20-30% in a single session. The review rates this HIGH — guaranteed whipsaw stop-outs. PM caught it this run; it won't always.

**File:** `tradingagents/agents/trader/trader.py`

- [ ] **Step 1: Locate the Trader system message content** (around line 105 in the current file).

- [ ] **Step 2: Add volatility guardrail section**

Append this block to the Trader system prompt, after the STRICT CONSTRAINTS section:

```
## VOLATILITY & STOP-LOSS SANITY CHECK (mandatory on every run)

Before setting stop-loss and position size:
1. REALIZED RANGE CHECK: Compare the current session high/low range against the provided ATR.
   - If (session_high - session_low) > ATR, the ATR is STALE. Do not use it directly.
2. ADJUSTED STOP-LOSS RULE: If realized range > ATR, place stop-loss at LEAST 1.5× the provided ATR below entry OR below the nearest named structural support level — whichever is wider.
3. ANTI-AIR-POCKET RULE: A stop-loss must be anchored to a named structural level (prior day close, 200-day SMA, earnings gap fill, named support from the market report). Never place a stop in a price zone with no structural reference.
4. POSITION SIZE RECONCILIATION: If the wider stop forces your dollar-at-risk above your target, reduce share count to keep total risk constant — do not widen the stop AND keep the same size.
```

- [ ] **Step 3: Write a prompt-content test**

Create `tests/agents/trader/test_trader_volatility_guardrail.py`:

```python
import tradingagents.agents.trader.trader as trader_module
import inspect


def test_trader_prompt_contains_volatility_sanity_check():
    src = inspect.getsource(trader_module)
    assert "VOLATILITY & STOP-LOSS SANITY CHECK" in src
    assert "ANTI-AIR-POCKET RULE" in src
    assert "structural" in src
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/agents/trader/test_trader_volatility_guardrail.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/trader/trader.py tests/agents/trader/test_trader_volatility_guardrail.py
git commit -m "fix(trader): add ATR freshness and anti-air-pocket stop-loss guardrail"
```

---

## Task P0.4: Constrain `regime_alignment` field in PM output

**Problem:** PM output produced `"regime_alignment": "nostalgic-interference: US CDS -6.08..."` — a hallucinated composite string. The review identifies this as prompt-boundary fraying in the JSON output schema.

**File:** `tradingagents/agents/managers/portfolio_manager.py`

- [ ] **Step 1: Locate PM prompt output instructions** — find where the PM's JSON output schema is described.

- [ ] **Step 2: Add schema constraint for `regime_alignment`**

Find the section that describes the `forensic_report` or `regime_alignment` output field and add:

```
IMPORTANT OUTPUT CONSTRAINTS:
- The `regime_alignment` field in any forensic or summary output MUST use exactly one of:
  ["macro-aligned", "sector-aligned", "regime-divergent", "uncorrelated"]
  Do NOT generate descriptive phrases, portmanteau terms, or compound strings for this field.
  If the alignment is unclear, use "uncorrelated".
```

- [ ] **Step 3: Write a prompt-content test**

Create `tests/agents/managers/test_pm_regime_alignment_constraint.py`:

```python
import tradingagents.agents.managers.portfolio_manager as pm_module
import inspect


def test_pm_prompt_constrains_regime_alignment_field():
    src = inspect.getsource(pm_module)
    assert "macro-aligned" in src
    assert "regime-divergent" in src
    assert "uncorrelated" in src
    assert "Do NOT generate descriptive phrases" in src
```

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/managers/portfolio_manager.py tests/agents/managers/test_pm_regime_alignment_constraint.py
git commit -m "fix(pm): constrain regime_alignment to allowed enum values"
```

---

# P1 Fixes — High Impact, One Session

---

## Task P1.1: Inject fundamentals worst-case metrics into debate brief ✅ Done

**Problem:** PE ratio (83x NOK), D/E (15.63), FCF trends, and negative working capital (TEAM) are produced by the Fundamentals Analyst but never reach Bull/Bear researchers or RM/Trader/risk debaters.

**Solution implemented (two layers):**

**Layer 1 — `build_debate_evidence_brief` (reaches Bull/Bear researchers):**
Commit 64ce49e added regex extraction from the raw `fundamentals_report` text in `build_debate_evidence_brief`. Patterns: P/E, D/E, FCF margin.

**Layer 2 — `build_research_packet` (reaches RM, Trader, risk debaters):**
`_fundamentals_risk_block(state)` appended to `build_research_packet`. Also reads from the raw `fundamentals_report` text using regex — NOT from `fundamentals_report_structured.key_metrics` (which only stores `numeric_mentions/summary_table_rows`, not valuation ratios).

**Design decision — prompt-anchored regex:**
The fundamentals analyst prompt now mandates exact output phrases:
```
- P/E ratio: <val>x
- D/E ratio: <val>
- Free cash flow: <pct> YoY
- Operating margin: <pct>
- Current ratio: <val>
- Working capital: <$val> (positive/negative)
```
The regex is anchored to these phrases but also covers common deviations (long form, no colon, FCF abbreviation, "price-to-earnings", "debt-to-equity"). Tests validate both the mandated format and deviation coverage.

**Files modified:**
- `tradingagents/agents/analysts/fundamentals_analyst.py` — REQUIRED METRICS FORMAT section
- `tradingagents/agents/utils/summary_context.py` — `_fundamentals_risk_block` + `build_debate_evidence_brief` regex
- `tests/agents/utils/test_summary_context_fundamentals.py` — 9 tests covering mandated format, deviations, and no-match cases

**Known limitation / future task (P2+):**
The regex approach assumes the LLM followed the prompt. If the model drifts far from the template, metrics will be silently absent from the block. The robust fix is to add a Pydantic-schema structured extraction step at `build_fundamentals_report_structured` time (same pattern as `build_investment_plan_structured`) that stores `pe_ratio`, `debt_equity_ratio`, etc. in `key_metrics` at write time. This avoids regex entirely. Tracked as a future P2 task.

---

## Task P1.2: Source-citation rule in risk debater prompts

**Problem:** All three risk debaters produced hallucinated statistical claims: "65% mean-reversion probability", "2.5x standard deviation bands" — no sources, zero evidence IDs. These are marked `"excluded per protocol"` in the synthesis but still appear in debate history and influence the PM.

**Files:**
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`

- [ ] **Step 1: Add citation rule to all three debater prompts**

In each debater's system prompt, add:

```
## EVIDENCE CITATION RULES (mandatory)

- Any numerical probability, rate, or statistical distribution you cite MUST appear in the analyst reports provided to you. Do NOT generate statistics from training data.
- If you want to express a probability or rate that is your own judgment (not from reports), preface it with: "Analyst estimate, unverified:"
- Hallucinated precision ("65% probability", "2.5 standard deviations") without a report source will be filtered. State your argument without false precision instead.
```

- [ ] **Step 2: Write a prompt-content test for all three**

Create `tests/agents/risk_mgmt/test_risk_debater_citation_rules.py`:

```python
import inspect
import tradingagents.agents.risk_mgmt.aggressive_debator as agg
import tradingagents.agents.risk_mgmt.conservative_debator as con
import tradingagents.agents.risk_mgmt.neutral_debator as neu


def test_all_debaters_have_citation_rule():
    for module, name in [(agg, "aggressive"), (con, "conservative"), (neu, "neutral")]:
        src = inspect.getsource(module)
        assert "EVIDENCE CITATION RULES" in src, f"{name} debater missing citation rules"
        assert "Analyst estimate, unverified" in src, f"{name} debater missing unverified label"
```

- [ ] **Step 3: Run, confirm pass.**

- [ ] **Step 4: Commit**

```bash
git add tradingagents/agents/risk_mgmt/ tests/agents/risk_mgmt/test_risk_debater_citation_rules.py
git commit -m "fix(risk-debaters): add mandatory evidence citation rule to prevent hallucinated statistics"
```

---

## Task P1.3: Mandate `sentiment_report` in social media analyst

**Problem:** `sentiment_report` is defined in AgentState and consumed by downstream nodes but was **blank** for both instruments in this run. The entire social sentiment signal dimension is missing.

**File:** `tradingagents/agents/analysts/social_media_analyst.py`

- [ ] **Step 1: Check what generates `sentiment_report`**

```bash
grep -n "sentiment_report\|return\|output" tradingagents/agents/analysts/social_media_analyst.py | head -20
```

- [ ] **Step 2: Confirm whether the node always returns a non-empty `sentiment_report`**

If the node can return `sentiment_report: ""` or omit it, locate the path and add a fallback:

```python
sentiment_report = str(output_content or "").strip()
if not sentiment_report:
    sentiment_report = f"{ticker} Sentiment: No social sentiment signals available for this period."
```

- [ ] **Step 3: Add a mandatory 3-sentence minimum requirement to the prompt**

Find the social media analyst's task instructions and add:

```
Your output MUST include at minimum 3 sentences describing the current sentiment signal — 
even if signals are weak or neutral. "No data available" is not acceptable. 
State: (1) the directional bias (bullish/bearish/neutral), (2) the primary evidence, 
(3) the confidence level and key risk to your assessment.
```

- [ ] **Step 4: Write regression test** asserting `sentiment_report` in the returned state is non-empty.

- [ ] **Step 5: Run, confirm pass.**

- [ ] **Step 6: Commit:** `fix(social-analyst): mandate non-empty sentiment_report output`

---

## Task P1.4: Add insider net-balance field to news structured output

**Problem:** The Prosi insider SELL (April 29, 15,000 shares at EUR 10.04) was captured in the NOK news report but never surfaced as a structured signal. The CEO Hotard insider BUY appeared but the contradictory SELL was invisible to the Bear researcher. The net transaction balance (buys - sells by share count) would make the contradiction machine-readable.

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py` (where `build_news_report_structured` is defined)

- [ ] **Step 1: Read `build_news_report_structured`**

```bash
grep -n "def build_news_report_structured\|insider\|net_balance" tradingagents/agents/utils/output_validation.py | head -20
```

- [ ] **Step 2: Add `insider_net_balance_shares` computed field**

In `build_news_report_structured` (or in the structured payload schema), after claims are processed:

```python
def _compute_insider_net_balance(claims: list[dict]) -> dict | None:
    buy_shares = 0
    sell_shares = 0
    for claim in (claims or []):
        text = str(claim.get("claim") or "").lower()
        shares_str = str(claim.get("shares") or "0").replace(",", "")
        try:
            shares = abs(float(shares_str))
        except (ValueError, TypeError):
            shares = 0
        if "insider" in text or "director" in text or "executive" in text:
            if any(w in text for w in ["buy", "bought", "purchase", "acquired"]):
                buy_shares += shares
            elif any(w in text for w in ["sell", "sold", "liquidat", "divest"]):
                sell_shares += shares
    if buy_shares == 0 and sell_shares == 0:
        return None
    return {
        "buy_shares": buy_shares,
        "sell_shares": sell_shares,
        "net_shares": buy_shares - sell_shares,
        "bias": "bullish" if buy_shares > sell_shares else "bearish" if sell_shares > buy_shares else "neutral",
    }
```

Include this in the structured payload under `"insider_activity"` key.

- [ ] **Step 3: Write test asserting insider_activity is populated when claim text contains insider buy/sell.**

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit:** `feat(news-structured): add insider_net_balance_shares to structured output`

---

# P2 Fixes — Larger, Next Sprint

---

## Task P2.1: Timeframe-tag commodity data in scanner context

**Problem:** `gold -12%` (YoY) and `Gold $4,583 (-1.01%)` (daily) both flow into agent context as if concurrent. 12+ nodes cite "gold's -12% collapse" as a live macro signal. This needs separate fields in the scanner packet.

**Approach:**
- In the scanner output schema / context packet builder, split price change fields into `*_change_pct_daily` and `*_change_pct_yoy`.
- In the scanner context text sent to agents, always label the timeframe: `"Gold: -1.01% (daily), -12.0% (YoY)"` instead of a bare `-12%`.
- Add a validation step that rejects bare change_pct fields without a timeframe label.

**Files to touch:** Scanner output builders, `scanner_graph_context_text` formatter. Exact paths require reading the scanner pipeline first.

---

## Task P2.2: Generate `research_packet_summary` at RM consistency guard

**Problem:** `research_packet_summary` field is empty at PM level. PM has no compressed memory of what the analyst chain concluded. This also blocks future cross-run context (historical-report-reuse plan Stage 2).

**Approach:**
- After RM consistency guard passes (`status: "ok"`), generate a 400-token structured summary of: ticker, date, top 3 bull points, top 3 bear points, final RM rating, key risk levels.
- Store as `research_packet_summary` in AgentState.
- PM prompt receives this as a structured header above the full research packet.

**Files to touch:** `tradingagents/agents/managers/rm_consistency_guard.py` (or wherever the consistency guard node lives), `AgentState` definition.

---

# P3 Fixes — Architecture Investments (Future Sprints)

---

## Task P3.1: Separate Research Judge from Research Manager

**Problem:** `investment_debate_state.judge_decision` and `investment_plan` are byte-for-byte identical — the RM writes both. The RM is simultaneously synthesizer and judge of its own analysis. Confirmation bias has no structural check.

**Approach:** Add a lightweight `research_judge` node that:
1. Receives the RM's `investment_plan` as input.
2. Runs a single LLM call with the prompt: *"You are a skeptical senior analyst reviewing a junior's recommendation. Identify: (1) any bearish evidence cited but dismissed without a data-backed rebuttal, (2) any HIGH-confidence rating on a stock with >2 fundamental red flags, (3) whether the recommendation is internally consistent. Output: approved / downgrade-required / flag-for-pm + reason."*
3. If `approved`: passes through unchanged. If `downgrade-required`: adjusts the rating (BUY→HOLD, HOLD→AVOID). If `flag-for-pm`: adds a warning block to the investment_plan.

**Files to touch:** `tradingagents/graph/setup.py` (new node + edge), new `tradingagents/agents/managers/research_judge.py`.

---

## Task P3.2: Portfolio correlation check node

**Problem:** TEAM and NOK are both high-beta tech momentum names analyzed and approved independently. No node checks combined sector exposure, beta overlap, or aggregate VaR.

**Approach:** After all per-ticker pipelines complete and before the final PM decision, add a `portfolio_correlation_check` node that:
1. Reads all candidate `trader_investment_plan` structs for the current run.
2. Computes sector concentration (sum of proposed positions by sector).
3. If any sector would exceed the configured `max_sector_exposure_pct`, outputs a warning block into PM context.
4. Flags if two proposals are in the same sector with combined weight > threshold.

**Files to touch:** `tradingagents/graph/portfolio_setup.py`, new node file.

---

# Acceptance Criteria

After P0 tasks:
- `verified: true` on every claim in `news_report_structured` that passed sanitization.
- Research Manager prompt contains explicit bearish-rebuttal requirement.
- Trader prompt contains ATR freshness check and anti-air-pocket rule.
- PM `regime_alignment` field is constrained to 4 allowed values.
- `pytest tests/ -v -m "not integration"` — all green.

After P1 tasks additionally:
- PE ratio, D/E, FCF trend appear in research packet that reaches Bull/Bear debate.
- Risk debater prompts require source citation or "unverified" label.
- `sentiment_report` is non-empty after social media analyst node.
- `news_report_structured` contains `insider_activity.net_shares` when insider transactions appear in claims.

---

# Links

- Related plan: `docs/superpowers/plans/2026-05-04-historical-report-reuse.md` (historical context + reflexion)
- Source run: `reports/daily/2026-05-04/01KQSGM0TM04CAT361N3ZQ4RXW`
- Both P1.1 (fundamentals in debate) and the historical-report-reuse Stage 2 (prior analyst context) address the same root cause from different angles — implement together for maximum effect.
