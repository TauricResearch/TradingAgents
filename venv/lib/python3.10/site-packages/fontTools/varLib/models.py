"""Variation fonts interpolation models."""

__all__ = [
    "normalizeValue",
    "normalizeLocation",
    "supportScalar",
    "piecewiseLinearMap",
    "VariationModel",
]

from fontTools.misc.roundTools import noRound
from .errors import VariationModelError


def nonNone(lst):
    return [l for l in lst if l is not None]


def allNone(lst):
    return all(l is None for l in lst)


def allEqualTo(ref, lst, mapper=None):
    if mapper is None:
        return all(ref == item for item in lst)

    mapped = mapper(ref)
    return all(mapped == mapper(item) for item in lst)


def allEqual(lst, mapper=None):
    if not lst:
        return True
    it = iter(lst)
    try:
        first = next(it)
    except StopIteration:
        return True
    return allEqualTo(first, it, mapper=mapper)


def subList(truth, lst):
    assert len(truth) == len(lst)
    return [l for l, t in zip(lst, truth) if t]


def normalizeValue(v, triple, extrapolate=False):
    """Normalizes value based on a min/default/max triple.

    >>> normalizeValue(400, (100, 400, 900))
    0.0
    >>> normalizeValue(100, (100, 400, 900))
    -1.0
    >>> normalizeValue(650, (100, 400, 900))
    0.5
    """
    lower, default, upper = triple
    if not (lower <= default <= upper):
        raise ValueError(
            f"Invalid axis values, must be minimum, default, maximum: "
            f"{lower:3.3f}, {default:3.3f}, {upper:3.3f}"
        )
    if not extrapolate:
        v = max(min(v, upper), lower)

    if v == default or lower == upper:
        return 0.0

    if (v < default and lower != default) or (v > default and upper == default):
        return (v - default) / (default - lower)
    else:
        assert (v > default and upper != default) or (
            v < default and lower == default
        ), f"Ooops... v={v}, triple=({lower}, {default}, {upper})"
        return (v - default) / (upper - default)


def normalizeLocation(location, axes, extrapolate=False, *, validate=False):
    """Normalizes location based on axis min/default/max values from axes.

    >>> axes = {"wght": (100, 400, 900)}
    >>> normalizeLocation({"wght": 400}, axes)
    {'wght': 0.0}
    >>> normalizeLocation({"wght": 100}, axes)
    {'wght': -1.0}
    >>> normalizeLocation({"wght": 900}, axes)
    {'wght': 1.0}
    >>> normalizeLocation({"wght": 650}, axes)
    {'wght': 0.5}
    >>> normalizeLocation({"wght": 1000}, axes)
    {'wght': 1.0}
    >>> normalizeLocation({"wght": 0}, axes)
    {'wght': -1.0}
    >>> axes = {"wght": (0, 0, 1000)}
    >>> normalizeLocation({"wght": 0}, axes)
    {'wght': 0.0}
    >>> normalizeLocation({"wght": -1}, axes)
    {'wght': 0.0}
    >>> normalizeLocation({"wght": 1000}, axes)
    {'wght': 1.0}
    >>> normalizeLocation({"wght": 500}, axes)
    {'wght': 0.5}
    >>> normalizeLocation({"wght": 1001}, axes)
    {'wght': 1.0}
    >>> axes = {"wght": (0, 1000, 1000)}
    >>> normalizeLocation({"wght": 0}, axes)
    {'wght': -1.0}
    >>> normalizeLocation({"wght": -1}, axes)
    {'wght': -1.0}
    >>> normalizeLocation({"wght": 500}, axes)
    {'wght': -0.5}
    >>> normalizeLocation({"wght": 1000}, axes)
    {'wght': 0.0}
    >>> normalizeLocation({"wght": 1001}, axes)
    {'wght': 0.0}
    """
    if validate:
        assert set(location.keys()) <= set(axes.keys()), set(location.keys()) - set(
            axes.keys()
        )
    out = {}
    for tag, triple in axes.items():
        v = location.get(tag, triple[1])
        out[tag] = normalizeValue(v, triple, extrapolate=extrapolate)
    return out


