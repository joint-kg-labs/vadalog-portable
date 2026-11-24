"""CSV input and output (SPECIFICATION.md sec. 10)."""

import os

import pytest

from harness import assert_answers, run
from vadalog.errors import StaticError
from vadalog.values import is_null


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_read_without_mapping_gives_strings(tmp_path):
    write(tmp_path, "in.csv", "a,b,c\nd,e,f\n")
    assert_answers("""
        au(X,Y,Z) :- ou(X,Y,Z).
        @input("ou").
        @bind("ou", "csv", ".", "in.csv").
        @output("au").
    """, 'au("a","b","c"). au("d","e","f").', base_dir=str(tmp_path))


def test_read_with_mapping_applies_types(tmp_path):
    write(tmp_path, "typed.csv", "1,2.5,#T,2020-01-02\n")
    assert_answers("""
        au(W,X,Y,Z) :- ou(W,X,Y,Z).
        @input("ou").
        @bind("ou", "csv", ".", "typed.csv").
        @mapping("ou", 0, "i", "int").
        @mapping("ou", 1, "d", "double").
        @mapping("ou", 2, "b", "boolean").
        @mapping("ou", 3, "t", "date").
        @output("au").
    """, 'au(1,2.5,#T,2020-01-02).', base_dir=str(tmp_path))


def test_headers_and_selected_columns(tmp_path):
    write(tmp_path, "h.csv", "c0,c1,c2,c3,c4\n0,1,2,3,4\n5,6,7,8,9\n")
    assert_answers("""
        au(W,X,Y,Z) :- ou(W,X,Y,Z).
        @input("ou").
        @bind("ou", "csv useHeaders='true', selectedColumns=[0:2; 4]", ".", "h.csv").
        @output("au").
    """, 'au("0","1","2","4"). au("5","6","7","9").', base_dir=str(tmp_path))


def test_select_column_by_name(tmp_path):
    write(tmp_path, "h.csv", "id,name,extra\n1,alpha,x\n2,beta,y\n")
    assert_answers("""
        au(X,Y) :- ou(X,Y).
        @input("ou").
        @bind("ou", "csv useHeaders='true', selectedColumns=['name'; 'id']", ".", "h.csv").
        @output("au").
    """, 'au("alpha","1"). au("beta","2").', base_dir=str(tmp_path))


def test_tab_delimiter(tmp_path):
    write(tmp_path, "t.tsv", "a\tb\nc\td\n")
    assert_answers("""
        au(X,Y) :- ou(X,Y).
        @input("ou").
        @bind("ou", "csv delimiter='\\t'", ".", "t.tsv").
        @output("au").
    """, 'au("a","b"). au("c","d").', base_dir=str(tmp_path))


def test_null_token_becomes_a_marked_null(tmp_path):
    write(tmp_path, "n.csv", "a,\\N\nb,\\N\n")
    result = run("""
        au(X,Y) :- ou(X,Y).
        @input("ou").
        @bind("ou", "csv", ".", "n.csv").
        @output("au").
    """, base_dir=str(tmp_path))
    rows = result.relations["au"]
    assert len(rows) == 2, rows
    assert all(is_null(r[1]) for r in rows)
    assert rows[0][1] != rows[1][1], "each null field gets its own identifier"


def test_write_output(tmp_path):
    write(tmp_path, "src.csv", "1,2\n3,4\n")
    result = run("""
        au(Y,X) :- ou(X,Y).
        @input("ou").
        @bind("ou", "csv", ".", "src.csv").
        @output("au").
        @bind("au", "csv", ".", "out.csv").
        @post("au","orderby(1)").
    """, base_dir=str(tmp_path))
    assert result.written == [os.path.join(str(tmp_path), "out.csv")]
    assert open(result.written[0]).read() == "2,1\n4,3\n"


def test_round_trip_with_headers(tmp_path):
    write(tmp_path, "src.csv", "n,v\nfoo,1\nbar,2\n")
    run("""
        au(X,Y) :- ou(X,Y).
        @input("ou").
        @bind("ou", "csv useHeaders='true'", ".", "src.csv").
        @mapping("ou", 0, "n", "string").
        @mapping("ou", 1, "v", "int").
        @output("au").
        @bind("au", "csv useHeaders='true'", ".", "out.csv").
        @mapping("au", 0, "n", "string").
        @mapping("au", 1, "v", "int").
        @post("au","orderby(1)").
    """, base_dir=str(tmp_path))
    assert open(os.path.join(str(tmp_path), "out.csv")).read() == "n,v\nbar,2\nfoo,1\n"


def test_non_csv_source_is_refused(tmp_path):
    with pytest.raises(StaticError) as exc:
        run("""
            a(X) :- b(X).
            @input("b").
            @bind("b", "postgres", "schema", "table").
            @output("a").
        """, base_dir=str(tmp_path))
    assert "CSV" in str(exc.value)


def test_arity_mismatch_is_reported(tmp_path):
    write(tmp_path, "bad.csv", "1,2,3\n")
    with pytest.raises(Exception) as exc:
        run("""
            a(X,Y) :- b(X,Y).
            @input("b").
            @bind("b", "csv", ".", "bad.csv").
            @output("a").
        """, base_dir=str(tmp_path))
    assert "arity" in str(exc.value)
