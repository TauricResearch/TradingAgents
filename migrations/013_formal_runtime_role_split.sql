-- Least-privilege runtime split for the formal paper trial.
--
-- Provision these Fly MPG users as Reader users before applying this migration:
--   tradingagents-paper-decision
--   tradingagents-paper-marker
-- Reader inherits broad SELECT on Fly MPG, so ordinary REVOKE is insufficient.
-- Every paper/formal table is therefore protected by ENABLE + FORCE ROW LEVEL
-- SECURITY.  The legacy combined role remains available only for a paused
-- migration/rehearsal window.  One content-addressed administrator receipt
-- atomically revokes its mutation surface and closes its transitional policies;
-- no formal authorization can be inserted before that retirement is durable.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

DO $$
DECLARE
    missing_roles TEXT[];
    invalid_roles TEXT[];
    missing_tables TEXT[];
    missing_authorization_columns TEXT[];
    reserve_functions INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles AS role
         WHERE role.rolname = 'schema_admin'
           AND NOT role.rolcanlogin
           AND NOT role.rolsuper
           AND NOT role.rolbypassrls
    ) OR NOT pg_catalog.pg_has_role(CURRENT_USER, 'schema_admin', 'MEMBER') THEN
        RAISE EXCEPTION 'exact MPG schema_admin NOLOGIN owner role is required';
    END IF;

    SELECT pg_catalog.array_agg(required.role_name ORDER BY required.role_name)
      INTO missing_roles
      FROM pg_catalog.unnest(ARRAY[
          'tradingagents-paper', 'tradingagents-paper-decision',
          'tradingagents-paper-marker'
      ]::TEXT[]) AS required(role_name)
     WHERE NOT EXISTS (
         SELECT 1 FROM pg_catalog.pg_roles AS role
          WHERE role.rolname = required.role_name
     );
    IF missing_roles IS NOT NULL THEN
        RAISE EXCEPTION 'formal split roles must be provisioned first: %', missing_roles;
    END IF;

    SELECT pg_catalog.array_agg(role.rolname ORDER BY role.rolname)
      INTO invalid_roles
      FROM pg_catalog.pg_roles AS role
     WHERE role.rolname IN (
         'tradingagents-paper-decision', 'tradingagents-paper-marker'
     )
       AND (NOT role.rolcanlogin OR role.rolsuper OR role.rolbypassrls);
    IF invalid_roles IS NOT NULL
       OR pg_catalog.pg_has_role(
            'tradingagents-paper-decision',
            'tradingagents-paper-marker', 'MEMBER'
       )
       OR pg_catalog.pg_has_role(
            'tradingagents-paper-marker',
            'tradingagents-paper-decision', 'MEMBER'
       ) THEN
        RAISE EXCEPTION 'formal split login roles are privileged or cross-inherited';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles AS runtime_role
         WHERE runtime_role.rolname IN (
             'tradingagents-paper', 'tradingagents-paper-decision',
             'tradingagents-paper-marker', 'tradingagents-ingest-v2',
             'tradingagents-ingest'
         )
           AND pg_catalog.pg_has_role(
               runtime_role.oid,
               (SELECT owner.oid FROM pg_catalog.pg_roles AS owner
                 WHERE owner.rolname = 'schema_admin'),
               'MEMBER'
           )
    ) THEN
        RAISE EXCEPTION 'runtime role must not inherit the formal definer owner';
    END IF;

    SELECT pg_catalog.array_agg(required.table_name ORDER BY required.table_name)
      INTO missing_tables
      FROM pg_catalog.unnest(ARRAY[
          'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
          'paper_targets', 'paper_marks', 'experiment_registry',
          'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
          'paper_decision_bundles', 'paper_events', 'paper_forecasts',
          'paper_strategy_targets', 'paper_strategy_marks',
          'paper_price_capture_attempt_events', 'paper_price_capture_batches',
          'paper_price_integrity_failures', 'paper_price_receipts',
          'paper_decision_attempt_events', 'paper_interval_assignments',
          'formal_release_receipts', 'formal_trial_authorizations'
      ]::TEXT[]) AS required(table_name)
     WHERE pg_catalog.to_regclass('public.' || required.table_name) IS NULL;
    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'formal split prerequisite tables are missing: %', missing_tables;
    END IF;

    SELECT pg_catalog.array_agg(required.column_name ORDER BY required.column_name)
      INTO missing_authorization_columns
      FROM pg_catalog.unnest(ARRAY[
          'configuration_manifest_id', 'collector_configuration_id',
          'paper_decision_configuration_id', 'paper_marker_configuration_id',
          'collector_build_id', 'paper_decision_build_id',
          'paper_marker_build_id', 'authorization_json'
      ]::TEXT[]) AS required(column_name)
     WHERE NOT EXISTS (
         SELECT 1 FROM pg_catalog.pg_attribute AS attribute
          WHERE attribute.attrelid =
                'public.formal_trial_authorizations'::pg_catalog.regclass
            AND attribute.attname = required.column_name
            AND attribute.attnum > 0
            AND NOT attribute.attisdropped
     );
    IF missing_authorization_columns IS NOT NULL THEN
        RAISE EXCEPTION 'migration 012 split authorization columns are missing: %',
            missing_authorization_columns;
    END IF;

    SELECT pg_catalog.count(*)
      INTO reserve_functions
      FROM pg_catalog.pg_proc AS procedure
     WHERE procedure.pronamespace = 'public'::pg_catalog.regnamespace
       AND procedure.proname = 'reserve_formal_llm_invocation_budget';
    IF reserve_functions <> 1 THEN
        RAISE EXCEPTION 'migration 011 exact LLM reservation function is required';
    END IF;

    IF EXISTS (SELECT 1 FROM public.formal_trial_authorizations) THEN
        RAISE EXCEPTION 'role split must precede every formal trial authorization';
    END IF;
END
$$;

REVOKE CREATE ON SCHEMA public FROM
    "tradingagents-paper", "tradingagents-paper-decision",
    "tradingagents-paper-marker";
GRANT USAGE ON SCHEMA public TO
    "tradingagents-paper", "tradingagents-paper-decision",
    "tradingagents-paper-marker";

CREATE TABLE public.formal_role_split_decommissions (
    decommission_id TEXT PRIMARY KEY,
    legacy_role TEXT NOT NULL UNIQUE,
    decommissioned_utc DOUBLE PRECISION NOT NULL,
    contract_id TEXT NOT NULL UNIQUE,
    details_json TEXT NOT NULL,
    CHECK (decommission_id ~ '^decommission_[0-9a-f]{24}$'),
    CHECK (legacy_role = 'tradingagents-paper'),
    CHECK (contract_id = 'role_contract_a9f9c18629547e56b6330eb1'),
    CHECK (decommissioned_utc > '-Infinity'::DOUBLE PRECISION),
    CHECK (decommissioned_utc < 'Infinity'::DOUBLE PRECISION)
);

CREATE TABLE public.formal_role_policy_contracts (
    contract_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    policy_name TEXT NOT NULL,
    command TEXT NOT NULL,
    role_names_json TEXT NOT NULL,
    using_sha256 TEXT NOT NULL,
    check_sha256 TEXT NOT NULL,
    recorded_utc DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (contract_id, table_name, policy_name),
    CHECK (contract_id = 'role_contract_a9f9c18629547e56b6330eb1'),
    CHECK (command IN ('*', 'r', 'a', 'w')),
    CHECK (using_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (check_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (recorded_utc > '-Infinity'::DOUBLE PRECISION),
    CHECK (recorded_utc < 'Infinity'::DOUBLE PRECISION)
);

CREATE TABLE public.formal_runtime_heartbeat_events (
    heartbeat_id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    runtime_role TEXT NOT NULL,
    runtime_build_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    observed_utc DOUBLE PRECISION NOT NULL,
    event_json TEXT NOT NULL,
    CHECK (heartbeat_id ~ '^heartbeat_[0-9a-f]{24}$'),
    CHECK (runtime_role IN (
        'tradingagents-paper-decision', 'tradingagents-paper-marker'
    )),
    CHECK (event_type IN ('success', 'failure', 'paused')),
    CHECK (observed_utc > '-Infinity'::DOUBLE PRECISION),
    CHECK (observed_utc < 'Infinity'::DOUBLE PRECISION),
    UNIQUE (run_id, runtime_role, observed_utc)
);

-- A stable MPG base role, never a mutable login, owns every protected table
-- and every privileged projection/trigger.  FORCE RLS still applies to this
-- owner through the explicit command-scoped formal_definer_* policies below.
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
        'paper_targets', 'paper_marks', 'experiment_registry',
        'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'formal_role_policy_contracts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'ALTER TABLE public.%I OWNER TO schema_admin', table_name
        );
    END LOOP;
END
$$;

CREATE OR REPLACE FUNCTION public.formal_decision_artifact_type_allowed(value TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $$
    SELECT value = ANY (ARRAY[
        'llm_invocation_reserved', 'llm_invocation_result',
        'global_forecast_bundle'
    ]::TEXT[])
$$;

CREATE OR REPLACE FUNCTION public.formal_legacy_transition_open()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
PARALLEL SAFE
SET search_path = pg_catalog
AS $$
    SELECT NOT EXISTS (
        SELECT 1
          FROM public.formal_role_split_decommissions AS decommission
         WHERE decommission.legacy_role = 'tradingagents-paper'
           AND decommission.contract_id = 'role_contract_a9f9c18629547e56b6330eb1'
    )
$$;

REVOKE ALL ON FUNCTION public.formal_decision_artifact_type_allowed(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_legacy_transition_open() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.formal_decision_artifact_type_allowed(TEXT)
    TO "tradingagents-paper-decision", "tradingagents-paper";
GRANT EXECUTE ON FUNCTION public.formal_legacy_transition_open()
    TO "tradingagents-paper";

-- RLS is the boundary against Fly MPG's inherited Reader privilege.  The
-- migration administrator receives one all-command policy.  The NOLOGIN
-- definer owner receives only the command surface required by the hash-pinned
-- functions: reads everywhere, plus INSERT/UPDATE solely for the atomic LLM
-- budget reservation and its immutable reservation artifact.
DO $$
DECLARE
    table_name TEXT;
    migration_role NAME := CURRENT_USER;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
        'paper_targets', 'paper_marks', 'experiment_registry',
        'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'formal_role_policy_contracts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name
        );
        EXECUTE pg_catalog.format(
            'ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name
        );
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_admin_all ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_admin_all ON public.%I FOR ALL TO %I '
            'USING (true) WITH CHECK (true)', table_name, migration_role
        );
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_definer_select ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_definer_select ON public.%I FOR SELECT '
            'TO schema_admin USING (true)', table_name
        );
    END LOOP;
END
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_artifacts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_definer_insert ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_definer_insert ON public.%I FOR INSERT '
            'TO schema_admin WITH CHECK (true)', table_name
        );
    END LOOP;
    DROP POLICY IF EXISTS formal_definer_update
        ON public.formal_llm_budget_counters;
    CREATE POLICY formal_definer_update
        ON public.formal_llm_budget_counters
        FOR UPDATE TO schema_admin USING (true) WITH CHECK (true);
END
$$;

