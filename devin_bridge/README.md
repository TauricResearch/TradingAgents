# Devin Bridge

An OpenAI-compatible local sidecar that routes TradingAgents LLM inference
through an authenticated [Devin CLI](https://devin.ai) installation.
TradingAgents keeps full control of graph orchestration, agents, prompts,
schemas, and tool execution; the bridge only translates model responses.

## Why

TradingAgents already speaks the OpenAI-compatible protocol. The Devin CLI
provides authenticated access to hosted models (e.g. GLM-5.2 High) without
requiring a direct LLM-provider API key for the LLM. The bridge exposes the
Devin CLI as a local `http://127.0.0.1:8765/v1` endpoint that
TradingAgents can talk to with `provider=openai_compatible`.

Data-provider credentials (FRED, Alpha Vantage, etc.) are separate from LLM
credentials and may still be required depending on the analysts you select.

## Prerequisite

Install and authenticate the Devin CLI:

```bash
devin          # authenticate once
devin -p ...   # verify it works
```

No Python package for `devin` is required — the bridge shells out to the
`devin` executable on your `PATH`.

## See available models

```bash
python -m devin_bridge --list-models
```

## Start the bridge

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

The bridge listens on `http://127.0.0.1:8765` by default. Verify with:

```bash
curl -s http://127.0.0.1:8765/healthz
```

## Configure TradingAgents

```bash
export TRADINGAGENTS_LLM_PROVIDER=openai_compatible
export TRADINGAGENTS_LLM_BACKEND_URL=http://127.0.0.1:8765/v1
export TRADINGAGENTS_QUICK_THINK_LLM=devin-quick
export TRADINGAGENTS_DEEP_THINK_LLM=devin-deep
export TRADINGAGENTS_LLM_MAX_RETRIES=0
```

## Run TradingAgents

```bash
tradingagents
```

TradingAgents chooses `devin-quick` for fast reasoning steps and
`devin-deep` for deeper reasoning steps (Research Manager, Portfolio
Manager). The bridge maps those aliases to actual Devin models.

## Stop

`Ctrl+C` in the bridge terminal. The bridge cleans up its runtime
directory automatically.

## Protocol

The bridge uses a strict bounded-envelope protocol with two response kinds:

- **FINAL** — raw bounded text for natural-language/Markdown assistant
  content. Not JSON-encoded, so newlines, quotes, tables, and braces are
  preserved verbatim.
- **TOOL_CALLS** — strict JSON for tool requests and structured outputs
  (ResearchPlan, TraderProposal, PortfolioDecision, SentimentReport).

The parser is intentionally strict: malformed envelopes are rejected, not
silently accepted. This is the trust boundary between Devin and
TradingAgents.

## Troubleshooting

**Devin auth missing**: run `devin` once to authenticate, then restart the
bridge.

**Unavailable model**: run `python -m devin_bridge --list-models` and pick
a model that is listed.

**Port occupied**: stop any previous bridge process, or start with
`--port <other-port>` and update `TRADINGAGENTS_LLM_BACKEND_URL` to match.

**Malformed protocol response**: the bridge logs a sanitized protocol error
(no raw content in normal mode). Restart with `--debug` to see a bounded
raw tail for diagnosis. The bridge does not weaken its parser — malformed
responses are rejected.

**Missing optional data provider**: `FRED_API_KEY` is optional. If unset,
macro data degrades gracefully and TradingAgents continues. Other data
providers (yfinance, Reddit RSS, Polymarket) are keyless.
