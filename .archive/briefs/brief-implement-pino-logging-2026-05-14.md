# Brief: Implement Pino Logging System

**Date:** 2026-05-14
**Status:** In Review

---

## Task: Replace scattered console.* calls with structured Pino logging

**Objective:** The codebase has inconsistent logging — `console.log`, `console.error`, `console.warn`, `process.stdout.write` scattered across server routes, CLI commands, and scripts. Replace with a centralized Pino logger that provides:
- Structured JSON logging (machine-parseable)
- Log levels (trace, debug, info, warn, error, fatal)
- Request/request IDs for tracing
- Environment-appropriate output (pretty in dev, JSON in prod)

## Why Pino?

- Bun-native (fast, async-safe)
- Structured JSON by default (observability tooling friendly)
- Request-scoped logging via `child` loggers
- Production-ready with low overhead

## What

### Phase 1 — Core Logger Setup

- [x] Create `src/lib/logger.ts` with:
  - Pino instance configured for Bun environment
  - `LOG_LEVEL` env var support (default: `info`, dev: `debug`)
  - Pretty output in development (`NODE_ENV !== "production"`), JSON in production
  - `createLogger(name: string)` factory for named child loggers
  - Export: `{ logger, createLogger }`
- [x] Create `src/lib/request-logger.ts` for HTTP request context:
  - `createRequestLogger(requestId: string, meta?: Record<string, unknown>)`
  - Adds `requestId` field to all logs automatically
- [x] Update `src/server/index.tsx` to:
  - Initialize logger at startup
  - Log server start/stop events

### Phase 2 — Server Routes

- [x] Audit `src/server/routes/*.ts` for `console.*` usage
- [x] Replace with `requestLogger.info/warn/error`:
  - Replace `console.log` → `requestLogger.info()`
  - Replace `console.error` → `requestLogger.error()`
  - Replace `console.warn` → `requestLogger.warn()`
- [x] Add request/response logging middleware:
  - Log incoming requests: method, path, requestId
  - Log response: status code, duration
- [x] Error handling: wrap route handlers with try/catch → `requestLogger.error(err)`

### Phase 3 — CLI Commands

- [x] Audit `src/cli/commands/*.ts` for `console.*` and `stdout/stderr.write`
- [~] Replace with logger calls (partial - analyze.ts, plan.ts updated):
  - Status/progress output → `logger.info()` or `logger.debug()`
  - Error messages → `logger.error()`
  - Warnings → `logger.warn()`
  - **Note:** Keep `process.stdout.write` for tabular/spinner output (user-facing data, not logs)
- [x] Add `--quiet` / `--verbose` flags to CLI (analyze.ts, plan.ts):
  - `--quiet`: only log errors
  - `--verbose`: log everything including debug

### Phase 4 — Scripts

- [x] Audit `scripts/*.ts` for `console.*` usage
- [x] Replace with logger where appropriate
  - **Decision:** Scripts are utility tools that produce user-facing tabular output. They are excluded from the `noConsole` rule via biome.json override for `scripts/**`. No changes required.
- Scripts that produce data output (not logs) keep `stdout.write`

### Phase 5 — Deprecation Enforcement

- [x] Add biome rule or custom script to catch `console.*` in production paths:
  - Pattern: `console\.(log|error|warn|info|debug)` in `src/**/*.{ts,tsx}`
  - Exceptions: test files, scripts/, archive/, src/cli/** (pending migration)
- [x] Wire into `just check` as a custom gate

## How to Verify

- [x] Run `just check` — no new `console.*` in `src/server/` or `src/lib/` (except test files)
- [x] `bun run src/server/index.tsx` shows structured JSON logs (or pretty in dev)
- [x] `trading analyze AAPL --verbose` shows debug-level logs
- [x] `trading analyze AAPL --quiet` shows only errors
- [x] Server request logs include `requestId` field
- [x] Log output is parseable JSON in production

## Technical Notes

- Pino is already Bun-compatible via `pino` npm package
- Use `pino-pretty` for dev formatting (add to dev dependencies)
- Child loggers inherit base config, can add per-module context
- Avoid logging sensitive data (API keys, passwords, PII) — add sanitize utility if needed
- Log levels: trace=0, debug=1, info=2, warn=3, error=4, fatal=5

## Out of Scope

- Logging to files (use system-level log rotation instead)
- Log aggregation infrastructure (Datadog, ELK, etc.) — just format correctly
- Performance profiling — separate concern
- Migration of remaining CLI commands (can be done incrementally)

---

## Done

When all `[x]` items are checked and verified:
- ✅ Phase 1 complete: Core logger infrastructure created
- ✅ Phase 2 complete: Server routes updated with request logging
- ⚠️ Phase 3 partial: analyze.ts and plan.ts updated with --quiet/--verbose flags
- ✅ Phase 4 complete: Scripts audited and excluded (user-facing output)
- ✅ Phase 5 complete: biome.json enforces noConsole in src/server and src/lib

**Remaining:** Migration of remaining ~30 CLI command files. Can be done incrementally as a follow-up task.