# Stage 1: Build the React Frontend
FROM node:18 AS frontend-build
WORKDIR /app
COPY ui/frontend/package.json ./
RUN npm install
COPY ui/frontend/ ./
RUN npm run build

# Stage 2: Build the Final Image with FastAPI
FROM python:3.12-slim
WORKDIR /home/appuser/app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn

# Create non-root user
RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents
USER appuser

# Copy the backend code
COPY --chown=appuser:appuser ui/backend/ /home/appuser/app/backend/

# Copy the React build from Stage 1
COPY --from=frontend-build --chown=appuser:appuser /app/build /home/appuser/app/frontend_build

# Install the tradingagents core package to ensure all imports/configs work
COPY --chown=appuser:appuser . /home/appuser/app/core
RUN pip install --user --no-cache-dir /home/appuser/app/core

# Set up environment
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PYTHONPATH=/home/appuser/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run the backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
