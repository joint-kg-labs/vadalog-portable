"""A local web front end for vadalog-portable.

    vadalog ui                       # or:  python3 -m vadalog.ui

Serves one page on 127.0.0.1 and evaluates programs in-process, so diagnostics
come back with their source position instead of being scraped from stderr.
Standard library only, like the engine itself.  See README.md beside this file.
"""

import csv
import io
import json
import os
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):                       # run as a plain script
    _here = os.path.dirname(os.path.abspath(__file__))          # src/vadalog/ui
    _src = os.path.dirname(os.path.dirname(_here))              # src
    if os.path.isdir(os.path.join(_src, "vadalog")) and _src not in sys.path:
        sys.path.insert(0, _src)

from vadalog.ast import Var                                          # noqa: E402
from vadalog.chase import Options                                    # noqa: E402
from vadalog.errors import (DataSourceError, ParameterError,         # noqa: E402
                            ParseError, ResourceExceeded, RuntimeFailure,
                            StaticError, VadalogError)
from vadalog.params import normalize, parse_literals                 # noqa: E402
from vadalog.program import (Runner, describe_check,                 # noqa: E402
                             describe_explain, load_text)
from vadalog.values import (BOOLEAN, DATE, DOUBLE, INT, STRING,      # noqa: E402
                            UNKNOWN, format_fact, to_string, vtype)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")


def read_index():
    """The page, read as a package resource so it also works from a .pyz.

    Inside a zipapp there is no file to open: `index.html` lives in the archive.
    Three routes are tried, in this order and for these reasons.

    1. **The module loader.**  ``get_data`` is implemented by the loader that
       imported this module, so it reads from wherever the module itself came
       from, and it is the only route that is correct on every version.  The
       path must be built from ``__file__`` as it stands, *not* from its
       absolute form: under zipimport ``__file__`` keeps the spelling of the
       archive as it was invoked (``dist/vadalog.pyz/vadalog/ui/server.py``),
       and ``zipimport.get_data`` finds the entry by stripping exactly that
       prefix.  Making it absolute first breaks the match.
    2. **importlib.resources**, for a loader with no ``get_data``.  Not first,
       because on Python 3.9 and 3.10 for Windows it joins the path inside the
       archive with the *platform* separator and then looks for
       ``vadalog\\ui/index.html`` in an archive whose entry is
       ``vadalog/ui/index.html``, which raises ``KeyError``.
    3. **The plain file**, for a source checkout, which is also what makes an
       edit to the page show up on a reload.
    """
    loader_data = getattr(getattr(sys.modules[__name__], "__loader__", None),
                          "get_data", None)
    if loader_data is not None:
        try:
            return loader_data(os.path.join(os.path.dirname(__file__), "index.html"))
        except Exception:
            pass

    if __package__:
        try:
            from importlib.resources import files
            return (files(__package__) / "index.html").read_bytes()
        except Exception:
            pass

    with open(INDEX, "rb") as fh:
        return fh.read()


MAX_FACTS_SHOWN = 2000          # per relation, before the panel is truncated
MAX_PROGRAM_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_FACTS = 200_000
TIMEOUT_CEILING = 300.0
FACTS_CEILING = 20_000_000

# The engine keeps a little global state (the marked-null counter, the rule-id
# counter), so evaluations are serialised.  File reads are not.
_engine_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Engine calls
# --------------------------------------------------------------------------- #

_KINDS = [(ParameterError, "parameters"), (ParseError, "parse"), (StaticError, "static"),
          (ResourceExceeded, "resource"), (DataSourceError, "io"),
          (RuntimeFailure, "runtime")]


def _error_payload(exc):
    kind = "error"
    for cls, name in _KINDS:
        if isinstance(exc, cls):
            kind = name
            break
    error = {
        "kind": kind,
        "message": getattr(exc, "message", None) or str(exc),
        "line": getattr(exc, "line", None),
        "col": getattr(exc, "col", None),
        "source": getattr(exc, "source", None),
    }
    if isinstance(exc, ParameterError):
        error["parameters"] = exc.names
    return {"ok": False, "error": error}


def _limits(body):
    raw = body.get("limits") or {}
    timeout = float(raw.get("timeout", DEFAULT_TIMEOUT) or 0)
    max_facts = int(raw.get("maxFacts", DEFAULT_MAX_FACTS) or 0)
    return Options(
        timeout=min(max(timeout, 0.0), TIMEOUT_CEILING),
        max_facts=min(max(max_facts, 0), FACTS_CEILING),
        allow_unstratified=bool(raw.get("allowUnstratified")),
    )


