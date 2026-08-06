from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

from tradingagents import formal_runtime as formal_runtime_module, poller
from tradingagents.formal_runtime import (
    FormalRuntimeConfigurationError,
    collector_component_configuration,
    in_image_preflight_identity,
    paper_component_configuration,
)
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL


def _collector_macro_themes() -> dict:
    return {
        theme: {"queries": list(queries)}
        for theme, queries in GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "broad_news_queries"
        ].items()
    }


def _collector_args(**changes) -> SimpleNamespace:
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    values = {
        "formal_collector": True,
        "macro": True,
        "tickers": None,
        "interval": evidence["query_cycle"]["collector_interval_seconds"],
        "trading_hours": False,
        "x_interval": evidence["x_cycle_interval_seconds"],
        "x_topics": evidence["max_x_search_requests_per_utc_day"],
        "x_limit": evidence["max_x_results_per_query"],
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _set_formal_collector_env(
    monkeypatch,
    *,
    collection_enabled: str = "false",
    fly_identity: bool = False,
    database_url: str | None = None,
) -> None:
    for name in (
        "MEDIA_POLLER_TICKERS",
        "MEDIA_DB_URL",
        "DATABASE_URL",
        "X_BEARER_TOKEN",
        "FLY_APP_NAME",
        "FLY_IMAGE_REF",
        "FLY_MACHINE_ID",
        *formal_runtime_module._LLM_SECRET_NAMES,
        *formal_runtime_module._DATA_VENDOR_SECRET_NAMES,
        *formal_runtime_module._BROKER_SECRET_NAMES,
        *formal_runtime_module._SOCIAL_SECRET_NAMES,
    ):
        monkeypatch.delenv(name, raising=False)
    values = {
        "MEDIA_AUTO_MIGRATE": "false",
        "MEDIA_COLLECTION_ENABLED": collection_enabled,
        "MEDIA_POLLER_SOURCES": "x",
        "MEDIA_POLLER_INTERVAL": "3600",
        "MEDIA_POLLER_TRADING_HOURS": "false",
        "MEDIA_POLLER_X_INTERVAL": "86400",
        "MEDIA_POLLER_X_TOPICS": "3",
        "MEDIA_POLLER_X_LIMIT": "10",
        "PAPER_HEARTBEAT_MAX_AGE": "93600",
    }
    if fly_identity:
        values.update({
            "FLY_APP_NAME": "tradagent",
            "FLY_MACHINE_ID": "machine-1",
            "FLY_IMAGE_REF": (
                "registry.fly.io/tradagent:"
                "deployment-01KZAE0P4ER12SS2215QXBSN0H"
            ),
        })
    if database_url is not None:
        values["MEDIA_DB_URL"] = database_url
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _paper_args() -> SimpleNamespace:
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    forecast = protocol["forecast"]
    invocation = forecast["invocation_policy"]
    return SimpleNamespace(
        run_id="global-event-v2-confirmatory-001",
        engine="formal-global-v2",
        tickers=",".join(protocol["universe"]["symbols"]),
        benchmark=protocol["portfolio"]["benchmark"],
        analysts="news",
        global_topics_only=True,
        llm_model_allowlist=",".join(sorted(
            f"{forecast['provider']}:{model}"
            for model in forecast["allowed_returned_models"]
        )),
        llm_max_calls_per_decision=invocation["max_calls_per_decision"],
        llm_max_calls_per_utc_day=invocation["max_calls_per_utc_day"],
        llm_max_prompt_bytes=invocation["max_prompt_bytes"],
        llm_max_completion_tokens=invocation["max_completion_tokens"],
        llm_timeout_seconds=invocation["timeout_seconds"],
        replicates=1,
        portfolio_mode=protocol["portfolio"]["mode"],
        cost_bps=protocol["portfolio"]["trading_cost_bps"],
        slippage_bps=protocol["portfolio"]["slippage_bps"],
        annual_borrow_bps=0.0,
    )


def _paper_env(role: str = "paper_decision") -> dict[str, str]:
    env = {
        "MEDIA_DB_URL": "postgresql://formal-runtime@example.invalid/formal",
        "MEDIA_AUTO_MIGRATE": "false",
        "PAPER_AUTO_MIGRATE": "false",
        "MEDIA_POLLER_INTERVAL": "3600",
        "PAPER_RETRY_ATTEMPTS": "3",
        "PAPER_RETRY_SECONDS": "300",
    }
    if role == "paper_decision":
        env["OPENAI_API_KEY"] = "configured-for-test"
    return env


def _model_config() -> dict:
    forecast = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
    return {
        "llm_provider": forecast["provider"],
        "quick_think_llm": forecast["requested_model"],
        "backend_url": forecast["backend_url"],
        "openai_reasoning_effort": forecast["reasoning_effort"],
        "temperature": forecast["temperature"],
    }


def _fly_paper_component(path: str, role: str) -> tuple[dict, dict]:
    document = tomllib.loads((Path(__file__).parents[1] / path).read_text())
    env = document["env"]
    runtime_env = {
        **env,
        "MEDIA_DB_URL": "postgresql://formal-runtime@example.invalid/formal",
    }
    if role == "paper_decision":
        runtime_env["OPENAI_API_KEY"] = "configured-for-test"
    forecast = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
    args = SimpleNamespace(
        run_id=env["PAPER_RUN_ID"],
        engine=env["PAPER_ENGINE"],
        tickers=env["PAPER_TICKERS"],
        benchmark=env["PAPER_BENCHMARK"],
        analysts=env.get("PAPER_ANALYSTS"),
        global_topics_only=env.get("PAPER_GLOBAL_TOPICS_ONLY") == "true",
        llm_model_allowlist=env.get("PAPER_LLM_MODEL_ALLOWLIST"),
        llm_max_calls_per_decision=int(env.get("PAPER_LLM_MAX_CALLS_PER_DECISION", "0")),
        llm_max_calls_per_utc_day=int(env.get("PAPER_LLM_MAX_CALLS_PER_UTC_DAY", "0")),
        llm_max_prompt_bytes=int(env.get("PAPER_LLM_MAX_PROMPT_BYTES", "0")),
        llm_max_completion_tokens=int(env.get("PAPER_LLM_MAX_COMPLETION_TOKENS", "0")),
        llm_timeout_seconds=int(env.get("PAPER_LLM_TIMEOUT_SECONDS", "0")),
        replicates=int(env.get("PAPER_REPLICATES", "1")),
        portfolio_mode=env["PAPER_PORTFOLIO_MODE"],
        cost_bps=float(env["PAPER_TRADING_COST_BPS"]),
        slippage_bps=float(env["PAPER_SLIPPAGE_BPS"]),
        annual_borrow_bps=float(env["PAPER_ANNUAL_BORROW_BPS"]),
    )
    component = paper_component_configuration(
        args,
        role=role,
        decision_semantics_id=forecast["expected_decision_semantics_id"],
        env=runtime_env,
        model_config=_model_config() if role == "paper_decision" else None,
    )
    return document, component


@pytest.mark.unit
def test_actual_paper_values_build_distinct_decision_and_marker_components():
    decision = paper_component_configuration(
        _paper_args(),
        role="paper_decision",
        decision_semantics_id=GLOBAL_EVENT_V2_PROTOCOL["forecast"][
            "expected_decision_semantics_id"
        ],
        env=_paper_env(),
        model_config=_model_config(),
    )
    marker = paper_component_configuration(
        _paper_args(),
        role="paper_marker",
        decision_semantics_id="ignored-by-marker",
        env=_paper_env("paper_marker"),
    )

    assert decision["role"] == "paper_decision"
    assert marker["role"] == "paper_marker"
    assert decision["configuration_id"] != marker["configuration_id"]
    assert "llm_provider" in decision["settings"]
    assert "llm_provider" not in marker["settings"]
    assert marker["settings"]["price_vendor"] == "yfinance"


@pytest.mark.unit
def test_actual_collector_values_build_exact_global_only_component():
    args = _collector_args()
    component = collector_component_configuration(
        args,
        enabled_sources=["x"],
        macro_themes=_collector_macro_themes(),
        collector_semantics_id="collector_" + "1" * 24,
        env={
            "MEDIA_AUTO_MIGRATE": "false",
            "PAPER_HEARTBEAT_MAX_AGE": "93600",
        },
    )

    assert component["role"] == "collector"
    assert component["settings"]["enabled_sources"] == ["globalnews", "x"]
    assert component["settings"]["globalnews_enabled"] is True
    assert component["settings"]["ticker_watchlist"] == []
    assert component["settings"]["trading_hours_only"] is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argument_changes", "theme_changes", "message"),
    [
        ({"macro": False}, {}, "global-news collection"),
        ({"tickers": "NVDA"}, {}, "ticker watchlist"),
        (
            {},
            {"rates": {"queries": ["different broad query when:7d"]}},
            "query slots differ",
        ),
    ],
)
def test_actual_collector_state_cannot_claim_frozen_global_news_material(
    argument_changes, theme_changes, message
):
    themes = _collector_macro_themes()
    themes.update(theme_changes)
    if argument_changes.get("macro") is False:
        themes = {}
    with pytest.raises(ValueError, match=message):
        collector_component_configuration(
            _collector_args(**argument_changes),
            enabled_sources=["x"],
            macro_themes=themes,
            collector_semantics_id="collector_" + "1" * 24,
            env={
                "MEDIA_AUTO_MIGRATE": "false",
                "PAPER_HEARTBEAT_MAX_AGE": "93600",
            },
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("media_url", "legacy_url", "message"),
    [
        (None, None, "MEDIA_DB_URL"),
        ("sqlite:////tmp/formal.db", None, "PostgreSQL scheme"),
        (
            "postgresql://formal-runtime@example.invalid/formal",
            "postgresql://legacy@example.invalid/formal",
            "legacy DATABASE_URL",
        ),
    ],
)
def test_collector_release_environment_rejects_database_fallbacks(
    media_url, legacy_url, message
):
    env = {
        "MEDIA_AUTO_MIGRATE": "false",
        "PAPER_HEARTBEAT_MAX_AGE": "93600",
    }
    if media_url is not None:
        env["MEDIA_DB_URL"] = media_url
    if legacy_url is not None:
        env["DATABASE_URL"] = legacy_url
    with pytest.raises(FormalRuntimeConfigurationError, match=message):
        collector_component_configuration(
            _collector_args(),
            enabled_sources=["x"],
            macro_themes=_collector_macro_themes(),
            collector_semantics_id="collector_" + "1" * 24,
            env=env,
            require_release_environment=True,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("role", "media_url", "legacy_url", "message"),
    [
        ("paper_marker", None, None, "MEDIA_DB_URL"),
        ("paper_marker", "sqlite:////tmp/formal.db", None, "PostgreSQL scheme"),
        (
            "paper_decision",
            "postgresql://formal-runtime@example.invalid/formal",
            "postgresql://legacy@example.invalid/formal",
            "legacy DATABASE_URL",
        ),
    ],
)
def test_paper_release_environment_rejects_database_fallbacks(
    role, media_url, legacy_url, message
):
    env = _paper_env(role)
    if media_url is None:
        env.pop("MEDIA_DB_URL")
    else:
        env["MEDIA_DB_URL"] = media_url
    if legacy_url is not None:
        env["DATABASE_URL"] = legacy_url
    with pytest.raises(FormalRuntimeConfigurationError, match=message):
        paper_component_configuration(
            _paper_args(),
            role=role,
            decision_semantics_id=(
                GLOBAL_EVENT_V2_PROTOCOL["forecast"][
                    "expected_decision_semantics_id"
                ]
            ),
            env=env,
            model_config=_model_config() if role == "paper_decision" else None,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("role", "secret_name"),
    [
        ("collector", "OPENAI_API_KEY"),
        ("collector", "ANTHROPIC_API_KEY"),
        ("collector", "TRUTHSOCIAL_TOKEN"),
        ("collector", "ALPACA_SECRET_KEY"),
        ("collector", "FRED_API_KEY"),
        ("paper_marker", "OPENAI_API_KEY"),
        ("paper_marker", "X_BEARER_TOKEN"),
        ("paper_marker", "TRUTHSOCIAL_TOKEN"),
        ("paper_marker", "ROBINHOOD_PASSWORD"),
        ("paper_marker", "ALPHA_VANTAGE_API_KEY"),
        ("paper_decision", "X_BEARER_TOKEN"),
        ("paper_decision", "TRUTHSOCIAL_TOKEN"),
        ("paper_decision", "IBKR_PASSWORD"),
        ("paper_decision", "ANTHROPIC_API_KEY"),
    ],
)
def test_formal_component_rejects_role_inappropriate_credentials(role, secret_name):
    secret_value = "must-not-be-rendered"
    if role == "collector":
        env = {
            "MEDIA_DB_URL": "postgresql://formal-runtime@example.invalid/formal",
            "MEDIA_AUTO_MIGRATE": "false",
            "PAPER_HEARTBEAT_MAX_AGE": "93600",
            secret_name: secret_value,
        }
    else:
        env = _paper_env(role)
        env[secret_name] = secret_value

    with pytest.raises(FormalRuntimeConfigurationError) as exc_info:
        if role == "collector":
            collector_component_configuration(
                _collector_args(),
                enabled_sources=["x"],
                macro_themes=_collector_macro_themes(),
                collector_semantics_id="collector_" + "1" * 24,
                env=env,
                require_release_environment=True,
            )
        else:
            paper_component_configuration(
                _paper_args(),
                role=role,
                decision_semantics_id=GLOBAL_EVENT_V2_PROTOCOL["forecast"][
                    "expected_decision_semantics_id"
                ],
                env=env,
                model_config=_model_config() if role == "paper_decision" else None,
            )
    assert secret_value not in str(exc_info.value)


