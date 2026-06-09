# Vue SPA + FastAPI Frontend Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Streamlit `webui.py` UI tier with a Vue 3 SPA + FastAPI backend at strict feature parity, fixing interaction latency (client-side state) and styling, with push-based (SSE) live analysis streaming.

**Architecture:** FastAPI (uvicorn :8502) reuses every non-UI module unchanged and spawns `worker.py` subprocesses exactly as today; it relays the worker's NDJSON to the browser over SSE and serves the built Vue `dist/`. The Vue SPA (Naive UI) holds run state client-side. Cutover is a Cloudflare tunnel repoint (:8501→:8502), instantly reversible.

**Tech Stack:** Python FastAPI + uvicorn + sse-starlette + pytest + httpx; Vue 3 + Vite + TypeScript + Pinia + Vue Router + Naive UI + vue-i18n + Vitest + Playwright.

Reference spec: `docs/superpowers/specs/2026-06-09-vue-frontend-rewrite-design.md`.

---

## File Structure

```
server/                         # NEW FastAPI backend package
  __init__.py
  app.py                        # FastAPI app, CORS, static mount, router include
  config.py                     # settings (port, cookie name, dirs) from env
  deps.py                       # require_auth dependency, get_email
  schemas.py                    # Pydantic request/response models (the CONTRACT)
  routers/
    auth.py                     # /api/auth/*
    meta.py                     # /api/providers, /api/resolve-ticker, /api/range-stats, /api/defaults
    analysis.py                 # /api/analysis/* (start, stream, snapshot, cancel)
    research.py                 # /api/research*
    history.py                  # /api/history*
    prefs.py                    # /api/prefs
    checkpoints.py              # /api/checkpoints
    telegram.py                 # /api/telegram/test
  runs.py                       # RunRegistry: spawn worker, drain stdout, semaphore, snapshot, SSE feed
  providers.py                  # PROVIDER_MODELS map + key-status (ported from webui.py)
tests/server/                   # NEW backend tests
  conftest.py                   # TestClient + tmp HOME fixture + env
  test_auth.py
  test_meta.py
  test_analysis_stream.py       # uses a stub worker
  test_prefs.py
  test_research.py
  _stub_worker.py               # emits canned NDJSON for stream tests
frontend/                       # NEW Vue SPA
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  playwright.config.ts
  src/
    main.ts
    App.vue
    router.ts
    i18n.ts                     # ported LANG dict (en/zh)
    api/client.ts               # fetch wrapper (credentials: include)
    api/sse.ts                  # EventSource helper
    stores/auth.ts
    stores/analysis.ts          # live run state from SSE
    stores/prefs.ts
    views/LoginView.vue
    views/AnalysisView.vue
    views/HistoryView.vue
    views/SettingsView.vue
    components/                 # ConfigPanel, ReportTabs, PipelineBar, RangeStatsCard, etc.
  tests/                        # Vitest unit + Playwright e2e
    analysis.store.spec.ts
    e2e/run-analysis.spec.ts
scripts/
  run_api.sh                    # NEW: uvicorn launcher (mirrors run_webui.sh env)
```

---

## Phase 1 — Foundation (serial)

### Task 1: Backend package skeleton + health

**Files:**
- Create: `server/__init__.py`, `server/config.py`, `server/app.py`
- Test: `tests/server/conftest.py`, `tests/server/test_health.py`

- [ ] **Step 1: conftest fixture** — TestClient with a tmp `HOME` so user data writes go to a sandbox.

```python
# tests/server/conftest.py
import os, pytest
from pathlib import Path

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ALLOWED_EMAILS", "a@b.com")
    monkeypatch.setenv("AUTH_DEV_FALLBACK", "1")
    from fastapi.testclient import TestClient
    from server.app import create_app
    return TestClient(create_app())
```

- [ ] **Step 2: failing test**

```python
# tests/server/test_health.py
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
```

