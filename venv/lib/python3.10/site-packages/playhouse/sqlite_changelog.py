from peewee import *
from playhouse.sqlite_ext import JSONField


class BaseChangeLog(Model):
    timestamp = DateTimeField(constraints=[SQL('DEFAULT CURRENT_TIMESTAMP')])
    action = TextField()
    table = TextField()
    primary_key = IntegerField()
    changes = JSONField()


class ChangeLog(object):
    # Model class that will serve as the base for the changelog. This model
    # will be subclassed and mapped to your application database.
    base_model = BaseChangeLog

    # Template for the triggers that handle updating the changelog table.
    # table: table name
    # action: insert / update / delete
    # new_old: NEW or OLD (OLD is for DELETE)
    # primary_key: table primary key column name
    # column_array: output of build_column_array()
    # change_table: changelog table name
    template = """CREATE TRIGGER IF NOT EXISTS %(table)s_changes_%(action)s
    AFTER %(action)s ON %(table)s
    BEGIN
        INSERT INTO %(change_table)s
            ("action", "table", "primary_key", "changes")
        SELECT
            '%(action)s', '%(table)s', %(new_old)s."%(primary_key)s", "changes"
        FROM (
            SELECT json_group_object(
                col,
                json_array(
                    case when json_valid("oldval") then json("oldval")
                        else "oldval" end,
                    case when json_valid("newval") then json("newval")
                        else "newval" end)
                ) AS "changes"
            FROM (
                SELECT json_extract(value, '$[0]') as "col",
                       json_extract(value, '$[1]') as "oldval",
                       json_extract(value, '$[2]') as "newval"
                FROM json_each(json_array(%(column_array)s))
                WHERE "oldval" IS NOT "newval"
            )
        );
    END;"""

    drop_template = 'DROP TRIGGER IF EXISTS %(table)s_changes_%(action)s'

    _actions = ('INSERT', 'UPDATE', 'DELETE')

    def __init__(self, db, table_name='changelog'):
        self.db = db
        self.table_name = table_name

    def _build_column_array(self, model, use_old, use_new, skip_fields=None):
        # Builds a list of SQL expressions for each field we are tracking. This
        # is used as the data source for change tracking in our trigger.
        col_array = []
        for field in model._meta.sorted_fields:
            if field.primary_key:
                continue

            if skip_fields is not None and field.name in skip_fields:
                continue

            column = field.column_name
            new = 'NULL' if not use_new else 'NEW."%s"' % column
            old = 'NULL' if not use_old else 'OLD."%s"' % column

            if isinstance(field, JSONField):
                # Ensure that values are cast to JSON so that the serialization
                # is preserved when calculating the old / new.
                if use_old: old = 'json(%s)' % old
                if use_new: new = 'json(%s)' % new

            col_array.append("json_array('%s', %s, %s)" % (column, old, new))

        return ', '.join(col_array)

    def trigger_sql(self, model, action, skip_fields=None):
        assert action in self._actions
        use_old = action != 'INSERT'
        use_new = action != 'DELETE'
        cols = self._build_column_array(model, use_old, use_new, skip_fields)
        return self.template % {
            'table': model._meta.table_name,
            'action': action,
            'new_old': 'NEW' if action != 'DELETE' else 'OLD',
            'primary_key': model._meta.primary_key.column_name,
            'column_array': cols,
            'change_table': self.table_name}

    def drop_trigger_sql(self, model, action):
        assert action in self._actions
        return self.drop_template % {
            'table': model._meta.table_name,
            'action': action}

    @property
    def model(self):
        if not hasattr(self, '_changelog_model'):
            class ChangeLog(self.base_model):
                class Meta:
                    database = self.db
                    table_name = self.table_name
            self._changelog_model = ChangeLog

        return self._changelog_model

    def install(self, model, skip_fields=None, drop=True, insert=True,
                update=True, delete=True, create_table=True):
        ChangeLog = self.model
        if create_table:
            ChangeLog.create_table()

        actions = list(zip((insert, update, delete), self._actions))
        if drop:
            for _, action in actions:
                self.db.execute_sql(self.drop_trigger_sql(model, action))

        for enabled, action in actions:
            if enabled:
                sql = self.trigger_sql(model, action, skip_fields)
                self.db.execute_sql(sql)
