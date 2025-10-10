"""Allows building all the variable fonts of a DesignSpace version 5 by
splitting the document into interpolable sub-space, then into each VF.
"""

from __future__ import annotations

import itertools
import logging
import math
from typing import Any, Callable, Dict, Iterator, List, Tuple, cast

from fontTools.designspaceLib import (
    AxisDescriptor,
    AxisMappingDescriptor,
    DesignSpaceDocument,
    DiscreteAxisDescriptor,
    InstanceDescriptor,
    RuleDescriptor,
    SimpleLocationDict,
    SourceDescriptor,
    VariableFontDescriptor,
)
from fontTools.designspaceLib.statNames import StatNames, getStatNames
from fontTools.designspaceLib.types import (
    ConditionSet,
    Range,
    Region,
    getVFUserRegion,
    locationInRegion,
    regionInRegion,
    userRegionToDesignRegion,
)

LOGGER = logging.getLogger(__name__)

MakeInstanceFilenameCallable = Callable[
    [DesignSpaceDocument, InstanceDescriptor, StatNames], str
]


def defaultMakeInstanceFilename(
    doc: DesignSpaceDocument, instance: InstanceDescriptor, statNames: StatNames
) -> str:
    """Default callable to synthesize an instance filename
    when makeNames=True, for instances that don't specify an instance name
    in the designspace. This part of the name generation can be overriden
    because it's not specified by the STAT table.
    """
    familyName = instance.familyName or statNames.familyNames.get("en")
    styleName = instance.styleName or statNames.styleNames.get("en")
    return f"{familyName}-{styleName}.ttf"


def splitInterpolable(
    doc: DesignSpaceDocument,
    makeNames: bool = True,
    expandLocations: bool = True,
    makeInstanceFilename: MakeInstanceFilenameCallable = defaultMakeInstanceFilename,
) -> Iterator[Tuple[SimpleLocationDict, DesignSpaceDocument]]:
    """Split the given DS5 into several interpolable sub-designspaces.
    There are as many interpolable sub-spaces as there are combinations of
    discrete axis values.

    E.g. with axes:
        - italic (discrete) Upright or Italic
        - style (discrete) Sans or Serif
        - weight (continuous) 100 to 900

    There are 4 sub-spaces in which the Weight axis should interpolate:
    (Upright, Sans), (Upright, Serif), (Italic, Sans) and (Italic, Serif).

    The sub-designspaces still include the full axis definitions and STAT data,
    but the rules, sources, variable fonts, instances are trimmed down to only
    keep what falls within the interpolable sub-space.

    Args:
      - ``makeNames``: Whether to compute the instance family and style
        names using the STAT data.
      - ``expandLocations``: Whether to turn all locations into "full"
        locations, including implicit default axis values where missing.
      - ``makeInstanceFilename``: Callable to synthesize an instance filename
        when makeNames=True, for instances that don't specify an instance name
        in the designspace. This part of the name generation can be overridden
        because it's not specified by the STAT table.

    .. versionadded:: 5.0
    """
    discreteAxes = []
    interpolableUserRegion: Region = {}
    for axis in doc.axes:
        if hasattr(axis, "values"):
            # Mypy doesn't support narrowing union types via hasattr()
            # TODO(Python 3.10): use TypeGuard
            # https://mypy.readthedocs.io/en/stable/type_narrowing.html
            axis = cast(DiscreteAxisDescriptor, axis)
            discreteAxes.append(axis)
        else:
            axis = cast(AxisDescriptor, axis)
            interpolableUserRegion[axis.name] = Range(
                axis.minimum,
                axis.maximum,
                axis.default,
            )
    valueCombinations = itertools.product(*[axis.values for axis in discreteAxes])
    for values in valueCombinations:
        discreteUserLocation = {
            discreteAxis.name: value
            for discreteAxis, value in zip(discreteAxes, values)
        }
        subDoc = _extractSubSpace(
            doc,
            {**interpolableUserRegion, **discreteUserLocation},
            keepVFs=True,
            makeNames=makeNames,
            expandLocations=expandLocations,
            makeInstanceFilename=makeInstanceFilename,
        )
        yield discreteUserLocation, subDoc


