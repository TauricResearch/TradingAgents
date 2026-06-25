FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build
COPY pyproject.toml README.md uv.lock ./
COPY tradingagents/ tradingagents/
COPY cli/ cli/
COPY web/ web/

RUN pip install uv && uv sync --no-dev

RUN apt-get update -qq && apt-get install -y -qq nodejs npm \
    && cd web/frontend && npm ci && npm run build \
    && apt-get remove -y -qq nodejs npm && apt-get autoremove -y -qq \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/appuser/app && cp -r /build/. /home/appuser/app
WORKDIR /home/appuser/app

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
