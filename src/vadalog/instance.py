"""The fact store: relations, indexes, canonical forms.

SPECIFICATION.md sec. 2.3, 2.4, 7.3, 7.4, 7.6.

Relations keep facts in **insertion order** (Python dicts are ordered).  That
makes evaluation deterministic without imposing an artificial sort, and it means
base facts are consumed in the order they appear in the program -- which is what
monotonic aggregates rely on.
"""

from .values import MarkedNull

_CANON_NULLS = []


def _canon_null(i):
    while len(_CANON_NULLS) <= i:
        _CANON_NULLS.append(MarkedNull("$%d" % len(_CANON_NULLS)))
    return _CANON_NULLS[i]


def canonical(tup):
    """Rename marked nulls to $0, $1, ... in order of first occurrence.

    Two facts are isomorphic exactly when their canonical forms are equal.
    """
    mapping = None
    out = None
    for i, v in enumerate(tup):
        if isinstance(v, MarkedNull):
            if mapping is None:
                mapping = {}
                out = list(tup)
            slot = mapping.get(v.name)
            if slot is None:
                slot = _canon_null(len(mapping))
                mapping[v.name] = slot
            out[i] = slot
    return tup if out is None else tuple(out)


def has_null(tup):
    return any(isinstance(v, MarkedNull) for v in tup)


ALL, DELTA, OLD = "all", "delta", "old"


class Relation:
    __slots__ = ("name", "arity", "facts", "delta", "pending", "canon",
                 "_index", "_delta_index", "_old")

    def __init__(self, name, arity):
        self.name = name
        self.arity = arity
        self.facts = {}            # tuple -> None, insertion ordered
        self.delta = {}            # added in the previous round: drives semi-naive
        self.pending = {}          # added in the current round
        self.canon = set()
        self._index = {}           # positions -> key -> [tuple], over `facts`
        self._delta_index = {}     # the same over `delta`, rebuilt once a round
        self._old = None           # facts minus delta, for unkeyed scans

    # -- mutation ---------------------------------------------------------- #

    def add(self, tup, isomorphism_check=True):
        """Insert a fact.  Returns True when it was genuinely new."""
        if tup in self.facts:
            return False
        if isomorphism_check:
            c = canonical(tup)
            if c in self.canon:
                return False
            self.canon.add(c)
        self.facts[tup] = None
        self.pending[tup] = None
        # Indexes over `facts` are append-only: extend the ones already built
        # rather than dropping them, so a round costs what it adds and not what
        # the relation already holds (SPECIFICATION.md sec. 7.3).
        for positions, idx in self._index.items():
            idx.setdefault(tuple(tup[p] for p in positions), []).append(tup)
        self._old = None
        return True

    def reset(self):
        self.facts = {}
        self.pending = {}
        self.delta = {}
        self.canon = set()
        self._index = {}
        self._delta_index = {}
        self._old = None

    def start_round(self, new_delta):
        """Make `new_delta` the driving delta and open a fresh pending set."""
        self.delta = {t: None for t in new_delta}
        self.pending = {}
        self._delta_index = {}
        self._old = None

    def advance(self):
        self.start_round(self.pending)

    # -- access ------------------------------------------------------------ #

    def source(self, which):
        if which == ALL:
            return self.facts
        if which == DELTA:
            return self.delta
        delta = self.delta
        if not delta:
            return self.facts
        old = self._old
        if old is None:
            old = self._old = [t for t in self.facts if t not in delta]
        return old

    def ordered(self, which=ALL):
        return list(self.source(which))

    def _bucket(self, positions, key):
        """The facts matching `key` at `positions`, over the whole relation."""
        idx = self._index.get(positions)
        if idx is None:
            idx = {}
            for t in self.facts:
                idx.setdefault(tuple(t[p] for p in positions), []).append(t)
            self._index[positions] = idx
        return idx.get(key, ())

    def _delta_bucket(self, positions, key):
        idx = self._delta_index.get(positions)
        if idx is None:
            idx = {}
            for t in self.delta:
                idx.setdefault(tuple(t[p] for p in positions), []).append(t)
            self._delta_index[positions] = idx
        return idx.get(key, ())

    def lookup(self, which, positions, key):
        """Facts whose values at `positions` equal `key`, in insertion order."""
        if not positions:
            return self.source(which)
        if which == DELTA:
            return self._delta_bucket(positions, key)
        bucket = self._bucket(positions, key)
        if which == ALL or not bucket or not self.delta:
            return bucket
        # OLD is ALL minus the delta.  The delta facts carrying this very key
        # are what has to come out, and usually there are none: one lookup in
        # the (small) delta index decides it, where materialising the whole
        # complement would cost the relation.
        hot = self._delta_bucket(positions, key)
        if not hot:
            return bucket
        if len(hot) >= len(bucket):
            return ()
        if len(hot) > 4:
            hot = set(hot)
        return [t for t in bucket if t not in hot]

    def __len__(self):
        return len(self.facts)


class Instance:
    def __init__(self, arities=None):
        self.rels = {}
        self.arities = dict(arities or {})
        self._total = 0

    def relation(self, name, arity=None):
        rel = self.rels.get(name)
        if rel is None:
            if arity is None:
                arity = self.arities.get(name, 0)
            rel = Relation(name, arity)
            self.rels[name] = rel
        return rel

    def add(self, name, tup, isomorphism_check=True):
        if self.relation(name, len(tup)).add(tup, isomorphism_check):
            self._total += 1
            return True
        return False

    def contains(self, name, tup):
        rel = self.rels.get(name)
        return rel is not None and tup in rel.facts

    def clear_deltas(self):
        for rel in self.rels.values():
            rel.start_round(())

    def promote_all_to_delta(self):
        for rel in self.rels.values():
            rel.start_round(list(rel.facts))

    def total(self):
        """The number of facts, maintained incrementally.

        The chase asks for it once per derived fact, to enforce `--max-facts`,
        so summing over the relations here would cost O(relations) per fact.
        """
        return self._total

    def recount(self):
        """Recompute the running total after facts are rewritten in place."""
        self._total = sum(len(r) for r in self.rels.values())
        return self._total
