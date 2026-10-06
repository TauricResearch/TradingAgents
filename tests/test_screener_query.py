"""The screen query language: tokenizer, parser, compiler, and why user text can
never become SQL. No database is needed for most of these."""

from __future__ import annotations

import re
import sqlite3

import pytest

from tradingagents.screener import catalog, compiler, query as q, screens
from tradingagents.screener.compiler import Compiler

pytestmark = pytest.mark.unit
NAMES = screens.name_table([])


def parse(text, want=q.BOOL_TYPE):
    return q.parse(text, NAMES, want)


def sql(text) -> compiler.Compiled:
    return Compiler({}, text).compile(parse(text))


def error(text) -> q.QueryError:
    with pytest.raises(q.QueryError) as info:
        parse(text)
    return info.value


def shape(node) -> str:
    """The AST as a compact s-expression, for precedence checks."""
    if isinstance(node, q.Num):
        return f"{node.value:g}"
    if isinstance(node, q.Str):
        return repr(node.value)
    if isinstance(node, q.Ref):
        return node.name.key
    if isinstance(node, q.Neg):
        return f"(- {shape(node.operand)})"
    if isinstance(node, (q.BinOp, q.Compare)):
        return f"({node.op} {shape(node.left)} {shape(node.right)})"
    if isinstance(node, q.InList):
        return f"({'NOT IN' if node.negated else 'IN'} {shape(node.operand)} {[v.value for v in node.values]})"
    if isinstance(node, q.BoolOp):
        return f"({node.op} {' '.join(shape(i) for i in node.items)})"
    if isinstance(node, q.Not):
        return f"(NOT {shape(node.operand)})"
    raise TypeError(node)


# --- Precedence and parentheses -------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("ROCE > 1 + 2 * 3", "(> roce (+ 1 (* 2 3)))"),
    ("ROCE > (1 + 2) * 3", "(> roce (* (+ 1 2) 3))"),
    ("ROCE > 10 - 2 - 3", "(> roce (- (- 10 2) 3))"),
    ("ROCE > 12 / 2 / 3", "(> roce (/ (/ 12 2) 3))"),
    ("ROCE > -5", "(> roce (- 5))"),
    ("ROCE > 1 OR ROE > 2 AND P/E < 3", "(OR (> roce 1) (AND (> roe 2) (< pe 3)))"),
    ("(ROCE > 1 OR ROE > 2) AND P/E < 3", "(AND (OR (> roce 1) (> roe 2)) (< pe 3))"),
    ("NOT ROCE > 1 AND ROE > 2", "(AND (NOT (> roce 1)) (> roe 2))"),
    ("NOT (ROCE > 1 AND ROE > 2)", "(NOT (AND (> roce 1) (> roe 2)))"),
    ("roce >= 1 and roe <= 2 or pe != 3", "(OR (AND (>= roce 1) (<= roe 2)) (!= pe 3))"),
    ("ROCE <> 1 AND ROE == 2", "(AND (!= roce 1) (= roe 2))"),
    ("Net profit / Sales * 100 > 10", "(> (* (/ net_profit sales) 100) 10)"),
])
def test_precedence_and_parentheses(text, expected):
    assert shape(parse(text)) == expected


@pytest.mark.parametrize("text, value", [("1,000", 1000), ("1,00,000", 100000), ("1e3", 1000), ("2.5E-1", 0.25),
                                         ("12.75", 12.75), (".5", 0.5), ("20%", 20), ("1,234.5", 1234.5)])
def test_numbers(text, value):
    node = parse(f"ROCE > {text}")
    assert node.right.value == pytest.approx(value)


# --- Names ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text, key", [
    ("Market Capitalization > 500", "market_cap"),
    ("market   capitalization > 500", "market_cap"),
    ("Return on capital employed > 20", "roce"),
    ("ROCE % > 20", "roce"),
    ("P/E < 20", "pe"),
    ("EV/EBITDA < 8", "ev_ebitda"),
    ("RSI(14) < 30", "rsi"),
    ("52 week high > 100", "high_52w"),
    ("50 DMA > 100", "dma_50"),
    ("Sales growth 3 years > 10", "sales_growth_3y"),
    ("Sales growth 3Y > 10", "sales_growth_3y"),
    ("Change in promoter holding > 0", "promoter_change_1q"),
    ("Change in promoter holding 1 year > 0", "promoter_change_1y"),
    ("Pledged % < 5", "pledged"),
    ("No. of shareholders > 5", "num_shareholders"),
    ("F-score >= 8", "piotroski"),
])
def test_multi_word_and_alias_names(text, key):
    assert parse(text).left.name.key == key


def test_the_longest_name_wins():
    assert shape(parse("Current price > 200 DMA")) == "(> current_price dma_200)"
    assert shape(parse("Price to book value < 1")) == "(< pb 1)"
    assert shape(parse("Price > 1")) == "(> current_price 1)"
    assert shape(parse("Sales > Sales last year")) == "(> sales sales_ly)"


