from __future__ import annotations

import hashlib
import platform
import sys
import sysconfig
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tradingagents.execution.models import AnalysisRequest
from tradingagents.execution.runner import PreparedInitialContext
from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    BUSINESS_PROJECTION_VERSION,
    SERIALIZER_VERSION,
    canonical_sha256,
)
from tradingagents.observability.events import EVENT_SCHEMA_VERSION
from tradingagents.portfolio import PortfolioContext, Position
from tradingagents.web.fingerprint import (
    CheckpointIncompatible,
    DependencyClosureManifest,
    FingerprintCheckpointGuard,
    _build_resume_fingerprint_for_test,
    compare_resume_fingerprints,
    dependency_closure_manifest,
    hash_runtime_sources,
    normalize_endpoint_identity,
    prepare_effective_config,
    python_runtime_manifest,
    runtime_environment_manifest,
)
from tradingagents.web.run_models import RunSnapshot, generate_run_id
from tradingagents.web.store import RunStore

pytestmark = pytest.mark.unit


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class _Metadata(dict[str, str]):
    def __init__(self, name: str, requirements: tuple[str, ...] = ()) -> None:
        super().__init__({"Name": name})
        self._requirements = requirements

    def get_all(self, key: str, failobj: Any = None) -> list[str] | Any:
        if key == "Requires-Dist":
            return list(self._requirements)
        return failobj


@dataclass
class _FakeDistribution:
    name: str
    version: str
    requirements: tuple[str, ...] = ()
    record: str | None = None
    sources: str | None = None
    direct_url: str | None = None

    @property
    def metadata(self) -> _Metadata:
        return _Metadata(self.name, self.requirements)

    @property
    def requires(self) -> list[str]:
        return list(self.requirements)

    def read_text(self, filename: str) -> str | None:
        return {
            "RECORD": self.record,
            "SOURCES.txt": self.sources,
            "direct_url.json": self.direct_url,
        }.get(filename)


@dataclass
class _FileBackedDistribution:
    name: str
    version: str
    root: Path
    files: tuple[str, ...]

    @property
    def metadata(self) -> _Metadata:
        return _Metadata(self.name)

    @property
    def requires(self) -> list[str]:
        return []

    def read_text(self, _filename: str) -> None:
        return None

    def locate_file(self, entry: str) -> Path:
        return self.root / entry


def _request(
    *,
    ticker: str = " aapl ",
    selected_analysts: tuple[str, ...] = ("news", "market"),
    effective_config: dict[str, Any] | None = None,
    portfolio: Any = None,
) -> AnalysisRequest:
    return AnalysisRequest(
        ticker=ticker,
        analysis_date="2026-07-18",
        selected_analysts=selected_analysts,
        max_debate_rounds=2,
        max_risk_discuss_rounds=3,
        effective_config=effective_config
        or {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-4.1-mini",
            "max_tokens": 2048,
            "backend_url": "https://api.example.com/v1?trace=discarded",
        },
        portfolio=portfolio,
    )


def _build(
    request: AnalysisRequest | None = None,
    *,
    initial_context: dict[str, Any] | None = None,
    agent_state_schema_sha256: str = AGENT_STATE_SCHEMA_SHA256,
):
    request = request or _request()
    return _build_resume_fingerprint_for_test(
        request,
        effective_config=request.effective_config,
        initial_context=initial_context
        or {
            "past_context": "No prior decision memory.",
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
        },
        runtime_semantics_hash="a" * 64,
        runtime_python={
            "implementation": "cpython",
            "version": "3.12.5",
            "cache_tag": "cpython-312",
            "abi_flags": "",
            "platform": "macosx-14.0-arm64",
        },
        runtime_distributions=[
            {
                "name": "langgraph",
                "version": "1.1.10",
                "record_sha256": "b" * 64,
                "direct_url_sha256": None,
            }
        ],
        agent_state_schema_sha256=agent_state_schema_sha256,
    )


