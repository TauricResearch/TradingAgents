import re
import weakref

import numpy as np
import pytest
import pytz

from pandas._libs.tslibs.dtypes import NpyDatetimeUnit

from pandas.core.dtypes.base import _registry as registry
from pandas.core.dtypes.common import (
    is_bool_dtype,
    is_categorical_dtype,
    is_datetime64_any_dtype,
    is_datetime64_dtype,
    is_datetime64_ns_dtype,
    is_datetime64tz_dtype,
    is_dtype_equal,
    is_interval_dtype,
    is_period_dtype,
    is_string_dtype,
)
from pandas.core.dtypes.dtypes import (
    CategoricalDtype,
    DatetimeTZDtype,
    IntervalDtype,
    PeriodDtype,
)

import pandas as pd
from pandas import (
    Categorical,
    CategoricalIndex,
    DatetimeIndex,
    IntervalIndex,
    Series,
    SparseDtype,
    date_range,
)
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray


class Base:
    def test_hash(self, dtype):
        hash(dtype)

    def test_equality_invalid(self, dtype):
        assert not dtype == "foo"
        assert not is_dtype_equal(dtype, np.int64)

    def test_numpy_informed(self, dtype):
        # npdev 2020-02-02 changed from "data type not understood" to
        #  "Cannot interpret 'foo' as a data type"
        msg = "|".join(
            ["data type not understood", "Cannot interpret '.*' as a data type"]
        )
        with pytest.raises(TypeError, match=msg):
            np.dtype(dtype)

        assert not dtype == np.str_
        assert not np.str_ == dtype

    def test_pickle(self, dtype):
        # make sure our cache is NOT pickled

        # clear the cache
        type(dtype).reset_cache()
        assert not len(dtype._cache_dtypes)

        # force back to the cache
        result = tm.round_trip_pickle(dtype)
        if not isinstance(dtype, PeriodDtype):
            # Because PeriodDtype has a cython class as a base class,
            #  it has different pickle semantics, and its cache is re-populated
            #  on un-pickling.
            assert not len(dtype._cache_dtypes)
        assert result == dtype


class TestCategoricalDtype(Base):
    @pytest.fixture
    def dtype(self):
        """
        Class level fixture of dtype for TestCategoricalDtype
        """
        return CategoricalDtype()

    def test_hash_vs_equality(self, dtype):
        dtype2 = CategoricalDtype()
        assert dtype == dtype2
        assert dtype2 == dtype
        assert hash(dtype) == hash(dtype2)

    def test_equality(self, dtype):
        assert dtype == "category"
        assert is_dtype_equal(dtype, "category")
        assert "category" == dtype
        assert is_dtype_equal("category", dtype)

        assert dtype == CategoricalDtype()
        assert is_dtype_equal(dtype, CategoricalDtype())
        assert CategoricalDtype() == dtype
        assert is_dtype_equal(CategoricalDtype(), dtype)

        assert dtype != "foo"
        assert not is_dtype_equal(dtype, "foo")
        assert "foo" != dtype
        assert not is_dtype_equal("foo", dtype)

    def test_construction_from_string(self, dtype):
        result = CategoricalDtype.construct_from_string("category")
        assert is_dtype_equal(dtype, result)
        msg = "Cannot construct a 'CategoricalDtype' from 'foo'"
        with pytest.raises(TypeError, match=msg):
            CategoricalDtype.construct_from_string("foo")

    def test_constructor_invalid(self):
        msg = "Parameter 'categories' must be list-like"
        with pytest.raises(TypeError, match=msg):
            CategoricalDtype("category")

    dtype1 = CategoricalDtype(["a", "b"], ordered=True)
    dtype2 = CategoricalDtype(["x", "y"], ordered=False)
    c = Categorical([0, 1], dtype=dtype1)

    @pytest.mark.parametrize(
        "values, categories, ordered, dtype, expected",
        [
            [None, None, None, None, CategoricalDtype()],
            [None, ["a", "b"], True, None, dtype1],
            [c, None, None, dtype2, dtype2],
            [c, ["x", "y"], False, None, dtype2],
        ],
    )
    def test_from_values_or_dtype(self, values, categories, ordered, dtype, expected):
        result = CategoricalDtype._from_values_or_dtype(
            values, categories, ordered, dtype
        )
        assert result == expected

    @pytest.mark.parametrize(
        "values, categories, ordered, dtype",
        [
            [None, ["a", "b"], True, dtype2],
            [None, ["a", "b"], None, dtype2],
            [None, None, True, dtype2],
        ],
    )
    def test_from_values_or_dtype_raises(self, values, categories, ordered, dtype):
        msg = "Cannot specify `categories` or `ordered` together with `dtype`."
        with pytest.raises(ValueError, match=msg):
            CategoricalDtype._from_values_or_dtype(values, categories, ordered, dtype)

    def test_from_values_or_dtype_invalid_dtype(self):
        msg = "Cannot not construct CategoricalDtype from <class 'object'>"
        with pytest.raises(ValueError, match=msg):
            CategoricalDtype._from_values_or_dtype(None, None, None, object)

    def test_is_dtype(self, dtype):
        assert CategoricalDtype.is_dtype(dtype)
        assert CategoricalDtype.is_dtype("category")
        assert CategoricalDtype.is_dtype(CategoricalDtype())
        assert not CategoricalDtype.is_dtype("foo")
        assert not CategoricalDtype.is_dtype(np.float64)

    def test_basic(self, dtype):
        msg = "is_categorical_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_categorical_dtype(dtype)

            factor = Categorical(["a", "b", "b", "a", "a", "c", "c", "c"])

            s = Series(factor, name="A")

            # dtypes
            assert is_categorical_dtype(s.dtype)
            assert is_categorical_dtype(s)
            assert not is_categorical_dtype(np.dtype("float64"))

    def test_tuple_categories(self):
        categories = [(1, "a"), (2, "b"), (3, "c")]
        result = CategoricalDtype(categories)
        assert all(result.categories == categories)

    @pytest.mark.parametrize(
        "categories, expected",
        [
            ([True, False], True),
            ([True, False, None], True),
            ([True, False, "a", "b'"], False),
            ([0, 1], False),
        ],
    )
    def test_is_boolean(self, categories, expected):
        cat = Categorical(categories)
        assert cat.dtype._is_boolean is expected
        assert is_bool_dtype(cat) is expected
        assert is_bool_dtype(cat.dtype) is expected

    def test_dtype_specific_categorical_dtype(self):
        expected = "datetime64[ns]"
        dti = DatetimeIndex([], dtype=expected)
        result = str(Categorical(dti).categories.dtype)
        assert result == expected

    def test_not_string(self):
        # though CategoricalDtype has object kind, it cannot be string
        assert not is_string_dtype(CategoricalDtype())

    def test_repr_range_categories(self):
        rng = pd.Index(range(3))
        dtype = CategoricalDtype(categories=rng, ordered=False)
        result = repr(dtype)

        expected = (
            "CategoricalDtype(categories=range(0, 3), ordered=False, "
            "categories_dtype=int64)"
        )
        assert result == expected

    def test_update_dtype(self):
        # GH 27338
        result = CategoricalDtype(["a"]).update_dtype(Categorical(["b"], ordered=True))
        expected = CategoricalDtype(["b"], ordered=True)
        assert result == expected

    def test_repr(self):
        cat = Categorical(pd.Index([1, 2, 3], dtype="int32"))
        result = cat.dtype.__repr__()
        expected = (
            "CategoricalDtype(categories=[1, 2, 3], ordered=False, "
            "categories_dtype=int32)"
        )
        assert result == expected