def splitVariableFonts(
    doc: DesignSpaceDocument,
    makeNames: bool = False,
    expandLocations: bool = False,
    makeInstanceFilename: MakeInstanceFilenameCallable = defaultMakeInstanceFilename,
) -> Iterator[Tuple[str, DesignSpaceDocument]]:
    """Convert each variable font listed in this document into a standalone
    designspace. This can be used to compile all the variable fonts from a
    format 5 designspace using tools that can only deal with 1 VF at a time.

    Args:
      - ``makeNames``: Whether to compute the instance family and style
        names using the STAT data.
      - ``expandLocations``: Whether to turn all locations into "full"
        locations, including implicit default axis values where missing.
      - ``makeInstanceFilename``: Callable to synthesize an instance filename
        when makeNames=True, for instances that don't specify an instance name
        in the designspace. This part of the name generation can be overridden
        because it's not specified by the STAT table.

    .. versionadded:: 5.0
    """
    # Make one DesignspaceDoc v5 for each variable font
    for vf in doc.getVariableFonts():
        vfUserRegion = getVFUserRegion(doc, vf)
        vfDoc = _extractSubSpace(
            doc,
            vfUserRegion,
            keepVFs=False,
            makeNames=makeNames,
            expandLocations=expandLocations,
            makeInstanceFilename=makeInstanceFilename,
        )
        vfDoc.lib = {**vfDoc.lib, **vf.lib}
        yield vf.name, vfDoc


def convert5to4(
    doc: DesignSpaceDocument,
) -> Dict[str, DesignSpaceDocument]:
    """Convert each variable font listed in this document into a standalone
    format 4 designspace. This can be used to compile all the variable fonts
    from a format 5 designspace using tools that only know about format 4.

    .. versionadded:: 5.0
    """
    vfs = {}
    for _location, subDoc in splitInterpolable(doc):
        for vfName, vfDoc in splitVariableFonts(subDoc):
            vfDoc.formatVersion = "4.1"
            vfs[vfName] = vfDoc
    return vfs


