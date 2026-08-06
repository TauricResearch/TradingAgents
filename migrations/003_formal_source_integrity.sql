-- Formal source-integrity receipt field.
--
-- A successful HTTP response is not sufficient for a formal cutoff slot: the
-- collector must also have observed at least one in-lookback row that passes
-- the frozen independent-editorial boundary.  Existing receipts remain NULL
-- and therefore fail closed; only post-deployment collections can qualify.

BEGIN;

ALTER TABLE fetch_runs
    ADD COLUMN IF NOT EXISTS formal_eligible_item_count INTEGER;

ALTER TABLE fetch_runs
    ADD COLUMN IF NOT EXISTS formal_eligible_evidence_ids_json TEXT;

-- A legacy scalar count is not independently auditable.  Preserve the receipt
-- but make its old scalar lineage fail closed after this migration.
UPDATE fetch_runs
SET formal_eligible_item_count = NULL
WHERE formal_eligible_item_count IS NOT NULL
  AND formal_eligible_evidence_ids_json IS NULL;

ALTER TABLE fetch_runs
    DROP CONSTRAINT IF EXISTS fetch_runs_formal_eligible_item_count_nonnegative;

CREATE OR REPLACE FUNCTION formal_evidence_id_array_is_valid(value TEXT)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT
        jsonb_typeof(value::jsonb) = 'array'
        AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(value::jsonb) AS element
            WHERE jsonb_typeof(element) <> 'string'
               OR (element #>> '{}') !~ '^evidence_[0-9a-f]{24}$'
        )
        AND jsonb_array_length(value::jsonb) = (
            SELECT COUNT(DISTINCT element #>> '{}')
            FROM jsonb_array_elements(value::jsonb) AS element
        );
$$;

ALTER TABLE fetch_runs
    ADD CONSTRAINT fetch_runs_formal_eligible_item_count_nonnegative
    CHECK (
        (
            formal_eligible_item_count IS NULL
            AND formal_eligible_evidence_ids_json IS NULL
        )
        OR (
            formal_eligible_item_count IS NOT NULL
            AND formal_eligible_item_count >= 0
            AND formal_eligible_item_count <= item_count
            AND formal_eligible_evidence_ids_json IS NOT NULL
            AND formal_evidence_id_array_is_valid(
                formal_eligible_evidence_ids_json
            )
            AND jsonb_array_length(formal_eligible_evidence_ids_json::jsonb)
                = formal_eligible_item_count
        )
    ) NOT VALID;

ALTER TABLE fetch_runs
    DROP CONSTRAINT IF EXISTS fetch_runs_terminal_receipt_coherence;

ALTER TABLE fetch_runs
    ADD CONSTRAINT fetch_runs_terminal_receipt_coherence
    CHECK (
        cost_units >= 0
        AND status IN ('running', 'success', 'empty', 'failed')
        AND (
            (
                status = 'running'
                AND received_utc IS NULL
                AND completed_utc IS NULL
                AND item_count IS NULL
                AND inserted_count IS NULL
                AND error IS NULL
                AND formal_eligible_item_count IS NULL
                AND formal_eligible_evidence_ids_json IS NULL
            )
            OR (
                status = 'success'
                AND received_utc IS NOT NULL
                AND completed_utc IS NOT NULL
                AND started_utc <= received_utc
                AND received_utc <= completed_utc
                AND item_count IS NOT NULL
                AND inserted_count IS NOT NULL
                AND item_count > 0
                AND inserted_count BETWEEN 0 AND item_count
                AND error IS NULL
            )
            OR (
                status = 'empty'
                AND received_utc IS NOT NULL
                AND completed_utc IS NOT NULL
                AND started_utc <= received_utc
                AND received_utc <= completed_utc
                AND item_count IS NOT NULL
                AND inserted_count IS NOT NULL
                AND item_count = 0
                AND inserted_count = 0
                AND error IS NULL
            )
            OR (
                status = 'failed'
                AND received_utc IS NOT NULL
                AND completed_utc IS NOT NULL
                AND started_utc <= received_utc
                AND received_utc <= completed_utc
                AND item_count IS NOT NULL
                AND inserted_count IS NOT NULL
                AND item_count = 0
                AND inserted_count = 0
                AND formal_eligible_item_count IS NULL
                AND formal_eligible_evidence_ids_json IS NULL
            )
        )
        AND (
            provider NOT IN ('globalnews', 'trendnews')
            OR status NOT IN ('success', 'empty')
            OR (
                formal_eligible_item_count IS NOT NULL
                AND formal_eligible_evidence_ids_json IS NOT NULL
            )
        )
    ) NOT VALID;

-- A fetch receipt has a two-step lifecycle: INSERT reserves/starts the
-- request, then one UPDATE completes it.  The collector needs UPDATE on this
-- table for that completion, so grants alone cannot make receipts immutable.
-- Keep the mutable set explicit and compare the rest of the row as JSONB so a
-- future column is fail-closed until this migration is deliberately revised.
-- Request cost is fixed when the request is started (and, for paid requests,
-- atomically reserved in poll_state), so completion may not rewrite it.
CREATE OR REPLACE FUNCTION enforce_fetch_run_lifecycle()
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

-- Preflight validates both this marker and the normalized pg_proc.prosrc hash,
-- so replacing the function body without the audited migration fails closed.
COMMENT ON FUNCTION enforce_fetch_run_lifecycle() IS
    'tradingagents.fetch-run-lifecycle.v1;normalized-prosrc-sha256=960437de68144974306543e18d8da4f9ba1f23e3363a1f61cf5bd253b1f54a2a';

DROP TRIGGER IF EXISTS immutable_fetch_runs ON fetch_runs;
CREATE TRIGGER immutable_fetch_runs
    BEFORE INSERT OR UPDATE OR DELETE ON fetch_runs
    FOR EACH ROW EXECUTE FUNCTION enforce_fetch_run_lifecycle();

COMMIT;
