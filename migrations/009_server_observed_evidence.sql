-- Database-authenticated observation times for fetch receipts and collection cycles.
--
-- Caller timestamps remain immutable provider/operation chronology, but they are
-- never sufficient for a formal cutoff.  New server fields are overwritten by
-- lifecycle triggers from PostgreSQL's wall clock.  Pre-migration rows remain
-- NULL and therefore fail closed instead of being retroactively authenticated.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.fetch_runs WHERE status = 'running')
       OR EXISTS (SELECT 1 FROM public.collection_cycles WHERE status = 'running') THEN
        RAISE EXCEPTION
            'server-observed evidence migration requires zero running fetches/cycles';
    END IF;
END
$$;

ALTER TABLE public.fetch_runs
    ADD COLUMN IF NOT EXISTS server_started_utc DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS server_terminal_utc DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS collector_build_id TEXT;

ALTER TABLE public.collection_cycles
    ADD COLUMN IF NOT EXISTS server_started_utc DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS server_terminal_utc DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS collector_build_id TEXT;

ALTER TABLE public.fetch_runs
    DROP CONSTRAINT IF EXISTS fetch_runs_server_observation_shape;
ALTER TABLE public.fetch_runs
    ADD CONSTRAINT fetch_runs_server_observation_shape CHECK (
        (
            server_started_utc IS NULL
            AND server_terminal_utc IS NULL
            AND collector_build_id IS NULL
        )
        OR (
            server_started_utc > '-Infinity'::DOUBLE PRECISION
            AND server_started_utc < 'Infinity'::DOUBLE PRECISION
            AND collector_build_id ~ '^build_[0-9a-f]{24}$'
            AND (
                (status = 'running' AND server_terminal_utc IS NULL)
                OR (
                    status IN ('success', 'empty', 'failed')
                    AND server_terminal_utc >= server_started_utc
                    AND server_terminal_utc > '-Infinity'::DOUBLE PRECISION
                    AND server_terminal_utc < 'Infinity'::DOUBLE PRECISION
                )
            )
        )
    ) NOT VALID;

ALTER TABLE public.collection_cycles
    DROP CONSTRAINT IF EXISTS collection_cycles_server_observation_shape;
ALTER TABLE public.collection_cycles
    ADD CONSTRAINT collection_cycles_server_observation_shape CHECK (
        (
            server_started_utc IS NULL
            AND server_terminal_utc IS NULL
            AND collector_build_id IS NULL
        )
        OR (
            server_started_utc > '-Infinity'::DOUBLE PRECISION
            AND server_started_utc < 'Infinity'::DOUBLE PRECISION
            AND collector_build_id ~ '^build_[0-9a-f]{24}$'
            AND (
                (status = 'running' AND server_terminal_utc IS NULL)
                OR (
                    status IN ('complete', 'incomplete')
                    AND server_terminal_utc >= server_started_utc
                    AND server_terminal_utc > '-Infinity'::DOUBLE PRECISION
                    AND server_terminal_utc < 'Infinity'::DOUBLE PRECISION
                )
            )
        )
    );

-- Compact, key-sorted JSON text matching the application's canonical encoder.
-- Manifest v2 normalizes integral doubles to JSON integers before hashing.
CREATE OR REPLACE FUNCTION public.canonical_jsonb_text(value JSONB)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
    SELECT CASE pg_catalog.jsonb_typeof(value)
        WHEN 'object' THEN '{' || COALESCE((
            SELECT pg_catalog.string_agg(
                pg_catalog.to_jsonb(entry.key)::TEXT || ':'
                    || public.canonical_jsonb_text(entry.value),
                ',' ORDER BY entry.key COLLATE "C"
            )
            FROM pg_catalog.jsonb_each(value) AS entry(key, value)
        ), '') || '}'
        WHEN 'array' THEN '[' || COALESCE((
            SELECT pg_catalog.string_agg(
                public.canonical_jsonb_text(entry.item),
                ',' ORDER BY entry.ordinal
            )
            FROM pg_catalog.jsonb_array_elements(value)
                WITH ORDINALITY AS entry(item, ordinal)
        ), '') || ']'
        ELSE value::TEXT
    END
$$;

