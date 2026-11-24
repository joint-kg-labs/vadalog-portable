"""Parameterised programs: placeholders `${name}` (SPECIFICATION.md sec. 11.8)."""

import datetime
import glob
import json
import os
import threading
import urllib.request

import pytest

from harness import PROGRAMS  # noqa: F401  (adds src/ to sys.path)

from vadalog.chase import Options                                   # noqa: E402
from vadalog.cli import main                                        # noqa: E402
from vadalog.errors import (LexError, ParameterError, ParseError,   # noqa: E402
                            VadalogError)
from vadalog.parser import parse                                    # noqa: E402
from vadalog.params import (load_json, normalize, parse_assignment,  # noqa: E402
                            parse_literal, parse_literals,
                            parse_string_assignment)
from vadalog.program import (Runner, load_program, load_text,       # noqa: E402
                             run_file, run_text)


def run(text, params=None, base_dir=None):
    program = load_text(text, params=params)
    return Runner(program, Options(), base_dir=base_dir or os.getcwd()).run()


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
# Placeholders where a term goes
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value", [
    0, 42, -7, 2.5, -0.125, 1e-05, "Acme", 'say "hi" \\ there', "àé€ 日本",
    "", True, False,
    datetime.datetime(2024, 1, 31), datetime.datetime(2024, 1, 31, 12, 30, 5),
])
def test_every_literal_kind_round_trips(value):
    result = run('p(${V}). @output("p").', {"V": value})
    assert result.relations["p"] == [(value,)]


def test_a_date_is_taken_as_a_date():
    result = run('p(${D}). @output("p").', {"D": datetime.date(2024, 2, 29)})
    assert result.relations["p"] == [(datetime.datetime(2024, 2, 29),)]


def test_placeholders_in_body_conditions_and_head():
    text = """
    edge(1,2,0.5). edge(2,3,0.1). edge(3,1,0.9).
    cl(${X}, Y, W) :- edge(X, Y, W), X = ${X}, W >= ${T}.
    @output("cl").
    """
    result = run(text, {"X": 1, "T": 0.2})
    assert result.relations["cl"] == [(1, 2, 0.5)]


def test_placeholders_in_arithmetic_including_negative_values():
    text = """
    n(10).
    a(Y) :- n(X), Y = X - ${K}.
    b(Y) :- n(X), Y = X * ${K}.
    c(Y) :- n(X), Y = ${K} + X.
    @output("a"). @output("b"). @output("c").
    """
    result = run(text, {"K": -3})
    assert result.relations == {"a": [(13,)], "b": [(-30,)], "c": [(7,)]}


def test_same_placeholder_used_many_times():
    result = run('p(${X}, ${X}). q(Y) :- p(Y, ${X}). @output("q").', {"X": "k"})
    assert result.relations["q"] == [("k",)]


def test_placeholder_as_an_annotation_argument():
    text = 'p(3). p(1). p(2). @output("p"). @post("p", ${O}).'
    result = run(text, {"O": "orderby(1)"})
    assert result.relations["p"] == [(1,), (2,), (3,)]


def test_a_comment_is_not_scanned():
    result = run('% p(${NOPE}).\np(1). @output("p").')
    assert result.relations["p"] == [(1,)]


# --------------------------------------------------------------------------- #
# Values cannot change the shape of the program
# --------------------------------------------------------------------------- #

def test_a_value_that_looks_like_code_stays_one_constant():
    hostile = '1), evil("x'
    result = run('p(${V}). @output("p").', {"V": hostile})
    assert result.relations["p"] == [(hostile,)]


def test_a_value_cannot_break_out_of_a_string():
    hostile = 'p"). @output("q'
    program = load_text('p(1). @output("${O}").', params={"O": hostile})
    outputs = [a.args[0] for a in program.annotations if a.name == "output"]
    assert outputs == [hostile]


@pytest.mark.parametrize("text", ["1), evil(X", "1 2", "p(1)", "Acme", "X",
                                  "[1,2]", "{1}", "${X}", "", "-", "-\"a\""])
def test_a_literal_must_be_exactly_one_literal(text):
    with pytest.raises(ParameterError) as exc:
        parse_literal(text, "V")
    assert exc.value.names == ["V"]


@pytest.mark.parametrize("text, value", [
    ("42", 42), ("-42", -42), ("0.5", 0.5), ("-0.5", -0.5), ('"Acme"', "Acme"),
    ('"a\\"b"', 'a"b'), ("2024-01-31", datetime.datetime(2024, 1, 31)),
    ("2024-01-31 08:00:00", datetime.datetime(2024, 1, 31, 8)), ("#T", True),
    ("#F", False), ("  7  ", 7),
])
def test_literals_accepted(text, value):
    assert parse_literal(text.strip()) == value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), None, [1], {"a": 1},
                                   {1}, object()])
