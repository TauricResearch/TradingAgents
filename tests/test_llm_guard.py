"""Persistent, fail-closed guardrails around formal LLM invocations."""

import json
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import exchange_calendars as xcals
import pytest

from tradingagents.dataflows.media_store import SqlAlchemyMediaStore, SqliteMediaStore
from tradingagents.formal_experiment import (
    _formal_completion_limit,
    _formal_invocation_stage_order,
    _formal_prompt_limit,
    _formal_timeout,
    _invoke_guarded_forecast,
    create_forecast_llm,
)
from tradingagents.global_research import prepare_evidence
from tradingagents.llm_guard import (
    LLMCallBudgetExceeded,
    LLMCallPolicy,
    LLMPolicyError,
    PersistentLLMCallGuard,
)
from tradingagents.paper_trading import PaperStore, _cycle_with_retries
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL_ID, content_id

NOW = datetime(2026, 8, 5, 1, tzinfo=timezone.utc)


def _evidence_row(*, body: str = "public reaction") -> dict:
    return {
        "source": "x", "external_id": "reaction-1", "ticker": "@TREND_WORLD",
        "labels": ["@TREND_WORLD"],
        "created_utc": 1.0, "fetched_utc": 2.0, "author": "public-user",
        "body": body,
        "metadata": {
            "verified_type": "none",
            "evidence_role": "unverified_public_reaction",
            "automation_risk": 0.1,
            "automation_signals_complete": True,
            "author_id": "12345",
            "account_created_utc": 1.0,
            "author_metrics": {
                "followers_count": 100,
                "following_count": 50,
                "tweet_count": 500,
            },
            "engagement": {
                "like_count": 1,
                "reply_count": 0,
                "retweet_count": 0,
                "quote_count": 0,
            },
        },
    }


def _policy(*, decision: int = 2, day: int = 2) -> LLMCallPolicy:
    return LLMCallPolicy.from_values(
        "openai:gpt-5.4-mini", decision, day,
    )


def _atomic_invocation_context(
    tmp_path,
    *,
    filename: str,
    run_id: str = "run-1",
    decision_date: str = "2026-08-04",
    policy: LLMCallPolicy | None = None,
):
    """Create the preregistered ledger state required before any paid call."""
    db_path = str(tmp_path / filename)
    protocol_id = f"protocol-{filename}"
    registration_id = f"registration-{filename}"
    registration = {
        "protocol_id": protocol_id,
        "run_id": run_id,
        "registration_id": registration_id,
        "registration_type": "confirmatory",
        "outcomes_accessed_before_registration": False,
    }
    frozen_policy = policy or _policy()
    invocation_policy = {
        "max_calls_per_decision": frozen_policy.max_calls_per_decision,
        "max_calls_per_utc_day": frozen_policy.max_calls_per_utc_day,
        "max_prompt_bytes": 160_000,
        "max_completion_tokens": 8_000,
    }
    ledger = PaperStore(db_path)
    ledger.create_run(
        run_id,
        {
            "engine": "formal-global-v2",
            "protocol_id": protocol_id,
            "trial_registration_id": registration_id,
            "llm_policy": frozen_policy.manifest(),
            "llm_max_prompt_bytes": 160_000,
            "llm_max_completion_tokens": 8_000,
        },
        NOW.timestamp(),
    )
    ledger.register_protocol(
        protocol_id,
        {"forecast": {"invocation_policy": invocation_policy}},
        NOW.timestamp(),
    )
    ledger.register_confirmatory_trial(run_id, NOW.timestamp(), registration)
    ledger.record_formal_attempt_started(
        run_id, decision_date, "2026-08-05", NOW.timestamp()
    )
    media = SqliteMediaStore(db_path)
    guard = PersistentLLMCallGuard(
        frozen_policy,
        scope="formal-global-v2",
        run_id=run_id,
        decision_date=decision_date,
    )
    return media, ledger, guard


