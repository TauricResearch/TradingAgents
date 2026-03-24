# Analyst Access

This folder adds a separate audit runner for `TradingAgents`.

It uses the same configuration and model setup as the main project, but saves
per-stage artifacts so you can inspect what each analyst received and produced:

- rendered LLM inputs sent to the model
- LLM outputs returned by the model
- tool calls and full tool outputs
- state snapshot before each stage
- final stage report

Important limitation:

- This does **not** expose hidden private chain-of-thought from the model.
- It captures the observable reasoning artifacts available through the app:
  prompts/messages, tool outputs, debate text, and final reports.

## Usage

From the repo root:

```powershell
python -m analyst_access.run --ticker NVDA --date 2026-03-23
```

Optional overrides:

```powershell
python -m analyst_access.run `
  --ticker NVDA `
  --date 2026-03-23 `
  --quick-model gpt-5-mini `
  --deep-model gpt-5.2 `
  --reasoning-effort low `
  --output-dir .\\analyst_access_runs
```

Outputs are written under:

```text
analyst_access_runs/<TICKER>/<DATE>/<timestamp>/
```

Each stage gets its own folder, for example:

- `01_market_analyst`
- `02_social_media_analyst`
- `03_news_analyst`
- `04_fundamentals_analyst`
- `05_bull_researcher`
- `06_bear_researcher`
- `07_research_manager`
- `08_trader`
- `09_aggressive_risk_analyst`
- `10_conservative_risk_analyst`
- `11_neutral_risk_analyst`
- `12_portfolio_manager`

The runner also writes:

- `run_summary.json`
- `processed_signal.txt`

Warnings are added when a tool-backed analyst finishes without gathering enough
external data.
