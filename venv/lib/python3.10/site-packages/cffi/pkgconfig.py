# pkg-config, https://www.freedesktop.org/wiki/Software/pkg-config/ integration for cffi
import sys, os, subprocess

from .error import PkgConfigError


def merge_flags(cfg1, cfg2):
    """Merge values from cffi config flags cfg2 to cf1

    Example:
        merge_flags({"libraries": ["one"]}, {"libraries": ["two"]})
        {"libraries": ["one", "two"]}
    """
    for key, value in cfg2.items():
        if key not in cfg1:
            cfg1[key] = value
        else:
            if not isinstance(cfg1[key], list):
                raise TypeError("cfg1[%r] should be a list of strings" % (key,))
            if not isinstance(value, list):
                raise TypeError("cfg2[%r] should be a list of strings" % (key,))
            cfg1[key].extend(value)
    return cfg1


def call(libname, flag, encoding=sys.getfilesystemencoding()):
    """Calls pkg-config and returns the output if found
    """
    a = ["pkg-config", "--print-errors"]
    a.append(flag)
    a.append(libname)
    try:
        pc = subprocess.Popen(a, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except EnvironmentError as e:
        raise PkgConfigError("cannot run pkg-config: %s" % (str(e).strip(),))

    bout, berr = pc.communicate()
    if pc.returncode != 0:
        try:
            berr = berr.decode(encoding)
        except Exception:
            pass
        raise PkgConfigError(berr.strip())

    if sys.version_info >= (3,) and not isinstance(bout, str):   # Python 3.x
        try:
            bout = bout.decode(encoding)
        except UnicodeDecodeError:
            raise PkgConfigError("pkg-config %s %s returned bytes that cannot "
                                 "be decoded with encoding %r:\n%r" %
                                 (flag, libname, encoding, bout))

    if os.altsep != '\\' and '\\' in bout:
        raise PkgConfigError("pkg-config %s %s returned an unsupported "
                             "backslash-escaped output:\n%r" %
                             (flag, libname, bout))
    return bout


def flags_from_pkgconfig(libs):
    r"""Return compiler line flags for FFI.set_source based on pkg-config output

    Usage
        ...
        ffibuilder.set_source("_foo", pkgconfig = ["libfoo", "libbar >= 1.8.3"])

    If pkg-config is installed on build machine, then arguments include_dirs,
    library_dirs, libraries, define_macros, extra_compile_args and
    extra_link_args are extended with an output of pkg-config for libfoo and
    libbar.

    Raises PkgConfigError in case the pkg-config call fails.
    """

    def get_include_dirs(string):
        return [x[2:] for x in string.split() if x.startswith("-I")]

    def get_library_dirs(string):
        return [x[2:] for x in string.split() if x.startswith("-L")]

    def get_libraries(string):
        return [x[2:] for x in string.split() if x.startswith("-l")]

    # convert -Dfoo=bar to list of tuples [("foo", "bar")] expected by distutils
    def get_macros(string):
        def _macro(x):
            x = x[2:]    # drop "-D"
            if '=' in x:
                return tuple(x.split("=", 1))  # "-Dfoo=bar" => ("foo", "bar")
            else:
                return (x, None)               # "-Dfoo" => ("foo", None)
        return [_macro(x) for x in string.split() if x.startswith("-D")]

    def get_other_cflags(string):
        return [x for x in string.split() if not x.startswith("-I") and
                                             not x.startswith("-D")]

    def get_other_libs(string):
        return [x for x in string.split() if not x.startswith("-L") and
                                             not x.startswith("-l")]

    # return kwargs for given libname
    def kwargs(libname):
        fse = sys.getfilesystemencoding()
        all_cflags = call(libname, "--cflags")
        all_libs = call(libname, "--libs")
        return {
            "include_dirs": get_include_dirs(all_cflags),
            "library_dirs": get_library_dirs(all_libs),
            "libraries": get_libraries(all_libs),
            "define_macros": get_macros(all_cflags),
            "extra_compile_args": get_other_cflags(all_cflags),
            "extra_link_args": get_other_libs(all_libs),
            }

    # merge all arguments together
    ret = {}
    for libname in libs:
        lib_flags = kwargs(libname)
        merge_flags(ret, lib_flags)
    return ret
