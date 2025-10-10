from fontTools.config import OPTIONS
from fontTools.misc.textTools import Tag, bytesjoin
from .DefaultTable import DefaultTable
from enum import IntEnum
import sys
import array
import struct
import logging
from functools import lru_cache
from typing import Iterator, NamedTuple, Optional, Tuple

log = logging.getLogger(__name__)

have_uharfbuzz = False
try:
    import uharfbuzz as hb

    # repack method added in uharfbuzz >= 0.23; if uharfbuzz *can* be
    # imported but repack method is missing, behave as if uharfbuzz
    # is not available (fallback to the slower Python implementation)
    have_uharfbuzz = callable(getattr(hb, "repack", None))
except ImportError:
    pass

USE_HARFBUZZ_REPACKER = OPTIONS[f"{__name__}:USE_HARFBUZZ_REPACKER"]


class OverflowErrorRecord(object):
    def __init__(self, overflowTuple):
        self.tableType = overflowTuple[0]
        self.LookupListIndex = overflowTuple[1]
        self.SubTableIndex = overflowTuple[2]
        self.itemName = overflowTuple[3]
        self.itemIndex = overflowTuple[4]

    def __repr__(self):
        return str(
            (
                self.tableType,
                "LookupIndex:",
                self.LookupListIndex,
                "SubTableIndex:",
                self.SubTableIndex,
                "ItemName:",
                self.itemName,
                "ItemIndex:",
                self.itemIndex,
            )
        )


class OTLOffsetOverflowError(Exception):
    def __init__(self, overflowErrorRecord):
        self.value = overflowErrorRecord

    def __str__(self):
        return repr(self.value)


class RepackerState(IntEnum):
    # Repacking control flow is implemnted using a state machine. The state machine table:
    #
    # State       | Packing Success | Packing Failed | Exception Raised |
    # ------------+-----------------+----------------+------------------+
    # PURE_FT     | Return result   | PURE_FT        | Return failure   |
    # HB_FT       | Return result   | HB_FT          | FT_FALLBACK      |
    # FT_FALLBACK | HB_FT           | FT_FALLBACK    | Return failure   |

    # Pack only with fontTools, don't allow sharing between extensions.
    PURE_FT = 1

    # Attempt to pack with harfbuzz (allowing sharing between extensions)
    # use fontTools to attempt overflow resolution.
    HB_FT = 2

    # Fallback if HB/FT packing gets stuck. Pack only with fontTools, don't allow sharing between
    # extensions.
    FT_FALLBACK = 3


class BaseTTXConverter(DefaultTable):
    """Generic base class for TTX table converters. It functions as an
    adapter between the TTX (ttLib actually) table model and the model
    we use for OpenType tables, which is necessarily subtly different.
    """

    def decompile(self, data, font):
        """Create an object from the binary data. Called automatically on access."""
        from . import otTables

        reader = OTTableReader(data, tableTag=self.tableTag)
        tableClass = getattr(otTables, self.tableTag)
        self.table = tableClass()
        self.table.decompile(reader, font)

    def compile(self, font):
        """Compiles the table into binary. Called automatically on save."""

        # General outline:
        # Create a top-level OTTableWriter for the GPOS/GSUB table.
        # 	Call the compile method for the the table
        # 		for each 'converter' record in the table converter list
        # 			call converter's write method for each item in the value.
        # 				- For simple items, the write method adds a string to the
        # 				writer's self.items list.
        # 				- For Struct/Table/Subtable items, it add first adds new writer to the
        # 				to the writer's self.items, then calls the item's compile method.
        # 				This creates a tree of writers, rooted at the GUSB/GPOS writer, with
        # 				each writer representing a table, and the writer.items list containing
        # 				the child data strings and writers.
        # 	call the getAllData method
        # 		call _doneWriting, which removes duplicates
        # 		call _gatherTables. This traverses the tables, adding unique occurences to a flat list of tables
        # 		Traverse the flat list of tables, calling getDataLength on each to update their position
        # 		Traverse the flat list of tables again, calling getData each get the data in the table, now that
        # 		pos's and offset are known.

        # 		If a lookup subtable overflows an offset, we have to start all over.
        overflowRecord = None
        # this is 3-state option: default (None) means automatically use hb.repack or
        # silently fall back if it fails; True, use it and raise error if not possible
        # or it errors out; False, don't use it, even if you can.
        use_hb_repack = font.cfg[USE_HARFBUZZ_REPACKER]
        if self.tableTag in ("GSUB", "GPOS"):
            if use_hb_repack is False:
                log.debug(
                    "hb.repack disabled, compiling '%s' with pure-python serializer",
                    self.tableTag,
                )
            elif not have_uharfbuzz:
                if use_hb_repack is True:
                    raise ImportError("No module named 'uharfbuzz'")
                else:
                    assert use_hb_repack is None
                    log.debug(
                        "uharfbuzz not found, compiling '%s' with pure-python serializer",
                        self.tableTag,
                    )

        if (
            use_hb_repack in (None, True)
            and have_uharfbuzz
            and self.tableTag in ("GSUB", "GPOS")
        ):
            state = RepackerState.HB_FT
        else:
            state = RepackerState.PURE_FT

        hb_first_error_logged = False
        lastOverflowRecord = None
        while True:
            try:
                writer = OTTableWriter(tableTag=self.tableTag)
                self.table.compile(writer, font)
                if state == RepackerState.HB_FT:
                    return self.tryPackingHarfbuzz(writer, hb_first_error_logged)
                elif state == RepackerState.PURE_FT:
                    return self.tryPackingFontTools(writer)
                elif state == RepackerState.FT_FALLBACK:
                    # Run packing with FontTools only, but don't return the result as it will
                    # not be optimally packed. Once a successful packing has been found, state is
                    # changed back to harfbuzz packing to produce the final, optimal, packing.
                    self.tryPackingFontTools(writer)
                    log.debug(
                        "Re-enabling sharing between extensions and switching back to "
                        "harfbuzz+fontTools packing."
                    )
                    state = RepackerState.HB_FT

            except OTLOffsetOverflowError as e:
                hb_first_error_logged = True
                ok = self.tryResolveOverflow(font, e, lastOverflowRecord)
                lastOverflowRecord = e.value

                if ok:
                    continue

                if state is RepackerState.HB_FT:
                    log.debug(
                        "Harfbuzz packing out of resolutions, disabling sharing between extensions and "
                        "switching to fontTools only packing."
                    )
                    state = RepackerState.FT_FALLBACK
                else:
                    raise

    def tryPackingHarfbuzz(self, writer, hb_first_error_logged):
        try:
            log.debug("serializing '%s' with hb.repack", self.tableTag)
            return writer.getAllDataUsingHarfbuzz(self.tableTag)
        except (ValueError, MemoryError, hb.RepackerError) as e:
            # Only log hb repacker errors the first time they occur in
            # the offset-overflow resolution loop, they are just noisy.
            # Maybe we can revisit this if/when uharfbuzz actually gives
            # us more info as to why hb.repack failed...
            if not hb_first_error_logged:
                error_msg = f"{type(e).__name__}"
                if str(e) != "":
                    error_msg += f": {e}"
                log.warning(
                    "hb.repack failed to serialize '%s', attempting fonttools resolutions "
                    "; the error message was: %s",
                    self.tableTag,
                    error_msg,
                )
                hb_first_error_logged = True
            return writer.getAllData(remove_duplicate=False)

    def tryPackingFontTools(self, writer):
        return writer.getAllData()

    def tryResolveOverflow(self, font, e, lastOverflowRecord):
        ok = 0
        if lastOverflowRecord == e.value:
            # Oh well...
            return ok

        overflowRecord = e.value
        log.info("Attempting to fix OTLOffsetOverflowError %s", e)

        if overflowRecord.itemName is None:
            from .otTables import fixLookupOverFlows

            ok = fixLookupOverFlows(font, overflowRecord)
        else:
            from .otTables import fixSubTableOverFlows

            ok = fixSubTableOverFlows(font, overflowRecord)

        if ok:
            return ok

        # Try upgrading lookup to Extension and hope
        # that cross-lookup sharing not happening would
        # fix overflow...
        from .otTables import fixLookupOverFlows

        return fixLookupOverFlows(font, overflowRecord)

    def toXML(self, writer, font):
        self.table.toXML2(writer, font)

    def fromXML(self, name, attrs, content, font):
        from . import otTables

        if not hasattr(self, "table"):
            tableClass = getattr(otTables, self.tableTag)
            self.table = tableClass()
        self.table.fromXML(name, attrs, content, font)
        self.table.populateDefaults()

    def ensureDecompiled(self, recurse=True):
        self.table.ensureDecompiled(recurse=recurse)


