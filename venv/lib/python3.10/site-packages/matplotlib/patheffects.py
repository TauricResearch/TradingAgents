"""
Defines classes for path effects. The path effects are supported in `.Text`,
`.Line2D` and `.Patch`.

.. seealso::
   :ref:`patheffects_guide`
"""

from matplotlib.backend_bases import RendererBase
from matplotlib import colors as mcolors
from matplotlib import patches as mpatches
from matplotlib import transforms as mtransforms
from matplotlib.path import Path
import numpy as np


class AbstractPathEffect:
    """
    A base class for path effects.

    Subclasses should override the ``draw_path`` method to add effect
    functionality.
    """

    def __init__(self, offset=(0., 0.)):
        """
        Parameters
        ----------
        offset : (float, float), default: (0, 0)
            The (x, y) offset to apply to the path, measured in points.
        """
        self._offset = offset

    def _offset_transform(self, renderer):
        """Apply the offset to the given transform."""
        return mtransforms.Affine2D().translate(
            *map(renderer.points_to_pixels, self._offset))

    def _update_gc(self, gc, new_gc_dict):
        """
        Update the given GraphicsContext with the given dict of properties.

        The keys in the dictionary are used to identify the appropriate
        ``set_`` method on the *gc*.
        """
        new_gc_dict = new_gc_dict.copy()

        dashes = new_gc_dict.pop("dashes", None)
        if dashes:
            gc.set_dashes(**dashes)

        for k, v in new_gc_dict.items():
            set_method = getattr(gc, 'set_' + k, None)
            if not callable(set_method):
                raise AttributeError(f'Unknown property {k}')
            set_method(v)
        return gc

    def draw_path(self, renderer, gc, tpath, affine, rgbFace=None):
        """
        Derived should override this method. The arguments are the same
        as :meth:`matplotlib.backend_bases.RendererBase.draw_path`
        except the first argument is a renderer.
        """
        # Get the real renderer, not a PathEffectRenderer.
        if isinstance(renderer, PathEffectRenderer):
            renderer = renderer._renderer
        return renderer.draw_path(gc, tpath, affine, rgbFace)


class PathEffectRenderer(RendererBase):
    """
    Implements a Renderer which contains another renderer.

    This proxy then intercepts draw calls, calling the appropriate
    :class:`AbstractPathEffect` draw method.

    .. note::
        Not all methods have been overridden on this RendererBase subclass.
        It may be necessary to add further methods to extend the PathEffects
        capabilities further.
    """

    def __init__(self, path_effects, renderer):
        """
        Parameters
        ----------
        path_effects : iterable of :class:`AbstractPathEffect`
            The path effects which this renderer represents.
        renderer : `~matplotlib.backend_bases.RendererBase` subclass

        """
        self._path_effects = path_effects
        self._renderer = renderer

    def copy_with_path_effect(self, path_effects):
        return self.__class__(path_effects, self._renderer)

    def __getattribute__(self, name):
        if name in ['flipy', 'get_canvas_width_height', 'new_gc',
                    'points_to_pixels', '_text2path', 'height', 'width']:
            return getattr(self._renderer, name)
        else:
            return object.__getattribute__(self, name)

    def draw_path(self, gc, tpath, affine, rgbFace=None):
        for path_effect in self._path_effects:
            path_effect.draw_path(self._renderer, gc, tpath, affine,
                                  rgbFace)

    def draw_markers(
            self, gc, marker_path, marker_trans, path, *args, **kwargs):
        # We do a little shimmy so that all markers are drawn for each path
        # effect in turn. Essentially, we induce recursion (depth 1) which is
        # terminated once we have just a single path effect to work with.
        if len(self._path_effects) == 1:
            # Call the base path effect function - this uses the unoptimised
            # approach of calling "draw_path" multiple times.
            return super().draw_markers(gc, marker_path, marker_trans, path,
                                        *args, **kwargs)

        for path_effect in self._path_effects:
            renderer = self.copy_with_path_effect([path_effect])
            # Recursively call this method, only next time we will only have
            # one path effect.
            renderer.draw_markers(gc, marker_path, marker_trans, path,
                                  *args, **kwargs)

    def draw_path_collection(self, gc, master_transform, paths, *args,
                             **kwargs):
        # We do a little shimmy so that all paths are drawn for each path
        # effect in turn. Essentially, we induce recursion (depth 1) which is
        # terminated once we have just a single path effect to work with.
        if len(self._path_effects) == 1:
            # Call the base path effect function - this uses the unoptimised
            # approach of calling "draw_path" multiple times.
            return super().draw_path_collection(gc, master_transform, paths,
                                                *args, **kwargs)

        for path_effect in self._path_effects:
            renderer = self.copy_with_path_effect([path_effect])
            # Recursively call this method, only next time we will only have
            # one path effect.
            renderer.draw_path_collection(gc, master_transform, paths,
                                          *args, **kwargs)

    def open_group(self, s, gid=None):
        return self._renderer.open_group(s, gid)

    def close_group(self, s):
        return self._renderer.close_group(s)


