# The Python Imaging Library.
# $Id$

# Optional color management support, based on Kevin Cazabon's PyCMS
# library.

# Originally released under LGPL.  Graciously donated to PIL in
# March 2009, for distribution under the standard PIL license

# History:

# 2009-03-08 fl   Added to PIL.

# Copyright (C) 2002-2003 Kevin Cazabon
# Copyright (c) 2009 by Fredrik Lundh
# Copyright (c) 2013 by Eric Soroos

# See the README file for information on usage and redistribution.  See
# below for the original description.
from __future__ import annotations

import operator
import sys
from enum import IntEnum, IntFlag
from functools import reduce
from typing import Any, Literal, SupportsFloat, SupportsInt, Union

from . import Image, __version__
from ._deprecate import deprecate
from ._typing import SupportsRead

try:
    from . import _imagingcms as core

    _CmsProfileCompatible = Union[
        str, SupportsRead[bytes], core.CmsProfile, "ImageCmsProfile"
    ]
except ImportError as ex:
    # Allow error import for doc purposes, but error out when accessing
    # anything in core.
    from ._util import DeferredError

    core = DeferredError.new(ex)

_DESCRIPTION = """
pyCMS

    a Python / PIL interface to the littleCMS ICC Color Management System
    Copyright (C) 2002-2003 Kevin Cazabon
    kevin@cazabon.com
    https://www.cazabon.com

    pyCMS home page:  https://www.cazabon.com/pyCMS
    littleCMS home page:  https://www.littlecms.com
    (littleCMS is Copyright (C) 1998-2001 Marti Maria)

    Originally released under LGPL.  Graciously donated to PIL in
    March 2009, for distribution under the standard PIL license

    The pyCMS.py module provides a "clean" interface between Python/PIL and
    pyCMSdll, taking care of some of the more complex handling of the direct
    pyCMSdll functions, as well as error-checking and making sure that all
    relevant data is kept together.

    While it is possible to call pyCMSdll functions directly, it's not highly
    recommended.

    Version History:

        1.0.0 pil       Oct 2013 Port to LCMS 2.

        0.1.0 pil mod   March 10, 2009

                        Renamed display profile to proof profile. The proof
                        profile is the profile of the device that is being
                        simulated, not the profile of the device which is
                        actually used to display/print the final simulation
                        (that'd be the output profile) - also see LCMSAPI.txt
                        input colorspace -> using 'renderingIntent' -> proof
                        colorspace -> using 'proofRenderingIntent' -> output
                        colorspace

                        Added LCMS FLAGS support.
                        Added FLAGS["SOFTPROOFING"] as default flag for
                        buildProofTransform (otherwise the proof profile/intent
                        would be ignored).

        0.1.0 pil       March 2009 - added to PIL, as PIL.ImageCms

        0.0.2 alpha     Jan 6, 2002

                        Added try/except statements around type() checks of
                        potential CObjects... Python won't let you use type()
                        on them, and raises a TypeError (stupid, if you ask
                        me!)

                        Added buildProofTransformFromOpenProfiles() function.
                        Additional fixes in DLL, see DLL code for details.

        0.0.1 alpha     first public release, Dec. 26, 2002

    Known to-do list with current version (of Python interface, not pyCMSdll):

        none

"""

_VERSION = "1.0.0 pil"


def __getattr__(name: str) -> Any:
    if name == "DESCRIPTION":
        deprecate("PIL.ImageCms.DESCRIPTION", 12)
        return _DESCRIPTION
    elif name == "VERSION":
        deprecate("PIL.ImageCms.VERSION", 12)
        return _VERSION
    elif name == "FLAGS":
        deprecate("PIL.ImageCms.FLAGS", 12, "PIL.ImageCms.Flags")
        return _FLAGS
    msg = f"module '{__name__}' has no attribute '{name}'"
    raise AttributeError(msg)


# --------------------------------------------------------------------.


#
# intent/direction values


class Intent(IntEnum):
    PERCEPTUAL = 0
    RELATIVE_COLORIMETRIC = 1
    SATURATION = 2
    ABSOLUTE_COLORIMETRIC = 3


class Direction(IntEnum):
    INPUT = 0
    OUTPUT = 1
    PROOF = 2


#
# flags


