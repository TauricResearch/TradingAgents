-- Point-in-time, content-bound price capture for the formal paper experiment.
-- Apply with collector and paper workers paused.  Existing formal price/mark
-- activity cannot be upgraded honestly because its provider vintage and
-- capture deadline were not durably bound, so this migration fails closed.

BEGIN;

SET LOCAL search_path = pg_catalog, public;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.paper_runs AS run
        WHERE run.config_json::jsonb ->> 'engine' = 'formal-global-v2'
          AND (
              EXISTS (SELECT 1 FROM public.paper_marks AS mark
                      WHERE mark.run_id = run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_price_receipts AS receipt
                         WHERE receipt.run_id = run.run_id)
              OR EXISTS (SELECT 1 FROM public.paper_interval_assignments AS assignment
                         WHERE assignment.run_id = run.run_id)
          )
    ) THEN
        RAISE EXCEPTION
            'formal price integrity migration requires zero existing formal marks/receipts';
    END IF;
END
$$;

ALTER TABLE public.paper_price_receipts
    ADD COLUMN IF NOT EXISTS capture_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS price_receipt_id TEXT,
    ADD COLUMN IF NOT EXISTS vendor_snapshot_id TEXT,
    ADD COLUMN IF NOT EXISTS receipt_identity_json TEXT,
    ADD COLUMN IF NOT EXISTS vendor_snapshot_identity_json TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_price_receipt_identity
    ON public.paper_price_receipts (price_receipt_id)
    WHERE price_receipt_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.paper_price_capture_attempt_events (
    run_id TEXT NOT NULL,
    session_date TEXT NOT NULL,
    attempt_ordinal INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    created_utc DOUBLE PRECISION NOT NULL,
    observed_utc DOUBLE PRECISION NOT NULL DEFAULT (
        EXTRACT(epoch FROM pg_catalog.clock_timestamp())
    ),
    reason_code TEXT,
    PRIMARY KEY (run_id, session_date, attempt_ordinal, event_type),
    CHECK (attempt_ordinal > 0),
    CHECK (created_utc > '-Infinity'::DOUBLE PRECISION
           AND created_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (observed_utc > '-Infinity'::DOUBLE PRECISION
           AND observed_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (event_type IN ('started', 'failed')),
    CHECK (
        (event_type = 'started' AND reason_code IS NULL)
        OR (event_type = 'failed' AND reason_code IN (
            'market_data_failed', 'capture_window_expired',
            'persistence_failed', 'unexpected_failure'
        ))
    )
);

CREATE TABLE IF NOT EXISTS public.paper_price_capture_batches (
    run_id TEXT NOT NULL,
    session_date TEXT NOT NULL,
    capture_batch_id TEXT NOT NULL UNIQUE,
    attempt_ordinal INTEGER NOT NULL,
    from_session_date TEXT,
    scheduled_utc DOUBLE PRECISION NOT NULL,
    started_utc DOUBLE PRECISION NOT NULL,
    completed_utc DOUBLE PRECISION NOT NULL,
    persisted_utc DOUBLE PRECISION NOT NULL DEFAULT (
        EXTRACT(epoch FROM pg_catalog.clock_timestamp())
    ),
    deadline_utc DOUBLE PRECISION NOT NULL,
    vendor TEXT NOT NULL,
    paper_build_id TEXT NOT NULL,
    return_vector_id TEXT,
    receipt_manifest_json TEXT NOT NULL,
    capture_identity_json TEXT NOT NULL,
    return_vector_identity_json TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_date),
    CHECK (attempt_ordinal > 0),
    CHECK (capture_batch_id ~ '^price_batch_[0-9a-f]{24}$'),
    CHECK (return_vector_id IS NULL
           OR return_vector_id ~ '^return_vector_[0-9a-f]{24}$'),
    CHECK (scheduled_utc > '-Infinity'::DOUBLE PRECISION
           AND scheduled_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (started_utc > '-Infinity'::DOUBLE PRECISION
           AND started_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (completed_utc > '-Infinity'::DOUBLE PRECISION
           AND completed_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (persisted_utc > '-Infinity'::DOUBLE PRECISION
           AND persisted_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (deadline_utc > '-Infinity'::DOUBLE PRECISION
           AND deadline_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (scheduled_utc <= started_utc
           AND started_utc <= completed_utc
           AND completed_utc < deadline_utc)
);

CREATE TABLE IF NOT EXISTS public.paper_price_integrity_failures (
    run_id TEXT NOT NULL,
    session_date TEXT NOT NULL,
    failure_id TEXT NOT NULL UNIQUE,
    detected_utc DOUBLE PRECISION NOT NULL,
    scheduled_utc DOUBLE PRECISION NOT NULL,
    deadline_utc DOUBLE PRECISION NOT NULL,
    last_attempt_ordinal INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_date),
    UNIQUE (run_id),
    CHECK (last_attempt_ordinal >= 0),
    CHECK (failure_id ~ '^price_failure_[0-9a-f]{24}$'),
    CHECK (detected_utc > '-Infinity'::DOUBLE PRECISION
           AND detected_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (scheduled_utc > '-Infinity'::DOUBLE PRECISION
           AND scheduled_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (deadline_utc > '-Infinity'::DOUBLE PRECISION
           AND deadline_utc < 'Infinity'::DOUBLE PRECISION),
    CHECK (detected_utc >= deadline_utc),
    CHECK (reason_code IN (
        'capture_deadline_expired', 'capture_crossed_deadline',
        'missing_provider_daily_open', 'unsupported_corporate_action',
        'invalid_vendor_snapshot'
    ))
);

ALTER TABLE public.paper_price_capture_attempt_events
    ALTER COLUMN observed_utc SET DEFAULT (
        EXTRACT(epoch FROM pg_catalog.clock_timestamp())
    ),
    ALTER COLUMN observed_utc SET NOT NULL;
ALTER TABLE public.paper_price_capture_batches
    ADD COLUMN IF NOT EXISTS paper_build_id TEXT;
ALTER TABLE public.paper_price_capture_batches
    ALTER COLUMN paper_build_id SET NOT NULL;
ALTER TABLE public.paper_price_capture_batches
    DROP CONSTRAINT IF EXISTS paper_price_capture_batches_build_id_check;
ALTER TABLE public.paper_price_capture_batches
    ADD CONSTRAINT paper_price_capture_batches_build_id_check
    CHECK (paper_build_id ~ '^build_[0-9a-f]{24}$');
ALTER TABLE public.paper_price_capture_batches
    ALTER COLUMN persisted_utc SET DEFAULT (
        EXTRACT(epoch FROM pg_catalog.clock_timestamp())
    ),
    ALTER COLUMN persisted_utc SET NOT NULL;

CREATE OR REPLACE FUNCTION public.enforce_formal_price_attempt_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    last_ordinal INTEGER;
    started_utc DOUBLE PRECISION;
BEGIN
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    NEW.observed_utc := EXTRACT(
        epoch FROM pg_catalog.clock_timestamp()
    );
    IF pg_catalog.abs(NEW.created_utc - NEW.observed_utc) > 30.0 THEN
        RAISE EXCEPTION 'formal price attempt time is not server-current'
            USING ERRCODE = '23514';
    END IF;
    SELECT COALESCE(MAX(event.attempt_ordinal), 0)
      INTO last_ordinal
      FROM public.paper_price_capture_attempt_events AS event
     WHERE event.run_id = NEW.run_id
       AND event.session_date = NEW.session_date;
    IF NEW.event_type = 'started' THEN
        IF NEW.attempt_ordinal IS DISTINCT FROM last_ordinal + 1
           OR EXISTS (
               SELECT 1 FROM public.paper_price_capture_batches AS batch
               WHERE batch.run_id = NEW.run_id
                 AND batch.session_date = NEW.session_date
           )
           OR EXISTS (
               SELECT 1 FROM public.paper_price_integrity_failures AS failure
               WHERE failure.run_id = NEW.run_id
           ) THEN
            RAISE EXCEPTION 'formal price attempt ordinals must be contiguous'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        SELECT event.created_utc
          INTO STRICT started_utc
          FROM public.paper_price_capture_attempt_events AS event
         WHERE event.run_id = NEW.run_id
           AND event.session_date = NEW.session_date
           AND event.attempt_ordinal = NEW.attempt_ordinal
           AND event.event_type = 'started';
        IF NEW.attempt_ordinal IS DISTINCT FROM last_ordinal
           OR NEW.created_utc < started_utc
           OR EXISTS (
               SELECT 1 FROM public.paper_price_capture_batches AS batch
               WHERE batch.run_id = NEW.run_id
                 AND batch.session_date = NEW.session_date
           ) THEN
            RAISE EXCEPTION 'formal price failure does not match an unresolved attempt'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal price attempt references no started event/run'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_price_attempt_event() IS
    'tradingagents.formal-price-attempt.v1;normalized-prosrc-sha256=f8c4a473648ba138a244047baf63bd044f58874fef1eaa421192f1bc74720588';

CREATE OR REPLACE FUNCTION public.enforce_formal_price_capture_batch()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    payload JSONB;
    capture_identity JSONB;
    vector_identity JSONB;
    expected_universe TEXT[];
    manifest_universe TEXT[];
    manifest_length INTEGER;
    observed_last_ordinal INTEGER;
BEGIN
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    NEW.persisted_utc := EXTRACT(
        epoch FROM pg_catalog.clock_timestamp()
    );
    IF NEW.persisted_utc >= NEW.deadline_utc
       OR NEW.completed_utc > NEW.persisted_utc + 30.0
       OR NEW.persisted_utc - NEW.completed_utc > 300.0 THEN
        RAISE EXCEPTION 'formal price batch was not persisted in its live window'
            USING ERRCODE = '23514';
    END IF;
    payload := NEW.payload_json::jsonb;
    capture_identity := NEW.capture_identity_json::jsonb;
    IF jsonb_typeof(run_config -> 'tickers') IS DISTINCT FROM 'array'
       OR jsonb_typeof(run_config -> 'benchmark') IS DISTINCT FROM 'string'
       OR jsonb_typeof(NEW.receipt_manifest_json::jsonb) IS DISTINCT FROM 'array'
       OR jsonb_typeof(capture_identity) IS DISTINCT FROM 'object'
       OR jsonb_typeof(payload) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'formal price batch payload disagrees with stored columns'
            USING ERRCODE = '23514';
    END IF;

    SELECT pg_catalog.array_agg(symbol ORDER BY symbol)
      INTO expected_universe
      FROM (
          SELECT symbol
            FROM pg_catalog.jsonb_array_elements_text(run_config -> 'tickers')
                 AS configured(symbol)
          UNION
          SELECT run_config ->> 'benchmark'
      ) AS exact_symbols;
    SELECT pg_catalog.array_agg(item ->> 'ticker' ORDER BY ordinal),
           pg_catalog.count(*)::integer
      INTO manifest_universe, manifest_length
      FROM pg_catalog.jsonb_array_elements(NEW.receipt_manifest_json::jsonb)
           WITH ORDINALITY AS manifest(item, ordinal);

    IF expected_universe IS NULL
       OR manifest_length IS DISTINCT FROM pg_catalog.cardinality(expected_universe)
       OR manifest_universe IS DISTINCT FROM expected_universe
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(
                    NEW.receipt_manifest_json::jsonb
                ) AS manifest(item)
           WHERE pg_catalog.jsonb_typeof(item) IS DISTINCT FROM 'object'
       ) THEN
        RAISE EXCEPTION 'formal price batch universe is not exact sorted-unique'
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(
                 NEW.receipt_manifest_json::jsonb
             ) AS manifest(item)
        WHERE (SELECT pg_catalog.array_agg(key ORDER BY key)
                 FROM pg_catalog.jsonb_object_keys(item) AS keys(key))
                  IS DISTINCT FROM ARRAY[
                      'price_receipt_id', 'ticker', 'vendor_snapshot_id'
                  ]::TEXT[]
           OR item ->> 'price_receipt_id'
                  !~ '^price_receipt_[0-9a-f]{24}$'
           OR item ->> 'vendor_snapshot_id'
                  !~ '^price_snapshot_[0-9a-f]{24}$'
    ) THEN
        RAISE EXCEPTION 'formal price batch manifest item is malformed'
            USING ERRCODE = '23514';
    END IF;

    IF (SELECT pg_catalog.array_agg(key ORDER BY key)
          FROM pg_catalog.jsonb_object_keys(capture_identity) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'attempt_ordinal', 'completed_utc', 'deadline_utc',
                'from_session_date', 'paper_build_id', 'receipt_manifest',
                'return_vector_id',
                'scheduled_utc', 'schema_version', 'session_date',
                'started_utc', 'vendor'
            ]::TEXT[]
       OR capture_identity ->> 'schema_version' IS DISTINCT FROM '1'
       OR payload - 'capture_batch_id' IS DISTINCT FROM capture_identity
       OR payload ->> 'capture_batch_id' IS DISTINCT FROM NEW.capture_batch_id
       OR NEW.capture_batch_id IS DISTINCT FROM (
            'price_batch_' || pg_catalog.substr(pg_catalog.encode(
                pg_catalog.sha256(pg_catalog.convert_to(
                    NEW.capture_identity_json, 'UTF8'
                )), 'hex'
            ), 1, 24)
       )
       OR NEW.vendor IS DISTINCT FROM 'yfinance'
       OR NEW.paper_build_id !~ '^build_[0-9a-f]{24}$'
       OR capture_identity ->> 'session_date' IS DISTINCT FROM NEW.session_date
       OR capture_identity ->> 'from_session_date'
            IS DISTINCT FROM NEW.from_session_date
       OR capture_identity ->> 'vendor' IS DISTINCT FROM NEW.vendor
       OR capture_identity ->> 'paper_build_id'
            IS DISTINCT FROM NEW.paper_build_id
       OR capture_identity ->> 'return_vector_id'
            IS DISTINCT FROM NEW.return_vector_id
       OR capture_identity -> 'receipt_manifest' IS DISTINCT FROM
            NEW.receipt_manifest_json::jsonb
       OR (capture_identity ->> 'attempt_ordinal')::integer
            IS DISTINCT FROM NEW.attempt_ordinal
       OR (capture_identity ->> 'scheduled_utc')::double precision
            IS DISTINCT FROM NEW.scheduled_utc
       OR (capture_identity ->> 'started_utc')::double precision
            IS DISTINCT FROM NEW.started_utc
       OR (capture_identity ->> 'completed_utc')::double precision
            IS DISTINCT FROM NEW.completed_utc
       OR (capture_identity ->> 'deadline_utc')::double precision
            IS DISTINCT FROM NEW.deadline_utc THEN
        RAISE EXCEPTION 'formal price batch identity is not content-addressed'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.from_session_date IS NULL THEN
        IF NEW.return_vector_id IS NOT NULL
           OR NEW.return_vector_identity_json IS NOT NULL THEN
            RAISE EXCEPTION 'formal initialization batch cannot contain a return vector'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        vector_identity := NEW.return_vector_identity_json::jsonb;
        IF NEW.return_vector_id IS NULL
           OR jsonb_typeof(vector_identity) IS DISTINCT FROM 'object'
           OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                 FROM pg_catalog.jsonb_object_keys(vector_identity) AS keys(key))
                IS DISTINCT FROM ARRAY[
                    'captured_utc', 'cash_component', 'components', 'deadline_utc',
                    'from_session', 'scheduled_utc', 'schema_version', 'to_session',
                    'vendor'
                ]::TEXT[]
           OR vector_identity ->> 'schema_version' IS DISTINCT FROM '2'
           OR vector_identity ->> 'from_session'
                IS DISTINCT FROM NEW.from_session_date
           OR vector_identity ->> 'to_session' IS DISTINCT FROM NEW.session_date
           OR vector_identity ->> 'vendor' IS DISTINCT FROM NEW.vendor
           OR (vector_identity ->> 'captured_utc')::double precision
                IS DISTINCT FROM NEW.completed_utc
           OR (vector_identity ->> 'scheduled_utc')::double precision
                IS DISTINCT FROM NEW.scheduled_utc
           OR (vector_identity ->> 'deadline_utc')::double precision
                IS DISTINCT FROM NEW.deadline_utc
           OR jsonb_typeof(vector_identity -> 'components') IS DISTINCT FROM 'object'
           OR jsonb_typeof(vector_identity -> 'cash_component')
                IS DISTINCT FROM 'object'
           OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                 FROM pg_catalog.jsonb_object_keys(
                          vector_identity -> 'components'
                      ) AS components(key))
                IS DISTINCT FROM expected_universe
           OR NEW.return_vector_id IS DISTINCT FROM (
                'return_vector_' || pg_catalog.substr(pg_catalog.encode(
                    pg_catalog.sha256(pg_catalog.convert_to(
                        NEW.return_vector_identity_json, 'UTF8'
                    )), 'hex'
                ), 1, 24)
           ) THEN
            RAISE EXCEPTION 'formal return vector identity is malformed'
                USING ERRCODE = '23514';
        END IF;
        IF (SELECT pg_catalog.array_agg(key ORDER BY key)
              FROM pg_catalog.jsonb_object_keys(
                       vector_identity -> 'cash_component'
                   ) AS cash_keys(key))
                IS DISTINCT FROM ARRAY[
                    'accrual_days', 'annual_yield_percent', 'annual_yield_proxy',
                    'day_count_basis', 'instrument', 'observation_session',
                    'open_return'
                ]::TEXT[]
           OR vector_identity -> 'cash_component' ->> 'instrument'
                IS DISTINCT FROM 'USD'
           OR vector_identity -> 'cash_component' ->> 'annual_yield_proxy'
                IS DISTINCT FROM '^IRX'
           OR (vector_identity -> 'cash_component' ->> 'day_count_basis')::integer
                IS DISTINCT FROM 360
           OR (vector_identity -> 'cash_component' ->> 'accrual_days')::integer
                IS DISTINCT FROM (
                    NEW.session_date::date - NEW.from_session_date::date
                )
           OR (vector_identity -> 'cash_component' ->> 'accrual_days')::integer <= 0
           OR (vector_identity -> 'cash_component' ->> 'observation_session')::date
                >= NEW.from_session_date::date
           OR (vector_identity -> 'cash_component' ->> 'annual_yield_percent')
                ::double precision NOT BETWEEN -20.0 AND 100.0
           OR pg_catalog.abs(
                (vector_identity -> 'cash_component' ->> 'open_return')
                    ::double precision
                - (vector_identity -> 'cash_component' ->> 'annual_yield_percent')
                    ::double precision / 100.0
                  * (vector_identity -> 'cash_component' ->> 'accrual_days')
                    ::integer / 360.0
              ) > 1e-12 THEN
            RAISE EXCEPTION 'formal return vector cash component is malformed'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_each(
                     vector_identity -> 'components'
                 ) AS component(ticker, value)
            WHERE pg_catalog.jsonb_typeof(value) IS DISTINCT FROM 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                     FROM pg_catalog.jsonb_object_keys(value) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'cash_dividend', 'current_adjusted_open',
                        'current_raw_open', 'open_return',
                        'previous_adjusted_open', 'price_receipt_id',
                        'split_ratio', 'vendor_snapshot_id'
                    ]::TEXT[]
               OR NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.jsonb_array_elements(
                             NEW.receipt_manifest_json::jsonb
                         ) AS manifest(item)
                    WHERE item ->> 'ticker' = component.ticker
                      AND item ->> 'price_receipt_id'
                            = component.value ->> 'price_receipt_id'
                      AND item ->> 'vendor_snapshot_id'
                            = component.value ->> 'vendor_snapshot_id'
               )
        ) THEN
            RAISE EXCEPTION 'formal return vector is not bound to its receipt manifest'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.paper_price_integrity_failures AS failure
        WHERE failure.run_id = NEW.run_id
    ) THEN
        RAISE EXCEPTION 'terminal price failure blocks a formal capture batch'
            USING ERRCODE = '55000';
    END IF;
    SELECT COALESCE(MAX(event.attempt_ordinal), 0)
      INTO observed_last_ordinal
      FROM public.paper_price_capture_attempt_events AS event
     WHERE event.run_id = NEW.run_id
       AND event.session_date = NEW.session_date;
    IF NEW.attempt_ordinal IS DISTINCT FROM observed_last_ordinal
       OR NOT EXISTS (
        SELECT 1 FROM public.paper_price_capture_attempt_events AS event
        WHERE event.run_id = NEW.run_id
          AND event.session_date = NEW.session_date
          AND event.attempt_ordinal = NEW.attempt_ordinal
          AND event.event_type = 'started'
          AND event.created_utc = NEW.started_utc
    ) OR EXISTS (
        SELECT 1 FROM public.paper_price_capture_attempt_events AS event
        WHERE event.run_id = NEW.run_id
          AND event.session_date = NEW.session_date
          AND event.attempt_ordinal = NEW.attempt_ordinal
          AND event.event_type = 'failed'
    ) THEN
        RAISE EXCEPTION 'formal price batch requires one unresolved started attempt'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal price batch references an unknown run'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_price_capture_batch() IS
    'tradingagents.formal-price-batch.v1;normalized-prosrc-sha256=5afaea253e470dfbbc7856ec870da1a23f3bdae20c6bf9c1a02abb314a5d94ae';

