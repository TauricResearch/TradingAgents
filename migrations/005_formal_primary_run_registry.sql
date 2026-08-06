-- Select one and only one primary confirmatory run for each immutable protocol.
--
-- Apply while both runtimes are paused.  The application also takes the same
-- protocol-scoped transaction advisory lock before registration; the database
-- uniqueness constraints are the final concurrency backstop.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

CREATE TABLE IF NOT EXISTS public.formal_trial_registry (
    protocol_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    registration_id TEXT NOT NULL,
    created_utc DOUBLE PRECISION NOT NULL,
    details_json TEXT NOT NULL,
    CONSTRAINT formal_trial_registry_pkey PRIMARY KEY (protocol_id),
    CONSTRAINT formal_trial_registry_run_id_key UNIQUE (run_id),
    CONSTRAINT formal_trial_registry_registration_id_key UNIQUE (registration_id)
);

-- Fail closed if a shadow/precreated table caused CREATE IF NOT EXISTS to skip
-- any of the exact uniqueness constraints.
DO $$
DECLARE
    valid_constraints INTEGER;
BEGIN
    SELECT count(*)
    INTO valid_constraints
    FROM (
        SELECT constraint_row.contype,
               array_agg(attribute.attname ORDER BY key_column.ordinality) AS columns
        FROM pg_catalog.pg_constraint AS constraint_row
        CROSS JOIN LATERAL unnest(constraint_row.conkey)
            WITH ORDINALITY AS key_column(attribute_number, ordinality)
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = constraint_row.conrelid
         AND attribute.attnum = key_column.attribute_number
        WHERE constraint_row.conrelid =
            'public.formal_trial_registry'::pg_catalog.regclass
          AND constraint_row.contype IN ('p', 'u')
        GROUP BY constraint_row.oid, constraint_row.contype
    ) AS installed
    WHERE (installed.contype = 'p' AND installed.columns = ARRAY['protocol_id']::name[])
       OR (installed.contype = 'u' AND installed.columns = ARRAY['run_id']::name[])
       OR (installed.contype = 'u'
           AND installed.columns = ARRAY['registration_id']::name[]);

    IF valid_constraints <> 3 THEN
        RAISE EXCEPTION 'formal primary-run uniqueness constraints are incomplete';
    END IF;
END
$$;

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

DROP TRIGGER IF EXISTS immutable_formal_trial_registry
    ON public.formal_trial_registry;
CREATE TRIGGER immutable_formal_trial_registry
    BEFORE UPDATE OR DELETE ON public.formal_trial_registry
    FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation();

-- Validate a new registry row against immutable run configuration and detect
-- any earlier same-protocol activity or outcome-access receipt.  The asserted
-- JSON flag in a registration document is never treated as evidence.
CREATE OR REPLACE FUNCTION public.enforce_formal_trial_registry_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    registration JSONB;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'tradingagents:formal-protocol:' || NEW.protocol_id,
            0
        )
    );
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;

    registration := NEW.details_json::jsonb;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2'
       OR run_config ->> 'protocol_id' IS DISTINCT FROM NEW.protocol_id
       OR registration ->> 'protocol_id' IS DISTINCT FROM NEW.protocol_id
       OR COALESCE(registration ->> 'run_id', NEW.run_id) IS DISTINCT FROM NEW.run_id
       OR COALESCE(registration ->> 'registration_type', 'confirmatory')
            IS DISTINCT FROM 'confirmatory'
       OR COALESCE(registration ->> 'registration_id', NEW.registration_id)
            IS DISTINCT FROM NEW.registration_id
       OR COALESCE(registration ->> 'outcomes_accessed_before_registration', 'false')
            IS DISTINCT FROM 'false'
       OR COALESCE(run_config ->> 'trial_registration_id', NEW.registration_id)
            IS DISTINCT FROM NEW.registration_id THEN
        RAISE EXCEPTION 'formal primary registration identity is inconsistent'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.paper_runs AS protocol_run
        JOIN public.paper_run_labels AS label
          ON label.run_id = protocol_run.run_id
        WHERE protocol_run.config_json::jsonb ->> 'engine' = 'formal-global-v2'
          AND protocol_run.config_json::jsonb ->> 'protocol_id' = NEW.protocol_id
          AND label.label = 'confirmatory-trial'
          AND (
              label.run_id IS DISTINCT FROM NEW.run_id
              OR label.details_json IS DISTINCT FROM NEW.details_json
              OR label.created_utc IS DISTINCT FROM NEW.created_utc
          )
    ) THEN
        RAISE EXCEPTION 'another same-protocol run was already labeled confirmatory'
            USING ERRCODE = '23505';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.paper_runs AS protocol_run
        WHERE protocol_run.config_json::jsonb ->> 'engine' = 'formal-global-v2'
          AND protocol_run.config_json::jsonb ->> 'protocol_id' = NEW.protocol_id
          AND (
              EXISTS (SELECT 1 FROM public.paper_decisions AS row
                      WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_decision_bundles AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_events AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_forecasts AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_targets AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_strategy_targets AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_marks AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_strategy_marks AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_price_receipts AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_decision_attempt_events AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_interval_assignments AS row
                         WHERE row.run_id = protocol_run.run_id)
              OR EXISTS (
                  SELECT 1 FROM public.paper_run_labels AS label
                  WHERE label.run_id = protocol_run.run_id
                    AND label.label <> 'confirmatory-trial'
              )
              OR EXISTS (
                  SELECT 1 FROM public.paper_artifacts AS artifact
                  WHERE artifact.content_json::jsonb ->> 'run_id' = protocol_run.run_id
              )
          )
    ) THEN
        RAISE EXCEPTION 'same-protocol activity predates primary registration'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal primary registration references an unknown run'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_trial_registry_insert() IS
    'tradingagents.formal-primary-registry-insert.v1;normalized-prosrc-sha256=0328846a8f4ec182bf55ce0850a6c0b80c80ea9bd7afe0550e4b1b7d99494009';

