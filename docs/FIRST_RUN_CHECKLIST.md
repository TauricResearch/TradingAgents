# First Run Checklist

Use this checklist to get from a clean clone to the first usable IndiaMarketAgents research pack.

## 1. Confirm The Right Use Case

Best first use:

- One Indian listed company.
- NSE/BSE ticker, starting with `RELIANCE.NS`.
- Research-pack generation for analyst review.
- Local filings or notes added when available.

Do not use the first run for broker execution, trade placement, investment advice, or real-time monitoring.

## 2. Install And Check The Repo

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m cli.main --help
python3 -m cli.main use-case
python3 -m cli.main doctor --ticker RELIANCE.NS
```

Expected doctor result:

- `ticker_validation` is `RELIANCE.NS`.
- `package_import` is `True`.
- At least one LLM key is present before you run `analyze`.

## 3. Configure Credentials Without Committing Them

Create a local `.env` file:

```bash
cp .env.example.india .env
```

Add exactly one LLM provider key to start:

```text
OPENAI_API_KEY=<your key>
TRADINGAGENTS_LLM_PROVIDER=openai
```

Alternative providers can use the matching key, for example:

```text
GOOGLE_API_KEY=<your key>
TRADINGAGENTS_LLM_PROVIDER=google
```

or:

```text
ANTHROPIC_API_KEY=<your key>
TRADINGAGENTS_LLM_PROVIDER=anthropic
```

Security rules:

- Never commit `.env`.
- Never paste keys into docs, prompts, reports, tests, or screenshots.
- Keep generated reports under ignored `reports/`.
- Keep local filings under ignored `data/india/filings/`.

## 4. Optional Local Inputs

Add notes or converted filing text before the run:

```text
data/india/filings/RELIANCE.NS/notes/
data/india/filings/RELIANCE.NS/concall/
data/india/filings/RELIANCE.NS/results/
data/india/filings/RELIANCE.NS/investor_presentations/
```

Prefer `.md`, `.txt`, or `.csv` for the first run. PDF OCR is not enabled by default.

## 5. Run The First Research Pack

Optional no-key workflow rehearsal:

```bash
python3 -m cli.main sample-report \
  --ticker RELIANCE.NS \
  --date 2026-06-05
```

This writes a saved-report bundle under `reports/RELIANCE.NS/2026-06-05/` with every section marked sample/UNAVAILABLE. Use it to verify report saving and dashboard review before configuring an LLM key. Do not treat it as market research.

Run the offline preflight first:

```bash
python3 -m cli.main first-run-check \
  --ticker RELIANCE.NS \
  --date 2026-06-05 \
  --provider openai
```

This command does not call an LLM or live market data. It should pass ticker/date/report-path checks and fail clearly if the provider key is missing.

Use a shallow run first to control cost:

```bash
python3 -m cli.main analyze \
  --ticker RELIANCE.NS \
  --date 2026-06-05 \
  --research-depth 1 \
  --no-display \
  --no-save-prompt
```

Expected output folder:

```text
reports/RELIANCE.NS/2026-06-05/
```

## 6. Review The Output

Read in this order:

1. `disclaimer.md`
2. `data_quality.json`
3. `sources.md`
4. `complete_report.md`
5. `trader_research_view.md`
6. `9_portfolio_decision.md`

Use the output as a research view only. Verify material claims against official filings, exchange disclosures, and your own notes before relying on them.

## 7. Acceptance Check

The repo is ready for practical use when:

- `doctor` validates `RELIANCE.NS`.
- Non-India tickers such as `AAPL` are rejected by default.
- `sample-report` can generate an explicit sample/UNAVAILABLE saved-report bundle.
- `first-run-check` passes for the selected provider.
- At least one LLM key is detected locally.
- A `reports/RELIANCE.NS/2026-06-05/` bundle is generated.
- The generated `data_quality.json` clearly shows missing or low-confidence sections instead of hiding gaps.

This output is for research and education only. It is not investment advice, a recommendation, an offer, or a solicitation to buy or sell securities. IndiaMarketAgents is not a SEBI-registered investment adviser or research analyst. Verify all data with official exchange/company filings and consult a qualified adviser before acting.