CREATE OR REPLACE FUNCTION public.enforce_formal_price_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    payload JSONB;
    receipt_identity JSONB;
    snapshot_identity JSONB;
    vector_identity JSONB;
    receipt_vector JSONB;
    component JSONB;
    current_row JSONB;
    previous_row JSONB;
    expected_sessions TEXT[];
    observed_sessions TEXT[];
    batch public.paper_price_capture_batches%ROWTYPE;
BEGIN
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    IF NEW.capture_batch_id IS NULL
       OR NEW.price_receipt_id !~ '^price_receipt_[0-9a-f]{24}$'
       OR NEW.vendor_snapshot_id !~ '^price_snapshot_[0-9a-f]{24}$'
       OR NEW.receipt_identity_json IS NULL
       OR NEW.vendor_snapshot_identity_json IS NULL
       OR NEW.raw_open <= 0 OR NEW.adjusted_open <= 0
       OR NEW.dividend < 0 OR NEW.split_ratio < 0
       OR NEW.captured_utc <= '-Infinity'::DOUBLE PRECISION
       OR NEW.captured_utc >= 'Infinity'::DOUBLE PRECISION
       OR NEW.raw_open <= '-Infinity'::DOUBLE PRECISION
       OR NEW.raw_open >= 'Infinity'::DOUBLE PRECISION
       OR NEW.adjusted_open <= '-Infinity'::DOUBLE PRECISION
       OR NEW.adjusted_open >= 'Infinity'::DOUBLE PRECISION
       OR NEW.dividend <= '-Infinity'::DOUBLE PRECISION
       OR NEW.dividend >= 'Infinity'::DOUBLE PRECISION
       OR NEW.split_ratio <= '-Infinity'::DOUBLE PRECISION
       OR NEW.split_ratio >= 'Infinity'::DOUBLE PRECISION THEN
        RAISE EXCEPTION 'formal price receipt scalar contract is invalid'
            USING ERRCODE = '23514';
    END IF;
    SELECT stored.*
      INTO STRICT batch
      FROM public.paper_price_capture_batches AS stored
     WHERE stored.run_id = NEW.run_id
       AND stored.session_date = NEW.session_date;
    payload := NEW.payload_json::jsonb;
    receipt_identity := NEW.receipt_identity_json::jsonb;
    snapshot_identity := NEW.vendor_snapshot_identity_json::jsonb;
    IF jsonb_typeof(payload) IS DISTINCT FROM 'object'
       OR jsonb_typeof(receipt_identity) IS DISTINCT FROM 'object'
       OR jsonb_typeof(snapshot_identity) IS DISTINCT FROM 'object'
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
             FROM pg_catalog.jsonb_object_keys(receipt_identity) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'adjusted_open', 'captured_utc', 'dividend', 'raw_open',
                'schema_version', 'session_date', 'split_ratio', 'ticker',
                'vendor', 'vendor_snapshot', 'vendor_snapshot_id'
            ]::TEXT[]
       OR (SELECT pg_catalog.array_agg(key ORDER BY key)
             FROM pg_catalog.jsonb_object_keys(snapshot_identity) AS keys(key))
            IS DISTINCT FROM ARRAY[
                'from_session', 'provider', 'received_utc', 'requested_ticker',
                'requested_utc', 'rows', 'schema_version', 'to_session'
            ]::TEXT[]
       OR receipt_identity ->> 'schema_version' IS DISTINCT FROM '2'
       OR snapshot_identity ->> 'schema_version' IS DISTINCT FROM '1'
       OR payload - ARRAY[
            'capture_batch_id', 'price_receipt_id', 'return_vector'
          ]::TEXT[] IS DISTINCT FROM receipt_identity
       OR receipt_identity -> 'vendor_snapshot' IS DISTINCT FROM (
            snapshot_identity || pg_catalog.jsonb_build_object(
                'vendor_snapshot_id', NEW.vendor_snapshot_id
            )
       )
       OR NEW.price_receipt_id IS DISTINCT FROM (
            'price_receipt_' || pg_catalog.substr(pg_catalog.encode(
                pg_catalog.sha256(pg_catalog.convert_to(
                    NEW.receipt_identity_json, 'UTF8'
                )), 'hex'
            ), 1, 24)
       )
       OR NEW.vendor_snapshot_id IS DISTINCT FROM (
            'price_snapshot_' || pg_catalog.substr(pg_catalog.encode(
                pg_catalog.sha256(pg_catalog.convert_to(
                    NEW.vendor_snapshot_identity_json, 'UTF8'
                )), 'hex'
            ), 1, 24)
       )
       OR NEW.capture_batch_id IS DISTINCT FROM batch.capture_batch_id
       OR NEW.captured_utc IS DISTINCT FROM batch.completed_utc
       OR NEW.vendor IS DISTINCT FROM batch.vendor
       OR receipt_identity ->> 'ticker' IS DISTINCT FROM NEW.ticker
       OR receipt_identity ->> 'session_date' IS DISTINCT FROM NEW.session_date
       OR receipt_identity ->> 'vendor' IS DISTINCT FROM NEW.vendor
       OR receipt_identity ->> 'vendor_snapshot_id'
            IS DISTINCT FROM NEW.vendor_snapshot_id
       OR payload ->> 'capture_batch_id' IS DISTINCT FROM NEW.capture_batch_id
       OR payload ->> 'price_receipt_id' IS DISTINCT FROM NEW.price_receipt_id
       OR (receipt_identity ->> 'captured_utc')::double precision
            IS DISTINCT FROM NEW.captured_utc
       OR (receipt_identity ->> 'raw_open')::double precision
            IS DISTINCT FROM NEW.raw_open
       OR (receipt_identity ->> 'adjusted_open')::double precision
            IS DISTINCT FROM NEW.adjusted_open
       OR (receipt_identity ->> 'dividend')::double precision
            IS DISTINCT FROM NEW.dividend
       OR (receipt_identity ->> 'split_ratio')::double precision
            IS DISTINCT FROM NEW.split_ratio
       OR snapshot_identity ->> 'provider' IS DISTINCT FROM NEW.vendor
       OR snapshot_identity ->> 'requested_ticker' IS DISTINCT FROM NEW.ticker
       OR snapshot_identity ->> 'from_session'
            IS DISTINCT FROM batch.from_session_date
       OR snapshot_identity ->> 'to_session' IS DISTINCT FROM NEW.session_date
       OR (snapshot_identity ->> 'requested_utc')::double precision
            < batch.started_utc
       OR (snapshot_identity ->> 'received_utc')::double precision
            < (snapshot_identity ->> 'requested_utc')::double precision
       OR (snapshot_identity ->> 'received_utc')::double precision
            > batch.completed_utc
       OR jsonb_typeof(snapshot_identity -> 'rows') IS DISTINCT FROM 'object'
       OR NOT EXISTS (
           SELECT 1
           FROM jsonb_array_elements(batch.receipt_manifest_json::jsonb) AS item
           WHERE item ->> 'ticker' = NEW.ticker
             AND item ->> 'price_receipt_id' = NEW.price_receipt_id
             AND item ->> 'vendor_snapshot_id' = NEW.vendor_snapshot_id
       ) THEN
        RAISE EXCEPTION 'formal price receipt is not bound to its capture batch'
            USING ERRCODE = '23514';
    END IF;

    expected_sessions := CASE
        WHEN batch.from_session_date IS NULL THEN ARRAY[NEW.session_date]::TEXT[]
        ELSE ARRAY[batch.from_session_date, NEW.session_date]::TEXT[]
    END;
    SELECT pg_catalog.array_agg(key ORDER BY key)
      INTO observed_sessions
      FROM pg_catalog.jsonb_object_keys(snapshot_identity -> 'rows') AS rows(key);
    IF observed_sessions IS DISTINCT FROM expected_sessions
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_each(snapshot_identity -> 'rows') AS row(session, value)
            WHERE jsonb_typeof(value) IS DISTINCT FROM 'object'
               OR (SELECT pg_catalog.array_agg(key ORDER BY key)
                     FROM pg_catalog.jsonb_object_keys(value) AS keys(key))
                    IS DISTINCT FROM ARRAY[
                        'adjusted_close', 'adjusted_open', 'adjustment_factor',
                        'close', 'dividend', 'raw_open', 'session_date', 'split_ratio'
                    ]::TEXT[]
               OR value ->> 'session_date' IS DISTINCT FROM row.session
               OR (value ->> 'raw_open')::double precision <= 0
               OR (value ->> 'close')::double precision <= 0
               OR (value ->> 'adjusted_close')::double precision <= 0
               OR (value ->> 'adjustment_factor')::double precision <= 0
               OR (value ->> 'adjusted_open')::double precision <= 0
               OR (value ->> 'dividend')::double precision < 0
               OR (value ->> 'split_ratio')::double precision < 0
               OR pg_catalog.abs(
                    (value ->> 'adjustment_factor')::double precision
                    - (value ->> 'adjusted_close')::double precision
                      / (value ->> 'close')::double precision
                  ) > 1e-12
               OR pg_catalog.abs(
                    (value ->> 'adjusted_open')::double precision
                    - (value ->> 'raw_open')::double precision
                      * (value ->> 'adjustment_factor')::double precision
                  ) > 1e-12
       ) THEN
        RAISE EXCEPTION 'formal vendor snapshot endpoints are malformed'
            USING ERRCODE = '23514';
    END IF;
    current_row := snapshot_identity -> 'rows' -> NEW.session_date;
    IF (current_row ->> 'raw_open')::double precision IS DISTINCT FROM NEW.raw_open
       OR (current_row ->> 'adjusted_open')::double precision
            IS DISTINCT FROM NEW.adjusted_open
       OR (current_row ->> 'dividend')::double precision IS DISTINCT FROM NEW.dividend
       OR (current_row ->> 'split_ratio')::double precision
            IS DISTINCT FROM NEW.split_ratio THEN
        RAISE EXCEPTION 'formal receipt scalars disagree with current snapshot endpoint'
            USING ERRCODE = '23514';
    END IF;

    IF batch.from_session_date IS NULL THEN
        IF payload ? 'return_vector' OR batch.return_vector_id IS NOT NULL
           OR batch.return_vector_identity_json IS NOT NULL THEN
            RAISE EXCEPTION 'formal initialization receipt cannot contain a vector'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        vector_identity := batch.return_vector_identity_json::jsonb;
        receipt_vector := payload -> 'return_vector';
        component := vector_identity -> 'components' -> NEW.ticker;
        previous_row := snapshot_identity -> 'rows' -> batch.from_session_date;
        IF jsonb_typeof(receipt_vector) IS DISTINCT FROM 'object'
           OR jsonb_typeof(component) IS DISTINCT FROM 'object'
           OR receipt_vector - ARRAY[
                'return_vector_id', 'schema_version', 'from_session', 'to_session',
                'captured_utc', 'scheduled_utc', 'deadline_utc', 'vendor',
                'cash_component'
              ]::TEXT[] IS DISTINCT FROM component
           OR receipt_vector ->> 'return_vector_id'
                IS DISTINCT FROM batch.return_vector_id
           OR receipt_vector ->> 'schema_version' IS DISTINCT FROM '2'
           OR receipt_vector ->> 'from_session'
                IS DISTINCT FROM batch.from_session_date
           OR receipt_vector ->> 'to_session' IS DISTINCT FROM NEW.session_date
           OR receipt_vector ->> 'vendor' IS DISTINCT FROM NEW.vendor
           OR (receipt_vector ->> 'captured_utc')::double precision
                IS DISTINCT FROM batch.completed_utc
           OR (receipt_vector ->> 'scheduled_utc')::double precision
                IS DISTINCT FROM batch.scheduled_utc
           OR (receipt_vector ->> 'deadline_utc')::double precision
                IS DISTINCT FROM batch.deadline_utc
           OR receipt_vector -> 'cash_component'
                IS DISTINCT FROM vector_identity -> 'cash_component'
           OR component ->> 'price_receipt_id' IS DISTINCT FROM NEW.price_receipt_id
           OR component ->> 'vendor_snapshot_id'
                IS DISTINCT FROM NEW.vendor_snapshot_id
           OR (component ->> 'previous_adjusted_open')::double precision
                IS DISTINCT FROM (previous_row ->> 'adjusted_open')::double precision
           OR (component ->> 'current_adjusted_open')::double precision
                IS DISTINCT FROM NEW.adjusted_open
           OR (component ->> 'current_raw_open')::double precision
                IS DISTINCT FROM NEW.raw_open
           OR (component ->> 'cash_dividend')::double precision
                IS DISTINCT FROM NEW.dividend
           OR (component ->> 'split_ratio')::double precision
                IS DISTINCT FROM NEW.split_ratio
           OR pg_catalog.abs(
                (component ->> 'open_return')::double precision
                - (component ->> 'current_adjusted_open')::double precision
                  / (component ->> 'previous_adjusted_open')::double precision + 1.0
              ) > 1e-12 THEN
            RAISE EXCEPTION 'formal receipt action fields disagree with return vector'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal price receipt references no capture batch'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_price_receipt() IS
    'tradingagents.formal-price-receipt.v1;normalized-prosrc-sha256=1e0374f548678bf1a580be10032b70a80284be78f69b74e3e104f2ec82e6868a';

