#!/usr/bin/env bun
/**
 * Data management subcommands — export, import.
 *
 * Usage:
 *   trading data export <json|csv> [-o path]
 *   trading data import <file.csv>
 */

import { defineCommand } from "citty"

export const dataCommand = defineCommand({
  meta: {
    name: "data",
    description: "Portfolio data management — export and import",
  },
  subCommands: {
    export: () => import("./data-export.ts").then((m) => m.dataExportCommand),
    import: () => import("./data-import.ts").then((m) => m.dataImportCommand),
  },
})