def _extractSubSpace(
    doc: DesignSpaceDocument,
    userRegion: Region,
    *,
    keepVFs: bool,
    makeNames: bool,
    expandLocations: bool,
    makeInstanceFilename: MakeInstanceFilenameCallable,
) -> DesignSpaceDocument:
    subDoc = DesignSpaceDocument()
    # Don't include STAT info
    # FIXME: (Jany) let's think about it. Not include = OK because the point of
    # the splitting is to build VFs and we'll use the STAT data of the full
    # document to generate the STAT of the VFs, so "no need" to have STAT data
    # in sub-docs. Counterpoint: what if someone wants to split this DS for
    # other purposes?  Maybe for that it would be useful to also subset the STAT
    # data?
    # subDoc.elidedFallbackName = doc.elidedFallbackName

    def maybeExpandDesignLocation(object):
        if expandLocations:
            return object.getFullDesignLocation(doc)
        else:
            return object.designLocation

    for axis in doc.axes:
        range = userRegion[axis.name]
        if isinstance(range, Range) and hasattr(axis, "minimum"):
            # Mypy doesn't support narrowing union types via hasattr()
            # TODO(Python 3.10): use TypeGuard
            # https://mypy.readthedocs.io/en/stable/type_narrowing.html
            axis = cast(AxisDescriptor, axis)
            subDoc.addAxis(
                AxisDescriptor(
                    # Same info
                    tag=axis.tag,
                    name=axis.name,
                    labelNames=axis.labelNames,
                    hidden=axis.hidden,
                    # Subset range
                    minimum=max(range.minimum, axis.minimum),
                    default=range.default or axis.default,
                    maximum=min(range.maximum, axis.maximum),
                    map=[
                        (user, design)
                        for user, design in axis.map
                        if range.minimum <= user <= range.maximum
                    ],
                    # Don't include STAT info
                    axisOrdering=None,
                    axisLabels=None,
                )
            )

    subDoc.axisMappings = mappings = []
    subDocAxes = {axis.name for axis in subDoc.axes}
    for mapping in doc.axisMappings:
        if not all(axis in subDocAxes for axis in mapping.inputLocation.keys()):
            continue
        if not all(axis in subDocAxes for axis in mapping.outputLocation.keys()):
            LOGGER.error(
                "In axis mapping from input %s, some output axes are not in the variable-font: %s",
                mapping.inputLocation,
                mapping.outputLocation,
            )
            continue

        mappingAxes = set()
        mappingAxes.update(mapping.inputLocation.keys())
        mappingAxes.update(mapping.outputLocation.keys())
        for axis in doc.axes:
            if axis.name not in mappingAxes:
                continue
            range = userRegion[axis.name]
            if (
                range.minimum != axis.minimum
                or (range.default is not None and range.default != axis.default)
                or range.maximum != axis.maximum
            ):
                LOGGER.error(
                    "Limiting axis ranges used in <mapping> elements not supported: %s",
                    axis.name,
                )
                continue

        mappings.append(
            AxisMappingDescriptor(
                inputLocation=mapping.inputLocation,
                outputLocation=mapping.outputLocation,
            )
        )

    # Don't include STAT info
    # subDoc.locationLabels = doc.locationLabels

    # Rules: subset them based on conditions
    designRegion = userRegionToDesignRegion(doc, userRegion)
    subDoc.rules = _subsetRulesBasedOnConditions(doc.rules, designRegion)
    subDoc.rulesProcessingLast = doc.rulesProcessingLast

    # Sources: keep only the ones that fall within the kept axis ranges
    for source in doc.sources:
        if not locationInRegion(doc.map_backward(source.designLocation), userRegion):
            continue

        subDoc.addSource(
            SourceDescriptor(
                filename=source.filename,
                path=source.path,
                font=source.font,
                name=source.name,
                designLocation=_filterLocation(
                    userRegion, maybeExpandDesignLocation(source)
                ),
                layerName=source.layerName,
                familyName=source.familyName,
                styleName=source.styleName,
                muteKerning=source.muteKerning,
                muteInfo=source.muteInfo,
                mutedGlyphNames=source.mutedGlyphNames,
            )
        )

    # Copy family name translations from the old default source to the new default
    vfDefault = subDoc.findDefault()
    oldDefault = doc.findDefault()
    if vfDefault is not None and oldDefault is not None:
        vfDefault.localisedFamilyName = oldDefault.localisedFamilyName

    # Variable fonts: keep only the ones that fall within the kept axis ranges
    if keepVFs:
        # Note: call getVariableFont() to make the implicit VFs explicit
        for vf in doc.getVariableFonts():
            vfUserRegion = getVFUserRegion(doc, vf)
            if regionInRegion(vfUserRegion, userRegion):
                subDoc.addVariableFont(
                    VariableFontDescriptor(
                        name=vf.name,
                        filename=vf.filename,
                        axisSubsets=[
                            axisSubset
                            for axisSubset in vf.axisSubsets
                            if isinstance(userRegion[axisSubset.name], Range)
                        ],
                        lib=vf.lib,
                    )
                )

    # Instances: same as Sources + compute missing names
    for instance in doc.instances:
        if not locationInRegion(instance.getFullUserLocation(doc), userRegion):
            continue

        if makeNames:
            statNames = getStatNames(doc, instance.getFullUserLocation(doc))
            familyName = instance.familyName or statNames.familyNames.get("en")
            styleName = instance.styleName or statNames.styleNames.get("en")
            subDoc.addInstance(
                InstanceDescriptor(
                    filename=instance.filename
                    or makeInstanceFilename(doc, instance, statNames),
                    path=instance.path,
                    font=instance.font,
                    name=instance.name or f"{familyName} {styleName}",
                    userLocation={} if expandLocations else instance.userLocation,
                    designLocation=_filterLocation(
                        userRegion, maybeExpandDesignLocation(instance)
                    ),
                    familyName=familyName,
                    styleName=styleName,
                    postScriptFontName=instance.postScriptFontName
                    or statNames.postScriptFontName,
                    styleMapFamilyName=instance.styleMapFamilyName
                    or statNames.styleMapFamilyNames.get("en"),
                    styleMapStyleName=instance.styleMapStyleName
                    or statNames.styleMapStyleName,
                    localisedFamilyName=instance.localisedFamilyName
                    or statNames.familyNames,
                    localisedStyleName=instance.localisedStyleName
                    or statNames.styleNames,
                    localisedStyleMapFamilyName=instance.localisedStyleMapFamilyName
                    or statNames.styleMapFamilyNames,
                    localisedStyleMapStyleName=instance.localisedStyleMapStyleName
                    or {},
                    lib=instance.lib,
                )
            )
        else:
            subDoc.addInstance(
                InstanceDescriptor(
                    filename=instance.filename,
                    path=instance.path,
                    font=instance.font,
                    name=instance.name,
                    userLocation={} if expandLocations else instance.userLocation,
                    designLocation=_filterLocation(
                        userRegion, maybeExpandDesignLocation(instance)
                    ),
                    familyName=instance.familyName,
                    styleName=instance.styleName,
                    postScriptFontName=instance.postScriptFontName,
                    styleMapFamilyName=instance.styleMapFamilyName,
                    styleMapStyleName=instance.styleMapStyleName,
                    localisedFamilyName=instance.localisedFamilyName,
                    localisedStyleName=instance.localisedStyleName,
                    localisedStyleMapFamilyName=instance.localisedStyleMapFamilyName,
                    localisedStyleMapStyleName=instance.localisedStyleMapStyleName,
                    lib=instance.lib,
                )
            )

    subDoc.lib = doc.lib

    return subDoc


