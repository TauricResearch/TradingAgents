import pytest

from pandas import (
    Interval,
    Timedelta,
    Timestamp,
)


@pytest.fixture(
    params=[
        (Timedelta("0 days"), Timedelta("1 day")),
        (Timestamp("2018-01-01"), Timedelta("1 day")),
        (0, 1),
    ],
    ids=lambda x: type(x[0]).__name__,
)
def start_shift(request):
    """
    Fixture for generating intervals of types from a start value and a shift
    value that can be added to start to generate an endpoint
    """
    return request.param


class TestOverlaps:
    def test_overlaps_self(self, start_shift, closed):
        start, shift = start_shift
        interval = Interval(start, start + shift, closed)
        assert interval.overlaps(interval)

    def test_overlaps_nested(self, start_shift, closed, other_closed):
        start, shift = start_shift
        interval1 = Interval(start, start + 3 * shift, other_closed)
        interval2 = Interval(start + shift, start + 2 * shift, closed)

        # nested intervals should always overlap
        assert interval1.overlaps(interval2)

    def test_overlaps_disjoint(self, start_shift, closed, other_closed):
        start, shift = start_shift
        interval1 = Interval(start, start + shift, other_closed)
        interval2 = Interval(start + 2 * shift, start + 3 * shift, closed)

        # disjoint intervals should never overlap
        assert not interval1.overlaps(interval2)

    def test_overlaps_endpoint(self, start_shift, closed, other_closed):
        start, shift = start_shift
        interval1 = Interval(start, start + shift, other_closed)
        interval2 = Interval(start + shift, start + 2 * shift, closed)

        # overlap if shared endpoint is closed for both (overlap at a point)
        result = interval1.overlaps(interval2)
        expected = interval1.closed_right and interval2.closed_left
        assert result == expected

    @pytest.mark.parametrize(
        "other",
        [10, True, "foo", Timedelta("1 day"), Timestamp("2018-01-01")],
        ids=lambda x: type(x).__name__,
    )
    def test_overlaps_invalid_type(self, other):
        interval = Interval(0, 1)
        msg = f"`other` must be an Interval, got {type(other).__name__}"
        with pytest.raises(TypeError, match=msg):
            interval.overlaps(other)
