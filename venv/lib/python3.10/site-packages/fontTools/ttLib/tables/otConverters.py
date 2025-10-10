from fontTools.misc.fixedTools import (
    fixedToFloat as fi2fl,
    floatToFixed as fl2fi,
    floatToFixedToStr as fl2str,
    strToFixedToFloat as str2fl,
    ensureVersionIsLong as fi2ve,
    versionToFixed as ve2fi,
)
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.misc.roundTools import nearestMultipleShortestRepr, otRound
from fontTools.misc.textTools import bytesjoin, tobytes, tostr, pad, safeEval
from fontTools.misc.lazyTools import LazyList
from fontTools.ttLib import OPTIMIZE_FONT_SPEED, getSearchRange
from .otBase import (
    CountReference,
    FormatSwitchingBaseTable,
    OTTableReader,
    OTTableWriter,
    ValueRecordFactory,
)
from .otTables import (
    lookupTypes,
    VarCompositeGlyph,
    AATStateTable,
    AATState,
    AATAction,
    ContextualMorphAction,
    LigatureMorphAction,
    InsertionMorphAction,
    MorxSubtable,
    ExtendMode as _ExtendMode,
    CompositeMode as _CompositeMode,
    NO_VARIATION_INDEX,
)
from itertools import zip_longest, accumulate
from functools import partial
from types import SimpleNamespace
import re
import struct
from typing import Optional
import logging


log = logging.getLogger(__name__)
istuple = lambda t: isinstance(t, tuple)


def buildConverters(tableSpec, tableNamespace):
    """Given a table spec from otData.py, build a converter object for each
    field of the table. This is called for each table in otData.py, and
    the results are assigned to the corresponding class in otTables.py."""
    converters = []
    convertersByName = {}
    for tp, name, repeat, aux, descr in tableSpec:
        tableName = name
        if name.startswith("ValueFormat"):
            assert tp == "uint16"
            converterClass = ValueFormat
        elif name.endswith("Count") or name in ("StructLength", "MorphType"):
            converterClass = {
                "uint8": ComputedUInt8,
                "uint16": ComputedUShort,
                "uint32": ComputedULong,
            }[tp]
        elif name == "SubTable":
            converterClass = SubTable
        elif name == "ExtSubTable":
            converterClass = ExtSubTable
        elif name == "SubStruct":
            converterClass = SubStruct
        elif name == "FeatureParams":
            converterClass = FeatureParams
        elif name in ("CIDGlyphMapping", "GlyphCIDMapping"):
            converterClass = StructWithLength
        else:
            if not tp in converterMapping and "(" not in tp:
                tableName = tp
                converterClass = Struct
            else:
                converterClass = eval(tp, tableNamespace, converterMapping)

        conv = converterClass(name, repeat, aux, description=descr)

        if conv.tableClass:
            # A "template" such as OffsetTo(AType) knows the table class already
            tableClass = conv.tableClass
        elif tp in ("MortChain", "MortSubtable", "MorxChain"):
            tableClass = tableNamespace.get(tp)
        else:
            tableClass = tableNamespace.get(tableName)

        if not conv.tableClass:
            conv.tableClass = tableClass

        if name in ["SubTable", "ExtSubTable", "SubStruct"]:
            conv.lookupTypes = tableNamespace["lookupTypes"]
            # also create reverse mapping
            for t in conv.lookupTypes.values():
                for cls in t.values():
                    convertersByName[cls.__name__] = Table(name, repeat, aux, cls)
        if name == "FeatureParams":
            conv.featureParamTypes = tableNamespace["featureParamTypes"]
            conv.defaultFeatureParams = tableNamespace["FeatureParams"]
            for cls in conv.featureParamTypes.values():
                convertersByName[cls.__name__] = Table(name, repeat, aux, cls)
        converters.append(conv)
        assert name not in convertersByName, name
        convertersByName[name] = conv
    return converters, convertersByName


class BaseConverter(object):
    """Base class for converter objects. Apart from the constructor, this
    is an abstract class."""

    def __init__(self, name, repeat, aux, tableClass=None, *, description=""):
        self.name = name
        self.repeat = repeat
        self.aux = aux
        if self.aux and not self.repeat:
            self.aux = compile(self.aux, "<string>", "eval")
        self.tableClass = tableClass
        self.isCount = name.endswith("Count") or name in [
            "DesignAxisRecordSize",
            "ValueRecordSize",
        ]
        self.isLookupType = name.endswith("LookupType") or name == "MorphType"
        self.isPropagated = name in [
            "ClassCount",
            "Class2Count",
            "FeatureTag",
            "SettingsCount",
            "VarRegionCount",
            "MappingCount",
            "RegionAxisCount",
            "DesignAxisCount",
            "DesignAxisRecordSize",
            "AxisValueCount",
            "ValueRecordSize",
            "AxisCount",
            "BaseGlyphRecordCount",
            "LayerRecordCount",
            "AxisIndicesList",
        ]
        self.description = description

    def readArray(self, reader, font, tableDict, count):
        """Read an array of values from the reader."""
        lazy = font.lazy and count > 8
        if lazy:
            recordSize = self.getRecordSize(reader)
            if recordSize is NotImplemented:
                lazy = False
        if not lazy:
            l = []
            for i in range(count):
                l.append(self.read(reader, font, tableDict))
            return l
        else:

            def get_read_item():
                reader_copy = reader.copy()
                pos = reader.pos

                def read_item(i):
                    reader_copy.seek(pos + i * recordSize)
                    return self.read(reader_copy, font, {})

                return read_item

            read_item = get_read_item()
            l = LazyList(read_item for i in range(count))
            reader.advance(count * recordSize)

            return l

    def getRecordSize(self, reader):
        if hasattr(self, "staticSize"):
            return self.staticSize
        return NotImplemented

    def read(self, reader, font, tableDict):
        """Read a value from the reader."""
        raise NotImplementedError(self)

    def writeArray(self, writer, font, tableDict, values):
        try:
            for i, value in enumerate(values):
                self.write(writer, font, tableDict, value, i)
        except Exception as e:
            e.args = e.args + (i,)
            raise

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        """Write a value to the writer."""
        raise NotImplementedError(self)

    def xmlRead(self, attrs, content, font):
        """Read a value from XML."""
        raise NotImplementedError(self)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        """Write a value to XML."""
        raise NotImplementedError(self)

    varIndexBasePlusOffsetRE = re.compile(r"VarIndexBase\s*\+\s*(\d+)")

    def getVarIndexOffset(self) -> Optional[int]:
        """If description has `VarIndexBase + {offset}`, return the offset else None."""
        m = self.varIndexBasePlusOffsetRE.search(self.description)
        if not m:
            return None
        return int(m.group(1))


class SimpleValue(BaseConverter):
    @staticmethod
    def toString(value):
        return value

    @staticmethod
    def fromString(value):
        return value

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", self.toString(value))])
        xmlWriter.newline()

    def xmlRead(self, attrs, content, font):
        return self.fromString(attrs["value"])


class OptionalValue(SimpleValue):
    DEFAULT = None

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        if value != self.DEFAULT:
            attrs.append(("value", self.toString(value)))
        xmlWriter.simpletag(name, attrs)
        xmlWriter.newline()

    def xmlRead(self, attrs, content, font):
        if "value" in attrs:
            return self.fromString(attrs["value"])
        return self.DEFAULT


class IntValue(SimpleValue):
    @staticmethod
    def fromString(value):
        return int(value, 0)


class Long(IntValue):
    staticSize = 4

    def read(self, reader, font, tableDict):
        return reader.readLong()

    def readArray(self, reader, font, tableDict, count):
        return reader.readLongArray(count)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeLong(value)

    def writeArray(self, writer, font, tableDict, values):
        writer.writeLongArray(values)


class ULong(IntValue):
    staticSize = 4

    def read(self, reader, font, tableDict):
        return reader.readULong()

    def readArray(self, reader, font, tableDict, count):
        return reader.readULongArray(count)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeULong(value)

    def writeArray(self, writer, font, tableDict, values):
        writer.writeULongArray(values)


class Flags32(ULong):
    @staticmethod
    def toString(value):
        return "0x%08X" % value


class VarIndex(OptionalValue, ULong):
    DEFAULT = NO_VARIATION_INDEX


