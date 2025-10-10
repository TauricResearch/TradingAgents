# coding: utf-8
"""fontTools.ttLib.tables.otTables -- A collection of classes representing the various
OpenType subtables.

Most are constructed upon import from data in otData.py, all are populated with
converter objects from otConverters.py.
"""
import copy
from enum import IntEnum
from functools import reduce
from math import radians
import itertools
from collections import defaultdict, namedtuple
from fontTools.ttLib import OPTIMIZE_FONT_SPEED
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.otTraverse import dfs_base_table
from fontTools.misc.arrayTools import quantizeRect
from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform, Identity, DecomposedTransform
from fontTools.misc.textTools import bytesjoin, pad, safeEval
from fontTools.misc.vector import Vector
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.transformPen import TransformPen
from .otBase import (
    BaseTable,
    FormatSwitchingBaseTable,
    ValueRecord,
    CountReference,
    getFormatSwitchingBaseTableClass,
)
from fontTools.misc.fixedTools import (
    fixedToFloat as fi2fl,
    floatToFixed as fl2fi,
    floatToFixedToStr as fl2str,
    strToFixedToFloat as str2fl,
)
from fontTools.feaLib.lookupDebugInfo import LookupDebugInfo, LOOKUP_DEBUG_INFO_KEY
import logging
import struct
import array
import sys
from enum import IntFlag
from typing import TYPE_CHECKING, Iterator, List, Optional, Set

if TYPE_CHECKING:
    from fontTools.ttLib.ttGlyphSet import _TTGlyphSet


log = logging.getLogger(__name__)


class VarComponentFlags(IntFlag):
    RESET_UNSPECIFIED_AXES = 1 << 0

    HAVE_AXES = 1 << 1

    AXIS_VALUES_HAVE_VARIATION = 1 << 2
    TRANSFORM_HAS_VARIATION = 1 << 3

    HAVE_TRANSLATE_X = 1 << 4
    HAVE_TRANSLATE_Y = 1 << 5
    HAVE_ROTATION = 1 << 6

    HAVE_CONDITION = 1 << 7

    HAVE_SCALE_X = 1 << 8
    HAVE_SCALE_Y = 1 << 9
    HAVE_TCENTER_X = 1 << 10
    HAVE_TCENTER_Y = 1 << 11

    GID_IS_24BIT = 1 << 12

    HAVE_SKEW_X = 1 << 13
    HAVE_SKEW_Y = 1 << 14

    RESERVED_MASK = (1 << 32) - (1 << 15)


VarTransformMappingValues = namedtuple(
    "VarTransformMappingValues",
    ["flag", "fractionalBits", "scale", "defaultValue"],
)

VAR_TRANSFORM_MAPPING = {
    "translateX": VarTransformMappingValues(
        VarComponentFlags.HAVE_TRANSLATE_X, 0, 1, 0
    ),
    "translateY": VarTransformMappingValues(
        VarComponentFlags.HAVE_TRANSLATE_Y, 0, 1, 0
    ),
    "rotation": VarTransformMappingValues(VarComponentFlags.HAVE_ROTATION, 12, 180, 0),
    "scaleX": VarTransformMappingValues(VarComponentFlags.HAVE_SCALE_X, 10, 1, 1),
    "scaleY": VarTransformMappingValues(VarComponentFlags.HAVE_SCALE_Y, 10, 1, 1),
    "skewX": VarTransformMappingValues(VarComponentFlags.HAVE_SKEW_X, 12, -180, 0),
    "skewY": VarTransformMappingValues(VarComponentFlags.HAVE_SKEW_Y, 12, 180, 0),
    "tCenterX": VarTransformMappingValues(VarComponentFlags.HAVE_TCENTER_X, 0, 1, 0),
    "tCenterY": VarTransformMappingValues(VarComponentFlags.HAVE_TCENTER_Y, 0, 1, 0),
}

# Probably should be somewhere in fontTools.misc
_packer = {
    1: lambda v: struct.pack(">B", v),
    2: lambda v: struct.pack(">H", v),
    3: lambda v: struct.pack(">L", v)[1:],
    4: lambda v: struct.pack(">L", v),
}
_unpacker = {
    1: lambda v: struct.unpack(">B", v)[0],
    2: lambda v: struct.unpack(">H", v)[0],
    3: lambda v: struct.unpack(">L", b"\0" + v)[0],
    4: lambda v: struct.unpack(">L", v)[0],
}


def _read_uint32var(data, i):
    """Read a variable-length number from data starting at index i.

    Return the number and the next index.
    """

    b0 = data[i]
    if b0 < 0x80:
        return b0, i + 1
    elif b0 < 0xC0:
        return (b0 - 0x80) << 8 | data[i + 1], i + 2
    elif b0 < 0xE0:
        return (b0 - 0xC0) << 16 | data[i + 1] << 8 | data[i + 2], i + 3
    elif b0 < 0xF0:
        return (b0 - 0xE0) << 24 | data[i + 1] << 16 | data[i + 2] << 8 | data[
            i + 3
        ], i + 4
    else:
        return (b0 - 0xF0) << 32 | data[i + 1] << 24 | data[i + 2] << 16 | data[
            i + 3
        ] << 8 | data[i + 4], i + 5


def _write_uint32var(v):
    """Write a variable-length number.

    Return the data.
    """
    if v < 0x80:
        return struct.pack(">B", v)
    elif v < 0x4000:
        return struct.pack(">H", (v | 0x8000))
    elif v < 0x200000:
        return struct.pack(">L", (v | 0xC00000))[1:]
    elif v < 0x10000000:
        return struct.pack(">L", (v | 0xE0000000))
    else:
        return struct.pack(">B", 0xF0) + struct.pack(">L", v)


class VarComponent:
    def __init__(self):
        self.populateDefaults()

    def populateDefaults(self, propagator=None):
        self.flags = 0
        self.glyphName = None
        self.conditionIndex = None
        self.axisIndicesIndex = None
        self.axisValues = ()
        self.axisValuesVarIndex = NO_VARIATION_INDEX
        self.transformVarIndex = NO_VARIATION_INDEX
        self.transform = DecomposedTransform()

    def decompile(self, data, font, localState):
        i = 0
        self.flags, i = _read_uint32var(data, i)
        flags = self.flags

        gidSize = 3 if flags & VarComponentFlags.GID_IS_24BIT else 2
        glyphID = _unpacker[gidSize](data[i : i + gidSize])
        i += gidSize
        self.glyphName = font.glyphOrder[glyphID]

        if flags & VarComponentFlags.HAVE_CONDITION:
            self.conditionIndex, i = _read_uint32var(data, i)

        if flags & VarComponentFlags.HAVE_AXES:
            self.axisIndicesIndex, i = _read_uint32var(data, i)
        else:
            self.axisIndicesIndex = None

        if self.axisIndicesIndex is None:
            numAxes = 0
        else:
            axisIndices = localState["AxisIndicesList"].Item[self.axisIndicesIndex]
            numAxes = len(axisIndices)

        if flags & VarComponentFlags.HAVE_AXES:
            axisValues, i = TupleVariation.decompileDeltas_(numAxes, data, i)
            self.axisValues = tuple(fi2fl(v, 14) for v in axisValues)
        else:
            self.axisValues = ()
        assert len(self.axisValues) == numAxes

        if flags & VarComponentFlags.AXIS_VALUES_HAVE_VARIATION:
            self.axisValuesVarIndex, i = _read_uint32var(data, i)
        else:
            self.axisValuesVarIndex = NO_VARIATION_INDEX
        if flags & VarComponentFlags.TRANSFORM_HAS_VARIATION:
            self.transformVarIndex, i = _read_uint32var(data, i)
        else:
            self.transformVarIndex = NO_VARIATION_INDEX

        self.transform = DecomposedTransform()

        def read_transform_component(values):
            nonlocal i
            if flags & values.flag:
                v = (
                    fi2fl(
                        struct.unpack(">h", data[i : i + 2])[0], values.fractionalBits
                    )
                    * values.scale
                )
                i += 2
                return v
            else:
                return values.defaultValue

        for attr_name, mapping_values in VAR_TRANSFORM_MAPPING.items():
            value = read_transform_component(mapping_values)
            setattr(self.transform, attr_name, value)

        if not (flags & VarComponentFlags.HAVE_SCALE_Y):
            self.transform.scaleY = self.transform.scaleX

        n = flags & VarComponentFlags.RESERVED_MASK
        while n:
            _, i = _read_uint32var(data, i)
            n &= n - 1

        return data[i:]

    def compile(self, font):
        optimizeSpeed = font.cfg[OPTIMIZE_FONT_SPEED]

        data = []

        flags = self.flags

        glyphID = font.getGlyphID(self.glyphName)
        if glyphID > 65535:
            flags |= VarComponentFlags.GID_IS_24BIT
            data.append(_packer[3](glyphID))
        else:
            flags &= ~VarComponentFlags.GID_IS_24BIT
            data.append(_packer[2](glyphID))

        if self.conditionIndex is not None:
            flags |= VarComponentFlags.HAVE_CONDITION
            data.append(_write_uint32var(self.conditionIndex))

        numAxes = len(self.axisValues)

        if numAxes:
            flags |= VarComponentFlags.HAVE_AXES
            data.append(_write_uint32var(self.axisIndicesIndex))
            data.append(
                TupleVariation.compileDeltaValues_(
                    [fl2fi(v, 14) for v in self.axisValues],
                    optimizeSize=not optimizeSpeed,
                )
            )
        else:
            flags &= ~VarComponentFlags.HAVE_AXES

        if self.axisValuesVarIndex != NO_VARIATION_INDEX:
            flags |= VarComponentFlags.AXIS_VALUES_HAVE_VARIATION
            data.append(_write_uint32var(self.axisValuesVarIndex))
        else:
            flags &= ~VarComponentFlags.AXIS_VALUES_HAVE_VARIATION
        if self.transformVarIndex != NO_VARIATION_INDEX:
            flags |= VarComponentFlags.TRANSFORM_HAS_VARIATION
            data.append(_write_uint32var(self.transformVarIndex))
        else:
            flags &= ~VarComponentFlags.TRANSFORM_HAS_VARIATION

        def write_transform_component(value, values):
            if flags & values.flag:
                return struct.pack(
                    ">h", fl2fi(value / values.scale, values.fractionalBits)
                )
            else:
                return b""

        for attr_name, mapping_values in VAR_TRANSFORM_MAPPING.items():
            value = getattr(self.transform, attr_name)
            data.append(write_transform_component(value, mapping_values))

        return _write_uint32var(flags) + bytesjoin(data)

    def toXML(self, writer, ttFont, attrs):
        writer.begintag("VarComponent", attrs)
        writer.newline()

        def write(name, value, attrs=()):
            if value is not None:
                writer.simpletag(name, (("value", value),) + attrs)
                writer.newline()

        write("glyphName", self.glyphName)

        if self.conditionIndex is not None:
            write("conditionIndex", self.conditionIndex)
        if self.axisIndicesIndex is not None:
            write("axisIndicesIndex", self.axisIndicesIndex)
        if (
            self.axisIndicesIndex is not None
            or self.flags & VarComponentFlags.RESET_UNSPECIFIED_AXES
        ):
            if self.flags & VarComponentFlags.RESET_UNSPECIFIED_AXES:
                attrs = (("resetUnspecifiedAxes", 1),)
            else:
                attrs = ()
            write("axisValues", [float(fl2str(v, 14)) for v in self.axisValues], attrs)

        if self.axisValuesVarIndex != NO_VARIATION_INDEX:
            write("axisValuesVarIndex", self.axisValuesVarIndex)
        if self.transformVarIndex != NO_VARIATION_INDEX:
            write("transformVarIndex", self.transformVarIndex)

        # Only write transform components that are specified in the
        # flags, even if they are the default value.
        for attr_name, mapping in VAR_TRANSFORM_MAPPING.items():
            if not (self.flags & mapping.flag):
                continue
            v = getattr(self.transform, attr_name)
            write(attr_name, fl2str(v, mapping.fractionalBits))

        writer.endtag("VarComponent")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        content = [c for c in content if isinstance(c, tuple)]

        self.populateDefaults()

        for name, attrs, content in content:
            assert not content
            v = attrs["value"]

            if name == "glyphName":
                self.glyphName = v
            elif name == "conditionIndex":
                self.conditionIndex = safeEval(v)
            elif name == "axisIndicesIndex":
                self.axisIndicesIndex = safeEval(v)
            elif name == "axisValues":
                self.axisValues = tuple(str2fl(v, 14) for v in safeEval(v))
                if safeEval(attrs.get("resetUnspecifiedAxes", "0")):
                    self.flags |= VarComponentFlags.RESET_UNSPECIFIED_AXES
            elif name == "axisValuesVarIndex":
                self.axisValuesVarIndex = safeEval(v)
            elif name == "transformVarIndex":
                self.transformVarIndex = safeEval(v)
            elif name in VAR_TRANSFORM_MAPPING:
                setattr(
                    self.transform,
                    name,
                    safeEval(v),
                )
                self.flags |= VAR_TRANSFORM_MAPPING[name].flag
            else:
                assert False, name

    def applyTransformDeltas(self, deltas):
        i = 0

        def read_transform_component_delta(values):
            nonlocal i
            if self.flags & values.flag:
                v = fi2fl(deltas[i], values.fractionalBits) * values.scale
                i += 1
                return v
            else:
                return 0

        for attr_name, mapping_values in VAR_TRANSFORM_MAPPING.items():
            value = read_transform_component_delta(mapping_values)
            setattr(
                self.transform, attr_name, getattr(self.transform, attr_name) + value
            )

        if not (self.flags & VarComponentFlags.HAVE_SCALE_Y):
            self.transform.scaleY = self.transform.scaleX

        assert i == len(deltas), (i, len(deltas))

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result


