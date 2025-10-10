"""
A layoutgrid is a nrows by ncols set of boxes, meant to be used by
`._constrained_layout`, each box is analogous to a subplotspec element of
a gridspec.

Each box is defined by left[ncols], right[ncols], bottom[nrows] and top[nrows],
and by two editable margins for each side.  The main margin gets its value
set by the size of ticklabels, titles, etc on each Axes that is in the figure.
The outer margin is the padding around the Axes, and space for any
colorbars.

The "inner" widths and heights of these boxes are then constrained to be the
same (relative the values of `width_ratios[ncols]` and `height_ratios[nrows]`).

The layoutgrid is then constrained to be contained within a parent layoutgrid,
its column(s) and row(s) specified when it is created.
"""

import itertools
import kiwisolver as kiwi
import logging
import numpy as np

import matplotlib as mpl
import matplotlib.patches as mpatches
from matplotlib.transforms import Bbox

_log = logging.getLogger(__name__)


class LayoutGrid:
    """
    Analogous to a gridspec, and contained in another LayoutGrid.
    """

    def __init__(self, parent=None, parent_pos=(0, 0),
                 parent_inner=False, name='', ncols=1, nrows=1,
                 h_pad=None, w_pad=None, width_ratios=None,
                 height_ratios=None):
        Variable = kiwi.Variable
        self.parent_pos = parent_pos
        self.parent_inner = parent_inner
        self.name = name + seq_id()
        if isinstance(parent, LayoutGrid):
            self.name = f'{parent.name}.{self.name}'
        self.nrows = nrows
        self.ncols = ncols
        self.height_ratios = np.atleast_1d(height_ratios)
        if height_ratios is None:
            self.height_ratios = np.ones(nrows)
        self.width_ratios = np.atleast_1d(width_ratios)
        if width_ratios is None:
            self.width_ratios = np.ones(ncols)

        sn = self.name + '_'
        if not isinstance(parent, LayoutGrid):
            # parent can be a rect if not a LayoutGrid
            # allows specifying a rectangle to contain the layout.
            self.solver = kiwi.Solver()
        else:
            parent.add_child(self, *parent_pos)
            self.solver = parent.solver
        # keep track of artist associated w/ this layout.  Can be none
        self.artists = np.empty((nrows, ncols), dtype=object)
        self.children = np.empty((nrows, ncols), dtype=object)

        self.margins = {}
        self.margin_vals = {}
        # all the boxes in each column share the same left/right margins:
        for todo in ['left', 'right', 'leftcb', 'rightcb']:
            # track the value so we can change only if a margin is larger
            # than the current value
            self.margin_vals[todo] = np.zeros(ncols)

        sol = self.solver

        self.lefts = [Variable(f'{sn}lefts[{i}]') for i in range(ncols)]
        self.rights = [Variable(f'{sn}rights[{i}]') for i in range(ncols)]
        for todo in ['left', 'right', 'leftcb', 'rightcb']:
            self.margins[todo] = [Variable(f'{sn}margins[{todo}][{i}]')
                                  for i in range(ncols)]
            for i in range(ncols):
                sol.addEditVariable(self.margins[todo][i], 'strong')

        for todo in ['bottom', 'top', 'bottomcb', 'topcb']:
            self.margins[todo] = np.empty((nrows), dtype=object)
            self.margin_vals[todo] = np.zeros(nrows)

        self.bottoms = [Variable(f'{sn}bottoms[{i}]') for i in range(nrows)]
        self.tops = [Variable(f'{sn}tops[{i}]') for i in range(nrows)]
        for todo in ['bottom', 'top', 'bottomcb', 'topcb']:
            self.margins[todo] = [Variable(f'{sn}margins[{todo}][{i}]')
                                  for i in range(nrows)]
            for i in range(nrows):
                sol.addEditVariable(self.margins[todo][i], 'strong')

        # set these margins to zero by default. They will be edited as
        # children are filled.
        self.reset_margins()
        self.add_constraints(parent)

        self.h_pad = h_pad
        self.w_pad = w_pad

    def __repr__(self):
        str = f'LayoutBox: {self.name:25s} {self.nrows}x{self.ncols},\n'
        for i in range(self.nrows):
            for j in range(self.ncols):
                str += f'{i}, {j}: '\
                       f'L{self.lefts[j].value():1.3f}, ' \
                       f'B{self.bottoms[i].value():1.3f}, ' \
                       f'R{self.rights[j].value():1.3f}, ' \
                       f'T{self.tops[i].value():1.3f}, ' \
                       f'ML{self.margins["left"][j].value():1.3f}, ' \
                       f'MR{self.margins["right"][j].value():1.3f}, ' \
                       f'MB{self.margins["bottom"][i].value():1.3f}, ' \
                       f'MT{self.margins["top"][i].value():1.3f}, \n'
        return str

    def reset_margins(self):
        """
        Reset all the margins to zero.  Must do this after changing
        figure size, for instance, because the relative size of the
        axes labels etc changes.
        """
        for todo in ['left', 'right', 'bottom', 'top',
                     'leftcb', 'rightcb', 'bottomcb', 'topcb']:
            self.edit_margins(todo, 0.0)

    def add_constraints(self, parent):
        # define self-consistent constraints
        self.hard_constraints()
        # define relationship with parent layoutgrid:
        self.parent_constraints(parent)
        # define relative widths of the grid cells to each other
        # and stack horizontally and vertically.
        self.grid_constraints()

    def hard_constraints(self):
        """
        These are the redundant constraints, plus ones that make the
        rest of the code easier.
        """
        for i in range(self.ncols):
            hc = [self.rights[i] >= self.lefts[i],
                  (self.rights[i] - self.margins['right'][i] -
                    self.margins['rightcb'][i] >=
                    self.lefts[i] - self.margins['left'][i] -
                    self.margins['leftcb'][i])
                  ]
            for c in hc:
                self.solver.addConstraint(c | 'required')

        for i in range(self.nrows):
            hc = [self.tops[i] >= self.bottoms[i],
                  (self.tops[i] - self.margins['top'][i] -
                    self.margins['topcb'][i] >=
                    self.bottoms[i] - self.margins['bottom'][i] -
                    self.margins['bottomcb'][i])
                  ]
            for c in hc:
                self.solver.addConstraint(c | 'required')

    def add_child(self, child, i=0, j=0):
        # np.ix_ returns the cross product of i and j indices
        self.children[np.ix_(np.atleast_1d(i), np.atleast_1d(j))] = child

    def parent_constraints(self, parent):
        # constraints that are due to the parent...
        # i.e. the first column's left is equal to the
        # parent's left, the last column right equal to the
        # parent's right...
        if not isinstance(parent, LayoutGrid):
            # specify a rectangle in figure coordinates
            hc = [self.lefts[0] == parent[0],
                  self.rights[-1] == parent[0] + parent[2],
                  # top and bottom reversed order...
                  self.tops[0] == parent[1] + parent[3],
                  self.bottoms[-1] == parent[1]]
        else:
            rows, cols = self.parent_pos
            rows = np.atleast_1d(rows)
            cols = np.atleast_1d(cols)

            left = parent.lefts[cols[0]]
            right = parent.rights[cols[-1]]
            top = parent.tops[rows[0]]
            bottom = parent.bottoms[rows[-1]]
            if self.parent_inner:
                # the layout grid is contained inside the inner
                # grid of the parent.
                left += parent.margins['left'][cols[0]]
                left += parent.margins['leftcb'][cols[0]]
                right -= parent.margins['right'][cols[-1]]
                right -= parent.margins['rightcb'][cols[-1]]
                top -= parent.margins['top'][rows[0]]
                top -= parent.margins['topcb'][rows[0]]
                bottom += parent.margins['bottom'][rows[-1]]
                bottom += parent.margins['bottomcb'][rows[-1]]
            hc = [self.lefts[0] == left,
                  self.rights[-1] == right,
                  # from top to bottom
                  self.tops[0] == top,
                  self.bottoms[-1] == bottom]
        for c in hc:
            self.solver.addConstraint(c | 'required')

    def grid_constraints(self):
        # constrain the ratio of the inner part of the grids
        # to be the same (relative to width_ratios)

        # constrain widths:
        w = (self.rights[0] - self.margins['right'][0] -
             self.margins['rightcb'][0])
        w = (w - self.lefts[0] - self.margins['left'][0] -
             self.margins['leftcb'][0])
        w0 = w / self.width_ratios[0]
        # from left to right
        for i in range(1, self.ncols):
            w = (self.rights[i] - self.margins['right'][i] -
                 self.margins['rightcb'][i])
            w = (w - self.lefts[i] - self.margins['left'][i] -
                 self.margins['leftcb'][i])
            c = (w == w0 * self.width_ratios[i])
            self.solver.addConstraint(c | 'strong')
            # constrain the grid cells to be directly next to each other.
            c = (self.rights[i - 1] == self.lefts[i])
            self.solver.addConstraint(c | 'strong')

        # constrain heights:
        h = self.tops[0] - self.margins['top'][0] - self.margins['topcb'][0]
        h = (h - self.bottoms[0] - self.margins['bottom'][0] -
             self.margins['bottomcb'][0])
        h0 = h / self.height_ratios[0]
        # from top to bottom:
        for i in range(1, self.nrows):
            h = (self.tops[i] - self.margins['top'][i] -
                 self.margins['topcb'][i])
            h = (h - self.bottoms[i] - self.margins['bottom'][i] -
                 self.margins['bottomcb'][i])
            c = (h == h0 * self.height_ratios[i])
            self.solver.addConstraint(c | 'strong')
            # constrain the grid cells to be directly above each other.
            c = (self.bottoms[i - 1] == self.tops[i])
            self.solver.addConstraint(c | 'strong')

    # Margin editing:  The margins are variable and meant to
    # contain things of a fixed size like axes labels, tick labels, titles
    # etc
    def edit_margin(self, todo, size, cell):
        """
        Change the size of the margin for one cell.

        Parameters
        ----------
        todo : string (one of 'left', 'right', 'bottom', 'top')
            margin to alter.

        size : float
            Size of the margin.  If it is larger than the existing minimum it
            updates the margin size. Fraction of figure size.

        cell : int
            Cell column or row to edit.
        """
        self.solver.suggestValue(self.margins[todo][cell], size)
        self.margin_vals[todo][cell] = size

    def edit_margin_min(self, todo, size, cell=0):
        """
        Change the minimum size of the margin for one cell.

        Parameters
        ----------
        todo : string (one of 'left', 'right', 'bottom', 'top')
            margin to alter.

        size : float
            Minimum size of the margin .  If it is larger than the
            existing minimum it updates the margin size. Fraction of
            figure size.

        cell : int
            Cell column or row to edit.
        """

        if size > self.margin_vals[todo][cell]:
            self.edit_margin(todo, size, cell)

    def edit_margins(self, todo, size):
        """
        Change the size of all the margin of all the cells in the layout grid.

        Parameters
        ----------
        todo : string (one of 'left', 'right', 'bottom', 'top')
            margin to alter.

        size : float
            Size to set the margins.  Fraction of figure size.
        """

        for i in range(len(self.margin_vals[todo])):
            self.edit_margin(todo, size, i)

    def edit_all_margins_min(self, todo, size):
        """
        Change the minimum size of all the margin of all
        the cells in the layout grid.

        Parameters
        ----------
        todo : {'left', 'right', 'bottom', 'top'}
            The margin to alter.

        size : float
            Minimum size of the margin.  If it is larger than the
            existing minimum it updates the margin size. Fraction of
            figure size.
        """

        for i in range(len(self.margin_vals[todo])):
            self.edit_margin_min(todo, size, i)

    def edit_outer_margin_mins(self, margin, ss):
        """
        Edit all four margin minimums in one statement.

        Parameters
        ----------
        margin : dict
            size of margins in a dict with keys 'left', 'right', 'bottom',
            'top'

        ss : SubplotSpec
            defines the subplotspec these margins should be applied to
        """

        self.edit_margin_min('left', margin['left'], ss.colspan.start)
        self.edit_margin_min('leftcb', margin['leftcb'], ss.colspan.start)
        self.edit_margin_min('right', margin['right'], ss.colspan.stop - 1)
        self.edit_margin_min('rightcb', margin['rightcb'], ss.colspan.stop - 1)
        # rows are from the top down:
        self.edit_margin_min('top', margin['top'], ss.rowspan.start)
        self.edit_margin_min('topcb', margin['topcb'], ss.rowspan.start)
        self.edit_margin_min('bottom', margin['bottom'], ss.rowspan.stop - 1)
        self.edit_margin_min('bottomcb', margin['bottomcb'],
                             ss.rowspan.stop - 1)

    def get_margins(self, todo, col):
        """Return the margin at this position"""
        return self.margin_vals[todo][col]

    def get_outer_bbox(self, rows=0, cols=0):
        """
        Return the outer bounding box of the subplot specs
        given by rows and cols.  rows and cols can be spans.
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            self.lefts[cols[0]].value(),
            self.bottoms[rows[-1]].value(),
            self.rights[cols[-1]].value(),
            self.tops[rows[0]].value())
        return bbox

    def get_inner_bbox(self, rows=0, cols=0):
        """
        Return the inner bounding box of the subplot specs
        given by rows and cols.  rows and cols can be spans.
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            (self.lefts[cols[0]].value() +
                self.margins['left'][cols[0]].value() +
                self.margins['leftcb'][cols[0]].value()),
            (self.bottoms[rows[-1]].value() +
                self.margins['bottom'][rows[-1]].value() +
                self.margins['bottomcb'][rows[-1]].value()),
            (self.rights[cols[-1]].value() -
                self.margins['right'][cols[-1]].value() -
                self.margins['rightcb'][cols[-1]].value()),
            (self.tops[rows[0]].value() -
                self.margins['top'][rows[0]].value() -
                self.margins['topcb'][rows[0]].value())
        )
        return bbox

    def get_bbox_for_cb(self, rows=0, cols=0):
        """
        Return the bounding box that includes the
        decorations but, *not* the colorbar...
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            (self.lefts[cols[0]].value() +
                self.margins['leftcb'][cols[0]].value()),
            (self.bottoms[rows[-1]].value() +
                self.margins['bottomcb'][rows[-1]].value()),
            (self.rights[cols[-1]].value() -
                self.margins['rightcb'][cols[-1]].value()),
            (self.tops[rows[0]].value() -
                self.margins['topcb'][rows[0]].value())
        )
        return bbox

    def get_left_margin_bbox(self, rows=0, cols=0):
        """
        Return the left margin bounding box of the subplot specs
        given by rows and cols.  rows and cols can be spans.
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            (self.lefts[cols[0]].value() +
                self.margins['leftcb'][cols[0]].value()),
            (self.bottoms[rows[-1]].value()),
            (self.lefts[cols[0]].value() +
                self.margins['leftcb'][cols[0]].value() +
                self.margins['left'][cols[0]].value()),
            (self.tops[rows[0]].value()))
        return bbox

    def get_bottom_margin_bbox(self, rows=0, cols=0):
        """
        Return the left margin bounding box of the subplot specs
        given by rows and cols.  rows and cols can be spans.
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            (self.lefts[cols[0]].value()),
            (self.bottoms[rows[-1]].value() +
             self.margins['bottomcb'][rows[-1]].value()),
            (self.rights[cols[-1]].value()),
            (self.bottoms[rows[-1]].value() +
                self.margins['bottom'][rows[-1]].value() +
             self.margins['bottomcb'][rows[-1]].value()
             ))
        return bbox

    def get_right_margin_bbox(self, rows=0, cols=0):
        """
        Return the left margin bounding box of the subplot specs
        given by rows and cols.  rows and cols can be spans.
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            (self.rights[cols[-1]].value() -
                self.margins['right'][cols[-1]].value() -
                self.margins['rightcb'][cols[-1]].value()),
            (self.bottoms[rows[-1]].value()),
            (self.rights[cols[-1]].value() -
                self.margins['rightcb'][cols[-1]].value()),
            (self.tops[rows[0]].value()))
        return bbox

    def get_top_margin_bbox(self, rows=0, cols=0):
        """
        Return the left margin bounding box of the subplot specs
        given by rows and cols.  rows and cols can be spans.
        """
        rows = np.atleast_1d(rows)
        cols = np.atleast_1d(cols)

        bbox = Bbox.from_extents(
            (self.lefts[cols[0]].value()),
            (self.tops[rows[0]].value() -
                self.margins['topcb'][rows[0]].value()),
            (self.rights[cols[-1]].value()),
            (self.tops[rows[0]].value() -
                self.margins['topcb'][rows[0]].value() -
                self.margins['top'][rows[0]].value()))
        return bbox

    def update_variables(self):
        """
        Update the variables for the solver attached to this layoutgrid.
        """
        self.solver.updateVariables()

