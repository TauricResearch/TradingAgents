"""
Abstract base classes define the primitives that renderers and
graphics contexts must implement to serve as a Matplotlib backend.

`RendererBase`
    An abstract base class to handle drawing/rendering operations.

`FigureCanvasBase`
    The abstraction layer that separates the `.Figure` from the backend
    specific details like a user interface drawing area.

`GraphicsContextBase`
    An abstract base class that provides color, line styles, etc.

`Event`
    The base class for all of the Matplotlib event handling.  Derived classes
    such as `KeyEvent` and `MouseEvent` store the meta data like keys and
    buttons pressed, x and y locations in pixel and `~.axes.Axes` coordinates.

`ShowBase`
    The base class for the ``Show`` class of each interactive backend; the
    'show' callable is then set to ``Show.__call__``.

`ToolContainerBase`
    The base class for the Toolbar class of each interactive backend.
"""

from collections import namedtuple
from contextlib import ExitStack, contextmanager, nullcontext
from enum import Enum, IntEnum
import functools
import importlib
import inspect
import io
import itertools
import logging
import os
import pathlib
import signal
import socket
import sys
import time
import weakref
from weakref import WeakKeyDictionary

import numpy as np

import matplotlib as mpl
from matplotlib import (
    _api, backend_tools as tools, cbook, colors, _docstring, text,
    _tight_bbox, transforms, widgets, is_interactive, rcParams)
from matplotlib._pylab_helpers import Gcf
from matplotlib.backend_managers import ToolManager
from matplotlib.cbook import _setattr_cm
from matplotlib.layout_engine import ConstrainedLayoutEngine
from matplotlib.path import Path
from matplotlib.texmanager import TexManager
from matplotlib.transforms import Affine2D
from matplotlib._enums import JoinStyle, CapStyle


_log = logging.getLogger(__name__)
_default_filetypes = {
    'eps': 'Encapsulated Postscript',
    'jpg': 'Joint Photographic Experts Group',
    'jpeg': 'Joint Photographic Experts Group',
    'pdf': 'Portable Document Format',
    'pgf': 'PGF code for LaTeX',
    'png': 'Portable Network Graphics',
    'ps': 'Postscript',
    'raw': 'Raw RGBA bitmap',
    'rgba': 'Raw RGBA bitmap',
    'svg': 'Scalable Vector Graphics',
    'svgz': 'Scalable Vector Graphics',
    'tif': 'Tagged Image File Format',
    'tiff': 'Tagged Image File Format',
    'webp': 'WebP Image Format',
}
_default_backends = {
    'eps': 'matplotlib.backends.backend_ps',
    'jpg': 'matplotlib.backends.backend_agg',
    'jpeg': 'matplotlib.backends.backend_agg',
    'pdf': 'matplotlib.backends.backend_pdf',
    'pgf': 'matplotlib.backends.backend_pgf',
    'png': 'matplotlib.backends.backend_agg',
    'ps': 'matplotlib.backends.backend_ps',
    'raw': 'matplotlib.backends.backend_agg',
    'rgba': 'matplotlib.backends.backend_agg',
    'svg': 'matplotlib.backends.backend_svg',
    'svgz': 'matplotlib.backends.backend_svg',
    'tif': 'matplotlib.backends.backend_agg',
    'tiff': 'matplotlib.backends.backend_agg',
    'webp': 'matplotlib.backends.backend_agg',
}


def register_backend(format, backend, description=None):
    """
    Register a backend for saving to a given file format.

    Parameters
    ----------
    format : str
        File extension
    backend : module string or canvas class
        Backend for handling file output
    description : str, default: ""
        Description of the file type.
    """
    if description is None:
        description = ''
    _default_backends[format] = backend
    _default_filetypes[format] = description


def get_registered_canvas_class(format):
    """
    Return the registered default canvas for given file format.
    Handles deferred import of required backend.
    """
    if format not in _default_backends:
        return None
    backend_class = _default_backends[format]
    if isinstance(backend_class, str):
        backend_class = importlib.import_module(backend_class).FigureCanvas
        _default_backends[format] = backend_class
    return backend_class


class RendererBase:
    """
    An abstract base class to handle drawing/rendering operations.

    The following methods must be implemented in the backend for full
    functionality (though just implementing `draw_path` alone would give a
    highly capable backend):

    * `draw_path`
    * `draw_image`
    * `draw_gouraud_triangles`

    The following methods *should* be implemented in the backend for
    optimization reasons:

    * `draw_text`
    * `draw_markers`
    * `draw_path_collection`
    * `draw_quad_mesh`
    """
    def __init__(self):
        super().__init__()
        self._texmanager = None
        self._text2path = text.TextToPath()
        self._raster_depth = 0
        self._rasterizing = False

    def open_group(self, s, gid=None):
        """
        Open a grouping element with label *s* and *gid* (if set) as id.

        Only used by the SVG renderer.
        """

    def close_group(self, s):
        """
        Close a grouping element with label *s*.

        Only used by the SVG renderer.
        """

    def draw_path(self, gc, path, transform, rgbFace=None):
        """Draw a `~.path.Path` instance using the given affine transform."""
        raise NotImplementedError

    def draw_markers(self, gc, marker_path, marker_trans, path,
                     trans, rgbFace=None):
        """
        Draw a marker at each of *path*'s vertices (excluding control points).

        The base (fallback) implementation makes multiple calls to `draw_path`.
        Backends may want to override this method in order to draw the marker
        only once and reuse it multiple times.

        Parameters
        ----------
        gc : `.GraphicsContextBase`
            The graphics context.
        marker_path : `~matplotlib.path.Path`
            The path for the marker.
        marker_trans : `~matplotlib.transforms.Transform`
            An affine transform applied to the marker.
        path : `~matplotlib.path.Path`
            The locations to draw the markers.
        trans : `~matplotlib.transforms.Transform`
            An affine transform applied to the path.
        rgbFace : :mpltype:`color`, optional
        """
        for vertices, codes in path.iter_segments(trans, simplify=False):
            if len(vertices):
                x, y = vertices[-2:]
                self.draw_path(gc, marker_path,
                               marker_trans +
                               transforms.Affine2D().translate(x, y),
                               rgbFace)

    def draw_path_collection(self, gc, master_transform, paths, all_transforms,
                             offsets, offset_trans, facecolors, edgecolors,
                             linewidths, linestyles, antialiaseds, urls,
                             offset_position):
        """
        Draw a collection of *paths*.

        Each path is first transformed by the corresponding entry
        in *all_transforms* (a list of (3, 3) matrices) and then by
        *master_transform*.  They are then translated by the corresponding
        entry in *offsets*, which has been first transformed by *offset_trans*.

        *facecolors*, *edgecolors*, *linewidths*, *linestyles*, and
        *antialiased* are lists that set the corresponding properties.

        *offset_position* is unused now, but the argument is kept for
        backwards compatibility.

        The base (fallback) implementation makes multiple calls to `draw_path`.
        Backends may want to override this in order to render each set of
        path data only once, and then reference that path multiple times with
        the different offsets, colors, styles etc.  The generator methods
        `_iter_collection_raw_paths` and `_iter_collection` are provided to
        help with (and standardize) the implementation across backends.  It
        is highly recommended to use those generators, so that changes to the
        behavior of `draw_path_collection` can be made globally.
        """
        path_ids = self._iter_collection_raw_paths(master_transform,
                                                   paths, all_transforms)

        for xo, yo, path_id, gc0, rgbFace in self._iter_collection(
                gc, list(path_ids), offsets, offset_trans,
                facecolors, edgecolors, linewidths, linestyles,
                antialiaseds, urls, offset_position):
            path, transform = path_id
            # Only apply another translation if we have an offset, else we
            # reuse the initial transform.
            if xo != 0 or yo != 0:
                # The transformation can be used by multiple paths. Since
                # translate is a inplace operation, we need to copy the
                # transformation by .frozen() before applying the translation.
                transform = transform.frozen()
                transform.translate(xo, yo)
            self.draw_path(gc0, path, transform, rgbFace)

    def draw_quad_mesh(self, gc, master_transform, meshWidth, meshHeight,
                       coordinates, offsets, offsetTrans, facecolors,
                       antialiased, edgecolors):
        """
        Draw a quadmesh.

        The base (fallback) implementation converts the quadmesh to paths and
        then calls `draw_path_collection`.
        """

        from matplotlib.collections import QuadMesh
        paths = QuadMesh._convert_mesh_to_paths(coordinates)

        if edgecolors is None:
            edgecolors = facecolors
        linewidths = np.array([gc.get_linewidth()], float)

        return self.draw_path_collection(
            gc, master_transform, paths, [], offsets, offsetTrans, facecolors,
            edgecolors, linewidths, [], [antialiased], [None], 'screen')

    def draw_gouraud_triangles(self, gc, triangles_array, colors_array,
                               transform):
        """
        Draw a series of Gouraud triangles.

        Parameters
        ----------
        gc : `.GraphicsContextBase`
            The graphics context.
        triangles_array : (N, 3, 2) array-like
            Array of *N* (x, y) points for the triangles.
        colors_array : (N, 3, 4) array-like
            Array of *N* RGBA colors for each point of the triangles.
        transform : `~matplotlib.transforms.Transform`
            An affine transform to apply to the points.
        """
        raise NotImplementedError

    def _iter_collection_raw_paths(self, master_transform, paths,
                                   all_transforms):
        """
        Helper method (along with `_iter_collection`) to implement
        `draw_path_collection` in a memory-efficient manner.

        This method yields all of the base path/transform combinations, given a
        master transform, a list of paths and list of transforms.

        The arguments should be exactly what is passed in to
        `draw_path_collection`.

        The backend should take each yielded path and transform and create an
        object that can be referenced (reused) later.
        """
        Npaths = len(paths)
        Ntransforms = len(all_transforms)
        N = max(Npaths, Ntransforms)

        if Npaths == 0:
            return

        transform = transforms.IdentityTransform()
        for i in range(N):
            path = paths[i % Npaths]
            if Ntransforms:
                transform = Affine2D(all_transforms[i % Ntransforms])
            yield path, transform + master_transform

    def _iter_collection_uses_per_path(self, paths, all_transforms,
                                       offsets, facecolors, edgecolors):
        """
        Compute how many times each raw path object returned by
        `_iter_collection_raw_paths` would be used when calling
        `_iter_collection`. This is intended for the backend to decide
        on the tradeoff between using the paths in-line and storing
        them once and reusing. Rounds up in case the number of uses
        is not the same for every path.
        """
        Npaths = len(paths)
        if Npaths == 0 or len(facecolors) == len(edgecolors) == 0:
            return 0
        Npath_ids = max(Npaths, len(all_transforms))
        N = max(Npath_ids, len(offsets))
        return (N + Npath_ids - 1) // Npath_ids

    def _iter_collection(self, gc, path_ids, offsets, offset_trans, facecolors,
                         edgecolors, linewidths, linestyles,
                         antialiaseds, urls, offset_position):
        """
        Helper method (along with `_iter_collection_raw_paths`) to implement
        `draw_path_collection` in a memory-efficient manner.

        This method yields all of the path, offset and graphics context
        combinations to draw the path collection.  The caller should already
        have looped over the results of `_iter_collection_raw_paths` to draw
        this collection.

        The arguments should be the same as that passed into
        `draw_path_collection`, with the exception of *path_ids*, which is a
        list of arbitrary objects that the backend will use to reference one of
        the paths created in the `_iter_collection_raw_paths` stage.

        Each yielded result is of the form::

           xo, yo, path_id, gc, rgbFace

        where *xo*, *yo* is an offset; *path_id* is one of the elements of
        *path_ids*; *gc* is a graphics context and *rgbFace* is a color to
        use for filling the path.
        """
        Npaths = len(path_ids)
        Noffsets = len(offsets)
        N = max(Npaths, Noffsets)
        Nfacecolors = len(facecolors)
        Nedgecolors = len(edgecolors)
        Nlinewidths = len(linewidths)
        Nlinestyles = len(linestyles)
        Nurls = len(urls)

        if (Nfacecolors == 0 and Nedgecolors == 0) or Npaths == 0:
            return

        gc0 = self.new_gc()
        gc0.copy_properties(gc)

        def cycle_or_default(seq, default=None):
            # Cycle over *seq* if it is not empty; else always yield *default*.
            return (itertools.cycle(seq) if len(seq)
                    else itertools.repeat(default))

        pathids = cycle_or_default(path_ids)
        toffsets = cycle_or_default(offset_trans.transform(offsets), (0, 0))
        fcs = cycle_or_default(facecolors)
        ecs = cycle_or_default(edgecolors)
        lws = cycle_or_default(linewidths)
        lss = cycle_or_default(linestyles)
        aas = cycle_or_default(antialiaseds)
        urls = cycle_or_default(urls)

        if Nedgecolors == 0:
            gc0.set_linewidth(0.0)

        for pathid, (xo, yo), fc, ec, lw, ls, aa, url in itertools.islice(
                zip(pathids, toffsets, fcs, ecs, lws, lss, aas, urls), N):
            if not (np.isfinite(xo) and np.isfinite(yo)):
                continue
            if Nedgecolors:
                if Nlinewidths:
                    gc0.set_linewidth(lw)
                if Nlinestyles:
                    gc0.set_dashes(*ls)
                if len(ec) == 4 and ec[3] == 0.0:
                    gc0.set_linewidth(0)
                else:
                    gc0.set_foreground(ec)
            if fc is not None and len(fc) == 4 and fc[3] == 0:
                fc = None
            gc0.set_antialiased(aa)
            if Nurls:
                gc0.set_url(url)
            yield xo, yo, pathid, gc0, fc
        gc0.restore()

    def get_image_magnification(self):
        """
        Get the factor by which to magnify images passed to `draw_image`.
        Allows a backend to have images at a different resolution to other
        artists.
        """
        return 1.0

    def draw_image(self, gc, x, y, im, transform=None):
        """
        Draw an RGBA image.

        Parameters
        ----------
        gc : `.GraphicsContextBase`
            A graphics context with clipping information.

        x : float
            The distance in physical units (i.e., dots or pixels) from the left
            hand side of the canvas.

        y : float
            The distance in physical units (i.e., dots or pixels) from the
            bottom side of the canvas.

        im : (N, M, 4) array of `numpy.uint8`
            An array of RGBA pixels.

        transform : `~matplotlib.transforms.Affine2DBase`
            If and only if the concrete backend is written such that
            `option_scale_image` returns ``True``, an affine transformation
            (i.e., an `.Affine2DBase`) *may* be passed to `draw_image`.  The
            translation vector of the transformation is given in physical units
            (i.e., dots or pixels). Note that the transformation does not
            override *x* and *y*, and has to be applied *before* translating
            the result by *x* and *y* (this can be accomplished by adding *x*
            and *y* to the translation vector defined by *transform*).
        """
        raise NotImplementedError

    def option_image_nocomposite(self):
        """
        Return whether image composition by Matplotlib should be skipped.

        Raster backends should usually return False (letting the C-level
        rasterizer take care of image composition); vector backends should
        usually return ``not rcParams["image.composite_image"]``.
        """
        return False

    def option_scale_image(self):
        """
        Return whether arbitrary affine transformations in `draw_image` are
        supported (True for most vector backends).
        """
        return False

    def draw_tex(self, gc, x, y, s, prop, angle, *, mtext=None):
        """
        Draw a TeX instance.

        Parameters
        ----------
        gc : `.GraphicsContextBase`
            The graphics context.
        x : float
            The x location of the text in display coords.
        y : float
            The y location of the text baseline in display coords.
        s : str
            The TeX text string.
        prop : `~matplotlib.font_manager.FontProperties`
            The font properties.
        angle : float
            The rotation angle in degrees anti-clockwise.
        mtext : `~matplotlib.text.Text`
            The original text object to be rendered.
        """
        self._draw_text_as_path(gc, x, y, s, prop, angle, ismath="TeX")

    def draw_text(self, gc, x, y, s, prop, angle, ismath=False, mtext=None):
        """
        Draw a text instance.

        Parameters
        ----------
        gc : `.GraphicsContextBase`
            The graphics context.
        x : float
            The x location of the text in display coords.
        y : float
            The y location of the text baseline in display coords.
        s : str
            The text string.
        prop : `~matplotlib.font_manager.FontProperties`
            The font properties.
        angle : float
            The rotation angle in degrees anti-clockwise.
        ismath : bool or "TeX"
            If True, use mathtext parser.
        mtext : `~matplotlib.text.Text`
            The original text object to be rendered.

        Notes
        -----
        **Notes for backend implementers:**

        `.RendererBase.draw_text` also supports passing "TeX" to the *ismath*
        parameter to use TeX rendering, but this is not required for actual
        rendering backends, and indeed many builtin backends do not support
        this.  Rather, TeX rendering is provided by `~.RendererBase.draw_tex`.
        """
        self._draw_text_as_path(gc, x, y, s, prop, angle, ismath)

    def _draw_text_as_path(self, gc, x, y, s, prop, angle, ismath):
        """
        Draw the text by converting them to paths using `.TextToPath`.

        This private helper supports the same parameters as
        `~.RendererBase.draw_text`; setting *ismath* to "TeX" triggers TeX
        rendering.
        """
        text2path = self._text2path
        fontsize = self.points_to_pixels(prop.get_size_in_points())
        verts, codes = text2path.get_text_path(prop, s, ismath=ismath)
        path = Path(verts, codes)
        if self.flipy():
            width, height = self.get_canvas_width_height()
            transform = (Affine2D()
                         .scale(fontsize / text2path.FONT_SCALE)
                         .rotate_deg(angle)
                         .translate(x, height - y))
        else:
            transform = (Affine2D()
                         .scale(fontsize / text2path.FONT_SCALE)
                         .rotate_deg(angle)
                         .translate(x, y))
        color = gc.get_rgb()
        gc.set_linewidth(0.0)
        self.draw_path(gc, path, transform, rgbFace=color)

    def get_text_width_height_descent(self, s, prop, ismath):
        """
        Get the width, height, and descent (offset from the bottom to the baseline), in
        display coords, of the string *s* with `.FontProperties` *prop*.

        Whitespace at the start and the end of *s* is included in the reported width.
        """
        fontsize = prop.get_size_in_points()

        if ismath == 'TeX':
            # todo: handle properties
            return self.get_texmanager().get_text_width_height_descent(
                s, fontsize, renderer=self)

        dpi = self.points_to_pixels(72)
        if ismath:
            dims = self._text2path.mathtext_parser.parse(s, dpi, prop)
            return dims[0:3]  # return width, height, descent

        flags = self._text2path._get_hinting_flag()
        font = self._text2path._get_font(prop)
        font.set_size(fontsize, dpi)
        # the width and height of unrotated string
        font.set_text(s, 0.0, flags=flags)
        w, h = font.get_width_height()
        d = font.get_descent()
        w /= 64.0  # convert from subpixels
        h /= 64.0
        d /= 64.0
        return w, h, d

    def flipy(self):
        """
        Return whether y values increase from top to bottom.

        Note that this only affects drawing of texts.
        """
        return True

    def get_canvas_width_height(self):
        """Return the canvas width and height in display coords."""
        return 1, 1

    def get_texmanager(self):
        """Return the `.TexManager` instance."""
        if self._texmanager is None:
            self._texmanager = TexManager()
        return self._texmanager

    def new_gc(self):
        """Return an instance of a `.GraphicsContextBase`."""
        return GraphicsContextBase()

    def points_to_pixels(self, points):
        """
        Convert points to display units.

        You need to override this function (unless your backend
        doesn't have a dpi, e.g., postscript or svg).  Some imaging
        systems assume some value for pixels per inch::

            points to pixels = points * pixels_per_inch/72 * dpi/72

        Parameters
        ----------
        points : float or array-like

        Returns
        -------
        Points converted to pixels
        """
        return points

    def start_rasterizing(self):
        """
        Switch to the raster renderer.

        Used by `.MixedModeRenderer`.
        """

    def stop_rasterizing(self):
        """
        Switch back to the vector renderer and draw the contents of the raster
        renderer as an image on the vector renderer.

        Used by `.MixedModeRenderer`.
        """

    def start_filter(self):
        """
        Switch to a temporary renderer for image filtering effects.

        Currently only supported by the agg renderer.
        """

    def stop_filter(self, filter_func):
        """
        Switch back to the original renderer.  The contents of the temporary
        renderer is processed with the *filter_func* and is drawn on the
        original renderer as an image.

        Currently only supported by the agg renderer.
        """

    def _draw_disabled(self):
        """
        Context manager to temporary disable drawing.

        This is used for getting the drawn size of Artists.  This lets us
        run the draw process to update any Python state but does not pay the
        cost of the draw_XYZ calls on the canvas.
        """
        no_ops = {
            meth_name: lambda *args, **kwargs: None
            for meth_name in dir(RendererBase)
            if (meth_name.startswith("draw_")
                or meth_name in ["open_group", "close_group"])
        }

        return _setattr_cm(self, **no_ops)


