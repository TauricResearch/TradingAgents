import logging
import weakref
from threading import local as thread_local
from threading import Event
from threading import Lock
from threading import Thread
try:
    from Queue import Queue
except ImportError:
    from queue import Queue

try:
    import gevent
    from gevent import Greenlet as GThread
    from gevent.event import Event as GEvent
    from gevent.local import local as greenlet_local
    from gevent.queue import Queue as GQueue
except ImportError:
    GThread = GQueue = GEvent = None

from peewee import __deprecated__
from playhouse.sqlite_ext import SqliteExtDatabase


logger = logging.getLogger('peewee.sqliteq')


class ResultTimeout(Exception):
    pass

class WriterPaused(Exception):
    pass

class ShutdownException(Exception):
    pass


class AsyncCursor(object):
    __slots__ = ('sql', 'params', 'timeout',
                 '_event', '_cursor', '_exc', '_idx', '_rows', '_ready')

    def __init__(self, event, sql, params, timeout):
        self._event = event
        self.sql = sql
        self.params = params
        self.timeout = timeout
        self._cursor = self._exc = self._idx = self._rows = None
        self._ready = False

    def set_result(self, cursor, exc=None):
        self._cursor = cursor
        self._exc = exc
        self._idx = 0
        self._rows = cursor.fetchall() if exc is None else []
        self._event.set()
        return self

    def _wait(self, timeout=None):
        timeout = timeout if timeout is not None else self.timeout
        if not self._event.wait(timeout=timeout) and timeout:
            raise ResultTimeout('results not ready, timed out.')
        if self._exc is not None:
            raise self._exc
        self._ready = True

    def __iter__(self):
        if not self._ready:
            self._wait()
        if self._exc is not None:
            raise self._exc
        return self

    def next(self):
        if not self._ready:
            self._wait()
        try:
            obj = self._rows[self._idx]
        except IndexError:
            raise StopIteration
        else:
            self._idx += 1
            return obj
    __next__ = next

    @property
    def lastrowid(self):
        if not self._ready:
            self._wait()
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        if not self._ready:
            self._wait()
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()

    def fetchall(self):
        return list(self)  # Iterating implies waiting until populated.

    def fetchone(self):
        if not self._ready:
            self._wait()
        try:
            return next(self)
        except StopIteration:
            return None

SHUTDOWN = StopIteration
QUERY = object()
PAUSE = object()
UNPAUSE = object()


class Writer(object):
    __slots__ = ('database', 'queue')

    def __init__(self, database, queue):
        self.database = database
        self.queue = queue

    def run(self):
        conn = self.database.connection()
        try:
            while True:
                try:
                    if conn is None:  # Paused.
                        if self.wait_unpause():
                            conn = self.database.connection()
                    else:
                        conn = self.loop(conn)
                except ShutdownException:
                    logger.info('writer received shutdown request, exiting.')
                    return
        finally:
            if conn is not None:
                self.database._close(conn)
                self.database._state.reset()

    def wait_unpause(self):
        op, obj = self.queue.get()
        if op is UNPAUSE:
            logger.info('writer unpaused - reconnecting to database.')
            obj.set()
            return True
        elif op is SHUTDOWN:
            raise ShutdownException()
        elif op is PAUSE:
            logger.error('writer received pause, but is already paused.')
            obj.set()
        else:
            obj.set_result(None, WriterPaused())
            logger.warning('writer paused, not handling %s', obj)

    def loop(self, conn):
        op, obj = self.queue.get()
        if op is QUERY:
            self.execute(obj)
        elif op is PAUSE:
            logger.info('writer paused - closing database connection.')
            self.database._close(conn)
            self.database._state.reset()
            obj.set()
            return
        elif op is UNPAUSE:
            logger.error('writer received unpause, but is already running.')
            obj.set()
        elif op is SHUTDOWN:
            raise ShutdownException()
        else:
            logger.error('writer received unsupported object: %s', obj)
        return conn

    def execute(self, obj):
        logger.debug('received query %s', obj.sql)
        try:
            cursor = self.database._execute(obj.sql, obj.params)
        except Exception as execute_err:
            cursor = None
            exc = execute_err  # python3 is so fucking lame.
        else:
            exc = None
        return obj.set_result(cursor, exc)


