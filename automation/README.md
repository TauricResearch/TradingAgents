# TradingAgents Automation

Runs scheduled, non-interactive analysis for the configured tickers using the
same Python API shown in the repository README.

## Manual run

Create a local config first:

```powershell
Copy-Item automation\config.json.example automation\config.json
```

Set your OpenAI API key in `.env`:

```text
OPENAI_API_KEY=...
```

```powershell
conda run -n tradingagents python automation\run_scheduled_analysis.py
```

Optional overrides:

```powershell
conda run -n tradingagents python automation\run_scheduled_analysis.py --analysis-date 2026-05-04 --tickers CFISP500.SN
```

Outputs are written to:

```text
reports/scheduled/<analysis-date>/<run-id>/<ticker>/
```

Each ticker folder contains:

- `complete_report.md`
- `complete_report.pdf` with an investment memo cover, executive dashboard,
  operative levels, daily price/risk chart, technical snapshot, and formatted
  analyst sections
- `signal.json`
- section-level markdown files

The run-level `run.log` is written next to the ticker folders.

If yfinance has no OHLCV data for a configured ticker, the runner writes
`skipped.json` for that ticker and does not call the LLM graph. Use
`ticker_aliases` in `automation/config.json` to map a portfolio ticker to a
different data symbol when a working market-data symbol exists.

## Register Windows schedule

```powershell
powershell -ExecutionPolicy Bypass -File automation\register_task.ps1
```

Default schedule: Monday and Thursday at 18:30 using conda env
`tradingagents`.
