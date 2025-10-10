from io import BytesIO
import struct
from fontTools.misc import sstruct
from fontTools.misc.textTools import bytesjoin, tostr
from collections import OrderedDict
from collections.abc import MutableMapping


class ResourceError(Exception):
    pass


class ResourceReader(MutableMapping):
    """Reader for Mac OS resource forks.

    Parses a resource fork and returns resources according to their type.
    If run on OS X, this will open the resource fork in the filesystem.
    Otherwise, it will open the file itself and attempt to read it as
    though it were a resource fork.

    The returned object can be indexed by type and iterated over,
    returning in each case a list of py:class:`Resource` objects
    representing all the resources of a certain type.

    """

    def __init__(self, fileOrPath):
        """Open a file

        Args:
                fileOrPath: Either an object supporting a ``read`` method, an
                        ``os.PathLike`` object, or a string.
        """
        self._resources = OrderedDict()
        if hasattr(fileOrPath, "read"):
            self.file = fileOrPath
        else:
            try:
                # try reading from the resource fork (only works on OS X)
                self.file = self.openResourceFork(fileOrPath)
                self._readFile()
                return
            except (ResourceError, IOError):
                # if it fails, use the data fork
                self.file = self.openDataFork(fileOrPath)
        self._readFile()

    @staticmethod
    def openResourceFork(path):
        if hasattr(path, "__fspath__"):  # support os.PathLike objects
            path = path.__fspath__()
        with open(path + "/..namedfork/rsrc", "rb") as resfork:
            data = resfork.read()
        infile = BytesIO(data)
        infile.name = path
        return infile

    @staticmethod
    def openDataFork(path):
        with open(path, "rb") as datafork:
            data = datafork.read()
        infile = BytesIO(data)
        infile.name = path
        return infile

    def _readFile(self):
        self._readHeaderAndMap()
        self._readTypeList()

    def _read(self, numBytes, offset=None):
        if offset is not None:
            try:
                self.file.seek(offset)
            except OverflowError:
                raise ResourceError("Failed to seek offset ('offset' is too large)")
            if self.file.tell() != offset:
                raise ResourceError("Failed to seek offset (reached EOF)")
        try:
            data = self.file.read(numBytes)
        except OverflowError:
            raise ResourceError("Cannot read resource ('numBytes' is too large)")
        if len(data) != numBytes:
            raise ResourceError("Cannot read resource (not enough data)")
        return data

    def _readHeaderAndMap(self):
        self.file.seek(0)
        headerData = self._read(ResourceForkHeaderSize)
        sstruct.unpack(ResourceForkHeader, headerData, self)
        # seek to resource map, skip reserved
        mapOffset = self.mapOffset + 22
        resourceMapData = self._read(ResourceMapHeaderSize, mapOffset)
        sstruct.unpack(ResourceMapHeader, resourceMapData, self)
        self.absTypeListOffset = self.mapOffset + self.typeListOffset
        self.absNameListOffset = self.mapOffset + self.nameListOffset

    def _readTypeList(self):
        absTypeListOffset = self.absTypeListOffset
        numTypesData = self._read(2, absTypeListOffset)
        (self.numTypes,) = struct.unpack(">H", numTypesData)
        absTypeListOffset2 = absTypeListOffset + 2
        for i in range(self.numTypes + 1):
            resTypeItemOffset = absTypeListOffset2 + ResourceTypeItemSize * i
            resTypeItemData = self._read(ResourceTypeItemSize, resTypeItemOffset)
            item = sstruct.unpack(ResourceTypeItem, resTypeItemData)
            resType = tostr(item["type"], encoding="mac-roman")
            refListOffset = absTypeListOffset + item["refListOffset"]
            numRes = item["numRes"] + 1
            resources = self._readReferenceList(resType, refListOffset, numRes)
            self._resources[resType] = resources

    def _readReferenceList(self, resType, refListOffset, numRes):
        resources = []
        for i in range(numRes):
            refOffset = refListOffset + ResourceRefItemSize * i
            refData = self._read(ResourceRefItemSize, refOffset)
            res = Resource(resType)
            res.decompile(refData, self)
            resources.append(res)
        return resources

    def __getitem__(self, resType):
        return self._resources[resType]

    def __delitem__(self, resType):
        del self._resources[resType]

    def __setitem__(self, resType, resources):
        self._resources[resType] = resources

    def __len__(self):
        return len(self._resources)

    def __iter__(self):
        return iter(self._resources)

    def keys(self):
        return self._resources.keys()

    @property
    def types(self):
        """A list of the types of resources in the resource fork."""
        return list(self._resources.keys())

    def countResources(self, resType):
        """Return the number of resources of a given type."""
        try:
            return len(self[resType])
        except KeyError:
            return 0

    def getIndices(self, resType):
        """Returns a list of indices of resources of a given type."""
        numRes = self.countResources(resType)
        if numRes:
            return list(range(1, numRes + 1))
        else:
            return []

    def getNames(self, resType):
        """Return list of names of all resources of a given type."""
        return [res.name for res in self.get(resType, []) if res.name is not None]

    def getIndResource(self, resType, index):
        """Return resource of given type located at an index ranging from 1
        to the number of resources for that type, or None if not found.
        """
        if index < 1:
            return None
        try:
            res = self[resType][index - 1]
        except (KeyError, IndexError):
            return None
        return res

    def getNamedResource(self, resType, name):
        """Return the named resource of given type, else return None."""
        name = tostr(name, encoding="mac-roman")
        for res in self.get(resType, []):
            if res.name == name:
                return res
        return None

    def close(self):
        if not self.file.closed:
            self.file.close()


