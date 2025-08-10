# Makefile for TradingAgents project

.PHONY: help install install-dev test test-unit test-integration test-coverage lint format clean

# Default target
help:
	@echo "TradingAgents Development Commands"
	@echo "=================================="
	@echo ""
	@echo "Installation:"
	@echo "  install          Install production dependencies"
	@echo "  install-dev      Install development dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-coverage    Run tests with coverage report"
	@echo "  test-fast        Run fast unit tests"
	@echo "  test-slow        Run slow tests"
	@echo ""
	@echo "Quality:"
	@echo "  lint             Run linting and type checking"
	@echo "  format           Format code with black and isort"
	@echo "  mypy             Run mypy type checking"
	@echo ""
	@echo "Utilities:"
	@echo "  clean            Clean up temporary files"
	@echo "  setup-env        Set up development environment"

# Installation targets
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -e ".[dev]"

# Testing targets
test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/unit/ -m unit -v

test-integration:
	python -m pytest tests/integration/ -m integration -v

test-coverage:
	python -m pytest tests/ --cov=tradingagents --cov=cli --cov-report=html:htmlcov --cov-report=term-missing --cov-report=xml

test-fast:
	python -m pytest tests/unit/ -m unit --durations=10 -v

test-slow:
	python -m pytest tests/ -m slow --timeout=600 -v

test-parallel:
	python -m pytest tests/ -n auto -v

# Quality targets
lint:
	python -m mypy tradingagents/ cli/ tests/
	python -m pytest tests/ --collect-only

format:
	python -m black tradingagents/ cli/ tests/
	python -m isort tradingagents/ cli/ tests/

mypy:
	python -m mypy tradingagents/ cli/ tests/

# Development utilities
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage*
	rm -rf coverage.xml
	rm -rf dist/
	rm -rf build/

setup-env:
	@echo "Setting up development environment..."
	@echo "1. Create virtual environment:"
	@echo "   python -m venv venv"
	@echo "   source venv/bin/activate  # On Windows: venv\\Scripts\\activate"
	@echo ""
	@echo "2. Install dependencies:"
	@echo "   make install-dev"
	@echo ""
	@echo "3. Copy .env.example to .env and configure:"
	@echo "   cp .env.example .env"
	@echo "   # Edit .env with your API keys"
	@echo ""
	@echo "4. Run tests to verify setup:"
	@echo "   make test-unit"

# CI/CD style targets
ci-test:
	python -m pytest tests/ --cov=tradingagents --cov=cli --cov-report=xml --junitxml=pytest.xml

ci-lint:
	python -m mypy tradingagents/ cli/ tests/ --junit-xml=mypy.xml

# Development server (if applicable)
run-cli:
	python -m cli.main

# Documentation (if you add docs later)
docs:
	@echo "Documentation generation not yet implemented"

# Package building
build:
	python -m build

# Show project statistics
stats:
	@echo "Project Statistics:"
	@echo "==================="
	@find tradingagents/ -name "*.py" | wc -l | xargs echo "Python files in tradingagents/:"
	@find cli/ -name "*.py" | wc -l | xargs echo "Python files in cli/:"
	@find tests/ -name "*.py" | wc -l | xargs echo "Test files:"
	@find . -name "*.py" -not -path "./venv/*" -not -path "./.venv/*" | xargs wc -l | tail -1 | xargs echo "Total lines of code:"