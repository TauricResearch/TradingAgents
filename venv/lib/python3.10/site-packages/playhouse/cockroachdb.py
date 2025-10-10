import functools
import re
import sys

from peewee import *
from peewee import _atomic
from peewee import _manual
from peewee import ColumnMetadata  # (name, data_type, null, primary_key, table, default)
from peewee import EnclosedNodeList
from peewee import Entity
from peewee import ForeignKeyMetadata  # (column, dest_table, dest_column, table).
from peewee import IndexMetadata
from peewee import NodeList
from playhouse.pool import _PooledPostgresqlDatabase
try:
    from playhouse.postgres_ext import ArrayField
    from playhouse.postgres_ext import BinaryJSONField
    from playhouse.postgres_ext import IntervalField
    JSONField = BinaryJSONField
except ImportError:  # psycopg2 not installed, ignore.
    ArrayField = BinaryJSONField = IntervalField = JSONField = None

if sys.version_info[0] > 2:
    basestring = str


NESTED_TX_MIN_VERSION = 200100

TXN_ERR_MSG = ('CockroachDB does not support nested transactions. You may '
               'alternatively use the @transaction context-manager/decorator, '
               'which only wraps the outer-most block in transactional logic. '
               'To run a transaction with automatic retries, use the '
               'run_transaction() helper.')

class ExceededMaxAttempts(OperationalError): pass


class UUIDKeyField(UUIDField):
    auto_increment = True

    def __init__(self, *args, **kwargs):
        if kwargs.get('constraints'):
            raise ValueError('%s cannot specify constraints.' % type(self))
        kwargs['constraints'] = [SQL('DEFAULT gen_random_uuid()')]
        kwargs.setdefault('primary_key', True)
        super(UUIDKeyField, self).__init__(*args, **kwargs)


class RowIDField(AutoField):
    field_type = 'INT'

    def __init__(self, *args, **kwargs):
        if kwargs.get('constraints'):
            raise ValueError('%s cannot specify constraints.' % type(self))
        kwargs['constraints'] = [SQL('DEFAULT unique_rowid()')]
        super(RowIDField, self).__init__(*args, **kwargs)


