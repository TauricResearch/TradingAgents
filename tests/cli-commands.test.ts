/**
 * CLI command smoke tests.
 *
 * Spawns the CLI as a subprocess and verifies output.
 * Uses test_portfolio.db (TEST_MODE=1) for database commands.
 */

import { describe, expect, test } from "bun:test"
import { join } from "node:path"

const CLI = join(import.meta.dir, "..", "src", "cli", "main.ts")

async function run(
  args: string[],
  env?: Record<string, string>,
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const proc = Bun.spawn({
    cmd: ["bun", CLI, ...args],
    env: { ...process.env, ...env },
    stdout: "pipe",
    stderr: "pipe",
  })

  let stdout = ""
  let stderr = ""

  const decoder = new TextDecoder()
  for await (const chunk of proc.stdout) stdout += decoder.decode(chunk)
  for await (const chunk of proc.stderr) stderr += decoder.decode(chunk)

  const exitCode = await proc.exited
  return { stdout, stderr, exitCode }
}

describe("trading config", () => {
  const configPath = `${process.env.HOME}/.tradingagents/config.json`

  test("set and get a value", async () => {
    const setResult = await run(["config", "set", "test_key", "test_value"])
    expect(setResult.exitCode).toBe(0)
    expect(setResult.stdout).toContain("test_key")

    const getResult = await run(["config", "get", "test_key"])
    expect(getResult.exitCode).toBe(0)
    expect(getResult.stdout.trim()).toBe("test_value")
  })

  test("get unset key returns error", async () => {
    const result = await run(["config", "get", "nonexistent_key_xyz"])
    expect(result.exitCode).toBe(1)
    expect(result.stdout.trim()).toBe("(not set)")
  })

  test("delete removes a key", async () => {
    await run(["config", "set", "del_me", "123"])
    const delResult = await run(["config", "delete", "del_me"])
    expect(delResult.exitCode).toBe(0)

    const getResult = await run(["config", "get", "del_me"])
    expect(getResult.exitCode).toBe(1)
  })

  test("path shows config file location", async () => {
    const result = await run(["config", "path"])
    expect(result.exitCode).toBe(0)
    expect(result.stdout.trim()).toContain(".tradingagents")
  })
})

describe("trading portfolio", () => {
  test("shows holdings table with headers", async () => {
    const result = await run(["portfolio"])
    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain("PORTFOLIO HOLDINGS")
    expect(result.stdout).toContain("Ticker")
    expect(result.stdout).toContain("TOTAL")
    expect(result.stdout).toContain("NET WORTH")
  })
})

describe("trading watchlist", () => {
  test("shows watchlist or empty message", async () => {
    const result = await run(["watchlist"], { TEST_MODE: "1" })
    expect(result.exitCode).toBe(0)
    const hasHeader = result.stdout.includes("WATCHLIST")
    const hasEmpty = result.stdout.includes("Watchlist is empty")
    expect(hasHeader || hasEmpty).toBe(true)
  })
})

describe("trading signals", () => {
  test("shows signals or empty message", async () => {
    const result = await run(["signals"], { TEST_MODE: "1" })
    expect(result.exitCode).toBe(0)
    const hasHeader = result.stdout.includes("LATEST SIGNALS")
    const hasEmpty = result.stdout.includes("No signals found")
    expect(hasHeader || hasEmpty).toBe(true)
  })
})

describe("trading help", () => {
  test("shows all commands", async () => {
    const result = await run(["help"])
    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain("plan")
    expect(result.stdout).toContain("portfolio")
    expect(result.stdout).toContain("watchlist")
    expect(result.stdout).toContain("signals")
    expect(result.stdout).toContain("trades")
    expect(result.stdout).toContain("prices")
    expect(result.stdout).toContain("config")
    expect(result.stdout).toContain("ig")
    expect(result.stdout).toContain("analyze")
    expect(result.stdout).toContain("completion")
  })
})

describe("trading completion", () => {
  test("generates bash completion", async () => {
    const result = await run(["completion", "bash"])
    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain("bash")
    expect(result.stdout).toContain("_trading_completions")
  })

  test("generates zsh completion", async () => {
    const result = await run(["completion", "zsh"])
    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain("zsh")
    expect(result.stdout).toContain("_trading")
  })

  test("generates fish completion", async () => {
    const result = await run(["completion", "fish"])
    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain("fish")
    expect(result.stdout).toContain("complete -c trading")
  })

  test("errors on unknown shell", async () => {
    const result = await run(["completion", "powershell"])
    expect(result.exitCode).toBe(1)
    expect(result.stderr).toContain("Unknown shell")
  })
})
