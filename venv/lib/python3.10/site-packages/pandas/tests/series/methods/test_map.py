from collections import (
    Counter,
    defaultdict,
)
from decimal import Decimal
import math

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    bdate_range,
    date_range,
    isna,
    timedelta_range,
)
import pandas._testing as tm


def test_series_map_box_timedelta():
    # GH#11349
    ser = Series(timedelta_range("1 day 1 s", periods=5, freq="h"))

    def f(x):
        return x.total_seconds()

    ser.map(f)


def test_map_callable(datetime_series):
    with np.errstate(all="ignore"):
        tm.assert_series_equal(datetime_series.map(np.sqrt), np.sqrt(datetime_series))

    # map function element-wise
    tm.assert_series_equal(datetime_series.map(math.exp), np.exp(datetime_series))

    # empty series
    s = Series(dtype=object, name="foo", index=Index([], name="bar"))
    rs = s.map(lambda x: x)
    tm.assert_series_equal(s, rs)

    # check all metadata (GH 9322)
    assert s is not rs
    assert s.index is rs.index
    assert s.dtype == rs.dtype
    assert s.name == rs.name

    # index but no data
    s = Series(index=[1, 2, 3], dtype=np.float64)
    rs = s.map(lambda x: x)
    tm.assert_series_equal(s, rs)


def test_map_same_length_inference_bug():
    s = Series([1, 2])

    def f(x):
        return (x, x + 1)

    s = Series([1, 2, 3])
    result = s.map(f)
    expected = Series([(1, 2), (2, 3), (3, 4)])
    tm.assert_series_equal(result, expected)

    s = Series(["foo,bar"])
    result = s.map(lambda x: x.split(","))
    expected = Series([("foo", "bar")])
    tm.assert_series_equal(result, expected)


def test_series_map_box_timestamps():
    # GH#2689, GH#2627
    ser = Series(date_range("1/1/2000", periods=3))

    def func(x):
        return (x.hour, x.day, x.month)

    result = ser.map(func)
    expected = Series([(0, 1, 1), (0, 2, 1), (0, 3, 1)])
    tm.assert_series_equal(result, expected)


def test_map_series_stringdtype(any_string_dtype, using_infer_string):
    # map test on StringDType, GH#40823
    ser1 = Series(
        data=["cat", "dog", "rabbit"],
        index=["id1", "id2", "id3"],
        dtype=any_string_dtype,
    )
    ser2 = Series(["id3", "id2", "id1", "id7000"], dtype=any_string_dtype)
    result = ser2.map(ser1)

    item = pd.NA
    if ser2.dtype == object:
        item = np.nan

    expected = Series(data=["rabbit", "dog", "cat", item], dtype=any_string_dtype)
    if using_infer_string and any_string_dtype == "object":
        expected = expected.astype("str")

    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "data, expected_dtype",
    [(["1-1", "1-1", np.nan], "category"), (["1-1", "1-2", np.nan], "str")],
)
def test_map_categorical_with_nan_values(data, expected_dtype):
    # GH 20714 bug fixed in: GH 24275
    def func(val):
        return val.split("-")[0]

    s = Series(data, dtype="category")

    result = s.map(func, na_action="ignore")
    expected = Series(["1", "1", np.nan], dtype=expected_dtype)
    tm.assert_series_equal(result, expected)


def test_map_empty_integer_series():
    # GH52384
    s = Series([], dtype=int)
    result = s.map(lambda x: x)
    tm.assert_series_equal(result, s)


def test_map_empty_integer_series_with_datetime_index():
    # GH 21245
    s = Series([], index=date_range(start="2018-01-01", periods=0), dtype=int)
    result = s.map(lambda x: x)
    tm.assert_series_equal(result, s)


@pytest.mark.parametrize("func", [str, lambda x: str(x)])
def test_map_simple_str_callables_same_as_astype(
    string_series, func, using_infer_string
):
    # test that we are evaluating row-by-row first
    # before vectorized evaluation
    result = string_series.map(func)
    expected = string_series.astype(str if not using_infer_string else "str")
    tm.assert_series_equal(result, expected)


