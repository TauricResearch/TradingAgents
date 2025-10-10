import sys
import logging
import timeit
from functools import wraps
from collections.abc import Mapping, Callable
import warnings
from logging import PercentStyle


# default logging level used by Timer class
TIME_LEVEL = logging.DEBUG

# per-level format strings used by the default formatter
# (the level name is not printed for INFO and DEBUG messages)
DEFAULT_FORMATS = {
    "*": "%(levelname)s: %(message)s",
    "INFO": "%(message)s",
    "DEBUG": "%(message)s",
}


class LevelFormatter(logging.Formatter):
    """Log formatter with level-specific formatting.

    Formatter class which optionally takes a dict of logging levels to
    format strings, allowing to customise the log records appearance for
    specific levels.


    Attributes:
            fmt: A dictionary mapping logging levels to format strings.
                    The ``*`` key identifies the default format string.
            datefmt: As per py:class:`logging.Formatter`
            style: As per py:class:`logging.Formatter`

    >>> import sys
    >>> handler = logging.StreamHandler(sys.stdout)
    >>> formatter = LevelFormatter(
    ...     fmt={
    ...         '*':     '[%(levelname)s] %(message)s',
    ...         'DEBUG': '%(name)s [%(levelname)s] %(message)s',
    ...         'INFO':  '%(message)s',
    ...     })
    >>> handler.setFormatter(formatter)
    >>> log = logging.getLogger('test')
    >>> log.setLevel(logging.DEBUG)
    >>> log.addHandler(handler)
    >>> log.debug('this uses a custom format string')
    test [DEBUG] this uses a custom format string
    >>> log.info('this also uses a custom format string')
    this also uses a custom format string
    >>> log.warning("this one uses the default format string")
    [WARNING] this one uses the default format string
    """

    def __init__(self, fmt=None, datefmt=None, style="%"):
        if style != "%":
            raise ValueError(
                "only '%' percent style is supported in both python 2 and 3"
            )
        if fmt is None:
            fmt = DEFAULT_FORMATS
        if isinstance(fmt, str):
            default_format = fmt
            custom_formats = {}
        elif isinstance(fmt, Mapping):
            custom_formats = dict(fmt)
            default_format = custom_formats.pop("*", None)
        else:
            raise TypeError("fmt must be a str or a dict of str: %r" % fmt)
        super(LevelFormatter, self).__init__(default_format, datefmt)
        self.default_format = self._fmt
        self.custom_formats = {}
        for level, fmt in custom_formats.items():
            level = logging._checkLevel(level)
            self.custom_formats[level] = fmt

    def format(self, record):
        if self.custom_formats:
            fmt = self.custom_formats.get(record.levelno, self.default_format)
            if self._fmt != fmt:
                self._fmt = fmt
                # for python >= 3.2, _style needs to be set if _fmt changes
                if PercentStyle:
                    self._style = PercentStyle(fmt)
        return super(LevelFormatter, self).format(record)


