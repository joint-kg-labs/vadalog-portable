#!/usr/bin/env python3
"""Build the native, single-file executable: dist/vadalog[.exe].

    python3 tools/build_binary.py [-o PATH] [--no-ui] [--no-examples]

`vadalog.pyz` needs a Python on the machine; this does not.  It is the same
engine, the same web UI and the same examples, frozen together with a Python
interpreter into one executable that a recipient can run with no prerequisite
at all:

    ./vadalog-macos-arm64 run program.vada
    vadalog-windows-x86_64.exe run program.vada

The engine itself stays dependency-free: **PyInstaller is a build-time tool
only**, it is never imported by the engine and nothing of it survives into the
source tree.  Install it where you build:

    python3 -m pip install pyinstaller

One executable is one platform and one architecture — they are not portable
across either — so the release builds five of them, one per runner, in
.github/workflows/binaries.yml.  `vadalog.pyz` remains the portable artefact.

The staging step is shared with tools/build_pyz.py, so the binary and the
archive always carry the same tree.
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_pyz import (EXAMPLES, ROOT, example_files,   # noqa: E402
                       shortest, stage, version)

DEFAULT_NAME = "vadalog.exe" if os.name == "nt" else "vadalog"
DEFAULT_OUT = os.path.join(ROOT, "dist", DEFAULT_NAME)

# Modules PyInstaller would otherwise drag in from the standard library or
# from the build environment.  Excluded for size only: nothing in the engine
# imports them.  `email` is deliberately *not* here — http.server parses its
# headers with it, so dropping it would break `vadalog ui`.
EXCLUDES = ("tkinter", "test", "unittest", "pydoc_data", "lib2to3")

# Imported lazily, inside a function, in cli.py.  PyInstaller's static
# analysis follows both, but naming them makes the build independent of how
# clever that analysis happens to be in a given version.
HIDDEN = ("vadalog.cli", "vadalog.ui.server", "vadalog.examples")


def data_arguments(staging, with_ui=True, with_examples=True):
    """`--add-data` for every file that is read as a resource rather than
    imported: the UI page and the example programs.

    The separator is `os.pathsep` — `:` everywhere but Windows, where it is
    `;` — because a colon on Windows would split `C:\\...` in half.
    """
    args = []

    def add(source, destination):
        args.extend(["--add-data", "%s%s%s" % (source, os.pathsep, destination)])

    if with_ui:
        add(os.path.join(staging, "vadalog", "ui", "index.html"),
            os.path.join("vadalog", "ui"))
    if with_examples:
        for name in example_files():
            if name.endswith(".py"):
                continue                    # a module: imported, not read
            add(os.path.join(EXAMPLES, name), os.path.join("vadalog", "examples"))
    return args


def frozen_name(out):
    """The `--name` to give PyInstaller, and the path it will then write.

    `--name` takes the stem: PyInstaller appends `.exe` itself on Windows, and
    a name already carrying it would come out as `vadalog.exe.exe`.  The two
    are returned together because the second follows from the first, and a
    build that guesses the output path wrongly fails after the slow part.
    """
    out = os.path.abspath(out)
    name = os.path.basename(out)
    if name.lower().endswith(".exe"):
        name = name[:-4]
    produced = os.path.join(os.path.dirname(out),
                            name + (".exe" if os.name == "nt" else ""))
    return name, produced


def build(out=DEFAULT_OUT, with_ui=True, with_examples=True, self_check=True,
          build_dir=None):
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    name, produced = frozen_name(out)

    # PyInstaller's scratch — the spec, the analysis, the object files — is
    # throwaway, and by default it is thrown away: a temporary directory keeps
    # a few hundred short-lived files out of the checkout, which matters when
    # the checkout is inside a synchronised folder.  `--build-dir` keeps them
    # somewhere they can be read afterwards.
    work = os.path.abspath(build_dir) if build_dir \
        else tempfile.mkdtemp(prefix="vadalog-work-")
    staging = tempfile.mkdtemp(prefix="vadalog-bin-")
    try:
        entry = stage(staging, with_ui=with_ui, with_examples=with_examples,
                      entry="vadalog_main.py")
        command = [sys.executable, "-m", "PyInstaller",
                   "--onefile",          # one file, like the .pyz
                   "--console",
                   "--noupx",            # UPX earns false positives from AV
                   "--noconfirm",
                   "--name", name,
                   "--paths", staging,
                   # Straight into the output directory, rather than into one
                   # of PyInstaller's own that the result is then moved out
                   # of: a move across filesystems is a copy plus a delete,
                   # and there are places where the delete is not allowed.
                   "--distpath", os.path.dirname(out),
                   "--workpath", os.path.join(work, "work"),
                   "--specpath", work]
        for module in HIDDEN:
            if module == "vadalog.ui.server" and not with_ui:
                continue
            if module == "vadalog.examples" and not with_examples:
                continue
            command += ["--hidden-import", module]
        for module in EXCLUDES:
            command += ["--exclude-module", module]
        command += data_arguments(staging, with_ui, with_examples)
        command.append(entry)

        print("$ %s" % " ".join(command))
        done = subprocess.run(command)
        if done.returncode != 0:
            raise SystemExit("PyInstaller exited %d" % done.returncode)
        if not os.path.isfile(produced):
            raise SystemExit("PyInstaller wrote no %s" % produced)

        if produced != out:
            # Only when the caller asked for a spelling PyInstaller would not
            # have chosen; both paths are in the same directory, so this is a
            # rename and cannot fail halfway.
            os.replace(produced, out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if not build_dir:
            shutil.rmtree(work, ignore_errors=True)

    mode = os.stat(out).st_mode
    os.chmod(out, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("%s  (%s, %.1f MB)" % (shortest(out), version(),
                                 os.path.getsize(out) / (1024.0 * 1024.0)))

    if self_check:
        # The cheapest possible proof that the thing starts at all; the real
        # checks are in tools/smoke.py.  Skippable because a cross-built
        # binary cannot run on the machine that built it.
        done = subprocess.run([out, "--version"], capture_output=True, text=True)
        if done.returncode != 0 or version() not in done.stdout:
            raise SystemExit("the binary does not run: %d %s%s"
                             % (done.returncode, done.stdout, done.stderr))
        print(done.stdout.strip())
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="build_binary",
        description="Freeze the engine into a native single-file executable.")
    p.add_argument("-o", "--output", default=DEFAULT_OUT,
                   help="where the executable goes (default %s)"
                        % shortest(DEFAULT_OUT))
    p.add_argument("--no-ui", action="store_true",
                   help="leave the web UI out of the executable")
    p.add_argument("--no-examples", action="store_true",
                   help="leave the example programs out of the executable")
    p.add_argument("--no-self-check", action="store_true",
                   help="do not run the new executable (cross builds)")
    p.add_argument("--build-dir", default=None,
                   help="keep PyInstaller's scratch here instead of in a "
                        "temporary directory that is removed afterwards")
    args = p.parse_args(argv)

    try:
        import PyInstaller                              # noqa: F401
    except ImportError:
        raise SystemExit(
            "PyInstaller is not installed.  It is a build-time tool only:\n"
            "    %s -m pip install pyinstaller" % os.path.basename(sys.executable))

    build(args.output, with_ui=not args.no_ui,
          with_examples=not args.no_examples,
          self_check=not args.no_self_check,
          build_dir=args.build_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
