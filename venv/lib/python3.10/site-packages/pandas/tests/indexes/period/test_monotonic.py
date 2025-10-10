from pandas import (
    Period,
    PeriodIndex,
)


def test_is_monotonic_increasing():
    # GH#17717
    p0 = Period("2017-09-01")
    p1 = Period("2017-09-02")
    p2 = Period("2017-09-03")

    idx_inc0 = PeriodIndex([p0, p1, p2])
    idx_inc1 = PeriodIndex([p0, p1, p1])
    idx_dec0 = PeriodIndex([p2, p1, p0])
    idx_dec1 = PeriodIndex([p2, p1, p1])
    idx = PeriodIndex([p1, p2, p0])

    assert idx_inc0.is_monotonic_increasing is True
    assert idx_inc1.is_monotonic_increasing is True
    assert idx_dec0.is_monotonic_increasing is False
    assert idx_dec1.is_monotonic_increasing is False
    assert idx.is_monotonic_increasing is False


def test_is_monotonic_decreasing():
    # GH#17717
    p0 = Period("2017-09-01")
    p1 = Period("2017-09-02")
    p2 = Period("2017-09-03")

    idx_inc0 = PeriodIndex([p0, p1, p2])
    idx_inc1 = PeriodIndex([p0, p1, p1])
    idx_dec0 = PeriodIndex([p2, p1, p0])
    idx_dec1 = PeriodIndex([p2, p1, p1])
    idx = PeriodIndex([p1, p2, p0])

    assert idx_inc0.is_monotonic_decreasing is False
    assert idx_inc1.is_monotonic_decreasing is False
    assert idx_dec0.is_monotonic_decreasing is True
    assert idx_dec1.is_monotonic_decreasing is True
    assert idx.is_monotonic_decreasing is False