COMMENT ON FUNCTION public.canonical_jsonb_text(JSONB) IS
    'tradingagents.canonical-jsonb-text.v1;normalized-prosrc-sha256=5d530ed30c769012e3ec4cc7650ae6f276ea0019ddaf8d13f2c4d165f6e7c78f';

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
        'cursor_after',
        'server_terminal_utc'
    ]::TEXT[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS NULL OR NEW.status <> 'running' THEN
            RAISE EXCEPTION 'fetch_runs rows must be inserted with running status'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.collector_build_id IS NULL
           OR NEW.collector_build_id !~ '^build_[0-9a-f]{24}$' THEN
            RAISE EXCEPTION 'fetch_runs require a canonical collector build identity'
                USING ERRCODE = '23514';
        END IF;
        NEW.server_started_utc := pg_catalog.date_part(
            'epoch', pg_catalog.clock_timestamp()
        );
        NEW.server_terminal_utc := NULL;
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

    NEW.server_started_utc := OLD.server_started_utc;
    NEW.collector_build_id := OLD.collector_build_id;
    NEW.server_terminal_utc := pg_catalog.date_part(
        'epoch', pg_catalog.clock_timestamp()
    );
    IF (pg_catalog.to_jsonb(NEW) - mutable_finish_fields)
       IS DISTINCT FROM (pg_catalog.to_jsonb(OLD) - mutable_finish_fields) THEN
        RAISE EXCEPTION 'fetch_runs completion changed an immutable field'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_fetch_run_lifecycle() IS
    'tradingagents.fetch-run-lifecycle.v3;normalized-prosrc-sha256=e69793ca6965e8ddccd178088b0506c178f369a88d2d501b05d0ca7d9e2e2b84';

DROP TRIGGER IF EXISTS immutable_fetch_runs ON public.fetch_runs;
CREATE TRIGGER immutable_fetch_runs
    BEFORE INSERT OR UPDATE OR DELETE ON public.fetch_runs
    FOR EACH ROW EXECUTE FUNCTION public.enforce_fetch_run_lifecycle();

CREATE OR REPLACE FUNCTION public.enforce_collection_cycle_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    identity pg_catalog.jsonb;
    static_slots pg_catalog.jsonb;
    dynamic_slots pg_catalog.jsonb;
    slot_receipts pg_catalog.jsonb;
    expected_manifest pg_catalog.jsonb;
    canonical_manifest TEXT;
    derived_status TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'collection cycles are immutable and cannot be deleted'
            USING ERRCODE = '23514';
    END IF;

    IF TG_OP = 'INSERT' THEN
        identity := NEW.identity_json::pg_catalog.jsonb;
        IF NEW.status IS DISTINCT FROM 'running'
           OR NEW.completed_utc IS NOT NULL
           OR NEW.manifest_id IS NOT NULL
           OR NEW.manifest_json IS NOT NULL THEN
            RAISE EXCEPTION 'collection cycles must start as running'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.collector_build_id IS NULL
           OR NEW.collector_build_id !~ '^build_[0-9a-f]{24}$' THEN
            RAISE EXCEPTION 'collection cycles require a canonical collector build identity'
                USING ERRCODE = '23514';
        END IF;
        NEW.server_started_utc := pg_catalog.date_part(
            'epoch', pg_catalog.clock_timestamp()
        );
        NEW.server_terminal_utc := NULL;
        IF NEW.collection_cycle_id IS DISTINCT FROM (
            'cycle_' || pg_catalog.substr(pg_catalog.encode(
                pg_catalog.sha256(pg_catalog.convert_to(NEW.identity_json, 'UTF8')),
                'hex'
            ), 1, 24)
        ) THEN
            RAISE EXCEPTION 'collection cycle identity is not content-addressed'
                USING ERRCODE = '23514';
        END IF;
        IF (SELECT pg_catalog.array_agg(key ORDER BY key)
            FROM pg_catalog.jsonb_object_keys(identity) AS key)
                IS DISTINCT FROM ARRAY[
                    'collector_semantics_id', 'cycle_kind', 'expected_static_slots',
                    'max_dynamic_slots', 'period_key', 'protocol_id', 'schema_version'
                ]::TEXT[]
           OR identity->>'schema_version' IS DISTINCT FROM '1'
           OR identity->>'cycle_kind' IS DISTINCT FROM NEW.cycle_kind
           OR identity->>'period_key' IS DISTINCT FROM NEW.period_key
           OR identity->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
           OR identity->>'collector_semantics_id'
                IS DISTINCT FROM NEW.collector_semantics_id
           OR NEW.cycle_kind !~ '^[a-z0-9][a-z0-9-]{0,63}$'
           OR NEW.period_key = ''
           OR NEW.protocol_id = ''
           OR NEW.collector_semantics_id = ''
           OR pg_catalog.jsonb_typeof(identity->'expected_static_slots') <> 'array'
           OR pg_catalog.jsonb_array_length(identity->'expected_static_slots') = 0
           OR pg_catalog.jsonb_array_length(identity->'expected_static_slots') > 100
           OR pg_catalog.jsonb_typeof(identity->'max_dynamic_slots') <> 'number'
           OR identity->>'max_dynamic_slots' !~ '^[0-9]+$'
           OR (identity->>'max_dynamic_slots')::INTEGER > 100
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.jsonb_array_elements(
                    identity->'expected_static_slots'
                ) AS slot
                WHERE pg_catalog.jsonb_typeof(slot) <> 'object'
                   OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                       FROM pg_catalog.jsonb_object_keys(slot) AS key)
                        IS DISTINCT FROM ARRAY['provider', 'query_key']::TEXT[]
                   OR slot->>'provider' IS NULL OR slot->>'provider' = ''
                   OR slot->>'query_key' IS NULL OR slot->>'query_key' = ''
                   OR pg_catalog.octet_length(slot->>'provider') > 64
                   OR pg_catalog.octet_length(slot->>'query_key') > 2048
           )
           OR identity->'expected_static_slots' IS DISTINCT FROM (
                SELECT pg_catalog.jsonb_agg(
                    slot ORDER BY
                        (slot->>'provider') COLLATE "C",
                        (slot->>'query_key') COLLATE "C"
                )
                FROM pg_catalog.jsonb_array_elements(
                    identity->'expected_static_slots'
                ) AS slot
           )
           OR pg_catalog.jsonb_array_length(identity->'expected_static_slots')
                IS DISTINCT FROM (
                    SELECT pg_catalog.count(DISTINCT (
                        slot->>'provider', slot->>'query_key'
                    ))
                    FROM pg_catalog.jsonb_array_elements(
                        identity->'expected_static_slots'
                    ) AS slot
                ) THEN
            RAISE EXCEPTION 'collection cycle identity has an invalid canonical shape'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status IS DISTINCT FROM 'running' THEN
        RAISE EXCEPTION 'terminal collection cycles are immutable'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status NOT IN ('complete', 'incomplete')
       OR NEW.completed_utc IS NULL
       OR NEW.completed_utc < OLD.started_utc THEN
        RAISE EXCEPTION 'collection cycle completion is malformed'
            USING ERRCODE = '23514';
    END IF;
    NEW.server_started_utc := OLD.server_started_utc;
    NEW.collector_build_id := OLD.collector_build_id;
    NEW.server_terminal_utc := pg_catalog.date_part(
        'epoch', pg_catalog.clock_timestamp()
    );
    IF (pg_catalog.to_jsonb(NEW) - ARRAY[
            'status', 'completed_utc', 'manifest_id', 'manifest_json',
            'server_terminal_utc'
        ]::TEXT[])
       IS DISTINCT FROM (pg_catalog.to_jsonb(OLD) - ARRAY[
            'status', 'completed_utc', 'manifest_id', 'manifest_json',
            'server_terminal_utc'
        ]::TEXT[]) THEN
        RAISE EXCEPTION 'collection cycle completion changed an immutable field'
            USING ERRCODE = '23514';
    END IF;

    identity := OLD.identity_json::pg_catalog.jsonb;
    SELECT
        COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'provider', provider, 'query_key', query_key
            ) ORDER BY provider COLLATE "C", query_key COLLATE "C"
        ) FILTER (WHERE slot_kind = 'static'), '[]'::pg_catalog.jsonb),
        COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'provider', provider, 'query_key', query_key
            ) ORDER BY provider COLLATE "C", query_key COLLATE "C"
        ) FILTER (WHERE slot_kind = 'dynamic'), '[]'::pg_catalog.jsonb)
    INTO static_slots, dynamic_slots
    FROM public.collection_cycle_slots
    WHERE collection_cycle_id = OLD.collection_cycle_id;

    SELECT COALESCE(pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
            'slot_kind', slot.slot_kind,
            'provider', slot.provider,
            'query_key', slot.query_key,
            'fetch_run_id', run.fetch_run_id,
            'status', COALESCE(run.status, 'missing'),
            'item_count', run.item_count,
            'raw_content_ids', COALESCE(
                lineage.raw_content_ids, '[]'::pg_catalog.jsonb
            )
        ) ORDER BY
            CASE slot.slot_kind WHEN 'static' THEN 0 ELSE 1 END,
            slot.provider COLLATE "C",
            slot.query_key COLLATE "C"
    ), '[]'::pg_catalog.jsonb)
    INTO slot_receipts
    FROM public.collection_cycle_slots AS slot
    LEFT JOIN public.fetch_runs AS run
      ON run.collection_cycle_id = slot.collection_cycle_id
     AND run.provider = slot.provider
     AND run.query_key = slot.query_key
    LEFT JOIN LATERAL (
        SELECT pg_catalog.jsonb_agg(
            item.raw_content_id ORDER BY item.raw_content_id
        ) AS raw_content_ids
        FROM public.fetch_run_items AS item
        WHERE item.fetch_run_id = run.fetch_run_id
    ) AS lineage ON TRUE
    WHERE slot.collection_cycle_id = OLD.collection_cycle_id;

    IF EXISTS (
        SELECT 1 FROM public.fetch_runs
        WHERE collection_cycle_id = OLD.collection_cycle_id
          AND status = 'running'
    ) THEN
        RAISE EXCEPTION 'collection cycle cannot finish while a child receipt is running'
            USING ERRCODE = '23514';
    END IF;

    derived_status := CASE WHEN EXISTS (
        SELECT 1
        FROM public.collection_cycle_slots AS slot
        LEFT JOIN public.fetch_runs AS run
          ON run.collection_cycle_id = slot.collection_cycle_id
         AND run.provider = slot.provider
         AND run.query_key = slot.query_key
        WHERE slot.collection_cycle_id = OLD.collection_cycle_id
          AND COALESCE(run.status, 'missing') NOT IN ('success', 'empty')
    ) THEN 'incomplete' ELSE 'complete' END;

    expected_manifest := pg_catalog.jsonb_build_object(
        'schema_version', 2,
        'collection_cycle_id', OLD.collection_cycle_id,
        'cycle_kind', OLD.cycle_kind,
        'period_key', OLD.period_key,
        'protocol_id', OLD.protocol_id,
        'collector_semantics_id', OLD.collector_semantics_id,
        'collector_build_id', OLD.collector_build_id,
        'started_utc', OLD.started_utc,
        'completed_utc', NEW.completed_utc,
        'server_started_utc', OLD.server_started_utc,
        'server_terminal_utc', NEW.server_terminal_utc,
        'status', derived_status,
        'expected_static_slots', static_slots,
        'expected_dynamic_slots', dynamic_slots,
        'slot_receipts', slot_receipts
    );
    IF static_slots IS DISTINCT FROM identity->'expected_static_slots'
       OR pg_catalog.jsonb_array_length(dynamic_slots) >
            (identity->>'max_dynamic_slots')::INTEGER
       OR NEW.status IS DISTINCT FROM derived_status THEN
        RAISE EXCEPTION 'collection cycle terminal state differs from stored receipts'
            USING ERRCODE = '23514';
    END IF;
    canonical_manifest := public.canonical_jsonb_text(expected_manifest);
    NEW.manifest_json := canonical_manifest;
    NEW.manifest_id := 'cycle_manifest_' || pg_catalog.substr(pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(canonical_manifest, 'UTF8')),
        'hex'
    ), 1, 24);
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_collection_cycle_lifecycle() IS
    'tradingagents.collection-cycle-lifecycle.v2;normalized-prosrc-sha256=ba161044134abafec2cc38b27ee790d1772a8ac68857d54158f1237a79c7cab8';

