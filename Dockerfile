FROM python:3.13-slim

WORKDIR /app

# System deps for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Chainlit listens on $PORT (Railway sets this automatically)
CMD chainlit run app.py --host 0.0.0.0 --port ${PORT:-8000}