- [ ] **Step 3: run, expect fail** — `pytest tests/server/test_health.py -v` → import error / 404.

- [ ] **Step 4: implement**

```python
# server/config.py
import os
class Settings:
    port = int(os.getenv("TRADINGAGENTS_API_PORT", "8502"))
    cookie_name = "ta_session"
    frontend_dist = os.getenv("TRADINGAGENTS_FRONTEND_DIST", "frontend/dist")
settings = Settings()
```

```python
# server/app.py
from fastapi import FastAPI
def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents API")
    @app.get("/api/health")
    def health():
        return {"ok": True}
    return app
app = create_app()
```

- [ ] **Step 5: run, expect pass; commit** `feat(api): FastAPI skeleton + health`

### Task 2: API contract — Pydantic schemas (THE CONTRACT, unblocks parallel work)

**Files:** Create `server/schemas.py`; Test `tests/server/test_schemas.py`

- [ ] **Step 1:** Define every request/response model used across routers so phases 2 & 5 can be built in parallel against it. Include: `OtpRequest{email}`, `OtpVerify{email,code}`, `Me{email}`, `ResolveResult{ticker,message}`, `ProviderInfo{models:list[str],key_present:bool}`, `AnalysisStartReq{ticker,trade_date,provider,deep_model,quick_model,selected_analysts:list[str],max_debate_rounds:int,max_risk_discuss_rounds:int,output_language:str,checkpoint_enabled:bool,user_research:str|None}`, `AnalysisStartResp{run_id,resumed}`, `RunSnapshot{run_id,status,chunks:list[dict],stats:dict|None,decision:str|None,error:dict|None,started_at:float,elapsed:float}`, `Prefs{...all user_prefs keys...}`, `ResearchItem{...}`, `HistoryEntry{...}`.
- [ ] **Step 2-5:** Trivial instantiation test, run, commit `feat(api): freeze request/response schemas`.

### Task 3: Auth core wiring + session cookie + require_auth dep

**Files:** Create `server/deps.py`, `server/routers/auth.py`; Modify `server/app.py` (include router); Test `tests/server/test_auth.py`

- [ ] **Step 1: failing tests** — request-otp (dev fallback returns ok), verify-otp wrong code 400, verify-otp right code sets cookie, `/api/auth/me` 401 without cookie / 200 with cookie, logout clears cookie. (Read dev OTP from `/tmp/tradingagents_otp.log`.)
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement** reusing `auth.send_otp/verify_otp/issue_token/verify_token`. `require_auth` reads `settings.cookie_name`, runs `verify_token`, 401 on None. Set cookie httponly/secure/samesite=lax with token; max_age from SESSION_TTL_DAYS.
- [ ] **Step 4-5:** pass; commit `feat(api): OTP auth endpoints + session cookie`.

### Task 4: Static SPA serving + run script

**Files:** Modify `server/app.py`; Create `scripts/run_api.sh`

- [ ] Mount `StaticFiles` at `/` for `settings.frontend_dist` with `html=True`, and an SPA fallback so non-`/api` routes return `index.html`. Guard: only mount if dist exists (tests run without it).
- [ ] `scripts/run_api.sh` mirrors `run_webui.sh` env (proxy source, miniconda python) and execs `uvicorn server.app:app --host 127.0.0.1 --port ${TRADINGAGENTS_API_PORT:-8502}`.
- [ ] Commit `feat(api): serve Vue dist + uvicorn launcher`.

---

## Phase 2 — Read-only endpoints (PARALLEL: one unit each)

Each task is independent behind the Task-2 contract. **Concurrency seam.**

### Task 5: providers + defaults (`server/providers.py`, `server/routers/meta.py`)
- [ ] Port `PROVIDER_MODELS` from `webui.py`. `GET /api/providers` → `{provider: {models, key_present}}` using the same env-key map. `GET /api/defaults` → DEFAULT_CONFIG-derived defaults. Tests assert known providers present + key_present reflects env. Commit.