class VarCompositeGlyph:
    def __init__(self, components=None):
        self.components = components if components is not None else []

    def decompile(self, data, font, localState):
        self.components = []
        while data:
            component = VarComponent()
            data = component.decompile(data, font, localState)
            self.components.append(component)

    def compile(self, font):
        data = []
        for component in self.components:
            data.append(component.compile(font))
        return bytesjoin(data)

    def toXML(self, xmlWriter, font, attrs, name):
        xmlWriter.begintag("VarCompositeGlyph", attrs)
        xmlWriter.newline()
        for i, component in enumerate(self.components):
            component.toXML(xmlWriter, font, [("index", i)])
        xmlWriter.endtag("VarCompositeGlyph")
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        content = [c for c in content if isinstance(c, tuple)]
        for name, attrs, content in content:
            assert name == "VarComponent"
            component = VarComponent()
            component.fromXML(name, attrs, content, font)
            self.components.append(component)


class AATStateTable(object):
    def __init__(self):
        self.GlyphClasses = {}  # GlyphID --> GlyphClass
        self.States = []  # List of AATState, indexed by state number
        self.PerGlyphLookups = []  # [{GlyphID:GlyphID}, ...]


class AATState(object):
    def __init__(self):
        self.Transitions = {}  # GlyphClass --> AATAction


class AATAction(object):
    _FLAGS = None

    @staticmethod
    def compileActions(font, states):
        return (None, None)

    def _writeFlagsToXML(self, xmlWriter):
        flags = [f for f in self._FLAGS if self.__dict__[f]]
        if flags:
            xmlWriter.simpletag("Flags", value=",".join(flags))
            xmlWriter.newline()
        if self.ReservedFlags != 0:
            xmlWriter.simpletag("ReservedFlags", value="0x%04X" % self.ReservedFlags)
            xmlWriter.newline()

    def _setFlag(self, flag):
        assert flag in self._FLAGS, "unsupported flag %s" % flag
        self.__dict__[flag] = True


class RearrangementMorphAction(AATAction):
    staticSize = 4
    actionHeaderSize = 0
    _FLAGS = ["MarkFirst", "DontAdvance", "MarkLast"]

    _VERBS = {
        0: "no change",
        1: "Ax ⇒ xA",
        2: "xD ⇒ Dx",
        3: "AxD ⇒ DxA",
        4: "ABx ⇒ xAB",
        5: "ABx ⇒ xBA",
        6: "xCD ⇒ CDx",
        7: "xCD ⇒ DCx",
        8: "AxCD ⇒ CDxA",
        9: "AxCD ⇒ DCxA",
        10: "ABxD ⇒ DxAB",
        11: "ABxD ⇒ DxBA",
        12: "ABxCD ⇒ CDxAB",
        13: "ABxCD ⇒ CDxBA",
        14: "ABxCD ⇒ DCxAB",
        15: "ABxCD ⇒ DCxBA",
    }

    def __init__(self):
        self.NewState = 0
        self.Verb = 0
        self.MarkFirst = False
        self.DontAdvance = False
        self.MarkLast = False
        self.ReservedFlags = 0

    def compile(self, writer, font, actionIndex):
        assert actionIndex is None
        writer.writeUShort(self.NewState)
        assert self.Verb >= 0 and self.Verb <= 15, self.Verb
        flags = self.Verb | self.ReservedFlags
        if self.MarkFirst:
            flags |= 0x8000
        if self.DontAdvance:
            flags |= 0x4000
        if self.MarkLast:
            flags |= 0x2000
        writer.writeUShort(flags)

    def decompile(self, reader, font, actionReader):
        assert actionReader is None
        self.NewState = reader.readUShort()
        flags = reader.readUShort()
        self.Verb = flags & 0xF
        self.MarkFirst = bool(flags & 0x8000)
        self.DontAdvance = bool(flags & 0x4000)
        self.MarkLast = bool(flags & 0x2000)
        self.ReservedFlags = flags & 0x1FF0

    def toXML(self, xmlWriter, font, attrs, name):
        xmlWriter.begintag(name, **attrs)
        xmlWriter.newline()
        xmlWriter.simpletag("NewState", value=self.NewState)
        xmlWriter.newline()
        self._writeFlagsToXML(xmlWriter)
        xmlWriter.simpletag("Verb", value=self.Verb)
        verbComment = self._VERBS.get(self.Verb)
        if verbComment is not None:
            xmlWriter.comment(verbComment)
        xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        self.NewState = self.Verb = self.ReservedFlags = 0
        self.MarkFirst = self.DontAdvance = self.MarkLast = False
        content = [t for t in content if isinstance(t, tuple)]
        for eltName, eltAttrs, eltContent in content:
            if eltName == "NewState":
                self.NewState = safeEval(eltAttrs["value"])
            elif eltName == "Verb":
                self.Verb = safeEval(eltAttrs["value"])
            elif eltName == "ReservedFlags":
                self.ReservedFlags = safeEval(eltAttrs["value"])
            elif eltName == "Flags":
                for flag in eltAttrs["value"].split(","):
                    self._setFlag(flag.strip())


class ContextualMorphAction(AATAction):
    staticSize = 8
    actionHeaderSize = 0
    _FLAGS = ["SetMark", "DontAdvance"]

    def __init__(self):
        self.NewState = 0
        self.SetMark, self.DontAdvance = False, False
        self.ReservedFlags = 0
        self.MarkIndex, self.CurrentIndex = 0xFFFF, 0xFFFF

    def compile(self, writer, font, actionIndex):
        assert actionIndex is None
        writer.writeUShort(self.NewState)
        flags = self.ReservedFlags
        if self.SetMark:
            flags |= 0x8000
        if self.DontAdvance:
            flags |= 0x4000
        writer.writeUShort(flags)
        writer.writeUShort(self.MarkIndex)
        writer.writeUShort(self.CurrentIndex)

    def decompile(self, reader, font, actionReader):
        assert actionReader is None
        self.NewState = reader.readUShort()
        flags = reader.readUShort()
        self.SetMark = bool(flags & 0x8000)
        self.DontAdvance = bool(flags & 0x4000)
        self.ReservedFlags = flags & 0x3FFF
        self.MarkIndex = reader.readUShort()
        self.CurrentIndex = reader.readUShort()

    def toXML(self, xmlWriter, font, attrs, name):
        xmlWriter.begintag(name, **attrs)
        xmlWriter.newline()
        xmlWriter.simpletag("NewState", value=self.NewState)
        xmlWriter.newline()
        self._writeFlagsToXML(xmlWriter)
        xmlWriter.simpletag("MarkIndex", value=self.MarkIndex)
        xmlWriter.newline()
        xmlWriter.simpletag("CurrentIndex", value=self.CurrentIndex)
        xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        self.NewState = self.ReservedFlags = 0
        self.SetMark = self.DontAdvance = False
        self.MarkIndex, self.CurrentIndex = 0xFFFF, 0xFFFF
        content = [t for t in content if isinstance(t, tuple)]
        for eltName, eltAttrs, eltContent in content:
            if eltName == "NewState":
                self.NewState = safeEval(eltAttrs["value"])
            elif eltName == "Flags":
                for flag in eltAttrs["value"].split(","):
                    self._setFlag(flag.strip())
            elif eltName == "ReservedFlags":
                self.ReservedFlags = safeEval(eltAttrs["value"])
            elif eltName == "MarkIndex":
                self.MarkIndex = safeEval(eltAttrs["value"])
            elif eltName == "CurrentIndex":
                self.CurrentIndex = safeEval(eltAttrs["value"])


class LigAction(object):
    def __init__(self):
        self.Store = False
        # GlyphIndexDelta is a (possibly negative) delta that gets
        # added to the glyph ID at the top of the AAT runtime
        # execution stack. It is *not* a byte offset into the
        # morx table. The result of the addition, which is performed
        # at run time by the shaping engine, is an index into
        # the ligature components table. See 'morx' specification.
        # In the AAT specification, this field is called Offset;
        # but its meaning is quite different from other offsets
        # in either AAT or OpenType, so we use a different name.
        self.GlyphIndexDelta = 0


