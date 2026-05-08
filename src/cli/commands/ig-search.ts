#!/usr/bin/env bun
/**
 * IG search — find market by name or ticker.
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

export const igSearchCommand = defineCommand({
  meta: { name: "search", description: "Search IG markets by name or ticker" },
  args: {
    query: {
      type: "positional",
      description: "Search term (e.g. FTSE, AAPL, DAX)",
      required: true,
    },
  },
  run: async ({ args }) => {
    const client = getClient()
    await client.login()
    const result = await client.searchMarkets(args.query)
    console.log(`Markets found: ${result.markets.length}`)
    for (const m of result.markets.slice(0, 5)) {
      const bid = m.bid != null ? m.bid.toFixed(1) : "—"
      const offer = m.offer != null ? m.offer.toFixed(1) : "—"
      console.log(
        `  ${m.epic.padEnd(24)} | ${m.instrumentName.slice(0, 30).padEnd(32)} | ${m.instrumentType.padEnd(8)} | ${bid} / ${offer}`,
      )
    }
  },
})
