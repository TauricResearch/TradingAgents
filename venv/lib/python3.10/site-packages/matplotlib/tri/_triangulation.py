import sys

import numpy as np

from matplotlib import _api


class Triangulation:
    """
    An unstructured triangular grid consisting of npoints points and
    ntri triangles.  The triangles can either be specified by the user
    or automatically generated using a Delaunay triangulation.

    Parameters
    ----------
    x, y : (npoints,) array-like
        Coordinates of grid points.
    triangles : (ntri, 3) array-like of int, optional
        For each triangle, the indices of the three points that make
        up the triangle, ordered in an anticlockwise manner.  If not
        specified, the Delaunay triangulation is calculated.
    mask : (ntri,) array-like of bool, optional
        Which triangles are masked out.

    Attributes
    ----------
    triangles : (ntri, 3) array of int
        For each triangle, the indices of the three points that make
        up the triangle, ordered in an anticlockwise manner. If you want to
        take the *mask* into account, use `get_masked_triangles` instead.
    mask : (ntri, 3) array of bool or None
        Masked out triangles.
    is_delaunay : bool
        Whether the Triangulation is a calculated Delaunay
        triangulation (where *triangles* was not specified) or not.

    Notes
    -----
    For a Triangulation to be valid it must not have duplicate points,
    triangles formed from colinear points, or overlapping triangles.
    """
    def __init__(self, x, y, triangles=None, mask=None):
        from matplotlib import _qhull

        self.x = np.asarray(x, dtype=np.float64)
        self.y = np.asarray(y, dtype=np.float64)
        if self.x.shape != self.y.shape or self.x.ndim != 1:
            raise ValueError("x and y must be equal-length 1D arrays, but "
                             f"found shapes {self.x.shape!r} and "
                             f"{self.y.shape!r}")

        self.mask = None
        self._edges = None
        self._neighbors = None
        self.is_delaunay = False

        if triangles is None:
            # No triangulation specified, so use matplotlib._qhull to obtain
            # Delaunay triangulation.
            self.triangles, self._neighbors = _qhull.delaunay(x, y, sys.flags.verbose)
            self.is_delaunay = True
        else:
            # Triangulation specified. Copy, since we may correct triangle
            # orientation.
            try:
                self.triangles = np.array(triangles, dtype=np.int32, order='C')
            except ValueError as e:
                raise ValueError('triangles must be a (N, 3) int array, not '
                                 f'{triangles!r}') from e
            if self.triangles.ndim != 2 or self.triangles.shape[1] != 3:
                raise ValueError(
                    'triangles must be a (N, 3) int array, but found shape '
                    f'{self.triangles.shape!r}')
            if self.triangles.max() >= len(self.x):
                raise ValueError(
                    'triangles are indices into the points and must be in the '
                    f'range 0 <= i < {len(self.x)} but found value '
                    f'{self.triangles.max()}')
            if self.triangles.min() < 0:
                raise ValueError(
                    'triangles are indices into the points and must be in the '
                    f'range 0 <= i < {len(self.x)} but found value '
                    f'{self.triangles.min()}')

        # Underlying C++ object is not created until first needed.
        self._cpp_triangulation = None

        # Default TriFinder not created until needed.
        self._trifinder = None

        self.set_mask(mask)

    def calculate_plane_coefficients(self, z):
        """
        Calculate plane equation coefficients for all unmasked triangles from
        the point (x, y) coordinates and specified z-array of shape (npoints).
        The returned array has shape (npoints, 3) and allows z-value at (x, y)
        position in triangle tri to be calculated using
        ``z = array[tri, 0] * x  + array[tri, 1] * y + array[tri, 2]``.
        """
        return self.get_cpp_triangulation().calculate_plane_coefficients(z)

    @property
    def edges(self):
        """
        Return integer array of shape (nedges, 2) containing all edges of
        non-masked triangles.

        Each row defines an edge by its start point index and end point
        index.  Each edge appears only once, i.e. for an edge between points
        *i*  and *j*, there will only be either *(i, j)* or *(j, i)*.
        """
        if self._edges is None:
            self._edges = self.get_cpp_triangulation().get_edges()
        return self._edges

    def get_cpp_triangulation(self):
        """
        Return the underlying C++ Triangulation object, creating it
        if necessary.
        """
        from matplotlib import _tri
        if self._cpp_triangulation is None:
            self._cpp_triangulation = _tri.Triangulation(
                # For unset arrays use empty tuple which has size of zero.
                self.x, self.y, self.triangles,
                self.mask if self.mask is not None else (),
                self._edges if self._edges is not None else (),
                self._neighbors if self._neighbors is not None else (),
                not self.is_delaunay)
        return self._cpp_triangulation

    def get_masked_triangles(self):
        """
        Return an array of triangles taking the mask into account.
        """
        if self.mask is not None:
            return self.triangles[~self.mask]
        else:
            return self.triangles

    @staticmethod
    def get_from_args_and_kwargs(*args, **kwargs):
        """
        Return a Triangulation object from the args and kwargs, and
        the remaining args and kwargs with the consumed values removed.

        There are two alternatives: either the first argument is a
        Triangulation object, in which case it is returned, or the args
        and kwargs are sufficient to create a new Triangulation to
        return.  In the latter case, see Triangulation.__init__ for
        the possible args and kwargs.
        """
        if isinstance(args[0], Triangulation):
            triangulation, *args = args
            if 'triangles' in kwargs:
                _api.warn_external(
                    "Passing the keyword 'triangles' has no effect when also "
                    "passing a Triangulation")
            if 'mask' in kwargs:
                _api.warn_external(
                    "Passing the keyword 'mask' has no effect when also "
                    "passing a Triangulation")
        else:
            x, y, triangles, mask, args, kwargs = \
                Triangulation._extract_triangulation_params(args, kwargs)
            triangulation = Triangulation(x, y, triangles, mask)
        return triangulation, args, kwargs

    @staticmethod
    def _extract_triangulation_params(args, kwargs):
        x, y, *args = args
        # Check triangles in kwargs then args.
        triangles = kwargs.pop('triangles', None)
        from_args = False
        if triangles is None and args:
            triangles = args[0]
            from_args = True
        if triangles is not None:
            try:
                triangles = np.asarray(triangles, dtype=np.int32)
            except ValueError:
                triangles = None
        if triangles is not None and (triangles.ndim != 2 or
                                      triangles.shape[1] != 3):
            triangles = None
        if triangles is not None and from_args:
            args = args[1:]  # Consumed first item in args.
        # Check for mask in kwargs.
        mask = kwargs.pop('mask', None)
        return x, y, triangles, mask, args, kwargs

    def get_trifinder(self):
        """
        Return the default `matplotlib.tri.TriFinder` of this
        triangulation, creating it if necessary.  This allows the same
        TriFinder object to be easily shared.
        """
        if self._trifinder is None:
            # Default TriFinder class.
            from matplotlib.tri._trifinder import TrapezoidMapTriFinder
            self._trifinder = TrapezoidMapTriFinder(self)
        return self._trifinder

    @property
    def neighbors(self):
        """
        Return integer array of shape (ntri, 3) containing neighbor triangles.

        For each triangle, the indices of the three triangles that
        share the same edges, or -1 if there is no such neighboring
        triangle.  ``neighbors[i, j]`` is the triangle that is the neighbor
        to the edge from point index ``triangles[i, j]`` to point index
        ``triangles[i, (j+1)%3]``.
        """
        if self._neighbors is None:
            self._neighbors = self.get_cpp_triangulation().get_neighbors()
        return self._neighbors

    def set_mask(self, mask):
        """
        Set or clear the mask array.

        Parameters
        ----------
        mask : None or bool array of length ntri
        """
        if mask is None:
            self.mask = None
        else:
            self.mask = np.asarray(mask, dtype=bool)
            if self.mask.shape != (self.triangles.shape[0],):
                raise ValueError('mask array must have same length as '
                                 'triangles array')

        # Set mask in C++ Triangulation.
        if self._cpp_triangulation is not None:
            self._cpp_triangulation.set_mask(
                self.mask if self.mask is not None else ())

        # Clear derived fields so they are recalculated when needed.
        self._edges = None
        self._neighbors = None

        # Recalculate TriFinder if it exists.
        if self._trifinder is not None:
            self._trifinder._initialize()
