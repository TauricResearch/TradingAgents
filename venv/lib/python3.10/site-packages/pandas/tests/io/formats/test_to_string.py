from datetime import (
    datetime,
    timedelta,
)
from io import StringIO
import re
import sys
from textwrap import dedent

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas import (
    CategoricalIndex,
    DataFrame,
    Index,
    NaT,
    Series,
    Timestamp,
    concat,
    date_range,
    get_option,
    option_context,
    read_csv,
    timedelta_range,
    to_datetime,
)
import pandas._testing as tm


def _three_digit_exp():
    return f"{1.7e8:.4g}" == "1.7e+008"


class TestDataFrameToStringFormatters:
    def test_to_string_masked_ea_with_formatter(self):
        # GH#39336
        df = DataFrame(
            {
                "a": Series([0.123456789, 1.123456789], dtype="Float64"),
                "b": Series([1, 2], dtype="Int64"),
            }
        )
        result = df.to_string(formatters=["{:.2f}".format, "{:.2f}".format])
        expected = dedent(
            """\
                  a     b
            0  0.12  1.00
            1  1.12  2.00"""
        )
        assert result == expected

    def test_to_string_with_formatters(self):
        df = DataFrame(
            {
                "int": [1, 2, 3],
                "float": [1.0, 2.0, 3.0],
                "object": [(1, 2), True, False],
            },
            columns=["int", "float", "object"],
        )

        formatters = [
            ("int", lambda x: f"0x{x:x}"),
            ("float", lambda x: f"[{x: 4.1f}]"),
            ("object", lambda x: f"-{x!s}-"),
        ]
        result = df.to_string(formatters=dict(formatters))
        result2 = df.to_string(formatters=list(zip(*formatters))[1])
        assert result == (
            "  int  float    object\n"
            "0 0x1 [ 1.0]  -(1, 2)-\n"
            "1 0x2 [ 2.0]    -True-\n"
            "2 0x3 [ 3.0]   -False-"
        )
        assert result == result2

    def test_to_string_with_datetime64_monthformatter(self):
        months = [datetime(2016, 1, 1), datetime(2016, 2, 2)]
        x = DataFrame({"months": months})

        def format_func(x):
            return x.strftime("%Y-%m")

        result = x.to_string(formatters={"months": format_func})
        expected = dedent(
            """\
            months
            0 2016-01
            1 2016-02"""
        )
        assert result.strip() == expected

    def test_to_string_with_datetime64_hourformatter(self):
        x = DataFrame(
            {"hod": to_datetime(["10:10:10.100", "12:12:12.120"], format="%H:%M:%S.%f")}
        )

        def format_func(x):
            return x.strftime("%H:%M")

        result = x.to_string(formatters={"hod": format_func})
        expected = dedent(
            """\
            hod
            0 10:10
            1 12:12"""
        )
        assert result.strip() == expected

    def test_to_string_with_formatters_unicode(self):
        df = DataFrame({"c/\u03c3": [1, 2, 3]})
        result = df.to_string(formatters={"c/\u03c3": str})
        expected = dedent(
            """\
              c/\u03c3
            0   1
            1   2
            2   3"""
        )
        assert result == expected

        def test_to_string_index_formatter(self):
            df = DataFrame([range(5), range(5, 10), range(10, 15)])

            rs = df.to_string(formatters={"__index__": lambda x: "abc"[x]})

            xp = dedent(
                """\
                0   1   2   3   4
            a   0   1   2   3   4
            b   5   6   7   8   9
            c  10  11  12  13  14\
            """
            )
            assert rs == xp

    def test_no_extra_space(self):
        # GH#52690: Check that no extra space is given
        col1 = "TEST"
        col2 = "PANDAS"
        col3 = "to_string"
        expected = f"{col1:<6s} {col2:<7s} {col3:<10s}"
        df = DataFrame([{"col1": "TEST", "col2": "PANDAS", "col3": "to_string"}])
        d = {"col1": "{:<6s}".format, "col2": "{:<7s}".format, "col3": "{:<10s}".format}
        result = df.to_string(index=False, header=False, formatters=d)
        assert result == expected


