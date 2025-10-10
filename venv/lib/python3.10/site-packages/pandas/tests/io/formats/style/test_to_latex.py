from textwrap import dedent

import numpy as np
import pytest

from pandas import (
    DataFrame,
    MultiIndex,
    Series,
    option_context,
)

pytest.importorskip("jinja2")
from pandas.io.formats.style import Styler
from pandas.io.formats.style_render import (
    _parse_latex_cell_styles,
    _parse_latex_css_conversion,
    _parse_latex_header_span,
    _parse_latex_table_styles,
    _parse_latex_table_wrapping,
)


@pytest.fixture
def df():
    return DataFrame(
        {"A": [0, 1], "B": [-0.61, -1.22], "C": Series(["ab", "cd"], dtype=object)}
    )


@pytest.fixture
def df_ext():
    return DataFrame(
        {"A": [0, 1, 2], "B": [-0.61, -1.22, -2.22], "C": ["ab", "cd", "de"]}
    )


@pytest.fixture
def styler(df):
    return Styler(df, uuid_len=0, precision=2)


def test_minimal_latex_tabular(styler):
    expected = dedent(
        """\
        \\begin{tabular}{lrrl}
         & A & B & C \\\\
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{tabular}
        """
    )
    assert styler.to_latex() == expected


def test_tabular_hrules(styler):
    expected = dedent(
        """\
        \\begin{tabular}{lrrl}
        \\toprule
         & A & B & C \\\\
        \\midrule
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\bottomrule
        \\end{tabular}
        """
    )
    assert styler.to_latex(hrules=True) == expected


def test_tabular_custom_hrules(styler):
    styler.set_table_styles(
        [
            {"selector": "toprule", "props": ":hline"},
            {"selector": "bottomrule", "props": ":otherline"},
        ]
    )  # no midrule
    expected = dedent(
        """\
        \\begin{tabular}{lrrl}
        \\hline
         & A & B & C \\\\
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\otherline
        \\end{tabular}
        """
    )
    assert styler.to_latex() == expected


def test_column_format(styler):
    # default setting is already tested in `test_latex_minimal_tabular`
    styler.set_table_styles([{"selector": "column_format", "props": ":cccc"}])

    assert "\\begin{tabular}{rrrr}" in styler.to_latex(column_format="rrrr")
    styler.set_table_styles([{"selector": "column_format", "props": ":r|r|cc"}])
    assert "\\begin{tabular}{r|r|cc}" in styler.to_latex()


def test_siunitx_cols(styler):
    expected = dedent(
        """\
        \\begin{tabular}{lSSl}
        {} & {A} & {B} & {C} \\\\
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{tabular}
        """
    )
    assert styler.to_latex(siunitx=True) == expected


def test_position(styler):
    assert "\\begin{table}[h!]" in styler.to_latex(position="h!")
    assert "\\end{table}" in styler.to_latex(position="h!")
    styler.set_table_styles([{"selector": "position", "props": ":b!"}])
    assert "\\begin{table}[b!]" in styler.to_latex()
    assert "\\end{table}" in styler.to_latex()


@pytest.mark.parametrize("env", [None, "longtable"])
def test_label(styler, env):
    assert "\n\\label{text}" in styler.to_latex(label="text", environment=env)
    styler.set_table_styles([{"selector": "label", "props": ":{more §text}"}])
    assert "\n\\label{more :text}" in styler.to_latex(environment=env)


def test_position_float_raises(styler):
    msg = "`position_float` should be one of 'raggedright', 'raggedleft', 'centering',"
    with pytest.raises(ValueError, match=msg):
        styler.to_latex(position_float="bad_string")

    msg = "`position_float` cannot be used in 'longtable' `environment`"
    with pytest.raises(ValueError, match=msg):
        styler.to_latex(position_float="centering", environment="longtable")


@pytest.mark.parametrize("label", [(None, ""), ("text", "\\label{text}")])
@pytest.mark.parametrize("position", [(None, ""), ("h!", "{table}[h!]")])
@pytest.mark.parametrize("caption", [(None, ""), ("text", "\\caption{text}")])
@pytest.mark.parametrize("column_format", [(None, ""), ("rcrl", "{tabular}{rcrl}")])
@pytest.mark.parametrize("position_float", [(None, ""), ("centering", "\\centering")])
def test_kwargs_combinations(
    styler, label, position, caption, column_format, position_float
):
    result = styler.to_latex(
        label=label[0],
        position=position[0],
        caption=caption[0],
        column_format=column_format[0],
        position_float=position_float[0],
    )
    assert label[1] in result
    assert position[1] in result
    assert caption[1] in result
    assert column_format[1] in result
    assert position_float[1] in result


