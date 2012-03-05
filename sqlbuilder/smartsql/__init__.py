# -*- coding: gb2312 -*-
# $Id: sql.py 47 2010-06-25 09:12:29Z scutwukai $
# Forked from http://code.google.com/p/py-smart-sql-constructor/

import copy


def sqlrepr(obj, dialect=None, *args, **kwargs):
    """Renders query set"""
    try:
        return obj.__sqlrepr__(*args, **kwargs)
    except:
        return obj.__sqlrepr__()


def sqlparams(obj):
    """Renders query set"""
    return obj.__params__()


class Error(Exception):
    pass


class MetaTable(type):
    def __getattr__(cls, key):
        if key[0] == '_':
            raise AttributeError
        pieces = key.split("__", 1)
        name = pieces[0]
        alias = None

        if len(pieces) > 1:
            alias = pieces[1]

        return cls(name, alias)


class Table(object):
    __metaclass__ = MetaTable

    def __init__(self, name, alias=None):
        self._name = name
        self._alias = alias
        self._join = None
        self._on = None

    def __mul__(self, obj):
        return TableSet(self).__mul__(obj)

    def __add__(self, obj):
        return TableSet(self).__add__(obj)

    def __getattr__(self, name):
        if self._alias:
            a = self._alias
        else:
            a = self._name
        return getattr(Field, u"{0}__{1}".format(a, name))

    def __sqlrepr__(self):
        sql = [self._name]

        if self._join:
            sql.insert(0, self._join)
        if self._alias:
            sql.extend(["AS", self._alias])
        if self._on:
            sql.extend(["ON", "(%s)" % (sqlrepr(self._on), )])

        return " ".join(sql)

    def __params__(self):
        return sqlparams(self._on) if self._on else []


class TableSet(object):
    def __init__(self, join_obj):
        self._join_list = [join_obj]

        self._sub = False
        self._join = None
        self._on = None

    def __mul__(self, obj):
        return self._add_join("JOIN", obj)

    def __add__(self, obj):
        return self._add_join("LEFT JOIN", obj)

    def __sqlrepr__(self):
        sql = [" ".join([sqlrepr(k) for k in self._join_list])]

        if self._join:
            sql[0] = "(%s)" % (sql[0], )
            sql.insert(0, self._join)
        if self._on:
            sql.extend(["ON", "(%s)" % (sqlrepr(self._on), )])

        return " ".join(sql)

    def __params__(self):
        params = []
        for sql_obj in self._join_list:
            params.extend(sqlparams(sql_obj))
        return params

    #public func
    def on(self, c):
        self._join_list[-1]._on = c
        return self

    #private func
    def _add_join(self, join_type, obj):
        obj._join = join_type
        self._join_list.append(obj)
        return self

##################################################################


class MetaField(type):
    def __getattr__(cls, key):
        if key[0] == '_':
            raise AttributeError
        pieces = key.split("__", 2)
        name = pieces[0]
        prefix = None
        alias = None

        if len(pieces) > 1:
            prefix = pieces[0]
            name = pieces[1]
        if len(pieces) > 2:
            alias = pieces[2]

        return cls(name, prefix, alias)


