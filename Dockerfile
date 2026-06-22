FROM node:22-slim AS frontend-builder
WORKDIR /app
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci
COPY web/frontend/ .
RUN npx vite build

FROM python:3.12-slim AS python-builder
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY . .
RUN pip install --no-cache-dir .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN adduser --disabled-password --gecos "" appuser \
 && mkdir -p /home/appuser/.tradingagents \
 && chown -R appuser:appuser /home/appuser/.tradingagents
USER appuser
WORKDIR /home/appuser/app
COPY --from=python-builder --chown=appuser:appuser /build .
COPY --from=frontend-builder --chown=appuser:appuser /app/dist web/frontend/dist/
EXPOSE 8080
CMD uvicorn web.server.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}
