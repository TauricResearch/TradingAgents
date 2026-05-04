# Scripts

## TypeScript (`*.ts` — Bun native)

Run with `bun scripts/<name>.ts` or via `just <recipe>`.

| Script | Purpose | Dependencies |
|--------|---------|-------------|
| `seed_database.ts` | Seed SQLite + exit plans + post-mortems | `bun:sqlite`, `js-yaml` |
| `summarize_analyses.ts` | LLM summarisation via OpenRouter | none (fetch) |
| `get_price.ts` | Yahoo Finance price + history | none (fetch) |
| `portfolio-intel.ts` | Portfolio summary via HTTP | none (fetch) |
| `render_diagrams.ts` | DOT/MMD → SVG (graphviz + mmdc) | `dot`, `mmdc` |
| `extract_mermaid.ts` | Strip YAML front matter from MMD | none |

## Python (`py/*.py` — tradingagents dependency)

Run with `python scripts/py/<name>.py` or via `just <recipe>`.
These require the `tradingagents` Python package (`.venv`).

| Script | Purpose |
|--------|---------|
| `analyze_stream.py` | Bun→Python bridge (StreamingAgentsGraph) |
| `analyze.py` | CLI wrapper for analyze_stream |
| `smoke_structured_output.py` | Smoke tests for agent output |
| `seed_database.py` | Reference only — TS version is canonical |

## Shell (`*.sh`)

| Script | Purpose |
|--------|---------|
| `init-test-db.sh` | Initialize test SQLite DB |
| `reset-portfolio.sh` | Reset portfolio state |
| `seed_test_journal.sh` | Seed hledger test journal |
| `copy-test-to-dev.sh` | Copy test DB to dev |

## Development

```bash
# Render all diagrams
just diagrams

# Seed dev database
just seed-db

# Full check
just check
```