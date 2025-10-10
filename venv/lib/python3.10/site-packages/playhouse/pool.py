"""
Lightweight connection pooling for peewee.

In a multi-threaded application, up to `max_connections` will be opened. Each
thread (or, if using gevent, greenlet) will have it's own connection.

In a single-threaded application, only one connection will be created. It will
be continually recycled until either it exceeds the stale timeout or is closed
explicitly (using `.manual_close()`).

By default, all your application needs to do is ensure that connections are
closed when you are finished with them, and they will be returned to the pool.
For web applications, this typically means that at the beginning of a request,
you will open a connection, and when you return a response, you will close the
connection.

Simple Postgres pool example code:

    # Use the special postgresql extensions.
    from playhouse.pool import PooledPostgresqlExtDatabase

    db = PooledPostgresqlExtDatabase(
        'my_app',
        max_connections=32,
        stale_timeout=300,  # 5 minutes.
        user='postgres')

    class BaseModel(Model):
        class Meta:
            database = db

That's it!
"""
import functools
import heapq
import logging
import threading
import time
from collections import namedtuple
from itertools import chain

try:
    from psycopg2.extensions import TRANSACTION_STATUS_IDLE
    from psycopg2.extensions import TRANSACTION_STATUS_INERROR
    from psycopg2.extensions import TRANSACTION_STATUS_UNKNOWN
except ImportError:
    TRANSACTION_STATUS_IDLE = \
            TRANSACTION_STATUS_INERROR = \
            TRANSACTION_STATUS_UNKNOWN = None
try:
    from psycopg.pq import TransactionStatus
except ImportError:
    pass

from peewee import MySQLDatabase
from peewee import PostgresqlDatabase
from peewee import SqliteDatabase

logger = logging.getLogger('peewee.pool')


def make_int(val):
    if val is not None and not isinstance(val, (int, float)):
        return int(val)
    return val


class MaxConnectionsExceeded(ValueError): pass


PoolConnection = namedtuple('PoolConnection', ('timestamp', 'connection',
                                               'checked_out'))

class _sentinel(object):
    def __lt__(self, other):
        return True


