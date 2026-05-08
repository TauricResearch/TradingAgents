/**
 * User configuration store.
 *
 * Reads/writes ~/.tradingagents/config.json
 * CLI defaults (account balance, risk %, platform, mode) live here.
 *
 * Usage:
 *   import { config } from "../lib/config.ts"
 *   const account = config.getNumber("account", 50000)
 *   config.set("platform", "ig")
 *   config.save()
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

const CONFIG_PATH = join(homedir(), ".tradingagents", "config.json")

export class ConfigStore {
  private data: Record<string, unknown>

  constructor() {
    this.data = this.load()
  }

  private load(): Record<string, unknown> {
    if (!existsSync(CONFIG_PATH)) return {}
    try {
      return JSON.parse(readFileSync(CONFIG_PATH, "utf-8"))
    } catch {
      return {}
    }
  }

  save(): void {
    writeFileSync(CONFIG_PATH, `${JSON.stringify(this.data, null, 2)}\n`)
  }

  get<T>(key: string, fallback: T): T {
    const val = this.data[key]
    return val !== undefined ? (val as T) : fallback
  }

  getNumber(key: string, fallback: number): number {
    const val = this.data[key]
    if (val === undefined) return fallback
    const n = typeof val === "string" ? parseFloat(val) : Number(val)
    return Number.isFinite(n) ? n : fallback
  }

  set(key: string, value: unknown): void {
    this.data[key] = value
  }

  delete(key: string): void {
    delete this.data[key]
  }

  list(): Array<{ key: string; value: unknown }> {
    return Object.entries(this.data).map(([key, value]) => ({ key, value }))
  }

  getPath(): string {
    return CONFIG_PATH
  }
}

export const config = new ConfigStore()
