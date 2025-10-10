"""
    designSpaceDocument

    - Read and write designspace files
"""

from __future__ import annotations

import collections
import copy
import itertools
import math
import os
import posixpath
from io import BytesIO, StringIO
from textwrap import indent
from typing import Any, Dict, List, MutableMapping, Optional, Tuple, Union, cast

from fontTools.misc import etree as ET
from fontTools.misc import plistlib
from fontTools.misc.loggingTools import LogMixin
from fontTools.misc.textTools import tobytes, tostr


__all__ = [
    "AxisDescriptor",
    "AxisLabelDescriptor",
    "AxisMappingDescriptor",
    "BaseDocReader",
    "BaseDocWriter",
    "DesignSpaceDocument",
    "DesignSpaceDocumentError",
    "DiscreteAxisDescriptor",
    "InstanceDescriptor",
    "LocationLabelDescriptor",
    "RangeAxisSubsetDescriptor",
    "RuleDescriptor",
    "SourceDescriptor",
    "ValueAxisSubsetDescriptor",
    "VariableFontDescriptor",
]

# ElementTree allows to find namespace-prefixed elements, but not attributes
# so we have to do it ourselves for 'xml:lang'
XML_NS = "{http://www.w3.org/XML/1998/namespace}"
XML_LANG = XML_NS + "lang"


def posix(path):
    """Normalize paths using forward slash to work also on Windows."""
    new_path = posixpath.join(*path.split(os.path.sep))
    if path.startswith("/"):
        # The above transformation loses absolute paths
        new_path = "/" + new_path
    elif path.startswith(r"\\"):
        # The above transformation loses leading slashes of UNC path mounts
        new_path = "//" + new_path
    return new_path


def posixpath_property(private_name):
    """Generate a propery that holds a path always using forward slashes."""

    def getter(self):
        # Normal getter
        return getattr(self, private_name)

    def setter(self, value):
        # The setter rewrites paths using forward slashes
        if value is not None:
            value = posix(value)
        setattr(self, private_name, value)

    return property(getter, setter)


class DesignSpaceDocumentError(Exception):
    def __init__(self, msg, obj=None):
        self.msg = msg
        self.obj = obj

    def __str__(self):
        return str(self.msg) + (": %r" % self.obj if self.obj is not None else "")


class AsDictMixin(object):
    def asdict(self):
        d = {}
        for attr, value in self.__dict__.items():
            if attr.startswith("_"):
                continue
            if hasattr(value, "asdict"):
                value = value.asdict()
            elif isinstance(value, list):
                value = [v.asdict() if hasattr(v, "asdict") else v for v in value]
            d[attr] = value
        return d


class SimpleDescriptor(AsDictMixin):
    """Containers for a bunch of attributes"""

    # XXX this is ugly. The 'print' is inappropriate here, and instead of
    # assert, it should simply return True/False
    def compare(self, other):
        # test if this object contains the same data as the other
        for attr in self._attrs:
            try:
                assert getattr(self, attr) == getattr(other, attr)
            except AssertionError:
                print(
                    "failed attribute",
                    attr,
                    getattr(self, attr),
                    "!=",
                    getattr(other, attr),
                )

    def __repr__(self):
        attrs = [f"{a}={repr(getattr(self, a))}," for a in self._attrs]
        attrs = indent("\n".join(attrs), "    ")
        return f"{self.__class__.__name__}(\n{attrs}\n)"


class SourceDescriptor(SimpleDescriptor):
    """Simple container for data related to the source

    .. code:: python

        doc = DesignSpaceDocument()
        s1 = SourceDescriptor()
        s1.path = masterPath1
        s1.name = "master.ufo1"
        s1.font = defcon.Font("master.ufo1")
        s1.location = dict(weight=0)
        s1.familyName = "MasterFamilyName"
        s1.styleName = "MasterStyleNameOne"
        s1.localisedFamilyName = dict(fr="Caractère")
        s1.mutedGlyphNames.append("A")
        s1.mutedGlyphNames.append("Z")
        doc.addSource(s1)

    """

    flavor = "source"
    _attrs = [
        "filename",
        "path",
        "name",
        "layerName",
        "location",
        "copyLib",
        "copyGroups",
        "copyFeatures",
        "muteKerning",
        "muteInfo",
        "mutedGlyphNames",
        "familyName",
        "styleName",
        "localisedFamilyName",
    ]

    filename = posixpath_property("_filename")
    path = posixpath_property("_path")

    def __init__(
        self,
        *,
        filename=None,
        path=None,
        font=None,
        name=None,
        location=None,
        designLocation=None,
        layerName=None,
        familyName=None,
        styleName=None,
        localisedFamilyName=None,
        copyLib=False,
        copyInfo=False,
        copyGroups=False,
        copyFeatures=False,
        muteKerning=False,
        muteInfo=False,
        mutedGlyphNames=None,
    ):
        self.filename = filename
        """string. A relative path to the source file, **as it is in the document**.

        MutatorMath + VarLib.
        """
        self.path = path
        """The absolute path, calculated from filename."""

        self.font = font
        """Any Python object. Optional. Points to a representation of this
        source font that is loaded in memory, as a Python object (e.g. a
        ``defcon.Font`` or a ``fontTools.ttFont.TTFont``).

        The default document reader will not fill-in this attribute, and the
        default writer will not use this attribute. It is up to the user of
        ``designspaceLib`` to either load the resource identified by
        ``filename`` and store it in this field, or write the contents of
        this field to the disk and make ```filename`` point to that.
        """

        self.name = name
        """string. Optional. Unique identifier name for this source.

        MutatorMath + varLib.
        """

        self.designLocation = (
            designLocation if designLocation is not None else location or {}
        )
        """dict. Axis values for this source, in design space coordinates.

        MutatorMath + varLib.

        This may be only part of the full design location.
        See :meth:`getFullDesignLocation()`

        .. versionadded:: 5.0
        """

        self.layerName = layerName
        """string. The name of the layer in the source to look for
        outline data. Default ``None`` which means ``foreground``.
        """
        self.familyName = familyName
        """string. Family name of this source. Though this data
        can be extracted from the font, it can be efficient to have it right
        here.

        varLib.
        """
        self.styleName = styleName
        """string. Style name of this source. Though this data
        can be extracted from the font, it can be efficient to have it right
        here.

        varLib.
        """
        self.localisedFamilyName = localisedFamilyName or {}
        """dict. A dictionary of localised family name strings, keyed by
        language code.

        If present, will be used to build localized names for all instances.

        .. versionadded:: 5.0
        """

        self.copyLib = copyLib
        """bool. Indicates if the contents of the font.lib need to
        be copied to the instances.

        MutatorMath.

        .. deprecated:: 5.0
        """
        self.copyInfo = copyInfo
        """bool. Indicates if the non-interpolating font.info needs
        to be copied to the instances.

        MutatorMath.

        .. deprecated:: 5.0
        """
        self.copyGroups = copyGroups
        """bool. Indicates if the groups need to be copied to the
        instances.

        MutatorMath.

        .. deprecated:: 5.0
        """
        self.copyFeatures = copyFeatures
        """bool. Indicates if the feature text needs to be
        copied to the instances.

        MutatorMath.

        .. deprecated:: 5.0
        """
        self.muteKerning = muteKerning
        """bool. Indicates if the kerning data from this source
        needs to be muted (i.e. not be part of the calculations).

        MutatorMath only.
        """
        self.muteInfo = muteInfo
        """bool. Indicated if the interpolating font.info data for
        this source needs to be muted.

        MutatorMath only.
        """
        self.mutedGlyphNames = mutedGlyphNames or []
        """list. Glyphnames that need to be muted in the
        instances.

        MutatorMath only.
        """

    @property
    def location(self):
        """dict. Axis values for this source, in design space coordinates.

        MutatorMath + varLib.

        .. deprecated:: 5.0
           Use the more explicit alias for this property :attr:`designLocation`.
        """
        return self.designLocation

    @location.setter
    def location(self, location: Optional[SimpleLocationDict]):
        self.designLocation = location or {}

    def setFamilyName(self, familyName, languageCode="en"):
        """Setter for :attr:`localisedFamilyName`

        .. versionadded:: 5.0
        """
        self.localisedFamilyName[languageCode] = tostr(familyName)

    def getFamilyName(self, languageCode="en"):
        """Getter for :attr:`localisedFamilyName`

        .. versionadded:: 5.0
        """
        return self.localisedFamilyName.get(languageCode)

    def getFullDesignLocation(self, doc: "DesignSpaceDocument") -> SimpleLocationDict:
        """Get the complete design location of this source, from its
        :attr:`designLocation` and the document's axis defaults.

        .. versionadded:: 5.0
        """
        result: SimpleLocationDict = {}
        for axis in doc.axes:
            if axis.name in self.designLocation:
                result[axis.name] = self.designLocation[axis.name]
            else:
                result[axis.name] = axis.map_forward(axis.default)
        return result


class RuleDescriptor(SimpleDescriptor):
    """Represents the rule descriptor element: a set of glyph substitutions to
    trigger conditionally in some parts of the designspace.

    .. code:: python

        r1 = RuleDescriptor()
        r1.name = "unique.rule.name"
        r1.conditionSets.append([dict(name="weight", minimum=-10, maximum=10), dict(...)])
        r1.conditionSets.append([dict(...), dict(...)])
        r1.subs.append(("a", "a.alt"))

    .. code:: xml

        <!-- optional: list of substitution rules -->
        <rules>
            <rule name="vertical.bars">
                <conditionset>
                    <condition minimum="250.000000" maximum="750.000000" name="weight"/>
                    <condition minimum="100" name="width"/>
                    <condition minimum="10" maximum="40" name="optical"/>
                </conditionset>
                <sub name="cent" with="cent.alt"/>
                <sub name="dollar" with="dollar.alt"/>
            </rule>
        </rules>
    """

    _attrs = ["name", "conditionSets", "subs"]  # what do we need here

    def __init__(self, *, name=None, conditionSets=None, subs=None):
        self.name = name
        """string. Unique name for this rule. Can be used to reference this rule data."""
        # list of lists of dict(name='aaaa', minimum=0, maximum=1000)
        self.conditionSets = conditionSets or []
        """a list of conditionsets.

        -  Each conditionset is a list of conditions.
        -  Each condition is a dict with ``name``, ``minimum`` and ``maximum`` keys.
        """
        # list of substitutions stored as tuples of glyphnames ("a", "a.alt")
        self.subs = subs or []
        """list of substitutions.

        -  Each substitution is stored as tuples of glyphnames, e.g. ("a", "a.alt").
        -  Note: By default, rules are applied first, before other text
           shaping/OpenType layout, as they are part of the
           `Required Variation Alternates OpenType feature <https://docs.microsoft.com/en-us/typography/opentype/spec/features_pt#-tag-rvrn>`_.
           See ref:`rules-element` § Attributes.
        """


def evaluateRule(rule, location):
    """Return True if any of the rule's conditionsets matches the given location."""
    return any(evaluateConditions(c, location) for c in rule.conditionSets)


def evaluateConditions(conditions, location):
    """Return True if all the conditions matches the given location.

    - If a condition has no minimum, check for < maximum.
    - If a condition has no maximum, check for > minimum.
    """
    for cd in conditions:
        value = location[cd["name"]]
        if cd.get("minimum") is None:
            if value > cd["maximum"]:
                return False
        elif cd.get("maximum") is None:
            if cd["minimum"] > value:
                return False
        elif not cd["minimum"] <= value <= cd["maximum"]:
            return False
    return True


def processRules(rules, location, glyphNames):
    """Apply these rules at this location to these glyphnames.

    Return a new list of glyphNames with substitutions applied.

    - rule order matters
    """
    newNames = []
    for rule in rules:
        if evaluateRule(rule, location):
            for name in glyphNames:
                swap = False
                for a, b in rule.subs:
                    if name == a:
                        swap = True
                        break
                if swap:
                    newNames.append(b)
                else:
                    newNames.append(name)
            glyphNames = newNames
            newNames = []
    return glyphNames


AnisotropicLocationDict = Dict[str, Union[float, Tuple[float, float]]]
SimpleLocationDict = Dict[str, float]


class AxisMappingDescriptor(SimpleDescriptor):
    """Represents the axis mapping element: mapping an input location
    to an output location in the designspace.

    .. code:: python

        m1 = AxisMappingDescriptor()
        m1.inputLocation = {"weight": 900, "width": 150}
        m1.outputLocation = {"weight": 870}

    .. code:: xml

        <mappings>
            <mapping>
                <input>
                    <dimension name="weight" xvalue="900"/>
                    <dimension name="width" xvalue="150"/>
                </input>
                <output>
                    <dimension name="weight" xvalue="870"/>
                </output>
            </mapping>
        </mappings>
    """

    _attrs = ["inputLocation", "outputLocation"]

    def __init__(
        self,
        *,
        inputLocation=None,
        outputLocation=None,
        description=None,
        groupDescription=None,
    ):
        self.inputLocation: SimpleLocationDict = inputLocation or {}
        """dict. Axis values for the input of the mapping, in design space coordinates.

        varLib.

        .. versionadded:: 5.1
        """
        self.outputLocation: SimpleLocationDict = outputLocation or {}
        """dict. Axis values for the output of the mapping, in design space coordinates.

        varLib.

        .. versionadded:: 5.1
        """
        self.description = description
        """string. A description of the mapping.

        varLib.

        .. versionadded:: 5.2
        """
        self.groupDescription = groupDescription
        """string. A description of the group of mappings.

        varLib.

        .. versionadded:: 5.2
        """


