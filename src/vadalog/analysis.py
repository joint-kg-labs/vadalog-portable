"""Static analysis: arity, condition classification, safety, stratification.

SPECIFICATION.md sec. 5.1, 5.2, 5.4, 5.5, 6.2.
"""

import itertools

from .ast import (EAgg, EBinary, ECall, EConst, ESkolem, EUnary, EVar, EGD,
                  FAILURE, NONMONOTONIC_AGGS, TGD, Var)
from .errors import StaticError

_uid = itertools.count(1)

_MONOTONIC_LIB_MAP = {"sum": "msum", "prod": "mprod", "count": "mcount",
                      "min": "mmin", "max": "mmax", "union": "munion"}


# --------------------------------------------------------------------------- #
# Expression walking
# --------------------------------------------------------------------------- #

def walk(expr):
    """Yield every sub-expression, parents before children."""
    yield expr
    cls = expr.__class__
    if cls is EBinary:
        yield from walk(expr.left)
        yield from walk(expr.right)
    elif cls is EUnary:
        yield from walk(expr.operand)
    elif cls in (ECall, ESkolem):
        for a in expr.args:
            yield from walk(a)
    elif cls is EAgg:
        yield from walk(expr.operand)


def expr_vars(expr):
    return {e.name for e in walk(expr) if e.__class__ is EVar}


def rewrite(expr, fn):
    """Bottom-up rewrite; `fn` maps an expression to its replacement."""
    cls = expr.__class__
    if cls is EBinary:
        expr.left = rewrite(expr.left, fn)
        expr.right = rewrite(expr.right, fn)
    elif cls is EUnary:
        expr.operand = rewrite(expr.operand, fn)
    elif cls in (ECall, ESkolem):
        expr.args = [rewrite(a, fn) for a in expr.args]
    elif cls is EAgg:
        expr.operand = rewrite(expr.operand, fn)
    return fn(expr)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

class Analysis:
    def __init__(self):
        self.arity = {}
        self.strata = []              # list[list[Rule]]
        self.stratum_of = {}          # predicate -> stratum index
        self.constraints = []         # EGD and FAILURE rules
        self.warnings = []
        self.idb = set()
        self.edb = set()
        self.recursive = set()        # predicates that depend on themselves


def analyse(program, libs, inputs=(), outputs=(), stratified=True):
    info = Analysis()
    _collect_arities(program, info, inputs, outputs)
    for rule in program.rules:
        _prepare_rule(rule, libs, info)
    if stratified:
        _stratify(program, info)
    else:
        stratify_flat(program, info)
    return info


def _note_arity(info, name, arity, where):
    known = info.arity.get(name)
    if known is None:
        info.arity[name] = arity
    elif known != arity:
        raise StaticError("predicate %r is used with arity %d and with arity %d"
                          % (name, known, arity),
                          line=getattr(where, "line", None))


def _collect_arities(program, info, inputs, outputs):
    for name, values, line, source, _anns in program.facts:
        _note_arity(info, name, len(values), None)
    for rule in program.rules:
        for atom in rule.head:
            _note_arity(info, atom.name, atom.arity, atom)
            info.idb.add(atom.name)
        for lit in rule.body:
            _note_arity(info, lit.atom.name, lit.atom.arity, lit.atom)
    for name in list(info.arity):
        if name not in info.idb:
            info.edb.add(name)
    for name in inputs:
        info.edb.add(name)


# --------------------------------------------------------------------------- #
# Per-rule preparation
# --------------------------------------------------------------------------- #

