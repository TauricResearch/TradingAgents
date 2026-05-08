import { defineCommand } from "citty"

export const helpCommand = defineCommand({
  meta: {
    name: "help",
    description: "Show help for trading CLI",
  },
  run() {
    console.log(`trading — TradingAgents CLI

Usage: trading <command> [args]

Core:
  plan <ticker>              Generate trade plan (shares or spread bet)
  execute <ticker>           Calculate plan and execute via IG API
  portfolio                  Show holdings, P&L, and cash summary
  config <get|set|list|...>  Manage CLI defaults

IG Trading:
  ig login                   Authenticate with IG
  ig accounts                List IG accounts
  ig search <term>           Search markets
  ig prices <epic>           Fetch historical prices
  ig positions               List open positions
  ig buy <epic>              Place market buy order
  ig sell <dealId>           Close position

Data & Operations:
  analyze <ticker>           Run TradingAgents LLM analysis
  seed [--positions]         Seed database with test data
  sync prices [ticker]       Sync Yahoo Finance prices
  backup [--test]            Backup SQLite database
  summarize [ticker]         LLM summary of analyses

Examples:
  trading plan AAPL
  trading plan AAPL --mode spreadbet --risk 0.03
  trading execute AAPL
  trading ig search FTSE
  trading ig buy IX.D.FTSE.CFD.IP --size 0.5
  trading config set account 75000
  trading config set risk 0.02
`)
  },
})
