try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict
from collections import namedtuple
from inspect import isclass
import re
import warnings

from peewee import *
from peewee import _StringField
from peewee import _query_val_transform
from peewee import CommaNodeList
from peewee import SCOPE_VALUES
from peewee import make_snake_case
from peewee import text_type
try:
    from pymysql.constants import FIELD_TYPE
except ImportError:
    try:
        from MySQLdb.constants import FIELD_TYPE
    except ImportError:
        FIELD_TYPE = None
try:
    from playhouse import postgres_ext
except ImportError:
    postgres_ext = None
try:
    from playhouse.cockroachdb import CockroachDatabase
except ImportError:
    CockroachDatabase = None

RESERVED_WORDS = set([
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif',
    'else', 'except', 'exec', 'finally', 'for', 'from', 'global', 'if',
    'import', 'in', 'is', 'lambda', 'not', 'or', 'pass', 'print', 'raise',
    'return', 'try', 'while', 'with', 'yield',
])


class UnknownField(object):
    pass


class Column(object):
    """
    Store metadata about a database column.
    """
    primary_key_types = (IntegerField, AutoField)

    def __init__(self, name, field_class, raw_column_type, nullable,
                 primary_key=False, column_name=None, index=False,
                 unique=False, default=None, extra_parameters=None):
        self.name = name
        self.field_class = field_class
        self.raw_column_type = raw_column_type
        self.nullable = nullable
        self.primary_key = primary_key
        self.column_name = column_name
        self.index = index
        self.unique = unique
        self.default = default
        self.extra_parameters = extra_parameters

        # Foreign key metadata.
        self.rel_model = None
        self.related_name = None
        self.to_field = None

    def __repr__(self):
        attrs = [
            'field_class',
            'raw_column_type',
            'nullable',
            'primary_key',
            'column_name']
        keyword_args = ', '.join(
            '%s=%s' % (attr, getattr(self, attr))
            for attr in attrs)
        return 'Column(%s, %s)' % (self.name, keyword_args)

    def get_field_parameters(self):
        params = {}
        if self.extra_parameters is not None:
            params.update(self.extra_parameters)

        # Set up default attributes.
        if self.nullable:
            params['null'] = True
        if self.field_class is ForeignKeyField or self.name != self.column_name:
            params['column_name'] = "'%s'" % self.column_name
        if self.primary_key and not issubclass(self.field_class, AutoField):
            params['primary_key'] = True
        if self.default is not None:
            params['constraints'] = '[SQL("DEFAULT %s")]' % \
                    self.default.replace('"', '\\"')

        # Handle ForeignKeyField-specific attributes.
        if self.is_foreign_key():
            params['model'] = self.rel_model
            if self.to_field:
                params['field'] = "'%s'" % self.to_field
            if self.related_name:
                params['backref'] = "'%s'" % self.related_name

        # Handle indexes on column.
        if not self.is_primary_key():
            if self.unique:
                params['unique'] = 'True'
            elif self.index and not self.is_foreign_key():
                params['index'] = 'True'

        return params

    def is_primary_key(self):
        return self.field_class is AutoField or self.primary_key

    def is_foreign_key(self):
        return self.field_class is ForeignKeyField

    def is_self_referential_fk(self):
        return (self.field_class is ForeignKeyField and
                self.rel_model == "'self'")

    def set_foreign_key(self, foreign_key, model_names, dest=None,
                        related_name=None):
        self.foreign_key = foreign_key
        self.field_class = ForeignKeyField
        if foreign_key.dest_table == foreign_key.table:
            self.rel_model = "'self'"
        else:
            self.rel_model = model_names[foreign_key.dest_table]
        self.to_field = dest and dest.name or None
        self.related_name = related_name or None

    def get_field(self):
        # Generate the field definition for this column.
        field_params = {}
        for key, value in self.get_field_parameters().items():
            if isclass(value) and issubclass(value, Field):
                value = value.__name__
            field_params[key] = value

        param_str = ', '.join('%s=%s' % (k, v)
                              for k, v in sorted(field_params.items()))
        field = '%s = %s(%s)' % (
            self.name,
            self.field_class.__name__,
            param_str)

        if self.field_class is UnknownField:
            field = '%s  # %s' % (field, self.raw_column_type)

        return field