def supportScalar(location, support, ot=True, extrapolate=False, axisRanges=None):
    """Returns the scalar multiplier at location, for a master
    with support.  If ot is True, then a peak value of zero
    for support of an axis means "axis does not participate".  That
    is how OpenType Variation Font technology works.

    If extrapolate is True, axisRanges must be a dict that maps axis
    names to (axisMin, axisMax) tuples.

      >>> supportScalar({}, {})
      1.0
      >>> supportScalar({'wght':.2}, {})
      1.0
      >>> supportScalar({'wght':.2}, {'wght':(0,2,3)})
      0.1
      >>> supportScalar({'wght':2.5}, {'wght':(0,2,4)})
      0.75
      >>> supportScalar({'wght':2.5, 'wdth':0}, {'wght':(0,2,4), 'wdth':(-1,0,+1)})
      0.75
      >>> supportScalar({'wght':2.5, 'wdth':.5}, {'wght':(0,2,4), 'wdth':(-1,0,+1)}, ot=False)
      0.375
      >>> supportScalar({'wght':2.5, 'wdth':0}, {'wght':(0,2,4), 'wdth':(-1,0,+1)})
      0.75
      >>> supportScalar({'wght':2.5, 'wdth':.5}, {'wght':(0,2,4), 'wdth':(-1,0,+1)})
      0.75
      >>> supportScalar({'wght':3}, {'wght':(0,1,2)}, extrapolate=True, axisRanges={'wght':(0, 2)})
      -1.0
      >>> supportScalar({'wght':-1}, {'wght':(0,1,2)}, extrapolate=True, axisRanges={'wght':(0, 2)})
      -1.0
      >>> supportScalar({'wght':3}, {'wght':(0,2,2)}, extrapolate=True, axisRanges={'wght':(0, 2)})
      1.5
      >>> supportScalar({'wght':-1}, {'wght':(0,2,2)}, extrapolate=True, axisRanges={'wght':(0, 2)})
      -0.5
    """
    if extrapolate and axisRanges is None:
        raise TypeError("axisRanges must be passed when extrapolate is True")
    scalar = 1.0
    for axis, (lower, peak, upper) in support.items():
        if ot:
            # OpenType-specific case handling
            if peak == 0.0:
                continue
            if lower > peak or peak > upper:
                continue
            if lower < 0.0 and upper > 0.0:
                continue
            v = location.get(axis, 0.0)
        else:
            assert axis in location
            v = location[axis]
        if v == peak:
            continue

        if extrapolate:
            axisMin, axisMax = axisRanges[axis]
            if v < axisMin and lower <= axisMin:
                if peak <= axisMin and peak < upper:
                    scalar *= (v - upper) / (peak - upper)
                    continue
                elif axisMin < peak:
                    scalar *= (v - lower) / (peak - lower)
                    continue
            elif axisMax < v and axisMax <= upper:
                if axisMax <= peak and lower < peak:
                    scalar *= (v - lower) / (peak - lower)
                    continue
                elif peak < axisMax:
                    scalar *= (v - upper) / (peak - upper)
                    continue

        if v <= lower or upper <= v:
            scalar = 0.0
            break

        if v < peak:
            scalar *= (v - lower) / (peak - lower)
        else:  # v > peak
            scalar *= (v - upper) / (peak - upper)
    return scalar


