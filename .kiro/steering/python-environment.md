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
.venv/bin/python -m ruff check .
```

## Key Details

- Python 3.12+
- Test framework: pytest
- Property-based testing: Hypothesis
- Default pytest args (from pyproject.toml): `--ignore=tests/integration --ignore=tests/e2e --disable-socket --allow-unix-socket -x -q`
- To run integration tests explicitly: `.venv/bin/python -m pytest tests/integration/test_file.py -x -q --override-ini="addopts="`
