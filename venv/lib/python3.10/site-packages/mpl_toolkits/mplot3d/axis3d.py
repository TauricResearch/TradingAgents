# axis3d.py, original mplot3d version by John Porter
# Created: 23 Sep 2005
# Parts rewritten by Reinier Heeres <reinier@heeres.eu>

import inspect

import numpy as np

import matplotlib as mpl
from matplotlib import (
    _api, artist, lines as mlines, axis as maxis, patches as mpatches,
    transforms as mtransforms, colors as mcolors)
from . import art3d, proj3d


def _move_from_center(coord, centers, deltas, axmask=(True, True, True)):
    """
    For each coordinate where *axmask* is True, move *coord* away from
    *centers* by *deltas*.
    """
    coord = np.asarray(coord)
    return coord + axmask * np.copysign(1, coord - centers) * deltas


def _tick_update_position(tick, tickxs, tickys, labelpos):
    """Update tick line and label position and style."""

    tick.label1.set_position(labelpos)
    tick.label2.set_position(labelpos)
    tick.tick1line.set_visible(True)
    tick.tick2line.set_visible(False)
    tick.tick1line.set_linestyle('-')
    tick.tick1line.set_marker('')
    tick.tick1line.set_data(tickxs, tickys)
    tick.gridline.set_data([0], [0])