class Short(IntValue):
    staticSize = 2

    def read(self, reader, font, tableDict):
        return reader.readShort()

    def readArray(self, reader, font, tableDict, count):
        return reader.readShortArray(count)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeShort(value)

    def writeArray(self, writer, font, tableDict, values):
        writer.writeShortArray(values)


class UShort(IntValue):
    staticSize = 2

    def read(self, reader, font, tableDict):
        return reader.readUShort()

    def readArray(self, reader, font, tableDict, count):
        return reader.readUShortArray(count)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeUShort(value)

    def writeArray(self, writer, font, tableDict, values):
        writer.writeUShortArray(values)


class Int8(IntValue):
    staticSize = 1

    def read(self, reader, font, tableDict):
        return reader.readInt8()

    def readArray(self, reader, font, tableDict, count):
        return reader.readInt8Array(count)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeInt8(value)

    def writeArray(self, writer, font, tableDict, values):
        writer.writeInt8Array(values)


class UInt8(IntValue):
    staticSize = 1

    def read(self, reader, font, tableDict):
        return reader.readUInt8()

    def readArray(self, reader, font, tableDict, count):
        return reader.readUInt8Array(count)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeUInt8(value)

    def writeArray(self, writer, font, tableDict, values):
        writer.writeUInt8Array(values)


class UInt24(IntValue):
    staticSize = 3

    def read(self, reader, font, tableDict):
        return reader.readUInt24()

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeUInt24(value)


class ComputedInt(IntValue):
    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        if value is not None:
            xmlWriter.comment("%s=%s" % (name, value))
            xmlWriter.newline()


class ComputedUInt8(ComputedInt, UInt8):
    pass


class ComputedUShort(ComputedInt, UShort):
    pass


class ComputedULong(ComputedInt, ULong):
    pass


class Tag(SimpleValue):
    staticSize = 4

    def read(self, reader, font, tableDict):
        return reader.readTag()

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeTag(value)


class GlyphID(SimpleValue):
    staticSize = 2
    typecode = "H"

    def readArray(self, reader, font, tableDict, count):
        return font.getGlyphNameMany(
            reader.readArray(self.typecode, self.staticSize, count)
        )

    def read(self, reader, font, tableDict):
        return font.getGlyphName(reader.readValue(self.typecode, self.staticSize))

    def writeArray(self, writer, font, tableDict, values):
        writer.writeArray(self.typecode, font.getGlyphIDMany(values))

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeValue(self.typecode, font.getGlyphID(value))


class GlyphID32(GlyphID):
    staticSize = 4
    typecode = "L"


class NameID(UShort):
    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", value)])
        if font and value:
            nameTable = font.get("name")
            if nameTable:
                name = nameTable.getDebugName(value)
                xmlWriter.write("  ")
                if name:
                    xmlWriter.comment(name)
                else:
                    xmlWriter.comment("missing from name table")
                    log.warning("name id %d missing from name table" % value)
        xmlWriter.newline()


class STATFlags(UShort):
    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", value)])
        flags = []
        if value & 0x01:
            flags.append("OlderSiblingFontAttribute")
        if value & 0x02:
            flags.append("ElidableAxisValueName")
        if flags:
            xmlWriter.write("  ")
            xmlWriter.comment(" ".join(flags))
        xmlWriter.newline()


class FloatValue(SimpleValue):
    @staticmethod
    def fromString(value):
        return float(value)


class DeciPoints(FloatValue):
    staticSize = 2

    def read(self, reader, font, tableDict):
        return reader.readUShort() / 10

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.writeUShort(round(value * 10))


class BaseFixedValue(FloatValue):
    staticSize = NotImplemented
    precisionBits = NotImplemented
    readerMethod = NotImplemented
    writerMethod = NotImplemented

    def read(self, reader, font, tableDict):
        return self.fromInt(getattr(reader, self.readerMethod)())

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        getattr(writer, self.writerMethod)(self.toInt(value))

    @classmethod
    def fromInt(cls, value):
        return fi2fl(value, cls.precisionBits)

    @classmethod
    def toInt(cls, value):
        return fl2fi(value, cls.precisionBits)

    @classmethod
    def fromString(cls, value):
        return str2fl(value, cls.precisionBits)

    @classmethod
    def toString(cls, value):
        return fl2str(value, cls.precisionBits)


class Fixed(BaseFixedValue):
    staticSize = 4
    precisionBits = 16
    readerMethod = "readLong"
    writerMethod = "writeLong"


class F2Dot14(BaseFixedValue):
    staticSize = 2
    precisionBits = 14
    readerMethod = "readShort"
    writerMethod = "writeShort"


class Angle(F2Dot14):
    # angles are specified in degrees, and encoded as F2Dot14 fractions of half
    # circle: e.g. 1.0 => 180, -0.5 => -90, -2.0 => -360, etc.
    bias = 0.0
    factor = 1.0 / (1 << 14) * 180  # 0.010986328125

    @classmethod
    def fromInt(cls, value):
        return (super().fromInt(value) + cls.bias) * 180

    @classmethod
    def toInt(cls, value):
        return super().toInt((value / 180) - cls.bias)

    @classmethod
    def fromString(cls, value):
        # quantize to nearest multiples of minimum fixed-precision angle
        return otRound(float(value) / cls.factor) * cls.factor

    @classmethod
    def toString(cls, value):
        return nearestMultipleShortestRepr(value, cls.factor)


class BiasedAngle(Angle):
    # A bias of 1.0 is used in the representation of start and end angles
    # of COLRv1 PaintSweepGradients to allow for encoding +360deg
    bias = 1.0


class Version(SimpleValue):
    staticSize = 4

    def read(self, reader, font, tableDict):
        value = reader.readLong()
        return value

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        value = fi2ve(value)
        writer.writeLong(value)

    @staticmethod
    def fromString(value):
        return ve2fi(value)

    @staticmethod
    def toString(value):
        return "0x%08x" % value

    @staticmethod
    def fromFloat(v):
        return fl2fi(v, 16)


class Char64(SimpleValue):
    """An ASCII string with up to 64 characters.

    Unused character positions are filled with 0x00 bytes.
    Used in Apple AAT fonts in the `gcid` table.
    """

    staticSize = 64

    def read(self, reader, font, tableDict):
        data = reader.readData(self.staticSize)
        zeroPos = data.find(b"\0")
        if zeroPos >= 0:
            data = data[:zeroPos]
        s = tostr(data, encoding="ascii", errors="replace")
        if s != tostr(data, encoding="ascii", errors="ignore"):
            log.warning('replaced non-ASCII characters in "%s"' % s)
        return s

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        data = tobytes(value, encoding="ascii", errors="replace")
        if data != tobytes(value, encoding="ascii", errors="ignore"):
            log.warning('replacing non-ASCII characters in "%s"' % value)
        if len(data) > self.staticSize:
            log.warning(
                'truncating overlong "%s" to %d bytes' % (value, self.staticSize)
            )
        data = (data + b"\0" * self.staticSize)[: self.staticSize]
        writer.writeData(data)


class Struct(BaseConverter):
    def getRecordSize(self, reader):
        return self.tableClass and self.tableClass.getRecordSize(reader)

    def read(self, reader, font, tableDict):
        table = self.tableClass()
        table.decompile(reader, font)
        return table

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        value.compile(writer, font)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        if value is None:
            if attrs:
                # If there are attributes (probably index), then
                # don't drop this even if it's NULL.  It will mess
                # up the array indices of the containing element.
                xmlWriter.simpletag(name, attrs + [("empty", 1)])
                xmlWriter.newline()
            else:
                pass  # NULL table, ignore
        else:
            value.toXML(xmlWriter, font, attrs, name=name)

    def xmlRead(self, attrs, content, font):
        if "empty" in attrs and safeEval(attrs["empty"]):
            return None
        table = self.tableClass()
        Format = attrs.get("Format")
        if Format is not None:
            table.Format = int(Format)

        noPostRead = not hasattr(table, "postRead")
        if noPostRead:
            # TODO Cache table.hasPropagated.
            cleanPropagation = False
            for conv in table.getConverters():
                if conv.isPropagated:
                    cleanPropagation = True
                    if not hasattr(font, "_propagator"):
                        font._propagator = {}
                    propagator = font._propagator
                    assert conv.name not in propagator, (conv.name, propagator)
                    setattr(table, conv.name, None)
                    propagator[conv.name] = CountReference(table.__dict__, conv.name)

        for element in content:
            if isinstance(element, tuple):
                name, attrs, content = element
                table.fromXML(name, attrs, content, font)
            else:
                pass

        table.populateDefaults(propagator=getattr(font, "_propagator", None))

        if noPostRead:
            if cleanPropagation:
                for conv in table.getConverters():
                    if conv.isPropagated:
                        propagator = font._propagator
                        del propagator[conv.name]
                        if not propagator:
                            del font._propagator

        return table

    def __repr__(self):
        return "Struct of " + repr(self.tableClass)


