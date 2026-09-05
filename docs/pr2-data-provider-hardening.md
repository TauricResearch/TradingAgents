# PR2 Data Provider Hardening

This phase keeps the PR1 research-platform contracts intact and hardens the live data path so local CLI runs fail predictably in desktop or restricted environments.

## Scope

- Configure yfinance's timezone cache before constructing the live ticker factory.
- Allow users to override the yfinance cache directory with `--yfinance-cache-dir` or `TRADINGAGENTS_YFINANCE_CACHE_DIR`.
- Wrap yfinance history, fundamentals, and news failures in `YFinanceDataUnavailableError`.
- Make the CLI return exit code `2` with a concise provider error instead of exposing a traceback for live data failures.

## Validation

Run the focused PR2 suite:

```bash
python -m pytest tests/test_yfinance_provider.py tests/test_cli_report.py -q
```

Run the broader research-platform suite:

```bash
python -m pytest tests/test_research_platform_contracts.py tests/test_legacy_dataflow_provider.py tests/test_yfinance_provider.py tests/test_artifact_store.py tests/test_agent_artifacts.py tests/test_signal_pipeline.py tests/test_backtest_engine.py tests/test_research_report.py tests/test_research_workflow.py tests/test_cli_report.py -q
```
