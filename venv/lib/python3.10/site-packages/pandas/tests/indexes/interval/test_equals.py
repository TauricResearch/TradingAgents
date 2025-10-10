import numpy as np

from pandas import (
    IntervalIndex,
    date_range,
)


class TestEquals:
    def test_equals(self, closed):
        expected = IntervalIndex.from_breaks(np.arange(5), closed=closed)
        assert expected.equals(expected)
        assert expected.equals(expected.copy())

        assert not expected.equals(expected.astype(object))
        assert not expected.equals(np.array(expected))
        assert not expected.equals(list(expected))

        assert not expected.equals([1, 2])
        assert not expected.equals(np.array([1, 2]))
        assert not expected.equals(date_range("20130101", periods=2))

        expected_name1 = IntervalIndex.from_breaks(
            np.arange(5), closed=closed, name="foo"
        )
        expected_name2 = IntervalIndex.from_breaks(
            np.arange(5), closed=closed, name="bar"
        )
        assert expected.equals(expected_name1)
        assert expected_name1.equals(expected_name2)

        for other_closed in {"left", "right", "both", "neither"} - {closed}:
            expected_other_closed = IntervalIndex.from_breaks(
                np.arange(5), closed=other_closed
            )
            assert not expected.equals(expected_other_closed)