class TestDatetimeTZDtype(Base):
    @pytest.fixture
    def dtype(self):
        """
        Class level fixture of dtype for TestDatetimeTZDtype
        """
        return DatetimeTZDtype("ns", "US/Eastern")

    def test_alias_to_unit_raises(self):
        # 23990
        with pytest.raises(ValueError, match="Passing a dtype alias"):
            DatetimeTZDtype("datetime64[ns, US/Central]")

    def test_alias_to_unit_bad_alias_raises(self):
        # 23990
        with pytest.raises(TypeError, match=""):
            DatetimeTZDtype("this is a bad string")

        with pytest.raises(TypeError, match=""):
            DatetimeTZDtype("datetime64[ns, US/NotATZ]")

    def test_hash_vs_equality(self, dtype):
        # make sure that we satisfy is semantics
        dtype2 = DatetimeTZDtype("ns", "US/Eastern")
        dtype3 = DatetimeTZDtype(dtype2)
        assert dtype == dtype2
        assert dtype2 == dtype
        assert dtype3 == dtype
        assert hash(dtype) == hash(dtype2)
        assert hash(dtype) == hash(dtype3)

        dtype4 = DatetimeTZDtype("ns", "US/Central")
        assert dtype2 != dtype4
        assert hash(dtype2) != hash(dtype4)

    def test_construction_non_nanosecond(self):
        res = DatetimeTZDtype("ms", "US/Eastern")
        assert res.unit == "ms"
        assert res._creso == NpyDatetimeUnit.NPY_FR_ms.value
        assert res.str == "|M8[ms]"
        assert str(res) == "datetime64[ms, US/Eastern]"
        assert res.base == np.dtype("M8[ms]")

    def test_day_not_supported(self):
        msg = "DatetimeTZDtype only supports s, ms, us, ns units"
        with pytest.raises(ValueError, match=msg):
            DatetimeTZDtype("D", "US/Eastern")

    def test_subclass(self):
        a = DatetimeTZDtype.construct_from_string("datetime64[ns, US/Eastern]")
        b = DatetimeTZDtype.construct_from_string("datetime64[ns, CET]")

        assert issubclass(type(a), type(a))
        assert issubclass(type(a), type(b))

    def test_compat(self, dtype):
        msg = "is_datetime64tz_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_datetime64tz_dtype(dtype)
            assert is_datetime64tz_dtype("datetime64[ns, US/Eastern]")
        assert is_datetime64_any_dtype(dtype)
        assert is_datetime64_any_dtype("datetime64[ns, US/Eastern]")
        assert is_datetime64_ns_dtype(dtype)
        assert is_datetime64_ns_dtype("datetime64[ns, US/Eastern]")
        assert not is_datetime64_dtype(dtype)
        assert not is_datetime64_dtype("datetime64[ns, US/Eastern]")

    def test_construction_from_string(self, dtype):
        result = DatetimeTZDtype.construct_from_string("datetime64[ns, US/Eastern]")
        assert is_dtype_equal(dtype, result)

    @pytest.mark.parametrize(
        "string",
        [
            "foo",
            "datetime64[ns, notatz]",
            # non-nano unit
            "datetime64[ps, UTC]",
            # dateutil str that returns None from gettz
            "datetime64[ns, dateutil/invalid]",
        ],
    )
    def test_construct_from_string_invalid_raises(self, string):
        msg = f"Cannot construct a 'DatetimeTZDtype' from '{string}'"
        with pytest.raises(TypeError, match=re.escape(msg)):
            DatetimeTZDtype.construct_from_string(string)

    def test_construct_from_string_wrong_type_raises(self):
        msg = "'construct_from_string' expects a string, got <class 'list'>"
        with pytest.raises(TypeError, match=msg):
            DatetimeTZDtype.construct_from_string(["datetime64[ns, notatz]"])

    def test_is_dtype(self, dtype):
        assert not DatetimeTZDtype.is_dtype(None)
        assert DatetimeTZDtype.is_dtype(dtype)
        assert DatetimeTZDtype.is_dtype("datetime64[ns, US/Eastern]")
        assert DatetimeTZDtype.is_dtype("M8[ns, US/Eastern]")
        assert not DatetimeTZDtype.is_dtype("foo")
        assert DatetimeTZDtype.is_dtype(DatetimeTZDtype("ns", "US/Pacific"))
        assert not DatetimeTZDtype.is_dtype(np.float64)

    def test_equality(self, dtype):
        assert is_dtype_equal(dtype, "datetime64[ns, US/Eastern]")
        assert is_dtype_equal(dtype, "M8[ns, US/Eastern]")
        assert is_dtype_equal(dtype, DatetimeTZDtype("ns", "US/Eastern"))
        assert not is_dtype_equal(dtype, "foo")
        assert not is_dtype_equal(dtype, DatetimeTZDtype("ns", "CET"))
        assert not is_dtype_equal(
            DatetimeTZDtype("ns", "US/Eastern"), DatetimeTZDtype("ns", "US/Pacific")
        )

        # numpy compat
        assert is_dtype_equal(np.dtype("M8[ns]"), "datetime64[ns]")

        assert dtype == "M8[ns, US/Eastern]"

    def test_basic(self, dtype):
        msg = "is_datetime64tz_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_datetime64tz_dtype(dtype)

        dr = date_range("20130101", periods=3, tz="US/Eastern")
        s = Series(dr, name="A")

        # dtypes
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_datetime64tz_dtype(s.dtype)
            assert is_datetime64tz_dtype(s)
            assert not is_datetime64tz_dtype(np.dtype("float64"))
            assert not is_datetime64tz_dtype(1.0)

    def test_dst(self):
        dr1 = date_range("2013-01-01", periods=3, tz="US/Eastern")
        s1 = Series(dr1, name="A")
        assert isinstance(s1.dtype, DatetimeTZDtype)

        dr2 = date_range("2013-08-01", periods=3, tz="US/Eastern")
        s2 = Series(dr2, name="A")
        assert isinstance(s2.dtype, DatetimeTZDtype)
        assert s1.dtype == s2.dtype

    @pytest.mark.parametrize("tz", ["UTC", "US/Eastern"])
    @pytest.mark.parametrize("constructor", ["M8", "datetime64"])
    def test_parser(self, tz, constructor):
        # pr #11245
        dtz_str = f"{constructor}[ns, {tz}]"
        result = DatetimeTZDtype.construct_from_string(dtz_str)
        expected = DatetimeTZDtype("ns", tz)
        assert result == expected

    def test_empty(self):
        with pytest.raises(TypeError, match="A 'tz' is required."):
            DatetimeTZDtype()

    def test_tz_standardize(self):
        # GH 24713
        tz = pytz.timezone("US/Eastern")
        dr = date_range("2013-01-01", periods=3, tz="US/Eastern")
        dtype = DatetimeTZDtype("ns", dr.tz)
        assert dtype.tz == tz
        dtype = DatetimeTZDtype("ns", dr[0].tz)
        assert dtype.tz == tz


