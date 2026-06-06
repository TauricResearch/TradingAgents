# IIC-FORGE-08 — F5 Delivery + Operations Design

| Field | Value |
|---|---|
| **Track** | IIC-FORGE |
| **Document** | 08 |
| **Scope** | F5 implementation design — delivery channels, scheduler, post-delivery actions, refinement classifier, dashboard, 72h soak exit gate |
| **Base** | F0–F4 complete (latest: `b5e5494` test(smoke): F4 exit-gate synthetic-event end-to-end) |
| **Owner** | Ziwei |
| **Date** | 2026-05-27 |
| **Status** | Ready for review |
| **Implements** | IIC-FORGE-03 §7 (F5 deliverables + exit gate), ADR-NEW-3 (post-delivery actions and brief threading) |
| **Companion plan** | IIC-FORGE-08 implementation plan (next step, via writing-plans skill) |

## Quick links

- §1 Executive summary
- §2 Anchoring decisions
- §3 Overall architecture
- §4 Data model — schema delta from F4
- §5 Secretary additions
- §6 Delivery channels
- §7 Action handler
- §8 Refinement classifier
- §9 Streamlit dashboard
- §10 Morning scheduler
- §11 Configuration, files
- §12 Cost guards (still `enabled=False`)
- §13 Exit gate and evidence approach
- §14 Risks
- §15 Out of scope
- §16 Open questions deferred to implementation

---

## 1 · Executive summary

F5 is the largest single phase in the program: three delivery channels (Telegram, email, CLI), a morning scheduler, a Streamlit operations dashboard, a structured post-delivery backtest prompt, and a free-text refinement classifier that turns user replies into parameter overrides and launches refined persona runs. F4 just shipped the autonomous trigger loop (promoter + worker, `compose_event_alert`); F5 is what lets the operator (a) see what the system did and (b) ask for more.

The exit gate is a **single contiguous 72-hour unattended soak against live F3 OSINT**. During the soak the operator must, at least once, accept a backtest prompt, let a prompt expire, and submit a free-text refinement — these are the three exit-gate checks that exercise the new action-handler + classifier surface.

Seven anchoring decisions shape this design (§2). The two with the largest downstream consequences:

- **All channels write to `brief_actions`; only one consumer (`iic-action-handler`) dispatches accepted actions.** This is the integration seam between channels (which know nothing about F2, the classifier, or refinement) and follow-up work (which knows nothing about which channel the user replied on).
- **Free-text refinement is best-effort.** The classifier always extracts what it can — no "I don't understand" branch. This simplifies V1 dramatically; the cost is a small wasted-graph-run rate when the user asks for drill-down or what-if (deferred). Mitigated by a hard depth-3 cap on refinement chains and by echoing the classifier's interpretation back to the user.

F5 adds **four new systemd units** parallel to F4's two (`iic-promoter` + `iic-worker`): `iic-telegram-bot`, `iic-action-handler`, `iic-morning.timer` + `iic-morning.service`, `iic-dashboard`. Each unit is single-purpose with `Restart=on-failure` and resource caps, matching the F4 ops pattern.

The schema delta is small (§4): no new tables, three append-only columns on `briefs` + `deliveries`, two new indexes. All F1 tables defined for F5 (`brief_actions`, `deliveries`) are already in place — F5 only fills them.

Cost guards remain `enabled=False` per Appendix A of the program design. F5 adds two new guard surfaces (refinement-chain budget, morning-digest token ceiling) and ships them disabled. The 72h soak is meant to measure the natural cost profile that future thresholds will be calibrated against.

## 2 · Anchoring decisions

### D1 — Three delivery channels, per-channel default for terse/full

Telegram (terse), email (full), CLI (full). Six total Jinja templates (3 modes × 2 distinct presentations — terse and full). Per-channel defaults live in `default_config.py`; no per-run override flag in V1.

**Rationale:** Telegram's natural form is short — inline buttons + a few lines work; multi-section morning digests don't. Email's natural form is long — readers expect a scrollable HTML document. CLI inherits email's full template since terminal users tolerate length.

### D2 — Four new systemd units

`iic-telegram-bot.service` (long-poll for updates + button callbacks + replies), `iic-action-handler.service` (poll `brief_actions` for accepted/expired, dispatch), `iic-morning.timer` + `iic-morning.service` (cron-style 07:00 morning digest), `iic-dashboard.service` (Streamlit on 127.0.0.1:8501).

**Rationale:** Single-purpose units match F4's pattern. Operator can disable channels independently (no Telegram bot token? → leave `iic-telegram-bot` masked; soak still completes via email + CLI). Restart blast radius is one component.

### D3 — Refinement classifier returns a fixed 4-field JSON schema

`{personas, risk_tilt, horizon, analysts}`. Each field is optional (`null` = inherit from parent). The classifier is one `quick_think_llm` call. Best-effort: it always returns this schema; no "decline" branch.