def _params(body):
    """Parameter values (sec. 11.8): `params` holds JSON-typed values (a JSON
    string is a string); `paramLiterals` holds Vadalog literals as text, as
    typed in the editor's parameter fields, and wins on conflicts."""
    values = normalize(body.get("params") or None)
    values.update(parse_literals(body.get("paramLiterals") or {}))
    return values


def _param_list(program):
    report = program.parameters
    if report is None:
        return []
    return [{"name": name, "supplied": report.has(name),
             "inStringsOnly": name not in report.terms}
            for name in report.names()]


def _prepare(body, root, lenient=False):
    """Parse the editor text into a Runner, resolving @bind and @include."""
    text = body.get("program") or ""
    if len(text.encode("utf-8")) > MAX_PROGRAM_BYTES:
        raise DataSourceError("the program is larger than this UI will accept")
    rel = body.get("path") or None
    source = os.path.join(root, rel) if rel else "<editor>"
    base_dir = os.path.dirname(source) if rel else root
    program = load_text(text, source=source, base_dir=base_dir,
                        params=_params(body), lenient=lenient)
    return program, base_dir


def do_run(body, root):
    with _engine_lock:
        started = time.monotonic()
        program, base_dir = _prepare(body, root)
        runner = Runner(program, _limits(body), base_dir=base_dir)
        result = runner.run()
        elapsed = (time.monotonic() - started) * 1000.0

    relations = []
    for name in runner.bindings.outputs:
        rows = result.relations.get(name, [])
        shown = rows[:MAX_FACTS_SHOWN]
        relations.append({
            "name": name,
            "count": len(rows),
            "shown": len(shown),
            "truncated": len(rows) > len(shown),
            "facts": [format_fact(name, tup) for tup in shown],
        })
    return {"ok": True, "relations": relations,
            "parameters": _param_list(program),
            "warnings": result.warnings,
            "written": result.written,
            "stats": result.stats,
            "elapsedMs": round(elapsed, 1)}


def do_check(body, root):
    with _engine_lock:
        program, base_dir = _prepare(body, root, lenient=True)
        runner = Runner(program, _limits(body), base_dir=base_dir)
        info = runner.prepare()
        text = describe_check(program, runner, info)
        warnings = list(runner.bindings.warnings)
    return {"ok": True, "text": text, "warnings": warnings,
            "parameters": _param_list(program)}


def do_explain(body, root):
    with _engine_lock:
        program, base_dir = _prepare(body, root)
        runner = Runner(program, _limits(body), base_dir=base_dir)
        info = runner.prepare()
        text = describe_explain(info)
        warnings = list(runner.bindings.warnings)
    return {"ok": True, "text": text, "warnings": warnings,
            "parameters": _param_list(program)}


# --------------------------------------------------------------------------- #
# Describing the relations a program derives
#
# The output side of the source dialog needs, for a relation that does not
# exist on disk yet: how wide it is, what its columns should be called, and
# what type each one holds.  Width and names come from the rule heads, which is
# static and cheap.  Types come from the values themselves, which means running
# the program — so the chase is run with the output list emptied, which keeps
# `@bind`-ed outputs from being written behind the user's back.
# --------------------------------------------------------------------------- #

_TYPE_NAME = {INT: "int", DOUBLE: "double", STRING: "string",
              BOOLEAN: "boolean", DATE: "date"}

SAMPLE_TUPLES = 500


def _merge_type(a, b):
    if a is None or a == b:
        return b
    if {a, b} == {"int", "double"}:
        return "double"
    return "string"


def _identifier(raw, position, taken):
    name = re.sub(r"[^a-z0-9_]+", "_", (raw or "").lower()).strip("_")
    if not name:
        name = "col%d" % position
    candidate, n = name, 2
    while candidate in taken:
        candidate = "%s_%d" % (name, n)
        n += 1
    taken.add(candidate)
    return candidate


def _column_names(program, pred, arity):
    """Head variable names, which are what the author already called these."""
    found = [None] * arity
    for rule in program.rules:
        for atom in rule.head or []:
            if atom.name != pred or atom.arity != arity:
                continue
            for i, term in enumerate(atom.terms):
                if found[i] is None and isinstance(term, Var):
                    found[i] = term.name
        if all(found):
            break
    taken = set()
    return [_identifier(found[i], i, taken) for i in range(arity)]


