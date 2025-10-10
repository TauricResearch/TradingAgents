import threading

from peewee import *
from peewee import Alias
from peewee import CompoundSelectQuery
from peewee import Metadata
from peewee import callable_
from peewee import __deprecated__


_clone_set = lambda s: set(s) if s else set()


def model_to_dict(model, recurse=True, backrefs=False, only=None,
                  exclude=None, seen=None, extra_attrs=None,
                  fields_from_query=None, max_depth=None, manytomany=False):
    """
    Convert a model instance (and any related objects) to a dictionary.

    :param bool recurse: Whether foreign-keys should be recursed.
    :param bool backrefs: Whether lists of related objects should be recursed.
    :param only: A list (or set) of field instances indicating which fields
        should be included.
    :param exclude: A list (or set) of field instances that should be
        excluded from the dictionary.
    :param list extra_attrs: Names of model instance attributes or methods
        that should be included.
    :param SelectQuery fields_from_query: Query that was source of model. Take
        fields explicitly selected by the query and serialize them.
    :param int max_depth: Maximum depth to recurse, value <= 0 means no max.
    :param bool manytomany: Process many-to-many fields.
    """
    max_depth = -1 if max_depth is None else max_depth
    if max_depth == 0:
        recurse = False

    only = _clone_set(only)
    extra_attrs = _clone_set(extra_attrs)
    should_skip = lambda n: (n in exclude) or (only and (n not in only))

    if fields_from_query is not None:
        only.add('__sentinel__')  # Add a placeholder to make non-empty.
        for item in fields_from_query._returning:
            if isinstance(item, Field):
                only.add(item)
            elif isinstance(item, Alias):
                extra_attrs.add(item._alias)

    data = {}
    exclude = _clone_set(exclude)
    seen = _clone_set(seen)
    exclude |= seen
    model_class = type(model)

    if manytomany:
        for name, m2m in model._meta.manytomany.items():
            if should_skip(name):
                continue

            exclude.update((m2m, m2m.rel_model._meta.manytomany[m2m.backref]))
            for fkf in m2m.through_model._meta.refs:
                exclude.add(fkf)

            accum = []
            for rel_obj in getattr(model, name):
                accum.append(model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude,
                    max_depth=max_depth - 1))
            data[name] = accum

    for field in model._meta.sorted_fields:
        if should_skip(field):
            continue

        field_data = model.__data__.get(field.name)
        if isinstance(field, ForeignKeyField) and recurse:
            if field_data is not None:
                seen.add(field)
                rel_obj = getattr(model, field.name)
                field_data = model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude,
                    seen=seen,
                    max_depth=max_depth - 1)
            else:
                field_data = None

        data[field.name] = field_data

    if extra_attrs:
        for attr_name in extra_attrs:
            attr = getattr(model, attr_name)
            if callable_(attr):
                data[attr_name] = attr()
            else:
                data[attr_name] = attr

    if backrefs and recurse:
        for foreign_key, rel_model in model._meta.backrefs.items():
            if foreign_key.backref == '+': continue
            descriptor = getattr(model_class, foreign_key.backref)
            if descriptor in exclude or foreign_key in exclude:
                continue
            if only and (descriptor not in only) and (foreign_key not in only):
                continue

            accum = []
            exclude.add(foreign_key)
            related_query = getattr(model, foreign_key.backref)

            for rel_obj in related_query:
                accum.append(model_to_dict(
                    rel_obj,
                    recurse=recurse,
                    backrefs=backrefs,
                    only=only,
                    exclude=exclude,
                    max_depth=max_depth - 1))

            data[foreign_key.backref] = accum

    return data


def update_model_from_dict(instance, data, ignore_unknown=False):
    meta = instance._meta
    backrefs = dict([(fk.backref, fk) for fk in meta.backrefs])

    for key, value in data.items():
        if key in meta.combined:
            field = meta.combined[key]
            is_backref = False
        elif key in backrefs:
            field = backrefs[key]
            is_backref = True
        elif ignore_unknown:
            setattr(instance, key, value)
            continue
        else:
            raise AttributeError('Unrecognized attribute "%s" for model '
                                 'class %s.' % (key, type(instance)))

        is_foreign_key = isinstance(field, ForeignKeyField)

        if not is_backref and is_foreign_key and isinstance(value, dict):
            try:
                rel_instance = instance.__rel__[field.name]
            except KeyError:
                rel_instance = field.rel_model()
            setattr(
                instance,
                field.name,
                update_model_from_dict(rel_instance, value, ignore_unknown))
        elif is_backref and isinstance(value, (list, tuple)):
            instances = [
                dict_to_model(field.model, row_data, ignore_unknown)
                for row_data in value]
            for rel_instance in instances:
                setattr(rel_instance, field.name, instance)
            setattr(instance, field.backref, instances)
        else:
            setattr(instance, field.name, value)

    return instance


