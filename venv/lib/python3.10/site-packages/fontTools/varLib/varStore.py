from fontTools.misc.roundTools import noRound, otRound
from fontTools.misc.intTools import bit_count
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.models import supportScalar
from fontTools.varLib.builder import (
    buildVarRegionList,
    buildVarStore,
    buildVarRegion,
    buildVarData,
)
from functools import partial
from collections import defaultdict
from heapq import heappush, heappop


NO_VARIATION_INDEX = ot.NO_VARIATION_INDEX
ot.VarStore.NO_VARIATION_INDEX = NO_VARIATION_INDEX


def _getLocationKey(loc):
    return tuple(sorted(loc.items(), key=lambda kv: kv[0]))


class OnlineVarStoreBuilder(object):
    def __init__(self, axisTags):
        self._axisTags = axisTags
        self._regionMap = {}
        self._regionList = buildVarRegionList([], axisTags)
        self._store = buildVarStore(self._regionList, [])
        self._data = None
        self._model = None
        self._supports = None
        self._varDataIndices = {}
        self._varDataCaches = {}
        self._cache = None

    def setModel(self, model):
        self.setSupports(model.supports)
        self._model = model

    def setSupports(self, supports):
        self._model = None
        self._supports = list(supports)
        if self._supports and not self._supports[0]:
            del self._supports[0]  # Drop base master support
        self._cache = None
        self._data = None

    def finish(self, optimize=True):
        self._regionList.RegionCount = len(self._regionList.Region)
        self._store.VarDataCount = len(self._store.VarData)
        for data in self._store.VarData:
            data.ItemCount = len(data.Item)
            data.calculateNumShorts(optimize=optimize)
        return self._store

    def _add_VarData(self, num_items=1):
        regionMap = self._regionMap
        regionList = self._regionList

        regions = self._supports
        regionIndices = []
        for region in regions:
            key = _getLocationKey(region)
            idx = regionMap.get(key)
            if idx is None:
                varRegion = buildVarRegion(region, self._axisTags)
                idx = regionMap[key] = len(regionList.Region)
                regionList.Region.append(varRegion)
            regionIndices.append(idx)

        # Check if we have one already...
        key = tuple(regionIndices)
        varDataIdx = self._varDataIndices.get(key)
        if varDataIdx is not None:
            self._outer = varDataIdx
            self._data = self._store.VarData[varDataIdx]
            self._cache = self._varDataCaches[key]
            if len(self._data.Item) + num_items > 0xFFFF:
                # This is full.  Need new one.
                varDataIdx = None

        if varDataIdx is None:
            self._data = buildVarData(regionIndices, [], optimize=False)
            self._outer = len(self._store.VarData)
            self._store.VarData.append(self._data)
            self._varDataIndices[key] = self._outer
            if key not in self._varDataCaches:
                self._varDataCaches[key] = {}
            self._cache = self._varDataCaches[key]

    def storeMasters(self, master_values, *, round=round):
        deltas = self._model.getDeltas(master_values, round=round)
        base = deltas.pop(0)
        return base, self.storeDeltas(deltas, round=noRound)

    def storeMastersMany(self, master_values_list, *, round=round):
        deltas_list = [
            self._model.getDeltas(master_values, round=round)
            for master_values in master_values_list
        ]
        base_list = [deltas.pop(0) for deltas in deltas_list]
        return base_list, self.storeDeltasMany(deltas_list, round=noRound)

    def storeDeltas(self, deltas, *, round=round):
        deltas = [round(d) for d in deltas]
        if len(deltas) == len(self._supports) + 1:
            deltas = tuple(deltas[1:])
        else:
            assert len(deltas) == len(self._supports)
            deltas = tuple(deltas)

        if not self._data:
            self._add_VarData()

        varIdx = self._cache.get(deltas)
        if varIdx is not None:
            return varIdx

        inner = len(self._data.Item)
        if inner == 0xFFFF:
            # Full array. Start new one.
            self._add_VarData()
            return self.storeDeltas(deltas, round=noRound)
        self._data.addItem(deltas, round=noRound)

        varIdx = (self._outer << 16) + inner
        self._cache[deltas] = varIdx
        return varIdx

    def storeDeltasMany(self, deltas_list, *, round=round):
        deltas_list = [[round(d) for d in deltas] for deltas in deltas_list]
        deltas_list = tuple(tuple(deltas) for deltas in deltas_list)

        if not self._data:
            self._add_VarData(len(deltas_list))

        varIdx = self._cache.get(deltas_list)
        if varIdx is not None:
            return varIdx

        inner = len(self._data.Item)
        if inner + len(deltas_list) > 0xFFFF:
            # Full array. Start new one.
            self._add_VarData(len(deltas_list))
            return self.storeDeltasMany(deltas_list, round=noRound)
        for i, deltas in enumerate(deltas_list):
            self._data.addItem(deltas, round=noRound)

            varIdx = (self._outer << 16) + inner + i
            self._cache[deltas] = varIdx

        varIdx = (self._outer << 16) + inner
        self._cache[deltas_list] = varIdx

        return varIdx


