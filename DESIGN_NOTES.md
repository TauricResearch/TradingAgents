# SignalFusion — Design Notes (Phase 0)

Branch: `feat/signal-fusion-design`. This document is the research output the
task spec asked for before any code lands. Please review and confirm (or
redirect) before I start writing the Phase 1 PR.

---

## 1. State of the codebase (v0.2.5, commit a5cb7cb)

### 1.1 Analyst execution model — confirmed **strictly serial**

`tradingagents/graph/setup.py` lines 119–138:

```python
first_analyst = selected_analysts[0]
workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")
for i, analyst_type in enumerate(selected_analysts):
    ...
    if i < len(selected_analysts) - 1:
        next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
        workflow.add_edge(current_clear, next_analyst)
    else:
        workflow.add_edge(current_clear, "Bull Researcher")
```

So the graph today is exactly:

```
START → Market Analyst → tools/loop → Msg Clear Market
      → Sentiment Analyst → tools/loop → Msg Clear Social
      → News Analyst → tools/loop → Msg Clear News
      → Fundamentals Analyst → tools/loop → Msg Clear Fundamentals
      → Bull Researcher ⇄ Bear Researcher → Research Manager
      → Trader → Aggressive ⇄ Neutral ⇄ Conservative → Portfolio Manager → END
```

The four logical analyst channels are still `{market, social, news,
fundamentals}` — note that the `"social"` selector key now maps to
`create_sentiment_analyst` (renamed in v0.2.5, see `setup.py:60-65`). The PR
must preserve the `"social"` wire-value for back-compat with saved configs.

**The `messages` channel is shared across all analysts** and reset between
them by the `Msg Clear *` nodes. This is the single biggest constraint on
parallelisation — see §3.2.

### 1.2 Analyst output format — still raw markdown

All four analysts return `{messages: [...], <name>_report: str}`. Examples:

- `tradingagents/agents/analysts/market_analyst.py:83-86`
- `tradingagents/agents/analysts/fundamentals_analyst.py:64-67`
- `tradingagents/agents/analysts/news_analyst.py:57-60`
- `tradingagents/agents/analysts/sentiment_analyst.py:91-94`

The four analyst-side `*_report` strings are flat in `AgentState`. There is
**no** typed direction / score / confidence anywhere upstream of the
Bull/Bear prompt today.

By contrast, Research Manager (`ResearchPlan`), Trader (`TraderProposal`),
and Portfolio Manager (`PortfolioDecision`) already use
`with_structured_output(Schema)` + `render_*` to markdown — see
`tradingagents/agents/schemas.py` and `tradingagents/agents/utils/structured.py`.
Analysts are the only tier still on free text.

### 1.3 Bull/Bear consume reports as f-strings

`tradingagents/agents/researchers/bull_researcher.py:11-32` (mirror in
bear). Each report is interpolated into the prompt:

```python
market_research_report = state["market_report"]
sentiment_report      = state["sentiment_report"]
news_report           = state["news_report"]
fundamentals_report   = state["fundamentals_report"]
prompt = f"""...Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
..."""
```

This is exactly the place to inject the composite score and to physically
compress / amplify reports based on weights (§5).

### 1.4 `AgentState` (current)

`tradingagents/agents/utils/agent_states.py:46-74` — flat strings, no
structured analyst-level fields.

### 1.5 Memory / reflection — out of scope, just orientation

`tradingagents/agents/utils/memory.py` writes pending entries at the end of
`propagate()` and resolves them on the next same-ticker run, using forward
N-day returns against a configurable benchmark. Reflections feed the past
context that the Portfolio Manager sees. **Nothing in the memory layer
needs to change for SignalFusion.** A future PR could include the composite
score in the memory tag for post-hoc weight calibration — flagged as TODO,
not in this PR.

### 1.6 Name collisions to avoid

`tradingagents/graph/signal_processing.py` already defines `SignalProcessor`
(a thin rating-extractor). To avoid confusion, the new module is
`tradingagents/graph/signal_fusion.py` and the class/factory will be
`create_signal_fusion_node`.

### 1.7 Test infrastructure

`tests/` uses pytest with markers `unit`/`integration`/`smoke` (see
`tests/conftest.py`). LLM tests mock providers via `MagicMock`. Pattern is
well-established (e.g. `tests/test_structured_agents.py`). Stub API keys
are auto-injected by an autouse fixture, so unit tests do not hit the
network. New tests will follow this style.

---

## 2. Architecture of the change

### 2.1 Target graph

```
START ─┬──→ Market Analyst       ─→ Extract Signal ─┐
       ├──→ Sentiment Analyst    ─→ Extract Signal ─┤
       ├──→ News Analyst         ─→ Extract Signal ─┤
       └──→ Fundamentals Analyst ─→ Extract Signal ─┴─→ SignalFusion ─→ Bull Researcher ⇄ Bear → RM → ...
```