# https://github.com/fonttools/fonttools/pull/2285#issuecomment-834652928
assert len(struct.pack("i", 0)) == 4
assert array.array("i").itemsize == 4, "Oops, file a bug against fonttools."


class OTTableReader(object):
    """Helper class to retrieve data from an OpenType table."""

    __slots__ = ("data", "offset", "pos", "localState", "tableTag")

    def __init__(self, data, localState=None, offset=0, tableTag=None):
        self.data = data
        self.offset = offset
        self.pos = offset
        self.localState = localState
        self.tableTag = tableTag

    def advance(self, count):
        self.pos += count

    def seek(self, pos):
        self.pos = pos

    def copy(self):
        other = self.__class__(self.data, self.localState, self.offset, self.tableTag)
        other.pos = self.pos
        return other

    def getSubReader(self, offset):
        offset = self.offset + offset
        return self.__class__(self.data, self.localState, offset, self.tableTag)

    def readValue(self, typecode, staticSize):
        pos = self.pos
        newpos = pos + staticSize
        (value,) = struct.unpack(f">{typecode}", self.data[pos:newpos])
        self.pos = newpos
        return value

    def readArray(self, typecode, staticSize, count):
        pos = self.pos
        newpos = pos + count * staticSize
        value = array.array(typecode, self.data[pos:newpos])
        if sys.byteorder != "big":
            value.byteswap()
        self.pos = newpos
        return value.tolist()

    def readInt8(self):
        return self.readValue("b", staticSize=1)

    def readInt8Array(self, count):
        return self.readArray("b", staticSize=1, count=count)

    def readShort(self):
        return self.readValue("h", staticSize=2)

    def readShortArray(self, count):
        return self.readArray("h", staticSize=2, count=count)

    def readLong(self):
        return self.readValue("i", staticSize=4)

    def readLongArray(self, count):
        return self.readArray("i", staticSize=4, count=count)

    def readUInt8(self):
        return self.readValue("B", staticSize=1)

    def readUInt8Array(self, count):
        return self.readArray("B", staticSize=1, count=count)

    def readUShort(self):
        return self.readValue("H", staticSize=2)

    def readUShortArray(self, count):
        return self.readArray("H", staticSize=2, count=count)

    def readULong(self):
        return self.readValue("I", staticSize=4)

    def readULongArray(self, count):
        return self.readArray("I", staticSize=4, count=count)

    def readUInt24(self):
        pos = self.pos
        newpos = pos + 3
        (value,) = struct.unpack(">l", b"\0" + self.data[pos:newpos])
        self.pos = newpos
        return value

    def readUInt24Array(self, count):
        return [self.readUInt24() for _ in range(count)]

    def readTag(self):
        pos = self.pos
        newpos = pos + 4
        value = Tag(self.data[pos:newpos])
        assert len(value) == 4, value
        self.pos = newpos
        return value

    def readData(self, count):
        pos = self.pos
        newpos = pos + count
        value = self.data[pos:newpos]
        self.pos = newpos
        return value

    def __setitem__(self, name, value):
        state = self.localState.copy() if self.localState else dict()
        state[name] = value
        self.localState = state

    def __getitem__(self, name):
        return self.localState and self.localState[name]

    def __contains__(self, name):
        return self.localState and name in self.localState