def _reservation_spec(
    guard: PersistentLLMCallGuard,
    *,
    decision_date: str = "2026-08-04",
    stage: str = "champion",
) -> dict:
    return guard.reservation_spec(
        "openai",
        "gpt-5.4-mini",
        decision_date=decision_date,
        stage=stage,
        input_bundle_id=f"input-{stage}",
        prompt_id=f"prompt-{stage}",
        prompt_bytes=100,
        max_prompt_bytes=160_000,
        max_completion_tokens=8_000,
    )


@pytest.mark.unit
def test_formal_invocation_stage_order_is_deterministic_and_counterbalanced():
    stages = [
        "champion",
        "without_public_reaction",
        "public_reaction_only",
    ]

    assert _formal_invocation_stage_order("2026-08-04", stages) == [
        "public_reaction_only",
        "champion",
        "without_public_reaction",
    ]
    assert _formal_invocation_stage_order("2026-08-10", stages) == [
        "without_public_reaction",
        "champion",
        "public_reaction_only",
    ]
    assert _formal_invocation_stage_order(
        "2026-08-04", ["champion", "without_public_reaction"]
    ) == ["champion", "without_public_reaction"]
    assert _formal_invocation_stage_order("2026-08-04", ["champion"]) == [
        "champion"
    ]


@pytest.mark.unit
def test_formal_invocation_stage_cycle_is_exactly_balanced_over_trial_horizon():
    stages = [
        "champion",
        "without_public_reaction",
        "public_reaction_only",
    ]
    calendar = xcals.get_calendar(
        "XNYS", start="2020-01-02", end="2030-12-31"
    )
    sessions = calendar.sessions_window("2026-08-05", 252)
    positions = {stage: Counter() for stage in stages}
    pair_positions = {
        stage: Counter() for stage in stages if stage != "public_reaction_only"
    }

    for session in sessions:
        decision_date = session.date().isoformat()
        order = _formal_invocation_stage_order(decision_date, stages)
        for ordinal, stage in enumerate(order, start=1):
            positions[stage][ordinal] += 1
        pair_order = _formal_invocation_stage_order(
            decision_date, ["champion", "without_public_reaction"]
        )
        for ordinal, stage in enumerate(pair_order, start=1):
            pair_positions[stage][ordinal] += 1

    assert all(counts == Counter({1: 84, 2: 84, 3: 84})
               for counts in positions.values())
    assert all(counts == Counter({1: 126, 2: 126})
               for counts in pair_positions.values())


@pytest.mark.unit
@pytest.mark.parametrize(
    ("decision_date", "stages"),
    [
        ("20260804", ["champion"]),
        ("2026-08-04", []),
        ("2026-08-04", ["champion", "champion"]),
        ("2026-08-04", ["unknown", "champion"]),
        ("2026-08-04", ["public_reaction_only"]),
        ("2026-08-09", ["champion"]),
    ],
)
def test_formal_invocation_stage_order_rejects_noncanonical_inputs(
    decision_date, stages
):
    with pytest.raises(ValueError, match="invocation"):
        _formal_invocation_stage_order(decision_date, stages)


def _forecast_bundle(kwargs: dict, *, returned_model: str = "gpt-5.4-mini"):
    universe = kwargs["universe"]
    evidence = prepare_evidence(kwargs["rows"])
    bundle = SimpleNamespace(
        input_bundle_id=content_id({
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "decision_date": kwargs["decision_date"],
            "universe": universe,
            "evidence": evidence,
        }, prefix="input_"),
        provider=kwargs["provider"],
        requested_model=kwargs["requested_model"],
        model_id=content_id(
            {
                "provider": kwargs["provider"],
                "requested_model": kwargs["requested_model"],
                "returned_model": returned_model,
            },
            prefix="model_",
        ),
        response_metadata={"model_name": returned_model},
        usage_metadata={"output_tokens": 100},
        response_id="response-fixture",
    )
    bundle.as_dict = lambda: {
        "input_bundle_id": bundle.input_bundle_id,
        "provider": bundle.provider,
        "requested_model": bundle.requested_model,
        "model_id": bundle.model_id,
        "response_id": bundle.response_id,
        "response_metadata": bundle.response_metadata,
        "usage_metadata": bundle.usage_metadata,
        "evidence": evidence,
    }
    return bundle


