"""
Interpolation inside triangular grids.
"""

import numpy as np

from matplotlib import _api
from matplotlib.tri import Triangulation
from matplotlib.tri._trifinder import TriFinder
from matplotlib.tri._tritools import TriAnalyzer

__all__ = ('TriInterpolator', 'LinearTriInterpolator', 'CubicTriInterpolator')


class TriInterpolator:
    """
    Abstract base class for classes used to interpolate on a triangular grid.

    Derived classes implement the following methods:

    - ``__call__(x, y)``,
      where x, y are array-like point coordinates of the same shape, and
      that returns a masked array of the same shape containing the
      interpolated z-values.

    - ``gradient(x, y)``,
      where x, y are array-like point coordinates of the same
      shape, and that returns a list of 2 masked arrays of the same shape
      containing the 2 derivatives of the interpolator (derivatives of
      interpolated z values with respect to x and y).
    """

    def __init__(self, triangulation, z, trifinder=None):
        _api.check_isinstance(Triangulation, triangulation=triangulation)
        self._triangulation = triangulation

        self._z = np.asarray(z)
        if self._z.shape != self._triangulation.x.shape:
            raise ValueError("z array must have same length as triangulation x"
                             " and y arrays")

        _api.check_isinstance((TriFinder, None), trifinder=trifinder)
        self._trifinder = trifinder or self._triangulation.get_trifinder()

        # Default scaling factors : 1.0 (= no scaling)
        # Scaling may be used for interpolations for which the order of
        # magnitude of x, y has an impact on the interpolant definition.
        # Please refer to :meth:`_interpolate_multikeys` for details.
        self._unit_x = 1.0
        self._unit_y = 1.0

        # Default triangle renumbering: None (= no renumbering)
        # Renumbering may be used to avoid unnecessary computations
        # if complex calculations are done inside the Interpolator.
        # Please refer to :meth:`_interpolate_multikeys` for details.
        self._tri_renum = None

    # __call__ and gradient docstrings are shared by all subclasses
    # (except, if needed, relevant additions).
    # However these methods are only implemented in subclasses to avoid
    # confusion in the documentation.
    _docstring__call__ = """
        Returns a masked array containing interpolated values at the specified
        (x, y) points.

        Parameters
        ----------
        x, y : array-like
            x and y coordinates of the same shape and any number of
            dimensions.

        Returns
        -------
        np.ma.array
            Masked array of the same shape as *x* and *y*; values corresponding
            to (*x*, *y*) points outside of the triangulation are masked out.

        """

    _docstringgradient = r"""
        Returns a list of 2 masked arrays containing interpolated derivatives
        at the specified (x, y) points.

        Parameters
        ----------
        x, y : array-like
            x and y coordinates of the same shape and any number of
            dimensions.

        Returns
        -------
        dzdx, dzdy : np.ma.array
            2 masked arrays of the same shape as *x* and *y*; values
            corresponding to (x, y) points outside of the triangulation
            are masked out.
            The first returned array contains the values of
            :math:`\frac{\partial z}{\partial x}` and the second those of
            :math:`\frac{\partial z}{\partial y}`.

        """

    def _interpolate_multikeys(self, x, y, tri_index=None,
                               return_keys=('z',)):
        """
        Versatile (private) method defined for all TriInterpolators.

        :meth:`_interpolate_multikeys` is a wrapper around method
        :meth:`_interpolate_single_key` (to be defined in the child
        subclasses).
        :meth:`_interpolate_single_key actually performs the interpolation,
        but only for 1-dimensional inputs and at valid locations (inside
        unmasked triangles of the triangulation).

        The purpose of :meth:`_interpolate_multikeys` is to implement the
        following common tasks needed in all subclasses implementations:

        - calculation of containing triangles
        - dealing with more than one interpolation request at the same
          location (e.g., if the 2 derivatives are requested, it is
          unnecessary to compute the containing triangles twice)
        - scaling according to self._unit_x, self._unit_y
        - dealing with points outside of the grid (with fill value np.nan)
        - dealing with multi-dimensional *x*, *y* arrays: flattening for
          :meth:`_interpolate_params` call and final reshaping.

        (Note that np.vectorize could do most of those things very well for
        you, but it does it by function evaluations over successive tuples of
        the input arrays. Therefore, this tends to be more time-consuming than
        using optimized numpy functions - e.g., np.dot - which can be used
        easily on the flattened inputs, in the child-subclass methods
        :meth:`_interpolate_single_key`.)

        It is guaranteed that the calls to :meth:`_interpolate_single_key`
        will be done with flattened (1-d) array-like input parameters *x*, *y*
        and with flattened, valid `tri_index` arrays (no -1 index allowed).

        Parameters
        ----------
        x, y : array-like
            x and y coordinates where interpolated values are requested.
        tri_index : array-like of int, optional
            Array of the containing triangle indices, same shape as
            *x* and *y*. Defaults to None. If None, these indices
            will be computed by a TriFinder instance.
            (Note: For point outside the grid, tri_index[ipt] shall be -1).
        return_keys : tuple of keys from {'z', 'dzdx', 'dzdy'}
            Defines the interpolation arrays to return, and in which order.

        Returns
        -------
        list of arrays
            Each array-like contains the expected interpolated values in the
            order defined by *return_keys* parameter.
        """
        # Flattening and rescaling inputs arrays x, y
        # (initial shape is stored for output)
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        sh_ret = x.shape
        if x.shape != y.shape:
            raise ValueError("x and y shall have same shapes."
                             f" Given: {x.shape} and {y.shape}")
        x = np.ravel(x)
        y = np.ravel(y)
        x_scaled = x/self._unit_x
        y_scaled = y/self._unit_y
        size_ret = np.size(x_scaled)

        # Computes & ravels the element indexes, extract the valid ones.
        if tri_index is None:
            tri_index = self._trifinder(x, y)
        else:
            if tri_index.shape != sh_ret:
                raise ValueError(
                    "tri_index array is provided and shall"
                    " have same shape as x and y. Given: "
                    f"{tri_index.shape} and {sh_ret}")
            tri_index = np.ravel(tri_index)

        mask_in = (tri_index != -1)
        if self._tri_renum is None:
            valid_tri_index = tri_index[mask_in]
        else:
            valid_tri_index = self._tri_renum[tri_index[mask_in]]
        valid_x = x_scaled[mask_in]
        valid_y = y_scaled[mask_in]

        ret = []
        for return_key in return_keys:
            # Find the return index associated with the key.
            try:
                return_index = {'z': 0, 'dzdx': 1, 'dzdy': 2}[return_key]
            except KeyError as err:
                raise ValueError("return_keys items shall take values in"
                                 " {'z', 'dzdx', 'dzdy'}") from err

            # Sets the scale factor for f & df components
            scale = [1., 1./self._unit_x, 1./self._unit_y][return_index]

            # Computes the interpolation
            ret_loc = np.empty(size_ret, dtype=np.float64)
            ret_loc[~mask_in] = np.nan
            ret_loc[mask_in] = self._interpolate_single_key(
                return_key, valid_tri_index, valid_x, valid_y) * scale
            ret += [np.ma.masked_invalid(ret_loc.reshape(sh_ret), copy=False)]

        return ret

    def _interpolate_single_key(self, return_key, tri_index, x, y):
        """
        Interpolate at points belonging to the triangulation
        (inside an unmasked triangles).

        Parameters
        ----------
        return_key : {'z', 'dzdx', 'dzdy'}
            The requested values (z or its derivatives).
        tri_index : 1D int array
            Valid triangle index (cannot be -1).
        x, y : 1D arrays, same shape as `tri_index`
            Valid locations where interpolation is requested.

        Returns
        -------
        1-d array
            Returned array of the same size as *tri_index*
        """
        raise NotImplementedError("TriInterpolator subclasses" +
                                  "should implement _interpolate_single_key!")


