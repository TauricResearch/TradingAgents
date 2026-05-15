import type pino from "pino"
import { logger } from "./logger"

export interface RequestMeta {
  requestId: string
  method?: string
  path?: string
  [key: string]: unknown
}

/**
 * Creates a request-scoped logger that automatically includes requestId
 * in all log entries for tracing.
 */
export function createRequestLogger(
  requestId: string,
  meta?: Record<string, unknown>,
): pino.Logger {
  const baseMeta: RequestMeta = { requestId }
  if (meta) {
    Object.assign(baseMeta, meta)
  }
  return logger.child(baseMeta)
}

export { logger as baseLogger }
