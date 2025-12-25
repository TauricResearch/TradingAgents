# Contributing to TradingAgents

Thank you for your interest in contributing to TradingAgents! This guide will help you get started.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and collaborative environment.

## How to Contribute

### Reporting Bugs

1. **Check existing issues**: Search [GitHub Issues](https://github.com/TauricResearch/TradingAgents/issues) first
2. **Create detailed report**: Include:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)
   - Relevant code snippets or logs
   - Screenshots if applicable

Example bug report:
```markdown
**Description**: Market analyst fails when ticker has no data

**Steps to Reproduce**:
1. Initialize TradingAgentsGraph
2. Call propagate("INVALID", "2024-01-01")
3. Error occurs in market analyst

**Expected**: Graceful error handling
**Actual**: Unhandled exception

**Environment**:
- Python 3.13
- macOS 14.0
- TradingAgents v0.1.0

**Error**:
```python
KeyError: 'close'
```

### Requesting Features

1. **Check existing requests**: Search issues for similar requests
2. **Create feature request**: Include:
   - Clear use case
   - Proposed solution
   - Alternative approaches considered
   - Impact on existing functionality

Example feature request:
```markdown
**Feature**: Add momentum analyst for multi-timeframe analysis

**Use Case**: Traders need to analyze momentum across daily, weekly, and monthly timeframes

**Proposed Solution**: Create MomentumAnalyst that:
- Calculates ROC, ADX across timeframes
- Identifies trend strength
- Generates momentum-based signals

**Alternatives**: Could extend existing MarketAnalyst

**Impact**: Adds new optional analyst, no breaking changes

### Contributing Code

#### 1. Fork and Clone

```bash
# Fork repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/TradingAgents.git
cd TradingAgents
```

#### 2. Set Up Development Environment

Follow the [Development Setup Guide](setup.md):

```bash
# Create virtual environment
conda create -n tradingagents python=3.13
conda activate tradingagents

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Install development tools
pip install pytest black isort flake8 mypy pre-commit
pre-commit install
```

#### 3. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `test/` - Test additions/improvements
- `refactor/` - Code refactoring

#### 4. Make Changes

Follow coding standards:
- **PEP 8**: Python style guide
- **Type Hints**: Add type annotations
- **Docstrings**: Google-style docstrings
- **Tests**: Write tests for new code
- **Documentation**: Update relevant docs

Example with type hints and docstrings:

```python
from typing import Dict, List, Any

def analyze_momentum(
    ticker: str,
    date: str,
    timeframes: List[str]
) -> Dict[str, Any]:
    """
    Analyze momentum across multiple timeframes.

    Args:
        ticker: Stock ticker symbol (e.g., "NVDA")
        date: Analysis date in YYYY-MM-DD format
        timeframes: List of timeframes ("daily", "weekly", "monthly")

    Returns:
        Dictionary containing momentum analysis:
            - trend_strength: float between 0.0 and 1.0
            - direction: "bullish" or "bearish"
            - signals: list of identified signals

    Raises:
        ValueError: If ticker or date format is invalid
        DataUnavailableError: If data cannot be retrieved

    Example:
        >>> result = analyze_momentum("NVDA", "2024-05-10", ["daily", "weekly"])
        >>> print(result["trend_strength"])
        0.75
    """
    # Implementation
    pass
```

#### 5. Write Tests

Create tests following TDD approach:

```python
# tests/unit/test_momentum_analyst.py

import pytest
from tradingagents.agents.analysts.momentum_analyst import MomentumAnalyst
from unittest.mock import Mock

def test_momentum_analyst_initialization():
    """Test MomentumAnalyst can be initialized."""
    llm = Mock()
    tools = []

    analyst = MomentumAnalyst(llm, tools)

    assert analyst.name == "momentum"
    assert analyst.llm == llm

def test_momentum_analyst_analyze():
    """Test analyst generates momentum analysis."""
    # Arrange
    llm = Mock()
    llm.invoke.return_value = Mock(
        content="Momentum analysis: Strong uptrend..."
    )
    tools = [Mock(name="get_stock_data")]

    analyst = MomentumAnalyst(llm, tools)

    # Act
    report = analyst.analyze("NVDA", "2024-05-10")

    # Assert
    assert "momentum" in report.lower()
    assert llm.invoke.called
```

