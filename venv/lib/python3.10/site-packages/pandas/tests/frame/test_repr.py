from datetime import (
    datetime,
    timedelta,
)
from io import StringIO

import numpy as np
import pytest

from pandas import (
    NA,
    Categorical,
    CategoricalIndex,
    DataFrame,
    IntervalIndex,
    MultiIndex,
    NaT,
    PeriodIndex,
    Series,
    Timestamp,
    date_range,
    option_context,
    period_range,
)
import pandas._testing as tm


class TestDataFrameRepr:
    def test_repr_should_return_str(self):
        # https://docs.python.org/3/reference/datamodel.html#object.__repr__
        # "...The return value must be a string object."

        # (str on py2.x, str (unicode) on py3)

        data = [8, 5, 3, 5]
        index1 = ["\u03c3", "\u03c4", "\u03c5", "\u03c6"]
        cols = ["\u03c8"]
        df = DataFrame(data, columns=cols, index=index1)
        assert type(df.__repr__()) is str  # noqa: E721

        ser = df[cols[0]]
        assert type(ser.__repr__()) is str  # noqa: E721

    def test_repr_bytes_61_lines(self):
        # GH#12857
        lets = list("ACDEFGHIJKLMNOP")
        words = np.random.default_rng(2).choice(lets, (1000, 50))
        df = DataFrame(words).astype("U1")
        assert (df.dtypes == object).all()

        # smoke tests; at one point this raised with 61 but not 60
        repr(df)
        repr(df.iloc[:60, :])
        repr(df.iloc[:61, :])

    def test_repr_unicode_level_names(self, frame_or_series):
        index = MultiIndex.from_tuples([(0, 0), (1, 1)], names=["\u0394", "i1"])

        obj = DataFrame(np.random.default_rng(2).standard_normal((2, 4)), index=index)
        obj = tm.get_obj(obj, frame_or_series)
        repr(obj)

    def test_assign_index_sequences(self):
        # GH#2200
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}).set_index(
            ["a", "b"]
        )
        index = list(df.index)
        index[0] = ("faz", "boo")
        df.index = index
        repr(df)

        # this travels an improper code path
        index[0] = ["faz", "boo"]
        df.index = index
        repr(df)

    def test_repr_with_mi_nat(self):
        df = DataFrame({"X": [1, 2]}, index=[[NaT, Timestamp("20130101")], ["a", "b"]])
        result = repr(df)
        expected = "              X\nNaT        a  1\n2013-01-01 b  2"
        assert result == expected

    def test_repr_with_different_nulls(self):
        # GH45263
        df = DataFrame([1, 2, 3, 4], [True, None, np.nan, NaT])
        result = repr(df)
        expected = """      0
True  1
None  2
NaN   3
NaT   4"""
        assert result == expected

    def test_repr_with_different_nulls_cols(self):
        # GH45263
        d = {np.nan: [1, 2], None: [3, 4], NaT: [6, 7], True: [8, 9]}
        df = DataFrame(data=d)
        result = repr(df)
        expected = """   NaN  None  NaT  True
0    1     3    6     8
1    2     4    7     9"""
        assert result == expected

    def test_multiindex_na_repr(self):
        # only an issue with long columns
        df3 = DataFrame(
            {
                "A" * 30: {("A", "A0006000", "nuit"): "A0006000"},
                "B" * 30: {("A", "A0006000", "nuit"): np.nan},
                "C" * 30: {("A", "A0006000", "nuit"): np.nan},
                "D" * 30: {("A", "A0006000", "nuit"): np.nan},
                "E" * 30: {("A", "A0006000", "nuit"): "A"},
                "F" * 30: {("A", "A0006000", "nuit"): np.nan},
            }
        )

        idf = df3.set_index(["A" * 30, "C" * 30])
        repr(idf)

    def test_repr_name_coincide(self):
        index = MultiIndex.from_tuples(
            [("a", 0, "foo"), ("b", 1, "bar")], names=["a", "b", "c"]
        )

        df = DataFrame({"value": [0, 1]}, index=index)

        lines = repr(df).split("\n")
        assert lines[2].startswith("a 0 foo")

    def test_repr_to_string(
        self,
        multiindex_year_month_day_dataframe_random_data,
        multiindex_dataframe_random_data,
    ):
        ymd = multiindex_year_month_day_dataframe_random_data
        frame = multiindex_dataframe_random_data

        repr(frame)
        repr(ymd)
        repr(frame.T)
        repr(ymd.T)

        buf = StringIO()
        frame.to_string(buf=buf)
        ymd.to_string(buf=buf)
        frame.T.to_string(buf=buf)
        ymd.T.to_string(buf=buf)

    def test_repr_empty(self):
        # empty
        repr(DataFrame())

        # empty with index
        frame = DataFrame(index=np.arange(1000))
        repr(frame)

    def test_repr_mixed(self, float_string_frame):
        # mixed
        repr(float_string_frame)

    @pytest.mark.slow
    def test_repr_mixed_big(self):
        # big mixed
        biggie = DataFrame(
            {
                "A": np.random.default_rng(2).standard_normal(200),
                "B": [str(i) for i in range(200)],
            },
            index=range(200),
        )
        biggie.loc[:20, "A"] = np.nan
        biggie.loc[:20, "B"] = np.nan

        repr(biggie)

    def test_repr(self):
        # columns but no index
        no_index = DataFrame(columns=[0, 1, 3])
        repr(no_index)

        df = DataFrame(["a\n\r\tb"], columns=["a\n\r\td"], index=["a\n\r\tf"])
        assert "\t" not in repr(df)
        assert "\r" not in repr(df)
        assert "a\n" not in repr(df)

    def test_repr_dimensions(self):
        df = DataFrame([[1, 2], [3, 4]])
        with option_context("display.show_dimensions", True):
            assert "2 rows x 2 columns" in repr(df)

        with option_context("display.show_dimensions", False):
            assert "2 rows x 2 columns" not in repr(df)

        with option_context("display.show_dimensions", "truncate"):
            assert "2 rows x 2 columns" not in repr(df)

    @pytest.mark.slow
    def test_repr_big(self):
        # big one
        biggie = DataFrame(np.zeros((200, 4)), columns=range(4), index=range(200))
        repr(biggie)

    def test_repr_unsortable(self):
        # columns are not sortable

        unsortable = DataFrame(
            {
                "foo": [1] * 50,
                datetime.today(): [1] * 50,
                "bar": ["bar"] * 50,
                datetime.today() + timedelta(1): ["bar"] * 50,
            },
            index=np.arange(50),
        )
        repr(unsortable)

    def test_repr_float_frame_options(self, float_frame):
        repr(float_frame)

        with option_context("display.precision", 3):
            repr(float_frame)

        with option_context("display.max_rows", 10, "display.max_columns", 2):
            repr(float_frame)

        with option_context("display.max_rows", 1000, "display.max_columns", 1000):
            repr(float_frame)

    def test_repr_unicode(self):
        uval = "\u03c3\u03c3\u03c3\u03c3"

        df = DataFrame({"A": [uval, uval]})

        result = repr(df)
        ex_top = "      A"
        assert result.split("\n")[0].rstrip() == ex_top

        df = DataFrame({"A": [uval, uval]})
        result = repr(df)
        assert result.split("\n")[0].rstrip() == ex_top

    def test_unicode_string_with_unicode(self):
        df = DataFrame({"A": ["\u05d0"]})
        str(df)

    def test_repr_unicode_columns(self):
        df = DataFrame({"\u05d0": [1, 2, 3], "\u05d1": [4, 5, 6], "c": [7, 8, 9]})
        repr(df.columns)  # should not raise UnicodeDecodeError

    def test_str_to_bytes_raises(self):
        # GH 26447
        df = DataFrame({"A": ["abc"]})
        msg = "^'str' object cannot be interpreted as an integer$"
        with pytest.raises(TypeError, match=msg):
            bytes(df)

    def test_very_wide_repr(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 20)),
            columns=np.array(["a" * 10] * 20, dtype=object),
        )
        repr(df)

    def test_repr_column_name_unicode_truncation_bug(self):
        # #1906
        df = DataFrame(
            {
                "Id": [7117434],
                "StringCol": (
                    "Is it possible to modify drop plot code"
                    "so that the output graph is displayed "
                    "in iphone simulator, Is it possible to "
                    "modify drop plot code so that the "
                    "output graph is \xe2\x80\xa8displayed "
                    "in iphone simulator.Now we are adding "
                    "the CSV file externally. I want to Call "
                    "the File through the code.."
                ),
            }
        )

        with option_context("display.max_columns", 20):
            assert "StringCol" in repr(df)

    def test_latex_repr(self):
        pytest.importorskip("jinja2")
        expected = r"""\begin{tabular}{llll}
\toprule
 & 0 & 1 & 2 \\
\midrule
0 & $\alpha$ & b & c \\
1 & 1 & 2 & 3 \\
\bottomrule
\end{tabular}
"""
        with option_context(
            "styler.format.escape", None, "styler.render.repr", "latex"
        ):
            df = DataFrame([[r"$\alpha$", "b", "c"], [1, 2, 3]])
            result = df._repr_latex_()
            assert result == expected

        # GH 12182
        assert df._repr_latex_() is None

    def test_repr_with_datetimeindex(self):
        df = DataFrame({"A": [1, 2, 3]}, index=date_range("2000", periods=3))
        result = repr(df)
        expected = "            A\n2000-01-01  1\n2000-01-02  2\n2000-01-03  3"
        assert result == expected

    def test_repr_with_intervalindex(self):
        # https://github.com/pandas-dev/pandas/pull/24134/files
        df = DataFrame(
            {"A": [1, 2, 3, 4]}, index=IntervalIndex.from_breaks([0, 1, 2, 3, 4])
        )
        result = repr(df)
        expected = "        A\n(0, 1]  1\n(1, 2]  2\n(2, 3]  3\n(3, 4]  4"
        assert result == expected

    def test_repr_with_categorical_index(self):
        df = DataFrame({"A": [1, 2, 3]}, index=CategoricalIndex(["a", "b", "c"]))
        result = repr(df)
        expected = "   A\na  1\nb  2\nc  3"
        assert result == expected

    def test_repr_categorical_dates_periods(self):
        # normal DataFrame
        dt = date_range("2011-01-01 09:00", freq="h", periods=5, tz="US/Eastern")
        p = period_range("2011-01", freq="M", periods=5)
        df = DataFrame({"dt": dt, "p": p})
        exp = """                         dt        p
0 2011-01-01 09:00:00-05:00  2011-01
1 2011-01-01 10:00:00-05:00  2011-02
2 2011-01-01 11:00:00-05:00  2011-03
3 2011-01-01 12:00:00-05:00  2011-04
4 2011-01-01 13:00:00-05:00  2011-05"""

        assert repr(df) == exp

        df2 = DataFrame({"dt": Categorical(dt), "p": Categorical(p)})
        assert repr(df2) == exp

    @pytest.mark.parametrize("arg", [np.datetime64, np.timedelta64])
    @pytest.mark.parametrize(
        "box, expected",
        [[Series, "0    NaT\ndtype: object"], [DataFrame, "     0\n0  NaT"]],
    )
    def test_repr_np_nat_with_object(self, arg, box, expected):
        # GH 25445
        result = repr(box([arg("NaT")], dtype=object))
        assert result == expected

    def test_frame_datetime64_pre1900_repr(self):
        df = DataFrame({"year": date_range("1/1/1700", periods=50, freq="YE-DEC")})
        # it works!
        repr(df)

    def test_frame_to_string_with_periodindex(self):
        index = PeriodIndex(["2011-1", "2011-2", "2011-3"], freq="M")
        frame = DataFrame(np.random.default_rng(2).standard_normal((3, 4)), index=index)

        # it works!
        frame.to_string()

    def test_to_string_ea_na_in_multiindex(self):
        # GH#47986
        df = DataFrame(
            {"a": [1, 2]},
            index=MultiIndex.from_arrays([Series([NA, 1], dtype="Int64")]),
        )

        result = df.to_string()
        expected = """      a
<NA>  1
1     2"""
        assert result == expected

    def test_datetime64tz_slice_non_truncate(self):
        # GH 30263
        df = DataFrame({"x": date_range("2019", periods=10, tz="UTC")})
        expected = repr(df)
        df = df.iloc[:, :5]
        result = repr(df)
        assert result == expected

    def test_to_records_no_typeerror_in_repr(self):
        # GH 48526
        df = DataFrame([["a", "b"], ["c", "d"], ["e", "f"]], columns=["left", "right"])
        df["record"] = df[["left", "right"]].to_records()
        expected = """  left right     record
0    a     b  [0, a, b]
1    c     d  [1, c, d]
2    e     f  [2, e, f]"""
        result = repr(df)
        assert result == expected

    def test_to_records_with_na_record_value(self):
        # GH 48526
        df = DataFrame(
            [["a", np.nan], ["c", "d"], ["e", "f"]], columns=["left", "right"]
        )
        df["record"] = df[["left", "right"]].to_records()
        expected = """  left right       record
0    a   NaN  [0, a, nan]
1    c     d    [1, c, d]
2    e     f    [2, e, f]"""
        result = repr(df)
        assert result == expected

    def test_to_records_with_na_record(self):
        # GH 48526
        df = DataFrame(
            [["a", "b"], [np.nan, np.nan], ["e", "f"]], columns=[np.nan, "right"]
        )
        df["record"] = df[[np.nan, "right"]].to_records()
        expected = """   NaN right         record
0    a     b      [0, a, b]
1  NaN   NaN  [1, nan, nan]
2    e     f      [2, e, f]"""
        result = repr(df)
        assert result == expected

    def test_to_records_with_inf_as_na_record(self):
        # GH 48526
        expected = """   NaN  inf         record
0  inf    b    [0, inf, b]
1  NaN  NaN  [1, nan, nan]
2    e    f      [2, e, f]"""
        msg = "use_inf_as_na option is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            with option_context("use_inf_as_na", True):
                df = DataFrame(
                    [[np.inf, "b"], [np.nan, np.nan], ["e", "f"]],
                    columns=[np.nan, np.inf],
                )
                df["record"] = df[[np.nan, np.inf]].to_records()
                result = repr(df)
        assert result == expected

    def test_to_records_with_inf_record(self):
        # GH 48526
        expected = """   NaN  inf         record
0  inf    b    [0, inf, b]
1  NaN  NaN  [1, nan, nan]
2    e    f      [2, e, f]"""
        msg = "use_inf_as_na option is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            with option_context("use_inf_as_na", False):
                df = DataFrame(
                    [[np.inf, "b"], [np.nan, np.nan], ["e", "f"]],
                    columns=[np.nan, np.inf],
                )
                df["record"] = df[[np.nan, np.inf]].to_records()
                result = repr(df)
        assert result == expected

    def test_masked_ea_with_formatter(self):
        # GH#39336
        df = DataFrame(
            {
                "a": Series([0.123456789, 1.123456789], dtype="Float64"),
                "b": Series([1, 2], dtype="Int64"),
            }
        )
        result = df.to_string(formatters=["{:.2f}".format, "{:.2f}".format])
        expected = """      a     b
0  0.12  1.00
1  1.12  2.00"""
        assert result == expected

    def test_repr_ea_columns(self, any_string_dtype):
        # GH#54797
        pytest.importorskip("pyarrow")
        df = DataFrame({"long_column_name": [1, 2, 3], "col2": [4, 5, 6]})
        df.columns = df.columns.astype(any_string_dtype)
        expected = """   long_column_name  col2
0                 1     4
1                 2     5
2                 3     6"""
        assert repr(df) == expected


