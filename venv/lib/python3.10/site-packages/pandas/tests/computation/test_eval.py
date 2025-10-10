from __future__ import annotations

from functools import reduce
from itertools import product
import operator

import numpy as np
import pytest

from pandas.compat import PY312
from pandas.compat._optional import import_optional_dependency
from pandas.errors import (
    NumExprClobberingError,
    PerformanceWarning,
    UndefinedVariableError,
)
import pandas.util._test_decorators as td

from pandas.core.dtypes.common import (
    is_bool,
    is_float,
    is_list_like,
    is_scalar,
)

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    date_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core.computation import (
    expr,
    pytables,
)
from pandas.core.computation.engines import ENGINES
from pandas.core.computation.expr import (
    BaseExprVisitor,
    PandasExprVisitor,
    PythonExprVisitor,
)
from pandas.core.computation.expressions import (
    NUMEXPR_INSTALLED,
    USE_NUMEXPR,
)
from pandas.core.computation.ops import (
    ARITH_OPS_SYMS,
    SPECIAL_CASE_ARITH_OPS_SYMS,
    _binary_math_ops,
    _binary_ops_dict,
    _unary_math_ops,
)
from pandas.core.computation.scope import DEFAULT_GLOBALS
from pandas.util.version import Version

numexpr = import_optional_dependency("numexpr", errors="ignore")


@pytest.fixture(
    params=(
        pytest.param(
            engine,
            marks=[
                pytest.mark.skipif(
                    engine == "numexpr" and not USE_NUMEXPR,
                    reason=f"numexpr enabled->{USE_NUMEXPR}, "
                    f"installed->{NUMEXPR_INSTALLED}",
                ),
                td.skip_if_no("numexpr"),
            ],
        )
        for engine in ENGINES
    )
)
def engine(request):
    return request.param


@pytest.fixture(params=expr.PARSERS)
def parser(request):
    return request.param


def _eval_single_bin(lhs, cmp1, rhs, engine):
    c = _binary_ops_dict[cmp1]
    if ENGINES[engine].has_neg_frac:
        try:
            return c(lhs, rhs)
        except ValueError as e:
            if str(e).startswith(
                "negative number cannot be raised to a fractional power"
            ):
                return np.nan
            raise
    return c(lhs, rhs)


# TODO: using range(5) here is a kludge
@pytest.fixture(
    params=list(range(5)),
    ids=["DataFrame", "Series", "SeriesNaN", "DataFrameNaN", "float"],
)
def lhs(request):
    nan_df1 = DataFrame(np.random.default_rng(2).standard_normal((10, 5)))
    nan_df1[nan_df1 > 0.5] = np.nan

    opts = (
        DataFrame(np.random.default_rng(2).standard_normal((10, 5))),
        Series(np.random.default_rng(2).standard_normal(5)),
        Series([1, 2, np.nan, np.nan, 5]),
        nan_df1,
        np.random.default_rng(2).standard_normal(),
    )
    return opts[request.param]


rhs = lhs
midhs = lhs


@pytest.fixture
def idx_func_dict():
    return {
        "i": lambda n: Index(np.arange(n), dtype=np.int64),
        "f": lambda n: Index(np.arange(n), dtype=np.float64),
        "s": lambda n: Index([f"{i}_{chr(i)}" for i in range(97, 97 + n)]),
        "dt": lambda n: date_range("2020-01-01", periods=n),
        "td": lambda n: timedelta_range("1 day", periods=n),
        "p": lambda n: period_range("2020-01-01", periods=n, freq="D"),
    }