CREATE OR REPLACE FUNCTION public.enforce_formal_price_batch_completion()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    manifest JSONB;
    expected_tickers TEXT[];
    observed_open_tickers TEXT[];
    receipt_count INTEGER;
BEGIN
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    manifest := NEW.receipt_manifest_json::jsonb;
    SELECT pg_catalog.count(*)::integer
      INTO receipt_count
      FROM public.paper_price_receipts AS receipt
     WHERE receipt.run_id = NEW.run_id
       AND receipt.session_date = NEW.session_date;
    IF receipt_count IS DISTINCT FROM pg_catalog.jsonb_array_length(manifest)
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(manifest) AS expected(item)
            WHERE NOT EXISTS (
                SELECT 1
                FROM public.paper_price_receipts AS receipt
                WHERE receipt.run_id = NEW.run_id
                  AND receipt.session_date = NEW.session_date
                  AND receipt.ticker = expected.item ->> 'ticker'
                  AND receipt.price_receipt_id
                        = expected.item ->> 'price_receipt_id'
                  AND receipt.vendor_snapshot_id
                        = expected.item ->> 'vendor_snapshot_id'
            )
       ) THEN
        RAISE EXCEPTION 'formal price batch did not atomically commit exact receipts'
            USING ERRCODE = '23514';
    END IF;

    SELECT pg_catalog.array_agg(symbol ORDER BY symbol)
      INTO expected_tickers
      FROM pg_catalog.jsonb_array_elements_text(run_config -> 'tickers')
           AS configured(symbol);
    SELECT pg_catalog.array_agg(key ORDER BY key)
      INTO observed_open_tickers
      FROM public.paper_marks AS mark,
           LATERAL pg_catalog.jsonb_object_keys(mark.opens_json::jsonb) AS opens(key)
     WHERE mark.run_id = NEW.run_id
       AND mark.session_date = NEW.session_date;
    IF observed_open_tickers IS DISTINCT FROM expected_tickers
       OR NOT EXISTS (
            SELECT 1
            FROM public.paper_marks AS mark
            WHERE mark.run_id = NEW.run_id
              AND mark.session_date = NEW.session_date
              AND mark.captured_utc = NEW.completed_utc
              AND mark.benchmark_open = (
                    SELECT receipt.adjusted_open
                    FROM public.paper_price_receipts AS receipt
                    WHERE receipt.run_id = NEW.run_id
                      AND receipt.session_date = NEW.session_date
                      AND receipt.ticker = run_config ->> 'benchmark'
              )
              AND NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.jsonb_array_elements_text(
                             run_config -> 'tickers'
                         ) AS configured(symbol)
                    WHERE (mark.opens_json::jsonb ->> configured.symbol)
                                ::double precision IS DISTINCT FROM (
                            SELECT receipt.adjusted_open
                            FROM public.paper_price_receipts AS receipt
                            WHERE receipt.run_id = NEW.run_id
                              AND receipt.session_date = NEW.session_date
                              AND receipt.ticker = configured.symbol
                    )
              )
       ) THEN
        RAISE EXCEPTION 'formal price batch did not atomically bind its champion mark'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.return_vector_id IS NULL THEN
        IF EXISTS (
            SELECT 1 FROM public.paper_interval_assignments AS assignment
            WHERE assignment.run_id = NEW.run_id
              AND assignment.session_date = NEW.session_date
        ) THEN
            RAISE EXCEPTION 'formal initialization batch has an interval assignment'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NOT EXISTS (
        SELECT 1 FROM public.paper_interval_assignments AS assignment
        WHERE assignment.run_id = NEW.run_id
          AND assignment.session_date = NEW.session_date
          AND assignment.created_utc = NEW.completed_utc
          AND assignment.return_vector_id = NEW.return_vector_id
    ) THEN
        RAISE EXCEPTION 'formal price batch did not atomically bind its interval assignment'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal price batch completion references an unknown run'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_price_batch_completion() IS
    'tradingagents.formal-price-completion.v1;normalized-prosrc-sha256=248b68941c1d9c098a5901dbe708d3acb23b29c30c81561e8e82d9e7bc61c6be';