class OffsetToWriter(object):
    def __init__(self, subWriter, offsetSize):
        self.subWriter = subWriter
        self.offsetSize = offsetSize

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.subWriter == other.subWriter and self.offsetSize == other.offsetSize

    def __hash__(self):
        # only works after self._doneWriting() has been called
        return hash((self.subWriter, self.offsetSize))


class OTTableWriter(object):
    """Helper class to gather and assemble data for OpenType tables."""

    def __init__(self, localState=None, tableTag=None):
        self.items = []
        self.pos = None
        self.localState = localState
        self.tableTag = tableTag
        self.parent = None
        self.name = "<none>"

    def __setitem__(self, name, value):
        state = self.localState.copy() if self.localState else dict()
        state[name] = value
        self.localState = state

    def __getitem__(self, name):
        return self.localState[name]

    def __delitem__(self, name):
        del self.localState[name]

    # assembler interface

    def getDataLength(self):
        """Return the length of this table in bytes, without subtables."""
        l = 0
        for item in self.items:
            if hasattr(item, "getCountData"):
                l += item.size
            elif hasattr(item, "subWriter"):
                l += item.offsetSize
            else:
                l = l + len(item)
        return l

    def getData(self):
        """Assemble the data for this writer/table, without subtables."""
        items = list(self.items)  # make a shallow copy
        pos = self.pos
        numItems = len(items)
        for i in range(numItems):
            item = items[i]

            if hasattr(item, "subWriter"):
                if item.offsetSize == 4:
                    items[i] = packULong(item.subWriter.pos - pos)
                elif item.offsetSize == 2:
                    try:
                        items[i] = packUShort(item.subWriter.pos - pos)
                    except struct.error:
                        # provide data to fix overflow problem.
                        overflowErrorRecord = self.getOverflowErrorRecord(
                            item.subWriter
                        )

                        raise OTLOffsetOverflowError(overflowErrorRecord)
                elif item.offsetSize == 3:
                    items[i] = packUInt24(item.subWriter.pos - pos)
                else:
                    raise ValueError(item.offsetSize)

        return bytesjoin(items)

    def getDataForHarfbuzz(self):
        """Assemble the data for this writer/table with all offset field set to 0"""
        items = list(self.items)
        packFuncs = {2: packUShort, 3: packUInt24, 4: packULong}
        for i, item in enumerate(items):
            if hasattr(item, "subWriter"):
                # Offset value is not needed in harfbuzz repacker, so setting offset to 0 to avoid overflow here
                if item.offsetSize in packFuncs:
                    items[i] = packFuncs[item.offsetSize](0)
                else:
                    raise ValueError(item.offsetSize)

        return bytesjoin(items)

    def __hash__(self):
        # only works after self._doneWriting() has been called
        return hash(self.items)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.items == other.items

    def _doneWriting(self, internedTables, shareExtension=False):
        # Convert CountData references to data string items
        # collapse duplicate table references to a unique entry
        # "tables" are OTTableWriter objects.

        # For Extension Lookup types, we can
        # eliminate duplicates only within the tree under the Extension Lookup,
        # as offsets may exceed 64K even between Extension LookupTable subtables.
        isExtension = hasattr(self, "Extension")

        # Certain versions of Uniscribe reject the font if the GSUB/GPOS top-level
        # arrays (ScriptList, FeatureList, LookupList) point to the same, possibly
        # empty, array.  So, we don't share those.
        # See: https://github.com/fonttools/fonttools/issues/518
        dontShare = hasattr(self, "DontShare")

        if isExtension and not shareExtension:
            internedTables = {}

        items = self.items
        for i, item in enumerate(items):
            if hasattr(item, "getCountData"):
                items[i] = item.getCountData()
            elif hasattr(item, "subWriter"):
                item.subWriter._doneWriting(
                    internedTables, shareExtension=shareExtension
                )
                # At this point, all subwriters are hashable based on their items.
                # (See hash and comparison magic methods above.) So the ``setdefault``
                # call here will return the first writer object we've seen with
                # equal content, or store it in the dictionary if it's not been
                # seen yet. We therefore replace the subwriter object with an equivalent
                # object, which deduplicates the tree.
                if not dontShare:
                    items[i].subWriter = internedTables.setdefault(
                        item.subWriter, item.subWriter
                    )
        self.items = tuple(items)

    def _gatherTables(self, tables, extTables, done):
        # Convert table references in self.items tree to a flat
        # list of tables in depth-first traversal order.
        # "tables" are OTTableWriter objects.
        # We do the traversal in reverse order at each level, in order to
        # resolve duplicate references to be the last reference in the list of tables.
        # For extension lookups, duplicate references can be merged only within the
        # writer tree under the  extension lookup.

        done[id(self)] = True

        numItems = len(self.items)
        iRange = list(range(numItems))
        iRange.reverse()

        isExtension = hasattr(self, "Extension")

        selfTables = tables

        if isExtension:
            assert (
                extTables is not None
            ), "Program or XML editing error. Extension subtables cannot contain extensions subtables"
            tables, extTables, done = extTables, None, {}

        # add Coverage table if it is sorted last.
        sortCoverageLast = False
        if hasattr(self, "sortCoverageLast"):
            # Find coverage table
            for i in range(numItems):
                item = self.items[i]
                if (
                    hasattr(item, "subWriter")
                    and getattr(item.subWriter, "name", None) == "Coverage"
                ):
                    sortCoverageLast = True
                    break
            if id(item.subWriter) not in done:
                item.subWriter._gatherTables(tables, extTables, done)
            else:
                # We're a new parent of item
                pass

        for i in iRange:
            item = self.items[i]
            if not hasattr(item, "subWriter"):
                continue

            if (
                sortCoverageLast
                and (i == 1)
                and getattr(item.subWriter, "name", None) == "Coverage"
            ):
                # we've already 'gathered' it above
                continue

            if id(item.subWriter) not in done:
                item.subWriter._gatherTables(tables, extTables, done)
            else:
                # Item is already written out by other parent
                pass

        selfTables.append(self)

    def _gatherGraphForHarfbuzz(self, tables, obj_list, done, objidx, virtual_edges):
        real_links = []
        virtual_links = []
        item_idx = objidx

        # Merge virtual_links from parent
        for idx in virtual_edges:
            virtual_links.append((0, 0, idx))

        sortCoverageLast = False
        coverage_idx = 0
        if hasattr(self, "sortCoverageLast"):
            # Find coverage table
            for i, item in enumerate(self.items):
                if getattr(item, "name", None) == "Coverage":
                    sortCoverageLast = True
                    if id(item) not in done:
                        coverage_idx = item_idx = item._gatherGraphForHarfbuzz(
                            tables, obj_list, done, item_idx, virtual_edges
                        )
                    else:
                        coverage_idx = done[id(item)]
                    virtual_edges.append(coverage_idx)
                    break

        child_idx = 0
        offset_pos = 0
        for i, item in enumerate(self.items):
            if hasattr(item, "subWriter"):
                pos = offset_pos
            elif hasattr(item, "getCountData"):
                offset_pos += item.size
                continue
            else:
                offset_pos = offset_pos + len(item)
                continue

            if id(item.subWriter) not in done:
                child_idx = item_idx = item.subWriter._gatherGraphForHarfbuzz(
                    tables, obj_list, done, item_idx, virtual_edges
                )
            else:
                child_idx = done[id(item.subWriter)]

            real_edge = (pos, item.offsetSize, child_idx)
            real_links.append(real_edge)
            offset_pos += item.offsetSize

        tables.append(self)
        obj_list.append((real_links, virtual_links))
        item_idx += 1
        done[id(self)] = item_idx
        if sortCoverageLast:
            virtual_edges.pop()

        return item_idx

    def getAllDataUsingHarfbuzz(self, tableTag):
        """The Whole table is represented as a Graph.
        Assemble graph data and call Harfbuzz repacker to pack the table.
        Harfbuzz repacker is faster and retain as much sub-table sharing as possible, see also:
        https://github.com/harfbuzz/harfbuzz/blob/main/docs/repacker.md
        The input format for hb.repack() method is explained here:
        https://github.com/harfbuzz/uharfbuzz/blob/main/src/uharfbuzz/_harfbuzz.pyx#L1149
        """
        internedTables = {}
        self._doneWriting(internedTables, shareExtension=True)
        tables = []
        obj_list = []
        done = {}
        objidx = 0
        virtual_edges = []
        self._gatherGraphForHarfbuzz(tables, obj_list, done, objidx, virtual_edges)
        # Gather all data in two passes: the absolute positions of all
        # subtable are needed before the actual data can be assembled.
        pos = 0
        for table in tables:
            table.pos = pos
            pos = pos + table.getDataLength()

        data = []
        for table in tables:
            tableData = table.getDataForHarfbuzz()
            data.append(tableData)

        if hasattr(hb, "repack_with_tag"):
            return hb.repack_with_tag(str(tableTag), data, obj_list)
        else:
            return hb.repack(data, obj_list)

    def getAllData(self, remove_duplicate=True):
        """Assemble all data, including all subtables."""
        if remove_duplicate:
            internedTables = {}
            self._doneWriting(internedTables)
        tables = []
        extTables = []
        done = {}
        self._gatherTables(tables, extTables, done)
        tables.reverse()
        extTables.reverse()
        # Gather all data in two passes: the absolute positions of all
        # subtable are needed before the actual data can be assembled.
        pos = 0
        for table in tables:
            table.pos = pos
            pos = pos + table.getDataLength()

        for table in extTables:
            table.pos = pos
            pos = pos + table.getDataLength()

        data = []
        for table in tables:
            tableData = table.getData()
            data.append(tableData)

        for table in extTables:
            tableData = table.getData()
            data.append(tableData)

        return bytesjoin(data)

    # interface for gathering data, as used by table.compile()

    def getSubWriter(self):
        subwriter = self.__class__(self.localState, self.tableTag)
        subwriter.parent = (
            self  # because some subtables have idential values, we discard
        )
        # the duplicates under the getAllData method. Hence some
        # subtable writers can have more than one parent writer.
        # But we just care about first one right now.
        return subwriter

    def writeValue(self, typecode, value):
        self.items.append(struct.pack(f">{typecode}", value))

    def writeArray(self, typecode, values):
        a = array.array(typecode, values)
        if sys.byteorder != "big":
            a.byteswap()
        self.items.append(a.tobytes())

    def writeInt8(self, value):
        assert -128 <= value < 128, value
        self.items.append(struct.pack(">b", value))

    def writeInt8Array(self, values):
        self.writeArray("b", values)

    def writeShort(self, value):
        assert -32768 <= value < 32768, value
        self.items.append(struct.pack(">h", value))

    def writeShortArray(self, values):
        self.writeArray("h", values)

    def writeLong(self, value):
        self.items.append(struct.pack(">i", value))

    def writeLongArray(self, values):
        self.writeArray("i", values)

    def writeUInt8(self, value):
        assert 0 <= value < 256, value
        self.items.append(struct.pack(">B", value))

    def writeUInt8Array(self, values):
        self.writeArray("B", values)

    def writeUShort(self, value):
        assert 0 <= value < 0x10000, value
        self.items.append(struct.pack(">H", value))

    def writeUShortArray(self, values):
        self.writeArray("H", values)

    def writeULong(self, value):
        self.items.append(struct.pack(">I", value))

    def writeULongArray(self, values):
        self.writeArray("I", values)

    def writeUInt24(self, value):
        assert 0 <= value < 0x1000000, value
        b = struct.pack(">L", value)
        self.items.append(b[1:])

    def writeUInt24Array(self, values):
        for value in values:
            self.writeUInt24(value)

    def writeTag(self, tag):
        tag = Tag(tag).tobytes()
        assert len(tag) == 4, tag
        self.items.append(tag)

    def writeSubTable(self, subWriter, offsetSize):
        self.items.append(OffsetToWriter(subWriter, offsetSize))

    def writeCountReference(self, table, name, size=2, value=None):
        ref = CountReference(table, name, size=size, value=value)
        self.items.append(ref)
        return ref

    def writeStruct(self, format, values):
        data = struct.pack(*(format,) + values)
        self.items.append(data)

    def writeData(self, data):
        self.items.append(data)

    def getOverflowErrorRecord(self, item):
        LookupListIndex = SubTableIndex = itemName = itemIndex = None
        if self.name == "LookupList":
            LookupListIndex = item.repeatIndex
        elif self.name == "Lookup":
            LookupListIndex = self.repeatIndex
            SubTableIndex = item.repeatIndex
        else:
            itemName = getattr(item, "name", "<none>")
            if hasattr(item, "repeatIndex"):
                itemIndex = item.repeatIndex
            if self.name == "SubTable":
                LookupListIndex = self.parent.repeatIndex
                SubTableIndex = self.repeatIndex
            elif self.name == "ExtSubTable":
                LookupListIndex = self.parent.parent.repeatIndex
                SubTableIndex = self.parent.repeatIndex
            else:  # who knows how far below the SubTable level we are! Climb back up to the nearest subtable.
                itemName = ".".join([self.name, itemName])
                p1 = self.parent
                while p1 and p1.name not in ["ExtSubTable", "SubTable"]:
                    itemName = ".".join([p1.name, itemName])
                    p1 = p1.parent
                if p1:
                    if p1.name == "ExtSubTable":
                        LookupListIndex = p1.parent.parent.repeatIndex
                        SubTableIndex = p1.parent.repeatIndex
                    else:
                        LookupListIndex = p1.parent.repeatIndex
                        SubTableIndex = p1.repeatIndex

        return OverflowErrorRecord(
            (self.tableTag, LookupListIndex, SubTableIndex, itemName, itemIndex)
        )


