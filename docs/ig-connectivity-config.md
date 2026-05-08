# IG Connectivity Configuration

**Date:** 2026-05-07
**Environment:** Demo (`https://demo-api.ig.com/gateway/deal`)
**Status:** Validated via live API calls — test trades executed

---

## Authentication

### Method: v2 Header Tokens

**Endpoint:** `POST /session`

**Confirmed working:** 2026-05-07 via curl

**Request:**
```bash
curl -X POST \
  "https://demo-api.ig.com/gateway/deal/session" \
  -H "X-IG-API-KEY: $IG_DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; charset=UTF-8" \
  -H "Version: 2" \
  -d '{"identifier":"TradingAgents","password":"***"}'
```

**Response Headers (v2):**
| Header | Value | Lifetime |
|--------|-------|----------|
| `CST` | Client session token | 6h initial, extends to 72h with use |
| `X-SECURITY-TOKEN` | Account security token | 6h initial, extends to 72h with use |

**Response Body:**
```json
{
  "accountType": "CFD",
  "accountInfo": {
    "balance": 10000.0,
    "deposit": 0.0,
    "profitLoss": 0.0,
    "available": 10000.0
  },
  "currencyIsoCode": "GBP",
  "currencySymbol": "£",
  "currentAccountId": "Z6B1MS",
  "accounts": [
    { "accountId": "Z6B1MS", "accountName": "CFD", "accountType": "CFD", "preferred": true },
    { "accountId": "Z6B1MT", "accountName": "Spread bet", "accountType": "SPREADBET", "preferred": false }
  ],
  "clientId": "104689490",
  "hasActiveDemoAccounts": true,
  "hasActiveLiveAccounts": true,
  "dealingEnabled": true
}
```

**Decision:** Use v2. v3 OAuth tokens expire in 60 seconds and require refresh logic. v2 tokens auto-extend on use and are simpler for our use case.

---

## Accounts

| Account ID | Name | Type | Preferred | Balance | Currency |
|------------|------|------|-----------|---------|----------|
| `Z6B1MS` | CFD | CFD | ✅ Yes | £10,000 | GBP |
| `Z6B1MT` | Spread bet | SPREADBET | No | £10,000 | GBP |

**Note:** No separate "share dealing" account type. Share dealing instruments are available within both CFD and Spread bet accounts as `SHARES` type instruments.

**Account switching:** Pass `IG-ACCOUNT-ID: {accountId}` header on all requests after login to switch context.

---

## Rate Limits

| Limit | Value | Source |
|-------|-------|--------|
| Demo requests | ~60/minute | Observed in IG docs |
| Token lifetime | 6h → 72h | Session response headers |

**Backoff strategy:**
- `429 Too Many Requests` → wait 60 seconds, retry
- `401 Unauthorized` → re-authenticate (tokens expired)

---

## Instrument Mapping (Validated)

### FTSE 100 (Spread Bet — ✅ Tested)

| Field | Value |
|-------|-------|
| EPIC | `IX.D.FTSE.CFD.IP` |
| Type | INDICES |
| Name | FTSE 100 Cash (£10) |
| Lot Size | 10.0 (£10 per point) |
| Margin | 5% |
| Min Deal Size | 0.5 (£5 min exposure) |
| Min Stop Distance | 8 points |
| Max Stop Distance | 75% of price |
| Currency | GBP |

**Test Trade Result:**
- Opened: BUY 0.5 at 10362.9
- Closed: SELL 0.5 at 10363.9
- Profit: £5.00 GBP
- Status: FULLY_CLOSED ✅

### Apple Inc — AAPL (Share Dealing — ⚠️ Tradeable but rejected on demo)

| Field | Value |
|-------|-------|
| EPIC | `UA.D.AAPL.CASH.IP` |
| Type | SHARES |
| Name | Apple Inc (24 Hours) |
| Lot Size | 0.01 (0.01 shares min) |
| Margin | 20% (tiered: 20% up to $7,500) |
| Min Deal Size | 1.0 |
| Min Stop Distance | 1 point |
| Max Stop Distance | 90% of price |
| Currency | USD |
| Bid/Offer | `null` in snapshot (delayed quote issue) |

**Test Trade Result:**
- Submitted: BUY 0.01 at MARKET
- Status: REJECTED ❌ (reason: UNKNOWN)
- Likely cause: null bid/offer in snapshot — IG demo may not provide live quotes for US 24-hour shares

