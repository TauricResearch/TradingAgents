# Vue SPA + FastAPI Frontend Rewrite — Design

**Date:** 2026-06-09
**Status:** Approved design → pending implementation plan
**Author:** brainstorming session

## 1. Motivation

The current frontend is a single 1192-line Streamlit app (`webui.py`). Two
user-reported pains drove this rewrite:

1. **Laggy / janky interaction.** Streamlit re-runs the entire Python script
   top-to-bottom on every widget interaction, and analysis progress is shown
   via a `sleep(0.5)` + `st.rerun()` polling loop. Because the app is accessed
   remotely through a Cloudflare tunnel (`trade.recompdaily.com`), every click
   incurs a server round-trip. This is architectural and cannot be removed
   within Streamlit.
2. **Plain / dated look.** The app has *no* theme config and *no* custom CSS —
   it is the bare Streamlit default. Streamlit's styling ceiling (CSS injection
   overriding auto-generated class names, sandboxed `components.html` iframes)
   makes a fully custom, professional look fragile.

A Streamlit-polish path (theming + `st.fragment`) was considered and rejected:
it cannot remove the per-interaction server round-trip latency or the styling
ceiling. The user chose a full rewrite to a Vue SPA + FastAPI backend.

## 2. Goals & Non-Goals

**Goals**
- Replace the Streamlit UI tier with a Vue 3 SPA + FastAPI backend.
- **Strict feature parity** with the current app first (1:1 migration, no new
  features, no feature removal).
- Fundamentally fix interaction latency (client-side state, local routing) and
  give full visual control.
- Push-based live streaming of analysis progress (SSE) instead of polling.
- Zero-downtime, reversible deployment cutover.
- **Thorough end-to-end testing** before claiming done — including a real
  analysis run observed through the new stack (per project rule: healthz +
  `ast.parse` are insufficient).

**Non-Goals**
- Rewriting the `tradingagents` analysis engine, `worker.py`, the scheduler,
  the Telegram bot, or any data/memory layer. These are reused as-is.
- Adding new product features during the migration.
- Migrating storage off the existing JSON-on-disk + per-user-hash layout.

## 3. Architecture

```
┌─────────────┐   HTTPS    ┌──────────────────────────┐   spawn    ┌───────────┐
│  Vue 3 SPA  │ ─────────> │  FastAPI (uvicorn :8502) │ ─────────> │ worker.py │
│ (browser)   │  SSE       │  - auth / config / hist   │  stdout    │ (subproc, │
│             │ <───────── │  - analysis SSE relay     │  NDJSON    │  engine   │
└─────────────┘            │  - reuses backend modules │ <───────── │  unchanged│
                           │  - serves Vue static dist │            └───────────┘
                           └──────────────────────────┘
```

**Core strategy: reuse everything below the UI tier.** The inventory confirmed
that only `auth.gate()` / `auth.sign_out()` (the Streamlit UI parts of auth) are
Streamlit-coupled. Everything else is framework-agnostic and reused unchanged:

| Module | Reuse |
|---|---|
| `tradingagents/` engine, `worker.py` | unchanged — analysis runs in a subprocess exactly as today |
| `auth.py` core (`send_otp`, `verify_otp`, `issue_token`, `verify_token`, `_get_whitelist`, `_socks_patched_socket`) | reused directly; only `gate()`/`sign_out()` are replaced by FastAPI endpoints |
| `ticker_resolver.resolve_ticker` | reused as-is |
| `user_prefs` (load/save/user_home/all_users_with_prefs) | reused as-is |
| `user_research` (ingest/list/delete/clear_run_dir) | reused as-is |
| `tradingagents/agents/utils/memory.TradingMemoryLog` | reused as-is |
| `tradingagents/graph/checkpointer` | reused as-is |
| `tradingagents/dataflows/range_stats` | reused as-is |
| `notify.send_telegram` | reused as-is |
| `scheduler.py`, `bot_listener.py` | untouched; keep running as their own systemd services |

## 4. Backend (FastAPI)

A new package, e.g. `server/` (FastAPI app `server/app.py`), running under
uvicorn. It mounts the API under `/api/*` and serves the built Vue `dist/` for
all other routes (SPA fallback to `index.html`).

### 4.1 Auth

OTP email login, reusing the pure functions in `auth.py`. Session is a
**HttpOnly, Secure, SameSite=Lax cookie** carrying the existing HMAC session
token (`email|expires|sig`), so `verify_token` validates it unchanged and
whitelist-shrink revocation still works.

