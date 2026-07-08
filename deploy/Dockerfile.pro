# TradingAgents Pro service image (paper trader + dashboard).
# The base repo's Dockerfile remains untouched for the stock workflow.
#
# NOTE: run a SINGLE uvicorn worker — the SSE broadcaster and session
# store are in-process; multiple workers would silently split the stream.
FROM node:22-slim AS frontend

WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
# build emits to ../tradingagents/... in the repo; here we redirect into
# a local dist and copy it into the python build context explicitly
RUN npx tsc -b && npx vite build --outDir /fe/dist

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.lock .
# reproducible builds: exact pinned dependency set first (SEC-02),
# then the project itself without re-resolving
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
COPY --from=frontend /fe/dist/ tradingagents/pro/dashboard/static/
# sourcemaps stay out of the wheel (CI keeps them as artifacts)
RUN find tradingagents/pro/dashboard/static -name "*.map" -delete \
    && pip install --no-cache-dir --no-deps .

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
