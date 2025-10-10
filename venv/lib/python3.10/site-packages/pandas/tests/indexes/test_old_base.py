from __future__ import annotations

from datetime import datetime
import weakref

import numpy as np
import pytest

from pandas._libs.tslibs import Timestamp

from pandas.core.dtypes.common import (
    is_integer_dtype,
    is_numeric_dtype,
)
from pandas.core.dtypes.dtypes import CategoricalDtype

import pandas as pd
from pandas import (
    CategoricalIndex,
    DatetimeIndex,
    DatetimeTZDtype,
    Index,
    IntervalIndex,
    MultiIndex,
    PeriodIndex,
    RangeIndex,
    Series,
    StringDtype,
    TimedeltaIndex,
    isna,
    period_range,
)
import pandas._testing as tm
import pandas.core.algorithms as algos
from pandas.core.arrays import BaseMaskedArray


class TestBase:
    @pytest.fixture(
        params=[
            RangeIndex(start=0, stop=20, step=2),
            Index(np.arange(5, dtype=np.float64)),
            Index(np.arange(5, dtype=np.float32)),
            Index(np.arange(5, dtype=np.uint64)),
            Index(range(0, 20, 2), dtype=np.int64),
            Index(range(0, 20, 2), dtype=np.int32),
            Index(range(0, 20, 2), dtype=np.int16),
            Index(range(0, 20, 2), dtype=np.int8),
            Index(list("abcde")),
            Index([0, "a", 1, "b", 2, "c"]),
            period_range("20130101", periods=5, freq="D"),
            TimedeltaIndex(
                [
                    "0 days 01:00:00",
                    "1 days 01:00:00",
                    "2 days 01:00:00",
                    "3 days 01:00:00",
                    "4 days 01:00:00",
                ],
                dtype="timedelta64[ns]",
                freq="D",
            ),
            DatetimeIndex(
                ["2013-01-01", "2013-01-02", "2013-01-03", "2013-01-04", "2013-01-05"],
                dtype="datetime64[ns]",
                freq="D",
            ),
            IntervalIndex.from_breaks(range(11), closed="right"),
        ]
    )
    def simple_index(self, request):
        return request.param

    def test_pickle_compat_construction(self, simple_index):
        # need an object to create with
        if isinstance(simple_index, RangeIndex):
            pytest.skip("RangeIndex() is a valid constructor")
        msg = "|".join(
            [
                r"Index\(\.\.\.\) must be called with a collection of some "
                r"kind, None was passed",
                r"DatetimeIndex\(\) must be called with a collection of some "
                r"kind, None was passed",
                r"TimedeltaIndex\(\) must be called with a collection of some "
                r"kind, None was passed",
                r"__new__\(\) missing 1 required positional argument: 'data'",
                r"__new__\(\) takes at least 2 arguments \(1 given\)",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            type(simple_index)()

    def test_shift(self, simple_index):
        # GH8083 test the base class for shift
        if isinstance(simple_index, (DatetimeIndex, TimedeltaIndex, PeriodIndex)):
            pytest.skip("Tested in test_ops/test_arithmetic")
        idx = simple_index
        msg = (
            f"This method is only implemented for DatetimeIndex, PeriodIndex and "
            f"TimedeltaIndex; Got type {type(idx).__name__}"
        )
        with pytest.raises(NotImplementedError, match=msg):
            idx.shift(1)
        with pytest.raises(NotImplementedError, match=msg):
            idx.shift(1, 2)

    def test_constructor_name_unhashable(self, simple_index):
        # GH#29069 check that name is hashable
        # See also same-named test in tests.series.test_constructors
        idx = simple_index
        with pytest.raises(TypeError, match="Index.name must be a hashable type"):
            type(idx)(idx, name=[])

    def test_create_index_existing_name(self, simple_index):
        # GH11193, when an existing index is passed, and a new name is not
        # specified, the new index should inherit the previous object name
        expected = simple_index.copy()
        if not isinstance(expected, MultiIndex):
            expected.name = "foo"
            result = Index(expected)
            tm.assert_index_equal(result, expected)

            result = Index(expected, name="bar")
            expected.name = "bar"
            tm.assert_index_equal(result, expected)
        else:
            expected.names = ["foo", "bar"]
            result = Index(expected)
            tm.assert_index_equal(
                result,
                Index(
                    Index(
                        [
                            ("foo", "one"),
                            ("foo", "two"),
                            ("bar", "one"),
                            ("baz", "two"),
                            ("qux", "one"),
                            ("qux", "two"),
                        ],
                        dtype="object",
                    ),
                    names=["foo", "bar"],
                ),
            )

            result = Index(expected, names=["A", "B"])
            tm.assert_index_equal(
                result,
                Index(
                    Index(
                        [
                            ("foo", "one"),
                            ("foo", "two"),
                            ("bar", "one"),
                            ("baz", "two"),
                            ("qux", "one"),
                            ("qux", "two"),
                        ],
                        dtype="object",
                    ),
                    names=["A", "B"],
                ),
            )

    def test_numeric_compat(self, simple_index):
        idx = simple_index
        # Check that this doesn't cover MultiIndex case, if/when it does,
        #  we can remove multi.test_compat.test_numeric_compat
        assert not isinstance(idx, MultiIndex)
        if type(idx) is Index:
            pytest.skip("Not applicable for Index")
        if is_numeric_dtype(simple_index.dtype) or isinstance(
            simple_index, TimedeltaIndex
        ):
            pytest.skip("Tested elsewhere.")

        typ = type(idx._data).__name__
        cls = type(idx).__name__
        lmsg = "|".join(
            [
                rf"unsupported operand type\(s\) for \*: '{typ}' and 'int'",
                "cannot perform (__mul__|__truediv__|__floordiv__) with "
                f"this index type: ({cls}|{typ})",
            ]
        )
        with pytest.raises(TypeError, match=lmsg):
            idx * 1
        rmsg = "|".join(
            [
                rf"unsupported operand type\(s\) for \*: 'int' and '{typ}'",
                "cannot perform (__rmul__|__rtruediv__|__rfloordiv__) with "
                f"this index type: ({cls}|{typ})",
            ]
        )
        with pytest.raises(TypeError, match=rmsg):
            1 * idx

        div_err = lmsg.replace("*", "/")
        with pytest.raises(TypeError, match=div_err):
            idx / 1
        div_err = rmsg.replace("*", "/")
        with pytest.raises(TypeError, match=div_err):
            1 / idx

        floordiv_err = lmsg.replace("*", "//")
        with pytest.raises(TypeError, match=floordiv_err):
            idx // 1
        floordiv_err = rmsg.replace("*", "//")
        with pytest.raises(TypeError, match=floordiv_err):
            1 // idx

    def test_logical_compat(self, simple_index):
        if simple_index.dtype in (object, "string"):
            pytest.skip("Tested elsewhere.")
        idx = simple_index
        if idx.dtype.kind in "iufcbm":
            assert idx.all() == idx._values.all()
            assert idx.all() == idx.to_series().all()
            assert idx.any() == idx._values.any()
            assert idx.any() == idx.to_series().any()
        else:
            msg = "cannot perform (any|all)"
            if isinstance(idx, IntervalIndex):
                msg = (
                    r"'IntervalArray' with dtype interval\[.*\] does "
                    "not support reduction '(any|all)'"
                )
            with pytest.raises(TypeError, match=msg):
                idx.all()
            with pytest.raises(TypeError, match=msg):
                idx.any()

    def test_repr_roundtrip(self, simple_index):
        if isinstance(simple_index, IntervalIndex):
            pytest.skip(f"Not a valid repr for {type(simple_index).__name__}")
        idx = simple_index
        tm.assert_index_equal(eval(repr(idx)), idx)

    def test_repr_max_seq_item_setting(self, simple_index):
        # GH10182
        if isinstance(simple_index, IntervalIndex):
            pytest.skip(f"Not a valid repr for {type(simple_index).__name__}")
        idx = simple_index
        idx = idx.repeat(50)
        with pd.option_context("display.max_seq_items", None):
            repr(idx)
            assert "..." not in str(idx)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_ensure_copied_data(self, index):
        # Check the "copy" argument of each Index.__new__ is honoured
        # GH12309
        init_kwargs = {}
        if isinstance(index, PeriodIndex):
            # Needs "freq" specification:
            init_kwargs["freq"] = index.freq
        elif isinstance(index, (RangeIndex, MultiIndex, CategoricalIndex)):
            pytest.skip(
                "RangeIndex cannot be initialized from data, "
                "MultiIndex and CategoricalIndex are tested separately"
            )
        elif index.dtype == object and index.inferred_type in ["boolean", "string"]:
            init_kwargs["dtype"] = index.dtype

        index_type = type(index)
        result = index_type(index.values, copy=True, **init_kwargs)
        if isinstance(index.dtype, DatetimeTZDtype):
            result = result.tz_localize("UTC").tz_convert(index.tz)
        if isinstance(index, (DatetimeIndex, TimedeltaIndex)):
            index = index._with_freq(None)

        tm.assert_index_equal(index, result)

        if isinstance(index, PeriodIndex):
            # .values an object array of Period, thus copied
            depr_msg = "The 'ordinal' keyword in PeriodIndex is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                result = index_type(ordinal=index.asi8, copy=False, **init_kwargs)
            tm.assert_numpy_array_equal(index.asi8, result.asi8, check_same="same")
        elif isinstance(index, IntervalIndex):
            # checked in test_interval.py
            pass
        elif type(index) is Index and not isinstance(index.dtype, np.dtype):
            result = index_type(index.values, copy=False, **init_kwargs)
            tm.assert_index_equal(result, index)

            if isinstance(index._values, BaseMaskedArray):
                assert np.shares_memory(index._values._data, result._values._data)
                tm.assert_numpy_array_equal(
                    index._values._data, result._values._data, check_same="same"
                )
                assert np.shares_memory(index._values._mask, result._values._mask)
                tm.assert_numpy_array_equal(
                    index._values._mask, result._values._mask, check_same="same"
                )
            elif (
                isinstance(index.dtype, StringDtype) and index.dtype.storage == "python"
            ):
                assert np.shares_memory(index._values._ndarray, result._values._ndarray)
                tm.assert_numpy_array_equal(
                    index._values._ndarray, result._values._ndarray, check_same="same"
                )
            elif (
                isinstance(index.dtype, StringDtype)
                and index.dtype.storage == "pyarrow"
            ):
                assert tm.shares_memory(result._values, index._values)
            else:
                raise NotImplementedError(index.dtype)
        else:
            result = index_type(index.values, copy=False, **init_kwargs)
            tm.assert_numpy_array_equal(index.values, result.values, check_same="same")

    def test_memory_usage(self, index):
        index._engine.clear_mapping()
        result = index.memory_usage()
        if index.empty:
            # we report 0 for no-length
            assert result == 0
            return

        # non-zero length
        index.get_loc(index[0])
        result2 = index.memory_usage()
        result3 = index.memory_usage(deep=True)

        # RangeIndex, IntervalIndex
        # don't have engines
        # Index[EA] has engine but it does not have a Hashtable .mapping
        if not isinstance(index, (RangeIndex, IntervalIndex)) and not (
            type(index) is Index and not isinstance(index.dtype, np.dtype)
        ):
            assert result2 > result

        if index.inferred_type == "object":
            assert result3 > result2

    def test_argsort(self, index):
        if isinstance(index, CategoricalIndex):
            pytest.skip(f"{type(self).__name__} separately tested")

        result = index.argsort()
        expected = np.array(index).argsort()
        tm.assert_numpy_array_equal(result, expected, check_dtype=False)

    def test_numpy_argsort(self, index):
        result = np.argsort(index)
        expected = index.argsort()
        tm.assert_numpy_array_equal(result, expected)

        result = np.argsort(index, kind="mergesort")
        expected = index.argsort(kind="mergesort")
        tm.assert_numpy_array_equal(result, expected)

        # these are the only two types that perform
        # pandas compatibility input validation - the
        # rest already perform separate (or no) such
        # validation via their 'values' attribute as
        # defined in pandas.core.indexes/base.py - they
        # cannot be changed at the moment due to
        # backwards compatibility concerns
        if isinstance(index, (CategoricalIndex, RangeIndex)):
            msg = "the 'axis' parameter is not supported"
            with pytest.raises(ValueError, match=msg):
                np.argsort(index, axis=1)

            msg = "the 'order' parameter is not supported"
            with pytest.raises(ValueError, match=msg):
                np.argsort(index, order=("a", "b"))

    def test_repeat(self, simple_index):
        rep = 2
        idx = simple_index.copy()
        new_index_cls = idx._constructor
        expected = new_index_cls(idx.values.repeat(rep), name=idx.name)
        tm.assert_index_equal(idx.repeat(rep), expected)

        idx = simple_index
        rep = np.arange(len(idx))
        expected = new_index_cls(idx.values.repeat(rep), name=idx.name)
        tm.assert_index_equal(idx.repeat(rep), expected)

    def test_numpy_repeat(self, simple_index):
        rep = 2
        idx = simple_index
        expected = idx.repeat(rep)
        tm.assert_index_equal(np.repeat(idx, rep), expected)

        msg = "the 'axis' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            np.repeat(idx, rep, axis=0)

    def test_where(self, listlike_box, simple_index):
        if isinstance(simple_index, (IntervalIndex, PeriodIndex)) or is_numeric_dtype(
            simple_index.dtype
        ):
            pytest.skip("Tested elsewhere.")
        klass = listlike_box

        idx = simple_index
        if isinstance(idx, (DatetimeIndex, TimedeltaIndex)):
            # where does not preserve freq
            idx = idx._with_freq(None)

        cond = [True] * len(idx)
        result = idx.where(klass(cond))
        expected = idx
        tm.assert_index_equal(result, expected)

        cond = [False] + [True] * len(idx[1:])
        expected = Index([idx._na_value] + idx[1:].tolist(), dtype=idx.dtype)
        result = idx.where(klass(cond))
        tm.assert_index_equal(result, expected)

    def test_insert_base(self, index):
        trimmed = index[1:4]

        if not len(index):
            pytest.skip("Not applicable for empty index")

        # test 0th element
        warn = None
        if index.dtype == object and index.inferred_type == "boolean":
            # GH#51363
            warn = FutureWarning
        msg = "The behavior of Index.insert with object-dtype is deprecated"
        with tm.assert_produces_warning(warn, match=msg):
            result = trimmed.insert(0, index[0])
        assert index[0:4].equals(result)

    def test_insert_out_of_bounds(self, index, using_infer_string):
        # TypeError/IndexError matches what np.insert raises in these cases

        if len(index) > 0:
            err = TypeError
        else:
            err = IndexError
        if len(index) == 0:
            # 0 vs 0.5 in error message varies with numpy version
            msg = "index (0|0.5) is out of bounds for axis 0 with size 0"
        else:
            msg = "slice indices must be integers or None or have an __index__ method"

        if using_infer_string:
            if index.dtype == "string" or index.dtype == "category":  # noqa: PLR1714
                msg = "loc must be an integer between"
            elif index.dtype == "object" and len(index) == 0:
                msg = "loc must be an integer between"
                err = TypeError

        with pytest.raises(err, match=msg):
            index.insert(0.5, "foo")

        msg = "|".join(
            [
                r"index -?\d+ is out of bounds for axis 0 with size \d+",
                "loc must be an integer between",
            ]
        )
        with pytest.raises(IndexError, match=msg):
            index.insert(len(index) + 1, 1)

        with pytest.raises(IndexError, match=msg):
            index.insert(-len(index) - 1, 1)

    def test_delete_base(self, index):
        if not len(index):
            pytest.skip("Not applicable for empty index")

        if isinstance(index, RangeIndex):
            # tested in class
            pytest.skip(f"{type(self).__name__} tested elsewhere")

        expected = index[1:]
        result = index.delete(0)
        assert result.equals(expected)
        assert result.name == expected.name

        expected = index[:-1]
        result = index.delete(-1)
        assert result.equals(expected)
        assert result.name == expected.name

        length = len(index)
        msg = f"index {length} is out of bounds for axis 0 with size {length}"
        with pytest.raises(IndexError, match=msg):
            index.delete(length)

    @pytest.mark.filterwarnings(r"ignore:Dtype inference:FutureWarning")
    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_equals(self, index):
        if isinstance(index, IntervalIndex):
            pytest.skip(f"{type(index).__name__} tested elsewhere")

        is_ea_idx = type(index) is Index and not isinstance(index.dtype, np.dtype)

        assert index.equals(index)
        assert index.equals(index.copy())
        if not is_ea_idx:
            # doesn't hold for e.g. IntegerDtype
            assert index.equals(index.astype(object))

        assert not index.equals(list(index))
        assert not index.equals(np.array(index))

        # Cannot pass in non-int64 dtype to RangeIndex
        if not isinstance(index, RangeIndex) and not is_ea_idx:
            same_values = Index(index, dtype=object)
            assert index.equals(same_values)
            assert same_values.equals(index)

        if index.nlevels == 1:
            # do not test MultiIndex
            assert not index.equals(Series(index))

    def test_equals_op(self, simple_index):
        # GH9947, GH10637
        index_a = simple_index

        n = len(index_a)
        index_b = index_a[0:-1]
        index_c = index_a[0:-1].append(index_a[-2:-1])
        index_d = index_a[0:1]

        msg = "Lengths must match|could not be broadcast"
        with pytest.raises(ValueError, match=msg):
            index_a == index_b
        expected1 = np.array([True] * n)
        expected2 = np.array([True] * (n - 1) + [False])
        tm.assert_numpy_array_equal(index_a == index_a, expected1)
        tm.assert_numpy_array_equal(index_a == index_c, expected2)

        # test comparisons with numpy arrays
        array_a = np.array(index_a)
        array_b = np.array(index_a[0:-1])
        array_c = np.array(index_a[0:-1].append(index_a[-2:-1]))
        array_d = np.array(index_a[0:1])
        with pytest.raises(ValueError, match=msg):
            index_a == array_b
        tm.assert_numpy_array_equal(index_a == array_a, expected1)
        tm.assert_numpy_array_equal(index_a == array_c, expected2)

        # test comparisons with Series
        series_a = Series(array_a)
        series_b = Series(array_b)
        series_c = Series(array_c)
        series_d = Series(array_d)
        with pytest.raises(ValueError, match=msg):
            index_a == series_b

        tm.assert_numpy_array_equal(index_a == series_a, expected1)
        tm.assert_numpy_array_equal(index_a == series_c, expected2)

        # cases where length is 1 for one of them
        with pytest.raises(ValueError, match="Lengths must match"):
            index_a == index_d
        with pytest.raises(ValueError, match="Lengths must match"):
            index_a == series_d
        with pytest.raises(ValueError, match="Lengths must match"):
            index_a == array_d
        msg = "Can only compare identically-labeled Series objects"
        with pytest.raises(ValueError, match=msg):
            series_a == series_d
        with pytest.raises(ValueError, match="Lengths must match"):
            series_a == array_d

        # comparing with a scalar should broadcast; note that we are excluding
        # MultiIndex because in this case each item in the index is a tuple of
        # length 2, and therefore is considered an array of length 2 in the
        # comparison instead of a scalar
        if not isinstance(index_a, MultiIndex):
            expected3 = np.array([False] * (len(index_a) - 2) + [True, False])
            # assuming the 2nd to last item is unique in the data
            item = index_a[-2]
            tm.assert_numpy_array_equal(index_a == item, expected3)
            tm.assert_series_equal(series_a == item, Series(expected3))

    def test_format(self, simple_index):
        # GH35439
        if is_numeric_dtype(simple_index.dtype) or isinstance(
            simple_index, DatetimeIndex
        ):
            pytest.skip("Tested elsewhere.")
        idx = simple_index
        expected = [str(x) for x in idx]
        msg = r"Index\.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert idx.format() == expected

    def test_format_empty(self, simple_index):
        # GH35712
        if isinstance(simple_index, (PeriodIndex, RangeIndex)):
            pytest.skip("Tested elsewhere")
        empty_idx = type(simple_index)([])
        msg = r"Index\.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert empty_idx.format() == []
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert empty_idx.format(name=True) == [""]

    def test_fillna(self, index):
        # GH 11343
        if len(index) == 0:
            pytest.skip("Not relevant for empty index")
        elif index.dtype == bool:
            pytest.skip(f"{index.dtype} cannot hold NAs")
        elif isinstance(index, Index) and is_integer_dtype(index.dtype):
            pytest.skip(f"Not relevant for Index with {index.dtype}")
        elif isinstance(index, MultiIndex):
            idx = index.copy(deep=True)
            msg = "isna is not defined for MultiIndex"
            with pytest.raises(NotImplementedError, match=msg):
                idx.fillna(idx[0])
        else:
            idx = index.copy(deep=True)
            result = idx.fillna(idx[0])
            tm.assert_index_equal(result, idx)
            assert result is not idx

            msg = "'value' must be a scalar, passed: "
            with pytest.raises(TypeError, match=msg):
                idx.fillna([idx[0]])

            idx = index.copy(deep=True)
            values = idx._values

            values[1] = np.nan

            idx = type(index)(values)

            msg = "does not support 'downcast'"
            msg2 = r"The 'downcast' keyword in .*Index\.fillna is deprecated"
            with tm.assert_produces_warning(FutureWarning, match=msg2):
                with pytest.raises(NotImplementedError, match=msg):
                    # For now at least, we only raise if there are NAs present
                    idx.fillna(idx[0], downcast="infer")

            expected = np.array([False] * len(idx), dtype=bool)
            expected[1] = True
            tm.assert_numpy_array_equal(idx._isnan, expected)
            assert idx.hasnans is True

    def test_nulls(self, index):
        # this is really a smoke test for the methods
        # as these are adequately tested for function elsewhere
        if len(index) == 0:
            tm.assert_numpy_array_equal(index.isna(), np.array([], dtype=bool))
        elif isinstance(index, MultiIndex):
            idx = index.copy()
            msg = "isna is not defined for MultiIndex"
            with pytest.raises(NotImplementedError, match=msg):
                idx.isna()
        elif not index.hasnans:
            tm.assert_numpy_array_equal(index.isna(), np.zeros(len(index), dtype=bool))
            tm.assert_numpy_array_equal(index.notna(), np.ones(len(index), dtype=bool))
        else:
            result = isna(index)
            tm.assert_numpy_array_equal(index.isna(), result)
            tm.assert_numpy_array_equal(index.notna(), ~result)

    def test_empty(self, simple_index):
        # GH 15270
        idx = simple_index
        assert not idx.empty
        assert idx[:0].empty

    def test_join_self_unique(self, join_type, simple_index):
        idx = simple_index
        if idx.is_unique:
            joined = idx.join(idx, how=join_type)
            expected = simple_index
            if join_type == "outer":
                expected = algos.safe_sort(expected)
            tm.assert_index_equal(joined, expected)

    def test_map(self, simple_index):
        # callable
        if isinstance(simple_index, (TimedeltaIndex, PeriodIndex)):
            pytest.skip("Tested elsewhere.")
        idx = simple_index

        result = idx.map(lambda x: x)
        # RangeIndex are equivalent to the similar Index with int64 dtype
        tm.assert_index_equal(result, idx, exact="equiv")

    @pytest.mark.parametrize(
        "mapper",
        [
            lambda values, index: {i: e for e, i in zip(values, index)},
            lambda values, index: Series(values, index),
        ],
    )
    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_map_dictlike(self, mapper, simple_index, request):
        idx = simple_index
        if isinstance(idx, (DatetimeIndex, TimedeltaIndex, PeriodIndex)):
            pytest.skip("Tested elsewhere.")

        identity = mapper(idx.values, idx)

        result = idx.map(identity)
        # RangeIndex are equivalent to the similar Index with int64 dtype
        tm.assert_index_equal(result, idx, exact="equiv")

        # empty mappable
        dtype = None
        if idx.dtype.kind == "f":
            dtype = idx.dtype

        expected = Index([np.nan] * len(idx), dtype=dtype)
        result = idx.map(mapper(expected, idx))
        tm.assert_index_equal(result, expected)

    def test_map_str(self, simple_index):
        # GH 31202
        if isinstance(simple_index, CategoricalIndex):
            pytest.skip("See test_map.py")
        idx = simple_index
        result = idx.map(str)
        expected = Index([str(x) for x in idx])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("copy", [True, False])
    @pytest.mark.parametrize("name", [None, "foo"])
    @pytest.mark.parametrize("ordered", [True, False])
    def test_astype_category(self, copy, name, ordered, simple_index):
        # GH 18630
        idx = simple_index
        if name:
            idx = idx.rename(name)

        # standard categories
        dtype = CategoricalDtype(ordered=ordered)
        result = idx.astype(dtype, copy=copy)
        expected = CategoricalIndex(idx, name=name, ordered=ordered)
        tm.assert_index_equal(result, expected, exact=True)

        # non-standard categories
        dtype = CategoricalDtype(idx.unique().tolist()[:-1], ordered)
        result = idx.astype(dtype, copy=copy)
        expected = CategoricalIndex(idx, name=name, dtype=dtype)
        tm.assert_index_equal(result, expected, exact=True)

        if ordered is False:
            # dtype='category' defaults to ordered=False, so only test once
            result = idx.astype("category", copy=copy)
            expected = CategoricalIndex(idx, name=name)
            tm.assert_index_equal(result, expected, exact=True)

    def test_is_unique(self, simple_index):
        # initialize a unique index
        index = simple_index.drop_duplicates()
        assert index.is_unique is True

        # empty index should be unique
        index_empty = index[:0]
        assert index_empty.is_unique is True

        # test basic dupes
        index_dup = index.insert(0, index[0])
        assert index_dup.is_unique is False

        # single NA should be unique
        index_na = index.insert(0, np.nan)
        assert index_na.is_unique is True

        # multiple NA should not be unique
        index_na_dup = index_na.insert(0, np.nan)
        assert index_na_dup.is_unique is False

    @pytest.mark.arm_slow
    def test_engine_reference_cycle(self, simple_index):
        # GH27585
        index = simple_index.copy()
        ref = weakref.ref(index)
        index._engine
        del index
        assert ref() is None

    def test_getitem_2d_deprecated(self, simple_index):
        # GH#30588, GH#31479
        if isinstance(simple_index, IntervalIndex):
            pytest.skip("Tested elsewhere")
        idx = simple_index
        msg = "Multi-dimensional indexing|too many|only"
        with pytest.raises((ValueError, IndexError), match=msg):
            idx[:, None]

        if not isinstance(idx, RangeIndex):
            # GH#44051 RangeIndex already raised pre-2.0 with a different message
            with pytest.raises((ValueError, IndexError), match=msg):
                idx[True]
            with pytest.raises((ValueError, IndexError), match=msg):
                idx[False]
        else:
            msg = "only integers, slices"
            with pytest.raises(IndexError, match=msg):
                idx[True]
            with pytest.raises(IndexError, match=msg):
                idx[False]

    def test_copy_shares_cache(self, simple_index):
        # GH32898, GH36840
        idx = simple_index
        idx.get_loc(idx[0])  # populates the _cache.
        copy = idx.copy()

        assert copy._cache is idx._cache

    def test_shallow_copy_shares_cache(self, simple_index):
        # GH32669, GH36840
        idx = simple_index
        idx.get_loc(idx[0])  # populates the _cache.
        shallow_copy = idx._view()

        assert shallow_copy._cache is idx._cache

        shallow_copy = idx._shallow_copy(idx._data)
        assert shallow_copy._cache is not idx._cache
        assert shallow_copy._cache == {}

    def test_index_groupby(self, simple_index):
        idx = simple_index[:5]
        to_groupby = np.array([1, 2, np.nan, 2, 1])
        tm.assert_dict_equal(
            idx.groupby(to_groupby), {1.0: idx[[0, 4]], 2.0: idx[[1, 3]]}
        )

        to_groupby = DatetimeIndex(
            [
                datetime(2011, 11, 1),
                datetime(2011, 12, 1),
                pd.NaT,
                datetime(2011, 12, 1),
                datetime(2011, 11, 1),
            ],
            tz="UTC",
        ).values

        ex_keys = [Timestamp("2011-11-01"), Timestamp("2011-12-01")]
        expected = {ex_keys[0]: idx[[0, 4]], ex_keys[1]: idx[[1, 3]]}
        tm.assert_dict_equal(idx.groupby(to_groupby), expected)

    def test_append_preserves_dtype(self, simple_index):
        # In particular Index with dtype float32
        index = simple_index
        N = len(index)

        result = index.append(index)
        assert result.dtype == index.dtype
        tm.assert_index_equal(result[:N], index, check_exact=True)
        tm.assert_index_equal(result[N:], index, check_exact=True)

        alt = index.take(list(range(N)) * 2)
        tm.assert_index_equal(result, alt, check_exact=True)

    def test_inv(self, simple_index, using_infer_string):
        idx = simple_index

        if idx.dtype.kind in ["i", "u"]:
            res = ~idx
            expected = Index(~idx.values, name=idx.name)
            tm.assert_index_equal(res, expected)

            # check that we are matching Series behavior
            res2 = ~Series(idx)
            tm.assert_series_equal(res2, Series(expected))
        else:
            if idx.dtype.kind == "f":
                msg = "ufunc 'invert' not supported for the input types"
            else:
                msg = "bad operand|__invert__ is not supported for string dtype"
            with pytest.raises(TypeError, match=msg):
                ~idx

            # check that we get the same behavior with Series
            with pytest.raises(TypeError, match=msg):
                ~Series(idx)

    def test_is_boolean_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(FutureWarning):
            idx.is_boolean()

    def test_is_floating_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(FutureWarning):
            idx.is_floating()

    def test_is_integer_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(FutureWarning):
            idx.is_integer()

    def test_holds_integer_deprecated(self, simple_index):
        # GH50243
        idx = simple_index
        msg = f"{type(idx).__name__}.holds_integer is deprecated. "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            idx.holds_integer()

    def test_is_numeric_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(
            FutureWarning,
            match=f"{type(idx).__name__}.is_numeric is deprecated. ",
        ):
            idx.is_numeric()

    def test_is_categorical_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(
            FutureWarning,
            match=r"Use pandas\.api\.types\.is_categorical_dtype instead",
        ):
            idx.is_categorical()

    def test_is_interval_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(FutureWarning):
            idx.is_interval()

    def test_is_object_is_deprecated(self, simple_index):
        # GH50042
        idx = simple_index
        with tm.assert_produces_warning(FutureWarning):
            idx.is_object()


class TestNumericBase:
    @pytest.fixture(
        params=[
            RangeIndex(start=0, stop=20, step=2),
            Index(np.arange(5, dtype=np.float64)),
            Index(np.arange(5, dtype=np.float32)),
            Index(np.arange(5, dtype=np.uint64)),
            Index(range(0, 20, 2), dtype=np.int64),
            Index(range(0, 20, 2), dtype=np.int32),
            Index(range(0, 20, 2), dtype=np.int16),
            Index(range(0, 20, 2), dtype=np.int8),
        ]
    )
    def simple_index(self, request):
        return request.param

    def test_constructor_unwraps_index(self, simple_index):
        if isinstance(simple_index, RangeIndex):
            pytest.skip("Tested elsewhere.")
        index_cls = type(simple_index)
        dtype = simple_index.dtype

        idx = Index([1, 2], dtype=dtype)
        result = index_cls(idx)
        expected = np.array([1, 2], dtype=idx.dtype)
        tm.assert_numpy_array_equal(result._data, expected)

    def test_can_hold_identifiers(self, simple_index):
        idx = simple_index
        key = idx[0]
        assert idx._can_hold_identifiers_and_holds_name(key) is False

    def test_view(self, simple_index):
        if isinstance(simple_index, RangeIndex):
            pytest.skip("Tested elsewhere.")
        index_cls = type(simple_index)
        dtype = simple_index.dtype

        idx = index_cls([], dtype=dtype, name="Foo")
        idx_view = idx.view()
        assert idx_view.name == "Foo"

        idx_view = idx.view(dtype)
        tm.assert_index_equal(idx, index_cls(idx_view, name="Foo"), exact=True)

        msg = "Passing a type in .*Index.view is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            idx_view = idx.view(index_cls)
        tm.assert_index_equal(idx, index_cls(idx_view, name="Foo"), exact=True)

    def test_format(self, simple_index):
        # GH35439
        if isinstance(simple_index, DatetimeIndex):
            pytest.skip("Tested elsewhere")
        idx = simple_index
        max_width = max(len(str(x)) for x in idx)
        expected = [str(x).ljust(max_width) for x in idx]
        msg = r"Index\.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert idx.format() == expected

    def test_insert_non_na(self, simple_index):
        # GH#43921 inserting an element that we know we can hold should
        #  not change dtype or type (except for RangeIndex)
        index = simple_index

        result = index.insert(0, index[0])

        expected = Index([index[0]] + list(index), dtype=index.dtype)
        tm.assert_index_equal(result, expected, exact=True)

    def test_insert_na(self, nulls_fixture, simple_index):
        # GH 18295 (test missing)
        index = simple_index
        na_val = nulls_fixture

        if na_val is pd.NaT:
            expected = Index([index[0], pd.NaT] + list(index[1:]), dtype=object)
        else:
            expected = Index([index[0], np.nan] + list(index[1:]))
            # GH#43921 we preserve float dtype
            if index.dtype.kind == "f":
                expected = Index(expected, dtype=index.dtype)

        result = index.insert(1, na_val)
        tm.assert_index_equal(result, expected, exact=True)

    def test_arithmetic_explicit_conversions(self, simple_index):
        # GH 8608
        # add/sub are overridden explicitly for Float/Int Index
        index_cls = type(simple_index)
        if index_cls is RangeIndex:
            idx = RangeIndex(5)
        else:
            idx = index_cls(np.arange(5, dtype="int64"))

        # float conversions
        arr = np.arange(5, dtype="int64") * 3.2
        expected = Index(arr, dtype=np.float64)
        fidx = idx * 3.2
        tm.assert_index_equal(fidx, expected)
        fidx = 3.2 * idx
        tm.assert_index_equal(fidx, expected)

        # interops with numpy arrays
        expected = Index(arr, dtype=np.float64)
        a = np.zeros(5, dtype="float64")
        result = fidx - a
        tm.assert_index_equal(result, expected)

        expected = Index(-arr, dtype=np.float64)
        a = np.zeros(5, dtype="float64")
        result = a - fidx
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("complex_dtype", [np.complex64, np.complex128])
    def test_astype_to_complex(self, complex_dtype, simple_index):
        result = simple_index.astype(complex_dtype)

        assert type(result) is Index and result.dtype == complex_dtype

    def test_cast_string(self, simple_index):
        if isinstance(simple_index, RangeIndex):
            pytest.skip("casting of strings not relevant for RangeIndex")
        result = type(simple_index)(["0", "1", "2"], dtype=simple_index.dtype)
        expected = type(simple_index)([0, 1, 2], dtype=simple_index.dtype)
        tm.assert_index_equal(result, expected)
