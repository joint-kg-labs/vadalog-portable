"""Command line interface (SPECIFICATION.md sec. 12.5)."""

import argparse
import json
import os
import sys

from . import __version__
from .chase import Options
from .errors import DataSourceError, VadalogError
from .params import load_json, parse_assignment, parse_string_assignment
from .program import Runner, describe_check, describe_explain, load_program
from .values import format_fact, is_null, to_string


DEFAULT_EXAMPLES_DIR = "vadalog-examples"


def _add_param_options(cmd):
    """`-p NAME=VALUE` and `--params FILE` (SPECIFICATION.md sec. 11.8)."""
    cmd.add_argument("-p", "--param", action="append", default=[],
                     metavar="NAME=VALUE",
                     help="fill the placeholder ${NAME}; VALUE is a Vadalog literal "
                          "(42, 0.5, \"text\", 2024-01-31, #T); repeatable")
    cmd.add_argument("-s", "--param-string", action="append", default=[],
                     metavar="NAME=TEXT",
                     help="fill ${NAME} with TEXT as a string, verbatim; repeatable")
    cmd.add_argument("--params", default=None, metavar="FILE",
                     help="a JSON object of parameter values; -p and -s win on conflicts")


def build_parser():
    p = argparse.ArgumentParser(
        prog="vadalog",
        description="A small, portable Datalog+/- (Vadalog) reasoner.")
    p.add_argument("--version", action="version", version="vadalog-portable " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="evaluate a program")
    run.add_argument("program")
    run.add_argument("--csv-dir", default=None,
                     help="base directory for relative @bind paths")
    run.add_argument("--out", default=None, help="directory for CSV output")
    run.add_argument("--format", choices=("facts", "csv", "json"), default="facts")
    run.add_argument("--max-facts", type=int, default=5_000_000)
    run.add_argument("--max-rounds", type=int, default=0)
    run.add_argument("--timeout", type=float, default=0.0)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--allow-unstratified", action="store_true")
    run.add_argument("--strict", action="store_true")
    run.add_argument("--stats", action="store_true")
    run.add_argument("-v", "--verbose", action="store_true")
    _add_param_options(run)

    check = sub.add_parser("check", help="parse and analyse without evaluating")
    check.add_argument("program")
    check.add_argument("--strict", action="store_true")
    _add_param_options(check)

    explain = sub.add_parser("explain", help="show the normalised program")
    explain.add_argument("program")
    _add_param_options(explain)

    ex = sub.add_parser("examples",
                        help="list the bundled example programs, or write them to disk")
    ex.add_argument("--extract", nargs="?", const=DEFAULT_EXAMPLES_DIR,
                    metavar="DIR",
                    help="write the examples into DIR (default %s) instead of "
                         "listing them" % DEFAULT_EXAMPLES_DIR)
    ex.add_argument("--force", action="store_true",
                    help="with --extract: overwrite files already there")

    ui = sub.add_parser("ui", help="serve the local web editor")
    ui.add_argument("--root", default=".", help="directory of .vada files to serve")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-browser", action="store_true")
    ui.add_argument("--read-only", action="store_true",
                    help="refuse saves; the editor becomes a viewer")
    ui.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return _run(args)
        if args.command == "check":
            return _check(args)
        if args.command == "examples":
            return _examples(args)
        if args.command == "ui":
            return _ui(args)
        return _explain(args)
    except VadalogError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return exc.exit_code
    except RecursionError:
        print("error: rule bodies nested too deeply for this interpreter",
              file=sys.stderr)
        return 3


def _options(args):
    return Options(max_facts=args.max_facts, max_rounds=args.max_rounds,
                   timeout=args.timeout, seed=args.seed,
                   allow_unstratified=args.allow_unstratified,
                   strict=args.strict, stats=args.stats)


def _params(args):
    values = load_json(args.params) if args.params else {}
    for item in args.param:
        name, value = parse_assignment(item)
        values[name] = value
    for item in args.param_string:
        name, value = parse_string_assignment(item)
        values[name] = value
    return values