class LigatureMorphAction(AATAction):
    staticSize = 6

    # 4 bytes for each of {action,ligComponents,ligatures}Offset
    actionHeaderSize = 12

    _FLAGS = ["SetComponent", "DontAdvance"]

    def __init__(self):
        self.NewState = 0
        self.SetComponent, self.DontAdvance = False, False
        self.ReservedFlags = 0
        self.Actions = []

    def compile(self, writer, font, actionIndex):
        assert actionIndex is not None
        writer.writeUShort(self.NewState)
        flags = self.ReservedFlags
        if self.SetComponent:
            flags |= 0x8000
        if self.DontAdvance:
            flags |= 0x4000
        if len(self.Actions) > 0:
            flags |= 0x2000
        writer.writeUShort(flags)
        if len(self.Actions) > 0:
            actions = self.compileLigActions()
            writer.writeUShort(actionIndex[actions])
        else:
            writer.writeUShort(0)

    def decompile(self, reader, font, actionReader):
        assert actionReader is not None
        self.NewState = reader.readUShort()
        flags = reader.readUShort()
        self.SetComponent = bool(flags & 0x8000)
        self.DontAdvance = bool(flags & 0x4000)
        performAction = bool(flags & 0x2000)
        # As of 2017-09-12, the 'morx' specification says that
        # the reserved bitmask in ligature subtables is 0x3FFF.
        # However, the specification also defines a flag 0x2000,
        # so the reserved value should actually be 0x1FFF.
        # TODO: Report this specification bug to Apple.
        self.ReservedFlags = flags & 0x1FFF
        actionIndex = reader.readUShort()
        if performAction:
            self.Actions = self._decompileLigActions(actionReader, actionIndex)
        else:
            self.Actions = []

    @staticmethod
    def compileActions(font, states):
        result, actions, actionIndex = b"", set(), {}
        for state in states:
            for _glyphClass, trans in state.Transitions.items():
                actions.add(trans.compileLigActions())
        # Sort the compiled actions in decreasing order of
        # length, so that the longer sequence come before the
        # shorter ones.  For each compiled action ABCD, its
        # suffixes BCD, CD, and D do not be encoded separately
        # (in case they occur); instead, we can just store an
        # index that points into the middle of the longer
        # sequence. Every compiled AAT ligature sequence is
        # terminated with an end-of-sequence flag, which can
        # only be set on the last element of the sequence.
        # Therefore, it is sufficient to consider just the
        # suffixes.
        for a in sorted(actions, key=lambda x: (-len(x), x)):
            if a not in actionIndex:
                for i in range(0, len(a), 4):
                    suffix = a[i:]
                    suffixIndex = (len(result) + i) // 4
                    actionIndex.setdefault(suffix, suffixIndex)
                result += a
        result = pad(result, 4)
        return (result, actionIndex)

    def compileLigActions(self):
        result = []
        for i, action in enumerate(self.Actions):
            last = i == len(self.Actions) - 1
            value = action.GlyphIndexDelta & 0x3FFFFFFF
            value |= 0x80000000 if last else 0
            value |= 0x40000000 if action.Store else 0
            result.append(struct.pack(">L", value))
        return bytesjoin(result)

    def _decompileLigActions(self, actionReader, actionIndex):
        actions = []
        last = False
        reader = actionReader.getSubReader(actionReader.pos + actionIndex * 4)
        while not last:
            value = reader.readULong()
            last = bool(value & 0x80000000)
            action = LigAction()
            actions.append(action)
            action.Store = bool(value & 0x40000000)
            delta = value & 0x3FFFFFFF
            if delta >= 0x20000000:  # sign-extend 30-bit value
                delta = -0x40000000 + delta
            action.GlyphIndexDelta = delta
        return actions

    def fromXML(self, name, attrs, content, font):
        self.NewState = self.ReservedFlags = 0
        self.SetComponent = self.DontAdvance = False
        self.ReservedFlags = 0
        self.Actions = []
        content = [t for t in content if isinstance(t, tuple)]
        for eltName, eltAttrs, eltContent in content:
            if eltName == "NewState":
                self.NewState = safeEval(eltAttrs["value"])
            elif eltName == "Flags":
                for flag in eltAttrs["value"].split(","):
                    self._setFlag(flag.strip())
            elif eltName == "ReservedFlags":
                self.ReservedFlags = safeEval(eltAttrs["value"])
            elif eltName == "Action":
                action = LigAction()
                flags = eltAttrs.get("Flags", "").split(",")
                flags = [f.strip() for f in flags]
                action.Store = "Store" in flags
                action.GlyphIndexDelta = safeEval(eltAttrs["GlyphIndexDelta"])
                self.Actions.append(action)

    def toXML(self, xmlWriter, font, attrs, name):
        xmlWriter.begintag(name, **attrs)
        xmlWriter.newline()
        xmlWriter.simpletag("NewState", value=self.NewState)
        xmlWriter.newline()
        self._writeFlagsToXML(xmlWriter)
        for action in self.Actions:
            attribs = [("GlyphIndexDelta", action.GlyphIndexDelta)]
            if action.Store:
                attribs.append(("Flags", "Store"))
            xmlWriter.simpletag("Action", attribs)
            xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()


