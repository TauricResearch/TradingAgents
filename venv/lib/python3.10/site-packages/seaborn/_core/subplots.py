from __future__ import annotations
from collections.abc import Generator

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # TODO move to seaborn._core.typing?
    from seaborn._core.plot import FacetSpec, PairSpec
    from matplotlib.figure import SubFigure


class Subplots:
    """
    Interface for creating and using matplotlib subplots based on seaborn parameters.

    Parameters
    ----------
    subplot_spec : dict
        Keyword args for :meth:`matplotlib.figure.Figure.subplots`.
    facet_spec : dict
        Parameters that control subplot faceting.
    pair_spec : dict
        Parameters that control subplot pairing.
    data : PlotData
        Data used to define figure setup.

    """
    def __init__(
        self,
        subplot_spec: dict,  # TODO define as TypedDict
        facet_spec: FacetSpec,
        pair_spec: PairSpec,
    ):

        self.subplot_spec = subplot_spec

        self._check_dimension_uniqueness(facet_spec, pair_spec)
        self._determine_grid_dimensions(facet_spec, pair_spec)
        self._handle_wrapping(facet_spec, pair_spec)
        self._determine_axis_sharing(pair_spec)

    def _check_dimension_uniqueness(
        self, facet_spec: FacetSpec, pair_spec: PairSpec
    ) -> None:
        """Reject specs that pair and facet on (or wrap to) same figure dimension."""
        err = None

        facet_vars = facet_spec.get("variables", {})

        if facet_spec.get("wrap") and {"col", "row"} <= set(facet_vars):
            err = "Cannot wrap facets when specifying both `col` and `row`."
        elif (
            pair_spec.get("wrap")
            and pair_spec.get("cross", True)
            and len(pair_spec.get("structure", {}).get("x", [])) > 1
            and len(pair_spec.get("structure", {}).get("y", [])) > 1
        ):
            err = "Cannot wrap subplots when pairing on both `x` and `y`."

        collisions = {"x": ["columns", "rows"], "y": ["rows", "columns"]}
        for pair_axis, (multi_dim, wrap_dim) in collisions.items():
            if pair_axis not in pair_spec.get("structure", {}):
                continue
            elif multi_dim[:3] in facet_vars:
                err = f"Cannot facet the {multi_dim} while pairing on `{pair_axis}``."
            elif wrap_dim[:3] in facet_vars and facet_spec.get("wrap"):
                err = f"Cannot wrap the {wrap_dim} while pairing on `{pair_axis}``."
            elif wrap_dim[:3] in facet_vars and pair_spec.get("wrap"):
                err = f"Cannot wrap the {multi_dim} while faceting the {wrap_dim}."

        if err is not None:
            raise RuntimeError(err)  # TODO what err class? Define PlotSpecError?

    def _determine_grid_dimensions(
        self, facet_spec: FacetSpec, pair_spec: PairSpec
    ) -> None:
        """Parse faceting and pairing information to define figure structure."""
        self.grid_dimensions: dict[str, list] = {}
        for dim, axis in zip(["col", "row"], ["x", "y"]):

            facet_vars = facet_spec.get("variables", {})
            if dim in facet_vars:
                self.grid_dimensions[dim] = facet_spec["structure"][dim]
            elif axis in pair_spec.get("structure", {}):
                self.grid_dimensions[dim] = [
                    None for _ in pair_spec.get("structure", {})[axis]
                ]
            else:
                self.grid_dimensions[dim] = [None]

            self.subplot_spec[f"n{dim}s"] = len(self.grid_dimensions[dim])

        if not pair_spec.get("cross", True):
            self.subplot_spec["nrows"] = 1

        self.n_subplots = self.subplot_spec["ncols"] * self.subplot_spec["nrows"]

    def _handle_wrapping(
        self, facet_spec: FacetSpec, pair_spec: PairSpec
    ) -> None:
        """Update figure structure parameters based on facet/pair wrapping."""
        self.wrap = wrap = facet_spec.get("wrap") or pair_spec.get("wrap")
        if not wrap:
            return

        wrap_dim = "row" if self.subplot_spec["nrows"] > 1 else "col"
        flow_dim = {"row": "col", "col": "row"}[wrap_dim]
        n_subplots = self.subplot_spec[f"n{wrap_dim}s"]
        flow = int(np.ceil(n_subplots / wrap))

        if wrap < self.subplot_spec[f"n{wrap_dim}s"]:
            self.subplot_spec[f"n{wrap_dim}s"] = wrap
        self.subplot_spec[f"n{flow_dim}s"] = flow
        self.n_subplots = n_subplots
        self.wrap_dim = wrap_dim

    def _determine_axis_sharing(self, pair_spec: PairSpec) -> None:
        """Update subplot spec with default or specified axis sharing parameters."""
        axis_to_dim = {"x": "col", "y": "row"}
        key: str
        val: str | bool
        for axis in "xy":
            key = f"share{axis}"
            # Always use user-specified value, if present
            if key not in self.subplot_spec:
                if axis in pair_spec.get("structure", {}):
                    # Paired axes are shared along one dimension by default
                    if self.wrap is None and pair_spec.get("cross", True):
                        val = axis_to_dim[axis]
                    else:
                        val = False
                else:
                    # This will pick up faceted plots, as well as single subplot
                    # figures, where the value doesn't really matter
                    val = True
                self.subplot_spec[key] = val

    def init_figure(
        self,
        pair_spec: PairSpec,
        pyplot: bool = False,
        figure_kws: dict | None = None,
        target: Axes | Figure | SubFigure | None = None,
    ) -> Figure:
        """Initialize matplotlib objects and add seaborn-relevant metadata."""
        # TODO reduce need to pass pair_spec here?

        if figure_kws is None:
            figure_kws = {}

        if isinstance(target, mpl.axes.Axes):

            if max(self.subplot_spec["nrows"], self.subplot_spec["ncols"]) > 1:
                err = " ".join([
                    "Cannot create multiple subplots after calling `Plot.on` with",
                    f"a {mpl.axes.Axes} object.",
                    f" You may want to use a {mpl.figure.SubFigure} instead.",
                ])
                raise RuntimeError(err)

            self._subplot_list = [{
                "ax": target,
                "left": True,
                "right": True,
                "top": True,
                "bottom": True,
                "col": None,
                "row": None,
                "x": "x",
                "y": "y",
            }]
            self._figure = target.figure
            return self._figure

        elif isinstance(target, mpl.figure.SubFigure):
            figure = target.figure
        elif isinstance(target, mpl.figure.Figure):
            figure = target
        else:
            if pyplot:
                figure = plt.figure(**figure_kws)
            else:
                figure = mpl.figure.Figure(**figure_kws)
            target = figure
        self._figure = figure

        axs = target.subplots(**self.subplot_spec, squeeze=False)

        if self.wrap:
            # Remove unused Axes and flatten the rest into a (2D) vector
            axs_flat = axs.ravel({"col": "C", "row": "F"}[self.wrap_dim])
            axs, extra = np.split(axs_flat, [self.n_subplots])
            for ax in extra:
                ax.remove()
            if self.wrap_dim == "col":
                axs = axs[np.newaxis, :]
            else:
                axs = axs[:, np.newaxis]

        # Get i, j coordinates for each Axes object
        # Note that i, j are with respect to faceting/pairing,
        # not the subplot grid itself, (which only matters in the case of wrapping).
        iter_axs: np.ndenumerate | zip
        if not pair_spec.get("cross", True):
            indices = np.arange(self.n_subplots)
            iter_axs = zip(zip(indices, indices), axs.flat)
        else:
            iter_axs = np.ndenumerate(axs)

        self._subplot_list = []
        for (i, j), ax in iter_axs:

            info = {"ax": ax}

            nrows, ncols = self.subplot_spec["nrows"], self.subplot_spec["ncols"]
            if not self.wrap:
                info["left"] = j % ncols == 0
                info["right"] = (j + 1) % ncols == 0
                info["top"] = i == 0
                info["bottom"] = i == nrows - 1
            elif self.wrap_dim == "col":
                info["left"] = j % ncols == 0
                info["right"] = ((j + 1) % ncols == 0) or ((j + 1) == self.n_subplots)
                info["top"] = j < ncols
                info["bottom"] = j >= (self.n_subplots - ncols)
            elif self.wrap_dim == "row":
                info["left"] = i < nrows
                info["right"] = i >= self.n_subplots - nrows
                info["top"] = i % nrows == 0
                info["bottom"] = ((i + 1) % nrows == 0) or ((i + 1) == self.n_subplots)

            if not pair_spec.get("cross", True):
                info["top"] = j < ncols
                info["bottom"] = j >= self.n_subplots - ncols

            for dim in ["row", "col"]:
                idx = {"row": i, "col": j}[dim]
                info[dim] = self.grid_dimensions[dim][idx]

            for axis in "xy":

                idx = {"x": j, "y": i}[axis]
                if axis in pair_spec.get("structure", {}):
                    key = f"{axis}{idx}"
                else:
                    key = axis
                info[axis] = key

            self._subplot_list.append(info)

        return figure

    def __iter__(self) -> Generator[dict, None, None]:  # TODO TypedDict?
        """Yield each subplot dictionary with Axes object and metadata."""
        yield from self._subplot_list

    def __len__(self) -> int:
        """Return the number of subplots in this figure."""
        return len(self._subplot_list)
