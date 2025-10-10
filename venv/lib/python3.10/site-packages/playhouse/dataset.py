import csv
import datetime
from decimal import Decimal
import json
import operator
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
import sys
import uuid

from peewee import *
from playhouse.db_url import connect
from playhouse.migrate import migrate
from playhouse.migrate import SchemaMigrator
from playhouse.reflection import Introspector

if sys.version_info[0] == 3:
    basestring = str
    from functools import reduce
    def open_file(f, mode, encoding='utf8'):
        return open(f, mode, encoding=encoding)
else:
    def open_file(f, mode, encoding='utf8'):
        return open(f, mode)


class DataSet(object):
    def __init__(self, url, include_views=False, **kwargs):
        if isinstance(url, Database):
            self._url = None
            self._database = url
            self._database_path = self._database.database
        else:
            self._url = url
            parse_result = urlparse(url)
            self._database_path = parse_result.path[1:]

            # Connect to the database.
            self._database = connect(url)

        # Open a connection if one does not already exist.
        self._database.connect(reuse_if_open=True)

        # Introspect the database and generate models.
        self._introspector = Introspector.from_database(self._database)
        self._include_views = include_views
        self._models = self._introspector.generate_models(
            skip_invalid=True,
            literal_column_names=True,
            include_views=self._include_views,
            **kwargs)
        self._migrator = SchemaMigrator.from_database(self._database)

        class BaseModel(Model):
            class Meta:
                database = self._database
        self._base_model = BaseModel
        self._export_formats = self.get_export_formats()
        self._import_formats = self.get_import_formats()

    def __repr__(self):
        return '<DataSet: %s>' % self._database_path

    def get_export_formats(self):
        return {
            'csv': CSVExporter,
            'json': JSONExporter,
            'tsv': TSVExporter}

    def get_import_formats(self):
        return {
            'csv': CSVImporter,
            'json': JSONImporter,
            'tsv': TSVImporter}

    def __getitem__(self, table):
        if table not in self._models and table in self.tables:
            self.update_cache(table)
        return Table(self, table, self._models.get(table))

    @property
    def tables(self):
        tables = self._database.get_tables()
        if self._include_views:
            tables += self.views
        return tables

    @property
    def views(self):
        return [v.name for v in self._database.get_views()]

    def __contains__(self, table):
        return table in self.tables

    def connect(self, reuse_if_open=False):
        self._database.connect(reuse_if_open=reuse_if_open)

    def close(self):
        self._database.close()

    def update_cache(self, table=None):
        if table:
            dependencies = [table]
            if table in self._models:
                model_class = self._models[table]
                dependencies.extend([
                    related._meta.table_name for _, related, _ in
                    model_class._meta.model_graph()])
            else:
                dependencies.extend(self.get_table_dependencies(table))
        else:
            dependencies = None  # Update all tables.
            self._models = {}
        updated = self._introspector.generate_models(
            skip_invalid=True,
            table_names=dependencies,
            literal_column_names=True,
            include_views=self._include_views)
        self._models.update(updated)

    def get_table_dependencies(self, table):
        stack = [table]
        accum = []
        seen = set()
        while stack:
            table = stack.pop()
            for fk_meta in self._database.get_foreign_keys(table):
                dest = fk_meta.dest_table
                if dest not in seen:
                    stack.append(dest)
                    accum.append(dest)
        return accum

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._database.is_closed():
            self.close()

    def query(self, sql, params=None):
        return self._database.execute_sql(sql, params)

    def transaction(self):
        return self._database.atomic()

    def _check_arguments(self, filename, file_obj, format, format_dict):
        if filename and file_obj:
            raise ValueError('file is over-specified. Please use either '
                             'filename or file_obj, but not both.')
        if not filename and not file_obj:
            raise ValueError('A filename or file-like object must be '
                             'specified.')
        if format not in format_dict:
            valid_formats = ', '.join(sorted(format_dict.keys()))
            raise ValueError('Unsupported format "%s". Use one of %s.' % (
                format, valid_formats))

    def freeze(self, query, format='csv', filename=None, file_obj=None,
               encoding='utf8', **kwargs):
        self._check_arguments(filename, file_obj, format, self._export_formats)
        if filename:
            file_obj = open_file(filename, 'w', encoding)

        exporter = self._export_formats[format](query)
        exporter.export(file_obj, **kwargs)

        if filename:
            file_obj.close()

    def thaw(self, table, format='csv', filename=None, file_obj=None,
             strict=False, encoding='utf8', **kwargs):
        self._check_arguments(filename, file_obj, format, self._export_formats)
        if filename:
            file_obj = open_file(filename, 'r', encoding)

        importer = self._import_formats[format](self[table], strict)
        count = importer.load(file_obj, **kwargs)

        if filename:
            file_obj.close()

        return count