class GraphicsContextBase:
    """An abstract base class that provides color, line styles, etc."""

    def __init__(self):
        self._alpha = 1.0
        self._forced_alpha = False  # if True, _alpha overrides A from RGBA
        self._antialiased = 1  # use 0, 1 not True, False for extension code
        self._capstyle = CapStyle('butt')
        self._cliprect = None
        self._clippath = None
        self._dashes = 0, None
        self._joinstyle = JoinStyle('round')
        self._linestyle = 'solid'
        self._linewidth = 1
        self._rgb = (0.0, 0.0, 0.0, 1.0)
        self._hatch = None
        self._hatch_color = colors.to_rgba(rcParams['hatch.color'])
        self._hatch_linewidth = rcParams['hatch.linewidth']
        self._url = None
        self._gid = None
        self._snap = None
        self._sketch = None

    def copy_properties(self, gc):
        """Copy properties from *gc* to self."""
        self._alpha = gc._alpha
        self._forced_alpha = gc._forced_alpha
        self._antialiased = gc._antialiased
        self._capstyle = gc._capstyle
        self._cliprect = gc._cliprect
        self._clippath = gc._clippath
        self._dashes = gc._dashes
        self._joinstyle = gc._joinstyle
        self._linestyle = gc._linestyle
        self._linewidth = gc._linewidth
        self._rgb = gc._rgb
        self._hatch = gc._hatch
        self._hatch_color = gc._hatch_color
        self._hatch_linewidth = gc._hatch_linewidth
        self._url = gc._url
        self._gid = gc._gid
        self._snap = gc._snap
        self._sketch = gc._sketch

    def restore(self):
        """
        Restore the graphics context from the stack - needed only
        for backends that save graphics contexts on a stack.
        """

    def get_alpha(self):
        """
        Return the alpha value used for blending - not supported on all
        backends.
        """
        return self._alpha

    def get_antialiased(self):
        """Return whether the object should try to do antialiased rendering."""
        return self._antialiased

    def get_capstyle(self):
        """Return the `.CapStyle`."""
        return self._capstyle.name

    def get_clip_rectangle(self):
        """
        Return the clip rectangle as a `~matplotlib.transforms.Bbox` instance.
        """
        return self._cliprect

    def get_clip_path(self):
        """
        Return the clip path in the form (path, transform), where path
        is a `~.path.Path` instance, and transform is
        an affine transform to apply to the path before clipping.
        """
        if self._clippath is not None:
            tpath, tr = self._clippath.get_transformed_path_and_affine()
            if np.all(np.isfinite(tpath.vertices)):
                return tpath, tr
            else:
                _log.warning("Ill-defined clip_path detected. Returning None.")
                return None, None
        return None, None

    def get_dashes(self):
        """
        Return the dash style as an (offset, dash-list) pair.

        See `.set_dashes` for details.

        Default value is (None, None).
        """
        return self._dashes

    def get_forced_alpha(self):
        """
        Return whether the value given by get_alpha() should be used to
        override any other alpha-channel values.
        """
        return self._forced_alpha

    def get_joinstyle(self):
        """Return the `.JoinStyle`."""
        return self._joinstyle.name

    def get_linewidth(self):
        """Return the line width in points."""
        return self._linewidth

    def get_rgb(self):
        """Return a tuple of three or four floats from 0-1."""
        return self._rgb

    def get_url(self):
        """Return a url if one is set, None otherwise."""
        return self._url

    def get_gid(self):
        """Return the object identifier if one is set, None otherwise."""
        return self._gid

    def get_snap(self):
        """
        Return the snap setting, which can be:

        * True: snap vertices to the nearest pixel center
        * False: leave vertices as-is
        * None: (auto) If the path contains only rectilinear line segments,
          round to the nearest pixel center
        """
        return self._snap

    def set_alpha(self, alpha):
        """
        Set the alpha value used for blending - not supported on all backends.

        If ``alpha=None`` (the default), the alpha components of the
        foreground and fill colors will be used to set their respective
        transparencies (where applicable); otherwise, ``alpha`` will override
        them.
        """
        if alpha is not None:
            self._alpha = alpha
            self._forced_alpha = True
        else:
            self._alpha = 1.0
            self._forced_alpha = False
        self.set_foreground(self._rgb, isRGBA=True)

    def set_antialiased(self, b):
        """Set whether object should be drawn with antialiased rendering."""
        # Use ints to make life easier on extension code trying to read the gc.
        self._antialiased = int(bool(b))

    @_docstring.interpd
    def set_capstyle(self, cs):
        """
        Set how to draw endpoints of lines.

        Parameters
        ----------
        cs : `.CapStyle` or %(CapStyle)s
        """
        self._capstyle = CapStyle(cs)

    def set_clip_rectangle(self, rectangle):
        """Set the clip rectangle to a `.Bbox` or None."""
        self._cliprect = rectangle

    def set_clip_path(self, path):
        """Set the clip path to a `.TransformedPath` or None."""
        _api.check_isinstance((transforms.TransformedPath, None), path=path)
        self._clippath = path

    def set_dashes(self, dash_offset, dash_list):
        """
        Set the dash style for the gc.

        Parameters
        ----------
        dash_offset : float
            Distance, in points, into the dash pattern at which to
            start the pattern. It is usually set to 0.
        dash_list : array-like or None
            The on-off sequence as points.  None specifies a solid line. All
            values must otherwise be non-negative (:math:`\\ge 0`).

        Notes
        -----
        See p. 666 of the PostScript
        `Language Reference
        <https://www.adobe.com/jp/print/postscript/pdfs/PLRM.pdf>`_
        for more info.
        """
        if dash_list is not None:
            dl = np.asarray(dash_list)
            if np.any(dl < 0.0):
                raise ValueError(
                    "All values in the dash list must be non-negative")
            if dl.size and not np.any(dl > 0.0):
                raise ValueError(
                    'At least one value in the dash list must be positive')
        self._dashes = dash_offset, dash_list

    def set_foreground(self, fg, isRGBA=False):
        """
        Set the foreground color.

        Parameters
        ----------
        fg : :mpltype:`color`
        isRGBA : bool
            If *fg* is known to be an ``(r, g, b, a)`` tuple, *isRGBA* can be
            set to True to improve performance.
        """
        if self._forced_alpha and isRGBA:
            self._rgb = fg[:3] + (self._alpha,)
        elif self._forced_alpha:
            self._rgb = colors.to_rgba(fg, self._alpha)
        elif isRGBA:
            self._rgb = fg
        else:
            self._rgb = colors.to_rgba(fg)

    @_docstring.interpd
    def set_joinstyle(self, js):
        """
        Set how to draw connections between line segments.

        Parameters
        ----------
        js : `.JoinStyle` or %(JoinStyle)s
        """
        self._joinstyle = JoinStyle(js)

    def set_linewidth(self, w):
        """Set the linewidth in points."""
        self._linewidth = float(w)

    def set_url(self, url):
        """Set the url for links in compatible backends."""
        self._url = url

    def set_gid(self, id):
        """Set the id."""
        self._gid = id

    def set_snap(self, snap):
        """
        Set the snap setting which may be:

        * True: snap vertices to the nearest pixel center
        * False: leave vertices as-is
        * None: (auto) If the path contains only rectilinear line segments,
          round to the nearest pixel center
        """
        self._snap = snap

    def set_hatch(self, hatch):
        """Set the hatch style (for fills)."""
        self._hatch = hatch

    def get_hatch(self):
        """Get the current hatch style."""
        return self._hatch

    def get_hatch_path(self, density=6.0):
        """Return a `.Path` for the current hatch."""
        hatch = self.get_hatch()
        if hatch is None:
            return None
        return Path.hatch(hatch, density)

    def get_hatch_color(self):
        """Get the hatch color."""
        return self._hatch_color

    def set_hatch_color(self, hatch_color):
        """Set the hatch color."""
        self._hatch_color = hatch_color

    def get_hatch_linewidth(self):
        """Get the hatch linewidth."""
        return self._hatch_linewidth

    def set_hatch_linewidth(self, hatch_linewidth):
        """Set the hatch linewidth."""
        self._hatch_linewidth = hatch_linewidth

    def get_sketch_params(self):
        """
        Return the sketch parameters for the artist.

        Returns
        -------
        tuple or `None`

            A 3-tuple with the following elements:

            * ``scale``: The amplitude of the wiggle perpendicular to the
              source line.
            * ``length``: The length of the wiggle along the line.
            * ``randomness``: The scale factor by which the length is
              shrunken or expanded.

            May return `None` if no sketch parameters were set.
        """
        return self._sketch

    def set_sketch_params(self, scale=None, length=None, randomness=None):
        """
        Set the sketch parameters.

        Parameters
        ----------
        scale : float, optional
            The amplitude of the wiggle perpendicular to the source line, in
            pixels.  If scale is `None`, or not provided, no sketch filter will
            be provided.
        length : float, default: 128
            The length of the wiggle along the line, in pixels.
        randomness : float, default: 16
            The scale factor by which the length is shrunken or expanded.
        """
        self._sketch = (
            None if scale is None
            else (scale, length or 128., randomness or 16.))