| Endpoint | Behavior |
|---|---|
| `POST /api/auth/request-otp` `{email}` | `send_otp(email)` → `{ok, message}` (dev-fallback message preserved) |
| `POST /api/auth/verify-otp` `{email, code}` | `verify_otp` → on success set session cookie via `issue_token`; `{ok}` |
| `GET /api/auth/me` | returns `{email}` from cookie or 401 |
| `POST /api/auth/logout` | clears cookie |

A FastAPI dependency `require_auth` reads the cookie, runs `verify_token`,
yields the email, and 401s otherwise. All endpoints below require it.

### 4.2 Config / metadata

| Endpoint | Behavior |
|---|---|
| `GET /api/providers` | provider → model lists (port `PROVIDER_MODELS` from `webui.py`) + per-provider API-key presence (`{provider: {key_present: bool}}`) |
| `GET /api/resolve-ticker?q=` | `resolve_ticker(q)` → `{ticker, message}` |
| `GET /api/range-stats?ticker=&date=` | reuse cached range-stats; returns the same payload shape `_range_stats_cached` produces, or `null` |
| `GET /api/defaults` | DEFAULT_CONFIG-derived defaults + i18n label keys needed by the client |

### 4.3 Analysis (the streaming core)

The in-flight run registry and the concurrency semaphore (`MAX_CONCURRENT_RUNS`)
move into the FastAPI process as module singletons. Each run still executes in a
`worker.py` subprocess (process isolation already solves the engine's
module-global config race — keep it).

