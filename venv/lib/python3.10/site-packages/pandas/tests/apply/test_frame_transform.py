import numpy as np
import pytest

from pandas import (
    DataFrame,
    MultiIndex,
    Series,
)
import pandas._testing as tm
from pandas.tests.apply.common import frame_transform_kernels
from pandas.tests.frame.common import zip_frames


def unpack_obj(obj, klass, axis):
    """
    Helper to ensure we have the right type of object for a test parametrized
    over frame_or_series.
    """
    if klass is not DataFrame:
        obj = obj["A"]
        if axis != 0:
            pytest.skip(f"Test is only for DataFrame with axis={axis}")
    return obj


def test_transform_ufunc(axis, float_frame, frame_or_series):
    # GH 35964
    obj = unpack_obj(float_frame, frame_or_series, axis)

    with np.errstate(all="ignore"):
        f_sqrt = np.sqrt(obj)

    # ufunc
    result = obj.transform(np.sqrt, axis=axis)
    expected = f_sqrt
    tm.assert_equal(result, expected)


@pytest.mark.parametrize(
    "ops, names",
    [
        ([np.sqrt], ["sqrt"]),
        ([np.abs, np.sqrt], ["absolute", "sqrt"]),
        (np.array([np.sqrt]), ["sqrt"]),
        (np.array([np.abs, np.sqrt]), ["absolute", "sqrt"]),
    ],
)
def test_transform_listlike(axis, float_frame, ops, names):
    # GH 35964
    other_axis = 1 if axis in {0, "index"} else 0
    with np.errstate(all="ignore"):
        expected = zip_frames([op(float_frame) for op in ops], axis=other_axis)
    if axis in {0, "index"}:
        expected.columns = MultiIndex.from_product([float_frame.columns, names])
    else:
        expected.index = MultiIndex.from_product([float_frame.index, names])
    result = float_frame.transform(ops, axis=axis)
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("ops", [[], np.array([])])
def test_transform_empty_listlike(float_frame, ops, frame_or_series):
    obj = unpack_obj(float_frame, frame_or_series, 0)

    with pytest.raises(ValueError, match="No transform functions were provided"):
        obj.transform(ops)