Run tests:
```bash
pytest tests/ -v
pytest tests/ --cov=tradingagents --cov-report=term-missing
```

#### 6. Update Documentation

Update relevant documentation:
- **API docs**: Add new classes/functions to API reference
- **Guides**: Create/update guides for new features
- **README**: Update if adding major features
- **Docstrings**: Ensure all public APIs have docstrings

#### 7. Format and Lint

```bash
# Format code
black tradingagents/ tests/

# Sort imports
isort tradingagents/ tests/

# Check linting
flake8 tradingagents/ tests/

# Type checking
mypy tradingagents/
```

#### 8. Commit Changes

Follow conventional commits format:

```bash
git add .
git commit -m "feat(analysts): add momentum analyst for multi-timeframe analysis"
```

Commit message format:
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test changes
- `refactor`: Code refactoring
- `style`: Code style changes (formatting)
- `perf`: Performance improvements
- `chore`: Maintenance tasks

Examples:
```bash
feat(agents): add momentum analyst
fix(dataflows): handle missing Alpha Vantage data
docs(guides): add configuration examples
test(analysts): add tests for news analyst
refactor(graph): simplify state management
```

#### 9. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Create pull request on GitHub with:
- Clear title and description
- Reference related issues
- List changes made
- Add screenshots if UI changes
- Mention breaking changes

Pull request template:
```markdown
## Description
Brief description of changes

## Related Issues
Fixes #123

## Changes Made
- Added MomentumAnalyst class
- Integrated multi-timeframe data access
- Added comprehensive tests
- Updated documentation

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Documentation
- [ ] API docs updated
- [ ] Guide created/updated
- [ ] Docstrings added

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

## Development Guidelines

### Code Style

- **PEP 8**: Follow Python style guide
- **Line Length**: Maximum 100 characters (black default)
- **Imports**: Sorted with isort
- **Type Hints**: Add to all public functions
- **Docstrings**: Google-style for all public APIs

### Testing

- **Coverage**: Aim for 80%+ overall
- **Test First**: Write tests before implementation (TDD)
- **Test Tiers**: Place tests in correct directories
  - `tests/unit/` - Fast, isolated tests
  - `tests/integration/` - Component interaction tests
  - `tests/regression/smoke/` - Critical path tests
- **Naming**: `test_<function>_<scenario>_<expected>`

### Documentation

- **API Docs**: Update when adding public APIs
- **Guides**: Create for significant features
- **Inline Comments**: Explain complex logic
- **Examples**: Provide working code examples

### Git Workflow

1. Create feature branch from `main`
2. Make focused, logical commits
3. Keep commits small and atomic
4. Write clear commit messages
5. Rebase on main before PR
6. Squash commits if requested

## Review Process

### What Reviewers Look For

1. **Code Quality**
   - Follows style guidelines
   - Proper error handling
   - Clear variable/function names
   - No unnecessary complexity

2. **Tests**
   - Comprehensive coverage
   - Tests are clear and maintainable
   - Edge cases covered

3. **Documentation**
   - All public APIs documented
   - Guides updated if needed
   - Examples provided

4. **Compatibility**
   - No breaking changes (or properly documented)
   - Works with existing features
   - Backwards compatible if possible

### Addressing Feedback

- Respond to all comments
- Make requested changes
- Ask questions if unclear
- Push updates to same branch
- Mark conversations as resolved

## Release Process

Maintainers handle releases:

1. Update version in `setup.py`
2. Update CHANGELOG.md
3. Create release tag
4. Publish to PyPI
5. Create GitHub release

## Community

- **Discord**: [Join our community](https://discord.com/invite/hk9PGKShPK)
- **GitHub Discussions**: Ask questions, share ideas
- **Twitter**: [@TauricResearch](https://x.com/TauricResearch)

## Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

## Questions?

- Check [Development Setup](setup.md)
- Read [Architecture Docs](../architecture/multi-agent-system.md)
- Ask on Discord or GitHub Discussions

Thank you for contributing to TradingAgents!