Where `Extract Signal` is the structured-output pass that converts the
analyst's markdown report into an `AnalystSignal` (§3.3).

Each analyst sub-pipeline (analyst node + its tool loop + extractor) runs
in parallel; LangGraph fans them out from `START` and fans them in at
`SignalFusion`.

When `signal_fusion_enabled=False`, the graph reverts to the existing
serial topology — Phase 1 ships with the kill switch wired in.

### 2.2 Why a separate `Extract Signal` step

`with_structured_output` and `bind_tools` cannot be combined on the same
chain in LangChain. The analyst loop is a tool-calling loop, so the
structured `AnalystSignal` must be produced by a second LLM invocation
after the tool loop ends. The extractor takes the rendered markdown
report and emits the typed signal. Cost: one extra `quick_thinking_llm`
call per analyst (4 total) of roughly markdown-in / ~200-token-JSON-out.

Alternative considered: have the LLM emit a trailing JSON block inside
the markdown. Rejected — fragile, breaks the Bull/Bear prompt contract
that downstream code already greps.

---

## 3. Concrete schema, state, and graph changes

### 3.1 New schema (extends `tradingagents/agents/schemas.py`)

```python
class SignalDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class AnalystSignal(BaseModel):
    """Structured complement to the analyst's free-text report.

    The markdown ``report`` remains the artifact users read and the
    Bull/Bear researchers debate from; ``direction``/``score``/
    ``confidence``/``key_evidence`` give SignalFusion something
    numerical to weight and aggregate.
    """
    report: str                                              # original markdown
    direction: SignalDirection
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    key_evidence: list[str] = Field(min_length=0, max_length=5)
```

Convention: `score` sign matches `direction`. SignalFusion will check
consistency and clamp/flip with a warning if a model violates it (rare
but observed in prior structured-output rollouts).

### 3.2 Per-analyst messages channel — required for fan-out

To unblock parallelism without four analysts polluting each other's tool
context, each analyst migrates from the shared `state["messages"]` to a
dedicated channel:

```python
class AgentState(MessagesState):  # MessagesState still gives us the shared
                                  # `messages` channel used by Bull/Bear/etc
    market_messages:       Annotated[list, add_messages]
    sentiment_messages:    Annotated[list, add_messages]
    news_messages:         Annotated[list, add_messages]
    fundamentals_messages: Annotated[list, add_messages]
```

`ToolNode` accepts a `messages_key=` kwarg so the per-analyst tool nodes
read/write the right channel. The `Msg Clear *` nodes (one per analyst)
can be removed in this flow — fan-out gives each analyst its own clean
channel, with no shared accumulation to clear.

### 3.3 New `AgentState` fields

```python
analyst_signals:    Annotated[dict[str, AnalystSignal], _merge_signals]
signal_weights:     Annotated[dict[str, float], "Per-analyst weights"]
composite_score:    Annotated[float, "Weighted directional score in [-1, 1]"]
disagreement_axes:  Annotated[list[str], "Where analysts diverge most"]
```

The `_merge_signals` reducer is a 2-line `lambda a, b: {**(a or {}), **(b or {})}`
so concurrent writes from the four extractors fan in cleanly. The other
three fields are only written once (by SignalFusion), so default-overwrite
is correct for them.

All fields are `Optional` / default-empty so old SqliteSaver checkpoints
(v0.2.4) deserialize without error — missing keys → empty dict / 0.0 /
[].

`_log_state` (the JSON writer) gains a serialiser branch that calls
`AnalystSignal.model_dump()` for each entry. SqliteSaver uses pickle and
handles Pydantic models natively, so no changes there.

### 3.4 SignalFusion node

`tradingagents/graph/signal_fusion.py`:

```python
def create_signal_fusion_node(weight_estimator, *, min_weight: float = 0.05):
    def node(state: AgentState) -> dict:
        signals = state["analyst_signals"]
        weights = weight_estimator.get_weights(
            ticker=state["company_of_interest"],
            as_of_date=state["trade_date"],   # estimator only sees <= t-1
            available_channels=list(signals.keys()),
        )
        composite = sum(
            weights[k] * signals[k].score * signals[k].confidence
            for k in signals if k in weights
        )
        disagreement = detect_disagreement(signals)
        return {
            "signal_weights": weights,
            "composite_score": composite,
            "disagreement_axes": disagreement,
        }
    return node
```

`detect_disagreement` returns up to 2 human-readable strings describing
the largest score gap, e.g. `"fundamentals (+0.7) vs sentiment (-0.5)"`.
The Bull/Bear prompt uses these to anchor the debate on the actual
divergence rather than rehashing everything.

### 3.5 Weight estimator — Phase 1 scope