def configLogger(**kwargs):
    """A more sophisticated logging system configuation manager.

    This is more or less the same as :py:func:`logging.basicConfig`,
    with some additional options and defaults.

    The default behaviour is to create a ``StreamHandler`` which writes to
    sys.stderr, set a formatter using the ``DEFAULT_FORMATS`` strings, and add
    the handler to the top-level library logger ("fontTools").

    A number of optional keyword arguments may be specified, which can alter
    the default behaviour.

    Args:

            logger: Specifies the logger name or a Logger instance to be
                    configured. (Defaults to "fontTools" logger). Unlike ``basicConfig``,
                    this function can be called multiple times to reconfigure a logger.
                    If the logger or any of its children already exists before the call is
                    made, they will be reset before the new configuration is applied.
            filename: Specifies that a ``FileHandler`` be created, using the
                    specified filename, rather than a ``StreamHandler``.
            filemode: Specifies the mode to open the file, if filename is
                    specified. (If filemode is unspecified, it defaults to ``a``).
            format: Use the specified format string for the handler. This
                    argument also accepts a dictionary of format strings keyed by
                    level name, to allow customising the records appearance for
                    specific levels. The special ``'*'`` key is for 'any other' level.
            datefmt: Use the specified date/time format.
            level: Set the logger level to the specified level.
            stream: Use the specified stream to initialize the StreamHandler. Note
                    that this argument is incompatible with ``filename`` - if both
                    are present, ``stream`` is ignored.
            handlers: If specified, this should be an iterable of already created
                    handlers, which will be added to the logger. Any handler in the
                    list which does not have a formatter assigned will be assigned the
                    formatter created in this function.
            filters: If specified, this should be an iterable of already created
                    filters. If the ``handlers`` do not already have filters assigned,
                    these filters will be added to them.
            propagate: All loggers have a ``propagate`` attribute which determines
                    whether to continue searching for handlers up the logging hierarchy.
                    If not provided, the "propagate" attribute will be set to ``False``.
    """
    # using kwargs to enforce keyword-only arguments in py2.
    handlers = kwargs.pop("handlers", None)
    if handlers is None:
        if "stream" in kwargs and "filename" in kwargs:
            raise ValueError(
                "'stream' and 'filename' should not be " "specified together"
            )
    else:
        if "stream" in kwargs or "filename" in kwargs:
            raise ValueError(
                "'stream' or 'filename' should not be "
                "specified together with 'handlers'"
            )
    if handlers is None:
        filename = kwargs.pop("filename", None)
        mode = kwargs.pop("filemode", "a")
        if filename:
            h = logging.FileHandler(filename, mode)
        else:
            stream = kwargs.pop("stream", None)
            h = logging.StreamHandler(stream)
        handlers = [h]
    # By default, the top-level library logger is configured.
    logger = kwargs.pop("logger", "fontTools")
    if not logger or isinstance(logger, str):
        # empty "" or None means the 'root' logger
        logger = logging.getLogger(logger)
    # before (re)configuring, reset named logger and its children (if exist)
    _resetExistingLoggers(parent=logger.name)
    # use DEFAULT_FORMATS if 'format' is None
    fs = kwargs.pop("format", None)
    dfs = kwargs.pop("datefmt", None)
    # XXX: '%' is the only format style supported on both py2 and 3
    style = kwargs.pop("style", "%")
    fmt = LevelFormatter(fs, dfs, style)
    filters = kwargs.pop("filters", [])
    for h in handlers:
        if h.formatter is None:
            h.setFormatter(fmt)
        if not h.filters:
            for f in filters:
                h.addFilter(f)
        logger.addHandler(h)
    if logger.name != "root":
        # stop searching up the hierarchy for handlers
        logger.propagate = kwargs.pop("propagate", False)
    # set a custom severity level
    level = kwargs.pop("level", None)
    if level is not None:
        logger.setLevel(level)
    if kwargs:
        keys = ", ".join(kwargs.keys())
        raise ValueError("Unrecognised argument(s): %s" % keys)


def _resetExistingLoggers(parent="root"):
    """Reset the logger named 'parent' and all its children to their initial
    state, if they already exist in the current configuration.
    """
    root = logging.root
    # get sorted list of all existing loggers
    existing = sorted(root.manager.loggerDict.keys())
    if parent == "root":
        # all the existing loggers are children of 'root'
        loggers_to_reset = [parent] + existing
    elif parent not in existing:
        # nothing to do
        return
    elif parent in existing:
        loggers_to_reset = [parent]
        # collect children, starting with the entry after parent name
        i = existing.index(parent) + 1
        prefixed = parent + "."
        pflen = len(prefixed)
        num_existing = len(existing)
        while i < num_existing:
            if existing[i][:pflen] == prefixed:
                loggers_to_reset.append(existing[i])
            i += 1
    for name in loggers_to_reset:
        if name == "root":
            root.setLevel(logging.WARNING)
            for h in root.handlers[:]:
                root.removeHandler(h)
            for f in root.filters[:]:
                root.removeFilters(f)
            root.disabled = False
        else:
            logger = root.manager.loggerDict[name]
            logger.level = logging.NOTSET
            logger.handlers = []
            logger.filters = []
            logger.propagate = True
            logger.disabled = False


