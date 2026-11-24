"""Static checks, diagnostics and resource guards (SPECIFICATION.md sec. 5.2, 5.4, 7.7)."""

import pytest

from harness import assert_answers, run
from vadalog.errors import (ParseError, ResourceExceeded, StaticError,
                            TypeFailure)


def test_arity_conflict_is_reported():
    with pytest.raises(StaticError) as exc:
        run('p(1). p(1,2). @output("p").')
    assert "arity" in str(exc.value)


def test_head_variable_bound_only_under_negation():
    with pytest.raises(StaticError) as exc:
        run("""
            q(1).
            p(X) :- q(Y), not r(X).
            @output("p").
        """)
    assert "negated literal" in str(exc.value)


def test_unstratifiable_program_is_rejected():
    with pytest.raises(StaticError) as exc:
        run("""
            b(1).
            p(X) :- b(X), not q(X).
            q(X) :- b(X), not p(X).
            @output("p").
        """)
    assert "not stratifiable" in str(exc.value)


def test_unstratifiable_program_runs_with_the_escape_hatch():
    result = run("""
        b(1).
        p(X) :- b(X), not q(X).
        q(X) :- b(X), not p(X).
        @output("p").
        @output("q").
    """, allow_unstratified=True)
    assert result.relations["p"] or result.relations["q"]


def test_non_monotonic_aggregate_in_recursion_is_rejected():
    with pytest.raises(StaticError) as exc:
        run("""
            e(1,2).
            p(X,Z) :- e(X,Y), Z = max(Y).
            p(X,Z) :- p(X,Y), Z = max(Y).
            @output("p").
        """)
    assert "not stratifiable" in str(exc.value)


def test_dom_star_is_refused():
    with pytest.raises(ParseError) as exc:
        run('p(X) :- q(X), dom(*). @output("p").')
    assert "warded rewriting" in str(exc.value)


def test_assignment_cycle_is_reported():
    with pytest.raises(StaticError) as exc:
        run("""
            b(1).
            p(X,Y,Z) :- b(X), Y = Z + 1, Z = Y + 1.
            @output("p").
        """)
    assert "cycle" in str(exc.value)


def test_comparing_incompatible_types_fails():
    with pytest.raises(TypeFailure):
        run("""
            a("x").
            b(1).
            p(X) :- a(X), b(Y), X > Y.
            @output("p").
        """)


def test_max_facts_guard():
    with pytest.raises(ResourceExceeded) as exc:
        run("""
            n(0).
            n(X) :- n(Y), Y < 100000, X = Y + 1.
            @output("n").
        """, max_facts=50)
    assert "max-facts" in str(exc.value)


def test_max_rounds_guard():
    with pytest.raises(ResourceExceeded) as exc:
        run("""
            n(0).
            n(X) :- n(Y), Y < 100000, X = Y + 1.
            @output("n").
        """, max_rounds=5)
    assert "max-rounds" in str(exc.value)


def test_recursive_existential_rule_terminates():
    """The isomorphism check is what stops this (SPECIFICATION.md sec. 7.4)."""
    assert_answers("""
        p(1).
        p(Y) :- p(X).
        @output("p").
    """, 'p(1). p(z1).')


def test_non_recursive_predicate_keeps_isomorphic_facts():
    """Non-recursive predicates are not subject to the isomorphism check."""
    result = run("""
        a("x","c").
        a("y","c").
        q(J,X) :- a(W,X), J = #sk(W).
        @output("q").
    """)
    assert len(result.relations["q"]) == 2


def test_unknown_annotation_warns_but_runs():
    result = run("""
        p(1).
        @output("p").
        @somethingElse("p").
    """)
    assert result.relations["p"] == [(1,)]
    assert any("somethingElse" in w for w in result.warnings)


def test_ignored_annotation_warns():
    result = run("""
        p(1).
        @output("p").
        @sne.
    """)
    assert any("@sne" in w for w in result.warnings)


def test_output_of_undefined_predicate_warns():
    result = run('p(1). @output("q").')
    assert result.relations["q"] == []
    assert any("never defines" in w for w in result.warnings)


def test_zero_arity_predicate():
    assert_answers("""
        flag.
        ok :- flag.
        @output("ok").
    """, 'ok.')


def test_multi_head_rule_shares_nulls():
    result = run("""
        e(1,2).
        p(I,Z), q(J,Z) :- e(I,J).
        @output("p").
        @output("q").
    """)
    assert result.relations["p"][0][1] == result.relations["q"][0][1]