class StructWithLength(Struct):
    def read(self, reader, font, tableDict):
        pos = reader.pos
        table = self.tableClass()
        table.decompile(reader, font)
        reader.seek(pos + table.StructLength)
        return table

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        for convIndex, conv in enumerate(value.getConverters()):
            if conv.name == "StructLength":
                break
        lengthIndex = len(writer.items) + convIndex
        if isinstance(value, FormatSwitchingBaseTable):
            lengthIndex += 1  # implicit Format field
        deadbeef = {1: 0xDE, 2: 0xDEAD, 4: 0xDEADBEEF}[conv.staticSize]

        before = writer.getDataLength()
        value.StructLength = deadbeef
        value.compile(writer, font)
        length = writer.getDataLength() - before
        lengthWriter = writer.getSubWriter()
        conv.write(lengthWriter, font, tableDict, length)
        assert writer.items[lengthIndex] == b"\xde\xad\xbe\xef"[: conv.staticSize]
        writer.items[lengthIndex] = lengthWriter.getAllData()


class Table(Struct):
    staticSize = 2

    def readOffset(self, reader):
        return reader.readUShort()

    def writeNullOffset(self, writer):
        writer.writeUShort(0)

    def read(self, reader, font, tableDict):
        offset = self.readOffset(reader)
        if offset == 0:
            return None
        table = self.tableClass()
        reader = reader.getSubReader(offset)
        if font.lazy:
            table.reader = reader
            table.font = font
        else:
            table.decompile(reader, font)
        return table

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        if value is None:
            self.writeNullOffset(writer)
        else:
            subWriter = writer.getSubWriter()
            subWriter.name = self.name
            if repeatIndex is not None:
                subWriter.repeatIndex = repeatIndex
            writer.writeSubTable(subWriter, offsetSize=self.staticSize)
            value.compile(subWriter, font)


class LTable(Table):
    staticSize = 4

    def readOffset(self, reader):
        return reader.readULong()

    def writeNullOffset(self, writer):
        writer.writeULong(0)


# Table pointed to by a 24-bit, 3-byte long offset
class Table24(Table):
    staticSize = 3

    def readOffset(self, reader):
        return reader.readUInt24()

    def writeNullOffset(self, writer):
        writer.writeUInt24(0)


# TODO Clean / merge the SubTable and SubStruct


class SubStruct(Struct):
    def getConverter(self, tableType, lookupType):
        tableClass = self.lookupTypes[tableType][lookupType]
        return self.__class__(self.name, self.repeat, self.aux, tableClass)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        super(SubStruct, self).xmlWrite(xmlWriter, font, value, None, attrs)


class SubTable(Table):
    def getConverter(self, tableType, lookupType):
        tableClass = self.lookupTypes[tableType][lookupType]
        return self.__class__(self.name, self.repeat, self.aux, tableClass)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        super(SubTable, self).xmlWrite(xmlWriter, font, value, None, attrs)


class ExtSubTable(LTable, SubTable):
    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer.Extension = True  # actually, mere presence of the field flags it as an Ext Subtable writer.
        Table.write(self, writer, font, tableDict, value, repeatIndex)


class FeatureParams(Table):
    def getConverter(self, featureTag):
        tableClass = self.featureParamTypes.get(featureTag, self.defaultFeatureParams)
        return self.__class__(self.name, self.repeat, self.aux, tableClass)


class ValueFormat(IntValue):
    staticSize = 2

    def __init__(self, name, repeat, aux, tableClass=None, *, description=""):
        BaseConverter.__init__(
            self, name, repeat, aux, tableClass, description=description
        )
        self.which = "ValueFormat" + ("2" if name[-1] == "2" else "1")

    def read(self, reader, font, tableDict):
        format = reader.readUShort()
        reader[self.which] = ValueRecordFactory(format)
        return format

    def write(self, writer, font, tableDict, format, repeatIndex=None):
        writer.writeUShort(format)
        writer[self.which] = ValueRecordFactory(format)


class ValueRecord(ValueFormat):
    def getRecordSize(self, reader):
        return 2 * len(reader[self.which])

    def read(self, reader, font, tableDict):
        return reader[self.which].readValueRecord(reader, font)

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        writer[self.which].writeValueRecord(writer, font, value)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        if value is None:
            pass  # NULL table, ignore
        else:
            value.toXML(xmlWriter, font, self.name, attrs)

    def xmlRead(self, attrs, content, font):
        from .otBase import ValueRecord

        value = ValueRecord()
        value.fromXML(None, attrs, content, font)
        return value


