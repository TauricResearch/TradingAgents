-- Durable, image-bound activation for the formal confirmatory trial.
--
-- Apply as schema administrator while collector and paper runtimes are paused.
-- A worker environment flag can pause activity but can never create authority:
-- only an append-only administrator record tied to exact release receipts,
-- container tags/digests, runtime configurations, and outcome semantics can do
-- so. Release receipts must be inserted before the authorization and cannot be
-- added or replaced afterward.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

CREATE TABLE IF NOT EXISTS public.formal_release_receipts (
    receipt_id TEXT PRIMARY KEY,
    receipt_type TEXT NOT NULL,
    protocol_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_utc DOUBLE PRECISION NOT NULL,
    content_json TEXT NOT NULL,
    UNIQUE (protocol_id, run_id, receipt_type),
    CHECK (receipt_id ~ '^release_[0-9a-f]{24}$'),
    CHECK (receipt_type IN (
        'configuration', 'collector_preflight',
        'paper_decision_preflight', 'paper_marker_preflight',
        'restore_rehearsal', 'alert_delivery', 'runtime_role_decommission'
    )),
    CHECK (created_utc > '-Infinity'::DOUBLE PRECISION),
    CHECK (created_utc < 'Infinity'::DOUBLE PRECISION)
);

CREATE TABLE IF NOT EXISTS public.formal_trial_authorizations (
    protocol_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    registration_id TEXT NOT NULL UNIQUE,
    authorization_id TEXT NOT NULL UNIQUE,
    authorized_utc DOUBLE PRECISION NOT NULL,
    outcome_semantics_id TEXT NOT NULL,
    configuration_manifest_id TEXT NOT NULL,
    collector_configuration_id TEXT NOT NULL,
    paper_decision_configuration_id TEXT NOT NULL,
    paper_marker_configuration_id TEXT NOT NULL,
    collector_build_id TEXT NOT NULL,
    paper_decision_build_id TEXT NOT NULL,
    paper_marker_build_id TEXT NOT NULL,
    authorization_json TEXT NOT NULL,
    CHECK (authorization_id ~ '^activation_[0-9a-f]{24}$'),
    CHECK (registration_id ~ '^registration_[0-9a-f]{24}$'),
    CHECK (outcome_semantics_id ~ '^outcome_semantics_[0-9a-f]{64}$'),
    CHECK (configuration_manifest_id ~ '^config_[0-9a-f]{24}$'),
    CHECK (collector_configuration_id ~ '^config_[0-9a-f]{24}$'),
    CHECK (paper_decision_configuration_id ~ '^config_[0-9a-f]{24}$'),
    CHECK (paper_marker_configuration_id ~ '^config_[0-9a-f]{24}$'),
    CHECK (collector_build_id ~ '^build_[0-9a-f]{24}$'),
    CHECK (paper_decision_build_id ~ '^build_[0-9a-f]{24}$'),
    CHECK (paper_marker_build_id ~ '^build_[0-9a-f]{24}$'),
    CHECK (authorized_utc > '-Infinity'::DOUBLE PRECISION),
    CHECK (authorized_utc < 'Infinity'::DOUBLE PRECISION)
);

