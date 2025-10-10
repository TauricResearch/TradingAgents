# Modified from https://github.com/adobe-type-tools/psautohint/blob/08b346865710ed3c172f1eb581d6ef243b203f99/python/psautohint/ufoFont.py#L800-L838
import hashlib

from fontTools.pens.basePen import MissingComponentError
from fontTools.pens.pointPen import AbstractPointPen


class HashPointPen(AbstractPointPen):
    """
    This pen can be used to check if a glyph's contents (outlines plus
    components) have changed.

    Components are added as the original outline plus each composite's
    transformation.

    Example: You have some TrueType hinting code for a glyph which you want to
    compile. The hinting code specifies a hash value computed with HashPointPen
    that was valid for the glyph's outlines at the time the hinting code was
    written. Now you can calculate the hash for the glyph's current outlines to
    check if the outlines have changed, which would probably make the hinting
    code invalid.

    > glyph = ufo[name]
    > hash_pen = HashPointPen(glyph.width, ufo)
    > glyph.drawPoints(hash_pen)
    > ttdata = glyph.lib.get("public.truetype.instructions", None)
    > stored_hash = ttdata.get("id", None)  # The hash is stored in the "id" key
    > if stored_hash is None or stored_hash != hash_pen.hash:
    >    logger.error(f"Glyph hash mismatch, glyph '{name}' will have no instructions in font.")
    > else:
    >    # The hash values are identical, the outline has not changed.
    >    # Compile the hinting code ...
    >    pass

    If you want to compare a glyph from a source format which supports floating point
    coordinates and transformations against a glyph from a format which has restrictions
    on the precision of floats, e.g. UFO vs. TTF, you must use an appropriate rounding
    function to make the values comparable. For TTF fonts with composites, this
    construct can be used to make the transform values conform to F2Dot14:

    > ttf_hash_pen = HashPointPen(ttf_glyph_width, ttFont.getGlyphSet())
    > ttf_round_pen = RoundingPointPen(ttf_hash_pen, transformRoundFunc=partial(floatToFixedToFloat, precisionBits=14))
    > ufo_hash_pen = HashPointPen(ufo_glyph.width, ufo)
    > ttf_glyph.drawPoints(ttf_round_pen, ttFont["glyf"])
    > ufo_round_pen = RoundingPointPen(ufo_hash_pen, transformRoundFunc=partial(floatToFixedToFloat, precisionBits=14))
    > ufo_glyph.drawPoints(ufo_round_pen)
    > assert ttf_hash_pen.hash == ufo_hash_pen.hash
    """

    def __init__(self, glyphWidth=0, glyphSet=None):
        self.glyphset = glyphSet
        self.data = ["w%s" % round(glyphWidth, 9)]

    @property
    def hash(self):
        data = "".join(self.data)
        if len(data) >= 128:
            data = hashlib.sha512(data.encode("ascii")).hexdigest()
        return data

    def beginPath(self, identifier=None, **kwargs):
        pass

    def endPath(self):
        self.data.append("|")

    def addPoint(
        self,
        pt,
        segmentType=None,
        smooth=False,
        name=None,
        identifier=None,
        **kwargs,
    ):
        if segmentType is None:
            pt_type = "o"  # offcurve
        else:
            pt_type = segmentType[0]
        self.data.append(f"{pt_type}{pt[0]:g}{pt[1]:+g}")

    def addComponent(self, baseGlyphName, transformation, identifier=None, **kwargs):
        tr = "".join([f"{t:+}" for t in transformation])
        self.data.append("[")
        try:
            self.glyphset[baseGlyphName].drawPoints(self)
        except KeyError:
            raise MissingComponentError(baseGlyphName)
        self.data.append(f"({tr})]")