class TestDataFrameToStringColSpace:
    def test_to_string_with_column_specific_col_space_raises(self):
        df = DataFrame(
            np.random.default_rng(2).random(size=(3, 3)), columns=["a", "b", "c"]
        )

        msg = (
            "Col_space length\\(\\d+\\) should match "
            "DataFrame number of columns\\(\\d+\\)"
        )
        with pytest.raises(ValueError, match=msg):
            df.to_string(col_space=[30, 40])

        with pytest.raises(ValueError, match=msg):
            df.to_string(col_space=[30, 40, 50, 60])

        msg = "unknown column"
        with pytest.raises(ValueError, match=msg):
            df.to_string(col_space={"a": "foo", "b": 23, "d": 34})

    def test_to_string_with_column_specific_col_space(self):
        df = DataFrame(
            np.random.default_rng(2).random(size=(3, 3)), columns=["a", "b", "c"]
        )

        result = df.to_string(col_space={"a": 10, "b": 11, "c": 12})
        # 3 separating space + each col_space for (id, a, b, c)
        assert len(result.split("\n")[1]) == (3 + 1 + 10 + 11 + 12)

        result = df.to_string(col_space=[10, 11, 12])
        assert len(result.split("\n")[1]) == (3 + 1 + 10 + 11 + 12)

    def test_to_string_with_col_space(self):
        df = DataFrame(np.random.default_rng(2).random(size=(1, 3)))
        c10 = len(df.to_string(col_space=10).split("\n")[1])
        c20 = len(df.to_string(col_space=20).split("\n")[1])
        c30 = len(df.to_string(col_space=30).split("\n")[1])
        assert c10 < c20 < c30

        # GH#8230
        # col_space wasn't being applied with header=False
        with_header = df.to_string(col_space=20)
        with_header_row1 = with_header.splitlines()[1]
        no_header = df.to_string(col_space=20, header=False)
        assert len(with_header_row1) == len(no_header)

    def test_to_string_repr_tuples(self):
        buf = StringIO()

        df = DataFrame({"tups": list(zip(range(10), range(10)))})
        repr(df)
        df.to_string(col_space=10, buf=buf)


class TestDataFrameToStringHeader:
    def test_to_string_header_false(self):
        # GH#49230
        df = DataFrame([1, 2])
        df.index.name = "a"
        s = df.to_string(header=False)
        expected = "a   \n0  1\n1  2"
        assert s == expected

        df = DataFrame([[1, 2], [3, 4]])
        df.index.name = "a"
        s = df.to_string(header=False)
        expected = "a      \n0  1  2\n1  3  4"
        assert s == expected

    def test_to_string_multindex_header(self):
        # GH#16718
        df = DataFrame({"a": [0], "b": [1], "c": [2], "d": [3]}).set_index(["a", "b"])
        res = df.to_string(header=["r1", "r2"])
        exp = "    r1 r2\na b      \n0 1  2  3"
        assert res == exp

    def test_to_string_no_header(self):
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        df_s = df.to_string(header=False)
        expected = "0  1  4\n1  2  5\n2  3  6"

        assert df_s == expected

    def test_to_string_specified_header(self):
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        df_s = df.to_string(header=["X", "Y"])
        expected = "   X  Y\n0  1  4\n1  2  5\n2  3  6"

        assert df_s == expected

        msg = "Writing 2 cols but got 1 aliases"
        with pytest.raises(ValueError, match=msg):
            df.to_string(header=["X"])


class TestDataFrameToStringLineWidth:
    def test_to_string_line_width(self):
        df = DataFrame(123, index=range(10, 15), columns=range(30))
        lines = df.to_string(line_width=80)
        assert max(len(line) for line in lines.split("\n")) == 80

    def test_to_string_line_width_no_index(self):
        # GH#13998, GH#22505
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1, index=False)
        expected = " x  \\\n 1   \n 2   \n 3   \n\n y  \n 4  \n 5  \n 6  "

        assert df_s == expected

        df = DataFrame({"x": [11, 22, 33], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1, index=False)
        expected = " x  \\\n11   \n22   \n33   \n\n y  \n 4  \n 5  \n 6  "

        assert df_s == expected

        df = DataFrame({"x": [11, 22, -33], "y": [4, 5, -6]})

        df_s = df.to_string(line_width=1, index=False)
        expected = "  x  \\\n 11   \n 22   \n-33   \n\n y  \n 4  \n 5  \n-6  "

        assert df_s == expected

    def test_to_string_line_width_no_header(self):
        # GH#53054
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1, header=False)
        expected = "0  1  \\\n1  2   \n2  3   \n\n0  4  \n1  5  \n2  6  "

        assert df_s == expected

        df = DataFrame({"x": [11, 22, 33], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1, header=False)
        expected = "0  11  \\\n1  22   \n2  33   \n\n0  4  \n1  5  \n2  6  "

        assert df_s == expected

        df = DataFrame({"x": [11, 22, -33], "y": [4, 5, -6]})

        df_s = df.to_string(line_width=1, header=False)
        expected = "0  11  \\\n1  22   \n2 -33   \n\n0  4  \n1  5  \n2 -6  "

        assert df_s == expected

    def test_to_string_line_width_with_both_index_and_header(self):
        # GH#53054
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1)
        expected = (
            "   x  \\\n0  1   \n1  2   \n2  3   \n\n   y  \n0  4  \n1  5  \n2  6  "
        )

        assert df_s == expected

        df = DataFrame({"x": [11, 22, 33], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1)
        expected = (
            "    x  \\\n0  11   \n1  22   \n2  33   \n\n   y  \n0  4  \n1  5  \n2  6  "
        )

        assert df_s == expected

        df = DataFrame({"x": [11, 22, -33], "y": [4, 5, -6]})

        df_s = df.to_string(line_width=1)
        expected = (
            "    x  \\\n0  11   \n1  22   \n2 -33   \n\n   y  \n0  4  \n1  5  \n2 -6  "
        )

        assert df_s == expected

    def test_to_string_line_width_no_index_no_header(self):
        # GH#53054
        df = DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1, index=False, header=False)
        expected = "1  \\\n2   \n3   \n\n4  \n5  \n6  "

        assert df_s == expected

        df = DataFrame({"x": [11, 22, 33], "y": [4, 5, 6]})

        df_s = df.to_string(line_width=1, index=False, header=False)
        expected = "11  \\\n22   \n33   \n\n4  \n5  \n6  "

        assert df_s == expected

        df = DataFrame({"x": [11, 22, -33], "y": [4, 5, -6]})

        df_s = df.to_string(line_width=1, index=False, header=False)
        expected = " 11  \\\n 22   \n-33   \n\n 4  \n 5  \n-6  "

        assert df_s == expected