class Normal(AbstractPathEffect):
    """
    The "identity" PathEffect.

    The Normal PathEffect's sole purpose is to draw the original artist with
    no special path effect.
    """


def _subclass_with_normal(effect_class):
    """
    Create a PathEffect class combining *effect_class* and a normal draw.
    """

    class withEffect(effect_class):
        def draw_path(self, renderer, gc, tpath, affine, rgbFace):
            super().draw_path(renderer, gc, tpath, affine, rgbFace)
            renderer.draw_path(gc, tpath, affine, rgbFace)

    withEffect.__name__ = f"with{effect_class.__name__}"
    withEffect.__qualname__ = f"with{effect_class.__name__}"
    withEffect.__doc__ = f"""
    A shortcut PathEffect for applying `.{effect_class.__name__}` and then
    drawing the original Artist.

    With this class you can use ::

        artist.set_path_effects([patheffects.with{effect_class.__name__}()])

    as a shortcut for ::

        artist.set_path_effects([patheffects.{effect_class.__name__}(),
                                 patheffects.Normal()])
    """
    # Docstring inheritance doesn't work for locally-defined subclasses.
    withEffect.draw_path.__doc__ = effect_class.draw_path.__doc__
    return withEffect


class Stroke(AbstractPathEffect):
    """A line based PathEffect which re-draws a stroke."""

    def __init__(self, offset=(0, 0), **kwargs):
        """
        The path will be stroked with its gc updated with the given
        keyword arguments, i.e., the keyword arguments should be valid
        gc parameter values.
        """
        super().__init__(offset)
        self._gc = kwargs

    def draw_path(self, renderer, gc, tpath, affine, rgbFace):
        """Draw the path with updated gc."""
        gc0 = renderer.new_gc()  # Don't modify gc, but a copy!
        gc0.copy_properties(gc)
        gc0 = self._update_gc(gc0, self._gc)
        renderer.draw_path(
            gc0, tpath, affine + self._offset_transform(renderer), rgbFace)
        gc0.restore()


withStroke = _subclass_with_normal(effect_class=Stroke)


class SimplePatchShadow(AbstractPathEffect):
    """A simple shadow via a filled patch."""

    def __init__(self, offset=(2, -2),
                 shadow_rgbFace=None, alpha=None,
                 rho=0.3, **kwargs):
        """
        Parameters
        ----------
        offset : (float, float), default: (2, -2)
            The (x, y) offset of the shadow in points.
        shadow_rgbFace : :mpltype:`color`
            The shadow color.
        alpha : float, default: 0.3
            The alpha transparency of the created shadow patch.
        rho : float, default: 0.3
            A scale factor to apply to the rgbFace color if *shadow_rgbFace*
            is not specified.
        **kwargs
            Extra keywords are stored and passed through to
            :meth:`AbstractPathEffect._update_gc`.

        """
        super().__init__(offset)

        if shadow_rgbFace is None:
            self._shadow_rgbFace = shadow_rgbFace
        else:
            self._shadow_rgbFace = mcolors.to_rgba(shadow_rgbFace)

        if alpha is None:
            alpha = 0.3

        self._alpha = alpha
        self._rho = rho

        #: The dictionary of keywords to update the graphics collection with.
        self._gc = kwargs

    def draw_path(self, renderer, gc, tpath, affine, rgbFace):
        """
        Overrides the standard draw_path to add the shadow offset and
        necessary color changes for the shadow.
        """
        gc0 = renderer.new_gc()  # Don't modify gc, but a copy!
        gc0.copy_properties(gc)

        if self._shadow_rgbFace is None:
            r, g, b = (rgbFace or (1., 1., 1.))[:3]
            # Scale the colors by a factor to improve the shadow effect.
            shadow_rgbFace = (r * self._rho, g * self._rho, b * self._rho)
        else:
            shadow_rgbFace = self._shadow_rgbFace

        gc0.set_foreground("none")
        gc0.set_alpha(self._alpha)
        gc0.set_linewidth(0)

        gc0 = self._update_gc(gc0, self._gc)
        renderer.draw_path(
            gc0, tpath, affine + self._offset_transform(renderer),
            shadow_rgbFace)
        gc0.restore()


