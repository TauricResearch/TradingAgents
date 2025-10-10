import pytest

from pandas._libs.tslibs import offsets

from pandas.tseries.frequencies import (
    is_subperiod,
    is_superperiod,
)


@pytest.mark.parametrize(
    "p1,p2,expected",
    [
        # Input validation.
        (offsets.MonthEnd(), None, False),
        (offsets.YearEnd(), None, False),
        (None, offsets.YearEnd(), False),
        (None, offsets.MonthEnd(), False),
        (None, None, False),
        (offsets.YearEnd(), offsets.MonthEnd(), True),
        (offsets.Hour(), offsets.Minute(), True),
        (offsets.Second(), offsets.Milli(), True),
        (offsets.Milli(), offsets.Micro(), True),
        (offsets.Micro(), offsets.Nano(), True),
    ],
)
def test_super_sub_symmetry(p1, p2, expected):
    assert is_superperiod(p1, p2) is expected
    assert is_subperiod(p2, p1) is expected
