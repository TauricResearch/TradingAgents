"""
Collection of postgres-specific extensions, currently including:

* Support for hstore, a key/value type storage
"""
import json
import logging
import uuid

from peewee import *
from peewee import ColumnBase
from peewee import Expression
from peewee import Node
from peewee import NodeList
from peewee import __deprecated__
from peewee import __exception_wrapper__

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass

try:
    from psycopg2.extras import register_hstore
except ImportError:
    def register_hstore(c, globally):
        pass
try:
    from psycopg2.extras import Json
except:
    Json = None


logger = logging.getLogger('peewee')


HCONTAINS_DICT = '@>'
HCONTAINS_KEYS = '?&'
HCONTAINS_KEY = '?'
HCONTAINS_ANY_KEY = '?|'
HKEY = '->'
HUPDATE = '||'
ACONTAINS = '@>'
ACONTAINED_BY = '<@'
ACONTAINS_ANY = '&&'
TS_MATCH = '@@'
JSONB_CONTAINS = '@>'
JSONB_CONTAINED_BY = '<@'
JSONB_CONTAINS_KEY = '?'
JSONB_CONTAINS_ANY_KEY = '?|'
JSONB_CONTAINS_ALL_KEYS = '?&'
JSONB_EXISTS = '?'
JSONB_REMOVE = '-'


class _LookupNode(ColumnBase):
    def __init__(self, node, parts):
        self.node = node
        self.parts = parts
        super(_LookupNode, self).__init__()

    def clone(self):
        return type(self)(self.node, list(self.parts))

    def __hash__(self):
        return hash((self.__class__.__name__, id(self)))


class _JsonLookupBase(_LookupNode):
    def __init__(self, node, parts, as_json=False):
        super(_JsonLookupBase, self).__init__(node, parts)
        self._as_json = as_json

    def clone(self):
        return type(self)(self.node, list(self.parts), self._as_json)

    @Node.copy
    def as_json(self, as_json=True):
        self._as_json = as_json

    def concat(self, rhs):
        if not isinstance(rhs, Node):
            rhs = Json(rhs)
        return Expression(self.as_json(True), OP.CONCAT, rhs)

    def contains(self, other):
        return Expression(self.as_json(True), JSONB_CONTAINS, Json(other))

    def contained_by(self, other):
        return Expression(self.as_json(True), JSONB_CONTAINED_BY, Json(other))

    def contains_any(self, *keys):
        return Expression(
            self.as_json(True),
            JSONB_CONTAINS_ANY_KEY,
            Value(list(keys), unpack=False))

    def contains_all(self, *keys):
        return Expression(
            self.as_json(True),
            JSONB_CONTAINS_ALL_KEYS,
            Value(list(keys), unpack=False))

    def has_key(self, key):
        return Expression(self.as_json(True), JSONB_CONTAINS_KEY, key)


class JsonLookup(_JsonLookupBase):
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


class JsonPath(_JsonLookupBase):
    def __sql__(self, ctx):
        return (ctx
                .sql(self.node)
                .literal('#>' if self._as_json else '#>>')
                .sql(Value('{%s}' % ','.join(map(str, self.parts)))))


class ObjectSlice(_LookupNode):
    @classmethod
    def create(cls, node, value):
        if isinstance(value, slice):
            parts = [value.start or 0, value.stop or 0]
        elif isinstance(value, int):
            parts = [value]
        elif isinstance(value, Node):
            parts = value
        else:
            # Assumes colon-separated integer indexes.
            parts = [int(i) for i in value.split(':')]
        return cls(node, parts)

    def __sql__(self, ctx):
        ctx.sql(self.node)
        if isinstance(self.parts, Node):
            ctx.literal('[').sql(self.parts).literal(']')
        else:
            ctx.literal('[%s]' % ':'.join(str(p + 1) for p in self.parts))
        return ctx

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)


class IndexedFieldMixin(object):
    default_index_type = 'GIN'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('index', True)  # By default, use an index.
        super(IndexedFieldMixin, self).__init__(*args, **kwargs)


