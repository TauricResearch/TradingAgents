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

# Install pgxman
RUN curl -sfL https://install.pgx.sh | sh -

# Install pgvector and pgvectorscale using pgxman
RUN pgxman install pgvector || echo "pgvector install failed" \
    && pgxman install pgvectorscale || echo "pgvectorscale install failed"

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
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SELECT extname, extversion FROM pg_extension;
EOF

EXPOSE 5432
