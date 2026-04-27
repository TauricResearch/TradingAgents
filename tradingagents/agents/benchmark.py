"""Agent benchmarking: compare outputs across different LLM backends."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tradingagents.agents.base_agent import BaseAgent
from tradingagents.agents.utils.schemas import AgentInput, AgentOutput
from tradingagents.llm_clients import create_llm_client


@dataclass
class BenchmarkResult:
    """Result of a single agent run against one LLM backend."""

    agent_name: str
    provider: str
    model: str
    output: AgentOutput | None
    elapsed_seconds: float
    error: str | None = None


@dataclass
class BenchmarkReport:
    """Aggregated results from benchmarking one or more agents across backends."""

    results: list[BenchmarkResult] = field(default_factory=list)

    def summary(self) -> list[dict[str, Any]]:
        """Return a list of dicts summarising each result for easy comparison."""
        rows: list[dict[str, Any]] = []
        for r in self.results:
            row: dict[str, Any] = {
                "agent": r.agent_name,
                "provider": r.provider,
                "model": r.model,
                "elapsed_s": round(r.elapsed_seconds, 2),
            }
            if r.error:
                row["error"] = r.error
            elif r.output:
                row["rating"] = r.output.rating
                row["confidence"] = r.output.confidence
                row["thesis_len"] = len(r.output.thesis)
                row["risk_factors"] = len(r.output.risk_factors)
            rows.append(row)
        return rows


@dataclass
class LLMBackend:
    """Describes an LLM backend to benchmark against."""

    provider: str
    model: str
    base_url: str | None = None
    kwargs: dict[str, Any] = field(default_factory=dict)


def _make_llm(backend: LLMBackend) -> Any:
    """Create a LangChain LLM from a backend spec."""
    client = create_llm_client(
        provider=backend.provider,
        model=backend.model,
        base_url=backend.base_url,
        **backend.kwargs,
    )
    return client.get_llm()


def benchmark_agent(
    agent_cls: type[BaseAgent],
    agent_input: AgentInput,
    backends: list[LLMBackend],
    **agent_kwargs: Any,
) -> BenchmarkReport:
    """Run *agent_cls* with *agent_input* across each backend and collect results.

    Args:
        agent_cls: A ``BaseAgent`` subclass whose ``__init__`` accepts a single
            ``llm`` positional argument.
        agent_input: The standardized input to feed every agent instance.
        backends: LLM backends to compare.
        **agent_kwargs: Additional keyword arguments forwarded to the
            *agent_cls* constructor (e.g. ``tools``, ``config``).

    Returns:
        A :class:`BenchmarkReport` with one :class:`BenchmarkResult` per backend.
    """
    report = BenchmarkReport()
    for backend in backends:
        t0 = time.monotonic()
        try:
            llm = _make_llm(backend)
            agent = agent_cls(llm, **agent_kwargs)
            output = agent.analyze(agent_input)
            elapsed = time.monotonic() - t0
            report.results.append(
                BenchmarkResult(
                    agent_name=agent.name,
                    provider=backend.provider,
                    model=backend.model,
                    output=output,
                    elapsed_seconds=elapsed,
                )
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            report.results.append(
                BenchmarkResult(
                    agent_name=agent_cls.name if hasattr(agent_cls, "name") else agent_cls.__name__,
                    provider=backend.provider,
                    model=backend.model,
                    output=None,
                    elapsed_seconds=elapsed,
                    error=str(exc),
                )
            )
    return report


def benchmark_agents(
    agent_classes: list[type[BaseAgent]],
    agent_input: AgentInput,
    backends: list[LLMBackend],
    **agent_kwargs: Any,
) -> BenchmarkReport:
    """Run multiple agent types across multiple backends.

    Convenience wrapper that calls :func:`benchmark_agent` for each class and
    merges the results into a single report.

    Args:
        agent_classes: Agent subclasses to benchmark.
        agent_input: The standardized input to feed every agent instance.
        backends: LLM backends to compare.
        **agent_kwargs: Additional keyword arguments forwarded to each
            agent constructor.
    """
    merged = BenchmarkReport()
    for cls in agent_classes:
        report = benchmark_agent(cls, agent_input, backends, **agent_kwargs)
        merged.results.extend(report.results)
    return merged
