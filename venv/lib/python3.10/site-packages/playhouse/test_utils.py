from functools import wraps
import logging


logger = logging.getLogger('peewee')


class _QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)

    def emit(self, record):
        # Counts all entries logged to the "peewee" logger by execute_sql().
        if record.name == 'peewee':
            self.queries.append(record)


class count_queries(object):
    def __init__(self, only_select=False):
        self.only_select = only_select
        self.count = 0

    def get_queries(self):
        return self._handler.queries

    def __enter__(self):
        self._handler = _QueryLogHandler()
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self._handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.removeHandler(self._handler)
        if self.only_select:
            self.count = len([q for q in self._handler.queries
                              if q.msg[0].startswith('SELECT ')])
        else:
            self.count = len(self._handler.queries)


class assert_query_count(count_queries):
    def __init__(self, expected, only_select=False):
        super(assert_query_count, self).__init__(only_select=only_select)
        self.expected = expected

    def __call__(self, f):
        @wraps(f)
        def decorated(*args, **kwds):
            with self:
                ret = f(*args, **kwds)

            self._assert_count()
            return ret

        return decorated

    def _assert_count(self):
        error_msg = '%s != %s' % (self.count, self.expected)
        assert self.count == self.expected, error_msg

    def __exit__(self, exc_type, exc_val, exc_tb):
        super(assert_query_count, self).__exit__(exc_type, exc_val, exc_tb)
        self._assert_count()
