# Agent Artifacts

The research platform should treat LLM output as validated artifacts, not as
free text that downstream systems must parse forever.

## Renderers

`tradingagents.research_platform.agent_artifacts` renders the core agent
contracts into deterministic markdown:

- `render_analyst_note(note)`
- `render_investment_thesis(thesis)`
- `render_trade_signal(signal)`

These renderers are for reports and cockpit display. The structured Pydantic
objects remain the source of truth for backtests and risk.

## Legacy Adapters

The same module also includes bridge functions for the current TradingAgents
graph:

- `analyst_note_from_legacy_report(...)`
- `investment_thesis_from_legacy_plan(...)`
- `trade_signal_from_legacy_decision(...)`

The most important bridge is `trade_signal_from_legacy_decision`. It parses the
existing Portfolio Manager markdown, maps the 5-tier rating into a 3-way
`TradeDirection`, and extracts obvious percentage fields such as position size,
expected return, and stop loss.

This is intentionally conservative. If legacy prose does not expose a clean
field, the adapter leaves that value empty instead of inventing one.

## Rating Mapping

| Legacy rating | Trade direction |
| --- | --- |
| Buy | buy |
| Overweight | buy |
| Hold | hold |
| Underweight | sell |
| Sell | sell |

## Next Step

The next migration slice should connect these artifacts to risk and backtesting:

1. Convert legacy final decisions to `TradeSignal`.
2. Send `TradeSignal` through deterministic risk review.
3. Feed approved signals into the backtest engine.
4. Keep the rendered markdown as the user-facing explanation.
