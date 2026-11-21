# Member D — recording rules

## What this folder holds
One file per analysis interaction, named `YYYY-MM-DD_HH-MM-SS.md` using the timestamp of the first message, `Asia/Hong_Kong`. Each file opens with a short English summary, then the record. Originals may stay in any language.

## What a measurement record must contain
1. **Frozen configuration** — provider, model pair, analyst set, debate and risk rounds, data vendors, ticker, analysis date. A measurement is only comparable to another when every one of these matches.
2. **Command used** — the exact CLI invocation or script path, so the row can be reproduced.
3. **Per-run figures** — wall-clock seconds, `tokens_in`, `tokens_out`, LLM call count, final rating, run status, and any data gaps observed.
4. **Measurement source** — state whether the figure came from `StatsCallbackHandler.get_stats()`, the CLI panel, or a provider dashboard. The CLI's live panel undercounts, so the panel is never acceptable on its own.
5. **Anomalies** — throttling, retries, missing vendor keys, or a run that ended early. A failed run is a row, not a deletion.

## Rules
- No secrets: no API keys, no `.env` contents, no endpoint URLs carrying credentials, no portfolio or personal data.
- Never edit a previous record to make it match a later result; append a correction with its own timestamp.
- Raw artefacts (report folders, state logs) stay outside the repo; record only their paths and the numbers.
- Runs are executed one after another, never in parallel.
- Report latency and token figures over `COMPLETE` runs only, and publish the count of excluded runs beside the average.
