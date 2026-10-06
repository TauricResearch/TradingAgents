"""Saved screens, custom ratios and the preset screens.

Both are the user's own data, so they live in the user database
(``userdb``: ``screener_db_path``, default ``~/.tradingagents/screener/screens.db``)
with the watchlists and alerts, and survive the India database being rebuilt.

A custom ratio is ``Name = expression`` over catalog metrics and other custom
ratios: ``Earnings to price = Net profit / Market Capitalization``. Its name then
works in queries like any metric's. It is checked with the query parser when
saved: the name must not be a catalog name or alias (or another ratio's), the
expression must be a number, and ratios may refer to each other but never in a
circle, nor more than ``compiler.MAX_RATIO_DEPTH`` deep. Ratios are compiled
inline into each screen's SQL, never stored as values.

Presets are written in code, read-only: duplicate one to edit it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from tradingagents.screener import catalog, userdb
from tradingagents.screener.compiler import MAX_RATIO_DEPTH
from tradingagents.screener.query import (
    NUMBER_TYPE,
    TEXT_TYPE,
    Name,
    NameTable,
    Node,
    QueryError,
    normalize,
    parse,
    references,
)

MAX_NAME = 60
MAX_SCREENS = 500
MAX_RATIOS = 200
_RATIO_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 _]*$")
RATIO_PREFIX = "ratio:"


class ScreenError(ValueError):
    """A screen or ratio that cannot be saved as it stands; the message says why."""

    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class Ratio:
    id: int
    name: str
    key: str
    expression: str
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "column": RATIO_PREFIX + self.key, "expression": self.expression,
                "description": self.description, "createdAt": self.created_at, "updatedAt": self.updated_at}


db_path = userdb.db_path
connect = userdb.connect  # the user database, its schema brought up to date


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- Names ------------------------------------------------------------------------------

def _catalog_entries() -> list[tuple[str, Name]]:
    out = []
    for m in catalog.METRICS.values():
        name = Name("metric", m.key, m.name, TEXT_TYPE if m.kind == catalog.TEXT else NUMBER_TYPE)
        out += [(spelling, name) for spelling in (m.name, *m.aliases)]
    return out


_CATALOG_ENTRIES = _catalog_entries()


def ratio_name(r: Ratio) -> Name:
    return Name("ratio", r.key, r.name, NUMBER_TYPE)


def name_table(ratios: list[Ratio]) -> NameTable:
    """Every name a query may use: the catalog's, then the custom ratios'."""
    return NameTable(_CATALOG_ENTRIES + [(r.name, ratio_name(r)) for r in ratios])


def parse_ratios(ratios: list[Ratio], names: NameTable) -> dict[str, Node]:
    """Each ratio's expression parsed; one that no longer parses is left out, so a
    screen using it says so instead of running without it."""
    out = {}
    for r in ratios:
        try:
            out[r.key] = parse(r.expression, names, NUMBER_TYPE)
        except QueryError:
            continue
    return out


# --- Custom ratios ------------------------------------------------------------------------

def list_ratios(conn) -> list[Ratio]:
    return [Ratio(**dict(r)) for r in conn.execute("SELECT * FROM custom_ratios ORDER BY name COLLATE NOCASE")]


def parse_definition(text: str) -> tuple[str, str]:
    """``Name = expression`` split in two."""
    name, eq, expression = (text or "").partition("=")
    if not eq or not name.strip() or not expression.strip():
        raise ScreenError("Write a ratio as Name = expression, e.g. Earnings to price = Net profit / Market "
                          "Capitalization")
    return name.strip(), expression.strip()


def _check_name(name: str, ratios: list[Ratio], editing: int | None) -> str:
    name = " ".join(name.split())
    if not name:
        raise ScreenError("Give the ratio a name.")
    if len(name) > MAX_NAME:
        raise ScreenError(f"Ratio names are at most {MAX_NAME} characters.")
    if not _RATIO_NAME.match(name):
        raise ScreenError("Ratio names use letters, digits, spaces and underscores, starting with a letter.")
    words = {w.upper() for w in name.split()}
    if words & {"AND", "OR", "NOT", "IN"}:
        raise ScreenError("A ratio's name cannot contain the words AND, OR, NOT or IN.")
    key = normalize(name)
    clash = catalog.lookup(name)
    if clash:
        same = "its name" if normalize(clash.name) == key else f"an alias of '{clash.name}'"
        raise ScreenError(f"'{name}' is already a catalog metric ({same}); choose another name.")
    for r in ratios:
        if r.key == key and r.id != editing:
            raise ScreenError(f"There is already a custom ratio called '{r.name}'.")
    return name


def _cycle(graph: dict[str, set[str]], start: str) -> list[str] | None:
    """A path from ``start`` back to itself through ``graph``, if there is one."""
    stack = [(start, [start])]
    seen = set()
    while stack:
        node, path = stack.pop()
        for nxt in graph.get(node, ()):
            if nxt == start:
                return [*path, start]
            if nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, [*path, nxt]))
    return None


def _depth(graph: dict[str, set[str]], key: str, trail=()) -> int:
    if key in trail:
        return 0
    return 1 + max((_depth(graph, k, (*trail, key)) for k in graph.get(key, ())), default=0)


def validate_ratio(conn, name: str, expression: str, editing: int | None = None) -> tuple[str, str]:
    """The cleaned (name, expression), or a ScreenError (with the parser's span for
    an expression error)."""
    ratios = [r for r in list_ratios(conn) if r.id != editing]
    name = _check_name(name, ratios, editing)
    key = normalize(name)
    mine = Ratio(editing or 0, name, key, expression)
    names = name_table([*ratios, mine])
    try:
        ast = parse(expression, names, NUMBER_TYPE)
    except QueryError as exc:
        raise ScreenError(str(exc), [exc.to_dict()]) from None
    graph = {k: {n.key for n in references(a) if n.kind == "ratio"} for k, a in parse_ratios(ratios, names).items()}
    graph[key] = {n.key for n in references(ast) if n.kind == "ratio"}
    labels = {r.key: r.name for r in [*ratios, mine]}
    if (path := _cycle(graph, key)) is not None:
        chain = " → ".join(labels.get(k, k) for k in path)
        raise ScreenError(f"Custom ratios cannot refer to each other in a circle: {chain}.")
    affected = [key] + [k for k in graph if key in _reach(graph, k)]
    if max(_depth(graph, k) for k in affected) > MAX_RATIO_DEPTH:
        raise ScreenError(f"Custom ratios can nest at most {MAX_RATIO_DEPTH} deep.")
    return name, expression.strip()


def _reach(graph: dict[str, set[str]], key: str) -> set[str]:
    out, todo = set(), [key]
    while todo:
        for nxt in graph.get(todo.pop(), ()):
            if nxt not in out:
                out.add(nxt)
                todo.append(nxt)
    return out


def save_ratio(conn, body: dict) -> Ratio:
    """Create a ratio, or update the one ``body['id']`` names."""
    editing = int(body["id"]) if body.get("id") not in (None, "") else None
    if body.get("definition"):
        name, expression = parse_definition(str(body["definition"]))
    else:
        name, expression = str(body.get("name") or ""), str(body.get("expression") or "")
    if not expression.strip():
        raise ScreenError("Give the ratio an expression, e.g. Net profit / Market Capitalization.")
    description = str(body.get("description") or "").strip()[:500]
    existing = list_ratios(conn)
    if editing is not None and not any(r.id == editing for r in existing):
        raise ScreenError("No such custom ratio.")
    if editing is None and len(existing) >= MAX_RATIOS:
        raise ScreenError(f"At most {MAX_RATIOS} custom ratios.")
    name, expression = validate_ratio(conn, name, expression, editing)
    now = _now()
    with conn:
        if editing is None:
            cur = conn.execute("INSERT INTO custom_ratios (name, key, expression, description, created_at, updated_at) "
                               "VALUES (?,?,?,?,?,?)", (name, normalize(name), expression, description, now, now))
            editing = cur.lastrowid
        else:
            conn.execute("UPDATE custom_ratios SET name=?, key=?, expression=?, description=?, updated_at=? WHERE id=?",
                         (name, normalize(name), expression, description, now, editing))
    return next(r for r in list_ratios(conn) if r.id == editing)


def delete_ratio(conn, ratio_id: int) -> None:
    ratios = list_ratios(conn)
    target = next((r for r in ratios if r.id == ratio_id), None)
    if target is None:
        raise ScreenError("No such custom ratio.")
    asts = parse_ratios(ratios, name_table(ratios))
    users = [r.name for r in ratios if r.id != ratio_id and r.key in asts
             and any(n.kind == "ratio" and n.key == target.key for n in references(asts[r.key]))]
    if users:
        raise ScreenError(f"'{target.name}' is used by the custom ratio{'s' * (len(users) > 1)} "
                          f"{', '.join(users)}; change or delete those first.")
    with conn:
        conn.execute("DELETE FROM custom_ratios WHERE id=?", (ratio_id,))


# --- Saved screens ------------------------------------------------------------------------

def _screen(row) -> dict:
    return {"id": row["id"], "name": row["name"], "description": row["description"], "query": row["query"],
            "columns": json.loads(row["columns"] or "[]"), "sort": json.loads(row["sort"]) if row["sort"] else None,
            "createdAt": row["created_at"], "updatedAt": row["updated_at"], "preset": False}


def list_screens(conn) -> list[dict]:
    return [_screen(r) for r in conn.execute("SELECT * FROM screens ORDER BY updated_at DESC, id DESC")]


def get_screen(conn, screen_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM screens WHERE id=?", (screen_id,)).fetchone()
    return _screen(row) if row else None


def known_columns(ratios: list[Ratio]) -> set[str]:
    return set(catalog.METRICS) | {RATIO_PREFIX + r.key for r in ratios}


def clean_columns(columns, ratios: list[Ratio]) -> list[str]:
    if columns in (None, ""):
        return []
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise ScreenError("columns must be a list of column ids.")
    known = known_columns(ratios)
    unknown = [c for c in columns if c not in known]
    if unknown:
        raise ScreenError(f"Unknown column{'s' * (len(unknown) > 1)}: {', '.join(unknown[:5])}.")
    return list(dict.fromkeys(columns))[:40]


def clean_sort(sort, ratios: list[Ratio]) -> dict | None:
    if sort in (None, "", {}):
        return None
    if not isinstance(sort, dict) or sort.get("key") not in known_columns(ratios) \
            or sort.get("dir", "desc") not in ("asc", "desc"):
        raise ScreenError('sort is {"key": a column id, "dir": "asc" or "desc"}.')
    return {"key": sort["key"], "dir": sort.get("dir", "desc")}


def save_screen(conn, body: dict, ratios: list[Ratio]) -> dict:
    """Create a screen, or update the one ``body['id']`` names. The query must parse."""
    editing = body.get("id")
    if isinstance(editing, str) and editing.startswith("preset:"):
        raise ScreenError("Presets are read-only: duplicate it and edit the copy.")
    editing = int(editing) if editing not in (None, "") else None
    name = " ".join(str(body.get("name") or "").split())
    if not name:
        raise ScreenError("Give the screen a name.")
    if len(name) > 80:
        raise ScreenError("Screen names are at most 80 characters.")
    query = str(body.get("query") or "")
    try:
        parse(query, name_table(ratios))
    except QueryError as exc:
        raise ScreenError(str(exc), [exc.to_dict()]) from None
    columns = json.dumps(clean_columns(body.get("columns"), ratios))
    sort = clean_sort(body.get("sort"), ratios)
    description = str(body.get("description") or "").strip()[:1000]
    now = _now()
    with conn:
        if editing is None:
            if conn.execute("SELECT COUNT(*) FROM screens").fetchone()[0] >= MAX_SCREENS:
                raise ScreenError(f"At most {MAX_SCREENS} saved screens.")
            cur = conn.execute("INSERT INTO screens (name, description, query, columns, sort, created_at, updated_at) "
                               "VALUES (?,?,?,?,?,?,?)",
                               (name, description, query, columns, json.dumps(sort) if sort else None, now, now))
            editing = cur.lastrowid
        else:
            done = conn.execute("UPDATE screens SET name=?, description=?, query=?, columns=?, sort=?, updated_at=? "
                                "WHERE id=?", (name, description, query, columns,
                                               json.dumps(sort) if sort else None, now, editing))
            if done.rowcount == 0:
                raise ScreenError("No such screen.")
    return get_screen(conn, editing)


def delete_screen(conn, screen_id) -> None:
    if isinstance(screen_id, str) and screen_id.startswith("preset:"):
        raise ScreenError("Presets are read-only and cannot be deleted.")
    with conn:
        if conn.execute("DELETE FROM screens WHERE id=?", (int(screen_id),)).rowcount == 0:
            raise ScreenError("No such screen.")


# --- Presets --------------------------------------------------------------------------------
# Written for this project. Each is a starting point to duplicate and adjust, not advice.

PRESETS = (
    ("debt-free-compounders", "Debt-free compounders",
     "Little or no borrowing, with sales and profit compounding at double digits for five years "
     "and a healthy return on equity.",
     "Debt to equity < 0.1\nSales growth 5 years > 12\nProfit growth 5 years > 12\nReturn on equity > 15",
     ["market_cap"], {"key": "profit_growth_5y", "dir": "desc"}),
    ("high-roce-fair-pe", "High ROCE at a reasonable P/E",
     "Businesses earning over 20% on the capital they employ, priced at under 25 times earnings, "
     "large enough to trade easily.",
     "Return on capital employed > 20\nPrice to earnings < 25\nMarket Capitalization > 1000",
     [], {"key": "roce", "dir": "desc"}),
    ("consistent-growers", "Consistent five-year growers",
     "Sales and profit up more than 10% a year over both three and five years, with a five-year "
     "average ROE above 12%: growth that has lasted, not one good year.",
     "Sales growth 5 years > 10 AND Sales growth 3 years > 10\n"
     "Profit growth 5 years > 10 AND Profit growth 3 years > 10\nAverage ROE 5 years > 12",
     [], {"key": "sales_growth_5y", "dir": "desc"}),
    ("piotroski-strong", "Piotroski 8 or 9",
     "Companies passing at least eight of Piotroski's nine accounting tests on their latest year.",
     "Piotroski score >= 8", ["roe", "debt_to_equity", "pe"], {"key": "piotroski", "dir": "desc"}),
    ("promoters-buying", "Promoters raising their stake",
     "Promoter holding up over the last quarter and by more than a percentage point over the year, "
     "with little of it pledged.",
     "Change in promoter holding > 0\nChange in promoter holding 1 year > 1\nPledged percentage < 5",
     ["promoter_holding"], {"key": "promoter_change_1y", "dir": "desc"}),
    ("low-pb-positive-fcf", "Low price to book, positive free cash flow",
     "Trading near book value while generating free cash over the last three years, without heavy debt.",
     "Price to book value < 1.5\nFree cash flow 3 years > 0\nDebt to equity < 1",
     ["market_cap"], {"key": "pb", "dir": "asc"}),
    ("near-high-growing", "Near the 52-week high, still growing",
     "Within 10% of the year's high, with sales and profit both up more than 15% on the same "
     "quarter last year.",
     "Down from 52 week high < 10\nYoY quarterly sales growth > 15\nYoY quarterly profit growth > 15",
     ["return_1y"], {"key": "from_52w_high", "dir": "asc"}),
    ("dividend-low-payout", "Dividend yield with low payout risk",
     "A dividend yield above 3% that takes under 60% of earnings, from a company with positive free "
     "cash flow last year.",
     "Dividend yield > 3\nDividend payout ratio < 60\nFree cash flow last year > 0",
     ["market_cap"], {"key": "dividend_yield", "dir": "desc"}),
    ("uptrend-large", "Large caps in an uptrend",
     "Above both their 50- and 200-day moving averages and up more than 15% in six months; works "
     "on prices alone, so it runs before any filings are imported.",
     "Market Capitalization > 5000\nPrice vs 50 DMA > 0\nPrice vs 200 DMA > 0\nReturn over 6 months > 15",
     ["return_1y", "rsi"], {"key": "return_6m", "dir": "desc"}),
)


def presets() -> list[dict]:
    return [{"id": f"preset:{slug}", "name": name, "description": text, "query": query, "columns": columns,
             "sort": sort, "preset": True} for slug, name, text, query, columns, sort in PRESETS]


def get_preset(screen_id: str) -> dict | None:
    return next((p for p in presets() if p["id"] == screen_id), None)
