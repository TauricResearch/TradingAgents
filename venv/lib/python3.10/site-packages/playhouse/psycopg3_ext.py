import json

from peewee import *
from peewee import Expression
from peewee import Node
from peewee import NodeList
from playhouse.postgres_ext import ArrayField
from playhouse.postgres_ext import DateTimeTZField
from playhouse.postgres_ext import IndexedFieldMixin
from playhouse.postgres_ext import IntervalField
from playhouse.postgres_ext import Match
from playhouse.postgres_ext import TSVectorField
# Helpers needed for psycopg3-specific overrides.
from playhouse.postgres_ext import _JsonLookupBase

try:
    import psycopg
    from psycopg.types.json import Jsonb
    from psycopg.pq import TransactionStatus
except ImportError:
    psycopg = Jsonb = None


JSONB_CONTAINS = '@>'
JSONB_CONTAINED_BY = '<@'
JSONB_CONTAINS_KEY = '?'
JSONB_CONTAINS_ANY_KEY = '?|'
JSONB_CONTAINS_ALL_KEYS = '?&'
JSONB_EXISTS = '?'
JSONB_REMOVE = '-'


class _Psycopg3JsonLookupBase(_JsonLookupBase):
    def concat(self, rhs):
        if not isinstance(rhs, Node):
            rhs = Jsonb(rhs)  # Note: uses psycopg3's Jsonb.
        return Expression(self.as_json(True), OP.CONCAT, rhs)

    def contains(self, other):
        return Expression(self.as_json(True), JSONB_CONTAINS, Jsonb(other))


class JsonLookup(_Psycopg3JsonLookupBase):
    def __getitem__(self, value):
        return JsonLookup(self.node, self.parts + [value], self._as_json)

    def __sql__(self, ctx):
        ctx.sql(self.node)
        for part in self.parts[:-1]:
            ctx.literal('->').sql(part)
        if self.parts:
            (ctx
             .literal('->' if self._as_json else '->>')
             .sql(self.parts[-1]))

        return ctx


class JsonPath(_Psycopg3JsonLookupBase):
    def __sql__(self, ctx):
        return (ctx
                .sql(self.node)
                .literal('#>' if self._as_json else '#>>')
                .sql(Value('{%s}' % ','.join(map(str, self.parts)))))


def cast_jsonb(node):
    return NodeList((node, SQL('::jsonb')), glue='')


class BinaryJSONField(IndexedFieldMixin, Field):
    field_type = 'JSONB'
    _json_datatype = 'jsonb'
    __hash__ = Field.__hash__

    def __init__(self, dumps=None, *args, **kwargs):
        self.dumps = dumps or json.dumps
        super(BinaryJSONField, self).__init__(*args, **kwargs)

    def db_value(self, value):
        if value is None:
            return value
        if not isinstance(value, Jsonb):
            return Cast(self.dumps(value), self._json_datatype)
        return value

    def __getitem__(self, value):
        return JsonLookup(self, [value])

    def path(self, *keys):
        return JsonPath(self, keys)

    def concat(self, value):
        if not isinstance(value, Node):
            value = Jsonb(value)
        return super(BinaryJSONField, self).concat(value)

    def contains(self, other):
        if isinstance(other, BinaryJSONField):
            return Expression(self, JSONB_CONTAINS, other)
        return Expression(cast_jsonb(self), JSONB_CONTAINS, Jsonb(other))

    def contained_by(self, other):
        return Expression(cast_jsonb(self), JSONB_CONTAINED_BY, Jsonb(other))

    def contains_any(self, *items):
        return Expression(
            cast_jsonb(self),
            JSONB_CONTAINS_ANY_KEY,
            Value(list(items), unpack=False))

    def contains_all(self, *items):
        return Expression(
            cast_jsonb(self),
            JSONB_CONTAINS_ALL_KEYS,
            Value(list(items), unpack=False))

    def has_key(self, key):
        return Expression(cast_jsonb(self), JSONB_CONTAINS_KEY, key)

    def remove(self, *items):
        return Expression(
            cast_jsonb(self),
            JSONB_REMOVE,
            # Hack: psycopg3 parameterizes this as an array, e.g. '{k1,k2}',
            # but that doesn't seem to be working, so we explicitly cast.
            # Perhaps postgres is interpreting it as a string. Using the more
            # explicit ARRAY['k1','k2'] also works just fine -- but we'll make
            # the cast explicit to get it working.
            Cast(Value(list(items), unpack=False), 'text[]'))


class Psycopg3Database(PostgresqlDatabase):
    def _connect(self):
        if psycopg is None:
            raise ImproperlyConfigured('psycopg3 is not installed!')
        if self.database.startswith('postgresql://'):
            conn = psycopg.connect(self.database, **self.connect_params)
        else:
            conn = psycopg.connect(dbname=self.database, **self.connect_params)
        if self._isolation_level is not None:
            conn.isolation_level = self._isolation_level
        conn.autocommit = True
        return conn

    def get_binary_type(self):
        return psycopg.Binary

    def _set_server_version(self, conn):
        self.server_version = conn.pgconn.server_version
        if self.server_version >= 90600:
            self.safe_create_index = True

    def is_connection_usable(self):
        if self._state.closed:
            return False

        # Returns True if we are idle, running a command, or in an active
        # connection. If the connection is in an error state or the connection
        # is otherwise unusable, return False.
        conn = self._state.conn
        return conn.pgconn.transaction_status < TransactionStatus.INERROR

    def extract_date(self, date_part, date_field):
        return fn.EXTRACT(NodeList((SQL(date_part), SQL('FROM'), date_field)))
