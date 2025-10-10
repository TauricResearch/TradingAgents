import numpy as np
import pytest

import pandas as pd


@pytest.fixture
def data():
    """Fixture returning boolean array, with valid and missing values."""
    return pd.array(
        [True, False] * 4 + [np.nan] + [True, False] * 44 + [np.nan] + [True, False],
        dtype="boolean",
    )


@pytest.mark.parametrize(
    "values, exp_any, exp_all, exp_any_noskip, exp_all_noskip",
    [
        ([True, pd.NA], True, True, True, pd.NA),
        ([False, pd.NA], False, False, pd.NA, False),
        ([pd.NA], False, True, pd.NA, pd.NA),
        ([], False, True, False, True),
        # GH-33253: all True / all False values buggy with skipna=False
        ([True, True], True, True, True, True),
        ([False, False], False, False, False, False),
    ],
)
def test_any_all(values, exp_any, exp_all, exp_any_noskip, exp_all_noskip):
    # the methods return numpy scalars
    exp_any = pd.NA if exp_any is pd.NA else np.bool_(exp_any)
    exp_all = pd.NA if exp_all is pd.NA else np.bool_(exp_all)
    exp_any_noskip = pd.NA if exp_any_noskip is pd.NA else np.bool_(exp_any_noskip)
    exp_all_noskip = pd.NA if exp_all_noskip is pd.NA else np.bool_(exp_all_noskip)

    for con in [pd.array, pd.Series]:
        a = con(values, dtype="boolean")
        assert a.any() is exp_any
        assert a.all() is exp_all
        assert a.any(skipna=False) is exp_any_noskip
        assert a.all(skipna=False) is exp_all_noskip

        assert np.any(a.any()) is exp_any
        assert np.all(a.all()) is exp_all


@pytest.mark.parametrize("dropna", [True, False])
def test_reductions_return_types(dropna, data, all_numeric_reductions):
    op = all_numeric_reductions
    s = pd.Series(data)
    if dropna:
        s = s.dropna()

    if op in ("sum", "prod"):
        assert isinstance(getattr(s, op)(), np.int_)
    elif op == "count":
        # Oddly on the 32 bit build (but not Windows), this is intc (!= intp)
        assert isinstance(getattr(s, op)(), np.integer)
    elif op in ("min", "max"):
        assert isinstance(getattr(s, op)(), np.bool_)
    else:
        # "mean", "std", "var", "median", "kurt", "skew"
        assert isinstance(getattr(s, op)(), np.float64)