class CountReference(object):
    """A reference to a Count value, not a count of references."""

    def __init__(self, table, name, size=None, value=None):
        self.table = table
        self.name = name
        self.size = size
        if value is not None:
            self.setValue(value)

    def setValue(self, value):
        table = self.table
        name = self.name
        if table[name] is None:
            table[name] = value
        else:
            assert table[name] == value, (name, table[name], value)

    def getValue(self):
        return self.table[self.name]

    def getCountData(self):
        v = self.table[self.name]
        if v is None:
            v = 0
        return {1: packUInt8, 2: packUShort, 4: packULong}[self.size](v)


def packUInt8(value):
    return struct.pack(">B", value)


def packUShort(value):
    return struct.pack(">H", value)


def packULong(value):
    assert 0 <= value < 0x100000000, value
    return struct.pack(">I", value)


def packUInt24(value):
    assert 0 <= value < 0x1000000, value
    return struct.pack(">I", value)[1:]


class BaseTable(object):
    """Generic base class for all OpenType (sub)tables."""

    def __getattr__(self, attr):
        reader = self.__dict__.get("reader")
        if reader:
            del self.reader
            font = self.font
            del self.font
            self.decompile(reader, font)
            return getattr(self, attr)

        raise AttributeError(attr)

    def ensureDecompiled(self, recurse=False):
        reader = self.__dict__.get("reader")
        if reader:
            del self.reader
            font = self.font
            del self.font
            self.decompile(reader, font)
        if recurse:
            for subtable in self.iterSubTables():
                subtable.value.ensureDecompiled(recurse)

    def __getstate__(self):
        # before copying/pickling 'lazy' objects, make a shallow copy of OTTableReader
        # https://github.com/fonttools/fonttools/issues/2965
        if "reader" in self.__dict__:
            state = self.__dict__.copy()
            state["reader"] = self.__dict__["reader"].copy()
            return state
        return self.__dict__

    @classmethod
    def getRecordSize(cls, reader):
        totalSize = 0
        for conv in cls.converters:
            size = conv.getRecordSize(reader)
            if size is NotImplemented:
                return NotImplemented
            countValue = 1
            if conv.repeat:
                if conv.repeat in reader:
                    countValue = reader[conv.repeat] + conv.aux
                else:
                    return NotImplemented
            totalSize += size * countValue
        return totalSize

    def getConverters(self):
        return self.converters

    def getConverterByName(self, name):
        return self.convertersByName[name]

    def populateDefaults(self, propagator=None):
        for conv in self.getConverters():
            if conv.repeat:
                if not hasattr(self, conv.name):
                    setattr(self, conv.name, [])
                countValue = len(getattr(self, conv.name)) - conv.aux
                try:
                    count_conv = self.getConverterByName(conv.repeat)
                    setattr(self, conv.repeat, countValue)
                except KeyError:
                    # conv.repeat is a propagated count
                    if propagator and conv.repeat in propagator:
                        propagator[conv.repeat].setValue(countValue)
            else:
                if conv.aux and not eval(conv.aux, None, self.__dict__):
                    continue
                if hasattr(self, conv.name):
                    continue  # Warn if it should NOT be present?!
                if hasattr(conv, "writeNullOffset"):
                    setattr(self, conv.name, None)  # Warn?
                # elif not conv.isCount:
                # 	# Warn?
                # 	pass
                if hasattr(conv, "DEFAULT"):
                    # OptionalValue converters (e.g. VarIndex)
                    setattr(self, conv.name, conv.DEFAULT)

    def decompile(self, reader, font):
        self.readFormat(reader)
        table = {}
        self.__rawTable = table  # for debugging
        for conv in self.getConverters():
            if conv.name == "SubTable":
                conv = conv.getConverter(reader.tableTag, table["LookupType"])
            if conv.name == "ExtSubTable":
                conv = conv.getConverter(reader.tableTag, table["ExtensionLookupType"])
            if conv.name == "FeatureParams":
                conv = conv.getConverter(reader["FeatureTag"])
            if conv.name == "SubStruct":
                conv = conv.getConverter(reader.tableTag, table["MorphType"])
            try:
                if conv.repeat:
                    if isinstance(conv.repeat, int):
                        countValue = conv.repeat
                    elif conv.repeat in table:
                        countValue = table[conv.repeat]
                    else:
                        # conv.repeat is a propagated count
                        countValue = reader[conv.repeat]
                    countValue += conv.aux
                    table[conv.name] = conv.readArray(reader, font, table, countValue)
                else:
                    if conv.aux and not eval(conv.aux, None, table):
                        continue
                    table[conv.name] = conv.read(reader, font, table)
                    if conv.isPropagated:
                        reader[conv.name] = table[conv.name]
            except Exception as e:
                name = conv.name
                e.args = e.args + (name,)
                raise

        if hasattr(self, "postRead"):
            self.postRead(table, font)
        else:
            self.__dict__.update(table)

        del self.__rawTable  # succeeded, get rid of debugging info

    def compile(self, writer, font):
        self.ensureDecompiled()
        # TODO Following hack to be removed by rewriting how FormatSwitching tables
        # are handled.
        # https://github.com/fonttools/fonttools/pull/2238#issuecomment-805192631
        if hasattr(self, "preWrite"):
            deleteFormat = not hasattr(self, "Format")
            table = self.preWrite(font)
            deleteFormat = deleteFormat and hasattr(self, "Format")
        else:
            deleteFormat = False
            table = self.__dict__.copy()

        # some count references may have been initialized in a custom preWrite; we set
        # these in the writer's state beforehand (instead of sequentially) so they will
        # be propagated to all nested subtables even if the count appears in the current
        # table only *after* the offset to the subtable that it is counting.
        for conv in self.getConverters():
            if conv.isCount and conv.isPropagated:
                value = table.get(conv.name)
                if isinstance(value, CountReference):
                    writer[conv.name] = value

        if hasattr(self, "sortCoverageLast"):
            writer.sortCoverageLast = 1

        if hasattr(self, "DontShare"):
            writer.DontShare = True

        if hasattr(self.__class__, "LookupType"):
            writer["LookupType"].setValue(self.__class__.LookupType)

        self.writeFormat(writer)
        for conv in self.getConverters():
            value = table.get(
                conv.name
            )  # TODO Handle defaults instead of defaulting to None!
            if conv.repeat:
                if value is None:
                    value = []
                countValue = len(value) - conv.aux
                if isinstance(conv.repeat, int):
                    assert len(value) == conv.repeat, "expected %d values, got %d" % (
                        conv.repeat,
                        len(value),
                    )
                elif conv.repeat in table:
                    CountReference(table, conv.repeat, value=countValue)
                else:
                    # conv.repeat is a propagated count
                    writer[conv.repeat].setValue(countValue)
                try:
                    conv.writeArray(writer, font, table, value)
                except Exception as e:
                    e.args = e.args + (conv.name + "[]",)
                    raise
            elif conv.isCount:
                # Special-case Count values.
                # Assumption: a Count field will *always* precede
                # the actual array(s).
                # We need a default value, as it may be set later by a nested
                # table. We will later store it here.
                # We add a reference: by the time the data is assembled
                # the Count value will be filled in.
                # We ignore the current count value since it will be recomputed,
                # unless it's a CountReference that was already initialized in a custom preWrite.
                if isinstance(value, CountReference):
                    ref = value
                    ref.size = conv.staticSize
                    writer.writeData(ref)
                    table[conv.name] = ref.getValue()
                else:
                    ref = writer.writeCountReference(table, conv.name, conv.staticSize)
                    table[conv.name] = None
                if conv.isPropagated:
                    writer[conv.name] = ref
            elif conv.isLookupType:
                # We make sure that subtables have the same lookup type,
                # and that the type is the same as the one set on the
                # Lookup object, if any is set.
                if conv.name not in table:
                    table[conv.name] = None
                ref = writer.writeCountReference(
                    table, conv.name, conv.staticSize, table[conv.name]
                )
                writer["LookupType"] = ref
            else:
                if conv.aux and not eval(conv.aux, None, table):
                    continue
                try:
                    conv.write(writer, font, table, value)
                except Exception as e:
                    name = value.__class__.__name__ if value is not None else conv.name
                    e.args = e.args + (name,)
                    raise
                if conv.isPropagated:
                    writer[conv.name] = value

        if deleteFormat:
            del self.Format

    def readFormat(self, reader):
        pass

    def writeFormat(self, writer):
        pass

    def toXML(self, xmlWriter, font, attrs=None, name=None):
        tableName = name if name else self.__class__.__name__
        if attrs is None:
            attrs = []
        if hasattr(self, "Format"):
            attrs = attrs + [("Format", self.Format)]
        xmlWriter.begintag(tableName, attrs)
        xmlWriter.newline()
        self.toXML2(xmlWriter, font)
        xmlWriter.endtag(tableName)
        xmlWriter.newline()

    def toXML2(self, xmlWriter, font):
        # Simpler variant of toXML, *only* for the top level tables (like GPOS, GSUB).
        # This is because in TTX our parent writes our main tag, and in otBase.py we
        # do it ourselves. I think I'm getting schizophrenic...
        for conv in self.getConverters():
            if conv.repeat:
                value = getattr(self, conv.name, [])
                for i, item in enumerate(value):
                    conv.xmlWrite(xmlWriter, font, item, conv.name, [("index", i)])
            else:
                if conv.aux and not eval(conv.aux, None, vars(self)):
                    continue
                value = getattr(
                    self, conv.name, None
                )  # TODO Handle defaults instead of defaulting to None!
                conv.xmlWrite(xmlWriter, font, value, conv.name, [])

    def fromXML(self, name, attrs, content, font):
        try:
            conv = self.getConverterByName(name)
        except KeyError:
            raise  # XXX on KeyError, raise nice error
        value = conv.xmlRead(attrs, content, font)
        # Some manually-written tables have a conv.repeat of ""
        # to represent lists. Hence comparing to None here to
        # allow those lists to be read correctly from XML.
        if conv.repeat is not None:
            seq = getattr(self, conv.name, None)
            if seq is None:
                seq = []
                setattr(self, conv.name, seq)
            seq.append(value)
        else:
            setattr(self, conv.name, value)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented

        self.ensureDecompiled()
        other.ensureDecompiled()

        return self.__dict__ == other.__dict__

    class SubTableEntry(NamedTuple):
        """See BaseTable.iterSubTables()"""

        name: str
        value: "BaseTable"
        index: Optional[int] = None  # index into given array, None for single values

    def iterSubTables(self) -> Iterator[SubTableEntry]:
        """Yield (name, value, index) namedtuples for all subtables of current table.

        A sub-table is an instance of BaseTable (or subclass thereof) that is a child
        of self, the current parent table.
        The tuples also contain the attribute name (str) of the of parent table to get
        a subtable, and optionally, for lists of subtables (i.e. attributes associated
        with a converter that has a 'repeat'), an index into the list containing the
        given subtable value.
        This method can be useful to traverse trees of otTables.
        """
        for conv in self.getConverters():
            name = conv.name
            value = getattr(self, name, None)
            if value is None:
                continue
            if isinstance(value, BaseTable):
                yield self.SubTableEntry(name, value)
            elif isinstance(value, list):
                yield from (
                    self.SubTableEntry(name, v, index=i)
                    for i, v in enumerate(value)
                    if isinstance(v, BaseTable)
                )

    # instance (not @class)method for consistency with FormatSwitchingBaseTable
    def getVariableAttrs(self):
        return getVariableAttrs(self.__class__)


