"""The local web UI: routes, path safety, and the three engine actions.

The server is a sub-package of the engine, so it is imported like any other
module.  See src/vadalog/ui/README.md.
"""

import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from harness import PROGRAMS  # noqa: F401  (adds src/ to sys.path)

from vadalog.ui import server  # noqa: E402

PROGRAM = """
edge(1,2).
edge(2,3).
path(X,Y) :- edge(X,Y).
path(X,Z) :- edge(X,Y), path(Y,Z).
@output("path").
@post("path","orderby(1,2)").
"""


@pytest.fixture
def live(tmp_path):
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "reach.vada").write_text(PROGRAM, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a program", encoding="utf-8")
    httpd = server.build(str(tmp_path), port=0, tries=1)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        yield base, tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def call(base, path, method="GET", body=None, headers=True):
    data = None
    hdrs = {}
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs["X-Vadalog"] = "1"
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw


# --------------------------------------------------------------------------- #
# static + files
# --------------------------------------------------------------------------- #

def test_index_is_served(live):
    base, _ = live
    with urllib.request.urlopen(base + "/") as res:
        html = res.read().decode()
    assert res.status == 200
    assert "<title>vadalog</title>" in html
    assert "/api/run" in html


def test_editor_layers_stay_aligned(live):
    """Guard the two mistakes that made clicks land on the wrong line.

    A <code> wrapper inside the highlight layer picks up the user-agent's
    generic `monospace` family instead of the editor's, and bold or italic in
    the highlight changes glyph advance widths.  Either desynchronises the
    transparent textarea from the coloured text underneath it.
    """
    base, _ = live
    with urllib.request.urlopen(base + "/") as res:
        html = res.read().decode()

    style = html[html.index("<style>"):html.index("</style>")]
    highlight_rules = [line for line in style.splitlines()
                       if ".hl .c-" in line or ".hl span" in line]
    assert highlight_rules, "the highlight colour rules moved"
    for line in highlight_rules:
        assert "font-weight" not in line, line
        assert "font-style" not in line, line
    assert '<pre class="hl" id="hl" aria-hidden="true"></pre>' in html, \
        "the highlight layer must hold no <code> wrapper"
    assert 'wrap="off"' in html, "the textarea must not soft-wrap"


def test_list_files_finds_only_vada(live):
    base, _ = live
    code, payload = call(base, "/api/files")
    assert code == 200 and payload["ok"]
    # The API always reports forward slashes (server.py: `.replace(os.sep, "/")`),
    # on Windows too, so the expectation is a literal and not os.path.join.
    assert payload["files"] == ["examples/reach.vada"]
    assert payload["readOnly"] is False


def test_read_and_write_a_file(live):
    base, tmp = live
    rel = os.path.join("examples", "reach.vada")
    code, payload = call(base, "/api/file?path=" + rel.replace(os.sep, "/"))
    assert code == 200 and "edge(1,2)." in payload["text"]

    code, payload = call(base, "/api/file?path=" + rel.replace(os.sep, "/"),
                         method="PUT", body=b"p(1).\n@output(\"p\").\n")
    assert code == 200 and payload["ok"]
    assert (tmp / "examples" / "reach.vada").read_text() == 'p(1).\n@output("p").\n'


def test_creating_a_new_file(live):
    base, tmp = live
    code, payload = call(base, "/api/file?path=scratch/new.vada",
                         method="PUT", body=b"% hello\n")
    assert code == 200 and payload["ok"]
    assert (tmp / "scratch" / "new.vada").read_text() == "% hello\n"


def test_directory_listing(live):
    """One folder at a time, as the file dialog walks it: sub-folders and
    .vada files only, hidden and tool folders left out."""
    base, tmp = live
    (tmp / "examples" / "data").mkdir()
    # write_bytes, not write_text: on Windows text mode turns "\n" into "\r\n"
    # and the size asserted below would be 5 instead of 4.
    (tmp / "examples" / "data" / "x.csv").write_bytes(b"a,b\n")
    (tmp / "empty").mkdir()
    (tmp / ".git").mkdir()
    (tmp / "__pycache__").mkdir()

    code, payload = call(base, "/api/dir")
    assert code == 200 and payload["ok"]
    assert payload["path"] == "" and payload["root"] == tmp.name
    assert payload["dirs"] == ["empty", "examples"]
    assert payload["files"] == [], "notes.txt is not a program"

    code, payload = call(base, "/api/dir?path=examples")
    assert payload["path"] == "examples"
    assert payload["dirs"] == ["data"] and payload["files"] == ["reach.vada"]

    code, payload = call(base, "/api/dir?path=examples/data/")
    assert payload["path"] == "examples/data"
    assert payload["dirs"] == [] and payload["files"] == []

    code, payload = call(base, "/api/dir?kind=data&path=examples/data")
    assert payload["files"] == ["x.csv"] and payload["sizes"] == [4]
    code, payload = call(base, "/api/dir?kind=vada&path=examples")
    assert payload["files"] == ["reach.vada"]
    assert call(base, "/api/dir?kind=exe")[0] == 400


@pytest.mark.parametrize("rel", ["..", "../x", "/etc", "examples/../.."])
def test_directory_listing_stays_inside_the_root(live, rel):
    base, _ = live
    code, _payload = call(base, "/api/dir?path=" + urllib.request.quote(rel))
    assert code == 403, rel


@pytest.mark.parametrize("rel", ["nope", "examples/reach.vada"])
def test_directory_listing_of_a_missing_folder(live, rel):
    base, _ = live
    assert call(base, "/api/dir?path=" + rel)[0] == 404


# --------------------------------------------------------------------------- #
# path safety and the CSRF guard
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", [
    "../secrets.vada", "/etc/passwd.vada", "examples/../../x.vada",
    "notes.txt", "", "examples/reach.txt",
])
def test_paths_outside_the_root_are_refused(live, rel):
    base, _ = live
    code, _payload = call(base, "/api/file?path=" + urllib.request.quote(rel))
    assert code == 403, rel


