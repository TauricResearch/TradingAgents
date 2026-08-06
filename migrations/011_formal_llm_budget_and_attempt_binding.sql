-- Database-owned formal LLM budgets and exact decision-attempt success binding.
--
-- Apply after migration 010 while every formal worker is paused.  Runtime
-- roles never mutate or read the counter table: the sole write surface is one
-- SECURITY DEFINER function that derives its UTC bucket and frozen limits,
-- reserves both counters, and appends the matching reservation artifact in the
-- same transaction.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

CREATE TABLE IF NOT EXISTS public.formal_llm_budget_counters (
    counter_key TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    protocol_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    counter_kind TEXT NOT NULL,
    bucket_date DATE NOT NULL,
    reserved_calls INTEGER NOT NULL,
    frozen_limit INTEGER NOT NULL,
    first_reserved_utc DOUBLE PRECISION NOT NULL,
    last_reserved_utc DOUBLE PRECISION NOT NULL,
    CONSTRAINT formal_llm_budget_counter_kind
        CHECK (counter_kind IN ('decision', 'utc_day')),
    CONSTRAINT formal_llm_budget_positive_counts
        CHECK (
            reserved_calls > 0
            AND frozen_limit > 0
            AND reserved_calls <= frozen_limit
        ),
    CONSTRAINT formal_llm_budget_finite_times
        CHECK (
            first_reserved_utc > '-Infinity'::DOUBLE PRECISION
            AND first_reserved_utc < 'Infinity'::DOUBLE PRECISION
            AND last_reserved_utc >= first_reserved_utc
            AND last_reserved_utc < 'Infinity'::DOUBLE PRECISION
        ),
    CONSTRAINT formal_llm_budget_bucket_unique
        UNIQUE (scope, protocol_id, run_id, counter_kind, bucket_date)
);

-- An already-running application version may have created a structurally
-- weaker table from its compatibility DDL.  Fail closed unless every exact
-- column and primary/unique key is present with the expected PostgreSQL type.
DO $$
DECLARE
    expected_columns CONSTANT TEXT[] := ARRAY[
        'bucket_date:date:true',
        'counter_key:text:true',
        'counter_kind:text:true',
        'first_reserved_utc:double precision:true',
        'frozen_limit:integer:true',
        'last_reserved_utc:double precision:true',
        'protocol_id:text:true',
        'reserved_calls:integer:true',
        'run_id:text:true',
        'scope:text:true'
    ];
    actual_columns TEXT[];
    valid_keys INTEGER;
    total_keys INTEGER;
BEGIN
    SELECT pg_catalog.array_agg(
        attribute.attname || ':'
        || pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) || ':'
        || attribute.attnotnull::TEXT
        ORDER BY attribute.attname COLLATE pg_catalog."C"
    )
      INTO actual_columns
      FROM pg_catalog.pg_attribute AS attribute
     WHERE attribute.attrelid =
            'public.formal_llm_budget_counters'::pg_catalog.regclass
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped;
    IF actual_columns IS DISTINCT FROM expected_columns THEN
        RAISE EXCEPTION 'formal LLM budget counter schema is not exact'
            USING ERRCODE = '55000';
    END IF;

    SELECT pg_catalog.count(*) FILTER (
               WHERE (installed.contype = 'p'
                      AND installed.columns = ARRAY['counter_key']::NAME[])
                  OR (installed.contype = 'u'
                      AND installed.columns = ARRAY[
                          'scope', 'protocol_id', 'run_id', 'counter_kind',
                          'bucket_date'
                      ]::NAME[])
           ),
           pg_catalog.count(*)
      INTO valid_keys, total_keys
      FROM (
        SELECT constraint_row.contype,
               pg_catalog.array_agg(
                   attribute.attname ORDER BY key_column.ordinality
               ) AS columns
          FROM pg_catalog.pg_constraint AS constraint_row
          CROSS JOIN LATERAL pg_catalog.unnest(constraint_row.conkey)
              WITH ORDINALITY AS key_column(attribute_number, ordinality)
          JOIN pg_catalog.pg_attribute AS attribute
            ON attribute.attrelid = constraint_row.conrelid
           AND attribute.attnum = key_column.attribute_number
         WHERE constraint_row.conrelid =
                'public.formal_llm_budget_counters'::pg_catalog.regclass
           AND constraint_row.contype IN ('p', 'u')
         GROUP BY constraint_row.oid, constraint_row.contype
      ) AS installed;
    IF valid_keys <> 2 OR total_keys <> 2 THEN
        RAISE EXCEPTION 'formal LLM budget counter keys are not exact'
            USING ERRCODE = '55000';
    END IF;