class TimerBase:
    """
    A base class for providing timer events, useful for things animations.
    Backends need to implement a few specific methods in order to use their
    own timing mechanisms so that the timer events are integrated into their
    event loops.

    Subclasses must override the following methods:

    - ``_timer_start``: Backend-specific code for starting the timer.
    - ``_timer_stop``: Backend-specific code for stopping the timer.

    Subclasses may additionally override the following methods:

    - ``_timer_set_single_shot``: Code for setting the timer to single shot
      operating mode, if supported by the timer object.  If not, the `Timer`
      class itself will store the flag and the ``_on_timer`` method should be
      overridden to support such behavior.

    - ``_timer_set_interval``: Code for setting the interval on the timer, if
      there is a method for doing so on the timer object.

    - ``_on_timer``: The internal function that any timer object should call,
      which will handle the task of running all callbacks that have been set.
    """

    def __init__(self, interval=None, callbacks=None):
        """
        Parameters
        ----------
        interval : int, default: 1000ms
            The time between timer events in milliseconds.  Will be stored as
            ``timer.interval``.
        callbacks : list[tuple[callable, tuple, dict]]
            List of (func, args, kwargs) tuples that will be called upon timer
            events.  This list is accessible as ``timer.callbacks`` and can be
            manipulated directly, or the functions `~.TimerBase.add_callback`
            and `~.TimerBase.remove_callback` can be used.
        """
        self.callbacks = [] if callbacks is None else callbacks.copy()
        # Set .interval and not ._interval to go through the property setter.
        self.interval = 1000 if interval is None else interval
        self.single_shot = False

    def __del__(self):
        """Need to stop timer and possibly disconnect timer."""
        self._timer_stop()

    @_api.delete_parameter("3.9", "interval", alternative="timer.interval")
    def start(self, interval=None):
        """
        Start the timer object.

        Parameters
        ----------
        interval : int, optional
            Timer interval in milliseconds; overrides a previously set interval
            if provided.
        """
        if interval is not None:
            self.interval = interval
        self._timer_start()

    def stop(self):
        """Stop the timer."""
        self._timer_stop()

    def _timer_start(self):
        pass

    def _timer_stop(self):
        pass

    @property
    def interval(self):
        """The time between timer events, in milliseconds."""
        return self._interval

    @interval.setter
    def interval(self, interval):
        # Force to int since none of the backends actually support fractional
        # milliseconds, and some error or give warnings.
        # Some backends also fail when interval == 0, so ensure >= 1 msec
        interval = max(int(interval), 1)
        self._interval = interval
        self._timer_set_interval()

    @property
    def single_shot(self):
        """Whether this timer should stop after a single run."""
        return self._single

    @single_shot.setter
    def single_shot(self, ss):
        self._single = ss
        self._timer_set_single_shot()

    def add_callback(self, func, *args, **kwargs):
        """
        Register *func* to be called by timer when the event fires. Any
        additional arguments provided will be passed to *func*.

        This function returns *func*, which makes it possible to use it as a
        decorator.
        """
        self.callbacks.append((func, args, kwargs))
        return func

    def remove_callback(self, func, *args, **kwargs):
        """
        Remove *func* from list of callbacks.

        *args* and *kwargs* are optional and used to distinguish between copies
        of the same function registered to be called with different arguments.
        This behavior is deprecated.  In the future, ``*args, **kwargs`` won't
        be considered anymore; to keep a specific callback removable by itself,
        pass it to `add_callback` as a `functools.partial` object.
        """
        if args or kwargs:
            _api.warn_deprecated(
                "3.1", message="In a future version, Timer.remove_callback "
                "will not take *args, **kwargs anymore, but remove all "
                "callbacks where the callable matches; to keep a specific "
                "callback removable by itself, pass it to add_callback as a "
                "functools.partial object.")
            self.callbacks.remove((func, args, kwargs))
        else:
            funcs = [c[0] for c in self.callbacks]
            if func in funcs:
                self.callbacks.pop(funcs.index(func))

    def _timer_set_interval(self):
        """Used to set interval on underlying timer object."""

    def _timer_set_single_shot(self):
        """Used to set single shot on underlying timer object."""

    def _on_timer(self):
        """
        Runs all function that have been registered as callbacks. Functions
        can return False (or 0) if they should not be called any more. If there
        are no callbacks, the timer is automatically stopped.
        """
        for func, args, kwargs in self.callbacks:
            ret = func(*args, **kwargs)
            # docstring above explains why we use `if ret == 0` here,
            # instead of `if not ret`.
            # This will also catch `ret == False` as `False == 0`
            # but does not annoy the linters
            # https://docs.python.org/3/library/stdtypes.html#boolean-values
            if ret == 0:
                self.callbacks.remove((func, args, kwargs))

        if len(self.callbacks) == 0:
            self.stop()


class Event:
    """
    A Matplotlib event.

    The following attributes are defined and shown with their default values.
    Subclasses may define additional attributes.

    Attributes
    ----------
    name : str
        The event name.
    canvas : `FigureCanvasBase`
        The backend-specific canvas instance generating the event.
    guiEvent
        The GUI event that triggered the Matplotlib event.
    """

    def __init__(self, name, canvas, guiEvent=None):
        self.name = name
        self.canvas = canvas
        self.guiEvent = guiEvent

    def _process(self):
        """Process this event on ``self.canvas``, then unset ``guiEvent``."""
        self.canvas.callbacks.process(self.name, self)
        self.guiEvent = None


class DrawEvent(Event):
    """
    An event triggered by a draw operation on the canvas.

    In most backends, callbacks subscribed to this event will be fired after
    the rendering is complete but before the screen is updated. Any extra
    artists drawn to the canvas's renderer will be reflected without an
    explicit call to ``blit``.

    .. warning::

       Calling ``canvas.draw`` and ``canvas.blit`` in these callbacks may
       not be safe with all backends and may cause infinite recursion.

    A DrawEvent has a number of special attributes in addition to those defined
    by the parent `Event` class.

    Attributes
    ----------
    renderer : `RendererBase`
        The renderer for the draw event.
    """
    def __init__(self, name, canvas, renderer):
        super().__init__(name, canvas)
        self.renderer = renderer


class ResizeEvent(Event):
    """
    An event triggered by a canvas resize.

    A ResizeEvent has a number of special attributes in addition to those
    defined by the parent `Event` class.

    Attributes
    ----------
    width : int
        Width of the canvas in pixels.
    height : int
        Height of the canvas in pixels.
    """

    def __init__(self, name, canvas):
        super().__init__(name, canvas)
        self.width, self.height = canvas.get_width_height()


class CloseEvent(Event):
    """An event triggered by a figure being closed."""


class LocationEvent(Event):
    """
    An event that has a screen location.

    A LocationEvent has a number of special attributes in addition to those
    defined by the parent `Event` class.

    Attributes
    ----------
    x, y : int or None
        Event location in pixels from bottom left of canvas.
    inaxes : `~matplotlib.axes.Axes` or None
        The `~.axes.Axes` instance over which the mouse is, if any.
    xdata, ydata : float or None
        Data coordinates of the mouse within *inaxes*, or *None* if the mouse
        is not over an Axes.
    modifiers : frozenset
        The keyboard modifiers currently being pressed (except for KeyEvent).
    """

    _last_axes_ref = None

    def __init__(self, name, canvas, x, y, guiEvent=None, *, modifiers=None):
        super().__init__(name, canvas, guiEvent=guiEvent)
        # x position - pixels from left of canvas
        self.x = int(x) if x is not None else x
        # y position - pixels from right of canvas
        self.y = int(y) if y is not None else y
        self.inaxes = None  # the Axes instance the mouse is over
        self.xdata = None   # x coord of mouse in data coords
        self.ydata = None   # y coord of mouse in data coords
        self.modifiers = frozenset(modifiers if modifiers is not None else [])

        if x is None or y is None:
            # cannot check if event was in Axes if no (x, y) info
            return

        self._set_inaxes(self.canvas.inaxes((x, y))
                         if self.canvas.mouse_grabber is None else
                         self.canvas.mouse_grabber,
                         (x, y))

    # Splitting _set_inaxes out is useful for the axes_leave_event handler: it
    # needs to generate synthetic LocationEvents with manually-set inaxes.  In
    # that latter case, xy has already been cast to int so it can directly be
    # read from self.x, self.y; in the normal case, however, it is more
    # accurate to pass the untruncated float x, y values passed to the ctor.

    def _set_inaxes(self, inaxes, xy=None):
        self.inaxes = inaxes
        if inaxes is not None:
            try:
                self.xdata, self.ydata = inaxes.transData.inverted().transform(
                    xy if xy is not None else (self.x, self.y))
            except ValueError:
                pass


class MouseButton(IntEnum):
    LEFT = 1
    MIDDLE = 2
    RIGHT = 3
    BACK = 8
    FORWARD = 9


class MouseEvent(LocationEvent):
    """
    A mouse event ('button_press_event', 'button_release_event', \
'scroll_event', 'motion_notify_event').

    A MouseEvent has a number of special attributes in addition to those
    defined by the parent `Event` and `LocationEvent` classes.

    Attributes
    ----------
    button : None or `MouseButton` or {'up', 'down'}
        The button pressed. 'up' and 'down' are used for scroll events.

        Note that LEFT and RIGHT actually refer to the "primary" and
        "secondary" buttons, i.e. if the user inverts their left and right
        buttons ("left-handed setting") then the LEFT button will be the one
        physically on the right.

        If this is unset, *name* is "scroll_event", and *step* is nonzero, then
        this will be set to "up" or "down" depending on the sign of *step*.

    buttons : None or frozenset
        For 'motion_notify_event', the mouse buttons currently being pressed
        (a set of zero or more MouseButtons);
        for other events, None.

        .. note::
           For 'motion_notify_event', this attribute is more accurate than
           the ``button`` (singular) attribute, which is obtained from the last
           'button_press_event' or 'button_release_event' that occurred within
           the canvas (and thus 1. be wrong if the last change in mouse state
           occurred when the canvas did not have focus, and 2. cannot report
           when multiple buttons are pressed).

           This attribute is not set for 'button_press_event' and
           'button_release_event' because GUI toolkits are inconsistent as to
           whether they report the button state *before* or *after* the
           press/release occurred.

        .. warning::
           On macOS, the Tk backends only report a single button even if
           multiple buttons are pressed.

    key : None or str
        The key pressed when the mouse event triggered, e.g. 'shift'.
        See `KeyEvent`.

        .. warning::
           This key is currently obtained from the last 'key_press_event' or
           'key_release_event' that occurred within the canvas.  Thus, if the
           last change of keyboard state occurred while the canvas did not have
           focus, this attribute will be wrong.  On the other hand, the
           ``modifiers`` attribute should always be correct, but it can only
           report on modifier keys.

    step : float
        The number of scroll steps (positive for 'up', negative for 'down').
        This applies only to 'scroll_event' and defaults to 0 otherwise.

    dblclick : bool
        Whether the event is a double-click. This applies only to
        'button_press_event' and is False otherwise. In particular, it's
        not used in 'button_release_event'.

    Examples
    --------
    ::

        def on_press(event):
            print('you pressed', event.button, event.xdata, event.ydata)

        cid = fig.canvas.mpl_connect('button_press_event', on_press)
    """

    def __init__(self, name, canvas, x, y, button=None, key=None,
                 step=0, dblclick=False, guiEvent=None, *,
                 buttons=None, modifiers=None):
        super().__init__(
            name, canvas, x, y, guiEvent=guiEvent, modifiers=modifiers)
        if button in MouseButton.__members__.values():
            button = MouseButton(button)
        if name == "scroll_event" and button is None:
            if step > 0:
                button = "up"
            elif step < 0:
                button = "down"
        self.button = button
        if name == "motion_notify_event":
            self.buttons = frozenset(buttons if buttons is not None else [])
        else:
            # We don't support 'buttons' for button_press/release_event because
            # toolkits are inconsistent as to whether they report the state
            # before or after the event.
            if buttons:
                raise ValueError(
                    "'buttons' is only supported for 'motion_notify_event'")
            self.buttons = None
        self.key = key
        self.step = step
        self.dblclick = dblclick

    def __str__(self):
        return (f"{self.name}: "
                f"xy=({self.x}, {self.y}) xydata=({self.xdata}, {self.ydata}) "
                f"button={self.button} dblclick={self.dblclick} "
                f"inaxes={self.inaxes}")


