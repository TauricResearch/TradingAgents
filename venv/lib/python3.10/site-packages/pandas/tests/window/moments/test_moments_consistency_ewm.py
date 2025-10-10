import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    concat,
)
import pandas._testing as tm


def create_mock_weights(obj, com, adjust, ignore_na):
    if isinstance(obj, DataFrame):
        if not len(obj.columns):
            return DataFrame(index=obj.index, columns=obj.columns)
        w = concat(
            [
                create_mock_series_weights(
                    obj.iloc[:, i], com=com, adjust=adjust, ignore_na=ignore_na
                )
                for i in range(len(obj.columns))
            ],
            axis=1,
        )
        w.index = obj.index
        w.columns = obj.columns
        return w
    else:
        return create_mock_series_weights(obj, com, adjust, ignore_na)


def create_mock_series_weights(s, com, adjust, ignore_na):
    w = Series(np.nan, index=s.index, name=s.name)
    alpha = 1.0 / (1.0 + com)
    if adjust:
        count = 0
        for i in range(len(s)):
            if s.iat[i] == s.iat[i]:
                w.iat[i] = pow(1.0 / (1.0 - alpha), count)
                count += 1
            elif not ignore_na:
                count += 1
    else:
        sum_wts = 0.0
        prev_i = -1
        count = 0
        for i in range(len(s)):
            if s.iat[i] == s.iat[i]:
                if prev_i == -1:
                    w.iat[i] = 1.0
                else:
                    w.iat[i] = alpha * sum_wts / pow(1.0 - alpha, count - prev_i)
                sum_wts += w.iat[i]
                prev_i = count
                count += 1
            elif not ignore_na:
                count += 1
    return w


def test_ewm_consistency_mean(all_data, adjust, ignore_na, min_periods):
    com = 3.0

    result = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).mean()
    weights = create_mock_weights(all_data, com=com, adjust=adjust, ignore_na=ignore_na)
    expected = all_data.multiply(weights).cumsum().divide(weights.cumsum()).ffill()
    expected[
        all_data.expanding().count() < (max(min_periods, 1) if min_periods else 1)
    ] = np.nan
    tm.assert_equal(result, expected.astype("float64"))


def test_ewm_consistency_consistent(consistent_data, adjust, ignore_na, min_periods):
    com = 3.0

    count_x = consistent_data.expanding().count()
    mean_x = consistent_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).mean()
    # check that correlation of a series with itself is either 1 or NaN
    corr_x_x = consistent_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).corr(consistent_data)
    exp = (
        consistent_data.max()
        if isinstance(consistent_data, Series)
        else consistent_data.max().max()
    )

    # check mean of constant series
    expected = consistent_data * np.nan
    expected[count_x >= max(min_periods, 1)] = exp
    tm.assert_equal(mean_x, expected)

    # check correlation of constant series with itself is NaN
    expected[:] = np.nan
    tm.assert_equal(corr_x_x, expected)


def test_ewm_consistency_var_debiasing_factors(
    all_data, adjust, ignore_na, min_periods
):
    com = 3.0

    # check variance debiasing factors
    var_unbiased_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=False)
    var_biased_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=True)

    weights = create_mock_weights(all_data, com=com, adjust=adjust, ignore_na=ignore_na)
    cum_sum = weights.cumsum().ffill()
    cum_sum_sq = (weights * weights).cumsum().ffill()
    numerator = cum_sum * cum_sum
    denominator = numerator - cum_sum_sq
    denominator[denominator <= 0.0] = np.nan
    var_debiasing_factors_x = numerator / denominator

    tm.assert_equal(var_unbiased_x, var_biased_x * var_debiasing_factors_x)


@pytest.mark.parametrize("bias", [True, False])
def test_moments_consistency_var(all_data, adjust, ignore_na, min_periods, bias):
    com = 3.0

    mean_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).mean()
    var_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=bias)
    assert not (var_x < 0).any().any()

    if bias:
        # check that biased var(x) == mean(x^2) - mean(x)^2
        mean_x2 = (
            (all_data * all_data)
            .ewm(com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na)
            .mean()
        )
        tm.assert_equal(var_x, mean_x2 - (mean_x * mean_x))


@pytest.mark.parametrize("bias", [True, False])
def test_moments_consistency_var_constant(
    consistent_data, adjust, ignore_na, min_periods, bias
):
    com = 3.0
    count_x = consistent_data.expanding(min_periods=min_periods).count()
    var_x = consistent_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=bias)

    # check that variance of constant series is identically 0
    assert not (var_x > 0).any().any()
    expected = consistent_data * np.nan
    expected[count_x >= max(min_periods, 1)] = 0.0
    if not bias:
        expected[count_x < 2] = np.nan
    tm.assert_equal(var_x, expected)


@pytest.mark.parametrize("bias", [True, False])
def test_ewm_consistency_std(all_data, adjust, ignore_na, min_periods, bias):
    com = 3.0
    var_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=bias)
    assert not (var_x < 0).any().any()

    std_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).std(bias=bias)
    assert not (std_x < 0).any().any()

    # check that var(x) == std(x)^2
    tm.assert_equal(var_x, std_x * std_x)

    cov_x_x = all_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).cov(all_data, bias=bias)
    assert not (cov_x_x < 0).any().any()

    # check that var(x) == cov(x, x)
    tm.assert_equal(var_x, cov_x_x)


@pytest.mark.parametrize("bias", [True, False])
def test_ewm_consistency_series_cov_corr(
    series_data, adjust, ignore_na, min_periods, bias
):
    com = 3.0

    var_x_plus_y = (
        (series_data + series_data)
        .ewm(com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na)
        .var(bias=bias)
    )
    var_x = series_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=bias)
    var_y = series_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).var(bias=bias)
    cov_x_y = series_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).cov(series_data, bias=bias)
    # check that cov(x, y) == (var(x+y) - var(x) -
    # var(y)) / 2
    tm.assert_equal(cov_x_y, 0.5 * (var_x_plus_y - var_x - var_y))

    # check that corr(x, y) == cov(x, y) / (std(x) *
    # std(y))
    corr_x_y = series_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).corr(series_data)
    std_x = series_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).std(bias=bias)
    std_y = series_data.ewm(
        com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
    ).std(bias=bias)
    tm.assert_equal(corr_x_y, cov_x_y / (std_x * std_y))

    if bias:
        # check that biased cov(x, y) == mean(x*y) -
        # mean(x)*mean(y)
        mean_x = series_data.ewm(
            com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
        ).mean()
        mean_y = series_data.ewm(
            com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na
        ).mean()
        mean_x_times_y = (
            (series_data * series_data)
            .ewm(com=com, min_periods=min_periods, adjust=adjust, ignore_na=ignore_na)
            .mean()
        )
        tm.assert_equal(cov_x_y, mean_x_times_y - (mean_x * mean_y))