class Resource(object):
    """Represents a resource stored within a resource fork.

    Attributes:
            type: resource type.
            data: resource data.
            id: ID.
            name: resource name.
            attr: attributes.
    """

    def __init__(
        self, resType=None, resData=None, resID=None, resName=None, resAttr=None
    ):
        self.type = resType
        self.data = resData
        self.id = resID
        self.name = resName
        self.attr = resAttr

    def decompile(self, refData, reader):
        sstruct.unpack(ResourceRefItem, refData, self)
        # interpret 3-byte dataOffset as (padded) ULONG to unpack it with struct
        (self.dataOffset,) = struct.unpack(">L", bytesjoin([b"\0", self.dataOffset]))
        absDataOffset = reader.dataOffset + self.dataOffset
        (dataLength,) = struct.unpack(">L", reader._read(4, absDataOffset))
        self.data = reader._read(dataLength)
        if self.nameOffset == -1:
            return
        absNameOffset = reader.absNameListOffset + self.nameOffset
        (nameLength,) = struct.unpack("B", reader._read(1, absNameOffset))
        (name,) = struct.unpack(">%ss" % nameLength, reader._read(nameLength))
        self.name = tostr(name, encoding="mac-roman")


ResourceForkHeader = """
		> # big endian
		dataOffset:     L
		mapOffset:      L
		dataLen:        L
		mapLen:         L
"""

ResourceForkHeaderSize = sstruct.calcsize(ResourceForkHeader)

ResourceMapHeader = """
		> # big endian
		attr:              H
		typeListOffset:    H
		nameListOffset:    H
"""

ResourceMapHeaderSize = sstruct.calcsize(ResourceMapHeader)

ResourceTypeItem = """
		> # big endian
		type:              4s
		numRes:            H
		refListOffset:     H
"""

ResourceTypeItemSize = sstruct.calcsize(ResourceTypeItem)

ResourceRefItem = """
		> # big endian
		id:                h
		nameOffset:        h
		attr:              B
		dataOffset:        3s
		reserved:          L
"""

ResourceRefItemSize = sstruct.calcsize(ResourceRefItem)