class TestPeriodDtype(Base):
    @pytest.fixture
    def dtype(self):
        """
        Class level fixture of dtype for TestPeriodDtype
        """
        return PeriodDtype("D")

    def test_hash_vs_equality(self, dtype):
        # make sure that we satisfy is semantics
        dtype2 = PeriodDtype("D")
        dtype3 = PeriodDtype(dtype2)
        assert dtype == dtype2
        assert dtype2 == dtype
        assert dtype3 == dtype
        assert dtype is not dtype2
        assert dtype2 is not dtype
        assert dtype3 is not dtype
        assert hash(dtype) == hash(dtype2)
        assert hash(dtype) == hash(dtype3)

    def test_construction(self):
        with pytest.raises(ValueError, match="Invalid frequency: xx"):
            PeriodDtype("xx")

        for s in ["period[D]", "Period[D]", "D"]:
            dt = PeriodDtype(s)
            assert dt.freq == pd.tseries.offsets.Day()

        for s in ["period[3D]", "Period[3D]", "3D"]:
            dt = PeriodDtype(s)
            assert dt.freq == pd.tseries.offsets.Day(3)

        for s in [
            "period[26h]",
            "Period[26h]",
            "26h",
            "period[1D2h]",
            "Period[1D2h]",
            "1D2h",
        ]:
            dt = PeriodDtype(s)
            assert dt.freq == pd.tseries.offsets.Hour(26)

    def test_cannot_use_custom_businessday(self):
        # GH#52534
        msg = "C is not supported as period frequency"
        msg1 = "<CustomBusinessDay> is not supported as period frequency"
        msg2 = r"PeriodDtype\[B\] is deprecated"
        with pytest.raises(ValueError, match=msg):
            PeriodDtype("C")
        with pytest.raises(ValueError, match=msg1):
            with tm.assert_produces_warning(FutureWarning, match=msg2):
                PeriodDtype(pd.offsets.CustomBusinessDay())

    def test_subclass(self):
        a = PeriodDtype("period[D]")
        b = PeriodDtype("period[3D]")

        assert issubclass(type(a), type(a))
        assert issubclass(type(a), type(b))

    def test_identity(self):
        assert PeriodDtype("period[D]") == PeriodDtype("period[D]")
        assert PeriodDtype("period[D]") is not PeriodDtype("period[D]")

        assert PeriodDtype("period[3D]") == PeriodDtype("period[3D]")
        assert PeriodDtype("period[3D]") is not PeriodDtype("period[3D]")

        assert PeriodDtype("period[1s1us]") == PeriodDtype("period[1000001us]")
        assert PeriodDtype("period[1s1us]") is not PeriodDtype("period[1000001us]")

    def test_compat(self, dtype):
        assert not is_datetime64_ns_dtype(dtype)
        assert not is_datetime64_ns_dtype("period[D]")
        assert not is_datetime64_dtype(dtype)
        assert not is_datetime64_dtype("period[D]")

    def test_construction_from_string(self, dtype):
        result = PeriodDtype("period[D]")
        assert is_dtype_equal(dtype, result)
        result = PeriodDtype.construct_from_string("period[D]")
        assert is_dtype_equal(dtype, result)

        with pytest.raises(TypeError, match="list"):
            PeriodDtype.construct_from_string([1, 2, 3])

    @pytest.mark.parametrize(
        "string",
        [
            "foo",
            "period[foo]",
            "foo[D]",
            "datetime64[ns]",
            "datetime64[ns, US/Eastern]",
        ],
    )
    def test_construct_dtype_from_string_invalid_raises(self, string):
        msg = f"Cannot construct a 'PeriodDtype' from '{string}'"
        with pytest.raises(TypeError, match=re.escape(msg)):
            PeriodDtype.construct_from_string(string)

    def test_is_dtype(self, dtype):
        assert PeriodDtype.is_dtype(dtype)
        assert PeriodDtype.is_dtype("period[D]")
        assert PeriodDtype.is_dtype("period[3D]")
        assert PeriodDtype.is_dtype(PeriodDtype("3D"))
        assert PeriodDtype.is_dtype("period[us]")
        assert PeriodDtype.is_dtype("period[s]")
        assert PeriodDtype.is_dtype(PeriodDtype("us"))
        assert PeriodDtype.is_dtype(PeriodDtype("s"))

        assert not PeriodDtype.is_dtype("D")
        assert not PeriodDtype.is_dtype("3D")
        assert not PeriodDtype.is_dtype("U")
        assert not PeriodDtype.is_dtype("s")
        assert not PeriodDtype.is_dtype("foo")
        assert not PeriodDtype.is_dtype(np.object_)
        assert not PeriodDtype.is_dtype(np.int64)
        assert not PeriodDtype.is_dtype(np.float64)

    def test_equality(self, dtype):
        assert is_dtype_equal(dtype, "period[D]")
        assert is_dtype_equal(dtype, PeriodDtype("D"))
        assert is_dtype_equal(dtype, PeriodDtype("D"))
        assert is_dtype_equal(PeriodDtype("D"), PeriodDtype("D"))

        assert not is_dtype_equal(dtype, "D")
        assert not is_dtype_equal(PeriodDtype("D"), PeriodDtype("2D"))

    def test_basic(self, dtype):
        msg = "is_period_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_period_dtype(dtype)

            pidx = pd.period_range("2013-01-01 09:00", periods=5, freq="h")

            assert is_period_dtype(pidx.dtype)
            assert is_period_dtype(pidx)

            s = Series(pidx, name="A")

            assert is_period_dtype(s.dtype)
            assert is_period_dtype(s)

            assert not is_period_dtype(np.dtype("float64"))
            assert not is_period_dtype(1.0)

    def test_freq_argument_required(self):
        # GH#27388
        msg = "missing 1 required positional argument: 'freq'"
        with pytest.raises(TypeError, match=msg):
            PeriodDtype()

        msg = "PeriodDtype argument should be string or BaseOffset, got NoneType"
        with pytest.raises(TypeError, match=msg):
            # GH#51790
            PeriodDtype(None)

    def test_not_string(self):
        # though PeriodDtype has object kind, it cannot be string
        assert not is_string_dtype(PeriodDtype("D"))

    def test_perioddtype_caching_dateoffset_normalize(self):
        # GH 24121
        per_d = PeriodDtype(pd.offsets.YearEnd(normalize=True))
        assert per_d.freq.normalize

        per_d2 = PeriodDtype(pd.offsets.YearEnd(normalize=False))
        assert not per_d2.freq.normalize

    def test_dont_keep_ref_after_del(self):
        # GH 54184
        dtype = PeriodDtype("D")
        ref = weakref.ref(dtype)
        del dtype
        assert ref() is None


