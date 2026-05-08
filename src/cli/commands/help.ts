import { defineCommand } from "citty"

export const helpCommand = defineCommand({
  meta: {
    name: "help",
    description: "Show help for trading CLI",
  },
  run() {
    console.log(`trading — TradingAgents CLI

Usage: trading <command> [args]

Commands:
  plan <ticker>      Generate trade plan (shares or spread bet)
  help               Show this message

Examples:
  trading plan AAPL --platform ig --account 50000 --risk 0.02
  trading plan AAPL --platform ig --mode spreadbet --account 50000 --risk 0.02
  trading plan TKA.DE --platform ajbell --account 25000 --risk 0.015
`)
  },
})