CREATE OR REPLACE FUNCTION public.enforce_formal_mark_price_batch()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    batch public.paper_price_capture_batches%ROWTYPE;
    expected_tickers TEXT[];
    observed_open_tickers TEXT[];
BEGIN
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    SELECT stored.*
      INTO STRICT batch
      FROM public.paper_price_capture_batches AS stored
     WHERE stored.run_id = NEW.run_id
       AND stored.session_date = NEW.session_date;
    SELECT pg_catalog.array_agg(symbol ORDER BY symbol)
      INTO expected_tickers
      FROM pg_catalog.jsonb_array_elements_text(run_config -> 'tickers')
           AS configured(symbol);
    SELECT pg_catalog.array_agg(key ORDER BY key)
      INTO observed_open_tickers
      FROM pg_catalog.jsonb_object_keys(NEW.opens_json::jsonb) AS opens(key);
    IF NEW.captured_utc IS DISTINCT FROM batch.completed_utc
       OR observed_open_tickers IS DISTINCT FROM expected_tickers
       OR NEW.benchmark_open IS DISTINCT FROM (
            SELECT receipt.adjusted_open
            FROM public.paper_price_receipts AS receipt
            WHERE receipt.run_id = NEW.run_id
              AND receipt.session_date = NEW.session_date
              AND receipt.ticker = run_config ->> 'benchmark'
       )
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements_text(run_config -> 'tickers')
                 AS configured(symbol)
            WHERE (NEW.opens_json::jsonb ->> configured.symbol)::double precision
                    IS DISTINCT FROM (
                SELECT receipt.adjusted_open
                FROM public.paper_price_receipts AS receipt
                WHERE receipt.run_id = NEW.run_id
                  AND receipt.session_date = NEW.session_date
                  AND receipt.ticker = configured.symbol
            )
       ) THEN
        RAISE EXCEPTION 'formal champion mark is not bound to its price batch'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal champion mark references no price batch/run'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_mark_price_batch() IS
    'tradingagents.formal-price-mark.v1;normalized-prosrc-sha256=86624999729c1909298c8d2b4a3c8d7317b14ba1f5e0a1eab1115823d9194065';

