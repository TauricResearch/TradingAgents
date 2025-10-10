import operator

import numpy as np
import pytest

from pandas.errors import (
    NumExprClobberingError,
    UndefinedVariableError,
)
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    date_range,
)
import pandas._testing as tm
from pandas.core.computation.check import NUMEXPR_INSTALLED


@pytest.fixture(params=["python", "pandas"], ids=lambda x: x)
def parser(request):
    return request.param


@pytest.fixture(
    params=["python", pytest.param("numexpr", marks=td.skip_if_no("numexpr"))],
    ids=lambda x: x,
)
def engine(request):
    return request.param


def skip_if_no_pandas_parser(parser):
    if parser != "pandas":
        pytest.skip(f"cannot evaluate with parser={parser}")


class TestCompat:
    @pytest.fixture
    def df(self):
        return DataFrame({"A": [1, 2, 3]})

    @pytest.fixture
    def expected1(self, df):
        return df[df.A > 0]

    @pytest.fixture
    def expected2(self, df):
        return df.A + 1

    def test_query_default(self, df, expected1, expected2):
        # GH 12749
        # this should always work, whether NUMEXPR_INSTALLED or not
        result = df.query("A>0")
        tm.assert_frame_equal(result, expected1)
        result = df.eval("A+1")
        tm.assert_series_equal(result, expected2, check_names=False)

    def test_query_None(self, df, expected1, expected2):
        result = df.query("A>0", engine=None)
        tm.assert_frame_equal(result, expected1)
        result = df.eval("A+1", engine=None)
        tm.assert_series_equal(result, expected2, check_names=False)

    def test_query_python(self, df, expected1, expected2):
        result = df.query("A>0", engine="python")
        tm.assert_frame_equal(result, expected1)
        result = df.eval("A+1", engine="python")
        tm.assert_series_equal(result, expected2, check_names=False)

    def test_query_numexpr(self, df, expected1, expected2):
        if NUMEXPR_INSTALLED:
            result = df.query("A>0", engine="numexpr")
            tm.assert_frame_equal(result, expected1)
            result = df.eval("A+1", engine="numexpr")
            tm.assert_series_equal(result, expected2, check_names=False)
        else:
            msg = (
                r"'numexpr' is not installed or an unsupported version. "
                r"Cannot use engine='numexpr' for query/eval if 'numexpr' is "
                r"not installed"
            )
            with pytest.raises(ImportError, match=msg):
                df.query("A>0", engine="numexpr")
            with pytest.raises(ImportError, match=msg):
                df.eval("A+1", engine="numexpr")


class TestDataFrameEval:
    # smaller hits python, larger hits numexpr
    @pytest.mark.parametrize("n", [4, 4000])
    @pytest.mark.parametrize(
        "op_str,op,rop",
        [
            ("+", "__add__", "__radd__"),
            ("-", "__sub__", "__rsub__"),
            ("*", "__mul__", "__rmul__"),
            ("/", "__truediv__", "__rtruediv__"),
        ],
    )
    def test_ops(self, op_str, op, rop, n):
        # tst ops and reversed ops in evaluation
        # GH7198

        df = DataFrame(1, index=range(n), columns=list("abcd"))
        df.iloc[0] = 2
        m = df.mean()

        base = DataFrame(  # noqa: F841
            np.tile(m.values, n).reshape(n, -1), columns=list("abcd")
        )

        expected = eval(f"base {op_str} df")

        # ops as strings
        result = eval(f"m {op_str} df")
        tm.assert_frame_equal(result, expected)

        # these are commutative
        if op in ["+", "*"]:
            result = getattr(df, op)(m)
            tm.assert_frame_equal(result, expected)

        # these are not
        elif op in ["-", "/"]:
            result = getattr(df, rop)(m)
            tm.assert_frame_equal(result, expected)

    def test_dataframe_sub_numexpr_path(self):
        # GH7192: Note we need a large number of rows to ensure this
        #  goes through the numexpr path
        df = DataFrame({"A": np.random.default_rng(2).standard_normal(25000)})
        df.iloc[0:5] = np.nan
        expected = 1 - np.isnan(df.iloc[0:25])
        result = (1 - np.isnan(df)).iloc[0:25]
        tm.assert_frame_equal(result, expected)

    def test_query_non_str(self):
        # GH 11485
        df = DataFrame({"A": [1, 2, 3], "B": ["a", "b", "b"]})

        msg = "expr must be a string to be evaluated"
        with pytest.raises(ValueError, match=msg):
            df.query(lambda x: x.B == "b")

        with pytest.raises(ValueError, match=msg):
            df.query(111)

    def test_query_empty_string(self):
        # GH 13139
        df = DataFrame({"A": [1, 2, 3]})

        msg = "expr cannot be an empty string"
        with pytest.raises(ValueError, match=msg):
            df.query("")

    def test_eval_resolvers_as_list(self):
        # GH 14095
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 2)), columns=list("ab")
        )
        dict1 = {"a": 1}
        dict2 = {"b": 2}
        assert df.eval("a + b", resolvers=[dict1, dict2]) == dict1["a"] + dict2["b"]
        assert pd.eval("a + b", resolvers=[dict1, dict2]) == dict1["a"] + dict2["b"]

    def test_eval_resolvers_combined(self):
        # GH 34966
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 2)), columns=list("ab")
        )
        dict1 = {"c": 2}

        # Both input and default index/column resolvers should be usable
        result = df.eval("a + b * c", resolvers=[dict1])

        expected = df["a"] + df["b"] * dict1["c"]
        tm.assert_series_equal(result, expected)

    def test_eval_object_dtype_binop(self):
        # GH#24883
        df = DataFrame({"a1": ["Y", "N"]})
        res = df.eval("c = ((a1 == 'Y') & True)")
        expected = DataFrame({"a1": ["Y", "N"], "c": [True, False]})
        tm.assert_frame_equal(res, expected)

    def test_extension_array_eval(self, engine, parser, request):
        # GH#58748
        if engine == "numexpr":
            mark = pytest.mark.xfail(
                reason="numexpr does not support extension array dtypes"
            )
            request.applymarker(mark)
        df = DataFrame({"a": pd.array([1, 2, 3]), "b": pd.array([4, 5, 6])})
        result = df.eval("a / b", engine=engine, parser=parser)
        expected = Series(pd.array([0.25, 0.40, 0.50]))
        tm.assert_series_equal(result, expected)

    def test_complex_eval(self, engine, parser):
        # GH#21374
        df = DataFrame({"a": [1 + 2j], "b": [1 + 1j]})
        result = df.eval("a/b", engine=engine, parser=parser)
        expected = Series([1.5 + 0.5j])
        tm.assert_series_equal(result, expected)


