import re

import pytest

from pandas.core.dtypes.common import (
    is_bool_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)

import pandas as pd
import pandas._testing as tm


@pytest.mark.filterwarnings(
    "ignore:The default of observed=False is deprecated:FutureWarning"
)
class BaseGroupbyTests:
    """Groupby-specific tests."""

    def test_grouping_grouper(self, data_for_grouping):
        df = pd.DataFrame(
            {
                "A": pd.Series(
                    ["B", "B", None, None, "A", "A", "B", "C"], dtype=object
                ),
                "B": data_for_grouping,
            }
        )
        gr1 = df.groupby("A")._grouper.groupings[0]
        gr2 = df.groupby("B")._grouper.groupings[0]

        tm.assert_numpy_array_equal(gr1.grouping_vector, df.A.values)
        tm.assert_extension_array_equal(gr2.grouping_vector, data_for_grouping)

    @pytest.mark.parametrize("as_index", [True, False])
    def test_groupby_extension_agg(self, as_index, data_for_grouping):
        df = pd.DataFrame({"A": [1, 1, 2, 2, 3, 3, 1, 4], "B": data_for_grouping})

        is_bool = data_for_grouping.dtype._is_boolean
        if is_bool:
            # only 2 unique values, and the final entry has c==b
            #  (see data_for_grouping docstring)
            df = df.iloc[:-1]

        result = df.groupby("B", as_index=as_index).A.mean()
        _, uniques = pd.factorize(data_for_grouping, sort=True)

        exp_vals = [3.0, 1.0, 4.0]
        if is_bool:
            exp_vals = exp_vals[:-1]
        if as_index:
            index = pd.Index(uniques, name="B")
            expected = pd.Series(exp_vals, index=index, name="A")
            tm.assert_series_equal(result, expected)
        else:
            expected = pd.DataFrame({"B": uniques, "A": exp_vals})
            tm.assert_frame_equal(result, expected)

    def test_groupby_agg_extension(self, data_for_grouping):
        # GH#38980 groupby agg on extension type fails for non-numeric types
        df = pd.DataFrame({"A": [1, 1, 2, 2, 3, 3, 1, 4], "B": data_for_grouping})

        expected = df.iloc[[0, 2, 4, 7]]
        expected = expected.set_index("A")

        result = df.groupby("A").agg({"B": "first"})
        tm.assert_frame_equal(result, expected)

        result = df.groupby("A").agg("first")
        tm.assert_frame_equal(result, expected)

        result = df.groupby("A").first()
        tm.assert_frame_equal(result, expected)

    def test_groupby_extension_no_sort(self, data_for_grouping):
        df = pd.DataFrame({"A": [1, 1, 2, 2, 3, 3, 1, 4], "B": data_for_grouping})

        is_bool = data_for_grouping.dtype._is_boolean
        if is_bool:
            # only 2 unique values, and the final entry has c==b
            #  (see data_for_grouping docstring)
            df = df.iloc[:-1]

        result = df.groupby("B", sort=False).A.mean()
        _, index = pd.factorize(data_for_grouping, sort=False)

        index = pd.Index(index, name="B")
        exp_vals = [1.0, 3.0, 4.0]
        if is_bool:
            exp_vals = exp_vals[:-1]
        expected = pd.Series(exp_vals, index=index, name="A")
        tm.assert_series_equal(result, expected)

    def test_groupby_extension_transform(self, data_for_grouping):
        is_bool = data_for_grouping.dtype._is_boolean

        valid = data_for_grouping[~data_for_grouping.isna()]
        df = pd.DataFrame({"A": [1, 1, 3, 3, 1, 4], "B": valid})
        is_bool = data_for_grouping.dtype._is_boolean
        if is_bool:
            # only 2 unique values, and the final entry has c==b
            #  (see data_for_grouping docstring)
            df = df.iloc[:-1]

        result = df.groupby("B").A.transform(len)
        expected = pd.Series([3, 3, 2, 2, 3, 1], name="A")
        if is_bool:
            expected = expected[:-1]

        tm.assert_series_equal(result, expected)

    def test_groupby_extension_apply(self, data_for_grouping, groupby_apply_op):
        df = pd.DataFrame({"A": [1, 1, 2, 2, 3, 3, 1, 4], "B": data_for_grouping})
        msg = "DataFrameGroupBy.apply operated on the grouping columns"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            df.groupby("B", group_keys=False, observed=False).apply(groupby_apply_op)
        df.groupby("B", group_keys=False, observed=False).A.apply(groupby_apply_op)
        msg = "DataFrameGroupBy.apply operated on the grouping columns"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            df.groupby("A", group_keys=False, observed=False).apply(groupby_apply_op)
        df.groupby("A", group_keys=False, observed=False).B.apply(groupby_apply_op)

    def test_groupby_apply_identity(self, data_for_grouping):
        df = pd.DataFrame({"A": [1, 1, 2, 2, 3, 3, 1, 4], "B": data_for_grouping})
        result = df.groupby("A").B.apply(lambda x: x.array)
        expected = pd.Series(
            [
                df.B.iloc[[0, 1, 6]].array,
                df.B.iloc[[2, 3]].array,
                df.B.iloc[[4, 5]].array,
                df.B.iloc[[7]].array,
            ],
            index=pd.Index([1, 2, 3, 4], name="A"),
            name="B",
        )
        tm.assert_series_equal(result, expected)

    def test_in_numeric_groupby(self, data_for_grouping):
        df = pd.DataFrame(
            {
                "A": [1, 1, 2, 2, 3, 3, 1, 4],
                "B": data_for_grouping,
                "C": [1, 1, 1, 1, 1, 1, 1, 1],
            }
        )

        dtype = data_for_grouping.dtype
        if (
            is_numeric_dtype(dtype)
            or is_bool_dtype(dtype)
            or dtype.name == "decimal"
            or is_string_dtype(dtype)
            or is_object_dtype(dtype)
            or dtype.kind == "m"  # in particular duration[*][pyarrow]
        ):
            expected = pd.Index(["B", "C"])
            result = df.groupby("A").sum().columns
        else:
            expected = pd.Index(["C"])

            msg = "|".join(
                [
                    # period/datetime
                    "does not support sum operations",
                    # all others
                    re.escape(f"agg function failed [how->sum,dtype->{dtype}"),
                ]
            )
            with pytest.raises(TypeError, match=msg):
                df.groupby("A").sum()
            result = df.groupby("A").sum(numeric_only=True).columns
        tm.assert_index_equal(result, expected)
