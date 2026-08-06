-- Fly Managed Postgres runtime grants.
--
-- Fly MPG creates login users through its control plane and exposes only the
-- schema_admin, writer, and reader base roles. Create these two users as
-- `reader` before applying this migration:
--
--   fly mpg users create <cluster-id> --username tradingagents-ingest --role reader
--   fly mpg users create <cluster-id> --username tradingagents-paper --role reader
--
-- Run this file as the schema-admin user after application schema migrations.
-- Starting from reader and adding narrow writes is safer than Fly's broad
-- writer role. Runtime apps must not retain the schema-admin connection URL.

BEGIN;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO "tradingagents-ingest", "tradingagents-paper";

GRANT SELECT, INSERT ON media_posts, media_labels, media_observations, macro_odds
    TO "tradingagents-ingest";
GRANT SELECT, INSERT, UPDATE ON fetch_runs, poll_state
    TO "tradingagents-ingest";

GRANT SELECT ON media_posts, media_labels, media_observations, macro_odds,
    fetch_runs, poll_state TO "tradingagents-paper";
GRANT INSERT, UPDATE ON poll_state TO "tradingagents-paper";
GRANT SELECT, INSERT ON paper_runs, paper_decisions, paper_targets, paper_marks,
    experiment_registry, paper_run_labels, paper_artifacts, paper_decision_bundles,
    paper_events, paper_forecasts, paper_strategy_targets, paper_strategy_marks,
    paper_price_receipts TO "tradingagents-paper";

REVOKE UPDATE, DELETE, TRUNCATE ON paper_decisions, paper_targets, paper_marks,
    experiment_registry, paper_run_labels, paper_artifacts, paper_decision_bundles,
    paper_events, paper_forecasts, paper_strategy_targets, paper_strategy_marks,
    paper_price_receipts
    FROM "tradingagents-paper", "tradingagents-ingest", PUBLIC;

COMMIT;
