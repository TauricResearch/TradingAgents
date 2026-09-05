# PR4 Backtest And Risk Enhancements

This phase keeps the original TradingAgents code untouched and extends only the local `research_platform` layer.

## Scope

- Add optional same-day signal execution through `ExecutionConfig.allow_same_day_signal`.
- Add structured `BacktestWarning` records while preserving the existing `warnings: list[str]` field.
- Add FIFO long-position `BacktestRoundTrip` records for closed-trade analysis.
- Add trade-quality metrics: win rate, profit factor, average trade return, average holding days, and max consecutive losses.
- Add `cash_after` and `position_after` to `BacktestTrade` for easier audit trails.
- Add structured `RiskRuleResult`, `RiskSeverity`, and breach recommended actions.
- Add portfolio-level gates for gross exposure and minimum cash preservation.
- Extend report rendering to show richer backtest metrics and risk-rule explanations.

## Non-Goals

- No large rewrite of the upstream TradingAgents runtime.
- No replacement of the existing research workflow, CLI, or report contracts.
- No broker-grade accounting, tax lots, benchmark attribution, or intraday simulation yet.

## Validation

```bash
python -m pytest tests/test_backtest_engine.py tests/test_research_platform_contracts.py tests/test_research_report.py tests/test_research_workflow.py -q
```

```bash
python -m pytest tests/test_research_platform_contracts.py tests/test_legacy_dataflow_provider.py tests/test_yfinance_provider.py tests/test_artifact_store.py tests/test_agent_artifacts.py tests/test_agent_output_format.py tests/test_signal_pipeline.py tests/test_backtest_engine.py tests/test_research_report.py tests/test_research_workflow.py tests/test_cli_report.py -q
```
