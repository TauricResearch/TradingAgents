from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

import pytest

from tradingagents import outcome_semantics


def _module_bytes() -> dict[str, bytes]:
    return {
        module_name: f"installed bytes for {module_name}".encode()
        for module_name in outcome_semantics.OUTCOME_BEARING_MODULES
    }


def _dependency_versions() -> dict[str, str | None]:
    return {
        "exchange-calendars": "4.13.2",
        "numpy": "2.5.1",
        "pandas": "3.0.5",
        "scipy": None,
    }


def _python_runtime() -> dict:
    return {
        "implementation": "cpython",
        "implementation_version": {
            "major": 3,
            "minor": 13,
            "micro": 7,
            "releaselevel": "final",
            "serial": 0,
        },
        "language_version": {
            "major": 3,
            "minor": 13,
            "micro": 7,
            "releaselevel": "final",
            "serial": 0,
        },
        "cache_tag": "cpython-313",
    }


@pytest.mark.unit
def test_installed_outcome_semantics_manifest_is_stable_and_complete():
    first = outcome_semantics.outcome_semantics_manifest()
    second = outcome_semantics.outcome_semantics_manifest()

    assert first == second
    assert outcome_semantics.outcome_semantics_id() == first["outcome_semantics_id"]
    assert first["schema_version"] == 1
    assert first["policy"] \
        == "formal-outcome-full-package-installed-bytes-and-dependencies-v2"
    assert set(first["modules"]) == set(outcome_semantics.OUTCOME_BEARING_MODULES)
    assert set(first["dependencies"]) == set(outcome_semantics.OUTCOME_AFFECTING_DEPENDENCIES)
    assert first["outcome_semantics_id"].startswith("outcome_semantics_")
    assert len(first["outcome_semantics_id"].removeprefix("outcome_semantics_")) == 64
    try:
        scipy_version = metadata.version("scipy")
    except metadata.PackageNotFoundError:
        scipy_version = None
    assert first["dependencies"]["scipy"] == {
        "required": False,
        "version": scipy_version,
    }
    assert first["python_runtime"] == outcome_semantics._python_runtime_identity()
    assert first["python_runtime"]["implementation"] == sys.implementation.name
    assert outcome_semantics.require_outcome_semantics(
        first["outcome_semantics_id"]
    ) == first


@pytest.mark.unit
@pytest.mark.parametrize(
    "expected_id",
    [
        "",
        "outcome_semantics_short",
        "outcome_semantics_" + "g" * 64,
        "outcome_semantics_" + "0" * 64,
    ],
)
def test_outcome_access_fails_closed_on_malformed_or_drifted_identity(expected_id):
    with pytest.raises(outcome_semantics.OutcomeSemanticsResolutionError):
        outcome_semantics.require_outcome_semantics(expected_id)


