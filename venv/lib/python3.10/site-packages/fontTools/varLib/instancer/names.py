"""Helpers for instantiating name table records."""

from contextlib import contextmanager
from copy import deepcopy
from enum import IntEnum
import re


class NameID(IntEnum):
    FAMILY_NAME = 1
    SUBFAMILY_NAME = 2
    UNIQUE_FONT_IDENTIFIER = 3
    FULL_FONT_NAME = 4
    VERSION_STRING = 5
    POSTSCRIPT_NAME = 6
    TYPOGRAPHIC_FAMILY_NAME = 16
    TYPOGRAPHIC_SUBFAMILY_NAME = 17
    VARIATIONS_POSTSCRIPT_NAME_PREFIX = 25


ELIDABLE_AXIS_VALUE_NAME = 2


def getVariationNameIDs(varfont):
    used = []
    if "fvar" in varfont:
        fvar = varfont["fvar"]
        for axis in fvar.axes:
            used.append(axis.axisNameID)
        for instance in fvar.instances:
            used.append(instance.subfamilyNameID)
            if instance.postscriptNameID != 0xFFFF:
                used.append(instance.postscriptNameID)
    if "STAT" in varfont:
        stat = varfont["STAT"].table
        for axis in stat.DesignAxisRecord.Axis if stat.DesignAxisRecord else ():
            used.append(axis.AxisNameID)
        for value in stat.AxisValueArray.AxisValue if stat.AxisValueArray else ():
            used.append(value.ValueNameID)
        elidedFallbackNameID = getattr(stat, "ElidedFallbackNameID", None)
        if elidedFallbackNameID is not None:
            used.append(elidedFallbackNameID)
    # nameIDs <= 255 are reserved by OT spec so we don't touch them
    return {nameID for nameID in used if nameID > 255}


@contextmanager
def pruningUnusedNames(varfont):
    from . import log

    origNameIDs = getVariationNameIDs(varfont)

    yield

    log.info("Pruning name table")
    exclude = origNameIDs - getVariationNameIDs(varfont)
    varfont["name"].names[:] = [
        record for record in varfont["name"].names if record.nameID not in exclude
    ]
    if "ltag" in varfont:
        # Drop the whole 'ltag' table if all the language-dependent Unicode name
        # records that reference it have been dropped.
        # TODO: Only prune unused ltag tags, renumerating langIDs accordingly.
        # Note ltag can also be used by feat or morx tables, so check those too.
        if not any(
            record
            for record in varfont["name"].names
            if record.platformID == 0 and record.langID != 0xFFFF
        ):
            del varfont["ltag"]


