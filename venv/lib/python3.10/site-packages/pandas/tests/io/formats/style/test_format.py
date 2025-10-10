import numpy as np
import pytest

from pandas import (
    NA,
    DataFrame,
    IndexSlice,
    MultiIndex,
    NaT,
    Timestamp,
    option_context,
)

pytest.importorskip("jinja2")
from pandas.io.formats.style import Styler
from pandas.io.formats.style_render import _str_escape


@pytest.fixture
def df():
    return DataFrame(
        data=[[0, -0.609], [1, -1.228]],
        columns=["A", "B"],
        index=["x", "y"],
    )


@pytest.fixture
def styler(df):
    return Styler(df, uuid_len=0)


@pytest.fixture
def df_multi():
    return DataFrame(
        data=np.arange(16).reshape(4, 4),
        columns=MultiIndex.from_product([["A", "B"], ["a", "b"]]),
        index=MultiIndex.from_product([["X", "Y"], ["x", "y"]]),
    )


@pytest.fixture
def styler_multi(df_multi):
    return Styler(df_multi, uuid_len=0)


def test_display_format(styler):
    ctx = styler.format("{:0.1f}")._translate(True, True)
    assert all(["display_value" in c for c in row] for row in ctx["body"])
    assert all([len(c["display_value"]) <= 3 for c in row[1:]] for row in ctx["body"])
    assert len(ctx["body"][0][1]["display_value"].lstrip("-")) <= 3


@pytest.mark.parametrize("index", [True, False])
@pytest.mark.parametrize("columns", [True, False])
def test_display_format_index(styler, index, columns):
    exp_index = ["x", "y"]
    if index:
        styler.format_index(lambda v: v.upper(), axis=0)  # test callable
        exp_index = ["X", "Y"]

    exp_columns = ["A", "B"]
    if columns:
        styler.format_index("*{}*", axis=1)  # test string
        exp_columns = ["*A*", "*B*"]

    ctx = styler._translate(True, True)

    for r, row in enumerate(ctx["body"]):
        assert row[0]["display_value"] == exp_index[r]

    for c, col in enumerate(ctx["head"][1:]):
        assert col["display_value"] == exp_columns[c]


def test_format_dict(styler):
    ctx = styler.format({"A": "{:0.1f}", "B": "{0:.2%}"})._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "0.0"
    assert ctx["body"][0][2]["display_value"] == "-60.90%"


def test_format_index_dict(styler):
    ctx = styler.format_index({0: lambda v: v.upper()})._translate(True, True)
    for i, val in enumerate(["X", "Y"]):
        assert ctx["body"][i][0]["display_value"] == val


def test_format_string(styler):
    ctx = styler.format("{:.2f}")._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "0.00"
    assert ctx["body"][0][2]["display_value"] == "-0.61"
    assert ctx["body"][1][1]["display_value"] == "1.00"
    assert ctx["body"][1][2]["display_value"] == "-1.23"


def test_format_callable(styler):
    ctx = styler.format(lambda v: "neg" if v < 0 else "pos")._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "pos"
    assert ctx["body"][0][2]["display_value"] == "neg"
    assert ctx["body"][1][1]["display_value"] == "pos"
    assert ctx["body"][1][2]["display_value"] == "neg"


def test_format_with_na_rep():
    # GH 21527 28358
    df = DataFrame([[None, None], [1.1, 1.2]], columns=["A", "B"])

    ctx = df.style.format(None, na_rep="-")._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "-"
    assert ctx["body"][0][2]["display_value"] == "-"

    ctx = df.style.format("{:.2%}", na_rep="-")._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "-"
    assert ctx["body"][0][2]["display_value"] == "-"
    assert ctx["body"][1][1]["display_value"] == "110.00%"
    assert ctx["body"][1][2]["display_value"] == "120.00%"

    ctx = df.style.format("{:.2%}", na_rep="-", subset=["B"])._translate(True, True)
    assert ctx["body"][0][2]["display_value"] == "-"
    assert ctx["body"][1][2]["display_value"] == "120.00%"


def test_format_index_with_na_rep():
    df = DataFrame([[1, 2, 3, 4, 5]], columns=["A", None, np.nan, NaT, NA])
    ctx = df.style.format_index(None, na_rep="--", axis=1)._translate(True, True)
    assert ctx["head"][0][1]["display_value"] == "A"
    for i in [2, 3, 4, 5]:
        assert ctx["head"][0][i]["display_value"] == "--"