-- Transitional legacy policy.  It is deliberately absent on the budget and
-- contract tables; mutation of the budget is only through migration 011's
-- SECURITY DEFINER reservation function.
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_runs', 'paper_decisions', 'paper_targets', 'paper_marks',
        'experiment_registry', 'formal_trial_registry', 'paper_run_labels',
        'paper_artifacts', 'paper_decision_bundles', 'paper_events',
        'paper_forecasts', 'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_legacy_transition ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_legacy_transition ON public.%I FOR ALL '
            'TO "tradingagents-paper" '
            'USING (public.formal_legacy_transition_open()) '
            'WITH CHECK (public.formal_legacy_transition_open())',
            table_name
        );
    END LOOP;
END
$$;

-- Decision-side SELECT policies.  Labels and artifacts are filtered further:
-- no review/outcome label or artifact can be observed through this credential.
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_runs', 'experiment_registry', 'formal_trial_registry',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'paper_decisions', 'paper_targets',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_decision_attempt_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_decision_select ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_decision_select ON public.%I FOR SELECT '
            'TO "tradingagents-paper-decision" USING (true)', table_name
        );
    END LOOP;

    DROP POLICY IF EXISTS formal_decision_select ON public.paper_run_labels;
    CREATE POLICY formal_decision_select ON public.paper_run_labels
        FOR SELECT TO "tradingagents-paper-decision"
        USING (label = 'confirmatory-trial');
    DROP POLICY IF EXISTS formal_decision_select ON public.paper_artifacts;
    CREATE POLICY formal_decision_select ON public.paper_artifacts
        FOR SELECT TO "tradingagents-paper-decision"
        USING (public.formal_decision_artifact_type_allowed(artifact_type));
END
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_decisions', 'paper_targets', 'paper_decision_bundles',
        'paper_events', 'paper_forecasts', 'paper_strategy_targets',
        'paper_decision_attempt_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_decision_insert ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_decision_insert ON public.%I FOR INSERT '
            'TO "tradingagents-paper-decision" WITH CHECK (true)', table_name
        );
    END LOOP;
    DROP POLICY IF EXISTS formal_decision_insert ON public.paper_artifacts;
    CREATE POLICY formal_decision_insert ON public.paper_artifacts
        FOR INSERT TO "tradingagents-paper-decision"
        WITH CHECK (public.formal_decision_artifact_type_allowed(artifact_type));
END
$$;

-- Marker may consume frozen targets/bundle identities and owns only the price,
-- mark, and interval write surfaces.  It never sees LLM artifacts or forecasts.
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_runs', 'experiment_registry', 'formal_trial_registry',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'paper_targets',
        'paper_decision_bundles', 'paper_strategy_targets', 'paper_marks',
        'paper_strategy_marks', 'paper_price_capture_attempt_events',
        'paper_price_capture_batches', 'paper_price_integrity_failures',
        'paper_price_receipts', 'paper_interval_assignments'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_marker_select ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_marker_select ON public.%I FOR SELECT '
            'TO "tradingagents-paper-marker" USING (true)', table_name
        );
    END LOOP;
    DROP POLICY IF EXISTS formal_marker_select ON public.paper_run_labels;
    CREATE POLICY formal_marker_select ON public.paper_run_labels
        FOR SELECT TO "tradingagents-paper-marker"
        USING (label = 'confirmatory-trial');
END
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_marks', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_interval_assignments'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'DROP POLICY IF EXISTS formal_marker_insert ON public.%I', table_name
        );
        EXECUTE pg_catalog.format(
            'CREATE POLICY formal_marker_insert ON public.%I FOR INSERT '
            'TO "tradingagents-paper-marker" WITH CHECK (true)', table_name
        );
    END LOOP;
END
$$;

-- Revoke every direct runtime ACL first.  Inherited Reader SELECT remains but
-- is now row-filtered by the forced policies above.
DO $$
DECLARE
    table_name TEXT;
    role_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
        'paper_targets', 'paper_marks', 'experiment_registry',
        'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'formal_role_policy_contracts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', table_name
        );
        FOREACH role_name IN ARRAY ARRAY[
            'tradingagents-paper', 'tradingagents-paper-decision',
            'tradingagents-paper-marker', 'tradingagents-ingest-v2',
            'tradingagents-ingest'
        ]
        LOOP
            IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
            ) THEN
                EXECUTE pg_catalog.format(
                    'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I',
                    table_name, role_name
                );
            END IF;
        END LOOP;
    END LOOP;
END
$$;

GRANT SELECT ON TABLE
    public.paper_runs, public.experiment_registry,
    public.formal_trial_registry, public.formal_release_receipts,
    public.formal_trial_authorizations, public.formal_role_split_decommissions,
    public.paper_run_labels, public.paper_artifacts, public.paper_decisions,
    public.paper_targets, public.paper_decision_bundles, public.paper_events,
    public.paper_forecasts, public.paper_strategy_targets,
    public.paper_decision_attempt_events
TO "tradingagents-paper-decision";
GRANT INSERT ON TABLE
    public.paper_artifacts, public.paper_decisions, public.paper_targets,
    public.paper_decision_bundles, public.paper_events, public.paper_forecasts,
    public.paper_strategy_targets, public.paper_decision_attempt_events
TO "tradingagents-paper-decision";

GRANT SELECT ON TABLE
    public.paper_runs, public.experiment_registry,
    public.formal_trial_registry, public.formal_release_receipts,
    public.formal_trial_authorizations, public.formal_role_split_decommissions,
    public.paper_run_labels, public.paper_targets,
    public.paper_decision_bundles, public.paper_strategy_targets,
    public.paper_marks, public.paper_strategy_marks,
    public.paper_price_capture_attempt_events, public.paper_price_capture_batches,
    public.paper_price_integrity_failures, public.paper_price_receipts,
    public.paper_interval_assignments
TO "tradingagents-paper-marker";
GRANT INSERT ON TABLE
    public.paper_marks, public.paper_strategy_marks,
    public.paper_price_capture_attempt_events, public.paper_price_capture_batches,
    public.paper_price_integrity_failures, public.paper_price_receipts,
    public.paper_interval_assignments
TO "tradingagents-paper-marker";

-- Keep the historical grants only until the append-only retirement receipt.
GRANT SELECT ON TABLE
    public.paper_runs, public.paper_decisions, public.paper_targets,
    public.paper_marks, public.experiment_registry, public.formal_trial_registry,
    public.paper_run_labels, public.paper_artifacts,
    public.paper_decision_bundles, public.paper_events, public.paper_forecasts,
    public.paper_strategy_targets, public.paper_strategy_marks,
    public.paper_price_capture_attempt_events, public.paper_price_capture_batches,
    public.paper_price_integrity_failures, public.paper_price_receipts,
    public.paper_decision_attempt_events, public.paper_interval_assignments,
    public.formal_release_receipts, public.formal_trial_authorizations
TO "tradingagents-paper";
GRANT INSERT ON TABLE
    public.paper_runs, public.paper_decisions, public.paper_targets,
    public.paper_marks, public.experiment_registry, public.formal_trial_registry,
    public.paper_run_labels, public.paper_artifacts,
    public.paper_decision_bundles, public.paper_events, public.paper_forecasts,
    public.paper_strategy_targets, public.paper_strategy_marks,
    public.paper_price_capture_attempt_events, public.paper_price_capture_batches,
    public.paper_price_integrity_failures, public.paper_price_receipts,
    public.paper_decision_attempt_events, public.paper_interval_assignments
TO "tradingagents-paper";

-- Only decision (and transitional legacy) can invoke the exact atomic budget
-- reservation function.  The marker and collector never gain its mutation.
DO $$
DECLARE
    reserve_signature TEXT;
    role_name TEXT;
BEGIN
    SELECT procedure.oid::pg_catalog.regprocedure::TEXT
      INTO STRICT reserve_signature
      FROM pg_catalog.pg_proc AS procedure
     WHERE procedure.pronamespace = 'public'::pg_catalog.regnamespace
       AND procedure.proname = 'reserve_formal_llm_invocation_budget';
    EXECUTE pg_catalog.format(
        'REVOKE ALL ON FUNCTION %s FROM PUBLIC', reserve_signature
    );
    FOREACH role_name IN ARRAY ARRAY[
        'tradingagents-paper', 'tradingagents-paper-decision',
        'tradingagents-paper-marker', 'tradingagents-ingest-v2',
        'tradingagents-ingest'
    ]
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN
            EXECUTE pg_catalog.format(
                'REVOKE ALL ON FUNCTION %s FROM %I', reserve_signature, role_name
            );
        END IF;
    END LOOP;
    EXECUTE pg_catalog.format(
        'GRANT EXECUTE ON FUNCTION %s TO %I, %I', reserve_signature,
        'tradingagents-paper-decision', 'tradingagents-paper'
    );
END
$$;

-- Decision gets one outcome-free current-state projection.  It reports a
-- terminal capture halt but never exposes a price, return, NAV, interval, or
-- marker payload.
CREATE OR REPLACE FUNCTION public.formal_decision_state_projection(requested_run_id TEXT)
RETURNS TABLE (
    run_id TEXT,
    protocol_id TEXT,
    registration_id TEXT,
    authorization_id TEXT,
    paper_decision_build_id TEXT,
    paper_decision_configuration_id TEXT,
    config_json TEXT,
    last_decision_date TEXT,
    last_entry_date TEXT,
    last_target_weights_json TEXT,
    terminal_price_integrity_failure BOOLEAN
)
LANGUAGE sql
STABLE
SECURITY DEFINER
ROWS 1
SET search_path = pg_catalog
AS $$
    SELECT run.run_id, registry.protocol_id, registry.registration_id,
           authz.authorization_id, authz.paper_decision_build_id,
           authz.paper_decision_configuration_id, run.config_json,
           target.decision_date, target.entry_date, target.weights_json,
           EXISTS (
               SELECT 1 FROM public.paper_price_integrity_failures AS failure
                WHERE failure.run_id = run.run_id
           )
      FROM public.paper_runs AS run
      JOIN public.formal_trial_registry AS registry ON registry.run_id = run.run_id
      JOIN public.formal_trial_authorizations AS authz
        ON authz.run_id = registry.run_id
       AND authz.protocol_id = registry.protocol_id
      LEFT JOIN LATERAL (
          SELECT candidate.decision_date, candidate.entry_date,
                 candidate.weights_json
            FROM public.paper_targets AS candidate
           WHERE candidate.run_id = run.run_id
           ORDER BY candidate.decision_date DESC
           LIMIT 1
      ) AS target ON true
     WHERE run.run_id = requested_run_id
       AND run.config_json::JSONB ->> 'engine' = 'formal-global-v2'
$$;