class Metadata(object):
    column_map = {}
    extension_import = ''

    def __init__(self, database):
        self.database = database
        self.requires_extension = False

    def execute(self, sql, *params):
        return self.database.execute_sql(sql, params)

    def get_columns(self, table, schema=None):
        metadata = OrderedDict(
            (metadata.name, metadata)
            for metadata in self.database.get_columns(table, schema))

        # Look up the actual column type for each column.
        column_types, extra_params = self.get_column_types(table, schema)

        # Look up the primary keys.
        pk_names = self.get_primary_keys(table, schema)
        if len(pk_names) == 1:
            pk = pk_names[0]
            if column_types[pk] is IntegerField:
                column_types[pk] = AutoField
            elif column_types[pk] is BigIntegerField:
                column_types[pk] = BigAutoField

        columns = OrderedDict()
        for name, column_data in metadata.items():
            field_class = column_types[name]
            default = self._clean_default(field_class, column_data.default)

            columns[name] = Column(
                name,
                field_class=field_class,
                raw_column_type=column_data.data_type,
                nullable=column_data.null,
                primary_key=column_data.primary_key,
                column_name=name,
                default=default,
                extra_parameters=extra_params.get(name))

        return columns

    def get_column_types(self, table, schema=None):
        raise NotImplementedError

    def _clean_default(self, field_class, default):
        if default is None or field_class in (AutoField, BigAutoField) or \
           default.lower() == 'null':
            return
        if issubclass(field_class, _StringField) and \
           isinstance(default, text_type) and not default.startswith("'"):
            default = "'%s'" % default
        return default or "''"

    def get_foreign_keys(self, table, schema=None):
        return self.database.get_foreign_keys(table, schema)

    def get_primary_keys(self, table, schema=None):
        return self.database.get_primary_keys(table, schema)

    def get_indexes(self, table, schema=None):
        return self.database.get_indexes(table, schema)