class TestEval:
    @pytest.mark.parametrize(
        "cmp1",
        ["!=", "==", "<=", ">=", "<", ">"],
        ids=["ne", "eq", "le", "ge", "lt", "gt"],
    )
    @pytest.mark.parametrize("cmp2", [">", "<"], ids=["gt", "lt"])
    @pytest.mark.parametrize("binop", expr.BOOL_OPS_SYMS)
    def test_complex_cmp_ops(self, cmp1, cmp2, binop, lhs, rhs, engine, parser):
        if parser == "python" and binop in ["and", "or"]:
            msg = "'BoolOp' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                ex = f"(lhs {cmp1} rhs) {binop} (lhs {cmp2} rhs)"
                pd.eval(ex, engine=engine, parser=parser)
            return

        lhs_new = _eval_single_bin(lhs, cmp1, rhs, engine)
        rhs_new = _eval_single_bin(lhs, cmp2, rhs, engine)
        expected = _eval_single_bin(lhs_new, binop, rhs_new, engine)

        ex = f"(lhs {cmp1} rhs) {binop} (lhs {cmp2} rhs)"
        result = pd.eval(ex, engine=engine, parser=parser)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("cmp_op", expr.CMP_OPS_SYMS)
    def test_simple_cmp_ops(self, cmp_op, lhs, rhs, engine, parser):
        lhs = lhs < 0
        rhs = rhs < 0

        if parser == "python" and cmp_op in ["in", "not in"]:
            msg = "'(In|NotIn)' nodes are not implemented"

            with pytest.raises(NotImplementedError, match=msg):
                ex = f"lhs {cmp_op} rhs"
                pd.eval(ex, engine=engine, parser=parser)
            return

        ex = f"lhs {cmp_op} rhs"
        msg = "|".join(
            [
                r"only list-like( or dict-like)? objects are allowed to be "
                r"passed to (DataFrame\.)?isin\(\), you passed a "
                r"(`|')bool(`|')",
                "argument of type 'bool' is not iterable",
            ]
        )
        if cmp_op in ("in", "not in") and not is_list_like(rhs):
            with pytest.raises(TypeError, match=msg):
                pd.eval(
                    ex,
                    engine=engine,
                    parser=parser,
                    local_dict={"lhs": lhs, "rhs": rhs},
                )
        else:
            expected = _eval_single_bin(lhs, cmp_op, rhs, engine)
            result = pd.eval(ex, engine=engine, parser=parser)
            tm.assert_equal(result, expected)

    @pytest.mark.parametrize("op", expr.CMP_OPS_SYMS)
    def test_compound_invert_op(self, op, lhs, rhs, request, engine, parser):
        if parser == "python" and op in ["in", "not in"]:
            msg = "'(In|NotIn)' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                ex = f"~(lhs {op} rhs)"
                pd.eval(ex, engine=engine, parser=parser)
            return

        if (
            is_float(lhs)
            and not is_float(rhs)
            and op in ["in", "not in"]
            and engine == "python"
            and parser == "pandas"
        ):
            mark = pytest.mark.xfail(
                reason="Looks like expected is negative, unclear whether "
                "expected is incorrect or result is incorrect"
            )
            request.applymarker(mark)
        skip_these = ["in", "not in"]
        ex = f"~(lhs {op} rhs)"

        msg = "|".join(
            [
                r"only list-like( or dict-like)? objects are allowed to be "
                r"passed to (DataFrame\.)?isin\(\), you passed a "
                r"(`|')float(`|')",
                "argument of type 'float' is not iterable",
            ]
        )
        if is_scalar(rhs) and op in skip_these:
            with pytest.raises(TypeError, match=msg):
                pd.eval(
                    ex,
                    engine=engine,
                    parser=parser,
                    local_dict={"lhs": lhs, "rhs": rhs},
                )
        else:
            # compound
            if is_scalar(lhs) and is_scalar(rhs):
                lhs, rhs = (np.array([x]) for x in (lhs, rhs))
            expected = _eval_single_bin(lhs, op, rhs, engine)
            if is_scalar(expected):
                expected = not expected
            else:
                expected = ~expected
            result = pd.eval(ex, engine=engine, parser=parser)
            tm.assert_almost_equal(expected, result)

    @pytest.mark.parametrize("cmp1", ["<", ">"])
    @pytest.mark.parametrize("cmp2", ["<", ">"])
    def test_chained_cmp_op(self, cmp1, cmp2, lhs, midhs, rhs, engine, parser):
        mid = midhs
        if parser == "python":
            ex1 = f"lhs {cmp1} mid {cmp2} rhs"
            msg = "'BoolOp' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(ex1, engine=engine, parser=parser)
            return

        lhs_new = _eval_single_bin(lhs, cmp1, mid, engine)
        rhs_new = _eval_single_bin(mid, cmp2, rhs, engine)

        if lhs_new is not None and rhs_new is not None:
            ex1 = f"lhs {cmp1} mid {cmp2} rhs"
            ex2 = f"lhs {cmp1} mid and mid {cmp2} rhs"
            ex3 = f"(lhs {cmp1} mid) & (mid {cmp2} rhs)"
            expected = _eval_single_bin(lhs_new, "&", rhs_new, engine)

            for ex in (ex1, ex2, ex3):
                result = pd.eval(ex, engine=engine, parser=parser)

                tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize(
        "arith1", sorted(set(ARITH_OPS_SYMS).difference(SPECIAL_CASE_ARITH_OPS_SYMS))
    )
    def test_binary_arith_ops(self, arith1, lhs, rhs, engine, parser):
        ex = f"lhs {arith1} rhs"
        result = pd.eval(ex, engine=engine, parser=parser)
        expected = _eval_single_bin(lhs, arith1, rhs, engine)

        tm.assert_almost_equal(result, expected)
        ex = f"lhs {arith1} rhs {arith1} rhs"
        result = pd.eval(ex, engine=engine, parser=parser)
        nlhs = _eval_single_bin(lhs, arith1, rhs, engine)
        try:
            nlhs, ghs = nlhs.align(rhs)
        except (ValueError, TypeError, AttributeError):
            # ValueError: series frame or frame series align
            # TypeError, AttributeError: series or frame with scalar align
            return
        else:
            if engine == "numexpr":
                import numexpr as ne

                # direct numpy comparison
                expected = ne.evaluate(f"nlhs {arith1} ghs")
                # Update assert statement due to unreliable numerical
                # precision component (GH37328)
                # TODO: update testing code so that assert_almost_equal statement
                #  can be replaced again by the assert_numpy_array_equal statement
                tm.assert_almost_equal(result.values, expected)
            else:
                expected = eval(f"nlhs {arith1} ghs")
                tm.assert_almost_equal(result, expected)

    # modulus, pow, and floor division require special casing

    def test_modulus(self, lhs, rhs, engine, parser):
        ex = r"lhs % rhs"
        result = pd.eval(ex, engine=engine, parser=parser)
        expected = lhs % rhs
        tm.assert_almost_equal(result, expected)

        if engine == "numexpr":
            import numexpr as ne

            expected = ne.evaluate(r"expected % rhs")
            if isinstance(result, (DataFrame, Series)):
                tm.assert_almost_equal(result.values, expected)
            else:
                tm.assert_almost_equal(result, expected.item())
        else:
            expected = _eval_single_bin(expected, "%", rhs, engine)
            tm.assert_almost_equal(result, expected)

    def test_floor_division(self, lhs, rhs, engine, parser):
        ex = "lhs // rhs"

        if engine == "python" or (
            engine == "numexpr" and Version(numexpr.__version__) >= Version("2.13.0")
        ):
            res = pd.eval(ex, engine=engine, parser=parser)
            expected = lhs // rhs
            tm.assert_equal(res, expected)
        else:
            msg = (
                r"unsupported operand type\(s\) for //: 'VariableNode' and "
                "'VariableNode'"
            )
            with pytest.raises(TypeError, match=msg):
                pd.eval(
                    ex,
                    local_dict={"lhs": lhs, "rhs": rhs},
                    engine=engine,
                    parser=parser,
                )

    @td.skip_if_windows
    def test_pow(self, lhs, rhs, engine, parser):
        # odd failure on win32 platform, so skip
        ex = "lhs ** rhs"
        expected = _eval_single_bin(lhs, "**", rhs, engine)
        result = pd.eval(ex, engine=engine, parser=parser)

        if (
            is_scalar(lhs)
            and is_scalar(rhs)
            and isinstance(expected, (complex, np.complexfloating))
            and np.isnan(result)
        ):
            msg = "(DataFrame.columns|numpy array) are different"
            with pytest.raises(AssertionError, match=msg):
                tm.assert_numpy_array_equal(result, expected)
        else:
            tm.assert_almost_equal(result, expected)

            ex = "(lhs ** rhs) ** rhs"
            result = pd.eval(ex, engine=engine, parser=parser)

            middle = _eval_single_bin(lhs, "**", rhs, engine)
            expected = _eval_single_bin(middle, "**", rhs, engine)
            tm.assert_almost_equal(result, expected)

    def test_check_single_invert_op(self, lhs, engine, parser):
        # simple
        try:
            elb = lhs.astype(bool)
        except AttributeError:
            elb = np.array([bool(lhs)])
        expected = ~elb
        result = pd.eval("~elb", engine=engine, parser=parser)
        tm.assert_almost_equal(expected, result)

    def test_frame_invert(self, engine, parser):
        expr = "~lhs"

        # ~ ##
        # frame
        # float always raises
        lhs = DataFrame(np.random.default_rng(2).standard_normal((5, 2)))
        if engine == "numexpr":
            msg = "couldn't find matching opcode for 'invert_dd'"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            msg = "ufunc 'invert' not supported for the input types"
            with pytest.raises(TypeError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)

        # int raises on numexpr
        lhs = DataFrame(np.random.default_rng(2).integers(5, size=(5, 2)))
        if engine == "numexpr" and Version(numexpr.__version__) < Version("2.13.0"):
            msg = "couldn't find matching opcode for 'invert"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            expect = ~lhs
            result = pd.eval(expr, engine=engine, parser=parser)
            tm.assert_frame_equal(expect, result)

        # bool always works
        lhs = DataFrame(np.random.default_rng(2).standard_normal((5, 2)) > 0.5)
        expect = ~lhs
        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_frame_equal(expect, result)

        # object raises
        lhs = DataFrame(
            {"b": ["a", 1, 2.0], "c": np.random.default_rng(2).standard_normal(3) > 0.5}
        )
        if engine == "numexpr":
            with pytest.raises(ValueError, match="unknown type object"):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            msg = "bad operand type for unary ~: 'str'"
            with pytest.raises(TypeError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)

    def test_series_invert(self, engine, parser):
        # ~ ####
        expr = "~lhs"

        # series
        # float raises
        lhs = Series(np.random.default_rng(2).standard_normal(5))
        if engine == "numexpr":
            msg = "couldn't find matching opcode for 'invert_dd'"
            with pytest.raises(NotImplementedError, match=msg):
                result = pd.eval(expr, engine=engine, parser=parser)
        else:
            msg = "ufunc 'invert' not supported for the input types"
            with pytest.raises(TypeError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)

        # int raises on numexpr
        lhs = Series(np.random.default_rng(2).integers(5, size=5))
        if engine == "numexpr" and Version(numexpr.__version__) < Version("2.13.0"):
            msg = "couldn't find matching opcode for 'invert"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            expect = ~lhs
            result = pd.eval(expr, engine=engine, parser=parser)
            tm.assert_series_equal(expect, result)

        # bool
        lhs = Series(np.random.default_rng(2).standard_normal(5) > 0.5)
        expect = ~lhs
        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_series_equal(expect, result)

        # float
        # int
        # bool

        # object
        lhs = Series(["a", 1, 2.0])
        if engine == "numexpr":
            with pytest.raises(ValueError, match="unknown type object"):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            msg = "bad operand type for unary ~: 'str'"
            with pytest.raises(TypeError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)

    def test_frame_negate(self, engine, parser):
        expr = "-lhs"

        # float
        lhs = DataFrame(np.random.default_rng(2).standard_normal((5, 2)))
        expect = -lhs
        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_frame_equal(expect, result)

        # int
        lhs = DataFrame(np.random.default_rng(2).integers(5, size=(5, 2)))
        expect = -lhs
        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_frame_equal(expect, result)

        # bool doesn't work with numexpr but works elsewhere
        lhs = DataFrame(np.random.default_rng(2).standard_normal((5, 2)) > 0.5)
        if engine == "numexpr":
            msg = "couldn't find matching opcode for 'neg_bb'"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            expect = -lhs
            result = pd.eval(expr, engine=engine, parser=parser)
            tm.assert_frame_equal(expect, result)

    def test_series_negate(self, engine, parser):
        expr = "-lhs"

        # float
        lhs = Series(np.random.default_rng(2).standard_normal(5))
        expect = -lhs
        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_series_equal(expect, result)

        # int
        lhs = Series(np.random.default_rng(2).integers(5, size=5))
        expect = -lhs
        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_series_equal(expect, result)

        # bool doesn't work with numexpr but works elsewhere
        lhs = Series(np.random.default_rng(2).standard_normal(5) > 0.5)
        if engine == "numexpr":
            msg = "couldn't find matching opcode for 'neg_bb'"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(expr, engine=engine, parser=parser)
        else:
            expect = -lhs
            result = pd.eval(expr, engine=engine, parser=parser)
            tm.assert_series_equal(expect, result)

    @pytest.mark.parametrize(
        "lhs",
        [
            # Float
            DataFrame(np.random.default_rng(2).standard_normal((5, 2))),
            # Int
            DataFrame(np.random.default_rng(2).integers(5, size=(5, 2))),
            # bool doesn't work with numexpr but works elsewhere
            DataFrame(np.random.default_rng(2).standard_normal((5, 2)) > 0.5),
        ],
    )
    def test_frame_pos(self, lhs, engine, parser):
        expr = "+lhs"
        expect = lhs

        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_frame_equal(expect, result)

    @pytest.mark.parametrize(
        "lhs",
        [
            # Float
            Series(np.random.default_rng(2).standard_normal(5)),
            # Int
            Series(np.random.default_rng(2).integers(5, size=5)),
            # bool doesn't work with numexpr but works elsewhere
            Series(np.random.default_rng(2).standard_normal(5) > 0.5),
        ],
    )
    def test_series_pos(self, lhs, engine, parser):
        expr = "+lhs"
        expect = lhs

        result = pd.eval(expr, engine=engine, parser=parser)
        tm.assert_series_equal(expect, result)

    def test_scalar_unary(self, engine, parser):
        msg = "bad operand type for unary ~: 'float'"
        warn = None
        if PY312 and not (engine == "numexpr" and parser == "pandas"):
            warn = DeprecationWarning
        with pytest.raises(TypeError, match=msg):
            pd.eval("~1.0", engine=engine, parser=parser)

        assert pd.eval("-1.0", parser=parser, engine=engine) == -1.0
        assert pd.eval("+1.0", parser=parser, engine=engine) == +1.0
        assert pd.eval("~1", parser=parser, engine=engine) == ~1
        assert pd.eval("-1", parser=parser, engine=engine) == -1
        assert pd.eval("+1", parser=parser, engine=engine) == +1
        with tm.assert_produces_warning(
            warn, match="Bitwise inversion", check_stacklevel=False
        ):
            assert pd.eval("~True", parser=parser, engine=engine) == ~True
        with tm.assert_produces_warning(
            warn, match="Bitwise inversion", check_stacklevel=False
        ):
            assert pd.eval("~False", parser=parser, engine=engine) == ~False
        assert pd.eval("-True", parser=parser, engine=engine) == -True
        assert pd.eval("-False", parser=parser, engine=engine) == -False
        assert pd.eval("+True", parser=parser, engine=engine) == +True
        assert pd.eval("+False", parser=parser, engine=engine) == +False

    def test_unary_in_array(self):
        # GH 11235
        # TODO: 2022-01-29: result return list with numexpr 2.7.3 in CI
        # but cannot reproduce locally
        result = np.array(
            pd.eval("[-True, True, +True, -False, False, +False, -37, 37, ~37, +37]"),
            dtype=np.object_,
        )
        expected = np.array(
            [
                -True,
                True,
                +True,
                -False,
                False,
                +False,
                -37,
                37,
                ~37,
                +37,
            ],
            dtype=np.object_,
        )
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("expr", ["x < -0.1", "-5 > x"])
    def test_float_comparison_bin_op(self, float_numpy_dtype, expr):
        # GH 16363
        df = DataFrame({"x": np.array([0], dtype=float_numpy_dtype)})
        res = df.eval(expr)
        assert res.values == np.array([False])

    def test_unary_in_function(self):
        # GH 46471
        df = DataFrame({"x": [0, 1, np.nan]})

        result = df.eval("x.fillna(-1)")
        expected = df.x.fillna(-1)
        # column name becomes None if using numexpr
        # only check names when the engine is not numexpr
        tm.assert_series_equal(result, expected, check_names=not USE_NUMEXPR)

        result = df.eval("x.shift(1, fill_value=-1)")
        expected = df.x.shift(1, fill_value=-1)
        tm.assert_series_equal(result, expected, check_names=not USE_NUMEXPR)

    @pytest.mark.parametrize(
        "ex",
        (
            "1 or 2",
            "1 and 2",
            "a and b",
            "a or b",
            "1 or 2 and (3 + 2) > 3",
            "2 * x > 2 or 1 and 2",
            "2 * df > 3 and 1 or a",
        ),
    )
    def test_disallow_scalar_bool_ops(self, ex, engine, parser):
        x, a, b = np.random.default_rng(2).standard_normal(3), 1, 2  # noqa: F841
        df = DataFrame(np.random.default_rng(2).standard_normal((3, 2)))  # noqa: F841

        msg = "cannot evaluate scalar only bool ops|'BoolOp' nodes are not"
        with pytest.raises(NotImplementedError, match=msg):
            pd.eval(ex, engine=engine, parser=parser)

    def test_identical(self, engine, parser):
        # see gh-10546
        x = 1
        result = pd.eval("x", engine=engine, parser=parser)
        assert result == 1
        assert is_scalar(result)

        x = 1.5
        result = pd.eval("x", engine=engine, parser=parser)
        assert result == 1.5
        assert is_scalar(result)

        x = False
        result = pd.eval("x", engine=engine, parser=parser)
        assert not result
        assert is_bool(result)
        assert is_scalar(result)

        x = np.array([1])
        result = pd.eval("x", engine=engine, parser=parser)
        tm.assert_numpy_array_equal(result, np.array([1]))
        assert result.shape == (1,)

        x = np.array([1.5])
        result = pd.eval("x", engine=engine, parser=parser)
        tm.assert_numpy_array_equal(result, np.array([1.5]))
        assert result.shape == (1,)

        x = np.array([False])  # noqa: F841
        result = pd.eval("x", engine=engine, parser=parser)
        tm.assert_numpy_array_equal(result, np.array([False]))
        assert result.shape == (1,)

    def test_line_continuation(self, engine, parser):
        # GH 11149
        exp = """1 + 2 * \
        5 - 1 + 2 """
        result = pd.eval(exp, engine=engine, parser=parser)
        assert result == 12

    def test_float_truncation(self, engine, parser):
        # GH 14241
        exp = "1000000000.006"
        result = pd.eval(exp, engine=engine, parser=parser)
        expected = np.float64(exp)
        assert result == expected

        df = DataFrame({"A": [1000000000.0009, 1000000000.0011, 1000000000.0015]})
        cutoff = 1000000000.0006
        result = df.query(f"A < {cutoff:.4f}")
        assert result.empty

        cutoff = 1000000000.0010
        result = df.query(f"A > {cutoff:.4f}")
        expected = df.loc[[1, 2], :]
        tm.assert_frame_equal(expected, result)

        exact = 1000000000.0011
        result = df.query(f"A == {exact:.4f}")
        expected = df.loc[[1], :]
        tm.assert_frame_equal(expected, result)

    def test_disallow_python_keywords(self):
        # GH 18221
        df = DataFrame([[0, 0, 0]], columns=["foo", "bar", "class"])
        msg = "Python keyword not valid identifier in numexpr query"
        with pytest.raises(SyntaxError, match=msg):
            df.query("class == 0")

        df = DataFrame()
        df.index.name = "lambda"
        with pytest.raises(SyntaxError, match=msg):
            df.query("lambda == 0")

    def test_true_false_logic(self):
        # GH 25823
        # This behavior is deprecated in Python 3.12
        with tm.maybe_produces_warning(
            DeprecationWarning, PY312, check_stacklevel=False
        ):
            assert pd.eval("not True") == -2
            assert pd.eval("not False") == -1
            assert pd.eval("True and not True") == 0

    def test_and_logic_string_match(self):
        # GH 25823
        event = Series({"a": "hello"})
        assert pd.eval(f"{event.str.match('hello').a}")
        assert pd.eval(f"{event.str.match('hello').a and event.str.match('hello').a}")


