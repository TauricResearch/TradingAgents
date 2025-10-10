"""
A collection of functions and objects for creating or placing inset axes.
"""

from matplotlib import _api, _docstring
from matplotlib.offsetbox import AnchoredOffsetbox
from matplotlib.patches import Patch, Rectangle
from matplotlib.path import Path
from matplotlib.transforms import Bbox
from matplotlib.transforms import IdentityTransform, TransformedBbox

from . import axes_size as Size
from .parasite_axes import HostAxes


class AnchoredLocatorBase(AnchoredOffsetbox):
    def __init__(self, bbox_to_anchor, offsetbox, loc,
                 borderpad=0.5, bbox_transform=None):
        super().__init__(
            loc, pad=0., child=None, borderpad=borderpad,
            bbox_to_anchor=bbox_to_anchor, bbox_transform=bbox_transform
        )

    def draw(self, renderer):
        raise RuntimeError("No draw method should be called")

    def __call__(self, ax, renderer):
        fig = ax.get_figure(root=False)
        if renderer is None:
            renderer = fig._get_renderer()
        self.axes = ax
        bbox = self.get_window_extent(renderer)
        px, py = self.get_offset(bbox.width, bbox.height, 0, 0, renderer)
        bbox_canvas = Bbox.from_bounds(px, py, bbox.width, bbox.height)
        tr = fig.transSubfigure.inverted()
        return TransformedBbox(bbox_canvas, tr)


class AnchoredSizeLocator(AnchoredLocatorBase):
    def __init__(self, bbox_to_anchor, x_size, y_size, loc,
                 borderpad=0.5, bbox_transform=None):
        super().__init__(
            bbox_to_anchor, None, loc,
            borderpad=borderpad, bbox_transform=bbox_transform
        )

        self.x_size = Size.from_any(x_size)
        self.y_size = Size.from_any(y_size)

    def get_bbox(self, renderer):
        bbox = self.get_bbox_to_anchor()
        dpi = renderer.points_to_pixels(72.)

        r, a = self.x_size.get_size(renderer)
        width = bbox.width * r + a * dpi
        r, a = self.y_size.get_size(renderer)
        height = bbox.height * r + a * dpi

        fontsize = renderer.points_to_pixels(self.prop.get_size_in_points())
        pad = self.pad * fontsize

        return Bbox.from_bounds(0, 0, width, height).padded(pad)


class AnchoredZoomLocator(AnchoredLocatorBase):
    def __init__(self, parent_axes, zoom, loc,
                 borderpad=0.5,
                 bbox_to_anchor=None,
                 bbox_transform=None):
        self.parent_axes = parent_axes
        self.zoom = zoom
        if bbox_to_anchor is None:
            bbox_to_anchor = parent_axes.bbox
        super().__init__(
            bbox_to_anchor, None, loc, borderpad=borderpad,
            bbox_transform=bbox_transform)

    def get_bbox(self, renderer):
        bb = self.parent_axes.transData.transform_bbox(self.axes.viewLim)
        fontsize = renderer.points_to_pixels(self.prop.get_size_in_points())
        pad = self.pad * fontsize
        return (
            Bbox.from_bounds(
                0, 0, abs(bb.width * self.zoom), abs(bb.height * self.zoom))
            .padded(pad))