def test_effective_config_excludes_only_four_root_location_keys():
    shared = {
        "provider": "openai",
        "routing": {"project_dir": "semantic nested value"},
        "project_dir": "/checkout/one",
        "results_dir": "/checkout/one/results",
        "data_cache_dir": "/checkout/one/cache",
        "memory_log_path": "/checkout/one/memory.jsonl",
    }
    relocated = {
        **shared,
        "project_dir": "/checkout/two",
        "results_dir": "/var/results",
        "data_cache_dir": "/var/cache",
        "memory_log_path": "/var/memory.jsonl",
    }

    first = prepare_effective_config(shared)
    second = prepare_effective_config(relocated)

    assert first == second
    assert not {
        "project_dir",
        "results_dir",
        "data_cache_dir",
        "memory_log_path",
    } & first.keys()
    assert first["routing"]["project_dir"] == "semantic nested value"


def test_future_nested_semantic_config_is_included_automatically():
    before = prepare_effective_config(
        {"provider": "openai", "future": {"retry": {"jitter": 0.2}}}
    )
    after = prepare_effective_config(
        {"provider": "openai", "future": {"retry": {"jitter": 0.3}}}
    )

    assert before != after
    assert canonical_sha256(before) != canonical_sha256(after)


def test_credentials_are_removed_regardless_of_location_presence_or_value():
    semantic = {
        "provider": "openai",
        "max_tokens": 2048,
        "headers": {"accept": "application/json"},
    }
    with_first_secrets = {
        **semantic,
        "OPENAI_API_KEY": "first-provider-value",
        "credentials": {"api_key": "first-nested-value"},
        "headers.Authorization": "Bearer first-dotted-value",
        "DASHSCOPE_CN_API_KEY": "first-second-provider-value",
    }
    with_second_secrets = {
        **semantic,
        "OPENAI_API_KEY": "second-provider-value",
        "credentials": {"api_key": "second-nested-value"},
        "headers.Authorization": "Bearer second-dotted-value",
        "DASHSCOPE_CN_API_KEY": "second-second-provider-value",
    }

    absent = prepare_effective_config(semantic)
    first = prepare_effective_config(with_first_secrets)
    second = prepare_effective_config(with_second_secrets)

    assert first == second == absent
    serialized = repr(first)
    assert "first-provider-value" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    changed_max_tokens = prepare_effective_config({**semantic, "max_tokens": 4096})
    assert changed_max_tokens != absent


def test_backend_endpoint_normalizes_default_ports_and_removes_unsafe_parts():
    implicit = normalize_endpoint_identity(
        "https://user:password@API.Example.COM/v1/chat?token=secret#fragment"
    )
    explicit = normalize_endpoint_identity("https://api.example.com:443/v1/chat")

    assert implicit == explicit == {
        "scheme": "https",
        "host": "api.example.com",
        "port": 443,
        "path": "/v1/chat",
    }
    assert normalize_endpoint_identity("http://api.example.com/v1") == (
        normalize_endpoint_identity("http://api.example.com:80/v1")
    )


def test_backend_endpoint_identity_changes_for_host_path_or_nondefault_port():
    base = normalize_endpoint_identity("https://api.example.com/v1")

    assert normalize_endpoint_identity("https://other.example.com/v1") != base
    assert normalize_endpoint_identity("https://api.example.com/v2") != base
    assert normalize_endpoint_identity("https://api.example.com:8443/v1") != base


def test_effective_config_replaces_backend_url_with_endpoint_identity():
    first = prepare_effective_config(
        {"backend_url": "https://user:secret@api.example.com/v1?q=one#first"}
    )
    second = prepare_effective_config(
        {"backend_url": "https://api.example.com:443/v1?q=two#second"}
    )

    assert first == second
    assert first["backend_url"] == {
        "scheme": "https",
        "host": "api.example.com",
        "port": 443,
        "path": "/v1",
    }


def test_runtime_source_hash_tracks_python_content_addition_and_rename(tmp_path: Path):
    package = tmp_path / "tradingagents"
    package.mkdir()
    module = package / "runner.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    base = hash_runtime_sources(package)

    module.write_text("VALUE = 2\n", encoding="utf-8")
    changed_content = hash_runtime_sources(package)
    (package / "observer.py").write_text("ENABLED = True\n", encoding="utf-8")
    added_source = hash_runtime_sources(package)
    module.rename(package / "renamed_runner.py")
    renamed_source = hash_runtime_sources(package)

    assert len(base) == 64
    assert len({base, changed_content, added_source, renamed_source}) == 4