class TestToStringNumericFormatting:
    def test_to_string_float_format_no_fixed_width(self):
        # GH#21625
        df = DataFrame({"x": [0.19999]})
        expected = "      x\n0 0.200"
        assert df.to_string(float_format="%.3f") == expected

        # GH#22270
        df = DataFrame({"x": [100.0]})
        expected = "    x\n0 100"
        assert df.to_string(float_format="%.0f") == expected

    def test_to_string_small_float_values(self):
        df = DataFrame({"a": [1.5, 1e-17, -5.5e-7]})

        result = df.to_string()
        # sadness per above
        if _three_digit_exp():
            expected = (
                "               a\n"
                "0  1.500000e+000\n"
                "1  1.000000e-017\n"
                "2 -5.500000e-007"
            )
        else:
            expected = (
                "              a\n"
                "0  1.500000e+00\n"
                "1  1.000000e-17\n"
                "2 -5.500000e-07"
            )
        assert result == expected

        # but not all exactly zero
        df = df * 0
        result = df.to_string()
        expected = "   0\n0  0\n1  0\n2 -0"
        # TODO: assert that these match??

    def test_to_string_complex_float_formatting(self):
        # GH #25514, 25745
        with option_context("display.precision", 5):
            df = DataFrame(
                {
                    "x": [
                        (0.4467846931321966 + 0.0715185102060818j),
                        (0.2739442392974528 + 0.23515228785438969j),
                        (0.26974928742135185 + 0.3250604054898979j),
                        (-1j),
                    ]
                }
            )
            result = df.to_string()
            expected = (
                "                  x\n0  0.44678+0.07152j\n"
                "1  0.27394+0.23515j\n"
                "2  0.26975+0.32506j\n"
                "3 -0.00000-1.00000j"
            )
            assert result == expected

    def test_to_string_format_inf(self):
        # GH#24861
        df = DataFrame(
            {
                "A": [-np.inf, np.inf, -1, -2.1234, 3, 4],
                "B": [-np.inf, np.inf, "foo", "foooo", "fooooo", "bar"],
            }
        )
        result = df.to_string()

        expected = (
            "        A       B\n"
            "0    -inf    -inf\n"
            "1     inf     inf\n"
            "2 -1.0000     foo\n"
            "3 -2.1234   foooo\n"
            "4  3.0000  fooooo\n"
            "5  4.0000     bar"
        )
        assert result == expected

        df = DataFrame(
            {
                "A": [-np.inf, np.inf, -1.0, -2.0, 3.0, 4.0],
                "B": [-np.inf, np.inf, "foo", "foooo", "fooooo", "bar"],
            }
        )
        result = df.to_string()

        expected = (
            "     A       B\n"
            "0 -inf    -inf\n"
            "1  inf     inf\n"
            "2 -1.0     foo\n"
            "3 -2.0   foooo\n"
            "4  3.0  fooooo\n"
            "5  4.0     bar"
        )
        assert result == expected

    def test_to_string_int_formatting(self):
        df = DataFrame({"x": [-15, 20, 25, -35]})
        assert issubclass(df["x"].dtype.type, np.integer)

        output = df.to_string()
        expected = "    x\n0 -15\n1  20\n2  25\n3 -35"
        assert output == expected

    def test_to_string_float_formatting(self):
        with option_context(
            "display.precision",
            5,
            "display.notebook_repr_html",
            False,
        ):
            df = DataFrame(
                {"x": [0, 0.25, 3456.000, 12e45, 1.64e6, 1.7e8, 1.253456, np.pi, -1e6]}
            )

            df_s = df.to_string()

            if _three_digit_exp():
                expected = (
                    "              x\n0  0.00000e+000\n1  2.50000e-001\n"
                    "2  3.45600e+003\n3  1.20000e+046\n4  1.64000e+006\n"
                    "5  1.70000e+008\n6  1.25346e+000\n7  3.14159e+000\n"
                    "8 -1.00000e+006"
                )
            else:
                expected = (
                    "             x\n0  0.00000e+00\n1  2.50000e-01\n"
                    "2  3.45600e+03\n3  1.20000e+46\n4  1.64000e+06\n"
                    "5  1.70000e+08\n6  1.25346e+00\n7  3.14159e+00\n"
                    "8 -1.00000e+06"
                )
            assert df_s == expected

            df = DataFrame({"x": [3234, 0.253]})
            df_s = df.to_string()

            expected = "          x\n0  3234.000\n1     0.253"
            assert df_s == expected

        assert get_option("display.precision") == 6

        df = DataFrame({"x": [1e9, 0.2512]})
        df_s = df.to_string()

        if _three_digit_exp():
            expected = "               x\n0  1.000000e+009\n1  2.512000e-001"
        else:
            expected = "              x\n0  1.000000e+09\n1  2.512000e-01"
        assert df_s == expected