### Task 6: resolve-ticker (`server/routers/meta.py`)
- [ ] `GET /api/resolve-ticker?q=` → `resolve_ticker(q)`. Test with an alias (e.g. 苹果→AAPL) monkeypatching the resolver to avoid network. Commit.

### Task 7: range-stats (`server/routers/meta.py`)
- [ ] `GET /api/range-stats?ticker=&date=` reusing the cached compute; return payload or null. Test monkeypatches compute. Commit.

### Task 8: prefs (`server/routers/prefs.py`)
- [ ] `GET /api/prefs` → `user_prefs.load(email)`; `PUT /api/prefs` → `user_prefs.save`. Auth required → keyed by cookie email. Test round-trips a pref change. Commit.

### Task 9: history (`server/routers/history.py`)
- [ ] `GET /api/history` → memory-log entries; `GET /api/history/{ticker}/{date}` → full state JSON from the user's logs dir. Test writes a fake full_states_log json then reads it. Commit.

### Task 10: research (`server/routers/research.py`)
- [ ] `GET /api/research?ticker=` list; `POST /api/research` multipart upload → `ingest_research` (summarize_fn via `create_llm_client`, monkeypatched in test); `DELETE /api/research/{ticker}/{digest}`. Test list+delete with a stubbed ingest. Commit.

### Task 11: checkpoints + telegram (`server/routers/checkpoints.py`, `server/routers/telegram.py`)
- [ ] `GET /api/checkpoints` status, `DELETE /api/checkpoints` clear-all; `POST /api/telegram/test` → `notify.send_telegram` (monkeypatched). Commit.

---

## Phase 3 — Analysis streaming core (serial, carefully verified)

### Task 12: RunRegistry — spawn worker + drain stdout + semaphore

**Files:** Create `server/runs.py`; Test `tests/server/_stub_worker.py`, `tests/server/test_analysis_stream.py`

- [ ] **Step 1: stub worker** that reads stdin JSON and emits canned NDJSON: `started`, two `chunk`s, `stats`, `done`.
- [ ] **Step 2: failing test** — `RunRegistry.start(email, req)` returns run_id; a background thread drains stdout into the run record; `snapshot(run_id)` eventually shows status=done with 2 chunks + decision. Use the stub worker path via env override.
- [ ] **Step 3: implement** — semaphore (`MAX_CONCURRENT_RUNS`), run_id keying (email+ticker+date, same as webui), `subprocess.Popen([python,"-u",worker])`, daemon reader thread parsing NDJSON, in-memory record `{status,chunks,stats,decision,error,started_at,subscribers}`, **always drains stdout even with no subscriber** (pipe-deadlock defense), hard-timeout terminate, `cancel(run_id)`, resume-or-reattach if key already in-flight.
- [ ] **Step 4-5:** pass; commit `feat(api): RunRegistry worker spawn + NDJSON drain`.

### Task 13: analysis router — start / stream(SSE) / snapshot / cancel

**Files:** Create `server/routers/analysis.py`; Test extends `test_analysis_stream.py`

- [ ] **Step 1: failing test** — `POST /api/analysis/start` returns run_id; `GET /api/analysis/{id}/stream` (TestClient stream) yields SSE events ending in `event: done`; `GET /api/analysis/{id}` snapshot replays accumulated chunks; `POST /api/analysis/{id}/cancel` terminates.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement** with `sse-starlette` `EventSourceResponse`: first replay buffered events, then tail new ones via an asyncio queue fed by the reader; heartbeat comment every 15s (tunnel anti-buffering). Auth required.
- [ ] **Step 4-5:** pass; commit `feat(api): analysis start + SSE stream + snapshot + cancel`.

---

## Phase 4 — Vue scaffold + SSE store (serial)

