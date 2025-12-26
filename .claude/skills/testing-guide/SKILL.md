---
name: testing-guide
version: 1.0.0
type: knowledge
description: Test-driven development (TDD), unit/integration/UAT testing strategies, test organization, coverage requirements, and GenAI validation patterns. Use when writing tests, validating code, or ensuring quality.
keywords: test, testing, tdd, unit test, integration test, coverage, pytest, validation, quality assurance, genai validation
auto_activate: true
allowed-tools: [Read, Grep, Glob, Bash]
---

# Testing Guide Skill

Comprehensive testing strategies including TDD, traditional pytest testing, GenAI validation, and system performance meta-analysis.

## When This Skill Activates

- Writing unit/integration/UAT tests
- Implementing TDD workflow
- Setting up test infrastructure
- Measuring test coverage
- Validating code quality
- Performance analysis and optimization
- Keywords: "test", "testing", "tdd", "coverage", "pytest", "validation"

---

## Core Concepts

### 1. Three-Layer Testing Strategy

Modern testing approach combining traditional pytest, GenAI validation, and system performance meta-analysis.

**Layer 1: Traditional Tests (pytest)**
- Unit tests for deterministic logic
- Integration tests for workflows
- Fast, automated, granular feedback

**Layer 2: GenAI Validation (Claude)**
- Validate architectural intent
- Assess code quality beyond syntax
- Comprehensive reasoning about design patterns

**Layer 3: System Performance Testing (Meta-analysis)**
- Agent performance metrics
- Model optimization opportunities
- ROI tracking
- System-wide performance analysis

**See**: `docs/three-layer-strategy.md` for complete framework and decision matrix

---

### 2. Testing Layers

Four-layer testing pyramid from fast unit tests to comprehensive GenAI validation.

**Layers**:
1. **Unit Tests** - Fast, isolated, deterministic (majority of tests)
2. **Integration Tests** - Medium speed, component interactions
3. **UAT Tests** - Slow, end-to-end scenarios (minimal)
4. **GenAI Validation** - Comprehensive, architectural reasoning

**Testing Pyramid**:
```
      /\        Layer 4: GenAI Validation (comprehensive)
     /  \
    /UAT \      Layer 3: UAT Tests (few, slow)
   /______\
  /Int Tests\   Layer 2: Integration Tests (some, medium)
 /__________\
/Unit Tests  \  Layer 1: Unit Tests (many, fast)
```

**See**: `docs/testing-layers.md` for detailed layer descriptions and examples

---

### 3. Testing Workflow & Hybrid Approach

Recommended workflow combining automated testing with manual verification.

**Development Phase**:
- Write failing test first (TDD)
- Implement minimal code to pass
- Refactor with confidence

**Pre-Commit (Automated)**:
- Run fast unit tests
- Check coverage thresholds
- Format code

**Pre-Release (Manual)**:
- GenAI validation for architecture
- Integration tests for workflows
- System performance analysis

**See**: `docs/workflow-hybrid-approach.md` for complete workflow and hybrid testing patterns

---

### 4. TDD Methodology

Test-Driven Development: Write tests before implementation.

**TDD Workflow**:
1. **Red** - Write failing test
2. **Green** - Write minimal code to pass
3. **Refactor** - Improve code while keeping tests green

**Benefits**:
- Guarantees test coverage
- Drives better design
- Provides living documentation
- Enables confident refactoring

**Coverage Standards**:
- Critical paths: 100%
- New features: 80%+
- Bug fixes: Add regression test

**See**: `docs/tdd-methodology.md` for detailed TDD workflow and test patterns

---

### 5. Progression Testing

Track performance improvements over time with baseline comparisons.

**Purpose**:
- Verify optimizations actually improve performance
- Prevent regression in key metrics
- Track system evolution

**How It Works**:
- Establish baseline metrics
- Run progression tests after optimizations
- Compare against baseline
- Update baseline when improvements validated

