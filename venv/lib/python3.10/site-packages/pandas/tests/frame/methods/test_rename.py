from collections import ChainMap
import inspect

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    merge,
)
import pandas._testing as tm


class TestRename:
    def test_rename_signature(self):
        sig = inspect.signature(DataFrame.rename)
        parameters = set(sig.parameters)
        assert parameters == {
            "self",
            "mapper",
            "index",
            "columns",
            "axis",
            "inplace",
            "copy",
            "level",
            "errors",
        }

    def test_rename_mi(self, frame_or_series):
        obj = frame_or_series(
            [11, 21, 31],
            index=MultiIndex.from_tuples([("A", x) for x in ["a", "B", "c"]]),
        )
        obj.rename(str.lower)

    def test_rename(self, float_frame):
        mapping = {"A": "a", "B": "b", "C": "c", "D": "d"}

        renamed = float_frame.rename(columns=mapping)
        renamed2 = float_frame.rename(columns=str.lower)

        tm.assert_frame_equal(renamed, renamed2)
        tm.assert_frame_equal(
            renamed2.rename(columns=str.upper), float_frame, check_names=False
        )

        # index
        data = {"A": {"foo": 0, "bar": 1}}

        df = DataFrame(data)
        renamed = df.rename(index={"foo": "bar", "bar": "foo"})
        tm.assert_index_equal(renamed.index, Index(["bar", "foo"]))

        renamed = df.rename(index=str.upper)
        tm.assert_index_equal(renamed.index, Index(["FOO", "BAR"]))

        # have to pass something
        with pytest.raises(TypeError, match="must pass an index to rename"):
            float_frame.rename()

        # partial columns
        renamed = float_frame.rename(columns={"C": "foo", "D": "bar"})
        tm.assert_index_equal(renamed.columns, Index(["A", "B", "foo", "bar"]))

        # other axis
        renamed = float_frame.T.rename(index={"C": "foo", "D": "bar"})
        tm.assert_index_equal(renamed.index, Index(["A", "B", "foo", "bar"]))

        # index with name
        index = Index(["foo", "bar"], name="name")
        renamer = DataFrame(data, index=index)
        renamed = renamer.rename(index={"foo": "bar", "bar": "foo"})
        tm.assert_index_equal(renamed.index, Index(["bar", "foo"], name="name"))
        assert renamed.index.name == renamer.index.name

    @pytest.mark.parametrize(
        "args,kwargs",
        [
            ((ChainMap({"A": "a"}, {"B": "b"}),), {"axis": "columns"}),
            ((), {"columns": ChainMap({"A": "a"}, {"B": "b"})}),
        ],
    )
    def test_rename_chainmap(self, args, kwargs):
        # see gh-23859
        colAData = range(1, 11)
        colBdata = np.random.default_rng(2).standard_normal(10)

        df = DataFrame({"A": colAData, "B": colBdata})
        result = df.rename(*args, **kwargs)

        expected = DataFrame({"a": colAData, "b": colBdata})
        tm.assert_frame_equal(result, expected)

    def test_rename_multiindex(self):
        tuples_index = [("foo1", "bar1"), ("foo2", "bar2")]
        tuples_columns = [("fizz1", "buzz1"), ("fizz2", "buzz2")]
        index = MultiIndex.from_tuples(tuples_index, names=["foo", "bar"])
        columns = MultiIndex.from_tuples(tuples_columns, names=["fizz", "buzz"])
        df = DataFrame([(0, 0), (1, 1)], index=index, columns=columns)

        #
        # without specifying level -> across all levels

        renamed = df.rename(
            index={"foo1": "foo3", "bar2": "bar3"},
            columns={"fizz1": "fizz3", "buzz2": "buzz3"},
        )
        new_index = MultiIndex.from_tuples(
            [("foo3", "bar1"), ("foo2", "bar3")], names=["foo", "bar"]
        )
        new_columns = MultiIndex.from_tuples(
            [("fizz3", "buzz1"), ("fizz2", "buzz3")], names=["fizz", "buzz"]
        )
        tm.assert_index_equal(renamed.index, new_index)
        tm.assert_index_equal(renamed.columns, new_columns)
        assert renamed.index.names == df.index.names
        assert renamed.columns.names == df.columns.names

        #
        # with specifying a level (GH13766)

        # dict
        new_columns = MultiIndex.from_tuples(
            [("fizz3", "buzz1"), ("fizz2", "buzz2")], names=["fizz", "buzz"]
        )
        renamed = df.rename(columns={"fizz1": "fizz3", "buzz2": "buzz3"}, level=0)
        tm.assert_index_equal(renamed.columns, new_columns)
        renamed = df.rename(columns={"fizz1": "fizz3", "buzz2": "buzz3"}, level="fizz")
        tm.assert_index_equal(renamed.columns, new_columns)

        new_columns = MultiIndex.from_tuples(
            [("fizz1", "buzz1"), ("fizz2", "buzz3")], names=["fizz", "buzz"]
        )
        renamed = df.rename(columns={"fizz1": "fizz3", "buzz2": "buzz3"}, level=1)
        tm.assert_index_equal(renamed.columns, new_columns)
        renamed = df.rename(columns={"fizz1": "fizz3", "buzz2": "buzz3"}, level="buzz")
        tm.assert_index_equal(renamed.columns, new_columns)

        # function
        func = str.upper
        new_columns = MultiIndex.from_tuples(
            [("FIZZ1", "buzz1"), ("FIZZ2", "buzz2")], names=["fizz", "buzz"]
        )
        renamed = df.rename(columns=func, level=0)
        tm.assert_index_equal(renamed.columns, new_columns)
        renamed = df.rename(columns=func, level="fizz")
        tm.assert_index_equal(renamed.columns, new_columns)

        new_columns = MultiIndex.from_tuples(
            [("fizz1", "BUZZ1"), ("fizz2", "BUZZ2")], names=["fizz", "buzz"]
        )
        renamed = df.rename(columns=func, level=1)
        tm.assert_index_equal(renamed.columns, new_columns)
        renamed = df.rename(columns=func, level="buzz")
        tm.assert_index_equal(renamed.columns, new_columns)

        # index
        new_index = MultiIndex.from_tuples(
            [("foo3", "bar1"), ("foo2", "bar2")], names=["foo", "bar"]
        )
        renamed = df.rename(index={"foo1": "foo3", "bar2": "bar3"}, level=0)
        tm.assert_index_equal(renamed.index, new_index)

    def test_rename_nocopy(self, float_frame, using_copy_on_write, warn_copy_on_write):
        renamed = float_frame.rename(columns={"C": "foo"}, copy=False)

        assert np.shares_memory(renamed["foo"]._values, float_frame["C"]._values)

        with tm.assert_cow_warning(warn_copy_on_write):
            renamed.loc[:, "foo"] = 1.0
        if using_copy_on_write:
            assert not (float_frame["C"] == 1.0).all()
        else:
            assert (float_frame["C"] == 1.0).all()

    def test_rename_inplace(self, float_frame):
        float_frame.rename(columns={"C": "foo"})
        assert "C" in float_frame
        assert "foo" not in float_frame

        c_values = float_frame["C"]
        float_frame = float_frame.copy()
        return_value = float_frame.rename(columns={"C": "foo"}, inplace=True)
        assert return_value is None

        assert "C" not in float_frame
        assert "foo" in float_frame
        # GH 44153
        # Used to be id(float_frame["foo"]) != c_id, but flaky in the CI
        assert float_frame["foo"] is not c_values

    def test_rename_bug(self):
        # GH 5344
        # rename set ref_locs, and set_index was not resetting
        df = DataFrame({0: ["foo", "bar"], 1: ["bah", "bas"], 2: [1, 2]})
        df = df.rename(columns={0: "a"})
        df = df.rename(columns={1: "b"})
        df = df.set_index(["a", "b"])
        df.columns = ["2001-01-01"]
        expected = DataFrame(
            [[1], [2]],
            index=MultiIndex.from_tuples(
                [("foo", "bah"), ("bar", "bas")], names=["a", "b"]
            ),
            columns=["2001-01-01"],
        )
        tm.assert_frame_equal(df, expected)

    def test_rename_bug2(self):
        # GH 19497
        # rename was changing Index to MultiIndex if Index contained tuples

        df = DataFrame(data=np.arange(3), index=[(0, 0), (1, 1), (2, 2)], columns=["a"])
        df = df.rename({(1, 1): (5, 4)}, axis="index")
        expected = DataFrame(
            data=np.arange(3), index=[(0, 0), (5, 4), (2, 2)], columns=["a"]
        )
        tm.assert_frame_equal(df, expected)

    def test_rename_errors_raises(self):
        df = DataFrame(columns=["A", "B", "C", "D"])
        with pytest.raises(KeyError, match="'E'] not found in axis"):
            df.rename(columns={"A": "a", "E": "e"}, errors="raise")

    @pytest.mark.parametrize(
        "mapper, errors, expected_columns",
        [
            ({"A": "a", "E": "e"}, "ignore", ["a", "B", "C", "D"]),
            ({"A": "a"}, "raise", ["a", "B", "C", "D"]),
            (str.lower, "raise", ["a", "b", "c", "d"]),
        ],
    )
    def test_rename_errors(self, mapper, errors, expected_columns):
        # GH 13473
        # rename now works with errors parameter
        df = DataFrame(columns=["A", "B", "C", "D"])
        result = df.rename(columns=mapper, errors=errors)
        expected = DataFrame(columns=expected_columns)
        tm.assert_frame_equal(result, expected)

    def test_rename_objects(self, float_string_frame):
        renamed = float_string_frame.rename(columns=str.upper)

        assert "FOO" in renamed
        assert "foo" not in renamed

    def test_rename_axis_style(self):
        # https://github.com/pandas-dev/pandas/issues/12392
        df = DataFrame({"A": [1, 2], "B": [1, 2]}, index=["X", "Y"])
        expected = DataFrame({"a": [1, 2], "b": [1, 2]}, index=["X", "Y"])

        result = df.rename(str.lower, axis=1)
        tm.assert_frame_equal(result, expected)

        result = df.rename(str.lower, axis="columns")
        tm.assert_frame_equal(result, expected)

        result = df.rename({"A": "a", "B": "b"}, axis=1)
        tm.assert_frame_equal(result, expected)

        result = df.rename({"A": "a", "B": "b"}, axis="columns")
        tm.assert_frame_equal(result, expected)

        # Index
        expected = DataFrame({"A": [1, 2], "B": [1, 2]}, index=["x", "y"])
        result = df.rename(str.lower, axis=0)
        tm.assert_frame_equal(result, expected)

        result = df.rename(str.lower, axis="index")
        tm.assert_frame_equal(result, expected)

        result = df.rename({"X": "x", "Y": "y"}, axis=0)
        tm.assert_frame_equal(result, expected)

        result = df.rename({"X": "x", "Y": "y"}, axis="index")
        tm.assert_frame_equal(result, expected)

        result = df.rename(mapper=str.lower, axis="index")
        tm.assert_frame_equal(result, expected)

    def test_rename_mapper_multi(self):
        df = DataFrame({"A": ["a", "b"], "B": ["c", "d"], "C": [1, 2]}).set_index(
            ["A", "B"]
        )
        result = df.rename(str.upper)
        expected = df.rename(index=str.upper)
        tm.assert_frame_equal(result, expected)

    def test_rename_positional_named(self):
        # https://github.com/pandas-dev/pandas/issues/12392
        df = DataFrame({"a": [1, 2], "b": [1, 2]}, index=["X", "Y"])
        result = df.rename(index=str.lower, columns=str.upper)
        expected = DataFrame({"A": [1, 2], "B": [1, 2]}, index=["x", "y"])
        tm.assert_frame_equal(result, expected)

    def test_rename_axis_style_raises(self):
        # see gh-12392
        df = DataFrame({"A": [1, 2], "B": [1, 2]}, index=["0", "1"])

        # Named target and axis
        over_spec_msg = "Cannot specify both 'axis' and any of 'index' or 'columns'"
        with pytest.raises(TypeError, match=over_spec_msg):
            df.rename(index=str.lower, axis=1)

        with pytest.raises(TypeError, match=over_spec_msg):
            df.rename(index=str.lower, axis="columns")

        with pytest.raises(TypeError, match=over_spec_msg):
            df.rename(columns=str.lower, axis="columns")

        with pytest.raises(TypeError, match=over_spec_msg):
            df.rename(index=str.lower, axis=0)

        # Multiple targets and axis
        with pytest.raises(TypeError, match=over_spec_msg):
            df.rename(str.lower, index=str.lower, axis="columns")

        # Too many targets
        over_spec_msg = "Cannot specify both 'mapper' and any of 'index' or 'columns'"
        with pytest.raises(TypeError, match=over_spec_msg):
            df.rename(str.lower, index=str.lower, columns=str.lower)

        # Duplicates
        with pytest.raises(TypeError, match="multiple values"):
            df.rename(id, mapper=id)

    def test_rename_positional_raises(self):
        # GH 29136
        df = DataFrame(columns=["A", "B"])
        msg = r"rename\(\) takes from 1 to 2 positional arguments"

        with pytest.raises(TypeError, match=msg):
            df.rename(None, str.lower)

    def test_rename_no_mappings_raises(self):
        # GH 29136
        df = DataFrame([[1]])
        msg = "must pass an index to rename"
        with pytest.raises(TypeError, match=msg):
            df.rename()

        with pytest.raises(TypeError, match=msg):
            df.rename(None, index=None)

        with pytest.raises(TypeError, match=msg):
            df.rename(None, columns=None)

        with pytest.raises(TypeError, match=msg):
            df.rename(None, columns=None, index=None)

    def test_rename_mapper_and_positional_arguments_raises(self):
        # GH 29136
        df = DataFrame([[1]])
        msg = "Cannot specify both 'mapper' and any of 'index' or 'columns'"
        with pytest.raises(TypeError, match=msg):
            df.rename({}, index={})

        with pytest.raises(TypeError, match=msg):
            df.rename({}, columns={})

        with pytest.raises(TypeError, match=msg):
            df.rename({}, columns={}, index={})

    def test_rename_with_duplicate_columns(self):
        # GH#4403
        df4 = DataFrame(
            {"RT": [0.0454], "TClose": [22.02], "TExg": [0.0422]},
            index=MultiIndex.from_tuples(
                [(600809, 20130331)], names=["STK_ID", "RPT_Date"]
            ),
        )

        df5 = DataFrame(
            {
                "RPT_Date": [20120930, 20121231, 20130331],
                "STK_ID": [600809] * 3,
                "STK_Name": ["饡驦", "饡驦", "饡驦"],
                "TClose": [38.05, 41.66, 30.01],
            },
            index=MultiIndex.from_tuples(
                [(600809, 20120930), (600809, 20121231), (600809, 20130331)],
                names=["STK_ID", "RPT_Date"],
            ),
        )
        # TODO: can we construct this without merge?
        k = merge(df4, df5, how="inner", left_index=True, right_index=True)
        result = k.rename(columns={"TClose_x": "TClose", "TClose_y": "QT_Close"})

        expected = DataFrame(
            [[0.0454, 22.02, 0.0422, 20130331, 600809, "饡驦", 30.01]],
            columns=[
                "RT",
                "TClose",
                "TExg",
                "RPT_Date",
                "STK_ID",
                "STK_Name",
                "QT_Close",
            ],
        ).set_index(["STK_ID", "RPT_Date"], drop=False)
        tm.assert_frame_equal(result, expected)

    def test_rename_boolean_index(self):
        df = DataFrame(np.arange(15).reshape(3, 5), columns=[False, True, 2, 3, 4])
        mapper = {0: "foo", 1: "bar", 2: "bah"}
        res = df.rename(index=mapper)
        exp = DataFrame(
            np.arange(15).reshape(3, 5),
            columns=[False, True, 2, 3, 4],
            index=["foo", "bar", "bah"],
        )
        tm.assert_frame_equal(res, exp)
