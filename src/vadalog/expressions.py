"""Expression evaluation (SPECIFICATION.md sec. 4)."""

from .ast import EAgg, EBinary, ECall, EConst, ESkolem, EUnary, EVar
from .errors import ArithmeticFailure, StaticError, TypeFailure
from .functions import BUILTINS, LibraryRegistry
from .values import (BOOLEAN, LIST, SET, STRING, compare, fresh_null, is_null,
                     is_numeric, to_string, values_equal, vtype)


class EvalContext:
    """Everything an expression needs beyond its own syntax."""

    __slots__ = ("bindings", "libs", "skolem", "agg_sink", "rule")

    def __init__(self, bindings=None, libs=None, skolem=None, agg_sink=None, rule=None):
        self.bindings = bindings if bindings is not None else {}
        self.libs = libs if libs is not None else LibraryRegistry()
        self.skolem = skolem if skolem is not None else {}
        self.agg_sink = agg_sink
        self.rule = rule


def evaluate(expr, ctx):
    kind = expr.__class__
    if kind is EConst:
        return expr.value
    if kind is EVar:
        try:
            return ctx.bindings[expr.name]
        except KeyError:
            raise StaticError("variable %s is not bound where it is used" % expr.name)
    if kind is EBinary:
        return _binary(expr, ctx)
    if kind is EUnary:
        return _unary(expr, ctx)
    if kind is ECall:
        return _call(expr, ctx)
    if kind is ESkolem:
        return _skolem(expr, ctx)
    if kind is EAgg:
        if ctx.agg_sink is None:
            raise StaticError("aggregation %s is only allowed in an assignment" % expr.op)
        return ctx.agg_sink(expr, ctx)
    raise StaticError("cannot evaluate expression %r" % (expr,))


# --------------------------------------------------------------------------- #
# Operators
# --------------------------------------------------------------------------- #

_COMPARISONS = {"==", "!=", "<>", "<", "<=", ">", ">="}


def _binary(expr, ctx):
    op = expr.op
    if op == "&&":
        left = _boolean(evaluate(expr.left, ctx), op)
        return left and _boolean(evaluate(expr.right, ctx), op)
    if op == "||":
        left = _boolean(evaluate(expr.left, ctx), op)
        return left or _boolean(evaluate(expr.right, ctx), op)

    a = evaluate(expr.left, ctx)
    b = evaluate(expr.right, ctx)

    if op in _COMPARISONS:
        return compare_values(op, a, b)
    if op == "+":
        return _plus(a, b)
    if op == "-":
        if vtype(a) == SET and vtype(b) == SET:
            return frozenset(set(a) - set(b))
        return _arith("-", a, b)
    if op in ("*", "/"):
        return _arith(op, a, b)
    if op == "|":
        return _setop("|", a, b)
    if op == "&":
        return _setop("&", a, b)
    raise StaticError("unknown operator %r" % op)


def compare_values(op, a, b):
    """Comparison shared by expressions (sec. 4.3) and filters (sec. 4.1)."""
    if op in ("==", "=", "!=", "<>"):
        eq = values_equal(a, b)
        return eq if op in ("==", "=") else not eq
    if is_null(a) or is_null(b):
        if not (is_null(a) and is_null(b)):
            return False
    c = compare(a, b)
    if op == "<":
        return c < 0
    if op == "<=":
        return c <= 0
    if op == ">":
        return c > 0
    if op == ">=":
        return c >= 0
    raise StaticError("unknown comparison %r" % op)


def _plus(a, b):
    ta, tb = vtype(a), vtype(b)
    if ta == LIST or tb == LIST:
        la = a if ta == LIST else (a,)
        lb = b if tb == LIST else (b,)
        return tuple(la) + tuple(lb)
    if ta == STRING or tb == STRING:
        return to_string(a) + to_string(b)
    return _arith("+", a, b)


def _arith(op, a, b):
    if not (is_numeric(a) and is_numeric(b)):
        raise TypeFailure("operator %r is not defined on %s and %s" % (op, vtype(a), vtype(b)))
    if op == "+":
        r = a + b
    elif op == "-":
        r = a - b
    elif op == "*":
        r = a * b
    else:
        if b == 0:
            raise ArithmeticFailure("division by zero")
        if isinstance(a, int) and isinstance(b, int):
            # Both operands integral: the result stays integral and truncates
            # toward zero.  A double on either side
            # upcasts the whole operation (SPECIFICATION.md sec. 4.3).
            q = abs(a) // abs(b)
            r = -q if (a < 0) != (b < 0) else q
        else:
            r = a / b
    if isinstance(r, float):
        if r != r:
            raise ArithmeticFailure("operation produced NaN")
        if r == 0.0:
            r = 0.0
    return r


def _setop(op, a, b):
    if vtype(a) != SET or vtype(b) != SET:
        raise TypeFailure("operator %r requires two sets, got %s and %s"
                          % (op, vtype(a), vtype(b)))
    return frozenset(set(a) | set(b)) if op == "|" else frozenset(set(a) & set(b))


def _unary(expr, ctx):
    v = evaluate(expr.operand, ctx)
    if expr.op == "!":
        return not _boolean(v, "!")
    if not is_numeric(v):
        raise TypeFailure("unary minus is not defined on %s" % vtype(v))
    return -v


def _boolean(v, op):
    if vtype(v) != BOOLEAN:
        raise TypeFailure("operator %r requires a boolean, got %s" % (op, vtype(v)))
    return bool(v)


# --------------------------------------------------------------------------- #
# Calls
# --------------------------------------------------------------------------- #

def _call(expr, ctx):
    args = [evaluate(a, ctx) for a in expr.args]
    resolved = ctx.libs.resolve(expr.name)
    if resolved is not None:
        libname, fn, impl = resolved
        if impl is None:
            raise StaticError("library %r has no function %r" % (libname, fn))
        return impl(args)
    impl = BUILTINS.get(expr.name)
    if impl is not None:
        return impl(args)
    if ":" in expr.name:
        alias = expr.name.rpartition(":")[0] + ":"
        raise StaticError("no library is imported under the alias %r; "
                          "add @library(\"%s\", \"...\")." % (alias, alias))
    raise StaticError("unknown function %r; built-in operators are %s"
                      % (expr.name, ", ".join(sorted(k for k in BUILTINS if not k.startswith("__")))))


def _skolem(expr, ctx):
    args = tuple(evaluate(a, ctx) for a in expr.args)
    key = (expr.name, args)
    null = ctx.skolem.get(key)
    if null is None:
        null = fresh_null()
        ctx.skolem[key] = null
    return null
