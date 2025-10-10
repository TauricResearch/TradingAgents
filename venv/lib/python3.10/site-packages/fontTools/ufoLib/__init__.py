"""
A library for importing .ufo files and their descendants.
Refer to http://unifiedfontobject.org for the UFO specification.

The main interfaces are the :class:`.UFOReader` and :class:`.UFOWriter`
classes, which support versions 1, 2, and 3 of the UFO specification.

Set variables are available for external use that list the font
info attribute names for the `fontinfo.plist` formats. These are:

- :obj:`.fontInfoAttributesVersion1`
- :obj:`.fontInfoAttributesVersion2`
- :obj:`.fontInfoAttributesVersion3`

A set listing the `fontinfo.plist` attributes that were deprecated
in version 2 is available for external use:

- :obj:`.deprecatedFontInfoAttributesVersion2`

Functions that do basic validation on values for `fontinfo.plist`
are available for external use. These are

- :func:`.validateFontInfoVersion2ValueForAttribute`
- :func:`.validateFontInfoVersion3ValueForAttribute`

Value conversion functions are available for converting
`fontinfo.plist` values between the possible format versions.

- :func:`.convertFontInfoValueForAttributeFromVersion1ToVersion2`
- :func:`.convertFontInfoValueForAttributeFromVersion2ToVersion1`
- :func:`.convertFontInfoValueForAttributeFromVersion2ToVersion3`
- :func:`.convertFontInfoValueForAttributeFromVersion3ToVersion2`
"""

from __future__ import annotations

import enum
import logging
import os
import zipfile
from collections import OrderedDict
from copy import deepcopy
from os import fsdecode
from typing import IO, TYPE_CHECKING, Any, Optional, Union, cast

from fontTools.misc import filesystem as fs
from fontTools.misc import plistlib
from fontTools.ufoLib.converters import convertUFO1OrUFO2KerningToUFO3Kerning
from fontTools.ufoLib.errors import UFOLibError
from fontTools.ufoLib.filenames import userNameToFileName
from fontTools.ufoLib.utils import (
    BaseFormatVersion,
    normalizeFormatVersion,
    numberTypes,
)
from fontTools.ufoLib.validators import *

if TYPE_CHECKING:
    from logging import Logger

    from fontTools.annotations import (
        GlyphNameToFileNameFunc,
        K,
        KerningDict,
        KerningGroups,
        KerningNested,
        PathOrFS,
        PathStr,
        UFOFormatVersionInput,
        V,
    )
    from fontTools.misc.filesystem._base import FS
    from fontTools.ufoLib.glifLib import GlyphSet

KerningGroupRenameMaps = dict[str, dict[str, str]]
LibDict = dict[str, Any]
LayerOrderList = Optional[list[Optional[str]]]
AttributeDataDict = dict[str, Any]
FontInfoAttributes = dict[str, AttributeDataDict]

# client code can check this to see if the upstream `fs` package is being used
haveFS = fs._haveFS

__all__: list[str] = [
    "haveFS",
    "makeUFOPath",
    "UFOLibError",
    "UFOReader",
    "UFOWriter",
    "UFOReaderWriter",
    "UFOFileStructure",
    "fontInfoAttributesVersion1",
    "fontInfoAttributesVersion2",
    "fontInfoAttributesVersion3",
    "deprecatedFontInfoAttributesVersion2",
    "validateFontInfoVersion2ValueForAttribute",
    "validateFontInfoVersion3ValueForAttribute",
    "convertFontInfoValueForAttributeFromVersion1ToVersion2",
    "convertFontInfoValueForAttributeFromVersion2ToVersion1",
]

__version__: str = "3.0.0"


logger: Logger = logging.getLogger(__name__)


# ---------
# Constants
# ---------

DEFAULT_GLYPHS_DIRNAME: str = "glyphs"
DATA_DIRNAME: str = "data"
IMAGES_DIRNAME: str = "images"
METAINFO_FILENAME: str = "metainfo.plist"
FONTINFO_FILENAME: str = "fontinfo.plist"
LIB_FILENAME: str = "lib.plist"
GROUPS_FILENAME: str = "groups.plist"
KERNING_FILENAME: str = "kerning.plist"
FEATURES_FILENAME: str = "features.fea"
LAYERCONTENTS_FILENAME: str = "layercontents.plist"
LAYERINFO_FILENAME: str = "layerinfo.plist"

DEFAULT_LAYER_NAME: str = "public.default"


class UFOFormatVersion(BaseFormatVersion):
    FORMAT_1_0 = (1, 0)
    FORMAT_2_0 = (2, 0)
    FORMAT_3_0 = (3, 0)


class UFOFileStructure(enum.Enum):
    ZIP = "zip"
    PACKAGE = "package"


# --------------
# Shared Methods
# --------------


class _UFOBaseIO:
    if TYPE_CHECKING:
        fs: FS
        _havePreviousFile: bool

    def getFileModificationTime(self, path: PathStr) -> Optional[float]:
        """
        Returns the modification time for the file at the given path, as a
        floating point number giving the number of seconds since the epoch.
        The path must be relative to the UFO path.
        Returns None if the file does not exist.
        """
        try:
            dt = self.fs.getinfo(fsdecode(path), namespaces=["details"]).modified
        except (fs.errors.MissingInfoNamespace, fs.errors.ResourceNotFound):
            return None
        else:
            if dt is not None:
                return dt.timestamp()
            return None

    def _getPlist(self, fileName: str, default: Optional[Any] = None) -> Any:
        """
        Read a property list relative to the UFO filesystem's root.
        Raises UFOLibError if the file is missing and default is None,
        otherwise default is returned.

        The errors that could be raised during the reading of a plist are
        unpredictable and/or too large to list, so, a blind try: except:
        is done. If an exception occurs, a UFOLibError will be raised.
        """
        try:
            with self.fs.open(fileName, "rb") as f:
                return plistlib.load(f)
        except fs.errors.ResourceNotFound:
            if default is None:
                raise UFOLibError(
                    "'%s' is missing on %s. This file is required" % (fileName, self.fs)
                )
            else:
                return default
        except Exception as e:
            # TODO(anthrotype): try to narrow this down a little
            raise UFOLibError(f"'{fileName}' could not be read on {self.fs}: {e}")

    def _writePlist(self, fileName: str, obj: Any) -> None:
        """
        Write a property list to a file relative to the UFO filesystem's root.

        Do this sort of atomically, making it harder to corrupt existing files,
        for example when plistlib encounters an error halfway during write.
        This also checks to see if text matches the text that is already in the
        file at path. If so, the file is not rewritten so that the modification
        date is preserved.

        The errors that could be raised during the writing of a plist are
        unpredictable and/or too large to list, so, a blind try: except: is done.
        If an exception occurs, a UFOLibError will be raised.
        """
        if self._havePreviousFile:
            try:
                data = plistlib.dumps(obj)
            except Exception as e:
                raise UFOLibError(
                    "'%s' could not be written on %s because "
                    "the data is not properly formatted: %s" % (fileName, self.fs, e)
                )
            if self.fs.exists(fileName) and data == self.fs.readbytes(fileName):
                return
            self.fs.writebytes(fileName, data)
        else:
            with self.fs.open(fileName, mode="wb") as fp:
                try:
                    plistlib.dump(obj, fp)
                except Exception as e:
                    raise UFOLibError(
                        "'%s' could not be written on %s because "
                        "the data is not properly formatted: %s"
                        % (fileName, self.fs, e)
                    )


# ----------
# UFO Reader
# ----------


