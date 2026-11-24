"""The chase: semi-naive evaluation with isomorphism-based termination.

SPECIFICATION.md sec. 7.
"""

import time

from .aggregates import AggregationTable, combine, dedupe_by_contributors
from .ast import Const, EGD, FAILURE, NONMONOTONIC_AGGS
from .egd import Equalities
from .errors import ReasoningFailure, ResourceExceeded, StaticError
from .expressions import EvalContext, compare_values, evaluate
from .instance import ALL, DELTA, OLD, Instance
from .values import fresh_null


# --------------------------------------------------------------------------- #
# Compiled rule plans (sec. 7.3)
# --------------------------------------------------------------------------- #

class AtomPlan:
    __slots__ = ("name", "key_positions", "key_terms", "bind_positions",
                 "repeat_positions", "filters")

    def __init__(self, name):
        self.name = name
        self.key_positions = ()      # positions matched against known values
        self.key_terms = ()          # Const or variable name for each key position
        self.bind_positions = ()     # (position, variable name) first occurrences
        self.repeat_positions = ()   # (position, earlier position) same var twice
        self.filters = []            # conditions evaluable once this atom is bound


class RulePlan:
    __slots__ = ("rule", "atoms", "negatives", "prefilters", "postfilters",
                 "is_aggregating")

    def __init__(self, rule):
        self.rule = rule
        self.atoms = []
        self.negatives = []
        self.prefilters = []         # conditions needing no body variable
        self.postfilters = []        # conditions over assigned variables
        self.is_aggregating = any(a.op in NONMONOTONIC_AGGS for a in rule.aggregates)


def order_atoms(atoms):
    """The body atoms in source order, with disconnected ones deferred.

    An atom that shares no variable with the atoms before it cannot be looked up
    by a key: the join degenerates into a cartesian product at that point, and
    every tuple of it is carried through the rest of the body.  Taking instead
    the first atom that does share a variable costs nothing and avoids the
    blow-up; measured on the LUBM ontology, an order that breaks the connection
    runs twenty to forty times slower than one that keeps it.

    Source order is preserved wherever it is already connected, which is the
    normal case, so this reorders nothing in a well-written program.  An atom
    with no variables at all yields at most one tuple and counts as connected,
    so it stays where the author put it.  Bodies of fewer than three atoms have
    no freedom to speak of and are returned untouched.

    This is a connectivity rule, not a cost model: among the connected atoms it
    picks the first, never the cheapest, because the sizes it would need for
    that are not known when the plan is compiled.
    """
    if len(atoms) < 3:
        return atoms
    remaining = list(atoms)
    ordered = [remaining.pop(0)]
    bound = set(ordered[0].variables())
    while remaining:
        pick = 0
        for i, atom in enumerate(remaining):
            variables = set(atom.variables())
            if not variables or (variables & bound):
                pick = i
                break
        atom = remaining.pop(pick)
        ordered.append(atom)
        bound.update(atom.variables())
    return ordered


def compile_rule(rule, reorder=True):
    plan = RulePlan(rule)
    bound = set()
    assigned = {c.var for c in rule.assignments}
    remaining = []
    for cond in rule.filters:
        if _condition_vars(cond) & assigned:
            plan.postfilters.append(cond)
        else:
            remaining.append(cond)

    atoms = rule.positive
    if reorder and not rule.aggregates:
        # A monotonic aggregate reads the activations as a stream, so the order
        # in which they are enumerated is part of its result (sec. 6.1): those
        # rules keep the order their author wrote.  `reorder` is off for a whole
        # program that post-processes with `limit`, which picks its rows by
        # insertion order (sec. 9).
        atoms = order_atoms(atoms)
    for atom in atoms:
        ap = AtomPlan(atom.name)
        keys, key_terms, binds, repeats = [], [], [], []
        seen = {}
        for pos, term in enumerate(atom.terms):
            if isinstance(term, Const):
                keys.append(pos)
                key_terms.append(term)
            elif term.name in seen:
                repeats.append((pos, seen[term.name]))
            elif term.name in bound:
                keys.append(pos)
                key_terms.append(term.name)
                seen[term.name] = pos
            else:
                binds.append((pos, term.name))
                seen[term.name] = pos
        ap.key_positions = tuple(keys)
        ap.key_terms = tuple(key_terms)
        ap.bind_positions = tuple(binds)
        ap.repeat_positions = tuple(repeats)
        bound.update(atom.variables())
        for cond in list(remaining):
            if _condition_vars(cond) <= bound:
                ap.filters.append(cond)
                remaining.remove(cond)
        plan.atoms.append(ap)

    if remaining:
        if plan.atoms:
            plan.atoms[-1].filters.extend(remaining)
        else:
            plan.prefilters.extend(remaining)

    for atom in rule.negative:
        plan.negatives.append(atom)
    return plan