def test_custom_table_styles(styler):
    styler.set_table_styles(
        [
            {"selector": "mycommand", "props": ":{myoptions}"},
            {"selector": "mycommand2", "props": ":{myoptions2}"},
        ]
    )
    expected = dedent(
        """\
        \\begin{table}
        \\mycommand{myoptions}
        \\mycommand2{myoptions2}
        """
    )
    assert expected in styler.to_latex()


def test_cell_styling(styler):
    styler.highlight_max(props="itshape:;Huge:--wrap;")
    expected = dedent(
        """\
        \\begin{tabular}{lrrl}
         & A & B & C \\\\
        0 & 0 & \\itshape {\\Huge -0.61} & ab \\\\
        1 & \\itshape {\\Huge 1} & -1.22 & \\itshape {\\Huge cd} \\\\
        \\end{tabular}
        """
    )
    assert expected == styler.to_latex()


def test_multiindex_columns(df):
    cidx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df.columns = cidx
    expected = dedent(
        """\
        \\begin{tabular}{lrrl}
         & \\multicolumn{2}{r}{A} & B \\\\
         & a & b & c \\\\
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{tabular}
        """
    )
    s = df.style.format(precision=2)
    assert expected == s.to_latex()

    # non-sparse
    expected = dedent(
        """\
        \\begin{tabular}{lrrl}
         & A & A & B \\\\
         & a & b & c \\\\
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{tabular}
        """
    )
    s = df.style.format(precision=2)
    assert expected == s.to_latex(sparse_columns=False)


def test_multiindex_row(df_ext):
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df_ext.index = ridx
    expected = dedent(
        """\
        \\begin{tabular}{llrrl}
         &  & A & B & C \\\\
        \\multirow[c]{2}{*}{A} & a & 0 & -0.61 & ab \\\\
         & b & 1 & -1.22 & cd \\\\
        B & c & 2 & -2.22 & de \\\\
        \\end{tabular}
        """
    )
    styler = df_ext.style.format(precision=2)
    result = styler.to_latex()
    assert expected == result

    # non-sparse
    expected = dedent(
        """\
        \\begin{tabular}{llrrl}
         &  & A & B & C \\\\
        A & a & 0 & -0.61 & ab \\\\
        A & b & 1 & -1.22 & cd \\\\
        B & c & 2 & -2.22 & de \\\\
        \\end{tabular}
        """
    )
    result = styler.to_latex(sparse_index=False)
    assert expected == result


def test_multirow_naive(df_ext):
    ridx = MultiIndex.from_tuples([("X", "x"), ("X", "y"), ("Y", "z")])
    df_ext.index = ridx
    expected = dedent(
        """\
        \\begin{tabular}{llrrl}
         &  & A & B & C \\\\
        X & x & 0 & -0.61 & ab \\\\
         & y & 1 & -1.22 & cd \\\\
        Y & z & 2 & -2.22 & de \\\\
        \\end{tabular}
        """
    )
    styler = df_ext.style.format(precision=2)
    result = styler.to_latex(multirow_align="naive")
    assert expected == result


def test_multiindex_row_and_col(df_ext):
    cidx = MultiIndex.from_tuples([("Z", "a"), ("Z", "b"), ("Y", "c")])
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df_ext.index, df_ext.columns = ridx, cidx
    expected = dedent(
        """\
        \\begin{tabular}{llrrl}
         &  & \\multicolumn{2}{l}{Z} & Y \\\\
         &  & a & b & c \\\\
        \\multirow[b]{2}{*}{A} & a & 0 & -0.61 & ab \\\\
         & b & 1 & -1.22 & cd \\\\
        B & c & 2 & -2.22 & de \\\\
        \\end{tabular}
        """
    )
    styler = df_ext.style.format(precision=2)
    result = styler.to_latex(multirow_align="b", multicol_align="l")
    assert result == expected

    # non-sparse
    expected = dedent(
        """\
        \\begin{tabular}{llrrl}
         &  & Z & Z & Y \\\\
         &  & a & b & c \\\\
        A & a & 0 & -0.61 & ab \\\\
        A & b & 1 & -1.22 & cd \\\\
        B & c & 2 & -2.22 & de \\\\
        \\end{tabular}
        """
    )
    result = styler.to_latex(sparse_index=False, sparse_columns=False)
    assert result == expected