-- The next decision needs current held weights for turnover and constraint
-- arithmetic.  Expose only that position vector and immutable lineage: no
-- This is explicitly classified as point-in-time operational state needed to
-- preserve preregistered turnover/constraint semantics.  No price, return,
-- NAV, cost, turnover, review artifact, or efficacy field crosses the boundary.
-- All eight frozen strategies are returned, including explicit all-zero rows
-- before a strategy has either a target or a mark; once marked, all eight must
-- share the exact latest champion-mark session or the projection returns none.
CREATE OR REPLACE FUNCTION public.formal_decision_weight_projection(
    requested_run_id TEXT
)
RETURNS TABLE (
    strategy_id TEXT,
    weights_json TEXT,
    source_kind TEXT,
    source_session_date TEXT,
    source_decision_date TEXT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
ROWS 8
SET search_path = pg_catalog
AS $$
    WITH strategy AS (
        SELECT item.strategy_id, item.ordinality
          FROM pg_catalog.unnest(ARRAY[
              'global_events_champion',
              'global_events_without_public_reaction',
              'public_reaction_only', 'market_only', 'equal_weight', 'momentum',
              'stale_events_negative_control',
              'shuffled_events_negative_control'
          ]::TEXT[]) WITH ORDINALITY AS item(strategy_id, ordinality)
    ), position AS (
        SELECT pg_catalog.max(mark.session_date) AS session_date
          FROM public.paper_marks AS mark
         WHERE mark.run_id = requested_run_id
    ), coherent AS (
        SELECT position.session_date,
               (
                   SELECT pg_catalog.array_agg(
                              mark.strategy_id
                              ORDER BY mark.strategy_id COLLATE pg_catalog."C"
                          )
                     FROM public.paper_strategy_marks AS mark
                    WHERE mark.run_id = requested_run_id
                      AND mark.session_date = position.session_date
               ) AS strategy_ids
          FROM position
    )
    SELECT strategy.strategy_id,
           COALESCE(mark.weights_json, target.weights_json, initial.weights_json),
           CASE
               WHEN mark.weights_json IS NOT NULL THEN 'strategy_mark'
               WHEN target.weights_json IS NOT NULL THEN 'strategy_target'
               ELSE 'initial_zero'
           END,
           mark.session_date,
           COALESCE(mark.target_decision_date, target.decision_date)
      FROM public.paper_runs AS run
      JOIN public.formal_trial_registry AS registry ON registry.run_id = run.run_id
      JOIN public.formal_trial_authorizations AS authz
       ON authz.run_id = registry.run_id
       AND authz.protocol_id = registry.protocol_id
      CROSS JOIN strategy
      CROSS JOIN coherent
      CROSS JOIN LATERAL (
          SELECT pg_catalog.jsonb_object_agg(
                     ticker.value, 0.0 ORDER BY ticker.value COLLATE pg_catalog."C"
                 )::TEXT AS weights_json
            FROM pg_catalog.jsonb_array_elements_text(
                     run.config_json::JSONB->'tickers'
                 ) AS ticker(value)
      ) AS initial
      LEFT JOIN LATERAL (
          SELECT candidate.weights_json, candidate.session_date,
                 candidate.target_decision_date
           FROM public.paper_strategy_marks AS candidate
           WHERE candidate.run_id = run.run_id
             AND candidate.strategy_id = strategy.strategy_id
             AND candidate.session_date = coherent.session_date
      ) AS mark ON true
      LEFT JOIN LATERAL (
          SELECT candidate.weights_json, candidate.decision_date
            FROM public.paper_strategy_targets AS candidate
           WHERE candidate.run_id = run.run_id
             AND candidate.strategy_id = strategy.strategy_id
           ORDER BY candidate.decision_date DESC
           LIMIT 1
      ) AS target ON true
     WHERE run.run_id = requested_run_id
       AND run.config_json::JSONB->>'engine' = 'formal-global-v2'
       AND (
           coherent.session_date IS NULL
           OR coherent.strategy_ids IS NOT DISTINCT FROM ARRAY[
               'equal_weight', 'global_events_champion',
               'global_events_without_public_reaction', 'market_only',
               'momentum', 'public_reaction_only',
               'shuffled_events_negative_control',
               'stale_events_negative_control'
           ]::TEXT[]
       )
     ORDER BY strategy.ordinality
$$;

-- Authenticate one requested decision slot without exposing the marker's
-- intervals, prices, marks, or returns.  The completed decision ledger must be
-- a one-to-one bundle/target chain and every bundle must own the exact frozen
-- eight-strategy inventory and successful attempt.  After initialization, the
-- latest synchronized mark/assignment frontier pins the next decision date;
-- missed decisions therefore advance through marker carry-forward rows rather
-- than extending the horizon.  XNYS next-entry validation remains the caller's
-- pinned decision-window check because PostgreSQL has no frozen exchange
-- calendar relation.
CREATE OR REPLACE FUNCTION public.formal_decision_slot_projection(
    p_run_id TEXT, p_decision_date TEXT, p_entry_date TEXT
)
RETURNS TABLE (
    run_id TEXT,
    protocol_id TEXT,
    registration_id TEXT,
    authorization_id TEXT,
    paper_decision_build_id TEXT,
    paper_decision_configuration_id TEXT,
    requested_decision_date TEXT,
    requested_entry_date TEXT,
    decision_chain_valid BOOLEAN,
    horizon_open BOOLEAN,
    slot_is_next BOOLEAN,
    terminal_price_integrity_failure BOOLEAN,
    eligible_for_requested_slot BOOLEAN
)
LANGUAGE sql
STABLE
SECURITY DEFINER
ROWS 1
SET search_path = pg_catalog
AS $$
    WITH context AS (
        SELECT run.run_id, registry.protocol_id, registry.registration_id,
               authz.authorization_id, authz.paper_decision_build_id,
               authz.paper_decision_configuration_id
          FROM public.paper_runs AS run
          JOIN public.formal_trial_registry AS registry
            ON registry.run_id = run.run_id
           AND registry.protocol_id = run.config_json::JSONB->>'protocol_id'
          JOIN public.paper_run_labels AS label
            ON label.run_id = registry.run_id
           AND label.label = 'confirmatory-trial'
           AND label.created_utc = registry.created_utc
           AND label.details_json = registry.details_json
          JOIN public.formal_trial_authorizations AS authz
            ON authz.run_id = registry.run_id
           AND authz.protocol_id = registry.protocol_id
          JOIN public.experiment_registry AS protocol
            ON protocol.protocol_id = registry.protocol_id
         WHERE run.run_id = p_run_id
           AND run.config_json::JSONB->>'engine' = 'formal-global-v2'
           AND COALESCE(
                   run.config_json::JSONB->>'trial_registration_id',
                   registry.registration_id
               ) = registry.registration_id
           AND protocol.manifest_json::JSONB->'strategies' = '[
               "global_events_champion",
               "global_events_without_public_reaction",
               "public_reaction_only",
               "market_only",
               "equal_weight",
               "momentum",
               "stale_events_negative_control",
               "shuffled_events_negative_control"
           ]'::JSONB
           AND protocol.manifest_json::JSONB
                   ->'analysis'->'trial_clock'->>'holding_intervals' = '252'
    ), frozen_bundle AS (
        SELECT bundle.decision_date, bundle.attempt_ordinal,
               bundle.protocol_id, bundle.build_id, bundle.created_utc,
               target.entry_date
          FROM public.paper_decision_bundles AS bundle
          LEFT JOIN public.paper_targets AS target
            ON target.run_id = bundle.run_id
           AND target.decision_date = bundle.decision_date
         WHERE bundle.run_id = p_run_id
    ), expected_slot AS (
        SELECT pg_catalog.count(*) AS mark_count,
               pg_catalog.max(mark.session_date) AS latest_mark_session,
               (
                   SELECT pg_catalog.count(*)
                     FROM public.paper_interval_assignments AS assignment
                    WHERE assignment.run_id = p_run_id
               ) AS completed_intervals,
               (
                   SELECT pg_catalog.max(assignment.interval_index)
                     FROM public.paper_interval_assignments AS assignment
                    WHERE assignment.run_id = p_run_id
               ) AS maximum_interval,
               (
                   SELECT pg_catalog.max(assignment.session_date)
                     FROM public.paper_interval_assignments AS assignment
                    WHERE assignment.run_id = p_run_id
               ) AS latest_assignment_session
          FROM public.paper_marks AS mark
         WHERE mark.run_id = p_run_id
    ), ledger AS (
        SELECT context.run_id,
               (SELECT pg_catalog.count(*) FROM frozen_bundle) AS bundle_count,
               expected.completed_intervals,
               COALESCE(expected.latest_mark_session, p_decision_date)
                   AS expected_decision_date,
               (
                   (
                       expected.mark_count = 0
                       AND expected.completed_intervals = 0
                       AND NOT EXISTS (
                           SELECT 1 FROM public.paper_targets AS target
                            WHERE target.run_id = p_run_id
                       )
                       AND NOT EXISTS (
                           SELECT 1 FROM public.paper_decision_bundles AS bundle
                            WHERE bundle.run_id = p_run_id
                       )
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.paper_strategy_targets AS target
                            WHERE target.run_id = p_run_id
                       )
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.paper_strategy_marks AS mark
                            WHERE mark.run_id = p_run_id
                       )
                   ) OR (
                       expected.mark_count > 0
                       AND expected.mark_count = expected.completed_intervals + 1
                       AND (
                           (
                               expected.completed_intervals = 0
                               AND expected.maximum_interval IS NULL
                               AND expected.latest_assignment_session IS NULL
                           ) OR (
                               expected.completed_intervals > 0
                               AND expected.maximum_interval
                                   = expected.completed_intervals
                               AND expected.latest_assignment_session
                                   = expected.latest_mark_session
                           )
                       )
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.paper_marks AS champion
                            WHERE champion.run_id = p_run_id
                              AND (
                                  SELECT pg_catalog.array_agg(
                                             shadow.strategy_id
                                             ORDER BY shadow.strategy_id
                                                 COLLATE pg_catalog."C"
                                         )
                                    FROM public.paper_strategy_marks AS shadow
                                   WHERE shadow.run_id = champion.run_id
                                     AND shadow.session_date = champion.session_date
                              ) IS DISTINCT FROM ARRAY[
                                  'equal_weight', 'global_events_champion',
                                  'global_events_without_public_reaction',
                                  'market_only', 'momentum',
                                  'public_reaction_only',
                                  'shuffled_events_negative_control',
                                  'stale_events_negative_control'
                              ]::TEXT[]
                       )
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.paper_strategy_marks AS shadow
                            WHERE shadow.run_id = p_run_id
                              AND NOT EXISTS (
                                  SELECT 1
                                    FROM public.paper_marks AS champion
                                   WHERE champion.run_id = shadow.run_id
                                     AND champion.session_date = shadow.session_date
                              )
                       )
                       AND NOT EXISTS (
                           SELECT 1
                             FROM public.paper_interval_assignments AS assignment
                            WHERE assignment.run_id = p_run_id
                              AND (
                                  NOT EXISTS (
                                      SELECT 1 FROM public.paper_marks AS mark
                                       WHERE mark.run_id = assignment.run_id
                                         AND mark.session_date
                                             = assignment.from_session_date
                                  ) OR NOT EXISTS (
                                      SELECT 1 FROM public.paper_marks AS mark
                                       WHERE mark.run_id = assignment.run_id
                                         AND mark.session_date = assignment.session_date
                                  ) OR (
                                      assignment.interval_index = 1
                                      AND assignment.from_session_date <> (
                                          SELECT pg_catalog.min(mark.session_date)
                                            FROM public.paper_marks AS mark
                                           WHERE mark.run_id = assignment.run_id
                                      )
                                  ) OR (
                                      assignment.interval_index > 1
                                      AND NOT EXISTS (
                                          SELECT 1
                                            FROM public.paper_interval_assignments
                                                 AS prior
                                           WHERE prior.run_id = assignment.run_id
                                             AND prior.interval_index
                                                 = assignment.interval_index - 1
                                             AND prior.session_date
                                                 = assignment.from_session_date
                                      )
                                  )
                              )
                       )
                   )
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM frozen_bundle AS bundle
                    WHERE bundle.entry_date IS NULL
                       OR bundle.decision_date !~ '^\d{4}-\d{2}-\d{2}$'
                       OR bundle.entry_date !~ '^\d{4}-\d{2}-\d{2}$'
                       OR bundle.entry_date <= bundle.decision_date
                       OR bundle.protocol_id <> context.protocol_id
                       OR bundle.build_id <> context.paper_decision_build_id
                       OR (
                           bundle.decision_date <> (
                               SELECT pg_catalog.min(candidate.decision_date)
                                 FROM frozen_bundle AS candidate
                           )
                           AND NOT EXISTS (
                               SELECT 1 FROM public.paper_marks AS mark
                                WHERE mark.run_id = p_run_id
                                  AND mark.session_date = bundle.decision_date
                           )
                       )
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM public.paper_targets AS target
                    WHERE target.run_id = p_run_id
                      AND NOT EXISTS (
                          SELECT 1
                            FROM public.paper_decision_bundles AS bundle
                           WHERE bundle.run_id = target.run_id
                             AND bundle.decision_date = target.decision_date
                      )
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM frozen_bundle AS bundle
                    WHERE (
                        SELECT pg_catalog.array_agg(
                                   target.strategy_id
                                   ORDER BY target.strategy_id
                                       COLLATE pg_catalog."C"
                               )
                          FROM public.paper_strategy_targets AS target
                         WHERE target.run_id = p_run_id
                           AND target.decision_date = bundle.decision_date
                    ) IS DISTINCT FROM ARRAY[
                        'equal_weight', 'global_events_champion',
                        'global_events_without_public_reaction', 'market_only',
                        'momentum', 'public_reaction_only',
                        'shuffled_events_negative_control',
                        'stale_events_negative_control'
                    ]::TEXT[]
                       OR EXISTS (
                           SELECT 1
                             FROM public.paper_strategy_targets AS target
                            WHERE target.run_id = p_run_id
                              AND target.decision_date = bundle.decision_date
                              AND target.entry_date <> bundle.entry_date
                       )
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM public.paper_strategy_targets AS target
                    WHERE target.run_id = p_run_id
                      AND NOT EXISTS (
                          SELECT 1
                            FROM frozen_bundle AS bundle
                           WHERE bundle.decision_date = target.decision_date
                             AND bundle.entry_date = target.entry_date
                      )
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM frozen_bundle AS bundle
                    WHERE NOT EXISTS (
                        SELECT 1
                          FROM public.paper_decision_attempt_events AS attempt
                         WHERE attempt.run_id = p_run_id
                           AND attempt.decision_date = bundle.decision_date
                           AND attempt.entry_date = bundle.entry_date
                           AND attempt.attempt_ordinal = bundle.attempt_ordinal
                           AND attempt.event_type = 'started'
                           AND attempt.created_utc <= bundle.created_utc
                    )
                       OR EXISTS (
                           SELECT 1
                             FROM public.paper_decision_attempt_events AS attempt
                            WHERE attempt.run_id = p_run_id
                              AND attempt.decision_date = bundle.decision_date
                              AND attempt.attempt_ordinal = bundle.attempt_ordinal
                              AND attempt.event_type = 'failed'
                       )
                       OR (
                           SELECT pg_catalog.max(attempt.attempt_ordinal)
                             FROM public.paper_decision_attempt_events AS attempt
                            WHERE attempt.run_id = p_run_id
                              AND attempt.decision_date = bundle.decision_date
                              AND attempt.event_type = 'started'
                       ) IS DISTINCT FROM bundle.attempt_ordinal
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM public.paper_decision_attempt_events AS failure
                    WHERE failure.run_id = p_run_id
                      AND failure.event_type = 'failed'
                      AND NOT EXISTS (
                          SELECT 1
                            FROM public.paper_decision_attempt_events AS started
                           WHERE started.run_id = failure.run_id
                             AND started.decision_date = failure.decision_date
                             AND started.entry_date = failure.entry_date
                             AND started.attempt_ordinal = failure.attempt_ordinal
                             AND started.event_type = 'started'
                             AND started.created_utc <= failure.created_utc
                      )
               )
               AND NOT EXISTS (
                   SELECT attempt.decision_date
                     FROM public.paper_decision_attempt_events AS attempt
                    WHERE attempt.run_id = p_run_id
                      AND attempt.event_type = 'started'
                    GROUP BY attempt.decision_date
                   HAVING pg_catalog.min(attempt.attempt_ordinal) <> 1
                       OR pg_catalog.max(attempt.attempt_ordinal)
                            <> pg_catalog.count(*)
               )
               AS chain_valid
          FROM context
          CROSS JOIN expected_slot AS expected
    ), result AS (
        SELECT context.*,
               ledger.chain_valid AS decision_chain_valid,
               ledger.completed_intervals < 251 AS horizon_open,
               p_decision_date ~ '^\d{4}-\d{2}-\d{2}$'
                   AND p_entry_date ~ '^\d{4}-\d{2}-\d{2}$'
                   AND p_entry_date > p_decision_date
                   AND p_decision_date = ledger.expected_decision_date
                   AND NOT EXISTS (
                       SELECT 1
                         FROM public.paper_decision_bundles AS bundle
                        WHERE bundle.run_id = p_run_id
                          AND bundle.decision_date = p_decision_date
                   ) AS slot_is_next,
               EXISTS (
                   SELECT 1
                     FROM public.paper_price_integrity_failures AS failure
                    WHERE failure.run_id = p_run_id
               ) AS terminal_price_integrity_failure
          FROM context
          JOIN ledger ON ledger.run_id = context.run_id
    )
    SELECT result.run_id, result.protocol_id, result.registration_id,
           result.authorization_id, result.paper_decision_build_id,
           result.paper_decision_configuration_id, p_decision_date, p_entry_date,
           result.decision_chain_valid, result.horizon_open,
           result.slot_is_next, result.terminal_price_integrity_failure,
           result.decision_chain_valid AND result.horizon_open
               AND result.slot_is_next
               AND NOT result.terminal_price_integrity_failure
      FROM result
