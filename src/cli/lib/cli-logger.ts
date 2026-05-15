/**
 * CLI-specific logger wrapper.
 *
 * Uses the centralized logger from @lib/logger with CLI-specific
 * context and output handling.
 *
 * Log level is controlled by LOG_LEVEL env var or --quiet/--verbose flags.
 * Default: info. --quiet sets error only. --verbose sets debug.
 *
 * Usage:
 *   import { cliLogger, setLogLevel } from "../lib/cli-logger"
 *   setLogLevel("verbose")
 *   cliLogger.info("Analysis started", { ticker: "AAPL" })
 */

import { createLogger } from "@lib/logger"

// Dynamic log level state
let _currentLevel: "quiet" | "verbose" | undefined

/**
 * Set the CLI log level based on --quiet or --verbose flags.
 * Must be called before using cliLogger if overriding defaults.
 */
export function setLogLevel(level: "quiet" | "verbose" | undefined): void {
  _currentLevel = level
}

// Internal logger with "cli" name context
const _logger = createLogger("cli")

// Level priority: quiet > verbose > default
function shouldLog(method: "trace" | "debug" | "info" | "warn" | "error" | "fatal"): boolean {
  if (_currentLevel === "quiet" && method !== "error" && method !== "fatal") {
    return false
  }
  if (_currentLevel === "verbose" && method === "trace") {
    return false
  }
  // Default: trace and debug are off, info/warn/error/fatal are on
  if (method === "trace" || method === "debug") {
    return _currentLevel === "verbose"
  }
  return true
}

// Convenience methods for common CLI scenarios
export const cliLogger = {
  trace: (msg: string, meta?: Record<string, unknown>) => {
    if (shouldLog("trace")) _logger.trace(meta ?? {}, msg)
  },
  debug: (msg: string, meta?: Record<string, unknown>) => {
    if (shouldLog("debug")) _logger.debug(meta ?? {}, msg)
  },
  info: (msg: string, meta?: Record<string, unknown>) => {
    if (shouldLog("info")) _logger.info(meta ?? {}, msg)
  },
  warn: (msg: string, meta?: Record<string, unknown>) => {
    if (shouldLog("warn")) _logger.warn(meta ?? {}, msg)
  },
  error: (msg: string, meta?: Record<string, unknown>) => {
    if (shouldLog("error")) _logger.error(meta ?? {}, msg)
  },
  fatal: (msg: string, meta?: Record<string, unknown>) => {
    if (shouldLog("fatal")) _logger.fatal(meta ?? {}, msg)
  },

  // For errors with an Error object
  errorWithCause: (msg: string, err: unknown, meta?: Record<string, unknown>) => {
    if (shouldLog("error")) {
      const errorMeta = {
        ...meta,
        err: err instanceof Error ? { message: err.message, stack: err.stack } : String(err),
      }
      _logger.error(errorMeta, msg)
    }
  },
}