class Flags(IntFlag):
    """Flags and documentation are taken from ``lcms2.h``."""

    NONE = 0
    NOCACHE = 0x0040
    """Inhibit 1-pixel cache"""
    NOOPTIMIZE = 0x0100
    """Inhibit optimizations"""
    NULLTRANSFORM = 0x0200
    """Don't transform anyway"""
    GAMUTCHECK = 0x1000
    """Out of Gamut alarm"""
    SOFTPROOFING = 0x4000
    """Do softproofing"""
    BLACKPOINTCOMPENSATION = 0x2000
    NOWHITEONWHITEFIXUP = 0x0004
    """Don't fix scum dot"""
    HIGHRESPRECALC = 0x0400
    """Use more memory to give better accuracy"""
    LOWRESPRECALC = 0x0800
    """Use less memory to minimize resources"""
    # this should be 8BITS_DEVICELINK, but that is not a valid name in Python:
    USE_8BITS_DEVICELINK = 0x0008
    """Create 8 bits devicelinks"""
    GUESSDEVICECLASS = 0x0020
    """Guess device class (for ``transform2devicelink``)"""
    KEEP_SEQUENCE = 0x0080
    """Keep profile sequence for devicelink creation"""
    FORCE_CLUT = 0x0002
    """Force CLUT optimization"""
    CLUT_POST_LINEARIZATION = 0x0001
    """create postlinearization tables if possible"""
    CLUT_PRE_LINEARIZATION = 0x0010
    """create prelinearization tables if possible"""
    NONEGATIVES = 0x8000
    """Prevent negative numbers in floating point transforms"""
    COPY_ALPHA = 0x04000000
    """Alpha channels are copied on ``cmsDoTransform()``"""
    NODEFAULTRESOURCEDEF = 0x01000000

    _GRIDPOINTS_1 = 1 << 16
    _GRIDPOINTS_2 = 2 << 16
    _GRIDPOINTS_4 = 4 << 16
    _GRIDPOINTS_8 = 8 << 16
    _GRIDPOINTS_16 = 16 << 16
    _GRIDPOINTS_32 = 32 << 16
    _GRIDPOINTS_64 = 64 << 16
    _GRIDPOINTS_128 = 128 << 16

    @staticmethod
    def GRIDPOINTS(n: int) -> Flags:
        """
        Fine-tune control over number of gridpoints

        :param n: :py:class:`int` in range ``0 <= n <= 255``
        """
        return Flags.NONE | ((n & 0xFF) << 16)


_MAX_FLAG = reduce(operator.or_, Flags)


_FLAGS = {
    "MATRIXINPUT": 1,
    "MATRIXOUTPUT": 2,
    "MATRIXONLY": (1 | 2),
    "NOWHITEONWHITEFIXUP": 4,  # Don't hot fix scum dot
    # Don't create prelinearization tables on precalculated transforms
    # (internal use):
    "NOPRELINEARIZATION": 16,
    "GUESSDEVICECLASS": 32,  # Guess device class (for transform2devicelink)
    "NOTCACHE": 64,  # Inhibit 1-pixel cache
    "NOTPRECALC": 256,
    "NULLTRANSFORM": 512,  # Don't transform anyway
    "HIGHRESPRECALC": 1024,  # Use more memory to give better accuracy
    "LOWRESPRECALC": 2048,  # Use less memory to minimize resources
    "WHITEBLACKCOMPENSATION": 8192,
    "BLACKPOINTCOMPENSATION": 8192,
    "GAMUTCHECK": 4096,  # Out of Gamut alarm
    "SOFTPROOFING": 16384,  # Do softproofing
    "PRESERVEBLACK": 32768,  # Black preservation
    "NODEFAULTRESOURCEDEF": 16777216,  # CRD special
    "GRIDPOINTS": lambda n: (n & 0xFF) << 16,  # Gridpoints
}


# --------------------------------------------------------------------.
# Experimental PIL-level API
# --------------------------------------------------------------------.

##
# Profile.


class ImageCmsProfile:
    def __init__(self, profile: str | SupportsRead[bytes] | core.CmsProfile) -> None:
        """
        :param profile: Either a string representing a filename,
            a file like object containing a profile or a
            low-level profile object

        """
        self.filename = None
        self.product_name = None  # profile.product_name
        self.product_info = None  # profile.product_info

        if isinstance(profile, str):
            if sys.platform == "win32":
                profile_bytes_path = profile.encode()
                try:
                    profile_bytes_path.decode("ascii")
                except UnicodeDecodeError:
                    with open(profile, "rb") as f:
                        self.profile = core.profile_frombytes(f.read())
                    return
            self.filename = profile
            self.profile = core.profile_open(profile)
        elif hasattr(profile, "read"):
            self.profile = core.profile_frombytes(profile.read())
        elif isinstance(profile, core.CmsProfile):
            self.profile = profile
        else:
            msg = "Invalid type for Profile"  # type: ignore[unreachable]
            raise TypeError(msg)

    def tobytes(self) -> bytes:
        """
        Returns the profile in a format suitable for embedding in
        saved images.

        :returns: a bytes object containing the ICC profile.
        """

        return core.profile_tobytes(self.profile)


