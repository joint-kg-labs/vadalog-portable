"""Equality-generating dependencies: union-find over marked nulls.

SPECIFICATION.md sec. 5.5.
"""

from .errors import UnificationFailure
from .values import MarkedNull, is_null, values_equal


def _rank(name):
    if name.startswith("z") and name[1:].isdigit():
        return (0, int(name[1:]))
    return (1, name)


class Equalities:
    """Tracks which marked nulls have been equated, and to which constants."""

    def __init__(self):
        self.parent = {}
        self.witness = {}          # root name -> constant it was equated with
        self.version = 0

    def _find(self, name):
        root = name
        while True:
            nxt = self.parent.get(root)
            if nxt is None or nxt == root:
                break
            root = nxt
        # path compression
        cur = name
        while cur != root:
            nxt = self.parent.get(cur, cur)
            self.parent[cur] = root
            cur = nxt
        return root

    def resolve(self, value):
        """Map a value to its current representative."""
        if not is_null(value):
            return value
        if not self.parent and not self.witness:
            return value
        root = self._find(value.name)
        const = self.witness.get(root)
        if const is not None:
            return const
        return value if root == value.name else MarkedNull(root)

    def resolve_tuple(self, tup):
        if not self.parent and not self.witness:
            return tup
        out = None
        for i, v in enumerate(tup):
            if is_null(v):
                r = self.resolve(v)
                if r is not v and not (is_null(r) and r.name == v.name):
                    if out is None:
                        out = list(tup)
                    out[i] = r
        return tup if out is None else tuple(out)

    # -- learning equalities ------------------------------------------------ #

    def equate(self, a, b, rule=None):
        """Apply one EGD activation.  Returns True when something changed."""
        if a is b and a == a:
            # A key EGD matches every fact with itself; on the diagonal there is
            # nothing to equate, and resolving both sides would say so the long
            # way round.  `a == a` keeps the one value that is not equal to
            # itself, a NaN, on the slow path, where it still fails as before.
            return False
        a = self.resolve(a)
        b = self.resolve(b)
        na, nb = is_null(a), is_null(b)

        if not na and not nb:
            if values_equal(a, b):
                return False
            raise UnificationFailure(
                "EGD tried to equate the distinct constants %r and %r" % (a, b),
                line=getattr(rule, "line", None), source=getattr(rule, "source", None))

        if na and nb:
            ra, rb = self._find(a.name), self._find(b.name)
            if ra == rb:
                return False
            keep, drop = (ra, rb) if _rank(ra) <= _rank(rb) else (rb, ra)
            self.parent[drop] = keep
            wd = self.witness.pop(drop, None)
            wk = self.witness.get(keep)
            if wd is not None:
                if wk is None:
                    self.witness[keep] = wd
                elif not values_equal(wk, wd):
                    raise UnificationFailure(
                        "EGD merged two nulls already equated to the distinct "
                        "constants %r and %r" % (wk, wd),
                        line=getattr(rule, "line", None),
                        source=getattr(rule, "source", None))
            self.version += 1
            return True

        null, const = (a, b) if na else (b, a)
        root = self._find(null.name)
        existing = self.witness.get(root)
        if existing is not None:
            if values_equal(existing, const):
                return False
            raise UnificationFailure(
                "EGD tried to equate the distinct constants %r and %r"
                % (existing, const),
                line=getattr(rule, "line", None), source=getattr(rule, "source", None))
        self.witness[root] = const
        self.version += 1
        return True

    @property
    def active(self):
        return bool(self.parent) or bool(self.witness)