$$;

-- Marker consumes only frozen target intent and the decision-bundle identity.
CREATE OR REPLACE FUNCTION public.formal_marker_target_projection(
    requested_run_id TEXT, through_session_date TEXT
)
RETURNS TABLE (
    decision_date TEXT,
    strategy_id TEXT,
    entry_date TEXT,
    created_utc DOUBLE PRECISION,
    weights_json TEXT,
    decision_artifact_id TEXT,
    attempt_ordinal INTEGER
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
    SELECT target.decision_date, 'champion'::TEXT, target.entry_date,
           target.created_utc, target.weights_json, bundle.artifact_id,
           bundle.attempt_ordinal
      FROM public.paper_targets AS target
      JOIN public.paper_decision_bundles AS bundle
        ON bundle.run_id = target.run_id
       AND bundle.decision_date = target.decision_date
     WHERE target.run_id = requested_run_id
       AND target.entry_date <= through_session_date
    UNION ALL
    SELECT target.decision_date, target.strategy_id, target.entry_date,
           target.created_utc, target.weights_json, bundle.artifact_id,
           bundle.attempt_ordinal
      FROM public.paper_strategy_targets AS target
      JOIN public.paper_decision_bundles AS bundle
        ON bundle.run_id = target.run_id
       AND bundle.decision_date = target.decision_date
     WHERE target.run_id = requested_run_id
       AND target.entry_date <= through_session_date
$$;

-- Collector sees only whether its exact build is activated and its own config
-- identity.  No run ID, target, mark, artifact, or outcome crosses this surface.
CREATE OR REPLACE FUNCTION public.formal_collector_release_projection(
    requested_protocol_id TEXT, requested_collector_build_id TEXT
)
RETURNS TABLE (authorized BOOLEAN, collector_configuration_id TEXT)
LANGUAGE sql
STABLE
SECURITY DEFINER
ROWS 1
SET search_path = pg_catalog
AS $$
    SELECT EXISTS (
               SELECT 1
                 FROM public.formal_trial_authorizations AS authz
                WHERE authz.protocol_id = requested_protocol_id
                  AND authz.collector_build_id = requested_collector_build_id
           ),
           (
               SELECT authz.collector_configuration_id
                 FROM public.formal_trial_authorizations AS authz
                WHERE authz.protocol_id = requested_protocol_id
                  AND authz.collector_build_id = requested_collector_build_id
           )
$$;

REVOKE ALL ON FUNCTION public.formal_decision_state_projection(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_decision_weight_projection(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_decision_slot_projection(TEXT, TEXT, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_marker_target_projection(TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_collector_release_projection(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.formal_decision_state_projection(TEXT)
    TO "tradingagents-paper-decision", "tradingagents-paper";
GRANT EXECUTE ON FUNCTION public.formal_decision_weight_projection(TEXT)
    TO "tradingagents-paper-decision", "tradingagents-paper";
GRANT EXECUTE ON FUNCTION public.formal_decision_slot_projection(TEXT, TEXT, TEXT)
    TO "tradingagents-paper-decision", "tradingagents-paper";
GRANT EXECUTE ON FUNCTION public.formal_marker_target_projection(TEXT, TEXT)
    TO "tradingagents-paper-marker", "tradingagents-paper";
DO $$
DECLARE
    role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['tradingagents-ingest-v2', 'tradingagents-ingest']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN
            EXECUTE pg_catalog.format(
                'GRANT EXECUTE ON FUNCTION '
                'public.formal_collector_release_projection(TEXT,TEXT) TO %I',
                role_name
            );
        END IF;
    END LOOP;
END
$$;

-- Heartbeats are an outcome-free operational receipt, not mutable poll_state.
-- The trigger, reached only through the definer recorder, derives the exact
-- login role, authorized build, server time, canonical document, and ID.  A
-- SET ROLE session is rejected using PostgreSQL's role GUC, which remains the
-- outer role identity inside SECURITY DEFINER execution.
CREATE OR REPLACE FUNCTION public.enforce_formal_runtime_heartbeat_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    authorized_protocol_id TEXT;
    server_observed_utc DOUBLE PRECISION;
    document JSONB;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'formal runtime heartbeat events are append-only'
            USING ERRCODE = '55000';
    END IF;
    IF SESSION_USER NOT IN (
        'tradingagents-paper-decision', 'tradingagents-paper-marker'
    ) OR pg_catalog.current_setting('role') IS DISTINCT FROM 'none' THEN
        RAISE EXCEPTION 'formal heartbeat requires an exact split runtime login'
            USING ERRCODE = '42501';
    END IF;
    IF NEW.run_id IS NULL OR pg_catalog.btrim(NEW.run_id) = ''
       OR NEW.event_type NOT IN ('success', 'failure', 'paused')
       OR NEW.runtime_build_id IS NULL
       OR pg_catalog.btrim(NEW.runtime_build_id) = '' THEN
        RAISE EXCEPTION 'formal runtime heartbeat request is malformed'
            USING ERRCODE = '22023';
    END IF;

    SELECT authz.protocol_id
      INTO STRICT authorized_protocol_id
      FROM public.formal_trial_authorizations AS authz
      JOIN public.formal_trial_registry AS registry
        ON registry.run_id = authz.run_id
       AND registry.protocol_id = authz.protocol_id
      JOIN public.paper_runs AS run ON run.run_id = authz.run_id
     WHERE authz.run_id = NEW.run_id
       AND run.config_json::JSONB->>'engine' = 'formal-global-v2'
       AND CASE SESSION_USER
           WHEN 'tradingagents-paper-decision' THEN
               authz.paper_decision_build_id = NEW.runtime_build_id
           WHEN 'tradingagents-paper-marker' THEN
               authz.paper_marker_build_id = NEW.runtime_build_id
           ELSE false
       END;

    server_observed_utc := pg_catalog.date_part(
        'epoch', pg_catalog.clock_timestamp()
    );
    document := pg_catalog.jsonb_build_object(
        'schema_version', 1,
        'protocol_id', authorized_protocol_id,
        'run_id', NEW.run_id,
        'runtime_role', SESSION_USER,
        'runtime_build_id', NEW.runtime_build_id,
        'event_type', NEW.event_type,
        'observed_utc', server_observed_utc
    );
    NEW.protocol_id := authorized_protocol_id;
    NEW.runtime_role := SESSION_USER;
    NEW.observed_utc := server_observed_utc;
    NEW.event_json := public.canonical_jsonb_text(document);
    NEW.heartbeat_id := 'heartbeat_' || pg_catalog.substr(pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(NEW.event_json, 'UTF8')),
        'hex'
    ), 1, 24);
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal heartbeat lacks exact run/build authorization'
            USING ERRCODE = '42501';
END
$$;

CREATE OR REPLACE FUNCTION public.record_formal_runtime_heartbeat(
    p_run_id TEXT, p_event_type TEXT, p_runtime_build_id TEXT
)
RETURNS TABLE (
    heartbeat_id TEXT,
    runtime_role TEXT,
    event_type TEXT,
    observed_utc DOUBLE PRECISION
)
LANGUAGE sql
VOLATILE
SECURITY DEFINER
ROWS 1
SET search_path = pg_catalog
AS $$
    INSERT INTO public.formal_runtime_heartbeat_events AS heartbeat (
        heartbeat_id, protocol_id, run_id, runtime_role, runtime_build_id,
        event_type, observed_utc, event_json
    ) VALUES (
        'heartbeat_000000000000000000000000', '', p_run_id, SESSION_USER,
        p_runtime_build_id, p_event_type, 0.0, '{}'
    )
    RETURNING heartbeat.heartbeat_id, heartbeat.runtime_role,
              heartbeat.event_type, heartbeat.observed_utc
$$;

DROP TRIGGER IF EXISTS govern_formal_runtime_heartbeat_event
    ON public.formal_runtime_heartbeat_events;
CREATE TRIGGER govern_formal_runtime_heartbeat_event
    BEFORE INSERT OR UPDATE OR DELETE
    ON public.formal_runtime_heartbeat_events
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_runtime_heartbeat_event();

-- Collector sees only component health for its own authorized build.  The
-- latest success/failure/paused timestamps are retained separately so a new
-- paused event cannot disguise a stale success or a recent failure.  No run,
-- decision, target, price, mark, return, or payload is projected.
CREATE OR REPLACE FUNCTION public.formal_runtime_latest_health_projection(
    p_protocol_id TEXT, p_collector_build_id TEXT
)
RETURNS TABLE (
    runtime_component TEXT,
    event_type TEXT,
    observed_utc DOUBLE PRECISION,
    latest_success_utc DOUBLE PRECISION,
    latest_failure_utc DOUBLE PRECISION,
    latest_paused_utc DOUBLE PRECISION
)
LANGUAGE sql
STABLE
SECURITY DEFINER
ROWS 2
SET search_path = pg_catalog
AS $$
    WITH authorized AS (
        SELECT authz.run_id
          FROM public.formal_trial_authorizations AS authz
         WHERE authz.protocol_id = p_protocol_id
           AND authz.collector_build_id = p_collector_build_id
    ), ranked AS (
        SELECT heartbeat.runtime_role, heartbeat.event_type,
               heartbeat.observed_utc,
               pg_catalog.row_number() OVER (
                   PARTITION BY heartbeat.runtime_role
                   ORDER BY heartbeat.observed_utc DESC, heartbeat.heartbeat_id DESC
               ) AS ordinal
          FROM public.formal_runtime_heartbeat_events AS heartbeat
          JOIN authorized ON authorized.run_id = heartbeat.run_id
    ), summary AS (
        SELECT ranked.runtime_role,
               pg_catalog.max(ranked.event_type)
                   FILTER (WHERE ranked.ordinal = 1) AS latest_event_type,
               pg_catalog.max(ranked.observed_utc)
                   FILTER (WHERE ranked.ordinal = 1) AS latest_observed_utc,
               pg_catalog.max(ranked.observed_utc)
                   FILTER (WHERE ranked.event_type = 'success') AS latest_success_utc,
               pg_catalog.max(ranked.observed_utc)
                   FILTER (WHERE ranked.event_type = 'failure') AS latest_failure_utc,
               pg_catalog.max(ranked.observed_utc)
                   FILTER (WHERE ranked.event_type = 'paused') AS latest_paused_utc
          FROM ranked
         GROUP BY ranked.runtime_role
    )
    SELECT CASE summary.runtime_role
               WHEN 'tradingagents-paper-decision' THEN 'decision'
               WHEN 'tradingagents-paper-marker' THEN 'marker'
           END,
           summary.latest_event_type, summary.latest_observed_utc,
           summary.latest_success_utc, summary.latest_failure_utc,
           summary.latest_paused_utc
      FROM summary
     ORDER BY 1
$$;

REVOKE ALL ON FUNCTION public.enforce_formal_runtime_heartbeat_event() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.record_formal_runtime_heartbeat(TEXT, TEXT, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_runtime_latest_health_projection(TEXT, TEXT)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.record_formal_runtime_heartbeat(TEXT, TEXT, TEXT)
    TO "tradingagents-paper-decision", "tradingagents-paper-marker";
DO $$
DECLARE
    role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['tradingagents-ingest-v2', 'tradingagents-ingest']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN
            EXECUTE pg_catalog.format(
                'GRANT EXECUTE ON FUNCTION '
                'public.formal_runtime_latest_health_projection(TEXT,TEXT) TO %I',
                role_name
            );
        END IF;
    END LOOP;
END
$$;

-- These two existing trigger functions must inspect the opposite side of the
-- RLS boundary to enforce a terminal halt and the 252-interval horizon.  Their
-- bodies remain hash-pinned by migrations 008/010; only execution identity is
-- elevated, and PUBLIC still has no EXECUTE privilege.
ALTER FUNCTION public.enforce_no_terminal_formal_price_failure() SECURITY DEFINER;
ALTER FUNCTION public.enforce_no_terminal_formal_price_failure()
    SET search_path = pg_catalog;
ALTER FUNCTION public.enforce_formal_artifact_governance() SECURITY DEFINER;
ALTER FUNCTION public.enforce_formal_artifact_governance()
    SET search_path = pg_catalog;

-- Snapshot every installed policy expression and role into an immutable
-- contract.  Any later ALTER/DROP/extra policy makes the production readiness
-- function false and blocks authorization.
INSERT INTO public.formal_role_policy_contracts (
    contract_id, table_name, policy_name, command, role_names_json,
    using_sha256, check_sha256, recorded_utc
)
SELECT 'role_contract_a9f9c18629547e56b6330eb1', class.relname,
       policy.polname, policy.polcmd::TEXT,
       pg_catalog.to_jsonb(ARRAY(
           SELECT pg_catalog.pg_get_userbyid(role_oid)
             FROM pg_catalog.unnest(policy.polroles) AS role_oid
            ORDER BY pg_catalog.pg_get_userbyid(role_oid)
       ))::TEXT,
       pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
           COALESCE(pg_catalog.pg_get_expr(policy.polqual, policy.polrelid, false), ''),
           'UTF8'
       )), 'hex'),
       pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
           COALESCE(pg_catalog.pg_get_expr(policy.polwithcheck, policy.polrelid, false), ''),
           'UTF8'
       )), 'hex'),
       pg_catalog.date_part('epoch', pg_catalog.clock_timestamp())
  FROM pg_catalog.pg_policy AS policy
  JOIN pg_catalog.pg_class AS class ON class.oid = policy.polrelid
  JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = class.relnamespace
 WHERE namespace.nspname = 'public'
   AND class.relname = ANY (ARRAY[
       'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
       'paper_targets', 'paper_marks', 'experiment_registry',
       'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
       'paper_decision_bundles', 'paper_events', 'paper_forecasts',
       'paper_strategy_targets', 'paper_strategy_marks',
       'paper_price_capture_attempt_events', 'paper_price_capture_batches',
       'paper_price_integrity_failures', 'paper_price_receipts',
       'paper_decision_attempt_events', 'paper_interval_assignments',
       'formal_release_receipts', 'formal_trial_authorizations',
       'formal_role_split_decommissions', 'formal_role_policy_contracts',
       'formal_runtime_heartbeat_events'
   ]::NAME[]);