def _describe(rows, arity):
    """Type and first value of every column, over a sample of the relation."""
    types = [None] * arity
    samples = [""] * arity
    nulls = [False] * arity
    for tup in rows[:SAMPLE_TUPLES]:
        for i, value in enumerate(tup[:arity]):
            kind = vtype(value)
            if kind == UNKNOWN:
                nulls[i] = True
                continue
            types[i] = _merge_type(types[i], _TYPE_NAME.get(kind, "string"))
            if not samples[i]:
                samples[i] = to_string(value)[:40]
    return types, samples, nulls


def do_relations(body, root):
    with _engine_lock:
        program, base_dir = _prepare(body, root)
        runner = Runner(program, _limits(body), base_dir=base_dir)
        info = runner.prepare()
        outputs, bound = list(runner.bindings.outputs), set(runner.bindings.binds)
        warnings = list(runner.bindings.warnings)

        ran, note, instance = False, None, None
        if body.get("run", True):
            runner.bindings.outputs = []        # nothing is emitted, nothing written
            try:
                runner.run()
                instance = runner.chase.instance
                ran = True
            except VadalogError as exc:
                note = ("the program does not run at the moment, so the column "
                        "types below are guesses: "
                        + (getattr(exc, "message", None) or str(exc)))

    order = []
    for rule in program.rules:
        for atom in rule.head or []:
            if atom.name in info.idb and atom.name not in order:
                order.append(atom.name)
    order += sorted(n for n in info.idb if n not in order)

    relations = []
    for name in order:
        arity = info.arity.get(name, 0)
        if not arity:
            continue
        rel = instance.rels.get(name) if instance is not None else None
        rows = list(rel.facts) if rel is not None else []
        types, samples, nulls = _describe(rows, arity)
        names = _column_names(program, name, arity)
        relations.append({
            "name": name,
            "arity": arity,
            "count": len(rows) if ran else None,
            "output": name in outputs,
            "bound": name in bound,
            "columns": [{"name": names[i], "type": types[i] or "string",
                         "sample": samples[i], "nulls": nulls[i]}
                        for i in range(arity)],
        })
    return {"ok": True, "ran": ran, "note": note,
            "relations": relations, "warnings": warnings}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

class PathRefused(Exception):
    pass


PROGRAM_EXTS = (".vada",)
DATA_EXTS = (".csv", ".tsv")


def safe_path(root, rel, exts=PROGRAM_EXTS):
    """Resolve `rel` under `root`, refusing anything that escapes it."""
    if not rel or rel.startswith(("/", "\\")) or ".." in rel.replace("\\", "/").split("/"):
        raise PathRefused("path %r is not inside the project" % rel)
    full = os.path.realpath(os.path.join(root, rel))
    base = os.path.realpath(root)
    if full != base and not full.startswith(base + os.sep):
        raise PathRefused("path %r is not inside the project" % rel)
    if not full.lower().endswith(exts):
        raise PathRefused("this route only accepts %s files"
                          % " / ".join(e.lstrip(".") for e in exts))
    return full


SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules",
             ".pytest_cache", "build", "dist"}


def list_files(root, exts, limit=800):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(exts):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                out.append(rel.replace(os.sep, "/"))
                if len(out) >= limit:
                    return out
    return out


def list_programs(root, limit=800):
    return list_files(root, PROGRAM_EXTS, limit)


def safe_dir(root, rel):
    """Resolve the folder `rel` under `root`; the empty path is the root."""
    rel = (rel or "").replace("\\", "/").strip()
    if rel.startswith("/") or ".." in rel.split("/"):
        raise PathRefused("path %r is not inside the project" % rel)
    base = os.path.realpath(root)
    full = os.path.realpath(os.path.join(base, rel)) if rel else base
    if full != base and not full.startswith(base + os.sep):
        raise PathRefused("path %r is not inside the project" % rel)
    if not os.path.isdir(full):
        raise FileNotFoundError(rel)
    return full


