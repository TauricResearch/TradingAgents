# Brief: Alerts Fire Integration — HTTP Route for Alert Matching Engine

**Date:** 2026-05-12
**Status:** Open
**Priority:** P2
**Type:** Induced requirement (from code registry gap-finding)
**Session:** ses_5c587d
**Induced from:** `code/INDEX.jsonl` — code registry gap-finding experiment

---

## Background

The alert system is complete through Phase 2:

| Component | File | Status |
|-----------|------|--------|
| SQLite schema | `server/lib/alerts-db.ts` | ✓ |
| CRUD routes | `server/routes/alerts.tsx` | ✓ |
| Matching engine | `server/lib/alerts-engine.ts` | ✓ |
| Telegram dispatch | `server/lib/telegram.ts` | ✓ |
| CLI trigger | `cli/commands/alerts-check.ts` | ✓ |
| **HTTP fire route** | _(missing)_ | **✗** |

All pieces exist. They are not connected via HTTP.

---

## The Gap

`cli/commands/alerts-check.ts` runs the matching engine and fires Telegram notifications. It is CLI-only.

`server/routes/alerts.tsx` provides CRUD but has no route to trigger the matching engine. There is no:
- `POST /api/alerts/fire` — run matching engine and dispatch
- `GET /api/alerts/check` — dry-run: show what would fire without sending

The system induces the requirement: every component exists; only the HTTP bridge is missing.

---

## Proposed Solution

Add `POST /api/alerts/fire` to `server/routes/alerts.tsx`:

```typescript
// POST /api/alerts/fire — run matching engine, dispatch triggered alerts via Telegram
// Body: { dryRun?: boolean }
// Response: { triggered: AlertTrigger[], dispatched: number }
```

Optionally also add `GET /api/alerts/check` for a safe preview mode.

The implementation:
1. Load all active alert rules via `listAlerts(db, { active: true })`
2. Fetch live prices for all tickers in rules via `intel-prices.ts`
3. Run `matchAlerts(rules, prices)`
4. For each triggered alert, send via `sendTelegramAlert(alert, price)` (from `telegram.ts`)
5. Record `last_triggered` in SQLite via `setLastTriggered()`
6. Return `{ triggered, dispatched }` as JSON

---

## Verification

- [ ] `POST /api/alerts/fire` returns `{ triggered: [], dispatched: 0 }` with no active rules
- [ ] `POST /api/alerts/fire` with `dryRun: true` returns what would fire without sending
- [ ] `POST /api/alerts/fire` with a triggered alert sends Telegram message
- [ ] `last_triggered` is updated in SQLite after dispatch
- [ ] `just check` passes

---

## Not in Scope

- Cron/job scheduling (use systemd timer or external scheduler)
- Email notifications (Telegram is the current channel)
- Alert deduplication (already handled in `alerts-engine.ts`)