class Timer(object):
    """Keeps track of overall time and split/lap times.

    >>> import time
    >>> timer = Timer()
    >>> time.sleep(0.01)
    >>> print("First lap:", timer.split())
    First lap: ...
    >>> time.sleep(0.02)
    >>> print("Second lap:", timer.split())
    Second lap: ...
    >>> print("Overall time:", timer.time())
    Overall time: ...

    Can be used as a context manager inside with-statements.

    >>> with Timer() as t:
    ...     time.sleep(0.01)
    >>> print("%0.3f seconds" % t.elapsed)
    0... seconds

    If initialised with a logger, it can log the elapsed time automatically
    upon exiting the with-statement.

    >>> import logging
    >>> log = logging.getLogger("my-fancy-timer-logger")
    >>> configLogger(logger=log, level="DEBUG", format="%(message)s", stream=sys.stdout)
    >>> with Timer(log, 'do something'):
    ...     time.sleep(0.01)
    Took ... to do something

    The same Timer instance, holding a reference to a logger, can be reused
    in multiple with-statements, optionally with different messages or levels.

    >>> timer = Timer(log)
    >>> with timer():
    ...     time.sleep(0.01)
    elapsed time: ...s
    >>> with timer('redo it', level=logging.INFO):
    ...     time.sleep(0.02)
    Took ... to redo it

    It can also be used as a function decorator to log the time elapsed to run
    the decorated function.

    >>> @timer()
    ... def test1():
    ...    time.sleep(0.01)
    >>> @timer('run test 2', level=logging.INFO)
    ... def test2():
    ...    time.sleep(0.02)
    >>> test1()
    Took ... to run 'test1'
    >>> test2()
    Took ... to run test 2
    """

    # timeit.default_timer choses the most accurate clock for each platform
    _time: Callable[[], float] = staticmethod(timeit.default_timer)
    default_msg = "elapsed time: %(time).3fs"
    default_format = "Took %(time).3fs to %(msg)s"

    def __init__(self, logger=None, msg=None, level=None, start=None):
        self.reset(start)
        if logger is None:
            for arg in ("msg", "level"):
                if locals().get(arg) is not None:
                    raise ValueError("'%s' can't be specified without a 'logger'" % arg)
        self.logger = logger
        self.level = level if level is not None else TIME_LEVEL
        self.msg = msg

    def reset(self, start=None):
        """Reset timer to 'start_time' or the current time."""
        if start is None:
            self.start = self._time()
        else:
            self.start = start
        self.last = self.start
        self.elapsed = 0.0

    def time(self):
        """Return the overall time (in seconds) since the timer started."""
        return self._time() - self.start

    def split(self):
        """Split and return the lap time (in seconds) in between splits."""
        current = self._time()
        self.elapsed = current - self.last
        self.last = current
        return self.elapsed

    def formatTime(self, msg, time):
        """Format 'time' value in 'msg' and return formatted string.
        If 'msg' contains a '%(time)' format string, try to use that.
        Otherwise, use the predefined 'default_format'.
        If 'msg' is empty or None, fall back to 'default_msg'.
        """
        if not msg:
            msg = self.default_msg
        if msg.find("%(time)") < 0:
            msg = self.default_format % {"msg": msg, "time": time}
        else:
            try:
                msg = msg % {"time": time}
            except (KeyError, ValueError):
                pass  # skip if the format string is malformed
        return msg

    def __enter__(self):
        """Start a new lap"""
        self.last = self._time()
        self.elapsed = 0.0
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """End the current lap. If timer has a logger, log the time elapsed,
        using the format string in self.msg (or the default one).
        """
        time = self.split()
        if self.logger is None or exc_type:
            # if there's no logger attached, or if any exception occurred in
            # the with-statement, exit without logging the time
            return
        message = self.formatTime(self.msg, time)
        # Allow log handlers to see the individual parts to facilitate things
        # like a server accumulating aggregate stats.
        msg_parts = {"msg": self.msg, "time": time}
        self.logger.log(self.level, message, msg_parts)

    def __call__(self, func_or_msg=None, **kwargs):
        """If the first argument is a function, return a decorator which runs
        the wrapped function inside Timer's context manager.
        Otherwise, treat the first argument as a 'msg' string and return an updated
        Timer instance, referencing the same logger.
        A 'level' keyword can also be passed to override self.level.
        """
        if isinstance(func_or_msg, Callable):
            func = func_or_msg
            # use the function name when no explicit 'msg' is provided
            if not self.msg:
                self.msg = "run '%s'" % func.__name__

            @wraps(func)
            def wrapper(*args, **kwds):
                with self:
                    return func(*args, **kwds)

            return wrapper
        else:
            msg = func_or_msg or kwargs.get("msg")
            level = kwargs.get("level", self.level)
            return self.__class__(self.logger, msg, level)

    def __float__(self):
        return self.elapsed

    def __int__(self):
        return int(self.elapsed)

    def __str__(self):
        return "%.3f" % self.elapsed