class InstanceDescriptor(SimpleDescriptor):
    """Simple container for data related to the instance


    .. code:: python

        i2 = InstanceDescriptor()
        i2.path = instancePath2
        i2.familyName = "InstanceFamilyName"
        i2.styleName = "InstanceStyleName"
        i2.name = "instance.ufo2"
        # anisotropic location
        i2.designLocation = dict(weight=500, width=(400,300))
        i2.postScriptFontName = "InstancePostscriptName"
        i2.styleMapFamilyName = "InstanceStyleMapFamilyName"
        i2.styleMapStyleName = "InstanceStyleMapStyleName"
        i2.lib['com.coolDesignspaceApp.specimenText'] = 'Hamburgerwhatever'
        doc.addInstance(i2)
    """

    flavor = "instance"
    _defaultLanguageCode = "en"
    _attrs = [
        "filename",
        "path",
        "name",
        "locationLabel",
        "designLocation",
        "userLocation",
        "familyName",
        "styleName",
        "postScriptFontName",
        "styleMapFamilyName",
        "styleMapStyleName",
        "localisedFamilyName",
        "localisedStyleName",
        "localisedStyleMapFamilyName",
        "localisedStyleMapStyleName",
        "glyphs",
        "kerning",
        "info",
        "lib",
    ]

    filename = posixpath_property("_filename")
    path = posixpath_property("_path")

    def __init__(
        self,
        *,
        filename=None,
        path=None,
        font=None,
        name=None,
        location=None,
        locationLabel=None,
        designLocation=None,
        userLocation=None,
        familyName=None,
        styleName=None,
        postScriptFontName=None,
        styleMapFamilyName=None,
        styleMapStyleName=None,
        localisedFamilyName=None,
        localisedStyleName=None,
        localisedStyleMapFamilyName=None,
        localisedStyleMapStyleName=None,
        glyphs=None,
        kerning=True,
        info=True,
        lib=None,
    ):
        self.filename = filename
        """string. Relative path to the instance file, **as it is
        in the document**. The file may or may not exist.

        MutatorMath + VarLib.
        """
        self.path = path
        """string. Absolute path to the instance file, calculated from
        the document path and the string in the filename attr. The file may
        or may not exist.

        MutatorMath.
        """
        self.font = font
        """Same as :attr:`SourceDescriptor.font`

        .. seealso:: :attr:`SourceDescriptor.font`
        """
        self.name = name
        """string. Unique identifier name of the instance, used to
        identify it if it needs to be referenced from elsewhere in the
        document.
        """
        self.locationLabel = locationLabel
        """Name of a :class:`LocationLabelDescriptor`. If
        provided, the instance should have the same location as the
        LocationLabel.

        .. seealso::
           :meth:`getFullDesignLocation`
           :meth:`getFullUserLocation`

        .. versionadded:: 5.0
        """
        self.designLocation: AnisotropicLocationDict = (
            designLocation if designLocation is not None else (location or {})
        )
        """dict. Axis values for this instance, in design space coordinates.

        MutatorMath + varLib.

        .. seealso:: This may be only part of the full location. See:
           :meth:`getFullDesignLocation`
           :meth:`getFullUserLocation`

        .. versionadded:: 5.0
        """
        self.userLocation: SimpleLocationDict = userLocation or {}
        """dict. Axis values for this instance, in user space coordinates.

        MutatorMath + varLib.

        .. seealso:: This may be only part of the full location. See:
           :meth:`getFullDesignLocation`
           :meth:`getFullUserLocation`

        .. versionadded:: 5.0
        """
        self.familyName = familyName
        """string. Family name of this instance.

        MutatorMath + varLib.
        """
        self.styleName = styleName
        """string. Style name of this instance.

        MutatorMath + varLib.
        """
        self.postScriptFontName = postScriptFontName
        """string. Postscript fontname for this instance.

        MutatorMath + varLib.
        """
        self.styleMapFamilyName = styleMapFamilyName
        """string. StyleMap familyname for this instance.

        MutatorMath + varLib.
        """
        self.styleMapStyleName = styleMapStyleName
        """string. StyleMap stylename for this instance.

        MutatorMath + varLib.
        """
        self.localisedFamilyName = localisedFamilyName or {}
        """dict. A dictionary of localised family name
        strings, keyed by language code.
        """
        self.localisedStyleName = localisedStyleName or {}
        """dict. A dictionary of localised stylename
        strings, keyed by language code.
        """
        self.localisedStyleMapFamilyName = localisedStyleMapFamilyName or {}
        """A dictionary of localised style map
        familyname strings, keyed by language code.
        """
        self.localisedStyleMapStyleName = localisedStyleMapStyleName or {}
        """A dictionary of localised style map
        stylename strings, keyed by language code.
        """
        self.glyphs = glyphs or {}
        """dict for special master definitions for glyphs. If glyphs
        need special masters (to record the results of executed rules for
        example).

        MutatorMath.

        .. deprecated:: 5.0
            Use rules or sparse sources instead.
        """
        self.kerning = kerning
        """ bool. Indicates if this instance needs its kerning
        calculated.

        MutatorMath.

        .. deprecated:: 5.0
        """
        self.info = info
        """bool. Indicated if this instance needs the interpolating
        font.info calculated.

        .. deprecated:: 5.0
        """

        self.lib = lib or {}
        """Custom data associated with this instance."""

    @property
    def location(self):
        """dict. Axis values for this instance.

        MutatorMath + varLib.

        .. deprecated:: 5.0
           Use the more explicit alias for this property :attr:`designLocation`.
        """
        return self.designLocation

    @location.setter
    def location(self, location: Optional[AnisotropicLocationDict]):
        self.designLocation = location or {}

    def setStyleName(self, styleName, languageCode="en"):
        """These methods give easier access to the localised names."""
        self.localisedStyleName[languageCode] = tostr(styleName)

    def getStyleName(self, languageCode="en"):
        return self.localisedStyleName.get(languageCode)

    def setFamilyName(self, familyName, languageCode="en"):
        self.localisedFamilyName[languageCode] = tostr(familyName)

    def getFamilyName(self, languageCode="en"):
        return self.localisedFamilyName.get(languageCode)

    def setStyleMapStyleName(self, styleMapStyleName, languageCode="en"):
        self.localisedStyleMapStyleName[languageCode] = tostr(styleMapStyleName)

    def getStyleMapStyleName(self, languageCode="en"):
        return self.localisedStyleMapStyleName.get(languageCode)

    def setStyleMapFamilyName(self, styleMapFamilyName, languageCode="en"):
        self.localisedStyleMapFamilyName[languageCode] = tostr(styleMapFamilyName)

    def getStyleMapFamilyName(self, languageCode="en"):
        return self.localisedStyleMapFamilyName.get(languageCode)

    def clearLocation(self, axisName: Optional[str] = None):
        """Clear all location-related fields. Ensures that
        :attr:``designLocation`` and :attr:``userLocation`` are dictionaries
        (possibly empty if clearing everything).

        In order to update the location of this instance wholesale, a user
        should first clear all the fields, then change the field(s) for which
        they have data.

        .. code:: python

            instance.clearLocation()
            instance.designLocation = {'Weight': (34, 36.5), 'Width': 100}
            instance.userLocation = {'Opsz': 16}

        In order to update a single axis location, the user should only clear
        that axis, then edit the values:

        .. code:: python

            instance.clearLocation('Weight')
            instance.designLocation['Weight'] = (34, 36.5)

        Args:
          axisName: if provided, only clear the location for that axis.

        .. versionadded:: 5.0
        """
        self.locationLabel = None
        if axisName is None:
            self.designLocation = {}
            self.userLocation = {}
        else:
            if self.designLocation is None:
                self.designLocation = {}
            if axisName in self.designLocation:
                del self.designLocation[axisName]
            if self.userLocation is None:
                self.userLocation = {}
            if axisName in self.userLocation:
                del self.userLocation[axisName]

    def getLocationLabelDescriptor(
        self, doc: "DesignSpaceDocument"
    ) -> Optional[LocationLabelDescriptor]:
        """Get the :class:`LocationLabelDescriptor` instance that matches
        this instances's :attr:`locationLabel`.

        Raises if the named label can't be found.

        .. versionadded:: 5.0
        """
        if self.locationLabel is None:
            return None
        label = doc.getLocationLabel(self.locationLabel)
        if label is None:
            raise DesignSpaceDocumentError(
                "InstanceDescriptor.getLocationLabelDescriptor(): "
                f"unknown location label `{self.locationLabel}` in instance `{self.name}`."
            )
        return label

    def getFullDesignLocation(
        self, doc: "DesignSpaceDocument"
    ) -> AnisotropicLocationDict:
        """Get the complete design location of this instance, by combining data
        from the various location fields, default axis values and mappings, and
        top-level location labels.

        The source of truth for this instance's location is determined for each
        axis independently by taking the first not-None field in this list:

        - ``locationLabel``: the location along this axis is the same as the
          matching STAT format 4 label. No anisotropy.
        - ``designLocation[axisName]``: the explicit design location along this
          axis, possibly anisotropic.
        - ``userLocation[axisName]``: the explicit user location along this
          axis. No anisotropy.
        - ``axis.default``: default axis value. No anisotropy.

        .. versionadded:: 5.0
        """
        label = self.getLocationLabelDescriptor(doc)
        if label is not None:
            return doc.map_forward(label.userLocation)  # type: ignore
        result: AnisotropicLocationDict = {}
        for axis in doc.axes:
            if axis.name in self.designLocation:
                result[axis.name] = self.designLocation[axis.name]
            elif axis.name in self.userLocation:
                result[axis.name] = axis.map_forward(self.userLocation[axis.name])
            else:
                result[axis.name] = axis.map_forward(axis.default)
        return result

    def getFullUserLocation(self, doc: "DesignSpaceDocument") -> SimpleLocationDict:
        """Get the complete user location for this instance.

        .. seealso:: :meth:`getFullDesignLocation`

        .. versionadded:: 5.0
        """
        return doc.map_backward(self.getFullDesignLocation(doc))


def tagForAxisName(name):
    # try to find or make a tag name for this axis name
    names = {
        "weight": ("wght", dict(en="Weight")),
        "width": ("wdth", dict(en="Width")),
        "optical": ("opsz", dict(en="Optical Size")),
        "slant": ("slnt", dict(en="Slant")),
        "italic": ("ital", dict(en="Italic")),
    }
    if name.lower() in names:
        return names[name.lower()]
    if len(name) < 4:
        tag = name + "*" * (4 - len(name))
    else:
        tag = name[:4]
    return tag, dict(en=name)


class AbstractAxisDescriptor(SimpleDescriptor):
    flavor = "axis"

    def __init__(
        self,
        *,
        tag=None,
        name=None,
        labelNames=None,
        hidden=False,
        map=None,
        axisOrdering=None,
        axisLabels=None,
    ):
        # opentype tag for this axis
        self.tag = tag
        """string. Four letter tag for this axis. Some might be
        registered at the `OpenType
        specification <https://www.microsoft.com/typography/otspec/fvar.htm#VAT>`__.
        Privately-defined axis tags must begin with an uppercase letter and
        use only uppercase letters or digits.
        """
        # name of the axis used in locations
        self.name = name
        """string. Name of the axis as it is used in the location dicts.

        MutatorMath + varLib.
        """
        # names for UI purposes, if this is not a standard axis,
        self.labelNames = labelNames or {}
        """dict. When defining a non-registered axis, it will be
        necessary to define user-facing readable names for the axis. Keyed by
        xml:lang code. Values are required to be ``unicode`` strings, even if
        they only contain ASCII characters.
        """
        self.hidden = hidden
        """bool. Whether this axis should be hidden in user interfaces.
        """
        self.map = map or []
        """list of input / output values that can describe a warp of user space
        to design space coordinates. If no map values are present, it is assumed
        user space is the same as design space, as in [(minimum, minimum),
        (maximum, maximum)].

        varLib.
        """
        self.axisOrdering = axisOrdering
        """STAT table field ``axisOrdering``.

        See: `OTSpec STAT Axis Record <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#axis-records>`_

        .. versionadded:: 5.0
        """
        self.axisLabels: List[AxisLabelDescriptor] = axisLabels or []
        """STAT table entries for Axis Value Tables format 1, 2, 3.

        See: `OTSpec STAT Axis Value Tables <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#axis-value-tables>`_

        .. versionadded:: 5.0
        """


class AxisDescriptor(AbstractAxisDescriptor):
    """Simple container for the axis data.

    Add more localisations?

    .. code:: python

        a1 = AxisDescriptor()
        a1.minimum = 1
        a1.maximum = 1000
        a1.default = 400
        a1.name = "weight"
        a1.tag = "wght"
        a1.labelNames['fa-IR'] = "قطر"
        a1.labelNames['en'] = "Wéíght"
        a1.map = [(1.0, 10.0), (400.0, 66.0), (1000.0, 990.0)]
        a1.axisOrdering = 1
        a1.axisLabels = [
            AxisLabelDescriptor(name="Regular", userValue=400, elidable=True)
        ]
        doc.addAxis(a1)
    """

    _attrs = [
        "tag",
        "name",
        "maximum",
        "minimum",
        "default",
        "map",
        "axisOrdering",
        "axisLabels",
    ]

    def __init__(
        self,
        *,
        tag=None,
        name=None,
        labelNames=None,
        minimum=None,
        default=None,
        maximum=None,
        hidden=False,
        map=None,
        axisOrdering=None,
        axisLabels=None,
    ):
        super().__init__(
            tag=tag,
            name=name,
            labelNames=labelNames,
            hidden=hidden,
            map=map,
            axisOrdering=axisOrdering,
            axisLabels=axisLabels,
        )
        self.minimum = minimum
        """number. The minimum value for this axis in user space.

        MutatorMath + varLib.
        """
        self.maximum = maximum
        """number. The maximum value for this axis in user space.

        MutatorMath + varLib.
        """
        self.default = default
        """number. The default value for this axis, i.e. when a new location is
        created, this is the value this axis will get in user space.

        MutatorMath + varLib.
        """

    def serialize(self):
        # output to a dict, used in testing
        return dict(
            tag=self.tag,
            name=self.name,
            labelNames=self.labelNames,
            maximum=self.maximum,
            minimum=self.minimum,
            default=self.default,
            hidden=self.hidden,
            map=self.map,
            axisOrdering=self.axisOrdering,
            axisLabels=self.axisLabels,
        )

    def map_forward(self, v):
        """Maps value from axis mapping's input (user) to output (design)."""
        from fontTools.varLib.models import piecewiseLinearMap

        if not self.map:
            return v
        return piecewiseLinearMap(v, {k: v for k, v in self.map})

    def map_backward(self, v):
        """Maps value from axis mapping's output (design) to input (user)."""
        from fontTools.varLib.models import piecewiseLinearMap

        if isinstance(v, tuple):
            v = v[0]
        if not self.map:
            return v
        return piecewiseLinearMap(v, {v: k for k, v in self.map})