class ArrayField(IndexedFieldMixin, Field):
    passthrough = True

    def __init__(self, field_class=IntegerField, field_kwargs=None,
                 dimensions=1, convert_values=False, *args, **kwargs):
        self.__field = field_class(**(field_kwargs or {}))
        self.dimensions = dimensions
        self.convert_values = convert_values
        self.field_type = self.__field.field_type
        super(ArrayField, self).__init__(*args, **kwargs)

    def bind(self, model, name, set_attribute=True):
        ret = super(ArrayField, self).bind(model, name, set_attribute)
        self.__field.bind(model, '__array_%s' % name, False)
        return ret

    def ddl_datatype(self, ctx):
        data_type = self.__field.ddl_datatype(ctx)
        return NodeList((data_type, SQL('[]' * self.dimensions)), glue='')

    def db_value(self, value):
        if value is None or isinstance(value, Node):
            return value
        elif self.convert_values:
            return self._process(self.__field.db_value, value, self.dimensions)
        else:
            return value if isinstance(value, list) else list(value)

    def python_value(self, value):
        if self.convert_values and value is not None:
            conv = self.__field.python_value
            if isinstance(value, list):
                return self._process(conv, value, self.dimensions)
            else:
                return conv(value)
        else:
            return value

    def _process(self, conv, value, dimensions):
        dimensions -= 1
        if dimensions == 0:
            return [conv(v) for v in value]
        else:
            return [self._process(conv, v, dimensions) for v in value]

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)

    def _e(op):
        def inner(self, rhs):
            return Expression(self, op, ArrayValue(self, rhs))
        return inner
    __eq__ = _e(OP.EQ)
    __ne__ = _e(OP.NE)
    __gt__ = _e(OP.GT)
    __ge__ = _e(OP.GTE)
    __lt__ = _e(OP.LT)
    __le__ = _e(OP.LTE)
    __hash__ = Field.__hash__

    def contains(self, *items):
        return Expression(self, ACONTAINS, ArrayValue(self, items))

    def contains_any(self, *items):
        return Expression(self, ACONTAINS_ANY, ArrayValue(self, items))

    def contained_by(self, *items):
        return Expression(self, ACONTAINED_BY, ArrayValue(self, items))


class ArrayValue(Node):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def __sql__(self, ctx):
        return (ctx
                .sql(Value(self.value, unpack=False))
                .literal('::')
                .sql(self.field.ddl_datatype(ctx)))


class DateTimeTZField(DateTimeField):
    field_type = 'TIMESTAMPTZ'


class HStoreField(IndexedFieldMixin, Field):
    field_type = 'HSTORE'
    __hash__ = Field.__hash__

    def __getitem__(self, key):
        return Expression(self, HKEY, Value(key))

    def keys(self):
        return fn.akeys(self)

    def values(self):
        return fn.avals(self)

    def items(self):
        return fn.hstore_to_matrix(self)

    def slice(self, *args):
        return fn.slice(self, Value(list(args), unpack=False))

    def exists(self, key):
        return fn.exist(self, key)

    def defined(self, key):
        return fn.defined(self, key)

    def update(self, **data):
        return Expression(self, HUPDATE, data)

    def delete(self, *keys):
        return fn.delete(self, Value(list(keys), unpack=False))

    def contains(self, value):
        if isinstance(value, dict):
            rhs = Value(value, unpack=False)
            return Expression(self, HCONTAINS_DICT, rhs)
        elif isinstance(value, (list, tuple)):
            rhs = Value(value, unpack=False)
            return Expression(self, HCONTAINS_KEYS, rhs)
        return Expression(self, HCONTAINS_KEY, value)

    def contains_any(self, *keys):
        return Expression(self, HCONTAINS_ANY_KEY, Value(list(keys),
                                                         unpack=False))


class JSONField(Field):
    field_type = 'JSON'
    _json_datatype = 'json'

    def __init__(self, dumps=None, *args, **kwargs):
        self.dumps = dumps or json.dumps
        super(JSONField, self).__init__(*args, **kwargs)

    def db_value(self, value):
        if value is None:
            return value
        if not isinstance(value, Json):
            return Cast(self.dumps(value), self._json_datatype)
        return value

    def __getitem__(self, value):
        return JsonLookup(self, [value])

    def path(self, *keys):
        return JsonPath(self, keys)

    def concat(self, value):
        if not isinstance(value, Node):
            value = Json(value)
        return super(JSONField, self).concat(value)


def cast_jsonb(node):
    return NodeList((node, SQL('::jsonb')), glue='')


class BinaryJSONField(IndexedFieldMixin, JSONField):
    field_type = 'JSONB'
    _json_datatype = 'jsonb'
    __hash__ = Field.__hash__

    def contains(self, other):
        if isinstance(other, JSONField):
            return Expression(self, JSONB_CONTAINS, other)
        return Expression(self, JSONB_CONTAINS, Json(other))

    def contained_by(self, other):
        return Expression(cast_jsonb(self), JSONB_CONTAINED_BY, Json(other))

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
            Value(list(items), unpack=False))


