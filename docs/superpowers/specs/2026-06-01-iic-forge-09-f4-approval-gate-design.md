# IIC-FORGE-09 — F4 Event-Alert Approval Gate — Design

| | |
|---|---|
| **Phase** | F4 rework (event-alert trigger loop) |
| **Date** | 2026-06-01 |
| **Status** | Approved (brainstorm) — pending implementation plan |
| **Supersedes** | The auto-fire trigger behavior in [IIC-FORGE-07 — F4 Orchestrator Design](2026-05-27-iic-forge-07-f4-orchestrator-design.md) §D5 / §9 SLA |
| **Branch** | `feat/iic-forge-08-f5` (fork PR #2, `VegarGG/TradingAgents`) |

## 1 · Problem & intent

Today F4 **auto-runs the full study** on every qualifying event: the promoter
enqueues a `queue_jobs` row, the worker leases it and calls
`compose_event_alert`, which runs **three full TradingAgentsGraph teams**
(`macro`, `momentum`, `value`) in parallel (~8–9 min, the 85–90% of per-brief
time) and synthesizes a brief. Verified against `iic.db`: one worker drains
~6 briefs/hr while events arrive ~12/hr, so the queue stacks and the original
SLA (`p95 event→brief ≤ 15 min`) fails on throughput, not correctness.

The **intended** product behavior (confirmed with the operator) is different:
an event that passes triage should produce a **light alert** (cheap, fast)
that asks the user whether to commission a full study. The heavy 3-team study
runs **only after the user approves**, and only for the ticker(s) the user
picks. This both matches the design intent and structurally dissolves the
throughput problem — studies now fire at the user's approval rate, not the
event arrival rate.

This rework was **never built** and is **not** in the F4/F5 specs as written;
F5 instead built a *post-hoc* "ask for more" model (`brief_actions`:
`run_backtest`, `refine_brief`) that operates on an already-produced brief.
This design adds the *pre-study* approval gate and reuses that F5 machinery.

## 2 · Scope

**In scope:** F4 event-alerts only.

**Attached requirements:**
- Morning-digest **behavior unchanged**, but its timer moves **07:00 → 06:00**
  (`ops/systemd/iic-morning.timer`).
- F5 follow-up actions (`run_backtest`, `refine_brief`) must remain functional
  and must **not** conflict with the new `run_full_study` action — they
  continue to operate on the *full* brief produced after approval.

**Out of scope (tracked follow-ups):**
- Applying the light-then-approve model to the morning digest (the digest
  still auto-runs full studies across the watchlist). Revisit as its own task.
- **Combined F4+F5 exit gate.** Because approval fuses the F4 trigger loop and
  the F5 delivery/follow-up path into one end-to-end flow (event → light alert
  delivered via F5 → user approves via Telegram/CLI → worker studies → F5
  delivers the full brief), F4 can no longer be exit-gated in isolation. The
  separate `scripts/f4_exit_gate.py` and `scripts/f5_exit_gate.py` should be
  **rewritten as one combined F4+F5 gate** once F5 delivery is wired in. This
  design updates the F4 evaluator for the new model now and flags the merge.

## 3 · Architecture

The rework inserts a human-approval gate between *detecting* an event and
*studying* it. The expensive 3-team study path is **unchanged**; only what
*triggers* it changes — the enqueue of the `event_alert` `queue_jobs` row moves
from "automatic, in the promoter" to "after approval, in the action-handler."

```
EVENT (triaged, watchlist-bound, high-confidence)
      │
      ▼  promoter (CHANGED)
  1. one quick_think_llm call → short "why this might matter" summary of the EVENT
  2. write a LIGHT brief: mode='event_alert_light', scope=[affected tickers]
     (triage facts + summary; run_ids=[]; cost ≈ cents; ~seconds)
  3. create one pending brief_actions row PER affected ticker:
     action_type='run_full_study', action_params={"ticker": T}, expires_at=+1 day
  4. suppress each alerted ticker for the rest of the local day (per-ticker-per-day)
  5. deliver via F5 Telegram: one message, per-ticker [Study T] buttons
      │
      ▼  (waits — nothing heavy runs yet)
  USER taps [Study NVDA]   OR   `forge alert approve <light_brief_id> --ticker NVDA`
      │
      ▼  action-handler (ONE NEW BRANCH)
  accepted run_full_study(ticker=T) → enqueue queue_jobs(job_type='event_alert', ticker=T)
      │                                  ↑ the EXISTING heavy job, unchanged
      ▼  worker (UNCHANGED)
  compose_event_alert(event, T) → 3 persona teams → synthesis → FULL brief
      │   full brief linked to the light brief via parent_brief_id;
      │   action.result_brief_id set to the full brief id
      ▼  F5 delivery (unchanged) + F5 follow-up (run_backtest / refine_brief) apply to the FULL brief
```

### Change / reuse split

| Component | Change |
|---|---|
| `orchestrator/promoter.py` | Instead of enqueuing a study: quick summary → light brief → pending action(s) → deliver. |
| `briefs` table | New `mode='event_alert_light'` (event-scoped, `scope`=JSON ticker list). |
| `brief_actions` table | New `action_type='run_full_study'` (no schema change; reuses state machine + `expires_at` + sweep). |
| `delivery/telegram*.py` | Per-ticker buttons; callback protocol gains the ticker in field 4. |
| `orchestrator/action_handler.py` | One new branch: accepted `run_full_study` → enqueue existing `event_alert` job. |
| `cli/forge.py` | New `forge alert list / approve / dismiss` sub-app. |
| `worker.py`, `secretary.compose_event_alert`, `synthesis.py` | **Unchanged.** |
| F5 `run_backtest` / `refine_brief` | **Unchanged** — operate on the full brief as today. |
| `ops/systemd/iic-morning.timer` | 07:00 → 06:00. Digest behavior otherwise unchanged. |

## 4 · Data model & state

**No new tables.** Three touchpoints on existing schema:

1. **`briefs` — new lightweight mode.** Promoter writes one
   `mode='event_alert_light'` row per event: `scope` = JSON list of affected
   tickers (same convention as `morning_digest`), body = the one-call event
   summary + triage facts, `run_ids=[]`, `cost_usd` ≈ the single quick call,
   `trigger_event_id` = the event. The later **full** brief is written as today
   (`mode='event_alert'`, single ticker) and linked back via the existing
   `parent_brief_id` column → light brief.

2. **`brief_actions` — one new `action_type`, no schema change.** One row per
   affected ticker: `action_type='run_full_study'`, `brief_id`=light brief,
   `action_params={"ticker": T}`, lifecycle `pending → accepted | declined |
   expired`, `expires_at`=**+1 day**. The existing `expire_lapsed_actions`
   sweep handles expiry. On accept, the action-handler enqueues the study and
   sets `result_brief_id` to the full brief when done — full audit chain
   light → action → full brief.

3. **Same-day dedup — extends the existing `suppression` table.** The promoter
   already writes `suppression` key `event_alert:<ticker>`; change the window
   from 60 min to **end-of-local-day** so each ticker gets **one** light alert
   per day. The candidate query already `LEFT JOIN suppression`, so a
   suppressed ticker generates no new alert. In a multi-ticker event, a ticker
   already alerted earlier today is **omitted from this event's button list**;
   the other affected tickers still appear.

### Per-event state diagram

```
event → [promoter] → light brief + pending action per ticker + suppress each ticker (1 day)
                          │
       ┌──────────────────┼─────────────────────┐
   accepted(T)         declined(T)           (1 day passes)
       │                   │                      │
 enqueue study(T)      no study               expired (swept)
       │               (audit kept)           (audit kept)
 full brief written; result_brief_id set
```

### Edge cases

- **Multi-ticker event:** one event-scoped light brief, one pending action and
  one button per affected (non-suppressed) ticker. Approving a ticker enqueues
  only that ticker's study. "Study all" accepts all still-pending tickers;
  "Dismiss all" declines them.
- **Same ticker, second event same day:** suppressed — no new alert
  (per-ticker-per-day). (Per-event dedup was considered and rejected for V1.)
- **Decline vs ignore:** `[Dismiss]` → `declined` (explicit, logged); never
  answering → `expired` after 1 day. Both leave an audit record; neither runs
  a study.

## 5 · Telegram + CLI interface

**Telegram — one message per event:**

```
⚡ Event alert — <event headline / sector>
<2–3 sentence quick_think_llm summary of the event>
Affected watchlist tickers — tap to launch a full study:
[ Study NVDA ] [ Study PANW ] [ Study CRWD ] [ Study DELL ]
[ Study HPE ]  [ Study NTAP ] [ Study IBM ]
[ ✅ Study all ]                         [ ✖ Dismiss all ]
```

- Callback protocol extends the existing 4-field format
  `act:<brief_id>:<action_type>:<arg>` — the 4th field carries the ticker:
  `act:<light_brief_id>:run_full_study:NVDA`. `handle_callback` already splits
  on `:` into 4 parts, so this is a minimal change. "Study all" / "Dismiss all"
  use a sentinel arg (e.g. `__all__`).
- Tapping a ticker flips only that ticker's pending action to `accepted` and
  edits the message to mark it (`NVDA ✓ studying…`).

**CLI — `forge alert` sub-app (headless / exit-gate use):**

```
forge alert list                                   # pending light alerts: id, event, tickers, age, expires
forge alert approve <light_brief_id> [--ticker T]  # approve one; no --ticker = approve all pending tickers
forge alert dismiss <light_brief_id> [--ticker T]  # decline one or all
```

These write the same `brief_actions` state transitions as the buttons, so the
action-handler dispatches identically. The exit-gate smoke test uses
`forge alert approve` to drive the flow with no human in the loop.

**Telemetry:** declines/expiries are retained, enabling later analysis of
approval rate for threshold tuning.

## 6 · Redefined exit gate & SLA

The old F4 SLA (`p95 event→brief ≤ 15 min`) is **retired** — it assumed
automatic study and would now measure the user's think time. The new model
measures only what the system controls.

**New F4 SLA — alert latency only:**
`p95(event.ingested_ts → light_brief.generated_ts) ≤ 5 min`
(one quick LLM call + DB write + Telegram send; 5 min absorbs the promoter poll
interval and Telegram send jitter). The heavy study is an **on-demand
background job** (like `forge deepdive`) with **no throughput SLA**.

**Rewritten `scripts/f4_exit_gate.py` checks:**
1. **Alert latency:** p95 event→light-brief ≤ 5 min over the window.
2. **Restart audit:** `NRestarts == 0` for `iic-promoter` and `iic-worker`.
3. **Approval plumbing:** ≥ 1 light alert approved (via CLI in the test)
   produced a full `event_alert` brief linked by `parent_brief_id`.
4. **Study correctness (not speed):** approved studies complete and write a
   full brief; no duration SLA, but they must succeed (no `error` state).
5. **Cost split:** report light-alert cost (cents) vs. full-study cost
   separately.

The quick summary uses `quick_think_llm` (configured `deepseek-v4-flash`).

## 7 · Testing strategy

TDD across all changed components, matching existing conventions
(`tests/orchestrator/`, `tests/smoke/`).

**Unit tests:**
- **promoter:** qualifying multi-ticker event → exactly one
  `event_alert_light` brief (event-scoped), one quick-summary call, one pending
  `run_full_study` action per affected ticker, one per-ticker 1-day
  suppression; asserts **no** `queue_jobs` study row created at this stage.
- **dedup:** ticker already alerted today is omitted; a fresh ticker on the
  same event still gets a button.
- **action-handler:** accepted `run_full_study` enqueues exactly one
  `event_alert` job for the right ticker and sets `result_brief_id`;
  declined/expired enqueue nothing.
- **telegram callback:** `act:<brief>:run_full_study:NVDA` flips only NVDA;
  `__all__` transitions all pending; unknown ticker ignored.
- **CLI:** `forge alert list/approve/dismiss` produce the same transitions as
  buttons (with/without `--ticker`).
- **expiry:** pending action past +1 day → `expired` by the existing sweep; no
  study runs.

**Smoke (`tests/smoke/test_f4_exit_gate.py`, rewritten):** synthetic event →
light brief + pending actions within budget → `forge alert approve` → heavy
`event_alert` job enqueued, runs (personas mocked), writes full brief linked by
`parent_brief_id`. End-to-end with no human/real LLM.

**F5 coexistence regression:** explicit test that `run_backtest` and
`refine_brief` still attach to and operate on the resulting *full* brief,
proving `run_full_study` coexists rather than conflicts.

**Gate evaluator:** `scripts/f4_exit_gate.py` rewritten per §6.

## 8 · Open questions / future

- **Combined F4+F5 exit gate** (see §2) — rewrite both gates as one once F5
  delivery is wired into the approval flow.
- **Morning digest** light-then-approve conversion — deferred.
- **Per-event vs per-ticker dedup** — V1 is per-ticker-per-day; revisit if the
  operator wants distinct same-day events for a ticker to re-alert.