class ImageCmsTransform(Image.ImagePointHandler):
    """
    Transform.  This can be used with the procedural API, or with the standard
    :py:func:`~PIL.Image.Image.point` method.

    Will return the output profile in the ``output.info['icc_profile']``.
    """

    def __init__(
        self,
        input: ImageCmsProfile,
        output: ImageCmsProfile,
        input_mode: str,
        output_mode: str,
        intent: Intent = Intent.PERCEPTUAL,
        proof: ImageCmsProfile | None = None,
        proof_intent: Intent = Intent.ABSOLUTE_COLORIMETRIC,
        flags: Flags = Flags.NONE,
    ):
        supported_modes = (
            "RGB",
            "RGBA",
            "RGBX",
            "CMYK",
            "I;16",
            "I;16L",
            "I;16B",
            "YCbCr",
            "LAB",
            "L",
            "1",
        )
        for mode in (input_mode, output_mode):
            if mode not in supported_modes:
                deprecate(
                    mode,
                    12,
                    {
                        "L;16": "I;16 or I;16L",
                        "L:16B": "I;16B",
                        "YCCA": "YCbCr",
                        "YCC": "YCbCr",
                    }.get(mode),
                )
        if proof is None:
            self.transform = core.buildTransform(
                input.profile, output.profile, input_mode, output_mode, intent, flags
            )
        else:
            self.transform = core.buildProofTransform(
                input.profile,
                output.profile,
                proof.profile,
                input_mode,
                output_mode,
                intent,
                proof_intent,
                flags,
            )
        # Note: inputMode and outputMode are for pyCMS compatibility only
        self.input_mode = self.inputMode = input_mode
        self.output_mode = self.outputMode = output_mode

        self.output_profile = output

    def point(self, im: Image.Image) -> Image.Image:
        return self.apply(im)

    def apply(self, im: Image.Image, imOut: Image.Image | None = None) -> Image.Image:
        if imOut is None:
            imOut = Image.new(self.output_mode, im.size, None)
        self.transform.apply(im.getim(), imOut.getim())
        imOut.info["icc_profile"] = self.output_profile.tobytes()
        return imOut

    def apply_in_place(self, im: Image.Image) -> Image.Image:
        if im.mode != self.output_mode:
            msg = "mode mismatch"
            raise ValueError(msg)  # wrong output mode
        self.transform.apply(im.getim(), im.getim())
        im.info["icc_profile"] = self.output_profile.tobytes()
        return im


def get_display_profile(handle: SupportsInt | None = None) -> ImageCmsProfile | None:
    """
    (experimental) Fetches the profile for the current display device.

    :returns: ``None`` if the profile is not known.
    """

    if sys.platform != "win32":
        return None

    from . import ImageWin  # type: ignore[unused-ignore, unreachable]

    if isinstance(handle, ImageWin.HDC):
        profile = core.get_display_profile_win32(int(handle), 1)
    else:
        profile = core.get_display_profile_win32(int(handle or 0))
    if profile is None:
        return None
    return ImageCmsProfile(profile)


# --------------------------------------------------------------------.
# pyCMS compatible layer
# --------------------------------------------------------------------.


class PyCMSError(Exception):
    """(pyCMS) Exception class.
    This is used for all errors in the pyCMS API."""

    pass


