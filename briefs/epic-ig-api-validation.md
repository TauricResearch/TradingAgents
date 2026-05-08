# Epic: IG API Validation — Test Trading with Real Order Placement

**Date:** 2026-05-07
**Epic ID:** IG-API-001
**Status:** Open
**Priority:** P1
**Platform:** IG (spread betting + share dealing)
**Goal:** Validate trade calculator output against actual IG order parameters

---

## Objective

Set up an IG demo account and use the IG REST API to place test trades. Compare the API's required parameters (margin, stake, stop distance, financing) against our calculator's predictions. Close any gaps.

**Why this matters:**
- Our spread bet calculator uses hardcoded estimates (5% margin, 2.5% overnight rate)
- IG's actual margin requirements vary by instrument (AAPL ≠ BTC ≠ TSLA)
- Stop distances have minimums (e.g., 5% for some stocks)
- Financing rates change with central bank policy
- If our calculator says "margin £1,048" but IG requires "£1,500", the user gets a margin call

---

## IG API Overview

| Endpoint | Purpose |
|----------|---------|
| `POST /session` | Authenticate (obtain CST + XST tokens) |
| `GET /accounts` | List account IDs and balances |
| `GET /markets/{epic}` | Get instrument details (margin, min stop, pip size) |
| `POST /positions/otc` | Place a trade (open position) |
| `POST /workingorders/otc` | Place a working order (limit entry) |
| `POST /positions/otc/{dealId}` | Close a position |
| `GET /history/activity` | Recent trades |

**Authentication:**
- Demo API key (free from IG Labs)
- Username + password + API key
- Returns CST token (session) + XST token (security)

**Rate limits:**
- 60 requests per minute for most endpoints
- Back off on 429 responses

---

## Task Assignments

| Story | Assigned To | Status |
|-------|-------------|--------|
| S01 | **User** | ✅ Done — demo account created |
| S02 | **User** | ✅ Done — connectivity config validated by agent via API calls |
| S03 | **Agent** | ✅ Done — test trades placed (FTSE spread bet opened & closed) |
| S04 | **Agent** | 🔄 Open — calculator validation vs. IG actuals |
| S05 | **Agent** | ✅ Done — order placement guide |

---

## Stories

### IG-API-001-S01: Demo Account Setup

**What:** Register for IG demo account, obtain API credentials.

**Steps:**
1. Visit https://labs.ig.com/gettingstarted
2. Register for a demo account (no real money required)
3. Generate an API key
4. Record credentials securely (`.env` file, not in repo)

**Acceptance:**
- Can authenticate via `POST /session` and receive CST/XST tokens
- Can call `GET /accounts` and see demo balance
- Credentials stored in `.env` as `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`

**Estimate:** 0.5d

---

### IG-API-001-S02: Connectivity Config (User Task)

**Assigned to:** User  
**Status:** 🔄 Open  
**Purpose:** Define the connectivity configuration for the IG REST API.

**What the user needs to provide:**

1. **API Endpoint Confirmation**
   - Demo base URL: `https://demo-api.ig.com/gateway/deal` ✅ (already stored in .env)
   - Confirm this is correct for the user's region (UK)

2. **Authentication Flow**
   - IG uses CST + XST tokens obtained via `POST /session`
   - Tokens expire — define refresh policy (e.g., every 23 hours)
   - Document whether 2FA is required on the demo account

3. **Rate Limits**
   - Confirm actual rate limits for the demo account
   - Define backoff strategy for 429 responses
   - Document which endpoints are most restrictive

4. **Account Selection**
   - Demo accounts may have multiple sub-accounts (spread bet, CFD, share dealing)
   - Document which account type to use for testing

5. **Instrument EPICs**
   - IG uses EPIC codes (e.g., `CS.D.AAPL.CFD.IP` for AAPL CFD)
   - Document how to map our ticker symbols to IG EPICs
   - Provide a mapping table for common tickers: AAPL, TSLA, TKA.DE, etc.

**Acceptance:**
- User provides a `docs/ig-connectivity-config.md` with the above
- Agent can authenticate successfully using provided credentials
- Agent can call `GET /accounts` and receive account list

---

### IG-API-001-S02: Market Data Fetch

**What:** Fetch instrument details for tickers in our `prices` table.

**Endpoint:** `GET /markets/{epic}`

**What we need:**
- `marginFactor` (actual margin % for this instrument)
- `minStopOrProfitDistance` (minimum stop distance in points)
- `slippageFactor` (slippage multiplier)
- `currency` (GBP, USD, EUR)
- `onePipMeans` (what "1 pip" means for this instrument)

