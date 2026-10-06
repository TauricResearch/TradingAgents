"""Saved screens, custom ratios and presets: the user's own SQLite store."""

from __future__ import annotations

import pytest

from tests import screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import compiler, engine, query as q, screens, snapshot

pytestmark = pytest.mark.unit


@pytest.fixture
def user(tmp_path):
    conn = screens.connect(tmp_path / "screens.db")
    yield conn
    conn.close()


def add(user, definition, **extra):
    return screens.save_ratio(user, {"definition": definition, **extra})


# --- Custom ratios ---------------------------------------------------------------------------

def test_a_ratio_is_saved_and_usable_in_a_query(user):
    r = add(user, "Earnings to price = Net profit / Market Capitalization")
    assert (r.name, r.key, r.expression) == ("Earnings to price", "earnings to price",
                                            "Net profit / Market Capitalization")
    assert r.describe()["column"] == "ratio:earnings to price"
    assert engine.validate("earnings TO price > 0.05 AND ROCE > 10", user)["ok"]
    with pytest.raises(screens.ScreenError, match="already a custom ratio"):
        add(user, "EARNINGS to  price = ROE")


@pytest.mark.parametrize("definition, message", [
    ("ROCE = Net profit / Sales", "already a catalog metric (an alias of 'Return on capital employed')"),
    ("Return on equity = Net profit / Sales", "already a catalog metric (its name)"),
    ("market cap = Sales * 2", "an alias of 'Market Capitalization'"),
    ("Sector = Sales", "an alias of 'Industry'"),
    ("Cash and debt = Cash + Debt", "cannot contain the words AND"),
    ("1st ratio = Sales", "starting with a letter"),
    ("Bad/name = Sales", "letters, digits, spaces and underscores"),
    ("No equals sign", "Write a ratio as Name = expression"),
    ("Text ratio = Industry", "this is text"),
    ("Cond ratio = ROCE > 5", "this is a condition"),
    ("Typo ratio = Net proft / Sales", "Unknown metric 'Net proft' at col 1 — did you mean 'Net profit'?"),
])
def test_ratios_that_cannot_be_saved(user, definition, message):
    with pytest.raises(screens.ScreenError, match=None) as info:
        add(user, definition)
    assert message in str(info.value)


def test_an_expression_error_carries_its_span(user):
    with pytest.raises(screens.ScreenError) as info:
        add(user, "Bad = Sales / Retrun on equity")
    [err] = info.value.errors
    assert (err["start"], err["end"]) == (8, 24)


def test_ratios_cannot_refer_to_each_other_in_a_circle(user):
    a = add(user, "Alpha = ROCE * 2")
    add(user, "Beta = Alpha + 1")
    with pytest.raises(screens.ScreenError, match="in a circle: Alpha → Beta → Alpha"):
        screens.save_ratio(user, {"id": a.id, "definition": "Alpha = Beta * 2"})
    with pytest.raises(screens.ScreenError, match="in a circle: Gamma → Gamma"):
        add(user, "Gamma = Gamma + 1")
    assert screens.list_ratios(user)[0].expression == "ROCE * 2"  # the refused edit changed nothing


def test_ratios_nest_but_not_too_deep(user):
    add(user, "R1 = ROCE")
    for n in range(2, compiler.MAX_RATIO_DEPTH + 1):
        add(user, f"R{n} = R{n - 1} + 1")
    with pytest.raises(screens.ScreenError, match="nest at most 8 deep"):
        add(user, f"R{compiler.MAX_RATIO_DEPTH + 1} = R{compiler.MAX_RATIO_DEPTH} + 1")
    ratios = screens.list_ratios(user)
    names = screens.name_table(ratios)
    compiled = compiler.Compiler(screens.parse_ratios(ratios, names)).compile(q.parse("R8 > 10", names))
    assert compiled.sql.count('"roce"') == 1 and compiled.params == [1.0] * 7 + [10.0]


def test_a_ratio_used_by_another_cannot_be_deleted(user):
    base = add(user, "Base = Sales / Debt")
    top = add(user, "Top = Base * 100")
    with pytest.raises(screens.ScreenError, match="used by the custom ratio Top"):
        screens.delete_ratio(user, base.id)
    screens.delete_ratio(user, top.id)
    screens.delete_ratio(user, base.id)
    assert screens.list_ratios(user) == []
    with pytest.raises(screens.ScreenError, match="No such custom ratio"):
        screens.delete_ratio(user, base.id)


