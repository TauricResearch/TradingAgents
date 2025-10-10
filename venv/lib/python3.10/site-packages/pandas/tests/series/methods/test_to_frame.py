import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm


class TestToFrame:
    def test_to_frame_respects_name_none(self):
        # GH#44212 if we explicitly pass name=None, then that should be respected,
        #  not changed to 0
        # GH-45448 this is first deprecated & enforced in 2.0
        ser = Series(range(3))
        result = ser.to_frame(None)

        exp_index = Index([None], dtype=object)
        tm.assert_index_equal(result.columns, exp_index)

        result = ser.rename("foo").to_frame(None)
        exp_index = Index([None], dtype=object)
        tm.assert_index_equal(result.columns, exp_index)

    def test_to_frame(self, datetime_series):
        datetime_series.name = None
        rs = datetime_series.to_frame()
        xp = DataFrame(datetime_series.values, index=datetime_series.index)
        tm.assert_frame_equal(rs, xp)

        datetime_series.name = "testname"
        rs = datetime_series.to_frame()
        xp = DataFrame(
            {"testname": datetime_series.values}, index=datetime_series.index
        )
        tm.assert_frame_equal(rs, xp)

        rs = datetime_series.to_frame(name="testdifferent")
        xp = DataFrame(
            {"testdifferent": datetime_series.values}, index=datetime_series.index
        )
        tm.assert_frame_equal(rs, xp)

    @pytest.mark.filterwarnings(
        "ignore:Passing a BlockManager|Passing a SingleBlockManager:DeprecationWarning"
    )
    def test_to_frame_expanddim(self):
        # GH#9762

        class SubclassedSeries(Series):
            @property
            def _constructor_expanddim(self):
                return SubclassedFrame

        class SubclassedFrame(DataFrame):
            pass

        ser = SubclassedSeries([1, 2, 3], name="X")
        result = ser.to_frame()
        assert isinstance(result, SubclassedFrame)
        expected = SubclassedFrame({"X": [1, 2, 3]})
        tm.assert_frame_equal(result, expected)
