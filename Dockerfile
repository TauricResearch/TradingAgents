FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir .

FROM python:3.13-slim

# hermes#213: deploy.sh's tag-pinning/rollback logic (shared with
# scanner/news-gap-ml's own deploy blocks) resolves :latest's real version
# by reading this baked-in env var back out via `docker inspect` -- without
# it, NEW_TAG comes back empty and the deploy aborts right after the pull
# (confirmed live: first deploy attempt failed exactly this way, this
# Dockerfile never declared APP_VERSION before).
ARG APP_VERSION=dev
# TRADINGAGENTS_IN_DOCKER lets an update notice name the rebuild command.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADINGAGENTS_IN_DOCKER=1 \
    APP_VERSION=$APP_VERSION

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents
USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

# hermes#213: only meaningful for the tradingagents-service compose
# override (entrypoint/command swapped to run uvicorn instead of the CLI
# below) -- deploy.sh polls this status to know when the container is ready
# to record as .last_good_version. Harmless no-op signal on the interactive
# `tradingagents` CLI service (nothing listens on 8100 there; it just shows
# "unhealthy", which nothing consumes).
EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=3)" || exit 1

ENTRYPOINT ["tradingagents"]
