"""
Enums representing sets of strings that Matplotlib uses as input parameters.

Matplotlib often uses simple data types like strings or tuples to define a
concept; e.g. the line capstyle can be specified as one of 'butt', 'round',
or 'projecting'. The classes in this module are used internally and serve to
document these concepts formally.

As an end-user you will not use these classes directly, but only the values
they define.
"""

from enum import Enum
from matplotlib import _docstring


class JoinStyle(str, Enum):
    """
    Define how the connection between two line segments is drawn.

    For a visual impression of each *JoinStyle*, `view these docs online
    <JoinStyle>`, or run `JoinStyle.demo`.

    Lines in Matplotlib are typically defined by a 1D `~.path.Path` and a
    finite ``linewidth``, where the underlying 1D `~.path.Path` represents the
    center of the stroked line.

    By default, `~.backend_bases.GraphicsContextBase` defines the boundaries of
    a stroked line to simply be every point within some radius,
    ``linewidth/2``, away from any point of the center line. However, this
    results in corners appearing "rounded", which may not be the desired
    behavior if you are drawing, for example, a polygon or pointed star.

    **Supported values:**

    .. rst-class:: value-list

        'miter'
            the "arrow-tip" style. Each boundary of the filled-in area will
            extend in a straight line parallel to the tangent vector of the
            centerline at the point it meets the corner, until they meet in a
            sharp point.
        'round'
            stokes every point within a radius of ``linewidth/2`` of the center
            lines.
        'bevel'
            the "squared-off" style. It can be thought of as a rounded corner
            where the "circular" part of the corner has been cut off.

    .. note::

        Very long miter tips are cut off (to form a *bevel*) after a
        backend-dependent limit called the "miter limit", which specifies the
        maximum allowed ratio of miter length to line width. For example, the
        PDF backend uses the default value of 10 specified by the PDF standard,
        while the SVG backend does not even specify the miter limit, resulting
        in a default value of 4 per the SVG specification. Matplotlib does not
        currently allow the user to adjust this parameter.

        A more detailed description of the effect of a miter limit can be found
        in the `Mozilla Developer Docs
        <https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/stroke-miterlimit>`_

    .. plot::
        :alt: Demo of possible JoinStyle's

        from matplotlib._enums import JoinStyle
        JoinStyle.demo()

    """

    miter = "miter"
    round = "round"
    bevel = "bevel"

    @staticmethod
    def demo():
        """Demonstrate how each JoinStyle looks for various join angles."""
        import numpy as np
        import matplotlib.pyplot as plt

        def plot_angle(ax, x, y, angle, style):
            phi = np.radians(angle)
            xx = [x + .5, x, x + .5*np.cos(phi)]
            yy = [y, y, y + .5*np.sin(phi)]
            ax.plot(xx, yy, lw=12, color='tab:blue', solid_joinstyle=style)
            ax.plot(xx, yy, lw=1, color='black')
            ax.plot(xx[1], yy[1], 'o', color='tab:red', markersize=3)

        fig, ax = plt.subplots(figsize=(5, 4), constrained_layout=True)
        ax.set_title('Join style')
        for x, style in enumerate(['miter', 'round', 'bevel']):
            ax.text(x, 5, style)
            for y, angle in enumerate([20, 45, 60, 90, 120]):
                plot_angle(ax, x, y, angle, style)
                if x == 0:
                    ax.text(-1.3, y, f'{angle} degrees')
        ax.set_xlim(-1.5, 2.75)
        ax.set_ylim(-.5, 5.5)
        ax.set_axis_off()
        fig.show()


JoinStyle.input_description = "{" \
        + ", ".join([f"'{js.name}'" for js in JoinStyle]) \
        + "}"


class CapStyle(str, Enum):
    r"""
    Define how the two endpoints (caps) of an unclosed line are drawn.

    How to draw the start and end points of lines that represent a closed curve
    (i.e. that end in a `~.path.Path.CLOSEPOLY`) is controlled by the line's
    `JoinStyle`. For all other lines, how the start and end points are drawn is
    controlled by the *CapStyle*.

    For a visual impression of each *CapStyle*, `view these docs online
    <CapStyle>` or run `CapStyle.demo`.

    By default, `~.backend_bases.GraphicsContextBase` draws a stroked line as
    squared off at its endpoints.

    **Supported values:**

    .. rst-class:: value-list

        'butt'
            the line is squared off at its endpoint.
        'projecting'
            the line is squared off as in *butt*, but the filled in area
            extends beyond the endpoint a distance of ``linewidth/2``.
        'round'
            like *butt*, but a semicircular cap is added to the end of the
            line, of radius ``linewidth/2``.

    .. plot::
        :alt: Demo of possible CapStyle's

        from matplotlib._enums import CapStyle
        CapStyle.demo()

    """
    butt = "butt"
    projecting = "projecting"
    round = "round"

    @staticmethod
    def demo():
        """Demonstrate how each CapStyle looks for a thick line segment."""
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(4, 1.2))
        ax = fig.add_axes([0, 0, 1, 0.8])
        ax.set_title('Cap style')

        for x, style in enumerate(['butt', 'round', 'projecting']):
            ax.text(x+0.25, 0.85, style, ha='center')
            xx = [x, x+0.5]
            yy = [0, 0]
            ax.plot(xx, yy, lw=12, color='tab:blue', solid_capstyle=style)
            ax.plot(xx, yy, lw=1, color='black')
            ax.plot(xx, yy, 'o', color='tab:red', markersize=3)

        ax.set_ylim(-.5, 1.5)
        ax.set_axis_off()
        fig.show()


CapStyle.input_description = "{" \
        + ", ".join([f"'{cs.name}'" for cs in CapStyle]) \
        + "}"

_docstring.interpd.register(
    JoinStyle=JoinStyle.input_description,
    CapStyle=CapStyle.input_description,
)
