#!/usr/bin/env bun
import { defineCommand } from "citty"
import { config } from "../../lib/config.ts"

export const configPathCommand = defineCommand({
  meta: { name: "path", description: "Show config file path" },
  run: () => {
    console.log(config.getPath())
  },
})