# -------------------------------------
# gh-12388: Typecasting rules consistency with python


class TestTypeCasting:
    @pytest.mark.parametrize("op", ["+", "-", "*", "**", "/"])
    # maybe someday... numexpr has too many upcasting rules now
    # chain(*(np.core.sctypes[x] for x in ['uint', 'int', 'float']))
    @pytest.mark.parametrize("left_right", [("df", "3"), ("3", "df")])
    def test_binop_typecasting(
        self, engine, parser, op, complex_or_float_dtype, left_right, request
    ):
        # GH#21374
        dtype = complex_or_float_dtype
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)), dtype=dtype)
        left, right = left_right
        s = f"{left} {op} {right}"
        res = pd.eval(s, engine=engine, parser=parser)
        if dtype == "complex64" and engine == "numexpr":
            mark = pytest.mark.xfail(
                reason="numexpr issue with complex that are upcast "
                "to complex 128 "
                "https://github.com/pydata/numexpr/issues/492"
            )
            request.applymarker(mark)
        assert df.values.dtype == dtype
        assert res.values.dtype == dtype
        tm.assert_frame_equal(res, eval(s), check_exact=False)


# -------------------------------------
# Basic and complex alignment


def should_warn(*args):
    not_mono = not any(map(operator.attrgetter("is_monotonic_increasing"), args))
    only_one_dt = reduce(
        operator.xor, (issubclass(x.dtype.type, np.datetime64) for x in args)
    )
    return not_mono and only_one_dt