def list_dir(root, rel, exts=PROGRAM_EXTS):
    """One level of the tree, as the file dialog shows it: sub-folders and the
    files with one of `exts` (with their size), skipping hidden entries,
    SKIP_DIRS and links that leave the root."""
    full = safe_dir(root, rel)
    base = os.path.realpath(root)
    dirs, files, sizes = [], [], []
    for name in sorted(os.listdir(full), key=lambda n: (n.lower(), n)):
        if name.startswith("."):
            continue
        path = os.path.join(full, name)
        if os.path.isdir(path):
            real = os.path.realpath(path)
            if name not in SKIP_DIRS and real.startswith(base + os.sep):
                dirs.append(name)
        elif name.lower().endswith(exts):
            files.append(name)
            try:
                sizes.append(os.path.getsize(path))
            except OSError:
                sizes.append(None)
    shown = os.path.relpath(full, base).replace(os.sep, "/")
    return {"path": "" if shown == "." else shown, "dirs": dirs,
            "files": files, "sizes": sizes}


# --------------------------------------------------------------------------- #
# Inspecting a data source
#
# The UI needs three things before it can write the annotations for a CSV file:
# which delimiter it uses, whether the first row names the columns, and what
# type each column holds.  All three are guesses, all three are shown to the
# user before anything is inserted, and all three can be overridden there.
# --------------------------------------------------------------------------- #

SNIFF_BYTES = 64 * 1024
SNIFF_ROWS = 200
NULL_TOKENS = {"", "\\N"}

_INT = re.compile(r"^[+-]?\d+$")
_DOUBLE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?$")
_BOOL = {"#t", "#f", "true", "false"}


def _column_type(values):
    """The narrowest of the engine's CSV types that fits every value."""
    seen = [v.strip() for v in values if v.strip() not in NULL_TOKENS]
    if not seen:
        return "string"
    for name, fits in (("int", lambda v: _INT.match(v)),
                       ("double", lambda v: _DOUBLE.match(v)),
                       ("boolean", lambda v: v.lower() in _BOOL),
                       ("date", lambda v: _DATE.match(v))):
        if all(fits(v) for v in seen):
            return name
    return "string"


def _looks_like_header(first, rest):
    """A header row names columns: text, distinct, and unlike the data below."""
    if not first or any(not cell.strip() for cell in first):
        return False
    if len(set(c.strip().lower() for c in first)) != len(first):
        return False
    if any(_column_type([cell]) != "string" for cell in first):
        return False
    if not rest:
        return True
    return any(_column_type([r[i] for r in rest if i < len(r)]) != "string"
               for i in range(len(first)))


