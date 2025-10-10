import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm
import pandas.core.common as com


class TestSample:
    @pytest.fixture
    def obj(self, frame_or_series):
        if frame_or_series is Series:
            arr = np.random.default_rng(2).standard_normal(10)
        else:
            arr = np.random.default_rng(2).standard_normal((10, 10))
        return frame_or_series(arr, dtype=None)

    @pytest.mark.parametrize("test", list(range(10)))
    def test_sample(self, test, obj):
        # Fixes issue: 2419
        # Check behavior of random_state argument
        # Check for stability when receives seed or random state -- run 10
        # times.

        seed = np.random.default_rng(2).integers(0, 100)
        tm.assert_equal(
            obj.sample(n=4, random_state=seed), obj.sample(n=4, random_state=seed)
        )

        tm.assert_equal(
            obj.sample(frac=0.7, random_state=seed),
            obj.sample(frac=0.7, random_state=seed),
        )

        tm.assert_equal(
            obj.sample(n=4, random_state=np.random.default_rng(test)),
            obj.sample(n=4, random_state=np.random.default_rng(test)),
        )

        tm.assert_equal(
            obj.sample(frac=0.7, random_state=np.random.default_rng(test)),
            obj.sample(frac=0.7, random_state=np.random.default_rng(test)),
        )

        tm.assert_equal(
            obj.sample(
                frac=2,
                replace=True,
                random_state=np.random.default_rng(test),
            ),
            obj.sample(
                frac=2,
                replace=True,
                random_state=np.random.default_rng(test),
            ),
        )

        os1, os2 = [], []
        for _ in range(2):
            os1.append(obj.sample(n=4, random_state=test))
            os2.append(obj.sample(frac=0.7, random_state=test))
        tm.assert_equal(*os1)
        tm.assert_equal(*os2)

    def test_sample_lengths(self, obj):
        # Check lengths are right
        assert len(obj.sample(n=4) == 4)
        assert len(obj.sample(frac=0.34) == 3)
        assert len(obj.sample(frac=0.36) == 4)

    def test_sample_invalid_random_state(self, obj):
        # Check for error when random_state argument invalid.
        msg = (
            "random_state must be an integer, array-like, a BitGenerator, Generator, "
            "a numpy RandomState, or None"
        )
        with pytest.raises(ValueError, match=msg):
            obj.sample(random_state="a_string")

    def test_sample_wont_accept_n_and_frac(self, obj):
        # Giving both frac and N throws error
        msg = "Please enter a value for `frac` OR `n`, not both"
        with pytest.raises(ValueError, match=msg):
            obj.sample(n=3, frac=0.3)

    def test_sample_requires_positive_n_frac(self, obj):
        with pytest.raises(
            ValueError,
            match="A negative number of rows requested. Please provide `n` >= 0",
        ):
            obj.sample(n=-3)
        with pytest.raises(
            ValueError,
            match="A negative number of rows requested. Please provide `frac` >= 0",
        ):
            obj.sample(frac=-0.3)

    def test_sample_requires_integer_n(self, obj):
        # Make sure float values of `n` give error
        with pytest.raises(ValueError, match="Only integers accepted as `n` values"):
            obj.sample(n=3.2)

    def test_sample_invalid_weight_lengths(self, obj):
        # Weight length must be right
        msg = "Weights and axis to be sampled must be of same length"
        with pytest.raises(ValueError, match=msg):
            obj.sample(n=3, weights=[0, 1])

        with pytest.raises(ValueError, match=msg):
            bad_weights = [0.5] * 11
            obj.sample(n=3, weights=bad_weights)

        with pytest.raises(ValueError, match="Fewer non-zero entries in p than size"):
            bad_weight_series = Series([0, 0, 0.2])
            obj.sample(n=4, weights=bad_weight_series)

    def test_sample_negative_weights(self, obj):
        # Check won't accept negative weights
        bad_weights = [-0.1] * 10
        msg = "weight vector many not include negative values"
        with pytest.raises(ValueError, match=msg):
            obj.sample(n=3, weights=bad_weights)

    def test_sample_inf_weights(self, obj):
        # Check inf and -inf throw errors:

        weights_with_inf = [0.1] * 10
        weights_with_inf[0] = np.inf
        msg = "weight vector may not include `inf` values"
        with pytest.raises(ValueError, match=msg):
            obj.sample(n=3, weights=weights_with_inf)

        weights_with_ninf = [0.1] * 10
        weights_with_ninf[0] = -np.inf
        with pytest.raises(ValueError, match=msg):
            obj.sample(n=3, weights=weights_with_ninf)

    def test_sample_zero_weights(self, obj):
        # All zeros raises errors

        zero_weights = [0] * 10
        with pytest.raises(ValueError, match="Invalid weights: weights sum to zero"):
            obj.sample(n=3, weights=zero_weights)

    def test_sample_missing_weights(self, obj):
        # All missing weights

        nan_weights = [np.nan] * 10
        with pytest.raises(ValueError, match="Invalid weights: weights sum to zero"):
            obj.sample(n=3, weights=nan_weights)

    def test_sample_none_weights(self, obj):
        # Check None are also replaced by zeros.
        weights_with_None = [None] * 10
        weights_with_None[5] = 0.5
        tm.assert_equal(
            obj.sample(n=1, axis=0, weights=weights_with_None), obj.iloc[5:6]
        )

    @pytest.mark.parametrize(
        "func_str,arg",
        [
            ("np.array", [2, 3, 1, 0]),
            ("np.random.MT19937", 3),
            ("np.random.PCG64", 11),
        ],
    )
    def test_sample_random_state(self, func_str, arg, frame_or_series):
        # GH#32503
        obj = DataFrame({"col1": range(10, 20), "col2": range(20, 30)})
        obj = tm.get_obj(obj, frame_or_series)
        result = obj.sample(n=3, random_state=eval(func_str)(arg))
        expected = obj.sample(n=3, random_state=com.random_state(eval(func_str)(arg)))
        tm.assert_equal(result, expected)

    def test_sample_generator(self, frame_or_series):
        # GH#38100
        obj = frame_or_series(np.arange(100))
        rng = np.random.default_rng(2)

        # Consecutive calls should advance the seed
        result1 = obj.sample(n=50, random_state=rng)
        result2 = obj.sample(n=50, random_state=rng)
        assert not (result1.index.values == result2.index.values).all()

        # Matching generator initialization must give same result
        # Consecutive calls should advance the seed
        result1 = obj.sample(n=50, random_state=np.random.default_rng(11))
        result2 = obj.sample(n=50, random_state=np.random.default_rng(11))
        tm.assert_equal(result1, result2)

    def test_sample_upsampling_without_replacement(self, frame_or_series):
        # GH#27451

        obj = DataFrame({"A": list("abc")})
        obj = tm.get_obj(obj, frame_or_series)

        msg = (
            "Replace has to be set to `True` when "
            "upsampling the population `frac` > 1."
        )
        with pytest.raises(ValueError, match=msg):
            obj.sample(frac=2, replace=False)