class TSVectorField(IndexedFieldMixin, TextField):
    field_type = 'TSVECTOR'
    __hash__ = Field.__hash__

    def match(self, query, language=None, plain=False):
        params = (language, query) if language is not None else (query,)
        func = fn.plainto_tsquery if plain else fn.to_tsquery
        return Expression(self, TS_MATCH, func(*params))


def Match(field, query, language=None):
    params = (language, query) if language is not None else (query,)
    field_params = (language, field) if language is not None else (field,)
    return Expression(
        fn.to_tsvector(*field_params),
        TS_MATCH,
        fn.to_tsquery(*params))


class IntervalField(Field):
    field_type = 'INTERVAL'


class FetchManyCursor(object):
    __slots__ = ('cursor', 'array_size', 'exhausted', 'iterable')

    def __init__(self, cursor, array_size=None):
        self.cursor = cursor
        self.array_size = array_size or cursor.itersize
        self.exhausted = False
        self.iterable = self.row_gen()

    def __del__(self):
        if self.cursor and not self.cursor.closed:
            try:
                self.cursor.close()
            except Exception:
                pass

    @property
    def description(self):
        return self.cursor.description

    def close(self):
        self.cursor.close()

    def row_gen(self):
        try:
            while True:
                rows = self.cursor.fetchmany(self.array_size)
                if not rows:
                    return
                for row in rows:
                    yield row
        finally:
            self.close()

    def fetchone(self):
        if self.exhausted:
            return
        try:
            return next(self.iterable)
        except StopIteration:
            self.exhausted = True


class ServerSideQuery(Node):
    def __init__(self, query, array_size=None):
        self.query = query
        self.array_size = array_size
        self._cursor_wrapper = None

    def __sql__(self, ctx):
        return self.query.__sql__(ctx)

    def __iter__(self):
        if self._cursor_wrapper is None:
            self._execute(self.query._database)
        return iter(self._cursor_wrapper.iterator())

    def _execute(self, database):
        if self._cursor_wrapper is None:
            cursor = database.execute(self.query, named_cursor=True,
                                      array_size=self.array_size)
            self._cursor_wrapper = self.query._get_cursor_wrapper(cursor)
        return self._cursor_wrapper


def ServerSide(query, database=None, array_size=None):
    if database is None:
        database = query._database
    server_side_query = ServerSideQuery(query, array_size=array_size)
    for row in server_side_query:
        yield row


class _empty_object(object):
    __slots__ = ()
    def __nonzero__(self):
        return False
    __bool__ = __nonzero__


class PostgresqlExtDatabase(PostgresqlDatabase):
    def __init__(self, *args, **kwargs):
        self._register_hstore = kwargs.pop('register_hstore', False)
        self._server_side_cursors = kwargs.pop('server_side_cursors', False)
        super(PostgresqlExtDatabase, self).__init__(*args, **kwargs)

    def _connect(self):
        conn = super(PostgresqlExtDatabase, self)._connect()
        if self._register_hstore:
            register_hstore(conn, globally=True)
        return conn

    def cursor(self, commit=None, named_cursor=None):
        if commit is not None:
            __deprecated__('"commit" has been deprecated and is a no-op.')
        if self.is_closed():
            if self.autoconnect:
                self.connect()
            else:
                raise InterfaceError('Error, database connection not opened.')
        if named_cursor:
            curs = self._state.conn.cursor(name=str(uuid.uuid1()),
                                           withhold=True)
            return curs
        return self._state.conn.cursor()

    def execute(self, query, commit=None, named_cursor=False, array_size=None,
                **context_options):
        if commit is not None:
            __deprecated__('"commit" has been deprecated and is a no-op.')
        ctx = self.get_sql_context(**context_options)
        sql, params = ctx.sql(query).query()
        named_cursor = named_cursor or (self._server_side_cursors and
                                        sql[:6].lower() == 'select')
        cursor = self.execute_sql(sql, params, named_cursor=named_cursor)
        if named_cursor:
            cursor = FetchManyCursor(cursor, array_size)
        return cursor

    def execute_sql(self, sql, params=None, commit=None, named_cursor=None):
        if commit is not None:
            __deprecated__('"commit" has been deprecated and is a no-op.')
        logger.debug((sql, params))
        with __exception_wrapper__:
            cursor = self.cursor(named_cursor=named_cursor)
            cursor.execute(sql, params or ())
        return cursor