class TestIntervalDtype(Base):
    @pytest.fixture
    def dtype(self):
        """
        Class level fixture of dtype for TestIntervalDtype
        """
        return IntervalDtype("int64", "right")

    def test_hash_vs_equality(self, dtype):
        # make sure that we satisfy is semantics
        dtype2 = IntervalDtype("int64", "right")
        dtype3 = IntervalDtype(dtype2)
        assert dtype == dtype2
        assert dtype2 == dtype
        assert dtype3 == dtype
        assert dtype is not dtype2
        assert dtype2 is not dtype3
        assert dtype3 is not dtype
        assert hash(dtype) == hash(dtype2)
        assert hash(dtype) == hash(dtype3)

        dtype1 = IntervalDtype("interval")
        dtype2 = IntervalDtype(dtype1)
        dtype3 = IntervalDtype("interval")
        assert dtype2 == dtype1
        assert dtype2 == dtype2
        assert dtype2 == dtype3
        assert dtype2 is not dtype1
        assert dtype2 is dtype2
        assert dtype2 is not dtype3
        assert hash(dtype2) == hash(dtype1)
        assert hash(dtype2) == hash(dtype2)
        assert hash(dtype2) == hash(dtype3)

    @pytest.mark.parametrize(
        "subtype", ["interval[int64]", "Interval[int64]", "int64", np.dtype("int64")]
    )
    def test_construction(self, subtype):
        i = IntervalDtype(subtype, closed="right")
        assert i.subtype == np.dtype("int64")
        msg = "is_interval_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_interval_dtype(i)

    @pytest.mark.parametrize(
        "subtype", ["interval[int64]", "Interval[int64]", "int64", np.dtype("int64")]
    )
    def test_construction_allows_closed_none(self, subtype):
        # GH#38394
        dtype = IntervalDtype(subtype)

        assert dtype.closed is None

    def test_closed_mismatch(self):
        msg = "'closed' keyword does not match value specified in dtype string"
        with pytest.raises(ValueError, match=msg):
            IntervalDtype("interval[int64, left]", "right")

    @pytest.mark.parametrize("subtype", [None, "interval", "Interval"])
    def test_construction_generic(self, subtype):
        # generic
        i = IntervalDtype(subtype)
        assert i.subtype is None
        msg = "is_interval_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_interval_dtype(i)

    @pytest.mark.parametrize(
        "subtype",
        [
            CategoricalDtype(list("abc"), False),
            CategoricalDtype(list("wxyz"), True),
            object,
            str,
            "<U10",
            "interval[category]",
            "interval[object]",
        ],
    )
    def test_construction_not_supported(self, subtype):
        # GH 19016
        msg = (
            "category, object, and string subtypes are not supported "
            "for IntervalDtype"
        )
        with pytest.raises(TypeError, match=msg):
            IntervalDtype(subtype)

    @pytest.mark.parametrize("subtype", ["xx", "IntervalA", "Interval[foo]"])
    def test_construction_errors(self, subtype):
        msg = "could not construct IntervalDtype"
        with pytest.raises(TypeError, match=msg):
            IntervalDtype(subtype)

    def test_closed_must_match(self):
        # GH#37933
        dtype = IntervalDtype(np.float64, "left")

        msg = "dtype.closed and 'closed' do not match"
        with pytest.raises(ValueError, match=msg):
            IntervalDtype(dtype, closed="both")

    def test_closed_invalid(self):
        with pytest.raises(ValueError, match="closed must be one of"):
            IntervalDtype(np.float64, "foo")

    def test_construction_from_string(self, dtype):
        result = IntervalDtype("interval[int64, right]")
        assert is_dtype_equal(dtype, result)
        result = IntervalDtype.construct_from_string("interval[int64, right]")
        assert is_dtype_equal(dtype, result)

    @pytest.mark.parametrize("string", [0, 3.14, ("a", "b"), None])
    def test_construction_from_string_errors(self, string):
        # these are invalid entirely
        msg = f"'construct_from_string' expects a string, got {type(string)}"

        with pytest.raises(TypeError, match=re.escape(msg)):
            IntervalDtype.construct_from_string(string)

    @pytest.mark.parametrize("string", ["foo", "foo[int64]", "IntervalA"])
    def test_construction_from_string_error_subtype(self, string):
        # this is an invalid subtype
        msg = (
            "Incorrectly formatted string passed to constructor. "
            r"Valid formats include Interval or Interval\[dtype\] "
            "where dtype is numeric, datetime, or timedelta"
        )

        with pytest.raises(TypeError, match=msg):
            IntervalDtype.construct_from_string(string)

    def test_subclass(self):
        a = IntervalDtype("interval[int64, right]")
        b = IntervalDtype("interval[int64, right]")

        assert issubclass(type(a), type(a))
        assert issubclass(type(a), type(b))

    def test_is_dtype(self, dtype):
        assert IntervalDtype.is_dtype(dtype)
        assert IntervalDtype.is_dtype("interval")
        assert IntervalDtype.is_dtype(IntervalDtype("float64"))
        assert IntervalDtype.is_dtype(IntervalDtype("int64"))
        assert IntervalDtype.is_dtype(IntervalDtype(np.int64))
        assert IntervalDtype.is_dtype(IntervalDtype("float64", "left"))
        assert IntervalDtype.is_dtype(IntervalDtype("int64", "right"))
        assert IntervalDtype.is_dtype(IntervalDtype(np.int64, "both"))

        assert not IntervalDtype.is_dtype("D")
        assert not IntervalDtype.is_dtype("3D")
        assert not IntervalDtype.is_dtype("us")
        assert not IntervalDtype.is_dtype("S")
        assert not IntervalDtype.is_dtype("foo")
        assert not IntervalDtype.is_dtype("IntervalA")
        assert not IntervalDtype.is_dtype(np.object_)
        assert not IntervalDtype.is_dtype(np.int64)
        assert not IntervalDtype.is_dtype(np.float64)

    def test_equality(self, dtype):
        assert is_dtype_equal(dtype, "interval[int64, right]")
        assert is_dtype_equal(dtype, IntervalDtype("int64", "right"))
        assert is_dtype_equal(
            IntervalDtype("int64", "right"), IntervalDtype("int64", "right")
        )

        assert not is_dtype_equal(dtype, "interval[int64]")
        assert not is_dtype_equal(dtype, IntervalDtype("int64"))
        assert not is_dtype_equal(
            IntervalDtype("int64", "right"), IntervalDtype("int64")
        )

        assert not is_dtype_equal(dtype, "int64")
        assert not is_dtype_equal(
            IntervalDtype("int64", "neither"), IntervalDtype("float64", "right")
        )
        assert not is_dtype_equal(
            IntervalDtype("int64", "both"), IntervalDtype("int64", "left")
        )

        # invalid subtype comparisons do not raise when directly compared
        dtype1 = IntervalDtype("float64", "left")
        dtype2 = IntervalDtype("datetime64[ns, US/Eastern]", "left")
        assert dtype1 != dtype2
        assert dtype2 != dtype1

    @pytest.mark.parametrize(
        "subtype",
        [
            None,
            "interval",
            "Interval",
            "int64",
            "uint64",
            "float64",
            "complex128",
            "datetime64",
            "timedelta64",
            PeriodDtype("Q"),
        ],
    )
    def test_equality_generic(self, subtype):
        # GH 18980
        closed = "right" if subtype is not None else None
        dtype = IntervalDtype(subtype, closed=closed)
        assert is_dtype_equal(dtype, "interval")
        assert is_dtype_equal(dtype, IntervalDtype())

    @pytest.mark.parametrize(
        "subtype",
        [
            "int64",
            "uint64",
            "float64",
            "complex128",
            "datetime64",
            "timedelta64",
            PeriodDtype("Q"),
        ],
    )
    def test_name_repr(self, subtype):
        # GH 18980
        closed = "right" if subtype is not None else None
        dtype = IntervalDtype(subtype, closed=closed)
        expected = f"interval[{subtype}, {closed}]"
        assert str(dtype) == expected
        assert dtype.name == "interval"

    @pytest.mark.parametrize("subtype", [None, "interval", "Interval"])
    def test_name_repr_generic(self, subtype):
        # GH 18980
        dtype = IntervalDtype(subtype)
        assert str(dtype) == "interval"
        assert dtype.name == "interval"

    def test_basic(self, dtype):
        msg = "is_interval_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_interval_dtype(dtype)

            ii = IntervalIndex.from_breaks(range(3))

            assert is_interval_dtype(ii.dtype)
            assert is_interval_dtype(ii)

            s = Series(ii, name="A")

            assert is_interval_dtype(s.dtype)
            assert is_interval_dtype(s)

    def test_basic_dtype(self):
        msg = "is_interval_dtype is deprecated"
        with tm.assert_produces_warning(DeprecationWarning, match=msg):
            assert is_interval_dtype("interval[int64, both]")
            assert is_interval_dtype(IntervalIndex.from_tuples([(0, 1)]))
            assert is_interval_dtype(IntervalIndex.from_breaks(np.arange(4)))
            assert is_interval_dtype(
                IntervalIndex.from_breaks(date_range("20130101", periods=3))
            )
            assert not is_interval_dtype("U")
            assert not is_interval_dtype("S")
            assert not is_interval_dtype("foo")
            assert not is_interval_dtype(np.object_)
            assert not is_interval_dtype(np.int64)
            assert not is_interval_dtype(np.float64)

    def test_caching(self):
        # GH 54184: Caching not shown to improve performance
        IntervalDtype.reset_cache()
        dtype = IntervalDtype("int64", "right")
        assert len(IntervalDtype._cache_dtypes) == 0

        IntervalDtype("interval")
        assert len(IntervalDtype._cache_dtypes) == 0

        IntervalDtype.reset_cache()
        tm.round_trip_pickle(dtype)
        assert len(IntervalDtype._cache_dtypes) == 0

    def test_not_string(self):
        # GH30568: though IntervalDtype has object kind, it cannot be string
        assert not is_string_dtype(IntervalDtype())

    def test_unpickling_without_closed(self):
        # GH#38394
        dtype = IntervalDtype("interval")

        assert dtype._closed is None

        tm.round_trip_pickle(dtype)

    def test_dont_keep_ref_after_del(self):
        # GH 54184
        dtype = IntervalDtype("int64", "right")
        ref = weakref.ref(dtype)
        del dtype
        assert ref() is None


