"""Strict, secret-free semantic fingerprints for checkpoint resume."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import sysconfig
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from tradingagents.dataflows.ticker_utils import normalize_ticker_symbol
from tradingagents.execution.config_identity import (
    normalize_endpoint_identity as normalize_endpoint_identity,
    prepare_effective_config,
    project_effective_config,
    prune_removed_credential_shells,
)
from tradingagents.execution.models import AnalysisRequest
from tradingagents.execution.runner import (
    CheckpointAuthorization,
    PreparedInitialContext,
)
from tradingagents.observability.canonical import (
    AGENT_STATE_SCHEMA_SHA256,
    BUSINESS_PROJECTION_VERSION,
    SERIALIZER_VERSION,
    canonical_json_bytes,
    canonical_sha256,
)
from tradingagents.observability.events import EVENT_SCHEMA_VERSION
from tradingagents.observability.redaction import (
    RedactionRecord,
    remove_credentials_recursive,
)
from tradingagents.web.store import RunStore

FINGERPRINT_VERSION = 1
_SOURCE_EXCLUDED_ROOTS = frozenset({"tests", "fixtures", "frontend"})


class FingerprintError(ValueError):
    """The current runtime cannot produce a truthful resume fingerprint."""


@dataclass(frozen=True)
class DependencyClosureManifest:
    distributions: tuple[dict[str, Any], ...]
    resumable: bool
    issues: tuple[str, ...] = ()

    @property
    def nonresumable_reason(self) -> str | None:
        return None if self.resumable else "unfingerprintable_dependency"

    @property
    def unfingerprintable_dependencies(self) -> tuple[str, ...]:
        prefix = "unfingerprintable_dependency:"
        return tuple(issue.removeprefix(prefix) for issue in self.issues if issue.startswith(prefix))


@dataclass(frozen=True)
class RuntimeEnvironmentManifest:
    document: dict[str, Any]
    resumable: bool
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResumeFingerprintV1:
    document: dict[str, Any]
    sha256: str
    resumable: bool
    issues: tuple[str, ...] = ()
    removed_credentials: tuple[RedactionRecord, ...] = ()


@dataclass(frozen=True)
class FingerprintComparison:
    compatible: bool
    mismatch_categories: tuple[str, ...] = ()


def _prepare_effective_config_with_manifest(
    effective_config: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[RedactionRecord, ...]]:
    projection = project_effective_config(effective_config)
    return projection.value, projection.removed_credentials


def hash_runtime_sources(package_root: str | Path | None = None) -> str:
    """Hash the stable path/byte manifest for all semantic Python sources."""
    root = Path(package_root) if package_root is not None else _default_package_root()
    root = root.resolve()
    before = _source_paths(root)
    before_manifest = {path: _source_identity(path) for path in before}
    digest = hashlib.sha256(b"TradingAgentsRuntimeSourcesV1\0")
    for path in before:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        if before_manifest[path] != _source_identity(path):
            raise FingerprintError("runtime source changed while fingerprinting")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    after = _source_paths(root)
    if before != after or before_manifest != {
        path: _source_identity(path) for path in after
    }:
        raise FingerprintError("runtime source manifest changed while fingerprinting")
    return digest.hexdigest()


def python_runtime_manifest() -> dict[str, str]:
    return {
        "implementation": sys.implementation.name,
        "version": platform.python_version(),
        "cache_tag": sys.implementation.cache_tag or "",
        "abi_flags": getattr(sys, "abiflags", "") or "",
        "platform": sysconfig.get_platform(),
    }


def dependency_closure_manifest(
    root_distribution: str = "tradingagents",
    *,
    distribution_getter: Callable[[str], Any] = metadata.distribution,
    distributions: list[Any] | tuple[Any, ...] | None = None,
) -> DependencyClosureManifest:
    """Fingerprint every installed distribution reachable from Requires-Dist."""
    issues: list[str] = []
    if distributions is not None:
        by_name = {
            canonicalize_name(
                _distribution_metadata_value(distribution, "Name")
                or getattr(distribution, "name", "")
            ): distribution
            for distribution in distributions
        }

        def distribution_getter(name: str) -> Any:
            try:
                return by_name[canonicalize_name(name)]
            except KeyError as exc:
                raise metadata.PackageNotFoundError(name) from exc

    try:
        root = distribution_getter(root_distribution)
    except metadata.PackageNotFoundError:
        return DependencyClosureManifest(
            (),
            False,
            (f"unfingerprintable_dependency:{canonicalize_name(root_distribution)}",),
        )

    pending = deque(_requirement_names(_distribution_requirements(root), issues, "root"))
    visited: set[str] = set()
    entries: list[dict[str, Any]] = []
    while pending:
        requested_name = canonicalize_name(pending.popleft())
        if requested_name in visited:
            continue
        visited.add(requested_name)
        try:
            distribution = distribution_getter(requested_name)
        except metadata.PackageNotFoundError:
            continue

        installed_name = canonicalize_name(
            _distribution_metadata_value(distribution, "Name") or requested_name
        )
        if installed_name in {entry["name"] for entry in entries}:
            continue
        version = str(
            getattr(distribution, "version", "")
            or _distribution_metadata_value(distribution, "Version")
            or ""
        )
        record = _distribution_file_bytes(distribution, "RECORD")
        if record is None:
            record = _distribution_file_bytes(distribution, "SOURCES.txt")
        if not version or not record:
            issues.append(f"unfingerprintable_dependency:{installed_name}")
        entry: dict[str, Any] = {
            "name": installed_name,
            "version": version,
            "record_sha256": hashlib.sha256(record).hexdigest()
            if record
            else None,
            "direct_url_sha256": None,
        }
        direct_url = _distribution_file_bytes(distribution, "direct_url.json")
        if direct_url is not None:
            try:
                safe_direct_url = _safe_direct_url_bytes(direct_url)
            except FingerprintError:
                issues.append(f"unfingerprintable_dependency:{installed_name}")
            else:
                entry["direct_url_sha256"] = hashlib.sha256(
                    safe_direct_url
                ).hexdigest()
        entries.append(entry)
        pending.extend(
            _requirement_names(
                _distribution_requirements(distribution),
                issues,
                installed_name,
            )
        )

    ordered = tuple(sorted(entries, key=lambda item: item["name"]))
    unique_issues = tuple(dict.fromkeys(issues))
    return DependencyClosureManifest(
        ordered,
        not unique_issues,
        unique_issues,
    )


def runtime_environment_manifest(
    *,
    capability_report: Any | None = None,
    dependency_manifest: DependencyClosureManifest | None = None,
) -> RuntimeEnvironmentManifest:
    dependencies = dependency_manifest or dependency_closure_manifest()
    issues = list(dependencies.issues)
    document: dict[str, Any] = {
        "python": python_runtime_manifest(),
        "distributions": list(dependencies.distributions),
    }
    if capability_report is not None:
        report_value = (
            capability_report.as_dict()
            if callable(getattr(capability_report, "as_dict", None))
            else dict(capability_report)
        )
        report_ok = (
            bool(capability_report.ok)
            if hasattr(capability_report, "ok")
            else bool(report_value.get("ok"))
        )
        if not report_ok:
            issues.append("checkpoint_capabilities_unavailable")
    canonical_json_bytes(document)
    return RuntimeEnvironmentManifest(
        document,
        dependencies.resumable and not issues,
        tuple(dict.fromkeys(issues)),
    )


def build_resume_fingerprint(
    request: AnalysisRequest,
    *,
    effective_config: Mapping[str, Any],
    initial_context: Mapping[str, Any],
    capability_report: Any | None = None,
) -> ResumeFingerprintV1:
    """Build a production fingerprint from the actual local runtime."""
    return _build_resume_fingerprint_for_test(
        request,
        effective_config=effective_config,
        initial_context=initial_context,
        runtime_semantics_hash=hash_runtime_sources(),
        runtime_environment=runtime_environment_manifest(
            capability_report=capability_report
        ),
        agent_state_schema_sha256=AGENT_STATE_SCHEMA_SHA256,
    )


def _build_resume_fingerprint_for_test(
    request: AnalysisRequest,
    *,
    effective_config: Mapping[str, Any],
    initial_context: Mapping[str, Any],
    package_root: str | Path | None = None,
    capability_report: Any | None = None,
    runtime_semantics_hash: str | None = None,
    runtime_environment: RuntimeEnvironmentManifest | None = None,
    runtime_python: Mapping[str, Any] | None = None,
    runtime_distributions: list[Mapping[str, Any]] | None = None,
    agent_state_schema_sha256: str = AGENT_STATE_SCHEMA_SHA256,
) -> ResumeFingerprintV1:
    if not effective_config:
        raise FingerprintError("complete effective_config is required")
    prepared_config, credential_manifest = _prepare_effective_config_with_manifest(
        effective_config
    )
    if not prepared_config:
        raise FingerprintError("complete effective_config is required")
    if request.effective_config:
        prepared_request = prepare_effective_config(request.effective_config)
        if prepared_request != prepared_config:
            raise FingerprintError("request and effective_config do not match")
    context, context_credentials, context_complete = _prepare_initial_context(
        initial_context
    )
    if runtime_environment is None and (
        runtime_python is not None or runtime_distributions is not None
    ):
        injected_document, injected_issues = _prepare_injected_runtime_environment(
            runtime_python,
            runtime_distributions,
        )
        environment = RuntimeEnvironmentManifest(
            injected_document,
            not injected_issues,
            injected_issues,
        )
    else:
        environment = runtime_environment or runtime_environment_manifest(
            capability_report=capability_report
        )
    semantics_hash = runtime_semantics_hash or hash_runtime_sources(package_root)
    if not _is_sha256(semantics_hash):
        raise FingerprintError("runtime_semantics_hash must be a SHA-256 digest")
    if not _is_sha256(agent_state_schema_sha256):
        raise FingerprintError("agent_state_schema_sha256 must be a SHA-256 digest")
    document = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "request": {
            "ticker": normalize_ticker_symbol(request.ticker),
            "analysis_date": request.analysis_date,
            "asset_type": request.asset_type,
            "selected_analysts": list(request.selected_analysts),
            "max_debate_rounds": request.max_debate_rounds,
            "max_risk_discuss_rounds": request.max_risk_discuss_rounds,
            "portfolio": asdict(request.portfolio) if request.portfolio is not None else None,
        },
        "effective_config": prepared_config,
        "runtime_semantics_hash": semantics_hash,
        "runtime_environment": environment.document,
        "observation_schema": {
            "serializer_version": SERIALIZER_VERSION,
            "business_projection_version": BUSINESS_PROJECTION_VERSION,
            "agent_state_schema_sha256": agent_state_schema_sha256,
        },
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "initial_context_hash": canonical_sha256(context),
    }
    digest = canonical_sha256(document)
    issues = list(environment.issues)
    if not context_complete:
        issues.append("initial_context_unavailable")
    return ResumeFingerprintV1(
        document=document,
        sha256=digest,
        resumable=environment.resumable and context_complete,
        issues=tuple(dict.fromkeys(issues)),
        removed_credentials=tuple(
            sorted(
                (*credential_manifest, *context_credentials),
                key=lambda record: (record.path, record.normalized_leaf),
            )
        ),
    )


def compare_resume_fingerprints(
    expected: ResumeFingerprintV1,
    actual: ResumeFingerprintV1,
) -> FingerprintComparison:
    try:
        expected_digest = canonical_sha256(expected.document)
        actual_digest = canonical_sha256(actual.document)
    except (TypeError, ValueError):
        return FingerprintComparison(False, ("fingerprint_integrity",))
    if expected.sha256 != expected_digest or actual.sha256 != actual_digest:
        return FingerprintComparison(False, ("fingerprint_integrity",))
    if expected_digest == actual_digest and expected.resumable and actual.resumable:
        return FingerprintComparison(True)
    mismatches = []
    for component in (
        "fingerprint_version",
        "request",
        "effective_config",
        "runtime_semantics_hash",
        "runtime_environment",
        "observation_schema",
        "event_schema_version",
        "initial_context_hash",
    ):
        if canonical_sha256(expected.document.get(component)) != canonical_sha256(
            actual.document.get(component)
        ):
            mismatches.append(component)
    if not expected.resumable or not actual.resumable:
        mismatches.append("resume_eligibility")
    return FingerprintComparison(False, tuple(mismatches))


class CheckpointIncompatible(RuntimeError):
    """A durable checkpoint cannot be opened under the current semantics."""

    def __init__(self, mismatch_categories: tuple[str, ...]):
        self.mismatch_categories = mismatch_categories
        super().__init__(
            "checkpoint_incompatible: " + ", ".join(mismatch_categories)
        )


class CheckpointResumeUnavailable(RuntimeError):
    """The current runtime cannot safely create a resumable checkpoint."""


class FingerprintCheckpointGuard:
    """Persist fresh fingerprints and compare them before opening web checkpoints."""

    def __init__(
        self,
        store: RunStore,
        run_id: str,
        request: AnalysisRequest,
        effective_config: Mapping[str, Any],
        *,
        capability_report: Any | None = None,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.request = request
        self.effective_config = effective_config
        self.capability_report = capability_report
        self._preauthorized: tuple[CheckpointAuthorization, str | None] | None = None

    def preauthorize(
        self,
        initial_context: PreparedInitialContext,
        checkpoint_access: Any,
    ) -> CheckpointAuthorization:
        """Freeze one resume authorization before any resumed event is appended."""
        if self._preauthorized is not None:
            raise RuntimeError("checkpoint guard already has a preauthorization")
        if getattr(checkpoint_access, "latest", None) is None:
            raise CheckpointIncompatible(("checkpoint_missing",))
        authorization = self._authorize(initial_context, checkpoint_access)
        self._preauthorized = (
            authorization,
            _checkpoint_access_id(checkpoint_access),
        )
        return authorization

    def __call__(
        self,
        initial_context: PreparedInitialContext,
        checkpoint_access: Any,
    ) -> CheckpointAuthorization:
        if self._preauthorized is not None:
            authorization, expected_checkpoint_id = self._preauthorized
            self._preauthorized = None
            if _checkpoint_access_id(checkpoint_access) != expected_checkpoint_id:
                raise CheckpointIncompatible(("checkpoint_frontier_drift",))
            return authorization
        return self._authorize(initial_context, checkpoint_access)

    def _authorize(
        self,
        initial_context: PreparedInitialContext,
        checkpoint_access: Any,
    ) -> CheckpointAuthorization:
        current = build_resume_fingerprint(
            self.request,
            effective_config=self.effective_config,
            initial_context=initial_context.values,
            capability_report=self.capability_report,
        )
        if not current.resumable:
            raise CheckpointResumeUnavailable(
                "checkpoint resume is unavailable: " + ", ".join(current.issues)
            )

        mode = "resume" if getattr(checkpoint_access, "latest", None) is not None else "fresh"
        with self.store.lock_for(self.run_id):
            snapshot = self.store.read_snapshot(self.run_id)
            stored_payload = snapshot.resume_fingerprint
            if stored_payload is None:
                if mode == "resume":
                    raise CheckpointIncompatible(("fingerprint_missing",))
                snapshot = snapshot.evolve(
                    resume_fingerprint=_fingerprint_payload(current),
                    runtime_semantics_hash=current.document["runtime_semantics_hash"],
                    agent_state_schema_sha256=current.document["observation_schema"][
                        "agent_state_schema_sha256"
                    ],
                )
                self.store.write_snapshot_atomic(snapshot)
            else:
                stored = _fingerprint_from_payload(stored_payload)
                comparison = compare_resume_fingerprints(stored, current)
                if not comparison.compatible:
                    raise CheckpointIncompatible(comparison.mismatch_categories)

        return CheckpointAuthorization._issue(
            run_id=self.run_id,
            fingerprint_sha256=current.sha256,
            mode=mode,
        )


def _checkpoint_access_id(checkpoint_access: Any) -> str | None:
    latest = getattr(checkpoint_access, "latest", None)
    if latest is None:
        return None
    config = getattr(latest, "config", None)
    checkpoint = getattr(latest, "checkpoint", None)
    configurable = config.get("configurable") if isinstance(config, Mapping) else None
    checkpoint_id = (
        configurable.get("checkpoint_id")
        if isinstance(configurable, Mapping)
        else None
    )
    if checkpoint_id is None and isinstance(checkpoint, Mapping):
        checkpoint_id = checkpoint.get("id")
    return str(checkpoint_id) if checkpoint_id else None


def _fingerprint_payload(fingerprint: ResumeFingerprintV1) -> dict[str, Any]:
    return {
        "document": fingerprint.document,
        "sha256": fingerprint.sha256,
        "resumable": fingerprint.resumable,
        "issues": list(fingerprint.issues),
    }


def _fingerprint_from_payload(payload: Mapping[str, Any]) -> ResumeFingerprintV1:
    try:
        document = payload["document"]
        digest = payload["sha256"]
        resumable = payload["resumable"]
        issues = payload.get("issues", [])
    except (KeyError, TypeError) as exc:
        raise CheckpointIncompatible(("fingerprint_integrity",)) from exc
    if (
        not isinstance(document, Mapping)
        or not isinstance(digest, str)
        or not isinstance(resumable, bool)
        or not isinstance(issues, list)
        or any(not isinstance(issue, str) for issue in issues)
    ):
        raise CheckpointIncompatible(("fingerprint_integrity",))
    return ResumeFingerprintV1(
        document=dict(document),
        sha256=digest,
        resumable=resumable,
        issues=tuple(issues),
    )


def _prepare_initial_context(
    initial_context: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[RedactionRecord, ...], bool]:
    stripped = remove_credentials_recursive(initial_context)
    value = prune_removed_credential_shells(initial_context, stripped.value)
    if isinstance(value, Mapping) and "instrument_identity" in value:
        identity = value.get("instrument_identity")
        context = {
            "past_context": value.get("past_context"),
            "instrument_identity": identity,
        }
        complete = _initial_context_is_complete(context)
    else:
        context = {
            "past_context": value.get("past_context")
            if isinstance(value, Mapping)
            else None,
            "instrument_identity": {
                "company_of_interest": value.get("company_of_interest")
                if isinstance(value, Mapping)
                else None,
                "asset_type": value.get("asset_type")
                if isinstance(value, Mapping)
                else None,
                "instrument_context": value.get("instrument_context")
                if isinstance(value, Mapping)
                else None,
            },
        }
        complete = _initial_context_is_complete(context)
    return context, stripped.manifest, complete


def _source_paths(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise FingerprintError("tradingagents package root is unavailable")
    paths = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts:
            continue
        if relative.parts and relative.parts[0].lower() in _SOURCE_EXCLUDED_ROOTS:
            continue
        paths.append(path)
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def _source_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _default_package_root() -> Path:
    import tradingagents

    package_file = getattr(tradingagents, "__file__", None)
    if package_file is None:
        raise FingerprintError("tradingagents package root is unavailable")
    return Path(package_file).resolve().parent


def _initial_context_is_complete(context: Mapping[str, Any]) -> bool:
    if "past_context" not in context or not isinstance(context["past_context"], str):
        return False
    identity = context.get("instrument_identity")
    if not isinstance(identity, Mapping):
        return False
    company = identity.get("company_of_interest")
    asset_type = identity.get("asset_type")
    instrument = identity.get("instrument_context")
    company_ok = isinstance(company, str) and bool(company.strip())
    asset_ok = asset_type in {"stock", "crypto"}
    instrument_ok = (
        isinstance(instrument, str)
        and bool(instrument.strip())
        or isinstance(instrument, Mapping)
        and bool(instrument)
    )
    return company_ok and asset_ok and instrument_ok


def _prepare_injected_runtime_environment(
    runtime_python: Mapping[str, Any] | None,
    runtime_distributions: list[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    issues: list[str] = []
    python_document = dict(runtime_python or {})
    expected_python_keys = {
        "implementation",
        "version",
        "cache_tag",
        "abi_flags",
        "platform",
    }
    if (
        runtime_python is None
        or set(python_document) != expected_python_keys
        or any(not isinstance(value, str) for value in python_document.values())
        or any(
            not python_document[key]
            for key in expected_python_keys - {"abi_flags"}
        )
    ):
        issues.append("invalid_python_runtime_manifest")

    distribution_documents: list[dict[str, Any]] = []
    expected_distribution_keys = {
        "name",
        "version",
        "record_sha256",
        "direct_url_sha256",
    }
    if runtime_distributions is None or not runtime_distributions:
        issues.append("invalid_dependency_manifest")
    else:
        for item in runtime_distributions:
            document = dict(item)
            record_hash = document.get("record_sha256")
            direct_hash = document.get("direct_url_sha256")
            if (
                set(document) != expected_distribution_keys
                or not isinstance(document.get("name"), str)
                or not document["name"]
                or not isinstance(document.get("version"), str)
                or not document["version"]
                or not isinstance(record_hash, str)
                or not _is_sha256(record_hash)
                or direct_hash is not None
                and (not isinstance(direct_hash, str) or not _is_sha256(direct_hash))
            ):
                issues.append("invalid_dependency_manifest")
            distribution_documents.append(document)
    distribution_documents.sort(
        key=lambda item: canonicalize_name(str(item.get("name", "")))
    )
    return (
        {
            "python": python_document,
            "distributions": distribution_documents,
        },
        tuple(dict.fromkeys(issues)),
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _safe_direct_url_bytes(raw: bytes) -> bytes:
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FingerprintError("direct_url.json is invalid") from exc
    if not isinstance(parsed, Mapping):
        raise FingerprintError("direct_url.json must be an object")
    stripped = remove_credentials_recursive(parsed)
    value = prune_removed_credential_shells(parsed, stripped.value)
    url = value.get("url") if isinstance(value, Mapping) else None
    if not isinstance(url, str) or not url.strip():
        raise FingerprintError("direct_url.json requires a URL")
    document = dict(value)
    document["url"] = _safe_distribution_url(url)
    return canonical_json_bytes(document)


def _safe_distribution_url(value: str) -> dict[str, Any]:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise FingerprintError("direct distribution URL is invalid") from exc
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or scheme != "file" and not host:
        raise FingerprintError("direct distribution URL requires a scheme and host")
    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": parsed.path or "/",
    }


def _requirement_names(
    requirements: list[str] | tuple[str, ...] | None,
    issues: list[str],
    parent: str,
) -> list[str]:
    names = []
    for raw in requirements or ():
        try:
            names.append(Requirement(raw).name)
        except InvalidRequirement:
            issues.append(f"invalid_requirement:{canonicalize_name(parent)}")
    return names


def _distribution_requirements(distribution: Any) -> list[str] | tuple[str, ...] | None:
    requires = getattr(distribution, "requires", None)
    if requires is not None:
        return requires
    requirements = getattr(distribution, "requirements", None)
    if requirements is not None:
        return requirements
    metadata_value = getattr(distribution, "metadata", None)
    get_all = getattr(metadata_value, "get_all", None)
    if callable(get_all):
        return get_all("Requires-Dist", [])
    return None


def _distribution_metadata_value(distribution: Any, key: str) -> str | None:
    values = getattr(distribution, "metadata", None)
    if values is None:
        return None
    value = values.get(key)
    return str(value) if value is not None else None


def _distribution_file_bytes(distribution: Any, basename: str) -> bytes | None:
    read_text = getattr(distribution, "read_text", None)
    if callable(read_text):
        try:
            value = read_text(basename)
        except (OSError, TypeError, UnicodeError):
            return None
        if value is not None:
            return value.encode("utf-8")
    for entry in getattr(distribution, "files", None) or ():
        name = str(entry).replace("\\", "/")
        parent_parts = name.split("/")[:-1]
        is_metadata_file = any(
            part.endswith((".dist-info", ".egg-info")) for part in parent_parts
        )
        if is_metadata_file and name.endswith(f"/{basename}"):
            try:
                return Path(distribution.locate_file(entry)).read_bytes()
            except (OSError, TypeError):
                return None
    return None
