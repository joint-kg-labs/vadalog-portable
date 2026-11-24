"""Worked examples: Skolem functions, EGDs, failure rules."""

import pytest

from harness import assert_answers, run
from vadalog.errors import ReasoningFailure, UnificationFailure


def test_example_25_skolem_determinism_and_range_disjointness():
    assert_answers("""
        b(1,2).
        a(X,Y,Z) :- b(X,Y),Z=#f(X,Y).
        c(K) :- b(X,Y),K=#f(X,Y).
        d(K) :- b(X,Y),K=#g(X,Y).
        @output("a").
        @output("c").
        @output("d").
    """, 'a(1,2,z2). c(z2). d(z1).')


def test_example_26_skolem_join():
    assert_answers("""
        c(1,2,3).
        d(2,3,4).
        w(Y,J) :- c(X,Y,Z),J=#f(Y,Z).
        v(X,J) :- d(X,Y,Z),J=#f(X,Y).
        q(X,Z) :- v(X,Y),w(Z,Y).
        f(J,X,X) :- q(X,X), J=#f1(X,X).
        @output("f").
    """, 'f(z2,2,2).')


def test_example_27_skolem_grouping():
    assert_answers("""
        a("a","b","c").
        a("a","b","d").
        a("a","c","d").
        a("a","c","e").
        q(J,X) :- a(W,V,X),J=#sk(W,V).
        @output("q").
    """, 'q(z1,"c"). q(z1,"d"). q(z2,"d"). q(z2,"e").')


def test_example_28_skolem_as_a_filter():
    assert_answers("""
        sequelOf(0,2,"a").
        sequelOf(5,3,"a").
        followOn(1,2,"a").
        followOn(2,2,"a").
        sequelSynt(X,J) :- sequelOf(X,Y,Z), J = #f(Y,Z).
        q(X,W) :- sequelSynt(X,J), followOn(W,Y,Z), J= #f(Y,Z).
        @output("q").
    """, 'q(0,1). q(0,2).')


def test_example_29_recursive_skolem():
    assert_answers("""
        a(1,2,3,4).
        a(2,3,4,5).
        a(2,3,6,5).
        a(4,3,6,5).
        a(X,Y,Z,K) :- a(X,C,Z,K), Y = #f1(K).
        b(X,Y,Z,K,Q) :- a(X,Y,Z,K), Y = #f1(K), Q=#f2(X).
        @output("b").
    """, 'b(1,z1,3,4,z3). b(2,z2,4,5,z4). b(2,z2,6,5,z4). b(4,z2,6,5,z5).')


# --------------------------------------------------------------------------- #
# EGDs
# --------------------------------------------------------------------------- #

def test_example_31_connected_components():
    assert_answers("""
        edge(1,2).
        edge(2,1).
        edge(1,3).
        conn(X,Y,Z):- edge(X,Y).
        Z1=Z2 :- conn(X,Y,Z1),conn(Y,Z,Z2).
        Z1=Z2 :- conn(X,Y,Z1),conn(X,Z,Z2).
        Z1=Z2 :- conn(X,Y,Z1),conn(Z,Y,Z2).
        Z1=Z2 :- conn(X,Y,Z1),conn(Z,X,Z2).
        @output(conn).
    """, 'conn(1,2,z1). conn(2,1,z1). conn(1,3,z1).')


def test_example_30_undirected_components():
    assert_answers("""
        edge(1,2).
        edge(2,1).
        edge(1,3).
        conn(X,Y,Z):- edge(X,Y).
        conn(Y,X,Z):- edge(X,Y).
        Z1=Z2 :- conn(X,Y,Z1),conn(Y,Z,Z2).
        @output(conn).
    """, 'conn(1,2,z1). conn(2,1,z1). conn(1,3,z1). conn(3,1,z1).')


def test_egd_binds_a_null_to_a_constant():
    assert_answers("""
        p(1).
        q(X,Y) :- p(X).
        r(7).
        Y=V :- q(X,Y), r(V).
        @output("q").
    """, 'q(1,7).')


def test_egd_on_two_constants_fails():
    with pytest.raises(UnificationFailure):
        run("""
            p(1,2).
            X=Y :- p(X,Y).
            @output("p").
        """)


def test_egd_groups_by_shared_key():
    """The `recursive_groupby` shape."""
    assert_answers("""
        t(1,10,5.0).
        t(1,11,6.0).
        t(2,11,7.0).
        t2(Z,CF,CCIA,VALUE) :- t(CF,CCIA,VALUE).
        Z1=Z2 :- t2(Z1,CF,CCIA,VALUE),t2(Z2,CF,CCIA2,VALUE2).
        Z1=Z2 :- t2(Z1,CF1,CCIA,VALUE),t2(Z2,CF2,CCIA,VALUE2).
        @output("t2").
    """, 't2(z1,1,10,5.0). t2(z1,1,11,6.0). t2(z1,2,11,7.0).')


# --------------------------------------------------------------------------- #
# Failure rules
# --------------------------------------------------------------------------- #

def test_example_32_cycle_detection_fires():
    with pytest.raises(ReasoningFailure):
        run("""
            edge(1,2).
            edge(2,1).
            edge(1,3).
            path(X,Y):- edge(X,Y).
            path(X,Z):- edge(X,Y), path(Y,Z).
            #F :- path(X,X).
            @output(path).
        """)


def test_failure_rule_does_not_fire_on_a_dag():
    assert_answers("""
        edge(1,2).
        edge(2,3).
        path(X,Y):- edge(X,Y).
        path(X,Z):- edge(X,Y), path(Y,Z).
        #F :- path(X,X).
        @output("path").
    """, 'path(1,2). path(2,3). path(1,3).')


def test_example_33_key_violation():
    with pytest.raises(ReasoningFailure):
        run("""
            company(1,"Acme",10).
            company(1,"Other",20).
            c(Id, Name) :- company(Id, Name, Revenue).
            #F :- c(Id, Name1), c(Id, Name2), Name1 <> Name2.
            @output(c).
        """)
