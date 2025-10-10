"""
Helper module for the *bbox_inches* parameter in `.Figure.savefig`.
"""

from matplotlib.transforms import Bbox, TransformedBbox, Affine2D


def adjust_bbox(fig, bbox_inches, fixed_dpi=None):
    """
    Temporarily adjust the figure so that only the specified area
    (bbox_inches) is saved.

    It modifies fig.bbox, fig.bbox_inches,
    fig.transFigure._boxout, and fig.patch.  While the figure size
    changes, the scale of the original figure is conserved.  A
    function which restores the original values are returned.
    """
    origBbox = fig.bbox
    origBboxInches = fig.bbox_inches
    _boxout = fig.transFigure._boxout

    old_aspect = []
    locator_list = []
    sentinel = object()
    for ax in fig.axes:
        locator = ax.get_axes_locator()
        if locator is not None:
            ax.apply_aspect(locator(ax, None))
        locator_list.append(locator)
        current_pos = ax.get_position(original=False).frozen()
        ax.set_axes_locator(lambda a, r, _pos=current_pos: _pos)
        # override the method that enforces the aspect ratio on the Axes
        if 'apply_aspect' in ax.__dict__:
            old_aspect.append(ax.apply_aspect)
        else:
            old_aspect.append(sentinel)
        ax.apply_aspect = lambda pos=None: None

    def restore_bbox():
        for ax, loc, aspect in zip(fig.axes, locator_list, old_aspect):
            ax.set_axes_locator(loc)
            if aspect is sentinel:
                # delete our no-op function which un-hides the original method
                del ax.apply_aspect
            else:
                ax.apply_aspect = aspect

        fig.bbox = origBbox
        fig.bbox_inches = origBboxInches
        fig.transFigure._boxout = _boxout
        fig.transFigure.invalidate()
        fig.patch.set_bounds(0, 0, 1, 1)

    if fixed_dpi is None:
        fixed_dpi = fig.dpi
    tr = Affine2D().scale(fixed_dpi)
    dpi_scale = fixed_dpi / fig.dpi

    fig.bbox_inches = Bbox.from_bounds(0, 0, *bbox_inches.size)
    x0, y0 = tr.transform(bbox_inches.p0)
    w1, h1 = fig.bbox.size * dpi_scale
    fig.transFigure._boxout = Bbox.from_bounds(-x0, -y0, w1, h1)
    fig.transFigure.invalidate()

    fig.bbox = TransformedBbox(fig.bbox_inches, tr)

    fig.patch.set_bounds(x0 / w1, y0 / h1,
                         fig.bbox.width / w1, fig.bbox.height / h1)

    return restore_bbox


def process_figure_for_rasterizing(fig, bbox_inches_restore, fixed_dpi=None):
    """
    A function that needs to be called when figure dpi changes during the
    drawing (e.g., rasterizing).  It recovers the bbox and re-adjust it with
    the new dpi.
    """

    bbox_inches, restore_bbox = bbox_inches_restore
    restore_bbox()
    r = adjust_bbox(fig, bbox_inches, fixed_dpi)

    return bbox_inches, r