END
$$;

ALTER TABLE public.paper_decision_bundles
    ADD COLUMN IF NOT EXISTS attempt_ordinal INTEGER;

-- No mutable backfill is acceptable: a pre-existing success without an exact
-- attempt identity cannot be made confirmatory after the fact.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.paper_decision_bundles AS bundle
         WHERE bundle.attempt_ordinal IS NULL
    ) THEN
        RAISE EXCEPTION 'existing decision bundle lacks an authenticated attempt ordinal'
            USING ERRCODE = '55000';
    END IF;
END
$$;

ALTER TABLE public.paper_decision_bundles
    ALTER COLUMN attempt_ordinal SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint
         WHERE conname = 'paper_decision_bundles_attempt_positive'
           AND conrelid = 'public.paper_decision_bundles'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.paper_decision_bundles
            ADD CONSTRAINT paper_decision_bundles_attempt_positive
            CHECK (attempt_ordinal > 0);
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.enforce_formal_decision_bundle_attempt()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    latest_ordinal INTEGER;
    started_utc DOUBLE PRECISION;
    artifact JSONB;
BEGIN
    SELECT pg_catalog.max(attempt.attempt_ordinal)
      INTO latest_ordinal
      FROM public.paper_decision_attempt_events AS attempt
     WHERE attempt.run_id = NEW.run_id
       AND attempt.decision_date = NEW.decision_date
       AND attempt.event_type = 'started';
    IF latest_ordinal IS NULL
       OR NEW.attempt_ordinal IS DISTINCT FROM latest_ordinal THEN
        RAISE EXCEPTION 'formal decision bundle is not bound to its latest started attempt'
            USING ERRCODE = '23514';
    END IF;
    SELECT attempt.created_utc
      INTO STRICT started_utc
      FROM public.paper_decision_attempt_events AS attempt
     WHERE attempt.run_id = NEW.run_id
       AND attempt.decision_date = NEW.decision_date
       AND attempt.attempt_ordinal = NEW.attempt_ordinal
       AND attempt.event_type = 'started';
    IF EXISTS (
        SELECT 1
          FROM public.paper_decision_attempt_events AS attempt
         WHERE attempt.run_id = NEW.run_id
           AND attempt.decision_date = NEW.decision_date
           AND attempt.attempt_ordinal = NEW.attempt_ordinal
           AND attempt.event_type = 'failed'
    ) OR NEW.created_utc < started_utc THEN
        RAISE EXCEPTION 'formal decision bundle attempt is failed or precedes its start'
            USING ERRCODE = '23514';
    END IF;
    SELECT stored.content_json::JSONB
      INTO STRICT artifact
      FROM public.paper_artifacts AS stored
     WHERE stored.artifact_id = NEW.artifact_id
       AND stored.artifact_type = 'global_forecast_bundle';
    IF artifact ->> 'run_id' IS DISTINCT FROM NEW.run_id
       OR artifact ->> 'decision_date' IS DISTINCT FROM NEW.decision_date
       OR pg_catalog.jsonb_typeof(artifact -> 'attempt_ordinal') <> 'number'
       OR (artifact ->> 'attempt_ordinal')::NUMERIC
            <> NEW.attempt_ordinal::NUMERIC THEN
        RAISE EXCEPTION 'formal decision bundle artifact has a different attempt identity'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal decision bundle lacks its exact start or artifact'
            USING ERRCODE = '23514';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_decision_bundle_attempt() IS
    'tradingagents.formal-decision-attempt-binding.v1;normalized-prosrc-sha256=1e9613a9150c51e41ffe72fd120b2c3bb1213a3d4d4b786e052bb0ee8859a58e';

