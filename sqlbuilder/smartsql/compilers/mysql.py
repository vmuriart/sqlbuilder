from .. import compile as parent_compile, SPACE, Name, Value, ValueCompiler as ValueCompilerOrig, Concat, Binary

try:
    str = unicode  # Python 2.* compatible
    string_types = (basestring,)
    integer_types = (int, long)

except NameError:
    string_types = (str,)
    integer_types = (int,)

compile = parent_compile.create_child()

TRANSLATION_MAP = {
    'LIKE': 'LIKE BINARY',
    'ILIKE': 'LIKE',
}


@compile.when(Name)
def compile_name(compile, expr, state):
    state.sql.append('`')
    state.sql.append(expr._name)
    state.sql.append('`')


class ValueCompiler(ValueCompilerOrig):

    _translation_map = (("'", "\\'"),) + ValueCompilerOrig._translation_map[1:]

compile_value = ValueCompiler()
compile.when(Value)(compile_value)


@compile.when(Binary)
def compile_condition(compile, expr, state):
    compile(expr._left, state)
    state.sql.append(SPACE)
    state.sql.append(TRANSLATION_MAP.get(expr._sql, expr._sql))
    state.sql.append(SPACE)
    compile(expr._right, state)


@compile.when(Concat)
def compile_concat(compile, expr, state):
    if not expr._ws:
        state.sql.append('CONCAT(')
        first = True
        for a in expr:
            if first:
                first = False
            else:
                state.sql.append(', ')
            compile(a, state)
        state.sql.append(')')
    else:
        state.sql.append('CONCAT_WS(')
        compile(expr._ws, state)
        for a in expr:
            state.sql.append(expr._sql)
            compile(a, state)
        state.sql.append(')')