def test_runtime_source_hash_ignores_non_python_caches_and_test_fixtures(tmp_path: Path):
    package = tmp_path / "tradingagents"
    package.mkdir()
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = hash_runtime_sources(package)

    (package / "README.md").write_text("not runtime Python", encoding="utf-8")
    pycache = package / "__pycache__"
    pycache.mkdir()
    (pycache / "generated.py").write_text("VALUE = 999\n", encoding="utf-8")
    (pycache / "runner.cpython-312.pyc").write_bytes(b"compiled")
    fixtures = package / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "fake_provider.py").write_text("VALUE = 999\n", encoding="utf-8")

    assert hash_runtime_sources(package) == base


def test_python_runtime_manifest_records_exact_resume_relevant_fields():
    manifest = python_runtime_manifest()

    assert manifest == {
        "implementation": sys.implementation.name,
        "version": platform.python_version(),
        "cache_tag": sys.implementation.cache_tag,
        "abi_flags": getattr(sys, "abiflags", ""),
        "platform": sysconfig.get_platform(),
    }


def test_dependency_closure_ignores_markers_recurses_sorts_and_hashes_metadata():
    root = _FakeDistribution(
        "TradingAgents",
        "0.3.1",
        requirements=(
            "Zulu_Dep>=1; python_version < '0'",
            "alpha.dep>=1",
            "not-installed>=1",
        ),
        record="root-record",
    )
    zulu = _FakeDistribution(
        "Zulu_Dep",
        "2.0",
        requirements=("Grand.Child>=1; extra == 'never-selected'",),
        record="zulu-record",
    )
    alpha = _FakeDistribution(
        "alpha.dep",
        "1.0",
        record="alpha-record",
        sources="must-not-win",
        direct_url='{"url":"file:///editable/alpha"}',
    )
    grand = _FakeDistribution(
        "Grand.Child",
        "3.0",
        sources="grand/sources.txt\n",
    )

    manifest = dependency_closure_manifest(
        "tradingagents",
        distributions=[grand, root, zulu, alpha],
    )

    assert manifest.resumable is True
    assert manifest.issues == ()
    assert list(manifest.distributions) == [
        {
            "name": "alpha-dep",
            "version": "1.0",
            "record_sha256": _sha256_text("alpha-record"),
            "direct_url_sha256": canonical_sha256(
                {
                    "url": {
                        "scheme": "file",
                        "host": "",
                        "port": None,
                        "path": "/editable/alpha",
                    }
                }
            ),
        },
        {
            "name": "grand-child",
            "version": "3.0",
            "record_sha256": _sha256_text("grand/sources.txt\n"),
            "direct_url_sha256": None,
        },
        {
            "name": "zulu-dep",
            "version": "2.0",
            "record_sha256": _sha256_text("zulu-record"),
            "direct_url_sha256": None,
        },
    ]


def test_unfingerprintable_installed_dependency_disables_resume_but_missing_is_skipped():
    root = _FakeDistribution(
        "tradingagents",
        "0.3.1",
        requirements=("Broken_Dep>=1", "not-installed>=1"),
        record="root-record",
    )
    broken = _FakeDistribution("Broken_Dep", "")

    manifest = dependency_closure_manifest(
        "tradingagents",
        distributions=[root, broken],
    )

    assert manifest.resumable is False
    assert manifest.issues == ("unfingerprintable_dependency:broken-dep",)


def test_dependency_record_is_read_only_from_distribution_metadata(tmp_path: Path):
    package_record = tmp_path / "package" / "RECORD"
    metadata_record = tmp_path / "dep-1.0.dist-info" / "RECORD"
    package_record.parent.mkdir()
    metadata_record.parent.mkdir()
    package_record.write_text("unrelated package payload", encoding="utf-8")
    metadata_record.write_text("authoritative metadata", encoding="utf-8")
    root = _FakeDistribution(
        "tradingagents",
        "0.3.1",
        requirements=("dep>=1",),
        record="root-record",
    )
    dependency = _FileBackedDistribution(
        "dep",
        "1.0",
        tmp_path,
        ("package/RECORD", "dep-1.0.dist-info/RECORD"),
    )

    manifest = dependency_closure_manifest(
        "tradingagents",
        distributions=[root, dependency],
    )

    assert manifest.resumable is True
    assert manifest.distributions[0]["record_sha256"] == _sha256_text(
        "authoritative metadata"
    )