def test_format_non_numeric_na():
    # GH 21527 28358
    df = DataFrame(
        {
            "object": [None, np.nan, "foo"],
            "datetime": [None, NaT, Timestamp("20120101")],
        }
    )
    ctx = df.style.format(None, na_rep="-")._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "-"
    assert ctx["body"][0][2]["display_value"] == "-"
    assert ctx["body"][1][1]["display_value"] == "-"
    assert ctx["body"][1][2]["display_value"] == "-"


@pytest.mark.parametrize(
    "func, attr, kwargs",
    [
        ("format", "_display_funcs", {}),
        ("format_index", "_display_funcs_index", {"axis": 0}),
        ("format_index", "_display_funcs_columns", {"axis": 1}),
    ],
)
def test_format_clear(styler, func, attr, kwargs):
    assert (0, 0) not in getattr(styler, attr)  # using default
    getattr(styler, func)("{:.2f}", **kwargs)
    assert (0, 0) in getattr(styler, attr)  # formatter is specified
    getattr(styler, func)(**kwargs)
    assert (0, 0) not in getattr(styler, attr)  # formatter cleared to default


@pytest.mark.parametrize(
    "escape, exp",
    [
        ("html", "&lt;&gt;&amp;&#34;%$#_{}~^\\~ ^ \\ "),
        (
            "latex",
            '<>\\&"\\%\\$\\#\\_\\{\\}\\textasciitilde \\textasciicircum '
            "\\textbackslash \\textasciitilde \\space \\textasciicircum \\space "
            "\\textbackslash \\space ",
        ),
    ],
)
def test_format_escape_html(escape, exp):
    chars = '<>&"%$#_{}~^\\~ ^ \\ '
    df = DataFrame([[chars]])

    s = Styler(df, uuid_len=0).format("&{0}&", escape=None)
    expected = f'<td id="T__row0_col0" class="data row0 col0" >&{chars}&</td>'
    assert expected in s.to_html()

    # only the value should be escaped before passing to the formatter
    s = Styler(df, uuid_len=0).format("&{0}&", escape=escape)
    expected = f'<td id="T__row0_col0" class="data row0 col0" >&{exp}&</td>'
    assert expected in s.to_html()

    # also test format_index()
    styler = Styler(DataFrame(columns=[chars]), uuid_len=0)
    styler.format_index("&{0}&", escape=None, axis=1)
    assert styler._translate(True, True)["head"][0][1]["display_value"] == f"&{chars}&"
    styler.format_index("&{0}&", escape=escape, axis=1)
    assert styler._translate(True, True)["head"][0][1]["display_value"] == f"&{exp}&"


@pytest.mark.parametrize(
    "chars, expected",
    [
        (
            r"$ \$&%#_{}~^\ $ &%#_{}~^\ $",
            "".join(
                [
                    r"$ \$&%#_{}~^\ $ ",
                    r"\&\%\#\_\{\}\textasciitilde \textasciicircum ",
                    r"\textbackslash \space \$",
                ]
            ),
        ),
        (
            r"\( &%#_{}~^\ \) &%#_{}~^\ \(",
            "".join(
                [
                    r"\( &%#_{}~^\ \) ",
                    r"\&\%\#\_\{\}\textasciitilde \textasciicircum ",
                    r"\textbackslash \space \textbackslash (",
                ]
            ),
        ),
        (
            r"$\&%#_{}^\$",
            r"\$\textbackslash \&\%\#\_\{\}\textasciicircum \textbackslash \$",
        ),
        (
            r"$ \frac{1}{2} $ \( \frac{1}{2} \)",
            "".join(
                [
                    r"$ \frac{1}{2} $",
                    r" \textbackslash ( \textbackslash frac\{1\}\{2\} \textbackslash )",
                ]
            ),
        ),
    ],
)
def test_format_escape_latex_math(chars, expected):
    # GH 51903
    # latex-math escape works for each DataFrame cell separately. If we have
    # a combination of dollar signs and brackets, the dollar sign would apply.
    df = DataFrame([[chars]])
    s = df.style.format("{0}", escape="latex-math")
    assert s._translate(True, True)["body"][0][1]["display_value"] == expected


