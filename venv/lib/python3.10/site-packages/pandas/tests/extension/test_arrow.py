"""
This file contains a minimal set of tests for compliance with the extension
array interface test suite, and should contain no other tests.
The test suite for the full functionality of the array is located in
`pandas/tests/arrays/`.
The tests in this file are inherited from the BaseExtensionTests, and only
minimal tweaks should be applied to get the tests passing (by overwriting a
parent method).
Additional tests should either be added to one of the BaseExtensionTests
classes (if they are relevant for the extension interface for all dtypes), or
be added to the array-specific tests in `pandas/tests/arrays/`.
"""
from __future__ import annotations

from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
from decimal import Decimal
from io import (
    BytesIO,
    StringIO,
)
import operator
import pickle
import re

import numpy as np
import pytest

from pandas._libs import lib
from pandas._libs.tslibs import timezones
from pandas.compat import (
    PY311,
    PY312,
    is_ci_environment,
    is_platform_windows,
    pa_version_under11p0,
    pa_version_under13p0,
    pa_version_under14p0,
    pa_version_under20p0,
    pa_version_under21p0,
)

from pandas.core.dtypes.dtypes import (
    ArrowDtype,
    CategoricalDtypeType,
)

import pandas as pd
import pandas._testing as tm
from pandas.api.extensions import no_default
from pandas.api.types import (
    is_bool_dtype,
    is_float_dtype,
    is_integer_dtype,
    is_numeric_dtype,
    is_signed_integer_dtype,
    is_string_dtype,
    is_unsigned_integer_dtype,
)
from pandas.tests.extension import base

pa = pytest.importorskip("pyarrow")

from pandas.core.arrays.arrow.array import ArrowExtensionArray
from pandas.core.arrays.arrow.extension_types import ArrowPeriodType


def _require_timezone_database(request):
    if is_platform_windows() and is_ci_environment():
        mark = pytest.mark.xfail(
            raises=pa.ArrowInvalid,
            reason=(
                "TODO: Set ARROW_TIMEZONE_DATABASE environment variable "
                "on CI to path to the tzdata for pyarrow."
            ),
        )
        request.applymarker(mark)


@pytest.fixture(params=tm.ALL_PYARROW_DTYPES, ids=str)
def dtype(request):
    return ArrowDtype(pyarrow_dtype=request.param)


@pytest.fixture
def data(dtype):
    pa_dtype = dtype.pyarrow_dtype
    if pa.types.is_boolean(pa_dtype):
        data = [True, False] * 4 + [None] + [True, False] * 44 + [None] + [True, False]
    elif pa.types.is_floating(pa_dtype):
        data = [1.0, 0.0] * 4 + [None] + [-2.0, -1.0] * 44 + [None] + [0.5, 99.5]
    elif pa.types.is_signed_integer(pa_dtype):
        data = [1, 0] * 4 + [None] + [-2, -1] * 44 + [None] + [1, 99]
    elif pa.types.is_unsigned_integer(pa_dtype):
        data = [1, 0] * 4 + [None] + [2, 1] * 44 + [None] + [1, 99]
    elif pa.types.is_decimal(pa_dtype):
        data = (
            [Decimal("1"), Decimal("0.0")] * 4
            + [None]
            + [Decimal("-2.0"), Decimal("-1.0")] * 44
            + [None]
            + [Decimal("0.5"), Decimal("33.123")]
        )
    elif pa.types.is_date(pa_dtype):
        data = (
            [date(2022, 1, 1), date(1999, 12, 31)] * 4
            + [None]
            + [date(2022, 1, 1), date(2022, 1, 1)] * 44
            + [None]
            + [date(1999, 12, 31), date(1999, 12, 31)]
        )
    elif pa.types.is_timestamp(pa_dtype):
        data = (
            [datetime(2020, 1, 1, 1, 1, 1, 1), datetime(1999, 1, 1, 1, 1, 1, 1)] * 4
            + [None]
            + [datetime(2020, 1, 1, 1), datetime(1999, 1, 1, 1)] * 44
            + [None]
            + [datetime(2020, 1, 1), datetime(1999, 1, 1)]
        )
    elif pa.types.is_duration(pa_dtype):
        data = (
            [timedelta(1), timedelta(1, 1)] * 4
            + [None]
            + [timedelta(-1), timedelta(0)] * 44
            + [None]
            + [timedelta(-10), timedelta(10)]
        )
    elif pa.types.is_time(pa_dtype):
        data = (
            [time(12, 0), time(0, 12)] * 4
            + [None]
            + [time(0, 0), time(1, 1)] * 44
            + [None]
            + [time(0, 5), time(5, 0)]
        )
    elif pa.types.is_string(pa_dtype):
        data = ["a", "b"] * 4 + [None] + ["1", "2"] * 44 + [None] + ["!", ">"]
    elif pa.types.is_binary(pa_dtype):
        data = [b"a", b"b"] * 4 + [None] + [b"1", b"2"] * 44 + [None] + [b"!", b">"]
    else:
        raise NotImplementedError
    return pd.array(data, dtype=dtype)


@pytest.fixture
def data_missing(data):
    """Length-2 array with [NA, Valid]"""
    return type(data)._from_sequence([None, data[0]], dtype=data.dtype)


@pytest.fixture(params=["data", "data_missing"])
def all_data(request, data, data_missing):
    """Parametrized fixture returning 'data' or 'data_missing' integer arrays.

    Used to test dtype conversion with and without missing values.
    """
    if request.param == "data":
        return data
    elif request.param == "data_missing":
        return data_missing


@pytest.fixture
def data_for_grouping(dtype):
    """
    Data for factorization, grouping, and unique tests.

    Expected to be like [B, B, NA, NA, A, A, B, C]

    Where A < B < C and NA is missing
    """
    pa_dtype = dtype.pyarrow_dtype
    if pa.types.is_boolean(pa_dtype):
        A = False
        B = True
        C = True
    elif pa.types.is_floating(pa_dtype):
        A = -1.1
        B = 0.0
        C = 1.1
    elif pa.types.is_signed_integer(pa_dtype):
        A = -1
        B = 0
        C = 1
    elif pa.types.is_unsigned_integer(pa_dtype):
        A = 0
        B = 1
        C = 10
    elif pa.types.is_date(pa_dtype):
        A = date(1999, 12, 31)
        B = date(2010, 1, 1)
        C = date(2022, 1, 1)
    elif pa.types.is_timestamp(pa_dtype):
        A = datetime(1999, 1, 1, 1, 1, 1, 1)
        B = datetime(2020, 1, 1)
        C = datetime(2020, 1, 1, 1)
    elif pa.types.is_duration(pa_dtype):
        A = timedelta(-1)
        B = timedelta(0)
        C = timedelta(1, 4)
    elif pa.types.is_time(pa_dtype):
        A = time(0, 0)
        B = time(0, 12)
        C = time(12, 12)
    elif pa.types.is_string(pa_dtype):
        A = "a"
        B = "b"
        C = "c"
    elif pa.types.is_binary(pa_dtype):
        A = b"a"
        B = b"b"
        C = b"c"
    elif pa.types.is_decimal(pa_dtype):
        A = Decimal("-1.1")
        B = Decimal("0.0")
        C = Decimal("1.1")
    else:
        raise NotImplementedError
    return pd.array([B, B, None, None, A, A, B, C], dtype=dtype)


@pytest.fixture
def data_for_sorting(data_for_grouping):
    """
    Length-3 array with a known sort order.

    This should be three items [B, C, A] with
    A < B < C
    """
    return type(data_for_grouping)._from_sequence(
        [data_for_grouping[0], data_for_grouping[7], data_for_grouping[4]],
        dtype=data_for_grouping.dtype,
    )


@pytest.fixture
def data_missing_for_sorting(data_for_grouping):
    """
    Length-3 array with a known sort order.

    This should be three items [B, NA, A] with
    A < B and NA missing.
    """
    return type(data_for_grouping)._from_sequence(
        [data_for_grouping[0], data_for_grouping[2], data_for_grouping[4]],
        dtype=data_for_grouping.dtype,
    )


@pytest.fixture
def data_for_twos(data):
    """Length-100 array in which all the elements are two."""
    pa_dtype = data.dtype.pyarrow_dtype
    if (
        pa.types.is_integer(pa_dtype)
        or pa.types.is_floating(pa_dtype)
        or pa.types.is_decimal(pa_dtype)
        or pa.types.is_duration(pa_dtype)
    ):
        return pd.array([2] * 100, dtype=data.dtype)
    # tests will be xfailed where 2 is not a valid scalar for pa_dtype
    return data
    # TODO: skip otherwise?


