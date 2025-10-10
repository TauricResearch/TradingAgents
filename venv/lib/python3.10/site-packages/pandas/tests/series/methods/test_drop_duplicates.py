import numpy as np
import pytest

import pandas as pd
from pandas import (
    Categorical,
    Series,
)
import pandas._testing as tm


@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", Series([False, False, False, False, True, True, False])),
        ("last", Series([False, True, True, False, False, False, False])),
        (False, Series([False, True, True, False, True, True, False])),
    ],
)
def test_drop_duplicates(any_numpy_dtype, keep, expected):
    tc = Series([1, 0, 3, 5, 3, 0, 4], dtype=np.dtype(any_numpy_dtype))

    if tc.dtype == "bool":
        pytest.skip("tested separately in test_drop_duplicates_bool")

    tm.assert_series_equal(tc.duplicated(keep=keep), expected)
    tm.assert_series_equal(tc.drop_duplicates(keep=keep), tc[~expected])
    sc = tc.copy()
    return_value = sc.drop_duplicates(keep=keep, inplace=True)
    assert return_value is None
    tm.assert_series_equal(sc, tc[~expected])


@pytest.mark.parametrize(
    "keep, expected",
    [
        ("first", Series([False, False, True, True])),
        ("last", Series([True, True, False, False])),
        (False, Series([True, True, True, True])),
    ],
)
def test_drop_duplicates_bool(keep, expected):
    tc = Series([True, False, True, False])

    tm.assert_series_equal(tc.duplicated(keep=keep), expected)
    tm.assert_series_equal(tc.drop_duplicates(keep=keep), tc[~expected])
    sc = tc.copy()
    return_value = sc.drop_duplicates(keep=keep, inplace=True)
    tm.assert_series_equal(sc, tc[~expected])
    assert return_value is None


@pytest.mark.parametrize("values", [[], list(range(5))])
def test_drop_duplicates_no_duplicates(any_numpy_dtype, keep, values):
    tc = Series(values, dtype=np.dtype(any_numpy_dtype))
    expected = Series([False] * len(tc), dtype="bool")

    if tc.dtype == "bool":
        # 0 -> False and 1-> True
        # any other value would be duplicated
        tc = tc[:2]
        expected = expected[:2]

    tm.assert_series_equal(tc.duplicated(keep=keep), expected)

    result_dropped = tc.drop_duplicates(keep=keep)
    tm.assert_series_equal(result_dropped, tc)

    # validate shallow copy
    assert result_dropped is not tc


