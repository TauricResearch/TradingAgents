from __future__ import annotations

from typing import Mapping, Any
from collections.abc import Container

from fontTools.annotations import KerningNested

"""
Functions for converting UFO1 or UFO2 files into UFO3 format.

Currently provides functionality for converting kerning rules
and kerning groups. Conversion is only supported _from_ UFO1
or UFO2, and _to_ UFO3.
"""

# adapted from the UFO spec


def convertUFO1OrUFO2KerningToUFO3Kerning(
    kerning: KerningNested, groups: dict[str, list[str]], glyphSet: Container[str] = ()
) -> tuple[KerningNested, dict[str, list[str]], dict[str, dict[str, str]]]:
    """Convert kerning data in UFO1 or UFO2 syntax into UFO3 syntax.

    Args:
      kerning:
          A dictionary containing the kerning rules defined in
          the UFO font, as used in :class:`.UFOReader` objects.
      groups:
          A dictionary containing the groups defined in the UFO
          font, as used in :class:`.UFOReader` objects.
      glyphSet:
        Optional; a set of glyph objects to skip (default: None).

    Returns:
      1. A dictionary representing the converted kerning data.
      2. A copy of the groups dictionary, with all groups renamed to UFO3 syntax.
      3. A dictionary containing the mapping of old group names to new group names.

    """
    # gather known kerning groups based on the prefixes
    firstReferencedGroups, secondReferencedGroups = findKnownKerningGroups(groups)
    # Make lists of groups referenced in kerning pairs.
    for first, seconds in list(kerning.items()):
        if first in groups and first not in glyphSet:
            if not first.startswith("public.kern1."):
                firstReferencedGroups.add(first)
        for second in list(seconds.keys()):
            if second in groups and second not in glyphSet:
                if not second.startswith("public.kern2."):
                    secondReferencedGroups.add(second)
    # Create new names for these groups.
    firstRenamedGroups: dict[str, str] = {}
    for first in firstReferencedGroups:
        # Make a list of existing group names.
        existingGroupNames = list(groups.keys()) + list(firstRenamedGroups.keys())
        # Remove the old prefix from the name
        newName = first.replace("@MMK_L_", "")
        # Add the new prefix to the name.
        newName = "public.kern1." + newName
        # Make a unique group name.
        newName = makeUniqueGroupName(newName, existingGroupNames)
        # Store for use later.
        firstRenamedGroups[first] = newName
    secondRenamedGroups: dict[str, str] = {}
    for second in secondReferencedGroups:
        # Make a list of existing group names.
        existingGroupNames = list(groups.keys()) + list(secondRenamedGroups.keys())
        # Remove the old prefix from the name
        newName = second.replace("@MMK_R_", "")
        # Add the new prefix to the name.
        newName = "public.kern2." + newName
        # Make a unique group name.
        newName = makeUniqueGroupName(newName, existingGroupNames)
        # Store for use later.
        secondRenamedGroups[second] = newName
    # Populate the new group names into the kerning dictionary as needed.
    newKerning = {}
    for first, seconds in list(kerning.items()):
        first = firstRenamedGroups.get(first, first)
        newSeconds = {}
        for second, value in list(seconds.items()):
            second = secondRenamedGroups.get(second, second)
            newSeconds[second] = value
        newKerning[first] = newSeconds
    # Make copies of the referenced groups and store them
    # under the new names in the overall groups dictionary.
    allRenamedGroups = list(firstRenamedGroups.items())
    allRenamedGroups += list(secondRenamedGroups.items())
    for oldName, newName in allRenamedGroups:
        group = list(groups[oldName])
        groups[newName] = group
    # Return the kerning and the groups.
    return newKerning, groups, dict(side1=firstRenamedGroups, side2=secondRenamedGroups)


