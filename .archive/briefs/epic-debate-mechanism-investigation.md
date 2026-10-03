# Epic: Investigate and Fix TradingAgents Debate Mechanism

**Date:** 2026-05-06
**Epic ID:** DEBATE-001
**Status:** Done
**Priority:** High

---

## Problem Statement

The TradingAgents debate mechanism is not functioning as designed. Two critical issues have been identified:

### Issue 1: Debate Counter Not Tracking

The `investment_debate_state["count"]` field is `None` in saved state logs, suggesting the debate round counter is not incrementing. The `conditional_logic.py` checks `count >= 2 * max_debate_rounds` to determine when to stop the debate, but if count is never set, the debate may not terminate correctly or may not run the intended number of rounds.

### Issue 2: Quick-Think Model Echoes Deep-Think Model

Both the Bull Researcher and Bear Researcher use the `quick_think_llm` (`openai/gpt-5.4-mini` via OpenRouter). Observed output shows identical reasoning blocks repeated 5+ times with no substantive disagreement. The quick model appears to be deferential/compliant rather than adversarial, defeating the purpose of a debate round.

**Evidence:**
- IONQ analysis: 5 identical "Sell" blocks with identical reasoning
- RGTI analysis: 5 identical "Hold" blocks with identical reasoning
- Both got "Underweight" from the Research Manager — no actual divergence in debate

### Issue 3 (Suspected): Single-Provider Bias

Both deep and quick models route through the same provider (OpenRouter → OpenAI). If the models share training data and alignment, they may converge on the same conclusion regardless of assigned persona (bull vs bear). True debate requires either:
- Different model families (e.g., GPT vs Claude vs Gemini)
- Explicit prompt engineering forcing disagreement
- Temperature/adversarial settings in quick model

---

## Stories

### DEBATE-001-S01 — Fix Debate Counter Increment

**What:** The debate state counter (`investment_debate_state["count"]`) must increment on each round and be checked by `conditional_logic.should_continue_debate()`.

**Investigation:**
1. Trace where `count` is initialized in `tradingagents/agents/` debate agent code
2. Trace where `count` should be incremented (after each bull/bear response)
3. Check if `count` is being reset to `None` somewhere in the state pipeline
4. Verify `conditional_logic.py` logic handles `None` correctly or fails fast

**Acceptance:**
- After running `just analyze <TICKER>`, saved state log shows `count` as integer ≥ 0
- `count` increments by 1 per debate round (2 per full cycle: bull + bear)
- Debate terminates after `max_debate_rounds` cycles (default: 1 = 2 turns)
- No `None` values in debate state

**Estimate:** 0.5d

---

### DEBATE-001-S02 — Verify Actual Debate Content (Not Echo)

**What:** Determine whether the repeated output is (a) actual repeated LLM calls with same result, or (b) debug logging artifacts from LangGraph node emission.

**Investigation:**
1. Enable verbose logging in `analyze.py` to see individual LLM calls
2. Check if bull and bear agents receive different system prompts/personas
3. Inspect `tradingagents/agents/researcher.py` for bull/bear prompt templates
4. Compare bull response vs bear response in state log — are they genuinely different messages?

**Acceptance:**
- Can distinguish between "same content from different agents" vs "same content repeated in logs"
- If content is genuinely identical: the prompt engineering is broken (proceed to S03)
- If content is log artifact: fix the debug output to show one summary per agent
- Document finding in debrief

**Estimate:** 0.5d

---

### DEBATE-001-S03 — Strengthen Adversarial Prompts or Model Selection

**What:** If S02 confirms the quick model is echoing, implement one or more fixes:

**Option A — Explicit adversarial prompts:**
- Bull researcher prompt: "You are a bull investor. Argue FOR buying this stock. Challenge the bear case."
- Bear researcher prompt: "You are a bear investor. Argue AGAINST buying this stock. Challenge the bull case."
- Current prompts may not be forceful enough in persona enforcement

**Option B — Model diversity:**
- Use different model families for bull vs bear (e.g., bull = Claude, bear = GPT)
- This requires multi-provider configuration in `trading_graph.py`
- May increase cost but increases debate divergence

**Option C — Temperature/constraints:**
- Increase temperature on quick model for more variability
- Add explicit instruction: "Disagree with the previous analyst's conclusion"
- Add constraint: "Your response must argue the opposite of the last message"

**Acceptance:**
- After fix, run `just analyze` on a volatile ticker (e.g., TSLA, crypto-adjacent)
- Bull and bear produce meaningfully different reasoning (not identical paragraphs)
- Research Manager sees actual conflict to resolve, not confirmation
- Document which fix was applied and why

**Estimate:** 1d

---

### DEBATE-001-S04 — Add Debate Quality Metrics to Output

**What:** Surface debate quality in the final output so users can judge whether to trust the recommendation.

**Metrics:**
- Number of debate rounds actually executed (vs configured)
- Bull/bear agreement score (semantic similarity of their conclusions)
- Whether the Research Manager had to break a tie or confirmed consensus
- Model names used for each role

**Acceptance:**
- Final trade decision includes a "Debate Quality" section
- If bull/bear agree → "Strong consensus" vs "Weak consensus (single round)"
- If bull/bear disagree → "Contested: Research Manager broke tie toward [direction]"
- Metrics stored in state log for future analysis

**Estimate:** 0.5d

---

## Exit Criteria

- S01: Debate counter increments correctly and terminates as configured
- S02: Root cause of echo identified and documented
- S03: Fix applied — bull/bear produce meaningfully different reasoning
- S04: Debate quality metrics visible in output
- All changes pass `just check` and `test-smoke`

---

## Technical Notes

- `tradingagents/graph/conditional_logic.py` — debate termination logic
- `tradingagents/graph/setup.py` — agent creation (bull/bear get `quick_think_llm`)
- `tradingagents/graph/trading_graph.py` — LLM client creation and config
- `tradingagents/agents/researcher.py` — bull/bear prompt templates
- `scripts/py/analyze.py` — CLI entry point, config override
- Saved state logs: `~/.tradingagents/logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_*.json`

---

## Dependencies

- `OPENROUTER_API_KEY` must be set (for testing fixes)
- `just check` must pass before any changes
- No schema changes required

---

## Risks

- **Model cost:** Testing with multiple providers increases API spend
- **Prompt engineering is fragile:** A fix for one ticker may not generalize
- **LangGraph complexity:** State management bugs may be in LangGraph itself, not our code
- **Breaking change risk:** If debate mechanism changes, output format may change → downstream consumers (dashboard) need updates

---

## Stretch

- A/B test: run same ticker with single model vs diverse models, measure decision divergence
- Add "devil's advocate" agent that always argues opposite of consensus
- Cache debate responses to avoid redundant LLM calls on re-runs
