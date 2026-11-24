"""Worked examples: language core."""

from harness import assert_answers


def test_example_4_simple_join():
    assert_answers("""
        a(1).
        c(1,2).
        b(Y,X) :- a(X),c(X,Y).
        @output("b").
    """, 'b(2,1).')


def test_anonymous_variables():
    assert_answers("""
        t("Text", 1, 2).
        t("Text2", 1, 2).
        b(X) :- t(X, _, _).
        @output("b").
    """, 'b("Text"). b("Text2").')


def test_example_5_marked_nulls():
    assert_answers("""
        employee(1).
        employee(2).
        manager(Y,X) :- employee(X).
        @output("manager").
    """, 'manager(z1,1). manager(z2,2).')


def test_example_6_ontology_with_nulls():
    assert_answers("""
        employee("Jack").
        contract("Jack").
        employee("Ruth").
        contract("Ruth").
        employee("Ann").
        hired("Ann","Ruth").
        manager(Z,X) :- employee(X).
        hired(Y,X) :- manager(Y,X),contract(X).
        contractSigned(X) :- hired(Y,X),manager(Y,Z).
        @output("contractSigned").
    """, 'contractSigned("Jack"). contractSigned("Ruth").')


def test_example_7_linear_rule():
    assert_answers("""
        employee(1).
        employee(2).
        department(Y,X) :- employee(X).
        @output("department").
    """, 'department(z1,1). department(z2,2).')


def test_example_10_cartesian_product():
    assert_answers("""
        employee("Jack").
        employee("Ruth").
        department("science").
        department("finance").
        canWork(X,Y,Z) :- employee(X), department(Y).
        @output("canWork").
    """, '''canWork("Jack","science",z1). canWork("Jack","finance",z2).
            canWork("Ruth","science",z3). canWork("Ruth","finance",z4).''')


def test_example_11_constants_in_head():
    assert_answers("""
        employee("Mark").
        junior("Mark").
        contract(X,"basic",20) :- employee(X),junior(X).
        @output("contract").
    """, 'contract("Mark","basic",20).')


def test_example_12_constants_filter():
    assert_answers("""
        employee("Mark","junior").
        employee("Ruth","senior").
        contract(X,"basic",20) :- employee(X,"junior").
        contract(X,"advanced",40) :- employee(X,"senior").
        @output("contract").
    """, 'contract("Mark","basic",20). contract("Ruth","advanced",40).')


def test_example_17_condition():
    assert_answers("""
        contract("Mark",14).
        contract("Jeff",22).
        rich(X) :- contract(X,Y),Y>=20.
        @output("rich").
    """, 'rich("Jeff").')


def test_example_18_condition_over_expression():
    assert_answers("""
        balanceItem(1,7,2,5).
        balanceItem(2,2,2,7).
        error(E,I) :- balanceItem(I,X,Y,Z),X<>Y+Z.
        @output("error").
    """, 'error(z1,2).')


def test_example_19_multiple_conditions():
    assert_answers("""
        player(1,"Chelsea").
        age(1,24).
        player(2,"Bayern").
        team("Chelsea").
        age(2,25).
        player(3,"Chelsea").
        age(3,18).
        team("Bayern").
        seniorEnglish(X) :- player(X,Y), team(Y), age(X,A), Y="Chelsea", A>20.
        @output("seniorEnglish").
    """, 'seniorEnglish(1).')


def test_example_20_assignment():
    assert_answers("""
        balanceItem("loans",23.0).
        balanceItem("deposits",20.0).
        operations(Q,Z,A) :- balanceItem(I1,X),balanceItem(I2,Y),
                              I1="loans",I2="deposits",Z=X+Y,A=(X+Y)/2.
        @output("operations").
    """, 'operations(z1,43.0,21.5).')


def test_example_21_set_union_assignment():
    assert_answers("""
        projects("Mark",1,{1,5,7}).
        projects("Mark",2,{4,5,6}).
        all(X,P) :- projects(X,D1,P1), projects(X,D2,P2), D1>D2, P=P1|P2.
        @output("all").
    """, 'all("Mark",{1,4,5,6,7}).')


EDGES = """
    edge(1,2).
    edge(2,3).
    edge(1,4).
    edge(4,5).
"""
REACHABLE = 'path(1,3). path(1,2). path(1,5). path(2,3). path(1,4). path(4,5).'


def test_example_22_left_recursion():
    assert_answers(EDGES + """
        path(X,Y) :- edge(X,Y).
        path(X,Z) :- path(Y,Z), edge(X,Y).
        @output("path").
    """, REACHABLE)


def test_example_22_right_recursion():
    assert_answers(EDGES + """
        path(X,Y) :- edge(X,Y).
        path(X,Z) :- edge(X,Y),path(Y,Z).
        @output("path").
    """, REACHABLE)


def test_example_22_non_linear_recursion():
    assert_answers(EDGES + """
        path(X,Y) :- edge(X,Y).
        path(X,Z) :- path(X,Y),path(Y,Z).
        @output("path").
    """, REACHABLE)


def test_example_23_negation():
    assert_answers("""
        employee("Mark").
        employee("Ruth").
        director("Jane").
        hired("Ruth").
        contractor("Mark").
        project(1,"Mark").
        project(2,"Ruth").
        project(3,"Jane").
        safeProjects(X,P) :- project(X,P), not contractor(P).
        @output("safeProjects").
    """, 'safeProjects(2,"Ruth"). safeProjects(3,"Jane").')


def test_example_24_recursion_with_negation():
    assert_answers("""
        s(1,2).
        s(2,3).
        s(3,5).
        s(4,6).
        b(6,2).
        b(4,2).
        b(2,2).
        c(2).
        f(X,Y) :- s(X,Y), not b(Y,Z).
        f(Y,X) :- f(X,Y), not b(X,Z).
        @output("f").
    """, 'f(5,3). f(2,3). f(3,5).')