def test_resume_fingerprint_document_has_the_exact_approved_top_level_shape():
    fingerprint = _build()

    assert fingerprint.document == {
        "fingerprint_version": 1,
        "request": {
            "ticker": "AAPL",
            "analysis_date": "2026-07-18",
            "asset_type": "stock",
            "selected_analysts": ["news", "market"],
                "max_debate_rounds": 2,
                "max_risk_discuss_rounds": 3,
                "portfolio": None,
            },
        "effective_config": {
            "backend_url": {
                "scheme": "https",
                "host": "api.example.com",
                "port": 443,
                "path": "/v1",
            },
            "llm_provider": "openai",
            "max_tokens": 2048,
            "quick_think_llm": "gpt-4.1-mini",
        },
        "runtime_semantics_hash": "a" * 64,
        "runtime_environment": {
            "python": {
                "implementation": "cpython",
                "version": "3.12.5",
                "cache_tag": "cpython-312",
                "abi_flags": "",
                "platform": "macosx-14.0-arm64",
            },
            "distributions": [
                {
                    "name": "langgraph",
                    "version": "1.1.10",
                    "record_sha256": "b" * 64,
                    "direct_url_sha256": None,
                }
            ],
        },
        "observation_schema": {
            "serializer_version": SERIALIZER_VERSION,
            "business_projection_version": BUSINESS_PROJECTION_VERSION,
            "agent_state_schema_sha256": AGENT_STATE_SCHEMA_SHA256,
        },
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "initial_context_hash": canonical_sha256(
            {
                "instrument_identity": {
                    "company_of_interest": "AAPL",
                    "asset_type": "stock",
                    "instrument_context": {
                        "symbol": "AAPL",
                        "exchange": "NASDAQ",
                    },
                },
                "past_context": "No prior decision memory.",
            }
        ),
    }
    assert fingerprint.sha256 == canonical_sha256(fingerprint.document)


def test_request_initial_context_and_state_schema_mutations_are_incompatible():
    original = _build()
    changed_request = _build(_request(ticker="MSFT"))
    changed_context = _build(
        initial_context={
            "past_context": "A prior decision exists.",
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
        }
    )
    changed_schema = _build(agent_state_schema_sha256="c" * 64)

    assert compare_resume_fingerprints(original, changed_request).mismatch_categories == (
        "request",
    )
    assert compare_resume_fingerprints(original, changed_context).mismatch_categories == (
        "initial_context_hash",
    )
    assert compare_resume_fingerprints(original, changed_schema).mismatch_categories == (
        "observation_schema",
    )


def test_portfolio_constraint_mutation_is_incompatible_with_resume():
    original = _build(
        _request(
            portfolio=PortfolioContext(
                cash=100_000,
                positions=(Position("AAPL", 10, 100),),
                mark_prices={"AAPL": 120},
            )
        )
    )
    changed = _build(
        _request(
            portfolio=PortfolioContext(
                cash=100_000,
                positions=(Position("AAPL", 10, 100),),
                mark_prices={"AAPL": 121},
            )
        )
    )

    assert compare_resume_fingerprints(original, changed).mismatch_categories == (
        "request",
    )


def test_analyst_order_mutation_is_incompatible_with_resume():
    original = _build(_request(selected_analysts=("news", "market")))
    changed = _build(_request(selected_analysts=("market", "news")))

    assert compare_resume_fingerprints(original, changed).mismatch_categories == (
        "request",
    )


