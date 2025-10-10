from fontTools.varLib.models import VariationModel
from fontTools.varLib.varStore import VarStoreInstancer
from fontTools.misc.fixedTools import fixedToFloat as fi2fl
from itertools import product
import sys


def _denormalize(v, axis):
    if v >= 0:
        return axis.defaultValue + v * (axis.maxValue - axis.defaultValue)
    else:
        return axis.defaultValue + v * (axis.defaultValue - axis.minValue)


def _pruneLocations(locations, poles, axisTags):
    # Now we have all the input locations, find which ones are
    # not needed and remove them.

    # Note: This algorithm is heavily tied to how VariationModel
    # is implemented.  It assumes that input was extracted from
    # VariationModel-generated object, like an ItemVariationStore
    # created by fontmake using varLib.models.VariationModel.
    # Some CoPilot blabbering:
    # I *think* I can prove that this algorithm is correct, but
    # I'm not 100% sure.  It's possible that there are edge cases
    # where this algorithm will fail.  I'm not sure how to prove
    # that it's correct, but I'm also not sure how to prove that
    # it's incorrect.  I'm not sure how to write a test case that
    # would prove that it's incorrect.  I'm not sure how to write
    # a test case that would prove that it's correct.

    model = VariationModel(locations, axisTags)
    modelMapping = model.mapping
    modelSupports = model.supports
    pins = {tuple(k.items()): None for k in poles}
    for location in poles:
        i = locations.index(location)
        i = modelMapping[i]
        support = modelSupports[i]
        supportAxes = set(support.keys())
        for axisTag, (minV, _, maxV) in support.items():
            for v in (minV, maxV):
                if v in (-1, 0, 1):
                    continue
                for pin in pins.keys():
                    pinLocation = dict(pin)
                    pinAxes = set(pinLocation.keys())
                    if pinAxes != supportAxes:
                        continue
                    if axisTag not in pinAxes:
                        continue
                    if pinLocation[axisTag] == v:
                        break
                else:
                    # No pin found. Go through the previous masters
                    # and find a suitable pin.  Going backwards is
                    # better because it can find a pin that is close
                    # to the pole in more dimensions, and reducing
                    # the total number of pins needed.
                    for candidateIdx in range(i - 1, -1, -1):
                        candidate = modelSupports[candidateIdx]
                        candidateAxes = set(candidate.keys())
                        if candidateAxes != supportAxes:
                            continue
                        if axisTag not in candidateAxes:
                            continue
                        candidate = {
                            k: defaultV for k, (_, defaultV, _) in candidate.items()
                        }
                        if candidate[axisTag] == v:
                            pins[tuple(candidate.items())] = None
                            break
                    else:
                        assert False, "No pin found"
    return [dict(t) for t in pins.keys()]


def mappings_from_avar(font, denormalize=True):
    fvarAxes = font["fvar"].axes
    axisMap = {a.axisTag: a for a in fvarAxes}
    axisTags = [a.axisTag for a in fvarAxes]
    axisIndexes = {a.axisTag: i for i, a in enumerate(fvarAxes)}
    if "avar" not in font:
        return {}, {}
    avar = font["avar"]
    axisMaps = {
        tag: seg
        for tag, seg in avar.segments.items()
        if seg and seg != {-1: -1, 0: 0, 1: 1}
    }
    mappings = []

    if getattr(avar, "majorVersion", 1) == 2:
        varStore = avar.table.VarStore
        regions = varStore.VarRegionList.Region

        # Find all the input locations; this finds "poles", that are
        # locations of the peaks, and "corners", that are locations
        # of the corners of the regions.  These two sets of locations
        # together constitute inputLocations to consider.

        poles = {(): None}  # Just using it as an ordered set
        inputLocations = set({()})
        for varData in varStore.VarData:
            regionIndices = varData.VarRegionIndex
            for regionIndex in regionIndices:
                peakLocation = []
                corners = []
                region = regions[regionIndex]
                for axisIndex, axis in enumerate(region.VarRegionAxis):
                    if axis.PeakCoord == 0:
                        continue
                    axisTag = axisTags[axisIndex]
                    peakLocation.append((axisTag, axis.PeakCoord))
                    corner = []
                    if axis.StartCoord != 0:
                        corner.append((axisTag, axis.StartCoord))
                    if axis.EndCoord != 0:
                        corner.append((axisTag, axis.EndCoord))
                    corners.append(corner)
                corners = set(product(*corners))
                peakLocation = tuple(peakLocation)
                poles[peakLocation] = None
                inputLocations.add(peakLocation)
                inputLocations.update(corners)

        # Sort them by number of axes, then by axis order
        inputLocations = [
            dict(t)
            for t in sorted(
                inputLocations,
                key=lambda t: (len(t), tuple(axisIndexes[tag] for tag, _ in t)),
            )
        ]
        poles = [dict(t) for t in poles.keys()]
        inputLocations = _pruneLocations(inputLocations, list(poles), axisTags)

        # Find the output locations, at input locations
        varIdxMap = avar.table.VarIdxMap
        instancer = VarStoreInstancer(varStore, fvarAxes)
        for location in inputLocations:
            instancer.setLocation(location)
            outputLocation = {}
            for axisIndex, axisTag in enumerate(axisTags):
                varIdx = axisIndex
                if varIdxMap is not None:
                    varIdx = varIdxMap[varIdx]
                delta = instancer[varIdx]
                if delta != 0:
                    v = location.get(axisTag, 0)
                    v = v + fi2fl(delta, 14)
                    # See https://github.com/fonttools/fonttools/pull/3598#issuecomment-2266082009
                    # v = max(-1, min(1, v))
                    outputLocation[axisTag] = v
            mappings.append((location, outputLocation))

        # Remove base master we added, if it maps to the default location
        assert mappings[0][0] == {}
        if mappings[0][1] == {}:
            mappings.pop(0)

    if denormalize:
        for tag, seg in axisMaps.items():
            if tag not in axisMap:
                raise ValueError(f"Unknown axis tag {tag}")
            denorm = lambda v: _denormalize(v, axisMap[tag])
            axisMaps[tag] = {denorm(k): denorm(v) for k, v in seg.items()}

        for i, (inputLoc, outputLoc) in enumerate(mappings):
            inputLoc = {
                tag: _denormalize(val, axisMap[tag]) for tag, val in inputLoc.items()
            }
            outputLoc = {
                tag: _denormalize(val, axisMap[tag]) for tag, val in outputLoc.items()
            }
            mappings[i] = (inputLoc, outputLoc)

    return axisMaps, mappings