def test_newlines_between_conditions_mean_and_and_bind_loosest():
    assert shape(parse("ROCE > 20\nROE > 15")) == "(AND (> roce 20) (> roe 15))"
    assert shape(parse("ROCE > 20\nROE > 15 OR P/E < 10")) == "(AND (> roce 20) (OR (> roe 15) (< pe 10)))"
    assert shape(parse("ROCE > 20 AND\nROE > 15")) == "(AND (> roce 20) (> roe 15))"
    assert shape(parse("ROCE > 20\n  OR ROE > 15")) == "(OR (> roce 20) (> roe 15))"
    assert shape(parse("Sales\n  / Debt > 2")) == "(> (/ sales debt) 2)"
    assert shape(parse("ROCE >\n20")) == "(> roce 20)"
    assert shape(parse("(ROCE > 1\nROE > 2)\nNOT P/E > 3")) == "(AND (AND (> roce 1) (> roe 2)) (NOT (> pe 3)))"
    assert shape(parse("\n\nROCE > 1\n\n")) == "(> roce 1)"


def test_in_lists_and_string_literals():
    assert shape(parse("Industry IN ('Banks', 'Finance')")) == "(IN industry ['Banks', 'Finance'])"
    assert shape(parse('Industry NOT IN ("Power")')) == "(NOT IN industry ['Power'])"
    assert shape(parse("Name = 'O''Reilly Ltd'")) == "(= name \"O'Reilly Ltd\")"
    assert shape(parse("Sector = 'Power'")) == "(= industry 'Power')"
    assert shape(parse("NSE symbol != ‘TCS’")) == "(!= nse_symbol 'TCS')"


# --- Errors ---------------------------------------------------------------------------------

def test_an_unknown_metric_says_where_and_suggests_one():
    e = error("Retrun on equity > 15")
    assert str(e) == "Unknown metric 'Retrun on equity' at col 1 — did you mean 'Return on equity'?"
    assert (e.start, e.end, e.line, e.col) == (0, 16, 1, 1)


@pytest.mark.parametrize("text, message, span", [
    ("ROCE > 20 AND Retrun on equity > 15", "Unknown metric 'Retrun on equity' at col 15", (14, 30)),
    ("ROCE > 20\nMarket capitalisaton > 5", "at line 2, col 1 — did you mean 'Market Capitalization'?", (10, 30)),
    ("52 wek high > 5", "did you mean '52 week high'?", (0, 11)),
    ("Market cap > 500 ROCE > 20", "Expected AND or OR before 'ROCE' at col 18", (17, 21)),
    ("ROCE > 20 AN ROE > 5", "'AN' at col 11 is not a keyword — did you mean AND?", (10, 12)),
    ("Market Capitalization crore > 500", "Expected a comparison such as > or = before 'crore'", (22, 27)),
    ("ROCE", "is only a value", (0, 4)),
    ("10 < PE < 20", "Compare one pair at a time", (8, 9)),
    ("Industry > 'A'", "Text can only be compared with = or !=", (9, 10)),
    ("Industry = 5", "Cannot compare text with a number", (0, 12)),
    ("Industry + 5 > 3", "'+' works on numbers, but 'Industry' at col 1 is text", (0, 8)),
    ("ROCE IN ('a')", "IN tests text", (0, 7)),
    ("Industry IN ('a' 'b')", "Expected ',' or ')'", (17, 20)),
    ("Industry IN (5)", "Expected a quoted value", (13, 14)),
    ("'abc", "missing its closing quote", (0, 4)),
    ("ROCE > (5", "is never closed", (7, 8)),
    ("ROCE > 5)", "has no '(' to close", (8, 9)),
    ("ROCE > 5 AND", "AND at col 10 needs a condition after it", (9, 12)),
    ("AND ROCE > 5", "AND at col 1 needs a condition before it", (0, 3)),
    ("ROCE >", "ends too early", (5, 6)),
    ("ROCE AND ROE > 5", "AND joins conditions, but 'ROCE' at col 1 is a value", (0, 4)),
    ("ROCE\nROE > 5", "Each line must be a condition, but 'ROCE' at line 1, col 1 is a value", (0, 4)),
    ("ROCE > 5; DROP TABLE x", "Unexpected character ';' at col 9", (8, 9)),
    ("", "The query is empty", (0, 0)),
])
def test_errors_have_messages_and_spans(text, message, span):
    e = error(text)
    assert message in str(e), str(e)
    assert (e.start, e.end) == span


def test_errors_serialise_for_the_api():
    d = error("ROCE > 20\nRetrun on equity > 1").to_dict()
    assert d == {"message": d["message"], "start": 10, "end": 26, "line": 2, "col": 1}


# --- Security -------------------------------------------------------------------------------

_SAFE_SQL = re.compile(r'\s+|"[a-z][a-z0-9_]*"|\?|NULLIF|COLLATE|NOCASE|NOT IN|IN|AND|OR|NOT|<>|<=|>=|[()<>=+\-*/,]|0')


def assert_parameterised(compiled: compiler.Compiled):
    """The SQL holds only catalog columns, placeholders, operators and keywords."""
    leftover = _SAFE_SQL.sub("", compiled.sql)
    assert leftover == "", leftover
    for column in re.findall(r'"([^"]*)"', compiled.sql):
        assert column in catalog.METRICS