class InsertionMorphAction(AATAction):
    staticSize = 8
    actionHeaderSize = 4  # 4 bytes for actionOffset
    _FLAGS = [
        "SetMark",
        "DontAdvance",
        "CurrentIsKashidaLike",
        "MarkedIsKashidaLike",
        "CurrentInsertBefore",
        "MarkedInsertBefore",
    ]

    def __init__(self):
        self.NewState = 0
        for flag in self._FLAGS:
            setattr(self, flag, False)
        self.ReservedFlags = 0
        self.CurrentInsertionAction, self.MarkedInsertionAction = [], []

    def compile(self, writer, font, actionIndex):
        assert actionIndex is not None
        writer.writeUShort(self.NewState)
        flags = self.ReservedFlags
        if self.SetMark:
            flags |= 0x8000
        if self.DontAdvance:
            flags |= 0x4000
        if self.CurrentIsKashidaLike:
            flags |= 0x2000
        if self.MarkedIsKashidaLike:
            flags |= 0x1000
        if self.CurrentInsertBefore:
            flags |= 0x0800
        if self.MarkedInsertBefore:
            flags |= 0x0400
        flags |= len(self.CurrentInsertionAction) << 5
        flags |= len(self.MarkedInsertionAction)
        writer.writeUShort(flags)
        if len(self.CurrentInsertionAction) > 0:
            currentIndex = actionIndex[tuple(self.CurrentInsertionAction)]
        else:
            currentIndex = 0xFFFF
        writer.writeUShort(currentIndex)
        if len(self.MarkedInsertionAction) > 0:
            markedIndex = actionIndex[tuple(self.MarkedInsertionAction)]
        else:
            markedIndex = 0xFFFF
        writer.writeUShort(markedIndex)

    def decompile(self, reader, font, actionReader):
        assert actionReader is not None
        self.NewState = reader.readUShort()
        flags = reader.readUShort()
        self.SetMark = bool(flags & 0x8000)
        self.DontAdvance = bool(flags & 0x4000)
        self.CurrentIsKashidaLike = bool(flags & 0x2000)
        self.MarkedIsKashidaLike = bool(flags & 0x1000)
        self.CurrentInsertBefore = bool(flags & 0x0800)
        self.MarkedInsertBefore = bool(flags & 0x0400)
        self.CurrentInsertionAction = self._decompileInsertionAction(
            actionReader, font, index=reader.readUShort(), count=((flags & 0x03E0) >> 5)
        )
        self.MarkedInsertionAction = self._decompileInsertionAction(
            actionReader, font, index=reader.readUShort(), count=(flags & 0x001F)
        )

    def _decompileInsertionAction(self, actionReader, font, index, count):
        if index == 0xFFFF or count == 0:
            return []
        reader = actionReader.getSubReader(actionReader.pos + index * 2)
        return font.getGlyphNameMany(reader.readUShortArray(count))

    def toXML(self, xmlWriter, font, attrs, name):
        xmlWriter.begintag(name, **attrs)
        xmlWriter.newline()
        xmlWriter.simpletag("NewState", value=self.NewState)
        xmlWriter.newline()
        self._writeFlagsToXML(xmlWriter)
        for g in self.CurrentInsertionAction:
            xmlWriter.simpletag("CurrentInsertionAction", glyph=g)
            xmlWriter.newline()
        for g in self.MarkedInsertionAction:
            xmlWriter.simpletag("MarkedInsertionAction", glyph=g)
            xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        self.__init__()
        content = [t for t in content if isinstance(t, tuple)]
        for eltName, eltAttrs, eltContent in content:
            if eltName == "NewState":
                self.NewState = safeEval(eltAttrs["value"])
            elif eltName == "Flags":
                for flag in eltAttrs["value"].split(","):
                    self._setFlag(flag.strip())
            elif eltName == "CurrentInsertionAction":
                self.CurrentInsertionAction.append(eltAttrs["glyph"])
            elif eltName == "MarkedInsertionAction":
                self.MarkedInsertionAction.append(eltAttrs["glyph"])
            else:
                assert False, eltName

    @staticmethod
    def compileActions(font, states):
        actions, actionIndex, result = set(), {}, b""
        for state in states:
            for _glyphClass, trans in state.Transitions.items():
                if trans.CurrentInsertionAction is not None:
                    actions.add(tuple(trans.CurrentInsertionAction))
                if trans.MarkedInsertionAction is not None:
                    actions.add(tuple(trans.MarkedInsertionAction))
        # Sort the compiled actions in decreasing order of
        # length, so that the longer sequence come before the
        # shorter ones.
        for action in sorted(actions, key=lambda x: (-len(x), x)):
            # We insert all sub-sequences of the action glyph sequence
            # into actionIndex. For example, if one action triggers on
            # glyph sequence [A, B, C, D, E] and another action triggers
            # on [C, D], we return result=[A, B, C, D, E] (as list of
            # encoded glyph IDs), and actionIndex={('A','B','C','D','E'): 0,
            # ('C','D'): 2}.
            if action in actionIndex:
                continue
            for start in range(0, len(action)):
                startIndex = (len(result) // 2) + start
                for limit in range(start, len(action)):
                    glyphs = action[start : limit + 1]
                    actionIndex.setdefault(glyphs, startIndex)
            for glyph in action:
                glyphID = font.getGlyphID(glyph)
                result += struct.pack(">H", glyphID)
        return result, actionIndex


class FeatureParams(BaseTable):
    def compile(self, writer, font):
        assert (
            featureParamTypes.get(writer["FeatureTag"]) == self.__class__
        ), "Wrong FeatureParams type for feature '%s': %s" % (
            writer["FeatureTag"],
            self.__class__.__name__,
        )
        BaseTable.compile(self, writer, font)

    def toXML(self, xmlWriter, font, attrs=None, name=None):
        BaseTable.toXML(self, xmlWriter, font, attrs, name=self.__class__.__name__)


class FeatureParamsSize(FeatureParams):
    pass


class FeatureParamsStylisticSet(FeatureParams):
    pass


class FeatureParamsCharacterVariants(FeatureParams):
    pass


class Coverage(FormatSwitchingBaseTable):
    # manual implementation to get rid of glyphID dependencies

    def populateDefaults(self, propagator=None):
        if not hasattr(self, "glyphs"):
            self.glyphs = []

    def postRead(self, rawTable, font):
        if self.Format == 1:
            self.glyphs = rawTable["GlyphArray"]
        elif self.Format == 2:
            glyphs = self.glyphs = []
            ranges = rawTable["RangeRecord"]
            # Some SIL fonts have coverage entries that don't have sorted
            # StartCoverageIndex.  If it is so, fixup and warn.  We undo
            # this when writing font out.
            sorted_ranges = sorted(ranges, key=lambda a: a.StartCoverageIndex)
            if ranges != sorted_ranges:
                log.warning("GSUB/GPOS Coverage is not sorted by glyph ids.")
                ranges = sorted_ranges
            del sorted_ranges
            for r in ranges:
                start = r.Start
                end = r.End
                startID = font.getGlyphID(start)
                endID = font.getGlyphID(end) + 1
                glyphs.extend(font.getGlyphNameMany(range(startID, endID)))
        else:
            self.glyphs = []
            log.warning("Unknown Coverage format: %s", self.Format)
        del self.Format  # Don't need this anymore

    def preWrite(self, font):
        glyphs = getattr(self, "glyphs", None)
        if glyphs is None:
            glyphs = self.glyphs = []
        format = 1
        rawTable = {"GlyphArray": glyphs}
        if glyphs:
            # find out whether Format 2 is more compact or not
            glyphIDs = font.getGlyphIDMany(glyphs)
            brokenOrder = sorted(glyphIDs) != glyphIDs

            last = glyphIDs[0]
            ranges = [[last]]
            for glyphID in glyphIDs[1:]:
                if glyphID != last + 1:
                    ranges[-1].append(last)
                    ranges.append([glyphID])
                last = glyphID
            ranges[-1].append(last)

            if brokenOrder or len(ranges) * 3 < len(glyphs):  # 3 words vs. 1 word
                # Format 2 is more compact
                index = 0
                for i, (start, end) in enumerate(ranges):
                    r = RangeRecord()
                    r.StartID = start
                    r.Start = font.getGlyphName(start)
                    r.End = font.getGlyphName(end)
                    r.StartCoverageIndex = index
                    ranges[i] = r
                    index = index + end - start + 1
                if brokenOrder:
                    log.warning("GSUB/GPOS Coverage is not sorted by glyph ids.")
                    ranges.sort(key=lambda a: a.StartID)
                for r in ranges:
                    del r.StartID
                format = 2
                rawTable = {"RangeRecord": ranges}
            # else:
            # 	fallthrough; Format 1 is more compact
        self.Format = format
        return rawTable

    def toXML2(self, xmlWriter, font):
        for glyphName in getattr(self, "glyphs", []):
            xmlWriter.simpletag("Glyph", value=glyphName)
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        glyphs = getattr(self, "glyphs", None)
        if glyphs is None:
            glyphs = []
            self.glyphs = glyphs
        glyphs.append(attrs["value"])


# The special 0xFFFFFFFF delta-set index is used to indicate that there
# is no variation data in the ItemVariationStore for a given variable field
NO_VARIATION_INDEX = 0xFFFFFFFF


class DeltaSetIndexMap(getFormatSwitchingBaseTableClass("uint8")):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "mapping"):
            self.mapping = []

    def postRead(self, rawTable, font):
        assert (rawTable["EntryFormat"] & 0xFFC0) == 0
        self.mapping = rawTable["mapping"]

    @staticmethod
    def getEntryFormat(mapping):
        ored = 0
        for idx in mapping:
            ored |= idx

        inner = ored & 0xFFFF
        innerBits = 0
        while inner:
            innerBits += 1
            inner >>= 1
        innerBits = max(innerBits, 1)
        assert innerBits <= 16

        ored = (ored >> (16 - innerBits)) | (ored & ((1 << innerBits) - 1))
        if ored <= 0x000000FF:
            entrySize = 1
        elif ored <= 0x0000FFFF:
            entrySize = 2
        elif ored <= 0x00FFFFFF:
            entrySize = 3
        else:
            entrySize = 4

        return ((entrySize - 1) << 4) | (innerBits - 1)

    def preWrite(self, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = self.mapping = []
        self.Format = 1 if len(mapping) > 0xFFFF else 0
        rawTable = self.__dict__.copy()
        rawTable["MappingCount"] = len(mapping)
        rawTable["EntryFormat"] = self.getEntryFormat(mapping)
        return rawTable

    def toXML2(self, xmlWriter, font):
        # Make xml dump less verbose, by omitting no-op entries like:
        #   <Map index="..." outer="65535" inner="65535"/>
        xmlWriter.comment("Omitted values default to 0xFFFF/0xFFFF (no variations)")
        xmlWriter.newline()
        for i, value in enumerate(getattr(self, "mapping", [])):
            attrs = [("index", i)]
            if value != NO_VARIATION_INDEX:
                attrs.extend(
                    [
                        ("outer", value >> 16),
                        ("inner", value & 0xFFFF),
                    ]
                )
            xmlWriter.simpletag("Map", attrs)
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            self.mapping = mapping = []
        index = safeEval(attrs["index"])
        outer = safeEval(attrs.get("outer", "0xFFFF"))
        inner = safeEval(attrs.get("inner", "0xFFFF"))
        assert inner <= 0xFFFF
        mapping.insert(index, (outer << 16) | inner)

    def __getitem__(self, i):
        return self.mapping[i] if i < len(self.mapping) else NO_VARIATION_INDEX


class VarIdxMap(BaseTable):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "mapping"):
            self.mapping = {}

    def postRead(self, rawTable, font):
        assert (rawTable["EntryFormat"] & 0xFFC0) == 0
        glyphOrder = font.getGlyphOrder()
        mapList = rawTable["mapping"]
        mapList.extend([mapList[-1]] * (len(glyphOrder) - len(mapList)))
        self.mapping = dict(zip(glyphOrder, mapList))

    def preWrite(self, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = self.mapping = {}

        glyphOrder = font.getGlyphOrder()
        mapping = [mapping[g] for g in glyphOrder]
        while len(mapping) > 1 and mapping[-2] == mapping[-1]:
            del mapping[-1]

        rawTable = {"mapping": mapping}
        rawTable["MappingCount"] = len(mapping)
        rawTable["EntryFormat"] = DeltaSetIndexMap.getEntryFormat(mapping)
        return rawTable

    def toXML2(self, xmlWriter, font):
        for glyph, value in sorted(getattr(self, "mapping", {}).items()):
            attrs = (
                ("glyph", glyph),
                ("outer", value >> 16),
                ("inner", value & 0xFFFF),
            )
            xmlWriter.simpletag("Map", attrs)
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = {}
            self.mapping = mapping
        try:
            glyph = attrs["glyph"]
        except:  # https://github.com/fonttools/fonttools/commit/21cbab8ce9ded3356fef3745122da64dcaf314e9#commitcomment-27649836
            glyph = font.getGlyphOrder()[attrs["index"]]
        outer = safeEval(attrs["outer"])
        inner = safeEval(attrs["inner"])
        assert inner <= 0xFFFF
        mapping[glyph] = (outer << 16) | inner

    def __getitem__(self, glyphName):
        return self.mapping.get(glyphName, NO_VARIATION_INDEX)


class VarRegionList(BaseTable):
    def preWrite(self, font):
        # The OT spec says VarStore.VarRegionList.RegionAxisCount should always
        # be equal to the fvar.axisCount, and OTS < v8.0.0 enforces this rule
        # even when the VarRegionList is empty. We can't treat RegionAxisCount
        # like a normal propagated count (== len(Region[i].VarRegionAxis)),
        # otherwise it would default to 0 if VarRegionList is empty.
        # Thus, we force it to always be equal to fvar.axisCount.
        # https://github.com/khaledhosny/ots/pull/192
        fvarTable = font.get("fvar")
        if fvarTable:
            self.RegionAxisCount = len(fvarTable.axes)
        return {
            **self.__dict__,
            "RegionAxisCount": CountReference(self.__dict__, "RegionAxisCount"),
        }


class SingleSubst(FormatSwitchingBaseTable):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "mapping"):
            self.mapping = {}

    def postRead(self, rawTable, font):
        mapping = {}
        input = _getGlyphsFromCoverageTable(rawTable["Coverage"])
        if self.Format == 1:
            delta = rawTable["DeltaGlyphID"]
            inputGIDS = font.getGlyphIDMany(input)
            outGIDS = [(glyphID + delta) % 65536 for glyphID in inputGIDS]
            outNames = font.getGlyphNameMany(outGIDS)
            for inp, out in zip(input, outNames):
                mapping[inp] = out
        elif self.Format == 2:
            assert (
                len(input) == rawTable["GlyphCount"]
            ), "invalid SingleSubstFormat2 table"
            subst = rawTable["Substitute"]
            for inp, sub in zip(input, subst):
                mapping[inp] = sub
        else:
            assert 0, "unknown format: %s" % self.Format
        self.mapping = mapping
        del self.Format  # Don't need this anymore

    def preWrite(self, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = self.mapping = {}
        items = list(mapping.items())
        getGlyphID = font.getGlyphID
        gidItems = [(getGlyphID(a), getGlyphID(b)) for a, b in items]
        sortableItems = sorted(zip(gidItems, items))

        # figure out format
        format = 2
        delta = None
        for inID, outID in gidItems:
            if delta is None:
                delta = (outID - inID) % 65536

            if (inID + delta) % 65536 != outID:
                break
        else:
            if delta is None:
                # the mapping is empty, better use format 2
                format = 2
            else:
                format = 1

        rawTable = {}
        self.Format = format
        cov = Coverage()
        input = [item[1][0] for item in sortableItems]
        subst = [item[1][1] for item in sortableItems]
        cov.glyphs = input
        rawTable["Coverage"] = cov
        if format == 1:
            assert delta is not None
            rawTable["DeltaGlyphID"] = delta
        else:
            rawTable["Substitute"] = subst
        return rawTable

    def toXML2(self, xmlWriter, font):
        items = sorted(self.mapping.items())
        for inGlyph, outGlyph in items:
            xmlWriter.simpletag("Substitution", [("in", inGlyph), ("out", outGlyph)])
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = {}
            self.mapping = mapping
        mapping[attrs["in"]] = attrs["out"]


class MultipleSubst(FormatSwitchingBaseTable):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "mapping"):
            self.mapping = {}

    def postRead(self, rawTable, font):
        mapping = {}
        if self.Format == 1:
            glyphs = _getGlyphsFromCoverageTable(rawTable["Coverage"])
            subst = [s.Substitute for s in rawTable["Sequence"]]
            mapping = dict(zip(glyphs, subst))
        else:
            assert 0, "unknown format: %s" % self.Format
        self.mapping = mapping
        del self.Format  # Don't need this anymore

    def preWrite(self, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = self.mapping = {}
        cov = Coverage()
        cov.glyphs = sorted(list(mapping.keys()), key=font.getGlyphID)
        self.Format = 1
        rawTable = {
            "Coverage": cov,
            "Sequence": [self.makeSequence_(mapping[glyph]) for glyph in cov.glyphs],
        }
        return rawTable

    def toXML2(self, xmlWriter, font):
        items = sorted(self.mapping.items())
        for inGlyph, outGlyphs in items:
            out = ",".join(outGlyphs)
            xmlWriter.simpletag("Substitution", [("in", inGlyph), ("out", out)])
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        mapping = getattr(self, "mapping", None)
        if mapping is None:
            mapping = {}
            self.mapping = mapping

        # TTX v3.0 and earlier.
        if name == "Coverage":
            self.old_coverage_ = []
            for element in content:
                if not isinstance(element, tuple):
                    continue
                element_name, element_attrs, _ = element
                if element_name == "Glyph":
                    self.old_coverage_.append(element_attrs["value"])
            return
        if name == "Sequence":
            index = int(attrs.get("index", len(mapping)))
            glyph = self.old_coverage_[index]
            glyph_mapping = mapping[glyph] = []
            for element in content:
                if not isinstance(element, tuple):
                    continue
                element_name, element_attrs, _ = element
                if element_name == "Substitute":
                    glyph_mapping.append(element_attrs["value"])
            return

            # TTX v3.1 and later.
        outGlyphs = attrs["out"].split(",") if attrs["out"] else []
        mapping[attrs["in"]] = [g.strip() for g in outGlyphs]

    @staticmethod
    def makeSequence_(g):
        seq = Sequence()
        seq.Substitute = g
        return seq


class ClassDef(FormatSwitchingBaseTable):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "classDefs"):
            self.classDefs = {}

    def postRead(self, rawTable, font):
        classDefs = {}

        if self.Format == 1:
            start = rawTable["StartGlyph"]
            classList = rawTable["ClassValueArray"]
            startID = font.getGlyphID(start)
            endID = startID + len(classList)
            glyphNames = font.getGlyphNameMany(range(startID, endID))
            for glyphName, cls in zip(glyphNames, classList):
                if cls:
                    classDefs[glyphName] = cls

        elif self.Format == 2:
            records = rawTable["ClassRangeRecord"]
            for rec in records:
                cls = rec.Class
                if not cls:
                    continue
                start = rec.Start
                end = rec.End
                startID = font.getGlyphID(start)
                endID = font.getGlyphID(end) + 1
                glyphNames = font.getGlyphNameMany(range(startID, endID))
                for glyphName in glyphNames:
                    classDefs[glyphName] = cls
        else:
            log.warning("Unknown ClassDef format: %s", self.Format)
        self.classDefs = classDefs
        del self.Format  # Don't need this anymore

    def _getClassRanges(self, font):
        classDefs = getattr(self, "classDefs", None)
        if classDefs is None:
            self.classDefs = {}
            return
        getGlyphID = font.getGlyphID
        items = []
        for glyphName, cls in classDefs.items():
            if not cls:
                continue
            items.append((getGlyphID(glyphName), glyphName, cls))
        if items:
            items.sort()
            last, lastName, lastCls = items[0]
            ranges = [[lastCls, last, lastName]]
            for glyphID, glyphName, cls in items[1:]:
                if glyphID != last + 1 or cls != lastCls:
                    ranges[-1].extend([last, lastName])
                    ranges.append([cls, glyphID, glyphName])
                last = glyphID
                lastName = glyphName
                lastCls = cls
            ranges[-1].extend([last, lastName])
            return ranges

    def preWrite(self, font):
        format = 2
        rawTable = {"ClassRangeRecord": []}
        ranges = self._getClassRanges(font)
        if ranges:
            startGlyph = ranges[0][1]
            endGlyph = ranges[-1][3]
            glyphCount = endGlyph - startGlyph + 1
            if len(ranges) * 3 < glyphCount + 1:
                # Format 2 is more compact
                for i, (cls, start, startName, end, endName) in enumerate(ranges):
                    rec = ClassRangeRecord()
                    rec.Start = startName
                    rec.End = endName
                    rec.Class = cls
                    ranges[i] = rec
                format = 2
                rawTable = {"ClassRangeRecord": ranges}
            else:
                # Format 1 is more compact
                startGlyphName = ranges[0][2]
                classes = [0] * glyphCount
                for cls, start, startName, end, endName in ranges:
                    for g in range(start - startGlyph, end - startGlyph + 1):
                        classes[g] = cls
                format = 1
                rawTable = {"StartGlyph": startGlyphName, "ClassValueArray": classes}
        self.Format = format
        return rawTable

    def toXML2(self, xmlWriter, font):
        items = sorted(self.classDefs.items())
        for glyphName, cls in items:
            xmlWriter.simpletag("ClassDef", [("glyph", glyphName), ("class", cls)])
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        classDefs = getattr(self, "classDefs", None)
        if classDefs is None:
            classDefs = {}
            self.classDefs = classDefs
        classDefs[attrs["glyph"]] = int(attrs["class"])


