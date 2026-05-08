---
date: 2026-05-07
tags: [playbook, ig, api, trading, spreadbet]
---

# IG REST API Playbook

## Purpose

Document the IG REST API authentication, endpoints, and patterns for placing test trades, fetching market data, and validating calculator output against actual IG parameters.

**Reference:** [IG Labs REST Trading API Guide](https://labs.ig.com/rest-trading-api-guide.html)

---

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Demo | `https://demo-api.ig.com/gateway/deal` |
| Live | `https://api.ig.com/gateway/deal` |

**Rule:** This codebase only uses the **demo** endpoint. Live trading is out of scope.

---

## Authentication

### v1/v2 (Header Tokens)

**Endpoint:** `POST /session`

**Request:**
```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/session" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"identifier":"TradingAgents","password":"HermeticZ00!"}'
```

**Response Headers:**
| Header | Purpose | Lifetime |
|--------|---------|----------|
| `CST` | Client session token | 6h initial, extends to 72h with use |
| `X-SECURITY-TOKEN` | Account security token | 6h initial, extends to 72h with use |

**Subsequent requests:**
```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/accounts" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST_TOKEN" \
  -H "X-SECURITY-TOKEN: $XST_TOKEN" \
  -H "Accept: application/json; charset=UTF-8"
```

### v3 (OAuth 2.0)

**Endpoint:** `POST /session`

**Response Body:**
```json
{
  "oauthToken": {
    "access_token": "...",
    "refresh_token": "...",
    "scope": "profile",
    "token_type": "Bearer",
    "expires_in": "60"
  }
}
```

**Subsequent requests:**
```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/accounts" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "IG-ACCOUNT-ID: $ACCOUNT_ID" \
  -H "Accept: application/json; charset=UTF-8"
```

| Token | Lifetime | Refresh |
|-------|----------|---------|
| Access token | 60 seconds | Use refresh token |
| Refresh token | 10 minutes after access expiry | Returns new access + refresh |

**Decision:** Use **v1/v2** for simplicity unless OAuth is explicitly required. v1 tokens auto-extend on use.

---

## Required Headers (All Requests)

| Header | Value | When |
|--------|-------|------|
| `X-IG-API-KEY` | `$IG_DEMO_API_KEY` | Always |
| `CST` | Session token (v1/v2) | After login |
| `X-SECURITY-TOKEN` | Account token (v1/v2) | After login |
| `Authorization` | `Bearer $TOKEN` (v3) | After login |
| `IG-ACCOUNT-ID` | Account ID (v3) | After login |
| `Content-Type` | `application/json` | PUT/POST requests |
| `Accept` | `application/json; charset=UTF-8` | All requests |
| `Version` | API version (e.g., `1`, `2`, `3`) | Optional, defaults to 1 |

---

## Core Endpoints

### Session Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/session` | POST | Authenticate |
| `/session` | DELETE | Logout (invalidate tokens) |
| `/session/refresh-token` | POST | Refresh OAuth token (v3) |

### Account Information

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/accounts` | GET | List accounts and balances |
| `/accounts/{accountId}` | GET | Account details |
| `/accounts/{accountId}/history/transactions` | GET | Transaction history |
| `/accounts/{accountId}/history/activity` | GET | Activity history |

### Market Data

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/markets` | GET | Search markets |
| `/markets/{epic}` | GET | Market details (margin, min stop, currency) |
| `/markets/{epic}/prices` | GET | Historical prices |

### Positions (Open Trades)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/positions` | GET | List open positions |
| `/positions` | POST | Open a new position (OTC) |
| `/positions/otc/{dealId}` | DELETE | Close a position |
| `/positions/sprintmarkets` | GET | Sprint market positions |

### Working Orders (Pending Entry)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/workingorders` | GET | List working orders |
| `/workingorders/otc` | POST | Create working order |
| `/workingorders/otc/{dealId}` | DELETE | Cancel working order |

---

## Placing a Trade

### 1. Open Position (Market Order)

**Endpoint:** `POST /positions`

**Request Body:**
```json
{
  "epic": "CS.D.AAPL.CFD.IP",
  "expiry": "-",
  "direction": "BUY",
  "size": 74.63,
  "orderType": "MARKET",
  "guaranteedStop": false,
  "stopLevel": 267.40,
  "profitLevel": 344.60,
  "currencyCode": "USD"
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `epic` | string | IG instrument identifier |
| `expiry` | string | `"-"` for DFB (daily funded bet), `"DFB"`, or future expiry |
| `direction` | string | `"BUY"` or `"SELL"` |
| `size` | number | Stake per point (spread bet) or share count |
| `orderType` | string | `"MARKET"`, `"LIMIT"`, `"QUOTE"` |
| `guaranteedStop` | boolean | `true` = guaranteed stop (costs extra) |
| `stopLevel` | number | Stop price level |
| `profitLevel` | number | Take profit level |
| `currencyCode` | string | `"USD"`, `"GBP"`, `"EUR"` |

**Response:**
```json
{
  "dealReference": "DIAAAABBB123",
  "dealStatus": "ACCEPTED",
  "direction": "BUY",
  "epic": "CS.D.AAPL.CFD.IP",
  "expiry": "-",
  "level": 280.80,
  "size": 74.63
}
```

### 2. Create Working Order (Limit Entry)

**Endpoint:** `POST /workingorders/otc`

**Request Body:**
```json
{
  "epic": "CS.D.AAPL.CFD.IP",
  "expiry": "-",
  "direction": "BUY",
  "size": 74.63,
  "level": 275.00,
  "type": "LIMIT",
  "currencyCode": "USD",
  "stopLevel": 267.40,
  "profitLevel": 344.60
}
```

### 3. Close Position

**Endpoint:** `DELETE /positions/otc/{dealId}`

**Query Parameters:**
- `dealId` — the deal reference from the open position

---

## Instrument EPICs

IG uses EPIC codes, not ticker symbols. EPICs vary by instrument type (CFD, spread bet, share dealing).

| Our Ticker | Spread Bet EPIC | CFD EPIC | Notes |
|------------|-----------------|----------|-------|
| AAPL | `CS.D.AAPL.CFD.IP` | `CC.D.AAPL.CFD.IP` | US equity, USD denominated |
| TSLA | `CS.D.TSLA.CFD.IP` | `CC.D.TSLA.CFD.IP` | US equity, USD denominated |
| BTC | `CS.D.BTCUSD.CFD.IP` | `CC.D.BTCUSD.CFD.IP` | Crypto, USD denominated |
| EURUSD | `CS.D.EURUSD.CFD.IP` | `CC.D.EURUSD.CFD.IP` | Forex pair |

**Finding EPICs:**
```bash
curl -X GET \
  "https://demo-api.ig.com/gateway/deal/markets?searchTerm=AAPL" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "CST: $CST" \
  -H "X-SECURITY-TOKEN: $XST"
```

---

## Rate Limits

| Account Type | Limit |
|-------------|-------|
| Demo | 60 requests/minute |
| Live | Varies by subscription |

**Back off on:**
- `429 Too Many Requests` — wait 60 seconds
- `401 Unauthorized` — tokens expired, re-authenticate

---

## Error Handling

| Status | Meaning | Action |
|--------|---------|--------|
| `200` | Success | — |
| `400` | Bad Request | Check JSON format, required fields |
| `401` | Unauthorized | Re-authenticate (tokens expired) |
| `404` | Not Found | Check EPIC, deal ID |
| `429` | Too Many Requests | Back off, retry after 60s |
| `500` | Server Error | Retry or contact IG support |

**Error Response Body:**
```json
{ "errorCode": "error.security.invalid-details" }
```

---

## Environment Variables

Stored in `.env` (not committed):

```bash
IG_DEMO_API_KEY=your-api-key
IG_DEMO_USERNAME=TradingAgents
IG_DEMO_PASSWORD=your-password
IG_DEMO_BASE_URL=https://demo-api.ig.com/gateway/deal
```

**Never** commit credentials. Use `skate` or `.env` only.

---

## Quick Reference

| Task | Command |
|------|---------|
| Authenticate | `POST /session` |
| List accounts | `GET /accounts` |
| Get market details | `GET /markets/{epic}` |
| Open position | `POST /positions` |
| Close position | `DELETE /positions/otc/{dealId}` |
| List open positions | `GET /positions` |
| Create working order | `POST /workingorders/otc` |
| Cancel working order | `DELETE /workingorders/otc/{dealId}` |

---

## Testing Checklist

- [ ] Can authenticate and receive CST/XST tokens
- [ ] Can list accounts and see demo balance
- [ ] Can fetch market details for AAPL EPIC
- [ ] Can place test position and receive deal reference
- [ ] Can close test position using deal reference
- [ ] Actual margin matches or exceeds calculator estimate
- [ ] Actual stop distance is ≥ calculator stop distance
- [ ] Rate limit observed (≤ 60 requests/minute)

---

## References

- [IG Labs REST API Guide](https://labs.ig.com/rest-trading-api-guide.html)
- [IG API Reference](https://labs.ig.com/reference/)
- `briefs/epic-ig-api-validation.md` — this project's IG integration epic
