"""Worked examples: single-fact operators and libraries."""

import pytest

from harness import assert_answers


def test_substring():
    assert_answers("""
        a("vadaengine").
        b("oxford").
        q(Y,J) :- a(X), b(Y), J = substring(X,4,10).
        @output("q").
    """, 'q("oxford", "engine").')


def test_contains():
    assert_answers("""
        a("vadaengine").
        b("engine").
        q(X,Y,J) :- a(X), b(Y), J = contains(X,Y).
        @output("q").
    """, 'q("vadaengine", "engine", #T).')


def test_starts_with():
    assert_answers("""
        a("vadaengine").
        b("vada").
        q(X,Y,J) :- a(X), b(Y), J = starts_with(X,Y).
        @output("q").
    """, 'q("vadaengine","vada",#T).')


def test_ends_with():
    assert_answers("""
        a("vadaengine").
        b("engine").
        q(X,Y,J) :- a(X), b(Y), J = ends_with(X,Y).
        @output("q").
    """, 'q("vadaengine","engine",#T).')


def test_concat():
    assert_answers("""
        a("vada").
        b("engine").
        q(X,Y,J) :- a(X), b(Y), J = concat(X,Y).
        @output("q").
    """, 'q("vada","engine","vadaengine").')


def test_plus_upcasts_to_string():
    assert_answers("""
        a("vada").
        b(1.0).
        q(X,Y,J) :- a(X), b(Y), J = X + Y.
        @output("q").
    """, 'q("vada",1.0,"vada1.0").')


def test_index_of():
    assert_answers("""
        a("vadaengine").
        b("engi").
        q(X,Y,J) :- a(X), b(Y), J = index_of(X,Y).
        @output("q").
    """, 'q("vadaengine","engi",4).')


def test_string_length():
    assert_answers("""
        a("vadaengine").
        q(X,J) :- a(X), J=string_length(X).
        @output("q").
    """, 'q("vadaengine",10).')


# --------------------------------------------------------------------------- #
# list operators
# --------------------------------------------------------------------------- #

def test_list_substring():
    assert_answers("""
        a([0, 1, 2, 3, 4, 5], 1, 3).
        b(P) :-  a(X, Y, Z), P = substring(X,Y,Z).
        @output("b").
    """, 'b([1,2]).')


def test_list_contains():
    assert_answers("""
        a([0, 1, 2, 3, 4, 5]).
        b(3).
        b(7).
        c(Y,J) :- a(X), b(Y), J = contains(X,Y).
        @output("c").
    """, 'c(3, #T). c(7, #F).')


def test_list_starts_with():
    assert_answers("""
        a([0, 1, 2, 3, 4, 5]).
        b([0, 1]).
        b([0, 1, 3]).
        c(Y,J) :- a(X), b(Y), J = starts_with(X,Y).
        @output("c").
    """, 'c([0,1], #T). c([0,1,3], #F).')


def test_list_ends_with():
    assert_answers("""
        a([0, 1, 2, 3, 4, 5]).
        b([4, 5]).
        b([2, 4, 5]).
        c(Y,J) :- a(X), b(Y), J = ends_with(X,Y).
        @output("c").
    """, 'c([4,5], #T). c([2,4,5], #F).')


def test_list_concat():
    assert_answers("""
        a(["a", "b"], [1, 2]).
        a(["a", "b"], "c").
        c(J) :- a(X,  Y), J = concat(X, Y).
        @output("c").
    """, 'c(["a","b",1,2]). c(["a","b","c"]).')


def test_list_length():
    assert_answers("""
        a([0, 1, 2, 3, 4, 5]).
        b(J) :- a(X), J=string_length(X).
        @output("b").
    """, 'b(6).')


# --------------------------------------------------------------------------- #
# libraries
# --------------------------------------------------------------------------- #