class Table(object):
    def __init__(self, dataset, name, model_class):
        self.dataset = dataset
        self.name = name
        if model_class is None:
            model_class = self._create_model()
            model_class.create_table()
            self.dataset._models[name] = model_class

    @property
    def model_class(self):
        return self.dataset._models[self.name]

    def __repr__(self):
        return '<Table: %s>' % self.name

    def __len__(self):
        return self.find().count()

    def __iter__(self):
        return iter(self.find().iterator())

    def _create_model(self):
        class Meta:
            table_name = self.name
        return type(
            str(self.name),
            (self.dataset._base_model,),
            {'Meta': Meta})

    def create_index(self, columns, unique=False):
        index = ModelIndex(self.model_class, columns, unique=unique)
        self.model_class.add_index(index)
        self.dataset._database.execute(index)

    def _guess_field_type(self, value):
        if isinstance(value, basestring):
            return TextField
        if isinstance(value, (datetime.date, datetime.datetime)):
            return DateTimeField
        elif value is True or value is False:
            return BooleanField
        elif isinstance(value, int):
            return IntegerField
        elif isinstance(value, float):
            return FloatField
        elif isinstance(value, Decimal):
            return DecimalField
        return TextField

    @property
    def columns(self):
        return [f.name for f in self.model_class._meta.sorted_fields]

    def _migrate_new_columns(self, data):
        new_keys = set(data) - set(self.model_class._meta.fields)
        new_keys -= set(self.model_class._meta.columns)
        if new_keys:
            operations = []
            for key in new_keys:
                field_class = self._guess_field_type(data[key])
                field = field_class(null=True)
                operations.append(
                    self.dataset._migrator.add_column(self.name, key, field))
                field.bind(self.model_class, key)

            migrate(*operations)

            self.dataset.update_cache(self.name)

    def __getitem__(self, item):
        try:
            return self.model_class[item]
        except self.model_class.DoesNotExist:
            pass

    def __setitem__(self, item, value):
        if not isinstance(value, dict):
            raise ValueError('Table.__setitem__() value must be a dict')

        pk = self.model_class._meta.primary_key
        value[pk.name] = item

        try:
            with self.dataset.transaction() as txn:
                self.insert(**value)
        except IntegrityError:
            self.dataset.update_cache(self.name)
            self.update(columns=[pk.name], **value)

    def __delitem__(self, item):
        del self.model_class[item]

    def insert(self, **data):
        self._migrate_new_columns(data)
        return self.model_class.insert(**data).execute()

    def _apply_where(self, query, filters, conjunction=None):
        conjunction = conjunction or operator.and_
        if filters:
            expressions = [
                (self.model_class._meta.fields[column] == value)
                for column, value in filters.items()]
            query = query.where(reduce(conjunction, expressions))
        return query

    def update(self, columns=None, conjunction=None, **data):
        self._migrate_new_columns(data)
        filters = {}
        if columns:
            for column in columns:
                filters[column] = data.pop(column)

        return self._apply_where(
            self.model_class.update(**data),
            filters,
            conjunction).execute()

    def _query(self, **query):
        return self._apply_where(self.model_class.select(), query)

    def find(self, **query):
        return self._query(**query).dicts()

    def find_one(self, **query):
        try:
            return self.find(**query).get()
        except self.model_class.DoesNotExist:
            return None

    def all(self):
        return self.find()

    def delete(self, **query):
        return self._apply_where(self.model_class.delete(), query).execute()

    def freeze(self, *args, **kwargs):
        return self.dataset.freeze(self.all(), *args, **kwargs)

    def thaw(self, *args, **kwargs):
        return self.dataset.thaw(self.name, *args, **kwargs)