@pytest.mark.unit
def test_model_policy_is_exact_explicit_and_manifestable():
    policy = LLMCallPolicy.from_values(
        " OpenAI:gpt-5.4-mini,openai:gpt-5.4-mini-2026-08-01 ", 3, 4,
    )

    assert policy.require_model("OPENAI", "gpt-5.4-mini") == "openai:gpt-5.4-mini"
    assert policy.manifest() == {
        "allowed_models": [
            "openai:gpt-5.4-mini",
            "openai:gpt-5.4-mini-2026-08-01",
        ],
        "max_calls_per_decision": 3,
        "max_calls_per_utc_day": 4,
    }
    with pytest.raises(LLMPolicyError, match="not in the explicit allowlist"):
        policy.require_model("openai", "gpt-5.5")
    with pytest.raises(LLMPolicyError, match="explicit LLM model allowlist"):
        LLMCallPolicy.from_values(None, 3, 3)
    with pytest.raises(LLMPolicyError, match="non-negative integer"):
        LLMCallPolicy.from_values("openai:gpt-5.4-mini", -1, 3)


@pytest.mark.unit
def test_formal_client_disables_sdk_retries_behind_one_reserved_call(monkeypatch):
    captured = {}
    expected = object()

    class Client:
        def get_llm(self):
            return expected

    def create_client(**kwargs):
        captured.update(kwargs)
        return Client()

    monkeypatch.setattr(
        "tradingagents.formal_experiment.create_llm_client", create_client
    )
    config = {
        "llm_provider": "openai",
        "quick_think_llm": "gpt-5.4-mini",
        "backend_url": None,
        "openai_reasoning_effort": "low",
        "temperature": None,
        "llm_max_retries": 99,
    }

    assert create_forecast_llm(config) is expected
    assert captured["max_retries"] == 0
    assert captured["max_completion_tokens"] == 8_000
    assert captured["timeout"] == 180
    assert captured["reasoning_effort"] == "low"
    assert config["llm_max_retries"] == 99


@pytest.mark.unit
def test_formal_invocation_limits_must_equal_the_preregistered_values():
    exact = SimpleNamespace(
        llm_max_prompt_bytes=160_000,
        llm_max_completion_tokens=8_000,
        llm_timeout_seconds=180,
    )
    assert _formal_prompt_limit(exact) == 160_000
    assert _formal_completion_limit(exact) == 8_000
    assert _formal_timeout(exact) == 180

    with pytest.raises(ValueError, match="differs from the frozen protocol"):
        _formal_prompt_limit(SimpleNamespace(llm_max_prompt_bytes=159_999))
    with pytest.raises(ValueError, match="differs from the frozen protocol"):
        _formal_completion_limit(SimpleNamespace(llm_max_completion_tokens=8_001))
    with pytest.raises(ValueError, match="differs from the frozen protocol"):
        _formal_timeout(SimpleNamespace(llm_timeout_seconds=179))


@pytest.mark.unit
def test_sqlite_multi_counter_reservation_persists_and_rolls_back(tmp_path):
    path = tmp_path / "budget.db"
    limits = {"a-daily": 10, "z-decision": 2}
    store = SqliteMediaStore(path)
    assert store.reserve_meta_budget(limits) == {"a-daily": 1.0, "z-decision": 1.0}
    store.close()

    store = SqliteMediaStore(path)
    assert store.reserve_meta_budget(limits) == {"a-daily": 2.0, "z-decision": 2.0}
    # The daily increment is attempted first, but the exhausted decision row
    # makes the complete reservation roll back.
    assert store.reserve_meta_budget(limits) is None
    assert store.get_meta("a-daily") == 2.0
    assert store.get_meta("z-decision") == 2.0
    store.close()


