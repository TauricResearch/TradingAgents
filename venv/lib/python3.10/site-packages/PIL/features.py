from __future__ import annotations

import collections
import os
import sys
import warnings
from typing import IO

import PIL

from . import Image
from ._deprecate import deprecate

modules = {
    "pil": ("PIL._imaging", "PILLOW_VERSION"),
    "tkinter": ("PIL._tkinter_finder", "tk_version"),
    "freetype2": ("PIL._imagingft", "freetype2_version"),
    "littlecms2": ("PIL._imagingcms", "littlecms_version"),
    "webp": ("PIL._webp", "webpdecoder_version"),
    "avif": ("PIL._avif", "libavif_version"),
}


def check_module(feature: str) -> bool:
    """
    Checks if a module is available.

    :param feature: The module to check for.
    :returns: ``True`` if available, ``False`` otherwise.
    :raises ValueError: If the module is not defined in this version of Pillow.
    """
    if feature not in modules:
        msg = f"Unknown module {feature}"
        raise ValueError(msg)

    module, ver = modules[feature]

    try:
        __import__(module)
        return True
    except ModuleNotFoundError:
        return False
    except ImportError as ex:
        warnings.warn(str(ex))
        return False


def version_module(feature: str) -> str | None:
    """
    :param feature: The module to check for.
    :returns:
        The loaded version number as a string, or ``None`` if unknown or not available.
    :raises ValueError: If the module is not defined in this version of Pillow.
    """
    if not check_module(feature):
        return None

    module, ver = modules[feature]

    return getattr(__import__(module, fromlist=[ver]), ver)


def get_supported_modules() -> list[str]:
    """
    :returns: A list of all supported modules.
    """
    return [f for f in modules if check_module(f)]


codecs = {
    "jpg": ("jpeg", "jpeglib"),
    "jpg_2000": ("jpeg2k", "jp2klib"),
    "zlib": ("zip", "zlib"),
    "libtiff": ("libtiff", "libtiff"),
}


def check_codec(feature: str) -> bool:
    """
    Checks if a codec is available.

    :param feature: The codec to check for.
    :returns: ``True`` if available, ``False`` otherwise.
    :raises ValueError: If the codec is not defined in this version of Pillow.
    """
    if feature not in codecs:
        msg = f"Unknown codec {feature}"
        raise ValueError(msg)

    codec, lib = codecs[feature]

    return f"{codec}_encoder" in dir(Image.core)


def version_codec(feature: str) -> str | None:
    """
    :param feature: The codec to check for.
    :returns:
        The version number as a string, or ``None`` if not available.
        Checked at compile time for ``jpg``, run-time otherwise.
    :raises ValueError: If the codec is not defined in this version of Pillow.
    """
    if not check_codec(feature):
        return None

    codec, lib = codecs[feature]

    version = getattr(Image.core, f"{lib}_version")

    if feature == "libtiff":
        return version.split("\n")[0].split("Version ")[1]

    return version


def get_supported_codecs() -> list[str]:
    """
    :returns: A list of all supported codecs.
    """
    return [f for f in codecs if check_codec(f)]


features: dict[str, tuple[str, str | bool, str | None]] = {
    "webp_anim": ("PIL._webp", True, None),
    "webp_mux": ("PIL._webp", True, None),
    "transp_webp": ("PIL._webp", True, None),
    "raqm": ("PIL._imagingft", "HAVE_RAQM", "raqm_version"),
    "fribidi": ("PIL._imagingft", "HAVE_FRIBIDI", "fribidi_version"),
    "harfbuzz": ("PIL._imagingft", "HAVE_HARFBUZZ", "harfbuzz_version"),
    "libjpeg_turbo": ("PIL._imaging", "HAVE_LIBJPEGTURBO", "libjpeg_turbo_version"),
    "mozjpeg": ("PIL._imaging", "HAVE_MOZJPEG", "libjpeg_turbo_version"),
    "zlib_ng": ("PIL._imaging", "HAVE_ZLIBNG", "zlib_ng_version"),
    "libimagequant": ("PIL._imaging", "HAVE_LIBIMAGEQUANT", "imagequant_version"),
    "xcb": ("PIL._imaging", "HAVE_XCB", None),
}


def check_feature(feature: str) -> bool | None:
    """
    Checks if a feature is available.

    :param feature: The feature to check for.
    :returns: ``True`` if available, ``False`` if unavailable, ``None`` if unknown.
    :raises ValueError: If the feature is not defined in this version of Pillow.
    """
    if feature not in features:
        msg = f"Unknown feature {feature}"
        raise ValueError(msg)

    module, flag, ver = features[feature]

    if isinstance(flag, bool):
        deprecate(f'check_feature("{feature}")', 12)
    try:
        imported_module = __import__(module, fromlist=["PIL"])
        if isinstance(flag, bool):
            return flag
        return getattr(imported_module, flag)
    except ModuleNotFoundError:
        return None
    except ImportError as ex:
        warnings.warn(str(ex))
        return None


def version_feature(feature: str) -> str | None:
    """
    :param feature: The feature to check for.
    :returns: The version number as a string, or ``None`` if not available.
    :raises ValueError: If the feature is not defined in this version of Pillow.
    """
    if not check_feature(feature):
        return None

    module, flag, ver = features[feature]

    if ver is None:
        return None

    return getattr(__import__(module, fromlist=[ver]), ver)


