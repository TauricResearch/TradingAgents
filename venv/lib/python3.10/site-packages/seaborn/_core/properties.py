from __future__ import annotations
import itertools
import warnings

import numpy as np
from numpy.typing import ArrayLike
from pandas import Series
import matplotlib as mpl
from matplotlib.colors import to_rgb, to_rgba, to_rgba_array
from matplotlib.markers import MarkerStyle
from matplotlib.path import Path

from seaborn._core.scales import Scale, Boolean, Continuous, Nominal, Temporal
from seaborn._core.rules import categorical_order, variable_type
from seaborn.palettes import QUAL_PALETTES, color_palette, blend_palette
from seaborn.utils import get_color_cycle

from typing import Any, Callable, Tuple, List, Union, Optional

RGBTuple = Tuple[float, float, float]
RGBATuple = Tuple[float, float, float, float]
ColorSpec = Union[RGBTuple, RGBATuple, str]

DashPattern = Tuple[float, ...]
DashPatternWithOffset = Tuple[float, Optional[DashPattern]]

MarkerPattern = Union[
    float,
    str,
    Tuple[int, int, float],
    List[Tuple[float, float]],
    Path,
    MarkerStyle,
]

Mapping = Callable[[ArrayLike], ArrayLike]


# =================================================================================== #
# Base classes
# =================================================================================== #


class Property:
    """Base class for visual properties that can be set directly or be data scaling."""

    # When True, scales for this property will populate the legend by default
    legend = False

    # When True, scales for this property normalize data to [0, 1] before mapping
    normed = False

    def __init__(self, variable: str | None = None):
        """Initialize the property with the name of the corresponding plot variable."""
        if not variable:
            variable = self.__class__.__name__.lower()
        self.variable = variable

    def default_scale(self, data: Series) -> Scale:
        """Given data, initialize appropriate scale class."""

        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)
        if var_type == "numeric":
            return Continuous()
        elif var_type == "datetime":
            return Temporal()
        elif var_type == "boolean":
            return Boolean()
        else:
            return Nominal()

    def infer_scale(self, arg: Any, data: Series) -> Scale:
        """Given data and a scaling argument, initialize appropriate scale class."""
        # TODO put these somewhere external for validation
        # TODO putting this here won't pick it up if subclasses define infer_scale
        # (e.g. color). How best to handle that? One option is to call super after
        # handling property-specific possibilities (e.g. for color check that the
        # arg is not a valid palette name) but that could get tricky.
        trans_args = ["log", "symlog", "logit", "pow", "sqrt"]
        if isinstance(arg, str):
            if any(arg.startswith(k) for k in trans_args):
                # TODO validate numeric type? That should happen centrally somewhere
                return Continuous(trans=arg)
            else:
                msg = f"Unknown magic arg for {self.variable} scale: '{arg}'."
                raise ValueError(msg)
        else:
            arg_type = type(arg).__name__
            msg = f"Magic arg for {self.variable} scale must be str, not {arg_type}."
            raise TypeError(msg)

    def get_mapping(self, scale: Scale, data: Series) -> Mapping:
        """Return a function that maps from data domain to property range."""
        def identity(x):
            return x
        return identity

    def standardize(self, val: Any) -> Any:
        """Coerce flexible property value to standardized representation."""
        return val

    def _check_dict_entries(self, levels: list, values: dict) -> None:
        """Input check when values are provided as a dictionary."""
        missing = set(levels) - set(values)
        if missing:
            formatted = ", ".join(map(repr, sorted(missing, key=str)))
            err = f"No entry in {self.variable} dictionary for {formatted}"
            raise ValueError(err)

    def _check_list_length(self, levels: list, values: list) -> list:
        """Input check when values are provided as a list."""
        message = ""
        if len(levels) > len(values):
            message = " ".join([
                f"\nThe {self.variable} list has fewer values ({len(values)})",
                f"than needed ({len(levels)}) and will cycle, which may",
                "produce an uninterpretable plot."
            ])
            values = [x for _, x in zip(levels, itertools.cycle(values))]

        elif len(values) > len(levels):
            message = " ".join([
                f"The {self.variable} list has more values ({len(values)})",
                f"than needed ({len(levels)}), which may not be intended.",
            ])
            values = values[:len(levels)]

        # TODO look into custom PlotSpecWarning with better formatting
        if message:
            warnings.warn(message, UserWarning)

        return values


