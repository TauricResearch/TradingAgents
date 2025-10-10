"""
Classes for the efficient drawing of large collections of objects that
share most properties, e.g., a large number of line segments or
polygons.

The classes are not meant to be as flexible as their single element
counterparts (e.g., you may not be able to select all line styles) but
they are meant to be fast for common use cases (e.g., a large set of solid
line segments).
"""

import itertools
import functools
import math
from numbers import Number, Real
import warnings

import numpy as np

import matplotlib as mpl
from . import (_api, _path, artist, cbook, colorizer as mcolorizer, colors as mcolors,
               _docstring, hatch as mhatch, lines as mlines, path as mpath, transforms)
from ._enums import JoinStyle, CapStyle


# "color" is excluded; it is a compound setter, and its docstring differs
# in LineCollection.
@_api.define_aliases({
    "antialiased": ["antialiaseds", "aa"],
    "edgecolor": ["edgecolors", "ec"],
    "facecolor": ["facecolors", "fc"],
    "linestyle": ["linestyles", "dashes", "ls"],
    "linewidth": ["linewidths", "lw"],
    "offset_transform": ["transOffset"],
})
class Collection(mcolorizer.ColorizingArtist):
    r"""
    Base class for Collections. Must be subclassed to be usable.

    A Collection represents a sequence of `.Patch`\es that can be drawn
    more efficiently together than individually. For example, when a single
    path is being drawn repeatedly at different offsets, the renderer can
    typically execute a ``draw_marker()`` call much more efficiently than a
    series of repeated calls to ``draw_path()`` with the offsets put in
    one-by-one.

    Most properties of a collection can be configured per-element. Therefore,
    Collections have "plural" versions of many of the properties of a `.Patch`
    (e.g. `.Collection.get_paths` instead of `.Patch.get_path`). Exceptions are
    the *zorder*, *hatch*, *pickradius*, *capstyle* and *joinstyle* properties,
    which can only be set globally for the whole collection.

    Besides these exceptions, all properties can be specified as single values
    (applying to all elements) or sequences of values. The property of the
    ``i``\th element of the collection is::

      prop[i % len(prop)]

    Each Collection can optionally be used as its own `.ScalarMappable` by
    passing the *norm* and *cmap* parameters to its constructor. If the
    Collection's `.ScalarMappable` matrix ``_A`` has been set (via a call
    to `.Collection.set_array`), then at draw time this internal scalar
    mappable will be used to set the ``facecolors`` and ``edgecolors``,
    ignoring those that were manually passed in.
    """
    #: Either a list of 3x3 arrays or an Nx3x3 array (representing N
    #: transforms), suitable for the `all_transforms` argument to
    #: `~matplotlib.backend_bases.RendererBase.draw_path_collection`;
    #: each 3x3 array is used to initialize an
    #: `~matplotlib.transforms.Affine2D` object.
    #: Each kind of collection defines this based on its arguments.
    _transforms = np.empty((0, 3, 3))

    # Whether to draw an edge by default.  Set on a
    # subclass-by-subclass basis.
    _edge_default = False

    @_docstring.interpd
    def __init__(self, *,
                 edgecolors=None,
                 facecolors=None,
                 linewidths=None,
                 linestyles='solid',
                 capstyle=None,
                 joinstyle=None,
                 antialiaseds=None,
                 offsets=None,
                 offset_transform=None,
                 norm=None,  # optional for ScalarMappable
                 cmap=None,  # ditto
                 colorizer=None,
                 pickradius=5.0,
                 hatch=None,
                 urls=None,
                 zorder=1,
                 **kwargs
                 ):
        """
        Parameters
        ----------
        edgecolors : :mpltype:`color` or list of colors, default: :rc:`patch.edgecolor`
            Edge color for each patch making up the collection. The special
            value 'face' can be passed to make the edgecolor match the
            facecolor.
        facecolors : :mpltype:`color` or list of colors, default: :rc:`patch.facecolor`
            Face color for each patch making up the collection.
        linewidths : float or list of floats, default: :rc:`patch.linewidth`
            Line width for each patch making up the collection.
        linestyles : str or tuple or list thereof, default: 'solid'
            Valid strings are ['solid', 'dashed', 'dashdot', 'dotted', '-',
            '--', '-.', ':']. Dash tuples should be of the form::

                (offset, onoffseq),

            where *onoffseq* is an even length tuple of on and off ink lengths
            in points. For examples, see
            :doc:`/gallery/lines_bars_and_markers/linestyles`.
        capstyle : `.CapStyle`-like, default: 'butt'
            Style to use for capping lines for all paths in the collection.
            Allowed values are %(CapStyle)s.
        joinstyle : `.JoinStyle`-like, default: 'round'
            Style to use for joining lines for all paths in the collection.
            Allowed values are %(JoinStyle)s.
        antialiaseds : bool or list of bool, default: :rc:`patch.antialiased`
            Whether each patch in the collection should be drawn with
            antialiasing.
        offsets : (float, float) or list thereof, default: (0, 0)
            A vector by which to translate each patch after rendering (default
            is no translation). The translation is performed in screen (pixel)
            coordinates (i.e. after the Artist's transform is applied).
        offset_transform : `~.Transform`, default: `.IdentityTransform`
            A single transform which will be applied to each *offsets* vector
            before it is used.
        cmap, norm
            Data normalization and colormapping parameters. See
            `.ScalarMappable` for a detailed description.
        hatch : str, optional
            Hatching pattern to use in filled paths, if any. Valid strings are
            ['/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*']. See
            :doc:`/gallery/shapes_and_collections/hatch_style_reference` for
            the meaning of each hatch type.
        pickradius : float, default: 5.0
            If ``pickradius <= 0``, then `.Collection.contains` will return
            ``True`` whenever the test point is inside of one of the polygons
            formed by the control points of a Path in the Collection. On the
            other hand, if it is greater than 0, then we instead check if the
            test point is contained in a stroke of width ``2*pickradius``
            following any of the Paths in the Collection.
        urls : list of str, default: None
            A URL for each patch to link to once drawn. Currently only works
            for the SVG backend. See :doc:`/gallery/misc/hyperlinks_sgskip` for
            examples.
        zorder : float, default: 1
            The drawing order, shared by all Patches in the Collection. See
            :doc:`/gallery/misc/zorder_demo` for all defaults and examples.
        **kwargs
            Remaining keyword arguments will be used to set properties as
            ``Collection.set_{key}(val)`` for each key-value pair in *kwargs*.
        """

        super().__init__(self._get_colorizer(cmap, norm, colorizer))
        # list of un-scaled dash patterns
        # this is needed scaling the dash pattern by linewidth
        self._us_linestyles = [(0, None)]
        # list of dash patterns
        self._linestyles = [(0, None)]
        # list of unbroadcast/scaled linewidths
        self._us_lw = [0]
        self._linewidths = [0]

        self._gapcolor = None  # Currently only used by LineCollection.

        # Flags set by _set_mappable_flags: are colors from mapping an array?
        self._face_is_mapped = None
        self._edge_is_mapped = None
        self._mapped_colors = None  # calculated in update_scalarmappable
        self._hatch_color = mcolors.to_rgba(mpl.rcParams['hatch.color'])
        self._hatch_linewidth = mpl.rcParams['hatch.linewidth']
        self.set_facecolor(facecolors)
        self.set_edgecolor(edgecolors)
        self.set_linewidth(linewidths)
        self.set_linestyle(linestyles)
        self.set_antialiased(antialiaseds)
        self.set_pickradius(pickradius)
        self.set_urls(urls)
        self.set_hatch(hatch)
        self.set_zorder(zorder)

        if capstyle:
            self.set_capstyle(capstyle)
        else:
            self._capstyle = None

        if joinstyle:
            self.set_joinstyle(joinstyle)
        else:
            self._joinstyle = None

        if offsets is not None:
            offsets = np.asanyarray(offsets, float)
            # Broadcast (2,) -> (1, 2) but nothing else.
            if offsets.shape == (2,):
                offsets = offsets[None, :]

        self._offsets = offsets
        self._offset_transform = offset_transform

        self._path_effects = None
        self._internal_update(kwargs)
        self._paths = None

    def get_paths(self):
        return self._paths

    def set_paths(self, paths):
        self._paths = paths
        self.stale = True

    def get_transforms(self):
        return self._transforms

    def get_offset_transform(self):
        """Return the `.Transform` instance used by this artist offset."""
        if self._offset_transform is None:
            self._offset_transform = transforms.IdentityTransform()
        elif (not isinstance(self._offset_transform, transforms.Transform)
              and hasattr(self._offset_transform, '_as_mpl_transform')):
            self._offset_transform = \
                self._offset_transform._as_mpl_transform(self.axes)
        return self._offset_transform

    def set_offset_transform(self, offset_transform):
        """
        Set the artist offset transform.

        Parameters
        ----------
        offset_transform : `.Transform`
        """
        self._offset_transform = offset_transform

    def get_datalim(self, transData):
        # Calculate the data limits and return them as a `.Bbox`.
        #
        # This operation depends on the transforms for the data in the
        # collection and whether the collection has offsets:
        #
        # 1. offsets = None, transform child of transData: use the paths for
        # the automatic limits (i.e. for LineCollection in streamline).
        # 2. offsets != None: offset_transform is child of transData:
        #
        #    a. transform is child of transData: use the path + offset for
        #       limits (i.e for bar).
        #    b. transform is not a child of transData: just use the offsets
        #       for the limits (i.e. for scatter)
        #
        # 3. otherwise return a null Bbox.

        transform = self.get_transform()
        offset_trf = self.get_offset_transform()
        if not (isinstance(offset_trf, transforms.IdentityTransform)
                or offset_trf.contains_branch(transData)):
            # if the offsets are in some coords other than data,
            # then don't use them for autoscaling.
            return transforms.Bbox.null()

        paths = self.get_paths()
        if not len(paths):
            # No paths to transform
            return transforms.Bbox.null()

        if not transform.is_affine:
            paths = [transform.transform_path_non_affine(p) for p in paths]
            # Don't convert transform to transform.get_affine() here because
            # we may have transform.contains_branch(transData) but not
            # transforms.get_affine().contains_branch(transData).  But later,
            # be careful to only apply the affine part that remains.

        offsets = self.get_offsets()

        if any(transform.contains_branch_seperately(transData)):
            # collections that are just in data units (like quiver)
            # can properly have the axes limits set by their shape +
            # offset.  LineCollections that have no offsets can
            # also use this algorithm (like streamplot).
            if isinstance(offsets, np.ma.MaskedArray):
                offsets = offsets.filled(np.nan)
                # get_path_collection_extents handles nan but not masked arrays
            return mpath.get_path_collection_extents(
                transform.get_affine() - transData, paths,
                self.get_transforms(),
                offset_trf.transform_non_affine(offsets),
                offset_trf.get_affine().frozen())

        # NOTE: None is the default case where no offsets were passed in
        if self._offsets is not None:
            # this is for collections that have their paths (shapes)
            # in physical, axes-relative, or figure-relative units
            # (i.e. like scatter). We can't uniquely set limits based on
            # those shapes, so we just set the limits based on their
            # location.
            offsets = (offset_trf - transData).transform(offsets)
            # note A-B means A B^{-1}
            offsets = np.ma.masked_invalid(offsets)
            if not offsets.mask.all():
                bbox = transforms.Bbox.null()
                bbox.update_from_data_xy(offsets)
                return bbox
        return transforms.Bbox.null()

    def get_window_extent(self, renderer=None):
        # TODO: check to ensure that this does not fail for
        # cases other than scatter plot legend
        return self.get_datalim(transforms.IdentityTransform())

    def _prepare_points(self):
        # Helper for drawing and hit testing.

        transform = self.get_transform()
        offset_trf = self.get_offset_transform()
        offsets = self.get_offsets()
        paths = self.get_paths()

        if self.have_units():
            paths = []
            for path in self.get_paths():
                vertices = path.vertices
                xs, ys = vertices[:, 0], vertices[:, 1]
                xs = self.convert_xunits(xs)
                ys = self.convert_yunits(ys)
                paths.append(mpath.Path(np.column_stack([xs, ys]), path.codes))
            xs = self.convert_xunits(offsets[:, 0])
            ys = self.convert_yunits(offsets[:, 1])
            offsets = np.ma.column_stack([xs, ys])

        if not transform.is_affine:
            paths = [transform.transform_path_non_affine(path)
                     for path in paths]
            transform = transform.get_affine()
        if not offset_trf.is_affine:
            offsets = offset_trf.transform_non_affine(offsets)
            # This might have changed an ndarray into a masked array.
            offset_trf = offset_trf.get_affine()

        if isinstance(offsets, np.ma.MaskedArray):
            offsets = offsets.filled(np.nan)
            # Changing from a masked array to nan-filled ndarray
            # is probably most efficient at this point.

        return transform, offset_trf, offsets, paths

    @artist.allow_rasterization
    def draw(self, renderer):
        if not self.get_visible():
            return
        renderer.open_group(self.__class__.__name__, self.get_gid())

        self.update_scalarmappable()

        transform, offset_trf, offsets, paths = self._prepare_points()

        gc = renderer.new_gc()
        self._set_gc_clip(gc)
        gc.set_snap(self.get_snap())

        if self._hatch:
            gc.set_hatch(self._hatch)
            gc.set_hatch_color(self._hatch_color)
            gc.set_hatch_linewidth(self._hatch_linewidth)

        if self.get_sketch_params() is not None:
            gc.set_sketch_params(*self.get_sketch_params())

        if self.get_path_effects():
            from matplotlib.patheffects import PathEffectRenderer
            renderer = PathEffectRenderer(self.get_path_effects(), renderer)

        # If the collection is made up of a single shape/color/stroke,
        # it can be rendered once and blitted multiple times, using
        # `draw_markers` rather than `draw_path_collection`.  This is
        # *much* faster for Agg, and results in smaller file sizes in
        # PDF/SVG/PS.

        trans = self.get_transforms()
        facecolors = self.get_facecolor()
        edgecolors = self.get_edgecolor()
        do_single_path_optimization = False
        if (len(paths) == 1 and len(trans) <= 1 and
                len(facecolors) == 1 and len(edgecolors) == 1 and
                len(self._linewidths) == 1 and
                all(ls[1] is None for ls in self._linestyles) and
                len(self._antialiaseds) == 1 and len(self._urls) == 1 and
                self.get_hatch() is None):
            if len(trans):
                combined_transform = transforms.Affine2D(trans[0]) + transform
            else:
                combined_transform = transform
            extents = paths[0].get_extents(combined_transform)
            if (extents.width < self.get_figure(root=True).bbox.width
                    and extents.height < self.get_figure(root=True).bbox.height):
                do_single_path_optimization = True

        if self._joinstyle:
            gc.set_joinstyle(self._joinstyle)

        if self._capstyle:
            gc.set_capstyle(self._capstyle)

        if do_single_path_optimization:
            gc.set_foreground(tuple(edgecolors[0]))
            gc.set_linewidth(self._linewidths[0])
            gc.set_dashes(*self._linestyles[0])
            gc.set_antialiased(self._antialiaseds[0])
            gc.set_url(self._urls[0])
            renderer.draw_markers(
                gc, paths[0], combined_transform.frozen(),
                mpath.Path(offsets), offset_trf, tuple(facecolors[0]))
        else:
            if self._gapcolor is not None:
                # First draw paths within the gaps.
                ipaths, ilinestyles = self._get_inverse_paths_linestyles()
                renderer.draw_path_collection(
                    gc, transform.frozen(), ipaths,
                    self.get_transforms(), offsets, offset_trf,
                    [mcolors.to_rgba("none")], self._gapcolor,
                    self._linewidths, ilinestyles,
                    self._antialiaseds, self._urls,
                    "screen")

            renderer.draw_path_collection(
                gc, transform.frozen(), paths,
                self.get_transforms(), offsets, offset_trf,
                self.get_facecolor(), self.get_edgecolor(),
                self._linewidths, self._linestyles,
                self._antialiaseds, self._urls,
                "screen")  # offset_position, kept for backcompat.

        gc.restore()
        renderer.close_group(self.__class__.__name__)
        self.stale = False

    def set_pickradius(self, pickradius):
        """
        Set the pick radius used for containment tests.

        Parameters
        ----------
        pickradius : float
            Pick radius, in points.
        """
        if not isinstance(pickradius, Real):
            raise ValueError(
                f"pickradius must be a real-valued number, not {pickradius!r}")
        self._pickradius = pickradius

    def get_pickradius(self):
        return self._pickradius

    def contains(self, mouseevent):
        """
        Test whether the mouse event occurred in the collection.

        Returns ``bool, dict(ind=itemlist)``, where every item in itemlist
        contains the event.
        """
        if self._different_canvas(mouseevent) or not self.get_visible():
            return False, {}
        pickradius = (
            float(self._picker)
            if isinstance(self._picker, Number) and
               self._picker is not True  # the bool, not just nonzero or 1
            else self._pickradius)
        if self.axes:
            self.axes._unstale_viewLim()
        transform, offset_trf, offsets, paths = self._prepare_points()
        # Tests if the point is contained on one of the polygons formed
        # by the control points of each of the paths. A point is considered
        # "on" a path if it would lie within a stroke of width 2*pickradius
        # following the path. If pickradius <= 0, then we instead simply check
        # if the point is *inside* of the path instead.
        ind = _path.point_in_path_collection(
            mouseevent.x, mouseevent.y, pickradius,
            transform.frozen(), paths, self.get_transforms(),
            offsets, offset_trf, pickradius <= 0)
        return len(ind) > 0, dict(ind=ind)

    def set_urls(self, urls):
        """
        Parameters
        ----------
        urls : list of str or None

        Notes
        -----
        URLs are currently only implemented by the SVG backend. They are
        ignored by all other backends.
        """
        self._urls = urls if urls is not None else [None]
        self.stale = True

    def get_urls(self):
        """
        Return a list of URLs, one for each element of the collection.

        The list contains *None* for elements without a URL. See
        :doc:`/gallery/misc/hyperlinks_sgskip` for an example.
        """
        return self._urls

    def set_hatch(self, hatch):
        r"""
        Set the hatching pattern

        *hatch* can be one of::

          /   - diagonal hatching
          \   - back diagonal
          |   - vertical
          -   - horizontal
          +   - crossed
          x   - crossed diagonal
          o   - small circle
          O   - large circle
          .   - dots
          *   - stars

        Letters can be combined, in which case all the specified
        hatchings are done.  If same letter repeats, it increases the
        density of hatching of that pattern.

        Unlike other properties such as linewidth and colors, hatching
        can only be specified for the collection as a whole, not separately
        for each member.

        Parameters
        ----------
        hatch : {'/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*'}
        """
        # Use validate_hatch(list) after deprecation.
        mhatch._validate_hatch_pattern(hatch)
        self._hatch = hatch
        self.stale = True

    def get_hatch(self):
        """Return the current hatching pattern."""
        return self._hatch

    def set_hatch_linewidth(self, lw):
        """Set the hatch linewidth."""
        self._hatch_linewidth = lw

    def get_hatch_linewidth(self):
        """Return the hatch linewidth."""
        return self._hatch_linewidth

    def set_offsets(self, offsets):
        """
        Set the offsets for the collection.

        Parameters
        ----------
        offsets : (N, 2) or (2,) array-like
        """
        offsets = np.asanyarray(offsets)
        if offsets.shape == (2,):  # Broadcast (2,) -> (1, 2) but nothing else.
            offsets = offsets[None, :]
        cstack = (np.ma.column_stack if isinstance(offsets, np.ma.MaskedArray)
                  else np.column_stack)
        self._offsets = cstack(
            (np.asanyarray(self.convert_xunits(offsets[:, 0]), float),
             np.asanyarray(self.convert_yunits(offsets[:, 1]), float)))
        self.stale = True

    def get_offsets(self):
        """Return the offsets for the collection."""
        # Default to zeros in the no-offset (None) case
        return np.zeros((1, 2)) if self._offsets is None else self._offsets

    def _get_default_linewidth(self):
        # This may be overridden in a subclass.
        return mpl.rcParams['patch.linewidth']  # validated as float

    def set_linewidth(self, lw):
        """
        Set the linewidth(s) for the collection.  *lw* can be a scalar
        or a sequence; if it is a sequence the patches will cycle
        through the sequence

        Parameters
        ----------
        lw : float or list of floats
        """
        if lw is None:
            lw = self._get_default_linewidth()
        # get the un-scaled/broadcast lw
        self._us_lw = np.atleast_1d(lw)

        # scale all of the dash patterns.
        self._linewidths, self._linestyles = self._bcast_lwls(
            self._us_lw, self._us_linestyles)
        self.stale = True

    def set_linestyle(self, ls):
        """
        Set the linestyle(s) for the collection.

        ===========================   =================
        linestyle                     description
        ===========================   =================
        ``'-'`` or ``'solid'``        solid line
        ``'--'`` or  ``'dashed'``     dashed line
        ``'-.'`` or  ``'dashdot'``    dash-dotted line
        ``':'`` or ``'dotted'``       dotted line
        ===========================   =================

        Alternatively a dash tuple of the following form can be provided::

            (offset, onoffseq),

        where ``onoffseq`` is an even length tuple of on and off ink in points.

        Parameters
        ----------
        ls : str or tuple or list thereof
            Valid values for individual linestyles include {'-', '--', '-.',
            ':', '', (offset, on-off-seq)}. See `.Line2D.set_linestyle` for a
            complete description.
        """
        # get the list of raw 'unscaled' dash patterns
        self._us_linestyles = mlines._get_dash_patterns(ls)

        # broadcast and scale the lw and dash patterns
        self._linewidths, self._linestyles = self._bcast_lwls(
            self._us_lw, self._us_linestyles)

    @_docstring.interpd
    def set_capstyle(self, cs):
        """
        Set the `.CapStyle` for the collection (for all its elements).

        Parameters
        ----------
        cs : `.CapStyle` or %(CapStyle)s
        """
        self._capstyle = CapStyle(cs)

    @_docstring.interpd
    def get_capstyle(self):
        """
        Return the cap style for the collection (for all its elements).

        Returns
        -------
        %(CapStyle)s or None
        """
        return self._capstyle.name if self._capstyle else None

    @_docstring.interpd
    def set_joinstyle(self, js):
        """
        Set the `.JoinStyle` for the collection (for all its elements).

        Parameters
        ----------
        js : `.JoinStyle` or %(JoinStyle)s
        """
        self._joinstyle = JoinStyle(js)

    @_docstring.interpd
    def get_joinstyle(self):
        """
        Return the join style for the collection (for all its elements).

        Returns
        -------
        %(JoinStyle)s or None
        """
        return self._joinstyle.name if self._joinstyle else None

    @staticmethod
    def _bcast_lwls(linewidths, dashes):
        """
        Internal helper function to broadcast + scale ls/lw

        In the collection drawing code, the linewidth and linestyle are cycled
        through as circular buffers (via ``v[i % len(v)]``).  Thus, if we are
        going to scale the dash pattern at set time (not draw time) we need to
        do the broadcasting now and expand both lists to be the same length.

        Parameters
        ----------
        linewidths : list
            line widths of collection
        dashes : list
            dash specification (offset, (dash pattern tuple))

        Returns
        -------
        linewidths, dashes : list
            Will be the same length, dashes are scaled by paired linewidth
        """
        if mpl.rcParams['_internal.classic_mode']:
            return linewidths, dashes
        # make sure they are the same length so we can zip them
        if len(dashes) != len(linewidths):
            l_dashes = len(dashes)
            l_lw = len(linewidths)
            gcd = math.gcd(l_dashes, l_lw)
            dashes = list(dashes) * (l_lw // gcd)
            linewidths = list(linewidths) * (l_dashes // gcd)

        # scale the dash patterns
        dashes = [mlines._scale_dashes(o, d, lw)
                  for (o, d), lw in zip(dashes, linewidths)]

        return linewidths, dashes

    def get_antialiased(self):
        """
        Get the antialiasing state for rendering.

        Returns
        -------
        array of bools
        """
        return self._antialiaseds

    def set_antialiased(self, aa):
        """
        Set the antialiasing state for rendering.

        Parameters
        ----------
        aa : bool or list of bools
        """
        if aa is None:
            aa = self._get_default_antialiased()
        self._antialiaseds = np.atleast_1d(np.asarray(aa, bool))
        self.stale = True

    def _get_default_antialiased(self):
        # This may be overridden in a subclass.
        return mpl.rcParams['patch.antialiased']

    def set_color(self, c):
        """
        Set both the edgecolor and the facecolor.

        Parameters
        ----------
        c : :mpltype:`color` or list of RGBA tuples

        See Also
        --------
        Collection.set_facecolor, Collection.set_edgecolor
            For setting the edge or face color individually.
        """
        self.set_facecolor(c)
        self.set_edgecolor(c)

    def _get_default_facecolor(self):
        # This may be overridden in a subclass.
        return mpl.rcParams['patch.facecolor']

    def _set_facecolor(self, c):
        if c is None:
            c = self._get_default_facecolor()

        self._facecolors = mcolors.to_rgba_array(c, self._alpha)
        self.stale = True

    def set_facecolor(self, c):
        """
        Set the facecolor(s) of the collection. *c* can be a color (all patches
        have same color), or a sequence of colors; if it is a sequence the
        patches will cycle through the sequence.

        If *c* is 'none', the patch will not be filled.

        Parameters
        ----------
        c : :mpltype:`color` or list of :mpltype:`color`
        """
        if isinstance(c, str) and c.lower() in ("none", "face"):
            c = c.lower()
        self._original_facecolor = c
        self._set_facecolor(c)

    def get_facecolor(self):
        return self._facecolors

    def get_edgecolor(self):
        if cbook._str_equal(self._edgecolors, 'face'):
            return self.get_facecolor()
        else:
            return self._edgecolors

    def _get_default_edgecolor(self):
        # This may be overridden in a subclass.
        return mpl.rcParams['patch.edgecolor']

    def _set_edgecolor(self, c):
        set_hatch_color = True
        if c is None:
            if (mpl.rcParams['patch.force_edgecolor']
                    or self._edge_default
                    or cbook._str_equal(self._original_facecolor, 'none')):
                c = self._get_default_edgecolor()
            else:
                c = 'none'
                set_hatch_color = False
        if cbook._str_lower_equal(c, 'face'):
            self._edgecolors = 'face'
            self.stale = True
            return
        self._edgecolors = mcolors.to_rgba_array(c, self._alpha)
        if set_hatch_color and len(self._edgecolors):
            self._hatch_color = tuple(self._edgecolors[0])
        self.stale = True

    def set_edgecolor(self, c):
        """
        Set the edgecolor(s) of the collection.

        Parameters
        ----------
        c : :mpltype:`color` or list of :mpltype:`color` or 'face'
            The collection edgecolor(s).  If a sequence, the patches cycle
            through it.  If 'face', match the facecolor.
        """
        # We pass through a default value for use in LineCollection.
        # This allows us to maintain None as the default indicator in
        # _original_edgecolor.
        if isinstance(c, str) and c.lower() in ("none", "face"):
            c = c.lower()
        self._original_edgecolor = c
        self._set_edgecolor(c)

    def set_alpha(self, alpha):
        """
        Set the transparency of the collection.

        Parameters
        ----------
        alpha : float or array of float or None
            If not None, *alpha* values must be between 0 and 1, inclusive.
            If an array is provided, its length must match the number of
            elements in the collection.  Masked values and nans are not
            supported.
        """
        artist.Artist._set_alpha_for_array(self, alpha)
        self._set_facecolor(self._original_facecolor)
        self._set_edgecolor(self._original_edgecolor)

    set_alpha.__doc__ = artist.Artist._set_alpha_for_array.__doc__

    def get_linewidth(self):
        return self._linewidths

    def get_linestyle(self):
        return self._linestyles

    def _set_mappable_flags(self):
        """
        Determine whether edges and/or faces are color-mapped.

        This is a helper for update_scalarmappable.
        It sets Boolean flags '_edge_is_mapped' and '_face_is_mapped'.

        Returns
        -------
        mapping_change : bool
            True if either flag is True, or if a flag has changed.
        """
        # The flags are initialized to None to ensure this returns True
        # the first time it is called.
        edge0 = self._edge_is_mapped
        face0 = self._face_is_mapped
        # After returning, the flags must be Booleans, not None.
        self._edge_is_mapped = False
        self._face_is_mapped = False
        if self._A is not None:
            if not cbook._str_equal(self._original_facecolor, 'none'):
                self._face_is_mapped = True
                if cbook._str_equal(self._original_edgecolor, 'face'):
                    self._edge_is_mapped = True
            else:
                if self._original_edgecolor is None:
                    self._edge_is_mapped = True

        mapped = self._face_is_mapped or self._edge_is_mapped
        changed = (edge0 is None or face0 is None
                   or self._edge_is_mapped != edge0
                   or self._face_is_mapped != face0)
        return mapped or changed

    def update_scalarmappable(self):
        """
        Update colors from the scalar mappable array, if any.

        Assign colors to edges and faces based on the array and/or
        colors that were directly set, as appropriate.
        """
        if not self._set_mappable_flags():
            return
        # Allow possibility to call 'self.set_array(None)'.
        if self._A is not None:
            # QuadMesh can map 2d arrays (but pcolormesh supplies 1d array)
            if self._A.ndim > 1 and not isinstance(self, _MeshData):
                raise ValueError('Collections can only map rank 1 arrays')
            if np.iterable(self._alpha):
                if self._alpha.size != self._A.size:
                    raise ValueError(
                        f'Data array shape, {self._A.shape} '
                        'is incompatible with alpha array shape, '
                        f'{self._alpha.shape}. '
                        'This can occur with the deprecated '
                        'behavior of the "flat" shading option, '
                        'in which a row and/or column of the data '
                        'array is dropped.')
                # pcolormesh, scatter, maybe others flatten their _A
                self._alpha = self._alpha.reshape(self._A.shape)
            self._mapped_colors = self.to_rgba(self._A, self._alpha)

        if self._face_is_mapped:
            self._facecolors = self._mapped_colors
        else:
            self._set_facecolor(self._original_facecolor)
        if self._edge_is_mapped:
            self._edgecolors = self._mapped_colors
        else:
            self._set_edgecolor(self._original_edgecolor)
        self.stale = True

    def get_fill(self):
        """Return whether face is colored."""
        return not cbook._str_lower_equal(self._original_facecolor, "none")

    def update_from(self, other):
        """Copy properties from other to self."""

        artist.Artist.update_from(self, other)
        self._antialiaseds = other._antialiaseds
        self._mapped_colors = other._mapped_colors
        self._edge_is_mapped = other._edge_is_mapped
        self._original_edgecolor = other._original_edgecolor
        self._edgecolors = other._edgecolors
        self._face_is_mapped = other._face_is_mapped
        self._original_facecolor = other._original_facecolor
        self._facecolors = other._facecolors
        self._linewidths = other._linewidths
        self._linestyles = other._linestyles
        self._us_linestyles = other._us_linestyles
        self._pickradius = other._pickradius
        self._hatch = other._hatch

        # update_from for scalarmappable
        self._A = other._A
        self.norm = other.norm
        self.cmap = other.cmap
        self.stale = True


class _CollectionWithSizes(Collection):
    """
    Base class for collections that have an array of sizes.
    """
    _factor = 1.0

    def get_sizes(self):
        """
        Return the sizes ('areas') of the elements in the collection.

        Returns
        -------
        array
            The 'area' of each element.
        """
        return self._sizes

    def set_sizes(self, sizes, dpi=72.0):
        """
        Set the sizes of each member of the collection.

        Parameters
        ----------
        sizes : `numpy.ndarray` or None
            The size to set for each element of the collection.  The
            value is the 'area' of the element.
        dpi : float, default: 72
            The dpi of the canvas.
        """
        if sizes is None:
            self._sizes = np.array([])
            self._transforms = np.empty((0, 3, 3))
        else:
            self._sizes = np.asarray(sizes)
            self._transforms = np.zeros((len(self._sizes), 3, 3))
            scale = np.sqrt(self._sizes) * dpi / 72.0 * self._factor
            self._transforms[:, 0, 0] = scale
            self._transforms[:, 1, 1] = scale
            self._transforms[:, 2, 2] = 1.0
        self.stale = True

    @artist.allow_rasterization
    def draw(self, renderer):
        self.set_sizes(self._sizes, self.get_figure(root=True).dpi)
        super().draw(renderer)


class PathCollection(_CollectionWithSizes):
    r"""
    A collection of `~.path.Path`\s, as created by e.g. `~.Axes.scatter`.
    """

    def __init__(self, paths, sizes=None, **kwargs):
        """
        Parameters
        ----------
        paths : list of `.path.Path`
            The paths that will make up the `.Collection`.
        sizes : array-like
            The factor by which to scale each drawn `~.path.Path`. One unit
            squared in the Path's data space is scaled to be ``sizes**2``
            points when rendered.
        **kwargs
            Forwarded to `.Collection`.
        """

        super().__init__(**kwargs)
        self.set_paths(paths)
        self.set_sizes(sizes)
        self.stale = True

    def get_paths(self):
        return self._paths

    def legend_elements(self, prop="colors", num="auto",
                        fmt=None, func=lambda x: x, **kwargs):
        """
        Create legend handles and labels for a PathCollection.

        Each legend handle is a `.Line2D` representing the Path that was drawn,
        and each label is a string that represents the Path.

        This is useful for obtaining a legend for a `~.Axes.scatter` plot;
        e.g.::

            scatter = plt.scatter([1, 2, 3],  [4, 5, 6],  c=[7, 2, 3], num=None)
            plt.legend(*scatter.legend_elements())

        creates three legend elements, one for each color with the numerical
        values passed to *c* as the labels.

        Also see the :ref:`automatedlegendcreation` example.

        Parameters
        ----------
        prop : {"colors", "sizes"}, default: "colors"
            If "colors", the legend handles will show the different colors of
            the collection. If "sizes", the legend will show the different
            sizes. To set both, use *kwargs* to directly edit the `.Line2D`
            properties.
        num : int, None, "auto" (default), array-like, or `~.ticker.Locator`
            Target number of elements to create.
            If None, use all unique elements of the mappable array. If an
            integer, target to use *num* elements in the normed range.
            If *"auto"*, try to determine which option better suits the nature
            of the data.
            The number of created elements may slightly deviate from *num* due
            to a `~.ticker.Locator` being used to find useful locations.
            If a list or array, use exactly those elements for the legend.
            Finally, a `~.ticker.Locator` can be provided.
        fmt : str, `~matplotlib.ticker.Formatter`, or None (default)
            The format or formatter to use for the labels. If a string must be
            a valid input for a `.StrMethodFormatter`. If None (the default),
            use a `.ScalarFormatter`.
        func : function, default: ``lambda x: x``
            Function to calculate the labels.  Often the size (or color)
            argument to `~.Axes.scatter` will have been pre-processed by the
            user using a function ``s = f(x)`` to make the markers visible;
            e.g. ``size = np.log10(x)``.  Providing the inverse of this
            function here allows that pre-processing to be inverted, so that
            the legend labels have the correct values; e.g. ``func = lambda
            x: 10**x``.
        **kwargs
            Allowed keyword arguments are *color* and *size*. E.g. it may be
            useful to set the color of the markers if *prop="sizes"* is used;
            similarly to set the size of the markers if *prop="colors"* is
            used. Any further parameters are passed onto the `.Line2D`
            instance. This may be useful to e.g. specify a different
            *markeredgecolor* or *alpha* for the legend handles.

        Returns
        -------
        handles : list of `.Line2D`
            Visual representation of each element of the legend.
        labels : list of str
            The string labels for elements of the legend.
        """
        handles = []
        labels = []
        hasarray = self.get_array() is not None
        if fmt is None:
            fmt = mpl.ticker.ScalarFormatter(useOffset=False, useMathText=True)
        elif isinstance(fmt, str):
            fmt = mpl.ticker.StrMethodFormatter(fmt)
        fmt.create_dummy_axis()

        if prop == "colors":
            if not hasarray:
                warnings.warn("Collection without array used. Make sure to "
                              "specify the values to be colormapped via the "
                              "`c` argument.")
                return handles, labels
            u = np.unique(self.get_array())
            size = kwargs.pop("size", mpl.rcParams["lines.markersize"])
        elif prop == "sizes":
            u = np.unique(self.get_sizes())
            color = kwargs.pop("color", "k")
        else:
            raise ValueError("Valid values for `prop` are 'colors' or "
                             f"'sizes'. You supplied '{prop}' instead.")

        fu = func(u)
        fmt.axis.set_view_interval(fu.min(), fu.max())
        fmt.axis.set_data_interval(fu.min(), fu.max())
        if num == "auto":
            num = 9
            if len(u) <= num:
                num = None
        if num is None:
            values = u
            label_values = func(values)
        else:
            if prop == "colors":
                arr = self.get_array()
            elif prop == "sizes":
                arr = self.get_sizes()
            if isinstance(num, mpl.ticker.Locator):
                loc = num
            elif np.iterable(num):
                loc = mpl.ticker.FixedLocator(num)
            else:
                num = int(num)
                loc = mpl.ticker.MaxNLocator(nbins=num, min_n_ticks=num-1,
                                             steps=[1, 2, 2.5, 3, 5, 6, 8, 10])
            label_values = loc.tick_values(func(arr).min(), func(arr).max())
            cond = ((label_values >= func(arr).min()) &
                    (label_values <= func(arr).max()))
            label_values = label_values[cond]
            yarr = np.linspace(arr.min(), arr.max(), 256)
            xarr = func(yarr)
            ix = np.argsort(xarr)
            values = np.interp(label_values, xarr[ix], yarr[ix])

        kw = {"markeredgewidth": self.get_linewidths()[0],
              "alpha": self.get_alpha(),
              **kwargs}

        for val, lab in zip(values, label_values):
            if prop == "colors":
                color = self.cmap(self.norm(val))
            elif prop == "sizes":
                size = np.sqrt(val)
                if np.isclose(size, 0.0):
                    continue
            h = mlines.Line2D([0], [0], ls="", color=color, ms=size,
                              marker=self.get_paths()[0], **kw)
            handles.append(h)
            if hasattr(fmt, "set_locs"):
                fmt.set_locs(label_values)
            l = fmt(lab)
            labels.append(l)

        return handles, labels


class PolyCollection(_CollectionWithSizes):

    def __init__(self, verts, sizes=None, *, closed=True, **kwargs):
        """
        Parameters
        ----------
        verts : list of array-like
            The sequence of polygons [*verts0*, *verts1*, ...] where each
            element *verts_i* defines the vertices of polygon *i* as a 2D
            array-like of shape (M, 2).
        sizes : array-like, default: None
            Squared scaling factors for the polygons. The coordinates of each
            polygon *verts_i* are multiplied by the square-root of the
            corresponding entry in *sizes* (i.e., *sizes* specify the scaling
            of areas). The scaling is applied before the Artist master
            transform.
        closed : bool, default: True
            Whether the polygon should be closed by adding a CLOSEPOLY
            connection at the end.
        **kwargs
            Forwarded to `.Collection`.
        """
        super().__init__(**kwargs)
        self.set_sizes(sizes)
        self.set_verts(verts, closed)
        self.stale = True

    def set_verts(self, verts, closed=True):
        """
        Set the vertices of the polygons.

        Parameters
        ----------
        verts : list of array-like
            The sequence of polygons [*verts0*, *verts1*, ...] where each
            element *verts_i* defines the vertices of polygon *i* as a 2D
            array-like of shape (M, 2).
        closed : bool, default: True
            Whether the polygon should be closed by adding a CLOSEPOLY
            connection at the end.
        """
        self.stale = True
        if isinstance(verts, np.ma.MaskedArray):
            verts = verts.astype(float).filled(np.nan)

        # No need to do anything fancy if the path isn't closed.
        if not closed:
            self._paths = [mpath.Path(xy) for xy in verts]
            return

        # Fast path for arrays
        if isinstance(verts, np.ndarray) and len(verts.shape) == 3:
            verts_pad = np.concatenate((verts, verts[:, :1]), axis=1)
            # Creating the codes once is much faster than having Path do it
            # separately each time by passing closed=True.
            codes = np.empty(verts_pad.shape[1], dtype=mpath.Path.code_type)
            codes[:] = mpath.Path.LINETO
            codes[0] = mpath.Path.MOVETO
            codes[-1] = mpath.Path.CLOSEPOLY
            self._paths = [mpath.Path(xy, codes) for xy in verts_pad]
            return

        self._paths = []
        for xy in verts:
            if len(xy):
                self._paths.append(mpath.Path._create_closed(xy))
            else:
                self._paths.append(mpath.Path(xy))

    set_paths = set_verts

    def set_verts_and_codes(self, verts, codes):
        """Initialize vertices with path codes."""
        if len(verts) != len(codes):
            raise ValueError("'codes' must be a 1D list or array "
                             "with the same length of 'verts'")
        self._paths = [mpath.Path(xy, cds) if len(xy) else mpath.Path(xy)
                       for xy, cds in zip(verts, codes)]
        self.stale = True


class FillBetweenPolyCollection(PolyCollection):
    """
    `.PolyCollection` that fills the area between two x- or y-curves.
    """
    def __init__(
            self, t_direction, t, f1, f2, *,
            where=None, interpolate=False, step=None, **kwargs):
        """
        Parameters
        ----------
        t_direction : {{'x', 'y'}}
            The axes on which the variable lies.

            - 'x': the curves are ``(t, f1)`` and ``(t, f2)``.
            - 'y': the curves are ``(f1, t)`` and ``(f2, t)``.

        t : array-like
            The ``t_direction`` coordinates of the nodes defining the curves.

        f1 : array-like or float
            The other coordinates of the nodes defining the first curve.

        f2 : array-like or float
            The other coordinates of the nodes defining the second curve.

        where : array-like of bool, optional
            Define *where* to exclude some {dir} regions from being filled.
            The filled regions are defined by the coordinates ``t[where]``.
            More precisely, fill between ``t[i]`` and ``t[i+1]`` if
            ``where[i] and where[i+1]``.  Note that this definition implies
            that an isolated *True* value between two *False* values in *where*
            will not result in filling.  Both sides of the *True* position
            remain unfilled due to the adjacent *False* values.

        interpolate : bool, default: False
            This option is only relevant if *where* is used and the two curves
            are crossing each other.

            Semantically, *where* is often used for *f1* > *f2* or
            similar.  By default, the nodes of the polygon defining the filled
            region will only be placed at the positions in the *t* array.
            Such a polygon cannot describe the above semantics close to the
            intersection.  The t-sections containing the intersection are
            simply clipped.

            Setting *interpolate* to *True* will calculate the actual
            intersection point and extend the filled region up to this point.

        step : {{'pre', 'post', 'mid'}}, optional
            Define *step* if the filling should be a step function,
            i.e. constant in between *t*.  The value determines where the
            step will occur:

            - 'pre': The f value is continued constantly to the left from
              every *t* position, i.e. the interval ``(t[i-1], t[i]]`` has the
              value ``f[i]``.
            - 'post': The y value is continued constantly to the right from
              every *x* position, i.e. the interval ``[t[i], t[i+1])`` has the
              value ``f[i]``.
            - 'mid': Steps occur half-way between the *t* positions.

        **kwargs
            Forwarded to `.PolyCollection`.

        See Also
        --------
        .Axes.fill_between, .Axes.fill_betweenx
        """
        self.t_direction = t_direction
        self._interpolate = interpolate
        self._step = step
        verts = self._make_verts(t, f1, f2, where)
        super().__init__(verts, **kwargs)

    @staticmethod
    def _f_dir_from_t(t_direction):
        """The direction that is other than `t_direction`."""
        if t_direction == "x":
            return "y"
        elif t_direction == "y":
            return "x"
        else:
            msg = f"t_direction must be 'x' or 'y', got {t_direction!r}"
            raise ValueError(msg)

    @property
    def _f_direction(self):
        """The direction that is other than `self.t_direction`."""
        return self._f_dir_from_t(self.t_direction)

    def set_data(self, t, f1, f2, *, where=None):
        """
        Set new values for the two bounding curves.

        Parameters
        ----------
        t : array-like
            The ``self.t_direction`` coordinates of the nodes defining the curves.

        f1 : array-like or float
            The other coordinates of the nodes defining the first curve.

        f2 : array-like or float
            The other coordinates of the nodes defining the second curve.

        where : array-like of bool, optional
            Define *where* to exclude some {dir} regions from being filled.
            The filled regions are defined by the coordinates ``t[where]``.
            More precisely, fill between ``t[i]`` and ``t[i+1]`` if
            ``where[i] and where[i+1]``.  Note that this definition implies
            that an isolated *True* value between two *False* values in *where*
            will not result in filling.  Both sides of the *True* position
            remain unfilled due to the adjacent *False* values.

        See Also
        --------
        .PolyCollection.set_verts, .Line2D.set_data
        """
        t, f1, f2 = self.axes._fill_between_process_units(
            self.t_direction, self._f_direction, t, f1, f2)

        verts = self._make_verts(t, f1, f2, where)
        self.set_verts(verts)

    def get_datalim(self, transData):
        """Calculate the data limits and return them as a `.Bbox`."""
        datalim = transforms.Bbox.null()
        datalim.update_from_data_xy((self.get_transform() - transData).transform(
            np.concatenate([self._bbox, [self._bbox.minpos]])))
        return datalim

    def _make_verts(self, t, f1, f2, where):
        """
        Make verts that can be forwarded to `.PolyCollection`.
        """
        self._validate_shapes(self.t_direction, self._f_direction, t, f1, f2)

        where = self._get_data_mask(t, f1, f2, where)
        t, f1, f2 = np.broadcast_arrays(np.atleast_1d(t), f1, f2, subok=True)

        self._bbox = transforms.Bbox.null()
        self._bbox.update_from_data_xy(self._fix_pts_xy_order(np.concatenate([
            np.stack((t[where], f[where]), axis=-1) for f in (f1, f2)])))

        return [
            self._make_verts_for_region(t, f1, f2, idx0, idx1)
            for idx0, idx1 in cbook.contiguous_regions(where)
        ]

    def _get_data_mask(self, t, f1, f2, where):
        """
        Return a bool array, with True at all points that should eventually be rendered.

        The array is True at a point if none of the data inputs
        *t*, *f1*, *f2* is masked and if the input *where* is true at that point.
        """
        if where is None:
            where = True
        else:
            where = np.asarray(where, dtype=bool)
            if where.size != t.size:
                msg = "where size ({}) does not match {!r} size ({})".format(
                    where.size, self.t_direction, t.size)
                raise ValueError(msg)
        return where & ~functools.reduce(
            np.logical_or, map(np.ma.getmaskarray, [t, f1, f2]))

    @staticmethod
    def _validate_shapes(t_dir, f_dir, t, f1, f2):
        """Validate that t, f1 and f2 are 1-dimensional and have the same length."""
        names = (d + s for d, s in zip((t_dir, f_dir, f_dir), ("", "1", "2")))
        for name, array in zip(names, [t, f1, f2]):
            if array.ndim > 1:
                raise ValueError(f"{name!r} is not 1-dimensional")
            if t.size > 1 and array.size > 1 and t.size != array.size:
                msg = "{!r} has size {}, but {!r} has an unequal size of {}".format(
                    t_dir, t.size, name, array.size)
                raise ValueError(msg)

    def _make_verts_for_region(self, t, f1, f2, idx0, idx1):
        """
        Make ``verts`` for a contiguous region between ``idx0`` and ``idx1``, taking
        into account ``step`` and ``interpolate``.
        """
        t_slice = t[idx0:idx1]
        f1_slice = f1[idx0:idx1]
        f2_slice = f2[idx0:idx1]
        if self._step is not None:
            step_func = cbook.STEP_LOOKUP_MAP["steps-" + self._step]
            t_slice, f1_slice, f2_slice = step_func(t_slice, f1_slice, f2_slice)

        if self._interpolate:
            start = self._get_interpolating_points(t, f1, f2, idx0)
            end = self._get_interpolating_points(t, f1, f2, idx1)
        else:
            # Handle scalar f2 (e.g. 0): the fill should go all
            # the way down to 0 even if none of the dep1 sample points do.
            start = t_slice[0], f2_slice[0]
            end = t_slice[-1], f2_slice[-1]

        pts = np.concatenate((
            np.asarray([start]),
            np.stack((t_slice, f1_slice), axis=-1),
            np.asarray([end]),
            np.stack((t_slice, f2_slice), axis=-1)[::-1]))

        return self._fix_pts_xy_order(pts)

    @classmethod
    def _get_interpolating_points(cls, t, f1, f2, idx):
        """Calculate interpolating points."""
        im1 = max(idx - 1, 0)
        t_values = t[im1:idx+1]
        diff_values = f1[im1:idx+1] - f2[im1:idx+1]
        f1_values = f1[im1:idx+1]

        if len(diff_values) == 2:
            if np.ma.is_masked(diff_values[1]):
                return t[im1], f1[im1]
            elif np.ma.is_masked(diff_values[0]):
                return t[idx], f1[idx]

        diff_root_t = cls._get_diff_root(0, diff_values, t_values)
        diff_root_f = cls._get_diff_root(diff_root_t, t_values, f1_values)
        return diff_root_t, diff_root_f

    @staticmethod
    def _get_diff_root(x, xp, fp):
        """Calculate diff root."""
        order = xp.argsort()
        return np.interp(x, xp[order], fp[order])

    def _fix_pts_xy_order(self, pts):
        """
        Fix pts calculation results with `self.t_direction`.

        In the workflow, it is assumed that `self.t_direction` is 'x'. If this
        is not true, we need to exchange the coordinates.
        """
        return pts[:, ::-1] if self.t_direction == "y" else pts


class RegularPolyCollection(_CollectionWithSizes):
    """A collection of n-sided regular polygons."""

    _path_generator = mpath.Path.unit_regular_polygon
    _factor = np.pi ** (-1/2)

    def __init__(self,
                 numsides,
                 *,
                 rotation=0,
                 sizes=(1,),
                 **kwargs):
        """
        Parameters
        ----------
        numsides : int
            The number of sides of the polygon.
        rotation : float
            The rotation of the polygon in radians.
        sizes : tuple of float
            The area of the circle circumscribing the polygon in points^2.
        **kwargs
            Forwarded to `.Collection`.

        Examples
        --------
        See :doc:`/gallery/event_handling/lasso_demo` for a complete example::

            offsets = np.random.rand(20, 2)
            facecolors = [cm.jet(x) for x in np.random.rand(20)]

            collection = RegularPolyCollection(
                numsides=5, # a pentagon
                rotation=0, sizes=(50,),
                facecolors=facecolors,
                edgecolors=("black",),
                linewidths=(1,),
                offsets=offsets,
                offset_transform=ax.transData,
                )
        """
        super().__init__(**kwargs)
        self.set_sizes(sizes)
        self._numsides = numsides
        self._paths = [self._path_generator(numsides)]
        self._rotation = rotation
        self.set_transform(transforms.IdentityTransform())

    def get_numsides(self):
        return self._numsides

    def get_rotation(self):
        return self._rotation

    @artist.allow_rasterization
    def draw(self, renderer):
        self.set_sizes(self._sizes, self.get_figure(root=True).dpi)
        self._transforms = [
            transforms.Affine2D(x).rotate(-self._rotation).get_matrix()
            for x in self._transforms
        ]
        # Explicitly not super().draw, because set_sizes must be called before
        # updating self._transforms.
        Collection.draw(self, renderer)


class StarPolygonCollection(RegularPolyCollection):
    """Draw a collection of regular stars with *numsides* points."""
    _path_generator = mpath.Path.unit_regular_star


class AsteriskPolygonCollection(RegularPolyCollection):
    """Draw a collection of regular asterisks with *numsides* points."""
    _path_generator = mpath.Path.unit_regular_asterisk


class LineCollection(Collection):
    r"""
    Represents a sequence of `.Line2D`\s that should be drawn together.

    This class extends `.Collection` to represent a sequence of
    `.Line2D`\s instead of just a sequence of `.Patch`\s.
    Just as in `.Collection`, each property of a *LineCollection* may be either
    a single value or a list of values. This list is then used cyclically for
    each element of the LineCollection, so the property of the ``i``\th element
    of the collection is::

      prop[i % len(prop)]

    The properties of each member of a *LineCollection* default to their values
    in :rc:`lines.*` instead of :rc:`patch.*`, and the property *colors* is
    added in place of *edgecolors*.
    """

    _edge_default = True

    def __init__(self, segments,  # Can be None.
                 *,
                 zorder=2,        # Collection.zorder is 1
                 **kwargs
                 ):
        """
        Parameters
        ----------
        segments : list of (N, 2) array-like
            A sequence ``[line0, line1, ...]`` where each line is a (N, 2)-shape
            array-like containing points::

                line0 = [(x0, y0), (x1, y1), ...]

            Each line can contain a different number of points.
        linewidths : float or list of float, default: :rc:`lines.linewidth`
            The width of each line in points.
        colors : :mpltype:`color` or list of color, default: :rc:`lines.color`
            A sequence of RGBA tuples (e.g., arbitrary color strings, etc, not
            allowed).
        antialiaseds : bool or list of bool, default: :rc:`lines.antialiased`
            Whether to use antialiasing for each line.
        zorder : float, default: 2
            zorder of the lines once drawn.

        facecolors : :mpltype:`color` or list of :mpltype:`color`, default: 'none'
            When setting *facecolors*, each line is interpreted as a boundary
            for an area, implicitly closing the path from the last point to the
            first point. The enclosed area is filled with *facecolor*.
            In order to manually specify what should count as the "interior" of
            each line, please use `.PathCollection` instead, where the
            "interior" can be specified by appropriate usage of
            `~.path.Path.CLOSEPOLY`.

        **kwargs
            Forwarded to `.Collection`.
        """
        # Unfortunately, mplot3d needs this explicit setting of 'facecolors'.
        kwargs.setdefault('facecolors', 'none')
        super().__init__(
            zorder=zorder,
            **kwargs)
        self.set_segments(segments)

    def set_segments(self, segments):
        if segments is None:
            return

        self._paths = [mpath.Path(seg) if isinstance(seg, np.ma.MaskedArray)
                       else mpath.Path(np.asarray(seg, float))
                       for seg in segments]
        self.stale = True

    set_verts = set_segments  # for compatibility with PolyCollection
    set_paths = set_segments

    def get_segments(self):
        """
        Returns
        -------
        list
            List of segments in the LineCollection. Each list item contains an
            array of vertices.
        """
        segments = []

        for path in self._paths:
            vertices = [
                vertex
                for vertex, _
                # Never simplify here, we want to get the data-space values
                # back and there in no way to know the "right" simplification
                # threshold so never try.
                in path.iter_segments(simplify=False)
            ]
            vertices = np.asarray(vertices)
            segments.append(vertices)

        return segments

    def _get_default_linewidth(self):
        return mpl.rcParams['lines.linewidth']

    def _get_default_antialiased(self):
        return mpl.rcParams['lines.antialiased']

    def _get_default_edgecolor(self):
        return mpl.rcParams['lines.color']

    def _get_default_facecolor(self):
        return 'none'

    def set_alpha(self, alpha):
        # docstring inherited
        super().set_alpha(alpha)
        if self._gapcolor is not None:
            self.set_gapcolor(self._original_gapcolor)

    def set_color(self, c):
        """
        Set the edgecolor(s) of the LineCollection.

        Parameters
        ----------
        c : :mpltype:`color` or list of :mpltype:`color`
            Single color (all lines have same color), or a
            sequence of RGBA tuples; if it is a sequence the lines will
            cycle through the sequence.
        """
        self.set_edgecolor(c)

    set_colors = set_color

    def get_color(self):
        return self._edgecolors

    get_colors = get_color  # for compatibility with old versions

    def set_gapcolor(self, gapcolor):
        """
        Set a color to fill the gaps in the dashed line style.

        .. note::

            Striped lines are created by drawing two interleaved dashed lines.
            There can be overlaps between those two, which may result in
            artifacts when using transparency.

            This functionality is experimental and may change.

        Parameters
        ----------
        gapcolor : :mpltype:`color` or list of :mpltype:`color` or None
            The color with which to fill the gaps. If None, the gaps are
            unfilled.
        """
        self._original_gapcolor = gapcolor
        self._set_gapcolor(gapcolor)

    def _set_gapcolor(self, gapcolor):
        if gapcolor is not None:
            gapcolor = mcolors.to_rgba_array(gapcolor, self._alpha)
        self._gapcolor = gapcolor
        self.stale = True

    def get_gapcolor(self):
        return self._gapcolor

    def _get_inverse_paths_linestyles(self):
        """
        Returns the path and pattern for the gaps in the non-solid lines.

        This path and pattern is the inverse of the path and pattern used to
        construct the non-solid lines. For solid lines, we set the inverse path
        to nans to prevent drawing an inverse line.
        """
        path_patterns = [
            (mpath.Path(np.full((1, 2), np.nan)), ls)
            if ls == (0, None) else
            (path, mlines._get_inverse_dash_pattern(*ls))
            for (path, ls) in
            zip(self._paths, itertools.cycle(self._linestyles))]

        return zip(*path_patterns)


class EventCollection(LineCollection):
    """
    A collection of locations along a single axis at which an "event" occurred.

    The events are given by a 1-dimensional array. They do not have an
    amplitude and are displayed as parallel lines.
    """

    _edge_default = True

    def __init__(self,
                 positions,  # Cannot be None.
                 orientation='horizontal',
                 *,
                 lineoffset=0,
                 linelength=1,
                 linewidth=None,
                 color=None,
                 linestyle='solid',
                 antialiased=None,
                 **kwargs
                 ):
        """
        Parameters
        ----------
        positions : 1D array-like
            Each value is an event.
        orientation : {'horizontal', 'vertical'}, default: 'horizontal'
            The sequence of events is plotted along this direction.
            The marker lines of the single events are along the orthogonal
            direction.
        lineoffset : float, default: 0
            The offset of the center of the markers from the origin, in the
            direction orthogonal to *orientation*.
        linelength : float, default: 1
            The total height of the marker (i.e. the marker stretches from
            ``lineoffset - linelength/2`` to ``lineoffset + linelength/2``).
        linewidth : float or list thereof, default: :rc:`lines.linewidth`
            The line width of the event lines, in points.
        color : :mpltype:`color` or list of :mpltype:`color`, default: :rc:`lines.color`
            The color of the event lines.
        linestyle : str or tuple or list thereof, default: 'solid'
            Valid strings are ['solid', 'dashed', 'dashdot', 'dotted',
            '-', '--', '-.', ':']. Dash tuples should be of the form::

                (offset, onoffseq),

            where *onoffseq* is an even length tuple of on and off ink
            in points.
        antialiased : bool or list thereof, default: :rc:`lines.antialiased`
            Whether to use antialiasing for drawing the lines.
        **kwargs
            Forwarded to `.LineCollection`.

        Examples
        --------
        .. plot:: gallery/lines_bars_and_markers/eventcollection_demo.py
        """
        super().__init__([],
                         linewidths=linewidth, linestyles=linestyle,
                         colors=color, antialiaseds=antialiased,
                         **kwargs)
        self._is_horizontal = True  # Initial value, may be switched below.
        self._linelength = linelength
        self._lineoffset = lineoffset
        self.set_orientation(orientation)
        self.set_positions(positions)

    def get_positions(self):
        """
        Return an array containing the floating-point values of the positions.
        """
        pos = 0 if self.is_horizontal() else 1
        return [segment[0, pos] for segment in self.get_segments()]

    def set_positions(self, positions):
        """Set the positions of the events."""
        if positions is None:
            positions = []
        if np.ndim(positions) != 1:
            raise ValueError('positions must be one-dimensional')
        lineoffset = self.get_lineoffset()
        linelength = self.get_linelength()
        pos_idx = 0 if self.is_horizontal() else 1
        segments = np.empty((len(positions), 2, 2))
        segments[:, :, pos_idx] = np.sort(positions)[:, None]
        segments[:, 0, 1 - pos_idx] = lineoffset + linelength / 2
        segments[:, 1, 1 - pos_idx] = lineoffset - linelength / 2
        self.set_segments(segments)

    def add_positions(self, position):
        """Add one or more events at the specified positions."""
        if position is None or (hasattr(position, 'len') and
                                len(position) == 0):
            return
        positions = self.get_positions()
        positions = np.hstack([positions, np.asanyarray(position)])
        self.set_positions(positions)
    extend_positions = append_positions = add_positions

    def is_horizontal(self):
        """True if the eventcollection is horizontal, False if vertical."""
        return self._is_horizontal

    def get_orientation(self):
        """
        Return the orientation of the event line ('horizontal' or 'vertical').
        """
        return 'horizontal' if self.is_horizontal() else 'vertical'

    def switch_orientation(self):
        """
        Switch the orientation of the event line, either from vertical to
        horizontal or vice versus.
        """
        segments = self.get_segments()
        for i, segment in enumerate(segments):
            segments[i] = np.fliplr(segment)
        self.set_segments(segments)
        self._is_horizontal = not self.is_horizontal()
        self.stale = True

    def set_orientation(self, orientation):
        """
        Set the orientation of the event line.

        Parameters
        ----------
        orientation : {'horizontal', 'vertical'}
        """
        is_horizontal = _api.check_getitem(
            {"horizontal": True, "vertical": False},
            orientation=orientation)
        if is_horizontal == self.is_horizontal():
            return
        self.switch_orientation()

    def get_linelength(self):
        """Return the length of the lines used to mark each event."""
        return self._linelength

    def set_linelength(self, linelength):
        """Set the length of the lines used to mark each event."""
        if linelength == self.get_linelength():
            return
        lineoffset = self.get_lineoffset()
        segments = self.get_segments()
        pos = 1 if self.is_horizontal() else 0
        for segment in segments:
            segment[0, pos] = lineoffset + linelength / 2.
            segment[1, pos] = lineoffset - linelength / 2.
        self.set_segments(segments)
        self._linelength = linelength

    def get_lineoffset(self):
        """Return the offset of the lines used to mark each event."""
        return self._lineoffset

    def set_lineoffset(self, lineoffset):
        """Set the offset of the lines used to mark each event."""
        if lineoffset == self.get_lineoffset():
            return
        linelength = self.get_linelength()
        segments = self.get_segments()
        pos = 1 if self.is_horizontal() else 0
        for segment in segments:
            segment[0, pos] = lineoffset + linelength / 2.
            segment[1, pos] = lineoffset - linelength / 2.
        self.set_segments(segments)
        self._lineoffset = lineoffset

    def get_linewidth(self):
        """Get the width of the lines used to mark each event."""
        return super().get_linewidth()[0]

    def get_linewidths(self):
        return super().get_linewidth()

    def get_color(self):
        """Return the color of the lines used to mark each event."""
        return self.get_colors()[0]


class CircleCollection(_CollectionWithSizes):
    """A collection of circles, drawn using splines."""

    _factor = np.pi ** (-1/2)

    def __init__(self, sizes, **kwargs):
        """
        Parameters
        ----------
        sizes : float or array-like
            The area of each circle in points^2.
        **kwargs
            Forwarded to `.Collection`.
        """
        super().__init__(**kwargs)
        self.set_sizes(sizes)
        self.set_transform(transforms.IdentityTransform())
        self._paths = [mpath.Path.unit_circle()]


class EllipseCollection(Collection):
    """A collection of ellipses, drawn using splines."""

    def __init__(self, widths, heights, angles, *, units='points', **kwargs):
        """
        Parameters
        ----------
        widths : array-like
            The lengths of the first axes (e.g., major axis lengths).
        heights : array-like
            The lengths of second axes.
        angles : array-like
            The angles of the first axes, degrees CCW from the x-axis.
        units : {'points', 'inches', 'dots', 'width', 'height', 'x', 'y', 'xy'}
            The units in which majors and minors are given; 'width' and
            'height' refer to the dimensions of the axes, while 'x' and 'y'
            refer to the *offsets* data units. 'xy' differs from all others in
            that the angle as plotted varies with the aspect ratio, and equals
            the specified angle only when the aspect ratio is unity.  Hence
            it behaves the same as the `~.patches.Ellipse` with
            ``axes.transData`` as its transform.
        **kwargs
            Forwarded to `Collection`.
        """
        super().__init__(**kwargs)
        self.set_widths(widths)
        self.set_heights(heights)
        self.set_angles(angles)
        self._units = units
        self.set_transform(transforms.IdentityTransform())
        self._transforms = np.empty((0, 3, 3))
        self._paths = [mpath.Path.unit_circle()]

    def _set_transforms(self):
        """Calculate transforms immediately before drawing."""

        ax = self.axes
        fig = self.get_figure(root=False)

        if self._units == 'xy':
            sc = 1
        elif self._units == 'x':
            sc = ax.bbox.width / ax.viewLim.width
        elif self._units == 'y':
            sc = ax.bbox.height / ax.viewLim.height
        elif self._units == 'inches':
            sc = fig.dpi
        elif self._units == 'points':
            sc = fig.dpi / 72.0
        elif self._units == 'width':
            sc = ax.bbox.width
        elif self._units == 'height':
            sc = ax.bbox.height
        elif self._units == 'dots':
            sc = 1.0
        else:
            raise ValueError(f'Unrecognized units: {self._units!r}')

        self._transforms = np.zeros((len(self._widths), 3, 3))
        widths = self._widths * sc
        heights = self._heights * sc
        sin_angle = np.sin(self._angles)
        cos_angle = np.cos(self._angles)
        self._transforms[:, 0, 0] = widths * cos_angle
        self._transforms[:, 0, 1] = heights * -sin_angle
        self._transforms[:, 1, 0] = widths * sin_angle
        self._transforms[:, 1, 1] = heights * cos_angle
        self._transforms[:, 2, 2] = 1.0

        _affine = transforms.Affine2D
        if self._units == 'xy':
            m = ax.transData.get_affine().get_matrix().copy()
            m[:2, 2:] = 0
            self.set_transform(_affine(m))

    def set_widths(self, widths):
        """Set the lengths of the first axes (e.g., major axis)."""
        self._widths = 0.5 * np.asarray(widths).ravel()
        self.stale = True

    def set_heights(self, heights):
        """Set the lengths of second axes (e.g., minor axes)."""
        self._heights = 0.5 * np.asarray(heights).ravel()
        self.stale = True

    def set_angles(self, angles):
        """Set the angles of the first axes, degrees CCW from the x-axis."""
        self._angles = np.deg2rad(angles).ravel()
        self.stale = True

    def get_widths(self):
        """Get the lengths of the first axes (e.g., major axis)."""
        return self._widths * 2

    def get_heights(self):
        """Set the lengths of second axes (e.g., minor axes)."""
        return self._heights * 2

    def get_angles(self):
        """Get the angles of the first axes, degrees CCW from the x-axis."""
        return np.rad2deg(self._angles)

    @artist.allow_rasterization
    def draw(self, renderer):
        self._set_transforms()
        super().draw(renderer)


class PatchCollection(Collection):
    """
    A generic collection of patches.

    PatchCollection draws faster than a large number of equivalent individual
    Patches. It also makes it easier to assign a colormap to a heterogeneous
    collection of patches.
    """

    def __init__(self, patches, *, match_original=False, **kwargs):
        """
        Parameters
        ----------
        patches : list of `.Patch`
            A sequence of Patch objects.  This list may include
            a heterogeneous assortment of different patch types.

        match_original : bool, default: False
            If True, use the colors and linewidths of the original
            patches.  If False, new colors may be assigned by
            providing the standard collection arguments, facecolor,
            edgecolor, linewidths, norm or cmap.

        **kwargs
            All other parameters are forwarded to `.Collection`.

            If any of *edgecolors*, *facecolors*, *linewidths*, *antialiaseds*
            are None, they default to their `.rcParams` patch setting, in
            sequence form.

        Notes
        -----
        The use of `~matplotlib.cm.ScalarMappable` functionality is optional.
        If the `~matplotlib.cm.ScalarMappable` matrix ``_A`` has been set (via
        a call to `~.ScalarMappable.set_array`), at draw time a call to scalar
        mappable will be made to set the face colors.
        """

        if match_original:
            def determine_facecolor(patch):
                if patch.get_fill():
                    return patch.get_facecolor()
                return [0, 0, 0, 0]

            kwargs['facecolors'] = [determine_facecolor(p) for p in patches]
            kwargs['edgecolors'] = [p.get_edgecolor() for p in patches]
            kwargs['linewidths'] = [p.get_linewidth() for p in patches]
            kwargs['linestyles'] = [p.get_linestyle() for p in patches]
            kwargs['antialiaseds'] = [p.get_antialiased() for p in patches]

        super().__init__(**kwargs)

        self.set_paths(patches)

    def set_paths(self, patches):
        paths = [p.get_transform().transform_path(p.get_path())
                 for p in patches]
        self._paths = paths


class TriMesh(Collection):
    """
    Class for the efficient drawing of a triangular mesh using Gouraud shading.

    A triangular mesh is a `~matplotlib.tri.Triangulation` object.
    """
    def __init__(self, triangulation, **kwargs):
        super().__init__(**kwargs)
        self._triangulation = triangulation
        self._shading = 'gouraud'

        self._bbox = transforms.Bbox.unit()

        # Unfortunately this requires a copy, unless Triangulation
        # was rewritten.
        xy = np.hstack((triangulation.x.reshape(-1, 1),
                        triangulation.y.reshape(-1, 1)))
        self._bbox.update_from_data_xy(xy)

    def get_paths(self):
        if self._paths is None:
            self.set_paths()
        return self._paths

    def set_paths(self):
        self._paths = self.convert_mesh_to_paths(self._triangulation)

    @staticmethod
    def convert_mesh_to_paths(tri):
        """
        Convert a given mesh into a sequence of `.Path` objects.

        This function is primarily of use to implementers of backends that do
        not directly support meshes.
        """
        triangles = tri.get_masked_triangles()
        verts = np.stack((tri.x[triangles], tri.y[triangles]), axis=-1)
        return [mpath.Path(x) for x in verts]

    @artist.allow_rasterization
    def draw(self, renderer):
        if not self.get_visible():
            return
        renderer.open_group(self.__class__.__name__, gid=self.get_gid())
        transform = self.get_transform()

        # Get a list of triangles and the color at each vertex.
        tri = self._triangulation
        triangles = tri.get_masked_triangles()

        verts = np.stack((tri.x[triangles], tri.y[triangles]), axis=-1)

        self.update_scalarmappable()
        colors = self._facecolors[triangles]

        gc = renderer.new_gc()
        self._set_gc_clip(gc)
        gc.set_linewidth(self.get_linewidth()[0])
        renderer.draw_gouraud_triangles(gc, verts, colors, transform.frozen())
        gc.restore()
        renderer.close_group(self.__class__.__name__)


class _MeshData:
    r"""
    Class for managing the two dimensional coordinates of Quadrilateral meshes
    and the associated data with them. This class is a mixin and is intended to
    be used with another collection that will implement the draw separately.

    A quadrilateral mesh is a grid of M by N adjacent quadrilaterals that are
    defined via a (M+1, N+1) grid of vertices. The quadrilateral (m, n) is
    defined by the vertices ::

               (m+1, n) ----------- (m+1, n+1)
                  /                   /
                 /                 /
                /               /
            (m, n) -------- (m, n+1)

    The mesh need not be regular and the polygons need not be convex.

    Parameters
    ----------
    coordinates : (M+1, N+1, 2) array-like
        The vertices. ``coordinates[m, n]`` specifies the (x, y) coordinates
        of vertex (m, n).

    shading : {'flat', 'gouraud'}, default: 'flat'
    """
    def __init__(self, coordinates, *, shading='flat'):
        _api.check_shape((None, None, 2), coordinates=coordinates)
        self._coordinates = coordinates
        self._shading = shading

    def set_array(self, A):
        """
        Set the data values.

        Parameters
        ----------
        A : array-like
            The mesh data. Supported array shapes are:

            - (M, N) or (M*N,): a mesh with scalar data. The values are mapped
              to colors using normalization and a colormap. See parameters
              *norm*, *cmap*, *vmin*, *vmax*.
            - (M, N, 3): an image with RGB values (0-1 float or 0-255 int).
            - (M, N, 4): an image with RGBA values (0-1 float or 0-255 int),
              i.e. including transparency.

            If the values are provided as a 2D grid, the shape must match the
            coordinates grid. If the values are 1D, they are reshaped to 2D.
            M, N follow from the coordinates grid, where the coordinates grid
            shape is (M, N) for 'gouraud' *shading* and (M+1, N+1) for 'flat'
            shading.
        """
        height, width = self._coordinates.shape[0:-1]
        if self._shading == 'flat':
            h, w = height - 1, width - 1
        else:
            h, w = height, width
        ok_shapes = [(h, w, 3), (h, w, 4), (h, w), (h * w,)]
        if A is not None:
            shape = np.shape(A)
            if shape not in ok_shapes:
                raise ValueError(
                    f"For X ({width}) and Y ({height}) with {self._shading} "
                    f"shading, A should have shape "
                    f"{' or '.join(map(str, ok_shapes))}, not {A.shape}")
        return super().set_array(A)

    def get_coordinates(self):
        """
        Return the vertices of the mesh as an (M+1, N+1, 2) array.

        M, N are the number of quadrilaterals in the rows / columns of the
        mesh, corresponding to (M+1, N+1) vertices.
        The last dimension specifies the components (x, y).
        """
        return self._coordinates

    def get_edgecolor(self):
        # docstring inherited
        # Note that we want to return an array of shape (N*M, 4)
        # a flattened RGBA collection
        return super().get_edgecolor().reshape(-1, 4)

    def get_facecolor(self):
        # docstring inherited
        # Note that we want to return an array of shape (N*M, 4)
        # a flattened RGBA collection
        return super().get_facecolor().reshape(-1, 4)

    @staticmethod
    def _convert_mesh_to_paths(coordinates):
        """
        Convert a given mesh into a sequence of `.Path` objects.

        This function is primarily of use to implementers of backends that do
        not directly support quadmeshes.
        """
        if isinstance(coordinates, np.ma.MaskedArray):
            c = coordinates.data
        else:
            c = coordinates
        points = np.concatenate([
            c[:-1, :-1],
            c[:-1, 1:],
            c[1:, 1:],
            c[1:, :-1],
            c[:-1, :-1]
        ], axis=2).reshape((-1, 5, 2))
        return [mpath.Path(x) for x in points]

    def _convert_mesh_to_triangles(self, coordinates):
        """
        Convert a given mesh into a sequence of triangles, each point
        with its own color.  The result can be used to construct a call to
        `~.RendererBase.draw_gouraud_triangles`.
        """
        if isinstance(coordinates, np.ma.MaskedArray):
            p = coordinates.data
        else:
            p = coordinates

        p_a = p[:-1, :-1]
        p_b = p[:-1, 1:]
        p_c = p[1:, 1:]
        p_d = p[1:, :-1]
        p_center = (p_a + p_b + p_c + p_d) / 4.0
        triangles = np.concatenate([
            p_a, p_b, p_center,
            p_b, p_c, p_center,
            p_c, p_d, p_center,
            p_d, p_a, p_center,
        ], axis=2).reshape((-1, 3, 2))

        c = self.get_facecolor().reshape((*coordinates.shape[:2], 4))
        z = self.get_array()
        mask = z.mask if np.ma.is_masked(z) else None
        if mask is not None:
            c[mask, 3] = np.nan
        c_a = c[:-1, :-1]
        c_b = c[:-1, 1:]
        c_c = c[1:, 1:]
        c_d = c[1:, :-1]
        c_center = (c_a + c_b + c_c + c_d) / 4.0
        colors = np.concatenate([
            c_a, c_b, c_center,
            c_b, c_c, c_center,
            c_c, c_d, c_center,
            c_d, c_a, c_center,
        ], axis=2).reshape((-1, 3, 4))
        tmask = np.isnan(colors[..., 2, 3])
        return triangles[~tmask], colors[~tmask]


class QuadMesh(_MeshData, Collection):
    r"""
    Class for the efficient drawing of a quadrilateral mesh.

    A quadrilateral mesh is a grid of M by N adjacent quadrilaterals that are
    defined via a (M+1, N+1) grid of vertices. The quadrilateral (m, n) is
    defined by the vertices ::

               (m+1, n) ----------- (m+1, n+1)
                  /                   /
                 /                 /
                /               /
            (m, n) -------- (m, n+1)

    The mesh need not be regular and the polygons need not be convex.

    Parameters
    ----------
    coordinates : (M+1, N+1, 2) array-like
        The vertices. ``coordinates[m, n]`` specifies the (x, y) coordinates
        of vertex (m, n).

    antialiased : bool, default: True

    shading : {'flat', 'gouraud'}, default: 'flat'

    Notes
    -----
    Unlike other `.Collection`\s, the default *pickradius* of `.QuadMesh` is 0,
    i.e. `~.Artist.contains` checks whether the test point is within any of the
    mesh quadrilaterals.

    """

    def __init__(self, coordinates, *, antialiased=True, shading='flat',
                 **kwargs):
        kwargs.setdefault("pickradius", 0)
        super().__init__(coordinates=coordinates, shading=shading)
        Collection.__init__(self, **kwargs)

        self._antialiased = antialiased
        self._bbox = transforms.Bbox.unit()
        self._bbox.update_from_data_xy(self._coordinates.reshape(-1, 2))
        self.set_mouseover(False)

    def get_paths(self):
        if self._paths is None:
            self.set_paths()
        return self._paths

    def set_paths(self):
        self._paths = self._convert_mesh_to_paths(self._coordinates)
        self.stale = True

    def get_datalim(self, transData):
        return (self.get_transform() - transData).transform_bbox(self._bbox)

    @artist.allow_rasterization
    def draw(self, renderer):
        if not self.get_visible():
            return
        renderer.open_group(self.__class__.__name__, self.get_gid())
        transform = self.get_transform()
        offset_trf = self.get_offset_transform()
        offsets = self.get_offsets()

        if self.have_units():
            xs = self.convert_xunits(offsets[:, 0])
            ys = self.convert_yunits(offsets[:, 1])
            offsets = np.column_stack([xs, ys])

        self.update_scalarmappable()

        if not transform.is_affine:
            coordinates = self._coordinates.reshape((-1, 2))
            coordinates = transform.transform(coordinates)
            coordinates = coordinates.reshape(self._coordinates.shape)
            transform = transforms.IdentityTransform()
        else:
            coordinates = self._coordinates

        if not offset_trf.is_affine:
            offsets = offset_trf.transform_non_affine(offsets)
            offset_trf = offset_trf.get_affine()

        gc = renderer.new_gc()
        gc.set_snap(self.get_snap())
        self._set_gc_clip(gc)
        gc.set_linewidth(self.get_linewidth()[0])

        if self._shading == 'gouraud':
            triangles, colors = self._convert_mesh_to_triangles(coordinates)
            renderer.draw_gouraud_triangles(
                gc, triangles, colors, transform.frozen())
        else:
            renderer.draw_quad_mesh(
                gc, transform.frozen(),
                coordinates.shape[1] - 1, coordinates.shape[0] - 1,
                coordinates, offsets, offset_trf,
                # Backends expect flattened rgba arrays (n*m, 4) for fc and ec
                self.get_facecolor().reshape((-1, 4)),
                self._antialiased, self.get_edgecolors().reshape((-1, 4)))
        gc.restore()
        renderer.close_group(self.__class__.__name__)
        self.stale = False

    def get_cursor_data(self, event):
        contained, info = self.contains(event)
        if contained and self.get_array() is not None:
            return self.get_array().ravel()[info["ind"]]
        return None


class PolyQuadMesh(_MeshData, PolyCollection):
    """
    Class for drawing a quadrilateral mesh as individual Polygons.

    A quadrilateral mesh is a grid of M by N adjacent quadrilaterals that are
    defined via a (M+1, N+1) grid of vertices. The quadrilateral (m, n) is
    defined by the vertices ::

               (m+1, n) ----------- (m+1, n+1)
                  /                   /
                 /                 /
                /               /
            (m, n) -------- (m, n+1)

    The mesh need not be regular and the polygons need not be convex.

    Parameters
    ----------
    coordinates : (M+1, N+1, 2) array-like
        The vertices. ``coordinates[m, n]`` specifies the (x, y) coordinates
        of vertex (m, n).

    Notes
    -----
    Unlike `.QuadMesh`, this class will draw each cell as an individual Polygon.
    This is significantly slower, but allows for more flexibility when wanting
    to add additional properties to the cells, such as hatching.

    Another difference from `.QuadMesh` is that if any of the vertices or data
    of a cell are masked, that Polygon will **not** be drawn and it won't be in
    the list of paths returned.
    """

    def __init__(self, coordinates, **kwargs):
        super().__init__(coordinates=coordinates)
        PolyCollection.__init__(self, verts=[], **kwargs)
        # Setting the verts updates the paths of the PolyCollection
        # This is called after the initializers to make sure the kwargs
        # have all been processed and available for the masking calculations
        self._set_unmasked_verts()

    def _get_unmasked_polys(self):
        """Get the unmasked regions using the coordinates and array"""
        # mask(X) | mask(Y)
        mask = np.any(np.ma.getmaskarray(self._coordinates), axis=-1)

        # We want the shape of the polygon, which is the corner of each X/Y array
        mask = (mask[0:-1, 0:-1] | mask[1:, 1:] | mask[0:-1, 1:] | mask[1:, 0:-1])
        arr = self.get_array()
        if arr is not None:
            arr = np.ma.getmaskarray(arr)
            if arr.ndim == 3:
                # RGB(A) case
                mask |= np.any(arr, axis=-1)
            elif arr.ndim == 2:
                mask |= arr
            else:
                mask |= arr.reshape(self._coordinates[:-1, :-1, :].shape[:2])
        return ~mask

    def _set_unmasked_verts(self):
        X = self._coordinates[..., 0]
        Y = self._coordinates[..., 1]

        unmask = self._get_unmasked_polys()
        X1 = np.ma.filled(X[:-1, :-1])[unmask]
        Y1 = np.ma.filled(Y[:-1, :-1])[unmask]
        X2 = np.ma.filled(X[1:, :-1])[unmask]
        Y2 = np.ma.filled(Y[1:, :-1])[unmask]
        X3 = np.ma.filled(X[1:, 1:])[unmask]
        Y3 = np.ma.filled(Y[1:, 1:])[unmask]
        X4 = np.ma.filled(X[:-1, 1:])[unmask]
        Y4 = np.ma.filled(Y[:-1, 1:])[unmask]
        npoly = len(X1)

        xy = np.ma.stack([X1, Y1, X2, Y2, X3, Y3, X4, Y4, X1, Y1], axis=-1)
        verts = xy.reshape((npoly, 5, 2))
        self.set_verts(verts)

    def get_edgecolor(self):
        # docstring inherited
        # We only want to return the facecolors of the polygons
        # that were drawn.
        ec = super().get_edgecolor()
        unmasked_polys = self._get_unmasked_polys().ravel()
        if len(ec) != len(unmasked_polys):
            # Mapping is off
            return ec
        return ec[unmasked_polys, :]

    def get_facecolor(self):
        # docstring inherited
        # We only want to return the facecolors of the polygons
        # that were drawn.
        fc = super().get_facecolor()
        unmasked_polys = self._get_unmasked_polys().ravel()
        if len(fc) != len(unmasked_polys):
            # Mapping is off
            return fc
        return fc[unmasked_polys, :]

    def set_array(self, A):
        # docstring inherited
        prev_unmask = self._get_unmasked_polys()
        super().set_array(A)
        # If the mask has changed at all we need to update
        # the set of Polys that we are drawing
        if not np.array_equal(prev_unmask, self._get_unmasked_polys()):
            self._set_unmasked_verts()
