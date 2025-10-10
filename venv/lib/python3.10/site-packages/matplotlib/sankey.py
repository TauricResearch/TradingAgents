"""
Module for creating Sankey diagrams using Matplotlib.
"""

import logging
from types import SimpleNamespace

import numpy as np

import matplotlib as mpl
from matplotlib.path import Path
from matplotlib.patches import PathPatch
from matplotlib.transforms import Affine2D
from matplotlib import _docstring

_log = logging.getLogger(__name__)

__author__ = "Kevin L. Davies"
__credits__ = ["Yannick Copin"]
__license__ = "BSD"
__version__ = "2011/09/16"

# Angles [deg/90]
RIGHT = 0
UP = 1
# LEFT = 2
DOWN = 3


class Sankey:
    """
    Sankey diagram.

      Sankey diagrams are a specific type of flow diagram, in which
      the width of the arrows is shown proportionally to the flow
      quantity.  They are typically used to visualize energy or
      material or cost transfers between processes.
      `Wikipedia (6/1/2011) <https://en.wikipedia.org/wiki/Sankey_diagram>`_

    """

    def __init__(self, ax=None, scale=1.0, unit='', format='%G', gap=0.25,
                 radius=0.1, shoulder=0.03, offset=0.15, head_angle=100,
                 margin=0.4, tolerance=1e-6, **kwargs):
        """
        Create a new Sankey instance.

        The optional arguments listed below are applied to all subdiagrams so
        that there is consistent alignment and formatting.

        In order to draw a complex Sankey diagram, create an instance of
        `Sankey` by calling it without any kwargs::

            sankey = Sankey()

        Then add simple Sankey sub-diagrams::

            sankey.add() # 1
            sankey.add() # 2
            #...
            sankey.add() # n

        Finally, create the full diagram::

            sankey.finish()

        Or, instead, simply daisy-chain those calls::

            Sankey().add().add...  .add().finish()

        Other Parameters
        ----------------
        ax : `~matplotlib.axes.Axes`
            Axes onto which the data should be plotted.  If *ax* isn't
            provided, new Axes will be created.
        scale : float
            Scaling factor for the flows.  *scale* sizes the width of the paths
            in order to maintain proper layout.  The same scale is applied to
            all subdiagrams.  The value should be chosen such that the product
            of the scale and the sum of the inputs is approximately 1.0 (and
            the product of the scale and the sum of the outputs is
            approximately -1.0).
        unit : str
            The physical unit associated with the flow quantities.  If *unit*
            is None, then none of the quantities are labeled.
        format : str or callable
            A Python number formatting string or callable used to label the
            flows with their quantities (i.e., a number times a unit, where the
            unit is given). If a format string is given, the label will be
            ``format % quantity``. If a callable is given, it will be called
            with ``quantity`` as an argument.
        gap : float
            Space between paths that break in/break away to/from the top or
            bottom.
        radius : float
            Inner radius of the vertical paths.
        shoulder : float
            Size of the shoulders of output arrows.
        offset : float
            Text offset (from the dip or tip of the arrow).
        head_angle : float
            Angle, in degrees, of the arrow heads (and negative of the angle of
            the tails).
        margin : float
            Minimum space between Sankey outlines and the edge of the plot
            area.
        tolerance : float
            Acceptable maximum of the magnitude of the sum of flows.  The
            magnitude of the sum of connected flows cannot be greater than
            *tolerance*.
        **kwargs
            Any additional keyword arguments will be passed to `add`, which
            will create the first subdiagram.

        See Also
        --------
        Sankey.add
        Sankey.finish

        Examples
        --------
        .. plot:: gallery/specialty_plots/sankey_basics.py
        """
        # Check the arguments.
        if gap < 0:
            raise ValueError(
                "'gap' is negative, which is not allowed because it would "
                "cause the paths to overlap")
        if radius > gap:
            raise ValueError(
                "'radius' is greater than 'gap', which is not allowed because "
                "it would cause the paths to overlap")
        if head_angle < 0:
            raise ValueError(
                "'head_angle' is negative, which is not allowed because it "
                "would cause inputs to look like outputs and vice versa")
        if tolerance < 0:
            raise ValueError(
                "'tolerance' is negative, but it must be a magnitude")

        # Create Axes if necessary.
        if ax is None:
            import matplotlib.pyplot as plt
            fig = plt.figure()
            ax = fig.add_subplot(1, 1, 1, xticks=[], yticks=[])

        self.diagrams = []

        # Store the inputs.
        self.ax = ax
        self.unit = unit
        self.format = format
        self.scale = scale
        self.gap = gap
        self.radius = radius
        self.shoulder = shoulder
        self.offset = offset
        self.margin = margin
        self.pitch = np.tan(np.pi * (1 - head_angle / 180.0) / 2.0)
        self.tolerance = tolerance

        # Initialize the vertices of tight box around the diagram(s).
        self.extent = np.array((np.inf, -np.inf, np.inf, -np.inf))

        # If there are any kwargs, create the first subdiagram.
        if len(kwargs):
            self.add(**kwargs)

    def _arc(self, quadrant=0, cw=True, radius=1, center=(0, 0)):
        """
        Return the codes and vertices for a rotated, scaled, and translated
        90 degree arc.

        Other Parameters
        ----------------
        quadrant : {0, 1, 2, 3}, default: 0
            Uses 0-based indexing (0, 1, 2, or 3).
        cw : bool, default: True
            If True, the arc vertices are produced clockwise; counter-clockwise
            otherwise.
        radius : float, default: 1
            The radius of the arc.
        center : (float, float), default: (0, 0)
            (x, y) tuple of the arc's center.
        """
        # Note:  It would be possible to use matplotlib's transforms to rotate,
        # scale, and translate the arc, but since the angles are discrete,
        # it's just as easy and maybe more efficient to do it here.
        ARC_CODES = [Path.LINETO,
                     Path.CURVE4,
                     Path.CURVE4,
                     Path.CURVE4,
                     Path.CURVE4,
                     Path.CURVE4,
                     Path.CURVE4]
        # Vertices of a cubic Bezier curve approximating a 90 deg arc
        # These can be determined by Path.arc(0, 90).
        ARC_VERTICES = np.array([[1.00000000e+00, 0.00000000e+00],
                                 [1.00000000e+00, 2.65114773e-01],
                                 [8.94571235e-01, 5.19642327e-01],
                                 [7.07106781e-01, 7.07106781e-01],
                                 [5.19642327e-01, 8.94571235e-01],
                                 [2.65114773e-01, 1.00000000e+00],
                                 # Insignificant
                                 # [6.12303177e-17, 1.00000000e+00]])
                                 [0.00000000e+00, 1.00000000e+00]])
        if quadrant in (0, 2):
            if cw:
                vertices = ARC_VERTICES
            else:
                vertices = ARC_VERTICES[:, ::-1]  # Swap x and y.
        else:  # 1, 3
            # Negate x.
            if cw:
                # Swap x and y.
                vertices = np.column_stack((-ARC_VERTICES[:, 1],
                                             ARC_VERTICES[:, 0]))
            else:
                vertices = np.column_stack((-ARC_VERTICES[:, 0],
                                             ARC_VERTICES[:, 1]))
        if quadrant > 1:
            radius = -radius  # Rotate 180 deg.
        return list(zip(ARC_CODES, radius * vertices +
                        np.tile(center, (ARC_VERTICES.shape[0], 1))))

    def _add_input(self, path, angle, flow, length):
        """
        Add an input to a path and return its tip and label locations.
        """
        if angle is None:
            return [0, 0], [0, 0]
        else:
            x, y = path[-1][1]  # Use the last point as a reference.
            dipdepth = (flow / 2) * self.pitch
            if angle == RIGHT:
                x -= length
                dip = [x + dipdepth, y + flow / 2.0]
                path.extend([(Path.LINETO, [x, y]),
                             (Path.LINETO, dip),
                             (Path.LINETO, [x, y + flow]),
                             (Path.LINETO, [x + self.gap, y + flow])])
                label_location = [dip[0] - self.offset, dip[1]]
            else:  # Vertical
                x -= self.gap
                if angle == UP:
                    sign = 1
                else:
                    sign = -1

                dip = [x - flow / 2, y - sign * (length - dipdepth)]
                if angle == DOWN:
                    quadrant = 2
                else:
                    quadrant = 1

                # Inner arc isn't needed if inner radius is zero
                if self.radius:
                    path.extend(self._arc(quadrant=quadrant,
                                          cw=angle == UP,
                                          radius=self.radius,
                                          center=(x + self.radius,
                                                  y - sign * self.radius)))
                else:
                    path.append((Path.LINETO, [x, y]))
                path.extend([(Path.LINETO, [x, y - sign * length]),
                             (Path.LINETO, dip),
                             (Path.LINETO, [x - flow, y - sign * length])])
                path.extend(self._arc(quadrant=quadrant,
                                      cw=angle == DOWN,
                                      radius=flow + self.radius,
                                      center=(x + self.radius,
                                              y - sign * self.radius)))
                path.append((Path.LINETO, [x - flow, y + sign * flow]))
                label_location = [dip[0], dip[1] - sign * self.offset]

            return dip, label_location

    def _add_output(self, path, angle, flow, length):
        """
        Append an output to a path and return its tip and label locations.

        .. note:: *flow* is negative for an output.
        """
        if angle is None:
            return [0, 0], [0, 0]
        else:
            x, y = path[-1][1]  # Use the last point as a reference.
            tipheight = (self.shoulder - flow / 2) * self.pitch
            if angle == RIGHT:
                x += length
                tip = [x + tipheight, y + flow / 2.0]
                path.extend([(Path.LINETO, [x, y]),
                             (Path.LINETO, [x, y + self.shoulder]),
                             (Path.LINETO, tip),
                             (Path.LINETO, [x, y - self.shoulder + flow]),
                             (Path.LINETO, [x, y + flow]),
                             (Path.LINETO, [x - self.gap, y + flow])])
                label_location = [tip[0] + self.offset, tip[1]]
            else:  # Vertical
                x += self.gap
                if angle == UP:
                    sign, quadrant = 1, 3
                else:
                    sign, quadrant = -1, 0

                tip = [x - flow / 2.0, y + sign * (length + tipheight)]
                # Inner arc isn't needed if inner radius is zero
                if self.radius:
                    path.extend(self._arc(quadrant=quadrant,
                                          cw=angle == UP,
                                          radius=self.radius,
                                          center=(x - self.radius,
                                                  y + sign * self.radius)))
                else:
                    path.append((Path.LINETO, [x, y]))
                path.extend([(Path.LINETO, [x, y + sign * length]),
                             (Path.LINETO, [x - self.shoulder,
                                            y + sign * length]),
                             (Path.LINETO, tip),
                             (Path.LINETO, [x + self.shoulder - flow,
                                            y + sign * length]),
                             (Path.LINETO, [x - flow, y + sign * length])])
                path.extend(self._arc(quadrant=quadrant,
                                      cw=angle == DOWN,
                                      radius=self.radius - flow,
                                      center=(x - self.radius,
                                              y + sign * self.radius)))
                path.append((Path.LINETO, [x - flow, y + sign * flow]))
                label_location = [tip[0], tip[1] + sign * self.offset]
            return tip, label_location

    def _revert(self, path, first_action=Path.LINETO):
        """
        A path is not simply reversible by path[::-1] since the code
        specifies an action to take from the **previous** point.
        """
        reverse_path = []
        next_code = first_action
        for code, position in path[::-1]:
            reverse_path.append((next_code, position))
            next_code = code
        return reverse_path
        # This might be more efficient, but it fails because 'tuple' object
        # doesn't support item assignment:
        # path[1] = path[1][-1:0:-1]
        # path[1][0] = first_action
        # path[2] = path[2][::-1]
        # return path

    @_docstring.interpd
    def add(self, patchlabel='', flows=None, orientations=None, labels='',
            trunklength=1.0, pathlengths=0.25, prior=None, connect=(0, 0),
            rotation=0, **kwargs):
        """
        Add a simple Sankey diagram with flows at the same hierarchical level.

        Parameters
        ----------
        patchlabel : str
            Label to be placed at the center of the diagram.
            Note that *label* (not *patchlabel*) can be passed as keyword
            argument to create an entry in the legend.

        flows : list of float
            Array of flow values.  By convention, inputs are positive and
            outputs are negative.

            Flows are placed along the top of the diagram from the inside out
            in order of their index within *flows*.  They are placed along the
            sides of the diagram from the top down and along the bottom from
            the outside in.

            If the sum of the inputs and outputs is
            nonzero, the discrepancy will appear as a cubic Bézier curve along
            the top and bottom edges of the trunk.

        orientations : list of {-1, 0, 1}
            List of orientations of the flows (or a single orientation to be
            used for all flows).  Valid values are 0 (inputs from
            the left, outputs to the right), 1 (from and to the top) or -1
            (from and to the bottom).

        labels : list of (str or None)
            List of labels for the flows (or a single label to be used for all
            flows).  Each label may be *None* (no label), or a labeling string.
            If an entry is a (possibly empty) string, then the quantity for the
            corresponding flow will be shown below the string.  However, if
            the *unit* of the main diagram is None, then quantities are never
            shown, regardless of the value of this argument.

        trunklength : float
            Length between the bases of the input and output groups (in
            data-space units).

        pathlengths : list of float
            List of lengths of the vertical arrows before break-in or after
            break-away.  If a single value is given, then it will be applied to
            the first (inside) paths on the top and bottom, and the length of
            all other arrows will be justified accordingly.  The *pathlengths*
            are not applied to the horizontal inputs and outputs.

        prior : int
            Index of the prior diagram to which this diagram should be
            connected.

        connect : (int, int)
            A (prior, this) tuple indexing the flow of the prior diagram and
            the flow of this diagram which should be connected.  If this is the
            first diagram or *prior* is *None*, *connect* will be ignored.

        rotation : float
            Angle of rotation of the diagram in degrees.  The interpretation of
            the *orientations* argument will be rotated accordingly (e.g., if
            *rotation* == 90, an *orientations* entry of 1 means to/from the
            left).  *rotation* is ignored if this diagram is connected to an
            existing one (using *prior* and *connect*).

        Returns
        -------
        Sankey
            The current `.Sankey` instance.

        Other Parameters
        ----------------
        **kwargs
           Additional keyword arguments set `matplotlib.patches.PathPatch`
           properties, listed below.  For example, one may want to use
           ``fill=False`` or ``label="A legend entry"``.

        %(Patch:kwdoc)s

        See Also
        --------
        Sankey.finish
        """
        # Check and preprocess the arguments.
        flows = np.array([1.0, -1.0]) if flows is None else np.array(flows)
        n = flows.shape[0]  # Number of flows
        if rotation is None:
            rotation = 0
        else:
            # In the code below, angles are expressed in deg/90.
            rotation /= 90.0
        if orientations is None:
            orientations = 0
        try:
            orientations = np.broadcast_to(orientations, n)
        except ValueError:
            raise ValueError(
                f"The shapes of 'flows' {np.shape(flows)} and 'orientations' "
                f"{np.shape(orientations)} are incompatible"
            ) from None
        try:
            labels = np.broadcast_to(labels, n)
        except ValueError:
            raise ValueError(
                f"The shapes of 'flows' {np.shape(flows)} and 'labels' "
                f"{np.shape(labels)} are incompatible"
            ) from None
        if trunklength < 0:
            raise ValueError(
                "'trunklength' is negative, which is not allowed because it "
                "would cause poor layout")
        if abs(np.sum(flows)) > self.tolerance:
            _log.info("The sum of the flows is nonzero (%f; patchlabel=%r); "
                      "is the system not at steady state?",
                      np.sum(flows), patchlabel)
        scaled_flows = self.scale * flows
        gain = sum(max(flow, 0) for flow in scaled_flows)
        loss = sum(min(flow, 0) for flow in scaled_flows)
        if prior is not None:
            if prior < 0:
                raise ValueError("The index of the prior diagram is negative")
            if min(connect) < 0:
                raise ValueError(
                    "At least one of the connection indices is negative")
            if prior >= len(self.diagrams):
                raise ValueError(
                    f"The index of the prior diagram is {prior}, but there "
                    f"are only {len(self.diagrams)} other diagrams")
            if connect[0] >= len(self.diagrams[prior].flows):
                raise ValueError(
                    "The connection index to the source diagram is {}, but "
                    "that diagram has only {} flows".format(
                        connect[0], len(self.diagrams[prior].flows)))
            if connect[1] >= n:
                raise ValueError(
                    f"The connection index to this diagram is {connect[1]}, "
                    f"but this diagram has only {n} flows")
            if self.diagrams[prior].angles[connect[0]] is None:
                raise ValueError(
                    f"The connection cannot be made, which may occur if the "
                    f"magnitude of flow {connect[0]} of diagram {prior} is "
                    f"less than the specified tolerance")
            flow_error = (self.diagrams[prior].flows[connect[0]] +
                          flows[connect[1]])
            if abs(flow_error) >= self.tolerance:
                raise ValueError(
                    f"The scaled sum of the connected flows is {flow_error}, "
                    f"which is not within the tolerance ({self.tolerance})")

        # Determine if the flows are inputs.
        are_inputs = [None] * n
        for i, flow in enumerate(flows):
            if flow >= self.tolerance:
                are_inputs[i] = True
            elif flow <= -self.tolerance:
                are_inputs[i] = False
            else:
                _log.info(
                    "The magnitude of flow %d (%f) is below the tolerance "
                    "(%f).\nIt will not be shown, and it cannot be used in a "
                    "connection.", i, flow, self.tolerance)

        # Determine the angles of the arrows (before rotation).
        angles = [None] * n
        for i, (orient, is_input) in enumerate(zip(orientations, are_inputs)):
            if orient == 1:
                if is_input:
                    angles[i] = DOWN
                elif is_input is False:
                    # Be specific since is_input can be None.
                    angles[i] = UP
            elif orient == 0:
                if is_input is not None:
                    angles[i] = RIGHT
            else:
                if orient != -1:
                    raise ValueError(
                        f"The value of orientations[{i}] is {orient}, "
                        f"but it must be -1, 0, or 1")
                if is_input:
                    angles[i] = UP
                elif is_input is False:
                    angles[i] = DOWN

        # Justify the lengths of the paths.
        if np.iterable(pathlengths):
            if len(pathlengths) != n:
                raise ValueError(
                    f"The lengths of 'flows' ({n}) and 'pathlengths' "
                    f"({len(pathlengths)}) are incompatible")
        else:  # Make pathlengths into a list.
            urlength = pathlengths
            ullength = pathlengths
            lrlength = pathlengths
            lllength = pathlengths
            d = dict(RIGHT=pathlengths)
            pathlengths = [d.get(angle, 0) for angle in angles]
            # Determine the lengths of the top-side arrows
            # from the middle outwards.
            for i, (angle, is_input, flow) in enumerate(zip(angles, are_inputs,
                                                            scaled_flows)):
                if angle == DOWN and is_input:
                    pathlengths[i] = ullength
                    ullength += flow
                elif angle == UP and is_input is False:
                    pathlengths[i] = urlength
                    urlength -= flow  # Flow is negative for outputs.
            # Determine the lengths of the bottom-side arrows
            # from the middle outwards.
            for i, (angle, is_input, flow) in enumerate(reversed(list(zip(
                  angles, are_inputs, scaled_flows)))):
                if angle == UP and is_input:
                    pathlengths[n - i - 1] = lllength
                    lllength += flow
                elif angle == DOWN and is_input is False:
                    pathlengths[n - i - 1] = lrlength
                    lrlength -= flow
            # Determine the lengths of the left-side arrows
            # from the bottom upwards.
            has_left_input = False
            for i, (angle, is_input, spec) in enumerate(reversed(list(zip(
                  angles, are_inputs, zip(scaled_flows, pathlengths))))):
                if angle == RIGHT:
                    if is_input:
                        if has_left_input:
                            pathlengths[n - i - 1] = 0
                        else:
                            has_left_input = True
            # Determine the lengths of the right-side arrows
            # from the top downwards.
            has_right_output = False
            for i, (angle, is_input, spec) in enumerate(zip(
                  angles, are_inputs, list(zip(scaled_flows, pathlengths)))):
                if angle == RIGHT:
                    if is_input is False:
                        if has_right_output:
                            pathlengths[i] = 0
                        else:
                            has_right_output = True

        # Begin the subpaths, and smooth the transition if the sum of the flows
        # is nonzero.
        urpath = [(Path.MOVETO, [(self.gap - trunklength / 2.0),  # Upper right
                                 gain / 2.0]),
                  (Path.LINETO, [(self.gap - trunklength / 2.0) / 2.0,
                                 gain / 2.0]),
                  (Path.CURVE4, [(self.gap - trunklength / 2.0) / 8.0,
                                 gain / 2.0]),
                  (Path.CURVE4, [(trunklength / 2.0 - self.gap) / 8.0,
                                 -loss / 2.0]),
                  (Path.LINETO, [(trunklength / 2.0 - self.gap) / 2.0,
                                 -loss / 2.0]),
                  (Path.LINETO, [(trunklength / 2.0 - self.gap),
                                 -loss / 2.0])]
        llpath = [(Path.LINETO, [(trunklength / 2.0 - self.gap),  # Lower left
                                 loss / 2.0]),
                  (Path.LINETO, [(trunklength / 2.0 - self.gap) / 2.0,
                                 loss / 2.0]),
                  (Path.CURVE4, [(trunklength / 2.0 - self.gap) / 8.0,
                                 loss / 2.0]),
                  (Path.CURVE4, [(self.gap - trunklength / 2.0) / 8.0,
                                 -gain / 2.0]),
                  (Path.LINETO, [(self.gap - trunklength / 2.0) / 2.0,
                                 -gain / 2.0]),
                  (Path.LINETO, [(self.gap - trunklength / 2.0),
                                 -gain / 2.0])]
        lrpath = [(Path.LINETO, [(trunklength / 2.0 - self.gap),  # Lower right
                                 loss / 2.0])]
        ulpath = [(Path.LINETO, [self.gap - trunklength / 2.0,  # Upper left
                                 gain / 2.0])]

        # Add the subpaths and assign the locations of the tips and labels.
        tips = np.zeros((n, 2))
        label_locations = np.zeros((n, 2))
        # Add the top-side inputs and outputs from the middle outwards.
        for i, (angle, is_input, spec) in enumerate(zip(
              angles, are_inputs, list(zip(scaled_flows, pathlengths)))):
            if angle == DOWN and is_input:
                tips[i, :], label_locations[i, :] = self._add_input(
                    ulpath, angle, *spec)
            elif angle == UP and is_input is False:
                tips[i, :], label_locations[i, :] = self._add_output(
                    urpath, angle, *spec)
        # Add the bottom-side inputs and outputs from the middle outwards.
        for i, (angle, is_input, spec) in enumerate(reversed(list(zip(
              angles, are_inputs, list(zip(scaled_flows, pathlengths)))))):
            if angle == UP and is_input:
                tip, label_location = self._add_input(llpath, angle, *spec)
                tips[n - i - 1, :] = tip
                label_locations[n - i - 1, :] = label_location
            elif angle == DOWN and is_input is False:
                tip, label_location = self._add_output(lrpath, angle, *spec)
                tips[n - i - 1, :] = tip
                label_locations[n - i - 1, :] = label_location
        # Add the left-side inputs from the bottom upwards.
        has_left_input = False
        for i, (angle, is_input, spec) in enumerate(reversed(list(zip(
              angles, are_inputs, list(zip(scaled_flows, pathlengths)))))):
            if angle == RIGHT and is_input:
                if not has_left_input:
                    # Make sure the lower path extends
                    # at least as far as the upper one.
                    if llpath[-1][1][0] > ulpath[-1][1][0]:
                        llpath.append((Path.LINETO, [ulpath[-1][1][0],
                                                     llpath[-1][1][1]]))
                    has_left_input = True
                tip, label_location = self._add_input(llpath, angle, *spec)
                tips[n - i - 1, :] = tip
                label_locations[n - i - 1, :] = label_location
        # Add the right-side outputs from the top downwards.
        has_right_output = False
        for i, (angle, is_input, spec) in enumerate(zip(
              angles, are_inputs, list(zip(scaled_flows, pathlengths)))):
            if angle == RIGHT and is_input is False:
                if not has_right_output:
                    # Make sure the upper path extends
                    # at least as far as the lower one.
                    if urpath[-1][1][0] < lrpath[-1][1][0]:
                        urpath.append((Path.LINETO, [lrpath[-1][1][0],
                                                     urpath[-1][1][1]]))
                    has_right_output = True
                tips[i, :], label_locations[i, :] = self._add_output(
                    urpath, angle, *spec)
        # Trim any hanging vertices.
        if not has_left_input:
            ulpath.pop()
            llpath.pop()
        if not has_right_output:
            lrpath.pop()
            urpath.pop()

        # Concatenate the subpaths in the correct order (clockwise from top).
        path = (urpath + self._revert(lrpath) + llpath + self._revert(ulpath) +
                [(Path.CLOSEPOLY, urpath[0][1])])

        # Create a patch with the Sankey outline.
        codes, vertices = zip(*path)
        vertices = np.array(vertices)

        def _get_angle(a, r):
            if a is None:
                return None
            else:
                return a + r

        if prior is None:
            if rotation != 0:  # By default, none of this is needed.
                angles = [_get_angle(angle, rotation) for angle in angles]
                rotate = Affine2D().rotate_deg(rotation * 90).transform_affine
                tips = rotate(tips)
                label_locations = rotate(label_locations)
                vertices = rotate(vertices)
            text = self.ax.text(0, 0, s=patchlabel, ha='center', va='center')
        else:
            rotation = (self.diagrams[prior].angles[connect[0]] -
                        angles[connect[1]])
            angles = [_get_angle(angle, rotation) for angle in angles]
            rotate = Affine2D().rotate_deg(rotation * 90).transform_affine
            tips = rotate(tips)
            offset = self.diagrams[prior].tips[connect[0]] - tips[connect[1]]
            translate = Affine2D().translate(*offset).transform_affine
            tips = translate(tips)
            label_locations = translate(rotate(label_locations))
            vertices = translate(rotate(vertices))
            kwds = dict(s=patchlabel, ha='center', va='center')
            text = self.ax.text(*offset, **kwds)
        if mpl.rcParams['_internal.classic_mode']:
            fc = kwargs.pop('fc', kwargs.pop('facecolor', '#bfd1d4'))
            lw = kwargs.pop('lw', kwargs.pop('linewidth', 0.5))
        else:
            fc = kwargs.pop('fc', kwargs.pop('facecolor', None))
            lw = kwargs.pop('lw', kwargs.pop('linewidth', None))
        if fc is None:
            fc = self.ax._get_patches_for_fill.get_next_color()
        patch = PathPatch(Path(vertices, codes), fc=fc, lw=lw, **kwargs)
        self.ax.add_patch(patch)

        # Add the path labels.
        texts = []
        for number, angle, label, location in zip(flows, angles, labels,
                                                  label_locations):
            if label is None or angle is None:
                label = ''
            elif self.unit is not None:
                if isinstance(self.format, str):
                    quantity = self.format % abs(number) + self.unit
                elif callable(self.format):
                    quantity = self.format(number)
                else:
                    raise TypeError(
                        'format must be callable or a format string')
                if label != '':
                    label += "\n"
                label += quantity
            texts.append(self.ax.text(x=location[0], y=location[1],
                                      s=label,
                                      ha='center', va='center'))
        # Text objects are placed even they are empty (as long as the magnitude
        # of the corresponding flow is larger than the tolerance) in case the
        # user wants to provide labels later.

        # Expand the size of the diagram if necessary.
        self.extent = (min(np.min(vertices[:, 0]),
                           np.min(label_locations[:, 0]),
                           self.extent[0]),
                       max(np.max(vertices[:, 0]),
                           np.max(label_locations[:, 0]),
                           self.extent[1]),
                       min(np.min(vertices[:, 1]),
                           np.min(label_locations[:, 1]),
                           self.extent[2]),
                       max(np.max(vertices[:, 1]),
                           np.max(label_locations[:, 1]),
                           self.extent[3]))
        # Include both vertices _and_ label locations in the extents; there are
        # where either could determine the margins (e.g., arrow shoulders).

        # Add this diagram as a subdiagram.
        self.diagrams.append(
            SimpleNamespace(patch=patch, flows=flows, angles=angles, tips=tips,
                            text=text, texts=texts))

        # Allow a daisy-chained call structure (see docstring for the class).
        return self

    def finish(self):
        """
        Adjust the Axes and return a list of information about the Sankey
        subdiagram(s).

        Returns a list of subdiagrams with the following fields:

        ========  =============================================================
        Field     Description
        ========  =============================================================
        *patch*   Sankey outline (a `~matplotlib.patches.PathPatch`).
        *flows*   Flow values (positive for input, negative for output).
        *angles*  List of angles of the arrows [deg/90].
                  For example, if the diagram has not been rotated,
                  an input to the top side has an angle of 3 (DOWN),
                  and an output from the top side has an angle of 1 (UP).
                  If a flow has been skipped (because its magnitude is less
                  than *tolerance*), then its angle will be *None*.
        *tips*    (N, 2)-array of the (x, y) positions of the tips (or "dips")
                  of the flow paths.
                  If the magnitude of a flow is less the *tolerance* of this
                  `Sankey` instance, the flow is skipped and its tip will be at
                  the center of the diagram.
        *text*    `.Text` instance for the diagram label.
        *texts*   List of `.Text` instances for the flow labels.
        ========  =============================================================

        See Also
        --------
        Sankey.add
        """
        self.ax.axis([self.extent[0] - self.margin,
                      self.extent[1] + self.margin,
                      self.extent[2] - self.margin,
                      self.extent[3] + self.margin])
        self.ax.set_aspect('equal', adjustable='datalim')
        return self.diagrams
