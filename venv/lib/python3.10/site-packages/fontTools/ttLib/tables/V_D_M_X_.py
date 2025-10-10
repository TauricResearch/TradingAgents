from . import DefaultTable
from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
import struct

VDMX_HeaderFmt = """
	>                 # big endian
	version:     H    # Version number (0 or 1)
	numRecs:     H    # Number of VDMX groups present
	numRatios:   H    # Number of aspect ratio groupings
"""
# the VMDX header is followed by an array of RatRange[numRatios] (i.e. aspect
# ratio ranges);
VDMX_RatRangeFmt = """
	>                 # big endian
	bCharSet:    B    # Character set
	xRatio:      B    # Value to use for x-Ratio
	yStartRatio: B    # Starting y-Ratio value
	yEndRatio:   B    # Ending y-Ratio value
"""
# followed by an array of offset[numRatios] from start of VDMX table to the
# VDMX Group for this ratio range (offsets will be re-calculated on compile);
# followed by an array of Group[numRecs] records;
VDMX_GroupFmt = """
	>                 # big endian
	recs:        H    # Number of height records in this group
	startsz:     B    # Starting yPelHeight
	endsz:       B    # Ending yPelHeight
"""
# followed by an array of vTable[recs] records.
VDMX_vTableFmt = """
	>                 # big endian
	yPelHeight:  H    # yPelHeight to which values apply
	yMax:        h    # Maximum value (in pels) for this yPelHeight
	yMin:        h    # Minimum value (in pels) for this yPelHeight
"""


