"""
Interpolate OpenType Layout tables (GDEF / GPOS / GSUB).
"""

from fontTools.ttLib import TTFont
from fontTools.varLib import models, VarLibError, load_designspace, load_masters
from fontTools.varLib.merger import InstancerMerger
import os.path
import logging
from copy import deepcopy
from pprint import pformat

log = logging.getLogger("fontTools.varLib.interpolate_layout")


def interpolate_layout(designspace, loc, master_finder=lambda s: s, mapped=False):
    """
    Interpolate GPOS from a designspace file and location.

    If master_finder is set, it should be a callable that takes master
    filename as found in designspace file and map it to master font
    binary as to be opened (eg. .ttf or .otf).

    If mapped is False (default), then location is mapped using the
    map element of the axes in designspace file.  If mapped is True,
    it is assumed that location is in designspace's internal space and
    no mapping is performed.
    """
    if hasattr(designspace, "sources"):  # Assume a DesignspaceDocument
        pass
    else:  # Assume a file path
        from fontTools.designspaceLib import DesignSpaceDocument

        designspace = DesignSpaceDocument.fromfile(designspace)

    ds = load_designspace(designspace)
    log.info("Building interpolated font")

    log.info("Loading master fonts")
    master_fonts = load_masters(designspace, master_finder)
    font = deepcopy(master_fonts[ds.base_idx])

    log.info("Location: %s", pformat(loc))
    if not mapped:
        loc = {name: ds.axes[name].map_forward(v) for name, v in loc.items()}
    log.info("Internal location: %s", pformat(loc))
    loc = models.normalizeLocation(loc, ds.internal_axis_supports)
    log.info("Normalized location: %s", pformat(loc))

    # Assume single-model for now.
    model = models.VariationModel(ds.normalized_master_locs)
    assert 0 == model.mapping[ds.base_idx]

    merger = InstancerMerger(font, model, loc)

    log.info("Building interpolated tables")
    # TODO GSUB/GDEF
    merger.mergeTables(font, master_fonts, ["GPOS"])
    return font


def main(args=None):
    """Interpolate GDEF/GPOS/GSUB tables for a point on a designspace"""
    from fontTools import configLogger
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        "fonttools varLib.interpolate_layout",
        description=main.__doc__,
    )
    parser.add_argument(
        "designspace_filename", metavar="DESIGNSPACE", help="Input TTF files"
    )
    parser.add_argument(
        "locations",
        metavar="LOCATION",
        type=str,
        nargs="+",
        help="Axis locations (e.g. wdth=120",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT",
        help="Output font file (defaults to <designspacename>-instance.ttf)",
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        metavar="LEVEL",
        default="INFO",
        help="Logging level (defaults to INFO)",
    )

    args = parser.parse_args(args)

    if not args.output:
        args.output = os.path.splitext(args.designspace_filename)[0] + "-instance.ttf"

    configLogger(level=args.loglevel)

    finder = lambda s: s.replace("master_ufo", "master_ttf_interpolatable").replace(
        ".ufo", ".ttf"
    )

    loc = {}
    for arg in args.locations:
        tag, val = arg.split("=")
        loc[tag] = float(val)

    font = interpolate_layout(args.designspace_filename, loc, finder)
    log.info("Saving font %s", args.output)
    font.save(args.output)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sys.exit(main())
    import doctest

    sys.exit(doctest.testmod().failed)
