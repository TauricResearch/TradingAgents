import numpy as np

import pytest

from matplotlib.testing.decorators import check_figures_equal
from matplotlib import (
    collections as mcollections, patches as mpatches, path as mpath)


@pytest.mark.backend('cairo')
@check_figures_equal(extensions=["png"])
def test_patch_alpha_coloring(fig_test, fig_ref):
    """
    Test checks that the patch and collection are rendered with the specified
    alpha values in their facecolor and edgecolor.
    """
    star = mpath.Path.unit_regular_star(6)
    circle = mpath.Path.unit_circle()
    # concatenate the star with an internal cutout of the circle
    verts = np.concatenate([circle.vertices, star.vertices[::-1]])
    codes = np.concatenate([circle.codes, star.codes])
    cut_star1 = mpath.Path(verts, codes)
    cut_star2 = mpath.Path(verts + 1, codes)

    # Reference: two separate patches
    ax = fig_ref.subplots()
    ax.set_xlim([-1, 2])
    ax.set_ylim([-1, 2])
    patch = mpatches.PathPatch(cut_star1,
                               linewidth=5, linestyle='dashdot',
                               facecolor=(1, 0, 0, 0.5),
                               edgecolor=(0, 0, 1, 0.75))
    ax.add_patch(patch)
    patch = mpatches.PathPatch(cut_star2,
                               linewidth=5, linestyle='dashdot',
                               facecolor=(1, 0, 0, 0.5),
                               edgecolor=(0, 0, 1, 0.75))
    ax.add_patch(patch)

    # Test: path collection
    ax = fig_test.subplots()
    ax.set_xlim([-1, 2])
    ax.set_ylim([-1, 2])
    col = mcollections.PathCollection([cut_star1, cut_star2],
                                      linewidth=5, linestyles='dashdot',
                                      facecolor=(1, 0, 0, 0.5),
                                      edgecolor=(0, 0, 1, 0.75))
    ax.add_collection(col)