class LinearTriInterpolator(TriInterpolator):
    """
    Linear interpolator on a triangular grid.

    Each triangle is represented by a plane so that an interpolated value at
    point (x, y) lies on the plane of the triangle containing (x, y).
    Interpolated values are therefore continuous across the triangulation, but
    their first derivatives are discontinuous at edges between triangles.

    Parameters
    ----------
    triangulation : `~matplotlib.tri.Triangulation`
        The triangulation to interpolate over.
    z : (npoints,) array-like
        Array of values, defined at grid points, to interpolate between.
    trifinder : `~matplotlib.tri.TriFinder`, optional
        If this is not specified, the Triangulation's default TriFinder will
        be used by calling `.Triangulation.get_trifinder`.

    Methods
    -------
    `__call__` (x, y) : Returns interpolated values at (x, y) points.
    `gradient` (x, y) : Returns interpolated derivatives at (x, y) points.

    """
    def __init__(self, triangulation, z, trifinder=None):
        super().__init__(triangulation, z, trifinder)

        # Store plane coefficients for fast interpolation calculations.
        self._plane_coefficients = \
            self._triangulation.calculate_plane_coefficients(self._z)

    def __call__(self, x, y):
        return self._interpolate_multikeys(x, y, tri_index=None,
                                           return_keys=('z',))[0]
    __call__.__doc__ = TriInterpolator._docstring__call__

    def gradient(self, x, y):
        return self._interpolate_multikeys(x, y, tri_index=None,
                                           return_keys=('dzdx', 'dzdy'))
    gradient.__doc__ = TriInterpolator._docstringgradient

    def _interpolate_single_key(self, return_key, tri_index, x, y):
        _api.check_in_list(['z', 'dzdx', 'dzdy'], return_key=return_key)
        if return_key == 'z':
            return (self._plane_coefficients[tri_index, 0]*x +
                    self._plane_coefficients[tri_index, 1]*y +
                    self._plane_coefficients[tri_index, 2])
        elif return_key == 'dzdx':
            return self._plane_coefficients[tri_index, 0]
        else:  # 'dzdy'
            return self._plane_coefficients[tri_index, 1]


class CubicTriInterpolator(TriInterpolator):
    r"""
    Cubic interpolator on a triangular grid.

    In one-dimension - on a segment - a cubic interpolating function is
    defined by the values of the function and its derivative at both ends.
    This is almost the same in 2D inside a triangle, except that the values
    of the function and its 2 derivatives have to be defined at each triangle
    node.

    The CubicTriInterpolator takes the value of the function at each node -
    provided by the user - and internally computes the value of the
    derivatives, resulting in a smooth interpolation.
    (As a special feature, the user can also impose the value of the
    derivatives at each node, but this is not supposed to be the common
    usage.)

    Parameters
    ----------
    triangulation : `~matplotlib.tri.Triangulation`
        The triangulation to interpolate over.
    z : (npoints,) array-like
        Array of values, defined at grid points, to interpolate between.
    kind : {'min_E', 'geom', 'user'}, optional
        Choice of the smoothing algorithm, in order to compute
        the interpolant derivatives (defaults to 'min_E'):

        - if 'min_E': (default) The derivatives at each node is computed
          to minimize a bending energy.
        - if 'geom': The derivatives at each node is computed as a
          weighted average of relevant triangle normals. To be used for
          speed optimization (large grids).
        - if 'user': The user provides the argument *dz*, no computation
          is hence needed.

    trifinder : `~matplotlib.tri.TriFinder`, optional
        If not specified, the Triangulation's default TriFinder will
        be used by calling `.Triangulation.get_trifinder`.
    dz : tuple of array-likes (dzdx, dzdy), optional
        Used only if  *kind* ='user'. In this case *dz* must be provided as
        (dzdx, dzdy) where dzdx, dzdy are arrays of the same shape as *z* and
        are the interpolant first derivatives at the *triangulation* points.

    Methods
    -------
    `__call__` (x, y) : Returns interpolated values at (x, y) points.
    `gradient` (x, y) : Returns interpolated derivatives at (x, y) points.

    Notes
    -----
    This note is a bit technical and details how the cubic interpolation is
    computed.

    The interpolation is based on a Clough-Tocher subdivision scheme of
    the *triangulation* mesh (to make it clearer, each triangle of the
    grid will be divided in 3 child-triangles, and on each child triangle
    the interpolated function is a cubic polynomial of the 2 coordinates).
    This technique originates from FEM (Finite Element Method) analysis;
    the element used is a reduced Hsieh-Clough-Tocher (HCT)
    element. Its shape functions are described in [1]_.
    The assembled function is guaranteed to be C1-smooth, i.e. it is
    continuous and its first derivatives are also continuous (this
    is easy to show inside the triangles but is also true when crossing the
    edges).

    In the default case (*kind* ='min_E'), the interpolant minimizes a
    curvature energy on the functional space generated by the HCT element
    shape functions - with imposed values but arbitrary derivatives at each
    node. The minimized functional is the integral of the so-called total
    curvature (implementation based on an algorithm from [2]_ - PCG sparse
    solver):

    .. math::

        E(z) = \frac{1}{2} \int_{\Omega} \left(
            \left( \frac{\partial^2{z}}{\partial{x}^2} \right)^2 +
            \left( \frac{\partial^2{z}}{\partial{y}^2} \right)^2 +
            2\left( \frac{\partial^2{z}}{\partial{y}\partial{x}} \right)^2
        \right) dx\,dy

    If the case *kind* ='geom' is chosen by the user, a simple geometric
    approximation is used (weighted average of the triangle normal
    vectors), which could improve speed on very large grids.

    References
    ----------
    .. [1] Michel Bernadou, Kamal Hassan, "Basis functions for general
        Hsieh-Clough-Tocher triangles, complete or reduced.",
        International Journal for Numerical Methods in Engineering,
        17(5):784 - 789. 2.01.
    .. [2] C.T. Kelley, "Iterative Methods for Optimization".

    """
    def __init__(self, triangulation, z, kind='min_E', trifinder=None,
                 dz=None):
        super().__init__(triangulation, z, trifinder)

        # Loads the underlying c++ _triangulation.
        # (During loading, reordering of triangulation._triangles may occur so
        # that all final triangles are now anti-clockwise)
        self._triangulation.get_cpp_triangulation()

        # To build the stiffness matrix and avoid zero-energy spurious modes
        # we will only store internally the valid (unmasked) triangles and
        # the necessary (used) points coordinates.
        # 2 renumbering tables need to be computed and stored:
        #  - a triangle renum table in order to translate the result from a
        #    TriFinder instance into the internal stored triangle number.
        #  - a node renum table to overwrite the self._z values into the new
        #    (used) node numbering.
        tri_analyzer = TriAnalyzer(self._triangulation)
        (compressed_triangles, compressed_x, compressed_y, tri_renum,
         node_renum) = tri_analyzer._get_compressed_triangulation()
        self._triangles = compressed_triangles
        self._tri_renum = tri_renum
        # Taking into account the node renumbering in self._z:
        valid_node = (node_renum != -1)
        self._z[node_renum[valid_node]] = self._z[valid_node]

        # Computing scale factors
        self._unit_x = np.ptp(compressed_x)
        self._unit_y = np.ptp(compressed_y)
        self._pts = np.column_stack([compressed_x / self._unit_x,
                                     compressed_y / self._unit_y])
        # Computing triangle points
        self._tris_pts = self._pts[self._triangles]
        # Computing eccentricities
        self._eccs = self._compute_tri_eccentricities(self._tris_pts)
        # Computing dof estimations for HCT triangle shape function
        _api.check_in_list(['user', 'geom', 'min_E'], kind=kind)
        self._dof = self._compute_dof(kind, dz=dz)
        # Loading HCT element
        self._ReferenceElement = _ReducedHCT_Element()

    def __call__(self, x, y):
        return self._interpolate_multikeys(x, y, tri_index=None,
                                           return_keys=('z',))[0]
    __call__.__doc__ = TriInterpolator._docstring__call__

    def gradient(self, x, y):
        return self._interpolate_multikeys(x, y, tri_index=None,
                                           return_keys=('dzdx', 'dzdy'))
    gradient.__doc__ = TriInterpolator._docstringgradient

    def _interpolate_single_key(self, return_key, tri_index, x, y):
        _api.check_in_list(['z', 'dzdx', 'dzdy'], return_key=return_key)
        tris_pts = self._tris_pts[tri_index]
        alpha = self._get_alpha_vec(x, y, tris_pts)
        ecc = self._eccs[tri_index]
        dof = np.expand_dims(self._dof[tri_index], axis=1)
        if return_key == 'z':
            return self._ReferenceElement.get_function_values(
                alpha, ecc, dof)
        else:  # 'dzdx', 'dzdy'
            J = self._get_jacobian(tris_pts)
            dzdx = self._ReferenceElement.get_function_derivatives(
                alpha, J, ecc, dof)
            if return_key == 'dzdx':
                return dzdx[:, 0, 0]
            else:
                return dzdx[:, 1, 0]

    def _compute_dof(self, kind, dz=None):
        """
        Compute and return nodal dofs according to kind.

        Parameters
        ----------
        kind : {'min_E', 'geom', 'user'}
            Choice of the _DOF_estimator subclass to estimate the gradient.
        dz : tuple of array-likes (dzdx, dzdy), optional
            Used only if *kind*=user; in this case passed to the
            :class:`_DOF_estimator_user`.

        Returns
        -------
        array-like, shape (npts, 2)
            Estimation of the gradient at triangulation nodes (stored as
            degree of freedoms of reduced-HCT triangle elements).
        """
        if kind == 'user':
            if dz is None:
                raise ValueError("For a CubicTriInterpolator with "
                                 "*kind*='user', a valid *dz* "
                                 "argument is expected.")
            TE = _DOF_estimator_user(self, dz=dz)
        elif kind == 'geom':
            TE = _DOF_estimator_geom(self)
        else:  # 'min_E', checked in __init__
            TE = _DOF_estimator_min_E(self)
        return TE.compute_dof_from_df()

    @staticmethod
    def _get_alpha_vec(x, y, tris_pts):
        """
        Fast (vectorized) function to compute barycentric coordinates alpha.

        Parameters
        ----------
        x, y : array-like of dim 1 (shape (nx,))
            Coordinates of the points whose points barycentric coordinates are
            requested.
        tris_pts : array like of dim 3 (shape: (nx, 3, 2))
            Coordinates of the containing triangles apexes.

        Returns
        -------
        array of dim 2 (shape (nx, 3))
            Barycentric coordinates of the points inside the containing
            triangles.
        """
        ndim = tris_pts.ndim-2

        a = tris_pts[:, 1, :] - tris_pts[:, 0, :]
        b = tris_pts[:, 2, :] - tris_pts[:, 0, :]
        abT = np.stack([a, b], axis=-1)
        ab = _transpose_vectorized(abT)
        OM = np.stack([x, y], axis=1) - tris_pts[:, 0, :]

        metric = ab @ abT
        # Here we try to deal with the colinear cases.
        # metric_inv is in this case set to the Moore-Penrose pseudo-inverse
        # meaning that we will still return a set of valid barycentric
        # coordinates.
        metric_inv = _pseudo_inv22sym_vectorized(metric)
        Covar = ab @ _transpose_vectorized(np.expand_dims(OM, ndim))
        ksi = metric_inv @ Covar
        alpha = _to_matrix_vectorized([
            [1-ksi[:, 0, 0]-ksi[:, 1, 0]], [ksi[:, 0, 0]], [ksi[:, 1, 0]]])
        return alpha

    @staticmethod
    def _get_jacobian(tris_pts):
        """
        Fast (vectorized) function to compute triangle jacobian matrix.

        Parameters
        ----------
        tris_pts : array like of dim 3 (shape: (nx, 3, 2))
            Coordinates of the containing triangles apexes.

        Returns
        -------
        array of dim 3 (shape (nx, 2, 2))
            Barycentric coordinates of the points inside the containing
            triangles.
            J[itri, :, :] is the jacobian matrix at apex 0 of the triangle
            itri, so that the following (matrix) relationship holds:
               [dz/dksi] = [J] x [dz/dx]
            with x: global coordinates
                 ksi: element parametric coordinates in triangle first apex
                 local basis.
        """
        a = np.array(tris_pts[:, 1, :] - tris_pts[:, 0, :])
        b = np.array(tris_pts[:, 2, :] - tris_pts[:, 0, :])
        J = _to_matrix_vectorized([[a[:, 0], a[:, 1]],
                                   [b[:, 0], b[:, 1]]])
        return J

    @staticmethod
    def _compute_tri_eccentricities(tris_pts):
        """
        Compute triangle eccentricities.

        Parameters
        ----------
        tris_pts : array like of dim 3 (shape: (nx, 3, 2))
            Coordinates of the triangles apexes.

        Returns
        -------
        array like of dim 2 (shape: (nx, 3))
            The so-called eccentricity parameters [1] needed for HCT triangular
            element.
        """
        a = np.expand_dims(tris_pts[:, 2, :] - tris_pts[:, 1, :], axis=2)
        b = np.expand_dims(tris_pts[:, 0, :] - tris_pts[:, 2, :], axis=2)
        c = np.expand_dims(tris_pts[:, 1, :] - tris_pts[:, 0, :], axis=2)
        # Do not use np.squeeze, this is dangerous if only one triangle
        # in the triangulation...
        dot_a = (_transpose_vectorized(a) @ a)[:, 0, 0]
        dot_b = (_transpose_vectorized(b) @ b)[:, 0, 0]
        dot_c = (_transpose_vectorized(c) @ c)[:, 0, 0]
        # Note that this line will raise a warning for dot_a, dot_b or dot_c
        # zeros, but we choose not to support triangles with duplicate points.
        return _to_matrix_vectorized([[(dot_c-dot_b) / dot_a],
                                      [(dot_a-dot_c) / dot_b],
                                      [(dot_b-dot_a) / dot_c]])


