from fontTools.misc import sstruct
from fontTools.misc.fixedTools import (
    fixedToFloat as fi2fl,
    floatToFixed as fl2fi,
    floatToFixedToStr as fl2str,
    strToFixedToFloat as str2fl,
)
from fontTools.misc.textTools import Tag, bytesjoin, safeEval
from fontTools.ttLib import TTLibError
from . import DefaultTable
import struct


# Apple's documentation of 'fvar':
# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6fvar.html

FVAR_HEADER_FORMAT = """
    > # big endian
    version:        L
    offsetToData:   H
    countSizePairs: H
    axisCount:      H
    axisSize:       H
    instanceCount:  H
    instanceSize:   H
"""

FVAR_AXIS_FORMAT = """
    > # big endian
    axisTag:        4s
    minValue:       16.16F
    defaultValue:   16.16F
    maxValue:       16.16F
    flags:          H
    axisNameID:         H
"""

FVAR_INSTANCE_FORMAT = """
    > # big endian
    subfamilyNameID:     H
    flags:      H
"""


class table__f_v_a_r(DefaultTable.DefaultTable):
    """FonT Variations table

    The ``fvar`` table contains records of the variation axes and of the
    named instances in a variable font.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6fvar.html
    """

    dependencies = ["name"]

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.axes = []
        self.instances = []

    def compile(self, ttFont):
        instanceSize = sstruct.calcsize(FVAR_INSTANCE_FORMAT) + (len(self.axes) * 4)
        includePostScriptNames = any(
            instance.postscriptNameID != 0xFFFF for instance in self.instances
        )
        if includePostScriptNames:
            instanceSize += 2
        header = {
            "version": 0x00010000,
            "offsetToData": sstruct.calcsize(FVAR_HEADER_FORMAT),
            "countSizePairs": 2,
            "axisCount": len(self.axes),
            "axisSize": sstruct.calcsize(FVAR_AXIS_FORMAT),
            "instanceCount": len(self.instances),
            "instanceSize": instanceSize,
        }
        result = [sstruct.pack(FVAR_HEADER_FORMAT, header)]
        result.extend([axis.compile() for axis in self.axes])
        axisTags = [axis.axisTag for axis in self.axes]
        for instance in self.instances:
            result.append(instance.compile(axisTags, includePostScriptNames))
        return bytesjoin(result)

    def decompile(self, data, ttFont):
        header = {}
        headerSize = sstruct.calcsize(FVAR_HEADER_FORMAT)
        header = sstruct.unpack(FVAR_HEADER_FORMAT, data[0:headerSize])
        if header["version"] != 0x00010000:
            raise TTLibError("unsupported 'fvar' version %04x" % header["version"])
        pos = header["offsetToData"]
        axisSize = header["axisSize"]
        for _ in range(header["axisCount"]):
            axis = Axis()
            axis.decompile(data[pos : pos + axisSize])
            self.axes.append(axis)
            pos += axisSize
        instanceSize = header["instanceSize"]
        axisTags = [axis.axisTag for axis in self.axes]
        for _ in range(header["instanceCount"]):
            instance = NamedInstance()
            instance.decompile(data[pos : pos + instanceSize], axisTags)
            self.instances.append(instance)
            pos += instanceSize

    def toXML(self, writer, ttFont):
        for axis in self.axes:
            axis.toXML(writer, ttFont)
        for instance in self.instances:
            instance.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name == "Axis":
            axis = Axis()
            axis.fromXML(name, attrs, content, ttFont)
            self.axes.append(axis)
        elif name == "NamedInstance":
            instance = NamedInstance()
            instance.fromXML(name, attrs, content, ttFont)
            self.instances.append(instance)

    def getAxes(self):
        return {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in self.axes}