DROP TRIGGER IF EXISTS validate_formal_decision_bundle_attempt
    ON public.paper_decision_bundles;
CREATE TRIGGER validate_formal_decision_bundle_attempt
    BEFORE INSERT ON public.paper_decision_bundles
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_decision_bundle_attempt();

CREATE OR REPLACE FUNCTION public.enforce_no_attempt_retry_after_llm_reservation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.event_type = 'started' AND EXISTS (
        SELECT 1
          FROM public.paper_artifacts AS artifact
         WHERE artifact.artifact_type = 'llm_invocation_reserved'
           AND artifact.content_json::JSONB ->> 'run_id' = NEW.run_id
           AND artifact.content_json::JSONB ->> 'decision_date' = NEW.decision_date
    ) THEN
        RAISE EXCEPTION 'formal decision cannot retry after an LLM reservation'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_no_attempt_retry_after_llm_reservation() IS
    'tradingagents.formal-attempt-no-retry-after-reservation.v1;normalized-prosrc-sha256=32247a653505236e9605b2b08bdc6859ec41ad1809099664d34052af43a40114';

DROP TRIGGER IF EXISTS reject_attempt_retry_after_llm_reservation
    ON public.paper_decision_attempt_events;
CREATE TRIGGER reject_attempt_retry_after_llm_reservation
    BEFORE INSERT ON public.paper_decision_attempt_events
    FOR EACH ROW EXECUTE FUNCTION public.enforce_no_attempt_retry_after_llm_reservation();

