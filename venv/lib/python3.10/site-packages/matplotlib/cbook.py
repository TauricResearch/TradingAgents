"""
A collection of utility functions and classes.  Originally, many
(but not all) were from the Python Cookbook -- hence the name cbook.
"""

import collections
import collections.abc
import contextlib
import functools
import gzip
import itertools
import math
import operator
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import traceback
import types
import weakref

import numpy as np

try:
    from numpy.exceptions import VisibleDeprecationWarning  # numpy >= 1.25
except ImportError:
    from numpy import VisibleDeprecationWarning

import matplotlib
from matplotlib import _api, _c_internal_utils


class _ExceptionInfo:
    """
    A class to carry exception information around.

    This is used to store and later raise exceptions. It's an alternative to
    directly storing Exception instances that circumvents traceback-related
    issues: caching tracebacks can keep user's objects in local namespaces
    alive indefinitely, which can lead to very surprising memory issues for
    users and result in incorrect tracebacks.
    """

    def __init__(self, cls, *args):
        self._cls = cls
        self._args = args

    @classmethod
    def from_exception(cls, exc):
        return cls(type(exc), *exc.args)

    def to_exception(self):
        return self._cls(*self._args)


def _get_running_interactive_framework():
    """
    Return the interactive framework whose event loop is currently running, if
    any, or "headless" if no event loop can be started, or None.

    Returns
    -------
    Optional[str]
        One of the following values: "qt", "gtk3", "gtk4", "wx", "tk",
        "macosx", "headless", ``None``.
    """
    # Use ``sys.modules.get(name)`` rather than ``name in sys.modules`` as
    # entries can also have been explicitly set to None.
    QtWidgets = (
        sys.modules.get("PyQt6.QtWidgets")
        or sys.modules.get("PySide6.QtWidgets")
        or sys.modules.get("PyQt5.QtWidgets")
        or sys.modules.get("PySide2.QtWidgets")
    )
    if QtWidgets and QtWidgets.QApplication.instance():
        return "qt"
    Gtk = sys.modules.get("gi.repository.Gtk")
    if Gtk:
        if Gtk.MAJOR_VERSION == 4:
            from gi.repository import GLib
            if GLib.main_depth():
                return "gtk4"
        if Gtk.MAJOR_VERSION == 3 and Gtk.main_level():
            return "gtk3"
    wx = sys.modules.get("wx")
    if wx and wx.GetApp():
        return "wx"
    tkinter = sys.modules.get("tkinter")
    if tkinter:
        codes = {tkinter.mainloop.__code__, tkinter.Misc.mainloop.__code__}
        for frame in sys._current_frames().values():
            while frame:
                if frame.f_code in codes:
                    return "tk"
                frame = frame.f_back
        # Preemptively break reference cycle between locals and the frame.
        del frame
    macosx = sys.modules.get("matplotlib.backends._macosx")
    if macosx and macosx.event_loop_is_running():
        return "macosx"
    if not _c_internal_utils.display_is_valid():
        return "headless"
    return None


def _exception_printer(exc):
    if _get_running_interactive_framework() in ["headless", None]:
        raise exc
    else:
        traceback.print_exc()


class _StrongRef:
    """
    Wrapper similar to a weakref, but keeping a strong reference to the object.
    """

    def __init__(self, obj):
        self._obj = obj

    def __call__(self):
        return self._obj

    def __eq__(self, other):
        return isinstance(other, _StrongRef) and self._obj == other._obj

    def __hash__(self):
        return hash(self._obj)


def _weak_or_strong_ref(func, callback):
    """
    Return a `WeakMethod` wrapping *func* if possible, else a `_StrongRef`.
    """
    try:
        return weakref.WeakMethod(func, callback)
    except TypeError:
        return _StrongRef(func)


class _UnhashDict:
    """
    A minimal dict-like class that also supports unhashable keys, storing them
    in a list of key-value pairs.

    This class only implements the interface needed for `CallbackRegistry`, and
    tries to minimize the overhead for the hashable case.
    """

    def __init__(self, pairs):
        self._dict = {}
        self._pairs = []
        for k, v in pairs:
            self[k] = v

    def __setitem__(self, key, value):
        try:
            self._dict[key] = value
        except TypeError:
            for i, (k, v) in enumerate(self._pairs):
                if k == key:
                    self._pairs[i] = (key, value)
                    break
            else:
                self._pairs.append((key, value))

    def __getitem__(self, key):
        try:
            return self._dict[key]
        except TypeError:
            pass
        for k, v in self._pairs:
            if k == key:
                return v
        raise KeyError(key)

    def pop(self, key, *args):
        try:
            if key in self._dict:
                return self._dict.pop(key)
        except TypeError:
            for i, (k, v) in enumerate(self._pairs):
                if k == key:
                    del self._pairs[i]
                    return v
        if args:
            return args[0]
        raise KeyError(key)

    def __iter__(self):
        yield from self._dict
        for k, v in self._pairs:
            yield k


class CallbackRegistry:
    """
    Handle registering, processing, blocking, and disconnecting
    for a set of signals and callbacks:

        >>> def oneat(x):
        ...     print('eat', x)
        >>> def ondrink(x):
        ...     print('drink', x)

        >>> from matplotlib.cbook import CallbackRegistry
        >>> callbacks = CallbackRegistry()

        >>> id_eat = callbacks.connect('eat', oneat)
        >>> id_drink = callbacks.connect('drink', ondrink)

        >>> callbacks.process('drink', 123)
        drink 123
        >>> callbacks.process('eat', 456)
        eat 456
        >>> callbacks.process('be merry', 456)   # nothing will be called

        >>> callbacks.disconnect(id_eat)
        >>> callbacks.process('eat', 456)        # nothing will be called

        >>> with callbacks.blocked(signal='drink'):
        ...     callbacks.process('drink', 123)  # nothing will be called
        >>> callbacks.process('drink', 123)
        drink 123

    In practice, one should always disconnect all callbacks when they are
    no longer needed to avoid dangling references (and thus memory leaks).
    However, real code in Matplotlib rarely does so, and due to its design,
    it is rather difficult to place this kind of code.  To get around this,
    and prevent this class of memory leaks, we instead store weak references
    to bound methods only, so when the destination object needs to die, the
    CallbackRegistry won't keep it alive.

    Parameters
    ----------
    exception_handler : callable, optional
       If not None, *exception_handler* must be a function that takes an
       `Exception` as single parameter.  It gets called with any `Exception`
       raised by the callbacks during `CallbackRegistry.process`, and may
       either re-raise the exception or handle it in another manner.

       The default handler prints the exception (with `traceback.print_exc`) if
       an interactive event loop is running; it re-raises the exception if no
       interactive event loop is running.

    signals : list, optional
        If not None, *signals* is a list of signals that this registry handles:
        attempting to `process` or to `connect` to a signal not in the list
        throws a `ValueError`.  The default, None, does not restrict the
        handled signals.
    """

    # We maintain two mappings:
    #   callbacks: signal -> {cid -> weakref-to-callback}
    #   _func_cid_map: {(signal, weakref-to-callback) -> cid}

    def __init__(self, exception_handler=_exception_printer, *, signals=None):
        self._signals = None if signals is None else list(signals)  # Copy it.
        self.exception_handler = exception_handler
        self.callbacks = {}
        self._cid_gen = itertools.count()
        self._func_cid_map = _UnhashDict([])
        # A hidden variable that marks cids that need to be pickled.
        self._pickled_cids = set()

    def __getstate__(self):
        return {
            **vars(self),
            # In general, callbacks may not be pickled, so we just drop them,
            # unless directed otherwise by self._pickled_cids.
            "callbacks": {s: {cid: proxy() for cid, proxy in d.items()
                              if cid in self._pickled_cids}
                          for s, d in self.callbacks.items()},
            # It is simpler to reconstruct this from callbacks in __setstate__.
            "_func_cid_map": None,
            "_cid_gen": next(self._cid_gen)
        }

    def __setstate__(self, state):
        cid_count = state.pop('_cid_gen')
        vars(self).update(state)
        self.callbacks = {
            s: {cid: _weak_or_strong_ref(func, functools.partial(self._remove_proxy, s))
                for cid, func in d.items()}
            for s, d in self.callbacks.items()}
        self._func_cid_map = _UnhashDict(
            ((s, proxy), cid)
            for s, d in self.callbacks.items() for cid, proxy in d.items())
        self._cid_gen = itertools.count(cid_count)

    def connect(self, signal, func):
        """Register *func* to be called when signal *signal* is generated."""
        if self._signals is not None:
            _api.check_in_list(self._signals, signal=signal)
        proxy = _weak_or_strong_ref(func, functools.partial(self._remove_proxy, signal))
        try:
            return self._func_cid_map[signal, proxy]
        except KeyError:
            cid = self._func_cid_map[signal, proxy] = next(self._cid_gen)
            self.callbacks.setdefault(signal, {})[cid] = proxy
            return cid

    def _connect_picklable(self, signal, func):
        """
        Like `.connect`, but the callback is kept when pickling/unpickling.

        Currently internal-use only.
        """
        cid = self.connect(signal, func)
        self._pickled_cids.add(cid)
        return cid

    # Keep a reference to sys.is_finalizing, as sys may have been cleared out
    # at that point.
    def _remove_proxy(self, signal, proxy, *, _is_finalizing=sys.is_finalizing):
        if _is_finalizing():
            # Weakrefs can't be properly torn down at that point anymore.
            return
        cid = self._func_cid_map.pop((signal, proxy), None)
        if cid is not None:
            del self.callbacks[signal][cid]
            self._pickled_cids.discard(cid)
        else:  # Not found
            return
        if len(self.callbacks[signal]) == 0:  # Clean up empty dicts
            del self.callbacks[signal]

    def disconnect(self, cid):
        """
        Disconnect the callback registered with callback id *cid*.

        No error is raised if such a callback does not exist.
        """
        self._pickled_cids.discard(cid)
        for signal, proxy in self._func_cid_map:
            if self._func_cid_map[signal, proxy] == cid:
                break
        else:  # Not found
            return
        assert self.callbacks[signal][cid] == proxy
        del self.callbacks[signal][cid]
        self._func_cid_map.pop((signal, proxy))
        if len(self.callbacks[signal]) == 0:  # Clean up empty dicts
            del self.callbacks[signal]

    def process(self, s, *args, **kwargs):
        """
        Process signal *s*.

        All of the functions registered to receive callbacks on *s* will be
        called with ``*args`` and ``**kwargs``.
        """
        if self._signals is not None:
            _api.check_in_list(self._signals, signal=s)
        for ref in list(self.callbacks.get(s, {}).values()):
            func = ref()
            if func is not None:
                try:
                    func(*args, **kwargs)
                # this does not capture KeyboardInterrupt, SystemExit,
                # and GeneratorExit
                except Exception as exc:
                    if self.exception_handler is not None:
                        self.exception_handler(exc)
                    else:
                        raise

    @contextlib.contextmanager
    def blocked(self, *, signal=None):
        """
        Block callback signals from being processed.

        A context manager to temporarily block/disable callback signals
        from being processed by the registered listeners.

        Parameters
        ----------
        signal : str, optional
            The callback signal to block. The default is to block all signals.
        """
        orig = self.callbacks
        try:
            if signal is None:
                # Empty out the callbacks
                self.callbacks = {}
            else:
                # Only remove the specific signal
                self.callbacks = {k: orig[k] for k in orig if k != signal}
            yield
        finally:
            self.callbacks = orig


