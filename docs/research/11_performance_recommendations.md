# 11 — Performance Recommendations

Deliverable 11. How to make the engine fast enough for the new workloads (especially optimization sweeps) without rewriting it. **Recommendations only — no invented speedup numbers.** The one real datapoint we have is measured: **~11 decisions/s on a 1-vCPU Cloud Run instance** (the current prod configuration; ~100/s on a dev laptop). Any figure beyond that must come from future measurement and is stated as such.

## Where the time goes today (from the code, not benchmarks)

- The engine is a single-process `for i in range(min_history, len(bars)-1)` loop (engine.py:78), GIL-bound, sharing the process with the request event loop. The streaming engine injects `time.sleep(0.002)` per decision (backtest_job.py) specifically to keep the server responsive — i.e. throughput is *deliberately* capped, not maxed.
- Indicators are already precomputed once per run (`compute_indicator_series`, the numpy-vectorized path) — a prior optimization; this is not the bottleneck.
- For a *single* backtest, ~11 dec/s is adequate (a 7-day 5m run is ~2000 decisions ≈ 3 min, cancellable, checkpointed). The performance problem is **not** the single run — it is **T3 optimization**, where a grid of 100 parameter sets = 100 runs and naive serialization would be hours.

## Recommendations, in priority order

### R1 — Process-pool the optimizer (the one that matters)
Optimization trials are embarrassingly parallel and each is a pure deterministic function of its params. Run them with `concurrent.futures.ProcessPoolExecutor`, one trial per worker process. This is the **correct GIL relief for C4** — it sidesteps the GIL entirely (separate processes) without touching the engine loop, and it turns "100 trials × 3 min serial" into "100 trials / N cores." *This is a design recommendation; the actual multiple must be measured on the target instance (and depends on vCPU count — the current 1-vCPU prod box gets no parallelism, so optimization needs a larger instance or a separate worker pool, see R4).*

### R2 — Drop the per-decision sleep for headless/optimization runs
The 2ms/decision `sleep` exists only to protect the shared request event loop during a *streaming* run the operator is watching. Optimization child runs are headless — they don't stream progress per decision — so they should run without the sleep. Removing it on the headless path recovers the deliberately-forgone throughput. Keep it on the interactive single-run path (the responsiveness guarantee is still needed there).

### R3 — Reuse precomputed indicators across trials on the same window
Every trial in a sweep replays the *same bars*; only strategy params change. `compute_indicator_series` output is a pure function of (bars, indicator_names) — compute it once per window and share the immutable series across trials (pass it into each child `BarReplay` rather than recomputing). Indicator params that are themselves being optimized are the exception (recompute only those). Avoids N× redundant indicator computation in a sweep.

### R4 — Separate the optimization worker from the request-serving instance
Today the backtest job runs on a daemon thread inside the dashboard's Cloud Run instance (`--no-cpu-throttling`, 1 vCPU). Long optimization sweeps should not contend with request serving. Options, cheapest first: (a) a larger-vCPU instance for the existing single worker so R1's process pool has cores to use; (b) a separate Cloud Run job / worker service that pulls optimization jobs off a queue and writes results to the same Firestore/GCS store. (b) is the scalable answer but is infrastructure work beyond the engine; (a) is a config change that unblocks R1 immediately. *Choice deferred to the roadmap; both preserve the single-runner 409 invariant per job type.*

### R5 — Vectorize only if measurement demands it
VectorBT-style full vectorization ([04](04_framework_comparison.md)) is the theoretical speed ceiling, but it is a *rewrite* incompatible with our event-driven order lifecycle (T2), stop-before-TP pessimism, and per-decision evidence record. **Do not vectorize the core.** If, after R1–R4, sweep throughput is still the binding constraint (measured, not assumed), consider a *separate* vectorized pre-screen path that narrows the parameter space before the faithful event-driven engine confirms the survivors — a two-stage funnel, not a replacement. This is a last resort, explicitly gated on measurement.

## What NOT to do

- **Don't chase single-run microseconds.** The single-run path is fast enough and its cost (the 2ms sleep, the evidence record) buys responsiveness and auditability we want to keep.
- **Don't distribute prematurely.** A process pool on one adequately-sized instance covers the foreseeable optimization load; a multi-node queue (R4b) is worth it only when sweep sizes or concurrency actually exceed one box — decide on measured demand.
- **Don't trade away determinism or the evidence record for speed.** Every recommendation above preserves byte-identical results and full-fidelity artifacts; that is non-negotiable ([06](06_hld.md) principle 1/3).

## Measurement plan (so future numbers are real)

Before and after R1–R3, on the target instance, record: decisions/s for a fixed reference run (headless, sleep off), and wall-clock for a fixed 64-trial grid. Publish the deltas as *measured* figures in the roadmap's progress notes — never as pre-committed targets. The engine already emits the timing hooks needed (decision counts, checkpoints); a small harness around a fixed window is all that's required.