### Other Discovered Instruments

| Instrument | EPIC | Type | Available |
|------------|------|------|-----------|
| EUR/USD | `CS.D.EURUSD.CFD.IP` | CURRENCIES | ✅ Yes |
| Spot Gold | `CS.D.CFPGOLD.CFP.IP` | CURRENCIES | ✅ Yes |
| Oil — US Crude | `CC.D.CL.UNC.IP` | COMMODITIES | ✅ Yes |
| Lloyds Banking | `KA.D.LLOY.CASH.IP` | SHARES | ✅ Yes |
| BP PLC | `KA.D.BP.CASH.IP` | SHARES | ✅ Yes |

---

## Order Placement (Validated)

### Open Position (Market Order)

**Endpoint:** `POST /positions/otc`

**Required Body Fields:**
```json
{
  "epic": "IX.D.FTSE.CFD.IP",
  "expiry": "-",
  "direction": "BUY",
  "size": 0.5,
  "orderType": "MARKET",
  "guaranteedStop": false,
  "forceOpen": true,
  "currencyCode": "GBP"
}
```

**Response:** `{ "dealReference": "7D5B8HS442CTYM9" }`

### Confirm Deal

**Endpoint:** `GET /confirms/{dealReference}`

**Response:**
```json
{
  "status": "OPEN",
  "dealStatus": "ACCEPTED",
  "dealId": "DIAAAAXEKG8QTA2",
  "level": 10362.9,
  "size": 0.5,
  "direction": "BUY"
}
```

### Close Position

**Endpoint:** `POST /positions/otc` (not DELETE — use opposite direction)

**Required Body Fields:**
```json
{
  "epic": "IX.D.FTSE.CFD.IP",
  "expiry": "-",
  "direction": "SELL",
  "size": 0.5,
  "orderType": "MARKET",
  "guaranteedStop": false,
  "forceOpen": false,
  "timeInForce": "EXECUTE_AND_ELIMINATE",
  "currencyCode": "GBP"
}
```

**Critical:** `forceOpen` must be `false` for close, `true` for open. `guaranteedStop` must be explicitly `false`.

**Response:** `{ "dealReference": "HU49G2KZ6SUTYM9" }`

---

## Platform Strategy (Updated)

| Platform | Priority | Instrument | Account | EPIC | Test Result |
|----------|----------|-----------|---------|------|-------------|
| **Spread Bet** | P1 | FTSE 100 | Z6B1MT | `IX.D.FTSE.CFD.IP` | ✅ Opened & closed with profit |
| **Share Dealing** | P2 | AAPL | Z6B1MS | `UA.D.AAPL.CASH.IP` | ⚠️ Rejected (null bid/offer) |
| **Share Dealing** | P2 | Lloyds/BP | Z6B1MS | `KA.D.LLOY.CASH.IP` | ⏳ Not yet tested |
| **CFD** | P3 | User unfamiliar | Z6B1MS | — | ⏳ Not yet tested |

---

## Known Limitations

1. **AAPL share dealing rejected on demo:** The `bid`/`offer` fields are `null` in the market snapshot. IG demo accounts may not provide live quotes for US 24-hour shares. Workaround: use UK shares (Lloyds, BP) or indices (FTSE) for testing.

2. **US stock spread bets not found:** No spread bet or CFD EPICs discovered for AAPL, TSLA, or other US stocks on this demo account. The demo account's spread bet sub-account may only have indices, forex, and commodities.

3. **Account switching invalidates tokens:** `PUT /session` to switch accounts causes subsequent requests to fail with 401. Solution: pass `IG-ACCOUNT-ID` header on each request instead of switching.

---

## Test Commands

```bash
# Authenticate
bash /tmp/ig-auth.sh

# List accounts
bash /tmp/ig-accounts.sh

# Search markets
bash /tmp/ig-search.sh

# Place test trade (spread bet)
bash /tmp/ig-trade-ftse-v4.sh

# Confirm deal
bash /tmp/ig-trade-confirm.sh

# Close position
bash /tmp/ig-trade-close-v5.sh
```

---

## References

- `playbooks/ig-api-playbook.md` — Full API reference
- `briefs/epic-ig-api-validation.md` — Integration epic
- `docs/ig-trading-guide.md` — Order placement guide (S05)
