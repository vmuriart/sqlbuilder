# -*- coding: utf-8 -*-
# Some ideas from http://code.google.com/p/py-smart-sql-constructor/
# But the code fully another... It's not a fork anymore...
from __future__ import absolute_import
import sys
import copy
import warnings
from functools import wraps
from weakref import WeakKeyDictionary

try:
    str = unicode  # Python 2.* compatible
    string_types = (basestring,)
    integer_types = (int, long)

except NameError:
    string_types = (str,)
    integer_types = (int,)


DEFAULT_DIALECT = 'postgres'
PLACEHOLDER = "%s"  # Can be re-defined by registered dialect.
LOOKUP_SEP = '__'
MAX_PRECEDENCE = 1000
SPACE = " "

CONTEXT_QUERY = 0
CONTEXT_COLUMN = 1
CONTEXT_TABLE = 2


class ClassRegistry(object):
    def __call__(self, name_or_cls):
        name = name_or_cls if isinstance(name_or_cls, string_types) else name_or_cls.__name__

        def deco(cls):
            setattr(self, name, cls)
            if not getattr(cls, '_cr', None) is self:  # save mem
                cls._cr = self
            return cls

        return deco if isinstance(name_or_cls, string_types) else deco(name_or_cls)


cr = ClassRegistry()


class State(object):

    def __init__(self):
        self.sql = []
        self.params = []
        self._stack = []
        self._callers = []
        self.context = CONTEXT_QUERY
        self.precedence = 0

    def push(self, attr, new_value):
        old_value = getattr(self, attr, None)
        self._stack.append((attr, old_value))
        if new_value is None:
            new_value = copy(old_value)
        setattr(self, attr, new_value)
        return old_value

    def pop(self):
        setattr(self, *self._stack.pop(-1))


class Compiler(object):

    def __init__(self, parent=None):
        self._children = WeakKeyDictionary()
        self._parents = []
        self._local_registry = {}
        self._local_precedence = {}
        self._registry = {}
        self._precedence = {}
        if parent:
            self._parents.extend(parent._parents)
            self._parents.append(parent)
            parent._children[self] = True
            self._update_cache()

    def create_child(self):
        return self.__class__(self)

    def when(self, cls):
        def deco(func):
            self._local_registry[cls] = func
            self._update_cache()
            return func
        return deco

    def _update_cache(self):
        for parent in self._parents:
            self._registry.update(parent._local_registry)
            self._precedence.update(parent._local_precedence)
        self._registry.update(self._local_registry)
        self._precedence.update(self._local_precedence)
        for child in self._children:
            child._update_cache()

    def __call__(self, expr, state=None):
        if state is None:
            state = State()
            self(expr, state)
            return ''.join(state.sql), state.params

        cls = expr.__class__
        parentheses = False
        if state._callers:
            if state._callers[0] in (OmitParentheses, Parentheses):
                pass
            elif isinstance(expr, (Condition, Query)) or type(expr) == Expr:
                parentheses = True

        # outer_precedence = state.precedence
        # if hasattr(cls, '_sql') and cls._sql in self._precedence:
        #     inner_precedence = state.precedence = self._precedence[cls._sql]
        # else:
        #     inner_precedence = state.precedence = self._precedence.get(cls, MAX_PRECEDENCE)
        # if inner_precedence < outer_precedence:
        #     parentheses = True

        state._callers.insert(0, expr.__class__)

        if parentheses:
            state.sql.append('(')

        for c in cls.mro():
            if c in self._registry:
                self._registry[c](self, expr, state)
                break
        else:
            raise Error("Unknown compiler for {}".format(cls))

        if parentheses:
            state.sql.append(')')
        state._callers.pop(0)
        # state.precedence = outer_precedence


compile = Compiler()


def opt_checker(k_list):
    def new_deco(f):
        @wraps(f)
        def new_func(self, *args, **opt):
            for k, v in list(opt.items()):
                if k not in k_list:
                    raise TypeError("Not implemented option: {0}".format(k))
            return f(self, *args, **opt)
        return new_func
    return new_deco