class FormatSwitchingBaseTable(BaseTable):
    """Minor specialization of BaseTable, for tables that have multiple
    formats, eg. CoverageFormat1 vs. CoverageFormat2."""

    @classmethod
    def getRecordSize(cls, reader):
        return NotImplemented

    def getConverters(self):
        try:
            fmt = self.Format
        except AttributeError:
            # some FormatSwitchingBaseTables (e.g. Coverage) no longer have 'Format'
            # attribute after fully decompiled, only gain one in preWrite before being
            # recompiled. In the decompiled state, these hand-coded classes defined in
            # otTables.py lose their format-specific nature and gain more high-level
            # attributes that are not tied to converters.
            return []
        return self.converters.get(self.Format, [])

    def getConverterByName(self, name):
        return self.convertersByName[self.Format][name]

    def readFormat(self, reader):
        self.Format = reader.readUShort()

    def writeFormat(self, writer):
        writer.writeUShort(self.Format)

    def toXML(self, xmlWriter, font, attrs=None, name=None):
        BaseTable.toXML(self, xmlWriter, font, attrs, name)

    def getVariableAttrs(self):
        return getVariableAttrs(self.__class__, self.Format)


class UInt8FormatSwitchingBaseTable(FormatSwitchingBaseTable):
    def readFormat(self, reader):
        self.Format = reader.readUInt8()

    def writeFormat(self, writer):
        writer.writeUInt8(self.Format)


