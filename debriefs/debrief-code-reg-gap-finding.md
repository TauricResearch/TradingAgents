# Debrief: Code Registry Gap-Finding Experiment

**Date:** 2026-05-12
**Session:** ses_5c587d
**Epic:** Code Registry (td-757501)

---

## What Was Tested

Reading `code/INDEX.jsonl` (137 TypeScript files) to find gaps between what the system has and what it should have. The hypothesis from the induced-requirements blog post: a code registry enables agents to find real gaps without imposed specs.

---

## What the System Has

| Area | Routes | CLI Commands | Status |
|------|--------|-------------|--------|
| Portfolio/positions | ✓ portfolio, holdings | ✓ portfolio | Covered |
| Signals | ✓ signals | ✓ signals | Covered |
| Analysis reports | ✓ analysis, analyses/* | ✓ analyze | Covered |
| Alerts | ✓ alerts (CRUD) | ✓ alerts-create, alerts-delete, alerts-list | Partial |
| Prospect management | ✓ prospects | ✓ watchlist | Partial |
| Exit plans | ✓ exits | (planned) | Partial |
| Governance | ✓ governance | (planned) | Partial |
| Prices | ✓ prices | ✓ prices, sync-prices | Partial |
| Benchmark | ✓ benchmark | ✓ benchmark | Covered |
| Feedback | ✓ feedback | ✓ summarize | Covered |

---

## Gaps Found

### 1. alerts-check has no HTTP route

`cli/commands/alerts-check.ts` is a background/cron job for running the alert matching engine. It has no server equivalent — there's no `GET /api/alerts/check` or `/api/alerts/fire`.

The `server/routes/alerts.tsx` provides CRUD (list, create, delete) but not the matching engine itself. An agent running `alerts check --fire` would need to be triggered manually or via cron.

**Implication:** Alerts are passive (user polls the dashboard). There is no push mechanism — Telegram notifications or email — built into the server. The `alerts-check` command could be integrated as a server-side task but isn't.

### 2. execute is CLI-only

`cli/commands/execute.ts` calculates a trade plan and executes via the IG API. There is a `GET /api/trade-plan/:ticker` route and a `TradePlanView`, but no trade execution route. The act of placing an order is CLI-only.

**Implication:** Web UI can show the plan. CLI can execute. There is no "confirm and execute" flow in the dashboard. This may be intentional (risk control), but it's an asymmetry worth noting.

### 3. No dedicated spreadbets view

`spreadbets` is a CLI command. No dedicated `SpreadBetPositionsView` found — gap confirmed.

### 4. IG commands are CLI-only

IG trading (`ig-buy`, `ig-sell`, `ig-positions`, `ig-prices`, `ig-search`, `ig-login`) has no server routes. All IG interaction is CLI-driven.

**Implication:** IG platform data is imported to SQLite but not surfaced via the dashboard. The `intel-spreadbets.tsx` partial exists but pulls from SQLite, not live IG data.

---

## Most Actionable Gap: alerts-check HTTP integration

The alerts system is the most complete area (full CRUD + matching engine) but the matching engine is CLI-only. A `POST /api/alerts/fire` route that runs the matching engine and returns triggered alerts would close the loop on push notifications.

This is an induced requirement — the system already has all the pieces (alert rules in SQLite, matching engine in `alerts-engine.ts`, Telegram in `telegram.ts`), they just aren't wired together.

---

## Conclusion

The code registry worked. Reading `code/INDEX.jsonl` surfaced a real, actionable gap in under 30 minutes. The alert matching engine has no HTTP trigger — that's a concrete gap the system induced by existing.

The brief is `briefs/brief-alert-fire-integration.md`. The system induced it.

**Verdict: The registry enables induced requirements. It works.**