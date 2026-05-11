#!/usr/bin/env bun
/**
 * alerts delete — delete an alert rule by ID.
 *
 * Usage:
 *   trading alerts delete <id>
 */

import { defineCommand } from "citty"
import { DatabaseFactory } from "../../../src/lib/db.ts"
import { deleteAlert, getAlert } from "../../../src/server/lib/alerts-db.ts"
import { cfg } from "../../../src/server/lib/settings.ts"

export const alertsDeleteCommand = defineCommand({
  meta: {
    name: "alerts delete",
    description: "Delete a custom alert rule by ID",
  },
  args: {
    id: {
      type: "positional",
      description: "Alert rule ID",
      required: true,
    },
    "--force": {
      type: "boolean",
      description: "Skip confirmation prompt",
      default: false,
    },
  },
  run: async ({ args }) => {
    const id = parseInt(args.id as string, 10)
    if (Number.isNaN(id)) {
      console.error(`Error: "${args.id}" is not a valid ID.`)
      process.exit(1)
    }

    DatabaseFactory.connect(cfg.portfolio.db)

    const alert = getAlert(id)
    if (!alert) {
      console.error(`Error: no alert rule with ID ${id}.`)
      process.exit(1)
    }

    if (!args["--force"]) {
      console.log(`Delete alert "${alert.name}" (ID ${id})? [y/N]`)
      const input = await new Promise<string>((resolve) => {
        process.stdin.once("data", (chunk) => resolve(chunk.toString().trim()))
        process.stdin.resume()
      })
      process.stdin.pause()
      if (input.toLowerCase() !== "y") {
        console.log("Aborted.")
        return
      }
    }

    const deleted = deleteAlert(id)
    if (deleted) {
      console.log(`Deleted alert #${id}: ${alert.name}`)
    } else {
      console.error(`Error: failed to delete alert #${id}.`)
      process.exit(1)
    }
  },
})