@pytest.mark.parametrize(
    "multicol_align, siunitx, header",
    [
        ("naive-l", False, " & A & &"),
        ("naive-r", False, " & & & A"),
        ("naive-l", True, "{} & {A} & {} & {}"),
        ("naive-r", True, "{} & {} & {} & {A}"),
    ],
)
def test_multicol_naive(df, multicol_align, siunitx, header):
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("A", "c")])
    df.columns = ridx
    level1 = " & a & b & c" if not siunitx else "{} & {a} & {b} & {c}"
    col_format = "lrrl" if not siunitx else "lSSl"
    expected = dedent(
        f"""\
        \\begin{{tabular}}{{{col_format}}}
        {header} \\\\
        {level1} \\\\
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{{tabular}}
        """
    )
    styler = df.style.format(precision=2)
    result = styler.to_latex(multicol_align=multicol_align, siunitx=siunitx)
    assert expected == result


def test_multi_options(df_ext):
    cidx = MultiIndex.from_tuples([("Z", "a"), ("Z", "b"), ("Y", "c")])
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df_ext.index, df_ext.columns = ridx, cidx
    styler = df_ext.style.format(precision=2)

    expected = dedent(
        """\
     &  & \\multicolumn{2}{r}{Z} & Y \\\\
     &  & a & b & c \\\\
    \\multirow[c]{2}{*}{A} & a & 0 & -0.61 & ab \\\\
    """
    )
    result = styler.to_latex()
    assert expected in result

    with option_context("styler.latex.multicol_align", "l"):
        assert " &  & \\multicolumn{2}{l}{Z} & Y \\\\" in styler.to_latex()

    with option_context("styler.latex.multirow_align", "b"):
        assert "\\multirow[b]{2}{*}{A} & a & 0 & -0.61 & ab \\\\" in styler.to_latex()


def test_multiindex_columns_hidden():
    df = DataFrame([[1, 2, 3, 4]])
    df.columns = MultiIndex.from_tuples([("A", 1), ("A", 2), ("A", 3), ("B", 1)])
    s = df.style
    assert "{tabular}{lrrrr}" in s.to_latex()
    s.set_table_styles([])  # reset the position command
    s.hide([("A", 2)], axis="columns")
    assert "{tabular}{lrrr}" in s.to_latex()


@pytest.mark.parametrize(
    "option, value",
    [
        ("styler.sparse.index", True),
        ("styler.sparse.index", False),
        ("styler.sparse.columns", True),
        ("styler.sparse.columns", False),
    ],
)
def test_sparse_options(df_ext, option, value):
    cidx = MultiIndex.from_tuples([("Z", "a"), ("Z", "b"), ("Y", "c")])
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df_ext.index, df_ext.columns = ridx, cidx
    styler = df_ext.style

    latex1 = styler.to_latex()
    with option_context(option, value):
        latex2 = styler.to_latex()
    assert (latex1 == latex2) is value


def test_hidden_index(styler):
    styler.hide(axis="index")
    expected = dedent(
        """\
        \\begin{tabular}{rrl}
        A & B & C \\\\
        0 & -0.61 & ab \\\\
        1 & -1.22 & cd \\\\
        \\end{tabular}
        """
    )
    assert styler.to_latex() == expected


@pytest.mark.parametrize("environment", ["table", "figure*", None])
def test_comprehensive(df_ext, environment):
    # test as many low level features simultaneously as possible
    cidx = MultiIndex.from_tuples([("Z", "a"), ("Z", "b"), ("Y", "c")])
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df_ext.index, df_ext.columns = ridx, cidx
    stlr = df_ext.style
    stlr.set_caption("mycap")
    stlr.set_table_styles(
        [
            {"selector": "label", "props": ":{fig§item}"},
            {"selector": "position", "props": ":h!"},
            {"selector": "position_float", "props": ":centering"},
            {"selector": "column_format", "props": ":rlrlr"},
            {"selector": "toprule", "props": ":toprule"},
            {"selector": "midrule", "props": ":midrule"},
            {"selector": "bottomrule", "props": ":bottomrule"},
            {"selector": "rowcolors", "props": ":{3}{pink}{}"},  # custom command
        ]
    )
    stlr.highlight_max(axis=0, props="textbf:--rwrap;cellcolor:[rgb]{1,1,0.6}--rwrap")
    stlr.highlight_max(axis=None, props="Huge:--wrap;", subset=[("Z", "a"), ("Z", "b")])

    expected = (
        """\
\\begin{table}[h!]
\\centering
\\caption{mycap}
\\label{fig:item}
\\rowcolors{3}{pink}{}
\\begin{tabular}{rlrlr}
\\toprule
 &  & \\multicolumn{2}{r}{Z} & Y \\\\
 &  & a & b & c \\\\
\\midrule
\\multirow[c]{2}{*}{A} & a & 0 & \\textbf{\\cellcolor[rgb]{1,1,0.6}{-0.61}} & ab \\\\
 & b & 1 & -1.22 & cd \\\\
B & c & \\textbf{\\cellcolor[rgb]{1,1,0.6}{{\\Huge 2}}} & -2.22 & """
        """\
\\textbf{\\cellcolor[rgb]{1,1,0.6}{de}} \\\\
\\bottomrule
\\end{tabular}
\\end{table}
"""
    ).replace("table", environment if environment else "table")
    result = stlr.format(precision=2).to_latex(environment=environment)
    assert result == expected