**See**: `docs/progression-testing.md` for baseline format and test templates

---

### 6. Regression Testing

Prevent fixed bugs from reappearing.

**When to Create**:
- Bug is fixed
- Bug had user impact
- Bug could easily recur

**Regression Test Template**:
```python
def test_regression_issue_123_handles_empty_input():
    """
    Regression test for Issue #123: Handle empty input gracefully.

    Previously crashed with KeyError on empty dict.
    """
    # Arrange
    empty_input = {}

    # Act
    result = process(empty_input)

    # Assert
    assert result == {"status": "empty"}
```

**See**: `docs/regression-testing.md` for complete patterns and organization

---

### 7. Test Tiers & Auto-Categorization (CRITICAL!)

Tests are **automatically marked** based on directory location. No manual `@pytest.mark` needed!

**Tier Structure**:
```
tests/
├── regression/
│   ├── smoke/           # Tier 0: Critical path (<5s) - CI GATE
│   ├── regression/      # Tier 1: Feature protection (<30s)
│   ├── extended/        # Tier 2: Deep validation (<5min)
│   └── progression/     # Tier 3: TDD red phase
├── unit/                # Unit tests (isolated functions)
├── integration/         # Integration tests (multi-component)
├── security/            # Security-focused tests
├── hooks/               # Hook-specific tests
└── archived/            # Obsolete tests (excluded)
```

**Where to Put New Tests**:
```
Is it protecting a released feature?
├─ Yes → Critical path (install, sync, load)?
│        ├─ Yes → tests/regression/smoke/
│        └─ No  → tests/regression/regression/
└─ No  → TDD red phase (not implemented)?
         ├─ Yes → tests/regression/progression/
         └─ No  → Single function/class?
                  ├─ Yes → tests/unit/{subcategory}/
                  └─ No  → tests/integration/
```

**Run by Tier**:
```bash
pytest -m smoke              # CI gate (must pass)
pytest -m regression         # Feature protection
pytest -m "smoke or regression"  # Both
pytest -m unit               # Unit tests only
```

**Validate Categorization**:
```bash
python scripts/validate_test_categorization.py --report
```

**See**: `docs/TESTING-TIERS.md` for complete tier definitions and examples

---

### 8. Test Organization & Best Practices

Directory structure, naming conventions, and testing best practices.

**Naming Conventions**:
- Test files: `test_*.py`
- Test functions: `test_*`
- Regression tests: `test_feature_v{VERSION}_{name}.py`
- Fixtures: descriptive names (no `test_` prefix)

**See**: `docs/test-organization-best-practices.md` for detailed conventions and best practices

---

### 9. Pytest Fixtures & Coverage

Common fixtures for setup/teardown and coverage measurement strategies.

**Common Fixtures**:
- `tmp_path` - Temporary directory
- `monkeypatch` - Mock environment variables
- `capsys` - Capture stdout/stderr
- Custom fixtures for project-specific setup

**Coverage Targets**:
- Unit tests: 90%+
- Integration tests: 70%+
- Overall project: 80%+

**Check Coverage**:
```bash
pytest --cov=src --cov-report=term-missing
```

**See**: `docs/pytest-fixtures-coverage.md` for fixture patterns and coverage strategies

---

### 10. CI/CD Integration

Automated testing in pre-push hooks and GitHub Actions.

**Pre-Push Hook**:
```bash
#!/bin/bash
pytest tests/ || exit 1
```

**GitHub Actions**:
```yaml
- name: Run tests
  run: pytest tests/ --cov=src --cov-report=xml
```

**See**: `docs/ci-cd-integration.md` for complete CI/CD integration patterns

---

## Quick Reference