# =================================================================================== #
# Properties relating to spatial position of marks on the plotting axes
# =================================================================================== #


class Coordinate(Property):
    """The position of visual marks with respect to the axes of the plot."""
    legend = False
    normed = False


# =================================================================================== #
# Properties with numeric values where scale range can be defined as an interval
# =================================================================================== #


class IntervalProperty(Property):
    """A numeric property where scale range can be defined as an interval."""
    legend = True
    normed = True

    _default_range: tuple[float, float] = (0, 1)

    @property
    def default_range(self) -> tuple[float, float]:
        """Min and max values used by default for semantic mapping."""
        return self._default_range

    def _forward(self, values: ArrayLike) -> ArrayLike:
        """Transform applied to native values before linear mapping into interval."""
        return values

    def _inverse(self, values: ArrayLike) -> ArrayLike:
        """Transform applied to results of mapping that returns to native values."""
        return values

    def infer_scale(self, arg: Any, data: Series) -> Scale:
        """Given data and a scaling argument, initialize appropriate scale class."""

        # TODO infer continuous based on log/sqrt etc?

        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)

        if var_type == "boolean":
            return Boolean(arg)
        elif isinstance(arg, (list, dict)):
            return Nominal(arg)
        elif var_type == "categorical":
            return Nominal(arg)
        elif var_type == "datetime":
            return Temporal(arg)
        # TODO other variable types
        else:
            return Continuous(arg)

    def get_mapping(self, scale: Scale, data: Series) -> Mapping:
        """Return a function that maps from data domain to property range."""
        if isinstance(scale, Nominal):
            return self._get_nominal_mapping(scale, data)
        elif isinstance(scale, Boolean):
            return self._get_boolean_mapping(scale, data)

        if scale.values is None:
            vmin, vmax = self._forward(self.default_range)
        elif isinstance(scale.values, tuple) and len(scale.values) == 2:
            vmin, vmax = self._forward(scale.values)
        else:
            if isinstance(scale.values, tuple):
                actual = f"{len(scale.values)}-tuple"
            else:
                actual = str(type(scale.values))
            scale_class = scale.__class__.__name__
            err = " ".join([
                f"Values for {self.variable} variables with {scale_class} scale",
                f"must be 2-tuple; not {actual}.",
            ])
            raise TypeError(err)

        def mapping(x):
            return self._inverse(np.multiply(x, vmax - vmin) + vmin)

        return mapping

    def _get_nominal_mapping(self, scale: Nominal, data: Series) -> Mapping:
        """Identify evenly-spaced values using interval or explicit mapping."""
        levels = categorical_order(data, scale.order)
        values = self._get_values(scale, levels)

        def mapping(x):
            ixs = np.asarray(x, np.intp)
            out = np.full(len(x), np.nan)
            use = np.isfinite(x)
            out[use] = np.take(values, ixs[use])
            return out

        return mapping

    def _get_boolean_mapping(self, scale: Boolean, data: Series) -> Mapping:
        """Identify evenly-spaced values using interval or explicit mapping."""
        values = self._get_values(scale, [True, False])

        def mapping(x):
            out = np.full(len(x), np.nan)
            use = np.isfinite(x)
            out[use] = np.where(x[use], *values)
            return out

        return mapping

    def _get_values(self, scale: Scale, levels: list) -> list:
        """Validate scale.values and identify a value for each level."""
        if isinstance(scale.values, dict):
            self._check_dict_entries(levels, scale.values)
            values = [scale.values[x] for x in levels]
        elif isinstance(scale.values, list):
            values = self._check_list_length(levels, scale.values)
        else:
            if scale.values is None:
                vmin, vmax = self.default_range
            elif isinstance(scale.values, tuple):
                vmin, vmax = scale.values
            else:
                scale_class = scale.__class__.__name__
                err = " ".join([
                    f"Values for {self.variable} variables with {scale_class} scale",
                    f"must be a dict, list or tuple; not {type(scale.values)}",
                ])
                raise TypeError(err)

            vmin, vmax = self._forward([vmin, vmax])
            values = list(self._inverse(np.linspace(vmax, vmin, len(levels))))

        return values


class PointSize(IntervalProperty):
    """Size (diameter) of a point mark, in points, with scaling by area."""
    _default_range = 2, 8  # TODO use rcparams?

    def _forward(self, values):
        """Square native values to implement linear scaling of point area."""
        return np.square(values)

    def _inverse(self, values):
        """Invert areal values back to point diameter."""
        return np.sqrt(values)


