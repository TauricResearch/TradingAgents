import numpy as np
import pytest

from pandas import (
    Categorical,
    CategoricalDtype,
    CategoricalIndex,
    DatetimeIndex,
    Interval,
    NaT,
    Period,
    Timestamp,
    array,
    to_datetime,
)
import pandas._testing as tm


class TestAstype:
    @pytest.mark.parametrize("cls", [Categorical, CategoricalIndex])
    @pytest.mark.parametrize("values", [[1, np.nan], [Timestamp("2000"), NaT]])
    def test_astype_nan_to_int(self, cls, values):
        # GH#28406
        obj = cls(values)

        msg = "Cannot (cast|convert)"
        with pytest.raises((ValueError, TypeError), match=msg):
            obj.astype(int)

    @pytest.mark.parametrize(
        "expected",
        [
            array(["2019", "2020"], dtype="datetime64[ns, UTC]"),
            array([0, 0], dtype="timedelta64[ns]"),
            array([Period("2019"), Period("2020")], dtype="period[Y-DEC]"),
            array([Interval(0, 1), Interval(1, 2)], dtype="interval"),
            array([1, np.nan], dtype="Int64"),
        ],
    )
    def test_astype_category_to_extension_dtype(self, expected):
        # GH#28668
        result = expected.astype("category").astype(expected.dtype)

        tm.assert_extension_array_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype, expected",
        [
            (
                "datetime64[ns]",
                np.array(["2015-01-01T00:00:00.000000000"], dtype="datetime64[ns]"),
            ),
            (
                "datetime64[ns, MET]",
                DatetimeIndex([Timestamp("2015-01-01 00:00:00+0100", tz="MET")]).array,
            ),
        ],
    )
    def test_astype_to_datetime64(self, dtype, expected):
        # GH#28448
        result = Categorical(["2015-01-01"]).astype(dtype)
        assert result == expected

    def test_astype_str_int_categories_to_nullable_int(self):
        # GH#39616
        dtype = CategoricalDtype([str(i) for i in range(5)])
        codes = np.random.default_rng(2).integers(5, size=20)
        arr = Categorical.from_codes(codes, dtype=dtype)

        res = arr.astype("Int64")
        expected = array(codes, dtype="Int64")
        tm.assert_extension_array_equal(res, expected)

    def test_astype_str_int_categories_to_nullable_float(self):
        # GH#39616
        dtype = CategoricalDtype([str(i / 2) for i in range(5)])
        codes = np.random.default_rng(2).integers(5, size=20)
        arr = Categorical.from_codes(codes, dtype=dtype)

        res = arr.astype("Float64")
        expected = array(codes, dtype="Float64") / 2
        tm.assert_extension_array_equal(res, expected)

    @pytest.mark.parametrize("ordered", [True, False])
    def test_astype(self, ordered):
        # string
        cat = Categorical(list("abbaaccc"), ordered=ordered)
        result = cat.astype(object)
        expected = np.array(cat)
        tm.assert_numpy_array_equal(result, expected)

        msg = r"Cannot cast object|str dtype to float64"
        with pytest.raises(ValueError, match=msg):
            cat.astype(float)

        # numeric
        cat = Categorical([0, 1, 2, 2, 1, 0, 1, 0, 2], ordered=ordered)
        result = cat.astype(object)
        expected = np.array(cat, dtype=object)
        tm.assert_numpy_array_equal(result, expected)

        result = cat.astype(int)
        expected = np.array(cat, dtype="int")
        tm.assert_numpy_array_equal(result, expected)

        result = cat.astype(float)
        expected = np.array(cat, dtype=float)
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("dtype_ordered", [True, False])
    @pytest.mark.parametrize("cat_ordered", [True, False])
    def test_astype_category(self, dtype_ordered, cat_ordered):
        # GH#10696/GH#18593
        data = list("abcaacbab")
        cat = Categorical(data, categories=list("bac"), ordered=cat_ordered)

        # standard categories
        dtype = CategoricalDtype(ordered=dtype_ordered)
        result = cat.astype(dtype)
        expected = Categorical(data, categories=cat.categories, ordered=dtype_ordered)
        tm.assert_categorical_equal(result, expected)

        # non-standard categories
        dtype = CategoricalDtype(list("adc"), dtype_ordered)
        result = cat.astype(dtype)
        expected = Categorical(data, dtype=dtype)
        tm.assert_categorical_equal(result, expected)

        if dtype_ordered is False:
            # dtype='category' can't specify ordered, so only test once
            result = cat.astype("category")
            expected = cat
            tm.assert_categorical_equal(result, expected)

    def test_astype_object_datetime_categories(self):
        # GH#40754
        cat = Categorical(to_datetime(["2021-03-27", NaT]))
        result = cat.astype(object)
        expected = np.array([Timestamp("2021-03-27 00:00:00"), NaT], dtype="object")
        tm.assert_numpy_array_equal(result, expected)

    def test_astype_object_timestamp_categories(self):
        # GH#18024
        cat = Categorical([Timestamp("2014-01-01")])
        result = cat.astype(object)
        expected = np.array([Timestamp("2014-01-01 00:00:00")], dtype="object")
        tm.assert_numpy_array_equal(result, expected)

    def test_astype_category_readonly_mask_values(self):
        # GH#53658
        arr = array([0, 1, 2], dtype="Int64")
        arr._mask.flags["WRITEABLE"] = False
        result = arr.astype("category")
        expected = array([0, 1, 2], dtype="Int64").astype("category")
        tm.assert_extension_array_equal(result, expected)