def VarData_addItem(self, deltas, *, round=round):
    deltas = [round(d) for d in deltas]

    countUs = self.VarRegionCount
    countThem = len(deltas)
    if countUs + 1 == countThem:
        deltas = list(deltas[1:])
    else:
        assert countUs == countThem, (countUs, countThem)
        deltas = list(deltas)
    self.Item.append(deltas)
    self.ItemCount = len(self.Item)


ot.VarData.addItem = VarData_addItem


def VarRegion_get_support(self, fvar_axes):
    return {
        fvar_axes[i].axisTag: (reg.StartCoord, reg.PeakCoord, reg.EndCoord)
        for i, reg in enumerate(self.VarRegionAxis)
        if reg.PeakCoord != 0
    }


ot.VarRegion.get_support = VarRegion_get_support


def VarStore___bool__(self):
    return bool(self.VarData)


ot.VarStore.__bool__ = VarStore___bool__


class VarStoreInstancer(object):
    def __init__(self, varstore, fvar_axes, location={}):
        self.fvar_axes = fvar_axes
        assert varstore is None or varstore.Format == 1
        self._varData = varstore.VarData if varstore else []
        self._regions = varstore.VarRegionList.Region if varstore else []
        self.setLocation(location)

    def setLocation(self, location):
        self.location = dict(location)
        self._clearCaches()

    def _clearCaches(self):
        self._scalars = {}

    def _getScalar(self, regionIdx):
        scalar = self._scalars.get(regionIdx)
        if scalar is None:
            support = self._regions[regionIdx].get_support(self.fvar_axes)
            scalar = supportScalar(self.location, support)
            self._scalars[regionIdx] = scalar
        return scalar

    @staticmethod
    def interpolateFromDeltasAndScalars(deltas, scalars):
        delta = 0.0
        for d, s in zip(deltas, scalars):
            if not s:
                continue
            delta += d * s
        return delta

    def __getitem__(self, varidx):
        major, minor = varidx >> 16, varidx & 0xFFFF
        if varidx == NO_VARIATION_INDEX:
            return 0.0
        varData = self._varData
        scalars = [self._getScalar(ri) for ri in varData[major].VarRegionIndex]
        deltas = varData[major].Item[minor]
        return self.interpolateFromDeltasAndScalars(deltas, scalars)

    def interpolateFromDeltas(self, varDataIndex, deltas):
        varData = self._varData
        scalars = [self._getScalar(ri) for ri in varData[varDataIndex].VarRegionIndex]
        return self.interpolateFromDeltasAndScalars(deltas, scalars)


#
# Optimizations
#
# retainFirstMap - If true, major 0 mappings are retained. Deltas for unused indices are zeroed
# advIdxes - Set of major 0 indices for advance deltas to be listed first. Other major 0 indices follow.


def VarStore_subset_varidxes(
    self,
    varIdxes,
    optimize=True,
    retainFirstMap=False,
    advIdxes=set(),
    *,
    VarData="VarData",
):
    # Sort out used varIdxes by major/minor.
    used = defaultdict(set)
    for varIdx in varIdxes:
        if varIdx == NO_VARIATION_INDEX:
            continue
        major = varIdx >> 16
        minor = varIdx & 0xFFFF
        used[major].add(minor)
    del varIdxes

    #
    # Subset VarData
    #

    varData = getattr(self, VarData)
    newVarData = []
    varDataMap = {NO_VARIATION_INDEX: NO_VARIATION_INDEX}
    for major, data in enumerate(varData):
        usedMinors = used.get(major)
        if usedMinors is None:
            continue
        newMajor = len(newVarData)
        newVarData.append(data)

        items = data.Item
        newItems = []
        if major == 0 and retainFirstMap:
            for minor in range(len(items)):
                newItems.append(
                    items[minor] if minor in usedMinors else [0] * len(items[minor])
                )
                varDataMap[minor] = minor
        else:
            if major == 0:
                minors = sorted(advIdxes) + sorted(usedMinors - advIdxes)
            else:
                minors = sorted(usedMinors)
            for minor in minors:
                newMinor = len(newItems)
                newItems.append(items[minor])
                varDataMap[(major << 16) + minor] = (newMajor << 16) + newMinor

        data.Item = newItems
        data.ItemCount = len(data.Item)

        if VarData == "VarData":
            data.calculateNumShorts(optimize=optimize)

    setattr(self, VarData, newVarData)
    setattr(self, VarData + "Count", len(newVarData))

    self.prune_regions()

    return varDataMap