def cached_compile(f):
    @wraps(f)
    def deco(compile, expr, state):
        if compile not in expr.__cached__:
            state.push('sql', [])
            f(compile, expr, state)
            expr.__cached__[compile] = ''.join(state.sql)
            state.pop()
        state.sql.append(expr.__cached__[compile])
    return deco


def same(name):
    def f(self, *a, **kw):
        return getattr(self, name)(*a, **kw)
    return f


@compile.when(object)
def compile_object(compile, expr, state):
    state.sql.append('%s')
    state.params.append(expr)


@compile.when(type(None))
def compile_none(compile, expr, state):
    state.sql.append('NULL')


@compile.when(list)
@compile.when(tuple)
def compile_list(compile, expr, state):
    compile(Parentheses(ExprList(*expr).join(", ")), state)


class Error(Exception):
    pass


class Comparable(object):

    __slots__ = ()

    def _c(op, inv=False):
        return (lambda self, other: Condition(self, op, other)) if not inv else (lambda self, other: Condition(other, op, self))

    def _ca(op, inv=False):
        return (lambda self, *a: Constant(op)(self, *a)) if not inv else (lambda self, other: Constant(op)(other, self))

    def _p(op):
        return lambda self: Prefix(op, self)

    def _l(mask, ci=False, inv=False):
        a = 'like'
        if ci:
            a = 'i' + a
        if inv:
            a = 'r' + a

        def f(self, other):
            args = [other]
            if 4 & mask:
                args.insert(0, '%')
            if 1 & mask:
                args.append('%')
            return getattr(self, a)(Concat(*args))
        return f

    __add__ = _c("+")
    __radd__ = _c("+", 1)
    __sub__ = _c("-")
    __rsub__ = _c("-", 1)
    __mul__ = _c("*")
    __rmul__ = _c("*", 1)
    __div__ = _c("/")
    __rdiv__ = _c("/", 1)
    __and__ = _c("AND")
    __rand__ = _c("AND", 1)
    __or__ = _c("OR")
    __ror__ = _c("OR", 1)
    __gt__ = _c(">")
    __lt__ = _c("<")
    __ge__ = _c(">=")
    __le__ = _c("<=")
    is_ = _c("IS")
    is_not = _c("IS NOT")
    in_ = _c("IN")
    not_in = _c("NOT IN")
    like = _c("LIKE")
    ilike = _c("ILIKE")
    rlike = _c("LIKE", 1)
    rilike = _c("ILIKE", 1)

    __pos__ = _p("+")
    __neg__ = _p("-")
    __invert__ = _p("NOT")
    distinct = _p("DISTINCT")

    __pow__ = _ca("POW")
    __rpow__ = _ca("POW", 1)
    __mod__ = _ca("MOD")
    __rmod__ = _ca("MOD", 1)
    __abs__ = _ca("ABS")
    count = _ca("COUNT")

    startswith = _l(1)
    istartswith = _l(1, 1)
    contains = _l(5)
    icontains = _l(5, 1)
    endswith = _l(4)
    iendswith = _l(4, 1)
    rstartswith = _l(1, 0, 1)
    ristartswith = _l(1, 1, 1)
    rcontains = _l(5, 0, 1)
    ricontains = _l(5, 1, 1)
    rendswith = _l(4, 0, 1)
    riendswith = _l(4, 1, 1)

    def __eq__(self, other):
        if other is None:
            return self.is_(None)
        if is_list(other):
            return self.in_(other)
        return Condition(self, "=", other)

    def __ne__(self, other):
        if other is None:
            return self.is_not(None)
        if is_list(other):
            return self.not_in(other)
        return Condition(self, "<>", other)

    def as_(self, alias):
        return Alias(alias, self)

    def between(self, start, end):
        return Between(self, start, end)

    def concat(self, *args):
        return Concat(self, *args)

    def concat_ws(self, sep, *args):
        return Concat(self, *args).ws(sep)

    def op(self, op):
        return lambda other: Condition(self, op, other)

    def rop(self, op):  # useless, can be P('lookingfor').op('=')(expr)
        return lambda other: Condition(other, op, self)

    def asc(self):
        return Postfix(self, "ASC")

    def desc(self):
        return Postfix(self, "DESC")

    def __getitem__(self, key):
        """Returns self.between()"""
        if isinstance(key, slice):
            start = key.start or 0
            end = key.stop or sys.maxsize
            return Between(self, start, end)
        else:
            return self.__eq__(key)

    # __hash__ = None