class silent_list(list):
    """
    A list with a short ``repr()``.

    This is meant to be used for a homogeneous list of artists, so that they
    don't cause long, meaningless output.

    Instead of ::

        [<matplotlib.lines.Line2D object at 0x7f5749fed3c8>,
         <matplotlib.lines.Line2D object at 0x7f5749fed4e0>,
         <matplotlib.lines.Line2D object at 0x7f5758016550>]

    one will get ::

        <a list of 3 Line2D objects>

    If ``self.type`` is None, the type name is obtained from the first item in
    the list (if any).
    """

    def __init__(self, type, seq=None):
        self.type = type
        if seq is not None:
            self.extend(seq)

    def __repr__(self):
        if self.type is not None or len(self) != 0:
            tp = self.type if self.type is not None else type(self[0]).__name__
            return f"<a list of {len(self)} {tp} objects>"
        else:
            return "<an empty list>"


def _local_over_kwdict(
        local_var, kwargs, *keys,
        warning_cls=_api.MatplotlibDeprecationWarning):
    out = local_var
    for key in keys:
        kwarg_val = kwargs.pop(key, None)
        if kwarg_val is not None:
            if out is None:
                out = kwarg_val
            else:
                _api.warn_external(f'"{key}" keyword argument will be ignored',
                                   warning_cls)
    return out


def strip_math(s):
    """
    Remove latex formatting from mathtext.

    Only handles fully math and fully non-math strings.
    """
    if len(s) >= 2 and s[0] == s[-1] == "$":
        s = s[1:-1]
        for tex, plain in [
                (r"\times", "x"),  # Specifically for Formatter support.
                (r"\mathdefault", ""),
                (r"\rm", ""),
                (r"\cal", ""),
                (r"\tt", ""),
                (r"\it", ""),
                ("\\", ""),
                ("{", ""),
                ("}", ""),
        ]:
            s = s.replace(tex, plain)
    return s


def _strip_comment(s):
    """Strip everything from the first unquoted #."""
    pos = 0
    while True:
        quote_pos = s.find('"', pos)
        hash_pos = s.find('#', pos)
        if quote_pos < 0:
            without_comment = s if hash_pos < 0 else s[:hash_pos]
            return without_comment.strip()
        elif 0 <= hash_pos < quote_pos:
            return s[:hash_pos].strip()
        else:
            closing_quote_pos = s.find('"', quote_pos + 1)
            if closing_quote_pos < 0:
                raise ValueError(
                    f"Missing closing quote in: {s!r}. If you need a double-"
                    'quote inside a string, use escaping: e.g. "the \" char"')
            pos = closing_quote_pos + 1  # behind closing quote


def is_writable_file_like(obj):
    """Return whether *obj* looks like a file object with a *write* method."""
    return callable(getattr(obj, 'write', None))


def file_requires_unicode(x):
    """
    Return whether the given writable file-like object requires Unicode to be
    written to it.
    """
    try:
        x.write(b'')
    except TypeError:
        return True
    else:
        return False


def to_filehandle(fname, flag='r', return_opened=False, encoding=None):
    """
    Convert a path to an open file handle or pass-through a file-like object.

    Consider using `open_file_cm` instead, as it allows one to properly close
    newly created file objects more easily.

    Parameters
    ----------
    fname : str or path-like or file-like
        If `str` or `os.PathLike`, the file is opened using the flags specified
        by *flag* and *encoding*.  If a file-like object, it is passed through.
    flag : str, default: 'r'
        Passed as the *mode* argument to `open` when *fname* is `str` or
        `os.PathLike`; ignored if *fname* is file-like.
    return_opened : bool, default: False
        If True, return both the file object and a boolean indicating whether
        this was a new file (that the caller needs to close).  If False, return
        only the new file.
    encoding : str or None, default: None
        Passed as the *mode* argument to `open` when *fname* is `str` or
        `os.PathLike`; ignored if *fname* is file-like.

    Returns
    -------
    fh : file-like
    opened : bool
        *opened* is only returned if *return_opened* is True.
    """
    if isinstance(fname, os.PathLike):
        fname = os.fspath(fname)
    if isinstance(fname, str):
        if fname.endswith('.gz'):
            fh = gzip.open(fname, flag)
        elif fname.endswith('.bz2'):
            # python may not be compiled with bz2 support,
            # bury import until we need it
            import bz2
            fh = bz2.BZ2File(fname, flag)
        else:
            fh = open(fname, flag, encoding=encoding)
        opened = True
    elif hasattr(fname, 'seek'):
        fh = fname
        opened = False
    else:
        raise ValueError('fname must be a PathLike or file handle')
    if return_opened:
        return fh, opened
    return fh


def open_file_cm(path_or_file, mode="r", encoding=None):
    r"""Pass through file objects and context-manage path-likes."""
    fh, opened = to_filehandle(path_or_file, mode, True, encoding)
    return fh if opened else contextlib.nullcontext(fh)


def is_scalar_or_string(val):
    """Return whether the given object is a scalar or string like."""
    return isinstance(val, str) or not np.iterable(val)


def get_sample_data(fname, asfileobj=True):
    """
    Return a sample data file.  *fname* is a path relative to the
    :file:`mpl-data/sample_data` directory.  If *asfileobj* is `True`
    return a file object, otherwise just a file path.

    Sample data files are stored in the 'mpl-data/sample_data' directory within
    the Matplotlib package.

    If the filename ends in .gz, the file is implicitly ungzipped.  If the
    filename ends with .npy or .npz, and *asfileobj* is `True`, the file is
    loaded with `numpy.load`.
    """
    path = _get_data_path('sample_data', fname)
    if asfileobj:
        suffix = path.suffix.lower()
        if suffix == '.gz':
            return gzip.open(path)
        elif suffix in ['.npy', '.npz']:
            return np.load(path)
        elif suffix in ['.csv', '.xrc', '.txt']:
            return path.open('r')
        else:
            return path.open('rb')
    else:
        return str(path)


def _get_data_path(*args):
    """
    Return the `pathlib.Path` to a resource file provided by Matplotlib.

    ``*args`` specify a path relative to the base data path.
    """
    return Path(matplotlib.get_data_path(), *args)


def flatten(seq, scalarp=is_scalar_or_string):
    """
    Return a generator of flattened nested containers.

    For example:

        >>> from matplotlib.cbook import flatten
        >>> l = (('John', ['Hunter']), (1, 23), [[([42, (5, 23)], )]])
        >>> print(list(flatten(l)))
        ['John', 'Hunter', 1, 23, 42, 5, 23]

    By: Composite of Holger Krekel and Luther Blissett
    From: https://code.activestate.com/recipes/121294-simple-generator-for-flattening-nested-containers/
    and Recipe 1.12 in cookbook
    """  # noqa: E501
    for item in seq:
        if scalarp(item) or item is None:
            yield item
        else:
            yield from flatten(item, scalarp)


