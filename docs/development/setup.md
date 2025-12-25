# Development Environment Setup

Complete guide for setting up a TradingAgents development environment.

## Prerequisites

- Python >= 3.10 (Python 3.13 recommended)
- Git
- Conda or virtualenv
- Text editor or IDE (VS Code, PyCharm recommended)

## Step 1: Clone Repository

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

## Step 2: Create Virtual Environment

### Using Conda (Recommended)

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

### Using venv

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows
```

## Step 3: Install Dependencies

### Production Dependencies

```bash
pip install -r requirements.txt
```

### Development Dependencies

```bash
# Install package in editable mode
pip install -e .

# Install testing dependencies
pip install pytest pytest-cov pytest-xdist pytest-mock

# Install linting/formatting tools
pip install black isort flake8 mypy

# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

## Step 4: Configure Environment Variables

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
# LLM Provider (choose one or more)
OPENAI_API_KEY=sk-your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
OPENROUTER_API_KEY=sk-or-v1-your_key_here
GOOGLE_API_KEY=your_key_here

# Data Vendor
ALPHA_VANTAGE_API_KEY=your_key_here

# Application Settings
TRADINGAGENTS_RESULTS_DIR=./results
```

## Step 5: Verify Installation

Run basic tests:

```bash
# Run smoke tests
pytest tests/regression/smoke/ -v

# Run unit tests
pytest tests/unit/ -v

# Quick integration test
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('Import successful')"
```

## Development Tools

### Code Formatting

```bash
# Format with black
black tradingagents/ tests/

# Sort imports with isort
isort tradingagents/ tests/
```

### Linting

```bash
# Check style with flake8
flake8 tradingagents/ tests/

# Type checking with mypy
mypy tradingagents/
```

### Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=tradingagents --cov-report=html

# Run specific test file
pytest tests/unit/test_analysts.py -v
```

## IDE Configuration

### VS Code

Create `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "[python]": {
        "editor.defaultFormatter": "ms-python.black-formatter"
    }
}
```

Create `.vscode/launch.json` for debugging:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "justMyCode": true,
            "envFile": "${workspaceFolder}/.env"
        },
        {
            "name": "Python: Pytest",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": [
                "tests/",
                "-v"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        }
    ]
}
```

### PyCharm

1. Open project in PyCharm
2. Configure interpreter:
   - File → Settings → Project → Python Interpreter
   - Select the virtual environment you created
3. Enable pytest:
   - File → Settings → Tools → Python Integrated Tools
   - Set "Default test runner" to pytest
4. Configure black:
   - File → Settings → Tools → External Tools
   - Add black as external tool

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/my-new-feature
```

### 2. Make Changes

Edit code following project conventions:
- Follow PEP 8 style guide
- Add docstrings to functions
- Write tests for new code
- Update documentation

### 3. Run Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=tradingagents --cov-report=term-missing
```

### 4. Format Code

```bash
# Format code
black tradingagents/ tests/

# Sort imports
isort tradingagents/ tests/

# Check linting
flake8 tradingagents/ tests/
```

### 5. Commit Changes

```bash
git add .
git commit -m "feat: Add new feature description"
```

Commit message format:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test changes
- `refactor:` Code refactoring

### 6. Push and Create PR

```bash
git push origin feature/my-new-feature
```

Then create a pull request on GitHub.

## Project Structure

```
TradingAgents/
├── tradingagents/          # Main package
│   ├── agents/            # Agent implementations
│   │   ├── analysts/      # Analyst agents
│   │   ├── utils/         # Agent utilities
│   │   └── ...
│   ├── dataflows/         # Data vendor integrations
│   ├── graph/             # LangGraph workflow
│   ├── utils/             # Shared utilities
│   └── default_config.py  # Default configuration
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── regression/       # Regression tests
├── cli/                  # CLI interface
├── docs/                 # Documentation
├── examples/             # Example scripts
├── requirements.txt      # Dependencies
└── setup.py             # Package setup
```

## Debugging

### Using Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint()
breakpoint()
```

### Using pytest with debugger

```bash
# Drop into debugger on failure
pytest tests/ --pdb

# Drop into debugger on error
pytest tests/ --pdb -x
```

### Logging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Common Issues

### Import Errors

**Issue**: `ModuleNotFoundError: No module named 'tradingagents'`

**Solution**: Install package in editable mode
```bash
pip install -e .
```

### API Key Errors

**Issue**: `ValueError: OPENAI_API_KEY not found`

**Solution**: Check `.env` file exists and is loaded
```bash
# Verify environment variable
echo $OPENAI_API_KEY

# Or in Python
import os
print(os.getenv("OPENAI_API_KEY"))
```

### Test Failures

**Issue**: Tests fail with mocked data

**Solution**: Check mock data format matches expected schema

## Best Practices

1. **Use Virtual Environment**: Always work in a virtual environment
2. **Run Tests Frequently**: Run tests before committing
3. **Format Code**: Use black and isort consistently
4. **Write Tests**: Add tests for new features
5. **Update Documentation**: Keep docs in sync with code
6. **Small Commits**: Make focused, logical commits
7. **Branch Strategy**: Create feature branches for new work
8. **Code Review**: Get code reviewed before merging

## Resources

- [Contributing Guide](contributing.md)
- [Testing Guide](../testing/README.md)
- [Architecture Documentation](../architecture/multi-agent-system.md)
- [GitHub Repository](https://github.com/TauricResearch/TradingAgents)

## Getting Help

- **Discord**: [Join our community](https://discord.com/invite/hk9PGKShPK)
- **GitHub Issues**: [Report issues](https://github.com/TauricResearch/TradingAgents/issues)
- **Documentation**: [Read the docs](../README.md)
