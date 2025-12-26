# End-to-End Tests

## Purpose

End-to-end (E2E) tests validate complete workflows and system behavior from a user's perspective. These tests ensure that all components work together correctly in realistic scenarios.

## Characteristics

- **Scope**: Complete workflows involving multiple components
- **Speed**: Slow (minutes) - most expensive tests to run
- **Frequency**: Run before releases, not on every commit
- **Coverage**: Focus on critical user journeys and system integration

## When to Write E2E Tests

Write E2E tests when:
- Testing complete user workflows (e.g., data ingestion → analysis → report generation)
- Validating system behavior across multiple components
- Ensuring critical paths work in production-like environments
- Testing deployment and configuration scenarios

## Guidelines

1. **Keep them minimal**: E2E tests are expensive - focus on critical paths
2. **Use realistic data**: Test with data that resembles production scenarios
3. **Test user journeys**: Validate complete workflows, not individual components
4. **Clean up properly**: Ensure tests clean up resources (files, DB entries, etc.)
5. **Make them independent**: Each test should be runnable in isolation
6. **Document scenarios**: Clearly describe what user journey is being tested

## Running E2E Tests

```bash
# Run all e2e tests
pytest tests/e2e/ -m e2e

# Run specific e2e test
pytest tests/e2e/test_workflow.py -m e2e

# Run with verbose output
pytest tests/e2e/ -m e2e -v
```

## Directory Structure

```
tests/e2e/
├── __init__.py          # Package initialization
├── conftest.py          # E2E-specific fixtures
├── README.md            # This file
└── test_*.py            # E2E test files
```

## Example E2E Test

```python
import pytest

pytestmark = pytest.mark.e2e

def test_complete_data_workflow(e2e_environment):
    """
    Test complete workflow: data ingestion → analysis → report.

    This test validates the entire user journey from fetching market data
    to generating a trading report.
    """
    # Arrange: Set up data source
    # Act: Execute complete workflow
    # Assert: Validate final report output
    pass
```

## Test Pyramid

E2E tests sit at the top of the testing pyramid:

```
      /\        E2E Tests (few, slow, expensive)
     /  \
    /Int \      Integration Tests (some, medium speed)
   /______\
  /  Unit  \    Unit Tests (many, fast, cheap)
 /__________\
```

Most of your tests should be fast unit tests. Use E2E tests sparingly for critical paths.