withSimplePatchShadow = _subclass_with_normal(effect_class=SimplePatchShadow)


class SimpleLineShadow(AbstractPathEffect):
    """A simple shadow via a line."""

    def __init__(self, offset=(2, -2),
                 shadow_color='k', alpha=0.3, rho=0.3, **kwargs):
        """
        Parameters
        ----------
        offset : (float, float), default: (2, -2)
            The (x, y) offset to apply to the path, in points.
        shadow_color : :mpltype:`color`, default: 'black'
            The shadow color.
            A value of ``None`` takes the original artist's color
            with a scale factor of *rho*.
        alpha : float, default: 0.3
            The alpha transparency of the created shadow patch.
        rho : float, default: 0.3
            A scale factor to apply to the rgbFace color if *shadow_color*
            is ``None``.
        **kwargs
            Extra keywords are stored and passed through to
            :meth:`AbstractPathEffect._update_gc`.
        """
        super().__init__(offset)
        if shadow_color is None:
            self._shadow_color = shadow_color
        else:
            self._shadow_color = mcolors.to_rgba(shadow_color)
        self._alpha = alpha
        self._rho = rho
        #: The dictionary of keywords to update the graphics collection with.
        self._gc = kwargs

    def draw_path(self, renderer, gc, tpath, affine, rgbFace):
        """
        Overrides the standard draw_path to add the shadow offset and
        necessary color changes for the shadow.
        """
        gc0 = renderer.new_gc()  # Don't modify gc, but a copy!
        gc0.copy_properties(gc)

        if self._shadow_color is None:
            r, g, b = (gc0.get_foreground() or (1., 1., 1.))[:3]
            # Scale the colors by a factor to improve the shadow effect.
            shadow_rgbFace = (r * self._rho, g * self._rho, b * self._rho)
        else:
            shadow_rgbFace = self._shadow_color

        gc0.set_foreground(shadow_rgbFace)
        gc0.set_alpha(self._alpha)

        gc0 = self._update_gc(gc0, self._gc)
        renderer.draw_path(
            gc0, tpath, affine + self._offset_transform(renderer))
        gc0.restore()


class PathPatchEffect(AbstractPathEffect):
    """
    Draws a `.PathPatch` instance whose Path comes from the original
    PathEffect artist.
    """

    def __init__(self, offset=(0, 0), **kwargs):
        """
        Parameters
        ----------
        offset : (float, float), default: (0, 0)
            The (x, y) offset to apply to the path, in points.
        **kwargs
            All keyword arguments are passed through to the
            :class:`~matplotlib.patches.PathPatch` constructor. The
            properties which cannot be overridden are "path", "clip_box"
            "transform" and "clip_path".
        """
        super().__init__(offset=offset)
        self.patch = mpatches.PathPatch([], **kwargs)

    def draw_path(self, renderer, gc, tpath, affine, rgbFace):
        self.patch._path = tpath
        self.patch.set_transform(affine + self._offset_transform(renderer))
        self.patch.set_clip_box(gc.get_clip_rectangle())
        clip_path = gc.get_clip_path()
        if clip_path and self.patch.get_clip_path() is None:
            self.patch.set_clip_path(*clip_path)
        self.patch.draw(renderer)