@pytest.mark.unit
def test_sqlalchemy_multi_counter_reservation_is_all_or_none(tmp_path, monkeypatch):
    pytest.importorskip("sqlalchemy")
    monkeypatch.delenv("MEDIA_AUTO_MIGRATE", raising=False)
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'budget-sa.db'}")
    limits = {"a-daily": 5, "z-decision": 1}

    assert store.reserve_meta_budget(limits) == {"a-daily": 1.0, "z-decision": 1.0}
    assert store.reserve_meta_budget(limits) is None
    assert store.get_meta("a-daily") == 1.0
    assert store.get_meta("z-decision") == 1.0
    store.close()


@pytest.mark.unit
def test_guarded_forecast_returns_unchanged_bundle_and_stops_before_extra_call(
    tmp_path, monkeypatch,
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="guard.db"
    )
    calls = []

    def invoke(**kwargs):
        calls.append(kwargs)
        return _forecast_bundle(kwargs)

    monkeypatch.setattr("tradingagents.formal_experiment.invoke_global_forecast", invoke)
    kwargs = {
        "guard": guard,
        "llm": object(),
        "provider": "openai",
        "requested_model": "gpt-5.4-mini",
        "decision_date": "2026-08-04",
        "rows": [_evidence_row()],
        "universe": ["AAPL"],
        "artifact_recorder": ledger,
    }

    assert _invoke_guarded_forecast(**kwargs).response_id == "response-fixture"
    assert _invoke_guarded_forecast(
        **{**kwargs, "invocation_stage": "without_public_reaction"}
    ).response_id == "response-fixture"
    with pytest.raises(LLMCallBudgetExceeded, match="refusing another invocation"):
        _invoke_guarded_forecast(
            **{**kwargs, "invocation_stage": "public_reaction_only"}
        )
    assert len(calls) == 2
    store.close()
    ledger.close()


@pytest.mark.unit
def test_guarded_forecast_appends_reservation_and_result_receipts(tmp_path, monkeypatch):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="receipts.db"
    )

    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast",
        lambda **kwargs: _forecast_bundle(kwargs),
    )
    result = _invoke_guarded_forecast(
        guard=guard, llm=object(), provider="openai",
        requested_model="gpt-5.4-mini", decision_date="2026-08-04",
        rows=[_evidence_row()],
        universe=["AAPL"], max_completion_tokens=100,
        invocation_stage="champion", artifact_recorder=ledger,
    )

    assert result.response_id == "response-fixture"
    receipts = ledger.formal_invocation_receipts("run-1", "2026-08-04")
    assert [receipt["artifact_type"] for receipt in receipts] == [
        "llm_invocation_reserved", "llm_invocation_result",
    ]
    reserved, completed = receipts[0]["content"], receipts[1]["content"]
    assert reserved["invocation_id"] == completed["invocation_id"]
    for field, expected in {
        "schema_version": 2,
        "scope": "formal-global-v2",
        "run_id": "run-1",
        "decision_date": "2026-08-04",
        "ordinal": 1,
        "stage": "champion",
        "provider": "openai",
        "requested_model": "gpt-5.4-mini",
        "input_bundle_id": result.input_bundle_id,
    }.items():
        assert reserved[field] == expected
        assert completed[field] == expected
    assert reserved["prompt_bytes"] > 0
    assert reserved["max_prompt_bytes"] == 160_000
    assert reserved["max_completion_tokens"] == 100
    assert reserved["max_calls_per_decision"] == 2
    assert reserved["max_calls_per_utc_day"] == 2
    assert completed["reservation_artifact_id"] == content_id(
        {
            "artifact_type": "llm_invocation_reserved",
            "content": reserved,
        },
        prefix="artifact_",
    )
    assert completed["status"] == "success"
    assert completed["model_id"] == result.model_id
    assert completed["response_id"] == result.response_id
    assert completed["usage_metadata"] == {"output_tokens": 100}
    assert completed["forecast_bundle_id"] == content_id(
        result.as_dict(), prefix="bundle_"
    )
    store.close()
    ledger.close()