def test_format_escape_na_rep():
    # tests the na_rep is not escaped
    df = DataFrame([['<>&"', None]])
    s = Styler(df, uuid_len=0).format("X&{0}>X", escape="html", na_rep="&")
    ex = '<td id="T__row0_col0" class="data row0 col0" >X&&lt;&gt;&amp;&#34;>X</td>'
    expected2 = '<td id="T__row0_col1" class="data row0 col1" >&</td>'
    assert ex in s.to_html()
    assert expected2 in s.to_html()

    # also test for format_index()
    df = DataFrame(columns=['<>&"', None])
    styler = Styler(df, uuid_len=0)
    styler.format_index("X&{0}>X", escape="html", na_rep="&", axis=1)
    ctx = styler._translate(True, True)
    assert ctx["head"][0][1]["display_value"] == "X&&lt;&gt;&amp;&#34;>X"
    assert ctx["head"][0][2]["display_value"] == "&"


def test_format_escape_floats(styler):
    # test given formatter for number format is not impacted by escape
    s = styler.format("{:.1f}", escape="html")
    for expected in [">0.0<", ">1.0<", ">-1.2<", ">-0.6<"]:
        assert expected in s.to_html()
    # tests precision of floats is not impacted by escape
    s = styler.format(precision=1, escape="html")
    for expected in [">0<", ">1<", ">-1.2<", ">-0.6<"]:
        assert expected in s.to_html()


@pytest.mark.parametrize("formatter", [5, True, [2.0]])
@pytest.mark.parametrize("func", ["format", "format_index"])
def test_format_raises(styler, formatter, func):
    with pytest.raises(TypeError, match="expected str or callable"):
        getattr(styler, func)(formatter)


@pytest.mark.parametrize(
    "precision, expected",
    [
        (1, ["1.0", "2.0", "3.2", "4.6"]),
        (2, ["1.00", "2.01", "3.21", "4.57"]),
        (3, ["1.000", "2.009", "3.212", "4.566"]),
    ],
)
def test_format_with_precision(precision, expected):
    # Issue #13257
    df = DataFrame([[1.0, 2.0090, 3.2121, 4.566]], columns=[1.0, 2.0090, 3.2121, 4.566])
    styler = Styler(df)
    styler.format(precision=precision)
    styler.format_index(precision=precision, axis=1)

    ctx = styler._translate(True, True)
    for col, exp in enumerate(expected):
        assert ctx["body"][0][col + 1]["display_value"] == exp  # format test
        assert ctx["head"][0][col + 1]["display_value"] == exp  # format_index test


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize(
    "level, expected",
    [
        (0, ["X", "X", "_", "_"]),  # level int
        ("zero", ["X", "X", "_", "_"]),  # level name
        (1, ["_", "_", "X", "X"]),  # other level int
        ("one", ["_", "_", "X", "X"]),  # other level name
        ([0, 1], ["X", "X", "X", "X"]),  # both levels
        ([0, "zero"], ["X", "X", "_", "_"]),  # level int and name simultaneous
        ([0, "one"], ["X", "X", "X", "X"]),  # both levels as int and name
        (["one", "zero"], ["X", "X", "X", "X"]),  # both level names, reversed
    ],
)
def test_format_index_level(axis, level, expected):
    midx = MultiIndex.from_arrays([["_", "_"], ["_", "_"]], names=["zero", "one"])
    df = DataFrame([[1, 2], [3, 4]])
    if axis == 0:
        df.index = midx
    else:
        df.columns = midx

    styler = df.style.format_index(lambda v: "X", level=level, axis=axis)
    ctx = styler._translate(True, True)

    if axis == 0:  # compare index
        result = [ctx["body"][s][0]["display_value"] for s in range(2)]
        result += [ctx["body"][s][1]["display_value"] for s in range(2)]
    else:  # compare columns
        result = [ctx["head"][0][s + 1]["display_value"] for s in range(2)]
        result += [ctx["head"][1][s + 1]["display_value"] for s in range(2)]

    assert expected == result


def test_format_subset():
    df = DataFrame([[0.1234, 0.1234], [1.1234, 1.1234]], columns=["a", "b"])
    ctx = df.style.format(
        {"a": "{:0.1f}", "b": "{0:.2%}"}, subset=IndexSlice[0, :]
    )._translate(True, True)
    expected = "0.1"
    raw_11 = "1.123400"
    assert ctx["body"][0][1]["display_value"] == expected
    assert ctx["body"][1][1]["display_value"] == raw_11
    assert ctx["body"][0][2]["display_value"] == "12.34%"

    ctx = df.style.format("{:0.1f}", subset=IndexSlice[0, :])._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == expected
    assert ctx["body"][1][1]["display_value"] == raw_11

    ctx = df.style.format("{:0.1f}", subset=IndexSlice["a"])._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == expected
    assert ctx["body"][0][2]["display_value"] == "0.123400"

    ctx = df.style.format("{:0.1f}", subset=IndexSlice[0, "a"])._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == expected
    assert ctx["body"][1][1]["display_value"] == raw_11

    ctx = df.style.format("{:0.1f}", subset=IndexSlice[[0, 1], ["a"]])._translate(
        True, True
    )
    assert ctx["body"][0][1]["display_value"] == expected
    assert ctx["body"][1][1]["display_value"] == "1.1"
    assert ctx["body"][0][2]["display_value"] == "0.123400"
    assert ctx["body"][1][2]["display_value"] == raw_11


