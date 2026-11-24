"""Built-in operators and importable function libraries (SPECIFICATION.md sec. 4.4, 11)."""

import hashlib
import math as _math
import random as _random
import re

from .errors import ArithmeticFailure, StaticError, TypeFailure
from .values import (BOOLEAN, DATE, DOUBLE, INT, LIST, SET, STRING, UNKNOWN,
                     compare, is_null, is_numeric, to_string, values_equal, vtype)

_rng = _random.Random(0)


def seed_rng(seed):
    global _rng
    _rng = _random.Random(seed)


def _need(name, args, lo, hi=None):
    hi = lo if hi is None else hi
    if not (lo <= len(args) <= (hi if hi >= 0 else len(args))):
        raise TypeFailure("%s expects %s arguments, got %d"
                          % (name, lo if lo == hi else "%d..%d" % (lo, hi), len(args)))


def _as_num(name, v):
    if not is_numeric(v):
        raise TypeFailure("%s expects a number, got %s" % (name, vtype(v)))
    return v


def _as_str(name, v):
    if vtype(v) != STRING:
        raise TypeFailure("%s expects a string, got %s" % (name, vtype(v)))
    return v


def _as_seq(name, v):
    t = vtype(v)
    if t not in (LIST, SET):
        raise TypeFailure("%s expects a list or a set, got %s" % (name, t))
    return v


# --------------------------------------------------------------------------- #
# Always-available operators (sec. 4.4)
# --------------------------------------------------------------------------- #

def _substring(args):
    _need("substring", args, 3)
    s, a, b = args
    a = int(_as_num("substring", a))
    b = int(_as_num("substring", b))
    if vtype(s) == LIST:
        return tuple(s[a:b])
    return _as_str("substring", s)[a:b]


def _contains(args):
    _need("contains", args, 2)
    s, x = args
    t = vtype(s)
    if t == LIST:
        return any(values_equal(e, x) for e in s)
    if t == SET:
        return any(values_equal(e, x) for e in s)
    return _as_str("contains", x) in _as_str("contains", s)


def _starts_with(args):
    _need("starts_with", args, 2)
    s, p = args
    if vtype(s) == LIST:
        p = p if vtype(p) == LIST else (p,)
        return len(p) <= len(s) and all(values_equal(a, b) for a, b in zip(s[:len(p)], p))
    return _as_str("starts_with", s).startswith(_as_str("starts_with", p))


def _ends_with(args):
    _need("ends_with", args, 2)
    s, p = args
    if vtype(s) == LIST:
        p = p if vtype(p) == LIST else (p,)
        return len(p) <= len(s) and all(values_equal(a, b) for a, b in zip(s[len(s) - len(p):], p))
    return _as_str("ends_with", s).endswith(_as_str("ends_with", p))


def _concat(args):
    _need("concat", args, 2)
    a, b = args
    if vtype(a) == LIST or vtype(b) == LIST:
        la = a if vtype(a) == LIST else (a,)
        lb = b if vtype(b) == LIST else (b,)
        return tuple(la) + tuple(lb)
    return to_string(a) + to_string(b)


def _index_of(args):
    _need("index_of", args, 2)
    return _as_str("index_of", args[0]).find(_as_str("index_of", args[1]))


def _string_length(args):
    _need("string_length", args, 1)
    v = args[0]
    if vtype(v) in (LIST, SET):
        return len(v)
    return len(_as_str("string_length", v))


BUILTINS = {
    "substring": _substring,
    "contains": _contains,
    "starts_with": _starts_with,
    "ends_with": _ends_with,
    "concat": _concat,
    "index_of": _index_of,
    "string_length": _string_length,
    "__list__": lambda args: tuple(args),
    "__set__": lambda args: frozenset(args),
}


# --------------------------------------------------------------------------- #
# math
# --------------------------------------------------------------------------- #

def _guard(x):
    if isinstance(x, float) and x != x:
        raise ArithmeticFailure("operation produced NaN")
    return x


