"""
Mesh refinement for triangular grids.
"""

import numpy as np

from matplotlib import _api
from matplotlib.tri._triangulation import Triangulation
import matplotlib.tri._triinterpolate


class TriRefiner:
    """
    Abstract base class for classes implementing mesh refinement.

    A TriRefiner encapsulates a Triangulation object and provides tools for
    mesh refinement and interpolation.

    Derived classes must implement:

    - ``refine_triangulation(return_tri_index=False, **kwargs)`` , where
      the optional keyword arguments *kwargs* are defined in each
      TriRefiner concrete implementation, and which returns:

      - a refined triangulation,
      - optionally (depending on *return_tri_index*), for each
        point of the refined triangulation: the index of
        the initial triangulation triangle to which it belongs.

    - ``refine_field(z, triinterpolator=None, **kwargs)``, where:

      - *z* array of field values (to refine) defined at the base
        triangulation nodes,
      - *triinterpolator* is an optional `~matplotlib.tri.TriInterpolator`,
      - the other optional keyword arguments *kwargs* are defined in
        each TriRefiner concrete implementation;

      and which returns (as a tuple) a refined triangular mesh and the
      interpolated values of the field at the refined triangulation nodes.
    """

    def __init__(self, triangulation):
        _api.check_isinstance(Triangulation, triangulation=triangulation)
        self._triangulation = triangulation


class UniformTriRefiner(TriRefiner):
    """
    Uniform mesh refinement by recursive subdivisions.

    Parameters
    ----------
    triangulation : `~matplotlib.tri.Triangulation`
        The encapsulated triangulation (to be refined)
    """