class AATLookup(BaseConverter):
    BIN_SEARCH_HEADER_SIZE = 10

    def __init__(self, name, repeat, aux, tableClass, *, description=""):
        BaseConverter.__init__(
            self, name, repeat, aux, tableClass, description=description
        )
        if issubclass(self.tableClass, SimpleValue):
            self.converter = self.tableClass(name="Value", repeat=None, aux=None)
        else:
            self.converter = Table(
                name="Value", repeat=None, aux=None, tableClass=self.tableClass
            )

    def read(self, reader, font, tableDict):
        format = reader.readUShort()
        if format == 0:
            return self.readFormat0(reader, font)
        elif format == 2:
            return self.readFormat2(reader, font)
        elif format == 4:
            return self.readFormat4(reader, font)
        elif format == 6:
            return self.readFormat6(reader, font)
        elif format == 8:
            return self.readFormat8(reader, font)
        else:
            assert False, "unsupported lookup format: %d" % format

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        values = list(
            sorted([(font.getGlyphID(glyph), val) for glyph, val in value.items()])
        )
        # TODO: Also implement format 4.
        formats = list(
            sorted(
                filter(
                    None,
                    [
                        self.buildFormat0(writer, font, values),
                        self.buildFormat2(writer, font, values),
                        self.buildFormat6(writer, font, values),
                        self.buildFormat8(writer, font, values),
                    ],
                )
            )
        )
        # We use the format ID as secondary sort key to make the output
        # deterministic when multiple formats have same encoded size.
        dataSize, lookupFormat, writeMethod = formats[0]
        pos = writer.getDataLength()
        writeMethod()
        actualSize = writer.getDataLength() - pos
        assert (
            actualSize == dataSize
        ), "AATLookup format %d claimed to write %d bytes, but wrote %d" % (
            lookupFormat,
            dataSize,
            actualSize,
        )

    @staticmethod
    def writeBinSearchHeader(writer, numUnits, unitSize):
        writer.writeUShort(unitSize)
        writer.writeUShort(numUnits)
        searchRange, entrySelector, rangeShift = getSearchRange(
            n=numUnits, itemSize=unitSize
        )
        writer.writeUShort(searchRange)
        writer.writeUShort(entrySelector)
        writer.writeUShort(rangeShift)

    def buildFormat0(self, writer, font, values):
        numGlyphs = len(font.getGlyphOrder())
        if len(values) != numGlyphs:
            return None
        valueSize = self.converter.staticSize
        return (
            2 + numGlyphs * valueSize,
            0,
            lambda: self.writeFormat0(writer, font, values),
        )

    def writeFormat0(self, writer, font, values):
        writer.writeUShort(0)
        for glyphID_, value in values:
            self.converter.write(
                writer, font, tableDict=None, value=value, repeatIndex=None
            )

    def buildFormat2(self, writer, font, values):
        segStart, segValue = values[0]
        segEnd = segStart
        segments = []
        for glyphID, curValue in values[1:]:
            if glyphID != segEnd + 1 or curValue != segValue:
                segments.append((segStart, segEnd, segValue))
                segStart = segEnd = glyphID
                segValue = curValue
            else:
                segEnd = glyphID
        segments.append((segStart, segEnd, segValue))
        valueSize = self.converter.staticSize
        numUnits, unitSize = len(segments) + 1, valueSize + 4
        return (
            2 + self.BIN_SEARCH_HEADER_SIZE + numUnits * unitSize,
            2,
            lambda: self.writeFormat2(writer, font, segments),
        )

    def writeFormat2(self, writer, font, segments):
        writer.writeUShort(2)
        valueSize = self.converter.staticSize
        numUnits, unitSize = len(segments), valueSize + 4
        self.writeBinSearchHeader(writer, numUnits, unitSize)
        for firstGlyph, lastGlyph, value in segments:
            writer.writeUShort(lastGlyph)
            writer.writeUShort(firstGlyph)
            self.converter.write(
                writer, font, tableDict=None, value=value, repeatIndex=None
            )
        writer.writeUShort(0xFFFF)
        writer.writeUShort(0xFFFF)
        writer.writeData(b"\x00" * valueSize)

    def buildFormat6(self, writer, font, values):
        valueSize = self.converter.staticSize
        numUnits, unitSize = len(values), valueSize + 2
        return (
            2 + self.BIN_SEARCH_HEADER_SIZE + (numUnits + 1) * unitSize,
            6,
            lambda: self.writeFormat6(writer, font, values),
        )

    def writeFormat6(self, writer, font, values):
        writer.writeUShort(6)
        valueSize = self.converter.staticSize
        numUnits, unitSize = len(values), valueSize + 2
        self.writeBinSearchHeader(writer, numUnits, unitSize)
        for glyphID, value in values:
            writer.writeUShort(glyphID)
            self.converter.write(
                writer, font, tableDict=None, value=value, repeatIndex=None
            )
        writer.writeUShort(0xFFFF)
        writer.writeData(b"\x00" * valueSize)

    def buildFormat8(self, writer, font, values):
        minGlyphID, maxGlyphID = values[0][0], values[-1][0]
        if len(values) != maxGlyphID - minGlyphID + 1:
            return None
        valueSize = self.converter.staticSize
        return (
            6 + len(values) * valueSize,
            8,
            lambda: self.writeFormat8(writer, font, values),
        )

    def writeFormat8(self, writer, font, values):
        firstGlyphID = values[0][0]
        writer.writeUShort(8)
        writer.writeUShort(firstGlyphID)
        writer.writeUShort(len(values))
        for _, value in values:
            self.converter.write(
                writer, font, tableDict=None, value=value, repeatIndex=None
            )

    def readFormat0(self, reader, font):
        numGlyphs = len(font.getGlyphOrder())
        data = self.converter.readArray(reader, font, tableDict=None, count=numGlyphs)
        return {font.getGlyphName(k): value for k, value in enumerate(data)}

    def readFormat2(self, reader, font):
        mapping = {}
        pos = reader.pos - 2  # start of table is at UShort for format
        unitSize, numUnits = reader.readUShort(), reader.readUShort()
        assert unitSize >= 4 + self.converter.staticSize, unitSize
        for i in range(numUnits):
            reader.seek(pos + i * unitSize + 12)
            last = reader.readUShort()
            first = reader.readUShort()
            value = self.converter.read(reader, font, tableDict=None)
            if last != 0xFFFF:
                for k in range(first, last + 1):
                    mapping[font.getGlyphName(k)] = value
        return mapping

    def readFormat4(self, reader, font):
        mapping = {}
        pos = reader.pos - 2  # start of table is at UShort for format
        unitSize = reader.readUShort()
        assert unitSize >= 6, unitSize
        for i in range(reader.readUShort()):
            reader.seek(pos + i * unitSize + 12)
            last = reader.readUShort()
            first = reader.readUShort()
            offset = reader.readUShort()
            if last != 0xFFFF:
                dataReader = reader.getSubReader(0)  # relative to current position
                dataReader.seek(pos + offset)  # relative to start of table
                data = self.converter.readArray(
                    dataReader, font, tableDict=None, count=last - first + 1
                )
                for k, v in enumerate(data):
                    mapping[font.getGlyphName(first + k)] = v
        return mapping

    def readFormat6(self, reader, font):
        mapping = {}
        pos = reader.pos - 2  # start of table is at UShort for format
        unitSize = reader.readUShort()
        assert unitSize >= 2 + self.converter.staticSize, unitSize
        for i in range(reader.readUShort()):
            reader.seek(pos + i * unitSize + 12)
            glyphID = reader.readUShort()
            value = self.converter.read(reader, font, tableDict=None)
            if glyphID != 0xFFFF:
                mapping[font.getGlyphName(glyphID)] = value
        return mapping

    def readFormat8(self, reader, font):
        first = reader.readUShort()
        count = reader.readUShort()
        data = self.converter.readArray(reader, font, tableDict=None, count=count)
        return {font.getGlyphName(first + k): value for (k, value) in enumerate(data)}

    def xmlRead(self, attrs, content, font):
        value = {}
        for element in content:
            if isinstance(element, tuple):
                name, a, eltContent = element
                if name == "Lookup":
                    value[a["glyph"]] = self.converter.xmlRead(a, eltContent, font)
        return value

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.begintag(name, attrs)
        xmlWriter.newline()
        for glyph, value in sorted(value.items()):
            self.converter.xmlWrite(
                xmlWriter, font, value=value, name="Lookup", attrs=[("glyph", glyph)]
            )
        xmlWriter.endtag(name)
        xmlWriter.newline()


# The AAT 'ankr' table has an unusual structure: An offset to an AATLookup
# followed by an offset to a glyph data table. Other than usual, the
# offsets in the AATLookup are not relative to the beginning of
# the beginning of the 'ankr' table, but relative to the glyph data table.
# So, to find the anchor data for a glyph, one needs to add the offset
# to the data table to the offset found in the AATLookup, and then use
# the sum of these two offsets to find the actual data.
class AATLookupWithDataOffset(BaseConverter):
    def read(self, reader, font, tableDict):
        lookupOffset = reader.readULong()
        dataOffset = reader.readULong()
        lookupReader = reader.getSubReader(lookupOffset)
        lookup = AATLookup("DataOffsets", None, None, UShort)
        offsets = lookup.read(lookupReader, font, tableDict)
        result = {}
        for glyph, offset in offsets.items():
            dataReader = reader.getSubReader(offset + dataOffset)
            item = self.tableClass()
            item.decompile(dataReader, font)
            result[glyph] = item
        return result

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        # We do not work with OTTableWriter sub-writers because
        # the offsets in our AATLookup are relative to our data
        # table, for which we need to provide an offset value itself.
        # It might have been possible to somehow make a kludge for
        # performing this indirect offset computation directly inside
        # OTTableWriter. But this would have made the internal logic
        # of OTTableWriter even more complex than it already is,
        # so we decided to roll our own offset computation for the
        # contents of the AATLookup and associated data table.
        offsetByGlyph, offsetByData, dataLen = {}, {}, 0
        compiledData = []
        for glyph in sorted(value, key=font.getGlyphID):
            subWriter = OTTableWriter()
            value[glyph].compile(subWriter, font)
            data = subWriter.getAllData()
            offset = offsetByData.get(data, None)
            if offset == None:
                offset = dataLen
                dataLen = dataLen + len(data)
                offsetByData[data] = offset
                compiledData.append(data)
            offsetByGlyph[glyph] = offset
        # For calculating the offsets to our AATLookup and data table,
        # we can use the regular OTTableWriter infrastructure.
        lookupWriter = writer.getSubWriter()
        lookup = AATLookup("DataOffsets", None, None, UShort)
        lookup.write(lookupWriter, font, tableDict, offsetByGlyph, None)

        dataWriter = writer.getSubWriter()
        writer.writeSubTable(lookupWriter, offsetSize=4)
        writer.writeSubTable(dataWriter, offsetSize=4)
        for d in compiledData:
            dataWriter.writeData(d)

    def xmlRead(self, attrs, content, font):
        lookup = AATLookup("DataOffsets", None, None, self.tableClass)
        return lookup.xmlRead(attrs, content, font)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        lookup = AATLookup("DataOffsets", None, None, self.tableClass)
        lookup.xmlWrite(xmlWriter, font, value, name, attrs)


