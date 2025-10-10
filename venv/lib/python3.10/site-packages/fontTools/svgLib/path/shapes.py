import re


def _prefer_non_zero(*args):
    for arg in args:
        if arg != 0:
            return arg
    return 0.0


def _ntos(n):
    # %f likes to add unnecessary 0's, %g isn't consistent about # decimals
    return ("%.3f" % n).rstrip("0").rstrip(".")


def _strip_xml_ns(tag):
    # ElementTree API doesn't provide a way to ignore XML namespaces in tags
    # so we here strip them ourselves: cf. https://bugs.python.org/issue18304
    return tag.split("}", 1)[1] if "}" in tag else tag


def _transform(raw_value):
    # TODO assumes a 'matrix' transform.
    # No other transform functions are supported at the moment.
    # https://developer.mozilla.org/en-US/docs/Web/SVG/Attribute/transform
    # start simple: if you aren't exactly matrix(...) then no love
    match = re.match(r"matrix\((.*)\)", raw_value)
    if not match:
        raise NotImplementedError
    matrix = tuple(float(p) for p in re.split(r"\s+|,", match.group(1)))
    if len(matrix) != 6:
        raise ValueError("wrong # of terms in %s" % raw_value)
    return matrix


class PathBuilder(object):
    def __init__(self):
        self.paths = []
        self.transforms = []

    def _start_path(self, initial_path=""):
        self.paths.append(initial_path)
        self.transforms.append(None)

    def _end_path(self):
        self._add("z")

    def _add(self, path_snippet):
        path = self.paths[-1]
        if path:
            path += " " + path_snippet
        else:
            path = path_snippet
        self.paths[-1] = path

    def _move(self, c, x, y):
        self._add("%s%s,%s" % (c, _ntos(x), _ntos(y)))

    def M(self, x, y):
        self._move("M", x, y)

    def m(self, x, y):
        self._move("m", x, y)

    def _arc(self, c, rx, ry, x, y, large_arc):
        self._add(
            "%s%s,%s 0 %d 1 %s,%s"
            % (c, _ntos(rx), _ntos(ry), large_arc, _ntos(x), _ntos(y))
        )

    def A(self, rx, ry, x, y, large_arc=0):
        self._arc("A", rx, ry, x, y, large_arc)

    def a(self, rx, ry, x, y, large_arc=0):
        self._arc("a", rx, ry, x, y, large_arc)

    def _vhline(self, c, x):
        self._add("%s%s" % (c, _ntos(x)))

    def H(self, x):
        self._vhline("H", x)

    def h(self, x):
        self._vhline("h", x)

    def V(self, y):
        self._vhline("V", y)

    def v(self, y):
        self._vhline("v", y)

    def _line(self, c, x, y):
        self._add("%s%s,%s" % (c, _ntos(x), _ntos(y)))

    def L(self, x, y):
        self._line("L", x, y)

    def l(self, x, y):
        self._line("l", x, y)

    def _parse_line(self, line):
        x1 = float(line.attrib.get("x1", 0))
        y1 = float(line.attrib.get("y1", 0))
        x2 = float(line.attrib.get("x2", 0))
        y2 = float(line.attrib.get("y2", 0))

        self._start_path()
        self.M(x1, y1)
        self.L(x2, y2)

    def _parse_rect(self, rect):
        x = float(rect.attrib.get("x", 0))
        y = float(rect.attrib.get("y", 0))
        w = float(rect.attrib.get("width"))
        h = float(rect.attrib.get("height"))
        rx = float(rect.attrib.get("rx", 0))
        ry = float(rect.attrib.get("ry", 0))

        rx = _prefer_non_zero(rx, ry)
        ry = _prefer_non_zero(ry, rx)
        # TODO there are more rules for adjusting rx, ry

        self._start_path()
        self.M(x + rx, y)
        self.H(x + w - rx)
        if rx > 0:
            self.A(rx, ry, x + w, y + ry)
        self.V(y + h - ry)
        if rx > 0:
            self.A(rx, ry, x + w - rx, y + h)
        self.H(x + rx)
        if rx > 0:
            self.A(rx, ry, x, y + h - ry)
        self.V(y + ry)
        if rx > 0:
            self.A(rx, ry, x + rx, y)
        self._end_path()

    def _parse_path(self, path):
        if "d" in path.attrib:
            self._start_path(initial_path=path.attrib["d"])

    def _parse_polygon(self, poly):
        if "points" in poly.attrib:
            self._start_path("M" + poly.attrib["points"])
            self._end_path()

    def _parse_polyline(self, poly):
        if "points" in poly.attrib:
            self._start_path("M" + poly.attrib["points"])

    def _parse_circle(self, circle):
        cx = float(circle.attrib.get("cx", 0))
        cy = float(circle.attrib.get("cy", 0))
        r = float(circle.attrib.get("r"))

        # arc doesn't seem to like being a complete shape, draw two halves
        self._start_path()
        self.M(cx - r, cy)
        self.A(r, r, cx + r, cy, large_arc=1)
        self.A(r, r, cx - r, cy, large_arc=1)

    def _parse_ellipse(self, ellipse):
        cx = float(ellipse.attrib.get("cx", 0))
        cy = float(ellipse.attrib.get("cy", 0))
        rx = float(ellipse.attrib.get("rx"))
        ry = float(ellipse.attrib.get("ry"))

        # arc doesn't seem to like being a complete shape, draw two halves
        self._start_path()
        self.M(cx - rx, cy)
        self.A(rx, ry, cx + rx, cy, large_arc=1)
        self.A(rx, ry, cx - rx, cy, large_arc=1)

    def add_path_from_element(self, el):
        tag = _strip_xml_ns(el.tag)
        parse_fn = getattr(self, "_parse_%s" % tag.lower(), None)
        if not callable(parse_fn):
            return False
        parse_fn(el)
        if "transform" in el.attrib:
            self.transforms[-1] = _transform(el.attrib["transform"])
        return True
