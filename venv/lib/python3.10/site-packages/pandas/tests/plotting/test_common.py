import pytest

from pandas import DataFrame
from pandas.tests.plotting.common import (
    _check_plot_works,
    _check_ticks_props,
    _gen_two_subplots,
)

plt = pytest.importorskip("matplotlib.pyplot")


class TestCommon:
    def test__check_ticks_props(self):
        # GH 34768
        df = DataFrame({"b": [0, 1, 0], "a": [1, 2, 3]})
        ax = _check_plot_works(df.plot, rot=30)
        ax.yaxis.set_tick_params(rotation=30)
        msg = "expected 0.00000 but got "
        with pytest.raises(AssertionError, match=msg):
            _check_ticks_props(ax, xrot=0)
        with pytest.raises(AssertionError, match=msg):
            _check_ticks_props(ax, xlabelsize=0)
        with pytest.raises(AssertionError, match=msg):
            _check_ticks_props(ax, yrot=0)
        with pytest.raises(AssertionError, match=msg):
            _check_ticks_props(ax, ylabelsize=0)

    def test__gen_two_subplots_with_ax(self):
        fig = plt.gcf()
        gen = _gen_two_subplots(f=lambda **kwargs: None, fig=fig, ax="test")
        # On the first yield, no subplot should be added since ax was passed
        next(gen)
        assert fig.get_axes() == []
        # On the second, the one axis should match fig.subplot(2, 1, 2)
        next(gen)
        axes = fig.get_axes()
        assert len(axes) == 1
        subplot_geometry = list(axes[0].get_subplotspec().get_geometry()[:-1])
        subplot_geometry[-1] += 1
        assert subplot_geometry == [2, 1, 2]

    def test_colorbar_layout(self):
        fig = plt.figure()

        axes = fig.subplot_mosaic(
            """
            AB
            CC
            """
        )

        x = [1, 2, 3]
        y = [1, 2, 3]

        cs0 = axes["A"].scatter(x, y)
        axes["B"].scatter(x, y)

        fig.colorbar(cs0, ax=[axes["A"], axes["B"]], location="right")
        DataFrame(x).plot(ax=axes["C"])
