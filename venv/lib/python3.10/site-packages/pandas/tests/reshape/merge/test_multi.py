import numpy as np
import pytest

import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    RangeIndex,
    Series,
    Timestamp,
    option_context,
)
import pandas._testing as tm
from pandas.core.reshape.concat import concat
from pandas.core.reshape.merge import merge


@pytest.fixture
def left():
    """left dataframe (not multi-indexed) for multi-index join tests"""
    # a little relevant example with NAs
    key1 = ["bar", "bar", "bar", "foo", "foo", "baz", "baz", "qux", "qux", "snap"]
    key2 = ["two", "one", "three", "one", "two", "one", "two", "two", "three", "one"]

    data = np.random.default_rng(2).standard_normal(len(key1))
    return DataFrame({"key1": key1, "key2": key2, "data": data})


@pytest.fixture
def right(multiindex_dataframe_random_data):
    """right dataframe (multi-indexed) for multi-index join tests"""
    df = multiindex_dataframe_random_data
    df.index.names = ["key1", "key2"]

    df.columns = ["j_one", "j_two", "j_three"]
    return df


@pytest.fixture
def left_multi():
    return DataFrame(
        {
            "Origin": ["A", "A", "B", "B", "C"],
            "Destination": ["A", "B", "A", "C", "A"],
            "Period": ["AM", "AM", "IP", "AM", "OP"],
            "TripPurp": ["hbw", "nhb", "hbo", "nhb", "hbw"],
            "Trips": [1987, 3647, 2470, 4296, 4444],
        },
        columns=["Origin", "Destination", "Period", "TripPurp", "Trips"],
    ).set_index(["Origin", "Destination", "Period", "TripPurp"])


@pytest.fixture
def right_multi():
    return DataFrame(
        {
            "Origin": ["A", "A", "B", "B", "C", "C", "E"],
            "Destination": ["A", "B", "A", "B", "A", "B", "F"],
            "Period": ["AM", "AM", "IP", "AM", "OP", "IP", "AM"],
            "LinkType": ["a", "b", "c", "b", "a", "b", "a"],
            "Distance": [100, 80, 90, 80, 75, 35, 55],
        },
        columns=["Origin", "Destination", "Period", "LinkType", "Distance"],
    ).set_index(["Origin", "Destination", "Period", "LinkType"])


@pytest.fixture
def on_cols_multi():
    return ["Origin", "Destination", "Period"]