def test_transform_listlike_func_with_args():
    # GH 50624
    df = DataFrame({"x": [1, 2, 3]})

    def foo1(x, a=1, c=0):
        return x + a + c

    def foo2(x, b=2, c=0):
        return x + b + c

    msg = r"foo1\(\) got an unexpected keyword argument 'b'"
    with pytest.raises(TypeError, match=msg):
        df.transform([foo1, foo2], 0, 3, b=3, c=4)

    result = df.transform([foo1, foo2], 0, 3, c=4)
    expected = DataFrame(
        [[8, 8], [9, 9], [10, 10]],
        columns=MultiIndex.from_tuples([("x", "foo1"), ("x", "foo2")]),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("box", [dict, Series])
def test_transform_dictlike(axis, float_frame, box):
    # GH 35964
    if axis in (0, "index"):
        e = float_frame.columns[0]
        expected = float_frame[[e]].transform(np.abs)
    else:
        e = float_frame.index[0]
        expected = float_frame.iloc[[0]].transform(np.abs)
    result = float_frame.transform(box({e: np.abs}), axis=axis)
    tm.assert_frame_equal(result, expected)


def test_transform_dictlike_mixed():
    # GH 40018 - mix of lists and non-lists in values of a dictionary
    df = DataFrame({"a": [1, 2], "b": [1, 4], "c": [1, 4]})
    result = df.transform({"b": ["sqrt", "abs"], "c": "sqrt"})
    expected = DataFrame(
        [[1.0, 1, 1.0], [2.0, 4, 2.0]],
        columns=MultiIndex([("b", "c"), ("sqrt", "abs")], [(0, 0, 1), (0, 1, 0)]),
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "ops",
    [
        {},
        {"A": []},
        {"A": [], "B": "cumsum"},
        {"A": "cumsum", "B": []},
        {"A": [], "B": ["cumsum"]},
        {"A": ["cumsum"], "B": []},
    ],
)
def test_transform_empty_dictlike(float_frame, ops, frame_or_series):
    obj = unpack_obj(float_frame, frame_or_series, 0)

    with pytest.raises(ValueError, match="No transform functions were provided"):
        obj.transform(ops)


@pytest.mark.parametrize("use_apply", [True, False])
def test_transform_udf(axis, float_frame, use_apply, frame_or_series):
    # GH 35964
    obj = unpack_obj(float_frame, frame_or_series, axis)

    # transform uses UDF either via apply or passing the entire DataFrame
    def func(x):
        # transform is using apply iff x is not a DataFrame
        if use_apply == isinstance(x, frame_or_series):
            # Force transform to fallback
            raise ValueError
        return x + 1

    result = obj.transform(func, axis=axis)
    expected = obj + 1
    tm.assert_equal(result, expected)


wont_fail = ["ffill", "bfill", "fillna", "pad", "backfill", "shift"]
frame_kernels_raise = [x for x in frame_transform_kernels if x not in wont_fail]


@pytest.mark.parametrize("op", [*frame_kernels_raise, lambda x: x + 1])
def test_transform_bad_dtype(op, frame_or_series, request):
    # GH 35964
    if op == "ngroup":
        request.applymarker(
            pytest.mark.xfail(raises=ValueError, reason="ngroup not valid for NDFrame")
        )

    obj = DataFrame({"A": 3 * [object]})  # DataFrame that will fail on most transforms
    obj = tm.get_obj(obj, frame_or_series)
    error = TypeError
    msg = "|".join(
        [
            "not supported between instances of 'type' and 'type'",
            "unsupported operand type",
        ]
    )

    with pytest.raises(error, match=msg):
        obj.transform(op)
    with pytest.raises(error, match=msg):
        obj.transform([op])
    with pytest.raises(error, match=msg):
        obj.transform({"A": op})
    with pytest.raises(error, match=msg):
        obj.transform({"A": [op]})


@pytest.mark.parametrize("op", frame_kernels_raise)
def test_transform_failure_typeerror(request, op):
    # GH 35964

    if op == "ngroup":
        request.applymarker(
            pytest.mark.xfail(raises=ValueError, reason="ngroup not valid for NDFrame")
        )

    # Using object makes most transform kernels fail
    df = DataFrame({"A": 3 * [object], "B": [1, 2, 3]})
    error = TypeError
    msg = "|".join(
        [
            "not supported between instances of 'type' and 'type'",
            "unsupported operand type",
        ]
    )

    with pytest.raises(error, match=msg):
        df.transform([op])

    with pytest.raises(error, match=msg):
        df.transform({"A": op, "B": op})

    with pytest.raises(error, match=msg):
        df.transform({"A": [op], "B": [op]})

    with pytest.raises(error, match=msg):
        df.transform({"A": [op, "shift"], "B": [op]})


def test_transform_failure_valueerror():
    # GH 40211
    def op(x):
        if np.sum(np.sum(x)) < 10:
            raise ValueError
        return x

    df = DataFrame({"A": [1, 2, 3], "B": [400, 500, 600]})
    msg = "Transform function failed"

    with pytest.raises(ValueError, match=msg):
        df.transform([op])

    with pytest.raises(ValueError, match=msg):
        df.transform({"A": op, "B": op})

    with pytest.raises(ValueError, match=msg):
        df.transform({"A": [op], "B": [op]})

    with pytest.raises(ValueError, match=msg):
        df.transform({"A": [op, "shift"], "B": [op]})


@pytest.mark.parametrize("use_apply", [True, False])
def test_transform_passes_args(use_apply, frame_or_series):
    # GH 35964
    # transform uses UDF either via apply or passing the entire DataFrame
    expected_args = [1, 2]
    expected_kwargs = {"c": 3}

    def f(x, a, b, c):
        # transform is using apply iff x is not a DataFrame
        if use_apply == isinstance(x, frame_or_series):
            # Force transform to fallback
            raise ValueError
        assert [a, b] == expected_args
        assert c == expected_kwargs["c"]
        return x

    frame_or_series([1]).transform(f, 0, *expected_args, **expected_kwargs)


def test_transform_empty_dataframe():
    # https://github.com/pandas-dev/pandas/issues/39636
    df = DataFrame([], columns=["col1", "col2"])
    result = df.transform(lambda x: x + 10)
    tm.assert_frame_equal(result, df)

    result = df["col1"].transform(lambda x: x + 10)
    tm.assert_series_equal(result, df["col1"])