class MorxSubtableConverter(BaseConverter):
    _PROCESSING_ORDERS = {
        # bits 30 and 28 of morx.CoverageFlags; see morx spec
        (False, False): "LayoutOrder",
        (True, False): "ReversedLayoutOrder",
        (False, True): "LogicalOrder",
        (True, True): "ReversedLogicalOrder",
    }

    _PROCESSING_ORDERS_REVERSED = {val: key for key, val in _PROCESSING_ORDERS.items()}

    def __init__(self, name, repeat, aux, tableClass=None, *, description=""):
        BaseConverter.__init__(
            self, name, repeat, aux, tableClass, description=description
        )

    def _setTextDirectionFromCoverageFlags(self, flags, subtable):
        if (flags & 0x20) != 0:
            subtable.TextDirection = "Any"
        elif (flags & 0x80) != 0:
            subtable.TextDirection = "Vertical"
        else:
            subtable.TextDirection = "Horizontal"

    def read(self, reader, font, tableDict):
        pos = reader.pos
        m = MorxSubtable()
        m.StructLength = reader.readULong()
        flags = reader.readUInt8()
        orderKey = ((flags & 0x40) != 0, (flags & 0x10) != 0)
        m.ProcessingOrder = self._PROCESSING_ORDERS[orderKey]
        self._setTextDirectionFromCoverageFlags(flags, m)
        m.Reserved = reader.readUShort()
        m.Reserved |= (flags & 0xF) << 16
        m.MorphType = reader.readUInt8()
        m.SubFeatureFlags = reader.readULong()
        tableClass = lookupTypes["morx"].get(m.MorphType)
        if tableClass is None:
            assert False, "unsupported 'morx' lookup type %s" % m.MorphType
        # To decode AAT ligatures, we need to know the subtable size.
        # The easiest way to pass this along is to create a new reader
        # that works on just the subtable as its data.
        headerLength = reader.pos - pos
        data = reader.data[reader.pos : reader.pos + m.StructLength - headerLength]
        assert len(data) == m.StructLength - headerLength
        subReader = OTTableReader(data=data, tableTag=reader.tableTag)
        m.SubStruct = tableClass()
        m.SubStruct.decompile(subReader, font)
        reader.seek(pos + m.StructLength)
        return m

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.begintag(name, attrs)
        xmlWriter.newline()
        xmlWriter.comment("StructLength=%d" % value.StructLength)
        xmlWriter.newline()
        xmlWriter.simpletag("TextDirection", value=value.TextDirection)
        xmlWriter.newline()
        xmlWriter.simpletag("ProcessingOrder", value=value.ProcessingOrder)
        xmlWriter.newline()
        if value.Reserved != 0:
            xmlWriter.simpletag("Reserved", value="0x%04x" % value.Reserved)
            xmlWriter.newline()
        xmlWriter.comment("MorphType=%d" % value.MorphType)
        xmlWriter.newline()
        xmlWriter.simpletag("SubFeatureFlags", value="0x%08x" % value.SubFeatureFlags)
        xmlWriter.newline()
        value.SubStruct.toXML(xmlWriter, font)
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def xmlRead(self, attrs, content, font):
        m = MorxSubtable()
        covFlags = 0
        m.Reserved = 0
        for eltName, eltAttrs, eltContent in filter(istuple, content):
            if eltName == "CoverageFlags":
                # Only in XML from old versions of fonttools.
                covFlags = safeEval(eltAttrs["value"])
                orderKey = ((covFlags & 0x40) != 0, (covFlags & 0x10) != 0)
                m.ProcessingOrder = self._PROCESSING_ORDERS[orderKey]
                self._setTextDirectionFromCoverageFlags(covFlags, m)
            elif eltName == "ProcessingOrder":
                m.ProcessingOrder = eltAttrs["value"]
                assert m.ProcessingOrder in self._PROCESSING_ORDERS_REVERSED, (
                    "unknown ProcessingOrder: %s" % m.ProcessingOrder
                )
            elif eltName == "TextDirection":
                m.TextDirection = eltAttrs["value"]
                assert m.TextDirection in {"Horizontal", "Vertical", "Any"}, (
                    "unknown TextDirection %s" % m.TextDirection
                )
            elif eltName == "Reserved":
                m.Reserved = safeEval(eltAttrs["value"])
            elif eltName == "SubFeatureFlags":
                m.SubFeatureFlags = safeEval(eltAttrs["value"])
            elif eltName.endswith("Morph"):
                m.fromXML(eltName, eltAttrs, eltContent, font)
            else:
                assert False, eltName
        m.Reserved = (covFlags & 0xF) << 16 | m.Reserved
        return m

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        covFlags = (value.Reserved & 0x000F0000) >> 16
        reverseOrder, logicalOrder = self._PROCESSING_ORDERS_REVERSED[
            value.ProcessingOrder
        ]
        covFlags |= 0x80 if value.TextDirection == "Vertical" else 0
        covFlags |= 0x40 if reverseOrder else 0
        covFlags |= 0x20 if value.TextDirection == "Any" else 0
        covFlags |= 0x10 if logicalOrder else 0
        value.CoverageFlags = covFlags
        lengthIndex = len(writer.items)
        before = writer.getDataLength()
        value.StructLength = 0xDEADBEEF
        # The high nibble of value.Reserved is actuallly encoded
        # into coverageFlags, so we need to clear it here.
        origReserved = value.Reserved  # including high nibble
        value.Reserved = value.Reserved & 0xFFFF  # without high nibble
        value.compile(writer, font)
        value.Reserved = origReserved  # restore original value
        assert writer.items[lengthIndex] == b"\xde\xad\xbe\xef"
        length = writer.getDataLength() - before
        writer.items[lengthIndex] = struct.pack(">L", length)


# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6Tables.html#ExtendedStateHeader
# TODO: Untangle the implementation of the various lookup-specific formats.
class STXHeader(BaseConverter):
    def __init__(self, name, repeat, aux, tableClass, *, description=""):
        BaseConverter.__init__(
            self, name, repeat, aux, tableClass, description=description
        )
        assert issubclass(self.tableClass, AATAction)
        self.classLookup = AATLookup("GlyphClasses", None, None, UShort)
        if issubclass(self.tableClass, ContextualMorphAction):
            self.perGlyphLookup = AATLookup("PerGlyphLookup", None, None, GlyphID)
        else:
            self.perGlyphLookup = None

    def read(self, reader, font, tableDict):
        table = AATStateTable()
        pos = reader.pos
        classTableReader = reader.getSubReader(0)
        stateArrayReader = reader.getSubReader(0)
        entryTableReader = reader.getSubReader(0)
        actionReader = None
        ligaturesReader = None
        table.GlyphClassCount = reader.readULong()
        classTableReader.seek(pos + reader.readULong())
        stateArrayReader.seek(pos + reader.readULong())
        entryTableReader.seek(pos + reader.readULong())
        if self.perGlyphLookup is not None:
            perGlyphTableReader = reader.getSubReader(0)
            perGlyphTableReader.seek(pos + reader.readULong())
        if issubclass(self.tableClass, LigatureMorphAction):
            actionReader = reader.getSubReader(0)
            actionReader.seek(pos + reader.readULong())
            ligComponentReader = reader.getSubReader(0)
            ligComponentReader.seek(pos + reader.readULong())
            ligaturesReader = reader.getSubReader(0)
            ligaturesReader.seek(pos + reader.readULong())
            numLigComponents = (ligaturesReader.pos - ligComponentReader.pos) // 2
            assert numLigComponents >= 0
            table.LigComponents = ligComponentReader.readUShortArray(numLigComponents)
            table.Ligatures = self._readLigatures(ligaturesReader, font)
        elif issubclass(self.tableClass, InsertionMorphAction):
            actionReader = reader.getSubReader(0)
            actionReader.seek(pos + reader.readULong())
        table.GlyphClasses = self.classLookup.read(classTableReader, font, tableDict)
        numStates = int(
            (entryTableReader.pos - stateArrayReader.pos) / (table.GlyphClassCount * 2)
        )
        for stateIndex in range(numStates):
            state = AATState()
            table.States.append(state)
            for glyphClass in range(table.GlyphClassCount):
                entryIndex = stateArrayReader.readUShort()
                state.Transitions[glyphClass] = self._readTransition(
                    entryTableReader, entryIndex, font, actionReader
                )
        if self.perGlyphLookup is not None:
            table.PerGlyphLookups = self._readPerGlyphLookups(
                table, perGlyphTableReader, font
            )
        return table

    def _readTransition(self, reader, entryIndex, font, actionReader):
        transition = self.tableClass()
        entryReader = reader.getSubReader(
            reader.pos + entryIndex * transition.staticSize
        )
        transition.decompile(entryReader, font, actionReader)
        return transition

    def _readLigatures(self, reader, font):
        limit = len(reader.data)
        numLigatureGlyphs = (limit - reader.pos) // 2
        return font.getGlyphNameMany(reader.readUShortArray(numLigatureGlyphs))

    def _countPerGlyphLookups(self, table):
        # Somewhat annoyingly, the morx table does not encode
        # the size of the per-glyph table. So we need to find
        # the maximum value that MorphActions use as index
        # into this table.
        numLookups = 0
        for state in table.States:
            for t in state.Transitions.values():
                if isinstance(t, ContextualMorphAction):
                    if t.MarkIndex != 0xFFFF:
                        numLookups = max(numLookups, t.MarkIndex + 1)
                    if t.CurrentIndex != 0xFFFF:
                        numLookups = max(numLookups, t.CurrentIndex + 1)
        return numLookups

    def _readPerGlyphLookups(self, table, reader, font):
        pos = reader.pos
        lookups = []
        for _ in range(self._countPerGlyphLookups(table)):
            lookupReader = reader.getSubReader(0)
            lookupReader.seek(pos + reader.readULong())
            lookups.append(self.perGlyphLookup.read(lookupReader, font, {}))
        return lookups

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        glyphClassWriter = OTTableWriter()
        self.classLookup.write(
            glyphClassWriter, font, tableDict, value.GlyphClasses, repeatIndex=None
        )
        glyphClassData = pad(glyphClassWriter.getAllData(), 2)
        glyphClassCount = max(value.GlyphClasses.values()) + 1
        glyphClassTableOffset = 16  # size of STXHeader
        if self.perGlyphLookup is not None:
            glyphClassTableOffset += 4

        glyphClassTableOffset += self.tableClass.actionHeaderSize
        actionData, actionIndex = self.tableClass.compileActions(font, value.States)
        stateArrayData, entryTableData = self._compileStates(
            font, value.States, glyphClassCount, actionIndex
        )
        stateArrayOffset = glyphClassTableOffset + len(glyphClassData)
        entryTableOffset = stateArrayOffset + len(stateArrayData)
        perGlyphOffset = entryTableOffset + len(entryTableData)
        perGlyphData = pad(self._compilePerGlyphLookups(value, font), 4)
        if actionData is not None:
            actionOffset = entryTableOffset + len(entryTableData)
        else:
            actionOffset = None

        ligaturesOffset, ligComponentsOffset = None, None
        ligComponentsData = self._compileLigComponents(value, font)
        ligaturesData = self._compileLigatures(value, font)
        if ligComponentsData is not None:
            assert len(perGlyphData) == 0
            ligComponentsOffset = actionOffset + len(actionData)
            ligaturesOffset = ligComponentsOffset + len(ligComponentsData)

        writer.writeULong(glyphClassCount)
        writer.writeULong(glyphClassTableOffset)
        writer.writeULong(stateArrayOffset)
        writer.writeULong(entryTableOffset)
        if self.perGlyphLookup is not None:
            writer.writeULong(perGlyphOffset)
        if actionOffset is not None:
            writer.writeULong(actionOffset)
        if ligComponentsOffset is not None:
            writer.writeULong(ligComponentsOffset)
            writer.writeULong(ligaturesOffset)
        writer.writeData(glyphClassData)
        writer.writeData(stateArrayData)
        writer.writeData(entryTableData)
        writer.writeData(perGlyphData)
        if actionData is not None:
            writer.writeData(actionData)
        if ligComponentsData is not None:
            writer.writeData(ligComponentsData)
        if ligaturesData is not None:
            writer.writeData(ligaturesData)

    def _compileStates(self, font, states, glyphClassCount, actionIndex):
        stateArrayWriter = OTTableWriter()
        entries, entryIDs = [], {}
        for state in states:
            for glyphClass in range(glyphClassCount):
                transition = state.Transitions[glyphClass]
                entryWriter = OTTableWriter()
                transition.compile(entryWriter, font, actionIndex)
                entryData = entryWriter.getAllData()
                assert (
                    len(entryData) == transition.staticSize
                ), "%s has staticSize %d, " "but actually wrote %d bytes" % (
                    repr(transition),
                    transition.staticSize,
                    len(entryData),
                )
                entryIndex = entryIDs.get(entryData)
                if entryIndex is None:
                    entryIndex = len(entries)
                    entryIDs[entryData] = entryIndex
                    entries.append(entryData)
                stateArrayWriter.writeUShort(entryIndex)
        stateArrayData = pad(stateArrayWriter.getAllData(), 4)
        entryTableData = pad(bytesjoin(entries), 4)
        return stateArrayData, entryTableData

    def _compilePerGlyphLookups(self, table, font):
        if self.perGlyphLookup is None:
            return b""
        numLookups = self._countPerGlyphLookups(table)
        assert len(table.PerGlyphLookups) == numLookups, (
            "len(AATStateTable.PerGlyphLookups) is %d, "
            "but the actions inside the table refer to %d"
            % (len(table.PerGlyphLookups), numLookups)
        )
        writer = OTTableWriter()
        for lookup in table.PerGlyphLookups:
            lookupWriter = writer.getSubWriter()
            self.perGlyphLookup.write(lookupWriter, font, {}, lookup, None)
            writer.writeSubTable(lookupWriter, offsetSize=4)
        return writer.getAllData()

    def _compileLigComponents(self, table, font):
        if not hasattr(table, "LigComponents"):
            return None
        writer = OTTableWriter()
        for component in table.LigComponents:
            writer.writeUShort(component)
        return writer.getAllData()

    def _compileLigatures(self, table, font):
        if not hasattr(table, "Ligatures"):
            return None
        writer = OTTableWriter()
        for glyphName in table.Ligatures:
            writer.writeUShort(font.getGlyphID(glyphName))
        return writer.getAllData()

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.begintag(name, attrs)
        xmlWriter.newline()
        xmlWriter.comment("GlyphClassCount=%s" % value.GlyphClassCount)
        xmlWriter.newline()
        for g, klass in sorted(value.GlyphClasses.items()):
            xmlWriter.simpletag("GlyphClass", glyph=g, value=klass)
            xmlWriter.newline()
        for stateIndex, state in enumerate(value.States):
            xmlWriter.begintag("State", index=stateIndex)
            xmlWriter.newline()
            for glyphClass, trans in sorted(state.Transitions.items()):
                trans.toXML(
                    xmlWriter,
                    font=font,
                    attrs={"onGlyphClass": glyphClass},
                    name="Transition",
                )
            xmlWriter.endtag("State")
            xmlWriter.newline()
        for i, lookup in enumerate(value.PerGlyphLookups):
            xmlWriter.begintag("PerGlyphLookup", index=i)
            xmlWriter.newline()
            for glyph, val in sorted(lookup.items()):
                xmlWriter.simpletag("Lookup", glyph=glyph, value=val)
                xmlWriter.newline()
            xmlWriter.endtag("PerGlyphLookup")
            xmlWriter.newline()
        if hasattr(value, "LigComponents"):
            xmlWriter.begintag("LigComponents")
            xmlWriter.newline()
            for i, val in enumerate(getattr(value, "LigComponents")):
                xmlWriter.simpletag("LigComponent", index=i, value=val)
                xmlWriter.newline()
            xmlWriter.endtag("LigComponents")
            xmlWriter.newline()
        self._xmlWriteLigatures(xmlWriter, font, value, name, attrs)
        xmlWriter.endtag(name)
        xmlWriter.newline()

    def _xmlWriteLigatures(self, xmlWriter, font, value, name, attrs):
        if not hasattr(value, "Ligatures"):
            return
        xmlWriter.begintag("Ligatures")
        xmlWriter.newline()
        for i, g in enumerate(getattr(value, "Ligatures")):
            xmlWriter.simpletag("Ligature", index=i, glyph=g)
            xmlWriter.newline()
        xmlWriter.endtag("Ligatures")
        xmlWriter.newline()

    def xmlRead(self, attrs, content, font):
        table = AATStateTable()
        for eltName, eltAttrs, eltContent in filter(istuple, content):
            if eltName == "GlyphClass":
                glyph = eltAttrs["glyph"]
                value = eltAttrs["value"]
                table.GlyphClasses[glyph] = safeEval(value)
            elif eltName == "State":
                state = self._xmlReadState(eltAttrs, eltContent, font)
                table.States.append(state)
            elif eltName == "PerGlyphLookup":
                lookup = self.perGlyphLookup.xmlRead(eltAttrs, eltContent, font)
                table.PerGlyphLookups.append(lookup)
            elif eltName == "LigComponents":
                table.LigComponents = self._xmlReadLigComponents(
                    eltAttrs, eltContent, font
                )
            elif eltName == "Ligatures":
                table.Ligatures = self._xmlReadLigatures(eltAttrs, eltContent, font)
        table.GlyphClassCount = max(table.GlyphClasses.values()) + 1
        return table

    def _xmlReadState(self, attrs, content, font):
        state = AATState()
        for eltName, eltAttrs, eltContent in filter(istuple, content):
            if eltName == "Transition":
                glyphClass = safeEval(eltAttrs["onGlyphClass"])
                transition = self.tableClass()
                transition.fromXML(eltName, eltAttrs, eltContent, font)
                state.Transitions[glyphClass] = transition
        return state

    def _xmlReadLigComponents(self, attrs, content, font):
        ligComponents = []
        for eltName, eltAttrs, _eltContent in filter(istuple, content):
            if eltName == "LigComponent":
                ligComponents.append(safeEval(eltAttrs["value"]))
        return ligComponents

    def _xmlReadLigatures(self, attrs, content, font):
        ligs = []
        for eltName, eltAttrs, _eltContent in filter(istuple, content):
            if eltName == "Ligature":
                ligs.append(eltAttrs["glyph"])
        return ligs