formatSwitchingBaseTables = {
    "uint16": FormatSwitchingBaseTable,
    "uint8": UInt8FormatSwitchingBaseTable,
}


def getFormatSwitchingBaseTableClass(formatType):
    try:
        return formatSwitchingBaseTables[formatType]
    except KeyError:
        raise TypeError(f"Unsupported format type: {formatType!r}")


# memoize since these are parsed from otData.py, thus stay constant
@lru_cache()
def getVariableAttrs(cls: BaseTable, fmt: Optional[int] = None) -> Tuple[str]:
    """Return sequence of variable table field names (can be empty).

    Attributes are deemed "variable" when their otData.py's description contain
    'VarIndexBase + {offset}', e.g. COLRv1 PaintVar* tables.
    """
    if not issubclass(cls, BaseTable):
        raise TypeError(cls)
    if issubclass(cls, FormatSwitchingBaseTable):
        if fmt is None:
            raise TypeError(f"'fmt' is required for format-switching {cls.__name__}")
        converters = cls.convertersByName[fmt]
    else:
        converters = cls.convertersByName
    # assume if no 'VarIndexBase' field is present, table has no variable fields
    if "VarIndexBase" not in converters:
        return ()
    varAttrs = {}
    for name, conv in converters.items():
        offset = conv.getVarIndexOffset()
        if offset is not None:
            varAttrs[name] = offset
    return tuple(sorted(varAttrs, key=varAttrs.__getitem__))