def test_list_raises(string_series):
    with pytest.raises(TypeError, match="'list' object is not callable"):
        string_series.map([lambda x: x])


def test_map():
    data = {
        "A": [0.0, 1.0, 2.0, 3.0, 4.0],
        "B": [0.0, 1.0, 0.0, 1.0, 0.0],
        "C": ["foo1", "foo2", "foo3", "foo4", "foo5"],
        "D": bdate_range("1/1/2009", periods=5),
    }

    source = Series(data["B"], index=data["C"])
    target = Series(data["C"][:4], index=data["D"][:4])

    merged = target.map(source)

    for k, v in merged.items():
        assert v == source[target[k]]

    # input could be a dict
    merged = target.map(source.to_dict())

    for k, v in merged.items():
        assert v == source[target[k]]


def test_map_datetime(datetime_series):
    # function
    result = datetime_series.map(lambda x: x * 2)
    tm.assert_series_equal(result, datetime_series * 2)


def test_map_category():
    # GH 10324
    a = Series([1, 2, 3, 4])
    b = Series(["even", "odd", "even", "odd"], dtype="category")
    c = Series(["even", "odd", "even", "odd"])

    exp = Series(["odd", "even", "odd", np.nan], dtype="category")
    tm.assert_series_equal(a.map(b), exp)
    exp = Series(["odd", "even", "odd", np.nan])
    tm.assert_series_equal(a.map(c), exp)


def test_map_category_numeric():
    a = Series(["a", "b", "c", "d"])
    b = Series([1, 2, 3, 4], index=pd.CategoricalIndex(["b", "c", "d", "e"]))
    c = Series([1, 2, 3, 4], index=Index(["b", "c", "d", "e"]))

    exp = Series([np.nan, 1, 2, 3])
    tm.assert_series_equal(a.map(b), exp)
    exp = Series([np.nan, 1, 2, 3])
    tm.assert_series_equal(a.map(c), exp)


def test_map_category_string():
    a = Series(["a", "b", "c", "d"])
    b = Series(
        ["B", "C", "D", "E"],
        dtype="category",
        index=pd.CategoricalIndex(["b", "c", "d", "e"]),
    )
    c = Series(["B", "C", "D", "E"], index=Index(["b", "c", "d", "e"]))

    exp = Series(
        pd.Categorical([np.nan, "B", "C", "D"], categories=["B", "C", "D", "E"])
    )
    tm.assert_series_equal(a.map(b), exp)
    exp = Series([np.nan, "B", "C", "D"])
    tm.assert_series_equal(a.map(c), exp)


@pytest.mark.filterwarnings(r"ignore:Dtype inference:FutureWarning")
def test_map_empty(request, index):
    if isinstance(index, MultiIndex):
        request.applymarker(
            pytest.mark.xfail(
                reason="Initializing a Series from a MultiIndex is not supported"
            )
        )

    s = Series(index)
    result = s.map({})

    expected = Series(np.nan, index=s.index)
    tm.assert_series_equal(result, expected)


def test_map_compat():
    # related GH 8024
    s = Series([True, True, False], index=[1, 2, 3])
    result = s.map({True: "foo", False: "bar"})
    expected = Series(["foo", "foo", "bar"], index=[1, 2, 3])
    tm.assert_series_equal(result, expected)


def test_map_int():
    left = Series({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4})
    right = Series({1: 11, 2: 22, 3: 33})

    assert left.dtype == np.float64
    assert issubclass(right.dtype.type, np.integer)

    merged = left.map(right)
    assert merged.dtype == np.float64
    assert isna(merged["d"])
    assert not isna(merged["c"])


def test_map_type_inference():
    s = Series(range(3))
    s2 = s.map(lambda x: np.where(x == 0, 0, 1))
    assert issubclass(s2.dtype.type, np.integer)


def test_map_decimal(string_series):
    result = string_series.map(lambda x: Decimal(str(x)))
    assert result.dtype == np.object_
    assert isinstance(result.iloc[0], Decimal)


def test_map_na_exclusion():
    s = Series([1.5, np.nan, 3, np.nan, 5])

    result = s.map(lambda x: x * 2, na_action="ignore")
    exp = s * 2
    tm.assert_series_equal(result, exp)