def test_comparison_returns_only_safe_categories_and_never_secret_values():
    original = _build()
    changed = _build(
        _request(
            effective_config={
                "llm_provider": "openai",
                "quick_think_llm": "gpt-4.1-mini",
                "max_tokens": 4096,
                "backend_url": "https://api.example.com/v1",
                "OPENAI_API_KEY": "must-never-escape",
            }
        )
    )

    same_with_changed_secret = _build(
        _request(
            effective_config={
                "llm_provider": "openai",
                "quick_think_llm": "gpt-4.1-mini",
                "max_tokens": 2048,
                "backend_url": "https://api.example.com/v1",
                "OPENAI_API_KEY": "a-different-secret",
            }
        )
    )
    assert compare_resume_fingerprints(original, same_with_changed_secret).compatible is True

    comparison = compare_resume_fingerprints(original, changed)

    assert comparison.compatible is False
    assert comparison.mismatch_categories == ("effective_config",)
    assert "must-never-escape" not in repr(comparison)
    assert "4096" not in repr(comparison)


def test_initial_context_credentials_neither_hash_nor_change_compatibility():
    initial_context = {
        "past_context": "No prior decision memory.",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
    }
    without_secret = _build(initial_context=initial_context)
    with_secret = _build(
        initial_context={
            **initial_context,
            "credentials": {"api_key": "must-never-affect-resume"},
        }
    )

    assert with_secret.sha256 == without_secret.sha256
    assert compare_resume_fingerprints(without_secret, with_secret).compatible is True
    assert "must-never-affect-resume" not in repr(with_secret.document)


@pytest.mark.parametrize("tampered_side", ["expected", "actual"])
def test_comparison_rejects_tampered_stored_digest_as_fingerprint_integrity(tampered_side):
    expected = _build()
    actual = _build()
    if tampered_side == "expected":
        expected = replace(expected, sha256="0" * 64)
    else:
        actual = replace(actual, sha256="0" * 64)

    comparison = compare_resume_fingerprints(expected, actual)

    assert comparison.compatible is False
    assert comparison.mismatch_categories == ("fingerprint_integrity",)


@pytest.mark.parametrize(
    ("root_requirements", "child_requirements", "expected_issue"),
    [
        (("not a valid requirement ???",), (), "invalid_requirement:root"),
        (("child>=1",), ("also not valid ???",), "invalid_requirement:child"),
    ],
)
def test_invalid_root_or_transitive_requirement_disables_resume(
    root_requirements,
    child_requirements,
    expected_issue,
):
    root = _FakeDistribution(
        "tradingagents",
        "0.3.1",
        requirements=root_requirements,
        record="root-record",
    )
    child = _FakeDistribution(
        "child",
        "1.0",
        requirements=child_requirements,
        record="child-record",
    )

    manifest = dependency_closure_manifest(
        "tradingagents",
        distributions=[root, child],
    )

    assert manifest.resumable is False
    assert expected_issue in manifest.issues


def test_empty_record_and_sources_metadata_disables_resume():
    root = _FakeDistribution(
        "tradingagents",
        "0.3.1",
        requirements=("empty-metadata>=1",),
        record="root-record",
    )
    dependency = _FakeDistribution(
        "empty-metadata",
        "1.0",
        record="",
        sources="",
    )

    manifest = dependency_closure_manifest(
        "tradingagents",
        distributions=[root, dependency],
    )

    assert manifest.resumable is False
    assert manifest.issues == ("unfingerprintable_dependency:empty-metadata",)


@pytest.mark.parametrize(
    ("secret_shell", "secret_value"),
    [
        ({"credentials": {"api_key": "nested-secret"}}, "nested-secret"),
        ({"transport.authorization": "literal-dotted-secret"}, "literal-dotted-secret"),
        ({"provider_secrets": [{"api_key": "list-secret"}]}, "list-secret"),
    ],
)
def test_initial_context_secret_shells_are_equivalent_to_absence(
    secret_shell,
    secret_value,
):
    initial_context = {
        "past_context": "No prior decision memory.",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
    }

    absent = _build(initial_context=initial_context)
    with_secret_shell = _build(initial_context={**initial_context, **secret_shell})

    assert with_secret_shell.sha256 == absent.sha256
    assert compare_resume_fingerprints(absent, with_secret_shell).compatible is True
    assert secret_value not in repr(with_secret_shell)