class Exporter(object):
    def __init__(self, query):
        self.query = query

    def export(self, file_obj):
        raise NotImplementedError


class JSONExporter(Exporter):
    def __init__(self, query, iso8601_datetimes=False):
        super(JSONExporter, self).__init__(query)
        self.iso8601_datetimes = iso8601_datetimes

    def _make_default(self):
        datetime_types = (datetime.datetime, datetime.date, datetime.time)

        if self.iso8601_datetimes:
            def default(o):
                if isinstance(o, datetime_types):
                    return o.isoformat()
                elif isinstance(o, (Decimal, uuid.UUID)):
                    return str(o)
                raise TypeError('Unable to serialize %r as JSON' % o)
        else:
            def default(o):
                if isinstance(o, datetime_types + (Decimal, uuid.UUID)):
                    return str(o)
                raise TypeError('Unable to serialize %r as JSON' % o)
        return default

    def export(self, file_obj, **kwargs):
        json.dump(
            list(self.query),
            file_obj,
            default=self._make_default(),
            **kwargs)


class CSVExporter(Exporter):
    def export(self, file_obj, header=True, **kwargs):
        writer = csv.writer(file_obj, **kwargs)
        tuples = self.query.tuples().execute()
        tuples.initialize()
        if header and getattr(tuples, 'columns', None):
            writer.writerow([column for column in tuples.columns])
        for row in tuples:
            writer.writerow(row)


class TSVExporter(CSVExporter):
    def export(self, file_obj, header=True, **kwargs):
        kwargs.setdefault('delimiter', '\t')
        return super(TSVExporter, self).export(file_obj, header, **kwargs)


class Importer(object):
    def __init__(self, table, strict=False):
        self.table = table
        self.strict = strict

        model = self.table.model_class
        self.columns = model._meta.columns
        self.columns.update(model._meta.fields)

    def load(self, file_obj):
        raise NotImplementedError


class JSONImporter(Importer):
    def load(self, file_obj, **kwargs):
        data = json.load(file_obj, **kwargs)
        count = 0

        for row in data:
            if self.strict:
                obj = {}
                for key in row:
                    field = self.columns.get(key)
                    if field is not None:
                        obj[field.name] = field.python_value(row[key])
            else:
                obj = row

            if obj:
                self.table.insert(**obj)
                count += 1

        return count


class CSVImporter(Importer):
    def load(self, file_obj, header=True, **kwargs):
        count = 0
        reader = csv.reader(file_obj, **kwargs)
        if header:
            try:
                header_keys = next(reader)
            except StopIteration:
                return count

            if self.strict:
                header_fields = []
                for idx, key in enumerate(header_keys):
                    if key in self.columns:
                        header_fields.append((idx, self.columns[key]))
            else:
                header_fields = list(enumerate(header_keys))
        else:
            header_fields = list(enumerate(self.model._meta.sorted_fields))

        if not header_fields:
            return count

        for row in reader:
            obj = {}
            for idx, field in header_fields:
                if self.strict:
                    obj[field.name] = field.python_value(row[idx])
                else:
                    obj[field] = row[idx]

            self.table.insert(**obj)
            count += 1

        return count


class TSVImporter(CSVImporter):
    def load(self, file_obj, header=True, **kwargs):
        kwargs.setdefault('delimiter', '\t')
        return super(TSVImporter, self).load(file_obj, header, **kwargs)
