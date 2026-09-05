# PR11: Research Report Workspace

PR11 turns an archived research run into a read-only report workspace inside
the local cockpit. The feature is implemented entirely under
`tradingagents/research_platform`; the upstream TradingAgents agent graph is
unchanged.

## Report flow

1. A completed local research job stores an immutable `ResearchReportBundle`.
2. Selecting that run in the cockpit loads a coverage summary and a Markdown
   preview rendered from the archived bundle.
3. The same report is available at
   `/api/reports/<symbol>/<run_id>.md`; adding `?download=1` returns an
   attachment response for a local Markdown export.

The endpoint reads the selected archived bundle, not the mutable current cache.
This preserves the point-in-time evidence, manual decision, risk review, and
backtest that belonged to the original run.

## Coverage summary

The workspace distinguishes three core evidence inputs: normalized market
data, fundamentals, and news. It also reports optional layers when present:
OpenAI narrative output, a manual decision, deterministic risk review, and a
backtest. A missing optional layer is shown as not used, rather than as a data
quality failure.

The report remains research support only. PR11 does not add automated trading,
change risk policy, or make LLM narrative output authoritative.
