# F4/F5 Combined Exit-Gate Report - 2026-06-06

**Window:** `2026-06-06T04:48:37+00:00` to `2026-06-06T16:48:37+00:00`

**Overall:** FAIL

| Check | Result | Detail |
|---|---|---|
| light_alert_latency | FAIL | 1 light alerts, p95=349077.5s |
| light_delivery_audit | PASS | 1/1 light alerts have sent/skipped delivery rows |
| alert_quality_audit | PASS | 1/1 light-alert events passed strict evaluation; rejects=815 |
| approval_lineage | PASS | 1/1 accepted actions completed a done job and linked full brief |
| full_brief_delivery | FAIL | 0/1 full briefs have sent/skipped delivery rows |
| worker_errors | PASS | 0 queue job errors |

## Cost And Cache Summary

- runs: 12
- input/output tokens: 3734841 / 716263
- cache hit/miss tokens: 1868800 / 1866041
- cache hit ratio: 50.0%
- estimated cost: $1.4225

## Operator Sign-Off

- [ ] Review a false-positive/false-negative sample from alert evaluations.
- [ ] Confirm accepted approval lineage maps light alert -> job -> full brief.
- [ ] Confirm full briefs were delivered or explicitly skipped.

---

## Investigation — 2026-06-06 (post-run analysis)

Two checks failed. One is a real code defect (**fatal**); the other is a measurement
artifact of running the gate over a backlogged window.

### FAIL 1 — `full_brief_delivery` (FATAL: real bug)

**Symptom:** `0/1 full briefs have sent/skipped delivery rows`.

**Trace (QBTS approval):**
- Approved action `57` (`run_full_study`, accepted) → full brief `4bd51609`
  (`mode=event_alert`, parent `15852245`, generated `06:03:13`). Lineage is intact
  (`approval_lineage` PASS).
- `deliveries` table: the **light** brief `15852245` has 3 rows
  (telegram/cli `skipped:quiet_hours`, email `skipped:smtp_disabled`). The **full**
  brief `4bd51609` has **zero** rows — delivery was never *attempted* (not skipped,
  not failed — simply never invoked).

**Root cause — the full-study path has no delivery step.** Delivery fan-out exists
only for light alerts:
- Light: `orchestrator/promoter.py:92` composes with `deliver=True` →
  `secretary/service.py:_deliver_light_alert` (hardcoded `mode="event_alert_light"`)
  → writes `deliveries` rows.
- Full: worker `orchestrator/worker.py:46` `drain_one` →
  `orchestrator/dispatch.py:18` `dispatch_event_alert` →
  `secretary/service.py:249` `compose_event_alert` (writes `mode="event_alert"`)
  → returns a rollup dict; the worker then `mark_done`s the job **and never calls
  any delivery**. There is no `_deliver_full_brief` / `event_alert` delivery method
  anywhere in the codebase.

So an approved full study is generated and persisted but never handed to a channel.
This fails **every time** a full brief is produced — it is deterministic, not
environmental (quiet-hours/SMTP-disabled would still record `skipped` rows; here
there are none).

**Fix:** add a delivery fan-out for `mode="event_alert"` mirroring
`_deliver_light_alert` — either inside `compose_event_alert` (a `deliver=True` path)
or in the worker after `mark_done`. Reuse `_build_channel` / `render_for_channel` /
`store.insert_delivery` so skipped/failed channels still record rows (which is what
this gate audits).

### FAIL 2 — `light_alert_latency` (not fatal: stale-event artifact)

**Symptom:** `1 light alert, p95=349077.5s` (≈ 97 h ≈ 4.04 days) vs threshold 300 s.

**Cause:** latency = event `ingested_ts` → light-brief `generated_ts`. The QBTS
trigger event `730835c3` was ingested **2026-06-02 04:38:32** but only passed strict
evaluation and produced a light alert at **2026-06-06 05:36:29** — a 4-day-old event
surfaced inside the gate window. With a single sample, p95 = that one value.

This reflects the pipeline being idle/backlogged 06-02→06-06 (plus the known
single-threaded worker throughput problem, ~14 min/job), **not** a delivery or
correctness fault. A continuously-running pipeline composes a light alert from a
fresh event in seconds. Re-measure over an active window with the worker keeping up;
do not treat this number as representative.

### Passing checks (context)
- `approval_lineage` PASS — light → job → full-brief lineage is correct; only the
  final *delivery* of the full brief is missing.
- `worker_errors` PASS (0) — jobs complete cleanly; no loop (verified separately:
  job 64 finished in ~14 min, no retry/recursion runaway).
- Cache hit ratio 50% / $1.42 over 12 runs — in line with prior measurements.

### Priority
1. **Fix `full_brief_delivery`** (code gap) — blocks the gate and means approved
   studies never reach the user.
2. Re-run the gate over an active window to clear the latency artifact and confirm
   delivery once #1 lands.
3. (Tracked separately) worker throughput + ~322k input-tokens/run cost.