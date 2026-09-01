# Contributing to TradingAgents

Thank you for your interest in contributing to TradingAgents! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Issues](#reporting-issues)
- [Style Guidelines](#style-guidelines)

## Code of Conduct

Please be respectful and inclusive in all interactions. We are committed to providing a welcoming and inclusive experience for everyone.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a branch for your changes
5. Make your changes and test them
6. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- An LLM provider API key (OpenAI, Google, Anthropic, etc.)

### Installation

```bash
# Clone your fork
git clone https://github.com/<your-username>/TradingAgents.git
cd TradingAgents

# Create a virtual environment
conda create -n tradingagents-dev python=3.13
conda activate tradingagents-dev

# Install in editable mode with development dependencies
pip install -e '.[dev]'
```

### Environment Configuration

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
# Edit .env with your preferred editor and add your API keys
```

## Making Changes

### Branch Naming

Use descriptive branch names:

- `docs/` prefix for documentation changes (e.g., `docs/update-readme`)
- `fix/` prefix for bug fixes (e.g., `fix/memory-leak`)
- `feat/` prefix for new features (e.g., `feat/add-bollinger-indicator`)

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Types:

- `docs:` Documentation-only changes
- `fix:` Bug fixes
- `feat:` New features
- `refactor:` Code changes that neither fix a bug nor add a feature
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Examples:

```
docs(readme): add Indian market ticker examples
fix(yfinance): handle missing data for delisted tickers
feat(agents): add Bollinger Band analyst
```

## Testing

### Running Tests

The test suite uses `pytest`. Run tests with:

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit          # Fast, isolated unit tests
pytest -m integration   # Tests requiring external services
pytest -m smoke         # Quick sanity checks

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_api_key_env.py
```

### Test Categories

Tests are organized with markers:

- **unit**: Fast, isolated tests that mock external dependencies
- **integration**: Tests that require API keys or external services
- **smoke**: Quick sanity checks for basic functionality

### Writing Tests

When adding new features or fixing bugs, include tests:

1. Place tests in the `tests/` directory
2. Name test files as `test_<module>.py`
3. Use descriptive test function names
4. Add appropriate markers (`@pytest.mark.unit`, etc.)
5. Mock external API calls in unit tests

Example:

```python
import pytest

@pytest.mark.unit
def test_default_config_has_required_keys():
    from tradingagents.default_config import DEFAULT_CONFIG
    assert "llm_provider" in DEFAULT_CONFIG
    assert "deep_think_llm" in DEFAULT_CONFIG
```

## Submitting a Pull Request

1. Ensure your changes pass all tests:

   ```bash
   pytest
   ```

2. Update documentation if needed (README, docstrings, etc.)

3. Add an entry to [CHANGELOG.md](CHANGELOG.md) under the `## [Unreleased]` section

4. Push your branch to your fork:

   ```bash
   git push origin docs/add-contributing-guide
   ```

5. Open a pull request against the `main` branch

6. Fill in the PR description with:
   - Summary of changes
   - Related issue numbers (if applicable)
   - Testing performed

### PR Guidelines

- Keep PRs focused: one logical change per PR
- Include tests for new functionality
- Update documentation for user-facing changes
- Ensure CI checks pass before requesting review
- Be responsive to review feedback

## Reporting Issues

When reporting issues, please include:

1. **Description**: Clear description of the issue
2. **Steps to Reproduce**: Minimal steps to reproduce the behavior
3. **Expected Behavior**: What you expected to happen
4. **Actual Behavior**: What actually happened
5. **Environment**: Python version, OS, package version
6. **Logs**: Relevant error messages or stack traces

Use the [issue tracker](https://github.com/TauricResearch/TradingAgents/issues) to report bugs or request features.

## Style Guidelines

### Python Code

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- Use type hints where appropriate
- Write docstrings for public functions and classes
- Keep functions focused and concise

### Documentation

- Use clear, concise language
- Include code examples where helpful
- Keep README and docs up to date with code changes

## Questions?

If you have questions about contributing, feel free to:

- Open a [discussion](https://github.com/TauricResearch/TradingAgents/discussions)
- Join the [Discord community](https://discord.com/invite/hk9PGKShPK)

Thank you for contributing to TradingAgents!