**Rationale:** A fixed schema lets `compose_refinement` apply overrides mechanically without a per-reply conditional tree. Best-effort means the classifier prompt is simpler and the user gets *something* even on ambiguous input (mitigated by depth-3 cap + interpretation echo).

### D4 — Refinement chain depth hard-capped at 3

A computed column `briefs.refine_depth` (set on insert by walking `parent_brief_id`) gates new refinements. Beyond depth 3, the secretary raises `RefinementDepthExceeded`; the action-handler replies on the original channel: "This thread has reached the refinement depth limit. Start a fresh deep-dive."

**Rationale:** Bounds cost-runaway risk during the no-cost-guards window. Three levels covers the realistic "tweak → try again → finalize" pattern. Depth-1 cap was considered and rejected as too restrictive; no cap was considered and rejected as cost-unsafe given Appendix A.

### D5 — Quiet hours suppress notifications only

Brief is still composed and persisted to `briefs` + `data/briefs/<id>.md` during quiet hours (default 22:00–07:00 local). The channel `send()` is skipped — `deliveries.status='skipped'`, `skip_reason='quiet_hours'`. Operator catches up via morning digest or dashboard. Quiet hours apply to **event alerts only**; morning digest and deep-dive bypass.

**Rationale:** Cleanest delivery semantics. No buffering complexity, no "bundle on wake" logic. Costs nothing — all the work already happened; only the ping is dropped.

### D6 — `brief_actions` is the single integration seam between channels and follow-up work

Telegram bot, dashboard `action_form`, and CLI deep-dive all write `brief_actions` rows. `iic-action-handler` is the only consumer that dispatches them. Channels never call F2, the classifier, or the secretary directly.

**Rationale:** Channels are dumb persisters of intent. Action-handler is the smart dispatcher. The bot can crash-restart without losing accepted actions; the dashboard can be disabled without breaking refinement; F2 can change its API and only the action-handler needs to know.

### D7 — 72-hour soak runs against live F3 OSINT

No synthetic injection. Operator interacts during the window to satisfy exit-gate checks G4 (accept one backtest prompt), G5 (let one expire), G6 (submit one free-text refinement).

**Rationale:** The soak is meant to produce a real natural-cost-profile signal that future cost-guard thresholds will be calibrated against. Synthetic injection would muddy that. Cost outlook (~$10.55 total — §13) is inside the cost-guards-off envelope.

## 3 · Overall architecture

```
   F3 OSINT ────► events ────► (F4) promoter ──► queue_jobs ──► (F4) worker ──► briefs (event_alert)
                                                                                      │
   forge deepdive ─────────────────────► Secretary.compose_deep_dive ──► briefs ──────┤
                                                                                      │
   iic-morning.timer ──► iic-morning.service ──► Secretary.compose_morning_digest ────┤
                                                                                      ▼
                                                                            ┌───────────────────┐
                                                                            │ DELIVERY (F5)     │
                                                                            │ - render template │
                                                                            │ - send + write    │
                                                                            │   deliveries row  │
                                                                            │ - quiet-hours skip│
                                                                            └────────┬──────────┘
                                                                                     │ (per channel)
                            ┌─────────────────┐  ┌───────────────┐  ┌───────────────┐
                            │ Telegram bot    │  │ SMTP email    │  │ CLI stdout    │
                            │ (long-poll      │  │ (one-shot     │  │ (interactive  │
                            │  + inline btns  │  │  smtplib send)│  │  prompts)     │
                            │  + reply read)  │  │ link → dash   │  │               │
                            └────────┬────────┘  └───────────────┘  └────────┬──────┘
                                     │                                       │
                                     │  user click / reply / typed reply     │
                                     ▼                                       ▼
                            ┌────────────────────────────────────────────────────┐
                            │ brief_actions  (state=pending, expires_at=+24h)    │
                            │   action_type: "run_backtest" | "refine_brief"     │
                            └────────────────────┬───────────────────────────────┘
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │ iic-action-handler service   │
                                  │ - poll state='accepted'      │
                                  │ - dispatch by action_type:   │
                                  │   • run_backtest → F2        │
                                  │   • refine_brief → classifier│
                                  │     + Secretary.compose_     │
                                  │     refinement(overrides=…)  │
                                  │ - sweep state='pending'      │
                                  │   past expires_at → expired  │
                                  └──────────────────────────────┘

                                  iic-dashboard.service (Streamlit, read-only over SQLite
                                                          + one POST: refinement form)
```

### Three load-bearing properties

1. **F5 adds no new event paths into brief composition.** All three modes already exist in the Secretary (`compose_deep_dive` ✅, `compose_event_alert` ✅, `compose_morning_digest` stub → implement). F5 only adds *delivery* and *follow-up handling*.
2. **`brief_actions` is the single inbox.** Every channel writes rows there; only `iic-action-handler` consumes them. Channels persist intent; the handler dispatches it.
3. **The action-handler uses `brief_actions`, not `queue_jobs`.** `brief_actions` has a user-facing state lifecycle (`pending → accepted | declined | expired`) that doesn't fit `queue_jobs`'s worker-leasing model. Polling sweep is simpler and matches the program-design wording.