class Expr(Comparable):

    __slots__ = ('_sql', '_params')

    def __init__(self, sql, *params):
        if params and is_list(params[0]):
            return self.__init__(sql, *params[0])
        self._sql, self._params = sql, params


@compile.when(Expr)
def compile_expr(compile, expr, state):
    state.sql.append(expr._sql)
    state.params += expr._params


class Condition(Expr):

    __slots__ = ('_left', '_right')

    def __init__(self, left, op, right):
        self._left = left
        self._sql = op.upper()
        self._right = right


@compile.when(Condition)
def compile_condition(compile, expr, state):
    compile(expr._left, state)
    state.sql.append(SPACE)
    state.sql.append(expr._sql)
    state.sql.append(SPACE)
    compile(expr._right, state)


class ExprList(Expr):

    __slots__ = ('data', )

    def __init__(self, *args):
        # if args and is_list(args[0]):
        #     return self.__init__(*args[0])
        self._sql, self.data = " ", list(args)

    def join(self, sep):
        self._sql = sep
        return self

    def __len__(self):
        return len(self.data)

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        if isinstance(key, slice):
            start = key.start or 0
            end = key.stop or sys.maxsize
            return ExprList(*self.data[start:end])
        return self.data[key]

    def __iter__(self):
        return iter(self.data)

    def append(self, x):
        return self.data.append(x)

    def insert(self, i, x):
        return self.data.insert(i, x)

    def extend(self, L):
        return self.data.extend(L)

    def pop(self, i):
        return self.data.pop(i)

    def remove(self, x):
        return self.data.remove(x)

    def reset(self):
        del self.data[:]
        return self

    def __copy__(self):
        dup = copy.copy(super(ExprList, self))
        dup.data = dup.data[:]
        return dup


@compile.when(ExprList)
def compile_exprlist(compile, expr, state):
    first = True
    for a in expr:
        if first:
            first = False
        else:
            state.sql.append(expr._sql)
        compile(a, state)


class FieldList(ExprList):
    __slots__ = ()

    def __init__(self, *args):
        # if args and is_list(args[0]):
        #     return self.__init__(*args[0])
        self._sql, self.data = ", ", list(args)


@compile.when(FieldList)
def compile_fieldlist(compile, expr, state):
    # state.push('context', CONTEXT_COLUMN)
    compile_exprlist(compile, expr, state)
    # state.pop()


class Concat(ExprList):

    __slots__ = ('_ws', )

    def __init__(self, *args):
        super(Concat, self).__init__(*args)
        self._sql = ' || '
        self._ws = None

    def ws(self, sep):
        self._ws = sep
        self._sql = ', '
        return self


@compile.when(Concat)
def compile_concat(compile, expr, state):
    if not expr._ws:
        return compile_exprlist(compile, expr, state)
    state.sql.append('concat_ws(')
    compile(expr._ws, state)
    for a in expr:
        state.sql.append(expr._sql)
        compile(a, state)
    state.sql.append(')')


class Param(Expr):

    __slots__ = ()


Placeholder = Param


class Parentheses(Expr):

    __slots__ = ('_expr', )

    def __init__(self, expr):
        self._expr = expr


@compile.when(Parentheses)
def compile_parentheses(compile, expr, state):
    state.sql.append('(')
    compile(expr._expr, state)
    state.sql.append(')')


class OmitParentheses(Parentheses):
    pass