class LineWidth(IntervalProperty):
    """Thickness of a line mark, in points."""
    @property
    def default_range(self) -> tuple[float, float]:
        """Min and max values used by default for semantic mapping."""
        base = mpl.rcParams["lines.linewidth"]
        return base * .5, base * 2


class EdgeWidth(IntervalProperty):
    """Thickness of the edges on a patch mark, in points."""
    @property
    def default_range(self) -> tuple[float, float]:
        """Min and max values used by default for semantic mapping."""
        base = mpl.rcParams["patch.linewidth"]
        return base * .5, base * 2


class Stroke(IntervalProperty):
    """Thickness of lines that define point glyphs."""
    _default_range = .25, 2.5


class Alpha(IntervalProperty):
    """Opacity of the color values for an arbitrary mark."""
    _default_range = .3, .95
    # TODO validate / enforce that output is in [0, 1]


class Offset(IntervalProperty):
    """Offset for edge-aligned text, in point units."""
    _default_range = 0, 5
    _legend = False


class FontSize(IntervalProperty):
    """Font size for textual marks, in points."""
    _legend = False

    @property
    def default_range(self) -> tuple[float, float]:
        """Min and max values used by default for semantic mapping."""
        base = mpl.rcParams["font.size"]
        return base * .5, base * 2


# =================================================================================== #
# Properties defined by arbitrary objects with inherently nominal scaling
# =================================================================================== #


class ObjectProperty(Property):
    """A property defined by arbitrary an object, with inherently nominal scaling."""
    legend = True
    normed = False

    # Object representing null data, should appear invisible when drawn by matplotlib
    # Note that we now drop nulls in Plot._plot_layer and thus may not need this
    null_value: Any = None

    def _default_values(self, n: int) -> list:
        raise NotImplementedError()

    def default_scale(self, data: Series) -> Scale:
        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)
        return Boolean() if var_type == "boolean" else Nominal()

    def infer_scale(self, arg: Any, data: Series) -> Scale:
        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)
        return Boolean(arg) if var_type == "boolean" else Nominal(arg)

    def get_mapping(self, scale: Scale, data: Series) -> Mapping:
        """Define mapping as lookup into list of object values."""
        boolean_scale = isinstance(scale, Boolean)
        order = getattr(scale, "order", [True, False] if boolean_scale else None)
        levels = categorical_order(data, order)
        values = self._get_values(scale, levels)

        if boolean_scale:
            values = values[::-1]

        def mapping(x):
            ixs = np.asarray(np.nan_to_num(x), np.intp)
            return [
                values[ix] if np.isfinite(x_i) else self.null_value
                for x_i, ix in zip(x, ixs)
            ]

        return mapping

    def _get_values(self, scale: Scale, levels: list) -> list:
        """Validate scale.values and identify a value for each level."""
        n = len(levels)
        if isinstance(scale.values, dict):
            self._check_dict_entries(levels, scale.values)
            values = [scale.values[x] for x in levels]
        elif isinstance(scale.values, list):
            values = self._check_list_length(levels, scale.values)
        elif scale.values is None:
            values = self._default_values(n)
        else:
            msg = " ".join([
                f"Scale values for a {self.variable} variable must be provided",
                f"in a dict or list; not {type(scale.values)}."
            ])
            raise TypeError(msg)

        values = [self.standardize(x) for x in values]
        return values


class Marker(ObjectProperty):
    """Shape of points in scatter-type marks or lines with data points marked."""
    null_value = MarkerStyle("")

    # TODO should we have named marker "palettes"? (e.g. see d3 options)

    # TODO need some sort of "require_scale" functionality
    # to raise when we get the wrong kind explicitly specified

    def standardize(self, val: MarkerPattern) -> MarkerStyle:
        return MarkerStyle(val)

    def _default_values(self, n: int) -> list[MarkerStyle]:
        """Build an arbitrarily long list of unique marker styles.

        Parameters
        ----------
        n : int
            Number of unique marker specs to generate.

        Returns
        -------
        markers : list of string or tuples
            Values for defining :class:`matplotlib.markers.MarkerStyle` objects.
            All markers will be filled.

        """
        # Start with marker specs that are well distinguishable
        markers = [
            "o", "X", (4, 0, 45), "P", (4, 0, 0), (4, 1, 0), "^", (4, 1, 45), "v",
        ]

        # Now generate more from regular polygons of increasing order
        s = 5
        while len(markers) < n:
            a = 360 / (s + 1) / 2
            markers.extend([(s + 1, 1, a), (s + 1, 0, a), (s, 1, 0), (s, 0, 0)])
            s += 1

        markers = [MarkerStyle(m) for m in markers[:n]]

        return markers