def _math_min(args):
    if not args:
        raise TypeFailure("min expects at least one argument")
    best = args[0]
    for v in args[1:]:
        if compare(v, best) < 0:
            best = v
    return best


def _math_max(args):
    if not args:
        raise TypeFailure("max expects at least one argument")
    best = args[0]
    for v in args[1:]:
        if compare(v, best) > 0:
            best = v
    return best


def _log(args):
    if len(args) == 1:
        return _guard(_math.log(_as_num("log", args[0])))
    _need("log", args, 2)
    base = _as_num("log", args[0])
    if base in (0, 1):
        raise ArithmeticFailure("log base cannot be 0 or 1")
    return _guard(_math.log(_as_num("log", args[1]), base))


MATH = {
    "mod": lambda a: int(_as_num("mod", a[0])) % int(_as_num("mod", a[1])),
    "sqrt": lambda a: _guard(_math.sqrt(_as_num("sqrt", a[0]))),
    "abs": lambda a: abs(_as_num("abs", a[0])),
    "min": _math_min,
    "max": _math_max,
    "log10": lambda a: _guard(_math.log10(_as_num("log10", a[0]))),
    "log": _log,
    "pow": lambda a: _guard(float(_as_num("pow", a[0]) ** _as_num("pow", a[1]))),
    "exp": lambda a: _guard(_math.exp(_as_num("exp", a[0]))),
    "round": lambda a: int(_math.floor(_as_num("round", a[0]) + 0.5)),
    "ceil": lambda a: int(_math.ceil(_as_num("ceil", a[0]))),
    "floor": lambda a: int(_math.floor(_as_num("floor", a[0]))),
    "sin": lambda a: _math.sin(_as_num("sin", a[0])),
    "cos": lambda a: _math.cos(_as_num("cos", a[0])),
    "tan": lambda a: _math.tan(_as_num("tan", a[0])),
    "PI": lambda a: _math.pi,
    "E": lambda a: _math.e,
    "rand": lambda a: _rng.random(),
}


# --------------------------------------------------------------------------- #
# collections
# --------------------------------------------------------------------------- #

def _c_get(args):
    _need("get", args, 2)
    seq = _as_seq("get", args[0])
    return tuple(seq)[int(_as_num("get", args[1]))]


def _c_set(args):
    _need("set", args, 3)
    seq = list(_as_seq("set", args[0]))
    seq[int(_as_num("set", args[1]))] = args[2]
    return tuple(seq)


def _c_join(args):
    _need("join", args, 2, 4)
    seq = _as_seq("join", args[0])
    sep = _as_str("join", args[1])
    pre = _as_str("join", args[2]) if len(args) > 2 else ""
    post = _as_str("join", args[3]) if len(args) > 3 else ""
    items = list(seq) if vtype(seq) == LIST else sorted(seq, key=to_string)
    return pre + sep.join(to_string(x) for x in items) + post


def _c_add(args):
    _need("add", args, 2)
    coll = _as_seq("add", args[0])
    if vtype(coll) == SET:
        return frozenset(set(coll) | {args[1]})
    return tuple(coll) + (args[1],)


def _c_remove(args):
    _need("remove", args, 2)
    coll = _as_seq("remove", args[0])
    kept = [x for x in coll if not values_equal(x, args[1])]
    return frozenset(kept) if vtype(coll) == SET else tuple(kept)


def _c_remove_at(args):
    _need("removeAt", args, 2)
    seq = list(_as_seq("removeAt", args[0]))
    del seq[int(_as_num("removeAt", args[1]))]
    return tuple(seq)


def _c_union(args):
    _need("union", args, 2)
    a, b = _as_seq("union", args[0]), _as_seq("union", args[1])
    if vtype(a) == LIST and vtype(b) == LIST:
        return tuple(a) + tuple(b)
    return frozenset(set(a) | set(b))