@pytest.mark.unit
def test_formal_decision_requires_its_exact_provider_credential():
    env = _paper_env("paper_decision")
    env.pop("OPENAI_API_KEY")

    with pytest.raises(FormalRuntimeConfigurationError, match="provider credential"):
        paper_component_configuration(
            _paper_args(),
            role="paper_decision",
            decision_semantics_id=GLOBAL_EVENT_V2_PROTOCOL["forecast"][
                "expected_decision_semantics_id"
            ],
            env=env,
            model_config=_model_config(),
        )


@pytest.mark.unit
def test_formal_no_macro_fails_before_database_or_provider(monkeypatch, capsys):
    _set_formal_collector_env(monkeypatch)

    def forbidden(*_args, **_kwargs):
        pytest.fail("formal validation must precede database/provider access")

    monkeypatch.setattr(poller, "open_store", forbidden)
    monkeypatch.setattr(poller, "fetch_global_news", forbidden)
    monkeypatch.setattr(poller, "fetch_x_topic", forbidden)

    with pytest.raises(SystemExit):
        poller.main(["--formal-collector", "--no-macro"])

    assert "global-news collection" in capsys.readouterr().err


@pytest.mark.unit
def test_formal_query_drift_fails_before_database_or_provider(monkeypatch, capsys):
    _set_formal_collector_env(monkeypatch)
    themes = copy.deepcopy(poller.DEFAULT_CONFIG["macro_themes"])
    themes["rates"]["queries"][0] = "different broad query when:7d"
    monkeypatch.setitem(poller.DEFAULT_CONFIG, "macro_themes", themes)

    def forbidden(*_args, **_kwargs):
        pytest.fail("query validation must precede database/provider access")

    monkeypatch.setattr(poller, "open_store", forbidden)
    monkeypatch.setattr(poller, "fetch_global_news", forbidden)

    with pytest.raises(SystemExit):
        poller.main(["--formal-collector"])

    assert "query slots differ" in capsys.readouterr().err