def _run(args):
    program = load_program(args.program, params=_params(args))
    runner = Runner(program, _options(args), csv_dir=args.csv_dir, out_dir=args.out)
    result = runner.run()

    for warning in result.warnings:
        print("warning: %s" % warning, file=sys.stderr)

    if args.format == "facts":
        for pred in runner.bindings.outputs:
            if pred in runner.bindings.binds:
                continue
            for tup in result.relations.get(pred, []):
                print(format_fact(pred, tup))
    elif args.format == "json":
        payload = {pred: [[_jsonable(v) for v in tup] for tup in rows]
                   for pred, rows in result.relations.items()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        out_dir = args.out or os.getcwd()
        os.makedirs(out_dir, exist_ok=True)
        import csv as _csv
        for pred, rows in result.relations.items():
            if pred in runner.bindings.binds:
                continue
            path = os.path.join(out_dir, "%s.csv" % pred)
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = _csv.writer(fh, lineterminator="\n")
                for tup in rows:
                    writer.writerow(["\\N" if is_null(v) else to_string(v) for v in tup])
            result.written.append(path)

    for path in result.written:
        print("wrote %s" % path, file=sys.stderr)
    if args.stats:
        print("stats: %s" % ", ".join("%s=%s" % kv for kv in sorted(result.stats.items())),
              file=sys.stderr)
    return 0


def _jsonable(v):
    if is_null(v):
        return v.name
    if isinstance(v, (bool, int, float, str)):
        return v
    return to_string(v)


def _examples(args):
    """The toy programs that travel inside the build.

    Listing them is the discoverable half; `--extract` is the useful one.  In
    an archive or an installed package they are read-only resources, and the
    web UI serves a directory on disk, so nothing can be opened, edited or run
    from the page until there is a copy on disk.
    """
    examples = _load_examples()

    if args.extract is None:
        print("example programs carried inside this build:\n")
        for name, blurb in examples.EXAMPLES:
            print("  %-22s %s" % (name, blurb))
        print("\nwrite them somewhere you can edit them:\n")
        print("  vadalog examples --extract %s" % DEFAULT_EXAMPLES_DIR)
        return 0

    dest = args.extract
    try:
        written, skipped = examples.extract(dest, force=args.force)
    except OSError as exc:
        raise DataSourceError("cannot write into %s: %s" % (dest, exc))

    for path in written:
        print("wrote %s" % path)
    if skipped:
        print("already there, left alone (--force overwrites): %s"
              % ", ".join(os.path.basename(p) for p in skipped))
    print("\n  vadalog run %s" % os.path.join(dest, "reachability.vada"))
    print("  vadalog ui --root %s" % dest)
    return 0


def _load_examples():
    """The examples package.

    Packaging maps the repository's top-level ``examples/`` into the package
    as ``vadalog.examples``, so an installed wheel and a ``.pyz`` import it
    normally.  In a source checkout there is no such subpackage — the
    directory is still at the top of the tree — so it is loaded from there,
    the same fallback ``read_index`` makes for the page.
    """
    try:
        from . import examples
        return examples
    except ImportError as missing:
        here = os.path.dirname(os.path.abspath(__file__))        # src/vadalog
        root = os.path.dirname(os.path.dirname(here))            # the checkout
        path = os.path.join(root, "examples", "__init__.py")
        if os.path.isfile(path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("vadalog_examples", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        raise DataSourceError(
            "the examples are not part of this build (%s); they are in the "
            "repository under examples/" % missing)


def _ui(args):
    server = _load_ui_server()
    return server.serve(args.root, args.port, not args.no_browser,
                        args.read_only, args.verbose)


def _load_ui_server():
    """The UI server module.

    It ships inside the package (``vadalog/ui``), so an ordinary import finds
    it wherever the engine runs from: a checkout, an installed wheel, or a
    single-file ``.pyz``.  ``VADALOG_UI`` still overrides it with a directory
    holding a ``server.py``, which is how one works on the page without
    reinstalling.
    """
    override = os.environ.get("VADALOG_UI")
    if override:
        import importlib.util
        path = os.path.join(override, "server.py")
        if not os.path.isfile(path):
            raise DataSourceError("VADALOG_UI does not hold a server.py: %s" % override)
        spec = importlib.util.spec_from_file_location("vadalog_ui_server", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    try:
        from .ui import server
    except ImportError as exc:                       # a build made without the UI
        raise DataSourceError(
            "the web UI is not part of this build (%s); reinstall the package, "
            "or point VADALOG_UI at a directory holding server.py" % exc)
    return server


def _check(args):
    program = load_program(args.program, params=_params(args), lenient=True)
    runner = Runner(program, Options(strict=args.strict))
    info = runner.prepare()
    for warning in runner.bindings.warnings:
        print("warning: %s" % warning, file=sys.stderr)
    print(describe_check(program, runner, info))
    return 0


def _explain(args):
    program = load_program(args.program, params=_params(args))
    runner = Runner(program, Options())
    print(describe_explain(runner.prepare()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
