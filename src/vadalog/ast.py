"""Abstract syntax of a Vadalog program (SPECIFICATION.md sec. 3, 4, 5)."""

from .values import format_value

# --------------------------------------------------------------------------- #
# Terms
# --------------------------------------------------------------------------- #


class Term:
    __slots__ = ()


class Const(Term):
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return format_value(self.value)


class Var(Term):
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, Var) and other.name == self.name

    def __hash__(self):
        return hash(("var", self.name))

    def __repr__(self):
        return self.name


# --------------------------------------------------------------------------- #
# Expressions
# --------------------------------------------------------------------------- #


class Expr:
    __slots__ = ()


class EConst(Expr):
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return format_value(self.value)


class EVar(Expr):
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


class EUnary(Expr):
    __slots__ = ("op", "operand")

    def __init__(self, op, operand):
        self.op = op
        self.operand = operand

    def __repr__(self):
        return "%s%r" % (self.op, self.operand)


class EBinary(Expr):
    __slots__ = ("op", "left", "right")

    def __init__(self, op, left, right):
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self):
        return "(%r %s %r)" % (self.left, self.op, self.right)


class ECall(Expr):
    """A built-in operator or an imported library function."""

    __slots__ = ("name", "args")

    def __init__(self, name, args):
        self.name = name
        self.args = args

    def __repr__(self):
        return "%s(%s)" % (self.name, ",".join(repr(a) for a in self.args))


class ESkolem(Expr):
    __slots__ = ("name", "args")

    def __init__(self, name, args):
        self.name = name
        self.args = args

    def __repr__(self):
        return "#%s(%s)" % (self.name, ",".join(repr(a) for a in self.args))


class EAgg(Expr):
    """An aggregation.  `group_by`, `head_pred` and `head_pos` are filled in by
    the analyser (SPECIFICATION.md sec. 6.1)."""

    __slots__ = ("op", "operand", "contributors", "group_by", "head_pred",
                 "head_pos", "explicit_group_by", "uid")

    def __init__(self, op, operand, contributors):
        self.op = op
        self.operand = operand
        self.contributors = contributors      # list of variable names
        self.group_by = []                    # list of variable names
        self.head_pred = None
        self.head_pos = -1
        self.explicit_group_by = False
        self.uid = None

    @property
    def agg_id(self):
        # Aggregation state is keyed on (function, head predicate,
        # head position), so two rules writing the same aggregated position of
        # the same predicate share one accumulator.  Aggregates that reach no
        # head position fall back to a per-occurrence identity.
        if self.head_pred is not None:
            return (self.op, self.head_pred, self.head_pos)
        return (self.op, None, self.uid)

    def __repr__(self):
        c = ",<%s>" % ",".join(self.contributors) if self.contributors else ""
        return "%s(%r%s)" % (self.op, self.operand, c)


MONOTONIC_AGGS = {"msum", "mprod", "mcount", "munion", "mmin", "mmax"}
NONMONOTONIC_AGGS = {"min", "max", "count", "sum", "prod", "avg", "set", "list", "union"}
AGGREGATES = MONOTONIC_AGGS | NONMONOTONIC_AGGS
INCREASING_AGGS = {"msum", "mcount", "munion", "mmax"}


# --------------------------------------------------------------------------- #
# Atoms, literals, conditions
# --------------------------------------------------------------------------- #


class Atom:
    __slots__ = ("name", "terms", "line")

    def __init__(self, name, terms, line=None):
        self.name = name
        self.terms = terms
        self.line = line

    @property
    def arity(self):
        return len(self.terms)

    def variables(self):
        return [t.name for t in self.terms if isinstance(t, Var)]

    def __repr__(self):
        if not self.terms:
            return self.name
        return "%s(%s)" % (self.name, ",".join(repr(t) for t in self.terms))


class Literal:
    __slots__ = ("atom", "negated")

    def __init__(self, atom, negated=False):
        self.atom = atom
        self.negated = negated

    def __repr__(self):
        return ("not " if self.negated else "") + repr(self.atom)


class Condition:
    """`VAR op expr`, later classified as a filter or an assignment."""

    __slots__ = ("var", "op", "expr", "is_assignment")

    def __init__(self, var, op, expr):
        self.var = var                        # variable name (str)
        self.op = op
        self.expr = expr
        self.is_assignment = False

    def __repr__(self):
        return "%s %s %r" % (self.var, self.op, self.expr)


# --------------------------------------------------------------------------- #
# Rules and programs
# --------------------------------------------------------------------------- #

TGD, EGD, FAILURE = "tgd", "egd", "failure"


class Rule:
    __slots__ = ("kind", "head", "body", "conditions", "annotations", "line",
                 "source", "egd_vars", "filters", "assignments", "aggregates",
                 "existential_vars", "body_vars", "index")

    def __init__(self, kind, head, body, conditions, line=None, source=None):
        self.kind = kind
        self.head = head                      # list[Atom]; [] for EGD/FAILURE
        self.body = body                      # list[Literal]
        self.conditions = conditions          # list[Condition]
        self.annotations = []
        self.line = line
        self.source = source
        self.egd_vars = None                  # (str, str) for EGD rules
        self.filters = []                     # filled by the analyser
        self.assignments = []
        self.aggregates = []
        self.existential_vars = []
        self.body_vars = set()
        self.index = 0

    @property
    def positive(self):
        return [l.atom for l in self.body if not l.negated]

    @property
    def negative(self):
        return [l.atom for l in self.body if l.negated]

    def head_predicates(self):
        return [a.name for a in self.head]

    def __repr__(self):
        if self.kind == EGD:
            h = "%s=%s" % self.egd_vars
        elif self.kind == FAILURE:
            h = "#F"
        else:
            h = ",".join(repr(a) for a in self.head)
        parts = [repr(l) for l in self.body] + [repr(c) for c in self.conditions]
        return "%s :- %s." % (h, ", ".join(parts))


class Annotation:
    __slots__ = ("name", "args", "line", "source")

    def __init__(self, name, args, line=None, source=None):
        self.name = name
        self.args = args                      # list of values
        self.line = line
        self.source = source

    def __repr__(self):
        if not self.args:
            return "@%s." % self.name
        return "@%s(%s)." % (self.name, ",".join(format_value(a) for a in self.args))


class Program:
    def __init__(self):
        self.rules = []                       # list[Rule]
        self.facts = []                       # list[(name, tuple_of_values, line)]
        self.annotations = []                 # list[Annotation]
        self.sources = []                     # files loaded, in order
        self.parameters = None                # params.ParamReport of the load

    def add_rule(self, rule):
        rule.index = len(self.rules)
        self.rules.append(rule)

    def annotations_named(self, name):
        return [a for a in self.annotations if a.name == name]
