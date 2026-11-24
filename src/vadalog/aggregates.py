"""Aggregation (SPECIFICATION.md sec. 6).

Two families:

* monotonic / streaming -- `msum`, `mprod`, `mcount`, `munion`, `mmin`, `mmax`.
  Kept in an aggregation table: a granular table
  keyed by (aggregate, group-by values, contributor values) holding the best
  contribution so far, and a running table keyed by (aggregate, group-by values).
* non-monotonic / stratified -- `min`, `max`, `count`, `sum`, `prod`, `avg`,
  and the collectors `set`, `list`, `union`.  Evaluated once, over a closed
  body relation.
"""

from .ast import INCREASING_AGGS, NONMONOTONIC_AGGS
from .errors import TypeFailure
from .values import SET, compare, is_numeric, sort_key, vtype

DOUBLE_PRECISION = 10


def _round(v):
    if isinstance(v, float):
        return round(v, DOUBLE_PRECISION)
    return v


class AggregationTable:
    """State for the monotonic aggregates (SPECIFICATION.md sec. 6.1)."""

    def __init__(self):
        self.granular = {}
        self.running = {}

    def reset(self):
        self.granular.clear()
        self.running.clear()

    def step(self, agg, group_values, contributor_values, value):
        op = agg.op
        gkey = (agg.agg_id, group_values, contributor_values)
        rkey = (agg.agg_id, group_values)

        if op in ("mmin", "mmax"):
            current = self.running.get(rkey)
            if current is None:
                new = value
            else:
                better = compare(value, current) > 0 if op == "mmax" else compare(value, current) < 0
                new = value if better else current
            self.running[rkey] = new
            return new

        old_g = self.granular.get(gkey)
        if contributor_values:
            increasing = op in INCREASING_AGGS
            if old_g is None or (compare(value, old_g) >= 0 if increasing
                                 else compare(value, old_g) <= 0):
                self.granular[gkey] = value
        new_g = self.granular.get(gkey, value)

        if op == "munion":
            identity = frozenset()
            old_r = self.running.get(rkey, identity)
            if vtype(new_g) != SET:
                raise TypeFailure("munion aggregates sets, got %s" % vtype(new_g))
            new_r = frozenset(set(old_r) | set(new_g))
        elif op == "mcount":
            old_r = self.running.get(rkey, 0)
            new_r = old_r + 1
        elif op == "msum":
            old_r = self.running.get(rkey, 0)
            base = old_g if old_g is not None else 0
            new_r = _round(_num(old_r) - _num(base) + _num(new_g))
        elif op == "mprod":
            old_r = self.running.get(rkey, 1)
            base = old_g if old_g is not None else 1
            divisor = _num(base)
            if divisor == 0:
                new_r = _num(new_g)
            else:
                new_r = _round(_num(old_r) / divisor * _num(new_g))
        else:
            raise TypeFailure("unknown monotonic aggregate %r" % op)

        self.running[rkey] = new_r
        return new_r


def _num(v):
    if not is_numeric(v):
        raise TypeFailure("aggregation requires a number, got %s" % vtype(v))
    return v


# --------------------------------------------------------------------------- #
# Stratified aggregates (sec. 6.2)
# --------------------------------------------------------------------------- #

def combine(op, values):
    """Fold a closed group of values into the aggregate's result."""
    if op == "count":
        return len(values)
    if not values:
        return None
    if op == "min":
        return _extremum(values, -1)
    if op == "max":
        return _extremum(values, 1)
    if op == "sum":
        return _round(_fold_numeric(values, 0, lambda a, b: a + b))
    if op == "prod":
        return _round(_fold_numeric(values, 1, lambda a, b: a * b))
    if op == "avg":
        total = _fold_numeric(values, 0, lambda a, b: a + b)
        return _round(float(total) / len(values))
    if op == "set":
        return frozenset(values)
    if op == "list":
        return tuple(values)
    if op == "union":
        out = set()
        for v in values:
            if vtype(v) != SET:
                raise TypeFailure("union aggregates sets, got %s" % vtype(v))
            out |= set(v)
        return frozenset(out)
    raise TypeFailure("unknown aggregate %r" % op)


def _extremum(values, sign):
    best = values[0]
    for v in values[1:]:
        if compare(v, best) * sign > 0:
            best = v
    return best


def _fold_numeric(values, identity, fn):
    acc = identity
    for v in values:
        acc = fn(acc, _num(v))
    return acc


def is_nonmonotonic(op):
    return op in NONMONOTONIC_AGGS


def dedupe_by_contributors(pairs):
    """`count(X, <C...>)` counts distinct contributor tuples (sec. 6.2)."""
    seen = {}
    for contrib, value in pairs:
        seen.setdefault(contrib, value)
    return list(seen.values())


def group_sort_key(values):
    return tuple(sort_key(v) for v in values)
