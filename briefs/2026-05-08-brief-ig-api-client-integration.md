# Brief: IG API Client Integration

**Date**: 2026-05-08
**Status**: open
**Epic**: UNIFIED-CLI-001

## Problem

The CLI `plan` command calculates trade plans but cannot interact with the
IG API. We have validated instrument configs (`src/cli/lib/ig-instruments.ts`)
and documented API connectivity (`docs/ig-connectivity-config.md`), but all
actual API calls are manual curl scripts.

To move toward automated trading workflow, we need a programmatic IG API
client integrated into the codebase.

## Solution

Integrate `@bennycode/ig-trading-api` as the official IG API client.
Validate with lab experiment first, then integrate into CLI.

## Package

- **Name**: `ig-trading-api` (npm)
- **Repository**: `bennycode/ig-trading-api` (archived on GitHub, npm package active)
- **Version**: 0.13.9 (June 2024)
- **Language**: 100% TypeScript
- **Coverage**: 100%
- **License**: MIT
- **Dependencies**: axios, axios-retry, lightstreamer-client-node, luxon

### Concerns

- Repository is **archived** on GitHub (no further updates)
- For demo account use, this is acceptable — we can fork if needed
- Package has 5 production dependencies (axios is the main one)

## Lab Experiment (scripts/lab/ig-client.ts)

Validate the client with demo credentials before touching production code:

1. **Login** — authenticate with IG demo API, obtain session tokens
2. **Account info** — fetch account balances, confirm account IDs match our config
3. **Market search** — search for FTSE 100 and AAPL, confirm EPICs match our config
4. **Price history** — fetch 14 days of prices for a ticker
5. **Place test trade** — open a small spread bet (£1/point), record deal reference
6. **Close test trade** — close the position, confirm P&L
7. **Error handling** — test invalid EPIC, test insufficient margin

## Integration Plan

### Phase 1: Lab (this brief)
- Install `ig-trading-api`
- Write `scripts/lab/ig-client.ts`
- Run all 7 validation steps
- Document findings in debrief

### Phase 2: CLI Subcommand
- Add `trading ig login` — store session tokens
- Add `trading ig accounts` — list accounts
- Add `trading ig markets <TICKER>` — search markets
- Add `trading ig prices <EPIC>` — fetch prices
- Add `trading ig order` — place order from trade plan

### Phase 3: Bridge
- Wire `trading plan AAPL` → `trading ig order` workflow
- Validate plan against live market data before order placement
- Record all trades in SQLite + hledger

## Acceptance Criteria

- [x] Lab experiment passes all 7 steps (custom fetch client, ig-trading-api abandoned)
- [x] Custom client type-checks with tsc
- [x] No new Python dependencies (TypeScript/Bun only)
- [x] Demo credentials from env vars (not in git)
- [x] CLI subcommands: login, accounts, search, prices, positions, buy, sell
- [x] `trading execute` bridges trade plan to IG order placement
- [x] Orders recorded in SQLite trades table
- [ ] Integration documented in `docs/ig-api-client.md`

## Related

- `docs/ig-connectivity-config.md` — validated API connectivity
- `docs/ig-trading-guide.md` — manual curl examples
- `src/cli/lib/ig-instruments.ts` — instrument config
- `playbooks/ig-api-playbook.md` — IG REST API reference
