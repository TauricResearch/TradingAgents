#!/usr/bin/env bun
/**
 * Batch-generate GitNexus diagrams from config file.
 *
 * Reads .tradingagents/gitnexus-diagrams.json and generates all
 * impact graphs (symbols) and file graphs (files).
 *
 * Usage:
 *   bun scripts/gitnexus-batch.ts              # generate all
 *   bun scripts/gitnexus-batch.ts --render       # also render SVG
 *
 * Config format:
 *   {
 *     "symbols": [{"name": "foo", "depth": 1}, ...],
 *     "files":   ["path/to/file.ts", ...]
 *   }
 */

import { spawn } from "node:child_process"
import { readFile } from "node:fs/promises"
import { join } from "node:path"

const CONFIG_PATH = join(Bun.env.HOME ?? "~", ".tradingagents", "gitnexus-diagrams.json")

interface Config {
  symbols?: Array<{ name: string; depth?: number }>
  files?: string[]
}

async function loadConfig(): Promise<Config> {
  try {
    const text = await readFile(CONFIG_PATH, "utf-8")
    return JSON.parse(text)
  } catch {
    console.error(`Config not found: ${CONFIG_PATH}`)
    return {}
  }
}

async function runGitnexus(args: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    const proc = spawn("bun", ["run", "scripts/gitnexus-to-dot.ts", ...args], {
      stdio: "inherit",
    })
    proc.on("exit", (code) => resolve(code === 0))
  })
}

async function main() {
  const render = Bun.argv.includes("--render") || Bun.argv.includes("-r")
  const config = await loadConfig()
  let count = 0

  if (config.symbols) {
    for (const sym of config.symbols) {
      const depth = sym.depth ?? 1
      const args = ["--symbol", sym.name, "--depth", String(depth)]
      if (render) args.push("--render")

      console.log(`\n→ Generating impact graph: ${sym.name} (depth=${depth})`)
      const ok = await runGitnexus(args)
      if (ok) count++
      else console.error(`  ✗ Failed: ${sym.name}`)
    }
  }

  if (config.files) {
    for (const file of config.files) {
      const args = ["--file", file]
      if (render) args.push("--render")

      console.log(`\n→ Generating file graph: ${file}`)
      const ok = await runGitnexus(args)
      if (ok) count++
      else console.error(`  ✗ Failed: ${file}`)
    }
  }

  console.log(`\nDone. Generated ${count} diagram(s).`)
}

main()
