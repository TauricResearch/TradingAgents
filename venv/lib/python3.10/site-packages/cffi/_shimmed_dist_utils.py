"""
Temporary shim module to indirect the bits of distutils we need from setuptools/distutils while providing useful
error messages beyond `No module named 'distutils' on Python >= 3.12, or when setuptools' vendored distutils is broken.

This is a compromise to avoid a hard-dep on setuptools for Python >= 3.12, since many users don't need runtime compilation support from CFFI.
"""
import sys

try:
    # import setuptools first; this is the most robust way to ensure its embedded distutils is available
    # (the .pth shim should usually work, but this is even more robust)
    import setuptools
except Exception as ex:
    if sys.version_info >= (3, 12):
        # Python 3.12 has no built-in distutils to fall back on, so any import problem is fatal
        raise Exception("This CFFI feature requires setuptools on Python >= 3.12. The setuptools module is missing or non-functional.") from ex

    # silently ignore on older Pythons (support fallback to stdlib distutils where available)
else:
    del setuptools

try:
    # bring in just the bits of distutils we need, whether they really came from setuptools or stdlib-embedded distutils
    from distutils import log, sysconfig
    from distutils.ccompiler import CCompiler
    from distutils.command.build_ext import build_ext
    from distutils.core import Distribution, Extension
    from distutils.dir_util import mkpath
    from distutils.errors import DistutilsSetupError, CompileError, LinkError
    from distutils.log import set_threshold, set_verbosity

    if sys.platform == 'win32':
        try:
            # FUTURE: msvc9compiler module was removed in setuptools 74; consider removing, as it's only used by an ancient patch in `recompiler`
            from distutils.msvc9compiler import MSVCCompiler
        except ImportError:
            MSVCCompiler = None
except Exception as ex:
    if sys.version_info >= (3, 12):
        raise Exception("This CFFI feature requires setuptools on Python >= 3.12. Please install the setuptools package.") from ex

    # anything older, just let the underlying distutils import error fly
    raise Exception("This CFFI feature requires distutils. Please install the distutils or setuptools package.") from ex

del sys