-- CREATE IF NOT EXISTS must never accept a shadow/precreated object with a
-- weaker shape. Validate every column plus the exact primary/unique keys before
-- installing any trigger or granting runtime reads.
DO $$
DECLARE
    invalid_columns TEXT;
    valid_keys INTEGER;
    target RECORD;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('formal_release_receipts', ARRAY[
                'receipt_id:text:true:false', 'receipt_type:text:true:false',
                'protocol_id:text:true:false', 'run_id:text:true:false',
                'created_utc:double precision:true:false',
                'content_json:text:true:false'
            ]::TEXT[]),
            ('formal_trial_authorizations', ARRAY[
                'protocol_id:text:true:false', 'run_id:text:true:false',
                'registration_id:text:true:false',
                'authorization_id:text:true:false',
                'authorized_utc:double precision:true:false',
                'outcome_semantics_id:text:true:false',
                'configuration_manifest_id:text:true:false',
                'collector_configuration_id:text:true:false',
                'paper_decision_configuration_id:text:true:false',
                'paper_marker_configuration_id:text:true:false',
                'collector_build_id:text:true:false',
                'paper_decision_build_id:text:true:false',
                'paper_marker_build_id:text:true:false',
                'authorization_json:text:true:false'
            ]::TEXT[])
        ) AS expected(table_name, columns)
    LOOP
        SELECT pg_catalog.string_agg(
            attribute.attname || ':'
            || pg_catalog.format_type(attribute.atttypid, attribute.atttypmod)
            || ':' || attribute.attnotnull::TEXT
            || ':' || attribute.atthasdef::TEXT,
            ',' ORDER BY attribute.attnum
        )
        INTO invalid_columns
        FROM pg_catalog.pg_attribute AS attribute
        WHERE attribute.attrelid = (
                'public.' || target.table_name
            )::pg_catalog.regclass
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped;
        IF pg_catalog.string_to_array(invalid_columns, ',')
                IS DISTINCT FROM target.columns THEN
            RAISE EXCEPTION 'formal release table % has an invalid exact schema',
                target.table_name;
        END IF;
    END LOOP;

    SELECT pg_catalog.count(*)
      INTO valid_keys
      FROM (
        SELECT constraint_row.conrelid, constraint_row.contype,
               pg_catalog.array_agg(
                   attribute.attname ORDER BY key_column.ordinality
               ) AS columns
        FROM pg_catalog.pg_constraint AS constraint_row
        CROSS JOIN LATERAL pg_catalog.unnest(constraint_row.conkey)
            WITH ORDINALITY AS key_column(attribute_number, ordinality)
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = constraint_row.conrelid
         AND attribute.attnum = key_column.attribute_number
        WHERE constraint_row.conrelid IN (
                'public.formal_release_receipts'::pg_catalog.regclass,
                'public.formal_trial_authorizations'::pg_catalog.regclass
            )
          AND constraint_row.contype IN ('p', 'u')
        GROUP BY constraint_row.oid, constraint_row.conrelid,
                 constraint_row.contype
      ) AS installed
      WHERE (
          installed.conrelid =
              'public.formal_release_receipts'::pg_catalog.regclass
          AND (
              (installed.contype = 'p'
               AND installed.columns = ARRAY['receipt_id']::NAME[])
              OR (installed.contype = 'u'
                  AND installed.columns =
                      ARRAY['protocol_id', 'run_id', 'receipt_type']::NAME[])
          )
      ) OR (
          installed.conrelid =
              'public.formal_trial_authorizations'::pg_catalog.regclass
          AND (
              (installed.contype = 'p'
               AND installed.columns = ARRAY['protocol_id']::NAME[])
              OR (installed.contype = 'u'
                  AND installed.columns = ARRAY['run_id']::NAME[])
              OR (installed.contype = 'u'
                  AND installed.columns = ARRAY['registration_id']::NAME[])
              OR (installed.contype = 'u'
                  AND installed.columns = ARRAY['authorization_id']::NAME[])
          )
      );
    IF valid_keys <> 6 THEN
        RAISE EXCEPTION 'formal release table primary/unique keys are incomplete';
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.enforce_formal_release_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    document JSONB;
    payload JSONB;
    configuration_binding JSONB;
    configuration_manifest JSONB;
    collector_configuration JSONB;
    paper_decision_configuration JSONB;
    paper_marker_configuration JSONB;
    backup_document JSONB;
    collector_rehearsal JSONB;
    cycle_manifest JSONB;
    verification_document JSONB;
    deliveries JSONB;
    delivery JSONB;
    stored_cycle public.collection_cycles%ROWTYPE;
    expected_receipt_id TEXT;
    expected_configuration_id TEXT;
    expected_preflight_id TEXT;
    expected_content_id TEXT;
    role_name TEXT;
    backup_time DOUBLE PRECISION;
    cycle_server_time DOUBLE PRECISION;
    verification_time DOUBLE PRECISION;
    delivery_time DOUBLE PRECISION;
    server_now DOUBLE PRECISION;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'formal release receipts are append-only'
            USING ERRCODE = '55000';
    END IF;

    server_now := pg_catalog.date_part('epoch', pg_catalog.clock_timestamp());
    document := NEW.content_json::jsonb;
    payload := document->'payload';
    IF pg_catalog.jsonb_typeof(document) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(document) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'payload', 'protocol_id', 'receipt_id', 'receipt_type',
                'run_id', 'schema_version'
            ]::TEXT[]
       OR document->>'schema_version' IS DISTINCT FROM '1'
       OR document->>'receipt_id' IS DISTINCT FROM NEW.receipt_id
       OR document->>'receipt_type' IS DISTINCT FROM NEW.receipt_type
       OR document->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
       OR document->>'run_id' IS DISTINCT FROM NEW.run_id
       OR pg_catalog.jsonb_typeof(payload) IS DISTINCT FROM 'object'
       OR NEW.receipt_id !~ '^release_[0-9a-f]{24}$'
       OR NEW.protocol_id !~ '^protocol_[0-9a-f]{24}$'
       OR NEW.run_id = '' THEN
        RAISE EXCEPTION 'formal release receipt has an invalid exact schema'
            USING ERRCODE = '23514';
    END IF;

    expected_receipt_id := 'release_' || pg_catalog.substr(pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(
            public.canonical_jsonb_text(document - 'receipt_id'), 'UTF8'
        )), 'hex'
    ), 1, 24);
    IF NEW.receipt_id IS DISTINCT FROM expected_receipt_id THEN
        RAISE EXCEPTION 'formal release receipt is not content-addressed'
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.formal_trial_registry AS registry
        WHERE registry.protocol_id = NEW.protocol_id
          AND registry.run_id = NEW.run_id
    ) OR EXISTS (
        SELECT 1
        FROM public.formal_trial_authorizations AS authz
        WHERE authz.protocol_id = NEW.protocol_id
           OR authz.run_id = NEW.run_id
    ) THEN
        RAISE EXCEPTION 'release evidence requires an inactive registered primary run'
            USING ERRCODE = '23514';
    END IF;

    CASE NEW.receipt_type
        WHEN 'configuration' THEN
            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(payload) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'collector_configuration', 'configuration_binding',
                        'configuration_manifest', 'paper_decision_configuration',
                        'paper_marker_configuration'
                    ]::TEXT[] THEN
                RAISE EXCEPTION 'configuration release receipt is malformed'
                    USING ERRCODE = '23514';
            END IF;
            configuration_binding := payload->'configuration_binding';
            configuration_manifest := payload->'configuration_manifest';
            collector_configuration := payload->'collector_configuration';
            paper_decision_configuration := payload->'paper_decision_configuration';
            paper_marker_configuration := payload->'paper_marker_configuration';
            IF pg_catalog.jsonb_typeof(configuration_binding)
                    IS DISTINCT FROM 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(configuration_binding)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'collector_configuration_id', 'configuration_manifest_id',
                        'paper_decision_configuration_id',
                        'paper_marker_configuration_id'
                    ]::TEXT[]
               OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.jsonb_each_text(configuration_binding)
                        AS binding(key, value)
                    WHERE binding.value !~ '^config_[0-9a-f]{24}$'
               ) THEN
                RAISE EXCEPTION 'configuration binding is malformed'
                    USING ERRCODE = '23514';
            END IF;

            IF pg_catalog.jsonb_typeof(collector_configuration)
                    IS DISTINCT FROM 'object'
               OR pg_catalog.jsonb_typeof(paper_decision_configuration)
                    IS DISTINCT FROM 'object'
               OR pg_catalog.jsonb_typeof(paper_marker_configuration)
                    IS DISTINCT FROM 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(collector_configuration)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'configuration_id', 'configuration_type', 'protocol_id',
                        'role', 'schema_version', 'settings'
                    ]::TEXT[]
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(paper_decision_configuration)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'configuration_id', 'configuration_type', 'protocol_id',
                        'role', 'schema_version', 'settings'
                    ]::TEXT[]
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(paper_marker_configuration)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'configuration_id', 'configuration_type', 'protocol_id',
                        'role', 'schema_version', 'settings'
                    ]::TEXT[]
               OR collector_configuration->>'schema_version' IS DISTINCT FROM '1'
               OR paper_decision_configuration->>'schema_version' IS DISTINCT FROM '1'
               OR paper_marker_configuration->>'schema_version' IS DISTINCT FROM '1'
               OR collector_configuration->>'configuration_type'
                    IS DISTINCT FROM 'formal-runtime-component'
               OR paper_decision_configuration->>'configuration_type'
                    IS DISTINCT FROM 'formal-runtime-component'
               OR paper_marker_configuration->>'configuration_type'
                    IS DISTINCT FROM 'formal-runtime-component'
               OR collector_configuration->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
               OR paper_decision_configuration->>'protocol_id'
                    IS DISTINCT FROM NEW.protocol_id
               OR paper_marker_configuration->>'protocol_id'
                    IS DISTINCT FROM NEW.protocol_id
               OR paper_decision_configuration->'settings'->>'run_id'
                    IS DISTINCT FROM NEW.run_id
               OR paper_marker_configuration->'settings'->>'run_id'
                    IS DISTINCT FROM NEW.run_id
               OR collector_configuration->>'role' IS DISTINCT FROM 'collector'
               OR paper_decision_configuration->>'role'
                    IS DISTINCT FROM 'paper_decision'
               OR paper_marker_configuration->>'role'
                    IS DISTINCT FROM 'paper_marker'
               OR pg_catalog.jsonb_typeof(collector_configuration->'settings')
                    IS DISTINCT FROM 'object'
               OR pg_catalog.jsonb_typeof(paper_decision_configuration->'settings')
                    IS DISTINCT FROM 'object'
               OR pg_catalog.jsonb_typeof(paper_marker_configuration->'settings')
                    IS DISTINCT FROM 'object' THEN
                RAISE EXCEPTION 'component configuration manifest is malformed'
                    USING ERRCODE = '23514';
            END IF;
            expected_configuration_id := 'config_' || pg_catalog.substr(
                pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                    public.canonical_jsonb_text(
                        collector_configuration - 'configuration_id'
                    ), 'UTF8'
                )), 'hex'), 1, 24
            );
            IF collector_configuration->>'configuration_id'
                    IS DISTINCT FROM expected_configuration_id
               OR configuration_binding->>'collector_configuration_id'
                    IS DISTINCT FROM expected_configuration_id THEN
                RAISE EXCEPTION 'collector configuration is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
            expected_configuration_id := 'config_' || pg_catalog.substr(
                pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                    public.canonical_jsonb_text(
                        paper_decision_configuration - 'configuration_id'
                    ), 'UTF8'
                )), 'hex'), 1, 24
            );
            IF paper_decision_configuration->>'configuration_id'
                    IS DISTINCT FROM expected_configuration_id
               OR configuration_binding->>'paper_decision_configuration_id'
                    IS DISTINCT FROM expected_configuration_id THEN
                RAISE EXCEPTION 'paper decision configuration is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
            expected_configuration_id := 'config_' || pg_catalog.substr(
                pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                    public.canonical_jsonb_text(
                        paper_marker_configuration - 'configuration_id'
                    ), 'UTF8'
                )), 'hex'), 1, 24
            );
            IF paper_marker_configuration->>'configuration_id'
                    IS DISTINCT FROM expected_configuration_id
               OR configuration_binding->>'paper_marker_configuration_id'
                    IS DISTINCT FROM expected_configuration_id THEN
                RAISE EXCEPTION 'paper marker configuration is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;

            IF pg_catalog.jsonb_typeof(configuration_manifest)
                    IS DISTINCT FROM 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(configuration_manifest)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'components', 'configuration_manifest_id',
                        'configuration_type', 'protocol_id', 'schema_version'
                    ]::TEXT[]
               OR configuration_manifest->>'schema_version' IS DISTINCT FROM '1'
               OR configuration_manifest->>'configuration_type'
                    IS DISTINCT FROM 'formal-runtime-release'
               OR configuration_manifest->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
               OR configuration_manifest->'components' IS DISTINCT FROM
                    pg_catalog.jsonb_build_object(
                        'collector', collector_configuration->>'configuration_id',
                        'paper_decision',
                            paper_decision_configuration->>'configuration_id',
                        'paper_marker',
                            paper_marker_configuration->>'configuration_id'
                    ) THEN
                RAISE EXCEPTION 'combined configuration manifest is malformed'
                    USING ERRCODE = '23514';
            END IF;
            expected_configuration_id := 'config_' || pg_catalog.substr(
                pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                    public.canonical_jsonb_text(
                        configuration_manifest - 'configuration_manifest_id'
                    ), 'UTF8'
                )), 'hex'), 1, 24
            );
            IF configuration_manifest->>'configuration_manifest_id'
                    IS DISTINCT FROM expected_configuration_id
               OR configuration_binding->>'configuration_manifest_id'
                    IS DISTINCT FROM expected_configuration_id THEN
                RAISE EXCEPTION 'combined configuration is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'collector_preflight', 'paper_decision_preflight',
             'paper_marker_preflight' THEN
            IF (
                NEW.receipt_type = 'collector_preflight'
                AND (SELECT pg_catalog.array_agg(key ORDER BY key)
                     FROM pg_catalog.jsonb_object_keys(payload) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'build_id', 'component_configuration_id',
                        'preflight_manifest_id', 'role', 'runtime_ready'
                    ]::TEXT[]
            ) OR (
                NEW.receipt_type <> 'collector_preflight'
                AND (SELECT pg_catalog.array_agg(key ORDER BY key)
                     FROM pg_catalog.jsonb_object_keys(payload) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'build_id', 'component_configuration_id',
                        'outcome_semantics_id', 'preflight_manifest_id',
                        'role', 'runtime_ready'
                    ]::TEXT[]
            )
               OR payload->>'role' IS DISTINCT FROM
                    pg_catalog.replace(NEW.receipt_type, '_preflight', '')
               OR payload->'runtime_ready' IS DISTINCT FROM 'true'::jsonb
               OR payload->>'preflight_manifest_id'
                    !~ '^preflight_[0-9a-f]{24}$'
               OR payload->>'component_configuration_id'
                    !~ '^config_[0-9a-f]{24}$'
               OR (
                    NEW.receipt_type <> 'collector_preflight'
                    AND payload->>'outcome_semantics_id'
                        !~ '^outcome_semantics_[0-9a-f]{64}$'
               )
               OR payload->>'build_id' !~ '^build_[0-9a-f]{24}$' THEN
                RAISE EXCEPTION 'preflight release receipt is not an exact pass'
                    USING ERRCODE = '23514';
            END IF;
            expected_preflight_id := 'preflight_' || pg_catalog.substr(
                pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                    public.canonical_jsonb_text(payload - 'preflight_manifest_id'),
                    'UTF8'
                )), 'hex'), 1, 24
            );
            IF payload->>'preflight_manifest_id'
                    IS DISTINCT FROM expected_preflight_id THEN
                RAISE EXCEPTION 'preflight release receipt is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'restore_rehearsal' THEN
            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(payload) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'backup', 'collector_rehearsal', 'evidence_type',
                        'passed', 'rehearsal_manifest_id', 'schema_version',
                        'verification'
                    ]::TEXT[]
               OR payload->>'schema_version' IS DISTINCT FROM '4'
               OR payload->>'evidence_type'
                    IS DISTINCT FROM 'formal-restore-rehearsal'
               OR payload->'passed' IS DISTINCT FROM 'true'::jsonb
               OR pg_catalog.jsonb_typeof(payload->'backup')
                    IS DISTINCT FROM 'object'
               OR pg_catalog.jsonb_typeof(payload->'collector_rehearsal')
                    IS DISTINCT FROM 'object'
               OR pg_catalog.jsonb_typeof(payload->'verification')
                    IS DISTINCT FROM 'object' THEN
                RAISE EXCEPTION 'restore rehearsal receipt is not an exact pass'
                    USING ERRCODE = '23514';
            END IF;

            backup_document := payload->'backup';
            collector_rehearsal := payload->'collector_rehearsal';
            cycle_manifest := collector_rehearsal->'manifest';
            verification_document := payload->'verification';
            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(backup_document) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'backup_fingerprint', 'backup_id', 'backup_type',
                        'collector_rehearsal_id', 'completed_utc',
                        'final_collection_cycle_id',
                        'final_collection_cycle_manifest_id', 'schema_version',
                        'source_cluster_fingerprint'
                    ]::TEXT[]
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(collector_rehearsal)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'collection_cycle_id', 'collector_build_id',
                        'collector_rehearsal_id',
                        'component_configuration_id', 'evidence_type',
                        'manifest', 'manifest_id', 'passed', 'protocol_id',
                        'schema_version', 'server_completed_utc'
                    ]::TEXT[]
               OR pg_catalog.jsonb_typeof(cycle_manifest)
                    IS DISTINCT FROM 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                   FROM pg_catalog.jsonb_object_keys(verification_document)
                        AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'backup_id', 'completed_utc', 'external_calls',
                        'formal_trial_activity_rows', 'migration_head', 'passed',
                        'restored_cluster_fingerprint', 'role_contract_id',
                        'schema_version', 'verification_id', 'verification_type'
                    ]::TEXT[] THEN
                RAISE EXCEPTION 'restore rehearsal nested documents are malformed'
                    USING ERRCODE = '23514';
            END IF;

            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(cycle_manifest) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'collection_cycle_id', 'collector_build_id',
                        'collector_semantics_id', 'completed_utc', 'cycle_kind',
                        'expected_dynamic_slots', 'expected_static_slots',
                        'period_key', 'protocol_id', 'schema_version',
                        'server_started_utc', 'server_terminal_utc',
                        'slot_receipts', 'started_utc', 'status'
                    ]::TEXT[]
               OR backup_document->>'schema_version' IS DISTINCT FROM '1'
               OR backup_document->>'backup_type'
                    IS DISTINCT FROM 'formal-production-database-backup'
               OR collector_rehearsal->>'schema_version' IS DISTINCT FROM '1'
               OR collector_rehearsal->>'evidence_type'
                    IS DISTINCT FROM 'formal-collector-release-rehearsal'
               OR collector_rehearsal->'passed' IS DISTINCT FROM 'true'::JSONB
               OR collector_rehearsal->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
               OR collector_rehearsal->>'collector_build_id'
                    IS DISTINCT FROM cycle_manifest->>'collector_build_id'
               OR collector_rehearsal->>'component_configuration_id'
                    !~ '^config_[0-9a-f]{24}$'
               OR collector_rehearsal->>'collector_rehearsal_id'
                    !~ '^collector_rehearsal_[0-9a-f]{24}$'
               OR verification_document->>'schema_version' IS DISTINCT FROM '1'
               OR verification_document->>'verification_type'
                    IS DISTINCT FROM
                        'formal-restored-cluster-initial-empty-trial-check'
               OR verification_document->'passed' IS DISTINCT FROM 'true'::jsonb
               OR verification_document->'formal_trial_activity_rows'
                    IS DISTINCT FROM '0'::JSONB
               OR verification_document->'external_calls'
                    IS DISTINCT FROM '0'::JSONB
               OR verification_document->>'migration_head'
                    IS DISTINCT FROM '013_formal_runtime_role_split.sql'
               OR verification_document->>'role_contract_id'
                    IS DISTINCT FROM 'role_contract_a9f9c18629547e56b6330eb1'
               OR cycle_manifest->>'schema_version' IS DISTINCT FROM '2'
               OR cycle_manifest->>'status' IS DISTINCT FROM 'complete'
               OR cycle_manifest->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
               OR cycle_manifest->>'cycle_kind'
                    IS DISTINCT FROM 'formal-release-rehearsal-v1'
               OR cycle_manifest->>'period_key'
                    !~ '^release-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z$'
               OR cycle_manifest->>'collector_semantics_id'
                    IS DISTINCT FROM 'collector_aec83e329b85d5bf8654b2eb'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'expected_static_slots')
                    IS DISTINCT FROM 'array'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'expected_dynamic_slots')
                    IS DISTINCT FROM 'array'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'slot_receipts')
                    IS DISTINCT FROM 'array'
               OR pg_catalog.jsonb_typeof(backup_document->'completed_utc')
                    IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(
                    collector_rehearsal->'server_completed_utc'
               )
                    IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(verification_document->'completed_utc')
                    IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'started_utc')
                    IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'completed_utc')
                    IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'server_started_utc')
                    IS DISTINCT FROM 'number'
               OR pg_catalog.jsonb_typeof(cycle_manifest->'server_terminal_utc')
                    IS DISTINCT FROM 'number'
               OR backup_document->>'source_cluster_fingerprint'
                    !~ '^sha256:[0-9a-f]{64}$'
               OR backup_document->>'backup_fingerprint'
                    !~ '^sha256:[0-9a-f]{64}$'
               OR verification_document->>'restored_cluster_fingerprint'
                    !~ '^sha256:[0-9a-f]{64}$'
               OR backup_document->>'source_cluster_fingerprint'
                    IS NOT DISTINCT FROM
                        verification_document->>'restored_cluster_fingerprint'
               OR backup_document->>'backup_id' !~ '^backup_[0-9a-f]{24}$'
               OR verification_document->>'verification_id'
                    !~ '^verification_[0-9a-f]{24}$'
               OR payload->>'rehearsal_manifest_id'
                    !~ '^rehearsal_[0-9a-f]{24}$'
               OR collector_rehearsal->>'collection_cycle_id'
                    !~ '^cycle_[0-9a-f]{24}$'
               OR collector_rehearsal->>'manifest_id'
                    !~ '^cycle_manifest_[0-9a-f]{24}$'
               OR cycle_manifest->>'collector_semantics_id'
                    !~ '^collector_[0-9a-f]{24}$'
               OR cycle_manifest->>'collector_build_id'
                    !~ '^build_[0-9a-f]{24}$'
               THEN
                RAISE EXCEPTION 'restore rehearsal material is malformed'
                    USING ERRCODE = '23514';
            END IF;

            backup_time := (backup_document->>'completed_utc')::DOUBLE PRECISION;
            cycle_server_time :=
                (collector_rehearsal->>'server_completed_utc')::DOUBLE PRECISION;
            verification_time :=
                (verification_document->>'completed_utc')::DOUBLE PRECISION;
            IF backup_time <= '-Infinity'::DOUBLE PRECISION
               OR backup_time >= 'Infinity'::DOUBLE PRECISION
               OR cycle_server_time <= '-Infinity'::DOUBLE PRECISION
               OR cycle_server_time >= 'Infinity'::DOUBLE PRECISION
               OR verification_time <= '-Infinity'::DOUBLE PRECISION
               OR verification_time >= 'Infinity'::DOUBLE PRECISION
               OR (cycle_manifest->>'started_utc')::DOUBLE PRECISION
                    > (cycle_manifest->>'completed_utc')::DOUBLE PRECISION
               OR (cycle_manifest->>'server_started_utc')::DOUBLE PRECISION
                    > (cycle_manifest->>'server_terminal_utc')::DOUBLE PRECISION
               OR cycle_server_time IS DISTINCT FROM
                    (cycle_manifest->>'server_terminal_utc')::DOUBLE PRECISION
               OR NOT (
                    cycle_server_time <= backup_time
                    AND backup_time <= verification_time
               )
               OR collector_rehearsal->>'collection_cycle_id'
                    IS DISTINCT FROM cycle_manifest->>'collection_cycle_id'
               OR collector_rehearsal->>'manifest_id'
                    IS DISTINCT FROM
                        public.formal_jsonb_content_id(
                            cycle_manifest, 'cycle_manifest_'
                        )
               OR backup_document->>'final_collection_cycle_id'
                    IS DISTINCT FROM collector_rehearsal->>'collection_cycle_id'
               OR backup_document->>'final_collection_cycle_manifest_id'
                    IS DISTINCT FROM collector_rehearsal->>'manifest_id'
               OR backup_document->>'collector_rehearsal_id'
                    IS DISTINCT FROM collector_rehearsal->>'collector_rehearsal_id'
               OR verification_document->>'backup_id'
                    IS DISTINCT FROM backup_document->>'backup_id' THEN
                RAISE EXCEPTION 'restore rehearsal chronology or lineage is inconsistent'
                    USING ERRCODE = '23514';
            END IF;

            IF collector_rehearsal->>'collector_rehearsal_id' IS DISTINCT FROM
                    public.formal_jsonb_content_id(
                        collector_rehearsal - 'collector_rehearsal_id',
                        'collector_rehearsal_'
                    )
               OR cycle_manifest->'expected_static_slots' IS DISTINCT FROM
                    '[{"provider":"globalnews","query_key":"companies:corporate earnings OR mergers OR layoffs OR IPO when:7d"},{"provider":"globalnews","query_key":"energy:oil prices OPEC energy commodities when:7d"},{"provider":"globalnews","query_key":"politics:US administration Congress courts policy global markets when:7d"},{"provider":"globalnews","query_key":"politics:global elections government policy political leadership markets when:7d"},{"provider":"globalnews","query_key":"rates:Federal Reserve interest rate decision when:7d"},{"provider":"globalnews","query_key":"rates:inflation CPI outlook when:7d"},{"provider":"globalnews","query_key":"technology:semiconductors data centers technology investment when:7d"},{"provider":"globalnews","query_key":"technology:technology product launches AI research industry developments when:7d"},{"provider":"globalnews","query_key":"trade:geopolitical conflict diplomacy global markets when:7d"},{"provider":"globalnews","query_key":"trade:global policy trade sanctions supply chains markets when:7d"},{"provider":"trendnews","query_key":"ranked-global-discovery"},{"provider":"xtrend","query_key":"woeid:1"},{"provider":"xtrend","query_key":"woeid:23424977"}]'::JSONB
               OR pg_catalog.jsonb_array_length(
                    cycle_manifest->'expected_dynamic_slots'
               ) > 3
               OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.jsonb_array_elements(
                        cycle_manifest->'expected_dynamic_slots'
                    ) AS slot(value)
                    WHERE pg_catalog.jsonb_typeof(slot.value) IS DISTINCT FROM 'object'
                       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                           FROM pg_catalog.jsonb_object_keys(slot.value) AS keys(key))
                            IS DISTINCT FROM ARRAY['provider', 'query_key']::TEXT[]
                       OR slot.value->>'provider' IS DISTINCT FROM 'x'
                       OR slot.value->>'query_key' IS NULL
                       OR slot.value->>'query_key' = ''
               )
               OR pg_catalog.jsonb_array_length(cycle_manifest->'slot_receipts')
                    IS DISTINCT FROM 13 + pg_catalog.jsonb_array_length(
                        cycle_manifest->'expected_dynamic_slots'
                    )
               OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.jsonb_array_elements(
                        cycle_manifest->'slot_receipts'
                    ) AS receipt(value)
                    WHERE pg_catalog.jsonb_typeof(receipt.value)
                            IS DISTINCT FROM 'object'
                       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                           FROM pg_catalog.jsonb_object_keys(receipt.value)
                                AS keys(key))
                            IS DISTINCT FROM ARRAY[
                                'fetch_run_id', 'item_count', 'provider',
                                'query_key', 'raw_content_ids', 'slot_kind',
                                'status'
                            ]::TEXT[]
                       OR receipt.value->>'fetch_run_id' IS NULL
                       OR receipt.value->>'fetch_run_id' = ''
                       OR receipt.value->>'slot_kind' NOT IN ('static', 'dynamic')
                       OR receipt.value->>'status' NOT IN ('success', 'empty')
                       OR pg_catalog.jsonb_typeof(receipt.value->'item_count')
                            IS DISTINCT FROM 'number'
                       OR pg_catalog.jsonb_typeof(receipt.value->'raw_content_ids')
                            IS DISTINCT FROM 'array'
                       OR (
                            receipt.value->>'provider' = 'globalnews'
                            AND (
                                receipt.value->>'slot_kind' <> 'static'
                                OR receipt.value->>'status' <> 'success'
                                OR (receipt.value->>'item_count')::INTEGER < 1
                                OR CASE
                                    WHEN pg_catalog.jsonb_typeof(
                                        receipt.value->'raw_content_ids'
                                    ) = 'array' THEN pg_catalog.jsonb_array_length(
                                        receipt.value->'raw_content_ids'
                                    ) = 0
                                    ELSE TRUE
                                END
                            )
                       )
                       OR (
                            receipt.value->>'status' = 'empty'
                            AND receipt.value->>'provider' NOT IN (
                                'polymarket', 'trendnews', 'x', 'xtrend'
                            )
                       )
                       OR (
                            receipt.value->>'status' = 'success'
                            AND CASE
                                WHEN pg_catalog.jsonb_typeof(
                                    receipt.value->'raw_content_ids'
                                ) = 'array' THEN pg_catalog.jsonb_array_length(
                                    receipt.value->'raw_content_ids'
                                ) = 0
                                ELSE TRUE
                            END
                       )
               ) THEN
                RAISE EXCEPTION 'restore rehearsal collector coverage is invalid'
                    USING ERRCODE = '23514';
            END IF;

            expected_content_id := public.formal_jsonb_content_id(
                backup_document - 'backup_id', 'backup_'
            );
            IF backup_document->>'backup_id' IS DISTINCT FROM expected_content_id THEN
                RAISE EXCEPTION 'restore backup is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
            expected_content_id := public.formal_jsonb_content_id(
                verification_document - 'verification_id', 'verification_'
            );
            IF verification_document->>'verification_id'
                    IS DISTINCT FROM expected_content_id THEN
                RAISE EXCEPTION 'restore verification is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
            expected_content_id := public.formal_jsonb_content_id(
                payload - 'rehearsal_manifest_id', 'rehearsal_'
            );
            IF payload->>'rehearsal_manifest_id'
                    IS DISTINCT FROM expected_content_id THEN
                RAISE EXCEPTION 'restore rehearsal is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;

            SELECT cycle.*
             INTO stored_cycle
              FROM public.collection_cycles AS cycle
             WHERE cycle.collection_cycle_id =
                    collector_rehearsal->>'collection_cycle_id';
            IF NOT FOUND THEN
                RAISE EXCEPTION 'restore rehearsal lacks its production collection cycle'
                    USING ERRCODE = '23514';
            END IF;
            IF stored_cycle.status IS DISTINCT FROM 'complete'
               OR stored_cycle.protocol_id IS DISTINCT FROM NEW.protocol_id
               OR stored_cycle.collector_build_id
                    IS DISTINCT FROM cycle_manifest->>'collector_build_id'
               OR stored_cycle.server_terminal_utc
                    IS DISTINCT FROM cycle_server_time
               OR stored_cycle.manifest_id
                    IS DISTINCT FROM collector_rehearsal->>'manifest_id'
               OR stored_cycle.manifest_json::JSONB IS DISTINCT FROM cycle_manifest
               OR EXISTS (
                    SELECT 1
                    FROM public.collection_cycles AS later
                    WHERE later.protocol_id = stored_cycle.protocol_id
                      AND (
                        coalesce(
                            later.server_terminal_utc,
                            later.server_started_utc
                        ),
                        later.collection_cycle_id
                      ) > (
                        stored_cycle.server_terminal_utc,
                        stored_cycle.collection_cycle_id
                      )
               ) THEN
                RAISE EXCEPTION 'restore rehearsal does not bind the final completed cycle'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'alert_delivery' THEN
            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(payload) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'alert_delivery_id', 'delivered', 'deliveries',
                        'evidence_type', 'route_fingerprint', 'schema_version'
                    ]::TEXT[]
               OR payload->>'schema_version' IS DISTINCT FROM '2'
               OR payload->>'evidence_type'
                    IS DISTINCT FROM 'formal-alert-delivery'
               OR payload->'delivered' IS DISTINCT FROM 'true'::jsonb
               OR payload->>'alert_delivery_id' !~ '^alert_[0-9a-f]{24}$'
               OR payload->>'route_fingerprint' !~ '^sha256:[0-9a-f]{64}$'
               OR pg_catalog.jsonb_typeof(payload->'deliveries')
                    IS DISTINCT FROM 'object' THEN
                RAISE EXCEPTION 'alert delivery aggregate is not an exact pass'
                    USING ERRCODE = '23514';
            END IF;
            deliveries := payload->'deliveries';
            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(deliveries) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'collector', 'paper_decision', 'paper_marker'
                    ]::TEXT[] THEN
                RAISE EXCEPTION 'alert delivery aggregate lacks an exact runtime set'
                    USING ERRCODE = '23514';
            END IF;
            FOREACH role_name IN ARRAY ARRAY[
                'collector', 'paper_decision', 'paper_marker'
            ]::TEXT[]
            LOOP
                delivery := deliveries->role_name;
                IF pg_catalog.jsonb_typeof(delivery) IS DISTINCT FROM 'object'
                   OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                       FROM pg_catalog.jsonb_object_keys(delivery) AS keys(key))
                        IS DISTINCT FROM ARRAY[
                            'build_id', 'client_observed_utc',
                            'component_configuration_id', 'delivered',
                            'delivery_id', 'delivery_type', 'role',
                            'route_fingerprint', 'schema_version'
                        ]::TEXT[]
                   OR delivery->>'schema_version' IS DISTINCT FROM '1'
                   OR delivery->>'delivery_type'
                        IS DISTINCT FROM 'formal-runtime-alert-delivery'
                   OR delivery->>'role' IS DISTINCT FROM role_name
                   OR delivery->'delivered' IS DISTINCT FROM 'true'::jsonb
                   OR delivery->>'build_id' !~ '^build_[0-9a-f]{24}$'
                   OR delivery->>'component_configuration_id'
                        !~ '^config_[0-9a-f]{24}$'
                   OR delivery->>'route_fingerprint'
                        IS DISTINCT FROM payload->>'route_fingerprint'
                   OR pg_catalog.jsonb_typeof(delivery->'client_observed_utc')
                        IS DISTINCT FROM 'number'
                   OR delivery->>'delivery_id'
                        !~ '^alert_delivery_[0-9a-f]{24}$' THEN
                    RAISE EXCEPTION 'runtime alert delivery is not an exact pass'
                        USING ERRCODE = '23514';
                END IF;
                delivery_time :=
                    (delivery->>'client_observed_utc')::DOUBLE PRECISION;
                IF delivery_time <= '-Infinity'::DOUBLE PRECISION
                   OR delivery_time >= 'Infinity'::DOUBLE PRECISION
                   OR delivery->>'delivery_id' IS DISTINCT FROM
                        public.formal_jsonb_content_id(
                            delivery - 'delivery_id', 'alert_delivery_'
                        ) THEN
                    RAISE EXCEPTION 'runtime alert delivery is not content-addressed'
                        USING ERRCODE = '23514';
                END IF;
            END LOOP;
            IF payload->>'alert_delivery_id' IS DISTINCT FROM
                    public.formal_jsonb_content_id(
                        payload - 'alert_delivery_id', 'alert_'
                    ) THEN
                RAISE EXCEPTION 'alert delivery aggregate is not content-addressed'
                    USING ERRCODE = '23514';
            END IF;
        WHEN 'runtime_role_decommission' THEN
            IF (SELECT pg_catalog.array_agg(key ORDER BY key)
                FROM pg_catalog.jsonb_object_keys(payload) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'decision_role', 'decommission_id', 'legacy_role',
                        'marker_role', 'passed'
                    ]::TEXT[]
               OR payload->'passed' IS DISTINCT FROM 'true'::jsonb
               OR payload->>'decommission_id' !~ '^decommission_[0-9a-f]{24}$'
               OR payload->>'legacy_role' IS DISTINCT FROM 'tradingagents-paper'
               OR payload->>'decision_role'
                    IS DISTINCT FROM 'tradingagents-paper-decision'
               OR payload->>'marker_role'
                    IS DISTINCT FROM 'tradingagents-paper-marker' THEN
                RAISE EXCEPTION 'runtime role decommission receipt is not an exact pass'
                    USING ERRCODE = '23514';
            END IF;
        ELSE
            RAISE EXCEPTION 'formal release receipt type is not allowed'
                USING ERRCODE = '23514';
    END CASE;

    NEW.created_utc := server_now;
    NEW.content_json := public.canonical_jsonb_text(document);
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_release_receipt() IS
    'tradingagents.formal-release-receipt.v5;normalized-prosrc-sha256=1e45267535232d31ed06246edff22a2820af1449a24d24db87d3b2c63cf50e28';

