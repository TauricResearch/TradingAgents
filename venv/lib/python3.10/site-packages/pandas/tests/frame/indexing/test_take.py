import pytest

import pandas._testing as tm


class TestDataFrameTake:
    def test_take_slices_deprecated(self, float_frame):
        # GH#51539
        df = float_frame

        slc = slice(0, 4, 1)
        with tm.assert_produces_warning(FutureWarning):
            df.take(slc, axis=0)
        with tm.assert_produces_warning(FutureWarning):
            df.take(slc, axis=1)

    def test_take(self, float_frame):
        # homogeneous
        order = [3, 1, 2, 0]
        for df in [float_frame]:
            result = df.take(order, axis=0)
            expected = df.reindex(df.index.take(order))
            tm.assert_frame_equal(result, expected)

            # axis = 1
            result = df.take(order, axis=1)
            expected = df.loc[:, ["D", "B", "C", "A"]]
            tm.assert_frame_equal(result, expected, check_names=False)

        # negative indices
        order = [2, 1, -1]
        for df in [float_frame]:
            result = df.take(order, axis=0)
            expected = df.reindex(df.index.take(order))
            tm.assert_frame_equal(result, expected)

            result = df.take(order, axis=0)
            tm.assert_frame_equal(result, expected)

            # axis = 1
            result = df.take(order, axis=1)
            expected = df.loc[:, ["C", "B", "D"]]
            tm.assert_frame_equal(result, expected, check_names=False)

        # illegal indices
        msg = "indices are out-of-bounds"
        with pytest.raises(IndexError, match=msg):
            df.take([3, 1, 2, 30], axis=0)
        with pytest.raises(IndexError, match=msg):
            df.take([3, 1, 2, -31], axis=0)
        with pytest.raises(IndexError, match=msg):
            df.take([3, 1, 2, 5], axis=1)
        with pytest.raises(IndexError, match=msg):
            df.take([3, 1, 2, -5], axis=1)

    def test_take_mixed_type(self, float_string_frame):
        # mixed-dtype
        order = [4, 1, 2, 0, 3]
        for df in [float_string_frame]:
            result = df.take(order, axis=0)
            expected = df.reindex(df.index.take(order))
            tm.assert_frame_equal(result, expected)

            # axis = 1
            result = df.take(order, axis=1)
            expected = df.loc[:, ["foo", "B", "C", "A", "D"]]
            tm.assert_frame_equal(result, expected)

        # negative indices
        order = [4, 1, -2]
        for df in [float_string_frame]:
            result = df.take(order, axis=0)
            expected = df.reindex(df.index.take(order))
            tm.assert_frame_equal(result, expected)

            # axis = 1
            result = df.take(order, axis=1)
            expected = df.loc[:, ["foo", "B", "D"]]
            tm.assert_frame_equal(result, expected)

    def test_take_mixed_numeric(self, mixed_float_frame, mixed_int_frame):
        # by dtype
        order = [1, 2, 0, 3]
        for df in [mixed_float_frame, mixed_int_frame]:
            result = df.take(order, axis=0)
            expected = df.reindex(df.index.take(order))
            tm.assert_frame_equal(result, expected)

            # axis = 1
            result = df.take(order, axis=1)
            expected = df.loc[:, ["B", "C", "A", "D"]]
            tm.assert_frame_equal(result, expected)