def test_null_management():
    assert_answers("""
        @library("null:", "nullManagement").
        p(1).
        p1(A,B) :- p(A).
        v1(X):- p1(A,B), X = null:isnull(B).
        @output("v1").
    """, 'v1(#T).')


def test_coalesce():
    assert_answers("""
        @library("null:", "nullManagement").
        p(1).
        p1(A,B) :- p(A).
        v1(X):- p1(A,B), X = null:coalesce(B, A).
        @output("v1").
    """, 'v1(1).')


def test_math_library():
    assert_answers("""
        @library("m:", "math").
        a(9.0, 2).
        b(R,S,T) :- a(X,Y), R = m:sqrt(X), S = m:mod(7,Y), T = m:max(3,9,5).
        @output("b").
    """, 'b(3.0,1,9).')


def test_collections_library():
    assert_answers("""
        @library("c:", "collections").
        a([3,1,2]).
        b(S,J,G) :- a(X), S = c:size(X), J = c:join(c:sort(X), "-"), G = c:get(X,1).
        @output("b").
    """, 'b(3,"1-2-3",1).')


def test_datatypes_library():
    assert_answers("""
        @library("d:", "datatypes").
        a(1, 1.5, "s").
        b(P,Q,R) :- a(X,Y,Z), P = d:isInt(X), Q = d:isDouble(Y), R = d:instanceOf(Z,"string").
        @output("b").
    """, 'b(#T,#T,#T).')


def test_regex_library():
    assert_answers("""
        @library("sub", "regex", "replaceAll").
        input("ab cd ef").
        res(Y) :- input(X), Y = sub(X, "[a-z]+", "*").
        @output("res").
    """, 'res("* * *").')


def test_unknown_library_is_reported():
    with pytest.raises(Exception) as exc:
        assert_answers('@library("s:", "simmetrics"). a(1). @output("a").', 'a(1).')
    assert "simmetrics" in str(exc.value)


def test_division_by_zero_aborts():
    with pytest.raises(Exception) as exc:
        assert_answers("""
            a(1,0).
            b(Z) :- a(X,Y), Z = X/Y.
            @output("b").
        """, 'b(1).')
    assert "division by zero" in str(exc.value)


def test_boolean_operators():
    assert_answers("""
        a(#T,#F).
        b(P,Q,R) :- a(X,Y), P = X && Y, Q = X || Y, R = !X.
        @output("b").
    """, 'b(#F,#T,#F).')


def test_in_condition():
    assert_answers("""
        s({1,2,3}).
        v(2).
        v(9).
        r(X) :- v(X), s(S), X in S.
        @output("r").
    """, 'r(2).')


def test_set_intersection():
    assert_answers("""
        a({1,2,3},{2,3,4}).
        b(P,Q) :- a(X,Y), P = X & Y, Q = X | Y.
        @output("b").
    """, 'b({2,3},{1,2,3,4}).')


def test_integer_division_truncates():
    """`/` stays integral unless a double is involved (SPECIFICATION.md sec. 4.3)."""
    assert_answers("""
        a(7,2).
        a(-7,2).
        b(J) :- a(X,Y), J = X/Y.
        c(J) :- a(X,Y), J = X/2.0.
        @output("b").
        @output("c").
    """, 'b(3). b(-3). c(3.5). c(-3.5).')


def test_arithmetic_precedence():
    assert_answers("""
        a(2,3,4).
        b(J,K) :- a(X,Y,Z), J = X + Y * Z, K = (X + Y) * Z.
        @output("b").
    """, 'b(14,20).')


def test_set_literal_over_variables():
    assert_answers("""
        p(1,2).
        q(S,T) :- p(X,Y), S = {X,Y}, T = {X} | {Y}.
        @output("q").
    """, 'q({1,2},{1,2}).')


def test_list_literal_over_variables():
    assert_answers("""
        p(1,2).
        q(L) :- p(X,Y), L = [X,Y,3].
        @output("q").
    """, 'q([1,2,3]).')