class _Stack:
    """
    Stack of elements with a movable cursor.

    Mimics home/back/forward in a web browser.
    """

    def __init__(self):
        self._pos = -1
        self._elements = []

    def clear(self):
        """Empty the stack."""
        self._pos = -1
        self._elements = []

    def __call__(self):
        """Return the current element, or None."""
        return self._elements[self._pos] if self._elements else None

    def __len__(self):
        return len(self._elements)

    def __getitem__(self, ind):
        return self._elements[ind]

    def forward(self):
        """Move the position forward and return the current element."""
        self._pos = min(self._pos + 1, len(self._elements) - 1)
        return self()

    def back(self):
        """Move the position back and return the current element."""
        self._pos = max(self._pos - 1, 0)
        return self()

    def push(self, o):
        """
        Push *o* to the stack after the current position, and return *o*.

        Discard all later elements.
        """
        self._elements[self._pos + 1:] = [o]
        self._pos = len(self._elements) - 1
        return o

    def home(self):
        """
        Push the first element onto the top of the stack.

        The first element is returned.
        """
        return self.push(self._elements[0]) if self._elements else None


def safe_masked_invalid(x, copy=False):
    x = np.array(x, subok=True, copy=copy)
    if not x.dtype.isnative:
        # If we have already made a copy, do the byteswap in place, else make a
        # copy with the byte order swapped.
        # Swap to native order.
        x = x.byteswap(inplace=copy).view(x.dtype.newbyteorder('N'))
    try:
        xm = np.ma.masked_where(~(np.isfinite(x)), x, copy=False)
    except TypeError:
        return x
    return xm


def print_cycles(objects, outstream=sys.stdout, show_progress=False):
    """
    Print loops of cyclic references in the given *objects*.

    It is often useful to pass in ``gc.garbage`` to find the cycles that are
    preventing some objects from being garbage collected.

    Parameters
    ----------
    objects
        A list of objects to find cycles in.
    outstream
        The stream for output.
    show_progress : bool
        If True, print the number of objects reached as they are found.
    """
    import gc

    def print_path(path):
        for i, step in enumerate(path):
            # next "wraps around"
            next = path[(i + 1) % len(path)]

            outstream.write("   %s -- " % type(step))
            if isinstance(step, dict):
                for key, val in step.items():
                    if val is next:
                        outstream.write(f"[{key!r}]")
                        break
                    if key is next:
                        outstream.write(f"[key] = {val!r}")
                        break
            elif isinstance(step, list):
                outstream.write("[%d]" % step.index(next))
            elif isinstance(step, tuple):
                outstream.write("( tuple )")
            else:
                outstream.write(repr(step))
            outstream.write(" ->\n")
        outstream.write("\n")

    def recurse(obj, start, all, current_path):
        if show_progress:
            outstream.write("%d\r" % len(all))

        all[id(obj)] = None

        referents = gc.get_referents(obj)
        for referent in referents:
            # If we've found our way back to the start, this is
            # a cycle, so print it out
            if referent is start:
                print_path(current_path)

            # Don't go back through the original list of objects, or
            # through temporary references to the object, since those
            # are just an artifact of the cycle detector itself.
            elif referent is objects or isinstance(referent, types.FrameType):
                continue

            # We haven't seen this object before, so recurse
            elif id(referent) not in all:
                recurse(referent, start, all, current_path + [obj])

    for obj in objects:
        outstream.write(f"Examining: {obj!r}\n")
        recurse(obj, obj, {}, [])


class Grouper:
    """
    A disjoint-set data structure.

    Objects can be joined using :meth:`join`, tested for connectedness
    using :meth:`joined`, and all disjoint sets can be retrieved by
    using the object as an iterator.

    The objects being joined must be hashable and weak-referenceable.

    Examples
    --------
    >>> from matplotlib.cbook import Grouper
    >>> class Foo:
    ...     def __init__(self, s):
    ...         self.s = s
    ...     def __repr__(self):
    ...         return self.s
    ...
    >>> a, b, c, d, e, f = [Foo(x) for x in 'abcdef']
    >>> grp = Grouper()
    >>> grp.join(a, b)
    >>> grp.join(b, c)
    >>> grp.join(d, e)
    >>> list(grp)
    [[a, b, c], [d, e]]
    >>> grp.joined(a, b)
    True
    >>> grp.joined(a, c)
    True
    >>> grp.joined(a, d)
    False
    """

    def __init__(self, init=()):
        self._mapping = weakref.WeakKeyDictionary(
            {x: weakref.WeakSet([x]) for x in init})
        self._ordering = weakref.WeakKeyDictionary()
        for x in init:
            if x not in self._ordering:
                self._ordering[x] = len(self._ordering)
        self._next_order = len(self._ordering)  # Plain int to simplify pickling.

    def __getstate__(self):
        return {
            **vars(self),
            # Convert weak refs to strong ones.
            "_mapping": {k: set(v) for k, v in self._mapping.items()},
            "_ordering": {**self._ordering},
        }

    def __setstate__(self, state):
        vars(self).update(state)
        # Convert strong refs to weak ones.
        self._mapping = weakref.WeakKeyDictionary(
            {k: weakref.WeakSet(v) for k, v in self._mapping.items()})
        self._ordering = weakref.WeakKeyDictionary(self._ordering)

    def __contains__(self, item):
        return item in self._mapping

    def join(self, a, *args):
        """
        Join given arguments into the same set.  Accepts one or more arguments.
        """
        mapping = self._mapping
        try:
            set_a = mapping[a]
        except KeyError:
            set_a = mapping[a] = weakref.WeakSet([a])
            self._ordering[a] = self._next_order
            self._next_order += 1
        for arg in args:
            try:
                set_b = mapping[arg]
            except KeyError:
                set_b = mapping[arg] = weakref.WeakSet([arg])
                self._ordering[arg] = self._next_order
                self._next_order += 1
            if set_b is not set_a:
                if len(set_b) > len(set_a):
                    set_a, set_b = set_b, set_a
                set_a.update(set_b)
                for elem in set_b:
                    mapping[elem] = set_a

    def joined(self, a, b):
        """Return whether *a* and *b* are members of the same set."""
        return (self._mapping.get(a, object()) is self._mapping.get(b))

    def remove(self, a):
        """Remove *a* from the grouper, doing nothing if it is not there."""
        self._mapping.pop(a, {a}).remove(a)
        self._ordering.pop(a, None)

    def __iter__(self):
        """
        Iterate over each of the disjoint sets as a list.

        The iterator is invalid if interleaved with calls to join().
        """
        unique_groups = {id(group): group for group in self._mapping.values()}
        for group in unique_groups.values():
            yield sorted(group, key=self._ordering.__getitem__)

    def get_siblings(self, a):
        """Return all of the items joined with *a*, including itself."""
        siblings = self._mapping.get(a, [a])
        return sorted(siblings, key=self._ordering.get)


class GrouperView:
    """Immutable view over a `.Grouper`."""

    def __init__(self, grouper): self._grouper = grouper
    def __contains__(self, item): return item in self._grouper
    def __iter__(self): return iter(self._grouper)

    def joined(self, a, b):
        """
        Return whether *a* and *b* are members of the same set.
        """
        return self._grouper.joined(a, b)

    def get_siblings(self, a):
        """
        Return all of the items joined with *a*, including itself.
        """
        return self._grouper.get_siblings(a)


def simple_linear_interpolation(a, steps):
    """
    Resample an array with ``steps - 1`` points between original point pairs.

    Along each column of *a*, ``(steps - 1)`` points are introduced between
    each original values; the values are linearly interpolated.

    Parameters
    ----------
    a : array, shape (n, ...)
    steps : int

    Returns
    -------
    array
        shape ``((n - 1) * steps + 1, ...)``
    """
    fps = a.reshape((len(a), -1))
    xp = np.arange(len(a)) * steps
    x = np.arange((len(a) - 1) * steps + 1)
    return (np.column_stack([np.interp(x, xp, fp) for fp in fps.T])
            .reshape((len(x),) + a.shape[1:]))


def delete_masked_points(*args):
    """
    Find all masked and/or non-finite points in a set of arguments,
    and return the arguments with only the unmasked points remaining.

    Arguments can be in any of 5 categories:

    1) 1-D masked arrays
    2) 1-D ndarrays
    3) ndarrays with more than one dimension
    4) other non-string iterables
    5) anything else

    The first argument must be in one of the first four categories;
    any argument with a length differing from that of the first
    argument (and hence anything in category 5) then will be
    passed through unchanged.

    Masks are obtained from all arguments of the correct length
    in categories 1, 2, and 4; a point is bad if masked in a masked
    array or if it is a nan or inf.  No attempt is made to
    extract a mask from categories 2, 3, and 4 if `numpy.isfinite`
    does not yield a Boolean array.

    All input arguments that are not passed unchanged are returned
    as ndarrays after removing the points or rows corresponding to
    masks in any of the arguments.

    A vastly simpler version of this function was originally
    written as a helper for Axes.scatter().

    """
    if not len(args):
        return ()
    if is_scalar_or_string(args[0]):
        raise ValueError("First argument must be a sequence")
    nrecs = len(args[0])
    margs = []
    seqlist = [False] * len(args)
    for i, x in enumerate(args):
        if not isinstance(x, str) and np.iterable(x) and len(x) == nrecs:
            seqlist[i] = True
            if isinstance(x, np.ma.MaskedArray):
                if x.ndim > 1:
                    raise ValueError("Masked arrays must be 1-D")
            else:
                x = np.asarray(x)
        margs.append(x)
    masks = []  # List of masks that are True where good.
    for i, x in enumerate(margs):
        if seqlist[i]:
            if x.ndim > 1:
                continue  # Don't try to get nan locations unless 1-D.
            if isinstance(x, np.ma.MaskedArray):
                masks.append(~np.ma.getmaskarray(x))  # invert the mask
                xd = x.data
            else:
                xd = x
            try:
                mask = np.isfinite(xd)
                if isinstance(mask, np.ndarray):
                    masks.append(mask)
            except Exception:  # Fixme: put in tuple of possible exceptions?
                pass
    if len(masks):
        mask = np.logical_and.reduce(masks)
        igood = mask.nonzero()[0]
        if len(igood) < nrecs:
            for i, x in enumerate(margs):
                if seqlist[i]:
                    margs[i] = x[igood]
    for i, x in enumerate(margs):
        if seqlist[i] and isinstance(x, np.ma.MaskedArray):
            margs[i] = x.filled()
    return margs


