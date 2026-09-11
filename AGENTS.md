# Repository Guidelines

## Project Structure & Module Organization

- `tradingagents/agents/`: analyst, researcher, trader, risk, and manager roles; shared schemas and utilities.
- `tradingagents/graph/`: LangGraph orchestration, checkpoints, propagation, and reflection.
- `tradingagents/dataflows/` and `llm_clients/`: financial-data adapters and model-provider clients, respectively, under `tradingagents/`.
- `cli/`: Typer terminal interface; `assets/` and `cli/static/`: visual resources.
- `tests/`: pytest suite; `scripts/`: developer smoke checks.
- `tasks/` and `docs/`: requirements and architecture. The Codex plugin/MCP documents describe planned functionality; do not assume it is implemented.

## Build, Test, and Development Commands

Use Python 3.10 or newer in a virtual environment.

```bash
python -m pip install -e ".[dev]"  # Editable install with pytest and Ruff
python -m cli.main               # Run the interactive analysis CLI
pytest -q                       # Run the configured test suite
pytest tests/test_reporting.py -q # Run one focused test module
ruff check .                    # Run repository lint checks
python -m pip wheel . --no-deps -w /tmp/tradingagents-dist
```

The last command builds a distribution wheel. CI tests Python 3.10–3.13 and checks a clean base installation.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions/modules, and `PascalCase` classes. Follow nearby typing and import conventions. Ruff targets Python 3.10 with a configured 100-character line length; line-length lint is disabled. Avoid repository-wide formatting: wholesale `ruff format` adoption is deferred.

Reuse existing vendor routing, schemas, and report writers. Keep changes scoped to the request and remove only unused code introduced by your change.

## Testing Guidelines

Name tests `tests/test_*.py` and functions `test_*`. Add focused regression checks for changed behavior; mock external services in isolated tests. Registered markers are `unit`, `integration`, and `smoke`. No numerical coverage threshold is configured. Run relevant tests during development and the full suite plus lint before submitting.

## Commit & Pull Request Guidelines

Recent history commonly uses `feat(llm):`, `fix(dataflows):`, `docs:`, and `test:` prefixes. Prefer concise, imperative subjects with a scope when useful. PR descriptions should explain the problem, resulting behavior, linked issue when applicable, and validation performed. Include terminal screenshots only when they clarify display changes.

## Configuration & Agent Instructions

Use `.env.example` for configuration; never commit credentials. Preserve historical date cutoffs, instrument identity, and explicit unavailable-data behavior.