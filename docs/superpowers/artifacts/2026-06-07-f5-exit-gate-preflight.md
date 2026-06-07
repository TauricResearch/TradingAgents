# F5 Exit-Gate — Pre-flight Check (2026-06-07)

> Evaluator: [scripts/f5_exit_gate.py](../../scripts/f5_exit_gate.py) — checks G1–G9,
> writes `data/exit_gates/f5-<date>.md`. Run with `--since <ISO-8601>`.
> Runbook: [ops/runbooks/f5-exit-gate.md](../../ops/runbooks/f5-exit-gate.md)
> Branch: `fix/full-brief-delivery-audit`

This is a **pre-flight** assessment against the current IIC DB
(`~/.tradingagents/iic.db`) — not a gate result. It establishes which checks
already pass, which still need an operator drive, and which are **blocked by a
code bug** that must be fixed before the gate can go green.

## Standings (9 checks)

| Check | Requirement | Current | Verdict |
|---|---|---|---|
| G1 morning_digest delivered | `mode=morning_digest` rows with `status=sent` ≥ 3 | 0 | ❌ drive |
| G2 event_alert delivered | `event_alert*` rows with `status=sent` ≥ 1 | 26 | ✅ pass |
| G3 deep_dive delivered | `mode=deep_dive` rows with `status=sent` ≥ 1 | 0 | ⛔ **BLOCKED (bug)** |
| G4 backtest accepted+done | `run_backtest` action `accepted` + `result_backtest_id` set ≥ 1 | 0 | ❌ drive |
| G5 expired-unactioned | `state=expired` & `result_backtest_id NULL` ≥ 1 | 56 | ✅ pass |
| G6 refinement | brief with `parent_brief_id` & `refine_overrides` ≥ 1 | 0 | ❌ drive |
| G7 no crashes | 0 systemd restarts of IIC units over the window | n/a | runtime |
| G8 ≥3 days cost data | distinct `runs.started_ts` days ≥ 3 | 4 | ✅ pass |
| G9 guards off | all cost/rate/budget guards `enabled=False` | all off | ✅ pass |

**Already passing from existing data: G2, G5, G8, G9.**

## Delivery reality (why the channel matters)

Current `deliveries` rows by channel/status:

| channel | status | reason | count |
|---|---|---|---|
| cli | sent | — | 26 |
| cli | skipped | quiet_hours | 1 |
| email | skipped | smtp_disabled | 27 |
| telegram | failed | — | 26 |
| telegram | skipped | quiet_hours | 1 |

- `delivery.enabled_channels = ['email', 'cli']`; `telegram_bot.enabled = True`
  (so telegram is appended at send time). `quiet_hours = None` currently.
- **`cli` is the only channel that actually produces `sent` rows.** Because G1/G2/G3
  accept *any* channel with `status='sent'`, **cli alone satisfies them** — telegram
  and SMTP do **not** need to work for the gate.
- **Telegram delivery is broken** (26 `failed`). The `iic-telegram-bot` service was
  observed `inactive`, and outbound sends error. Not a gate blocker (cli covers it),
  but the interactive bot path (approve buttons, refinement replies) is unvalidated.
- **Email is `smtp_disabled`** (no SMTP creds / flag). Expected; not a blocker.

## ⛔ BLOCKER — G3: deep-dive briefs are never delivered (code bug)

Same bug class as the `full_brief_delivery` gap fixed on this branch for
`event_alert`. `compose_deep_dive`
([service.py:94-147](../../tradingagents/secretary/service.py#L94)) inserts the
`deep_dive` brief and returns with **no delivery call**, and the `deepdive` CLI
([cli/deepdive.py:71-95](../../cli/deepdive.py#L71)) composes then runs post-delivery
prompts **without ever delivering** the brief. So a deep-dive never gets a `sent`
delivery row → **G3 = 0, fails deterministically.**

The delivery fix on this branch only covered `compose_event_alert` /
`_deliver_event_alert`. **`compose_deep_dive` was not fixed.**

### Suggested fix (belongs on this branch)
Mirror `_deliver_event_alert` for the deep-dive path:
1. Add `deliver: bool = False` to `compose_deep_dive`; after `insert_brief`, call a
   new `_deliver_deep_dive(brief_id, ticker, generated_ts, synthesis, ...)`.
2. `_deliver_deep_dive` fans out over `enabled_channels` (+ telegram if bot enabled)
   via `_build_channel` / `render_for_channel(mode="deep_dive")` / `ch.send`, and
   records `failed` rows on exception — identical structure to `_deliver_light_alert`
   / `_deliver_event_alert`.
3. Have the `deepdive` CLI call `run_deepdive(..., deliver=True)` (thread a `deliver`
   flag through `run_deepdive` → `compose_deep_dive`).
4. Add a unit test paralleling `test_compose_event_alert_delivers_full_brief_when_enabled`
   asserting a `deep_dive` `sent`/recorded row is produced.

Until this lands, **G3 cannot pass** and the F5 gate cannot go fully green.

## Secondary issue (not a gate blocker)
- **Telegram outbound failing (26×) + bot inactive.** The gate passes on `cli`, but
  if Telegram delivery and the interactive bot are in scope for "done", they need a
  separate fix (live bot token, active `iic-telegram-bot`, working send path) and the
  manual runbook drives (G4 button, G6 reply). Track separately.

## How to drive the remaining checks (after the G3 fix)

```bash
cd /home/ziwei-huang/TradingAgents/TradingAgents
PY=/home/ziwei-huang/miniconda3/bin/python
export SOAK_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # see --since note below

# G1 — three real morning-digest sends (cli -> 'sent' rows). Run three times.
$PY -m cli.main forge morning-digest now

# G3 (after fix) + G4 + G6 — interactive deep-dive.
#   At the prompts: accept backtest 'y' (G4), then enter a refinement
#   e.g. "drop value, more conservative" (G6). G3 satisfied once deep_dive delivers.
$PY -m cli.main deepdive NVDA

# Evaluate -> writes data/exit_gates/f5-<date>.md
$PY scripts/f5_exit_gate.py --since "$SOAK_START"
```

### Caveats
- **`--since` data window.** G2/G5/G8's passing data is from 06-02→06-06. If
  `SOAK_START` is *now*, those rows fall outside the window and G2/G5/G8 read 0.
  Backdate `--since` (e.g. `2026-05-31T00:00:00Z`) to count them. A *faithful* F5
  result, though, is a contiguous 72h soak with `--since` = soak start; backdating is
  a pragmatic "what passes" check, not a real soak pass.
- **G7** audits `journalctl` for IIC-unit restarts since `--since` — do **not**
  `systemctl restart` units during the window.
- **G9** is already satisfied (all guards `enabled=False`); keep them off.

## Bottom line
4 of 9 pass today (G2, G5, G8, G9). 3 are simple operator drives (G1, G4, G6) once
delivery works on `cli`. **1 is hard-blocked by the deep-dive delivery bug (G3)** —
fix that on this branch first, then the gate is drivable to green in a single session
(modulo the `--since` window choice and the contiguous-soak caveat).
