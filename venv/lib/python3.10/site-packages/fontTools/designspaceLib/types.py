from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union, cast

from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    DesignSpaceDocumentError,
    RangeAxisSubsetDescriptor,
    SimpleLocationDict,
    ValueAxisSubsetDescriptor,
    VariableFontDescriptor,
)


def clamp(value, minimum, maximum):
    return min(max(value, minimum), maximum)


@dataclass
class Range:
    minimum: float
    """Inclusive minimum of the range."""
    maximum: float
    """Inclusive maximum of the range."""
    default: float = 0
    """Default value"""

    def __post_init__(self):
        self.minimum, self.maximum = sorted((self.minimum, self.maximum))
        self.default = clamp(self.default, self.minimum, self.maximum)

    def __contains__(self, value: Union[float, Range]) -> bool:
        if isinstance(value, Range):
            return self.minimum <= value.minimum and value.maximum <= self.maximum
        return self.minimum <= value <= self.maximum

    def intersection(self, other: Range) -> Optional[Range]:
        if self.maximum < other.minimum or self.minimum > other.maximum:
            return None
        else:
            return Range(
                max(self.minimum, other.minimum),
                min(self.maximum, other.maximum),
                self.default,  # We don't care about the default in this use-case
            )


# A region selection is either a range or a single value, as a Designspace v5
# axis-subset element only allows a single discrete value or a range for a
# variable-font element.
Region = Dict[str, Union[Range, float]]

# A conditionset is a set of named ranges.
ConditionSet = Dict[str, Range]

# A rule is a list of conditionsets where any has to be relevant for the whole rule to be relevant.
Rule = List[ConditionSet]
Rules = Dict[str, Rule]


def locationInRegion(location: SimpleLocationDict, region: Region) -> bool:
    for name, value in location.items():
        if name not in region:
            return False
        regionValue = region[name]
        if isinstance(regionValue, (float, int)):
            if value != regionValue:
                return False
        else:
            if value not in regionValue:
                return False
    return True


def regionInRegion(region: Region, superRegion: Region) -> bool:
    for name, value in region.items():
        if not name in superRegion:
            return False
        superValue = superRegion[name]
        if isinstance(superValue, (float, int)):
            if value != superValue:
                return False
        else:
            if value not in superValue:
                return False
    return True


def userRegionToDesignRegion(doc: DesignSpaceDocument, userRegion: Region) -> Region:
    designRegion = {}
    for name, value in userRegion.items():
        axis = doc.getAxis(name)
        if axis is None:
            raise DesignSpaceDocumentError(
                f"Cannot find axis named '{name}' for region."
            )
        if isinstance(value, (float, int)):
            designRegion[name] = axis.map_forward(value)
        else:
            designRegion[name] = Range(
                axis.map_forward(value.minimum),
                axis.map_forward(value.maximum),
                axis.map_forward(value.default),
            )
    return designRegion


def getVFUserRegion(doc: DesignSpaceDocument, vf: VariableFontDescriptor) -> Region:
    vfUserRegion: Region = {}
    # For each axis, 2 cases:
    #  - it has a range = it's an axis in the VF DS
    #  - it's a single location = use it to know which rules should apply in the VF
    for axisSubset in vf.axisSubsets:
        axis = doc.getAxis(axisSubset.name)
        if axis is None:
            raise DesignSpaceDocumentError(
                f"Cannot find axis named '{axisSubset.name}' for variable font '{vf.name}'."
            )
        if hasattr(axisSubset, "userMinimum"):
            # Mypy doesn't support narrowing union types via hasattr()
            # TODO(Python 3.10): use TypeGuard
            # https://mypy.readthedocs.io/en/stable/type_narrowing.html
            axisSubset = cast(RangeAxisSubsetDescriptor, axisSubset)
            if not hasattr(axis, "minimum"):
                raise DesignSpaceDocumentError(
                    f"Cannot select a range over '{axis.name}' for variable font '{vf.name}' "
                    "because it's a discrete axis, use only 'userValue' instead."
                )
            axis = cast(AxisDescriptor, axis)
            vfUserRegion[axis.name] = Range(
                max(axisSubset.userMinimum, axis.minimum),
                min(axisSubset.userMaximum, axis.maximum),
                axisSubset.userDefault or axis.default,
            )
        else:
            axisSubset = cast(ValueAxisSubsetDescriptor, axisSubset)
            vfUserRegion[axis.name] = axisSubset.userValue
    # Any axis not mentioned explicitly has a single location = default value
    for axis in doc.axes:
        if axis.name not in vfUserRegion:
            assert isinstance(
                axis.default, (int, float)
            ), f"Axis '{axis.name}' has no valid default value."
            vfUserRegion[axis.name] = axis.default
    return vfUserRegion