def _conditionSetFrom(conditionSet: List[Dict[str, Any]]) -> ConditionSet:
    c: Dict[str, Range] = {}
    for condition in conditionSet:
        minimum, maximum = condition.get("minimum"), condition.get("maximum")
        c[condition["name"]] = Range(
            minimum if minimum is not None else -math.inf,
            maximum if maximum is not None else math.inf,
        )
    return c


def _subsetRulesBasedOnConditions(
    rules: List[RuleDescriptor], designRegion: Region
) -> List[RuleDescriptor]:
    # What rules to keep:
    #  - Keep the rule if any conditionset is relevant.
    #  - A conditionset is relevant if all conditions are relevant or it is empty.
    #  - A condition is relevant if
    #    - axis is point (C-AP),
    #       - and point in condition's range (C-AP-in)
    #            (in this case remove the condition because it's always true)
    #       - else (C-AP-out) whole conditionset can be discarded (condition false
    #         => conditionset false)
    #    - axis is range (C-AR),
    #       - (C-AR-all) and axis range fully contained in condition range: we can
    #         scrap the condition because it's always true
    #       - (C-AR-inter) and intersection(axis range, condition range) not empty:
    #         keep the condition with the smaller range (= intersection)
    #       - (C-AR-none) else, whole conditionset can be discarded
    newRules: List[RuleDescriptor] = []
    for rule in rules:
        newRule: RuleDescriptor = RuleDescriptor(
            name=rule.name, conditionSets=[], subs=rule.subs
        )
        for conditionset in rule.conditionSets:
            cs = _conditionSetFrom(conditionset)
            newConditionset: List[Dict[str, Any]] = []
            discardConditionset = False
            for selectionName, selectionValue in designRegion.items():
                # TODO: Ensure that all(key in conditionset for key in region.keys())?
                if selectionName not in cs:
                    # raise Exception("Selection has different axes than the rules")
                    continue
                if isinstance(selectionValue, (float, int)):  # is point
                    # Case C-AP-in
                    if selectionValue in cs[selectionName]:
                        pass  # always matches, conditionset can stay empty for this one.
                    # Case C-AP-out
                    else:
                        discardConditionset = True
                else:  # is range
                    # Case C-AR-all
                    if selectionValue in cs[selectionName]:
                        pass  # always matches, conditionset can stay empty for this one.
                    else:
                        intersection = cs[selectionName].intersection(selectionValue)
                        # Case C-AR-inter
                        if intersection is not None:
                            newConditionset.append(
                                {
                                    "name": selectionName,
                                    "minimum": intersection.minimum,
                                    "maximum": intersection.maximum,
                                }
                            )
                        # Case C-AR-none
                        else:
                            discardConditionset = True
            if not discardConditionset:
                newRule.conditionSets.append(newConditionset)
        if newRule.conditionSets:
            newRules.append(newRule)

    return newRules


def _filterLocation(
    userRegion: Region,
    location: Dict[str, float],
) -> Dict[str, float]:
    return {
        name: value
        for name, value in location.items()
        if name in userRegion and isinstance(userRegion[name], Range)
    }
