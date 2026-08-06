-- Immutable, content-addressed collection-cycle manifests.
--
-- Migration 007 binds each X daily collection attempt to a parent known before
-- any request. Migration 008 is reserved for market-outcome capture.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

-- Pause both workers. A request started without the cycle-binding trigger must
-- not be allowed to acquire a parent retroactively.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.fetch_runs WHERE status = 'running') THEN
        RAISE EXCEPTION
            'collection-cycle migration requires zero running fetch receipts';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS public.collection_cycles (
    collection_cycle_id TEXT NOT NULL,
    cycle_kind TEXT NOT NULL,
    period_key TEXT NOT NULL,
    protocol_id TEXT NOT NULL,
    collector_semantics_id TEXT NOT NULL,
    identity_json TEXT NOT NULL,
    started_utc DOUBLE PRECISION NOT NULL,
    completed_utc DOUBLE PRECISION,
    status TEXT NOT NULL,
    manifest_id TEXT,
    manifest_json TEXT
);

CREATE TABLE IF NOT EXISTS public.collection_cycle_slots (
    collection_cycle_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    query_key TEXT NOT NULL,
    slot_kind TEXT NOT NULL,
    declared_utc DOUBLE PRECISION NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'collection_cycles_pkey'
          AND conrelid = 'public.collection_cycles'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.collection_cycles
            ADD CONSTRAINT collection_cycles_pkey
            PRIMARY KEY (collection_cycle_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'collection_cycle_slots_pkey'
          AND conrelid = 'public.collection_cycle_slots'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.collection_cycle_slots
            ADD CONSTRAINT collection_cycle_slots_pkey
            PRIMARY KEY (collection_cycle_id, provider, query_key);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'collection_cycle_slots_cycle_fk'
          AND conrelid = 'public.collection_cycle_slots'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.collection_cycle_slots
            ADD CONSTRAINT collection_cycle_slots_cycle_fk
            FOREIGN KEY (collection_cycle_id)
            REFERENCES public.collection_cycles(collection_cycle_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_runs_collection_cycle_fk'
          AND conrelid = 'public.fetch_runs'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_runs
            ADD CONSTRAINT fetch_runs_collection_cycle_fk
            FOREIGN KEY (collection_cycle_id)
            REFERENCES public.collection_cycles(collection_cycle_id)
            NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = 'fetch_runs_cycle_slot_unique'
          AND conrelid = 'public.fetch_runs'::pg_catalog.regclass
    ) THEN
        ALTER TABLE public.fetch_runs
            ADD CONSTRAINT fetch_runs_cycle_slot_unique
            UNIQUE (collection_cycle_id, provider, query_key);
    END IF;
END
$$;

ALTER TABLE public.collection_cycles
    DROP CONSTRAINT IF EXISTS collection_cycles_id_format;
ALTER TABLE public.collection_cycles
    ADD CONSTRAINT collection_cycles_id_format
    CHECK (collection_cycle_id ~ '^cycle_[0-9a-f]{24}$');

ALTER TABLE public.collection_cycles
    DROP CONSTRAINT IF EXISTS collection_cycles_manifest_id_format;
ALTER TABLE public.collection_cycles
    ADD CONSTRAINT collection_cycles_manifest_id_format
    CHECK (
        manifest_id IS NULL
        OR manifest_id ~ '^cycle_manifest_[0-9a-f]{24}$'
    );

ALTER TABLE public.collection_cycles
    DROP CONSTRAINT IF EXISTS collection_cycles_status_valid;
ALTER TABLE public.collection_cycles
    ADD CONSTRAINT collection_cycles_status_valid
    CHECK (status IN ('running', 'complete', 'incomplete'));

ALTER TABLE public.collection_cycles
    DROP CONSTRAINT IF EXISTS collection_cycles_terminal_shape;
ALTER TABLE public.collection_cycles
    ADD CONSTRAINT collection_cycles_terminal_shape
    CHECK (
        (
            status = 'running'
            AND completed_utc IS NULL
            AND manifest_id IS NULL
            AND manifest_json IS NULL
        )
        OR (
            status IN ('complete', 'incomplete')
            AND completed_utc IS NOT NULL
            AND manifest_id IS NOT NULL
            AND manifest_json IS NOT NULL
        )
    );

ALTER TABLE public.collection_cycles
    DROP CONSTRAINT IF EXISTS collection_cycles_times_finite;
ALTER TABLE public.collection_cycles
    ADD CONSTRAINT collection_cycles_times_finite
    CHECK (
        started_utc > '-Infinity'::DOUBLE PRECISION
        AND started_utc < 'Infinity'::DOUBLE PRECISION
        AND (
            completed_utc IS NULL
            OR (
                completed_utc >= started_utc
                AND completed_utc > '-Infinity'::DOUBLE PRECISION
                AND completed_utc < 'Infinity'::DOUBLE PRECISION
            )
        )
    );

ALTER TABLE public.collection_cycle_slots
    DROP CONSTRAINT IF EXISTS collection_cycle_slots_kind_valid;
ALTER TABLE public.collection_cycle_slots
    ADD CONSTRAINT collection_cycle_slots_kind_valid
    CHECK (slot_kind IN ('static', 'dynamic'));

ALTER TABLE public.collection_cycle_slots
    DROP CONSTRAINT IF EXISTS collection_cycle_slots_fields_valid;
ALTER TABLE public.collection_cycle_slots
    ADD CONSTRAINT collection_cycle_slots_fields_valid
    CHECK (
        provider <> ''
        AND pg_catalog.octet_length(provider) <= 64
        AND query_key <> ''
        AND pg_catalog.octet_length(query_key) <= 2048
        AND declared_utc > '-Infinity'::DOUBLE PRECISION
        AND declared_utc < 'Infinity'::DOUBLE PRECISION
    );

CREATE OR REPLACE FUNCTION public.enforce_collection_cycle_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    identity pg_catalog.jsonb;
    manifest pg_catalog.jsonb;
    static_slots pg_catalog.jsonb;
    dynamic_slots pg_catalog.jsonb;
    slot_receipts pg_catalog.jsonb;
    expected_manifest pg_catalog.jsonb;
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
       OR NEW.completed_utc < OLD.started_utc
       OR NEW.manifest_id IS NULL
       OR NEW.manifest_json IS NULL THEN
        RAISE EXCEPTION 'collection cycle completion is malformed'
            USING ERRCODE = '23514';
    END IF;
    IF (pg_catalog.to_jsonb(NEW) - ARRAY[
            'status', 'completed_utc', 'manifest_id', 'manifest_json'
        ]::TEXT[])
       IS DISTINCT FROM (pg_catalog.to_jsonb(OLD) - ARRAY[
            'status', 'completed_utc', 'manifest_id', 'manifest_json'
        ]::TEXT[]) THEN
        RAISE EXCEPTION 'collection cycle completion changed an immutable field'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.manifest_id IS DISTINCT FROM (
        'cycle_manifest_' || pg_catalog.substr(pg_catalog.encode(
            pg_catalog.sha256(pg_catalog.convert_to(NEW.manifest_json, 'UTF8')),
            'hex'
        ), 1, 24)
    ) THEN
        RAISE EXCEPTION 'collection cycle manifest is not content-addressed'
            USING ERRCODE = '23514';
    END IF;

    identity := OLD.identity_json::pg_catalog.jsonb;
    manifest := NEW.manifest_json::pg_catalog.jsonb;
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
        'schema_version', 1,
        'collection_cycle_id', OLD.collection_cycle_id,
        'cycle_kind', OLD.cycle_kind,
        'period_key', OLD.period_key,
        'protocol_id', OLD.protocol_id,
        'collector_semantics_id', OLD.collector_semantics_id,
        'started_utc', OLD.started_utc,
        'completed_utc', NEW.completed_utc,
        'status', derived_status,
        'expected_static_slots', static_slots,
        'expected_dynamic_slots', dynamic_slots,
        'slot_receipts', slot_receipts
    );
    IF static_slots IS DISTINCT FROM identity->'expected_static_slots'
       OR pg_catalog.jsonb_array_length(dynamic_slots) >
            (identity->>'max_dynamic_slots')::INTEGER
       OR NEW.status IS DISTINCT FROM derived_status
       OR manifest IS DISTINCT FROM expected_manifest THEN
        RAISE EXCEPTION 'collection cycle terminal manifest differs from stored receipts'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_collection_cycle_lifecycle() IS
    'tradingagents.collection-cycle-lifecycle.v1;normalized-prosrc-sha256=28a16fce48b86c1d988b6c59d46f9d7c3256e8450d41788c0910b1250512e3d5';

DROP TRIGGER IF EXISTS immutable_collection_cycles ON public.collection_cycles;
CREATE TRIGGER immutable_collection_cycles
    BEFORE INSERT OR UPDATE OR DELETE ON public.collection_cycles
    FOR EACH ROW EXECUTE FUNCTION public.enforce_collection_cycle_lifecycle();

CREATE OR REPLACE FUNCTION public.enforce_collection_cycle_slot_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    parent public.collection_cycles%ROWTYPE;
    identity pg_catalog.jsonb;
    dynamic_count BIGINT;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        RAISE EXCEPTION 'collection cycle slots are append-only'
            USING ERRCODE = '55000';
    END IF;
    SELECT * INTO parent
    FROM public.collection_cycles
    WHERE collection_cycle_id = NEW.collection_cycle_id
    FOR UPDATE;
    IF NOT FOUND OR parent.status IS DISTINCT FROM 'running'
       OR NEW.declared_utc < parent.started_utc THEN
        RAISE EXCEPTION 'collection cycle slot lacks a matching running parent'
            USING ERRCODE = '23514';
    END IF;
    identity := parent.identity_json::pg_catalog.jsonb;
    IF NEW.slot_kind = 'static' THEN
        IF NOT (identity->'expected_static_slots') @>
            pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
                'provider', NEW.provider, 'query_key', NEW.query_key
            )) THEN
            RAISE EXCEPTION 'static collection slot is absent from the cycle identity'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.slot_kind = 'dynamic' THEN
        SELECT pg_catalog.count(*) INTO dynamic_count
        FROM public.collection_cycle_slots
        WHERE collection_cycle_id = NEW.collection_cycle_id
          AND slot_kind = 'dynamic';
        IF dynamic_count >= (identity->>'max_dynamic_slots')::INTEGER THEN
            RAISE EXCEPTION 'collection cycle exceeded its dynamic-slot cap'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        RAISE EXCEPTION 'collection cycle slot kind is invalid'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_collection_cycle_slot_lifecycle() IS
    'tradingagents.collection-cycle-slot-lifecycle.v1;normalized-prosrc-sha256=e64e3c6c91b954edc370fae0db4d2b6f585935c134389f8a7f3d1e4f578dfce4';

