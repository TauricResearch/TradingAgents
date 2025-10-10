from typing import final

import pytest

import pandas as pd
import pandas._testing as tm
from pandas.api.types import is_numeric_dtype


class BaseReduceTests:
    """
    Reduction specific tests. Generally these only
    make sense for numeric/boolean operations.
    """

    def _supports_reduction(self, ser: pd.Series, op_name: str) -> bool:
        # Specify if we expect this reduction to succeed.
        return False

    def check_reduce(self, ser: pd.Series, op_name: str, skipna: bool):
        # We perform the same operation on the np.float64 data and check
        #  that the results match. Override if you need to cast to something
        #  other than float64.
        res_op = getattr(ser, op_name)

        try:
            alt = ser.astype("float64")
        except (TypeError, ValueError):
            # e.g. Interval can't cast (TypeError), StringArray can't cast
            #  (ValueError), so let's cast to object and do
            #  the reduction pointwise
            alt = ser.astype(object)

        exp_op = getattr(alt, op_name)
        if op_name == "count":
            result = res_op()
            expected = exp_op()
        else:
            result = res_op(skipna=skipna)
            expected = exp_op(skipna=skipna)
        tm.assert_almost_equal(result, expected)

    def _get_expected_reduction_dtype(self, arr, op_name: str, skipna: bool):
        # Find the expected dtype when the given reduction is done on a DataFrame
        # column with this array.  The default assumes float64-like behavior,
        # i.e. retains the dtype.
        return arr.dtype

    # We anticipate that authors should not need to override check_reduce_frame,
    #  but should be able to do any necessary overriding in
    #  _get_expected_reduction_dtype. If you have a use case where this
    #  does not hold, please let us know at github.com/pandas-dev/pandas/issues.
    @final
    def check_reduce_frame(self, ser: pd.Series, op_name: str, skipna: bool):
        # Check that the 2D reduction done in a DataFrame reduction "looks like"
        # a wrapped version of the 1D reduction done by Series.
        arr = ser.array
        df = pd.DataFrame({"a": arr})

        kwargs = {"ddof": 1} if op_name in ["var", "std"] else {}

        cmp_dtype = self._get_expected_reduction_dtype(arr, op_name, skipna)

        # The DataFrame method just calls arr._reduce with keepdims=True,
        #  so this first check is perfunctory.
        result1 = arr._reduce(op_name, skipna=skipna, keepdims=True, **kwargs)
        result2 = getattr(df, op_name)(skipna=skipna, **kwargs).array
        tm.assert_extension_array_equal(result1, result2)

        # Check that the 2D reduction looks like a wrapped version of the
        #  1D reduction
        if not skipna and ser.isna().any():
            expected = pd.array([pd.NA], dtype=cmp_dtype)
        else:
            exp_value = getattr(ser.dropna(), op_name)()
            expected = pd.array([exp_value], dtype=cmp_dtype)

        tm.assert_extension_array_equal(result1, expected)

    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_series_boolean(self, data, all_boolean_reductions, skipna):
        op_name = all_boolean_reductions
        ser = pd.Series(data)

        if not self._supports_reduction(ser, op_name):
            # TODO: the message being checked here isn't actually checking anything
            msg = (
                "[Cc]annot perform|Categorical is not ordered for operation|"
                "does not support reduction|"
            )

            with pytest.raises(TypeError, match=msg):
                getattr(ser, op_name)(skipna=skipna)

        else:
            self.check_reduce(ser, op_name, skipna)

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_series_numeric(self, data, all_numeric_reductions, skipna):
        op_name = all_numeric_reductions
        ser = pd.Series(data)

        if not self._supports_reduction(ser, op_name):
            # TODO: the message being checked here isn't actually checking anything
            msg = (
                "[Cc]annot perform|Categorical is not ordered for operation|"
                "does not support reduction|"
            )

            with pytest.raises(TypeError, match=msg):
                getattr(ser, op_name)(skipna=skipna)

        else:
            # min/max with empty produce numpy warnings
            self.check_reduce(ser, op_name, skipna)

    @pytest.mark.parametrize("skipna", [True, False])
    def test_reduce_frame(self, data, all_numeric_reductions, skipna):
        op_name = all_numeric_reductions
        ser = pd.Series(data)
        if not is_numeric_dtype(ser.dtype):
            pytest.skip(f"{ser.dtype} is not numeric dtype")

        if op_name in ["count", "kurt", "sem"]:
            pytest.skip(f"{op_name} not an array method")

        if not self._supports_reduction(ser, op_name):
            pytest.skip(f"Reduction {op_name} not supported for this dtype")

        self.check_reduce_frame(ser, op_name, skipna)


# TODO(3.0): remove BaseNoReduceTests, BaseNumericReduceTests,
#  BaseBooleanReduceTests
class BaseNoReduceTests(BaseReduceTests):
    """we don't define any reductions"""


class BaseNumericReduceTests(BaseReduceTests):
    # For backward compatibility only, this only runs the numeric reductions
    def _supports_reduction(self, ser: pd.Series, op_name: str) -> bool:
        if op_name in ["any", "all"]:
            pytest.skip("These are tested in BaseBooleanReduceTests")
        return True


class BaseBooleanReduceTests(BaseReduceTests):
    # For backward compatibility only, this only runs the numeric reductions
    def _supports_reduction(self, ser: pd.Series, op_name: str) -> bool:
        if op_name not in ["any", "all"]:
            pytest.skip("These are tested in BaseNumericReduceTests")
        return True
