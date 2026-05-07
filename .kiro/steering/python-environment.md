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

## CI Pipeline (`.github/workflows/pre-commit.yml`)

CI runs three steps for the Python job. All must pass before a PR can merge.

### Step 1: Ruff Lint (`ruff check .`)

Checks for code quality issues. Common errors and fixes:

| Rule | Meaning | Fix |
|------|---------|-----|
| I001 | Import block unsorted | `ruff check . --fix` auto-fixes |
| F401 | Unused import | `ruff check . --fix` auto-fixes |
| F841 | Unused variable | Remove the assignment or use `_` prefix |
| E402 | Module-level import not at top | Move import above non-import statements |
| UP047 | Use PEP 695 type params | Replace `T = TypeVar("T", bound=X)` with `def func[T: X](...)` |

### Step 2: Ruff Format (`ruff format --check .`)

Checks formatting matches ruff's style. Fix with:

```bash
.venv/bin/ruff format .
```

### Step 3: Tests (`pytest tests/unit tests/agents tests/graph tests/observability -m "not integration"`)

Runs all non-integration tests. CI installs these packages:
- pytest, pytest-recording, vcrpy, pytest-socket, hypothesis, ruff

If you add a new test dependency, add it to **both**:
1. `pyproject.toml` → `[dependency-groups] dev`
2. `.github/workflows/pre-commit.yml` → `pip install ...` line

## Pre-Push CI Checklist

**Always run these three commands before pushing:**

```bash
.venv/bin/ruff check . --fix   # 1. fix lint errors
.venv/bin/ruff format .        # 2. fix formatting
.venv/bin/pytest tests/unit tests/agents tests/graph tests/observability -m "not integration" -x -q  # 3. run tests
```

Then verify lint and format are clean:

```bash
.venv/bin/ruff check .          # must print "All checks passed!"
.venv/bin/ruff format --check . # must print "X files already formatted"
```

## Key Details

- Python 3.12+
- Test framework: pytest
- Property-based testing: Hypothesis
- Default pytest args (from pyproject.toml): `--ignore=tests/integration --ignore=tests/e2e --disable-socket --allow-unix-socket -x -q`
- To run integration tests explicitly: `.venv/bin/pytest tests/integration/test_file.py -x -q --override-ini="addopts="`