@compile.when(OmitParentheses)
def compile_omitparentheses(compile, expr, state):
    compile(expr._expr, state)


class Prefix(Expr):

    __slots__ = ('_expr', )

    def __init__(self, prefix, expr):
        self._sql = prefix
        self._expr = expr


@compile.when(Prefix)
def compile_prefix(compile, expr, state):
    state.sql.append(expr._sql)
    state.sql.append(SPACE)
    compile(expr._expr, state)


class Postfix(Expr):

    __slots__ = ('_expr', )

    def __init__(self, expr, postfix):
        self._sql = postfix
        self._expr = expr


@compile.when(Postfix)
def compile_postfix(compile, expr, state):
    compile(expr._expr, state)
    state.sql.append(SPACE)
    state.sql.append(expr._sql)


class Between(Expr):

    __slots__ = ('_expr', '_start', '_end')

    def __init__(self, expr, start, end):
        self._expr, self._start, self._end = expr, start, end


@compile.when(Between)
def compile_between(compile, expr, state):
    compile(expr._expr, state)
    state.sql.append(' BETWEEN ')
    compile(expr._start, state)
    state.sql.append(' AND ')
    compile(expr._end, state)


class Callable(Expr):

    __slots__ = ('_expr', '_args')

    def __init__(self, expr, *args):
        self._expr = expr
        self._args = ExprList(*args).join(", ")


@compile.when(Callable)
def compile_callable(compile, expr, state):
    compile(expr._expr, state)
    state.sql.append('(')
    compile(expr._args, state)
    state.sql.append(')')


class Constant(Expr):

    __slots__ = ()

    def __init__(self, const):
        self._sql = const.upper()

    def __call__(self, *args):
        return Callable(self, *args)


@compile.when(Constant)
def compile_constant(compile, expr, state):
    state.sql.append(expr._sql)


class ConstantSpace(object):

    __slots__ = ()

    def __getattr__(self, attr):
        return Constant(attr)


class MetaField(type):

    def __getattr__(cls, key):
        if key[0] == '_':
            raise AttributeError
        parts = key.split(LOOKUP_SEP, 2)
        prefix, name, alias = parts + [None] * (3 - len(parts))
        if name is None:
            prefix, name = name, prefix
        f = cls(name, prefix)
        return f.as_(alias) if alias else f


class Field(MetaField("NewBase", (Expr,), {})):

    __slots__ = ('_name', '_prefix', '__cached__')

    def __init__(self, name, prefix=None):
        self._name = name
        if isinstance(prefix, string_types):
            prefix = Table(prefix)
        self._prefix = prefix
        self.__cached__ = {}


@compile.when(Field)
@cached_compile
def compile_field(compile, expr, state):
    if expr._prefix is not None:
        compile(expr._prefix, state)
        state.sql.append('.')
    if expr._name == '*':
        state.sql.append(expr._name)
    else:
        compile(Name(expr._name), state)


class Alias(Expr):

    __slots__ = ('_expr', '_sql')

    def __init__(self, alias, expr=None):
        self._expr = expr
        super(Alias, self).__init__(alias)


@compile.when(Alias)
def compile_alias(compile, expr, state):
    try:
        render_column = state._callers[1] == FieldList
        # render_column = state.context == CONTEXT_COLUMN
    except IndexError:
        pass
    else:
        if render_column:
            compile(expr._expr, state)
            state.sql.append(' AS ')
    compile(Name(expr._sql), state)


class MetaTable(type):

    def __new__(cls, name, bases, attrs):
        def _f(attr):
            return lambda self, *a, **kw: getattr(self._cr.TableJoin(self), attr)(*a, **kw)

        for a in ['inner_join', 'left_join', 'right_join', 'full_join', 'cross_join', 'join', 'on', 'hint']:
            attrs[a] = _f(a)
        return type.__new__(cls, name, bases, attrs)

    def __getattr__(cls, key):
        if key[0] == '_':
            raise AttributeError
        parts = key.split(LOOKUP_SEP, 1)
        name, alias = parts + [None] * (2 - len(parts))
        table = cls(name)
        return table.as_(alias) if alias else table