def test_map_dict_with_tuple_keys():
    """
    Due to new MultiIndex-ing behaviour in v0.14.0,
    dicts with tuple keys passed to map were being
    converted to a multi-index, preventing tuple values
    from being mapped properly.
    """
    # GH 18496
    df = DataFrame({"a": [(1,), (2,), (3, 4), (5, 6)]})
    label_mappings = {(1,): "A", (2,): "B", (3, 4): "A", (5, 6): "B"}

    df["labels"] = df["a"].map(label_mappings)
    df["expected_labels"] = Series(["A", "B", "A", "B"], index=df.index)
    # All labels should be filled now
    tm.assert_series_equal(df["labels"], df["expected_labels"], check_names=False)


def test_map_counter():
    s = Series(["a", "b", "c"], index=[1, 2, 3])
    counter = Counter()
    counter["b"] = 5
    counter["c"] += 1
    result = s.map(counter)
    expected = Series([0, 5, 1], index=[1, 2, 3])
    tm.assert_series_equal(result, expected)


def test_map_defaultdict():
    s = Series([1, 2, 3], index=["a", "b", "c"])
    default_dict = defaultdict(lambda: "blank")
    default_dict[1] = "stuff"
    result = s.map(default_dict)
    expected = Series(["stuff", "blank", "blank"], index=["a", "b", "c"])
    tm.assert_series_equal(result, expected)


def test_map_dict_na_key():
    # https://github.com/pandas-dev/pandas/issues/17648
    # Checks that np.nan key is appropriately mapped
    s = Series([1, 2, np.nan])
    expected = Series(["a", "b", "c"])
    result = s.map({1: "a", 2: "b", np.nan: "c"})
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("na_action", [None, "ignore"])
def test_map_defaultdict_na_key(na_action):
    # GH 48813
    s = Series([1, 2, np.nan])
    default_map = defaultdict(lambda: "missing", {1: "a", 2: "b", np.nan: "c"})
    result = s.map(default_map, na_action=na_action)
    expected = Series({0: "a", 1: "b", 2: "c" if na_action is None else np.nan})
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("na_action", [None, "ignore"])
def test_map_defaultdict_missing_key(na_action):
    # GH 48813
    s = Series([1, 2, np.nan])
    default_map = defaultdict(lambda: "missing", {1: "a", 2: "b", 3: "c"})
    result = s.map(default_map, na_action=na_action)
    expected = Series({0: "a", 1: "b", 2: "missing" if na_action is None else np.nan})
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("na_action", [None, "ignore"])
def test_map_defaultdict_unmutated(na_action):
    # GH 48813
    s = Series([1, 2, np.nan])
    default_map = defaultdict(lambda: "missing", {1: "a", 2: "b", np.nan: "c"})
    expected_default_map = default_map.copy()
    s.map(default_map, na_action=na_action)
    assert default_map == expected_default_map


@pytest.mark.parametrize("arg_func", [dict, Series])
def test_map_dict_ignore_na(arg_func):
    # GH#47527
    mapping = arg_func({1: 10, np.nan: 42})
    ser = Series([1, np.nan, 2])
    result = ser.map(mapping, na_action="ignore")
    expected = Series([10, np.nan, np.nan])
    tm.assert_series_equal(result, expected)


def test_map_defaultdict_ignore_na():
    # GH#47527
    mapping = defaultdict(int, {1: 10, np.nan: 42})
    ser = Series([1, np.nan, 2])
    result = ser.map(mapping)
    expected = Series([10, 42, 0])
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "na_action, expected",
    [(None, Series([10.0, 42.0, np.nan])), ("ignore", Series([10, np.nan, np.nan]))],
)
def test_map_categorical_na_ignore(na_action, expected):
    # GH#47527
    values = pd.Categorical([1, np.nan, 2], categories=[10, 1, 2])
    ser = Series(values)
    result = ser.map({1: 10, np.nan: 42}, na_action=na_action)
    tm.assert_series_equal(result, expected)


