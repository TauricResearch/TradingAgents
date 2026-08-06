-- Replace the collector identity whose connection URI was exposed by an old
-- startup log line. The Fly control plane must create
-- `tradingagents-ingest-v2` as a `reader` before this migration is applied.
--
-- This migration is idempotent for the replacement identity. The conditional
-- block allows fresh/restore environments where the retired identity is
-- already absent.

BEGIN;

GRANT USAGE ON SCHEMA public TO "tradingagents-ingest-v2";
REVOKE CREATE ON SCHEMA public FROM "tradingagents-ingest-v2";

GRANT SELECT, INSERT ON media_posts, media_labels, media_observations, macro_odds
    TO "tradingagents-ingest-v2";
GRANT SELECT, INSERT, UPDATE ON fetch_runs, poll_state
    TO "tradingagents-ingest-v2";

REVOKE UPDATE, DELETE, TRUNCATE ON media_posts, media_labels,
    media_observations, macro_odds FROM "tradingagents-ingest-v2";
REVOKE DELETE, TRUNCATE ON fetch_runs, poll_state
    FROM "tradingagents-ingest-v2";
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON paper_runs, paper_decisions,
    paper_targets, paper_marks, experiment_registry, paper_run_labels,
    paper_artifacts, paper_decision_bundles, paper_events, paper_forecasts,
    paper_strategy_targets, paper_strategy_marks, paper_price_receipts
    FROM "tradingagents-ingest-v2";

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-ingest') THEN
        REVOKE ALL PRIVILEGES ON media_posts, media_labels, media_observations,
            macro_odds, fetch_runs, poll_state FROM "tradingagents-ingest";
        REVOKE ALL PRIVILEGES ON paper_runs, paper_decisions, paper_targets,
            paper_marks, experiment_registry, paper_run_labels, paper_artifacts,
            paper_decision_bundles, paper_events, paper_forecasts,
            paper_strategy_targets, paper_strategy_marks, paper_price_receipts
            FROM "tradingagents-ingest";
        REVOKE ALL PRIVILEGES ON SCHEMA public FROM "tradingagents-ingest";
    END IF;
END
$$;

COMMIT;