# FEM element used for interpolation and for solving minimisation
# problem (Reduced HCT element)
class _ReducedHCT_Element:
    """
    Implementation of reduced HCT triangular element with explicit shape
    functions.

    Computes z, dz, d2z and the element stiffness matrix for bending energy:
    E(f) = integral( (d2z/dx2 + d2z/dy2)**2 dA)

    *** Reference for the shape functions: ***
    [1] Basis functions for general Hsieh-Clough-Tocher _triangles, complete or
        reduced.
        Michel Bernadou, Kamal Hassan
        International Journal for Numerical Methods in Engineering.
        17(5):784 - 789.  2.01

    *** Element description: ***
    9 dofs: z and dz given at 3 apex
    C1 (conform)

    """
    # 1) Loads matrices to generate shape functions as a function of
    #    triangle eccentricities - based on [1] p.11 '''
    M = np.array([
        [ 0.00, 0.00, 0.00,  4.50,  4.50, 0.00, 0.00, 0.00, 0.00, 0.00],
        [-0.25, 0.00, 0.00,  0.50,  1.25, 0.00, 0.00, 0.00, 0.00, 0.00],
        [-0.25, 0.00, 0.00,  1.25,  0.50, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.50, 1.00, 0.00, -1.50,  0.00, 3.00, 3.00, 0.00, 0.00, 3.00],
        [ 0.00, 0.00, 0.00, -0.25,  0.25, 0.00, 1.00, 0.00, 0.00, 0.50],
        [ 0.25, 0.00, 0.00, -0.50, -0.25, 1.00, 0.00, 0.00, 0.00, 1.00],
        [ 0.50, 0.00, 1.00,  0.00, -1.50, 0.00, 0.00, 3.00, 3.00, 3.00],
        [ 0.25, 0.00, 0.00, -0.25, -0.50, 0.00, 0.00, 0.00, 1.00, 1.00],
        [ 0.00, 0.00, 0.00,  0.25, -0.25, 0.00, 0.00, 1.00, 0.00, 0.50]])
    M0 = np.array([
        [ 0.00, 0.00, 0.00,  0.00,  0.00, 0.00, 0.00, 0.00, 0.00,  0.00],
        [ 0.00, 0.00, 0.00,  0.00,  0.00, 0.00, 0.00, 0.00, 0.00,  0.00],
        [ 0.00, 0.00, 0.00,  0.00,  0.00, 0.00, 0.00, 0.00, 0.00,  0.00],
        [-1.00, 0.00, 0.00,  1.50,  1.50, 0.00, 0.00, 0.00, 0.00, -3.00],
        [-0.50, 0.00, 0.00,  0.75,  0.75, 0.00, 0.00, 0.00, 0.00, -1.50],
        [ 0.00, 0.00, 0.00,  0.00,  0.00, 0.00, 0.00, 0.00, 0.00,  0.00],
        [ 1.00, 0.00, 0.00, -1.50, -1.50, 0.00, 0.00, 0.00, 0.00,  3.00],
        [ 0.00, 0.00, 0.00,  0.00,  0.00, 0.00, 0.00, 0.00, 0.00,  0.00],
        [ 0.50, 0.00, 0.00, -0.75, -0.75, 0.00, 0.00, 0.00, 0.00,  1.50]])
    M1 = np.array([
        [-0.50, 0.00, 0.00,  1.50, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [-0.25, 0.00, 0.00,  0.75, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.50, 0.00, 0.00, -1.50, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.25, 0.00, 0.00, -0.75, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00]])
    M2 = np.array([
        [ 0.50, 0.00, 0.00, 0.00, -1.50, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.25, 0.00, 0.00, 0.00, -0.75, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [-0.50, 0.00, 0.00, 0.00,  1.50, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [-0.25, 0.00, 0.00, 0.00,  0.75, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        [ 0.00, 0.00, 0.00, 0.00,  0.00, 0.00, 0.00, 0.00, 0.00, 0.00]])

    # 2) Loads matrices to rotate components of gradient & Hessian
    #    vectors in the reference basis of triangle first apex (a0)
    rotate_dV = np.array([[ 1.,  0.], [ 0.,  1.],
                          [ 0.,  1.], [-1., -1.],
                          [-1., -1.], [ 1.,  0.]])

    rotate_d2V = np.array([[1., 0., 0.], [0., 1., 0.], [ 0.,  0.,  1.],
                           [0., 1., 0.], [1., 1., 1.], [ 0., -2., -1.],
                           [1., 1., 1.], [1., 0., 0.], [-2.,  0., -1.]])

    # 3) Loads Gauss points & weights on the 3 sub-_triangles for P2
    #    exact integral - 3 points on each subtriangles.
    # NOTE: as the 2nd derivative is discontinuous , we really need those 9
    # points!
    n_gauss = 9
    gauss_pts = np.array([[13./18.,  4./18.,  1./18.],
                          [ 4./18., 13./18.,  1./18.],
                          [ 7./18.,  7./18.,  4./18.],
                          [ 1./18., 13./18.,  4./18.],
                          [ 1./18.,  4./18., 13./18.],
                          [ 4./18.,  7./18.,  7./18.],
                          [ 4./18.,  1./18., 13./18.],
                          [13./18.,  1./18.,  4./18.],
                          [ 7./18.,  4./18.,  7./18.]], dtype=np.float64)
    gauss_w = np.ones([9], dtype=np.float64) / 9.

    #  4) Stiffness matrix for curvature energy
    E = np.array([[1., 0., 0.], [0., 1., 0.], [0., 0., 2.]])

    #  5) Loads the matrix to compute DOF_rot from tri_J at apex 0
    J0_to_J1 = np.array([[-1.,  1.], [-1.,  0.]])
    J0_to_J2 = np.array([[ 0., -1.], [ 1., -1.]])

    def get_function_values(self, alpha, ecc, dofs):
        """
        Parameters
        ----------
        alpha : is a (N x 3 x 1) array (array of column-matrices) of
        barycentric coordinates,
        ecc : is a (N x 3 x 1) array (array of column-matrices) of triangle
        eccentricities,
        dofs : is a (N x 1 x 9) arrays (arrays of row-matrices) of computed
        degrees of freedom.

        Returns
        -------
        Returns the N-array of interpolated function values.
        """
        subtri = np.argmin(alpha, axis=1)[:, 0]
        ksi = _roll_vectorized(alpha, -subtri, axis=0)
        E = _roll_vectorized(ecc, -subtri, axis=0)
        x = ksi[:, 0, 0]
        y = ksi[:, 1, 0]
        z = ksi[:, 2, 0]
        x_sq = x*x
        y_sq = y*y
        z_sq = z*z
        V = _to_matrix_vectorized([
            [x_sq*x], [y_sq*y], [z_sq*z], [x_sq*z], [x_sq*y], [y_sq*x],
            [y_sq*z], [z_sq*y], [z_sq*x], [x*y*z]])
        prod = self.M @ V
        prod += _scalar_vectorized(E[:, 0, 0], self.M0 @ V)
        prod += _scalar_vectorized(E[:, 1, 0], self.M1 @ V)
        prod += _scalar_vectorized(E[:, 2, 0], self.M2 @ V)
        s = _roll_vectorized(prod, 3*subtri, axis=0)
        return (dofs @ s)[:, 0, 0]

    def get_function_derivatives(self, alpha, J, ecc, dofs):
        """
        Parameters
        ----------
        *alpha* is a (N x 3 x 1) array (array of column-matrices of
        barycentric coordinates)
        *J* is a (N x 2 x 2) array of jacobian matrices (jacobian matrix at
        triangle first apex)
        *ecc* is a (N x 3 x 1) array (array of column-matrices of triangle
        eccentricities)
        *dofs* is a (N x 1 x 9) arrays (arrays of row-matrices) of computed
        degrees of freedom.

        Returns
        -------
        Returns the values of interpolated function derivatives [dz/dx, dz/dy]
        in global coordinates at locations alpha, as a column-matrices of
        shape (N x 2 x 1).
        """
        subtri = np.argmin(alpha, axis=1)[:, 0]
        ksi = _roll_vectorized(alpha, -subtri, axis=0)
        E = _roll_vectorized(ecc, -subtri, axis=0)
        x = ksi[:, 0, 0]
        y = ksi[:, 1, 0]
        z = ksi[:, 2, 0]
        x_sq = x*x
        y_sq = y*y
        z_sq = z*z
        dV = _to_matrix_vectorized([
            [    -3.*x_sq,     -3.*x_sq],
            [     3.*y_sq,           0.],
            [          0.,      3.*z_sq],
            [     -2.*x*z, -2.*x*z+x_sq],
            [-2.*x*y+x_sq,      -2.*x*y],
            [ 2.*x*y-y_sq,        -y_sq],
            [      2.*y*z,         y_sq],
            [        z_sq,       2.*y*z],
            [       -z_sq,  2.*x*z-z_sq],
            [     x*z-y*z,      x*y-y*z]])
        # Puts back dV in first apex basis
        dV = dV @ _extract_submatrices(
            self.rotate_dV, subtri, block_size=2, axis=0)

        prod = self.M @ dV
        prod += _scalar_vectorized(E[:, 0, 0], self.M0 @ dV)
        prod += _scalar_vectorized(E[:, 1, 0], self.M1 @ dV)
        prod += _scalar_vectorized(E[:, 2, 0], self.M2 @ dV)
        dsdksi = _roll_vectorized(prod, 3*subtri, axis=0)
        dfdksi = dofs @ dsdksi
        # In global coordinates:
        # Here we try to deal with the simplest colinear cases, returning a
        # null matrix.
        J_inv = _safe_inv22_vectorized(J)
        dfdx = J_inv @ _transpose_vectorized(dfdksi)
        return dfdx

    def get_function_hessians(self, alpha, J, ecc, dofs):
        """
        Parameters
        ----------
        *alpha* is a (N x 3 x 1) array (array of column-matrices) of
        barycentric coordinates
        *J* is a (N x 2 x 2) array of jacobian matrices (jacobian matrix at
        triangle first apex)
        *ecc* is a (N x 3 x 1) array (array of column-matrices) of triangle
        eccentricities
        *dofs* is a (N x 1 x 9) arrays (arrays of row-matrices) of computed
        degrees of freedom.

        Returns
        -------
        Returns the values of interpolated function 2nd-derivatives
        [d2z/dx2, d2z/dy2, d2z/dxdy] in global coordinates at locations alpha,
        as a column-matrices of shape (N x 3 x 1).
        """
        d2sdksi2 = self.get_d2Sidksij2(alpha, ecc)
        d2fdksi2 = dofs @ d2sdksi2
        H_rot = self.get_Hrot_from_J(J)
        d2fdx2 = d2fdksi2 @ H_rot
        return _transpose_vectorized(d2fdx2)

    def get_d2Sidksij2(self, alpha, ecc):
        """
        Parameters
        ----------
        *alpha* is a (N x 3 x 1) array (array of column-matrices) of
        barycentric coordinates
        *ecc* is a (N x 3 x 1) array (array of column-matrices) of triangle
        eccentricities

        Returns
        -------
        Returns the arrays d2sdksi2 (N x 3 x 1) Hessian of shape functions
        expressed in covariant coordinates in first apex basis.
        """
        subtri = np.argmin(alpha, axis=1)[:, 0]
        ksi = _roll_vectorized(alpha, -subtri, axis=0)
        E = _roll_vectorized(ecc, -subtri, axis=0)
        x = ksi[:, 0, 0]
        y = ksi[:, 1, 0]
        z = ksi[:, 2, 0]
        d2V = _to_matrix_vectorized([
            [     6.*x,      6.*x,      6.*x],
            [     6.*y,        0.,        0.],
            [       0.,      6.*z,        0.],
            [     2.*z, 2.*z-4.*x, 2.*z-2.*x],
            [2.*y-4.*x,      2.*y, 2.*y-2.*x],
            [2.*x-4.*y,        0.,     -2.*y],
            [     2.*z,        0.,      2.*y],
            [       0.,      2.*y,      2.*z],
            [       0., 2.*x-4.*z,     -2.*z],
            [    -2.*z,     -2.*y,     x-y-z]])
        # Puts back d2V in first apex basis
        d2V = d2V @ _extract_submatrices(
            self.rotate_d2V, subtri, block_size=3, axis=0)
        prod = self.M @ d2V
        prod += _scalar_vectorized(E[:, 0, 0], self.M0 @ d2V)
        prod += _scalar_vectorized(E[:, 1, 0], self.M1 @ d2V)
        prod += _scalar_vectorized(E[:, 2, 0], self.M2 @ d2V)
        d2sdksi2 = _roll_vectorized(prod, 3*subtri, axis=0)
        return d2sdksi2

    def get_bending_matrices(self, J, ecc):
        """
        Parameters
        ----------
        *J* is a (N x 2 x 2) array of jacobian matrices (jacobian matrix at
        triangle first apex)
        *ecc* is a (N x 3 x 1) array (array of column-matrices) of triangle
        eccentricities

        Returns
        -------
        Returns the element K matrices for bending energy expressed in
        GLOBAL nodal coordinates.
        K_ij = integral [ (d2zi/dx2 + d2zi/dy2) * (d2zj/dx2 + d2zj/dy2) dA]
        tri_J is needed to rotate dofs from local basis to global basis
        """
        n = np.size(ecc, 0)

        # 1) matrix to rotate dofs in global coordinates
        J1 = self.J0_to_J1 @ J
        J2 = self.J0_to_J2 @ J
        DOF_rot = np.zeros([n, 9, 9], dtype=np.float64)
        DOF_rot[:, 0, 0] = 1
        DOF_rot[:, 3, 3] = 1
        DOF_rot[:, 6, 6] = 1
        DOF_rot[:, 1:3, 1:3] = J
        DOF_rot[:, 4:6, 4:6] = J1
        DOF_rot[:, 7:9, 7:9] = J2

        # 2) matrix to rotate Hessian in global coordinates.
        H_rot, area = self.get_Hrot_from_J(J, return_area=True)

        # 3) Computes stiffness matrix
        # Gauss quadrature.
        K = np.zeros([n, 9, 9], dtype=np.float64)
        weights = self.gauss_w
        pts = self.gauss_pts
        for igauss in range(self.n_gauss):
            alpha = np.tile(pts[igauss, :], n).reshape(n, 3)
            alpha = np.expand_dims(alpha, 2)
            weight = weights[igauss]
            d2Skdksi2 = self.get_d2Sidksij2(alpha, ecc)
            d2Skdx2 = d2Skdksi2 @ H_rot
            K += weight * (d2Skdx2 @ self.E @ _transpose_vectorized(d2Skdx2))

        # 4) With nodal (not elem) dofs
        K = _transpose_vectorized(DOF_rot) @ K @ DOF_rot

        # 5) Need the area to compute total element energy
        return _scalar_vectorized(area, K)

    def get_Hrot_from_J(self, J, return_area=False):
        """
        Parameters
        ----------
        *J* is a (N x 2 x 2) array of jacobian matrices (jacobian matrix at
        triangle first apex)

        Returns
        -------
        Returns H_rot used to rotate Hessian from local basis of first apex,
        to global coordinates.
        if *return_area* is True, returns also the triangle area (0.5*det(J))
        """
        # Here we try to deal with the simplest colinear cases; a null
        # energy and area is imposed.
        J_inv = _safe_inv22_vectorized(J)
        Ji00 = J_inv[:, 0, 0]
        Ji11 = J_inv[:, 1, 1]
        Ji10 = J_inv[:, 1, 0]
        Ji01 = J_inv[:, 0, 1]
        H_rot = _to_matrix_vectorized([
            [Ji00*Ji00, Ji10*Ji10, Ji00*Ji10],
            [Ji01*Ji01, Ji11*Ji11, Ji01*Ji11],
            [2*Ji00*Ji01, 2*Ji11*Ji10, Ji00*Ji11+Ji10*Ji01]])
        if not return_area:
            return H_rot
        else:
            area = 0.5 * (J[:, 0, 0]*J[:, 1, 1] - J[:, 0, 1]*J[:, 1, 0])
            return H_rot, area

    def get_Kff_and_Ff(self, J, ecc, triangles, Uc):
        """
        Build K and F for the following elliptic formulation:
        minimization of curvature energy with value of function at node
        imposed and derivatives 'free'.

        Build the global Kff matrix in cco format.
        Build the full Ff vec Ff = - Kfc x Uc.

        Parameters
        ----------
        *J* is a (N x 2 x 2) array of jacobian matrices (jacobian matrix at
        triangle first apex)
        *ecc* is a (N x 3 x 1) array (array of column-matrices) of triangle
        eccentricities
        *triangles* is a (N x 3) array of nodes indexes.
        *Uc* is (N x 3) array of imposed displacements at nodes

        Returns
        -------
        (Kff_rows, Kff_cols, Kff_vals) Kff matrix in coo format - Duplicate
        (row, col) entries must be summed.
        Ff: force vector - dim npts * 3
        """
        ntri = np.size(ecc, 0)
        vec_range = np.arange(ntri, dtype=np.int32)
        c_indices = np.full(ntri, -1, dtype=np.int32)  # for unused dofs, -1
        f_dof = [1, 2, 4, 5, 7, 8]
        c_dof = [0, 3, 6]

        # vals, rows and cols indices in global dof numbering
        f_dof_indices = _to_matrix_vectorized([[
            c_indices, triangles[:, 0]*2, triangles[:, 0]*2+1,
            c_indices, triangles[:, 1]*2, triangles[:, 1]*2+1,
            c_indices, triangles[:, 2]*2, triangles[:, 2]*2+1]])

        expand_indices = np.ones([ntri, 9, 1], dtype=np.int32)
        f_row_indices = _transpose_vectorized(expand_indices @ f_dof_indices)
        f_col_indices = expand_indices @ f_dof_indices
        K_elem = self.get_bending_matrices(J, ecc)

        # Extracting sub-matrices
        # Explanation & notations:
        # * Subscript f denotes 'free' degrees of freedom (i.e. dz/dx, dz/dx)
        # * Subscript c denotes 'condensated' (imposed) degrees of freedom
        #    (i.e. z at all nodes)
        # * F = [Ff, Fc] is the force vector
        # * U = [Uf, Uc] is the imposed dof vector
        #        [ Kff Kfc ]
        # * K =  [         ]  is the laplacian stiffness matrix
        #        [ Kcf Kff ]
        # * As F = K x U one gets straightforwardly: Ff = - Kfc x Uc

        # Computing Kff stiffness matrix in sparse coo format
        Kff_vals = np.ravel(K_elem[np.ix_(vec_range, f_dof, f_dof)])
        Kff_rows = np.ravel(f_row_indices[np.ix_(vec_range, f_dof, f_dof)])
        Kff_cols = np.ravel(f_col_indices[np.ix_(vec_range, f_dof, f_dof)])

        # Computing Ff force vector in sparse coo format
        Kfc_elem = K_elem[np.ix_(vec_range, f_dof, c_dof)]
        Uc_elem = np.expand_dims(Uc, axis=2)
        Ff_elem = -(Kfc_elem @ Uc_elem)[:, :, 0]
        Ff_indices = f_dof_indices[np.ix_(vec_range, [0], f_dof)][:, 0, :]

        # Extracting Ff force vector in dense format
        # We have to sum duplicate indices -  using bincount
        Ff = np.bincount(np.ravel(Ff_indices), weights=np.ravel(Ff_elem))
        return Kff_rows, Kff_cols, Kff_vals, Ff


# :class:_DOF_estimator, _DOF_estimator_user, _DOF_estimator_geom,
# _DOF_estimator_min_E
# Private classes used to compute the degree of freedom of each triangular
# element for the TriCubicInterpolator.
class _DOF_estimator:
    """
    Abstract base class for classes used to estimate a function's first
    derivatives, and deduce the dofs for a CubicTriInterpolator using a
    reduced HCT element formulation.

    Derived classes implement ``compute_df(self, **kwargs)``, returning
    ``np.vstack([dfx, dfy]).T`` where ``dfx, dfy`` are the estimation of the 2
    gradient coordinates.
    """
    def __init__(self, interpolator, **kwargs):
        _api.check_isinstance(CubicTriInterpolator, interpolator=interpolator)
        self._pts = interpolator._pts
        self._tris_pts = interpolator._tris_pts
        self.z = interpolator._z
        self._triangles = interpolator._triangles
        (self._unit_x, self._unit_y) = (interpolator._unit_x,
                                        interpolator._unit_y)
        self.dz = self.compute_dz(**kwargs)
        self.compute_dof_from_df()

    def compute_dz(self, **kwargs):
        raise NotImplementedError

    def compute_dof_from_df(self):
        """
        Compute reduced-HCT elements degrees of freedom, from the gradient.
        """
        J = CubicTriInterpolator._get_jacobian(self._tris_pts)
        tri_z = self.z[self._triangles]
        tri_dz = self.dz[self._triangles]
        tri_dof = self.get_dof_vec(tri_z, tri_dz, J)
        return tri_dof

    @staticmethod
    def get_dof_vec(tri_z, tri_dz, J):
        """
        Compute the dof vector of a triangle, from the value of f, df and
        of the local Jacobian at each node.

        Parameters
        ----------
        tri_z : shape (3,) array
            f nodal values.
        tri_dz : shape (3, 2) array
            df/dx, df/dy nodal values.
        J
            Jacobian matrix in local basis of apex 0.

        Returns
        -------
        dof : shape (9,) array
            For each apex ``iapex``::

                dof[iapex*3+0] = f(Ai)
                dof[iapex*3+1] = df(Ai).(AiAi+)
                dof[iapex*3+2] = df(Ai).(AiAi-)
        """
        npt = tri_z.shape[0]
        dof = np.zeros([npt, 9], dtype=np.float64)
        J1 = _ReducedHCT_Element.J0_to_J1 @ J
        J2 = _ReducedHCT_Element.J0_to_J2 @ J

        col0 = J @ np.expand_dims(tri_dz[:, 0, :], axis=2)
        col1 = J1 @ np.expand_dims(tri_dz[:, 1, :], axis=2)
        col2 = J2 @ np.expand_dims(tri_dz[:, 2, :], axis=2)

        dfdksi = _to_matrix_vectorized([
            [col0[:, 0, 0], col1[:, 0, 0], col2[:, 0, 0]],
            [col0[:, 1, 0], col1[:, 1, 0], col2[:, 1, 0]]])
        dof[:, 0:7:3] = tri_z
        dof[:, 1:8:3] = dfdksi[:, 0]
        dof[:, 2:9:3] = dfdksi[:, 1]
        return dof


class _DOF_estimator_user(_DOF_estimator):
    """dz is imposed by user; accounts for scaling if any."""

    def compute_dz(self, dz):
        (dzdx, dzdy) = dz
        dzdx = dzdx * self._unit_x
        dzdy = dzdy * self._unit_y
        return np.vstack([dzdx, dzdy]).T


class _DOF_estimator_geom(_DOF_estimator):
    """Fast 'geometric' approximation, recommended for large arrays."""

    def compute_dz(self):
        """
        self.df is computed as weighted average of _triangles sharing a common
        node. On each triangle itri f is first assumed linear (= ~f), which
        allows to compute d~f[itri]
        Then the following approximation of df nodal values is then proposed:
            f[ipt] = SUM ( w[itri] x d~f[itri] , for itri sharing apex ipt)
        The weighted coeff. w[itri] are proportional to the angle of the
        triangle itri at apex ipt
        """
        el_geom_w = self.compute_geom_weights()
        el_geom_grad = self.compute_geom_grads()

        # Sum of weights coeffs
        w_node_sum = np.bincount(np.ravel(self._triangles),
                                 weights=np.ravel(el_geom_w))

        # Sum of weighted df = (dfx, dfy)
        dfx_el_w = np.empty_like(el_geom_w)
        dfy_el_w = np.empty_like(el_geom_w)
        for iapex in range(3):
            dfx_el_w[:, iapex] = el_geom_w[:, iapex]*el_geom_grad[:, 0]
            dfy_el_w[:, iapex] = el_geom_w[:, iapex]*el_geom_grad[:, 1]
        dfx_node_sum = np.bincount(np.ravel(self._triangles),
                                   weights=np.ravel(dfx_el_w))
        dfy_node_sum = np.bincount(np.ravel(self._triangles),
                                   weights=np.ravel(dfy_el_w))

        # Estimation of df
        dfx_estim = dfx_node_sum/w_node_sum
        dfy_estim = dfy_node_sum/w_node_sum
        return np.vstack([dfx_estim, dfy_estim]).T

    def compute_geom_weights(self):
        """
        Build the (nelems, 3) weights coeffs of _triangles angles,
        renormalized so that np.sum(weights, axis=1) == np.ones(nelems)
        """
        weights = np.zeros([np.size(self._triangles, 0), 3])
        tris_pts = self._tris_pts
        for ipt in range(3):
            p0 = tris_pts[:, ipt % 3, :]
            p1 = tris_pts[:, (ipt+1) % 3, :]
            p2 = tris_pts[:, (ipt-1) % 3, :]
            alpha1 = np.arctan2(p1[:, 1]-p0[:, 1], p1[:, 0]-p0[:, 0])
            alpha2 = np.arctan2(p2[:, 1]-p0[:, 1], p2[:, 0]-p0[:, 0])
            # In the below formula we could take modulo 2. but
            # modulo 1. is safer regarding round-off errors (flat triangles).
            angle = np.abs(((alpha2-alpha1) / np.pi) % 1)
            # Weight proportional to angle up np.pi/2; null weight for
            # degenerated cases 0 and np.pi (note that *angle* is normalized
            # by np.pi).
            weights[:, ipt] = 0.5 - np.abs(angle-0.5)
        return weights

    def compute_geom_grads(self):
        """
        Compute the (global) gradient component of f assumed linear (~f).
        returns array df of shape (nelems, 2)
        df[ielem].dM[ielem] = dz[ielem] i.e. df = dz x dM = dM.T^-1 x dz
        """
        tris_pts = self._tris_pts
        tris_f = self.z[self._triangles]

        dM1 = tris_pts[:, 1, :] - tris_pts[:, 0, :]
        dM2 = tris_pts[:, 2, :] - tris_pts[:, 0, :]
        dM = np.dstack([dM1, dM2])
        # Here we try to deal with the simplest colinear cases: a null
        # gradient is assumed in this case.
        dM_inv = _safe_inv22_vectorized(dM)

        dZ1 = tris_f[:, 1] - tris_f[:, 0]
        dZ2 = tris_f[:, 2] - tris_f[:, 0]
        dZ = np.vstack([dZ1, dZ2]).T
        df = np.empty_like(dZ)

        # With np.einsum: could be ej,eji -> ej
        df[:, 0] = dZ[:, 0]*dM_inv[:, 0, 0] + dZ[:, 1]*dM_inv[:, 1, 0]
        df[:, 1] = dZ[:, 0]*dM_inv[:, 0, 1] + dZ[:, 1]*dM_inv[:, 1, 1]
        return df


class _DOF_estimator_min_E(_DOF_estimator_geom):
    """
    The 'smoothest' approximation, df is computed through global minimization
    of the bending energy:
      E(f) = integral[(d2z/dx2 + d2z/dy2 + 2 d2z/dxdy)**2 dA]
    """
    def __init__(self, Interpolator):
        self._eccs = Interpolator._eccs
        super().__init__(Interpolator)

    def compute_dz(self):
        """
        Elliptic solver for bending energy minimization.
        Uses a dedicated 'toy' sparse Jacobi PCG solver.
        """
        # Initial guess for iterative PCG solver.
        dz_init = super().compute_dz()
        Uf0 = np.ravel(dz_init)

        reference_element = _ReducedHCT_Element()
        J = CubicTriInterpolator._get_jacobian(self._tris_pts)
        eccs = self._eccs
        triangles = self._triangles
        Uc = self.z[self._triangles]

        # Building stiffness matrix and force vector in coo format
        Kff_rows, Kff_cols, Kff_vals, Ff = reference_element.get_Kff_and_Ff(
            J, eccs, triangles, Uc)

        # Building sparse matrix and solving minimization problem
        # We could use scipy.sparse direct solver; however to avoid this
        # external dependency an implementation of a simple PCG solver with
        # a simple diagonal Jacobi preconditioner is implemented.
        tol = 1.e-10
        n_dof = Ff.shape[0]
        Kff_coo = _Sparse_Matrix_coo(Kff_vals, Kff_rows, Kff_cols,
                                     shape=(n_dof, n_dof))
        Kff_coo.compress_csc()
        Uf, err = _cg(A=Kff_coo, b=Ff, x0=Uf0, tol=tol)
        # If the PCG did not converge, we return the best guess between Uf0
        # and Uf.
        err0 = np.linalg.norm(Kff_coo.dot(Uf0) - Ff)
        if err0 < err:
            # Maybe a good occasion to raise a warning here ?
            _api.warn_external("In TriCubicInterpolator initialization, "
                               "PCG sparse solver did not converge after "
                               "1000 iterations. `geom` approximation is "
                               "used instead of `min_E`")
            Uf = Uf0

        # Building dz from Uf
        dz = np.empty([self._pts.shape[0], 2], dtype=np.float64)
        dz[:, 0] = Uf[::2]
        dz[:, 1] = Uf[1::2]
        return dz


# The following private :class:_Sparse_Matrix_coo and :func:_cg provide
# a PCG sparse solver for (symmetric) elliptic problems.
class _Sparse_Matrix_coo:
    def __init__(self, vals, rows, cols, shape):
        """
        Create a sparse matrix in coo format.
        *vals*: arrays of values of non-null entries of the matrix
        *rows*: int arrays of rows of non-null entries of the matrix
        *cols*: int arrays of cols of non-null entries of the matrix
        *shape*: 2-tuple (n, m) of matrix shape
        """
        self.n, self.m = shape
        self.vals = np.asarray(vals, dtype=np.float64)
        self.rows = np.asarray(rows, dtype=np.int32)
        self.cols = np.asarray(cols, dtype=np.int32)

    def dot(self, V):
        """
        Dot product of self by a vector *V* in sparse-dense to dense format
        *V* dense vector of shape (self.m,).
        """
        assert V.shape == (self.m,)
        return np.bincount(self.rows,
                           weights=self.vals*V[self.cols],
                           minlength=self.m)

    def compress_csc(self):
        """
        Compress rows, cols, vals / summing duplicates. Sort for csc format.
        """
        _, unique, indices = np.unique(
            self.rows + self.n*self.cols,
            return_index=True, return_inverse=True)
        self.rows = self.rows[unique]
        self.cols = self.cols[unique]
        self.vals = np.bincount(indices, weights=self.vals)

    def compress_csr(self):
        """
        Compress rows, cols, vals / summing duplicates. Sort for csr format.
        """
        _, unique, indices = np.unique(
            self.m*self.rows + self.cols,
            return_index=True, return_inverse=True)
        self.rows = self.rows[unique]
        self.cols = self.cols[unique]
        self.vals = np.bincount(indices, weights=self.vals)

    def to_dense(self):
        """
        Return a dense matrix representing self, mainly for debugging purposes.
        """
        ret = np.zeros([self.n, self.m], dtype=np.float64)
        nvals = self.vals.size
        for i in range(nvals):
            ret[self.rows[i], self.cols[i]] += self.vals[i]
        return ret

    def __str__(self):
        return self.to_dense().__str__()

    @property
    def diag(self):
        """Return the (dense) vector of the diagonal elements."""
        in_diag = (self.rows == self.cols)
        diag = np.zeros(min(self.n, self.n), dtype=np.float64)  # default 0.
        diag[self.rows[in_diag]] = self.vals[in_diag]
        return diag


def _cg(A, b, x0=None, tol=1.e-10, maxiter=1000):
    """
    Use Preconditioned Conjugate Gradient iteration to solve A x = b
    A simple Jacobi (diagonal) preconditioner is used.

    Parameters
    ----------
    A : _Sparse_Matrix_coo
        *A* must have been compressed before by compress_csc or
        compress_csr method.
    b : array
        Right hand side of the linear system.
    x0 : array, optional
        Starting guess for the solution. Defaults to the zero vector.
    tol : float, optional
        Tolerance to achieve. The algorithm terminates when the relative
        residual is below tol. Default is 1e-10.
    maxiter : int, optional
        Maximum number of iterations.  Iteration will stop after *maxiter*
        steps even if the specified tolerance has not been achieved. Defaults
        to 1000.

    Returns
    -------
    x : array
        The converged solution.
    err : float
        The absolute error np.linalg.norm(A.dot(x) - b)
    """
    n = b.size
    assert A.n == n
    assert A.m == n
    b_norm = np.linalg.norm(b)

    # Jacobi pre-conditioner
    kvec = A.diag
    # For diag elem < 1e-6 we keep 1e-6.
    kvec = np.maximum(kvec, 1e-6)

    # Initial guess
    if x0 is None:
        x = np.zeros(n)
    else:
        x = x0

    r = b - A.dot(x)
    w = r/kvec

    p = np.zeros(n)
    beta = 0.0
    rho = np.dot(r, w)
    k = 0

    # Following C. T. Kelley
    while (np.sqrt(abs(rho)) > tol*b_norm) and (k < maxiter):
        p = w + beta*p
        z = A.dot(p)
        alpha = rho/np.dot(p, z)
        r = r - alpha*z
        w = r/kvec
        rhoold = rho
        rho = np.dot(r, w)
        x = x + alpha*p
        beta = rho/rhoold
        # err = np.linalg.norm(A.dot(x) - b)  # absolute accuracy - not used
        k += 1
    err = np.linalg.norm(A.dot(x) - b)
    return x, err


# The following private functions:
#     :func:`_safe_inv22_vectorized`
#     :func:`_pseudo_inv22sym_vectorized`
#     :func:`_scalar_vectorized`
#     :func:`_transpose_vectorized`
#     :func:`_roll_vectorized`
#     :func:`_to_matrix_vectorized`
#     :func:`_extract_submatrices`
# provide fast numpy implementation of some standard operations on arrays of
# matrices - stored as (:, n_rows, n_cols)-shaped np.arrays.

# Development note: Dealing with pathologic 'flat' triangles in the
# CubicTriInterpolator code and impact on (2, 2)-matrix inversion functions
# :func:`_safe_inv22_vectorized` and :func:`_pseudo_inv22sym_vectorized`.
#
# Goals:
# 1) The CubicTriInterpolator should be able to handle flat or almost flat
#    triangles without raising an error,
# 2) These degenerated triangles should have no impact on the automatic dof
#    calculation (associated with null weight for the _DOF_estimator_geom and
#    with null energy for the _DOF_estimator_min_E),
# 3) Linear patch test should be passed exactly on degenerated meshes,
# 4) Interpolation (with :meth:`_interpolate_single_key` or
#    :meth:`_interpolate_multi_key`) shall be correctly handled even *inside*
#    the pathologic triangles, to interact correctly with a TriRefiner class.
#
# Difficulties:
# Flat triangles have rank-deficient *J* (so-called jacobian matrix) and
# *metric* (the metric tensor = J x J.T). Computation of the local
# tangent plane is also problematic.
#
# Implementation:
# Most of the time, when computing the inverse of a rank-deficient matrix it
# is safe to simply return the null matrix (which is the implementation in
# :func:`_safe_inv22_vectorized`). This is because of point 2), itself
# enforced by:
#    - null area hence null energy in :class:`_DOF_estimator_min_E`
#    - angles close or equal to 0 or np.pi hence null weight in
#      :class:`_DOF_estimator_geom`.
#      Note that the function angle -> weight is continuous and maximum for an
#      angle np.pi/2 (refer to :meth:`compute_geom_weights`)
# The exception is the computation of barycentric coordinates, which is done
# by inversion of the *metric* matrix. In this case, we need to compute a set
# of valid coordinates (1 among numerous possibilities), to ensure point 4).
# We benefit here from the symmetry of metric = J x J.T, which makes it easier
# to compute a pseudo-inverse in :func:`_pseudo_inv22sym_vectorized`
def _safe_inv22_vectorized(M):
    """
    Inversion of arrays of (2, 2) matrices, returns 0 for rank-deficient
    matrices.

    *M* : array of (2, 2) matrices to inverse, shape (n, 2, 2)
    """
    _api.check_shape((None, 2, 2), M=M)
    M_inv = np.empty_like(M)
    prod1 = M[:, 0, 0]*M[:, 1, 1]
    delta = prod1 - M[:, 0, 1]*M[:, 1, 0]

    # We set delta_inv to 0. in case of a rank deficient matrix; a
    # rank-deficient input matrix *M* will lead to a null matrix in output
    rank2 = (np.abs(delta) > 1e-8*np.abs(prod1))
    if np.all(rank2):
        # Normal 'optimized' flow.
        delta_inv = 1./delta
    else:
        # 'Pathologic' flow.
        delta_inv = np.zeros(M.shape[0])
        delta_inv[rank2] = 1./delta[rank2]

    M_inv[:, 0, 0] = M[:, 1, 1]*delta_inv
    M_inv[:, 0, 1] = -M[:, 0, 1]*delta_inv
    M_inv[:, 1, 0] = -M[:, 1, 0]*delta_inv
    M_inv[:, 1, 1] = M[:, 0, 0]*delta_inv
    return M_inv


def _pseudo_inv22sym_vectorized(M):
    """
    Inversion of arrays of (2, 2) SYMMETRIC matrices; returns the
    (Moore-Penrose) pseudo-inverse for rank-deficient matrices.

    In case M is of rank 1, we have M = trace(M) x P where P is the orthogonal
    projection on Im(M), and we return trace(M)^-1 x P == M / trace(M)**2
    In case M is of rank 0, we return the null matrix.

    *M* : array of (2, 2) matrices to inverse, shape (n, 2, 2)
    """
    _api.check_shape((None, 2, 2), M=M)
    M_inv = np.empty_like(M)
    prod1 = M[:, 0, 0]*M[:, 1, 1]
    delta = prod1 - M[:, 0, 1]*M[:, 1, 0]
    rank2 = (np.abs(delta) > 1e-8*np.abs(prod1))

    if np.all(rank2):
        # Normal 'optimized' flow.
        M_inv[:, 0, 0] = M[:, 1, 1] / delta
        M_inv[:, 0, 1] = -M[:, 0, 1] / delta
        M_inv[:, 1, 0] = -M[:, 1, 0] / delta
        M_inv[:, 1, 1] = M[:, 0, 0] / delta
    else:
        # 'Pathologic' flow.
        # Here we have to deal with 2 sub-cases
        # 1) First sub-case: matrices of rank 2:
        delta = delta[rank2]
        M_inv[rank2, 0, 0] = M[rank2, 1, 1] / delta
        M_inv[rank2, 0, 1] = -M[rank2, 0, 1] / delta
        M_inv[rank2, 1, 0] = -M[rank2, 1, 0] / delta
        M_inv[rank2, 1, 1] = M[rank2, 0, 0] / delta
        # 2) Second sub-case: rank-deficient matrices of rank 0 and 1:
        rank01 = ~rank2
        tr = M[rank01, 0, 0] + M[rank01, 1, 1]
        tr_zeros = (np.abs(tr) < 1.e-8)
        sq_tr_inv = (1.-tr_zeros) / (tr**2+tr_zeros)
        # sq_tr_inv = 1. / tr**2
        M_inv[rank01, 0, 0] = M[rank01, 0, 0] * sq_tr_inv
        M_inv[rank01, 0, 1] = M[rank01, 0, 1] * sq_tr_inv
        M_inv[rank01, 1, 0] = M[rank01, 1, 0] * sq_tr_inv
        M_inv[rank01, 1, 1] = M[rank01, 1, 1] * sq_tr_inv

    return M_inv


def _scalar_vectorized(scalar, M):
    """
    Scalar product between scalars and matrices.
    """
    return scalar[:, np.newaxis, np.newaxis]*M


def _transpose_vectorized(M):
    """
    Transposition of an array of matrices *M*.
    """
    return np.transpose(M, [0, 2, 1])


def _roll_vectorized(M, roll_indices, axis):
    """
    Roll an array of matrices along *axis* (0: rows, 1: columns) according to
    an array of indices *roll_indices*.
    """
    assert axis in [0, 1]
    ndim = M.ndim
    assert ndim == 3
    ndim_roll = roll_indices.ndim
    assert ndim_roll == 1
    sh = M.shape
    r, c = sh[-2:]
    assert sh[0] == roll_indices.shape[0]
    vec_indices = np.arange(sh[0], dtype=np.int32)

    # Builds the rolled matrix
    M_roll = np.empty_like(M)
    if axis == 0:
        for ir in range(r):
            for ic in range(c):
                M_roll[:, ir, ic] = M[vec_indices, (-roll_indices+ir) % r, ic]
    else:  # 1
        for ir in range(r):
            for ic in range(c):
                M_roll[:, ir, ic] = M[vec_indices, ir, (-roll_indices+ic) % c]
    return M_roll


def _to_matrix_vectorized(M):
    """
    Build an array of matrices from individuals np.arrays of identical shapes.

    Parameters
    ----------
    M
        ncols-list of nrows-lists of shape sh.

    Returns
    -------
    M_res : np.array of shape (sh, nrow, ncols)
        *M_res* satisfies ``M_res[..., i, j] = M[i][j]``.
    """
    assert isinstance(M, (tuple, list))
    assert all(isinstance(item, (tuple, list)) for item in M)
    c_vec = np.asarray([len(item) for item in M])
    assert np.all(c_vec-c_vec[0] == 0)
    r = len(M)
    c = c_vec[0]
    M00 = np.asarray(M[0][0])
    dt = M00.dtype
    sh = [M00.shape[0], r, c]
    M_ret = np.empty(sh, dtype=dt)
    for irow in range(r):
        for icol in range(c):
            M_ret[:, irow, icol] = np.asarray(M[irow][icol])
    return M_ret


def _extract_submatrices(M, block_indices, block_size, axis):
    """
    Extract selected blocks of a matrices *M* depending on parameters
    *block_indices* and *block_size*.

    Returns the array of extracted matrices *Mres* so that ::

        M_res[..., ir, :] = M[(block_indices*block_size+ir), :]
    """
    assert block_indices.ndim == 1
    assert axis in [0, 1]

    r, c = M.shape
    if axis == 0:
        sh = [block_indices.shape[0], block_size, c]
    else:  # 1
        sh = [block_indices.shape[0], r, block_size]

    dt = M.dtype
    M_res = np.empty(sh, dtype=dt)
    if axis == 0:
        for ir in range(block_size):
            M_res[:, ir, :] = M[(block_indices*block_size+ir), :]
    else:  # 1
        for ic in range(block_size):
            M_res[:, :, ic] = M[:, (block_indices*block_size+ic)]

    return M_res