_layoutboxobjnum = itertools.count()


def seq_id():
    """Generate a short sequential id for layoutbox objects."""
    return '%06d' % next(_layoutboxobjnum)


def plot_children(fig, lg=None, level=0):
    """Simple plotting to show where boxes are."""
    if lg is None:
        _layoutgrids = fig.get_layout_engine().execute(fig)
        lg = _layoutgrids[fig]
    colors = mpl.rcParams["axes.prop_cycle"].by_key()["color"]
    col = colors[level]
    for i in range(lg.nrows):
        for j in range(lg.ncols):
            bb = lg.get_outer_bbox(rows=i, cols=j)
            fig.add_artist(
                mpatches.Rectangle(bb.p0, bb.width, bb.height, linewidth=1,
                                   edgecolor='0.7', facecolor='0.7',
                                   alpha=0.2, transform=fig.transFigure,
                                   zorder=-3))
            bbi = lg.get_inner_bbox(rows=i, cols=j)
            fig.add_artist(
                mpatches.Rectangle(bbi.p0, bbi.width, bbi.height, linewidth=2,
                                   edgecolor=col, facecolor='none',
                                   transform=fig.transFigure, zorder=-2))

            bbi = lg.get_left_margin_bbox(rows=i, cols=j)
            fig.add_artist(
                mpatches.Rectangle(bbi.p0, bbi.width, bbi.height, linewidth=0,
                                   edgecolor='none', alpha=0.2,
                                   facecolor=[0.5, 0.7, 0.5],
                                   transform=fig.transFigure, zorder=-2))
            bbi = lg.get_right_margin_bbox(rows=i, cols=j)
            fig.add_artist(
                mpatches.Rectangle(bbi.p0, bbi.width, bbi.height, linewidth=0,
                                   edgecolor='none', alpha=0.2,
                                   facecolor=[0.7, 0.5, 0.5],
                                   transform=fig.transFigure, zorder=-2))
            bbi = lg.get_bottom_margin_bbox(rows=i, cols=j)
            fig.add_artist(
                mpatches.Rectangle(bbi.p0, bbi.width, bbi.height, linewidth=0,
                                   edgecolor='none', alpha=0.2,
                                   facecolor=[0.5, 0.5, 0.7],
                                   transform=fig.transFigure, zorder=-2))
            bbi = lg.get_top_margin_bbox(rows=i, cols=j)
            fig.add_artist(
                mpatches.Rectangle(bbi.p0, bbi.width, bbi.height, linewidth=0,
                                   edgecolor='none', alpha=0.2,
                                   facecolor=[0.7, 0.2, 0.7],
                                   transform=fig.transFigure, zorder=-2))
    for ch in lg.children.flat:
        if ch is not None:
            plot_children(fig, ch, level=level+1)