CREATE OR REPLACE FUNCTION public.formal_role_policy_contract_matches()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
PARALLEL RESTRICTED
-- pg_get_expr qualifies names relative to search_path.  Match the exact
-- migration-time path used when the immutable hashes were recorded.
SET search_path = pg_catalog, public
AS $$
    WITH actual AS (
        SELECT class.relname::TEXT AS table_name, policy.polname::TEXT AS policy_name,
               policy.polcmd::TEXT AS command,
               pg_catalog.to_jsonb(ARRAY(
                   SELECT pg_catalog.pg_get_userbyid(role_oid)
                     FROM pg_catalog.unnest(policy.polroles) AS role_oid
                    ORDER BY pg_catalog.pg_get_userbyid(role_oid)
               ))::TEXT AS role_names_json,
               pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                   COALESCE(pg_catalog.pg_get_expr(
                       policy.polqual, policy.polrelid, false
                   ), ''), 'UTF8'
               )), 'hex') AS using_sha256,
               pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                   COALESCE(pg_catalog.pg_get_expr(
                       policy.polwithcheck, policy.polrelid, false
                   ), ''), 'UTF8'
               )), 'hex') AS check_sha256
          FROM pg_catalog.pg_policy AS policy
          JOIN pg_catalog.pg_class AS class ON class.oid = policy.polrelid
          JOIN pg_catalog.pg_namespace AS namespace
            ON namespace.oid = class.relnamespace
         WHERE namespace.nspname = 'public'
           AND class.relname = ANY (ARRAY[
               'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
               'paper_targets', 'paper_marks', 'experiment_registry',
               'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
               'paper_decision_bundles', 'paper_events', 'paper_forecasts',
               'paper_strategy_targets', 'paper_strategy_marks',
               'paper_price_capture_attempt_events', 'paper_price_capture_batches',
               'paper_price_integrity_failures', 'paper_price_receipts',
               'paper_decision_attempt_events', 'paper_interval_assignments',
               'formal_release_receipts', 'formal_trial_authorizations',
               'formal_role_split_decommissions', 'formal_role_policy_contracts',
               'formal_runtime_heartbeat_events'
           ]::NAME[])
    ), expected AS (
        SELECT contract.table_name, contract.policy_name, contract.command,
               contract.role_names_json, contract.using_sha256,
               contract.check_sha256
          FROM public.formal_role_policy_contracts AS contract
         WHERE contract.contract_id = 'role_contract_a9f9c18629547e56b6330eb1'
    )
    SELECT NOT EXISTS (
        (SELECT * FROM actual EXCEPT SELECT * FROM expected)
        UNION ALL
        (SELECT * FROM expected EXCEPT SELECT * FROM actual)
    )
