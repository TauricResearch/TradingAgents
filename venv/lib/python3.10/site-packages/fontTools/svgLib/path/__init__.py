from fontTools.pens.transformPen import TransformPen
from fontTools.misc import etree
from fontTools.misc.textTools import tostr
from .parser import parse_path
from .shapes import PathBuilder


__all__ = [tostr(s) for s in ("SVGPath", "parse_path")]


class SVGPath(object):
    """Parse SVG ``path`` elements from a file or string, and draw them
    onto a glyph object that supports the FontTools Pen protocol.

    For example, reading from an SVG file and drawing to a Defcon Glyph:

    .. code-block::

        import defcon
        glyph = defcon.Glyph()
        pen = glyph.getPen()
        svg = SVGPath("path/to/a.svg")
        svg.draw(pen)

    Or reading from a string containing SVG data, using the alternative
    'fromstring' (a class method):

    .. code-block::

        data = '<?xml version="1.0" ...'
        svg = SVGPath.fromstring(data)
        svg.draw(pen)

    Both constructors can optionally take a 'transform' matrix (6-float
    tuple, or a FontTools Transform object) to modify the draw output.
    """

    def __init__(self, filename=None, transform=None):
        if filename is None:
            self.root = etree.ElementTree()
        else:
            tree = etree.parse(filename)
            self.root = tree.getroot()
        self.transform = transform

    @classmethod
    def fromstring(cls, data, transform=None):
        self = cls(transform=transform)
        self.root = etree.fromstring(data)
        return self

    def draw(self, pen):
        if self.transform:
            pen = TransformPen(pen, self.transform)
        pb = PathBuilder()
        # xpath | doesn't seem to reliable work so just walk it
        for el in self.root.iter():
            pb.add_path_from_element(el)
        original_pen = pen
        for path, transform in zip(pb.paths, pb.transforms):
            if transform:
                pen = TransformPen(original_pen, transform)
            else:
                pen = original_pen
            parse_path(path, pen)