class DiscreteAxisDescriptor(AbstractAxisDescriptor):
    """Container for discrete axis data.

    Use this for axes that do not interpolate. The main difference from a
    continuous axis is that a continuous axis has a ``minimum`` and ``maximum``,
    while a discrete axis has a list of ``values``.

    Example: an Italic axis with 2 stops, Roman and Italic, that are not
    compatible. The axis still allows to bind together the full font family,
    which is useful for the STAT table, however it can't become a variation
    axis in a VF.

    .. code:: python

        a2 = DiscreteAxisDescriptor()
        a2.values = [0, 1]
        a2.default = 0
        a2.name = "Italic"
        a2.tag = "ITAL"
        a2.labelNames['fr'] = "Italique"
        a2.map = [(0, 0), (1, -11)]
        a2.axisOrdering = 2
        a2.axisLabels = [
            AxisLabelDescriptor(name="Roman", userValue=0, elidable=True)
        ]
        doc.addAxis(a2)

    .. versionadded:: 5.0
    """

    flavor = "axis"
    _attrs = ("tag", "name", "values", "default", "map", "axisOrdering", "axisLabels")

    def __init__(
        self,
        *,
        tag=None,
        name=None,
        labelNames=None,
        values=None,
        default=None,
        hidden=False,
        map=None,
        axisOrdering=None,
        axisLabels=None,
    ):
        super().__init__(
            tag=tag,
            name=name,
            labelNames=labelNames,
            hidden=hidden,
            map=map,
            axisOrdering=axisOrdering,
            axisLabels=axisLabels,
        )
        self.default: float = default
        """The default value for this axis, i.e. when a new location is
        created, this is the value this axis will get in user space.

        However, this default value is less important than in continuous axes:

        -  it doesn't define the "neutral" version of outlines from which
           deltas would apply, as this axis does not interpolate.
        -  it doesn't provide the reference glyph set for the designspace, as
           fonts at each value can have different glyph sets.
        """
        self.values: List[float] = values or []
        """List of possible values for this axis. Contrary to continuous axes,
        only the values in this list can be taken by the axis, nothing in-between.
        """

    def map_forward(self, value):
        """Maps value from axis mapping's input to output.

        Returns value unchanged if no mapping entry is found.

        Note: for discrete axes, each value must have its mapping entry, if
        you intend that value to be mapped.
        """
        return next((v for k, v in self.map if k == value), value)

    def map_backward(self, value):
        """Maps value from axis mapping's output to input.

        Returns value unchanged if no mapping entry is found.

        Note: for discrete axes, each value must have its mapping entry, if
        you intend that value to be mapped.
        """
        if isinstance(value, tuple):
            value = value[0]
        return next((k for k, v in self.map if v == value), value)


class AxisLabelDescriptor(SimpleDescriptor):
    """Container for axis label data.

    Analogue of OpenType's STAT data for a single axis (formats 1, 2 and 3).
    All values are user values.
    See: `OTSpec STAT Axis value table, format 1, 2, 3 <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#axis-value-table-format-1>`_

    The STAT format of the Axis value depends on which field are filled-in,
    see :meth:`getFormat`

    .. versionadded:: 5.0
    """

    flavor = "label"
    _attrs = (
        "userMinimum",
        "userValue",
        "userMaximum",
        "name",
        "elidable",
        "olderSibling",
        "linkedUserValue",
        "labelNames",
    )

    def __init__(
        self,
        *,
        name,
        userValue,
        userMinimum=None,
        userMaximum=None,
        elidable=False,
        olderSibling=False,
        linkedUserValue=None,
        labelNames=None,
    ):
        self.userMinimum: Optional[float] = userMinimum
        """STAT field ``rangeMinValue`` (format 2)."""
        self.userValue: float = userValue
        """STAT field ``value`` (format 1, 3) or ``nominalValue`` (format 2)."""
        self.userMaximum: Optional[float] = userMaximum
        """STAT field ``rangeMaxValue`` (format 2)."""
        self.name: str = name
        """Label for this axis location, STAT field ``valueNameID``."""
        self.elidable: bool = elidable
        """STAT flag ``ELIDABLE_AXIS_VALUE_NAME``.

        See: `OTSpec STAT Flags <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#flags>`_
        """
        self.olderSibling: bool = olderSibling
        """STAT flag ``OLDER_SIBLING_FONT_ATTRIBUTE``.

        See: `OTSpec STAT Flags <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#flags>`_
        """
        self.linkedUserValue: Optional[float] = linkedUserValue
        """STAT field ``linkedValue`` (format 3)."""
        self.labelNames: MutableMapping[str, str] = labelNames or {}
        """User-facing translations of this location's label. Keyed by
        ``xml:lang`` code.
        """

    def getFormat(self) -> int:
        """Determine which format of STAT Axis value to use to encode this label.

        ===========  =========  ===========  ===========  ===============
        STAT Format  userValue  userMinimum  userMaximum  linkedUserValue
        ===========  =========  ===========  ===========  ===============
        1            ✅          ❌            ❌            ❌
        2            ✅          ✅            ✅            ❌
        3            ✅          ❌            ❌            ✅
        ===========  =========  ===========  ===========  ===============
        """
        if self.linkedUserValue is not None:
            return 3
        if self.userMinimum is not None or self.userMaximum is not None:
            return 2
        return 1

    @property
    def defaultName(self) -> str:
        """Return the English name from :attr:`labelNames` or the :attr:`name`."""
        return self.labelNames.get("en") or self.name


class LocationLabelDescriptor(SimpleDescriptor):
    """Container for location label data.

    Analogue of OpenType's STAT data for a free-floating location (format 4).
    All values are user values.

    See: `OTSpec STAT Axis value table, format 4 <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#axis-value-table-format-4>`_

    .. versionadded:: 5.0
    """

    flavor = "label"
    _attrs = ("name", "elidable", "olderSibling", "userLocation", "labelNames")

    def __init__(
        self,
        *,
        name,
        userLocation,
        elidable=False,
        olderSibling=False,
        labelNames=None,
    ):
        self.name: str = name
        """Label for this named location, STAT field ``valueNameID``."""
        self.userLocation: SimpleLocationDict = userLocation or {}
        """Location in user coordinates along each axis.

        If an axis is not mentioned, it is assumed to be at its default location.

        .. seealso:: This may be only part of the full location. See:
           :meth:`getFullUserLocation`
        """
        self.elidable: bool = elidable
        """STAT flag ``ELIDABLE_AXIS_VALUE_NAME``.

        See: `OTSpec STAT Flags <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#flags>`_
        """
        self.olderSibling: bool = olderSibling
        """STAT flag ``OLDER_SIBLING_FONT_ATTRIBUTE``.

        See: `OTSpec STAT Flags <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#flags>`_
        """
        self.labelNames: Dict[str, str] = labelNames or {}
        """User-facing translations of this location's label. Keyed by
        xml:lang code.
        """

    @property
    def defaultName(self) -> str:
        """Return the English name from :attr:`labelNames` or the :attr:`name`."""
        return self.labelNames.get("en") or self.name

    def getFullUserLocation(self, doc: "DesignSpaceDocument") -> SimpleLocationDict:
        """Get the complete user location of this label, by combining data
        from the explicit user location and default axis values.

        .. versionadded:: 5.0
        """
        return {
            axis.name: self.userLocation.get(axis.name, axis.default)
            for axis in doc.axes
        }


class VariableFontDescriptor(SimpleDescriptor):
    """Container for variable fonts, sub-spaces of the Designspace.

    Use-cases:

    - From a single DesignSpace with discrete axes, define 1 variable font
      per value on the discrete axes. Before version 5, you would have needed
      1 DesignSpace per such variable font, and a lot of data duplication.
    - From a big variable font with many axes, define subsets of that variable
      font that only include some axes and freeze other axes at a given location.

    .. versionadded:: 5.0
    """

    flavor = "variable-font"
    _attrs = ("filename", "axisSubsets", "lib")

    filename = posixpath_property("_filename")

    def __init__(self, *, name, filename=None, axisSubsets=None, lib=None):
        self.name: str = name
        """string, required. Name of this variable to identify it during the
        build process and from other parts of the document, and also as a
        filename in case the filename property is empty.

        VarLib.
        """
        self.filename: str = filename
        """string, optional. Relative path to the variable font file, **as it is
        in the document**. The file may or may not exist.

        If not specified, the :attr:`name` will be used as a basename for the file.
        """
        self.axisSubsets: List[
            Union[RangeAxisSubsetDescriptor, ValueAxisSubsetDescriptor]
        ] = (axisSubsets or [])
        """Axis subsets to include in this variable font.

        If an axis is not mentioned, assume that we only want the default
        location of that axis (same as a :class:`ValueAxisSubsetDescriptor`).
        """
        self.lib: MutableMapping[str, Any] = lib or {}
        """Custom data associated with this variable font."""


class RangeAxisSubsetDescriptor(SimpleDescriptor):
    """Subset of a continuous axis to include in a variable font.

    .. versionadded:: 5.0
    """

    flavor = "axis-subset"
    _attrs = ("name", "userMinimum", "userDefault", "userMaximum")

    def __init__(
        self, *, name, userMinimum=-math.inf, userDefault=None, userMaximum=math.inf
    ):
        self.name: str = name
        """Name of the :class:`AxisDescriptor` to subset."""
        self.userMinimum: float = userMinimum
        """New minimum value of the axis in the target variable font.
        If not specified, assume the same minimum value as the full axis.
        (default = ``-math.inf``)
        """
        self.userDefault: Optional[float] = userDefault
        """New default value of the axis in the target variable font.
        If not specified, assume the same default value as the full axis.
        (default = ``None``)
        """
        self.userMaximum: float = userMaximum
        """New maximum value of the axis in the target variable font.
        If not specified, assume the same maximum value as the full axis.
        (default = ``math.inf``)
        """


class ValueAxisSubsetDescriptor(SimpleDescriptor):
    """Single value of a discrete or continuous axis to use in a variable font.

    .. versionadded:: 5.0
    """

    flavor = "axis-subset"
    _attrs = ("name", "userValue")

    def __init__(self, *, name, userValue):
        self.name: str = name
        """Name of the :class:`AxisDescriptor` or :class:`DiscreteAxisDescriptor`
        to "snapshot" or "freeze".
        """
        self.userValue: float = userValue
        """Value in user coordinates at which to freeze the given axis."""