$$;

CREATE OR REPLACE FUNCTION public.formal_role_split_catalog_ready()
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
PARALLEL RESTRICTED
SET search_path = pg_catalog
AS $$
DECLARE
    table_name TEXT;
    role_name TEXT;
    reserve_oid OID;
    schema_admin_oid OID;
    function_contract RECORD;
    function_access RECORD;
    function_oid OID;
    actual_function_hash TEXT;
    actual_security_definer BOOLEAN;
    actual_function_config TEXT[];
    actual_function_owner TEXT;
BEGIN
    SELECT role.oid
      INTO schema_admin_oid
      FROM pg_catalog.pg_roles AS role
     WHERE role.rolname = 'schema_admin'
       AND NOT role.rolcanlogin
       AND NOT role.rolsuper
       AND NOT role.rolbypassrls;
    IF schema_admin_oid IS NULL OR EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles AS runtime_role
         WHERE runtime_role.rolname IN (
             'tradingagents-paper', 'tradingagents-paper-decision',
             'tradingagents-paper-marker', 'tradingagents-ingest-v2',
             'tradingagents-ingest'
         )
           AND pg_catalog.pg_has_role(
               runtime_role.oid, schema_admin_oid, 'MEMBER'
           )
    ) THEN
        RETURN false;
    END IF;

    IF NOT public.formal_role_policy_contract_matches()
       OR NOT EXISTS (
            SELECT 1 FROM public.formal_role_split_decommissions AS receipt
             WHERE receipt.legacy_role = 'tradingagents-paper'
               AND receipt.contract_id = 'role_contract_a9f9c18629547e56b6330eb1'
       )
       OR public.formal_legacy_transition_open() THEN
        RETURN false;
    END IF;

    FOR function_contract IN
        SELECT * FROM (VALUES
            (
                'public.formal_jsonb_exact_keys(jsonb,text[])',
                'edfa5a248962ef184d41f505ef84decfcee0d99106577fbbb1294b17eb27b669',
                false, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_jsonb_has_forbidden_outcome_key(jsonb)',
                '5cf6c65bc6605cbca70c86cdd413c70fa5b3e42fa79cea299bc067e6db5ba53d',
                false, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_jsonb_contains_key_value(jsonb,text,text)',
                '6f22b912095630441b89dcfef4720f02de03335b7c438835ac4a2df2775d05a9',
                false, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_jsonb_content_id(jsonb,text)',
                '1a86d1b1f7f25c241d91e77e7ca85858cd91698a9fcfdcccf30bc3f75ea4d4c4',
                false, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.enforce_formal_artifact_governance()',
                'e8972a0d65826c26dd51a4da7cbd66ef51ff5d5593cbf11dbc9f8a3f42f0a04b',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.enforce_formal_label_governance()',
                '84dfaba6f00da36a9be1626f1ca88409cb0bd7e351db3c9f119ca1b89bc0be62',
                false, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.enforce_no_terminal_formal_price_failure()',
                '24b132357569f84ef2b2ffb1c169f67a8324e3ffcd597934ab801f3aaa38a1bf',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.reserve_formal_llm_invocation_budget('
                    'text,text,text,text,text,text,text,integer,integer,integer)',
                '6a3a596b9b66f3ca4c937ac3ce750a2a1041ed74e819db07cfa2c4f59826fa93',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_decision_artifact_type_allowed(text)',
                '8fc5642ef491ca988e2aa3c98f3baad1e7d546b4cce0b071596f48c1e3c90e36',
                false, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_legacy_transition_open()',
                '7d8bfb1923b265bd8d7bbdec498c39c1036a54c59c53011bbe0d894ddb5be445',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_decision_state_projection(text)',
                '559babe366a677b6fda85322a6a340660b04040644e5a6d03c2a8581835e211f',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_decision_weight_projection(text)',
                '0f8f6ea6e8e7e741e2ffed713845e6d92da3abe7324ebadf4fc0a71be24a2bb6',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_decision_slot_projection(text,text,text)',
                'c302b642885620680f5d522b5fd1ab3009ac1b06f5b8422375aacaa72ddb243a',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_marker_target_projection(text,text)',
                '0148ddf028382b09f79e5a0f9ee3731f7a8bedcf7a4f6151736d3b34dad64da6',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_collector_release_projection(text,text)',
                'e52a63ad0e3f88165afc5843dd68ce0b38c070b49c69372f41c989fdfed05df3',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.enforce_formal_runtime_heartbeat_event()',
                '631724e3adb32136fd493235c5a76421b31596eb2c1177a617cdf08e15021c8e',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.record_formal_runtime_heartbeat(text,text,text)',
                '5b51c3db50dc2985076f4d2867171c850822435a4c2e6851b5fd4aec04fe1c89',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_runtime_latest_health_projection(text,text)',
                '0ccfe12156245196039432153a3a68c65b0003882ed2a39c969ecd38984ed12b',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.formal_role_policy_contract_matches()',
                '76d4d125b74174413906e523b9f69d8c7e6cc054631b2027ea94c3f911be8449',
                true, ARRAY['search_path=pg_catalog, public']::TEXT[]
            ),
            (
                'public.formal_role_split_preflight()',
                'a747665579cfa91e355d55f96fe39119e5e980a198d7473f2b0148a9ad289b36',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.enforce_formal_role_decommission()',
                '2c4b4d97122ab9be71938a9d5b071e37ca20c83b93ba69973384c10932a0d999',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            ),
            (
                'public.enforce_formal_role_split_authorization()',
                '6fa5bc328e98054c359ea035a04881acd1cdb0549aa49e8fd40da504fe2dabcf',
                true, ARRAY['search_path=pg_catalog']::TEXT[]
            )
        ) AS expected(signature, source_hash, security_definer, function_config)
    LOOP
        function_oid := pg_catalog.to_regprocedure(function_contract.signature);
        IF function_oid IS NULL THEN
            RETURN false;
        END IF;
        SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
                   procedure.prosrc, 'UTF8'
               )), 'hex'),
               procedure.prosecdef, procedure.proconfig,
               pg_catalog.pg_get_userbyid(procedure.proowner)
          INTO actual_function_hash, actual_security_definer,
               actual_function_config, actual_function_owner
          FROM pg_catalog.pg_proc AS procedure
         WHERE procedure.oid = function_oid;
        IF actual_function_hash IS DISTINCT FROM function_contract.source_hash
           OR actual_security_definer
                IS DISTINCT FROM function_contract.security_definer
           OR actual_function_config
                IS DISTINCT FROM function_contract.function_config
           OR actual_function_owner IS DISTINCT FROM 'schema_admin' THEN
            RETURN false;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles AS role
         WHERE role.rolname IN (
             'tradingagents-paper-decision', 'tradingagents-paper-marker',
             'tradingagents-paper', 'tradingagents-ingest-v2',
             'tradingagents-ingest'
         )
           AND (NOT role.rolcanlogin OR role.rolsuper OR role.rolbypassrls)
    ) OR (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_roles AS role
         WHERE role.rolname IN (
             'tradingagents-paper-decision', 'tradingagents-paper-marker'
         )
    ) <> 2
       OR pg_catalog.pg_has_role(
            'tradingagents-paper-decision',
            'tradingagents-paper-marker', 'MEMBER'
       )
       OR pg_catalog.pg_has_role(
            'tradingagents-paper-marker',
            'tradingagents-paper-decision', 'MEMBER'
       ) THEN
        RETURN false;
    END IF;

    FOREACH role_name IN ARRAY ARRAY[
        'tradingagents-paper', 'tradingagents-paper-decision',
        'tradingagents-paper-marker', 'tradingagents-ingest-v2',
        'tradingagents-ingest'
    ]
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name)
           AND pg_catalog.has_schema_privilege(role_name, 'public', 'CREATE') THEN
            RETURN false;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_class AS class
          JOIN pg_catalog.pg_namespace AS namespace
            ON namespace.oid = class.relnamespace
         WHERE namespace.nspname = 'public'
           AND class.relname = ANY (ARRAY[
               'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
               'paper_targets', 'paper_marks', 'experiment_registry',
               'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
               'paper_decision_bundles', 'paper_events', 'paper_forecasts',
               'paper_strategy_targets', 'paper_strategy_marks',
               'paper_price_capture_attempt_events', 'paper_price_capture_batches',
               'paper_price_integrity_failures', 'paper_price_receipts',
               'paper_decision_attempt_events', 'paper_interval_assignments',
               'formal_release_receipts', 'formal_trial_authorizations',
               'formal_role_split_decommissions', 'formal_role_policy_contracts',
               'formal_runtime_heartbeat_events'
           ]::NAME[])
           AND (
               NOT class.relrowsecurity OR NOT class.relforcerowsecurity
               OR class.relowner <> schema_admin_oid
           )
    ) THEN
        RETURN false;
    END IF;

    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
        'paper_targets', 'paper_marks', 'experiment_registry',
        'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'formal_role_policy_contracts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        IF pg_catalog.has_table_privilege(
               'tradingagents-paper', 'public.' || table_name,
               'INSERT,UPDATE,DELETE,TRUNCATE'
           )
           OR pg_catalog.has_table_privilege(
               'tradingagents-paper-decision', 'public.' || table_name,
               'UPDATE,DELETE,TRUNCATE'
           )
           OR pg_catalog.has_table_privilege(
               'tradingagents-paper-marker', 'public.' || table_name,
               'UPDATE,DELETE,TRUNCATE'
           ) THEN
            RETURN false;
        END IF;
        FOREACH role_name IN ARRAY ARRAY[
            'tradingagents-ingest-v2', 'tradingagents-ingest'
        ]
        LOOP
            IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
            ) AND pg_catalog.has_table_privilege(
                role_name, 'public.' || table_name,
                'INSERT,UPDATE,DELETE,TRUNCATE'
            ) THEN
                RETURN false;
            END IF;
        END LOOP;
        IF pg_catalog.has_table_privilege(
               'tradingagents-paper-decision', 'public.' || table_name, 'INSERT'
           ) IS DISTINCT FROM table_name = ANY (ARRAY[
               'paper_artifacts', 'paper_decisions', 'paper_targets',
               'paper_decision_bundles', 'paper_events', 'paper_forecasts',
               'paper_strategy_targets', 'paper_decision_attempt_events'
           ]::TEXT[]) THEN
            RETURN false;
        END IF;
        IF pg_catalog.has_table_privilege(
               'tradingagents-paper-marker', 'public.' || table_name, 'INSERT'
           ) IS DISTINCT FROM table_name = ANY (ARRAY[
               'paper_marks', 'paper_strategy_marks',
               'paper_price_capture_attempt_events', 'paper_price_capture_batches',
               'paper_price_integrity_failures', 'paper_price_receipts',
               'paper_interval_assignments'
           ]::TEXT[]) THEN
            RETURN false;
        END IF;
    END LOOP;

    SELECT procedure.oid
      INTO reserve_oid
      FROM pg_catalog.pg_proc AS procedure
     WHERE procedure.pronamespace = 'public'::pg_catalog.regnamespace
       AND procedure.proname = 'reserve_formal_llm_invocation_budget';
    IF reserve_oid IS NULL
       OR NOT pg_catalog.has_function_privilege(
            'tradingagents-paper-decision', reserve_oid, 'EXECUTE'
       )
       OR pg_catalog.has_function_privilege(
            'tradingagents-paper-marker', reserve_oid, 'EXECUTE'
       )
       OR pg_catalog.has_function_privilege(
            'tradingagents-paper', reserve_oid, 'EXECUTE'
    ) THEN
        RETURN false;
    END IF;

    FOR function_access IN
        SELECT * FROM (VALUES
            ('public.formal_jsonb_exact_keys(jsonb,text[])', ARRAY[]::TEXT[]),
            ('public.formal_jsonb_has_forbidden_outcome_key(jsonb)', ARRAY[]::TEXT[]),
            ('public.formal_jsonb_contains_key_value(jsonb,text,text)', ARRAY[]::TEXT[]),
            ('public.formal_jsonb_content_id(jsonb,text)', ARRAY[]::TEXT[]),
            ('public.enforce_formal_artifact_governance()', ARRAY[]::TEXT[]),
            ('public.enforce_formal_label_governance()', ARRAY[]::TEXT[]),
            ('public.enforce_no_terminal_formal_price_failure()', ARRAY[]::TEXT[]),
            (
                'public.reserve_formal_llm_invocation_budget('
                    'text,text,text,text,text,text,text,integer,integer,integer)',
                ARRAY['tradingagents-paper-decision']::TEXT[]
            ),
            (
                'public.formal_decision_artifact_type_allowed(text)',
                ARRAY['tradingagents-paper-decision']::TEXT[]
            ),
            (
                'public.formal_legacy_transition_open()',
                ARRAY['tradingagents-paper']::TEXT[]
            ),
            (
                'public.formal_decision_state_projection(text)',
                ARRAY['tradingagents-paper-decision']::TEXT[]
            ),
            (
                'public.formal_decision_weight_projection(text)',
                ARRAY['tradingagents-paper-decision']::TEXT[]
            ),
            (
                'public.formal_decision_slot_projection(text,text,text)',
                ARRAY['tradingagents-paper-decision']::TEXT[]
            ),
            (
                'public.formal_marker_target_projection(text,text)',
                ARRAY['tradingagents-paper-marker']::TEXT[]
            ),
            (
                'public.formal_collector_release_projection(text,text)',
                ARRAY['tradingagents-ingest-v2','tradingagents-ingest']::TEXT[]
            ),
            ('public.enforce_formal_runtime_heartbeat_event()', ARRAY[]::TEXT[]),
            (
                'public.record_formal_runtime_heartbeat(text,text,text)',
                ARRAY[
                    'tradingagents-paper-decision',
                    'tradingagents-paper-marker'
                ]::TEXT[]
            ),
            (
                'public.formal_runtime_latest_health_projection(text,text)',
                ARRAY['tradingagents-ingest-v2','tradingagents-ingest']::TEXT[]
            ),
            ('public.formal_role_policy_contract_matches()', ARRAY[]::TEXT[]),
            ('public.formal_role_split_catalog_ready()', ARRAY[]::TEXT[]),
            (
                'public.formal_role_split_preflight()',
                ARRAY[
                    'tradingagents-paper-decision',
                    'tradingagents-paper-marker'
                ]::TEXT[]
            ),
            ('public.enforce_formal_role_decommission()', ARRAY[]::TEXT[]),
            ('public.enforce_formal_role_split_authorization()', ARRAY[]::TEXT[])
        ) AS expected(signature, allowed_roles)
    LOOP
        function_oid := pg_catalog.to_regprocedure(function_access.signature);
        IF function_oid IS NULL THEN
            RETURN false;
        END IF;
        FOREACH role_name IN ARRAY ARRAY[
            'tradingagents-paper', 'tradingagents-paper-decision',
            'tradingagents-paper-marker', 'tradingagents-ingest-v2',
            'tradingagents-ingest'
        ]
        LOOP
            IF EXISTS (
                SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name
            ) AND pg_catalog.has_function_privilege(
                role_name, function_oid, 'EXECUTE'
            ) IS DISTINCT FROM (
                role_name = ANY (function_access.allowed_roles)
            ) THEN
                RETURN false;
            END IF;
        END LOOP;
    END LOOP;
    RETURN true;