class VariationModel(object):
    """Locations must have the base master at the origin (ie. 0).

    If axis-ranges are not provided, values are assumed to be normalized to
    the range [-1, 1].

    If the extrapolate argument is set to True, then values are extrapolated
    outside the axis range.

      >>> from pprint import pprint
      >>> axisRanges = {'wght': (-180, +180), 'wdth': (-1, +1)}
      >>> locations = [ \
      {'wght':100}, \
      {'wght':-100}, \
      {'wght':-180}, \
      {'wdth':+.3}, \
      {'wght':+120,'wdth':.3}, \
      {'wght':+120,'wdth':.2}, \
      {}, \
      {'wght':+180,'wdth':.3}, \
      {'wght':+180}, \
      ]
      >>> model = VariationModel(locations, axisOrder=['wght'], axisRanges=axisRanges)
      >>> pprint(model.locations)
      [{},
       {'wght': -100},
       {'wght': -180},
       {'wght': 100},
       {'wght': 180},
       {'wdth': 0.3},
       {'wdth': 0.3, 'wght': 180},
       {'wdth': 0.3, 'wght': 120},
       {'wdth': 0.2, 'wght': 120}]
      >>> pprint(model.deltaWeights)
      [{},
       {0: 1.0},
       {0: 1.0},
       {0: 1.0},
       {0: 1.0},
       {0: 1.0},
       {0: 1.0, 4: 1.0, 5: 1.0},
       {0: 1.0, 3: 0.75, 4: 0.25, 5: 1.0, 6: 0.6666666666666666},
       {0: 1.0,
        3: 0.75,
        4: 0.25,
        5: 0.6666666666666667,
        6: 0.4444444444444445,
        7: 0.6666666666666667}]
    """

    def __init__(
        self, locations, axisOrder=None, extrapolate=False, *, axisRanges=None
    ):
        if len(set(tuple(sorted(l.items())) for l in locations)) != len(locations):
            raise VariationModelError("Locations must be unique.")

        self.origLocations = locations
        self.axisOrder = axisOrder if axisOrder is not None else []
        self.extrapolate = extrapolate
        if axisRanges is None:
            if extrapolate:
                axisRanges = self.computeAxisRanges(locations)
            else:
                allAxes = {axis for loc in locations for axis in loc.keys()}
                axisRanges = {axis: (-1, 1) for axis in allAxes}
        self.axisRanges = axisRanges

        locations = [{k: v for k, v in loc.items() if v != 0.0} for loc in locations]
        keyFunc = self.getMasterLocationsSortKeyFunc(
            locations, axisOrder=self.axisOrder
        )
        self.locations = sorted(locations, key=keyFunc)

        # Mapping from user's master order to our master order
        self.mapping = [self.locations.index(l) for l in locations]
        self.reverseMapping = [locations.index(l) for l in self.locations]

        self._computeMasterSupports()
        self._subModels = {}

    def getSubModel(self, items):
        """Return a sub-model and the items that are not None.

        The sub-model is necessary for working with the subset
        of items when some are None.

        The sub-model is cached."""
        if None not in items:
            return self, items
        key = tuple(v is not None for v in items)
        subModel = self._subModels.get(key)
        if subModel is None:
            subModel = VariationModel(subList(key, self.origLocations), self.axisOrder)
            self._subModels[key] = subModel
        return subModel, subList(key, items)

    @staticmethod
    def computeAxisRanges(locations):
        axisRanges = {}
        allAxes = {axis for loc in locations for axis in loc.keys()}
        for loc in locations:
            for axis in allAxes:
                value = loc.get(axis, 0)
                axisMin, axisMax = axisRanges.get(axis, (value, value))
                axisRanges[axis] = min(value, axisMin), max(value, axisMax)
        return axisRanges

    @staticmethod
    def getMasterLocationsSortKeyFunc(locations, axisOrder=[]):
        if {} not in locations:
            raise VariationModelError("Base master not found.")
        axisPoints = {}
        for loc in locations:
            if len(loc) != 1:
                continue
            axis = next(iter(loc))
            value = loc[axis]
            if axis not in axisPoints:
                axisPoints[axis] = {0.0}
            assert (
                value not in axisPoints[axis]
            ), 'Value "%s" in axisPoints["%s"] -->  %s' % (value, axis, axisPoints)
            axisPoints[axis].add(value)

        def getKey(axisPoints, axisOrder):
            def sign(v):
                return -1 if v < 0 else +1 if v > 0 else 0

            def key(loc):
                rank = len(loc)
                onPointAxes = [
                    axis
                    for axis, value in loc.items()
                    if axis in axisPoints and value in axisPoints[axis]
                ]
                orderedAxes = [axis for axis in axisOrder if axis in loc]
                orderedAxes.extend(
                    [axis for axis in sorted(loc.keys()) if axis not in axisOrder]
                )
                return (
                    rank,  # First, order by increasing rank
                    -len(onPointAxes),  # Next, by decreasing number of onPoint axes
                    tuple(
                        axisOrder.index(axis) if axis in axisOrder else 0x10000
                        for axis in orderedAxes
                    ),  # Next, by known axes
                    tuple(orderedAxes),  # Next, by all axes
                    tuple(
                        sign(loc[axis]) for axis in orderedAxes
                    ),  # Next, by signs of axis values
                    tuple(
                        abs(loc[axis]) for axis in orderedAxes
                    ),  # Next, by absolute value of axis values
                )

            return key

        ret = getKey(axisPoints, axisOrder)
        return ret

    def reorderMasters(self, master_list, mapping):
        # For changing the master data order without
        # recomputing supports and deltaWeights.
        new_list = [master_list[idx] for idx in mapping]
        self.origLocations = [self.origLocations[idx] for idx in mapping]
        locations = [
            {k: v for k, v in loc.items() if v != 0.0} for loc in self.origLocations
        ]
        self.mapping = [self.locations.index(l) for l in locations]
        self.reverseMapping = [locations.index(l) for l in self.locations]
        self._subModels = {}
        return new_list

    def _computeMasterSupports(self):
        self.supports = []
        regions = self._locationsToRegions()
        for i, region in enumerate(regions):
            locAxes = set(region.keys())
            # Walk over previous masters now
            for prev_region in regions[:i]:
                # Master with different axes do not participte
                if set(prev_region.keys()) != locAxes:
                    continue
                # If it's NOT in the current box, it does not participate
                relevant = True
                for axis, (lower, peak, upper) in region.items():
                    if not (
                        prev_region[axis][1] == peak
                        or lower < prev_region[axis][1] < upper
                    ):
                        relevant = False
                        break
                if not relevant:
                    continue

                # Split the box for new master; split in whatever direction
                # that has largest range ratio.
                #
                # For symmetry, we actually cut across multiple axes
                # if they have the largest, equal, ratio.
                # https://github.com/fonttools/fonttools/commit/7ee81c8821671157968b097f3e55309a1faa511e#commitcomment-31054804

                bestAxes = {}
                bestRatio = -1
                for axis in prev_region.keys():
                    val = prev_region[axis][1]
                    assert axis in region
                    lower, locV, upper = region[axis]
                    newLower, newUpper = lower, upper
                    if val < locV:
                        newLower = val
                        ratio = (val - locV) / (lower - locV)
                    elif locV < val:
                        newUpper = val
                        ratio = (val - locV) / (upper - locV)
                    else:  # val == locV
                        # Can't split box in this direction.
                        continue
                    if ratio > bestRatio:
                        bestAxes = {}
                        bestRatio = ratio
                    if ratio == bestRatio:
                        bestAxes[axis] = (newLower, locV, newUpper)

                for axis, triple in bestAxes.items():
                    region[axis] = triple
            self.supports.append(region)
        self._computeDeltaWeights()

    def _locationsToRegions(self):
        locations = self.locations
        axisRanges = self.axisRanges

        regions = []
        for loc in locations:
            region = {}
            for axis, locV in loc.items():
                if locV > 0:
                    region[axis] = (0, locV, axisRanges[axis][1])
                else:
                    region[axis] = (axisRanges[axis][0], locV, 0)
            regions.append(region)
        return regions

    def _computeDeltaWeights(self):
        self.deltaWeights = []
        for i, loc in enumerate(self.locations):
            deltaWeight = {}
            # Walk over previous masters now, populate deltaWeight
            for j, support in enumerate(self.supports[:i]):
                scalar = supportScalar(loc, support)
                if scalar:
                    deltaWeight[j] = scalar
            self.deltaWeights.append(deltaWeight)

    def getDeltas(self, masterValues, *, round=noRound):
        assert len(masterValues) == len(self.deltaWeights), (
            len(masterValues),
            len(self.deltaWeights),
        )
        mapping = self.reverseMapping
        out = []
        for i, weights in enumerate(self.deltaWeights):
            delta = masterValues[mapping[i]]
            for j, weight in weights.items():
                if weight == 1:
                    delta -= out[j]
                else:
                    delta -= out[j] * weight
            out.append(round(delta))
        return out

    def getDeltasAndSupports(self, items, *, round=noRound):
        model, items = self.getSubModel(items)
        return model.getDeltas(items, round=round), model.supports

    def getScalars(self, loc):
        """Return scalars for each delta, for the given location.
        If interpolating many master-values at the same location,
        this function allows speed up by fetching the scalars once
        and using them with interpolateFromMastersAndScalars()."""
        return [
            supportScalar(
                loc, support, extrapolate=self.extrapolate, axisRanges=self.axisRanges
            )
            for support in self.supports
        ]

    def getMasterScalars(self, targetLocation):
        """Return multipliers for each master, for the given location.
        If interpolating many master-values at the same location,
        this function allows speed up by fetching the scalars once
        and using them with interpolateFromValuesAndScalars().

        Note that the scalars used in interpolateFromMastersAndScalars(),
        are *not* the same as the ones returned here. They are the result
        of getScalars()."""
        out = self.getScalars(targetLocation)
        for i, weights in reversed(list(enumerate(self.deltaWeights))):
            for j, weight in weights.items():
                out[j] -= out[i] * weight

        out = [out[self.mapping[i]] for i in range(len(out))]
        return out

    @staticmethod
    def interpolateFromValuesAndScalars(values, scalars):
        """Interpolate from values and scalars coefficients.

        If the values are master-values, then the scalars should be
        fetched from getMasterScalars().

        If the values are deltas, then the scalars should be fetched
        from getScalars(); in which case this is the same as
        interpolateFromDeltasAndScalars().
        """
        v = None
        assert len(values) == len(scalars)
        for value, scalar in zip(values, scalars):
            if not scalar:
                continue
            contribution = value * scalar
            if v is None:
                v = contribution
            else:
                v += contribution
        return v

    @staticmethod
    def interpolateFromDeltasAndScalars(deltas, scalars):
        """Interpolate from deltas and scalars fetched from getScalars()."""
        return VariationModel.interpolateFromValuesAndScalars(deltas, scalars)

    def interpolateFromDeltas(self, loc, deltas):
        """Interpolate from deltas, at location loc."""
        scalars = self.getScalars(loc)
        return self.interpolateFromDeltasAndScalars(deltas, scalars)

    def interpolateFromMasters(self, loc, masterValues, *, round=noRound):
        """Interpolate from master-values, at location loc."""
        scalars = self.getMasterScalars(loc)
        return self.interpolateFromValuesAndScalars(masterValues, scalars)

    def interpolateFromMastersAndScalars(self, masterValues, scalars, *, round=noRound):
        """Interpolate from master-values, and scalars fetched from
        getScalars(), which is useful when you want to interpolate
        multiple master-values with the same location."""
        deltas = self.getDeltas(masterValues, round=round)
        return self.interpolateFromDeltasAndScalars(deltas, scalars)


