---
inclusion: auto
---

# Python Environment

This project uses a local virtual environment at `.venv/`.

## Git & PRs

- The fork remote is `origin` → `aguzererler/TradingAgents`
- Always create PRs on `aguzererler/TradingAgents` (not the upstream `TauricResearch/TradingAgents`)
- Use: `gh pr create --repo aguzererler/TradingAgents --base main`

## Running Python

```bash
.venv/bin/python
```

## Running Tests

```bash
.venv/bin/pytest tests/path/to/test_file.py -x -q
```

## Running a specific test

```bash
.venv/bin/pytest tests/path/to/test_file.py::TestClassName::test_method -x -q
```

## Linting

```bash
.venv/bin/ruff check .
```

## Formatting

```bash
.venv/bin/ruff format .
```

## Pre-Push CI Checklist

CI runs two checks: **Ruff Lint** and **Ruff Format**. Always run both locally before pushing:

```bash
.venv/bin/ruff check . --fix   # fix lint errors (I001, F401, F841, etc.)
.venv/bin/ruff format .        # fix formatting
```

Then verify:

```bash
.venv/bin/ruff check .         # must print "All checks passed!"
.venv/bin/ruff format --check . # must print "X files already formatted"
```

## Key Details

- Python 3.12+
- Test framework: pytest
- Property-based testing: Hypothesis
- Default pytest args (from pyproject.toml): `--ignore=tests/integration --ignore=tests/e2e --disable-socket --allow-unix-socket -x -q`
- To run integration tests explicitly: `.venv/bin/python -m pytest tests/integration/test_file.py -x -q --override-ini="addopts="`