@pytest.mark.unit
def test_atomic_reservation_crash_rolls_back_counters_and_receipt(
    tmp_path, monkeypatch
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="reservation-crash.db"
    )
    provider_calls = []
    monkeypatch.setattr(
        ledger,
        "_before_llm_reservation_artifact_insert",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("simulated crash")),
    )
    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast",
        lambda **kwargs: provider_calls.append(kwargs),
    )

    with pytest.raises(RuntimeError, match="simulated crash"):
        _invoke_guarded_forecast(
            guard=guard,
            llm=object(),
            provider="openai",
            requested_model="gpt-5.4-mini",
            decision_date="2026-08-04",
            rows=[_evidence_row()],
            universe=["AAPL"],
            artifact_recorder=ledger,
        )

    assert provider_calls == []
    assert ledger._rows("SELECT * FROM formal_llm_budget_counters") == []
    assert ledger.formal_invocation_receipts("run-1", "2026-08-04") == []
    store.close()
    ledger.close()


@pytest.mark.unit
def test_zero_call_budget_fails_without_counter_receipt_or_provider(
    tmp_path, monkeypatch
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path,
        filename="zero-budget.db",
        policy=_policy(decision=0, day=2),
    )
    provider_calls = []
    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast",
        lambda **kwargs: provider_calls.append(kwargs),
    )

    with pytest.raises(LLMCallBudgetExceeded):
        _invoke_guarded_forecast(
            guard=guard,
            llm=object(),
            provider="openai",
            requested_model="gpt-5.4-mini",
            decision_date="2026-08-04",
            rows=[_evidence_row()],
            universe=["AAPL"],
            artifact_recorder=ledger,
        )

    assert provider_calls == []
    assert ledger._rows("SELECT * FROM formal_llm_budget_counters") == []
    assert ledger.formal_invocation_receipts("run-1", "2026-08-04") == []
    store.close()
    ledger.close()


@pytest.mark.unit
def test_provider_failure_appends_one_exact_idempotent_terminal_result(
    tmp_path, monkeypatch
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="provider-failure.db"
    )
    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast",
        lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("provider timeout")),
    )

    with pytest.raises(TimeoutError, match="provider timeout"):
        _invoke_guarded_forecast(
            guard=guard,
            llm=object(),
            provider="openai",
            requested_model="gpt-5.4-mini",
            decision_date="2026-08-04",
            rows=[_evidence_row()],
            universe=["AAPL"],
            artifact_recorder=ledger,
        )

    receipts = ledger.formal_invocation_receipts("run-1", "2026-08-04")
    assert [row["artifact_type"] for row in receipts] == [
        "llm_invocation_reserved",
        "llm_invocation_result",
    ]
    terminal = receipts[1]["content"]
    assert terminal["status"] == "failed"
    assert terminal["error_type"] == "TimeoutError"
    artifact_id = ledger.record_llm_invocation_result(terminal, NOW.timestamp())
    assert artifact_id == receipts[1]["artifact_id"]
    assert len(ledger.formal_invocation_receipts("run-1", "2026-08-04")) == 2
    different_terminal = {**terminal, "error_type": "ConnectionError"}
    with pytest.raises(ValueError, match="already has a different result"):
        ledger.record_llm_invocation_result(different_terminal, NOW.timestamp())
    store.close()
    ledger.close()


