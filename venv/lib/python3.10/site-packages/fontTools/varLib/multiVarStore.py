from fontTools.misc.roundTools import noRound, otRound
from fontTools.misc.intTools import bit_count
from fontTools.misc.vector import Vector
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.models import supportScalar
import fontTools.varLib.varStore  # For monkey-patching
from fontTools.varLib.builder import (
    buildVarRegionList,
    buildSparseVarRegionList,
    buildSparseVarRegion,
    buildMultiVarStore,
    buildMultiVarData,
)
from fontTools.misc.iterTools import batched
from functools import partial
from collections import defaultdict
from heapq import heappush, heappop


NO_VARIATION_INDEX = ot.NO_VARIATION_INDEX
ot.MultiVarStore.NO_VARIATION_INDEX = NO_VARIATION_INDEX


def _getLocationKey(loc):
    return tuple(sorted(loc.items(), key=lambda kv: kv[0]))


class OnlineMultiVarStoreBuilder(object):
    def __init__(self, axisTags):
        self._axisTags = axisTags
        self._regionMap = {}
        self._regionList = buildSparseVarRegionList([], axisTags)
        self._store = buildMultiVarStore(self._regionList, [])
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
        if not self._supports[0]:
            del self._supports[0]  # Drop base master support
        self._cache = None
        self._data = None

    def finish(self):
        self._regionList.RegionCount = len(self._regionList.Region)
        self._store.MultiVarDataCount = len(self._store.MultiVarData)
        return self._store

    def _add_MultiVarData(self):
        regionMap = self._regionMap
        regionList = self._regionList

        regions = self._supports
        regionIndices = []
        for region in regions:
            key = _getLocationKey(region)
            idx = regionMap.get(key)
            if idx is None:
                varRegion = buildSparseVarRegion(region, self._axisTags)
                idx = regionMap[key] = len(regionList.Region)
                regionList.Region.append(varRegion)
            regionIndices.append(idx)

        # Check if we have one already...
        key = tuple(regionIndices)
        varDataIdx = self._varDataIndices.get(key)
        if varDataIdx is not None:
            self._outer = varDataIdx
            self._data = self._store.MultiVarData[varDataIdx]
            self._cache = self._varDataCaches[key]
            if len(self._data.Item) == 0xFFFF:
                # This is full.  Need new one.
                varDataIdx = None

        if varDataIdx is None:
            self._data = buildMultiVarData(regionIndices, [])
            self._outer = len(self._store.MultiVarData)
            self._store.MultiVarData.append(self._data)
            self._varDataIndices[key] = self._outer
            if key not in self._varDataCaches:
                self._varDataCaches[key] = {}
            self._cache = self._varDataCaches[key]

    def storeMasters(self, master_values, *, round=round):
        deltas = self._model.getDeltas(master_values, round=round)
        base = deltas.pop(0)
        return base, self.storeDeltas(deltas, round=noRound)

    def storeDeltas(self, deltas, *, round=round):
        deltas = tuple(round(d) for d in deltas)

        if not any(deltas):
            return NO_VARIATION_INDEX

        deltas_tuple = tuple(tuple(d) for d in deltas)

        if not self._data:
            self._add_MultiVarData()

        varIdx = self._cache.get(deltas_tuple)
        if varIdx is not None:
            return varIdx

        inner = len(self._data.Item)
        if inner == 0xFFFF:
            # Full array. Start new one.
            self._add_MultiVarData()
            return self.storeDeltas(deltas, round=noRound)
        self._data.addItem(deltas, round=noRound)

        varIdx = (self._outer << 16) + inner
        self._cache[deltas_tuple] = varIdx
        return varIdx


def MultiVarData_addItem(self, deltas, *, round=round):
    deltas = tuple(round(d) for d in deltas)

    assert len(deltas) == self.VarRegionCount

    values = []
    for d in deltas:
        values.extend(d)

    self.Item.append(values)
    self.ItemCount = len(self.Item)


ot.MultiVarData.addItem = MultiVarData_addItem


def SparseVarRegion_get_support(self, fvar_axes):
    return {
        fvar_axes[reg.AxisIndex].axisTag: (reg.StartCoord, reg.PeakCoord, reg.EndCoord)
        for reg in self.SparseVarRegionAxis
    }


ot.SparseVarRegion.get_support = SparseVarRegion_get_support


def MultiVarStore___bool__(self):
    return bool(self.MultiVarData)


ot.MultiVarStore.__bool__ = MultiVarStore___bool__


class MultiVarStoreInstancer(object):
    def __init__(self, multivarstore, fvar_axes, location={}):
        self.fvar_axes = fvar_axes
        assert multivarstore is None or multivarstore.Format == 1
        self._varData = multivarstore.MultiVarData if multivarstore else []
        self._regions = (
            multivarstore.SparseVarRegionList.Region if multivarstore else []
        )
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
        if not deltas:
            return Vector([])
        assert len(deltas) % len(scalars) == 0, (len(deltas), len(scalars))
        m = len(deltas) // len(scalars)
        delta = Vector([0] * m)
        for d, s in zip(batched(deltas, m), scalars):
            if not s:
                continue
            delta += Vector(d) * s
        return delta

    def __getitem__(self, varidx):
        major, minor = varidx >> 16, varidx & 0xFFFF
        if varidx == NO_VARIATION_INDEX:
            return Vector([])
        varData = self._varData
        scalars = [self._getScalar(ri) for ri in varData[major].VarRegionIndex]
        deltas = varData[major].Item[minor]
        return self.interpolateFromDeltasAndScalars(deltas, scalars)

    def interpolateFromDeltas(self, varDataIndex, deltas):
        varData = self._varData
        scalars = [self._getScalar(ri) for ri in varData[varDataIndex].VarRegionIndex]
        return self.interpolateFromDeltasAndScalars(deltas, scalars)


def MultiVarStore_subset_varidxes(self, varIdxes):
    return ot.VarStore.subset_varidxes(self, varIdxes, VarData="MultiVarData")


def MultiVarStore_prune_regions(self):
    return ot.VarStore.prune_regions(
        self, VarData="MultiVarData", VarRegionList="SparseVarRegionList"
    )


ot.MultiVarStore.prune_regions = MultiVarStore_prune_regions
ot.MultiVarStore.subset_varidxes = MultiVarStore_subset_varidxes


def MultiVarStore_get_supports(self, major, fvarAxes):
    supports = []
    varData = self.MultiVarData[major]
    for regionIdx in varData.VarRegionIndex:
        region = self.SparseVarRegionList.Region[regionIdx]
        support = region.get_support(fvarAxes)
        supports.append(support)
    return supports


ot.MultiVarStore.get_supports = MultiVarStore_get_supports


def VARC_collect_varidxes(self, varidxes):
    for glyph in self.VarCompositeGlyphs.VarCompositeGlyph:
        for component in glyph.components:
            varidxes.add(component.axisValuesVarIndex)
            varidxes.add(component.transformVarIndex)


def VARC_remap_varidxes(self, varidxes_map):
    for glyph in self.VarCompositeGlyphs.VarCompositeGlyph:
        for component in glyph.components:
            component.axisValuesVarIndex = varidxes_map[component.axisValuesVarIndex]
            component.transformVarIndex = varidxes_map[component.transformVarIndex]


ot.VARC.collect_varidxes = VARC_collect_varidxes
ot.VARC.remap_varidxes = VARC_remap_varidxes