@pytest.mark.unit
def test_formal_release_material_requires_disabled_migrations_before_db(monkeypatch):
    _set_formal_collector_env(
        monkeypatch,
        fly_identity=True,
        database_url="postgresql://formal-runtime@example.invalid/formal",
    )
    monkeypatch.delenv("MEDIA_AUTO_MIGRATE")
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: pytest.fail("release material must not open a DB"),
    )

    with pytest.raises(SystemExit):
        poller.main(["--formal-collector", "--release-material"])


@pytest.mark.unit
@pytest.mark.parametrize("configured", (None, "true"))
def test_formal_release_material_requires_explicit_collection_pause(
    monkeypatch, capsys, configured
):
    _set_formal_collector_env(
        monkeypatch,
        fly_identity=True,
        database_url="postgresql://formal-runtime@example.invalid/formal",
    )
    if configured is None:
        monkeypatch.delenv("MEDIA_COLLECTION_ENABLED")
    else:
        monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", configured)
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: pytest.fail("pause validation must precede DB open"),
    )

    with pytest.raises(SystemExit):
        poller.main(["--formal-collector", "--release-material"])

    assert "must be explicitly false" in capsys.readouterr().err


@pytest.mark.unit
def test_formal_release_material_uses_no_database_provider_or_secret(
    monkeypatch, capsys
):
    _set_formal_collector_env(monkeypatch, fly_identity=True)
    monkeypatch.setenv(
        "MEDIA_DB_URL",
        "postgresql://collector:database-secret@example.invalid/formal",
    )
    monkeypatch.setenv("X_BEARER_TOKEN", "x-provider-secret")

    def forbidden(*_args, **_kwargs):
        pytest.fail("release material must not access a database or provider")

    monkeypatch.setattr(poller, "open_store", forbidden)
    monkeypatch.setattr(poller, "fetch_global_news", forbidden)
    monkeypatch.setattr(poller, "fetch_x_topic", forbidden)
    monkeypatch.setattr(poller, "fetch_x_trends", forbidden)

    poller.main(["--formal-collector", "--release-material"])

    rendered = capsys.readouterr().out.strip()
    material = json.loads(rendered)
    assert material["component_configuration"]["settings"][
        "enabled_sources"
    ] == ["globalnews", "x"]
    assert material["preflight_payload"]["role"] == "collector"
    assert "outcome_semantics_id" not in material["preflight_payload"]
    assert "database-secret" not in rendered
    assert "x-provider-secret" not in rendered


