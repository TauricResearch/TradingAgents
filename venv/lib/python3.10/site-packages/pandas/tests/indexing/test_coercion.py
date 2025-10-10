from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
)
import itertools

import numpy as np
import pytest

from pandas.compat import (
    IS64,
    is_platform_windows,
)
from pandas.compat.numpy import np_version_gt2

import pandas as pd
import pandas._testing as tm

###############################################################
# Index / Series common tests which may trigger dtype coercions
###############################################################


@pytest.fixture(autouse=True, scope="class")
def check_comprehensiveness(request):
    # Iterate over combination of dtype, method and klass
    # and ensure that each are contained within a collected test
    cls = request.cls
    combos = itertools.product(cls.klasses, cls.dtypes, [cls.method])

    def has_test(combo):
        klass, dtype, method = combo
        cls_funcs = request.node.session.items
        return any(
            klass in x.name and dtype in x.name and method in x.name for x in cls_funcs
        )

    opts = request.config.option
    if opts.lf or opts.keyword:
        # If we are running with "last-failed" or -k foo, we expect to only
        #  run a subset of tests.
        yield

    else:
        for combo in combos:
            if not has_test(combo):
                raise AssertionError(
                    f"test method is not defined: {cls.__name__}, {combo}"
                )

        yield


class CoercionBase:
    klasses = ["index", "series"]
    dtypes = [
        "object",
        "int64",
        "float64",
        "complex128",
        "bool",
        "datetime64",
        "datetime64tz",
        "timedelta64",
        "period",
    ]

    @property
    def method(self):
        raise NotImplementedError(self)