## 4 · Data model — schema delta from F4

F1 already defines `briefs`, `brief_actions`, `deliveries`, `costs`, `runs`. F5 adds:

### Append-only columns

```sql
-- Quiet-hours buffering signal + channel back-reference
ALTER TABLE deliveries ADD COLUMN skip_reason TEXT;          -- "quiet_hours" | NULL
ALTER TABLE deliveries ADD COLUMN channel_ref TEXT;          -- "<chat_id>:<message_id>" | "<Message-ID>" | "cli"

-- Refinement depth (denormalized for fast gate-check)
ALTER TABLE briefs     ADD COLUMN refine_depth INTEGER NOT NULL DEFAULT 0;

-- Refinement override audit (replay what the classifier extracted)
ALTER TABLE briefs     ADD COLUMN refine_overrides TEXT;     -- JSON of {personas, risk_tilt, horizon, analysts}
```

All via the per-statement-idempotent migration applier introduced in F4's `db.py`.

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_deliveries_brief ON deliveries(brief_id);
CREATE INDEX IF NOT EXISTS idx_brief_actions_pending_expires
    ON brief_actions(state, expires_at) WHERE state = 'pending';
```

### Action lifecycle

```
   pending ──(user clicks/replies)──► accepted ──(dispatch ok)──► result_*_id set (terminal)
       │
       ├──(sweep finds expires_at < now)──► expired (terminal)
       │
       └──(user clicks Dismiss)─────────► declined (terminal)
```

The action handler holds **no in-memory state** — every iteration re-queries `state='accepted' AND result_backtest_id IS NULL AND result_brief_id IS NULL`. Crash-safe by construction.

### Telegram ↔ brief mapping

- **Outbound:** `TelegramOutbound.send()` records `deliveries.channel_ref = "<chat_id>:<message_id>"`.
- **Reply:** Telegram update carries `message.reply_to_message.message_id`; bot resolves `(chat_id, message_id) → brief_id` via `deliveries`, then writes a `brief_actions` row.
- **Inline button click:** `callback_data = "act:<brief_id>:<action_type>:<answer>"` — direct mapping, no lookup.

## 5 · Secretary additions

### `Secretary.compose_morning_digest(watchlist, ts)` — implement the F1 stub

```python
def compose_morning_digest(self, *, watchlist: list[str] | None, ts: str) -> str:
    """
    If watchlist is None, fetch rows from `watchlist` table where
    `ttl_until IS NULL OR ttl_until > datetime('now')`.
    For each ticker:
      1. Run the default balanced TradingAgents graph
      2. Synthesize per-ticker consensus/divergence/recommendation
    Then synthesize an across-ticker top-of-digest summary.
    Write one briefs row: mode='morning_digest', scope=<json list>, run_ids=<all runs>.
    Return brief_id.
    """
```

**Three load-bearing details:**

- Per-ticker default studies use one balanced graph; across-ticker is serial.
  Committee mode is explicit and should be reserved for comparison or
  disagreement analysis.
- Token cost dominates: ~$0.50–$2.00 per morning (deep_think_llm tier, 20 tickers). 3 mornings in the soak = real data for cost-guard calibration.
- Per-ticker failures (graph crash, persona error) are caught and written as a "data error" line in that ticker's section. **The digest always completes** — failure threshold of 50%+ tickers is still left as an Open Question (§16) for post-soak tuning.

### `Secretary.compose_refinement(parent_brief_id, overrides, reply_text)` — new method

```python
def compose_refinement(self, *, parent_brief_id: str, overrides: dict, reply_text: str) -> str:
    """
    1. Load parent brief; raise RefinementDepthExceeded if parent.refine_depth >= 3.
    2. Load the parent's Analysis Pack when present.
    3. Launch a focused default run, or explicit committee mode if requested.
    4. Synthesize a refined brief: mode='deep_dive' (regardless of parent mode),
       parent_brief_id=<parent>, refine_depth=<parent.depth + 1>,
       refine_overrides=<json>.
    5. Return new brief_id. Delivery is enqueued by the action-handler, not by this
       method.
    """
```

Override application is **in-memory only** — never written back to YAML files. Persona YAMLs are immutable at runtime. Audit trail lives in `briefs.refine_overrides`.

## 6 · Delivery channels

### `tradingagents/delivery/` — new package

```
tradingagents/delivery/
├── __init__.py
├── base.py              # DeliveryChannel ABC: send(brief, mode) -> delivery_id
├── telegram.py          # TelegramOutbound (python-telegram-bot Bot API)
├── email.py             # SMTP via smtplib (Gmail config)
├── cli.py               # stdout renderer + interactive prompt helpers
├── quiet_hours.py       # is_quiet_hours(now, config) -> bool
└── templates/           # Jinja templates (existing dir secretary/templates moves here)
    ├── telegram/
    │   ├── morning_digest.j2     (terse)
    │   ├── event_alert.j2        (terse — already exists, move)
    │   └── deep_dive.j2          (terse)
    ├── email/
    │   ├── morning_digest.j2     (full HTML + plaintext alt)
    │   └── deep_dive.j2          (full HTML)
    └── cli/
        ├── morning_digest.j2
        ├── event_alert.j2
        └── deep_dive.j2