def _combine_masks(*args):
    """
    Find all masked and/or non-finite points in a set of arguments,
    and return the arguments as masked arrays with a common mask.

    Arguments can be in any of 5 categories:

    1) 1-D masked arrays
    2) 1-D ndarrays
    3) ndarrays with more than one dimension
    4) other non-string iterables
    5) anything else

    The first argument must be in one of the first four categories;
    any argument with a length differing from that of the first
    argument (and hence anything in category 5) then will be
    passed through unchanged.

    Masks are obtained from all arguments of the correct length
    in categories 1, 2, and 4; a point is bad if masked in a masked
    array or if it is a nan or inf.  No attempt is made to
    extract a mask from categories 2 and 4 if `numpy.isfinite`
    does not yield a Boolean array.  Category 3 is included to
    support RGB or RGBA ndarrays, which are assumed to have only
    valid values and which are passed through unchanged.

    All input arguments that are not passed unchanged are returned
    as masked arrays if any masked points are found, otherwise as
    ndarrays.

    """
    if not len(args):
        return ()
    if is_scalar_or_string(args[0]):
        raise ValueError("First argument must be a sequence")
    nrecs = len(args[0])
    margs = []  # Output args; some may be modified.
    seqlist = [False] * len(args)  # Flags: True if output will be masked.
    masks = []    # List of masks.
    for i, x in enumerate(args):
        if is_scalar_or_string(x) or len(x) != nrecs:
            margs.append(x)  # Leave it unmodified.
        else:
            if isinstance(x, np.ma.MaskedArray) and x.ndim > 1:
                raise ValueError("Masked arrays must be 1-D")
            try:
                x = np.asanyarray(x)
            except (VisibleDeprecationWarning, ValueError):
                # NumPy 1.19 raises a warning about ragged arrays, but we want
                # to accept basically anything here.
                x = np.asanyarray(x, dtype=object)
            if x.ndim == 1:
                x = safe_masked_invalid(x)
                seqlist[i] = True
                if np.ma.is_masked(x):
                    masks.append(np.ma.getmaskarray(x))
            margs.append(x)  # Possibly modified.
    if len(masks):
        mask = np.logical_or.reduce(masks)
        for i, x in enumerate(margs):
            if seqlist[i]:
                margs[i] = np.ma.array(x, mask=mask)
    return margs


def _broadcast_with_masks(*args, compress=False):
    """
    Broadcast inputs, combining all masked arrays.

    Parameters
    ----------
    *args : array-like
        The inputs to broadcast.
    compress : bool, default: False
        Whether to compress the masked arrays. If False, the masked values
        are replaced by NaNs.

    Returns
    -------
    list of array-like
        The broadcasted and masked inputs.
    """
    # extract the masks, if any
    masks = [k.mask for k in args if isinstance(k, np.ma.MaskedArray)]
    # broadcast to match the shape
    bcast = np.broadcast_arrays(*args, *masks)
    inputs = bcast[:len(args)]
    masks = bcast[len(args):]
    if masks:
        # combine the masks into one
        mask = np.logical_or.reduce(masks)
        # put mask on and compress
        if compress:
            inputs = [np.ma.array(k, mask=mask).compressed()
                      for k in inputs]
        else:
            inputs = [np.ma.array(k, mask=mask, dtype=float).filled(np.nan).ravel()
                      for k in inputs]
    else:
        inputs = [np.ravel(k) for k in inputs]
    return inputs


def boxplot_stats(X, whis=1.5, bootstrap=None, labels=None, autorange=False):
    r"""
    Return a list of dictionaries of statistics used to draw a series of box
    and whisker plots using `~.Axes.bxp`.

    Parameters
    ----------
    X : array-like
        Data that will be represented in the boxplots. Should have 2 or
        fewer dimensions.

    whis : float or (float, float), default: 1.5
        The position of the whiskers.

        If a float, the lower whisker is at the lowest datum above
        ``Q1 - whis*(Q3-Q1)``, and the upper whisker at the highest datum below
        ``Q3 + whis*(Q3-Q1)``, where Q1 and Q3 are the first and third
        quartiles.  The default value of ``whis = 1.5`` corresponds to Tukey's
        original definition of boxplots.

        If a pair of floats, they indicate the percentiles at which to draw the
        whiskers (e.g., (5, 95)).  In particular, setting this to (0, 100)
        results in whiskers covering the whole range of the data.

        In the edge case where ``Q1 == Q3``, *whis* is automatically set to
        (0, 100) (cover the whole range of the data) if *autorange* is True.

        Beyond the whiskers, data are considered outliers and are plotted as
        individual points.

    bootstrap : int, optional
        Number of times the confidence intervals around the median
        should be bootstrapped (percentile method).

    labels : list of str, optional
        Labels for each dataset. Length must be compatible with
        dimensions of *X*.

    autorange : bool, optional (False)
        When `True` and the data are distributed such that the 25th and 75th
        percentiles are equal, ``whis`` is set to (0, 100) such that the
        whisker ends are at the minimum and maximum of the data.

    Returns
    -------
    list of dict
        A list of dictionaries containing the results for each column
        of data. Keys of each dictionary are the following:

        ========   ===================================
        Key        Value Description
        ========   ===================================
        label      tick label for the boxplot
        mean       arithmetic mean value
        med        50th percentile
        q1         first quartile (25th percentile)
        q3         third quartile (75th percentile)
        iqr        interquartile range
        cilo       lower notch around the median
        cihi       upper notch around the median
        whislo     end of the lower whisker
        whishi     end of the upper whisker
        fliers     outliers
        ========   ===================================

    Notes
    -----
    Non-bootstrapping approach to confidence interval uses Gaussian-based
    asymptotic approximation:

    .. math::

        \mathrm{med} \pm 1.57 \times \frac{\mathrm{iqr}}{\sqrt{N}}

    General approach from:
    McGill, R., Tukey, J.W., and Larsen, W.A. (1978) "Variations of
    Boxplots", The American Statistician, 32:12-16.
    """

    def _bootstrap_median(data, N=5000):
        # determine 95% confidence intervals of the median
        M = len(data)
        percentiles = [2.5, 97.5]

        bs_index = np.random.randint(M, size=(N, M))
        bsData = data[bs_index]
        estimate = np.median(bsData, axis=1, overwrite_input=True)

        CI = np.percentile(estimate, percentiles)
        return CI

    def _compute_conf_interval(data, med, iqr, bootstrap):
        if bootstrap is not None:
            # Do a bootstrap estimate of notch locations.
            # get conf. intervals around median
            CI = _bootstrap_median(data, N=bootstrap)
            notch_min = CI[0]
            notch_max = CI[1]
        else:

            N = len(data)
            notch_min = med - 1.57 * iqr / np.sqrt(N)
            notch_max = med + 1.57 * iqr / np.sqrt(N)

        return notch_min, notch_max

    # output is a list of dicts
    bxpstats = []

    # convert X to a list of lists
    X = _reshape_2D(X, "X")

    ncols = len(X)
    if labels is None:
        labels = itertools.repeat(None)
    elif len(labels) != ncols:
        raise ValueError("Dimensions of labels and X must be compatible")

    input_whis = whis
    for ii, (x, label) in enumerate(zip(X, labels)):

        # empty dict
        stats = {}
        if label is not None:
            stats['label'] = label

        # restore whis to the input values in case it got changed in the loop
        whis = input_whis

        # note tricksiness, append up here and then mutate below
        bxpstats.append(stats)

        # if empty, bail
        if len(x) == 0:
            stats['fliers'] = np.array([])
            stats['mean'] = np.nan
            stats['med'] = np.nan
            stats['q1'] = np.nan
            stats['q3'] = np.nan
            stats['iqr'] = np.nan
            stats['cilo'] = np.nan
            stats['cihi'] = np.nan
            stats['whislo'] = np.nan
            stats['whishi'] = np.nan
            continue

        # up-convert to an array, just to be safe
        x = np.ma.asarray(x)
        x = x.data[~x.mask].ravel()

        # arithmetic mean
        stats['mean'] = np.mean(x)

        # medians and quartiles
        q1, med, q3 = np.percentile(x, [25, 50, 75])

        # interquartile range
        stats['iqr'] = q3 - q1
        if stats['iqr'] == 0 and autorange:
            whis = (0, 100)

        # conf. interval around median
        stats['cilo'], stats['cihi'] = _compute_conf_interval(
            x, med, stats['iqr'], bootstrap
        )

        # lowest/highest non-outliers
        if np.iterable(whis) and not isinstance(whis, str):
            loval, hival = np.percentile(x, whis)
        elif np.isreal(whis):
            loval = q1 - whis * stats['iqr']
            hival = q3 + whis * stats['iqr']
        else:
            raise ValueError('whis must be a float or list of percentiles')

        # get high extreme
        wiskhi = x[x <= hival]
        if len(wiskhi) == 0 or np.max(wiskhi) < q3:
            stats['whishi'] = q3
        else:
            stats['whishi'] = np.max(wiskhi)

        # get low extreme
        wisklo = x[x >= loval]
        if len(wisklo) == 0 or np.min(wisklo) > q1:
            stats['whislo'] = q1
        else:
            stats['whislo'] = np.min(wisklo)

        # compute a single array of outliers
        stats['fliers'] = np.concatenate([
            x[x < stats['whislo']],
            x[x > stats['whishi']],
        ])

        # add in the remaining stats
        stats['q1'], stats['med'], stats['q3'] = q1, med, q3

    return bxpstats


