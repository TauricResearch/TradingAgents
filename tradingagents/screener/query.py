"""The screen query language: a hand-written tokenizer and recursive-descent parser.

Nothing here evaluates user text. A query becomes tokens, the tokens an AST of
the node classes below, and ``compiler`` turns the AST into SQL whose only
identifiers come from the metrics catalog and whose every literal is a bound
parameter.

Grammar, loosest binding first::

    query      := lines
    lines      := or_expr (NEWLINE or_expr)*      (a newline between conditions: AND, loosest)
    or_expr    := and_expr ("OR" and_expr)*
    and_expr   := not_expr ("AND" not_expr)*
    not_expr   := "NOT" not_expr | comparison
    comparison := sum (CMP sum | ["NOT"] "IN" "(" STRING ("," STRING)* ")")?
    sum        := term (("+" | "-") term)*
    term       := unary (("*" | "/") unary)*
    unary      := ("-" | "+") unary | primary
    primary    := NUMBER | STRING | METRIC | "(" lines ")"
    CMP        := ">" | "<" | ">=" | "<=" | "=" | "!="     ("==" and "<>" are accepted too)

Metric names may hold spaces and are matched case-insensitively against every
name and alias in the catalog (and the custom ratios), longest first, so
``Sales growth 3 years`` is one metric and not ``Sales`` followed by words.
Keywords are case-insensitive. Numbers may be grouped (``1,000`` or Indian
``1,00,000``), written with an exponent (``1e3``) and carry a ``%`` that is
ignored (``ROE > 20%``). Strings go in single or double quotes, a quote inside
doubled (``'O''Reilly'``).

A newline between two conditions is an AND: a line break where one condition
has ended (after a number, string, metric or ``)``) and another begins. It binds
looser than OR, so each line is a condition of its own: ``ROCE > 20`` then
``ROE > 15 OR P/E < 10`` on the next line means ROCE > 20 AND (ROE > 15 OR
P/E < 10). A line that starts with an operator, AND or OR continues the line
before.

Every error is a ``QueryError`` carrying the character span to highlight and a
message that says where, in line and column, and what to do about it.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_LENGTH = 4000  # characters in a query
MAX_DEPTH = 40  # nesting of the AST
MAX_NODES = 600
MAX_IN_VALUES = 100

KEYWORDS = ("AND", "OR", "NOT", "IN")
NUMBER_TYPE, TEXT_TYPE, BOOL_TYPE = "number", "text", "condition"


class QueryError(ValueError):
    """A query that cannot be used; ``start``/``end`` is the span to highlight."""

    def __init__(self, message: str, start: int, end: int, text: str = ""):
        self.raw, self.start, self.end = message, start, max(end, start)
        self.line, self.col = position(text, start)
        multiline = "\n" in text
        where = f"at line {self.line}, col {self.col}" if multiline else f"at col {self.col}"
        super().__init__(message.replace("{at}", where))

    def to_dict(self) -> dict:
        return {"message": str(self), "start": self.start, "end": self.end, "line": self.line, "col": self.col}


def position(text: str, offset: int) -> tuple[int, int]:
    """1-based (line, column) of a character offset."""
    before = text[:offset]
    line = before.count("\n") + 1
    return line, offset - (before.rfind("\n") + 1) + 1


# --- Names --------------------------------------------------------------------------------

def normalize(name: str) -> str:
    return " ".join(name.split()).casefold()


@dataclass(frozen=True)
class Name:
    """What a name in a query refers to."""

    kind: str  # "metric" | "ratio"
    key: str  # metric key, or the custom ratio's normalised name
    label: str  # the canonical display name
    type: str  # NUMBER_TYPE | TEXT_TYPE


class NameTable:
    """Every name a query may use, compiled into one longest-first pattern."""

    def __init__(self, entries: Iterable[tuple[str, Name]]):
        self.names: dict[str, Name] = {}
        self.spelled: dict[str, str] = {}  # normalised -> as written in the catalog
        for spelling, name in entries:
            key = normalize(spelling)
            if not key:
                continue
            self.names.setdefault(key, name)
            self.spelled.setdefault(key, " ".join(spelling.split()))
        patterns = []
        for key in sorted(self.spelled, key=len, reverse=True):
            words = self.spelled[key].split(" ")
            pattern = r"[ \t]+".join(re.escape(w) for w in words)
            if re.match(r"\w", words[-1][-1]):
                pattern += r"(?![A-Za-z0-9_])"
            patterns.append(pattern)
        self.pattern = re.compile("|".join(patterns), re.IGNORECASE) if patterns else None

    def match(self, text: str, pos: int) -> tuple[Name, int] | None:
        if self.pattern is None:
            return None
        m = self.pattern.match(text, pos)
        if not m:
            return None
        return self.names[normalize(m.group())], m.end()

    def suggest(self, text: str) -> str | None:
        """The closest name to a misspelt one, as the catalog writes it."""
        hits = difflib.get_close_matches(normalize(text), list(self.spelled), n=1, cutoff=0.6)
        return self.spelled[hits[0]] if hits else None


# --- Tokens -------------------------------------------------------------------------------

@dataclass
class Token:
    kind: str  # NUM STR NAME UNKNOWN OP CMP LPAREN RPAREN COMMA AND OR NOT IN EOF
    value: object
    start: int
    end: int
    newline: bool = False  # a line break between this token and the one before
    words: list[tuple[int, int]] = field(default_factory=list)  # UNKNOWN: each word's span


_NUMBER = re.compile(r"(?:\d{1,3}(?:,\d{2,3})*,\d{3}(?![\d,])|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?%?"
                     r"|\.\d+(?:[eE][+-]?\d+)?%?")
_WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.%&'-]*")
_CMP = (">=", "<=", "!=", "<>", "==", ">", "<", "=")
_QUOTES = {"'": "'", '"': '"', "‘": "’", "“": "”"}
_OPERAND_END = {"NUM", "STR", "NAME", "RPAREN", "UNKNOWN"}
_OPERAND_START = {"NUM", "STR", "NAME", "LPAREN", "NOT", "UNKNOWN"}


def _keyword(text: str, pos: int) -> str | None:
    m = re.match(r"(AND|OR|NOT|IN)(?![A-Za-z0-9_])", text[pos:pos + 4], re.IGNORECASE)
    if not m:
        return None
    word = m.group(1).upper()
    if word == "IN" and not re.match(r"[ \t]*\(", text[pos + 2:]):
        return None  # "in" inside a name ("Change in ..."), not the IN operator
    return word


def tokenize(text: str, names: NameTable) -> list[Token]:
    if len(text) > MAX_LENGTH:
        raise QueryError(f"The query is {len(text):,} characters long; the limit is {MAX_LENGTH:,}.",
                         MAX_LENGTH, len(text), text)
    tokens: list[Token] = []
    pos, newline, n = 0, False, len(text)
    while pos < n:
        ch = text[pos]
        if ch in " \t\r":
            pos += 1
            continue
        if ch == "\n":
            newline, pos = True, pos + 1
            continue
        start = pos
        keyword = _keyword(text, pos)
        hit = None if keyword else names.match(text, pos)
        if keyword:
            tokens.append(Token(keyword, keyword, start, start + len(keyword), newline))
            pos = start + len(keyword)
        elif hit:
            name, pos = hit
            tokens.append(Token("NAME", name, start, pos, newline))
        elif (m := _NUMBER.match(text, pos)) and not re.match(r"[A-Za-z_]", text[m.end():m.end() + 1]):
            raw = m.group().rstrip("%").replace(",", "")
            tokens.append(Token("NUM", float(raw), start, m.end(), newline))
            pos = m.end()
        elif ch in _QUOTES:
            pos = _string(text, pos, tokens, newline)
        elif text.startswith(_CMP, pos):
            op = next(o for o in _CMP if text.startswith(o, pos))
            pos += len(op)
            tokens.append(Token("CMP", {"<>": "!=", "==": "="}.get(op, op), start, pos, newline))
        elif ch in "+-*/":
            tokens.append(Token("OP", ch, start, start + 1, newline))
            pos += 1
        elif ch in "(),":
            tokens.append(Token({"(": "LPAREN", ")": "RPAREN", ",": "COMMA"}[ch], ch, start, start + 1, newline))
            pos += 1
        elif re.match(r"[A-Za-z0-9_]", ch):
            pos = _unknown(text, pos, tokens, newline)
        else:
            raise QueryError(f"Unexpected character '{ch}' {{at}}.", start, start + 1, text)
        newline = False
    tokens.append(Token("EOF", None, n, n, newline))
    return _implicit_and(tokens)


def _string(text: str, pos: int, tokens: list[Token], newline: bool) -> int:
    start, close = pos, _QUOTES[text[pos]]
    pos += 1
    parts = []
    while True:
        end = text.find(close, pos)
        if end == -1 or "\n" in text[pos:end]:
            stop = text.find("\n", pos)
            raise QueryError("This text is missing its closing quote {at}.", start,
                             len(text) if stop == -1 else stop, text)
        parts.append(text[pos:end])
        if text.startswith(close * 2, end) and close in "'\"":
            parts.append(close)
            pos = end + 2
            continue
        tokens.append(Token("STR", "".join(parts), start, end + 1, newline))
        return end + 1


def _unknown(text: str, pos: int, tokens: list[Token], newline: bool) -> int:
    """A run of words that names nothing: kept whole, so the error can show it all
    and suggest the name it was meant to be. A number just before it that the
    name would have started with (``52 wek high``) is folded in."""
    words = []
    while True:
        m = _WORD.match(text, pos)
        if not m or _keyword(text, pos):
            break
        words.append((pos, m.end()))
        pos = m.end()
        ahead = re.match(r"[ \t]+", text[pos:])
        nxt = pos + (ahead.end() if ahead else 0)
        if not ahead or nxt >= len(text) or not re.match(r"[A-Za-z0-9_]", text[nxt]) or _keyword(text, nxt):
            break
        pos = nxt
    start, end = words[0][0], words[-1][1]
    begins = len(tokens) <= 1 or tokens[-2].kind in ("AND", "OR", "NOT", "LPAREN")
    if tokens and tokens[-1].kind == "NUM" and not text[tokens[-1].end:start].strip(" \t") \
            and tokens[-1].end < start and (begins or tokens[-1].newline):
        number = tokens.pop()
        words.insert(0, (number.start, number.end))
        start, newline = number.start, number.newline
    tokens.append(Token("UNKNOWN", text[start:end], start, end, newline, words))
    return end


def _implicit_and(tokens: list[Token]) -> list[Token]:
    out: list[Token] = []
    for t in tokens:
        if t.newline and out and out[-1].kind in _OPERAND_END and t.kind in _OPERAND_START:
            out.append(Token("NLAND", "AND", t.start, t.start, True))
        out.append(t)
    return out


# --- The AST ------------------------------------------------------------------------------

@dataclass
class Node:
    start: int
    end: int
    type: str


@dataclass
class Num(Node):
    value: float


@dataclass
class Str(Node):
    value: str


@dataclass
class Ref(Node):
    name: Name


@dataclass
class Neg(Node):
    operand: Node


@dataclass
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass
class Compare(Node):
    op: str
    left: Node
    right: Node


@dataclass
class InList(Node):
    operand: Node
    values: list[Str]
    negated: bool


@dataclass
class BoolOp(Node):
    op: str  # "AND" | "OR"
    items: list[Node]


@dataclass
class Not(Node):
    operand: Node


def walk(node: Node):
    yield node
    for child in _children(node):
        yield from walk(child)


def _children(node: Node) -> list[Node]:
    if isinstance(node, (Neg, Not)):
        return [node.operand]
    if isinstance(node, (BinOp, Compare)):
        return [node.left, node.right]
    if isinstance(node, InList):
        return [node.operand, *node.values]
    if isinstance(node, BoolOp):
        return list(node.items)
    return []


def references(node: Node) -> list[Name]:
    """The names a query uses, in order of first appearance."""
    seen, out = set(), []
    for n in walk(node):
        if isinstance(n, Ref) and (n.name.kind, n.name.key) not in seen:
            seen.add((n.name.kind, n.name.key))
            out.append(n.name)
    return out


# --- The parser ---------------------------------------------------------------------------

_KEYWORD_SPELLINGS = {"AND": ("AN", "ADN", "NAD", "AMD", "&&", "&"), "OR": ("RO", "0R", "||")}


class Parser:
    def __init__(self, text: str, names: NameTable):
        self.text, self.names = text, names
        self.tokens = tokenize(text, names)
        self.i = 0
        self.depth = 0
        self.nodes = 0

    # Helpers -------------------------------------------------------------------------
    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def take(self) -> Token:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def error(self, message: str, start: int, end: int):
        raise QueryError(message, start, end, self.text)

    def snippet(self, t: Token) -> str:
        return "the end of the query" if t.kind == "EOF" else f"'{self.text[t.start:t.end]}'"

    def quote(self, node: Node) -> str:
        text = " ".join(self.text[node.start:node.end].split())
        return f"'{text if len(text) <= 40 else text[:37] + '...'}'"

    def node(self, cls, *args, **kwargs):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            self.error(f"The query is too complex (more than {MAX_NODES} parts); split it into simpler screens.",
                       0, len(self.text))
        return cls(*args, **kwargs)

    def nest(self, t: Token):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            self.error(f"The query nests too deeply (more than {MAX_DEPTH} levels) {{at}}.", t.start, t.end)

    def unknown(self, t: Token):
        guess = self.names.suggest(t.value)
        hint = f" — did you mean '{guess}'?" if guess else ". Open the metrics list to see every name."
        self.error(f"Unknown metric '{t.value}' {{at}}{hint}", t.start, t.end)

    # Grammar -------------------------------------------------------------------------
    def parse(self, want: str = BOOL_TYPE) -> Node:
        if self.tok.kind == "EOF":
            self.error("The query is empty. Write a condition such as: Return on capital employed > 20",
                       0, len(self.text))
        node = self.lines()
        if self.tok.kind != "EOF":
            self.unexpected(self.tok, after=node)
        if want == BOOL_TYPE and node.type != BOOL_TYPE:
            self.error(f"A screen needs a condition to test, such as ROCE > 20, but {self.quote(node)} {{at}} "
                       "is only a value.", node.start, node.end)
        if want == NUMBER_TYPE and node.type != NUMBER_TYPE:
            what = "a condition" if node.type == BOOL_TYPE else "text"
            self.error(f"A ratio must be a number worked out from metrics; this is {what} {{at}}.",
                       node.start, node.end)
        return node

    def unexpected(self, t: Token, after: Node | None = None):
        if t.kind == "UNKNOWN":
            first = self.text[t.words[0][0]:t.words[0][1]].upper()
            for keyword, spellings in _KEYWORD_SPELLINGS.items():
                if first in spellings:
                    s, e = t.words[0]
                    self.error(f"'{self.text[s:e]}' {{at}} is not a keyword — did you mean {keyword}?", s, e)
            if after is not None and after.type != BOOL_TYPE:
                self.error(f"Expected a comparison such as > or = before '{t.value}' {{at}}.", t.start, t.end)
            self.unknown(t)
        if t.kind == "RPAREN":
            self.error("This ')' {at} has no '(' to close.", t.start, t.end)
        if after is not None and after.type == BOOL_TYPE and t.kind in _OPERAND_START:
            self.error(f"Expected AND or OR before {self.snippet(t)} {{at}}.", t.start, t.end)
        if after is not None and t.kind in _OPERAND_START:
            self.error(f"Expected an operator or a comparison before {self.snippet(t)} {{at}}.", t.start, t.end)
        self.error(f"Unexpected {self.snippet(t)} {{at}}.", t.start, t.end)

    def lines(self) -> Node:
        return self._bool("NLAND", self.or_expr, "AND", "Each line")

    def or_expr(self) -> Node:
        return self._bool("OR", self.and_expr)

    def and_expr(self) -> Node:
        return self._bool("AND", self.not_expr)

    def _bool(self, kind: str, operand, op: str | None = None, who: str | None = None) -> Node:
        op = op or kind
        items = [operand()]
        while self.tok.kind == kind:
            t = self.take()
            if self.tok.kind == "EOF":
                self.error(f"{op} {{at}} needs a condition after it.", t.start, t.end)
            items.append(operand())
        if len(items) == 1:
            return items[0]
        for item in items:
            self._want_condition(item, who or op)
        return self.node(BoolOp, items[0].start, items[-1].end, BOOL_TYPE, op, items)

    def _want_condition(self, node: Node, who: str):
        if node.type != BOOL_TYPE:
            verb = "must be a condition" if who == "Each line" else "joins conditions"
            self.error(f"{who} {verb}, but {self.quote(node)} {{at}} is a value: compare it with "
                       "something first, e.g. '> 0'.", node.start, node.end)

    def not_expr(self) -> Node:
        if self.tok.kind == "NOT":
            t = self.take()
            self.nest(t)
            operand = self.not_expr()
            self.depth -= 1
            self._want_condition(operand, "NOT")
            return self.node(Not, t.start, operand.end, BOOL_TYPE, operand)
        return self.comparison()

    def comparison(self) -> Node:
        left = self.sum()
        t = self.tok
        if t.kind == "CMP":
            self.take()
            right = self.sum()
            for side in (left, right):
                if side.type == BOOL_TYPE:
                    self.error(f"{self.quote(side)} {{at}} is already a condition, so it cannot be compared "
                               "again. Compare one pair at a time and join them with AND.", side.start, side.end)
            if left.type != right.type:
                text_side = left if left.type == TEXT_TYPE else right
                self.error(f"Cannot compare text with a number {{at}}: {self.quote(text_side)} is text, compared "
                           "with = or != against a quoted value.", left.start, right.end)
            if left.type == TEXT_TYPE and t.value not in ("=", "!="):
                self.error(f"Text can only be compared with = or != (or IN), not '{t.value}' {{at}}.",
                           t.start, t.end)
            if self.tok.kind == "CMP":
                self.error("Compare one pair at a time {at}: write 'A < B AND B < C'.", self.tok.start, self.tok.end)
            return self.node(Compare, left.start, right.end, BOOL_TYPE, t.value, left, right)
        negated = False
        if t.kind == "NOT" and self.tokens[self.i + 1].kind == "IN":
            self.take()
            negated = True
        if self.tok.kind == "IN":
            return self.in_list(left, negated, t)
        if negated:
            self.error("NOT here must be followed by IN {at}.", t.start, t.end)
        return left

    def in_list(self, left: Node, negated: bool, first: Token) -> Node:
        keyword = self.take()
        if left.type != TEXT_TYPE:
            self.error("IN tests text such as Industry against a list of quoted values {at}.",
                       left.start, keyword.end)
        if self.tok.kind != "LPAREN":
            self.error("IN needs a list in brackets {at}, e.g. Industry IN ('Power', 'Utilities').",
                       self.tok.start, self.tok.end)
        self.take()
        values: list[Str] = []
        while True:
            t = self.tok
            if t.kind != "STR":
                self.error(f"Expected a quoted value in the IN list, found {self.snippet(t)} {{at}}.", t.start, t.end)
            self.take()
            values.append(self.node(Str, t.start, t.end, TEXT_TYPE, t.value))
            if len(values) > MAX_IN_VALUES:
                self.error(f"An IN list holds at most {MAX_IN_VALUES} values {{at}}.", t.start, t.end)
            if self.tok.kind == "COMMA":
                self.take()
                continue
            if self.tok.kind != "RPAREN":
                self.error(f"Expected ',' or ')' in the IN list, found {self.snippet(self.tok)} {{at}}.",
                           self.tok.start, self.tok.end)
            end = self.take().end
            break
        return self.node(InList, left.start, end, BOOL_TYPE, left, values, negated)

    def sum(self) -> Node:
        return self._arith(("+", "-"), self.term)

    def term(self) -> Node:
        return self._arith(("*", "/"), self.unary)

    def _arith(self, ops: tuple[str, ...], operand) -> Node:
        left = operand()
        while self.tok.kind == "OP" and self.tok.value in ops:
            t = self.take()
            right = operand()
            for side in (left, right):
                if side.type != NUMBER_TYPE:
                    what = "text" if side.type == TEXT_TYPE else "a condition"
                    self.error(f"'{t.value}' works on numbers, but {self.quote(side)} {{at}} is {what}.",
                               side.start, side.end)
            left = self.node(BinOp, left.start, right.end, NUMBER_TYPE, t.value, left, right)
        return left

    def unary(self) -> Node:
        if self.tok.kind == "OP" and self.tok.value in "+-":
            t = self.take()
            self.nest(t)
            operand = self.unary()
            self.depth -= 1
            if operand.type != NUMBER_TYPE:
                self.error(f"'{t.value}' works on numbers {{at}}.", t.start, operand.end)
            return operand if t.value == "+" else self.node(Neg, t.start, operand.end, NUMBER_TYPE, operand)
        return self.primary()

    def primary(self) -> Node:
        t = self.tok
        if t.kind == "NUM":
            self.take()
            return self.node(Num, t.start, t.end, NUMBER_TYPE, t.value)
        if t.kind == "STR":
            self.take()
            return self.node(Str, t.start, t.end, TEXT_TYPE, t.value)
        if t.kind == "NAME":
            self.take()
            return self.node(Ref, t.start, t.end, t.value.type, t.value)
        if t.kind == "LPAREN":
            self.take()
            self.nest(t)
            inner = self.lines()
            self.depth -= 1
            if self.tok.kind != "RPAREN":
                if self.tok.kind == "EOF":
                    self.error("This '(' {at} is never closed.", t.start, t.end)
                self.unexpected(self.tok, after=inner)
            close = self.take()
            inner.start, inner.end = t.start, close.end
            return inner
        if t.kind == "UNKNOWN":
            self.unknown(t)
        if t.kind == "EOF":
            prev = self.tokens[self.i - 1] if self.i else t
            self.error(f"The query ends too early: something must follow {self.snippet(prev)} {{at}}.",
                       prev.start, prev.end)
        if t.kind in ("AND", "OR"):
            self.error(f"{t.value} {{at}} needs a condition before it.", t.start, t.end)
        self.error(f"Expected a metric, number or quoted text, found {self.snippet(t)} {{at}}.", t.start, t.end)


def parse(text: str, names: NameTable, want: str = BOOL_TYPE) -> Node:
    """The AST of ``text``, or a ``QueryError``. ``want`` is BOOL_TYPE for a screen
    and NUMBER_TYPE for a custom ratio's expression."""
    return Parser(text, names).parse(want)