ot.VarStore.subset_varidxes = VarStore_subset_varidxes


def VarStore_prune_regions(self, *, VarData="VarData", VarRegionList="VarRegionList"):
    """Remove unused VarRegions."""
    #
    # Subset VarRegionList
    #

    # Collect.
    usedRegions = set()
    for data in getattr(self, VarData):
        usedRegions.update(data.VarRegionIndex)
    # Subset.
    regionList = getattr(self, VarRegionList)
    regions = regionList.Region
    newRegions = []
    regionMap = {}
    for i in sorted(usedRegions):
        regionMap[i] = len(newRegions)
        newRegions.append(regions[i])
    regionList.Region = newRegions
    regionList.RegionCount = len(regionList.Region)
    # Map.
    for data in getattr(self, VarData):
        data.VarRegionIndex = [regionMap[i] for i in data.VarRegionIndex]


ot.VarStore.prune_regions = VarStore_prune_regions


def _visit(self, func):
    """Recurse down from self, if type of an object is ot.Device,
    call func() on it.  Works on otData-style classes."""

    if type(self) == ot.Device:
        func(self)

    elif isinstance(self, list):
        for that in self:
            _visit(that, func)

    elif hasattr(self, "getConverters") and not hasattr(self, "postRead"):
        for conv in self.getConverters():
            that = getattr(self, conv.name, None)
            if that is not None:
                _visit(that, func)

    elif isinstance(self, ot.ValueRecord):
        for that in self.__dict__.values():
            _visit(that, func)


def _Device_recordVarIdx(self, s):
    """Add VarIdx in this Device table (if any) to the set s."""
    if self.DeltaFormat == 0x8000:
        s.add((self.StartSize << 16) + self.EndSize)


def Object_collect_device_varidxes(self, varidxes):
    adder = partial(_Device_recordVarIdx, s=varidxes)
    _visit(self, adder)


ot.GDEF.collect_device_varidxes = Object_collect_device_varidxes
ot.GPOS.collect_device_varidxes = Object_collect_device_varidxes


def _Device_mapVarIdx(self, mapping, done):
    """Map VarIdx in this Device table (if any) through mapping."""
    if id(self) in done:
        return
    done.add(id(self))
    if self.DeltaFormat == 0x8000:
        varIdx = mapping[(self.StartSize << 16) + self.EndSize]
        self.StartSize = varIdx >> 16
        self.EndSize = varIdx & 0xFFFF


def Object_remap_device_varidxes(self, varidxes_map):
    mapper = partial(_Device_mapVarIdx, mapping=varidxes_map, done=set())
    _visit(self, mapper)


ot.GDEF.remap_device_varidxes = Object_remap_device_varidxes
ot.GPOS.remap_device_varidxes = Object_remap_device_varidxes


class _Encoding(object):
    def __init__(self, chars):
        self.chars = chars
        self.width = bit_count(chars)
        self.columns = self._columns(chars)
        self.overhead = self._characteristic_overhead(self.columns)
        self.items = set()

    def append(self, row):
        self.items.add(row)

    def extend(self, lst):
        self.items.update(lst)

    def width_sort_key(self):
        return self.width, self.chars

    @staticmethod
    def _characteristic_overhead(columns):
        """Returns overhead in bytes of encoding this characteristic
        as a VarData."""
        c = 4 + 6  # 4 bytes for LOffset, 6 bytes for VarData header
        c += bit_count(columns) * 2
        return c

    @staticmethod
    def _columns(chars):
        cols = 0
        i = 1
        while chars:
            if chars & 0b1111:
                cols |= i
            chars >>= 4
            i <<= 1
        return cols

    def gain_from_merging(self, other_encoding):
        combined_chars = other_encoding.chars | self.chars
        combined_width = bit_count(combined_chars)
        combined_columns = self.columns | other_encoding.columns
        combined_overhead = _Encoding._characteristic_overhead(combined_columns)
        combined_gain = (
            +self.overhead
            + other_encoding.overhead
            - combined_overhead
            - (combined_width - self.width) * len(self.items)
            - (combined_width - other_encoding.width) * len(other_encoding.items)
        )
        return combined_gain


