import pino from "pino"

// Environment configuration
const isProduction = process.env.NODE_ENV === "production"
const logLevel = process.env.LOG_LEVEL ?? (isProduction ? "info" : "debug")

// Base logger configuration for Bun environment
const logger = pino({
  level: logLevel,
  base: {
    service: "tradingagents-dashboard",
  },
  transport: isProduction
    ? undefined
    : {
        target: "pino-pretty",
        options: {
          colorize: true,
          translateTime: "SYS:standard",
          ignore: "pid,hostname",
        },
      },
  formatters: {
    level: (label) => ({ level: label }),
  },
})

// Factory function for named child loggers
export function createLogger(name: string): pino.Logger {
  return logger.child({ name })
}

export { logger }
