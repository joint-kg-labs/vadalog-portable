"""The native build: `python3 tools/build_binary.py` -> dist/vadalog[.exe].

Freezing an executable needs PyInstaller and takes minutes, so the build
itself runs only when asked for (``VADALOG_BUILD_BINARY=1``, which is what
.github/workflows/binaries.yml does on five platforms).  What runs always is
everything that can be checked without freezing anything: that the staging
step lays out exactly the tree both builders ship, that the PyInstaller
invocation names every file the engine reads as a resource, and that the
output is spelled the way the platform spells an executable.
"""

import os
import subprocess
import sys

import pytest

from harness import PROGRAMS  # noqa: F401  (adds src/ to sys.path)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_binary                                             # noqa: E402
import build_pyz                                                # noqa: E402


# --------------------------------------------------------------------------
# the staging step, shared by the archive and the binary
# --------------------------------------------------------------------------

def test_staging_carries_the_engine_the_page_and_the_examples(tmp_path):
    staging = str(tmp_path / "tree")
    os.makedirs(staging)
    entry = build_pyz.stage(staging, entry="vadalog_main.py")

    assert os.path.isfile(os.path.join(staging, "vadalog", "cli.py"))
    assert os.path.isfile(os.path.join(staging, "vadalog", "ui", "index.html"))
    assert os.path.isfile(os.path.join(staging, "vadalog", "examples",
                                       "reachability.vada"))
    # The entry point propagates main()'s return value; zipapp's own does not,
    # and every exit code in SPECIFICATION.md sec. 12.5 depends on this one.
    with open(entry, encoding="utf-8") as fh:
        assert "sys.exit(main())" in fh.read()

    # __pycache__ from a source checkout must not travel: it is stale the
    # moment it is copied and pins the build to one interpreter version.
    for _, directories, _ in os.walk(staging):
        assert "__pycache__" not in directories


def test_staging_can_leave_the_ui_and_the_examples_out(tmp_path):
    staging = str(tmp_path / "bare")
    os.makedirs(staging)
    build_pyz.stage(staging, with_ui=False, with_examples=False)
    assert not os.path.exists(os.path.join(staging, "vadalog", "ui"))
    assert not os.path.exists(os.path.join(staging, "vadalog", "examples"))


# --------------------------------------------------------------------------
# the PyInstaller invocation
# --------------------------------------------------------------------------

def test_every_resource_is_named_to_pyinstaller(tmp_path):
    """A file that is read rather than imported reaches the binary only if it
    is listed: a missing `--add-data` costs the page or the examples, and the
    loss shows up in nobody's unit tests."""
    staging = str(tmp_path / "tree")
    os.makedirs(staging)
    build_pyz.stage(staging)

    arguments = build_binary.data_arguments(staging)
    assert arguments[0::2] == ["--add-data"] * (len(arguments) // 2)

    pairs = [value.rsplit(os.pathsep, 1) for value in arguments[1::2]]
    sources = [os.path.basename(source) for source, _ in pairs]
    assert "index.html" in sources
    for name in build_pyz.example_files():
        # `__init__.py` is a module: imported, not read as a resource.
        assert (name in sources) is not name.endswith(".py")

    destinations = {destination for _, destination in pairs}
    assert destinations == {os.path.join("vadalog", "ui"),
                            os.path.join("vadalog", "examples")}


def test_the_output_is_spelled_the_way_the_platform_spells_it():
    windows = os.name == "nt"

    name, produced = build_binary.frozen_name(os.path.join("dist", "vadalog"))
    assert name == "vadalog"
    assert os.path.basename(produced) == ("vadalog.exe" if windows else "vadalog")

    # What the release matrix asks for.  `--name vadalog-windows-x86_64.exe`
    # would have PyInstaller write `vadalog-windows-x86_64.exe.exe`.
    name, produced = build_binary.frozen_name(
        os.path.join("dist", "vadalog-windows-x86_64.exe"))
    assert name == "vadalog-windows-x86_64"
    assert os.path.basename(produced) == (
        "vadalog-windows-x86_64.exe" if windows else "vadalog-windows-x86_64")


def test_the_builder_says_what_is_missing_rather_than_traceback():
    """Without PyInstaller the builder must explain itself: it is the one
    build-time dependency in a project that has no runtime ones."""
    done = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_binary.py"),
                           "--help"], capture_output=True, text=True)
    assert done.returncode == 0
    assert "executable" in done.stdout


# --------------------------------------------------------------------------
# the real thing, on request
# --------------------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("VADALOG_BUILD_BINARY"),
                    reason="set VADALOG_BUILD_BINARY=1 to freeze a binary (minutes)")
def test_the_frozen_binary_runs_and_carries_its_resources(tmp_path):
    pytest.importorskip("PyInstaller")
    out = str(tmp_path / ("vadalog.exe" if os.name == "nt" else "vadalog"))
    build_binary.build(out, build_dir=str(tmp_path / "work"), self_check=False)

    smoke = os.path.join(ROOT, "tools", "smoke.py")
    done = subprocess.run([sys.executable, smoke, "--", out],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
