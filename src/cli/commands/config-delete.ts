#!/usr/bin/env bun
import { defineCommand } from "citty"
import { config } from "../../lib/config.ts"

export const configDeleteCommand = defineCommand({
  meta: { name: "delete", description: "Delete a config key" },
  args: {
    key: {
      type: "positional",
      description: "Config key to delete",
      required: true,
    },
  },
  run: ({ args }) => {
    config.delete(args.key)
    config.save()
    console.log(`✓ Deleted ${args.key}`)
  },
})
