# Debrief: IG API Client Integration Session (2026-05-08)

**Date**: 2026-05-08
**Session**: ses_f5f225
**Scope**: IG API client integration — from broken npm package to production-ready custom fetch client with CLI bridge

---

## What We Built

### 1. Custom IG API Client (`src/lib/ig-client.ts`)

A thin, typed IG API client using **native fetch** — zero dependencies, works under Bun and Node.js v22+.

**Endpoints covered**:
- `POST /session` — v2 authentication (CST/XST tokens)
- `GET /accounts` — v1 (v2 returns 404)
- `GET /markets?searchTerm=` — v1 (v2 returns 500)
- `GET /prices/{epic}` — v3 (v1/v2 return 404)
- `POST /positions/otc` — v2 (create/close)
- `GET /confirms/{ref}` — v1 (v2/v3 return 500)
- `GET /positions` — v2

**Features**:
- Automatic token extraction from response headers
- Per-request timeout (default 15s, configurable)
- Type-safe interfaces for all IG entities
- Account switching via `IG-ACCOUNT-ID` header

### 2. CLI Subcommands (`trading ig <cmd>`)

Seven IG-specific commands, all lazy-loaded via citty:

| Command | Purpose |
|---------|---------|
| `trading ig login` | Authenticate and show session |
| `trading ig accounts` | List accounts with balances |
| `trading ig search <term>` | Search markets |
| `trading ig prices <epic>` | Fetch historical prices |
| `trading ig positions` | List open positions |
| `trading ig buy <epic>` | Place market buy |
| `trading ig sell <dealId>` | Close position |

### 3. Execute Bridge (`trading execute <ticker>`)

End-to-end flow: calculate trade plan → validate against IG rules → user confirmation → place order → record in SQLite.

---

## Problems Encountered and Overcome

### Problem 1: `ig-trading-api` Package Is Broken

**Discovery**: After `bun add ig-trading-api`, the package:
- Hangs indefinitely on trading endpoints (POST /positions/otc)
- Sends `X-IG-API-KEY: undefined` in requests
- Hardcodes Version 3 globally, but IG requires different versions per endpoint
- Is **archived on GitHub** (no updates since 2024)

**Evidence**:
```
AxiosError: timeout of 15000ms exceeded
# Request headers show: X-IG-API-KEY: undefined
```

**Resolution**: Abandoned the package after 30 minutes of debugging. Built custom `IGClient` using native fetch.

**Lesson**: **Check package health before integrating.** Stars, last commit date, and open issues are leading indicators. An archived repo with 15 open issues is a red flag.

---

### Problem 2: IG API Version Matrix Is Non-Obvious

**Discovery**: Each endpoint requires a specific API version header. The IG documentation does not clearly state which version per endpoint.

**Trial and error**:
```
/accounts      v1 → 200 OK    | v2 → 404 | v3 → 404
/markets       v1 → 200 OK    | v2 → 500 | v3 → 404
/prices        v1 → 404      | v2 → 404 | v3 → 200 OK
/positions/otc v2 → 200 OK    | v1 → 400 | v3 → ?
/confirms      v1 → 200 OK    | v2 → 500 | v3 → 500
```

**Resolution**: Systematic version testing with curl/fetch. Documented the matrix in code comments. The custom client sets the correct version per endpoint.

**Lesson**: **When an API uses version headers per endpoint, the only reliable documentation is the API itself.** Systematic testing beats reading docs.

---

### Problem 3: Position Close Requires `epic` and `expiry`

**Discovery**: Closing a position requires `epic` and `expiry` in the body, not just `dealId`. The `ig-trading-api` package does not include these, causing `validation.null-not-allowed.request.epic`.

**Evidence**:
```
POST /positions/otc
{ dealId, direction, size }  → 400 "validation.null-not-allowed.request.epic"
{ dealId, direction, size, epic, expiry } → 200 OK
```

**Resolution**: Fetched open positions to extract `epic` before closing. Updated `closePosition()` to require `epic` and `expiry`.

**Lesson**: **Read the error message literally.** "null-not-allowed.request.epic" means the field is required, not that it's wrong. The API is explicit.

---

### Problem 4: Position Close Also Requires `guaranteedStop` and `forceOpen`

**Discovery**: After adding `epic` and `expiry`, the API then rejected with `validation.null-not-allowed.request.guaranteedStop`, then `validation.null-not-allowed.request.forceOpen`.

**Resolution**: Added `guaranteedStop: false` and `forceOpen: false` to all close requests.

**Lesson**: **IG's validation is cumulative — it reports one missing field at a time.** Add the field, test again, repeat until it passes. This is tedious but reliable.