class PickEvent(Event):
    """
    A pick event.

    This event is fired when the user picks a location on the canvas
    sufficiently close to an artist that has been made pickable with
    `.Artist.set_picker`.

    A PickEvent has a number of special attributes in addition to those defined
    by the parent `Event` class.

    Attributes
    ----------
    mouseevent : `MouseEvent`
        The mouse event that generated the pick.
    artist : `~matplotlib.artist.Artist`
        The picked artist.  Note that artists are not pickable by default
        (see `.Artist.set_picker`).
    other
        Additional attributes may be present depending on the type of the
        picked object; e.g., a `.Line2D` pick may define different extra
        attributes than a `.PatchCollection` pick.

    Examples
    --------
    Bind a function ``on_pick()`` to pick events, that prints the coordinates
    of the picked data point::

        ax.plot(np.rand(100), 'o', picker=5)  # 5 points tolerance

        def on_pick(event):
            line = event.artist
            xdata, ydata = line.get_data()
            ind = event.ind
            print(f'on pick line: {xdata[ind]:.3f}, {ydata[ind]:.3f}')

        cid = fig.canvas.mpl_connect('pick_event', on_pick)
    """

    def __init__(self, name, canvas, mouseevent, artist,
                 guiEvent=None, **kwargs):
        if guiEvent is None:
            guiEvent = mouseevent.guiEvent
        super().__init__(name, canvas, guiEvent)
        self.mouseevent = mouseevent
        self.artist = artist
        self.__dict__.update(kwargs)


class KeyEvent(LocationEvent):
    """
    A key event (key press, key release).

    A KeyEvent has a number of special attributes in addition to those defined
    by the parent `Event` and `LocationEvent` classes.

    Attributes
    ----------
    key : None or str
        The key(s) pressed. Could be *None*, a single case sensitive Unicode
        character ("g", "G", "#", etc.), a special key ("control", "shift",
        "f1", "up", etc.) or a combination of the above (e.g., "ctrl+alt+g",
        "ctrl+alt+G").

    Notes
    -----
    Modifier keys will be prefixed to the pressed key and will be in the order
    "ctrl", "alt", "super". The exception to this rule is when the pressed key
    is itself a modifier key, therefore "ctrl+alt" and "alt+control" can both
    be valid key values.

    Examples
    --------
    ::

        def on_key(event):
            print('you pressed', event.key, event.xdata, event.ydata)

        cid = fig.canvas.mpl_connect('key_press_event', on_key)
    """

    def __init__(self, name, canvas, key, x=0, y=0, guiEvent=None):
        super().__init__(name, canvas, x, y, guiEvent=guiEvent)
        self.key = key


# Default callback for key events.
def _key_handler(event):
    # Dead reckoning of key.
    if event.name == "key_press_event":
        event.canvas._key = event.key
    elif event.name == "key_release_event":
        event.canvas._key = None


# Default callback for mouse events.
def _mouse_handler(event):
    # Dead-reckoning of button and key.
    if event.name == "button_press_event":
        event.canvas._button = event.button
    elif event.name == "button_release_event":
        event.canvas._button = None
    elif event.name == "motion_notify_event" and event.button is None:
        event.button = event.canvas._button
    if event.key is None:
        event.key = event.canvas._key
    # Emit axes_enter/axes_leave.
    if event.name == "motion_notify_event":
        last_ref = LocationEvent._last_axes_ref
        last_axes = last_ref() if last_ref else None
        if last_axes != event.inaxes:
            if last_axes is not None:
                # Create a synthetic LocationEvent for the axes_leave_event.
                # Its inaxes attribute needs to be manually set (because the
                # cursor is actually *out* of that Axes at that point); this is
                # done with the internal _set_inaxes method which ensures that
                # the xdata and ydata attributes are also correct.
                try:
                    canvas = last_axes.get_figure(root=True).canvas
                    leave_event = LocationEvent(
                        "axes_leave_event", canvas,
                        event.x, event.y, event.guiEvent,
                        modifiers=event.modifiers)
                    leave_event._set_inaxes(last_axes)
                    canvas.callbacks.process("axes_leave_event", leave_event)
                except Exception:
                    pass  # The last canvas may already have been torn down.
            if event.inaxes is not None:
                event.canvas.callbacks.process("axes_enter_event", event)
        LocationEvent._last_axes_ref = (
            weakref.ref(event.inaxes) if event.inaxes else None)


def _get_renderer(figure, print_method=None):
    """
    Get the renderer that would be used to save a `.Figure`.

    If you need a renderer without any active draw methods use
    renderer._draw_disabled to temporary patch them out at your call site.
    """
    # This is implemented by triggering a draw, then immediately jumping out of
    # Figure.draw() by raising an exception.

    class Done(Exception):
        pass

    def _draw(renderer): raise Done(renderer)

    with cbook._setattr_cm(figure, draw=_draw), ExitStack() as stack:
        if print_method is None:
            fmt = figure.canvas.get_default_filetype()
            # Even for a canvas' default output type, a canvas switch may be
            # needed, e.g. for FigureCanvasBase.
            print_method = stack.enter_context(
                figure.canvas._switch_canvas_and_return_print_method(fmt))
        try:
            print_method(io.BytesIO())
        except Done as exc:
            renderer, = exc.args
            return renderer
        else:
            raise RuntimeError(f"{print_method} did not call Figure.draw, so "
                               f"no renderer is available")


def _no_output_draw(figure):
    # _no_output_draw was promoted to the figure level, but
    # keep this here in case someone was calling it...
    figure.draw_without_rendering()


def _is_non_interactive_terminal_ipython(ip):
    """
    Return whether we are in a terminal IPython, but non interactive.

    When in _terminal_ IPython, ip.parent will have and `interact` attribute,
    if this attribute is False we do not setup eventloop integration as the
    user will _not_ interact with IPython. In all other case (ZMQKernel, or is
    interactive), we do.
    """
    return (hasattr(ip, 'parent')
            and (ip.parent is not None)
            and getattr(ip.parent, 'interact', None) is False)


@contextmanager
def _allow_interrupt(prepare_notifier, handle_sigint):
    """
    A context manager that allows terminating a plot by sending a SIGINT.  It
    is necessary because the running backend prevents the Python interpreter
    from running and processing signals (i.e., to raise a KeyboardInterrupt).
    To solve this, one needs to somehow wake up the interpreter and make it
    close the plot window.  We do this by using the signal.set_wakeup_fd()
    function which organizes a write of the signal number into a socketpair.
    A backend-specific function, *prepare_notifier*, arranges to listen to
    the pair's read socket while the event loop is running.  (If it returns a
    notifier object, that object is kept alive while the context manager runs.)

    If SIGINT was indeed caught, after exiting the on_signal() function the
    interpreter reacts to the signal according to the handler function which
    had been set up by a signal.signal() call; here, we arrange to call the
    backend-specific *handle_sigint* function, passing the notifier object
    as returned by prepare_notifier().  Finally, we call the old SIGINT
    handler with the same arguments that were given to our custom handler.

    We do this only if the old handler for SIGINT was not None, which means
    that a non-python handler was installed, i.e. in Julia, and not SIG_IGN
    which means we should ignore the interrupts.

    Parameters
    ----------
    prepare_notifier : Callable[[socket.socket], object]
    handle_sigint : Callable[[object], object]
    """

    old_sigint_handler = signal.getsignal(signal.SIGINT)
    if old_sigint_handler in (None, signal.SIG_IGN, signal.SIG_DFL):
        yield
        return

    handler_args = None
    wsock, rsock = socket.socketpair()
    wsock.setblocking(False)
    rsock.setblocking(False)
    old_wakeup_fd = signal.set_wakeup_fd(wsock.fileno())
    notifier = prepare_notifier(rsock)

    def save_args_and_handle_sigint(*args):
        nonlocal handler_args, notifier
        handler_args = args
        handle_sigint(notifier)
        notifier = None

    signal.signal(signal.SIGINT, save_args_and_handle_sigint)
    try:
        yield
    finally:
        wsock.close()
        rsock.close()
        signal.set_wakeup_fd(old_wakeup_fd)
        signal.signal(signal.SIGINT, old_sigint_handler)
        if handler_args is not None:
            old_sigint_handler(*handler_args)