@pytest.mark.parametrize("text", [
    "Market Capitalization > 500 AND Return on capital employed > 20 AND Debt to equity < 0.5",
    "Name = 'x''; DROP TABLE metrics_snapshot; --'",
    "Name = \"Robert'); DELETE FROM screens; --\"",
    "Industry IN ('a\" OR 1=1 --', 'b')",
    "NOT (ROCE > 1 OR (Sales / Debt) * -2 >= 1e3) AND Industry != 'x'",
    "1 = 1",
])
def test_every_compiled_query_uses_bound_parameters_only(text):
    compiled = sql(text)
    assert_parameterised(compiled)
    literals = [n for n in q.walk(parse(text)) if isinstance(n, (q.Num, q.Str))]
    assert len(compiled.params) == len(literals)


def test_injected_text_is_only_ever_a_value(tmp_path):
    from tradingagents.screener import snapshot

    conn = sqlite3.connect(tmp_path / "s.db")
    snapshot.ensure_schema(conn)
    conn.execute("INSERT INTO metrics_snapshot (as_of_date, isin, built_at, name) VALUES ('live', 'IN1', 'now', 'A')")
    attack = "Name = 'A'' OR 1=1; DROP TABLE metrics_snapshot; --'"
    compiled = sql(attack)
    assert compiled.params == ["A' OR 1=1; DROP TABLE metrics_snapshot; --"]
    count = conn.execute(f"SELECT COUNT(*) FROM metrics_snapshot WHERE {compiled.sql}", compiled.params).fetchone()
    assert count == (0,)
    assert conn.execute("SELECT COUNT(*) FROM metrics_snapshot").fetchone() == (1,)


@pytest.mark.parametrize("text", ['"roce" > 1', "[roce] > 1", "`roce` > 1", "roce; > 1", "sqlite_master > 1",
                                  "isin = 'x'", "as_of_date = 'live'", "built_at > 1", "financial = 1"])
def test_identifiers_outside_the_catalog_are_refused(text):
    with pytest.raises(q.QueryError):
        parse(text)


def test_the_compiler_refuses_a_column_the_catalog_does_not_have():
    for bad in ("sqlite_master", 'roce" OR 1 --', "isin", "", "ROCE"):
        with pytest.raises(ValueError):
            compiler.column(bad)
    forged = q.Ref(0, 4, q.NUMBER_TYPE, q.Name("metric", 'x" OR 1=1 --', "x", q.NUMBER_TYPE))
    with pytest.raises(ValueError):
        Compiler().compile(forged)


def test_division_by_zero_is_null():
    compiled = sql("Sales / Debt > 1")
    assert "NULLIF" in compiled.sql
    conn = sqlite3.connect(":memory:")
    conn.execute('CREATE TABLE t ("sales" REAL, "debt" REAL)')
    conn.execute("INSERT INTO t VALUES (10, 0)")
    assert conn.execute(f"SELECT ({compiled.sql}) FROM t", compiled.params).fetchone() == (None,)


def test_limits_on_length_depth_and_size():
    assert "characters long" in str(error("ROCE > 1 AND " * 400))
    assert "nests too deeply" in str(error("(" * 50 + "ROCE > 1" + ")" * 50))
    assert "nests too deeply" in str(error("NOT " * 50 + "ROCE > 1"))
    assert "too complex" in str(error(" + ".join(["1"] * 700) + " > 1"))
    assert "at most 100 values" in str(error("Industry IN (" + ", ".join(["'x'"] * 101) + ")"))
    parse("(" * 30 + "ROCE > 1" + ")" * 30)  # deep, but within the limit


# --- Custom ratios in the compiler ------------------------------------------------------------

def test_custom_ratios_compile_inline():
    ratios = [screens.Ratio(1, "Earnings to price", "earnings to price", "Net profit / Market Capitalization"),
              screens.Ratio(2, "EP twice", "ep twice", "Earnings to price * 2")]
    names = screens.name_table(ratios)
    asts = screens.parse_ratios(ratios, names)
    node = q.parse("EP twice > 0.1 AND ROCE > 5", names)
    compiled = Compiler(asts, "").compile(node)
    # AND( Compare( EP twice( * ( Earnings to price( / ))))): each ratio inlined in its own brackets.
    assert compiled.sql == '(((((("net_profit" / NULLIF("market_cap", 0))) * ?)) > ?) AND ("roce" > ?))'
    assert compiled.params == [2.0, 0.1, 5.0]
    assert_parameterised(compiled)


def test_a_ratio_that_no_longer_parses_is_reported_where_it_is_used():
    ratios = [screens.Ratio(1, "Broken", "broken", "Gone metric * 2")]
    names = screens.name_table(ratios)
    node = q.parse("ROCE > 1 AND Broken > 1", names)
    with pytest.raises(q.QueryError, match="'Broken' at col 14 no longer exists") as e:
        Compiler(screens.parse_ratios(ratios, names), "ROCE > 1 AND Broken > 1").compile(node)
    assert (e.value.start, e.value.end) == (13, 19)