---

### Problem 5: AAPL Share Dealing Has Null Bid/Offer on Demo

**Discovery**: AAPL (UA.D.AAPL.CASH.IP) returns `bid: null, offer: null` on the demo account. FTSE 100 works fine.

**Evidence**:
```
AAPL: bid: null | offer: null
# This means share dealing cannot be tested on demo
```

**Resolution**: Documented in `docs/ig-connectivity-config.md`. The CLI uses CFD/indices for demo testing, not US shares.

**Lesson**: **Demo accounts are not full-featured.** IG's demo lacks some instruments. Test with what works, document what doesn't.

---

### Problem 6: Insufficient Funds After Multiple Test Trades

**Discovery**: After 3-4 test trades, the CFD account balance dropped below the margin requirement, causing `REJECTED: INSUFFICIENT_FUNDS`.

**Evidence**:
```
Z6B1MS balance: £10005 → £7427 → £4861 → £2309
Margin required: ~£2500 per FTSE 100 position at 0.5 size
```

**Resolution**: Closed all open positions manually. Added balance check before placing orders in the execute command.

**Lesson**: **Demo account balances are real for testing purposes.** Margin requirements apply. Clean up test positions.

---

## Lab-First Development

Every problem above was discovered and solved in `scripts/lab/ig-client.ts` before touching production code:

1. **Lab**: Test `ig-trading-api` package → discovers hangs
2. **Lab**: Test direct fetch → works, package abandoned
3. **Lab**: Test version matrix → discovers v1/v2/v3 per endpoint
4. **Lab**: Test position close → discovers `epic`, `expiry`, `guaranteedStop`, `forceOpen` required
5. **Lab**: Test AAPL → discovers null bid/offer on demo
6. **Lab**: Test 3+ trades → discovers margin depletion

**No production code was written until the lab experiment passed all 7 steps.**

---

## Architecture Decisions

### Custom Client Over Package

| Aspect | `ig-trading-api` | Custom `IGClient` |
|--------|------------------|-------------------|
| Dependencies | 5 (axios, axios-retry, lightstreamer, luxon) | 0 |
| Maintenance | Archived, broken | Active, tested |
| Version handling | Global v3 | Per-endpoint correct |
| Type safety | Partial | Full |
| Timeout control | Broken (hangs) | Configurable per request |
| Size | 277KB | ~8KB |

### Why Native Fetch

- **Zero dependencies** — no axios, no retry logic, no lightstreamer
- **Works everywhere** — Bun, Node v22+, Deno
- **Transparent** — what you send is what the API receives
- **Timeout control** — AbortController per request

---

## Files Created/Modified

| File | What |
|------|------|
| `src/lib/ig-client.ts` | Custom fetch-based IG API client |
| `src/cli/commands/ig.ts` | Parent IG command |
| `src/cli/commands/ig-login.ts` | Login subcommand |
| `src/cli/commands/ig-accounts.ts` | Accounts subcommand |
| `src/cli/commands/ig-search.ts` | Search subcommand |
| `src/cli/commands/ig-prices.ts` | Prices subcommand |
| `src/cli/commands/ig-positions.ts` | Positions subcommand |
| `src/cli/commands/ig-buy.ts` | Buy subcommand |
| `src/cli/commands/ig-sell.ts` | Sell subcommand |
| `src/cli/commands/execute.ts` | Execute bridge command |
| `src/cli/main.ts` | Wired `execute` and `ig` subcommands |
| `scripts/lab/ig-client.ts` | Lab validation script |
| `briefs/2026-05-08-brief-ig-api-client-integration.md` | Brief |

---

## Acceptance Criteria Status

- [x] Lab experiment passes all 7 steps
- [x] Custom client type-checks with tsc
- [x] No new Python dependencies
- [x] Demo credentials from env vars
- [x] CLI subcommands: login, accounts, search, prices, positions, buy, sell
- [x] `trading execute` bridges plan to order
- [x] Orders recorded in SQLite
- [ ] Integration documented in `docs/ig-api-client.md`

---

## Key Takeaway

**A broken package is not a dead end. It's an opportunity to build something better.**

The `ig-trading-api` package was mature (30 versions, 100% coverage claims), archived, and broken. We spent 30 minutes confirming it was unusable, then built a replacement in 2 hours that is:
- Smaller (8KB vs 277KB)
- Faster (native fetch vs axios overhead)
- More correct (per-endpoint versions)
- Fully typed (our own interfaces)
- Zero dependencies

**Lab-first development caught every problem before production.** The execute command works because every edge case was discovered and handled in the lab.