@pytest.mark.parametrize("formatter", [None, "{:,.1f}"])
@pytest.mark.parametrize("decimal", [".", "*"])
@pytest.mark.parametrize("precision", [None, 2])
@pytest.mark.parametrize("func, col", [("format", 1), ("format_index", 0)])
def test_format_thousands(formatter, decimal, precision, func, col):
    styler = DataFrame([[1000000.123456789]], index=[1000000.123456789]).style
    result = getattr(styler, func)(  # testing float
        thousands="_", formatter=formatter, decimal=decimal, precision=precision
    )._translate(True, True)
    assert "1_000_000" in result["body"][0][col]["display_value"]

    styler = DataFrame([[1000000]], index=[1000000]).style
    result = getattr(styler, func)(  # testing int
        thousands="_", formatter=formatter, decimal=decimal, precision=precision
    )._translate(True, True)
    assert "1_000_000" in result["body"][0][col]["display_value"]

    styler = DataFrame([[1 + 1000000.123456789j]], index=[1 + 1000000.123456789j]).style
    result = getattr(styler, func)(  # testing complex
        thousands="_", formatter=formatter, decimal=decimal, precision=precision
    )._translate(True, True)
    assert "1_000_000" in result["body"][0][col]["display_value"]


@pytest.mark.parametrize("formatter", [None, "{:,.4f}"])
@pytest.mark.parametrize("thousands", [None, ",", "*"])
@pytest.mark.parametrize("precision", [None, 4])
@pytest.mark.parametrize("func, col", [("format", 1), ("format_index", 0)])
def test_format_decimal(formatter, thousands, precision, func, col):
    styler = DataFrame([[1000000.123456789]], index=[1000000.123456789]).style
    result = getattr(styler, func)(  # testing float
        decimal="_", formatter=formatter, thousands=thousands, precision=precision
    )._translate(True, True)
    assert "000_123" in result["body"][0][col]["display_value"]

    styler = DataFrame([[1 + 1000000.123456789j]], index=[1 + 1000000.123456789j]).style
    result = getattr(styler, func)(  # testing complex
        decimal="_", formatter=formatter, thousands=thousands, precision=precision
    )._translate(True, True)
    assert "000_123" in result["body"][0][col]["display_value"]


def test_str_escape_error():
    msg = "`escape` only permitted in {'html', 'latex', 'latex-math'}, got "
    with pytest.raises(ValueError, match=msg):
        _str_escape("text", "bad_escape")

    with pytest.raises(ValueError, match=msg):
        _str_escape("text", [])

    _str_escape(2.00, "bad_escape")  # OK since dtype is float


def test_long_int_formatting():
    df = DataFrame(data=[[1234567890123456789]], columns=["test"])
    styler = df.style
    ctx = styler._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "1234567890123456789"

    styler = df.style.format(thousands="_")
    ctx = styler._translate(True, True)
    assert ctx["body"][0][1]["display_value"] == "1_234_567_890_123_456_789"


def test_format_options():
    df = DataFrame({"int": [2000, 1], "float": [1.009, None], "str": ["&<", "&~"]})
    ctx = df.style._translate(True, True)

    # test option: na_rep
    assert ctx["body"][1][2]["display_value"] == "nan"
    with option_context("styler.format.na_rep", "MISSING"):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][1][2]["display_value"] == "MISSING"

    # test option: decimal and precision
    assert ctx["body"][0][2]["display_value"] == "1.009000"
    with option_context("styler.format.decimal", "_"):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][0][2]["display_value"] == "1_009000"
    with option_context("styler.format.precision", 2):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][0][2]["display_value"] == "1.01"

    # test option: thousands
    assert ctx["body"][0][1]["display_value"] == "2000"
    with option_context("styler.format.thousands", "_"):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][0][1]["display_value"] == "2_000"

    # test option: escape
    assert ctx["body"][0][3]["display_value"] == "&<"
    assert ctx["body"][1][3]["display_value"] == "&~"
    with option_context("styler.format.escape", "html"):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][0][3]["display_value"] == "&amp;&lt;"
    with option_context("styler.format.escape", "latex"):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][1][3]["display_value"] == "\\&\\textasciitilde "
    with option_context("styler.format.escape", "latex-math"):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][1][3]["display_value"] == "\\&\\textasciitilde "

    # test option: formatter
    with option_context("styler.format.formatter", {"int": "{:,.2f}"}):
        ctx_with_op = df.style._translate(True, True)
        assert ctx_with_op["body"][0][1]["display_value"] == "2,000.00"