def sniff_csv(full, delimiter=None):
    with open(full, encoding="utf-8", errors="replace") as fh:
        sample = fh.read(SNIFF_BYTES)
    if not sample.strip():
        raise DataSourceError("%s is empty" % os.path.basename(full))

    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = "\t" if full.lower().endswith(".tsv") else ","

    rows = []
    for row in csv.reader(io.StringIO(sample), delimiter=delimiter):
        rows.append(row)
        if len(rows) >= SNIFF_ROWS:
            break
    rows = [r for r in rows if r]
    if not rows:
        raise DataSourceError("%s has no rows" % os.path.basename(full))

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = _looks_like_header(rows[0], rows[1:])
    body = rows[1:] if header else rows

    columns = []
    for i in range(width):
        values = [r[i] for r in body]
        name = rows[0][i].strip() if header else "col%d" % i
        columns.append({"name": name or ("col%d" % i),
                        "type": _column_type(values),
                        "sample": next((v for v in values if v.strip()), "")})
    return {"delimiter": delimiter, "header": header, "columns": columns,
            "sampled": len(body), "partial": len(sample) >= SNIFF_BYTES}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    server_version = "vadalog-ui"
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------- #

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload, code=200):
        self._send(code, json.dumps(payload))

    def _fail(self, code, message):
        self._json({"ok": False, "error": {"kind": "request", "message": message}}, code)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_PROGRAM_BYTES:
            raise PathRefused("request body too large")
        return self.rfile.read(length) if length else b""

    def _guard(self):
        """Refuse cross-site writes: a custom header cannot come from a form."""
        if self.headers.get("X-Vadalog") != "1":
            self._fail(403, "missing X-Vadalog header")
            return False
        return True

    # -- routes ------------------------------------------------------------ #

    def do_GET(self):
        url = urlparse(self.path)
        root = self.server.root
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, read_index(), "text/html; charset=utf-8")
            if url.path == "/api/files":
                return self._json({"ok": True, "root": root,
                                   "files": list_programs(root),
                                   "readOnly": self.server.read_only})
            if url.path == "/api/dir":
                rel = (parse_qs(url.query).get("path") or [""])[0]
                kind = (parse_qs(url.query).get("kind") or ["vada"])[0]
                if kind not in ("vada", "data"):
                    return self._fail(400, "kind must be vada or data")
                listing = list_dir(root, rel,
                                   DATA_EXTS if kind == "data" else PROGRAM_EXTS)
                listing.update({"ok": True,
                                "root": os.path.basename(root) or root,
                                "readOnly": self.server.read_only})
                return self._json(listing)
            if url.path == "/api/sources":
                return self._json({"ok": True, "root": root,
                                   "files": list_files(root, DATA_EXTS)})
            if url.path == "/api/sniff":
                rel = (parse_qs(url.query).get("path") or [""])[0]
                delim = (parse_qs(url.query).get("delimiter") or [""])[0]
                full = safe_path(root, rel, DATA_EXTS)
                info = sniff_csv(full, delim or None)
                info.update({"ok": True, "path": rel})
                return self._json(info)
            if url.path == "/api/file":
                rel = (parse_qs(url.query).get("path") or [""])[0]
                full = safe_path(root, rel)
                with open(full, encoding="utf-8") as fh:
                    return self._json({"ok": True, "path": rel, "text": fh.read()})
            return self._fail(404, "no such route")
        except PathRefused as exc:
            return self._fail(403, str(exc))
        except DataSourceError as exc:
            return self._fail(400, getattr(exc, "message", None) or str(exc))
        except FileNotFoundError:
            return self._fail(404, "no such file")
        except Exception as exc:                                # pragma: no cover
            return self._fail(500, "%s: %s" % (type(exc).__name__, exc))

    def do_PUT(self):
        url = urlparse(self.path)
        if url.path != "/api/file":
            return self._fail(404, "no such route")
        if not self._guard():
            return
        if self.server.read_only:
            return self._fail(403, "the server was started read-only")
        try:
            rel = (parse_qs(url.query).get("path") or [""])[0]
            full = safe_path(self.server.root, rel)
            text = self._body().decode("utf-8")
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(text)
            return self._json({"ok": True, "path": rel})
        except PathRefused as exc:
            return self._fail(403, str(exc))
        except Exception as exc:                                # pragma: no cover
            return self._fail(500, "%s: %s" % (type(exc).__name__, exc))

    def do_POST(self):
        url = urlparse(self.path)
        actions = {"/api/run": do_run, "/api/check": do_check,
                   "/api/explain": do_explain, "/api/relations": do_relations}
        action = actions.get(url.path)
        if action is None:
            return self._fail(404, "no such route")
        if not self._guard():
            return
        try:
            body = json.loads(self._body() or b"{}")
        except ValueError:
            return self._fail(400, "malformed JSON body")
        try:
            return self._json(action(body, self.server.root))
        except VadalogError as exc:
            return self._json(_error_payload(exc))
        except RecursionError:
            return self._json({"ok": False, "error": {
                "kind": "resource",
                "message": "rule bodies nested too deeply for this interpreter"}})
        except PathRefused as exc:
            return self._fail(403, str(exc))
        except Exception as exc:                                # pragma: no cover
            return self._json({"ok": False, "error": {
                "kind": "internal",
                "message": "%s: %s" % (type(exc).__name__, exc)}})


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def build(root, port=8765, read_only=False, verbose=False, tries=12):
    root = os.path.realpath(root)
    last = None
    for candidate in range(port, port + tries):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
        except OSError as exc:
            last = exc
            continue
        httpd.daemon_threads = True
        httpd.root = root
        httpd.read_only = read_only
        httpd.verbose = verbose
        return httpd
    raise SystemExit("no free port in %d..%d (%s)" % (port, port + tries - 1, last))


def serve(root=".", port=8765, open_browser=True, read_only=False, verbose=False):
    httpd = build(root, port, read_only, verbose)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("vadalog ui  %s" % url)
    print("            serving %s%s" % (httpd.root, "  (read-only)" if read_only else ""))
    print("            ctrl-c to stop")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="vadalog ui",
                                description="Local web UI for vadalog-portable.")
    p.add_argument("--root", default=".", help="directory of .vada files to serve")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--read-only", action="store_true",
                   help="refuse saves; the editor becomes a viewer")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    return serve(args.root, args.port, not args.no_browser,
                 args.read_only, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