class Axis(maxis.XAxis):
    """An Axis class for the 3D plots."""
    # These points from the unit cube make up the x, y and z-planes
    _PLANES = (
        (0, 3, 7, 4), (1, 2, 6, 5),  # yz planes
        (0, 1, 5, 4), (3, 2, 6, 7),  # xz planes
        (0, 1, 2, 3), (4, 5, 6, 7),  # xy planes
    )

    # Some properties for the axes
    _AXINFO = {
        'x': {'i': 0, 'tickdir': 1, 'juggled': (1, 0, 2)},
        'y': {'i': 1, 'tickdir': 0, 'juggled': (0, 1, 2)},
        'z': {'i': 2, 'tickdir': 0, 'juggled': (0, 2, 1)},
    }

    def _old_init(self, adir, v_intervalx, d_intervalx, axes, *args,
                  rotate_label=None, **kwargs):
        return locals()

    def _new_init(self, axes, *, rotate_label=None, **kwargs):
        return locals()

    def __init__(self, *args, **kwargs):
        params = _api.select_matching_signature(
            [self._old_init, self._new_init], *args, **kwargs)
        if "adir" in params:
            _api.warn_deprecated(
                "3.6", message=f"The signature of 3D Axis constructors has "
                f"changed in %(since)s; the new signature is "
                f"{inspect.signature(type(self).__init__)}", pending=True)
            if params["adir"] != self.axis_name:
                raise ValueError(f"Cannot instantiate {type(self).__name__} "
                                 f"with adir={params['adir']!r}")
        axes = params["axes"]
        rotate_label = params["rotate_label"]
        args = params.get("args", ())
        kwargs = params["kwargs"]

        name = self.axis_name

        self._label_position = 'default'
        self._tick_position = 'default'

        # This is a temporary member variable.
        # Do not depend on this existing in future releases!
        self._axinfo = self._AXINFO[name].copy()
        # Common parts
        self._axinfo.update({
            'label': {'va': 'center', 'ha': 'center',
                      'rotation_mode': 'anchor'},
            'color': mpl.rcParams[f'axes3d.{name}axis.panecolor'],
            'tick': {
                'inward_factor': 0.2,
                'outward_factor': 0.1,
            },
        })

        if mpl.rcParams['_internal.classic_mode']:
            self._axinfo.update({
                'axisline': {'linewidth': 0.75, 'color': (0, 0, 0, 1)},
                'grid': {
                    'color': (0.9, 0.9, 0.9, 1),
                    'linewidth': 1.0,
                    'linestyle': '-',
                },
            })
            self._axinfo['tick'].update({
                'linewidth': {
                    True: mpl.rcParams['lines.linewidth'],  # major
                    False: mpl.rcParams['lines.linewidth'],  # minor
                }
            })
        else:
            self._axinfo.update({
                'axisline': {
                    'linewidth': mpl.rcParams['axes.linewidth'],
                    'color': mpl.rcParams['axes.edgecolor'],
                },
                'grid': {
                    'color': mpl.rcParams['grid.color'],
                    'linewidth': mpl.rcParams['grid.linewidth'],
                    'linestyle': mpl.rcParams['grid.linestyle'],
                },
            })
            self._axinfo['tick'].update({
                'linewidth': {
                    True: (  # major
                        mpl.rcParams['xtick.major.width'] if name in 'xz'
                        else mpl.rcParams['ytick.major.width']),
                    False: (  # minor
                        mpl.rcParams['xtick.minor.width'] if name in 'xz'
                        else mpl.rcParams['ytick.minor.width']),
                }
            })

        super().__init__(axes, *args, **kwargs)

        # data and viewing intervals for this direction
        if "d_intervalx" in params:
            self.set_data_interval(*params["d_intervalx"])
        if "v_intervalx" in params:
            self.set_view_interval(*params["v_intervalx"])
        self.set_rotate_label(rotate_label)
        self._init3d()  # Inline after init3d deprecation elapses.

    __init__.__signature__ = inspect.signature(_new_init)
    adir = _api.deprecated("3.6", pending=True)(
        property(lambda self: self.axis_name))

    def _init3d(self):
        self.line = mlines.Line2D(
            xdata=(0, 0), ydata=(0, 0),
            linewidth=self._axinfo['axisline']['linewidth'],
            color=self._axinfo['axisline']['color'],
            antialiased=True)

        # Store dummy data in Polygon object
        self.pane = mpatches.Polygon([[0, 0], [0, 1]], closed=False)
        self.set_pane_color(self._axinfo['color'])

        self.axes._set_artist_props(self.line)
        self.axes._set_artist_props(self.pane)
        self.gridlines = art3d.Line3DCollection([])
        self.axes._set_artist_props(self.gridlines)
        self.axes._set_artist_props(self.label)
        self.axes._set_artist_props(self.offsetText)
        # Need to be able to place the label at the correct location
        self.label._transform = self.axes.transData
        self.offsetText._transform = self.axes.transData

    @_api.deprecated("3.6", pending=True)
    def init3d(self):  # After deprecation elapses, inline _init3d to __init__.
        self._init3d()

    def get_major_ticks(self, numticks=None):
        ticks = super().get_major_ticks(numticks)
        for t in ticks:
            for obj in [
                    t.tick1line, t.tick2line, t.gridline, t.label1, t.label2]:
                obj.set_transform(self.axes.transData)
        return ticks

    def get_minor_ticks(self, numticks=None):
        ticks = super().get_minor_ticks(numticks)
        for t in ticks:
            for obj in [
                    t.tick1line, t.tick2line, t.gridline, t.label1, t.label2]:
                obj.set_transform(self.axes.transData)
        return ticks

    def set_ticks_position(self, position):
        """
        Set the ticks position.

        Parameters
        ----------
        position : {'lower', 'upper', 'both', 'default', 'none'}
            The position of the bolded axis lines, ticks, and tick labels.
        """
        _api.check_in_list(['lower', 'upper', 'both', 'default', 'none'],
                           position=position)
        self._tick_position = position

    def get_ticks_position(self):
        """
        Get the ticks position.

        Returns
        -------
        str : {'lower', 'upper', 'both', 'default', 'none'}
            The position of the bolded axis lines, ticks, and tick labels.
        """
        return self._tick_position

    def set_label_position(self, position):
        """
        Set the label position.

        Parameters
        ----------
        position : {'lower', 'upper', 'both', 'default', 'none'}
            The position of the axis label.
        """
        _api.check_in_list(['lower', 'upper', 'both', 'default', 'none'],
                           position=position)
        self._label_position = position

    def get_label_position(self):
        """
        Get the label position.

        Returns
        -------
        str : {'lower', 'upper', 'both', 'default', 'none'}
            The position of the axis label.
        """
        return self._label_position

    def set_pane_color(self, color, alpha=None):
        """
        Set pane color.

        Parameters
        ----------
        color : :mpltype:`color`
            Color for axis pane.
        alpha : float, optional
            Alpha value for axis pane. If None, base it on *color*.
        """
        color = mcolors.to_rgba(color, alpha)
        self._axinfo['color'] = color
        self.pane.set_edgecolor(color)
        self.pane.set_facecolor(color)
        self.pane.set_alpha(color[-1])
        self.stale = True

    def set_rotate_label(self, val):
        """
        Whether to rotate the axis label: True, False or None.
        If set to None the label will be rotated if longer than 4 chars.
        """
        self._rotate_label = val
        self.stale = True

    def get_rotate_label(self, text):
        if self._rotate_label is not None:
            return self._rotate_label
        else:
            return len(text) > 4

    def _get_coord_info(self):
        mins, maxs = np.array([
            self.axes.get_xbound(),
            self.axes.get_ybound(),
            self.axes.get_zbound(),
        ]).T

        # Project the bounds along the current position of the cube:
        bounds = mins[0], maxs[0], mins[1], maxs[1], mins[2], maxs[2]
        bounds_proj = self.axes._transformed_cube(bounds)

        # Determine which one of the parallel planes are higher up:
        means_z0 = np.zeros(3)
        means_z1 = np.zeros(3)
        for i in range(3):
            means_z0[i] = np.mean(bounds_proj[self._PLANES[2 * i], 2])
            means_z1[i] = np.mean(bounds_proj[self._PLANES[2 * i + 1], 2])
        highs = means_z0 < means_z1

        # Special handling for edge-on views
        equals = np.abs(means_z0 - means_z1) <= np.finfo(float).eps
        if np.sum(equals) == 2:
            vertical = np.where(~equals)[0][0]
            if vertical == 2:  # looking at XY plane
                highs = np.array([True, True, highs[2]])
            elif vertical == 1:  # looking at XZ plane
                highs = np.array([True, highs[1], False])
            elif vertical == 0:  # looking at YZ plane
                highs = np.array([highs[0], False, False])

        return mins, maxs, bounds_proj, highs

    def _calc_centers_deltas(self, maxs, mins):
        centers = 0.5 * (maxs + mins)
        # In mpl3.8, the scale factor was 1/12. mpl3.9 changes this to
        # 1/12 * 24/25 = 0.08 to compensate for the change in automargin
        # behavior and keep appearance the same. The 24/25 factor is from the
        # 1/48 padding added to each side of the axis in mpl3.8.
        scale = 0.08
        deltas = (maxs - mins) * scale
        return centers, deltas

    def _get_axis_line_edge_points(self, minmax, maxmin, position=None):
        """Get the edge points for the black bolded axis line."""
        # When changing vertical axis some of the axes has to be
        # moved to the other plane so it looks the same as if the z-axis
        # was the vertical axis.
        mb = [minmax, maxmin]  # line from origin to nearest corner to camera
        mb_rev = mb[::-1]
        mm = [[mb, mb_rev, mb_rev], [mb_rev, mb_rev, mb], [mb, mb, mb]]
        mm = mm[self.axes._vertical_axis][self._axinfo["i"]]

        juggled = self._axinfo["juggled"]
        edge_point_0 = mm[0].copy()  # origin point

        if ((position == 'lower' and mm[1][juggled[-1]] < mm[0][juggled[-1]]) or
                (position == 'upper' and mm[1][juggled[-1]] > mm[0][juggled[-1]])):
            edge_point_0[juggled[-1]] = mm[1][juggled[-1]]
        else:
            edge_point_0[juggled[0]] = mm[1][juggled[0]]

        edge_point_1 = edge_point_0.copy()
        edge_point_1[juggled[1]] = mm[1][juggled[1]]

        return edge_point_0, edge_point_1

    def _get_all_axis_line_edge_points(self, minmax, maxmin, axis_position=None):
        # Determine edge points for the axis lines
        edgep1s = []
        edgep2s = []
        position = []
        if axis_position in (None, 'default'):
            edgep1, edgep2 = self._get_axis_line_edge_points(minmax, maxmin)
            edgep1s = [edgep1]
            edgep2s = [edgep2]
            position = ['default']
        else:
            edgep1_l, edgep2_l = self._get_axis_line_edge_points(minmax, maxmin,
                                                                 position='lower')
            edgep1_u, edgep2_u = self._get_axis_line_edge_points(minmax, maxmin,
                                                                 position='upper')
            if axis_position in ('lower', 'both'):
                edgep1s.append(edgep1_l)
                edgep2s.append(edgep2_l)
                position.append('lower')
            if axis_position in ('upper', 'both'):
                edgep1s.append(edgep1_u)
                edgep2s.append(edgep2_u)
                position.append('upper')
        return edgep1s, edgep2s, position

    def _get_tickdir(self, position):
        """
        Get the direction of the tick.

        Parameters
        ----------
        position : str, optional : {'upper', 'lower', 'default'}
            The position of the axis.

        Returns
        -------
        tickdir : int
            Index which indicates which coordinate the tick line will
            align with.
        """
        _api.check_in_list(('upper', 'lower', 'default'), position=position)

        # TODO: Move somewhere else where it's triggered less:
        tickdirs_base = [v["tickdir"] for v in self._AXINFO.values()]  # default
        elev_mod = np.mod(self.axes.elev + 180, 360) - 180
        azim_mod = np.mod(self.axes.azim, 360)
        if position == 'upper':
            if elev_mod >= 0:
                tickdirs_base = [2, 2, 0]
            else:
                tickdirs_base = [1, 0, 0]
            if 0 <= azim_mod < 180:
                tickdirs_base[2] = 1
        elif position == 'lower':
            if elev_mod >= 0:
                tickdirs_base = [1, 0, 1]
            else:
                tickdirs_base = [2, 2, 1]
            if 0 <= azim_mod < 180:
                tickdirs_base[2] = 0
        info_i = [v["i"] for v in self._AXINFO.values()]

        i = self._axinfo["i"]
        vert_ax = self.axes._vertical_axis
        j = vert_ax - 2
        # default: tickdir = [[1, 2, 1], [2, 2, 0], [1, 0, 0]][vert_ax][i]
        tickdir = np.roll(info_i, -j)[np.roll(tickdirs_base, j)][i]
        return tickdir

    def active_pane(self):
        mins, maxs, tc, highs = self._get_coord_info()
        info = self._axinfo
        index = info['i']
        if not highs[index]:
            loc = mins[index]
            plane = self._PLANES[2 * index]
        else:
            loc = maxs[index]
            plane = self._PLANES[2 * index + 1]
        xys = np.array([tc[p] for p in plane])
        return xys, loc

    def draw_pane(self, renderer):
        """
        Draw pane.

        Parameters
        ----------
        renderer : `~matplotlib.backend_bases.RendererBase` subclass
        """
        renderer.open_group('pane3d', gid=self.get_gid())
        xys, loc = self.active_pane()
        self.pane.xy = xys[:, :2]
        self.pane.draw(renderer)
        renderer.close_group('pane3d')

    def _axmask(self):
        axmask = [True, True, True]
        axmask[self._axinfo["i"]] = False
        return axmask

    def _draw_ticks(self, renderer, edgep1, centers, deltas, highs,
                    deltas_per_point, pos):
        ticks = self._update_ticks()
        info = self._axinfo
        index = info["i"]
        juggled = info["juggled"]

        mins, maxs, tc, highs = self._get_coord_info()
        centers, deltas = self._calc_centers_deltas(maxs, mins)

        # Draw ticks:
        tickdir = self._get_tickdir(pos)
        tickdelta = deltas[tickdir] if highs[tickdir] else -deltas[tickdir]

        tick_info = info['tick']
        tick_out = tick_info['outward_factor'] * tickdelta
        tick_in = tick_info['inward_factor'] * tickdelta
        tick_lw = tick_info['linewidth']
        edgep1_tickdir = edgep1[tickdir]
        out_tickdir = edgep1_tickdir + tick_out
        in_tickdir = edgep1_tickdir - tick_in

        default_label_offset = 8.  # A rough estimate
        points = deltas_per_point * deltas
        for tick in ticks:
            # Get tick line positions
            pos = edgep1.copy()
            pos[index] = tick.get_loc()
            pos[tickdir] = out_tickdir
            x1, y1, z1 = proj3d.proj_transform(*pos, self.axes.M)
            pos[tickdir] = in_tickdir
            x2, y2, z2 = proj3d.proj_transform(*pos, self.axes.M)

            # Get position of label
            labeldeltas = (tick.get_pad() + default_label_offset) * points

            pos[tickdir] = edgep1_tickdir
            pos = _move_from_center(pos, centers, labeldeltas, self._axmask())
            lx, ly, lz = proj3d.proj_transform(*pos, self.axes.M)

            _tick_update_position(tick, (x1, x2), (y1, y2), (lx, ly))
            tick.tick1line.set_linewidth(tick_lw[tick._major])
            tick.draw(renderer)

    def _draw_offset_text(self, renderer, edgep1, edgep2, labeldeltas, centers,
                          highs, pep, dx, dy):
        # Get general axis information:
        info = self._axinfo
        index = info["i"]
        juggled = info["juggled"]
        tickdir = info["tickdir"]

        # Which of the two edge points do we want to
        # use for locating the offset text?
        if juggled[2] == 2:
            outeredgep = edgep1
            outerindex = 0
        else:
            outeredgep = edgep2
            outerindex = 1

        pos = _move_from_center(outeredgep, centers, labeldeltas,
                                self._axmask())
        olx, oly, olz = proj3d.proj_transform(*pos, self.axes.M)
        self.offsetText.set_text(self.major.formatter.get_offset())
        self.offsetText.set_position((olx, oly))
        angle = art3d._norm_text_angle(np.rad2deg(np.arctan2(dy, dx)))
        self.offsetText.set_rotation(angle)
        # Must set rotation mode to "anchor" so that
        # the alignment point is used as the "fulcrum" for rotation.
        self.offsetText.set_rotation_mode('anchor')

        # ----------------------------------------------------------------------
        # Note: the following statement for determining the proper alignment of
        # the offset text. This was determined entirely by trial-and-error
        # and should not be in any way considered as "the way".  There are
        # still some edge cases where alignment is not quite right, but this
        # seems to be more of a geometry issue (in other words, I might be
        # using the wrong reference points).
        #
        # (TT, FF, TF, FT) are the shorthand for the tuple of
        #   (centpt[tickdir] <= pep[tickdir, outerindex],
        #    centpt[index] <= pep[index, outerindex])
        #
        # Three-letters (e.g., TFT, FTT) are short-hand for the array of bools
        # from the variable 'highs'.
        # ---------------------------------------------------------------------
        centpt = proj3d.proj_transform(*centers, self.axes.M)
        if centpt[tickdir] > pep[tickdir, outerindex]:
            # if FT and if highs has an even number of Trues
            if (centpt[index] <= pep[index, outerindex]
                    and np.count_nonzero(highs) % 2 == 0):
                # Usually, this means align right, except for the FTT case,
                # in which offset for axis 1 and 2 are aligned left.
                if highs.tolist() == [False, True, True] and index in (1, 2):
                    align = 'left'
                else:
                    align = 'right'
            else:
                # The FF case
                align = 'left'
        else:
            # if TF and if highs has an even number of Trues
            if (centpt[index] > pep[index, outerindex]
                    and np.count_nonzero(highs) % 2 == 0):
                # Usually mean align left, except if it is axis 2
                align = 'right' if index == 2 else 'left'
            else:
                # The TT case
                align = 'right'

        self.offsetText.set_va('center')
        self.offsetText.set_ha(align)
        self.offsetText.draw(renderer)

    def _draw_labels(self, renderer, edgep1, edgep2, labeldeltas, centers, dx, dy):
        label = self._axinfo["label"]

        # Draw labels
        lxyz = 0.5 * (edgep1 + edgep2)
        lxyz = _move_from_center(lxyz, centers, labeldeltas, self._axmask())
        tlx, tly, tlz = proj3d.proj_transform(*lxyz, self.axes.M)
        self.label.set_position((tlx, tly))
        if self.get_rotate_label(self.label.get_text()):
            angle = art3d._norm_text_angle(np.rad2deg(np.arctan2(dy, dx)))
            self.label.set_rotation(angle)
        self.label.set_va(label['va'])
        self.label.set_ha(label['ha'])
        self.label.set_rotation_mode(label['rotation_mode'])
        self.label.draw(renderer)

    @artist.allow_rasterization
    def draw(self, renderer):
        self.label._transform = self.axes.transData
        self.offsetText._transform = self.axes.transData
        renderer.open_group("axis3d", gid=self.get_gid())

        # Get general axis information:
        mins, maxs, tc, highs = self._get_coord_info()
        centers, deltas = self._calc_centers_deltas(maxs, mins)

        # Calculate offset distances
        # A rough estimate; points are ambiguous since 3D plots rotate
        reltoinches = self.get_figure(root=False).dpi_scale_trans.inverted()
        ax_inches = reltoinches.transform(self.axes.bbox.size)
        ax_points_estimate = sum(72. * ax_inches)
        deltas_per_point = 48 / ax_points_estimate
        default_offset = 21.
        labeldeltas = (self.labelpad + default_offset) * deltas_per_point * deltas

        # Determine edge points for the axis lines
        minmax = np.where(highs, maxs, mins)  # "origin" point
        maxmin = np.where(~highs, maxs, mins)  # "opposite" corner near camera

        for edgep1, edgep2, pos in zip(*self._get_all_axis_line_edge_points(
                                           minmax, maxmin, self._tick_position)):
            # Project the edge points along the current position
            pep = proj3d._proj_trans_points([edgep1, edgep2], self.axes.M)
            pep = np.asarray(pep)

            # The transAxes transform is used because the Text object
            # rotates the text relative to the display coordinate system.
            # Therefore, if we want the labels to remain parallel to the
            # axis regardless of the aspect ratio, we need to convert the
            # edge points of the plane to display coordinates and calculate
            # an angle from that.
            # TODO: Maybe Text objects should handle this themselves?
            dx, dy = (self.axes.transAxes.transform([pep[0:2, 1]]) -
                      self.axes.transAxes.transform([pep[0:2, 0]]))[0]

            # Draw the lines
            self.line.set_data(pep[0], pep[1])
            self.line.draw(renderer)

            # Draw ticks
            self._draw_ticks(renderer, edgep1, centers, deltas, highs,
                             deltas_per_point, pos)

            # Draw Offset text
            self._draw_offset_text(renderer, edgep1, edgep2, labeldeltas,
                                   centers, highs, pep, dx, dy)

        for edgep1, edgep2, pos in zip(*self._get_all_axis_line_edge_points(
                                           minmax, maxmin, self._label_position)):
            # See comments above
            pep = proj3d._proj_trans_points([edgep1, edgep2], self.axes.M)
            pep = np.asarray(pep)
            dx, dy = (self.axes.transAxes.transform([pep[0:2, 1]]) -
                      self.axes.transAxes.transform([pep[0:2, 0]]))[0]

            # Draw labels
            self._draw_labels(renderer, edgep1, edgep2, labeldeltas, centers, dx, dy)

        renderer.close_group('axis3d')
        self.stale = False

    @artist.allow_rasterization
    def draw_grid(self, renderer):
        if not self.axes._draw_grid:
            return

        renderer.open_group("grid3d", gid=self.get_gid())

        ticks = self._update_ticks()
        if len(ticks):
            # Get general axis information:
            info = self._axinfo
            index = info["i"]

            mins, maxs, tc, highs = self._get_coord_info()

            minmax = np.where(highs, maxs, mins)
            maxmin = np.where(~highs, maxs, mins)

            # Grid points where the planes meet
            xyz0 = np.tile(minmax, (len(ticks), 1))
            xyz0[:, index] = [tick.get_loc() for tick in ticks]

            # Grid lines go from the end of one plane through the plane
            # intersection (at xyz0) to the end of the other plane.  The first
            # point (0) differs along dimension index-2 and the last (2) along
            # dimension index-1.
            lines = np.stack([xyz0, xyz0, xyz0], axis=1)
            lines[:, 0, index - 2] = maxmin[index - 2]
            lines[:, 2, index - 1] = maxmin[index - 1]
            self.gridlines.set_segments(lines)
            gridinfo = info['grid']
            self.gridlines.set_color(gridinfo['color'])
            self.gridlines.set_linewidth(gridinfo['linewidth'])
            self.gridlines.set_linestyle(gridinfo['linestyle'])
            self.gridlines.do_3d_projection()
            self.gridlines.draw(renderer)

        renderer.close_group('grid3d')

    # TODO: Get this to work (more) properly when mplot3d supports the
    #       transforms framework.
    def get_tightbbox(self, renderer=None, *, for_layout_only=False):
        # docstring inherited
        if not self.get_visible():
            return
        # We have to directly access the internal data structures
        # (and hope they are up to date) because at draw time we
        # shift the ticks and their labels around in (x, y) space
        # based on the projection, the current view port, and their
        # position in 3D space. If we extend the transforms framework
        # into 3D we would not need to do this different book keeping
        # than we do in the normal axis
        major_locs = self.get_majorticklocs()
        minor_locs = self.get_minorticklocs()

        ticks = [*self.get_minor_ticks(len(minor_locs)),
                 *self.get_major_ticks(len(major_locs))]
        view_low, view_high = self.get_view_interval()
        if view_low > view_high:
            view_low, view_high = view_high, view_low
        interval_t = self.get_transform().transform([view_low, view_high])

        ticks_to_draw = []
        for tick in ticks:
            try:
                loc_t = self.get_transform().transform(tick.get_loc())
            except AssertionError:
                # Transform.transform doesn't allow masked values but
                # some scales might make them, so we need this try/except.
                pass
            else:
                if mtransforms._interval_contains_close(interval_t, loc_t):
                    ticks_to_draw.append(tick)

        ticks = ticks_to_draw

        bb_1, bb_2 = self._get_ticklabel_bboxes(ticks, renderer)
        other = []

        if self.line.get_visible():
            other.append(self.line.get_window_extent(renderer))
        if (self.label.get_visible() and not for_layout_only and
                self.label.get_text()):
            other.append(self.label.get_window_extent(renderer))

        return mtransforms.Bbox.union([*bb_1, *bb_2, *other])

    d_interval = _api.deprecated(
        "3.6", alternative="get_data_interval", pending=True)(
            property(lambda self: self.get_data_interval(),
                     lambda self, minmax: self.set_data_interval(*minmax)))
    v_interval = _api.deprecated(
        "3.6", alternative="get_view_interval", pending=True)(
            property(lambda self: self.get_view_interval(),
                     lambda self, minmax: self.set_view_interval(*minmax)))


class XAxis(Axis):
    axis_name = "x"
    get_view_interval, set_view_interval = maxis._make_getset_interval(
        "view", "xy_viewLim", "intervalx")
    get_data_interval, set_data_interval = maxis._make_getset_interval(
        "data", "xy_dataLim", "intervalx")


class YAxis(Axis):
    axis_name = "y"
    get_view_interval, set_view_interval = maxis._make_getset_interval(
        "view", "xy_viewLim", "intervaly")
    get_data_interval, set_data_interval = maxis._make_getset_interval(
        "data", "xy_dataLim", "intervaly")


class ZAxis(Axis):
    axis_name = "z"
    get_view_interval, set_view_interval = maxis._make_getset_interval(
        "view", "zz_viewLim", "intervalx")
    get_data_interval, set_data_interval = maxis._make_getset_interval(
        "data", "zz_dataLim", "intervalx")