class TestSetitemCoercion(CoercionBase):
    method = "setitem"

    # disable comprehensiveness tests, as most of these have been moved to
    #  tests.series.indexing.test_setitem in SetitemCastingEquivalents subclasses.
    klasses: list[str] = []

    def test_setitem_series_no_coercion_from_values_list(self):
        # GH35865 - int casted to str when internally calling np.array(ser.values)
        ser = pd.Series(["a", 1])
        ser[:] = list(ser.values)

        expected = pd.Series(["a", 1])

        tm.assert_series_equal(ser, expected)

    def _assert_setitem_index_conversion(
        self, original_series, loc_key, expected_index, expected_dtype
    ):
        """test index's coercion triggered by assign key"""
        temp = original_series.copy()
        # GH#33469 pre-2.0 with int loc_key and temp.index.dtype == np.float64
        #  `temp[loc_key] = 5` treated loc_key as positional
        temp[loc_key] = 5
        exp = pd.Series([1, 2, 3, 4, 5], index=expected_index)
        tm.assert_series_equal(temp, exp)
        # check dtype explicitly for sure
        assert temp.index.dtype == expected_dtype

        temp = original_series.copy()
        temp.loc[loc_key] = 5
        exp = pd.Series([1, 2, 3, 4, 5], index=expected_index)
        tm.assert_series_equal(temp, exp)
        # check dtype explicitly for sure
        assert temp.index.dtype == expected_dtype

    @pytest.mark.parametrize(
        "val,exp_dtype", [("x", object), (5, IndexError), (1.1, object)]
    )
    def test_setitem_index_object(self, val, exp_dtype):
        obj = pd.Series([1, 2, 3, 4], index=pd.Index(list("abcd"), dtype=object))
        assert obj.index.dtype == object

        if exp_dtype is IndexError:
            temp = obj.copy()
            warn_msg = "Series.__setitem__ treating keys as positions is deprecated"
            msg = "index 5 is out of bounds for axis 0 with size 4"
            with pytest.raises(exp_dtype, match=msg):
                with tm.assert_produces_warning(FutureWarning, match=warn_msg):
                    temp[5] = 5
        else:
            exp_index = pd.Index(list("abcd") + [val], dtype=object)
            self._assert_setitem_index_conversion(obj, val, exp_index, exp_dtype)

    @pytest.mark.parametrize(
        "val,exp_dtype", [(5, np.int64), (1.1, np.float64), ("x", object)]
    )
    def test_setitem_index_int64(self, val, exp_dtype):
        obj = pd.Series([1, 2, 3, 4])
        assert obj.index.dtype == np.int64

        exp_index = pd.Index([0, 1, 2, 3, val])
        self._assert_setitem_index_conversion(obj, val, exp_index, exp_dtype)

    @pytest.mark.parametrize(
        "val,exp_dtype", [(5, np.float64), (5.1, np.float64), ("x", object)]
    )
    def test_setitem_index_float64(self, val, exp_dtype, request):
        obj = pd.Series([1, 2, 3, 4], index=[1.1, 2.1, 3.1, 4.1])
        assert obj.index.dtype == np.float64

        exp_index = pd.Index([1.1, 2.1, 3.1, 4.1, val])
        self._assert_setitem_index_conversion(obj, val, exp_index, exp_dtype)

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_series_period(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_index_complex128(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_index_bool(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_index_datetime64(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_index_datetime64tz(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_index_timedelta64(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_setitem_index_period(self):
        raise NotImplementedError


class TestInsertIndexCoercion(CoercionBase):
    klasses = ["index"]
    method = "insert"

    def _assert_insert_conversion(self, original, value, expected, expected_dtype):
        """test coercion triggered by insert"""
        target = original.copy()
        res = target.insert(1, value)
        tm.assert_index_equal(res, expected)
        assert res.dtype == expected_dtype

    @pytest.mark.parametrize(
        "insert, coerced_val, coerced_dtype",
        [
            (1, 1, object),
            (1.1, 1.1, object),
            (False, False, object),
            ("x", "x", object),
        ],
    )
    def test_insert_index_object(self, insert, coerced_val, coerced_dtype):
        obj = pd.Index(list("abcd"), dtype=object)
        assert obj.dtype == object

        exp = pd.Index(["a", coerced_val, "b", "c", "d"], dtype=object)
        self._assert_insert_conversion(obj, insert, exp, coerced_dtype)

    @pytest.mark.parametrize(
        "insert, coerced_val, coerced_dtype",
        [
            (1, 1, None),
            (1.1, 1.1, np.float64),
            (False, False, object),  # GH#36319
            ("x", "x", object),
        ],
    )
    def test_insert_int_index(
        self, any_int_numpy_dtype, insert, coerced_val, coerced_dtype
    ):
        dtype = any_int_numpy_dtype
        obj = pd.Index([1, 2, 3, 4], dtype=dtype)
        coerced_dtype = coerced_dtype if coerced_dtype is not None else dtype

        exp = pd.Index([1, coerced_val, 2, 3, 4], dtype=coerced_dtype)
        self._assert_insert_conversion(obj, insert, exp, coerced_dtype)

    @pytest.mark.parametrize(
        "insert, coerced_val, coerced_dtype",
        [
            (1, 1.0, None),
            # When float_numpy_dtype=float32, this is not the case
            # see the correction below
            (1.1, 1.1, np.float64),
            (False, False, object),  # GH#36319
            ("x", "x", object),
        ],
    )
    def test_insert_float_index(
        self, float_numpy_dtype, insert, coerced_val, coerced_dtype
    ):
        dtype = float_numpy_dtype
        obj = pd.Index([1.0, 2.0, 3.0, 4.0], dtype=dtype)
        coerced_dtype = coerced_dtype if coerced_dtype is not None else dtype

        if np_version_gt2 and dtype == "float32" and coerced_val == 1.1:
            # Hack, in the 2nd test case, since 1.1 can be losslessly cast to float32
            # the expected dtype will be float32 if the original dtype was float32
            coerced_dtype = np.float32
        exp = pd.Index([1.0, coerced_val, 2.0, 3.0, 4.0], dtype=coerced_dtype)
        self._assert_insert_conversion(obj, insert, exp, coerced_dtype)

    @pytest.mark.parametrize(
        "fill_val,exp_dtype",
        [
            (pd.Timestamp("2012-01-01"), "datetime64[ns]"),
            (pd.Timestamp("2012-01-01", tz="US/Eastern"), "datetime64[ns, US/Eastern]"),
        ],
        ids=["datetime64", "datetime64tz"],
    )
    @pytest.mark.parametrize(
        "insert_value",
        [pd.Timestamp("2012-01-01"), pd.Timestamp("2012-01-01", tz="Asia/Tokyo"), 1],
    )
    def test_insert_index_datetimes(self, fill_val, exp_dtype, insert_value):
        obj = pd.DatetimeIndex(
            ["2011-01-01", "2011-01-02", "2011-01-03", "2011-01-04"], tz=fill_val.tz
        ).as_unit("ns")
        assert obj.dtype == exp_dtype

        exp = pd.DatetimeIndex(
            ["2011-01-01", fill_val.date(), "2011-01-02", "2011-01-03", "2011-01-04"],
            tz=fill_val.tz,
        ).as_unit("ns")
        self._assert_insert_conversion(obj, fill_val, exp, exp_dtype)

        if fill_val.tz:
            # mismatched tzawareness
            ts = pd.Timestamp("2012-01-01")
            result = obj.insert(1, ts)
            expected = obj.astype(object).insert(1, ts)
            assert expected.dtype == object
            tm.assert_index_equal(result, expected)

            ts = pd.Timestamp("2012-01-01", tz="Asia/Tokyo")
            result = obj.insert(1, ts)
            # once deprecation is enforced:
            expected = obj.insert(1, ts.tz_convert(obj.dtype.tz))
            assert expected.dtype == obj.dtype
            tm.assert_index_equal(result, expected)

        else:
            # mismatched tzawareness
            ts = pd.Timestamp("2012-01-01", tz="Asia/Tokyo")
            result = obj.insert(1, ts)
            expected = obj.astype(object).insert(1, ts)
            assert expected.dtype == object
            tm.assert_index_equal(result, expected)

        item = 1
        result = obj.insert(1, item)
        expected = obj.astype(object).insert(1, item)
        assert expected[1] == item
        assert expected.dtype == object
        tm.assert_index_equal(result, expected)

    def test_insert_index_timedelta64(self):
        obj = pd.TimedeltaIndex(["1 day", "2 day", "3 day", "4 day"])
        assert obj.dtype == "timedelta64[ns]"

        # timedelta64 + timedelta64 => timedelta64
        exp = pd.TimedeltaIndex(["1 day", "10 day", "2 day", "3 day", "4 day"])
        self._assert_insert_conversion(
            obj, pd.Timedelta("10 day"), exp, "timedelta64[ns]"
        )

        for item in [pd.Timestamp("2012-01-01"), 1]:
            result = obj.insert(1, item)
            expected = obj.astype(object).insert(1, item)
            assert expected.dtype == object
            tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "insert, coerced_val, coerced_dtype",
        [
            (pd.Period("2012-01", freq="M"), "2012-01", "period[M]"),
            (pd.Timestamp("2012-01-01"), pd.Timestamp("2012-01-01"), object),
            (1, 1, object),
            ("x", "x", object),
        ],
    )
    def test_insert_index_period(self, insert, coerced_val, coerced_dtype):
        obj = pd.PeriodIndex(["2011-01", "2011-02", "2011-03", "2011-04"], freq="M")
        assert obj.dtype == "period[M]"

        data = [
            pd.Period("2011-01", freq="M"),
            coerced_val,
            pd.Period("2011-02", freq="M"),
            pd.Period("2011-03", freq="M"),
            pd.Period("2011-04", freq="M"),
        ]
        if isinstance(insert, pd.Period):
            exp = pd.PeriodIndex(data, freq="M")
            self._assert_insert_conversion(obj, insert, exp, coerced_dtype)

            # string that can be parsed to appropriate PeriodDtype
            self._assert_insert_conversion(obj, str(insert), exp, coerced_dtype)

        else:
            result = obj.insert(0, insert)
            expected = obj.astype(object).insert(0, insert)
            tm.assert_index_equal(result, expected)

            # TODO: ATM inserting '2012-01-01 00:00:00' when we have obj.freq=="M"
            #  casts that string to Period[M], not clear that is desirable
            if not isinstance(insert, pd.Timestamp):
                # non-castable string
                result = obj.insert(0, str(insert))
                expected = obj.astype(object).insert(0, str(insert))
                tm.assert_index_equal(result, expected)

    @pytest.mark.xfail(reason="Test not implemented")
    def test_insert_index_complex128(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_insert_index_bool(self):
        raise NotImplementedError


class TestWhereCoercion(CoercionBase):
    method = "where"
    _cond = np.array([True, False, True, False])

    def _assert_where_conversion(
        self, original, cond, values, expected, expected_dtype
    ):
        """test coercion triggered by where"""
        target = original.copy()
        res = target.where(cond, values)
        tm.assert_equal(res, expected)
        assert res.dtype == expected_dtype

    def _construct_exp(self, obj, klass, fill_val, exp_dtype):
        if fill_val is True:
            values = klass([True, False, True, True])
        elif isinstance(fill_val, (datetime, np.datetime64)):
            values = pd.date_range(fill_val, periods=4)
        else:
            values = klass(x * fill_val for x in [5, 6, 7, 8])

        exp = klass([obj[0], values[1], obj[2], values[3]], dtype=exp_dtype)
        return values, exp

    def _run_test(self, obj, fill_val, klass, exp_dtype):
        cond = klass(self._cond)

        exp = klass([obj[0], fill_val, obj[2], fill_val], dtype=exp_dtype)
        self._assert_where_conversion(obj, cond, fill_val, exp, exp_dtype)

        values, exp = self._construct_exp(obj, klass, fill_val, exp_dtype)
        self._assert_where_conversion(obj, cond, values, exp, exp_dtype)

    @pytest.mark.parametrize(
        "fill_val,exp_dtype",
        [(1, object), (1.1, object), (1 + 1j, object), (True, object)],
    )
    def test_where_object(self, index_or_series, fill_val, exp_dtype):
        klass = index_or_series
        obj = klass(list("abcd"), dtype=object)
        assert obj.dtype == object
        self._run_test(obj, fill_val, klass, exp_dtype)

    @pytest.mark.parametrize(
        "fill_val,exp_dtype",
        [(1, np.int64), (1.1, np.float64), (1 + 1j, np.complex128), (True, object)],
    )
    def test_where_int64(self, index_or_series, fill_val, exp_dtype, request):
        klass = index_or_series

        obj = klass([1, 2, 3, 4])
        assert obj.dtype == np.int64
        self._run_test(obj, fill_val, klass, exp_dtype)

    @pytest.mark.parametrize(
        "fill_val, exp_dtype",
        [(1, np.float64), (1.1, np.float64), (1 + 1j, np.complex128), (True, object)],
    )
    def test_where_float64(self, index_or_series, fill_val, exp_dtype, request):
        klass = index_or_series

        obj = klass([1.1, 2.2, 3.3, 4.4])
        assert obj.dtype == np.float64
        self._run_test(obj, fill_val, klass, exp_dtype)

    @pytest.mark.parametrize(
        "fill_val,exp_dtype",
        [
            (1, np.complex128),
            (1.1, np.complex128),
            (1 + 1j, np.complex128),
            (True, object),
        ],
    )
    def test_where_complex128(self, index_or_series, fill_val, exp_dtype):
        klass = index_or_series
        obj = klass([1 + 1j, 2 + 2j, 3 + 3j, 4 + 4j], dtype=np.complex128)
        assert obj.dtype == np.complex128
        self._run_test(obj, fill_val, klass, exp_dtype)

    @pytest.mark.parametrize(
        "fill_val,exp_dtype",
        [(1, object), (1.1, object), (1 + 1j, object), (True, np.bool_)],
    )
    def test_where_series_bool(self, index_or_series, fill_val, exp_dtype):
        klass = index_or_series

        obj = klass([True, False, True, False])
        assert obj.dtype == np.bool_
        self._run_test(obj, fill_val, klass, exp_dtype)

    @pytest.mark.parametrize(
        "fill_val,exp_dtype",
        [
            (pd.Timestamp("2012-01-01"), "datetime64[ns]"),
            (pd.Timestamp("2012-01-01", tz="US/Eastern"), object),
        ],
        ids=["datetime64", "datetime64tz"],
    )
    def test_where_datetime64(self, index_or_series, fill_val, exp_dtype):
        klass = index_or_series

        obj = klass(pd.date_range("2011-01-01", periods=4, freq="D")._with_freq(None))
        assert obj.dtype == "datetime64[ns]"

        fv = fill_val
        # do the check with each of the available datetime scalars
        if exp_dtype == "datetime64[ns]":
            for scalar in [fv, fv.to_pydatetime(), fv.to_datetime64()]:
                self._run_test(obj, scalar, klass, exp_dtype)
        else:
            for scalar in [fv, fv.to_pydatetime()]:
                self._run_test(obj, fill_val, klass, exp_dtype)

    @pytest.mark.xfail(reason="Test not implemented")
    def test_where_index_complex128(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_where_index_bool(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_where_series_timedelta64(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_where_series_period(self):
        raise NotImplementedError

    @pytest.mark.parametrize(
        "value", [pd.Timedelta(days=9), timedelta(days=9), np.timedelta64(9, "D")]
    )
    def test_where_index_timedelta64(self, value):
        tdi = pd.timedelta_range("1 Day", periods=4)
        cond = np.array([True, False, False, True])

        expected = pd.TimedeltaIndex(["1 Day", value, value, "4 Days"])
        result = tdi.where(cond, value)
        tm.assert_index_equal(result, expected)

        # wrong-dtyped NaT
        dtnat = np.datetime64("NaT", "ns")
        expected = pd.Index([tdi[0], dtnat, dtnat, tdi[3]], dtype=object)
        assert expected[1] is dtnat

        result = tdi.where(cond, dtnat)
        tm.assert_index_equal(result, expected)

    def test_where_index_period(self):
        dti = pd.date_range("2016-01-01", periods=3, freq="QS")
        pi = dti.to_period("Q")

        cond = np.array([False, True, False])

        # Passing a valid scalar
        value = pi[-1] + pi.freq * 10
        expected = pd.PeriodIndex([value, pi[1], value])
        result = pi.where(cond, value)
        tm.assert_index_equal(result, expected)

        # Case passing ndarray[object] of Periods
        other = np.asarray(pi + pi.freq * 10, dtype=object)
        result = pi.where(cond, other)
        expected = pd.PeriodIndex([other[0], pi[1], other[2]])
        tm.assert_index_equal(result, expected)

        # Passing a mismatched scalar -> casts to object
        td = pd.Timedelta(days=4)
        expected = pd.Index([td, pi[1], td], dtype=object)
        result = pi.where(cond, td)
        tm.assert_index_equal(result, expected)

        per = pd.Period("2020-04-21", "D")
        expected = pd.Index([per, pi[1], per], dtype=object)
        result = pi.where(cond, per)
        tm.assert_index_equal(result, expected)


class TestFillnaSeriesCoercion(CoercionBase):
    # not indexing, but place here for consistency

    method = "fillna"

    @pytest.mark.xfail(reason="Test not implemented")
    def test_has_comprehensive_tests(self):
        raise NotImplementedError

    def _assert_fillna_conversion(self, original, value, expected, expected_dtype):
        """test coercion triggered by fillna"""
        target = original.copy()
        res = target.fillna(value)
        tm.assert_equal(res, expected)
        assert res.dtype == expected_dtype

    @pytest.mark.parametrize(
        "fill_val, fill_dtype",
        [(1, object), (1.1, object), (1 + 1j, object), (True, object)],
    )
    def test_fillna_object(self, index_or_series, fill_val, fill_dtype):
        klass = index_or_series
        obj = klass(["a", np.nan, "c", "d"], dtype=object)
        assert obj.dtype == object

        exp = klass(["a", fill_val, "c", "d"], dtype=object)
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.parametrize(
        "fill_val,fill_dtype",
        [(1, np.float64), (1.1, np.float64), (1 + 1j, np.complex128), (True, object)],
    )
    def test_fillna_float64(self, index_or_series, fill_val, fill_dtype):
        klass = index_or_series
        obj = klass([1.1, np.nan, 3.3, 4.4])
        assert obj.dtype == np.float64

        exp = klass([1.1, fill_val, 3.3, 4.4])
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.parametrize(
        "fill_val,fill_dtype",
        [
            (1, np.complex128),
            (1.1, np.complex128),
            (1 + 1j, np.complex128),
            (True, object),
        ],
    )
    def test_fillna_complex128(self, index_or_series, fill_val, fill_dtype):
        klass = index_or_series
        obj = klass([1 + 1j, np.nan, 3 + 3j, 4 + 4j], dtype=np.complex128)
        assert obj.dtype == np.complex128

        exp = klass([1 + 1j, fill_val, 3 + 3j, 4 + 4j])
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.parametrize(
        "fill_val,fill_dtype",
        [
            (pd.Timestamp("2012-01-01"), "datetime64[ns]"),
            (pd.Timestamp("2012-01-01", tz="US/Eastern"), object),
            (1, object),
            ("x", object),
        ],
        ids=["datetime64", "datetime64tz", "object", "object"],
    )
    def test_fillna_datetime(self, index_or_series, fill_val, fill_dtype):
        klass = index_or_series
        obj = klass(
            [
                pd.Timestamp("2011-01-01"),
                pd.NaT,
                pd.Timestamp("2011-01-03"),
                pd.Timestamp("2011-01-04"),
            ]
        )
        assert obj.dtype == "datetime64[ns]"

        exp = klass(
            [
                pd.Timestamp("2011-01-01"),
                fill_val,
                pd.Timestamp("2011-01-03"),
                pd.Timestamp("2011-01-04"),
            ]
        )
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.parametrize(
        "fill_val,fill_dtype",
        [
            (pd.Timestamp("2012-01-01", tz="US/Eastern"), "datetime64[ns, US/Eastern]"),
            (pd.Timestamp("2012-01-01"), object),
            # pre-2.0 with a mismatched tz we would get object result
            (pd.Timestamp("2012-01-01", tz="Asia/Tokyo"), "datetime64[ns, US/Eastern]"),
            (1, object),
            ("x", object),
        ],
    )
    def test_fillna_datetime64tz(self, index_or_series, fill_val, fill_dtype):
        klass = index_or_series
        tz = "US/Eastern"

        obj = klass(
            [
                pd.Timestamp("2011-01-01", tz=tz),
                pd.NaT,
                pd.Timestamp("2011-01-03", tz=tz),
                pd.Timestamp("2011-01-04", tz=tz),
            ]
        )
        assert obj.dtype == "datetime64[ns, US/Eastern]"

        if getattr(fill_val, "tz", None) is None:
            fv = fill_val
        else:
            fv = fill_val.tz_convert(tz)
        exp = klass(
            [
                pd.Timestamp("2011-01-01", tz=tz),
                fv,
                pd.Timestamp("2011-01-03", tz=tz),
                pd.Timestamp("2011-01-04", tz=tz),
            ]
        )
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.parametrize(
        "fill_val",
        [
            1,
            1.1,
            1 + 1j,
            True,
            pd.Interval(1, 2, closed="left"),
            pd.Timestamp("2012-01-01", tz="US/Eastern"),
            pd.Timestamp("2012-01-01"),
            pd.Timedelta(days=1),
            pd.Period("2016-01-01", "D"),
        ],
    )
    def test_fillna_interval(self, index_or_series, fill_val):
        ii = pd.interval_range(1.0, 5.0, closed="right").insert(1, np.nan)
        assert isinstance(ii.dtype, pd.IntervalDtype)
        obj = index_or_series(ii)

        exp = index_or_series([ii[0], fill_val, ii[2], ii[3], ii[4]], dtype=object)

        fill_dtype = object
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_series_int64(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_index_int64(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_series_bool(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_index_bool(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_series_timedelta64(self):
        raise NotImplementedError

    @pytest.mark.parametrize(
        "fill_val",
        [
            1,
            1.1,
            1 + 1j,
            True,
            pd.Interval(1, 2, closed="left"),
            pd.Timestamp("2012-01-01", tz="US/Eastern"),
            pd.Timestamp("2012-01-01"),
            pd.Timedelta(days=1),
            pd.Period("2016-01-01", "W"),
        ],
    )
    def test_fillna_series_period(self, index_or_series, fill_val):
        pi = pd.period_range("2016-01-01", periods=4, freq="D").insert(1, pd.NaT)
        assert isinstance(pi.dtype, pd.PeriodDtype)
        obj = index_or_series(pi)

        exp = index_or_series([pi[0], fill_val, pi[2], pi[3], pi[4]], dtype=object)

        fill_dtype = object
        self._assert_fillna_conversion(obj, fill_val, exp, fill_dtype)

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_index_timedelta64(self):
        raise NotImplementedError

    @pytest.mark.xfail(reason="Test not implemented")
    def test_fillna_index_period(self):
        raise NotImplementedError


class TestReplaceSeriesCoercion(CoercionBase):
    klasses = ["series"]
    method = "replace"

    rep: dict[str, list] = {}
    rep["object"] = ["a", "b"]
    rep["int64"] = [4, 5]
    rep["float64"] = [1.1, 2.2]
    rep["complex128"] = [1 + 1j, 2 + 2j]
    rep["bool"] = [True, False]
    rep["datetime64[ns]"] = [pd.Timestamp("2011-01-01"), pd.Timestamp("2011-01-03")]

    for tz in ["UTC", "US/Eastern"]:
        # to test tz => different tz replacement
        key = f"datetime64[ns, {tz}]"
        rep[key] = [
            pd.Timestamp("2011-01-01", tz=tz),
            pd.Timestamp("2011-01-03", tz=tz),
        ]

    rep["timedelta64[ns]"] = [pd.Timedelta("1 day"), pd.Timedelta("2 day")]

    @pytest.fixture(params=["dict", "series"])
    def how(self, request):
        return request.param

    @pytest.fixture(
        params=[
            "object",
            "int64",
            "float64",
            "complex128",
            "bool",
            "datetime64[ns]",
            "datetime64[ns, UTC]",
            "datetime64[ns, US/Eastern]",
            "timedelta64[ns]",
        ]
    )
    def from_key(self, request):
        return request.param

    @pytest.fixture(
        params=[
            "object",
            "int64",
            "float64",
            "complex128",
            "bool",
            "datetime64[ns]",
            "datetime64[ns, UTC]",
            "datetime64[ns, US/Eastern]",
            "timedelta64[ns]",
        ],
        ids=[
            "object",
            "int64",
            "float64",
            "complex128",
            "bool",
            "datetime64",
            "datetime64tz",
            "datetime64tz",
            "timedelta64",
        ],
    )
    def to_key(self, request):
        return request.param

    @pytest.fixture
    def replacer(self, how, from_key, to_key):
        """
        Object we will pass to `Series.replace`
        """
        if how == "dict":
            replacer = dict(zip(self.rep[from_key], self.rep[to_key]))
        elif how == "series":
            replacer = pd.Series(self.rep[to_key], index=self.rep[from_key])
        else:
            raise ValueError
        return replacer

    def test_replace_series(self, how, to_key, from_key, replacer, using_infer_string):
        index = pd.Index([3, 4], name="xxx")
        obj = pd.Series(self.rep[from_key], index=index, name="yyy")
        obj = obj.astype(from_key)
        assert obj.dtype == from_key

        if from_key.startswith("datetime") and to_key.startswith("datetime"):
            # tested below
            return
        elif from_key in ["datetime64[ns, US/Eastern]", "datetime64[ns, UTC]"]:
            # tested below
            return

        if (from_key == "float64" and to_key in ("int64")) or (
            from_key == "complex128" and to_key in ("int64", "float64")
        ):
            if not IS64 or is_platform_windows():
                pytest.skip(f"32-bit platform buggy: {from_key} -> {to_key}")

            # Expected: do not downcast by replacement
            exp = pd.Series(self.rep[to_key], index=index, name="yyy", dtype=from_key)

        else:
            exp = pd.Series(self.rep[to_key], index=index, name="yyy")

        if using_infer_string and exp.dtype == "string":
            # with infer_string, we disable the deprecated downcasting behavior
            exp = exp.astype(object)

        msg = "Downcasting behavior in `replace`"
        warn = FutureWarning
        if (
            exp.dtype == obj.dtype
            or exp.dtype == object
            or (exp.dtype.kind in "iufc" and obj.dtype.kind in "iufc")
        ):
            warn = None
        with tm.assert_produces_warning(warn, match=msg):
            result = obj.replace(replacer)

        tm.assert_series_equal(result, exp)

    @pytest.mark.parametrize(
        "to_key",
        ["timedelta64[ns]", "bool", "object", "complex128", "float64", "int64"],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "from_key", ["datetime64[ns, UTC]", "datetime64[ns, US/Eastern]"], indirect=True
    )
    def test_replace_series_datetime_tz(
        self, how, to_key, from_key, replacer, using_infer_string
    ):
        index = pd.Index([3, 4], name="xyz")
        obj = pd.Series(self.rep[from_key], index=index, name="yyy")
        assert obj.dtype == from_key

        exp = pd.Series(self.rep[to_key], index=index, name="yyy")
        if using_infer_string and exp.dtype == "string":
            # with infer_string, we disable the deprecated downcasting behavior
            exp = exp.astype(object)
        else:
            assert exp.dtype == to_key

        msg = "Downcasting behavior in `replace`"
        warn = FutureWarning if exp.dtype != object else None
        with tm.assert_produces_warning(warn, match=msg):
            result = obj.replace(replacer)

        tm.assert_series_equal(result, exp)

    @pytest.mark.parametrize(
        "to_key",
        ["datetime64[ns]", "datetime64[ns, UTC]", "datetime64[ns, US/Eastern]"],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "from_key",
        ["datetime64[ns]", "datetime64[ns, UTC]", "datetime64[ns, US/Eastern]"],
        indirect=True,
    )
    def test_replace_series_datetime_datetime(self, how, to_key, from_key, replacer):
        index = pd.Index([3, 4], name="xyz")
        obj = pd.Series(self.rep[from_key], index=index, name="yyy")
        assert obj.dtype == from_key

        exp = pd.Series(self.rep[to_key], index=index, name="yyy")
        warn = FutureWarning
        if isinstance(obj.dtype, pd.DatetimeTZDtype) and isinstance(
            exp.dtype, pd.DatetimeTZDtype
        ):
            # with mismatched tzs, we retain the original dtype as of 2.0
            exp = exp.astype(obj.dtype)
            warn = None
        else:
            assert exp.dtype == to_key
            if to_key == from_key:
                warn = None

        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(warn, match=msg):
            result = obj.replace(replacer)

        tm.assert_series_equal(result, exp)

    @pytest.mark.xfail(reason="Test not implemented")
    def test_replace_series_period(self):
        raise NotImplementedError