class Axis(object):
    def __init__(self):
        self.axisTag = None
        self.axisNameID = 0
        self.flags = 0
        self.minValue = -1.0
        self.defaultValue = 0.0
        self.maxValue = 1.0

    def compile(self):
        return sstruct.pack(FVAR_AXIS_FORMAT, self)

    def decompile(self, data):
        sstruct.unpack2(FVAR_AXIS_FORMAT, data, self)

    def toXML(self, writer, ttFont):
        name = (
            ttFont["name"].getDebugName(self.axisNameID) if "name" in ttFont else None
        )
        if name is not None:
            writer.newline()
            writer.comment(name)
            writer.newline()
        writer.begintag("Axis")
        writer.newline()
        for tag, value in [
            ("AxisTag", self.axisTag),
            ("Flags", "0x%X" % self.flags),
            ("MinValue", fl2str(self.minValue, 16)),
            ("DefaultValue", fl2str(self.defaultValue, 16)),
            ("MaxValue", fl2str(self.maxValue, 16)),
            ("AxisNameID", str(self.axisNameID)),
        ]:
            writer.begintag(tag)
            writer.write(value)
            writer.endtag(tag)
            writer.newline()
        writer.endtag("Axis")
        writer.newline()

    def fromXML(self, name, _attrs, content, ttFont):
        assert name == "Axis"
        for tag, _, value in filter(lambda t: type(t) is tuple, content):
            value = "".join(value)
            if tag == "AxisTag":
                self.axisTag = Tag(value)
            elif tag in {"Flags", "MinValue", "DefaultValue", "MaxValue", "AxisNameID"}:
                setattr(
                    self,
                    tag[0].lower() + tag[1:],
                    str2fl(value, 16) if tag.endswith("Value") else safeEval(value),
                )


class NamedInstance(object):
    def __init__(self):
        self.subfamilyNameID = 0
        self.postscriptNameID = 0xFFFF
        self.flags = 0
        self.coordinates = {}

    def compile(self, axisTags, includePostScriptName):
        result = [sstruct.pack(FVAR_INSTANCE_FORMAT, self)]
        for axis in axisTags:
            fixedCoord = fl2fi(self.coordinates[axis], 16)
            result.append(struct.pack(">l", fixedCoord))
        if includePostScriptName:
            result.append(struct.pack(">H", self.postscriptNameID))
        return bytesjoin(result)

    def decompile(self, data, axisTags):
        sstruct.unpack2(FVAR_INSTANCE_FORMAT, data, self)
        pos = sstruct.calcsize(FVAR_INSTANCE_FORMAT)
        for axis in axisTags:
            value = struct.unpack(">l", data[pos : pos + 4])[0]
            self.coordinates[axis] = fi2fl(value, 16)
            pos += 4
        if pos + 2 <= len(data):
            self.postscriptNameID = struct.unpack(">H", data[pos : pos + 2])[0]
        else:
            self.postscriptNameID = 0xFFFF

    def toXML(self, writer, ttFont):
        name = (
            ttFont["name"].getDebugName(self.subfamilyNameID)
            if "name" in ttFont
            else None
        )
        if name is not None:
            writer.newline()
            writer.comment(name)
            writer.newline()
        psname = (
            ttFont["name"].getDebugName(self.postscriptNameID)
            if "name" in ttFont
            else None
        )
        if psname is not None:
            writer.comment("PostScript: " + psname)
            writer.newline()
        if self.postscriptNameID == 0xFFFF:
            writer.begintag(
                "NamedInstance",
                flags=("0x%X" % self.flags),
                subfamilyNameID=self.subfamilyNameID,
            )
        else:
            writer.begintag(
                "NamedInstance",
                flags=("0x%X" % self.flags),
                subfamilyNameID=self.subfamilyNameID,
                postscriptNameID=self.postscriptNameID,
            )
        writer.newline()
        for axis in ttFont["fvar"].axes:
            writer.simpletag(
                "coord",
                axis=axis.axisTag,
                value=fl2str(self.coordinates[axis.axisTag], 16),
            )
            writer.newline()
        writer.endtag("NamedInstance")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        assert name == "NamedInstance"
        self.subfamilyNameID = safeEval(attrs["subfamilyNameID"])
        self.flags = safeEval(attrs.get("flags", "0"))
        if "postscriptNameID" in attrs:
            self.postscriptNameID = safeEval(attrs["postscriptNameID"])
        else:
            self.postscriptNameID = 0xFFFF

        for tag, elementAttrs, _ in filter(lambda t: type(t) is tuple, content):
            if tag == "coord":
                value = str2fl(elementAttrs["value"], 16)
                self.coordinates[elementAttrs["axis"]] = value