class ChannelsFilter(logging.Filter):
    """Provides a hierarchical filter for log entries based on channel names.

    Filters out records emitted from a list of enabled channel names,
    including their children. It works the same as the ``logging.Filter``
    class, but allows the user to specify multiple channel names.

    >>> import sys
    >>> handler = logging.StreamHandler(sys.stdout)
    >>> handler.setFormatter(logging.Formatter("%(message)s"))
    >>> filter = ChannelsFilter("A.B", "C.D")
    >>> handler.addFilter(filter)
    >>> root = logging.getLogger()
    >>> root.addHandler(handler)
    >>> root.setLevel(level=logging.DEBUG)
    >>> logging.getLogger('A.B').debug('this record passes through')
    this record passes through
    >>> logging.getLogger('A.B.C').debug('records from children also pass')
    records from children also pass
    >>> logging.getLogger('C.D').debug('this one as well')
    this one as well
    >>> logging.getLogger('A.B.').debug('also this one')
    also this one
    >>> logging.getLogger('A.F').debug('but this one does not!')
    >>> logging.getLogger('C.DE').debug('neither this one!')
    """

    def __init__(self, *names):
        self.names = names
        self.num = len(names)
        self.lengths = {n: len(n) for n in names}

    def filter(self, record):
        if self.num == 0:
            return True
        for name in self.names:
            nlen = self.lengths[name]
            if name == record.name:
                return True
            elif record.name.find(name, 0, nlen) == 0 and record.name[nlen] == ".":
                return True
        return False


class CapturingLogHandler(logging.Handler):
    def __init__(self, logger, level):
        super(CapturingLogHandler, self).__init__(level=level)
        self.records = []
        if isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger

    def __enter__(self):
        self.original_disabled = self.logger.disabled
        self.original_level = self.logger.level
        self.original_propagate = self.logger.propagate

        self.logger.addHandler(self)
        self.logger.setLevel(self.level)
        self.logger.disabled = False
        self.logger.propagate = False

        return self

    def __exit__(self, type, value, traceback):
        self.logger.removeHandler(self)
        self.logger.setLevel(self.original_level)
        self.logger.disabled = self.original_disabled
        self.logger.propagate = self.original_propagate

        return self

    def emit(self, record):
        self.records.append(record)

    def assertRegex(self, regexp, msg=None):
        import re

        pattern = re.compile(regexp)
        for r in self.records:
            if pattern.search(r.getMessage()):
                return True
        if msg is None:
            msg = "Pattern '%s' not found in logger records" % regexp
        assert 0, msg


class LogMixin(object):
    """Mixin class that adds logging functionality to another class.

    You can define a new class that subclasses from ``LogMixin`` as well as
    other base classes through multiple inheritance.
    All instances of that class will have a ``log`` property that returns
    a ``logging.Logger`` named after their respective ``<module>.<class>``.

    For example:

    >>> class BaseClass(object):
    ...     pass
    >>> class MyClass(LogMixin, BaseClass):
    ...     pass
    >>> a = MyClass()
    >>> isinstance(a.log, logging.Logger)
    True
    >>> print(a.log.name)
    fontTools.misc.loggingTools.MyClass
    >>> class AnotherClass(MyClass):
    ...     pass
    >>> b = AnotherClass()
    >>> isinstance(b.log, logging.Logger)
    True
    >>> print(b.log.name)
    fontTools.misc.loggingTools.AnotherClass
    """

    @property
    def log(self):
        if not hasattr(self, "_log"):
            name = ".".join((self.__class__.__module__, self.__class__.__name__))
            self._log = logging.getLogger(name)
        return self._log


def deprecateArgument(name, msg, category=UserWarning):
    """Raise a warning about deprecated function argument 'name'."""
    warnings.warn("%r is deprecated; %s" % (name, msg), category=category, stacklevel=3)


def deprecateFunction(msg, category=UserWarning):
    """Decorator to raise a warning when a deprecated function is called."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(
                "%r is deprecated; %s" % (func.__name__, msg),
                category=category,
                stacklevel=2,
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator


if __name__ == "__main__":
    import doctest

    sys.exit(doctest.testmod(optionflags=doctest.ELLIPSIS).failed)
