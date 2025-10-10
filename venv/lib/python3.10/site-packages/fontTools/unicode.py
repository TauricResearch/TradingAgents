def _makeunicodes(f):
    lines = iter(f.readlines())
    unicodes = {}
    for line in lines:
        if not line:
            continue
        num, name = line.split(";")[:2]
        if name[0] == "<":
            continue  # "<control>", etc.
        num = int(num, 16)
        unicodes[num] = name
    return unicodes


class _UnicodeCustom(object):
    def __init__(self, f):
        if isinstance(f, str):
            with open(f) as fd:
                codes = _makeunicodes(fd)
        else:
            codes = _makeunicodes(f)
        self.codes = codes

    def __getitem__(self, charCode):
        try:
            return self.codes[charCode]
        except KeyError:
            return "????"


class _UnicodeBuiltin(object):
    def __getitem__(self, charCode):
        try:
            # use unicodedata backport to python2, if available:
            # https://github.com/mikekap/unicodedata2
            import unicodedata2 as unicodedata
        except ImportError:
            import unicodedata
        try:
            return unicodedata.name(chr(charCode))
        except ValueError:
            return "????"


Unicode = _UnicodeBuiltin()


def setUnicodeData(f):
    global Unicode
    Unicode = _UnicodeCustom(f)