DROP TRIGGER IF EXISTS immutable_formal_release_receipts
    ON public.formal_release_receipts;
CREATE TRIGGER immutable_formal_release_receipts
    BEFORE INSERT OR UPDATE OR DELETE ON public.formal_release_receipts
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_release_receipt();

CREATE OR REPLACE FUNCTION public.formal_image_build_id(image JSONB)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
DECLARE
    runtime JSONB;
    expected_ref TEXT;
    expected_build_id TEXT;
BEGIN
    runtime := image->'runtime_build_manifest';
    IF pg_catalog.jsonb_typeof(image) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(image) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'app_name', 'build_id', 'image_digest', 'image_ref',
                'runtime_build_manifest', 'schema_version'
            ]::TEXT[]
       OR image->>'schema_version' IS DISTINCT FROM '1'
       OR pg_catalog.jsonb_typeof(runtime) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(runtime) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'app_name', 'deployment_id', 'image_ref', 'platform',
                'schema_version'
            ]::TEXT[]
       OR runtime->>'schema_version' IS DISTINCT FROM '1'
       OR runtime->>'platform' IS DISTINCT FROM 'fly'
       OR runtime->>'app_name' !~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'
       OR runtime->>'deployment_id' !~ '^[0-9A-HJKMNP-TV-Z]{26}$'
       OR image->>'image_digest' !~ '^sha256:[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'formal image attestation has an invalid exact schema'
            USING ERRCODE = '23514';
    END IF;

    expected_ref := 'registry.fly.io/' || (runtime->>'app_name')
        || ':deployment-' || (runtime->>'deployment_id');
    expected_build_id := 'build_' || pg_catalog.substr(pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(
            public.canonical_jsonb_text(runtime), 'UTF8'
        )), 'hex'
    ), 1, 24);
    IF runtime->>'image_ref' IS DISTINCT FROM expected_ref
       OR image->>'app_name' IS DISTINCT FROM runtime->>'app_name'
       OR image->>'image_ref' IS DISTINCT FROM expected_ref
       OR image->>'build_id' IS DISTINCT FROM expected_build_id THEN
        RAISE EXCEPTION 'formal image attestation is internally inconsistent'
            USING ERRCODE = '23514';
    END IF;
    RETURN expected_build_id;