def piecewiseLinearMap(v, mapping):
    keys = mapping.keys()
    if not keys:
        return v
    if v in keys:
        return mapping[v]
    k = min(keys)
    if v < k:
        return v + mapping[k] - k
    k = max(keys)
    if v > k:
        return v + mapping[k] - k
    # Interpolate
    a = max(k for k in keys if k < v)
    b = min(k for k in keys if k > v)
    va = mapping[a]
    vb = mapping[b]
    return va + (vb - va) * (v - a) / (b - a)


def main(args=None):
    """Normalize locations on a given designspace"""
    from fontTools import configLogger
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools varLib.models",
        description=main.__doc__,
    )
    parser.add_argument(
        "--loglevel",
        metavar="LEVEL",
        default="INFO",
        help="Logging level (defaults to INFO)",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-d", "--designspace", metavar="DESIGNSPACE", type=str)
    group.add_argument(
        "-l",
        "--locations",
        metavar="LOCATION",
        nargs="+",
        help="Master locations as comma-separate coordinates. One must be all zeros.",
    )

    args = parser.parse_args(args)

    configLogger(level=args.loglevel)
    from pprint import pprint

    if args.designspace:
        from fontTools.designspaceLib import DesignSpaceDocument

        doc = DesignSpaceDocument()
        doc.read(args.designspace)
        locs = [s.location for s in doc.sources]
        print("Original locations:")
        pprint(locs)
        doc.normalize()
        print("Normalized locations:")
        locs = [s.location for s in doc.sources]
        pprint(locs)
    else:
        axes = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        locs = [
            dict(zip(axes, (float(v) for v in s.split(",")))) for s in args.locations
        ]

    model = VariationModel(locs)
    print("Sorted locations:")
    pprint(model.locations)
    print("Supports:")
    pprint(model.supports)


if __name__ == "__main__":
    import doctest, sys

    if len(sys.argv) > 1:
        sys.exit(main())

    sys.exit(doctest.testmod().failed)
