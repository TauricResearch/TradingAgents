#!/usr/bin/env bun
/**
 * IG positions — list open positions.
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

export const igPositionsCommand = defineCommand({
  meta: { name: "positions", description: "List open IG positions" },
  run: async () => {
    const client = getClient()
    await client.login()
    const result = await client.getPositions()
    console.log(`Open positions: ${result.positions.length}`)
    console.log(``)
    console.log(
      `${"Deal ID".padEnd(16)} | ${"EPIC".padEnd(24)} | ${"Dir".padEnd(4)} | ${"Size".padEnd(6)} | ${"Level".padEnd(8)} | ${"P&L".padEnd(10)} | Currency`,
    )
    console.log("—".repeat(90))
    for (const p of result.positions) {
      const pos = p.position
      const m = p.market
      console.log(
        `${pos.dealId.padEnd(16)} | ${(m?.epic ?? "?").padEnd(24)} | ${pos.direction.padEnd(4)} | ${String(pos.size).padEnd(6)} | ${String(pos.level).padEnd(8)} | ${"?".padEnd(10)} | ${pos.currency}`,
      )
    }
  },
})
