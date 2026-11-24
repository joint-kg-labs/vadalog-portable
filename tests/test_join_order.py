"""Body atom ordering: the connectivity rule (SPECIFICATION.md sec. 7.3).

The engine keeps the order the author wrote wherever that order is already
connected, and defers an atom that shares no variable with the atoms before it.
These tests pin both halves of that: what the rule does when it has something to
offer, and -- more importantly -- that it leaves everything else alone.
"""

import random

import pytest

from harness import assert_answers, run
from vadalog.ast import Atom, Const, Var
from vadalog.chase import Options, compile_rule, order_atoms
from vadalog.program import Runner, load_text


def atom(name, *terms):
    """`atom('p', 'X', 'Y')` -- an upper-case term is a variable, else a constant."""
    return Atom(name, [Var(t) if t[:1].isupper() else Const(t) for t in terms])


def names(atoms):
    return [a.name for a in atoms]


# --------------------------------------------------------------------------- #
# The rule itself
# --------------------------------------------------------------------------- #

CASES = [
    ("already connected",
     [atom('a', 'X', 'Y'), atom('b', 'Y', 'Z'), atom('c', 'Z', 'W')], ['a', 'b', 'c']),
    ("a disconnected atom in the middle is deferred",
     [atom('a', 'X', 'Y'), atom('b', 'P', 'Q'), atom('c', 'Y', 'Z')], ['a', 'c', 'b']),
    ("a disconnected atom at the end stays where it is",
     [atom('a', 'X', 'Y'), atom('b', 'Y', 'Z'), atom('c', 'P', 'Q')], ['a', 'b', 'c']),
    ("the connected atom is taken however far down it sits",
     [atom('a', 'X'), atom('b', 'P'), atom('c', 'Q'), atom('d', 'X', 'P')],
     ['a', 'd', 'b', 'c']),
    ("a chain written backwards is already connected",
     [atom('a', 'Z', 'W'), atom('b', 'Y', 'Z'), atom('c', 'X', 'Y')], ['a', 'b', 'c']),
    ("a product that cannot be avoided keeps the source order",
     [atom('a', 'X'), atom('b', 'P'), atom('c', 'Q')], ['a', 'b', 'c']),
    ("a ground atom counts as connected and does not move",
     [atom('a', 'X'), atom('b', 'k1', 'k2'), atom('c', 'X', 'Y')], ['a', 'b', 'c']),
    ("every atom on the same variable",
     [atom('a', 'X'), atom('b', 'X'), atom('c', 'X')], ['a', 'b', 'c']),
]


@pytest.mark.parametrize("label,atoms,expected", CASES, ids=[c[0] for c in CASES])
def test_order_atoms(label, atoms, expected):
    assert names(order_atoms(atoms)) == expected


SHORT_BODIES = [
    [],
    [atom('a', 'X')],
    [atom('a', 'X'), atom('b', 'Y')],          # disconnected, but nothing to gain
    [atom('a', 'X'), atom('b', 'X')],
]


@pytest.mark.parametrize("atoms", SHORT_BODIES)
def test_a_body_of_fewer_than_three_atoms_is_returned_untouched(atoms):
    assert order_atoms(atoms) is atoms


def test_the_result_is_always_a_permutation_that_keeps_the_first_atom():
    rng = random.Random(3)
    variables = ['X', 'Y', 'Z', 'W', 'V']
    for _ in range(2000):
        atoms = [atom('p%d' % i, *[rng.choice(variables)
                                   for _ in range(rng.randint(1, 3))])
                 for i in range(rng.randint(1, 6))]
        out = order_atoms(atoms)
        assert sorted(map(id, out)) == sorted(map(id, atoms))
        assert out[0] is atoms[0]