def test_unusable_values_are_refused(value):
    with pytest.raises(ParameterError):
        normalize({"V": value})


@pytest.mark.parametrize("name", ["", "a-b", "a b", "x.y", "$X", None])
def test_bad_names_are_refused(name):
    with pytest.raises(ParameterError):
        normalize({name: 1})


# --------------------------------------------------------------------------- #
# Where a placeholder may not go
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    "p_${X}(1).", "a${X}.", "p(${X}1).", "p(1${X}).", "${X}(1).",
    "q(Y) :- ${X} (Y).", "q(Y) :- p(Y), Y = f${X}.",
])
def test_a_placeholder_is_a_whole_constant(text):
    with pytest.raises(LexError) as exc:
        parse(text, params={"X": 1})
    assert "${X}" in exc.value.message


@pytest.mark.parametrize("text", ["p(${}).", "p(${a-b}).", "p(${X).", "p(${ X })."])
def test_malformed_placeholders(text):
    with pytest.raises(LexError) as exc:
        parse(text, params={"X": 1})
    assert "placeholder" in exc.value.message


# --------------------------------------------------------------------------- #
# Missing values
# --------------------------------------------------------------------------- #

def test_all_missing_names_are_reported_at_once():
    with pytest.raises(ParameterError) as exc:
        load_text('a(${A}).\nb(${B}) :- a(${A}), X = ${C}.', params={"B": 1})
    err = exc.value
    assert err.names == ["A", "C"]
    assert (err.line, err.col) == (1, 3)
    assert "A, C" in err.message
    assert isinstance(err, ParseError) and isinstance(err, VadalogError)


def test_missing_names_across_include(tmp_path):
    write(tmp_path / "lib.vada", "base(${LIB}).\n")
    main_file = write(tmp_path / "main.vada",
                      '@include("lib.vada").\np(${MAIN}) :- base(_).\n@output("p").\n')
    with pytest.raises(ParameterError) as exc:
        load_program(main_file)
    assert sorted(exc.value.names) == ["LIB", "MAIN"]


def test_lenient_load_lists_instead_of_failing():
    program = load_text('a(${A}). @output("${O}").', lenient=True)
    report = program.parameters
    assert report.names() == ["A", "O"]
    assert list(report.missing) == ["A"]