class TickedStroke(AbstractPathEffect):
    """
    A line-based PathEffect which draws a path with a ticked style.

    This line style is frequently used to represent constraints in
    optimization.  The ticks may be used to indicate that one side
    of the line is invalid or to represent a closed boundary of a
    domain (i.e. a wall or the edge of a pipe).

    The spacing, length, and angle of ticks can be controlled.

    This line style is sometimes referred to as a hatched line.

    See also the :doc:`/gallery/misc/tickedstroke_demo` example.
    """

    def __init__(self, offset=(0, 0),
                 spacing=10.0, angle=45.0, length=np.sqrt(2),
                 **kwargs):
        """
        Parameters
        ----------
        offset : (float, float), default: (0, 0)
            The (x, y) offset to apply to the path, in points.
        spacing : float, default: 10.0
            The spacing between ticks in points.
        angle : float, default: 45.0
            The angle between the path and the tick in degrees.  The angle
            is measured as if you were an ant walking along the curve, with
            zero degrees pointing directly ahead, 90 to your left, -90
            to your right, and 180 behind you. To change side of the ticks,
            change sign of the angle.
        length : float, default: 1.414
            The length of the tick relative to spacing.
            Recommended length = 1.414 (sqrt(2)) when angle=45, length=1.0
            when angle=90 and length=2.0 when angle=60.
        **kwargs
            Extra keywords are stored and passed through to
            :meth:`AbstractPathEffect._update_gc`.

        Examples
        --------
        See :doc:`/gallery/misc/tickedstroke_demo`.
        """
        super().__init__(offset)

        self._spacing = spacing
        self._angle = angle
        self._length = length
        self._gc = kwargs

    def draw_path(self, renderer, gc, tpath, affine, rgbFace):
        """Draw the path with updated gc."""
        # Do not modify the input! Use copy instead.
        gc0 = renderer.new_gc()
        gc0.copy_properties(gc)

        gc0 = self._update_gc(gc0, self._gc)
        trans = affine + self._offset_transform(renderer)

        theta = -np.radians(self._angle)
        trans_matrix = np.array([[np.cos(theta), -np.sin(theta)],
                                 [np.sin(theta), np.cos(theta)]])

        # Convert spacing parameter to pixels.
        spacing_px = renderer.points_to_pixels(self._spacing)

        # Transform before evaluation because to_polygons works at resolution
        # of one -- assuming it is working in pixel space.
        transpath = affine.transform_path(tpath)

        # Evaluate path to straight line segments that can be used to
        # construct line ticks.
        polys = transpath.to_polygons(closed_only=False)

        for p in polys:
            x = p[:, 0]
            y = p[:, 1]

            # Can not interpolate points or draw line if only one point in
            # polyline.
            if x.size < 2:
                continue

            # Find distance between points on the line
            ds = np.hypot(x[1:] - x[:-1], y[1:] - y[:-1])

            # Build parametric coordinate along curve
            s = np.concatenate(([0.0], np.cumsum(ds)))
            s_total = s[-1]

            num = int(np.ceil(s_total / spacing_px)) - 1
            # Pick parameter values for ticks.
            s_tick = np.linspace(spacing_px/2, s_total - spacing_px/2, num)

            # Find points along the parameterized curve
            x_tick = np.interp(s_tick, s, x)
            y_tick = np.interp(s_tick, s, y)

            # Find unit vectors in local direction of curve
            delta_s = self._spacing * .001
            u = (np.interp(s_tick + delta_s, s, x) - x_tick) / delta_s
            v = (np.interp(s_tick + delta_s, s, y) - y_tick) / delta_s

            # Normalize slope into unit slope vector.
            n = np.hypot(u, v)
            mask = n == 0
            n[mask] = 1.0

            uv = np.array([u / n, v / n]).T
            uv[mask] = np.array([0, 0]).T

            # Rotate and scale unit vector into tick vector
            dxy = np.dot(uv, trans_matrix) * self._length * spacing_px

            # Build tick endpoints
            x_end = x_tick + dxy[:, 0]
            y_end = y_tick + dxy[:, 1]

            # Interleave ticks to form Path vertices
            xyt = np.empty((2 * num, 2), dtype=x_tick.dtype)
            xyt[0::2, 0] = x_tick
            xyt[1::2, 0] = x_end
            xyt[0::2, 1] = y_tick
            xyt[1::2, 1] = y_end

            # Build up vector of Path codes
            codes = np.tile([Path.MOVETO, Path.LINETO], num)

            # Construct and draw resulting path
            h = Path(xyt, codes)
            # Transform back to data space during render
            renderer.draw_path(gc0, h, affine.inverted() + trans, rgbFace)

        gc0.restore()


withTickedStroke = _subclass_with_normal(effect_class=TickedStroke)