@pytest.mark.unit
def test_outcome_identity_covers_every_installed_tradingagents_python_module():
    package_root = Path(outcome_semantics.__file__).resolve().parent
    expected = set()
    for path in package_root.rglob("*.py"):
        parts = list(path.relative_to(package_root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        expected.add(".".join(("tradingagents", *parts)))

    assert set(outcome_semantics.OUTCOME_BEARING_MODULES) == expected
    assert {
        "tradingagents.formal_activation",
        "tradingagents.formal_configuration",
        "tradingagents.formal_experiment",
        "tradingagents.formal_governance",
        "tradingagents.global_research",
        "tradingagents.llm_guard",
        "tradingagents.outcome_semantics",
    } <= expected


@pytest.mark.unit
def test_resolved_input_order_does_not_change_outcome_semantics_id():
    modules = _module_bytes()
    dependencies = _dependency_versions()
    python_runtime = _python_runtime()

    forward = outcome_semantics._manifest_from_resolved(modules, dependencies, python_runtime)
    reversed_inputs = outcome_semantics._manifest_from_resolved(
        dict(reversed(list(modules.items()))),
        dict(reversed(list(dependencies.items()))),
        dict(reversed(list(python_runtime.items()))),
    )

    assert forward == reversed_inputs


@pytest.mark.unit
@pytest.mark.parametrize("module_name", outcome_semantics.OUTCOME_BEARING_MODULES)
def test_any_outcome_module_byte_mutation_changes_identity(module_name):
    modules = _module_bytes()
    dependencies = _dependency_versions()
    python_runtime = _python_runtime()
    baseline = outcome_semantics._manifest_from_resolved(modules, dependencies, python_runtime)

    mutated = dict(modules)
    mutated[module_name] += b"\x00"
    changed = outcome_semantics._manifest_from_resolved(mutated, dependencies, python_runtime)

    assert changed["outcome_semantics_id"] != baseline["outcome_semantics_id"]


@pytest.mark.unit
@pytest.mark.parametrize("distribution", outcome_semantics.OUTCOME_AFFECTING_DEPENDENCIES)
def test_any_dependency_version_mutation_changes_identity(distribution):
    modules = _module_bytes()
    dependencies = _dependency_versions()
    python_runtime = _python_runtime()
    baseline = outcome_semantics._manifest_from_resolved(modules, dependencies, python_runtime)

    mutated = dict(dependencies)
    mutated[distribution] = "installed-version-mutation"
    changed = outcome_semantics._manifest_from_resolved(modules, mutated, python_runtime)

    assert changed["outcome_semantics_id"] != baseline["outcome_semantics_id"]


@pytest.mark.unit
@pytest.mark.parametrize("missing_kind", ("module", "dependency", "python_runtime"))
def test_missing_resolved_input_fails_closed(missing_kind):
    modules = _module_bytes()
    dependencies = _dependency_versions()
    python_runtime = _python_runtime()
    if missing_kind == "module":
        modules.pop(next(iter(modules)))
    elif missing_kind == "dependency":
        dependencies.pop(next(iter(dependencies)))
    else:
        python_runtime.pop("implementation")

    with pytest.raises(
        outcome_semantics.OutcomeSemanticsResolutionError,
        match="differs from the frozen policy",
    ):
        outcome_semantics._manifest_from_resolved(modules, dependencies, python_runtime)


@pytest.mark.unit
@pytest.mark.parametrize(
    "runtime_field",
    ("implementation", "implementation_version", "language_version", "cache_tag"),
)
def test_any_python_runtime_mutation_changes_identity(runtime_field):
    modules = _module_bytes()
    dependencies = _dependency_versions()
    python_runtime = _python_runtime()
    baseline = outcome_semantics._manifest_from_resolved(modules, dependencies, python_runtime)

    mutated = dict(python_runtime)
    if runtime_field in {"implementation_version", "language_version"}:
        mutated[runtime_field] = {
            **python_runtime[runtime_field],
            "micro": python_runtime[runtime_field]["micro"] + 1,
        }
    else:
        mutated[runtime_field] += "-mutated"
    changed = outcome_semantics._manifest_from_resolved(modules, dependencies, mutated)

    assert changed["outcome_semantics_id"] != baseline["outcome_semantics_id"]


@pytest.mark.unit
def test_unresolvable_module_file_fails_closed(monkeypatch):
    monkeypatch.setattr(outcome_semantics.util, "find_spec", lambda _name: None)

    with pytest.raises(
        outcome_semantics.OutcomeSemanticsResolutionError,
        match="cannot resolve outcome-bearing module",
    ):
        outcome_semantics.outcome_semantics_manifest()


@pytest.mark.unit
def test_unresolvable_required_dependency_version_fails_closed(monkeypatch):
    installed_version = outcome_semantics.metadata.version

    def missing_numpy(distribution):
        if distribution == "numpy":
            raise metadata.PackageNotFoundError(distribution)
        return installed_version(distribution)

    monkeypatch.setattr(outcome_semantics.metadata, "version", missing_numpy)

    with pytest.raises(
        outcome_semantics.OutcomeSemanticsResolutionError,
        match="required outcome dependency 'numpy'",
    ):
        outcome_semantics.outcome_semantics_manifest()


@pytest.mark.unit
def test_installed_optional_dependency_without_version_fails_closed(monkeypatch):
    def missing_scipy(_distribution):
        raise metadata.PackageNotFoundError("scipy")

    monkeypatch.setattr(outcome_semantics.metadata, "version", missing_scipy)
    monkeypatch.setattr(outcome_semantics.util, "find_spec", lambda _name: object())

    with pytest.raises(
        outcome_semantics.OutcomeSemanticsResolutionError,
        match="installed outcome dependency 'scipy' version",
    ):
        outcome_semantics._installed_dependency_version("scipy")