CREATE OR REPLACE FUNCTION public.reserve_formal_llm_invocation_budget(
    p_run_id TEXT,
    p_decision_date TEXT,
    p_stage TEXT,
    p_provider TEXT,
    p_requested_model TEXT,
    p_input_bundle_id TEXT,
    p_prompt_id TEXT,
    p_prompt_bytes INTEGER,
    p_max_prompt_bytes INTEGER,
    p_max_completion_tokens INTEGER
)
RETURNS TABLE (
    reservation_artifact_id TEXT,
    reservation_receipt_json TEXT,
    decision_count INTEGER,
    daily_count INTEGER,
    utc_day TEXT,
    reserved_utc DOUBLE PRECISION,
    max_calls_per_decision INTEGER,
    max_calls_per_utc_day INTEGER,
    decision_counter_key TEXT,
    daily_counter_key TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    server_timestamp TIMESTAMPTZ;
    server_iso TEXT;
    run_config JSONB;
    protocol JSONB;
    frozen_protocol_id TEXT;
    configured_decision_limit NUMERIC;
    configured_daily_limit NUMERIC;
    protocol_decision_limit NUMERIC;
    protocol_daily_limit NUMERIC;
    protocol_prompt_limit NUMERIC;
    protocol_completion_limit NUMERIC;
    latest_attempt INTEGER;
    prior_decision_receipts INTEGER;
    prior_daily_receipts INTEGER;
    existing_decision_count INTEGER;
    existing_daily_count INTEGER;
    existing_decision_limit INTEGER;
    existing_daily_limit INTEGER;
    invocation_identity JSONB;
    invocation_id TEXT;
    receipt JSONB;
    receipt_text TEXT;
    expected_artifact_id TEXT;
    requested_identity TEXT;
BEGIN
    IF p_run_id IS NULL OR pg_catalog.btrim(p_run_id) = ''
       OR p_decision_date IS NULL OR p_decision_date !~ '^\d{4}-\d{2}-\d{2}$'
       OR p_decision_date::DATE::TEXT IS DISTINCT FROM p_decision_date
       OR p_stage NOT IN (
            'champion', 'without_public_reaction', 'public_reaction_only'
       )
       OR p_provider IS NULL OR pg_catalog.btrim(p_provider) = ''
       OR p_requested_model IS NULL OR pg_catalog.btrim(p_requested_model) = ''
       OR p_input_bundle_id IS NULL OR pg_catalog.btrim(p_input_bundle_id) = ''
       OR p_prompt_id IS NULL OR pg_catalog.btrim(p_prompt_id) = ''
       OR p_prompt_bytes IS NULL OR p_prompt_bytes < 1
       OR p_max_prompt_bytes IS NULL OR p_max_prompt_bytes < 1
       OR p_max_completion_tokens IS NULL OR p_max_completion_tokens < 1
       OR p_prompt_bytes > p_max_prompt_bytes THEN
        RAISE EXCEPTION 'formal LLM reservation request is malformed'
            USING ERRCODE = '22023';
    END IF;

    -- This function remains safe when invoked directly instead of through the
    -- application transaction wrapper.  The shared run lock serializes the
    -- stage uniqueness check, receipt reconciliation, both counter writes,
    -- and the immutable receipt insert.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtext('tradingagents:paper-trial:' || p_run_id)
    );
    server_timestamp := pg_catalog.clock_timestamp();
    reserved_utc := EXTRACT(EPOCH FROM server_timestamp);
    utc_day := (server_timestamp AT TIME ZONE 'UTC')::DATE::TEXT;
    server_iso := pg_catalog.to_char(
        server_timestamp AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.US'
    ) || '+00:00';

    SELECT run.config_json::JSONB, registry.protocol_id
      INTO STRICT run_config, frozen_protocol_id
      FROM public.paper_runs AS run
      JOIN public.formal_trial_registry AS registry
        ON registry.run_id = run.run_id
       AND registry.protocol_id = run.config_json::JSONB ->> 'protocol_id'
     WHERE run.run_id = p_run_id
       AND run.config_json::JSONB ->> 'engine' = 'formal-global-v2';
    SELECT registered.manifest_json::JSONB
      INTO STRICT protocol
      FROM public.experiment_registry AS registered
     WHERE registered.protocol_id = frozen_protocol_id;

    IF pg_catalog.jsonb_typeof(run_config -> 'llm_policy') <> 'object'
       OR pg_catalog.jsonb_typeof(
            run_config -> 'llm_policy' -> 'allowed_models'
       ) <> 'array'
       OR pg_catalog.jsonb_typeof(
            run_config -> 'llm_policy' -> 'max_calls_per_decision'
       ) <> 'number'
       OR pg_catalog.jsonb_typeof(
            run_config -> 'llm_policy' -> 'max_calls_per_utc_day'
       ) <> 'number'
       OR pg_catalog.jsonb_typeof(
            protocol -> 'forecast' -> 'invocation_policy'
                -> 'max_calls_per_decision'
       ) <> 'number'
       OR pg_catalog.jsonb_typeof(
            protocol -> 'forecast' -> 'invocation_policy'
                -> 'max_calls_per_utc_day'
       ) <> 'number'
       OR pg_catalog.jsonb_typeof(
            protocol -> 'forecast' -> 'invocation_policy' -> 'max_prompt_bytes'
       ) <> 'number'
       OR pg_catalog.jsonb_typeof(
            protocol -> 'forecast' -> 'invocation_policy'
                -> 'max_completion_tokens'
       ) <> 'number' THEN
        RAISE EXCEPTION 'formal LLM frozen budget policy is malformed'
            USING ERRCODE = '23514';
    END IF;

    configured_decision_limit := (
        run_config -> 'llm_policy' ->> 'max_calls_per_decision'
    )::NUMERIC;
    configured_daily_limit := (
        run_config -> 'llm_policy' ->> 'max_calls_per_utc_day'
    )::NUMERIC;
    protocol_decision_limit := (
        protocol -> 'forecast' -> 'invocation_policy'
            ->> 'max_calls_per_decision'
    )::NUMERIC;
    protocol_daily_limit := (
        protocol -> 'forecast' -> 'invocation_policy'
            ->> 'max_calls_per_utc_day'
    )::NUMERIC;
    protocol_prompt_limit := (
        protocol -> 'forecast' -> 'invocation_policy' ->> 'max_prompt_bytes'
    )::NUMERIC;
    protocol_completion_limit := (
        protocol -> 'forecast' -> 'invocation_policy'
            ->> 'max_completion_tokens'
    )::NUMERIC;
    IF configured_decision_limit <> pg_catalog.trunc(configured_decision_limit)
       OR configured_daily_limit <> pg_catalog.trunc(configured_daily_limit)
       OR protocol_decision_limit <> pg_catalog.trunc(protocol_decision_limit)
       OR protocol_daily_limit <> pg_catalog.trunc(protocol_daily_limit)
       OR protocol_prompt_limit <> pg_catalog.trunc(protocol_prompt_limit)
       OR protocol_completion_limit <> pg_catalog.trunc(protocol_completion_limit)
       OR configured_decision_limit < 0 OR configured_daily_limit < 0
       OR configured_decision_limit > 2147483647
       OR configured_daily_limit > 2147483647
       OR configured_decision_limit IS DISTINCT FROM protocol_decision_limit
       OR configured_daily_limit IS DISTINCT FROM protocol_daily_limit
       OR p_max_prompt_bytes::NUMERIC IS DISTINCT FROM protocol_prompt_limit
       OR p_max_completion_tokens::NUMERIC IS DISTINCT FROM protocol_completion_limit
       OR (run_config ->> 'llm_max_prompt_bytes')::NUMERIC
            IS DISTINCT FROM protocol_prompt_limit
       OR (run_config ->> 'llm_max_completion_tokens')::NUMERIC
            IS DISTINCT FROM protocol_completion_limit THEN
        RAISE EXCEPTION 'formal LLM request differs from its frozen budget policy'
            USING ERRCODE = '23514';
    END IF;
    max_calls_per_decision := configured_decision_limit::INTEGER;
    max_calls_per_utc_day := configured_daily_limit::INTEGER;
    IF max_calls_per_decision < 1 OR max_calls_per_utc_day < 1 THEN
        RAISE EXCEPTION 'formal LLM budget exhausted'
            USING ERRCODE = 'P0001';
    END IF;

    requested_identity := pg_catalog.lower(pg_catalog.btrim(p_provider))
        || ':' || pg_catalog.btrim(p_requested_model);
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.jsonb_array_elements_text(
            run_config -> 'llm_policy' -> 'allowed_models'
          ) AS allowed(identity)
         WHERE allowed.identity = requested_identity
    ) THEN
        RAISE EXCEPTION 'formal LLM requested model is not frozen'
            USING ERRCODE = '23514';
    END IF;

    SELECT pg_catalog.max(attempt.attempt_ordinal)
      INTO latest_attempt
      FROM public.paper_decision_attempt_events AS attempt
     WHERE attempt.run_id = p_run_id
       AND attempt.decision_date = p_decision_date
       AND attempt.event_type = 'started';
    IF latest_attempt IS NULL OR EXISTS (
        SELECT 1
          FROM public.paper_decision_attempt_events AS attempt
         WHERE attempt.run_id = p_run_id
           AND attempt.decision_date = p_decision_date
           AND attempt.attempt_ordinal = latest_attempt
           AND attempt.event_type = 'failed'
    ) OR EXISTS (
        SELECT 1
          FROM public.paper_decision_bundles AS bundle
         WHERE bundle.run_id = p_run_id
           AND bundle.decision_date = p_decision_date
    ) THEN
        RAISE EXCEPTION 'formal LLM reservation requires one latest live attempt'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.paper_artifacts AS artifact
         WHERE artifact.artifact_type = 'llm_invocation_reserved'
           AND artifact.content_json::JSONB ->> 'run_id' = p_run_id
           AND artifact.content_json::JSONB ->> 'decision_date' = p_decision_date
           AND artifact.content_json::JSONB ->> 'stage' = p_stage
    ) THEN
        RAISE EXCEPTION 'formal LLM stage already has a reservation'
            USING ERRCODE = '23505';
    END IF;

    decision_counter_key := 'llm:formal-global-v2:decision:'
        || p_run_id || ':' || p_decision_date;
    daily_counter_key := 'llm:formal-global-v2:protocol:'
        || frozen_protocol_id || ':utc-day:' || utc_day;

    SELECT counter.reserved_calls, counter.frozen_limit
      INTO existing_decision_count, existing_decision_limit
      FROM public.formal_llm_budget_counters AS counter
     WHERE counter.counter_key = decision_counter_key;
    SELECT counter.reserved_calls, counter.frozen_limit
      INTO existing_daily_count, existing_daily_limit
      FROM public.formal_llm_budget_counters AS counter
     WHERE counter.counter_key = daily_counter_key;
    SELECT pg_catalog.count(*)
      INTO prior_decision_receipts
      FROM public.paper_artifacts AS artifact
     WHERE artifact.artifact_type = 'llm_invocation_reserved'
       AND artifact.content_json::JSONB ->> 'run_id' = p_run_id
       AND artifact.content_json::JSONB ->> 'decision_date' = p_decision_date;
    SELECT pg_catalog.count(*)
      INTO prior_daily_receipts
      FROM public.paper_artifacts AS artifact
     WHERE artifact.artifact_type = 'llm_invocation_reserved'
       AND artifact.content_json::JSONB ->> 'run_id' = p_run_id
       AND artifact.content_json::JSONB ->> 'utc_day' = utc_day;
    IF COALESCE(existing_decision_count, 0) <> prior_decision_receipts
       OR COALESCE(existing_daily_count, 0) <> prior_daily_receipts
       OR (
            existing_decision_count IS NOT NULL
            AND existing_decision_limit IS DISTINCT FROM max_calls_per_decision
       ) OR (
            existing_daily_count IS NOT NULL
            AND existing_daily_limit IS DISTINCT FROM max_calls_per_utc_day
       ) THEN
        RAISE EXCEPTION 'formal LLM counter and immutable receipts disagree'
            USING ERRCODE = '55000';
    END IF;

    INSERT INTO public.formal_llm_budget_counters AS counter (
        counter_key, scope, protocol_id, run_id, counter_kind, bucket_date,
        reserved_calls, frozen_limit, first_reserved_utc, last_reserved_utc
    ) VALUES (
        decision_counter_key, 'formal-global-v2', frozen_protocol_id, p_run_id,
        'decision', p_decision_date::DATE, 1, max_calls_per_decision,
        reserved_utc, reserved_utc
    )
    ON CONFLICT (counter_key) DO UPDATE
       SET reserved_calls = counter.reserved_calls + 1,
           last_reserved_utc = EXCLUDED.last_reserved_utc
     WHERE counter.scope = EXCLUDED.scope
       AND counter.protocol_id = EXCLUDED.protocol_id
       AND counter.run_id = EXCLUDED.run_id
       AND counter.counter_kind = EXCLUDED.counter_kind
       AND counter.bucket_date = EXCLUDED.bucket_date
       AND counter.frozen_limit = EXCLUDED.frozen_limit
       AND counter.reserved_calls < counter.frozen_limit
    RETURNING counter.reserved_calls INTO decision_count;
    IF decision_count IS NULL THEN
        RAISE EXCEPTION 'formal LLM budget exhausted or frozen limit changed'
            USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO public.formal_llm_budget_counters AS counter (
        counter_key, scope, protocol_id, run_id, counter_kind, bucket_date,
        reserved_calls, frozen_limit, first_reserved_utc, last_reserved_utc
    ) VALUES (
        daily_counter_key, 'formal-global-v2', frozen_protocol_id, p_run_id,
        'utc_day', utc_day::DATE, 1, max_calls_per_utc_day,
        reserved_utc, reserved_utc
    )
    ON CONFLICT (counter_key) DO UPDATE
       SET reserved_calls = counter.reserved_calls + 1,
           last_reserved_utc = EXCLUDED.last_reserved_utc
     WHERE counter.scope = EXCLUDED.scope
       AND counter.protocol_id = EXCLUDED.protocol_id
       AND counter.run_id = EXCLUDED.run_id
       AND counter.counter_kind = EXCLUDED.counter_kind
       AND counter.bucket_date = EXCLUDED.bucket_date
       AND counter.frozen_limit = EXCLUDED.frozen_limit
       AND counter.reserved_calls < counter.frozen_limit
    RETURNING counter.reserved_calls INTO daily_count;
    IF daily_count IS NULL THEN
        RAISE EXCEPTION 'formal LLM budget exhausted or frozen limit changed'
            USING ERRCODE = 'P0001';
    END IF;

    invocation_identity := pg_catalog.jsonb_build_object(
        'scope', 'formal-global-v2',
        'run_id', p_run_id,
        'decision_date', p_decision_date,
        'ordinal', decision_count,
        'stage', p_stage,
        'provider', p_provider,
        'requested_model', p_requested_model,
        'input_bundle_id', p_input_bundle_id
    );
    invocation_id := 'invocation_' || pg_catalog.substr(
        pg_catalog.encode(
            pg_catalog.sha256(pg_catalog.convert_to(
                public.canonical_jsonb_text(invocation_identity), 'UTF8'
            )),
            'hex'
        ),
        1,
        24
    );
    receipt := pg_catalog.jsonb_build_object(
        'schema_version', 2,
        'invocation_id', invocation_id,
        'scope', 'formal-global-v2',
        'run_id', p_run_id,
        'decision_date', p_decision_date,
        'ordinal', decision_count,
        'stage', p_stage,
        'provider', p_provider,
        'requested_model', p_requested_model,
        'input_bundle_id', p_input_bundle_id,
        'prompt_id', p_prompt_id,
        'prompt_bytes', p_prompt_bytes,
        'max_prompt_bytes', p_max_prompt_bytes,
        'max_completion_tokens', p_max_completion_tokens,
        'max_calls_per_decision', max_calls_per_decision,
        'max_calls_per_utc_day', max_calls_per_utc_day,
        'decision_counter_key', decision_counter_key,
        'daily_counter_key', daily_counter_key,
        'utc_day', utc_day,
        'reserved_utc', server_iso,
        'reservation_counts', pg_catalog.jsonb_build_object(
            decision_counter_key, decision_count,
            daily_counter_key, daily_count
        )
    );
    receipt_text := public.canonical_jsonb_text(receipt);
    expected_artifact_id := 'artifact_' || pg_catalog.substr(
        pg_catalog.encode(
            pg_catalog.sha256(pg_catalog.convert_to(
                public.canonical_jsonb_text(pg_catalog.jsonb_build_object(
                    'artifact_type', 'llm_invocation_reserved',
                    'content', receipt
                )),
                'UTF8'
            )),
            'hex'
        ),
        1,
        24
    );
    INSERT INTO public.paper_artifacts (
        artifact_id, created_utc, artifact_type, content_json
    ) VALUES (
        expected_artifact_id, reserved_utc,
        'llm_invocation_reserved', receipt_text
    );
    reservation_artifact_id := expected_artifact_id;
    reservation_receipt_json := receipt_text;
    RETURN NEXT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal LLM reservation lacks its registered run or protocol'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.reserve_formal_llm_invocation_budget(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, INTEGER
) IS
    'tradingagents.formal-llm-atomic-reservation.v1;normalized-prosrc-sha256=083360a3e261ff35bdbff9a366a24d4039660f9fcb4b6e4f1e49d6d655c2958e';