class TestCategoricalDtypeParametrized:
    @pytest.mark.parametrize(
        "categories",
        [
            list("abcd"),
            np.arange(1000),
            ["a", "b", 10, 2, 1.3, True],
            [True, False],
            date_range("2017", periods=4),
        ],
    )
    def test_basic(self, categories, ordered):
        c1 = CategoricalDtype(categories, ordered=ordered)
        tm.assert_index_equal(c1.categories, pd.Index(categories))
        assert c1.ordered is ordered

    def test_order_matters(self):
        categories = ["a", "b"]
        c1 = CategoricalDtype(categories, ordered=True)
        c2 = CategoricalDtype(categories, ordered=False)
        c3 = CategoricalDtype(categories, ordered=None)
        assert c1 is not c2
        assert c1 is not c3

    @pytest.mark.parametrize("ordered", [False, None])
    def test_unordered_same(self, ordered):
        c1 = CategoricalDtype(["a", "b"], ordered=ordered)
        c2 = CategoricalDtype(["b", "a"], ordered=ordered)
        assert hash(c1) == hash(c2)

    def test_categories(self):
        result = CategoricalDtype(["a", "b", "c"])
        tm.assert_index_equal(result.categories, pd.Index(["a", "b", "c"]))
        assert result.ordered is False

    def test_equal_but_different(self):
        c1 = CategoricalDtype([1, 2, 3])
        c2 = CategoricalDtype([1.0, 2.0, 3.0])
        assert c1 is not c2
        assert c1 != c2

    def test_equal_but_different_mixed_dtypes(self):
        c1 = CategoricalDtype([1, 2, "3"])
        c2 = CategoricalDtype(["3", 1, 2])
        assert c1 is not c2
        assert c1 == c2

    def test_equal_empty_ordered(self):
        c1 = CategoricalDtype([], ordered=True)
        c2 = CategoricalDtype([], ordered=True)
        assert c1 is not c2
        assert c1 == c2

    def test_equal_empty_unordered(self):
        c1 = CategoricalDtype([])
        c2 = CategoricalDtype([])
        assert c1 is not c2
        assert c1 == c2

    @pytest.mark.parametrize("v1, v2", [([1, 2, 3], [1, 2, 3]), ([1, 2, 3], [3, 2, 1])])
    def test_order_hashes_different(self, v1, v2):
        c1 = CategoricalDtype(v1, ordered=False)
        c2 = CategoricalDtype(v2, ordered=True)
        c3 = CategoricalDtype(v1, ordered=None)
        assert c1 is not c2
        assert c1 is not c3

    def test_nan_invalid(self):
        msg = "Categorical categories cannot be null"
        with pytest.raises(ValueError, match=msg):
            CategoricalDtype([1, 2, np.nan])

    def test_non_unique_invalid(self):
        msg = "Categorical categories must be unique"
        with pytest.raises(ValueError, match=msg):
            CategoricalDtype([1, 2, 1])

    def test_same_categories_different_order(self):
        c1 = CategoricalDtype(["a", "b"], ordered=True)
        c2 = CategoricalDtype(["b", "a"], ordered=True)
        assert c1 is not c2

    @pytest.mark.parametrize("ordered1", [True, False, None])
    @pytest.mark.parametrize("ordered2", [True, False, None])
    def test_categorical_equality(self, ordered1, ordered2):
        # same categories, same order
        # any combination of None/False are equal
        # True/True is the only combination with True that are equal
        c1 = CategoricalDtype(list("abc"), ordered1)
        c2 = CategoricalDtype(list("abc"), ordered2)
        result = c1 == c2
        expected = bool(ordered1) is bool(ordered2)
        assert result is expected

        # same categories, different order
        # any combination of None/False are equal (order doesn't matter)
        # any combination with True are not equal (different order of cats)
        c1 = CategoricalDtype(list("abc"), ordered1)
        c2 = CategoricalDtype(list("cab"), ordered2)
        result = c1 == c2
        expected = (bool(ordered1) is False) and (bool(ordered2) is False)
        assert result is expected

        # different categories
        c2 = CategoricalDtype([1, 2, 3], ordered2)
        assert c1 != c2

        # none categories
        c1 = CategoricalDtype(list("abc"), ordered1)
        c2 = CategoricalDtype(None, ordered2)
        c3 = CategoricalDtype(None, ordered1)
        assert c1 != c2
        assert c2 != c1
        assert c2 == c3

    def test_categorical_dtype_equality_requires_categories(self):
        # CategoricalDtype with categories=None is *not* equal to
        #  any fully-initialized CategoricalDtype
        first = CategoricalDtype(["a", "b"])
        second = CategoricalDtype()
        third = CategoricalDtype(ordered=True)

        assert second == second
        assert third == third

        assert first != second
        assert second != first
        assert first != third
        assert third != first
        assert second == third
        assert third == second

    @pytest.mark.parametrize("categories", [list("abc"), None])
    @pytest.mark.parametrize("other", ["category", "not a category"])
    def test_categorical_equality_strings(self, categories, ordered, other):
        c1 = CategoricalDtype(categories, ordered)
        result = c1 == other
        expected = other == "category"
        assert result is expected

    def test_invalid_raises(self):
        with pytest.raises(TypeError, match="ordered"):
            CategoricalDtype(["a", "b"], ordered="foo")

        with pytest.raises(TypeError, match="'categories' must be list-like"):
            CategoricalDtype("category")

    def test_mixed(self):
        a = CategoricalDtype(["a", "b", 1, 2])
        b = CategoricalDtype(["a", "b", "1", "2"])
        assert hash(a) != hash(b)

    def test_from_categorical_dtype_identity(self):
        c1 = Categorical([1, 2], categories=[1, 2, 3], ordered=True)
        # Identity test for no changes
        c2 = CategoricalDtype._from_categorical_dtype(c1)
        assert c2 is c1

    def test_from_categorical_dtype_categories(self):
        c1 = Categorical([1, 2], categories=[1, 2, 3], ordered=True)
        # override categories
        result = CategoricalDtype._from_categorical_dtype(c1, categories=[2, 3])
        assert result == CategoricalDtype([2, 3], ordered=True)

    def test_from_categorical_dtype_ordered(self):
        c1 = Categorical([1, 2], categories=[1, 2, 3], ordered=True)
        # override ordered
        result = CategoricalDtype._from_categorical_dtype(c1, ordered=False)
        assert result == CategoricalDtype([1, 2, 3], ordered=False)

    def test_from_categorical_dtype_both(self):
        c1 = Categorical([1, 2], categories=[1, 2, 3], ordered=True)
        # override ordered
        result = CategoricalDtype._from_categorical_dtype(
            c1, categories=[1, 2], ordered=False
        )
        assert result == CategoricalDtype([1, 2], ordered=False)

    def test_str_vs_repr(self, ordered, using_infer_string):
        c1 = CategoricalDtype(["a", "b"], ordered=ordered)
        assert str(c1) == "category"
        # Py2 will have unicode prefixes
        dtype = "str" if using_infer_string else "object"
        pat = (
            r"CategoricalDtype\(categories=\[.*\], ordered={ordered}, "
            rf"categories_dtype={dtype}\)"
        )
        assert re.match(pat.format(ordered=ordered), repr(c1))

    def test_categorical_categories(self):
        # GH17884
        c1 = CategoricalDtype(Categorical(["a", "b"]))
        tm.assert_index_equal(c1.categories, pd.Index(["a", "b"]))
        c1 = CategoricalDtype(CategoricalIndex(["a", "b"]))
        tm.assert_index_equal(c1.categories, pd.Index(["a", "b"]))

    @pytest.mark.parametrize(
        "new_categories", [list("abc"), list("cba"), list("wxyz"), None]
    )
    @pytest.mark.parametrize("new_ordered", [True, False, None])
    def test_update_dtype(self, ordered, new_categories, new_ordered):
        original_categories = list("abc")
        dtype = CategoricalDtype(original_categories, ordered)
        new_dtype = CategoricalDtype(new_categories, new_ordered)

        result = dtype.update_dtype(new_dtype)
        expected_categories = pd.Index(new_categories or original_categories)
        expected_ordered = new_ordered if new_ordered is not None else dtype.ordered

        tm.assert_index_equal(result.categories, expected_categories)
        assert result.ordered is expected_ordered

    def test_update_dtype_string(self, ordered):
        dtype = CategoricalDtype(list("abc"), ordered)
        expected_categories = dtype.categories
        expected_ordered = dtype.ordered
        result = dtype.update_dtype("category")
        tm.assert_index_equal(result.categories, expected_categories)
        assert result.ordered is expected_ordered

    @pytest.mark.parametrize("bad_dtype", ["foo", object, np.int64, PeriodDtype("Q")])
    def test_update_dtype_errors(self, bad_dtype):
        dtype = CategoricalDtype(list("abc"), False)
        msg = "a CategoricalDtype must be passed to perform an update, "
        with pytest.raises(ValueError, match=msg):
            dtype.update_dtype(bad_dtype)