def test_environment_option(styler):
    with option_context("styler.latex.environment", "bar-env"):
        assert "\\begin{bar-env}" in styler.to_latex()
        assert "\\begin{foo-env}" in styler.to_latex(environment="foo-env")


def test_parse_latex_table_styles(styler):
    styler.set_table_styles(
        [
            {"selector": "foo", "props": [("attr", "value")]},
            {"selector": "bar", "props": [("attr", "overwritten")]},
            {"selector": "bar", "props": [("attr", "baz"), ("attr2", "ignored")]},
            {"selector": "label", "props": [("", "{fig§item}")]},
        ]
    )
    assert _parse_latex_table_styles(styler.table_styles, "bar") == "baz"

    # test '§' replaced by ':' [for CSS compatibility]
    assert _parse_latex_table_styles(styler.table_styles, "label") == "{fig:item}"


def test_parse_latex_cell_styles_basic():  # test nesting
    cell_style = [("itshape", "--rwrap"), ("cellcolor", "[rgb]{0,1,1}--rwrap")]
    expected = "\\itshape{\\cellcolor[rgb]{0,1,1}{text}}"
    assert _parse_latex_cell_styles(cell_style, "text") == expected


@pytest.mark.parametrize(
    "wrap_arg, expected",
    [  # test wrapping
        ("", "\\<command><options> <display_value>"),
        ("--wrap", "{\\<command><options> <display_value>}"),
        ("--nowrap", "\\<command><options> <display_value>"),
        ("--lwrap", "{\\<command><options>} <display_value>"),
        ("--dwrap", "{\\<command><options>}{<display_value>}"),
        ("--rwrap", "\\<command><options>{<display_value>}"),
    ],
)
def test_parse_latex_cell_styles_braces(wrap_arg, expected):
    cell_style = [("<command>", f"<options>{wrap_arg}")]
    assert _parse_latex_cell_styles(cell_style, "<display_value>") == expected


def test_parse_latex_header_span():
    cell = {"attributes": 'colspan="3"', "display_value": "text", "cellstyle": []}
    expected = "\\multicolumn{3}{Y}{text}"
    assert _parse_latex_header_span(cell, "X", "Y") == expected

    cell = {"attributes": 'rowspan="5"', "display_value": "text", "cellstyle": []}
    expected = "\\multirow[X]{5}{*}{text}"
    assert _parse_latex_header_span(cell, "X", "Y") == expected

    cell = {"display_value": "text", "cellstyle": []}
    assert _parse_latex_header_span(cell, "X", "Y") == "text"

    cell = {"display_value": "text", "cellstyle": [("bfseries", "--rwrap")]}
    assert _parse_latex_header_span(cell, "X", "Y") == "\\bfseries{text}"


def test_parse_latex_table_wrapping(styler):
    styler.set_table_styles(
        [
            {"selector": "toprule", "props": ":value"},
            {"selector": "bottomrule", "props": ":value"},
            {"selector": "midrule", "props": ":value"},
            {"selector": "column_format", "props": ":value"},
        ]
    )
    assert _parse_latex_table_wrapping(styler.table_styles, styler.caption) is False
    assert _parse_latex_table_wrapping(styler.table_styles, "some caption") is True
    styler.set_table_styles(
        [
            {"selector": "not-ignored", "props": ":value"},
        ],
        overwrite=False,
    )
    assert _parse_latex_table_wrapping(styler.table_styles, None) is True


def test_short_caption(styler):
    result = styler.to_latex(caption=("full cap", "short cap"))
    assert "\\caption[short cap]{full cap}" in result


