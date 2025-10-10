"""Partially instantiate a variable font.

The module exports an `instantiateVariableFont` function and CLI that allow to
create full instances (i.e. static fonts) from variable fonts, as well as "partial"
variable fonts that only contain a subset of the original variation space.

For example, if you wish to pin the width axis to a given location while also
restricting the weight axis to 400..700 range, you can do:

.. code-block:: sh

    $ fonttools varLib.instancer ./NotoSans-VF.ttf wdth=85 wght=400:700

See `fonttools varLib.instancer --help` for more info on the CLI options.

The module's entry point is the `instantiateVariableFont` function, which takes
a TTFont object and a dict specifying either axis coodinates or (min, max) ranges,
and returns a new TTFont representing either a partial VF, or full instance if all
the VF axes were given an explicit coordinate.

E.g. here's how to pin the wght axis at a given location in a wght+wdth variable
font, keeping only the deltas associated with the wdth axis:
.. code-block:: pycon

    >>>
    >> from fontTools import ttLib
    >> from fontTools.varLib import instancer
    >> varfont = ttLib.TTFont("path/to/MyVariableFont.ttf")
    >> [a.axisTag for a in varfont["fvar"].axes]  # the varfont's current axes
    ['wght', 'wdth']
    >> partial = instancer.instantiateVariableFont(varfont, {"wght": 300})
    >> [a.axisTag for a in partial["fvar"].axes]  # axes left after pinning 'wght'
    ['wdth']

If the input location specifies all the axes, the resulting instance is no longer
'variable' (same as using fontools varLib.mutator):
.. code-block:: pycon

    >>>
    >> instance = instancer.instantiateVariableFont(
    ...     varfont, {"wght": 700, "wdth": 67.5}
    ... )
    >> "fvar" not in instance
    True

If one just want to drop an axis at the default location, without knowing in
advance what the default value for that axis is, one can pass a `None` value:
.. code-block:: pycon

    >>>
    >> instance = instancer.instantiateVariableFont(varfont, {"wght": None})
    >> len(varfont["fvar"].axes)
    1

From the console script, this is equivalent to passing `wght=drop` as input.

This module is similar to fontTools.varLib.mutator, which it's intended to supersede.
Note that, unlike varLib.mutator, when an axis is not mentioned in the input
location, by default the varLib.instancer will keep the axis and the corresponding
deltas, whereas mutator implicitly drops the axis at its default coordinate.
To obtain the same behavior as mutator, pass the `static=True` parameter or
the `--static` CLI option.

The module supports all the following "levels" of instancing, which can of
course be combined:

L1
    dropping one or more axes while leaving the default tables unmodified;
    .. code-block:: pycon

        >>>
        >> font = instancer.instantiateVariableFont(varfont, {"wght": None})

L2
    dropping one or more axes while pinning them at non-default locations;
    .. code-block:: pycon

        >>>
        >> font = instancer.instantiateVariableFont(varfont, {"wght": 700})

L3
    restricting the range of variation of one or more axes, by setting either
    a new minimum or maximum, potentially -- though not necessarily -- dropping
    entire regions of variations that fall completely outside this new range.
    .. code-block:: pycon

        >>>
        >> font = instancer.instantiateVariableFont(varfont, {"wght": (100, 300)})

L4
    moving the default location of an axis, by specifying (min,defalt,max) values:
    .. code-block:: pycon

        >>>
        >> font = instancer.instantiateVariableFont(varfont, {"wght": (100, 300, 700)})

Both TrueType-flavored (glyf+gvar) variable and CFF2 variable fonts are supported.
"""

from fontTools.misc.fixedTools import (
    floatToFixedToFloat,
    strToFixedToFloat,
    otRound,
)
from fontTools.varLib.models import normalizeValue, piecewiseLinearMap
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables import _g_l_y_f
from fontTools import varLib

# we import the `subset` module because we use the `prune_lookups` method on the GSUB
# table class, and that method is only defined dynamically upon importing `subset`
from fontTools import subset  # noqa: F401
from fontTools.cffLib import privateDictOperators2
from fontTools.cffLib.specializer import (
    programToCommands,
    commandsToProgram,
    specializeCommands,
    generalizeCommands,
)
from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF
from fontTools.varLib import builder
from fontTools.varLib.mvar import MVAR_ENTRIES
from fontTools.varLib.merger import MutatorMerger
from fontTools.varLib.instancer import names
from .featureVars import instantiateFeatureVariations
from fontTools.misc.cliTools import makeOutputFileName
from fontTools.varLib.instancer import solver
from fontTools.ttLib.tables.otTables import VarComponentFlags
import collections
import dataclasses
from contextlib import contextmanager
from copy import deepcopy
from enum import IntEnum
import logging
import os
import re
import io
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union
import warnings


log = logging.getLogger("fontTools.varLib.instancer")