| Pattern | Use Case | Details |
|---------|----------|---------|
| **Test Tiers** | Auto-categorization | `docs/TESTING-TIERS.md` |
| Three-Layer Strategy | Complete testing approach | `docs/three-layer-strategy.md` |
| Testing Layers | Pytest pyramid | `docs/testing-layers.md` |
| TDD Methodology | Test-first development | `docs/tdd-methodology.md` |
| Progression Testing | Performance tracking | `docs/progression-testing.md` |
| Regression Testing | Bug prevention | `docs/regression-testing.md` |
| Test Organization | Directory structure | `docs/test-organization-best-practices.md` |
| Pytest Fixtures | Setup/teardown patterns | `docs/pytest-fixtures-coverage.md` |
| CI/CD Integration | Automated testing | `docs/ci-cd-integration.md` |

### Test Tier Quick Reference

| Tier | Directory | Time Limit | Purpose |
|------|-----------|------------|---------|
| **0 (Smoke)** | `regression/smoke/` | <5s | CI gate, critical path |
| **1 (Regression)** | `regression/regression/` | <30s | Feature protection |
| **2 (Extended)** | `regression/extended/` | <5min | Deep validation |
| **3 (Progression)** | `regression/progression/` | - | TDD red phase |
| **Unit** | `unit/` | <1s | Isolated functions |
| **Integration** | `integration/` | <30s | Multi-component |

---

## Test Types Decision Matrix

| Test Type | Speed | When to Use | Coverage Target |
|-----------|-------|-------------|-----------------|
| **Unit** | Fast (ms) | Pure functions, deterministic logic | 90%+ |
| **Integration** | Medium (sec) | Component interactions, workflows | 70%+ |
| **UAT** | Slow (min) | End-to-end scenarios, critical paths | Key flows |
| **GenAI Validation** | Slow (min) | Architecture validation, design review | As needed |

---

## Progressive Disclosure

This skill uses progressive disclosure to prevent context bloat:

- **Index** (this file): High-level concepts and quick reference (<500 lines)
- **Detailed docs**: `docs/*.md` files with implementation details (loaded on-demand)

**Available Documentation**:
- `docs/three-layer-strategy.md` - Modern three-layer testing framework
- `docs/testing-layers.md` - Four-layer testing pyramid
- `docs/workflow-hybrid-approach.md` - Development and testing workflow
- `docs/tdd-methodology.md` - Test-driven development patterns
- `docs/progression-testing.md` - Performance baseline tracking
- `docs/regression-testing.md` - Bug prevention patterns
- `docs/test-organization-best-practices.md` - Directory structure and conventions
- `docs/pytest-fixtures-coverage.md` - Pytest patterns and coverage
- `docs/ci-cd-integration.md` - Automated testing integration

---

## Cross-References

**Related Skills**:
- **python-standards** - Python coding conventions
- **code-review** - Code quality standards
- **error-handling-patterns** - Error handling best practices
- **observability** - Logging and monitoring

**Related Tools**:
- pytest - Testing framework
- pytest-cov - Coverage measurement
- pytest-xdist - Parallel test execution
- hypothesis - Property-based testing

---

## Key Takeaways

1. **Put tests in the right directory** - Auto-markers handle the rest (no manual @pytest.mark)
2. **Smoke tests for critical paths** - `regression/smoke/` = CI gate
3. **Write tests first** (TDD) - Guarantees coverage and drives better design
4. **Use the testing pyramid** - Many unit tests, some integration, few UAT
5. **Aim for 80%+ coverage** - Focus on critical paths
6. **Fast tests matter** - Keep unit tests under 1 second
7. **Name tests clearly** - `test_<function>_<scenario>_<expected>`
8. **One assertion per test** - Clear failure messages
9. **Use fixtures** - DRY principle for setup/teardown
10. **Test behavior, not implementation** - Tests should survive refactoring
11. **Add regression tests** - Prevent fixed bugs from returning
12. **Automate testing** - Pre-push hooks and CI/CD
13. **Use GenAI validation** - Architectural reasoning beyond syntax
14. **Track performance** - Progression tests for optimization validation
15. **Validate categorization** - Run `python scripts/validate_test_categorization.py`
