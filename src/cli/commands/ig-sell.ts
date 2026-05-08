#!/usr/bin/env bun
/**
 * IG sell — close an open position by deal ID.
 */

import { defineCommand } from "citty"
import { IGClient } from "../../lib/ig-client.ts"

function getClient(): IGClient {
  const apiKey = process.env.IG_DEMO_API_KEY
  const username = process.env.IG_DEMO_USERNAME
  const password = process.env.IG_DEMO_PASSWORD
  if (!apiKey || !username || !password) {
    console.error("Missing IG credentials")
    process.exit(1)
  }
  return new IGClient({
    apiKey,
    username,
    password,
    baseUrl: "https://demo-api.ig.com/gateway/deal",
  })
}

export const igSellCommand = defineCommand({
  meta: { name: "sell", description: "Close an open IG position by deal ID" },
  args: {
    dealId: {
      type: "positional",
      description: "Deal ID of the position to close",
      required: true,
    },
  },
  run: async ({ args }) => {
    const client = getClient()
    await client.login()

    // Find the position to get direction and size
    const positions = await client.getPositions()
    const pos = positions.positions.find((p) => p.position.dealId === args.dealId)

    if (!pos) {
      console.error(`Position not found: ${args.dealId}`)
      console.error("Run 'trading ig positions' to see open positions")
      process.exit(1)
    }

    const closeDirection = pos.position.direction === "BUY" ? "SELL" : "BUY"
    console.log(`Closing position: ${args.dealId}`)
    console.log(
      `  ${pos.position.direction} → ${closeDirection} | size: ${pos.position.size} | ${pos.market?.epic ?? "?"}`,
    )

    const order = await client.closePosition({
      dealId: args.dealId,
      direction: closeDirection,
      size: pos.position.size,
      epic: pos.market?.epic ?? "",
      expiry: "-",
      currencyCode: pos.position.currency,
    })
    console.log(`Close ref: ${order.dealReference}`)

    const confirmation = await client.confirmTrade(order.dealReference)
    console.log(`Status: ${confirmation.dealStatus}`)
    if (confirmation.dealStatus === "ACCEPTED") {
      console.log(`  Closed at: ${confirmation.level}`)
      if (confirmation.profit != null) {
        const sign = confirmation.profit >= 0 ? "+" : ""
        console.log(`  P&L: ${sign}${confirmation.profit.toFixed(2)} ${confirmation.currency}`)
      }
    } else {
      console.log(`  Rejected: ${(confirmation as Record<string, unknown>).reason ?? "unknown"}`)
    }
  },
})
