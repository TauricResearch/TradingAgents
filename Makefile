.PHONY: help install test test-unit test-smoke lint run docker-build clean

help:
	@echo "TradingAgents — available targets:"
	@echo ""
	@echo "  install      Install project + dev deps (uv sync)"
	@echo "  test         Run full test suite"
	@echo "  test-unit    Run unit tests only (-m unit)"
	@echo "  test-smoke   Run smoke tests only (-m smoke)"
	@echo "  lint         Run ruff + mypy"
	@echo "  run          Launch the interactive CLI"
	@echo "  docker-build Build Docker image tagged 'tradingagents'"
	@echo "  clean        Remove __pycache__ and .pyc files"

install:
	uv sync

test:
	uv run pytest tests/ -x -v

test-unit:
	uv run pytest tests/ -x -v -m unit

test-smoke:
	uv run pytest tests/ -x -v -m smoke

lint:
	uv run ruff check . --fix || true
	uv run mypy tradingagents/ --ignore-missing-imports || true

run:
	uv run tradingagents

docker-build:
	docker build -t tradingagents .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f .coverage
