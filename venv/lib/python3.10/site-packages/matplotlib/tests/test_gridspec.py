import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import pytest


def test_equal():
    gs = gridspec.GridSpec(2, 1)
    assert gs[0, 0] == gs[0, 0]
    assert gs[:, 0] == gs[:, 0]


def test_width_ratios():
    """
    Addresses issue #5835.
    See at https://github.com/matplotlib/matplotlib/issues/5835.
    """
    with pytest.raises(ValueError):
        gridspec.GridSpec(1, 1, width_ratios=[2, 1, 3])


def test_height_ratios():
    """
    Addresses issue #5835.
    See at https://github.com/matplotlib/matplotlib/issues/5835.
    """
    with pytest.raises(ValueError):
        gridspec.GridSpec(1, 1, height_ratios=[2, 1, 3])


def test_repr():
    ss = gridspec.GridSpec(3, 3)[2, 1:3]
    assert repr(ss) == "GridSpec(3, 3)[2:3, 1:3]"

    ss = gridspec.GridSpec(2, 2,
                           height_ratios=(3, 1),
                           width_ratios=(1, 3))
    assert repr(ss) == \
        "GridSpec(2, 2, height_ratios=(3, 1), width_ratios=(1, 3))"


def test_subplotspec_args():
    fig, axs = plt.subplots(1, 2)
    # should work:
    gs = gridspec.GridSpecFromSubplotSpec(2, 1,
                                          subplot_spec=axs[0].get_subplotspec())
    assert gs.get_topmost_subplotspec() == axs[0].get_subplotspec()
    with pytest.raises(TypeError, match="subplot_spec must be type SubplotSpec"):
        gs = gridspec.GridSpecFromSubplotSpec(2, 1, subplot_spec=axs[0])
    with pytest.raises(TypeError, match="subplot_spec must be type SubplotSpec"):
        gs = gridspec.GridSpecFromSubplotSpec(2, 1, subplot_spec=axs)
