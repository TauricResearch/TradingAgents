import pytest

from pandas import DataFrame
import pandas._testing as tm


class TestGet:
    def test_get(self, float_frame):
        b = float_frame.get("B")
        tm.assert_series_equal(b, float_frame["B"])

        assert float_frame.get("foo") is None
        tm.assert_series_equal(
            float_frame.get("foo", float_frame["B"]), float_frame["B"]
        )

    @pytest.mark.parametrize(
        "df",
        [
            DataFrame(),
            DataFrame(columns=list("AB")),
            DataFrame(columns=list("AB"), index=range(3)),
        ],
    )
    def test_get_none(self, df):
        # see gh-5652
        assert df.get(None) is None
