"""Executable identity for the formal experiment's outcome semantics.

The declarative research protocol is not enough to identify an executable
readout.  This module content-addresses the installed bytes that reconstruct,
verify, analyse, and govern formal outcomes together with the installed
versions of their numerical and calendar dependencies.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from importlib import metadata, util
from pathlib import Path
from typing import Any


class OutcomeSemanticsResolutionError(RuntimeError):
    """Raised when executable outcome identity cannot be resolved exactly."""


def _installed_package_modules() -> tuple[str, ...]:
    """Enumerate the complete installed package without importing its modules.

    A curated outcome-module list is unsafe: a new helper, adapter, gate, or
    dynamically imported implementation could affect a formal result without
    changing the executable identity.  The formal image is intentionally
    immutable for a trial, so conservatively binding every installed package
    module has the same release boundary and closes that omission class.
    """
    package_root = Path(__file__).resolve().parent
    modules: list[str] = []
    try:
        paths = tuple(package_root.rglob("*.py"))
    except OSError as exc:
        raise OutcomeSemanticsResolutionError(
            "cannot enumerate the installed tradingagents package"
        ) from exc
    for path in paths:
        try:
            relative = path.relative_to(package_root)
        except ValueError as exc:
            raise OutcomeSemanticsResolutionError(
                "installed tradingagents module escaped its package root"
            ) from exc
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        module_name = ".".join(("tradingagents", *parts))
        modules.append(module_name)
    normalized = tuple(sorted(modules))
    if not normalized or len(normalized) != len(set(normalized)):
        raise OutcomeSemanticsResolutionError(
            "installed tradingagents package module set is empty or ambiguous"
        )
    return normalized


OUTCOME_BEARING_MODULES = _installed_package_modules()

OUTCOME_AFFECTING_DEPENDENCIES = (
    "exchange-calendars",
    "numpy",
    "pandas",
    "scipy",
)

_REQUIRED_DEPENDENCIES = frozenset({"exchange-calendars", "numpy", "pandas"})
_DEPENDENCY_IMPORTS = {
    "exchange-calendars": "exchange_calendars",
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
}
_SCHEMA_VERSION = 1
_POLICY_LABEL = "formal-outcome-full-package-installed-bytes-and-dependencies-v2"
_ID_PREFIX = "outcome_semantics_"
_ID_PATTERN = re.compile(r"^outcome_semantics_[0-9a-f]{64}$")
_RUNTIME_VERSION_FIELDS = frozenset({"major", "minor", "micro", "releaselevel", "serial"})
_PYTHON_RUNTIME_FIELDS = frozenset(
    {"implementation", "implementation_version", "language_version", "cache_tag"}
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _read_installed_module_bytes(module_name: str) -> bytes:
    try:
        spec = util.find_spec(module_name)
    except (AttributeError, ImportError, ModuleNotFoundError, ValueError) as exc:
        raise OutcomeSemanticsResolutionError(
            f"cannot resolve outcome-bearing module {module_name!r}"
        ) from exc
    if spec is None or not isinstance(spec.origin, str) or not spec.origin:
        raise OutcomeSemanticsResolutionError(
            f"cannot resolve outcome-bearing module {module_name!r}"
        )

    try:
        path = Path(spec.origin).resolve(strict=True)
        if not path.is_file():
            raise OSError("module origin is not a regular file")
        return path.read_bytes()
    except OSError as exc:
        raise OutcomeSemanticsResolutionError(
            f"cannot read installed bytes for outcome-bearing module {module_name!r}"
        ) from exc


def _installed_dependency_version(distribution: str) -> str | None:
    required = distribution in _REQUIRED_DEPENDENCIES
    import_name = _DEPENDENCY_IMPORTS.get(distribution)
    if import_name is None:
        raise OutcomeSemanticsResolutionError(
            f"outcome dependency policy is incomplete for {distribution!r}"
        )
    try:
        resolved = metadata.version(distribution)
    except metadata.PackageNotFoundError as exc:
        if required:
            raise OutcomeSemanticsResolutionError(
                f"cannot resolve required outcome dependency {distribution!r}"
            ) from exc

        try:
            installed_without_metadata = util.find_spec(import_name) is not None
        except (AttributeError, ImportError, ModuleNotFoundError, ValueError) as find_exc:
            raise OutcomeSemanticsResolutionError(
                f"cannot determine whether outcome dependency {distribution!r} is installed"
            ) from find_exc
        if installed_without_metadata:
            raise OutcomeSemanticsResolutionError(
                f"cannot resolve installed outcome dependency {distribution!r} version"
            ) from exc
        return None
    except Exception as exc:
        raise OutcomeSemanticsResolutionError(
            f"cannot resolve outcome dependency {distribution!r} version"
        ) from exc

    if not isinstance(resolved, str) or not resolved:
        raise OutcomeSemanticsResolutionError(
            f"outcome dependency {distribution!r} has no exact installed version"
        )
    try:
        module_available = util.find_spec(import_name) is not None
    except (AttributeError, ImportError, ModuleNotFoundError, ValueError) as exc:
        raise OutcomeSemanticsResolutionError(
            f"cannot resolve installed outcome dependency {distribution!r} module"
        ) from exc
    if not module_available:
        raise OutcomeSemanticsResolutionError(
            f"cannot resolve installed outcome dependency {distribution!r} module"
        )
    return resolved


def _runtime_version(value: Any, label: str) -> dict[str, int | str]:
    try:
        resolved = {
            "major": value.major,
            "minor": value.minor,
            "micro": value.micro,
            "releaselevel": value.releaselevel,
            "serial": value.serial,
        }
    except AttributeError as exc:
        raise OutcomeSemanticsResolutionError(f"cannot resolve exact {label}") from exc
    if (
        any(
            isinstance(resolved[field], bool) or not isinstance(resolved[field], int)
            for field in ("major", "minor", "micro", "serial")
        )
        or not isinstance(resolved["releaselevel"], str)
        or not resolved["releaselevel"]
    ):
        raise OutcomeSemanticsResolutionError(f"cannot resolve exact {label}")
    return resolved


def _python_runtime_identity() -> dict[str, Any]:
    try:
        implementation = sys.implementation.name
        implementation_version = sys.implementation.version
        cache_tag = sys.implementation.cache_tag
    except AttributeError as exc:
        raise OutcomeSemanticsResolutionError("cannot resolve exact Python implementation") from exc
    if not isinstance(implementation, str) or not implementation:
        raise OutcomeSemanticsResolutionError("cannot resolve exact Python implementation")
    if not isinstance(cache_tag, str) or not cache_tag:
        raise OutcomeSemanticsResolutionError("cannot resolve exact Python cache tag")
    return {
        "implementation": implementation,
        "implementation_version": _runtime_version(
            implementation_version, "Python implementation version"
        ),
        "language_version": _runtime_version(sys.version_info, "Python language version"),
        "cache_tag": cache_tag,
    }


def _validated_python_runtime(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != _PYTHON_RUNTIME_FIELDS:
        raise OutcomeSemanticsResolutionError(
            "resolved Python runtime differs from the frozen policy"
        )
    implementation = value["implementation"]
    cache_tag = value["cache_tag"]
    if not isinstance(implementation, str) or not implementation:
        raise OutcomeSemanticsResolutionError("resolved Python implementation is invalid")
    if not isinstance(cache_tag, str) or not cache_tag:
        raise OutcomeSemanticsResolutionError("resolved Python cache tag is invalid")

    versions: dict[str, dict[str, int | str]] = {}
    for field in ("implementation_version", "language_version"):
        version = value[field]
        if not isinstance(version, Mapping) or set(version) != _RUNTIME_VERSION_FIELDS:
            raise OutcomeSemanticsResolutionError(
                f"resolved Python {field.replace('_', ' ')} is invalid"
            )
        if (
            any(
                isinstance(version[part], bool) or not isinstance(version[part], int)
                for part in ("major", "minor", "micro", "serial")
            )
            or not isinstance(version["releaselevel"], str)
            or not version["releaselevel"]
        ):
            raise OutcomeSemanticsResolutionError(
                f"resolved Python {field.replace('_', ' ')} is invalid"
            )
        versions[field] = {part: version[part] for part in sorted(_RUNTIME_VERSION_FIELDS)}

    return {
        "cache_tag": cache_tag,
        "implementation": implementation,
        **versions,
    }


def _manifest_from_resolved(
    module_bytes: Mapping[str, bytes],
    dependency_versions: Mapping[str, str | None],
    python_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    expected_modules = set(OUTCOME_BEARING_MODULES)
    expected_dependencies = set(OUTCOME_AFFECTING_DEPENDENCIES)
    if set(module_bytes) != expected_modules:
        raise OutcomeSemanticsResolutionError(
            "resolved outcome module set differs from the frozen policy"
        )
    if set(dependency_versions) != expected_dependencies:
        raise OutcomeSemanticsResolutionError(
            "resolved outcome dependency set differs from the frozen policy"
        )

    modules: dict[str, dict[str, int | str]] = {}
    for module_name in sorted(expected_modules):
        installed_bytes = module_bytes[module_name]
        if not isinstance(installed_bytes, bytes):
            raise OutcomeSemanticsResolutionError(
                f"installed bytes for outcome-bearing module {module_name!r} are invalid"
            )
        modules[module_name] = {
            "byte_length": len(installed_bytes),
            "sha256": hashlib.sha256(installed_bytes).hexdigest(),
        }

    dependencies: dict[str, dict[str, bool | str | None]] = {}
    for distribution in sorted(expected_dependencies):
        resolved = dependency_versions[distribution]
        required = distribution in _REQUIRED_DEPENDENCIES
        if (resolved is None and required) or (
            resolved is not None and (not isinstance(resolved, str) or not resolved)
        ):
            raise OutcomeSemanticsResolutionError(
                f"outcome dependency {distribution!r} has no exact installed version"
            )
        dependencies[distribution] = {
            "required": required,
            "version": resolved,
        }

    base = {
        "schema_version": _SCHEMA_VERSION,
        "policy": _POLICY_LABEL,
        "module_material": "exact-installed-file-bytes",
        "module_digest": "sha256",
        "dependency_material": "exact-installed-distribution-version",
        "python_runtime_material": "exact-implementation-and-language-version",
        "modules": modules,
        "dependencies": dependencies,
        "python_runtime": _validated_python_runtime(python_runtime),
    }
    digest = hashlib.sha256(_canonical_json(base).encode("utf-8")).hexdigest()
    return {**base, "outcome_semantics_id": f"{_ID_PREFIX}{digest}"}


def outcome_semantics_manifest() -> dict[str, Any]:
    """Return the fail-closed identity of the installed outcome implementation."""
    module_bytes = {
        module_name: _read_installed_module_bytes(module_name)
        for module_name in OUTCOME_BEARING_MODULES
    }
    dependency_versions = {
        distribution: _installed_dependency_version(distribution)
        for distribution in OUTCOME_AFFECTING_DEPENDENCIES
    }
    return _manifest_from_resolved(module_bytes, dependency_versions, _python_runtime_identity())


def outcome_semantics_id() -> str:
    """Return only the installed executable outcome-semantics content ID."""
    return str(outcome_semantics_manifest()["outcome_semantics_id"])


def require_outcome_semantics(expected_id: str) -> dict[str, Any]:
    """Return the installed manifest only when it matches preregistration.

    Every outcome-bearing read path calls this before loading a price, return,
    statistic, review, or report.  A new checkout or dependency environment
    can still inspect raw immutable rows, but it cannot present them as the
    preregistered formal outcome implementation.
    """
    if not isinstance(expected_id, str) or _ID_PATTERN.fullmatch(expected_id) is None:
        raise OutcomeSemanticsResolutionError(
            "registered outcome semantics identity is malformed"
        )
    manifest = outcome_semantics_manifest()
    if manifest["outcome_semantics_id"] != expected_id:
        raise OutcomeSemanticsResolutionError(
            "installed outcome semantics differ from preregistration"
        )
    return manifest


__all__ = [
    "OUTCOME_AFFECTING_DEPENDENCIES",
    "OUTCOME_BEARING_MODULES",
    "OutcomeSemanticsResolutionError",
    "outcome_semantics_id",
    "outcome_semantics_manifest",
    "require_outcome_semantics",
]
