"""Worked examples: `@post` directives."""

from harness import assert_answers, run


def _ordered(text, pred, **kwargs):
    return run(text, **kwargs).relations[pred]


def test_example_39_orderby():
    rows = _ordered("""
        t(1,"b",5).
        t(1,"a",1).
        t(1,"c",1).
        p(X,Y,Z) :- t(X,Y,Z).
        @output("p").
        @post("p","orderby(3,-2)").
    """, "p")
    assert rows == [(1, "c", 1), (1, "a", 1), (1, "b", 5)]


def test_example_40_min():
    assert_answers("""
        t(1,"b",5).
        t(1,"b",1).
        t(1,"c",1).
        p(X,Y,Z) :- t(X,Y,Z).
        @output("p").
        @post("p","min(3)").
    """, 'p(1,"b",1). p(1,"c",1).')


def test_min_over_two_positions():
    assert_answers("""
        t(1,"b",1).
        t(2,"c",1).
        t(1,"a",1).
        q(X,Y,Z) :- t(X,Y,Z).
        @output("q").
        @post("q","min(1,2)").
    """, 'q(1,"a",1).')


def test_example_41_max():
    assert_answers("""
        t(1,"b",5).
        t(1,"b",1).
        t(1,"c",1).
        p(X,Y,Z) :- t(X,Y,Z).
        @output("p").
        @post("p","max(3)").
    """, 'p(1,"b",5). p(1,"c",1).')


def test_max_over_two_positions():
    assert_answers("""
        t(2,"b",1).
        t(1,"c",1).
        t(2,"a",1).
        q(X,Y,Z) :- t(X,Y,Z).
        @output("q").
        @post("q","max(2,1)").
    """, 'q(1,"c",1).')


def test_example_42_argmin():
    rows = _ordered("""
        f(1,3,"a", 3).
        f(4,3,"a", 5).
        f(2,6,"b", 7).
        f(2,6,"b", 8).
        f(3,6,"b", 9).
        g(X,Y,Z,K) :- f(X,Y,Z,K).
        @output("g").
        @post("g","argmin(4,<2,3>)").
        @post("g","orderby(1)").
    """, "g")
    assert rows == [(1, 3, "a", 3), (2, 6, "b", 7)]


def test_example_43_argmax():
    rows = _ordered("""
        f(1,3,"a", 3).
        f(4,3,"a", 5).
        f(2,6,"b", 7).
        f(2,6,"b", 8).
        f(3,6,"b", 9).
        g(X,Y,Z,K) :- f(X,Y,Z,K).
        @output("g").
        @post("g","argmax(4,<2,3>)").
        @post("g","orderby(1)").
    """, "g")
    assert rows == [(3, 6, "b", 9), (4, 3, "a", 5)]


def test_certain_drops_facts_with_nulls():
    assert_answers("""
        employee(1).
        known(2,2).
        manager(Y,X) :- employee(X).
        manager(Y,X) :- known(X,Y).
        @output("manager").
        @post("manager","certain").
    """, 'manager(2,2).')


def test_limit_applies_after_ordering():
    rows = _ordered("""
        p(2).
        p(4).
        p(3).
        p(7).
        p(1).
        q(X) :- p(X).
        @output("q").
        @post("q", "orderBy(1)").
        @post("q", "limit(3)").
    """, "q")
    assert rows == [(1,), (2,), (3,)]


def test_prelimit_applies_before_ordering():
    rows = _ordered("""
        p(2).
        p(4).
        p(3).
        p(7).
        p(1).
        q(X) :- p(X).
        @output("q").
        @post("q", "orderBy(1)").
        @post("q", "prelimit(3)").
    """, "q")
    assert rows == [(2,), (3,), (4,)]


def test_unique_is_accepted():
    assert_answers("""
        p(1).
        q(X) :- p(X).
        @output("q").
        @post("q", "unique").
    """, 'q(1).')