@cr
class Table(MetaTable("NewBase", (object, ), {})):

    __slots__ = ('_name', '__cached__')

    def __init__(self, name):
        self._name = name
        self.__cached__ = {}

    def as_(self, alias):
        return self._cr.TableAlias(alias, self)

    def __getattr__(self, name):
        if name[0] == '_':
            raise AttributeError
        parts = name.split(LOOKUP_SEP, 1)
        name, alias = parts + [None] * (2 - len(parts))
        f = Field(name, self)
        if alias:
            f = f.as_(alias)
        setattr(self, name, f)
        return f

    __and__ = same('inner_join')
    __add__ = same('left_join')
    __sub__ = same('right_join')
    __or__ = same('full_join')
    __mul__ = same('cross_join')


@compile.when(Table)
def compile_table(compile, expr, state):
    compile(Name(expr._name), state)


@cr
class TableAlias(Table):

    __slots__ = ('_table', '_alias')

    def __init__(self, alias, table=None):
        self._table = table
        self._alias = alias
        self.__cached__ = {}

    def as_(self, alias):
        return type(self)(alias, self._table)


@compile.when(TableAlias)
def compile_tablealias(compile, expr, state):
    # if expr._table is not None and state.context == CONTEXT_TABLE:
    try:
        render_table = expr._table is not None and state._callers[1] == TableJoin
        # render_table = expr._table is not None and state.context == CONTEXT_TABLE
    except IndexError:
        pass
    else:
        if render_table:
            compile(expr._table, state)
            state.sql.append(' AS ')
    compile(Name(expr._alias), state)


@cr
class TableJoin(object):

    __slots__ = ('_table', '_alias', '_join_type', '_on', '_left', '_hint', '_nested')

    def __init__(self, table_or_alias, join_type=None, on=None, left=None):
        self._table = table_or_alias
        self._join_type = join_type
        self._on = on
        self._left = left
        self._hint = None
        self._nested = False

    def _j(j):
        return lambda self, obj: self.join(j, obj)

    inner_join = _j("INNER JOIN")
    left_join = _j("LEFT OUTER JOIN")
    right_join = _j("RIGHT OUTER JOIN")
    full_join = _j("FULL OUTER JOIN")
    cross_join = _j("CROSS JOIN")

    def join(self, join_type, obj):
        if not isinstance(obj, TableJoin) or obj.left():
            obj = type(self)(obj, left=self)
        obj = obj.left(self).join_type(join_type)
        return obj

    def left(self, left=None):
        if left is None:
            return self._left
        self._left = left
        return self

    def join_type(self, join_type):
        self._join_type = join_type
        return self

    def on(self, c):
        if self._on is not None:
            self = type(self)(self)
        self._on = c
        return self

    def __call__(self):
        self._nested = True
        self = self.__class__(self)
        return self

    def hint(self, expr):
        if isinstance(expr, string_types):
            expr = Expr(expr)
        self._hint = OmitParentheses(expr)
        return self

    def __copy__(self):
        dup = copy.copy(super(TableJoin, self))
        for a in ['_hint', ]:
            setattr(dup, a, copy.copy(getattr(dup, a, None)))
        return dup

    as_nested = same('__call__')
    group = same('__call__')
    __and__ = same('inner_join')
    __add__ = same('left_join')
    __sub__ = same('right_join')
    __or__ = same('full_join')
    __mul__ = same('cross_join')


@compile.when(TableJoin)
def compile_tablejoin(compile, expr, state):
    if expr._nested:
        state.sql.append('(')
    if expr._left is not None:
        compile(expr._left, state)
    if expr._join_type:
        state.sql.append(SPACE)
        state.sql.append(expr._join_type)
        state.sql.append(SPACE)
    state.push('context', CONTEXT_TABLE)
    compile(expr._table, state)
    state.pop()
    if expr._on is not None:
        state.sql.append(' ON ')
        compile(expr._on, state)
    if expr._hint is not None:
        state.sql.append(SPACE)
        compile(expr._hint, state)
    if expr._nested:
        state.sql.append(')')