END
$$;

COMMENT ON FUNCTION public.formal_image_build_id(JSONB) IS
    'tradingagents.formal-image-attestation.v1;normalized-prosrc-sha256=4c64547f9630318b6adf10c357b26a24ac14404489017018c869bbd1adf2fb63';

CREATE OR REPLACE FUNCTION public.enforce_formal_trial_authorization()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    document JSONB;
    images JSONB;
    configurations JSONB;
    receipt_ids JSONB;
    registration JSONB;
    run_config JSONB;
    release_receipt JSONB;
    restore_payload JSONB;
    alert_payload JSONB;
    delivery JSONB;
    expected_authorization_id TEXT;
    collector_build TEXT;
    paper_decision_build TEXT;
    paper_marker_build TEXT;
    server_now DOUBLE PRECISION;
    expected_type TEXT;
    expected_receipt_id TEXT;
    role_name TEXT;
    evidence_time DOUBLE PRECISION;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'formal trial authorizations are append-only'
            USING ERRCODE = '55000';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'tradingagents:formal-protocol:' || NEW.protocol_id,
            0
        )
    );
    document := NEW.authorization_json::jsonb;
    images := document->'images';
    configurations := document->'configuration_binding';
    receipt_ids := document->'release_receipt_ids';
    IF pg_catalog.jsonb_typeof(document) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(document) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'authorization_id', 'authorization_type', 'configuration_binding',
                'images', 'outcome_semantics_id', 'protocol_id',
                'registration_id', 'release_receipt_ids', 'run_id',
                'schema_version'
            ]::TEXT[]
       OR document->>'schema_version' IS DISTINCT FROM '2'
       OR document->>'authorization_type'
            IS DISTINCT FROM 'formal-trial-release-authorization'
       OR document->>'authorization_id' IS DISTINCT FROM NEW.authorization_id
       OR document->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
       OR document->>'run_id' IS DISTINCT FROM NEW.run_id
       OR document->>'registration_id' IS DISTINCT FROM NEW.registration_id
       OR document->>'outcome_semantics_id' IS DISTINCT FROM NEW.outcome_semantics_id
       OR pg_catalog.jsonb_typeof(images) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(images) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'collector', 'paper_decision', 'paper_marker'
            ]::TEXT[]
       OR pg_catalog.jsonb_typeof(configurations) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(configurations) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'collector_configuration_id', 'configuration_manifest_id',
                'paper_decision_configuration_id',
                'paper_marker_configuration_id'
            ]::TEXT[]
       OR configurations->>'configuration_manifest_id'
            IS DISTINCT FROM NEW.configuration_manifest_id
       OR configurations->>'collector_configuration_id'
            IS DISTINCT FROM NEW.collector_configuration_id
       OR configurations->>'paper_decision_configuration_id'
            IS DISTINCT FROM NEW.paper_decision_configuration_id
       OR configurations->>'paper_marker_configuration_id'
            IS DISTINCT FROM NEW.paper_marker_configuration_id
       OR pg_catalog.jsonb_typeof(receipt_ids) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
           FROM pg_catalog.jsonb_object_keys(receipt_ids) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'alert_delivery', 'collector_preflight', 'configuration',
                'paper_decision_preflight', 'paper_marker_preflight',
                'restore_rehearsal', 'runtime_role_decommission'
            ]::TEXT[]
       OR EXISTS (
            SELECT 1 FROM pg_catalog.jsonb_each_text(receipt_ids) AS receipt(key, value)
            WHERE receipt.value !~ '^release_[0-9a-f]{24}$'
       ) THEN
        RAISE EXCEPTION 'formal trial authorization has an invalid exact schema'
            USING ERRCODE = '23514';
    END IF;

    expected_authorization_id := 'activation_' || pg_catalog.substr(pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(
            public.canonical_jsonb_text(document - 'authorization_id'), 'UTF8'
        )), 'hex'
    ), 1, 24);
    IF NEW.authorization_id IS DISTINCT FROM expected_authorization_id THEN
        RAISE EXCEPTION 'formal trial authorization is not content-addressed'
            USING ERRCODE = '23514';
    END IF;

    collector_build := public.formal_image_build_id(images->'collector');
    paper_decision_build := public.formal_image_build_id(images->'paper_decision');
    paper_marker_build := public.formal_image_build_id(images->'paper_marker');
    IF collector_build IS DISTINCT FROM NEW.collector_build_id
       OR paper_decision_build IS DISTINCT FROM NEW.paper_decision_build_id
       OR paper_marker_build IS DISTINCT FROM NEW.paper_marker_build_id
       OR (SELECT pg_catalog.count(DISTINCT image.value->>'app_name')
           FROM pg_catalog.jsonb_each(images) AS image(key, value)) <> 3 THEN
        RAISE EXCEPTION 'formal authorization image bindings are inconsistent'
            USING ERRCODE = '23514';
    END IF;

    SELECT registry.details_json::jsonb, run.config_json::jsonb
      INTO registration, run_config
      FROM public.formal_trial_registry AS registry
      JOIN public.paper_runs AS run ON run.run_id = registry.run_id
      JOIN public.paper_run_labels AS label
        ON label.run_id = registry.run_id
     AND label.label = 'confirmatory-trial'
     AND label.created_utc = registry.created_utc
     AND pg_catalog.convert_to(label.details_json, 'UTF8') =
         pg_catalog.convert_to(registry.details_json, 'UTF8')
     WHERE registry.protocol_id = NEW.protocol_id
       AND registry.run_id = NEW.run_id
       AND registry.registration_id = NEW.registration_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'formal authorization requires exact validated confirmatory label'
            USING ERRCODE = '23514';
    END IF;
    IF run_config->>'engine' IS DISTINCT FROM 'formal-global-v2'
       OR run_config->>'protocol_id' IS DISTINCT FROM NEW.protocol_id
       OR registration->>'outcome_semantics_id'
            IS DISTINCT FROM NEW.outcome_semantics_id
       OR registration->'configuration_binding' IS DISTINCT FROM configurations
       OR run_config->>'outcome_semantics_id'
            IS DISTINCT FROM NEW.outcome_semantics_id
       OR run_config->'configuration_binding' IS DISTINCT FROM configurations THEN
        RAISE EXCEPTION 'authorization differs from preregistered executable/configuration'
            USING ERRCODE = '23514';
    END IF;

    server_now := pg_catalog.date_part('epoch', pg_catalog.clock_timestamp());
    FOR expected_type, expected_receipt_id IN
        SELECT key, value
        FROM pg_catalog.jsonb_each_text(receipt_ids)
    LOOP
        SELECT receipt.content_json::jsonb
          INTO STRICT release_receipt
          FROM public.formal_release_receipts AS receipt
         WHERE receipt.receipt_id = expected_receipt_id
           AND receipt.receipt_type = expected_type
           AND receipt.protocol_id = NEW.protocol_id
           AND receipt.run_id = NEW.run_id;
        IF release_receipt->>'receipt_id' IS DISTINCT FROM expected_receipt_id THEN
            RAISE EXCEPTION 'authorization references inconsistent release evidence'
                USING ERRCODE = '23514';
        END IF;
        CASE expected_type
            WHEN 'configuration' THEN
                IF release_receipt->'payload'->'configuration_binding'
                        IS DISTINCT FROM configurations THEN
                    RAISE EXCEPTION 'authorization configuration receipt differs'
                        USING ERRCODE = '23514';
                END IF;
            WHEN 'collector_preflight' THEN
                IF release_receipt->'payload'->>'build_id'
                        IS DISTINCT FROM collector_build
                   OR release_receipt->'payload'->>'component_configuration_id'
                        IS DISTINCT FROM
                            configurations->>'collector_configuration_id' THEN
                    RAISE EXCEPTION 'collector preflight used a different image or configuration'
                        USING ERRCODE = '23514';
                END IF;
            WHEN 'paper_decision_preflight' THEN
                IF release_receipt->'payload'->>'build_id'
                        IS DISTINCT FROM paper_decision_build
                   OR release_receipt->'payload'->>'component_configuration_id'
                        IS DISTINCT FROM
                            configurations->>'paper_decision_configuration_id'
                   OR release_receipt->'payload'->>'outcome_semantics_id'
                        IS DISTINCT FROM NEW.outcome_semantics_id THEN
                    RAISE EXCEPTION 'paper decision preflight used different executable material'
                        USING ERRCODE = '23514';
                END IF;
            WHEN 'paper_marker_preflight' THEN
                IF release_receipt->'payload'->>'build_id'
                        IS DISTINCT FROM paper_marker_build
                   OR release_receipt->'payload'->>'component_configuration_id'
                        IS DISTINCT FROM
                            configurations->>'paper_marker_configuration_id'
                   OR release_receipt->'payload'->>'outcome_semantics_id'
                        IS DISTINCT FROM NEW.outcome_semantics_id THEN
                    RAISE EXCEPTION 'paper marker preflight used different executable material'
                        USING ERRCODE = '23514';
                END IF;
            WHEN 'restore_rehearsal' THEN
                restore_payload := release_receipt->'payload';
                IF restore_payload->'verification'->'formal_trial_activity_rows'
                        IS DISTINCT FROM '0'::JSONB
                   OR restore_payload->'verification'->'external_calls'
                        IS DISTINCT FROM '0'::JSONB
                   OR restore_payload->'collector_rehearsal'
                        ->>'component_configuration_id'
                            IS DISTINCT FROM
                                configurations->>'collector_configuration_id'
                   OR restore_payload->'collector_rehearsal'->'manifest'
                        ->>'collector_build_id' IS DISTINCT FROM collector_build
                   OR restore_payload->'collector_rehearsal'->'manifest'
                        ->>'protocol_id' IS DISTINCT FROM NEW.protocol_id THEN
                    RAISE EXCEPTION 'restore rehearsal differs from the empty released trial'
                        USING ERRCODE = '23514';
                END IF;
                FOREACH evidence_time IN ARRAY ARRAY[
                    (restore_payload->'collector_rehearsal'
                        ->>'server_completed_utc')::DOUBLE PRECISION,
                    (restore_payload->'backup'
                        ->>'completed_utc')::DOUBLE PRECISION,
                    (restore_payload->'verification'
                        ->>'completed_utc')::DOUBLE PRECISION
                ]::DOUBLE PRECISION[]
                LOOP
                    IF evidence_time < server_now - 86400.0
                       OR evidence_time > server_now + 300.0 THEN
                        RAISE EXCEPTION 'restore rehearsal evidence is stale or future-dated'
                            USING ERRCODE = '23514';
                    END IF;
                END LOOP;
                IF EXISTS (
                    SELECT 1
                    FROM public.collection_cycles AS later
                    WHERE later.protocol_id = NEW.protocol_id
                      AND (
                        coalesce(
                            later.server_terminal_utc,
                            later.server_started_utc
                        ),
                        later.collection_cycle_id
                      ) > (
                        (restore_payload->'collector_rehearsal'
                            ->>'server_completed_utc')::DOUBLE PRECISION,
                        restore_payload->'collector_rehearsal'
                            ->>'collection_cycle_id'
                      )
                ) THEN
                    RAISE EXCEPTION 'restore rehearsal collection cycle is no longer final'
                        USING ERRCODE = '23514';
                END IF;
            WHEN 'alert_delivery' THEN
                alert_payload := release_receipt->'payload';
                FOREACH role_name IN ARRAY ARRAY[
                    'collector', 'paper_decision', 'paper_marker'
                ]::TEXT[]
                LOOP
                    delivery := alert_payload->'deliveries'->role_name;
                    IF (
                        role_name = 'collector'
                        AND (
                            delivery->>'build_id' IS DISTINCT FROM collector_build
                            OR delivery->>'component_configuration_id'
                                IS DISTINCT FROM configurations
                                    ->>'collector_configuration_id'
                        )
                    ) OR (
                        role_name = 'paper_decision'
                        AND (
                            delivery->>'build_id'
                                IS DISTINCT FROM paper_decision_build
                            OR delivery->>'component_configuration_id'
                                IS DISTINCT FROM configurations
                                    ->>'paper_decision_configuration_id'
                        )
                    ) OR (
                        role_name = 'paper_marker'
                        AND (
                            delivery->>'build_id'
                                IS DISTINCT FROM paper_marker_build
                            OR delivery->>'component_configuration_id'
                                IS DISTINCT FROM configurations
                                    ->>'paper_marker_configuration_id'
                        )
                    ) THEN
                        RAISE EXCEPTION 'alert delivery used different executable material'
                            USING ERRCODE = '23514';
                    END IF;
                    evidence_time :=
                        (delivery->>'client_observed_utc')::DOUBLE PRECISION;
                    IF evidence_time < server_now - 86400.0
                       OR evidence_time > server_now + 300.0 THEN
                        RAISE EXCEPTION 'alert delivery evidence is stale or future-dated'
                            USING ERRCODE = '23514';
                    END IF;
                END LOOP;
            WHEN 'runtime_role_decommission' THEN
                NULL;
            ELSE
                RAISE EXCEPTION 'authorization release evidence type is invalid'
                    USING ERRCODE = '23514';
        END CASE;
    END LOOP;

    IF EXISTS (SELECT 1 FROM public.paper_decisions WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_decision_bundles WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_events WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_forecasts WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_targets WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_strategy_targets WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_marks WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_strategy_marks WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_price_receipts WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_price_capture_attempt_events
                    WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_price_capture_batches
                    WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_price_integrity_failures
                    WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_decision_attempt_events
                    WHERE run_id = NEW.run_id)
       OR EXISTS (SELECT 1 FROM public.paper_interval_assignments
                    WHERE run_id = NEW.run_id)
       OR EXISTS (
            SELECT 1 FROM public.paper_artifacts AS artifact
            WHERE artifact.content_json::jsonb->>'run_id' = NEW.run_id
       )
       OR EXISTS (
            SELECT 1 FROM public.paper_run_labels AS label
            WHERE label.run_id = NEW.run_id
              AND label.label <> 'confirmatory-trial'
       ) THEN
        RAISE EXCEPTION 'formal trial activity predates release authorization'
            USING ERRCODE = '55000';
    END IF;

    NEW.authorized_utc := server_now;
    NEW.authorization_json := public.canonical_jsonb_text(document);
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal authorization lacks exact registration or release evidence'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_trial_authorization() IS
    'tradingagents.formal-release-authorization.v5;normalized-prosrc-sha256=958607069dedaed0f0a5371f1aa3d2c15a9a63e396201c79eaadf1db292d7d11';

