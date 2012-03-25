import re
from django.conf import settings
from django.db import connection, connections
from django.db.models import Model
from django.db.models.query import RawQuerySet
from django.utils.importlib import import_module

SMARTSQL_ALIAS = getattr(settings, 'SQLBUILDER_SMARTSQL_ALIAS', 'ss')
SMARTSQL_USE = getattr(settings, 'SQLBUILDER_SMARTSQL_USE', True)

SQLOBJECT_ALIAS = getattr(settings, 'SQLBUILDER_SQLOBJECT_ALIAS', 'so')
SQLOBJECT_USE = getattr(settings, 'SQLBUILDER_SQLOBJECT_USE', True)

SQLALCHEMY_ALIAS = getattr(settings, 'SQLBUILDER_SQLALCHEMY_ALIAS', 'sa')
SQLALCHEMY_USE = getattr(settings, 'SQLBUILDER_SQLALCHEMY_USE', True)


class classproperty(object):
    """Class property decorator"""
    def __init__(self, getter):
        self.getter = getter

    def __get__(self, instance, owner):
        return self.getter(owner)


class AbstractFacade(object):
    """Abstract facade for Django integration"""
    _model = None
    _table = None
    _query_set = None

    def __init__(self, model):
        """Constructor"""
        raise NotImplementedError

    @property
    def model(self):
        """Returns table instance."""
        return self._model

    @property
    def table(self):
        """Returns table instance."""
        return self._table

    def get_fields(self, prefix=None):
        """Returns fileld list."""
        raise NotImplementedError

    def set_query_set(self, query_set):
        """Sets query set."""
        self._query_set = query_set
        return self

    def get_query_set(self):
        """Returns query set."""
        return self._query_set

    @property
    def qs(self):
        """Sets query set."""
        return self.get_query_set()

    # Aliases
    @property
    def t(self):
        """Returns table instance."""
        return self._table


if SMARTSQL_USE:
    import smartsql

    class DjQS(smartsql.QS):
        """Query Set adapted for Django."""
        def execute(self):
            """Implementation of query execution"""
            return self.django.model.objects.raw(
                smartsql.sqlrepr(self), smartsql.sqlparams(self)
            )

    class SmartSQLFacade(AbstractFacade):
        """Abstract facade for Django integration"""

        def __init__(self, model):
            """Constructor"""
            self._model = model
            self._table = smartsql.Table(self._model._meta.db_table)
            self._table.django = self
            self._query_set = DjQS(self.table).fields(self.get_fields())
            self._query_set.django = self

        def get_fields(self, prefix=None):
            """Returns field list."""
            if prefix is None:
                prefix = self._table
            result = []
            for f in self._model._meta.fields:
                if f.column:
                    result.append(smartsql.Field(f.column, prefix))
            return result

    @classproperty
    def ss(cls):
        if getattr(cls, '_{0}'.format(SMARTSQL_ALIAS), None) is None:
            setattr(cls, '_{0}'.format(SMARTSQL_ALIAS), SmartSQLFacade(cls))
        return getattr(cls, '_{0}'.format(SMARTSQL_ALIAS))

    setattr(Model, SMARTSQL_ALIAS, ss)

if SQLOBJECT_USE:
    import sqlobject

    SQLOBJECT_DIALECTS = {
        'sqlite3': 'sqlite',
        'mysql': 'mysql',
        'postgresql': 'postgres',
        'postgresql_psycopg2': 'postgres',
        'postgis': 'postgres',
        'oracle': 'oracle',
    }

    def get_so_dialect():
        """Returns instance of Dialect"""
        engine = connection.settings_dict['ENGINE'].rsplit('.')[-1]
        return SQLOBJECT_DIALECTS[engine]

    SQLOBJECT_DIALECT = get_so_dialect()
    settings.SQLBUILDER_SQLOBJECT_DIALECT = SQLOBJECT_DIALECT

    class SQLObjectFacade(AbstractFacade):
        """Abstract facade for Django integration"""

        def __init__(self, model):
            """Constructor"""
            self._model = model
            self._table = sqlobject.Table(self._model._meta.db_table)
            self._query_set = sqlobject.Select(
                items=self.get_fields(),
                staticTables=[self.table, ]
            )

        def get_fields(self, prefix=None):
            """Returns field list."""
            if prefix is None:
                prefix = self._table
            result = []
            for f in self._model._meta.fields:
                if f.column:
                    result.append(getattr(prefix, f.column))
            return result

    @classproperty
    def so(cls):
        if getattr(cls, '_{0}'.format(SQLOBJECT_ALIAS), None) is None:
            setattr(cls, '_{0}'.format(SQLOBJECT_ALIAS), SQLObjectFacade(cls))
        return getattr(cls, '_{0}'.format(SQLOBJECT_ALIAS))

    setattr(Model, SQLOBJECT_ALIAS, so)