class TestAlignment:
    index_types = ["i", "s", "dt"]
    lhs_index_types = index_types + ["s"]  # 'p'

    def test_align_nested_unary_op(self, engine, parser):
        s = "df * ~2"
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        res = pd.eval(s, engine=engine, parser=parser)
        tm.assert_frame_equal(res, df * ~2)

    @pytest.mark.filterwarnings("always::RuntimeWarning")
    @pytest.mark.parametrize("lr_idx_type", lhs_index_types)
    @pytest.mark.parametrize("rr_idx_type", index_types)
    @pytest.mark.parametrize("c_idx_type", index_types)
    def test_basic_frame_alignment(
        self, engine, parser, lr_idx_type, rr_idx_type, c_idx_type, idx_func_dict
    ):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 10)),
            index=idx_func_dict[lr_idx_type](10),
            columns=idx_func_dict[c_idx_type](10),
        )
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((20, 10)),
            index=idx_func_dict[rr_idx_type](20),
            columns=idx_func_dict[c_idx_type](10),
        )
        # only warns if not monotonic and not sortable
        if should_warn(df.index, df2.index):
            with tm.assert_produces_warning(RuntimeWarning):
                res = pd.eval("df + df2", engine=engine, parser=parser)
        else:
            res = pd.eval("df + df2", engine=engine, parser=parser)
        tm.assert_frame_equal(res, df + df2)

    @pytest.mark.parametrize("r_idx_type", lhs_index_types)
    @pytest.mark.parametrize("c_idx_type", lhs_index_types)
    def test_frame_comparison(
        self, engine, parser, r_idx_type, c_idx_type, idx_func_dict
    ):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 10)),
            index=idx_func_dict[r_idx_type](10),
            columns=idx_func_dict[c_idx_type](10),
        )
        res = pd.eval("df < 2", engine=engine, parser=parser)
        tm.assert_frame_equal(res, df < 2)

        df3 = DataFrame(
            np.random.default_rng(2).standard_normal(df.shape),
            index=df.index,
            columns=df.columns,
        )
        res = pd.eval("df < df3", engine=engine, parser=parser)
        tm.assert_frame_equal(res, df < df3)

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.parametrize("r1", lhs_index_types)
    @pytest.mark.parametrize("c1", index_types)
    @pytest.mark.parametrize("r2", index_types)
    @pytest.mark.parametrize("c2", index_types)
    def test_medium_complex_frame_alignment(
        self, engine, parser, r1, c1, r2, c2, idx_func_dict
    ):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 2)),
            index=idx_func_dict[r1](3),
            columns=idx_func_dict[c1](2),
        )
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((4, 2)),
            index=idx_func_dict[r2](4),
            columns=idx_func_dict[c2](2),
        )
        df3 = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)),
            index=idx_func_dict[r2](5),
            columns=idx_func_dict[c2](2),
        )
        if should_warn(df.index, df2.index, df3.index):
            with tm.assert_produces_warning(RuntimeWarning):
                res = pd.eval("df + df2 + df3", engine=engine, parser=parser)
        else:
            res = pd.eval("df + df2 + df3", engine=engine, parser=parser)
        tm.assert_frame_equal(res, df + df2 + df3)

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.parametrize("index_name", ["index", "columns"])
    @pytest.mark.parametrize("c_idx_type", index_types)
    @pytest.mark.parametrize("r_idx_type", lhs_index_types)
    def test_basic_frame_series_alignment(
        self, engine, parser, index_name, r_idx_type, c_idx_type, idx_func_dict
    ):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 10)),
            index=idx_func_dict[r_idx_type](10),
            columns=idx_func_dict[c_idx_type](10),
        )
        index = getattr(df, index_name)
        s = Series(np.random.default_rng(2).standard_normal(5), index[:5])

        if should_warn(df.index, s.index):
            with tm.assert_produces_warning(RuntimeWarning):
                res = pd.eval("df + s", engine=engine, parser=parser)
        else:
            res = pd.eval("df + s", engine=engine, parser=parser)

        if r_idx_type == "dt" or c_idx_type == "dt":
            expected = df.add(s) if engine == "numexpr" else df + s
        else:
            expected = df + s
        tm.assert_frame_equal(res, expected)

    @pytest.mark.parametrize("index_name", ["index", "columns"])
    @pytest.mark.parametrize(
        "r_idx_type, c_idx_type",
        list(product(["i", "s"], ["i", "s"])) + [("dt", "dt")],
    )
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_basic_series_frame_alignment(
        self, request, engine, parser, index_name, r_idx_type, c_idx_type, idx_func_dict
    ):
        if (
            engine == "numexpr"
            and parser in ("pandas", "python")
            and index_name == "index"
            and r_idx_type == "i"
            and c_idx_type == "s"
        ):
            reason = (
                f"Flaky column ordering when engine={engine}, "
                f"parser={parser}, index_name={index_name}, "
                f"r_idx_type={r_idx_type}, c_idx_type={c_idx_type}"
            )
            request.applymarker(pytest.mark.xfail(reason=reason, strict=False))
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 7)),
            index=idx_func_dict[r_idx_type](10),
            columns=idx_func_dict[c_idx_type](7),
        )
        index = getattr(df, index_name)
        s = Series(np.random.default_rng(2).standard_normal(5), index[:5])
        if should_warn(s.index, df.index):
            with tm.assert_produces_warning(RuntimeWarning):
                res = pd.eval("s + df", engine=engine, parser=parser)
        else:
            res = pd.eval("s + df", engine=engine, parser=parser)

        if r_idx_type == "dt" or c_idx_type == "dt":
            expected = df.add(s) if engine == "numexpr" else s + df
        else:
            expected = s + df
        tm.assert_frame_equal(res, expected)

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.parametrize("c_idx_type", index_types)
    @pytest.mark.parametrize("r_idx_type", lhs_index_types)
    @pytest.mark.parametrize("index_name", ["index", "columns"])
    @pytest.mark.parametrize("op", ["+", "*"])
    def test_series_frame_commutativity(
        self, engine, parser, index_name, op, r_idx_type, c_idx_type, idx_func_dict
    ):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 10)),
            index=idx_func_dict[r_idx_type](10),
            columns=idx_func_dict[c_idx_type](10),
        )
        index = getattr(df, index_name)
        s = Series(np.random.default_rng(2).standard_normal(5), index[:5])

        lhs = f"s {op} df"
        rhs = f"df {op} s"
        if should_warn(df.index, s.index):
            with tm.assert_produces_warning(RuntimeWarning):
                a = pd.eval(lhs, engine=engine, parser=parser)
            with tm.assert_produces_warning(RuntimeWarning):
                b = pd.eval(rhs, engine=engine, parser=parser)
        else:
            a = pd.eval(lhs, engine=engine, parser=parser)
            b = pd.eval(rhs, engine=engine, parser=parser)

        if r_idx_type != "dt" and c_idx_type != "dt":
            if engine == "numexpr":
                tm.assert_frame_equal(a, b)

    @pytest.mark.filterwarnings("always::RuntimeWarning")
    @pytest.mark.parametrize("r1", lhs_index_types)
    @pytest.mark.parametrize("c1", index_types)
    @pytest.mark.parametrize("r2", index_types)
    @pytest.mark.parametrize("c2", index_types)
    def test_complex_series_frame_alignment(
        self, engine, parser, r1, c1, r2, c2, idx_func_dict
    ):
        n = 3
        m1 = 5
        m2 = 2 * m1
        df = DataFrame(
            np.random.default_rng(2).standard_normal((m1, n)),
            index=idx_func_dict[r1](m1),
            columns=idx_func_dict[c1](n),
        )
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((m2, n)),
            index=idx_func_dict[r2](m2),
            columns=idx_func_dict[c2](n),
        )
        index = df2.columns
        ser = Series(np.random.default_rng(2).standard_normal(n), index[:n])

        if r2 == "dt" or c2 == "dt":
            if engine == "numexpr":
                expected2 = df2.add(ser)
            else:
                expected2 = df2 + ser
        else:
            expected2 = df2 + ser

        if r1 == "dt" or c1 == "dt":
            if engine == "numexpr":
                expected = expected2.add(df)
            else:
                expected = expected2 + df
        else:
            expected = expected2 + df

        if should_warn(df2.index, ser.index, df.index):
            with tm.assert_produces_warning(RuntimeWarning):
                res = pd.eval("df2 + ser + df", engine=engine, parser=parser)
        else:
            res = pd.eval("df2 + ser + df", engine=engine, parser=parser)
        assert res.shape == expected.shape
        tm.assert_frame_equal(res, expected)

    def test_performance_warning_for_poor_alignment(self, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((1000, 10)))
        s = Series(np.random.default_rng(2).standard_normal(10000))
        if engine == "numexpr":
            seen = PerformanceWarning
        else:
            seen = False

        with tm.assert_produces_warning(seen):
            pd.eval("df + s", engine=engine, parser=parser)

        s = Series(np.random.default_rng(2).standard_normal(1000))
        with tm.assert_produces_warning(False):
            pd.eval("df + s", engine=engine, parser=parser)

        df = DataFrame(np.random.default_rng(2).standard_normal((10, 10000)))
        s = Series(np.random.default_rng(2).standard_normal(10000))
        with tm.assert_produces_warning(False):
            pd.eval("df + s", engine=engine, parser=parser)

        df = DataFrame(np.random.default_rng(2).standard_normal((10, 10)))
        s = Series(np.random.default_rng(2).standard_normal(10000))

        is_python_engine = engine == "python"

        if not is_python_engine:
            wrn = PerformanceWarning
        else:
            wrn = False

        with tm.assert_produces_warning(wrn) as w:
            pd.eval("df + s", engine=engine, parser=parser)

            if not is_python_engine:
                assert len(w) == 1
                msg = str(w[0].message)
                logged = np.log10(s.size - df.shape[1])
                expected = (
                    f"Alignment difference on axis 1 is larger "
                    f"than an order of magnitude on term 'df', "
                    f"by more than {logged:.4g}; performance may suffer."
                )
                assert msg == expected