def test_renaming_a_ratio_keeps_its_id(user):
    r = add(user, "Old name = Sales * 2")
    r2 = screens.save_ratio(user, {"id": r.id, "name": "New name", "expression": "Sales * 3"})
    assert (r2.id, r2.name, r2.expression) == (r.id, "New name", "Sales * 3")


def test_ratios_run_inline_over_the_snapshot(user, tmp_path):
    import tradingagents.dataflows.config as config_module

    path = tmp_path / "india.db"
    fx.build(path)
    config_module._config["india_db_path"] = str(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn)
    conn.close()
    add(user, "Earnings to price = Net profit / Market Capitalization")
    result = engine.run("Earnings to price > 0", user_conn=user, columns=["ratio:earnings to price"])
    row = next(r for r in result["rows"] if r["isin"] == fx.GROWCO)
    snap = store.open_existing(path).execute(
        "SELECT net_profit / market_cap FROM metrics_snapshot WHERE isin=?", (fx.GROWCO,)).fetchone()[0]
    assert row["values"]["ratio:earnings to price"] == pytest.approx(snap)
    assert result["columns"][2]["name"] == "Earnings to price" and result["columns"][2]["custom"]


# --- Saved screens ------------------------------------------------------------------------------

def test_screens_are_saved_renamed_listed_and_deleted(user):
    s = screens.save_screen(user, {"name": "  My   screen ", "query": "ROCE > 20\nROE > 15", "columns": ["pe"],
                                   "sort": {"key": "roce", "dir": "desc"}}, [])
    assert (s["name"], s["columns"], s["sort"], s["preset"]) == ("My screen", ["pe"], {"key": "roce", "dir": "desc"},
                                                                 False)
    renamed = screens.save_screen(user, {"id": s["id"], "name": "Renamed", "query": s["query"]}, [])
    assert renamed["id"] == s["id"] and renamed["name"] == "Renamed" and renamed["createdAt"] == s["createdAt"]
    assert [x["name"] for x in screens.list_screens(user)] == ["Renamed"]
    screens.delete_screen(user, s["id"])
    assert screens.list_screens(user) == []
    with pytest.raises(screens.ScreenError, match="No such screen"):
        screens.delete_screen(user, s["id"])


@pytest.mark.parametrize("body, message", [
    ({"name": "", "query": "ROCE > 1"}, "Give the screen a name"),
    ({"name": "x", "query": "Retrun on equity > 1"}, "did you mean 'Return on equity'"),
    ({"name": "x", "query": "ROCE > 1", "columns": ["nope"]}, "Unknown column: nope"),
    ({"name": "x", "query": "ROCE > 1", "columns": "roce"}, "columns must be a list"),
    ({"name": "x", "query": "ROCE > 1", "sort": {"key": "roce", "dir": "up"}}, "sort is"),
    ({"name": "x", "query": "ROCE > 1", "id": "preset:piotroski-strong"}, "Presets are read-only"),
    ({"name": "x", "query": "ROCE > 1", "id": 999}, "No such screen"),
])
def test_screens_that_cannot_be_saved(user, body, message):
    with pytest.raises(screens.ScreenError) as info:
        screens.save_screen(user, body, [])
    assert message in str(info.value)


def test_presets_are_ours_read_only_and_valid():
    presets = screens.presets()
    assert len(presets) >= 8 and all(p["preset"] and p["id"].startswith("preset:") for p in presets)
    names = screens.name_table([])
    for p in presets:
        q.parse(p["query"], names)
        assert screens.clean_columns(p["columns"], []) == p["columns"]
        assert screens.clean_sort(p["sort"], []) == p["sort"]
    with pytest.raises(screens.ScreenError, match="read-only"):
        screens.delete_screen(None, "preset:piotroski-strong")


def test_a_preset_can_be_duplicated_and_the_copy_edited(user):
    preset = screens.get_preset("preset:piotroski-strong")
    copy = screens.save_screen(user, {**preset, "id": None, "name": preset["name"] + " (copy)"}, [])
    edited = screens.save_screen(user, {**copy, "query": "Piotroski score >= 7"}, [])
    assert edited["query"] == "Piotroski score >= 7"
    assert screens.get_preset("preset:piotroski-strong")["query"] == "Piotroski score >= 8"