#: Maps short codes for line style to their full name used by backends.
ls_mapper = {'-': 'solid', '--': 'dashed', '-.': 'dashdot', ':': 'dotted'}
#: Maps full names for line styles used by backends to their short codes.
ls_mapper_r = {v: k for k, v in ls_mapper.items()}


def contiguous_regions(mask):
    """
    Return a list of (ind0, ind1) such that ``mask[ind0:ind1].all()`` is
    True and we cover all such regions.
    """
    mask = np.asarray(mask, dtype=bool)

    if not mask.size:
        return []

    # Find the indices of region changes, and correct offset
    idx, = np.nonzero(mask[:-1] != mask[1:])
    idx += 1

    # List operations are faster for moderately sized arrays
    idx = idx.tolist()

    # Add first and/or last index if needed
    if mask[0]:
        idx = [0] + idx
    if mask[-1]:
        idx.append(len(mask))

    return list(zip(idx[::2], idx[1::2]))


def is_math_text(s):
    """
    Return whether the string *s* contains math expressions.

    This is done by checking whether *s* contains an even number of
    non-escaped dollar signs.
    """
    s = str(s)
    dollar_count = s.count(r'$') - s.count(r'\$')
    even_dollars = (dollar_count > 0 and dollar_count % 2 == 0)
    return even_dollars


def _to_unmasked_float_array(x):
    """
    Convert a sequence to a float array; if input was a masked array, masked
    values are converted to nans.
    """
    if hasattr(x, 'mask'):
        return np.ma.asarray(x, float).filled(np.nan)
    else:
        return np.asarray(x, float)


def _check_1d(x):
    """Convert scalars to 1D arrays; pass-through arrays as is."""
    # Unpack in case of e.g. Pandas or xarray object
    x = _unpack_to_numpy(x)
    # plot requires `shape` and `ndim`.  If passed an
    # object that doesn't provide them, then force to numpy array.
    # Note this will strip unit information.
    if (not hasattr(x, 'shape') or
            not hasattr(x, 'ndim') or
            len(x.shape) < 1):
        return np.atleast_1d(x)
    else:
        return x


def _reshape_2D(X, name):
    """
    Use Fortran ordering to convert ndarrays and lists of iterables to lists of
    1D arrays.

    Lists of iterables are converted by applying `numpy.asanyarray` to each of
    their elements.  1D ndarrays are returned in a singleton list containing
    them.  2D ndarrays are converted to the list of their *columns*.

    *name* is used to generate the error message for invalid inputs.
    """

    # Unpack in case of e.g. Pandas or xarray object
    X = _unpack_to_numpy(X)

    # Iterate over columns for ndarrays.
    if isinstance(X, np.ndarray):
        X = X.transpose()

        if len(X) == 0:
            return [[]]
        elif X.ndim == 1 and np.ndim(X[0]) == 0:
            # 1D array of scalars: directly return it.
            return [X]
        elif X.ndim in [1, 2]:
            # 2D array, or 1D array of iterables: flatten them first.
            return [np.reshape(x, -1) for x in X]
        else:
            raise ValueError(f'{name} must have 2 or fewer dimensions')

    # Iterate over list of iterables.
    if len(X) == 0:
        return [[]]

    result = []
    is_1d = True
    for xi in X:
        # check if this is iterable, except for strings which we
        # treat as singletons.
        if not isinstance(xi, str):
            try:
                iter(xi)
            except TypeError:
                pass
            else:
                is_1d = False
        xi = np.asanyarray(xi)
        nd = np.ndim(xi)
        if nd > 1:
            raise ValueError(f'{name} must have 2 or fewer dimensions')
        result.append(xi.reshape(-1))

    if is_1d:
        # 1D array of scalars: directly return it.
        return [np.reshape(result, -1)]
    else:
        # 2D array, or 1D array of iterables: use flattened version.
        return result


def violin_stats(X, method, points=100, quantiles=None):
    """
    Return a list of dictionaries of data which can be used to draw a series
    of violin plots.

    See the ``Returns`` section below to view the required keys of the
    dictionary.

    Users can skip this function and pass a user-defined set of dictionaries
    with the same keys to `~.axes.Axes.violinplot` instead of using Matplotlib
    to do the calculations. See the *Returns* section below for the keys
    that must be present in the dictionaries.

    Parameters
    ----------
    X : array-like
        Sample data that will be used to produce the gaussian kernel density
        estimates. Must have 2 or fewer dimensions.

    method : callable
        The method used to calculate the kernel density estimate for each
        column of data. When called via ``method(v, coords)``, it should
        return a vector of the values of the KDE evaluated at the values
        specified in coords.

    points : int, default: 100
        Defines the number of points to evaluate each of the gaussian kernel
        density estimates at.

    quantiles : array-like, default: None
        Defines (if not None) a list of floats in interval [0, 1] for each
        column of data, which represents the quantiles that will be rendered
        for that column of data. Must have 2 or fewer dimensions. 1D array will
        be treated as a singleton list containing them.

    Returns
    -------
    list of dict
        A list of dictionaries containing the results for each column of data.
        The dictionaries contain at least the following:

        - coords: A list of scalars containing the coordinates this particular
          kernel density estimate was evaluated at.
        - vals: A list of scalars containing the values of the kernel density
          estimate at each of the coordinates given in *coords*.
        - mean: The mean value for this column of data.
        - median: The median value for this column of data.
        - min: The minimum value for this column of data.
        - max: The maximum value for this column of data.
        - quantiles: The quantile values for this column of data.
    """

    # List of dictionaries describing each of the violins.
    vpstats = []

    # Want X to be a list of data sequences
    X = _reshape_2D(X, "X")

    # Want quantiles to be as the same shape as data sequences
    if quantiles is not None and len(quantiles) != 0:
        quantiles = _reshape_2D(quantiles, "quantiles")
    # Else, mock quantiles if it's none or empty
    else:
        quantiles = [[]] * len(X)

    # quantiles should have the same size as dataset
    if len(X) != len(quantiles):
        raise ValueError("List of violinplot statistics and quantiles values"
                         " must have the same length")

    # Zip x and quantiles
    for (x, q) in zip(X, quantiles):
        # Dictionary of results for this distribution
        stats = {}

        # Calculate basic stats for the distribution
        min_val = np.min(x)
        max_val = np.max(x)
        quantile_val = np.percentile(x, 100 * q)

        # Evaluate the kernel density estimate
        coords = np.linspace(min_val, max_val, points)
        stats['vals'] = method(x, coords)
        stats['coords'] = coords

        # Store additional statistics for this distribution
        stats['mean'] = np.mean(x)
        stats['median'] = np.median(x)
        stats['min'] = min_val
        stats['max'] = max_val
        stats['quantiles'] = np.atleast_1d(quantile_val)

        # Append to output
        vpstats.append(stats)

    return vpstats


def pts_to_prestep(x, *args):
    """
    Convert continuous line to pre-steps.

    Given a set of ``N`` points, convert to ``2N - 1`` points, which when
    connected linearly give a step function which changes values at the
    beginning of the intervals.

    Parameters
    ----------
    x : array
        The x location of the steps. May be empty.

    y1, ..., yp : array
        y arrays to be turned into steps; all must be the same length as ``x``.

    Returns
    -------
    array
        The x and y values converted to steps in the same order as the input;
        can be unpacked as ``x_out, y1_out, ..., yp_out``.  If the input is
        length ``N``, each of these arrays will be length ``2N + 1``. For
        ``N=0``, the length will be 0.

    Examples
    --------
    >>> x_s, y1_s, y2_s = pts_to_prestep(x, y1, y2)
    """
    steps = np.zeros((1 + len(args), max(2 * len(x) - 1, 0)))
    # In all `pts_to_*step` functions, only assign once using *x* and *args*,
    # as converting to an array may be expensive.
    steps[0, 0::2] = x
    steps[0, 1::2] = steps[0, 0:-2:2]
    steps[1:, 0::2] = args
    steps[1:, 1::2] = steps[1:, 2::2]
    return steps