@pytest.mark.parametrize(
    "css, expected",
    [
        ([("color", "red")], [("color", "{red}")]),  # test color and input format types
        (
            [("color", "rgb(128, 128, 128 )")],
            [("color", "[rgb]{0.502, 0.502, 0.502}")],
        ),
        (
            [("color", "rgb(128, 50%, 25% )")],
            [("color", "[rgb]{0.502, 0.500, 0.250}")],
        ),
        (
            [("color", "rgba(128,128,128,1)")],
            [("color", "[rgb]{0.502, 0.502, 0.502}")],
        ),
        ([("color", "#FF00FF")], [("color", "[HTML]{FF00FF}")]),
        ([("color", "#F0F")], [("color", "[HTML]{FF00FF}")]),
        ([("font-weight", "bold")], [("bfseries", "")]),  # test font-weight and types
        ([("font-weight", "bolder")], [("bfseries", "")]),
        ([("font-weight", "normal")], []),
        ([("background-color", "red")], [("cellcolor", "{red}--lwrap")]),
        (
            [("background-color", "#FF00FF")],  # test background-color command and wrap
            [("cellcolor", "[HTML]{FF00FF}--lwrap")],
        ),
        ([("font-style", "italic")], [("itshape", "")]),  # test font-style and types
        ([("font-style", "oblique")], [("slshape", "")]),
        ([("font-style", "normal")], []),
        ([("color", "red /*--dwrap*/")], [("color", "{red}--dwrap")]),  # css comments
        ([("background-color", "red /* --dwrap */")], [("cellcolor", "{red}--dwrap")]),
    ],
)
def test_parse_latex_css_conversion(css, expected):
    result = _parse_latex_css_conversion(css)
    assert result == expected


@pytest.mark.parametrize(
    "env, inner_env",
    [
        (None, "tabular"),
        ("table", "tabular"),
        ("longtable", "longtable"),
    ],
)
@pytest.mark.parametrize(
    "convert, exp", [(True, "bfseries"), (False, "font-weightbold")]
)
def test_parse_latex_css_convert_minimal(styler, env, inner_env, convert, exp):
    # parameters ensure longtable template is also tested
    styler.highlight_max(props="font-weight:bold;")
    result = styler.to_latex(convert_css=convert, environment=env)
    expected = dedent(
        f"""\
        0 & 0 & \\{exp} -0.61 & ab \\\\
        1 & \\{exp} 1 & -1.22 & \\{exp} cd \\\\
        \\end{{{inner_env}}}
    """
    )
    assert expected in result


def test_parse_latex_css_conversion_option():
    css = [("command", "option--latex--wrap")]
    expected = [("command", "option--wrap")]
    result = _parse_latex_css_conversion(css)
    assert result == expected


def test_styler_object_after_render(styler):
    # GH 42320
    pre_render = styler._copy(deepcopy=True)
    styler.to_latex(
        column_format="rllr",
        position="h",
        position_float="centering",
        hrules=True,
        label="my lab",
        caption="my cap",
    )

    assert pre_render.table_styles == styler.table_styles
    assert pre_render.caption == styler.caption


def test_longtable_comprehensive(styler):
    result = styler.to_latex(
        environment="longtable", hrules=True, label="fig:A", caption=("full", "short")
    )
    expected = dedent(
        """\
        \\begin{longtable}{lrrl}
        \\caption[short]{full} \\label{fig:A} \\\\
        \\toprule
         & A & B & C \\\\
        \\midrule
        \\endfirsthead
        \\caption[]{full} \\\\
        \\toprule
         & A & B & C \\\\
        \\midrule
        \\endhead
        \\midrule
        \\multicolumn{4}{r}{Continued on next page} \\\\
        \\midrule
        \\endfoot
        \\bottomrule
        \\endlastfoot
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{longtable}
    """
    )
    assert result == expected


def test_longtable_minimal(styler):
    result = styler.to_latex(environment="longtable")
    expected = dedent(
        """\
        \\begin{longtable}{lrrl}
         & A & B & C \\\\
        \\endfirsthead
         & A & B & C \\\\
        \\endhead
        \\multicolumn{4}{r}{Continued on next page} \\\\
        \\endfoot
        \\endlastfoot
        0 & 0 & -0.61 & ab \\\\
        1 & 1 & -1.22 & cd \\\\
        \\end{longtable}
    """
    )
    assert result == expected


