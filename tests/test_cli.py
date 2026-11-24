"""The command line surface (SPECIFICATION.md sec. 12.5)."""

import json
import os

from harness import PROGRAMS  # noqa: F401  (adds src/ to sys.path)
from vadalog.cli import main

PROGRAM = """
edge(1,2).
edge(2,3).
path(X,Y) :- edge(X,Y).
path(X,Z) :- edge(X,Y), path(Y,Z).
@output("path").
@post("path","orderby(1,2)").
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_run_prints_facts(tmp_path, capsys):
    path = write(tmp_path, "p.vada", PROGRAM)
    assert main(["run", path]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["path(1,2).", "path(1,3).", "path(2,3)."]


def test_run_json(tmp_path, capsys):
    path = write(tmp_path, "p.vada", PROGRAM)
    assert main(["run", path, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == [[1, 2], [1, 3], [2, 3]]


def test_run_csv(tmp_path, capsys):
    path = write(tmp_path, "p.vada", PROGRAM)
    out_dir = str(tmp_path / "out")
    assert main(["run", path, "--format", "csv", "--out", out_dir]) == 0
    assert open(os.path.join(out_dir, "path.csv")).read() == "1,2\n1,3\n2,3\n"


def test_check(tmp_path, capsys):
    path = write(tmp_path, "p.vada", PROGRAM)
    assert main(["check", path]) == 0
    assert "ok" in capsys.readouterr().out


def test_explain(tmp_path, capsys):
    path = write(tmp_path, "p.vada", PROGRAM)
    assert main(["explain", path]) == 0
    assert "stratum 0" in capsys.readouterr().out


def test_static_error_exit_code(tmp_path, capsys):
    path = write(tmp_path, "bad.vada", 'p(1). p(1,2). @output("p").')
    assert main(["run", path]) == 1
    assert "arity" in capsys.readouterr().err


def test_failure_rule_exit_code(tmp_path, capsys):
    path = write(tmp_path, "f.vada", 'p(1). #F :- p(X). @output("p").')
    assert main(["run", path]) == 2


def test_guard_exit_code(tmp_path, capsys):
    path = write(tmp_path, "g.vada", """
        n(0).
        n(X) :- n(Y), Y < 1000, X = Y + 1.
        @output("n").
    """)
    assert main(["run", path, "--max-facts", "10"]) == 3


def test_missing_file_exit_code(capsys):
    assert main(["run", "/nonexistent/none.vada"]) == 4


def test_include(tmp_path, capsys):
    write(tmp_path, "mod_b.vada", '@module("mod_b.vada").\nsub_b(2).\n')
    write(tmp_path, "mod_a.vada",
          '@module("mod_a.vada").\n@include("mod_b.vada").\nsub_a(1).\n')
    main_path = write(tmp_path, "main.vada", """
        @include("mod_a.vada").
        main(X) :- sub_a(X).
        main(X) :- sub_b(X).
        @output("main").
        @post("main","orderby(1)").
    """)
    assert main(["run", main_path]) == 0
    assert capsys.readouterr().out.strip().splitlines() == ["main(1).", "main(2)."]


def test_include_cycle_is_reported(tmp_path, capsys):
    write(tmp_path, "a.vada", '@include("b.vada").\nx(1).\n')
    write(tmp_path, "b.vada", '@include("a.vada").\ny(1).\n')
    assert main(["run", str(tmp_path / "a.vada")]) == 1
    assert "cycle" in capsys.readouterr().err


def test_csv_dir_override(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "in.csv").write_text("7\n", encoding="utf-8")
    path = write(tmp_path, "p.vada", """
        a(X) :- b(X).
        @input("b").
        @bind("b", "csv", ".", "in.csv").
        @output("a").
    """)
    assert main(["run", path, "--csv-dir", str(data)]) == 0
    assert capsys.readouterr().out.strip() == 'a("7").'


def test_stats(tmp_path, capsys):
    path = write(tmp_path, "p.vada", PROGRAM)
    assert main(["run", path, "--stats"]) == 0
    assert "activations=" in capsys.readouterr().err
