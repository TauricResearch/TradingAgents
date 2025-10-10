"""ttLib.macUtils.py -- Various Mac-specific stuff."""

from io import BytesIO
from fontTools.misc.macRes import ResourceReader, ResourceError


def getSFNTResIndices(path):
    """Determine whether a file has a 'sfnt' resource fork or not."""
    try:
        reader = ResourceReader(path)
        indices = reader.getIndices("sfnt")
        reader.close()
        return indices
    except ResourceError:
        return []


def openTTFonts(path):
    """Given a pathname, return a list of TTFont objects. In the case
    of a flat TTF/OTF file, the list will contain just one font object;
    but in the case of a Mac font suitcase it will contain as many
    font objects as there are sfnt resources in the file.
    """
    from fontTools import ttLib

    fonts = []
    sfnts = getSFNTResIndices(path)
    if not sfnts:
        fonts.append(ttLib.TTFont(path))
    else:
        for index in sfnts:
            fonts.append(ttLib.TTFont(path, index))
        if not fonts:
            raise ttLib.TTLibError("no fonts found in file '%s'" % path)
    return fonts


class SFNTResourceReader(BytesIO):
    """Simple read-only file wrapper for 'sfnt' resources."""

    def __init__(self, path, res_name_or_index):
        from fontTools import ttLib

        reader = ResourceReader(path)
        if isinstance(res_name_or_index, str):
            rsrc = reader.getNamedResource("sfnt", res_name_or_index)
        else:
            rsrc = reader.getIndResource("sfnt", res_name_or_index)
        if rsrc is None:
            raise ttLib.TTLibError("sfnt resource not found: %s" % res_name_or_index)
        reader.close()
        self.rsrc = rsrc
        super(SFNTResourceReader, self).__init__(rsrc.data)
        self.name = path
