from .. import compile as parent_compile, Name, Field, Value
from .mysql import compile_value

try:
    str = unicode  # Python 2.* compatible
    string_types = (basestring,)
    integer_types = (int, long)

except NameError:
    string_types = (str,)
    integer_types = (int,)

compile = parent_compile.create_child()


@compile.when(Field)
def compile_field(compile, expr, state):
    if expr._name == '*':
        state.sql.append(expr._name)
    else:
        compile(Name(expr._name), state)


compile.when(Value)(compile_value)