DROP TRIGGER IF EXISTS immutable_collection_cycles ON public.collection_cycles;
CREATE TRIGGER immutable_collection_cycles
    BEFORE INSERT OR UPDATE OR DELETE ON public.collection_cycles
    FOR EACH ROW EXECUTE FUNCTION public.enforce_collection_cycle_lifecycle();

CREATE OR REPLACE FUNCTION public.enforce_fetch_run_cycle_binding()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    parent_status TEXT;
    parent_server_started_utc DOUBLE PRECISION;
    parent_build_id TEXT;
BEGIN
    IF NEW.collection_cycle_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT status, server_started_utc, collector_build_id
    INTO parent_status, parent_server_started_utc, parent_build_id
    FROM public.collection_cycles
    WHERE collection_cycle_id = NEW.collection_cycle_id
    FOR KEY SHARE;
    IF NOT FOUND
       OR parent_status IS DISTINCT FROM 'running'
       OR NEW.server_started_utc < parent_server_started_utc
       OR NEW.collector_build_id IS DISTINCT FROM parent_build_id
       OR NOT EXISTS (
            SELECT 1 FROM public.collection_cycle_slots
            WHERE collection_cycle_id = NEW.collection_cycle_id
              AND provider = NEW.provider
              AND query_key = NEW.query_key
       ) THEN
        RAISE EXCEPTION 'fetch receipt lacks its declared cycle slot/build identity'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_fetch_run_cycle_binding() IS
    'tradingagents.fetch-run-cycle-binding.v2;normalized-prosrc-sha256=d340d1423c67392398e9d949c0494304db608acaeb5d3f3e6275540f11cb5c1c';

DROP TRIGGER IF EXISTS validate_fetch_run_cycle_binding ON public.fetch_runs;
CREATE TRIGGER validate_fetch_run_cycle_binding
    BEFORE INSERT ON public.fetch_runs
    FOR EACH ROW EXECUTE FUNCTION public.enforce_fetch_run_cycle_binding();

CREATE INDEX IF NOT EXISTS idx_fetch_query_server_time
    ON public.fetch_runs (
        provider, query_key, server_started_utc DESC, server_terminal_utc DESC
    );

ALTER TABLE public.fetch_runs
    VALIDATE CONSTRAINT fetch_runs_server_observation_shape;

COMMIT;