def pts_to_poststep(x, *args):
    """
    Convert continuous line to post-steps.

    Given a set of ``N`` points convert to ``2N + 1`` points, which when
    connected linearly give a step function which changes values at the end of
    the intervals.

    Parameters
    ----------
    x : array
        The x location of the steps. May be empty.

    y1, ..., yp : array
        y arrays to be turned into steps; all must be the same length as ``x``.

    Returns
    -------
    array
        The x and y values converted to steps in the same order as the input;
        can be unpacked as ``x_out, y1_out, ..., yp_out``.  If the input is
        length ``N``, each of these arrays will be length ``2N + 1``. For
        ``N=0``, the length will be 0.

    Examples
    --------
    >>> x_s, y1_s, y2_s = pts_to_poststep(x, y1, y2)
    """
    steps = np.zeros((1 + len(args), max(2 * len(x) - 1, 0)))
    steps[0, 0::2] = x
    steps[0, 1::2] = steps[0, 2::2]
    steps[1:, 0::2] = args
    steps[1:, 1::2] = steps[1:, 0:-2:2]
    return steps


def pts_to_midstep(x, *args):
    """
    Convert continuous line to mid-steps.

    Given a set of ``N`` points convert to ``2N`` points which when connected
    linearly give a step function which changes values at the middle of the
    intervals.

    Parameters
    ----------
    x : array
        The x location of the steps. May be empty.

    y1, ..., yp : array
        y arrays to be turned into steps; all must be the same length as
        ``x``.

    Returns
    -------
    array
        The x and y values converted to steps in the same order as the input;
        can be unpacked as ``x_out, y1_out, ..., yp_out``.  If the input is
        length ``N``, each of these arrays will be length ``2N``.

    Examples
    --------
    >>> x_s, y1_s, y2_s = pts_to_midstep(x, y1, y2)
    """
    steps = np.zeros((1 + len(args), 2 * len(x)))
    x = np.asanyarray(x)
    steps[0, 1:-1:2] = steps[0, 2::2] = (x[:-1] + x[1:]) / 2
    steps[0, :1] = x[:1]  # Also works for zero-sized input.
    steps[0, -1:] = x[-1:]
    steps[1:, 0::2] = args
    steps[1:, 1::2] = steps[1:, 0::2]
    return steps


STEP_LOOKUP_MAP = {'default': lambda x, y: (x, y),
                   'steps': pts_to_prestep,
                   'steps-pre': pts_to_prestep,
                   'steps-post': pts_to_poststep,
                   'steps-mid': pts_to_midstep}


def index_of(y):
    """
    A helper function to create reasonable x values for the given *y*.

    This is used for plotting (x, y) if x values are not explicitly given.

    First try ``y.index`` (assuming *y* is a `pandas.Series`), if that
    fails, use ``range(len(y))``.

    This will be extended in the future to deal with more types of
    labeled data.

    Parameters
    ----------
    y : float or array-like

    Returns
    -------
    x, y : ndarray
       The x and y values to plot.
    """
    try:
        return y.index.to_numpy(), y.to_numpy()
    except AttributeError:
        pass
    try:
        y = _check_1d(y)
    except (VisibleDeprecationWarning, ValueError):
        # NumPy 1.19 will warn on ragged input, and we can't actually use it.
        pass
    else:
        return np.arange(y.shape[0], dtype=float), y
    raise ValueError('Input could not be cast to an at-least-1D NumPy array')


def safe_first_element(obj):
    """
    Return the first element in *obj*.

    This is a type-independent way of obtaining the first element,
    supporting both index access and the iterator protocol.
    """
    if isinstance(obj, collections.abc.Iterator):
        # needed to accept `array.flat` as input.
        # np.flatiter reports as an instance of collections.Iterator but can still be
        # indexed via []. This has the side effect of re-setting the iterator, but
        # that is acceptable.
        try:
            return obj[0]
        except TypeError:
            pass
        raise RuntimeError("matplotlib does not support generators as input")
    return next(iter(obj))


def _safe_first_finite(obj):
    """
    Return the first finite element in *obj* if one is available and skip_nonfinite is
    True. Otherwise, return the first element.

    This is a method for internal use.

    This is a type-independent way of obtaining the first finite element, supporting
    both index access and the iterator protocol.
    """
    def safe_isfinite(val):
        if val is None:
            return False
        try:
            return math.isfinite(val)
        except (TypeError, ValueError):
            # if the outer object is 2d, then val is a 1d array, and
            # - math.isfinite(numpy.zeros(3)) raises TypeError
            # - math.isfinite(torch.zeros(3)) raises ValueError
            pass
        try:
            return np.isfinite(val) if np.isscalar(val) else True
        except TypeError:
            # This is something that NumPy cannot make heads or tails of,
            # assume "finite"
            return True

    if isinstance(obj, np.flatiter):
        # TODO do the finite filtering on this
        return obj[0]
    elif isinstance(obj, collections.abc.Iterator):
        raise RuntimeError("matplotlib does not support generators as input")
    else:
        for val in obj:
            if safe_isfinite(val):
                return val
        return safe_first_element(obj)


def sanitize_sequence(data):
    """
    Convert dictview objects to list. Other inputs are returned unchanged.
    """
    return (list(data) if isinstance(data, collections.abc.MappingView)
            else data)


def normalize_kwargs(kw, alias_mapping=None):
    """
    Helper function to normalize kwarg inputs.

    Parameters
    ----------
    kw : dict or None
        A dict of keyword arguments.  None is explicitly supported and treated
        as an empty dict, to support functions with an optional parameter of
        the form ``props=None``.

    alias_mapping : dict or Artist subclass or Artist instance, optional
        A mapping between a canonical name to a list of aliases, in order of
        precedence from lowest to highest.

        If the canonical value is not in the list it is assumed to have the
        highest priority.

        If an Artist subclass or instance is passed, use its properties alias
        mapping.

    Raises
    ------
    TypeError
        To match what Python raises if invalid arguments/keyword arguments are
        passed to a callable.
    """
    from matplotlib.artist import Artist

    if kw is None:
        return {}

    # deal with default value of alias_mapping
    if alias_mapping is None:
        alias_mapping = {}
    elif (isinstance(alias_mapping, type) and issubclass(alias_mapping, Artist)
          or isinstance(alias_mapping, Artist)):
        alias_mapping = getattr(alias_mapping, "_alias_map", {})

    to_canonical = {alias: canonical
                    for canonical, alias_list in alias_mapping.items()
                    for alias in alias_list}
    canonical_to_seen = {}
    ret = {}  # output dictionary

    for k, v in kw.items():
        canonical = to_canonical.get(k, k)
        if canonical in canonical_to_seen:
            raise TypeError(f"Got both {canonical_to_seen[canonical]!r} and "
                            f"{k!r}, which are aliases of one another")
        canonical_to_seen[canonical] = k
        ret[canonical] = v

    return ret


@contextlib.contextmanager
def _lock_path(path):
    """
    Context manager for locking a path.

    Usage::

        with _lock_path(path):
            ...

    Another thread or process that attempts to lock the same path will wait
    until this context manager is exited.

    The lock is implemented by creating a temporary file in the parent
    directory, so that directory must exist and be writable.
    """
    path = Path(path)
    lock_path = path.with_name(path.name + ".matplotlib-lock")
    retries = 50
    sleeptime = 0.1
    for _ in range(retries):
        try:
            with lock_path.open("xb"):
                break
        except FileExistsError:
            time.sleep(sleeptime)
    else:
        raise TimeoutError("""\
Lock error: Matplotlib failed to acquire the following lock file:
    {}
This maybe due to another process holding this lock file.  If you are sure no
other Matplotlib process is running, remove this file and try again.""".format(
            lock_path))
    try:
        yield
    finally:
        lock_path.unlink()


def _topmost_artist(
        artists,
        _cached_max=functools.partial(max, key=operator.attrgetter("zorder"))):
    """
    Get the topmost artist of a list.

    In case of a tie, return the *last* of the tied artists, as it will be
    drawn on top of the others. `max` returns the first maximum in case of
    ties, so we need to iterate over the list in reverse order.
    """
    return _cached_max(reversed(artists))


def _str_equal(obj, s):
    """
    Return whether *obj* is a string equal to string *s*.

    This helper solely exists to handle the case where *obj* is a numpy array,
    because in such cases, a naive ``obj == s`` would yield an array, which
    cannot be used in a boolean context.
    """
    return isinstance(obj, str) and obj == s


def _str_lower_equal(obj, s):
    """
    Return whether *obj* is a string equal, when lowercased, to string *s*.

    This helper solely exists to handle the case where *obj* is a numpy array,
    because in such cases, a naive ``obj == s`` would yield an array, which
    cannot be used in a boolean context.
    """
    return isinstance(obj, str) and obj.lower() == s


