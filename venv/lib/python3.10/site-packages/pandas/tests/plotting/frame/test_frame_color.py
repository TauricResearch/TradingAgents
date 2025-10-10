""" Test cases for DataFrame.plot """
import re

import numpy as np
import pytest

import pandas as pd
from pandas import DataFrame
import pandas._testing as tm
from pandas.tests.plotting.common import (
    _check_colors,
    _check_plot_works,
    _unpack_cycler,
)
from pandas.util.version import Version

mpl = pytest.importorskip("matplotlib")
plt = pytest.importorskip("matplotlib.pyplot")
cm = pytest.importorskip("matplotlib.cm")


def _check_colors_box(bp, box_c, whiskers_c, medians_c, caps_c="k", fliers_c=None):
    if fliers_c is None:
        fliers_c = "k"
    _check_colors(bp["boxes"], linecolors=[box_c] * len(bp["boxes"]))
    _check_colors(bp["whiskers"], linecolors=[whiskers_c] * len(bp["whiskers"]))
    _check_colors(bp["medians"], linecolors=[medians_c] * len(bp["medians"]))
    _check_colors(bp["fliers"], linecolors=[fliers_c] * len(bp["fliers"]))
    _check_colors(bp["caps"], linecolors=[caps_c] * len(bp["caps"]))


