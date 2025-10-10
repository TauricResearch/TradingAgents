#!/usr/bin/env python3
# Copyright (c) 2005-2010 ActiveState Software Inc.
# Copyright (c) 2013 Eddy Petrișor

# flake8: noqa

"""
This file is directly from
https://github.com/ActiveState/appdirs/blob/3fe6a83776843a46f20c2e5587afcffe05e03b39/appdirs.py

The license of https://github.com/ActiveState/appdirs copied below:


# This is the MIT license

Copyright (c) 2010 ActiveState Software Inc.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

"""Utilities for determining application-specific dirs.

See <https://github.com/ActiveState/appdirs> for details and usage.
"""
# Dev Notes:
# - MSDN on where to store app data files:
#   http://support.microsoft.com/default.aspx?scid=kb;en-us;310294#XSLTH3194121123120121120120
# - Mac OS X: http://developer.apple.com/documentation/MacOSX/Conceptual/BPFileSystem/index.html
# - XDG spec for Un*x: https://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html

__version__ = "1.4.4"
__version_info__ = tuple(int(segment) for segment in __version__.split("."))


import sys
import os

unicode = str

if sys.platform.startswith('java'):
    import platform
    os_name = platform.java_ver()[3][0]
    if os_name.startswith('Windows'): # "Windows XP", "Windows 7", etc.
        system = 'win32'
    elif os_name.startswith('Mac'): # "Mac OS X", etc.
        system = 'darwin'
    else: # "Linux", "SunOS", "FreeBSD", etc.
        # Setting this to "linux2" is not ideal, but only Windows or Mac
        # are actually checked for and the rest of the module expects
        # *sys.platform* style strings.
        system = 'linux2'
else:
    system = sys.platform


def user_cache_dir(appname=None, appauthor=None, version=None, opinion=True):
    r"""Return full path to the user-specific cache dir for this application.

        "appname" is the name of application.
            If None, just the system directory is returned.
        "appauthor" (only used on Windows) is the name of the
            appauthor or distributing body for this application. Typically
            it is the owning company name. This falls back to appname. You may
            pass False to disable it.
        "version" is an optional version path element to append to the
            path. You might want to use this if you want multiple versions
            of your app to be able to run independently. If used, this
            would typically be "<major>.<minor>".
            Only applied when appname is present.
        "opinion" (boolean) can be False to disable the appending of
            "Cache" to the base app data dir for Windows. See
            discussion below.

    Typical user cache directories are:
        Mac OS X:   ~/Library/Caches/<AppName>
        Unix:       ~/.cache/<AppName> (XDG default)
        Win XP:     C:\Documents and Settings\<username>\Local Settings\Application Data\<AppAuthor>\<AppName>\Cache
        Vista:      C:\Users\<username>\AppData\Local\<AppAuthor>\<AppName>\Cache

    On Windows the only suggestion in the MSDN docs is that local settings go in
    the `CSIDL_LOCAL_APPDATA` directory. This is identical to the non-roaming
    app data dir (the default returned by `user_data_dir` above). Apps typically
    put cache data somewhere *under* the given dir here. Some examples:
        ...\Mozilla\Firefox\Profiles\<ProfileName>\Cache
        ...\Acme\SuperApp\Cache\1.0
    OPINION: This function appends "Cache" to the `CSIDL_LOCAL_APPDATA` value.
    This can be disabled with the `opinion=False` option.
    """
    if system == "win32":
        if appauthor is None:
            appauthor = appname
        path = os.path.normpath(_get_win_folder("CSIDL_LOCAL_APPDATA"))
        if appname:
            if appauthor is not False:
                path = os.path.join(path, appauthor, appname)
            else:
                path = os.path.join(path, appname)
            if opinion:
                path = os.path.join(path, "Cache")
    elif system == 'darwin':
        path = os.path.expanduser('~/Library/Caches')
        if appname:
            path = os.path.join(path, appname)
    else:
        path = os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
        if appname:
            path = os.path.join(path, appname)
    if appname and version:
        path = os.path.join(path, version)
    return path


#---- internal support stuff

def _get_win_folder_from_registry(csidl_name):
    """This is a fallback technique at best. I'm not sure if using the
    registry for this guarantees us the correct answer for all CSIDL_*
    names.
    """
    import winreg as _winreg

    shell_folder_name = {
        "CSIDL_APPDATA": "AppData",
        "CSIDL_COMMON_APPDATA": "Common AppData",
        "CSIDL_LOCAL_APPDATA": "Local AppData",
    }[csidl_name]

    key = _winreg.OpenKey(
        _winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
    )
    dir, type = _winreg.QueryValueEx(key, shell_folder_name)
    return dir


def _get_win_folder_with_pywin32(csidl_name):
    from win32com.shell import shellcon, shell
    dir = shell.SHGetFolderPath(0, getattr(shellcon, csidl_name), 0, 0)
    # Try to make this a unicode path because SHGetFolderPath does
    # not return unicode strings when there is unicode data in the
    # path.
    try:
        dir = unicode(dir)

        # Downgrade to short path name if have highbit chars. See
        # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
        has_high_char = False
        for c in dir:
            if ord(c) > 255:
                has_high_char = True
                break
        if has_high_char:
            try:
                import win32api
                dir = win32api.GetShortPathName(dir)
            except ImportError:
                pass
    except UnicodeError:
        pass
    return dir


def _get_win_folder_with_ctypes(csidl_name):
    import ctypes

    csidl_const = {
        "CSIDL_APPDATA": 26,
        "CSIDL_COMMON_APPDATA": 35,
        "CSIDL_LOCAL_APPDATA": 28,
    }[csidl_name]

    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl_const, None, 0, buf)

    # Downgrade to short path name if have highbit chars. See
    # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
    has_high_char = False
    for c in buf:
        if ord(c) > 255:
            has_high_char = True
            break
    if has_high_char:
        buf2 = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(buf.value, buf2, 1024):
            buf = buf2

    return buf.value

def _get_win_folder_with_jna(csidl_name):
    import array
    from com.sun import jna
    from com.sun.jna.platform import win32

    buf_size = win32.WinDef.MAX_PATH * 2
    buf = array.zeros('c', buf_size)
    shell = win32.Shell32.INSTANCE
    shell.SHGetFolderPath(None, getattr(win32.ShlObj, csidl_name), None, win32.ShlObj.SHGFP_TYPE_CURRENT, buf)
    dir = jna.Native.toString(buf.tostring()).rstrip("\0")

    # Downgrade to short path name if have highbit chars. See
    # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
    has_high_char = False
    for c in dir:
        if ord(c) > 255:
            has_high_char = True
            break
    if has_high_char:
        buf = array.zeros('c', buf_size)
        kernel = win32.Kernel32.INSTANCE
        if kernel.GetShortPathName(dir, buf, buf_size):
            dir = jna.Native.toString(buf.tostring()).rstrip("\0")

    return dir

if system == "win32":
    try:
        import win32com.shell
        _get_win_folder = _get_win_folder_with_pywin32
    except ImportError:
        try:
            from ctypes import windll
            _get_win_folder = _get_win_folder_with_ctypes
        except ImportError:
            try:
                import com.sun.jna
                _get_win_folder = _get_win_folder_with_jna
            except ImportError:
                _get_win_folder = _get_win_folder_from_registry
