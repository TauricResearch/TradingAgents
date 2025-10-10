from copy import (
    copy,
    deepcopy,
)

import numpy as np
import pytest

from pandas.core.dtypes.common import is_scalar

from pandas import (
    DataFrame,
    Index,
    Series,
    date_range,
)
import pandas._testing as tm

# ----------------------------------------------------------------------
# Generic types test cases


def construct(box, shape, value=None, dtype=None, **kwargs):
    """
    construct an object for the given shape
    if value is specified use that if its a scalar
    if value is an array, repeat it as needed
    """
    if isinstance(shape, int):
        shape = tuple([shape] * box._AXIS_LEN)
    if value is not None:
        if is_scalar(value):
            if value == "empty":
                arr = None
                dtype = np.float64

                # remove the info axis
                kwargs.pop(box._info_axis_name, None)
            else:
                arr = np.empty(shape, dtype=dtype)
                arr.fill(value)
        else:
            fshape = np.prod(shape)
            arr = value.ravel()
            new_shape = fshape / arr.shape[0]
            if fshape % arr.shape[0] != 0:
                raise Exception("invalid value passed in construct")

            arr = np.repeat(arr, new_shape).reshape(shape)
    else:
        arr = np.random.default_rng(2).standard_normal(shape)
    return box(arr, dtype=dtype, **kwargs)


