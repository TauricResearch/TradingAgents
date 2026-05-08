# IG Order Placement Guide

**Date:** 2026-05-07
**Platform:** IG (Demo API)
**Status:** Validated via live test trades

---

## Overview

This guide documents the validated flow for placing trades via the IG REST API. All examples use the **demo environment** (`demo-api.ig.com`).

**Prerequisites:**
- IG demo account with API key
- Valid CST + XST tokens (see Authentication below)
- Instrument EPIC (see Instrument Mapping)

---

## Authentication

### Step 1: Obtain Session Tokens

**Endpoint:** `POST /session`
**Version:** `2`

```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/session" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 2" \
  -d '{
    "identifier": "TradingAgents",
    "password": "***"
  }'
```

**Response Headers:**
```
CST: <client-session-token>
X-SECURITY-TOKEN: <account-security-token>
```

**Response Body:**
```json
{
  "accountType": "CFD",
  "currentAccountId": "Z6B1MS",
  "accounts": [
    { "accountId": "Z6B1MS", "accountName": "CFD", "accountType": "CFD" },
    { "accountId": "Z6B1MT", "accountName": "Spread bet", "accountType": "SPREADBET" }
  ],
  "dealingEnabled": true
}
```

**Store tokens for subsequent requests.** Tokens are valid for 6 hours and extend to 72 hours while in use.

### Step 2: Include Tokens on Every Request

```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/accounts" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST_TOKEN" \
  -H "X-SECURITY-TOKEN: $XST_TOKEN" \
  -H "Accept: application/json; charset=UTF-8"
```

### Step 3: Account Switching

**Do NOT use `PUT /session`** — it invalidates tokens and causes 401 errors.

**Instead:** Pass `IG-ACCOUNT-ID` header on every request:

```bash
# CFD account
curl ... -H "IG-ACCOUNT-ID: Z6B1MS" ...

# Spread bet account
curl ... -H "IG-ACCOUNT-ID: Z6B1MT" ...
```

---

## Instrument Mapping

| Our Ticker | Instrument | EPIC | Type | Margin | Min Deal |
|------------|-----------|------|------|--------|----------|
| FTSE 100 | FTSE 100 Cash (£10) | `IX.D.FTSE.CFD.IP` | INDICES | 5% | 0.5 |
| AAPL | Apple Inc (24 Hours) | `UA.D.AAPL.CASH.IP` | SHARES | 20% | 0.01 |
| EUR/USD | EUR/USD | `CS.D.EURUSD.CFD.IP` | CURRENCIES | — | — |
| Gold | Spot Gold (£1) | `CS.D.CFPGOLD.CFP.IP` | CURRENCIES | — | — |
| Lloyds | Lloyds Banking Group | `KA.D.LLOY.CASH.IP` | SHARES | — | — |
| BP | BP PLC | `KA.D.BP.CASH.IP` | SHARES | — | — |

**Finding EPICs:**
```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/markets?searchTerm=AAPL" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "Accept: application/json; charset=UTF-8"
```

---

## Market Order (Open Position)

**Endpoint:** `POST /positions/otc`
**Version:** `1`

### Spread Bet Example — FTSE 100

```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/positions/otc" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "IG-ACCOUNT-ID: Z6B1MT" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 1" \
  -d '{
    "epic": "IX.D.FTSE.CFD.IP",
    "expiry": "-",
    "direction": "BUY",
    "size": 0.5,
    "orderType": "MARKET",
    "guaranteedStop": false,
    "forceOpen": true,
    "currencyCode": "GBP"
  }'
```

**Response:**
```json
{ "dealReference": "7D5B8HS442CTYM9" }
```

### Share Dealing Example — AAPL (⚠️ Rejected on Demo)

```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/positions/otc" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "IG-ACCOUNT-ID: Z6B1MS" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 1" \
  -d '{
    "epic": "UA.D.AAPL.CASH.IP",
    "expiry": "-",
    "direction": "BUY",
    "size": 0.01,
    "orderType": "MARKET",
    "guaranteedStop": false,
    "forceOpen": true,
    "currencyCode": "USD"
  }'
```

**Response (demo only):**
```json
{ "dealReference": "VRR5ZYKAUECTYM9" }
```

**Confirm:**
```json
{ "dealStatus": "REJECTED", "reason": "UNKNOWN" }
```

**Why:** AAPL bid/offer are `null` in demo snapshot. Use UK shares (Lloyds, BP) for share dealing tests.

---

## Confirm Deal

**Endpoint:** `GET /confirms/{dealReference}`

```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/confirms/7D5B8HS442CTYM9" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 1"
```

**Response (success):**
```json
{
  "status": "OPEN",
  "dealStatus": "ACCEPTED",
  "dealId": "DIAAAAXEKG8QTA2",
  "level": 10362.9,
  "size": 0.5,
  "direction": "BUY",
  "profit": null
}
```

**Response (rejected):**
```json
{
  "dealStatus": "REJECTED",
  "reason": "UNKNOWN"
}
```

**Always confirm before assuming a trade is open.**

---

## Close Position

**Endpoint:** `POST /positions/otc` — same endpoint as open, opposite direction
**Version:** `1`

**Critical fields:**
- `direction`: opposite of open (`SELL` for a `BUY` position)
- `forceOpen`: `false` (tells IG this is a close, not a new position)
- `guaranteedStop`: `false` (required even for close)
- `timeInForce`: `"EXECUTE_AND_ELIMINATE"` (match and close)