class AlternateSubst(FormatSwitchingBaseTable):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "alternates"):
            self.alternates = {}

    def postRead(self, rawTable, font):
        alternates = {}
        if self.Format == 1:
            input = _getGlyphsFromCoverageTable(rawTable["Coverage"])
            alts = rawTable["AlternateSet"]
            assert len(input) == len(alts)
            for inp, alt in zip(input, alts):
                alternates[inp] = alt.Alternate
        else:
            assert 0, "unknown format: %s" % self.Format
        self.alternates = alternates
        del self.Format  # Don't need this anymore

    def preWrite(self, font):
        self.Format = 1
        alternates = getattr(self, "alternates", None)
        if alternates is None:
            alternates = self.alternates = {}
        items = list(alternates.items())
        for i, (glyphName, set) in enumerate(items):
            items[i] = font.getGlyphID(glyphName), glyphName, set
        items.sort()
        cov = Coverage()
        cov.glyphs = [item[1] for item in items]
        alternates = []
        setList = [item[-1] for item in items]
        for set in setList:
            alts = AlternateSet()
            alts.Alternate = set
            alternates.append(alts)
        # a special case to deal with the fact that several hundred Adobe Japan1-5
        # CJK fonts will overflow an offset if the coverage table isn't pushed to the end.
        # Also useful in that when splitting a sub-table because of an offset overflow
        # I don't need to calculate the change in the subtable offset due to the change in the coverage table size.
        # Allows packing more rules in subtable.
        self.sortCoverageLast = 1
        return {"Coverage": cov, "AlternateSet": alternates}

    def toXML2(self, xmlWriter, font):
        items = sorted(self.alternates.items())
        for glyphName, alternates in items:
            xmlWriter.begintag("AlternateSet", glyph=glyphName)
            xmlWriter.newline()
            for alt in alternates:
                xmlWriter.simpletag("Alternate", glyph=alt)
                xmlWriter.newline()
            xmlWriter.endtag("AlternateSet")
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        alternates = getattr(self, "alternates", None)
        if alternates is None:
            alternates = {}
            self.alternates = alternates
        glyphName = attrs["glyph"]
        set = []
        alternates[glyphName] = set
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            set.append(attrs["glyph"])


class LigatureSubst(FormatSwitchingBaseTable):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "ligatures"):
            self.ligatures = {}

    def postRead(self, rawTable, font):
        ligatures = {}
        if self.Format == 1:
            input = _getGlyphsFromCoverageTable(rawTable["Coverage"])
            ligSets = rawTable["LigatureSet"]
            assert len(input) == len(ligSets)
            for i, inp in enumerate(input):
                ligatures[inp] = ligSets[i].Ligature
        else:
            assert 0, "unknown format: %s" % self.Format
        self.ligatures = ligatures
        del self.Format  # Don't need this anymore

    @staticmethod
    def _getLigatureSortKey(components):
        # Computes a key for ordering ligatures in a GSUB Type-4 lookup.

        # When building the OpenType lookup, we need to make sure that
        # the longest sequence of components is listed first, so we
        # use the negative length as the key for sorting.
        # Note, we no longer need to worry about deterministic order because the
        # ligature mapping `dict` remembers the insertion order, and this in
        # turn depends on the order in which the ligatures are written in the FEA.
        # Since python sort algorithm is stable, the ligatures of equal length
        # will keep the relative order in which they appear in the feature file.
        # For example, given the following ligatures (all starting with 'f' and
        # thus belonging to the same LigatureSet):
        #
        #   feature liga {
        #     sub f i by f_i;
        #     sub f f f by f_f_f;
        #     sub f f by f_f;
        #     sub f f i by f_f_i;
        #   } liga;
        #
        # this should sort to: f_f_f, f_f_i, f_i, f_f
        # This is also what fea-rs does, see:
        # https://github.com/adobe-type-tools/afdko/issues/1727
        # https://github.com/fonttools/fonttools/issues/3428
        # https://github.com/googlefonts/fontc/pull/680
        return -len(components)

    def preWrite(self, font):
        self.Format = 1
        ligatures = getattr(self, "ligatures", None)
        if ligatures is None:
            ligatures = self.ligatures = {}

        if ligatures and isinstance(next(iter(ligatures)), tuple):
            # New high-level API in v3.1 and later.  Note that we just support compiling this
            # for now.  We don't load to this API, and don't do XML with it.

            # ligatures is map from components-sequence to lig-glyph
            newLigatures = dict()
            for comps in sorted(ligatures.keys(), key=self._getLigatureSortKey):
                ligature = Ligature()
                ligature.Component = comps[1:]
                ligature.CompCount = len(comps)
                ligature.LigGlyph = ligatures[comps]
                newLigatures.setdefault(comps[0], []).append(ligature)
            ligatures = newLigatures

        items = list(ligatures.items())
        for i, (glyphName, set) in enumerate(items):
            items[i] = font.getGlyphID(glyphName), glyphName, set
        items.sort()
        cov = Coverage()
        cov.glyphs = [item[1] for item in items]

        ligSets = []
        setList = [item[-1] for item in items]
        for set in setList:
            ligSet = LigatureSet()
            ligs = ligSet.Ligature = []
            for lig in set:
                ligs.append(lig)
            ligSets.append(ligSet)
        # Useful in that when splitting a sub-table because of an offset overflow
        # I don't need to calculate the change in subtabl offset due to the coverage table size.
        # Allows packing more rules in subtable.
        self.sortCoverageLast = 1
        return {"Coverage": cov, "LigatureSet": ligSets}

    def toXML2(self, xmlWriter, font):
        items = sorted(self.ligatures.items())
        for glyphName, ligSets in items:
            xmlWriter.begintag("LigatureSet", glyph=glyphName)
            xmlWriter.newline()
            for lig in ligSets:
                xmlWriter.simpletag(
                    "Ligature", glyph=lig.LigGlyph, components=",".join(lig.Component)
                )
                xmlWriter.newline()
            xmlWriter.endtag("LigatureSet")
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        ligatures = getattr(self, "ligatures", None)
        if ligatures is None:
            ligatures = {}
            self.ligatures = ligatures
        glyphName = attrs["glyph"]
        ligs = []
        ligatures[glyphName] = ligs
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            lig = Ligature()
            lig.LigGlyph = attrs["glyph"]
            components = attrs["components"]
            lig.Component = components.split(",") if components else []
            lig.CompCount = len(lig.Component)
            ligs.append(lig)


class COLR(BaseTable):
    def decompile(self, reader, font):
        # COLRv0 is exceptional in that LayerRecordCount appears *after* the
        # LayerRecordArray it counts, but the parser logic expects Count fields
        # to always precede the arrays. Here we work around this by parsing the
        # LayerRecordCount before the rest of the table, and storing it in
        # the reader's local state.
        subReader = reader.getSubReader(offset=0)
        for conv in self.getConverters():
            if conv.name != "LayerRecordCount":
                subReader.advance(conv.staticSize)
                continue
            reader[conv.name] = conv.read(subReader, font, tableDict={})
            break
        else:
            raise AssertionError("LayerRecordCount converter not found")
        return BaseTable.decompile(self, reader, font)

    def preWrite(self, font):
        # The writer similarly assumes Count values precede the things counted,
        # thus here we pre-initialize a CountReference; the actual count value
        # will be set to the lenght of the array by the time this is assembled.
        self.LayerRecordCount = None
        return {
            **self.__dict__,
            "LayerRecordCount": CountReference(self.__dict__, "LayerRecordCount"),
        }

    def computeClipBoxes(self, glyphSet: "_TTGlyphSet", quantization: int = 1):
        if self.Version == 0:
            return

        clips = {}
        for rec in self.BaseGlyphList.BaseGlyphPaintRecord:
            try:
                clipBox = rec.Paint.computeClipBox(self, glyphSet, quantization)
            except Exception as e:
                from fontTools.ttLib import TTLibError

                raise TTLibError(
                    f"Failed to compute COLR ClipBox for {rec.BaseGlyph!r}"
                ) from e

            if clipBox is not None:
                clips[rec.BaseGlyph] = clipBox

        hasClipList = hasattr(self, "ClipList") and self.ClipList is not None
        if not clips:
            if hasClipList:
                self.ClipList = None
        else:
            if not hasClipList:
                self.ClipList = ClipList()
                self.ClipList.Format = 1
            self.ClipList.clips = clips