#
# Support for ValueRecords
#
# This data type is so different from all other OpenType data types that
# it requires quite a bit of code for itself. It even has special support
# in OTTableReader and OTTableWriter...
#

valueRecordFormat = [
    # 	Mask	 Name		isDevice signed
    (0x0001, "XPlacement", 0, 1),
    (0x0002, "YPlacement", 0, 1),
    (0x0004, "XAdvance", 0, 1),
    (0x0008, "YAdvance", 0, 1),
    (0x0010, "XPlaDevice", 1, 0),
    (0x0020, "YPlaDevice", 1, 0),
    (0x0040, "XAdvDevice", 1, 0),
    (0x0080, "YAdvDevice", 1, 0),
    # 	reserved:
    (0x0100, "Reserved1", 0, 0),
    (0x0200, "Reserved2", 0, 0),
    (0x0400, "Reserved3", 0, 0),
    (0x0800, "Reserved4", 0, 0),
    (0x1000, "Reserved5", 0, 0),
    (0x2000, "Reserved6", 0, 0),
    (0x4000, "Reserved7", 0, 0),
    (0x8000, "Reserved8", 0, 0),
]


def _buildDict():
    d = {}
    for mask, name, isDevice, signed in valueRecordFormat:
        d[name] = mask, isDevice, signed
    return d


