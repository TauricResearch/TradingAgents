FROM postgres:17-bookworm

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    lsb-release \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Add TimescaleDB APT repository
RUN echo "deb https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/timescaledb.list \
    && curl -L https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg \
    && apt-get update

# Install TimescaleDB for PostgreSQL 16
RUN apt-get install -y timescaledb-2-postgresql-17

# Install pgvector manually for PostgreSQL 17
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    postgresql-server-dev-17 \
    && rm -rf /var/lib/apt/lists/*

# Clone and build pgvector
RUN cd /tmp && \
    git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git && \
    cd pgvector && \
    make && \
    make install && \
    cd / && \
    rm -rf /tmp/pgvector

# Install pgxman for pgvectorscale (optional)
RUN curl -sfL https://install.pgx.sh | sh || echo "pgxman installation failed"

# Set PostgreSQL path for pgxman
ENV PATH="/usr/lib/postgresql/17/bin:$PATH"
ENV PG_CONFIG="/usr/lib/postgresql/17/bin/pg_config"

# Try to install pgvectorscale - it's optional for basic functionality
RUN cd /tmp && \
    pgxman install pgvectorscale || echo "pgvectorscale not installed - will use basic vector operations"

# Configure PostgreSQL for TimescaleDB (instead of using timescaledb-tune)
RUN echo "shared_preload_libraries = 'timescaledb'" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "# TimescaleDB configuration" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "shared_buffers = 256MB" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "effective_cache_size = 1GB" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "maintenance_work_mem = 64MB" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "work_mem = 4MB" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "timescaledb.max_background_workers = 8" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "max_worker_processes = 16" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "max_parallel_workers_per_gather = 2" >> /usr/share/postgresql/postgresql.conf.sample \
    && echo "max_parallel_workers = 4" >> /usr/share/postgresql/postgresql.conf.sample

# Create initialization script
RUN cat > /docker-entrypoint-initdb.d/00-init.sql <<'EOF'
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
-- vectorscale extension - try to install but don't fail if not available
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'vectorscale extension not available, continuing without it';
END $$;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'vector', 'uuid-ossp');
EOF

EXPOSE 5432
