"""Extra methods for DesignSpaceDocument to generate its STAT table data."""

from __future__ import annotations

from typing import Dict, List, Union

import fontTools.otlLib.builder
from fontTools.designspaceLib import (
    AxisLabelDescriptor,
    DesignSpaceDocument,
    DesignSpaceDocumentError,
    LocationLabelDescriptor,
)
from fontTools.designspaceLib.types import Region, getVFUserRegion, locationInRegion
from fontTools.ttLib import TTFont


def buildVFStatTable(ttFont: TTFont, doc: DesignSpaceDocument, vfName: str) -> None:
    """Build the STAT table for the variable font identified by its name in
    the given document.

    Knowing which variable we're building STAT data for is needed to subset
    the STAT locations to only include what the variable font actually ships.

    .. versionadded:: 5.0

    .. seealso::
        - :func:`getStatAxes()`
        - :func:`getStatLocations()`
        - :func:`fontTools.otlLib.builder.buildStatTable()`
    """
    for vf in doc.getVariableFonts():
        if vf.name == vfName:
            break
    else:
        raise DesignSpaceDocumentError(
            f"Cannot find the variable font by name {vfName}"
        )

    region = getVFUserRegion(doc, vf)

    # if there are not currently any mac names don't add them here, that's inconsistent
    # https://github.com/fonttools/fonttools/issues/683
    macNames = any(
        nr.platformID == 1 for nr in getattr(ttFont.get("name"), "names", ())
    )

    return fontTools.otlLib.builder.buildStatTable(
        ttFont,
        getStatAxes(doc, region),
        getStatLocations(doc, region),
        doc.elidedFallbackName if doc.elidedFallbackName is not None else 2,
        macNames=macNames,
    )


def getStatAxes(doc: DesignSpaceDocument, userRegion: Region) -> List[Dict]:
    """Return a list of axis dicts suitable for use as the ``axes``
    argument to :func:`fontTools.otlLib.builder.buildStatTable()`.

    .. versionadded:: 5.0
    """
    # First, get the axis labels with explicit ordering
    # then append the others in the order they appear.
    maxOrdering = max(
        (axis.axisOrdering for axis in doc.axes if axis.axisOrdering is not None),
        default=-1,
    )
    axisOrderings = []
    for axis in doc.axes:
        if axis.axisOrdering is not None:
            axisOrderings.append(axis.axisOrdering)
        else:
            maxOrdering += 1
            axisOrderings.append(maxOrdering)
    return [
        dict(
            tag=axis.tag,
            name={"en": axis.name, **axis.labelNames},
            ordering=ordering,
            values=[
                _axisLabelToStatLocation(label)
                for label in axis.axisLabels
                if locationInRegion({axis.name: label.userValue}, userRegion)
            ],
        )
        for axis, ordering in zip(doc.axes, axisOrderings)
    ]


def getStatLocations(doc: DesignSpaceDocument, userRegion: Region) -> List[Dict]:
    """Return a list of location dicts suitable for use as the ``locations``
    argument to :func:`fontTools.otlLib.builder.buildStatTable()`.

    .. versionadded:: 5.0
    """
    axesByName = {axis.name: axis for axis in doc.axes}
    return [
        dict(
            name={"en": label.name, **label.labelNames},
            # Location in the designspace is keyed by axis name
            # Location in buildStatTable by axis tag
            location={
                axesByName[name].tag: value
                for name, value in label.getFullUserLocation(doc).items()
            },
            flags=_labelToFlags(label),
        )
        for label in doc.locationLabels
        if locationInRegion(label.getFullUserLocation(doc), userRegion)
    ]


def _labelToFlags(label: Union[AxisLabelDescriptor, LocationLabelDescriptor]) -> int:
    flags = 0
    if label.olderSibling:
        flags |= 1
    if label.elidable:
        flags |= 2
    return flags


def _axisLabelToStatLocation(
    label: AxisLabelDescriptor,
) -> Dict:
    label_format = label.getFormat()
    name = {"en": label.name, **label.labelNames}
    flags = _labelToFlags(label)
    if label_format == 1:
        return dict(name=name, value=label.userValue, flags=flags)
    if label_format == 3:
        return dict(
            name=name,
            value=label.userValue,
            linkedValue=label.linkedUserValue,
            flags=flags,
        )
    if label_format == 2:
        res = dict(
            name=name,
            nominalValue=label.userValue,
            flags=flags,
        )
        if label.userMinimum is not None:
            res["rangeMinValue"] = label.userMinimum
        if label.userMaximum is not None:
            res["rangeMaxValue"] = label.userMaximum
        return res
    raise NotImplementedError("Unknown STAT label format")