class TestDataFrameColor:
    @pytest.mark.parametrize(
        "color", ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]
    )
    def test_mpl2_color_cycle_str(self, color):
        # GH 15516
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=["a", "b", "c"]
        )
        _check_plot_works(df.plot, color=color)

    def test_color_single_series_list(self):
        # GH 3486
        df = DataFrame({"A": [1, 2, 3]})
        _check_plot_works(df.plot, color=["red"])

    @pytest.mark.parametrize("color", [(1, 0, 0), (1, 0, 0, 0.5)])
    def test_rgb_tuple_color(self, color):
        # GH 16695
        df = DataFrame({"x": [1, 2], "y": [3, 4]})
        _check_plot_works(df.plot, x="x", y="y", color=color)

    def test_color_empty_string(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 2)))
        with pytest.raises(ValueError, match="Invalid color argument:"):
            df.plot(color="")

    def test_color_and_style_arguments(self):
        df = DataFrame({"x": [1, 2], "y": [3, 4]})
        # passing both 'color' and 'style' arguments should be allowed
        # if there is no color symbol in the style strings:
        ax = df.plot(color=["red", "black"], style=["-", "--"])
        # check that the linestyles are correctly set:
        linestyle = [line.get_linestyle() for line in ax.lines]
        assert linestyle == ["-", "--"]
        # check that the colors are correctly set:
        color = [line.get_color() for line in ax.lines]
        assert color == ["red", "black"]
        # passing both 'color' and 'style' arguments should not be allowed
        # if there is a color symbol in the style strings:
        msg = (
            "Cannot pass 'style' string with a color symbol and 'color' keyword "
            "argument. Please use one or the other or pass 'style' without a color "
            "symbol"
        )
        with pytest.raises(ValueError, match=msg):
            df.plot(color=["red", "black"], style=["k-", "r--"])

    @pytest.mark.parametrize(
        "color, expected",
        [
            ("green", ["green"] * 4),
            (["yellow", "red", "green", "blue"], ["yellow", "red", "green", "blue"]),
        ],
    )
    def test_color_and_marker(self, color, expected):
        # GH 21003
        df = DataFrame(np.random.default_rng(2).random((7, 4)))
        ax = df.plot(color=color, style="d--")
        # check colors
        result = [i.get_color() for i in ax.lines]
        assert result == expected
        # check markers and linestyles
        assert all(i.get_linestyle() == "--" for i in ax.lines)
        assert all(i.get_marker() == "d" for i in ax.lines)

    def test_bar_colors(self):
        default_colors = _unpack_cycler(plt.rcParams)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot.bar()
        _check_colors(ax.patches[::5], facecolors=default_colors[:5])

    def test_bar_colors_custom(self):
        custom_colors = "rgcby"
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot.bar(color=custom_colors)
        _check_colors(ax.patches[::5], facecolors=custom_colors)

    @pytest.mark.parametrize("colormap", ["jet", cm.jet])
    def test_bar_colors_cmap(self, colormap):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))

        ax = df.plot.bar(colormap=colormap)
        rgba_colors = [cm.jet(n) for n in np.linspace(0, 1, 5)]
        _check_colors(ax.patches[::5], facecolors=rgba_colors)

    def test_bar_colors_single_col(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.loc[:, [0]].plot.bar(color="DodgerBlue")
        _check_colors([ax.patches[0]], facecolors=["DodgerBlue"])

    def test_bar_colors_green(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot(kind="bar", color="green")
        _check_colors(ax.patches[::5], facecolors=["green"] * 5)

    def test_bar_user_colors(self):
        df = DataFrame(
            {"A": range(4), "B": range(1, 5), "color": ["red", "blue", "blue", "red"]}
        )
        # This should *only* work when `y` is specified, else
        # we use one color per column
        ax = df.plot.bar(y="A", color=df["color"])
        result = [p.get_facecolor() for p in ax.patches]
        expected = [
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0, 1.0),
            (0.0, 0.0, 1.0, 1.0),
            (1.0, 0.0, 0.0, 1.0),
        ]
        assert result == expected

    def test_if_scatterplot_colorbar_affects_xaxis_visibility(self):
        # addressing issue #10611, to ensure colobar does not
        # interfere with x-axis label and ticklabels with
        # ipython inline backend.
        random_array = np.random.default_rng(2).random((10, 3))
        df = DataFrame(random_array, columns=["A label", "B label", "C label"])

        ax1 = df.plot.scatter(x="A label", y="B label")
        ax2 = df.plot.scatter(x="A label", y="B label", c="C label")

        vis1 = [vis.get_visible() for vis in ax1.xaxis.get_minorticklabels()]
        vis2 = [vis.get_visible() for vis in ax2.xaxis.get_minorticklabels()]
        assert vis1 == vis2

        vis1 = [vis.get_visible() for vis in ax1.xaxis.get_majorticklabels()]
        vis2 = [vis.get_visible() for vis in ax2.xaxis.get_majorticklabels()]
        assert vis1 == vis2

        assert (
            ax1.xaxis.get_label().get_visible() == ax2.xaxis.get_label().get_visible()
        )

    def test_if_hexbin_xaxis_label_is_visible(self):
        # addressing issue #10678, to ensure colobar does not
        # interfere with x-axis label and ticklabels with
        # ipython inline backend.
        random_array = np.random.default_rng(2).random((10, 3))
        df = DataFrame(random_array, columns=["A label", "B label", "C label"])

        ax = df.plot.hexbin("A label", "B label", gridsize=12)
        assert all(vis.get_visible() for vis in ax.xaxis.get_minorticklabels())
        assert all(vis.get_visible() for vis in ax.xaxis.get_majorticklabels())
        assert ax.xaxis.get_label().get_visible()

    def test_if_scatterplot_colorbars_are_next_to_parent_axes(self):
        random_array = np.random.default_rng(2).random((10, 3))
        df = DataFrame(random_array, columns=["A label", "B label", "C label"])

        fig, axes = plt.subplots(1, 2)
        df.plot.scatter("A label", "B label", c="C label", ax=axes[0])
        df.plot.scatter("A label", "B label", c="C label", ax=axes[1])
        plt.tight_layout()

        points = np.array([ax.get_position().get_points() for ax in fig.axes])
        axes_x_coords = points[:, :, 0]
        parent_distance = axes_x_coords[1, :] - axes_x_coords[0, :]
        colorbar_distance = axes_x_coords[3, :] - axes_x_coords[2, :]
        assert np.isclose(parent_distance, colorbar_distance, atol=1e-7).all()

    @pytest.mark.parametrize("cmap", [None, "Greys"])
    def test_scatter_with_c_column_name_with_colors(self, cmap):
        # https://github.com/pandas-dev/pandas/issues/34316

        df = DataFrame(
            [[5.1, 3.5], [4.9, 3.0], [7.0, 3.2], [6.4, 3.2], [5.9, 3.0]],
            columns=["length", "width"],
        )
        df["species"] = ["r", "r", "g", "g", "b"]
        if cmap is not None:
            with tm.assert_produces_warning(UserWarning, check_stacklevel=False):
                ax = df.plot.scatter(x=0, y=1, cmap=cmap, c="species")
        else:
            ax = df.plot.scatter(x=0, y=1, c="species", cmap=cmap)
        assert ax.collections[0].colorbar is None

    def test_scatter_colors(self):
        df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3], "c": [1, 2, 3]})
        with pytest.raises(TypeError, match="Specify exactly one of `c` and `color`"):
            df.plot.scatter(x="a", y="b", c="c", color="green")

    def test_scatter_colors_not_raising_warnings(self):
        # GH-53908. Do not raise UserWarning: No data for colormapping
        # provided via 'c'. Parameters 'cmap' will be ignored
        df = DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
        with tm.assert_produces_warning(None):
            df.plot.scatter(x="x", y="y", c="b")

    def test_scatter_colors_default(self):
        df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3], "c": [1, 2, 3]})
        default_colors = _unpack_cycler(mpl.pyplot.rcParams)

        ax = df.plot.scatter(x="a", y="b", c="c")
        tm.assert_numpy_array_equal(
            ax.collections[0].get_facecolor()[0],
            np.array(mpl.colors.ColorConverter.to_rgba(default_colors[0])),
        )

    def test_scatter_colors_white(self):
        df = DataFrame({"a": [1, 2, 3], "b": [1, 2, 3], "c": [1, 2, 3]})
        ax = df.plot.scatter(x="a", y="b", color="white")
        tm.assert_numpy_array_equal(
            ax.collections[0].get_facecolor()[0],
            np.array([1, 1, 1, 1], dtype=np.float64),
        )

    def test_scatter_colorbar_different_cmap(self):
        # GH 33389
        df = DataFrame({"x": [1, 2, 3], "y": [1, 3, 2], "c": [1, 2, 3]})
        df["x2"] = df["x"] + 1

        _, ax = plt.subplots()
        df.plot("x", "y", c="c", kind="scatter", cmap="cividis", ax=ax)
        df.plot("x2", "y", c="c", kind="scatter", cmap="magma", ax=ax)

        assert ax.collections[0].cmap.name == "cividis"
        assert ax.collections[1].cmap.name == "magma"

    def test_line_colors(self):
        custom_colors = "rgcby"
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))

        ax = df.plot(color=custom_colors)
        _check_colors(ax.get_lines(), linecolors=custom_colors)

        plt.close("all")

        ax2 = df.plot(color=custom_colors)
        lines2 = ax2.get_lines()

        for l1, l2 in zip(ax.get_lines(), lines2):
            assert l1.get_color() == l2.get_color()

    @pytest.mark.parametrize("colormap", ["jet", cm.jet])
    def test_line_colors_cmap(self, colormap):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot(colormap=colormap)
        rgba_colors = [cm.jet(n) for n in np.linspace(0, 1, len(df))]
        _check_colors(ax.get_lines(), linecolors=rgba_colors)

    def test_line_colors_single_col(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # make color a list if plotting one column frame
        # handles cases like df.plot(color='DodgerBlue')
        ax = df.loc[:, [0]].plot(color="DodgerBlue")
        _check_colors(ax.lines, linecolors=["DodgerBlue"])

    def test_line_colors_single_color(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot(color="red")
        _check_colors(ax.get_lines(), linecolors=["red"] * 5)

    def test_line_colors_hex(self):
        # GH 10299
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        custom_colors = ["#FF0000", "#0000FF", "#FFFF00", "#000000", "#FFFFFF"]
        ax = df.plot(color=custom_colors)
        _check_colors(ax.get_lines(), linecolors=custom_colors)

    def test_dont_modify_colors(self):
        colors = ["r", "g", "b"]
        DataFrame(np.random.default_rng(2).random((10, 2))).plot(color=colors)
        assert len(colors) == 3

    def test_line_colors_and_styles_subplots(self):
        # GH 9894
        default_colors = _unpack_cycler(mpl.pyplot.rcParams)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))

        axes = df.plot(subplots=True)
        for ax, c in zip(axes, list(default_colors)):
            _check_colors(ax.get_lines(), linecolors=[c])

    @pytest.mark.parametrize("color", ["k", "green"])
    def test_line_colors_and_styles_subplots_single_color_str(self, color):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        axes = df.plot(subplots=True, color=color)
        for ax in axes:
            _check_colors(ax.get_lines(), linecolors=[color])

    @pytest.mark.parametrize("color", ["rgcby", list("rgcby")])
    def test_line_colors_and_styles_subplots_custom_colors(self, color):
        # GH 9894
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        axes = df.plot(color=color, subplots=True)
        for ax, c in zip(axes, list(color)):
            _check_colors(ax.get_lines(), linecolors=[c])

    def test_line_colors_and_styles_subplots_colormap_hex(self):
        # GH 9894
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # GH 10299
        custom_colors = ["#FF0000", "#0000FF", "#FFFF00", "#000000", "#FFFFFF"]
        axes = df.plot(color=custom_colors, subplots=True)
        for ax, c in zip(axes, list(custom_colors)):
            _check_colors(ax.get_lines(), linecolors=[c])

    @pytest.mark.parametrize("cmap", ["jet", cm.jet])
    def test_line_colors_and_styles_subplots_colormap_subplot(self, cmap):
        # GH 9894
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        rgba_colors = [cm.jet(n) for n in np.linspace(0, 1, len(df))]
        axes = df.plot(colormap=cmap, subplots=True)
        for ax, c in zip(axes, rgba_colors):
            _check_colors(ax.get_lines(), linecolors=[c])

    def test_line_colors_and_styles_subplots_single_col(self):
        # GH 9894
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # make color a list if plotting one column frame
        # handles cases like df.plot(color='DodgerBlue')
        axes = df.loc[:, [0]].plot(color="DodgerBlue", subplots=True)
        _check_colors(axes[0].lines, linecolors=["DodgerBlue"])

    def test_line_colors_and_styles_subplots_single_char(self):
        # GH 9894
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # single character style
        axes = df.plot(style="r", subplots=True)
        for ax in axes:
            _check_colors(ax.get_lines(), linecolors=["r"])

    def test_line_colors_and_styles_subplots_list_styles(self):
        # GH 9894
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # list of styles
        styles = list("rgcby")
        axes = df.plot(style=styles, subplots=True)
        for ax, c in zip(axes, styles):
            _check_colors(ax.get_lines(), linecolors=[c])

    def test_area_colors(self):
        from matplotlib.collections import PolyCollection

        custom_colors = "rgcby"
        df = DataFrame(np.random.default_rng(2).random((5, 5)))

        ax = df.plot.area(color=custom_colors)
        _check_colors(ax.get_lines(), linecolors=custom_colors)
        poly = [o for o in ax.get_children() if isinstance(o, PolyCollection)]
        _check_colors(poly, facecolors=custom_colors)

        handles, _ = ax.get_legend_handles_labels()
        _check_colors(handles, facecolors=custom_colors)

        for h in handles:
            assert h.get_alpha() is None

    def test_area_colors_poly(self):
        from matplotlib import cm
        from matplotlib.collections import PolyCollection

        df = DataFrame(np.random.default_rng(2).random((5, 5)))
        ax = df.plot.area(colormap="jet")
        jet_colors = [cm.jet(n) for n in np.linspace(0, 1, len(df))]
        _check_colors(ax.get_lines(), linecolors=jet_colors)
        poly = [o for o in ax.get_children() if isinstance(o, PolyCollection)]
        _check_colors(poly, facecolors=jet_colors)

        handles, _ = ax.get_legend_handles_labels()
        _check_colors(handles, facecolors=jet_colors)
        for h in handles:
            assert h.get_alpha() is None

    def test_area_colors_stacked_false(self):
        from matplotlib import cm
        from matplotlib.collections import PolyCollection

        df = DataFrame(np.random.default_rng(2).random((5, 5)))
        jet_colors = [cm.jet(n) for n in np.linspace(0, 1, len(df))]
        # When stacked=False, alpha is set to 0.5
        ax = df.plot.area(colormap=cm.jet, stacked=False)
        _check_colors(ax.get_lines(), linecolors=jet_colors)
        poly = [o for o in ax.get_children() if isinstance(o, PolyCollection)]
        jet_with_alpha = [(c[0], c[1], c[2], 0.5) for c in jet_colors]
        _check_colors(poly, facecolors=jet_with_alpha)

        handles, _ = ax.get_legend_handles_labels()
        linecolors = jet_with_alpha
        _check_colors(handles[: len(jet_colors)], linecolors=linecolors)
        for h in handles:
            assert h.get_alpha() == 0.5

    def test_hist_colors(self):
        default_colors = _unpack_cycler(mpl.pyplot.rcParams)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot.hist()
        _check_colors(ax.patches[::10], facecolors=default_colors[:5])

    def test_hist_colors_single_custom(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        custom_colors = "rgcby"
        ax = df.plot.hist(color=custom_colors)
        _check_colors(ax.patches[::10], facecolors=custom_colors)

    @pytest.mark.parametrize("colormap", ["jet", cm.jet])
    def test_hist_colors_cmap(self, colormap):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot.hist(colormap=colormap)
        rgba_colors = [cm.jet(n) for n in np.linspace(0, 1, 5)]
        _check_colors(ax.patches[::10], facecolors=rgba_colors)

    def test_hist_colors_single_col(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.loc[:, [0]].plot.hist(color="DodgerBlue")
        _check_colors([ax.patches[0]], facecolors=["DodgerBlue"])

    def test_hist_colors_single_color(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot(kind="hist", color="green")
        _check_colors(ax.patches[::10], facecolors=["green"] * 5)

    def test_kde_colors(self):
        pytest.importorskip("scipy")
        custom_colors = "rgcby"
        df = DataFrame(np.random.default_rng(2).random((5, 5)))

        ax = df.plot.kde(color=custom_colors)
        _check_colors(ax.get_lines(), linecolors=custom_colors)

    @pytest.mark.parametrize("colormap", ["jet", cm.jet])
    def test_kde_colors_cmap(self, colormap):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        ax = df.plot.kde(colormap=colormap)
        rgba_colors = [cm.jet(n) for n in np.linspace(0, 1, len(df))]
        _check_colors(ax.get_lines(), linecolors=rgba_colors)

    def test_kde_colors_and_styles_subplots(self):
        pytest.importorskip("scipy")
        default_colors = _unpack_cycler(mpl.pyplot.rcParams)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))

        axes = df.plot(kind="kde", subplots=True)
        for ax, c in zip(axes, list(default_colors)):
            _check_colors(ax.get_lines(), linecolors=[c])

    @pytest.mark.parametrize("colormap", ["k", "red"])
    def test_kde_colors_and_styles_subplots_single_col_str(self, colormap):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        axes = df.plot(kind="kde", color=colormap, subplots=True)
        for ax in axes:
            _check_colors(ax.get_lines(), linecolors=[colormap])

    def test_kde_colors_and_styles_subplots_custom_color(self):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        custom_colors = "rgcby"
        axes = df.plot(kind="kde", color=custom_colors, subplots=True)
        for ax, c in zip(axes, list(custom_colors)):
            _check_colors(ax.get_lines(), linecolors=[c])

    @pytest.mark.parametrize("colormap", ["jet", cm.jet])
    def test_kde_colors_and_styles_subplots_cmap(self, colormap):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        rgba_colors = [cm.jet(n) for n in np.linspace(0, 1, len(df))]
        axes = df.plot(kind="kde", colormap=colormap, subplots=True)
        for ax, c in zip(axes, rgba_colors):
            _check_colors(ax.get_lines(), linecolors=[c])

    def test_kde_colors_and_styles_subplots_single_col(self):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # make color a list if plotting one column frame
        # handles cases like df.plot(color='DodgerBlue')
        axes = df.loc[:, [0]].plot(kind="kde", color="DodgerBlue", subplots=True)
        _check_colors(axes[0].lines, linecolors=["DodgerBlue"])

    def test_kde_colors_and_styles_subplots_single_char(self):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # list of styles
        # single character style
        axes = df.plot(kind="kde", style="r", subplots=True)
        for ax in axes:
            _check_colors(ax.get_lines(), linecolors=["r"])

    def test_kde_colors_and_styles_subplots_list(self):
        pytest.importorskip("scipy")
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # list of styles
        styles = list("rgcby")
        axes = df.plot(kind="kde", style=styles, subplots=True)
        for ax, c in zip(axes, styles):
            _check_colors(ax.get_lines(), linecolors=[c])

    def test_boxplot_colors(self):
        default_colors = _unpack_cycler(mpl.pyplot.rcParams)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        bp = df.plot.box(return_type="dict")
        _check_colors_box(
            bp,
            default_colors[0],
            default_colors[0],
            default_colors[2],
            default_colors[0],
        )

    def test_boxplot_colors_dict_colors(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        dict_colors = {
            "boxes": "#572923",
            "whiskers": "#982042",
            "medians": "#804823",
            "caps": "#123456",
        }
        bp = df.plot.box(color=dict_colors, sym="r+", return_type="dict")
        _check_colors_box(
            bp,
            dict_colors["boxes"],
            dict_colors["whiskers"],
            dict_colors["medians"],
            dict_colors["caps"],
            "r",
        )

    def test_boxplot_colors_default_color(self):
        default_colors = _unpack_cycler(mpl.pyplot.rcParams)
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # partial colors
        dict_colors = {"whiskers": "c", "medians": "m"}
        bp = df.plot.box(color=dict_colors, return_type="dict")
        _check_colors_box(bp, default_colors[0], "c", "m", default_colors[0])

    @pytest.mark.parametrize("colormap", ["jet", cm.jet])
    def test_boxplot_colors_cmap(self, colormap):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        bp = df.plot.box(colormap=colormap, return_type="dict")
        jet_colors = [cm.jet(n) for n in np.linspace(0, 1, 3)]
        _check_colors_box(
            bp, jet_colors[0], jet_colors[0], jet_colors[2], jet_colors[0]
        )

    def test_boxplot_colors_single(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # string color is applied to all artists except fliers
        bp = df.plot.box(color="DodgerBlue", return_type="dict")
        _check_colors_box(bp, "DodgerBlue", "DodgerBlue", "DodgerBlue", "DodgerBlue")

    def test_boxplot_colors_tuple(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        # tuple is also applied to all artists except fliers
        bp = df.plot.box(color=(0, 1, 0), sym="#123456", return_type="dict")
        _check_colors_box(bp, (0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 1, 0), "#123456")

    def test_boxplot_colors_invalid(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((5, 5)))
        msg = re.escape(
            "color dict contains invalid key 'xxxx'. The key must be either "
            "['boxes', 'whiskers', 'medians', 'caps']"
        )
        with pytest.raises(ValueError, match=msg):
            # Color contains invalid key results in ValueError
            df.plot.box(color={"boxes": "red", "xxxx": "blue"})

    def test_default_color_cycle(self):
        import cycler

        colors = list("rgbk")
        plt.rcParams["axes.prop_cycle"] = cycler.cycler("color", colors)

        df = DataFrame(np.random.default_rng(2).standard_normal((5, 3)))
        ax = df.plot()

        expected = _unpack_cycler(plt.rcParams)[:3]
        _check_colors(ax.get_lines(), linecolors=expected)

    def test_no_color_bar(self):
        df = DataFrame(
            {
                "A": np.random.default_rng(2).uniform(size=20),
                "B": np.random.default_rng(2).uniform(size=20),
                "C": np.arange(20) + np.random.default_rng(2).uniform(size=20),
            }
        )
        ax = df.plot.hexbin(x="A", y="B", colorbar=None)
        assert ax.collections[0].colorbar is None

    def test_mixing_cmap_and_colormap_raises(self):
        df = DataFrame(
            {
                "A": np.random.default_rng(2).uniform(size=20),
                "B": np.random.default_rng(2).uniform(size=20),
                "C": np.arange(20) + np.random.default_rng(2).uniform(size=20),
            }
        )
        msg = "Only specify one of `cmap` and `colormap`"
        with pytest.raises(TypeError, match=msg):
            df.plot.hexbin(x="A", y="B", cmap="YlGn", colormap="BuGn")

    def test_passed_bar_colors(self):
        color_tuples = [(0.9, 0, 0, 1), (0, 0.9, 0, 1), (0, 0, 0.9, 1)]
        colormap = mpl.colors.ListedColormap(color_tuples)
        barplot = DataFrame([[1, 2, 3]]).plot(kind="bar", cmap=colormap)
        assert color_tuples == [c.get_facecolor() for c in barplot.patches]

    def test_rcParams_bar_colors(self):
        color_tuples = [(0.9, 0, 0, 1), (0, 0.9, 0, 1), (0, 0, 0.9, 1)]
        with mpl.rc_context(rc={"axes.prop_cycle": mpl.cycler("color", color_tuples)}):
            barplot = DataFrame([[1, 2, 3]]).plot(kind="bar")
        assert color_tuples == [c.get_facecolor() for c in barplot.patches]

    def test_colors_of_columns_with_same_name(self):
        # ISSUE 11136 -> https://github.com/pandas-dev/pandas/issues/11136
        # Creating a DataFrame with duplicate column labels and testing colors of them.
        df = DataFrame({"b": [0, 1, 0], "a": [1, 2, 3]})
        df1 = DataFrame({"a": [2, 4, 6]})
        df_concat = pd.concat([df, df1], axis=1)
        result = df_concat.plot()
        legend = result.get_legend()
        if Version(mpl.__version__) < Version("3.7"):
            handles = legend.legendHandles
        else:
            handles = legend.legend_handles
        for legend, line in zip(handles, result.lines):
            assert legend.get_color() == line.get_color()

    def test_invalid_colormap(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 2)), columns=["A", "B"]
        )
        msg = "(is not a valid value)|(is not a known colormap)"
        with pytest.raises((ValueError, KeyError), match=msg):
            df.plot(colormap="invalid_colormap")

    def test_dataframe_none_color(self):
        # GH51953
        df = DataFrame([[1, 2, 3]])
        ax = df.plot(color=None)
        expected = _unpack_cycler(mpl.pyplot.rcParams)[:3]
        _check_colors(ax.get_lines(), linecolors=expected)
