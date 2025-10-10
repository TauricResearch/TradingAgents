from fontTools.varLib.models import normalizeValue


def _denormalize(v, triplet):
    if v >= 0:
        return triplet[1] + v * (triplet[2] - triplet[1])
    else:
        return triplet[1] + v * (triplet[1] - triplet[0])


def map(
    font, location, *, inputNormalized=False, outputNormalized=False, dropZeroes=False
):
    if "fvar" not in font:
        return None

    fvar = font["fvar"]
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fvar.axes}

    if not inputNormalized:
        location = {
            tag: normalizeValue(value, axes[tag]) for tag, value in location.items()
        }

    if "avar" in font:
        location = font["avar"].renormalizeLocation(location, font, dropZeroes)

    if not outputNormalized:
        location = {
            tag: _denormalize(value, axes[tag]) for tag, value in location.items()
        }

    return location


def main(args=None):
    """Map variation coordinates through the `avar` table."""

    from fontTools.ttLib import TTFont
    import argparse

    if args is None:
        import sys

        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        "fonttools varLib.avar.map",
        description="Map variation coordinates through the `avar` table.",
    )
    parser.add_argument("font", metavar="varfont.ttf", help="Variable-font file.")
    parser.add_argument(
        "coords",
        metavar="[AXIS=value...]",
        help="Coordinates to map, e.g. 'wght=700 wdth=75'.",
        nargs="*",
        default=None,
    )
    parser.add_argument(
        "-f", action="store_true", help="Do not omit axes at default location."
    )
    parser.add_argument(
        "-i", action="store_true", help="Input coordinates are normalized (-1..1)."
    )
    parser.add_argument(
        "-o", action="store_true", help="Output coordinates as normalized (-1..1)."
    )

    options = parser.parse_args(args)

    if not options.coords:
        parser.error(
            "No coordinates provided. Please specify at least one axis coordinate (e.g., wght=500)"
        )

    if options.font.endswith(".designspace"):
        from .build import build

        font = TTFont()
        build(font, options.font)
    else:
        font = TTFont(options.font)
        if "fvar" not in font:
            parser.error(f"Font '{options.font}' does not contain an 'fvar' table.")

    location = {
        tag: float(value) for tag, value in (item.split("=") for item in options.coords)
    }

    mapped = map(
        font,
        location,
        inputNormalized=options.i,
        outputNormalized=options.o,
        dropZeroes=not options.f,
    )
    assert mapped is not None

    for tag in mapped:
        v = mapped[tag]
        v = int(v) if v == int(v) else v
        print(f"{tag}={v:g}")


if __name__ == "__main__":
    import sys

    sys.exit(main())