@pytest.mark.parametrize(
    "instrument_context",
    [
        {
            "symbol": "AAPL",
            "exchange": "NASDAQ",
            "headers": {"Authorization": "Bearer nested-secret"},
        },
        {
            "symbol": "AAPL",
            "exchange": "NASDAQ",
            "headers.Authorization": "Bearer dotted-secret",
        },
        {
            "symbol": "AAPL",
            "exchange": "NASDAQ",
            "sources": [{"api_key": "list-secret"}],
        },
    ],
)
def test_instrument_identity_secret_shells_are_equivalent_to_absence(
    instrument_context,
):
    base_context = {
        "past_context": "No prior decision memory.",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
    }

    absent = _build(initial_context=base_context)
    with_secret = _build(
        initial_context={**base_context, "instrument_context": instrument_context}
    )

    assert with_secret.sha256 == absent.sha256
    assert compare_resume_fingerprints(absent, with_secret).compatible is True
    assert "secret" not in repr(with_secret.document).lower()


@pytest.mark.parametrize("instrument_identity", [{}, None])
def test_empty_or_none_instrument_identity_is_not_resumable(instrument_identity):
    fingerprint = _build(
        initial_context={
            "past_context": "No prior decision memory.",
            "instrument_identity": instrument_identity,
        }
    )

    assert fingerprint.resumable is False
    assert "initial_context_unavailable" in fingerprint.issues


def test_imported_generated_python_source_changes_runtime_hash(tmp_path: Path):
    package = tmp_path / "tradingagents"
    generated = package / "generated"
    generated.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from .generated.provider import PROVIDER\n",
        encoding="utf-8",
    )
    (generated / "__init__.py").write_text("", encoding="utf-8")
    provider = generated / "provider.py"
    provider.write_text("PROVIDER = 'first'\n", encoding="utf-8")
    before = hash_runtime_sources(package)

    provider.write_text("PROVIDER = 'second'\n", encoding="utf-8")

    assert hash_runtime_sources(package) != before


def _direct_url_manifest(direct_url: str):
    root = _FakeDistribution(
        "tradingagents",
        "0.3.1",
        requirements=("private-wheel>=1",),
        record="root-record",
    )
    dependency = _FakeDistribution(
        "private-wheel",
        "1.0",
        record="wheel-record",
        direct_url=direct_url,
    )
    return dependency_closure_manifest(
        "tradingagents",
        distributions=[root, dependency],
    )


def test_direct_url_credentials_and_query_tokens_do_not_affect_dependency_hash():
    first = _direct_url_manifest(
        '{"url":"https://alice:first@example.com/private.whl?token=one#sha256=abc"}'
    )
    second = _direct_url_manifest(
        '{"url":"https://bob:second@example.com/private.whl?token=two#sha256=abc"}'
    )

    assert first.resumable is True
    assert second.resumable is True
    assert first.distributions == second.distributions
    assert "first" not in repr(first)
    assert "token=one" not in repr(first)


def test_invalid_direct_url_json_disables_resume():
    manifest = _direct_url_manifest("{not-json")

    assert manifest.resumable is False
    assert "unfingerprintable_dependency:private-wheel" in manifest.issues


@pytest.mark.parametrize(
    ("runtime_python", "runtime_distributions", "expected_issue"),
    [
        (
            {"implementation": "cpython", "version": "3.12.5"},
            [
                {
                    "name": "langgraph",
                    "version": "1.1.10",
                    "record_sha256": "b" * 64,
                    "direct_url_sha256": None,
                }
            ],
            "invalid_python_runtime_manifest",
        ),
        (
            {
                "implementation": "cpython",
                "version": "3.12.5",
                "cache_tag": "cpython-312",
                "abi_flags": "",
                "platform": "macosx-14.0-arm64",
            },
            [{"name": "langgraph", "version": "1.1.10"}],
            "invalid_dependency_manifest",
        ),
    ],
)
def test_incomplete_injected_runtime_environment_is_not_resumable(
    runtime_python,
    runtime_distributions,
    expected_issue,
):
    request = _request()
    fingerprint = _build_resume_fingerprint_for_test(
        request,
        effective_config=request.effective_config,
        initial_context={
            "past_context": "No prior decision memory.",
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
        },
        runtime_semantics_hash="a" * 64,
        runtime_python=runtime_python,
        runtime_distributions=runtime_distributions,
    )

    assert fingerprint.resumable is False
    assert expected_issue in fingerprint.issues


