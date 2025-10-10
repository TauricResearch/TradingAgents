import pytest

from pandas import (
    DatetimeIndex,
    Index,
    MultiIndex,
    Period,
    date_range,
)
import pandas._testing as tm


class TestMap:
    def test_map(self):
        rng = date_range("1/1/2000", periods=10)

        f = lambda x: x.strftime("%Y%m%d")
        result = rng.map(f)
        exp = Index([f(x) for x in rng])
        tm.assert_index_equal(result, exp)

    def test_map_fallthrough(self, capsys):
        # GH#22067, check we don't get warnings about silently ignored errors
        dti = date_range("2017-01-01", "2018-01-01", freq="B")

        dti.map(lambda x: Period(year=x.year, month=x.month, freq="M"))

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_map_bug_1677(self):
        index = DatetimeIndex(["2012-04-25 09:30:00.393000"])
        f = index.asof

        result = index.map(f)
        expected = Index([f(index[0])])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("name", [None, "name"])
    def test_index_map(self, name):
        # see GH#20990
        count = 6
        index = date_range("2018-01-01", periods=count, freq="ME", name=name).map(
            lambda x: (x.year, x.month)
        )
        exp_index = MultiIndex.from_product(((2018,), range(1, 7)), names=[name, name])
        tm.assert_index_equal(index, exp_index)