class BaseDocWriter(object):
    _whiteSpace = "    "
    axisDescriptorClass = AxisDescriptor
    discreteAxisDescriptorClass = DiscreteAxisDescriptor
    axisLabelDescriptorClass = AxisLabelDescriptor
    axisMappingDescriptorClass = AxisMappingDescriptor
    locationLabelDescriptorClass = LocationLabelDescriptor
    ruleDescriptorClass = RuleDescriptor
    sourceDescriptorClass = SourceDescriptor
    variableFontDescriptorClass = VariableFontDescriptor
    valueAxisSubsetDescriptorClass = ValueAxisSubsetDescriptor
    rangeAxisSubsetDescriptorClass = RangeAxisSubsetDescriptor
    instanceDescriptorClass = InstanceDescriptor

    @classmethod
    def getAxisDecriptor(cls):
        return cls.axisDescriptorClass()

    @classmethod
    def getAxisMappingDescriptor(cls):
        return cls.axisMappingDescriptorClass()

    @classmethod
    def getSourceDescriptor(cls):
        return cls.sourceDescriptorClass()

    @classmethod
    def getInstanceDescriptor(cls):
        return cls.instanceDescriptorClass()

    @classmethod
    def getRuleDescriptor(cls):
        return cls.ruleDescriptorClass()

    def __init__(self, documentPath, documentObject: DesignSpaceDocument):
        self.path = documentPath
        self.documentObject = documentObject
        self.effectiveFormatTuple = self._getEffectiveFormatTuple()
        self.root = ET.Element("designspace")

    def write(self, pretty=True, encoding="UTF-8", xml_declaration=True):
        self.root.attrib["format"] = ".".join(str(i) for i in self.effectiveFormatTuple)

        if (
            self.documentObject.axes
            or self.documentObject.axisMappings
            or self.documentObject.elidedFallbackName is not None
        ):
            axesElement = ET.Element("axes")
            if self.documentObject.elidedFallbackName is not None:
                axesElement.attrib["elidedfallbackname"] = (
                    self.documentObject.elidedFallbackName
                )
            self.root.append(axesElement)
        for axisObject in self.documentObject.axes:
            self._addAxis(axisObject)

        if self.documentObject.axisMappings:
            mappingsElement = None
            lastGroup = object()
            for mappingObject in self.documentObject.axisMappings:
                if getattr(mappingObject, "groupDescription", None) != lastGroup:
                    if mappingsElement is not None:
                        self.root.findall(".axes")[0].append(mappingsElement)
                    lastGroup = getattr(mappingObject, "groupDescription", None)
                    mappingsElement = ET.Element("mappings")
                    if lastGroup is not None:
                        mappingsElement.attrib["description"] = lastGroup
                self._addAxisMapping(mappingsElement, mappingObject)
            if mappingsElement is not None:
                self.root.findall(".axes")[0].append(mappingsElement)

        if self.documentObject.locationLabels:
            labelsElement = ET.Element("labels")
            for labelObject in self.documentObject.locationLabels:
                self._addLocationLabel(labelsElement, labelObject)
            self.root.append(labelsElement)

        if self.documentObject.rules:
            if getattr(self.documentObject, "rulesProcessingLast", False):
                attributes = {"processing": "last"}
            else:
                attributes = {}
            self.root.append(ET.Element("rules", attributes))
        for ruleObject in self.documentObject.rules:
            self._addRule(ruleObject)

        if self.documentObject.sources:
            self.root.append(ET.Element("sources"))
        for sourceObject in self.documentObject.sources:
            self._addSource(sourceObject)

        if self.documentObject.variableFonts:
            variableFontsElement = ET.Element("variable-fonts")
            for variableFont in self.documentObject.variableFonts:
                self._addVariableFont(variableFontsElement, variableFont)
            self.root.append(variableFontsElement)

        if self.documentObject.instances:
            self.root.append(ET.Element("instances"))
        for instanceObject in self.documentObject.instances:
            self._addInstance(instanceObject)

        if self.documentObject.lib:
            self._addLib(self.root, self.documentObject.lib, 2)

        tree = ET.ElementTree(self.root)
        tree.write(
            self.path,
            encoding=encoding,
            method="xml",
            xml_declaration=xml_declaration,
            pretty_print=pretty,
        )

    def _getEffectiveFormatTuple(self):
        """Try to use the version specified in the document, or a sufficiently
        recent version to be able to encode what the document contains.
        """
        minVersion = self.documentObject.formatTuple
        if (
            any(
                hasattr(axis, "values")
                or axis.axisOrdering is not None
                or axis.axisLabels
                for axis in self.documentObject.axes
            )
            or self.documentObject.locationLabels
            or any(source.localisedFamilyName for source in self.documentObject.sources)
            or self.documentObject.variableFonts
            or any(
                instance.locationLabel or instance.userLocation
                for instance in self.documentObject.instances
            )
        ):
            if minVersion < (5, 0):
                minVersion = (5, 0)
        if self.documentObject.axisMappings:
            if minVersion < (5, 1):
                minVersion = (5, 1)
        return minVersion

    def _makeLocationElement(self, locationObject, name=None):
        """Convert Location dict to a locationElement."""
        locElement = ET.Element("location")
        if name is not None:
            locElement.attrib["name"] = name
        validatedLocation = self.documentObject.newDefaultLocation()
        for axisName, axisValue in locationObject.items():
            if axisName in validatedLocation:
                # only accept values we know
                validatedLocation[axisName] = axisValue
        for dimensionName, dimensionValue in validatedLocation.items():
            dimElement = ET.Element("dimension")
            dimElement.attrib["name"] = dimensionName
            if type(dimensionValue) == tuple:
                dimElement.attrib["xvalue"] = self.intOrFloat(dimensionValue[0])
                dimElement.attrib["yvalue"] = self.intOrFloat(dimensionValue[1])
            else:
                dimElement.attrib["xvalue"] = self.intOrFloat(dimensionValue)
            locElement.append(dimElement)
        return locElement, validatedLocation

    def intOrFloat(self, num):
        if int(num) == num:
            return "%d" % num
        return ("%f" % num).rstrip("0").rstrip(".")

    def _addRule(self, ruleObject):
        # if none of the conditions have minimum or maximum values, do not add the rule.
        ruleElement = ET.Element("rule")
        if ruleObject.name is not None:
            ruleElement.attrib["name"] = ruleObject.name
        for conditions in ruleObject.conditionSets:
            conditionsetElement = ET.Element("conditionset")
            for cond in conditions:
                if cond.get("minimum") is None and cond.get("maximum") is None:
                    # neither is defined, don't add this condition
                    continue
                conditionElement = ET.Element("condition")
                conditionElement.attrib["name"] = cond.get("name")
                if cond.get("minimum") is not None:
                    conditionElement.attrib["minimum"] = self.intOrFloat(
                        cond.get("minimum")
                    )
                if cond.get("maximum") is not None:
                    conditionElement.attrib["maximum"] = self.intOrFloat(
                        cond.get("maximum")
                    )
                conditionsetElement.append(conditionElement)
            if len(conditionsetElement):
                ruleElement.append(conditionsetElement)
        for sub in ruleObject.subs:
            subElement = ET.Element("sub")
            subElement.attrib["name"] = sub[0]
            subElement.attrib["with"] = sub[1]
            ruleElement.append(subElement)
        if len(ruleElement):
            self.root.findall(".rules")[0].append(ruleElement)

    def _addAxis(self, axisObject):
        axisElement = ET.Element("axis")
        axisElement.attrib["tag"] = axisObject.tag
        axisElement.attrib["name"] = axisObject.name
        self._addLabelNames(axisElement, axisObject.labelNames)
        if axisObject.map:
            for inputValue, outputValue in axisObject.map:
                mapElement = ET.Element("map")
                mapElement.attrib["input"] = self.intOrFloat(inputValue)
                mapElement.attrib["output"] = self.intOrFloat(outputValue)
                axisElement.append(mapElement)
        if axisObject.axisOrdering is not None or axisObject.axisLabels:
            labelsElement = ET.Element("labels")
            if axisObject.axisOrdering is not None:
                labelsElement.attrib["ordering"] = str(axisObject.axisOrdering)
            for label in axisObject.axisLabels:
                self._addAxisLabel(labelsElement, label)
            axisElement.append(labelsElement)
        if hasattr(axisObject, "minimum"):
            axisElement.attrib["minimum"] = self.intOrFloat(axisObject.minimum)
            axisElement.attrib["maximum"] = self.intOrFloat(axisObject.maximum)
        elif hasattr(axisObject, "values"):
            axisElement.attrib["values"] = " ".join(
                self.intOrFloat(v) for v in axisObject.values
            )
        axisElement.attrib["default"] = self.intOrFloat(axisObject.default)
        if axisObject.hidden:
            axisElement.attrib["hidden"] = "1"
        self.root.findall(".axes")[0].append(axisElement)

    def _addAxisMapping(self, mappingsElement, mappingObject):
        mappingElement = ET.Element("mapping")
        if getattr(mappingObject, "description", None) is not None:
            mappingElement.attrib["description"] = mappingObject.description
        for what in ("inputLocation", "outputLocation"):
            whatObject = getattr(mappingObject, what, None)
            if whatObject is None:
                continue
            whatElement = ET.Element(what[:-8])
            mappingElement.append(whatElement)

            for name, value in whatObject.items():
                dimensionElement = ET.Element("dimension")
                dimensionElement.attrib["name"] = name
                dimensionElement.attrib["xvalue"] = self.intOrFloat(value)
                whatElement.append(dimensionElement)

        mappingsElement.append(mappingElement)

    def _addAxisLabel(
        self, axisElement: ET.Element, label: AxisLabelDescriptor
    ) -> None:
        labelElement = ET.Element("label")
        labelElement.attrib["uservalue"] = self.intOrFloat(label.userValue)
        if label.userMinimum is not None:
            labelElement.attrib["userminimum"] = self.intOrFloat(label.userMinimum)
        if label.userMaximum is not None:
            labelElement.attrib["usermaximum"] = self.intOrFloat(label.userMaximum)
        labelElement.attrib["name"] = label.name
        if label.elidable:
            labelElement.attrib["elidable"] = "true"
        if label.olderSibling:
            labelElement.attrib["oldersibling"] = "true"
        if label.linkedUserValue is not None:
            labelElement.attrib["linkeduservalue"] = self.intOrFloat(
                label.linkedUserValue
            )
        self._addLabelNames(labelElement, label.labelNames)
        axisElement.append(labelElement)

    def _addLabelNames(self, parentElement, labelNames):
        for languageCode, labelName in sorted(labelNames.items()):
            languageElement = ET.Element("labelname")
            languageElement.attrib[XML_LANG] = languageCode
            languageElement.text = labelName
            parentElement.append(languageElement)

    def _addLocationLabel(
        self, parentElement: ET.Element, label: LocationLabelDescriptor
    ) -> None:
        labelElement = ET.Element("label")
        labelElement.attrib["name"] = label.name
        if label.elidable:
            labelElement.attrib["elidable"] = "true"
        if label.olderSibling:
            labelElement.attrib["oldersibling"] = "true"
        self._addLabelNames(labelElement, label.labelNames)
        self._addLocationElement(labelElement, userLocation=label.userLocation)
        parentElement.append(labelElement)

    def _addLocationElement(
        self,
        parentElement,
        *,
        designLocation: AnisotropicLocationDict = None,
        userLocation: SimpleLocationDict = None,
    ):
        locElement = ET.Element("location")
        for axis in self.documentObject.axes:
            if designLocation is not None and axis.name in designLocation:
                dimElement = ET.Element("dimension")
                dimElement.attrib["name"] = axis.name
                value = designLocation[axis.name]
                if isinstance(value, tuple):
                    dimElement.attrib["xvalue"] = self.intOrFloat(value[0])
                    dimElement.attrib["yvalue"] = self.intOrFloat(value[1])
                else:
                    dimElement.attrib["xvalue"] = self.intOrFloat(value)
                locElement.append(dimElement)
            elif userLocation is not None and axis.name in userLocation:
                dimElement = ET.Element("dimension")
                dimElement.attrib["name"] = axis.name
                value = userLocation[axis.name]
                dimElement.attrib["uservalue"] = self.intOrFloat(value)
                locElement.append(dimElement)
        if len(locElement) > 0:
            parentElement.append(locElement)

    def _addInstance(self, instanceObject):
        instanceElement = ET.Element("instance")
        if instanceObject.name is not None:
            instanceElement.attrib["name"] = instanceObject.name
        if instanceObject.locationLabel is not None:
            instanceElement.attrib["location"] = instanceObject.locationLabel
        if instanceObject.familyName is not None:
            instanceElement.attrib["familyname"] = instanceObject.familyName
        if instanceObject.styleName is not None:
            instanceElement.attrib["stylename"] = instanceObject.styleName
        # add localisations
        if instanceObject.localisedStyleName:
            languageCodes = list(instanceObject.localisedStyleName.keys())
            languageCodes.sort()
            for code in languageCodes:
                if code == "en":
                    continue  # already stored in the element attribute
                localisedStyleNameElement = ET.Element("stylename")
                localisedStyleNameElement.attrib[XML_LANG] = code
                localisedStyleNameElement.text = instanceObject.getStyleName(code)
                instanceElement.append(localisedStyleNameElement)
        if instanceObject.localisedFamilyName:
            languageCodes = list(instanceObject.localisedFamilyName.keys())
            languageCodes.sort()
            for code in languageCodes:
                if code == "en":
                    continue  # already stored in the element attribute
                localisedFamilyNameElement = ET.Element("familyname")
                localisedFamilyNameElement.attrib[XML_LANG] = code
                localisedFamilyNameElement.text = instanceObject.getFamilyName(code)
                instanceElement.append(localisedFamilyNameElement)
        if instanceObject.localisedStyleMapStyleName:
            languageCodes = list(instanceObject.localisedStyleMapStyleName.keys())
            languageCodes.sort()
            for code in languageCodes:
                if code == "en":
                    continue
                localisedStyleMapStyleNameElement = ET.Element("stylemapstylename")
                localisedStyleMapStyleNameElement.attrib[XML_LANG] = code
                localisedStyleMapStyleNameElement.text = (
                    instanceObject.getStyleMapStyleName(code)
                )
                instanceElement.append(localisedStyleMapStyleNameElement)
        if instanceObject.localisedStyleMapFamilyName:
            languageCodes = list(instanceObject.localisedStyleMapFamilyName.keys())
            languageCodes.sort()
            for code in languageCodes:
                if code == "en":
                    continue
                localisedStyleMapFamilyNameElement = ET.Element("stylemapfamilyname")
                localisedStyleMapFamilyNameElement.attrib[XML_LANG] = code
                localisedStyleMapFamilyNameElement.text = (
                    instanceObject.getStyleMapFamilyName(code)
                )
                instanceElement.append(localisedStyleMapFamilyNameElement)

        if self.effectiveFormatTuple >= (5, 0):
            if instanceObject.locationLabel is None:
                self._addLocationElement(
                    instanceElement,
                    designLocation=instanceObject.designLocation,
                    userLocation=instanceObject.userLocation,
                )
        else:
            # Pre-version 5.0 code was validating and filling in the location
            # dict while writing it out, as preserved below.
            if instanceObject.location is not None:
                locationElement, instanceObject.location = self._makeLocationElement(
                    instanceObject.location
                )
                instanceElement.append(locationElement)
        if instanceObject.filename is not None:
            instanceElement.attrib["filename"] = instanceObject.filename
        if instanceObject.postScriptFontName is not None:
            instanceElement.attrib["postscriptfontname"] = (
                instanceObject.postScriptFontName
            )
        if instanceObject.styleMapFamilyName is not None:
            instanceElement.attrib["stylemapfamilyname"] = (
                instanceObject.styleMapFamilyName
            )
        if instanceObject.styleMapStyleName is not None:
            instanceElement.attrib["stylemapstylename"] = (
                instanceObject.styleMapStyleName
            )
        if self.effectiveFormatTuple < (5, 0):
            # Deprecated members as of version 5.0
            if instanceObject.glyphs:
                if instanceElement.findall(".glyphs") == []:
                    glyphsElement = ET.Element("glyphs")
                    instanceElement.append(glyphsElement)
                glyphsElement = instanceElement.findall(".glyphs")[0]
                for glyphName, data in sorted(instanceObject.glyphs.items()):
                    glyphElement = self._writeGlyphElement(
                        instanceElement, instanceObject, glyphName, data
                    )
                    glyphsElement.append(glyphElement)
            if instanceObject.kerning:
                kerningElement = ET.Element("kerning")
                instanceElement.append(kerningElement)
            if instanceObject.info:
                infoElement = ET.Element("info")
                instanceElement.append(infoElement)
        self._addLib(instanceElement, instanceObject.lib, 4)
        self.root.findall(".instances")[0].append(instanceElement)

    def _addSource(self, sourceObject):
        sourceElement = ET.Element("source")
        if sourceObject.filename is not None:
            sourceElement.attrib["filename"] = sourceObject.filename
        if sourceObject.name is not None:
            if sourceObject.name.find("temp_master") != 0:
                # do not save temporary source names
                sourceElement.attrib["name"] = sourceObject.name
        if sourceObject.familyName is not None:
            sourceElement.attrib["familyname"] = sourceObject.familyName
        if sourceObject.styleName is not None:
            sourceElement.attrib["stylename"] = sourceObject.styleName
        if sourceObject.layerName is not None:
            sourceElement.attrib["layer"] = sourceObject.layerName
        if sourceObject.localisedFamilyName:
            languageCodes = list(sourceObject.localisedFamilyName.keys())
            languageCodes.sort()
            for code in languageCodes:
                if code == "en":
                    continue  # already stored in the element attribute
                localisedFamilyNameElement = ET.Element("familyname")
                localisedFamilyNameElement.attrib[XML_LANG] = code
                localisedFamilyNameElement.text = sourceObject.getFamilyName(code)
                sourceElement.append(localisedFamilyNameElement)
        if sourceObject.copyLib:
            libElement = ET.Element("lib")
            libElement.attrib["copy"] = "1"
            sourceElement.append(libElement)
        if sourceObject.copyGroups:
            groupsElement = ET.Element("groups")
            groupsElement.attrib["copy"] = "1"
            sourceElement.append(groupsElement)
        if sourceObject.copyFeatures:
            featuresElement = ET.Element("features")
            featuresElement.attrib["copy"] = "1"
            sourceElement.append(featuresElement)
        if sourceObject.copyInfo or sourceObject.muteInfo:
            infoElement = ET.Element("info")
            if sourceObject.copyInfo:
                infoElement.attrib["copy"] = "1"
            if sourceObject.muteInfo:
                infoElement.attrib["mute"] = "1"
            sourceElement.append(infoElement)
        if sourceObject.muteKerning:
            kerningElement = ET.Element("kerning")
            kerningElement.attrib["mute"] = "1"
            sourceElement.append(kerningElement)
        if sourceObject.mutedGlyphNames:
            for name in sourceObject.mutedGlyphNames:
                glyphElement = ET.Element("glyph")
                glyphElement.attrib["name"] = name
                glyphElement.attrib["mute"] = "1"
                sourceElement.append(glyphElement)
        if self.effectiveFormatTuple >= (5, 0):
            self._addLocationElement(
                sourceElement, designLocation=sourceObject.location
            )
        else:
            # Pre-version 5.0 code was validating and filling in the location
            # dict while writing it out, as preserved below.
            locationElement, sourceObject.location = self._makeLocationElement(
                sourceObject.location
            )
            sourceElement.append(locationElement)
        self.root.findall(".sources")[0].append(sourceElement)

    def _addVariableFont(
        self, parentElement: ET.Element, vf: VariableFontDescriptor
    ) -> None:
        vfElement = ET.Element("variable-font")
        vfElement.attrib["name"] = vf.name
        if vf.filename is not None:
            vfElement.attrib["filename"] = vf.filename
        if vf.axisSubsets:
            subsetsElement = ET.Element("axis-subsets")
            for subset in vf.axisSubsets:
                subsetElement = ET.Element("axis-subset")
                subsetElement.attrib["name"] = subset.name
                # Mypy doesn't support narrowing union types via hasattr()
                # https://mypy.readthedocs.io/en/stable/type_narrowing.html
                # TODO(Python 3.10): use TypeGuard
                if hasattr(subset, "userMinimum"):
                    subset = cast(RangeAxisSubsetDescriptor, subset)
                    if subset.userMinimum != -math.inf:
                        subsetElement.attrib["userminimum"] = self.intOrFloat(
                            subset.userMinimum
                        )
                    if subset.userMaximum != math.inf:
                        subsetElement.attrib["usermaximum"] = self.intOrFloat(
                            subset.userMaximum
                        )
                    if subset.userDefault is not None:
                        subsetElement.attrib["userdefault"] = self.intOrFloat(
                            subset.userDefault
                        )
                elif hasattr(subset, "userValue"):
                    subset = cast(ValueAxisSubsetDescriptor, subset)
                    subsetElement.attrib["uservalue"] = self.intOrFloat(
                        subset.userValue
                    )
                subsetsElement.append(subsetElement)
            vfElement.append(subsetsElement)
        self._addLib(vfElement, vf.lib, 4)
        parentElement.append(vfElement)

    def _addLib(self, parentElement: ET.Element, data: Any, indent_level: int) -> None:
        if not data:
            return
        libElement = ET.Element("lib")
        libElement.append(plistlib.totree(data, indent_level=indent_level))
        parentElement.append(libElement)

    def _writeGlyphElement(self, instanceElement, instanceObject, glyphName, data):
        glyphElement = ET.Element("glyph")
        if data.get("mute"):
            glyphElement.attrib["mute"] = "1"
        if data.get("unicodes") is not None:
            glyphElement.attrib["unicode"] = " ".join(
                [hex(u) for u in data.get("unicodes")]
            )
        if data.get("instanceLocation") is not None:
            locationElement, data["instanceLocation"] = self._makeLocationElement(
                data.get("instanceLocation")
            )
            glyphElement.append(locationElement)
        if glyphName is not None:
            glyphElement.attrib["name"] = glyphName
        if data.get("note") is not None:
            noteElement = ET.Element("note")
            noteElement.text = data.get("note")
            glyphElement.append(noteElement)
        if data.get("masters") is not None:
            mastersElement = ET.Element("masters")
            for m in data.get("masters"):
                masterElement = ET.Element("master")
                if m.get("glyphName") is not None:
                    masterElement.attrib["glyphname"] = m.get("glyphName")
                if m.get("font") is not None:
                    masterElement.attrib["source"] = m.get("font")
                if m.get("location") is not None:
                    locationElement, m["location"] = self._makeLocationElement(
                        m.get("location")
                    )
                    masterElement.append(locationElement)
                mastersElement.append(masterElement)
            glyphElement.append(mastersElement)
        return glyphElement


