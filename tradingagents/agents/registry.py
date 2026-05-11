"""AgentRegistry for pluggable agent discovery."""

from __future__ import annotations

from typing import Callable

from .base_agent import BaseAgent


class AgentRegistry:
    """Registry that maps agent names to their factory callables.

    Usage::

        registry = AgentRegistry()
        registry.register("fundamentals", FundamentalsAgent, llm=my_llm)
        agent = registry.get("fundamentals")
        output = agent.analyze(agent_input)

    Agents can be registered either as a pre-built instance or as a class
    (with optional ``**kwargs`` forwarded to the constructor on first access).
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], BaseAgent]] = {}
        self._instances: dict[str, BaseAgent] = {}

    def register(
        self,
        name: str,
        agent: type[BaseAgent] | BaseAgent,
        **kwargs,
    ) -> None:
        """Register an agent class or instance under *name*.

        If *agent* is a class, ``kwargs`` are forwarded to its constructor
        when :meth:`get` is called.  If it is already an instance, it is
        stored directly.
        """
        # Evict stale cached instance so the new registration takes effect.
        self._instances.pop(name, None)
        self._factories.pop(name, None)

        if isinstance(agent, BaseAgent):
            self._instances[name] = agent
        elif isinstance(agent, type) and issubclass(agent, BaseAgent):
            self._factories[name] = lambda: agent(**kwargs)
        else:
            raise TypeError(f"Expected BaseAgent subclass or instance, got {type(agent)}")

    def get(self, name: str) -> BaseAgent:
        """Return the agent registered under *name*, instantiating lazily if needed."""
        if name not in self._instances:
            if name not in self._factories:
                raise KeyError(f"No agent registered under '{name}'")
            self._instances[name] = self._factories[name]()
            del self._factories[name]
        return self._instances[name]

    def list(self) -> list[str]:
        """Return sorted list of all registered agent names."""
        return sorted({*self._factories, *self._instances})

    def __contains__(self, name: str) -> bool:
        return name in self._factories or name in self._instances

    def __len__(self) -> int:
        return len(self.list())