@pytest.mark.unit
def test_provider_runs_after_the_reservation_transaction_has_closed(
    tmp_path, monkeypatch
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="provider-outside-transaction.db"
    )

    def invoke(**kwargs):
        independent = sqlite3.connect(ledger.url, timeout=0.1)
        try:
            independent.execute(
                "INSERT INTO poll_state (key,value) VALUES ('provider-probe',1.0)"
            )
            independent.commit()
        finally:
            independent.close()
        return _forecast_bundle(kwargs)

    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast", invoke
    )

    result = _invoke_guarded_forecast(
        guard=guard,
        llm=object(),
        provider="openai",
        requested_model="gpt-5.4-mini",
        decision_date="2026-08-04",
        rows=[_evidence_row()],
        universe=["AAPL"],
        artifact_recorder=ledger,
    )

    assert result.response_id == "response-fixture"
    assert store.get_meta("provider-probe") == 1.0
    store.close()
    ledger.close()


@pytest.mark.unit
def test_guarded_forecast_rejects_missing_response_identity_after_reservation(
    tmp_path, monkeypatch
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="missing-response-id.db"
    )

    def invoke(**kwargs):
        bundle = _forecast_bundle(kwargs)
        bundle.response_id = None
        return bundle

    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast", invoke
    )

    with pytest.raises(ValueError, match="response ID"):
        _invoke_guarded_forecast(
            guard=guard, llm=object(), provider="openai",
            requested_model="gpt-5.4-mini", decision_date="2026-08-04",
            rows=[_evidence_row()], universe=["AAPL"], artifact_recorder=ledger,
        )

    assert {row["reserved_calls"] for row in ledger._rows(
        "SELECT reserved_calls FROM formal_llm_budget_counters"
    )} == {1}
    receipts = ledger.formal_invocation_receipts("run-1", "2026-08-04")
    assert [row["content"]["status"] for row in receipts[1:]] == ["failed"]
    store.close()
    ledger.close()


@pytest.mark.unit
def test_formal_worker_does_not_retry_after_a_durable_invocation_reservation(
    tmp_path, monkeypatch
):
    db_path = str(tmp_path / "paper.db")
    calls = []
    sleeps = []
    alerts = []

    def fail_after_reservation(_args, now):
        calls.append(now)
        store = PaperStore(db_path)
        store.record_artifact(
            "llm_invocation_reserved",
            {
                "run_id": "run-1",
                "decision_date": "2026-08-04",
            },
            now.timestamp(),
        )
        store.close()
        raise RuntimeError("provider failed after reservation")

    monkeypatch.setattr("tradingagents.paper_trading.cycle", fail_after_reservation)
    monkeypatch.setattr(
        "tradingagents.paper_trading.current_decision_date",
        lambda _now: "2026-08-04",
    )
    monkeypatch.setattr(
        "tradingagents.paper_trading._record_daemon_heartbeat",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tradingagents.paper_trading.emit_alert",
        lambda component, event, **kwargs: alerts.append((component, event, kwargs)),
    )
    args = SimpleNamespace(
        db=db_path,
        engine="formal-global-v2",
        run_id="run-1",
    )

    result = _cycle_with_retries(
        args, attempts=3, retry_seconds=1, sleep_fn=sleeps.append
    )

    assert result is None
    assert len(calls) == 1
    assert sleeps == []
    assert alerts[0][1] == "formal_invocation_consumed_carry_forward"


@pytest.mark.unit
def test_oversized_prompt_is_rejected_before_budget_or_external_call(tmp_path, monkeypatch):
    guard = PersistentLLMCallGuard(
        _policy(), scope="formal-global-v2", run_id="run-1",
        decision_date="2026-08-04",
    )
    called = []
    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast",
        lambda **_kwargs: called.append(True),
    )

    with pytest.raises(ValueError, match="prompt exceeds"):
        _invoke_guarded_forecast(
            guard=guard, llm=object(), provider="openai",
            requested_model="gpt-5.4-mini", decision_date="2026-08-04",
            rows=[_evidence_row(body="large input " * 50)],
            universe=["AAPL"], max_prompt_bytes=100,
        )

    assert not called


