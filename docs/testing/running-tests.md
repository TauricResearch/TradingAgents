# Running Tests

Complete guide for running the TradingAgents test suite.

## Prerequisites

Install test dependencies:

```bash
pip install -r requirements.txt
pytest --version  # Verify pytest is installed
```

## Basic Usage

### Run All Tests

```bash
pytest tests/
```

### Run with Verbose Output

```bash
pytest tests/ -v
```

### Run with Coverage

```bash
pytest tests/ --cov=tradingagents --cov-report=html
```

View coverage report:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## Test Selection

### By Directory

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Regression tests only
pytest tests/regression/
```

### By File

```bash
pytest tests/unit/test_analysts.py
```

### By Test Function

```bash
pytest tests/unit/test_analysts.py::test_market_analyst_initialization
```

### By Test Class

```bash
pytest tests/unit/test_analysts.py::TestMarketAnalyst
```

### By Pattern

```bash
# Run all tests matching pattern
pytest -k "analyst"

# Run tests NOT matching pattern
pytest -k "not integration"

# Multiple patterns
pytest -k "analyst and not integration"
```

### By Markers

```bash
# Smoke tests (critical path)
pytest -m smoke

# Integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Output Options

### Minimal Output

```bash
pytest tests/ -q
```

### Show All Output

```bash
pytest tests/ -v -s
```

### Show Only Failures

```bash
pytest tests/ --tb=short
```

### Show Failed Tests First

```bash
pytest tests/ --failed-first
```

### Stop on First Failure

```bash
pytest tests/ -x
```

### Stop After N Failures

```bash
pytest tests/ --maxfail=3
```

## Parallel Execution

Run tests in parallel for faster execution:

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run with 4 workers
pytest tests/ -n 4

# Run with auto-detect workers
pytest tests/ -n auto
```

## Test Coverage

### Generate Coverage Report

```bash
pytest tests/ --cov=tradingagents --cov-report=term-missing
```

### Coverage with HTML Report

```bash
pytest tests/ --cov=tradingagents --cov-report=html
```

### Coverage for Specific Module

```bash
pytest tests/ --cov=tradingagents.agents --cov-report=term
```

### Minimum Coverage Threshold

```bash
pytest tests/ --cov=tradingagents --cov-fail-under=80
```

## Debugging Tests

### Run with Python Debugger

```bash
pytest tests/ --pdb
```

### Drop into Debugger on Failure

```bash
pytest tests/ --pdb -x
```

### Show Local Variables on Failure

```bash
pytest tests/ -l
```

### Show Print Statements

```bash
pytest tests/ -s
```

## Environment Setup

### Set Environment Variables

```bash
# For single test run
OPENAI_API_KEY=test_key pytest tests/

# Or create .env.test
cat > .env.test <<EOF
OPENAI_API_KEY=test_key
ALPHA_VANTAGE_API_KEY=test_key
EOF

# Load in tests
pytest tests/
```

### Skip Tests Requiring API Keys

```bash
# Skip integration tests
pytest tests/ -m "not integration"
```

## Continuous Integration

### Pre-Commit Testing

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
pytest tests/regression/smoke/ --maxfail=1 || exit 1
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

### GitHub Actions

Tests run automatically on push/PR via `.github/workflows/tests.yml`

## Test Filtering

### By Test Tier

```bash
# Smoke tests only (fastest)
pytest -m smoke

# Regression tests
pytest -m regression

# Unit tests
pytest tests/unit/
```

### Skip Slow Tests

```bash
pytest -m "not slow"
```

### Skip External API Tests

```bash
pytest -m "not api"
```

## Common Workflows

### Quick Check

```bash
# Fast smoke tests
pytest -m smoke -v
```

### Pre-Commit

```bash
# Critical path tests
pytest tests/regression/smoke/ -v
```

### Full Validation

```bash
# All tests with coverage
pytest tests/ --cov=tradingagents --cov-report=html -v
```

### Debugging Failure

```bash
# Run specific test with debugger
pytest tests/unit/test_analysts.py::test_failing_test --pdb -s
```

## Performance

### Show Slowest Tests

```bash
pytest tests/ --durations=10
```

### Show All Test Durations

```bash
pytest tests/ --durations=0
```

## Output Formats

### JUnit XML (for CI)

```bash
pytest tests/ --junit-xml=test-results.xml
```

### JSON Report

```bash
pip install pytest-json-report
pytest tests/ --json-report --json-report-file=report.json
```

## Troubleshooting

### Tests Not Found

**Issue**: `ERROR: file or directory not found: tests/`

**Solution**: Run from project root
```bash
cd /path/to/TradingAgents
pytest tests/
```

### Import Errors

**Issue**: `ModuleNotFoundError: No module named 'tradingagents'`

**Solution**: Install package in editable mode
```bash
pip install -e .
```

### Fixture Not Found

**Issue**: `fixture 'mock_llm' not found`

**Solution**: Check `conftest.py` is in test directory

### Slow Tests

**Issue**: Tests taking too long

**Solution**: Run specific categories or use parallel execution
```bash
pytest tests/unit/ -n auto
```

## See Also

- [Testing Overview](README.md)
- [Writing Tests](writing-tests.md)
- [Test Organization Best Practices](../../.claude/skills/testing-guide/docs/test-organization-best-practices.md)
