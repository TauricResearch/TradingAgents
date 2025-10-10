import pytest

import pandas as pd
import pandas._testing as tm


@pytest.mark.parametrize(
    "values, dtype",
    [
        ([], "object"),
        ([1, 2, 3], "int64"),
        ([1.0, 2.0, 3.0], "float64"),
        (["a", "b", "c"], "object"),
        (["a", "b", "c"], "string"),
        ([1, 2, 3], "datetime64[ns]"),
        ([1, 2, 3], "datetime64[ns, CET]"),
        ([1, 2, 3], "timedelta64[ns]"),
        (["2000", "2001", "2002"], "Period[D]"),
        ([1, 0, 3], "Sparse"),
        ([pd.Interval(0, 1), pd.Interval(1, 2), pd.Interval(3, 4)], "interval"),
    ],
)
@pytest.mark.parametrize(
    "mask", [[True, False, False], [True, True, True], [False, False, False]]
)
@pytest.mark.parametrize("indexer_class", [list, pd.array, pd.Index, pd.Series])
@pytest.mark.parametrize("frame", [True, False])
def test_series_mask_boolean(values, dtype, mask, indexer_class, frame):
    # In case len(values) < 3
    index = ["a", "b", "c"][: len(values)]
    mask = mask[: len(values)]

    obj = pd.Series(values, dtype=dtype, index=index)
    if frame:
        if len(values) == 0:
            # Otherwise obj is an empty DataFrame with shape (0, 1)
            obj = pd.DataFrame(dtype=dtype, index=index)
        else:
            obj = obj.to_frame()

    if indexer_class is pd.array:
        mask = pd.array(mask, dtype="boolean")
    elif indexer_class is pd.Series:
        mask = pd.Series(mask, index=obj.index, dtype="boolean")
    else:
        mask = indexer_class(mask)

    expected = obj[mask]

    result = obj[mask]
    tm.assert_equal(result, expected)

    if indexer_class is pd.Series:
        msg = "iLocation based boolean indexing cannot use an indexable as a mask"
        with pytest.raises(ValueError, match=msg):
            result = obj.iloc[mask]
            tm.assert_equal(result, expected)
    else:
        result = obj.iloc[mask]
        tm.assert_equal(result, expected)

    result = obj.loc[mask]
    tm.assert_equal(result, expected)


def test_na_treated_as_false(frame_or_series, indexer_sli):
    # https://github.com/pandas-dev/pandas/issues/31503
    obj = frame_or_series([1, 2, 3])

    mask = pd.array([True, False, None], dtype="boolean")

    result = indexer_sli(obj)[mask]
    expected = indexer_sli(obj)[mask.fillna(False)]

    tm.assert_equal(result, expected)
