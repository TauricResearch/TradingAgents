/**
 * Central configuration module — single source of truth for all settings.
 *
 * Defaults are loaded from settings.json. Environment variables override defaults.
 * This module is the only place that reads env vars for application configuration;
 * all other files import from here instead.
 *
 * Usage:
 *   import { cfg } from "./settings.ts"
 *   cfg.paths.resultsDir      // "~/.tradingagents/logs" or env override
 *   cfg.isTestMode
 *   cfg.portfolioDb
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

// ── JSON defaults ──────────────────────────────────────────────────────────────

interface SettingsJson {
  paths: {
    resultsDir: string
    positionsDir: string
    postMortemsDir: string
    decisionsDir: string
    hledgerJournal: string
    testHledgerJournal: string
    memoryLog: string
    cacheDir: string
  }
  defaults: {
    benchmarkTicker: string
    dashboardPort: string
    portfolioDb: string
    testPortfolioDb: string
  }
  trading: {
    defaultPlatform: string
    defaultMode: string
    defaultAccountBalance: number
    defaultRiskPerTrade: number
  }
  timeouts: {
    analysisIdleSeconds: number
  }
}

function loadDefaults(): SettingsJson {
  // Resolve relative to this file's directory
  const jsonPath = join(__dirname, "settings.json")
  return JSON.parse(readFileSync(jsonPath, "utf-8")) as SettingsJson
}

const DEFAULTS = loadDefaults()

// ── Env override helpers ───────────────────────────────────────────────────────

function taRoot(): string {
  return process.env.TA_ROOT ?? join(process.env.HOME ?? "", ".tradingagents")
}

function resolvePath(relative: string): string {
  // If it starts with "/" it's absolute; otherwise resolve relative to TA_ROOT
  return relative.startsWith("/") ? relative : join(taRoot(), relative)
}

function optionalStr(env: string | undefined, fallback: string): string {
  return env ?? fallback
}

function optionalNum(env: string | undefined, fallback: number): number {
  return env != null ? parseInt(env, 10) : fallback
}

// ── Public config object ───────────────────────────────────────────────────────

export const cfg = {
  isTestMode: process.env.TEST_MODE === "1",

  paths: {
    resultsDir: resolvePath(
      optionalStr(process.env.TRADINGAGENTS_RESULTS_DIR, DEFAULTS.paths.resultsDir),
    ),
    positionsDir: resolvePath(optionalStr(process.env.POSITIONS_DIR, DEFAULTS.paths.positionsDir)),
    postMortemsDir: resolvePath(
      optionalStr(process.env.POST_MORTEMS_DIR, DEFAULTS.paths.postMortemsDir),
    ),
    decisionsDir: resolvePath(optionalStr(process.env.DECISIONS_DIR, DEFAULTS.paths.decisionsDir)),
    hledgerJournal: optionalStr(
      process.env.HLEDGER_FILE,
      join(process.env.HOME ?? "", DEFAULTS.paths.hledgerJournal),
    ),
    testHledgerJournal: optionalStr(
      process.env.TEST_HLEDGER_FILE,
      join(taRoot(), DEFAULTS.paths.testHledgerJournal),
    ),
    memoryLog: resolvePath(DEFAULTS.paths.memoryLog),
    cacheDir: resolvePath(DEFAULTS.paths.cacheDir),
  },

  hledger: {
    journal:
      process.env.TEST_MODE === "1" && process.env.TEST_HLEDGER_FILE
        ? process.env.TEST_HLEDGER_FILE
        : (process.env.HLEDGER_FILE ?? join(process.env.HOME ?? "", DEFAULTS.paths.hledgerJournal)),
    testJournal: process.env.TEST_HLEDGER_FILE ?? join(taRoot(), DEFAULTS.paths.testHledgerJournal),
  },

  portfolio: {
    db:
      process.env.TEST_MODE === "1"
        ? (process.env.TEST_PORTFOLIO_DB ?? DEFAULTS.defaults.testPortfolioDb)
        : (process.env.PORTFOLIO_DB ?? DEFAULTS.defaults.portfolioDb),
  },

  app: {
    benchmarkTicker: optionalStr(process.env.BENCHMARK, DEFAULTS.defaults.benchmarkTicker),
    dashboardPort: optionalNum(process.env.TA_DASHBOARD_PORT ?? process.env.PORT, 3000),
    openRouterApiKey: process.env.OPENROUTER_API_KEY ?? "",
    hasOpenRouter: !!process.env.OPENROUTER_API_KEY,
  },

  trading: {
    defaultPlatform: DEFAULTS.trading.defaultPlatform,
    defaultMode: DEFAULTS.trading.defaultMode,
    defaultAccountBalance: DEFAULTS.trading.defaultAccountBalance,
    defaultRiskPerTrade: DEFAULTS.trading.defaultRiskPerTrade,
  },

  timeouts: {
    analysisIdleSeconds: DEFAULTS.timeouts.analysisIdleSeconds,
  },
} as const

export type Config = typeof cfg
