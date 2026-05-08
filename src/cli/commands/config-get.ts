#!/usr/bin/env bun
import { defineCommand } from "citty"
import { config } from "../../lib/config.ts"

export const configGetCommand = defineCommand({
  meta: { name: "get", description: "Get a config value by key" },
  args: {
    key: {
      type: "positional",
      description: "Config key (e.g. account, risk, platform, mode)",
      required: true,
    },
  },
  run: ({ args }) => {
    const val = config.get(args.key, undefined)
    if (val === undefined) {
      console.log(`(not set)`)
      process.exit(1)
    }
    console.log(String(val))
  },
})
