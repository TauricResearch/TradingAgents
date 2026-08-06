-- Append-only provenance for confirmatory decision attempts and completed
-- intent-to-treat holding intervals.
--
-- Attempt events deliberately contain only an allowlisted reason code. They
-- never persist exception messages, provider payloads, credentials, or URLs.
-- A successful paper_decision_bundles row is the authoritative success event;
-- a started event without either a failure or decision bundle records a crash.
--
-- PostgreSQL REAL is float4. At current Unix epochs it cannot preserve even
-- sub-minute ordering, and float4 portfolio values are too narrow for exact
-- accounting replay. The conditional conversion below takes an ACCESS
-- EXCLUSIVE lock and may rewrite a table when a legacy float4 column exists.
-- Schedule the migration while both runtimes are paused. SQLAlchemy's normal
-- PostgreSQL FLOAT columns are already float8, so those media tables are only
-- rewritten if inspection proves that an older float4 schema actually exists.

BEGIN;

-- Never let a caller-controlled search_path redirect catalog-qualified checks
-- to a shadow table or function in another schema.
SET LOCAL search_path = pg_catalog, public;

DO $$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('schema_migrations', 'applied_utc'),
            ('paper_runs', 'created_utc'),
            ('paper_decisions', 'created_utc'),
            ('paper_decisions', 'score'),
            ('paper_targets', 'created_utc'),
            ('paper_marks', 'captured_utc'),
            ('paper_marks', 'nav'),
            ('paper_marks', 'benchmark_nav'),
            ('paper_marks', 'period_return'),
            ('paper_marks', 'benchmark_period_return'),
            ('paper_marks', 'turnover'),
            ('paper_marks', 'trading_cost'),
            ('paper_marks', 'borrow_cost'),
            ('paper_marks', 'benchmark_open'),
            ('experiment_registry', 'created_utc'),
            ('paper_run_labels', 'created_utc'),
            ('paper_artifacts', 'created_utc'),
            ('paper_decision_bundles', 'created_utc'),
            ('paper_strategy_targets', 'created_utc'),
            ('paper_strategy_marks', 'captured_utc'),
            ('paper_strategy_marks', 'nav'),
            ('paper_strategy_marks', 'benchmark_nav'),
            ('paper_strategy_marks', 'period_return'),
            ('paper_strategy_marks', 'benchmark_period_return'),
            ('paper_strategy_marks', 'turnover'),
            ('paper_strategy_marks', 'trading_cost'),
            ('paper_strategy_marks', 'borrow_cost'),
            ('paper_strategy_marks', 'benchmark_open'),
            ('paper_price_receipts', 'captured_utc'),
            ('paper_price_receipts', 'raw_open'),
            ('paper_price_receipts', 'adjusted_open'),
            ('paper_price_receipts', 'dividend'),
            ('paper_price_receipts', 'split_ratio'),
            ('paper_decision_attempt_events', 'created_utc'),
            ('paper_interval_assignments', 'created_utc'),
            ('media_posts', 'created_utc'),
            ('media_posts', 'fetched_utc'),
            ('media_labels', 'linked_utc'),
            ('media_observations', 'observed_utc'),
            ('macro_odds', 'captured_utc'),
            ('macro_odds', 'probability'),
            ('macro_odds', 'volume'),
            ('macro_odds', 'resolution_utc'),
            ('poll_state', 'value'),
            ('fetch_runs', 'started_utc'),
            ('fetch_runs', 'received_utc'),
            ('fetch_runs', 'completed_utc'),
            ('fetch_runs', 'cost_units'),
            ('fetch_runs', 'cursor_before'),
            ('fetch_runs', 'cursor_after')
        ) AS columns_to_check(table_name, column_name)
    LOOP
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = target.table_name
              AND column_name = target.column_name
              AND udt_name = 'float4'
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ALTER COLUMN %I TYPE DOUBLE PRECISION '
                'USING %I::double precision',
                target.table_name, target.column_name, target.column_name
            );
        END IF;
    END LOOP;
END
$$;

CREATE TABLE IF NOT EXISTS public.paper_decision_attempt_events (
    run_id TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    attempt_ordinal INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    created_utc DOUBLE PRECISION NOT NULL,
    reason_code TEXT,
    PRIMARY KEY (run_id, decision_date, attempt_ordinal, event_type),
    CHECK (attempt_ordinal > 0),
    CHECK (event_type IN ('started', 'failed')),
    CHECK (
        (event_type = 'started' AND reason_code IS NULL)
        OR (event_type = 'failed' AND reason_code IN (
            'configuration_failed', 'coverage_gate_failed',
            'decision_window_expired', 'llm_failed', 'market_data_failed',
            'persistence_failed', 'target_construction_failed',
            'unexpected_failure'
        ))
    )
);