class TestDataFrameQueryWithMultiIndex:
    def test_query_with_named_multiindex(self, parser, engine):
        skip_if_no_pandas_parser(parser)
        a = np.random.default_rng(2).choice(["red", "green"], size=10)
        b = np.random.default_rng(2).choice(["eggs", "ham"], size=10)
        index = MultiIndex.from_arrays([a, b], names=["color", "food"])
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2)), index=index)
        ind = Series(
            df.index.get_level_values("color").values, index=index, name="color"
        )

        # equality
        res1 = df.query('color == "red"', parser=parser, engine=engine)
        res2 = df.query('"red" == color', parser=parser, engine=engine)
        exp = df[ind == "red"]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # inequality
        res1 = df.query('color != "red"', parser=parser, engine=engine)
        res2 = df.query('"red" != color', parser=parser, engine=engine)
        exp = df[ind != "red"]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # list equality (really just set membership)
        res1 = df.query('color == ["red"]', parser=parser, engine=engine)
        res2 = df.query('["red"] == color', parser=parser, engine=engine)
        exp = df[ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        res1 = df.query('color != ["red"]', parser=parser, engine=engine)
        res2 = df.query('["red"] != color', parser=parser, engine=engine)
        exp = df[~ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # in/not in ops
        res1 = df.query('["red"] in color', parser=parser, engine=engine)
        res2 = df.query('"red" in color', parser=parser, engine=engine)
        exp = df[ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        res1 = df.query('["red"] not in color', parser=parser, engine=engine)
        res2 = df.query('"red" not in color', parser=parser, engine=engine)
        exp = df[~ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

    def test_query_with_unnamed_multiindex(self, parser, engine):
        skip_if_no_pandas_parser(parser)
        a = np.random.default_rng(2).choice(["red", "green"], size=10)
        b = np.random.default_rng(2).choice(["eggs", "ham"], size=10)
        index = MultiIndex.from_arrays([a, b])
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2)), index=index)
        ind = Series(df.index.get_level_values(0).values, index=index)

        res1 = df.query('ilevel_0 == "red"', parser=parser, engine=engine)
        res2 = df.query('"red" == ilevel_0', parser=parser, engine=engine)
        exp = df[ind == "red"]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # inequality
        res1 = df.query('ilevel_0 != "red"', parser=parser, engine=engine)
        res2 = df.query('"red" != ilevel_0', parser=parser, engine=engine)
        exp = df[ind != "red"]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # list equality (really just set membership)
        res1 = df.query('ilevel_0 == ["red"]', parser=parser, engine=engine)
        res2 = df.query('["red"] == ilevel_0', parser=parser, engine=engine)
        exp = df[ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        res1 = df.query('ilevel_0 != ["red"]', parser=parser, engine=engine)
        res2 = df.query('["red"] != ilevel_0', parser=parser, engine=engine)
        exp = df[~ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # in/not in ops
        res1 = df.query('["red"] in ilevel_0', parser=parser, engine=engine)
        res2 = df.query('"red" in ilevel_0', parser=parser, engine=engine)
        exp = df[ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        res1 = df.query('["red"] not in ilevel_0', parser=parser, engine=engine)
        res2 = df.query('"red" not in ilevel_0', parser=parser, engine=engine)
        exp = df[~ind.isin(["red"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # ## LEVEL 1
        ind = Series(df.index.get_level_values(1).values, index=index)
        res1 = df.query('ilevel_1 == "eggs"', parser=parser, engine=engine)
        res2 = df.query('"eggs" == ilevel_1', parser=parser, engine=engine)
        exp = df[ind == "eggs"]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # inequality
        res1 = df.query('ilevel_1 != "eggs"', parser=parser, engine=engine)
        res2 = df.query('"eggs" != ilevel_1', parser=parser, engine=engine)
        exp = df[ind != "eggs"]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # list equality (really just set membership)
        res1 = df.query('ilevel_1 == ["eggs"]', parser=parser, engine=engine)
        res2 = df.query('["eggs"] == ilevel_1', parser=parser, engine=engine)
        exp = df[ind.isin(["eggs"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        res1 = df.query('ilevel_1 != ["eggs"]', parser=parser, engine=engine)
        res2 = df.query('["eggs"] != ilevel_1', parser=parser, engine=engine)
        exp = df[~ind.isin(["eggs"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        # in/not in ops
        res1 = df.query('["eggs"] in ilevel_1', parser=parser, engine=engine)
        res2 = df.query('"eggs" in ilevel_1', parser=parser, engine=engine)
        exp = df[ind.isin(["eggs"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

        res1 = df.query('["eggs"] not in ilevel_1', parser=parser, engine=engine)
        res2 = df.query('"eggs" not in ilevel_1', parser=parser, engine=engine)
        exp = df[~ind.isin(["eggs"])]
        tm.assert_frame_equal(res1, exp)
        tm.assert_frame_equal(res2, exp)

    def test_query_with_partially_named_multiindex(self, parser, engine):
        skip_if_no_pandas_parser(parser)
        a = np.random.default_rng(2).choice(["red", "green"], size=10)
        b = np.arange(10)
        index = MultiIndex.from_arrays([a, b])
        index.names = [None, "rating"]
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2)), index=index)
        res = df.query("rating == 1", parser=parser, engine=engine)
        ind = Series(
            df.index.get_level_values("rating").values, index=index, name="rating"
        )
        exp = df[ind == 1]
        tm.assert_frame_equal(res, exp)

        res = df.query("rating != 1", parser=parser, engine=engine)
        ind = Series(
            df.index.get_level_values("rating").values, index=index, name="rating"
        )
        exp = df[ind != 1]
        tm.assert_frame_equal(res, exp)

        res = df.query('ilevel_0 == "red"', parser=parser, engine=engine)
        ind = Series(df.index.get_level_values(0).values, index=index)
        exp = df[ind == "red"]
        tm.assert_frame_equal(res, exp)

        res = df.query('ilevel_0 != "red"', parser=parser, engine=engine)
        ind = Series(df.index.get_level_values(0).values, index=index)
        exp = df[ind != "red"]
        tm.assert_frame_equal(res, exp)

    def test_query_multiindex_get_index_resolvers(self):
        df = DataFrame(
            np.ones((10, 3)),
            index=MultiIndex.from_arrays(
                [range(10) for _ in range(2)], names=["spam", "eggs"]
            ),
        )
        resolvers = df._get_index_resolvers()

        def to_series(mi, level):
            level_values = mi.get_level_values(level)
            s = level_values.to_series()
            s.index = mi
            return s

        col_series = df.columns.to_series()
        expected = {
            "index": df.index,
            "columns": col_series,
            "spam": to_series(df.index, "spam"),
            "eggs": to_series(df.index, "eggs"),
            "clevel_0": col_series,
        }
        for k, v in resolvers.items():
            if isinstance(v, Index):
                assert v.is_(expected[k])
            elif isinstance(v, Series):
                tm.assert_series_equal(v, expected[k])
            else:
                raise AssertionError("object must be a Series or Index")


@td.skip_if_no("numexpr")
class TestDataFrameQueryNumExprPandas:
    @pytest.fixture
    def engine(self):
        return "numexpr"

    @pytest.fixture
    def parser(self):
        return "pandas"

    def test_date_query_with_attribute_access(self, engine, parser):
        skip_if_no_pandas_parser(parser)
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        df["dates1"] = date_range("1/1/2012", periods=5)
        df["dates2"] = date_range("1/1/2013", periods=5)
        df["dates3"] = date_range("1/1/2014", periods=5)
        res = df.query(
            "@df.dates1 < 20130101 < @df.dates3", engine=engine, parser=parser
        )
        expec = df[(df.dates1 < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_query_no_attribute_access(self, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        df["dates1"] = date_range("1/1/2012", periods=5)
        df["dates2"] = date_range("1/1/2013", periods=5)
        df["dates3"] = date_range("1/1/2014", periods=5)
        res = df.query("dates1 < 20130101 < dates3", engine=engine, parser=parser)
        expec = df[(df.dates1 < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_query_with_NaT(self, engine, parser):
        n = 10
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3)))
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates2"] = date_range("1/1/2013", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        df.loc[np.random.default_rng(2).random(n) > 0.5, "dates1"] = pd.NaT
        df.loc[np.random.default_rng(2).random(n) > 0.5, "dates3"] = pd.NaT
        res = df.query("dates1 < 20130101 < dates3", engine=engine, parser=parser)
        expec = df[(df.dates1 < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_index_query(self, engine, parser):
        n = 10
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3)))
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        return_value = df.set_index("dates1", inplace=True, drop=True)
        assert return_value is None
        res = df.query("index < 20130101 < dates3", engine=engine, parser=parser)
        expec = df[(df.index < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_index_query_with_NaT(self, engine, parser):
        n = 10
        # Cast to object to avoid implicit cast when setting entry to pd.NaT below
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3))).astype(
            {0: object}
        )
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        df.iloc[0, 0] = pd.NaT
        return_value = df.set_index("dates1", inplace=True, drop=True)
        assert return_value is None
        res = df.query("index < 20130101 < dates3", engine=engine, parser=parser)
        expec = df[(df.index < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_index_query_with_NaT_duplicates(self, engine, parser):
        n = 10
        d = {}
        d["dates1"] = date_range("1/1/2012", periods=n)
        d["dates3"] = date_range("1/1/2014", periods=n)
        df = DataFrame(d)
        df.loc[np.random.default_rng(2).random(n) > 0.5, "dates1"] = pd.NaT
        return_value = df.set_index("dates1", inplace=True, drop=True)
        assert return_value is None
        res = df.query("dates1 < 20130101 < dates3", engine=engine, parser=parser)
        expec = df[(df.index.to_series() < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_query_with_non_date(self, engine, parser):
        n = 10
        df = DataFrame(
            {"dates": date_range("1/1/2012", periods=n), "nondate": np.arange(n)}
        )

        result = df.query("dates == nondate", parser=parser, engine=engine)
        assert len(result) == 0

        result = df.query("dates != nondate", parser=parser, engine=engine)
        tm.assert_frame_equal(result, df)

        msg = r"Invalid comparison between dtype=datetime64\[ns\] and ndarray"
        for op in ["<", ">", "<=", ">="]:
            with pytest.raises(TypeError, match=msg):
                df.query(f"dates {op} nondate", parser=parser, engine=engine)

    def test_query_syntax_error(self, engine, parser):
        df = DataFrame({"i": range(10), "+": range(3, 13), "r": range(4, 14)})
        msg = "invalid syntax"
        with pytest.raises(SyntaxError, match=msg):
            df.query("i - +", engine=engine, parser=parser)

    def test_query_scope(self, engine, parser):
        skip_if_no_pandas_parser(parser)

        df = DataFrame(
            np.random.default_rng(2).standard_normal((20, 2)), columns=list("ab")
        )

        a, b = 1, 2  # noqa: F841
        res = df.query("a > b", engine=engine, parser=parser)
        expected = df[df.a > df.b]
        tm.assert_frame_equal(res, expected)

        res = df.query("@a > b", engine=engine, parser=parser)
        expected = df[a > df.b]
        tm.assert_frame_equal(res, expected)

        # no local variable c
        with pytest.raises(
            UndefinedVariableError, match="local variable 'c' is not defined"
        ):
            df.query("@a > b > @c", engine=engine, parser=parser)

        # no column named 'c'
        with pytest.raises(UndefinedVariableError, match="name 'c' is not defined"):
            df.query("@a > b > c", engine=engine, parser=parser)

    def test_query_doesnt_pickup_local(self, engine, parser):
        n = m = 10
        df = DataFrame(
            np.random.default_rng(2).integers(m, size=(n, 3)), columns=list("abc")
        )

        # we don't pick up the local 'sin'
        with pytest.raises(UndefinedVariableError, match="name 'sin' is not defined"):
            df.query("sin > 5", engine=engine, parser=parser)

    def test_query_builtin(self, engine, parser):
        n = m = 10
        df = DataFrame(
            np.random.default_rng(2).integers(m, size=(n, 3)), columns=list("abc")
        )

        df.index.name = "sin"
        msg = "Variables in expression.+"
        with pytest.raises(NumExprClobberingError, match=msg):
            df.query("sin > 5", engine=engine, parser=parser)

    def test_query(self, engine, parser):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=["a", "b", "c"]
        )

        tm.assert_frame_equal(
            df.query("a < b", engine=engine, parser=parser), df[df.a < df.b]
        )
        tm.assert_frame_equal(
            df.query("a + b > b * c", engine=engine, parser=parser),
            df[df.a + df.b > df.b * df.c],
        )

    def test_query_index_with_name(self, engine, parser):
        df = DataFrame(
            np.random.default_rng(2).integers(10, size=(10, 3)),
            index=Index(range(10), name="blob"),
            columns=["a", "b", "c"],
        )
        res = df.query("(blob < 5) & (a < b)", engine=engine, parser=parser)
        expec = df[(df.index < 5) & (df.a < df.b)]
        tm.assert_frame_equal(res, expec)

        res = df.query("blob < b", engine=engine, parser=parser)
        expec = df[df.index < df.b]

        tm.assert_frame_equal(res, expec)

    def test_query_index_without_name(self, engine, parser):
        df = DataFrame(
            np.random.default_rng(2).integers(10, size=(10, 3)),
            index=range(10),
            columns=["a", "b", "c"],
        )

        # "index" should refer to the index
        res = df.query("index < b", engine=engine, parser=parser)
        expec = df[df.index < df.b]
        tm.assert_frame_equal(res, expec)

        # test against a scalar
        res = df.query("index < 5", engine=engine, parser=parser)
        expec = df[df.index < 5]
        tm.assert_frame_equal(res, expec)

    def test_nested_scope(self, engine, parser):
        skip_if_no_pandas_parser(parser)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        df2 = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        expected = df[(df > 0) & (df2 > 0)]

        result = df.query("(@df > 0) & (@df2 > 0)", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)

        result = pd.eval("df[df > 0 and df2 > 0]", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)

        result = pd.eval(
            "df[df > 0 and df2 > 0 and df[df > 0] > 0]", engine=engine, parser=parser
        )
        expected = df[(df > 0) & (df2 > 0) & (df[df > 0] > 0)]
        tm.assert_frame_equal(result, expected)

        result = pd.eval("df[(df>0) & (df2>0)]", engine=engine, parser=parser)
        expected = df.query("(@df>0) & (@df2>0)", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)

    def test_nested_raises_on_local_self_reference(self, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))

        # can't reference ourself b/c we're a local so @ is necessary
        with pytest.raises(UndefinedVariableError, match="name 'df' is not defined"):
            df.query("df > 0", engine=engine, parser=parser)

    def test_local_syntax(self, engine, parser):
        skip_if_no_pandas_parser(parser)

        df = DataFrame(
            np.random.default_rng(2).standard_normal((100, 10)),
            columns=list("abcdefghij"),
        )
        b = 1
        expect = df[df.a < b]
        result = df.query("a < @b", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expect)

        expect = df[df.a < df.b]
        result = df.query("a < b", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expect)

    def test_chained_cmp_and_in(self, engine, parser):
        skip_if_no_pandas_parser(parser)
        cols = list("abc")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((100, len(cols))), columns=cols
        )
        res = df.query(
            "a < b < c and a not in b not in c", engine=engine, parser=parser
        )
        ind = (df.a < df.b) & (df.b < df.c) & ~df.b.isin(df.a) & ~df.c.isin(df.b)
        expec = df[ind]
        tm.assert_frame_equal(res, expec)

    def test_local_variable_with_in(self, engine, parser):
        skip_if_no_pandas_parser(parser)
        a = Series(np.random.default_rng(2).integers(3, size=15), name="a")
        b = Series(np.random.default_rng(2).integers(10, size=15), name="b")
        df = DataFrame({"a": a, "b": b})

        expected = df.loc[(df.b - 1).isin(a)]
        result = df.query("b - 1 in a", engine=engine, parser=parser)
        tm.assert_frame_equal(expected, result)

        b = Series(np.random.default_rng(2).integers(10, size=15), name="b")
        expected = df.loc[(b - 1).isin(a)]
        result = df.query("@b - 1 in a", engine=engine, parser=parser)
        tm.assert_frame_equal(expected, result)

    def test_at_inside_string(self, engine, parser):
        skip_if_no_pandas_parser(parser)
        c = 1  # noqa: F841
        df = DataFrame({"a": ["a", "a", "b", "b", "@c", "@c"]})
        result = df.query('a == "@c"', engine=engine, parser=parser)
        expected = df[df.a == "@c"]
        tm.assert_frame_equal(result, expected)

    def test_query_undefined_local(self):
        engine, parser = self.engine, self.parser
        skip_if_no_pandas_parser(parser)

        df = DataFrame(np.random.default_rng(2).random((10, 2)), columns=list("ab"))
        with pytest.raises(
            UndefinedVariableError, match="local variable 'c' is not defined"
        ):
            df.query("a == @c", engine=engine, parser=parser)

    def test_index_resolvers_come_after_columns_with_the_same_name(
        self, engine, parser
    ):
        n = 1  # noqa: F841
        a = np.r_[20:101:20]

        df = DataFrame(
            {"index": a, "b": np.random.default_rng(2).standard_normal(a.size)}
        )
        df.index.name = "index"
        result = df.query("index > 5", engine=engine, parser=parser)
        expected = df[df["index"] > 5]
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            {"index": a, "b": np.random.default_rng(2).standard_normal(a.size)}
        )
        result = df.query("ilevel_0 > 5", engine=engine, parser=parser)
        expected = df.loc[df.index[df.index > 5]]
        tm.assert_frame_equal(result, expected)

        df = DataFrame({"a": a, "b": np.random.default_rng(2).standard_normal(a.size)})
        df.index.name = "a"
        result = df.query("a > 5", engine=engine, parser=parser)
        expected = df[df.a > 5]
        tm.assert_frame_equal(result, expected)

        result = df.query("index > 5", engine=engine, parser=parser)
        expected = df.loc[df.index[df.index > 5]]
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("op, f", [["==", operator.eq], ["!=", operator.ne]])
    def test_inf(self, op, f, engine, parser):
        n = 10
        df = DataFrame(
            {
                "a": np.random.default_rng(2).random(n),
                "b": np.random.default_rng(2).random(n),
            }
        )
        df.loc[::2, 0] = np.inf
        q = f"a {op} inf"
        expected = df[f(df.a, np.inf)]
        result = df.query(q, engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)

    def test_check_tz_aware_index_query(self, tz_aware_fixture):
        # https://github.com/pandas-dev/pandas/issues/29463
        tz = tz_aware_fixture
        df_index = date_range(
            start="2019-01-01", freq="1d", periods=10, tz=tz, name="time"
        )
        expected = DataFrame(index=df_index)
        df = DataFrame(index=df_index)
        result = df.query('"2018-01-03 00:00:00+00" < time')
        tm.assert_frame_equal(result, expected)

        expected = DataFrame(df_index)
        result = df.reset_index().query('"2018-01-03 00:00:00+00" < time')
        tm.assert_frame_equal(result, expected)

    def test_method_calls_in_query(self, engine, parser):
        # https://github.com/pandas-dev/pandas/issues/22435
        n = 10
        df = DataFrame(
            {
                "a": 2 * np.random.default_rng(2).random(n),
                "b": np.random.default_rng(2).random(n),
            }
        )
        expected = df[df["a"].astype("int") == 0]
        result = df.query("a.astype('int') == 0", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            {
                "a": np.where(
                    np.random.default_rng(2).random(n) < 0.5,
                    np.nan,
                    np.random.default_rng(2).standard_normal(n),
                ),
                "b": np.random.default_rng(2).standard_normal(n),
            }
        )
        expected = df[df["a"].notnull()]
        result = df.query("a.notnull()", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)


@td.skip_if_no("numexpr")
class TestDataFrameQueryNumExprPython(TestDataFrameQueryNumExprPandas):
    @pytest.fixture
    def engine(self):
        return "numexpr"

    @pytest.fixture
    def parser(self):
        return "python"

    def test_date_query_no_attribute_access(self, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        df["dates1"] = date_range("1/1/2012", periods=5)
        df["dates2"] = date_range("1/1/2013", periods=5)
        df["dates3"] = date_range("1/1/2014", periods=5)
        res = df.query(
            "(dates1 < 20130101) & (20130101 < dates3)", engine=engine, parser=parser
        )
        expec = df[(df.dates1 < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_query_with_NaT(self, engine, parser):
        n = 10
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3)))
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates2"] = date_range("1/1/2013", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        df.loc[np.random.default_rng(2).random(n) > 0.5, "dates1"] = pd.NaT
        df.loc[np.random.default_rng(2).random(n) > 0.5, "dates3"] = pd.NaT
        res = df.query(
            "(dates1 < 20130101) & (20130101 < dates3)", engine=engine, parser=parser
        )
        expec = df[(df.dates1 < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_index_query(self, engine, parser):
        n = 10
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3)))
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        return_value = df.set_index("dates1", inplace=True, drop=True)
        assert return_value is None
        res = df.query(
            "(index < 20130101) & (20130101 < dates3)", engine=engine, parser=parser
        )
        expec = df[(df.index < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_index_query_with_NaT(self, engine, parser):
        n = 10
        # Cast to object to avoid implicit cast when setting entry to pd.NaT below
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3))).astype(
            {0: object}
        )
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        df.iloc[0, 0] = pd.NaT
        return_value = df.set_index("dates1", inplace=True, drop=True)
        assert return_value is None
        res = df.query(
            "(index < 20130101) & (20130101 < dates3)", engine=engine, parser=parser
        )
        expec = df[(df.index < "20130101") & ("20130101" < df.dates3)]
        tm.assert_frame_equal(res, expec)

    def test_date_index_query_with_NaT_duplicates(self, engine, parser):
        n = 10
        df = DataFrame(np.random.default_rng(2).standard_normal((n, 3)))
        df["dates1"] = date_range("1/1/2012", periods=n)
        df["dates3"] = date_range("1/1/2014", periods=n)
        df.loc[np.random.default_rng(2).random(n) > 0.5, "dates1"] = pd.NaT
        return_value = df.set_index("dates1", inplace=True, drop=True)
        assert return_value is None
        msg = r"'BoolOp' nodes are not implemented"
        with pytest.raises(NotImplementedError, match=msg):
            df.query("index < 20130101 < dates3", engine=engine, parser=parser)

    def test_nested_scope(self, engine, parser):
        # smoke test
        x = 1  # noqa: F841
        result = pd.eval("x + 1", engine=engine, parser=parser)
        assert result == 2

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        df2 = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))

        # don't have the pandas parser
        msg = r"The '@' prefix is only supported by the pandas parser"
        with pytest.raises(SyntaxError, match=msg):
            df.query("(@df>0) & (@df2>0)", engine=engine, parser=parser)

        with pytest.raises(UndefinedVariableError, match="name 'df' is not defined"):
            df.query("(df>0) & (df2>0)", engine=engine, parser=parser)

        expected = df[(df > 0) & (df2 > 0)]
        result = pd.eval("df[(df > 0) & (df2 > 0)]", engine=engine, parser=parser)
        tm.assert_frame_equal(expected, result)

        expected = df[(df > 0) & (df2 > 0) & (df[df > 0] > 0)]
        result = pd.eval(
            "df[(df > 0) & (df2 > 0) & (df[df > 0] > 0)]", engine=engine, parser=parser
        )
        tm.assert_frame_equal(expected, result)

    def test_query_numexpr_with_min_and_max_columns(self):
        df = DataFrame({"min": [1, 2, 3], "max": [4, 5, 6]})
        regex_to_match = (
            r"Variables in expression \"\(min\) == \(1\)\" "
            r"overlap with builtins: \('min'\)"
        )
        with pytest.raises(NumExprClobberingError, match=regex_to_match):
            df.query("min == 1")

        regex_to_match = (
            r"Variables in expression \"\(max\) == \(1\)\" "
            r"overlap with builtins: \('max'\)"
        )
        with pytest.raises(NumExprClobberingError, match=regex_to_match):
            df.query("max == 1")


class TestDataFrameQueryPythonPandas(TestDataFrameQueryNumExprPandas):
    @pytest.fixture
    def engine(self):
        return "python"

    @pytest.fixture
    def parser(self):
        return "pandas"

    def test_query_builtin(self, engine, parser):
        n = m = 10
        df = DataFrame(
            np.random.default_rng(2).integers(m, size=(n, 3)), columns=list("abc")
        )

        df.index.name = "sin"
        expected = df[df.index > 5]
        result = df.query("sin > 5", engine=engine, parser=parser)
        tm.assert_frame_equal(expected, result)


class TestDataFrameQueryPythonPython(TestDataFrameQueryNumExprPython):
    @pytest.fixture
    def engine(self):
        return "python"

    @pytest.fixture
    def parser(self):
        return "python"

    def test_query_builtin(self, engine, parser):
        n = m = 10
        df = DataFrame(
            np.random.default_rng(2).integers(m, size=(n, 3)), columns=list("abc")
        )

        df.index.name = "sin"
        expected = df[df.index > 5]
        result = df.query("sin > 5", engine=engine, parser=parser)
        tm.assert_frame_equal(expected, result)


class TestDataFrameQueryStrings:
    def test_str_query_method(self, parser, engine):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 1)), columns=["b"])
        df["strings"] = Series(list("aabbccddee"))
        expect = df[df.strings == "a"]

        if parser != "pandas":
            col = "strings"
            lst = '"a"'

            lhs = [col] * 2 + [lst] * 2
            rhs = lhs[::-1]

            eq, ne = "==", "!="
            ops = 2 * ([eq] + [ne])
            msg = r"'(Not)?In' nodes are not implemented"

            for lhs, op, rhs in zip(lhs, ops, rhs):
                ex = f"{lhs} {op} {rhs}"
                with pytest.raises(NotImplementedError, match=msg):
                    df.query(
                        ex,
                        engine=engine,
                        parser=parser,
                        local_dict={"strings": df.strings},
                    )
        else:
            res = df.query('"a" == strings', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)

            res = df.query('strings == "a"', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)
            tm.assert_frame_equal(res, df[df.strings.isin(["a"])])

            expect = df[df.strings != "a"]
            res = df.query('strings != "a"', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)

            res = df.query('"a" != strings', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)
            tm.assert_frame_equal(res, df[~df.strings.isin(["a"])])

    def test_str_list_query_method(self, parser, engine):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 1)), columns=["b"])
        df["strings"] = Series(list("aabbccddee"))
        expect = df[df.strings.isin(["a", "b"])]

        if parser != "pandas":
            col = "strings"
            lst = '["a", "b"]'

            lhs = [col] * 2 + [lst] * 2
            rhs = lhs[::-1]

            eq, ne = "==", "!="
            ops = 2 * ([eq] + [ne])
            msg = r"'(Not)?In' nodes are not implemented"

            for lhs, op, rhs in zip(lhs, ops, rhs):
                ex = f"{lhs} {op} {rhs}"
                with pytest.raises(NotImplementedError, match=msg):
                    df.query(ex, engine=engine, parser=parser)
        else:
            res = df.query('strings == ["a", "b"]', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)

            res = df.query('["a", "b"] == strings', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)

            expect = df[~df.strings.isin(["a", "b"])]

            res = df.query('strings != ["a", "b"]', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)

            res = df.query('["a", "b"] != strings', engine=engine, parser=parser)
            tm.assert_frame_equal(res, expect)

    def test_query_with_string_columns(self, parser, engine):
        df = DataFrame(
            {
                "a": list("aaaabbbbcccc"),
                "b": list("aabbccddeeff"),
                "c": np.random.default_rng(2).integers(5, size=12),
                "d": np.random.default_rng(2).integers(9, size=12),
            }
        )
        if parser == "pandas":
            res = df.query("a in b", parser=parser, engine=engine)
            expec = df[df.a.isin(df.b)]
            tm.assert_frame_equal(res, expec)

            res = df.query("a in b and c < d", parser=parser, engine=engine)
            expec = df[df.a.isin(df.b) & (df.c < df.d)]
            tm.assert_frame_equal(res, expec)
        else:
            msg = r"'(Not)?In' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                df.query("a in b", parser=parser, engine=engine)

            msg = r"'BoolOp' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                df.query("a in b and c < d", parser=parser, engine=engine)

    def test_object_array_eq_ne(self, parser, engine):
        df = DataFrame(
            {
                "a": list("aaaabbbbcccc"),
                "b": list("aabbccddeeff"),
                "c": np.random.default_rng(2).integers(5, size=12),
                "d": np.random.default_rng(2).integers(9, size=12),
            }
        )
        res = df.query("a == b", parser=parser, engine=engine)
        exp = df[df.a == df.b]
        tm.assert_frame_equal(res, exp)

        res = df.query("a != b", parser=parser, engine=engine)
        exp = df[df.a != df.b]
        tm.assert_frame_equal(res, exp)

    def test_query_with_nested_strings(self, parser, engine):
        skip_if_no_pandas_parser(parser)
        events = [
            f"page {n} {act}" for n in range(1, 4) for act in ["load", "exit"]
        ] * 2
        stamps1 = date_range("2014-01-01 0:00:01", freq="30s", periods=6)
        stamps2 = date_range("2014-02-01 1:00:01", freq="30s", periods=6)
        df = DataFrame(
            {
                "id": np.arange(1, 7).repeat(2),
                "event": events,
                "timestamp": stamps1.append(stamps2),
            }
        )

        expected = df[df.event == '"page 1 load"']
        res = df.query("""'"page 1 load"' in event""", parser=parser, engine=engine)
        tm.assert_frame_equal(expected, res)

    def test_query_with_nested_special_character(self, parser, engine):
        skip_if_no_pandas_parser(parser)
        df = DataFrame({"a": ["a", "b", "test & test"], "b": [1, 2, 3]})
        res = df.query('a == "test & test"', parser=parser, engine=engine)
        expec = df[df.a == "test & test"]
        tm.assert_frame_equal(res, expec)

    @pytest.mark.parametrize(
        "op, func",
        [
            ["<", operator.lt],
            [">", operator.gt],
            ["<=", operator.le],
            [">=", operator.ge],
        ],
    )
    def test_query_lex_compare_strings(self, parser, engine, op, func):
        a = Series(np.random.default_rng(2).choice(list("abcde"), 20))
        b = Series(np.arange(a.size))
        df = DataFrame({"X": a, "Y": b})

        res = df.query(f'X {op} "d"', engine=engine, parser=parser)
        expected = df[func(df.X, "d")]
        tm.assert_frame_equal(res, expected)

    def test_query_single_element_booleans(self, parser, engine):
        columns = "bid", "bidsize", "ask", "asksize"
        data = np.random.default_rng(2).integers(2, size=(1, len(columns))).astype(bool)
        df = DataFrame(data, columns=columns)
        res = df.query("bid & ask", engine=engine, parser=parser)
        expected = df[df.bid & df.ask]
        tm.assert_frame_equal(res, expected)

    def test_query_string_scalar_variable(self, parser, engine):
        skip_if_no_pandas_parser(parser)
        df = DataFrame(
            {
                "Symbol": ["BUD US", "BUD US", "IBM US", "IBM US"],
                "Price": [109.70, 109.72, 183.30, 183.35],
            }
        )
        e = df[df.Symbol == "BUD US"]
        symb = "BUD US"  # noqa: F841
        r = df.query("Symbol == @symb", parser=parser, engine=engine)
        tm.assert_frame_equal(e, r)

    @pytest.mark.parametrize(
        "in_list",
        [
            [None, "asdf", "ghjk"],
            ["asdf", None, "ghjk"],
            ["asdf", "ghjk", None],
            [None, None, "asdf"],
            ["asdf", None, None],
            [None, None, None],
        ],
    )
    def test_query_string_null_elements(self, in_list):
        # GITHUB ISSUE #31516
        parser = "pandas"
        engine = "python"
        expected = {i: value for i, value in enumerate(in_list) if value == "asdf"}

        df_expected = DataFrame({"a": expected}, dtype="string")
        df_expected.index = df_expected.index.astype("int64")
        df = DataFrame({"a": in_list}, dtype="string")
        res1 = df.query("a == 'asdf'", parser=parser, engine=engine)
        res2 = df[df["a"] == "asdf"]
        res3 = df.query("a <= 'asdf'", parser=parser, engine=engine)
        tm.assert_frame_equal(res1, df_expected)
        tm.assert_frame_equal(res1, res2)
        tm.assert_frame_equal(res1, res3)
        tm.assert_frame_equal(res2, res3)


class TestDataFrameEvalWithFrame:
    @pytest.fixture
    def frame(self):
        return DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=list("abc")
        )

    def test_simple_expr(self, frame, parser, engine):
        res = frame.eval("a + b", engine=engine, parser=parser)
        expect = frame.a + frame.b
        tm.assert_series_equal(res, expect)

    def test_bool_arith_expr(self, frame, parser, engine):
        res = frame.eval("a[a < 1] + b", engine=engine, parser=parser)
        expect = frame.a[frame.a < 1] + frame.b
        tm.assert_series_equal(res, expect)

    @pytest.mark.parametrize("op", ["+", "-", "*", "/"])
    def test_invalid_type_for_operator_raises(self, parser, engine, op):
        df = DataFrame({"a": [1, 2], "b": ["c", "d"]})
        msg = r"unsupported operand type\(s\) for .+: '.+' and '.+'|Cannot"

        with pytest.raises(TypeError, match=msg):
            df.eval(f"a {op} b", engine=engine, parser=parser)


class TestDataFrameQueryBacktickQuoting:
    @pytest.fixture
    def df(self):
        """
        Yields a dataframe with strings that may or may not need escaping
        by backticks. The last two columns cannot be escaped by backticks
        and should raise a ValueError.
        """
        yield DataFrame(
            {
                "A": [1, 2, 3],
                "B B": [3, 2, 1],
                "C C": [4, 5, 6],
                "C  C": [7, 4, 3],
                "C_C": [8, 9, 10],
                "D_D D": [11, 1, 101],
                "E.E": [6, 3, 5],
                "F-F": [8, 1, 10],
                "1e1": [2, 4, 8],
                "def": [10, 11, 2],
                "A (x)": [4, 1, 3],
                "B(x)": [1, 1, 5],
                "B (x)": [2, 7, 4],
                "  &^ :!€$?(} >    <++*''  ": [2, 5, 6],
                "": [10, 11, 1],
                " A": [4, 7, 9],
                "  ": [1, 2, 1],
                "it's": [6, 3, 1],
                "that's": [9, 1, 8],
                "☺": [8, 7, 6],
                "foo#bar": [2, 4, 5],
                1: [5, 7, 9],
            }
        )

    def test_single_backtick_variable_query(self, df):
        res = df.query("1 < `B B`")
        expect = df[1 < df["B B"]]
        tm.assert_frame_equal(res, expect)

    def test_two_backtick_variables_query(self, df):
        res = df.query("1 < `B B` and 4 < `C C`")
        expect = df[(1 < df["B B"]) & (4 < df["C C"])]
        tm.assert_frame_equal(res, expect)

    def test_single_backtick_variable_expr(self, df):
        res = df.eval("A + `B B`")
        expect = df["A"] + df["B B"]
        tm.assert_series_equal(res, expect)

    def test_two_backtick_variables_expr(self, df):
        res = df.eval("`B B` + `C C`")
        expect = df["B B"] + df["C C"]
        tm.assert_series_equal(res, expect)

    def test_already_underscore_variable(self, df):
        res = df.eval("`C_C` + A")
        expect = df["C_C"] + df["A"]
        tm.assert_series_equal(res, expect)

    def test_same_name_but_underscores(self, df):
        res = df.eval("C_C + `C C`")
        expect = df["C_C"] + df["C C"]
        tm.assert_series_equal(res, expect)

    def test_mixed_underscores_and_spaces(self, df):
        res = df.eval("A + `D_D D`")
        expect = df["A"] + df["D_D D"]
        tm.assert_series_equal(res, expect)

    def test_backtick_quote_name_with_no_spaces(self, df):
        res = df.eval("A + `C_C`")
        expect = df["A"] + df["C_C"]
        tm.assert_series_equal(res, expect)

    def test_special_characters(self, df):
        res = df.eval("`E.E` + `F-F` - A")
        expect = df["E.E"] + df["F-F"] - df["A"]
        tm.assert_series_equal(res, expect)

    def test_start_with_digit(self, df):
        res = df.eval("A + `1e1`")
        expect = df["A"] + df["1e1"]
        tm.assert_series_equal(res, expect)

    def test_keyword(self, df):
        res = df.eval("A + `def`")
        expect = df["A"] + df["def"]
        tm.assert_series_equal(res, expect)

    def test_unneeded_quoting(self, df):
        res = df.query("`A` > 2")
        expect = df[df["A"] > 2]
        tm.assert_frame_equal(res, expect)

    def test_parenthesis(self, df):
        res = df.query("`A (x)` > 2")
        expect = df[df["A (x)"] > 2]
        tm.assert_frame_equal(res, expect)

    def test_empty_string(self, df):
        res = df.query("`` > 5")
        expect = df[df[""] > 5]
        tm.assert_frame_equal(res, expect)

    def test_multiple_spaces(self, df):
        res = df.query("`C  C` > 5")
        expect = df[df["C  C"] > 5]
        tm.assert_frame_equal(res, expect)

    def test_start_with_spaces(self, df):
        res = df.eval("` A` + `  `")
        expect = df[" A"] + df["  "]
        tm.assert_series_equal(res, expect)

    def test_lots_of_operators_string(self, df):
        res = df.query("`  &^ :!€$?(} >    <++*''  ` > 4")
        expect = df[df["  &^ :!€$?(} >    <++*''  "] > 4]
        tm.assert_frame_equal(res, expect)

    def test_missing_attribute(self, df):
        message = "module 'pandas' has no attribute 'thing'"
        with pytest.raises(AttributeError, match=message):
            df.eval("@pd.thing")

    def test_failing_quote(self, df):
        msg = r"(Could not convert ).*( to a valid Python identifier.)"
        with pytest.raises(SyntaxError, match=msg):
            df.query("`it's` > `that's`")

    def test_failing_character_outside_range(self, df):
        msg = r"(Could not convert ).*( to a valid Python identifier.)"
        with pytest.raises(SyntaxError, match=msg):
            df.query("`☺` > 4")

    def test_failing_hashtag(self, df):
        msg = "Failed to parse backticks"
        with pytest.raises(SyntaxError, match=msg):
            df.query("`foo#bar` > 4")

    def test_call_non_named_expression(self, df):
        """
        Only attributes and variables ('named functions') can be called.
        .__call__() is not an allowed attribute because that would allow
        calling anything.
        https://github.com/pandas-dev/pandas/pull/32460
        """

        def func(*_):
            return 1

        funcs = [func]  # noqa: F841

        df.eval("@func()")

        with pytest.raises(TypeError, match="Only named functions are supported"):
            df.eval("@funcs[0]()")

        with pytest.raises(TypeError, match="Only named functions are supported"):
            df.eval("@funcs[0].__call__()")

    def test_ea_dtypes(self, any_numeric_ea_and_arrow_dtype):
        # GH#29618
        df = DataFrame(
            [[1, 2], [3, 4]], columns=["a", "b"], dtype=any_numeric_ea_and_arrow_dtype
        )
        warning = RuntimeWarning if NUMEXPR_INSTALLED else None
        with tm.assert_produces_warning(warning):
            result = df.eval("c = b - a")
        expected = DataFrame(
            [[1, 2, 1], [3, 4, 1]],
            columns=["a", "b", "c"],
            dtype=any_numeric_ea_and_arrow_dtype,
        )
        tm.assert_frame_equal(result, expected)

    def test_ea_dtypes_and_scalar(self):
        # GH#29618
        df = DataFrame([[1, 2], [3, 4]], columns=["a", "b"], dtype="Float64")
        warning = RuntimeWarning if NUMEXPR_INSTALLED else None
        with tm.assert_produces_warning(warning):
            result = df.eval("c = b - 1")
        expected = DataFrame(
            [[1, 2, 1], [3, 4, 3]], columns=["a", "b", "c"], dtype="Float64"
        )
        tm.assert_frame_equal(result, expected)

    def test_ea_dtypes_and_scalar_operation(self, any_numeric_ea_and_arrow_dtype):
        # GH#29618
        df = DataFrame(
            [[1, 2], [3, 4]], columns=["a", "b"], dtype=any_numeric_ea_and_arrow_dtype
        )
        result = df.eval("c = 2 - 1")
        expected = DataFrame(
            {
                "a": Series([1, 3], dtype=any_numeric_ea_and_arrow_dtype),
                "b": Series([2, 4], dtype=any_numeric_ea_and_arrow_dtype),
                "c": Series([1, 1], dtype=result["c"].dtype),
            }
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", ["int64", "Int64", "int64[pyarrow]"])
    def test_query_ea_dtypes(self, dtype):
        if dtype == "int64[pyarrow]":
            pytest.importorskip("pyarrow")
        # GH#50261
        df = DataFrame({"a": Series([1, 2], dtype=dtype)})
        ref = {2}  # noqa: F841
        warning = RuntimeWarning if dtype == "Int64" and NUMEXPR_INSTALLED else None
        with tm.assert_produces_warning(warning):
            result = df.query("a in @ref")
        expected = DataFrame({"a": Series([2], dtype=dtype, index=[1])})
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("engine", ["python", "numexpr"])
    @pytest.mark.parametrize("dtype", ["int64", "Int64", "int64[pyarrow]"])
    def test_query_ea_equality_comparison(self, dtype, engine):
        # GH#50261
        warning = RuntimeWarning if engine == "numexpr" else None
        if engine == "numexpr" and not NUMEXPR_INSTALLED:
            pytest.skip("numexpr not installed")
        if dtype == "int64[pyarrow]":
            pytest.importorskip("pyarrow")
        df = DataFrame(
            {"A": Series([1, 1, 2], dtype="Int64"), "B": Series([1, 2, 2], dtype=dtype)}
        )
        with tm.assert_produces_warning(warning):
            result = df.query("A == B", engine=engine)
        expected = DataFrame(
            {
                "A": Series([1, 2], dtype="Int64", index=[0, 2]),
                "B": Series([1, 2], dtype=dtype, index=[0, 2]),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_all_nat_in_object(self):
        # GH#57068
        now = pd.Timestamp.now("UTC")  # noqa: F841
        df = DataFrame({"a": pd.to_datetime([None, None], utc=True)}, dtype=object)
        result = df.query("a > @now")
        expected = DataFrame({"a": []}, dtype=object)
        tm.assert_frame_equal(result, expected)