```

### Three load-bearing properties

- **`DeliveryChannel.send(brief, mode)` always writes a `deliveries` row.** Success → `status='sent'`, `channel_ref` set. Failure → `status='failed'` with reason. Quiet-hours skip → `status='skipped'`, `skip_reason='quiet_hours'`. The row is the truth; no exceptions leak to callers.
- **Quiet-hours check happens in `base.send()`, not per channel.** One `is_quiet_hours` helper, gated to `mode='event_alert'` only — unit test asserts morning + deep-dive bypass.
- **Email body composed once, sent multipart (plain + html).** Plain alt is the rendered Jinja with stripped formatting; HTML is the styled version with the action-prompt link to Streamlit. Avoids spam-filter penalties on HTML-only emails.

### Telegram bot — `iic-telegram-bot.service`

Long-polling process using `python-telegram-bot` (new dependency, v20+ async API). Three responsibilities:

1. **Send outbound briefs.** Called by `TelegramOutbound.send()` over a shared connection. Inline keyboard for event alerts: `[Run Backtest] [Dismiss]`. Each message records `(chat_id, message_id) → brief_id` in `deliveries.channel_ref`.
2. **Receive callback queries (button clicks).** Parse `callback_data = "act:<brief_id>:<action_type>:<answer>"`. Write `brief_actions` row with appropriate state (`accepted` for yes-clicks, `declined` for dismiss-clicks). Edit the original message inline to show "✓ accepted" / "✗ dismissed".
3. **Receive text replies.** If `message.reply_to_message` exists, resolve to `brief_id`, write `brief_actions(action_type='refine_brief', state='accepted', action_params={'reply_text': …})`. If no reply context, ignore (V1: no top-level chat support).

The bot **never** calls the secretary, F2, or the classifier directly. It only writes `brief_actions` rows. Decoupling = the bot can crash-restart without losing accepted actions; the action-handler picks them up on its next tick.

### Email — one-shot smtplib send

No service of its own. `EmailOutbound.send()` is called synchronously from inside `iic-morning.service` (and from `iic-telegram-bot`-side outbound flows if email is also enabled for event alerts). Failure modes (Gmail SMTP rejects, network blip) are caught and recorded as `deliveries.status='failed'`. No retry in V1 — failure is visible in the dashboard.

Refinement input on email = the user clicks the per-ticker link → Streamlit page → form → POST writes a `brief_actions` row. Dashboard service owns this endpoint (§9).

### CLI — interactive prompts on `forge deepdive`

After the deep-dive brief is written:

```
==================================================================
Deep-dive complete: AAPL (brief abc123)
==================================================================
[rendered brief]
==================================================================

Run a backtest on these strategies? [y/N]:
Anything to refine? (free text, or Enter to finish): more aggressive, drop value
  → Got it — re-running with value persona dropped and risk tilt to aggressive.
Anything to refine? (free text, or Enter to finish): _
```

Each non-empty reply creates a `refine_brief` row. The CLI loops on the prompt until the user hits Enter on an empty line.

**CLI is synchronous with action dispatch in V1.** The CLI process waits for the action-handler to finish the refinement and prints the refined brief inline before re-prompting. This matters for ergonomics; backtest acceptance does the same (CLI waits for F2's brief-scoped backtest report path, prints the report path, continues). Telegram and email refinements are async — the user gets a new message minutes later.

## 7 · Action handler

### `iic-action-handler.service` — the `brief_actions` consumer

`tradingagents/orchestrator/action_handler.py`. Polling loop, default 5-second interval:

```python
def tick(conn) -> None:
    # 1. Sweep: pending rows past expires_at → expired
    expire_lapsed(conn, now=utcnow())

    # 2. Dispatch: accepted rows without a result yet
    for row in fetch_accepted_undispatched(conn):
        try:
            if row.action_type == "run_backtest":
                backtest_id = dispatch_backtest(row.brief_id, row.action_params)
                mark_done(conn, row.action_id, result_backtest_id=backtest_id)
            elif row.action_type == "refine_brief":
                overrides = classify_and_extract(
                    reply_text=row.action_params["reply_text"],
                    parent_brief=load_brief(row.brief_id),
                )
                new_brief_id = secretary.compose_refinement(
                    parent_brief_id=row.brief_id,
                    overrides=overrides,
                    reply_text=row.action_params["reply_text"],
                )
                mark_done(conn, row.action_id, result_brief_id=new_brief_id)
                enqueue_delivery(new_brief_id, channel=parent_delivery_channel(row.brief_id))
        except RefinementDepthExceeded:
            mark_done(conn, row.action_id, error="refinement_depth_exceeded")
            send_thread_limit_notice(row.brief_id)
