#!/usr/bin/env bun
/**
 * Lab Experiment: Custom IG API Client (native fetch)
 *
 * Validates our thin IGClient against demo credentials.
 * Steps:
 *   1. Login
 *   2. Account info
 *   3. Market search
 *   4. Price history
 *   5. Place test trade (on appropriate account)
 *   6. Close test trade
 *   7. Error handling
 *
 * Usage:
 *   bun scripts/lab/ig-client.ts
 */

import { IGClient } from "../../src/lib/ig-client.ts"

const API_KEY = process.env.IG_DEMO_API_KEY
const USERNAME = process.env.IG_DEMO_USERNAME
const PASSWORD = process.env.IG_DEMO_PASSWORD

if (!API_KEY || !USERNAME || !PASSWORD) {
  console.error("Missing IG credentials")
  process.exit(1)
}

async function main() {
  console.log("=== IG API Client Lab Experiment ===")
  console.log(`Date: ${new Date().toISOString()}`)
  console.log(`Client: custom IGClient (native fetch, no deps)`)

  const client = new IGClient({
    apiKey: API_KEY,
    username: USERNAME,
    password: PASSWORD,
    baseUrl: "https://demo-api.ig.com/gateway/deal",
  })

  // Step 1: Login
  console.log("\n── Step 1: Login ──")
  const session = await client.login()
  console.log(`  Client ID: ${session.clientId}`)
  console.log(`  Preferred account: ${session.currentAccountId}`)
  console.log(`  Dealing enabled: ${session.dealingEnabled}`)

  // Step 2: Account info
  console.log("\n── Step 2: Account Info ──")
  const accounts = await client.getAccounts()
  let tradeAccountId: string | null = null
  let tradeAccountType: string | null = null
  for (const a of accounts.accounts) {
    console.log(
      `  ${a.accountId} (${a.accountType}): ${a.currency}${a.balance.balance} | avail: ${a.balance.available}`,
    )
    // Use preferred account for trading (IG defaults to it)
    if (a.preferred) {
      tradeAccountId = a.accountId
      tradeAccountType = a.accountType
    }
  }

  if (!tradeAccountId) {
    console.log("  No preferred account found")
    process.exit(1)
  }
  console.log(`  → Trading on preferred account: ${tradeAccountId} (${tradeAccountType})`)
  client.setAccountId(tradeAccountId)

  // Step 3: Market search
  console.log("\n── Step 3: Market Search ──")
  const ftse = await client.searchMarkets("FTSE 100")
  if (ftse.markets.length > 0) {
    const m = ftse.markets[0]
    console.log(`  FTSE 100: ${m.epic} | bid: ${m.bid} | offer: ${m.offer}`)
  }

  const aapl = await client.searchMarkets("AAPL")
  if (aapl.markets.length > 0) {
    const m = aapl.markets[0]
    console.log(`  AAPL: ${m.epic} | bid: ${m.bid} | offer: ${m.offer}`)
  }

  // Step 4: Price history
  console.log("\n── Step 4: Price History ──")
  const prices = await client.getPrices("IX.D.FTSE.CFD.IP", "DAY", 14)
  console.log(`  Fetched ${prices.prices.length} days`)
  if (prices.prices.length > 0) {
    const last = prices.prices[prices.prices.length - 1]
    console.log(`  Latest: ${last.snapshotTime} | close: ${last.closePrice?.bid}`)
  }

  // Step 5: Place test trade (use CFD-compatible expiry for CFD account)
  console.log("\n── Step 5: Place Test Trade ──")
  let dealId: string | null = null
  try {
    const order = await client.createPosition({
      epic: "IX.D.FTSE.CFD.IP",
      direction: "BUY",
      size: 0.5,
      expiry: tradeAccountType === "SPREADBET" ? "DFB" : "-",
      currencyCode: "GBP",
      forceOpen: true,
      guaranteedStop: false,
    })
    console.log(`  Order ref: ${order.dealReference}`)

    // Confirm the deal
    try {
      const confirmation = await client.confirmTrade(order.dealReference)
      console.log(`  Confirmed: dealId=${confirmation.dealId}`)
      console.log(`    Status: ${confirmation.dealStatus}`)
      console.log(`    Level: ${confirmation.level}`)
      if ((confirmation as Record<string, unknown>).reason) {
        console.log(`    Reason: ${(confirmation as Record<string, unknown>).reason}`)
      }
      dealId = confirmation.dealId
    } catch (e) {
      console.log(`  Confirm failed: ${e instanceof Error ? e.message : String(e)}`)
      // Trade may still be open — check positions
    }
  } catch (e) {
    console.log(`  Error placing trade: ${e instanceof Error ? e.message : String(e)}`)
  }

  // Verify by checking positions (in case confirm failed but trade went through)
  if (!dealId) {
    try {
      const positions = await client.getPositions()
      const recent = positions.positions.find((p) => p.position.epic === "IX.D.FTSE.CFD.IP")
      if (recent) {
        console.log(`  Found open position: dealId=${recent.position.dealId}`)
        dealId = recent.position.dealId
      }
    } catch (e) {
      console.log(`  Error checking positions: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  // Step 6: Close test trade
  console.log("\n── Step 6: Close Test Trade ──")
  if (dealId) {
    try {
      const positions = await client.getPositions()
      const pos = positions.positions.find((p) => p.position.dealId === dealId)

      if (pos) {
        const order = await client.closePosition({
          dealId,
          direction: pos.position.direction === "BUY" ? "SELL" : "BUY",
          size: pos.position.size,
          epic: pos.market.epic,
          expiry: tradeAccountType === "SPREADBET" ? "DFB" : "-",
          currencyCode: "GBP",
        })
        console.log(`  Close ref: ${order.dealReference}`)

        try {
          const confirmation = await client.confirmTrade(order.dealReference)
          console.log(`  Confirmed: dealId=${confirmation.dealId}`)
          console.log(`    P&L: ${confirmation.profit} ${confirmation.currency}`)
        } catch (e) {
          console.log(`  Close confirm failed: ${e instanceof Error ? e.message : String(e)}`)
        }
      } else {
        console.log(`  Position ${dealId} not found (already closed?)`)
      }
    } catch (e) {
      console.log(`  Error closing: ${e instanceof Error ? e.message : String(e)}`)
    }
  } else {
    console.log("  No dealId — skipping")
  }

  // Step 7: Error handling
  console.log("\n── Step 7: Error Handling ──")
  try {
    await client.createPosition({ epic: "INVALID.EPIC", direction: "BUY", size: 1 })
    console.log("  Invalid EPIC: UNEXPECTED SUCCESS")
  } catch (e) {
    console.log(`  Invalid EPIC: ${e instanceof Error ? e.message : String(e)}`)
  }

  console.log("\n=== Lab Experiment Complete ===")
  if (dealId) {
    console.log(`✓ Test trade: OPENED (dealId: ${dealId})`)
    console.log(`  (Close status: see Step 6 output above)`)
  } else {
    console.log("⚠ Test trade: NOT PLACED")
  }
}

main().catch((e) => {
  console.error(`Fatal: ${e instanceof Error ? e.message : String(e)}`)
  process.exit(1)
})
