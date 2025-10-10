import numpy as np
import pytest

from pandas import Series
import pandas._testing as tm


def no_nans(x):
    return x.notna().all().all()


def all_na(x):
    return x.isnull().all().all()


@pytest.fixture(params=[(1, 0), (5, 1)])
def rolling_consistency_cases(request):
    """window, min_periods"""
    return request.param


@pytest.mark.parametrize("f", [lambda v: Series(v).sum(), np.nansum, np.sum])
def test_rolling_apply_consistency_sum(
    request, all_data, rolling_consistency_cases, center, f
):
    window, min_periods = rolling_consistency_cases

    if f is np.sum:
        if not no_nans(all_data) and not (
            all_na(all_data) and not all_data.empty and min_periods > 0
        ):
            request.applymarker(
                pytest.mark.xfail(reason="np.sum has different behavior with NaNs")
            )
    rolling_f_result = all_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).sum()
    rolling_apply_f_result = all_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).apply(func=f, raw=True)
    tm.assert_equal(rolling_f_result, rolling_apply_f_result)


@pytest.mark.parametrize("ddof", [0, 1])
def test_moments_consistency_var(all_data, rolling_consistency_cases, center, ddof):
    window, min_periods = rolling_consistency_cases

    var_x = all_data.rolling(window=window, min_periods=min_periods, center=center).var(
        ddof=ddof
    )
    assert not (var_x < 0).any().any()

    if ddof == 0:
        # check that biased var(x) == mean(x^2) - mean(x)^2
        mean_x = all_data.rolling(
            window=window, min_periods=min_periods, center=center
        ).mean()
        mean_x2 = (
            (all_data * all_data)
            .rolling(window=window, min_periods=min_periods, center=center)
            .mean()
        )
        tm.assert_equal(var_x, mean_x2 - (mean_x * mean_x))


@pytest.mark.parametrize("ddof", [0, 1])
def test_moments_consistency_var_constant(
    consistent_data, rolling_consistency_cases, center, ddof
):
    window, min_periods = rolling_consistency_cases

    count_x = consistent_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).count()
    var_x = consistent_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).var(ddof=ddof)

    # check that variance of constant series is identically 0
    assert not (var_x > 0).any().any()
    expected = consistent_data * np.nan
    expected[count_x >= max(min_periods, 1)] = 0.0
    if ddof == 1:
        expected[count_x < 2] = np.nan
    tm.assert_equal(var_x, expected)


@pytest.mark.parametrize("ddof", [0, 1])
def test_rolling_consistency_var_std_cov(
    all_data, rolling_consistency_cases, center, ddof
):
    window, min_periods = rolling_consistency_cases

    var_x = all_data.rolling(window=window, min_periods=min_periods, center=center).var(
        ddof=ddof
    )
    assert not (var_x < 0).any().any()

    std_x = all_data.rolling(window=window, min_periods=min_periods, center=center).std(
        ddof=ddof
    )
    assert not (std_x < 0).any().any()

    # check that var(x) == std(x)^2
    tm.assert_equal(var_x, std_x * std_x)

    cov_x_x = all_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).cov(all_data, ddof=ddof)
    assert not (cov_x_x < 0).any().any()

    # check that var(x) == cov(x, x)
    tm.assert_equal(var_x, cov_x_x)


@pytest.mark.parametrize("ddof", [0, 1])
def test_rolling_consistency_series_cov_corr(
    series_data, rolling_consistency_cases, center, ddof
):
    window, min_periods = rolling_consistency_cases

    var_x_plus_y = (
        (series_data + series_data)
        .rolling(window=window, min_periods=min_periods, center=center)
        .var(ddof=ddof)
    )
    var_x = series_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).var(ddof=ddof)
    var_y = series_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).var(ddof=ddof)
    cov_x_y = series_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).cov(series_data, ddof=ddof)
    # check that cov(x, y) == (var(x+y) - var(x) -
    # var(y)) / 2
    tm.assert_equal(cov_x_y, 0.5 * (var_x_plus_y - var_x - var_y))

    # check that corr(x, y) == cov(x, y) / (std(x) *
    # std(y))
    corr_x_y = series_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).corr(series_data)
    std_x = series_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).std(ddof=ddof)
    std_y = series_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).std(ddof=ddof)
    tm.assert_equal(corr_x_y, cov_x_y / (std_x * std_y))

    if ddof == 0:
        # check that biased cov(x, y) == mean(x*y) -
        # mean(x)*mean(y)
        mean_x = series_data.rolling(
            window=window, min_periods=min_periods, center=center
        ).mean()
        mean_y = series_data.rolling(
            window=window, min_periods=min_periods, center=center
        ).mean()
        mean_x_times_y = (
            (series_data * series_data)
            .rolling(window=window, min_periods=min_periods, center=center)
            .mean()
        )
        tm.assert_equal(cov_x_y, mean_x_times_y - (mean_x * mean_y))


def test_rolling_consistency_mean(all_data, rolling_consistency_cases, center):
    window, min_periods = rolling_consistency_cases

    result = all_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).mean()
    expected = (
        all_data.rolling(window=window, min_periods=min_periods, center=center)
        .sum()
        .divide(
            all_data.rolling(
                window=window, min_periods=min_periods, center=center
            ).count()
        )
    )
    tm.assert_equal(result, expected.astype("float64"))


def test_rolling_consistency_constant(
    consistent_data, rolling_consistency_cases, center
):
    window, min_periods = rolling_consistency_cases

    count_x = consistent_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).count()
    mean_x = consistent_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).mean()
    # check that correlation of a series with itself is either 1 or NaN
    corr_x_x = consistent_data.rolling(
        window=window, min_periods=min_periods, center=center
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


def test_rolling_consistency_var_debiasing_factors(
    all_data, rolling_consistency_cases, center
):
    window, min_periods = rolling_consistency_cases

    # check variance debiasing factors
    var_unbiased_x = all_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).var()
    var_biased_x = all_data.rolling(
        window=window, min_periods=min_periods, center=center
    ).var(ddof=0)
    var_debiasing_factors_x = (
        all_data.rolling(window=window, min_periods=min_periods, center=center)
        .count()
        .divide(
            (
                all_data.rolling(
                    window=window, min_periods=min_periods, center=center
                ).count()
                - 1.0
            ).replace(0.0, np.nan)
        )
    )
    tm.assert_equal(var_unbiased_x, var_biased_x * var_debiasing_factors_x)