def test_safe_path_unit(tmp_path):
    root = str(tmp_path)
    (tmp_path / "a").mkdir()
    assert server.safe_path(root, "a/x.vada").startswith(os.path.realpath(root))
    for bad in ["../x.vada", "/x.vada", "a/../../x.vada", "x.txt", ""]:
        with pytest.raises(server.PathRefused):
            server.safe_path(root, bad)


def test_write_without_the_header_is_refused(live):
    base, _ = live
    code, _ = call(base, "/api/file?path=examples/reach.vada",
                   method="PUT", body=b"x", headers=False)
    assert code == 403
    code, _ = call(base, "/api/run", method="POST",
                   body={"program": "p(1)."}, headers=False)
    assert code == 403


def test_read_only_server_refuses_writes(tmp_path):
    (tmp_path / "p.vada").write_text('p(1). @output("p").', encoding="utf-8")
    httpd = server.build(str(tmp_path), port=0, tries=1, read_only=True)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        code, payload = call(base, "/api/files")
        assert payload["readOnly"] is True
        code, _ = call(base, "/api/file?path=p.vada", method="PUT", body=b"q(2).")
        assert code == 403
        code, payload = call(base, "/api/run", method="POST",
                             body={"program": 'p(1). @output("p").'})
        assert code == 200 and payload["ok"], "a read-only server still evaluates"
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=5)


def test_unknown_route(live):
    base, _ = live
    assert call(base, "/api/nope")[0] == 404


# --------------------------------------------------------------------------- #
# run / check / explain
# --------------------------------------------------------------------------- #

def test_run_returns_relations_and_stats(live):
    base, _ = live
    code, payload = call(base, "/api/run", method="POST", body={"program": PROGRAM})
    assert code == 200 and payload["ok"], payload
    rel = payload["relations"][0]
    assert rel["name"] == "path" and rel["count"] == 3
    assert rel["facts"] == ["path(1,2).", "path(1,3).", "path(2,3)."]
    assert rel["truncated"] is False
    assert payload["stats"]["facts"] > 0
    assert isinstance(payload["elapsedMs"], float)


