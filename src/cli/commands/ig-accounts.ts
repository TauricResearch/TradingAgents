#!/usr/bin/env bun
/**
 * IG accounts — list all accounts with balances.
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

export const igAccountsCommand = defineCommand({
  meta: { name: "accounts", description: "List IG accounts with balances" },
  run: async () => {
    const client = getClient()
    await client.login()
    const accounts = await client.getAccounts()
    console.log(`Accounts: ${accounts.accounts.length}`)
    for (const a of accounts.accounts) {
      const pref = a.preferred ? "★" : " "
      console.log(
        `  ${pref} ${a.accountId} | ${a.accountType.padEnd(10)} | ${a.currency}${a.balance.balance.toFixed(2)} | avail: ${a.balance.available.toFixed(2)}`,
      )
    }
  },
})
