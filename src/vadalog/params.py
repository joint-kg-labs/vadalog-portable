"""Parameterised programs (SPECIFICATION.md sec. 11.8).

A program may contain placeholders `${name}`, filled in when it is loaded.
The substitution is done by the lexer, token by token, not on the raw text:

* where a term is expected, the placeholder becomes exactly one literal
  token (integer, double, string, date or boolean), so a value can never
  change the shape of the program;
* inside a string literal, the value is spliced into the string's content
  (this is how `@bind` paths and `@output` names are parameterised);
  `$${` writes a literal `${`.

This module holds what the lexer needs and nothing more: validation of the
supplied values, parsing of values written as Vadalog literals (the CLI's
`-p NAME=VALUE`, the web UI's parameter fields) or as JSON, and the report
that records which placeholders a load met.
"""

import datetime
import json
import math
import re

from .errors import ParameterError
from .values import escape_string, to_string

_NAME = re.compile(r"[A-Za-z0-9_]+\Z")

KINDS = "an integer, a double, a \"string\", a date, #T or #F"


def is_name(name):
    return isinstance(name, str) and bool(_NAME.match(name))


def check_value(name, value):
    """Validate one supplied value and return it in the engine's representation."""
    if not is_name(name):
        raise ParameterError("%r is not a valid parameter name (letters, digits "
                             "and underscores only)" % (name,), names=[str(name)])
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ParameterError("parameter %s: %r is not a finite number"
                                 % (name, value), names=[name])
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    raise ParameterError("parameter %s: a value must be %s, not %s"
                         % (name, KINDS, type(value).__name__), names=[name])


def normalize(params):
    """Validate a mapping of supplied values; None means no parameters."""
    if not params:
        return {}
    if not isinstance(params, dict):
        raise ParameterError("parameters must be given as a mapping of names to values")
    return {name: check_value(name, value) for name, value in params.items()}


def string_text(value):
    """The text a value contributes to the body of a string literal (escaped)."""
    return escape_string(value if isinstance(value, str) else to_string(value))


# --------------------------------------------------------------------------- #
# Values written as text
# --------------------------------------------------------------------------- #

def parse_literal(text, name="?"):
    """Read one Vadalog literal: `42`, `-0.5`, `"Acme"`, `2024-01-01`, `#T`."""
    from . import lexer as lx                      # lexer imports this module
    from .errors import LexError
    from .values import parse_date, unescape_string

    def refuse():
        raise ParameterError("parameter %s: %r is not a Vadalog literal; write %s "
                             "(strings in double quotes)" % (name, text, KINDS),
                             names=[name])

    try:
        tokens = lx.tokenize(text)[:-1]            # drop EOF
    except (LexError, ParameterError):
        refuse()
    sign = 1
    if len(tokens) == 2 and tokens[0].kind == lx.OP and tokens[0].text == "-" \
            and tokens[1].kind in (lx.INTEGER, lx.DOUBLE):
        sign, tokens = -1, tokens[1:]
    if len(tokens) != 1:
        refuse()
    t = tokens[0]
    if t.kind == lx.INTEGER:
        return sign * int(t.text)
    if t.kind == lx.DOUBLE:
        return sign * float(t.text)
    if t.kind == lx.STRING:
        return unescape_string(t.text)
    if t.kind == lx.DATE:
        return parse_date(t.text)
    if t.kind in (lx.TRUE, lx.FALSE):
        return t.value
    refuse()


def parse_assignment(text):
    """`NAME=VALUE`, VALUE a Vadalog literal, as given to `-p`."""
    name, sep, value = text.partition("=")
    name = name.strip()
    if not sep or not is_name(name):
        raise ParameterError("expected NAME=VALUE, got %r" % text)
    return name, parse_literal(value.strip(), name)


def parse_string_assignment(text):
    """`NAME=TEXT`, TEXT taken verbatim as a string, as given to `-s`."""
    name, sep, value = text.partition("=")
    name = name.strip()
    if not sep or not is_name(name):
        raise ParameterError("expected NAME=TEXT, got %r" % text)
    return name, value


def parse_literals(mapping):
    """A mapping of names to literal texts (the web UI's parameter fields)."""
    if not isinstance(mapping, dict):
        raise ParameterError("parameters must be given as a mapping of names to values")
    out = {}
    for name, text in mapping.items():
        if not is_name(name):
            check_value(name, None)                # raises the naming error
        if not isinstance(text, str):
            raise ParameterError("parameter %s: expected the literal as text" % name,
                                 names=[name])
        out[name] = parse_literal(text.strip(), name)
    return out


def load_json(path):
    """A JSON object of names to values; JSON strings are strings."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        from .errors import DataSourceError
        raise DataSourceError("cannot read parameter file %s: %s" % (path, exc.strerror))
    except ValueError as exc:
        raise ParameterError("parameter file %s is not valid JSON: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ParameterError("parameter file %s must hold a JSON object" % path)
    return normalize(data)


# --------------------------------------------------------------------------- #
# What a load met
# --------------------------------------------------------------------------- #

class ParamReport:
    """Placeholders met while loading one program and its @include-d files."""

    def __init__(self, params=None):
        self.params = normalize(params)
        self.terms = {}            # name -> (source, line, col) of first use as a term
        self.strings = {}          # name -> (source, line, col) of first use in a string
        self.missing = {}          # term placeholders with no value

    def value(self, name):
        return self.params.get(name)

    def has(self, name):
        return name in self.params

    def met_term(self, name, source, line, col):
        self.terms.setdefault(name, (source, line, col))
        if name not in self.params:
            self.missing.setdefault(name, (source, line, col))

    def met_string(self, name, source, line, col):
        self.strings.setdefault(name, (source, line, col))

    def names(self):
        """Every placeholder name met, in order of first appearance."""
        seen = dict(self.terms)
        for name, where in self.strings.items():
            seen.setdefault(name, where)
        return list(seen)

    def unused(self):
        met = set(self.terms) | set(self.strings)
        return sorted(name for name in self.params if name not in met)

    def raise_if_missing(self):
        if not self.missing:
            return
        names = list(self.missing)
        source, line, col = self.missing[names[0]]
        raise ParameterError(
            "missing value for parameter%s %s"
            % ("" if len(names) == 1 else "s", ", ".join(names)),
            line=line, col=col, source=source, names=names)

    def describe(self):
        """One line per placeholder, for `vadalog check`."""
        lines = []
        for name in self.names():
            if name in self.params:
                state = "= %s" % _show(self.params[name])
            elif name in self.terms:
                state = "(no value)"
            else:
                state = "(no value; left as written inside strings)"
            lines.append("  ${%s} %s" % (name, state))
        return lines


def _show(value):
    from .values import format_value
    return format_value(value)