class LookupList(BaseTable):
    @property
    def table(self):
        for l in self.Lookup:
            for st in l.SubTable:
                if type(st).__name__.endswith("Subst"):
                    return "GSUB"
                if type(st).__name__.endswith("Pos"):
                    return "GPOS"
        raise ValueError

    def toXML2(self, xmlWriter, font):
        if (
            not font
            or "Debg" not in font
            or LOOKUP_DEBUG_INFO_KEY not in font["Debg"].data
        ):
            return super().toXML2(xmlWriter, font)
        debugData = font["Debg"].data[LOOKUP_DEBUG_INFO_KEY][self.table]
        for conv in self.getConverters():
            if conv.repeat:
                value = getattr(self, conv.name, [])
                for lookupIndex, item in enumerate(value):
                    if str(lookupIndex) in debugData:
                        info = LookupDebugInfo(*debugData[str(lookupIndex)])
                        tag = info.location
                        if info.name:
                            tag = f"{info.name}: {tag}"
                        if info.feature:
                            script, language, feature = info.feature
                            tag = f"{tag} in {feature} ({script}/{language})"
                        xmlWriter.comment(tag)
                        xmlWriter.newline()

                    conv.xmlWrite(
                        xmlWriter, font, item, conv.name, [("index", lookupIndex)]
                    )
            else:
                if conv.aux and not eval(conv.aux, None, vars(self)):
                    continue
                value = getattr(
                    self, conv.name, None
                )  # TODO Handle defaults instead of defaulting to None!
                conv.xmlWrite(xmlWriter, font, value, conv.name, [])


class BaseGlyphRecordArray(BaseTable):
    def preWrite(self, font):
        self.BaseGlyphRecord = sorted(
            self.BaseGlyphRecord, key=lambda rec: font.getGlyphID(rec.BaseGlyph)
        )
        return self.__dict__.copy()


class BaseGlyphList(BaseTable):
    def preWrite(self, font):
        self.BaseGlyphPaintRecord = sorted(
            self.BaseGlyphPaintRecord, key=lambda rec: font.getGlyphID(rec.BaseGlyph)
        )
        return self.__dict__.copy()


class ClipBoxFormat(IntEnum):
    Static = 1
    Variable = 2

    def is_variable(self):
        return self is self.Variable

    def as_variable(self):
        return self.Variable


class ClipBox(getFormatSwitchingBaseTableClass("uint8")):
    formatEnum = ClipBoxFormat

    def as_tuple(self):
        return tuple(getattr(self, conv.name) for conv in self.getConverters())

    def __repr__(self):
        return f"{self.__class__.__name__}{self.as_tuple()}"


class ClipList(getFormatSwitchingBaseTableClass("uint8")):
    def populateDefaults(self, propagator=None):
        if not hasattr(self, "clips"):
            self.clips = {}

    def postRead(self, rawTable, font):
        clips = {}
        glyphOrder = font.getGlyphOrder()
        for i, rec in enumerate(rawTable["ClipRecord"]):
            if rec.StartGlyphID > rec.EndGlyphID:
                log.warning(
                    "invalid ClipRecord[%i].StartGlyphID (%i) > "
                    "EndGlyphID (%i); skipped",
                    i,
                    rec.StartGlyphID,
                    rec.EndGlyphID,
                )
                continue
            redefinedGlyphs = []
            missingGlyphs = []
            for glyphID in range(rec.StartGlyphID, rec.EndGlyphID + 1):
                try:
                    glyph = glyphOrder[glyphID]
                except IndexError:
                    missingGlyphs.append(glyphID)
                    continue
                if glyph not in clips:
                    clips[glyph] = copy.copy(rec.ClipBox)
                else:
                    redefinedGlyphs.append(glyphID)
            if redefinedGlyphs:
                log.warning(
                    "ClipRecord[%i] overlaps previous records; "
                    "ignoring redefined clip boxes for the "
                    "following glyph ID range: [%i-%i]",
                    i,
                    min(redefinedGlyphs),
                    max(redefinedGlyphs),
                )
            if missingGlyphs:
                log.warning(
                    "ClipRecord[%i] range references missing " "glyph IDs: [%i-%i]",
                    i,
                    min(missingGlyphs),
                    max(missingGlyphs),
                )
        self.clips = clips

    def groups(self):
        glyphsByClip = defaultdict(list)
        uniqueClips = {}
        for glyphName, clipBox in self.clips.items():
            key = clipBox.as_tuple()
            glyphsByClip[key].append(glyphName)
            if key not in uniqueClips:
                uniqueClips[key] = clipBox
        return {
            frozenset(glyphs): uniqueClips[key] for key, glyphs in glyphsByClip.items()
        }

    def preWrite(self, font):
        if not hasattr(self, "clips"):
            self.clips = {}
        clipBoxRanges = {}
        glyphMap = font.getReverseGlyphMap()
        for glyphs, clipBox in self.groups().items():
            glyphIDs = sorted(
                glyphMap[glyphName] for glyphName in glyphs if glyphName in glyphMap
            )
            if not glyphIDs:
                continue
            last = glyphIDs[0]
            ranges = [[last]]
            for glyphID in glyphIDs[1:]:
                if glyphID != last + 1:
                    ranges[-1].append(last)
                    ranges.append([glyphID])
                last = glyphID
            ranges[-1].append(last)
            for start, end in ranges:
                assert (start, end) not in clipBoxRanges
                clipBoxRanges[(start, end)] = clipBox

        clipRecords = []
        for (start, end), clipBox in sorted(clipBoxRanges.items()):
            record = ClipRecord()
            record.StartGlyphID = start
            record.EndGlyphID = end
            record.ClipBox = clipBox
            clipRecords.append(record)
        rawTable = {
            "ClipCount": len(clipRecords),
            "ClipRecord": clipRecords,
        }
        return rawTable

    def toXML(self, xmlWriter, font, attrs=None, name=None):
        tableName = name if name else self.__class__.__name__
        if attrs is None:
            attrs = []
        if hasattr(self, "Format"):
            attrs.append(("Format", self.Format))
        xmlWriter.begintag(tableName, attrs)
        xmlWriter.newline()
        # sort clips alphabetically to ensure deterministic XML dump
        for glyphs, clipBox in sorted(
            self.groups().items(), key=lambda item: min(item[0])
        ):
            xmlWriter.begintag("Clip")
            xmlWriter.newline()
            for glyphName in sorted(glyphs):
                xmlWriter.simpletag("Glyph", value=glyphName)
                xmlWriter.newline()
            xmlWriter.begintag("ClipBox", [("Format", clipBox.Format)])
            xmlWriter.newline()
            clipBox.toXML2(xmlWriter, font)
            xmlWriter.endtag("ClipBox")
            xmlWriter.newline()
            xmlWriter.endtag("Clip")
            xmlWriter.newline()
        xmlWriter.endtag(tableName)
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        clips = getattr(self, "clips", None)
        if clips is None:
            self.clips = clips = {}
        assert name == "Clip"
        glyphs = []
        clipBox = None
        for elem in content:
            if not isinstance(elem, tuple):
                continue
            name, attrs, content = elem
            if name == "Glyph":
                glyphs.append(attrs["value"])
            elif name == "ClipBox":
                clipBox = ClipBox()
                clipBox.Format = safeEval(attrs["Format"])
                for elem in content:
                    if not isinstance(elem, tuple):
                        continue
                    name, attrs, content = elem
                    clipBox.fromXML(name, attrs, content, font)
        if clipBox:
            for glyphName in glyphs:
                clips[glyphName] = clipBox


class ExtendMode(IntEnum):
    PAD = 0
    REPEAT = 1
    REFLECT = 2


# Porter-Duff modes for COLRv1 PaintComposite:
# https://github.com/googlefonts/colr-gradients-spec/tree/off_sub_1#compositemode-enumeration
class CompositeMode(IntEnum):
    CLEAR = 0
    SRC = 1
    DEST = 2
    SRC_OVER = 3
    DEST_OVER = 4
    SRC_IN = 5
    DEST_IN = 6
    SRC_OUT = 7
    DEST_OUT = 8
    SRC_ATOP = 9
    DEST_ATOP = 10
    XOR = 11
    PLUS = 12
    SCREEN = 13
    OVERLAY = 14
    DARKEN = 15
    LIGHTEN = 16
    COLOR_DODGE = 17
    COLOR_BURN = 18
    HARD_LIGHT = 19
    SOFT_LIGHT = 20
    DIFFERENCE = 21
    EXCLUSION = 22
    MULTIPLY = 23
    HSL_HUE = 24
    HSL_SATURATION = 25
    HSL_COLOR = 26
    HSL_LUMINOSITY = 27


class PaintFormat(IntEnum):
    PaintColrLayers = 1
    PaintSolid = 2
    PaintVarSolid = 3
    PaintLinearGradient = 4
    PaintVarLinearGradient = 5
    PaintRadialGradient = 6
    PaintVarRadialGradient = 7
    PaintSweepGradient = 8
    PaintVarSweepGradient = 9
    PaintGlyph = 10
    PaintColrGlyph = 11
    PaintTransform = 12
    PaintVarTransform = 13
    PaintTranslate = 14
    PaintVarTranslate = 15
    PaintScale = 16
    PaintVarScale = 17
    PaintScaleAroundCenter = 18
    PaintVarScaleAroundCenter = 19
    PaintScaleUniform = 20
    PaintVarScaleUniform = 21
    PaintScaleUniformAroundCenter = 22
    PaintVarScaleUniformAroundCenter = 23
    PaintRotate = 24
    PaintVarRotate = 25
    PaintRotateAroundCenter = 26
    PaintVarRotateAroundCenter = 27
    PaintSkew = 28
    PaintVarSkew = 29
    PaintSkewAroundCenter = 30
    PaintVarSkewAroundCenter = 31
    PaintComposite = 32

    def is_variable(self):
        return self.name.startswith("PaintVar")

    def as_variable(self):
        if self.is_variable():
            return self
        try:
            return PaintFormat.__members__[f"PaintVar{self.name[5:]}"]
        except KeyError:
            return None