def test_map_dict_subclass_with_missing():
    """
    Test Series.map with a dictionary subclass that defines __missing__,
    i.e. sets a default value (GH #15999).
    """

    class DictWithMissing(dict):
        def __missing__(self, key):
            return "missing"

    s = Series([1, 2, 3])
    dictionary = DictWithMissing({3: "three"})
    result = s.map(dictionary)
    expected = Series(["missing", "missing", "three"])
    tm.assert_series_equal(result, expected)


def test_map_dict_subclass_without_missing():
    class DictWithoutMissing(dict):
        pass

    s = Series([1, 2, 3])
    dictionary = DictWithoutMissing({3: "three"})
    result = s.map(dictionary)
    expected = Series([np.nan, np.nan, "three"])
    tm.assert_series_equal(result, expected)


def test_map_abc_mapping(non_dict_mapping_subclass):
    # https://github.com/pandas-dev/pandas/issues/29733
    # Check collections.abc.Mapping support as mapper for Series.map
    s = Series([1, 2, 3])
    not_a_dictionary = non_dict_mapping_subclass({3: "three"})
    result = s.map(not_a_dictionary)
    expected = Series([np.nan, np.nan, "three"])
    tm.assert_series_equal(result, expected)


def test_map_abc_mapping_with_missing(non_dict_mapping_subclass):
    # https://github.com/pandas-dev/pandas/issues/29733
    # Check collections.abc.Mapping support as mapper for Series.map
    class NonDictMappingWithMissing(non_dict_mapping_subclass):
        def __missing__(self, key):
            return "missing"

    s = Series([1, 2, 3])
    not_a_dictionary = NonDictMappingWithMissing({3: "three"})
    result = s.map(not_a_dictionary)
    # __missing__ is a dict concept, not a Mapping concept,
    # so it should not change the result!
    expected = Series([np.nan, np.nan, "three"])
    tm.assert_series_equal(result, expected)


def test_map_box_dt64(unit):
    vals = [pd.Timestamp("2011-01-01"), pd.Timestamp("2011-01-02")]
    ser = Series(vals).dt.as_unit(unit)
    assert ser.dtype == f"datetime64[{unit}]"
    # boxed value must be Timestamp instance
    res = ser.map(lambda x: f"{type(x).__name__}_{x.day}_{x.tz}")
    exp = Series(["Timestamp_1_None", "Timestamp_2_None"])
    tm.assert_series_equal(res, exp)


def test_map_box_dt64tz(unit):
    vals = [
        pd.Timestamp("2011-01-01", tz="US/Eastern"),
        pd.Timestamp("2011-01-02", tz="US/Eastern"),
    ]
    ser = Series(vals).dt.as_unit(unit)
    assert ser.dtype == f"datetime64[{unit}, US/Eastern]"
    res = ser.map(lambda x: f"{type(x).__name__}_{x.day}_{x.tz}")
    exp = Series(["Timestamp_1_US/Eastern", "Timestamp_2_US/Eastern"])
    tm.assert_series_equal(res, exp)


def test_map_box_td64(unit):
    # timedelta
    vals = [pd.Timedelta("1 days"), pd.Timedelta("2 days")]
    ser = Series(vals).dt.as_unit(unit)
    assert ser.dtype == f"timedelta64[{unit}]"
    res = ser.map(lambda x: f"{type(x).__name__}_{x.days}")
    exp = Series(["Timedelta_1", "Timedelta_2"])
    tm.assert_series_equal(res, exp)


def test_map_box_period():
    # period
    vals = [pd.Period("2011-01-01", freq="M"), pd.Period("2011-01-02", freq="M")]
    ser = Series(vals)
    assert ser.dtype == "Period[M]"
    res = ser.map(lambda x: f"{type(x).__name__}_{x.freqstr}")
    exp = Series(["Period_M", "Period_M"])
    tm.assert_series_equal(res, exp)


