#!/usr/bin/env bun
/**
 * IG buy — place a market buy order.
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

export const igBuyCommand = defineCommand({
  meta: { name: "buy", description: "Place a market buy order on IG" },
  args: {
    epic: {
      type: "positional",
      description: "IG EPIC (e.g. IX.D.FTSE.CFD.IP)",
      required: true,
    },
    size: {
      type: "string",
      description: "Order size (e.g. 0.5 for £5/point on FTSE)",
      default: "0.5",
    },
    currency: {
      type: "string",
      description: "Currency code",
      default: "GBP",
    },
    stop: {
      type: "string",
      description: "Stop distance in points (optional)",
    },
    limit: {
      type: "string",
      description: "Limit distance in points (optional)",
    },
  },
  run: async ({ args }) => {
    const client = getClient()
    await client.login()

    const body: Record<string, unknown> = {
      epic: args.epic,
      direction: "BUY",
      size: parseFloat(args.size),
      expiry: "-",
      orderType: "MARKET",
      timeInForce: "EXECUTE_AND_ELIMINATE",
      currencyCode: args.currency,
      forceOpen: true,
      guaranteedStop: false,
    }
    if (args.stop) body.stopDistance = parseFloat(args.stop)
    if (args.limit) body.limitDistance = parseFloat(args.limit)

    console.log(`Placing BUY order: ${args.epic} | size: ${args.size} ${args.currency}`)
    const order = await client.createPosition(body as Parameters<typeof client.createPosition>[0])
    console.log(`Order ref: ${order.dealReference}`)

    const confirmation = await client.confirmTrade(order.dealReference)
    console.log(`Status: ${confirmation.dealStatus}`)
    if (confirmation.dealStatus === "ACCEPTED") {
      console.log(`  Deal ID: ${confirmation.dealId}`)
      console.log(`  Level: ${confirmation.level}`)
      console.log(`  Size: ${confirmation.size}`)
      console.log(`  Direction: ${confirmation.direction}`)
    } else {
      console.log(`  Rejected: ${(confirmation as Record<string, unknown>).reason ?? "unknown"}`)
    }
  },
})