class BboxPatch(Patch):
    @_docstring.interpd
    def __init__(self, bbox, **kwargs):
        """
        Patch showing the shape bounded by a Bbox.

        Parameters
        ----------
        bbox : `~matplotlib.transforms.Bbox`
            Bbox to use for the extents of this patch.

        **kwargs
            Patch properties. Valid arguments include:

            %(Patch:kwdoc)s
        """
        if "transform" in kwargs:
            raise ValueError("transform should not be set")

        kwargs["transform"] = IdentityTransform()
        super().__init__(**kwargs)
        self.bbox = bbox

    def get_path(self):
        # docstring inherited
        x0, y0, x1, y1 = self.bbox.extents
        return Path._create_closed([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


class BboxConnector(Patch):
    @staticmethod
    def get_bbox_edge_pos(bbox, loc):
        """
        Return the ``(x, y)`` coordinates of corner *loc* of *bbox*; parameters
        behave as documented for the `.BboxConnector` constructor.
        """
        x0, y0, x1, y1 = bbox.extents
        if loc == 1:
            return x1, y1
        elif loc == 2:
            return x0, y1
        elif loc == 3:
            return x0, y0
        elif loc == 4:
            return x1, y0

    @staticmethod
    def connect_bbox(bbox1, bbox2, loc1, loc2=None):
        """
        Construct a `.Path` connecting corner *loc1* of *bbox1* to corner
        *loc2* of *bbox2*, where parameters behave as documented as for the
        `.BboxConnector` constructor.
        """
        if isinstance(bbox1, Rectangle):
            bbox1 = TransformedBbox(Bbox.unit(), bbox1.get_transform())
        if isinstance(bbox2, Rectangle):
            bbox2 = TransformedBbox(Bbox.unit(), bbox2.get_transform())
        if loc2 is None:
            loc2 = loc1
        x1, y1 = BboxConnector.get_bbox_edge_pos(bbox1, loc1)
        x2, y2 = BboxConnector.get_bbox_edge_pos(bbox2, loc2)
        return Path([[x1, y1], [x2, y2]])

    @_docstring.interpd
    def __init__(self, bbox1, bbox2, loc1, loc2=None, **kwargs):
        """
        Connect two bboxes with a straight line.

        Parameters
        ----------
        bbox1, bbox2 : `~matplotlib.transforms.Bbox`
            Bounding boxes to connect.

        loc1, loc2 : {1, 2, 3, 4}
            Corner of *bbox1* and *bbox2* to draw the line. Valid values are::

                'upper right'  : 1,
                'upper left'   : 2,
                'lower left'   : 3,
                'lower right'  : 4

            *loc2* is optional and defaults to *loc1*.

        **kwargs
            Patch properties for the line drawn. Valid arguments include:

            %(Patch:kwdoc)s
        """
        if "transform" in kwargs:
            raise ValueError("transform should not be set")

        kwargs["transform"] = IdentityTransform()
        kwargs.setdefault(
            "fill", bool({'fc', 'facecolor', 'color'}.intersection(kwargs)))
        super().__init__(**kwargs)
        self.bbox1 = bbox1
        self.bbox2 = bbox2
        self.loc1 = loc1
        self.loc2 = loc2

    def get_path(self):
        # docstring inherited
        return self.connect_bbox(self.bbox1, self.bbox2,
                                 self.loc1, self.loc2)


class BboxConnectorPatch(BboxConnector):
    @_docstring.interpd
    def __init__(self, bbox1, bbox2, loc1a, loc2a, loc1b, loc2b, **kwargs):
        """
        Connect two bboxes with a quadrilateral.

        The quadrilateral is specified by two lines that start and end at
        corners of the bboxes. The four sides of the quadrilateral are defined
        by the two lines given, the line between the two corners specified in
        *bbox1* and the line between the two corners specified in *bbox2*.

        Parameters
        ----------
        bbox1, bbox2 : `~matplotlib.transforms.Bbox`
            Bounding boxes to connect.

        loc1a, loc2a, loc1b, loc2b : {1, 2, 3, 4}
            The first line connects corners *loc1a* of *bbox1* and *loc2a* of
            *bbox2*; the second line connects corners *loc1b* of *bbox1* and
            *loc2b* of *bbox2*.  Valid values are::

                'upper right'  : 1,
                'upper left'   : 2,
                'lower left'   : 3,
                'lower right'  : 4

        **kwargs
            Patch properties for the line drawn:

            %(Patch:kwdoc)s
        """
        if "transform" in kwargs:
            raise ValueError("transform should not be set")
        super().__init__(bbox1, bbox2, loc1a, loc2a, **kwargs)
        self.loc1b = loc1b
        self.loc2b = loc2b

    def get_path(self):
        # docstring inherited
        path1 = self.connect_bbox(self.bbox1, self.bbox2, self.loc1, self.loc2)
        path2 = self.connect_bbox(self.bbox2, self.bbox1,
                                  self.loc2b, self.loc1b)
        path_merged = [*path1.vertices, *path2.vertices, path1.vertices[0]]
        return Path(path_merged)


def _add_inset_axes(parent_axes, axes_class, axes_kwargs, axes_locator):
    """Helper function to add an inset axes and disable navigation in it."""
    if axes_class is None:
        axes_class = HostAxes
    if axes_kwargs is None:
        axes_kwargs = {}
    fig = parent_axes.get_figure(root=False)
    inset_axes = axes_class(
        fig, parent_axes.get_position(),
        **{"navigate": False, **axes_kwargs, "axes_locator": axes_locator})
    return fig.add_axes(inset_axes)


@_docstring.interpd
def inset_axes(parent_axes, width, height, loc='upper right',
               bbox_to_anchor=None, bbox_transform=None,
               axes_class=None, axes_kwargs=None,
               borderpad=0.5):
    """
    Create an inset axes with a given width and height.

    Both sizes used can be specified either in inches or percentage.
    For example,::

        inset_axes(parent_axes, width='40%%', height='30%%', loc='lower left')

    creates in inset axes in the lower left corner of *parent_axes* which spans
    over 30%% in height and 40%% in width of the *parent_axes*. Since the usage
    of `.inset_axes` may become slightly tricky when exceeding such standard
    cases, it is recommended to read :doc:`the examples
    </gallery/axes_grid1/inset_locator_demo>`.

    Notes
    -----
    The meaning of *bbox_to_anchor* and *bbox_to_transform* is interpreted
    differently from that of legend. The value of bbox_to_anchor
    (or the return value of its get_points method; the default is
    *parent_axes.bbox*) is transformed by the bbox_transform (the default
    is Identity transform) and then interpreted as points in the pixel
    coordinate (which is dpi dependent).

    Thus, following three calls are identical and creates an inset axes
    with respect to the *parent_axes*::

       axins = inset_axes(parent_axes, "30%%", "40%%")
       axins = inset_axes(parent_axes, "30%%", "40%%",
                          bbox_to_anchor=parent_axes.bbox)
       axins = inset_axes(parent_axes, "30%%", "40%%",
                          bbox_to_anchor=(0, 0, 1, 1),
                          bbox_transform=parent_axes.transAxes)

    Parameters
    ----------
    parent_axes : `matplotlib.axes.Axes`
        Axes to place the inset axes.

    width, height : float or str
        Size of the inset axes to create. If a float is provided, it is
        the size in inches, e.g. *width=1.3*. If a string is provided, it is
        the size in relative units, e.g. *width='40%%'*. By default, i.e. if
        neither *bbox_to_anchor* nor *bbox_transform* are specified, those
        are relative to the parent_axes. Otherwise, they are to be understood
        relative to the bounding box provided via *bbox_to_anchor*.

    loc : str, default: 'upper right'
        Location to place the inset axes.  Valid locations are
        'upper left', 'upper center', 'upper right',
        'center left', 'center', 'center right',
        'lower left', 'lower center', 'lower right'.
        For backward compatibility, numeric values are accepted as well.
        See the parameter *loc* of `.Legend` for details.

    bbox_to_anchor : tuple or `~matplotlib.transforms.BboxBase`, optional
        Bbox that the inset axes will be anchored to. If None,
        a tuple of (0, 0, 1, 1) is used if *bbox_transform* is set
        to *parent_axes.transAxes* or *parent_axes.figure.transFigure*.
        Otherwise, *parent_axes.bbox* is used. If a tuple, can be either
        [left, bottom, width, height], or [left, bottom].
        If the kwargs *width* and/or *height* are specified in relative units,
        the 2-tuple [left, bottom] cannot be used. Note that,
        unless *bbox_transform* is set, the units of the bounding box
        are interpreted in the pixel coordinate. When using *bbox_to_anchor*
        with tuple, it almost always makes sense to also specify
        a *bbox_transform*. This might often be the axes transform
        *parent_axes.transAxes*.

    bbox_transform : `~matplotlib.transforms.Transform`, optional
        Transformation for the bbox that contains the inset axes.
        If None, a `.transforms.IdentityTransform` is used. The value
        of *bbox_to_anchor* (or the return value of its get_points method)
        is transformed by the *bbox_transform* and then interpreted
        as points in the pixel coordinate (which is dpi dependent).
        You may provide *bbox_to_anchor* in some normalized coordinate,
        and give an appropriate transform (e.g., *parent_axes.transAxes*).

    axes_class : `~matplotlib.axes.Axes` type, default: `.HostAxes`
        The type of the newly created inset axes.

    axes_kwargs : dict, optional
        Keyword arguments to pass to the constructor of the inset axes.
        Valid arguments include:

        %(Axes:kwdoc)s

    borderpad : float, default: 0.5
        Padding between inset axes and the bbox_to_anchor.
        The units are axes font size, i.e. for a default font size of 10 points
        *borderpad = 0.5* is equivalent to a padding of 5 points.

    Returns
    -------
    inset_axes : *axes_class*
        Inset axes object created.
    """

    if (bbox_transform in [parent_axes.transAxes,
                           parent_axes.get_figure(root=False).transFigure]
            and bbox_to_anchor is None):
        _api.warn_external("Using the axes or figure transform requires a "
                           "bounding box in the respective coordinates. "
                           "Using bbox_to_anchor=(0, 0, 1, 1) now.")
        bbox_to_anchor = (0, 0, 1, 1)
    if bbox_to_anchor is None:
        bbox_to_anchor = parent_axes.bbox
    if (isinstance(bbox_to_anchor, tuple) and
            (isinstance(width, str) or isinstance(height, str))):
        if len(bbox_to_anchor) != 4:
            raise ValueError("Using relative units for width or height "
                             "requires to provide a 4-tuple or a "
                             "`Bbox` instance to `bbox_to_anchor.")
    return _add_inset_axes(
        parent_axes, axes_class, axes_kwargs,
        AnchoredSizeLocator(
            bbox_to_anchor, width, height, loc=loc,
            bbox_transform=bbox_transform, borderpad=borderpad))


@_docstring.interpd
def zoomed_inset_axes(parent_axes, zoom, loc='upper right',
                      bbox_to_anchor=None, bbox_transform=None,
                      axes_class=None, axes_kwargs=None,
                      borderpad=0.5):
    """
    Create an anchored inset axes by scaling a parent axes. For usage, also see
    :doc:`the examples </gallery/axes_grid1/inset_locator_demo2>`.

    Parameters
    ----------
    parent_axes : `~matplotlib.axes.Axes`
        Axes to place the inset axes.

    zoom : float
        Scaling factor of the data axes. *zoom* > 1 will enlarge the
        coordinates (i.e., "zoomed in"), while *zoom* < 1 will shrink the
        coordinates (i.e., "zoomed out").

    loc : str, default: 'upper right'
        Location to place the inset axes.  Valid locations are
        'upper left', 'upper center', 'upper right',
        'center left', 'center', 'center right',
        'lower left', 'lower center', 'lower right'.
        For backward compatibility, numeric values are accepted as well.
        See the parameter *loc* of `.Legend` for details.

    bbox_to_anchor : tuple or `~matplotlib.transforms.BboxBase`, optional
        Bbox that the inset axes will be anchored to. If None,
        *parent_axes.bbox* is used. If a tuple, can be either
        [left, bottom, width, height], or [left, bottom].
        If the kwargs *width* and/or *height* are specified in relative units,
        the 2-tuple [left, bottom] cannot be used. Note that
        the units of the bounding box are determined through the transform
        in use. When using *bbox_to_anchor* it almost always makes sense to
        also specify a *bbox_transform*. This might often be the axes transform
        *parent_axes.transAxes*.

    bbox_transform : `~matplotlib.transforms.Transform`, optional
        Transformation for the bbox that contains the inset axes.
        If None, a `.transforms.IdentityTransform` is used (i.e. pixel
        coordinates). This is useful when not providing any argument to
        *bbox_to_anchor*. When using *bbox_to_anchor* it almost always makes
        sense to also specify a *bbox_transform*. This might often be the
        axes transform *parent_axes.transAxes*. Inversely, when specifying
        the axes- or figure-transform here, be aware that not specifying
        *bbox_to_anchor* will use *parent_axes.bbox*, the units of which are
        in display (pixel) coordinates.

    axes_class : `~matplotlib.axes.Axes` type, default: `.HostAxes`
        The type of the newly created inset axes.

    axes_kwargs : dict, optional
        Keyword arguments to pass to the constructor of the inset axes.
        Valid arguments include:

        %(Axes:kwdoc)s

    borderpad : float, default: 0.5
        Padding between inset axes and the bbox_to_anchor.
        The units are axes font size, i.e. for a default font size of 10 points
        *borderpad = 0.5* is equivalent to a padding of 5 points.

    Returns
    -------
    inset_axes : *axes_class*
        Inset axes object created.
    """

    return _add_inset_axes(
        parent_axes, axes_class, axes_kwargs,
        AnchoredZoomLocator(
            parent_axes, zoom=zoom, loc=loc,
            bbox_to_anchor=bbox_to_anchor, bbox_transform=bbox_transform,
            borderpad=borderpad))


class _TransformedBboxWithCallback(TransformedBbox):
    """
    Variant of `.TransformBbox` which calls *callback* before returning points.

    Used by `.mark_inset` to unstale the parent axes' viewlim as needed.
    """

    def __init__(self, *args, callback, **kwargs):
        super().__init__(*args, **kwargs)
        self._callback = callback

    def get_points(self):
        self._callback()
        return super().get_points()


@_docstring.interpd
def mark_inset(parent_axes, inset_axes, loc1, loc2, **kwargs):
    """
    Draw a box to mark the location of an area represented by an inset axes.

    This function draws a box in *parent_axes* at the bounding box of
    *inset_axes*, and shows a connection with the inset axes by drawing lines
    at the corners, giving a "zoomed in" effect.

    Parameters
    ----------
    parent_axes : `~matplotlib.axes.Axes`
        Axes which contains the area of the inset axes.

    inset_axes : `~matplotlib.axes.Axes`
        The inset axes.

    loc1, loc2 : {1, 2, 3, 4}
        Corners to use for connecting the inset axes and the area in the
        parent axes.

    **kwargs
        Patch properties for the lines and box drawn:

        %(Patch:kwdoc)s

    Returns
    -------
    pp : `~matplotlib.patches.Patch`
        The patch drawn to represent the area of the inset axes.

    p1, p2 : `~matplotlib.patches.Patch`
        The patches connecting two corners of the inset axes and its area.
    """
    rect = _TransformedBboxWithCallback(
        inset_axes.viewLim, parent_axes.transData,
        callback=parent_axes._unstale_viewLim)

    kwargs.setdefault("fill", bool({'fc', 'facecolor', 'color'}.intersection(kwargs)))
    pp = BboxPatch(rect, **kwargs)
    parent_axes.add_patch(pp)

    p1 = BboxConnector(inset_axes.bbox, rect, loc1=loc1, **kwargs)
    inset_axes.add_patch(p1)
    p1.set_clip_on(False)
    p2 = BboxConnector(inset_axes.bbox, rect, loc1=loc2, **kwargs)
    inset_axes.add_patch(p2)
    p2.set_clip_on(False)

    return pp, p1, p2
