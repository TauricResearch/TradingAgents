# TradingAgents Flint Shadow Setup

This checkout is a separate sibling repo for evaluating TradingAgents as a Flint
shadow-analysis comparator.

## Boundary

- Keep TradingAgents outside Flint's Poetry environment.
- Keep all TradingAgents logs, cache, checkpoints, and memory under this repo's
  `output/` directory.
- Treat TradingAgents output as advisory evidence only. It must not bypass
  Flint's signal gates, profile scope, trace, receipt, or human-review model.
- Do not wire broker or external-write behavior into this checkout for Flint
  shadow runs.

## Paths

- Flint repo: `/Users/sydneymilton/dev/_sandbox/flint`
- TradingAgents shadow repo: `/Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow`
- Local venv: `.venv/`
- Shadow output: `output/`

## Setup

```bash
cd /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow
uv venv .venv
uv pip install -e .
cp flint-shadow.env.example .env.flint-shadow
```

Edit `.env.flint-shadow` for the selected LLM provider and model.

## Run

```bash
cd /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow
.venv/bin/python scripts/flint/run_shadow_analysis.py NVDA 2026-01-15 --checkpoint
```

For a smaller first pass:

```bash
.venv/bin/python scripts/flint/run_shadow_analysis.py NVDA 2026-01-15 --analysts market,news
```

## Flint Integration Shape

```text
Flint SignalLog / SignalReport
  -> TradingAgents shadow run
  -> normalized advisory artifact
  -> Flint evidence attachment / Pensieve scoped memory / GameMaster frame
```

The next useful adapter should normalize:

- ticker
- analysis date
- selected analysts
- final rating
- final decision markdown
- analyst report paths
- debate report paths
- output hashes
- runtime/provider metadata

## Architecture Reference

For the end-to-end C4 pipeline schema, see:

- `docs/flint/TRADINGAGENTS_C4_PIPELINE.md`
- `Architecture/TradingAgentsFlintShadow.yaml`

For local API/worker stack commands and Flint callback/poll contract details,
see:

- `docs/flint/SHADOW_SERVICE_RUNBOOK.md`
