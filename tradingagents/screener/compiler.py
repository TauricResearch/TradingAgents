"""A parsed query, compiled to SQL over ``metrics_snapshot``.

Two rules make the SQL safe whatever the user typed:

- identifiers come only from the catalog: a metric reference compiles to its
  catalog key, which must be a key of ``catalog.METRICS`` (snake_case, checked
  again here), never to text from the query;
- every literal (number or string) is a bound ``?`` parameter.

Custom ratios compile inline: a reference to one is replaced by its own
expression, compiled the same way, in parentheses. Nothing is materialised.

NULL semantics are SQL's: a comparison with a missing value is unknown, NOT of
unknown is still unknown, and only a definitely true condition matches. So a
stock missing any value a condition needs is left out, unless another branch of
an OR is true for it. Division by zero gives NULL (``NULLIF``), never an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tradingagents.screener import catalog
from tradingagents.screener.query import (
    BinOp,
    BoolOp,
    Compare,
    InList,
    Neg,
    Node,
    Not,
    Num,
    QueryError,
    Ref,
    Str,
)

MAX_RATIO_DEPTH = 8  # custom ratios inside custom ratios
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SQL_CMP = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "=": "=", "!=": "<>"}


def column(key: str) -> str:
    """The quoted snapshot column of a catalog metric. Raises for anything else."""
    if key not in catalog.METRICS or not _IDENTIFIER.match(key):
        raise ValueError(f"not a catalog metric: {key!r}")
    return f'"{key}"'


@dataclass
class Compiled:
    sql: str
    params: list = field(default_factory=list)


class Compiler:
    """Compiles ASTs; ``ratios`` maps a custom ratio's normalised name to its AST."""

    def __init__(self, ratios: dict[str, Node] | None = None, text: str = ""):
        self.ratios = ratios or {}
        self.text = text
        self.expanding: list[str] = []

    def compile(self, node: Node) -> Compiled:
        params: list = []
        sql = self._sql(node, params)
        return Compiled(sql, params)

    def _sql(self, node: Node, params: list) -> str:
        if isinstance(node, Num):
            params.append(float(node.value))
            return "?"
        if isinstance(node, Str):
            params.append(str(node.value))
            return "?"
        if isinstance(node, Ref):
            if node.name.kind == "metric":
                return column(node.name.key)
            return self._ratio(node, params)
        if isinstance(node, Neg):
            return f"(-{self._sql(node.operand, params)})"
        if isinstance(node, BinOp):
            left, right = self._sql(node.left, params), self._sql(node.right, params)
            if node.op == "/":
                return f"({left} / NULLIF({right}, 0))"
            if node.op not in "+-*":
                raise ValueError(f"unknown operator {node.op!r}")
            return f"({left} {node.op} {right})"
        if isinstance(node, Compare):
            left, right = self._sql(node.left, params), self._sql(node.right, params)
            op = _SQL_CMP[node.op]
            if node.left.type == "text":
                return f"({left} COLLATE NOCASE {op} {right})"
            return f"({left} {op} {right})"
        if isinstance(node, InList):
            operand = self._sql(node.operand, params)
            values = ", ".join(self._sql(v, params) for v in node.values)
            return f"({operand} COLLATE NOCASE {'NOT IN' if node.negated else 'IN'} ({values}))"
        if isinstance(node, BoolOp):
            if node.op not in ("AND", "OR"):
                raise ValueError(f"unknown operator {node.op!r}")
            return "(" + f" {node.op} ".join(self._sql(item, params) for item in node.items) + ")"
        if isinstance(node, Not):
            return f"(NOT {self._sql(node.operand, params)})"
        raise TypeError(f"cannot compile {type(node).__name__}")

    def _ratio(self, node: Ref, params: list) -> str:
        key = node.name.key
        if not self.expanding:
            self.outer = (node.start, node.end)  # errors inside a ratio point at its use in the query
        start, end = self.outer
        if key in self.expanding:
            chain = " → ".join([*self.expanding, key])
            raise QueryError(f"Custom ratios refer to each other in a circle ({chain}) {{at}}.", start, end, self.text)
        if len(self.expanding) >= MAX_RATIO_DEPTH:
            raise QueryError(f"Custom ratios nest more than {MAX_RATIO_DEPTH} deep {{at}}.", start, end, self.text)
        ast = self.ratios.get(key)
        if ast is None:
            raise QueryError(f"The custom ratio '{node.name.label}' {{at}} no longer exists or no longer parses.",
                             start, end, self.text)
        self.expanding.append(key)
        try:
            return f"({self._sql(ast, params)})"
        finally:
            self.expanding.pop()
