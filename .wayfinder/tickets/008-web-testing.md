---
id: 008
title: "Decide: web-layer testing strategy"
labels: [wayfinder:grilling]
status: closed
assignee: JMAN730
blocked-by: [005]
---

## Question

How is the web layer tested, consistent with the repo's existing pytest suite (`tests/`, pytest + pytest-subtests, no browser tooling)?

- API/SSE: FastAPI TestClient (httpx) over the JSON endpoints and the SSE stream (replay from Last-Event-ID, terminal event, keepalive)? Fake run engine vs real graph with mocked LLM clients?
- Run manager: unit tests for serialization (single active run), cancellation semantics, crash surfacing.
- Frontend JS: is any browser-level testing warranted (Playwright exists as a plugin locally but is NOT a repo dep), or is the vanilla-JS layer thin enough that API-contract tests + the markdown sanitize pipeline (testable via a tiny node-less harness or not at all) suffice?
- CSP/security assertions worth encoding as tests (headers present, Host-allowlist rejects).

## Resolution

Decided; environment facts verified (anyio 4.13.0 pytest plugin importable, httpx 0.28.1 present — both already transitive deps, zero new test dependencies).

1. **Same pytest suite, flat naming:** `tests/test_web_*.py`, matching the repo's existing flat layout, pytest + pytest-subtests. Async tests use the **anyio pytest plugin** (`@pytest.mark.anyio`, asyncio backend only) — no pytest-asyncio dependency.
2. **Injectable engine seam:** RunManager takes the run-driving callable as a constructor dependency; tests inject a scripted fake emitting canned projected events. This is the load-bearing test seam — no LLM calls, no network, no real graph in web tests.
3. **API/SSE contract tests** via FastAPI TestClient (httpx): SSE replay-from-Last-Event-ID, monotonic event ids, terminal `done`/`error`/`cancelled` event always emitted (also prevents hanging streams in tests — the fake engine always terminates, plus a test-level timeout), 409 while a run is active (including draining), idempotent cancel, `run.json` manifest written, history listing with and without manifests.
4. **Run-manager unit tests:** single-active invariant counts draining; per-run executor drains before slot release; crash → `failed` + error event content; pre-run key validation failure.
5. **Security regression tests (mandatory):** CSP header present and exact on index/static responses; Host-allowlist rejects a foreign `Host:` header; `GET /api/config` payload keys are exactly the whitelist; key-echo test — set a fake `OPENAI_API_KEY` in the test env and assert its value appears nowhere in any API response body; `backend_url` never echoed.
6. **Scaffolding conformance tests (from 005's checklist):** web run config overrides `stream_mode`; checkpoint-enabled path constructs AsyncSqliteSaver (tmp-path smoke); post-phase order includes store_decision/clear_checkpoint.
7. **No browser automation in v1.** Vanilla JS layer keeps logic in pure functions (store reducers) for future testability; UI verified by a manual smoke checklist recorded in the spec. Playwright exists only as a local plugin, not a repo dep — stays that way.