@cr
class Query(Expr):
    # Without methods like insert, delete, update etc. it will be named Select.

    compile = compile

    def __init__(self, tables=None):

        self._distinct = False
        self._fields = FieldList().join(", ")
        if tables:
            if not isinstance(tables, TableJoin):
                tables = self._cr.TableJoin(tables)
        self._tables = tables
        self._wheres = None
        self._havings = None
        self._group_by = ExprList().join(", ")
        self._order_by = ExprList().join(", ")
        self._limit = None
        self._offset = None

        self._for_update = False

    def clone(self):
        dup = copy.copy(super(Query, self))
        for a in ['_fields', '_tables', '_group_by', '_order_by']:
            setattr(dup, a, copy.copy(getattr(dup, a, None)))
        return dup

    def tables(self, t=None):
        if t is None:
            return self._tables
        self = self.clone()
        self._tables = t if isinstance(t, TableJoin) else self._cr.TableJoin(t)
        return self

    def distinct(self, val=None):
        if val is None:
            return self._distinct
        self = self.clone()
        self._distinct = val
        return self

    @opt_checker(["reset", ])
    def fields(self, *args, **opts):
        if not args and not opts:
            return self._fields

        if args and is_list(args[0]):
            return self.fields(*args[0], reset=True)

        c = self.clone()
        if opts.get("reset"):
            c._fields.reset()
        if args:
            c._fields.extend([f if isinstance(f, Expr) else Field(f) for f in args])
        return c

    def on(self, c):
        # TODO: Remove?
        self = self.clone()
        if not isinstance(self._tables, TableJoin):
            raise Error("Can't set on without join table")
        self._tables = self._tables.on(c)
        return self

    def where(self, c):
        self = self.clone()
        self._wheres = c if self._wheres is None else self._wheres & c
        return self

    def or_where(self, c):
        self = self.clone()
        self._wheres = c if self._wheres is None else self._wheres | c
        return self

    @opt_checker(["reset", ])
    def group_by(self, *args, **opts):
        if not args and not opts:
            return self._group_by

        if args and is_list(args[0]):
            return self.group_by(*args[0], reset=True)

        c = self.clone()
        if opts.get("reset"):
            c._group_by.reset()
        if args:
            c._group_by.extend(args)
        return c

    def having(self, cond):
        c = self.clone()
        c._havings = cond if c._havings is None else c._havings & cond
        return c

    def or_having(self, cond):
        c = self.clone()
        c._havings = cond if c._havings is None else c._havings | cond
        return c

    @opt_checker(["desc", "reset", ])
    def order_by(self, *args, **opts):
        if not args and not opts:
            return self._order_by

        if args and is_list(args[0]):
            return self.order_by(*args[0], reset=True)

        c = self.clone()
        if opts.get("reset"):
            c._order_by.reset()
        if args:
            direct = "DESC" if opts.get("desc") else "ASC"
            c._order_by.extend([f if isinstance(f, Postfix) and f._sql in ("ASC", "DESC") else Postfix(f, direct) for f in args])
        return c

    def limit(self, *args, **kwargs):
        c = self.clone()
        if args:
            if len(args) < 2:
                args = (0,) + args
            c._offset, c._limit = args
        else:
            c._limit = kwargs.get('limit')
            c._offset = kwargs.get('offset', 0)
        return c

    def __getitem__(self, key):
        if isinstance(key, slice):
            offset = key.start or 0
            limit = key.stop - offset if key.stop else None
        else:
            offset, limit = key, 1
        return self.limit(offset, limit)

    @opt_checker(["distinct", "for_update"])
    def select(self, *args, **opts):
        c = self.clone()
        if args:
            c = c.fields(*args)
        if opts.get("distinct"):
            c = c.distinct(True)
        if opts.get("for_update"):
            c._for_update = True
        return c.result()

    def count(self):
        return self.result(SelectCount(self))

    def insert(self, fv_dict=None, **kw):
        kw.setdefault('table', self._tables)
        kw.setdefault('fields', self._fields)
        return self.result(self._cr.Insert(map=fv_dict, **kw))

    def insert_many(self, fields, values, **kw):
        return self.insert(fields=fields, values=values, **kw)

    def update(self, key_values, **kw):
        kw.setdefault('table', self._tables)
        kw.setdefault('fields', self._fields)
        kw.setdefault('where', self._wheres)
        kw.setdefault('order_by', self._order_by)
        kw.setdefault('limit', self._limit)
        return self.result(self._cr.Update(map=key_values, **kw))

    def delete(self, **kw):
        kw.setdefault('table', self._tables)
        kw.setdefault('where', self._wheres)
        kw.setdefault('order_by', self._order_by)
        kw.setdefault('limit', self._limit)
        return self.result(self._cr.Delete(**kw))

    def as_table(self, alias):
        return self._cr.TableAlias(alias, self)

    def set(self, all=False):
        return self._cr.Set(self, all=all)

    def execute(self, expr):
        return self.compile(expr)

    def result(self, expr=None):
        return self.execute(self if expr is None else expr)

    def set_compiler(self, compile):
        c = self.clone()
        c.compile = compile
        return c

    columns = same('fields')
    __copy__ = same('clone')