class LineStyle(ObjectProperty):
    """Dash pattern for line-type marks."""
    null_value = ""

    def standardize(self, val: str | DashPattern) -> DashPatternWithOffset:
        return self._get_dash_pattern(val)

    def _default_values(self, n: int) -> list[DashPatternWithOffset]:
        """Build an arbitrarily long list of unique dash styles for lines.

        Parameters
        ----------
        n : int
            Number of unique dash specs to generate.

        Returns
        -------
        dashes : list of strings or tuples
            Valid arguments for the ``dashes`` parameter on
            :class:`matplotlib.lines.Line2D`. The first spec is a solid
            line (``""``), the remainder are sequences of long and short
            dashes.

        """
        # Start with dash specs that are well distinguishable
        dashes: list[str | DashPattern] = [
            "-", (4, 1.5), (1, 1), (3, 1.25, 1.5, 1.25), (5, 1, 1, 1),
        ]

        # Now programmatically build as many as we need
        p = 3
        while len(dashes) < n:

            # Take combinations of long and short dashes
            a = itertools.combinations_with_replacement([3, 1.25], p)
            b = itertools.combinations_with_replacement([4, 1], p)

            # Interleave the combinations, reversing one of the streams
            segment_list = itertools.chain(*zip(list(a)[1:-1][::-1], list(b)[1:-1]))

            # Now insert the gaps
            for segments in segment_list:
                gap = min(segments)
                spec = tuple(itertools.chain(*((seg, gap) for seg in segments)))
                dashes.append(spec)

            p += 1

        return [self._get_dash_pattern(x) for x in dashes]

    @staticmethod
    def _get_dash_pattern(style: str | DashPattern) -> DashPatternWithOffset:
        """Convert linestyle arguments to dash pattern with offset."""
        # Copied and modified from Matplotlib 3.4
        # go from short hand -> full strings
        ls_mapper = {"-": "solid", "--": "dashed", "-.": "dashdot", ":": "dotted"}
        if isinstance(style, str):
            style = ls_mapper.get(style, style)
            # un-dashed styles
            if style in ["solid", "none", "None"]:
                offset = 0
                dashes = None
            # dashed styles
            elif style in ["dashed", "dashdot", "dotted"]:
                offset = 0
                dashes = tuple(mpl.rcParams[f"lines.{style}_pattern"])
            else:
                options = [*ls_mapper.values(), *ls_mapper.keys()]
                msg = f"Linestyle string must be one of {options}, not {repr(style)}."
                raise ValueError(msg)

        elif isinstance(style, tuple):
            if len(style) > 1 and isinstance(style[1], tuple):
                offset, dashes = style
            elif len(style) > 1 and style[1] is None:
                offset, dashes = style
            else:
                offset = 0
                dashes = style
        else:
            val_type = type(style).__name__
            msg = f"Linestyle must be str or tuple, not {val_type}."
            raise TypeError(msg)

        # Normalize offset to be positive and shorter than the dash cycle
        if dashes is not None:
            try:
                dsum = sum(dashes)
            except TypeError as err:
                msg = f"Invalid dash pattern: {dashes}"
                raise TypeError(msg) from err
            if dsum:
                offset %= dsum

        return offset, dashes


class TextAlignment(ObjectProperty):
    legend = False


class HorizontalAlignment(TextAlignment):

    def _default_values(self, n: int) -> list:
        vals = itertools.cycle(["left", "right"])
        return [next(vals) for _ in range(n)]


class VerticalAlignment(TextAlignment):

    def _default_values(self, n: int) -> list:
        vals = itertools.cycle(["top", "bottom"])
        return [next(vals) for _ in range(n)]


# =================================================================================== #
# Properties with  RGB(A) color values
# =================================================================================== #