def body_signature(rule):
    """A key identifying rules that join exactly the same thing.

    Two rules with the same positive atoms, the same negative atoms and the same
    variable names in the same places enumerate the same matches, so the join can
    be run once for all of them.  A rule carrying conditions or assignments gets
    no signature: those are pushed into the plan and would have to be compared
    too, and the constraints this is meant for do not have any.
    """
    if rule.filters or rule.assignments:
        return None
    shape = []
    for kind, atoms in (("+", rule.positive), ("-", rule.negative)):
        for atom in atoms:
            terms = tuple(("c", t.value) if isinstance(t, Const) else ("v", t.name)
                          for t in atom.terms)
            shape.append((kind, atom.name, terms))
    return tuple(shape)


def _condition_vars(cond):
    from .analysis import expr_vars
    return expr_vars(cond.expr) | {cond.var}


# --------------------------------------------------------------------------- #
# The engine
# --------------------------------------------------------------------------- #

class Chase:
    def __init__(self, program, info, libs, options=None, reorder=True):
        self.reorder = reorder
        self.program = program
        self.info = info
        self.libs = libs
        self.options = options or Options()
        self.instance = Instance(info.arity)
        self.equalities = Equalities()
        self.aggregation = AggregationTable()
        self.skolem = {}
        self.plans = {}
        self.groups = None           # constraints sharing one join
        self.stats = {"rounds": 0, "activations": 0, "facts": 0, "suppressed": 0}
        self._deadline = None

    # -- setup ------------------------------------------------------------- #

    def plan_for(self, rule):
        plan = self.plans.get(id(rule))
        if plan is None:
            plan = compile_rule(rule, self.reorder)
            self.plans[id(rule)] = plan
        return plan

    def load_fact(self, name, values):
        # Base facts are never subject to the termination check: two CSV rows
        # that differ only by distinct marked nulls are two distinct facts.
        self.instance.add(name, tuple(values), isomorphism_check=False)

    # -- driver ------------------------------------------------------------- #

    def run(self):
        if self.options.timeout:
            self._deadline = time.monotonic() + self.options.timeout
        for stratum in self.info.strata:
            self._run_stratum(stratum)
        self.stats["facts"] = self.instance.total()
        return self.instance

    def _run_stratum(self, rules):
        normal = [r for r in rules if not self.plan_for(r).is_aggregating]
        aggregating = [r for r in rules if self.plan_for(r).is_aggregating]
        # Entering a stratum, every fact derived so far is new to its rules.
        self.instance.promote_all_to_delta()
        while True:
            self._fixpoint(normal)
            if not aggregating:
                break
            if not self._full_aggregates(aggregating):
                break
            # Only the facts the aggregate rules just emitted drive the next
            # pass: re-promoting the whole instance would replay the monotonic
            # aggregates and accumulate their state twice.
            self._advance_round()

    def _fixpoint(self, rules):
        any_change = False
        while True:
            self._check_guards()
            self.stats["rounds"] += 1
            produced = []
            for rule in rules:
                produced.extend(self._apply_semi_naive(rule))
            added = False
            for name, tup in produced:
                if self._emit(name, tup):
                    added = True
            constraint_change = self._apply_constraints()
            if not (added or constraint_change):
                break
            any_change = True
            self._advance_round()
            if constraint_change and self.equalities.active:
                # Facts rewritten by an EGD become delta again so that the rules
                # depending on them re-fire; relations left untouched keep the
                # delta they just rotated, so existential rules do not replay.
                self._recanonicalise()
        return any_change

    def _advance_round(self):
        for rel in self.instance.rels.values():
            rel.advance()

    def _emit(self, name, tup):
        tup = self.equalities.resolve_tuple(tup)
        if self.instance.add(name, tup, name in self.info.recursive):
            if self.options.max_facts and self.instance.total() > self.options.max_facts:
                raise ResourceExceeded(
                    "the instance exceeded %d facts; raise --max-facts if the "
                    "program is expected to be this large"
                    % self.options.max_facts)
            return True
        self.stats["suppressed"] += 1
        return False

    def _check_guards(self):
        if self.options.max_rounds and self.stats["rounds"] >= self.options.max_rounds:
            raise ResourceExceeded("stopped after %d chase rounds (--max-rounds)"
                                   % self.options.max_rounds)
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise ResourceExceeded("stopped after %.1fs (--timeout)" % self.options.timeout)

    # -- rule application ----------------------------------------------------- #

    def _apply_semi_naive(self, rule):
        plan = self.plan_for(rule)
        produced = []
        if not plan.atoms:
            for bindings in self._match(plan, 0, -1, {}):
                produced.extend(self._instantiate(rule, bindings))
            return produced
        for delta_at in range(len(plan.atoms)):
            rel = self.instance.rels.get(plan.atoms[delta_at].name)
            if rel is None or not rel.delta:
                continue
            for bindings in self._match(plan, 0, delta_at, {}):
                produced.extend(self._instantiate(rule, bindings))
        return produced

    def _apply_full(self, rule):
        """Enumerate every match over the whole instance (no delta)."""
        plan = self.plan_for(rule)
        return self._match(plan, 0, None, {})

    def _match(self, plan, idx, delta_at, bindings):
        if idx == len(plan.atoms):
            if idx == 0:
                for cond in plan.prefilters:
                    if not self._filter_holds(cond, bindings, plan.rule):
                        return
            if self._negatives_hold(plan, bindings):
                yield dict(bindings)
            return

        ap = plan.atoms[idx]
        rel = self.instance.rels.get(ap.name)
        if rel is None:
            return
        if delta_at is None:
            which = ALL
        elif idx == delta_at:
            which = DELTA
        elif idx < delta_at:
            which = ALL
        else:
            which = OLD

        key = []
        for term in ap.key_terms:
            if isinstance(term, Const):
                key.append(self.equalities.resolve(term.value))
            else:
                key.append(bindings[term])
        candidates = rel.lookup(which, ap.key_positions, tuple(key))

        for tup in candidates:
            ok = True
            for pos, earlier in ap.repeat_positions:
                if tup[pos] != tup[earlier]:
                    ok = False
                    break
            if not ok:
                continue
            for pos, name in ap.bind_positions:
                bindings[name] = tup[pos]
            passed = True
            for cond in ap.filters:
                if not self._filter_holds(cond, bindings, plan.rule):
                    passed = False
                    break
            if passed:
                yield from self._match(plan, idx + 1, delta_at, bindings)
            for _pos, name in ap.bind_positions:
                bindings.pop(name, None)

    def _filter_holds(self, cond, bindings, rule):
        ctx = EvalContext(bindings, self.libs, self.skolem, None, rule)
        value = bindings.get(cond.var)
        if value is None and cond.var not in bindings:
            raise StaticError("condition variable %s is unbound" % cond.var,
                              line=rule.line, source=rule.source)
        rhs = evaluate(cond.expr, ctx)
        if cond.op == "in":
            return _membership(value, rhs)
        if cond.op == "!in":
            return not _membership(value, rhs)
        return compare_values(cond.op, value, rhs)

    def _negatives_hold(self, plan, bindings):
        for atom in plan.negatives:
            rel = self.instance.rels.get(atom.name)
            if rel is None:
                continue
            positions, key = [], []
            free = False
            for pos, term in enumerate(atom.terms):
                if isinstance(term, Const):
                    positions.append(pos)
                    key.append(self.equalities.resolve(term.value))
                elif term.name in bindings:
                    positions.append(pos)
                    key.append(bindings[term.name])
                else:
                    free = True
            hits = rel.lookup(ALL, tuple(positions), tuple(key))
            if free:
                if any(True for _ in hits):
                    return False
            else:
                for _ in hits:
                    return False
        return True

    # -- head construction ----------------------------------------------------- #

    def _instantiate(self, rule, bindings):
        self.stats["activations"] += 1
        if rule.assignments:
            ctx = EvalContext(bindings, self.libs, self.skolem,
                              self._monotonic_sink, rule)
            for cond in rule.assignments:
                bindings[cond.var] = evaluate(cond.expr, ctx)
        for cond in self.plan_for(rule).postfilters:
            if not self._filter_holds(cond, bindings, rule):
                return ()

        if rule.kind == FAILURE:
            raise ReasoningFailure(
                "failure rule fired: %s" % _explain_binding(rule, bindings),
                line=rule.line, source=rule.source)
        if rule.kind == EGD:
            a, b = rule.egd_vars
            self.equalities.equate(bindings[a], bindings[b], rule)
            return ()

        nulls = {v: fresh_null() for v in rule.existential_vars}
        out = []
        for atom in rule.head:
            values = []
            for term in atom.terms:
                if isinstance(term, Const):
                    values.append(term.value)
                elif term.name in bindings:
                    values.append(bindings[term.name])
                else:
                    values.append(nulls[term.name])
            out.append((atom.name, tuple(values)))
        return out

    def _monotonic_sink(self, agg, ctx):
        if agg.op in NONMONOTONIC_AGGS:
            raise StaticError("aggregate %s is evaluated in stratified mode and "
                              "cannot be used here" % agg.op)
        gvals = tuple(ctx.bindings[v] for v in agg.group_by)
        cvals = tuple(ctx.bindings[v] for v in agg.contributors)
        value = evaluate(agg.operand, ctx)
        return self.aggregation.step(agg, gvals, cvals, value)

    # -- stratified aggregates (sec. 6.2) --------------------------------------- #

    def _full_aggregates(self, rules):
        changed = False
        for rule in rules:
            changed |= self._evaluate_aggregate_rule(rule)
        return changed

    def _evaluate_aggregate_rule(self, rule):
        aggs = rule.aggregates
        group_vars = aggs[0].group_by
        groups = {}
        for bindings in self._apply_full(rule):
            gkey = tuple(bindings[v] for v in group_vars)
            slot = groups.get(gkey)
            if slot is None:
                slot = groups[gkey] = {"first": dict(bindings),
                                       "values": {id(a): [] for a in aggs}}
            ctx = EvalContext(bindings, self.libs, self.skolem, None, rule)
            for agg in aggs:
                contrib = tuple(bindings[c] for c in agg.contributors)
                slot["values"][id(agg)].append((contrib, evaluate(agg.operand, ctx)))

        changed = False
        for gkey, slot in groups.items():
            results = {}
            for agg in aggs:
                pairs = slot["values"][id(agg)]
                if agg.contributors:
                    values = dedupe_by_contributors(pairs)
                else:
                    values = [v for _c, v in pairs]
                results[id(agg)] = combine(agg.op, values)
            bindings = slot["first"]
            ctx = EvalContext(bindings, self.libs, self.skolem,
                              lambda a, c: results[id(a)], rule)
            for cond in rule.assignments:
                bindings[cond.var] = evaluate(cond.expr, ctx)
            if any(not self._filter_holds(c, bindings, rule)
                   for c in self.plan_for(rule).postfilters):
                continue
            nulls = {v: fresh_null() for v in rule.existential_vars}
            for atom in rule.head:
                values = []
                for term in atom.terms:
                    if isinstance(term, Const):
                        values.append(term.value)
                    elif term.name in bindings:
                        values.append(bindings[term.name])
                    else:
                        values.append(nulls[term.name])
                if self._emit(atom.name, tuple(values)):
                    changed = True
        return changed

    # -- constraints ------------------------------------------------------------ #

    def _constraint_groups(self):
        """The constraints, with EGDs that share a body collected together.

        The ChaseBench `doctors` scenario states ten EGDs over four distinct
        bodies -- a key constrains three attributes at once, one EGD per
        attribute -- and enumerating each body once instead of once per EGD is
        most of its chase.
        """
        if self.groups is None:
            groups, index = [], {}
            for rule in self.info.constraints:
                sig = body_signature(rule) if rule.kind == EGD else None
                try:
                    slot = index.get(sig) if sig is not None else None
                except TypeError:          # a constant that cannot be hashed
                    sig, slot = None, None
                if slot is None:
                    slot = [self.plan_for(rule), []]
                    if sig is not None:
                        index[sig] = slot
                    groups.append(slot)
                slot[1].append(rule)
            self.groups = groups
        return self.groups

    def _apply_constraints(self):
        before = self.equalities.version
        for plan, rules in self._constraint_groups():
            if len(rules) == 1:
                for _ in self._apply_semi_naive(rules[0]):
                    pass
                continue
            # The shared bindings are never written to: a rule with assignments
            # or conditions is given a group of its own by `body_signature`.
            if not plan.atoms:
                for bindings in self._match(plan, 0, -1, {}):
                    for rule in rules:
                        self._instantiate(rule, bindings)
                continue
            for delta_at in range(len(plan.atoms)):
                rel = self.instance.rels.get(plan.atoms[delta_at].name)
                if rel is None or not rel.delta:
                    continue
                for bindings in self._match(plan, 0, delta_at, {}):
                    for rule in rules:
                        self._instantiate(rule, bindings)
        return self.equalities.version != before

    def _recanonicalise(self):
        """Rewrite the instance through the union-find (sec. 5.5)."""
        changed = False
        for rel in self.instance.rels.values():
            rewritten = []
            touched = []
            differs = False
            for tup in rel.facts:
                new = self.equalities.resolve_tuple(tup)
                if new != tup:
                    differs = True
                    touched.append(new)
                rewritten.append(new)
            if not differs:
                continue
            changed = True
            carried = [self.equalities.resolve_tuple(t) for t in rel.delta]
            rel.reset()
            recursive = rel.name in self.info.recursive
            for tup in rewritten:
                rel.add(tup, recursive)
            # Only the facts the rewriting actually moved -- plus the delta the
            # relation was already carrying -- drive the next round.  A rule
            # match that involves none of them was enumerated before the
            # rewriting and its outcome has not changed, so replaying the whole
            # relation would re-enumerate the entire join for nothing.
            fresh = dict.fromkeys(carried)
            for tup in touched:
                fresh.setdefault(tup, None)
            rel.start_round([t for t in fresh if t in rel.facts])
        if changed:
            # Resolution can merge two facts into one, so the running total of
            # the instance no longer follows from the additions alone.
            self.instance.recount()
        return changed


def _membership(value, container):
    from .values import LIST, SET, vtype, values_equal
    if vtype(container) in (SET, LIST):
        return any(values_equal(value, x) for x in container)
    return False


def _explain_binding(rule, bindings):
    body = ", ".join(repr(l) for l in rule.body)
    shown = ", ".join("%s=%r" % (k, v) for k, v in sorted(bindings.items())
                      if not k.startswith("_"))
    return "#F :- %s  with  %s" % (body, shown or "no bindings")


class Options:
    __slots__ = ("max_facts", "max_rounds", "timeout", "seed", "allow_unstratified",
                 "strict", "stats")

    def __init__(self, max_facts=5_000_000, max_rounds=0, timeout=0.0, seed=0,
                 allow_unstratified=False, strict=False, stats=False):
        self.max_facts = max_facts
        self.max_rounds = max_rounds
        self.timeout = timeout
        self.seed = seed
        self.allow_unstratified = allow_unstratified
        self.strict = strict
        self.stats = stats