CREATE OR REPLACE FUNCTION public.enforce_formal_price_terminal_failure()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    run_config JSONB;
    payload JSONB;
    observed_last_ordinal INTEGER;
BEGIN
    SELECT run.config_json::jsonb
      INTO STRICT run_config
      FROM public.paper_runs AS run
     WHERE run.run_id = NEW.run_id;
    IF run_config ->> 'engine' IS DISTINCT FROM 'formal-global-v2' THEN
        RETURN NEW;
    END IF;
    payload := NEW.payload_json::jsonb;
    SELECT COALESCE(MAX(event.attempt_ordinal), 0)
      INTO observed_last_ordinal
      FROM public.paper_price_capture_attempt_events AS event
     WHERE event.run_id = NEW.run_id
       AND event.session_date = NEW.session_date;
    IF EXISTS (
        SELECT 1 FROM public.paper_price_capture_batches AS batch
        WHERE batch.run_id = NEW.run_id
          AND batch.session_date = NEW.session_date
    ) OR NEW.last_attempt_ordinal IS DISTINCT FROM observed_last_ordinal
       OR payload ->> 'failure_id' IS DISTINCT FROM NEW.failure_id
       OR payload ->> 'run_id' IS DISTINCT FROM NEW.run_id
       OR payload ->> 'session_date' IS DISTINCT FROM NEW.session_date
       OR payload ->> 'reason_code' IS DISTINCT FROM NEW.reason_code
       OR (payload ->> 'detected_utc')::double precision
            IS DISTINCT FROM NEW.detected_utc
       OR (payload ->> 'scheduled_utc')::double precision
            IS DISTINCT FROM NEW.scheduled_utc
       OR (payload ->> 'deadline_utc')::double precision
            IS DISTINCT FROM NEW.deadline_utc
       OR (payload ->> 'last_attempt_ordinal')::integer
            IS DISTINCT FROM NEW.last_attempt_ordinal THEN
        RAISE EXCEPTION 'formal terminal price failure is inconsistent'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'formal terminal price failure references an unknown run'
            USING ERRCODE = '23503';
