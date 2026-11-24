"""Worked examples: aggregation."""

from harness import assert_answers, flatten, run


def test_example_13_msum():
    assert_answers("""
        s(1.0,"a").
        s(2.0,"a").
        s(3.0,"a").
        s(4.0,"b").
        s(3.0,"b").
        f(J,Y) :- s(X,Y), J = msum(X).
        @output("f").
    """, 'f(1.0,"a"). f(3.0,"a"). f(6.0,"a"). f(4.0,"b"). f(7.0,"b").')


def test_example_14_mprod_with_contributors():
    assert_answers("""
        s(0.1,2,"a").
        s(0.2,2,"a").
        s(0.5,3,"a").
        s(0.6,4,"b").
        s(0.5,5,"b").
        f(J,Z) :- s(X,Y,Z), J = mprod(X,<Y>).
        @output("f").
    """, 'f(0.1,"a"). f(0.05,"a"). f(0.6,"b"). f(0.3,"b").')


def test_example_15_threshold_discards_intermediates():
    assert_answers("""
        edge(1,2).
        edge(3,2).
        edge(5,2).
        edge(3,1).
        edge(2,5).
        indegree(Y,J) :- edge(X,Y),J=msum(1,<X>).
        found(X) :- indegree(X,J),J>2.
        @output("found").
    """, 'found(2).')


def test_example_16_post_max_discards_intermediates():
    assert_answers("""
        s(1.0,"a").
        s(2.0,"a").
        s(3.0,"a").
        s(4.0,"b").
        s(3.0,"b").
        f(J,Y) :- s(X,Y), J = msum(X).
        @output("f").
        @post("f","max(1)").
    """, 'f(6.0,"a"). f(7.0,"b").')


def test_stratified_max():
    assert_answers("""
        b(1,2).
        b(1,3).
        b(2,5).
        b(2,7).
        h(X,Z) :- b(X,Y), Z = max(Y), X > 0.
        @output("h").
    """, 'h(1,3). h(2,7).')


def test_stratified_min():
    assert_answers("""
        b(1,2).
        b(1,3).
        b(2,5).
        b(2,7).
        h(X,Z) :- b(X,Y), Z = min(Y), X > 0.
        @output("h").
    """, 'h(1,2). h(2,5).')


def test_stratified_count():
    assert_answers("""
        b(1,2).
        b(1,3).
        b(2,5).
        b(2,7).
        b(2,9).
        h(X,Z) :- b(X,Y), Z = count(Y), X > 0.
        @output("h").
    """, 'h(1,2). h(2,3).')


def test_msum_then_max():
    assert_answers("""
        b(1,2).
        b(1,3).
        b(2,5).
        b(2,7).
        b_msum(X,Z):- b(X, Y), Z = msum(Y).
        b_sum(X,Z) :- b_msum(X, Y), Z = max(Y).
        @output("b_sum").
        @relaxedSafety.
    """, 'b_sum(1,5). b_sum(2,12).')


def test_stratified_sum_directly():
    """`sum` is this engine's deterministic addition (SPECIFICATION.md sec. 6.2)."""
    assert_answers("""
        b(1,2).
        b(1,3).
        b(2,5).
        b(2,7).
        b_sum(X,Z) :- b(X,Y), Z = sum(Y).
        b_avg(X,Z) :- b(X,Y), Z = avg(Y).
        @output("b_sum").
        @output("b_avg").
    """, 'b_sum(1,5). b_sum(2,12). b_avg(1,2.5). b_avg(2,6.0).')


def test_relaxed_safety_example_via_negation():
    assert_answers("""
        a(1, 2).
        a(1, 3).
        a(1, 4).
        a(2, 2).
        a(2, 4).
        a_msum(X, Z) :- a(X, Y), Z = msum(Y).
        a_msum_red(X, Z1) :- a_msum(X, Z1), a_msum(X, Z2), Z2 > Z1 .
        a_sum(X, Z) :- a_msum(X, Z), not a_msum_red(X, Z).
        @output("a_sum").
        @relaxedSafety.
    """, 'a_sum(1,9). a_sum(2,6).')


def test_monotonic_library_guaranteed_facts():
    """Intermediate values are order dependent; only the extrema are guaranteed."""
    result = run("""
        a("one", 3, "a", 10).
        a("one", 6, "c", 30).
        a("one", 1, "b", 20).
        a("one", 2, "c", 30).
        a("two", 5, "f", 60).
        a("two", 3, "e", 50).
        a("two", 6, "g", 70).
        a("two", 2, "d", 40).
        a("two", 3, "d", 40).
        @library("m:", "monotonic").
        ssum(X, Sum) :- a(X, Y, Z, U), Sum = m:sum(Y, [X],[]).
        pprod(X, Sum) :- a(X, Y, Z, U), Sum = m:prod(Y, [X],[]).
        mmin(X, Sum) :- a(X, Y, Z, U), Sum = m:min(Y, X).
        mmax(X, Sum) :- a(X, Y, Z, U), Sum = m:max(Y, X).
        ccount(X, Sum) :- a(X, Y, Z, U), Sum = m:count(X).
        @output("ssum").
        @output("pprod").
        @output("mmin").
        @output("mmax").
        @output("ccount").
    """)
    facts = flatten(result.relations)
    for expected in [("ssum", ("one", 12)), ("ssum", ("two", 19)),
                     ("pprod", ("one", 36)), ("pprod", ("two", 540)),
                     ("mmax", ("one", 6)), ("mmax", ("two", 6)),
                     ("mmin", ("one", 1)), ("mmin", ("two", 2))]:
        assert expected in facts, "%s missing from %s" % (expected, sorted(facts))
    counts = {t for p, t in facts if p == "ccount"}
    assert counts == {("one", i) for i in range(1, 5)} | {("two", i) for i in range(1, 6)}


def test_company_control():
    """Recursive aggregation: control via more than 50% of ownership."""
    result = run("""
        @library("m:", "monotonic").
        owns("source", "c1", 1.0).
        owns("source", "c2", 1.0).
        owns("source", "c3", 1.0).
        owns("c1", "c4", 0.3).
        owns("c2", "c4", 0.3).
        owns("c4", "sink", 0.3).
        owns("c3", "sink", 0.3).
        controls(I, I), controls(J, J) :- owns(I, J, W).
        controls(I, K) :- controls(I, J), owns(J, K, W2), W = m:sum(W2, [I, K], []), W > 0.5.
        @output("controls").
    """)
    got = {t for p, t in flatten(result.relations)}
    for company in ["source", "c1", "c2", "c3", "c4", "sink"]:
        assert (company, company) in got
    for target in ["c1", "c2", "c3", "c4", "sink"]:
        assert ("source", target) in got, "source should control %s" % target