DROP TRIGGER IF EXISTS immutable_formal_trial_authorizations
    ON public.formal_trial_authorizations;
CREATE TRIGGER immutable_formal_trial_authorizations
    BEFORE INSERT OR UPDATE OR DELETE ON public.formal_trial_authorizations
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_trial_authorization();

-- The database is the final backstop for all direct SQL formal activity. The
-- application must perform the same authorization check before external calls.
CREATE OR REPLACE FUNCTION public.enforce_formal_activity_authorization()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    authz public.formal_trial_authorizations%ROWTYPE;
    batch_identity JSONB;
BEGIN
    SELECT run.config_json::jsonb
      INTO run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config->>'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    SELECT authorized.*
      INTO authz
      FROM public.formal_trial_authorizations AS authorized
     WHERE authorized.run_id = NEW.run_id
       AND authorized.protocol_id = run_config->>'protocol_id'
       AND authorized.outcome_semantics_id = run_config->>'outcome_semantics_id'
       AND authorized.configuration_manifest_id =
            run_config->'configuration_binding'->>'configuration_manifest_id'
       AND authorized.collector_configuration_id =
            run_config->'configuration_binding'->>'collector_configuration_id'
       AND authorized.paper_decision_configuration_id =
            run_config->'configuration_binding'->>'paper_decision_configuration_id'
       AND authorized.paper_marker_configuration_id =
            run_config->'configuration_binding'->>'paper_marker_configuration_id';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'formal activity requires exact durable release authorization'
            USING ERRCODE = '23514';
    END IF;

    IF TG_TABLE_NAME = 'paper_decision_bundles'
       AND pg_catalog.to_jsonb(NEW)->>'build_id'
            IS DISTINCT FROM authz.paper_decision_build_id THEN
        RAISE EXCEPTION 'formal decision bundle used an unauthorized decision image'
            USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'paper_price_capture_batches' THEN
        batch_identity := (
            pg_catalog.to_jsonb(NEW)->>'capture_identity_json'
        )::jsonb;
        IF batch_identity->>'paper_build_id'
                IS DISTINCT FROM authz.paper_marker_build_id THEN
            RAISE EXCEPTION 'formal price batch used an unauthorized marker image'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_activity_authorization() IS
    'tradingagents.formal-activity-authorization.v2;normalized-prosrc-sha256=c2793411767fec57dcceb5de977425b0f5fb2dee2360ae823850da15fca023ea';

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_decisions', 'paper_decision_bundles', 'paper_events',
        'paper_forecasts', 'paper_targets', 'paper_strategy_targets',
        'paper_marks', 'paper_strategy_marks', 'paper_price_receipts',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_decision_attempt_events',
        'paper_interval_assignments'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS require_formal_release_authorization ON public.%I',
            table_name
        );
        EXECUTE format(
            'CREATE TRIGGER require_formal_release_authorization '
            'BEFORE INSERT ON public.%I FOR EACH ROW '
            'EXECUTE FUNCTION public.enforce_formal_activity_authorization()',
            table_name
        );
    END LOOP;