def AxisRange(minimum, maximum):
    warnings.warn(
        "AxisRange is deprecated; use AxisTriple instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return AxisTriple(minimum, None, maximum)


def NormalizedAxisRange(minimum, maximum):
    warnings.warn(
        "NormalizedAxisRange is deprecated; use AxisTriple instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return NormalizedAxisTriple(minimum, None, maximum)


@dataclasses.dataclass(frozen=True, order=True, repr=False)
class AxisTriple(Sequence):
    """A triple of (min, default, max) axis values.

    Any of the values can be None, in which case the limitRangeAndPopulateDefaults()
    method can be used to fill in the missing values based on the fvar axis values.
    """

    minimum: Optional[float]
    default: Optional[float]
    maximum: Optional[float]

    def __post_init__(self):
        if self.default is None and self.minimum == self.maximum:
            object.__setattr__(self, "default", self.minimum)
        if (
            (
                self.minimum is not None
                and self.default is not None
                and self.minimum > self.default
            )
            or (
                self.default is not None
                and self.maximum is not None
                and self.default > self.maximum
            )
            or (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            )
        ):
            raise ValueError(
                f"{type(self).__name__} minimum ({self.minimum}), default ({self.default}), maximum ({self.maximum}) must be in sorted order"
            )

    def __getitem__(self, i):
        fields = dataclasses.fields(self)
        return getattr(self, fields[i].name)

    def __len__(self):
        return len(dataclasses.fields(self))

    def _replace(self, **kwargs):
        return dataclasses.replace(self, **kwargs)

    def __repr__(self):
        return (
            f"({', '.join(format(v, 'g') if v is not None else 'None' for v in self)})"
        )

    @classmethod
    def expand(
        cls,
        v: Union[
            "AxisTriple",
            float,  # pin axis at single value, same as min==default==max
            Tuple[float, float],  # (min, max), restrict axis and keep default
            Tuple[float, float, float],  # (min, default, max)
        ],
    ) -> "AxisTriple":
        """Convert a single value or a tuple into an AxisTriple.

        If the input is a single value, it is interpreted as a pin at that value.
        If the input is a tuple, it is interpreted as (min, max) or (min, default, max).
        """
        if isinstance(v, cls):
            return v
        if isinstance(v, (int, float)):
            return cls(v, v, v)
        try:
            n = len(v)
        except TypeError as e:
            raise ValueError(
                f"expected float, 2- or 3-tuple of floats; got {type(v)}: {v!r}"
            ) from e
        default = None
        if n == 2:
            minimum, maximum = v
        elif n >= 3:
            return cls(*v)
        else:
            raise ValueError(f"expected sequence of 2 or 3; got {n}: {v!r}")
        return cls(minimum, default, maximum)

    def limitRangeAndPopulateDefaults(self, fvarTriple) -> "AxisTriple":
        """Return a new AxisTriple with the default value filled in.

        Set default to fvar axis default if the latter is within the min/max range,
        otherwise set default to the min or max value, whichever is closer to the
        fvar axis default.
        If the default value is already set, return self.
        """
        minimum = self.minimum
        if minimum is None:
            minimum = fvarTriple[0]
        default = self.default
        if default is None:
            default = fvarTriple[1]
        maximum = self.maximum
        if maximum is None:
            maximum = fvarTriple[2]

        minimum = max(minimum, fvarTriple[0])
        maximum = max(maximum, fvarTriple[0])
        minimum = min(minimum, fvarTriple[2])
        maximum = min(maximum, fvarTriple[2])
        default = max(minimum, min(maximum, default))

        return AxisTriple(minimum, default, maximum)


@dataclasses.dataclass(frozen=True, order=True, repr=False)
class NormalizedAxisTriple(AxisTriple):
    """A triple of (min, default, max) normalized axis values."""

    minimum: float
    default: float
    maximum: float

    def __post_init__(self):
        if self.default is None:
            object.__setattr__(self, "default", max(self.minimum, min(self.maximum, 0)))
        if not (-1.0 <= self.minimum <= self.default <= self.maximum <= 1.0):
            raise ValueError(
                "Normalized axis values not in -1..+1 range; got "
                f"minimum={self.minimum:g}, default={self.default:g}, maximum={self.maximum:g})"
            )


@dataclasses.dataclass(frozen=True, order=True, repr=False)
class NormalizedAxisTripleAndDistances(AxisTriple):
    """A triple of (min, default, max) normalized axis values,
    with distances between min and default, and default and max,
    in the *pre-normalized* space."""

    minimum: float
    default: float
    maximum: float
    distanceNegative: Optional[float] = 1
    distancePositive: Optional[float] = 1

    def __post_init__(self):
        if self.default is None:
            object.__setattr__(self, "default", max(self.minimum, min(self.maximum, 0)))
        if not (-1.0 <= self.minimum <= self.default <= self.maximum <= 1.0):
            raise ValueError(
                "Normalized axis values not in -1..+1 range; got "
                f"minimum={self.minimum:g}, default={self.default:g}, maximum={self.maximum:g})"
            )

    def reverse_negate(self):
        v = self
        return self.__class__(-v[2], -v[1], -v[0], v[4], v[3])

    def renormalizeValue(self, v, extrapolate=True):
        """Renormalizes a normalized value v to the range of this axis,
        considering the pre-normalized distances as well as the new
        axis limits."""

        lower, default, upper, distanceNegative, distancePositive = self
        assert lower <= default <= upper

        if not extrapolate:
            v = max(lower, min(upper, v))

        if v == default:
            return 0

        if default < 0:
            return -self.reverse_negate().renormalizeValue(-v, extrapolate=extrapolate)

        # default >= 0 and v != default

        if v > default:
            return (v - default) / (upper - default)

        # v < default

        if lower >= 0:
            return (v - default) / (default - lower)

        # lower < 0 and v < default

        totalDistance = distanceNegative * -lower + distancePositive * default

        if v >= 0:
            vDistance = (default - v) * distancePositive
        else:
            vDistance = -v * distanceNegative + distancePositive * default

        return -vDistance / totalDistance


class _BaseAxisLimits(Mapping[str, AxisTriple]):
    def __getitem__(self, key: str) -> AxisTriple:
        return self._data[key]

    def __iter__(self) -> Iterable[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._data!r})"

    def __str__(self) -> str:
        return str(self._data)

    def defaultLocation(self) -> Dict[str, float]:
        """Return a dict of default axis values."""
        return {k: v.default for k, v in self.items()}

    def pinnedLocation(self) -> Dict[str, float]:
        """Return a location dict with only the pinned axes."""
        return {k: v.default for k, v in self.items() if v.minimum == v.maximum}


class AxisLimits(_BaseAxisLimits):
    """Maps axis tags (str) to AxisTriple values."""

    def __init__(self, *args, **kwargs):
        self._data = data = {}
        for k, v in dict(*args, **kwargs).items():
            if v is None:
                # will be filled in by limitAxesAndPopulateDefaults
                data[k] = v
            else:
                try:
                    triple = AxisTriple.expand(v)
                except ValueError as e:
                    raise ValueError(f"Invalid axis limits for {k!r}: {v!r}") from e
                data[k] = triple

    def limitAxesAndPopulateDefaults(self, varfont) -> "AxisLimits":
        """Return a new AxisLimits with defaults filled in from fvar table.

        If all axis limits already have defaults, return self.
        """
        fvar = varfont["fvar"]
        fvarTriples = {
            a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fvar.axes
        }
        newLimits = {}
        for axisTag, triple in self.items():
            fvarTriple = fvarTriples[axisTag]
            default = fvarTriple[1]
            if triple is None:
                newLimits[axisTag] = AxisTriple(default, default, default)
            else:
                newLimits[axisTag] = triple.limitRangeAndPopulateDefaults(fvarTriple)
        return type(self)(newLimits)

    def normalize(self, varfont, usingAvar=True) -> "NormalizedAxisLimits":
        """Return a new NormalizedAxisLimits with normalized -1..0..+1 values.

        If usingAvar is True, the avar table is used to warp the default normalization.
        """
        fvar = varfont["fvar"]
        badLimits = set(self.keys()).difference(a.axisTag for a in fvar.axes)
        if badLimits:
            raise ValueError("Cannot limit: {} not present in fvar".format(badLimits))

        axes = {
            a.axisTag: (a.minValue, a.defaultValue, a.maxValue)
            for a in fvar.axes
            if a.axisTag in self
        }

        avarSegments = {}
        if usingAvar and "avar" in varfont:
            avar = varfont["avar"]
            avarSegments = avar.segments

            if getattr(avar, "majorVersion", 1) >= 2 and avar.table.VarStore:
                pinnedAxes = set(self.pinnedLocation())
                if not pinnedAxes.issuperset(avarSegments):
                    raise NotImplementedError(
                        "Partial-instancing avar2 table is not supported"
                    )

                # TODO: Merge this with the main codepath.

                # Full instancing of avar2 font. Use avar table to normalize location and return.
                location = self.pinnedLocation()
                location = {
                    tag: normalize(value, axes[tag], avarSegments.get(tag, None))
                    for tag, value in location.items()
                }
                return NormalizedAxisLimits(
                    **avar.renormalizeLocation(location, varfont, dropZeroes=False)
                )

        normalizedLimits = {}

        for axis_tag, triple in axes.items():
            distanceNegative = triple[1] - triple[0]
            distancePositive = triple[2] - triple[1]

            if self[axis_tag] is None:
                normalizedLimits[axis_tag] = NormalizedAxisTripleAndDistances(
                    0, 0, 0, distanceNegative, distancePositive
                )
                continue

            minV, defaultV, maxV = self[axis_tag]

            if defaultV is None:
                defaultV = triple[1]

            avarMapping = avarSegments.get(axis_tag, None)
            normalizedLimits[axis_tag] = NormalizedAxisTripleAndDistances(
                *(normalize(v, triple, avarMapping) for v in (minV, defaultV, maxV)),
                distanceNegative,
                distancePositive,
            )

        return NormalizedAxisLimits(normalizedLimits)


class NormalizedAxisLimits(_BaseAxisLimits):
    """Maps axis tags (str) to NormalizedAxisTriple values."""

    def __init__(self, *args, **kwargs):
        self._data = data = {}
        for k, v in dict(*args, **kwargs).items():
            try:
                triple = NormalizedAxisTripleAndDistances.expand(v)
            except ValueError as e:
                raise ValueError(f"Invalid axis limits for {k!r}: {v!r}") from e
            data[k] = triple


class OverlapMode(IntEnum):
    KEEP_AND_DONT_SET_FLAGS = 0
    KEEP_AND_SET_FLAGS = 1
    REMOVE = 2
    REMOVE_AND_IGNORE_ERRORS = 3


def instantiateVARC(varfont, axisLimits):
    log.info("Instantiating VARC tables")

    # TODO(behdad) My confidence in this function is rather low;
    # It needs more testing. Specially with partial-instancing,
    # I don't think it currently works.

    varc = varfont["VARC"].table
    fvarAxes = varfont["fvar"].axes if "fvar" in varfont else []

    location = axisLimits.pinnedLocation()
    axisMap = [i for i, axis in enumerate(fvarAxes) if axis.axisTag not in location]
    reverseAxisMap = {i: j for j, i in enumerate(axisMap)}

    if varc.AxisIndicesList:
        axisIndicesList = varc.AxisIndicesList.Item
        for i, axisIndices in enumerate(axisIndicesList):
            if any(fvarAxes[j].axisTag in axisLimits for j in axisIndices):
                raise NotImplementedError(
                    "Instancing across VarComponent axes is not supported."
                )
            axisIndicesList[i] = [reverseAxisMap[j] for j in axisIndices]

    store = varc.MultiVarStore
    if store:
        for region in store.SparseVarRegionList.Region:
            newRegionAxis = []
            for regionRecord in region.SparseVarRegionAxis:
                tag = fvarAxes[regionRecord.AxisIndex].axisTag
                if tag in axisLimits:
                    raise NotImplementedError(
                        "Instancing across VarComponent axes is not supported."
                    )
                regionRecord.AxisIndex = reverseAxisMap[regionRecord.AxisIndex]


def instantiateTupleVariationStore(
    variations, axisLimits, origCoords=None, endPts=None
):
    """Instantiate TupleVariation list at the given location, or limit axes' min/max.

    The 'variations' list of TupleVariation objects is modified in-place.
    The 'axisLimits' (dict) maps axis tags (str) to NormalizedAxisTriple namedtuples
    specifying (minimum, default, maximum) in the -1,0,+1 normalized space. Pinned axes
    have minimum == default == maximum.

    A 'full' instance (i.e. static font) is produced when all the axes are pinned to
    single coordinates; a 'partial' instance (i.e. a less variable font) is produced
    when some of the axes are omitted, or restricted with a new range.

    Tuples that do not participate are kept as they are. Those that have 0 influence
    at the given location are removed from the variation store.
    Those that are fully instantiated (i.e. all their axes are being pinned) are also
    removed from the variation store, their scaled deltas accummulated and returned, so
    that they can be added by the caller to the default instance's coordinates.
    Tuples that are only partially instantiated (i.e. not all the axes that they
    participate in are being pinned) are kept in the store, and their deltas multiplied
    by the scalar support of the axes to be pinned at the desired location.

    Args:
        variations: List[TupleVariation] from either 'gvar' or 'cvar'.
        axisLimits: NormalizedAxisLimits: map from axis tags to (min, default, max)
            normalized coordinates for the full or partial instance.
        origCoords: GlyphCoordinates: default instance's coordinates for computing 'gvar'
            inferred points (cf. table__g_l_y_f._getCoordinatesAndControls).
        endPts: List[int]: indices of contour end points, for inferring 'gvar' deltas.

    Returns:
        List[float]: the overall delta adjustment after applicable deltas were summed.
    """

    newVariations = changeTupleVariationsAxisLimits(variations, axisLimits)

    mergedVariations = collections.OrderedDict()
    for var in newVariations:
        # compute inferred deltas only for gvar ('origCoords' is None for cvar)
        if origCoords is not None:
            var.calcInferredDeltas(origCoords, endPts)

        # merge TupleVariations with overlapping "tents"
        axes = frozenset(var.axes.items())
        if axes in mergedVariations:
            mergedVariations[axes] += var
        else:
            mergedVariations[axes] = var

    # drop TupleVariation if all axes have been pinned (var.axes.items() is empty);
    # its deltas will be added to the default instance's coordinates
    defaultVar = mergedVariations.pop(frozenset(), None)

    for var in mergedVariations.values():
        var.roundDeltas()
    variations[:] = list(mergedVariations.values())

    return defaultVar.coordinates if defaultVar is not None else []


def changeTupleVariationsAxisLimits(variations, axisLimits):
    for axisTag, axisLimit in sorted(axisLimits.items()):
        newVariations = []
        for var in variations:
            newVariations.extend(changeTupleVariationAxisLimit(var, axisTag, axisLimit))
        variations = newVariations
    return variations


def changeTupleVariationAxisLimit(var, axisTag, axisLimit):
    assert isinstance(axisLimit, NormalizedAxisTripleAndDistances)

    # Skip when current axis is missing or peaks at 0 (i.e. doesn't participate)
    lower, peak, upper = var.axes.get(axisTag, (-1, 0, 1))
    if peak == 0:
        # explicitly defined, no-op axes can be omitted
        # https://github.com/fonttools/fonttools/issues/3453
        if axisTag in var.axes:
            del var.axes[axisTag]
        return [var]
    # Drop if the var 'tent' isn't well-formed
    if not (lower <= peak <= upper) or (lower < 0 and upper > 0):
        return []

    if axisTag not in var.axes:
        return [var]

    tent = var.axes[axisTag]

    solutions = solver.rebaseTent(tent, axisLimit)

    out = []
    for scalar, tent in solutions:
        newVar = (
            TupleVariation(var.axes, var.coordinates) if len(solutions) > 1 else var
        )
        if tent is None:
            newVar.axes.pop(axisTag)
        else:
            assert tent[1] != 0, tent
            newVar.axes[axisTag] = tent
        newVar *= scalar
        out.append(newVar)

    return out


def instantiateCFF2(
    varfont,
    axisLimits,
    *,
    round=round,
    specialize=True,
    generalize=False,
    downgrade=False,
):
    # The algorithm here is rather simple:
    #
    # Take all blend operations and store their deltas in the (otherwise empty)
    # CFF2 VarStore. Then, instantiate the VarStore with the given axis limits,
    # and read back the new deltas. This is done for both the CharStrings and
    # the Private dicts.
    #
    # Then prune unused things and possibly drop the VarStore if it's empty.
    #
    # If the downgrade parameter is True, no actual downgrading is done, but
    # the function returns True if the VarStore was empty after instantiation,
    # and hence a downgrade to CFF is possible. In all other cases it returns
    # False.

    log.info("Instantiating CFF2 table")

    fvarAxes = varfont["fvar"].axes

    cff = varfont["CFF2"].cff
    topDict = cff.topDictIndex[0]
    varStore = topDict.VarStore.otVarStore
    if not varStore:
        if downgrade:
            from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF

            convertCFF2ToCFF(varfont)
        return

    cff.desubroutinize()

    def getNumRegions(vsindex):
        return varStore.VarData[vsindex if vsindex is not None else 0].VarRegionCount

    charStrings = topDict.CharStrings.values()

    # Gather all unique private dicts
    uniquePrivateDicts = set()
    privateDicts = []
    for fd in topDict.FDArray:
        if fd.Private not in uniquePrivateDicts:
            uniquePrivateDicts.add(fd.Private)
            privateDicts.append(fd.Private)

    allCommands = []
    allCommandPrivates = []
    for cs in charStrings:
        assert cs.private.vstore.otVarStore is varStore  # Or in many places!!
        commands = programToCommands(cs.program, getNumRegions=getNumRegions)
        if generalize:
            commands = generalizeCommands(commands)
        if specialize:
            commands = specializeCommands(commands, generalizeFirst=not generalize)
        allCommands.append(commands)
        allCommandPrivates.append(cs.private)

    def storeBlendsToVarStore(arg):
        if not isinstance(arg, list):
            return

        if any(isinstance(subarg, list) for subarg in arg[:-1]):
            raise NotImplementedError("Nested blend lists not supported (yet)")

        count = arg[-1]
        assert (len(arg) - 1) % count == 0
        nRegions = (len(arg) - 1) // count - 1
        assert nRegions == getNumRegions(vsindex)
        for i in range(count, len(arg) - 1, nRegions):
            deltas = arg[i : i + nRegions]
            assert len(deltas) == nRegions
            varData = varStore.VarData[vsindex]
            varData.Item.append(deltas)
            varData.ItemCount += 1

    def fetchBlendsFromVarStore(arg):
        if not isinstance(arg, list):
            return [arg]

        if any(isinstance(subarg, list) for subarg in arg[:-1]):
            raise NotImplementedError("Nested blend lists not supported (yet)")

        count = arg[-1]
        assert (len(arg) - 1) % count == 0
        numRegions = getNumRegions(vsindex)
        newDefaults = []
        newDeltas = []
        for i in range(count):
            defaultValue = arg[i]

            major = vsindex
            minor = varDataCursor[major]
            varDataCursor[major] += 1

            defaultValue += round(defaultDeltas[major][minor])
            newDefaults.append(defaultValue)

            varData = varStore.VarData[major]
            deltas = varData.Item[minor]
            assert len(deltas) == numRegions
            newDeltas.extend(deltas)

        if not numRegions:
            return newDefaults  # No deltas, just return the defaults

        return [newDefaults + newDeltas + [count]]

    # Check VarData's are empty
    for varData in varStore.VarData:
        assert varData.Item == []
        assert varData.ItemCount == 0

    # Add charstring blend lists to VarStore so we can instantiate them
    for commands, private in zip(allCommands, allCommandPrivates):
        vsindex = getattr(private, "vsindex", 0)
        for command in commands:
            if command[0] == "vsindex":
                vsindex = command[1][0]
                continue
            for arg in command[1]:
                storeBlendsToVarStore(arg)

    # Add private blend lists to VarStore so we can instantiate values
    for opcode, name, arg_type, default, converter in privateDictOperators2:
        if arg_type not in ("number", "delta", "array"):
            continue

        vsindex = 0
        for private in privateDicts:
            if not hasattr(private, name):
                continue
            values = getattr(private, name)

            # This is safe here since "vsindex" is the first in the privateDictOperators2
            if name == "vsindex":
                vsindex = values[0]
                continue

            if arg_type == "number":
                values = [values]

            for value in values:
                if not isinstance(value, list):
                    continue

                assert len(value) % (getNumRegions(vsindex) + 1) == 0
                count = len(value) // (getNumRegions(vsindex) + 1)
                storeBlendsToVarStore(value + [count])

    # Instantiate VarStore
    defaultDeltas = instantiateItemVariationStore(
        varStore, fvarAxes, axisLimits, hierarchical=True
    )

    # Read back new charstring blends from the instantiated VarStore
    varDataCursor = [0] * len(varStore.VarData)
    for commands, private in zip(allCommands, allCommandPrivates):
        vsindex = getattr(private, "vsindex", 0)
        for command in commands:
            if command[0] == "vsindex":
                vsindex = command[1][0]
                continue
            newArgs = []
            for arg in command[1]:
                newArgs.extend(fetchBlendsFromVarStore(arg))
            command[1][:] = newArgs

    # Read back new private blends from the instantiated VarStore
    for opcode, name, arg_type, default, converter in privateDictOperators2:
        if arg_type not in ("number", "delta", "array"):
            continue

        vsindex = 0
        for private in privateDicts:
            if not hasattr(private, name):
                continue

            # This is safe here since "vsindex" is the first in the privateDictOperators2
            if name == "vsindex":
                vsindex = values[0]
                continue

            values = getattr(private, name)
            if arg_type == "number":
                values = [values]

            newValues = []
            for value in values:
                if not isinstance(value, list):
                    newValues.append(value)
                    continue

                value.append(1)
                value = fetchBlendsFromVarStore(value)
                newValues.extend(v[:-1] if isinstance(v, list) else v for v in value)

            if arg_type == "number":
                newValues = newValues[0]

            setattr(private, name, newValues)

    # Empty out the VarStore
    for i, varData in enumerate(varStore.VarData):
        assert varDataCursor[i] == varData.ItemCount, (
            varDataCursor[i],
            varData.ItemCount,
        )
        varData.Item = []
        varData.ItemCount = 0

    # Collect surviving vsindexes
    usedVsindex = set(
        i for i in range(len(varStore.VarData)) if varStore.VarData[i].VarRegionCount
    )
    # Remove vsindex commands that are no longer needed
    for commands, private in zip(allCommands, allCommandPrivates):
        if not any(isinstance(arg, list) for command in commands for arg in command[1]):
            commands[:] = [command for command in commands if command[0] != "vsindex"]

    # Remove unused VarData and update vsindex values
    vsindexMapping = {v: i for i, v in enumerate(sorted(usedVsindex))}
    varStore.VarData = [
        varData for i, varData in enumerate(varStore.VarData) if i in usedVsindex
    ]
    varStore.VarDataCount = len(varStore.VarData)
    for commands in allCommands:
        for command in commands:
            if command[0] == "vsindex":
                command[1][0] = vsindexMapping[command[1][0]]
    for private in privateDicts:
        if hasattr(private, "vsindex"):
            private.vsindex = vsindexMapping[private.vsindex]

    # Remove initial vsindex commands that are implied
    for commands, private in zip(allCommands, allCommandPrivates):
        vsindex = getattr(private, "vsindex", 0)
        if commands and commands[0] == ("vsindex", [vsindex]):
            commands.pop(0)

    # Ship the charstrings!
    for cs, commands in zip(charStrings, allCommands):
        cs.program = commandsToProgram(commands)

    # Remove empty VarStore
    if not varStore.VarData:
        if "VarStore" in topDict.rawDict:
            del topDict.rawDict["VarStore"]
        del topDict.VarStore
        del topDict.CharStrings.varStore
        for private in privateDicts:
            del private.vstore

        if downgrade:
            return True

    return False


def _instantiateGvarGlyph(
    glyphname, glyf, gvar, hMetrics, vMetrics, axisLimits, optimize=True
):
    coordinates, ctrl = glyf._getCoordinatesAndControls(glyphname, hMetrics, vMetrics)
    endPts = ctrl.endPts

    # Not every glyph may have variations
    tupleVarStore = gvar.variations.get(glyphname)

    if tupleVarStore:
        defaultDeltas = instantiateTupleVariationStore(
            tupleVarStore, axisLimits, coordinates, endPts
        )

        if defaultDeltas:
            coordinates += _g_l_y_f.GlyphCoordinates(defaultDeltas)

    # _setCoordinates also sets the hmtx/vmtx advance widths and sidebearings from
    # the four phantom points and glyph bounding boxes.
    # We call it unconditionally even if a glyph has no variations or no deltas are
    # applied at this location, in case the glyph's xMin and in turn its sidebearing
    # have changed. E.g. a composite glyph has no deltas for the component's (x, y)
    # offset nor for the 4 phantom points (e.g. it's monospaced). Thus its entry in
    # gvar table is empty; however, the composite's base glyph may have deltas
    # applied, hence the composite's bbox and left/top sidebearings may need updating
    # in the instanced font.
    glyf._setCoordinates(glyphname, coordinates, hMetrics, vMetrics)

    if not tupleVarStore:
        if glyphname in gvar.variations:
            del gvar.variations[glyphname]
        return

    if optimize:
        # IUP semantics depend on point equality, and so round prior to
        # optimization to ensure that comparisons that happen now will be the
        # same as those that happen at render time. This is especially needed
        # when floating point deltas have been applied to the default position.
        #     See https://github.com/fonttools/fonttools/issues/3634
        # Rounding must happen only after calculating glyf metrics above, to
        # preserve backwards compatibility.
        #     See 0010a3cd9aa25f84a3a6250dafb119743d32aa40
        coordinates.toInt()

        isComposite = glyf[glyphname].isComposite()

        for var in tupleVarStore:
            var.optimize(coordinates, endPts, isComposite=isComposite)


def instantiateGvarGlyph(varfont, glyphname, axisLimits, optimize=True):
    """Remove?
    https://github.com/fonttools/fonttools/pull/2266"""
    gvar = varfont["gvar"]
    glyf = varfont["glyf"]
    hMetrics = varfont["hmtx"].metrics
    vMetrics = getattr(varfont.get("vmtx"), "metrics", None)
    _instantiateGvarGlyph(
        glyphname, glyf, gvar, hMetrics, vMetrics, axisLimits, optimize=optimize
    )


def instantiateGvar(varfont, axisLimits, optimize=True):
    log.info("Instantiating glyf/gvar tables")

    gvar = varfont["gvar"]
    glyf = varfont["glyf"]
    hMetrics = varfont["hmtx"].metrics
    vMetrics = getattr(varfont.get("vmtx"), "metrics", None)
    # Get list of glyph names sorted by component depth.
    # If a composite glyph is processed before its base glyph, the bounds may
    # be calculated incorrectly because deltas haven't been applied to the
    # base glyph yet.
    glyphnames = sorted(
        glyf.glyphOrder,
        key=lambda name: (
            (
                glyf[name].getCompositeMaxpValues(glyf).maxComponentDepth
                if glyf[name].isComposite()
                else 0
            ),
            name,
        ),
    )
    for glyphname in glyphnames:
        _instantiateGvarGlyph(
            glyphname, glyf, gvar, hMetrics, vMetrics, axisLimits, optimize=optimize
        )

    if not gvar.variations:
        del varfont["gvar"]


def setCvarDeltas(cvt, deltas):
    for i, delta in enumerate(deltas):
        if delta:
            cvt[i] += otRound(delta)


def instantiateCvar(varfont, axisLimits):
    log.info("Instantiating cvt/cvar tables")

    cvar = varfont["cvar"]

    defaultDeltas = instantiateTupleVariationStore(cvar.variations, axisLimits)

    if defaultDeltas:
        setCvarDeltas(varfont["cvt "], defaultDeltas)

    if not cvar.variations:
        del varfont["cvar"]


def setMvarDeltas(varfont, deltas):
    mvar = varfont["MVAR"].table
    records = mvar.ValueRecord
    for rec in records:
        mvarTag = rec.ValueTag
        if mvarTag not in MVAR_ENTRIES:
            continue
        tableTag, itemName = MVAR_ENTRIES[mvarTag]
        delta = deltas[rec.VarIdx]
        if delta != 0:
            setattr(
                varfont[tableTag],
                itemName,
                getattr(varfont[tableTag], itemName) + otRound(delta),
            )


@contextmanager
def verticalMetricsKeptInSync(varfont):
    """Ensure hhea vertical metrics stay in sync with OS/2 ones after instancing.

    When applying MVAR deltas to the OS/2 table, if the ascender, descender and
    line gap change but they were the same as the respective hhea metrics in the
    original font, this context manager ensures that hhea metrcs also get updated
    accordingly.
    The MVAR spec only has tags for the OS/2 metrics, but it is common in fonts
    to have the hhea metrics be equal to those for compat reasons.

    https://learn.microsoft.com/en-us/typography/opentype/spec/mvar
    https://googlefonts.github.io/gf-guide/metrics.html#7-hhea-and-typo-metrics-should-be-equal
    https://github.com/fonttools/fonttools/issues/3297
    """
    current_os2_vmetrics = [
        getattr(varfont["OS/2"], attr)
        for attr in ("sTypoAscender", "sTypoDescender", "sTypoLineGap")
    ]
    metrics_are_synced = current_os2_vmetrics == [
        getattr(varfont["hhea"], attr) for attr in ("ascender", "descender", "lineGap")
    ]

    yield metrics_are_synced

    if metrics_are_synced:
        new_os2_vmetrics = [
            getattr(varfont["OS/2"], attr)
            for attr in ("sTypoAscender", "sTypoDescender", "sTypoLineGap")
        ]
        if current_os2_vmetrics != new_os2_vmetrics:
            for attr, value in zip(
                ("ascender", "descender", "lineGap"), new_os2_vmetrics
            ):
                setattr(varfont["hhea"], attr, value)


def instantiateMVAR(varfont, axisLimits):
    log.info("Instantiating MVAR table")

    mvar = varfont["MVAR"].table
    fvarAxes = varfont["fvar"].axes
    varStore = mvar.VarStore
    defaultDeltas = instantiateItemVariationStore(varStore, fvarAxes, axisLimits)

    with verticalMetricsKeptInSync(varfont):
        setMvarDeltas(varfont, defaultDeltas)

    if varStore.VarRegionList.Region:
        varIndexMapping = varStore.optimize()
        for rec in mvar.ValueRecord:
            rec.VarIdx = varIndexMapping[rec.VarIdx]
    else:
        del varfont["MVAR"]


def _remapVarIdxMap(table, attrName, varIndexMapping, glyphOrder):
    oldMapping = getattr(table, attrName).mapping
    newMapping = [varIndexMapping[oldMapping[glyphName]] for glyphName in glyphOrder]
    setattr(table, attrName, builder.buildVarIdxMap(newMapping, glyphOrder))


# TODO(anthrotype) Add support for HVAR/VVAR in CFF2
def _instantiateVHVAR(varfont, axisLimits, tableFields, *, round=round):
    location = axisLimits.pinnedLocation()
    tableTag = tableFields.tableTag
    fvarAxes = varfont["fvar"].axes

    log.info("Instantiating %s table", tableTag)
    vhvar = varfont[tableTag].table
    varStore = vhvar.VarStore

    if "glyf" in varfont:
        # Deltas from gvar table have already been applied to the hmtx/vmtx. For full
        # instances (i.e. all axes pinned), we can simply drop HVAR/VVAR and return
        if set(location).issuperset(axis.axisTag for axis in fvarAxes):
            log.info("Dropping %s table", tableTag)
            del varfont[tableTag]
            return

    defaultDeltas = instantiateItemVariationStore(varStore, fvarAxes, axisLimits)

    if "glyf" not in varfont:
        # CFF2 fonts need hmtx/vmtx updated here. For glyf fonts, the instantiateGvar
        # function already updated the hmtx/vmtx from phantom points. Maybe remove
        # that and do it here for both CFF2 and glyf fonts?
        #
        # Specially, if a font has glyf but not gvar, the hmtx/vmtx will not have been
        # updated by instantiateGvar. Though one can call that a faulty font.
        metricsTag = "vmtx" if tableTag == "VVAR" else "hmtx"
        if metricsTag in varfont:
            advMapping = getattr(vhvar, tableFields.advMapping)
            metricsTable = varfont[metricsTag]
            metrics = metricsTable.metrics
            for glyphName, (advanceWidth, sb) in metrics.items():
                if advMapping:
                    varIdx = advMapping.mapping[glyphName]
                else:
                    varIdx = varfont.getGlyphID(glyphName)
                delta = round(defaultDeltas[varIdx])
                metrics[glyphName] = (max(0, advanceWidth + delta), sb)

            if (
                tableTag == "VVAR"
                and getattr(vhvar, tableFields.vOrigMapping) is not None
            ):
                log.warning(
                    "VORG table not yet updated to reflect changes in VVAR table"
                )

            # For full instances (i.e. all axes pinned), we can simply drop HVAR/VVAR and return
            if set(location).issuperset(axis.axisTag for axis in fvarAxes):
                log.info("Dropping %s table", tableTag)
                del varfont[tableTag]
                return

    if varStore.VarRegionList.Region:
        # Only re-optimize VarStore if the HVAR/VVAR already uses indirect AdvWidthMap
        # or AdvHeightMap. If a direct, implicit glyphID->VariationIndex mapping is
        # used for advances, skip re-optimizing and maintain original VariationIndex.
        if getattr(vhvar, tableFields.advMapping):
            varIndexMapping = varStore.optimize(use_NO_VARIATION_INDEX=False)
            glyphOrder = varfont.getGlyphOrder()
            _remapVarIdxMap(vhvar, tableFields.advMapping, varIndexMapping, glyphOrder)
            if getattr(vhvar, tableFields.sb1):  # left or top sidebearings
                _remapVarIdxMap(vhvar, tableFields.sb1, varIndexMapping, glyphOrder)
            if getattr(vhvar, tableFields.sb2):  # right or bottom sidebearings
                _remapVarIdxMap(vhvar, tableFields.sb2, varIndexMapping, glyphOrder)
            if tableTag == "VVAR" and getattr(vhvar, tableFields.vOrigMapping):
                _remapVarIdxMap(
                    vhvar, tableFields.vOrigMapping, varIndexMapping, glyphOrder
                )


def instantiateHVAR(varfont, axisLimits):
    return _instantiateVHVAR(varfont, axisLimits, varLib.HVAR_FIELDS)


def instantiateVVAR(varfont, axisLimits):
    return _instantiateVHVAR(varfont, axisLimits, varLib.VVAR_FIELDS)


class _TupleVarStoreAdapter(object):
    def __init__(self, regions, axisOrder, tupleVarData, itemCounts):
        self.regions = regions
        self.axisOrder = axisOrder
        self.tupleVarData = tupleVarData
        self.itemCounts = itemCounts

    @classmethod
    def fromItemVarStore(cls, itemVarStore, fvarAxes):
        axisOrder = [axis.axisTag for axis in fvarAxes]
        regions = [
            region.get_support(fvarAxes) for region in itemVarStore.VarRegionList.Region
        ]
        tupleVarData = []
        itemCounts = []
        for varData in itemVarStore.VarData:
            variations = []
            varDataRegions = (regions[i] for i in varData.VarRegionIndex)
            for axes, coordinates in zip(varDataRegions, zip(*varData.Item)):
                variations.append(TupleVariation(axes, list(coordinates)))
            tupleVarData.append(variations)
            itemCounts.append(varData.ItemCount)
        return cls(regions, axisOrder, tupleVarData, itemCounts)

    def rebuildRegions(self):
        # Collect the set of all unique region axes from the current TupleVariations.
        # We use an OrderedDict to de-duplicate regions while keeping the order.
        uniqueRegions = collections.OrderedDict.fromkeys(
            (
                frozenset(var.axes.items())
                for variations in self.tupleVarData
                for var in variations
            )
        )
        # Maintain the original order for the regions that pre-existed, appending
        # the new regions at the end of the region list.
        newRegions = []
        for region in self.regions:
            regionAxes = frozenset(region.items())
            if regionAxes in uniqueRegions:
                newRegions.append(region)
                del uniqueRegions[regionAxes]
        if uniqueRegions:
            newRegions.extend(dict(region) for region in uniqueRegions)
        self.regions = newRegions

    def instantiate(self, axisLimits):
        defaultDeltaArray = []
        for variations, itemCount in zip(self.tupleVarData, self.itemCounts):
            defaultDeltas = instantiateTupleVariationStore(variations, axisLimits)
            if not defaultDeltas:
                defaultDeltas = [0] * itemCount
            defaultDeltaArray.append(defaultDeltas)

        # rebuild regions whose axes were dropped or limited
        self.rebuildRegions()

        pinnedAxes = set(axisLimits.pinnedLocation())
        self.axisOrder = [
            axisTag for axisTag in self.axisOrder if axisTag not in pinnedAxes
        ]

        return defaultDeltaArray

    def asItemVarStore(self):
        regionOrder = [frozenset(axes.items()) for axes in self.regions]
        varDatas = []
        for variations, itemCount in zip(self.tupleVarData, self.itemCounts):
            if variations:
                assert len(variations[0].coordinates) == itemCount
                varRegionIndices = [
                    regionOrder.index(frozenset(var.axes.items())) for var in variations
                ]
                varDataItems = list(zip(*(var.coordinates for var in variations)))
                varDatas.append(
                    builder.buildVarData(varRegionIndices, varDataItems, optimize=False)
                )
            else:
                varDatas.append(
                    builder.buildVarData([], [[] for _ in range(itemCount)])
                )
        regionList = builder.buildVarRegionList(self.regions, self.axisOrder)
        itemVarStore = builder.buildVarStore(regionList, varDatas)
        # remove unused regions from VarRegionList
        itemVarStore.prune_regions()
        return itemVarStore


def instantiateItemVariationStore(
    itemVarStore, fvarAxes, axisLimits, hierarchical=False
):
    """Compute deltas at partial location, and update varStore in-place.

    Remove regions in which all axes were instanced, or fall outside the new axis
    limits. Scale the deltas of the remaining regions where only some of the axes
    were instanced.

    The number of VarData subtables, and the number of items within each, are
    not modified, in order to keep the existing VariationIndex valid.
    One may call VarStore.optimize() method after this to further optimize those.

    Args:
        varStore: An otTables.VarStore object (Item Variation Store)
        fvarAxes: list of fvar's Axis objects
        axisLimits: NormalizedAxisLimits: mapping axis tags to normalized
            min/default/max axis coordinates. May not specify coordinates/ranges for
            all the fvar axes.

    Returns:
        defaultDeltas: to be added to the default instance, of type dict of floats
            keyed by VariationIndex compound values: i.e. (outer << 16) + inner.
    """
    tupleVarStore = _TupleVarStoreAdapter.fromItemVarStore(itemVarStore, fvarAxes)
    defaultDeltaArray = tupleVarStore.instantiate(axisLimits)
    newItemVarStore = tupleVarStore.asItemVarStore()

    itemVarStore.VarRegionList = newItemVarStore.VarRegionList
    if not hasattr(itemVarStore, "VarDataCount"):  # Happens fromXML
        itemVarStore.VarDataCount = len(newItemVarStore.VarData)
    assert itemVarStore.VarDataCount == newItemVarStore.VarDataCount
    itemVarStore.VarData = newItemVarStore.VarData

    if not hierarchical:
        defaultDeltas = {
            ((major << 16) + minor): delta
            for major, deltas in enumerate(defaultDeltaArray)
            for minor, delta in enumerate(deltas)
        }
        defaultDeltas[itemVarStore.NO_VARIATION_INDEX] = 0
    else:
        defaultDeltas = {0xFFFF: {0xFFFF: 0}}  # NO_VARIATION_INDEX
        for major, deltas in enumerate(defaultDeltaArray):
            defaultDeltasForMajor = defaultDeltas.setdefault(major, {})
            for minor, delta in enumerate(deltas):
                defaultDeltasForMajor[minor] = delta
    return defaultDeltas


def instantiateOTL(varfont, axisLimits):
    # TODO(anthrotype) Support partial instancing of JSTF and BASE tables

    if (
        "GDEF" not in varfont
        or varfont["GDEF"].table.Version < 0x00010003
        or not varfont["GDEF"].table.VarStore
    ):
        return

    if "GPOS" in varfont:
        msg = "Instantiating GDEF and GPOS tables"
    else:
        msg = "Instantiating GDEF table"
    log.info(msg)

    gdef = varfont["GDEF"].table
    varStore = gdef.VarStore
    fvarAxes = varfont["fvar"].axes

    defaultDeltas = instantiateItemVariationStore(varStore, fvarAxes, axisLimits)

    # When VF are built, big lookups may overflow and be broken into multiple
    # subtables. MutatorMerger (which inherits from AligningMerger) reattaches
    # them upon instancing, in case they can now fit a single subtable (if not,
    # they will be split again upon compilation).
    # This 'merger' also works as a 'visitor' that traverses the OTL tables and
    # calls specific methods when instances of a given type are found.
    # Specifically, it adds default deltas to GPOS Anchors/ValueRecords and GDEF
    # LigatureCarets, and optionally deletes all VariationIndex tables if the
    # VarStore is fully instanced.
    merger = MutatorMerger(
        varfont, defaultDeltas, deleteVariations=(not varStore.VarRegionList.Region)
    )
    merger.mergeTables(varfont, [varfont], ["GDEF", "GPOS"])

    if varStore.VarRegionList.Region:
        varIndexMapping = varStore.optimize()
        gdef.remap_device_varidxes(varIndexMapping)
        if "GPOS" in varfont:
            varfont["GPOS"].table.remap_device_varidxes(varIndexMapping)
    else:
        # Downgrade GDEF.
        del gdef.VarStore
        gdef.Version = 0x00010002
        if gdef.MarkGlyphSetsDef is None:
            del gdef.MarkGlyphSetsDef
            gdef.Version = 0x00010000

        if not (
            gdef.LigCaretList
            or gdef.MarkAttachClassDef
            or gdef.GlyphClassDef
            or gdef.AttachList
            or (gdef.Version >= 0x00010002 and gdef.MarkGlyphSetsDef)
        ):
            del varfont["GDEF"]


def _isValidAvarSegmentMap(axisTag, segmentMap):
    if not segmentMap:
        return True
    if not {(-1.0, -1.0), (0, 0), (1.0, 1.0)}.issubset(segmentMap.items()):
        log.warning(
            f"Invalid avar SegmentMap record for axis '{axisTag}': does not "
            "include all required value maps {-1.0: -1.0, 0: 0, 1.0: 1.0}"
        )
        return False
    previousValue = None
    for fromCoord, toCoord in sorted(segmentMap.items()):
        if previousValue is not None and previousValue > toCoord:
            log.warning(
                f"Invalid avar AxisValueMap({fromCoord}, {toCoord}) record "
                f"for axis '{axisTag}': the toCoordinate value must be >= to "
                f"the toCoordinate value of the preceding record ({previousValue})."
            )
            return False
        previousValue = toCoord
    return True


def downgradeCFF2ToCFF(varfont):
    # Save these properties
    recalcTimestamp = varfont.recalcTimestamp
    recalcBBoxes = varfont.recalcBBoxes

    # Disable them
    varfont.recalcTimestamp = False
    varfont.recalcBBoxes = False

    # Save to memory, reload, downgrade and save again, reload.
    # We do this dance because the convertCFF2ToCFF changes glyph
    # names, so following save would fail if any other table was
    # loaded and referencing glyph names.
    #
    # The second save+load is unfortunate but also necessary.

    stream = io.BytesIO()
    log.info("Saving CFF2 font to memory for downgrade")
    varfont.save(stream)
    stream.seek(0)
    varfont = TTFont(stream, recalcTimestamp=False, recalcBBoxes=False)

    convertCFF2ToCFF(varfont)

    stream = io.BytesIO()
    log.info("Saving downgraded CFF font to memory")
    varfont.save(stream)
    stream.seek(0)
    varfont = TTFont(stream, recalcTimestamp=False, recalcBBoxes=False)

    # Uncomment, to see test all tables can be loaded. This fails without
    # the extra save+load above.
    """
    for tag in varfont.keys():
        print("Loading", tag)
        varfont[tag]
    """

    # Restore them
    varfont.recalcTimestamp = recalcTimestamp
    varfont.recalcBBoxes = recalcBBoxes

    return varfont


def instantiateAvar(varfont, axisLimits):
    # 'axisLimits' dict must contain user-space (non-normalized) coordinates.

    avar = varfont["avar"]

    segments = avar.segments

    # drop table if we instantiate all the axes
    pinnedAxes = set(axisLimits.pinnedLocation())
    if pinnedAxes.issuperset(segments):
        log.info("Dropping avar table")
        del varfont["avar"]
        return

    if getattr(avar, "majorVersion", 1) >= 2 and avar.table.VarStore:
        raise NotImplementedError("avar table with VarStore is not supported")

    log.info("Instantiating avar table")
    for axis in pinnedAxes:
        if axis in segments:
            del segments[axis]

    # First compute the default normalization for axisLimits coordinates: i.e.
    # min = -1.0, default = 0, max = +1.0, and in between values interpolated linearly,
    # without using the avar table's mappings.
    # Then, for each SegmentMap, if we are restricting its axis, compute the new
    # mappings by dividing the key/value pairs by the desired new min/max values,
    # dropping any mappings that fall outside the restricted range.
    # The keys ('fromCoord') are specified in default normalized coordinate space,
    # whereas the values ('toCoord') are "mapped forward" using the SegmentMap.
    normalizedRanges = axisLimits.normalize(varfont, usingAvar=False)
    newSegments = {}
    for axisTag, mapping in segments.items():
        if not _isValidAvarSegmentMap(axisTag, mapping):
            continue
        if mapping and axisTag in normalizedRanges:
            axisRange = normalizedRanges[axisTag]
            mappedMin = floatToFixedToFloat(
                piecewiseLinearMap(axisRange.minimum, mapping), 14
            )
            mappedDef = floatToFixedToFloat(
                piecewiseLinearMap(axisRange.default, mapping), 14
            )
            mappedMax = floatToFixedToFloat(
                piecewiseLinearMap(axisRange.maximum, mapping), 14
            )
            mappedAxisLimit = NormalizedAxisTripleAndDistances(
                mappedMin,
                mappedDef,
                mappedMax,
                axisRange.distanceNegative,
                axisRange.distancePositive,
            )
            newMapping = {}
            for fromCoord, toCoord in mapping.items():
                if fromCoord < axisRange.minimum or fromCoord > axisRange.maximum:
                    continue
                fromCoord = axisRange.renormalizeValue(fromCoord)

                assert mappedMin <= toCoord <= mappedMax
                toCoord = mappedAxisLimit.renormalizeValue(toCoord)

                fromCoord = floatToFixedToFloat(fromCoord, 14)
                toCoord = floatToFixedToFloat(toCoord, 14)
                newMapping[fromCoord] = toCoord
            newMapping.update({-1.0: -1.0, 0.0: 0.0, 1.0: 1.0})
            newSegments[axisTag] = newMapping
        else:
            newSegments[axisTag] = mapping
    avar.segments = newSegments


def isInstanceWithinAxisRanges(location, axisRanges):
    for axisTag, coord in location.items():
        if axisTag in axisRanges:
            axisRange = axisRanges[axisTag]
            if coord < axisRange.minimum or coord > axisRange.maximum:
                return False
    return True


def instantiateFvar(varfont, axisLimits):
    # 'axisLimits' dict must contain user-space (non-normalized) coordinates

    location = axisLimits.pinnedLocation()

    fvar = varfont["fvar"]

    # drop table if we instantiate all the axes
    if set(location).issuperset(axis.axisTag for axis in fvar.axes):
        log.info("Dropping fvar table")
        del varfont["fvar"]
        return

    log.info("Instantiating fvar table")

    axes = []
    for axis in fvar.axes:
        axisTag = axis.axisTag
        if axisTag in location:
            continue
        if axisTag in axisLimits:
            triple = axisLimits[axisTag]
            if triple.default is None:
                triple = (triple.minimum, axis.defaultValue, triple.maximum)
            axis.minValue, axis.defaultValue, axis.maxValue = triple
        axes.append(axis)
    fvar.axes = axes

    # only keep NamedInstances whose coordinates == pinned axis location
    instances = []
    for instance in fvar.instances:
        if any(instance.coordinates[axis] != value for axis, value in location.items()):
            continue
        for axisTag in location:
            del instance.coordinates[axisTag]
        if not isInstanceWithinAxisRanges(instance.coordinates, axisLimits):
            continue
        instances.append(instance)
    fvar.instances = instances


def instantiateSTAT(varfont, axisLimits):
    # 'axisLimits' dict must contain user-space (non-normalized) coordinates

    stat = varfont["STAT"].table
    if not stat.DesignAxisRecord or not (
        stat.AxisValueArray and stat.AxisValueArray.AxisValue
    ):
        return  # STAT table empty, nothing to do

    log.info("Instantiating STAT table")
    newAxisValueTables = axisValuesFromAxisLimits(stat, axisLimits)
    stat.AxisValueCount = len(newAxisValueTables)
    if stat.AxisValueCount:
        stat.AxisValueArray.AxisValue = newAxisValueTables
    else:
        stat.AxisValueArray = None


def axisValuesFromAxisLimits(stat, axisLimits):
    def isAxisValueOutsideLimits(axisTag, axisValue):
        if axisTag in axisLimits:
            triple = axisLimits[axisTag]
            if axisValue < triple.minimum or axisValue > triple.maximum:
                return True
        return False

    # only keep AxisValues whose axis is not pinned nor restricted, or is pinned at the
    # exact (nominal) value, or is restricted but the value is within the new range
    designAxes = stat.DesignAxisRecord.Axis
    newAxisValueTables = []
    for axisValueTable in stat.AxisValueArray.AxisValue:
        axisValueFormat = axisValueTable.Format
        if axisValueFormat in (1, 2, 3):
            axisTag = designAxes[axisValueTable.AxisIndex].AxisTag
            if axisValueFormat == 2:
                axisValue = axisValueTable.NominalValue
            else:
                axisValue = axisValueTable.Value
            if isAxisValueOutsideLimits(axisTag, axisValue):
                continue
        elif axisValueFormat == 4:
            # drop 'non-analytic' AxisValue if _any_ AxisValueRecord doesn't match
            # the pinned location or is outside range
            dropAxisValueTable = False
            for rec in axisValueTable.AxisValueRecord:
                axisTag = designAxes[rec.AxisIndex].AxisTag
                axisValue = rec.Value
                if isAxisValueOutsideLimits(axisTag, axisValue):
                    dropAxisValueTable = True
                    break
            if dropAxisValueTable:
                continue
        else:
            log.warning("Unknown AxisValue table format (%s); ignored", axisValueFormat)
        newAxisValueTables.append(axisValueTable)
    return newAxisValueTables


def setMacOverlapFlags(glyfTable):
    flagOverlapCompound = _g_l_y_f.OVERLAP_COMPOUND
    flagOverlapSimple = _g_l_y_f.flagOverlapSimple
    for glyphName in glyfTable.keys():
        glyph = glyfTable[glyphName]
        # Set OVERLAP_COMPOUND bit for compound glyphs
        if glyph.isComposite():
            glyph.components[0].flags |= flagOverlapCompound
        # Set OVERLAP_SIMPLE bit for simple glyphs
        elif glyph.numberOfContours > 0:
            glyph.flags[0] |= flagOverlapSimple


def normalize(value, triple, avarMapping):
    value = normalizeValue(value, triple)
    if avarMapping:
        value = piecewiseLinearMap(value, avarMapping)
    # Quantize to F2Dot14, to avoid surprise interpolations.
    return floatToFixedToFloat(value, 14)


def sanityCheckVariableTables(varfont):
    if "fvar" not in varfont:
        raise ValueError("Missing required table fvar")
    if "gvar" in varfont:
        if "glyf" not in varfont:
            raise ValueError("Can't have gvar without glyf")


def instantiateVariableFont(
    varfont,
    axisLimits,
    inplace=False,
    optimize=True,
    overlap=OverlapMode.KEEP_AND_SET_FLAGS,
    updateFontNames=False,
    *,
    downgradeCFF2=False,
    static=False,
):
    """Instantiate variable font, either fully or partially.

    Depending on whether the `axisLimits` dictionary references all or some of the
    input varfont's axes, the output font will either be a full instance (static
    font) or a variable font with possibly less variation data.

    Args:
        varfont: a TTFont instance, which must contain at least an 'fvar' table.
        axisLimits: a dict keyed by axis tags (str) containing the coordinates (float)
            along one or more axes where the desired instance will be located.
            If the value is `None`, the default coordinate as per 'fvar' table for
            that axis is used.
            The limit values can also be (min, max) tuples for restricting an
            axis's variation range. The default axis value must be included in
            the new range.
        inplace (bool): whether to modify input TTFont object in-place instead of
            returning a distinct object.
        optimize (bool): if False, do not perform IUP-delta optimization on the
            remaining 'gvar' table's deltas. Possibly faster, and might work around
            rendering issues in some buggy environments, at the cost of a slightly
            larger file size.
        overlap (OverlapMode): variable fonts usually contain overlapping contours, and
            some font rendering engines on Apple platforms require that the
            `OVERLAP_SIMPLE` and `OVERLAP_COMPOUND` flags in the 'glyf' table be set to
            force rendering using a non-zero fill rule. Thus we always set these flags
            on all glyphs to maximise cross-compatibility of the generated instance.
            You can disable this by passing OverlapMode.KEEP_AND_DONT_SET_FLAGS.
            If you want to remove the overlaps altogether and merge overlapping
            contours and components, you can pass OverlapMode.REMOVE (or
            REMOVE_AND_IGNORE_ERRORS to not hard-fail on tricky glyphs). Note that this
            requires the skia-pathops package (available to pip install).
            The overlap parameter only has effect when generating full static instances.
        updateFontNames (bool): if True, update the instantiated font's name table using
            the Axis Value Tables from the STAT table. The name table and the style bits
            in the head and OS/2 table will be updated so they conform to the R/I/B/BI
            model. If the STAT table is missing or an Axis Value table is missing for
            a given axis coordinate, a ValueError will be raised.
        downgradeCFF2 (bool): if True, downgrade the CFF2 table to CFF table when possible
            ie. full instancing of all axes. This is useful for compatibility with older
            software that does not support CFF2. Defaults to False. Note that this
            operation also removes overlaps within glyph shapes, as CFF does not support
            overlaps but CFF2 does.
        static (bool): if True, generate a full instance (static font) instead of a partial
            instance (variable font).
    """
    # 'overlap' used to be bool and is now enum; for backward compat keep accepting bool
    overlap = OverlapMode(int(overlap))

    sanityCheckVariableTables(varfont)

    if static:
        unspecified = []
        for axis in varfont["fvar"].axes:
            if axis.axisTag not in axisLimits:
                axisLimits[axis.axisTag] = None
                unspecified.append(axis.axisTag)
        if unspecified:
            log.info("Pinning unspecified axes to default: %s", unspecified)

    axisLimits = AxisLimits(axisLimits).limitAxesAndPopulateDefaults(varfont)

    log.info("Restricted limits: %s", axisLimits)

    normalizedLimits = axisLimits.normalize(varfont)

    log.info("Normalized limits: %s", normalizedLimits)

    if not inplace:
        varfont = deepcopy(varfont)

    if "DSIG" in varfont:
        del varfont["DSIG"]

    if updateFontNames:
        log.info("Updating name table")
        names.updateNameTable(varfont, axisLimits)

    if "VARC" in varfont:
        instantiateVARC(varfont, normalizedLimits)

    if "CFF2" in varfont:
        downgradeCFF2 = instantiateCFF2(
            varfont, normalizedLimits, downgrade=downgradeCFF2
        )

    if "gvar" in varfont:
        instantiateGvar(varfont, normalizedLimits, optimize=optimize)

    if "cvar" in varfont:
        instantiateCvar(varfont, normalizedLimits)

    if "MVAR" in varfont:
        instantiateMVAR(varfont, normalizedLimits)

    if "HVAR" in varfont:
        instantiateHVAR(varfont, normalizedLimits)

    if "VVAR" in varfont:
        instantiateVVAR(varfont, normalizedLimits)

    instantiateOTL(varfont, normalizedLimits)

    instantiateFeatureVariations(varfont, normalizedLimits)

    if "avar" in varfont:
        instantiateAvar(varfont, axisLimits)

    with names.pruningUnusedNames(varfont):
        if "STAT" in varfont:
            instantiateSTAT(varfont, axisLimits)

        instantiateFvar(varfont, axisLimits)

    if "fvar" not in varfont:
        if "glyf" in varfont:
            if overlap == OverlapMode.KEEP_AND_SET_FLAGS:
                setMacOverlapFlags(varfont["glyf"])
            elif overlap in (OverlapMode.REMOVE, OverlapMode.REMOVE_AND_IGNORE_ERRORS):
                from fontTools.ttLib.removeOverlaps import removeOverlaps

                log.info("Removing overlaps from glyf table")
                removeOverlaps(
                    varfont,
                    ignoreErrors=(overlap == OverlapMode.REMOVE_AND_IGNORE_ERRORS),
                )

    if "OS/2" in varfont:
        varfont["OS/2"].recalcAvgCharWidth(varfont)

    varLib.set_default_weight_width_slant(
        varfont, location=axisLimits.defaultLocation()
    )

    if updateFontNames:
        # Set Regular/Italic/Bold/Bold Italic bits as appropriate, after the
        # name table has been updated.
        setRibbiBits(varfont)

    if downgradeCFF2:
        origVarfont = varfont
        varfont = downgradeCFF2ToCFF(varfont)
        if inplace:
            origVarfont.__dict__ = varfont.__dict__.copy()

    return varfont


def setRibbiBits(font):
    """Set the `head.macStyle` and `OS/2.fsSelection` style bits
    appropriately."""

    english_ribbi_style = font["name"].getName(names.NameID.SUBFAMILY_NAME, 3, 1, 0x409)
    if english_ribbi_style is None:
        return

    styleMapStyleName = english_ribbi_style.toStr().lower()
    if styleMapStyleName not in {"regular", "bold", "italic", "bold italic"}:
        return

    if styleMapStyleName == "bold":
        font["head"].macStyle = 0b01
    elif styleMapStyleName == "bold italic":
        font["head"].macStyle = 0b11
    elif styleMapStyleName == "italic":
        font["head"].macStyle = 0b10

    selection = font["OS/2"].fsSelection
    # First clear...
    selection &= ~(1 << 0)
    selection &= ~(1 << 5)
    selection &= ~(1 << 6)
    # ...then re-set the bits.
    if styleMapStyleName == "regular":
        selection |= 1 << 6
    elif styleMapStyleName == "bold":
        selection |= 1 << 5
    elif styleMapStyleName == "italic":
        selection |= 1 << 0
    elif styleMapStyleName == "bold italic":
        selection |= 1 << 0
        selection |= 1 << 5
    font["OS/2"].fsSelection = selection


def parseLimits(limits: Iterable[str]) -> Dict[str, Optional[AxisTriple]]:
    result = {}
    for limitString in limits:
        match = re.match(
            r"^(\w{1,4})=(?:(drop)|(?:([^:]*)(?:[:]([^:]*))?(?:[:]([^:]*))?))$",
            limitString,
        )
        if not match:
            raise ValueError("invalid location format: %r" % limitString)
        tag = match.group(1).ljust(4)

        if match.group(2):  # 'drop'
            result[tag] = None
            continue

        triple = match.group(3, 4, 5)

        if triple[1] is None:  # "value" syntax
            triple = (triple[0], triple[0], triple[0])
        elif triple[2] is None:  # "min:max" syntax
            triple = (triple[0], None, triple[1])

        triple = tuple(float(v) if v else None for v in triple)

        result[tag] = AxisTriple(*triple)

    return result


def parseArgs(args):
    """Parse argv.

    Returns:
        3-tuple (infile, axisLimits, options)
        axisLimits is either a Dict[str, Optional[float]], for pinning variation axes
        to specific coordinates along those axes (with `None` as a placeholder for an
        axis' default value); or a Dict[str, Tuple(float, float)], meaning limit this
        axis to min/max range.
        Axes locations are in user-space coordinates, as defined in the "fvar" table.
    """
    from fontTools import configLogger
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools varLib.instancer",
        description="Partially instantiate a variable font",
    )
    parser.add_argument("input", metavar="INPUT.ttf", help="Input variable TTF file.")
    parser.add_argument(
        "locargs",
        metavar="AXIS=LOC",
        nargs="*",
        help="List of space separated locations. A location consists of "
        "the tag of a variation axis, followed by '=' and the literal, "
        "string 'drop', or colon-separated list of one to three values, "
        "each of which is the empty string, or a number. "
        "E.g.: wdth=100 or wght=75.0:125.0 or wght=100:400:700 or wght=:500: "
        "or wght=drop",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT.ttf",
        default=None,
        help="Output instance TTF file (default: INPUT-instance.ttf).",
    )
    parser.add_argument(
        "--static",
        dest="static",
        action="store_true",
        help="Make a static font: pin unspecified axes to their default location.",
    )
    parser.add_argument(
        "--no-optimize",
        dest="optimize",
        action="store_false",
        help="Don't perform IUP optimization on the remaining gvar TupleVariations",
    )
    parser.add_argument(
        "--no-overlap-flag",
        dest="overlap",
        action="store_false",
        help="Don't set OVERLAP_SIMPLE/OVERLAP_COMPOUND glyf flags (only applicable "
        "when generating a full instance)",
    )
    parser.add_argument(
        "--remove-overlaps",
        dest="remove_overlaps",
        action="store_true",
        help="Merge overlapping contours and components (only applicable "
        "when generating a full instance). Requires skia-pathops",
    )
    parser.add_argument(
        "--ignore-overlap-errors",
        dest="ignore_overlap_errors",
        action="store_true",
        help="Don't crash if the remove-overlaps operation fails for some glyphs.",
    )
    parser.add_argument(
        "--update-name-table",
        action="store_true",
        help="Update the instantiated font's `name` table. Input font must have "
        "a STAT table with Axis Value Tables",
    )
    parser.add_argument(
        "--downgrade-cff2",
        action="store_true",
        help="If all axes are pinned, downgrade CFF2 to CFF table format",
    )
    parser.add_argument(
        "--no-recalc-timestamp",
        dest="recalc_timestamp",
        action="store_false",
        help="Don't set the output font's timestamp to the current time.",
    )
    parser.add_argument(
        "--no-recalc-bounds",
        dest="recalc_bounds",
        action="store_false",
        help="Don't recalculate font bounding boxes",
    )
    loggingGroup = parser.add_mutually_exclusive_group(required=False)
    loggingGroup.add_argument(
        "-v", "--verbose", action="store_true", help="Run more verbosely."
    )
    loggingGroup.add_argument(
        "-q", "--quiet", action="store_true", help="Turn verbosity off."
    )
    options = parser.parse_args(args)

    if options.remove_overlaps:
        if options.ignore_overlap_errors:
            options.overlap = OverlapMode.REMOVE_AND_IGNORE_ERRORS
        else:
            options.overlap = OverlapMode.REMOVE
    else:
        options.overlap = OverlapMode(int(options.overlap))

    infile = options.input
    if not os.path.isfile(infile):
        parser.error("No such file '{}'".format(infile))

    configLogger(
        level=("DEBUG" if options.verbose else "ERROR" if options.quiet else "INFO")
    )

    try:
        axisLimits = parseLimits(options.locargs)
    except ValueError as e:
        parser.error(str(e))

    if len(axisLimits) != len(options.locargs):
        parser.error("Specified multiple limits for the same axis")

    return (infile, axisLimits, options)


def main(args=None):
    """Partially instantiate a variable font"""
    infile, axisLimits, options = parseArgs(args)
    log.info("Restricting axes: %s", axisLimits)

    log.info("Loading variable font")
    varfont = TTFont(
        infile,
        recalcTimestamp=options.recalc_timestamp,
        recalcBBoxes=options.recalc_bounds,
    )

    isFullInstance = options.static or {
        axisTag
        for axisTag, limit in axisLimits.items()
        if limit is None or limit[0] == limit[2]
    }.issuperset(axis.axisTag for axis in varfont["fvar"].axes)

    varfont = instantiateVariableFont(
        varfont,
        axisLimits,
        inplace=True,
        optimize=options.optimize,
        overlap=options.overlap,
        updateFontNames=options.update_name_table,
        downgradeCFF2=options.downgrade_cff2,
        static=options.static,
    )

    suffix = "-instance" if isFullInstance else "-partial"
    outfile = (
        makeOutputFileName(infile, overWrite=True, suffix=suffix)
        if not options.output
        else options.output
    )

    log.info(
        "Saving %s font %s",
        "instance" if isFullInstance else "partial variable",
        outfile,
    )
    varfont.save(outfile)