```

### Three load-bearing properties

- **No leasing.** `brief_actions` doesn't need leasing because acceptance is user-initiated and serialized by the channel (a user can't double-click an inline button race-faster than `editMessageReplyMarkup` returns). Sweep + retry is enough.
- **Single-process consumer.** Only one `iic-action-handler` runs at a time (systemd unit, `Restart=on-failure` with default `RestartSec`). Concurrency = 1 keeps the SQLite write pattern simple and matches expected volume (handful of actions per day).
- **Refinement = synchronous from CLI's perspective, async on Telegram/email.** CLI's `forge deepdive` blocks until the action-handler produces the refined brief. Telegram replies get a refined brief as a new message minutes later. Email refinements (via Streamlit) get the refined brief delivered through the parent's original channel on next handler tick after composition.

## 8 · Refinement classifier

### New module `tradingagents/secretary/refinement.py`

```python
def classify_and_extract(reply_text: str, parent_brief: dict) -> dict:
    """
    One quick_think_llm call. Returns:
      {
        "personas": ["macro", "value"] | None,
        "risk_tilt": "more_aggressive" | "more_conservative" | None,
        "horizon": "days" | "weeks" | "months" | "quarters" | None,
        "analysts": {"include": [...], "exclude": [...]} | None,
        "interpretation": "<one-sentence echo back to user>",
      }
    Best-effort: classifier always returns a structured object, even if all override
    fields are None. No 'unclear' branch.
    """
```

### Prompt (concrete)

```
You are extracting refinement parameters from a user reply to an investment brief.
The original brief was about ticker(s): {scope}, personas: {personas}, horizon: {horizon}.

User reply: "{reply_text}"