class Field(object):
    __metaclass__ = MetaField

    def __init__(self, name, prefix=None, alias=None):
        self._name = name
        self._prefix = prefix
        self._alias = alias

    def __eq__(self, f):
        if f is None:
            return Condition("%s IS NULL" % (sqlrepr(self), ))

        if isinstance(f, Field):
            return Condition("%s = %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s = %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        if isinstance(f, list) or isinstance(f, tuple):
            if len(f) < 1:
                raise ("Empty list is not allowed")

            sql = ", ".join(["%s" for i in xrange(len(f))])
            return Condition("%s IN (%s)" % (sqlrepr(self), sql), list(f))

        return Condition(sqlrepr(self) + " = %s", [f])

    def __ne__(self, f):
        if f is None:
            return Condition("%s IS NOT NULL" % (sqlrepr(self), ))

        if isinstance(f, Field):
            return Condition("%s <> %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s <> %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        if isinstance(f, list) or isinstance(f, tuple):
            if len(f) < 1:
                raise Error("Empty list is not allowed")

            sql = ", ".join(["%s" for i in xrange(len(f))])
            return Condition("%s NOT IN (%s)" % (sqlrepr(self), sql), list(f))

        return Condition(sqlrepr(self) + " <> %s", [f])

    def __gt__(self, f):
        if isinstance(f, Field):
            return Condition("%s > %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s > %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        return Condition(sqlrepr(self) + " > %s", [f])

    def __lt__(self, f):
        if isinstance(f, Field):
            return Condition("%s < %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s < %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        return Condition(sqlrepr(self) + " < %s", [f])

    def __ge__(self, f):
        if isinstance(f, Field):
            return Condition("%s >= %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s >= %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        return Condition(sqlrepr(self) + " >= %s", [f])

    def __le__(self, f):
        if isinstance(f, Field):
            return Condition("%s <= %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s <= %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        return Condition(sqlrepr(self) + " <= %s", [f])

    def __mod__(self, f):
        if isinstance(f, Field):
            return Condition("%s LIKE %s" % (sqlrepr(self), sqlrepr(f)))

        if isinstance(f, Expr):
            return Condition("%s LIKE %s" % (sqlrepr(self), sqlrepr(f)), sqlparams(f))

        return Condition(sqlrepr(self) + " LIKE %s", [f])

    def __sqlrepr__(self, define=False):
        sql = ".".join((self._prefix, self._name)) if self._prefix else self._name
        if define:
            return self._alias or sql
        if self._alias:
            sql = "{0} AS {1}".format(sql, self._alias)
        return sql


class Condition(object):
    def __init__(self, sql, params=None):
        self._sql = sql
        self._params = params if params else []

    def __and__(self, c):
        if isinstance(c, str):
            return self & Condition(c)

        if isinstance(c, Condition):
            return ConditionSet(self) & c

        if isinstance(c, ConditionSet):
            return c.__rand__(self)

        raise TypeError("Can't do operation with %s" % str(type(c)))

    def __or__(self, c):
        if isinstance(c, str):
            return self | Condition(c)

        if isinstance(c, Condition):
            return ConditionSet(self) | c

        if isinstance(c, ConditionSet):
            return c.__ror__(self)

        raise TypeError("Can't do operation with %s" % str(type(c)))

    def __sqlrepr__(self):
        return self._sql

    def __params__(self):
        return self._params


class ConditionSet(object):
    OP_AND = 0
    OP_OR = 1

    def __init__(self, c=None):
        self._empty = True
        self._last_op = None
        if c:
            self._init(c)

    def _init(self, c):
        self._sql = sqlrepr(c)
        self._params = sqlparams(c)
        if isinstance(c, ConditionSet):
            self._last_op = c._last_op
        self._empty = False
        return self

    def _pre_extend(self, array1, array2):
        for item in array2:
            array1.insert(0, item)

    ##################################
    def __rand__(self, c):
        return copy.deepcopy(self)._rand(c)

    def _rand(self, c):
        if isinstance(c, str):
            return self._rand(Condition(c))

        if not isinstance(c, Condition):
            raise TypeError("Can't do operation with %s" % str(type(c)))

        if self._empty:
            return self._init(c)

        if self._last_op is not None and self._last_op == ConditionSet.OP_OR:
            self._sql = "(%s)" % (self._sql, )

        self._sql = "%s AND %s" % (sqlrepr(c), self._sql)
        self._pre_extend(self._params, sqlparams(c))
        self._last_op = ConditionSet.OP_AND
        return self

    ###################################
    def __and__(self, c):
        return copy.deepcopy(self)._and(c)

    def _and(self, c):
        if isinstance(c, str):
            return self._and(Condition(c))

        if not isinstance(c, Condition) and not isinstance(c, ConditionSet):
            raise TypeError("Can't do operation with %s" % str(type(c)))

        if self._empty:
            return self._init(c)

        if self._last_op is not None and self._last_op == ConditionSet.OP_OR:
            self._sql = "(%s)" % (self._sql, )

        if isinstance(c, ConditionSet) and c._last_op == ConditionSet.OP_OR:
            self._sql = "%s AND (%s)" % (self._sql, sqlrepr(c))
        else:
            self._sql = "%s AND %s" % (self._sql, sqlrepr(c))

        self._params.extend(sqlparams(c))
        self._last_op = ConditionSet.OP_AND
        return self

    ###################################
    def __ror__(self, c):
        return copy.deepcopy(self)._ror(c)

    def _ror(self, c):
        if isinstance(c, str):
            return self._ror(Condition(c))

        if not isinstance(c, Condition):
            raise TypeError("Can't do operation with %s" % str(type(c)))

        if self._empty:
            return self._init(c)

        self._sql = "%s OR %s" % (sqlrepr(c), self._sql)
        self._pre_extend(self._params, sqlparams(c))
        self._last_op = ConditionSet.OP_OR
        return self

    ###################################
    def __or__(self, c):
        return copy.deepcopy(self)._or(c)

    def _or(self, c):
        if isinstance(c, str):
            return self._or(Condition(c))

        if not isinstance(c, Condition) and not isinstance(c, ConditionSet):
            raise TypeError("Can't do operation with %s" % str(type(c)))

        if self._empty:
            return self._init(c)

        self._sql = "%s OR %s" % (self._sql, sqlrepr(c))
        self._params.extend(sqlparams(c))
        self._last_op = ConditionSet.OP_OR
        return self

    def __sqlrepr__(self):
        return "" if self._empty else self._sql

    def __params__(self):
        return [] if self._empty else self._params

################################################


class Expr(object):
    def __init__(self, sql, *params):
        self._sql = sql
        self._params = params

    def __sqlrepr__(self):
        return self._sql

    def __params__(self):
        return self._params


################################################


def opt_checker(k_list):
    def new_deco(func):
        def new_func(self, *args, **opt):
            for k, v in opt.items():
                if k not in k_list:
                    raise TypeError("Not implemented option: %s" % (k, ))
            return func(self, *args, **opt)

        new_func.__doc__ = func.__doc__
        return new_func
    return new_deco


def _gen_order_by_list(f_list, direct="ASC"):
        return ", ".join(["%s %s" % ((sqlrepr(f) if isinstance(f, Field) else f), direct) for f in f_list])


def _gen_f_list(f_list):
    return ", ".join([(sqlrepr(f) if isinstance(f, Field) else f) for f in f_list])


def _gen_f_list_define(f_list):
    return ", ".join([(sqlrepr(f) if isinstance(f, Field) else f) for f in f_list])


def _gen_v_list(v_list, params):
    values = []
    for v in v_list:
        values.append("%s")
        params.append(v)
    return "(%s)" % (", ".join(values), )


def _gen_v_list_set(v_list_set, params):
    return ", ".join([_gen_v_list(v_list, params) for v_list in v_list_set])


def _gen_fv_dict(fv_dict, params):
    sql = []
    for f, v in fv_dict.items():
        if isinstance(v, Expr):
            sql.append("%s = %s" % (f, sqlrepr(v)))
            params.extend(sqlparams(v))
        else:
            sql.append("%s = %%s" % (f, ))
            params.append(v)

    return ", ".join(sql)


class QuerySet(object):
    def __init__(self, t):
        # complex var
        self.tables = t
        self.fields = []
        self._wheres = None
        self._havings = None

        # simple var
        self._group_by = None
        self._order_by = None
        self._limit = None

        # default var
        self._default_count_field_list = ("*", )
        self._default_count_distinct = False

    @apply
    def wheres():
        def fget(self):
            return self._wheres if self._wheres else ConditionSet()

        def fset(self, cs):
            self._wheres = cs

        return property(**locals())

    @apply
    def havings():
        def fget(self):
            return self._havings if self._havings else ConditionSet()

        def fset(self, cs):
            self._havings = cs

        return property(**locals())

    # public function
    def clone(self):
        return copy.deepcopy(self)

    def on(self, c):
        if not isinstance(self.tables, TableSet):
            raise Error("Can't set on without join table")

        self.tables.on(c)
        return self

    def where(self, c):
        if self._wheres is None:
            self._wheres = c
        else:
            self.wheres = self.wheres & c
        return self

    def or_where(self, c):
        if self._wheres is None:
            self._wheres = c
        else:
            self.wheres = self.wheres | c
        return self

    def group_by(self, *f_list):
        self._group_by = "GROUP BY %s" % (_gen_f_list(f_list), )
        self._default_count_field_list = f_list
        self._default_count_distinct = True
        return self

    def having(self, c):
        if self._havings is None:
            self._havings = c
        else:
            self.havings = self.havings & c
        return self

    def or_having(self, c):
        if self._havings is None:
            self._havings = c
        else:
            self.havings = self.havings | c
        return self

    @opt_checker(["desc"])
    def order_by(self, *f_list, **opt):
        direct = "DESC" if opt.get("desc") else "ASC"
        order_by_field = _gen_order_by_list(f_list, direct)

        if self._order_by is None:
            self._order_by = "ORDER BY %s" % (order_by_field, )
        else:
            self._order_by = "%s, %s" % (self._order_by, order_by_field)

        return self

    def limit(self, offset, limit):
        self._limit = "LIMIT %u, %u" % (offset, limit)
        return self

    @opt_checker(["distinct", "for_update"])
    def count(self, *f_list, **opt):
        sql = ["SELECT"]
        params = []

        if len(f_list) == 0:
            f_list = self._default_count_field_list

        if opt.get("distinct", self._default_count_distinct):
            sql.append("COUNT(DISTINCT %s)" % (_gen_f_list(f_list), ))
        else:
            sql.append("COUNT(%s)" % (_gen_f_list(f_list), ))

        self._join_sql_part(sql, params, ["from", "where"])

        if opt.get("for_update"):
            sql.append("FOR UPDATE")

        return " ".join(sql), params

    @opt_checker(["distinct", "for_update"])
    def select(self, *f_list, **opt):
        sql = ["SELECT"]
        params = []
        f_list = list(f_list)
        f_list += self.fields

        if opt.get("distinct"):
            sql.append("DISTINCT")
        sql.append(_gen_f_list(f_list))

        self._join_sql_part(sql, params, ["from", "where", "group", "having", "order", "limit"])

        if opt.get("for_update"):
            sql.append("FOR UPDATE")

        return " ".join(sql), params

    @opt_checker(["distinct", "for_update"])
    def select_one(self, *f_list, **opt):
        sql = ["SELECT"]
        params = []
        f_list = list(f_list)
        f_list += self.fields

        if opt.get("distinct"):
            sql.append("DISTINCT")
        sql.append(_gen_f_list(f_list))

        self._join_sql_part(sql, params, ["from", "where", "group", "having", "order"])
        sql.append("LIMIT 0, 1")

        if opt.get("for_update"):
            sql.append("FOR UPDATE")

        return " ".join(sql), params

    def select_for_union(self, *f_list):
        return UnionPart(*self.select(*f_list))

    def insert(self, fv_dict, **opt):
        return self.insert_many(fv_dict.keys(), ([fv_dict[k] for k in fv_dict.keys()], ), **opt)

    @opt_checker(["ignore", "on_duplicate_key_update"])
    def insert_many(self, f_list, v_list_set, **opt):
        sql = ["INSERT"]
        params = []

        if opt.get("ignore"):
            sql.append("IGNORE")
        sql.append("INTO")

        self._join_sql_part(sql, params, ["tables"])
        sql.append("(%s) VALUES %s" % (_gen_f_list(f_list), _gen_v_list_set(v_list_set, params)))

        fv_dict = opt.get("on_duplicate_key_update")
        if fv_dict:
            sql.append("ON DUPLICATE KEY UPDATE")
            sql.append(_gen_fv_dict(fv_dict, params))

        return " ".join(sql), params

    @opt_checker(["ignore"])
    def update(self, fv_dict, **opt):
        sql = ["UPDATE"]
        params = []

        if opt.get("ignore"):
            sql.append("IGNORE")

        self._join_sql_part(sql, params, ["tables"])

        sql.append("SET")
        sql.append(_gen_fv_dict(fv_dict, params))

        self._join_sql_part(sql, params, ["where", "limit"])
        return " ".join(sql), params

    def delete(self):
        sql = ["DELETE"]
        params = []

        self._join_sql_part(sql, params, ["from", "where"])
        return " ".join(sql), params

    # private function
    def _join_sql_part(self, sql, params, join_list):
        if "tables" in join_list and self.tables:
            sql.append(sqlrepr(self.tables))
            params.extend(sqlparams(self.tables))
        if "from" in join_list and self.tables:
            sql.extend(["FROM", sqlrepr(self.tables)])
            params.extend(sqlparams(self.tables))
        if "where" in join_list and self._wheres:
            sql.extend(["WHERE", sqlrepr(self._wheres)])
            params.extend(sqlparams(self._wheres))
        if "group" in join_list and self._group_by:
            sql.append(self._group_by)
        if "having" in join_list and self._havings:
            sql.extend(["HAVING", sqlrepr(self._havings)])
            params.extend(sqlparams(self._havings))
        if "order" in join_list and self._order_by:
            sql.append(self._order_by)
        if "limit" in join_list and self._limit:
            sql.append(self._limit)


class UnionPart(object):
    def __init__(self, sql, params):
        self._sql = sql
        self._params = params

    def __mul__(self, up):
        if not isinstance(up, UnionPart):
            raise TypeError("Can't do operation with %s" % str(type(up)))
        return UnionQuerySet(self) * up

    def __add__(self, up):
        if not isinstance(up, UnionPart):
            raise TypeError("Can't do operation with %s" % str(type(up)))
        return UnionQuerySet(self) + up

    def __sqlrepr__(self):
        return self._sql

    def __params__(self):
        return self._params


class UnionQuerySet(object):
    def __init__(self, up):
        self._union_part_list = [(None, up)]

        self._group_by = None
        self._order_by = None
        self._limit = None

    def __mul__(self, up):
        if not isinstance(up, UnionPart):
            raise TypeError("Can't do operation with %s" % str(type(up)))
        self._union_part_list.append(("UNION DISTINCT", up))
        return self

    def __add__(self, up):
        if not isinstance(up, UnionPart):
            raise TypeError("Can't do operation with %s" % str(type(up)))
        self._union_part_list.append(("UNION ALL", up))
        return self

    @opt_checker(["desc"])
    def order_by(self, *f_list, **opt):
        direct = "DESC" if opt.get("desc") else "ASC"
        order_by_field = _gen_order_by_list(f_list, direct)

        if self._order_by is None:
            self._order_by = "ORDER BY %s" % (order_by_field, )
        else:
            self._order_by = "%s, %s" % (self._order_by, order_by_field)

        return self

    def limit(self, offset, limit):
        self._limit = "LIMIT %u, %u" % (offset, limit)
        return self

    def select(self):
        sql = []
        params = []

        for union_type, part in self._union_part_list:
            if union_type:
                sql.append(union_type)
            sql.append("(%s)" % (sqlrepr(part), ))

            params.extend(sqlparams(part))

        if self._order_by:
            sql.append(self._order_by)
        if self._limit:
            sql.append(self._limit)

        return " ".join(sql), params

T, F, E, QS = Table, Field, Expr, QuerySet

if __name__ == "__main__":

    print
    print "*******************************************"
    print "************   Single Query   *************"
    print "*******************************************"
    print QS((T.base + T.grade).on((F.base__type == F.grade__item_type) & (F.base__type == 1)) + T.lottery).on(
        F.base__type == F.lottery__item_type
    ).where(
        (F.name == "name") & (F.status == 0) | (F.name == None)
    ).group_by("base.type").having(F("count(*)") > 1).select(F.type, F.grade__grade, F.lottery__grade)

    print
    print "*******************************************"
    print "**********  Step by Step Query   **********"
    print "*******************************************"
    t = T.grade
    print QS(t).limit(0, 100).select(F.name)
    print "==========================================="

    t = (t * T.base).on(F.grade__item_type == F.base__type)
    print QS(t).order_by(F.grade__name, F.base__name, desc=True).select(F.grade__name, F.base__img)
    print "==========================================="

    t = (t + T.lottery).on(F.base__type == F.lottery__item_type)
    print QS(t).group_by(F.grade__grade).having(F.grade__grade > 0).select(F.grade__name, F.base__img, F.lottery__price)
    print "==========================================="

    w = (F.base__type == 1)
    print QS(t).where(w).select(F.grade__name, for_update=True)
    print "==========================================="

    w = w & (F.grade__status == [0, 1])
    print QS(t).where(w).group_by(F.grade__name, F.base__img).count()
    print "==========================================="

    from datetime import datetime
    w = w | (F.lottery__add_time > "2009-01-01") & (F.lottery__add_time <= datetime.now())
    print QS(t).where(w).select_one(F.grade__name, F.base__img, F.lottery__price)
    print "==========================================="

    w = w & (F.base__status != [1, 2])
    print QS(t).where(w).select(F.grade__name, F.base__img, F.lottery__price, "CASE 1 WHEN 1")

    print
    print "*******************************************"
    print "**********  Step by Step Query2  **********"
    print "*******************************************"
    qs = QS(T.user)
    print qs.select(F.name)
    print "==========================================="
    qs.tables = (qs.tables * T.address).on(F.user__id == F.address__user_id)
    print qs.select(F.user__name, F.address__street)
    print "==========================================="
    qs.wheres = qs.wheres & (F.id == 1)
    print qs.select(F.name, F.id)
    print "==========================================="
    qs.wheres = qs.wheres & ((F.address__city_id == [111, 112]) | "address.city_id IS NULL")
    print qs.select(F.user__name, F.address__street, "COUNT(*) AS count")
    print "==========================================="

    print
    print "*******************************************"
    print "**********      Union Query      **********"
    print "*******************************************"
    a = QS(T.item).where(F.status != -1).select_for_union("type, name, img")
    b = QS(T.gift).where(F.storage > 0).select_for_union("type, name, img")
    print (a + b).order_by("type", "name", desc=True).limit(100, 10).select()

    print
    print "*******************************************"
    print "**********    Other Operation    **********"
    print "*******************************************"
    print QS(T.user).insert({
        "name": "garfield",
        "gender": "male",
        "status": 0
    }, ignore=True)
    print "==========================================="
    fl = ("name", "gender", "status", "age")
    vl = (("garfield", "male", 0, 1), ("superwoman", "female", 0, 10))
    print QS(T.user).insert_many(fl, vl, on_duplicate_key_update={"age": E("age + VALUES(age)")})
    print "==========================================="
    print QS(T.user).where(F.id == 100).update({"name": "nobody", "status": 1}, ignore=True)
    print "==========================================="
    print QS(T.user).where(F.status == 1).delete()
