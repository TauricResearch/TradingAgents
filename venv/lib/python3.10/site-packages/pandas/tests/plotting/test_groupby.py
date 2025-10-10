""" Test cases for GroupBy.plot """


import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    Series,
)
from pandas.tests.plotting.common import (
    _check_axes_shape,
    _check_legend_labels,
)

pytest.importorskip("matplotlib")


class TestDataFrameGroupByPlots:
    def test_series_groupby_plotting_nominally_works(self):
        n = 10
        weight = Series(np.random.default_rng(2).normal(166, 20, size=n))
        gender = np.random.default_rng(2).choice(["male", "female"], size=n)

        weight.groupby(gender).plot()

    def test_series_groupby_plotting_nominally_works_hist(self):
        n = 10
        height = Series(np.random.default_rng(2).normal(60, 10, size=n))
        gender = np.random.default_rng(2).choice(["male", "female"], size=n)
        height.groupby(gender).hist()

    def test_series_groupby_plotting_nominally_works_alpha(self):
        n = 10
        height = Series(np.random.default_rng(2).normal(60, 10, size=n))
        gender = np.random.default_rng(2).choice(["male", "female"], size=n)
        # Regression test for GH8733
        height.groupby(gender).plot(alpha=0.5)

    def test_plotting_with_float_index_works(self):
        # GH 7025
        df = DataFrame(
            {
                "def": [1, 1, 1, 2, 2, 2, 3, 3, 3],
                "val": np.random.default_rng(2).standard_normal(9),
            },
            index=[1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
        )

        df.groupby("def")["val"].plot()

    def test_plotting_with_float_index_works_apply(self):
        # GH 7025
        df = DataFrame(
            {
                "def": [1, 1, 1, 2, 2, 2, 3, 3, 3],
                "val": np.random.default_rng(2).standard_normal(9),
            },
            index=[1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
        )
        df.groupby("def")["val"].apply(lambda x: x.plot())

    def test_hist_single_row(self):
        # GH10214
        bins = np.arange(80, 100 + 2, 1)
        df = DataFrame({"Name": ["AAA", "BBB"], "ByCol": [1, 2], "Mark": [85, 89]})
        df["Mark"].hist(by=df["ByCol"], bins=bins)

    def test_hist_single_row_single_bycol(self):
        # GH10214
        bins = np.arange(80, 100 + 2, 1)
        df = DataFrame({"Name": ["AAA"], "ByCol": [1], "Mark": [85]})
        df["Mark"].hist(by=df["ByCol"], bins=bins)

    def test_plot_submethod_works(self):
        df = DataFrame({"x": [1, 2, 3, 4, 5], "y": [1, 2, 3, 2, 1], "z": list("ababa")})
        df.groupby("z").plot.scatter("x", "y")

    def test_plot_submethod_works_line(self):
        df = DataFrame({"x": [1, 2, 3, 4, 5], "y": [1, 2, 3, 2, 1], "z": list("ababa")})
        df.groupby("z")["x"].plot.line()

    def test_plot_kwargs(self):
        df = DataFrame({"x": [1, 2, 3, 4, 5], "y": [1, 2, 3, 2, 1], "z": list("ababa")})

        res = df.groupby("z").plot(kind="scatter", x="x", y="y")
        # check that a scatter plot is effectively plotted: the axes should
        # contain a PathCollection from the scatter plot (GH11805)
        assert len(res["a"].collections) == 1

    def test_plot_kwargs_scatter(self):
        df = DataFrame({"x": [1, 2, 3, 4, 5], "y": [1, 2, 3, 2, 1], "z": list("ababa")})
        res = df.groupby("z").plot.scatter(x="x", y="y")
        assert len(res["a"].collections) == 1

    @pytest.mark.parametrize("column, expected_axes_num", [(None, 2), ("b", 1)])
    def test_groupby_hist_frame_with_legend(self, column, expected_axes_num):
        # GH 6279 - DataFrameGroupBy histogram can have a legend
        expected_layout = (1, expected_axes_num)
        expected_labels = column or [["a"], ["b"]]

        index = Index(15 * ["1"] + 15 * ["2"], name="c")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((30, 2)),
            index=index,
            columns=["a", "b"],
        )
        g = df.groupby("c")

        for axes in g.hist(legend=True, column=column):
            _check_axes_shape(axes, axes_num=expected_axes_num, layout=expected_layout)
            for ax, expected_label in zip(axes[0], expected_labels):
                _check_legend_labels(ax, expected_label)

    @pytest.mark.parametrize("column", [None, "b"])
    def test_groupby_hist_frame_with_legend_raises(self, column):
        # GH 6279 - DataFrameGroupBy histogram with legend and label raises
        index = Index(15 * ["1"] + 15 * ["2"], name="c")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((30, 2)),
            index=index,
            columns=["a", "b"],
        )
        g = df.groupby("c")

        with pytest.raises(ValueError, match="Cannot use both legend and label"):
            g.hist(legend=True, column=column, label="d")

    def test_groupby_hist_series_with_legend(self):
        # GH 6279 - SeriesGroupBy histogram can have a legend
        index = Index(15 * ["1"] + 15 * ["2"], name="c")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((30, 2)),
            index=index,
            columns=["a", "b"],
        )
        g = df.groupby("c")

        for ax in g["a"].hist(legend=True):
            _check_axes_shape(ax, axes_num=1, layout=(1, 1))
            _check_legend_labels(ax, ["1", "2"])

    def test_groupby_hist_series_with_legend_raises(self):
        # GH 6279 - SeriesGroupBy histogram with legend and label raises
        index = Index(15 * ["1"] + 15 * ["2"], name="c")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((30, 2)),
            index=index,
            columns=["a", "b"],
        )
        g = df.groupby("c")

        with pytest.raises(ValueError, match="Cannot use both legend and label"):
            g.hist(legend=True, label="d")