def get_supported_features() -> list[str]:
    """
    :returns: A list of all supported features.
    """
    supported_features = []
    for f, (module, flag, _) in features.items():
        if flag is True:
            for feature, (feature_module, _) in modules.items():
                if feature_module == module:
                    if check_module(feature):
                        supported_features.append(f)
                    break
        elif check_feature(f):
            supported_features.append(f)
    return supported_features


def check(feature: str) -> bool | None:
    """
    :param feature: A module, codec, or feature name.
    :returns:
        ``True`` if the module, codec, or feature is available,
        ``False`` or ``None`` otherwise.
    """

    if feature in modules:
        return check_module(feature)
    if feature in codecs:
        return check_codec(feature)
    if feature in features:
        return check_feature(feature)
    warnings.warn(f"Unknown feature '{feature}'.", stacklevel=2)
    return False


def version(feature: str) -> str | None:
    """
    :param feature:
        The module, codec, or feature to check for.
    :returns:
        The version number as a string, or ``None`` if unknown or not available.
    """
    if feature in modules:
        return version_module(feature)
    if feature in codecs:
        return version_codec(feature)
    if feature in features:
        return version_feature(feature)
    return None


def get_supported() -> list[str]:
    """
    :returns: A list of all supported modules, features, and codecs.
    """

    ret = get_supported_modules()
    ret.extend(get_supported_features())
    ret.extend(get_supported_codecs())
    return ret


def pilinfo(out: IO[str] | None = None, supported_formats: bool = True) -> None:
    """
    Prints information about this installation of Pillow.
    This function can be called with ``python3 -m PIL``.
    It can also be called with ``python3 -m PIL.report`` or ``python3 -m PIL --report``
    to have "supported_formats" set to ``False``, omitting the list of all supported
    image file formats.

    :param out:
        The output stream to print to. Defaults to ``sys.stdout`` if ``None``.
    :param supported_formats:
        If ``True``, a list of all supported image file formats will be printed.
    """

    if out is None:
        out = sys.stdout

    Image.init()

    print("-" * 68, file=out)
    print(f"Pillow {PIL.__version__}", file=out)
    py_version_lines = sys.version.splitlines()
    print(f"Python {py_version_lines[0].strip()}", file=out)
    for py_version in py_version_lines[1:]:
        print(f"       {py_version.strip()}", file=out)
    print("-" * 68, file=out)
    print(f"Python executable is {sys.executable or 'unknown'}", file=out)
    if sys.prefix != sys.base_prefix:
        print(f"Environment Python files loaded from {sys.prefix}", file=out)
    print(f"System Python files loaded from {sys.base_prefix}", file=out)
    print("-" * 68, file=out)
    print(
        f"Python Pillow modules loaded from {os.path.dirname(Image.__file__)}",
        file=out,
    )
    print(
        f"Binary Pillow modules loaded from {os.path.dirname(Image.core.__file__)}",
        file=out,
    )
    print("-" * 68, file=out)

    for name, feature in [
        ("pil", "PIL CORE"),
        ("tkinter", "TKINTER"),
        ("freetype2", "FREETYPE2"),
        ("littlecms2", "LITTLECMS2"),
        ("webp", "WEBP"),
        ("avif", "AVIF"),
        ("jpg", "JPEG"),
        ("jpg_2000", "OPENJPEG (JPEG2000)"),
        ("zlib", "ZLIB (PNG/ZIP)"),
        ("libtiff", "LIBTIFF"),
        ("raqm", "RAQM (Bidirectional Text)"),
        ("libimagequant", "LIBIMAGEQUANT (Quantization method)"),
        ("xcb", "XCB (X protocol)"),
    ]:
        if check(name):
            v: str | None = None
            if name == "jpg":
                libjpeg_turbo_version = version_feature("libjpeg_turbo")
                if libjpeg_turbo_version is not None:
                    v = "mozjpeg" if check_feature("mozjpeg") else "libjpeg-turbo"
                    v += " " + libjpeg_turbo_version
            if v is None:
                v = version(name)
            if v is not None:
                version_static = name in ("pil", "jpg")
                if name == "littlecms2":
                    # this check is also in src/_imagingcms.c:setup_module()
                    version_static = tuple(int(x) for x in v.split(".")) < (2, 7)
                t = "compiled for" if version_static else "loaded"
                if name == "zlib":
                    zlib_ng_version = version_feature("zlib_ng")
                    if zlib_ng_version is not None:
                        v += ", compiled for zlib-ng " + zlib_ng_version
                elif name == "raqm":
                    for f in ("fribidi", "harfbuzz"):
                        v2 = version_feature(f)
                        if v2 is not None:
                            v += f", {f} {v2}"
                print("---", feature, "support ok,", t, v, file=out)
            else:
                print("---", feature, "support ok", file=out)
        else:
            print("***", feature, "support not installed", file=out)
    print("-" * 68, file=out)

    if supported_formats:
        extensions = collections.defaultdict(list)
        for ext, i in Image.EXTENSION.items():
            extensions[i].append(ext)

        for i in sorted(Image.ID):
            line = f"{i}"
            if i in Image.MIME:
                line = f"{line} {Image.MIME[i]}"
            print(line, file=out)

            if i in extensions:
                print(
                    "Extensions: {}".format(", ".join(sorted(extensions[i]))), file=out
                )

            features = []
            if i in Image.OPEN:
                features.append("open")
            if i in Image.SAVE:
                features.append("save")
            if i in Image.SAVE_ALL:
                features.append("save_all")
            if i in Image.DECODERS:
                features.append("decode")
            if i in Image.ENCODERS:
                features.append("encode")

            print("Features: {}".format(", ".join(features)), file=out)
            print("-" * 68, file=out)