class TestSeriesDropDuplicates:
    @pytest.fixture(
        params=["int_", "uint", "float64", "str_", "timedelta64[h]", "datetime64[D]"]
    )
    def dtype(self, request):
        return request.param

    @pytest.fixture
    def cat_series_unused_category(self, dtype, ordered):
        # Test case 1
        cat_array = np.array([1, 2, 3, 4, 5], dtype=np.dtype(dtype))

        input1 = np.array([1, 2, 3, 3], dtype=np.dtype(dtype))
        cat = Categorical(input1, categories=cat_array, ordered=ordered)
        tc1 = Series(cat)
        return tc1

    def test_drop_duplicates_categorical_non_bool(self, cat_series_unused_category):
        tc1 = cat_series_unused_category

        expected = Series([False, False, False, True])

        result = tc1.duplicated()
        tm.assert_series_equal(result, expected)

        result = tc1.drop_duplicates()
        tm.assert_series_equal(result, tc1[~expected])

        sc = tc1.copy()
        return_value = sc.drop_duplicates(inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc1[~expected])

    def test_drop_duplicates_categorical_non_bool_keeplast(
        self, cat_series_unused_category
    ):
        tc1 = cat_series_unused_category

        expected = Series([False, False, True, False])

        result = tc1.duplicated(keep="last")
        tm.assert_series_equal(result, expected)

        result = tc1.drop_duplicates(keep="last")
        tm.assert_series_equal(result, tc1[~expected])

        sc = tc1.copy()
        return_value = sc.drop_duplicates(keep="last", inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc1[~expected])

    def test_drop_duplicates_categorical_non_bool_keepfalse(
        self, cat_series_unused_category
    ):
        tc1 = cat_series_unused_category

        expected = Series([False, False, True, True])

        result = tc1.duplicated(keep=False)
        tm.assert_series_equal(result, expected)

        result = tc1.drop_duplicates(keep=False)
        tm.assert_series_equal(result, tc1[~expected])

        sc = tc1.copy()
        return_value = sc.drop_duplicates(keep=False, inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc1[~expected])

    @pytest.fixture
    def cat_series(self, dtype, ordered):
        # no unused categories, unlike cat_series_unused_category
        cat_array = np.array([1, 2, 3, 4, 5], dtype=np.dtype(dtype))

        input2 = np.array([1, 2, 3, 5, 3, 2, 4], dtype=np.dtype(dtype))
        cat = Categorical(input2, categories=cat_array, ordered=ordered)
        tc2 = Series(cat)
        return tc2

    def test_drop_duplicates_categorical_non_bool2(self, cat_series):
        tc2 = cat_series

        expected = Series([False, False, False, False, True, True, False])

        result = tc2.duplicated()
        tm.assert_series_equal(result, expected)

        result = tc2.drop_duplicates()
        tm.assert_series_equal(result, tc2[~expected])

        sc = tc2.copy()
        return_value = sc.drop_duplicates(inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc2[~expected])

    def test_drop_duplicates_categorical_non_bool2_keeplast(self, cat_series):
        tc2 = cat_series

        expected = Series([False, True, True, False, False, False, False])

        result = tc2.duplicated(keep="last")
        tm.assert_series_equal(result, expected)

        result = tc2.drop_duplicates(keep="last")
        tm.assert_series_equal(result, tc2[~expected])

        sc = tc2.copy()
        return_value = sc.drop_duplicates(keep="last", inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc2[~expected])

    def test_drop_duplicates_categorical_non_bool2_keepfalse(self, cat_series):
        tc2 = cat_series

        expected = Series([False, True, True, False, True, True, False])

        result = tc2.duplicated(keep=False)
        tm.assert_series_equal(result, expected)

        result = tc2.drop_duplicates(keep=False)
        tm.assert_series_equal(result, tc2[~expected])

        sc = tc2.copy()
        return_value = sc.drop_duplicates(keep=False, inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc2[~expected])

    def test_drop_duplicates_categorical_bool(self, ordered):
        tc = Series(
            Categorical(
                [True, False, True, False], categories=[True, False], ordered=ordered
            )
        )

        expected = Series([False, False, True, True])
        tm.assert_series_equal(tc.duplicated(), expected)
        tm.assert_series_equal(tc.drop_duplicates(), tc[~expected])
        sc = tc.copy()
        return_value = sc.drop_duplicates(inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc[~expected])

        expected = Series([True, True, False, False])
        tm.assert_series_equal(tc.duplicated(keep="last"), expected)
        tm.assert_series_equal(tc.drop_duplicates(keep="last"), tc[~expected])
        sc = tc.copy()
        return_value = sc.drop_duplicates(keep="last", inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc[~expected])

        expected = Series([True, True, True, True])
        tm.assert_series_equal(tc.duplicated(keep=False), expected)
        tm.assert_series_equal(tc.drop_duplicates(keep=False), tc[~expected])
        sc = tc.copy()
        return_value = sc.drop_duplicates(keep=False, inplace=True)
        assert return_value is None
        tm.assert_series_equal(sc, tc[~expected])

    def test_drop_duplicates_categorical_bool_na(self, nulls_fixture):
        # GH#44351
        ser = Series(
            Categorical(
                [True, False, True, False, nulls_fixture],
                categories=[True, False],
                ordered=True,
            )
        )
        result = ser.drop_duplicates()
        expected = Series(
            Categorical([True, False, np.nan], categories=[True, False], ordered=True),
            index=[0, 1, 4],
        )
        tm.assert_series_equal(result, expected)

    def test_drop_duplicates_ignore_index(self):
        # GH#48304
        ser = Series([1, 2, 2, 3])
        result = ser.drop_duplicates(ignore_index=True)
        expected = Series([1, 2, 3])
        tm.assert_series_equal(result, expected)

    def test_duplicated_arrow_dtype(self):
        pytest.importorskip("pyarrow")
        ser = Series([True, False, None, False], dtype="bool[pyarrow]")
        result = ser.drop_duplicates()
        expected = Series([True, False, None], dtype="bool[pyarrow]")
        tm.assert_series_equal(result, expected)

    def test_drop_duplicates_arrow_strings(self):
        # GH#54904
        pa = pytest.importorskip("pyarrow")
        ser = Series(["a", "a"], dtype=pd.ArrowDtype(pa.string()))
        result = ser.drop_duplicates()
        expecetd = Series(["a"], dtype=pd.ArrowDtype(pa.string()))
        tm.assert_series_equal(result, expecetd)
