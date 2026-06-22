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
 && mkdir -p /home/appuser/.tradingagents /home/appuser/app \
 && chown -R appuser:appuser /home/appuser/.tradingagents /home/appuser/app
WORKDIR /home/appuser/app
COPY --from=python-builder --chown=appuser:appuser /build .
COPY --from=frontend-builder --chown=appuser:appuser /app/dist web/frontend/dist/
COPY --chown=appuser:appuser entrypoint.sh /home/appuser/app/
RUN chmod +x /home/appuser/app/entrypoint.sh
EXPOSE 8080
ENTRYPOINT ["/home/appuser/app/entrypoint.sh"]
