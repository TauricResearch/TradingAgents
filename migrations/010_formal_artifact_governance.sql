-- Fail-closed insertion governance for the sole primary formal artifact and
-- label ledgers. Apply while both runtimes are paused, after migration 009.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

CREATE OR REPLACE FUNCTION public.formal_jsonb_exact_keys(
    document JSONB,
    expected_keys TEXT[]
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog
AS $$
    SELECT pg_catalog.jsonb_typeof(document) = 'object'
       AND COALESCE(
            (
                SELECT pg_catalog.array_agg(key ORDER BY key COLLATE pg_catalog."C")
                FROM pg_catalog.jsonb_object_keys(document) AS observed(key)
            ),
            ARRAY[]::TEXT[]
       ) = COALESCE(
            (
                SELECT pg_catalog.array_agg(key ORDER BY key COLLATE pg_catalog."C")
                FROM pg_catalog.unnest(expected_keys) AS required(key)
            ),
            ARRAY[]::TEXT[]
       )
$$;

COMMENT ON FUNCTION public.formal_jsonb_exact_keys(JSONB, TEXT[]) IS
    'tradingagents.formal-jsonb-exact-keys.v1;normalized-prosrc-sha256=44a0350f8be93d2ad11c5a3bae3a2cfa1b42fb227bcd4d1529dba4f931675453';

CREATE OR REPLACE FUNCTION public.formal_jsonb_has_forbidden_outcome_key(
    document JSONB
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog
AS $$
    WITH RECURSIVE walk(value, key) AS (
        SELECT document, NULL::TEXT
        UNION ALL
        SELECT child.value, child.key
        FROM walk
        CROSS JOIN LATERAL (
            SELECT entry.value, entry.key
            FROM pg_catalog.jsonb_each(
                CASE pg_catalog.jsonb_typeof(walk.value)
                    WHEN 'object' THEN walk.value
                    ELSE '{}'::JSONB
                END
            ) AS entry(key, value)
            UNION ALL
            SELECT element.value, NULL::TEXT
            FROM pg_catalog.jsonb_array_elements(
                CASE pg_catalog.jsonb_typeof(walk.value)
                    WHEN 'array' THEN walk.value
                    ELSE '[]'::JSONB
                END
            ) AS element(value)
        ) AS child
    )
    SELECT EXISTS (
        SELECT 1
        FROM walk
        WHERE pg_catalog.lower(key) = ANY (ARRAY[
            'benchmark_returns',
            'benchmark_nav',
            'benchmark_period_return',
            'formal_readout',
            'machine_statistical_candidate',
            'nav',
            'period_return',
            'pnl',
            'portfolio_returns',
            'profit_and_loss',
            'promotion_decision',
            'realized_returns',
            'returns',
            'sharpe',
            'sharpe_ratio',
            'spy_descriptives',
            'strategy_descriptives',
            'strategy_performance',
            'strategy_returns'
        ]::TEXT[])
    )
$$;

COMMENT ON FUNCTION public.formal_jsonb_has_forbidden_outcome_key(JSONB) IS
    'tradingagents.formal-jsonb-forbidden-outcome-key.v1;normalized-prosrc-sha256=78220265c7fbb70712504ba9332277e86ed4f8bd5d5f4230e8eb56ae045c4cc6';

CREATE OR REPLACE FUNCTION public.formal_jsonb_contains_key_value(
    document JSONB,
    target_key TEXT,
    target_value TEXT
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
    WITH RECURSIVE walk(value, key) AS (
        SELECT document, NULL::TEXT
        UNION ALL
        SELECT child.value, child.key
        FROM walk
        CROSS JOIN LATERAL (
            SELECT entry.value, entry.key
            FROM pg_catalog.jsonb_each(
                CASE pg_catalog.jsonb_typeof(walk.value)
                    WHEN 'object' THEN walk.value
                    ELSE '{}'::JSONB
                END
            ) AS entry(key, value)
            UNION ALL
            SELECT element.value, NULL::TEXT
            FROM pg_catalog.jsonb_array_elements(
                CASE pg_catalog.jsonb_typeof(walk.value)
                    WHEN 'array' THEN walk.value
                    ELSE '[]'::JSONB
                END
            ) AS element(value)
        ) AS child
    )
    SELECT EXISTS (
        SELECT 1
        FROM walk
        WHERE key = target_key
          AND pg_catalog.jsonb_typeof(value) = 'string'
          AND value #>> '{}' = target_value
    )
$$;

COMMENT ON FUNCTION public.formal_jsonb_contains_key_value(JSONB, TEXT, TEXT) IS
    'tradingagents.formal-jsonb-contains-key-value.v1;normalized-prosrc-sha256=ffc301b34ddbd5bcc6d304b6b0f2a10ed3be7b186356b56d7f90ca28a7177f07';

CREATE OR REPLACE FUNCTION public.formal_jsonb_content_id(
    document JSONB,
    id_prefix TEXT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
    SELECT id_prefix || pg_catalog.substr(
        pg_catalog.encode(
            pg_catalog.sha256(
                pg_catalog.convert_to(public.canonical_jsonb_text(document), 'UTF8')
            ),
            'hex'
        ),
        1,
        24
    )
$$;

COMMENT ON FUNCTION public.formal_jsonb_content_id(JSONB, TEXT) IS
    'tradingagents.formal-jsonb-content-id.v1;normalized-prosrc-sha256=fb1b0abd5f2a96d219a3cf691541675ac059e08e12e348fb7fb185c4100e3223';

CREATE OR REPLACE FUNCTION public.enforce_formal_artifact_governance()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    content JSONB;
    artifact_run_id TEXT;
    primary_run_id TEXT;
    primary_protocol_id TEXT;
    primary_registration_id TEXT;
    completed_intervals INTEGER;
    expected_keys TEXT[];
    expected_artifact_id TEXT;
    expected_audit_id TEXT;
    expected_invocation_id TEXT;
    expected_report_id TEXT;
    expected_manifest_id TEXT;
    gate INTEGER;
    access_kind TEXT;
    candidate_ids TEXT[];
    sorted_candidate_ids TEXT[];
    observation_count INTEGER;
    formal_candidate BOOLEAN;
    reservation_content JSONB;
    reservation_created_utc DOUBLE PRECISION;
BEGIN
    IF NEW.created_utc IN (
        '-Infinity'::DOUBLE PRECISION,
        'Infinity'::DOUBLE PRECISION,
        'NaN'::DOUBLE PRECISION
    ) THEN
        RAISE EXCEPTION 'formal artifact timestamp must be finite'
            USING ERRCODE = '23514';
    END IF;
    content := NEW.content_json::JSONB;
    IF pg_catalog.jsonb_typeof(content) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'formal artifact content must be an object'
            USING ERRCODE = '23514';
    END IF;
    -- Normalize before hashing or persistence. Direct SQL callers cannot create
    -- an alternative content identity by changing whitespace or object order.
    NEW.content_json := public.canonical_jsonb_text(content);

    -- The sole exception before primary registration is one complete frozen
    -- development-selection universe. It deliberately has no run_id because
    -- the primary run does not exist yet.
    IF NEW.artifact_type = 'formal_development_selection_audit' THEN
        expected_keys := ARRAY[
            'schema_version', 'audit_type', 'protocol_id',
            'development_sample_id', 'selected_candidate_id', 'candidate_ids',
            'candidate_sharpes', 'candidate_return_paths', 'observation_count',
            'periods_per_year', 'completeness_attested', 'audit_id'
        ];
        IF NOT public.formal_jsonb_exact_keys(content, expected_keys)
           OR content ->> 'schema_version' IS DISTINCT FROM '1'
           OR content ->> 'audit_type'
                IS DISTINCT FROM 'complete-development-selection-universe'
           OR content ->> 'protocol_id' IS NULL
           OR content ->> 'protocol_id' = ''
           OR content ->> 'development_sample_id' IS NULL
           OR content ->> 'development_sample_id' = ''
           OR content ->> 'periods_per_year' IS DISTINCT FROM '252'
           OR content ->> 'completeness_attested' IS DISTINCT FROM 'true'
           OR content ->> 'audit_id' !~ '^selection_audit_[0-9a-f]{24}$'
           OR pg_catalog.jsonb_typeof(content -> 'candidate_ids') <> 'array'
           OR pg_catalog.jsonb_typeof(content -> 'candidate_sharpes') <> 'object'
           OR pg_catalog.jsonb_typeof(content -> 'candidate_return_paths') <> 'object'
           OR pg_catalog.jsonb_typeof(content -> 'observation_count') <> 'number'
           OR (content ->> 'observation_count')::NUMERIC < 4
           OR (content ->> 'observation_count')::NUMERIC
                <> pg_catalog.trunc((content ->> 'observation_count')::NUMERIC)
           OR public.formal_jsonb_has_forbidden_outcome_key(content)
           OR EXISTS (
                SELECT 1 FROM public.formal_trial_registry AS registry
                WHERE registry.protocol_id = content ->> 'protocol_id'
           )
           OR EXISTS (
                SELECT 1 FROM public.paper_artifacts AS prior
                WHERE prior.content_json::JSONB ->> 'protocol_id'
                        = content ->> 'protocol_id'
           )
           OR EXISTS (
                SELECT 1
                FROM public.paper_runs AS protocol_run
                WHERE protocol_run.config_json::JSONB ->> 'engine'
                        = 'formal-global-v2'
                  AND protocol_run.config_json::JSONB ->> 'protocol_id'
                        = content ->> 'protocol_id'
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
                      OR EXISTS (
                          SELECT 1 FROM public.paper_price_capture_attempt_events AS row
                          WHERE row.run_id = protocol_run.run_id
                      )
                      OR EXISTS (
                          SELECT 1 FROM public.paper_price_capture_batches AS row
                          WHERE row.run_id = protocol_run.run_id
                      )
                      OR EXISTS (
                          SELECT 1 FROM public.paper_price_integrity_failures AS row
                          WHERE row.run_id = protocol_run.run_id
                      )
                      OR EXISTS (SELECT 1 FROM public.paper_price_receipts AS row
                                 WHERE row.run_id = protocol_run.run_id)
                      OR EXISTS (
                          SELECT 1 FROM public.paper_decision_attempt_events AS row
                          WHERE row.run_id = protocol_run.run_id
                      )
                      OR EXISTS (
                          SELECT 1 FROM public.paper_interval_assignments AS row
                          WHERE row.run_id = protocol_run.run_id
                      )
                      OR EXISTS (SELECT 1 FROM public.paper_run_labels AS row
                                 WHERE row.run_id = protocol_run.run_id)
                      OR EXISTS (
                          SELECT 1 FROM public.paper_artifacts AS row
                          WHERE row.content_json::JSONB ->> 'run_id'
                                = protocol_run.run_id
                      )
                  )
           ) THEN
            RAISE EXCEPTION 'development selection audit is not exact pre-activity'
                USING ERRCODE = '23514';
        END IF;
        observation_count := (content ->> 'observation_count')::INTEGER;
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(content -> 'candidate_ids') AS item(value)
            WHERE pg_catalog.jsonb_typeof(item.value) <> 'string'
               OR item.value #>> '{}' = ''
        ) THEN
            RAISE EXCEPTION 'development selection candidate identities are invalid'
                USING ERRCODE = '23514';
        END IF;
        SELECT pg_catalog.array_agg(item.value #>> '{}' ORDER BY item.ordinality),
               pg_catalog.array_agg(
                   item.value #>> '{}' ORDER BY item.value #>> '{}' COLLATE pg_catalog."C"
               )
          INTO candidate_ids, sorted_candidate_ids
          FROM pg_catalog.jsonb_array_elements(content -> 'candidate_ids')
               WITH ORDINALITY AS item(value, ordinality);
        IF COALESCE(pg_catalog.cardinality(candidate_ids), 0) < 2
           OR candidate_ids IS DISTINCT FROM sorted_candidate_ids
           OR pg_catalog.cardinality(candidate_ids)
                <> pg_catalog.cardinality(
                    ARRAY(SELECT DISTINCT candidate FROM pg_catalog.unnest(candidate_ids)
                          AS candidate)
                )
           OR NOT ((content ->> 'selected_candidate_id') = ANY (candidate_ids))
           OR NOT public.formal_jsonb_exact_keys(
                content -> 'candidate_sharpes', candidate_ids
           )
           OR NOT public.formal_jsonb_exact_keys(
                content -> 'candidate_return_paths', candidate_ids
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.jsonb_each(
                    content -> 'candidate_sharpes'
                ) AS sharpe(candidate, value)
                WHERE pg_catalog.jsonb_typeof(sharpe.value) <> 'number'
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.jsonb_each(
                    content -> 'candidate_return_paths'
                ) AS path(candidate, value)
                WHERE pg_catalog.jsonb_typeof(path.value) <> 'array'
                   OR pg_catalog.jsonb_array_length(path.value) <> observation_count
                   OR EXISTS (
                        SELECT 1
                        FROM pg_catalog.jsonb_array_elements(path.value) AS observed(value)
                        WHERE pg_catalog.jsonb_typeof(observed.value) <> 'number'
                           OR (observed.value #>> '{}')::DOUBLE PRECISION <= -1.0
                   )
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.jsonb_each(
                    content -> 'candidate_return_paths'
                ) AS path(candidate, value)
                CROSS JOIN LATERAL (
                    SELECT pg_catalog.avg(
                               (observed.value #>> '{}')::DOUBLE PRECISION
                           ) AS mean_return,
                           pg_catalog.stddev_samp(
                               (observed.value #>> '{}')::DOUBLE PRECISION
                           ) AS sample_deviation
                    FROM pg_catalog.jsonb_array_elements(path.value)
                         AS observed(value)
                ) AS stats
                WHERE CASE
                    WHEN stats.sample_deviation = 0.0 THEN
                        stats.mean_return <> 0.0
                        OR (content -> 'candidate_sharpes' ->> path.candidate)
                            ::DOUBLE PRECISION <> 0.0
                    ELSE pg_catalog.abs(
                        stats.mean_return / stats.sample_deviation
                        * pg_catalog.sqrt(252.0::DOUBLE PRECISION)
                        - (content -> 'candidate_sharpes' ->> path.candidate)
                            ::DOUBLE PRECISION
                    ) > 1e-12::DOUBLE PRECISION * GREATEST(
                        1.0::DOUBLE PRECISION,
                        pg_catalog.abs(
                            stats.mean_return / stats.sample_deviation
                            * pg_catalog.sqrt(252.0::DOUBLE PRECISION)
                        ),
                        pg_catalog.abs(
                            (content -> 'candidate_sharpes' ->> path.candidate)
                                ::DOUBLE PRECISION
                        )
                    )
                END
           ) THEN
            RAISE EXCEPTION 'development selection audit data is incomplete'
                USING ERRCODE = '23514';
        END IF;
        expected_audit_id := public.formal_jsonb_content_id(
            content - 'audit_id', 'selection_audit_'
        );
        IF content ->> 'audit_id' IS DISTINCT FROM expected_audit_id THEN
            RAISE EXCEPTION 'development selection audit identity is invalid'
                USING ERRCODE = '23514';
        END IF;
        expected_artifact_id := public.formal_jsonb_content_id(
            pg_catalog.jsonb_build_object(
                'artifact_type', NEW.artifact_type,
                'content', content
            ),
            'artifact_'
        );
        IF NEW.artifact_id IS DISTINCT FROM expected_artifact_id THEN
            RAISE EXCEPTION 'development selection artifact identity is invalid'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    -- Preserve the generic paper ledger, but fail closed for every known
    -- formal type, every recursively formal-scoped payload, and any disguised
    -- outcome-bearing payload. This also closes the pre-registration return
    -- path: the development audit above is the sole formal artifact allowed
    -- without a primary registration and deliberately has no run_id.
    formal_candidate := NEW.artifact_type IN (
        'llm_invocation_reserved', 'llm_invocation_result',
        'global_forecast_bundle', 'formal_outcome_access',
        'formal_interim_integrity_failure',
        'formal_interim_operations_report',
        'formal_interim_calibration_report',
        'formal_interim_operational_integrity_report',
        'formal_final_verification_manifest',
        'formal_review_integrity_failure', 'formal_outcome_bundle',
        'formal_confirmatory_report'
    ) OR public.formal_jsonb_has_forbidden_outcome_key(content)
      OR EXISTS (
            SELECT 1
            FROM public.formal_trial_registry AS registry
            WHERE public.formal_jsonb_contains_key_value(
                    content, 'run_id', registry.run_id
                  )
               OR public.formal_jsonb_contains_key_value(
                    content, 'protocol_id', registry.protocol_id
                  )
      )
      OR EXISTS (
            SELECT 1
            FROM public.paper_runs AS run
            WHERE run.config_json::JSONB ->> 'engine' = 'formal-global-v2'
              AND (
                  public.formal_jsonb_contains_key_value(
                      content, 'run_id', run.run_id
                  )
                  OR public.formal_jsonb_contains_key_value(
                      content,
                      'protocol_id',
                      run.config_json::JSONB ->> 'protocol_id'
                  )
              )
      );
    IF NOT formal_candidate THEN
        RETURN NEW;
    END IF;

    artifact_run_id := content ->> 'run_id';
    SELECT registry.run_id, registry.protocol_id, registry.registration_id
      INTO primary_run_id, primary_protocol_id, primary_registration_id
      FROM public.formal_trial_registry AS registry
      JOIN public.paper_runs AS run ON run.run_id = registry.run_id
      JOIN public.paper_run_labels AS label
        ON label.run_id = registry.run_id
       AND label.label = 'confirmatory-trial'
       AND label.created_utc = registry.created_utc
       AND label.details_json = registry.details_json
     WHERE registry.run_id = artifact_run_id
       AND run.config_json::JSONB ->> 'engine' = 'formal-global-v2'
       AND run.config_json::JSONB ->> 'protocol_id' = registry.protocol_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'formal artifact has an unscoped or wrong primary identity'
            USING ERRCODE = '23514';
    END IF;
    IF artifact_run_id IS DISTINCT FROM primary_run_id
       OR (
            content ? 'protocol_id'
            AND content ->> 'protocol_id' IS DISTINCT FROM primary_protocol_id
       ) THEN
        RAISE EXCEPTION 'formal artifact has an unscoped or wrong primary identity'
            USING ERRCODE = '23514';
    END IF;

    SELECT pg_catalog.count(*)
      INTO completed_intervals
      FROM public.paper_interval_assignments AS assignment
     WHERE assignment.run_id = primary_run_id;

    expected_keys := CASE NEW.artifact_type
        WHEN 'llm_invocation_reserved' THEN ARRAY[
            'schema_version', 'invocation_id', 'scope', 'run_id', 'decision_date',
            'ordinal', 'stage', 'provider', 'requested_model', 'input_bundle_id',
            'prompt_id', 'prompt_bytes', 'max_prompt_bytes',
            'max_completion_tokens', 'max_calls_per_decision',
            'max_calls_per_utc_day', 'decision_counter_key', 'daily_counter_key',
            'utc_day', 'reserved_utc', 'reservation_counts'
        ]
        WHEN 'llm_invocation_result' THEN
            CASE content ->> 'status'
                WHEN 'failed' THEN ARRAY[
                    'schema_version', 'invocation_id', 'scope', 'run_id',
                    'decision_date', 'ordinal', 'stage', 'provider',
                    'requested_model', 'input_bundle_id', 'reservation_artifact_id',
                    'status', 'error_type', 'completed_utc', 'elapsed_ms'
                ]
                WHEN 'success' THEN ARRAY[
                    'schema_version', 'invocation_id', 'scope', 'run_id',
                    'decision_date', 'ordinal', 'stage', 'provider',
                    'requested_model', 'input_bundle_id', 'reservation_artifact_id',
                    'status', 'returned_model', 'model_id', 'response_id',
                    'usage_metadata', 'forecast_bundle_id', 'completed_utc', 'elapsed_ms'
                ]
                ELSE NULL
            END
        WHEN 'global_forecast_bundle' THEN ARRAY[
            'schema_version', 'protocol_id', 'build_id', 'run_id', 'decision_date',
            'attempt_ordinal',
            'universe', 'decision_context', 'coverage',
            'required_evidence_query_slots', 'evidence_policy',
            'x_cycle_availability',
            'evidence_selection_manifest', 'evidence_selection_coverage',
            'decision_semantics', 'trial_registration_id', 'llm_policy',
            'invocation_stage_order', 'champion', 'without_public_reaction',
            'public_reaction_only', 'market_inputs', 'stale_input_lineage',
            'strategy_inputs', 'strategy_targets'
        ]
        WHEN 'formal_outcome_access' THEN
            CASE WHEN content ? 'report_id' THEN ARRAY[
                'schema_version', 'run_id', 'protocol_id', 'review_gate',
                'access_kind', 'accessed_utc', 'report_id',
                'outcomes_may_be_read_after_this_receipt'
            ] ELSE ARRAY[
                'schema_version', 'run_id', 'protocol_id', 'review_gate',
                'access_kind', 'accessed_utc',
                'outcomes_may_be_read_after_this_receipt'
            ] END
        WHEN 'formal_interim_integrity_failure' THEN
            CASE WHEN content ? 'access_artifact_id' THEN ARRAY[
                'schema_version', 'run_id', 'protocol_id', 'review_gate',
                'reason_code', 'access_artifact_id'
            ] ELSE ARRAY[
                'schema_version', 'run_id', 'protocol_id', 'review_gate', 'reason_code'
            ] END
        WHEN 'formal_interim_operations_report' THEN ARRAY[
            'schema_version', 'report_type', 'protocol_id', 'run_id',
            'registration_id', 'review_gate', 'interim', 'scope',
            'completed_intervals', 'interpretation', 'report_id', 'outcomes_read',
            'assignment_completeness', 'attempt_operations', 'mark_completeness',
            'receipt_operations'
        ]
        WHEN 'formal_interim_calibration_report' THEN ARRAY[
            'schema_version', 'report_type', 'protocol_id', 'run_id',
            'registration_id', 'review_gate', 'interim', 'scope',
            'completed_intervals', 'interpretation', 'report_id',
            'successful_decision_sets', 'forecast_observations', 'calibration',
            'forecast_integrity', 'selected_evidence_occurrence_balance', 'missingness'
        ]
        WHEN 'formal_interim_operational_integrity_report' THEN ARRAY[
            'schema_version', 'report_type', 'protocol_id', 'run_id',
            'registration_id', 'review_gate', 'interim', 'scope',
            'completed_intervals', 'interpretation', 'report_id',
            'successful_decision_sets', 'outcomes_read',
            'strategy_identities_withheld', 'efficacy_statistics_withheld',
            'aggregate_integrity'
        ]
        WHEN 'formal_final_verification_manifest' THEN ARRAY[
            'schema_version', 'manifest_type', 'protocol_id', 'run_id',
            'coverage_rule', 'successful_applied_decisions', 'decision_dates',
            'verifications', 'external_calls_total', 'exact_coverage',
            'price_capture_manifest_id', 'verification_manifest_id'
        ]
        WHEN 'formal_review_integrity_failure' THEN
            CASE WHEN content ? 'access_artifact_id' THEN ARRAY[
                'schema_version', 'run_id', 'protocol_id', 'review_gate',
                'access_artifact_id', 'reason_code'
            ] ELSE ARRAY[
                'schema_version', 'run_id', 'protocol_id', 'review_gate', 'reason_code'
            ] END
        WHEN 'formal_outcome_bundle' THEN ARRAY[
            'schema_version', 'bundle_type', 'protocol_id', 'run_id',
            'registration_id', 'holding_intervals', 'successful_decision_sets',
            'synchronized_marks', 'verification_manifest_id',
            'verification_manifest_artifact_id', 'assignments', 'strategy_returns',
            'benchmark_returns'
        ]
        WHEN 'formal_confirmatory_report' THEN ARRAY[
            'schema_version', 'report_type', 'protocol_id', 'run_id',
            'registration_id', 'review_gate', 'interim', 'outcome_bundle_id',
            'verification_manifest_id', 'verification_manifest_artifact_id',
            'readout', 'report_id'
        ]
        ELSE NULL
    END;

    IF expected_keys IS NULL
       OR NOT public.formal_jsonb_exact_keys(content, expected_keys) THEN
        RAISE EXCEPTION 'formal artifact type or schema is not allowlisted'
            USING ERRCODE = '23514';
    END IF;

    IF pg_catalog.jsonb_typeof(content -> 'schema_version') <> 'number'
       OR (content ->> 'schema_version')::NUMERIC
            <> pg_catalog.trunc((content ->> 'schema_version')::NUMERIC)
       OR pg_catalog.jsonb_typeof(content -> 'run_id') <> 'string'
       OR COALESCE(content ->> 'run_id', '') = ''
       OR (
            content ? 'protocol_id'
            AND (
                pg_catalog.jsonb_typeof(content -> 'protocol_id') <> 'string'
                OR COALESCE(content ->> 'protocol_id', '') = ''
            )
       )
       OR (content ->> 'schema_version') IS DISTINCT FROM (
        CASE NEW.artifact_type
            WHEN 'llm_invocation_reserved' THEN '2'
            WHEN 'llm_invocation_result' THEN '2'
            WHEN 'global_forecast_bundle' THEN '3'
            ELSE '1'
        END
    ) THEN
        RAISE EXCEPTION 'formal artifact schema version is not frozen'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type IN ('llm_invocation_reserved', 'llm_invocation_result') THEN
        expected_invocation_id := public.formal_jsonb_content_id(
            pg_catalog.jsonb_build_object(
                'scope', content -> 'scope',
                'run_id', content -> 'run_id',
                'decision_date', content -> 'decision_date',
                'ordinal', content -> 'ordinal',
                'stage', content -> 'stage',
                'provider', content -> 'provider',
                'requested_model', content -> 'requested_model',
                'input_bundle_id', content -> 'input_bundle_id'
            ),
            'invocation_'
        );
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'invocation_id', 'scope', 'run_id', 'decision_date', 'stage',
                'provider', 'requested_model', 'input_bundle_id'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'string'
               OR COALESCE(content ->> required.field, '') = ''
        )
           OR pg_catalog.jsonb_typeof(content -> 'ordinal') <> 'number'
           OR (content ->> 'ordinal')::NUMERIC < 1
           OR (content ->> 'ordinal')::NUMERIC
                <> pg_catalog.trunc((content ->> 'ordinal')::NUMERIC)
           OR content ->> 'scope' IS DISTINCT FROM 'formal-global-v2'
           OR content ->> 'invocation_id' IS DISTINCT FROM expected_invocation_id THEN
            RAISE EXCEPTION 'formal invocation identity is invalid'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type = 'llm_invocation_reserved' AND (
        EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'prompt_id', 'decision_counter_key', 'daily_counter_key',
                'utc_day', 'reserved_utc'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'string'
               OR COALESCE(content ->> required.field, '') = ''
        )
        OR content ->> 'decision_counter_key'
            = content ->> 'daily_counter_key'
        OR EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'prompt_bytes', 'max_prompt_bytes', 'max_completion_tokens',
                'max_calls_per_decision', 'max_calls_per_utc_day'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'number'
               OR (content ->> required.field)::NUMERIC < 1
               OR (content ->> required.field)::NUMERIC
                    <> pg_catalog.trunc((content ->> required.field)::NUMERIC)
        )
        OR pg_catalog.jsonb_typeof(content -> 'reservation_counts') <> 'object'
        OR NOT pg_catalog.isfinite(
            (content ->> 'reserved_utc')::TIMESTAMPTZ
        )
        OR NOT public.formal_jsonb_exact_keys(
            content -> 'reservation_counts',
            ARRAY[content ->> 'decision_counter_key', content ->> 'daily_counter_key']
        )
        OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_each(content -> 'reservation_counts') AS counter(key, value)
            WHERE pg_catalog.jsonb_typeof(counter.value) <> 'number'
               OR (counter.value #>> '{}')::NUMERIC < 1
               OR (counter.value #>> '{}')::NUMERIC
                    <> pg_catalog.trunc((counter.value #>> '{}')::NUMERIC)
        )
    ) THEN
        RAISE EXCEPTION 'formal invocation reservation counters are invalid'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type = 'llm_invocation_result' AND (
        pg_catalog.jsonb_typeof(content -> 'reservation_artifact_id') <> 'string'
        OR content ->> 'reservation_artifact_id' !~ '^artifact_[0-9a-f]{24}$'
        OR pg_catalog.jsonb_typeof(content -> 'status') <> 'string'
        OR pg_catalog.jsonb_typeof(content -> 'completed_utc') <> 'string'
        OR COALESCE(content ->> 'completed_utc', '') = ''
        OR NOT pg_catalog.isfinite(
            (content ->> 'completed_utc')::TIMESTAMPTZ
        )
        OR pg_catalog.jsonb_typeof(content -> 'elapsed_ms') <> 'number'
        OR (content ->> 'elapsed_ms')::NUMERIC < 0
        OR (content ->> 'elapsed_ms')::NUMERIC
            <> pg_catalog.trunc((content ->> 'elapsed_ms')::NUMERIC)
        OR (
            content ->> 'status' = 'failed'
            AND (
                pg_catalog.jsonb_typeof(content -> 'error_type') <> 'string'
                OR COALESCE(content ->> 'error_type', '') = ''
            )
        )
        OR (
            content ->> 'status' = 'success'
            AND (
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.unnest(ARRAY[
                        'returned_model', 'model_id', 'response_id',
                        'forecast_bundle_id'
                    ]::TEXT[]) AS required(field)
                    WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'string'
                       OR COALESCE(content ->> required.field, '') = ''
                )
                OR pg_catalog.jsonb_typeof(content -> 'usage_metadata') <> 'object'
            )
        )
    ) THEN
        RAISE EXCEPTION 'formal invocation result fields are malformed'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type = 'llm_invocation_result' THEN
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended(
                'tradingagents:formal-llm-reservation:'
                    || (content ->> 'reservation_artifact_id'),
                0
            )
        );
        SELECT reservation.content_json::JSONB, reservation.created_utc
          INTO reservation_content, reservation_created_utc
          FROM public.paper_artifacts AS reservation
         WHERE reservation.artifact_id = content ->> 'reservation_artifact_id'
           AND reservation.artifact_type = 'llm_invocation_reserved';
        IF NOT FOUND
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(ARRAY[
                    'invocation_id', 'scope', 'run_id', 'decision_date',
                    'ordinal', 'stage', 'provider', 'requested_model',
                    'input_bundle_id'
                ]::TEXT[]) AS identity(field)
                WHERE reservation_content -> identity.field
                        IS DISTINCT FROM content -> identity.field
           )
           OR NEW.created_utc < reservation_created_utc
           OR (content ->> 'completed_utc')::TIMESTAMPTZ
                < (reservation_content ->> 'reserved_utc')::TIMESTAMPTZ
           OR EXTRACT(
                EPOCH FROM (content ->> 'completed_utc')::TIMESTAMPTZ
              ) < reservation_created_utc
           OR NEW.created_utc < EXTRACT(
                EPOCH FROM (reservation_content ->> 'reserved_utc')::TIMESTAMPTZ
              ) THEN
            RAISE EXCEPTION 'formal invocation result is not bound to its reservation'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM public.paper_artifacts AS prior_result
            WHERE prior_result.artifact_type = 'llm_invocation_result'
              AND prior_result.content_json::JSONB ->> 'reservation_artifact_id'
                    = content ->> 'reservation_artifact_id'
        ) THEN
            RAISE EXCEPTION 'formal invocation reservation already has a result'
                USING ERRCODE = '23505';
        END IF;
    END IF;

    IF NEW.artifact_type = 'global_forecast_bundle' AND (
        EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'protocol_id', 'build_id', 'run_id', 'decision_date',
                'trial_registration_id'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'string'
               OR COALESCE(content ->> required.field, '') = ''
        )
        OR content ->> 'trial_registration_id'
            IS DISTINCT FROM primary_registration_id
        OR pg_catalog.jsonb_typeof(content -> 'attempt_ordinal') <> 'number'
        OR (content ->> 'attempt_ordinal')::NUMERIC < 1
        OR (content ->> 'attempt_ordinal')::NUMERIC
            <> pg_catalog.trunc((content ->> 'attempt_ordinal')::NUMERIC)
        OR EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'decision_context', 'coverage', 'evidence_policy',
                'x_cycle_availability', 'evidence_selection_manifest',
                'evidence_selection_coverage', 'decision_semantics',
                'llm_policy', 'champion', 'without_public_reaction',
                'market_inputs', 'stale_input_lineage', 'strategy_inputs',
                'strategy_targets'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'object'
        )
        OR EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'universe', 'required_evidence_query_slots',
                'invocation_stage_order'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'array'
        )
        OR pg_catalog.jsonb_typeof(content -> 'public_reaction_only')
            NOT IN ('object', 'null')
    ) THEN
        RAISE EXCEPTION 'formal forecast registration or attempt identity is invalid'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type = 'global_forecast_bundle' THEN
        expected_artifact_id := public.formal_jsonb_content_id(content, 'artifact_');
    ELSE
        expected_artifact_id := public.formal_jsonb_content_id(
            pg_catalog.jsonb_build_object(
                'artifact_type', NEW.artifact_type,
                'content', content
            ),
            'artifact_'
        );
    END IF;
    IF NEW.artifact_id IS DISTINCT FROM expected_artifact_id THEN
        RAISE EXCEPTION 'formal artifact content identity is invalid'
            USING ERRCODE = '23514';
    END IF;

    gate := CASE NEW.artifact_type
        WHEN 'formal_interim_operations_report' THEN 20
        WHEN 'formal_interim_calibration_report' THEN 60
        WHEN 'formal_interim_operational_integrity_report' THEN 126
        ELSE NULL
    END;
    IF gate IS NOT NULL THEN
        expected_report_id := public.formal_jsonb_content_id(
            content - 'report_id', 'interim_report_'
        );
        IF completed_intervals <> gate
           OR pg_catalog.jsonb_typeof(content -> 'review_gate') <> 'number'
           OR (content ->> 'review_gate')::NUMERIC
                <> pg_catalog.trunc((content ->> 'review_gate')::NUMERIC)
           OR (content ->> 'review_gate')::INTEGER <> gate
           OR pg_catalog.jsonb_typeof(content -> 'completed_intervals') <> 'number'
           OR (content ->> 'completed_intervals')::NUMERIC
                <> pg_catalog.trunc((content ->> 'completed_intervals')::NUMERIC)
           OR (content ->> 'completed_intervals')::INTEGER <> gate
           OR pg_catalog.jsonb_typeof(content -> 'interim') <> 'boolean'
           OR content ->> 'interim' IS DISTINCT FROM 'true'
           OR pg_catalog.jsonb_typeof(content -> 'interpretation') <> 'string'
           OR COALESCE(content ->> 'interpretation', '') = ''
           OR content ->> 'registration_id'
                IS DISTINCT FROM primary_registration_id
           OR content ->> 'report_type' IS DISTINCT FROM (CASE gate
                WHEN 20 THEN 'global-event-v2-operations-only-interim'
                WHEN 60 THEN 'global-event-v2-data-calibration-interim'
                WHEN 126 THEN 'global-event-v2-blinded-operational-integrity-interim'
           END)
           OR content ->> 'scope' IS DISTINCT FROM (CASE gate
                WHEN 20 THEN 'operations-only'
                WHEN 60 THEN 'data-and-calibration-only'
                WHEN 126 THEN 'locked-descriptive-nonconclusive'
           END)
           OR content ->> 'report_id' IS DISTINCT FROM expected_report_id THEN
            RAISE EXCEPTION 'formal interim artifact is outside its exact gate'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.artifact_type = 'formal_interim_operations_report' AND (
            pg_catalog.jsonb_typeof(content -> 'outcomes_read') <> 'boolean'
            OR content ->> 'outcomes_read' IS DISTINCT FROM 'false'
            OR EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(ARRAY[
                    'assignment_completeness', 'attempt_operations',
                    'mark_completeness', 'receipt_operations'
                ]::TEXT[]) AS required(field)
                WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'object'
            )
        ) THEN
            RAISE EXCEPTION 'formal operations report contract is invalid'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.artifact_type = 'formal_interim_calibration_report' AND (
            EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(ARRAY[
                    'successful_decision_sets', 'forecast_observations'
                ]::TEXT[]) AS required(field)
                WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'number'
                   OR (content ->> required.field)::NUMERIC < 0
                   OR (content ->> required.field)::NUMERIC
                        <> pg_catalog.trunc((content ->> required.field)::NUMERIC)
            )
            OR EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(ARRAY[
                    'calibration', 'forecast_integrity',
                    'selected_evidence_occurrence_balance', 'missingness'
                ]::TEXT[]) AS required(field)
                WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'object'
            )
        ) THEN
            RAISE EXCEPTION 'formal calibration report contract is invalid'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.artifact_type = 'formal_interim_operational_integrity_report' AND (
            pg_catalog.jsonb_typeof(content -> 'successful_decision_sets') <> 'number'
            OR (content ->> 'successful_decision_sets')::NUMERIC < 0
            OR (content ->> 'successful_decision_sets')::NUMERIC
                <> pg_catalog.trunc(
                    (content ->> 'successful_decision_sets')::NUMERIC
                )
            OR pg_catalog.jsonb_typeof(content -> 'outcomes_read') <> 'boolean'
            OR content ->> 'outcomes_read' IS DISTINCT FROM 'false'
            OR pg_catalog.jsonb_typeof(
                content -> 'strategy_identities_withheld'
            ) <> 'boolean'
            OR content ->> 'strategy_identities_withheld' IS DISTINCT FROM 'true'
            OR pg_catalog.jsonb_typeof(
                content -> 'efficacy_statistics_withheld'
            ) <> 'boolean'
            OR content ->> 'efficacy_statistics_withheld' IS DISTINCT FROM 'true'
            OR pg_catalog.jsonb_typeof(content -> 'aggregate_integrity') <> 'object'
        ) THEN
            RAISE EXCEPTION 'formal operational-integrity report contract is invalid'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type IN (
        'formal_final_verification_manifest', 'formal_review_integrity_failure',
        'formal_outcome_bundle', 'formal_confirmatory_report'
    ) AND completed_intervals <> 252 THEN
        RAISE EXCEPTION 'formal final artifact requires exactly 252 intervals'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type IN (
        'llm_invocation_reserved', 'llm_invocation_result', 'global_forecast_bundle'
    ) AND completed_intervals >= 252 THEN
        RAISE EXCEPTION 'formal decision artifact is beyond the trial horizon'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type = 'formal_outcome_access' THEN
        gate := (content ->> 'review_gate')::INTEGER;
        access_kind := content ->> 'access_kind';
        IF pg_catalog.jsonb_typeof(content -> 'review_gate') <> 'number'
           OR (content ->> 'review_gate')::NUMERIC
                <> pg_catalog.trunc((content ->> 'review_gate')::NUMERIC)
           OR pg_catalog.jsonb_typeof(content -> 'access_kind') <> 'string'
           OR COALESCE(access_kind, '') = ''
           OR pg_catalog.jsonb_typeof(content -> 'accessed_utc') <> 'number'
           OR (content ->> 'accessed_utc')::DOUBLE PRECISION
                NOT BETWEEN '-Infinity'::DOUBLE PRECISION
                        AND 'Infinity'::DOUBLE PRECISION
           OR (content ->> 'accessed_utc')::DOUBLE PRECISION IN (
                '-Infinity'::DOUBLE PRECISION, 'Infinity'::DOUBLE PRECISION
           )
           OR pg_catalog.jsonb_typeof(
                content -> 'outcomes_may_be_read_after_this_receipt'
           ) <> 'boolean'
           OR content ->> 'outcomes_may_be_read_after_this_receipt' IS DISTINCT FROM 'true'
           OR NOT (
                (gate = 60 AND completed_intervals = 60
                 AND access_kind = 'automatic_interim_60_materialization'
                 AND NOT (content ? 'report_id'))
                OR (gate = 60 AND completed_intervals >= 60
                    AND access_kind = 'explicit_interim_60_report_view'
                    AND (content ? 'report_id'))
                OR (gate = 252 AND completed_intervals = 252
                    AND access_kind = 'automatic_final_report_materialization'
                    AND NOT (content ? 'report_id'))
                OR (gate = 252 AND completed_intervals = 252
                    AND access_kind = 'explicit_final_report_view'
                    AND (content ? 'report_id'))
           ) THEN
            RAISE EXCEPTION 'formal outcome access is outside its exact gate'
                USING ERRCODE = '23514';
        END IF;
        IF content ? 'report_id' AND NOT EXISTS (
            SELECT 1
            FROM public.paper_artifacts AS report
            WHERE report.artifact_type = (CASE gate
                    WHEN 60 THEN 'formal_interim_calibration_report'
                    WHEN 252 THEN 'formal_confirmatory_report'
                END)
              AND report.content_json::JSONB ->> 'run_id' = primary_run_id
              AND report.content_json::JSONB ->> 'report_id'
                    = content ->> 'report_id'
        ) THEN
            RAISE EXCEPTION 'formal outcome access report identity is not durable'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type = 'formal_interim_integrity_failure' THEN
        gate := (content ->> 'review_gate')::INTEGER;
        IF pg_catalog.jsonb_typeof(content -> 'review_gate') <> 'number'
           OR (content ->> 'review_gate')::NUMERIC
                <> pg_catalog.trunc((content ->> 'review_gate')::NUMERIC)
           OR gate NOT IN (20, 60, 126)
           OR completed_intervals <> gate
           OR content ->> 'reason_code' IS DISTINCT FROM 'integrity_validation_failed'
           OR (gate = 60) IS DISTINCT FROM (content ? 'access_artifact_id')
           OR (
                content ? 'access_artifact_id'
                AND NOT EXISTS (
                    SELECT 1
                    FROM public.paper_artifacts AS access
                    WHERE access.artifact_id = content ->> 'access_artifact_id'
                      AND access.artifact_type = 'formal_outcome_access'
                      AND access.content_json::JSONB ->> 'run_id' = primary_run_id
                      AND access.content_json::JSONB ->> 'review_gate' = gate::TEXT
                )
           ) THEN
            RAISE EXCEPTION 'formal interim failure is outside its exact gate'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type = 'formal_review_integrity_failure' THEN
        IF pg_catalog.jsonb_typeof(content -> 'review_gate') <> 'number'
           OR content ->> 'review_gate' IS DISTINCT FROM '252'
           OR content ->> 'reason_code' NOT IN (
                'offline_verification_failed', 'integrity_validation_failed'
           )
           OR (
                content ->> 'reason_code' = 'integrity_validation_failed'
           ) IS DISTINCT FROM (content ? 'access_artifact_id')
           OR (
                content ? 'access_artifact_id'
                AND NOT EXISTS (
                    SELECT 1
                    FROM public.paper_artifacts AS access
                    WHERE access.artifact_id = content ->> 'access_artifact_id'
                      AND access.artifact_type = 'formal_outcome_access'
                      AND access.content_json::JSONB ->> 'run_id' = primary_run_id
                      AND access.content_json::JSONB ->> 'review_gate' = '252'
                )
           ) THEN
            RAISE EXCEPTION 'formal review failure reason is not allowlisted'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type = 'formal_outcome_bundle' AND (
        content ->> 'bundle_type' IS DISTINCT FROM 'global-event-v2-final-outcomes'
        OR content ->> 'registration_id' IS DISTINCT FROM primary_registration_id
        OR pg_catalog.jsonb_typeof(content -> 'holding_intervals') <> 'number'
        OR content ->> 'holding_intervals' IS DISTINCT FROM '252'
        OR EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(ARRAY[
                'successful_decision_sets', 'synchronized_marks'
            ]::TEXT[]) AS required(field)
            WHERE pg_catalog.jsonb_typeof(content -> required.field) <> 'number'
               OR (content ->> required.field)::NUMERIC < 0
               OR (content ->> required.field)::NUMERIC
                    <> pg_catalog.trunc((content ->> required.field)::NUMERIC)
        )
        OR pg_catalog.jsonb_typeof(content -> 'assignments') <> 'array'
        OR pg_catalog.jsonb_typeof(content -> 'strategy_returns') <> 'object'
        OR pg_catalog.jsonb_typeof(content -> 'benchmark_returns') <> 'array'
        OR content ->> 'verification_manifest_id'
            !~ '^formal_verification_[0-9a-f]{24}$'
        OR content ->> 'verification_manifest_artifact_id'
            !~ '^artifact_[0-9a-f]{24}$'
        OR NOT EXISTS (
            SELECT 1
            FROM public.paper_artifacts AS verification
            WHERE verification.artifact_id
                    = content ->> 'verification_manifest_artifact_id'
              AND verification.artifact_type
                    = 'formal_final_verification_manifest'
              AND verification.content_json::JSONB ->> 'run_id' = primary_run_id
              AND verification.content_json::JSONB ->> 'verification_manifest_id'
                    = content ->> 'verification_manifest_id'
        )
    ) THEN
        RAISE EXCEPTION 'formal outcome bundle contract is invalid'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.artifact_type = 'formal_confirmatory_report' THEN
        expected_report_id := public.formal_jsonb_content_id(
            content - 'report_id', 'formal_report_'
        );
        IF content ->> 'report_type'
                IS DISTINCT FROM 'global-event-v2-sole-confirmatory-readout'
           OR content ->> 'registration_id' IS DISTINCT FROM primary_registration_id
           OR pg_catalog.jsonb_typeof(content -> 'review_gate') <> 'number'
           OR content ->> 'review_gate' IS DISTINCT FROM '252'
           OR pg_catalog.jsonb_typeof(content -> 'interim') <> 'boolean'
           OR content ->> 'interim' IS DISTINCT FROM 'false'
           OR pg_catalog.jsonb_typeof(content -> 'readout') <> 'object'
           OR content -> 'readout' ->> 'live_capital_approved' IS DISTINCT FROM 'false'
           OR content ->> 'outcome_bundle_id'
                !~ '^outcome_bundle_[0-9a-f]{24}$'
           OR content ->> 'verification_manifest_id'
                !~ '^formal_verification_[0-9a-f]{24}$'
           OR content ->> 'verification_manifest_artifact_id'
                !~ '^artifact_[0-9a-f]{24}$'
           OR content ->> 'report_id' IS DISTINCT FROM expected_report_id
           OR NOT EXISTS (
                SELECT 1
                FROM public.paper_artifacts AS outcome
                WHERE outcome.artifact_type = 'formal_outcome_bundle'
                  AND outcome.content_json::JSONB ->> 'run_id' = primary_run_id
                  AND public.formal_jsonb_content_id(
                        outcome.content_json::JSONB, 'outcome_bundle_'
                      ) = content ->> 'outcome_bundle_id'
                  AND outcome.content_json::JSONB ->> 'verification_manifest_id'
                        = content ->> 'verification_manifest_id'
                  AND outcome.content_json::JSONB
                        ->> 'verification_manifest_artifact_id'
                        = content ->> 'verification_manifest_artifact_id'
           )
           OR NOT EXISTS (
                SELECT 1
                FROM public.paper_artifacts AS verification
                WHERE verification.artifact_id
                        = content ->> 'verification_manifest_artifact_id'
                  AND verification.artifact_type
                        = 'formal_final_verification_manifest'
                  AND verification.content_json::JSONB ->> 'run_id' = primary_run_id
                  AND verification.content_json::JSONB ->> 'verification_manifest_id'
                        = content ->> 'verification_manifest_id'
           ) THEN
            RAISE EXCEPTION 'formal confirmatory report contract is invalid'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type = 'formal_final_verification_manifest' THEN
        expected_manifest_id := public.formal_jsonb_content_id(
            content - 'verification_manifest_id', 'formal_verification_'
        );
        IF content ->> 'manifest_type'
                IS DISTINCT FROM 'global-event-v2-final-offline-verification'
           OR content ->> 'coverage_rule'
                IS DISTINCT FROM 'every-successful-applied-decision-exactly-once'
           OR pg_catalog.jsonb_typeof(
                content -> 'successful_applied_decisions'
           ) <> 'number'
           OR (content ->> 'successful_applied_decisions')::NUMERIC < 0
           OR (content ->> 'successful_applied_decisions')::NUMERIC
                <> pg_catalog.trunc(
                    (content ->> 'successful_applied_decisions')::NUMERIC
                )
           OR pg_catalog.jsonb_typeof(content -> 'decision_dates') <> 'array'
           OR pg_catalog.jsonb_typeof(content -> 'verifications') <> 'array'
           OR pg_catalog.jsonb_typeof(content -> 'external_calls_total') <> 'number'
           OR content ->> 'external_calls_total' IS DISTINCT FROM '0'
           OR pg_catalog.jsonb_typeof(content -> 'exact_coverage') <> 'boolean'
           OR content ->> 'exact_coverage' IS DISTINCT FROM 'true'
           OR COALESCE(content ->> 'price_capture_manifest_id', '') = ''
           OR content ->> 'verification_manifest_id'
                IS DISTINCT FROM expected_manifest_id THEN
            RAISE EXCEPTION 'formal final verification manifest is not frozen'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.artifact_type NOT IN (
        'formal_outcome_bundle', 'formal_confirmatory_report'
    ) AND public.formal_jsonb_has_forbidden_outcome_key(content) THEN
        RAISE EXCEPTION 'pre-final formal artifact contains a forbidden outcome key'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION public.enforce_formal_label_governance()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    details JSONB;
    primary_run_id TEXT;
    primary_protocol_id TEXT;
    run_engine TEXT;
    run_config JSONB;
    protocol_manifest JSONB;
    completed_intervals INTEGER;
    expected_keys TEXT[];
    gate INTEGER;
    expected_scope TEXT;
    report_type TEXT;
    expected_analysis_id TEXT;
    expected_review_gates_id TEXT;
    expected_decision_semantics_id TEXT;
    expected_registration_id TEXT;