def updateNameTable(varfont, axisLimits):
    """Update instatiated variable font's name table using STAT AxisValues.

    Raises ValueError if the STAT table is missing or an Axis Value table is
    missing for requested axis locations.

    First, collect all STAT AxisValues that match the new default axis locations
    (excluding "elided" ones); concatenate the strings in design axis order,
    while giving priority to "synthetic" values (Format 4), to form the
    typographic subfamily name associated with the new default instance.
    Finally, update all related records in the name table, making sure that
    legacy family/sub-family names conform to the the R/I/B/BI (Regular, Italic,
    Bold, Bold Italic) naming model.

    Example: Updating a partial variable font:
    | >>> ttFont = TTFont("OpenSans[wdth,wght].ttf")
    | >>> updateNameTable(ttFont, {"wght": (400, 900), "wdth": 75})

    The name table records will be updated in the following manner:
    NameID 1 familyName: "Open Sans" --> "Open Sans Condensed"
    NameID 2 subFamilyName: "Regular" --> "Regular"
    NameID 3 Unique font identifier: "3.000;GOOG;OpenSans-Regular" --> \
        "3.000;GOOG;OpenSans-Condensed"
    NameID 4 Full font name: "Open Sans Regular" --> "Open Sans Condensed"
    NameID 6 PostScript name: "OpenSans-Regular" --> "OpenSans-Condensed"
    NameID 16 Typographic Family name: None --> "Open Sans"
    NameID 17 Typographic Subfamily name: None --> "Condensed"

    References:
    https://docs.microsoft.com/en-us/typography/opentype/spec/stat
    https://docs.microsoft.com/en-us/typography/opentype/spec/name#name-ids
    """
    from . import AxisLimits, axisValuesFromAxisLimits

    if "STAT" not in varfont:
        raise ValueError("Cannot update name table since there is no STAT table.")
    stat = varfont["STAT"].table
    if not stat.AxisValueArray:
        raise ValueError("Cannot update name table since there are no STAT Axis Values")
    fvar = varfont["fvar"]

    # The updated name table will reflect the new 'zero origin' of the font.
    # If we're instantiating a partial font, we will populate the unpinned
    # axes with their default axis values from fvar.
    axisLimits = AxisLimits(axisLimits).limitAxesAndPopulateDefaults(varfont)
    partialDefaults = axisLimits.defaultLocation()
    fvarDefaults = {a.axisTag: a.defaultValue for a in fvar.axes}
    defaultAxisCoords = AxisLimits({**fvarDefaults, **partialDefaults})
    assert all(v.minimum == v.maximum for v in defaultAxisCoords.values())

    axisValueTables = axisValuesFromAxisLimits(stat, defaultAxisCoords)
    checkAxisValuesExist(stat, axisValueTables, defaultAxisCoords.pinnedLocation())

    # ignore "elidable" axis values, should be omitted in application font menus.
    axisValueTables = [
        v for v in axisValueTables if not v.Flags & ELIDABLE_AXIS_VALUE_NAME
    ]
    axisValueTables = _sortAxisValues(axisValueTables)
    _updateNameRecords(varfont, axisValueTables)


def checkAxisValuesExist(stat, axisValues, axisCoords):
    seen = set()
    designAxes = stat.DesignAxisRecord.Axis
    hasValues = set()
    for value in stat.AxisValueArray.AxisValue:
        if value.Format in (1, 2, 3):
            hasValues.add(designAxes[value.AxisIndex].AxisTag)
        elif value.Format == 4:
            for rec in value.AxisValueRecord:
                hasValues.add(designAxes[rec.AxisIndex].AxisTag)

    for axisValueTable in axisValues:
        axisValueFormat = axisValueTable.Format
        if axisValueTable.Format in (1, 2, 3):
            axisTag = designAxes[axisValueTable.AxisIndex].AxisTag
            if axisValueFormat == 2:
                axisValue = axisValueTable.NominalValue
            else:
                axisValue = axisValueTable.Value
            if axisTag in axisCoords and axisValue == axisCoords[axisTag]:
                seen.add(axisTag)
        elif axisValueTable.Format == 4:
            for rec in axisValueTable.AxisValueRecord:
                axisTag = designAxes[rec.AxisIndex].AxisTag
                if axisTag in axisCoords and rec.Value == axisCoords[axisTag]:
                    seen.add(axisTag)

    missingAxes = (set(axisCoords) - seen) & hasValues
    if missingAxes:
        missing = ", ".join(f"'{i}': {axisCoords[i]}" for i in missingAxes)
        raise ValueError(f"Cannot find Axis Values {{{missing}}}")


def _sortAxisValues(axisValues):
    # Sort by axis index, remove duplicates and ensure that format 4 AxisValues
    # are dominant.
    # The MS Spec states: "if a format 1, format 2 or format 3 table has a
    # (nominal) value used in a format 4 table that also has values for
    # other axes, the format 4 table, being the more specific match, is used",
    # https://docs.microsoft.com/en-us/typography/opentype/spec/stat#axis-value-table-format-4
    results = []
    seenAxes = set()
    # Sort format 4 axes so the tables with the most AxisValueRecords are first
    format4 = sorted(
        [v for v in axisValues if v.Format == 4],
        key=lambda v: len(v.AxisValueRecord),
        reverse=True,
    )

    for val in format4:
        axisIndexes = set(r.AxisIndex for r in val.AxisValueRecord)
        minIndex = min(axisIndexes)
        if not seenAxes & axisIndexes:
            seenAxes |= axisIndexes
            results.append((minIndex, val))

    for val in axisValues:
        if val in format4:
            continue
        axisIndex = val.AxisIndex
        if axisIndex not in seenAxes:
            seenAxes.add(axisIndex)
            results.append((axisIndex, val))

    return [axisValue for _, axisValue in sorted(results)]