QuerySet = Query


@compile.when(Query)
def compile_queryset(compile, expr, state):
    state.sql.append("SELECT ")
    if expr._distinct:
        state.sql.append("DISTINCT ")
    compile(expr._fields, state)
    state.sql.append(" FROM ")
    compile(expr._tables, state)
    if expr._wheres:
        state.sql.append(" WHERE ")
        compile(expr._wheres, state)
    if expr._group_by:
        state.sql.append(" GROUP BY ")
        compile(expr._group_by, state)
    if expr._havings:
        state.sql.append(" HAVING ")
        compile(expr._havings, state)
    if expr._order_by:
        state.sql.append(" ORDER BY ")
        compile(expr._order_by, state)
    if expr._limit is not None:
        state.sql.append(" LIMIT ")
        compile(expr._limit, state)
    if expr._offset:
        state.sql.append(" OFFSET ")
        compile(expr._offset, state)
    if expr._for_update:
        state.sql.append(" FOR UPDATE")


@cr
class SelectCount(Query):

    def __init__(self, qs):
        Query.__init__(self, qs.order_by(reset=True).as_table('count_list'))
        self._fields.append(Constant('COUNT')(Constant('1')).as_('count_value'))


class Modify(object):
    pass


@cr
class Insert(Modify):

    def __init__(self, table, map=None, fields=None, values=None, ignore=False, on_duplicate_key_update=None):
        self._table = table
        self._fields = FieldList(*(k if isinstance(k, Expr) else Field(k) for k in (map or fields)))
        self._values = (tuple(map.values()),) if map else values
        self._ignore = ignore
        self._on_duplicate_key_update = tuple(
            (k if isinstance(k, Expr) else Field(k), v)
            for k, v in on_duplicate_key_update.items()
        ) if on_duplicate_key_update else None


@compile.when(Insert)
def compile_insert(compile, expr, state):
    state.sql.append("INSERT ")
    if expr._ignore:
        state.sql.append("IGNORE ")
    state.sql.append("INTO ")
    compile(expr._table, state)
    state.sql.append(SPACE)
    compile(Parentheses(expr._fields), state)
    state.sql.append(" VALUES ")
    compile(ExprList(*expr._values).join(', '), state)
    if expr._on_duplicate_key_update:
        state.sql.append(" ON DUPLICATE KEY UPDATE ")
        first = True
        for f, v in expr._on_duplicate_key_update:
            if first:
                first = False
            else:
                state.sql.append(", ")
            compile(f, state)
            state.sql.append(" = ")
            compile(v, state)