BEGIN
    IF NEW.created_utc IN (
        '-Infinity'::DOUBLE PRECISION,
        'Infinity'::DOUBLE PRECISION,
        'NaN'::DOUBLE PRECISION
    ) THEN
        RAISE EXCEPTION 'formal label timestamp must be finite'
            USING ERRCODE = '23514';
    END IF;
    SELECT run.config_json::JSONB, registry.run_id,
           registry.protocol_id, experiment.manifest_json::JSONB
      INTO run_config, primary_run_id, primary_protocol_id, protocol_manifest
      FROM public.paper_runs AS run
      LEFT JOIN public.formal_trial_registry AS registry
        ON registry.run_id = run.run_id
       AND registry.protocol_id = run.config_json::JSONB ->> 'protocol_id'
      LEFT JOIN public.experiment_registry AS experiment
        ON experiment.protocol_id = registry.protocol_id
     WHERE run.run_id = NEW.run_id;
    run_engine := run_config ->> 'engine';
    IF primary_run_id IS NULL THEN
        IF run_engine = 'formal-global-v2'
           OR NEW.label = 'confirmatory-trial'
           OR NEW.label LIKE 'formal-review-%' THEN
            RAISE EXCEPTION 'formal label has a wrong primary run identity'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.run_id IS DISTINCT FROM primary_run_id THEN
        RAISE EXCEPTION 'formal label has a wrong primary run identity'
            USING ERRCODE = '23514';
    END IF;

    details := NEW.details_json::JSONB;
    IF pg_catalog.jsonb_typeof(details) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'formal label details must be an object'
            USING ERRCODE = '23514';
    END IF;
    IF public.formal_jsonb_has_forbidden_outcome_key(details) THEN
        RAISE EXCEPTION 'formal label contains a forbidden outcome key'
            USING ERRCODE = '23514';
    END IF;
    SELECT pg_catalog.count(*) INTO completed_intervals
      FROM public.paper_interval_assignments AS assignment
     WHERE assignment.run_id = primary_run_id;

    IF NEW.label = 'confirmatory-trial' THEN
        expected_keys := ARRAY[
            'schema_version', 'registration_type', 'run_id', 'protocol_id',
            'analysis_id', 'review_gates_id', 'decision_semantics_id',
            'outcome_semantics_id', 'configuration_binding',
            'registered_strategies', 'confirmatory_family', 'secondary_family',
            'trial_clock', 'parent_run_id', 'outcomes_accessed_before_registration',
            'registration_id'
        ];
        expected_registration_id := public.formal_jsonb_content_id(
            details - 'registration_id', 'registration_'
        );
        expected_analysis_id := public.formal_jsonb_content_id(
            protocol_manifest -> 'analysis', 'analysis_'
        );
        expected_review_gates_id := public.formal_jsonb_content_id(
            protocol_manifest -> 'review_gates', 'reviews_'
        );
        expected_decision_semantics_id := public.formal_jsonb_content_id(
            (run_config -> 'decision_semantics') - 'semantic_id', 'semantics_'
        );
        IF NOT public.formal_jsonb_exact_keys(details, expected_keys)
           OR details ->> 'run_id' IS DISTINCT FROM primary_run_id
           OR details ->> 'protocol_id' IS DISTINCT FROM primary_protocol_id
           OR pg_catalog.jsonb_typeof(protocol_manifest) <> 'object'
           OR pg_catalog.jsonb_typeof(protocol_manifest -> 'analysis') <> 'object'
           OR pg_catalog.jsonb_typeof(protocol_manifest -> 'review_gates') <> 'object'
           OR pg_catalog.jsonb_typeof(protocol_manifest -> 'strategies') <> 'array'
           OR pg_catalog.jsonb_typeof(
                protocol_manifest -> 'analysis' -> 'multiplicity'
           ) <> 'object'
           OR pg_catalog.jsonb_typeof(
                protocol_manifest -> 'analysis' -> 'multiplicity'
                    -> 'confirmatory_family'
           ) <> 'array'
           OR pg_catalog.jsonb_typeof(
                protocol_manifest -> 'analysis' -> 'multiplicity'
                    -> 'secondary_family'
           ) <> 'array'
           OR pg_catalog.jsonb_typeof(
                protocol_manifest -> 'analysis' -> 'trial_clock'
           ) <> 'object'
           OR pg_catalog.jsonb_typeof(run_config -> 'decision_semantics') <> 'object'
           OR pg_catalog.jsonb_typeof(run_config -> 'configuration_binding') <> 'object'
           OR pg_catalog.jsonb_typeof(details -> 'schema_version') <> 'number'
           OR details ->> 'schema_version' IS DISTINCT FROM '2'
           OR details ->> 'registration_type' IS DISTINCT FROM 'confirmatory'
           OR details ->> 'analysis_id' IS DISTINCT FROM expected_analysis_id
           OR details ->> 'review_gates_id'
                IS DISTINCT FROM expected_review_gates_id
           OR details ->> 'decision_semantics_id'
                IS DISTINCT FROM expected_decision_semantics_id
           OR run_config -> 'decision_semantics' ->> 'semantic_id'
                IS DISTINCT FROM expected_decision_semantics_id
           OR details ->> 'outcome_semantics_id'
                IS DISTINCT FROM run_config ->> 'outcome_semantics_id'
           OR details -> 'configuration_binding'
                IS DISTINCT FROM run_config -> 'configuration_binding'
           OR details -> 'registered_strategies'
                IS DISTINCT FROM protocol_manifest -> 'strategies'
           OR details -> 'confirmatory_family' IS DISTINCT FROM
                protocol_manifest -> 'analysis' -> 'multiplicity'
                    -> 'confirmatory_family'
           OR details -> 'secondary_family' IS DISTINCT FROM
                protocol_manifest -> 'analysis' -> 'multiplicity'
                    -> 'secondary_family'
           OR details -> 'trial_clock' IS DISTINCT FROM
                protocol_manifest -> 'analysis' -> 'trial_clock'
           OR details ->> 'outcome_semantics_id'
                !~ '^outcome_semantics_[0-9a-f]{64}$'
           OR pg_catalog.jsonb_typeof(details -> 'configuration_binding') <> 'object'
           OR NOT public.formal_jsonb_exact_keys(
                details -> 'configuration_binding',
                ARRAY[
                    'collector_configuration_id',
                    'paper_decision_configuration_id',
                    'paper_marker_configuration_id',
                    'configuration_manifest_id'
                ]
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.jsonb_each(
                    details -> 'configuration_binding'
                ) AS binding(key, value)
                WHERE pg_catalog.jsonb_typeof(binding.value) <> 'string'
                   OR binding.value #>> '{}' !~ '^config_[0-9a-f]{24}$'
           )
           OR EXISTS (
                SELECT 1
                FROM pg_catalog.unnest(ARRAY[
                    'analysis_id', 'review_gates_id', 'decision_semantics_id',
                    'registration_id'
                ]::TEXT[]) AS required(field)
                WHERE pg_catalog.jsonb_typeof(details -> required.field) <> 'string'
                   OR COALESCE(details ->> required.field, '') = ''
           )
           OR pg_catalog.jsonb_typeof(details -> 'registered_strategies') <> 'array'
           OR pg_catalog.jsonb_typeof(details -> 'confirmatory_family') <> 'array'
           OR pg_catalog.jsonb_typeof(details -> 'secondary_family') <> 'array'
           OR pg_catalog.jsonb_typeof(details -> 'trial_clock') <> 'object'
           OR details -> 'parent_run_id' IS DISTINCT FROM 'null'::JSONB
           OR pg_catalog.jsonb_typeof(
                details -> 'outcomes_accessed_before_registration'
           ) <> 'boolean'
           OR details ->> 'outcomes_accessed_before_registration' IS DISTINCT FROM 'false'
           OR details ->> 'registration_id'
                IS DISTINCT FROM expected_registration_id
           OR details ->> 'registration_id'
                IS DISTINCT FROM run_config ->> 'trial_registration_id'
           OR completed_intervals <> 0
           OR NOT EXISTS (
                SELECT 1 FROM public.formal_trial_registry AS registry
                WHERE registry.run_id = NEW.run_id
                  AND registry.protocol_id = details ->> 'protocol_id'
                  AND registry.registration_id = details ->> 'registration_id'
                  AND registry.details_json = NEW.details_json
                  AND registry.created_utc = NEW.created_utc
           ) THEN
            RAISE EXCEPTION 'confirmatory label is not exact and pre-activity'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    gate := CASE NEW.label
        WHEN 'formal-review-20-operations' THEN 20
        WHEN 'formal-review-60-calibration' THEN 60
        WHEN 'formal-review-126-descriptive' THEN 126
        WHEN 'formal-review-252-complete' THEN 252
        ELSE NULL
    END;
    IF gate IS NULL THEN
        RAISE EXCEPTION 'formal label is not allowlisted'
            USING ERRCODE = '23514';
    END IF;
    IF pg_catalog.jsonb_typeof(details -> 'protocol_id') <> 'string'
       OR pg_catalog.jsonb_typeof(details -> 'review_gate') <> 'number'
       OR (details ->> 'review_gate')::NUMERIC
            <> pg_catalog.trunc((details ->> 'review_gate')::NUMERIC)
       OR details ->> 'protocol_id' IS DISTINCT FROM primary_protocol_id
       OR (details ->> 'review_gate')::INTEGER <> gate
       OR completed_intervals <> gate THEN
        RAISE EXCEPTION 'formal label is outside its exact gate'
            USING ERRCODE = '23514';
    END IF;

    IF gate < 252 THEN
        expected_scope := CASE gate
            WHEN 20 THEN 'operations-only'
            WHEN 60 THEN 'data-and-calibration-only'
            WHEN 126 THEN 'locked-descriptive-nonconclusive'
        END;
        report_type := CASE gate
            WHEN 20 THEN 'formal_interim_operations_report'
            WHEN 60 THEN 'formal_interim_calibration_report'
            WHEN 126 THEN 'formal_interim_operational_integrity_report'
        END;
        expected_keys := ARRAY[
            'schema_version', 'protocol_id', 'review_gate', 'scope', 'report_id',
            'report_artifact_id', 'outcomes_withheld'
        ];
        IF NOT public.formal_jsonb_exact_keys(details, expected_keys)
           OR pg_catalog.jsonb_typeof(details -> 'schema_version') <> 'number'
           OR details ->> 'schema_version' IS DISTINCT FROM '1'
           OR details ->> 'scope' IS DISTINCT FROM expected_scope
           OR details ->> 'report_id' !~ '^interim_report_[0-9a-f]{24}$'
           OR details ->> 'report_artifact_id' !~ '^artifact_[0-9a-f]{24}$'
           OR pg_catalog.jsonb_typeof(details -> 'outcomes_withheld') <> 'boolean'
           OR details ->> 'outcomes_withheld' IS DISTINCT FROM 'true'
           OR NOT EXISTS (
                SELECT 1 FROM public.paper_artifacts AS artifact
                WHERE artifact.artifact_id = details ->> 'report_artifact_id'
                  AND artifact.artifact_type = report_type
                  AND artifact.content_json::JSONB ->> 'run_id' = primary_run_id
                  AND artifact.content_json::JSONB ->> 'report_id'
                        = details ->> 'report_id'
                  AND artifact.content_json::JSONB ->> 'review_gate' = gate::TEXT
           ) THEN
            RAISE EXCEPTION 'formal interim label is not bound to its exact report'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    expected_keys := ARRAY[
        'schema_version', 'protocol_id', 'review_gate', 'outcome_bundle_id',
        'outcome_bundle_artifact_id', 'report_id', 'report_artifact_id',
        'verification_manifest_id', 'verification_manifest_artifact_id',
        'live_capital_approved'
    ];
    IF NOT public.formal_jsonb_exact_keys(details, expected_keys)
       OR pg_catalog.jsonb_typeof(details -> 'schema_version') <> 'number'
       OR details ->> 'schema_version' IS DISTINCT FROM '2'
       OR details ->> 'outcome_bundle_id'
            !~ '^outcome_bundle_[0-9a-f]{24}$'
       OR details ->> 'outcome_bundle_artifact_id'
            !~ '^artifact_[0-9a-f]{24}$'
       OR details ->> 'report_id' !~ '^formal_report_[0-9a-f]{24}$'
       OR details ->> 'report_artifact_id' !~ '^artifact_[0-9a-f]{24}$'
       OR details ->> 'verification_manifest_id'
            !~ '^formal_verification_[0-9a-f]{24}$'
       OR details ->> 'verification_manifest_artifact_id'
            !~ '^artifact_[0-9a-f]{24}$'
       OR pg_catalog.jsonb_typeof(details -> 'live_capital_approved') <> 'boolean'
       OR details ->> 'live_capital_approved' IS DISTINCT FROM 'false'
       OR NOT EXISTS (
            SELECT 1 FROM public.paper_artifacts AS artifact
            WHERE artifact.artifact_id = details ->> 'outcome_bundle_artifact_id'
              AND artifact.artifact_type = 'formal_outcome_bundle'
              AND artifact.content_json::JSONB ->> 'run_id' = primary_run_id
              AND public.formal_jsonb_content_id(
                    artifact.content_json::JSONB, 'outcome_bundle_'
                  ) = details ->> 'outcome_bundle_id'
              AND artifact.content_json::JSONB ->> 'verification_manifest_id'
                    = details ->> 'verification_manifest_id'
              AND artifact.content_json::JSONB
                    ->> 'verification_manifest_artifact_id'
                    = details ->> 'verification_manifest_artifact_id'
       )
       OR NOT EXISTS (
            SELECT 1 FROM public.paper_artifacts AS artifact
            WHERE artifact.artifact_id = details ->> 'report_artifact_id'
              AND artifact.artifact_type = 'formal_confirmatory_report'
              AND artifact.content_json::JSONB ->> 'run_id' = primary_run_id
              AND artifact.content_json::JSONB ->> 'report_id' = details ->> 'report_id'
              AND artifact.content_json::JSONB ->> 'outcome_bundle_id'
                    = details ->> 'outcome_bundle_id'
              AND artifact.content_json::JSONB ->> 'verification_manifest_id'
                    = details ->> 'verification_manifest_id'
              AND artifact.content_json::JSONB
                    ->> 'verification_manifest_artifact_id'
                    = details ->> 'verification_manifest_artifact_id'
       )
       OR NOT EXISTS (
            SELECT 1 FROM public.paper_artifacts AS artifact
            WHERE artifact.artifact_id = details ->> 'verification_manifest_artifact_id'
              AND artifact.artifact_type = 'formal_final_verification_manifest'
              AND artifact.content_json::JSONB ->> 'run_id' = primary_run_id
              AND artifact.content_json::JSONB ->> 'verification_manifest_id'
                    = details ->> 'verification_manifest_id'
       ) THEN
        RAISE EXCEPTION 'formal final label is not bound to exact final artifacts'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS govern_formal_artifact_insert ON public.paper_artifacts;