DROP TRIGGER IF EXISTS immutable_collection_cycle_slots
    ON public.collection_cycle_slots;
CREATE TRIGGER immutable_collection_cycle_slots
    BEFORE INSERT OR UPDATE OR DELETE ON public.collection_cycle_slots
    FOR EACH ROW EXECUTE FUNCTION public.enforce_collection_cycle_slot_lifecycle();

CREATE OR REPLACE FUNCTION public.enforce_fetch_run_cycle_binding()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    parent_status TEXT;
    parent_started_utc DOUBLE PRECISION;
BEGIN
    IF NEW.collection_cycle_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT status, started_utc
    INTO parent_status, parent_started_utc
    FROM public.collection_cycles
    WHERE collection_cycle_id = NEW.collection_cycle_id
    FOR KEY SHARE;
    IF NOT FOUND
       OR parent_status IS DISTINCT FROM 'running'
       OR NEW.started_utc < parent_started_utc
       OR NOT EXISTS (
            SELECT 1 FROM public.collection_cycle_slots
            WHERE collection_cycle_id = NEW.collection_cycle_id
              AND provider = NEW.provider
              AND query_key = NEW.query_key
       ) THEN
        RAISE EXCEPTION 'fetch receipt lacks a declared running cycle slot'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_fetch_run_cycle_binding() IS
    'tradingagents.fetch-run-cycle-binding.v1;normalized-prosrc-sha256=367b093a528d434959b09b6a2fa369f773dbd4d9f1f8fe99ca9dfdac1dac2e52';