valueRecordFormatDict = _buildDict()


class ValueRecordFactory(object):
    """Given a format code, this object convert ValueRecords."""

    def __init__(self, valueFormat):
        format = []
        for mask, name, isDevice, signed in valueRecordFormat:
            if valueFormat & mask:
                format.append((name, isDevice, signed))
        self.format = format

    def __len__(self):
        return len(self.format)

    def readValueRecord(self, reader, font):
        format = self.format
        if not format:
            return None
        valueRecord = ValueRecord()
        for name, isDevice, signed in format:
            if signed:
                value = reader.readShort()
            else:
                value = reader.readUShort()
            if isDevice:
                if value:
                    from . import otTables

                    subReader = reader.getSubReader(value)
                    value = getattr(otTables, name)()
                    value.decompile(subReader, font)
                else:
                    value = None
            setattr(valueRecord, name, value)
        return valueRecord

    def writeValueRecord(self, writer, font, valueRecord):
        for name, isDevice, signed in self.format:
            value = getattr(valueRecord, name, 0)
            if isDevice:
                if value:
                    subWriter = writer.getSubWriter()
                    writer.writeSubTable(subWriter, offsetSize=2)
                    value.compile(subWriter, font)
                else:
                    writer.writeUShort(0)
            elif signed:
                writer.writeShort(value)
            else:
                writer.writeUShort(value)


class ValueRecord(object):
    # see ValueRecordFactory

    def __init__(self, valueFormat=None, src=None):
        if valueFormat is not None:
            for mask, name, isDevice, signed in valueRecordFormat:
                if valueFormat & mask:
                    setattr(self, name, None if isDevice else 0)
            if src is not None:
                for key, val in src.__dict__.items():
                    if not hasattr(self, key):
                        continue
                    setattr(self, key, val)
        elif src is not None:
            self.__dict__ = src.__dict__.copy()

    def getFormat(self):
        format = 0
        for name in self.__dict__.keys():
            format = format | valueRecordFormatDict[name][0]
        return format

    def getEffectiveFormat(self):
        format = 0
        for name, value in self.__dict__.items():
            if value:
                format = format | valueRecordFormatDict[name][0]
        return format

    def toXML(self, xmlWriter, font, valueName, attrs=None):
        if attrs is None:
            simpleItems = []
        else:
            simpleItems = list(attrs)
        for mask, name, isDevice, format in valueRecordFormat[:4]:  # "simple" values
            if hasattr(self, name):
                simpleItems.append((name, getattr(self, name)))
        deviceItems = []
        for mask, name, isDevice, format in valueRecordFormat[4:8]:  # device records
            if hasattr(self, name):
                device = getattr(self, name)
                if device is not None:
                    deviceItems.append((name, device))
        if deviceItems:
            xmlWriter.begintag(valueName, simpleItems)
            xmlWriter.newline()
            for name, deviceRecord in deviceItems:
                if deviceRecord is not None:
                    deviceRecord.toXML(xmlWriter, font, name=name)
            xmlWriter.endtag(valueName)
            xmlWriter.newline()
        else:
            xmlWriter.simpletag(valueName, simpleItems)
            xmlWriter.newline()

    def fromXML(self, name, attrs, content, font):
        from . import otTables

        for k, v in attrs.items():
            setattr(self, k, int(v))
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            value = getattr(otTables, name)()
            for elem2 in content:
                if not isinstance(elem2, tuple):
                    continue
                name2, attrs2, content2 = elem2
                value.fromXML(name2, attrs2, content2, font)
            setattr(self, name, value)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.__dict__ == other.__dict__