Available overrides (set null if user didn't address them):
  - personas: subset of [macro, value, momentum] to keep for the refined run
  - risk_tilt: "more_aggressive" | "more_conservative"
  - horizon: "days" | "weeks" | "months" | "quarters"
  - analysts.include / analysts.exclude: subset of [market, news, social, fundamentals, derivatives]

Return JSON. If the reply asks for new information rather than refinement (e.g. "what
about earnings?"), still extract what you can — V1 treats all replies as refinements.

Also write a one-sentence interpretation in the user's voice that will be echoed back
("Got it — re-running with momentum dropped and a shorter horizon.").
```

### Interpretation echo

The `interpretation` string is echoed back to the user on the original channel **before** the refined brief lands:

- **Telegram:** a follow-up message in the same reply thread.
- **CLI:** printed in the interactive prompt loop (see §6 CLI example).
- **Email:** included as a confirmation line on the Streamlit page after form submit.

If the echo is wrong, the user can re-reply with a correction within the depth-3 budget.

## 9 · Streamlit dashboard

### `tradingagents/dashboard/` — new package

```
tradingagents/dashboard/
├── app.py                   # streamlit entrypoint
├── panels/
│   ├── briefs.py            # recent briefs table + brief detail view + parent_brief chain
│   ├── costs.py             # cost/token trend chart (Altair)
│   ├── queue.py             # queue_jobs depth + last 10 + worker heartbeat (max ended_ts)
│   └── actions.py           # pending brief_actions + recent 20 actioned
└── action_form.py           # ?brief_id=… → refinement form (POST writes brief_actions row)
```

### systemd unit

```ini
ExecStart=/path/to/venv/bin/streamlit run tradingagents/dashboard/app.py \
          --server.port=8501 --server.address=127.0.0.1
```

### Panels (all MVP per the brainstorming)

1. **Recent briefs table** — last 50 briefs: timestamp, mode, scope (ticker), `parent_brief_id` (so refinement threads are visible), delivery status. Clickable to view content from `data/briefs/<id>.md`.
2. **Cost / token trend chart** — line chart of `costs.usd_estimate` per day, last 30d, grouped by model. The primary signal for calibrating future cost-guard thresholds.
3. **Queue depth + worker status** — current `queue_jobs` depth by state (waiting / leased / done / failed), oldest waiting job age, last 10 jobs. Spot a stuck worker before it cascades.
4. **Brief actions queue** — pending `brief_actions` (state=`pending`, `expires_at` upcoming) + last 20 actioned. Critical because action acceptance is part of the exit gate.

### Bound to localhost; one mutation surface

The dashboard binds to `127.0.0.1:8501`. No auth, no remote access in V1. The email morning-digest link is `http://127.0.0.1:8501/action_form?brief_id=<id>` — works only when the user is on the same machine, which matches the local-first principle (P5).

Dashboard accepts **one mutation**: the refinement form POST on `action_form` writes a single `brief_actions` row with explicit `state='accepted'`. Every other panel is read-only. CSRF is not a concern at 127.0.0.1.

## 10 · Morning scheduler

### `iic-morning.timer` + `iic-morning.service`

systemd timer pattern, parallel to F4's promoter/worker:

```ini
# /etc/systemd/system/iic-morning.timer
[Timer]
OnCalendar=*-*-* 07:00:00     # configurable per default_config; documented in runbook
Persistent=true               # catches up if machine was off
Unit=iic-morning.service

# /etc/systemd/system/iic-morning.service
[Service]
Type=oneshot
ExecStart=/path/to/venv/bin/forge morning-digest --now
```

### `forge morning-digest --now` — new CLI command

1. Reads current watchlist from SQLite — rows where `ttl_until IS NULL OR ttl_until > datetime('now')` (matches F3's auto-promote-with-TTL convention).
2. Calls `Secretary.compose_morning_digest(watchlist=…, ts=now)`.
3. For each enabled channel in `delivery.enabled_channels` config (default: `["email", "cli"]`):
   - Renders the channel/mode template (`email/morning_digest.j2` or `cli/morning_digest.j2`).
   - Calls `channel.send(brief, mode='morning_digest')`.
4. Exits 0 unconditionally — failures are recorded in `deliveries`, not via exit code (the timer should not retry).

A `--dry-run` flag composes the brief and renders templates but skips `channel.send()` calls — used by the pre-flight checklist (§13) to verify end-to-end without sending real email.

### `forge digest tail` — operator convenience

Prints the most recent `mode='morning_digest'` brief from `data/briefs/<id>.md` to stdout. No interactive prompt — read-only.

## 11 · Configuration, files

### New configuration keys (`tradingagents/default_config.py`)

```python
"delivery": {
    "enabled_channels": ["email", "cli"],         # subset of ["telegram", "email", "cli"]
    "quiet_hours": {
        "enabled": True,
        "start": "22:00",                          # local time, 24h
        "end": "07:00",
    },
    "digest_modes": {                              # per-channel default
        "telegram": "terse",
        "email": "full",
        "cli": "full",
    },
},
"telegram_bot": {
    "enabled": False,                              # opt-in; needs IIC_TELEGRAM_BOT_TOKEN
    "allowed_chat_ids": [],                        # whitelist; empty = none
    "poll_interval_seconds": 1,
},
"smtp": {
    "enabled": False,                              # opt-in; needs IIC_SMTP_*
    "host": "smtp.gmail.com",
    "port": 587,
    "from_addr": "watter008@gmail.com",
    "to_addrs": ["watter008@gmail.com"],
},
"morning_digest": {
    "schedule_local_time": "07:00",
    "watchlist_source": "db",                      # always read from SQLite watchlist table
},
"refinement": {
    "max_depth": 3,
    "classifier_llm": "quick_think_llm",
    "action_expires_hours": 24,
},
"action_handler": {
    "tick_interval_seconds": 5,
},
"dashboard": {
    "enabled": False,                              # opt-in
    "port": 8501,
    "bind_address": "127.0.0.1",
},
```

Secrets via `.env`: `IIC_TELEGRAM_BOT_TOKEN`, `IIC_SMTP_USER`, `IIC_SMTP_APP_PASSWORD`.

### File layout

```
tradingagents/delivery/                          # new package (§6)
tradingagents/dashboard/                         # new package (§9)
tradingagents/orchestrator/action_handler.py     # new module (§7)
tradingagents/secretary/refinement.py            # new module (§8)
tradingagents/secretary/morning.py               # compose_morning_digest implementation (§5)
cli/morning.py                                   # forge morning-digest sub-app (§10)
ops/systemd/iic-telegram-bot.service             # new unit
ops/systemd/iic-action-handler.service           # new unit
ops/systemd/iic-morning.service                  # new unit
ops/systemd/iic-morning.timer                    # new timer
ops/systemd/iic-dashboard.service                # new unit
ops/runbooks/f5-exit-gate.md                     # 72h soak runbook
scripts/f5_exit_gate.py                          # evaluator (§13)
```

### Boundary tests (P7 discipline)

- `tests/delivery/test_quiet_hours_boundary.py` — asserts quiet-hours skip applies to `event_alert` only; `morning_digest` and `deep_dive` bypass.
- `tests/delivery/test_brief_actions_seam.py` — asserts no channel module calls F2, classifier, or secretary directly; only `brief_actions` writes.
- `tests/secretary/test_refinement_depth_cap.py` — asserts `RefinementDepthExceeded` raises at `parent.refine_depth >= 3`.
- `tests/secretary/test_refinement_overrides_in_memory.py` — asserts persona YAML files on disk are unchanged after a refinement run.
- `tests/orchestrator/test_action_handler_idempotent.py` — asserts repeated `tick()` calls do not double-dispatch an already-completed action.
- `tests/dashboard/test_action_form_single_mutation.py` — asserts only `action_form.py` performs SQLite writes; other panels are read-only.

### Smoke test

`tests/smoke/test_f5_exit_gate.py` — synthetic-event end-to-end equivalent to F4's smoke, exercising:
1. Synthetic high-salience event → F4 worker → event_alert brief.
2. Simulated inline-button accept → `brief_actions` accepted → backtest dispatch.
3. Simulated free-text reply → classifier → refined brief.
4. Lapsed action → sweep → expired.

Designed to run in < 90s in CI (no real SMTP, no real Telegram — channel `send()` is mocked at boundary).

## 12 · Cost guards (still `enabled=False`)

F5 adds two new guard surfaces per Appendix A of the program design, both shipping disabled:

```python
"refinement_chain_budget": {
    "enabled": False,
    "max_usd_per_chain": 10.0,                   # cap on cumulative cost across a refinement thread
},
"morning_digest_token_ceiling": {
    "enabled": False,
    "max_in_tokens": 500_000,                    # per-digest ceiling across all tickers/personas
},
```

Plus the four F4 guards remain unchanged (`QueueBackpressure`, `QueueRateGuard`, `DailyBudgetGuard`, per-run token budget — all `enabled=False`).

**Measurement is always on.** Every refinement run rolls up into `costs` like F4's event_alerts do. The dashboard's cost panel is the proof. The 72h soak measures the natural cost profile that future thresholds will be calibrated against (Appendix A).

## 13 · Exit gate and evidence approach

Update 2026-06-03: the approval model now spans F4 and F5, so the primary
approval-through-delivery evaluator is `scripts/f4_f5_exit_gate.py`. The
original `scripts/f5_exit_gate.py` remains useful for F5 soak checks, but it is
no longer sufficient by itself to judge the event-alert approval flow.

Single contiguous **72-hour soak** against live F3 OSINT. Operator interacts during the window to drive action-related checks.

### Gate criteria (all must hold)

| # | Check | How verified |
|---|-------|--------------|
| G1 | At least one morning_digest brief delivered per scheduled morning | `briefs` × `deliveries` for `mode='morning_digest' AND status='sent'`, count ≥ 3 |
| G2 | At least one light or full event alert delivered | `briefs` × `deliveries` for `mode IN ('event_alert_light', 'event_alert') AND status='sent'`, count ≥ 1 |
| G3 | At least one deep_dive brief delivered | Operator runs `forge deepdive <ticker>` at least once during the window |
| G4 | At least one structured backtest prompt accepted → F2 brief-scoped backtest completes | `brief_actions` row with `action_type='run_backtest' AND state='accepted' AND result_backtest_id IS NOT NULL`; backtests are valid only on full `event_alert` briefs with persisted run IDs |
| G5 | At least one prompt left to expire → no work done | `brief_actions` row with `state='expired' AND result_backtest_id IS NULL AND result_brief_id IS NULL` |
| G6 | At least one free-text refinement → threaded refined brief | `briefs` row with `parent_brief_id IS NOT NULL AND refine_overrides IS NOT NULL` |
| G7 | No process crashes | `systemctl status` clean on all 4 new units (plus F4's 2 + F3's adapters); `journalctl --since=<soak_start>` shows no `Restart=on-failure` entries |
| G8 | Token/cost telemetry visible | Dashboard cost chart shows ≥ 3 days of data; total spend recorded in `costs` |
| G9 | Cost guards remain off | Evaluator imports `DEFAULT_CONFIG` (which already applies env-var overrides) and asserts every guard's `enabled` key is `False` |

### `scripts/f5_exit_gate.py` and the combined gate

Runs all nine checks and produces `data/exit_gates/f5-<date>.md` (parallel to F4's evaluator output). Pre-flight checklist + runbook structure mirror `ops/runbooks/f4-exit-gate.md`.

For the approval-through-delivery flow, run:

```bash
python scripts/f4_f5_exit_gate.py --since 2026-06-03T09:00:00Z --window-hours 12
```

The combined gate reports light-alert latency, strict alert evaluation
pass/reject counts, light/full delivery audit counts, accepted approval
lineage, worker errors, cost/cache summary, and operator false-positive sample
sign-off.

### Cost outlook for the gate

- 3 mornings × 20 tickers × one balanced graph × ~$0.04/run ≈ **$2.40**
- ~20 light alerts × one quick summary call ≈ **low dollars or cents, provider-dependent**
- Approved full event studies × one balanced graph × ~$0.04/run each
- 1 deep-dive + 1 refinement (chain depth 1) ≈ **$0.30**
- 1 backtest brief-scoped over 30-day window ≈ **$0.50**
- F3 ingestion + salience continues at ~$0.05/day × 3 = **$0.15**
- **Total estimate is now approval-rate dependent**; the combined gate reports
  actual cost/cache totals from `costs`.

Well inside the cost-guards-off envelope. Provides real cost-shape data for guard calibration at end of F5.

### Pre-flight checklist (excerpt — full version in runbook)

- All 4 F5 systemd units present, `systemd-analyze verify` passes on each.
- `IIC_TELEGRAM_BOT_TOKEN`, `IIC_SMTP_USER`, `IIC_SMTP_APP_PASSWORD` set in `.env`.
- Test email sent and received from `forge morning-digest --now --dry-run` (renders template + sends, no LLM calls).
- Telegram bot `getMe` confirms token works; `allowed_chat_ids[0]` set.
- Streamlit dashboard reachable at `127.0.0.1:8501`.
- F3 sensing service running and producing events (per `ops/runbooks/f3-exit-gate.md`; verify with `sqlite3 data/iic.db "SELECT COUNT(*) FROM events WHERE ingested_ts > datetime('now', '-1 hour')"` ≥ 1).
- F4 worker + promoter running, queue depth = 0.
- `systemd-inhibit --what=sleep:idle` started for the soak window.

## 14 · Risks

F5 additions to the program risk register:

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R-F5-1 | Refinement classifier mis-extracts overrides — user says "less risk" but classifier picks `risk_tilt='more_aggressive'`, wastes a graph run | Med | `briefs.refine_overrides` is the audit trail; classifier echoes its interpretation back to the user before launching (Telegram inline message, CLI prompt line, email confirmation page); user can re-reply with a correction within the depth-3 budget |
| R-F5-2 | Refinement chain cost runaway — user replies repeatedly; no cost guard until F6 | High | Hard depth cap at 3 (D4); `refinement_chain_budget` coded `enabled=False` ready for flip; the 72h soak measures natural chain length |
| R-F5-3 | Telegram bot session loss — long-poll connection drops mid-soak; missed updates | Med | `python-telegram-bot` has built-in reconnect; `systemd Restart=on-failure`; offset persisted by the library so resumed polling catches missed updates within the Telegram lookback window |
| R-F5-4 | SMTP auth/quota failures during soak — Gmail blocks the IP or revokes the app password | Low-Med | Failure recorded as `deliveries.status='failed'`; dashboard surfaces it; soak does not crash. Pre-flight sends a test email |
| R-F5-5 | `brief_actions` race on accept — user clicks the inline button while the action-handler is mid-sweep | Low | Action-handler uses `UPDATE … WHERE state='accepted' AND result_*_id IS NULL` — idempotent. Double-click is harmless |
| R-F5-6 | Streamlit dashboard mutates state via the action_form — only mutation surface in an otherwise read-only dashboard | Low | Form writes a single `brief_actions` row with explicit `state='accepted'`; CSRF not a concern at 127.0.0.1; documented in runbook |
| R-F5-7 | Morning digest tail latency — 20 tickers still run serially across tickers | Med | Default balanced graph keeps cost lower than committee mode; documented in runbook; tail latency on dashboard alerts if it exceeds 60 min |
| R-F5-8 | Quiet-hours bug suppresses morning digest — wrong predicate flags the digest as quiet | Med | Quiet-hours check gated to `mode='event_alert'` only — boundary test asserts morning + deep-dive bypass |

## 15 · Out of scope

Deferred to F6 or post-V1:

- **Multi-recipient email** — V1 emails only to `to_addrs[0]`; multiple recipients = single delivery row.
- **Telegram group chats** — V1 supports a single private chat per `allowed_chat_ids[0]`; groups deferred.
- **Telegram free-text without reply context** — V1 only treats messages with `reply_to_message` as refinement input; top-level chat ignored.
- **Refinement of refinements beyond depth 3** — hard cap (D4).
- **Drill-down / scenario / what-if** — already deferred per program design §9; classifier may misclassify them in V1 (R-F5-1 mitigation handles).
- **Dashboard auth / remote access** — 127.0.0.1 only.
- **Backtest customization in the prompt** — V1 backtest acceptance uses the brief's recommended strategies + default 30-day window; no per-prompt parameter tuning.
- **Reminder pings** — V1 does not nag the user about pending `brief_actions` approaching `expires_at`.
- **Mobile-specific email rendering** — single Jinja template, HTML + plain alt, no responsive design.
- **F2 backtest "watchlist" mode auto-trigger** — F5 only triggers F2's brief-scoped mode; watchlist-mode backtests stay manual per F2 spec.

## 16 · Open questions deferred to implementation

1. **`python-telegram-bot` version pin** — pick at implementation; v20+ async API is preferred.
2. **Streamlit HTML embed in email** — should the morning email include the action_form as an embedded mini-form, or only a link? Decide after seeing what Gmail HTML actually renders.
3. **Refinement interpretation echo timing** — echo before launching (extra round-trip) or after launching (faster but harder to abort)? V1 default: echo immediately after the action-handler reads the action, before the graph runs.
4. **Action-handler tick interval** — 5s is a guess; tune from soak observation.
5. **Per-ticker morning-digest failure threshold** — if 50%+ of tickers error out, should the digest still send? V1: yes, always send; tune later from observed data.
6. **Streamlit refresh strategy** — autorefresh every 30s vs manual? V1: manual refresh; revisit if it hurts usability.

---

*End of IIC-FORGE-08 design. Per-phase implementation plan follows via the writing-plans skill.*