def test_precision_zero(df):
    styler = Styler(df, precision=0)
    ctx = styler._translate(True, True)
    assert ctx["body"][0][2]["display_value"] == "-1"
    assert ctx["body"][1][2]["display_value"] == "-1"


@pytest.mark.parametrize(
    "formatter, exp",
    [
        (lambda x: f"{x:.3f}", "9.000"),
        ("{:.2f}", "9.00"),
        ({0: "{:.1f}"}, "9.0"),
        (None, "9"),
    ],
)
def test_formatter_options_validator(formatter, exp):
    df = DataFrame([[9]])
    with option_context("styler.format.formatter", formatter):
        assert f" {exp} " in df.style.to_latex()


def test_formatter_options_raises():
    msg = "Value must be an instance of"
    with pytest.raises(ValueError, match=msg):
        with option_context("styler.format.formatter", ["bad", "type"]):
            DataFrame().style.to_latex()


def test_1level_multiindex():
    # GH 43383
    midx = MultiIndex.from_product([[1, 2]], names=[""])
    df = DataFrame(-1, index=midx, columns=[0, 1])
    ctx = df.style._translate(True, True)
    assert ctx["body"][0][0]["display_value"] == "1"
    assert ctx["body"][0][0]["is_visible"] is True
    assert ctx["body"][1][0]["display_value"] == "2"
    assert ctx["body"][1][0]["is_visible"] is True


def test_boolean_format():
    # gh 46384: booleans do not collapse to integer representation on display
    df = DataFrame([[True, False]])
    ctx = df.style._translate(True, True)
    assert ctx["body"][0][1]["display_value"] is True
    assert ctx["body"][0][2]["display_value"] is False


@pytest.mark.parametrize(
    "hide, labels",
    [
        (False, [1, 2]),
        (True, [1, 2, 3, 4]),
    ],
)
def test_relabel_raise_length(styler_multi, hide, labels):
    if hide:
        styler_multi.hide(axis=0, subset=[("X", "x"), ("Y", "y")])
    with pytest.raises(ValueError, match="``labels`` must be of length equal"):
        styler_multi.relabel_index(labels=labels)


def test_relabel_index(styler_multi):
    labels = [(1, 2), (3, 4)]
    styler_multi.hide(axis=0, subset=[("X", "x"), ("Y", "y")])
    styler_multi.relabel_index(labels=labels)
    ctx = styler_multi._translate(True, True)
    assert {"value": "X", "display_value": 1}.items() <= ctx["body"][0][0].items()
    assert {"value": "y", "display_value": 2}.items() <= ctx["body"][0][1].items()
    assert {"value": "Y", "display_value": 3}.items() <= ctx["body"][1][0].items()
    assert {"value": "x", "display_value": 4}.items() <= ctx["body"][1][1].items()


def test_relabel_columns(styler_multi):
    labels = [(1, 2), (3, 4)]
    styler_multi.hide(axis=1, subset=[("A", "a"), ("B", "b")])
    styler_multi.relabel_index(axis=1, labels=labels)
    ctx = styler_multi._translate(True, True)
    assert {"value": "A", "display_value": 1}.items() <= ctx["head"][0][3].items()
    assert {"value": "B", "display_value": 3}.items() <= ctx["head"][0][4].items()
    assert {"value": "b", "display_value": 2}.items() <= ctx["head"][1][3].items()
    assert {"value": "a", "display_value": 4}.items() <= ctx["head"][1][4].items()


def test_relabel_roundtrip(styler):
    styler.relabel_index(["{}", "{}"])
    ctx = styler._translate(True, True)
    assert {"value": "x", "display_value": "x"}.items() <= ctx["body"][0][0].items()
    assert {"value": "y", "display_value": "y"}.items() <= ctx["body"][1][0].items()
