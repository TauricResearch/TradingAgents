# ops/guardrails/base.py
"""Guardrail rule primitives.

A Rule inspects an Order in the context of broker state + config and either
allows the order through or rejects it with a structured reason. Rules are
pure with respect to broker state read at evaluation time; they do not mutate
broker state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from ops.broker.base import Broker
from ops.broker.types import Order
from ops.config import OpsConfig


@dataclass(frozen=True)
class RuleResult:
    allowed: bool
    reason: str = ""

    @classmethod
    def allow(cls) -> "RuleResult":
        return cls(allowed=True)

    @classmethod
    def reject(cls, reason: str) -> "RuleResult":
        return cls(allowed=False, reason=reason)


@dataclass(frozen=True)
class RuleContext:
    order: Order
    broker: Broker
    config: OpsConfig


class Rule(ABC):
    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def check(self, ctx: RuleContext) -> RuleResult: ...
