"""The single-file build: `python3 tools/build_pyz.py` -> dist/vadalog.pyz.

The archive is how the engine is handed to someone who cannot install
anything, so it is worth a test of its own.  Everything here runs the archive
the way a recipient does, in a fresh interpreter, with nothing on the path.
"""

import os
import subprocess
import sys
import zipfile

import pytest

from harness import PROGRAMS  # noqa: F401  (adds src/ to sys.path)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(ROOT, "tools", "build_pyz.py")

PROGRAM = 'edge(1,2).\npath(X,Y) :- edge(X,Y).\n@output("path").\n'


def _build(out, *extra):
    """Build the archive, and say why if it will not build.

    Not `check=True`: that raises a CalledProcessError whose message is the
    command line and whose stderr nobody ever sees, which is how a one-line
    failure in the builder turns into six identical walls of traceback.
    """
    done = subprocess.run([sys.executable, BUILDER, "-o", out] + list(extra),
                          capture_output=True, text=True)
    if done.returncode != 0:
        pytest.fail("build_pyz exited %d\n%s%s"
                    % (done.returncode, done.stdout, done.stderr))
    return out


@pytest.fixture(scope="module")
def pyz(tmp_path_factory):
    # The temporary directory may well be on another drive than the checkout,
    # which is the normal arrangement on a Windows CI runner.
    return _build(str(tmp_path_factory.mktemp("pyz") / "vadalog.pyz"))


def _run(*argv, **kwargs):
    return subprocess.run([sys.executable] + list(argv), capture_output=True,
                          text=True, **kwargs)


def test_archive_carries_the_package_and_the_page(pyz):
    names = zipfile.ZipFile(pyz).namelist()
    assert "vadalog/cli.py" in names
    assert "vadalog/ui/index.html" in names
    # Zip entries are named with forward slashes, whatever the platform.  A
    # reader that joins them with os.sep looks for `vadalog\ui/index.html` and
    # finds nothing; read_index() must not depend on such a reader.
    assert not any("\\" in name for name in names)


def test_the_benchmark_scenarios_stay_out_of_the_archive(pyz):
    """`benchmark/` is for whoever clones the repository, not for a release.

    It carries third-party data an order of magnitude larger than the engine,
    so a packaging list that ever started globbing the checkout must fail here
    rather than in a release asset.
    """
    names = zipfile.ZipFile(pyz).namelist()
    assert not any("benchmark" in name for name in names), names


def test_it_reasons(pyz):
    program = os.path.join(os.path.dirname(pyz), "p.vada")
    with open(program, "w") as fh:
        fh.write(PROGRAM)
    done = _run(pyz, "run", program)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "path(1,2)."


def test_exit_codes_survive_the_archive(pyz, tmp_path):
    """zipapp's own entry point drops main()'s return value; ours does not.

    Without this the archive exits 0 on every failure, which is invisible by
    hand and fatal in a script (SPECIFICATION.md sec. 12.5).
    """
    broken = str(tmp_path / "broken.vada")
    with open(broken, "w") as fh:
        fh.write("p(X) :- \n")
    assert _run(pyz, "run", broken).returncode == 1            # static error

    failing = str(tmp_path / "failing.vada")
    with open(failing, "w") as fh:
        fh.write("p(1).\n#F :- p(1).\n")
    assert _run(pyz, "run", failing).returncode == 2           # a failure rule

    assert _run(pyz, "run", str(tmp_path / "absent.vada")).returncode == 4


def test_the_version_is_the_package_version(pyz):
    from vadalog import __version__
    done = _run(pyz, "--version")
    assert done.returncode == 0, done.stderr
    assert __version__ in done.stdout + done.stderr


def test_the_page_is_readable_from_inside_the_archive(pyz):
    """The regression guard: `index.html` is in the zip, not on the disk."""
    done = _run("-c", (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from vadalog.ui import server;"
        "page = server.read_index();"
        "print(len(page));"
        "assert b'<title>vadalog</title>' in page"), pyz)
    assert done.returncode == 0, done.stderr
    assert int(done.stdout.strip()) > 1000


def test_the_examples_travel_in_the_archive(pyz, tmp_path):
    """`examples --extract` is the only way a recipient gets at them.

    Inside the archive they are resources, not files, and the web UI serves a
    directory on disk; without the extraction there is nothing to open.  The
    list is `examples/__init__.py`'s own, so a file dropped from the packaging
    lists (pyproject.toml, build_pyz.py) fails here.
    """
    from vadalog.cli import _load_examples
    wanted = _load_examples().names()

    names = zipfile.ZipFile(pyz).namelist()
    for name in wanted:
        assert "vadalog/examples/" + name in names

    dest = tmp_path / "ex"
    done = _run(pyz, "examples", "--extract", str(dest))
    assert done.returncode == 0, done.stderr
    assert sorted(os.listdir(str(dest))) == sorted(wanted)

    # A second extraction must not discard edits made to the first.
    edited = dest / wanted[0]
    with open(str(edited), "w") as fh:
        fh.write("% mine\n")
    assert _run(pyz, "examples", "--extract", str(dest)).returncode == 0
    with open(str(edited)) as fh:
        assert fh.read() == "% mine\n"

    # And every extracted program still runs, straight from the archive.
    for name in wanted:
        if name.endswith(".vada"):
            done = _run(pyz, "run", str(dest / name))
            assert done.returncode == 0, (name, done.stderr)


def test_a_build_without_the_examples_says_so(pyz, tmp_path):
    out = _build(str(tmp_path / "bare.pyz"), "--no-examples")
    assert not any(name.startswith("vadalog/examples/")
                   for name in zipfile.ZipFile(out).namelist())
    refused = _run(out, "examples")
    assert refused.returncode != 0
    assert "not part of this build" in refused.stdout + refused.stderr


def test_the_engine_alone_still_builds(pyz, tmp_path):
    """--no-ui drops the page; the reasoner is unaffected, `ui` says so."""
    out = _build(str(tmp_path / "engine.pyz"), "--no-ui")
    assert not any(name.startswith("vadalog/ui/")
                   for name in zipfile.ZipFile(out).namelist())
    program = os.path.join(os.path.dirname(pyz), "p2.vada")
    with open(program, "w") as fh:
        fh.write(PROGRAM)
    assert _run(out, "run", program).returncode == 0
    refused = _run(out, "ui", "--no-browser")
    assert refused.returncode != 0
    assert "not part of this build" in refused.stdout + refused.stderr
