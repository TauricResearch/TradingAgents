import operator

from peewee import *
from peewee import sqlite3
from peewee import Expression
from playhouse.fields import PickleField
try:
    from playhouse.sqlite_ext import CSqliteExtDatabase as SqliteExtDatabase
except ImportError:
    from playhouse.sqlite_ext import SqliteExtDatabase


Sentinel = type('Sentinel', (object,), {})


class KeyValue(object):
    """
    Persistent dictionary.

    :param Field key_field: field to use for key. Defaults to CharField.
    :param Field value_field: field to use for value. Defaults to PickleField.
    :param bool ordered: data should be returned in key-sorted order.
    :param Database database: database where key/value data is stored.
    :param str table_name: table name for data.
    """
    def __init__(self, key_field=None, value_field=None, ordered=False,
                 database=None, table_name='keyvalue'):
        if key_field is None:
            key_field = CharField(max_length=255, primary_key=True)
        if not key_field.primary_key:
            raise ValueError('key_field must have primary_key=True.')

        if value_field is None:
            value_field = PickleField()

        self._key_field = key_field
        self._value_field = value_field
        self._ordered = ordered
        self._database = database or SqliteExtDatabase(':memory:')
        self._table_name = table_name
        support_on_conflict = (isinstance(self._database, PostgresqlDatabase) or
                              (isinstance(self._database, SqliteDatabase) and
                               self._database.server_version >= (3, 24)))
        if support_on_conflict:
            self.upsert = self._postgres_upsert
            self.update = self._postgres_update
        else:
            self.upsert = self._upsert
            self.update = self._update

        self.model = self.create_model()
        self.key = self.model.key
        self.value = self.model.value

        # Ensure table exists.
        self.model.create_table()

    def create_model(self):
        class KeyValue(Model):
            key = self._key_field
            value = self._value_field
            class Meta:
                database = self._database
                table_name = self._table_name
        return KeyValue

    def query(self, *select):
        query = self.model.select(*select).tuples()
        if self._ordered:
            query = query.order_by(self.key)
        return query

    def convert_expression(self, expr):
        if not isinstance(expr, Expression):
            return (self.key == expr), True
        return expr, False

    def __contains__(self, key):
        expr, _ = self.convert_expression(key)
        return self.model.select().where(expr).exists()

    def __len__(self):
        return len(self.model)

    def __getitem__(self, expr):
        converted, is_single = self.convert_expression(expr)
        query = self.query(self.value).where(converted)
        item_getter = operator.itemgetter(0)
        result = [item_getter(row) for row in query]
        if len(result) == 0 and is_single:
            raise KeyError(expr)
        elif is_single:
            return result[0]
        return result

    def _upsert(self, key, value):
        (self.model
         .insert(key=key, value=value)
         .on_conflict('replace')
         .execute())

    def _postgres_upsert(self, key, value):
        (self.model
         .insert(key=key, value=value)
         .on_conflict(conflict_target=[self.key],
                      preserve=[self.value])
         .execute())

    def __setitem__(self, expr, value):
        if isinstance(expr, Expression):
            self.model.update(value=value).where(expr).execute()
        else:
            self.upsert(expr, value)

    def __delitem__(self, expr):
        converted, _ = self.convert_expression(expr)
        self.model.delete().where(converted).execute()

    def __iter__(self):
        return iter(self.query().execute())

    def keys(self):
        return map(operator.itemgetter(0), self.query(self.key))

    def values(self):
        return map(operator.itemgetter(0), self.query(self.value))

    def items(self):
        return iter(self.query().execute())

    def _update(self, __data=None, **mapping):
        if __data is not None:
            mapping.update(__data)
        return (self.model
                .insert_many(list(mapping.items()),
                             fields=[self.key, self.value])
                .on_conflict('replace')
                .execute())

    def _postgres_update(self, __data=None, **mapping):
        if __data is not None:
            mapping.update(__data)
        return (self.model
                .insert_many(list(mapping.items()),
                             fields=[self.key, self.value])
                .on_conflict(conflict_target=[self.key],
                             preserve=[self.value])
                .execute())

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    def pop(self, key, default=Sentinel):
        with self._database.atomic():
            try:
                result = self[key]
            except KeyError:
                if default is Sentinel:
                    raise
                return default
            del self[key]

        return result

    def clear(self):
        self.model.delete().execute()