class TestMergeMulti:
    def test_merge_on_multikey(self, left, right, join_type):
        on_cols = ["key1", "key2"]
        result = left.join(right, on=on_cols, how=join_type).reset_index(drop=True)

        expected = merge(left, right.reset_index(), on=on_cols, how=join_type)

        tm.assert_frame_equal(result, expected)

        result = left.join(right, on=on_cols, how=join_type, sort=True).reset_index(
            drop=True
        )

        expected = merge(
            left, right.reset_index(), on=on_cols, how=join_type, sort=True
        )

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "infer_string", [False, pytest.param(True, marks=td.skip_if_no("pyarrow"))]
    )
    @pytest.mark.parametrize("sort", [True, False])
    def test_left_join_multi_index(self, sort, infer_string):
        with option_context("future.infer_string", infer_string):
            icols = ["1st", "2nd", "3rd"]

            def bind_cols(df):
                iord = lambda a: 0 if a != a else ord(a)
                f = lambda ts: ts.map(iord) - ord("a")
                return f(df["1st"]) + f(df["3rd"]) * 1e2 + df["2nd"].fillna(0) * 10

            def run_asserts(left, right, sort):
                res = left.join(right, on=icols, how="left", sort=sort)

                assert len(left) < len(res) + 1
                assert not res["4th"].isna().any()
                assert not res["5th"].isna().any()

                tm.assert_series_equal(res["4th"], -res["5th"], check_names=False)
                result = bind_cols(res.iloc[:, :-2])
                tm.assert_series_equal(res["4th"], result, check_names=False)
                assert result.name is None

                if sort:
                    tm.assert_frame_equal(res, res.sort_values(icols, kind="mergesort"))

                out = merge(left, right.reset_index(), on=icols, sort=sort, how="left")

                res.index = RangeIndex(len(res))
                tm.assert_frame_equal(out, res)

            lc = list(map(chr, np.arange(ord("a"), ord("z") + 1)))
            left = DataFrame(
                np.random.default_rng(2).choice(lc, (50, 2)), columns=["1st", "3rd"]
            )
            # Explicit cast to float to avoid implicit cast when setting nan
            left.insert(
                1,
                "2nd",
                np.random.default_rng(2).integers(0, 10, len(left)).astype("float"),
            )

            i = np.random.default_rng(2).permutation(len(left))
            right = left.iloc[i].copy()

            left["4th"] = bind_cols(left)
            right["5th"] = -bind_cols(right)
            right.set_index(icols, inplace=True)

            run_asserts(left, right, sort)

            # inject some nulls
            left.loc[1::4, "1st"] = np.nan
            left.loc[2::5, "2nd"] = np.nan
            left.loc[3::6, "3rd"] = np.nan
            left["4th"] = bind_cols(left)

            i = np.random.default_rng(2).permutation(len(left))
            right = left.iloc[i, :-1]
            right["5th"] = -bind_cols(right)
            right.set_index(icols, inplace=True)

            run_asserts(left, right, sort)

    @pytest.mark.parametrize("sort", [False, True])
    def test_merge_right_vs_left(self, left, right, sort):
        # compare left vs right merge with multikey
        on_cols = ["key1", "key2"]
        merged_left_right = left.merge(
            right, left_on=on_cols, right_index=True, how="left", sort=sort
        )

        merge_right_left = right.merge(
            left, right_on=on_cols, left_index=True, how="right", sort=sort
        )

        # Reorder columns
        merge_right_left = merge_right_left[merged_left_right.columns]

        tm.assert_frame_equal(merged_left_right, merge_right_left)

    def test_merge_multiple_cols_with_mixed_cols_index(self):
        # GH29522
        s = Series(
            range(6),
            MultiIndex.from_product([["A", "B"], [1, 2, 3]], names=["lev1", "lev2"]),
            name="Amount",
        )
        df = DataFrame({"lev1": list("AAABBB"), "lev2": [1, 2, 3, 1, 2, 3], "col": 0})
        result = merge(df, s.reset_index(), on=["lev1", "lev2"])
        expected = DataFrame(
            {
                "lev1": list("AAABBB"),
                "lev2": [1, 2, 3, 1, 2, 3],
                "col": [0] * 6,
                "Amount": range(6),
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_compress_group_combinations(self):
        # ~ 40000000 possible unique groups
        key1 = [str(i) for i in range(10000)]
        key1 = np.tile(key1, 2)
        key2 = key1[::-1]

        df = DataFrame(
            {
                "key1": key1,
                "key2": key2,
                "value1": np.random.default_rng(2).standard_normal(20000),
            }
        )

        df2 = DataFrame(
            {
                "key1": key1[::2],
                "key2": key2[::2],
                "value2": np.random.default_rng(2).standard_normal(10000),
            }
        )

        # just to hit the label compression code path
        merge(df, df2, how="outer")

    def test_left_join_index_preserve_order(self):
        on_cols = ["k1", "k2"]
        left = DataFrame(
            {
                "k1": [0, 1, 2] * 8,
                "k2": ["foo", "bar"] * 12,
                "v": np.array(np.arange(24), dtype=np.int64),
            }
        )

        index = MultiIndex.from_tuples([(2, "bar"), (1, "foo")])
        right = DataFrame({"v2": [5, 7]}, index=index)

        result = left.join(right, on=on_cols)

        expected = left.copy()
        expected["v2"] = np.nan
        expected.loc[(expected.k1 == 2) & (expected.k2 == "bar"), "v2"] = 5
        expected.loc[(expected.k1 == 1) & (expected.k2 == "foo"), "v2"] = 7

        tm.assert_frame_equal(result, expected)

        result.sort_values(on_cols, kind="mergesort", inplace=True)
        expected = left.join(right, on=on_cols, sort=True)

        tm.assert_frame_equal(result, expected)

        # test join with multi dtypes blocks
        left = DataFrame(
            {
                "k1": [0, 1, 2] * 8,
                "k2": ["foo", "bar"] * 12,
                "k3": np.array([0, 1, 2] * 8, dtype=np.float32),
                "v": np.array(np.arange(24), dtype=np.int32),
            }
        )

        index = MultiIndex.from_tuples([(2, "bar"), (1, "foo")])
        right = DataFrame({"v2": [5, 7]}, index=index)

        result = left.join(right, on=on_cols)

        expected = left.copy()
        expected["v2"] = np.nan
        expected.loc[(expected.k1 == 2) & (expected.k2 == "bar"), "v2"] = 5
        expected.loc[(expected.k1 == 1) & (expected.k2 == "foo"), "v2"] = 7

        tm.assert_frame_equal(result, expected)

        result = result.sort_values(on_cols, kind="mergesort")
        expected = left.join(right, on=on_cols, sort=True)

        tm.assert_frame_equal(result, expected)

    def test_left_join_index_multi_match_multiindex(self):
        left = DataFrame(
            [
                ["X", "Y", "C", "a"],
                ["W", "Y", "C", "e"],
                ["V", "Q", "A", "h"],
                ["V", "R", "D", "i"],
                ["X", "Y", "D", "b"],
                ["X", "Y", "A", "c"],
                ["W", "Q", "B", "f"],
                ["W", "R", "C", "g"],
                ["V", "Y", "C", "j"],
                ["X", "Y", "B", "d"],
            ],
            columns=["cola", "colb", "colc", "tag"],
            index=[3, 2, 0, 1, 7, 6, 4, 5, 9, 8],
        )

        right = DataFrame(
            [
                ["W", "R", "C", 0],
                ["W", "Q", "B", 3],
                ["W", "Q", "B", 8],
                ["X", "Y", "A", 1],
                ["X", "Y", "A", 4],
                ["X", "Y", "B", 5],
                ["X", "Y", "C", 6],
                ["X", "Y", "C", 9],
                ["X", "Q", "C", -6],
                ["X", "R", "C", -9],
                ["V", "Y", "C", 7],
                ["V", "R", "D", 2],
                ["V", "R", "D", -1],
                ["V", "Q", "A", -3],
            ],
            columns=["col1", "col2", "col3", "val"],
        ).set_index(["col1", "col2", "col3"])

        result = left.join(right, on=["cola", "colb", "colc"], how="left")

        expected = DataFrame(
            [
                ["X", "Y", "C", "a", 6],
                ["X", "Y", "C", "a", 9],
                ["W", "Y", "C", "e", np.nan],
                ["V", "Q", "A", "h", -3],
                ["V", "R", "D", "i", 2],
                ["V", "R", "D", "i", -1],
                ["X", "Y", "D", "b", np.nan],
                ["X", "Y", "A", "c", 1],
                ["X", "Y", "A", "c", 4],
                ["W", "Q", "B", "f", 3],
                ["W", "Q", "B", "f", 8],
                ["W", "R", "C", "g", 0],
                ["V", "Y", "C", "j", 7],
                ["X", "Y", "B", "d", 5],
            ],
            columns=["cola", "colb", "colc", "tag", "val"],
            index=[3, 3, 2, 0, 1, 1, 7, 6, 6, 4, 4, 5, 9, 8],
        )

        tm.assert_frame_equal(result, expected)

        result = left.join(right, on=["cola", "colb", "colc"], how="left", sort=True)

        expected = expected.sort_values(["cola", "colb", "colc"], kind="mergesort")

        tm.assert_frame_equal(result, expected)

    def test_left_join_index_multi_match(self):
        left = DataFrame(
            [["c", 0], ["b", 1], ["a", 2], ["b", 3]],
            columns=["tag", "val"],
            index=[2, 0, 1, 3],
        )

        right = DataFrame(
            [
                ["a", "v"],
                ["c", "w"],
                ["c", "x"],
                ["d", "y"],
                ["a", "z"],
                ["c", "r"],
                ["e", "q"],
                ["c", "s"],
            ],
            columns=["tag", "char"],
        ).set_index("tag")

        result = left.join(right, on="tag", how="left")

        expected = DataFrame(
            [
                ["c", 0, "w"],
                ["c", 0, "x"],
                ["c", 0, "r"],
                ["c", 0, "s"],
                ["b", 1, np.nan],
                ["a", 2, "v"],
                ["a", 2, "z"],
                ["b", 3, np.nan],
            ],
            columns=["tag", "val", "char"],
            index=[2, 2, 2, 2, 0, 1, 1, 3],
        )

        tm.assert_frame_equal(result, expected)

        result = left.join(right, on="tag", how="left", sort=True)
        expected2 = expected.sort_values("tag", kind="mergesort")

        tm.assert_frame_equal(result, expected2)

        # GH7331 - maintain left frame order in left merge
        result = merge(left, right.reset_index(), how="left", on="tag")
        expected.index = RangeIndex(len(expected))
        tm.assert_frame_equal(result, expected)

    def test_left_merge_na_buglet(self):
        left = DataFrame(
            {
                "id": list("abcde"),
                "v1": np.random.default_rng(2).standard_normal(5),
                "v2": np.random.default_rng(2).standard_normal(5),
                "dummy": list("abcde"),
                "v3": np.random.default_rng(2).standard_normal(5),
            },
            columns=["id", "v1", "v2", "dummy", "v3"],
        )
        right = DataFrame(
            {
                "id": ["a", "b", np.nan, np.nan, np.nan],
                "sv3": [1.234, 5.678, np.nan, np.nan, np.nan],
            }
        )

        result = merge(left, right, on="id", how="left")

        rdf = right.drop(["id"], axis=1)
        expected = left.join(rdf)
        tm.assert_frame_equal(result, expected)

    def test_merge_na_keys(self):
        data = [
            [1950, "A", 1.5],
            [1950, "B", 1.5],
            [1955, "B", 1.5],
            [1960, "B", np.nan],
            [1970, "B", 4.0],
            [1950, "C", 4.0],
            [1960, "C", np.nan],
            [1965, "C", 3.0],
            [1970, "C", 4.0],
        ]

        frame = DataFrame(data, columns=["year", "panel", "data"])

        other_data = [
            [1960, "A", np.nan],
            [1970, "A", np.nan],
            [1955, "A", np.nan],
            [1965, "A", np.nan],
            [1965, "B", np.nan],
            [1955, "C", np.nan],
        ]
        other = DataFrame(other_data, columns=["year", "panel", "data"])

        result = frame.merge(other, how="outer")

        expected = frame.fillna(-999).merge(other.fillna(-999), how="outer")
        expected = expected.replace(-999, np.nan)

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("klass", [None, np.asarray, Series, Index])
    def test_merge_datetime_index(self, klass):
        # see gh-19038
        df = DataFrame(
            [1, 2, 3], ["2016-01-01", "2017-01-01", "2018-01-01"], columns=["a"]
        )
        df.index = pd.to_datetime(df.index)
        on_vector = df.index.year

        if klass is not None:
            on_vector = klass(on_vector)

        exp_years = np.array([2016, 2017, 2018], dtype=np.int32)
        expected = DataFrame({"a": [1, 2, 3], "key_1": exp_years})

        result = df.merge(df, on=["a", on_vector], how="inner")
        tm.assert_frame_equal(result, expected)

        expected = DataFrame({"key_0": exp_years, "a_x": [1, 2, 3], "a_y": [1, 2, 3]})

        result = df.merge(df, on=[df.index.year], how="inner")
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("merge_type", ["left", "right"])
    def test_merge_datetime_multi_index_empty_df(self, merge_type):
        # see gh-36895

        left = DataFrame(
            data={
                "data": [1.5, 1.5],
            },
            index=MultiIndex.from_tuples(
                [[Timestamp("1950-01-01"), "A"], [Timestamp("1950-01-02"), "B"]],
                names=["date", "panel"],
            ),
        )

        right = DataFrame(
            index=MultiIndex.from_tuples([], names=["date", "panel"]), columns=["state"]
        )

        expected_index = MultiIndex.from_tuples(
            [[Timestamp("1950-01-01"), "A"], [Timestamp("1950-01-02"), "B"]],
            names=["date", "panel"],
        )

        if merge_type == "left":
            expected = DataFrame(
                data={
                    "data": [1.5, 1.5],
                    "state": np.array([np.nan, np.nan], dtype=object),
                },
                index=expected_index,
            )
            results_merge = left.merge(right, how="left", on=["date", "panel"])
            results_join = left.join(right, how="left")
        else:
            expected = DataFrame(
                data={
                    "state": np.array([np.nan, np.nan], dtype=object),
                    "data": [1.5, 1.5],
                },
                index=expected_index,
            )
            results_merge = right.merge(left, how="right", on=["date", "panel"])
            results_join = right.join(left, how="right")

        tm.assert_frame_equal(results_merge, expected)
        tm.assert_frame_equal(results_join, expected)

    @pytest.fixture
    def household(self):
        household = DataFrame(
            {
                "household_id": [1, 2, 3],
                "male": [0, 1, 0],
                "wealth": [196087.3, 316478.7, 294750],
            },
            columns=["household_id", "male", "wealth"],
        ).set_index("household_id")
        return household

    @pytest.fixture
    def portfolio(self):
        portfolio = DataFrame(
            {
                "household_id": [1, 2, 2, 3, 3, 3, 4],
                "asset_id": [
                    "nl0000301109",
                    "nl0000289783",
                    "gb00b03mlx29",
                    "gb00b03mlx29",
                    "lu0197800237",
                    "nl0000289965",
                    np.nan,
                ],
                "name": [
                    "ABN Amro",
                    "Robeco",
                    "Royal Dutch Shell",
                    "Royal Dutch Shell",
                    "AAB Eastern Europe Equity Fund",
                    "Postbank BioTech Fonds",
                    np.nan,
                ],
                "share": [1.0, 0.4, 0.6, 0.15, 0.6, 0.25, 1.0],
            },
            columns=["household_id", "asset_id", "name", "share"],
        ).set_index(["household_id", "asset_id"])
        return portfolio

    @pytest.fixture
    def expected(self):
        expected = (
            DataFrame(
                {
                    "male": [0, 1, 1, 0, 0, 0],
                    "wealth": [
                        196087.3,
                        316478.7,
                        316478.7,
                        294750.0,
                        294750.0,
                        294750.0,
                    ],
                    "name": [
                        "ABN Amro",
                        "Robeco",
                        "Royal Dutch Shell",
                        "Royal Dutch Shell",
                        "AAB Eastern Europe Equity Fund",
                        "Postbank BioTech Fonds",
                    ],
                    "share": [1.00, 0.40, 0.60, 0.15, 0.60, 0.25],
                    "household_id": [1, 2, 2, 3, 3, 3],
                    "asset_id": [
                        "nl0000301109",
                        "nl0000289783",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "lu0197800237",
                        "nl0000289965",
                    ],
                }
            )
            .set_index(["household_id", "asset_id"])
            .reindex(columns=["male", "wealth", "name", "share"])
        )
        return expected

    def test_join_multi_levels(self, portfolio, household, expected):
        portfolio = portfolio.copy()
        household = household.copy()

        # GH 3662
        # merge multi-levels
        result = household.join(portfolio, how="inner")
        tm.assert_frame_equal(result, expected)

    def test_join_multi_levels_merge_equivalence(self, portfolio, household, expected):
        portfolio = portfolio.copy()
        household = household.copy()

        # equivalency
        result = merge(
            household.reset_index(),
            portfolio.reset_index(),
            on=["household_id"],
            how="inner",
        ).set_index(["household_id", "asset_id"])
        tm.assert_frame_equal(result, expected)

    def test_join_multi_levels_outer(self, portfolio, household, expected):
        portfolio = portfolio.copy()
        household = household.copy()

        result = household.join(portfolio, how="outer")
        expected = concat(
            [
                expected,
                (
                    DataFrame(
                        {"share": [1.00]},
                        index=MultiIndex.from_tuples(
                            [(4, np.nan)], names=["household_id", "asset_id"]
                        ),
                    )
                ),
            ],
            axis=0,
            sort=True,
        ).reindex(columns=expected.columns)
        tm.assert_frame_equal(result, expected, check_index_type=False)

    def test_join_multi_levels_invalid(self, portfolio, household):
        portfolio = portfolio.copy()
        household = household.copy()

        # invalid cases
        household.index.name = "foo"

        with pytest.raises(
            ValueError, match="cannot join with no overlapping index names"
        ):
            household.join(portfolio, how="inner")

        portfolio2 = portfolio.copy()
        portfolio2.index.set_names(["household_id", "foo"])

        with pytest.raises(ValueError, match="columns overlap but no suffix specified"):
            portfolio2.join(portfolio, how="inner")

    def test_join_multi_levels2(self):
        # some more advanced merges
        # GH6360
        household = DataFrame(
            {
                "household_id": [1, 2, 2, 3, 3, 3, 4],
                "asset_id": [
                    "nl0000301109",
                    "nl0000301109",
                    "gb00b03mlx29",
                    "gb00b03mlx29",
                    "lu0197800237",
                    "nl0000289965",
                    np.nan,
                ],
                "share": [1.0, 0.4, 0.6, 0.15, 0.6, 0.25, 1.0],
            },
            columns=["household_id", "asset_id", "share"],
        ).set_index(["household_id", "asset_id"])

        log_return = DataFrame(
            {
                "asset_id": [
                    "gb00b03mlx29",
                    "gb00b03mlx29",
                    "gb00b03mlx29",
                    "lu0197800237",
                    "lu0197800237",
                ],
                "t": [233, 234, 235, 180, 181],
                "log_return": [
                    0.09604978,
                    -0.06524096,
                    0.03532373,
                    0.03025441,
                    0.036997,
                ],
            }
        ).set_index(["asset_id", "t"])

        expected = (
            DataFrame(
                {
                    "household_id": [2, 2, 2, 3, 3, 3, 3, 3],
                    "asset_id": [
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "lu0197800237",
                        "lu0197800237",
                    ],
                    "t": [233, 234, 235, 233, 234, 235, 180, 181],
                    "share": [0.6, 0.6, 0.6, 0.15, 0.15, 0.15, 0.6, 0.6],
                    "log_return": [
                        0.09604978,
                        -0.06524096,
                        0.03532373,
                        0.09604978,
                        -0.06524096,
                        0.03532373,
                        0.03025441,
                        0.036997,
                    ],
                }
            )
            .set_index(["household_id", "asset_id", "t"])
            .reindex(columns=["share", "log_return"])
        )

        # this is the equivalency
        result = merge(
            household.reset_index(),
            log_return.reset_index(),
            on=["asset_id"],
            how="inner",
        ).set_index(["household_id", "asset_id", "t"])
        tm.assert_frame_equal(result, expected)

        expected = (
            DataFrame(
                {
                    "household_id": [2, 2, 2, 3, 3, 3, 3, 3, 3, 1, 2, 4],
                    "asset_id": [
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "gb00b03mlx29",
                        "lu0197800237",
                        "lu0197800237",
                        "nl0000289965",
                        "nl0000301109",
                        "nl0000301109",
                        None,
                    ],
                    "t": [
                        233,
                        234,
                        235,
                        233,
                        234,
                        235,
                        180,
                        181,
                        None,
                        None,
                        None,
                        None,
                    ],
                    "share": [
                        0.6,
                        0.6,
                        0.6,
                        0.15,
                        0.15,
                        0.15,
                        0.6,
                        0.6,
                        0.25,
                        1.0,
                        0.4,
                        1.0,
                    ],
                    "log_return": [
                        0.09604978,
                        -0.06524096,
                        0.03532373,
                        0.09604978,
                        -0.06524096,
                        0.03532373,
                        0.03025441,
                        0.036997,
                        None,
                        None,
                        None,
                        None,
                    ],
                }
            )
            .set_index(["household_id", "asset_id", "t"])
            .reindex(columns=["share", "log_return"])
        )

        result = merge(
            household.reset_index(),
            log_return.reset_index(),
            on=["asset_id"],
            how="outer",
        ).set_index(["household_id", "asset_id", "t"])

        tm.assert_frame_equal(result, expected)


class TestJoinMultiMulti:
    def test_join_multi_multi(self, left_multi, right_multi, join_type, on_cols_multi):
        left_names = left_multi.index.names
        right_names = right_multi.index.names
        if join_type == "right":
            level_order = right_names + left_names.difference(right_names)
        else:
            level_order = left_names + right_names.difference(left_names)
        # Multi-index join tests
        expected = (
            merge(
                left_multi.reset_index(),
                right_multi.reset_index(),
                how=join_type,
                on=on_cols_multi,
            )
            .set_index(level_order)
            .sort_index()
        )

        result = left_multi.join(right_multi, how=join_type).sort_index()
        tm.assert_frame_equal(result, expected)

    def test_join_multi_empty_frames(
        self, left_multi, right_multi, join_type, on_cols_multi
    ):
        left_multi = left_multi.drop(columns=left_multi.columns)
        right_multi = right_multi.drop(columns=right_multi.columns)

        left_names = left_multi.index.names
        right_names = right_multi.index.names
        if join_type == "right":
            level_order = right_names + left_names.difference(right_names)
        else:
            level_order = left_names + right_names.difference(left_names)

        expected = (
            merge(
                left_multi.reset_index(),
                right_multi.reset_index(),
                how=join_type,
                on=on_cols_multi,
            )
            .set_index(level_order)
            .sort_index()
        )

        result = left_multi.join(right_multi, how=join_type).sort_index()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("box", [None, np.asarray, Series, Index])
    def test_merge_datetime_index(self, box):
        # see gh-19038
        df = DataFrame(
            [1, 2, 3], ["2016-01-01", "2017-01-01", "2018-01-01"], columns=["a"]
        )
        df.index = pd.to_datetime(df.index)
        on_vector = df.index.year

        if box is not None:
            on_vector = box(on_vector)

        exp_years = np.array([2016, 2017, 2018], dtype=np.int32)
        expected = DataFrame({"a": [1, 2, 3], "key_1": exp_years})

        result = df.merge(df, on=["a", on_vector], how="inner")
        tm.assert_frame_equal(result, expected)

        expected = DataFrame({"key_0": exp_years, "a_x": [1, 2, 3], "a_y": [1, 2, 3]})

        result = df.merge(df, on=[df.index.year], how="inner")
        tm.assert_frame_equal(result, expected)

    def test_single_common_level(self):
        index_left = MultiIndex.from_tuples(
            [("K0", "X0"), ("K0", "X1"), ("K1", "X2")], names=["key", "X"]
        )

        left = DataFrame(
            {"A": ["A0", "A1", "A2"], "B": ["B0", "B1", "B2"]}, index=index_left
        )

        index_right = MultiIndex.from_tuples(
            [("K0", "Y0"), ("K1", "Y1"), ("K2", "Y2"), ("K2", "Y3")], names=["key", "Y"]
        )

        right = DataFrame(
            {"C": ["C0", "C1", "C2", "C3"], "D": ["D0", "D1", "D2", "D3"]},
            index=index_right,
        )

        result = left.join(right)
        expected = merge(
            left.reset_index(), right.reset_index(), on=["key"], how="inner"
        ).set_index(["key", "X", "Y"])

        tm.assert_frame_equal(result, expected)

    def test_join_multi_wrong_order(self):
        # GH 25760
        # GH 28956

        midx1 = MultiIndex.from_product([[1, 2], [3, 4]], names=["a", "b"])
        midx3 = MultiIndex.from_tuples([(4, 1), (3, 2), (3, 1)], names=["b", "a"])

        left = DataFrame(index=midx1, data={"x": [10, 20, 30, 40]})
        right = DataFrame(index=midx3, data={"y": ["foo", "bar", "fing"]})

        result = left.join(right)

        expected = DataFrame(
            index=midx1,
            data={"x": [10, 20, 30, 40], "y": ["fing", "foo", "bar", np.nan]},
        )

        tm.assert_frame_equal(result, expected)