@pytest.mark.unit
def test_paused_formal_startup_is_structured_and_has_no_db_or_token_dependency(
    monkeypatch, capsys
):
    _set_formal_collector_env(monkeypatch, collection_enabled="false")
    monkeypatch.setenv("OPENAI_API_KEY", "irrelevant-while-paused")
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: pytest.fail("paused startup must not open a DB"),
    )
    held = []
    monkeypatch.setattr(
        poller,
        "_hold_paused_formal_collector",
        lambda: held.append(True),
    )

    poller.main(["--formal-collector"])

    status = json.loads(capsys.readouterr().out)
    assert status == {
        "component_configuration_id": status["component_configuration_id"],
        "protocol_id": status["protocol_id"],
        "role": "collector",
        "schema_version": 1,
        "status": "paused",
    }
    assert status["component_configuration_id"].startswith("config_")
    assert held == [True]


@pytest.mark.unit
def test_paused_formal_collector_stays_alive_without_operational_calls(monkeypatch):
    waits = []

    def stop_after_first_wait(seconds):
        waits.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(poller.time, "sleep", stop_after_first_wait)

    with pytest.raises(KeyboardInterrupt):
        poller._hold_paused_formal_collector()

    assert waits == [3600.0]


@pytest.mark.unit
def test_collection_enabled_checks_token_after_component_and_before_db(
    monkeypatch, capsys
):
    _set_formal_collector_env(
        monkeypatch,
        collection_enabled="true",
        fly_identity=True,
        database_url="postgresql://formal-runtime@example.invalid/formal",
    )
    built = {"value": False}
    original = poller._formal_collector_runtime_material

    def capture(*args, **kwargs):
        component = original(*args, **kwargs)
        built["value"] = True
        return component

    monkeypatch.setattr(poller, "_formal_collector_runtime_material", capture)
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: pytest.fail("token validation must precede DB open"),
    )

    with pytest.raises(SystemExit):
        poller.main(["--formal-collector"])

    assert built["value"] is True
    assert "X_BEARER_TOKEN is required" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize("name", ("MEDIA_AUTO_MIGRATE", "PAPER_AUTO_MIGRATE"))
