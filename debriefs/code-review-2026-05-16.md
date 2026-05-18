---
agent: Terax
role: code reviewer
date: 2026-05-16
repository: tradingagents
scope: project review
---

# Code Review

## Findings

[MUST] `src/server/index.tsx:95-136` — schema/migration work runs at module import time on every process start, before the app is even exported → move DB init/migrations behind an explicit startup path and make them idempotent/atomic so a bad migration can’t prevent the server from booting.

[SHOULD] `src/server/index.tsx:104-136` — the `ALTER TABLE` / `CREATE INDEX` blocks ignore all errors, so unrelated migration failures are silently swallowed and the app keeps running with a potentially broken schema → check the error message/code and only ignore “already exists”; surface any other failure and fail fast.

[SHOULD] `src/server/lib/hledger.ts:68-76, 108-119` — `hledger` is spawned without a timeout, so a hung CLI call can tie up request handlers indefinitely → add per-call timeout/kill logic matching the Python bridge pattern.

[SHOULD] `scripts/py/analyze_stream.py:56-83` — `poll_state()` only emits each report key once, but it is called only after synchronous `propagate()`, so the “real-time streaming” comments are misleading and the queue-based design can’t actually stream intermediate state → either wire actual step hooks or remove the streaming claims and simplify the implementation.

[SHOULD] `scripts/py/analyze_stream.py:86-100` — the code appends `seen_debates`/`seen_reports` only after the final synchronous run, which means any transient state changes during propagation are lost; debate/report updates won’t be incremental → if live updates matter, emit from the graph’s internal step boundaries rather than a post-run snapshot.

## Todos

- [ ] Move DB bootstrap/migrations out of module import in `src/server/index.tsx`.
- [ ] Tighten migration error handling so only benign duplicate-object cases are ignored.
- [ ] Add timeout/kill handling to `hledger` subprocess calls.
- [ ] Either implement real incremental streaming in `analyze_stream.py` or simplify the comments/design to match synchronous behavior.
- [ ] Add/adjust tests around migration failure handling and bridge streaming behavior.