### Task 14: Vite/TS/Pinia/Router/Naive UI scaffold + i18n
- [ ] Create `frontend/` with Vite Vue-TS template, add Naive UI, Pinia, Vue Router, vue-i18n. Port `LANG` en/zh into `src/i18n.ts`. `App.vue` wraps `n-config-provider` with a dark/clean theme + `n-message-provider`. Router with the 4 views (lazy). `api/client.ts` = fetch wrapper with `credentials:"include"`. Build check: `npm run build` succeeds. Commit `feat(web): Vue scaffold + Naive UI + i18n`.

### Task 15: analysis store + SSE helper (Vitest)
- [ ] `api/sse.ts` wraps `EventSource`. `stores/analysis.ts` actions `start()`, `subscribe(runId)`, handlers for chunk/stats/done/error updating reactive `reports` (per-tab), `pipelineStep`, `status`, `decision`. **Step 1:** Vitest test feeding mock SSE events asserts store maps a `chunk` payload to the right report fields and `done` sets decision. Implement. Commit `feat(web): analysis store + SSE streaming`.

---

## Phase 5 — Vue views (PARALLEL behind the contract + scaffold)

**Concurrency seam.** Each view is an independent unit using the store/api.

### Task 16: LoginView — email→OTP→cookie; redirect on auth. Vitest renders form, mocks api. Commit.
### Task 17: AnalysisView — ConfigPanel (ticker w/ debounced resolve, date, provider/model selects w/ key-status, analyst checkboxes, rounds, output lang, checkpoint controls), RangeStatsCard, Run button, live ReportTabs (8 tabs), PipelineBar, elapsed timer. Wires to analysis store. Commit.
### Task 18: HistoryView — list past runs, open one into the same ReportTabs (read-only). Commit.
### Task 19: SettingsView — daily-schedule (enable, watchlist, telegram_chat_id + test ping), research upload/list/delete, default prefs, sign-out. Commit.

---

## Phase 6 — E2E tests + deployment cutover (serial)

### Task 20: Playwright E2E — real run
- [ ] `playwright.config.ts` + `tests/e2e/run-analysis.spec.ts`: start backend with `AUTH_DEV_FALLBACK=1` on a test port, build+serve frontend, log in via dev OTP (read code from `/tmp/tradingagents_otp.log`), submit a real analysis for a cheap ticker, assert a report tab populates and a final decision label (BUY/SELL/HOLD) renders within a timeout. Commit `test(web): Playwright E2E real analysis run`.

### Task 21: Backend test suite green + lint
- [ ] `pytest tests/server -v` all pass; `python -c "import server.app"`. Commit.

### Task 22: Deploy cutover (manual gate)
- [ ] Add `~/.config/systemd/user/trading-api.service` (mirrors webui env, runs `run_api.sh`). Build frontend → `frontend/dist`. Deploy to `~/prod` via git + restart. **Manually run one real end-to-end analysis on :8502** (project rule: no done-claim on healthz/parse alone). Then repoint Cloudflare tunnel :8501→:8502. Keep Streamlit service for rollback. Document rollback in commit body.

---

## Self-Review

**Spec coverage:** auth (T3), providers/key-status (T5), resolve (T6), range-stats (T7), prefs/schedule (T8/T19), history (T9/T18), research (T10/T19), checkpoints/telegram (T11/T19), analysis SSE core (T12/T13), reconnect snapshot (T13), Vue views parity map (T16-19), i18n (T14), deployment cutover + rollback (T22), testing incl. real E2E run (T20/T22). All spec sections mapped.

**Placeholder scan:** schemas/views enumerate concrete fields from the inventory; no TBD/TODO. CRUD tasks (Phase 2/5) are intentionally one-unit-each for parallel dispatch — each names exact files, endpoints, and test approach.

**Type consistency:** `run_id`, `selected_analysts`, `RunSnapshot` fields, cookie name `ta_session`, port 8502, `PROVIDER_MODELS` used consistently across tasks.

**Concurrency map:** serial = Phases 1,3,4,6; parallel = Phase 2 (T5-11) and Phase 5 (T16-19), each behind the Task-2 contract + Task-14 scaffold.