def test_missing_or_enabled_runtime_migration_flag_fails_closed(name):
    env = _paper_env("paper_marker")
    env.pop(name)
    with pytest.raises(FormalRuntimeConfigurationError, match=name):
        paper_component_configuration(
            _paper_args(),
            role="paper_marker",
            decision_semantics_id="ignored-by-marker",
            env=env,
        )


@pytest.mark.unit
def test_paused_fly_image_emits_build_config_and_outcome_bound_preflight():
    component = paper_component_configuration(
        _paper_args(),
        role="paper_marker",
        decision_semantics_id="ignored-by-marker",
        env=_paper_env("paper_marker"),
    )
    outcome_id = "outcome_semantics_" + "5" * 64
    material = in_image_preflight_identity(
        component,
        env={
            "FLY_APP_NAME": "tradagent-paper-marker",
            "FLY_MACHINE_ID": "machine-1",
            "FLY_IMAGE_REF": (
                "registry.fly.io/tradagent-paper-marker:"
                "deployment-01KZAF9N3MYKKKYCY3KKX9F558"
            ),
        },
        resolved_outcome_semantics_id=outcome_id,
    )

    payload = material["preflight_payload"]
    assert payload["component_configuration_id"] == component["configuration_id"]
    assert payload["outcome_semantics_id"] == outcome_id
    assert payload["build_id"].startswith("build_")