| Endpoint | Behavior |
|---|---|
| `POST /api/analysis/start` | body = `{ticker, trade_date, provider, deep_model, quick_model, selected_analysts, max_debate_rounds, max_risk_discuss_rounds, output_language, checkpoint_enabled, user_research}`. Acquire semaphore; derive `run_id` (same email+ticker+date keying as today); spawn `worker.py`; start a background reader that parses NDJSON into an in-memory run record (accumulated chunks, stats, decision, error, status). Returns `{run_id, resumed: bool}`. If a run with the same key is already in-flight, re-attach instead of spawning (preserve today's resume-or-spawn behavior). |
| `GET /api/analysis/{run_id}/stream` | **SSE**. Replays already-accumulated events first (so a browser refresh re-attaches mid-run), then streams new events as the background reader produces them: `event: chunk` / `event: stats` / `event: done` / `event: error`. Closes on done/error. |
| `GET /api/analysis/{run_id}` | JSON snapshot of the run record (for non-SSE reconnect / history of an in-flight run). |
| `POST /api/analysis/{run_id}/cancel` | terminate the worker subprocess + release semaphore (covers today's hard-terminate path). |

**Worker protocol is unchanged.** FastAPI writes the same JSON request to the
worker's stdin and reads the same `{kind: started|chunk|stats|done|error}`
NDJSON from stdout. The background reader replaces `WorkerDrainer`'s polling
role; SSE replaces the `sleep(0.5)+rerun` loop with push.

**Orphan/cleanup defense** (per existing project hardening): the background
reader must drain stdout even if no SSE client is attached (prevents the 64 KB
pipe-buffer deadlock), and a hard-timeout terminate path is retained. The
existing systemd orphan-cleanup timer stays as defense-in-depth.

### 4.4 Research / history / prefs / checkpoints / telegram

| Endpoint | Behavior |
|---|---|
| `GET /api/research?ticker=` | `list_research` |
| `POST /api/research` (multipart upload) | `ingest_research` (summarize_fn = a quick LLM via `create_llm_client`) |
| `DELETE /api/research/{ticker}/{digest}` | `delete_research` |
| `GET /api/history` | `TradingMemoryLog.load_entries()` for the user |
| `GET /api/history/{ticker}/{date}` | full state JSON from disk |
| `GET /api/prefs` / `PUT /api/prefs` | `user_prefs.load` / `save` (daily schedule, watchlist, telegram_chat_id, defaults) |
| `GET /api/checkpoints` | per-ticker resumable checkpoint status (`checkpoint_step`) |
| `DELETE /api/checkpoints` | `clear_all_checkpoints` |
| `POST /api/telegram/test` `{chat_id}` | `notify.send_telegram` test ping |

### 4.5 Transport choice

**SSE over WebSocket.** Streaming is one-directional (server→client progress);
SSE is simpler, auto-reconnects, and passes cleanly through the Cloudflare
tunnel. Control actions (start/cancel) are ordinary POSTs.

## 5. Frontend (Vue 3 SPA)

Stack: **Vue 3 + Vite + TypeScript + Pinia + Vue Router + Naive UI + vue-i18n**.

- **Naive UI** chosen for a modern, clean, themeable, TS-native component set
  suited to a finance dashboard (the "look good" requirement is primary).
- **i18n:** port the existing `LANG` dict (en/zh) into vue-i18n resources;
  language toggle persisted to localStorage and `/api/prefs`.
- **State:** a Pinia `analysisStore` holds the live run; an `EventSource`
  subscription updates it reactively → tabs and the pipeline indicator update
  incrementally with **no full-page reload**.
- **Routing:** client-side routes give clean deep links (`/analysis`,
  `/run/:id`, `/history`, `/history/:ticker/:date`, `/settings`), browser
  back/forward, and shareable URLs.

**Views (feature parity map):**

| View | Replaces (Streamlit) |
|---|---|
| Login | `auth.gate()` email + OTP forms |
| Analysis | sidebar config (ticker w/ live resolve, date, provider, deep/quick model w/ key status, analyst checkboxes, debate/risk rounds, output language, checkpoint controls) + range-stats card + Run button + live run panel with tabs (Market / Sentiment / News / Fundamentals / Investment Plan / Trader / Risk Decision / Activity log) + elapsed timer + pipeline indicator |
| History | past runs from memory log; open a past run's full state into the same tabbed report view |
| Settings | daily-schedule panel (enable, watchlist, telegram_chat_id + test ping), user-research upload/list/delete, default preferences, sign-out |

## 6. Deployment & migration (zero-downtime, reversible)

1. Add `trading-api.service` (systemd user unit) running
   `uvicorn server.app:app --host 127.0.0.1 --port 8502`, same env as the
   webui service (miniconda python, proxy script).
2. FastAPI serves both `/api/*` and the Vue `dist/` build (Vite `build` step in
   the deploy flow).
3. The existing `trading-webui.service` (Streamlit, :8501) **stays running**
   during development and the verification window.
4. After full E2E verification on :8502, repoint the Cloudflare tunnel from
   `127.0.0.1:8501` → `127.0.0.1:8502`. Rollback = repoint back to :8501.
5. Follow the dev/prod split: develop in `~/workdir/TradingAgents`, deploy to
   `~/prod/TradingAgents` via `git reset --hard` + `systemctl restart`.

## 7. Testing strategy (first-class — addresses the "test thoroughly" goal)

- **Backend (pytest):**
  - Unit: auth token issue/verify, OTP request/verify with dev-fallback, prefs
    load/save, ticker resolve, providers/key-status, range-stats shape.
  - Integration: `POST /api/analysis/start` against a **stub worker** that emits
    canned NDJSON, asserting the SSE endpoint streams `chunk`→`stats`→`done` and
    that mid-stream `GET /api/analysis/{id}` snapshot replays accumulated chunks
    (reconnect path).
- **Frontend:**
  - Vitest component tests for the analysis store (SSE event → reactive state)
    and key components.
  - **Playwright E2E** against the real running stack with `AUTH_DEV_FALLBACK=1`:
    log in via dev OTP → start a **real analysis** → assert streamed reports
    appear in tabs → assert a final BUY/SELL/HOLD decision renders.
- **Pre-cutover manual gate:** a real end-to-end analysis run observed on :8502
  before the tunnel is switched. (Project rule: never claim done on healthz +
  syntax-parse alone.)

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Auth cookie semantics differ from URL-token (cross-site, tunnel) | SameSite=Lax + Secure; verify cookie survives refresh through the tunnel during the verification window |
| SSE buffering by Cloudflare tunnel | disable proxy buffering / send periodic heartbeat comments; verify live streaming end-to-end before cutover |
| Pipe-buffer deadlock if no client attached | background reader always drains stdout regardless of SSE attachment; retain hard-timeout terminate + orphan-cleanup timer |
| Feature drift from Streamlit | explicit parity map (§5); spec review against `webui.py` before sign-off |
| Big-bang risk | phased plan; Streamlit stays live; tunnel cutover is the only switch and is instantly reversible |

## 9. Implementation phasing (for the plan)

Sequential foundation, then parallel fan-out where independent:

1. **Foundation (serial):** FastAPI skeleton, auth + session middleware, static
   serving, and the **frozen API contract** (request/response schemas).
2. **Read-only endpoints (parallel):** providers, resolve-ticker, range-stats,
   history, prefs, research — one unit each.
3. **Analysis streaming core (serial, carefully verified):** run registry +
   semaphore, worker spawn/reattach, background NDJSON reader, SSE relay,
   snapshot/reconnect, cancel.
4. **Vue scaffold + SSE store (serial):** Vite/TS/Pinia/Router/Naive UI, i18n,
   analysisStore + EventSource.
5. **Vue views (parallel):** Login, Analysis, History, Settings.
6. **E2E tests + deployment cutover (serial):** Playwright + pytest green, real
   run on :8502, repoint tunnel.

Phases 2 and 5 are the natural concurrency seams (independent units behind a
frozen contract); phases 1, 3, 4, 6 are the serial critical path.
