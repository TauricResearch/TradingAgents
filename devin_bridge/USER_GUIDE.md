# Devin Bridge — User Guide

The Devin bridge lets TradingAgents use an authenticated Devin CLI
installation as its LLM backend, instead of requiring a direct
LLM-provider API key. TradingAgents' own tools, agents, prompts, and
graph remain unchanged; only model inference is routed through Devin.

## One-time setup

```bash
cd TradingAgents
. .venv/bin/activate      # or: conda activate tradingagents
```

Make sure the `devin` CLI is installed and authenticated (`devin` works
from your shell). No OpenAI, Anthropic, or other paid LLM-provider API
keys are required for the LLM.

## See available models

```bash
python -m devin_bridge --list-models
```

## Start the bridge (Terminal 1)

Default — both quick and deep aliases use the model configured/defaulted by
the authenticated Devin CLI (no `--model` flag passed to `devin -p`):

```bash
python -m devin_bridge
```

One explicit model for all aliases:

```bash
python -m devin_bridge --model <model-id>
```

Separate quick / deep models:

```bash
python -m devin_bridge \
  --quick-model <quick-model-id> \
  --deep-model <deep-model-id>
```

The bridge listens on `http://127.0.0.1:8765` by default and prints the
mapped models on startup. Verify with:

```bash
curl -s http://127.0.0.1:8765/healthz
```

## Start TradingAgents (Terminal 2)

```bash
cd TradingAgents
. .venv/bin/activate

export TRADINGAGENTS_LLM_PROVIDER=openai_compatible
export TRADINGAGENTS_LLM_BACKEND_URL=http://127.0.0.1:8765/v1
export TRADINGAGENTS_QUICK_THINK_LLM=devin-quick
export TRADINGAGENTS_DEEP_THINK_LLM=devin-deep
export TRADINGAGENTS_LLM_MAX_RETRIES=0
export TRADINGAGENTS_RESULTS_DIR=/tmp/tradingagents-results
export TRADINGAGENTS_CACHE_DIR=/tmp/tradingagents-cache
export TRADINGAGENTS_MEMORY_LOG_PATH=/tmp/tradingagents-memory/trading_memory.md
export TRADINGAGENTS_CHECKPOINT_ENABLED=true

tradingagents
```

Follow the interactive prompts to pick a ticker, date, and analysts.

## How it works

- TradingAgents chooses `devin-quick` for fast reasoning steps and
  `devin-deep` for deeper reasoning steps (Research Manager, Portfolio
  Manager).
- The bridge maps those aliases to actual Devin models.
- TradingAgents executes its own financial/data tools locally; the bridge
  only translates model responses.
- Data-provider credentials (e.g. `FRED_API_KEY`) are separate from LLM
  credentials and are passed through to TradingAgents tools unchanged.

## Stop

Press `Ctrl+C` in the bridge terminal (Terminal 1). The bridge cleans up
its runtime directory automatically.

## Troubleshooting

**Devin auth missing**: run `devin` once in your shell to authenticate,
then restart the bridge.

**Unavailable model**: run `python -m devin_bridge --list-models` and pick
a model that is listed.

**Port occupied**: stop any previous bridge process, or start with
`--port <other-port>` and update `TRADINGAGENTS_LLM_BACKEND_URL` to match.

**Malformed Devin protocol response**: the bridge logs a sanitized
protocol error (no raw content in normal mode). Restart with `--debug` to
see a bounded raw tail for diagnosis. The bridge does not weaken its
parser — malformed responses are rejected, not silently accepted.

**Missing optional data provider**: `FRED_API_KEY` is optional. If unset,
macro data degrades gracefully and TradingAgents continues. Other data
providers (yfinance, Reddit RSS, Polymarket) are keyless.