def profileToProfile(
    im: Image.Image,
    inputProfile: _CmsProfileCompatible,
    outputProfile: _CmsProfileCompatible,
    renderingIntent: Intent = Intent.PERCEPTUAL,
    outputMode: str | None = None,
    inPlace: bool = False,
    flags: Flags = Flags.NONE,
) -> Image.Image | None:
    """
    (pyCMS) Applies an ICC transformation to a given image, mapping from
    ``inputProfile`` to ``outputProfile``.

    If the input or output profiles specified are not valid filenames, a
    :exc:`PyCMSError` will be raised.  If ``inPlace`` is ``True`` and
    ``outputMode != im.mode``, a :exc:`PyCMSError` will be raised.
    If an error occurs during application of the profiles,
    a :exc:`PyCMSError` will be raised.
    If ``outputMode`` is not a mode supported by the ``outputProfile`` (or by pyCMS),
    a :exc:`PyCMSError` will be raised.

    This function applies an ICC transformation to im from ``inputProfile``'s
    color space to ``outputProfile``'s color space using the specified rendering
    intent to decide how to handle out-of-gamut colors.

    ``outputMode`` can be used to specify that a color mode conversion is to
    be done using these profiles, but the specified profiles must be able
    to handle that mode.  I.e., if converting im from RGB to CMYK using
    profiles, the input profile must handle RGB data, and the output
    profile must handle CMYK data.

    :param im: An open :py:class:`~PIL.Image.Image` object (i.e. Image.new(...)
        or Image.open(...), etc.)
    :param inputProfile: String, as a valid filename path to the ICC input
        profile you wish to use for this image, or a profile object
    :param outputProfile: String, as a valid filename path to the ICC output
        profile you wish to use for this image, or a profile object
    :param renderingIntent: Integer (0-3) specifying the rendering intent you
        wish to use for the transform

            ImageCms.Intent.PERCEPTUAL            = 0 (DEFAULT)
            ImageCms.Intent.RELATIVE_COLORIMETRIC = 1
            ImageCms.Intent.SATURATION            = 2
            ImageCms.Intent.ABSOLUTE_COLORIMETRIC = 3

        see the pyCMS documentation for details on rendering intents and what
        they do.
    :param outputMode: A valid PIL mode for the output image (i.e. "RGB",
        "CMYK", etc.).  Note: if rendering the image "inPlace", outputMode
        MUST be the same mode as the input, or omitted completely.  If
        omitted, the outputMode will be the same as the mode of the input
        image (im.mode)
    :param inPlace: Boolean.  If ``True``, the original image is modified in-place,
        and ``None`` is returned.  If ``False`` (default), a new
        :py:class:`~PIL.Image.Image` object is returned with the transform applied.
    :param flags: Integer (0-...) specifying additional flags
    :returns: Either None or a new :py:class:`~PIL.Image.Image` object, depending on
        the value of ``inPlace``
    :exception PyCMSError:
    """

    if outputMode is None:
        outputMode = im.mode

    if not isinstance(renderingIntent, int) or not (0 <= renderingIntent <= 3):
        msg = "renderingIntent must be an integer between 0 and 3"
        raise PyCMSError(msg)

    if not isinstance(flags, int) or not (0 <= flags <= _MAX_FLAG):
        msg = f"flags must be an integer between 0 and {_MAX_FLAG}"
        raise PyCMSError(msg)

    try:
        if not isinstance(inputProfile, ImageCmsProfile):
            inputProfile = ImageCmsProfile(inputProfile)
        if not isinstance(outputProfile, ImageCmsProfile):
            outputProfile = ImageCmsProfile(outputProfile)
        transform = ImageCmsTransform(
            inputProfile,
            outputProfile,
            im.mode,
            outputMode,
            renderingIntent,
            flags=flags,
        )
        if inPlace:
            transform.apply_in_place(im)
            imOut = None
        else:
            imOut = transform.apply(im)
    except (OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v

    return imOut


def getOpenProfile(
    profileFilename: str | SupportsRead[bytes] | core.CmsProfile,
) -> ImageCmsProfile:
    """
    (pyCMS) Opens an ICC profile file.

    The PyCMSProfile object can be passed back into pyCMS for use in creating
    transforms and such (as in ImageCms.buildTransformFromOpenProfiles()).

    If ``profileFilename`` is not a valid filename for an ICC profile,
    a :exc:`PyCMSError` will be raised.

    :param profileFilename: String, as a valid filename path to the ICC profile
        you wish to open, or a file-like object.
    :returns: A CmsProfile class object.
    :exception PyCMSError:
    """

    try:
        return ImageCmsProfile(profileFilename)
    except (OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def buildTransform(
    inputProfile: _CmsProfileCompatible,
    outputProfile: _CmsProfileCompatible,
    inMode: str,
    outMode: str,
    renderingIntent: Intent = Intent.PERCEPTUAL,
    flags: Flags = Flags.NONE,
) -> ImageCmsTransform:
    """
    (pyCMS) Builds an ICC transform mapping from the ``inputProfile`` to the
    ``outputProfile``. Use applyTransform to apply the transform to a given
    image.

    If the input or output profiles specified are not valid filenames, a
    :exc:`PyCMSError` will be raised. If an error occurs during creation
    of the transform, a :exc:`PyCMSError` will be raised.

    If ``inMode`` or ``outMode`` are not a mode supported by the ``outputProfile``
    (or by pyCMS), a :exc:`PyCMSError` will be raised.

    This function builds and returns an ICC transform from the ``inputProfile``
    to the ``outputProfile`` using the ``renderingIntent`` to determine what to do
    with out-of-gamut colors.  It will ONLY work for converting images that
    are in ``inMode`` to images that are in ``outMode`` color format (PIL mode,
    i.e. "RGB", "RGBA", "CMYK", etc.).

    Building the transform is a fair part of the overhead in
    ImageCms.profileToProfile(), so if you're planning on converting multiple
    images using the same input/output settings, this can save you time.
    Once you have a transform object, it can be used with
    ImageCms.applyProfile() to convert images without the need to re-compute
    the lookup table for the transform.

    The reason pyCMS returns a class object rather than a handle directly
    to the transform is that it needs to keep track of the PIL input/output
    modes that the transform is meant for.  These attributes are stored in
    the ``inMode`` and ``outMode`` attributes of the object (which can be
    manually overridden if you really want to, but I don't know of any
    time that would be of use, or would even work).

    :param inputProfile: String, as a valid filename path to the ICC input
        profile you wish to use for this transform, or a profile object
    :param outputProfile: String, as a valid filename path to the ICC output
        profile you wish to use for this transform, or a profile object
    :param inMode: String, as a valid PIL mode that the appropriate profile
        also supports (i.e. "RGB", "RGBA", "CMYK", etc.)
    :param outMode: String, as a valid PIL mode that the appropriate profile
        also supports (i.e. "RGB", "RGBA", "CMYK", etc.)
    :param renderingIntent: Integer (0-3) specifying the rendering intent you
        wish to use for the transform

            ImageCms.Intent.PERCEPTUAL            = 0 (DEFAULT)
            ImageCms.Intent.RELATIVE_COLORIMETRIC = 1
            ImageCms.Intent.SATURATION            = 2
            ImageCms.Intent.ABSOLUTE_COLORIMETRIC = 3

        see the pyCMS documentation for details on rendering intents and what
        they do.
    :param flags: Integer (0-...) specifying additional flags
    :returns: A CmsTransform class object.
    :exception PyCMSError:
    """

    if not isinstance(renderingIntent, int) or not (0 <= renderingIntent <= 3):
        msg = "renderingIntent must be an integer between 0 and 3"
        raise PyCMSError(msg)

    if not isinstance(flags, int) or not (0 <= flags <= _MAX_FLAG):
        msg = f"flags must be an integer between 0 and {_MAX_FLAG}"
        raise PyCMSError(msg)

    try:
        if not isinstance(inputProfile, ImageCmsProfile):
            inputProfile = ImageCmsProfile(inputProfile)
        if not isinstance(outputProfile, ImageCmsProfile):
            outputProfile = ImageCmsProfile(outputProfile)
        return ImageCmsTransform(
            inputProfile, outputProfile, inMode, outMode, renderingIntent, flags=flags
        )
    except (OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def buildProofTransform(
    inputProfile: _CmsProfileCompatible,
    outputProfile: _CmsProfileCompatible,
    proofProfile: _CmsProfileCompatible,
    inMode: str,
    outMode: str,
    renderingIntent: Intent = Intent.PERCEPTUAL,
    proofRenderingIntent: Intent = Intent.ABSOLUTE_COLORIMETRIC,
    flags: Flags = Flags.SOFTPROOFING,
) -> ImageCmsTransform:
    """
    (pyCMS) Builds an ICC transform mapping from the ``inputProfile`` to the
    ``outputProfile``, but tries to simulate the result that would be
    obtained on the ``proofProfile`` device.

    If the input, output, or proof profiles specified are not valid
    filenames, a :exc:`PyCMSError` will be raised.

    If an error occurs during creation of the transform,
    a :exc:`PyCMSError` will be raised.

    If ``inMode`` or ``outMode`` are not a mode supported by the ``outputProfile``
    (or by pyCMS), a :exc:`PyCMSError` will be raised.

    This function builds and returns an ICC transform from the ``inputProfile``
    to the ``outputProfile``, but tries to simulate the result that would be
    obtained on the ``proofProfile`` device using ``renderingIntent`` and
    ``proofRenderingIntent`` to determine what to do with out-of-gamut
    colors.  This is known as "soft-proofing".  It will ONLY work for
    converting images that are in ``inMode`` to images that are in outMode
    color format (PIL mode, i.e. "RGB", "RGBA", "CMYK", etc.).

    Usage of the resulting transform object is exactly the same as with
    ImageCms.buildTransform().

    Proof profiling is generally used when using an output device to get a
    good idea of what the final printed/displayed image would look like on
    the ``proofProfile`` device when it's quicker and easier to use the
    output device for judging color.  Generally, this means that the
    output device is a monitor, or a dye-sub printer (etc.), and the simulated
    device is something more expensive, complicated, or time consuming
    (making it difficult to make a real print for color judgement purposes).

    Soft-proofing basically functions by adjusting the colors on the
    output device to match the colors of the device being simulated. However,
    when the simulated device has a much wider gamut than the output
    device, you may obtain marginal results.

    :param inputProfile: String, as a valid filename path to the ICC input
        profile you wish to use for this transform, or a profile object
    :param outputProfile: String, as a valid filename path to the ICC output
        (monitor, usually) profile you wish to use for this transform, or a
        profile object
    :param proofProfile: String, as a valid filename path to the ICC proof
        profile you wish to use for this transform, or a profile object
    :param inMode: String, as a valid PIL mode that the appropriate profile
        also supports (i.e. "RGB", "RGBA", "CMYK", etc.)
    :param outMode: String, as a valid PIL mode that the appropriate profile
        also supports (i.e. "RGB", "RGBA", "CMYK", etc.)
    :param renderingIntent: Integer (0-3) specifying the rendering intent you
        wish to use for the input->proof (simulated) transform

            ImageCms.Intent.PERCEPTUAL            = 0 (DEFAULT)
            ImageCms.Intent.RELATIVE_COLORIMETRIC = 1
            ImageCms.Intent.SATURATION            = 2
            ImageCms.Intent.ABSOLUTE_COLORIMETRIC = 3

        see the pyCMS documentation for details on rendering intents and what
        they do.
    :param proofRenderingIntent: Integer (0-3) specifying the rendering intent
        you wish to use for proof->output transform

            ImageCms.Intent.PERCEPTUAL            = 0 (DEFAULT)
            ImageCms.Intent.RELATIVE_COLORIMETRIC = 1
            ImageCms.Intent.SATURATION            = 2
            ImageCms.Intent.ABSOLUTE_COLORIMETRIC = 3

        see the pyCMS documentation for details on rendering intents and what
        they do.
    :param flags: Integer (0-...) specifying additional flags
    :returns: A CmsTransform class object.
    :exception PyCMSError:
    """

    if not isinstance(renderingIntent, int) or not (0 <= renderingIntent <= 3):
        msg = "renderingIntent must be an integer between 0 and 3"
        raise PyCMSError(msg)

    if not isinstance(flags, int) or not (0 <= flags <= _MAX_FLAG):
        msg = f"flags must be an integer between 0 and {_MAX_FLAG}"
        raise PyCMSError(msg)

    try:
        if not isinstance(inputProfile, ImageCmsProfile):
            inputProfile = ImageCmsProfile(inputProfile)
        if not isinstance(outputProfile, ImageCmsProfile):
            outputProfile = ImageCmsProfile(outputProfile)
        if not isinstance(proofProfile, ImageCmsProfile):
            proofProfile = ImageCmsProfile(proofProfile)
        return ImageCmsTransform(
            inputProfile,
            outputProfile,
            inMode,
            outMode,
            renderingIntent,
            proofProfile,
            proofRenderingIntent,
            flags,
        )
    except (OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


buildTransformFromOpenProfiles = buildTransform
buildProofTransformFromOpenProfiles = buildProofTransform


def applyTransform(
    im: Image.Image, transform: ImageCmsTransform, inPlace: bool = False
) -> Image.Image | None:
    """
    (pyCMS) Applies a transform to a given image.

    If ``im.mode != transform.input_mode``, a :exc:`PyCMSError` is raised.

    If ``inPlace`` is ``True`` and ``transform.input_mode != transform.output_mode``, a
    :exc:`PyCMSError` is raised.

    If ``im.mode``, ``transform.input_mode`` or ``transform.output_mode`` is not
    supported by pyCMSdll or the profiles you used for the transform, a
    :exc:`PyCMSError` is raised.

    If an error occurs while the transform is being applied,
    a :exc:`PyCMSError` is raised.

    This function applies a pre-calculated transform (from
    ImageCms.buildTransform() or ImageCms.buildTransformFromOpenProfiles())
    to an image. The transform can be used for multiple images, saving
    considerable calculation time if doing the same conversion multiple times.

    If you want to modify im in-place instead of receiving a new image as
    the return value, set ``inPlace`` to ``True``.  This can only be done if
    ``transform.input_mode`` and ``transform.output_mode`` are the same, because we
    can't change the mode in-place (the buffer sizes for some modes are
    different).  The default behavior is to return a new :py:class:`~PIL.Image.Image`
    object of the same dimensions in mode ``transform.output_mode``.

    :param im: An :py:class:`~PIL.Image.Image` object, and ``im.mode`` must be the same
        as the ``input_mode`` supported by the transform.
    :param transform: A valid CmsTransform class object
    :param inPlace: Bool.  If ``True``, ``im`` is modified in place and ``None`` is
        returned, if ``False``, a new :py:class:`~PIL.Image.Image` object with the
        transform applied is returned (and ``im`` is not changed). The default is
        ``False``.
    :returns: Either ``None``, or a new :py:class:`~PIL.Image.Image` object,
        depending on the value of ``inPlace``. The profile will be returned in
        the image's ``info['icc_profile']``.
    :exception PyCMSError:
    """

    try:
        if inPlace:
            transform.apply_in_place(im)
            imOut = None
        else:
            imOut = transform.apply(im)
    except (TypeError, ValueError) as v:
        raise PyCMSError(v) from v

    return imOut


def createProfile(
    colorSpace: Literal["LAB", "XYZ", "sRGB"], colorTemp: SupportsFloat = 0
) -> core.CmsProfile:
    """
    (pyCMS) Creates a profile.

    If colorSpace not in ``["LAB", "XYZ", "sRGB"]``,
    a :exc:`PyCMSError` is raised.

    If using LAB and ``colorTemp`` is not a positive integer,
    a :exc:`PyCMSError` is raised.

    If an error occurs while creating the profile,
    a :exc:`PyCMSError` is raised.

    Use this function to create common profiles on-the-fly instead of
    having to supply a profile on disk and knowing the path to it.  It
    returns a normal CmsProfile object that can be passed to
    ImageCms.buildTransformFromOpenProfiles() to create a transform to apply
    to images.

    :param colorSpace: String, the color space of the profile you wish to
        create.
        Currently only "LAB", "XYZ", and "sRGB" are supported.
    :param colorTemp: Positive number for the white point for the profile, in
        degrees Kelvin (i.e. 5000, 6500, 9600, etc.).  The default is for D50
        illuminant if omitted (5000k).  colorTemp is ONLY applied to LAB
        profiles, and is ignored for XYZ and sRGB.
    :returns: A CmsProfile class object
    :exception PyCMSError:
    """

    if colorSpace not in ["LAB", "XYZ", "sRGB"]:
        msg = (
            f"Color space not supported for on-the-fly profile creation ({colorSpace})"
        )
        raise PyCMSError(msg)

    if colorSpace == "LAB":
        try:
            colorTemp = float(colorTemp)
        except (TypeError, ValueError) as e:
            msg = f'Color temperature must be numeric, "{colorTemp}" not valid'
            raise PyCMSError(msg) from e

    try:
        return core.createProfile(colorSpace, colorTemp)
    except (TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getProfileName(profile: _CmsProfileCompatible) -> str:
    """

    (pyCMS) Gets the internal product name for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile,
    a :exc:`PyCMSError` is raised If an error occurs while trying
    to obtain the name tag, a :exc:`PyCMSError` is raised.

    Use this function to obtain the INTERNAL name of the profile (stored
    in an ICC tag in the profile itself), usually the one used when the
    profile was originally created.  Sometimes this tag also contains
    additional information supplied by the creator.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: A string containing the internal name of the profile as stored
        in an ICC tag.
    :exception PyCMSError:
    """

    try:
        # add an extra newline to preserve pyCMS compatibility
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        # do it in python, not c.
        #    // name was "%s - %s" (model, manufacturer) || Description ,
        #    // but if the Model and Manufacturer were the same or the model
        #    // was long, Just the model,  in 1.x
        model = profile.profile.model
        manufacturer = profile.profile.manufacturer

        if not (model or manufacturer):
            return (profile.profile.profile_description or "") + "\n"
        if not manufacturer or (model and len(model) > 30):
            return f"{model}\n"
        return f"{model} - {manufacturer}\n"

    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getProfileInfo(profile: _CmsProfileCompatible) -> str:
    """
    (pyCMS) Gets the internal product information for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile,
    a :exc:`PyCMSError` is raised.

    If an error occurs while trying to obtain the info tag,
    a :exc:`PyCMSError` is raised.

    Use this function to obtain the information stored in the profile's
    info tag.  This often contains details about the profile, and how it
    was created, as supplied by the creator.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: A string containing the internal profile information stored in
        an ICC tag.
    :exception PyCMSError:
    """

    try:
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        # add an extra newline to preserve pyCMS compatibility
        # Python, not C. the white point bits weren't working well,
        # so skipping.
        # info was description \r\n\r\n copyright \r\n\r\n K007 tag \r\n\r\n whitepoint
        description = profile.profile.profile_description
        cpright = profile.profile.copyright
        elements = [element for element in (description, cpright) if element]
        return "\r\n\r\n".join(elements) + "\r\n\r\n"

    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getProfileCopyright(profile: _CmsProfileCompatible) -> str:
    """
    (pyCMS) Gets the copyright for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile, a
    :exc:`PyCMSError` is raised.

    If an error occurs while trying to obtain the copyright tag,
    a :exc:`PyCMSError` is raised.

    Use this function to obtain the information stored in the profile's
    copyright tag.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: A string containing the internal profile information stored in
        an ICC tag.
    :exception PyCMSError:
    """
    try:
        # add an extra newline to preserve pyCMS compatibility
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        return (profile.profile.copyright or "") + "\n"
    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getProfileManufacturer(profile: _CmsProfileCompatible) -> str:
    """
    (pyCMS) Gets the manufacturer for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile, a
    :exc:`PyCMSError` is raised.

    If an error occurs while trying to obtain the manufacturer tag, a
    :exc:`PyCMSError` is raised.

    Use this function to obtain the information stored in the profile's
    manufacturer tag.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: A string containing the internal profile information stored in
        an ICC tag.
    :exception PyCMSError:
    """
    try:
        # add an extra newline to preserve pyCMS compatibility
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        return (profile.profile.manufacturer or "") + "\n"
    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getProfileModel(profile: _CmsProfileCompatible) -> str:
    """
    (pyCMS) Gets the model for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile, a
    :exc:`PyCMSError` is raised.

    If an error occurs while trying to obtain the model tag,
    a :exc:`PyCMSError` is raised.

    Use this function to obtain the information stored in the profile's
    model tag.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: A string containing the internal profile information stored in
        an ICC tag.
    :exception PyCMSError:
    """

    try:
        # add an extra newline to preserve pyCMS compatibility
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        return (profile.profile.model or "") + "\n"
    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getProfileDescription(profile: _CmsProfileCompatible) -> str:
    """
    (pyCMS) Gets the description for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile, a
    :exc:`PyCMSError` is raised.

    If an error occurs while trying to obtain the description tag,
    a :exc:`PyCMSError` is raised.

    Use this function to obtain the information stored in the profile's
    description tag.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: A string containing the internal profile information stored in an
        ICC tag.
    :exception PyCMSError:
    """

    try:
        # add an extra newline to preserve pyCMS compatibility
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        return (profile.profile.profile_description or "") + "\n"
    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def getDefaultIntent(profile: _CmsProfileCompatible) -> int:
    """
    (pyCMS) Gets the default intent name for the given profile.

    If ``profile`` isn't a valid CmsProfile object or filename to a profile, a
    :exc:`PyCMSError` is raised.

    If an error occurs while trying to obtain the default intent, a
    :exc:`PyCMSError` is raised.

    Use this function to determine the default (and usually best optimized)
    rendering intent for this profile.  Most profiles support multiple
    rendering intents, but are intended mostly for one type of conversion.
    If you wish to use a different intent than returned, use
    ImageCms.isIntentSupported() to verify it will work first.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :returns: Integer 0-3 specifying the default rendering intent for this
        profile.

            ImageCms.Intent.PERCEPTUAL            = 0 (DEFAULT)
            ImageCms.Intent.RELATIVE_COLORIMETRIC = 1
            ImageCms.Intent.SATURATION            = 2
            ImageCms.Intent.ABSOLUTE_COLORIMETRIC = 3

        see the pyCMS documentation for details on rendering intents and what
            they do.
    :exception PyCMSError:
    """

    try:
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        return profile.profile.rendering_intent
    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def isIntentSupported(
    profile: _CmsProfileCompatible, intent: Intent, direction: Direction
) -> Literal[-1, 1]:
    """
    (pyCMS) Checks if a given intent is supported.

    Use this function to verify that you can use your desired
    ``intent`` with ``profile``, and that ``profile`` can be used for the
    input/output/proof profile as you desire.

    Some profiles are created specifically for one "direction", can cannot
    be used for others. Some profiles can only be used for certain
    rendering intents, so it's best to either verify this before trying
    to create a transform with them (using this function), or catch the
    potential :exc:`PyCMSError` that will occur if they don't
    support the modes you select.

    :param profile: EITHER a valid CmsProfile object, OR a string of the
        filename of an ICC profile.
    :param intent: Integer (0-3) specifying the rendering intent you wish to
        use with this profile

            ImageCms.Intent.PERCEPTUAL            = 0 (DEFAULT)
            ImageCms.Intent.RELATIVE_COLORIMETRIC = 1
            ImageCms.Intent.SATURATION            = 2
            ImageCms.Intent.ABSOLUTE_COLORIMETRIC = 3

        see the pyCMS documentation for details on rendering intents and what
            they do.
    :param direction: Integer specifying if the profile is to be used for
        input, output, or proof

            INPUT  = 0 (or use ImageCms.Direction.INPUT)
            OUTPUT = 1 (or use ImageCms.Direction.OUTPUT)
            PROOF  = 2 (or use ImageCms.Direction.PROOF)

    :returns: 1 if the intent/direction are supported, -1 if they are not.
    :exception PyCMSError:
    """

    try:
        if not isinstance(profile, ImageCmsProfile):
            profile = ImageCmsProfile(profile)
        # FIXME: I get different results for the same data w. different
        # compilers.  Bug in LittleCMS or in the binding?
        if profile.profile.is_intent_supported(intent, direction):
            return 1
        else:
            return -1
    except (AttributeError, OSError, TypeError, ValueError) as v:
        raise PyCMSError(v) from v


def versions() -> tuple[str, str | None, str, str]:
    """
    (pyCMS) Fetches versions.
    """

    deprecate(
        "PIL.ImageCms.versions()",
        12,
        '(PIL.features.version("littlecms2"), sys.version, PIL.__version__)',
    )
    return _VERSION, core.littlecms_version, sys.version.split()[0], __version__
