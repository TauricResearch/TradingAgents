import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    date_range,
)
from pandas.tests.plotting.common import (
    _check_legend_labels,
    _check_legend_marker,
    _check_text_labels,
)
from pandas.util.version import Version

mpl = pytest.importorskip("matplotlib")


class TestFrameLegend:
    @pytest.mark.xfail(
        reason=(
            "Open bug in matplotlib "
            "https://github.com/matplotlib/matplotlib/issues/11357"
        )
    )
    def test_mixed_yerr(self):
        # https://github.com/pandas-dev/pandas/issues/39522
        from matplotlib.collections import LineCollection
        from matplotlib.lines import Line2D

        df = DataFrame([{"x": 1, "a": 1, "b": 1}, {"x": 2, "a": 2, "b": 3}])

        ax = df.plot("x", "a", c="orange", yerr=0.1, label="orange")
        df.plot("x", "b", c="blue", yerr=None, ax=ax, label="blue")

        legend = ax.get_legend()
        if Version(mpl.__version__) < Version("3.7"):
            result_handles = legend.legendHandles
        else:
            result_handles = legend.legend_handles

        assert isinstance(result_handles[0], LineCollection)
        assert isinstance(result_handles[1], Line2D)

    def test_legend_false(self):
        # https://github.com/pandas-dev/pandas/issues/40044
        df = DataFrame({"a": [1, 1], "b": [2, 3]})
        df2 = DataFrame({"d": [2.5, 2.5]})

        ax = df.plot(legend=True, color={"a": "blue", "b": "green"}, secondary_y="b")
        df2.plot(legend=True, color={"d": "red"}, ax=ax)
        legend = ax.get_legend()
        if Version(mpl.__version__) < Version("3.7"):
            handles = legend.legendHandles
        else:
            handles = legend.legend_handles
        result = [handle.get_color() for handle in handles]
        expected = ["blue", "green", "red"]
        assert result == expected

    @pytest.mark.parametrize("kind", ["line", "bar", "barh", "kde", "area", "hist"])
    def test_df_legend_labels(self, kind):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).random((3, 3)), columns=["a", "b", "c"])
        df2 = DataFrame(
            np.random.default_rng(2).random((3, 3)), columns=["d", "e", "f"]
        )
        df3 = DataFrame(
            np.random.default_rng(2).random((3, 3)), columns=["g", "h", "i"]
        )
        df4 = DataFrame(
            np.random.default_rng(2).random((3, 3)), columns=["j", "k", "l"]
        )

        ax = df.plot(kind=kind, legend=True)
        _check_legend_labels(ax, labels=df.columns)

        ax = df2.plot(kind=kind, legend=False, ax=ax)
        _check_legend_labels(ax, labels=df.columns)

        ax = df3.plot(kind=kind, legend=True, ax=ax)
        _check_legend_labels(ax, labels=df.columns.union(df3.columns))

        ax = df4.plot(kind=kind, legend="reverse", ax=ax)
        expected = list(df.columns.union(df3.columns)) + list(reversed(df4.columns))
        _check_legend_labels(ax, labels=expected)

    def test_df_legend_labels_secondary_y(self):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).random((3, 3)), columns=["a", "b", "c"])
        df2 = DataFrame(
            np.random.default_rng(2).random((3, 3)), columns=["d", "e", "f"]
        )
        df3 = DataFrame(
            np.random.default_rng(2).random((3, 3)), columns=["g", "h", "i"]
        )
        # Secondary Y
        ax = df.plot(legend=True, secondary_y="b")
        _check_legend_labels(ax, labels=["a", "b (right)", "c"])
        ax = df2.plot(legend=False, ax=ax)
        _check_legend_labels(ax, labels=["a", "b (right)", "c"])
        ax = df3.plot(kind="bar", legend=True, secondary_y="h", ax=ax)
        _check_legend_labels(ax, labels=["a", "b (right)", "c", "g", "h (right)", "i"])

    def test_df_legend_labels_time_series(self):
        # Time Series
        pytest.importorskip("scipy")
        ind = date_range("1/1/2014", periods=3)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["a", "b", "c"],
            index=ind,
        )
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["d", "e", "f"],
            index=ind,
        )
        df3 = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["g", "h", "i"],
            index=ind,
        )
        ax = df.plot(legend=True, secondary_y="b")
        _check_legend_labels(ax, labels=["a", "b (right)", "c"])
        ax = df2.plot(legend=False, ax=ax)
        _check_legend_labels(ax, labels=["a", "b (right)", "c"])
        ax = df3.plot(legend=True, ax=ax)
        _check_legend_labels(ax, labels=["a", "b (right)", "c", "g", "h", "i"])

    def test_df_legend_labels_time_series_scatter(self):
        # Time Series
        pytest.importorskip("scipy")
        ind = date_range("1/1/2014", periods=3)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["a", "b", "c"],
            index=ind,
        )
        df2 = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["d", "e", "f"],
            index=ind,
        )
        df3 = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["g", "h", "i"],
            index=ind,
        )
        # scatter
        ax = df.plot.scatter(x="a", y="b", label="data1")
        _check_legend_labels(ax, labels=["data1"])
        ax = df2.plot.scatter(x="d", y="e", legend=False, label="data2", ax=ax)
        _check_legend_labels(ax, labels=["data1"])
        ax = df3.plot.scatter(x="g", y="h", label="data3", ax=ax)
        _check_legend_labels(ax, labels=["data1", "data3"])

    def test_df_legend_labels_time_series_no_mutate(self):
        pytest.importorskip("scipy")
        ind = date_range("1/1/2014", periods=3)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=["a", "b", "c"],
            index=ind,
        )
        # ensure label args pass through and
        # index name does not mutate
        # column names don't mutate
        df5 = df.set_index("a")
        ax = df5.plot(y="b")
        _check_legend_labels(ax, labels=["b"])
        ax = df5.plot(y="b", label="LABEL_b")
        _check_legend_labels(ax, labels=["LABEL_b"])
        _check_text_labels(ax.xaxis.get_label(), "a")
        ax = df5.plot(y="c", label="LABEL_c", ax=ax)
        _check_legend_labels(ax, labels=["LABEL_b", "LABEL_c"])
        assert df5.columns.tolist() == ["b", "c"]

    def test_missing_marker_multi_plots_on_same_ax(self):
        # GH 18222
        df = DataFrame(data=[[1, 1, 1, 1], [2, 2, 4, 8]], columns=["x", "r", "g", "b"])
        _, ax = mpl.pyplot.subplots(nrows=1, ncols=3)
        # Left plot
        df.plot(x="x", y="r", linewidth=0, marker="o", color="r", ax=ax[0])
        df.plot(x="x", y="g", linewidth=1, marker="x", color="g", ax=ax[0])
        df.plot(x="x", y="b", linewidth=1, marker="o", color="b", ax=ax[0])
        _check_legend_labels(ax[0], labels=["r", "g", "b"])
        _check_legend_marker(ax[0], expected_markers=["o", "x", "o"])
        # Center plot
        df.plot(x="x", y="b", linewidth=1, marker="o", color="b", ax=ax[1])
        df.plot(x="x", y="r", linewidth=0, marker="o", color="r", ax=ax[1])
        df.plot(x="x", y="g", linewidth=1, marker="x", color="g", ax=ax[1])
        _check_legend_labels(ax[1], labels=["b", "r", "g"])
        _check_legend_marker(ax[1], expected_markers=["o", "o", "x"])
        # Right plot
        df.plot(x="x", y="g", linewidth=1, marker="x", color="g", ax=ax[2])
        df.plot(x="x", y="b", linewidth=1, marker="o", color="b", ax=ax[2])
        df.plot(x="x", y="r", linewidth=0, marker="o", color="r", ax=ax[2])
        _check_legend_labels(ax[2], labels=["g", "b", "r"])
        _check_legend_marker(ax[2], expected_markers=["x", "o", "o"])

    def test_legend_name(self):
        multi = DataFrame(
            np.random.default_rng(2).standard_normal((4, 4)),
            columns=[np.array(["a", "a", "b", "b"]), np.array(["x", "y", "x", "y"])],
        )
        multi.columns.names = ["group", "individual"]

        ax = multi.plot()
        leg_title = ax.legend_.get_title()
        _check_text_labels(leg_title, "group,individual")

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot(legend=True, ax=ax)
        leg_title = ax.legend_.get_title()
        _check_text_labels(leg_title, "group,individual")

        df.columns.name = "new"
        ax = df.plot(legend=False, ax=ax)
        leg_title = ax.legend_.get_title()
        _check_text_labels(leg_title, "group,individual")

        ax = df.plot(legend=True, ax=ax)
        leg_title = ax.legend_.get_title()
        _check_text_labels(leg_title, "new")

    @pytest.mark.parametrize(
        "kind",
        [
            "line",
            "bar",
            "barh",
            pytest.param("kde", marks=td.skip_if_no("scipy")),
            "area",
            "hist",
        ],
    )
    def test_no_legend(self, kind):
        df = DataFrame(np.random.default_rng(2).random((3, 3)), columns=["a", "b", "c"])
        ax = df.plot(kind=kind, legend=False)
        _check_legend_labels(ax, visible=False)

    def test_missing_markers_legend(self):
        # 14958
        df = DataFrame(
            np.random.default_rng(2).standard_normal((8, 3)), columns=["A", "B", "C"]
        )
        ax = df.plot(y=["A"], marker="x", linestyle="solid")
        df.plot(y=["B"], marker="o", linestyle="dotted", ax=ax)
        df.plot(y=["C"], marker="<", linestyle="dotted", ax=ax)

        _check_legend_labels(ax, labels=["A", "B", "C"])
        _check_legend_marker(ax, expected_markers=["x", "o", "<"])

    def test_missing_markers_legend_using_style(self):
        # 14563
        df = DataFrame(
            {
                "A": [1, 2, 3, 4, 5, 6],
                "B": [2, 4, 1, 3, 2, 4],
                "C": [3, 3, 2, 6, 4, 2],
                "X": [1, 2, 3, 4, 5, 6],
            }
        )

        _, ax = mpl.pyplot.subplots()
        for kind in "ABC":
            df.plot("X", kind, label=kind, ax=ax, style=".")

        _check_legend_labels(ax, labels=["A", "B", "C"])
        _check_legend_marker(ax, expected_markers=[".", ".", "."])