class FigureCanvasBase:
    """
    The canvas the figure renders into.

    Attributes
    ----------
    figure : `~matplotlib.figure.Figure`
        A high-level figure instance.
    """

    # Set to one of {"qt", "gtk3", "gtk4", "wx", "tk", "macosx"} if an
    # interactive framework is required, or None otherwise.
    required_interactive_framework = None

    # The manager class instantiated by new_manager.
    # (This is defined as a classproperty because the manager class is
    # currently defined *after* the canvas class, but one could also assign
    # ``FigureCanvasBase.manager_class = FigureManagerBase``
    # after defining both classes.)
    manager_class = _api.classproperty(lambda cls: FigureManagerBase)

    events = [
        'resize_event',
        'draw_event',
        'key_press_event',
        'key_release_event',
        'button_press_event',
        'button_release_event',
        'scroll_event',
        'motion_notify_event',
        'pick_event',
        'figure_enter_event',
        'figure_leave_event',
        'axes_enter_event',
        'axes_leave_event',
        'close_event'
    ]

    fixed_dpi = None

    filetypes = _default_filetypes

    @_api.classproperty
    def supports_blit(cls):
        """If this Canvas sub-class supports blitting."""
        return (hasattr(cls, "copy_from_bbox")
                and hasattr(cls, "restore_region"))

    def __init__(self, figure=None):
        from matplotlib.figure import Figure
        self._fix_ipython_backend2gui()
        self._is_idle_drawing = True
        self._is_saving = False
        if figure is None:
            figure = Figure()
        figure.set_canvas(self)
        self.figure = figure
        self.manager = None
        self.widgetlock = widgets.LockDraw()
        self._button = None  # the button pressed
        self._key = None  # the key pressed
        self.mouse_grabber = None  # the Axes currently grabbing mouse
        self.toolbar = None  # NavigationToolbar2 will set me
        self._is_idle_drawing = False
        # We don't want to scale up the figure DPI more than once.
        figure._original_dpi = figure.dpi
        self._device_pixel_ratio = 1
        super().__init__()  # Typically the GUI widget init (if any).

    callbacks = property(lambda self: self.figure._canvas_callbacks)
    button_pick_id = property(lambda self: self.figure._button_pick_id)
    scroll_pick_id = property(lambda self: self.figure._scroll_pick_id)

    @classmethod
    @functools.cache
    def _fix_ipython_backend2gui(cls):
        # Fix hard-coded module -> toolkit mapping in IPython (used for
        # `ipython --auto`).  This cannot be done at import time due to
        # ordering issues, so we do it when creating a canvas, and should only
        # be done once per class (hence the `cache`).

        # This function will not be needed when Python 3.12, the latest version
        # supported by IPython < 8.24, reaches end-of-life in late 2028.
        # At that time this function can be made a no-op and deprecated.
        mod_ipython = sys.modules.get("IPython")
        if mod_ipython is None or mod_ipython.version_info[:2] >= (8, 24):
            # Use of backend2gui is not needed for IPython >= 8.24 as the
            # functionality has been moved to Matplotlib.
            return

        import IPython
        ip = IPython.get_ipython()
        if not ip:
            return
        from IPython.core import pylabtools as pt
        if (not hasattr(pt, "backend2gui")
                or not hasattr(ip, "enable_matplotlib")):
            # In case we ever move the patch to IPython and remove these APIs,
            # don't break on our side.
            return
        backend2gui_rif = {
            "qt": "qt",
            "gtk3": "gtk3",
            "gtk4": "gtk4",
            "wx": "wx",
            "macosx": "osx",
        }.get(cls.required_interactive_framework)
        if backend2gui_rif:
            if _is_non_interactive_terminal_ipython(ip):
                ip.enable_gui(backend2gui_rif)

    @classmethod
    def new_manager(cls, figure, num):
        """
        Create a new figure manager for *figure*, using this canvas class.

        Notes
        -----
        This method should not be reimplemented in subclasses.  If
        custom manager creation logic is needed, please reimplement
        ``FigureManager.create_with_canvas``.
        """
        return cls.manager_class.create_with_canvas(cls, figure, num)

    @contextmanager
    def _idle_draw_cntx(self):
        self._is_idle_drawing = True
        try:
            yield
        finally:
            self._is_idle_drawing = False

    def is_saving(self):
        """
        Return whether the renderer is in the process of saving
        to a file, rather than rendering for an on-screen buffer.
        """
        return self._is_saving

    def blit(self, bbox=None):
        """Blit the canvas in bbox (default entire canvas)."""

    def inaxes(self, xy):
        """
        Return the topmost visible `~.axes.Axes` containing the point *xy*.

        Parameters
        ----------
        xy : (float, float)
            (x, y) pixel positions from left/bottom of the canvas.

        Returns
        -------
        `~matplotlib.axes.Axes` or None
            The topmost visible Axes containing the point, or None if there
            is no Axes at the point.
        """
        axes_list = [a for a in self.figure.get_axes()
                     if a.patch.contains_point(xy) and a.get_visible()]
        if axes_list:
            axes = cbook._topmost_artist(axes_list)
        else:
            axes = None

        return axes

    def grab_mouse(self, ax):
        """
        Set the child `~.axes.Axes` which is grabbing the mouse events.

        Usually called by the widgets themselves. It is an error to call this
        if the mouse is already grabbed by another Axes.
        """
        if self.mouse_grabber not in (None, ax):
            raise RuntimeError("Another Axes already grabs mouse input")
        self.mouse_grabber = ax

    def release_mouse(self, ax):
        """
        Release the mouse grab held by the `~.axes.Axes` *ax*.

        Usually called by the widgets. It is ok to call this even if *ax*
        doesn't have the mouse grab currently.
        """
        if self.mouse_grabber is ax:
            self.mouse_grabber = None

    def set_cursor(self, cursor):
        """
        Set the current cursor.

        This may have no effect if the backend does not display anything.

        If required by the backend, this method should trigger an update in
        the backend event loop after the cursor is set, as this method may be
        called e.g. before a long-running task during which the GUI is not
        updated.

        Parameters
        ----------
        cursor : `.Cursors`
            The cursor to display over the canvas. Note: some backends may
            change the cursor for the entire window.
        """

    def draw(self, *args, **kwargs):
        """
        Render the `.Figure`.

        This method must walk the artist tree, even if no output is produced,
        because it triggers deferred work that users may want to access
        before saving output to disk. For example computing limits,
        auto-limits, and tick values.
        """

    def draw_idle(self, *args, **kwargs):
        """
        Request a widget redraw once control returns to the GUI event loop.

        Even if multiple calls to `draw_idle` occur before control returns
        to the GUI event loop, the figure will only be rendered once.

        Notes
        -----
        Backends may choose to override the method and implement their own
        strategy to prevent multiple renderings.

        """
        if not self._is_idle_drawing:
            with self._idle_draw_cntx():
                self.draw(*args, **kwargs)

    @property
    def device_pixel_ratio(self):
        """
        The ratio of physical to logical pixels used for the canvas on screen.

        By default, this is 1, meaning physical and logical pixels are the same
        size. Subclasses that support High DPI screens may set this property to
        indicate that said ratio is different. All Matplotlib interaction,
        unless working directly with the canvas, remains in logical pixels.

        """
        return self._device_pixel_ratio

    def _set_device_pixel_ratio(self, ratio):
        """
        Set the ratio of physical to logical pixels used for the canvas.

        Subclasses that support High DPI screens can set this property to
        indicate that said ratio is different. The canvas itself will be
        created at the physical size, while the client side will use the
        logical size. Thus the DPI of the Figure will change to be scaled by
        this ratio. Implementations that support High DPI screens should use
        physical pixels for events so that transforms back to Axes space are
        correct.

        By default, this is 1, meaning physical and logical pixels are the same
        size.

        Parameters
        ----------
        ratio : float
            The ratio of logical to physical pixels used for the canvas.

        Returns
        -------
        bool
            Whether the ratio has changed. Backends may interpret this as a
            signal to resize the window, repaint the canvas, or change any
            other relevant properties.
        """
        if self._device_pixel_ratio == ratio:
            return False
        # In cases with mixed resolution displays, we need to be careful if the
        # device pixel ratio changes - in this case we need to resize the
        # canvas accordingly. Some backends provide events that indicate a
        # change in DPI, but those that don't will update this before drawing.
        dpi = ratio * self.figure._original_dpi
        self.figure._set_dpi(dpi, forward=False)
        self._device_pixel_ratio = ratio
        return True

    def get_width_height(self, *, physical=False):
        """
        Return the figure width and height in integral points or pixels.

        When the figure is used on High DPI screens (and the backend supports
        it), the truncation to integers occurs after scaling by the device
        pixel ratio.

        Parameters
        ----------
        physical : bool, default: False
            Whether to return true physical pixels or logical pixels. Physical
            pixels may be used by backends that support HiDPI, but still
            configure the canvas using its actual size.

        Returns
        -------
        width, height : int
            The size of the figure, in points or pixels, depending on the
            backend.
        """
        return tuple(int(size / (1 if physical else self.device_pixel_ratio))
                     for size in self.figure.bbox.max)

    @classmethod
    def get_supported_filetypes(cls):
        """Return dict of savefig file formats supported by this backend."""
        return cls.filetypes

    @classmethod
    def get_supported_filetypes_grouped(cls):
        """
        Return a dict of savefig file formats supported by this backend,
        where the keys are a file type name, such as 'Joint Photographic
        Experts Group', and the values are a list of filename extensions used
        for that filetype, such as ['jpg', 'jpeg'].
        """
        groupings = {}
        for ext, name in cls.filetypes.items():
            groupings.setdefault(name, []).append(ext)
            groupings[name].sort()
        return groupings

    @contextmanager
    def _switch_canvas_and_return_print_method(self, fmt, backend=None):
        """
        Context manager temporarily setting the canvas for saving the figure::

            with (canvas._switch_canvas_and_return_print_method(fmt, backend)
                  as print_method):
                # ``print_method`` is a suitable ``print_{fmt}`` method, and
                # the figure's canvas is temporarily switched to the method's
                # canvas within the with... block.  ``print_method`` is also
                # wrapped to suppress extra kwargs passed by ``print_figure``.

        Parameters
        ----------
        fmt : str
            If *backend* is None, then determine a suitable canvas class for
            saving to format *fmt* -- either the current canvas class, if it
            supports *fmt*, or whatever `get_registered_canvas_class` returns;
            switch the figure canvas to that canvas class.
        backend : str or None, default: None
            If not None, switch the figure canvas to the ``FigureCanvas`` class
            of the given backend.
        """
        canvas = None
        if backend is not None:
            # Return a specific canvas class, if requested.
            from .backends.registry import backend_registry
            canvas_class = backend_registry.load_backend_module(backend).FigureCanvas
            if not hasattr(canvas_class, f"print_{fmt}"):
                raise ValueError(
                    f"The {backend!r} backend does not support {fmt} output")
            canvas = canvas_class(self.figure)
        elif hasattr(self, f"print_{fmt}"):
            # Return the current canvas if it supports the requested format.
            canvas = self
        else:
            # Return a default canvas for the requested format, if it exists.
            canvas_class = get_registered_canvas_class(fmt)
            if canvas_class is None:
                raise ValueError(
                    "Format {!r} is not supported (supported formats: {})".format(
                        fmt, ", ".join(sorted(self.get_supported_filetypes()))))
            canvas = canvas_class(self.figure)
        canvas._is_saving = self._is_saving
        meth = getattr(canvas, f"print_{fmt}")
        mod = (meth.func.__module__
               if hasattr(meth, "func")  # partialmethod, e.g. backend_wx.
               else meth.__module__)
        if mod.startswith(("matplotlib.", "mpl_toolkits.")):
            optional_kws = {  # Passed by print_figure for other renderers.
                "dpi", "facecolor", "edgecolor", "orientation",
                "bbox_inches_restore"}
            skip = optional_kws - {*inspect.signature(meth).parameters}
            print_method = functools.wraps(meth)(lambda *args, **kwargs: meth(
                *args, **{k: v for k, v in kwargs.items() if k not in skip}))
        else:  # Let third-parties do as they see fit.
            print_method = meth
        try:
            yield print_method
        finally:
            self.figure.canvas = self

    def print_figure(
            self, filename, dpi=None, facecolor=None, edgecolor=None,
            orientation='portrait', format=None, *,
            bbox_inches=None, pad_inches=None, bbox_extra_artists=None,
            backend=None, **kwargs):
        """
        Render the figure to hardcopy. Set the figure patch face and edge
        colors.  This is useful because some of the GUIs have a gray figure
        face color background and you'll probably want to override this on
        hardcopy.

        Parameters
        ----------
        filename : str or path-like or file-like
            The file where the figure is saved.

        dpi : float, default: :rc:`savefig.dpi`
            The dots per inch to save the figure in.

        facecolor : :mpltype:`color` or 'auto', default: :rc:`savefig.facecolor`
            The facecolor of the figure.  If 'auto', use the current figure
            facecolor.

        edgecolor : :mpltype:`color` or 'auto', default: :rc:`savefig.edgecolor`
            The edgecolor of the figure.  If 'auto', use the current figure
            edgecolor.

        orientation : {'landscape', 'portrait'}, default: 'portrait'
            Only currently applies to PostScript printing.

        format : str, optional
            Force a specific file format. If not given, the format is inferred
            from the *filename* extension, and if that fails from
            :rc:`savefig.format`.

        bbox_inches : 'tight' or `.Bbox`, default: :rc:`savefig.bbox`
            Bounding box in inches: only the given portion of the figure is
            saved.  If 'tight', try to figure out the tight bbox of the figure.

        pad_inches : float or 'layout', default: :rc:`savefig.pad_inches`
            Amount of padding in inches around the figure when bbox_inches is
            'tight'. If 'layout' use the padding from the constrained or
            compressed layout engine; ignored if one of those engines is not in
            use.

        bbox_extra_artists : list of `~matplotlib.artist.Artist`, optional
            A list of extra artists that will be considered when the
            tight bbox is calculated.

        backend : str, optional
            Use a non-default backend to render the file, e.g. to render a
            png file with the "cairo" backend rather than the default "agg",
            or a pdf file with the "pgf" backend rather than the default
            "pdf".  Note that the default backend is normally sufficient.  See
            :ref:`the-builtin-backends` for a list of valid backends for each
            file format.  Custom backends can be referenced as "module://...".
        """
        if format is None:
            # get format from filename, or from backend's default filetype
            if isinstance(filename, os.PathLike):
                filename = os.fspath(filename)
            if isinstance(filename, str):
                format = os.path.splitext(filename)[1][1:]
            if format is None or format == '':
                format = self.get_default_filetype()
                if isinstance(filename, str):
                    filename = filename.rstrip('.') + '.' + format
        format = format.lower()

        if dpi is None:
            dpi = rcParams['savefig.dpi']
        if dpi == 'figure':
            dpi = getattr(self.figure, '_original_dpi', self.figure.dpi)

        # Remove the figure manager, if any, to avoid resizing the GUI widget.
        with (cbook._setattr_cm(self, manager=None),
              self._switch_canvas_and_return_print_method(format, backend)
                 as print_method,
              cbook._setattr_cm(self.figure, dpi=dpi),
              cbook._setattr_cm(self.figure.canvas, _device_pixel_ratio=1),
              cbook._setattr_cm(self.figure.canvas, _is_saving=True),
              ExitStack() as stack):

            for prop in ["facecolor", "edgecolor"]:
                color = locals()[prop]
                if color is None:
                    color = rcParams[f"savefig.{prop}"]
                if not cbook._str_equal(color, "auto"):
                    stack.enter_context(self.figure._cm_set(**{prop: color}))

            if bbox_inches is None:
                bbox_inches = rcParams['savefig.bbox']

            layout_engine = self.figure.get_layout_engine()
            if layout_engine is not None or bbox_inches == "tight":
                # we need to trigger a draw before printing to make sure
                # CL works.  "tight" also needs a draw to get the right
                # locations:
                renderer = _get_renderer(
                    self.figure,
                    functools.partial(
                        print_method, orientation=orientation)
                )
                # we do this instead of `self.figure.draw_without_rendering`
                # so that we can inject the orientation
                with getattr(renderer, "_draw_disabled", nullcontext)():
                    self.figure.draw(renderer)
            if bbox_inches:
                if bbox_inches == "tight":
                    bbox_inches = self.figure.get_tightbbox(
                        renderer, bbox_extra_artists=bbox_extra_artists)
                    if (isinstance(layout_engine, ConstrainedLayoutEngine) and
                            pad_inches == "layout"):
                        h_pad = layout_engine.get()["h_pad"]
                        w_pad = layout_engine.get()["w_pad"]
                    else:
                        if pad_inches in [None, "layout"]:
                            pad_inches = rcParams['savefig.pad_inches']
                        h_pad = w_pad = pad_inches
                    bbox_inches = bbox_inches.padded(w_pad, h_pad)

                # call adjust_bbox to save only the given area
                restore_bbox = _tight_bbox.adjust_bbox(
                    self.figure, bbox_inches, self.figure.canvas.fixed_dpi)

                _bbox_inches_restore = (bbox_inches, restore_bbox)
            else:
                _bbox_inches_restore = None

            # we have already done layout above, so turn it off:
            stack.enter_context(self.figure._cm_set(layout_engine='none'))
            try:
                # _get_renderer may change the figure dpi (as vector formats
                # force the figure dpi to 72), so we need to set it again here.
                with cbook._setattr_cm(self.figure, dpi=dpi):
                    result = print_method(
                        filename,
                        facecolor=facecolor,
                        edgecolor=edgecolor,
                        orientation=orientation,
                        bbox_inches_restore=_bbox_inches_restore,
                        **kwargs)
            finally:
                if bbox_inches and restore_bbox:
                    restore_bbox()

            return result

    @classmethod
    def get_default_filetype(cls):
        """
        Return the default savefig file format as specified in
        :rc:`savefig.format`.

        The returned string does not include a period. This method is
        overridden in backends that only support a single file type.
        """
        return rcParams['savefig.format']

    def get_default_filename(self):
        """
        Return a suitable default filename, including the extension.
        """
        default_basename = (
            self.manager.get_window_title()
            if self.manager is not None
            else ''
        )
        default_basename = default_basename or 'image'
        # Characters to be avoided in a NT path:
        # https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247(v=vs.85).aspx#naming_conventions
        # plus ' '
        removed_chars = '<>:"/\\|?*\0 '
        default_basename = default_basename.translate(
            {ord(c): "_" for c in removed_chars})
        default_filetype = self.get_default_filetype()
        return f'{default_basename}.{default_filetype}'

    def mpl_connect(self, s, func):
        """
        Bind function *func* to event *s*.

        Parameters
        ----------
        s : str
            One of the following events ids:

            - 'button_press_event'
            - 'button_release_event'
            - 'draw_event'
            - 'key_press_event'
            - 'key_release_event'
            - 'motion_notify_event'
            - 'pick_event'
            - 'resize_event'
            - 'scroll_event'
            - 'figure_enter_event',
            - 'figure_leave_event',
            - 'axes_enter_event',
            - 'axes_leave_event'
            - 'close_event'.

        func : callable
            The callback function to be executed, which must have the
            signature::

                def func(event: Event) -> Any

            For the location events (button and key press/release), if the
            mouse is over the Axes, the ``inaxes`` attribute of the event will
            be set to the `~matplotlib.axes.Axes` the event occurs is over, and
            additionally, the variables ``xdata`` and ``ydata`` attributes will
            be set to the mouse location in data coordinates.  See `.KeyEvent`
            and `.MouseEvent` for more info.

            .. note::

                If func is a method, this only stores a weak reference to the
                method. Thus, the figure does not influence the lifetime of
                the associated object. Usually, you want to make sure that the
                object is kept alive throughout the lifetime of the figure by
                holding a reference to it.

        Returns
        -------
        cid
            A connection id that can be used with
            `.FigureCanvasBase.mpl_disconnect`.

        Examples
        --------
        ::

            def on_press(event):
                print('you pressed', event.button, event.xdata, event.ydata)

            cid = canvas.mpl_connect('button_press_event', on_press)
        """

        return self.callbacks.connect(s, func)

    def mpl_disconnect(self, cid):
        """
        Disconnect the callback with id *cid*.

        Examples
        --------
        ::

            cid = canvas.mpl_connect('button_press_event', on_press)
            # ... later
            canvas.mpl_disconnect(cid)
        """
        self.callbacks.disconnect(cid)

    # Internal subclasses can override _timer_cls instead of new_timer, though
    # this is not a public API for third-party subclasses.
    _timer_cls = TimerBase

    def new_timer(self, interval=None, callbacks=None):
        """
        Create a new backend-specific subclass of `.Timer`.

        This is useful for getting periodic events through the backend's native
        event loop.  Implemented only for backends with GUIs.

        Parameters
        ----------
        interval : int
            Timer interval in milliseconds.

        callbacks : list[tuple[callable, tuple, dict]]
            Sequence of (func, args, kwargs) where ``func(*args, **kwargs)``
            will be executed by the timer every *interval*.

            Callbacks which return ``False`` or ``0`` will be removed from the
            timer.

        Examples
        --------
        >>> timer = fig.canvas.new_timer(callbacks=[(f1, (1,), {'a': 3})])
        """
        return self._timer_cls(interval=interval, callbacks=callbacks)

    def flush_events(self):
        """
        Flush the GUI events for the figure.

        Interactive backends need to reimplement this method.
        """

    def start_event_loop(self, timeout=0):
        """
        Start a blocking event loop.

        Such an event loop is used by interactive functions, such as
        `~.Figure.ginput` and `~.Figure.waitforbuttonpress`, to wait for
        events.

        The event loop blocks until a callback function triggers
        `stop_event_loop`, or *timeout* is reached.

        If *timeout* is 0 or negative, never timeout.

        Only interactive backends need to reimplement this method and it relies
        on `flush_events` being properly implemented.

        Interactive backends should implement this in a more native way.
        """
        if timeout <= 0:
            timeout = np.inf
        timestep = 0.01
        counter = 0
        self._looping = True
        while self._looping and counter * timestep < timeout:
            self.flush_events()
            time.sleep(timestep)
            counter += 1

    def stop_event_loop(self):
        """
        Stop the current blocking event loop.

        Interactive backends need to reimplement this to match
        `start_event_loop`
        """
        self._looping = False