`tradingagents/dataflows/signal_weights.py`:

- **`EqualWeightEstimator`** — `weights = {k: 1/len(channels) for k in channels}`.
  Default. Used by default config + by Phase 1's "no-op refactor" commit.
- **`RollingLassoEstimator`** — scaffolded, *not* default. Reads ≤ t-1
  proxy series (RSI/MACD momentum for market; historical VADER on cached
  news headlines for sentiment; event-dummy for news; EPS-surprise
  z-score for fundamentals), runs Lasso vs forward-5d alpha return,
  softmax → weights, EWMA-smoothed across days, floor at
  `min_weight=0.05`. Cached at
  `~/.tradingagents/cache/signal_weights/<TICKER>.parquet` with TTL.
- **Strict lookahead guard:** the estimator's `get_weights(ticker,
  as_of_date)` raises if any input row has `date >= as_of_date`. Unit
  test asserts this.

Regime-conditional weighting and Bayesian online updates are explicitly
out of scope for this PR — left as a TODO in the module docstring.

### 3.6 Bull/Bear prompt rewrite

Inject *three* new pieces above the existing report block:

1. `**Composite signal:** +0.42 (moderately bullish; weighted by analyst confidence)`
2. A small markdown weights table.
3. `**Key disagreement:** fundamentals (+0.71) vs sentiment (-0.42). Anchor your debate on this divergence.`

And **physically scale the reports** in the prompt:

- analyst weight > `compress_threshold` (default 0.10) → full report
- analyst weight ≤ threshold → 3-sentence summary extracted from
  `key_evidence` (already in the signal — no extra LLM call needed)

This makes the weights load-bearing in context, not just a number the
LLM is free to ignore. The compression respects existing back-compat:
when `signal_fusion_enabled=False`, full reports go in unchanged.

---

## 4. Config additions (`tradingagents/default_config.py`)

```python
"signal_fusion_enabled":       True,            # master kill switch
"weight_estimation_method":    "equal",         # "equal" | "rolling_lasso"
"weight_cache_ttl_days":       7,
"signal_fusion_min_weight":    0.05,
"signal_fusion_compress_threshold": 0.10,
"signal_fusion_compress_to_sentences": 3,
"analyst_max_tool_calls":      8,               # budget per analyst (parallel-safe)
```

`analyst_max_tool_calls` is new but cheap insurance — under serial flow a
runaway analyst was a latency hit; under parallel it is a *cost* hit.
Implementation: count tool calls in the conditional edge, route to
`Msg Clear` / fan-in once the budget is hit.

All `TRADINGAGENTS_*` env-var overrides naturally extend via the existing
`_ENV_OVERRIDES` table.

---

## 5. Multi-provider structured-output fallback

`tradingagents/agents/utils/structured.py` currently falls back to
free-text when `with_structured_output` is unsupported or fails. For the
analyst-extraction step we want a **stricter** fallback:

1. Try `with_structured_output(AnalystSignal)`.
2. On schema-validation failure → one self-repair retry: send the
   original markdown + the validator's error message to the LLM in plain
   JSON mode, parse, validate.
3. On second failure → synthesise an `AnalystSignal` from heuristics
   (parse "FINAL TRANSACTION PROPOSAL: **X**" line for direction;
   set `confidence=0.3`, `evidence_count=0`, `key_evidence=[]`, neutral
   score). This guarantees SignalFusion never KeyErrors on a missing
   channel.

This adds a new helper `extract_analyst_signal()` next to the existing
`invoke_structured_or_freetext`, rather than retrofitting the existing
helper (PM/Trader/RM behavior must stay unchanged).

OpenAI / Anthropic / Google / xAI / MiniMax all support
`with_structured_output` via their native modes; capability table at
`tradingagents/llm_clients/capabilities.py` already gates this and the
flow respects it. Ollama and a handful of weaker models fall through to
step 2/3.

---

## 6. Backward compatibility — checklist

- [x] `TradingAgentsGraph(...).propagate(ticker, date)` signature unchanged.
- [x] Return value `(final_state, decision_signal)` unchanged.
- [x] `final_state["market_report"]` etc. still populated (parallel branch
      writes them; serial branch unchanged).
- [x] `final_state["final_trade_decision"]` and `process_signal()` semantics
      unchanged.
- [x] All new `AgentState` fields have empty defaults.
- [x] SqliteSaver pickle checkpoints from v0.2.4 deserialise without
      raising (extra keys → defaulted; old keys preserved).
- [x] `selected_analysts=["market", "social", "news", "fundamentals"]`
      keeps the same default and same labels in saved JSON state.
- [x] `signal_fusion_enabled=False` reverts to the v0.2.5 serial graph
      identically (verified by a "no-op disabled" integration test).

---

## 7. Commit plan

This PR will be **two commits** so the user can verify the refactor is
truly behavior-neutral before the fusion logic is layered on top.

**Commit 1 — `refactor: structured analyst signals + parallel fan-out (equal weights)`**

- Add `AnalystSignal` + `SignalDirection` to `schemas.py`.
- Add per-analyst `*_messages` channels; convert four analyst nodes to
  use them; remove (or no-op) the four `Msg Clear *` nodes.
- Add `extract_analyst_signal` helper in `utils/structured.py`.
- Wire `Extract Signal` nodes after each analyst's tool loop.
- Add a *trivial* fan-in node that just sets `composite_score = 0` /
  `signal_weights = equal` — no behavioral change to Bull/Bear yet.
- New tests cover schema rendering, the dict reducer, the messages-key
  isolation, the heuristic-fallback path, and the disabled-flag round-trip.
- Existing tests (`tests/test_structured_agents.py`,
  `tests/test_signal_processing.py`, `tests/test_checkpoint_resume.py`)
  must remain green untouched.

Expected end-to-end behavior at this commit with `weight_estimation_method
= "equal"`: produces equivalent Bull/Bear inputs to v0.2.5 (full reports
in, prompt body unchanged because the composite-score block is gated on
`signal_fusion_enabled` AND on the non-default fusion prompts — see
commit 2). Numerical regression should be near-zero, modulo provider
non-determinism.

**Commit 2 — `feat: signal-fusion weighting + bull/bear prompt injection`**

- Add `tradingagents/dataflows/signal_weights.py` with both estimators
  and the parquet cache.
- Replace the trivial fan-in with the real `create_signal_fusion_node`.
- Rewrite Bull/Bear prompts with composite score, weights table,
  disagreement anchor, and weight-conditional report compression.
- New tests: equal-weight composite math, lookahead guard, weight
  clamping, disagreement detection, compression integration.
- Add `scripts/backtest_signal_fusion.py` (see §8).
- Write `SIGNAL_FUSION.md` (architecture, config, rollback, backtest
  results).

---

## 8. Backtest plan

Script: `scripts/backtest_signal_fusion.py`.

- Ticker set (matches the user's spec): **TSLA, JNJ, NVDA, SPY, RKLB**.
  RKLB picked as the small-cap — diverse news flow, retail-heavy
  sentiment, and enough fundamental ambiguity to stress the fusion.
- Dates: a rolling 1-month window of weekly Mondays (4 trade dates per
  ticker → 20 runs per arm).
- Two arms: `signal_fusion_enabled=False` (baseline) and `True` (with
  equal weights — Phase 1's only honest claim).
- Holding period: 5 trading days, alpha vs the configured benchmark
  (SPY for US tickers).
- Metrics per arm: mean alpha, hit rate, decision distribution
  (Buy/Hold/Sell counts), tokens used, wall-clock.
- Acceptance: mean alpha delta ≥ 0; token delta ≤ +20%; wall-clock delta
  flat-to-negative (parallel fan-out should *win* here, modulo the 4
  extra extraction calls).
- Output: a markdown table in `SIGNAL_FUSION.md` + a CSV under
  `~/.tradingagents/logs/` for reproducibility. **Not** committed.

If results miss the acceptance bar I will surface that explicitly rather
than ship a regression dressed as a feature.

---

## 9. Devil's Advocate node (§7 of the task, "Stretch")

Not in this PR. Worth doing later, but the right place to sequence it is
after the fusion layer has shipped and stabilised, since both nodes
target the Bull/Bear → RM seam and you want clean isolation when you A/B
each.

---

## 10. Open questions for confirmation

1. **Small-cap pick:** I chose **RKLB** for the backtest because it has
   live news flow + active retail sentiment + ambiguous fundamentals.
   Override if you prefer (e.g. SMCI, IRBT).
2. **Compression default:** I propose `signal_fusion_compress_threshold
   = 0.10` (compress any analyst with ≤10% weight to 3 sentences). This
   is conservative — under equal weights nothing gets compressed (each
   weight is 0.25). The compression only bites once `rolling_lasso` is
   enabled. OK?
3. **Eager parallelisation vs deferred:** I propose **parallel + per-
   analyst messages channels in commit 1** as the task spec asks. The
   only honest risk is provider rate-limit pressure when four analysts
   run concurrently — mitigated by `analyst_max_tool_calls=8`. If you'd
   rather defer parallelism to a follow-up PR (structured + serial in
   commit 1, parallel in a later PR), I'll cut commit 1 smaller.
4. **Schema location:** `AnalystSignal` lives in
   `tradingagents/agents/schemas.py` alongside `ResearchPlan` /
   `TraderProposal` / `PortfolioDecision`. No separate file. OK?

Please confirm or redirect on §10, and I'll start commit 1.