class SqliteQueueDatabase(SqliteExtDatabase):
    WAL_MODE_ERROR_MESSAGE = ('SQLite must be configured to use the WAL '
                              'journal mode when using this feature. WAL mode '
                              'allows one or more readers to continue reading '
                              'while another connection writes to the '
                              'database.')

    def __init__(self, database, use_gevent=False, autostart=True,
                 queue_max_size=None, results_timeout=None, *args, **kwargs):
        kwargs['check_same_thread'] = False

        # Lock around starting and stopping write thread operations.
        self._qlock = Lock()

        # Ensure that journal_mode is WAL. This value is passed to the parent
        # class constructor below.
        pragmas = self._validate_journal_mode(kwargs.pop('pragmas', None))

        # Reference to execute_sql on the parent class. Since we've overridden
        # execute_sql(), this is just a handy way to reference the real
        # implementation.
        Parent = super(SqliteQueueDatabase, self)
        self._execute = Parent.execute_sql

        # Call the parent class constructor with our modified pragmas.
        Parent.__init__(database, pragmas=pragmas, *args, **kwargs)

        self._autostart = autostart
        self._results_timeout = results_timeout
        self._is_stopped = True

        # Get different objects depending on the threading implementation.
        self._thread_helper = self.get_thread_impl(use_gevent)(queue_max_size)

        # Create the writer thread, optionally starting it.
        self._create_write_queue()
        if self._autostart:
            self.start()

    def get_thread_impl(self, use_gevent):
        return GreenletHelper if use_gevent else ThreadHelper

    def _validate_journal_mode(self, pragmas=None):
        if not pragmas:
            return {'journal_mode': 'wal'}

        if not isinstance(pragmas, dict):
            pragmas = dict((k.lower(), v) for (k, v) in pragmas)
        if pragmas.get('journal_mode', 'wal').lower() != 'wal':
            raise ValueError(self.WAL_MODE_ERROR_MESSAGE)

        pragmas['journal_mode'] = 'wal'
        return pragmas

    def _create_write_queue(self):
        self._write_queue = self._thread_helper.queue()

    def queue_size(self):
        return self._write_queue.qsize()

    def execute_sql(self, sql, params=None, commit=None, timeout=None):
        if commit is not None:
            __deprecated__('"commit" has been deprecated and is a no-op.')
        if sql.lower().startswith('select'):
            return self._execute(sql, params)

        cursor = AsyncCursor(
            event=self._thread_helper.event(),
            sql=sql,
            params=params,
            timeout=self._results_timeout if timeout is None else timeout)
        self._write_queue.put((QUERY, cursor))
        return cursor

    def start(self):
        with self._qlock:
            if not self._is_stopped:
                return False
            def run():
                writer = Writer(self, self._write_queue)
                writer.run()

            self._writer = self._thread_helper.thread(run)
            self._writer.start()
            self._is_stopped = False
            return True

    def stop(self):
        logger.debug('environment stop requested.')
        with self._qlock:
            if self._is_stopped:
                return False

            self._write_queue.put((SHUTDOWN, None))
            self._writer.join()

            # Empty queue of any remaining tasks.
            while not self._write_queue.empty():
                op, obj = self._write_queue.get()
                if op == PAUSE or op == UNPAUSE:
                    obj.set()
                elif op == QUERY:
                    obj.set_result(None, ShutdownException())

            self._is_stopped = True
            return True

    def is_stopped(self):
        with self._qlock:
            return self._is_stopped

    def pause(self):
        with self._qlock:
            if self._is_stopped:
                return False

            evt = self._thread_helper.event()
            self._write_queue.put((PAUSE, evt))

        evt.wait()

    def unpause(self):
        with self._qlock:
            if self._is_stopped:
                return False

            evt = self._thread_helper.event()
            self._write_queue.put((UNPAUSE, evt))

        evt.wait()

    def __unsupported__(self, *args, **kwargs):
        raise ValueError('This method is not supported by %r.' % type(self))
    atomic = transaction = savepoint = __unsupported__


class ThreadHelper(object):
    __slots__ = ('queue_max_size',)

    def __init__(self, queue_max_size=None):
        self.queue_max_size = queue_max_size

    def event(self): return Event()

    def queue(self, max_size=None):
        max_size = max_size if max_size is not None else self.queue_max_size
        return Queue(maxsize=max_size or 0)

    def thread(self, fn, *args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.daemon = True
        return thread


class GreenletHelper(ThreadHelper):
    __slots__ = ()

    def event(self): return GEvent()

    def queue(self, max_size=None):
        max_size = max_size if max_size is not None else self.queue_max_size
        return GQueue(maxsize=max_size or 0)

    def thread(self, fn, *args, **kwargs):
        def wrap(*a, **k):
            gevent.sleep()
            return fn(*a, **k)
        return GThread(wrap, *args, **kwargs)
