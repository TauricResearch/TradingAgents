#!/usr/bin/env bun
/**
 * IG login — authenticate and show session info.
 */

import { defineCommand } from "citty"
import { IGClient } from "../../lib/ig-client.ts"

function getClient(): IGClient {
  const apiKey = process.env.IG_DEMO_API_KEY
  const username = process.env.IG_DEMO_USERNAME
  const password = process.env.IG_DEMO_PASSWORD
  if (!apiKey || !username || !password) {
    console.error("Missing IG credentials. Set IG_DEMO_API_KEY, IG_DEMO_USERNAME, IG_DEMO_PASSWORD")
    process.exit(1)
  }
  return new IGClient({
    apiKey,
    username,
    password,
    baseUrl: "https://demo-api.ig.com/gateway/deal",
  })
}

export const igLoginCommand = defineCommand({
  meta: { name: "login", description: "Authenticate with IG and show session details" },
  run: async () => {
    const client = getClient()
    const session = await client.login()
    console.log(`Client ID:     ${session.clientId}`)
    console.log(`Account:       ${session.currentAccountId}`)
    console.log(`Dealing:       ${session.dealingEnabled ? "enabled" : "disabled"}`)
    console.log(`Demo accounts: ${session.hasActiveDemoAccounts ? "yes" : "no"}`)
    console.log(`Live accounts: ${session.hasActiveLiveAccounts ? "yes" : "no"}`)
  },
})