class TestGeneric:
    @pytest.mark.parametrize(
        "func",
        [
            str.lower,
            {x: x.lower() for x in list("ABCD")},
            Series({x: x.lower() for x in list("ABCD")}),
        ],
    )
    def test_rename(self, frame_or_series, func):
        # single axis
        idx = list("ABCD")

        for axis in frame_or_series._AXIS_ORDERS:
            kwargs = {axis: idx}
            obj = construct(frame_or_series, 4, **kwargs)

            # rename a single axis
            result = obj.rename(**{axis: func})
            expected = obj.copy()
            setattr(expected, axis, list("abcd"))
            tm.assert_equal(result, expected)

    def test_get_numeric_data(self, frame_or_series):
        n = 4
        kwargs = {
            frame_or_series._get_axis_name(i): list(range(n))
            for i in range(frame_or_series._AXIS_LEN)
        }

        # get the numeric data
        o = construct(frame_or_series, n, **kwargs)
        result = o._get_numeric_data()
        tm.assert_equal(result, o)

        # non-inclusion
        result = o._get_bool_data()
        expected = construct(frame_or_series, n, value="empty", **kwargs)
        if isinstance(o, DataFrame):
            # preserve columns dtype
            expected.columns = o.columns[:0]
        # https://github.com/pandas-dev/pandas/issues/50862
        tm.assert_equal(result.reset_index(drop=True), expected)

        # get the bool data
        arr = np.array([True, True, False, True])
        o = construct(frame_or_series, n, value=arr, **kwargs)
        result = o._get_numeric_data()
        tm.assert_equal(result, o)

    def test_nonzero(self, frame_or_series):
        # GH 4633
        # look at the boolean/nonzero behavior for objects
        obj = construct(frame_or_series, shape=4)
        msg = f"The truth value of a {frame_or_series.__name__} is ambiguous"
        with pytest.raises(ValueError, match=msg):
            bool(obj == 0)
        with pytest.raises(ValueError, match=msg):
            bool(obj == 1)
        with pytest.raises(ValueError, match=msg):
            bool(obj)

        obj = construct(frame_or_series, shape=4, value=1)
        with pytest.raises(ValueError, match=msg):
            bool(obj == 0)
        with pytest.raises(ValueError, match=msg):
            bool(obj == 1)
        with pytest.raises(ValueError, match=msg):
            bool(obj)

        obj = construct(frame_or_series, shape=4, value=np.nan)
        with pytest.raises(ValueError, match=msg):
            bool(obj == 0)
        with pytest.raises(ValueError, match=msg):
            bool(obj == 1)
        with pytest.raises(ValueError, match=msg):
            bool(obj)

        # empty
        obj = construct(frame_or_series, shape=0)
        with pytest.raises(ValueError, match=msg):
            bool(obj)

        # invalid behaviors

        obj1 = construct(frame_or_series, shape=4, value=1)
        obj2 = construct(frame_or_series, shape=4, value=1)

        with pytest.raises(ValueError, match=msg):
            if obj1:
                pass

        with pytest.raises(ValueError, match=msg):
            obj1 and obj2
        with pytest.raises(ValueError, match=msg):
            obj1 or obj2
        with pytest.raises(ValueError, match=msg):
            not obj1

    def test_frame_or_series_compound_dtypes(self, frame_or_series):
        # see gh-5191
        # Compound dtypes should raise NotImplementedError.

        def f(dtype):
            return construct(frame_or_series, shape=3, value=1, dtype=dtype)

        msg = (
            "compound dtypes are not implemented "
            f"in the {frame_or_series.__name__} constructor"
        )

        with pytest.raises(NotImplementedError, match=msg):
            f([("A", "datetime64[h]"), ("B", "str"), ("C", "int32")])

        # these work (though results may be unexpected)
        f("int64")
        f("float64")
        f("M8[ns]")

    def test_metadata_propagation(self, frame_or_series):
        # check that the metadata matches up on the resulting ops

        o = construct(frame_or_series, shape=3)
        o.name = "foo"
        o2 = construct(frame_or_series, shape=3)
        o2.name = "bar"

        # ----------
        # preserving
        # ----------

        # simple ops with scalars
        for op in ["__add__", "__sub__", "__truediv__", "__mul__"]:
            result = getattr(o, op)(1)
            tm.assert_metadata_equivalent(o, result)

        # ops with like
        for op in ["__add__", "__sub__", "__truediv__", "__mul__"]:
            result = getattr(o, op)(o)
            tm.assert_metadata_equivalent(o, result)

        # simple boolean
        for op in ["__eq__", "__le__", "__ge__"]:
            v1 = getattr(o, op)(o)
            tm.assert_metadata_equivalent(o, v1)
            tm.assert_metadata_equivalent(o, v1 & v1)
            tm.assert_metadata_equivalent(o, v1 | v1)

        # combine_first
        result = o.combine_first(o2)
        tm.assert_metadata_equivalent(o, result)

        # ---------------------------
        # non-preserving (by default)
        # ---------------------------

        # add non-like
        result = o + o2
        tm.assert_metadata_equivalent(result)

        # simple boolean
        for op in ["__eq__", "__le__", "__ge__"]:
            # this is a name matching op
            v1 = getattr(o, op)(o)
            v2 = getattr(o, op)(o2)
            tm.assert_metadata_equivalent(v2)
            tm.assert_metadata_equivalent(v1 & v2)
            tm.assert_metadata_equivalent(v1 | v2)

    def test_size_compat(self, frame_or_series):
        # GH8846
        # size property should be defined

        o = construct(frame_or_series, shape=10)
        assert o.size == np.prod(o.shape)
        assert o.size == 10 ** len(o.axes)

    def test_split_compat(self, frame_or_series):
        # xref GH8846
        o = construct(frame_or_series, shape=10)
        with tm.assert_produces_warning(
            FutureWarning, match=".swapaxes' is deprecated", check_stacklevel=False
        ):
            assert len(np.array_split(o, 5)) == 5
            assert len(np.array_split(o, 2)) == 2

    # See gh-12301
    def test_stat_unexpected_keyword(self, frame_or_series):
        obj = construct(frame_or_series, 5)
        starwars = "Star Wars"
        errmsg = "unexpected keyword"

        with pytest.raises(TypeError, match=errmsg):
            obj.max(epic=starwars)  # stat_function
        with pytest.raises(TypeError, match=errmsg):
            obj.var(epic=starwars)  # stat_function_ddof
        with pytest.raises(TypeError, match=errmsg):
            obj.sum(epic=starwars)  # cum_function
        with pytest.raises(TypeError, match=errmsg):
            obj.any(epic=starwars)  # logical_function

    @pytest.mark.parametrize("func", ["sum", "cumsum", "any", "var"])
    def test_api_compat(self, func, frame_or_series):
        # GH 12021
        # compat for __name__, __qualname__

        obj = construct(frame_or_series, 5)
        f = getattr(obj, func)
        assert f.__name__ == func
        assert f.__qualname__.endswith(func)

    def test_stat_non_defaults_args(self, frame_or_series):
        obj = construct(frame_or_series, 5)
        out = np.array([0])
        errmsg = "the 'out' parameter is not supported"

        with pytest.raises(ValueError, match=errmsg):
            obj.max(out=out)  # stat_function
        with pytest.raises(ValueError, match=errmsg):
            obj.var(out=out)  # stat_function_ddof
        with pytest.raises(ValueError, match=errmsg):
            obj.sum(out=out)  # cum_function
        with pytest.raises(ValueError, match=errmsg):
            obj.any(out=out)  # logical_function

    def test_truncate_out_of_bounds(self, frame_or_series):
        # GH11382

        # small
        shape = [2000] + ([1] * (frame_or_series._AXIS_LEN - 1))
        small = construct(frame_or_series, shape, dtype="int8", value=1)
        tm.assert_equal(small.truncate(), small)
        tm.assert_equal(small.truncate(before=0, after=3e3), small)
        tm.assert_equal(small.truncate(before=-1, after=2e3), small)

        # big
        shape = [2_000_000] + ([1] * (frame_or_series._AXIS_LEN - 1))
        big = construct(frame_or_series, shape, dtype="int8", value=1)
        tm.assert_equal(big.truncate(), big)
        tm.assert_equal(big.truncate(before=0, after=3e6), big)
        tm.assert_equal(big.truncate(before=-1, after=2e6), big)

    @pytest.mark.parametrize(
        "func",
        [copy, deepcopy, lambda x: x.copy(deep=False), lambda x: x.copy(deep=True)],
    )
    @pytest.mark.parametrize("shape", [0, 1, 2])
    def test_copy_and_deepcopy(self, frame_or_series, shape, func):
        # GH 15444
        obj = construct(frame_or_series, shape)
        obj_copy = func(obj)
        assert obj_copy is not obj
        tm.assert_equal(obj_copy, obj)

    def test_data_deprecated(self, frame_or_series):
        obj = frame_or_series()
        msg = "(Series|DataFrame)._data is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            mgr = obj._data
        assert mgr is obj._mgr


