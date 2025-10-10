"""
The inset module defines the InsetIndicator class, which draws the rectangle and
connectors required for `.Axes.indicate_inset` and `.Axes.indicate_inset_zoom`.
"""

from . import _api, artist, transforms
from matplotlib.patches import ConnectionPatch, PathPatch, Rectangle
from matplotlib.path import Path


_shared_properties = ('alpha', 'edgecolor', 'linestyle', 'linewidth')


class InsetIndicator(artist.Artist):
    """
    An artist to highlight an area of interest.

    An inset indicator is a rectangle on the plot at the position indicated by
    *bounds* that optionally has lines that connect the rectangle to an inset
    Axes (`.Axes.inset_axes`).

    .. versionadded:: 3.10
    """
    zorder = 4.99

    def __init__(self, bounds=None, inset_ax=None, zorder=None, **kwargs):
        """
        Parameters
        ----------
        bounds : [x0, y0, width, height], optional
            Lower-left corner of rectangle to be marked, and its width
            and height.  If not set, the bounds will be calculated from the
            data limits of inset_ax, which must be supplied.

        inset_ax : `~.axes.Axes`, optional
            An optional inset Axes to draw connecting lines to.  Two lines are
            drawn connecting the indicator box to the inset Axes on corners
            chosen so as to not overlap with the indicator box.

        zorder : float, default: 4.99
            Drawing order of the rectangle and connector lines.  The default,
            4.99, is just below the default level of inset Axes.

        **kwargs
            Other keyword arguments are passed on to the `.Rectangle` patch.
        """
        if bounds is None and inset_ax is None:
            raise ValueError("At least one of bounds or inset_ax must be supplied")

        self._inset_ax = inset_ax

        if bounds is None:
            # Work out bounds from inset_ax
            self._auto_update_bounds = True
            bounds = self._bounds_from_inset_ax()
        else:
            self._auto_update_bounds = False

        x, y, width, height = bounds

        self._rectangle = Rectangle((x, y), width, height, clip_on=False, **kwargs)

        # Connector positions cannot be calculated till the artist has been added
        # to an axes, so just make an empty list for now.
        self._connectors = []

        super().__init__()
        self.set_zorder(zorder)

        # Initial style properties for the artist should match the rectangle.
        for prop in _shared_properties:
            setattr(self, f'_{prop}', artist.getp(self._rectangle, prop))

    def _shared_setter(self, prop, val):
        """
        Helper function to set the same style property on the artist and its children.
        """
        setattr(self, f'_{prop}', val)

        artist.setp([self._rectangle, *self._connectors], prop, val)

    def set_alpha(self, alpha):
        # docstring inherited
        self._shared_setter('alpha', alpha)

    def set_edgecolor(self, color):
        """
        Set the edge color of the rectangle and the connectors.

        Parameters
        ----------
        color : :mpltype:`color` or None
        """
        self._shared_setter('edgecolor', color)

    def set_color(self, c):
        """
        Set the edgecolor of the rectangle and the connectors, and the
        facecolor for the rectangle.

        Parameters
        ----------
        c : :mpltype:`color`
        """
        self._shared_setter('edgecolor', c)
        self._shared_setter('facecolor', c)

    def set_linewidth(self, w):
        """
        Set the linewidth in points of the rectangle and the connectors.

        Parameters
        ----------
        w : float or None
        """
        self._shared_setter('linewidth', w)

    def set_linestyle(self, ls):
        """
        Set the linestyle of the rectangle and the connectors.

        ==========================================  =================
        linestyle                                   description
        ==========================================  =================
        ``'-'`` or ``'solid'``                      solid line
        ``'--'`` or ``'dashed'``                    dashed line
        ``'-.'`` or ``'dashdot'``                   dash-dotted line
        ``':'`` or ``'dotted'``                     dotted line
        ``'none'``, ``'None'``, ``' '``, or ``''``  draw nothing
        ==========================================  =================

        Alternatively a dash tuple of the following form can be provided::

            (offset, onoffseq)

        where ``onoffseq`` is an even length tuple of on and off ink in points.

        Parameters
        ----------
        ls : {'-', '--', '-.', ':', '', (offset, on-off-seq), ...}
            The line style.
        """
        self._shared_setter('linestyle', ls)

    def _bounds_from_inset_ax(self):
        xlim = self._inset_ax.get_xlim()
        ylim = self._inset_ax.get_ylim()
        return (xlim[0], ylim[0], xlim[1] - xlim[0], ylim[1] - ylim[0])

    def _update_connectors(self):
        (x, y) = self._rectangle.get_xy()
        width = self._rectangle.get_width()
        height = self._rectangle.get_height()

        existing_connectors = self._connectors or [None] * 4

        # connect the inset_axes to the rectangle
        for xy_inset_ax, existing in zip([(0, 0), (0, 1), (1, 0), (1, 1)],
                                         existing_connectors):
            # inset_ax positions are in axes coordinates
            # The 0, 1 values define the four edges if the inset_ax
            # lower_left, upper_left, lower_right upper_right.
            ex, ey = xy_inset_ax
            if self.axes.xaxis.get_inverted():
                ex = 1 - ex
            if self.axes.yaxis.get_inverted():
                ey = 1 - ey
            xy_data = x + ex * width, y + ey * height
            if existing is None:
                # Create new connection patch with styles inherited from the
                # parent artist.
                p = ConnectionPatch(
                    xyA=xy_inset_ax, coordsA=self._inset_ax.transAxes,
                    xyB=xy_data, coordsB=self.axes.transData,
                    arrowstyle="-",
                    edgecolor=self._edgecolor, alpha=self.get_alpha(),
                    linestyle=self._linestyle, linewidth=self._linewidth)
                self._connectors.append(p)
            else:
                # Only update positioning of existing connection patch.  We
                # do not want to override any style settings made by the user.
                existing.xy1 = xy_inset_ax
                existing.xy2 = xy_data
                existing.coords1 = self._inset_ax.transAxes
                existing.coords2 = self.axes.transData

        if existing is None:
            # decide which two of the lines to keep visible....
            pos = self._inset_ax.get_position()
            bboxins = pos.transformed(self.get_figure(root=False).transSubfigure)
            rectbbox = transforms.Bbox.from_bounds(x, y, width, height).transformed(
                self._rectangle.get_transform())
            x0 = rectbbox.x0 < bboxins.x0
            x1 = rectbbox.x1 < bboxins.x1
            y0 = rectbbox.y0 < bboxins.y0
            y1 = rectbbox.y1 < bboxins.y1
            self._connectors[0].set_visible(x0 ^ y0)
            self._connectors[1].set_visible(x0 == y1)
            self._connectors[2].set_visible(x1 == y0)
            self._connectors[3].set_visible(x1 ^ y1)

    @property
    def rectangle(self):
        """`.Rectangle`: the indicator frame."""
        return self._rectangle

    @property
    def connectors(self):
        """
        4-tuple of `.patches.ConnectionPatch` or None
            The four connector lines connecting to (lower_left, upper_left,
            lower_right upper_right) corners of *inset_ax*. Two lines are
            set with visibility to *False*,  but the user can set the
            visibility to True if the automatic choice is not deemed correct.
        """
        if self._inset_ax is None:
            return

        if self._auto_update_bounds:
            self._rectangle.set_bounds(self._bounds_from_inset_ax())
        self._update_connectors()
        return tuple(self._connectors)

    def draw(self, renderer):
        # docstring inherited
        conn_same_style = []

        # Figure out which connectors have the same style as the box, so should
        # be drawn as a single path.
        for conn in self.connectors or []:
            if conn.get_visible():
                drawn = False
                for s in _shared_properties:
                    if artist.getp(self._rectangle, s) != artist.getp(conn, s):
                        # Draw this connector by itself
                        conn.draw(renderer)
                        drawn = True
                        break

                if not drawn:
                    # Connector has same style as box.
                    conn_same_style.append(conn)

        if conn_same_style:
            # Since at least one connector has the same style as the rectangle, draw
            # them as a compound path.
            artists = [self._rectangle] + conn_same_style
            paths = [a.get_transform().transform_path(a.get_path()) for a in artists]
            path = Path.make_compound_path(*paths)

            # Create a temporary patch to draw the path.
            p = PathPatch(path)
            p.update_from(self._rectangle)
            p.set_transform(transforms.IdentityTransform())
            p.draw(renderer)

            return

        # Just draw the rectangle
        self._rectangle.draw(renderer)

    @_api.deprecated(
        '3.10',
        message=('Since Matplotlib 3.10 indicate_inset_[zoom] returns a single '
                 'InsetIndicator artist with a rectangle property and a connectors '
                 'property.  From 3.12 it will no longer be possible to unpack the '
                 'return value into two elements.'))
    def __getitem__(self, key):
        return [self._rectangle, self.connectors][key]
