-- Atomic, content-bound lineage for every persisted media response item.
--
-- Migration 005 is reserved for the confirmatory trial registry.  This
-- migration is self-contained and may be applied after a schema-only restore.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

-- A request started by the pre-lineage collector cannot be completed under the
-- new exact-item contract. Both runtimes must be paused and every old request
-- terminal before this migration is applied.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.fetch_runs WHERE status = 'running'
    ) THEN
        RAISE EXCEPTION
            'atomic fetch lineage migration requires zero running fetch receipts';
    END IF;
END
$$;

ALTER TABLE public.fetch_runs
    ADD COLUMN IF NOT EXISTS formal_eligible_lineage_json TEXT;

-- Nullable for pre-migration runs.  A future collection-cycle manifest can
-- bind all static and dynamically discovered child query attempts through this
-- immutable parent ID without changing the fetch receipt lifecycle again.
ALTER TABLE public.fetch_runs
    ADD COLUMN IF NOT EXISTS collection_cycle_id TEXT;

CREATE TABLE IF NOT EXISTS public.fetch_run_items (
    fetch_run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    raw_content_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    observed_utc DOUBLE PRECISION NOT NULL,
    formal_eligible BOOLEAN NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_pkey'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_pkey
            PRIMARY KEY (fetch_run_id, source, external_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_run_raw_unique'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_run_raw_unique
            UNIQUE (fetch_run_id, raw_content_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_run_fk'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_run_fk
            FOREIGN KEY (fetch_run_id)
            REFERENCES public.fetch_runs(fetch_run_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_media_fk'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_media_fk
            FOREIGN KEY (source, external_id)
            REFERENCES public.media_posts(source, external_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_raw_id_format'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_raw_id_format
            CHECK (raw_content_id ~ '^raw_[0-9a-f]{24}$');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_evidence_id_format'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_evidence_id_format
            CHECK (evidence_id ~ '^evidence_[0-9a-f]{24}$');
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_run_items_observed_utc_finite'
          AND conrelid = 'public.fetch_run_items'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_run_items
            ADD CONSTRAINT fetch_run_items_observed_utc_finite
            CHECK (
                observed_utc > '-Infinity'::DOUBLE PRECISION
                AND observed_utc < 'Infinity'::DOUBLE PRECISION
            );
    END IF;
END
$$;

ALTER TABLE public.fetch_runs
    DROP CONSTRAINT IF EXISTS fetch_runs_collection_cycle_id_format;
ALTER TABLE public.fetch_runs
    ADD CONSTRAINT fetch_runs_collection_cycle_id_format
    CHECK (
        collection_cycle_id IS NULL
        OR collection_cycle_id ~ '^cycle_[0-9a-f]{24}$'
    ) NOT VALID;

ALTER TABLE public.fetch_runs
    DROP CONSTRAINT IF EXISTS fetch_runs_lineage_times_finite;
ALTER TABLE public.fetch_runs
    ADD CONSTRAINT fetch_runs_lineage_times_finite
    CHECK (
        started_utc > '-Infinity'::DOUBLE PRECISION
        AND started_utc < 'Infinity'::DOUBLE PRECISION
        AND (
            received_utc IS NULL
            OR (
                received_utc > '-Infinity'::DOUBLE PRECISION
                AND received_utc < 'Infinity'::DOUBLE PRECISION
            )
        )
        AND (
            completed_utc IS NULL
            OR (
                completed_utc > '-Infinity'::DOUBLE PRECISION
                AND completed_utc < 'Infinity'::DOUBLE PRECISION
            )
        )
    ) NOT VALID;

CREATE OR REPLACE FUNCTION public.formal_evidence_lineage_is_valid(
    evidence_ids_text TEXT,
    lineage_text TEXT
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
    SELECT
        pg_catalog.jsonb_typeof(evidence_ids_text::pg_catalog.jsonb) = 'array'
        AND pg_catalog.jsonb_typeof(lineage_text::pg_catalog.jsonb) = 'array'
        AND NOT EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(
                lineage_text::pg_catalog.jsonb
            ) AS item
            WHERE pg_catalog.jsonb_typeof(item) <> 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(item) AS key)
                    IS DISTINCT FROM ARRAY['evidence_id', 'raw_content_id']::TEXT[]
               OR item->>'evidence_id' !~ '^evidence_[0-9a-f]{24}$'
               OR item->>'raw_content_id' !~ '^raw_[0-9a-f]{24}$'
        )
        AND lineage_text::pg_catalog.jsonb = COALESCE((
            SELECT pg_catalog.jsonb_agg(
                item ORDER BY item->>'evidence_id', item->>'raw_content_id'
            )
            FROM pg_catalog.jsonb_array_elements(
                lineage_text::pg_catalog.jsonb
            ) AS item
        ), '[]'::pg_catalog.jsonb)
        AND evidence_ids_text::pg_catalog.jsonb = COALESCE((
            SELECT pg_catalog.jsonb_agg(item->>'evidence_id' ORDER BY ordinal)
            FROM pg_catalog.jsonb_array_elements(
                lineage_text::pg_catalog.jsonb
            ) WITH ORDINALITY AS entry(item, ordinal)
        ), '[]'::pg_catalog.jsonb)
        AND pg_catalog.jsonb_array_length(lineage_text::pg_catalog.jsonb) = (
            SELECT pg_catalog.count(DISTINCT (
                item->>'evidence_id', item->>'raw_content_id'
            ))
            FROM pg_catalog.jsonb_array_elements(
                lineage_text::pg_catalog.jsonb
            ) AS item
        );
$$;

COMMENT ON FUNCTION public.formal_evidence_lineage_is_valid(TEXT, TEXT) IS
    'tradingagents.formal-evidence-lineage.v1;normalized-prosrc-sha256=d98785b2b63fb1f34786e706acae1c5898c26ac69a9c6598ad06dfb7128a62fe';

ALTER TABLE public.fetch_runs
    DROP CONSTRAINT IF EXISTS fetch_runs_formal_eligible_content_lineage;
ALTER TABLE public.fetch_runs
    ADD CONSTRAINT fetch_runs_formal_eligible_content_lineage
    CHECK (
        (
            formal_eligible_item_count IS NULL
            AND formal_eligible_evidence_ids_json IS NULL
            AND formal_eligible_lineage_json IS NULL
        )
        OR (
            formal_eligible_item_count IS NOT NULL
            AND formal_eligible_evidence_ids_json IS NOT NULL
            AND formal_eligible_lineage_json IS NOT NULL
            AND public.formal_evidence_lineage_is_valid(
                formal_eligible_evidence_ids_json,
                formal_eligible_lineage_json
            )
            AND pg_catalog.jsonb_array_length(
                formal_eligible_lineage_json::pg_catalog.jsonb
            ) = formal_eligible_item_count
        )
    ) NOT VALID;

-- Replace migration 003's lifecycle function so the new terminal lineage field
-- is mutable exactly once. collection_cycle_id is intentionally absent from
-- this allowlist and is therefore immutable from request start onward.
CREATE OR REPLACE FUNCTION public.enforce_fetch_run_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    mutable_finish_fields CONSTANT TEXT[] := ARRAY[
        'status',
        'received_utc',
        'completed_utc',
        'item_count',
        'inserted_count',
        'error',
        'formal_eligible_item_count',
        'formal_eligible_evidence_ids_json',
        'formal_eligible_lineage_json',
        'cursor_after'
    ]::TEXT[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS NULL OR NEW.status <> 'running' THEN
            RAISE EXCEPTION 'fetch_runs rows must be inserted with running status'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'fetch_runs receipts are immutable and cannot be deleted'
            USING ERRCODE = '23514';
    END IF;

    IF OLD.status IS DISTINCT FROM 'running' THEN
        RAISE EXCEPTION 'completed fetch_runs receipts are immutable'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.status IS NULL
       OR NEW.status NOT IN ('success', 'empty', 'failed') THEN
        RAISE EXCEPTION 'fetch_runs completion must transition running to a terminal status'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.cost_units IS DISTINCT FROM OLD.cost_units THEN
        RAISE EXCEPTION 'fetch_runs cost_units is fixed when the request starts'
            USING ERRCODE = '23514';
    END IF;

    IF (pg_catalog.to_jsonb(NEW) - mutable_finish_fields)
       IS DISTINCT FROM (pg_catalog.to_jsonb(OLD) - mutable_finish_fields) THEN
        RAISE EXCEPTION 'fetch_runs completion changed an immutable field'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_fetch_run_lifecycle() IS
    'tradingagents.fetch-run-lifecycle.v2;normalized-prosrc-sha256=2cc223eeb01e1d364a19288558d94bdf5e95f43ab95c00cb441087bbec8e30d4';

DROP TRIGGER IF EXISTS immutable_fetch_runs ON public.fetch_runs;
CREATE TRIGGER immutable_fetch_runs
    BEFORE INSERT OR UPDATE OR DELETE ON public.fetch_runs
    FOR EACH ROW EXECUTE FUNCTION public.enforce_fetch_run_lifecycle();

CREATE OR REPLACE FUNCTION public.enforce_fetch_run_item_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    parent public.fetch_runs%ROWTYPE;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'fetch_run_items lineage is append-only'
            USING ERRCODE = '55000';
    END IF;

    SELECT * INTO parent
    FROM public.fetch_runs
    WHERE fetch_run_id = NEW.fetch_run_id
    FOR UPDATE;
    IF NOT FOUND
       OR parent.status IS DISTINCT FROM 'running'
       OR parent.provider IS DISTINCT FROM NEW.source
       OR NEW.observed_utc < parent.started_utc THEN
        RAISE EXCEPTION 'fetch item lacks a matching running receipt'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_fetch_run_item_lifecycle() IS
    'tradingagents.fetch-run-item-lifecycle.v1;normalized-prosrc-sha256=3b09b817e4945f2fe39b831a7695ad2c8ee0acd7e19084ed1ff31ee7b2d989fa';

DROP TRIGGER IF EXISTS immutable_fetch_run_items ON public.fetch_run_items;
CREATE TRIGGER immutable_fetch_run_items
    BEFORE INSERT OR UPDATE OR DELETE ON public.fetch_run_items
    FOR EACH ROW EXECUTE FUNCTION public.enforce_fetch_run_item_lifecycle();

CREATE OR REPLACE FUNCTION public.enforce_fetch_run_content_completion()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    persisted_kind TEXT := OLD.metadata_json::pg_catalog.jsonb->>'kind';
    lineage_count BIGINT;
    eligible_count BIGINT;
    lineage_payload pg_catalog.jsonb;
BEGIN
    IF TG_OP <> 'UPDATE' OR OLD.status IS DISTINCT FROM 'running' THEN
        RETURN NEW;
    END IF;

    SELECT pg_catalog.count(*),
           pg_catalog.count(*) FILTER (WHERE formal_eligible),
           COALESCE(pg_catalog.jsonb_agg(
               pg_catalog.jsonb_build_object(
                   'evidence_id', evidence_id,
                   'raw_content_id', raw_content_id
               ) ORDER BY evidence_id, raw_content_id
           ) FILTER (WHERE formal_eligible), '[]'::pg_catalog.jsonb)
    INTO lineage_count, eligible_count, lineage_payload
    FROM public.fetch_run_items
    WHERE fetch_run_id = OLD.fetch_run_id;

    IF persisted_kind = 'media' THEN
        IF NEW.status = 'success' AND lineage_count IS DISTINCT FROM NEW.item_count THEN
            RAISE EXCEPTION 'successful media receipt lacks exact item lineage'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.status IN ('empty', 'failed') AND lineage_count <> 0 THEN
            RAISE EXCEPTION 'empty or failed media receipt cannot retain item lineage'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (
            SELECT 1 FROM public.fetch_run_items
            WHERE fetch_run_id = OLD.fetch_run_id
              AND observed_utc IS DISTINCT FROM NEW.received_utc
        ) THEN
            RAISE EXCEPTION 'fetch item observation time differs from receipt time'
                USING ERRCODE = '23514';
        END IF;
    ELSIF lineage_count <> 0 THEN
        RAISE EXCEPTION 'non-media receipt cannot retain media item lineage'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.formal_eligible_item_count IS NOT NULL THEN
        IF eligible_count IS DISTINCT FROM NEW.formal_eligible_item_count
           OR lineage_payload IS DISTINCT FROM
                NEW.formal_eligible_lineage_json::pg_catalog.jsonb THEN
            RAISE EXCEPTION 'formal receipt lineage differs from persisted items'
                USING ERRCODE = '23514';
        END IF;
    ELSIF eligible_count <> 0 OR NEW.formal_eligible_lineage_json IS NOT NULL THEN
        RAISE EXCEPTION 'receipt omitted persisted formal lineage'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.provider IN ('globalnews', 'trendnews')
       AND NEW.status IN ('success', 'empty')
       AND NEW.formal_eligible_lineage_json IS NULL THEN
        RAISE EXCEPTION 'formal news receipt requires content-bound lineage'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_fetch_run_content_completion() IS
    'tradingagents.fetch-run-content-completion.v1;normalized-prosrc-sha256=26e4ec999f2e0a92b95e2d5c0dfa93373a40ebf2c0301a309afa6fa32f616514';

DROP TRIGGER IF EXISTS validate_fetch_run_content_completion
    ON public.fetch_runs;
CREATE TRIGGER validate_fetch_run_content_completion
    BEFORE UPDATE ON public.fetch_runs
    FOR EACH ROW EXECUTE FUNCTION public.enforce_fetch_run_content_completion();

REVOKE ALL PRIVILEGES ON TABLE public.fetch_run_items FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-ingest-v2'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.fetch_run_items
            FROM "tradingagents-ingest-v2";
        GRANT SELECT, INSERT ON TABLE public.fetch_run_items
            TO "tradingagents-ingest-v2";
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-paper'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.fetch_run_items
            FROM "tradingagents-paper";
        GRANT SELECT ON TABLE public.fetch_run_items
            TO "tradingagents-paper";
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-ingest'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.fetch_run_items
            FROM "tradingagents-ingest";
    END IF;
END
$$;

COMMIT;