try:
    if not SQLALCHEMY_USE:
        raise ImportError
    import sqlalchemy.sql

    SQLALCHEMY_DIALECTS = {
        'sqlite3': 'sqlalchemy.dialects.sqlite.pysqlite.SQLiteDialect_pysqlite',
        'mysql': 'sqlalchemy.dialects.mysql.mysqldb.MySQLDialect_mysqldb',
        'postgresql': 'sqlalchemy.dialects.postgresql.pypostgresql.PGDialect_pypostgresql',
        'postgresql_psycopg2': 'sqlalchemy.dialects.postgresql.psycopg2.PGDialect_psycopg2',
        'postgis': 'sqlalchemy.dialects.postgresql.psycopg2.PGDialect_psycopg2',
        'oracle': 'sqlalchemy.dialects.oracle.cx_oracle.OracleDialect_cx_oracle',
    }

    def get_sa_dialect():
        """Returns instance of Dialect"""
        engine = connection.settings_dict['ENGINE'].rsplit('.')[-1]
        module_name, cls_name = SQLALCHEMY_DIALECTS[engine].rsplit('.', 1)
        module = import_module(module_name)
        cls = getattr(module, cls_name)
        return cls()

    SQLALCHEMY_DIALECT = get_sa_dialect()
    settings.SQLBUILDER_SQLALCHEMY_DIALECT = SQLALCHEMY_DIALECT

    class VirtualColumns(object):
        """Virtual column class."""
        _table = None
        _columns = None

        def __init__(self, table=None):
            """Constructor"""
            self._table = table
            self._columns = {}

        def __getattr__(self, name):
            """Creates column on fly."""
            if name not in self._columns:
                c = sqlalchemy.sql.column(name)
                c.table = self._table
                self._columns[name] = c
            return self._columns[name]

    @property
    def vc(self):
        """Returns VirtualColumns instance"""
        if getattr(self, '_vc', None) is None:
            self._vc = VirtualColumns(self)
        return self._vc

    sqlalchemy.sql.TableClause.vc = vc

    class SQLAlchemyFacade(AbstractFacade):
        """Abstract facade for Django integration"""

        dialect = SQLALCHEMY_DIALECT

        def __init__(self, model):
            """Constructor"""
            self._model = model
            self._table = sqlalchemy.sql.table(self._model._meta.db_table)
            self._query_set = sqlalchemy.sql.select(self.get_fields())\
                .select_from(self.table)

        def get_fields(self, prefix=None):
            """Returns field list."""
            if prefix is None:
                prefix = self._table
            result = []
            for f in self._model._meta.fields:
                if f.column:
                    result.append(getattr(self._table.vc, f.column))
            return result

    @classproperty
    def sa(cls):
        if getattr(cls, '_{0}'.format(SQLALCHEMY_ALIAS), None) is None:
            setattr(cls, '_{0}'.format(SQLALCHEMY_ALIAS), SQLAlchemyFacade(cls))
        return getattr(cls, '_{0}'.format(SQLALCHEMY_ALIAS))

    setattr(Model, SQLALCHEMY_ALIAS, sa)

except ImportError:
    pass

# Fixing django.db.models.query.RawQuerySet


def count(self):
    """Returns count of rows"""
    sql = self.query.sql
    make_cache_if_need(self)
    if getattr(self, '_result_cache', None) is not None:
        return len(self._result_cache)
    if not re.compile(r"""^((?:"(?:[^"\\]|\\"|\\\\)*"|'(?:[^'\\]|\\'|\\\\)*'|/\*.*?\*/|--[^\n]*\n|[^"'\\])+)(?:LIMIT|OFFSET).+$""", re.I|re.U|re.S).match(sql):
        sql = re.compile(r"""^((?:"(?:[^"\\]|\\"|\\\\)*"|'(?:[^'\\]|\\'|\\\\)*'|/\*.*?\*/|--[^\n]*\n|[^"'\\])+)ORDER BY[^%]+$""", re.I|re.U|re.S).sub(r'\1', sql)
    sql = u"SELECT COUNT(1) as c FROM ({0}) as t".format(sql)
    cursor = connections[self.query.using].cursor()
    cursor.execute(sql, self.params)
    row = cursor.fetchone()
    return row[0]


def __getitem__(self, k):
    """Returns sliced instance of self.__class__"""
    sql = self.query.sql
    offset = 0
    limit = None
    if isinstance(k, slice):
        if k.start is not None:
            offset = int(k.start)
        if k.stop is not None:
            end = int(k.stop)
            limit = end - offset
    else:
        return list(self)[k]
    if limit:
        sql = u"{0} LIMIT {1:d}".format(sql, limit)
    if offset:
        sql = u"{0} OFFSET {1:d}".format(sql, offset)
    new_cls = self.__class__(sql, model=self.model, query=None,
                             params=self.params, translations=self.translations,
                             using=self.db)
    new_cls.sliced = True
    new_cls.limit = limit
    return new_cls

__iter_origin__ = None


def make_cache_if_need(self):
    """Cache for small selections"""
    if getattr(self, 'sliced', False) and getattr(self, 'limit', 0) < 300:
        if getattr(self, '_result_cache', None) is None:
            self._result_cache = [v for v in __iter_origin__(self)]


def __iter__(self):
    """Cache for small selections"""
    make_cache_if_need(self)
    if getattr(self, '_result_cache', None) is not None:
        for v in self._result_cache:
            yield v
    else:
        for v in __iter_origin__(self):
            yield v


def patch_raw_query_set():
    global __iter_origin__
    if RawQuerySet.__getitem__ is not __getitem__:
        RawQuerySet.count = RawQuerySet.__len__ = count
        RawQuerySet.__getitem__ = __getitem__
        __iter_origin__ = RawQuerySet.__iter__
        RawQuerySet.__iter__ = __iter__

patch_raw_query_set()
