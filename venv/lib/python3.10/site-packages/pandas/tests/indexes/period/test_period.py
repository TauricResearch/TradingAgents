import numpy as np
import pytest

from pandas import (
    Index,
    NaT,
    Period,
    PeriodIndex,
    Series,
    date_range,
    offsets,
    period_range,
)
import pandas._testing as tm


class TestPeriodIndex:
    def test_view_asi8(self):
        idx = PeriodIndex([], freq="M")

        exp = np.array([], dtype=np.int64)
        tm.assert_numpy_array_equal(idx.view("i8"), exp)
        tm.assert_numpy_array_equal(idx.asi8, exp)

        idx = PeriodIndex(["2011-01", NaT], freq="M")

        exp = np.array([492, -9223372036854775808], dtype=np.int64)
        tm.assert_numpy_array_equal(idx.view("i8"), exp)
        tm.assert_numpy_array_equal(idx.asi8, exp)

        exp = np.array([14975, -9223372036854775808], dtype=np.int64)
        idx = PeriodIndex(["2011-01-01", NaT], freq="D")
        tm.assert_numpy_array_equal(idx.view("i8"), exp)
        tm.assert_numpy_array_equal(idx.asi8, exp)

    def test_values(self):
        idx = PeriodIndex([], freq="M")

        exp = np.array([], dtype=object)
        tm.assert_numpy_array_equal(idx.values, exp)
        tm.assert_numpy_array_equal(idx.to_numpy(), exp)

        exp = np.array([], dtype=np.int64)
        tm.assert_numpy_array_equal(idx.asi8, exp)

        idx = PeriodIndex(["2011-01", NaT], freq="M")

        exp = np.array([Period("2011-01", freq="M"), NaT], dtype=object)
        tm.assert_numpy_array_equal(idx.values, exp)
        tm.assert_numpy_array_equal(idx.to_numpy(), exp)
        exp = np.array([492, -9223372036854775808], dtype=np.int64)
        tm.assert_numpy_array_equal(idx.asi8, exp)

        idx = PeriodIndex(["2011-01-01", NaT], freq="D")

        exp = np.array([Period("2011-01-01", freq="D"), NaT], dtype=object)
        tm.assert_numpy_array_equal(idx.values, exp)
        tm.assert_numpy_array_equal(idx.to_numpy(), exp)
        exp = np.array([14975, -9223372036854775808], dtype=np.int64)
        tm.assert_numpy_array_equal(idx.asi8, exp)

    @pytest.mark.parametrize(
        "field",
        [
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "weekofyear",
            "week",
            "dayofweek",
            "day_of_week",
            "dayofyear",
            "day_of_year",
            "quarter",
            "qyear",
            "days_in_month",
        ],
    )
    @pytest.mark.parametrize(
        "periodindex",
        [
            period_range(freq="Y", start="1/1/2001", end="12/1/2005"),
            period_range(freq="Q", start="1/1/2001", end="12/1/2002"),
            period_range(freq="M", start="1/1/2001", end="1/1/2002"),
            period_range(freq="D", start="12/1/2001", end="6/1/2001"),
            period_range(freq="h", start="12/31/2001", end="1/1/2002 23:00"),
            period_range(freq="Min", start="12/31/2001", end="1/1/2002 00:20"),
            period_range(
                freq="s", start="12/31/2001 00:00:00", end="12/31/2001 00:05:00"
            ),
            period_range(end=Period("2006-12-31", "W"), periods=10),
        ],
    )
    def test_fields(self, periodindex, field):
        periods = list(periodindex)
        ser = Series(periodindex)

        field_idx = getattr(periodindex, field)
        assert len(periodindex) == len(field_idx)
        for x, val in zip(periods, field_idx):
            assert getattr(x, field) == val

        if len(ser) == 0:
            return

        field_s = getattr(ser.dt, field)
        assert len(periodindex) == len(field_s)
        for x, val in zip(periods, field_s):
            assert getattr(x, field) == val

    def test_is_(self):
        create_index = lambda: period_range(freq="Y", start="1/1/2001", end="12/1/2009")
        index = create_index()
        assert index.is_(index)
        assert not index.is_(create_index())
        assert index.is_(index.view())
        assert index.is_(index.view().view().view().view().view())
        assert index.view().is_(index)
        ind2 = index.view()
        index.name = "Apple"
        assert ind2.is_(index)
        assert not index.is_(index[:])
        assert not index.is_(index.asfreq("M"))
        assert not index.is_(index.asfreq("Y"))

        assert not index.is_(index - 2)
        assert not index.is_(index - 0)

    def test_index_unique(self):
        idx = PeriodIndex([2000, 2007, 2007, 2009, 2009], freq="Y-JUN")
        expected = PeriodIndex([2000, 2007, 2009], freq="Y-JUN")
        tm.assert_index_equal(idx.unique(), expected)
        assert idx.nunique() == 3

    def test_pindex_fieldaccessor_nat(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2012-03", "2012-04"], freq="D", name="name"
        )

        exp = Index([2011, 2011, -1, 2012, 2012], dtype=np.int64, name="name")
        tm.assert_index_equal(idx.year, exp)
        exp = Index([1, 2, -1, 3, 4], dtype=np.int64, name="name")
        tm.assert_index_equal(idx.month, exp)

    def test_pindex_multiples(self):
        expected = PeriodIndex(
            ["2011-01", "2011-03", "2011-05", "2011-07", "2011-09", "2011-11"],
            freq="2M",
        )

        pi = period_range(start="1/1/11", end="12/31/11", freq="2M")
        tm.assert_index_equal(pi, expected)
        assert pi.freq == offsets.MonthEnd(2)
        assert pi.freqstr == "2M"

        pi = period_range(start="1/1/11", periods=6, freq="2M")
        tm.assert_index_equal(pi, expected)
        assert pi.freq == offsets.MonthEnd(2)
        assert pi.freqstr == "2M"

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    @pytest.mark.filterwarnings("ignore:Period with BDay freq:FutureWarning")
    def test_iteration(self):
        index = period_range(start="1/1/10", periods=4, freq="B")

        result = list(index)
        assert isinstance(result[0], Period)
        assert result[0].freq == index.freq

    def test_with_multi_index(self):
        # #1705
        index = date_range("1/1/2012", periods=4, freq="12h")
        index_as_arrays = [index.to_period(freq="D"), index.hour]

        s = Series([0, 1, 2, 3], index_as_arrays)

        assert isinstance(s.index.levels[0], PeriodIndex)

        assert isinstance(s.index.values[0][0], Period)

    def test_map(self):
        # test_map_dictlike generally tests

        index = PeriodIndex([2005, 2007, 2009], freq="Y")
        result = index.map(lambda x: x.ordinal)
        exp = Index([x.ordinal for x in index])
        tm.assert_index_equal(result, exp)