@pytest.mark.parametrize("na_action", [None, "ignore"])
def test_map_categorical(na_action, using_infer_string):
    values = pd.Categorical(list("ABBABCD"), categories=list("DCBA"), ordered=True)
    s = Series(values, name="XX", index=list("abcdefg"))

    result = s.map(lambda x: x.lower(), na_action=na_action)
    exp_values = pd.Categorical(list("abbabcd"), categories=list("dcba"), ordered=True)
    exp = Series(exp_values, name="XX", index=list("abcdefg"))
    tm.assert_series_equal(result, exp)
    tm.assert_categorical_equal(result.values, exp_values)

    result = s.map(lambda x: "A", na_action=na_action)
    exp = Series(["A"] * 7, name="XX", index=list("abcdefg"))
    tm.assert_series_equal(result, exp)
    assert result.dtype == object if not using_infer_string else "str"


@pytest.mark.parametrize(
    "na_action, expected",
    (
        [None, Series(["A", "B", "nan"], name="XX")],
        [
            "ignore",
            Series(
                ["A", "B", np.nan],
                name="XX",
                dtype=pd.CategoricalDtype(list("DCBA"), True),
            ),
        ],
    ),
)
def test_map_categorical_na_action(na_action, expected):
    dtype = pd.CategoricalDtype(list("DCBA"), ordered=True)
    values = pd.Categorical(list("AB") + [np.nan], dtype=dtype)
    s = Series(values, name="XX")
    result = s.map(str, na_action=na_action)
    tm.assert_series_equal(result, expected)


def test_map_datetimetz():
    values = date_range("2011-01-01", "2011-01-02", freq="h").tz_localize("Asia/Tokyo")
    s = Series(values, name="XX")

    # keep tz
    result = s.map(lambda x: x + pd.offsets.Day())
    exp_values = date_range("2011-01-02", "2011-01-03", freq="h").tz_localize(
        "Asia/Tokyo"
    )
    exp = Series(exp_values, name="XX")
    tm.assert_series_equal(result, exp)

    result = s.map(lambda x: x.hour)
    exp = Series(list(range(24)) + [0], name="XX", dtype=np.int64)
    tm.assert_series_equal(result, exp)

    # not vectorized
    def f(x):
        if not isinstance(x, pd.Timestamp):
            raise ValueError
        return str(x.tz)

    result = s.map(f)
    exp = Series(["Asia/Tokyo"] * 25, name="XX")
    tm.assert_series_equal(result, exp)


@pytest.mark.parametrize(
    "vals,mapping,exp",
    [
        (list("abc"), {np.nan: "not NaN"}, [np.nan] * 3 + ["not NaN"]),
        (list("abc"), {"a": "a letter"}, ["a letter"] + [np.nan] * 3),
        (list(range(3)), {0: 42}, [42] + [np.nan] * 3),
    ],
)
def test_map_missing_mixed(vals, mapping, exp):
    # GH20495
    s = Series(vals + [np.nan])
    result = s.map(mapping)
    exp = Series(exp)
    tm.assert_series_equal(result, exp)


def test_map_scalar_on_date_time_index_aware_series():
    # GH 25959
    # Calling map on a localized time series should not cause an error
    series = Series(
        np.arange(10, dtype=np.float64),
        index=date_range("2020-01-01", periods=10, tz="UTC"),
        name="ts",
    )
    result = Series(series.index).map(lambda x: 1)
    tm.assert_series_equal(result, Series(np.ones(len(series)), dtype="int64"))


def test_map_float_to_string_precision():
    # GH 13228
    ser = Series(1 / 3)
    result = ser.map(lambda val: str(val)).to_dict()
    expected = {0: "0.3333333333333333"}
    assert result == expected


def test_map_to_timedelta():
    list_of_valid_strings = ["00:00:01", "00:00:02"]
    a = pd.to_timedelta(list_of_valid_strings)
    b = Series(list_of_valid_strings).map(pd.to_timedelta)
    tm.assert_series_equal(Series(a), b)

    list_of_strings = ["00:00:01", np.nan, pd.NaT, pd.NaT]

    a = pd.to_timedelta(list_of_strings)
    ser = Series(list_of_strings)
    b = ser.map(pd.to_timedelta)
    tm.assert_series_equal(Series(a), b)


def test_map_type():
    # GH 46719
    s = Series([3, "string", float], index=["a", "b", "c"])
    result = s.map(type)
    expected = Series([int, str, type], index=["a", "b", "c"])
    tm.assert_series_equal(result, expected)