class PostgresqlMetadata(Metadata):
    column_map = {
        16: BooleanField,
        17: BlobField,
        20: BigIntegerField,
        21: SmallIntegerField,
        23: IntegerField,
        25: TextField,
        700: FloatField,
        701: DoubleField,
        1042: CharField, # blank-padded CHAR
        1043: CharField,
        1082: DateField,
        1114: DateTimeField,
        1184: DateTimeField,
        1083: TimeField,
        1266: TimeField,
        1700: DecimalField,
        2950: UUIDField, # UUID
    }
    array_types = {
        1000: BooleanField,
        1001: BlobField,
        1005: SmallIntegerField,
        1007: IntegerField,
        1009: TextField,
        1014: CharField,
        1015: CharField,
        1016: BigIntegerField,
        1115: DateTimeField,
        1182: DateField,
        1183: TimeField,
        2951: UUIDField,
    }
    extension_import = 'from playhouse.postgres_ext import *'

    def __init__(self, database):
        super(PostgresqlMetadata, self).__init__(database)

        if postgres_ext is not None:
            # Attempt to add types like HStore and JSON.
            cursor = self.execute('select oid, typname, format_type(oid, NULL)'
                                  ' from pg_type;')
            results = cursor.fetchall()

            for oid, typname, formatted_type in results:
                if typname == 'json':
                    self.column_map[oid] = postgres_ext.JSONField
                elif typname == 'jsonb':
                    self.column_map[oid] = postgres_ext.BinaryJSONField
                elif typname == 'hstore':
                    self.column_map[oid] = postgres_ext.HStoreField
                elif typname == 'tsvector':
                    self.column_map[oid] = postgres_ext.TSVectorField

            for oid in self.array_types:
                self.column_map[oid] = postgres_ext.ArrayField

    def get_column_types(self, table, schema):
        column_types = {}
        extra_params = {}
        extension_types = set((
            postgres_ext.ArrayField,
            postgres_ext.BinaryJSONField,
            postgres_ext.JSONField,
            postgres_ext.TSVectorField,
            postgres_ext.HStoreField)) if postgres_ext is not None else set()

        # Look up the actual column type for each column.
        identifier = '%s."%s"' % (schema, table)
        cursor = self.execute(
            'SELECT attname, atttypid FROM pg_catalog.pg_attribute '
            'WHERE attrelid = %s::regclass AND attnum > %s', identifier, 0)

        # Store column metadata in dictionary keyed by column name.
        for name, oid in cursor.fetchall():
            column_types[name] = self.column_map.get(oid, UnknownField)
            if column_types[name] in extension_types:
                self.requires_extension = True
            if oid in self.array_types:
                extra_params[name] = {'field_class': self.array_types[oid]}

        return column_types, extra_params

    def get_columns(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_columns(table, schema)

    def get_foreign_keys(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_foreign_keys(table, schema)

    def get_primary_keys(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_primary_keys(table, schema)

    def get_indexes(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_indexes(table, schema)


class CockroachDBMetadata(PostgresqlMetadata):
    # CRDB treats INT the same as BIGINT, so we just map bigint type OIDs to
    # regular IntegerField.
    column_map = PostgresqlMetadata.column_map.copy()
    column_map[20] = IntegerField
    array_types = PostgresqlMetadata.array_types.copy()
    array_types[1016] = IntegerField
    extension_import = 'from playhouse.cockroachdb import *'

    def __init__(self, database):
        Metadata.__init__(self, database)
        self.requires_extension = True

        if postgres_ext is not None:
            # Attempt to add JSON types.
            cursor = self.execute('select oid, typname, format_type(oid, NULL)'
                                  ' from pg_type;')
            results = cursor.fetchall()

            for oid, typname, formatted_type in results:
                if typname == 'jsonb':
                    self.column_map[oid] = postgres_ext.BinaryJSONField

            for oid in self.array_types:
                self.column_map[oid] = postgres_ext.ArrayField


class MySQLMetadata(Metadata):
    if FIELD_TYPE is None:
        column_map = {}
    else:
        column_map = {
            FIELD_TYPE.BLOB: TextField,
            FIELD_TYPE.CHAR: CharField,
            FIELD_TYPE.DATE: DateField,
            FIELD_TYPE.DATETIME: DateTimeField,
            FIELD_TYPE.DECIMAL: DecimalField,
            FIELD_TYPE.DOUBLE: FloatField,
            FIELD_TYPE.FLOAT: FloatField,
            FIELD_TYPE.INT24: IntegerField,
            FIELD_TYPE.LONG_BLOB: TextField,
            FIELD_TYPE.LONG: IntegerField,
            FIELD_TYPE.LONGLONG: BigIntegerField,
            FIELD_TYPE.MEDIUM_BLOB: TextField,
            FIELD_TYPE.NEWDECIMAL: DecimalField,
            FIELD_TYPE.SHORT: IntegerField,
            FIELD_TYPE.STRING: CharField,
            FIELD_TYPE.TIMESTAMP: DateTimeField,
            FIELD_TYPE.TIME: TimeField,
            FIELD_TYPE.TINY_BLOB: TextField,
            FIELD_TYPE.TINY: IntegerField,
            FIELD_TYPE.VAR_STRING: CharField,
        }

    def __init__(self, database, **kwargs):
        if 'password' in kwargs:
            kwargs['passwd'] = kwargs.pop('password')
        super(MySQLMetadata, self).__init__(database, **kwargs)

    def get_column_types(self, table, schema=None):
        column_types = {}

        # Look up the actual column type for each column.
        cursor = self.execute('SELECT * FROM `%s` LIMIT 1' % table)

        # Store column metadata in dictionary keyed by column name.
        for column_description in cursor.description:
            name, type_code = column_description[:2]
            column_types[name] = self.column_map.get(type_code, UnknownField)

        return column_types, {}


class SqliteMetadata(Metadata):
    column_map = {
        'bigint': BigIntegerField,
        'blob': BlobField,
        'bool': BooleanField,
        'boolean': BooleanField,
        'char': CharField,
        'date': DateField,
        'datetime': DateTimeField,
        'decimal': DecimalField,
        'float': FloatField,
        'integer': IntegerField,
        'integer unsigned': IntegerField,
        'int': IntegerField,
        'long': BigIntegerField,
        'numeric': DecimalField,
        'real': FloatField,
        'smallinteger': IntegerField,
        'smallint': IntegerField,
        'smallint unsigned': IntegerField,
        'text': TextField,
        'time': TimeField,
        'varchar': CharField,
    }

    begin = r'(?:["\[\(]+)?'
    end = r'(?:["\]\)]+)?'
    re_foreign_key = (
        r'(?:FOREIGN KEY\s*)?'
        r'{begin}(.+?){end}\s+(?:.+\s+)?'
        r'references\s+{begin}(.+?){end}'
        r'\s*\(["|\[]?(.+?)["|\]]?\)').format(begin=begin, end=end)
    re_varchar = r'^\s*(?:var)?char\s*\(\s*(\d+)\s*\)\s*$'

    def _map_col(self, column_type):
        raw_column_type = column_type.lower()
        if raw_column_type in self.column_map:
            field_class = self.column_map[raw_column_type]
        elif re.search(self.re_varchar, raw_column_type):
            field_class = CharField
        else:
            column_type = re.sub(r'\(.+\)', '', raw_column_type)
            if column_type == '':
                field_class = BareField
            else:
                field_class = self.column_map.get(column_type, UnknownField)
        return field_class

    def get_column_types(self, table, schema=None):
        column_types = {}
        columns = self.database.get_columns(table)

        for column in columns:
            column_types[column.name] = self._map_col(column.data_type)

        return column_types, {}


_DatabaseMetadata = namedtuple('_DatabaseMetadata', (
    'columns',
    'primary_keys',
    'foreign_keys',
    'model_names',
    'indexes'))


class DatabaseMetadata(_DatabaseMetadata):
    def multi_column_indexes(self, table):
        accum = []
        for index in self.indexes[table]:
            if len(index.columns) > 1:
                field_names = [self.columns[table][column].name
                               for column in index.columns
                               if column in self.columns[table]]
                accum.append((field_names, index.unique))
        return accum

    def column_indexes(self, table):
        accum = {}
        for index in self.indexes[table]:
            if len(index.columns) == 1:
                accum[index.columns[0]] = index.unique
        return accum


class Introspector(object):
    pk_classes = [AutoField, IntegerField]

    def __init__(self, metadata, schema=None):
        self.metadata = metadata
        self.schema = schema

    def __repr__(self):
        return '<Introspector: %s>' % self.metadata.database

    @classmethod
    def from_database(cls, database, schema=None):
        if isinstance(database, Proxy):
            if database.obj is None:
                raise ValueError('Cannot introspect an uninitialized Proxy.')
            database = database.obj  # Reference the proxied db obj.
        if CockroachDatabase and isinstance(database, CockroachDatabase):
            metadata = CockroachDBMetadata(database)
        elif isinstance(database, PostgresqlDatabase):
            metadata = PostgresqlMetadata(database)
        elif isinstance(database, MySQLDatabase):
            metadata = MySQLMetadata(database)
        elif isinstance(database, SqliteDatabase):
            metadata = SqliteMetadata(database)
        else:
            raise ValueError('Introspection not supported for %r' % database)
        return cls(metadata, schema=schema)

    def get_database_class(self):
        return type(self.metadata.database)

    def get_database_name(self):
        return self.metadata.database.database

    def get_database_kwargs(self):
        return self.metadata.database.connect_params

    def get_additional_imports(self):
        if self.metadata.requires_extension:
            return '\n' + self.metadata.extension_import
        return ''

    def make_model_name(self, table, snake_case=True):
        if snake_case:
            table = make_snake_case(table)
        model = re.sub(r'[^\w]+', '', table)
        model_name = ''.join(sub.title() for sub in model.split('_'))
        if not model_name[0].isalpha():
            model_name = 'T' + model_name
        return model_name

    def make_column_name(self, column, is_foreign_key=False, snake_case=True):
        column = column.strip()
        if snake_case:
            column = make_snake_case(column)
        column = column.lower()
        if is_foreign_key:
            # Strip "_id" from foreign keys, unless the foreign-key happens to
            # be named "_id", in which case the name is retained.
            column = re.sub('_id$', '', column) or column

        # Remove characters that are invalid for Python identifiers.
        column = re.sub(r'[^\w]+', '_', column)
        if column in RESERVED_WORDS:
            column += '_'
        if len(column) and column[0].isdigit():
            column = '_' + column
        return column

    def introspect(self, table_names=None, literal_column_names=False,
                   include_views=False, snake_case=True):
        # Retrieve all the tables in the database.
        tables = self.metadata.database.get_tables(schema=self.schema)
        if include_views:
            views = self.metadata.database.get_views(schema=self.schema)
            tables.extend([view.name for view in views])

        if table_names is not None:
            tables = [table for table in tables if table in table_names]
        table_set = set(tables)

        # Store a mapping of table name -> dictionary of columns.
        columns = {}

        # Store a mapping of table name -> set of primary key columns.
        primary_keys = {}

        # Store a mapping of table -> foreign keys.
        foreign_keys = {}

        # Store a mapping of table name -> model name.
        model_names = {}

        # Store a mapping of table name -> indexes.
        indexes = {}

        # Gather the columns for each table.
        for table in tables:
            table_indexes = self.metadata.get_indexes(table, self.schema)
            table_columns = self.metadata.get_columns(table, self.schema)
            try:
                foreign_keys[table] = self.metadata.get_foreign_keys(
                    table, self.schema)
            except ValueError as exc:
                foreign_keys[table] = []
            else:
                # If there is a possibility we could exclude a dependent table,
                # ensure that we introspect it so FKs will work.
                if table_names is not None:
                    for foreign_key in foreign_keys[table]:
                        if foreign_key.dest_table not in table_set:
                            tables.append(foreign_key.dest_table)
                            table_set.add(foreign_key.dest_table)

            model_names[table] = self.make_model_name(table, snake_case)

            # Collect sets of all the column names as well as all the
            # foreign-key column names.
            lower_col_names = set(column_name.lower()
                                  for column_name in table_columns)
            fks = set(fk_col.column for fk_col in foreign_keys[table])

            for col_name, column in table_columns.items():
                if literal_column_names:
                    new_name = re.sub(r'[^\w]+', '_', col_name)
                else:
                    new_name = self.make_column_name(col_name, col_name in fks,
                                                     snake_case)

                # If we have two columns, "parent" and "parent_id", ensure
                # that when we don't introduce naming conflicts.
                lower_name = col_name.lower()
                if lower_name.endswith('_id') and new_name in lower_col_names:
                    new_name = col_name.lower()

                column.name = new_name

            for index in table_indexes:
                if len(index.columns) == 1:
                    column = index.columns[0]
                    if column in table_columns:
                        table_columns[column].unique = index.unique
                        table_columns[column].index = True

            primary_keys[table] = self.metadata.get_primary_keys(
                table, self.schema)
            columns[table] = table_columns
            indexes[table] = table_indexes

        # Gather all instances where we might have a `related_name` conflict,
        # either due to multiple FKs on a table pointing to the same table,
        # or a related_name that would conflict with an existing field.
        related_names = {}
        sort_fn = lambda foreign_key: foreign_key.column
        for table in tables:
            models_referenced = set()
            for foreign_key in sorted(foreign_keys[table], key=sort_fn):
                try:
                    column = columns[table][foreign_key.column]
                except KeyError:
                    continue

                dest_table = foreign_key.dest_table
                if dest_table in models_referenced:
                    related_names[column] = '%s_%s_set' % (
                        dest_table,
                        column.name)
                else:
                    models_referenced.add(dest_table)

        # On the second pass convert all foreign keys.
        for table in tables:
            for foreign_key in foreign_keys[table]:
                src = columns[foreign_key.table][foreign_key.column]
                try:
                    dest = columns[foreign_key.dest_table][
                        foreign_key.dest_column]
                except KeyError:
                    dest = None

                src.set_foreign_key(
                    foreign_key=foreign_key,
                    model_names=model_names,
                    dest=dest,
                    related_name=related_names.get(src))

        return DatabaseMetadata(
            columns,
            primary_keys,
            foreign_keys,
            model_names,
            indexes)

    def generate_models(self, skip_invalid=False, table_names=None,
                        literal_column_names=False, bare_fields=False,
                        include_views=False):
        database = self.introspect(table_names, literal_column_names,
                                   include_views)
        models = {}

        class BaseModel(Model):
            class Meta:
                database = self.metadata.database
                schema = self.schema

        pending = set()

        def _create_model(table, models):
            pending.add(table)
            for foreign_key in database.foreign_keys[table]:
                dest = foreign_key.dest_table

                if dest not in models and dest != table:
                    if dest in pending:
                        warnings.warn('Possible reference cycle found between '
                                      '%s and %s' % (table, dest))
                    else:
                        _create_model(dest, models)

            primary_keys = []
            columns = database.columns[table]
            for column_name, column in columns.items():
                if column.primary_key:
                    primary_keys.append(column.name)

            multi_column_indexes = database.multi_column_indexes(table)
            column_indexes = database.column_indexes(table)

            class Meta:
                indexes = multi_column_indexes
                table_name = table

            # Fix models with multi-column primary keys.
            composite_key = False
            if len(primary_keys) == 0:
                if 'id' not in columns:
                    Meta.primary_key = False
                else:
                    primary_keys = columns.keys()

            if len(primary_keys) > 1:
                Meta.primary_key = CompositeKey(*[
                    field.name for col, field in columns.items()
                    if col in primary_keys])
                composite_key = True

            attrs = {'Meta': Meta}
            for column_name, column in columns.items():
                FieldClass = column.field_class
                if FieldClass is not ForeignKeyField and bare_fields:
                    FieldClass = BareField
                elif FieldClass is UnknownField:
                    FieldClass = BareField

                params = {
                    'column_name': column_name,
                    'null': column.nullable}
                if column.primary_key and composite_key:
                    if FieldClass is AutoField:
                        FieldClass = IntegerField
                    params['primary_key'] = False
                elif column.primary_key and FieldClass is not AutoField:
                    params['primary_key'] = True
                if column.is_foreign_key():
                    if column.is_self_referential_fk():
                        params['model'] = 'self'
                    else:
                        dest_table = column.foreign_key.dest_table
                        if dest_table in models:
                            params['model'] = models[dest_table]
                        else:
                            FieldClass = DeferredForeignKey
                            params['rel_model_name'] = dest_table
                    if column.to_field:
                        params['field'] = column.to_field

                    # Generate a unique related name.
                    params['backref'] = '%s_%s_rel' % (table, column_name)

                if column.default is not None:
                    constraint = SQL('DEFAULT %s' % column.default)
                    params['constraints'] = [constraint]

                if not column.is_primary_key():
                    if column_name in column_indexes:
                        if column_indexes[column_name]:
                            params['unique'] = True
                        elif not column.is_foreign_key():
                            params['index'] = True
                    else:
                        params['index'] = False

                attrs[column.name] = FieldClass(**params)

            try:
                models[table] = type(str(table), (BaseModel,), attrs)
            except ValueError:
                if not skip_invalid:
                    raise
            finally:
                if table in pending:
                    pending.remove(table)

        # Actually generate Model classes.
        for table, model in sorted(database.model_names.items()):
            if table not in models:
                _create_model(table, models)

        return models


def introspect(database, schema=None):
    introspector = Introspector.from_database(database, schema=schema)
    return introspector.introspect()


def generate_models(database, schema=None, **options):
    introspector = Introspector.from_database(database, schema=schema)
    return introspector.generate_models(**options)


def print_model(model, indexes=True, inline_indexes=False):
    print(model._meta.name)
    for field in model._meta.sorted_fields:
        parts = ['  %s %s' % (field.name, field.field_type)]
        if field.primary_key:
            parts.append(' PK')
        elif inline_indexes:
            if field.unique:
                parts.append(' UNIQUE')
            elif field.index:
                parts.append(' INDEX')
        if isinstance(field, ForeignKeyField):
            parts.append(' FK: %s.%s' % (field.rel_model.__name__,
                                         field.rel_field.name))
        print(''.join(parts))

    if indexes:
        index_list = model._meta.fields_to_index()
        if not index_list:
            return

        print('\nindex(es)')
        for index in index_list:
            parts = ['  ']
            ctx = model._meta.database.get_sql_context()
            with ctx.scope_values(param='%s', quote='""'):
                ctx.sql(CommaNodeList(index._expressions))
                if index._where:
                    ctx.literal(' WHERE ')
                    ctx.sql(index._where)
                sql, params = ctx.query()

            clean = sql % tuple(map(_query_val_transform, params))
            parts.append(clean.replace('"', ''))

            if index._unique:
                parts.append(' UNIQUE')
            print(''.join(parts))


def get_table_sql(model):
    sql, params = model._schema._create_table().query()
    if model._meta.database.param != '%s':
        sql = sql.replace(model._meta.database.param, '%s')

    # Format and indent the table declaration, simplest possible approach.
    match_obj = re.match(r'^(.+?\()(.+)(\).*)', sql)
    create, columns, extra = match_obj.groups()
    indented = ',\n'.join('  %s' % column for column in columns.split(', '))

    clean = '\n'.join((create, indented, extra)).strip()
    return clean % tuple(map(_query_val_transform, params))

def print_table_sql(model):
    print(get_table_sql(model))
