# IG API Client

**Date:** 2026-05-07
**Scope:** `src/lib/ig-client.ts` — native fetch wrapper for IG REST API

---

## Why a Custom Client?

The `ig-trading-api` npm package is **archived** on GitHub and has three critical issues:

1. **axios hangs** on trading endpoints (positions, confirms)
2. **Wrong API versions** hardcoded globally — IG requires per-endpoint version headers
3. **No timeout control** — requests can hang indefinitely

Our native fetch client solves all three with zero dependencies.

---

## Architecture

```
┌─────────────────┐     ┌─────────────┐     ┌──────────────┐
│   IGClient      │────▶│  native     │────▶│  IG REST API │
│  (src/lib/)     │     │  fetch      │     │  (demo/live) │
└─────────────────┘     └─────────────┘     └──────────────┘
        │
        ├── v2  POST /session (auth)
        ├── v1  GET  /accounts
        ├── v1  GET  /markets
        ├── v3  GET  /prices
        ├── v2  POST /positions/otc
        └── v1  GET  /confirms
```

---

## Per-Endpoint Version Matrix

| Endpoint | Version | Notes |
|----------|---------|-------|
| `/session` | v2 | Authentication, CST/XST tokens |
| `/accounts` | v1 | Account list, balances |
| `/markets` | v1 | Market search, EPIC details |
| `/prices` | v3 | Historical price data |
| `/positions/otc` | v2 | Open/close positions |
| `/confirms` | v1 | Deal confirmation |

The `ig-trading-api` package used a **global** version which was fundamentally wrong.

---

## Authentication

```typescript
import { IGClient } from "./src/lib/ig-client.ts"

const client = new IGClient({
  apiKey: process.env.IG_API_KEY!,
  username: process.env.IG_USERNAME!,
  password: process.env.IG_PASSWORD!,
  demo: true,  // demo = true, live = false
})

await client.authenticate()
// client.cst and client.xst now hold session tokens
```

**Token flow:**
1. POST `/session` with `X-IG-API-KEY` header
2. Extract `CST` and `XST` from response headers
3. Include both in all subsequent requests
4. Tokens auto-extend on use (no refresh logic needed)

---

## Examples

### List Accounts

```typescript
const accounts = await client.getAccounts()
// [{ accountId: "Z6B1MS", accountName: "CFD", balance: 10062, ... }]
```

### Search Markets

```typescript
const results = await client.searchMarkets("FTSE")
// [{ epic: "IX.D.FTSE.CFD.IP", instrumentName: "FTSE 100", ... }]
```

### Get Price History

```typescript
const prices = await client.getPrices("IX.D.FTSE.CFD.IP", "DAY", 10)
// { prices: [{ open, high, low, close, volume }, ...] }
```

### Open a Position

```typescript
const deal = await client.createPosition({
  epic: "IX.D.FTSE.CFD.IP",
  direction: "BUY",
  size: 0.5,
  orderType: "MARKET",
  currencyCode: "GBP",
  forceOpen: true,
})
// { dealReference: "ABCDE1", dealId: "12345..." }
```

### Close a Position

```typescript
const deal = await client.closePosition({
  dealId: "12345...",
  direction: "SELL",
  size: 0.5,
  epic: "IX.D.FTSE.CFD.IP",
  expiry: "DFB",
  currencyCode: "GBP",
  guaranteedStop: false,
  forceOpen: false,
})
```

**Important:** IG requires `forceOpen: false` for closes, not a DELETE request.

---

## Error Handling

All methods throw `IGError` on failure:

```typescript
try {
  await client.createPosition({ ... })
} catch (err) {
  if (err instanceof IGError) {
    console.error(err.message)      // human-readable
    console.error(err.statusCode)   // HTTP status
    console.error(err.body)         // raw IG error JSON
  }
}
```

---

## Demo vs Live

| | Demo | Live |
|--|------|------|
| Base URL | `https://demo-api.ig.com` | `https://api.ig.com` |
| Account | Created via IG website | Real money account |
| Instruments | Limited (no US stock spread bets) | Full range |
| Rate limits | Same as live | Same |

**Always test on demo first.** Our demo account:
- CFD: Z6B1MS, £10,062
- Spread Bet: Z6B1MT, £10,000

---

## CLI Integration

The IG client is exposed via `trading ig <command>`:

```bash
trading ig login              # Authenticate
trading ig accounts           # List accounts
trading ig search FTSE        # Search markets
trading ig prices IX.D.FTSE.CFD.IP  # Price history
trading ig positions          # Open positions
trading ig buy IX.D.FTSE.CFD.IP --size 0.5   # Open position
trading ig sell <dealId>     # Close position
```

See `src/cli/commands/ig-*.ts` for implementation.

---

## Testing

Run IG connectivity tests:

```bash
# Unit tests for instrument config
bun test tests/ig-instruments.test.ts

# Live API test (requires credentials)
trading ig login
trading ig accounts
```

---

## References

- IG REST API docs: https://labs.ig.com/site
- Source: `src/lib/ig-client.ts`
- CLI commands: `src/cli/commands/ig*.ts`
- Instrument config: `src/cli/lib/ig-instruments.ts`
