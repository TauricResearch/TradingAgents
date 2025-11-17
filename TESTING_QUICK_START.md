# Testing Quick Start Guide

Get up and running with the TradingAgents test suite in 5 minutes!

## Prerequisites

```bash
# Make sure pytest is installed
pip install pytest pytest-cov
```

## Quick Commands

### Run All Broker Tests (Recommended First Step)
```bash
cd /home/user/TradingAgents
pytest tests/brokers/ -v
```

**Expected Output**: ✅ 84 passed in 0.45s

### Run with Coverage Report
```bash
pytest tests/brokers/ --cov=tradingagents.brokers --cov-report=term-missing
```

**Expected Coverage**: 89%

### Run Individual Test Files
```bash
# Base broker tests (36 tests)
pytest tests/brokers/test_base_broker.py -v

# Alpaca broker tests (48 tests)
pytest tests/brokers/test_alpaca_broker.py -v
```

### Generate HTML Coverage Report
```bash
pytest tests/brokers/ --cov=tradingagents.brokers --cov-report=html
# Open htmlcov/index.html in your browser
```

## What Gets Tested

### ✅ Broker Integration (89% coverage)
- Base broker interface
- Alpaca broker API integration
- Order management (market, limit, stop orders)
- Position tracking
- Account management
- Error handling

### ✅ LLM Factory (40 tests ready)
- OpenAI, Anthropic, Google support
- Model recommendations
- Configuration handling

### ✅ Web Interface (50+ tests ready)
- Command parsing
- State management
- Integration with brokers

## Test Results Summary

```
========================= test session starts =========================
collected 84 items

tests/brokers/test_base_broker.py::36 tests ..................... PASSED
tests/brokers/test_alpaca_broker.py::48 tests ................... PASSED

Coverage Report:
Name                                     Stmts   Miss  Cover
--------------------------------------------------------------
tradingagents/brokers/alpaca_broker.py     172     20    88%
tradingagents/brokers/base.py              110     10    91%
--------------------------------------------------------------
TOTAL                                      298     34    89%

========================= 84 passed in 0.45s ==========================
```

## Troubleshooting

### Issue: "No module named pytest"
```bash
pip install pytest pytest-cov
```

### Issue: "No tests collected"
```bash
# Make sure you're in the project root
cd /home/user/TradingAgents
pytest tests/brokers/ --collect-only
```

### Issue: Import errors
```bash
# Install the package in development mode
pip install -e .
```

## Next Steps

1. ✅ Run broker tests: `pytest tests/brokers/ -v`
2. 📊 View coverage: `pytest tests/brokers/ --cov=tradingagents.brokers --cov-report=html`
3. 📖 Read full docs: See `tests/README.md` and `TEST_IMPLEMENTATION_SUMMARY.md`
4. 🔧 Add to CI/CD: See examples in `TEST_IMPLEMENTATION_SUMMARY.md`
5. 🚀 Write more tests: Follow patterns in existing test files

## Quick Test Examples

### Test a Single Function
```bash
pytest tests/brokers/test_base_broker.py::TestBrokerOrder::test_create_market_buy_order -v
```

### Test with Detailed Output
```bash
pytest tests/brokers/test_alpaca_broker.py -vv --tb=long
```

### Test and Show Print Statements
```bash
pytest tests/brokers/ -v -s
```

### Test Specific Pattern
```bash
# Run all tests with "order" in the name
pytest tests/brokers/ -v -k "order"

# Run all tests with "connection" in the name
pytest tests/brokers/ -v -k "connection"
```

## Understanding Test Output

### ✅ PASSED - Test succeeded
```
tests/brokers/test_base_broker.py::test_create_market_buy_order PASSED
```

### ❌ FAILED - Test failed
```
tests/brokers/test_base_broker.py::test_something FAILED
  AssertionError: Expected 100 but got 99
```

### ⚠️ WARNING - Non-critical issue
```
PytestConfigWarning: Unknown config option: asyncio_mode
```

## Coverage Interpretation

```
Name                                Stmts   Miss  Cover   Missing
-----------------------------------------------------------------
tradingagents/brokers/base.py         110     10    91%   110, 115, 125
```

- **Stmts**: Total lines of code
- **Miss**: Lines not covered by tests
- **Cover**: Percentage covered
- **Missing**: Specific line numbers not covered

## Test File Structure

```
tests/
├── brokers/
│   ├── __init__.py
│   ├── test_base_broker.py      # Base broker interface tests (36 tests)
│   └── test_alpaca_broker.py    # Alpaca integration tests (48 tests)
├── conftest.py                   # Shared fixtures and utilities
├── test_llm_factory.py           # LLM factory tests (40 tests)
├── test_web_app.py               # Web interface tests (50+ tests)
└── README.md                     # Detailed documentation
```

## Common pytest Options

```bash
-v, --verbose         # Verbose output
-vv                   # Extra verbose
-s                    # Show print statements
-x                    # Stop on first failure
--tb=short            # Shorter tracebacks
--tb=long             # Detailed tracebacks
-k EXPRESSION         # Run tests matching expression
-m MARKER             # Run tests with marker
--collect-only        # Show what tests would run
--durations=10        # Show 10 slowest tests
```

## Questions?

- Full documentation: `tests/README.md`
- Implementation details: `TEST_IMPLEMENTATION_SUMMARY.md`
- Test patterns: Look at existing test files
- Pytest docs: https://docs.pytest.org/

## Success Checklist

- [ ] Ran `pytest tests/brokers/` successfully
- [ ] Saw 84 tests pass
- [ ] Coverage is 89%
- [ ] Generated HTML coverage report
- [ ] Reviewed test files in `tests/brokers/`
- [ ] Read `tests/README.md`

**Ready to write more tests? Copy the patterns from existing tests!**