```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/positions/otc" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "IG-ACCOUNT-ID: Z6B1MT" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 1" \
  -d '{
    "epic": "IX.D.FTSE.CFD.IP",
    "expiry": "-",
    "direction": "SELL",
    "size": 0.5,
    "orderType": "MARKET",
    "guaranteedStop": false,
    "forceOpen": false,
    "timeInForce": "EXECUTE_AND_ELIMINATE",
    "currencyCode": "GBP"
  }'
```

**Response:**
```json
{ "dealReference": "HU49G2KZ6SUTYM9" }
```

### Confirm Close

```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/confirms/HU49G2KZ6SUTYM9" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "Accept: application/json; charset=UTF-8"
```

**Response:**
```json
{
  "status": "CLOSED",
  "dealStatus": "ACCEPTED",
  "dealId": "DIAAAAXEKG8QTA2",
  "affectedDeals": [{ "dealId": "DIAAAAXEKG8QTA2", "status": "FULLY_CLOSED" }],
  "level": 10363.9,
  "size": 0.5,
  "direction": "SELL",
  "profit": 5.0,
  "profitCurrency": "GBP"
}
```

**FTSE 100 test trade: opened at 10362.9, closed at 10363.9, profit £5.00.**

---

## Working Order (Limit Entry)

For entering at a specific price (not market price), use a working order.

**Endpoint:** `POST /workingorders/otc`

```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/workingorders/otc" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST" \
  -H "IG-ACCOUNT-ID: Z6B1MT" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 2" \
  -d '{
    "epic": "IX.D.FTSE.CFD.IP",
    "expiry": "-",
    "direction": "BUY",
    "size": 0.5,
    "level": 10350.0,
    "type": "LIMIT",
    "currencyCode": "GBP",
    "stopLevel": 10300.0,
    "limitLevel": 10500.0,
    "timeInForce": "GOOD_TILL_CANCELLED"
  }'
```

**Fields:**
| Field | Description |
|-------|-------------|
| `level` | Entry price (limit level) |
| `type` | `"LIMIT"` or `"STOP"` |
| `stopLevel` | Stop-loss price |
| `limitLevel` | Take-profit price |
| `timeInForce` | `"GOOD_TILL_CANCELLED"` or `"GOOD_TILL_DATE"` |

---

## Stops and Limits

### Stop Types

| Type | Field | Cost | Use When |
|------|-------|------|----------|
| **Normal** | `stopLevel` | Free | Standard risk management |
| **Guaranteed** | `guaranteedStop: true` + `stopLevel` | Extra spread | Must exit at exact price |
| **Trailing** | `trailingStop: true` + `trailingStopDistance` | Free | Lock in profits as price moves |

### Stop Distance Rules

| Instrument | Min Stop Distance | Max Stop Distance |
|------------|-------------------|-------------------|
| FTSE 100 | 8 points | 75% of price |
| AAPL | 1 point | 90% of price |

**Always verify stop distance is ≥ instrument minimum.**

---

## Full Trade Lifecycle

```
1. AUTHENTICATE
   POST /session → CST + XST tokens

2. GET MARKET DATA
   GET /markets/{epic} → margin, min stop, current price

3. PLACE ORDER
   POST /positions/otc → dealReference

4. CONFIRM
   GET /confirms/{dealReference} → dealStatus ACCEPTED/REJECTED

5. MONITOR
   GET /positions → open positions

6. CLOSE
   POST /positions/otc (opposite direction, forceOpen: false)
   → dealReference

7. CONFIRM CLOSE
   GET /confirms/{dealReference} → profit/loss
```

---

## Error Handling

| HTTP | Error Code | Meaning | Fix |
|------|-----------|---------|-----|
| 400 | `validation.null-not-allowed.request.forceOpen` | `forceOpen` missing | Add `"forceOpen": true/false` |
| 400 | `validation.null-not-allowed.request.guaranteedStop` | `guaranteedStop` missing | Add `"guaranteedStop": false` |
| 400 | `validation.null-not-allowed.request` | Multiple fields missing | Check all required fields |
| 401 | `error.security.account-token-invalid` | Tokens expired | Re-authenticate |
| 401 | `error.security.api-key-invalid` | API key wrong | Check `X-IG-API-KEY` |
| 404 | — | EPIC not found | Verify instrument exists on account |
| 429 | — | Rate limit exceeded | Wait 60 seconds |

---

## TypeScript Implementation Notes

```typescript
// Authentication
interface IGSession {
  cst: string;
  xst: string;
  accountId: string;
  accountType: "CFD" | "SPREADBET";
}

// Order request
interface IGOrderRequest {
  epic: string;
  expiry: "-" | string;
  direction: "BUY" | "SELL";
  size: number;
  orderType: "MARKET" | "LIMIT";
  guaranteedStop: boolean;
  forceOpen: boolean;
  currencyCode: string;
  stopLevel?: number;
  limitLevel?: number;
  timeInForce?: "EXECUTE_AND_ELIMINATE" | "GOOD_TILL_CANCELLED";
}

// Confirm response
interface IGConfirmResponse {
  status: "OPEN" | "CLOSED" | null;
  dealStatus: "ACCEPTED" | "REJECTED";
  dealId: string;
  dealReference: string;
  level: number;
  size: number;
  direction: "BUY" | "SELL";
  profit: number | null;
  profitCurrency: string | null;
}
```

---

## References

- `playbooks/ig-api-playbook.md` — Full API endpoint reference
- `docs/ig-connectivity-config.md` — Authentication and account details
- `briefs/epic-ig-api-validation.md` — Epic tracking