class TestArrowArray(base.ExtensionTests):
    def test_compare_scalar(self, data, comparison_op):
        ser = pd.Series(data)
        self._compare_other(ser, data, comparison_op, data[0])

    @pytest.mark.parametrize("na_action", [None, "ignore"])
    def test_map(self, data_missing, na_action):
        if data_missing.dtype.kind in "mM":
            result = data_missing.map(lambda x: x, na_action=na_action)
            expected = data_missing.to_numpy(dtype=object)
            tm.assert_numpy_array_equal(result, expected)
        else:
            result = data_missing.map(lambda x: x, na_action=na_action)
            if data_missing.dtype == "float32[pyarrow]":
                # map roundtrips through objects, which converts to float64
                expected = data_missing.to_numpy(dtype="float64", na_value=np.nan)
            else:
                expected = data_missing.to_numpy()
            tm.assert_numpy_array_equal(result, expected)

    def test_astype_str(self, data, request, using_infer_string):
        pa_dtype = data.dtype.pyarrow_dtype
        if pa.types.is_binary(pa_dtype):
            request.applymarker(
                pytest.mark.xfail(
                    reason=f"For {pa_dtype} .astype(str) decodes.",
                )
            )
        elif not using_infer_string and (
            (pa.types.is_timestamp(pa_dtype) and pa_dtype.tz is None)
            or pa.types.is_duration(pa_dtype)
        ):
            request.applymarker(
                pytest.mark.xfail(
                    reason="pd.Timestamp/pd.Timedelta repr different from numpy repr",
                )
            )
        super().test_astype_str(data)

    def test_from_dtype(self, data, request):
        pa_dtype = data.dtype.pyarrow_dtype
        if pa.types.is_string(pa_dtype) or pa.types.is_decimal(pa_dtype):
            if pa.types.is_string(pa_dtype):
                reason = "ArrowDtype(pa.string()) != StringDtype('pyarrow')"
            else:
                reason = f"pyarrow.type_for_alias cannot infer {pa_dtype}"

            request.applymarker(
                pytest.mark.xfail(
                    reason=reason,
                )
            )
        super().test_from_dtype(data)

    def test_from_sequence_pa_array(self, data):
        # https://github.com/pandas-dev/pandas/pull/47034#discussion_r955500784
        # data._pa_array = pa.ChunkedArray
        result = type(data)._from_sequence(data._pa_array, dtype=data.dtype)
        tm.assert_extension_array_equal(result, data)
        assert isinstance(result._pa_array, pa.ChunkedArray)

        result = type(data)._from_sequence(
            data._pa_array.combine_chunks(), dtype=data.dtype
        )
        tm.assert_extension_array_equal(result, data)
        assert isinstance(result._pa_array, pa.ChunkedArray)

    def test_from_sequence_pa_array_notimplemented(self, request):
        with pytest.raises(NotImplementedError, match="Converting strings to"):
            ArrowExtensionArray._from_sequence_of_strings(
                ["12-1"], dtype=pa.month_day_nano_interval()
            )

    def test_from_sequence_of_strings_pa_array(self, data, request):
        pa_dtype = data.dtype.pyarrow_dtype
        if pa.types.is_time64(pa_dtype) and pa_dtype.equals("time64[ns]") and not PY311:
            request.applymarker(
                pytest.mark.xfail(
                    reason="Nanosecond time parsing not supported.",
                )
            )
        elif pa_version_under11p0 and (
            pa.types.is_duration(pa_dtype) or pa.types.is_decimal(pa_dtype)
        ):
            request.applymarker(
                pytest.mark.xfail(
                    raises=pa.ArrowNotImplementedError,
                    reason=f"pyarrow doesn't support parsing {pa_dtype}",
                )
            )
        elif pa.types.is_timestamp(pa_dtype) and pa_dtype.tz is not None:
            _require_timezone_database(request)

        pa_array = data._pa_array.cast(pa.string())
        result = type(data)._from_sequence_of_strings(pa_array, dtype=data.dtype)
        tm.assert_extension_array_equal(result, data)

        pa_array = pa_array.combine_chunks()
        result = type(data)._from_sequence_of_strings(pa_array, dtype=data.dtype)
        tm.assert_extension_array_equal(result, data)

    def check_accumulate(self, ser, op_name, skipna):
        result = getattr(ser, op_name)(skipna=skipna)

        pa_type = ser.dtype.pyarrow_dtype
        if pa.types.is_temporal(pa_type):
            # Just check that we match the integer behavior.
            if pa_type.bit_width == 32:
                int_type = "int32[pyarrow]"
            else:
                int_type = "int64[pyarrow]"
            ser = ser.astype(int_type)
            result = result.astype(int_type)

        result = result.astype("Float64")
        expected = getattr(ser.astype("Float64"), op_name)(skipna=skipna)
        tm.assert_series_equal(result, expected, check_dtype=False)

    def _supports_accumulation(self, ser: pd.Series, op_name: str) -> bool:
        # error: Item "dtype[Any]" of "dtype[Any] | ExtensionDtype" has no
        # attribute "pyarrow_dtype"
        pa_type = ser.dtype.pyarrow_dtype  # type: ignore[union-attr]

        if pa.types.is_binary(pa_type) or pa.types.is_decimal(pa_type):
            if op_name in ["cumsum", "cumprod", "cummax", "cummin"]:
                return False
        elif pa.types.is_string(pa_type):
            if op_name == "cumprod":
                return False
        elif pa.types.is_boolean(pa_type):
            if op_name in ["cumprod", "cummax", "cummin"]:
                return False
        elif pa.types.is_temporal(pa_type):
            if op_name == "cumsum" and not pa.types.is_duration(pa_type):
                return False
            elif op_name == "cumprod":
                return False
        return True

    @pytest.mark.parametrize("skipna", [True, False])
    def test_accumulate_series(self, data, all_numeric_accumulations, skipna, request):
        pa_type = data.dtype.pyarrow_dtype
        op_name = all_numeric_accumulations

        if pa.types.is_string(pa_type) and op_name in ["cumsum", "cummin", "cummax"]:
            # https://github.com/pandas-dev/pandas/pull/60633
            # Doesn't fit test structure, tested in series/test_cumulative.py instead.
            return

        ser = pd.Series(data)

        if not self._supports_accumulation(ser, op_name):
            # The base class test will check that we raise
            return super().test_accumulate_series(
                data, all_numeric_accumulations, skipna
            )

        if pa_version_under13p0 and all_numeric_accumulations != "cumsum":
            # xfailing takes a long time to run because pytest
            # renders the exception messages even when not showing them
            opt = request.config.option
            if opt.markexpr and "not slow" in opt.markexpr:
                pytest.skip(
                    f"{all_numeric_accumulations} not implemented for pyarrow < 9"
                )
            mark = pytest.mark.xfail(
                reason=f"{all_numeric_accumulations} not implemented for pyarrow < 9"
            )
            request.applymarker(mark)

        elif all_numeric_accumulations == "cumsum" and (
            pa.types.is_boolean(pa_type) or pa.types.is_decimal(pa_type)
        ):
            request.applymarker(
                pytest.mark.xfail(
                    reason=f"{all_numeric_accumulations} not implemented for {pa_type}",
                    raises=TypeError,
                )
            )

        self.check_accumulate(ser, op_name, skipna)

    def _supports_reduction(self, ser: pd.Series, op_name: str) -> bool:
        if op_name == "kurt" or (pa_version_under20p0 and op_name == "skew"):
            return False

        dtype = ser.dtype
        # error: Item "dtype[Any]" of "dtype[Any] | ExtensionDtype" has
        # no attribute "pyarrow_dtype"
        pa_dtype = dtype.pyarrow_dtype  # type: ignore[union-attr]
        if pa.types.is_temporal(pa_dtype) and op_name in [
            "sum",
            "var",
            "skew",
            "kurt",
            "prod",
        ]:
            if pa.types.is_duration(pa_dtype) and op_name in ["sum"]:
                # summing timedeltas is one case that *is* well-defined
                pass
            else:
                return False
        elif pa.types.is_binary(pa_dtype) and op_name in ["sum", "skew"]:
            return False
        elif (
            pa.types.is_string(pa_dtype) or pa.types.is_binary(pa_dtype)
        ) and op_name in [
            "mean",
            "median",
            "prod",
            "std",
            "sem",
            "var",
            "skew",
            "kurt",
        ]:
            return False

        if (
            pa.types.is_temporal(pa_dtype)
            and not pa.types.is_duration(pa_dtype)
            and op_name in ["any", "all"]
        ):
            # xref GH#34479 we support this in our non-pyarrow datetime64 dtypes,
            #  but it isn't obvious we _should_.  For now, we keep the pyarrow
            #  behavior which does not support this.
            return False

        return True

    def check_reduce(self, ser: pd.Series, op_name: str, skipna: bool):
        # error: Item "dtype[Any]" of "dtype[Any] | ExtensionDtype" has no
        # attribute "pyarrow_dtype"
        pa_dtype = ser.dtype.pyarrow_dtype  # type: ignore[union-attr]
        if pa.types.is_integer(pa_dtype) or pa.types.is_floating(pa_dtype):
            alt = ser.astype("Float64")
        else:
            # TODO: in the opposite case, aren't we testing... nothing? For
            # e.g. date/time dtypes trying to calculate 'expected' by converting
            # to object will raise for mean, std etc
            alt = ser

        # TODO: in the opposite case, aren't we testing... nothing?
        if op_name == "count":
            result = getattr(ser, op_name)()
            expected = getattr(alt, op_name)()
        else:
            result = getattr(ser, op_name)(skipna=skipna)
            expected = getattr(alt, op_name)(skipna=skipna)
        tm.assert_almost_equal(result, expected)

    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_series_numeric(self, data, all_numeric_reductions, skipna, request):
        dtype = data.dtype
        pa_dtype = dtype.pyarrow_dtype

        xfail_mark = pytest.mark.xfail(
            raises=TypeError,
            reason=(
                f"{all_numeric_reductions} is not implemented in "
                f"pyarrow={pa.__version__} for {pa_dtype}"
            ),
        )
        if pa.types.is_boolean(pa_dtype) and all_numeric_reductions in {
            "sem",
            "std",
            "var",
            "median",
        }:
            request.applymarker(xfail_mark)
        elif (
            not pa_version_under20p0
            and all_numeric_reductions == "skew"
            and (
                pa.types.is_boolean(pa_dtype)
                or (
                    skipna
                    and (
                        pa.types.is_integer(pa_dtype) or pa.types.is_floating(pa_dtype)
                    )
                )
            )
        ):
            request.applymarker(
                pytest.mark.xfail(
                    reason="https://github.com/apache/arrow/issues/45733",
                )
            )
        super().test_reduce_series_numeric(data, all_numeric_reductions, skipna)

    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_series_boolean(
        self, data, all_boolean_reductions, skipna, na_value, request
    ):
        pa_dtype = data.dtype.pyarrow_dtype
        xfail_mark = pytest.mark.xfail(
            raises=TypeError,
            reason=(
                f"{all_boolean_reductions} is not implemented in "
                f"pyarrow={pa.__version__} for {pa_dtype}"
            ),
        )
        if pa.types.is_string(pa_dtype) or pa.types.is_binary(pa_dtype):
            # We *might* want to make this behave like the non-pyarrow cases,
            #  but have not yet decided.
            request.applymarker(xfail_mark)

        return super().test_reduce_series_boolean(data, all_boolean_reductions, skipna)

    def _get_expected_reduction_dtype(self, arr, op_name: str, skipna: bool):
        pa_type = arr._pa_array.type
        if op_name in ["max", "min"]:
            cmp_dtype = arr.dtype
        elif arr.dtype.name == "decimal128(7, 3)[pyarrow]":
            if op_name == "sum" and not pa_version_under21p0:
                # https://github.com/apache/arrow/pull/44184
                cmp_dtype = ArrowDtype(pa.decimal128(38, 3))
            elif op_name not in ["median", "var", "std", "skew"]:
                cmp_dtype = arr.dtype
            else:
                cmp_dtype = "float64[pyarrow]"
        elif op_name in ["median", "var", "std", "mean", "skew"]:
            cmp_dtype = "float64[pyarrow]"
        elif op_name == "sum" and pa.types.is_string(pa_type):
            cmp_dtype = arr.dtype
        else:
            cmp_dtype = {
                "i": "int64[pyarrow]",
                "u": "uint64[pyarrow]",
                "f": "float64[pyarrow]",
            }[arr.dtype.kind]
        return cmp_dtype

    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_frame(self, data, all_numeric_reductions, skipna, request):
        op_name = all_numeric_reductions
        if op_name == "skew" and pa_version_under20p0:
            if data.dtype._is_numeric:
                mark = pytest.mark.xfail(reason="skew not implemented")
                request.applymarker(mark)
        return super().test_reduce_frame(data, all_numeric_reductions, skipna)

    @pytest.mark.parametrize("typ", ["int64", "uint64", "float64"])
    def test_median_not_approximate(self, typ):
        # GH 52679
        result = pd.Series([1, 2], dtype=f"{typ}[pyarrow]").median()
        assert result == 1.5

    def test_construct_from_string_own_name(self, dtype, request):
        pa_dtype = dtype.pyarrow_dtype
        if pa.types.is_decimal(pa_dtype):
            request.applymarker(
                pytest.mark.xfail(
                    raises=NotImplementedError,
                    reason=f"pyarrow.type_for_alias cannot infer {pa_dtype}",
                )
            )

        if pa.types.is_string(pa_dtype):
            # We still support StringDtype('pyarrow') over ArrowDtype(pa.string())
            msg = r"string\[pyarrow\] should be constructed by StringDtype"
            with pytest.raises(TypeError, match=msg):
                dtype.construct_from_string(dtype.name)

            return

        super().test_construct_from_string_own_name(dtype)

    def test_is_dtype_from_name(self, dtype, request):
        pa_dtype = dtype.pyarrow_dtype
        if pa.types.is_string(pa_dtype):
            # We still support StringDtype('pyarrow') over ArrowDtype(pa.string())
            assert not type(dtype).is_dtype(dtype.name)
        else:
            if pa.types.is_decimal(pa_dtype):
                request.applymarker(
                    pytest.mark.xfail(
                        raises=NotImplementedError,
                        reason=f"pyarrow.type_for_alias cannot infer {pa_dtype}",
                    )
                )
            super().test_is_dtype_from_name(dtype)

    def test_construct_from_string_another_type_raises(self, dtype):
        msg = r"'another_type' must end with '\[pyarrow\]'"
        with pytest.raises(TypeError, match=msg):
            type(dtype).construct_from_string("another_type")

    def test_get_common_dtype(self, dtype, request):
        pa_dtype = dtype.pyarrow_dtype
        if (
            pa.types.is_date(pa_dtype)
            or pa.types.is_time(pa_dtype)
            or (pa.types.is_timestamp(pa_dtype) and pa_dtype.tz is not None)
            or pa.types.is_binary(pa_dtype)
            or pa.types.is_decimal(pa_dtype)
        ):
            request.applymarker(
                pytest.mark.xfail(
                    reason=(
                        f"{pa_dtype} does not have associated numpy "
                        f"dtype findable by find_common_type"
                    )
                )
            )
        super().test_get_common_dtype(dtype)

    def test_is_not_string_type(self, dtype):
        pa_dtype = dtype.pyarrow_dtype
        if pa.types.is_string(pa_dtype):
            assert is_string_dtype(dtype)
        else:
            super().test_is_not_string_type(dtype)

    @pytest.mark.xfail(
        reason="GH 45419: pyarrow.ChunkedArray does not support views.", run=False
    )
    def test_view(self, data):
        super().test_view(data)

    def test_fillna_no_op_returns_copy(self, data):
        data = data[~data.isna()]

        valid = data[0]
        result = data.fillna(valid)
        assert result is not data
        tm.assert_extension_array_equal(result, data)

        result = data.fillna(method="backfill")
        assert result is not data
        tm.assert_extension_array_equal(result, data)

    @pytest.mark.xfail(
        reason="GH 45419: pyarrow.ChunkedArray does not support views", run=False
    )
    def test_transpose(self, data):
        super().test_transpose(data)

    @pytest.mark.xfail(
        reason="GH 45419: pyarrow.ChunkedArray does not support views", run=False
    )
    def test_setitem_preserves_views(self, data):
        super().test_setitem_preserves_views(data)

    @pytest.mark.parametrize("dtype_backend", ["pyarrow", no_default])
    @pytest.mark.parametrize("engine", ["c", "python"])
    def test_EA_types(self, engine, data, dtype_backend, request):
        pa_dtype = data.dtype.pyarrow_dtype
        if pa.types.is_decimal(pa_dtype):
            request.applymarker(
                pytest.mark.xfail(
                    raises=NotImplementedError,
                    reason=f"Parameterized types {pa_dtype} not supported.",
                )
            )
        elif pa.types.is_timestamp(pa_dtype) and pa_dtype.unit in ("us", "ns"):
            request.applymarker(
                pytest.mark.xfail(
                    raises=ValueError,
                    reason="https://github.com/pandas-dev/pandas/issues/49767",
                )
            )
        elif pa.types.is_binary(pa_dtype):
            request.applymarker(
                pytest.mark.xfail(reason="CSV parsers don't correctly handle binary")
            )
        df = pd.DataFrame({"with_dtype": pd.Series(data, dtype=str(data.dtype))})
        csv_output = df.to_csv(index=False, na_rep=np.nan)
        if pa.types.is_binary(pa_dtype):
            csv_output = BytesIO(csv_output)
        else:
            csv_output = StringIO(csv_output)
        result = pd.read_csv(
            csv_output,
            dtype={"with_dtype": str(data.dtype)},
            engine=engine,
            dtype_backend=dtype_backend,
        )
        expected = df
        tm.assert_frame_equal(result, expected)

    def test_invert(self, data, request):
        pa_dtype = data.dtype.pyarrow_dtype
        if not (
            pa.types.is_boolean(pa_dtype)
            or pa.types.is_integer(pa_dtype)
            or pa.types.is_string(pa_dtype)
        ):
            request.applymarker(
                pytest.mark.xfail(
                    raises=pa.ArrowNotImplementedError,
                    reason=f"pyarrow.compute.invert does support {pa_dtype}",
                )
            )
        if PY312 and pa.types.is_boolean(pa_dtype):
            with tm.assert_produces_warning(
                DeprecationWarning, match="Bitwise inversion", check_stacklevel=False
            ):
                super().test_invert(data)
        else:
            super().test_invert(data)

    @pytest.mark.parametrize("periods", [1, -2])
    def test_diff(self, data, periods, request):
        pa_dtype = data.dtype.pyarrow_dtype
        if pa.types.is_unsigned_integer(pa_dtype) and periods == 1:
            request.applymarker(
                pytest.mark.xfail(
                    raises=pa.ArrowInvalid,
                    reason=(
                        f"diff with {pa_dtype} and periods={periods} will overflow"
                    ),
                )
            )
        super().test_diff(data, periods)

    def test_value_counts_returns_pyarrow_int64(self, data):
        # GH 51462
        data = data[:10]
        result = data.value_counts()
        assert result.dtype == ArrowDtype(pa.int64())

    _combine_le_expected_dtype = "bool[pyarrow]"

    def get_op_from_name(self, op_name):
        short_opname = op_name.strip("_")
        if short_opname == "rtruediv":
            # use the numpy version that won't raise on division by zero

            def rtruediv(x, y):
                return np.divide(y, x)

            return rtruediv
        elif short_opname == "rfloordiv":
            return lambda x, y: np.floor_divide(y, x)

        return tm.get_op_from_name(op_name)

    def _cast_pointwise_result(self, op_name: str, obj, other, pointwise_result):
        # BaseOpsUtil._combine can upcast expected dtype
        # (because it generates expected on python scalars)
        # while ArrowExtensionArray maintains original type
        expected = pointwise_result

        if op_name in ["eq", "ne", "lt", "le", "gt", "ge"]:
            return pointwise_result.astype("boolean[pyarrow]")

        was_frame = False
        if isinstance(expected, pd.DataFrame):
            was_frame = True
            expected_data = expected.iloc[:, 0]
            original_dtype = obj.iloc[:, 0].dtype
        else:
            expected_data = expected
            original_dtype = obj.dtype

        orig_pa_type = original_dtype.pyarrow_dtype
        if not was_frame and isinstance(other, pd.Series):
            # i.e. test_arith_series_with_array
            if not (
                pa.types.is_floating(orig_pa_type)
                or (
                    pa.types.is_integer(orig_pa_type)
                    and op_name not in ["__truediv__", "__rtruediv__"]
                )
                or pa.types.is_duration(orig_pa_type)
                or pa.types.is_timestamp(orig_pa_type)
                or pa.types.is_date(orig_pa_type)
                or pa.types.is_decimal(orig_pa_type)
            ):
                # base class _combine always returns int64, while
                #  ArrowExtensionArray does not upcast
                return expected
        elif not (
            (op_name == "__floordiv__" and pa.types.is_integer(orig_pa_type))
            or pa.types.is_duration(orig_pa_type)
            or pa.types.is_timestamp(orig_pa_type)
            or pa.types.is_date(orig_pa_type)
            or pa.types.is_decimal(orig_pa_type)
        ):
            # base class _combine always returns int64, while
            #  ArrowExtensionArray does not upcast
            return expected

        pa_expected = pa.array(expected_data._values)

        if pa.types.is_duration(pa_expected.type):
            if pa.types.is_date(orig_pa_type):
                if pa.types.is_date64(orig_pa_type):
                    # TODO: why is this different vs date32?
                    unit = "ms"
                else:
                    unit = "s"
            else:
                # pyarrow sees sequence of datetime/timedelta objects and defaults
                #  to "us" but the non-pointwise op retains unit
                # timestamp or duration
                unit = orig_pa_type.unit
                if type(other) in [datetime, timedelta] and unit in ["s", "ms"]:
                    # pydatetime/pytimedelta objects have microsecond reso, so we
                    #  take the higher reso of the original and microsecond. Note
                    #  this matches what we would do with DatetimeArray/TimedeltaArray
                    unit = "us"

            pa_expected = pa_expected.cast(f"duration[{unit}]")

        elif pa.types.is_decimal(pa_expected.type) and pa.types.is_decimal(
            orig_pa_type
        ):
            # decimal precision can resize in the result type depending on data
            # just compare the float values
            alt = getattr(obj, op_name)(other)
            alt_dtype = tm.get_dtype(alt)
            assert isinstance(alt_dtype, ArrowDtype)
            if op_name == "__pow__" and isinstance(other, Decimal):
                # TODO: would it make more sense to retain Decimal here?
                alt_dtype = ArrowDtype(pa.float64())
            elif (
                op_name == "__pow__"
                and isinstance(other, pd.Series)
                and other.dtype == original_dtype
            ):
                # TODO: would it make more sense to retain Decimal here?
                alt_dtype = ArrowDtype(pa.float64())
            else:
                assert pa.types.is_decimal(alt_dtype.pyarrow_dtype)
            return expected.astype(alt_dtype)

        else:
            pa_expected = pa_expected.cast(orig_pa_type)

        pd_expected = type(expected_data._values)(pa_expected)
        if was_frame:
            expected = pd.DataFrame(
                pd_expected, index=expected.index, columns=expected.columns
            )
        else:
            expected = pd.Series(pd_expected)
        return expected

    def _is_temporal_supported(self, opname, pa_dtype):
        return (
            (
                opname in ("__add__", "__radd__")
                or (
                    opname
                    in ("__truediv__", "__rtruediv__", "__floordiv__", "__rfloordiv__")
                    and not pa_version_under14p0
                )
            )
            and pa.types.is_duration(pa_dtype)
            or opname in ("__sub__", "__rsub__")
            and pa.types.is_temporal(pa_dtype)
        )

    def _get_expected_exception(
        self, op_name: str, obj, other
    ) -> type[Exception] | tuple[type[Exception], ...] | None:
        if op_name in ("__divmod__", "__rdivmod__"):
            return (NotImplementedError, TypeError)

        exc: type[Exception] | tuple[type[Exception], ...] | None
        dtype = tm.get_dtype(obj)
        # error: Item "dtype[Any]" of "dtype[Any] | ExtensionDtype" has no
        # attribute "pyarrow_dtype"
        pa_dtype = dtype.pyarrow_dtype  # type: ignore[union-attr]

        arrow_temporal_supported = self._is_temporal_supported(op_name, pa_dtype)
        if op_name in {
            "__mod__",
            "__rmod__",
        }:
            exc = (NotImplementedError, TypeError)
        elif arrow_temporal_supported:
            exc = None
        elif op_name in ["__add__", "__radd__"] and (
            pa.types.is_string(pa_dtype) or pa.types.is_binary(pa_dtype)
        ):
            exc = None
        elif not (
            pa.types.is_floating(pa_dtype)
            or pa.types.is_integer(pa_dtype)
            or pa.types.is_decimal(pa_dtype)
        ):
            exc = TypeError
        else:
            exc = None
        return exc

    def _get_arith_xfail_marker(self, opname, pa_dtype):
        mark = None

        arrow_temporal_supported = self._is_temporal_supported(opname, pa_dtype)

        if opname == "__rpow__" and (
            pa.types.is_floating(pa_dtype)
            or pa.types.is_integer(pa_dtype)
            or pa.types.is_decimal(pa_dtype)
        ):
            mark = pytest.mark.xfail(
                reason=(
                    f"GH#29997: 1**pandas.NA == 1 while 1**pyarrow.NA == NULL "
                    f"for {pa_dtype}"
                )
            )
        elif arrow_temporal_supported and (
            pa.types.is_time(pa_dtype)
            or (
                opname
                in ("__truediv__", "__rtruediv__", "__floordiv__", "__rfloordiv__")
                and pa.types.is_duration(pa_dtype)
            )
        ):
            mark = pytest.mark.xfail(
                raises=TypeError,
                reason=(
                    f"{opname} not supported between"
                    f"pd.NA and {pa_dtype} Python scalar"
                ),
            )
        elif opname == "__rfloordiv__" and (
            pa.types.is_integer(pa_dtype) or pa.types.is_decimal(pa_dtype)
        ):
            mark = pytest.mark.xfail(
                raises=pa.ArrowInvalid,
                reason="divide by 0",
            )
        elif opname == "__rtruediv__" and pa.types.is_decimal(pa_dtype):
            mark = pytest.mark.xfail(
                raises=pa.ArrowInvalid,
                reason="divide by 0",
            )

        return mark

    def test_arith_series_with_scalar(self, data, all_arithmetic_operators, request):
        pa_dtype = data.dtype.pyarrow_dtype

        if all_arithmetic_operators == "__rmod__" and pa.types.is_binary(pa_dtype):
            pytest.skip("Skip testing Python string formatting")

        mark = self._get_arith_xfail_marker(all_arithmetic_operators, pa_dtype)
        if mark is not None:
            request.applymarker(mark)

        super().test_arith_series_with_scalar(data, all_arithmetic_operators)

    def test_arith_frame_with_scalar(self, data, all_arithmetic_operators, request):
        pa_dtype = data.dtype.pyarrow_dtype

        if all_arithmetic_operators == "__rmod__" and (
            pa.types.is_string(pa_dtype) or pa.types.is_binary(pa_dtype)
        ):
            pytest.skip("Skip testing Python string formatting")

        mark = self._get_arith_xfail_marker(all_arithmetic_operators, pa_dtype)
        if mark is not None:
            request.applymarker(mark)

        super().test_arith_frame_with_scalar(data, all_arithmetic_operators)

    def test_arith_series_with_array(self, data, all_arithmetic_operators, request):
        pa_dtype = data.dtype.pyarrow_dtype

        if all_arithmetic_operators in (
            "__sub__",
            "__rsub__",
        ) and pa.types.is_unsigned_integer(pa_dtype):
            request.applymarker(
                pytest.mark.xfail(
                    raises=pa.ArrowInvalid,
                    reason=(
                        f"Implemented pyarrow.compute.subtract_checked "
                        f"which raises on overflow for {pa_dtype}"
                    ),
                )
            )

        mark = self._get_arith_xfail_marker(all_arithmetic_operators, pa_dtype)
        if mark is not None:
            request.applymarker(mark)

        op_name = all_arithmetic_operators
        ser = pd.Series(data)
        # pd.Series([ser.iloc[0]] * len(ser)) may not return ArrowExtensionArray
        # since ser.iloc[0] is a python scalar
        other = pd.Series(pd.array([ser.iloc[0]] * len(ser), dtype=data.dtype))

        self.check_opname(ser, op_name, other)

    def test_add_series_with_extension_array(self, data, request):
        pa_dtype = data.dtype.pyarrow_dtype

        if pa_dtype.equals("int8"):
            request.applymarker(
                pytest.mark.xfail(
                    raises=pa.ArrowInvalid,
                    reason=f"raises on overflow for {pa_dtype}",
                )
            )
        super().test_add_series_with_extension_array(data)

    def test_invalid_other_comp(self, data, comparison_op):
        # GH 48833
        with pytest.raises(
            NotImplementedError, match=".* not implemented for <class 'object'>"
        ):
            comparison_op(data, object())

    @pytest.mark.parametrize("masked_dtype", ["boolean", "Int64", "Float64"])
    def test_comp_masked_numpy(self, masked_dtype, comparison_op):
        # GH 52625
        data = [1, 0, None]
        ser_masked = pd.Series(data, dtype=masked_dtype)
        ser_pa = pd.Series(data, dtype=f"{masked_dtype.lower()}[pyarrow]")
        result = comparison_op(ser_pa, ser_masked)
        if comparison_op in [operator.lt, operator.gt, operator.ne]:
            exp = [False, False, None]
        else:
            exp = [True, True, None]
        expected = pd.Series(exp, dtype=ArrowDtype(pa.bool_()))
        tm.assert_series_equal(result, expected)