END
$$;

COMMENT ON FUNCTION public.enforce_formal_price_terminal_failure() IS
    'tradingagents.formal-price-terminal.v1;normalized-prosrc-sha256=d40d48d749d72c3c45ee5b7e847f47b9267b2e38b6074aa62424164e97add431';

CREATE OR REPLACE FUNCTION public.enforce_no_terminal_formal_price_failure()
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
       AND EXISTS (
           SELECT 1 FROM public.paper_price_integrity_failures AS failure
           WHERE failure.run_id = NEW.run_id
       ) THEN
        RAISE EXCEPTION 'terminal price failure blocks formal trial activity'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.enforce_no_terminal_formal_price_failure() IS
    'tradingagents.formal-price-terminal-activity.v1;normalized-prosrc-sha256=65efefa5d115fcf339662ab1d8913ab0273a17b6f2a688d72c1469d257427d0f';

DROP TRIGGER IF EXISTS validate_formal_price_attempt_event
    ON public.paper_price_capture_attempt_events;
CREATE TRIGGER validate_formal_price_attempt_event
    BEFORE INSERT ON public.paper_price_capture_attempt_events
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_price_attempt_event();

DROP TRIGGER IF EXISTS validate_formal_price_capture_batch
    ON public.paper_price_capture_batches;
