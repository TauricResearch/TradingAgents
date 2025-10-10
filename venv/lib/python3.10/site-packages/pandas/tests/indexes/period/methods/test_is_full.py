import pytest

from pandas import PeriodIndex


def test_is_full():
    index = PeriodIndex([2005, 2007, 2009], freq="Y")
    assert not index.is_full

    index = PeriodIndex([2005, 2006, 2007], freq="Y")
    assert index.is_full

    index = PeriodIndex([2005, 2005, 2007], freq="Y")
    assert not index.is_full

    index = PeriodIndex([2005, 2005, 2006], freq="Y")
    assert index.is_full

    index = PeriodIndex([2006, 2005, 2005], freq="Y")
    with pytest.raises(ValueError, match="Index is not monotonic"):
        index.is_full

    assert index[:0].is_full
