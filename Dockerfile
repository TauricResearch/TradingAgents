FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
# ".[server]" adds FastAPI + uvicorn so the same image can serve the TradingDesk
# macOS app's backend (desk-server) in addition to the interactive CLI.
RUN pip install --no-cache-dir ".[server]"

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents
USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

# Backend server port (overridable via DESK_SERVER_PORT). The macOS app maps
# this to 127.0.0.1 on the host so it is never exposed off-box.
EXPOSE 8765

# Default entrypoint is the interactive CLI; the `desk-server` compose service
# overrides the entrypoint to run the HTTP/SSE backend instead.
ENTRYPOINT ["tradingagents"]