def test_run_reports_a_static_error_with_a_position(live):
    base, _ = live
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": 'p(1).\np(1,2).\n@output("p").\n'})
    assert code == 200 and payload["ok"] is False
    assert payload["error"]["kind"] == "static"
    assert "arity" in payload["error"]["message"]


def test_run_reports_a_parse_error_with_a_line(live):
    base, _ = live
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": "p(1).\nq(X) :- .\n"})
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "parse"
    assert payload["error"]["line"] == 2


def test_run_reports_a_failure_rule(live):
    base, _ = live
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": 'p(1).\n#F :- p(X).\n@output("p").\n'})
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "runtime"


def test_limits_are_enforced(live):
    base, _ = live
    program = 'n(0).\nn(X) :- n(Y), Y < 100000, X = Y + 1.\n@output("n").\n'
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": program, "limits": {"maxFacts": 25}})
    assert payload["ok"] is False
    assert payload["error"]["kind"] == "resource"


def test_allow_unstratified_flag(live):
    base, _ = live
    program = ('b(1).\np(X) :- b(X), not q(X).\nq(X) :- b(X), not p(X).\n'
               '@output("p").\n@output("q").\n')
    code, payload = call(base, "/api/run", method="POST", body={"program": program})
    assert payload["ok"] is False and "stratifiable" in payload["error"]["message"]
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": program, "limits": {"allowUnstratified": True}})
    assert payload["ok"] is True


def test_output_is_truncated(live, monkeypatch):
    base, _ = live
    monkeypatch.setattr(server, "MAX_FACTS_SHOWN", 3)
    program = 'n(0).\nn(X) :- n(Y), Y < 20, X = Y + 1.\n@output("n").\n'
    code, payload = call(base, "/api/run", method="POST", body={"program": program})
    rel = payload["relations"][0]
    assert rel["count"] == 21 and rel["shown"] == 3 and rel["truncated"] is True


def test_warnings_are_returned(live):
    base, _ = live
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": 'p(1).\n@output("p").\n@sne.\n'})
    assert payload["ok"] and any("@sne" in w for w in payload["warnings"])


def test_check(live):
    base, _ = live
    code, payload = call(base, "/api/check", method="POST", body={"program": PROGRAM})
    assert payload["ok"]
    assert "strata:     1" in payload["text"]
    assert "recursive:  path" in payload["text"]


def test_explain(live):
    base, _ = live
    code, payload = call(base, "/api/explain", method="POST", body={"program": PROGRAM})
    assert payload["ok"] and "stratum 0:" in payload["text"]


def test_csv_binding_resolves_next_to_the_open_file(live):
    base, tmp = live
    (tmp / "examples" / "in.csv").write_text("7\n8\n", encoding="utf-8")
    program = ('a(X) :- b(X).\n@input("b").\n@bind("b","csv",".","in.csv").\n'
               '@output("a").\n@post("a","orderby(1)").\n')
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": program, "path": "examples/reach.vada"})
    assert payload["ok"], payload
    assert payload["relations"][0]["facts"] == ['a("7").', 'a("8").']


def test_include_resolves_next_to_the_open_file(live):
    base, tmp = live
    (tmp / "examples" / "mod.vada").write_text("sub(42).\n", encoding="utf-8")
    program = '@include("mod.vada").\nmain(X) :- sub(X).\n@output("main").\n'
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": program, "path": "examples/reach.vada"})
    assert payload["ok"], payload
    assert payload["relations"][0]["facts"] == ["main(42)."]


def test_malformed_json_body(live):
    base, _ = live
    code, _payload = call(base, "/api/run", method="POST", body=b"{nope")
    assert code == 400


def test_written_csv_files_are_reported(live, tmp_path):
    base, tmp = live
    program = ('a(1).\nb(X) :- a(X).\n@output("b").\n'
               '@bind("b","csv",".","out.csv").\n')
    code, payload = call(base, "/api/run", method="POST",
                         body={"program": program, "path": "examples/reach.vada"})
    assert payload["ok"]
    assert payload["written"] and payload["written"][0].endswith("out.csv")
    assert (tmp / "examples" / "out.csv").read_text() == "1\n"