class TestSampleDataFrame:
    # Tests which are relevant only for DataFrame, so these are
    #  as fully parametrized as they can get.

    def test_sample(self):
        # GH#2419
        # additional specific object based tests

        # A few dataframe test with degenerate weights.
        easy_weight_list = [0] * 10
        easy_weight_list[5] = 1

        df = DataFrame(
            {
                "col1": range(10, 20),
                "col2": range(20, 30),
                "colString": ["a"] * 10,
                "easyweights": easy_weight_list,
            }
        )
        sample1 = df.sample(n=1, weights="easyweights")
        tm.assert_frame_equal(sample1, df.iloc[5:6])

        # Ensure proper error if string given as weight for Series or
        # DataFrame with axis = 1.
        ser = Series(range(10))
        msg = "Strings cannot be passed as weights when sampling from a Series."
        with pytest.raises(ValueError, match=msg):
            ser.sample(n=3, weights="weight_column")

        msg = (
            "Strings can only be passed to weights when sampling from rows on a "
            "DataFrame"
        )
        with pytest.raises(ValueError, match=msg):
            df.sample(n=1, weights="weight_column", axis=1)

        # Check weighting key error
        with pytest.raises(
            KeyError, match="'String passed to weights not a valid column'"
        ):
            df.sample(n=3, weights="not_a_real_column_name")

        # Check that re-normalizes weights that don't sum to one.
        weights_less_than_1 = [0] * 10
        weights_less_than_1[0] = 0.5
        tm.assert_frame_equal(df.sample(n=1, weights=weights_less_than_1), df.iloc[:1])

        ###
        # Test axis argument
        ###

        # Test axis argument
        df = DataFrame({"col1": range(10), "col2": ["a"] * 10})
        second_column_weight = [0, 1]
        tm.assert_frame_equal(
            df.sample(n=1, axis=1, weights=second_column_weight), df[["col2"]]
        )

        # Different axis arg types
        tm.assert_frame_equal(
            df.sample(n=1, axis="columns", weights=second_column_weight), df[["col2"]]
        )

        weight = [0] * 10
        weight[5] = 0.5
        tm.assert_frame_equal(df.sample(n=1, axis="rows", weights=weight), df.iloc[5:6])
        tm.assert_frame_equal(
            df.sample(n=1, axis="index", weights=weight), df.iloc[5:6]
        )

        # Check out of range axis values
        msg = "No axis named 2 for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.sample(n=1, axis=2)

        msg = "No axis named not_a_name for object type DataFrame"
        with pytest.raises(ValueError, match=msg):
            df.sample(n=1, axis="not_a_name")

        ser = Series(range(10))
        with pytest.raises(ValueError, match="No axis named 1 for object type Series"):
            ser.sample(n=1, axis=1)

        # Test weight length compared to correct axis
        msg = "Weights and axis to be sampled must be of same length"
        with pytest.raises(ValueError, match=msg):
            df.sample(n=1, axis=1, weights=[0.5] * 10)

    def test_sample_axis1(self):
        # Check weights with axis = 1
        easy_weight_list = [0] * 3
        easy_weight_list[2] = 1

        df = DataFrame(
            {"col1": range(10, 20), "col2": range(20, 30), "colString": ["a"] * 10}
        )
        sample1 = df.sample(n=1, axis=1, weights=easy_weight_list)
        tm.assert_frame_equal(sample1, df[["colString"]])

        # Test default axes
        tm.assert_frame_equal(
            df.sample(n=3, random_state=42), df.sample(n=3, axis=0, random_state=42)
        )

    def test_sample_aligns_weights_with_frame(self):
        # Test that function aligns weights with frame
        df = DataFrame({"col1": [5, 6, 7], "col2": ["a", "b", "c"]}, index=[9, 5, 3])
        ser = Series([1, 0, 0], index=[3, 5, 9])
        tm.assert_frame_equal(df.loc[[3]], df.sample(1, weights=ser))

        # Weights have index values to be dropped because not in
        # sampled DataFrame
        ser2 = Series([0.001, 0, 10000], index=[3, 5, 10])
        tm.assert_frame_equal(df.loc[[3]], df.sample(1, weights=ser2))

        # Weights have empty values to be filed with zeros
        ser3 = Series([0.01, 0], index=[3, 5])
        tm.assert_frame_equal(df.loc[[3]], df.sample(1, weights=ser3))

        # No overlap in weight and sampled DataFrame indices
        ser4 = Series([1, 0], index=[1, 2])

        with pytest.raises(ValueError, match="Invalid weights: weights sum to zero"):
            df.sample(1, weights=ser4)

    def test_sample_is_copy(self):
        # GH#27357, GH#30784: ensure the result of sample is an actual copy and
        # doesn't track the parent dataframe / doesn't give SettingWithCopy warnings
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=["a", "b", "c"]
        )
        df2 = df.sample(3)

        with tm.assert_produces_warning(None):
            df2["d"] = 1

    def test_sample_does_not_modify_weights(self):
        # GH-42843
        result = np.array([np.nan, 1, np.nan])
        expected = result.copy()
        ser = Series([1, 2, 3])

        # Test numpy array weights won't be modified in place
        ser.sample(weights=result)
        tm.assert_numpy_array_equal(result, expected)

        # Test DataFrame column won't be modified in place
        df = DataFrame({"values": [1, 1, 1], "weights": [1, np.nan, np.nan]})
        expected = df["weights"].copy()

        df.sample(frac=1.0, replace=True, weights="weights")
        result = df["weights"]
        tm.assert_series_equal(result, expected)

    def test_sample_ignore_index(self):
        # GH 38581
        df = DataFrame(
            {"col1": range(10, 20), "col2": range(20, 30), "colString": ["a"] * 10}
        )
        result = df.sample(3, ignore_index=True)
        expected_index = Index(range(3))
        tm.assert_index_equal(result.index, expected_index, exact=True)