DROP TRIGGER IF EXISTS validate_fetch_run_cycle_binding ON public.fetch_runs;
CREATE TRIGGER validate_fetch_run_cycle_binding
    BEFORE INSERT ON public.fetch_runs
    FOR EACH ROW EXECUTE FUNCTION public.enforce_fetch_run_cycle_binding();

ALTER TABLE public.fetch_runs
    VALIDATE CONSTRAINT fetch_runs_collection_cycle_fk;

REVOKE ALL PRIVILEGES ON TABLE public.collection_cycles FROM PUBLIC;
REVOKE ALL PRIVILEGES ON TABLE public.collection_cycle_slots FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-ingest-v2'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.collection_cycles
            FROM "tradingagents-ingest-v2";
        REVOKE ALL PRIVILEGES ON TABLE public.collection_cycle_slots
            FROM "tradingagents-ingest-v2";
        GRANT SELECT, INSERT, UPDATE ON TABLE public.collection_cycles
            TO "tradingagents-ingest-v2";
        GRANT SELECT, INSERT ON TABLE public.collection_cycle_slots
            TO "tradingagents-ingest-v2";
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-paper'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.collection_cycles
            FROM "tradingagents-paper";
        REVOKE ALL PRIVILEGES ON TABLE public.collection_cycle_slots
            FROM "tradingagents-paper";
        GRANT SELECT ON TABLE public.collection_cycles
            TO "tradingagents-paper";
        GRANT SELECT ON TABLE public.collection_cycle_slots
            TO "tradingagents-paper";
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'tradingagents-ingest'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.collection_cycles
            FROM "tradingagents-ingest";
        REVOKE ALL PRIVILEGES ON TABLE public.collection_cycle_slots
            FROM "tradingagents-ingest";
    END IF;
END
$$;

COMMIT;