def _prepare_rule(rule, libs, info):
    positive = rule.positive
    negative = rule.negative

    body_vars = set()
    for atom in positive:
        body_vars.update(atom.variables())
    rule.body_vars = body_vars

    neg_vars = set()
    for atom in negative:
        neg_vars.update(atom.variables())

    head_vars = []
    for atom in rule.head:
        for t in atom.terms:
            if isinstance(t, Var) and t.name not in head_vars:
                head_vars.append(t.name)

    # -- monotonic library calls become aggregates ------------------------- #
    for cond in rule.conditions:
        cond.expr = rewrite(cond.expr, lambda e: _lift_monotonic(e, libs, rule))

    # -- assignments vs filters (sec. 4.1) --------------------------------- #
    # `X = expr` is an assignment exactly when X has no binding in a positive
    # body atom: it then either fills a head position, or introduces a local
    # value that later conditions can test (`W = m:sum(...), W > 0.5`).
    assigned = set()
    for cond in rule.conditions:
        cond.is_assignment = (cond.op == "=" and cond.var not in body_vars)
        if cond.is_assignment:
            if cond.var in assigned:
                raise StaticError("variable %s is assigned twice in the same rule"
                                  % cond.var, line=rule.line, source=rule.source)
            assigned.add(cond.var)

    rule.assignments = [c for c in rule.conditions if c.is_assignment]
    rule.filters = [c for c in rule.conditions if not c.is_assignment]
    rule.existential_vars = [v for v in head_vars
                             if v not in body_vars and v not in assigned]

    # -- safety (sec. 5.2) ------------------------------------------------- #
    for v in rule.existential_vars:
        if v in neg_vars:
            raise StaticError(
                "head variable %s is bound only inside a negated literal" % v,
                line=rule.line, source=rule.source)
    if rule.kind == EGD:
        for v in rule.egd_vars:
            if v not in body_vars:
                raise StaticError("EGD variable %s does not occur in the body" % v,
                                  line=rule.line, source=rule.source)
    for cond in rule.filters:
        if cond.var not in body_vars and cond.var not in assigned:
            raise StaticError("condition variable %s is not bound in the body"
                              % cond.var, line=rule.line, source=rule.source)
        unknown = expr_vars(cond.expr) - body_vars - assigned
        if unknown:
            raise StaticError("condition uses unbound variable(s) %s"
                              % ", ".join(sorted(unknown)),
                              line=rule.line, source=rule.source)

    _order_assignments(rule, body_vars)

    # -- aggregates (sec. 6) ------------------------------------------------ #
    group_by = sorted(v for v in head_vars if v in body_vars)
    head_name = rule.head[0].name if rule.head else None
    aggregates = []
    for cond in rule.conditions:
        pos = -1
        if rule.head:
            for i, t in enumerate(rule.head[0].terms):
                if isinstance(t, Var) and t.name == cond.var:
                    pos = i
                    break
        for e in walk(cond.expr):
            if e.__class__ is EAgg:
                e.head_pred = head_name
                e.head_pos = pos
                e.uid = next(_uid)
                if not e.explicit_group_by:
                    e.group_by = list(group_by)
                aggregates.append(e)
    rule.aggregates = aggregates

    for agg in aggregates:
        unknown = (expr_vars(agg.operand) | set(agg.contributors) | set(agg.group_by)) - body_vars
        if unknown:
            raise StaticError("aggregate %s uses unbound variable(s) %s"
                              % (agg.op, ", ".join(sorted(unknown))),
                              line=rule.line, source=rule.source)
        if not any(c.is_assignment and agg in list(walk(c.expr)) for c in rule.conditions):
            raise StaticError("aggregate %s must appear in an assignment to a head "
                              "variable" % agg.op, line=rule.line, source=rule.source)

    # -- literal order: negatives last (BodyLiteralsNegComparator) ---------- #
    rule.body = [l for l in rule.body if not l.negated] + \
                [l for l in rule.body if l.negated]


def _lift_monotonic(expr, libs, rule):
    """Turn `m:sum(X,[K],[C])` and friends into aggregation nodes (sec. 6.1)."""
    if expr.__class__ is not ECall:
        return expr
    resolved = libs.resolve(expr.name)
    if resolved is None or resolved[0] != "monotonic":
        return expr
    fn = resolved[1]
    op = _MONOTONIC_LIB_MAP.get(fn)
    if op is None:
        raise StaticError("the monotonic library has no function %r" % fn,
                          line=rule.line, source=rule.source)
    args = expr.args
    if fn in ("sum", "prod", "union"):
        if len(args) != 3:
            raise StaticError("%s expects (value, [group-by], [contributors])" % fn,
                              line=rule.line, source=rule.source)
        agg = EAgg(op, args[0], _var_names(args[2], fn, rule))
        agg.group_by = _var_names(args[1], fn, rule)
    elif fn == "count":
        agg = EAgg(op, EConst(1), [])
        agg.group_by = [a.name for a in args if a.__class__ is EVar]
    else:                                              # min / max
        if not args:
            raise StaticError("%s expects (value, key...)" % fn,
                              line=rule.line, source=rule.source)
        agg = EAgg(op, args[0], [])
        agg.group_by = [a.name for a in args[1:] if a.__class__ is EVar]
    agg.explicit_group_by = True
    return agg


def _var_names(expr, fn, rule):
    if expr.__class__ is EConst and expr.value == ():
        return []
    if expr.__class__ is ECall and expr.name == "__list__":
        names = []
        for a in expr.args:
            if a.__class__ is not EVar:
                raise StaticError("%s expects a list of variables" % fn,
                                  line=rule.line, source=rule.source)
            names.append(a.name)
        return names
    raise StaticError("%s expects a bracketed list of variables" % fn,
                      line=rule.line, source=rule.source)


def _order_assignments(rule, body_vars):
    """Topologically order assignments; report cycles."""
    pending = list(rule.assignments)
    available = set(body_vars)
    ordered = []
    while pending:
        progressed = False
        for cond in list(pending):
            if expr_vars(cond.expr) <= available:
                ordered.append(cond)
                available.add(cond.var)
                pending.remove(cond)
                progressed = True
        if not progressed:
            names = ", ".join(sorted(c.var for c in pending))
            raise StaticError("assignments to %s form a cycle or use unbound variables"
                              % names, line=rule.line, source=rule.source)
    rule.assignments = ordered