@cr
class Update(Modify):

    def __init__(self, table, map=None, fields=None, values=None, ignore=False, where=None, order_by=None, limit=None):
        self._table = table
        self._fields = FieldList(*(k if isinstance(k, Expr) else Field(k) for k in (map or fields)))
        self._values = tuple(map.values()) if map else values
        self._ignore = ignore
        self._where = where
        self._order_by = order_by
        self._limit = limit


@compile.when(Update)
def compile_update(compile, expr, state):
    state.sql.append("UPDATE ")
    if expr._ignore:
        state.sql.append("IGNORE ")
    compile(expr._table, state)
    state.sql.append(" SET ")
    first = True
    for f, v in zip(expr._fields, expr._values):
        if first:
            first = False
        else:
            state.sql.append(", ")
        compile(f, state)
        state.sql.append(" = ")
        compile(v, state)
    if expr._where:
        state.sql.append(" WHERE ")
        compile(expr._where, state)
    if expr._order_by:
        state.sql.append(" ORDER BY ")
        compile(expr._order_by, state)
    if expr._limit is not None:
        state.sql.append(" LIMIT ")
        compile(expr._limit, state)


@cr
class Delete(Modify):

    def __init__(self, table, where=None, order_by=None, limit=None):
        self._table = table
        self._where = where
        self._order_by = order_by
        self._limit = limit


@compile.when(Delete)
def compile_delete(compile, expr, state):
    state.sql.append("DELETE FROM ")
    compile(expr._table, state)
    if expr._where:
        state.sql.append(" WHERE ")
        compile(expr._where, state)
    if expr._order_by:
        state.sql.append(" ORDER BY ")
        compile(expr._order_by, state)
    if expr._limit is not None:
        state.sql.append(" LIMIT ")
        compile(expr._limit, state)


@cr
class Set(Query):

    def __init__(self, *exprs, **kw):
        super(Set, self).__init__()
        self._sql, self._all = kw.get('op'), kw.get('all', False)
        self._exprs = ExprList(*exprs)

    def _f(op):
        def f(self, qs):
            c = self
            if self._sql is None:
                self._sql = op
            elif self._sql != op:
                c = self._cr.Set(self, op, self._all)
            c._exprs.append(qs)
            return c
        return f

    __or__ = _f('UNION')
    __and__ = _f('INTERSECT')
    __sub__ = _f('EXCEPT')

    def all(self, all=True):
        self._all = all
        return self

    def clone(self):
        self = super(Set, self).clone()
        self._exprs = copy.copy(self._exprs)
        return self


@compile.when(Set)
def compile_set(compile, expr, state):
    if expr._all:
        op = ' {} ALL '.format(expr._sql)
    else:
        op = ' {} '.format(expr._sql)
    compile(expr._exprs.join(op), state)
    if expr._order_by:
        state.sql.append(" ORDER BY ")
        compile(expr._order_by, state)
    if expr._limit is not None:
        state.sql.append(" LIMIT ")
        compile(expr._limit, state)
    if expr._offset:
        state.sql.append(" OFFSET ")
        compile(expr._offset, state)
    if expr._for_update:
        state.sql.append(" FOR UPDATE")


class Name(object):

    __slots__ = ('_name', )

    def __init__(self, name=None):
        self._name = name


@compile.when(Name)
def compile_name(compile, expr, state):
    state.sql.append('"')
    state.sql.append(expr._name)
    state.sql.append('"')


def is_list(v):
    return isinstance(v, (list, tuple))


def warn(old, new, stacklevel=3):
    warnings.warn("{0} is deprecated. Use {1} instead".format(old, new), PendingDeprecationWarning, stacklevel=stacklevel)

A, C, E, F, P, T, TA, Q, QS = Alias, Condition, Expr, Field, Placeholder, Table, TableAlias, Query, Query
func = const = ConstantSpace()
qn = lambda name, compile: compile(Name(name))[0]

for cls in (Expr, Table, TableJoin, Modify):
    cls.__repr__ = lambda self: "<{0}: {1}, {2}>".format(type(self).__name__, *compile(self))