def test_unused_value_is_a_warning():
    result = run('p(1). @output("p").', {"EXTRA": 1})
    assert any("EXTRA" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Inside string literals
# --------------------------------------------------------------------------- #

def test_interpolation_inside_strings():
    text = 'p("${A}-${B}-${C}"). @output("p").'
    result = run(text, {"A": "x", "B": 3, "C": True})
    assert result.relations["p"] == [("x-3-#T",)]


def test_interpolated_value_is_escaped_inside_the_string():
    result = run('p("<${A}>"). @output("p").', {"A": 'q"\\n'})
    assert result.relations["p"] == [('<q"\\n>',)]


@pytest.mark.parametrize("inner", [
    "where id = ${1}",      # how @qbind writes its own row parameters
    "load ${file} later",   # a valid name, but no value supplied
])
def test_unresolved_inside_a_string_is_left_as_written(inner):
    text = 'p("%s"). @output("p").' % inner
    assert run(text).relations["p"] == [(inner,)]
    assert run(text, {"X": 1}).relations["p"] == [(inner,)]


def test_dollar_dollar_escapes_a_placeholder():
    text = 'p("$${X} and ${X}"). @output("p").'
    assert run(text, {"X": 5}).relations["p"] == [("${X} and 5",)]
    assert run(text).relations["p"] == [("${X} and ${X}",)]


def test_parameterised_bind_path(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "edges_2024.csv").write_text("1,2\n2,3\n", encoding="utf-8")
    (tmp_path / "data" / "edges_2025.csv").write_text("7,8\n", encoding="utf-8")
    path = write(tmp_path / "p.vada", """
        @input("e").
        @bind("e", "csv", "data", "edges_${year}.csv").
        r(X,Y) :- e(X,Y).
        @output("r").
        """)
    assert len(run_file(path, params={"year": 2024}).relations["r"]) == 2
    assert run_file(path, params={"year": "2025"}).relations["r"] == [("7", "8")]


def test_parameterised_output_names():
    # The reference test RunProgramsAsLibrary.testVeryBasicWithParameters.
    text = 'a(${parZ}).\na(2).\nb(X) :- a(X).\nc(X) :- a(X).\n' \
           '@output("${parX}").\n@output("${parY}").\n'
    result = run_text(text, params={"parX": "b", "parY": "c", "parZ": 1})
    assert result.relations == {"b": [(1,), (2,)], "c": [(1,), (2,)]}


# --------------------------------------------------------------------------- #
# Error positions are those of the source
# --------------------------------------------------------------------------- #

def test_positions_after_a_long_value_are_unchanged():
    text = "p(${V}). q(1) r."
    with pytest.raises(ParseError) as exc:
        parse(text, params={"V": "x" * 50})
    assert (exc.value.line, exc.value.col) == (1, 15)


def test_positions_after_a_negative_value_are_unchanged():
    text = "p(${V}).\nq(${V}) :- p(X), $"
    with pytest.raises(LexError) as exc:
        parse(text, params={"V": -12345})
    assert (exc.value.line, exc.value.col) == (2, 18)


# --------------------------------------------------------------------------- #
# @include
# --------------------------------------------------------------------------- #

def test_values_reach_included_files(tmp_path):
    write(tmp_path / "lib.vada", 'base(${X}).\n@output("${OUT}").\n')
    main_file = write(tmp_path / "main.vada",
                      '@include("lib.vada").\nderived(Y) :- base(Y), Y = ${X}.\n')
    result = run_file(main_file, params={"X": 9, "OUT": "derived"})
    assert result.relations == {"derived": [(9,)]}


def test_no_parameters_changes_nothing(tmp_path):
    text = 'edge(1,2). path(X,Y) :- edge(X,Y). @output("path").'
    assert run(text).relations == run(text, {}).relations == {"path": [(1, 2)]}


# --------------------------------------------------------------------------- #
# Values given as text: -p, -s, JSON, the UI's fields
# --------------------------------------------------------------------------- #

def test_parse_assignment():
    assert parse_assignment("X=42") == ("X", 42)
    assert parse_assignment(' X = "a=b" ') == ("X", "a=b")
    for bad in ("X", "=1", "a b=1", "X=Acme"):
        with pytest.raises(ParameterError):
            parse_assignment(bad)


def test_parse_string_assignment():
    assert parse_string_assignment("F=data/x=1.csv") == ("F", "data/x=1.csv")
    assert parse_string_assignment("F=") == ("F", "")
    with pytest.raises(ParameterError):
        parse_string_assignment("no-equals")


def test_parse_literals_mapping():
    assert parse_literals({"A": "1", "B": '"b"'}) == {"A": 1, "B": "b"}
    with pytest.raises(ParameterError):
        parse_literals({"A": 1})
    with pytest.raises(ParameterError):
        parse_literals(["A"])


def test_load_json(tmp_path):
    path = write(tmp_path / "p.json", json.dumps(
        {"S": "42", "I": 42, "F": 0.5, "B": False}))
    assert load_json(path) == {"S": "42", "I": 42, "F": 0.5, "B": False}
    for bad in ("[1]", '{"A": null}', '{"A": [1]}', "{nope"):
        write(tmp_path / "bad.json", bad)
        with pytest.raises(ParameterError):
            load_json(str(tmp_path / "bad.json"))
    with pytest.raises(VadalogError):
        load_json(str(tmp_path / "missing.json"))


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #

PROGRAM = """
edge(1,2). edge(2,3). edge(3,4).
from(Y) :- edge(X,Y), X = ${START}.
@output("${OUT}").
"""


def test_cli_run_with_values(tmp_path, capsys):
    path = write(tmp_path / "p.vada", PROGRAM)
    assert main(["run", path, "-p", "START=2", "-s", "OUT=from"]) == 0
    assert capsys.readouterr().out.split() == ["from(3)."]


def test_cli_json_file_and_precedence(tmp_path, capsys):
    path = write(tmp_path / "p.vada", PROGRAM)
    params = write(tmp_path / "p.json", json.dumps({"START": 1, "OUT": "from"}))
    assert main(["run", path, "--params", params]) == 0
    assert capsys.readouterr().out.split() == ["from(2)."]
    assert main(["run", path, "--params", params, "-p", "START=3"]) == 0
    assert capsys.readouterr().out.split() == ["from(4)."]


def test_cli_missing_values_fail(tmp_path, capsys):
    path = write(tmp_path / "p.vada", PROGRAM)
    assert main(["run", path]) == 1
    err = capsys.readouterr().err
    assert "missing value for parameter START" in err


def test_cli_bad_literal(tmp_path, capsys):
    path = write(tmp_path / "p.vada", PROGRAM)
    assert main(["run", path, "-p", "START=two", "-s", "OUT=from"]) == 1
    assert "not a Vadalog literal" in capsys.readouterr().err


def test_cli_check_lists_parameters(tmp_path, capsys):
    path = write(tmp_path / "p.vada", PROGRAM)
    assert main(["check", path]) == 0
    out = capsys.readouterr().out
    assert "parameters:" in out
    assert "${START} (no value)" in out
    assert "${OUT} (no value; left as written inside strings)" in out
    assert out.rstrip().endswith("missing parameter values")
    assert main(["check", path, "-p", "START=2", "-s", "OUT=from"]) == 0
    out = capsys.readouterr().out
    assert "${START} = 2" in out and '${OUT} = "from"' in out
    assert out.rstrip().endswith("ok")


def test_cli_check_without_placeholders_is_unchanged(tmp_path, capsys):
    path = write(tmp_path / "p.vada", 'p(1). @output("p").')
    assert main(["check", path]) == 0
    out = capsys.readouterr().out
    assert "parameters" not in out and out.rstrip().endswith("ok")


def test_cli_explain_with_values(tmp_path, capsys):
    path = write(tmp_path / "p.vada", PROGRAM)
    assert main(["explain", path, "-p", "START=2", "-s", "OUT=from"]) == 0
    assert "X = 2" in capsys.readouterr().out.replace("X=2", "X = 2")


def test_cli_unused_value_warns(tmp_path, capsys):
    path = write(tmp_path / "p.vada", 'p(1). @output("p").')
    assert main(["run", path, "-p", "NOPE=1"]) == 0
    assert "parameter NOPE is supplied" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Web UI server
# --------------------------------------------------------------------------- #

@pytest.fixture
def live(tmp_path):
    from vadalog.ui import server
    httpd = server.build(str(tmp_path), port=0, tries=1)
    thread = threading.Thread(target=httpd.serve_forever,
                              kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % httpd.server_address[1], tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-Vadalog": "1"}, method="POST")
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())


def test_ui_run_with_literals(live):
    base, _ = live
    r = post(base, "/api/run", {"program": PROGRAM,
                                "paramLiterals": {"START": "2", "OUT": '"from"'}})
    assert r["ok"], r
    assert r["relations"][0]["facts"] == ["from(3)."]
    assert {p["name"] for p in r["parameters"]} == {"START", "OUT"}


def test_ui_run_with_typed_values_and_precedence(live):
    base, _ = live
    r = post(base, "/api/run", {"program": PROGRAM,
                                "params": {"START": 1, "OUT": "from"},
                                "paramLiterals": {"START": "3"}})
    assert r["ok"], r
    assert r["relations"][0]["facts"] == ["from(4)."]


def test_ui_missing_values(live):
    base, _ = live
    r = post(base, "/api/run", {"program": PROGRAM})
    assert not r["ok"]
    assert r["error"]["kind"] == "parameters"
    assert r["error"]["parameters"] == ["START"]
    assert r["error"]["line"] == 3


def test_ui_bad_literal(live):
    base, _ = live
    r = post(base, "/api/run", {"program": PROGRAM,
                                "paramLiterals": {"START": "two", "OUT": '"from"'}})
    assert r["error"]["kind"] == "parameters"
    assert r["error"]["parameters"] == ["START"]


def test_ui_check_lists_parameters(live):
    base, _ = live
    r = post(base, "/api/check", {"program": PROGRAM, "paramLiterals": {"START": "1"}})
    assert r["ok"], r
    assert r["parameters"] == [
        {"name": "START", "supplied": True, "inStringsOnly": False},
        {"name": "OUT", "supplied": False, "inStringsOnly": True}]


def test_ui_page_has_the_parameters_panel(live):
    base, _ = live
    with urllib.request.urlopen(base + "/") as res:
        page = res.read().decode()
    assert 'id="paramsBtn"' in page and 'id="params"' in page
    assert "paramLiterals" in page


# --------------------------------------------------------------------------- #
# The programs in the repository
# --------------------------------------------------------------------------- #

ROOT = os.path.join(os.path.dirname(__file__), "..")
REPO_PROGRAMS = sorted(
    os.path.relpath(p, ROOT).replace(os.sep, "/")
    for d in ("examples", "benchmark")
    for p in glob.glob(os.path.join(ROOT, d, "**", "*.vada"), recursive=True))


def test_the_repository_has_programs_to_check():
    assert len(REPO_PROGRAMS) > 40


@pytest.mark.parametrize("rel", REPO_PROGRAMS)
def test_programs_without_placeholders_parse_as_before(rel):
    """No regression: a program with no placeholders parses without values and
    never asks for any."""
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        parse(fh.read(), source=rel)