class CockroachDatabase(PostgresqlDatabase):
    field_types = PostgresqlDatabase.field_types.copy()
    field_types.update({
        'BLOB': 'BYTES',
    })

    release_after_rollback = True

    def __init__(self, database, *args, **kwargs):
        # Unless a DSN or database connection-url were specified, provide
        # convenient defaults for the user and port.
        if 'dsn' not in kwargs and (database and
                                    not database.startswith('postgresql://')):
            kwargs.setdefault('user', 'root')
            kwargs.setdefault('port', 26257)
        super(CockroachDatabase, self).__init__(database, *args, **kwargs)

    def _set_server_version(self, conn):
        curs = conn.cursor()
        curs.execute('select version()')
        raw, = curs.fetchone()
        match_obj = re.match(r'^CockroachDB.+?v(\d+)\.(\d+)\.(\d+)', raw)
        if match_obj is not None:
            clean = '%d%02d%02d' % tuple(int(i) for i in match_obj.groups())
            self.server_version = int(clean)  # 19.1.5 -> 190105.
        else:
            # Fallback to use whatever cockroachdb tells us via protocol.
            super(CockroachDatabase, self)._set_server_version(conn)

    def _get_pk_constraint(self, table, schema=None):
        query = ('SELECT constraint_name '
                 'FROM information_schema.table_constraints '
                 'WHERE table_name = %s AND table_schema = %s '
                 'AND constraint_type = %s')
        cursor = self.execute_sql(query, (table, schema or 'public',
                                          'PRIMARY KEY'))
        row = cursor.fetchone()
        return row and row[0] or None

    def get_indexes(self, table, schema=None):
        # The primary-key index is returned by default, so we will just strip
        # it out here.
        indexes = super(CockroachDatabase, self).get_indexes(table, schema)
        pkc = self._get_pk_constraint(table, schema)
        return [idx for idx in indexes if (not pkc) or (idx.name != pkc)]

    def conflict_statement(self, on_conflict, query):
        if not on_conflict._action: return

        action = on_conflict._action.lower()
        if action in ('replace', 'upsert'):
            return SQL('UPSERT')
        elif action not in ('ignore', 'nothing', 'update'):
            raise ValueError('Un-supported action for conflict resolution. '
                             'CockroachDB supports REPLACE (UPSERT), IGNORE '
                             'and UPDATE.')

    def conflict_update(self, oc, query):
        action = oc._action.lower() if oc._action else ''
        if action in ('ignore', 'nothing'):
            parts = [SQL('ON CONFLICT')]
            if oc._conflict_target:
                parts.append(EnclosedNodeList([
                    Entity(col) if isinstance(col, basestring) else col
                    for col in oc._conflict_target]))
            parts.append(SQL('DO NOTHING'))
            return NodeList(parts)
        elif action in ('replace', 'upsert'):
            # No special stuff is necessary, this is just indicated by starting
            # the statement with UPSERT instead of INSERT.
            return
        elif oc._conflict_constraint:
            raise ValueError('CockroachDB does not support the usage of a '
                             'constraint name. Use the column(s) instead.')

        return super(CockroachDatabase, self).conflict_update(oc, query)

    def extract_date(self, date_part, date_field):
        return fn.extract(date_part, date_field)

    def from_timestamp(self, date_field):
        # CRDB does not allow casting a decimal/float to timestamp, so we first
        # cast to int, then to timestamptz.
        return date_field.cast('int').cast('timestamptz')

    def begin(self, system_time=None, priority=None):
        super(CockroachDatabase, self).begin()
        if system_time is not None:
            self.cursor().execute('SET TRANSACTION AS OF SYSTEM TIME %s',
                                  (system_time,))
        if priority is not None:
            priority = priority.lower()
            if priority not in ('low', 'normal', 'high'):
                raise ValueError('priority must be low, normal or high')
            self.cursor().execute('SET TRANSACTION PRIORITY %s' % priority)

    def atomic(self, system_time=None, priority=None):
        if self.is_closed(): self.connect()  # Side-effect, set server version.
        if self.server_version < NESTED_TX_MIN_VERSION:
            return _crdb_atomic(self, system_time, priority)
        return super(CockroachDatabase, self).atomic(system_time, priority)

    def savepoint(self):
        if self.is_closed(): self.connect()  # Side-effect, set server version.
        if self.server_version < NESTED_TX_MIN_VERSION:
            raise NotImplementedError(TXN_ERR_MSG)
        return super(CockroachDatabase, self).savepoint()

    def retry_transaction(self, max_attempts=None, system_time=None,
                          priority=None):
        def deco(cb):
            @functools.wraps(cb)
            def new_fn():
                return run_transaction(self, cb, max_attempts, system_time,
                                       priority)
            return new_fn
        return deco

    def run_transaction(self, cb, max_attempts=None, system_time=None,
                        priority=None):
        return run_transaction(self, cb, max_attempts, system_time, priority)


class _crdb_atomic(_atomic):
    def __enter__(self):
        if self.db.transaction_depth() > 0:
            if not isinstance(self.db.top_transaction(), _manual):
                raise NotImplementedError(TXN_ERR_MSG)
        return super(_crdb_atomic, self).__enter__()


def run_transaction(db, callback, max_attempts=None, system_time=None,
                    priority=None):
    """
    Run transactional SQL in a transaction with automatic retries.

    User-provided `callback`:
    * Must accept one parameter, the `db` instance representing the connection
      the transaction is running under.
    * Must not attempt to commit, rollback or otherwise manage transactions.
    * May be called more than once.
    * Should ideally only contain SQL operations.

    Additionally, the database must not have any open transaction at the time
    this function is called, as CRDB does not support nested transactions.
    """
    max_attempts = max_attempts or -1
    with db.atomic(system_time=system_time, priority=priority) as txn:
        db.execute_sql('SAVEPOINT cockroach_restart')
        while max_attempts != 0:
            try:
                result = callback(db)
                db.execute_sql('RELEASE SAVEPOINT cockroach_restart')
                return result
            except OperationalError as exc:
                if exc.orig.pgcode == '40001':
                    max_attempts -= 1
                    db.execute_sql('ROLLBACK TO SAVEPOINT cockroach_restart')
                    continue
                raise
    raise ExceededMaxAttempts(None, 'unable to commit transaction')


class PooledCockroachDatabase(_PooledPostgresqlDatabase, CockroachDatabase):
    pass