def _array_perimeter(arr):
    """
    Get the elements on the perimeter of *arr*.

    Parameters
    ----------
    arr : ndarray, shape (M, N)
        The input array.

    Returns
    -------
    ndarray, shape (2*(M - 1) + 2*(N - 1),)
        The elements on the perimeter of the array::

           [arr[0, 0], ..., arr[0, -1], ..., arr[-1, -1], ..., arr[-1, 0], ...]

    Examples
    --------
    >>> i, j = np.ogrid[:3, :4]
    >>> a = i*10 + j
    >>> a
    array([[ 0,  1,  2,  3],
           [10, 11, 12, 13],
           [20, 21, 22, 23]])
    >>> _array_perimeter(a)
    array([ 0,  1,  2,  3, 13, 23, 22, 21, 20, 10])
    """
    # note we use Python's half-open ranges to avoid repeating
    # the corners
    forward = np.s_[0:-1]      # [0 ... -1)
    backward = np.s_[-1:0:-1]  # [-1 ... 0)
    return np.concatenate((
        arr[0, forward],
        arr[forward, -1],
        arr[-1, backward],
        arr[backward, 0],
    ))


def _unfold(arr, axis, size, step):
    """
    Append an extra dimension containing sliding windows along *axis*.

    All windows are of size *size* and begin with every *step* elements.

    Parameters
    ----------
    arr : ndarray, shape (N_1, ..., N_k)
        The input array
    axis : int
        Axis along which the windows are extracted
    size : int
        Size of the windows
    step : int
        Stride between first elements of subsequent windows.

    Returns
    -------
    ndarray, shape (N_1, ..., 1 + (N_axis-size)/step, ..., N_k, size)

    Examples
    --------
    >>> i, j = np.ogrid[:3, :7]
    >>> a = i*10 + j
    >>> a
    array([[ 0,  1,  2,  3,  4,  5,  6],
           [10, 11, 12, 13, 14, 15, 16],
           [20, 21, 22, 23, 24, 25, 26]])
    >>> _unfold(a, axis=1, size=3, step=2)
    array([[[ 0,  1,  2],
            [ 2,  3,  4],
            [ 4,  5,  6]],
           [[10, 11, 12],
            [12, 13, 14],
            [14, 15, 16]],
           [[20, 21, 22],
            [22, 23, 24],
            [24, 25, 26]]])
    """
    new_shape = [*arr.shape, size]
    new_strides = [*arr.strides, arr.strides[axis]]
    new_shape[axis] = (new_shape[axis] - size) // step + 1
    new_strides[axis] = new_strides[axis] * step
    return np.lib.stride_tricks.as_strided(arr,
                                           shape=new_shape,
                                           strides=new_strides,
                                           writeable=False)


def _array_patch_perimeters(x, rstride, cstride):
    """
    Extract perimeters of patches from *arr*.

    Extracted patches are of size (*rstride* + 1) x (*cstride* + 1) and
    share perimeters with their neighbors. The ordering of the vertices matches
    that returned by ``_array_perimeter``.

    Parameters
    ----------
    x : ndarray, shape (N, M)
        Input array
    rstride : int
        Vertical (row) stride between corresponding elements of each patch
    cstride : int
        Horizontal (column) stride between corresponding elements of each patch

    Returns
    -------
    ndarray, shape (N/rstride * M/cstride, 2 * (rstride + cstride))
    """
    assert rstride > 0 and cstride > 0
    assert (x.shape[0] - 1) % rstride == 0
    assert (x.shape[1] - 1) % cstride == 0
    # We build up each perimeter from four half-open intervals. Here is an
    # illustrated explanation for rstride == cstride == 3
    #
    #       T T T R
    #       L     R
    #       L     R
    #       L B B B
    #
    # where T means that this element will be in the top array, R for right,
    # B for bottom and L for left. Each of the arrays below has a shape of:
    #
    #    (number of perimeters that can be extracted vertically,
    #     number of perimeters that can be extracted horizontally,
    #     cstride for top and bottom and rstride for left and right)
    #
    # Note that _unfold doesn't incur any memory copies, so the only costly
    # operation here is the np.concatenate.
    top = _unfold(x[:-1:rstride, :-1], 1, cstride, cstride)
    bottom = _unfold(x[rstride::rstride, 1:], 1, cstride, cstride)[..., ::-1]
    right = _unfold(x[:-1, cstride::cstride], 0, rstride, rstride)
    left = _unfold(x[1:, :-1:cstride], 0, rstride, rstride)[..., ::-1]
    return (np.concatenate((top, right, bottom, left), axis=2)
              .reshape(-1, 2 * (rstride + cstride)))


@contextlib.contextmanager
def _setattr_cm(obj, **kwargs):
    """
    Temporarily set some attributes; restore original state at context exit.
    """
    sentinel = object()
    origs = {}
    for attr in kwargs:
        orig = getattr(obj, attr, sentinel)
        if attr in obj.__dict__ or orig is sentinel:
            # if we are pulling from the instance dict or the object
            # does not have this attribute we can trust the above
            origs[attr] = orig
        else:
            # if the attribute is not in the instance dict it must be
            # from the class level
            cls_orig = getattr(type(obj), attr)
            # if we are dealing with a property (but not a general descriptor)
            # we want to set the original value back.
            if isinstance(cls_orig, property):
                origs[attr] = orig
            # otherwise this is _something_ we are going to shadow at
            # the instance dict level from higher up in the MRO.  We
            # are going to assume we can delattr(obj, attr) to clean
            # up after ourselves.  It is possible that this code will
            # fail if used with a non-property custom descriptor which
            # implements __set__ (and __delete__ does not act like a
            # stack).  However, this is an internal tool and we do not
            # currently have any custom descriptors.
            else:
                origs[attr] = sentinel

    try:
        for attr, val in kwargs.items():
            setattr(obj, attr, val)
        yield
    finally:
        for attr, orig in origs.items():
            if orig is sentinel:
                delattr(obj, attr)
            else:
                setattr(obj, attr, orig)


class _OrderedSet(collections.abc.MutableSet):
    def __init__(self):
        self._od = collections.OrderedDict()

    def __contains__(self, key):
        return key in self._od

    def __iter__(self):
        return iter(self._od)

    def __len__(self):
        return len(self._od)

    def add(self, key):
        self._od.pop(key, None)
        self._od[key] = None

    def discard(self, key):
        self._od.pop(key, None)


# Agg's buffers are unmultiplied RGBA8888, which neither PyQt<=5.1 nor cairo
# support; however, both do support premultiplied ARGB32.


