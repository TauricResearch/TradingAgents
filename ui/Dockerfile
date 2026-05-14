# Stage 1: Build the React Frontend
FROM node:18 AS frontend-build
WORKDIR /app
# We need to copy the package.json to install dependencies first
COPY ui/frontend/package.json ./
RUN npm install
# Copy the rest of the frontend source code and build
COPY ui/frontend/ ./
RUN npm run build

# Stage 2: Build the Final Image with FastAPI
FROM python:3.12-slim
WORKDIR /app

# Install FastAPI and Uvicorn
RUN pip install --no-cache-dir fastapi uvicorn

# Copy the backend code
COPY ui/backend/ /app/backend/

# Copy the React build from Stage 1
COPY --from=frontend-build /app/build /app/frontend_build

# Copy minimal required parts of the tradingagents core for config/paths
COPY tradingagents/default_config.py /app/tradingagents/
COPY tradingagents/__init__.py /app/tradingagents/

# Set up environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run the backend (which also serves the frontend)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
