# Stage 1: Build the React Frontend
FROM node:18 AS frontend-build
WORKDIR /app
COPY ui/frontend/package.json ./
RUN npm install
COPY ui/frontend/ ./
RUN npm run build

# Stage 2: Build the Final Image with FastAPI
FROM python:3.12-slim AS builder

WORKDIR /build
COPY ui/backend/requirements.txt .

# Use a virtualenv to avoid system python conflicts
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install ONLY UI-specific requirements
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Final Production Image
FROM python:3.12-slim
WORKDIR /home/appuser/app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents
USER appuser

# Copy ONLY the necessary code for the dashboard
# We copy the tradingagents folder so the backend can import shared logic (config/memory)
# but we DO NOT install its heavy dependencies.
COPY --chown=appuser:appuser tradingagents/ /home/appuser/app/tradingagents/
COPY --chown=appuser:appuser ui/backend/ /home/appuser/app/backend/

# Copy the React build from Stage 1
COPY --from=frontend-build --chown=appuser:appuser /app/build /home/appuser/app/frontend_build

# Set up environment
# PYTHONPATH ensures that 'import tradingagents' works even without 'pip install .'
ENV PYTHONPATH=/home/appuser/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run the backend
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