END
$$;

CREATE OR REPLACE FUNCTION public.enforce_formal_artifact_authorization()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    artifact JSONB;
    artifact_run_id TEXT;
    run_config JSONB;
BEGIN
    artifact := NEW.content_json::jsonb;
    -- The outcome-blind development audit has no run_id and is governed by
    -- migration 010 before primary registration. It is the sole exemption.
    IF NEW.artifact_type = 'formal_development_selection_audit' THEN
        RETURN NEW;
    END IF;
    artifact_run_id := artifact->>'run_id';
    IF artifact_run_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT run.config_json::jsonb
      INTO run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = artifact_run_id;
    IF run_config->>'engine' = 'formal-global-v2'
       AND NOT EXISTS (
            SELECT 1 FROM public.formal_trial_authorizations AS authz
            WHERE authz.run_id = artifact_run_id
              AND authz.protocol_id = run_config->>'protocol_id'
              AND authz.outcome_semantics_id =
                    run_config->>'outcome_semantics_id'
              AND authz.configuration_manifest_id =
                    run_config->'configuration_binding'->>'configuration_manifest_id'
       ) THEN
        RAISE EXCEPTION 'formal artifact requires durable release authorization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_artifact_authorization() IS
    'tradingagents.formal-artifact-authorization.v1;normalized-prosrc-sha256=e990942c301da32d1d55b37b559a437d0f02a6e8883d626ce55898a5e528dd5a';