class CIDGlyphMap(BaseConverter):
    def read(self, reader, font, tableDict):
        numCIDs = reader.readUShort()
        result = {}
        for cid, glyphID in enumerate(reader.readUShortArray(numCIDs)):
            if glyphID != 0xFFFF:
                result[cid] = font.getGlyphName(glyphID)
        return result

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        items = {cid: font.getGlyphID(glyph) for cid, glyph in value.items()}
        count = max(items) + 1 if items else 0
        writer.writeUShort(count)
        for cid in range(count):
            writer.writeUShort(items.get(cid, 0xFFFF))

    def xmlRead(self, attrs, content, font):
        result = {}
        for eName, eAttrs, _eContent in filter(istuple, content):
            if eName == "CID":
                result[safeEval(eAttrs["cid"])] = eAttrs["glyph"].strip()
        return result

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.begintag(name, attrs)
        xmlWriter.newline()
        for cid, glyph in sorted(value.items()):
            if glyph is not None and glyph != 0xFFFF:
                xmlWriter.simpletag("CID", cid=cid, glyph=glyph)
                xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()


class GlyphCIDMap(BaseConverter):
    def read(self, reader, font, tableDict):
        glyphOrder = font.getGlyphOrder()
        count = reader.readUShort()
        cids = reader.readUShortArray(count)
        if count > len(glyphOrder):
            log.warning(
                "GlyphCIDMap has %d elements, "
                "but the font has only %d glyphs; "
                "ignoring the rest" % (count, len(glyphOrder))
            )
        result = {}
        for glyphID in range(min(len(cids), len(glyphOrder))):
            cid = cids[glyphID]
            if cid != 0xFFFF:
                result[glyphOrder[glyphID]] = cid
        return result

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        items = {
            font.getGlyphID(g): cid
            for g, cid in value.items()
            if cid is not None and cid != 0xFFFF
        }
        count = max(items) + 1 if items else 0
        writer.writeUShort(count)
        for glyphID in range(count):
            writer.writeUShort(items.get(glyphID, 0xFFFF))

    def xmlRead(self, attrs, content, font):
        result = {}
        for eName, eAttrs, _eContent in filter(istuple, content):
            if eName == "CID":
                result[eAttrs["glyph"]] = safeEval(eAttrs["value"])
        return result

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.begintag(name, attrs)
        xmlWriter.newline()
        for glyph, cid in sorted(value.items()):
            if cid is not None and cid != 0xFFFF:
                xmlWriter.simpletag("CID", glyph=glyph, value=cid)
                xmlWriter.newline()
        xmlWriter.endtag(name)
        xmlWriter.newline()


class DeltaValue(BaseConverter):
    def read(self, reader, font, tableDict):
        StartSize = tableDict["StartSize"]
        EndSize = tableDict["EndSize"]
        DeltaFormat = tableDict["DeltaFormat"]
        assert DeltaFormat in (1, 2, 3), "illegal DeltaFormat"
        nItems = EndSize - StartSize + 1
        nBits = 1 << DeltaFormat
        minusOffset = 1 << nBits
        mask = (1 << nBits) - 1
        signMask = 1 << (nBits - 1)

        DeltaValue = []
        tmp, shift = 0, 0
        for i in range(nItems):
            if shift == 0:
                tmp, shift = reader.readUShort(), 16
            shift = shift - nBits
            value = (tmp >> shift) & mask
            if value & signMask:
                value = value - minusOffset
            DeltaValue.append(value)
        return DeltaValue

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        StartSize = tableDict["StartSize"]
        EndSize = tableDict["EndSize"]
        DeltaFormat = tableDict["DeltaFormat"]
        DeltaValue = value
        assert DeltaFormat in (1, 2, 3), "illegal DeltaFormat"
        nItems = EndSize - StartSize + 1
        nBits = 1 << DeltaFormat
        assert len(DeltaValue) == nItems
        mask = (1 << nBits) - 1

        tmp, shift = 0, 16
        for value in DeltaValue:
            shift = shift - nBits
            tmp = tmp | ((value & mask) << shift)
            if shift == 0:
                writer.writeUShort(tmp)
                tmp, shift = 0, 16
        if shift != 16:
            writer.writeUShort(tmp)

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", value)])
        xmlWriter.newline()

    def xmlRead(self, attrs, content, font):
        return safeEval(attrs["value"])


class VarIdxMapValue(BaseConverter):
    def read(self, reader, font, tableDict):
        fmt = tableDict["EntryFormat"]
        nItems = tableDict["MappingCount"]

        innerBits = 1 + (fmt & 0x000F)
        innerMask = (1 << innerBits) - 1
        outerMask = 0xFFFFFFFF - innerMask
        outerShift = 16 - innerBits

        entrySize = 1 + ((fmt & 0x0030) >> 4)
        readArray = {
            1: reader.readUInt8Array,
            2: reader.readUShortArray,
            3: reader.readUInt24Array,
            4: reader.readULongArray,
        }[entrySize]

        return [
            (((raw & outerMask) << outerShift) | (raw & innerMask))
            for raw in readArray(nItems)
        ]

    def write(self, writer, font, tableDict, value, repeatIndex=None):
        fmt = tableDict["EntryFormat"]
        mapping = value
        writer["MappingCount"].setValue(len(mapping))

        innerBits = 1 + (fmt & 0x000F)
        innerMask = (1 << innerBits) - 1
        outerShift = 16 - innerBits

        entrySize = 1 + ((fmt & 0x0030) >> 4)
        writeArray = {
            1: writer.writeUInt8Array,
            2: writer.writeUShortArray,
            3: writer.writeUInt24Array,
            4: writer.writeULongArray,
        }[entrySize]

        writeArray(
            [
                (((idx & 0xFFFF0000) >> outerShift) | (idx & innerMask))
                for idx in mapping
            ]
        )


class VarDataValue(BaseConverter):
    def read(self, reader, font, tableDict):
        values = []

        regionCount = tableDict["VarRegionCount"]
        wordCount = tableDict["NumShorts"]

        # https://github.com/fonttools/fonttools/issues/2279
        longWords = bool(wordCount & 0x8000)
        wordCount = wordCount & 0x7FFF

        if longWords:
            readBigArray, readSmallArray = reader.readLongArray, reader.readShortArray
        else:
            readBigArray, readSmallArray = reader.readShortArray, reader.readInt8Array

        n1, n2 = min(regionCount, wordCount), max(regionCount, wordCount)
        values.extend(readBigArray(n1))
        values.extend(readSmallArray(n2 - n1))
        if n2 > regionCount:  # Padding
            del values[regionCount:]

        return values

    def write(self, writer, font, tableDict, values, repeatIndex=None):
        regionCount = tableDict["VarRegionCount"]
        wordCount = tableDict["NumShorts"]

        # https://github.com/fonttools/fonttools/issues/2279
        longWords = bool(wordCount & 0x8000)
        wordCount = wordCount & 0x7FFF

        (writeBigArray, writeSmallArray) = {
            False: (writer.writeShortArray, writer.writeInt8Array),
            True: (writer.writeLongArray, writer.writeShortArray),
        }[longWords]

        n1, n2 = min(regionCount, wordCount), max(regionCount, wordCount)
        writeBigArray(values[:n1])
        writeSmallArray(values[n1:regionCount])
        if n2 > regionCount:  # Padding
            writer.writeSmallArray([0] * (n2 - regionCount))

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", value)])
        xmlWriter.newline()

    def xmlRead(self, attrs, content, font):
        return safeEval(attrs["value"])


