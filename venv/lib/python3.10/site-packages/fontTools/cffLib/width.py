# -*- coding: utf-8 -*-

"""T2CharString glyph width optimizer.

CFF glyphs whose width equals the CFF Private dictionary's ``defaultWidthX``
value do not need to specify their width in their charstring, saving bytes.
This module determines the optimum ``defaultWidthX`` and ``nominalWidthX``
values for a font, when provided with a list of glyph widths."""

from fontTools.ttLib import TTFont
from collections import defaultdict
from operator import add
from functools import reduce


__all__ = ["optimizeWidths", "main"]


class missingdict(dict):
    def __init__(self, missing_func):
        self.missing_func = missing_func

    def __missing__(self, v):
        return self.missing_func(v)


def cumSum(f, op=add, start=0, decreasing=False):
    keys = sorted(f.keys())
    minx, maxx = keys[0], keys[-1]

    total = reduce(op, f.values(), start)

    if decreasing:
        missing = lambda x: start if x > maxx else total
        domain = range(maxx, minx - 1, -1)
    else:
        missing = lambda x: start if x < minx else total
        domain = range(minx, maxx + 1)

    out = missingdict(missing)

    v = start
    for x in domain:
        v = op(v, f[x])
        out[x] = v

    return out


def byteCost(widths, default, nominal):
    if not hasattr(widths, "items"):
        d = defaultdict(int)
        for w in widths:
            d[w] += 1
        widths = d

    cost = 0
    for w, freq in widths.items():
        if w == default:
            continue
        diff = abs(w - nominal)
        if diff <= 107:
            cost += freq
        elif diff <= 1131:
            cost += freq * 2
        else:
            cost += freq * 5
    return cost


def optimizeWidthsBruteforce(widths):
    """Bruteforce version.  Veeeeeeeeeeeeeeeeery slow.  Only works for smallests of fonts."""

    d = defaultdict(int)
    for w in widths:
        d[w] += 1

    # Maximum number of bytes using default can possibly save
    maxDefaultAdvantage = 5 * max(d.values())

    minw, maxw = min(widths), max(widths)
    domain = list(range(minw, maxw + 1))

    bestCostWithoutDefault = min(byteCost(widths, None, nominal) for nominal in domain)

    bestCost = len(widths) * 5 + 1
    for nominal in domain:
        if byteCost(widths, None, nominal) > bestCost + maxDefaultAdvantage:
            continue
        for default in domain:
            cost = byteCost(widths, default, nominal)
            if cost < bestCost:
                bestCost = cost
                bestDefault = default
                bestNominal = nominal

    return bestDefault, bestNominal


def optimizeWidths(widths):
    """Given a list of glyph widths, or dictionary mapping glyph width to number of
    glyphs having that, returns a tuple of best CFF default and nominal glyph widths.

    This algorithm is linear in UPEM+numGlyphs."""

    if not hasattr(widths, "items"):
        d = defaultdict(int)
        for w in widths:
            d[w] += 1
        widths = d

    keys = sorted(widths.keys())
    minw, maxw = keys[0], keys[-1]
    domain = list(range(minw, maxw + 1))

    # Cumulative sum/max forward/backward.
    cumFrqU = cumSum(widths, op=add)
    cumMaxU = cumSum(widths, op=max)
    cumFrqD = cumSum(widths, op=add, decreasing=True)
    cumMaxD = cumSum(widths, op=max, decreasing=True)

    # Cost per nominal choice, without default consideration.
    nomnCostU = missingdict(
        lambda x: cumFrqU[x] + cumFrqU[x - 108] + cumFrqU[x - 1132] * 3
    )
    nomnCostD = missingdict(
        lambda x: cumFrqD[x] + cumFrqD[x + 108] + cumFrqD[x + 1132] * 3
    )
    nomnCost = missingdict(lambda x: nomnCostU[x] + nomnCostD[x] - widths[x])

    # Cost-saving per nominal choice, by best default choice.
    dfltCostU = missingdict(
        lambda x: max(cumMaxU[x], cumMaxU[x - 108] * 2, cumMaxU[x - 1132] * 5)
    )
    dfltCostD = missingdict(
        lambda x: max(cumMaxD[x], cumMaxD[x + 108] * 2, cumMaxD[x + 1132] * 5)
    )
    dfltCost = missingdict(lambda x: max(dfltCostU[x], dfltCostD[x]))

    # Combined cost per nominal choice.
    bestCost = missingdict(lambda x: nomnCost[x] - dfltCost[x])

    # Best nominal.
    nominal = min(domain, key=lambda x: bestCost[x])

    # Work back the best default.
    bestC = bestCost[nominal]
    dfltC = nomnCost[nominal] - bestCost[nominal]
    ends = []
    if dfltC == dfltCostU[nominal]:
        starts = [nominal, nominal - 108, nominal - 1132]
        for start in starts:
            while cumMaxU[start] and cumMaxU[start] == cumMaxU[start - 1]:
                start -= 1
            ends.append(start)
    else:
        starts = [nominal, nominal + 108, nominal + 1132]
        for start in starts:
            while cumMaxD[start] and cumMaxD[start] == cumMaxD[start + 1]:
                start += 1
            ends.append(start)
    default = min(ends, key=lambda default: byteCost(widths, default, nominal))

    return default, nominal


def main(args=None):
    """Calculate optimum defaultWidthX/nominalWidthX values"""

    import argparse

    parser = argparse.ArgumentParser(
        "fonttools cffLib.width",
        description=main.__doc__,
    )
    parser.add_argument(
        "inputs", metavar="FILE", type=str, nargs="+", help="Input TTF files"
    )
    parser.add_argument(
        "-b",
        "--brute-force",
        dest="brute",
        action="store_true",
        help="Use brute-force approach (VERY slow)",
    )

    args = parser.parse_args(args)

    for fontfile in args.inputs:
        font = TTFont(fontfile)
        hmtx = font["hmtx"]
        widths = [m[0] for m in hmtx.metrics.values()]
        if args.brute:
            default, nominal = optimizeWidthsBruteforce(widths)
        else:
            default, nominal = optimizeWidths(widths)
        print(
            "glyphs=%d default=%d nominal=%d byteCost=%d"
            % (len(widths), default, nominal, byteCost(widths, default, nominal))
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        import doctest

        sys.exit(doctest.testmod().failed)
    main()