def _c_intersection(args):
    _need("intersection", args, 2)
    a, b = _as_seq("intersection", args[0]), _as_seq("intersection", args[1])
    keep = [x for x in a if any(values_equal(x, y) for y in b)]
    return frozenset(keep) if vtype(a) == SET else tuple(keep)


def _c_difference(args):
    _need("difference", args, 2)
    a, b = _as_seq("difference", args[0]), _as_seq("difference", args[1])
    keep = [x for x in a if not any(values_equal(x, y) for y in b)]
    return frozenset(keep) if vtype(a) == SET else tuple(keep)


def _c_parse(as_set):
    def go(args):
        _need("parse", args, 1)
        raw = _as_str("parse", args[0])
        items = tuple(p.strip() for p in raw.split(",")) if raw.strip() else ()
        return frozenset(items) if as_set else items
    return go


COLLECTIONS = {
    "size": lambda a: len(_as_seq("size", a[0])),
    "contains": _contains,
    "containsAll": lambda a: all(any(values_equal(x, y) for y in _as_seq("containsAll", a[0]))
                                 for x in _as_seq("containsAll", a[1])),
    "get": _c_get,
    "set": _c_set,
    "subList": lambda a: tuple(_as_seq("subList", a[0]))[int(a[1]):int(a[2])],
    "sort": lambda a: tuple(sorted(_as_seq("sort", a[0]), key=to_string)),
    "asList": lambda a: tuple(sorted(a[0], key=to_string)) if vtype(a[0]) == SET else tuple(a[0]),
    "asSet": lambda a: frozenset(_as_seq("asSet", a[0])),
    "join": _c_join,
    "add": _c_add,
    "remove": _c_remove,
    "removeAt": _c_remove_at,
    "union": _c_union,
    "intersection": _c_intersection,
    "difference": _c_difference,
    "parse_set": _c_parse(True),
    "parse_list": _c_parse(False),
}


# --------------------------------------------------------------------------- #
# nullManagement / datatypes / hashCode
# --------------------------------------------------------------------------- #

NULLMANAGEMENT = {
    "isnull": lambda a: is_null(a[0]),
    "ifnull": lambda a: a[1] if is_null(a[0]) else a[2],
    "coalesce": lambda a: a[0] if (not is_null(a[0]) or is_null(a[1])) else a[1],
}


def _instance_of(args):
    _need("instanceOf", args, 2)
    return vtype(args[0]) == {"integer": INT, "int": INT, "double": DOUBLE,
                              "string": STRING, "boolean": BOOLEAN, "date": DATE,
                              "set": SET, "list": LIST, "unknown": UNKNOWN
                              }.get(_as_str("instanceOf", args[1]).lower())


DATATYPES = {
    "isInt": lambda a: vtype(a[0]) == INT,
    "isInteger": lambda a: vtype(a[0]) == INT,
    "isDouble": lambda a: vtype(a[0]) == DOUBLE,
    "isString": lambda a: vtype(a[0]) == STRING,
    "isBoolean": lambda a: vtype(a[0]) == BOOLEAN,
    "isDate": lambda a: vtype(a[0]) == DATE,
    "isSet": lambda a: vtype(a[0]) == SET,
    "isList": lambda a: vtype(a[0]) == LIST,
    "instanceOf": _instance_of,
}


def _hash_with(algo):
    def go(args):
        h = hashlib.new(algo)
        for a in args:
            h.update(to_string(a).encode("utf-8"))
        return h.hexdigest()
    return go


HASHCODE = {name: _hash_with(algo) for name, algo in (
    ("md5", "md5"), ("sha", "sha1"), ("sha224", "sha224"), ("sha256", "sha256"),
    ("sha384", "sha384"), ("sha512", "sha512"))}
HASHCODE["javaHashCode"] = lambda a: _java_hash("".join(to_string(x) for x in a))


def _java_hash(s):
    h = 0
    for ch in s:
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    return h - 0x100000000 if h >= 0x80000000 else h