class TestLogicalOps:
    """Various Series and DataFrame logical ops methods."""

    def test_kleene_or(self):
        a = pd.Series([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean[pyarrow]")
        b = pd.Series([True, False, None] * 3, dtype="boolean[pyarrow]")
        result = a | b
        expected = pd.Series(
            [True, True, True, True, False, None, True, None, None],
            dtype="boolean[pyarrow]",
        )
        tm.assert_series_equal(result, expected)

        result = b | a
        tm.assert_series_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_series_equal(
            a,
            pd.Series([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean[pyarrow]"),
        )
        tm.assert_series_equal(
            b, pd.Series([True, False, None] * 3, dtype="boolean[pyarrow]")
        )

    @pytest.mark.parametrize(
        "other, expected",
        [
            (None, [True, None, None]),
            (pd.NA, [True, None, None]),
            (True, [True, True, True]),
            (np.bool_(True), [True, True, True]),
            (False, [True, False, None]),
            (np.bool_(False), [True, False, None]),
        ],
    )
    def test_kleene_or_scalar(self, other, expected):
        a = pd.Series([True, False, None], dtype="boolean[pyarrow]")
        result = a | other
        expected = pd.Series(expected, dtype="boolean[pyarrow]")
        tm.assert_series_equal(result, expected)

        result = other | a
        tm.assert_series_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_series_equal(
            a, pd.Series([True, False, None], dtype="boolean[pyarrow]")
        )

    def test_kleene_and(self):
        a = pd.Series([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean[pyarrow]")
        b = pd.Series([True, False, None] * 3, dtype="boolean[pyarrow]")
        result = a & b
        expected = pd.Series(
            [True, False, None, False, False, False, None, False, None],
            dtype="boolean[pyarrow]",
        )
        tm.assert_series_equal(result, expected)

        result = b & a
        tm.assert_series_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_series_equal(
            a,
            pd.Series([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean[pyarrow]"),
        )
        tm.assert_series_equal(
            b, pd.Series([True, False, None] * 3, dtype="boolean[pyarrow]")
        )

    @pytest.mark.parametrize(
        "other, expected",
        [
            (None, [None, False, None]),
            (pd.NA, [None, False, None]),
            (True, [True, False, None]),
            (False, [False, False, False]),
            (np.bool_(True), [True, False, None]),
            (np.bool_(False), [False, False, False]),
        ],
    )
    def test_kleene_and_scalar(self, other, expected):
        a = pd.Series([True, False, None], dtype="boolean[pyarrow]")
        result = a & other
        expected = pd.Series(expected, dtype="boolean[pyarrow]")
        tm.assert_series_equal(result, expected)

        result = other & a
        tm.assert_series_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_series_equal(
            a, pd.Series([True, False, None], dtype="boolean[pyarrow]")
        )

    def test_kleene_xor(self):
        a = pd.Series([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean[pyarrow]")
        b = pd.Series([True, False, None] * 3, dtype="boolean[pyarrow]")
        result = a ^ b
        expected = pd.Series(
            [False, True, None, True, False, None, None, None, None],
            dtype="boolean[pyarrow]",
        )
        tm.assert_series_equal(result, expected)

        result = b ^ a
        tm.assert_series_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_series_equal(
            a,
            pd.Series([True] * 3 + [False] * 3 + [None] * 3, dtype="boolean[pyarrow]"),
        )
        tm.assert_series_equal(
            b, pd.Series([True, False, None] * 3, dtype="boolean[pyarrow]")
        )

    @pytest.mark.parametrize(
        "other, expected",
        [
            (None, [None, None, None]),
            (pd.NA, [None, None, None]),
            (True, [False, True, None]),
            (np.bool_(True), [False, True, None]),
            (np.bool_(False), [True, False, None]),
        ],
    )
    def test_kleene_xor_scalar(self, other, expected):
        a = pd.Series([True, False, None], dtype="boolean[pyarrow]")
        result = a ^ other
        expected = pd.Series(expected, dtype="boolean[pyarrow]")
        tm.assert_series_equal(result, expected)

        result = other ^ a
        tm.assert_series_equal(result, expected)

        # ensure we haven't mutated anything inplace
        tm.assert_series_equal(
            a, pd.Series([True, False, None], dtype="boolean[pyarrow]")
        )

    @pytest.mark.parametrize(
        "op, exp",
        [
            ["__and__", True],
            ["__or__", True],
            ["__xor__", False],
        ],
    )
    def test_logical_masked_numpy(self, op, exp):
        # GH 52625
        data = [True, False, None]
        ser_masked = pd.Series(data, dtype="boolean")
        ser_pa = pd.Series(data, dtype="boolean[pyarrow]")
        result = getattr(ser_pa, op)(ser_masked)
        expected = pd.Series([exp, False, None], dtype=ArrowDtype(pa.bool_()))
        tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.ALL_INT_PYARROW_DTYPES)
def test_bitwise(pa_type):
    # GH 54495
    dtype = ArrowDtype(pa_type)
    left = pd.Series([1, None, 3, 4], dtype=dtype)
    right = pd.Series([None, 3, 5, 4], dtype=dtype)

    result = left | right
    expected = pd.Series([None, None, 3 | 5, 4 | 4], dtype=dtype)
    tm.assert_series_equal(result, expected)

    result = left & right
    expected = pd.Series([None, None, 3 & 5, 4 & 4], dtype=dtype)
    tm.assert_series_equal(result, expected)

    result = left ^ right
    expected = pd.Series([None, None, 3 ^ 5, 4 ^ 4], dtype=dtype)
    tm.assert_series_equal(result, expected)

    result = ~left
    expected = ~(left.fillna(0).to_numpy())
    expected = pd.Series(expected, dtype=dtype).mask(left.isnull())
    tm.assert_series_equal(result, expected)


def test_arrowdtype_construct_from_string_type_with_unsupported_parameters():
    with pytest.raises(NotImplementedError, match="Passing pyarrow type"):
        ArrowDtype.construct_from_string("not_a_real_dype[s, tz=UTC][pyarrow]")

    with pytest.raises(NotImplementedError, match="Passing pyarrow type"):
        ArrowDtype.construct_from_string("decimal(7, 2)[pyarrow]")


def test_arrowdtype_construct_from_string_supports_dt64tz():
    # as of GH#50689, timestamptz is supported
    dtype = ArrowDtype.construct_from_string("timestamp[s, tz=UTC][pyarrow]")
    expected = ArrowDtype(pa.timestamp("s", "UTC"))
    assert dtype == expected


def test_arrowdtype_construct_from_string_type_only_one_pyarrow():
    # GH#51225
    invalid = "int64[pyarrow]foobar[pyarrow]"
    msg = (
        r"Passing pyarrow type specific parameters \(\[pyarrow\]\) in the "
        r"string is not supported\."
    )
    with pytest.raises(NotImplementedError, match=msg):
        pd.Series(range(3), dtype=invalid)


def test_arrow_string_multiplication():
    # GH 56537
    binary = pd.Series(["abc", "defg"], dtype=ArrowDtype(pa.string()))
    repeat = pd.Series([2, -2], dtype="int64[pyarrow]")
    result = binary * repeat
    expected = pd.Series(["abcabc", ""], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)
    reflected_result = repeat * binary
    tm.assert_series_equal(result, reflected_result)


def test_arrow_string_multiplication_scalar_repeat():
    binary = pd.Series(["abc", "defg"], dtype=ArrowDtype(pa.string()))
    result = binary * 2
    expected = pd.Series(["abcabc", "defgdefg"], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)
    reflected_result = 2 * binary
    tm.assert_series_equal(reflected_result, expected)


@pytest.mark.parametrize(
    "interpolation", ["linear", "lower", "higher", "nearest", "midpoint"]
)
@pytest.mark.parametrize("quantile", [0.5, [0.5, 0.5]])
def test_quantile(data, interpolation, quantile, request):
    pa_dtype = data.dtype.pyarrow_dtype

    data = data.take([0, 0, 0])
    ser = pd.Series(data)

    if (
        pa.types.is_string(pa_dtype)
        or pa.types.is_binary(pa_dtype)
        or pa.types.is_boolean(pa_dtype)
    ):
        # For string, bytes, and bool, we don't *expect* to have quantile work
        # Note this matches the non-pyarrow behavior
        msg = r"Function 'quantile' has no kernel matching input types \(.*\)"
        with pytest.raises(pa.ArrowNotImplementedError, match=msg):
            ser.quantile(q=quantile, interpolation=interpolation)
        return

    if (
        pa.types.is_integer(pa_dtype)
        or pa.types.is_floating(pa_dtype)
        or pa.types.is_decimal(pa_dtype)
    ):
        pass
    elif pa.types.is_temporal(data._pa_array.type):
        pass
    else:
        request.applymarker(
            pytest.mark.xfail(
                raises=pa.ArrowNotImplementedError,
                reason=f"quantile not supported by pyarrow for {pa_dtype}",
            )
        )
    data = data.take([0, 0, 0])
    ser = pd.Series(data)
    result = ser.quantile(q=quantile, interpolation=interpolation)

    if pa.types.is_timestamp(pa_dtype) and interpolation not in ["lower", "higher"]:
        # rounding error will make the check below fail
        #  (e.g. '2020-01-01 01:01:01.000001' vs '2020-01-01 01:01:01.000001024'),
        #  so we'll check for now that we match the numpy analogue
        if pa_dtype.tz:
            pd_dtype = f"M8[{pa_dtype.unit}, {pa_dtype.tz}]"
        else:
            pd_dtype = f"M8[{pa_dtype.unit}]"
        ser_np = ser.astype(pd_dtype)

        expected = ser_np.quantile(q=quantile, interpolation=interpolation)
        if quantile == 0.5:
            if pa_dtype.unit == "us":
                expected = expected.to_pydatetime(warn=False)
            assert result == expected
        else:
            if pa_dtype.unit == "us":
                expected = expected.dt.floor("us")
            tm.assert_series_equal(result, expected.astype(data.dtype))
        return

    if quantile == 0.5:
        assert result == data[0]
    else:
        # Just check the values
        expected = pd.Series(data.take([0, 0]), index=[0.5, 0.5])
        if (
            pa.types.is_integer(pa_dtype)
            or pa.types.is_floating(pa_dtype)
            or pa.types.is_decimal(pa_dtype)
        ):
            expected = expected.astype("float64[pyarrow]")
            result = result.astype("float64[pyarrow]")
        tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "take_idx, exp_idx",
    [[[0, 0, 2, 2, 4, 4], [4, 0]], [[0, 0, 0, 2, 4, 4], [0]]],
    ids=["multi_mode", "single_mode"],
)
def test_mode_dropna_true(data_for_grouping, take_idx, exp_idx):
    data = data_for_grouping.take(take_idx)
    ser = pd.Series(data)
    result = ser.mode(dropna=True)
    expected = pd.Series(data_for_grouping.take(exp_idx))
    tm.assert_series_equal(result, expected)


def test_mode_dropna_false_mode_na(data):
    # GH 50982
    more_nans = pd.Series([None, None, data[0]], dtype=data.dtype)
    result = more_nans.mode(dropna=False)
    expected = pd.Series([None], dtype=data.dtype)
    tm.assert_series_equal(result, expected)

    expected = pd.Series([data[0], None], dtype=data.dtype)
    result = expected.mode(dropna=False)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "arrow_dtype, expected_type",
    [
        [pa.binary(), bytes],
        [pa.binary(16), bytes],
        [pa.large_binary(), bytes],
        [pa.large_string(), str],
        [pa.list_(pa.int64()), list],
        [pa.large_list(pa.int64()), list],
        [pa.map_(pa.string(), pa.int64()), list],
        [pa.struct([("f1", pa.int8()), ("f2", pa.string())]), dict],
        [pa.dictionary(pa.int64(), pa.int64()), CategoricalDtypeType],
    ],
)
def test_arrow_dtype_type(arrow_dtype, expected_type):
    # GH 51845
    # TODO: Redundant with test_getitem_scalar once arrow_dtype exists in data fixture
    assert ArrowDtype(arrow_dtype).type == expected_type


def test_is_bool_dtype():
    # GH 22667
    data = ArrowExtensionArray(pa.array([True, False, True]))
    assert is_bool_dtype(data)
    assert pd.core.common.is_bool_indexer(data)
    s = pd.Series(range(len(data)))
    result = s[data]
    expected = s[np.asarray(data)]
    tm.assert_series_equal(result, expected)


def test_is_numeric_dtype(data):
    # GH 50563
    pa_type = data.dtype.pyarrow_dtype
    if (
        pa.types.is_floating(pa_type)
        or pa.types.is_integer(pa_type)
        or pa.types.is_decimal(pa_type)
    ):
        assert is_numeric_dtype(data)
    else:
        assert not is_numeric_dtype(data)


def test_is_integer_dtype(data):
    # GH 50667
    pa_type = data.dtype.pyarrow_dtype
    if pa.types.is_integer(pa_type):
        assert is_integer_dtype(data)
    else:
        assert not is_integer_dtype(data)


def test_is_signed_integer_dtype(data):
    pa_type = data.dtype.pyarrow_dtype
    if pa.types.is_signed_integer(pa_type):
        assert is_signed_integer_dtype(data)
    else:
        assert not is_signed_integer_dtype(data)


def test_is_unsigned_integer_dtype(data):
    pa_type = data.dtype.pyarrow_dtype
    if pa.types.is_unsigned_integer(pa_type):
        assert is_unsigned_integer_dtype(data)
    else:
        assert not is_unsigned_integer_dtype(data)


def test_is_float_dtype(data):
    pa_type = data.dtype.pyarrow_dtype
    if pa.types.is_floating(pa_type):
        assert is_float_dtype(data)
    else:
        assert not is_float_dtype(data)


def test_pickle_roundtrip(data):
    # GH 42600
    expected = pd.Series(data)
    expected_sliced = expected.head(2)
    full_pickled = pickle.dumps(expected)
    sliced_pickled = pickle.dumps(expected_sliced)

    assert len(full_pickled) > len(sliced_pickled)

    result = pickle.loads(full_pickled)
    tm.assert_series_equal(result, expected)

    result_sliced = pickle.loads(sliced_pickled)
    tm.assert_series_equal(result_sliced, expected_sliced)


def test_astype_from_non_pyarrow(data):
    # GH49795
    pd_array = data._pa_array.to_pandas().array
    result = pd_array.astype(data.dtype)
    assert not isinstance(pd_array.dtype, ArrowDtype)
    assert isinstance(result.dtype, ArrowDtype)
    tm.assert_extension_array_equal(result, data)


def test_astype_float_from_non_pyarrow_str():
    # GH50430
    ser = pd.Series(["1.0"])
    result = ser.astype("float64[pyarrow]")
    expected = pd.Series([1.0], dtype="float64[pyarrow]")
    tm.assert_series_equal(result, expected)


def test_astype_errors_ignore():
    # GH 55399
    expected = pd.DataFrame({"col": [17000000]}, dtype="int32[pyarrow]")
    result = expected.astype("float[pyarrow]", errors="ignore")
    tm.assert_frame_equal(result, expected)


def test_to_numpy_with_defaults(data):
    # GH49973
    result = data.to_numpy()

    pa_type = data._pa_array.type
    if pa.types.is_duration(pa_type) or pa.types.is_timestamp(pa_type):
        pytest.skip("Tested in test_to_numpy_temporal")
    elif pa.types.is_date(pa_type):
        expected = np.array(list(data))
    else:
        expected = np.array(data._pa_array)

    if data._hasna and not is_numeric_dtype(data.dtype):
        expected = expected.astype(object)
        expected[pd.isna(data)] = pd.NA

    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_int_with_na():
    # GH51227: ensure to_numpy does not convert int to float
    data = [1, None]
    arr = pd.array(data, dtype="int64[pyarrow]")
    result = arr.to_numpy()
    expected = np.array([1, np.nan])
    assert isinstance(result[0], float)
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("na_val, exp", [(lib.no_default, np.nan), (1, 1)])
def test_to_numpy_null_array(na_val, exp):
    # GH#52443
    arr = pd.array([pd.NA, pd.NA], dtype="null[pyarrow]")
    result = arr.to_numpy(dtype="float64", na_value=na_val)
    expected = np.array([exp] * 2, dtype="float64")
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_null_array_no_dtype():
    # GH#52443
    arr = pd.array([pd.NA, pd.NA], dtype="null[pyarrow]")
    result = arr.to_numpy(dtype=None)
    expected = np.array([pd.NA] * 2, dtype="object")
    tm.assert_numpy_array_equal(result, expected)


def test_to_numpy_without_dtype():
    # GH 54808
    arr = pd.array([True, pd.NA], dtype="boolean[pyarrow]")
    result = arr.to_numpy(na_value=False)
    expected = np.array([True, False], dtype=np.bool_)
    tm.assert_numpy_array_equal(result, expected)

    arr = pd.array([1.0, pd.NA], dtype="float32[pyarrow]")
    result = arr.to_numpy(na_value=0.0)
    expected = np.array([1.0, 0.0], dtype=np.float32)
    tm.assert_numpy_array_equal(result, expected)


def test_setitem_null_slice(data):
    # GH50248
    orig = data.copy()

    result = orig.copy()
    result[:] = data[0]
    expected = ArrowExtensionArray._from_sequence(
        [data[0]] * len(data),
        dtype=data.dtype,
    )
    tm.assert_extension_array_equal(result, expected)

    result = orig.copy()
    result[:] = data[::-1]
    expected = data[::-1]
    tm.assert_extension_array_equal(result, expected)

    result = orig.copy()
    result[:] = data.tolist()
    expected = data
    tm.assert_extension_array_equal(result, expected)


def test_setitem_invalid_dtype(data):
    # GH50248
    pa_type = data._pa_array.type
    if pa.types.is_string(pa_type) or pa.types.is_binary(pa_type):
        fill_value = 123
        err = TypeError
        msg = "Invalid value '123' for dtype"
    elif (
        pa.types.is_integer(pa_type)
        or pa.types.is_floating(pa_type)
        or pa.types.is_boolean(pa_type)
    ):
        fill_value = "foo"
        err = pa.ArrowInvalid
        msg = "Could not convert"
    else:
        fill_value = "foo"
        err = TypeError
        msg = "Invalid value 'foo' for dtype"
    with pytest.raises(err, match=msg):
        data[:] = fill_value


def test_from_arrow_respecting_given_dtype():
    date_array = pa.array(
        [pd.Timestamp("2019-12-31"), pd.Timestamp("2019-12-31")], type=pa.date32()
    )
    result = date_array.to_pandas(
        types_mapper={pa.date32(): ArrowDtype(pa.date64())}.get
    )
    expected = pd.Series(
        [pd.Timestamp("2019-12-31"), pd.Timestamp("2019-12-31")],
        dtype=ArrowDtype(pa.date64()),
    )
    tm.assert_series_equal(result, expected)


def test_from_arrow_respecting_given_dtype_unsafe():
    array = pa.array([1.5, 2.5], type=pa.float64())
    with tm.external_error_raised(pa.ArrowInvalid):
        array.to_pandas(types_mapper={pa.float64(): ArrowDtype(pa.int64())}.get)


def test_round():
    dtype = "float64[pyarrow]"

    ser = pd.Series([0.0, 1.23, 2.56, pd.NA], dtype=dtype)
    result = ser.round(1)
    expected = pd.Series([0.0, 1.2, 2.6, pd.NA], dtype=dtype)
    tm.assert_series_equal(result, expected)

    ser = pd.Series([123.4, pd.NA, 56.78], dtype=dtype)
    result = ser.round(-1)
    expected = pd.Series([120.0, pd.NA, 60.0], dtype=dtype)
    tm.assert_series_equal(result, expected)


def test_searchsorted_with_na_raises(data_for_sorting, as_series):
    # GH50447
    b, c, a = data_for_sorting
    arr = data_for_sorting.take([2, 0, 1])  # to get [a, b, c]
    arr[-1] = pd.NA

    if as_series:
        arr = pd.Series(arr)

    msg = (
        "searchsorted requires array to be sorted, "
        "which is impossible with NAs present."
    )
    with pytest.raises(ValueError, match=msg):
        arr.searchsorted(b)


def test_sort_values_dictionary():
    df = pd.DataFrame(
        {
            "a": pd.Series(
                ["x", "y"], dtype=ArrowDtype(pa.dictionary(pa.int32(), pa.string()))
            ),
            "b": [1, 2],
        },
    )
    expected = df.copy()
    result = df.sort_values(by=["a", "b"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("pat", ["abc", "a[a-z]{2}"])
def test_str_count(pat):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.count(pat)
    expected = pd.Series([1, None], dtype=ArrowDtype(pa.int32()))
    tm.assert_series_equal(result, expected)


def test_str_count_flags_unsupported():
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    with pytest.raises(NotImplementedError, match="count not"):
        ser.str.count("abc", flags=1)


@pytest.mark.parametrize(
    "side, str_func", [["left", "rjust"], ["right", "ljust"], ["both", "center"]]
)
def test_str_pad(side, str_func):
    ser = pd.Series(["a", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.pad(width=3, side=side, fillchar="x")
    expected = pd.Series(
        [getattr("a", str_func)(3, "x"), None], dtype=ArrowDtype(pa.string())
    )
    tm.assert_series_equal(result, expected)


def test_str_pad_invalid_side():
    ser = pd.Series(["a", None], dtype=ArrowDtype(pa.string()))
    with pytest.raises(ValueError, match="Invalid side: foo"):
        ser.str.pad(3, "foo", "x")


@pytest.mark.parametrize(
    "pat, case, na, regex, exp",
    [
        ["ab", False, None, False, [True, None]],
        ["Ab", True, None, False, [False, None]],
        ["ab", False, True, False, [True, True]],
        ["a[a-z]{1}", False, None, True, [True, None]],
        ["A[a-z]{1}", True, None, True, [False, None]],
    ],
)
def test_str_contains(pat, case, na, regex, exp):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.contains(pat, case=case, na=na, regex=regex)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


def test_str_contains_flags_unsupported():
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    with pytest.raises(NotImplementedError, match="contains not"):
        ser.str.contains("a", flags=1)


@pytest.mark.parametrize(
    "side, pat, na, exp",
    [
        ["startswith", "ab", None, [True, None, False]],
        ["startswith", "b", False, [False, False, False]],
        ["endswith", "b", True, [False, True, False]],
        ["endswith", "bc", None, [True, None, False]],
        ["startswith", ("a", "e", "g"), None, [True, None, True]],
        ["endswith", ("a", "c", "g"), None, [True, None, True]],
        ["startswith", (), None, [False, None, False]],
        ["endswith", (), None, [False, None, False]],
    ],
)
def test_str_start_ends_with(side, pat, na, exp):
    ser = pd.Series(["abc", None, "efg"], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, side)(pat, na=na)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("side", ("startswith", "endswith"))
def test_str_starts_ends_with_all_nulls_empty_tuple(side):
    ser = pd.Series([None, None], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, side)(())

    # bool datatype preserved for all nulls.
    expected = pd.Series([None, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "arg_name, arg",
    [["pat", re.compile("b")], ["repl", str], ["case", False], ["flags", 1]],
)
def test_str_replace_unsupported(arg_name, arg):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    kwargs = {"pat": "b", "repl": "x", "regex": True}
    kwargs[arg_name] = arg
    with pytest.raises(NotImplementedError, match="replace is not supported"):
        ser.str.replace(**kwargs)


@pytest.mark.parametrize(
    "pat, repl, n, regex, exp",
    [
        ["a", "x", -1, False, ["xbxc", None]],
        ["a", "x", 1, False, ["xbac", None]],
        ["[a-b]", "x", -1, True, ["xxxc", None]],
    ],
)
def test_str_replace(pat, repl, n, regex, exp):
    ser = pd.Series(["abac", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.replace(pat, repl, n=n, regex=regex)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


def test_str_replace_negative_n():
    # GH 56404
    ser = pd.Series(["abc", "aaaaaa"], dtype=ArrowDtype(pa.string()))
    actual = ser.str.replace("a", "", -3, True)
    expected = pd.Series(["bc", ""], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(expected, actual)

    # Same bug for pyarrow-backed StringArray GH#59628
    ser2 = ser.astype(pd.StringDtype(storage="pyarrow"))
    actual2 = ser2.str.replace("a", "", -3, True)
    expected2 = expected.astype(ser2.dtype)
    tm.assert_series_equal(expected2, actual2)

    ser3 = ser.astype(pd.StringDtype(storage="pyarrow", na_value=np.nan))
    actual3 = ser3.str.replace("a", "", -3, True)
    expected3 = expected.astype(ser3.dtype)
    tm.assert_series_equal(expected3, actual3)


def test_str_repeat_unsupported():
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    with pytest.raises(NotImplementedError, match="repeat is not"):
        ser.str.repeat([1, 2])


def test_str_repeat():
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.repeat(2)
    expected = pd.Series(["abcabc", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "pat, case, na, exp",
    [
        ["ab", False, None, [True, None]],
        ["Ab", True, None, [False, None]],
        ["bc", True, None, [False, None]],
        ["ab", False, True, [True, True]],
        ["a[a-z]{1}", False, None, [True, None]],
        ["A[a-z]{1}", True, None, [False, None]],
    ],
)
def test_str_match(pat, case, na, exp):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.match(pat, case=case, na=na)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "pat, case, na, exp",
    # Note: keep cases in sync with
    # pandas/tests/strings/test_find_replace.py::test_str_fullmatch_extra_cases
    [
        ["abc", False, None, [True, False, False, None]],
        ["Abc", True, None, [False, False, False, None]],
        ["bc", True, None, [False, False, False, None]],
        ["ab", False, None, [False, False, False, None]],
        ["a[a-z]{2}", False, None, [True, False, False, None]],
        ["A[a-z]{1}", True, None, [False, False, False, None]],
        # GH Issue: #56652
        ["abc$", False, None, [True, False, False, None]],
        ["abc\\$", False, None, [False, True, False, None]],
        ["Abc$", True, None, [False, False, False, None]],
        ["Abc\\$", True, None, [False, False, False, None]],
        # https://github.com/pandas-dev/pandas/issues/61072
        ["(abc)|(abx)", True, None, [True, False, False, None]],
        ["((abc)|(abx))", True, None, [True, False, False, None]],
    ],
)
def test_str_fullmatch(pat, case, na, exp):
    ser = pd.Series(["abc", "abc$", "$abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.fullmatch(pat, case=case, na=na)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "sub, start, end, exp, exp_typ",
    [["ab", 0, None, [0, None], pa.int32()], ["bc", 1, 3, [1, None], pa.int64()]],
)
def test_str_find(sub, start, end, exp, exp_typ):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.find(sub, start=start, end=end)
    expected = pd.Series(exp, dtype=ArrowDtype(exp_typ))
    tm.assert_series_equal(result, expected)


def test_str_find_negative_start():
    # GH 56411
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.find(sub="b", start=-1000, end=3)
    expected = pd.Series([1, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)


def test_str_find_no_end():
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.find("ab", start=1)
    expected = pd.Series([-1, None], dtype="int64[pyarrow]")
    tm.assert_series_equal(result, expected)


def test_str_find_negative_start_negative_end():
    # GH 56791
    ser = pd.Series(["abcdefg", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.find(sub="d", start=-6, end=-3)
    expected = pd.Series([3, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)


def test_str_find_large_start():
    # GH 56791
    ser = pd.Series(["abcdefg", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.find(sub="d", start=16)
    expected = pd.Series([-1, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)


@pytest.mark.skipif(
    pa_version_under13p0, reason="https://github.com/apache/arrow/issues/36311"
)
@pytest.mark.parametrize("start", [-15, -3, 0, 1, 15, None])
@pytest.mark.parametrize("end", [-15, -1, 0, 3, 15, None])
@pytest.mark.parametrize("sub", ["", "az", "abce", "a", "caa"])
def test_str_find_e2e(start, end, sub):
    s = pd.Series(
        ["abcaadef", "abc", "abcdeddefgj8292", "ab", "a", ""],
        dtype=ArrowDtype(pa.string()),
    )
    object_series = s.astype(pd.StringDtype(storage="python"))
    result = s.str.find(sub, start, end)
    expected = object_series.str.find(sub, start, end).astype(result.dtype)
    tm.assert_series_equal(result, expected)

    arrow_str_series = s.astype(pd.StringDtype(storage="pyarrow"))
    result2 = arrow_str_series.str.find(sub, start, end).astype(result.dtype)
    tm.assert_series_equal(result2, expected)


def test_str_find_negative_start_negative_end_no_match():
    # GH 56791
    ser = pd.Series(["abcdefg", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.find(sub="d", start=-3, end=-6)
    expected = pd.Series([-1, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "i, exp",
    [
        [1, ["b", "e", None]],
        [-1, ["c", "e", None]],
        [2, ["c", None, None]],
        [-3, ["a", None, None]],
        [4, [None, None, None]],
    ],
)
def test_str_get(i, exp):
    ser = pd.Series(["abc", "de", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.get(i)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.xfail(
    reason="TODO: StringMethods._validate should support Arrow list types",
    raises=AttributeError,
)
def test_str_join():
    ser = pd.Series(ArrowExtensionArray(pa.array([list("abc"), list("123"), None])))
    result = ser.str.join("=")
    expected = pd.Series(["a=b=c", "1=2=3", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


def test_str_join_string_type():
    ser = pd.Series(ArrowExtensionArray(pa.array(["abc", "123", None])))
    result = ser.str.join("=")
    expected = pd.Series(["a=b=c", "1=2=3", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "start, stop, step, exp",
    [
        [None, 2, None, ["ab", None]],
        [None, 2, 1, ["ab", None]],
        [1, 3, 1, ["bc", None]],
        (None, None, -1, ["dcba", None]),
    ],
)
def test_str_slice(start, stop, step, exp):
    ser = pd.Series(["abcd", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.slice(start, stop, step)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "start, stop, repl, exp",
    [
        [1, 2, "x", ["axcd", None]],
        [None, 2, "x", ["xcd", None]],
        [None, 2, None, ["cd", None]],
    ],
)
def test_str_slice_replace(start, stop, repl, exp):
    ser = pd.Series(["abcd", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.slice_replace(start, stop, repl)
    expected = pd.Series(exp, dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "value, method, exp",
    [
        ["a1c", "isalnum", True],
        ["!|,", "isalnum", False],
        ["aaa", "isalpha", True],
        ["!!!", "isalpha", False],
        ["٠", "isdecimal", True],  # noqa: RUF001
        ["~!", "isdecimal", False],
        ["2", "isdigit", True],
        ["~", "isdigit", False],
        ["aaa", "islower", True],
        ["aaA", "islower", False],
        ["123", "isnumeric", True],
        ["11I", "isnumeric", False],
        [" ", "isspace", True],
        ["", "isspace", False],
        ["The That", "istitle", True],
        ["the That", "istitle", False],
        ["AAA", "isupper", True],
        ["AAc", "isupper", False],
    ],
)
def test_str_is_functions(value, method, exp):
    ser = pd.Series([value, None], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, method)()
    expected = pd.Series([exp, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method, exp",
    [
        ["capitalize", "Abc def"],
        ["title", "Abc Def"],
        ["swapcase", "AbC Def"],
        ["lower", "abc def"],
        ["upper", "ABC DEF"],
        ["casefold", "abc def"],
    ],
)
def test_str_transform_functions(method, exp):
    ser = pd.Series(["aBc dEF", None], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, method)()
    expected = pd.Series([exp, None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


def test_str_len():
    ser = pd.Series(["abcd", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.len()
    expected = pd.Series([4, None], dtype=ArrowDtype(pa.int32()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method, to_strip, val",
    [
        ["strip", None, " abc "],
        ["strip", "x", "xabcx"],
        ["lstrip", None, " abc"],
        ["lstrip", "x", "xabc"],
        ["rstrip", None, "abc "],
        ["rstrip", "x", "abcx"],
    ],
)
def test_str_strip(method, to_strip, val):
    ser = pd.Series([val, None], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, method)(to_strip=to_strip)
    expected = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("val", ["abc123", "abc"])
def test_str_removesuffix(val):
    ser = pd.Series([val, None], dtype=ArrowDtype(pa.string()))
    result = ser.str.removesuffix("123")
    expected = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("val", ["123abc", "abc"])
def test_str_removeprefix(val):
    ser = pd.Series([val, None], dtype=ArrowDtype(pa.string()))
    result = ser.str.removeprefix("123")
    expected = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("errors", ["ignore", "strict"])
@pytest.mark.parametrize(
    "encoding, exp",
    [
        ["utf8", b"abc"],
        ["utf32", b"\xff\xfe\x00\x00a\x00\x00\x00b\x00\x00\x00c\x00\x00\x00"],
    ],
)
def test_str_encode(errors, encoding, exp):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.encode(encoding, errors)
    expected = pd.Series([exp, None], dtype=ArrowDtype(pa.binary()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("flags", [0, 2])
def test_str_findall(flags):
    ser = pd.Series(["abc", "efg", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.findall("b", flags=flags)
    expected = pd.Series([["b"], [], None], dtype=ArrowDtype(pa.list_(pa.string())))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["index", "rindex"])
@pytest.mark.parametrize(
    "start, end",
    [
        [0, None],
        [1, 4],
    ],
)
def test_str_r_index(method, start, end):
    ser = pd.Series(["abcba", None], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, method)("c", start, end)
    expected = pd.Series([2, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)

    with pytest.raises(ValueError, match="substring not found"):
        getattr(ser.str, method)("foo", start, end)


@pytest.mark.parametrize("form", ["NFC", "NFKC"])
def test_str_normalize(form):
    ser = pd.Series(["abc", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.normalize(form)
    expected = ser.copy()
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "start, end",
    [
        [0, None],
        [1, 4],
    ],
)
def test_str_rfind(start, end):
    ser = pd.Series(["abcba", "foo", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.rfind("c", start, end)
    expected = pd.Series([2, -1, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)


def test_str_translate():
    ser = pd.Series(["abcba", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.translate({97: "b"})
    expected = pd.Series(["bbcbb", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


def test_str_wrap():
    ser = pd.Series(["abcba", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.wrap(3)
    expected = pd.Series(["abc\nba", None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


def test_get_dummies():
    ser = pd.Series(["a|b", None, "a|c"], dtype=ArrowDtype(pa.string()))
    result = ser.str.get_dummies()
    expected = pd.DataFrame(
        [[True, True, False], [False, False, False], [True, False, True]],
        dtype=ArrowDtype(pa.bool_()),
        columns=["a", "b", "c"],
    )
    tm.assert_frame_equal(result, expected)


def test_str_partition():
    ser = pd.Series(["abcba", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.partition("b")
    expected = pd.DataFrame(
        [["a", "b", "cba"], [None, None, None]], dtype=ArrowDtype(pa.string())
    )
    tm.assert_frame_equal(result, expected)

    result = ser.str.partition("b", expand=False)
    expected = pd.Series(ArrowExtensionArray(pa.array([["a", "b", "cba"], None])))
    tm.assert_series_equal(result, expected)

    result = ser.str.rpartition("b")
    expected = pd.DataFrame(
        [["abc", "b", "a"], [None, None, None]], dtype=ArrowDtype(pa.string())
    )
    tm.assert_frame_equal(result, expected)

    result = ser.str.rpartition("b", expand=False)
    expected = pd.Series(ArrowExtensionArray(pa.array([["abc", "b", "a"], None])))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["rsplit", "split"])
def test_str_split_pat_none(method):
    # GH 56271
    ser = pd.Series(["a1 cbc\nb", None], dtype=ArrowDtype(pa.string()))
    result = getattr(ser.str, method)()
    expected = pd.Series(ArrowExtensionArray(pa.array([["a1", "cbc", "b"], None])))
    tm.assert_series_equal(result, expected)


def test_str_split():
    # GH 52401
    ser = pd.Series(["a1cbcb", "a2cbcb", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.split("c")
    expected = pd.Series(
        ArrowExtensionArray(pa.array([["a1", "b", "b"], ["a2", "b", "b"], None]))
    )
    tm.assert_series_equal(result, expected)

    result = ser.str.split("c", n=1)
    expected = pd.Series(
        ArrowExtensionArray(pa.array([["a1", "bcb"], ["a2", "bcb"], None]))
    )
    tm.assert_series_equal(result, expected)

    result = ser.str.split("[1-2]", regex=True)
    expected = pd.Series(
        ArrowExtensionArray(pa.array([["a", "cbcb"], ["a", "cbcb"], None]))
    )
    tm.assert_series_equal(result, expected)

    result = ser.str.split("[1-2]", regex=True, expand=True)
    expected = pd.DataFrame(
        {
            0: ArrowExtensionArray(pa.array(["a", "a", None])),
            1: ArrowExtensionArray(pa.array(["cbcb", "cbcb", None])),
        }
    )
    tm.assert_frame_equal(result, expected)

    result = ser.str.split("1", expand=True)
    expected = pd.DataFrame(
        {
            0: ArrowExtensionArray(pa.array(["a", "a2cbcb", None])),
            1: ArrowExtensionArray(pa.array(["cbcb", None, None])),
        }
    )
    tm.assert_frame_equal(result, expected)


def test_str_rsplit():
    # GH 52401
    ser = pd.Series(["a1cbcb", "a2cbcb", None], dtype=ArrowDtype(pa.string()))
    result = ser.str.rsplit("c")
    expected = pd.Series(
        ArrowExtensionArray(pa.array([["a1", "b", "b"], ["a2", "b", "b"], None]))
    )
    tm.assert_series_equal(result, expected)

    result = ser.str.rsplit("c", n=1)
    expected = pd.Series(
        ArrowExtensionArray(pa.array([["a1cb", "b"], ["a2cb", "b"], None]))
    )
    tm.assert_series_equal(result, expected)

    result = ser.str.rsplit("c", n=1, expand=True)
    expected = pd.DataFrame(
        {
            0: ArrowExtensionArray(pa.array(["a1cb", "a2cb", None])),
            1: ArrowExtensionArray(pa.array(["b", "b", None])),
        }
    )
    tm.assert_frame_equal(result, expected)

    result = ser.str.rsplit("1", expand=True)
    expected = pd.DataFrame(
        {
            0: ArrowExtensionArray(pa.array(["a", "a2cbcb", None])),
            1: ArrowExtensionArray(pa.array(["cbcb", None, None])),
        }
    )
    tm.assert_frame_equal(result, expected)


def test_str_extract_non_symbolic():
    ser = pd.Series(["a1", "b2", "c3"], dtype=ArrowDtype(pa.string()))
    with pytest.raises(ValueError, match="pat=.* must contain a symbolic group name."):
        ser.str.extract(r"[ab](\d)")


@pytest.mark.parametrize("expand", [True, False])
def test_str_extract(expand):
    ser = pd.Series(["a1", "b2", "c3"], dtype=ArrowDtype(pa.string()))
    result = ser.str.extract(r"(?P<letter>[ab])(?P<digit>\d)", expand=expand)
    expected = pd.DataFrame(
        {
            "letter": ArrowExtensionArray(pa.array(["a", "b", None])),
            "digit": ArrowExtensionArray(pa.array(["1", "2", None])),
        }
    )
    tm.assert_frame_equal(result, expected)


def test_str_extract_expand():
    ser = pd.Series(["a1", "b2", "c3"], dtype=ArrowDtype(pa.string()))
    result = ser.str.extract(r"[ab](?P<digit>\d)", expand=True)
    expected = pd.DataFrame(
        {
            "digit": ArrowExtensionArray(pa.array(["1", "2", None])),
        }
    )
    tm.assert_frame_equal(result, expected)

    result = ser.str.extract(r"[ab](?P<digit>\d)", expand=False)
    expected = pd.Series(ArrowExtensionArray(pa.array(["1", "2", None])), name="digit")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
def test_duration_from_strings_with_nat(unit):
    # GH51175
    strings = ["1000", "NaT"]
    pa_type = pa.duration(unit)
    result = ArrowExtensionArray._from_sequence_of_strings(strings, dtype=pa_type)
    expected = ArrowExtensionArray(pa.array([1000, None], type=pa_type))
    tm.assert_extension_array_equal(result, expected)


def test_unsupported_dt(data):
    pa_dtype = data.dtype.pyarrow_dtype
    if not pa.types.is_temporal(pa_dtype):
        with pytest.raises(
            AttributeError, match="Can only use .dt accessor with datetimelike values"
        ):
            pd.Series(data).dt


@pytest.mark.parametrize(
    "prop, expected",
    [
        ["year", 2023],
        ["day", 2],
        ["day_of_week", 0],
        ["dayofweek", 0],
        ["weekday", 0],
        ["day_of_year", 2],
        ["dayofyear", 2],
        ["hour", 3],
        ["minute", 4],
        ["is_leap_year", False],
        ["microsecond", 5],
        ["month", 1],
        ["nanosecond", 6],
        ["quarter", 1],
        ["second", 7],
        ["date", date(2023, 1, 2)],
        ["time", time(3, 4, 7, 5)],
    ],
)
def test_dt_properties(prop, expected):
    ser = pd.Series(
        [
            pd.Timestamp(
                year=2023,
                month=1,
                day=2,
                hour=3,
                minute=4,
                second=7,
                microsecond=5,
                nanosecond=6,
            ),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    result = getattr(ser.dt, prop)
    exp_type = None
    if isinstance(expected, date):
        exp_type = pa.date32()
    elif isinstance(expected, time):
        exp_type = pa.time64("ns")
    expected = pd.Series(ArrowExtensionArray(pa.array([expected, None], type=exp_type)))
    tm.assert_series_equal(result, expected)


def test_dt_is_month_start_end():
    ser = pd.Series(
        [
            datetime(year=2023, month=12, day=2, hour=3),
            datetime(year=2023, month=1, day=1, hour=3),
            datetime(year=2023, month=3, day=31, hour=3),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("us")),
    )
    result = ser.dt.is_month_start
    expected = pd.Series([False, True, False, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)

    result = ser.dt.is_month_end
    expected = pd.Series([False, False, True, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


def test_dt_is_year_start_end():
    ser = pd.Series(
        [
            datetime(year=2023, month=12, day=31, hour=3),
            datetime(year=2023, month=1, day=1, hour=3),
            datetime(year=2023, month=3, day=31, hour=3),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("us")),
    )
    result = ser.dt.is_year_start
    expected = pd.Series([False, True, False, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)

    result = ser.dt.is_year_end
    expected = pd.Series([True, False, False, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


def test_dt_is_quarter_start_end():
    ser = pd.Series(
        [
            datetime(year=2023, month=11, day=30, hour=3),
            datetime(year=2023, month=1, day=1, hour=3),
            datetime(year=2023, month=3, day=31, hour=3),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("us")),
    )
    result = ser.dt.is_quarter_start
    expected = pd.Series([False, True, False, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)

    result = ser.dt.is_quarter_end
    expected = pd.Series([False, False, True, None], dtype=ArrowDtype(pa.bool_()))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["days_in_month", "daysinmonth"])
def test_dt_days_in_month(method):
    ser = pd.Series(
        [
            datetime(year=2023, month=3, day=30, hour=3),
            datetime(year=2023, month=4, day=1, hour=3),
            datetime(year=2023, month=2, day=3, hour=3),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("us")),
    )
    result = getattr(ser.dt, method)
    expected = pd.Series([31, 30, 28, None], dtype=ArrowDtype(pa.int64()))
    tm.assert_series_equal(result, expected)


def test_dt_normalize():
    ser = pd.Series(
        [
            datetime(year=2023, month=3, day=30),
            datetime(year=2023, month=4, day=1, hour=3),
            datetime(year=2023, month=2, day=3, hour=23, minute=59, second=59),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("us")),
    )
    result = ser.dt.normalize()
    expected = pd.Series(
        [
            datetime(year=2023, month=3, day=30),
            datetime(year=2023, month=4, day=1),
            datetime(year=2023, month=2, day=3),
            None,
        ],
        dtype=ArrowDtype(pa.timestamp("us")),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("unit", ["us", "ns"])
def test_dt_time_preserve_unit(unit):
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp(unit)),
    )
    assert ser.dt.unit == unit

    result = ser.dt.time
    expected = pd.Series(
        ArrowExtensionArray(pa.array([time(3, 0), None], type=pa.time64(unit)))
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("tz", [None, "UTC", "US/Pacific"])
def test_dt_tz(tz):
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns", tz=tz)),
    )
    result = ser.dt.tz
    assert result == timezones.maybe_get_tz(tz)


def test_dt_isocalendar():
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    result = ser.dt.isocalendar()
    expected = pd.DataFrame(
        [[2023, 1, 1], [0, 0, 0]],
        columns=["year", "week", "day"],
        dtype="int64[pyarrow]",
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "method, exp", [["day_name", "Sunday"], ["month_name", "January"]]
)
def test_dt_day_month_name(method, exp, request):
    # GH 52388
    _require_timezone_database(request)

    ser = pd.Series([datetime(2023, 1, 1), None], dtype=ArrowDtype(pa.timestamp("ms")))
    result = getattr(ser.dt, method)()
    expected = pd.Series([exp, None], dtype=ArrowDtype(pa.string()))
    tm.assert_series_equal(result, expected)


def test_dt_strftime(request):
    _require_timezone_database(request)

    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    result = ser.dt.strftime("%Y-%m-%dT%H:%M:%S")
    expected = pd.Series(
        ["2023-01-02T03:00:00.000000000", None], dtype=ArrowDtype(pa.string())
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["ceil", "floor", "round"])
def test_dt_roundlike_tz_options_not_supported(method):
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    with pytest.raises(NotImplementedError, match="ambiguous is not supported."):
        getattr(ser.dt, method)("1h", ambiguous="NaT")

    with pytest.raises(NotImplementedError, match="nonexistent is not supported."):
        getattr(ser.dt, method)("1h", nonexistent="NaT")


@pytest.mark.parametrize("method", ["ceil", "floor", "round"])
def test_dt_roundlike_unsupported_freq(method):
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    with pytest.raises(ValueError, match="freq='1B' is not supported"):
        getattr(ser.dt, method)("1B")

    with pytest.raises(ValueError, match="Must specify a valid frequency: None"):
        getattr(ser.dt, method)(None)


@pytest.mark.parametrize("freq", ["D", "h", "min", "s", "ms", "us", "ns"])
@pytest.mark.parametrize("method", ["ceil", "floor", "round"])
def test_dt_ceil_year_floor(freq, method):
    ser = pd.Series(
        [datetime(year=2023, month=1, day=1), None],
    )
    pa_dtype = ArrowDtype(pa.timestamp("ns"))
    expected = getattr(ser.dt, method)(f"1{freq}").astype(pa_dtype)
    result = getattr(ser.astype(pa_dtype).dt, method)(f"1{freq}")
    tm.assert_series_equal(result, expected)


def test_dt_to_pydatetime():
    # GH 51859
    data = [datetime(2022, 1, 1), datetime(2023, 1, 1)]
    ser = pd.Series(data, dtype=ArrowDtype(pa.timestamp("ns")))

    msg = "The behavior of ArrowTemporalProperties.to_pydatetime is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = ser.dt.to_pydatetime()
    expected = np.array(data, dtype=object)
    tm.assert_numpy_array_equal(result, expected)
    assert all(type(res) is datetime for res in result)

    msg = "The behavior of DatetimeProperties.to_pydatetime is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        expected = ser.astype("datetime64[ns]").dt.to_pydatetime()
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("date_type", [32, 64])
def test_dt_to_pydatetime_date_error(date_type):
    # GH 52812
    ser = pd.Series(
        [date(2022, 12, 31)],
        dtype=ArrowDtype(getattr(pa, f"date{date_type}")()),
    )
    msg = "The behavior of ArrowTemporalProperties.to_pydatetime is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        with pytest.raises(ValueError, match="to_pydatetime cannot be called with"):
            ser.dt.to_pydatetime()


def test_dt_tz_localize_unsupported_tz_options():
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    with pytest.raises(NotImplementedError, match="ambiguous='NaT' is not supported"):
        ser.dt.tz_localize("UTC", ambiguous="NaT")

    with pytest.raises(NotImplementedError, match="nonexistent='NaT' is not supported"):
        ser.dt.tz_localize("UTC", nonexistent="NaT")


def test_dt_tz_localize_none():
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns", tz="US/Pacific")),
    )
    result = ser.dt.tz_localize(None)
    expected = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("unit", ["us", "ns"])
def test_dt_tz_localize(unit, request):
    _require_timezone_database(request)

    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp(unit)),
    )
    result = ser.dt.tz_localize("US/Pacific")
    exp_data = pa.array(
        [datetime(year=2023, month=1, day=2, hour=3), None], type=pa.timestamp(unit)
    )
    exp_data = pa.compute.assume_timezone(exp_data, "US/Pacific")
    expected = pd.Series(ArrowExtensionArray(exp_data))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "nonexistent, exp_date",
    [
        ["shift_forward", datetime(year=2023, month=3, day=12, hour=3)],
        ["shift_backward", pd.Timestamp("2023-03-12 01:59:59.999999999")],
    ],
)
def test_dt_tz_localize_nonexistent(nonexistent, exp_date, request):
    _require_timezone_database(request)

    ser = pd.Series(
        [datetime(year=2023, month=3, day=12, hour=2, minute=30), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    result = ser.dt.tz_localize("US/Pacific", nonexistent=nonexistent)
    exp_data = pa.array([exp_date, None], type=pa.timestamp("ns"))
    exp_data = pa.compute.assume_timezone(exp_data, "US/Pacific")
    expected = pd.Series(ArrowExtensionArray(exp_data))
    tm.assert_series_equal(result, expected)


def test_dt_tz_convert_not_tz_raises():
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    with pytest.raises(TypeError, match="Cannot convert tz-naive timestamps"):
        ser.dt.tz_convert("UTC")


def test_dt_tz_convert_none():
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns", "US/Pacific")),
    )
    result = ser.dt.tz_convert(None)
    expected = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp("ns")),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("unit", ["us", "ns"])
def test_dt_tz_convert(unit):
    ser = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp(unit, "US/Pacific")),
    )
    result = ser.dt.tz_convert("US/Eastern")
    expected = pd.Series(
        [datetime(year=2023, month=1, day=2, hour=3), None],
        dtype=ArrowDtype(pa.timestamp(unit, "US/Eastern")),
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dtype", ["timestamp[ms][pyarrow]", "duration[ms][pyarrow]"])
def test_as_unit(dtype):
    # GH 52284
    ser = pd.Series([1000, None], dtype=dtype)
    result = ser.dt.as_unit("ns")
    expected = ser.astype(dtype.replace("ms", "ns"))
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "prop, expected",
    [
        ["days", 1],
        ["seconds", 2],
        ["microseconds", 3],
        ["nanoseconds", 4],
    ],
)
def test_dt_timedelta_properties(prop, expected):
    # GH 52284
    ser = pd.Series(
        [
            pd.Timedelta(
                days=1,
                seconds=2,
                microseconds=3,
                nanoseconds=4,
            ),
            None,
        ],
        dtype=ArrowDtype(pa.duration("ns")),
    )
    result = getattr(ser.dt, prop)
    expected = pd.Series(
        ArrowExtensionArray(pa.array([expected, None], type=pa.int32()))
    )
    tm.assert_series_equal(result, expected)


def test_dt_timedelta_total_seconds():
    # GH 52284
    ser = pd.Series(
        [
            pd.Timedelta(
                days=1,
                seconds=2,
                microseconds=3,
                nanoseconds=4,
            ),
            None,
        ],
        dtype=ArrowDtype(pa.duration("ns")),
    )
    result = ser.dt.total_seconds()
    expected = pd.Series(
        ArrowExtensionArray(pa.array([86402.000003, None], type=pa.float64()))
    )
    tm.assert_series_equal(result, expected)


def test_dt_to_pytimedelta():
    # GH 52284
    data = [timedelta(1, 2, 3), timedelta(1, 2, 4)]
    ser = pd.Series(data, dtype=ArrowDtype(pa.duration("ns")))

    result = ser.dt.to_pytimedelta()
    expected = np.array(data, dtype=object)
    tm.assert_numpy_array_equal(result, expected)
    assert all(type(res) is timedelta for res in result)

    expected = ser.astype("timedelta64[ns]").dt.to_pytimedelta()
    tm.assert_numpy_array_equal(result, expected)


def test_dt_components():
    # GH 52284
    ser = pd.Series(
        [
            pd.Timedelta(
                days=1,
                seconds=2,
                microseconds=3,
                nanoseconds=4,
            ),
            None,
        ],
        dtype=ArrowDtype(pa.duration("ns")),
    )
    result = ser.dt.components
    expected = pd.DataFrame(
        [[1, 0, 0, 2, 0, 3, 4], [None, None, None, None, None, None, None]],
        columns=[
            "days",
            "hours",
            "minutes",
            "seconds",
            "milliseconds",
            "microseconds",
            "nanoseconds",
        ],
        dtype="int32[pyarrow]",
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("skipna", [True, False])
def test_boolean_reduce_series_all_null(all_boolean_reductions, skipna):
    # GH51624
    ser = pd.Series([None], dtype="float64[pyarrow]")
    result = getattr(ser, all_boolean_reductions)(skipna=skipna)
    if skipna:
        expected = all_boolean_reductions == "all"
    else:
        expected = pd.NA
    assert result is expected


def test_from_sequence_of_strings_boolean():
    true_strings = ["true", "TRUE", "True", "1", "1.0"]
    false_strings = ["false", "FALSE", "False", "0", "0.0"]
    nulls = [None]
    strings = true_strings + false_strings + nulls
    bools = (
        [True] * len(true_strings) + [False] * len(false_strings) + [None] * len(nulls)
    )

    result = ArrowExtensionArray._from_sequence_of_strings(strings, dtype=pa.bool_())
    expected = pd.array(bools, dtype="boolean[pyarrow]")
    tm.assert_extension_array_equal(result, expected)

    strings = ["True", "foo"]
    with pytest.raises(pa.ArrowInvalid, match="Failed to parse"):
        ArrowExtensionArray._from_sequence_of_strings(strings, dtype=pa.bool_())


def test_concat_empty_arrow_backed_series(dtype):
    # GH#51734
    ser = pd.Series([], dtype=dtype)
    expected = ser.copy()
    result = pd.concat([ser[np.array([], dtype=np.bool_)]])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dtype", ["string", "string[pyarrow]"])
def test_series_from_string_array(dtype):
    arr = pa.array("the quick brown fox".split())
    ser = pd.Series(arr, dtype=dtype)
    expected = pd.Series(ArrowExtensionArray(arr), dtype=dtype)
    tm.assert_series_equal(ser, expected)


# _data was renamed to _pa_data
class OldArrowExtensionArray(ArrowExtensionArray):
    def __getstate__(self):
        state = super().__getstate__()
        state["_data"] = state.pop("_pa_array")
        return state


def test_pickle_old_arrowextensionarray():
    data = pa.array([1])
    expected = OldArrowExtensionArray(data)
    result = pickle.loads(pickle.dumps(expected))
    tm.assert_extension_array_equal(result, expected)
    assert result._pa_array == pa.chunked_array(data)
    assert not hasattr(result, "_data")


def test_setitem_boolean_replace_with_mask_segfault():
    # GH#52059
    N = 145_000
    arr = ArrowExtensionArray(pa.chunked_array([np.ones((N,), dtype=np.bool_)]))
    expected = arr.copy()
    arr[np.zeros((N,), dtype=np.bool_)] = False
    assert arr._pa_array == expected._pa_array


@pytest.mark.parametrize(
    "data, arrow_dtype",
    [
        ([b"a", b"b"], pa.large_binary()),
        (["a", "b"], pa.large_string()),
    ],
)
def test_conversion_large_dtypes_from_numpy_array(data, arrow_dtype):
    dtype = ArrowDtype(arrow_dtype)
    result = pd.array(np.array(data), dtype=dtype)
    expected = pd.array(data, dtype=dtype)
    tm.assert_extension_array_equal(result, expected)


def test_concat_null_array():
    df = pd.DataFrame({"a": [None, None]}, dtype=ArrowDtype(pa.null()))
    df2 = pd.DataFrame({"a": [0, 1]}, dtype="int64[pyarrow]")

    result = pd.concat([df, df2], ignore_index=True)
    expected = pd.DataFrame({"a": [None, None, 0, 1]}, dtype="int64[pyarrow]")
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.ALL_INT_PYARROW_DTYPES + tm.FLOAT_PYARROW_DTYPES)
def test_describe_numeric_data(pa_type):
    # GH 52470
    data = pd.Series([1, 2, 3], dtype=ArrowDtype(pa_type))
    result = data.describe()
    expected = pd.Series(
        [3, 2, 1, 1, 1.5, 2.0, 2.5, 3],
        dtype=ArrowDtype(pa.float64()),
        index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.TIMEDELTA_PYARROW_DTYPES)
def test_describe_timedelta_data(pa_type):
    # GH53001
    data = pd.Series(range(1, 10), dtype=ArrowDtype(pa_type))
    result = data.describe()
    expected = pd.Series(
        [9] + pd.to_timedelta([5, 2, 1, 3, 5, 7, 9], unit=pa_type.unit).tolist(),
        dtype=object,
        index=["count", "mean", "std", "min", "25%", "50%", "75%", "max"],
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.DATETIME_PYARROW_DTYPES)
def test_describe_datetime_data(pa_type):
    # GH53001
    data = pd.Series(range(1, 10), dtype=ArrowDtype(pa_type))
    result = data.describe()
    expected = pd.Series(
        [9]
        + [
            pd.Timestamp(v, tz=pa_type.tz, unit=pa_type.unit)
            for v in [5, 1, 3, 5, 7, 9]
        ],
        dtype=object,
        index=["count", "mean", "min", "25%", "50%", "75%", "max"],
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_quantile_temporal(pa_type):
    # GH52678
    data = [1, 2, 3]
    ser = pd.Series(data, dtype=ArrowDtype(pa_type))
    result = ser.quantile(0.1)
    expected = ser[0]
    assert result == expected


def test_date32_repr():
    # GH48238
    arrow_dt = pa.array([date.fromisoformat("2020-01-01")], type=pa.date32())
    ser = pd.Series(arrow_dt, dtype=ArrowDtype(arrow_dt.type))
    assert repr(ser) == "0    2020-01-01\ndtype: date32[day][pyarrow]"


def test_duration_overflow_from_ndarray_containing_nat():
    # GH52843
    data_ts = pd.to_datetime([1, None])
    data_td = pd.to_timedelta([1, None])
    ser_ts = pd.Series(data_ts, dtype=ArrowDtype(pa.timestamp("ns")))
    ser_td = pd.Series(data_td, dtype=ArrowDtype(pa.duration("ns")))
    result = ser_ts + ser_td
    expected = pd.Series([2, None], dtype=ArrowDtype(pa.timestamp("ns")))
    tm.assert_series_equal(result, expected)


def test_infer_dtype_pyarrow_dtype(data, request):
    res = lib.infer_dtype(data)
    assert res != "unknown-array"

    if data._hasna and res in ["floating", "datetime64", "timedelta64"]:
        mark = pytest.mark.xfail(
            reason="in infer_dtype pd.NA is not ignored in these cases "
            "even with skipna=True in the list(data) check below"
        )
        request.applymarker(mark)

    assert res == lib.infer_dtype(list(data), skipna=True)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_from_sequence_temporal(pa_type):
    # GH 53171
    val = 3
    unit = pa_type.unit
    if pa.types.is_duration(pa_type):
        seq = [pd.Timedelta(val, unit=unit).as_unit(unit)]
    else:
        seq = [pd.Timestamp(val, unit=unit, tz=pa_type.tz).as_unit(unit)]

    result = ArrowExtensionArray._from_sequence(seq, dtype=pa_type)
    expected = ArrowExtensionArray(pa.array([val], type=pa_type))
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_setitem_temporal(pa_type):
    # GH 53171
    unit = pa_type.unit
    if pa.types.is_duration(pa_type):
        val = pd.Timedelta(1, unit=unit).as_unit(unit)
    else:
        val = pd.Timestamp(1, unit=unit, tz=pa_type.tz).as_unit(unit)

    arr = ArrowExtensionArray(pa.array([1, 2, 3], type=pa_type))

    result = arr.copy()
    result[:] = val
    expected = ArrowExtensionArray(pa.array([1, 1, 1], type=pa_type))
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_arithmetic_temporal(pa_type, request):
    # GH 53171
    arr = ArrowExtensionArray(pa.array([1, 2, 3], type=pa_type))
    unit = pa_type.unit
    result = arr - pd.Timedelta(1, unit=unit).as_unit(unit)
    expected = ArrowExtensionArray(pa.array([0, 1, 2], type=pa_type))
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_comparison_temporal(pa_type):
    # GH 53171
    unit = pa_type.unit
    if pa.types.is_duration(pa_type):
        val = pd.Timedelta(1, unit=unit).as_unit(unit)
    else:
        val = pd.Timestamp(1, unit=unit, tz=pa_type.tz).as_unit(unit)

    arr = ArrowExtensionArray(pa.array([1, 2, 3], type=pa_type))

    result = arr > val
    expected = ArrowExtensionArray(pa.array([False, True, True], type=pa.bool_()))
    tm.assert_extension_array_equal(result, expected)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_getitem_temporal(pa_type):
    # GH 53326
    arr = ArrowExtensionArray(pa.array([1, 2, 3], type=pa_type))
    result = arr[1]
    if pa.types.is_duration(pa_type):
        expected = pd.Timedelta(2, unit=pa_type.unit).as_unit(pa_type.unit)
        assert isinstance(result, pd.Timedelta)
    else:
        expected = pd.Timestamp(2, unit=pa_type.unit, tz=pa_type.tz).as_unit(
            pa_type.unit
        )
        assert isinstance(result, pd.Timestamp)
    assert result.unit == expected.unit
    assert result == expected


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES
)
def test_iter_temporal(pa_type):
    # GH 53326
    arr = ArrowExtensionArray(pa.array([1, None], type=pa_type))
    result = list(arr)
    if pa.types.is_duration(pa_type):
        expected = [
            pd.Timedelta(1, unit=pa_type.unit).as_unit(pa_type.unit),
            pd.NA,
        ]
        assert isinstance(result[0], pd.Timedelta)
    else:
        expected = [
            pd.Timestamp(1, unit=pa_type.unit, tz=pa_type.tz).as_unit(pa_type.unit),
            pd.NA,
        ]
        assert isinstance(result[0], pd.Timestamp)
    assert result[0].unit == expected[0].unit
    assert result == expected


def test_groupby_series_size_returns_pa_int(data):
    # GH 54132
    ser = pd.Series(data[:3], index=["a", "a", "b"])
    result = ser.groupby(level=0).size()
    expected = pd.Series([2, 1], dtype="int64[pyarrow]", index=["a", "b"])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "pa_type", tm.DATETIME_PYARROW_DTYPES + tm.TIMEDELTA_PYARROW_DTYPES, ids=repr
)
@pytest.mark.parametrize("dtype", [None, object])
def test_to_numpy_temporal(pa_type, dtype):
    # GH 53326
    # GH 55997: Return datetime64/timedelta64 types with NaT if possible
    arr = ArrowExtensionArray(pa.array([1, None], type=pa_type))
    result = arr.to_numpy(dtype=dtype)
    if pa.types.is_duration(pa_type):
        value = pd.Timedelta(1, unit=pa_type.unit).as_unit(pa_type.unit)
    else:
        value = pd.Timestamp(1, unit=pa_type.unit, tz=pa_type.tz).as_unit(pa_type.unit)

    if dtype == object or (pa.types.is_timestamp(pa_type) and pa_type.tz is not None):
        if dtype == object:
            na = pd.NA
        else:
            na = pd.NaT
        expected = np.array([value, na], dtype=object)
        assert result[0].unit == value.unit
    else:
        na = pa_type.to_pandas_dtype().type("nat", pa_type.unit)
        value = value.to_numpy()
        expected = np.array([value, na])
        assert np.datetime_data(result[0])[0] == pa_type.unit
    tm.assert_numpy_array_equal(result, expected)


def test_groupby_count_return_arrow_dtype(data_missing):
    df = pd.DataFrame({"A": [1, 1], "B": data_missing, "C": data_missing})
    result = df.groupby("A").count()
    expected = pd.DataFrame(
        [[1, 1]],
        index=pd.Index([1], name="A"),
        columns=["B", "C"],
        dtype="int64[pyarrow]",
    )
    tm.assert_frame_equal(result, expected)


def test_fixed_size_list():
    # GH#55000
    ser = pd.Series(
        [[1, 2], [3, 4]], dtype=ArrowDtype(pa.list_(pa.int64(), list_size=2))
    )
    result = ser.dtype.type
    assert result == list


def test_arrowextensiondtype_dataframe_repr():
    # GH 54062
    df = pd.DataFrame(
        pd.period_range("2012", periods=3),
        columns=["col"],
        dtype=ArrowDtype(ArrowPeriodType("D")),
    )
    result = repr(df)
    # TODO: repr value may not be expected; address how
    # pyarrow.ExtensionType values are displayed
    expected = "     col\n0  15340\n1  15341\n2  15342"
    assert result == expected


def test_pow_missing_operand():
    # GH 55512
    k = pd.Series([2, None], dtype="int64[pyarrow]")
    result = k.pow(None, fill_value=3)
    expected = pd.Series([8, None], dtype="int64[pyarrow]")
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.TIMEDELTA_PYARROW_DTYPES)
def test_duration_fillna_numpy(pa_type):
    # GH 54707
    ser1 = pd.Series([None, 2], dtype=ArrowDtype(pa_type))
    ser2 = pd.Series(np.array([1, 3], dtype=f"m8[{pa_type.unit}]"))
    result = ser1.fillna(ser2)
    expected = pd.Series([1, 2], dtype=ArrowDtype(pa_type))
    tm.assert_series_equal(result, expected)


def test_comparison_not_propagating_arrow_error():
    # GH#54944
    a = pd.Series([1 << 63], dtype="uint64[pyarrow]")
    b = pd.Series([None], dtype="int64[pyarrow]")
    with pytest.raises(pa.lib.ArrowInvalid, match="Integer value"):
        a < b


def test_factorize_chunked_dictionary():
    # GH 54844
    pa_array = pa.chunked_array(
        [pa.array(["a"]).dictionary_encode(), pa.array(["b"]).dictionary_encode()]
    )
    ser = pd.Series(ArrowExtensionArray(pa_array))
    res_indices, res_uniques = ser.factorize()
    exp_indicies = np.array([0, 1], dtype=np.intp)
    exp_uniques = pd.Index(ArrowExtensionArray(pa_array.combine_chunks()))
    tm.assert_numpy_array_equal(res_indices, exp_indicies)
    tm.assert_index_equal(res_uniques, exp_uniques)


def test_dictionary_astype_categorical():
    # GH#56672
    arrs = [
        pa.array(np.array(["a", "x", "c", "a"])).dictionary_encode(),
        pa.array(np.array(["a", "d", "c"])).dictionary_encode(),
    ]
    ser = pd.Series(ArrowExtensionArray(pa.chunked_array(arrs)))
    result = ser.astype("category")
    categories = pd.Index(["a", "x", "c", "d"], dtype=ArrowDtype(pa.string()))
    expected = pd.Series(
        ["a", "x", "c", "a", "a", "d", "c"],
        dtype=pd.CategoricalDtype(categories=categories),
    )
    tm.assert_series_equal(result, expected)


def test_arrow_floordiv():
    # GH 55561
    a = pd.Series([-7], dtype="int64[pyarrow]")
    b = pd.Series([4], dtype="int64[pyarrow]")
    expected = pd.Series([-2], dtype="int64[pyarrow]")
    result = a // b
    tm.assert_series_equal(result, expected)


def test_arrow_floordiv_large_values():
    # GH 56645
    a = pd.Series([1425801600000000000], dtype="int64[pyarrow]")
    expected = pd.Series([1425801600000], dtype="int64[pyarrow]")
    result = a // 1_000_000
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dtype", ["int64[pyarrow]", "uint64[pyarrow]"])
def test_arrow_floordiv_large_integral_result(dtype):
    # GH 56676
    a = pd.Series([18014398509481983], dtype=dtype)
    result = a // 1
    tm.assert_series_equal(result, a)


@pytest.mark.parametrize("pa_type", tm.SIGNED_INT_PYARROW_DTYPES)
def test_arrow_floordiv_larger_divisor(pa_type):
    # GH 56676
    dtype = ArrowDtype(pa_type)
    a = pd.Series([-23], dtype=dtype)
    result = a // 24
    expected = pd.Series([-1], dtype=dtype)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.SIGNED_INT_PYARROW_DTYPES)
def test_arrow_floordiv_integral_invalid(pa_type):
    # GH 56676
    min_value = np.iinfo(pa_type.to_pandas_dtype()).min
    a = pd.Series([min_value], dtype=ArrowDtype(pa_type))
    with pytest.raises(pa.lib.ArrowInvalid, match="overflow|not in range"):
        a // -1
    with pytest.raises(pa.lib.ArrowInvalid, match="divide by zero"):
        a // 0


@pytest.mark.parametrize("dtype", tm.FLOAT_PYARROW_DTYPES_STR_REPR)
def test_arrow_floordiv_floating_0_divisor(dtype):
    # GH 56676
    a = pd.Series([2], dtype=dtype)
    result = a // 0
    expected = pd.Series([float("inf")], dtype=dtype)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dtype", ["float64", "datetime64[ns]", "timedelta64[ns]"])
def test_astype_int_with_null_to_numpy_dtype(dtype):
    # GH 57093
    ser = pd.Series([1, None], dtype="int64[pyarrow]")
    result = ser.astype(dtype)
    expected = pd.Series([1, None], dtype=dtype)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("pa_type", tm.ALL_INT_PYARROW_DTYPES)
def test_arrow_integral_floordiv_large_values(pa_type):
    # GH 56676
    max_value = np.iinfo(pa_type.to_pandas_dtype()).max
    dtype = ArrowDtype(pa_type)
    a = pd.Series([max_value], dtype=dtype)
    b = pd.Series([1], dtype=dtype)
    result = a // b
    tm.assert_series_equal(result, a)


@pytest.mark.parametrize("dtype", ["int64[pyarrow]", "uint64[pyarrow]"])
def test_arrow_true_division_large_divisor(dtype):
    # GH 56706
    a = pd.Series([0], dtype=dtype)
    b = pd.Series([18014398509481983], dtype=dtype)
    expected = pd.Series([0], dtype="float64[pyarrow]")
    result = a / b
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("dtype", ["int64[pyarrow]", "uint64[pyarrow]"])
def test_arrow_floor_division_large_divisor(dtype):
    # GH 56706
    a = pd.Series([0], dtype=dtype)
    b = pd.Series([18014398509481983], dtype=dtype)
    expected = pd.Series([0], dtype=dtype)
    result = a // b
    tm.assert_series_equal(result, expected)


def test_string_to_datetime_parsing_cast():
    # GH 56266
    string_dates = ["2020-01-01 04:30:00", "2020-01-02 00:00:00", "2020-01-03 00:00:00"]
    result = pd.Series(string_dates, dtype="timestamp[ns][pyarrow]")
    expected = pd.Series(
        ArrowExtensionArray(pa.array(pd.to_datetime(string_dates), from_pandas=True))
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.skipif(
    pa_version_under13p0, reason="pairwise_diff_checked not implemented in pyarrow"
)
def test_interpolate_not_numeric(data):
    if not data.dtype._is_numeric:
        ser = pd.Series(data)
        msg = re.escape(f"Cannot interpolate with {ser.dtype} dtype")
        with pytest.raises(TypeError, match=msg):
            pd.Series(data).interpolate()


def test_string_to_time_parsing_cast():
    # GH 56463
    string_times = ["11:41:43.076160"]
    result = pd.Series(string_times, dtype="time64[us][pyarrow]")
    expected = pd.Series(
        ArrowExtensionArray(pa.array([time(11, 41, 43, 76160)], from_pandas=True))
    )
    tm.assert_series_equal(result, expected)


def test_to_numpy_float():
    # GH#56267
    ser = pd.Series([32, 40, None], dtype="float[pyarrow]")
    result = ser.astype("float64")
    expected = pd.Series([32, 40, np.nan], dtype="float64")
    tm.assert_series_equal(result, expected)


def test_to_numpy_timestamp_to_int():
    # GH 55997
    ser = pd.Series(["2020-01-01 04:30:00"], dtype="timestamp[ns][pyarrow]")
    result = ser.to_numpy(dtype=np.int64)
    expected = np.array([1577853000000000000])
    tm.assert_numpy_array_equal(result, expected)


def test_map_numeric_na_action():
    ser = pd.Series([32, 40, None], dtype="int64[pyarrow]")
    result = ser.map(lambda x: 42, na_action="ignore")
    expected = pd.Series([42.0, 42.0, np.nan], dtype="float64")
    tm.assert_series_equal(result, expected)