@pytest.mark.parametrize(
    "dtype", [CategoricalDtype, IntervalDtype, DatetimeTZDtype, PeriodDtype]
)
def test_registry(dtype):
    assert dtype in registry.dtypes


@pytest.mark.parametrize(
    "dtype, expected",
    [
        ("int64", None),
        ("interval", IntervalDtype()),
        ("interval[int64, neither]", IntervalDtype()),
        ("interval[datetime64[ns], left]", IntervalDtype("datetime64[ns]", "left")),
        ("period[D]", PeriodDtype("D")),
        ("category", CategoricalDtype()),
        ("datetime64[ns, US/Eastern]", DatetimeTZDtype("ns", "US/Eastern")),
    ],
)
def test_registry_find(dtype, expected):
    assert registry.find(dtype) == expected


@pytest.mark.parametrize(
    "dtype, expected",
    [
        (str, False),
        (int, False),
        (bool, True),
        (np.bool_, True),
        (np.array(["a", "b"]), False),
        (Series([1, 2]), False),
        (np.array([True, False]), True),
        (Series([True, False]), True),
        (SparseArray([True, False]), True),
        (SparseDtype(bool), True),
    ],
)
def test_is_bool_dtype(dtype, expected):
    result = is_bool_dtype(dtype)
    assert result is expected