# --------------------------------------------------------------------------- #
# regex
# --------------------------------------------------------------------------- #

_FLAGS = {"MULTILINE": re.MULTILINE, "CASE_INSENSITIVE": re.IGNORECASE,
          "DOTALL": re.DOTALL, "UNICODE_CASE": re.UNICODE, "COMMENTS": re.VERBOSE}


def _compile(pattern, params):
    flags = 0
    if params:
        for part in _as_str("regex", params).split("|"):
            key = part.strip().upper()
            if not key:
                continue
            if key not in _FLAGS:
                raise TypeFailure("unknown regex flag %r" % key)
            flags |= _FLAGS[key]
    try:
        return re.compile(_as_str("regex", pattern), flags)
    except re.error as exc:
        raise TypeFailure("invalid regular expression %r: %s" % (pattern, exc))


def _re_matches(a):
    _need("matches", a, 2, 3)
    return _compile(a[1], a[2] if len(a) > 2 else None).fullmatch(_as_str("matches", a[0])) is not None


def _re_contains(a):
    _need("contains", a, 2, 3)
    return _compile(a[1], a[2] if len(a) > 2 else None).search(_as_str("contains", a[0])) is not None


def _re_replace(count):
    def go(a):
        _need("replace", a, 3, 4)
        rx = _compile(a[1], a[3] if len(a) > 3 else None)
        return rx.sub(_as_str("replace", a[2]).replace("\\", "\\\\"),
                      _as_str("replace", a[0]), count=count)
    return go


def _re_remove(count):
    def go(a):
        _need("remove", a, 2, 3)
        rx = _compile(a[1], a[2] if len(a) > 2 else None)
        return rx.sub("", _as_str("remove", a[0]), count=count)
    return go


REGEX = {
    "matches": _re_matches,
    "contains": _re_contains,
    "replaceFirst": _re_replace(1),
    "replaceAll": _re_replace(0),
    "removeFirst": _re_remove(1),
    "removeAll": _re_remove(0),
}


LIBRARIES = {
    "math": MATH,
    "collections": COLLECTIONS,
    "nullManagement": NULLMANAGEMENT,
    "datatypes": DATATYPES,
    "regex": REGEX,
    "hashCode": HASHCODE,
    "monotonic": {},        # handled by the aggregation machinery, sec. 6.1
}

MONOTONIC_LIBRARY_FUNCTIONS = {"sum", "prod", "count", "min", "max"}


class LibraryRegistry:
    """Resolves `alias:function` names against the imported libraries."""

    def __init__(self):
        self.by_alias = {}          # alias -> (library name, {fn: impl} or single fn name)
        self.single = {}            # alias -> (library name, fn name)

    def add(self, annotation):
        args = annotation.args
        if len(args) < 2:
            raise StaticError("@library takes an alias and a library name",
                              line=annotation.line, source=annotation.source)
        alias, libname = str(args[0]), str(args[1])
        if libname not in LIBRARIES:
            raise StaticError(
                "unknown library %r; this engine provides: %s"
                % (libname, ", ".join(sorted(LIBRARIES))),
                line=annotation.line, source=annotation.source)
        if len(args) >= 3:
            fn = str(args[2])
            if libname != "monotonic" and fn not in LIBRARIES[libname]:
                raise StaticError("library %r has no function %r" % (libname, fn),
                                  line=annotation.line, source=annotation.source)
            self.single[alias] = (libname, fn)
        else:
            self.by_alias[alias] = libname

    def resolve(self, name):
        """Return (library_name, function_name, impl) or None."""
        if name in self.single:
            libname, fn = self.single[name]
            return libname, fn, LIBRARIES[libname].get(fn)
        if ":" in name:
            alias, _, fn = name.rpartition(":")
            alias += ":"
            libname = self.by_alias.get(alias)
            if libname is None:
                libname = self.by_alias.get(alias[:-1])
            if libname is not None:
                return libname, fn, LIBRARIES[libname].get(fn)
        return None