CREATE TRIGGER validate_formal_price_capture_batch
    BEFORE INSERT ON public.paper_price_capture_batches
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_price_capture_batch();

DROP TRIGGER IF EXISTS complete_formal_price_capture_batch
    ON public.paper_price_capture_batches;
CREATE CONSTRAINT TRIGGER complete_formal_price_capture_batch
    AFTER INSERT ON public.paper_price_capture_batches
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_price_batch_completion();

DROP TRIGGER IF EXISTS validate_formal_price_receipt
    ON public.paper_price_receipts;
CREATE TRIGGER validate_formal_price_receipt
    BEFORE INSERT ON public.paper_price_receipts
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_price_receipt();

DROP TRIGGER IF EXISTS validate_formal_mark_price_batch
    ON public.paper_marks;
CREATE TRIGGER validate_formal_mark_price_batch
    BEFORE INSERT ON public.paper_marks
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_mark_price_batch();

DROP TRIGGER IF EXISTS validate_formal_price_terminal_failure
    ON public.paper_price_integrity_failures;
CREATE TRIGGER validate_formal_price_terminal_failure
    BEFORE INSERT ON public.paper_price_integrity_failures
    FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_price_terminal_failure();

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_decisions', 'paper_decision_bundles', 'paper_events',
        'paper_forecasts', 'paper_targets', 'paper_strategy_targets',
        'paper_marks', 'paper_strategy_marks', 'paper_price_receipts',
        'paper_decision_attempt_events',
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_interval_assignments'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS reject_after_terminal_price_failure ON public.%I',
            table_name
        );
        EXECUTE format(
            'CREATE TRIGGER reject_after_terminal_price_failure BEFORE INSERT ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.enforce_no_terminal_formal_price_failure()',
            table_name
        );
    END LOOP;