class Paint(getFormatSwitchingBaseTableClass("uint8")):
    formatEnum = PaintFormat

    def getFormatName(self):
        try:
            return self.formatEnum(self.Format).name
        except ValueError:
            raise NotImplementedError(f"Unknown Paint format: {self.Format}")

    def toXML(self, xmlWriter, font, attrs=None, name=None):
        tableName = name if name else self.__class__.__name__
        if attrs is None:
            attrs = []
        attrs.append(("Format", self.Format))
        xmlWriter.begintag(tableName, attrs)
        xmlWriter.comment(self.getFormatName())
        xmlWriter.newline()
        self.toXML2(xmlWriter, font)
        xmlWriter.endtag(tableName)
        xmlWriter.newline()

    def iterPaintSubTables(self, colr: COLR) -> Iterator[BaseTable.SubTableEntry]:
        if self.Format == PaintFormat.PaintColrLayers:
            # https://github.com/fonttools/fonttools/issues/2438: don't die when no LayerList exists
            layers = []
            if colr.LayerList is not None:
                layers = colr.LayerList.Paint
            yield from (
                BaseTable.SubTableEntry(name="Layers", value=v, index=i)
                for i, v in enumerate(
                    layers[self.FirstLayerIndex : self.FirstLayerIndex + self.NumLayers]
                )
            )
            return

        if self.Format == PaintFormat.PaintColrGlyph:
            for record in colr.BaseGlyphList.BaseGlyphPaintRecord:
                if record.BaseGlyph == self.Glyph:
                    yield BaseTable.SubTableEntry(name="BaseGlyph", value=record.Paint)
                    return
            else:
                raise KeyError(f"{self.Glyph!r} not in colr.BaseGlyphList")

        for conv in self.getConverters():
            if conv.tableClass is not None and issubclass(conv.tableClass, type(self)):
                value = getattr(self, conv.name)
                yield BaseTable.SubTableEntry(name=conv.name, value=value)

    def getChildren(self, colr) -> List["Paint"]:
        # this is kept for backward compatibility (e.g. it's used by the subsetter)
        return [p.value for p in self.iterPaintSubTables(colr)]

    def traverse(self, colr: COLR, callback):
        """Depth-first traversal of graph rooted at self, callback on each node."""
        if not callable(callback):
            raise TypeError("callback must be callable")

        for path in dfs_base_table(
            self, iter_subtables_fn=lambda paint: paint.iterPaintSubTables(colr)
        ):
            paint = path[-1].value
            callback(paint)

    def getTransform(self) -> Transform:
        if self.Format == PaintFormat.PaintTransform:
            t = self.Transform
            return Transform(t.xx, t.yx, t.xy, t.yy, t.dx, t.dy)
        elif self.Format == PaintFormat.PaintTranslate:
            return Identity.translate(self.dx, self.dy)
        elif self.Format == PaintFormat.PaintScale:
            return Identity.scale(self.scaleX, self.scaleY)
        elif self.Format == PaintFormat.PaintScaleAroundCenter:
            return (
                Identity.translate(self.centerX, self.centerY)
                .scale(self.scaleX, self.scaleY)
                .translate(-self.centerX, -self.centerY)
            )
        elif self.Format == PaintFormat.PaintScaleUniform:
            return Identity.scale(self.scale)
        elif self.Format == PaintFormat.PaintScaleUniformAroundCenter:
            return (
                Identity.translate(self.centerX, self.centerY)
                .scale(self.scale)
                .translate(-self.centerX, -self.centerY)
            )
        elif self.Format == PaintFormat.PaintRotate:
            return Identity.rotate(radians(self.angle))
        elif self.Format == PaintFormat.PaintRotateAroundCenter:
            return (
                Identity.translate(self.centerX, self.centerY)
                .rotate(radians(self.angle))
                .translate(-self.centerX, -self.centerY)
            )
        elif self.Format == PaintFormat.PaintSkew:
            return Identity.skew(radians(-self.xSkewAngle), radians(self.ySkewAngle))
        elif self.Format == PaintFormat.PaintSkewAroundCenter:
            return (
                Identity.translate(self.centerX, self.centerY)
                .skew(radians(-self.xSkewAngle), radians(self.ySkewAngle))
                .translate(-self.centerX, -self.centerY)
            )
        if PaintFormat(self.Format).is_variable():
            raise NotImplementedError(f"Variable Paints not supported: {self.Format}")

        return Identity

    def computeClipBox(
        self, colr: COLR, glyphSet: "_TTGlyphSet", quantization: int = 1
    ) -> Optional[ClipBox]:
        pen = ControlBoundsPen(glyphSet)
        for path in dfs_base_table(
            self, iter_subtables_fn=lambda paint: paint.iterPaintSubTables(colr)
        ):
            paint = path[-1].value
            if paint.Format == PaintFormat.PaintGlyph:
                transformation = reduce(
                    Transform.transform,
                    (st.value.getTransform() for st in path),
                    Identity,
                )
                glyphSet[paint.Glyph].draw(TransformPen(pen, transformation))

        if pen.bounds is None:
            return None

        cb = ClipBox()
        cb.Format = int(ClipBoxFormat.Static)
        cb.xMin, cb.yMin, cb.xMax, cb.yMax = quantizeRect(pen.bounds, quantization)
        return cb


# For each subtable format there is a class. However, we don't really distinguish
# between "field name" and "format name": often these are the same. Yet there's
# a whole bunch of fields with different names. The following dict is a mapping
# from "format name" to "field name". _buildClasses() uses this to create a
# subclass for each alternate field name.
#
_equivalents = {
    "MarkArray": ("Mark1Array",),
    "LangSys": ("DefaultLangSys",),
    "Coverage": (
        "MarkCoverage",
        "BaseCoverage",
        "LigatureCoverage",
        "Mark1Coverage",
        "Mark2Coverage",
        "BacktrackCoverage",
        "InputCoverage",
        "LookAheadCoverage",
        "VertGlyphCoverage",
        "HorizGlyphCoverage",
        "TopAccentCoverage",
        "ExtendedShapeCoverage",
        "MathKernCoverage",
    ),
    "ClassDef": (
        "ClassDef1",
        "ClassDef2",
        "BacktrackClassDef",
        "InputClassDef",
        "LookAheadClassDef",
        "GlyphClassDef",
        "MarkAttachClassDef",
    ),
    "Anchor": (
        "EntryAnchor",
        "ExitAnchor",
        "BaseAnchor",
        "LigatureAnchor",
        "Mark2Anchor",
        "MarkAnchor",
    ),
    "Device": (
        "XPlaDevice",
        "YPlaDevice",
        "XAdvDevice",
        "YAdvDevice",
        "XDeviceTable",
        "YDeviceTable",
        "DeviceTable",
    ),
    "Axis": (
        "HorizAxis",
        "VertAxis",
    ),
    "MinMax": ("DefaultMinMax",),
    "BaseCoord": (
        "MinCoord",
        "MaxCoord",
    ),
    "JstfLangSys": ("DefJstfLangSys",),
    "JstfGSUBModList": (
        "ShrinkageEnableGSUB",
        "ShrinkageDisableGSUB",
        "ExtensionEnableGSUB",
        "ExtensionDisableGSUB",
    ),
    "JstfGPOSModList": (
        "ShrinkageEnableGPOS",
        "ShrinkageDisableGPOS",
        "ExtensionEnableGPOS",
        "ExtensionDisableGPOS",
    ),
    "JstfMax": (
        "ShrinkageJstfMax",
        "ExtensionJstfMax",
    ),
    "MathKern": (
        "TopRightMathKern",
        "TopLeftMathKern",
        "BottomRightMathKern",
        "BottomLeftMathKern",
    ),
    "MathGlyphConstruction": ("VertGlyphConstruction", "HorizGlyphConstruction"),
}

#
# OverFlow logic, to automatically create ExtensionLookups
# XXX This should probably move to otBase.py
#


def fixLookupOverFlows(ttf, overflowRecord):
    """Either the offset from the LookupList to a lookup overflowed, or
    an offset from a lookup to a subtable overflowed.

    The table layout is::

      GPSO/GUSB
              Script List
              Feature List
              LookUpList
                      Lookup[0] and contents
                              SubTable offset list
                                      SubTable[0] and contents
                                      ...
                                      SubTable[n] and contents
                      ...
                      Lookup[n] and contents
                              SubTable offset list
                                      SubTable[0] and contents
                                      ...
                                      SubTable[n] and contents

    If the offset to a lookup overflowed (SubTableIndex is None)
            we must promote the *previous* lookup to an Extension type.

    If the offset from a lookup to subtable overflowed, then we must promote it
            to an Extension Lookup type.
    """
    ok = 0
    lookupIndex = overflowRecord.LookupListIndex
    if overflowRecord.SubTableIndex is None:
        lookupIndex = lookupIndex - 1
    if lookupIndex < 0:
        return ok
    if overflowRecord.tableType == "GSUB":
        extType = 7
    elif overflowRecord.tableType == "GPOS":
        extType = 9

    lookups = ttf[overflowRecord.tableType].table.LookupList.Lookup
    lookup = lookups[lookupIndex]
    # If the previous lookup is an extType, look further back. Very unlikely, but possible.
    while lookup.SubTable[0].__class__.LookupType == extType:
        lookupIndex = lookupIndex - 1
        if lookupIndex < 0:
            return ok
        lookup = lookups[lookupIndex]

    for lookupIndex in range(lookupIndex, len(lookups)):
        lookup = lookups[lookupIndex]
        if lookup.LookupType != extType:
            lookup.LookupType = extType
            for si, subTable in enumerate(lookup.SubTable):
                extSubTableClass = lookupTypes[overflowRecord.tableType][extType]
                extSubTable = extSubTableClass()
                extSubTable.Format = 1
                extSubTable.ExtSubTable = subTable
                lookup.SubTable[si] = extSubTable
    ok = 1
    return ok


def splitMultipleSubst(oldSubTable, newSubTable, overflowRecord):
    ok = 1
    oldMapping = sorted(oldSubTable.mapping.items())
    oldLen = len(oldMapping)

    if overflowRecord.itemName in ["Coverage", "RangeRecord"]:
        # Coverage table is written last. Overflow is to or within the
        # the coverage table. We will just cut the subtable in half.
        newLen = oldLen // 2

    elif overflowRecord.itemName == "Sequence":
        # We just need to back up by two items from the overflowed
        # Sequence index to make sure the offset to the Coverage table
        # doesn't overflow.
        newLen = overflowRecord.itemIndex - 1

    newSubTable.mapping = {}
    for i in range(newLen, oldLen):
        item = oldMapping[i]
        key = item[0]
        newSubTable.mapping[key] = item[1]
        del oldSubTable.mapping[key]

    return ok


def splitAlternateSubst(oldSubTable, newSubTable, overflowRecord):
    ok = 1
    if hasattr(oldSubTable, "sortCoverageLast"):
        newSubTable.sortCoverageLast = oldSubTable.sortCoverageLast

    oldAlts = sorted(oldSubTable.alternates.items())
    oldLen = len(oldAlts)

    if overflowRecord.itemName in ["Coverage", "RangeRecord"]:
        # Coverage table is written last. overflow is to or within the
        # the coverage table. We will just cut the subtable in half.
        newLen = oldLen // 2

    elif overflowRecord.itemName == "AlternateSet":
        # We just need to back up by two items
        # from the overflowed AlternateSet index to make sure the offset
        # to the Coverage table doesn't overflow.
        newLen = overflowRecord.itemIndex - 1

    newSubTable.alternates = {}
    for i in range(newLen, oldLen):
        item = oldAlts[i]
        key = item[0]
        newSubTable.alternates[key] = item[1]
        del oldSubTable.alternates[key]

    return ok


def splitLigatureSubst(oldSubTable, newSubTable, overflowRecord):
    ok = 1
    oldLigs = sorted(oldSubTable.ligatures.items())
    oldLen = len(oldLigs)

    if overflowRecord.itemName in ["Coverage", "RangeRecord"]:
        # Coverage table is written last. overflow is to or within the
        # the coverage table. We will just cut the subtable in half.
        newLen = oldLen // 2

    elif overflowRecord.itemName == "LigatureSet":
        # We just need to back up by two items
        # from the overflowed AlternateSet index to make sure the offset
        # to the Coverage table doesn't overflow.
        newLen = overflowRecord.itemIndex - 1

    newSubTable.ligatures = {}
    for i in range(newLen, oldLen):
        item = oldLigs[i]
        key = item[0]
        newSubTable.ligatures[key] = item[1]
        del oldSubTable.ligatures[key]

    return ok