def test_failed_checkpoint_capability_report_disables_resume():
    dependencies = DependencyClosureManifest(
        distributions=(
            {
                "name": "langgraph",
                "version": "1.1.10",
                "record_sha256": "b" * 64,
                "direct_url_sha256": None,
            },
        ),
        resumable=True,
    )

    environment = runtime_environment_manifest(
        capability_report={"ok": False, "issues": ["missing pending_writes"]},
        dependency_manifest=dependencies,
    )

    assert environment.resumable is False
    assert "checkpoint_capabilities_unavailable" in environment.issues


def test_fingerprint_requires_complete_matching_effective_config():
    request = _request()
    initial_context = {
        "past_context": "",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "instrument_context": {"symbol": "AAPL"},
    }

    with pytest.raises(ValueError, match="complete effective_config"):
        _build_resume_fingerprint_for_test(
            request,
            effective_config={},
            initial_context=initial_context,
            runtime_semantics_hash="a" * 64,
            runtime_python={
                "implementation": "cpython",
                "version": "3.12.5",
                "cache_tag": "cpython-312",
                "abi_flags": "",
                "platform": "macosx-14.0-arm64",
            },
            runtime_distributions=[
                {
                    "name": "langgraph",
                    "version": "1.1.10",
                    "record_sha256": "b" * 64,
                    "direct_url_sha256": None,
                }
            ],
        )

    with pytest.raises(ValueError, match="do not match"):
        _build_resume_fingerprint_for_test(
            request,
            effective_config={**request.effective_config, "max_tokens": 4096},
            initial_context=initial_context,
            runtime_semantics_hash="a" * 64,
            runtime_python={
                "implementation": "cpython",
                "version": "3.12.5",
                "cache_tag": "cpython-312",
                "abi_flags": "",
                "platform": "macosx-14.0-arm64",
            },
            runtime_distributions=[
                {
                    "name": "langgraph",
                    "version": "1.1.10",
                    "record_sha256": "b" * 64,
                    "direct_url_sha256": None,
                }
            ],
        )


def test_fingerprint_config_comparison_ignores_secret_presence_and_rotation():
    semantic_config = dict(_request().effective_config)
    request = _request(
        effective_config={**semantic_config, "OPENAI_API_KEY": "old-secret"}
    )
    runtime_python = {
        "implementation": "cpython",
        "version": "3.12.5",
        "cache_tag": "cpython-312",
        "abi_flags": "",
        "platform": "macosx-14.0-arm64",
    }
    runtime_distributions = [
        {
            "name": "langgraph",
            "version": "1.1.10",
            "record_sha256": "b" * 64,
            "direct_url_sha256": None,
        }
    ]
    initial_context = {
        "past_context": "",
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "instrument_context": {"symbol": "AAPL"},
    }

    rotated = _build_resume_fingerprint_for_test(
        request,
        effective_config={**semantic_config, "OPENAI_API_KEY": "new-secret"},
        initial_context=initial_context,
        runtime_semantics_hash="a" * 64,
        runtime_python=runtime_python,
        runtime_distributions=runtime_distributions,
    )
    omitted = _build_resume_fingerprint_for_test(
        request,
        effective_config=semantic_config,
        initial_context=initial_context,
        runtime_semantics_hash="a" * 64,
        runtime_python=runtime_python,
        runtime_distributions=runtime_distributions,
    )

    assert rotated.sha256 == omitted.sha256
    assert "secret" not in repr(rotated.document)


def _guard_snapshot(run_id):
    return RunSnapshot.create(
        run_id=run_id,
        ticker="AAPL",
        analysis_date="2026-07-18",
        selected_analysts=("market", "news"),
        llm_provider="openai",
        quick_think_llm="gpt-4.1-mini",
        deep_think_llm="gpt-4.1",
    )


