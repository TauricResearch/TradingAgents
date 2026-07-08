# TradingAgents Pro service image (paper trader + dashboard).
# The base repo's Dockerfile remains untouched for the stock workflow.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir ".[dashboard]"

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADINGAGENTS_PRO_DATA=/data

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home trader && mkdir -p /data && chown trader /data
USER trader
VOLUME /data

# Paper trading is the only mode this image runs by default (Constraint 5).
# Live mode additionally requires a checkpointer, human approval, and a real
# venue transport — none of which exist in this image by design.
EXPOSE 8600
CMD ["python", "-m", "uvicorn", "--factory", \
     "tradingagents.pro.dashboard.app:create_default_app", \
     "--host", "0.0.0.0", "--port", "8600"]