@pytest.mark.parametrize(
    "sparse, exp, siunitx",
    [
        (True, "{} & \\multicolumn{2}{r}{A} & {B}", True),
        (False, "{} & {A} & {A} & {B}", True),
        (True, " & \\multicolumn{2}{r}{A} & B", False),
        (False, " & A & A & B", False),
    ],
)
def test_longtable_multiindex_columns(df, sparse, exp, siunitx):
    cidx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df.columns = cidx
    with_si = "{} & {a} & {b} & {c} \\\\"
    without_si = " & a & b & c \\\\"
    expected = dedent(
        f"""\
        \\begin{{longtable}}{{l{"SS" if siunitx else "rr"}l}}
        {exp} \\\\
        {with_si if siunitx else without_si}
        \\endfirsthead
        {exp} \\\\
        {with_si if siunitx else without_si}
        \\endhead
        """
    )
    result = df.style.to_latex(
        environment="longtable", sparse_columns=sparse, siunitx=siunitx
    )
    assert expected in result


@pytest.mark.parametrize(
    "caption, cap_exp",
    [
        ("full", ("{full}", "")),
        (("full", "short"), ("{full}", "[short]")),
    ],
)
@pytest.mark.parametrize("label, lab_exp", [(None, ""), ("tab:A", " \\label{tab:A}")])
def test_longtable_caption_label(styler, caption, cap_exp, label, lab_exp):
    cap_exp1 = f"\\caption{cap_exp[1]}{cap_exp[0]}"
    cap_exp2 = f"\\caption[]{cap_exp[0]}"

    expected = dedent(
        f"""\
        {cap_exp1}{lab_exp} \\\\
         & A & B & C \\\\
        \\endfirsthead
        {cap_exp2} \\\\
        """
    )
    assert expected in styler.to_latex(
        environment="longtable", caption=caption, label=label
    )


@pytest.mark.parametrize("index", [True, False])
@pytest.mark.parametrize(
    "columns, siunitx",
    [
        (True, True),
        (True, False),
        (False, False),
    ],
)
def test_apply_map_header_render_mi(df_ext, index, columns, siunitx):
    cidx = MultiIndex.from_tuples([("Z", "a"), ("Z", "b"), ("Y", "c")])
    ridx = MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "c")])
    df_ext.index, df_ext.columns = ridx, cidx
    styler = df_ext.style

    func = lambda v: "bfseries: --rwrap" if "A" in v or "Z" in v or "c" in v else None

    if index:
        styler.map_index(func, axis="index")
    if columns:
        styler.map_index(func, axis="columns")

    result = styler.to_latex(siunitx=siunitx)

    expected_index = dedent(
        """\
    \\multirow[c]{2}{*}{\\bfseries{A}} & a & 0 & -0.610000 & ab \\\\
    \\bfseries{} & b & 1 & -1.220000 & cd \\\\
    B & \\bfseries{c} & 2 & -2.220000 & de \\\\
    """
    )
    assert (expected_index in result) is index

    exp_cols_si = dedent(
        """\
    {} & {} & \\multicolumn{2}{r}{\\bfseries{Z}} & {Y} \\\\
    {} & {} & {a} & {b} & {\\bfseries{c}} \\\\
    """
    )
    exp_cols_no_si = """\
 &  & \\multicolumn{2}{r}{\\bfseries{Z}} & Y \\\\
 &  & a & b & \\bfseries{c} \\\\
"""
    assert ((exp_cols_si if siunitx else exp_cols_no_si) in result) is columns


def test_repr_option(styler):
    assert "<style" in styler._repr_html_()[:6]
    assert styler._repr_latex_() is None
    with option_context("styler.render.repr", "latex"):
        assert "\\begin{tabular}" in styler._repr_latex_()[:15]
        assert styler._repr_html_() is None


@pytest.mark.parametrize("option", ["hrules"])
def test_bool_options(styler, option):
    with option_context(f"styler.latex.{option}", False):
        latex_false = styler.to_latex()
    with option_context(f"styler.latex.{option}", True):
        latex_true = styler.to_latex()
    assert latex_false != latex_true  # options are reactive under to_latex(*no_args)


def test_siunitx_basic_headers(styler):
    assert "{} & {A} & {B} & {C} \\\\" in styler.to_latex(siunitx=True)
    assert " & A & B & C \\\\" in styler.to_latex()  # default siunitx=False


@pytest.mark.parametrize("axis", ["index", "columns"])
def test_css_convert_apply_index(styler, axis):
    styler.map_index(lambda x: "font-weight: bold;", axis=axis)
    for label in getattr(styler, axis):
        assert f"\\bfseries {label}" in styler.to_latex(convert_css=True)


def test_hide_index_latex(styler):
    # GH 43637
    styler.hide([0], axis=0)
    result = styler.to_latex()
    expected = dedent(
        """\
    \\begin{tabular}{lrrl}
     & A & B & C \\\\
    1 & 1 & -1.22 & cd \\\\
    \\end{tabular}
    """
    )
    assert expected == result