class BaseDocReader(LogMixin):
    axisDescriptorClass = AxisDescriptor
    discreteAxisDescriptorClass = DiscreteAxisDescriptor
    axisLabelDescriptorClass = AxisLabelDescriptor
    axisMappingDescriptorClass = AxisMappingDescriptor
    locationLabelDescriptorClass = LocationLabelDescriptor
    ruleDescriptorClass = RuleDescriptor
    sourceDescriptorClass = SourceDescriptor
    variableFontsDescriptorClass = VariableFontDescriptor
    valueAxisSubsetDescriptorClass = ValueAxisSubsetDescriptor
    rangeAxisSubsetDescriptorClass = RangeAxisSubsetDescriptor
    instanceDescriptorClass = InstanceDescriptor

    def __init__(self, documentPath, documentObject):
        self.path = documentPath
        self.documentObject = documentObject
        tree = ET.parse(self.path)
        self.root = tree.getroot()
        self.documentObject.formatVersion = self.root.attrib.get("format", "3.0")
        self._axes = []
        self.rules = []
        self.sources = []
        self.instances = []
        self.axisDefaults = {}
        self._strictAxisNames = True

    @classmethod
    def fromstring(cls, string, documentObject):
        f = BytesIO(tobytes(string, encoding="utf-8"))
        self = cls(f, documentObject)
        self.path = None
        return self

    def read(self):
        self.readAxes()
        self.readLabels()
        self.readRules()
        self.readVariableFonts()
        self.readSources()
        self.readInstances()
        self.readLib()

    def readRules(self):
        # we also need to read any conditions that are outside of a condition set.
        rules = []
        rulesElement = self.root.find(".rules")
        if rulesElement is not None:
            processingValue = rulesElement.attrib.get("processing", "first")
            if processingValue not in {"first", "last"}:
                raise DesignSpaceDocumentError(
                    "<rules> processing attribute value is not valid: %r, "
                    "expected 'first' or 'last'" % processingValue
                )
            self.documentObject.rulesProcessingLast = processingValue == "last"
        for ruleElement in self.root.findall(".rules/rule"):
            ruleObject = self.ruleDescriptorClass()
            ruleName = ruleObject.name = ruleElement.attrib.get("name")
            # read any stray conditions outside a condition set
            externalConditions = self._readConditionElements(
                ruleElement,
                ruleName,
            )
            if externalConditions:
                ruleObject.conditionSets.append(externalConditions)
                self.log.info(
                    "Found stray rule conditions outside a conditionset. "
                    "Wrapped them in a new conditionset."
                )
            # read the conditionsets
            for conditionSetElement in ruleElement.findall(".conditionset"):
                conditionSet = self._readConditionElements(
                    conditionSetElement,
                    ruleName,
                )
                if conditionSet is not None:
                    ruleObject.conditionSets.append(conditionSet)
            for subElement in ruleElement.findall(".sub"):
                a = subElement.attrib["name"]
                b = subElement.attrib["with"]
                ruleObject.subs.append((a, b))
            rules.append(ruleObject)
        self.documentObject.rules = rules

    def _readConditionElements(self, parentElement, ruleName=None):
        cds = []
        for conditionElement in parentElement.findall(".condition"):
            cd = {}
            cdMin = conditionElement.attrib.get("minimum")
            if cdMin is not None:
                cd["minimum"] = float(cdMin)
            else:
                # will allow these to be None, assume axis.minimum
                cd["minimum"] = None
            cdMax = conditionElement.attrib.get("maximum")
            if cdMax is not None:
                cd["maximum"] = float(cdMax)
            else:
                # will allow these to be None, assume axis.maximum
                cd["maximum"] = None
            cd["name"] = conditionElement.attrib.get("name")
            # # test for things
            if cd.get("minimum") is None and cd.get("maximum") is None:
                raise DesignSpaceDocumentError(
                    "condition missing required minimum or maximum in rule"
                    + (" '%s'" % ruleName if ruleName is not None else "")
                )
            cds.append(cd)
        return cds

    def readAxes(self):
        # read the axes elements, including the warp map.
        axesElement = self.root.find(".axes")
        if axesElement is not None and "elidedfallbackname" in axesElement.attrib:
            self.documentObject.elidedFallbackName = axesElement.attrib[
                "elidedfallbackname"
            ]
        axisElements = self.root.findall(".axes/axis")
        if not axisElements:
            return
        for axisElement in axisElements:
            if (
                self.documentObject.formatTuple >= (5, 0)
                and "values" in axisElement.attrib
            ):
                axisObject = self.discreteAxisDescriptorClass()
                axisObject.values = [
                    float(s) for s in axisElement.attrib["values"].split(" ")
                ]
            else:
                axisObject = self.axisDescriptorClass()
                axisObject.minimum = float(axisElement.attrib.get("minimum"))
                axisObject.maximum = float(axisElement.attrib.get("maximum"))
            axisObject.default = float(axisElement.attrib.get("default"))
            axisObject.name = axisElement.attrib.get("name")
            if axisElement.attrib.get("hidden", False):
                axisObject.hidden = True
            axisObject.tag = axisElement.attrib.get("tag")
            for mapElement in axisElement.findall("map"):
                a = float(mapElement.attrib["input"])
                b = float(mapElement.attrib["output"])
                axisObject.map.append((a, b))
            for labelNameElement in axisElement.findall("labelname"):
                # Note: elementtree reads the "xml:lang" attribute name as
                # '{http://www.w3.org/XML/1998/namespace}lang'
                for key, lang in labelNameElement.items():
                    if key == XML_LANG:
                        axisObject.labelNames[lang] = tostr(labelNameElement.text)
            labelElement = axisElement.find(".labels")
            if labelElement is not None:
                if "ordering" in labelElement.attrib:
                    axisObject.axisOrdering = int(labelElement.attrib["ordering"])
                for label in labelElement.findall(".label"):
                    axisObject.axisLabels.append(self.readAxisLabel(label))
            self.documentObject.axes.append(axisObject)
            self.axisDefaults[axisObject.name] = axisObject.default

        self.documentObject.axisMappings = []
        for mappingsElement in self.root.findall(".axes/mappings"):
            groupDescription = mappingsElement.attrib.get("description")
            for mappingElement in mappingsElement.findall("mapping"):
                description = mappingElement.attrib.get("description")
                inputElement = mappingElement.find("input")
                outputElement = mappingElement.find("output")
                inputLoc = {}
                outputLoc = {}
                for dimElement in inputElement.findall(".dimension"):
                    name = dimElement.attrib["name"]
                    value = float(dimElement.attrib["xvalue"])
                    inputLoc[name] = value
                for dimElement in outputElement.findall(".dimension"):
                    name = dimElement.attrib["name"]
                    value = float(dimElement.attrib["xvalue"])
                    outputLoc[name] = value
                axisMappingObject = self.axisMappingDescriptorClass(
                    inputLocation=inputLoc,
                    outputLocation=outputLoc,
                    description=description,
                    groupDescription=groupDescription,
                )
                self.documentObject.axisMappings.append(axisMappingObject)

    def readAxisLabel(self, element: ET.Element):
        xml_attrs = {
            "userminimum",
            "uservalue",
            "usermaximum",
            "name",
            "elidable",
            "oldersibling",
            "linkeduservalue",
        }
        unknown_attrs = set(element.attrib) - xml_attrs
        if unknown_attrs:
            raise DesignSpaceDocumentError(
                f"label element contains unknown attributes: {', '.join(unknown_attrs)}"
            )

        name = element.get("name")
        if name is None:
            raise DesignSpaceDocumentError("label element must have a name attribute.")
        valueStr = element.get("uservalue")
        if valueStr is None:
            raise DesignSpaceDocumentError(
                "label element must have a uservalue attribute."
            )
        value = float(valueStr)
        minimumStr = element.get("userminimum")
        minimum = float(minimumStr) if minimumStr is not None else None
        maximumStr = element.get("usermaximum")
        maximum = float(maximumStr) if maximumStr is not None else None
        linkedValueStr = element.get("linkeduservalue")
        linkedValue = float(linkedValueStr) if linkedValueStr is not None else None
        elidable = True if element.get("elidable") == "true" else False
        olderSibling = True if element.get("oldersibling") == "true" else False
        labelNames = {
            lang: label_name.text or ""
            for label_name in element.findall("labelname")
            for attr, lang in label_name.items()
            if attr == XML_LANG
            # Note: elementtree reads the "xml:lang" attribute name as
            # '{http://www.w3.org/XML/1998/namespace}lang'
        }
        return self.axisLabelDescriptorClass(
            name=name,
            userValue=value,
            userMinimum=minimum,
            userMaximum=maximum,
            elidable=elidable,
            olderSibling=olderSibling,
            linkedUserValue=linkedValue,
            labelNames=labelNames,
        )

    def readLabels(self):
        if self.documentObject.formatTuple < (5, 0):
            return

        xml_attrs = {"name", "elidable", "oldersibling"}
        for labelElement in self.root.findall(".labels/label"):
            unknown_attrs = set(labelElement.attrib) - xml_attrs
            if unknown_attrs:
                raise DesignSpaceDocumentError(
                    f"Label element contains unknown attributes: {', '.join(unknown_attrs)}"
                )

            name = labelElement.get("name")
            if name is None:
                raise DesignSpaceDocumentError(
                    "label element must have a name attribute."
                )
            designLocation, userLocation = self.locationFromElement(labelElement)
            if designLocation:
                raise DesignSpaceDocumentError(
                    f'<label> element "{name}" must only have user locations (using uservalue="").'
                )
            elidable = True if labelElement.get("elidable") == "true" else False
            olderSibling = True if labelElement.get("oldersibling") == "true" else False
            labelNames = {
                lang: label_name.text or ""
                for label_name in labelElement.findall("labelname")
                for attr, lang in label_name.items()
                if attr == XML_LANG
                # Note: elementtree reads the "xml:lang" attribute name as
                # '{http://www.w3.org/XML/1998/namespace}lang'
            }
            locationLabel = self.locationLabelDescriptorClass(
                name=name,
                userLocation=userLocation,
                elidable=elidable,
                olderSibling=olderSibling,
                labelNames=labelNames,
            )
            self.documentObject.locationLabels.append(locationLabel)

    def readVariableFonts(self):
        if self.documentObject.formatTuple < (5, 0):
            return

        xml_attrs = {"name", "filename"}
        for variableFontElement in self.root.findall(".variable-fonts/variable-font"):
            unknown_attrs = set(variableFontElement.attrib) - xml_attrs
            if unknown_attrs:
                raise DesignSpaceDocumentError(
                    f"variable-font element contains unknown attributes: {', '.join(unknown_attrs)}"
                )

            name = variableFontElement.get("name")
            if name is None:
                raise DesignSpaceDocumentError(
                    "variable-font element must have a name attribute."
                )

            filename = variableFontElement.get("filename")

            axisSubsetsElement = variableFontElement.find(".axis-subsets")
            if axisSubsetsElement is None:
                raise DesignSpaceDocumentError(
                    "variable-font element must contain an axis-subsets element."
                )
            axisSubsets = []
            for axisSubset in axisSubsetsElement.iterfind(".axis-subset"):
                axisSubsets.append(self.readAxisSubset(axisSubset))

            lib = None
            libElement = variableFontElement.find(".lib")
            if libElement is not None:
                lib = plistlib.fromtree(libElement[0])

            variableFont = self.variableFontsDescriptorClass(
                name=name,
                filename=filename,
                axisSubsets=axisSubsets,
                lib=lib,
            )
            self.documentObject.variableFonts.append(variableFont)

    def readAxisSubset(self, element: ET.Element):
        if "uservalue" in element.attrib:
            xml_attrs = {"name", "uservalue"}
            unknown_attrs = set(element.attrib) - xml_attrs
            if unknown_attrs:
                raise DesignSpaceDocumentError(
                    f"axis-subset element contains unknown attributes: {', '.join(unknown_attrs)}"
                )

            name = element.get("name")
            if name is None:
                raise DesignSpaceDocumentError(
                    "axis-subset element must have a name attribute."
                )
            userValueStr = element.get("uservalue")
            if userValueStr is None:
                raise DesignSpaceDocumentError(
                    "The axis-subset element for a discrete subset must have a uservalue attribute."
                )
            userValue = float(userValueStr)

            return self.valueAxisSubsetDescriptorClass(name=name, userValue=userValue)
        else:
            xml_attrs = {"name", "userminimum", "userdefault", "usermaximum"}
            unknown_attrs = set(element.attrib) - xml_attrs
            if unknown_attrs:
                raise DesignSpaceDocumentError(
                    f"axis-subset element contains unknown attributes: {', '.join(unknown_attrs)}"
                )

            name = element.get("name")
            if name is None:
                raise DesignSpaceDocumentError(
                    "axis-subset element must have a name attribute."
                )

            userMinimum = element.get("userminimum")
            userDefault = element.get("userdefault")
            userMaximum = element.get("usermaximum")
            if (
                userMinimum is not None
                and userDefault is not None
                and userMaximum is not None
            ):
                return self.rangeAxisSubsetDescriptorClass(
                    name=name,
                    userMinimum=float(userMinimum),
                    userDefault=float(userDefault),
                    userMaximum=float(userMaximum),
                )
            if all(v is None for v in (userMinimum, userDefault, userMaximum)):
                return self.rangeAxisSubsetDescriptorClass(name=name)

            raise DesignSpaceDocumentError(
                "axis-subset element must have min/max/default values or none at all."
            )

    def readSources(self):
        for sourceCount, sourceElement in enumerate(
            self.root.findall(".sources/source")
        ):
            filename = sourceElement.attrib.get("filename")
            if filename is not None and self.path is not None:
                sourcePath = os.path.abspath(
                    os.path.join(os.path.dirname(self.path), filename)
                )
            else:
                sourcePath = None
            sourceName = sourceElement.attrib.get("name")
            if sourceName is None:
                # add a temporary source name
                sourceName = "temp_master.%d" % (sourceCount)
            sourceObject = self.sourceDescriptorClass()
            sourceObject.path = sourcePath  # absolute path to the ufo source
            sourceObject.filename = filename  # path as it is stored in the document
            sourceObject.name = sourceName
            familyName = sourceElement.attrib.get("familyname")
            if familyName is not None:
                sourceObject.familyName = familyName
            styleName = sourceElement.attrib.get("stylename")
            if styleName is not None:
                sourceObject.styleName = styleName
            for familyNameElement in sourceElement.findall("familyname"):
                for key, lang in familyNameElement.items():
                    if key == XML_LANG:
                        familyName = familyNameElement.text
                        sourceObject.setFamilyName(familyName, lang)
            designLocation, userLocation = self.locationFromElement(sourceElement)
            if userLocation:
                raise DesignSpaceDocumentError(
                    f'<source> element "{sourceName}" must only have design locations (using xvalue="").'
                )
            sourceObject.location = designLocation
            layerName = sourceElement.attrib.get("layer")
            if layerName is not None:
                sourceObject.layerName = layerName
            for libElement in sourceElement.findall(".lib"):
                if libElement.attrib.get("copy") == "1":
                    sourceObject.copyLib = True
            for groupsElement in sourceElement.findall(".groups"):
                if groupsElement.attrib.get("copy") == "1":
                    sourceObject.copyGroups = True
            for infoElement in sourceElement.findall(".info"):
                if infoElement.attrib.get("copy") == "1":
                    sourceObject.copyInfo = True
                if infoElement.attrib.get("mute") == "1":
                    sourceObject.muteInfo = True
            for featuresElement in sourceElement.findall(".features"):
                if featuresElement.attrib.get("copy") == "1":
                    sourceObject.copyFeatures = True
            for glyphElement in sourceElement.findall(".glyph"):
                glyphName = glyphElement.attrib.get("name")
                if glyphName is None:
                    continue
                if glyphElement.attrib.get("mute") == "1":
                    sourceObject.mutedGlyphNames.append(glyphName)
            for kerningElement in sourceElement.findall(".kerning"):
                if kerningElement.attrib.get("mute") == "1":
                    sourceObject.muteKerning = True
            self.documentObject.sources.append(sourceObject)

    def locationFromElement(self, element):
        """Read a nested ``<location>`` element inside the given ``element``.

        .. versionchanged:: 5.0
           Return a tuple of (designLocation, userLocation)
        """
        elementLocation = (None, None)
        for locationElement in element.findall(".location"):
            elementLocation = self.readLocationElement(locationElement)
            break
        return elementLocation

    def readLocationElement(self, locationElement):
        """Read a ``<location>`` element.

        .. versionchanged:: 5.0
           Return a tuple of (designLocation, userLocation)
        """
        if self._strictAxisNames and not self.documentObject.axes:
            raise DesignSpaceDocumentError("No axes defined")
        userLoc = {}
        designLoc = {}
        for dimensionElement in locationElement.findall(".dimension"):
            dimName = dimensionElement.attrib.get("name")
            if self._strictAxisNames and dimName not in self.axisDefaults:
                # In case the document contains no axis definitions,
                self.log.warning('Location with undefined axis: "%s".', dimName)
                continue
            userValue = xValue = yValue = None
            try:
                userValue = dimensionElement.attrib.get("uservalue")
                if userValue is not None:
                    userValue = float(userValue)
            except ValueError:
                self.log.warning(
                    "ValueError in readLocation userValue %3.3f", userValue
                )
            try:
                xValue = dimensionElement.attrib.get("xvalue")
                if xValue is not None:
                    xValue = float(xValue)
            except ValueError:
                self.log.warning("ValueError in readLocation xValue %3.3f", xValue)
            try:
                yValue = dimensionElement.attrib.get("yvalue")
                if yValue is not None:
                    yValue = float(yValue)
            except ValueError:
                self.log.warning("ValueError in readLocation yValue %3.3f", yValue)
            if userValue is None == xValue is None:
                raise DesignSpaceDocumentError(
                    f'Exactly one of uservalue="" or xvalue="" must be provided for location dimension "{dimName}"'
                )
            if yValue is not None:
                if xValue is None:
                    raise DesignSpaceDocumentError(
                        f'Missing xvalue="" for the location dimension "{dimName}"" with yvalue="{yValue}"'
                    )
                designLoc[dimName] = (xValue, yValue)
            elif xValue is not None:
                designLoc[dimName] = xValue
            else:
                userLoc[dimName] = userValue
        return designLoc, userLoc

    def readInstances(self, makeGlyphs=True, makeKerning=True, makeInfo=True):
        instanceElements = self.root.findall(".instances/instance")
        for instanceElement in instanceElements:
            self._readSingleInstanceElement(
                instanceElement,
                makeGlyphs=makeGlyphs,
                makeKerning=makeKerning,
                makeInfo=makeInfo,
            )

    def _readSingleInstanceElement(
        self, instanceElement, makeGlyphs=True, makeKerning=True, makeInfo=True
    ):
        filename = instanceElement.attrib.get("filename")
        if filename is not None and self.documentObject.path is not None:
            instancePath = os.path.join(
                os.path.dirname(self.documentObject.path), filename
            )
        else:
            instancePath = None
        instanceObject = self.instanceDescriptorClass()
        instanceObject.path = instancePath  # absolute path to the instance
        instanceObject.filename = filename  # path as it is stored in the document
        name = instanceElement.attrib.get("name")
        if name is not None:
            instanceObject.name = name
        familyname = instanceElement.attrib.get("familyname")
        if familyname is not None:
            instanceObject.familyName = familyname
        stylename = instanceElement.attrib.get("stylename")
        if stylename is not None:
            instanceObject.styleName = stylename
        postScriptFontName = instanceElement.attrib.get("postscriptfontname")
        if postScriptFontName is not None:
            instanceObject.postScriptFontName = postScriptFontName
        styleMapFamilyName = instanceElement.attrib.get("stylemapfamilyname")
        if styleMapFamilyName is not None:
            instanceObject.styleMapFamilyName = styleMapFamilyName
        styleMapStyleName = instanceElement.attrib.get("stylemapstylename")
        if styleMapStyleName is not None:
            instanceObject.styleMapStyleName = styleMapStyleName
        # read localised names
        for styleNameElement in instanceElement.findall("stylename"):
            for key, lang in styleNameElement.items():
                if key == XML_LANG:
                    styleName = styleNameElement.text
                    instanceObject.setStyleName(styleName, lang)
        for familyNameElement in instanceElement.findall("familyname"):
            for key, lang in familyNameElement.items():
                if key == XML_LANG:
                    familyName = familyNameElement.text
                    instanceObject.setFamilyName(familyName, lang)
        for styleMapStyleNameElement in instanceElement.findall("stylemapstylename"):
            for key, lang in styleMapStyleNameElement.items():
                if key == XML_LANG:
                    styleMapStyleName = styleMapStyleNameElement.text
                    instanceObject.setStyleMapStyleName(styleMapStyleName, lang)
        for styleMapFamilyNameElement in instanceElement.findall("stylemapfamilyname"):
            for key, lang in styleMapFamilyNameElement.items():
                if key == XML_LANG:
                    styleMapFamilyName = styleMapFamilyNameElement.text
                    instanceObject.setStyleMapFamilyName(styleMapFamilyName, lang)
        designLocation, userLocation = self.locationFromElement(instanceElement)
        locationLabel = instanceElement.attrib.get("location")
        if (designLocation or userLocation) and locationLabel is not None:
            raise DesignSpaceDocumentError(
                'instance element must have at most one of the location="..." attribute or the nested location element'
            )
        instanceObject.locationLabel = locationLabel
        instanceObject.userLocation = userLocation or {}
        instanceObject.designLocation = designLocation or {}
        for glyphElement in instanceElement.findall(".glyphs/glyph"):
            self.readGlyphElement(glyphElement, instanceObject)
        for infoElement in instanceElement.findall("info"):
            self.readInfoElement(infoElement, instanceObject)
        for libElement in instanceElement.findall("lib"):
            self.readLibElement(libElement, instanceObject)
        self.documentObject.instances.append(instanceObject)

    def readLibElement(self, libElement, instanceObject):
        """Read the lib element for the given instance."""
        instanceObject.lib = plistlib.fromtree(libElement[0])

    def readInfoElement(self, infoElement, instanceObject):
        """Read the info element."""
        instanceObject.info = True

    def readGlyphElement(self, glyphElement, instanceObject):
        """
        Read the glyph element, which could look like either one of these:

        .. code-block:: xml

            <glyph name="b" unicode="0x62"/>

            <glyph name="b"/>

            <glyph name="b">
                <master location="location-token-bbb" source="master-token-aaa2"/>
                <master glyphname="b.alt1" location="location-token-ccc" source="master-token-aaa3"/>
                <note>
                    This is an instance from an anisotropic interpolation.
                </note>
            </glyph>
        """
        glyphData = {}
        glyphName = glyphElement.attrib.get("name")
        if glyphName is None:
            raise DesignSpaceDocumentError("Glyph object without name attribute")
        mute = glyphElement.attrib.get("mute")
        if mute == "1":
            glyphData["mute"] = True
        # unicode
        unicodes = glyphElement.attrib.get("unicode")
        if unicodes is not None:
            try:
                unicodes = [int(u, 16) for u in unicodes.split(" ")]
                glyphData["unicodes"] = unicodes
            except ValueError:
                raise DesignSpaceDocumentError(
                    "unicode values %s are not integers" % unicodes
                )

        for noteElement in glyphElement.findall(".note"):
            glyphData["note"] = noteElement.text
            break
        designLocation, userLocation = self.locationFromElement(glyphElement)
        if userLocation:
            raise DesignSpaceDocumentError(
                f'<glyph> element "{glyphName}" must only have design locations (using xvalue="").'
            )
        if designLocation is not None:
            glyphData["instanceLocation"] = designLocation
        glyphSources = None
        for masterElement in glyphElement.findall(".masters/master"):
            fontSourceName = masterElement.attrib.get("source")
            designLocation, userLocation = self.locationFromElement(masterElement)
            if userLocation:
                raise DesignSpaceDocumentError(
                    f'<master> element "{fontSourceName}" must only have design locations (using xvalue="").'
                )
            masterGlyphName = masterElement.attrib.get("glyphname")
            if masterGlyphName is None:
                # if we don't read a glyphname, use the one we have
                masterGlyphName = glyphName
            d = dict(
                font=fontSourceName, location=designLocation, glyphName=masterGlyphName
            )
            if glyphSources is None:
                glyphSources = []
            glyphSources.append(d)
        if glyphSources is not None:
            glyphData["masters"] = glyphSources
        instanceObject.glyphs[glyphName] = glyphData

    def readLib(self):
        """Read the lib element for the whole document."""
        for libElement in self.root.findall(".lib"):
            self.documentObject.lib = plistlib.fromtree(libElement[0])


