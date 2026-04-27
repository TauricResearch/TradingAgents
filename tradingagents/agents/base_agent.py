"""Abstract base class for trading agents with a standardized analyze contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .utils.schemas import AgentInput, AgentOutput


class BaseAgent(ABC):
    """Base class all trading agents must implement.

    Subclasses provide ``analyze`` which accepts an :class:`AgentInput` and
    returns an :class:`AgentOutput`, ensuring a uniform contract across every
    agent in the system.
    """

    name: str = "unnamed_agent"

    @abstractmethod
    def analyze(self, agent_input: AgentInput) -> AgentOutput:
        """Run analysis and return a standardized output."""
        ...