DROP TRIGGER IF EXISTS require_formal_release_authorization
    ON public.paper_artifacts;
CREATE TRIGGER require_formal_release_authorization
    BEFORE INSERT ON public.paper_artifacts
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_artifact_authorization();

CREATE OR REPLACE FUNCTION public.enforce_formal_label_authorization()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
BEGIN
    IF NEW.label = 'confirmatory-trial' THEN
        RETURN NEW;
    END IF;
    SELECT run.config_json::jsonb
      INTO run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config->>'engine' = 'formal-global-v2'
       AND NOT EXISTS (
            SELECT 1 FROM public.formal_trial_authorizations AS authz
            WHERE authz.run_id = NEW.run_id
              AND authz.protocol_id = run_config->>'protocol_id'
              AND authz.outcome_semantics_id =
                    run_config->>'outcome_semantics_id'
              AND authz.configuration_manifest_id =
                    run_config->'configuration_binding'->>'configuration_manifest_id'
       ) THEN
        RAISE EXCEPTION 'formal run label requires durable release authorization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_label_authorization() IS
    'tradingagents.formal-label-authorization.v1;normalized-prosrc-sha256=2774b96041c71cdb6c77351d89c20859b721ce189a36fba9a529efac20ad2cff';

DROP TRIGGER IF EXISTS require_formal_release_authorization
    ON public.paper_run_labels;
