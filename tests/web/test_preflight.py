import subprocess
import sys
import textwrap
from importlib import import_module

import pytest

from tradingagents.web import preflight

pytestmark = pytest.mark.unit


def test_current_graph_runtime_proves_every_checkpoint_capability():
    report = preflight.check_web_runtime(include_web_dependencies=False)

    assert report.ok, report.issues
    assert report.stream_accepts_durability is True
    assert report.graph_features.ok is True
    assert report.graph_features.sync_durability is True
    assert report.graph_features.task_stream is True
    assert report.graph_features.checkpoint_stream is True
    assert report.graph_features.task_ids is True
    assert report.graph_features.checkpoint_ids is True
    assert report.graph_features.checkpoint_steps is True
    assert report.graph_features.pending_writes is True


def test_version_failure_is_actionable_and_skips_capability_probe(monkeypatch):
    versions = {
        "langgraph": "1.0.0",
        "langgraph-checkpoint": "4.0.3",
        "langgraph-checkpoint-sqlite": "3.0.3",
    }
    probe = pytest.fail
    monkeypatch.setattr(preflight, "_installed_version", versions.get)
    monkeypatch.setattr(preflight, "_run_feature_probe", probe)

    report = preflight.check_web_runtime(
        include_web_dependencies=False,
        run_probe=True,
    )

    assert report.ok is False
    assert any("unsupported langgraph 1.0.0" in issue for issue in report.issues)
    assert any("probe skipped" in issue for issue in report.issues)


def test_missing_durability_parameter_is_a_hard_failure(monkeypatch):
    monkeypatch.setattr(preflight, "_stream_accepts_durability", lambda: False)

    report = preflight.check_web_runtime(
        include_web_dependencies=False,
        run_probe=True,
    )

    assert report.ok is False
    assert "LangGraph Pregel.stream has no durability parameter" in report.issues


def test_ensure_runtime_reports_install_command(monkeypatch):
    failed = preflight.WebCapabilityReport(
        versions={"fastapi": None},
        requirements={"fastapi": ">=0.115,<1"},
        stream_accepts_durability=False,
        graph_features=preflight.GraphFeatureProbe(),
        issues=("missing distribution fastapi (>=0.115,<1)",),
    )
    monkeypatch.setattr(preflight, "check_web_runtime", lambda: failed)

    with pytest.raises(preflight.WebRuntimeError) as exc_info:
        preflight.ensure_web_runtime()

    assert exc_info.value.report is failed
    assert "tradingagents[web]" in str(exc_info.value)
    assert "missing distribution fastapi" in str(exc_info.value)


def test_report_is_serializable_runtime_fingerprint_evidence():
    report = preflight.check_web_runtime(
        include_web_dependencies=False,
        run_probe=False,
    )

    payload = report.as_dict()
    assert payload["versions"] == report.versions
    assert payload["requirements"] == report.requirements
    assert payload["graph_features"]["pending_writes"] is False
    assert payload["ok"] is False


def test_web_package_import_does_not_import_optional_frameworks(monkeypatch):
    imported = []
    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"fastapi", "uvicorn", "rfc8785"}:
            imported.append(name)
            raise AssertionError(f"unexpected optional import: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    module = import_module("tradingagents.web")

    assert module is not None
    assert imported == []


def test_base_graph_import_does_not_require_web_only_rfc8785():
    script = textwrap.dedent(
        """
        import builtins

        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split('.', 1)[0] == 'rfc8785':
                raise ModuleNotFoundError('rfc8785 intentionally unavailable')
            return real_import(name, *args, **kwargs)

        builtins.__import__ = guarded_import
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        assert TradingAgentsGraph is not None
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
