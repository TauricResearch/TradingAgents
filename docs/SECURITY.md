# Security

## Secrets

Do not commit API keys, `.env`, tokens, local caches, or generated reports.

## Live Trading

This repo must not include live broker order execution. Broker integrations, if ever scaffolded, must remain mocked, disabled, and clearly marked as future work.

## Local Filings

Files under `data/india/filings/` may contain sensitive research material and are ignored by git.

## Path Safety

Use `safe_india_ticker_component()` before writing ticker-derived paths.

## Vulnerabilities

Report security issues privately to the repository owner. Do not open public issues containing secrets or exploit details.
