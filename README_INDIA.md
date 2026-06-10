# IndiaMarketAgents

IndiaMarketAgents is an India-only institutional market research copilot for Indian listed equities, indices, macro context, filings, and compliance-aware research workflows.

Built as an India-focused fork of TauricResearch/TradingAgents under Apache 2.0.

## What It Does

- Validates India tickers by default: `.NS`, `.BO`, and supported Indian indices.
- Normalizes common bare Indian tickers such as `RELIANCE` to `RELIANCE.NS`.
- Rejects non-India tickers such as `AAPL`, `SPY`, and `BTC-USD` by default.
- Provides India-specialist analyst agents for technicals, fundamentals, news/filings, macro/policy, flows, sentiment, and compliance.
- Saves reports under `reports/<SYMBOL>/<DATE>/`.
- Includes explicit data-quality and compliance disclaimers.

## What It Does Not Do

- It does not provide investment advice.
- It does not place orders.
- It does not connect to Zerodha, Upstox, Angel, Groww, ICICI Direct, or any broker for live trading.
- It does not fabricate unavailable NSE/BSE/FII/DII data.

## Install

```bash
git clone <your-fork-url>
cd IndiaMarketAgents
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
cp .env.example.india .env
```

Add at least one LLM API key to `.env`.

For Ollama, configure the local runtime instead of an API key by adding this to `.env` or exporting it:

```bash
export OLLAMA_BASE_URL=http://localhost:11434/v1
```

## First Run

```bash
indiamarketagents use-case
indiamarketagents doctor --ticker RELIANCE.NS
indiamarketagents sample-report --ticker RELIANCE.NS --date 2026-06-05
indiamarketagents first-run-check --ticker RELIANCE.NS --date 2026-06-05 --provider openai
indiamarketagents analyze --ticker RELIANCE.NS --date 2026-06-05 --research-depth 1 --no-display --no-save-prompt
```

Reports are saved to:

```text
reports/RELIANCE.NS/2026-06-05/
```

For the recommended first workflow and highest-value use case, read `docs/USAGE_PLAYBOOK.md`. For exact credential setup and first-run checks, read `docs/FIRST_RUN_CHECKLIST.md`.

## Pharma, Chemicals, Oil & Gas

Use explicit NSE tickers:

```bash
indiamarketagents analyze --ticker SUNPHARMA.NS --date 2026-06-05
indiamarketagents analyze --ticker SRF.NS --date 2026-06-05
indiamarketagents analyze --ticker ONGC.NS --date 2026-06-05
```

Add local filings under:

```text
data/india/filings/<SYMBOL>/concall/
data/india/filings/<SYMBOL>/results/
data/india/filings/<SYMBOL>/notes/
```

## Dashboard

Install optional dependencies:

```bash
python3 -m pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

## Troubleshooting

- `AAPL rejected`: expected. IndiaMarketAgents is India-only by default.
- `NSE source blocked`: use local files under `data/india/filings/`.
- `API key missing`: add keys to `.env` or export them in your shell.
- `Future date rejected`: analysis date cannot be after today.

## Compliance

This output is for research and education only. It is not investment advice, a recommendation, an offer, or a solicitation to buy or sell securities. IndiaMarketAgents is not a SEBI-registered investment adviser or research analyst. Verify all data with official exchange/company filings and consult a qualified adviser before acting.