def test_maybe_convert_timedelta():
    pi = PeriodIndex(["2000", "2001"], freq="D")
    offset = offsets.Day(2)
    assert pi._maybe_convert_timedelta(offset) == 2
    assert pi._maybe_convert_timedelta(2) == 2

    offset = offsets.BusinessDay()
    msg = r"Input has different freq=B from PeriodIndex\(freq=D\)"
    with pytest.raises(ValueError, match=msg):
        pi._maybe_convert_timedelta(offset)


@pytest.mark.parametrize("array", [True, False])
def test_dunder_array(array):
    obj = PeriodIndex(["2000-01-01", "2001-01-01"], freq="D")
    if array:
        obj = obj._data

    expected = np.array([obj[0], obj[1]], dtype=object)
    result = np.array(obj)
    tm.assert_numpy_array_equal(result, expected)

    result = np.asarray(obj)
    tm.assert_numpy_array_equal(result, expected)

    expected = obj.asi8
    for dtype in ["i8", "int64", np.int64]:
        result = np.array(obj, dtype=dtype)
        tm.assert_numpy_array_equal(result, expected)

        result = np.asarray(obj, dtype=dtype)
        tm.assert_numpy_array_equal(result, expected)

    for dtype in ["float64", "int32", "uint64"]:
        msg = "argument must be"
        with pytest.raises(TypeError, match=msg):
            np.array(obj, dtype=dtype)
        with pytest.raises(TypeError, match=msg):
            np.array(obj, dtype=getattr(np, dtype))