def test_is_bool_dtype_sparse():
    result = is_bool_dtype(Series(SparseArray([True, False])))
    assert result is True


@pytest.mark.parametrize(
    "check",
    [
        is_categorical_dtype,
        is_datetime64tz_dtype,
        is_period_dtype,
        is_datetime64_ns_dtype,
        is_datetime64_dtype,
        is_interval_dtype,
        is_datetime64_any_dtype,
        is_string_dtype,
        is_bool_dtype,
    ],
)
def test_is_dtype_no_warning(check):
    data = pd.DataFrame({"A": [1, 2]})

    warn = None
    msg = f"{check.__name__} is deprecated"
    if (
        check is is_categorical_dtype
        or check is is_interval_dtype
        or check is is_datetime64tz_dtype
        or check is is_period_dtype
    ):
        warn = DeprecationWarning

    with tm.assert_produces_warning(warn, match=msg):
        check(data)

    with tm.assert_produces_warning(warn, match=msg):
        check(data["A"])


def test_period_dtype_compare_to_string():
    # https://github.com/pandas-dev/pandas/issues/37265
    dtype = PeriodDtype(freq="M")
    assert (dtype == "period[M]") is True
    assert (dtype != "period[M]") is False


def test_compare_complex_dtypes():
    # GH 28050
    df = pd.DataFrame(np.arange(5).astype(np.complex128))
    msg = "'<' not supported between instances of 'complex' and 'complex'"

    with pytest.raises(TypeError, match=msg):
        df < df.astype(object)

    with pytest.raises(TypeError, match=msg):
        df.lt(df.astype(object))


def test_cast_string_to_complex():
    # GH 4895
    expected = pd.DataFrame(["1.0+5j", "1.5-3j"], dtype=complex)
    result = pd.DataFrame(["1.0+5j", "1.5-3j"]).astype(complex)
    tm.assert_frame_equal(result, expected)


def test_categorical_complex():
    result = Categorical([1, 2 + 2j])
    expected = Categorical([1.0 + 0.0j, 2.0 + 2.0j])
    tm.assert_categorical_equal(result, expected)
    result = Categorical([1, 2, 2 + 2j])
    expected = Categorical([1.0 + 0.0j, 2.0 + 0.0j, 2.0 + 2.0j])
    tm.assert_categorical_equal(result, expected)


def test_multi_column_dtype_assignment():
    # GH #27583
    df = pd.DataFrame({"a": [0.0], "b": 0.0})
    expected = pd.DataFrame({"a": [0], "b": 0})

    df[["a", "b"]] = 0
    tm.assert_frame_equal(df, expected)

    df["b"] = 0
    tm.assert_frame_equal(df, expected)