def test_latex_hiding_index_columns_multiindex_alignment():
    # gh 43644
    midx = MultiIndex.from_product(
        [["i0", "j0"], ["i1"], ["i2", "j2"]], names=["i-0", "i-1", "i-2"]
    )
    cidx = MultiIndex.from_product(
        [["c0"], ["c1", "d1"], ["c2", "d2"]], names=["c-0", "c-1", "c-2"]
    )
    df = DataFrame(np.arange(16).reshape(4, 4), index=midx, columns=cidx)
    styler = Styler(df, uuid_len=0)
    styler.hide(level=1, axis=0).hide(level=0, axis=1)
    styler.hide([("i0", "i1", "i2")], axis=0)
    styler.hide([("c0", "c1", "c2")], axis=1)
    styler.map(lambda x: "color:{red};" if x == 5 else "")
    styler.map_index(lambda x: "color:{blue};" if "j" in x else "")
    result = styler.to_latex()
    expected = dedent(
        """\
        \\begin{tabular}{llrrr}
         & c-1 & c1 & \\multicolumn{2}{r}{d1} \\\\
         & c-2 & d2 & c2 & d2 \\\\
        i-0 & i-2 &  &  &  \\\\
        i0 & \\color{blue} j2 & \\color{red} 5 & 6 & 7 \\\\
        \\multirow[c]{2}{*}{\\color{blue} j0} & i2 & 9 & 10 & 11 \\\\
        \\color{blue}  & \\color{blue} j2 & 13 & 14 & 15 \\\\
        \\end{tabular}
        """
    )
    assert result == expected


def test_rendered_links():
    # note the majority of testing is done in test_html.py: test_rendered_links
    # these test only the alternative latex format is functional
    df = DataFrame(["text www.domain.com text"])
    result = df.style.format(hyperlinks="latex").to_latex()
    assert r"text \href{www.domain.com}{www.domain.com} text" in result


def test_apply_index_hidden_levels():
    # gh 45156
    styler = DataFrame(
        [[1]],
        index=MultiIndex.from_tuples([(0, 1)], names=["l0", "l1"]),
        columns=MultiIndex.from_tuples([(0, 1)], names=["c0", "c1"]),
    ).style
    styler.hide(level=1)
    styler.map_index(lambda v: "color: red;", level=0, axis=1)
    result = styler.to_latex(convert_css=True)
    expected = dedent(
        """\
        \\begin{tabular}{lr}
        c0 & \\color{red} 0 \\\\
        c1 & 1 \\\\
        l0 &  \\\\
        0 & 1 \\\\
        \\end{tabular}
        """
    )
    assert result == expected


@pytest.mark.parametrize("clines", ["bad", "index", "skip-last", "all", "data"])
def test_clines_validation(clines, styler):
    msg = f"`clines` value of {clines} is invalid."
    with pytest.raises(ValueError, match=msg):
        styler.to_latex(clines=clines)


@pytest.mark.parametrize(
    "clines, exp",
    [
        ("all;index", "\n\\cline{1-1}"),
        ("all;data", "\n\\cline{1-2}"),
        ("skip-last;index", ""),
        ("skip-last;data", ""),
        (None, ""),
    ],
)
@pytest.mark.parametrize("env", ["table", "longtable"])
def test_clines_index(clines, exp, env):
    df = DataFrame([[1], [2], [3], [4]])
    result = df.style.to_latex(clines=clines, environment=env)
    expected = f"""\
0 & 1 \\\\{exp}
1 & 2 \\\\{exp}
2 & 3 \\\\{exp}
3 & 4 \\\\{exp}
"""
    assert expected in result