# --------------------------------------------------------------------------- #
# Stratification (sec. 5.4, 6.2)
# --------------------------------------------------------------------------- #

def _stratify(program, info):
    preds = set(info.arity)
    edges = []                      # (from, to, weight, reason)

    for rule in program.rules:
        if rule.kind in (EGD, FAILURE):
            info.constraints.append(rule)
            continue
        heavy = any(a.op in NONMONOTONIC_AGGS for a in rule.aggregates)
        heads = [a.name for a in rule.head]
        for lit in rule.body:
            w = 1 if (lit.negated or heavy) else 0
            reason = "negation" if lit.negated else (
                "non-monotonic aggregate" if heavy else "")
            for h in heads:
                edges.append((lit.atom.name, h, w, reason))
        for a, b in zip(heads, heads[1:]):              # keep multi-heads together
            edges.append((a, b, 0, ""))
            edges.append((b, a, 0, ""))

    level = {p: 0 for p in preds}
    n = len(preds) + 1
    for _ in range(n):
        changed = False
        for src, dst, w, _reason in edges:
            if level[dst] < level[src] + w:
                level[dst] = level[src] + w
                changed = True
        if not changed:
            break
    else:
        bad = [(s, d, r) for s, d, w, r in edges if w and level[d] <= level[s]]
        culprit = _first_rule_on(program, bad)
        raise StaticError(
            "the program is not stratifiable: %s. Rewrite it, or pass "
            "--allow-unstratified to evaluate it against the instance available "
            "at each activation." % _negative_cycle(edges, level),
            line=getattr(culprit, "line", None),
            source=getattr(culprit, "source", None))

    info.recursive = _recursive_predicates(edges)
    info.stratum_of = level
    top = max(level.values()) if level else 0
    info.strata = [[] for _ in range(top + 1)]
    for rule in program.rules:
        if rule.kind in (EGD, FAILURE):
            continue
        s = max(level[a.name] for a in rule.head)
        info.strata[s].append(rule)


def _first_rule_on(program, bad_edges):
    """A rule that carries one of the offending dependencies, for the diagnostic."""
    wanted = {(src, dst) for src, dst, _r in bad_edges}
    for rule in program.rules:
        if rule.kind != TGD:
            continue
        for atom in rule.head:
            for lit in rule.body:
                if (lit.atom.name, atom.name) in wanted:
                    return rule
    return None


def _recursive_predicates(edges):
    """Predicates that depend on themselves, directly or transitively.

    Only these need the isomorphism check during the chase: a non-recursive
    predicate can only ever derive finitely many facts, so suppressing an
    isomorphic copy there would lose answers without buying termination.

    A predicate reaches itself exactly when it carries a self-loop or sits in a
    strongly connected component of more than one node, so one pass of Tarjan's
    algorithm answers the question for every predicate at once -- linear in the
    dependency graph, where a search per predicate is quadratic and dominates
    the analysis of a program with a thousand rules.
    """
    succ = {}
    recursive = set()
    for src, dst, _w, _r in edges:
        succ.setdefault(src, []).append(dst)
        succ.setdefault(dst, [])
        if src == dst:
            recursive.add(src)

    index = {}
    low = {}
    onstack = set()
    stack = []
    counter = 0
    for root in succ:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        onstack.add(root)
        work = [(root, iter(succ[root]))]
        while work:
            node, it = work[-1]
            descended = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    onstack.add(nxt)
                    work.append((nxt, iter(succ[nxt])))
                    descended = True
                    break
                if nxt in onstack and index[nxt] < low[node]:
                    low[node] = index[nxt]
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                if low[node] < low[parent]:
                    low[parent] = low[node]
            if low[node] == index[node]:
                component = []
                while True:
                    top = stack.pop()
                    onstack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                if len(component) > 1:
                    recursive.update(component)
    return recursive


def _negative_cycle(edges, level):
    bad = sorted({"%s -> %s (%s)" % (s, d, r or "recursion")
                  for s, d, w, r in edges if w and level[d] <= level[s]})
    return "; ".join(bad[:5]) if bad else "a cycle carries a negative dependency"


def stratify_flat(program, info):
    """Single-stratum fallback used with --allow-unstratified (sec. 5.4).

    Negation is then evaluated against whatever the instance holds at the moment
    of the activation, so the result may depend on evaluation order.
    """
    info.strata = [[r for r in program.rules if r.kind == TGD]]
    info.constraints = [r for r in program.rules if r.kind in (EGD, FAILURE)]
    info.stratum_of = {p: 0 for p in info.arity}
    edges = [(lit.atom.name, atom.name, 0, "")
             for rule in program.rules if rule.kind == TGD
             for atom in rule.head for lit in rule.body]
    info.recursive = _recursive_predicates(edges)
    info.warnings.append(
        "evaluating without stratification: results may depend on rule order")
    return info