class TestNDFrame:
    # tests that don't fit elsewhere

    @pytest.mark.parametrize(
        "ser",
        [
            Series(range(10), dtype=np.float64),
            Series([str(i) for i in range(10)], dtype=object),
        ],
    )
    def test_squeeze_series_noop(self, ser):
        # noop
        tm.assert_series_equal(ser.squeeze(), ser)

    def test_squeeze_frame_noop(self):
        # noop
        df = DataFrame(np.eye(2))
        tm.assert_frame_equal(df.squeeze(), df)

    def test_squeeze_frame_reindex(self):
        # squeezing
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        ).reindex(columns=["A"])
        tm.assert_series_equal(df.squeeze(), df["A"])

    def test_squeeze_0_len_dim(self):
        # don't fail with 0 length dimensions GH11229 & GH8999
        empty_series = Series([], name="five", dtype=np.float64)
        empty_frame = DataFrame([empty_series])
        tm.assert_series_equal(empty_series, empty_series.squeeze())
        tm.assert_series_equal(empty_series, empty_frame.squeeze())

    def test_squeeze_axis(self):
        # axis argument
        df = DataFrame(
            np.random.default_rng(2).standard_normal((1, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=1, freq="B"),
        ).iloc[:, :1]
        assert df.shape == (1, 1)
        tm.assert_series_equal(df.squeeze(axis=0), df.iloc[0])
        tm.assert_series_equal(df.squeeze(axis="index"), df.iloc[0])
        tm.assert_series_equal(df.squeeze(axis=1), df.iloc[:, 0])
        tm.assert_series_equal(df.squeeze(axis="columns"), df.iloc[:, 0])
        assert df.squeeze() == df.iloc[0, 0]
        msg = "No axis named 2 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.squeeze(axis=2)
        msg = "No axis named x for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.squeeze(axis="x")

    def test_squeeze_axis_len_3(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=3, freq="B"),
        )
        tm.assert_frame_equal(df.squeeze(axis=0), df)

    def test_numpy_squeeze(self):
        s = Series(range(2), dtype=np.float64)
        tm.assert_series_equal(np.squeeze(s), s)

        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        ).reindex(columns=["A"])
        tm.assert_series_equal(np.squeeze(df), df["A"])

    @pytest.mark.parametrize(
        "ser",
        [
            Series(range(10), dtype=np.float64),
            Series([str(i) for i in range(10)], dtype=object),
        ],
    )
    def test_transpose_series(self, ser):
        # calls implementation in pandas/core/base.py
        tm.assert_series_equal(ser.transpose(), ser)

    def test_transpose_frame(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        tm.assert_frame_equal(df.transpose().transpose(), df)

    def test_numpy_transpose(self, frame_or_series):
        obj = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        obj = tm.get_obj(obj, frame_or_series)

        if frame_or_series is Series:
            # 1D -> np.transpose is no-op
            tm.assert_series_equal(np.transpose(obj), obj)

        # round-trip preserved
        tm.assert_equal(np.transpose(np.transpose(obj)), obj)

        msg = "the 'axes' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            np.transpose(obj, axes=1)

    @pytest.mark.parametrize(
        "ser",
        [
            Series(range(10), dtype=np.float64),
            Series([str(i) for i in range(10)], dtype=object),
        ],
    )
    def test_take_series(self, ser):
        indices = [1, 5, -2, 6, 3, -1]
        out = ser.take(indices)
        expected = Series(
            data=ser.values.take(indices),
            index=ser.index.take(indices),
            dtype=ser.dtype,
        )
        tm.assert_series_equal(out, expected)

    def test_take_frame(self):
        indices = [1, 5, -2, 6, 3, -1]
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
            index=date_range("2000-01-01", periods=10, freq="B"),
        )
        out = df.take(indices)
        expected = DataFrame(
            data=df.values.take(indices, axis=0),
            index=df.index.take(indices),
            columns=df.columns,
        )
        tm.assert_frame_equal(out, expected)

    def test_take_invalid_kwargs(self, frame_or_series):
        indices = [-3, 2, 0, 1]

        obj = DataFrame(range(5))
        obj = tm.get_obj(obj, frame_or_series)

        msg = r"take\(\) got an unexpected keyword argument 'foo'"
        with pytest.raises(TypeError, match=msg):
            obj.take(indices, foo=2)

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            obj.take(indices, out=indices)

        msg = "the 'mode' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            obj.take(indices, mode="clip")

    def test_axis_classmethods(self, frame_or_series):
        box = frame_or_series
        obj = box(dtype=object)
        values = box._AXIS_TO_AXIS_NUMBER.keys()
        for v in values:
            assert obj._get_axis_number(v) == box._get_axis_number(v)
            assert obj._get_axis_name(v) == box._get_axis_name(v)
            assert obj._get_block_manager_axis(v) == box._get_block_manager_axis(v)

    def test_flags_identity(self, frame_or_series):
        obj = Series([1, 2])
        if frame_or_series is DataFrame:
            obj = obj.to_frame()

        assert obj.flags is obj.flags
        obj2 = obj.copy()
        assert obj2.flags is not obj.flags

    def test_bool_dep(self) -> None:
        # GH-51749
        msg_warn = (
            "DataFrame.bool is now deprecated and will be removed "
            "in future version of pandas"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg_warn):
            DataFrame({"col": [False]}).bool()
