# AGENTS.md

## Project Purpose

`tradingagents-flint-shadow` is a separate sibling repo used to run
`TauricResearch/TradingAgents` as a Flint shadow-analysis comparator.

This repo is not Flint's execution path. It is an advisory sidecar that
produces evidence artifacts Flint can ingest.

## Repository Context

- Flint repo: `/Users/sydneymilton/dev/_sandbox/flint`
- Shadow repo: `/Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow`
- Main shadow runner: `scripts/flint/run_shadow_analysis.py`
- Setup reference: `docs/flint/SHADOW_RUN_SETUP.md`

## Operating Boundary (Hard Rules)

- Do not write into the Flint repo from this repo.
- Do not submit broker orders or wire external execution paths.
- Treat all TradingAgents outputs as advisory artifacts only.
- Keep all TradingAgents state in this repo under `output/`.
- Preserve Flint governance assumptions: traceability, scope, receipts, and
  human review are enforced on the Flint side.

## Environment Conventions

- Use local virtualenv only: `.venv/`
- Create environment:
  - `uv venv .venv`
  - `uv pip install -e .`
- Local shadow env file:
  - template: `flint-shadow.env.example`
  - local file: `.env.flint-shadow` (ignored)

## Required Runtime Paths

The shadow runner must keep these values:

- `results_dir` -> `output/logs`
- `data_cache_dir` -> `output/cache`
- `memory_log_path` -> `output/memory/trading_memory.md`

Do not revert these defaults to `~/.tradingagents` for Flint shadow runs.

## Standard Run Commands

Minimal pass:

```bash
cd /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow
.venv/bin/python scripts/flint/run_shadow_analysis.py NVDA 2026-01-15 --analysts market,news
```

Checkpointed pass:

```bash
cd /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow
.venv/bin/python scripts/flint/run_shadow_analysis.py NVDA 2026-01-15 --checkpoint
```

## Flint Context Contract

When running shadow analysis for Flint, keep these input semantics explicit:

- `ticker`: exact symbol, preserve suffixes (for example, `.T`, `.HK`)
- `trade_date`: analysis date in `YYYY-MM-DD`
- `selected_analysts`: subset of `market,social,news,fundamentals`

Expected output fields for Flint-side normalization:

- ticker
- trade_date
- final rating (parsed decision)
- final decision markdown
- state log directory path
- memory log path
- provider/model metadata used for the run

## Change Scope Guidance

- Keep edits narrow and operational.
- Prefer additive docs/scripts over refactoring upstream TradingAgents internals.
- If changing runtime behavior, update:
  - `scripts/flint/run_shadow_analysis.py`
  - `docs/flint/SHADOW_RUN_SETUP.md`
  - this file (`AGENTS.md`)

## Verification Expectations

For setup or wrapper changes:

- validate CLI entry:
  - `.venv/bin/tradingagents --help`
- validate wrapper entry:
  - `.venv/bin/python scripts/flint/run_shadow_analysis.py --help`
- run targeted tests when available:
  - `.venv/bin/python -m pytest tests/test_signal_processing.py tests/test_structured_agents.py -q`

## Escalation Conditions

Stop and escalate before proceeding if any of these occur:

- request requires writing into Flint repo from this repo
- request requires enabling order execution
- request requires global hook/skill mutation outside repo scope
- unknown provider credentials are required and not present