class UFOReader(_UFOBaseIO):
    """Read the various components of a .ufo.

    Attributes:
        path: An :class:`os.PathLike` object pointing to the .ufo.
        validate: A boolean indicating if the data read should be
          validated. Defaults to `True`.

    By default read data is validated. Set ``validate`` to
    ``False`` to not validate the data.
    """

    def __init__(self, path: PathOrFS, validate: bool = True) -> None:
        # Only call __fspath__ if path is not already a str or FS object
        if not isinstance(path, (str, fs.base.FS)) and hasattr(path, "__fspath__"):
            path = path.__fspath__()

        if isinstance(path, str):
            structure = _sniffFileStructure(path)
            parentFS: FS
            try:
                if structure is UFOFileStructure.ZIP:
                    parentFS = fs.zipfs.ZipFS(path, write=False, encoding="utf-8")  # type: ignore[abstract]
                else:
                    parentFS = fs.osfs.OSFS(path)
            except fs.errors.CreateFailed as e:
                raise UFOLibError(f"unable to open '{path}': {e}")

            if structure is UFOFileStructure.ZIP:
                # .ufoz zip files must contain a single root directory, with arbitrary
                # name, containing all the UFO files
                rootDirs = [
                    p.name
                    for p in parentFS.scandir("/")
                    # exclude macOS metadata contained in zip file
                    if p.is_dir and p.name != "__MACOSX"
                ]
                if len(rootDirs) == 1:
                    # 'ClosingSubFS' ensures that the parent zip file is closed when
                    # its root subdirectory is closed
                    self.fs: FS = parentFS.opendir(
                        rootDirs[0], factory=fs.subfs.ClosingSubFS
                    )
                else:
                    raise UFOLibError(
                        "Expected exactly 1 root directory, found %d" % len(rootDirs)
                    )
            else:
                # normal UFO 'packages' are just a single folder
                self.fs = parentFS
            # when passed a path string, we make sure we close the newly opened fs
            # upon calling UFOReader.close method or context manager's __exit__
            self._shouldClose: bool = True
            self._fileStructure = structure
        elif isinstance(path, fs.base.FS):
            filesystem: FS = path
            try:
                filesystem.check()
            except fs.errors.FilesystemClosed:
                raise UFOLibError("the filesystem '%s' is closed" % path)
            else:
                self.fs = filesystem
            try:
                path = filesystem.getsyspath("/")
            except fs.errors.NoSysPath:
                # network or in-memory FS may not map to the local one
                path = str(filesystem)
            # when user passed an already initialized fs instance, it is her
            # responsibility to close it, thus UFOReader.close/__exit__ are no-op
            self._shouldClose = False
            # default to a 'package' structure
            self._fileStructure = UFOFileStructure.PACKAGE
        else:
            raise TypeError(
                "Expected a path string or fs.base.FS object, found '%s'"
                % type(path).__name__
            )
        self._path: str = fsdecode(path)
        self._validate: bool = validate
        self._upConvertedKerningData: Optional[dict[str, Any]] = None

        try:
            self.readMetaInfo(validate=validate)
        except UFOLibError:
            self.close()
            raise

    # properties

    def _get_path(self) -> str:
        import warnings

        warnings.warn(
            "The 'path' attribute is deprecated; use the 'fs' attribute instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._path

    path: property = property(_get_path, doc="The path of the UFO (DEPRECATED).")

    def _get_formatVersion(self) -> int:
        import warnings

        warnings.warn(
            "The 'formatVersion' attribute is deprecated; use the 'formatVersionTuple'",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._formatVersion.major

    formatVersion = property(
        _get_formatVersion,
        doc="The (major) format version of the UFO. DEPRECATED: Use formatVersionTuple",
    )

    @property
    def formatVersionTuple(self) -> tuple[int, int]:
        """The (major, minor) format version of the UFO.
        This is determined by reading metainfo.plist during __init__.
        """
        return self._formatVersion

    def _get_fileStructure(self) -> Any:
        return self._fileStructure

    fileStructure: property = property(
        _get_fileStructure,
        doc=(
            "The file structure of the UFO: "
            "either UFOFileStructure.ZIP or UFOFileStructure.PACKAGE"
        ),
    )

    # up conversion

    def _upConvertKerning(self, validate: bool) -> None:
        """
        Up convert kerning and groups in UFO 1 and 2.
        The data will be held internally until each bit of data
        has been retrieved. The conversion of both must be done
        at once, so the raw data is cached and an error is raised
        if one bit of data becomes obsolete before it is called.

        ``validate`` will validate the data.
        """
        if self._upConvertedKerningData:
            testKerning = self._readKerning()
            if testKerning != self._upConvertedKerningData["originalKerning"]:
                raise UFOLibError(
                    "The data in kerning.plist has been modified since it was converted to UFO 3 format."
                )
            testGroups = self._readGroups()
            if testGroups != self._upConvertedKerningData["originalGroups"]:
                raise UFOLibError(
                    "The data in groups.plist has been modified since it was converted to UFO 3 format."
                )
        else:
            groups = self._readGroups()
            if validate:
                invalidFormatMessage = "groups.plist is not properly formatted."
                if not isinstance(groups, dict):
                    raise UFOLibError(invalidFormatMessage)
                for groupName, glyphList in groups.items():
                    if not isinstance(groupName, str):
                        raise UFOLibError(invalidFormatMessage)
                    elif not isinstance(glyphList, list):
                        raise UFOLibError(invalidFormatMessage)
                    for glyphName in glyphList:
                        if not isinstance(glyphName, str):
                            raise UFOLibError(invalidFormatMessage)
            self._upConvertedKerningData = dict(
                kerning={},
                originalKerning=self._readKerning(),
                groups={},
                originalGroups=groups,
            )
            # convert kerning and groups
            kerning, groups, conversionMaps = convertUFO1OrUFO2KerningToUFO3Kerning(
                self._upConvertedKerningData["originalKerning"],
                deepcopy(self._upConvertedKerningData["originalGroups"]),
                self.getGlyphSet(),
            )
            # store
            self._upConvertedKerningData["kerning"] = kerning
            self._upConvertedKerningData["groups"] = groups
            self._upConvertedKerningData["groupRenameMaps"] = conversionMaps

    # support methods

    def readBytesFromPath(self, path: PathStr) -> Optional[bytes]:
        """
        Returns the bytes in the file at the given path.
        The path must be relative to the UFO's filesystem root.
        Returns None if the file does not exist.
        """
        try:
            return self.fs.readbytes(fsdecode(path))
        except fs.errors.ResourceNotFound:
            return None

    def getReadFileForPath(
        self, path: PathStr, encoding: Optional[str] = None
    ) -> Optional[Union[IO[bytes], IO[str]]]:
        """
        Returns a file (or file-like) object for the file at the given path.
        The path must be relative to the UFO path.
        Returns None if the file does not exist.
        By default the file is opened in binary mode (reads bytes).
        If encoding is passed, the file is opened in text mode (reads str).

        Note: The caller is responsible for closing the open file.
        """
        path = fsdecode(path)
        try:
            if encoding is None:
                return self.fs.open(path, mode="rb")
            else:
                return self.fs.open(path, mode="r", encoding=encoding)
        except fs.errors.ResourceNotFound:
            return None

    # metainfo.plist

    def _readMetaInfo(self, validate: Optional[bool] = None) -> dict[str, Any]:
        """
        Read metainfo.plist and return raw data. Only used for internal operations.

        ``validate`` will validate the read data, by default it is set
        to the class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        data = self._getPlist(METAINFO_FILENAME)
        if validate and not isinstance(data, dict):
            raise UFOLibError("metainfo.plist is not properly formatted.")
        try:
            formatVersionMajor = data["formatVersion"]
        except KeyError:
            raise UFOLibError(
                f"Missing required formatVersion in '{METAINFO_FILENAME}' on {self.fs}"
            )
        formatVersionMinor = data.setdefault("formatVersionMinor", 0)

        try:
            formatVersion = UFOFormatVersion((formatVersionMajor, formatVersionMinor))
        except ValueError as e:
            unsupportedMsg = (
                f"Unsupported UFO format ({formatVersionMajor}.{formatVersionMinor}) "
                f"in '{METAINFO_FILENAME}' on {self.fs}"
            )
            if validate:
                from fontTools.ufoLib.errors import UnsupportedUFOFormat

                raise UnsupportedUFOFormat(unsupportedMsg) from e

            formatVersion = UFOFormatVersion.default()
            logger.warning(
                "%s. Assuming the latest supported version (%s). "
                "Some data may be skipped or parsed incorrectly",
                unsupportedMsg,
                formatVersion,
            )
        data["formatVersionTuple"] = formatVersion
        return data

    def readMetaInfo(self, validate: Optional[bool] = None) -> None:
        """
        Read metainfo.plist and set formatVersion. Only used for internal operations.

        ``validate`` will validate the read data, by default it is set
        to the class's validate value, can be overridden.
        """
        data = self._readMetaInfo(validate=validate)
        self._formatVersion = data["formatVersionTuple"]

    # groups.plist

    def _readGroups(self) -> dict[str, list[str]]:
        groups = self._getPlist(GROUPS_FILENAME, {})
        # remove any duplicate glyphs in a kerning group
        for groupName, glyphList in groups.items():
            if groupName.startswith(("public.kern1.", "public.kern2.")):
                groups[groupName] = list(OrderedDict.fromkeys(glyphList))
        return groups

    def readGroups(self, validate: Optional[bool] = None) -> dict[str, list[str]]:
        """
        Read groups.plist. Returns a dict.
        ``validate`` will validate the read data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        # handle up conversion
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            self._upConvertKerning(validate)
            groups = cast(dict, self._upConvertedKerningData)["groups"]
        # normal
        else:
            groups = self._readGroups()
        if validate:
            valid, message = groupsValidator(groups)
            if not valid:
                raise UFOLibError(message)
        return groups

    def getKerningGroupConversionRenameMaps(
        self, validate: Optional[bool] = None
    ) -> KerningGroupRenameMaps:
        """
        Get maps defining the renaming that was done during any
        needed kerning group conversion. This method returns a
        dictionary of this form::

                {
                        "side1" : {"old group name" : "new group name"},
                        "side2" : {"old group name" : "new group name"}
                }

        When no conversion has been performed, the side1 and side2
        dictionaries will be empty.

        ``validate`` will validate the groups, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        if self._formatVersion >= UFOFormatVersion.FORMAT_3_0:
            return dict(side1={}, side2={})
        # use the public group reader to force the load and
        # conversion of the data if it hasn't happened yet.
        self.readGroups(validate=validate)
        return cast(dict, self._upConvertedKerningData)["groupRenameMaps"]

    # fontinfo.plist

    def _readInfo(self, validate: bool) -> dict[str, Any]:
        data = self._getPlist(FONTINFO_FILENAME, {})
        if validate and not isinstance(data, dict):
            raise UFOLibError("fontinfo.plist is not properly formatted.")
        return data

    def readInfo(self, info: Any, validate: Optional[bool] = None) -> None:
        """
        Read fontinfo.plist. It requires an object that allows
        setting attributes with names that follow the fontinfo.plist
        version 3 specification. This will write the attributes
        defined in the file into the object.

        ``validate`` will validate the read data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        infoDict = self._readInfo(validate)
        infoDataToSet = {}
        # version 1
        if self._formatVersion == UFOFormatVersion.FORMAT_1_0:
            for attr in fontInfoAttributesVersion1:
                value = infoDict.get(attr)
                if value is not None:
                    infoDataToSet[attr] = value
            infoDataToSet = _convertFontInfoDataVersion1ToVersion2(infoDataToSet)
            infoDataToSet = _convertFontInfoDataVersion2ToVersion3(infoDataToSet)
        # version 2
        elif self._formatVersion == UFOFormatVersion.FORMAT_2_0:
            for attr, dataValidationDict in list(
                fontInfoAttributesVersion2ValueData.items()
            ):
                value = infoDict.get(attr)
                if value is None:
                    continue
                infoDataToSet[attr] = value
            infoDataToSet = _convertFontInfoDataVersion2ToVersion3(infoDataToSet)
        # version 3.x
        elif self._formatVersion.major == UFOFormatVersion.FORMAT_3_0.major:
            for attr, dataValidationDict in list(
                fontInfoAttributesVersion3ValueData.items()
            ):
                value = infoDict.get(attr)
                if value is None:
                    continue
                infoDataToSet[attr] = value
        # unsupported version
        else:
            raise NotImplementedError(self._formatVersion)
        # validate data
        if validate:
            infoDataToSet = validateInfoVersion3Data(infoDataToSet)
        # populate the object
        for attr, value in list(infoDataToSet.items()):
            try:
                setattr(info, attr, value)
            except AttributeError:
                raise UFOLibError(
                    "The supplied info object does not support setting a necessary attribute (%s)."
                    % attr
                )

    # kerning.plist

    def _readKerning(self) -> KerningNested:
        data = self._getPlist(KERNING_FILENAME, {})
        return data

    def readKerning(self, validate: Optional[bool] = None) -> KerningDict:
        """
        Read kerning.plist. Returns a dict.

        ``validate`` will validate the kerning data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        # handle up conversion
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            self._upConvertKerning(validate)
            kerningNested = cast(dict, self._upConvertedKerningData)["kerning"]
        # normal
        else:
            kerningNested = self._readKerning()
        if validate:
            valid, message = kerningValidator(kerningNested)
            if not valid:
                raise UFOLibError(message)
        # flatten
        kerning = {}
        for left in kerningNested:
            for right in kerningNested[left]:
                value = kerningNested[left][right]
                kerning[left, right] = value
        return kerning

    # lib.plist

    def readLib(self, validate: Optional[bool] = None) -> dict[str, Any]:
        """
        Read lib.plist. Returns a dict.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        data = self._getPlist(LIB_FILENAME, {})
        if validate:
            valid, message = fontLibValidator(data)
            if not valid:
                raise UFOLibError(message)
        return data

    # features.fea

    def readFeatures(self) -> str:
        """
        Read features.fea. Return a string.
        The returned string is empty if the file is missing.
        """
        try:
            with self.fs.open(FEATURES_FILENAME, "r", encoding="utf-8-sig") as f:
                return f.read()
        except fs.errors.ResourceNotFound:
            return ""

    # glyph sets & layers

    def _readLayerContents(self, validate: bool) -> list[tuple[str, str]]:
        """
        Rebuild the layer contents list by checking what glyphsets
        are available on disk.

        ``validate`` will validate the layer contents.
        """
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            return [(DEFAULT_LAYER_NAME, DEFAULT_GLYPHS_DIRNAME)]
        contents = self._getPlist(LAYERCONTENTS_FILENAME)
        if validate:
            valid, error = layerContentsValidator(contents, self.fs)
            if not valid:
                raise UFOLibError(error)
        return contents

    def getLayerNames(self, validate: Optional[bool] = None) -> list[str]:
        """
        Get the ordered layer names from layercontents.plist.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        layerContents = self._readLayerContents(validate)
        layerNames = [layerName for layerName, directoryName in layerContents]
        return layerNames

    def getDefaultLayerName(self, validate: Optional[bool] = None) -> str:
        """
        Get the default layer name from layercontents.plist.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        layerContents = self._readLayerContents(validate)
        for layerName, layerDirectory in layerContents:
            if layerDirectory == DEFAULT_GLYPHS_DIRNAME:
                return layerName
        # this will already have been raised during __init__
        raise UFOLibError("The default layer is not defined in layercontents.plist.")

    def getGlyphSet(
        self,
        layerName: Optional[str] = None,
        validateRead: Optional[bool] = None,
        validateWrite: Optional[bool] = None,
    ) -> GlyphSet:
        """
        Return the GlyphSet associated with the
        glyphs directory mapped to layerName
        in the UFO. If layerName is not provided,
        the name retrieved with getDefaultLayerName
        will be used.

        ``validateRead`` will validate the read data, by default it is set to the
        class's validate value, can be overridden.
        ``validateWrite`` will validate the written data, by default it is set to the
        class's validate value, can be overridden.
        """
        from fontTools.ufoLib.glifLib import GlyphSet

        if validateRead is None:
            validateRead = self._validate
        if validateWrite is None:
            validateWrite = self._validate
        if layerName is None:
            layerName = self.getDefaultLayerName(validate=validateRead)
        directory = None
        layerContents = self._readLayerContents(validateRead)
        for storedLayerName, storedLayerDirectory in layerContents:
            if layerName == storedLayerName:
                directory = storedLayerDirectory
                break
        if directory is None:
            raise UFOLibError('No glyphs directory is mapped to "%s".' % layerName)
        try:
            glyphSubFS = self.fs.opendir(directory)
        except fs.errors.ResourceNotFound:
            raise UFOLibError(f"No '{directory}' directory for layer '{layerName}'")
        return GlyphSet(
            glyphSubFS,
            ufoFormatVersion=self._formatVersion,
            validateRead=validateRead,
            validateWrite=validateWrite,
            expectContentsFile=True,
        )

    def getCharacterMapping(
        self, layerName: Optional[str] = None, validate: Optional[bool] = None
    ) -> dict[int, list[str]]:
        """
        Return a dictionary that maps unicode values (ints) to
        lists of glyph names.
        """
        if validate is None:
            validate = self._validate
        glyphSet = self.getGlyphSet(
            layerName, validateRead=validate, validateWrite=True
        )
        allUnicodes = glyphSet.getUnicodes()
        cmap: dict[int, list[str]] = {}
        for glyphName, unicodes in allUnicodes.items():
            for code in unicodes:
                if code in cmap:
                    cmap[code].append(glyphName)
                else:
                    cmap[code] = [glyphName]
        return cmap

    # /data

    def getDataDirectoryListing(self) -> list[str]:
        """
        Returns a list of all files in the data directory.
        The returned paths will be relative to the UFO.
        This will not list directory names, only file names.
        Thus, empty directories will be skipped.
        """
        try:
            self._dataFS = self.fs.opendir(DATA_DIRNAME)
        except fs.errors.ResourceNotFound:
            return []
        except fs.errors.DirectoryExpected:
            raise UFOLibError('The UFO contains a "data" file instead of a directory.')
        try:
            # fs Walker.files method returns "absolute" paths (in terms of the
            # root of the 'data' SubFS), so we strip the leading '/' to make
            # them relative
            return [p.lstrip("/") for p in self._dataFS.walk.files()]
        except fs.errors.ResourceError:
            return []

    def getImageDirectoryListing(self, validate: Optional[bool] = None) -> list[str]:
        """
        Returns a list of all image file names in
        the images directory. Each of the images will
        have been verified to have the PNG signature.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            return []
        if validate is None:
            validate = self._validate
        try:
            self._imagesFS = imagesFS = self.fs.opendir(IMAGES_DIRNAME)
        except fs.errors.ResourceNotFound:
            return []
        except fs.errors.DirectoryExpected:
            raise UFOLibError(
                'The UFO contains an "images" file instead of a directory.'
            )
        result = []
        for path in imagesFS.scandir("/"):
            if path.is_dir:
                # silently skip this as version control
                # systems often have hidden directories
                continue
            if validate:
                with imagesFS.open(path.name, "rb") as fp:
                    valid, error = pngValidator(fileObj=fp)
                if valid:
                    result.append(path.name)
            else:
                result.append(path.name)
        return result

    def readData(self, fileName: PathStr) -> bytes:
        """
        Return bytes for the file named 'fileName' inside the 'data/' directory.
        """
        fileName = fsdecode(fileName)
        try:
            try:
                dataFS = self._dataFS
            except AttributeError:
                # in case readData is called before getDataDirectoryListing
                dataFS = self.fs.opendir(DATA_DIRNAME)
            data = dataFS.readbytes(fileName)
        except fs.errors.ResourceNotFound:
            raise UFOLibError(f"No data file named '{fileName}' on {self.fs}")
        return data

    def readImage(self, fileName: PathStr, validate: Optional[bool] = None) -> bytes:
        """
        Return image data for the file named fileName.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            raise UFOLibError(
                f"Reading images is not allowed in UFO {self._formatVersion.major}."
            )
        fileName = fsdecode(fileName)
        try:
            try:
                imagesFS = self._imagesFS
            except AttributeError:
                # in case readImage is called before getImageDirectoryListing
                imagesFS = self.fs.opendir(IMAGES_DIRNAME)
            data = imagesFS.readbytes(fileName)
        except fs.errors.ResourceNotFound:
            raise UFOLibError(f"No image file named '{fileName}' on {self.fs}")
        if validate:
            valid, error = pngValidator(data=data)
            if not valid:
                raise UFOLibError(error)
        return data

    def close(self) -> None:
        if self._shouldClose:
            self.fs.close()

    def __enter__(self) -> UFOReader:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        self.close()


# ----------
# UFO Writer
# ----------


class UFOWriter(UFOReader):
    """Write the various components of a .ufo.

    Attributes:
        path: An :class:`os.PathLike` object pointing to the .ufo.
        formatVersion: the UFO format version as a tuple of integers (major, minor),
            or as a single integer for the major digit only (minor is implied to be 0).
            By default, the latest formatVersion will be used; currently it is 3.0,
            which is equivalent to formatVersion=(3, 0).
        fileCreator: The creator of the .ufo file. Defaults to
            `com.github.fonttools.ufoLib`.
        structure: The internal structure of the .ufo file: either `ZIP` or `PACKAGE`.
        validate: A boolean indicating if the data read should be validated. Defaults
            to `True`.

    By default, the written data will be validated before writing. Set ``validate`` to
    ``False`` if you do not want to validate the data. Validation can also be overriden
    on a per-method level if desired.

    Raises:
        UnsupportedUFOFormat: An exception indicating that the requested UFO
            formatVersion is not supported.
    """

    def __init__(
        self,
        path: PathOrFS,
        formatVersion: UFOFormatVersionInput = None,
        fileCreator: str = "com.github.fonttools.ufoLib",
        structure: Optional[UFOFileStructure] = None,
        validate: bool = True,
    ) -> None:
        try:
            formatVersion = normalizeFormatVersion(formatVersion, UFOFormatVersion)
        except ValueError as e:
            from fontTools.ufoLib.errors import UnsupportedUFOFormat

            raise UnsupportedUFOFormat(
                f"Unsupported UFO format: {formatVersion!r}"
            ) from e

        if hasattr(path, "__fspath__"):  # support os.PathLike objects
            path = path.__fspath__()

        if isinstance(path, str):
            # normalize path by removing trailing or double slashes
            path = os.path.normpath(path)
            havePreviousFile = os.path.exists(path)
            if havePreviousFile:
                # ensure we use the same structure as the destination
                existingStructure = _sniffFileStructure(path)
                if structure is not None:
                    try:
                        structure = UFOFileStructure(structure)
                    except ValueError:
                        raise UFOLibError(
                            "Invalid or unsupported structure: '%s'" % structure
                        )
                    if structure is not existingStructure:
                        raise UFOLibError(
                            "A UFO with a different structure (%s) already exists "
                            "at the given path: '%s'" % (existingStructure, path)
                        )
                else:
                    structure = existingStructure
            else:
                # if not exists, default to 'package' structure
                if structure is None:
                    structure = UFOFileStructure.PACKAGE
                dirName = os.path.dirname(path)
                if dirName and not os.path.isdir(dirName):
                    raise UFOLibError(
                        "Cannot write to '%s': directory does not exist" % path
                    )
            if structure is UFOFileStructure.ZIP:
                if havePreviousFile:
                    # we can't write a zip in-place, so we have to copy its
                    # contents to a temporary location and work from there, then
                    # upon closing UFOWriter we create the final zip file
                    parentFS: FS = fs.tempfs.TempFS()
                    with fs.zipfs.ZipFS(path, encoding="utf-8") as origFS:  # type: ignore[abstract]
                        fs.copy.copy_fs(origFS, parentFS)
                    # if output path is an existing zip, we require that it contains
                    # one, and only one, root directory (with arbitrary name), in turn
                    # containing all the existing UFO contents
                    rootDirs = [
                        p.name
                        for p in parentFS.scandir("/")
                        # exclude macOS metadata contained in zip file
                        if p.is_dir and p.name != "__MACOSX"
                    ]
                    if len(rootDirs) != 1:
                        raise UFOLibError(
                            "Expected exactly 1 root directory, found %d"
                            % len(rootDirs)
                        )
                    else:
                        rootDir = rootDirs[0]
                else:
                    # if the output zip file didn't exist, we create the root folder;
                    # we name it the same as input 'path', but with '.ufo' extension
                    rootDir = os.path.splitext(os.path.basename(path))[0] + ".ufo"
                    parentFS = fs.zipfs.ZipFS(path, write=True, encoding="utf-8")  # type: ignore[abstract]
                    parentFS.makedir(rootDir)
                # 'ClosingSubFS' ensures that the parent filesystem is closed
                # when its root subdirectory is closed
                self.fs = parentFS.opendir(rootDir, factory=fs.subfs.ClosingSubFS)
            else:
                self.fs = fs.osfs.OSFS(path, create=True)
            self._fileStructure = structure
            self._havePreviousFile = havePreviousFile
            self._shouldClose = True
        elif isinstance(path, fs.base.FS):
            filesystem: FS = path
            try:
                filesystem.check()
            except fs.errors.FilesystemClosed:
                raise UFOLibError("the filesystem '%s' is closed" % path)
            else:
                self.fs = filesystem
            try:
                path = filesystem.getsyspath("/")
            except fs.errors.NoSysPath:
                # network or in-memory FS may not map to the local one
                path = str(filesystem)
            # if passed an FS object, always use 'package' structure
            if structure and structure is not UFOFileStructure.PACKAGE:
                import warnings

                warnings.warn(
                    "The 'structure' argument is not used when input is an FS object",
                    UserWarning,
                    stacklevel=2,
                )
            self._fileStructure = UFOFileStructure.PACKAGE
            # if FS contains a "metainfo.plist", we consider it non-empty
            self._havePreviousFile = filesystem.exists(METAINFO_FILENAME)
            # the user is responsible for closing the FS object
            self._shouldClose = False
        else:
            raise TypeError(
                "Expected a path string or fs object, found %s" % type(path).__name__
            )

        # establish some basic stuff
        self._path = fsdecode(path)
        self._formatVersion = formatVersion
        self._fileCreator = fileCreator
        self._downConversionKerningData: Optional[KerningGroupRenameMaps] = None
        self._validate = validate
        # if the file already exists, get the format version.
        # this will be needed for up and down conversion.
        previousFormatVersion = None
        if self._havePreviousFile:
            metaInfo = self._readMetaInfo(validate=validate)
            previousFormatVersion = metaInfo["formatVersionTuple"]
            # catch down conversion
            if previousFormatVersion > formatVersion:
                from fontTools.ufoLib.errors import UnsupportedUFOFormat

                raise UnsupportedUFOFormat(
                    "The UFO located at this path is a higher version "
                    f"({previousFormatVersion}) than the version ({formatVersion}) "
                    "that is trying to be written. This is not supported."
                )
        # handle the layer contents
        self.layerContents: Union[dict[str, str], OrderedDict[str, str]] = {}
        if previousFormatVersion is not None and previousFormatVersion.major >= 3:
            # already exists
            self.layerContents = OrderedDict(self._readLayerContents(validate))
        else:
            # previous < 3
            # imply the layer contents
            if self.fs.exists(DEFAULT_GLYPHS_DIRNAME):
                self.layerContents = {DEFAULT_LAYER_NAME: DEFAULT_GLYPHS_DIRNAME}
        # write the new metainfo
        self._writeMetaInfo()

    # properties

    def _get_fileCreator(self) -> str:
        return self._fileCreator

    fileCreator: property = property(
        _get_fileCreator,
        doc="The file creator of the UFO. This is set into metainfo.plist during __init__.",
    )

    # support methods for file system interaction

    def copyFromReader(
        self, reader: UFOReader, sourcePath: PathStr, destPath: PathStr
    ) -> None:
        """
        Copy the sourcePath in the provided UFOReader to destPath
        in this writer. The paths must be relative. This works with
        both individual files and directories.
        """
        if not isinstance(reader, UFOReader):
            raise UFOLibError("The reader must be an instance of UFOReader.")
        sourcePath = fsdecode(sourcePath)
        destPath = fsdecode(destPath)
        if not reader.fs.exists(sourcePath):
            raise UFOLibError(
                'The reader does not have data located at "%s".' % sourcePath
            )
        if self.fs.exists(destPath):
            raise UFOLibError('A file named "%s" already exists.' % destPath)
        # create the destination directory if it doesn't exist
        self.fs.makedirs(fs.path.dirname(destPath), recreate=True)
        if reader.fs.isdir(sourcePath):
            fs.copy.copy_dir(reader.fs, sourcePath, self.fs, destPath)
        else:
            fs.copy.copy_file(reader.fs, sourcePath, self.fs, destPath)

    def writeBytesToPath(self, path: PathStr, data: bytes) -> None:
        """
        Write bytes to a path relative to the UFO filesystem's root.
        If writing to an existing UFO, check to see if data matches the data
        that is already in the file at path; if so, the file is not rewritten
        so that the modification date is preserved.
        If needed, the directory tree for the given path will be built.
        """
        path = fsdecode(path)
        if self._havePreviousFile:
            if self.fs.isfile(path) and data == self.fs.readbytes(path):
                return
        try:
            self.fs.writebytes(path, data)
        except fs.errors.FileExpected:
            raise UFOLibError("A directory exists at '%s'" % path)
        except fs.errors.ResourceNotFound:
            self.fs.makedirs(fs.path.dirname(path), recreate=True)
            self.fs.writebytes(path, data)

    def getFileObjectForPath(
        self,
        path: PathStr,
        mode: str = "w",
        encoding: Optional[str] = None,
    ) -> Optional[IO[Any]]:
        """
        Returns a file (or file-like) object for the
        file at the given path. The path must be relative
        to the UFO path. Returns None if the file does
        not exist and the mode is "r" or "rb.
        An encoding may be passed if the file is opened in text mode.

        Note: The caller is responsible for closing the open file.
        """
        path = fsdecode(path)
        try:
            return self.fs.open(path, mode=mode, encoding=encoding)
        except fs.errors.ResourceNotFound as e:
            m = mode[0]
            if m == "r":
                # XXX I think we should just let it raise. The docstring,
                # however, says that this returns None if mode is 'r'
                return None
            elif m == "w" or m == "a" or m == "x":
                self.fs.makedirs(fs.path.dirname(path), recreate=True)
                return self.fs.open(path, mode=mode, encoding=encoding)
        except fs.errors.ResourceError as e:
            raise UFOLibError(f"unable to open '{path}' on {self.fs}: {e}")
        return None

    def removePath(
        self, path: PathStr, force: bool = False, removeEmptyParents: bool = True
    ) -> None:
        """
        Remove the file (or directory) at path. The path
        must be relative to the UFO.
        Raises UFOLibError if the path doesn't exist.
        If force=True, ignore non-existent paths.
        If the directory where 'path' is located becomes empty, it will
        be automatically removed, unless 'removeEmptyParents' is False.
        """
        path = fsdecode(path)
        try:
            self.fs.remove(path)
        except fs.errors.FileExpected:
            self.fs.removetree(path)
        except fs.errors.ResourceNotFound:
            if not force:
                raise UFOLibError(f"'{path}' does not exist on {self.fs}")
        if removeEmptyParents:
            parent = fs.path.dirname(path)
            if parent:
                fs.tools.remove_empty(self.fs, parent)

    # alias kept for backward compatibility with old API
    removeFileForPath = removePath

    # UFO mod time

    def setModificationTime(self) -> None:
        """
        Set the UFO modification time to the current time.
        This is never called automatically. It is up to the
        caller to call this when finished working on the UFO.
        """
        path = self._path
        if path is not None and os.path.exists(path):
            try:
                # this may fail on some filesystems (e.g. SMB servers)
                os.utime(path, None)
            except OSError as e:
                logger.warning("Failed to set modified time: %s", e)

    # metainfo.plist

    def _writeMetaInfo(self) -> None:
        metaInfo = dict(
            creator=self._fileCreator,
            formatVersion=self._formatVersion.major,
        )
        if self._formatVersion.minor != 0:
            metaInfo["formatVersionMinor"] = self._formatVersion.minor
        self._writePlist(METAINFO_FILENAME, metaInfo)

    # groups.plist

    def setKerningGroupConversionRenameMaps(self, maps: KerningGroupRenameMaps) -> None:
        """
        Set maps defining the renaming that should be done
        when writing groups and kerning in UFO 1 and UFO 2.
        This will effectively undo the conversion done when
        UFOReader reads this data. The dictionary should have
        this form::

                {
                        "side1" : {"group name to use when writing" : "group name in data"},
                        "side2" : {"group name to use when writing" : "group name in data"}
                }

        This is the same form returned by UFOReader's
        getKerningGroupConversionRenameMaps method.
        """
        if self._formatVersion >= UFOFormatVersion.FORMAT_3_0:
            return  # XXX raise an error here
        # flip the dictionaries
        remap = {}
        for side in ("side1", "side2"):
            for writeName, dataName in list(maps[side].items()):
                remap[dataName] = writeName
        self._downConversionKerningData = dict(groupRenameMap=remap)

    def writeGroups(
        self, groups: KerningGroups, validate: Optional[bool] = None
    ) -> None:
        """
        Write groups.plist. This method requires a
        dict of glyph groups as an argument.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        # validate the data structure
        if validate:
            valid, message = groupsValidator(groups)
            if not valid:
                raise UFOLibError(message)
        # down convert
        if (
            self._formatVersion < UFOFormatVersion.FORMAT_3_0
            and self._downConversionKerningData is not None
        ):
            remap = self._downConversionKerningData["groupRenameMap"]
            remappedGroups = {}
            # there are some edge cases here that are ignored:
            # 1. if a group is being renamed to a name that
            #    already exists, the existing group is always
            #    overwritten. (this is why there are two loops
            #    below.) there doesn't seem to be a logical
            #    solution to groups mismatching and overwriting
            #    with the specifiecd group seems like a better
            #    solution than throwing an error.
            # 2. if side 1 and side 2 groups are being renamed
            #    to the same group name there is no check to
            #    ensure that the contents are identical. that
            #    is left up to the caller.
            for name, contents in list(groups.items()):
                if name in remap:
                    continue
                remappedGroups[name] = contents
            for name, contents in list(groups.items()):
                if name not in remap:
                    continue
                name = remap[name]
                remappedGroups[name] = contents
            groups = remappedGroups
        # pack and write
        groupsNew = {}
        for key, value in groups.items():
            groupsNew[key] = list(value)
        if groupsNew:
            self._writePlist(GROUPS_FILENAME, groupsNew)
        elif self._havePreviousFile:
            self.removePath(GROUPS_FILENAME, force=True, removeEmptyParents=False)

    # fontinfo.plist

    def writeInfo(self, info: Any, validate: Optional[bool] = None) -> None:
        """
        Write info.plist. This method requires an object
        that supports getting attributes that follow the
        fontinfo.plist version 2 specification. Attributes
        will be taken from the given object and written
        into the file.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        # gather version 3 data
        infoData = {}
        for attr in list(fontInfoAttributesVersion3ValueData.keys()):
            if hasattr(info, attr):
                try:
                    value = getattr(info, attr)
                except AttributeError:
                    raise UFOLibError(
                        "The supplied info object does not support getting a necessary attribute (%s)."
                        % attr
                    )
                if value is None:
                    continue
                infoData[attr] = value
        # down convert data if necessary and validate
        if self._formatVersion == UFOFormatVersion.FORMAT_3_0:
            if validate:
                infoData = validateInfoVersion3Data(infoData)
        elif self._formatVersion == UFOFormatVersion.FORMAT_2_0:
            infoData = _convertFontInfoDataVersion3ToVersion2(infoData)
            if validate:
                infoData = validateInfoVersion2Data(infoData)
        elif self._formatVersion == UFOFormatVersion.FORMAT_1_0:
            infoData = _convertFontInfoDataVersion3ToVersion2(infoData)
            if validate:
                infoData = validateInfoVersion2Data(infoData)
            infoData = _convertFontInfoDataVersion2ToVersion1(infoData)
        # write file if there is anything to write
        if infoData:
            self._writePlist(FONTINFO_FILENAME, infoData)

    # kerning.plist

    def writeKerning(
        self, kerning: KerningDict, validate: Optional[bool] = None
    ) -> None:
        """
        Write kerning.plist. This method requires a
        dict of kerning pairs as an argument.

        This performs basic structural validation of the kerning,
        but it does not check for compliance with the spec in
        regards to conflicting pairs. The assumption is that the
        kerning data being passed is standards compliant.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        # validate the data structure
        if validate:
            invalidFormatMessage = "The kerning is not properly formatted."
            if not isDictEnough(kerning):
                raise UFOLibError(invalidFormatMessage)
            for pair, value in list(kerning.items()):
                if not isinstance(pair, (list, tuple)):
                    raise UFOLibError(invalidFormatMessage)
                if not len(pair) == 2:
                    raise UFOLibError(invalidFormatMessage)
                if not isinstance(pair[0], str):
                    raise UFOLibError(invalidFormatMessage)
                if not isinstance(pair[1], str):
                    raise UFOLibError(invalidFormatMessage)
                if not isinstance(value, numberTypes):
                    raise UFOLibError(invalidFormatMessage)
        # down convert
        if (
            self._formatVersion < UFOFormatVersion.FORMAT_3_0
            and self._downConversionKerningData is not None
        ):
            remap = self._downConversionKerningData["groupRenameMap"]
            remappedKerning = {}
            for (side1, side2), value in list(kerning.items()):
                side1 = remap.get(side1, side1)
                side2 = remap.get(side2, side2)
                remappedKerning[side1, side2] = value
            kerning = remappedKerning
        # pack and write
        kerningDict: KerningNested = {}
        for left, right in kerning.keys():
            value = kerning[left, right]
            if left not in kerningDict:
                kerningDict[left] = {}
            kerningDict[left][right] = value
        if kerningDict:
            self._writePlist(KERNING_FILENAME, kerningDict)
        elif self._havePreviousFile:
            self.removePath(KERNING_FILENAME, force=True, removeEmptyParents=False)

    # lib.plist

    def writeLib(self, libDict: LibDict, validate: Optional[bool] = None) -> None:
        """
        Write lib.plist. This method requires a
        lib dict as an argument.

        ``validate`` will validate the data, by default it is set to the
        class's validate value, can be overridden.
        """
        if validate is None:
            validate = self._validate
        if validate:
            valid, message = fontLibValidator(libDict)
            if not valid:
                raise UFOLibError(message)
        if libDict:
            self._writePlist(LIB_FILENAME, libDict)
        elif self._havePreviousFile:
            self.removePath(LIB_FILENAME, force=True, removeEmptyParents=False)

    # features.fea

    def writeFeatures(self, features: str, validate: Optional[bool] = None) -> None:
        """
        Write features.fea. This method requires a
        features string as an argument.
        """
        if validate is None:
            validate = self._validate
        if self._formatVersion == UFOFormatVersion.FORMAT_1_0:
            raise UFOLibError("features.fea is not allowed in UFO Format Version 1.")
        if validate:
            if not isinstance(features, str):
                raise UFOLibError("The features are not text.")
        if features:
            self.writeBytesToPath(FEATURES_FILENAME, features.encode("utf8"))
        elif self._havePreviousFile:
            self.removePath(FEATURES_FILENAME, force=True, removeEmptyParents=False)

    # glyph sets & layers

    def writeLayerContents(
        self, layerOrder: LayerOrderList = None, validate: Optional[bool] = None
    ) -> None:
        """
        Write the layercontents.plist file. This method  *must* be called
        after all glyph sets have been written.
        """
        if validate is None:
            validate = self._validate
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            return
        if layerOrder is not None:
            newOrder: list[Optional[str]] = []
            for layerName in layerOrder:
                if layerName is None:
                    layerName = DEFAULT_LAYER_NAME
                newOrder.append(layerName)
            layerOrder = newOrder
        else:
            layerOrder = list(self.layerContents.keys())
        if validate and set(layerOrder) != set(self.layerContents.keys()):
            raise UFOLibError(
                "The layer order content does not match the glyph sets that have been created."
            )
        layerContents = [
            (layerName, self.layerContents[layerName])
            for layerName in layerOrder
            if layerName is not None
        ]
        self._writePlist(LAYERCONTENTS_FILENAME, layerContents)

    def _findDirectoryForLayerName(self, layerName: Optional[str]) -> str:
        foundDirectory = None
        for existingLayerName, directoryName in list(self.layerContents.items()):
            if layerName is None and directoryName == DEFAULT_GLYPHS_DIRNAME:
                foundDirectory = directoryName
                break
            elif existingLayerName == layerName:
                foundDirectory = directoryName
                break
        if not foundDirectory:
            raise UFOLibError(
                "Could not locate a glyph set directory for the layer named %s."
                % layerName
            )
        return foundDirectory

    def getGlyphSet(  # type: ignore[override]
        self,
        layerName: Optional[str] = None,
        defaultLayer: bool = True,
        glyphNameToFileNameFunc: GlyphNameToFileNameFunc = None,
        validateRead: Optional[bool] = None,
        validateWrite: Optional[bool] = None,
        expectContentsFile: bool = False,
    ) -> GlyphSet:
        """
        Return the GlyphSet object associated with the
        appropriate glyph directory in the .ufo.
        If layerName is None, the default glyph set
        will be used. The defaultLayer flag indictes
        that the layer should be saved into the default
        glyphs directory.

        ``validateRead`` will validate the read data, by default it is set to the
        class's validate value, can be overridden.
        ``validateWrte`` will validate the written data, by default it is set to the
        class's validate value, can be overridden.
        ``expectContentsFile`` will raise a GlifLibError if a contents.plist file is
        not found on the glyph set file system. This should be set to ``True`` if you
        are reading an existing UFO and ``False`` if you use ``getGlyphSet`` to create
        a fresh	glyph set.
        """
        if validateRead is None:
            validateRead = self._validate
        if validateWrite is None:
            validateWrite = self._validate
        # only default can be written in < 3
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0 and (
            not defaultLayer or layerName is not None
        ):
            raise UFOLibError(
                f"Only the default layer can be writen in UFO {self._formatVersion.major}."
            )
        # locate a layer name when None has been given
        if layerName is None and defaultLayer:
            for existingLayerName, directory in self.layerContents.items():
                if directory == DEFAULT_GLYPHS_DIRNAME:
                    layerName = existingLayerName
            if layerName is None:
                layerName = DEFAULT_LAYER_NAME
        elif layerName is None and not defaultLayer:
            raise UFOLibError("A layer name must be provided for non-default layers.")
        # move along to format specific writing
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            return self._getDefaultGlyphSet(
                validateRead,
                validateWrite,
                glyphNameToFileNameFunc=glyphNameToFileNameFunc,
                expectContentsFile=expectContentsFile,
            )
        elif self._formatVersion.major == UFOFormatVersion.FORMAT_3_0.major:
            return self._getGlyphSetFormatVersion3(
                validateRead,
                validateWrite,
                layerName=layerName,
                defaultLayer=defaultLayer,
                glyphNameToFileNameFunc=glyphNameToFileNameFunc,
                expectContentsFile=expectContentsFile,
            )
        else:
            raise NotImplementedError(self._formatVersion)

    def _getDefaultGlyphSet(
        self,
        validateRead: bool,
        validateWrite: bool,
        glyphNameToFileNameFunc: GlyphNameToFileNameFunc = None,
        expectContentsFile: bool = False,
    ) -> GlyphSet:
        from fontTools.ufoLib.glifLib import GlyphSet

        glyphSubFS = self.fs.makedir(DEFAULT_GLYPHS_DIRNAME, recreate=True)
        return GlyphSet(
            glyphSubFS,
            glyphNameToFileNameFunc=glyphNameToFileNameFunc,
            ufoFormatVersion=self._formatVersion,
            validateRead=validateRead,
            validateWrite=validateWrite,
            expectContentsFile=expectContentsFile,
        )

    def _getGlyphSetFormatVersion3(
        self,
        validateRead: bool,
        validateWrite: bool,
        layerName: Optional[str] = None,
        defaultLayer: bool = True,
        glyphNameToFileNameFunc: GlyphNameToFileNameFunc = None,
        expectContentsFile: bool = False,
    ) -> GlyphSet:
        from fontTools.ufoLib.glifLib import GlyphSet

        # if the default flag is on, make sure that the default in the file
        # matches the default being written. also make sure that this layer
        # name is not already linked to a non-default layer.
        if defaultLayer:
            for existingLayerName, directory in self.layerContents.items():
                if directory == DEFAULT_GLYPHS_DIRNAME:
                    if existingLayerName != layerName:
                        raise UFOLibError(
                            "Another layer ('%s') is already mapped to the default directory."
                            % existingLayerName
                        )
                elif existingLayerName == layerName:
                    raise UFOLibError(
                        "The layer name is already mapped to a non-default layer."
                    )

        # handle layerName is None to avoid MyPy errors
        if layerName is None:
            raise TypeError("'leyerName' cannot be None.")

        # get an existing directory name
        if layerName in self.layerContents:
            directory = self.layerContents[layerName]
        # get a  new directory name
        else:
            if defaultLayer:
                directory = DEFAULT_GLYPHS_DIRNAME
            else:
                # not caching this could be slightly expensive,
                # but caching it will be cumbersome
                existing = {d.lower() for d in self.layerContents.values()}
                directory = userNameToFileName(
                    layerName, existing=existing, prefix="glyphs."
                )
        # make the directory
        glyphSubFS = self.fs.makedir(directory, recreate=True)
        # store the mapping
        self.layerContents[layerName] = directory
        # load the glyph set
        return GlyphSet(
            glyphSubFS,
            glyphNameToFileNameFunc=glyphNameToFileNameFunc,
            ufoFormatVersion=self._formatVersion,
            validateRead=validateRead,
            validateWrite=validateWrite,
            expectContentsFile=expectContentsFile,
        )

    def renameGlyphSet(
        self,
        layerName: Optional[str],
        newLayerName: Optional[str],
        defaultLayer: bool = False,
    ) -> None:
        """
        Rename a glyph set.

        Note: if a GlyphSet object has already been retrieved for
        layerName, it is up to the caller to inform that object that
        the directory it represents has changed.
        """
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            # ignore renaming glyph sets for UFO1 UFO2
            # just write the data from the default layer
            return
        # the new and old names can be the same
        # as long as the default is being switched
        if layerName is not None and layerName == newLayerName:
            # if the default is off and the layer is already not the default, skip
            if (
                self.layerContents[layerName] != DEFAULT_GLYPHS_DIRNAME
                and not defaultLayer
            ):
                return
            # if the default is on and the layer is already the default, skip
            if self.layerContents[layerName] == DEFAULT_GLYPHS_DIRNAME and defaultLayer:
                return
        else:
            # make sure the new layer name doesn't already exist
            if newLayerName is None:
                newLayerName = DEFAULT_LAYER_NAME
            if newLayerName in self.layerContents:
                raise UFOLibError("A layer named %s already exists." % newLayerName)
            # make sure the default layer doesn't already exist
            if defaultLayer and DEFAULT_GLYPHS_DIRNAME in self.layerContents.values():
                raise UFOLibError("A default layer already exists.")
        # get the paths
        oldDirectory = self._findDirectoryForLayerName(layerName)
        if defaultLayer:
            newDirectory = DEFAULT_GLYPHS_DIRNAME
        else:
            existing = {name.lower() for name in self.layerContents.values()}
            newDirectory = userNameToFileName(
                newLayerName, existing=existing, prefix="glyphs."
            )
        # update the internal mapping
        if layerName is not None:
            del self.layerContents[layerName]
        self.layerContents[newLayerName] = newDirectory
        # do the file system copy
        self.fs.movedir(oldDirectory, newDirectory, create=True)

    def deleteGlyphSet(self, layerName: Optional[str]) -> None:
        """
        Remove the glyph set matching layerName.
        """
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            # ignore deleting glyph sets for UFO1 UFO2 as there are no layers
            # just write the data from the default layer
            return
        foundDirectory = self._findDirectoryForLayerName(layerName)
        self.removePath(foundDirectory, removeEmptyParents=False)
        if layerName is not None:
            del self.layerContents[layerName]

    def writeData(self, fileName: PathStr, data: bytes) -> None:
        """
        Write data to fileName in the 'data' directory.
        The data must be a bytes string.
        """
        self.writeBytesToPath(f"{DATA_DIRNAME}/{fsdecode(fileName)}", data)

    def removeData(self, fileName: PathStr) -> None:
        """
        Remove the file named fileName from the data directory.
        """
        self.removePath(f"{DATA_DIRNAME}/{fsdecode(fileName)}")

    # /images

    def writeImage(
        self,
        fileName: PathStr,
        data: bytes,
        validate: Optional[bool] = None,
    ) -> None:
        """
        Write data to fileName in the images directory.
        The data must be a valid PNG.
        """
        if validate is None:
            validate = self._validate
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            raise UFOLibError(
                f"Images are not allowed in UFO {self._formatVersion.major}."
            )
        fileName = fsdecode(fileName)
        if validate:
            valid, error = pngValidator(data=data)
            if not valid:
                raise UFOLibError(error)
        self.writeBytesToPath(f"{IMAGES_DIRNAME}/{fileName}", data)

    def removeImage(
        self,
        fileName: PathStr,
        validate: Optional[bool] = None,
    ) -> None:  # XXX remove unused 'validate'?
        """
        Remove the file named fileName from the
        images directory.
        """
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            raise UFOLibError(
                f"Images are not allowed in UFO {self._formatVersion.major}."
            )
        self.removePath(f"{IMAGES_DIRNAME}/{fsdecode(fileName)}")

    def copyImageFromReader(
        self,
        reader: UFOReader,
        sourceFileName: PathStr,
        destFileName: PathStr,
        validate: Optional[bool] = None,
    ) -> None:
        """
        Copy the sourceFileName in the provided UFOReader to destFileName
        in this writer. This uses the most memory efficient method possible
        for copying the data possible.
        """
        if validate is None:
            validate = self._validate
        if self._formatVersion < UFOFormatVersion.FORMAT_3_0:
            raise UFOLibError(
                f"Images are not allowed in UFO {self._formatVersion.major}."
            )
        sourcePath = f"{IMAGES_DIRNAME}/{fsdecode(sourceFileName)}"
        destPath = f"{IMAGES_DIRNAME}/{fsdecode(destFileName)}"
        self.copyFromReader(reader, sourcePath, destPath)

    def close(self) -> None:
        if self._havePreviousFile and self._fileStructure is UFOFileStructure.ZIP:
            # if we are updating an existing zip file, we can now compress the
            # contents of the temporary filesystem in the destination path
            rootDir = os.path.splitext(os.path.basename(self._path))[0] + ".ufo"
            with fs.zipfs.ZipFS(self._path, write=True, encoding="utf-8") as destFS:  # type: ignore[abstract]
                fs.copy.copy_fs(self.fs, destFS.makedir(rootDir))
        super().close()


# just an alias, makes it more explicit
UFOReaderWriter = UFOWriter


# ----------------
# Helper Functions
# ----------------


def _sniffFileStructure(ufo_path: PathStr) -> UFOFileStructure:
    """Return UFOFileStructure.ZIP if the UFO at path 'ufo_path' (str)
    is a zip file, else return UFOFileStructure.PACKAGE if 'ufo_path' is a
    directory.
    Raise UFOLibError if it is a file with unknown structure, or if the path
    does not exist.
    """
    if zipfile.is_zipfile(ufo_path):
        return UFOFileStructure.ZIP
    elif os.path.isdir(ufo_path):
        return UFOFileStructure.PACKAGE
    elif os.path.isfile(ufo_path):
        raise UFOLibError(
            "The specified UFO does not have a known structure: '%s'" % ufo_path
        )
    else:
        raise UFOLibError("No such file or directory: '%s'" % ufo_path)


def makeUFOPath(path: PathStr) -> str:
    """
    Return a .ufo pathname.

    >>> makeUFOPath("directory/something.ext") == (
    ... 	os.path.join('directory', 'something.ufo'))
    True
    >>> makeUFOPath("directory/something.another.thing.ext") == (
    ... 	os.path.join('directory', 'something.another.thing.ufo'))
    True
    """
    dir, name = os.path.split(path)
    name = ".".join([".".join(name.split(".")[:-1]), "ufo"])
    return os.path.join(dir, name)


# ----------------------
# fontinfo.plist Support
# ----------------------

# Version Validators

# There is no version 1 validator and there shouldn't be.
# The version 1 spec was very loose and there were numerous
# cases of invalid values.


def validateFontInfoVersion2ValueForAttribute(attr: str, value: Any) -> bool:
    """
    This performs very basic validation of the value for attribute
    following the UFO 2 fontinfo.plist specification. The results
    of this should not be interpretted as *correct* for the font
    that they are part of. This merely indicates that the value
    is of the proper type and, where the specification defines
    a set range of possible values for an attribute, that the
    value is in the accepted range.
    """
    dataValidationDict = fontInfoAttributesVersion2ValueData[attr]
    valueType = dataValidationDict.get("type")
    validator = dataValidationDict.get("valueValidator", genericTypeValidator)
    valueOptions = dataValidationDict.get("valueOptions")
    # have specific options for the validator
    if valueOptions is not None:
        isValidValue = validator(value, valueOptions)
    # no specific options
    else:
        if validator == genericTypeValidator:
            isValidValue = validator(value, valueType)
        else:
            isValidValue = validator(value)
    return isValidValue


def validateInfoVersion2Data(infoData: dict[str, Any]) -> dict[str, Any]:
    """
    This performs very basic validation of the value for infoData
    following the UFO 2 fontinfo.plist specification. The results
    of this should not be interpretted as *correct* for the font
    that they are part of. This merely indicates that the values
    are of the proper type and, where the specification defines
    a set range of possible values for an attribute, that the
    value is in the accepted range.
    """
    validInfoData = {}
    for attr, value in list(infoData.items()):
        isValidValue = validateFontInfoVersion2ValueForAttribute(attr, value)
        if not isValidValue:
            raise UFOLibError(f"Invalid value for attribute {attr} ({value!r}).")
        else:
            validInfoData[attr] = value
    return validInfoData


def validateFontInfoVersion3ValueForAttribute(attr: str, value: Any) -> bool:
    """
    This performs very basic validation of the value for attribute
    following the UFO 3 fontinfo.plist specification. The results
    of this should not be interpretted as *correct* for the font
    that they are part of. This merely indicates that the value
    is of the proper type and, where the specification defines
    a set range of possible values for an attribute, that the
    value is in the accepted range.
    """
    dataValidationDict = fontInfoAttributesVersion3ValueData[attr]
    valueType = dataValidationDict.get("type")
    validator = dataValidationDict.get("valueValidator", genericTypeValidator)
    valueOptions = dataValidationDict.get("valueOptions")
    # have specific options for the validator
    if valueOptions is not None:
        isValidValue = validator(value, valueOptions)
    # no specific options
    else:
        if validator == genericTypeValidator:
            isValidValue = validator(value, valueType)
        else:
            isValidValue = validator(value)
    return isValidValue


def validateInfoVersion3Data(infoData: dict[str, Any]) -> dict[str, Any]:
    """
    This performs very basic validation of the value for infoData
    following the UFO 3 fontinfo.plist specification. The results
    of this should not be interpretted as *correct* for the font
    that they are part of. This merely indicates that the values
    are of the proper type and, where the specification defines
    a set range of possible values for an attribute, that the
    value is in the accepted range.
    """
    validInfoData = {}
    for attr, value in list(infoData.items()):
        isValidValue = validateFontInfoVersion3ValueForAttribute(attr, value)
        if not isValidValue:
            raise UFOLibError(f"Invalid value for attribute {attr} ({value!r}).")
        else:
            validInfoData[attr] = value
    return validInfoData


# Value Options

fontInfoOpenTypeHeadFlagsOptions: list[int] = list(range(0, 15))
fontInfoOpenTypeOS2SelectionOptions: list[int] = [1, 2, 3, 4, 7, 8, 9]
fontInfoOpenTypeOS2UnicodeRangesOptions: list[int] = list(range(0, 128))
fontInfoOpenTypeOS2CodePageRangesOptions: list[int] = list(range(0, 64))
fontInfoOpenTypeOS2TypeOptions: list[int] = [0, 1, 2, 3, 8, 9]

# Version Attribute Definitions
# This defines the attributes, types and, in some
# cases the possible values, that can exist is
# fontinfo.plist.

fontInfoAttributesVersion1: set[str] = {
    "familyName",
    "styleName",
    "fullName",
    "fontName",
    "menuName",
    "fontStyle",
    "note",
    "versionMajor",
    "versionMinor",
    "year",
    "copyright",
    "notice",
    "trademark",
    "license",
    "licenseURL",
    "createdBy",
    "designer",
    "designerURL",
    "vendorURL",
    "unitsPerEm",
    "ascender",
    "descender",
    "capHeight",
    "xHeight",
    "defaultWidth",
    "slantAngle",
    "italicAngle",
    "widthName",
    "weightName",
    "weightValue",
    "fondName",
    "otFamilyName",
    "otStyleName",
    "otMacName",
    "msCharSet",
    "fondID",
    "uniqueID",
    "ttVendor",
    "ttUniqueID",
    "ttVersion",
}

fontInfoAttributesVersion2ValueData: FontInfoAttributes = {
    "familyName": dict(type=str),
    "styleName": dict(type=str),
    "styleMapFamilyName": dict(type=str),
    "styleMapStyleName": dict(
        type=str, valueValidator=fontInfoStyleMapStyleNameValidator
    ),
    "versionMajor": dict(type=int),
    "versionMinor": dict(type=int),
    "year": dict(type=int),
    "copyright": dict(type=str),
    "trademark": dict(type=str),
    "unitsPerEm": dict(type=(int, float)),
    "descender": dict(type=(int, float)),
    "xHeight": dict(type=(int, float)),
    "capHeight": dict(type=(int, float)),
    "ascender": dict(type=(int, float)),
    "italicAngle": dict(type=(float, int)),
    "note": dict(type=str),
    "openTypeHeadCreated": dict(
        type=str, valueValidator=fontInfoOpenTypeHeadCreatedValidator
    ),
    "openTypeHeadLowestRecPPEM": dict(type=(int, float)),
    "openTypeHeadFlags": dict(
        type="integerList",
        valueValidator=genericIntListValidator,
        valueOptions=fontInfoOpenTypeHeadFlagsOptions,
    ),
    "openTypeHheaAscender": dict(type=(int, float)),
    "openTypeHheaDescender": dict(type=(int, float)),
    "openTypeHheaLineGap": dict(type=(int, float)),
    "openTypeHheaCaretSlopeRise": dict(type=int),
    "openTypeHheaCaretSlopeRun": dict(type=int),
    "openTypeHheaCaretOffset": dict(type=(int, float)),
    "openTypeNameDesigner": dict(type=str),
    "openTypeNameDesignerURL": dict(type=str),
    "openTypeNameManufacturer": dict(type=str),
    "openTypeNameManufacturerURL": dict(type=str),
    "openTypeNameLicense": dict(type=str),
    "openTypeNameLicenseURL": dict(type=str),
    "openTypeNameVersion": dict(type=str),
    "openTypeNameUniqueID": dict(type=str),
    "openTypeNameDescription": dict(type=str),
    "openTypeNamePreferredFamilyName": dict(type=str),
    "openTypeNamePreferredSubfamilyName": dict(type=str),
    "openTypeNameCompatibleFullName": dict(type=str),
    "openTypeNameSampleText": dict(type=str),
    "openTypeNameWWSFamilyName": dict(type=str),
    "openTypeNameWWSSubfamilyName": dict(type=str),
    "openTypeOS2WidthClass": dict(
        type=int, valueValidator=fontInfoOpenTypeOS2WidthClassValidator
    ),
    "openTypeOS2WeightClass": dict(
        type=int, valueValidator=fontInfoOpenTypeOS2WeightClassValidator
    ),
    "openTypeOS2Selection": dict(
        type="integerList",
        valueValidator=genericIntListValidator,
        valueOptions=fontInfoOpenTypeOS2SelectionOptions,
    ),
    "openTypeOS2VendorID": dict(type=str),
    "openTypeOS2Panose": dict(
        type="integerList", valueValidator=fontInfoVersion2OpenTypeOS2PanoseValidator
    ),
    "openTypeOS2FamilyClass": dict(
        type="integerList", valueValidator=fontInfoOpenTypeOS2FamilyClassValidator
    ),
    "openTypeOS2UnicodeRanges": dict(
        type="integerList",
        valueValidator=genericIntListValidator,
        valueOptions=fontInfoOpenTypeOS2UnicodeRangesOptions,
    ),
    "openTypeOS2CodePageRanges": dict(
        type="integerList",
        valueValidator=genericIntListValidator,
        valueOptions=fontInfoOpenTypeOS2CodePageRangesOptions,
    ),
    "openTypeOS2TypoAscender": dict(type=(int, float)),
    "openTypeOS2TypoDescender": dict(type=(int, float)),
    "openTypeOS2TypoLineGap": dict(type=(int, float)),
    "openTypeOS2WinAscent": dict(type=(int, float)),
    "openTypeOS2WinDescent": dict(type=(int, float)),
    "openTypeOS2Type": dict(
        type="integerList",
        valueValidator=genericIntListValidator,
        valueOptions=fontInfoOpenTypeOS2TypeOptions,
    ),
    "openTypeOS2SubscriptXSize": dict(type=(int, float)),
    "openTypeOS2SubscriptYSize": dict(type=(int, float)),
    "openTypeOS2SubscriptXOffset": dict(type=(int, float)),
    "openTypeOS2SubscriptYOffset": dict(type=(int, float)),
    "openTypeOS2SuperscriptXSize": dict(type=(int, float)),
    "openTypeOS2SuperscriptYSize": dict(type=(int, float)),
    "openTypeOS2SuperscriptXOffset": dict(type=(int, float)),
    "openTypeOS2SuperscriptYOffset": dict(type=(int, float)),
    "openTypeOS2StrikeoutSize": dict(type=(int, float)),
    "openTypeOS2StrikeoutPosition": dict(type=(int, float)),
    "openTypeVheaVertTypoAscender": dict(type=(int, float)),
    "openTypeVheaVertTypoDescender": dict(type=(int, float)),
    "openTypeVheaVertTypoLineGap": dict(type=(int, float)),
    "openTypeVheaCaretSlopeRise": dict(type=int),
    "openTypeVheaCaretSlopeRun": dict(type=int),
    "openTypeVheaCaretOffset": dict(type=(int, float)),
    "postscriptFontName": dict(type=str),
    "postscriptFullName": dict(type=str),
    "postscriptSlantAngle": dict(type=(float, int)),
    "postscriptUniqueID": dict(type=int),
    "postscriptUnderlineThickness": dict(type=(int, float)),
    "postscriptUnderlinePosition": dict(type=(int, float)),
    "postscriptIsFixedPitch": dict(type=bool),
    "postscriptBlueValues": dict(
        type="integerList", valueValidator=fontInfoPostscriptBluesValidator
    ),
    "postscriptOtherBlues": dict(
        type="integerList", valueValidator=fontInfoPostscriptOtherBluesValidator
    ),
    "postscriptFamilyBlues": dict(
        type="integerList", valueValidator=fontInfoPostscriptBluesValidator
    ),
    "postscriptFamilyOtherBlues": dict(
        type="integerList", valueValidator=fontInfoPostscriptOtherBluesValidator
    ),
    "postscriptStemSnapH": dict(
        type="integerList", valueValidator=fontInfoPostscriptStemsValidator
    ),
    "postscriptStemSnapV": dict(
        type="integerList", valueValidator=fontInfoPostscriptStemsValidator
    ),
    "postscriptBlueFuzz": dict(type=(int, float)),
    "postscriptBlueShift": dict(type=(int, float)),
    "postscriptBlueScale": dict(type=(float, int)),
    "postscriptForceBold": dict(type=bool),
    "postscriptDefaultWidthX": dict(type=(int, float)),
    "postscriptNominalWidthX": dict(type=(int, float)),
    "postscriptWeightName": dict(type=str),
    "postscriptDefaultCharacter": dict(type=str),
    "postscriptWindowsCharacterSet": dict(
        type=int, valueValidator=fontInfoPostscriptWindowsCharacterSetValidator
    ),
    "macintoshFONDFamilyID": dict(type=int),
    "macintoshFONDName": dict(type=str),
}
fontInfoAttributesVersion2: set[str] = set(fontInfoAttributesVersion2ValueData.keys())

fontInfoAttributesVersion3ValueData: FontInfoAttributes = deepcopy(
    fontInfoAttributesVersion2ValueData
)
fontInfoAttributesVersion3ValueData.update(
    {
        "versionMinor": dict(type=int, valueValidator=genericNonNegativeIntValidator),
        "unitsPerEm": dict(
            type=(int, float), valueValidator=genericNonNegativeNumberValidator
        ),
        "openTypeHeadLowestRecPPEM": dict(
            type=int, valueValidator=genericNonNegativeNumberValidator
        ),
        "openTypeHheaAscender": dict(type=int),
        "openTypeHheaDescender": dict(type=int),
        "openTypeHheaLineGap": dict(type=int),
        "openTypeHheaCaretOffset": dict(type=int),
        "openTypeOS2Panose": dict(
            type="integerList",
            valueValidator=fontInfoVersion3OpenTypeOS2PanoseValidator,
        ),
        "openTypeOS2TypoAscender": dict(type=int),
        "openTypeOS2TypoDescender": dict(type=int),
        "openTypeOS2TypoLineGap": dict(type=int),
        "openTypeOS2WinAscent": dict(
            type=int, valueValidator=genericNonNegativeNumberValidator
        ),
        "openTypeOS2WinDescent": dict(
            type=int, valueValidator=genericNonNegativeNumberValidator
        ),
        "openTypeOS2SubscriptXSize": dict(type=int),
        "openTypeOS2SubscriptYSize": dict(type=int),
        "openTypeOS2SubscriptXOffset": dict(type=int),
        "openTypeOS2SubscriptYOffset": dict(type=int),
        "openTypeOS2SuperscriptXSize": dict(type=int),
        "openTypeOS2SuperscriptYSize": dict(type=int),
        "openTypeOS2SuperscriptXOffset": dict(type=int),
        "openTypeOS2SuperscriptYOffset": dict(type=int),
        "openTypeOS2StrikeoutSize": dict(type=int),
        "openTypeOS2StrikeoutPosition": dict(type=int),
        "openTypeGaspRangeRecords": dict(
            type="dictList", valueValidator=fontInfoOpenTypeGaspRangeRecordsValidator
        ),
        "openTypeNameRecords": dict(
            type="dictList", valueValidator=fontInfoOpenTypeNameRecordsValidator
        ),
        "openTypeVheaVertTypoAscender": dict(type=int),
        "openTypeVheaVertTypoDescender": dict(type=int),
        "openTypeVheaVertTypoLineGap": dict(type=int),
        "openTypeVheaCaretOffset": dict(type=int),
        "woffMajorVersion": dict(
            type=int, valueValidator=genericNonNegativeIntValidator
        ),
        "woffMinorVersion": dict(
            type=int, valueValidator=genericNonNegativeIntValidator
        ),
        "woffMetadataUniqueID": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataUniqueIDValidator
        ),
        "woffMetadataVendor": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataVendorValidator
        ),
        "woffMetadataCredits": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataCreditsValidator
        ),
        "woffMetadataDescription": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataDescriptionValidator
        ),
        "woffMetadataLicense": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataLicenseValidator
        ),
        "woffMetadataCopyright": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataCopyrightValidator
        ),
        "woffMetadataTrademark": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataTrademarkValidator
        ),
        "woffMetadataLicensee": dict(
            type=dict, valueValidator=fontInfoWOFFMetadataLicenseeValidator
        ),
        "woffMetadataExtensions": dict(
            type=list, valueValidator=fontInfoWOFFMetadataExtensionsValidator
        ),
        "guidelines": dict(type=list, valueValidator=guidelinesValidator),
    }
)
fontInfoAttributesVersion3: set[str] = set(fontInfoAttributesVersion3ValueData.keys())

# insert the type validator for all attrs that
# have no defined validator.
for attr, dataDict in list(fontInfoAttributesVersion2ValueData.items()):
    if "valueValidator" not in dataDict:
        dataDict["valueValidator"] = genericTypeValidator

for attr, dataDict in list(fontInfoAttributesVersion3ValueData.items()):
    if "valueValidator" not in dataDict:
        dataDict["valueValidator"] = genericTypeValidator

# Version Conversion Support
# These are used from converting from version 1
# to version 2 or vice-versa.


def _flipDict(d: dict[K, V]) -> dict[V, K]:
    flipped = {}
    for key, value in list(d.items()):
        flipped[value] = key
    return flipped


fontInfoAttributesVersion1To2: dict[str, str] = {
    "menuName": "styleMapFamilyName",
    "designer": "openTypeNameDesigner",
    "designerURL": "openTypeNameDesignerURL",
    "createdBy": "openTypeNameManufacturer",
    "vendorURL": "openTypeNameManufacturerURL",
    "license": "openTypeNameLicense",
    "licenseURL": "openTypeNameLicenseURL",
    "ttVersion": "openTypeNameVersion",
    "ttUniqueID": "openTypeNameUniqueID",
    "notice": "openTypeNameDescription",
    "otFamilyName": "openTypeNamePreferredFamilyName",
    "otStyleName": "openTypeNamePreferredSubfamilyName",
    "otMacName": "openTypeNameCompatibleFullName",
    "weightName": "postscriptWeightName",
    "weightValue": "openTypeOS2WeightClass",
    "ttVendor": "openTypeOS2VendorID",
    "uniqueID": "postscriptUniqueID",
    "fontName": "postscriptFontName",
    "fondID": "macintoshFONDFamilyID",
    "fondName": "macintoshFONDName",
    "defaultWidth": "postscriptDefaultWidthX",
    "slantAngle": "postscriptSlantAngle",
    "fullName": "postscriptFullName",
    # require special value conversion
    "fontStyle": "styleMapStyleName",
    "widthName": "openTypeOS2WidthClass",
    "msCharSet": "postscriptWindowsCharacterSet",
}
fontInfoAttributesVersion2To1 = _flipDict(fontInfoAttributesVersion1To2)
deprecatedFontInfoAttributesVersion2 = set(fontInfoAttributesVersion1To2.keys())

_fontStyle1To2: dict[int, str] = {
    64: "regular",
    1: "italic",
    32: "bold",
    33: "bold italic",
}
_fontStyle2To1: dict[str, int] = _flipDict(_fontStyle1To2)
# Some UFO 1 files have 0
_fontStyle1To2[0] = "regular"

_widthName1To2: dict[str, int] = {
    "Ultra-condensed": 1,
    "Extra-condensed": 2,
    "Condensed": 3,
    "Semi-condensed": 4,
    "Medium (normal)": 5,
    "Semi-expanded": 6,
    "Expanded": 7,
    "Extra-expanded": 8,
    "Ultra-expanded": 9,
}
_widthName2To1: dict[int, str] = _flipDict(_widthName1To2)
# FontLab's default width value is "Normal".
# Many format version 1 UFOs will have this.
_widthName1To2["Normal"] = 5
# FontLab has an "All" width value. In UFO 1
# move this up to "Normal".
_widthName1To2["All"] = 5
# "medium" appears in a lot of UFO 1 files.
_widthName1To2["medium"] = 5
# "Medium" appears in a lot of UFO 1 files.
_widthName1To2["Medium"] = 5

_msCharSet1To2: dict[int, int] = {
    0: 1,
    1: 2,
    2: 3,
    77: 4,
    128: 5,
    129: 6,
    130: 7,
    134: 8,
    136: 9,
    161: 10,
    162: 11,
    163: 12,
    177: 13,
    178: 14,
    186: 15,
    200: 16,
    204: 17,
    222: 18,
    238: 19,
    255: 20,
}
_msCharSet2To1: dict[int, int] = _flipDict(_msCharSet1To2)

# 1 <-> 2


def convertFontInfoValueForAttributeFromVersion1ToVersion2(
    attr: str, value: Any
) -> tuple[str, Any]:
    """
    Convert value from version 1 to version 2 format.
    Returns the new attribute name and the converted value.
    If the value is None, None will be returned for the new value.
    """
    # convert floats to ints if possible
    if isinstance(value, float):
        if int(value) == value:
            value = int(value)
    if value is not None:
        if attr == "fontStyle":
            v: Optional[Union[str, int]] = _fontStyle1To2.get(value)
            if v is None:
                raise UFOLibError(
                    f"Cannot convert value ({value!r}) for attribute {attr}."
                )
            value = v
        elif attr == "widthName":
            v = _widthName1To2.get(value)
            if v is None:
                raise UFOLibError(
                    f"Cannot convert value ({value!r}) for attribute {attr}."
                )
            value = v
        elif attr == "msCharSet":
            v = _msCharSet1To2.get(value)
            if v is None:
                raise UFOLibError(
                    f"Cannot convert value ({value!r}) for attribute {attr}."
                )
            value = v
    attr = fontInfoAttributesVersion1To2.get(attr, attr)
    return attr, value


def convertFontInfoValueForAttributeFromVersion2ToVersion1(
    attr: str, value: Any
) -> tuple[str, Any]:
    """
    Convert value from version 2 to version 1 format.
    Returns the new attribute name and the converted value.
    If the value is None, None will be returned for the new value.
    """
    if value is not None:
        if attr == "styleMapStyleName":
            value = _fontStyle2To1.get(value)
        elif attr == "openTypeOS2WidthClass":
            value = _widthName2To1.get(value)
        elif attr == "postscriptWindowsCharacterSet":
            value = _msCharSet2To1.get(value)
    attr = fontInfoAttributesVersion2To1.get(attr, attr)
    return attr, value


def _convertFontInfoDataVersion1ToVersion2(data: dict[str, Any]) -> dict[str, Any]:
    converted = {}
    for attr, value in list(data.items()):
        # FontLab gives -1 for the weightValue
        # for fonts wil no defined value. Many
        # format version 1 UFOs will have this.
        if attr == "weightValue" and value == -1:
            continue
        newAttr, newValue = convertFontInfoValueForAttributeFromVersion1ToVersion2(
            attr, value
        )
        # skip if the attribute is not part of version 2
        if newAttr not in fontInfoAttributesVersion2:
            continue
        # catch values that can't be converted
        if value is None:
            raise UFOLibError(
                f"Cannot convert value ({value!r}) for attribute {newAttr}."
            )
        # store
        converted[newAttr] = newValue
    return converted


def _convertFontInfoDataVersion2ToVersion1(data: dict[str, Any]) -> dict[str, Any]:
    converted = {}
    for attr, value in list(data.items()):
        newAttr, newValue = convertFontInfoValueForAttributeFromVersion2ToVersion1(
            attr, value
        )
        # only take attributes that are registered for version 1
        if newAttr not in fontInfoAttributesVersion1:
            continue
        # catch values that can't be converted
        if value is None:
            raise UFOLibError(
                f"Cannot convert value ({value!r}) for attribute {newAttr}."
            )
        # store
        converted[newAttr] = newValue
    return converted


# 2 <-> 3

_ufo2To3NonNegativeInt: set[str] = {
    "versionMinor",
    "openTypeHeadLowestRecPPEM",
    "openTypeOS2WinAscent",
    "openTypeOS2WinDescent",
}
_ufo2To3NonNegativeIntOrFloat: set[str] = {
    "unitsPerEm",
}
_ufo2To3FloatToInt: set[str] = {
    "openTypeHeadLowestRecPPEM",
    "openTypeHheaAscender",
    "openTypeHheaDescender",
    "openTypeHheaLineGap",
    "openTypeHheaCaretOffset",
    "openTypeOS2TypoAscender",
    "openTypeOS2TypoDescender",
    "openTypeOS2TypoLineGap",
    "openTypeOS2WinAscent",
    "openTypeOS2WinDescent",
    "openTypeOS2SubscriptXSize",
    "openTypeOS2SubscriptYSize",
    "openTypeOS2SubscriptXOffset",
    "openTypeOS2SubscriptYOffset",
    "openTypeOS2SuperscriptXSize",
    "openTypeOS2SuperscriptYSize",
    "openTypeOS2SuperscriptXOffset",
    "openTypeOS2SuperscriptYOffset",
    "openTypeOS2StrikeoutSize",
    "openTypeOS2StrikeoutPosition",
    "openTypeVheaVertTypoAscender",
    "openTypeVheaVertTypoDescender",
    "openTypeVheaVertTypoLineGap",
    "openTypeVheaCaretOffset",
}


def convertFontInfoValueForAttributeFromVersion2ToVersion3(
    attr: str, value: Any
) -> tuple[str, Any]:
    """
    Convert value from version 2 to version 3 format.
    Returns the new attribute name and the converted value.
    If the value is None, None will be returned for the new value.
    """
    if attr in _ufo2To3FloatToInt:
        try:
            value = round(value)
        except (ValueError, TypeError):
            raise UFOLibError("Could not convert value for %s." % attr)
    if attr in _ufo2To3NonNegativeInt:
        try:
            value = int(abs(value))
        except (ValueError, TypeError):
            raise UFOLibError("Could not convert value for %s." % attr)
    elif attr in _ufo2To3NonNegativeIntOrFloat:
        try:
            v = float(abs(value))
        except (ValueError, TypeError):
            raise UFOLibError("Could not convert value for %s." % attr)
        if v == int(v):
            v = int(v)
        if v != value:
            value = v
    return attr, value


def convertFontInfoValueForAttributeFromVersion3ToVersion2(
    attr: str, value: Any
) -> tuple[str, Any]:
    """
    Convert value from version 3 to version 2 format.
    Returns the new attribute name and the converted value.
    If the value is None, None will be returned for the new value.
    """
    return attr, value


def _convertFontInfoDataVersion3ToVersion2(data: dict[str, Any]) -> dict[str, Any]:
    converted = {}
    for attr, value in list(data.items()):
        newAttr, newValue = convertFontInfoValueForAttributeFromVersion3ToVersion2(
            attr, value
        )
        if newAttr not in fontInfoAttributesVersion2:
            continue
        converted[newAttr] = newValue
    return converted


def _convertFontInfoDataVersion2ToVersion3(data: dict[str, Any]) -> dict[str, Any]:
    converted = {}
    for attr, value in list(data.items()):
        attr, value = convertFontInfoValueForAttributeFromVersion2ToVersion3(
            attr, value
        )
        converted[attr] = value
    return converted


if __name__ == "__main__":
    import doctest

    doctest.testmod()
