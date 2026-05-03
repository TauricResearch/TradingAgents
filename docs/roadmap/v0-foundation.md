# v0 Foundation: Domestic Model and Data Reliability Baseline

## Status

Implemented in this workspace as the first foundation pass.

## Changes

- Removed DeepSeek legacy model aliasing for `deepseek-chat` and `deepseek-reasoner`.
- Kept supported DeepSeek model IDs explicit: `deepseek-v4-flash` and `deepseek-v4-pro`.
- Added Xiaomi MiMo as an Anthropic-compatible provider with:
  - quick default: `mimo-v2.5`
  - deep default: `mimo-v2.5-pro`
  - base URL: `https://token-plan-sgp.xiaomimimo.com/anthropic`
  - env var: `MIMO_API_KEY`
- Defaulted DeepSeek tool-call workflows to non-thinking mode unless callers explicitly override `extra_body`.
- Updated GLM/Z.AI default endpoint to `https://api.z.ai/api/paas/v4/` and added `ZAI_API_KEY` as a preferred env alias before `ZHIPU_API_KEY`.
- Added conservative Tavily configuration keys to the default config and `.env.example`.
- Added `halt_on_missing_data=True` so required market/fundamental data failures raise a clear `DataUnavailableError` instead of silently continuing with empty data.
- Added raw data logging for China data providers under `~/.tradingagents/logs/<TICKER>/<DATE>/data/`.

## Verification

- Unit tests should cover rejected DeepSeek legacy names, new DeepSeek defaults, MiMo catalog defaults, and provider configuration.
- Runtime smoke tests should still be run with real API keys before relying on live trading analysis.
