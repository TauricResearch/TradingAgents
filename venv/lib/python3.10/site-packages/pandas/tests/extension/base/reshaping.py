import itertools

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.api.extensions import ExtensionArray
from pandas.core.internals.blocks import EABackedBlock


class BaseReshapingTests:
    """Tests for reshaping and concatenation."""

    @pytest.mark.parametrize("in_frame", [True, False])
    def test_concat(self, data, in_frame):
        wrapped = pd.Series(data)
        if in_frame:
            wrapped = pd.DataFrame(wrapped)
        result = pd.concat([wrapped, wrapped], ignore_index=True)

        assert len(result) == len(data) * 2

        if in_frame:
            dtype = result.dtypes[0]
        else:
            dtype = result.dtype

        assert dtype == data.dtype
        if hasattr(result._mgr, "blocks"):
            assert isinstance(result._mgr.blocks[0], EABackedBlock)
        assert isinstance(result._mgr.arrays[0], ExtensionArray)

    @pytest.mark.parametrize("in_frame", [True, False])
    def test_concat_all_na_block(self, data_missing, in_frame):
        valid_block = pd.Series(data_missing.take([1, 1]), index=[0, 1])
        na_block = pd.Series(data_missing.take([0, 0]), index=[2, 3])
        if in_frame:
            valid_block = pd.DataFrame({"a": valid_block})
            na_block = pd.DataFrame({"a": na_block})
        result = pd.concat([valid_block, na_block])
        if in_frame:
            expected = pd.DataFrame({"a": data_missing.take([1, 1, 0, 0])})
            tm.assert_frame_equal(result, expected)
        else:
            expected = pd.Series(data_missing.take([1, 1, 0, 0]))
            tm.assert_series_equal(result, expected)

    def test_concat_mixed_dtypes(self, data):
        # https://github.com/pandas-dev/pandas/issues/20762
        df1 = pd.DataFrame({"A": data[:3]})
        df2 = pd.DataFrame({"A": [1, 2, 3]})
        df3 = pd.DataFrame({"A": ["a", "b", "c"]}).astype("category")
        dfs = [df1, df2, df3]

        # dataframes
        result = pd.concat(dfs)
        expected = pd.concat([x.astype(object) for x in dfs])
        tm.assert_frame_equal(result, expected)

        # series
        result = pd.concat([x["A"] for x in dfs])
        expected = pd.concat([x["A"].astype(object) for x in dfs])
        tm.assert_series_equal(result, expected)

        # simple test for just EA and one other
        result = pd.concat([df1, df2.astype(object)])
        expected = pd.concat([df1.astype("object"), df2.astype("object")])
        tm.assert_frame_equal(result, expected)

        result = pd.concat([df1["A"], df2["A"].astype(object)])
        expected = pd.concat([df1["A"].astype("object"), df2["A"].astype("object")])
        tm.assert_series_equal(result, expected)

    def test_concat_columns(self, data, na_value):
        df1 = pd.DataFrame({"A": data[:3]})
        df2 = pd.DataFrame({"B": [1, 2, 3]})

        expected = pd.DataFrame({"A": data[:3], "B": [1, 2, 3]})
        result = pd.concat([df1, df2], axis=1)
        tm.assert_frame_equal(result, expected)
        result = pd.concat([df1["A"], df2["B"]], axis=1)
        tm.assert_frame_equal(result, expected)

        # non-aligned
        df2 = pd.DataFrame({"B": [1, 2, 3]}, index=[1, 2, 3])
        expected = pd.DataFrame(
            {
                "A": data._from_sequence(list(data[:3]) + [na_value], dtype=data.dtype),
                "B": [np.nan, 1, 2, 3],
            }
        )

        result = pd.concat([df1, df2], axis=1)
        tm.assert_frame_equal(result, expected)
        result = pd.concat([df1["A"], df2["B"]], axis=1)
        tm.assert_frame_equal(result, expected)

    def test_concat_extension_arrays_copy_false(self, data, na_value):
        # GH 20756
        df1 = pd.DataFrame({"A": data[:3]})
        df2 = pd.DataFrame({"B": data[3:7]})
        expected = pd.DataFrame(
            {
                "A": data._from_sequence(list(data[:3]) + [na_value], dtype=data.dtype),
                "B": data[3:7],
            }
        )
        result = pd.concat([df1, df2], axis=1, copy=False)
        tm.assert_frame_equal(result, expected)

    def test_concat_with_reindex(self, data):
        # GH-33027
        a = pd.DataFrame({"a": data[:5]})
        b = pd.DataFrame({"b": data[:5]})
        result = pd.concat([a, b], ignore_index=True)
        expected = pd.DataFrame(
            {
                "a": data.take(list(range(5)) + ([-1] * 5), allow_fill=True),
                "b": data.take(([-1] * 5) + list(range(5)), allow_fill=True),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_align(self, data, na_value):
        a = data[:3]
        b = data[2:5]
        r1, r2 = pd.Series(a).align(pd.Series(b, index=[1, 2, 3]))

        # Assumes that the ctor can take a list of scalars of the type
        e1 = pd.Series(data._from_sequence(list(a) + [na_value], dtype=data.dtype))
        e2 = pd.Series(data._from_sequence([na_value] + list(b), dtype=data.dtype))
        tm.assert_series_equal(r1, e1)
        tm.assert_series_equal(r2, e2)

    def test_align_frame(self, data, na_value):
        a = data[:3]
        b = data[2:5]
        r1, r2 = pd.DataFrame({"A": a}).align(pd.DataFrame({"A": b}, index=[1, 2, 3]))

        # Assumes that the ctor can take a list of scalars of the type
        e1 = pd.DataFrame(
            {"A": data._from_sequence(list(a) + [na_value], dtype=data.dtype)}
        )
        e2 = pd.DataFrame(
            {"A": data._from_sequence([na_value] + list(b), dtype=data.dtype)}
        )
        tm.assert_frame_equal(r1, e1)
        tm.assert_frame_equal(r2, e2)

    def test_align_series_frame(self, data, na_value):
        # https://github.com/pandas-dev/pandas/issues/20576
        ser = pd.Series(data, name="a")
        df = pd.DataFrame({"col": np.arange(len(ser) + 1)})
        r1, r2 = ser.align(df)

        e1 = pd.Series(
            data._from_sequence(list(data) + [na_value], dtype=data.dtype),
            name=ser.name,
        )

        tm.assert_series_equal(r1, e1)
        tm.assert_frame_equal(r2, df)

    def test_set_frame_expand_regular_with_extension(self, data):
        df = pd.DataFrame({"A": [1] * len(data)})
        df["B"] = data
        expected = pd.DataFrame({"A": [1] * len(data), "B": data})
        tm.assert_frame_equal(df, expected)

    def test_set_frame_expand_extension_with_regular(self, data):
        df = pd.DataFrame({"A": data})
        df["B"] = [1] * len(data)
        expected = pd.DataFrame({"A": data, "B": [1] * len(data)})
        tm.assert_frame_equal(df, expected)

    def test_set_frame_overwrite_object(self, data):
        # https://github.com/pandas-dev/pandas/issues/20555
        df = pd.DataFrame({"A": [1] * len(data)}, dtype=object)
        df["A"] = data
        assert df.dtypes["A"] == data.dtype

    def test_merge(self, data, na_value):
        # GH-20743
        df1 = pd.DataFrame({"ext": data[:3], "int1": [1, 2, 3], "key": [0, 1, 2]})
        df2 = pd.DataFrame({"int2": [1, 2, 3, 4], "key": [0, 0, 1, 3]})

        res = pd.merge(df1, df2)
        exp = pd.DataFrame(
            {
                "int1": [1, 1, 2],
                "int2": [1, 2, 3],
                "key": [0, 0, 1],
                "ext": data._from_sequence(
                    [data[0], data[0], data[1]], dtype=data.dtype
                ),
            }
        )
        tm.assert_frame_equal(res, exp[["ext", "int1", "key", "int2"]])

        res = pd.merge(df1, df2, how="outer")
        exp = pd.DataFrame(
            {
                "int1": [1, 1, 2, 3, np.nan],
                "int2": [1, 2, 3, np.nan, 4],
                "key": [0, 0, 1, 2, 3],
                "ext": data._from_sequence(
                    [data[0], data[0], data[1], data[2], na_value], dtype=data.dtype
                ),
            }
        )
        tm.assert_frame_equal(res, exp[["ext", "int1", "key", "int2"]])

    def test_merge_on_extension_array(self, data):
        # GH 23020
        a, b = data[:2]
        key = type(data)._from_sequence([a, b], dtype=data.dtype)

        df = pd.DataFrame({"key": key, "val": [1, 2]})
        result = pd.merge(df, df, on="key")
        expected = pd.DataFrame({"key": key, "val_x": [1, 2], "val_y": [1, 2]})
        tm.assert_frame_equal(result, expected)

        # order
        result = pd.merge(df.iloc[[1, 0]], df, on="key")
        expected = expected.iloc[[1, 0]].reset_index(drop=True)
        tm.assert_frame_equal(result, expected)

    def test_merge_on_extension_array_duplicates(self, data):
        # GH 23020
        a, b = data[:2]
        key = type(data)._from_sequence([a, b, a], dtype=data.dtype)
        df1 = pd.DataFrame({"key": key, "val": [1, 2, 3]})
        df2 = pd.DataFrame({"key": key, "val": [1, 2, 3]})

        result = pd.merge(df1, df2, on="key")
        expected = pd.DataFrame(
            {
                "key": key.take([0, 0, 1, 2, 2]),
                "val_x": [1, 1, 2, 3, 3],
                "val_y": [1, 3, 2, 1, 3],
            }
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.filterwarnings(
        "ignore:The previous implementation of stack is deprecated"
    )
    @pytest.mark.parametrize(
        "columns",
        [
            ["A", "B"],
            pd.MultiIndex.from_tuples(
                [("A", "a"), ("A", "b")], names=["outer", "inner"]
            ),
        ],
    )
    @pytest.mark.parametrize("future_stack", [True, False])
    def test_stack(self, data, columns, future_stack):
        df = pd.DataFrame({"A": data[:5], "B": data[:5]})
        df.columns = columns
        result = df.stack(future_stack=future_stack)
        expected = df.astype(object).stack(future_stack=future_stack)
        # we need a second astype(object), in case the constructor inferred
        # object -> specialized, as is done for period.
        expected = expected.astype(object)

        if isinstance(expected, pd.Series):
            assert result.dtype == df.iloc[:, 0].dtype
        else:
            assert all(result.dtypes == df.iloc[:, 0].dtype)

        result = result.astype(object)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "index",
        [
            # Two levels, uniform.
            pd.MultiIndex.from_product(([["A", "B"], ["a", "b"]]), names=["a", "b"]),
            # non-uniform
            pd.MultiIndex.from_tuples([("A", "a"), ("A", "b"), ("B", "b")]),
            # three levels, non-uniform
            pd.MultiIndex.from_product([("A", "B"), ("a", "b", "c"), (0, 1, 2)]),
            pd.MultiIndex.from_tuples(
                [
                    ("A", "a", 1),
                    ("A", "b", 0),
                    ("A", "a", 0),
                    ("B", "a", 0),
                    ("B", "c", 1),
                ]
            ),
        ],
    )
    @pytest.mark.parametrize("obj", ["series", "frame"])
    def test_unstack(self, data, index, obj):
        data = data[: len(index)]
        if obj == "series":
            ser = pd.Series(data, index=index)
        else:
            ser = pd.DataFrame({"A": data, "B": data}, index=index)

        n = index.nlevels
        levels = list(range(n))
        # [0, 1, 2]
        # [(0,), (1,), (2,), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
        combinations = itertools.chain.from_iterable(
            itertools.permutations(levels, i) for i in range(1, n)
        )

        for level in combinations:
            result = ser.unstack(level=level)
            assert all(
                isinstance(result[col].array, type(data)) for col in result.columns
            )

            if obj == "series":
                # We should get the same result with to_frame+unstack+droplevel
                df = ser.to_frame()

                alt = df.unstack(level=level).droplevel(0, axis=1)
                tm.assert_frame_equal(result, alt)

            obj_ser = ser.astype(object)

            expected = obj_ser.unstack(level=level, fill_value=data.dtype.na_value)
            if obj == "series":
                assert (expected.dtypes == object).all()

            result = result.astype(object)
            tm.assert_frame_equal(result, expected)

    def test_ravel(self, data):
        # as long as EA is 1D-only, ravel is a no-op
        result = data.ravel()
        assert type(result) == type(data)

        if data.dtype._is_immutable:
            pytest.skip(f"test_ravel assumes mutability and {data.dtype} is immutable")

        # Check that we have a view, not a copy
        result[0] = result[1]
        assert data[0] == data[1]

    def test_transpose(self, data):
        result = data.transpose()
        assert type(result) == type(data)

        # check we get a new object
        assert result is not data

        # If we ever _did_ support 2D, shape should be reversed
        assert result.shape == data.shape[::-1]

        if data.dtype._is_immutable:
            pytest.skip(
                f"test_transpose assumes mutability and {data.dtype} is immutable"
            )

        # Check that we have a view, not a copy
        result[0] = result[1]
        assert data[0] == data[1]

    def test_transpose_frame(self, data):
        df = pd.DataFrame({"A": data[:4], "B": data[:4]}, index=["a", "b", "c", "d"])
        result = df.T
        expected = pd.DataFrame(
            {
                "a": type(data)._from_sequence([data[0]] * 2, dtype=data.dtype),
                "b": type(data)._from_sequence([data[1]] * 2, dtype=data.dtype),
                "c": type(data)._from_sequence([data[2]] * 2, dtype=data.dtype),
                "d": type(data)._from_sequence([data[3]] * 2, dtype=data.dtype),
            },
            index=["A", "B"],
        )
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(np.transpose(np.transpose(df)), df)
        tm.assert_frame_equal(np.transpose(np.transpose(df[["A"]])), df[["A"]])
