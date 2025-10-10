from textwrap import dedent

import pytest

from pandas import (
    DataFrame,
    IndexSlice,
)

pytest.importorskip("jinja2")

from pandas.io.formats.style import Styler


@pytest.fixture
def df():
    return DataFrame(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        index=["i", "j", "j"],
        columns=["c", "d", "d"],
        dtype=float,
    )


@pytest.fixture
def styler(df):
    return Styler(df, uuid_len=0)


def test_format_non_unique(df):
    # GH 41269

    # test dict
    html = df.style.format({"d": "{:.1f}"}).to_html()
    for val in ["1.000000<", "4.000000<", "7.000000<"]:
        assert val in html
    for val in ["2.0<", "3.0<", "5.0<", "6.0<", "8.0<", "9.0<"]:
        assert val in html

    # test subset
    html = df.style.format(precision=1, subset=IndexSlice["j", "d"]).to_html()
    for val in ["1.000000<", "4.000000<", "7.000000<", "2.000000<", "3.000000<"]:
        assert val in html
    for val in ["5.0<", "6.0<", "8.0<", "9.0<"]:
        assert val in html


@pytest.mark.parametrize("func", ["apply", "map"])
def test_apply_map_non_unique_raises(df, func):
    # GH 41269
    if func == "apply":
        op = lambda s: ["color: red;"] * len(s)
    else:
        op = lambda v: "color: red;"

    with pytest.raises(KeyError, match="`Styler.apply` and `.map` are not"):
        getattr(df.style, func)(op)._compute()


def test_table_styles_dict_non_unique_index(styler):
    styles = styler.set_table_styles(
        {"j": [{"selector": "td", "props": "a: v;"}]}, axis=1
    ).table_styles
    assert styles == [
        {"selector": "td.row1", "props": [("a", "v")]},
        {"selector": "td.row2", "props": [("a", "v")]},
    ]


def test_table_styles_dict_non_unique_columns(styler):
    styles = styler.set_table_styles(
        {"d": [{"selector": "td", "props": "a: v;"}]}, axis=0
    ).table_styles
    assert styles == [
        {"selector": "td.col1", "props": [("a", "v")]},
        {"selector": "td.col2", "props": [("a", "v")]},
    ]


def test_tooltips_non_unique_raises(styler):
    # ttips has unique keys
    ttips = DataFrame([["1", "2"], ["3", "4"]], columns=["c", "d"], index=["a", "b"])
    styler.set_tooltips(ttips=ttips)  # OK

    # ttips has non-unique columns
    ttips = DataFrame([["1", "2"], ["3", "4"]], columns=["c", "c"], index=["a", "b"])
    with pytest.raises(KeyError, match="Tooltips render only if `ttips` has unique"):
        styler.set_tooltips(ttips=ttips)

    # ttips has non-unique index
    ttips = DataFrame([["1", "2"], ["3", "4"]], columns=["c", "d"], index=["a", "a"])
    with pytest.raises(KeyError, match="Tooltips render only if `ttips` has unique"):
        styler.set_tooltips(ttips=ttips)


def test_set_td_classes_non_unique_raises(styler):
    # classes has unique keys
    classes = DataFrame([["1", "2"], ["3", "4"]], columns=["c", "d"], index=["a", "b"])
    styler.set_td_classes(classes=classes)  # OK

    # classes has non-unique columns
    classes = DataFrame([["1", "2"], ["3", "4"]], columns=["c", "c"], index=["a", "b"])
    with pytest.raises(KeyError, match="Classes render only if `classes` has unique"):
        styler.set_td_classes(classes=classes)

    # classes has non-unique index
    classes = DataFrame([["1", "2"], ["3", "4"]], columns=["c", "d"], index=["a", "a"])
    with pytest.raises(KeyError, match="Classes render only if `classes` has unique"):
        styler.set_td_classes(classes=classes)


def test_hide_columns_non_unique(styler):
    ctx = styler.hide(["d"], axis="columns")._translate(True, True)

    assert ctx["head"][0][1]["display_value"] == "c"
    assert ctx["head"][0][1]["is_visible"] is True

    assert ctx["head"][0][2]["display_value"] == "d"
    assert ctx["head"][0][2]["is_visible"] is False

    assert ctx["head"][0][3]["display_value"] == "d"
    assert ctx["head"][0][3]["is_visible"] is False

    assert ctx["body"][0][1]["is_visible"] is True
    assert ctx["body"][0][2]["is_visible"] is False
    assert ctx["body"][0][3]["is_visible"] is False


def test_latex_non_unique(styler):
    result = styler.to_latex()
    assert result == dedent(
        """\
        \\begin{tabular}{lrrr}
         & c & d & d \\\\
        i & 1.000000 & 2.000000 & 3.000000 \\\\
        j & 4.000000 & 5.000000 & 6.000000 \\\\
        j & 7.000000 & 8.000000 & 9.000000 \\\\
        \\end{tabular}
    """
    )