def test_production_checkpoint_guard_persists_fresh_and_authorizes_matching_resume(
    tmp_path,
    monkeypatch,
):
    run_id = generate_run_id()
    store = RunStore(tmp_path)
    store.create_run(_guard_snapshot(run_id))
    request = _request()
    fingerprint = _build(request)
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *_args, **_kwargs: fingerprint,
    )
    guard = FingerprintCheckpointGuard(
        store,
        run_id,
        request,
        request.effective_config,
    )
    initial_context = PreparedInitialContext(
        {
            "past_context": "No prior decision memory.",
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
        }
    )

    fresh = guard(initial_context, SimpleNamespace(latest=None))
    resume = guard(initial_context, SimpleNamespace(latest=object()))

    assert fresh.mode == "fresh"
    assert resume.mode == "resume"
    assert fresh.fingerprint_sha256 == resume.fingerprint_sha256 == fingerprint.sha256
    persisted = store.read_snapshot(run_id)
    assert persisted.resume_fingerprint["sha256"] == fingerprint.sha256
    assert persisted.runtime_semantics_hash == "a" * 64
    assert persisted.agent_state_schema_sha256 == AGENT_STATE_SCHEMA_SHA256


def test_checkpoint_guard_consumes_one_frozen_resume_preauthorization(
    tmp_path,
    monkeypatch,
):
    run_id = generate_run_id()
    store = RunStore(tmp_path)
    store.create_run(_guard_snapshot(run_id))
    request = _request()
    fingerprint = _build(request)
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *_args, **_kwargs: fingerprint,
    )
    guard = FingerprintCheckpointGuard(
        store,
        run_id,
        request,
        request.effective_config,
    )
    initial_context = PreparedInitialContext({"instrument_context": "Apple"})
    guard(initial_context, SimpleNamespace(latest=None))
    access = SimpleNamespace(
        latest=SimpleNamespace(
            config={"configurable": {"checkpoint_id": "checkpoint-1"}},
            checkpoint={"id": "checkpoint-1"},
        )
    )

    authorized = guard.preauthorize(initial_context, access)
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("worker must consume the frozen authorization")
        ),
    )

    consumed = guard(PreparedInitialContext({"instrument_context": "changed"}), access)
    assert consumed == authorized
    assert consumed.mode == "resume"


def test_resume_preauthorization_without_checkpoint_never_mutates_snapshot(
    tmp_path,
    monkeypatch,
):
    run_id = generate_run_id()
    store = RunStore(tmp_path)
    store.create_run(_guard_snapshot(run_id))
    request = _request()
    fingerprint = _build(request)
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *_args, **_kwargs: fingerprint,
    )
    guard = FingerprintCheckpointGuard(
        store,
        run_id,
        request,
        request.effective_config,
    )
    before = store.read_snapshot(run_id)

    with pytest.raises(CheckpointIncompatible) as missing:
        guard.preauthorize(
            PreparedInitialContext({"instrument_context": "Apple"}),
            SimpleNamespace(latest=None),
        )

    assert missing.value.mismatch_categories == ("checkpoint_missing",)
    assert store.read_snapshot(run_id) == before


def test_production_checkpoint_guard_rejects_missing_or_incompatible_fingerprint(
    tmp_path,
    monkeypatch,
):
    run_id = generate_run_id()
    store = RunStore(tmp_path)
    store.create_run(_guard_snapshot(run_id))
    request = _request()
    current = _build(request)
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *_args, **_kwargs: current,
    )
    guard = FingerprintCheckpointGuard(
        store,
        run_id,
        request,
        request.effective_config,
    )
    initial_context = PreparedInitialContext(
        {
            "past_context": "No prior decision memory.",
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "instrument_context": {"symbol": "AAPL", "exchange": "NASDAQ"},
        }
    )

    with pytest.raises(CheckpointIncompatible) as missing:
        guard(initial_context, SimpleNamespace(latest=object()))
    assert missing.value.mismatch_categories == ("fingerprint_missing",)

    guard(initial_context, SimpleNamespace(latest=None))
    changed = _build(_request(ticker="MSFT"))
    monkeypatch.setattr(
        "tradingagents.web.fingerprint.build_resume_fingerprint",
        lambda *_args, **_kwargs: changed,
    )
    with pytest.raises(CheckpointIncompatible) as incompatible:
        guard(initial_context, SimpleNamespace(latest=object()))
    assert incompatible.value.mismatch_categories == ("request",)