**Acceptance:**
- Can fetch market details for AAPL, TSLA, TKA.DE
- `marginFactor` is captured per instrument (not hardcoded 5%)
- Minimum stop distance is known per instrument

**Estimate:** 0.5d

---

### IG-API-001-S03: Test Trade Placement (Agent — ✅ Complete)

**Status:** Complete 2026-05-07

**Results:**

| Instrument | Account | Action | Result | Deal Ref |
|------------|---------|--------|--------|----------|
| FTSE 100 (`IX.D.FTSE.CFD.IP`) | Z6B1MT (Spread Bet) | BUY 0.5 @ MARKET | ✅ ACCEPTED | `7D5B8HS442CTYM9` |
| FTSE 100 (`IX.D.FTSE.CFD.IP`) | Z6B1MT (Spread Bet) | SELL 0.5 @ MARKET | ✅ CLOSED | `HU49G2KZ6SUTYM9` |
| AAPL (`UA.D.AAPL.CASH.IP`) | Z6B1MS (CFD) | BUY 0.01 @ MARKET | ❌ REJECTED | `VRR5ZYKAUECTYM9` |

**Key findings:**
- FTSE spread bet opened at 10362.9, closed at 10363.9, profit £5.00
- AAPL share dealing rejected — `bid`/`offer` are `null` in demo snapshot (likely no live quotes for US 24-hour shares)
- Close endpoint is `POST /positions/otc` with `forceOpen: false` (not DELETE)
- `guaranteedStop` must be explicitly `false` on all requests

**Next:** Use FTSE for spread bet calculator validation; use UK shares (Lloyds, BP) for share dealing tests.

---

### IG-API-001-S04: Calculator Validation (Agent — 🔄 In Progress)

**Status:** In Progress 2026-05-07

**Actual vs Calculator — FTSE 100 Spread Bet:**

| Parameter | Our Calculator | IG Actual | Match? |
|-----------|-------------|-----------|--------|
| Margin factor | 5% (hardcoded) | 5% | ✅ MATCH |
| Min stop distance | Not enforced | 8 points | ⚠️ Need to enforce |
| Min deal size | Not enforced | 0.5 (£5 exposure) | ⚠️ Need to enforce |
| Lot size | Not known | £10 per point | ⚠️ Need to document |

**Actual vs Calculator — AAPL Share Dealing:**

| Parameter | Our Calculator | IG Actual | Match? |
|-----------|-------------|-----------|--------|
| Margin factor | Not set | 20% (tiered) | ⚠️ Need to add |
| Min deal size | Not enforced | 0.01 shares | ⚠️ Need to enforce |
| Min stop distance | Not enforced | 1 point | ⚠️ Need to enforce |

**Acceptance:**
- Per-instrument margin factors captured in `cli/trading/lib/platforms.ts` or external config
- Per-instrument minimum stop distances enforced in calculator
- Calculator updated with actual values where discrepancies exist
- Spread bet output includes note: "Margin is an estimate — verify with IG"

**Estimate:** 0.5d

---

### IG-API-001-S05: Order Placement Guide (Agent — ✅ Complete)

**Status:** Complete 2026-05-07
**Output:** `docs/ig-trading-guide.md`

**Contents:**
- Full trade lifecycle: auth → market data → open → confirm → close → confirm
- Spread bet example (FTSE 100, validated via live test trade: profit £5.00)
- Share dealing example (AAPL, with demo rejection note and workaround)
- Working orders (limit entry) with stop/limit levels
- Stop types: normal, guaranteed, trailing
- Error handling table: 400/401/404/429 with fixes
- TypeScript interfaces for session, order, confirm response

**What:** Document how to reliably place trades with stops and limits via IG.

**Topics:**
- Authentication flow (tokens, expiry, refresh)
- Working order vs. position (limit entry vs. market entry)
- Stop types: guaranteed vs. non-guaranteed (costs extra)
- Limit orders: take-profit levels
- Position sizing: stake per point vs. total exposure
- Currency conversion: when dealing in USD stocks from GBP account

**Output:** `docs/ig-trading-guide.md`

**Estimate:** 0.5d

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Demo account expires | Re-register — takes 10 minutes |
| API rate limits | Cache market details, batch operations |
| Margin changes overnight | Fetch fresh data before each trade |
| IG API v3 deprecation | Use v2 (stable) or migrate when announced |

---

## Dependencies

- IG demo account (free)
- `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD` in `.env`
- `cli/trading/` calculator (already implemented)
- `prices` table with tickers to test

---

## Stretch

- **Automated validation script:** Run daily, fetch IG margin for all tickers in `prices`, alert if any margin > our estimate
- **Live P&L comparison:** Track our calculated P&L vs. IG's reported P&L
- **Order execution latency:** Measure time from API call to position confirmation