def test_no_atom_is_placed_before_one_that_connects_it():
    """After the first atom, every atom either shares a variable or none can."""
    rng = random.Random(11)
    variables = ['X', 'Y', 'Z', 'W']
    for _ in range(2000):
        atoms = [atom('p%d' % i, *[rng.choice(variables)
                                   for _ in range(rng.randint(1, 2))])
                 for i in range(rng.randint(3, 6))]
        out = order_atoms(atoms)
        bound = set(out[0].variables())
        for i, placed in enumerate(out[1:], start=1):
            own = set(placed.variables())
            if own and not (own & bound):
                # a disconnected atom is allowed only when nothing else connects
                assert not any(set(a.variables()) & bound for a in out[i:]), \
                    "a connected atom was left behind %r" % placed.name
            bound |= own


# --------------------------------------------------------------------------- #
# Where the plan keeps the order the author wrote
# --------------------------------------------------------------------------- #

def prepared(text):
    runner = Runner(load_text(text), Options())
    runner.prepare()
    return runner


DISCONNECTED = """
    a(1,1). b(1,10). c(1,1).
    r(X,W) :- a(X,Y), b(Z,W), c(Y,Z).
    @output("r").
"""


def test_a_disconnected_body_is_reordered():
    rule = prepared(DISCONNECTED).program.rules[0]
    assert names(compile_rule(rule).atoms) == ['a', 'c', 'b']


def test_reorder_false_keeps_the_source_order():
    rule = prepared(DISCONNECTED).program.rules[0]
    assert names(compile_rule(rule, reorder=False).atoms) == ['a', 'b', 'c']


def test_a_rule_with_an_aggregate_keeps_the_source_order():
    """A monotonic aggregate reads the activations as a stream (sec. 6.1)."""
    runner = prepared("""
        a(1,1). b(1,10). c(1,1).
        s(X,M) :- a(X,Y), b(Z,W), c(Y,Z), M = msum(W).
        @output("s").
    """)
    rule = runner.program.rules[0]
    assert rule.aggregates
    assert names(compile_rule(rule).atoms) == ['a', 'b', 'c']


@pytest.mark.parametrize("directive", ["limit(2)", "prelimit(2)"])
def test_a_program_that_limits_is_order_sensitive(directive):
    """`limit` keeps the first n facts in insertion order (sec. 9)."""
    runner = prepared(DISCONNECTED + '@post("r","%s").' % directive)
    assert runner._order_sensitive()


@pytest.mark.parametrize("directive", ["unique", "certain", "orderby(1)",
                                       "min(2)", "max(2)", "argmin(2,<1>)"])
def test_the_other_directives_are_not_order_sensitive(directive):
    runner = prepared(DISCONNECTED + '@post("r","%s").' % directive)
    assert not runner._order_sensitive()


def test_a_program_without_post_processing_is_not_order_sensitive():
    assert not prepared(DISCONNECTED)._order_sensitive()


# --------------------------------------------------------------------------- #
# End to end: the answers do not depend on how the body was written
# --------------------------------------------------------------------------- #

FACTS = " ".join("a(%d,%d). b(%d,%d). c(%d,%d)." % (i, i, i, i * 10, i, i)
                 for i in range(1, 21))


def test_the_answers_do_not_depend_on_the_order_of_the_body():
    connected = run(FACTS + """
        r(X,W) :- a(X,Y), c(Y,Z), b(Z,W).
        @output("r").
    """)
    disconnected = run(FACTS + """
        r(X,W) :- a(X,Y), b(Z,W), c(Y,Z).
        @output("r").
    """)
    assert connected.relations["r"] == disconnected.relations["r"]
    assert len(connected.relations["r"]) == 20


def test_a_limited_program_still_answers_by_derivation_order():
    """The guard is what makes this stable, not the ordering rule."""
    assert_answers("""
        a(1,1).
        c(1,5). c(1,2). c(1,9).
        b(2,20). b(5,50). b(9,90).
        r(X,W) :- a(X,Y), b(Z,W), c(Y,Z).
        @post("r","limit(1)").
        @output("r").
    """, 'r(1,20).')


def test_a_disconnected_body_under_negation_and_conditions():
    assert_answers(FACTS + """
        r(X,W) :- a(X,Y), b(Z,W), c(Y,Z), W > 180, not a(W,W).
        @output("r").
    """, 'r(19,190). r(20,200).')