DROP TRIGGER IF EXISTS validate_formal_trial_registry_insert
    ON public.formal_trial_registry;
CREATE TRIGGER validate_formal_trial_registry_insert
    BEFORE INSERT ON public.formal_trial_registry
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_trial_registry_insert();

-- Every formal run-scoped insert must belong to the registered primary.  This
-- closes the race between legacy-activity inspection and registry insertion
-- even for a direct SQL write using the runtime credential.
CREATE OR REPLACE FUNCTION public.enforce_formal_primary_run_activity()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
BEGIN
    SELECT run.config_json::jsonb
      INTO run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' = 'formal-global-v2'
       AND NOT EXISTS (
           SELECT 1
           FROM public.formal_trial_registry AS registry
           WHERE registry.run_id = NEW.run_id
             AND registry.protocol_id = run_config ->> 'protocol_id'
       ) THEN
        RAISE EXCEPTION 'formal activity requires the registered primary run'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_primary_run_activity() IS
    'tradingagents.formal-primary-run-activity.v1;normalized-prosrc-sha256=6e334ab1ee2217b262744505279a8b0da361128eed4e327c7605a70de547bf2e';

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_decisions', 'paper_decision_bundles', 'paper_events',
        'paper_forecasts', 'paper_targets', 'paper_strategy_targets',
        'paper_marks', 'paper_strategy_marks', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS require_formal_primary_run ON public.%I',
            table_name
        );
        EXECUTE format(
            'CREATE TRIGGER require_formal_primary_run BEFORE INSERT ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_primary_run_activity()',
            table_name
        );
    END LOOP;
END
$$;

CREATE OR REPLACE FUNCTION public.enforce_formal_artifact_primary_run()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    artifact_run_id TEXT;
    run_config JSONB;
BEGIN
    artifact_run_id := NEW.content_json::jsonb ->> 'run_id';
    IF artifact_run_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT run.config_json::jsonb
      INTO run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = artifact_run_id;
    IF run_config ->> 'engine' = 'formal-global-v2'
       AND NOT EXISTS (
           SELECT 1
           FROM public.formal_trial_registry AS registry
           WHERE registry.run_id = artifact_run_id
             AND registry.protocol_id = run_config ->> 'protocol_id'
       ) THEN
        RAISE EXCEPTION 'formal artifact requires the registered primary run'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_artifact_primary_run() IS
    'tradingagents.formal-primary-artifact.v1;normalized-prosrc-sha256=cfa9ec896396a6bd8d049471594500cb886e696d8628db36f98ac3b93ea59255';

DROP TRIGGER IF EXISTS require_formal_primary_run
    ON public.paper_artifacts;
CREATE TRIGGER require_formal_primary_run
    BEFORE INSERT ON public.paper_artifacts
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_artifact_primary_run();

CREATE OR REPLACE FUNCTION public.enforce_formal_run_label()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    registry public.formal_trial_registry%ROWTYPE;
BEGIN
    SELECT run.config_json::jsonb
      INTO run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    SELECT registered.*
      INTO registry
      FROM public.formal_trial_registry AS registered
     WHERE registered.run_id = NEW.run_id
       AND registered.protocol_id = run_config ->> 'protocol_id';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'formal label requires the registered primary run'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.label = 'confirmatory-trial'
       AND (
           NEW.details_json IS DISTINCT FROM registry.details_json
           OR NEW.created_utc IS DISTINCT FROM registry.created_utc
       ) THEN
        RAISE EXCEPTION 'confirmatory label differs from primary registry'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_run_label() IS
    'tradingagents.formal-primary-run-label.v1;normalized-prosrc-sha256=05dbd7df121d2a2a565329653acfd0f7bd6e6cd9108ff83006af0e95ebfa384c';

DROP TRIGGER IF EXISTS guard_confirmatory_run_label
    ON public.paper_run_labels;
CREATE TRIGGER guard_confirmatory_run_label
    BEFORE INSERT ON public.paper_run_labels
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_run_label();

COMMENT ON TABLE public.formal_trial_registry IS
    'tradingagents.formal-primary-run.v1; one immutable primary run per protocol';

REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_trial_registry_insert() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_primary_run_activity() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_artifact_primary_run() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_run_label() FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-paper'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry
            FROM "tradingagents-paper";
        GRANT SELECT, INSERT ON TABLE public.formal_trial_registry
            TO "tradingagents-paper";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-ingest-v2'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry
            FROM "tradingagents-ingest-v2";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-ingest'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry
            FROM "tradingagents-ingest";
    END IF;
END
$$;

COMMIT;
