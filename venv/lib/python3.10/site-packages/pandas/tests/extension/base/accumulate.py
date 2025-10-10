import pytest

import pandas as pd
import pandas._testing as tm


class BaseAccumulateTests:
    """
    Accumulation specific tests. Generally these only
    make sense for numeric/boolean operations.
    """

    def _supports_accumulation(self, ser: pd.Series, op_name: str) -> bool:
        # Do we expect this accumulation to be supported for this dtype?
        # We default to assuming "no"; subclass authors should override here.
        return False

    def check_accumulate(self, ser: pd.Series, op_name: str, skipna: bool):
        try:
            alt = ser.astype("float64")
        except (TypeError, ValueError):
            # e.g. Period can't be cast to float64 (TypeError)
            #      String can't be cast to float64 (ValueError)
            alt = ser.astype(object)

        result = getattr(ser, op_name)(skipna=skipna)
        expected = getattr(alt, op_name)(skipna=skipna)
        tm.assert_series_equal(result, expected, check_dtype=False)

    @pytest.mark.parametrize("skipna", [True, False])
    def test_accumulate_series(self, data, all_numeric_accumulations, skipna):
        op_name = all_numeric_accumulations
        ser = pd.Series(data)

        if self._supports_accumulation(ser, op_name):
            self.check_accumulate(ser, op_name, skipna)
        else:
            with pytest.raises((NotImplementedError, TypeError)):
                # TODO: require TypeError for things that will _never_ work?
                getattr(ser, op_name)(skipna=skipna)