class _EncodingDict(dict):
    def __missing__(self, chars):
        r = self[chars] = _Encoding(chars)
        return r

    def add_row(self, row):
        chars = self._row_characteristics(row)
        self[chars].append(row)

    @staticmethod
    def _row_characteristics(row):
        """Returns encoding characteristics for a row."""
        longWords = False

        chars = 0
        i = 1
        for v in row:
            if v:
                chars += i
            if not (-128 <= v <= 127):
                chars += i * 0b0010
            if not (-32768 <= v <= 32767):
                longWords = True
                break
            i <<= 4

        if longWords:
            # Redo; only allow 2byte/4byte encoding
            chars = 0
            i = 1
            for v in row:
                if v:
                    chars += i * 0b0011
                if not (-32768 <= v <= 32767):
                    chars += i * 0b1100
                i <<= 4

        return chars


def VarStore_optimize(self, use_NO_VARIATION_INDEX=True, quantization=1):
    """Optimize storage. Returns mapping from old VarIdxes to new ones."""

    # Overview:
    #
    # For each VarData row, we first extend it with zeroes to have
    # one column per region in VarRegionList. We then group the
    # rows into _Encoding objects, by their "characteristic" bitmap.
    # The characteristic bitmap is a binary number representing how
    # many bytes each column of the data takes up to encode. Each
    # column is encoded in four bits. For example, if a column has
    # only values in the range -128..127, it would only have a single
    # bit set in the characteristic bitmap for that column. If it has
    # values in the range -32768..32767, it would have two bits set.
    # The number of ones in the characteristic bitmap is the "width"
    # of the encoding.
    #
    # Each encoding as such has a number of "active" (ie. non-zero)
    # columns. The overhead of encoding the characteristic bitmap
    # is 10 bytes, plus 2 bytes per active column.
    #
    # When an encoding is merged into another one, if the characteristic
    # of the old encoding is a subset of the new one, then the overhead
    # of the old encoding is completely eliminated. However, each row
    # now would require more bytes to encode, to the tune of one byte
    # per characteristic bit that is active in the new encoding but not
    # in the old one.
    #
    # The "gain" of merging two encodings is how many bytes we save by doing so.
    #
    # High-level algorithm:
    #
    # - Each encoding has a minimal way to encode it. However, because
    #   of the overhead of encoding the characteristic bitmap, it may
    #   be beneficial to merge two encodings together, if there is
    #   gain in doing so. As such, we need to search for the best
    #   such successive merges.
    #
    # Algorithm:
    #
    # - Put all encodings into a "todo" list.
    #
    # - Sort todo list (for stability) by width_sort_key(), which is a tuple
    #   of the following items:
    #   * The "width" of the encoding.
    #   * The characteristic bitmap of the encoding, with higher-numbered
    #     columns compared first.
    #
    # - Make a priority-queue of the gain from combining each two
    #   encodings in the todo list. The priority queue is sorted by
    #   decreasing gain. Only positive gains are included.
    #
    # - While priority queue is not empty:
    #   - Pop the first item from the priority queue,
    #   - Merge the two encodings it represents,
    #   - Remove the two encodings from the todo list,
    #   - Insert positive gains from combining the new encoding with
    #     all existing todo list items into the priority queue,
    #   - If a todo list item with the same characteristic bitmap as
    #     the new encoding exists, remove it from the todo list and
    #     merge it into the new encoding.
    #   - Insert the new encoding into the todo list,
    #
    # - Encode all remaining items in the todo list.
    #
    # The output is then sorted for stability, in the following way:
    # - The VarRegionList of the input is kept intact.
    # - The VarData is sorted by the same width_sort_key() used at the beginning.
    # - Within each VarData, the items are sorted as vectors of numbers.
    #
    # Finally, each VarData is optimized to remove the empty columns and
    # reorder columns as needed.

    # TODO
    # Check that no two VarRegions are the same; if they are, fold them.

    n = len(self.VarRegionList.Region)  # Number of columns
    zeroes = [0] * n

    front_mapping = {}  # Map from old VarIdxes to full row tuples

    encodings = _EncodingDict()

    # Collect all items into a set of full rows (with lots of zeroes.)
    for major, data in enumerate(self.VarData):
        regionIndices = data.VarRegionIndex

        for minor, item in enumerate(data.Item):
            row = list(zeroes)

            if quantization == 1:
                for regionIdx, v in zip(regionIndices, item):
                    row[regionIdx] += v
            else:
                for regionIdx, v in zip(regionIndices, item):
                    row[regionIdx] += (
                        round(v / quantization) * quantization
                    )  # TODO https://github.com/fonttools/fonttools/pull/3126#discussion_r1205439785

            row = tuple(row)

            if use_NO_VARIATION_INDEX and not any(row):
                front_mapping[(major << 16) + minor] = None
                continue

            encodings.add_row(row)
            front_mapping[(major << 16) + minor] = row

    # Prepare for the main algorithm.
    todo = sorted(encodings.values(), key=_Encoding.width_sort_key)
    del encodings

    # Repeatedly pick two best encodings to combine, and combine them.

    heap = []
    for i, encoding in enumerate(todo):
        for j in range(i + 1, len(todo)):
            other_encoding = todo[j]
            combining_gain = encoding.gain_from_merging(other_encoding)
            if combining_gain > 0:
                heappush(heap, (-combining_gain, i, j))

    while heap:
        _, i, j = heappop(heap)
        if todo[i] is None or todo[j] is None:
            continue

        encoding, other_encoding = todo[i], todo[j]
        todo[i], todo[j] = None, None

        # Combine the two encodings
        combined_chars = other_encoding.chars | encoding.chars
        combined_encoding = _Encoding(combined_chars)
        combined_encoding.extend(encoding.items)
        combined_encoding.extend(other_encoding.items)

        for k, enc in enumerate(todo):
            if enc is None:
                continue

            # In the unlikely event that the same encoding exists already,
            # combine it.
            if enc.chars == combined_chars:
                combined_encoding.extend(enc.items)
                todo[k] = None
                continue

            combining_gain = combined_encoding.gain_from_merging(enc)
            if combining_gain > 0:
                heappush(heap, (-combining_gain, k, len(todo)))

        todo.append(combined_encoding)

    encodings = [encoding for encoding in todo if encoding is not None]

    # Assemble final store.
    back_mapping = {}  # Mapping from full rows to new VarIdxes
    encodings.sort(key=_Encoding.width_sort_key)
    self.VarData = []
    for encoding in encodings:
        items = sorted(encoding.items)

        while items:
            major = len(self.VarData)
            data = ot.VarData()
            self.VarData.append(data)
            data.VarRegionIndex = range(n)
            data.VarRegionCount = len(data.VarRegionIndex)

            # Each major can only encode up to 0xFFFF entries.
            data.Item, items = items[:0xFFFF], items[0xFFFF:]

            for minor, item in enumerate(data.Item):
                back_mapping[item] = (major << 16) + minor

    # Compile final mapping.
    varidx_map = {NO_VARIATION_INDEX: NO_VARIATION_INDEX}
    for k, v in front_mapping.items():
        varidx_map[k] = back_mapping[v] if v is not None else NO_VARIATION_INDEX

    # Recalculate things and go home.
    self.VarRegionList.RegionCount = len(self.VarRegionList.Region)
    self.VarDataCount = len(self.VarData)
    for data in self.VarData:
        data.ItemCount = len(data.Item)
        data.optimize()

    # Remove unused regions.
    self.prune_regions()

    return varidx_map


