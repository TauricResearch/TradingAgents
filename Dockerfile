FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY tradingagents/ tradingagents/
COPY cli/ cli/
COPY web/ web/

RUN pip install uv && uv sync --no-dev

RUN apt-get update -qq && apt-get install -y -qq nodejs npm \
    && cd web/frontend && npm ci && npm run build \
    && apt-get remove -y -qq nodejs npm && apt-get autoremove -y -qq \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

CMD uv run uvicorn web.server.app:create_app --host 0.0.0.0 --port $PORT
