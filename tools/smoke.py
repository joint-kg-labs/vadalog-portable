#!/usr/bin/env python3
"""Exercise a finished build the way the person who was handed it does.

    python3 tools/smoke.py -- dist/vadalog-linux-x86_64        # the binary
    python3 tools/smoke.py -- python3 dist/vadalog.pyz         # the archive
    python3 tools/smoke.py --skip-ui -- ./vadalog              # the checkout

Everything after `--` is the command that runs the engine, so one script
covers every shape it ships in.  Nothing is installed and nothing is imported
from the source tree: each check spawns the build as its own process and looks
only at what comes back, which is the whole point — a build can be broken in
ways a test run inside the interpreter cannot see (a resource that did not make
it into the archive, an exit code swallowed by an entry point, a UI that cannot
find its page).

Exits 0 when every check passed, 1 otherwise, with a summary either way.
Standard library only, like the engine.
"""

import argparse
import faulthandler
import glob
import http.client
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A static error: the rule has no body.  Exit code 1 (SPECIFICATION.md 12.5).
BROKEN = "p(X) :- \n"
# A failure rule that fires.  Exit code 2.
FAILING = 'q(1).\n#F :- q(X).\n@output("q").\n'
# Accented output, to be written to a redirected file rather than a terminal.
ACCENTS = '@output("p"). p("città", "naïve").\n'

failures = []
passed = 0


def check(name, problem):
    """Record one outcome.  `problem` is None when the check passed."""
    global passed
    if problem is None:
        passed += 1
        print("  ok    %s" % name)
    else:
        failures.append((name, problem))
        print("  FAIL  %s\n        %s" % (name, problem.replace("\n", "\n        ")))


def run(command, *args, **kwargs):
    """Run the build with `args`, capturing everything it says."""
    return subprocess.run(list(command) + list(args), capture_output=True,
                          text=True, errors="replace", **kwargs)


def detail(done):
    return "exit %d\n%s%s" % (done.returncode, done.stdout, done.stderr)


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------

def check_version(command, expected):
    done = run(command, "--version")
    if done.returncode != 0:
        return check("--version", detail(done))
    if expected and expected not in done.stdout:
        return check("--version", "expected %r in %r" % (expected, done.stdout.strip()))
    check("--version  (%s)" % done.stdout.strip(), None)


def check_programs(command, programs, label):
    """Every example program, run straight from the build."""
    if not programs:
        return check(label, "no programs to run")
    for program in programs:
        done = run(command, "run", program)
        name = "%s  %s" % (label, os.path.basename(program))
        check(name, None if done.returncode == 0 else detail(done))


def check_examples_listing(command):
    done = run(command, "examples")
    if done.returncode != 0:
        return check("examples (listing)", detail(done))
    if "reachability.vada" not in done.stdout:
        return check("examples (listing)", "the listing names no examples:\n" + done.stdout)
    check("examples (listing)", None)


def check_examples_extract(command, workdir):
    """`examples --extract` is the only way a recipient gets at the programs
    inside the build, and the only way the web UI can serve them."""
    dest = os.path.join(workdir, "extracted")
    done = run(command, "examples", "--extract", dest)
    if done.returncode != 0:
        return check("examples --extract", detail(done))
    programs = sorted(glob.glob(os.path.join(dest, "*.vada")))
    if not programs:
        return check("examples --extract", "the build carried no example programs")
    check("examples --extract  (%d programs)" % len(programs), None)
    check_programs(command, programs, "extracted")


def check_subcommands(command, program):
    """`check` and `explain`: separate paths through the CLI that a run never
    touches, and the two commands a new user is told to try first."""
    if not program:
        return check("check / explain", "no program to analyse")
    for subcommand, wanted in (("check", "strata:"), ("explain", "stratum 0")):
        done = run(command, subcommand, program)
        if done.returncode != 0:
            check(subcommand, detail(done))
        elif wanted not in done.stdout.lower():
            check(subcommand, "unexpected output:\n" + done.stdout)
        else:
            check(subcommand, None)


def check_exit_codes(command, workdir):
    """The exit codes of SPECIFICATION.md 12.5, which an entry point that
    throws main()'s return value away would quietly turn into a uniform 0."""
    cases = [
        ("static error -> 1", write(os.path.join(workdir, "broken.vada"), BROKEN), 1),
        ("failure rule -> 2", write(os.path.join(workdir, "failing.vada"), FAILING), 2),
        ("missing file -> 4", os.path.join(workdir, "not-there.vada"), 4),
    ]
    for name, program, expected in cases:
        done = run(command, "run", program)
        check("exit code: " + name,
              None if done.returncode == expected
              else "expected %d, got %s" % (expected, detail(done)))