def _premultiplied_argb32_to_unmultiplied_rgba8888(buf):
    """
    Convert a premultiplied ARGB32 buffer to an unmultiplied RGBA8888 buffer.
    """
    rgba = np.take(  # .take() ensures C-contiguity of the result.
        buf,
        [2, 1, 0, 3] if sys.byteorder == "little" else [1, 2, 3, 0], axis=2)
    rgb = rgba[..., :-1]
    alpha = rgba[..., -1]
    # Un-premultiply alpha.  The formula is the same as in cairo-png.c.
    mask = alpha != 0
    for channel in np.rollaxis(rgb, -1):
        channel[mask] = (
            (channel[mask].astype(int) * 255 + alpha[mask] // 2)
            // alpha[mask])
    return rgba


def _unmultiplied_rgba8888_to_premultiplied_argb32(rgba8888):
    """
    Convert an unmultiplied RGBA8888 buffer to a premultiplied ARGB32 buffer.
    """
    if sys.byteorder == "little":
        argb32 = np.take(rgba8888, [2, 1, 0, 3], axis=2)
        rgb24 = argb32[..., :-1]
        alpha8 = argb32[..., -1:]
    else:
        argb32 = np.take(rgba8888, [3, 0, 1, 2], axis=2)
        alpha8 = argb32[..., :1]
        rgb24 = argb32[..., 1:]
    # Only bother premultiplying when the alpha channel is not fully opaque,
    # as the cost is not negligible.  The unsafe cast is needed to do the
    # multiplication in-place in an integer buffer.
    if alpha8.min() != 0xff:
        np.multiply(rgb24, alpha8 / 0xff, out=rgb24, casting="unsafe")
    return argb32


def _get_nonzero_slices(buf):
    """
    Return the bounds of the nonzero region of a 2D array as a pair of slices.

    ``buf[_get_nonzero_slices(buf)]`` is the smallest sub-rectangle in *buf*
    that encloses all non-zero entries in *buf*.  If *buf* is fully zero, then
    ``(slice(0, 0), slice(0, 0))`` is returned.
    """
    x_nz, = buf.any(axis=0).nonzero()
    y_nz, = buf.any(axis=1).nonzero()
    if len(x_nz) and len(y_nz):
        l, r = x_nz[[0, -1]]
        b, t = y_nz[[0, -1]]
        return slice(b, t + 1), slice(l, r + 1)
    else:
        return slice(0, 0), slice(0, 0)


def _pformat_subprocess(command):
    """Pretty-format a subprocess command for printing/logging purposes."""
    return (command if isinstance(command, str)
            else " ".join(shlex.quote(os.fspath(arg)) for arg in command))


def _check_and_log_subprocess(command, logger, **kwargs):
    """
    Run *command*, returning its stdout output if it succeeds.

    If it fails (exits with nonzero return code), raise an exception whose text
    includes the failed command and captured stdout and stderr output.

    Regardless of the return code, the command is logged at DEBUG level on
    *logger*.  In case of success, the output is likewise logged.
    """
    logger.debug('%s', _pformat_subprocess(command))
    proc = subprocess.run(command, capture_output=True, **kwargs)
    if proc.returncode:
        stdout = proc.stdout
        if isinstance(stdout, bytes):
            stdout = stdout.decode()
        stderr = proc.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode()
        raise RuntimeError(
            f"The command\n"
            f"    {_pformat_subprocess(command)}\n"
            f"failed and generated the following output:\n"
            f"{stdout}\n"
            f"and the following error:\n"
            f"{stderr}")
    if proc.stdout:
        logger.debug("stdout:\n%s", proc.stdout)
    if proc.stderr:
        logger.debug("stderr:\n%s", proc.stderr)
    return proc.stdout


def _setup_new_guiapp():
    """
    Perform OS-dependent setup when Matplotlib creates a new GUI application.
    """
    # Windows: If not explicit app user model id has been set yet (so we're not
    # already embedded), then set it to "matplotlib", so that taskbar icons are
    # correct.
    try:
        _c_internal_utils.Win32_GetCurrentProcessExplicitAppUserModelID()
    except OSError:
        _c_internal_utils.Win32_SetCurrentProcessExplicitAppUserModelID(
            "matplotlib")


def _format_approx(number, precision):
    """
    Format the number with at most the number of decimals given as precision.
    Remove trailing zeros and possibly the decimal point.
    """
    return f'{number:.{precision}f}'.rstrip('0').rstrip('.') or '0'


def _g_sig_digits(value, delta):
    """
    Return the number of significant digits to %g-format *value*, assuming that
    it is known with an error of *delta*.
    """
    # For inf or nan, the precision doesn't matter.
    if not math.isfinite(value):
        return 0
    if delta == 0:
        if value == 0:
            # if both value and delta are 0, np.spacing below returns 5e-324
            # which results in rather silly results
            return 3
        # delta = 0 may occur when trying to format values over a tiny range;
        # in that case, replace it by the distance to the closest float.
        delta = abs(np.spacing(value))
    # If e.g. value = 45.67 and delta = 0.02, then we want to round to 2 digits
    # after the decimal point (floor(log10(0.02)) = -2); 45.67 contributes 2
    # digits before the decimal point (floor(log10(45.67)) + 1 = 2): the total
    # is 4 significant digits.  A value of 0 contributes 1 "digit" before the
    # decimal point.
    return max(
        0,
        (math.floor(math.log10(abs(value))) + 1 if value else 1)
        - math.floor(math.log10(delta)))


def _unikey_or_keysym_to_mplkey(unikey, keysym):
    """
    Convert a Unicode key or X keysym to a Matplotlib key name.

    The Unicode key is checked first; this avoids having to list most printable
    keysyms such as ``EuroSign``.
    """
    # For non-printable characters, gtk3 passes "\0" whereas tk passes an "".
    if unikey and unikey.isprintable():
        return unikey
    key = keysym.lower()
    if key.startswith("kp_"):  # keypad_x (including kp_enter).
        key = key[3:]
    if key.startswith("page_"):  # page_{up,down}
        key = key.replace("page_", "page")
    if key.endswith(("_l", "_r")):  # alt_l, ctrl_l, shift_l.
        key = key[:-2]
    if sys.platform == "darwin" and key == "meta":
        # meta should be reported as command on mac
        key = "cmd"
    key = {
        "return": "enter",
        "prior": "pageup",  # Used by tk.
        "next": "pagedown",  # Used by tk.
    }.get(key, key)
    return key


@functools.cache
def _make_class_factory(mixin_class, fmt, attr_name=None):
    """
    Return a function that creates picklable classes inheriting from a mixin.

    After ::

        factory = _make_class_factory(FooMixin, fmt, attr_name)
        FooAxes = factory(Axes)

    ``Foo`` is a class that inherits from ``FooMixin`` and ``Axes`` and **is
    picklable** (picklability is what differentiates this from a plain call to
    `type`).  Its ``__name__`` is set to ``fmt.format(Axes.__name__)`` and the
    base class is stored in the ``attr_name`` attribute, if not None.

    Moreover, the return value of ``factory`` is memoized: calls with the same
    ``Axes`` class always return the same subclass.
    """

    @functools.cache
    def class_factory(axes_class):
        # if we have already wrapped this class, declare victory!
        if issubclass(axes_class, mixin_class):
            return axes_class

        # The parameter is named "axes_class" for backcompat but is really just
        # a base class; no axes semantics are used.
        base_class = axes_class

        class subcls(mixin_class, base_class):
            # Better approximation than __module__ = "matplotlib.cbook".
            __module__ = mixin_class.__module__

            def __reduce__(self):
                return (_picklable_class_constructor,
                        (mixin_class, fmt, attr_name, base_class),
                        self.__getstate__())

        subcls.__name__ = subcls.__qualname__ = fmt.format(base_class.__name__)
        if attr_name is not None:
            setattr(subcls, attr_name, base_class)
        return subcls

    class_factory.__module__ = mixin_class.__module__
    return class_factory


def _picklable_class_constructor(mixin_class, fmt, attr_name, base_class):
    """Internal helper for _make_class_factory."""
    factory = _make_class_factory(mixin_class, fmt, attr_name)
    cls = factory(base_class)
    return cls.__new__(cls)


def _is_torch_array(x):
    """Return whether *x* is a PyTorch Tensor."""
    try:
        # We're intentionally not attempting to import torch. If somebody
        # has created a torch array, torch should already be in sys.modules.
        tp = sys.modules.get("torch").Tensor
    except AttributeError:
        return False  # Module not imported or a nonstandard module with no Tensor attr.
    return (isinstance(tp, type)  # Just in case it's a very nonstandard module.
            and isinstance(x, tp))


def _is_jax_array(x):
    """Return whether *x* is a JAX Array."""
    try:
        # We're intentionally not attempting to import jax. If somebody
        # has created a jax array, jax should already be in sys.modules.
        tp = sys.modules.get("jax").Array
    except AttributeError:
        return False  # Module not imported or a nonstandard module with no Array attr.
    return (isinstance(tp, type)  # Just in case it's a very nonstandard module.
            and isinstance(x, tp))


def _is_pandas_dataframe(x):
    """Check if *x* is a Pandas DataFrame."""
    try:
        # We're intentionally not attempting to import Pandas. If somebody
        # has created a Pandas DataFrame, Pandas should already be in sys.modules.
        tp = sys.modules.get("pandas").DataFrame
    except AttributeError:
        return False  # Module not imported or a nonstandard module with no Array attr.
    return (isinstance(tp, type)  # Just in case it's a very nonstandard module.
            and isinstance(x, tp))


def _is_tensorflow_array(x):
    """Return whether *x* is a TensorFlow Tensor or Variable."""
    try:
        # We're intentionally not attempting to import TensorFlow. If somebody
        # has created a TensorFlow array, TensorFlow should already be in
        # sys.modules we use `is_tensor` to not depend on the class structure
        # of TensorFlow arrays, as `tf.Variables` are not instances of
        # `tf.Tensor` (they both convert the same way).
        is_tensor = sys.modules.get("tensorflow").is_tensor
    except AttributeError:
        return False
    try:
        return is_tensor(x)
    except Exception:
        return False  # Just in case it's a very nonstandard module.


def _unpack_to_numpy(x):
    """Internal helper to extract data from e.g. pandas and xarray objects."""
    if isinstance(x, np.ndarray):
        # If numpy, return directly
        return x
    if hasattr(x, 'to_numpy'):
        # Assume that any to_numpy() method actually returns a numpy array
        return x.to_numpy()
    if hasattr(x, 'values'):
        xtmp = x.values
        # For example a dict has a 'values' attribute, but it is not a property
        # so in this case we do not want to return a function
        if isinstance(xtmp, np.ndarray):
            return xtmp
    if _is_torch_array(x) or _is_jax_array(x) or _is_tensorflow_array(x):
        # using np.asarray() instead of explicitly __array__(), as the latter is
        # only _one_ of many methods, and it's the last resort, see also
        # https://numpy.org/devdocs/user/basics.interoperability.html#using-arbitrary-objects-in-numpy
        # therefore, let arrays do better if they can
        xtmp = np.asarray(x)

        # In case np.asarray method does not return a numpy array in future
        if isinstance(xtmp, np.ndarray):
            return xtmp
    return x


def _auto_format_str(fmt, value):
    """
    Apply *value* to the format string *fmt*.

    This works both with unnamed %-style formatting and
    unnamed {}-style formatting. %-style formatting has priority.
    If *fmt* is %-style formattable that will be used. Otherwise,
    {}-formatting is applied. Strings without formatting placeholders
    are passed through as is.

    Examples
    --------
    >>> _auto_format_str('%.2f m', 0.2)
    '0.20 m'
    >>> _auto_format_str('{} m', 0.2)
    '0.2 m'
    >>> _auto_format_str('const', 0.2)
    'const'
    >>> _auto_format_str('%d or {}', 0.2)
    '0 or {}'
    """
    try:
        return fmt % (value,)
    except (TypeError, ValueError):
        return fmt.format(value)