def dict_to_model(model_class, data, ignore_unknown=False):
    return update_model_from_dict(model_class(), data, ignore_unknown)


def insert_where(cls, data, where=None):
    """
    Helper for generating conditional INSERT queries.

    For example, prevent INSERTing a new tweet if the user has tweeted within
    the last hour::

        INSERT INTO "tweet" ("user_id", "content", "timestamp")
        SELECT 234, 'some content', now()
        WHERE NOT EXISTS (
            SELECT 1 FROM "tweet"
            WHERE user_id = 234 AND timestamp > now() - interval '1 hour')

    Using this helper:

        cond = ~fn.EXISTS(Tweet.select().where(
            Tweet.user == user_obj,
            Tweet.timestamp > one_hour_ago))

        iq = insert_where(Tweet, {
            Tweet.user: user_obj,
            Tweet.content: 'some content'}, where=cond)

        res = iq.execute()
    """
    for field, default in cls._meta.defaults.items():
        if field.name in data or field in data: continue
        value = default() if callable_(default) else default
        data[field] = value
    fields, values = zip(*data.items())
    sq = Select(columns=values).where(where)
    return cls.insert_from(sq, fields).as_rowcount()


class ReconnectMixin(object):
    """
    Mixin class that attempts to automatically reconnect to the database under
    certain error conditions.

    For example, MySQL servers will typically close connections that are idle
    for 28800 seconds ("wait_timeout" setting). If your application makes use
    of long-lived connections, you may find your connections are closed after
    a period of no activity. This mixin will attempt to reconnect automatically
    when these errors occur.

    This mixin class probably should not be used with Postgres (unless you
    REALLY know what you are doing) and definitely has no business being used
    with Sqlite. If you wish to use with Postgres, you will need to adapt the
    `reconnect_errors` attribute to something appropriate for Postgres.
    """
    reconnect_errors = (
        # Error class, error message fragment (or empty string for all).
        (OperationalError, '2006'),  # MySQL server has gone away.
        (OperationalError, '2013'),  # Lost connection to MySQL server.
        (OperationalError, '2014'),  # Commands out of sync.
        (OperationalError, '4031'),  # Client interaction timeout.

        # mysql-connector raises a slightly different error when an idle
        # connection is terminated by the server. This is equivalent to 2013.
        (OperationalError, 'MySQL Connection not available.'),

        # Postgres error examples:
        #(OperationalError, 'terminat'),
        #(InterfaceError, 'connection already closed'),
    )

    def __init__(self, *args, **kwargs):
        super(ReconnectMixin, self).__init__(*args, **kwargs)

        # Normalize the reconnect errors to a more efficient data-structure.
        self._reconnect_errors = {}
        for exc_class, err_fragment in self.reconnect_errors:
            self._reconnect_errors.setdefault(exc_class, [])
            self._reconnect_errors[exc_class].append(err_fragment.lower())

    def execute_sql(self, sql, params=None, commit=None):
        if commit is not None:
            __deprecated__('"commit" has been deprecated and is a no-op.')
        return self._reconnect(super(ReconnectMixin, self).execute_sql, sql, params)

    def begin(self):
        return self._reconnect(super(ReconnectMixin, self).begin)

    def _reconnect(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            # If we are in a transaction, do not reconnect silently as
            # any changes could be lost.
            if self.in_transaction():
                raise exc

            exc_class = type(exc)
            if exc_class not in self._reconnect_errors:
                raise exc

            exc_repr = str(exc).lower()
            for err_fragment in self._reconnect_errors[exc_class]:
                if err_fragment in exc_repr:
                    break
            else:
                raise exc

            if not self.is_closed():
                self.close()
                self.connect()

            return func(*args, **kwargs)


def resolve_multimodel_query(query, key='_model_identifier'):
    mapping = {}
    accum = [query]
    while accum:
        curr = accum.pop()
        if isinstance(curr, CompoundSelectQuery):
            accum.extend((curr.lhs, curr.rhs))
            continue

        model_class = curr.model
        name = model_class._meta.table_name
        mapping[name] = model_class
        curr._returning.append(Value(name).alias(key))

    def wrapped_iterator():
        for row in query.dicts().iterator():
            identifier = row.pop(key)
            model = mapping[identifier]
            yield model(**row)

    return wrapped_iterator()


class ThreadSafeDatabaseMetadata(Metadata):
    """
    Metadata class to allow swapping database at run-time in a multi-threaded
    application. To use:

    class Base(Model):
        class Meta:
            model_metadata_class = ThreadSafeDatabaseMetadata
    """
    def __init__(self, *args, **kwargs):
        # The database attribute is stored in a thread-local.
        self._database = None
        self._local = threading.local()
        super(ThreadSafeDatabaseMetadata, self).__init__(*args, **kwargs)

    def _get_db(self):
        return getattr(self._local, 'database', self._database)
    def _set_db(self, db):
        if self._database is None:
            self._database = db
        self._local.database = db
    database = property(_get_db, _set_db)