def locked(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        with self._pool_lock:
            return fn(self, *args, **kwargs)
    return inner


class PooledDatabase(object):
    def __init__(self, database, max_connections=20, stale_timeout=None,
                 timeout=None, **kwargs):
        self._max_connections = make_int(max_connections)
        self._stale_timeout = make_int(stale_timeout)
        self._wait_timeout = make_int(timeout)
        if self._wait_timeout == 0:
            self._wait_timeout = float('inf')

        self._pool_lock = threading.RLock()

        # Available / idle connections stored in a heap, sorted oldest first.
        self._connections = []

        # Mapping of connection id to PoolConnection. Ordinarily we would want
        # to use something like a WeakKeyDictionary, but Python typically won't
        # allow us to create weak references to connection objects.
        self._in_use = {}

        # Use the memory address of the connection as the key in the event the
        # connection object is not hashable. Connections will not get
        # garbage-collected, however, because a reference to them will persist
        # in "_in_use" as long as the conn has not been closed.
        self.conn_key = id

        super(PooledDatabase, self).__init__(database, **kwargs)

    def init(self, database, max_connections=None, stale_timeout=None,
             timeout=None, **connect_kwargs):
        super(PooledDatabase, self).init(database, **connect_kwargs)
        if max_connections is not None:
            self._max_connections = make_int(max_connections)
        if stale_timeout is not None:
            self._stale_timeout = make_int(stale_timeout)
        if timeout is not None:
            self._wait_timeout = make_int(timeout)
            if self._wait_timeout == 0:
                self._wait_timeout = float('inf')

    def connect(self, reuse_if_open=False):
        if not self._wait_timeout:
            return super(PooledDatabase, self).connect(reuse_if_open)

        expires = time.time() + self._wait_timeout
        while expires > time.time():
            try:
                ret = super(PooledDatabase, self).connect(reuse_if_open)
            except MaxConnectionsExceeded:
                time.sleep(0.1)
            else:
                return ret
        raise MaxConnectionsExceeded('Max connections exceeded, timed out '
                                     'attempting to connect.')

    @locked
    def _connect(self):
        while True:
            try:
                # Remove the oldest connection from the heap.
                ts, _, c_conn = heapq.heappop(self._connections)
                conn = c_conn
                key = self.conn_key(conn)
            except IndexError:
                ts = conn = None
                logger.debug('No connection available in pool.')
                break
            else:
                if self._is_closed(conn):
                    # This connecton was closed, but since it was not stale
                    # it got added back to the queue of available conns. We
                    # then closed it and marked it as explicitly closed, so
                    # it's safe to throw it away now.
                    # (Because Database.close() calls Database._close()).
                    logger.debug('Connection %s was closed.', key)
                    ts = conn = None
                elif self._stale_timeout and self._is_stale(ts):
                    # If we are attempting to check out a stale connection,
                    # then close it. We don't need to mark it in the "closed"
                    # set, because it is not in the list of available conns
                    # anymore.
                    logger.debug('Connection %s was stale, closing.', key)
                    self._close(conn, True)
                    ts = conn = None
                else:
                    break

        if conn is None:
            if self._max_connections and (
                    len(self._in_use) >= self._max_connections):
                raise MaxConnectionsExceeded('Exceeded maximum connections.')
            conn = super(PooledDatabase, self)._connect()
            ts = time.time()
            key = self.conn_key(conn)
            logger.debug('Created new connection %s.', key)

        self._in_use[key] = PoolConnection(ts, conn, time.time())
        return conn

    def _is_stale(self, timestamp):
        # Called on check-out and check-in to ensure the connection has
        # not outlived the stale timeout.
        return (time.time() - timestamp) > self._stale_timeout

    def _is_closed(self, conn):
        return False

    def _can_reuse(self, conn):
        # Called on check-in to make sure the connection can be re-used.
        return True

    @locked
    def _close(self, conn, close_conn=False):
        key = self.conn_key(conn)
        if close_conn:
            super(PooledDatabase, self)._close(conn)
        elif key in self._in_use:
            pool_conn = self._in_use.pop(key)
            if self._stale_timeout and self._is_stale(pool_conn.timestamp):
                logger.debug('Closing stale connection %s.', key)
                super(PooledDatabase, self)._close(conn)
            elif self._can_reuse(conn):
                logger.debug('Returning %s to pool.', key)
                heapq.heappush(self._connections,
                               (pool_conn.timestamp, _sentinel(), conn))
            else:
                logger.debug('Closed %s.', key)

    @locked
    def manual_close(self):
        """
        Close the underlying connection without returning it to the pool.
        """
        if self.is_closed():
            return False

        # Obtain reference to the connection in-use by the calling thread.
        conn = self.connection()

        # A connection will only be re-added to the available list if it is
        # marked as "in use" at the time it is closed. We will explicitly
        # remove it from the "in use" list, call "close()" for the
        # side-effects, and then explicitly close the connection.
        self._in_use.pop(self.conn_key(conn), None)
        self.close()
        self._close(conn, close_conn=True)

    @locked
    def close_idle(self):
        # Close any open connections that are not currently in-use.
        for _, _, conn in self._connections:
            self._close(conn, close_conn=True)
        self._connections = []

    @locked
    def close_stale(self, age=600):
        # Close any connections that are in-use but were checked out quite some
        # time ago and can be considered stale.
        in_use = {}
        cutoff = time.time() - age
        n = 0
        for key, pool_conn in self._in_use.items():
            if pool_conn.checked_out < cutoff:
                self._close(pool_conn.connection, close_conn=True)
                n += 1
            else:
                in_use[key] = pool_conn
        self._in_use = in_use
        return n

    @locked
    def close_all(self):
        # Close all connections -- available and in-use. Warning: may break any
        # active connections used by other threads.
        self.close()
        for _, _, conn in self._connections:
            self._close(conn, close_conn=True)
        for pool_conn in self._in_use.values():
            self._close(pool_conn.connection, close_conn=True)
        self._connections = []
        self._in_use = {}


class PooledMySQLDatabase(PooledDatabase, MySQLDatabase):
    def _is_closed(self, conn):
        if self.server_version[0] == 8:
            args = ()
        else:
            args = (False,)
        try:
            conn.ping(*args)
        except:
            return True
        else:
            return False


class _PooledPostgresqlDatabase(PooledDatabase):
    def _is_closed(self, conn):
        if conn.closed:
            return True

        txn_status = conn.get_transaction_status()
        if txn_status == TRANSACTION_STATUS_UNKNOWN:
            return True
        elif txn_status != TRANSACTION_STATUS_IDLE:
            conn.rollback()
        return False

    def _can_reuse(self, conn):
        txn_status = conn.get_transaction_status()
        # Do not return connection in an error state, as subsequent queries
        # will all fail. If the status is unknown then we lost the connection
        # to the server and the connection should not be re-used.
        if txn_status == TRANSACTION_STATUS_UNKNOWN:
            return False
        elif txn_status == TRANSACTION_STATUS_INERROR:
            conn.reset()
        elif txn_status != TRANSACTION_STATUS_IDLE:
            conn.rollback()
        return True

class PooledPostgresqlDatabase(_PooledPostgresqlDatabase, PostgresqlDatabase):
    pass

try:
    from playhouse.postgres_ext import PostgresqlExtDatabase

    class PooledPostgresqlExtDatabase(_PooledPostgresqlDatabase, PostgresqlExtDatabase):
        pass
except ImportError:
    PooledPostgresqlExtDatabase = None


try:
    from playhouse.psycopg3_ext import Psycopg3Database

    class PooledPsycopg3Database(PooledDatabase, Psycopg3Database):
        def _is_closed(self, conn):
            if conn.closed:
                return True

            txn_status = conn.pgconn.transaction_status
            if txn_status == TransactionStatus.UNKNOWN:
                return True
            elif txn_status != TransactionStatus.IDLE:
                conn.rollback()
            return False

        def _can_reuse(self, conn):
            txn_status = conn.pgconn.transaction_status
            # Do not return connection in an error state, as subsequent queries
            # will all fail. If the status is unknown then we lost the connection
            # to the server and the connection should not be re-used.
            if txn_status == TransactionStatus.UNKNOWN:
                return False
            elif txn_status == TransactionStatus.INERROR:
                conn.reset()
            elif txn_status != TransactionStatus.IDLE:
                conn.rollback()
            return True
except ImportError:
    PooledPsycopg3Database = None


class _PooledSqliteDatabase(PooledDatabase):
    def _is_closed(self, conn):
        try:
            conn.total_changes
        except:
            return True
        else:
            return False

class PooledSqliteDatabase(_PooledSqliteDatabase, SqliteDatabase):
    pass

try:
    from playhouse.sqlite_ext import SqliteExtDatabase

    class PooledSqliteExtDatabase(_PooledSqliteDatabase, SqliteExtDatabase):
        pass
except ImportError:
    PooledSqliteExtDatabase = None

try:
    from playhouse.sqlite_ext import CSqliteExtDatabase

    class PooledCSqliteExtDatabase(_PooledSqliteDatabase, CSqliteExtDatabase):
        pass
except ImportError:
    PooledCSqliteExtDatabase = None