@pytest.mark.parametrize(
    "data,output",
    [
        ([2, complex("nan"), 1], [" 2.0+0.0j", " NaN+0.0j", " 1.0+0.0j"]),
        ([2, complex("nan"), -1], [" 2.0+0.0j", " NaN+0.0j", "-1.0+0.0j"]),
        ([-2, complex("nan"), -1], ["-2.0+0.0j", " NaN+0.0j", "-1.0+0.0j"]),
        ([-1.23j, complex("nan"), -1], ["-0.00-1.23j", "  NaN+0.00j", "-1.00+0.00j"]),
        ([1.23j, complex("nan"), 1.23], [" 0.00+1.23j", "  NaN+0.00j", " 1.23+0.00j"]),
        (
            [-1.23j, complex(np.nan, np.nan), 1],
            ["-0.00-1.23j", "  NaN+ NaNj", " 1.00+0.00j"],
        ),
        (
            [-1.23j, complex(1.2, np.nan), 1],
            ["-0.00-1.23j", " 1.20+ NaNj", " 1.00+0.00j"],
        ),
        (
            [-1.23j, complex(np.nan, -1.2), 1],
            ["-0.00-1.23j", "  NaN-1.20j", " 1.00+0.00j"],
        ),
    ],
)
@pytest.mark.parametrize("as_frame", [True, False])
def test_repr_with_complex_nans(data, output, as_frame):
    # GH#53762, GH#53841
    obj = Series(np.array(data))
    if as_frame:
        obj = obj.to_frame(name="val")
        reprs = [f"{i} {val}" for i, val in enumerate(output)]
        expected = f"{'val': >{len(reprs[0])}}\n" + "\n".join(reprs)
    else:
        reprs = [f"{i}   {val}" for i, val in enumerate(output)]
        expected = "\n".join(reprs) + "\ndtype: complex128"
    assert str(obj) == expected, f"\n{str(obj)}\n\n{expected}"