class Color(Property):
    """Color, as RGB(A), scalable with nominal palettes or continuous gradients."""
    legend = True
    normed = True

    def standardize(self, val: ColorSpec) -> RGBTuple | RGBATuple:
        # Return color with alpha channel only if the input spec has it
        # This is so that RGBA colors can override the Alpha property
        if to_rgba(val) != to_rgba(val, 1):
            return to_rgba(val)
        else:
            return to_rgb(val)

    def _standardize_color_sequence(self, colors: ArrayLike) -> ArrayLike:
        """Convert color sequence to RGB(A) array, preserving but not adding alpha."""
        def has_alpha(x):
            return to_rgba(x) != to_rgba(x, 1)

        if isinstance(colors, np.ndarray):
            needs_alpha = colors.shape[1] == 4
        else:
            needs_alpha = any(has_alpha(x) for x in colors)

        if needs_alpha:
            return to_rgba_array(colors)
        else:
            return to_rgba_array(colors)[:, :3]

    def infer_scale(self, arg: Any, data: Series) -> Scale:
        # TODO when inferring Continuous without data, verify type

        # TODO need to rethink the variable type system
        # (e.g. boolean, ordered categories as Ordinal, etc)..
        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)

        if var_type == "boolean":
            return Boolean(arg)

        if isinstance(arg, (dict, list)):
            return Nominal(arg)

        if isinstance(arg, tuple):
            if var_type == "categorical":
                # TODO It seems reasonable to allow a gradient mapping for nominal
                # scale but it also feels "technically" wrong. Should this infer
                # Ordinal with categorical data and, if so, verify orderedness?
                return Nominal(arg)
            return Continuous(arg)

        if callable(arg):
            return Continuous(arg)

        # TODO Do we accept str like "log", "pow", etc. for semantics?

        if not isinstance(arg, str):
            msg = " ".join([
                f"A single scale argument for {self.variable} variables must be",
                f"a string, dict, tuple, list, or callable, not {type(arg)}."
            ])
            raise TypeError(msg)

        if arg in QUAL_PALETTES:
            return Nominal(arg)
        elif var_type == "numeric":
            return Continuous(arg)
        # TODO implement scales for date variables and any others.
        else:
            return Nominal(arg)

    def get_mapping(self, scale: Scale, data: Series) -> Mapping:
        """Return a function that maps from data domain to color values."""
        # TODO what is best way to do this conditional?
        # Should it be class-based or should classes have behavioral attributes?
        if isinstance(scale, Nominal):
            return self._get_nominal_mapping(scale, data)
        elif isinstance(scale, Boolean):
            return self._get_boolean_mapping(scale, data)

        if scale.values is None:
            # TODO Rethink best default continuous color gradient
            mapping = color_palette("ch:", as_cmap=True)
        elif isinstance(scale.values, tuple):
            # TODO blend_palette will strip alpha, but we should support
            # interpolation on all four channels
            mapping = blend_palette(scale.values, as_cmap=True)
        elif isinstance(scale.values, str):
            # TODO for matplotlib colormaps this will clip extremes, which is
            # different from what using the named colormap directly would do
            # This may or may not be desireable.
            mapping = color_palette(scale.values, as_cmap=True)
        elif callable(scale.values):
            mapping = scale.values
        else:
            scale_class = scale.__class__.__name__
            msg = " ".join([
                f"Scale values for {self.variable} with a {scale_class} mapping",
                f"must be string, tuple, or callable; not {type(scale.values)}."
            ])
            raise TypeError(msg)

        def _mapping(x):
            # Remove alpha channel so it does not override alpha property downstream
            # TODO this will need to be more flexible to support RGBA tuples (see above)
            invalid = ~np.isfinite(x)
            out = mapping(x)[:, :3]
            out[invalid] = np.nan
            return out

        return _mapping

    def _get_nominal_mapping(self, scale: Nominal, data: Series) -> Mapping:

        levels = categorical_order(data, scale.order)
        colors = self._get_values(scale, levels)

        def mapping(x):
            ixs = np.asarray(np.nan_to_num(x), np.intp)
            use = np.isfinite(x)
            out = np.full((len(ixs), colors.shape[1]), np.nan)
            out[use] = np.take(colors, ixs[use], axis=0)
            return out

        return mapping

    def _get_boolean_mapping(self, scale: Boolean, data: Series) -> Mapping:

        colors = self._get_values(scale, [True, False])

        def mapping(x):

            use = np.isfinite(x)
            x = np.asarray(np.nan_to_num(x)).astype(bool)
            out = np.full((len(x), colors.shape[1]), np.nan)
            out[x & use] = colors[0]
            out[~x & use] = colors[1]
            return out

        return mapping

    def _get_values(self, scale: Scale, levels: list) -> ArrayLike:
        """Validate scale.values and identify a value for each level."""
        n = len(levels)
        values = scale.values
        if isinstance(values, dict):
            self._check_dict_entries(levels, values)
            colors = [values[x] for x in levels]
        elif isinstance(values, list):
            colors = self._check_list_length(levels, values)
        elif isinstance(values, tuple):
            colors = blend_palette(values, n)
        elif isinstance(values, str):
            colors = color_palette(values, n)
        elif values is None:
            if n <= len(get_color_cycle()):
                # Use current (global) default palette
                colors = color_palette(n_colors=n)
            else:
                colors = color_palette("husl", n)
        else:
            scale_class = scale.__class__.__name__
            msg = " ".join([
                f"Scale values for {self.variable} with a {scale_class} mapping",
                f"must be string, list, tuple, or dict; not {type(scale.values)}."
            ])
            raise TypeError(msg)

        return self._standardize_color_sequence(colors)


