"""`@post` directives (SPECIFICATION.md sec. 9)."""

import re

from .errors import StaticError
from .instance import has_null
from .values import sort_key

_CALL = re.compile(r"^\s*(\w+)\s*(?:\(\s*(.*?)\s*\))?\s*$", re.S)


class Directive:
    __slots__ = ("name", "positions", "group", "limit", "raw")

    def __init__(self, name, positions=(), group=(), limit=None, raw=""):
        self.name = name
        self.positions = positions
        self.group = group
        self.limit = limit
        self.raw = raw

    def __repr__(self):
        return self.raw or self.name


def parse_directive(text, line=None, source=None):
    match = _CALL.match(text)
    if not match:
        raise StaticError("cannot parse post-processing directive %r" % text,
                          line=line, source=source)
    name = match.group(1).lower()
    body = (match.group(2) or "").strip()

    if name in ("unique", "certain"):
        return Directive(name, raw=text)
    if name in ("limit", "prelimit"):
        return Directive(name, limit=int(body), raw=text)
    if name in ("orderby", "min", "max"):
        positions = tuple(int(p.strip()) for p in body.split(",") if p.strip())
        if not positions:
            raise StaticError("%s needs at least one position" % name,
                              line=line, source=source)
        return Directive(name, positions=positions, raw=text)
    if name in ("argmin", "argmax"):
        inner = re.match(r"^\s*(-?\d+)\s*,\s*<(.*)>\s*$", body)
        if not inner:
            raise StaticError("%s expects `%s(p, <p1,...,pn>)`" % (name, name),
                              line=line, source=source)
        target = int(inner.group(1))
        group = tuple(int(p.strip()) for p in inner.group(2).split(",") if p.strip())
        return Directive(name, positions=(target,), group=group, raw=text)
    raise StaticError("unknown post-processing directive %r" % name,
                      line=line, source=source)


def apply_all(facts, directives):
    """`prelimit` first, then the remaining directives in order (sec. 9)."""
    rows = list(facts)
    for d in directives:
        if d.name == "prelimit":
            rows = rows[:d.limit]
    for d in directives:
        if d.name != "prelimit":
            rows = _apply(rows, d)
    return rows


def _apply(rows, d):
    if d.name == "unique":
        return list(dict.fromkeys(rows))
    if d.name == "certain":
        return [r for r in rows if not has_null(r)]
    if d.name == "limit":
        return rows[:d.limit]
    if d.name == "orderby":
        return _order_by(rows, d.positions)
    if d.name in ("min", "max"):
        return _extremal(rows, d.positions, d.name == "max")
    if d.name in ("argmin", "argmax"):
        return _arg_extremal(rows, d.positions[0], d.group, d.name == "argmax")
    raise StaticError("unknown post-processing directive %r" % d.name)


def _idx(rows, pos):
    i = abs(pos) - 1
    if rows and i >= len(rows[0]):
        raise StaticError("position %d is out of range for an arity-%d relation"
                          % (abs(pos), len(rows[0])))
    return i


def _order_by(rows, positions):
    out = list(rows)
    for pos in reversed(positions):
        i = _idx(out, pos)
        out.sort(key=lambda t, i=i: sort_key(t[i]), reverse=pos < 0)
    return out


def _extremal(rows, positions, maximise):
    if not rows:
        return rows
    idxs = [_idx(rows, p) for p in positions]
    others = [i for i in range(len(rows[0])) if i not in idxs]
    groups = {}
    for t in rows:
        gkey = tuple(sort_key(t[i]) for i in others)
        groups.setdefault(gkey, []).append(t)
    out = []
    for _gkey, members in groups.items():
        best = None
        for t in members:
            key = tuple(sort_key(t[i]) for i in idxs)
            if best is None or (key > best if maximise else key < best):
                best = key
        out.extend(t for t in members
                   if tuple(sort_key(t[i]) for i in idxs) == best)
    return out


def _arg_extremal(rows, target, group, maximise):
    if not rows:
        return rows
    ti = _idx(rows, target)
    gidx = [_idx(rows, p) for p in group]
    groups = {}
    for t in rows:
        groups.setdefault(tuple(sort_key(t[i]) for i in gidx), []).append(t)
    out = []
    for _gkey, members in groups.items():
        best = None
        for t in members:
            key = sort_key(t[ti])
            if best is None or (key > best if maximise else key < best):
                best = key
        out.extend(t for t in members if sort_key(t[ti]) == best)
    return out