ot.VarStore.optimize = VarStore_optimize


def main(args=None):
    """Optimize a font's GDEF variation store"""
    from argparse import ArgumentParser
    from fontTools import configLogger
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables.otBase import OTTableWriter

    parser = ArgumentParser(prog="varLib.varStore", description=main.__doc__)
    parser.add_argument("--quantization", type=int, default=1)
    parser.add_argument("fontfile")
    parser.add_argument("outfile", nargs="?")
    options = parser.parse_args(args)

    # TODO: allow user to configure logging via command-line options
    configLogger(level="INFO")

    quantization = options.quantization
    fontfile = options.fontfile
    outfile = options.outfile

    font = TTFont(fontfile)
    gdef = font["GDEF"]
    store = gdef.table.VarStore

    writer = OTTableWriter()
    store.compile(writer, font)
    size = len(writer.getAllData())
    print("Before: %7d bytes" % size)

    varidx_map = store.optimize(quantization=quantization)

    writer = OTTableWriter()
    store.compile(writer, font)
    size = len(writer.getAllData())
    print("After:  %7d bytes" % size)

    if outfile is not None:
        gdef.table.remap_device_varidxes(varidx_map)
        if "GPOS" in font:
            font["GPOS"].table.remap_device_varidxes(varidx_map)

        font.save(outfile)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sys.exit(main())
    import doctest

    sys.exit(doctest.testmod().failed)