CREATE TRIGGER require_formal_release_authorization
    BEFORE INSERT ON public.paper_run_labels
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_label_authorization();

COMMENT ON TABLE public.formal_release_receipts IS
    'tradingagents.formal-release-evidence.v2; administrator-only append-only gates';
COMMENT ON TABLE public.formal_trial_authorizations IS
    'tradingagents.formal-release-authorization.v2; one exact activation per primary protocol';

REVOKE ALL PRIVILEGES ON TABLE public.formal_release_receipts,
    public.formal_trial_authorizations FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_release_receipt() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_image_build_id(JSONB) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_trial_authorization() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_activity_authorization() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_artifact_authorization() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_label_authorization() FROM PUBLIC;

DO $$
DECLARE
    role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'tradingagents-paper', 'tradingagents-paper-decision',
        'tradingagents-paper-marker'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
        ) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE '
                'public.formal_release_receipts, '
                'public.formal_trial_authorizations FROM %I',
                role_name
            );
            EXECUTE format(
                'GRANT SELECT ON TABLE public.formal_release_receipts, '
                'public.formal_trial_authorizations TO %I',
                role_name
            );
        END IF;
    END LOOP;

    FOREACH role_name IN ARRAY ARRAY[
        'tradingagents-ingest-v2', 'tradingagents-ingest'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
        ) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE '
                'public.formal_release_receipts, '
                'public.formal_trial_authorizations FROM %I',
                role_name
            );
        END IF;
    END LOOP;
END
$$;

COMMIT;