@pytest.mark.parametrize(
    "clines, expected",
    [
        (
            None,
            dedent(
                """\
            \\multirow[c]{2}{*}{A} & X & 1 \\\\
             & Y & 2 \\\\
            \\multirow[c]{2}{*}{B} & X & 3 \\\\
             & Y & 4 \\\\
            """
            ),
        ),
        (
            "skip-last;index",
            dedent(
                """\
            \\multirow[c]{2}{*}{A} & X & 1 \\\\
             & Y & 2 \\\\
            \\cline{1-2}
            \\multirow[c]{2}{*}{B} & X & 3 \\\\
             & Y & 4 \\\\
            \\cline{1-2}
            """
            ),
        ),
        (
            "skip-last;data",
            dedent(
                """\
            \\multirow[c]{2}{*}{A} & X & 1 \\\\
             & Y & 2 \\\\
            \\cline{1-3}
            \\multirow[c]{2}{*}{B} & X & 3 \\\\
             & Y & 4 \\\\
            \\cline{1-3}
            """
            ),
        ),
        (
            "all;index",
            dedent(
                """\
            \\multirow[c]{2}{*}{A} & X & 1 \\\\
            \\cline{2-2}
             & Y & 2 \\\\
            \\cline{1-2} \\cline{2-2}
            \\multirow[c]{2}{*}{B} & X & 3 \\\\
            \\cline{2-2}
             & Y & 4 \\\\
            \\cline{1-2} \\cline{2-2}
            """
            ),
        ),
        (
            "all;data",
            dedent(
                """\
            \\multirow[c]{2}{*}{A} & X & 1 \\\\
            \\cline{2-3}
             & Y & 2 \\\\
            \\cline{1-3} \\cline{2-3}
            \\multirow[c]{2}{*}{B} & X & 3 \\\\
            \\cline{2-3}
             & Y & 4 \\\\
            \\cline{1-3} \\cline{2-3}
            """
            ),
        ),
    ],
)
@pytest.mark.parametrize("env", ["table"])
def test_clines_multiindex(clines, expected, env):
    # also tests simultaneously with hidden rows and a hidden multiindex level
    midx = MultiIndex.from_product([["A", "-", "B"], [0], ["X", "Y"]])
    df = DataFrame([[1], [2], [99], [99], [3], [4]], index=midx)
    styler = df.style
    styler.hide([("-", 0, "X"), ("-", 0, "Y")])
    styler.hide(level=1)
    result = styler.to_latex(clines=clines, environment=env)
    assert expected in result


def test_col_format_len(styler):
    # gh 46037
    result = styler.to_latex(environment="longtable", column_format="lrr{10cm}")
    expected = r"\multicolumn{4}{r}{Continued on next page} \\"
    assert expected in result


def test_concat(styler):
    result = styler.concat(styler.data.agg(["sum"]).style).to_latex()
    expected = dedent(
        """\
    \\begin{tabular}{lrrl}
     & A & B & C \\\\
    0 & 0 & -0.61 & ab \\\\
    1 & 1 & -1.22 & cd \\\\
    sum & 1 & -1.830000 & abcd \\\\
    \\end{tabular}
    """
    )
    assert result == expected


def test_concat_recursion():
    # tests hidden row recursion and applied styles
    styler1 = DataFrame([[1], [9]]).style.hide([1]).highlight_min(color="red")
    styler2 = DataFrame([[9], [2]]).style.hide([0]).highlight_min(color="green")
    styler3 = DataFrame([[3], [9]]).style.hide([1]).highlight_min(color="blue")

    result = styler1.concat(styler2.concat(styler3)).to_latex(convert_css=True)
    expected = dedent(
        """\
    \\begin{tabular}{lr}
     & 0 \\\\
    0 & {\\cellcolor{red}} 1 \\\\
    1 & {\\cellcolor{green}} 2 \\\\
    0 & {\\cellcolor{blue}} 3 \\\\
    \\end{tabular}
    """
    )
    assert result == expected


def test_concat_chain():
    # tests hidden row recursion and applied styles
    styler1 = DataFrame([[1], [9]]).style.hide([1]).highlight_min(color="red")
    styler2 = DataFrame([[9], [2]]).style.hide([0]).highlight_min(color="green")
    styler3 = DataFrame([[3], [9]]).style.hide([1]).highlight_min(color="blue")

    result = styler1.concat(styler2).concat(styler3).to_latex(convert_css=True)
    expected = dedent(
        """\
    \\begin{tabular}{lr}
     & 0 \\\\
    0 & {\\cellcolor{red}} 1 \\\\
    1 & {\\cellcolor{green}} 2 \\\\
    0 & {\\cellcolor{blue}} 3 \\\\
    \\end{tabular}
    """
    )
    assert result == expected


@pytest.mark.parametrize(
    "df, expected",
    [
        (
            DataFrame(),
            dedent(
                """\
            \\begin{tabular}{l}
            \\end{tabular}
            """
            ),
        ),
        (
            DataFrame(columns=["a", "b", "c"]),
            dedent(
                """\
            \\begin{tabular}{llll}
             & a & b & c \\\\
            \\end{tabular}
            """
            ),
        ),
    ],
)
@pytest.mark.parametrize(
    "clines", [None, "all;data", "all;index", "skip-last;data", "skip-last;index"]
)
def test_empty_clines(df: DataFrame, expected: str, clines: str):
    # GH 47203
    result = df.style.to_latex(clines=clines)
    assert result == expected
