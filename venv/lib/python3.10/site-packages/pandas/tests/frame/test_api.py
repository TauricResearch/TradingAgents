from copy import deepcopy
import inspect
import pydoc

import numpy as np
import pytest

from pandas._config import using_string_dtype
from pandas._config.config import option_context

from pandas.compat import HAS_PYARROW

import pandas as pd
from pandas import (
    DataFrame,
    Series,
    date_range,
    timedelta_range,
)
import pandas._testing as tm


class TestDataFrameMisc:
    def test_getitem_pop_assign_name(self, float_frame):
        s = float_frame["A"]
        assert s.name == "A"

        s = float_frame.pop("A")
        assert s.name == "A"

        s = float_frame.loc[:, "B"]
        assert s.name == "B"

        s2 = s.loc[:]
        assert s2.name == "B"

    def test_get_axis(self, float_frame):
        f = float_frame
        assert f._get_axis_number(0) == 0
        assert f._get_axis_number(1) == 1
        assert f._get_axis_number("index") == 0
        assert f._get_axis_number("rows") == 0
        assert f._get_axis_number("columns") == 1

        assert f._get_axis_name(0) == "index"
        assert f._get_axis_name(1) == "columns"
        assert f._get_axis_name("index") == "index"
        assert f._get_axis_name("rows") == "index"
        assert f._get_axis_name("columns") == "columns"

        assert f._get_axis(0) is f.index
        assert f._get_axis(1) is f.columns

        with pytest.raises(ValueError, match="No axis named"):
            f._get_axis_number(2)

        with pytest.raises(ValueError, match="No axis.*foo"):
            f._get_axis_name("foo")

        with pytest.raises(ValueError, match="No axis.*None"):
            f._get_axis_name(None)

        with pytest.raises(ValueError, match="No axis named"):
            f._get_axis_number(None)

    def test_column_contains_raises(self, float_frame):
        with pytest.raises(TypeError, match="unhashable type: 'Index'"):
            float_frame.columns in float_frame

    def test_tab_completion(self):
        # DataFrame whose columns are identifiers shall have them in __dir__.
        df = DataFrame([list("abcd"), list("efgh")], columns=list("ABCD"))
        for key in list("ABCD"):
            assert key in dir(df)
        assert isinstance(df.__getitem__("A"), Series)

        # DataFrame whose first-level columns are identifiers shall have
        # them in __dir__.
        df = DataFrame(
            [list("abcd"), list("efgh")],
            columns=pd.MultiIndex.from_tuples(list(zip("ABCD", "EFGH"))),
        )
        for key in list("ABCD"):
            assert key in dir(df)
        for key in list("EFGH"):
            assert key not in dir(df)
        assert isinstance(df.__getitem__("A"), DataFrame)

    def test_display_max_dir_items(self):
        # display.max_dir_items increaes the number of columns that are in __dir__.
        columns = ["a" + str(i) for i in range(420)]
        values = [range(420), range(420)]
        df = DataFrame(values, columns=columns)

        # The default value for display.max_dir_items is 100
        assert "a99" in dir(df)
        assert "a100" not in dir(df)

        with option_context("display.max_dir_items", 300):
            df = DataFrame(values, columns=columns)
            assert "a299" in dir(df)
            assert "a300" not in dir(df)

        with option_context("display.max_dir_items", None):
            df = DataFrame(values, columns=columns)
            assert "a419" in dir(df)

    def test_not_hashable(self):
        empty_frame = DataFrame()

        df = DataFrame([1])
        msg = "unhashable type: 'DataFrame'"
        with pytest.raises(TypeError, match=msg):
            hash(df)
        with pytest.raises(TypeError, match=msg):
            hash(empty_frame)

    @pytest.mark.xfail(
        using_string_dtype() and HAS_PYARROW, reason="surrogates not allowed"
    )
    def test_column_name_contains_unicode_surrogate(self):
        # GH 25509
        colname = "\ud83d"
        df = DataFrame({colname: []})
        # this should not crash
        assert colname not in dir(df)
        assert df.columns[0] == colname

    def test_new_empty_index(self):
        df1 = DataFrame(np.random.default_rng(2).standard_normal((0, 3)))
        df2 = DataFrame(np.random.default_rng(2).standard_normal((0, 3)))
        df1.index.name = "foo"
        assert df2.index.name is None

    def test_get_agg_axis(self, float_frame):
        cols = float_frame._get_agg_axis(0)
        assert cols is float_frame.columns

        idx = float_frame._get_agg_axis(1)
        assert idx is float_frame.index

        msg = r"Axis must be 0 or 1 \(got 2\)"
        with pytest.raises(ValueError, match=msg):
            float_frame._get_agg_axis(2)

    def test_empty(self, float_frame, float_string_frame):
        empty_frame = DataFrame()
        assert empty_frame.empty

        assert not float_frame.empty
        assert not float_string_frame.empty

        # corner case
        df = DataFrame({"A": [1.0, 2.0, 3.0], "B": ["a", "b", "c"]}, index=np.arange(3))
        del df["A"]
        assert not df.empty

    def test_len(self, float_frame):
        assert len(float_frame) == len(float_frame.index)

        # single block corner case
        arr = float_frame[["A", "B"]].values
        expected = float_frame.reindex(columns=["A", "B"]).values
        tm.assert_almost_equal(arr, expected)

    def test_axis_aliases(self, float_frame):
        f = float_frame

        # reg name
        expected = f.sum(axis=0)
        result = f.sum(axis="index")
        tm.assert_series_equal(result, expected)

        expected = f.sum(axis=1)
        result = f.sum(axis="columns")
        tm.assert_series_equal(result, expected)

    def test_class_axis(self):
        # GH 18147
        # no exception and no empty docstring
        assert pydoc.getdoc(DataFrame.index)
        assert pydoc.getdoc(DataFrame.columns)

    def test_series_put_names(self, float_string_frame):
        series = float_string_frame._series
        for k, v in series.items():
            assert v.name == k

    def test_empty_nonzero(self):
        df = DataFrame([1, 2, 3])
        assert not df.empty
        df = DataFrame(index=[1], columns=[1])
        assert not df.empty
        df = DataFrame(index=["a", "b"], columns=["c", "d"]).dropna()
        assert df.empty
        assert df.T.empty

    @pytest.mark.parametrize(
        "df",
        [
            DataFrame(),
            DataFrame(index=[1]),
            DataFrame(columns=[1]),
            DataFrame({1: []}),
        ],
    )
    def test_empty_like(self, df):
        assert df.empty
        assert df.T.empty

    def test_with_datetimelikes(self):
        df = DataFrame(
            {
                "A": date_range("20130101", periods=10),
                "B": timedelta_range("1 day", periods=10),
            }
        )
        t = df.T

        result = t.dtypes.value_counts()
        expected = Series({np.dtype("object"): 10}, name="count")
        tm.assert_series_equal(result, expected)

    def test_deepcopy(self, float_frame):
        cp = deepcopy(float_frame)
        cp.loc[0, "A"] = 10
        assert not float_frame.equals(cp)

    def test_inplace_return_self(self):
        # GH 1893

        data = DataFrame(
            {"a": ["foo", "bar", "baz", "qux"], "b": [0, 0, 1, 1], "c": [1, 2, 3, 4]}
        )

        def _check_f(base, f):
            result = f(base)
            assert result is None

        # -----DataFrame-----

        # set_index
        f = lambda x: x.set_index("a", inplace=True)
        _check_f(data.copy(), f)

        # reset_index
        f = lambda x: x.reset_index(inplace=True)
        _check_f(data.set_index("a"), f)

        # drop_duplicates
        f = lambda x: x.drop_duplicates(inplace=True)
        _check_f(data.copy(), f)

        # sort
        f = lambda x: x.sort_values("b", inplace=True)
        _check_f(data.copy(), f)

        # sort_index
        f = lambda x: x.sort_index(inplace=True)
        _check_f(data.copy(), f)

        # fillna
        f = lambda x: x.fillna(0, inplace=True)
        _check_f(data.copy(), f)

        # replace
        f = lambda x: x.replace(1, 0, inplace=True)
        _check_f(data.copy(), f)

        # rename
        f = lambda x: x.rename({1: "foo"}, inplace=True)
        _check_f(data.copy(), f)

        # -----Series-----
        d = data.copy()["c"]

        # reset_index
        f = lambda x: x.reset_index(inplace=True, drop=True)
        _check_f(data.set_index("a")["c"], f)

        # fillna
        f = lambda x: x.fillna(0, inplace=True)
        _check_f(d.copy(), f)

        # replace
        f = lambda x: x.replace(1, 0, inplace=True)
        _check_f(d.copy(), f)

        # rename
        f = lambda x: x.rename({1: "foo"}, inplace=True)
        _check_f(d.copy(), f)

    def test_tab_complete_warning(self, ip, frame_or_series):
        # GH 16409
        pytest.importorskip("IPython", minversion="6.0.0")
        from IPython.core.completer import provisionalcompleter

        if frame_or_series is DataFrame:
            code = "from pandas import DataFrame; obj = DataFrame()"
        else:
            code = "from pandas import Series; obj = Series(dtype=object)"

        ip.run_cell(code)
        # GH 31324 newer jedi version raises Deprecation warning;
        #  appears resolved 2021-02-02
        with tm.assert_produces_warning(None, raise_on_extra_warnings=False):
            with provisionalcompleter("ignore"):
                list(ip.Completer.completions("obj.", 1))

    def test_attrs(self):
        df = DataFrame({"A": [2, 3]})
        assert df.attrs == {}
        df.attrs["version"] = 1

        result = df.rename(columns=str)
        assert result.attrs == {"version": 1}

    def test_attrs_deepcopy(self):
        df = DataFrame({"A": [2, 3]})
        assert df.attrs == {}
        df.attrs["tags"] = {"spam", "ham"}

        result = df.rename(columns=str)
        assert result.attrs == df.attrs
        assert result.attrs["tags"] is not df.attrs["tags"]

    @pytest.mark.parametrize("allows_duplicate_labels", [True, False, None])
    def test_set_flags(
        self,
        allows_duplicate_labels,
        frame_or_series,
        using_copy_on_write,
        warn_copy_on_write,
    ):
        obj = DataFrame({"A": [1, 2]})
        key = (0, 0)
        if frame_or_series is Series:
            obj = obj["A"]
            key = 0

        result = obj.set_flags(allows_duplicate_labels=allows_duplicate_labels)

        if allows_duplicate_labels is None:
            # We don't update when it's not provided
            assert result.flags.allows_duplicate_labels is True
        else:
            assert result.flags.allows_duplicate_labels is allows_duplicate_labels

        # We made a copy
        assert obj is not result

        # We didn't mutate obj
        assert obj.flags.allows_duplicate_labels is True

        # But we didn't copy data
        if frame_or_series is Series:
            assert np.may_share_memory(obj.values, result.values)
        else:
            assert np.may_share_memory(obj["A"].values, result["A"].values)

        with tm.assert_cow_warning(warn_copy_on_write):
            result.iloc[key] = 0
        if using_copy_on_write:
            assert obj.iloc[key] == 1
        else:
            assert obj.iloc[key] == 0
            # set back to 1 for test below
            with tm.assert_cow_warning(warn_copy_on_write):
                result.iloc[key] = 1

        # Now we do copy.
        result = obj.set_flags(
            copy=True, allows_duplicate_labels=allows_duplicate_labels
        )
        result.iloc[key] = 10
        assert obj.iloc[key] == 1

    def test_constructor_expanddim(self):
        # GH#33628 accessing _constructor_expanddim should not raise NotImplementedError
        # GH38782 pandas has no container higher than DataFrame (two-dim), so
        # DataFrame._constructor_expand_dim, doesn't make sense, so is removed.
        df = DataFrame()

        msg = "'DataFrame' object has no attribute '_constructor_expanddim'"
        with pytest.raises(AttributeError, match=msg):
            df._constructor_expanddim(np.arange(27).reshape(3, 3, 3))

    def test_inspect_getmembers(self):
        # GH38740
        df = DataFrame()
        msg = "DataFrame._data is deprecated"
        with tm.assert_produces_warning(
            DeprecationWarning, match=msg, check_stacklevel=False
        ):
            inspect.getmembers(df)