CREATE TABLE IF NOT EXISTS public.paper_interval_assignments (
    run_id TEXT NOT NULL,
    interval_index INTEGER NOT NULL,
    from_session_date TEXT NOT NULL,
    session_date TEXT NOT NULL,
    scheduled_decision_date TEXT NOT NULL,
    created_utc DOUBLE PRECISION NOT NULL,
    disposition TEXT NOT NULL,
    applied_target_decision_date TEXT,
    return_vector_id TEXT NOT NULL,
    PRIMARY KEY (run_id, interval_index),
    UNIQUE (run_id, session_date),
    CONSTRAINT paper_interval_assignments_horizon
        CHECK (interval_index > 0 AND interval_index <= 252),
    CHECK (disposition IN (
        'target_applied', 'carry_forward_missing_decision'
    )),
    CHECK (
        (disposition = 'target_applied'
            AND applied_target_decision_date IS NOT NULL)
        OR (disposition = 'carry_forward_missing_decision'
            AND applied_target_decision_date IS NULL)
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'paper_interval_assignments_horizon'
          AND conrelid = 'public.paper_interval_assignments'::regclass
    ) THEN
        ALTER TABLE public.paper_interval_assignments
            ADD CONSTRAINT paper_interval_assignments_horizon
            CHECK (interval_index > 0 AND interval_index <= 252);
    END IF;
END
$$;

-- PaperStore normally installs this shared trigger function before the SQL
-- migrations run.  Define it here as well so a restore or schema-only bootstrap
-- does not depend on that application-side ordering.
CREATE OR REPLACE FUNCTION public.reject_append_only_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'append-only table % cannot be mutated', TG_TABLE_NAME
        USING ERRCODE = '55000';
END
$$;

COMMENT ON FUNCTION public.reject_append_only_mutation() IS
    'tradingagents.append-only.v1';

DROP TRIGGER IF EXISTS immutable_paper_decision_attempt_events
    ON public.paper_decision_attempt_events;
CREATE TRIGGER immutable_paper_decision_attempt_events
    BEFORE UPDATE OR DELETE ON public.paper_decision_attempt_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation();

DROP TRIGGER IF EXISTS immutable_paper_interval_assignments
    ON public.paper_interval_assignments;
CREATE TRIGGER immutable_paper_interval_assignments
    BEFORE UPDATE OR DELETE ON public.paper_interval_assignments
    FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation();

REVOKE ALL PRIVILEGES ON TABLE public.paper_decision_attempt_events,
    public.paper_interval_assignments FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-paper'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.paper_decision_attempt_events,
            public.paper_interval_assignments FROM "tradingagents-paper";
        GRANT SELECT, INSERT ON TABLE public.paper_decision_attempt_events,
            public.paper_interval_assignments TO "tradingagents-paper";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-ingest-v2'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.paper_decision_attempt_events,
            public.paper_interval_assignments
            FROM "tradingagents-ingest-v2";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-ingest'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.paper_decision_attempt_events,
            public.paper_interval_assignments
            FROM "tradingagents-ingest";
    END IF;
END
$$;

DO $$
DECLARE
    invalid_columns TEXT;
BEGIN
    SELECT string_agg(
        columns_to_check.table_name || '.' || columns_to_check.column_name,
        ', ' ORDER BY columns_to_check.table_name, columns_to_check.column_name
    )
    INTO invalid_columns
    FROM (VALUES
        ('schema_migrations', 'applied_utc'),
        ('paper_runs', 'created_utc'),
        ('paper_decisions', 'created_utc'),
        ('paper_decisions', 'score'),
        ('paper_targets', 'created_utc'),
        ('paper_marks', 'captured_utc'),
        ('paper_marks', 'nav'),
        ('paper_marks', 'benchmark_nav'),
        ('paper_marks', 'period_return'),
        ('paper_marks', 'benchmark_period_return'),
        ('paper_marks', 'turnover'),
        ('paper_marks', 'trading_cost'),
        ('paper_marks', 'borrow_cost'),
        ('paper_marks', 'benchmark_open'),
        ('experiment_registry', 'created_utc'),
        ('paper_run_labels', 'created_utc'),
        ('paper_artifacts', 'created_utc'),
        ('paper_decision_bundles', 'created_utc'),
        ('paper_strategy_targets', 'created_utc'),
        ('paper_strategy_marks', 'captured_utc'),
        ('paper_strategy_marks', 'nav'),
        ('paper_strategy_marks', 'benchmark_nav'),
        ('paper_strategy_marks', 'period_return'),
        ('paper_strategy_marks', 'benchmark_period_return'),
        ('paper_strategy_marks', 'turnover'),
        ('paper_strategy_marks', 'trading_cost'),
        ('paper_strategy_marks', 'borrow_cost'),
        ('paper_strategy_marks', 'benchmark_open'),
        ('paper_price_receipts', 'captured_utc'),
        ('paper_price_receipts', 'raw_open'),
        ('paper_price_receipts', 'adjusted_open'),
        ('paper_price_receipts', 'dividend'),
        ('paper_price_receipts', 'split_ratio'),
        ('paper_decision_attempt_events', 'created_utc'),
        ('paper_interval_assignments', 'created_utc'),
        ('media_posts', 'created_utc'),
        ('media_posts', 'fetched_utc'),
        ('media_labels', 'linked_utc'),
        ('media_observations', 'observed_utc'),
        ('macro_odds', 'captured_utc'),
        ('macro_odds', 'probability'),
        ('macro_odds', 'volume'),
        ('macro_odds', 'resolution_utc'),
        ('poll_state', 'value'),
        ('fetch_runs', 'started_utc'),
        ('fetch_runs', 'received_utc'),
        ('fetch_runs', 'completed_utc'),
        ('fetch_runs', 'cost_units'),
        ('fetch_runs', 'cursor_before'),
        ('fetch_runs', 'cursor_after')
    ) AS columns_to_check(table_name, column_name)
    LEFT JOIN information_schema.columns AS actual
      ON actual.table_schema = 'public'
     AND actual.table_name = columns_to_check.table_name
     AND actual.column_name = columns_to_check.column_name
    WHERE actual.udt_name IS DISTINCT FROM 'float8';

    IF invalid_columns IS NOT NULL THEN
        RAISE EXCEPTION 'formal numeric precision migration incomplete: %',
            invalid_columns;
    END IF;
END
$$;

COMMIT;