class DesignSpaceDocument(LogMixin, AsDictMixin):
    """The DesignSpaceDocument object can read and write ``.designspace`` data.
    It imports the axes, sources, variable fonts and instances to very basic
    **descriptor** objects that store the data in attributes. Data is added to
    the document by creating such descriptor objects, filling them with data
    and then adding them to the document. This makes it easy to integrate this
    object in different contexts.

    The **DesignSpaceDocument** object can be subclassed to work with
    different objects, as long as they have the same attributes. Reader and
    Writer objects can be subclassed as well.

    **Note:** Python attribute names are usually camelCased, the
    corresponding `XML <document-xml-structure>`_ attributes are usually
    all lowercase.

    .. code:: python

        from fontTools.designspaceLib import DesignSpaceDocument
        doc = DesignSpaceDocument.fromfile("some/path/to/my.designspace")
        doc.formatVersion
        doc.elidedFallbackName
        doc.axes
        doc.axisMappings
        doc.locationLabels
        doc.rules
        doc.rulesProcessingLast
        doc.sources
        doc.variableFonts
        doc.instances
        doc.lib

    """

    def __init__(self, readerClass=None, writerClass=None):
        self.path = None
        """String, optional. When the document is read from the disk, this is
        the full path that was given to :meth:`read` or :meth:`fromfile`.
        """
        self.filename = None
        """String, optional. When the document is read from the disk, this is
        its original file name, i.e. the last part of its path.

        When the document is produced by a Python script and still only exists
        in memory, the producing script can write here an indication of a
        possible "good" filename, in case one wants to save the file somewhere.
        """

        self.formatVersion: Optional[str] = None
        """Format version for this document, as a string. E.g. "4.0" """

        self.elidedFallbackName: Optional[str] = None
        """STAT Style Attributes Header field ``elidedFallbackNameID``.

        See: `OTSpec STAT Style Attributes Header <https://docs.microsoft.com/en-us/typography/opentype/spec/stat#style-attributes-header>`_

        .. versionadded:: 5.0
        """

        self.axes: List[Union[AxisDescriptor, DiscreteAxisDescriptor]] = []
        """List of this document's axes."""

        self.axisMappings: List[AxisMappingDescriptor] = []
        """List of this document's axis mappings."""

        self.locationLabels: List[LocationLabelDescriptor] = []
        """List of this document's STAT format 4 labels.

        .. versionadded:: 5.0"""
        self.rules: List[RuleDescriptor] = []
        """List of this document's rules."""
        self.rulesProcessingLast: bool = False
        """This flag indicates whether the substitution rules should be applied
        before or after other glyph substitution features.

        - False: before
        - True: after.

        Default is False. For new projects, you probably want True. See
        the following issues for more information:
        `fontTools#1371 <https://github.com/fonttools/fonttools/issues/1371#issuecomment-590214572>`__
        `fontTools#2050 <https://github.com/fonttools/fonttools/issues/2050#issuecomment-678691020>`__

        If you want to use a different feature altogether, e.g. ``calt``,
        use the lib key ``com.github.fonttools.varLib.featureVarsFeatureTag``

        .. code:: xml

            <lib>
                <dict>
                    <key>com.github.fonttools.varLib.featureVarsFeatureTag</key>
                    <string>calt</string>
                </dict>
            </lib>
        """
        self.sources: List[SourceDescriptor] = []
        """List of this document's sources."""
        self.variableFonts: List[VariableFontDescriptor] = []
        """List of this document's variable fonts.

        .. versionadded:: 5.0"""
        self.instances: List[InstanceDescriptor] = []
        """List of this document's instances."""
        self.lib: Dict = {}
        """User defined, custom data associated with the whole document.

        Use reverse-DNS notation to identify your own data.
        Respect the data stored by others.
        """

        self.default: Optional[str] = None
        """Name of the default master.

        This attribute is updated by the :meth:`findDefault`
        """

        if readerClass is not None:
            self.readerClass = readerClass
        else:
            self.readerClass = BaseDocReader
        if writerClass is not None:
            self.writerClass = writerClass
        else:
            self.writerClass = BaseDocWriter

    @classmethod
    def fromfile(cls, path, readerClass=None, writerClass=None):
        """Read a designspace file from ``path`` and return a new instance of
        :class:.
        """
        self = cls(readerClass=readerClass, writerClass=writerClass)
        self.read(path)
        return self

    @classmethod
    def fromstring(cls, string, readerClass=None, writerClass=None):
        self = cls(readerClass=readerClass, writerClass=writerClass)
        reader = self.readerClass.fromstring(string, self)
        reader.read()
        if self.sources:
            self.findDefault()
        return self

    def tostring(self, encoding=None):
        """Returns the designspace as a string. Default encoding ``utf-8``."""
        if encoding is str or (encoding is not None and encoding.lower() == "unicode"):
            f = StringIO()
            xml_declaration = False
        elif encoding is None or encoding == "utf-8":
            f = BytesIO()
            encoding = "UTF-8"
            xml_declaration = True
        else:
            raise ValueError("unsupported encoding: '%s'" % encoding)
        writer = self.writerClass(f, self)
        writer.write(encoding=encoding, xml_declaration=xml_declaration)
        return f.getvalue()

    def read(self, path):
        """Read a designspace file from ``path`` and populates the fields of
        ``self`` with the data.
        """
        if hasattr(path, "__fspath__"):  # support os.PathLike objects
            path = path.__fspath__()
        self.path = path
        self.filename = os.path.basename(path)
        reader = self.readerClass(path, self)
        reader.read()
        if self.sources:
            self.findDefault()

    def write(self, path):
        """Write this designspace to ``path``."""
        if hasattr(path, "__fspath__"):  # support os.PathLike objects
            path = path.__fspath__()
        self.path = path
        self.filename = os.path.basename(path)
        self.updatePaths()
        writer = self.writerClass(path, self)
        writer.write()

    def _posixRelativePath(self, otherPath):
        relative = os.path.relpath(otherPath, os.path.dirname(self.path))
        return posix(relative)

    def updatePaths(self):
        """
        Right before we save we need to identify and respond to the following situations:
        In each descriptor, we have to do the right thing for the filename attribute.

        ::

            case 1.
            descriptor.filename == None
            descriptor.path == None

            -- action:
            write as is, descriptors will not have a filename attr.
            useless, but no reason to interfere.


            case 2.
            descriptor.filename == "../something"
            descriptor.path == None

            -- action:
            write as is. The filename attr should not be touched.


            case 3.
            descriptor.filename == None
            descriptor.path == "~/absolute/path/there"

            -- action:
            calculate the relative path for filename.
            We're not overwriting some other value for filename, it should be fine


            case 4.
            descriptor.filename == '../somewhere'
            descriptor.path == "~/absolute/path/there"

            -- action:
            there is a conflict between the given filename, and the path.
            So we know where the file is relative to the document.
            Can't guess why they're different, we just choose for path to be correct and update filename.
        """
        assert self.path is not None
        for descriptor in self.sources + self.instances:
            if descriptor.path is not None:
                # case 3 and 4: filename gets updated and relativized
                descriptor.filename = self._posixRelativePath(descriptor.path)

    def addSource(self, sourceDescriptor: SourceDescriptor):
        """Add the given ``sourceDescriptor`` to ``doc.sources``."""
        self.sources.append(sourceDescriptor)

    def addSourceDescriptor(self, **kwargs):
        """Instantiate a new :class:`SourceDescriptor` using the given
        ``kwargs`` and add it to ``doc.sources``.
        """
        source = self.writerClass.sourceDescriptorClass(**kwargs)
        self.addSource(source)
        return source

    def addInstance(self, instanceDescriptor: InstanceDescriptor):
        """Add the given ``instanceDescriptor`` to :attr:`instances`."""
        self.instances.append(instanceDescriptor)

    def addInstanceDescriptor(self, **kwargs):
        """Instantiate a new :class:`InstanceDescriptor` using the given
        ``kwargs`` and add it to :attr:`instances`.
        """
        instance = self.writerClass.instanceDescriptorClass(**kwargs)
        self.addInstance(instance)
        return instance

    def addAxis(self, axisDescriptor: Union[AxisDescriptor, DiscreteAxisDescriptor]):
        """Add the given ``axisDescriptor`` to :attr:`axes`."""
        self.axes.append(axisDescriptor)

    def addAxisDescriptor(self, **kwargs):
        """Instantiate a new :class:`AxisDescriptor` using the given
        ``kwargs`` and add it to :attr:`axes`.

        The axis will be and instance of :class:`DiscreteAxisDescriptor` if
        the ``kwargs`` provide a ``value``, or a :class:`AxisDescriptor` otherwise.
        """
        if "values" in kwargs:
            axis = self.writerClass.discreteAxisDescriptorClass(**kwargs)
        else:
            axis = self.writerClass.axisDescriptorClass(**kwargs)
        self.addAxis(axis)
        return axis

    def addAxisMapping(self, axisMappingDescriptor: AxisMappingDescriptor):
        """Add the given ``axisMappingDescriptor`` to :attr:`axisMappings`."""
        self.axisMappings.append(axisMappingDescriptor)

    def addAxisMappingDescriptor(self, **kwargs):
        """Instantiate a new :class:`AxisMappingDescriptor` using the given
        ``kwargs`` and add it to :attr:`rules`.
        """
        axisMapping = self.writerClass.axisMappingDescriptorClass(**kwargs)
        self.addAxisMapping(axisMapping)
        return axisMapping

    def addRule(self, ruleDescriptor: RuleDescriptor):
        """Add the given ``ruleDescriptor`` to :attr:`rules`."""
        self.rules.append(ruleDescriptor)

    def addRuleDescriptor(self, **kwargs):
        """Instantiate a new :class:`RuleDescriptor` using the given
        ``kwargs`` and add it to :attr:`rules`.
        """
        rule = self.writerClass.ruleDescriptorClass(**kwargs)
        self.addRule(rule)
        return rule

    def addVariableFont(self, variableFontDescriptor: VariableFontDescriptor):
        """Add the given ``variableFontDescriptor`` to :attr:`variableFonts`.

        .. versionadded:: 5.0
        """
        self.variableFonts.append(variableFontDescriptor)

    def addVariableFontDescriptor(self, **kwargs):
        """Instantiate a new :class:`VariableFontDescriptor` using the given
        ``kwargs`` and add it to :attr:`variableFonts`.

        .. versionadded:: 5.0
        """
        variableFont = self.writerClass.variableFontDescriptorClass(**kwargs)
        self.addVariableFont(variableFont)
        return variableFont

    def addLocationLabel(self, locationLabelDescriptor: LocationLabelDescriptor):
        """Add the given ``locationLabelDescriptor`` to :attr:`locationLabels`.

        .. versionadded:: 5.0
        """
        self.locationLabels.append(locationLabelDescriptor)

    def addLocationLabelDescriptor(self, **kwargs):
        """Instantiate a new :class:`LocationLabelDescriptor` using the given
        ``kwargs`` and add it to :attr:`locationLabels`.

        .. versionadded:: 5.0
        """
        locationLabel = self.writerClass.locationLabelDescriptorClass(**kwargs)
        self.addLocationLabel(locationLabel)
        return locationLabel

    def newDefaultLocation(self):
        """Return a dict with the default location in design space coordinates."""
        # Without OrderedDict, output XML would be non-deterministic.
        # https://github.com/LettError/designSpaceDocument/issues/10
        loc = collections.OrderedDict()
        for axisDescriptor in self.axes:
            loc[axisDescriptor.name] = axisDescriptor.map_forward(
                axisDescriptor.default
            )
        return loc

    def labelForUserLocation(
        self, userLocation: SimpleLocationDict
    ) -> Optional[LocationLabelDescriptor]:
        """Return the :class:`LocationLabel` that matches the given
        ``userLocation``, or ``None`` if no such label exists.

        .. versionadded:: 5.0
        """
        return next(
            (
                label
                for label in self.locationLabels
                if label.userLocation == userLocation
            ),
            None,
        )

    def updateFilenameFromPath(self, masters=True, instances=True, force=False):
        """Set a descriptor filename attr from the path and this document path.

        If the filename attribute is not None: skip it.
        """
        if masters:
            for descriptor in self.sources:
                if descriptor.filename is not None and not force:
                    continue
                if self.path is not None:
                    descriptor.filename = self._posixRelativePath(descriptor.path)
        if instances:
            for descriptor in self.instances:
                if descriptor.filename is not None and not force:
                    continue
                if self.path is not None:
                    descriptor.filename = self._posixRelativePath(descriptor.path)

    def newAxisDescriptor(self):
        """Ask the writer class to make us a new axisDescriptor."""
        return self.writerClass.getAxisDecriptor()

    def newSourceDescriptor(self):
        """Ask the writer class to make us a new sourceDescriptor."""
        return self.writerClass.getSourceDescriptor()

    def newInstanceDescriptor(self):
        """Ask the writer class to make us a new instanceDescriptor."""
        return self.writerClass.getInstanceDescriptor()

    def getAxisOrder(self):
        """Return a list of axis names, in the same order as defined in the document."""
        names = []
        for axisDescriptor in self.axes:
            names.append(axisDescriptor.name)
        return names

    def getAxis(self, name: str) -> AxisDescriptor | DiscreteAxisDescriptor | None:
        """Return the axis with the given ``name``, or ``None`` if no such axis exists."""
        return next((axis for axis in self.axes if axis.name == name), None)

    def getAxisByTag(self, tag: str) -> AxisDescriptor | DiscreteAxisDescriptor | None:
        """Return the axis with the given ``tag``, or ``None`` if no such axis exists."""
        return next((axis for axis in self.axes if axis.tag == tag), None)

    def getLocationLabel(self, name: str) -> Optional[LocationLabelDescriptor]:
        """Return the top-level location label with the given ``name``, or
        ``None`` if no such label exists.

        .. versionadded:: 5.0
        """
        for label in self.locationLabels:
            if label.name == name:
                return label
        return None

    def map_forward(self, userLocation: SimpleLocationDict) -> SimpleLocationDict:
        """Map a user location to a design location.

        Assume that missing coordinates are at the default location for that axis.

        Note: the output won't be anisotropic, only the xvalue is set.

        .. versionadded:: 5.0
        """
        return {
            axis.name: axis.map_forward(userLocation.get(axis.name, axis.default))
            for axis in self.axes
        }

    def map_backward(
        self, designLocation: AnisotropicLocationDict
    ) -> SimpleLocationDict:
        """Map a design location to a user location.

        Assume that missing coordinates are at the default location for that axis.

        When the input has anisotropic locations, only the xvalue is used.

        .. versionadded:: 5.0
        """
        return {
            axis.name: (
                axis.map_backward(designLocation[axis.name])
                if axis.name in designLocation
                else axis.default
            )
            for axis in self.axes
        }

    def findDefault(self):
        """Set and return SourceDescriptor at the default location or None.

        The default location is the set of all `default` values in user space
        of all axes.

        This function updates the document's :attr:`default` value.

        .. versionchanged:: 5.0
           Allow the default source to not specify some of the axis values, and
           they are assumed to be the default.
           See :meth:`SourceDescriptor.getFullDesignLocation()`
        """
        self.default = None

        # Convert the default location from user space to design space before comparing
        # it against the SourceDescriptor locations (always in design space).
        defaultDesignLocation = self.newDefaultLocation()

        for sourceDescriptor in self.sources:
            if sourceDescriptor.getFullDesignLocation(self) == defaultDesignLocation:
                self.default = sourceDescriptor
                return sourceDescriptor

        return None

    def normalizeLocation(self, location):
        """Return a dict with normalized axis values."""
        from fontTools.varLib.models import normalizeValue

        new = {}
        for axis in self.axes:
            if axis.name not in location:
                # skipping this dimension it seems
                continue
            value = location[axis.name]
            # 'anisotropic' location, take first coord only
            if isinstance(value, tuple):
                value = value[0]
            triple = [
                axis.map_forward(v) for v in (axis.minimum, axis.default, axis.maximum)
            ]
            new[axis.name] = normalizeValue(value, triple)
        return new

    def normalize(self):
        """
        Normalise the geometry of this designspace:

        - scale all the locations of all masters and instances to the -1 - 0 - 1 value.
        - we need the axis data to do the scaling, so we do those last.
        """
        # masters
        for item in self.sources:
            item.location = self.normalizeLocation(item.location)
        # instances
        for item in self.instances:
            # glyph masters for this instance
            for _, glyphData in item.glyphs.items():
                glyphData["instanceLocation"] = self.normalizeLocation(
                    glyphData["instanceLocation"]
                )
                for glyphMaster in glyphData["masters"]:
                    glyphMaster["location"] = self.normalizeLocation(
                        glyphMaster["location"]
                    )
            item.location = self.normalizeLocation(item.location)
        # the axes
        for axis in self.axes:
            # scale the map first
            newMap = []
            for inputValue, outputValue in axis.map:
                newOutputValue = self.normalizeLocation({axis.name: outputValue}).get(
                    axis.name
                )
                newMap.append((inputValue, newOutputValue))
            if newMap:
                axis.map = newMap
            # finally the axis values
            minimum = self.normalizeLocation({axis.name: axis.minimum}).get(axis.name)
            maximum = self.normalizeLocation({axis.name: axis.maximum}).get(axis.name)
            default = self.normalizeLocation({axis.name: axis.default}).get(axis.name)
            # and set them in the axis.minimum
            axis.minimum = minimum
            axis.maximum = maximum
            axis.default = default
        # now the rules
        for rule in self.rules:
            newConditionSets = []
            for conditions in rule.conditionSets:
                newConditions = []
                for cond in conditions:
                    if cond.get("minimum") is not None:
                        minimum = self.normalizeLocation(
                            {cond["name"]: cond["minimum"]}
                        ).get(cond["name"])
                    else:
                        minimum = None
                    if cond.get("maximum") is not None:
                        maximum = self.normalizeLocation(
                            {cond["name"]: cond["maximum"]}
                        ).get(cond["name"])
                    else:
                        maximum = None
                    newConditions.append(
                        dict(name=cond["name"], minimum=minimum, maximum=maximum)
                    )
                newConditionSets.append(newConditions)
            rule.conditionSets = newConditionSets

    def loadSourceFonts(self, opener, **kwargs):
        """Ensure SourceDescriptor.font attributes are loaded, and return list of fonts.

        Takes a callable which initializes a new font object (e.g. TTFont, or
        defcon.Font, etc.) from the SourceDescriptor.path, and sets the
        SourceDescriptor.font attribute.
        If the font attribute is already not None, it is not loaded again.
        Fonts with the same path are only loaded once and shared among SourceDescriptors.

        For example, to load UFO sources using defcon:

            designspace = DesignSpaceDocument.fromfile("path/to/my.designspace")
            designspace.loadSourceFonts(defcon.Font)

        Or to load masters as FontTools binary fonts, including extra options:

            designspace.loadSourceFonts(ttLib.TTFont, recalcBBoxes=False)

        Args:
            opener (Callable): takes one required positional argument, the source.path,
                and an optional list of keyword arguments, and returns a new font object
                loaded from the path.
            **kwargs: extra options passed on to the opener function.

        Returns:
            List of font objects in the order they appear in the sources list.
        """
        # we load fonts with the same source.path only once
        loaded = {}
        fonts = []
        for source in self.sources:
            if source.font is not None:  # font already loaded
                fonts.append(source.font)
                continue
            if source.path in loaded:
                source.font = loaded[source.path]
            else:
                if source.path is None:
                    raise DesignSpaceDocumentError(
                        "Designspace source '%s' has no 'path' attribute"
                        % (source.name or "<Unknown>")
                    )
                source.font = opener(source.path, **kwargs)
                loaded[source.path] = source.font
            fonts.append(source.font)
        return fonts

    @property
    def formatTuple(self):
        """Return the formatVersion as a tuple of (major, minor).

        .. versionadded:: 5.0
        """
        if self.formatVersion is None:
            return (5, 0)
        numbers = (int(i) for i in self.formatVersion.split("."))
        major = next(numbers)
        minor = next(numbers, 0)
        return (major, minor)

    def getVariableFonts(self) -> List[VariableFontDescriptor]:
        """Return all variable fonts defined in this document, or implicit
        variable fonts that can be built from the document's continuous axes.

        In the case of Designspace documents before version 5, the whole
        document was implicitly describing a variable font that covers the
        whole space.

        In version 5 and above documents, there can be as many variable fonts
        as there are locations on discrete axes.

        .. seealso:: :func:`splitInterpolable`

        .. versionadded:: 5.0
        """
        if self.variableFonts:
            return self.variableFonts

        variableFonts = []
        discreteAxes = []
        rangeAxisSubsets: List[
            Union[RangeAxisSubsetDescriptor, ValueAxisSubsetDescriptor]
        ] = []
        for axis in self.axes:
            if hasattr(axis, "values"):
                # Mypy doesn't support narrowing union types via hasattr()
                # TODO(Python 3.10): use TypeGuard
                # https://mypy.readthedocs.io/en/stable/type_narrowing.html
                axis = cast(DiscreteAxisDescriptor, axis)
                discreteAxes.append(axis)  # type: ignore
            else:
                rangeAxisSubsets.append(RangeAxisSubsetDescriptor(name=axis.name))
        valueCombinations = itertools.product(*[axis.values for axis in discreteAxes])
        for values in valueCombinations:
            basename = None
            if self.filename is not None:
                basename = os.path.splitext(self.filename)[0] + "-VF"
            if self.path is not None:
                basename = os.path.splitext(os.path.basename(self.path))[0] + "-VF"
            if basename is None:
                basename = "VF"
            axisNames = "".join(
                [f"-{axis.tag}{value}" for axis, value in zip(discreteAxes, values)]
            )
            variableFonts.append(
                VariableFontDescriptor(
                    name=f"{basename}{axisNames}",
                    axisSubsets=rangeAxisSubsets
                    + [
                        ValueAxisSubsetDescriptor(name=axis.name, userValue=value)
                        for axis, value in zip(discreteAxes, values)
                    ],
                )
            )
        return variableFonts

    def deepcopyExceptFonts(self):
        """Allow deep-copying a DesignSpace document without deep-copying
        attached UFO fonts or TTFont objects. The :attr:`font` attribute
        is shared by reference between the original and the copy.

        .. versionadded:: 5.0
        """
        fonts = [source.font for source in self.sources]
        try:
            for source in self.sources:
                source.font = None
            res = copy.deepcopy(self)
            for source, font in zip(res.sources, fonts):
                source.font = font
            return res
        finally:
            for source, font in zip(self.sources, fonts):
                source.font = font


def main(args=None):
    """Roundtrip .designspace file through the DesignSpaceDocument class"""

    if args is None:
        import sys

        args = sys.argv[1:]

    from argparse import ArgumentParser

    parser = ArgumentParser(prog="designspaceLib", description=main.__doc__)
    parser.add_argument("input")
    parser.add_argument("output")

    options = parser.parse_args(args)

    ds = DesignSpaceDocument.fromfile(options.input)
    ds.write(options.output)