# ------------------------------------
# Slightly more complex ops


class TestOperations:
    def eval(self, *args, **kwargs):
        kwargs["level"] = kwargs.pop("level", 0) + 1
        return pd.eval(*args, **kwargs)

    def test_simple_arith_ops(self, engine, parser):
        exclude_arith = []
        if parser == "python":
            exclude_arith = ["in", "not in"]

        arith_ops = [
            op
            for op in expr.ARITH_OPS_SYMS + expr.CMP_OPS_SYMS
            if op not in exclude_arith
        ]

        ops = (op for op in arith_ops if op != "//")

        for op in ops:
            ex = f"1 {op} 1"
            ex2 = f"x {op} 1"
            ex3 = f"1 {op} (x + 1)"

            if op in ("in", "not in"):
                msg = "argument of type 'int' is not iterable"
                with pytest.raises(TypeError, match=msg):
                    pd.eval(ex, engine=engine, parser=parser)
            else:
                expec = _eval_single_bin(1, op, 1, engine)
                x = self.eval(ex, engine=engine, parser=parser)
                assert x == expec

                expec = _eval_single_bin(x, op, 1, engine)
                y = self.eval(ex2, local_dict={"x": x}, engine=engine, parser=parser)
                assert y == expec

                expec = _eval_single_bin(1, op, x + 1, engine)
                y = self.eval(ex3, local_dict={"x": x}, engine=engine, parser=parser)
                assert y == expec

    @pytest.mark.parametrize("rhs", [True, False])
    @pytest.mark.parametrize("lhs", [True, False])
    @pytest.mark.parametrize("op", expr.BOOL_OPS_SYMS)
    def test_simple_bool_ops(self, rhs, lhs, op):
        ex = f"{lhs} {op} {rhs}"

        if parser == "python" and op in ["and", "or"]:
            msg = "'BoolOp' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                self.eval(ex)
            return

        res = self.eval(ex)
        exp = eval(ex)
        assert res == exp

    @pytest.mark.parametrize("rhs", [True, False])
    @pytest.mark.parametrize("lhs", [True, False])
    @pytest.mark.parametrize("op", expr.BOOL_OPS_SYMS)
    def test_bool_ops_with_constants(self, rhs, lhs, op):
        ex = f"{lhs} {op} {rhs}"

        if parser == "python" and op in ["and", "or"]:
            msg = "'BoolOp' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                self.eval(ex)
            return

        res = self.eval(ex)
        exp = eval(ex)
        assert res == exp

    def test_4d_ndarray_fails(self):
        x = np.random.default_rng(2).standard_normal((3, 4, 5, 6))
        y = Series(np.random.default_rng(2).standard_normal(10))
        msg = "N-dimensional objects, where N > 2, are not supported with eval"
        with pytest.raises(NotImplementedError, match=msg):
            self.eval("x + y", local_dict={"x": x, "y": y})

    def test_constant(self):
        x = self.eval("1")
        assert x == 1

    def test_single_variable(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2)))
        df2 = self.eval("df", local_dict={"df": df})
        tm.assert_frame_equal(df, df2)

    def test_failing_subscript_with_name_error(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))  # noqa: F841
        with pytest.raises(NameError, match="name 'x' is not defined"):
            self.eval("df[x > 2] > 2")

    def test_lhs_expression_subscript(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        result = self.eval("(df + 1)[df > 2]", local_dict={"df": df})
        expected = (df + 1)[df > 2]
        tm.assert_frame_equal(result, expected)

    def test_attr_expression(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)), columns=list("abc")
        )
        expr1 = "df.a < df.b"
        expec1 = df.a < df.b
        expr2 = "df.a + df.b + df.c"
        expec2 = df.a + df.b + df.c
        expr3 = "df.a + df.b + df.c[df.b < 0]"
        expec3 = df.a + df.b + df.c[df.b < 0]
        exprs = expr1, expr2, expr3
        expecs = expec1, expec2, expec3
        for e, expec in zip(exprs, expecs):
            tm.assert_series_equal(expec, self.eval(e, local_dict={"df": df}))

    def test_assignment_fails(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)), columns=list("abc")
        )
        df2 = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        expr1 = "df = df2"
        msg = "cannot assign without a target object"
        with pytest.raises(ValueError, match=msg):
            self.eval(expr1, local_dict={"df": df, "df2": df2})

    def test_assignment_column_multiple_raise(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        # multiple assignees
        with pytest.raises(SyntaxError, match="invalid syntax"):
            df.eval("d c = a + b")

    def test_assignment_column_invalid_assign(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        # invalid assignees
        msg = "left hand side of an assignment must be a single name"
        with pytest.raises(SyntaxError, match=msg):
            df.eval("d,c = a + b")

    def test_assignment_column_invalid_assign_function_call(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        msg = "cannot assign to function call"
        with pytest.raises(SyntaxError, match=msg):
            df.eval('Timestamp("20131001") = a + b')

    def test_assignment_single_assign_existing(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        # single assignment - existing variable
        expected = df.copy()
        expected["a"] = expected["a"] + expected["b"]
        df.eval("a = a + b", inplace=True)
        tm.assert_frame_equal(df, expected)

    def test_assignment_single_assign_new(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        # single assignment - new variable
        expected = df.copy()
        expected["c"] = expected["a"] + expected["b"]
        df.eval("c = a + b", inplace=True)
        tm.assert_frame_equal(df, expected)

    def test_assignment_single_assign_local_overlap(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        df = df.copy()
        a = 1  # noqa: F841
        df.eval("a = 1 + b", inplace=True)

        expected = df.copy()
        expected["a"] = 1 + expected["b"]
        tm.assert_frame_equal(df, expected)

    def test_assignment_single_assign_name(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )

        a = 1  # noqa: F841
        old_a = df.a.copy()
        df.eval("a = a + b", inplace=True)
        result = old_a + df.b
        tm.assert_series_equal(result, df.a, check_names=False)
        assert result.name is None

    def test_assignment_multiple_raises(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        # multiple assignment
        df.eval("c = a + b", inplace=True)
        msg = "can only assign a single expression"
        with pytest.raises(SyntaxError, match=msg):
            df.eval("c = a = b")

    def test_assignment_explicit(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )
        # explicit targets
        self.eval("c = df.a + df.b", local_dict={"df": df}, target=df, inplace=True)
        expected = df.copy()
        expected["c"] = expected["a"] + expected["b"]
        tm.assert_frame_equal(df, expected)

    def test_column_in(self):
        # GH 11235
        df = DataFrame({"a": [11], "b": [-32]})
        result = df.eval("a in [11, -32]")
        expected = Series([True])
        # TODO: 2022-01-29: Name check failed with numexpr 2.7.3 in CI
        # but cannot reproduce locally
        tm.assert_series_equal(result, expected, check_names=False)

    @pytest.mark.xfail(reason="Unknown: Omitted test_ in name prior.")
    def test_assignment_not_inplace(self):
        # see gh-9297
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 2)), columns=list("ab")
        )

        actual = df.eval("c = a + b", inplace=False)
        assert actual is not None

        expected = df.copy()
        expected["c"] = expected["a"] + expected["b"]
        tm.assert_frame_equal(df, expected)

    def test_multi_line_expression(self, warn_copy_on_write):
        # GH 11149
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        expected = df.copy()

        expected["c"] = expected["a"] + expected["b"]
        expected["d"] = expected["c"] + expected["b"]
        answer = df.eval(
            """
        c = a + b
        d = c + b""",
            inplace=True,
        )
        tm.assert_frame_equal(expected, df)
        assert answer is None

        expected["a"] = expected["a"] - 1
        expected["e"] = expected["a"] + 2
        answer = df.eval(
            """
        a = a - 1
        e = a + 2""",
            inplace=True,
        )
        tm.assert_frame_equal(expected, df)
        assert answer is None

        # multi-line not valid if not all assignments
        msg = "Multi-line expressions are only valid if all expressions contain"
        with pytest.raises(ValueError, match=msg):
            df.eval(
                """
            a = b + 2
            b - 2""",
                inplace=False,
            )

    def test_multi_line_expression_not_inplace(self):
        # GH 11149
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        expected = df.copy()

        expected["c"] = expected["a"] + expected["b"]
        expected["d"] = expected["c"] + expected["b"]
        df = df.eval(
            """
        c = a + b
        d = c + b""",
            inplace=False,
        )
        tm.assert_frame_equal(expected, df)

        expected["a"] = expected["a"] - 1
        expected["e"] = expected["a"] + 2
        df = df.eval(
            """
        a = a - 1
        e = a + 2""",
            inplace=False,
        )
        tm.assert_frame_equal(expected, df)

    def test_multi_line_expression_local_variable(self):
        # GH 15342
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        expected = df.copy()

        local_var = 7
        expected["c"] = expected["a"] * local_var
        expected["d"] = expected["c"] + local_var
        answer = df.eval(
            """
        c = a * @local_var
        d = c + @local_var
        """,
            inplace=True,
        )
        tm.assert_frame_equal(expected, df)
        assert answer is None

    def test_multi_line_expression_callable_local_variable(self):
        # 26426
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        def local_func(a, b):
            return b

        expected = df.copy()
        expected["c"] = expected["a"] * local_func(1, 7)
        expected["d"] = expected["c"] + local_func(1, 7)
        answer = df.eval(
            """
        c = a * @local_func(1, 7)
        d = c + @local_func(1, 7)
        """,
            inplace=True,
        )
        tm.assert_frame_equal(expected, df)
        assert answer is None

    def test_multi_line_expression_callable_local_variable_with_kwargs(self):
        # 26426
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        def local_func(a, b):
            return b

        expected = df.copy()
        expected["c"] = expected["a"] * local_func(b=7, a=1)
        expected["d"] = expected["c"] + local_func(b=7, a=1)
        answer = df.eval(
            """
        c = a * @local_func(b=7, a=1)
        d = c + @local_func(b=7, a=1)
        """,
            inplace=True,
        )
        tm.assert_frame_equal(expected, df)
        assert answer is None

    def test_assignment_in_query(self):
        # GH 8664
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df_orig = df.copy()
        msg = "cannot assign without a target object"
        with pytest.raises(ValueError, match=msg):
            df.query("a = 1")
        tm.assert_frame_equal(df, df_orig)

    def test_query_inplace(self):
        # see gh-11149
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        expected = df.copy()
        expected = expected[expected["a"] == 2]
        df.query("a == 2", inplace=True)
        tm.assert_frame_equal(expected, df)

        df = {}
        expected = {"a": 3}

        self.eval("a = 1 + 2", target=df, inplace=True)
        tm.assert_dict_equal(df, expected)

    @pytest.mark.parametrize("invalid_target", [1, "cat", [1, 2], np.array([]), (1, 3)])
    def test_cannot_item_assign(self, invalid_target):
        msg = "Cannot assign expression output to target"
        expression = "a = 1 + 2"

        with pytest.raises(ValueError, match=msg):
            self.eval(expression, target=invalid_target, inplace=True)

        if hasattr(invalid_target, "copy"):
            with pytest.raises(ValueError, match=msg):
                self.eval(expression, target=invalid_target, inplace=False)

    @pytest.mark.parametrize("invalid_target", [1, "cat", (1, 3)])
    def test_cannot_copy_item(self, invalid_target):
        msg = "Cannot return a copy of the target"
        expression = "a = 1 + 2"

        with pytest.raises(ValueError, match=msg):
            self.eval(expression, target=invalid_target, inplace=False)

    @pytest.mark.parametrize("target", [1, "cat", [1, 2], np.array([]), (1, 3), {1: 2}])
    def test_inplace_no_assignment(self, target):
        expression = "1 + 2"

        assert self.eval(expression, target=target, inplace=False) == 3

        msg = "Cannot operate inplace if there is no assignment"
        with pytest.raises(ValueError, match=msg):
            self.eval(expression, target=target, inplace=True)

    def test_basic_period_index_boolean_expression(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((2, 2)),
            columns=period_range("2020-01-01", freq="D", periods=2),
        )
        e = df < 2
        r = self.eval("df < 2", local_dict={"df": df})
        x = df < 2

        tm.assert_frame_equal(r, e)
        tm.assert_frame_equal(x, e)

    def test_basic_period_index_subscript_expression(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((2, 2)),
            columns=period_range("2020-01-01", freq="D", periods=2),
        )
        r = self.eval("df[df < 2 + 3]", local_dict={"df": df})
        e = df[df < 2 + 3]
        tm.assert_frame_equal(r, e)

    def test_nested_period_index_subscript_expression(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((2, 2)),
            columns=period_range("2020-01-01", freq="D", periods=2),
        )
        r = self.eval("df[df[df < 2] < 2] + df * 2", local_dict={"df": df})
        e = df[df[df < 2] < 2] + df * 2
        tm.assert_frame_equal(r, e)

    def test_date_boolean(self, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        df["dates1"] = date_range("1/1/2012", periods=5)
        res = self.eval(
            "df.dates1 < 20130101",
            local_dict={"df": df},
            engine=engine,
            parser=parser,
        )
        expec = df.dates1 < "20130101"
        tm.assert_series_equal(res, expec, check_names=False)

    def test_simple_in_ops(self, engine, parser):
        if parser != "python":
            res = pd.eval("1 in [1, 2]", engine=engine, parser=parser)
            assert res

            res = pd.eval("2 in (1, 2)", engine=engine, parser=parser)
            assert res

            res = pd.eval("3 in (1, 2)", engine=engine, parser=parser)
            assert not res

            res = pd.eval("3 not in (1, 2)", engine=engine, parser=parser)
            assert res

            res = pd.eval("[3] not in (1, 2)", engine=engine, parser=parser)
            assert res

            res = pd.eval("[3] in ([3], 2)", engine=engine, parser=parser)
            assert res

            res = pd.eval("[[3]] in [[[3]], 2]", engine=engine, parser=parser)
            assert res

            res = pd.eval("(3,) in [(3,), 2]", engine=engine, parser=parser)
            assert res

            res = pd.eval("(3,) not in [(3,), 2]", engine=engine, parser=parser)
            assert not res

            res = pd.eval("[(3,)] in [[(3,)], 2]", engine=engine, parser=parser)
            assert res
        else:
            msg = "'In' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval("1 in [1, 2]", engine=engine, parser=parser)
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval("2 in (1, 2)", engine=engine, parser=parser)
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval("3 in (1, 2)", engine=engine, parser=parser)
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval("[(3,)] in (1, 2, [(3,)])", engine=engine, parser=parser)
            msg = "'NotIn' nodes are not implemented"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval("3 not in (1, 2)", engine=engine, parser=parser)
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval("[3] not in (1, 2, [[3]])", engine=engine, parser=parser)

    def test_check_many_exprs(self, engine, parser):
        a = 1  # noqa: F841
        expr = " * ".join("a" * 33)
        expected = 1
        res = pd.eval(expr, engine=engine, parser=parser)
        assert res == expected

    @pytest.mark.parametrize(
        "expr",
        [
            "df > 2 and df > 3",
            "df > 2 or df > 3",
            "not df > 2",
        ],
    )
    def test_fails_and_or_not(self, expr, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        if parser == "python":
            msg = "'BoolOp' nodes are not implemented"
            if "not" in expr:
                msg = "'Not' nodes are not implemented"

            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(
                    expr,
                    local_dict={"df": df},
                    parser=parser,
                    engine=engine,
                )
        else:
            # smoke-test, should not raise
            pd.eval(
                expr,
                local_dict={"df": df},
                parser=parser,
                engine=engine,
            )

    @pytest.mark.parametrize("char", ["|", "&"])
    def test_fails_ampersand_pipe(self, char, engine, parser):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))  # noqa: F841
        ex = f"(df + 2)[df > 1] > 0 {char} (df > 0)"
        if parser == "python":
            msg = "cannot evaluate scalar only bool ops"
            with pytest.raises(NotImplementedError, match=msg):
                pd.eval(ex, parser=parser, engine=engine)
        else:
            # smoke-test, should not raise
            pd.eval(ex, parser=parser, engine=engine)


class TestMath:
    def eval(self, *args, **kwargs):
        kwargs["level"] = kwargs.pop("level", 0) + 1
        return pd.eval(*args, **kwargs)

    @pytest.mark.skipif(
        not NUMEXPR_INSTALLED, reason="Unary ops only implemented for numexpr"
    )
    @pytest.mark.parametrize("fn", _unary_math_ops)
    def test_unary_functions(self, fn):
        df = DataFrame({"a": np.random.default_rng(2).standard_normal(10)})
        a = df.a

        expr = f"{fn}(a)"
        got = self.eval(expr)
        with np.errstate(all="ignore"):
            expect = getattr(np, fn)(a)
        tm.assert_series_equal(got, expect, check_names=False)

    @pytest.mark.parametrize("fn", _binary_math_ops)
    def test_binary_functions(self, fn):
        df = DataFrame(
            {
                "a": np.random.default_rng(2).standard_normal(10),
                "b": np.random.default_rng(2).standard_normal(10),
            }
        )
        a = df.a
        b = df.b

        expr = f"{fn}(a, b)"
        got = self.eval(expr)
        with np.errstate(all="ignore"):
            expect = getattr(np, fn)(a, b)
        tm.assert_almost_equal(got, expect, check_names=False)

    def test_df_use_case(self, engine, parser):
        df = DataFrame(
            {
                "a": np.random.default_rng(2).standard_normal(10),
                "b": np.random.default_rng(2).standard_normal(10),
            }
        )
        df.eval(
            "e = arctan2(sin(a), b)",
            engine=engine,
            parser=parser,
            inplace=True,
        )
        got = df.e
        expect = np.arctan2(np.sin(df.a), df.b)
        tm.assert_series_equal(got, expect, check_names=False)

    def test_df_arithmetic_subexpression(self, engine, parser):
        df = DataFrame(
            {
                "a": np.random.default_rng(2).standard_normal(10),
                "b": np.random.default_rng(2).standard_normal(10),
            }
        )
        df.eval("e = sin(a + b)", engine=engine, parser=parser, inplace=True)
        got = df.e
        expect = np.sin(df.a + df.b)
        tm.assert_series_equal(got, expect, check_names=False)

    @pytest.mark.parametrize(
        "dtype, expect_dtype",
        [
            (np.int32, np.float64),
            (np.int64, np.float64),
            (np.float32, np.float32),
            (np.float64, np.float64),
            pytest.param(np.complex128, np.complex128, marks=td.skip_if_windows),
        ],
    )
    def test_result_types(self, dtype, expect_dtype, engine, parser):
        # xref https://github.com/pandas-dev/pandas/issues/12293
        #  this fails on Windows, apparently a floating point precision issue

        # Did not test complex64 because DataFrame is converting it to
        # complex128. Due to https://github.com/pandas-dev/pandas/issues/10952
        df = DataFrame(
            {"a": np.random.default_rng(2).standard_normal(10).astype(dtype)}
        )
        assert df.a.dtype == dtype
        df.eval("b = sin(a)", engine=engine, parser=parser, inplace=True)
        got = df.b
        expect = np.sin(df.a)
        assert expect.dtype == got.dtype
        assert expect_dtype == got.dtype
        tm.assert_series_equal(got, expect, check_names=False)

    def test_undefined_func(self, engine, parser):
        df = DataFrame({"a": np.random.default_rng(2).standard_normal(10)})
        msg = '"mysin" is not a supported function'

        with pytest.raises(ValueError, match=msg):
            df.eval("mysin(a)", engine=engine, parser=parser)

    def test_keyword_arg(self, engine, parser):
        df = DataFrame({"a": np.random.default_rng(2).standard_normal(10)})
        msg = 'Function "sin" does not support keyword arguments'

        with pytest.raises(TypeError, match=msg):
            df.eval("sin(x=a)", engine=engine, parser=parser)


_var_s = np.random.default_rng(2).standard_normal(10)


class TestScope:
    def test_global_scope(self, engine, parser):
        e = "_var_s * 2"
        tm.assert_numpy_array_equal(
            _var_s * 2, pd.eval(e, engine=engine, parser=parser)
        )

    def test_no_new_locals(self, engine, parser):
        x = 1
        lcls = locals().copy()
        pd.eval("x + 1", local_dict=lcls, engine=engine, parser=parser)
        lcls2 = locals().copy()
        lcls2.pop("lcls")
        assert lcls == lcls2

    def test_no_new_globals(self, engine, parser):
        x = 1  # noqa: F841
        gbls = globals().copy()
        pd.eval("x + 1", engine=engine, parser=parser)
        gbls2 = globals().copy()
        assert gbls == gbls2

    def test_empty_locals(self, engine, parser):
        # GH 47084
        x = 1  # noqa: F841
        msg = "name 'x' is not defined"
        with pytest.raises(UndefinedVariableError, match=msg):
            pd.eval("x + 1", engine=engine, parser=parser, local_dict={})

    def test_empty_globals(self, engine, parser):
        # GH 47084
        msg = "name '_var_s' is not defined"
        e = "_var_s * 2"
        with pytest.raises(UndefinedVariableError, match=msg):
            pd.eval(e, engine=engine, parser=parser, global_dict={})


@td.skip_if_no("numexpr")
def test_invalid_engine():
    msg = "Invalid engine 'asdf' passed"
    with pytest.raises(KeyError, match=msg):
        pd.eval("x + y", local_dict={"x": 1, "y": 2}, engine="asdf")


@td.skip_if_no("numexpr")
@pytest.mark.parametrize(
    ("use_numexpr", "expected"),
    (
        (True, "numexpr"),
        (False, "python"),
    ),
)
def test_numexpr_option_respected(use_numexpr, expected):
    # GH 32556
    from pandas.core.computation.eval import _check_engine

    with pd.option_context("compute.use_numexpr", use_numexpr):
        result = _check_engine(None)
        assert result == expected


@td.skip_if_no("numexpr")
def test_numexpr_option_incompatible_op():
    # GH 32556
    with pd.option_context("compute.use_numexpr", False):
        df = DataFrame(
            {"A": [True, False, True, False, None, None], "B": [1, 2, 3, 4, 5, 6]}
        )
        result = df.query("A.isnull()")
        expected = DataFrame({"A": [None, None], "B": [5, 6]}, index=[4, 5])
        tm.assert_frame_equal(result, expected)


@td.skip_if_no("numexpr")
def test_invalid_parser():
    msg = "Invalid parser 'asdf' passed"
    with pytest.raises(KeyError, match=msg):
        pd.eval("x + y", local_dict={"x": 1, "y": 2}, parser="asdf")


_parsers: dict[str, type[BaseExprVisitor]] = {
    "python": PythonExprVisitor,
    "pytables": pytables.PyTablesExprVisitor,
    "pandas": PandasExprVisitor,
}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("parser", _parsers)
def test_disallowed_nodes(engine, parser):
    VisitorClass = _parsers[parser]
    inst = VisitorClass("x + 1", engine, parser)

    for ops in VisitorClass.unsupported_nodes:
        msg = "nodes are not implemented"
        with pytest.raises(NotImplementedError, match=msg):
            getattr(inst, ops)()


def test_syntax_error_exprs(engine, parser):
    e = "s +"
    with pytest.raises(SyntaxError, match="invalid syntax"):
        pd.eval(e, engine=engine, parser=parser)


def test_name_error_exprs(engine, parser):
    e = "s + t"
    msg = "name 's' is not defined"
    with pytest.raises(NameError, match=msg):
        pd.eval(e, engine=engine, parser=parser)


@pytest.mark.parametrize("express", ["a + @b", "@a + b", "@a + @b"])
def test_invalid_local_variable_reference(engine, parser, express):
    a, b = 1, 2  # noqa: F841

    if parser != "pandas":
        with pytest.raises(SyntaxError, match="The '@' prefix is only"):
            pd.eval(express, engine=engine, parser=parser)
    else:
        with pytest.raises(SyntaxError, match="The '@' prefix is not"):
            pd.eval(express, engine=engine, parser=parser)


def test_numexpr_builtin_raises(engine, parser):
    sin, dotted_line = 1, 2
    if engine == "numexpr":
        msg = "Variables in expression .+"
        with pytest.raises(NumExprClobberingError, match=msg):
            pd.eval("sin + dotted_line", engine=engine, parser=parser)
    else:
        res = pd.eval("sin + dotted_line", engine=engine, parser=parser)
        assert res == sin + dotted_line


def test_bad_resolver_raises(engine, parser):
    cannot_resolve = 42, 3.0
    with pytest.raises(TypeError, match="Resolver of type .+"):
        pd.eval("1 + 2", resolvers=cannot_resolve, engine=engine, parser=parser)


def test_empty_string_raises(engine, parser):
    # GH 13139
    with pytest.raises(ValueError, match="expr cannot be an empty string"):
        pd.eval("", engine=engine, parser=parser)


def test_more_than_one_expression_raises(engine, parser):
    with pytest.raises(SyntaxError, match="only a single expression is allowed"):
        pd.eval("1 + 1; 2 + 2", engine=engine, parser=parser)


@pytest.mark.parametrize("cmp", ("and", "or"))
@pytest.mark.parametrize("lhs", (int, float))
@pytest.mark.parametrize("rhs", (int, float))
def test_bool_ops_fails_on_scalars(lhs, cmp, rhs, engine, parser):
    gen = {
        int: lambda: np.random.default_rng(2).integers(10),
        float: np.random.default_rng(2).standard_normal,
    }

    mid = gen[lhs]()  # noqa: F841
    lhs = gen[lhs]()
    rhs = gen[rhs]()

    ex1 = f"lhs {cmp} mid {cmp} rhs"
    ex2 = f"lhs {cmp} mid and mid {cmp} rhs"
    ex3 = f"(lhs {cmp} mid) & (mid {cmp} rhs)"
    for ex in (ex1, ex2, ex3):
        msg = "cannot evaluate scalar only bool ops|'BoolOp' nodes are not"
        with pytest.raises(NotImplementedError, match=msg):
            pd.eval(ex, engine=engine, parser=parser)


@pytest.mark.parametrize(
    "other",
    [
        "'x'",
        "...",
    ],
)
def test_equals_various(other):
    df = DataFrame({"A": ["a", "b", "c"]}, dtype=object)
    result = df.eval(f"A == {other}")
    expected = Series([False, False, False], name="A")
    if USE_NUMEXPR:
        # https://github.com/pandas-dev/pandas/issues/10239
        # lose name with numexpr engine. Remove when that's fixed.
        expected.name = None
    tm.assert_series_equal(result, expected)


def test_inf(engine, parser):
    s = "inf + 1"
    expected = np.inf
    result = pd.eval(s, engine=engine, parser=parser)
    assert result == expected


@pytest.mark.parametrize("column", ["Temp(°C)", "Capacitance(μF)"])
def test_query_token(engine, column):
    # See: https://github.com/pandas-dev/pandas/pull/42826
    df = DataFrame(
        np.random.default_rng(2).standard_normal((5, 2)), columns=[column, "b"]
    )
    expected = df[df[column] > 5]
    query_string = f"`{column}` > 5"
    result = df.query(query_string, engine=engine)
    tm.assert_frame_equal(result, expected)


def test_negate_lt_eq_le(engine, parser):
    df = DataFrame([[0, 10], [1, 20]], columns=["cat", "count"])
    expected = df[~(df.cat > 0)]

    result = df.query("~(cat > 0)", engine=engine, parser=parser)
    tm.assert_frame_equal(result, expected)

    if parser == "python":
        msg = "'Not' nodes are not implemented"
        with pytest.raises(NotImplementedError, match=msg):
            df.query("not (cat > 0)", engine=engine, parser=parser)
    else:
        result = df.query("not (cat > 0)", engine=engine, parser=parser)
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "column",
    DEFAULT_GLOBALS.keys(),
)
def test_eval_no_support_column_name(request, column):
    # GH 44603
    if column in ["True", "False", "inf", "Inf"]:
        request.applymarker(
            pytest.mark.xfail(
                raises=KeyError,
                reason=f"GH 47859 DataFrame eval not supported with {column}",
            )
        )

    df = DataFrame(
        np.random.default_rng(2).integers(0, 100, size=(10, 2)),
        columns=[column, "col1"],
    )
    expected = df[df[column] > 6]
    result = df.query(f"{column}>6")

    tm.assert_frame_equal(result, expected)


def test_set_inplace(using_copy_on_write, warn_copy_on_write):
    # https://github.com/pandas-dev/pandas/issues/47449
    # Ensure we don't only update the DataFrame inplace, but also the actual
    # column values, such that references to this column also get updated
    df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9]})
    result_view = df[:]
    ser = df["A"]
    with tm.assert_cow_warning(warn_copy_on_write):
        df.eval("A = B + C", inplace=True)
    expected = DataFrame({"A": [11, 13, 15], "B": [4, 5, 6], "C": [7, 8, 9]})
    tm.assert_frame_equal(df, expected)
    if not using_copy_on_write:
        tm.assert_series_equal(ser, expected["A"])
        tm.assert_series_equal(result_view["A"], expected["A"])
    else:
        expected = Series([1, 2, 3], name="A")
        tm.assert_series_equal(ser, expected)
        tm.assert_series_equal(result_view["A"], expected)


class TestValidate:
    @pytest.mark.parametrize("value", [1, "True", [1, 2, 3], 5.0])
    def test_validate_bool_args(self, value):
        msg = 'For argument "inplace" expected type bool, received type'
        with pytest.raises(ValueError, match=msg):
            pd.eval("2+2", inplace=value)
