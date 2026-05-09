/**
 * Shared mining utilities for registry tools.
 *
 * Extract project-specific tokens to produce portable, canonical playbooks.
 * Used by reg-mine.ts and reg-promote.ts.
 */

export const REPLACEMENTS: Array<{ pattern: RegExp; replacement: string }> = [
  // Session IDs
  { pattern: /\bses_[0-9a-f]{6,}\b/g, replacement: "<SESSION-ID>" },
  // Project CLI commands: tradingagents <cmd> → <CLI> <cmd>
  {
    pattern:
      /\btradingagents (analyze|plan|portfolio|watchlist|signals|config|sync|backup|summarize|ig)\b/g,
    replacement: "<CLI> $1",
  },
  // Project package directory
  { pattern: /\btradingagents\//g, replacement: "<PACKAGE>/" },
  // Project name
  { pattern: /\bTradingAgents\b/g, replacement: "<PROJECT>" },
  // Source directory hierarchy
  { pattern: /\bsrc\/server\//g, replacement: "<SRC-SERVER>/" },
  { pattern: /\bsrc\/cli\//g, replacement: "<SRC-CLI>/" },
  { pattern: /\bsrc\/lib\//g, replacement: "<SRC-LIB>/" },
  { pattern: /\bsrc\//g, replacement: "<SRC>/" },
  // Project-specific scripts (named ones only)
  { pattern: /\bscripts\/server-lifecycle\.ts\b/g, replacement: "scripts/<SERVICE>.ts" },
  { pattern: /\bscripts\/seed_database\.ts\b/g, replacement: "scripts/<SEED>.ts" },
  { pattern: /\bscripts\/get_price\.ts\b/g, replacement: "scripts/<PRICE>.ts" },
  { pattern: /\bscripts\/trade-calculator\.ts\b/g, replacement: "scripts/<CALC>.ts" },
  { pattern: /\bscripts\/barnacle-scan\.ts\b/g, replacement: "scripts/<SCAN>.ts" },
  // Project-specific env vars
  { pattern: /\bTA_DASHBOARD_PORT\b/g, replacement: "<SERVICE>_PORT" },
  { pattern: /\bTA_([A-Z_]+)\b/g, replacement: "<PREFIX>_$1" },
  // Project data dirs
  { pattern: /\b~\/\.tradingagents\//g, replacement: "~/.<PROJECT>/" },
  // Specific port references (port 3000 is the dashboard port)
  { pattern: /\bport 3000\b/g, replacement: "port <PORT>" },
  // Ticker symbols
  {
    pattern: /\b(AAPL|MSFT|GOOGL|AMZN|TSLA|META|NVDA|BRK\.B|IBM|INTC)\b/g,
    replacement: "<TICKER>",
  },
  // Ticker with exchange suffix
  { pattern: /\b[A-Z]{2,6}\.[A-Z]{1,4}\b/g, replacement: "<TICKER.EXCHANGE>" },
  // Specific dates (YYYY-MM-DD format, 2026 only)
  { pattern: /\b2026-[0-9]{2}-[0-9]{2}\b/g, replacement: "<DATE>" },
  // Ephemeral commit/PR references specific to this project
  { pattern: /\b(td|TD)-[0-9a-f]{6}\b/g, replacement: "<TASK-ID>" },
]

export function sanitize(content: string): string {
  let cleaned = content
  for (const { pattern, replacement } of REPLACEMENTS) {
    cleaned = cleaned.replace(pattern, replacement)
  }
  return cleaned
}
