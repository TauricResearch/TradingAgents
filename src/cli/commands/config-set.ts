#!/usr/bin/env bun
import { defineCommand } from "citty"
import { config } from "../../lib/config.ts"

export const configSetCommand = defineCommand({
  meta: { name: "set", description: "Set a config value by key" },
  args: {
    key: {
      type: "positional",
      description: "Config key (e.g. account, risk, platform, mode)",
      required: true,
    },
    value: {
      type: "positional",
      description: "Value to store",
      required: true,
    },
  },
  run: ({ args }) => {
    const num = parseFloat(args.value)
    config.set(args.key, Number.isFinite(num) ? num : args.value)
    config.save()
    console.log(`✓ Set ${args.key} = ${args.value}`)
  },
})