def _updateNameRecords(varfont, axisValues):
    # Update nametable based on the axisValues using the R/I/B/BI model.
    nametable = varfont["name"]
    stat = varfont["STAT"].table

    axisValueNameIDs = [a.ValueNameID for a in axisValues]
    ribbiNameIDs = [n for n in axisValueNameIDs if _isRibbi(nametable, n)]
    nonRibbiNameIDs = [n for n in axisValueNameIDs if n not in ribbiNameIDs]
    elidedNameID = stat.ElidedFallbackNameID
    elidedNameIsRibbi = _isRibbi(nametable, elidedNameID)

    getName = nametable.getName
    platforms = set((r.platformID, r.platEncID, r.langID) for r in nametable.names)
    for platform in platforms:
        if not all(getName(i, *platform) for i in (1, 2, elidedNameID)):
            # Since no family name and subfamily name records were found,
            # we cannot update this set of name Records.
            continue

        subFamilyName = " ".join(
            getName(n, *platform).toUnicode() for n in ribbiNameIDs
        )
        if nonRibbiNameIDs:
            typoSubFamilyName = " ".join(
                getName(n, *platform).toUnicode() for n in axisValueNameIDs
            )
        else:
            typoSubFamilyName = None

        # If neither subFamilyName and typographic SubFamilyName exist,
        # we will use the STAT's elidedFallbackName
        if not typoSubFamilyName and not subFamilyName:
            if elidedNameIsRibbi:
                subFamilyName = getName(elidedNameID, *platform).toUnicode()
            else:
                typoSubFamilyName = getName(elidedNameID, *platform).toUnicode()

        familyNameSuffix = " ".join(
            getName(n, *platform).toUnicode() for n in nonRibbiNameIDs
        )

        _updateNameTableStyleRecords(
            varfont,
            familyNameSuffix,
            subFamilyName,
            typoSubFamilyName,
            *platform,
        )


def _isRibbi(nametable, nameID):
    englishRecord = nametable.getName(nameID, 3, 1, 0x409)
    return (
        True
        if englishRecord is not None
        and englishRecord.toUnicode() in ("Regular", "Italic", "Bold", "Bold Italic")
        else False
    )


def _updateNameTableStyleRecords(
    varfont,
    familyNameSuffix,
    subFamilyName,
    typoSubFamilyName,
    platformID=3,
    platEncID=1,
    langID=0x409,
):
    # TODO (Marc F) It may be nice to make this part a standalone
    # font renamer in the future.
    nametable = varfont["name"]
    platform = (platformID, platEncID, langID)

    currentFamilyName = nametable.getName(
        NameID.TYPOGRAPHIC_FAMILY_NAME, *platform
    ) or nametable.getName(NameID.FAMILY_NAME, *platform)

    currentStyleName = nametable.getName(
        NameID.TYPOGRAPHIC_SUBFAMILY_NAME, *platform
    ) or nametable.getName(NameID.SUBFAMILY_NAME, *platform)

    if not all([currentFamilyName, currentStyleName]):
        raise ValueError(f"Missing required NameIDs 1 and 2 for platform {platform}")

    currentFamilyName = currentFamilyName.toUnicode()
    currentStyleName = currentStyleName.toUnicode()

    nameIDs = {
        NameID.FAMILY_NAME: currentFamilyName,
        NameID.SUBFAMILY_NAME: subFamilyName or "Regular",
    }
    if typoSubFamilyName:
        nameIDs[NameID.FAMILY_NAME] = f"{currentFamilyName} {familyNameSuffix}".strip()
        nameIDs[NameID.TYPOGRAPHIC_FAMILY_NAME] = currentFamilyName
        nameIDs[NameID.TYPOGRAPHIC_SUBFAMILY_NAME] = typoSubFamilyName
    else:
        # Remove previous Typographic Family and SubFamily names since they're
        # no longer required
        for nameID in (
            NameID.TYPOGRAPHIC_FAMILY_NAME,
            NameID.TYPOGRAPHIC_SUBFAMILY_NAME,
        ):
            nametable.removeNames(nameID=nameID)

    newFamilyName = (
        nameIDs.get(NameID.TYPOGRAPHIC_FAMILY_NAME) or nameIDs[NameID.FAMILY_NAME]
    )
    newStyleName = (
        nameIDs.get(NameID.TYPOGRAPHIC_SUBFAMILY_NAME) or nameIDs[NameID.SUBFAMILY_NAME]
    )

    nameIDs[NameID.FULL_FONT_NAME] = f"{newFamilyName} {newStyleName}"
    nameIDs[NameID.POSTSCRIPT_NAME] = _updatePSNameRecord(
        varfont, newFamilyName, newStyleName, platform
    )

    uniqueID = _updateUniqueIdNameRecord(varfont, nameIDs, platform)
    if uniqueID:
        nameIDs[NameID.UNIQUE_FONT_IDENTIFIER] = uniqueID

    for nameID, string in nameIDs.items():
        assert string, nameID
        nametable.setName(string, nameID, *platform)

    if "fvar" not in varfont:
        nametable.removeNames(NameID.VARIATIONS_POSTSCRIPT_NAME_PREFIX)