def findKnownKerningGroups(groups: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """Find all kerning groups in a UFO1 or UFO2 font that use known prefixes.

    In some cases, not all kerning groups will be referenced
    by the kerning pairs in a UFO. The algorithm for locating
    groups in :func:`convertUFO1OrUFO2KerningToUFO3Kerning` will
    miss these unreferenced groups. By scanning for known prefixes,
    this function will catch all of the prefixed groups.

    The prefixes and sides by this function are:

    @MMK_L_ - side 1
    @MMK_R_ - side 2

    as defined in the UFO1 specification.

    Args:
        groups:
          A dictionary containing the groups defined in the UFO
          font, as read by :class:`.UFOReader`.

    Returns:
        Two sets; the first containing the names of all
        first-side kerning groups identified in the ``groups``
        dictionary, and the second containing the names of all
        second-side kerning groups identified.

        "First-side" and "second-side" are with respect to the
        writing direction of the script.

        Example::

          >>> testGroups = {
          ...     "@MMK_L_1" : None,
          ...     "@MMK_L_2" : None,
          ...     "@MMK_L_3" : None,
          ...     "@MMK_R_1" : None,
          ...     "@MMK_R_2" : None,
          ...     "@MMK_R_3" : None,
          ...     "@MMK_l_1" : None,
          ...     "@MMK_r_1" : None,
          ...     "@MMK_X_1" : None,
          ...     "foo" : None,
          ... }
          >>> first, second = findKnownKerningGroups(testGroups)
          >>> sorted(first) == ['@MMK_L_1', '@MMK_L_2', '@MMK_L_3']
          True
          >>> sorted(second) == ['@MMK_R_1', '@MMK_R_2', '@MMK_R_3']
          True
    """
    knownFirstGroupPrefixes = ["@MMK_L_"]
    knownSecondGroupPrefixes = ["@MMK_R_"]
    firstGroups = set()
    secondGroups = set()
    for groupName in list(groups.keys()):
        for firstPrefix in knownFirstGroupPrefixes:
            if groupName.startswith(firstPrefix):
                firstGroups.add(groupName)
                break
        for secondPrefix in knownSecondGroupPrefixes:
            if groupName.startswith(secondPrefix):
                secondGroups.add(groupName)
                break
    return firstGroups, secondGroups


def makeUniqueGroupName(name: str, groupNames: list[str], counter: int = 0) -> str:
    """Make a kerning group name that will be unique within the set of group names.

    If the requested kerning group name already exists within the set, this
    will return a new name by adding an incremented counter to the end
    of the requested name.

    Args:
        name:
          The requested kerning group name.
        groupNames:
          A list of the existing kerning group names.
        counter:
          Optional; a counter of group names already seen (default: 0). If
          :attr:`.counter` is not provided, the function will recurse,
          incrementing the value of :attr:`.counter` until it finds the
          first unused ``name+counter`` combination, and return that result.

    Returns:
        A unique kerning group name composed of the requested name suffixed
        by the smallest available integer counter.
    """
    # Add a number to the name if the counter is higher than zero.
    newName = name
    if counter > 0:
        newName = "%s%d" % (newName, counter)
    # If the new name is in the existing group names, recurse.
    if newName in groupNames:
        return makeUniqueGroupName(name, groupNames, counter + 1)
    # Otherwise send back the new name.
    return newName


def test():
    """
    Tests for :func:`.convertUFO1OrUFO2KerningToUFO3Kerning`.

    No known prefixes.

    >>> testKerning = {
    ...     "A" : {
    ...         "A" : 1,
    ...         "B" : 2,
    ...         "CGroup" : 3,
    ...         "DGroup" : 4
    ...     },
    ...     "BGroup" : {
    ...         "A" : 5,
    ...         "B" : 6,
    ...         "CGroup" : 7,
    ...         "DGroup" : 8
    ...     },
    ...     "CGroup" : {
    ...         "A" : 9,
    ...         "B" : 10,
    ...         "CGroup" : 11,
    ...         "DGroup" : 12
    ...     },
    ... }
    >>> testGroups = {
    ...     "BGroup" : ["B"],
    ...     "CGroup" : ["C"],
    ...     "DGroup" : ["D"],
    ... }
    >>> kerning, groups, maps = convertUFO1OrUFO2KerningToUFO3Kerning(
    ...     testKerning, testGroups, [])
    >>> expected = {
    ...     "A" : {
    ...         "A": 1,
    ...         "B": 2,
    ...         "public.kern2.CGroup": 3,
    ...         "public.kern2.DGroup": 4
    ...     },
    ...     "public.kern1.BGroup": {
    ...         "A": 5,
    ...         "B": 6,
    ...         "public.kern2.CGroup": 7,
    ...         "public.kern2.DGroup": 8
    ...     },
    ...     "public.kern1.CGroup": {
    ...         "A": 9,
    ...         "B": 10,
    ...         "public.kern2.CGroup": 11,
    ...         "public.kern2.DGroup": 12
    ...     }
    ... }
    >>> kerning == expected
    True
    >>> expected = {
    ...     "BGroup": ["B"],
    ...     "CGroup": ["C"],
    ...     "DGroup": ["D"],
    ...     "public.kern1.BGroup": ["B"],
    ...     "public.kern1.CGroup": ["C"],
    ...     "public.kern2.CGroup": ["C"],
    ...     "public.kern2.DGroup": ["D"],
    ... }
    >>> groups == expected
    True

    Known prefixes.

    >>> testKerning = {
    ...     "A" : {
    ...         "A" : 1,
    ...         "B" : 2,
    ...         "@MMK_R_CGroup" : 3,
    ...         "@MMK_R_DGroup" : 4
    ...     },
    ...     "@MMK_L_BGroup" : {
    ...         "A" : 5,
    ...         "B" : 6,
    ...         "@MMK_R_CGroup" : 7,
    ...         "@MMK_R_DGroup" : 8
    ...     },
    ...     "@MMK_L_CGroup" : {
    ...         "A" : 9,
    ...         "B" : 10,
    ...         "@MMK_R_CGroup" : 11,
    ...         "@MMK_R_DGroup" : 12
    ...     },
    ... }
    >>> testGroups = {
    ...     "@MMK_L_BGroup" : ["B"],
    ...     "@MMK_L_CGroup" : ["C"],
    ...     "@MMK_L_XGroup" : ["X"],
    ...     "@MMK_R_CGroup" : ["C"],
    ...     "@MMK_R_DGroup" : ["D"],
    ...     "@MMK_R_XGroup" : ["X"],
    ... }
    >>> kerning, groups, maps = convertUFO1OrUFO2KerningToUFO3Kerning(
    ...     testKerning, testGroups, [])
    >>> expected = {
    ...     "A" : {
    ...         "A": 1,
    ...         "B": 2,
    ...         "public.kern2.CGroup": 3,
    ...         "public.kern2.DGroup": 4
    ...     },
    ...     "public.kern1.BGroup": {
    ...         "A": 5,
    ...         "B": 6,
    ...         "public.kern2.CGroup": 7,
    ...         "public.kern2.DGroup": 8
    ...     },
    ...     "public.kern1.CGroup": {
    ...         "A": 9,
    ...         "B": 10,
    ...         "public.kern2.CGroup": 11,
    ...         "public.kern2.DGroup": 12
    ...     }
    ... }
    >>> kerning == expected
    True
    >>> expected = {
    ...     "@MMK_L_BGroup": ["B"],
    ...     "@MMK_L_CGroup": ["C"],
    ...     "@MMK_L_XGroup": ["X"],
    ...     "@MMK_R_CGroup": ["C"],
    ...     "@MMK_R_DGroup": ["D"],
    ...     "@MMK_R_XGroup": ["X"],
    ...     "public.kern1.BGroup": ["B"],
    ...     "public.kern1.CGroup": ["C"],
    ...     "public.kern1.XGroup": ["X"],
    ...     "public.kern2.CGroup": ["C"],
    ...     "public.kern2.DGroup": ["D"],
    ...     "public.kern2.XGroup": ["X"],
    ... }
    >>> groups == expected
    True

    >>> from .validators import kerningValidator
    >>> kerningValidator(kerning)
    (True, None)

    Mixture of known prefixes and groups without prefixes.

    >>> testKerning = {
    ...     "A" : {
    ...         "A" : 1,
    ...         "B" : 2,
    ...         "@MMK_R_CGroup" : 3,
    ...         "DGroup" : 4
    ...     },
    ...     "BGroup" : {
    ...         "A" : 5,
    ...         "B" : 6,
    ...         "@MMK_R_CGroup" : 7,
    ...         "DGroup" : 8
    ...     },
    ...     "@MMK_L_CGroup" : {
    ...         "A" : 9,
    ...         "B" : 10,
    ...         "@MMK_R_CGroup" : 11,
    ...         "DGroup" : 12
    ...     },
    ... }
    >>> testGroups = {
    ...     "BGroup" : ["B"],
    ...     "@MMK_L_CGroup" : ["C"],
    ...     "@MMK_R_CGroup" : ["C"],
    ...     "DGroup" : ["D"],
    ... }
    >>> kerning, groups, maps = convertUFO1OrUFO2KerningToUFO3Kerning(
    ...     testKerning, testGroups, [])
    >>> expected = {
    ...     "A" : {
    ...         "A": 1,
    ...         "B": 2,
    ...         "public.kern2.CGroup": 3,
    ...         "public.kern2.DGroup": 4
    ...     },
    ...     "public.kern1.BGroup": {
    ...         "A": 5,
    ...         "B": 6,
    ...         "public.kern2.CGroup": 7,
    ...         "public.kern2.DGroup": 8
    ...     },
    ...     "public.kern1.CGroup": {
    ...         "A": 9,
    ...         "B": 10,
    ...         "public.kern2.CGroup": 11,
    ...         "public.kern2.DGroup": 12
    ...     }
    ... }
    >>> kerning == expected
    True
    >>> expected = {
    ...     "BGroup": ["B"],
    ...     "@MMK_L_CGroup": ["C"],
    ...     "@MMK_R_CGroup": ["C"],
    ...     "DGroup": ["D"],
    ...     "public.kern1.BGroup": ["B"],
    ...     "public.kern1.CGroup": ["C"],
    ...     "public.kern2.CGroup": ["C"],
    ...     "public.kern2.DGroup": ["D"],
    ... }
    >>> groups == expected
    True
    """


if __name__ == "__main__":
    import doctest

    doctest.testmod()