class table_V_D_M_X_(DefaultTable.DefaultTable):
    """Vertical Device Metrics table

    The ``VDMX`` table records changes to the vertical glyph minima
    and maxima that result from Truetype instructions.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/vdmx
    """

    def decompile(self, data, ttFont):
        pos = 0  # track current position from to start of VDMX table
        dummy, data = sstruct.unpack2(VDMX_HeaderFmt, data, self)
        pos += sstruct.calcsize(VDMX_HeaderFmt)
        self.ratRanges = []
        for i in range(self.numRatios):
            ratio, data = sstruct.unpack2(VDMX_RatRangeFmt, data)
            pos += sstruct.calcsize(VDMX_RatRangeFmt)
            # the mapping between a ratio and a group is defined further below
            ratio["groupIndex"] = None
            self.ratRanges.append(ratio)
        lenOffset = struct.calcsize(">H")
        _offsets = []  # temporarily store offsets to groups
        for i in range(self.numRatios):
            offset = struct.unpack(">H", data[0:lenOffset])[0]
            data = data[lenOffset:]
            pos += lenOffset
            _offsets.append(offset)
        self.groups = []
        for groupIndex in range(self.numRecs):
            # the offset to this group from beginning of the VDMX table
            currOffset = pos
            group, data = sstruct.unpack2(VDMX_GroupFmt, data)
            # the group lenght and bounding sizes are re-calculated on compile
            recs = group.pop("recs")
            startsz = group.pop("startsz")
            endsz = group.pop("endsz")
            pos += sstruct.calcsize(VDMX_GroupFmt)
            for j in range(recs):
                vTable, data = sstruct.unpack2(VDMX_vTableFmt, data)
                vTableLength = sstruct.calcsize(VDMX_vTableFmt)
                pos += vTableLength
                # group is a dict of (yMax, yMin) tuples keyed by yPelHeight
                group[vTable["yPelHeight"]] = (vTable["yMax"], vTable["yMin"])
            # make sure startsz and endsz match the calculated values
            minSize = min(group.keys())
            maxSize = max(group.keys())
            assert (
                startsz == minSize
            ), "startsz (%s) must equal min yPelHeight (%s): group %d" % (
                group.startsz,
                minSize,
                groupIndex,
            )
            assert (
                endsz == maxSize
            ), "endsz (%s) must equal max yPelHeight (%s): group %d" % (
                group.endsz,
                maxSize,
                groupIndex,
            )
            self.groups.append(group)
            # match the defined offsets with the current group's offset
            for offsetIndex, offsetValue in enumerate(_offsets):
                # when numRecs < numRatios there can more than one ratio range
                # sharing the same VDMX group
                if currOffset == offsetValue:
                    # map the group with the ratio range thas has the same
                    # index as the offset to that group (it took me a while..)
                    self.ratRanges[offsetIndex]["groupIndex"] = groupIndex
        # check that all ratio ranges have a group
        for i in range(self.numRatios):
            ratio = self.ratRanges[i]
            if ratio["groupIndex"] is None:
                from fontTools import ttLib

                raise ttLib.TTLibError("no group defined for ratRange %d" % i)

    def _getOffsets(self):
        """
        Calculate offsets to VDMX_Group records.
        For each ratRange return a list of offset values from the beginning of
        the VDMX table to a VDMX_Group.
        """
        lenHeader = sstruct.calcsize(VDMX_HeaderFmt)
        lenRatRange = sstruct.calcsize(VDMX_RatRangeFmt)
        lenOffset = struct.calcsize(">H")
        lenGroupHeader = sstruct.calcsize(VDMX_GroupFmt)
        lenVTable = sstruct.calcsize(VDMX_vTableFmt)
        # offset to the first group
        pos = lenHeader + self.numRatios * lenRatRange + self.numRatios * lenOffset
        groupOffsets = []
        for group in self.groups:
            groupOffsets.append(pos)
            lenGroup = lenGroupHeader + len(group) * lenVTable
            pos += lenGroup  # offset to next group
        offsets = []
        for ratio in self.ratRanges:
            groupIndex = ratio["groupIndex"]
            offsets.append(groupOffsets[groupIndex])
        return offsets

    def compile(self, ttFont):
        if not (self.version == 0 or self.version == 1):
            from fontTools import ttLib

            raise ttLib.TTLibError(
                "unknown format for VDMX table: version %s" % self.version
            )
        data = sstruct.pack(VDMX_HeaderFmt, self)
        for ratio in self.ratRanges:
            data += sstruct.pack(VDMX_RatRangeFmt, ratio)
        # recalculate offsets to VDMX groups
        for offset in self._getOffsets():
            data += struct.pack(">H", offset)
        for group in self.groups:
            recs = len(group)
            startsz = min(group.keys())
            endsz = max(group.keys())
            gHeader = {"recs": recs, "startsz": startsz, "endsz": endsz}
            data += sstruct.pack(VDMX_GroupFmt, gHeader)
            for yPelHeight, (yMax, yMin) in sorted(group.items()):
                vTable = {"yPelHeight": yPelHeight, "yMax": yMax, "yMin": yMin}
                data += sstruct.pack(VDMX_vTableFmt, vTable)
        return data

    def toXML(self, writer, ttFont):
        writer.simpletag("version", value=self.version)
        writer.newline()
        writer.begintag("ratRanges")
        writer.newline()
        for ratio in self.ratRanges:
            groupIndex = ratio["groupIndex"]
            writer.simpletag(
                "ratRange",
                bCharSet=ratio["bCharSet"],
                xRatio=ratio["xRatio"],
                yStartRatio=ratio["yStartRatio"],
                yEndRatio=ratio["yEndRatio"],
                groupIndex=groupIndex,
            )
            writer.newline()
        writer.endtag("ratRanges")
        writer.newline()
        writer.begintag("groups")
        writer.newline()
        for groupIndex in range(self.numRecs):
            group = self.groups[groupIndex]
            recs = len(group)
            startsz = min(group.keys())
            endsz = max(group.keys())
            writer.begintag("group", index=groupIndex)
            writer.newline()
            writer.comment("recs=%d, startsz=%d, endsz=%d" % (recs, startsz, endsz))
            writer.newline()
            for yPelHeight, (yMax, yMin) in sorted(group.items()):
                writer.simpletag(
                    "record",
                    [("yPelHeight", yPelHeight), ("yMax", yMax), ("yMin", yMin)],
                )
                writer.newline()
            writer.endtag("group")
            writer.newline()
        writer.endtag("groups")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = safeEval(attrs["value"])
        elif name == "ratRanges":
            if not hasattr(self, "ratRanges"):
                self.ratRanges = []
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content = element
                if name == "ratRange":
                    if not hasattr(self, "numRatios"):
                        self.numRatios = 1
                    else:
                        self.numRatios += 1
                    ratio = {
                        "bCharSet": safeEval(attrs["bCharSet"]),
                        "xRatio": safeEval(attrs["xRatio"]),
                        "yStartRatio": safeEval(attrs["yStartRatio"]),
                        "yEndRatio": safeEval(attrs["yEndRatio"]),
                        "groupIndex": safeEval(attrs["groupIndex"]),
                    }
                    self.ratRanges.append(ratio)
        elif name == "groups":
            if not hasattr(self, "groups"):
                self.groups = []
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content = element
                if name == "group":
                    if not hasattr(self, "numRecs"):
                        self.numRecs = 1
                    else:
                        self.numRecs += 1
                    group = {}
                    for element in content:
                        if not isinstance(element, tuple):
                            continue
                        name, attrs, content = element
                        if name == "record":
                            yPelHeight = safeEval(attrs["yPelHeight"])
                            yMax = safeEval(attrs["yMax"])
                            yMin = safeEval(attrs["yMin"])
                            group[yPelHeight] = (yMax, yMin)
                    self.groups.append(group)
