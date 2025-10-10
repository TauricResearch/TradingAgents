import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    date_range,
)


@pytest.fixture
def series_ints():
    return Series(np.random.default_rng(2).random(4), index=np.arange(0, 8, 2))


@pytest.fixture
def frame_ints():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)),
        index=np.arange(0, 8, 2),
        columns=np.arange(0, 12, 3),
    )


@pytest.fixture
def series_uints():
    return Series(
        np.random.default_rng(2).random(4),
        index=Index(np.arange(0, 8, 2, dtype=np.uint64)),
    )


@pytest.fixture
def frame_uints():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)),
        index=Index(range(0, 8, 2), dtype=np.uint64),
        columns=Index(range(0, 12, 3), dtype=np.uint64),
    )


@pytest.fixture
def series_labels():
    return Series(np.random.default_rng(2).standard_normal(4), index=list("abcd"))


@pytest.fixture
def frame_labels():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)),
        index=list("abcd"),
        columns=list("ABCD"),
    )


@pytest.fixture
def series_ts():
    return Series(
        np.random.default_rng(2).standard_normal(4),
        index=date_range("20130101", periods=4),
    )


@pytest.fixture
def frame_ts():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)),
        index=date_range("20130101", periods=4),
    )


@pytest.fixture
def series_floats():
    return Series(
        np.random.default_rng(2).random(4),
        index=Index(range(0, 8, 2), dtype=np.float64),
    )


@pytest.fixture
def frame_floats():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)),
        index=Index(range(0, 8, 2), dtype=np.float64),
        columns=Index(range(0, 12, 3), dtype=np.float64),
    )


@pytest.fixture
def series_mixed():
    return Series(np.random.default_rng(2).standard_normal(4), index=[2, 4, "null", 8])


@pytest.fixture
def frame_mixed():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)), index=[2, 4, "null", 8]
    )


@pytest.fixture
def frame_empty():
    return DataFrame()


@pytest.fixture
def series_empty():
    return Series(dtype=object)


@pytest.fixture
def frame_multi():
    return DataFrame(
        np.random.default_rng(2).standard_normal((4, 4)),
        index=MultiIndex.from_product([[1, 2], [3, 4]]),
        columns=MultiIndex.from_product([[5, 6], [7, 8]]),
    )


@pytest.fixture
def series_multi():
    return Series(
        np.random.default_rng(2).random(4),
        index=MultiIndex.from_product([[1, 2], [3, 4]]),
    )
