# PR9: Manual Decision Jobs

The local research runner can now receive an explicit manual decision. A
decision is optional; when it is omitted, the job remains a data-and-research
run with no signal, risk review, or backtest.

When a user selects a direction, horizon, confidence, proposed position, and
rationale in the cockpit, the task converts that input to the existing typed
`TradeSignal`. The unchanged workflow then applies deterministic `RiskPolicy`
rules and backtests the risk-approved position before archiving the complete
bundle.

This is a deliberate personal-investor control: the platform never invents a
trade merely because a ticker was researched. Later optional LLM agents may
propose structured signals, but they will enter exactly this same validation,
risk, backtest, report, and archive path.