END
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'paper_price_capture_attempt_events', 'paper_price_capture_batches',
        'paper_price_integrity_failures'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS immutable_%I ON public.%I',
                       table_name, table_name);
        EXECUTE format(
            'CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation()',
            table_name, table_name
        );
        EXECUTE format('DROP TRIGGER IF EXISTS require_formal_primary_run ON public.%I',
                       table_name);
        EXECUTE format(
            'CREATE TRIGGER require_formal_primary_run BEFORE INSERT ON public.%I '
            'FOR EACH ROW EXECUTE FUNCTION public.enforce_formal_primary_run_activity()',
            table_name
        );
    END LOOP;
END
$$;

REVOKE ALL PRIVILEGES ON TABLE
    public.paper_price_capture_attempt_events,
    public.paper_price_capture_batches,
    public.paper_price_integrity_failures
    FROM PUBLIC;

REVOKE ALL ON FUNCTION public.enforce_formal_price_capture_batch() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_price_batch_completion() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_mark_price_batch() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_price_attempt_event() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_price_receipt() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_formal_price_terminal_failure() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.enforce_no_terminal_formal_price_failure() FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-paper'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.paper_price_capture_attempt_events,
            public.paper_price_capture_batches,
            public.paper_price_integrity_failures
            FROM "tradingagents-paper";
        GRANT SELECT, INSERT ON TABLE
            public.paper_price_capture_attempt_events,
            public.paper_price_capture_batches,
            public.paper_price_integrity_failures
            TO "tradingagents-paper";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-ingest-v2'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.paper_price_capture_attempt_events,
            public.paper_price_capture_batches,
            public.paper_price_integrity_failures
            FROM "tradingagents-ingest-v2";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tradingagents-ingest'
    ) THEN
        REVOKE ALL PRIVILEGES ON TABLE
            public.paper_price_capture_attempt_events,
            public.paper_price_capture_batches,
            public.paper_price_integrity_failures
            FROM "tradingagents-ingest";
    END IF;
END
$$;

COMMIT;