def check_redirected_non_ascii(command, workdir):
    """Accented output written to a file rather than a terminal.

    On Windows a redirected stdout uses the locale encoding, not UTF-8, so
    this fails there while succeeding on Linux and macOS.  The text is
    representable in both encodings on purpose: the check is that the engine
    completes, not which encoding the platform chose.
    """
    program = write(os.path.join(workdir, "accents.vada"), ACCENTS)
    target = os.path.join(workdir, "accents.out")
    with open(target, "wb") as fh:
        done = subprocess.run(list(command) + ["run", program],
                              stdout=fh, stderr=subprocess.PIPE, text=False)
    if done.returncode != 0:
        return check("non-ASCII to a redirected file",
                     "exit %d\n%s" % (done.returncode,
                                      done.stderr.decode("utf-8", "replace")))
    with open(target, "rb") as fh:
        raw = fh.read()
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            if "città" in raw.decode(encoding):
                return check("non-ASCII to a redirected file (%s)" % encoding, None)
        except UnicodeDecodeError:
            continue
    check("non-ASCII to a redirected file", "unreadable output: %r" % raw[:120])


def check_ui(command, workdir, port, deadline_seconds=60):
    """The web UI, started as its own process and asked for its page.

    On a leash throughout: the child writes to a file rather than to a pipe
    nobody drains, the wait has a deadline, and the process is killed however
    the check ends.  A UI that wedges must fail the build, not hold the runner.
    """
    log_path = os.path.join(workdir, "ui.log")
    log = open(log_path, "w+")
    server = subprocess.Popen(
        list(command) + ["ui", "--root", workdir, "--port", str(port),
                         "--no-browser", "--read-only"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)

    def transcript():
        log.flush()
        log.seek(0, os.SEEK_SET)
        return log.read()

    def serving_port():
        """The port it actually bound: `serve` walks up when one is taken, and
        says so on its first line."""
        found = re.search(r"127\.0\.0\.1:(\d+)", transcript())
        return int(found.group(1)) if found else None

    def fetch(on):
        # http.client rather than urllib: urllib consults the proxy settings,
        # and on Windows those come from the registry, where a hosted runner
        # may have one set that does not except loopback.
        conn = http.client.HTTPConnection("127.0.0.1", on, timeout=3)
        try:
            conn.request("GET", "/")
            return conn.getresponse().read()
        finally:
            conn.close()

    try:
        page, last, deadline = None, None, time.time() + deadline_seconds
        while time.time() < deadline:
            if server.poll() is not None:
                return check("web UI", "the ui exited with %s before answering\n%s"
                             % (server.returncode, transcript()))
            try:
                page = fetch(serving_port() or port)
                break
            except Exception as exc:
                last = exc
                time.sleep(0.5)
        if page is None:
            return check("web UI", "no answer within %d s (%s)\n%s"
                         % (deadline_seconds, last, transcript()))
        if b"<title>vadalog</title>" not in page:
            return check("web UI", "it answered, but not with its page\n%s" % transcript())
        check("web UI  (%d bytes on port %s)" % (len(page), serving_port() or port), None)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()


# --------------------------------------------------------------------------

def expected_version():
    """The version in the source tree, when there is one to compare against."""
    path = os.path.join(ROOT, "src", "vadalog", "__init__.py")
    try:
        with open(path, encoding="utf-8") as fh:
            found = re.search(r'__version__\s*=\s*"([^"]+)"', fh.read())
        return found.group(1) if found else None
    except OSError:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="smoke",
        description="Run a finished build the way a recipient does.")
    p.add_argument("--programs", default=os.path.join(ROOT, "examples"),
                   help="directory of .vada programs to run (default examples/)")
    p.add_argument("--skip-ui", action="store_true", help="do not start the web UI")
    p.add_argument("--port", type=int, default=8899, help="port for the UI check")
    p.add_argument("--timeout", type=int, default=180,
                   help="seconds before the whole run is aborted with a traceback")
    p.add_argument("command", nargs="+",
                   help="how to run the build, e.g. `-- python3 dist/vadalog.pyz`")
    args = p.parse_args(argv)

    command = list(args.command)
    # A bare path, given without `./`, is a file here and not something on the
    # PATH; spelling it absolute is what makes `vadalog-linux-x86_64` work.
    if len(command) == 1 and os.path.exists(command[0]):
        command[0] = os.path.abspath(command[0])

    # A wedged child would otherwise take the whole job down with it six hours
    # later; this takes it down now, with a traceback saying where.
    faulthandler.dump_traceback_later(args.timeout, exit=True)

    print("smoke: %s" % " ".join(command))
    print("       python %s on %s\n" % (sys.version.split()[0], sys.platform))

    workdir = tempfile.mkdtemp(prefix="vadalog-smoke-")
    try:
        check_version(command, expected_version())
        check_programs(command, sorted(glob.glob(os.path.join(args.programs, "*.vada"))),
                       "example")
        check_subcommands(command, (sorted(glob.glob(os.path.join(
            args.programs, "*.vada"))) or [None])[0])
        check_examples_listing(command)
        check_examples_extract(command, workdir)
        check_exit_codes(command, workdir)
        check_redirected_non_ascii(command, workdir)
        if args.skip_ui:
            print("  skip  web UI")
        else:
            check_ui(command, workdir, args.port)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("\n%d passed, %d failed" % (passed, len(failures)))
    for name, problem in failures:
        print("  %s: %s" % (name, problem.splitlines()[0] if problem else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