class TestDataFrameToString:
    def test_to_string_decimal(self):
        # GH#23614
        df = DataFrame({"A": [6.0, 3.1, 2.2]})
        expected = "     A\n0  6,0\n1  3,1\n2  2,2"
        assert df.to_string(decimal=",") == expected

    def test_to_string_left_justify_cols(self):
        df = DataFrame({"x": [3234, 0.253]})
        df_s = df.to_string(justify="left")
        expected = "   x       \n0  3234.000\n1     0.253"
        assert df_s == expected

    def test_to_string_format_na(self):
        df = DataFrame(
            {
                "A": [np.nan, -1, -2.1234, 3, 4],
                "B": [np.nan, "foo", "foooo", "fooooo", "bar"],
            }
        )
        result = df.to_string()

        expected = (
            "        A       B\n"
            "0     NaN     NaN\n"
            "1 -1.0000     foo\n"
            "2 -2.1234   foooo\n"
            "3  3.0000  fooooo\n"
            "4  4.0000     bar"
        )
        assert result == expected

        df = DataFrame(
            {
                "A": [np.nan, -1.0, -2.0, 3.0, 4.0],
                "B": [np.nan, "foo", "foooo", "fooooo", "bar"],
            }
        )
        result = df.to_string()

        expected = (
            "     A       B\n"
            "0  NaN     NaN\n"
            "1 -1.0     foo\n"
            "2 -2.0   foooo\n"
            "3  3.0  fooooo\n"
            "4  4.0     bar"
        )
        assert result == expected

    def test_to_string_with_dict_entries(self):
        df = DataFrame({"A": [{"a": 1, "b": 2}]})

        val = df.to_string()
        assert "'a': 1" in val
        assert "'b': 2" in val

    def test_to_string_with_categorical_columns(self):
        # GH#35439
        data = [[4, 2], [3, 2], [4, 3]]
        cols = ["aaaaaaaaa", "b"]
        df = DataFrame(data, columns=cols)
        df_cat_cols = DataFrame(data, columns=CategoricalIndex(cols))

        assert df.to_string() == df_cat_cols.to_string()

    def test_repr_embedded_ndarray(self):
        arr = np.empty(10, dtype=[("err", object)])
        for i in range(len(arr)):
            arr["err"][i] = np.random.default_rng(2).standard_normal(i)

        df = DataFrame(arr)
        repr(df["err"])
        repr(df)
        df.to_string()

    def test_to_string_truncate(self):
        # GH 9784 - dont truncate when calling DataFrame.to_string
        df = DataFrame(
            [
                {
                    "a": "foo",
                    "b": "bar",
                    "c": "let's make this a very VERY long line that is longer "
                    "than the default 50 character limit",
                    "d": 1,
                },
                {"a": "foo", "b": "bar", "c": "stuff", "d": 1},
            ]
        )
        df.set_index(["a", "b", "c"])
        assert df.to_string() == (
            "     a    b                                         "
            "                                                c  d\n"
            "0  foo  bar  let's make this a very VERY long line t"
            "hat is longer than the default 50 character limit  1\n"
            "1  foo  bar                                         "
            "                                            stuff  1"
        )
        with option_context("max_colwidth", 20):
            # the display option has no effect on the to_string method
            assert df.to_string() == (
                "     a    b                                         "
                "                                                c  d\n"
                "0  foo  bar  let's make this a very VERY long line t"
                "hat is longer than the default 50 character limit  1\n"
                "1  foo  bar                                         "
                "                                            stuff  1"
            )
        assert df.to_string(max_colwidth=20) == (
            "     a    b                    c  d\n"
            "0  foo  bar  let's make this ...  1\n"
            "1  foo  bar                stuff  1"
        )

    @pytest.mark.parametrize(
        "input_array, expected",
        [
            ({"A": ["a"]}, "A\na"),
            ({"A": ["a", "b"], "B": ["c", "dd"]}, "A  B\na  c\nb dd"),
            ({"A": ["a", 1], "B": ["aa", 1]}, "A  B\na aa\n1  1"),
        ],
    )
    def test_format_remove_leading_space_dataframe(self, input_array, expected):
        # GH#24980
        df = DataFrame(input_array).to_string(index=False)
        assert df == expected

    @pytest.mark.parametrize(
        "data,expected",
        [
            (
                {"col1": [1, 2], "col2": [3, 4]},
                "   col1  col2\n0     1     3\n1     2     4",
            ),
            (
                {"col1": ["Abc", 0.756], "col2": [np.nan, 4.5435]},
                "    col1    col2\n0    Abc     NaN\n1  0.756  4.5435",
            ),
            (
                {"col1": [np.nan, "a"], "col2": [0.009, 3.543], "col3": ["Abc", 23]},
                "  col1   col2 col3\n0  NaN  0.009  Abc\n1    a  3.543   23",
            ),
        ],
    )
    def test_to_string_max_rows_zero(self, data, expected):
        # GH#35394
        result = DataFrame(data=data).to_string(max_rows=0)
        assert result == expected

    @pytest.mark.parametrize(
        "max_cols, max_rows, expected",
        [
            (
                10,
                None,
                " 0   1   2   3   4   ...  6   7   8   9   10\n"
                "  0   0   0   0   0  ...   0   0   0   0   0\n"
                "  0   0   0   0   0  ...   0   0   0   0   0\n"
                "  0   0   0   0   0  ...   0   0   0   0   0\n"
                "  0   0   0   0   0  ...   0   0   0   0   0",
            ),
            (
                None,
                2,
                " 0   1   2   3   4   5   6   7   8   9   10\n"
                "  0   0   0   0   0   0   0   0   0   0   0\n"
                " ..  ..  ..  ..  ..  ..  ..  ..  ..  ..  ..\n"
                "  0   0   0   0   0   0   0   0   0   0   0",
            ),
            (
                10,
                2,
                " 0   1   2   3   4   ...  6   7   8   9   10\n"
                "  0   0   0   0   0  ...   0   0   0   0   0\n"
                " ..  ..  ..  ..  ..  ...  ..  ..  ..  ..  ..\n"
                "  0   0   0   0   0  ...   0   0   0   0   0",
            ),
            (
                9,
                2,
                " 0   1   2   3   ...  7   8   9   10\n"
                "  0   0   0   0  ...   0   0   0   0\n"
                " ..  ..  ..  ..  ...  ..  ..  ..  ..\n"
                "  0   0   0   0  ...   0   0   0   0",
            ),
            (
                1,
                1,
                " 0  ...\n 0  ...\n..  ...",
            ),
        ],
    )
    def test_truncation_no_index(self, max_cols, max_rows, expected):
        df = DataFrame([[0] * 11] * 4)
        assert (
            df.to_string(index=False, max_cols=max_cols, max_rows=max_rows) == expected
        )

    def test_to_string_no_index(self):
        # GH#16839, GH#13032
        df = DataFrame({"x": [11, 22], "y": [33, -44], "z": ["AAA", "   "]})

        df_s = df.to_string(index=False)
        # Leading space is expected for positive numbers.
        expected = " x   y   z\n11  33 AAA\n22 -44    "
        assert df_s == expected

        df_s = df[["y", "x", "z"]].to_string(index=False)
        expected = "  y  x   z\n 33 11 AAA\n-44 22    "
        assert df_s == expected

    def test_to_string_unicode_columns(self, float_frame):
        df = DataFrame({"\u03c3": np.arange(10.0)})

        buf = StringIO()
        df.to_string(buf=buf)
        buf.getvalue()

        buf = StringIO()
        df.info(buf=buf)
        buf.getvalue()

        result = float_frame.to_string()
        assert isinstance(result, str)

    @pytest.mark.parametrize("na_rep", ["NaN", "Ted"])
    def test_to_string_na_rep_and_float_format(self, na_rep):
        # GH#13828
        df = DataFrame([["A", 1.2225], ["A", None]], columns=["Group", "Data"])
        result = df.to_string(na_rep=na_rep, float_format="{:.2f}".format)
        expected = dedent(
            f"""\
               Group  Data
             0     A  1.22
             1     A   {na_rep}"""
        )
        assert result == expected

    def test_to_string_string_dtype(self):
        # GH#50099
        pytest.importorskip("pyarrow")
        df = DataFrame(
            {"x": ["foo", "bar", "baz"], "y": ["a", "b", "c"], "z": [1, 2, 3]}
        )
        df = df.astype(
            {"x": "string[pyarrow]", "y": "string[python]", "z": "int64[pyarrow]"}
        )
        result = df.dtypes.to_string()
        expected = dedent(
            """\
            x    string[pyarrow]
            y     string[python]
            z     int64[pyarrow]"""
        )
        assert result == expected

    def test_to_string_pos_args_deprecation(self):
        # GH#54229
        df = DataFrame({"a": [1, 2, 3]})
        msg = (
            "Starting with pandas version 3.0 all arguments of to_string "
            "except for the "
            "argument 'buf' will be keyword-only."
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            buf = StringIO()
            df.to_string(buf, None, None, True, True)

    def test_to_string_utf8_columns(self):
        n = "\u05d0".encode()
        df = DataFrame([1, 2], columns=[n])

        with option_context("display.max_rows", 1):
            repr(df)

    def test_to_string_unicode_two(self):
        dm = DataFrame({"c/\u03c3": []})
        buf = StringIO()
        dm.to_string(buf)

    def test_to_string_unicode_three(self):
        dm = DataFrame(["\xc2"])
        buf = StringIO()
        dm.to_string(buf)

    def test_to_string_with_float_index(self):
        index = Index([1.5, 2, 3, 4, 5])
        df = DataFrame(np.arange(5), index=index)

        result = df.to_string()
        expected = "     0\n1.5  0\n2.0  1\n3.0  2\n4.0  3\n5.0  4"
        assert result == expected

    def test_to_string(self):
        # big mixed
        biggie = DataFrame(
            {
                "A": np.random.default_rng(2).standard_normal(200),
                "B": Index([f"{i}?!" for i in range(200)]),
            },
        )

        biggie.loc[:20, "A"] = np.nan
        biggie.loc[:20, "B"] = np.nan
        s = biggie.to_string()

        buf = StringIO()
        retval = biggie.to_string(buf=buf)
        assert retval is None
        assert buf.getvalue() == s

        assert isinstance(s, str)

        # print in right order
        result = biggie.to_string(
            columns=["B", "A"], col_space=17, float_format="%.5f".__mod__
        )
        lines = result.split("\n")
        header = lines[0].strip().split()
        joined = "\n".join([re.sub(r"\s+", " ", x).strip() for x in lines[1:]])
        recons = read_csv(StringIO(joined), names=header, header=None, sep=" ")
        tm.assert_series_equal(recons["B"], biggie["B"])
        assert recons["A"].count() == biggie["A"].count()
        assert (np.abs(recons["A"].dropna() - biggie["A"].dropna()) < 0.1).all()

        # FIXME: don't leave commented-out
        # expected = ['B', 'A']
        # assert header == expected

        result = biggie.to_string(columns=["A"], col_space=17)
        header = result.split("\n")[0].strip().split()
        expected = ["A"]
        assert header == expected

        biggie.to_string(columns=["B", "A"], formatters={"A": lambda x: f"{x:.1f}"})

        biggie.to_string(columns=["B", "A"], float_format=str)
        biggie.to_string(columns=["B", "A"], col_space=12, float_format=str)

        frame = DataFrame(index=np.arange(200))
        frame.to_string()

    # TODO: split or simplify this test?
    @pytest.mark.xfail(using_string_dtype(), reason="fix when arrow is default")
    def test_to_string_index_with_nan(self):
        # GH#2850
        df = DataFrame(
            {
                "id1": {0: "1a3", 1: "9h4"},
                "id2": {0: np.nan, 1: "d67"},
                "id3": {0: "78d", 1: "79d"},
                "value": {0: 123, 1: 64},
            }
        )

        # multi-index
        y = df.set_index(["id1", "id2", "id3"])
        result = y.to_string()
        expected = (
            "             value\nid1 id2 id3       \n"
            "1a3 NaN 78d    123\n9h4 d67 79d     64"
        )
        assert result == expected

        # index
        y = df.set_index("id2")
        result = y.to_string()
        expected = (
            "     id1  id3  value\nid2                 \n"
            "NaN  1a3  78d    123\nd67  9h4  79d     64"
        )
        assert result == expected

        # with append (this failed in 0.12)
        y = df.set_index(["id1", "id2"]).set_index("id3", append=True)
        result = y.to_string()
        expected = (
            "             value\nid1 id2 id3       \n"
            "1a3 NaN 78d    123\n9h4 d67 79d     64"
        )
        assert result == expected

        # all-nan in mi
        df2 = df.copy()
        df2.loc[:, "id2"] = np.nan
        y = df2.set_index("id2")
        result = y.to_string()
        expected = (
            "     id1  id3  value\nid2                 \n"
            "NaN  1a3  78d    123\nNaN  9h4  79d     64"
        )
        assert result == expected

        # partial nan in mi
        df2 = df.copy()
        df2.loc[:, "id2"] = np.nan
        y = df2.set_index(["id2", "id3"])
        result = y.to_string()
        expected = (
            "         id1  value\nid2 id3            \n"
            "NaN 78d  1a3    123\n    79d  9h4     64"
        )
        assert result == expected

        df = DataFrame(
            {
                "id1": {0: np.nan, 1: "9h4"},
                "id2": {0: np.nan, 1: "d67"},
                "id3": {0: np.nan, 1: "79d"},
                "value": {0: 123, 1: 64},
            }
        )

        y = df.set_index(["id1", "id2", "id3"])
        result = y.to_string()
        expected = (
            "             value\nid1 id2 id3       \n"
            "NaN NaN NaN    123\n9h4 d67 79d     64"
        )
        assert result == expected

    def test_to_string_nonunicode_nonascii_alignment(self):
        df = DataFrame([["aa\xc3\xa4\xc3\xa4", 1], ["bbbb", 2]])
        rep_str = df.to_string()
        lines = rep_str.split("\n")
        assert len(lines[1]) == len(lines[2])

    def test_unicode_problem_decoding_as_ascii(self):
        df = DataFrame({"c/\u03c3": Series({"test": np.nan})})
        str(df.to_string())

    def test_to_string_repr_unicode(self):
        buf = StringIO()

        unicode_values = ["\u03c3"] * 10
        unicode_values = np.array(unicode_values, dtype=object)
        df = DataFrame({"unicode": unicode_values})
        df.to_string(col_space=10, buf=buf)

        # it works!
        repr(df)
        # it works even if sys.stdin in None
        _stdin = sys.stdin
        try:
            sys.stdin = None
            repr(df)
        finally:
            sys.stdin = _stdin


class TestSeriesToString:
    def test_to_string_without_index(self):
        # GH#11729 Test index=False option
        ser = Series([1, 2, 3, 4])
        result = ser.to_string(index=False)
        expected = "\n".join(["1", "2", "3", "4"])
        assert result == expected

    def test_to_string_name(self):
        ser = Series(range(100), dtype="int64")
        ser.name = "myser"
        res = ser.to_string(max_rows=2, name=True)
        exp = "0      0\n      ..\n99    99\nName: myser"
        assert res == exp
        res = ser.to_string(max_rows=2, name=False)
        exp = "0      0\n      ..\n99    99"
        assert res == exp

    def test_to_string_dtype(self):
        ser = Series(range(100), dtype="int64")
        res = ser.to_string(max_rows=2, dtype=True)
        exp = "0      0\n      ..\n99    99\ndtype: int64"
        assert res == exp
        res = ser.to_string(max_rows=2, dtype=False)
        exp = "0      0\n      ..\n99    99"
        assert res == exp

    def test_to_string_length(self):
        ser = Series(range(100), dtype="int64")
        res = ser.to_string(max_rows=2, length=True)
        exp = "0      0\n      ..\n99    99\nLength: 100"
        assert res == exp

    def test_to_string_na_rep(self):
        ser = Series(index=range(100), dtype=np.float64)
        res = ser.to_string(na_rep="foo", max_rows=2)
        exp = "0    foo\n      ..\n99   foo"
        assert res == exp

    def test_to_string_float_format(self):
        ser = Series(range(10), dtype="float64")
        res = ser.to_string(float_format=lambda x: f"{x:2.1f}", max_rows=2)
        exp = "0   0.0\n     ..\n9   9.0"
        assert res == exp

    def test_to_string_header(self):
        ser = Series(range(10), dtype="int64")
        ser.index.name = "foo"
        res = ser.to_string(header=True, max_rows=2)
        exp = "foo\n0    0\n    ..\n9    9"
        assert res == exp
        res = ser.to_string(header=False, max_rows=2)
        exp = "0    0\n    ..\n9    9"
        assert res == exp

    def test_to_string_empty_col(self):
        # GH#13653
        ser = Series(["", "Hello", "World", "", "", "Mooooo", "", ""])
        res = ser.to_string(index=False)
        exp = "      \n Hello\n World\n      \n      \nMooooo\n      \n      "
        assert re.match(exp, res)

    def test_to_string_timedelta64(self):
        Series(np.array([1100, 20], dtype="timedelta64[ns]")).to_string()

        ser = Series(date_range("2012-1-1", periods=3, freq="D"))

        # GH#2146

        # adding NaTs
        y = ser - ser.shift(1)
        result = y.to_string()
        assert "1 days" in result
        assert "00:00:00" not in result
        assert "NaT" in result

        # with frac seconds
        o = Series([datetime(2012, 1, 1, microsecond=150)] * 3)
        y = ser - o
        result = y.to_string()
        assert "-1 days +23:59:59.999850" in result

        # rounding?
        o = Series([datetime(2012, 1, 1, 1)] * 3)
        y = ser - o
        result = y.to_string()
        assert "-1 days +23:00:00" in result
        assert "1 days 23:00:00" in result

        o = Series([datetime(2012, 1, 1, 1, 1)] * 3)
        y = ser - o
        result = y.to_string()
        assert "-1 days +22:59:00" in result
        assert "1 days 22:59:00" in result

        o = Series([datetime(2012, 1, 1, 1, 1, microsecond=150)] * 3)
        y = ser - o
        result = y.to_string()
        assert "-1 days +22:58:59.999850" in result
        assert "0 days 22:58:59.999850" in result

        # neg time
        td = timedelta(minutes=5, seconds=3)
        s2 = Series(date_range("2012-1-1", periods=3, freq="D")) + td
        y = ser - s2
        result = y.to_string()
        assert "-1 days +23:54:57" in result

        td = timedelta(microseconds=550)
        s2 = Series(date_range("2012-1-1", periods=3, freq="D")) + td
        y = ser - td
        result = y.to_string()
        assert "2012-01-01 23:59:59.999450" in result

        # no boxing of the actual elements
        td = Series(timedelta_range("1 days", periods=3))
        result = td.to_string()
        assert result == "0   1 days\n1   2 days\n2   3 days"

    def test_to_string(self):
        ts = Series(
            np.arange(10, dtype=np.float64),
            index=date_range("2020-01-01", periods=10, freq="B"),
        )
        buf = StringIO()

        s = ts.to_string()

        retval = ts.to_string(buf=buf)
        assert retval is None
        assert buf.getvalue().strip() == s

        # pass float_format
        format = "%.4f".__mod__
        result = ts.to_string(float_format=format)
        result = [x.split()[1] for x in result.split("\n")[:-1]]
        expected = [format(x) for x in ts]
        assert result == expected

        # empty string
        result = ts[:0].to_string()
        assert result == "Series([], Freq: B)"

        result = ts[:0].to_string(length=0)
        assert result == "Series([], Freq: B)"

        # name and length
        cp = ts.copy()
        cp.name = "foo"
        result = cp.to_string(length=True, name=True, dtype=True)
        last_line = result.split("\n")[-1].strip()
        assert last_line == (f"Freq: B, Name: foo, Length: {len(cp)}, dtype: float64")

    @pytest.mark.parametrize(
        "input_array, expected",
        [
            ("a", "a"),
            (["a", "b"], "a\nb"),
            ([1, "a"], "1\na"),
            (1, "1"),
            ([0, -1], " 0\n-1"),
            (1.0, "1.0"),
            ([" a", " b"], " a\n b"),
            ([".1", "1"], ".1\n 1"),
            (["10", "-10"], " 10\n-10"),
        ],
    )
    def test_format_remove_leading_space_series(self, input_array, expected):
        # GH: 24980
        ser = Series(input_array)
        result = ser.to_string(index=False)
        assert result == expected

    def test_to_string_complex_number_trims_zeros(self):
        ser = Series([1.000000 + 1.000000j, 1.0 + 1.0j, 1.05 + 1.0j])
        result = ser.to_string()
        expected = dedent(
            """\
            0    1.00+1.00j
            1    1.00+1.00j
            2    1.05+1.00j"""
        )
        assert result == expected

    def test_nullable_float_to_string(self, float_ea_dtype):
        # https://github.com/pandas-dev/pandas/issues/36775
        dtype = float_ea_dtype
        ser = Series([0.0, 1.0, None], dtype=dtype)
        result = ser.to_string()
        expected = dedent(
            """\
            0     0.0
            1     1.0
            2    <NA>"""
        )
        assert result == expected

    def test_nullable_int_to_string(self, any_int_ea_dtype):
        # https://github.com/pandas-dev/pandas/issues/36775
        dtype = any_int_ea_dtype
        ser = Series([0, 1, None], dtype=dtype)
        result = ser.to_string()
        expected = dedent(
            """\
            0       0
            1       1
            2    <NA>"""
        )
        assert result == expected

    def test_to_string_mixed(self):
        ser = Series(["foo", np.nan, -1.23, 4.56])
        result = ser.to_string()
        expected = "".join(["0     foo\n", "1     NaN\n", "2   -1.23\n", "3    4.56"])
        assert result == expected

        # but don't count NAs as floats
        ser = Series(["foo", np.nan, "bar", "baz"])
        result = ser.to_string()
        expected = "".join(["0    foo\n", "1    NaN\n", "2    bar\n", "3    baz"])
        assert result == expected

        ser = Series(["foo", 5, "bar", "baz"])
        result = ser.to_string()
        expected = "".join(["0    foo\n", "1      5\n", "2    bar\n", "3    baz"])
        assert result == expected

    def test_to_string_float_na_spacing(self):
        ser = Series([0.0, 1.5678, 2.0, -3.0, 4.0])
        ser[::2] = np.nan

        result = ser.to_string()
        expected = (
            "0       NaN\n"
            "1    1.5678\n"
            "2       NaN\n"
            "3   -3.0000\n"
            "4       NaN"
        )
        assert result == expected

    def test_to_string_with_datetimeindex(self):
        index = date_range("20130102", periods=6)
        ser = Series(1, index=index)
        result = ser.to_string()
        assert "2013-01-02" in result

        # nat in index
        s2 = Series(2, index=[Timestamp("20130111"), NaT])
        ser = concat([s2, ser])
        result = ser.to_string()
        assert "NaT" in result

        # nat in summary
        result = str(s2.index)
        assert "NaT" in result
