"""Hard runtime capability checks for the localhost web workbench."""

from __future__ import annotations

import inspect
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import TypedDict


INSTALL_COMMAND = "python -m pip install --upgrade 'tradingagents[web]'"

GRAPH_RUNTIME_REQUIREMENTS = {
    "langgraph": ">=1.1.10,<2",
    "langgraph-checkpoint": ">=4.0.3,<5",
    "langgraph-checkpoint-sqlite": ">=3.0.3,<4",
}

WEB_DEPENDENCY_REQUIREMENTS = {
    "fastapi": ">=0.115,<1",
    "uvicorn": ">=0.30,<1",
    "rfc8785": ">=0.1.4,<1",
}


@dataclass(frozen=True)
class GraphFeatureProbe:
    """Observed checkpoint features required by the resume protocol."""

    sync_durability: bool = False
    task_stream: bool = False
    checkpoint_stream: bool = False
    task_ids: bool = False
    checkpoint_ids: bool = False
    checkpoint_steps: bool = False
    pending_writes: bool = False

    @property
    def ok(self) -> bool:
        return all(asdict(self).values())


@dataclass(frozen=True)
class WebCapabilityReport:
    """Serializable runtime evidence consumed by startup and fingerprinting."""

    versions: dict[str, str | None]
    requirements: dict[str, str]
    stream_accepts_durability: bool
    graph_features: GraphFeatureProbe
    issues: tuple[str, ...] = ()
    install_command: str = INSTALL_COMMAND

    @property
    def ok(self) -> bool:
        return (
            not self.issues
            and self.stream_accepts_durability
            and self.graph_features.ok
        )

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["ok"] = self.ok
        return result


class WebRuntimeError(RuntimeError):
    """Raised before server startup when checkpoint guarantees are unavailable."""

    def __init__(self, report: WebCapabilityReport):
        self.report = report
        details = "; ".join(report.issues) or "required graph capability is missing"
        super().__init__(
            f"TradingAgents web runtime preflight failed: {details}. "
            f"Install or upgrade with: {report.install_command}"
        )


def _installed_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _version_satisfies(version: str, requirement: str) -> bool:
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
    except ImportError:
        return False
    try:
        return Version(version) in SpecifierSet(requirement)
    except Exception:
        return False


def _stream_accepts_durability() -> bool:
    from langgraph.pregel import Pregel

    return "durability" in inspect.signature(Pregel.stream).parameters


class _ProbeState(TypedDict):
    value: int


def _increment_probe(state: _ProbeState) -> _ProbeState:
    return {"value": state["value"] + 1}


def _run_feature_probe() -> GraphFeatureProbe:
    """Execute a real temporary SQLite graph and inspect its emitted evidence."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(_ProbeState)
    builder.add_node("increment", _increment_probe)
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)

    with tempfile.TemporaryDirectory(prefix="tradingagents-web-preflight-") as temp_dir:
        database = Path(temp_dir) / "checkpoint.sqlite"
        connection = sqlite3.connect(database, check_same_thread=False)
        try:
            saver = SqliteSaver(connection)
            graph = builder.compile(checkpointer=saver)
            config = {"configurable": {"thread_id": "web-preflight"}}
            events = list(
                graph.stream(
                    {"value": 0},
                    config,
                    stream_mode=["tasks", "checkpoints"],
                    durability="sync",
                )
            )
            checkpoint_tuple = saver.get_tuple(config)
        finally:
            connection.close()

    task_payloads = [payload for mode, payload in events if mode == "tasks"]
    checkpoint_payloads = [
        payload for mode, payload in events if mode == "checkpoints"
    ]
    return GraphFeatureProbe(
        sync_durability=True,
        task_stream=bool(task_payloads),
        checkpoint_stream=bool(checkpoint_payloads),
        task_ids=bool(task_payloads)
        and all(isinstance(payload.get("id"), str) for payload in task_payloads),
        checkpoint_ids=bool(checkpoint_payloads)
        and all(
            isinstance(
                payload.get("config", {})
                .get("configurable", {})
                .get("checkpoint_id"),
                str,
            )
            for payload in checkpoint_payloads
        ),
        checkpoint_steps=bool(checkpoint_payloads)
        and all(
            isinstance(payload.get("metadata", {}).get("step"), int)
            for payload in checkpoint_payloads
        ),
        pending_writes=checkpoint_tuple is not None
        and hasattr(checkpoint_tuple, "pending_writes"),
    )


def check_web_runtime(
    *,
    include_web_dependencies: bool = True,
    run_probe: bool = True,
) -> WebCapabilityReport:
    """Collect all startup capability evidence without raising."""
    requirements = dict(GRAPH_RUNTIME_REQUIREMENTS)
    if include_web_dependencies:
        requirements.update(WEB_DEPENDENCY_REQUIREMENTS)

    versions = {name: _installed_version(name) for name in requirements}
    issues: list[str] = []
    for name, requirement in requirements.items():
        installed = versions[name]
        if installed is None:
            issues.append(f"missing distribution {name} ({requirement})")
        elif not _version_satisfies(installed, requirement):
            issues.append(f"unsupported {name} {installed} (requires {requirement})")

    accepts_durability = False
    features = GraphFeatureProbe()
    graph_versions_ok = all(
        versions.get(name) is not None
        and _version_satisfies(versions[name] or "", requirement)
        for name, requirement in GRAPH_RUNTIME_REQUIREMENTS.items()
    )
    if graph_versions_ok:
        try:
            accepts_durability = _stream_accepts_durability()
        except Exception as exc:
            issues.append(f"unable to inspect LangGraph stream: {type(exc).__name__}: {exc}")
        if not accepts_durability:
            issues.append("LangGraph Pregel.stream has no durability parameter")

        if run_probe and accepts_durability:
            try:
                features = _run_feature_probe()
            except Exception as exc:
                issues.append(f"SQLite graph capability probe failed: {type(exc).__name__}: {exc}")
            else:
                for name, available in asdict(features).items():
                    if not available:
                        issues.append(f"SQLite graph capability missing: {name}")
    else:
        issues.append("LangGraph runtime floor is not satisfied; capability probe skipped")

    return WebCapabilityReport(
        versions=versions,
        requirements=requirements,
        stream_accepts_durability=accepts_durability,
        graph_features=features,
        issues=tuple(issues),
    )


def ensure_web_runtime() -> WebCapabilityReport:
    """Return runtime evidence or fail before a web server can start."""
    report = check_web_runtime()
    if not report.ok:
        raise WebRuntimeError(report)
    return report