#    See Also
#    --------
#    :class:`~matplotlib.tri.CubicTriInterpolator` and
#    :class:`~matplotlib.tri.TriAnalyzer`.
#    """
    def __init__(self, triangulation):
        super().__init__(triangulation)

    def refine_triangulation(self, return_tri_index=False, subdiv=3):
        """
        Compute a uniformly refined triangulation *refi_triangulation* of
        the encapsulated :attr:`triangulation`.

        This function refines the encapsulated triangulation by splitting each
        father triangle into 4 child sub-triangles built on the edges midside
        nodes, recursing *subdiv* times.  In the end, each triangle is hence
        divided into ``4**subdiv`` child triangles.

        Parameters
        ----------
        return_tri_index : bool, default: False
            Whether an index table indicating the father triangle index of each
            point is returned.
        subdiv : int, default: 3
            Recursion level for the subdivision.
            Each triangle is divided into ``4**subdiv`` child triangles;
            hence, the default results in 64 refined subtriangles for each
            triangle of the initial triangulation.

        Returns
        -------
        refi_triangulation : `~matplotlib.tri.Triangulation`
            The refined triangulation.
        found_index : int array
            Index of the initial triangulation containing triangle, for each
            point of *refi_triangulation*.
            Returned only if *return_tri_index* is set to True.
        """
        refi_triangulation = self._triangulation
        ntri = refi_triangulation.triangles.shape[0]

        # Computes the triangulation ancestors numbers in the reference
        # triangulation.
        ancestors = np.arange(ntri, dtype=np.int32)
        for _ in range(subdiv):
            refi_triangulation, ancestors = self._refine_triangulation_once(
                refi_triangulation, ancestors)
        refi_npts = refi_triangulation.x.shape[0]
        refi_triangles = refi_triangulation.triangles

        # Now we compute found_index table if needed
        if return_tri_index:
            # We have to initialize found_index with -1 because some nodes
            # may very well belong to no triangle at all, e.g., in case of
            # Delaunay Triangulation with DuplicatePointWarning.
            found_index = np.full(refi_npts, -1, dtype=np.int32)
            tri_mask = self._triangulation.mask
            if tri_mask is None:
                found_index[refi_triangles] = np.repeat(ancestors,
                                                        3).reshape(-1, 3)
            else:
                # There is a subtlety here: we want to avoid whenever possible
                # that refined points container is a masked triangle (which
                # would result in artifacts in plots).
                # So we impose the numbering from masked ancestors first,
                # then overwrite it with unmasked ancestor numbers.
                ancestor_mask = tri_mask[ancestors]
                found_index[refi_triangles[ancestor_mask, :]
                            ] = np.repeat(ancestors[ancestor_mask],
                                          3).reshape(-1, 3)
                found_index[refi_triangles[~ancestor_mask, :]
                            ] = np.repeat(ancestors[~ancestor_mask],
                                          3).reshape(-1, 3)
            return refi_triangulation, found_index
        else:
            return refi_triangulation

    def refine_field(self, z, triinterpolator=None, subdiv=3):
        """
        Refine a field defined on the encapsulated triangulation.

        Parameters
        ----------
        z : (npoints,) array-like
            Values of the field to refine, defined at the nodes of the
            encapsulated triangulation. (``n_points`` is the number of points
            in the initial triangulation)
        triinterpolator : `~matplotlib.tri.TriInterpolator`, optional
            Interpolator used for field interpolation. If not specified,
            a `~matplotlib.tri.CubicTriInterpolator` will be used.
        subdiv : int, default: 3
            Recursion level for the subdivision.
            Each triangle is divided into ``4**subdiv`` child triangles.

        Returns
        -------
        refi_tri : `~matplotlib.tri.Triangulation`
             The returned refined triangulation.
        refi_z : 1D array of length: *refi_tri* node count.
             The returned interpolated field (at *refi_tri* nodes).
        """
        if triinterpolator is None:
            interp = matplotlib.tri.CubicTriInterpolator(
                self._triangulation, z)
        else:
            _api.check_isinstance(matplotlib.tri.TriInterpolator,
                                  triinterpolator=triinterpolator)
            interp = triinterpolator

        refi_tri, found_index = self.refine_triangulation(
            subdiv=subdiv, return_tri_index=True)
        refi_z = interp._interpolate_multikeys(
            refi_tri.x, refi_tri.y, tri_index=found_index)[0]
        return refi_tri, refi_z

    @staticmethod
    def _refine_triangulation_once(triangulation, ancestors=None):
        """
        Refine a `.Triangulation` by splitting each triangle into 4
        child-masked_triangles built on the edges midside nodes.

        Masked triangles, if present, are also split, but their children
        returned masked.

        If *ancestors* is not provided, returns only a new triangulation:
        child_triangulation.

        If the array-like key table *ancestor* is given, it shall be of shape
        (ntri,) where ntri is the number of *triangulation* masked_triangles.
        In this case, the function returns
        (child_triangulation, child_ancestors)
        child_ancestors is defined so that the 4 child masked_triangles share
        the same index as their father: child_ancestors.shape = (4 * ntri,).
        """

        x = triangulation.x
        y = triangulation.y

        #    According to tri.triangulation doc:
        #         neighbors[i, j] is the triangle that is the neighbor
        #         to the edge from point index masked_triangles[i, j] to point
        #         index masked_triangles[i, (j+1)%3].
        neighbors = triangulation.neighbors
        triangles = triangulation.triangles
        npts = np.shape(x)[0]
        ntri = np.shape(triangles)[0]
        if ancestors is not None:
            ancestors = np.asarray(ancestors)
            if np.shape(ancestors) != (ntri,):
                raise ValueError(
                    "Incompatible shapes provide for "
                    "triangulation.masked_triangles and ancestors: "
                    f"{np.shape(triangles)} and {np.shape(ancestors)}")

        # Initiating tables refi_x and refi_y of the refined triangulation
        # points
        # hint: each apex is shared by 2 masked_triangles except the borders.
        borders = np.sum(neighbors == -1)
        added_pts = (3*ntri + borders) // 2
        refi_npts = npts + added_pts
        refi_x = np.zeros(refi_npts)
        refi_y = np.zeros(refi_npts)

        # First part of refi_x, refi_y is just the initial points
        refi_x[:npts] = x
        refi_y[:npts] = y

        # Second part contains the edge midside nodes.
        # Each edge belongs to 1 triangle (if border edge) or is shared by 2
        # masked_triangles (interior edge).
        # We first build 2 * ntri arrays of edge starting nodes (edge_elems,
        # edge_apexes); we then extract only the masters to avoid overlaps.
        # The so-called 'master' is the triangle with biggest index
        # The 'slave' is the triangle with lower index
        # (can be -1 if border edge)
        # For slave and master we will identify the apex pointing to the edge
        # start
        edge_elems = np.tile(np.arange(ntri, dtype=np.int32), 3)
        edge_apexes = np.repeat(np.arange(3, dtype=np.int32), ntri)
        edge_neighbors = neighbors[edge_elems, edge_apexes]
        mask_masters = (edge_elems > edge_neighbors)

        # Identifying the "masters" and adding to refi_x, refi_y vec
        masters = edge_elems[mask_masters]
        apex_masters = edge_apexes[mask_masters]
        x_add = (x[triangles[masters, apex_masters]] +
                 x[triangles[masters, (apex_masters+1) % 3]]) * 0.5
        y_add = (y[triangles[masters, apex_masters]] +
                 y[triangles[masters, (apex_masters+1) % 3]]) * 0.5
        refi_x[npts:] = x_add
        refi_y[npts:] = y_add

        # Building the new masked_triangles; each old masked_triangles hosts
        # 4 new masked_triangles
        # there are 6 pts to identify per 'old' triangle, 3 new_pt_corner and
        # 3 new_pt_midside
        new_pt_corner = triangles

        # What is the index in refi_x, refi_y of point at middle of apex iapex
        #  of elem ielem ?
        # If ielem is the apex master: simple count, given the way refi_x was
        #  built.
        # If ielem is the apex slave: yet we do not know; but we will soon
        # using the neighbors table.
        new_pt_midside = np.empty([ntri, 3], dtype=np.int32)
        cum_sum = npts
        for imid in range(3):
            mask_st_loc = (imid == apex_masters)
            n_masters_loc = np.sum(mask_st_loc)
            elem_masters_loc = masters[mask_st_loc]
            new_pt_midside[:, imid][elem_masters_loc] = np.arange(
                n_masters_loc, dtype=np.int32) + cum_sum
            cum_sum += n_masters_loc

        # Now dealing with slave elems.
        # for each slave element we identify the master and then the inode
        # once slave_masters is identified, slave_masters_apex is such that:
        # neighbors[slaves_masters, slave_masters_apex] == slaves
        mask_slaves = np.logical_not(mask_masters)
        slaves = edge_elems[mask_slaves]
        slaves_masters = edge_neighbors[mask_slaves]
        diff_table = np.abs(neighbors[slaves_masters, :] -
                            np.outer(slaves, np.ones(3, dtype=np.int32)))
        slave_masters_apex = np.argmin(diff_table, axis=1)
        slaves_apex = edge_apexes[mask_slaves]
        new_pt_midside[slaves, slaves_apex] = new_pt_midside[
            slaves_masters, slave_masters_apex]

        # Builds the 4 child masked_triangles
        child_triangles = np.empty([ntri*4, 3], dtype=np.int32)
        child_triangles[0::4, :] = np.vstack([
            new_pt_corner[:, 0], new_pt_midside[:, 0],
            new_pt_midside[:, 2]]).T
        child_triangles[1::4, :] = np.vstack([
            new_pt_corner[:, 1], new_pt_midside[:, 1],
            new_pt_midside[:, 0]]).T
        child_triangles[2::4, :] = np.vstack([
            new_pt_corner[:, 2], new_pt_midside[:, 2],
            new_pt_midside[:, 1]]).T
        child_triangles[3::4, :] = np.vstack([
            new_pt_midside[:, 0], new_pt_midside[:, 1],
            new_pt_midside[:, 2]]).T
        child_triangulation = Triangulation(refi_x, refi_y, child_triangles)

        # Builds the child mask
        if triangulation.mask is not None:
            child_triangulation.set_mask(np.repeat(triangulation.mask, 4))

        if ancestors is None:
            return child_triangulation
        else:
            return child_triangulation, np.repeat(ancestors, 4)