def _updatePSNameRecord(varfont, familyName, styleName, platform):
    # Implementation based on Adobe Technical Note #5902 :
    # https://wwwimages2.adobe.com/content/dam/acom/en/devnet/font/pdfs/5902.AdobePSNameGeneration.pdf
    nametable = varfont["name"]

    family_prefix = nametable.getName(
        NameID.VARIATIONS_POSTSCRIPT_NAME_PREFIX, *platform
    )
    if family_prefix:
        family_prefix = family_prefix.toUnicode()
    else:
        family_prefix = familyName

    psName = f"{family_prefix}-{styleName}"
    # Remove any characters other than uppercase Latin letters, lowercase
    # Latin letters, digits and hyphens.
    psName = re.sub(r"[^A-Za-z0-9-]", r"", psName)

    if len(psName) > 127:
        # Abbreviating the stylename so it fits within 127 characters whilst
        # conforming to every vendor's specification is too complex. Instead
        # we simply truncate the psname and add the required "..."
        return f"{psName[:124]}..."
    return psName


def _updateUniqueIdNameRecord(varfont, nameIDs, platform):
    nametable = varfont["name"]
    currentRecord = nametable.getName(NameID.UNIQUE_FONT_IDENTIFIER, *platform)
    if not currentRecord:
        return None

    # Check if full name and postscript name are a substring of currentRecord
    for nameID in (NameID.FULL_FONT_NAME, NameID.POSTSCRIPT_NAME):
        nameRecord = nametable.getName(nameID, *platform)
        if not nameRecord:
            continue
        if nameRecord.toUnicode() in currentRecord.toUnicode():
            return currentRecord.toUnicode().replace(
                nameRecord.toUnicode(), nameIDs[nameRecord.nameID]
            )

    # Create a new string since we couldn't find any substrings.
    fontVersion = _fontVersion(varfont, platform)
    achVendID = varfont["OS/2"].achVendID
    # Remove non-ASCII characers and trailing spaces
    vendor = re.sub(r"[^\x00-\x7F]", "", achVendID).strip()
    psName = nameIDs[NameID.POSTSCRIPT_NAME]
    return f"{fontVersion};{vendor};{psName}"


def _fontVersion(font, platform=(3, 1, 0x409)):
    nameRecord = font["name"].getName(NameID.VERSION_STRING, *platform)
    if nameRecord is None:
        return f'{font["head"].fontRevision:.3f}'
    # "Version 1.101; ttfautohint (v1.8.1.43-b0c9)" --> "1.101"
    # Also works fine with inputs "Version 1.101" or "1.101" etc
    versionNumber = nameRecord.toUnicode().split(";")[0]
    return versionNumber.lstrip("Version ").strip()