@pytest.mark.unit
def test_poll_state_reset_cannot_reset_dedicated_formal_budget(tmp_path):
    media, ledger, guard = _atomic_invocation_context(
        tmp_path,
        filename="isolated-budget.db",
        policy=_policy(decision=1, day=1),
    )
    spec = guard.reservation_spec(
        "openai",
        "gpt-5.4-mini",
        decision_date="2026-08-04",
        stage="champion",
        input_bundle_id="input-fixture",
        prompt_id="prompt-fixture",
        prompt_bytes=100,
        max_prompt_bytes=160_000,
        max_completion_tokens=8_000,
    )
    ledger.reserve_llm_invocation(spec)
    media.set_meta("llm:formal-global-v2:decision:run-1:2026-08-04", 0.0)

    with pytest.raises(LLMCallBudgetExceeded):
        ledger.reserve_llm_invocation({**spec, "stage": "public_reaction_only"})
    rows = ledger._rows(
        "SELECT reserved_calls,frozen_limit FROM formal_llm_budget_counters"
    )
    assert sorted((row["reserved_calls"], row["frozen_limit"]) for row in rows) == [
        (1, 1),
        (1, 1),
    ]
    media.close()
    ledger.close()


@pytest.mark.unit
def test_n_plus_one_concurrent_reservations_cannot_exceed_frozen_budget(tmp_path):
    media, ledger, guard = _atomic_invocation_context(
        tmp_path,
        filename="concurrent-budget.db",
        policy=_policy(decision=2, day=2),
    )
    specs = [
        _reservation_spec(guard, stage=stage)
        for stage in (
            "champion",
            "without_public_reaction",
            "public_reaction_only",
        )
    ]
    db_path = ledger.url
    media.close()
    ledger.close()

    def reserve(spec):
        worker = PaperStore(db_path)
        try:
            return worker.reserve_llm_invocation(spec)["reservation_artifact_id"]
        except LLMCallBudgetExceeded:
            return "exhausted"
        finally:
            worker.close()

    with ThreadPoolExecutor(max_workers=3) as executor:
        outcomes = list(executor.map(reserve, specs))

    assert outcomes.count("exhausted") == 1
    assert sum(value.startswith("artifact_") for value in outcomes) == 2
    verifier = PaperStore(db_path)
    try:
        rows = verifier._rows(
            "SELECT counter_kind,reserved_calls,frozen_limit "
            "FROM formal_llm_budget_counters ORDER BY counter_kind"
        )
        assert {(row["counter_kind"], row["reserved_calls"], row["frozen_limit"])
                for row in rows} == {
            ("decision", 2, 2),
            ("utc_day", 2, 2),
        }
        assert len(verifier.formal_invocation_receipts("run-1", "2026-08-04")) == 2
    finally:
        verifier.close()


@pytest.mark.unit
def test_future_decision_date_cannot_move_server_owned_utc_bucket(tmp_path):
    media, ledger, _guard = _atomic_invocation_context(
        tmp_path,
        filename="future-day-budget.db",
        policy=_policy(decision=2, day=2),
    )
    future_date = "2099-01-01"
    ledger.conn.execute(
        "INSERT INTO paper_decision_attempt_events "
        "(run_id,decision_date,entry_date,attempt_ordinal,event_type,created_utc,reason_code) "
        "VALUES (?,?,?,?,? ,?,NULL)",
        ("run-1", future_date, "2099-01-02", 1, "started", NOW.timestamp()),
    )
    ledger.conn.commit()
    future_guard = PersistentLLMCallGuard(
        _policy(decision=2, day=2),
        scope="formal-global-v2",
        run_id="run-1",
        decision_date=future_date,
    )

    reservation = ledger.reserve_llm_invocation(
        _reservation_spec(future_guard, decision_date=future_date)
    )["reservation_receipt"]

    server_day = datetime.now(timezone.utc).date().isoformat()
    assert reservation["utc_day"] == server_day
    assert reservation["utc_day"] != future_date
    assert reservation["daily_counter_key"].endswith(f":utc-day:{server_day}")
    rows = ledger._rows(
        "SELECT counter_kind,bucket_date FROM formal_llm_budget_counters"
    )
    assert {row["bucket_date"] for row in rows if row["counter_kind"] == "utc_day"} == {
        server_day
    }
    media.close()
    ledger.close()


