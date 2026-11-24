"""Value model: data types, marked nulls, ordering, conversion.

SPECIFICATION.md sec. 2 and sec. 4.5.

Carriers
    string   -> str
    integer  -> int
    double   -> float
    date     -> datetime.datetime (naive, UTC)
    boolean  -> bool
    set      -> frozenset
    list     -> tuple
    null     -> MarkedNull

`bool` is a subclass of `int` in Python, so every type test checks `bool` first.
"""

import datetime
import itertools

from .errors import TypeFailure

# --------------------------------------------------------------------------- #
# Marked nulls
# --------------------------------------------------------------------------- #

_null_counter = itertools.count(1)


class MarkedNull:
    """An identity token for an unknown value (SPECIFICATION.md sec. 2.2)."""

    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, MarkedNull) and other.name == self.name

    def __hash__(self):
        return hash(("#null", self.name))

    def __repr__(self):
        return self.name

    __str__ = __repr__


def fresh_null():
    """Mint a new marked null named z1, z2, ... from the global counter."""
    return MarkedNull("z%d" % next(_null_counter))


def reset_nulls():
    """Restart null numbering. Called once per program run for determinism."""
    global _null_counter
    _null_counter = itertools.count(1)


def is_null(v):
    return isinstance(v, MarkedNull)


# --------------------------------------------------------------------------- #
# Type tags
# --------------------------------------------------------------------------- #

STRING, INT, DOUBLE, DATE, BOOLEAN, SET, LIST, UNKNOWN = (
    "string", "int", "double", "date", "boolean", "set", "list", "unknown")

TYPE_ALIASES = {
    "string": STRING, "str": STRING,
    "int": INT, "integer": INT,
    "double": DOUBLE, "float": DOUBLE,
    "date": DATE,
    "boolean": BOOLEAN, "bool": BOOLEAN,
    "set": SET, "list": LIST,
    "unknown": UNKNOWN, "null": UNKNOWN,
}


def vtype(v):
    if isinstance(v, MarkedNull):
        return UNKNOWN
    if isinstance(v, bool):
        return BOOLEAN
    if isinstance(v, int):
        return INT
    if isinstance(v, float):
        return DOUBLE
    if isinstance(v, str):
        return STRING
    if isinstance(v, datetime.datetime):
        return DATE
    if isinstance(v, frozenset):
        return SET
    if isinstance(v, tuple):
        return LIST
    raise TypeFailure("value of unsupported kind: %r" % (v,))


def is_numeric(v):
    return (not isinstance(v, bool)) and isinstance(v, (int, float))


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #

_RANK = {UNKNOWN: 0, BOOLEAN: 1, INT: 2, DOUBLE: 2, DATE: 3,
         STRING: 4, SET: 5, LIST: 6}


def sort_key(v):
    """A total order over all values, used to make evaluation deterministic."""
    t = vtype(v)
    r = _RANK[t]
    if t == UNKNOWN:
        return (r, _null_sort_key(v.name))
    if t == BOOLEAN:
        return (r, 1 if v else 0)
    if t in (INT, DOUBLE):
        return (r, float(v))
    if t == DATE:
        return (r, v.timestamp() if v.year > 1 else 0.0, v.isoformat())
    if t == STRING:
        return (r, v)
    if t == SET:
        return (r, tuple(sorted((sort_key(x) for x in v), key=repr)))
    return (r, tuple(sort_key(x) for x in v))


def _null_sort_key(name):
    """Order nulls z1 < z2 < ... < z10 numerically rather than lexically."""
    if name.startswith("z") and name[1:].isdigit():
        return (0, int(name[1:]))
    return (1, name)