class TupleValues:
    def read(self, data, font):
        return TupleVariation.decompileDeltas_(None, data)[0]

    def write(self, writer, font, tableDict, values, repeatIndex=None):
        optimizeSpeed = font.cfg[OPTIMIZE_FONT_SPEED]
        return bytes(
            TupleVariation.compileDeltaValues_(values, optimizeSize=not optimizeSpeed)
        )

    def xmlRead(self, attrs, content, font):
        return safeEval(attrs["value"])

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", value)])
        xmlWriter.newline()


class CFF2Index(BaseConverter):
    def __init__(
        self,
        name,
        repeat,
        aux,
        tableClass=None,
        *,
        itemClass=None,
        itemConverterClass=None,
        description="",
    ):
        BaseConverter.__init__(
            self, name, repeat, aux, tableClass, description=description
        )
        self._itemClass = itemClass
        self._converter = (
            itemConverterClass() if itemConverterClass is not None else None
        )

    def read(self, reader, font, tableDict):
        count = reader.readULong()
        if count == 0:
            return []
        offSize = reader.readUInt8()

        def getReadArray(reader, offSize):
            return {
                1: reader.readUInt8Array,
                2: reader.readUShortArray,
                3: reader.readUInt24Array,
                4: reader.readULongArray,
            }[offSize]

        readArray = getReadArray(reader, offSize)

        lazy = font.lazy is not False and count > 8
        if not lazy:
            offsets = readArray(count + 1)
            items = []
            lastOffset = offsets.pop(0)
            reader.readData(lastOffset - 1)  # In case first offset is not 1

            for offset in offsets:
                assert lastOffset <= offset
                item = reader.readData(offset - lastOffset)

                if self._itemClass is not None:
                    obj = self._itemClass()
                    obj.decompile(item, font, reader.localState)
                    item = obj
                elif self._converter is not None:
                    item = self._converter.read(item, font)

                items.append(item)
                lastOffset = offset
            return items
        else:

            def get_read_item():
                reader_copy = reader.copy()
                offset_pos = reader.pos
                data_pos = offset_pos + (count + 1) * offSize - 1
                readArray = getReadArray(reader_copy, offSize)

                def read_item(i):
                    reader_copy.seek(offset_pos + i * offSize)
                    offsets = readArray(2)
                    reader_copy.seek(data_pos + offsets[0])
                    item = reader_copy.readData(offsets[1] - offsets[0])

                    if self._itemClass is not None:
                        obj = self._itemClass()
                        obj.decompile(item, font, reader_copy.localState)
                        item = obj
                    elif self._converter is not None:
                        item = self._converter.read(item, font)
                    return item

                return read_item

            read_item = get_read_item()
            l = LazyList([read_item] * count)

            # TODO: Advance reader

            return l

    def write(self, writer, font, tableDict, values, repeatIndex=None):
        items = values

        writer.writeULong(len(items))
        if not len(items):
            return

        if self._itemClass is not None:
            items = [item.compile(font) for item in items]
        elif self._converter is not None:
            items = [
                self._converter.write(writer, font, tableDict, item, i)
                for i, item in enumerate(items)
            ]

        offsets = [len(item) for item in items]
        offsets = list(accumulate(offsets, initial=1))

        lastOffset = offsets[-1]
        offSize = (
            1
            if lastOffset < 0x100
            else 2 if lastOffset < 0x10000 else 3 if lastOffset < 0x1000000 else 4
        )
        writer.writeUInt8(offSize)

        writeArray = {
            1: writer.writeUInt8Array,
            2: writer.writeUShortArray,
            3: writer.writeUInt24Array,
            4: writer.writeULongArray,
        }[offSize]

        writeArray(offsets)
        for item in items:
            writer.writeData(item)

    def xmlRead(self, attrs, content, font):
        if self._itemClass is not None:
            obj = self._itemClass()
            obj.fromXML(None, attrs, content, font)
            return obj
        elif self._converter is not None:
            return self._converter.xmlRead(attrs, content, font)
        else:
            raise NotImplementedError()

    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        if self._itemClass is not None:
            for i, item in enumerate(value):
                item.toXML(xmlWriter, font, [("index", i)], name)
        elif self._converter is not None:
            for i, item in enumerate(value):
                self._converter.xmlWrite(
                    xmlWriter, font, item, name, attrs + [("index", i)]
                )
        else:
            raise NotImplementedError()


class LookupFlag(UShort):
    def xmlWrite(self, xmlWriter, font, value, name, attrs):
        xmlWriter.simpletag(name, attrs + [("value", value)])
        flags = []
        if value & 0x01:
            flags.append("rightToLeft")
        if value & 0x02:
            flags.append("ignoreBaseGlyphs")
        if value & 0x04:
            flags.append("ignoreLigatures")
        if value & 0x08:
            flags.append("ignoreMarks")
        if value & 0x10:
            flags.append("useMarkFilteringSet")
        if value & 0xFF00:
            flags.append("markAttachmentType[%i]" % (value >> 8))
        if flags:
            xmlWriter.comment(" ".join(flags))
        xmlWriter.newline()


class _UInt8Enum(UInt8):
    enumClass = NotImplemented

    def read(self, reader, font, tableDict):
        return self.enumClass(super().read(reader, font, tableDict))

    @classmethod
    def fromString(cls, value):
        return getattr(cls.enumClass, value.upper())

    @classmethod
    def toString(cls, value):
        return cls.enumClass(value).name.lower()


class ExtendMode(_UInt8Enum):
    enumClass = _ExtendMode


class CompositeMode(_UInt8Enum):
    enumClass = _CompositeMode


converterMapping = {
    # type		class
    "int8": Int8,
    "int16": Short,
    "int32": Long,
    "uint8": UInt8,
    "uint16": UShort,
    "uint24": UInt24,
    "uint32": ULong,
    "char64": Char64,
    "Flags32": Flags32,
    "VarIndex": VarIndex,
    "Version": Version,
    "Tag": Tag,
    "GlyphID": GlyphID,
    "GlyphID32": GlyphID32,
    "NameID": NameID,
    "DeciPoints": DeciPoints,
    "Fixed": Fixed,
    "F2Dot14": F2Dot14,
    "Angle": Angle,
    "BiasedAngle": BiasedAngle,
    "struct": Struct,
    "Offset": Table,
    "LOffset": LTable,
    "Offset24": Table24,
    "ValueRecord": ValueRecord,
    "DeltaValue": DeltaValue,
    "VarIdxMapValue": VarIdxMapValue,
    "VarDataValue": VarDataValue,
    "LookupFlag": LookupFlag,
    "ExtendMode": ExtendMode,
    "CompositeMode": CompositeMode,
    "STATFlags": STATFlags,
    "TupleList": partial(CFF2Index, itemConverterClass=TupleValues),
    "VarCompositeGlyphList": partial(CFF2Index, itemClass=VarCompositeGlyph),
    # AAT
    "CIDGlyphMap": CIDGlyphMap,
    "GlyphCIDMap": GlyphCIDMap,
    "MortChain": StructWithLength,
    "MortSubtable": StructWithLength,
    "MorxChain": StructWithLength,
    "MorxSubtable": MorxSubtableConverter,
    # "Template" types
    "AATLookup": lambda C: partial(AATLookup, tableClass=C),
    "AATLookupWithDataOffset": lambda C: partial(AATLookupWithDataOffset, tableClass=C),
    "STXHeader": lambda C: partial(STXHeader, tableClass=C),
    "OffsetTo": lambda C: partial(Table, tableClass=C),
    "LOffsetTo": lambda C: partial(LTable, tableClass=C),
    "LOffset24To": lambda C: partial(Table24, tableClass=C),
}
