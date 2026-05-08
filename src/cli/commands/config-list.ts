#!/usr/bin/env bun
import { defineCommand } from "citty"
import { config } from "../../lib/config.ts"

export const configListCommand = defineCommand({
  meta: { name: "list", description: "List all config values" },
  run: () => {
    const entries = config.list()
    if (entries.length === 0) {
      console.log("No config values set.")
      console.log(`Store: ${config.getPath()}`)
      return
    }
    console.log(`Config: ${config.getPath()}`)
    console.log("")
    console.log(`${"Key".padEnd(12)} | Value`)
    console.log("—".repeat(40))
    for (const { key, value } of entries) {
      console.log(`${key.padEnd(12)} | ${value}`)
    }
  },
})
