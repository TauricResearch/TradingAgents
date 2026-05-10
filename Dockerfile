FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# gosu: drop privileges from root → appuser inside entrypoint
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && mkdir -p /home/appuser/.tradingagents/cache \
            /home/appuser/.tradingagents/logs \
            /home/appuser/.tradingagents/memory \
 && chown -R appuser:appuser /home/appuser/.tradingagents

WORKDIR /home/appuser/app
COPY --from=builder --chown=appuser:appuser /build .

COPY --chmod=0755 entrypoint.sh /usr/local/bin/entrypoint.sh

# Run as root only long enough for entrypoint to fix volume ownership,
# then gosu switches to appuser before exec'ing tradingagents.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