REVOKE ALL PRIVILEGES ON TABLE public.formal_llm_budget_counters FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reserve_formal_llm_invocation_budget(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, INTEGER
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_decision_bundle_attempt() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_no_attempt_retry_after_llm_reservation() FROM PUBLIC;

DO $$
DECLARE
    runtime_role TEXT;
BEGIN
    FOREACH runtime_role IN ARRAY ARRAY[
        'tradingagents-paper', 'tradingagents-paper-decision',
        'tradingagents-paper-marker', 'tradingagents-ingest-v2',
        'tradingagents-ingest'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = runtime_role
        ) THEN
            EXECUTE pg_catalog.format(
                'REVOKE ALL PRIVILEGES ON TABLE '
                'public.formal_llm_budget_counters FROM %I',
                runtime_role
            );
            EXECUTE pg_catalog.format(
                'REVOKE ALL ON FUNCTION '
                'public.reserve_formal_llm_invocation_budget('
                'TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,INTEGER,INTEGER) '
                'FROM %I',
                runtime_role
            );
        END IF;
    END LOOP;
    FOREACH runtime_role IN ARRAY ARRAY[
        'tradingagents-paper', 'tradingagents-paper-decision'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = runtime_role
        ) THEN
            EXECUTE pg_catalog.format(
                'GRANT EXECUTE ON FUNCTION '
                'public.reserve_formal_llm_invocation_budget('
                'TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,INTEGER,INTEGER) '
                'TO %I',
                runtime_role
            );
        END IF;
    END LOOP;
END
$$;

COMMIT;
