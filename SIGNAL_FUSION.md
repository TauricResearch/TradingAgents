# SignalFusion — Architecture, Config, Rollback, Backtest

The SignalFusion layer sits between the analyst team and the Researcher
debate. It turns the previous "four reports stitched into a prompt and
let the LLM weigh them" into:

1. A typed `AnalystSignal` per channel (direction, score, confidence,
   evidence count, key evidence) — produced by a structured-output
   pass after each analyst's free-text report is finalised.
2. A per-ticker `{channel: weight}` map produced by a `WeightEstimator`.
3. A `composite_score` ∈ [-1, 1] and explicit `disagreement_axes` that
   anchor the Bull/Bear debate on the actual channel pair in conflict
   rather than rehashing every report end-to-end.
4. Physical compression of low-weight reports in the Bull/Bear prompt,
   so weights are load-bearing in context — not just a number the LLM
   is free to ignore.

This document covers architecture, config keys, rollback, and the A/B
backtest harness. See [DESIGN_NOTES.md](DESIGN_NOTES.md) for the
Phase-0 research and the design decisions that led here.

---

## Architecture

Default graph (`signal_fusion_enabled=True`):

```
                    ┌──→ Market Analyst        ─→ Extract Market        ─┐
                    ├──→ Sentiment Analyst     ─→ Extract Sentiment     ─┤
START ──────────────┤                                                    ├─→ Signal Fusion ─→ Bull ⇄ Bear → RM → Trader → Risk → PM → END
                    ├──→ News Analyst          ─→ Extract News          ─┤
                    └──→ Fundamentals Analyst  ─→ Extract Fundamentals  ─┘
```

Key shape changes from v0.2.5:

- **Parallel fan-out from `START`.** Each analyst owns a dedicated
  `<channel>_messages` channel so concurrent tool loops don't pollute
  each other's transcripts. The four `Msg Clear *` nodes from the
  serial flow are removed — fan-out gives each analyst a clean slate
  by construction.
- **Extract Signal nodes.** Each analyst's markdown report is converted
  to a typed `AnalystSignal` by a quick LLM call right after the tool
  loop ends. The extraction always succeeds: structured output → JSON-
  mode self-repair → heuristic synthesis from the markdown's `FINAL
  TRANSACTION PROPOSAL: **X**` line. SignalFusion is guaranteed a
  typed signal for every channel that produced a markdown report.
- **Signal Fusion node.** Pure-Python aggregation: a `WeightEstimator`
  produces `{channel: weight}` from the ticker + date + available
  channels; `composite_score = Σ wᵢ · scoreᵢ · confidenceᵢ` is written
  to state; `disagreement_axes` names the channel pair with the widest
  signed-score gap.
- **Bull/Bear prompts** open with a fusion preamble (composite score +
  weights table + disagreement anchor) and physically swap in
  compressed digests for any analyst with weight below the
  configured threshold.

Kill-switch graph (`signal_fusion_enabled=False`): the v0.2.5 serial
topology is reproduced verbatim. No extraction, no fusion, shared
`messages` channel, same `Msg Clear *` nodes — see
[setup.py](tradingagents/graph/setup.py) `_build_legacy_serial_graph`.

### Weight estimators

Two estimators ship in Phase 1, in
[tradingagents/dataflows/signal_weights.py](tradingagents/dataflows/signal_weights.py):

- **`EqualWeightEstimator`** — uniform 1/N. Default. The composite
  score and the disagreement anchor still flow through to the prompt,
  but no compression happens because 0.25 > 0.10 (the default
  threshold). The behaviour upstream of Bull/Bear matches v0.2.5
  exactly when every analyst produces a signal.
- **`RollingCorrelationEstimator`** — opt-in. Builds 90-day proxy
  series for each channel from yfinance OHLCV alone (RSI z-score,
  volume ratio, jump count, trend strength), computes |Pearson
  correlation| between each proxy and the forward 5-day alpha vs the
  configured benchmark, softmaxes the magnitudes (temperature 5),
  enforces the per-channel floor via water-filling, and caches to
  `<data_cache_dir>/signal_weights/<TICKER>_weights.csv` with a
  TTL refresh.

The full Lasso variant promised by the original task spec is reserved
for Phase 2 — the config key `weight_estimation_method="rolling_lasso"`
is accepted today as an alias for `"rolling_correlation"` so user
configs are forward-compatible with the Phase-2 rename.

### Strict no-lookahead

`RollingCorrelationEstimator.get_weights(ticker, as_of_date, ...)` only
reads OHLCV rows strictly dated *before* `as_of_date`. The forward-
alpha target uses prices within the window and is dropped wherever it
would need post-`as_of_date` data. A unit test enforces this with a
synthetic dataset that injects a row on the trade date and asserts the
estimator falls back to equal weights rather than fitting on
contaminated data — see
[`tests/test_signal_fusion.py::TestRollingCorrelationEstimator::test_lookahead_guard_rejects_history_containing_trade_date`](tests/test_signal_fusion.py).

---

## Config keys

All keys live in
[`tradingagents/default_config.py`](tradingagents/default_config.py) and
can be overridden by the matching `TRADINGAGENTS_*` env var where one
exists.

| Key | Default | What it does |
|---|---|---|
| `signal_fusion_enabled` | `True` | Master switch. `False` reverts to the v0.2.5 serial graph (no extraction, no fusion). |
| `weight_estimation_method` | `"equal"` | `"equal"` or `"rolling_correlation"` (`"rolling_lasso"` is an alias for the latter). |
| `weight_cache_ttl_days` | `7` | How long a cached weights row stays fresh. |
| `signal_fusion_min_weight` | `0.05` | Per-channel floor enforced after softmax (water-filled, exact). |
| `signal_fusion_compress_threshold` | `0.10` | Reports for channels below this weight are swapped for `AnalystSignal.key_evidence` digests in the Bull/Bear prompt. |
| `signal_fusion_compress_to_sentences` | `3` | Sentence cap used when an analyst has no `key_evidence` to render (heuristic-fallback path). |
| `analyst_max_tool_calls` | `8` | Cap on tool calls per analyst — extra insurance under parallel fan-out, where runaway analysts are a cost hit. `None` disables. |

Env-var overrides (existing pattern):

```bash
TRADINGAGENTS_SIGNAL_FUSION_ENABLED=false
TRADINGAGENTS_WEIGHT_ESTIMATION_METHOD=rolling_correlation
```

---

## Rollback

In order of granularity:

1. **`signal_fusion_enabled=False`** — graph reverts to the v0.2.5
   serial topology in place. No state-schema changes are visible
   downstream of Bull/Bear because the new state fields default empty,
   and the fusion prompt-renderer collapses to passing reports through
   verbatim when `signal_weights` is empty.

2. **`weight_estimation_method="equal"`** — keep the parallel topology
   and structured signals but disable the rolling estimator. This is
   the right A/B middle ground: you get parallel speedup + structured
   logging + composite-score telemetry, with no risk of poorly-fit
   weights skewing the debate.

3. **`signal_fusion_compress_threshold=0.0`** — keep the weights and
   the preamble but never compress reports. Useful when investigating
   whether prompt context length is dominating outcomes.

4. **Full revert** — `git revert` the two SignalFusion commits. All
   downstream consumers (memory log, reflection, checkpoint format)
   are unchanged, so a hard revert leaves user data intact.

Pre-fusion (`v0.2.4` / `v0.2.5`) SqliteSaver checkpoints **only resume**
under `signal_fusion_enabled=False` — the parallel graph's node IDs
don't match the serial graph's saved snapshots. Document this in the
ops runbook before flipping the flag on for users with in-flight
checkpoints.

---

## A/B backtest

Script: [`scripts/backtest_signal_fusion.py`](scripts/backtest_signal_fusion.py).

It runs `propagate(ticker, date)` twice per pair — once with
`signal_fusion_enabled=False`, once with the default fused pipeline —
fetches the forward 5-day alpha vs the configured benchmark, and writes
a CSV plus a markdown summary. Default ticker set:

| Ticker | Why |
|---|---|
| TSLA | Large-cap, retail-heavy sentiment, frequent news flow |
| JNJ  | Defensive large-cap, slow-moving fundamentals |
| NVDA | Large-cap, momentum-driven, dense earnings flow |
| SPY  | Index ETF — sanity check that we don't blow up the macro case |
| RKLB | Small-cap, ambiguous fundamentals, mixed retail sentiment |

Dry-run (default) prints the matrix without issuing any LLM calls:

```bash
uv run python scripts/backtest_signal_fusion.py --dry-run
```

Execute (costs real money; needs provider keys):

```bash
uv run python scripts/backtest_signal_fusion.py \
    --execute \
    --output ./fusion_backtest.csv