def key_press_handler(event, canvas=None, toolbar=None):
    """
    Implement the default Matplotlib key bindings for the canvas and toolbar
    described at :ref:`key-event-handling`.

    Parameters
    ----------
    event : `KeyEvent`
        A key press/release event.
    canvas : `FigureCanvasBase`, default: ``event.canvas``
        The backend-specific canvas instance.  This parameter is kept for
        back-compatibility, but, if set, should always be equal to
        ``event.canvas``.
    toolbar : `NavigationToolbar2`, default: ``event.canvas.toolbar``
        The navigation cursor toolbar.  This parameter is kept for
        back-compatibility, but, if set, should always be equal to
        ``event.canvas.toolbar``.
    """
    if event.key is None:
        return
    if canvas is None:
        canvas = event.canvas
    if toolbar is None:
        toolbar = canvas.toolbar

    # toggle fullscreen mode (default key 'f', 'ctrl + f')
    if event.key in rcParams['keymap.fullscreen']:
        try:
            canvas.manager.full_screen_toggle()
        except AttributeError:
            pass

    # quit the figure (default key 'ctrl+w')
    if event.key in rcParams['keymap.quit']:
        Gcf.destroy_fig(canvas.figure)
    if event.key in rcParams['keymap.quit_all']:
        Gcf.destroy_all()

    if toolbar is not None:
        # home or reset mnemonic  (default key 'h', 'home' and 'r')
        if event.key in rcParams['keymap.home']:
            toolbar.home()
        # forward / backward keys to enable left handed quick navigation
        # (default key for backward: 'left', 'backspace' and 'c')
        elif event.key in rcParams['keymap.back']:
            toolbar.back()
        # (default key for forward: 'right' and 'v')
        elif event.key in rcParams['keymap.forward']:
            toolbar.forward()
        # pan mnemonic (default key 'p')
        elif event.key in rcParams['keymap.pan']:
            toolbar.pan()
            toolbar._update_cursor(event)
        # zoom mnemonic (default key 'o')
        elif event.key in rcParams['keymap.zoom']:
            toolbar.zoom()
            toolbar._update_cursor(event)
        # saving current figure (default key 's')
        elif event.key in rcParams['keymap.save']:
            toolbar.save_figure()

    if event.inaxes is None:
        return

    # these bindings require the mouse to be over an Axes to trigger
    def _get_uniform_gridstate(ticks):
        # Return True/False if all grid lines are on or off, None if they are
        # not all in the same state.
        return (True if all(tick.gridline.get_visible() for tick in ticks) else
                False if not any(tick.gridline.get_visible() for tick in ticks) else
                None)

    ax = event.inaxes
    # toggle major grids in current Axes (default key 'g')
    # Both here and below (for 'G'), we do nothing if *any* grid (major or
    # minor, x or y) is not in a uniform state, to avoid messing up user
    # customization.
    if (event.key in rcParams['keymap.grid']
            # Exclude minor grids not in a uniform state.
            and None not in [_get_uniform_gridstate(ax.xaxis.minorTicks),
                             _get_uniform_gridstate(ax.yaxis.minorTicks)]):
        x_state = _get_uniform_gridstate(ax.xaxis.majorTicks)
        y_state = _get_uniform_gridstate(ax.yaxis.majorTicks)
        cycle = [(False, False), (True, False), (True, True), (False, True)]
        try:
            x_state, y_state = (
                cycle[(cycle.index((x_state, y_state)) + 1) % len(cycle)])
        except ValueError:
            # Exclude major grids not in a uniform state.
            pass
        else:
            # If turning major grids off, also turn minor grids off.
            ax.grid(x_state, which="major" if x_state else "both", axis="x")
            ax.grid(y_state, which="major" if y_state else "both", axis="y")
            canvas.draw_idle()
    # toggle major and minor grids in current Axes (default key 'G')
    if (event.key in rcParams['keymap.grid_minor']
            # Exclude major grids not in a uniform state.
            and None not in [_get_uniform_gridstate(ax.xaxis.majorTicks),
                             _get_uniform_gridstate(ax.yaxis.majorTicks)]):
        x_state = _get_uniform_gridstate(ax.xaxis.minorTicks)
        y_state = _get_uniform_gridstate(ax.yaxis.minorTicks)
        cycle = [(False, False), (True, False), (True, True), (False, True)]
        try:
            x_state, y_state = (
                cycle[(cycle.index((x_state, y_state)) + 1) % len(cycle)])
        except ValueError:
            # Exclude minor grids not in a uniform state.
            pass
        else:
            ax.grid(x_state, which="both", axis="x")
            ax.grid(y_state, which="both", axis="y")
            canvas.draw_idle()
    # toggle scaling of y-axes between 'log and 'linear' (default key 'l')
    elif event.key in rcParams['keymap.yscale']:
        scale = ax.get_yscale()
        if scale == 'log':
            ax.set_yscale('linear')
            ax.get_figure(root=True).canvas.draw_idle()
        elif scale == 'linear':
            try:
                ax.set_yscale('log')
            except ValueError as exc:
                _log.warning(str(exc))
                ax.set_yscale('linear')
            ax.get_figure(root=True).canvas.draw_idle()
    # toggle scaling of x-axes between 'log and 'linear' (default key 'k')
    elif event.key in rcParams['keymap.xscale']:
        scalex = ax.get_xscale()
        if scalex == 'log':
            ax.set_xscale('linear')
            ax.get_figure(root=True).canvas.draw_idle()
        elif scalex == 'linear':
            try:
                ax.set_xscale('log')
            except ValueError as exc:
                _log.warning(str(exc))
                ax.set_xscale('linear')
            ax.get_figure(root=True).canvas.draw_idle()


def button_press_handler(event, canvas=None, toolbar=None):
    """
    The default Matplotlib button actions for extra mouse buttons.

    Parameters are as for `key_press_handler`, except that *event* is a
    `MouseEvent`.
    """
    if canvas is None:
        canvas = event.canvas
    if toolbar is None:
        toolbar = canvas.toolbar
    if toolbar is not None:
        button_name = str(MouseButton(event.button))
        if button_name in rcParams['keymap.back']:
            toolbar.back()
        elif button_name in rcParams['keymap.forward']:
            toolbar.forward()


class NonGuiException(Exception):
    """Raised when trying show a figure in a non-GUI backend."""
    pass


class FigureManagerBase:
    """
    A backend-independent abstraction of a figure container and controller.

    The figure manager is used by pyplot to interact with the window in a
    backend-independent way. It's an adapter for the real (GUI) framework that
    represents the visual figure on screen.

    The figure manager is connected to a specific canvas instance, which in turn
    is connected to a specific figure instance. To access a figure manager for
    a given figure in user code, you typically use ``fig.canvas.manager``.

    GUI backends derive from this class to translate common operations such
    as *show* or *resize* to the GUI-specific code. Non-GUI backends do not
    support these operations and can just use the base class.

    This following basic operations are accessible:

    **Window operations**

    - `~.FigureManagerBase.show`
    - `~.FigureManagerBase.destroy`
    - `~.FigureManagerBase.full_screen_toggle`
    - `~.FigureManagerBase.resize`
    - `~.FigureManagerBase.get_window_title`
    - `~.FigureManagerBase.set_window_title`

    **Key and mouse button press handling**

    The figure manager sets up default key and mouse button press handling by
    hooking up the `.key_press_handler` to the matplotlib event system. This
    ensures the same shortcuts and mouse actions across backends.

    **Other operations**

    Subclasses will have additional attributes and functions to access
    additional functionality. This is of course backend-specific. For example,
    most GUI backends have ``window`` and ``toolbar`` attributes that give
    access to the native GUI widgets of the respective framework.

    Attributes
    ----------
    canvas : `FigureCanvasBase`
        The backend-specific canvas instance.

    num : int or str
        The figure number.

    key_press_handler_id : int
        The default key handler cid, when using the toolmanager.
        To disable the default key press handling use::

            figure.canvas.mpl_disconnect(
                figure.canvas.manager.key_press_handler_id)

    button_press_handler_id : int
        The default mouse button handler cid, when using the toolmanager.
        To disable the default button press handling use::

            figure.canvas.mpl_disconnect(
                figure.canvas.manager.button_press_handler_id)
    """

    _toolbar2_class = None
    _toolmanager_toolbar_class = None

    def __init__(self, canvas, num):
        self.canvas = canvas
        canvas.manager = self  # store a pointer to parent
        self.num = num
        self.set_window_title(f"Figure {num:d}")

        self.key_press_handler_id = None
        self.button_press_handler_id = None
        if rcParams['toolbar'] != 'toolmanager':
            self.key_press_handler_id = self.canvas.mpl_connect(
                'key_press_event', key_press_handler)
            self.button_press_handler_id = self.canvas.mpl_connect(
                'button_press_event', button_press_handler)

        self.toolmanager = (ToolManager(canvas.figure)
                            if mpl.rcParams['toolbar'] == 'toolmanager'
                            else None)
        if (mpl.rcParams["toolbar"] == "toolbar2"
                and self._toolbar2_class):
            self.toolbar = self._toolbar2_class(self.canvas)
        elif (mpl.rcParams["toolbar"] == "toolmanager"
                and self._toolmanager_toolbar_class):
            self.toolbar = self._toolmanager_toolbar_class(self.toolmanager)
        else:
            self.toolbar = None

        if self.toolmanager:
            tools.add_tools_to_manager(self.toolmanager)
            if self.toolbar:
                tools.add_tools_to_container(self.toolbar)

        @self.canvas.figure.add_axobserver
        def notify_axes_change(fig):
            # Called whenever the current Axes is changed.
            if self.toolmanager is None and self.toolbar is not None:
                self.toolbar.update()

    @classmethod
    def create_with_canvas(cls, canvas_class, figure, num):
        """
        Create a manager for a given *figure* using a specific *canvas_class*.

        Backends should override this method if they have specific needs for
        setting up the canvas or the manager.
        """
        return cls(canvas_class(figure), num)

    @classmethod
    def start_main_loop(cls):
        """
        Start the main event loop.

        This method is called by `.FigureManagerBase.pyplot_show`, which is the
        implementation of `.pyplot.show`.  To customize the behavior of
        `.pyplot.show`, interactive backends should usually override
        `~.FigureManagerBase.start_main_loop`; if more customized logic is
        necessary, `~.FigureManagerBase.pyplot_show` can also be overridden.
        """

    @classmethod
    def pyplot_show(cls, *, block=None):
        """
        Show all figures.  This method is the implementation of `.pyplot.show`.

        To customize the behavior of `.pyplot.show`, interactive backends
        should usually override `~.FigureManagerBase.start_main_loop`; if more
        customized logic is necessary, `~.FigureManagerBase.pyplot_show` can
        also be overridden.

        Parameters
        ----------
        block : bool, optional
            Whether to block by calling ``start_main_loop``.  The default,
            None, means to block if we are neither in IPython's ``%pylab`` mode
            nor in ``interactive`` mode.
        """
        managers = Gcf.get_all_fig_managers()
        if not managers:
            return
        for manager in managers:
            try:
                manager.show()  # Emits a warning for non-interactive backend.
            except NonGuiException as exc:
                _api.warn_external(str(exc))
        if block is None:
            # Hack: Are we in IPython's %pylab mode?  In pylab mode, IPython
            # (>= 0.10) tacks a _needmain attribute onto pyplot.show (always
            # set to False).
            pyplot_show = getattr(sys.modules.get("matplotlib.pyplot"), "show", None)
            ipython_pylab = hasattr(pyplot_show, "_needmain")
            block = not ipython_pylab and not is_interactive()
        if block:
            cls.start_main_loop()

    def show(self):
        """
        For GUI backends, show the figure window and redraw.
        For non-GUI backends, raise an exception, unless running headless (i.e.
        on Linux with an unset DISPLAY); this exception is converted to a
        warning in `.Figure.show`.
        """
        # This should be overridden in GUI backends.
        if sys.platform == "linux" and not os.environ.get("DISPLAY"):
            # We cannot check _get_running_interactive_framework() ==
            # "headless" because that would also suppress the warning when
            # $DISPLAY exists but is invalid, which is more likely an error and
            # thus warrants a warning.
            return
        raise NonGuiException(
            f"{type(self.canvas).__name__} is non-interactive, and thus cannot be "
            f"shown")

    def destroy(self):
        pass

    def full_screen_toggle(self):
        pass

    def resize(self, w, h):
        """For GUI backends, resize the window (in physical pixels)."""

    def get_window_title(self):
        """Return the title text of the window containing the figure."""
        return self._window_title

    def set_window_title(self, title):
        """
        Set the title text of the window containing the figure.

        Examples
        --------
        >>> fig = plt.figure()
        >>> fig.canvas.manager.set_window_title('My figure')
        """
        # This attribute is not defined in __init__ (but __init__ calls this
        # setter), as derived classes (real GUI managers) will store this
        # information directly on the widget; only the base (non-GUI) manager
        # class needs a specific attribute for it (so that filename escaping
        # can be checked in the test suite).
        self._window_title = title