END
$$;

CREATE OR REPLACE FUNCTION public.formal_role_split_preflight()
RETURNS TABLE (
    contract_id TEXT,
    ready BOOLEAN,
    legacy_decommissioned BOOLEAN,
    policy_contract_matches BOOLEAN
)
LANGUAGE sql
STABLE
SECURITY DEFINER
ROWS 1
SET search_path = pg_catalog
AS $$
    SELECT 'role_contract_a9f9c18629547e56b6330eb1'::TEXT,
           public.formal_role_split_catalog_ready(),
           EXISTS (
               SELECT 1 FROM public.formal_role_split_decommissions AS receipt
                WHERE receipt.legacy_role = 'tradingagents-paper'
                  AND receipt.contract_id = 'role_contract_a9f9c18629547e56b6330eb1'
           ),
           public.formal_role_policy_contract_matches()
$$;

REVOKE ALL ON FUNCTION public.formal_role_policy_contract_matches() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_role_split_catalog_ready() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_role_split_preflight() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.formal_role_split_preflight()
    TO "tradingagents-paper-decision", "tradingagents-paper-marker";

-- Administrator-only append-only decommission.  The trigger derives time and
-- ID, atomically revokes the legacy mutation functions/ACLs, and refuses to
-- retire a role that still inherits DML from another MPG base role.
CREATE OR REPLACE FUNCTION public.enforce_formal_role_decommission()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    document JSONB;
    expected_id TEXT;
    table_name TEXT;
    reserve_signature TEXT;
    function_signature TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'formal role decommission receipts are append-only'
            USING ERRCODE = '55000';
    END IF;
    IF SESSION_USER IN (
        'tradingagents-paper', 'tradingagents-paper-decision',
        'tradingagents-paper-marker'
    ) THEN
        RAISE EXCEPTION 'runtime role cannot decommission formal credentials'
            USING ERRCODE = '42501';
    END IF;
    document := NEW.details_json::JSONB;
    IF pg_catalog.jsonb_typeof(document) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
             FROM pg_catalog.jsonb_object_keys(document) AS keys(key))
          IS DISTINCT FROM ARRAY[
              'contract_id', 'decision_role', 'decommission_id',
              'legacy_role', 'marker_role', 'schema_version'
          ]::TEXT[]
       OR document->>'schema_version' IS DISTINCT FROM '1'
       OR document->>'contract_id'
            IS DISTINCT FROM 'role_contract_a9f9c18629547e56b6330eb1'
       OR document->>'legacy_role' IS DISTINCT FROM 'tradingagents-paper'
       OR document->>'decision_role'
            IS DISTINCT FROM 'tradingagents-paper-decision'
       OR document->>'marker_role'
            IS DISTINCT FROM 'tradingagents-paper-marker'
       OR document->>'decommission_id' IS DISTINCT FROM NEW.decommission_id
       OR NEW.legacy_role IS DISTINCT FROM document->>'legacy_role'
       OR NEW.contract_id IS DISTINCT FROM document->>'contract_id' THEN
        RAISE EXCEPTION 'formal role decommission receipt has a wrong exact schema'
            USING ERRCODE = '23514';
    END IF;
    expected_id := 'decommission_' || pg_catalog.substr(pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(
            public.canonical_jsonb_text(document - 'decommission_id'), 'UTF8'
        )), 'hex'
    ), 1, 24);
    IF NEW.decommission_id IS DISTINCT FROM expected_id THEN
        RAISE EXCEPTION 'formal role decommission receipt is not content-addressed'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.formal_trial_authorizations) THEN
        RAISE EXCEPTION 'legacy role must be decommissioned before authorization'
            USING ERRCODE = '55000';
    END IF;

    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
        'paper_targets', 'paper_marks', 'experiment_registry',
        'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'formal_role_policy_contracts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.%I '
            'FROM "tradingagents-paper"', table_name
        );
    END LOOP;
    SELECT procedure.oid::pg_catalog.regprocedure::TEXT
      INTO STRICT reserve_signature
      FROM pg_catalog.pg_proc AS procedure
     WHERE procedure.pronamespace = 'public'::pg_catalog.regnamespace
       AND procedure.proname = 'reserve_formal_llm_invocation_budget';
    EXECUTE pg_catalog.format(
        'REVOKE EXECUTE ON FUNCTION %s FROM "tradingagents-paper"',
        reserve_signature
    );
    FOREACH function_signature IN ARRAY ARRAY[
        'public.formal_jsonb_exact_keys(JSONB,TEXT[])',
        'public.formal_jsonb_has_forbidden_outcome_key(JSONB)',
        'public.formal_jsonb_contains_key_value(JSONB,TEXT,TEXT)',
        'public.formal_jsonb_content_id(JSONB,TEXT)',
        'public.formal_decision_artifact_type_allowed(TEXT)',
        'public.formal_decision_state_projection(TEXT)',
        'public.formal_decision_weight_projection(TEXT)',
        'public.formal_decision_slot_projection(TEXT,TEXT,TEXT)',
        'public.formal_marker_target_projection(TEXT,TEXT)'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'REVOKE EXECUTE ON FUNCTION %s FROM "tradingagents-paper"',
            function_signature
        );
    END LOOP;

    FOREACH table_name IN ARRAY ARRAY[
        'formal_llm_budget_counters', 'paper_runs', 'paper_decisions',
        'paper_targets', 'paper_marks', 'experiment_registry',
        'formal_trial_registry', 'paper_run_labels', 'paper_artifacts',
        'paper_decision_bundles', 'paper_events', 'paper_forecasts',
        'paper_strategy_targets', 'paper_strategy_marks',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures', 'paper_price_receipts',
        'paper_decision_attempt_events', 'paper_interval_assignments',
        'formal_release_receipts', 'formal_trial_authorizations',
        'formal_role_split_decommissions', 'formal_role_policy_contracts',
        'formal_runtime_heartbeat_events'
    ]
    LOOP
        IF pg_catalog.has_table_privilege(
            'tradingagents-paper', 'public.' || table_name,
            'INSERT,UPDATE,DELETE,TRUNCATE'
        ) THEN
            RAISE EXCEPTION 'legacy role still inherits DML on %', table_name
                USING ERRCODE = '42501';
        END IF;
    END LOOP;
    IF pg_catalog.has_function_privilege(
        'tradingagents-paper', reserve_signature, 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'legacy role still inherits formal reservation execution'
            USING ERRCODE = '42501';
    END IF;
    FOREACH function_signature IN ARRAY ARRAY[
        'public.formal_jsonb_exact_keys(JSONB,TEXT[])',
        'public.formal_jsonb_has_forbidden_outcome_key(JSONB)',
        'public.formal_jsonb_contains_key_value(JSONB,TEXT,TEXT)',
        'public.formal_jsonb_content_id(JSONB,TEXT)',
        'public.formal_decision_artifact_type_allowed(TEXT)',
        'public.formal_decision_state_projection(TEXT)',
        'public.formal_decision_weight_projection(TEXT)',
        'public.formal_decision_slot_projection(TEXT,TEXT,TEXT)',
        'public.formal_marker_target_projection(TEXT,TEXT)'
    ]
    LOOP
        IF pg_catalog.has_function_privilege(
            'tradingagents-paper', function_signature, 'EXECUTE'
        ) THEN
            RAISE EXCEPTION 'legacy role still inherits split function %',
                function_signature USING ERRCODE = '42501';
        END IF;
    END LOOP;
    NEW.decommissioned_utc :=
        pg_catalog.date_part('epoch', pg_catalog.clock_timestamp());
    NEW.details_json := public.canonical_jsonb_text(document);
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS immutable_formal_role_split_decommissions
    ON public.formal_role_split_decommissions;
CREATE TRIGGER immutable_formal_role_split_decommissions
    BEFORE INSERT OR UPDATE OR DELETE ON public.formal_role_split_decommissions
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_role_decommission();

DROP TRIGGER IF EXISTS immutable_formal_role_policy_contracts
    ON public.formal_role_policy_contracts;
CREATE TRIGGER immutable_formal_role_policy_contracts
    BEFORE UPDATE OR DELETE ON public.formal_role_policy_contracts
    FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation();

-- Independent authorization guard layered onto migration 012.  Even a valid
-- image/configuration receipt cannot activate while the legacy combined role
-- or a drifted RLS policy remains usable.
CREATE OR REPLACE FUNCTION public.enforce_formal_role_split_authorization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    document JSONB;
    release_receipt JSONB;
    release_receipt_id TEXT;
    durable_decommission_id TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF SESSION_USER = 'tradingagents-paper'
           OR CURRENT_USER = 'tradingagents-paper'
           OR NOT public.formal_role_split_catalog_ready() THEN
            RAISE EXCEPTION 'formal authorization requires exact decommissioned role split'
                USING ERRCODE = '55000';
        END IF;
        document := NEW.authorization_json::JSONB;
        release_receipt_id := document->'release_receipt_ids'
            ->>'runtime_role_decommission';
        SELECT receipt.content_json::JSONB
          INTO release_receipt
          FROM public.formal_release_receipts AS receipt
         WHERE receipt.receipt_id = release_receipt_id
           AND receipt.receipt_type = 'runtime_role_decommission'
           AND receipt.protocol_id = NEW.protocol_id
           AND receipt.run_id = NEW.run_id;
        SELECT receipt.decommission_id
          INTO durable_decommission_id
          FROM public.formal_role_split_decommissions AS receipt
         WHERE receipt.legacy_role = 'tradingagents-paper'
           AND receipt.contract_id = 'role_contract_a9f9c18629547e56b6330eb1';
        IF release_receipt_id IS NULL
           OR release_receipt->'payload'->'passed' IS DISTINCT FROM 'true'::JSONB
           OR release_receipt->'payload'->>'legacy_role'
                IS DISTINCT FROM 'tradingagents-paper'
           OR release_receipt->'payload'->>'decision_role'
                IS DISTINCT FROM 'tradingagents-paper-decision'
           OR release_receipt->'payload'->>'marker_role'
                IS DISTINCT FROM 'tradingagents-paper-marker'
           OR release_receipt->'payload'->>'decommission_id'
                IS DISTINCT FROM durable_decommission_id THEN
            RAISE EXCEPTION 'authorization decommission release differs from durable role receipt'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS require_formal_runtime_role_split
    ON public.formal_trial_authorizations;
CREATE TRIGGER require_formal_runtime_role_split
    BEFORE INSERT ON public.formal_trial_authorizations
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_role_split_authorization();

-- Own every privileged function with the same non-login MPG base role.  The
-- migration login is a member for administration, but no runtime role may be.
DO $$
DECLARE
    function_signature TEXT;
BEGIN
    FOREACH function_signature IN ARRAY ARRAY[
        'public.formal_jsonb_exact_keys(JSONB,TEXT[])',
        'public.formal_jsonb_has_forbidden_outcome_key(JSONB)',
        'public.formal_jsonb_contains_key_value(JSONB,TEXT,TEXT)',
        'public.formal_jsonb_content_id(JSONB,TEXT)',
        'public.enforce_formal_artifact_governance()',
        'public.enforce_formal_label_governance()',
        'public.enforce_no_terminal_formal_price_failure()',
        'public.reserve_formal_llm_invocation_budget('
            'TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,INTEGER,INTEGER)',
        'public.formal_decision_artifact_type_allowed(TEXT)',
        'public.formal_legacy_transition_open()',
        'public.formal_decision_state_projection(TEXT)',
        'public.formal_decision_weight_projection(TEXT)',
        'public.formal_decision_slot_projection(TEXT,TEXT,TEXT)',
        'public.formal_marker_target_projection(TEXT,TEXT)',
        'public.formal_collector_release_projection(TEXT,TEXT)',
        'public.enforce_formal_runtime_heartbeat_event()',
        'public.record_formal_runtime_heartbeat(TEXT,TEXT,TEXT)',
        'public.formal_runtime_latest_health_projection(TEXT,TEXT)',
        'public.formal_role_policy_contract_matches()',
        'public.formal_role_split_catalog_ready()',
        'public.formal_role_split_preflight()',
        'public.enforce_formal_role_decommission()',
        'public.enforce_formal_role_split_authorization()'
    ]
    LOOP
        IF pg_catalog.to_regprocedure(function_signature) IS NULL THEN
            RAISE EXCEPTION 'formal definer function is missing: %', function_signature;
        END IF;
        EXECUTE pg_catalog.format(
            'ALTER FUNCTION %s OWNER TO schema_admin', function_signature
        );
    END LOOP;
END
$$;

COMMENT ON TABLE public.formal_role_split_decommissions IS
    'tradingagents.formal-role-decommission.v1; append-only legacy credential retirement';
COMMENT ON TABLE public.formal_role_policy_contracts IS
    'tradingagents.formal-role-policy-contract.v1; exact forced-RLS catalog snapshot';
COMMENT ON TABLE public.formal_runtime_heartbeat_events IS
    'tradingagents.formal-runtime-heartbeat-event.v1; append-only outcome-free health';
COMMENT ON FUNCTION public.formal_decision_artifact_type_allowed(TEXT) IS
    'tradingagents.formal-decision-artifact-filter.v1;normalized-prosrc-sha256=f34871459c2daf34a68b8da7c214c132ddd70ba3c1b5b04db6bbf4471f0b077d';
COMMENT ON FUNCTION public.formal_legacy_transition_open() IS
    'tradingagents.formal-legacy-transition.v1;normalized-prosrc-sha256=1ded3cb1065c4c6371b84850974982262ffb76493207c4bf82537242755c5126';
COMMENT ON FUNCTION public.formal_decision_state_projection(TEXT) IS
    'tradingagents.formal-decision-state-projection.v1;normalized-prosrc-sha256=dfca7bce3a50e15c0f7e447b9356ca401230ddccd4e8b07a7e8c16531929e7b3;no-outcomes';
COMMENT ON FUNCTION public.formal_decision_weight_projection(TEXT) IS
    'tradingagents.formal-decision-weight-projection.v1;normalized-prosrc-sha256=b4f4234fe2fd0e081227c30c8a0f04d30c22129d343f8dd20192b07285556d88;point-in-time-operational-state;positions-only';
COMMENT ON FUNCTION public.formal_decision_slot_projection(TEXT, TEXT, TEXT) IS
    'tradingagents.formal-decision-slot-projection.v1;normalized-prosrc-sha256=f7a7548d34ed631c65ef233c87661e03908645f0fac5221036f974547f7f936d;eligibility-only';
COMMENT ON FUNCTION public.formal_marker_target_projection(TEXT, TEXT) IS
    'tradingagents.formal-marker-target-projection.v1;normalized-prosrc-sha256=599ae00296530cc3656ac474e2323d649c5eae502c3c482f6019d0f4a1577009;intent-only';
COMMENT ON FUNCTION public.formal_collector_release_projection(TEXT, TEXT) IS
    'tradingagents.formal-collector-release-projection.v1;normalized-prosrc-sha256=ec126c4f6345cc42003f2e54dfafeabae95177551e3d66fae83eb4b8d645d8c9;no-paper-data';
COMMENT ON FUNCTION public.enforce_formal_runtime_heartbeat_event() IS
    'tradingagents.formal-runtime-heartbeat-trigger.v1;normalized-prosrc-sha256=39b13ec5e5fcacfc2c2a93299e2827ddaa1e681fada227287eaf1bdab7abeeba';
COMMENT ON FUNCTION public.record_formal_runtime_heartbeat(TEXT, TEXT, TEXT) IS
    'tradingagents.formal-runtime-heartbeat-recorder.v1;normalized-prosrc-sha256=d9e9e11c5ef9578b31b444c172f5e7d8da3cef71daf281afed62d50c62e4bcc6';
COMMENT ON FUNCTION public.formal_runtime_latest_health_projection(TEXT, TEXT) IS
    'tradingagents.formal-runtime-health-projection.v1;normalized-prosrc-sha256=f42e51b0010c47ef8661272feb1dcd8aeb9773c72387ddda58151e23f5e7d68f;no-run-or-outcomes';
COMMENT ON FUNCTION public.formal_role_policy_contract_matches() IS
    'tradingagents.formal-role-policy-audit.v1;normalized-prosrc-sha256=0371a6e5af6b6151d8738cf29d289c116ae39befaee34bdd40fed3a72d731150';
COMMENT ON FUNCTION public.formal_role_split_catalog_ready() IS
    'tradingagents.formal-role-split-readiness.v1;normalized-prosrc-sha256=f6dad023e2e0459b97ae9eb1d8b371124bf04be513fbe49a38b7d78ed720a242';
COMMENT ON FUNCTION public.formal_role_split_preflight() IS
    'tradingagents.formal-role-split-preflight.v1;normalized-prosrc-sha256=3acfa782a695b12d915cf2d018adb5aaae73c375e8e883bdd41ea40c642b0b1a';
COMMENT ON FUNCTION public.enforce_formal_role_decommission() IS
    'tradingagents.formal-role-decommission-trigger.v1;normalized-prosrc-sha256=61006f28f6c78555eb96f6c4b8b6ebf5e157657bf494963a67043ddeace04197';
COMMENT ON FUNCTION public.enforce_formal_role_split_authorization() IS
    'tradingagents.formal-role-authorization-guard.v1;normalized-prosrc-sha256=7a824f9e4886f642e28dc1a58bfb7c99a8cd6a882f39900217ebed17e6061f2c';

REVOKE ALL PRIVILEGES ON TABLE public.formal_role_split_decommissions,
    public.formal_role_policy_contracts,
    public.formal_runtime_heartbeat_events FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_role_decommission() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_role_split_authorization() FROM PUBLIC;

COMMIT;