@pytest.mark.unit
def test_release_preflight_refuses_local_or_caller_selected_build_identity():
    component = paper_component_configuration(
        _paper_args(),
        role="paper_marker",
        decision_semantics_id="ignored-by-marker",
        env=_paper_env("paper_marker"),
    )
    with pytest.raises(FormalRuntimeConfigurationError, match="Fly deployment"):
        in_image_preflight_identity(
            component,
            env={"TRADINGAGENTS_BUILD_ID": "build_" + "1" * 24},
            resolved_outcome_semantics_id="outcome_semantics_" + "5" * 64,
        )


@pytest.mark.unit
def test_split_fly_configs_reconstruct_exact_paused_components():
    decision_doc, decision = _fly_paper_component(
        "fly.paper.decision.toml", "paper_decision"
    )
    marker_doc, marker = _fly_paper_component(
        "fly.paper.marker.toml", "paper_marker"
    )

    assert decision_doc["processes"] == {"app": "decision-daemon"}
    assert marker_doc["processes"] == {"app": "marker-daemon"}
    assert decision_doc["env"]["PAPER_DECISIONS_ENABLED"] == "false"
    assert marker_doc["env"]["PAPER_MARKS_ENABLED"] == "false"
    assert decision["role"] == "paper_decision"
    assert marker["role"] == "paper_marker"
    assert decision["settings"]["annual_borrow_bps"] == 0.0
    assert marker["settings"]["annual_borrow_bps"] == 0.0
    assert not any(
        "LLM" in key or "OPENAI" in key for key in marker_doc["env"]
    )


@pytest.mark.unit
def test_fly_collector_reconstructs_exact_paused_formal_component():
    document = tomllib.loads(
        (Path(__file__).parents[1] / "fly.toml").read_text(encoding="utf-8")
    )
    env = document["env"]
    process_args = shlex.split(document["processes"]["app"])
    args = poller._build_parser(env).parse_args(process_args)
    sources = poller.resolve_sources(
        poller._comma_separated(args.sources, lowercase=True) or None,
        env=env,
    )
    macro_themes = poller.DEFAULT_CONFIG["macro_themes"] if args.macro else {}
    component = poller._formal_collector_runtime_material(
        args,
        sources=sources,
        macro_themes=macro_themes,
        env=env,
    )

    assert document["processes"] == {"app": "--formal-collector"}
    assert env["MEDIA_COLLECTION_ENABLED"] == "false"
    assert "MEDIA_POLLER_TICKERS" not in env
    assert args.formal_collector is True
    assert args.macro is True
    assert args.tickers is None
    assert component["settings"]["collector_mode"] == "formal-global-news-v2"
    assert component["settings"]["ticker_watchlist"] == []
    assert component["settings"]["globalnews_enabled"] is True
    assert len(component["settings"]["globalnews_query_slots"]) == 10