cursors = tools.cursors


class _Mode(str, Enum):
    NONE = ""
    PAN = "pan/zoom"
    ZOOM = "zoom rect"

    def __str__(self):
        return self.value

    @property
    def _navigate_mode(self):
        return self.name if self is not _Mode.NONE else None


class NavigationToolbar2:
    """
    Base class for the navigation cursor, version 2.

    Backends must implement a canvas that handles connections for
    'button_press_event' and 'button_release_event'.  See
    :meth:`FigureCanvasBase.mpl_connect` for more information.

    They must also define

    :meth:`save_figure`
        Save the current figure.

    :meth:`draw_rubberband` (optional)
        Draw the zoom to rect "rubberband" rectangle.

    :meth:`set_message` (optional)
        Display message.

    :meth:`set_history_buttons` (optional)
        You can change the history back / forward buttons to indicate disabled / enabled
        state.

    and override ``__init__`` to set up the toolbar -- without forgetting to
    call the base-class init.  Typically, ``__init__`` needs to set up toolbar
    buttons connected to the `home`, `back`, `forward`, `pan`, `zoom`, and
    `save_figure` methods and using standard icons in the "images" subdirectory
    of the data path.

    That's it, we'll do the rest!
    """

    # list of toolitems to add to the toolbar, format is:
    # (
    #   text, # the text of the button (often not visible to users)
    #   tooltip_text, # the tooltip shown on hover (where possible)
    #   image_file, # name of the image for the button (without the extension)
    #   name_of_method, # name of the method in NavigationToolbar2 to call
    # )
    toolitems = (
        ('Home', 'Reset original view', 'home', 'home'),
        ('Back', 'Back to previous view', 'back', 'back'),
        ('Forward', 'Forward to next view', 'forward', 'forward'),
        (None, None, None, None),
        ('Pan',
         'Left button pans, Right button zooms\n'
         'x/y fixes axis, CTRL fixes aspect',
         'move', 'pan'),
        ('Zoom', 'Zoom to rectangle\nx/y fixes axis', 'zoom_to_rect', 'zoom'),
        ('Subplots', 'Configure subplots', 'subplots', 'configure_subplots'),
        (None, None, None, None),
        ('Save', 'Save the figure', 'filesave', 'save_figure'),
      )

    UNKNOWN_SAVED_STATUS = object()

    def __init__(self, canvas):
        self.canvas = canvas
        canvas.toolbar = self
        self._nav_stack = cbook._Stack()
        # This cursor will be set after the initial draw.
        self._last_cursor = tools.Cursors.POINTER

        self._id_press = self.canvas.mpl_connect(
            'button_press_event', self._zoom_pan_handler)
        self._id_release = self.canvas.mpl_connect(
            'button_release_event', self._zoom_pan_handler)
        self._id_drag = self.canvas.mpl_connect(
            'motion_notify_event', self.mouse_move)
        self._pan_info = None
        self._zoom_info = None

        self.mode = _Mode.NONE  # a mode string for the status bar
        self.set_history_buttons()

    def set_message(self, s):
        """Display a message on toolbar or in status bar."""

    def draw_rubberband(self, event, x0, y0, x1, y1):
        """
        Draw a rectangle rubberband to indicate zoom limits.

        Note that it is not guaranteed that ``x0 <= x1`` and ``y0 <= y1``.
        """

    def remove_rubberband(self):
        """Remove the rubberband."""

    def home(self, *args):
        """
        Restore the original view.

        For convenience of being directly connected as a GUI callback, which
        often get passed additional parameters, this method accepts arbitrary
        parameters, but does not use them.
        """
        self._nav_stack.home()
        self.set_history_buttons()
        self._update_view()

    def back(self, *args):
        """
        Move back up the view lim stack.

        For convenience of being directly connected as a GUI callback, which
        often get passed additional parameters, this method accepts arbitrary
        parameters, but does not use them.
        """
        self._nav_stack.back()
        self.set_history_buttons()
        self._update_view()

    def forward(self, *args):
        """
        Move forward in the view lim stack.

        For convenience of being directly connected as a GUI callback, which
        often get passed additional parameters, this method accepts arbitrary
        parameters, but does not use them.
        """
        self._nav_stack.forward()
        self.set_history_buttons()
        self._update_view()

    def _update_cursor(self, event):
        """
        Update the cursor after a mouse move event or a tool (de)activation.
        """
        if self.mode and event.inaxes and event.inaxes.get_navigate():
            if (self.mode == _Mode.ZOOM
                    and self._last_cursor != tools.Cursors.SELECT_REGION):
                self.canvas.set_cursor(tools.Cursors.SELECT_REGION)
                self._last_cursor = tools.Cursors.SELECT_REGION
            elif (self.mode == _Mode.PAN
                  and self._last_cursor != tools.Cursors.MOVE):
                self.canvas.set_cursor(tools.Cursors.MOVE)
                self._last_cursor = tools.Cursors.MOVE
        elif self._last_cursor != tools.Cursors.POINTER:
            self.canvas.set_cursor(tools.Cursors.POINTER)
            self._last_cursor = tools.Cursors.POINTER

    @contextmanager
    def _wait_cursor_for_draw_cm(self):
        """
        Set the cursor to a wait cursor when drawing the canvas.

        In order to avoid constantly changing the cursor when the canvas
        changes frequently, do nothing if this context was triggered during the
        last second.  (Optimally we'd prefer only setting the wait cursor if
        the *current* draw takes too long, but the current draw blocks the GUI
        thread).
        """
        self._draw_time, last_draw_time = (
            time.time(), getattr(self, "_draw_time", -np.inf))
        if self._draw_time - last_draw_time > 1:
            try:
                self.canvas.set_cursor(tools.Cursors.WAIT)
                yield
            finally:
                self.canvas.set_cursor(self._last_cursor)
        else:
            yield

    @staticmethod
    def _mouse_event_to_message(event):
        if event.inaxes and event.inaxes.get_navigate():
            try:
                s = event.inaxes.format_coord(event.xdata, event.ydata)
            except (ValueError, OverflowError):
                pass
            else:
                s = s.rstrip()
                artists = [a for a in event.inaxes._mouseover_set
                           if a.contains(event)[0] and a.get_visible()]
                if artists:
                    a = cbook._topmost_artist(artists)
                    if a is not event.inaxes.patch:
                        data = a.get_cursor_data(event)
                        if data is not None:
                            data_str = a.format_cursor_data(data).rstrip()
                            if data_str:
                                s = s + '\n' + data_str
                return s
        return ""

    def mouse_move(self, event):
        self._update_cursor(event)
        self.set_message(self._mouse_event_to_message(event))

    def _zoom_pan_handler(self, event):
        if self.mode == _Mode.PAN:
            if event.name == "button_press_event":
                self.press_pan(event)
            elif event.name == "button_release_event":
                self.release_pan(event)
        if self.mode == _Mode.ZOOM:
            if event.name == "button_press_event":
                self.press_zoom(event)
            elif event.name == "button_release_event":
                self.release_zoom(event)

    def _start_event_axes_interaction(self, event, *, method):

        def _ax_filter(ax):
            return (ax.in_axes(event) and
                    ax.get_navigate() and
                    getattr(ax, f"can_{method}")()
                    )

        def _capture_events(ax):
            f = ax.get_forward_navigation_events()
            if f == "auto":  # (capture = patch visibility)
                f = not ax.patch.get_visible()
            return not f

        # get all relevant axes for the event
        axes = list(filter(_ax_filter, self.canvas.figure.get_axes()))

        if len(axes) == 0:
            return []

        if self._nav_stack() is None:
            self.push_current()   # Set the home button to this view.

        # group axes by zorder (reverse to trigger later axes first)
        grps = dict()
        for ax in reversed(axes):
            grps.setdefault(ax.get_zorder(), []).append(ax)

        axes_to_trigger = []
        # go through zorders in reverse until we hit a capturing axes
        for zorder in sorted(grps, reverse=True):
            for ax in grps[zorder]:
                axes_to_trigger.append(ax)
                # NOTE: shared axes are automatically triggered, but twin-axes not!
                axes_to_trigger.extend(ax._twinned_axes.get_siblings(ax))

                if _capture_events(ax):
                    break  # break if we hit a capturing axes
            else:
                # If the inner loop finished without an explicit break,
                # (e.g. no capturing axes was found) continue the
                # outer loop to the next zorder.
                continue

            # If the inner loop was terminated with an explicit break,
            # terminate the outer loop as well.
            break

        # avoid duplicated triggers (but keep order of list)
        axes_to_trigger = list(dict.fromkeys(axes_to_trigger))

        return axes_to_trigger

    def pan(self, *args):
        """
        Toggle the pan/zoom tool.

        Pan with left button, zoom with right.
        """
        if not self.canvas.widgetlock.available(self):
            self.set_message("pan unavailable")
            return
        if self.mode == _Mode.PAN:
            self.mode = _Mode.NONE
            self.canvas.widgetlock.release(self)
        else:
            self.mode = _Mode.PAN
            self.canvas.widgetlock(self)
        for a in self.canvas.figure.get_axes():
            a.set_navigate_mode(self.mode._navigate_mode)

    _PanInfo = namedtuple("_PanInfo", "button axes cid")

    def press_pan(self, event):
        """Callback for mouse button press in pan/zoom mode."""
        if (event.button not in [MouseButton.LEFT, MouseButton.RIGHT]
                or event.x is None or event.y is None):
            return

        axes = self._start_event_axes_interaction(event, method="pan")
        if not axes:
            return

        # call "ax.start_pan(..)" on all relevant axes of an event
        for ax in axes:
            ax.start_pan(event.x, event.y, event.button)

        self.canvas.mpl_disconnect(self._id_drag)
        id_drag = self.canvas.mpl_connect("motion_notify_event", self.drag_pan)

        self._pan_info = self._PanInfo(
            button=event.button, axes=axes, cid=id_drag)

    def drag_pan(self, event):
        """Callback for dragging in pan/zoom mode."""
        for ax in self._pan_info.axes:
            # Using the recorded button at the press is safer than the current
            # button, as multiple buttons can get pressed during motion.
            ax.drag_pan(self._pan_info.button, event.key, event.x, event.y)
        self.canvas.draw_idle()

    def release_pan(self, event):
        """Callback for mouse button release in pan/zoom mode."""
        if self._pan_info is None:
            return
        self.canvas.mpl_disconnect(self._pan_info.cid)
        self._id_drag = self.canvas.mpl_connect(
            'motion_notify_event', self.mouse_move)
        for ax in self._pan_info.axes:
            ax.end_pan()
        self.canvas.draw_idle()
        self._pan_info = None
        self.push_current()

    def zoom(self, *args):
        if not self.canvas.widgetlock.available(self):
            self.set_message("zoom unavailable")
            return
        """Toggle zoom to rect mode."""
        if self.mode == _Mode.ZOOM:
            self.mode = _Mode.NONE
            self.canvas.widgetlock.release(self)
        else:
            self.mode = _Mode.ZOOM
            self.canvas.widgetlock(self)
        for a in self.canvas.figure.get_axes():
            a.set_navigate_mode(self.mode._navigate_mode)

    _ZoomInfo = namedtuple("_ZoomInfo", "direction start_xy axes cid cbar")

    def press_zoom(self, event):
        """Callback for mouse button press in zoom to rect mode."""
        if (event.button not in [MouseButton.LEFT, MouseButton.RIGHT]
                or event.x is None or event.y is None):
            return

        axes = self._start_event_axes_interaction(event, method="zoom")
        if not axes:
            return

        id_zoom = self.canvas.mpl_connect(
            "motion_notify_event", self.drag_zoom)

        # A colorbar is one-dimensional, so we extend the zoom rectangle out
        # to the edge of the Axes bbox in the other dimension. To do that we
        # store the orientation of the colorbar for later.
        parent_ax = axes[0]
        if hasattr(parent_ax, "_colorbar"):
            cbar = parent_ax._colorbar.orientation
        else:
            cbar = None

        self._zoom_info = self._ZoomInfo(
            direction="in" if event.button == 1 else "out",
            start_xy=(event.x, event.y), axes=axes, cid=id_zoom, cbar=cbar)

    def drag_zoom(self, event):
        """Callback for dragging in zoom mode."""
        start_xy = self._zoom_info.start_xy
        ax = self._zoom_info.axes[0]
        (x1, y1), (x2, y2) = np.clip(
            [start_xy, [event.x, event.y]], ax.bbox.min, ax.bbox.max)
        key = event.key
        # Force the key on colorbars to extend the short-axis bbox
        if self._zoom_info.cbar == "horizontal":
            key = "x"
        elif self._zoom_info.cbar == "vertical":
            key = "y"
        if key == "x":
            y1, y2 = ax.bbox.intervaly
        elif key == "y":
            x1, x2 = ax.bbox.intervalx

        self.draw_rubberband(event, x1, y1, x2, y2)

    def release_zoom(self, event):
        """Callback for mouse button release in zoom to rect mode."""
        if self._zoom_info is None:
            return

        # We don't check the event button here, so that zooms can be cancelled
        # by (pressing and) releasing another mouse button.
        self.canvas.mpl_disconnect(self._zoom_info.cid)
        self.remove_rubberband()

        start_x, start_y = self._zoom_info.start_xy
        key = event.key
        # Force the key on colorbars to ignore the zoom-cancel on the
        # short-axis side
        if self._zoom_info.cbar == "horizontal":
            key = "x"
        elif self._zoom_info.cbar == "vertical":
            key = "y"
        # Ignore single clicks: 5 pixels is a threshold that allows the user to
        # "cancel" a zoom action by zooming by less than 5 pixels.
        if ((abs(event.x - start_x) < 5 and key != "y") or
                (abs(event.y - start_y) < 5 and key != "x")):
            self.canvas.draw_idle()
            self._zoom_info = None
            return

        for i, ax in enumerate(self._zoom_info.axes):
            # Detect whether this Axes is twinned with an earlier Axes in the
            # list of zoomed Axes, to avoid double zooming.
            twinx = any(ax.get_shared_x_axes().joined(ax, prev)
                        for prev in self._zoom_info.axes[:i])
            twiny = any(ax.get_shared_y_axes().joined(ax, prev)
                        for prev in self._zoom_info.axes[:i])
            ax._set_view_from_bbox(
                (start_x, start_y, event.x, event.y),
                self._zoom_info.direction, key, twinx, twiny)

        self.canvas.draw_idle()
        self._zoom_info = None
        self.push_current()

    def push_current(self):
        """Push the current view limits and position onto the stack."""
        self._nav_stack.push(
            WeakKeyDictionary(
                {ax: (ax._get_view(),
                      # Store both the original and modified positions.
                      (ax.get_position(True).frozen(),
                       ax.get_position().frozen()))
                 for ax in self.canvas.figure.axes}))
        self.set_history_buttons()

    def _update_view(self):
        """
        Update the viewlim and position from the view and position stack for
        each Axes.
        """
        nav_info = self._nav_stack()
        if nav_info is None:
            return
        # Retrieve all items at once to avoid any risk of GC deleting an Axes
        # while in the middle of the loop below.
        items = list(nav_info.items())
        for ax, (view, (pos_orig, pos_active)) in items:
            ax._set_view(view)
            # Restore both the original and modified positions
            ax._set_position(pos_orig, 'original')
            ax._set_position(pos_active, 'active')
        self.canvas.draw_idle()

    def configure_subplots(self, *args):
        if hasattr(self, "subplot_tool"):
            self.subplot_tool.figure.canvas.manager.show()
            return
        # This import needs to happen here due to circular imports.
        from matplotlib.figure import Figure
        with mpl.rc_context({"toolbar": "none"}):  # No navbar for the toolfig.
            manager = type(self.canvas).new_manager(Figure(figsize=(6, 3)), -1)
        manager.set_window_title("Subplot configuration tool")
        tool_fig = manager.canvas.figure
        tool_fig.subplots_adjust(top=0.9)
        self.subplot_tool = widgets.SubplotTool(self.canvas.figure, tool_fig)
        cid = self.canvas.mpl_connect(
            "close_event", lambda e: manager.destroy())

        def on_tool_fig_close(e):
            self.canvas.mpl_disconnect(cid)
            del self.subplot_tool

        tool_fig.canvas.mpl_connect("close_event", on_tool_fig_close)
        manager.show()
        return self.subplot_tool

    def save_figure(self, *args):
        """
        Save the current figure.

        Backend implementations may choose to return
        the absolute path of the saved file, if any, as
        a string.

        If no file is created then `None` is returned.

        If the backend does not implement this functionality
        then `NavigationToolbar2.UNKNOWN_SAVED_STATUS` is returned.

        Returns
        -------
        str or `NavigationToolbar2.UNKNOWN_SAVED_STATUS` or `None`
            The filepath of the saved figure.
            Returns `None` if figure is not saved.
            Returns `NavigationToolbar2.UNKNOWN_SAVED_STATUS` when
            the backend does not provide the information.
        """
        raise NotImplementedError

    def update(self):
        """Reset the Axes stack."""
        self._nav_stack.clear()
        self.set_history_buttons()

    def set_history_buttons(self):
        """Enable or disable the back/forward button."""