def splitPairPos(oldSubTable, newSubTable, overflowRecord):
    st = oldSubTable
    ok = False
    newSubTable.Format = oldSubTable.Format
    if oldSubTable.Format == 1 and len(oldSubTable.PairSet) > 1:
        for name in "ValueFormat1", "ValueFormat2":
            setattr(newSubTable, name, getattr(oldSubTable, name))

        # Move top half of coverage to new subtable

        newSubTable.Coverage = oldSubTable.Coverage.__class__()

        coverage = oldSubTable.Coverage.glyphs
        records = oldSubTable.PairSet

        oldCount = len(oldSubTable.PairSet) // 2

        oldSubTable.Coverage.glyphs = coverage[:oldCount]
        oldSubTable.PairSet = records[:oldCount]

        newSubTable.Coverage.glyphs = coverage[oldCount:]
        newSubTable.PairSet = records[oldCount:]

        oldSubTable.PairSetCount = len(oldSubTable.PairSet)
        newSubTable.PairSetCount = len(newSubTable.PairSet)

        ok = True

    elif oldSubTable.Format == 2 and len(oldSubTable.Class1Record) > 1:
        if not hasattr(oldSubTable, "Class2Count"):
            oldSubTable.Class2Count = len(oldSubTable.Class1Record[0].Class2Record)
        for name in "Class2Count", "ClassDef2", "ValueFormat1", "ValueFormat2":
            setattr(newSubTable, name, getattr(oldSubTable, name))

        # The two subtables will still have the same ClassDef2 and the table
        # sharing will still cause the sharing to overflow.  As such, disable
        # sharing on the one that is serialized second (that's oldSubTable).
        oldSubTable.DontShare = True

        # Move top half of class numbers to new subtable

        newSubTable.Coverage = oldSubTable.Coverage.__class__()
        newSubTable.ClassDef1 = oldSubTable.ClassDef1.__class__()

        coverage = oldSubTable.Coverage.glyphs
        classDefs = oldSubTable.ClassDef1.classDefs
        records = oldSubTable.Class1Record

        oldCount = len(oldSubTable.Class1Record) // 2
        newGlyphs = set(k for k, v in classDefs.items() if v >= oldCount)

        oldSubTable.Coverage.glyphs = [g for g in coverage if g not in newGlyphs]
        oldSubTable.ClassDef1.classDefs = {
            k: v for k, v in classDefs.items() if v < oldCount
        }
        oldSubTable.Class1Record = records[:oldCount]

        newSubTable.Coverage.glyphs = [g for g in coverage if g in newGlyphs]
        newSubTable.ClassDef1.classDefs = {
            k: (v - oldCount) for k, v in classDefs.items() if v > oldCount
        }
        newSubTable.Class1Record = records[oldCount:]

        oldSubTable.Class1Count = len(oldSubTable.Class1Record)
        newSubTable.Class1Count = len(newSubTable.Class1Record)

        ok = True

    return ok


def splitMarkBasePos(oldSubTable, newSubTable, overflowRecord):
    # split half of the mark classes to the new subtable
    classCount = oldSubTable.ClassCount
    if classCount < 2:
        # oh well, not much left to split...
        return False

    oldClassCount = classCount // 2
    newClassCount = classCount - oldClassCount

    oldMarkCoverage, oldMarkRecords = [], []
    newMarkCoverage, newMarkRecords = [], []
    for glyphName, markRecord in zip(
        oldSubTable.MarkCoverage.glyphs, oldSubTable.MarkArray.MarkRecord
    ):
        if markRecord.Class < oldClassCount:
            oldMarkCoverage.append(glyphName)
            oldMarkRecords.append(markRecord)
        else:
            markRecord.Class -= oldClassCount
            newMarkCoverage.append(glyphName)
            newMarkRecords.append(markRecord)

    oldBaseRecords, newBaseRecords = [], []
    for rec in oldSubTable.BaseArray.BaseRecord:
        oldBaseRecord, newBaseRecord = rec.__class__(), rec.__class__()
        oldBaseRecord.BaseAnchor = rec.BaseAnchor[:oldClassCount]
        newBaseRecord.BaseAnchor = rec.BaseAnchor[oldClassCount:]
        oldBaseRecords.append(oldBaseRecord)
        newBaseRecords.append(newBaseRecord)

    newSubTable.Format = oldSubTable.Format

    oldSubTable.MarkCoverage.glyphs = oldMarkCoverage
    newSubTable.MarkCoverage = oldSubTable.MarkCoverage.__class__()
    newSubTable.MarkCoverage.glyphs = newMarkCoverage

    # share the same BaseCoverage in both halves
    newSubTable.BaseCoverage = oldSubTable.BaseCoverage

    oldSubTable.ClassCount = oldClassCount
    newSubTable.ClassCount = newClassCount

    oldSubTable.MarkArray.MarkRecord = oldMarkRecords
    newSubTable.MarkArray = oldSubTable.MarkArray.__class__()
    newSubTable.MarkArray.MarkRecord = newMarkRecords

    oldSubTable.MarkArray.MarkCount = len(oldMarkRecords)
    newSubTable.MarkArray.MarkCount = len(newMarkRecords)

    oldSubTable.BaseArray.BaseRecord = oldBaseRecords
    newSubTable.BaseArray = oldSubTable.BaseArray.__class__()
    newSubTable.BaseArray.BaseRecord = newBaseRecords

    oldSubTable.BaseArray.BaseCount = len(oldBaseRecords)
    newSubTable.BaseArray.BaseCount = len(newBaseRecords)

    return True


splitTable = {
    "GSUB": {
        # 					1: splitSingleSubst,
        2: splitMultipleSubst,
        3: splitAlternateSubst,
        4: splitLigatureSubst,
        # 					5: splitContextSubst,
        # 					6: splitChainContextSubst,
        # 					7: splitExtensionSubst,
        # 					8: splitReverseChainSingleSubst,
    },
    "GPOS": {
        # 					1: splitSinglePos,
        2: splitPairPos,
        # 					3: splitCursivePos,
        4: splitMarkBasePos,
        # 					5: splitMarkLigPos,
        # 					6: splitMarkMarkPos,
        # 					7: splitContextPos,
        # 					8: splitChainContextPos,
        # 					9: splitExtensionPos,
    },
}


def fixSubTableOverFlows(ttf, overflowRecord):
    """
    An offset has overflowed within a sub-table. We need to divide this subtable into smaller parts.
    """
    table = ttf[overflowRecord.tableType].table
    lookup = table.LookupList.Lookup[overflowRecord.LookupListIndex]
    subIndex = overflowRecord.SubTableIndex
    subtable = lookup.SubTable[subIndex]

    # First, try not sharing anything for this subtable...
    if not hasattr(subtable, "DontShare"):
        subtable.DontShare = True
        return True

    if hasattr(subtable, "ExtSubTable"):
        # We split the subtable of the Extension table, and add a new Extension table
        # to contain the new subtable.

        subTableType = subtable.ExtSubTable.__class__.LookupType
        extSubTable = subtable
        subtable = extSubTable.ExtSubTable
        newExtSubTableClass = lookupTypes[overflowRecord.tableType][
            extSubTable.__class__.LookupType
        ]
        newExtSubTable = newExtSubTableClass()
        newExtSubTable.Format = extSubTable.Format
        toInsert = newExtSubTable

        newSubTableClass = lookupTypes[overflowRecord.tableType][subTableType]
        newSubTable = newSubTableClass()
        newExtSubTable.ExtSubTable = newSubTable
    else:
        subTableType = subtable.__class__.LookupType
        newSubTableClass = lookupTypes[overflowRecord.tableType][subTableType]
        newSubTable = newSubTableClass()
        toInsert = newSubTable

    if hasattr(lookup, "SubTableCount"):  # may not be defined yet.
        lookup.SubTableCount = lookup.SubTableCount + 1

    try:
        splitFunc = splitTable[overflowRecord.tableType][subTableType]
    except KeyError:
        log.error(
            "Don't know how to split %s lookup type %s",
            overflowRecord.tableType,
            subTableType,
        )
        return False

    ok = splitFunc(subtable, newSubTable, overflowRecord)
    if ok:
        lookup.SubTable.insert(subIndex + 1, toInsert)
    return ok


# End of OverFlow logic


def _buildClasses():
    import re
    from .otData import otData

    formatPat = re.compile(r"([A-Za-z0-9]+)Format(\d+)$")
    namespace = globals()

    # populate module with classes
    for name, table in otData:
        baseClass = BaseTable
        m = formatPat.match(name)
        if m:
            # XxxFormatN subtable, we only add the "base" table
            name = m.group(1)
            # the first row of a format-switching otData table describes the Format;
            # the first column defines the type of the Format field.
            # Currently this can be either 'uint16' or 'uint8'.
            formatType = table[0][0]
            baseClass = getFormatSwitchingBaseTableClass(formatType)
        if name not in namespace:
            # the class doesn't exist yet, so the base implementation is used.
            cls = type(name, (baseClass,), {})
            if name in ("GSUB", "GPOS"):
                cls.DontShare = True
            namespace[name] = cls

    # link Var{Table} <-> {Table} (e.g. ColorStop <-> VarColorStop, etc.)
    for name, _ in otData:
        if name.startswith("Var") and len(name) > 3 and name[3:] in namespace:
            varType = namespace[name]
            noVarType = namespace[name[3:]]
            varType.NoVarType = noVarType
            noVarType.VarType = varType

    for base, alts in _equivalents.items():
        base = namespace[base]
        for alt in alts:
            namespace[alt] = base

    global lookupTypes
    lookupTypes = {
        "GSUB": {
            1: SingleSubst,
            2: MultipleSubst,
            3: AlternateSubst,
            4: LigatureSubst,
            5: ContextSubst,
            6: ChainContextSubst,
            7: ExtensionSubst,
            8: ReverseChainSingleSubst,
        },
        "GPOS": {
            1: SinglePos,
            2: PairPos,
            3: CursivePos,
            4: MarkBasePos,
            5: MarkLigPos,
            6: MarkMarkPos,
            7: ContextPos,
            8: ChainContextPos,
            9: ExtensionPos,
        },
        "mort": {
            4: NoncontextualMorph,
        },
        "morx": {
            0: RearrangementMorph,
            1: ContextualMorph,
            2: LigatureMorph,
            # 3: Reserved,
            4: NoncontextualMorph,
            5: InsertionMorph,
        },
    }
    lookupTypes["JSTF"] = lookupTypes["GPOS"]  # JSTF contains GPOS
    for lookupEnum in lookupTypes.values():
        for enum, cls in lookupEnum.items():
            cls.LookupType = enum

    global featureParamTypes
    featureParamTypes = {
        "size": FeatureParamsSize,
    }
    for i in range(1, 20 + 1):
        featureParamTypes["ss%02d" % i] = FeatureParamsStylisticSet
    for i in range(1, 99 + 1):
        featureParamTypes["cv%02d" % i] = FeatureParamsCharacterVariants

    # add converters to classes
    from .otConverters import buildConverters

    for name, table in otData:
        m = formatPat.match(name)
        if m:
            # XxxFormatN subtable, add converter to "base" table
            name, format = m.groups()
            format = int(format)
            cls = namespace[name]
            if not hasattr(cls, "converters"):
                cls.converters = {}
                cls.convertersByName = {}
            converters, convertersByName = buildConverters(table[1:], namespace)
            cls.converters[format] = converters
            cls.convertersByName[format] = convertersByName
            # XXX Add staticSize?
        else:
            cls = namespace[name]
            cls.converters, cls.convertersByName = buildConverters(table, namespace)
            # XXX Add staticSize?


_buildClasses()


def _getGlyphsFromCoverageTable(coverage):
    if coverage is None:
        # empty coverage table
        return []
    else:
        return coverage.glyphs
