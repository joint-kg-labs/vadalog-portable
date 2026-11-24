#!/usr/bin/env python3
"""Build the single-file distribution: dist/vadalog.pyz.

    python3 tools/build_pyz.py [-o PATH] [--no-ui]

The engine has no dependencies, so the whole of it — the web UI and its page
included — fits in one zipapp that any Python 3.9+ can execute directly:

    ./vadalog.pyz run program.vada          # macOS, Linux
    python vadalog.pyz run program.vada     # anywhere, Windows included

The archive carries the engine, the web UI and its page, and the example
programs, which `vadalog examples --extract DIR` writes back out to disk.

Nothing is installed, no virtualenv is created, no administrator rights are
needed.  Standard library only, like everything else here.

`tools/build_binary.py` reuses the staging step below to freeze the very same
tree into a native executable for people who have no Python at all.
"""

import argparse
import io
import os
import shutil
import stat
import sys
import tempfile
import zipapp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "vadalog")
EXAMPLES = os.path.join(ROOT, "examples")
DEFAULT_OUT = os.path.join(ROOT, "dist", "vadalog.pyz")

# __pycache__ is stale the moment it is copied; .pyc files bloat the archive
# and pin it to one interpreter version.
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")

# The entry point is written here rather than left to zipapp's `main=`.  The
# one zipapp generates calls main() and throws away what it returns, so the
# archive would exit 0 on a static error, a failed rule or a tripped guard, and
# every exit code in SPECIFICATION.md sec. 12.5 would be a lie.
ENTRY = '''"""The archive entry point, written by tools/build_pyz.py."""

import sys

from vadalog.cli import main

if __name__ == "__main__":
    sys.exit(main())
'''


def example_files():
    """The curated example files, named by `examples/__init__.py` itself.

    Loaded from its path rather than imported by name: `examples` is a plain
    directory here and only becomes `vadalog.examples` once it is packaged.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_vadalog_examples", os.path.join(EXAMPLES, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return ["__init__.py"] + module.names()


def version():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import vadalog
    return vadalog.__version__


def stage(staging, with_ui=True, with_examples=True, entry="__main__.py"):
    """Lay the whole distribution out under `staging`; return the entry script.

    One tree, two consumers: zipapp zips it into `vadalog.pyz`, PyInstaller
    freezes it into a native executable.  Both need exactly the same thing —
    the package, the page, the examples mapped into `vadalog/examples`, and an
    entry point that propagates main()'s exit code — so it is built once here
    and neither builder can drift from the other.
    """
    if not os.path.isdir(SRC):
        raise SystemExit("cannot find %s" % SRC)

    shutil.copytree(SRC, os.path.join(staging, "vadalog"), ignore=IGNORE)
    if not with_ui:
        shutil.rmtree(os.path.join(staging, "vadalog", "ui"), ignore_errors=True)
    if with_examples:
        # A few KB, and the difference between a file someone was handed
        # and a file someone can try:  `vadalog.pyz examples --extract .`
        target = os.path.join(staging, "vadalog", "examples")
        os.makedirs(target)
        for name in example_files():
            shutil.copy2(os.path.join(EXAMPLES, name),
                         os.path.join(target, name))

    entry_path = os.path.join(staging, entry)
    with io.open(entry_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ENTRY)
    return entry_path


def build(out=DEFAULT_OUT, with_ui=True, with_examples=True):
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    staging = tempfile.mkdtemp(prefix="vadalog-pyz-")
    try:
        stage(staging, with_ui=with_ui, with_examples=with_examples)
        zipapp.create_archive(staging, target=out,
                              interpreter="/usr/bin/env python3",
                              compressed=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    mode = os.stat(out).st_mode
    os.chmod(out, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("%s  (%s, %.0f KB)" % (shortest(out), version(),
                                 os.path.getsize(out) / 1024.0))
    return out


def shortest(path):
    """The path as the caller would recognise it: relative when that means
    anything.  On Windows it need not: a checkout on D: and a temporary
    directory on C: have no relative path at all, and relpath raises rather
    than saying so."""
    try:
        relative = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return relative if not relative.startswith(os.pardir) else path


# The name it had before the builder grew a sibling; kept so nothing that
# imported it breaks.
_shortest = shortest


def main(argv=None):
    p = argparse.ArgumentParser(prog="build_pyz",
                                description="Build the single-file vadalog.pyz.")
    p.add_argument("-o", "--output", default=DEFAULT_OUT)
    p.add_argument("--no-ui", action="store_true",
                   help="leave the web UI out of the archive")
    p.add_argument("--no-examples", action="store_true",
                   help="leave the example programs out of the archive")
    args = p.parse_args(argv)
    build(args.output, with_ui=not args.no_ui,
          with_examples=not args.no_examples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