class ToolContainerBase:
    """
    Base class for all tool containers, e.g. toolbars.

    Attributes
    ----------
    toolmanager : `.ToolManager`
        The tools with which this `ToolContainer` wants to communicate.
    """

    _icon_extension = '.png'
    """
    Toolcontainer button icon image format extension

    **String**: Image extension
    """

    def __init__(self, toolmanager):
        self.toolmanager = toolmanager
        toolmanager.toolmanager_connect(
            'tool_message_event',
            lambda event: self.set_message(event.message))
        toolmanager.toolmanager_connect(
            'tool_removed_event',
            lambda event: self.remove_toolitem(event.tool.name))

    def _tool_toggled_cbk(self, event):
        """
        Capture the 'tool_trigger_[name]'

        This only gets used for toggled tools.
        """
        self.toggle_toolitem(event.tool.name, event.tool.toggled)

    def add_tool(self, tool, group, position=-1):
        """
        Add a tool to this container.

        Parameters
        ----------
        tool : tool_like
            The tool to add, see `.ToolManager.get_tool`.
        group : str
            The name of the group to add this tool to.
        position : int, default: -1
            The position within the group to place this tool.
        """
        tool = self.toolmanager.get_tool(tool)
        image = self._get_image_filename(tool)
        toggle = getattr(tool, 'toggled', None) is not None
        self.add_toolitem(tool.name, group, position,
                          image, tool.description, toggle)
        if toggle:
            self.toolmanager.toolmanager_connect('tool_trigger_%s' % tool.name,
                                                 self._tool_toggled_cbk)
            # If initially toggled
            if tool.toggled:
                self.toggle_toolitem(tool.name, True)

    def _get_image_filename(self, tool):
        """Resolve a tool icon's filename."""
        if not tool.image:
            return None
        if os.path.isabs(tool.image):
            filename = tool.image
        else:
            if "image" in getattr(tool, "__dict__", {}):
                raise ValueError("If 'tool.image' is an instance variable, "
                                 "it must be an absolute path")
            for cls in type(tool).__mro__:
                if "image" in vars(cls):
                    try:
                        src = inspect.getfile(cls)
                        break
                    except (OSError, TypeError):
                        raise ValueError("Failed to locate source file "
                                         "where 'tool.image' is defined") from None
            else:
                raise ValueError("Failed to find parent class defining 'tool.image'")
            filename = str(pathlib.Path(src).parent / tool.image)
        for filename in [filename, filename + self._icon_extension]:
            if os.path.isfile(filename):
                return os.path.abspath(filename)
        for fname in [  # Fallback; once deprecation elapses.
            tool.image,
            tool.image + self._icon_extension,
            cbook._get_data_path("images", tool.image),
            cbook._get_data_path("images", tool.image + self._icon_extension),
        ]:
            if os.path.isfile(fname):
                _api.warn_deprecated(
                    "3.9", message=f"Loading icon {tool.image!r} from the current "
                    "directory or from Matplotlib's image directory.  This behavior "
                    "is deprecated since %(since)s and will be removed in %(removal)s; "
                    "Tool.image should be set to a path relative to the Tool's source "
                    "file, or to an absolute path.")
                return os.path.abspath(fname)

    def trigger_tool(self, name):
        """
        Trigger the tool.

        Parameters
        ----------
        name : str
            Name (id) of the tool triggered from within the container.
        """
        self.toolmanager.trigger_tool(name, sender=self)

    def add_toolitem(self, name, group, position, image, description, toggle):
        """
        A hook to add a toolitem to the container.

        This hook must be implemented in each backend and contains the
        backend-specific code to add an element to the toolbar.

        .. warning::
            This is part of the backend implementation and should
            not be called by end-users.  They should instead call
            `.ToolContainerBase.add_tool`.

        The callback associated with the button click event
        must be *exactly* ``self.trigger_tool(name)``.

        Parameters
        ----------
        name : str
            Name of the tool to add, this gets used as the tool's ID and as the
            default label of the buttons.
        group : str
            Name of the group that this tool belongs to.
        position : int
            Position of the tool within its group, if -1 it goes at the end.
        image : str
            Filename of the image for the button or `None`.
        description : str
            Description of the tool, used for the tooltips.
        toggle : bool
            * `True` : The button is a toggle (change the pressed/unpressed
              state between consecutive clicks).
            * `False` : The button is a normal button (returns to unpressed
              state after release).
        """
        raise NotImplementedError

    def toggle_toolitem(self, name, toggled):
        """
        A hook to toggle a toolitem without firing an event.

        This hook must be implemented in each backend and contains the
        backend-specific code to silently toggle a toolbar element.

        .. warning::
            This is part of the backend implementation and should
            not be called by end-users.  They should instead call
            `.ToolManager.trigger_tool` or `.ToolContainerBase.trigger_tool`
            (which are equivalent).

        Parameters
        ----------
        name : str
            Id of the tool to toggle.
        toggled : bool
            Whether to set this tool as toggled or not.
        """
        raise NotImplementedError

    def remove_toolitem(self, name):
        """
        A hook to remove a toolitem from the container.

        This hook must be implemented in each backend and contains the
        backend-specific code to remove an element from the toolbar; it is
        called when `.ToolManager` emits a ``tool_removed_event``.

        Because some tools are present only on the `.ToolManager` but not on
        the `ToolContainer`, this method must be a no-op when called on a tool
        absent from the container.

        .. warning::
            This is part of the backend implementation and should
            not be called by end-users.  They should instead call
            `.ToolManager.remove_tool`.

        Parameters
        ----------
        name : str
            Name of the tool to remove.
        """
        raise NotImplementedError

    def set_message(self, s):
        """
        Display a message on the toolbar.

        Parameters
        ----------
        s : str
            Message text.
        """
        raise NotImplementedError


class _Backend:
    # A backend can be defined by using the following pattern:
    #
    # @_Backend.export
    # class FooBackend(_Backend):
    #     # override the attributes and methods documented below.

    # `backend_version` may be overridden by the subclass.
    backend_version = "unknown"

    # The `FigureCanvas` class must be defined.
    FigureCanvas = None

    # For interactive backends, the `FigureManager` class must be overridden.
    FigureManager = FigureManagerBase

    # For interactive backends, `mainloop` should be a function taking no
    # argument and starting the backend main loop.  It should be left as None
    # for non-interactive backends.
    mainloop = None

    # The following methods will be automatically defined and exported, but
    # can be overridden.

    @classmethod
    def new_figure_manager(cls, num, *args, **kwargs):
        """Create a new figure manager instance."""
        # This import needs to happen here due to circular imports.
        from matplotlib.figure import Figure
        fig_cls = kwargs.pop('FigureClass', Figure)
        fig = fig_cls(*args, **kwargs)
        return cls.new_figure_manager_given_figure(num, fig)

    @classmethod
    def new_figure_manager_given_figure(cls, num, figure):
        """Create a new figure manager instance for the given figure."""
        return cls.FigureCanvas.new_manager(figure, num)

    @classmethod
    def draw_if_interactive(cls):
        manager_class = cls.FigureCanvas.manager_class
        # Interactive backends reimplement start_main_loop or pyplot_show.
        backend_is_interactive = (
            manager_class.start_main_loop != FigureManagerBase.start_main_loop
            or manager_class.pyplot_show != FigureManagerBase.pyplot_show)
        if backend_is_interactive and is_interactive():
            manager = Gcf.get_active()
            if manager:
                manager.canvas.draw_idle()

    @classmethod
    def show(cls, *, block=None):
        """
        Show all figures.

        `show` blocks by calling `mainloop` if *block* is ``True``, or if it is
        ``None`` and we are not in `interactive` mode and if IPython's
        ``%matplotlib`` integration has not been activated.
        """
        managers = Gcf.get_all_fig_managers()
        if not managers:
            return
        for manager in managers:
            try:
                manager.show()  # Emits a warning for non-interactive backend.
            except NonGuiException as exc:
                _api.warn_external(str(exc))
        if cls.mainloop is None:
            return
        if block is None:
            # Hack: Is IPython's %matplotlib integration activated?  If so,
            # IPython's activate_matplotlib (>= 0.10) tacks a _needmain
            # attribute onto pyplot.show (always set to False).
            pyplot_show = getattr(sys.modules.get("matplotlib.pyplot"), "show", None)
            ipython_pylab = hasattr(pyplot_show, "_needmain")
            block = not ipython_pylab and not is_interactive()
        if block:
            cls.mainloop()

    # This method is the one actually exporting the required methods.

    @staticmethod
    def export(cls):
        for name in [
                "backend_version",
                "FigureCanvas",
                "FigureManager",
                "new_figure_manager",
                "new_figure_manager_given_figure",
                "draw_if_interactive",
                "show",
        ]:
            setattr(sys.modules[cls.__module__], name, getattr(cls, name))

        # For back-compatibility, generate a shim `Show` class.

        class Show(ShowBase):
            def mainloop(self):
                return cls.mainloop()

        setattr(sys.modules[cls.__module__], "Show", Show)
        return cls


class ShowBase(_Backend):
    """
    Simple base class to generate a ``show()`` function in backends.

    Subclass must override ``mainloop()`` method.
    """

    def __call__(self, block=None):
        return self.show(block=block)
