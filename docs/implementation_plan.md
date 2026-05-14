# Implementation Plan: Productization & Hybrid UI Architecture

## Phased Implementation Plan

### Phase 1: Engine Optimization (Parallelization & Modularity)
1. Modify `tradingagents/graph/setup.py` to use parallel routing for the Analyst nodes.
2. Add a `standalone` configuration flag. If `True`, the Analyst Synchronizer node routes to `END`. Otherwise, it routes to `Bull Researcher`.
3. Update `cli/main.py` to accept `--analysts` and `--standalone` arguments.
4. Verify sub-graph logic locally.

### Phase 2: Database Integration
1. Add `SQLAlchemy` and `alembic` to the UI backend dependencies.
2. Configure the UI backend to connect to the existing PostgreSQL database (using `DATABASE_URL`).
3. Define models (`User`, `JobMeta`, `Portfolio`, `MemoryLog`) in the `ui/backend/` directory.
3. Update `/api/jobs/trigger` to record job metadata in the database before dispatching the Kubernetes Job.
4. Update `/api/config/portfolio` to write/read from the DB tied to a user session instead of `portfolio.txt`.
5. Migrate `TradingMemoryLog` to query the database by `user_id`.

### Phase 3: Authentication & Multi-Tenancy
1. Add JWT-based authentication middleware to FastAPI.
2. Create login/registration endpoints.
3. Enforce `user_id` context on all API calls (jobs, portfolio, memory).

### Phase 4: UI Enhancements
1. Build Authentication screens (Login/Register).
2. Update the Dashboard to include a "Modular Analysis" workflow builder (Checkboxes for Sentiment, News, etc.).
3. Update the Progress UI to listen for parallel webhooks and render reports dynamically as each node completes.

## Verification & Rollback
- **Local Testing**: Run the parallel graph using standard `make dev` Docker setup without K8s.
- **Database Migrations**: Use Alembic for up/down database migrations to easily roll back schema changes.
- **Job Integrity**: Ensure the "Full Comprehensive Analysis" job remains the default and behaves exactly as it did before, just faster.