# =================================================================================== #
# Properties that can take only two states
# =================================================================================== #


class Fill(Property):
    """Boolean property of points/bars/patches that can be solid or outlined."""
    legend = True
    normed = False

    def default_scale(self, data: Series) -> Scale:
        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)
        return Boolean() if var_type == "boolean" else Nominal()

    def infer_scale(self, arg: Any, data: Series) -> Scale:
        var_type = variable_type(data, boolean_type="boolean", strict_boolean=True)
        return Boolean(arg) if var_type == "boolean" else Nominal(arg)

    def standardize(self, val: Any) -> bool:
        return bool(val)

    def _default_values(self, n: int) -> list:
        """Return a list of n values, alternating True and False."""
        if n > 2:
            msg = " ".join([
                f"The variable assigned to {self.variable} has more than two levels,",
                f"so {self.variable} values will cycle and may be uninterpretable",
            ])
            # TODO fire in a "nice" way (see above)
            warnings.warn(msg, UserWarning)
        return [x for x, _ in zip(itertools.cycle([True, False]), range(n))]

    def get_mapping(self, scale: Scale, data: Series) -> Mapping:
        """Return a function that maps each data value to True or False."""
        boolean_scale = isinstance(scale, Boolean)
        order = getattr(scale, "order", [True, False] if boolean_scale else None)
        levels = categorical_order(data, order)
        values = self._get_values(scale, levels)

        if boolean_scale:
            values = values[::-1]

        def mapping(x):
            ixs = np.asarray(np.nan_to_num(x), np.intp)
            return [
                values[ix] if np.isfinite(x_i) else False
                for x_i, ix in zip(x, ixs)
            ]

        return mapping

    def _get_values(self, scale: Scale, levels: list) -> list:
        """Validate scale.values and identify a value for each level."""
        if isinstance(scale.values, list):
            values = [bool(x) for x in scale.values]
        elif isinstance(scale.values, dict):
            values = [bool(scale.values[x]) for x in levels]
        elif scale.values is None:
            values = self._default_values(len(levels))
        else:
            msg = " ".join([
                f"Scale values for {self.variable} must be passed in",
                f"a list or dict; not {type(scale.values)}."
            ])
            raise TypeError(msg)

        return values


# =================================================================================== #
# Enumeration of properties for use by Plot and Mark classes
# =================================================================================== #
# TODO turn this into a property registry with hooks, etc.
# TODO Users do not interact directly with properties, so how to document them?


PROPERTY_CLASSES = {
    "x": Coordinate,
    "y": Coordinate,
    "color": Color,
    "alpha": Alpha,
    "fill": Fill,
    "marker": Marker,
    "pointsize": PointSize,
    "stroke": Stroke,
    "linewidth": LineWidth,
    "linestyle": LineStyle,
    "fillcolor": Color,
    "fillalpha": Alpha,
    "edgewidth": EdgeWidth,
    "edgestyle": LineStyle,
    "edgecolor": Color,
    "edgealpha": Alpha,
    "text": Property,
    "halign": HorizontalAlignment,
    "valign": VerticalAlignment,
    "offset": Offset,
    "fontsize": FontSize,
    "xmin": Coordinate,
    "xmax": Coordinate,
    "ymin": Coordinate,
    "ymax": Coordinate,
    "group": Property,
    # TODO pattern?
    # TODO gradient?
}

PROPERTIES = {var: cls(var) for var, cls in PROPERTY_CLASSES.items()}