def unbuild(font, f=sys.stdout):
    fvar = font["fvar"]
    axes = fvar.axes
    segments, mappings = mappings_from_avar(font)

    if "name" in font:
        name = font["name"]
        axisNames = {axis.axisTag: name.getDebugName(axis.axisNameID) for axis in axes}
    else:
        axisNames = {a.axisTag: a.axisTag for a in axes}

    print("<?xml version='1.0' encoding='UTF-8'?>", file=f)
    print('<designspace format="5.1">', file=f)
    print("  <axes>", file=f)
    for axis in axes:

        axisName = axisNames[axis.axisTag]

        triplet = (axis.minValue, axis.defaultValue, axis.maxValue)
        triplet = [int(v) if v == int(v) else v for v in triplet]

        axisMap = segments.get(axis.axisTag)
        closing = "/>" if axisMap is None else ">"

        print(
            f'    <axis tag="{axis.axisTag}" name="{axisName}" minimum="{triplet[0]}" maximum="{triplet[2]}" default="{triplet[1]}"{closing}',
            file=f,
        )
        if axisMap is not None:
            for k in sorted(axisMap.keys()):
                v = axisMap[k]
                k = int(k) if k == int(k) else k
                v = int(v) if v == int(v) else v
                print(f'      <map input="{k}" output="{v}"/>', file=f)
            print("    </axis>", file=f)
    if mappings:
        print("    <mappings>", file=f)
        for inputLoc, outputLoc in mappings:
            print("      <mapping>", file=f)
            print("        <input>", file=f)
            for tag in sorted(inputLoc.keys()):
                v = inputLoc[tag]
                v = int(v) if v == int(v) else v
                print(
                    f'          <dimension name="{axisNames[tag]}" xvalue="{v}"/>',
                    file=f,
                )
            print("        </input>", file=f)
            print("        <output>", file=f)
            for tag in sorted(outputLoc.keys()):
                v = outputLoc[tag]
                v = int(v) if v == int(v) else v
                print(
                    f'          <dimension name="{axisNames[tag]}" xvalue="{v}"/>',
                    file=f,
                )
            print("        </output>", file=f)
            print("      </mapping>", file=f)
        print("    </mappings>", file=f)
    print("  </axes>", file=f)
    print("</designspace>", file=f)


def main(args=None):
    """Print `avar` table as a designspace snippet."""

    if args is None:
        args = sys.argv[1:]

    from fontTools.ttLib import TTFont
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools varLib.avar.unbuild",
        description="Print `avar` table as a designspace snippet.",
    )
    parser.add_argument("font", metavar="varfont.ttf", help="Variable-font file.")
    options = parser.parse_args(args)

    font = TTFont(options.font)
    if "fvar" not in font:
        print("Not a variable font.", file=sys.stderr)
        return 1

    unbuild(font)


if __name__ == "__main__":
    import sys

    sys.exit(main())