CREATE TRIGGER govern_formal_artifact_insert
    BEFORE INSERT ON public.paper_artifacts
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_artifact_governance();

DROP TRIGGER IF EXISTS govern_formal_label_insert ON public.paper_run_labels;
CREATE TRIGGER govern_formal_label_insert
    BEFORE INSERT ON public.paper_run_labels
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_label_governance();

-- Reassert append-only protection even on a schema-only restore.
DROP TRIGGER IF EXISTS immutable_paper_artifacts ON public.paper_artifacts;
CREATE TRIGGER immutable_paper_artifacts
    BEFORE UPDATE OR DELETE ON public.paper_artifacts
    FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation();
DROP TRIGGER IF EXISTS immutable_paper_run_labels ON public.paper_run_labels;
CREATE TRIGGER immutable_paper_run_labels
    BEFORE UPDATE OR DELETE ON public.paper_run_labels
    FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation();

REVOKE ALL ON FUNCTION public.formal_jsonb_exact_keys(JSONB, TEXT[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_jsonb_has_forbidden_outcome_key(JSONB) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_jsonb_contains_key_value(JSONB, TEXT, TEXT)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.formal_jsonb_content_id(JSONB, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_artifact_governance() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_label_governance() FROM PUBLIC;

REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.paper_artifacts,
    public.paper_run_labels FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-paper'
    ) THEN
        GRANT EXECUTE ON FUNCTION public.formal_jsonb_exact_keys(JSONB, TEXT[])
            TO "tradingagents-paper";
        GRANT EXECUTE ON FUNCTION public.formal_jsonb_has_forbidden_outcome_key(JSONB)
            TO "tradingagents-paper";
        GRANT EXECUTE ON FUNCTION public.formal_jsonb_contains_key_value(
            JSONB, TEXT, TEXT
        ) TO "tradingagents-paper";
        GRANT EXECUTE ON FUNCTION public.formal_jsonb_content_id(JSONB, TEXT)
            TO "tradingagents-paper";
        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.paper_artifacts,
            public.paper_run_labels FROM "tradingagents-paper";
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-ingest-v2'
    ) THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.paper_artifacts,
            public.paper_run_labels FROM "tradingagents-ingest-v2";
    END IF;
END
$$;

COMMENT ON FUNCTION public.enforce_formal_artifact_governance() IS
    'tradingagents.formal-artifact-governance.v1;normalized-prosrc-sha256=09a18750fe2a369ab2ca060d6603c0dd0a0b953bbffb2fca87d167cbab7e4b8d';
COMMENT ON FUNCTION public.enforce_formal_label_governance() IS
    'tradingagents.formal-label-governance.v1;normalized-prosrc-sha256=d931191828411953462cba13bae58f78897eedaec68094fd87143876404235ca';

COMMIT;