```

The summary table the script prints at the end is in the same format
the README's results section expects:

```text
| Arm | Runs | Mean α | Hit rate | Mean wall-clock | Decisions (B/H/S) |
|---|---|---|---|---|---|
| legacy | 20 | …  | …  | …s | …/…/… |
| fusion | 20 | …  | …  | …s | …/…/… |
```

### Backtest results

Not run in this PR (each (ticker, date) pair costs a deep-think + four
quick-think calls; the full 5×4×2 matrix is the user's call to spend).
Drop the markdown table the script emits into the slot above after
running, and link the CSV in the PR description for reproducibility.

Acceptance bar agreed in DESIGN_NOTES.md §8:

- Mean α delta (fusion − legacy) **≥ 0**.
- Token delta ≤ **+20 %**.
- Wall-clock delta flat-to-negative (parallel fan-out should win;
  the extraction passes cost ~4 quick-think calls in exchange).

If a run misses the bar, that is information — not failure. Surface
it in the PR, not the docs.

---

## Test coverage

`tests/test_signal_fusion.py` ships 53 unit tests covering:

- `AnalystSignal` schema bounds and `render_analyst_signal_summary`.
- `equal_weights` / `compute_composite_score` / `detect_disagreement`.
- `_merge_analyst_signals` reducer correctness.
- `extract_analyst_signal` happy path, JSON-mode self-repair retry,
  heuristic fallback, and sign-consistency clamping.
- Graph topology selection — parallel mode includes `Signal Fusion` +
  `Extract <Analyst>` nodes; legacy mode preserves `Msg Clear *`.
- `ConditionalLogic` routing — Extract vs Msg Clear, tool-call budget.
- `RollingCorrelationEstimator` — lookahead guard, floor enforcement,
  weight sum = 1, cache hit, channel-subset renormalisation.
- `build_weight_estimator` factory dispatch.
- `render_fusion_prompt_parts` — preamble presence/absence, compression
  trigger below threshold, sentence-clip fallback when no
  `key_evidence`.
- SignalFusion node with a captured estimator.

Run with:

```bash
uv run pytest tests/test_signal_fusion.py -v
```

The full repo test suite (253 tests + 1 deepseek skip) stays green; no
existing test was modified.