@pytest.mark.unit
def test_raising_registered_limits_cannot_raise_an_existing_counter(tmp_path):
    media, ledger, guard = _atomic_invocation_context(
        tmp_path,
        filename="raised-limit-budget.db",
        policy=_policy(decision=1, day=1),
    )
    ledger.reserve_llm_invocation(_reservation_spec(guard))
    config = json.loads(
        ledger._rows("SELECT config_json FROM paper_runs WHERE run_id='run-1'")[0][
            "config_json"
        ]
    )
    protocol_id = config["protocol_id"]
    manifest = json.loads(
        ledger._rows(
            "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
            {"protocol_id": protocol_id},
        )[0]["manifest_json"]
    )
    for target in (config["llm_policy"], manifest["forecast"]["invocation_policy"]):
        target["max_calls_per_decision"] = 2
        target["max_calls_per_utc_day"] = 2
    ledger.conn.execute("DROP TRIGGER immutable_experiment_registry_update")
    ledger.conn.execute(
        "UPDATE paper_runs SET config_json=? WHERE run_id='run-1'",
        (json.dumps(config, sort_keys=True, separators=(",", ":")),),
    )
    ledger.conn.execute(
        "UPDATE experiment_registry SET manifest_json=? WHERE protocol_id=?",
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")), protocol_id),
    )
    ledger.conn.commit()

    with pytest.raises(LLMCallBudgetExceeded):
        ledger.reserve_llm_invocation(
            _reservation_spec(guard, stage="without_public_reaction")
        )
    assert {
        (row["reserved_calls"], row["frozen_limit"])
        for row in ledger._rows(
            "SELECT reserved_calls,frozen_limit FROM formal_llm_budget_counters"
        )
    } == {(1, 1)}
    media.close()
    ledger.close()


@pytest.mark.unit
def test_returned_model_substitution_is_rejected_after_one_charged_call(
    tmp_path, monkeypatch,
):
    store, ledger, guard = _atomic_invocation_context(
        tmp_path, filename="substitution.db"
    )
    monkeypatch.setattr(
        "tradingagents.formal_experiment.invoke_global_forecast",
        lambda **kwargs: _forecast_bundle(kwargs, returned_model="unapproved-preview"),
    )

    with pytest.raises(LLMPolicyError, match="returned unallowlisted model"):
        _invoke_guarded_forecast(
            guard=guard, llm=object(), provider="openai",
            requested_model="gpt-5.4-mini", decision_date="2026-08-04",
            rows=[_evidence_row()], universe=["AAPL"], artifact_recorder=ledger,
        )
    assert {row["reserved_calls"] for row in ledger._rows(
        "SELECT reserved_calls FROM formal_llm_budget_counters"
    )} == {1}
    store.close()
    ledger.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({}, "omitted an explicit"),
        (
            {"model_name": "gpt-5.4-mini", "model": "different-snapshot"},
            "conflicting returned-model",
        ),
    ],
)
def test_returned_model_identity_must_be_explicit_and_unambiguous(metadata, message):
    guard = PersistentLLMCallGuard(
        _policy(), scope="formal-global-v2", run_id="run-1",
        decision_date="2026-08-04",
    )

    with pytest.raises(LLMPolicyError, match=message):
        guard.require_returned_model(
            "openai", "gpt-5.4-mini", metadata
        )
