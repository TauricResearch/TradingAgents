#!/usr/bin/env bun
/**
 * IG prices — fetch historical prices for an EPIC.
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

export const igPricesCommand = defineCommand({
  meta: { name: "prices", description: "Fetch historical prices for an IG EPIC" },
  args: {
    epic: {
      type: "positional",
      description: "IG EPIC (e.g. IX.D.FTSE.CFD.IP)",
      required: true,
    },
    resolution: {
      type: "string",
      description: "DAY, HOUR, MINUTE_5, etc.",
      default: "DAY",
    },
    count: {
      type: "string",
      description: "Number of data points",
      default: "14",
    },
  },
  run: async ({ args }) => {
    const client = getClient()
    await client.login()
    const result = await client.getPrices(args.epic, args.resolution, parseInt(args.count, 10))
    console.log(`Prices for ${args.epic}: ${result.prices.length} ${args.resolution} bars`)
    console.log(``)
    console.log(
      `${"Date".padEnd(20)} | ${"Open".padEnd(8)} | ${"High".padEnd(8)} | ${"Low".padEnd(8)} | ${"Close".padEnd(8)} | Volume`,
    )
    console.log("—".repeat(70))
    for (const p of result.prices) {
      const open = p.openPrice?.bid?.toFixed(1) ?? "—"
      const high = p.highPrice?.bid?.toFixed(1) ?? "—"
      const low = p.lowPrice?.bid?.toFixed(1) ?? "—"
      const close = p.closePrice?.bid?.toFixed(1) ?? "—"
      console.log(
        `${p.snapshotTime.padEnd(20)} | ${open.padEnd(8)} | ${high.padEnd(8)} | ${low.padEnd(8)} | ${close.padEnd(8)} | ${p.lastTradedVolume}`,
      )
    }
  },
})