def compare(a, b):
    """Three-way comparison of two values of compatible type.

    Raises TypeFailure when the types cannot be compared.  Marked nulls compare
    only with marked nulls (SPECIFICATION.md sec. 2.2, 4.3).
    """
    ta, tb = vtype(a), vtype(b)
    if ta == UNKNOWN or tb == UNKNOWN:
        if ta == tb:
            return _cmp(_null_sort_key(a.name), _null_sort_key(b.name))
        raise TypeFailure("cannot compare a marked null with a %s" % (tb if ta == UNKNOWN else ta))
    if is_numeric(a) and is_numeric(b):
        return _cmp(float(a), float(b))
    if ta != tb:
        raise TypeFailure("cannot compare %s with %s" % (ta, tb))
    if ta == BOOLEAN:
        return _cmp(int(a), int(b))
    if ta in (STRING, DATE):
        return _cmp(a, b)
    if ta == SET:
        return _cmp(sorted((sort_key(x) for x in a), key=repr),
                    sorted((sort_key(x) for x in b), key=repr))
    return _cmp([sort_key(x) for x in a], [sort_key(x) for x in b])


def _cmp(a, b):
    return -1 if a < b else (1 if a > b else 0)


def values_equal(a, b):
    """Equality used by comparison operators: never raises, unlike `compare`."""
    ta, tb = vtype(a), vtype(b)
    if ta == UNKNOWN or tb == UNKNOWN:
        return ta == tb and a.name == b.name
    if is_numeric(a) and is_numeric(b):
        return float(a) == float(b)
    if ta != tb:
        return False
    return a == b


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #

def to_string(v):
    """The `toString` used by `+` upcasting and by CSV/JSON output."""
    t = vtype(v)
    if t == STRING:
        return v
    if t == UNKNOWN:
        return v.name
    if t == BOOLEAN:
        return "#T" if v else "#F"
    if t == INT:
        return str(v)
    if t == DOUBLE:
        return format_double(v)
    if t == DATE:
        return format_date(v)
    if t == SET:
        return "{" + ",".join(to_string(x) for x in sorted(v, key=sort_key)) + "}"
    return "[" + ",".join(to_string(x) for x in v) + "]"


def format_double(v):
    if v != v:
        return "NaN"
    if v == float("inf"):
        return "+inf"
    if v == float("-inf"):
        return "-inf"
    if v == int(v) and abs(v) < 1e16:
        return "%.1f" % v
    return repr(v)


def format_date(v):
    if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0):
        return v.strftime("%Y-%m-%d")
    return v.strftime("%Y-%m-%d %H:%M:%S")


def parse_date(text):
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise TypeFailure("not a valid date literal: %r" % text)


_ESCAPES = {'"': '"', "\\": "\\", "'": "'", "b": "\b", "t": "\t",
            "n": "\n", "f": "\f", "r": "\r"}


def unescape_string(raw):
    """Decode the body of a STRING token (quotes already stripped)."""
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '"' and i + 1 < n and raw[i + 1] == '"':
            out.append('"')
            i += 2
            continue
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt == "u" and i + 5 < n + 1:
            try:
                out.append(chr(int(raw[i + 2:i + 6], 16)))
                i += 6
                continue
            except ValueError:
                pass
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def escape_string(text):
    out = []
    for c in text:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        else:
            out.append(c)
    return "".join(out)


def format_value(v):
    """Render a value as a Vadalog literal, for `--format facts` output."""
    t = vtype(v)
    if t == STRING:
        return '"%s"' % escape_string(v)
    if t == SET:
        return "{" + ",".join(format_value(x) for x in sorted(v, key=sort_key)) + "}"
    if t == LIST:
        return "[" + ",".join(format_value(x) for x in v) + "]"
    return to_string(v)


def format_fact(name, args):
    if not args:
        return "%s." % name
    return "%s(%s)." % (name, ",".join(format_value(a) for a in args))


def coerce_to(text, type_name):
    """Parse a CSV field into the declared type (SPECIFICATION.md sec. 10.3)."""
    t = TYPE_ALIASES.get(type_name.lower())
    if t is None:
        raise TypeFailure("unknown column type %r" % type_name)
    if t == STRING:
        return text
    text = text.strip()
    if t == INT:
        return int(text)
    if t == DOUBLE:
        return float(text)
    if t == BOOLEAN:
        low = text.lower()
        if low in ("#t", "true", "t", "1", "yes"):
            return True
        if low in ("#f", "false", "f", "0", "no"):
            return False
        raise TypeFailure("not a boolean: %r" % text)
    if t == DATE:
        return parse_date(text)
    raise TypeFailure("column type %r cannot be read from CSV" % type_name)
