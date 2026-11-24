# vadalog-portable

A small, portable **Datalog±** reasoner: the reasoning core of the Vadalog
language, implemented in Python with **no runtime dependencies at all**.

It runs anywhere Python 3.9+ runs — macOS first, then Linux and Windows — and,
as a native binary, on machines with no Python at all. There is no virtual
machine, no build system, no Docker, no database, no parser generator. The whole
engine is just over 4,000 lines of standard-library Python.

---

## Installation

One prerequisite, and only one: **Python 3.9 or newer** — and not even that, if
you take a binary. macOS and every Linux
distribution already ship one; on Windows, install it from
[python.org](https://www.python.org/downloads/) or the Microsoft Store and tick
*Add python.exe to PATH*. To see what you have:

```bash
python3 --version          # macOS, Linux
python  --version          # Windows
```

Then take one of the two routes below.

* **From a release** — you download one file and run it: a native binary, which
  needs nothing at all, or `vadalog.pyz`, which needs a Python. Nothing is
  installed, no virtualenv is created, no administrator rights are needed, and
  deleting the file removes it completely. This is the route for *using* the
  engine, and the right thing to send to a locked-down machine.
* **From the repository** — you clone the source and run it from the working
  tree; a virtualenv is optional and needed only for the test suite or to put
  `vadalog` on your PATH. This is the route for *reading, changing or testing*
  the engine.

---

### 1. From a release

The [releases page](https://github.com/joint-kg-labs/vadalog-portable/releases)
carries two kinds of file, and you need exactly one of them: a **binary** for
your system, or the portable **`vadalog.pyz`**. They are the same engine, the
same web UI, the same examples and the same commands; they differ only in what
they expect to find on the machine.

#### A binary, when there is no Python on the machine

One file per system, about 7 MB, carrying a Python interpreter along with
everything else. Nothing else is required at all.

| file | for |
|---|---|
| `vadalog-linux-x86_64` | Linux, Intel or AMD |
| `vadalog-linux-arm64` | Linux, ARM (Graviton, Ampere, Raspberry Pi 64-bit) |
| `vadalog-macos-x86_64` | macOS, Intel |
| `vadalog-macos-arm64` | macOS, Apple silicon (M1 and later) |
| `vadalog-windows-x86_64.exe` | Windows, 64-bit |

**macOS and Linux**

```bash
chmod +x vadalog-macos-arm64               # once, after downloading
./vadalog-macos-arm64 run program.vada
./vadalog-macos-arm64 ui                   # the editor, in a browser
```

The binaries are unsigned, so macOS refuses the first run of a file that came
from the internet. Clearing the quarantine flag once settles it for good:

```bash
xattr -d com.apple.quarantine vadalog-macos-arm64
```

**Windows** (PowerShell or `cmd`)

```powershell
.\vadalog-windows-x86_64.exe run program.vada
```

SmartScreen warns about an unsigned download: *More info*, then *Run anyway*.

A binary is native code, so it runs on its own system and on no other — check
`SHA256SUMS` against what you downloaded. It also starts a shade more slowly
than the archive below, since it unpacks itself into a temporary directory on
every run; everything else about it is identical.

#### `vadalog.pyz`, when a Python 3.9+ is already there

About 80 KB: the entire engine, the web UI, its page and the example programs,
in a single file that is the same on every system. Download it and run it as it
is.

**macOS and Linux**

```bash
python3 vadalog.pyz run program.vada
python3 vadalog.pyz ui                     # the editor, in a browser
chmod +x vadalog.pyz                       # optional: then ./vadalog.pyz run …
```

**Windows** (PowerShell or `cmd`)

```powershell
python vadalog.pyz run program.vada
python vadalog.pyz ui
```

The file is a [zipapp](https://docs.python.org/3/library/zipapp.html): an
ordinary zip archive of the package with a one-line header, so it can be
inspected before it is run. The release also carries `SHA256SUMS`, should you
want to check what you downloaded — `shasum -a 256 vadalog.pyz` on macOS,
`sha256sum vadalog.pyz` on Linux, `certutil -hashfile vadalog.pyz SHA256` on
Windows.

#### Something to run, whichever you took

A handful of toy programs travel inside every build, binaries included. Writing
them out is what makes them editable, and what lets the web UI serve them.

**From a binary**, under whichever name you downloaded:

```bash
./vadalog-macos-arm64 examples                                # what there is
./vadalog-macos-arm64 examples --extract vadalog-examples     # onto the disk
./vadalog-macos-arm64 run vadalog-examples/reachability.vada
./vadalog-macos-arm64 ui  --root vadalog-examples
```

On Windows, `.\vadalog-windows-x86_64.exe` in place of `./vadalog-macos-arm64`.

**From `vadalog.pyz`:**

```bash
python3 vadalog.pyz examples                                 # what there is
python3 vadalog.pyz examples --extract vadalog-examples      # onto the disk
python3 vadalog.pyz run vadalog-examples/reachability.vada
python3 vadalog.pyz ui  --root vadalog-examples
```

On Windows, `python` in place of `python3`.

They are a set to try the engine with; after that you work on your own files,
wherever you keep them.

#### The wheel, if you do have pip

The same release carries a wheel and an sdist, which give you `vadalog` as a
command on the PATH:

```bash
pip install vadalog_portable-*-py3-none-any.whl
vadalog run program.vada
vadalog examples --extract vadalog-examples      # they travel in the wheel too
```

On a Homebrew or system Python, pip may refuse to install outside a virtualenv
(`error: externally-managed-environment`). Either make one first — see §2 — or
use `pipx install ./vadalog_portable-*-py3-none-any.whl`, or simply keep to
`vadalog.pyz`, which never has this problem.

---

### 2. From the repository

```bash
git clone https://github.com/joint-kg-labs/vadalog-portable.git
cd vadalog-portable
```

There is nothing to build and nothing to install. From that directory:

**macOS and Linux**

```bash
./vadalog run examples/reachability.vada
```

The `./vadalog` script just puts `src/` on the path and calls
`python3 -m vadalog`; set `PYTHON=...` if you want a different interpreter.

**Windows**, where that shell script does not run, use the equivalent directly:

```powershell
$env:PYTHONPATH = "src"
python -m vadalog run examples\reachability.vada
```

The same one-liner on macOS and Linux is
`PYTHONPATH=src python3 -m vadalog run program.vada`.

#### A virtualenv, for the tests or for `vadalog` on the PATH

```bash
make venv                                  # macOS, Linux: creates .venv,
source .venv/bin/activate                  # upgrades pip, installs the package
vadalog run examples/reachability.vada
```

By hand, the same thing:

```bash
python3 -m venv .venv                      # macOS, Linux
source .venv/bin/activate
pip install --upgrade pip                  # <- do not skip this
pip install -e ".[dev]"
```

```powershell
python -m venv .venv                       # Windows
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

**The `--upgrade pip` line matters.** A pip older than 21.3 cannot do an
editable install from a `pyproject.toml`, and fails with

```
ERROR: File "setup.py" or "setup.cfg" not found.
Directory cannot be installed in editable mode
```

macOS ships an old pip inside fresh virtualenvs often enough that this is the
usual first stumble. Three ways past it, in order of preference:

1. `pip install --upgrade pip`, then repeat the editable install;
2. `pip install ".[dev]"` — a plain, non-editable install, which works on any
   pip back to 19 (re-run it after editing the source);
3. don't install at all and use `./vadalog`, above.

`make venv` does (1) and falls back to (2) on its own.

#### Building the single file yourself

```bash
make pyz                    # -> dist/vadalog.pyz, about 80 KB
```

That is `python3 tools/build_pyz.py`, which works on Windows too;
`--no-ui` leaves the web UI out of the archive.

#### Building a binary yourself

```bash
python3 -m pip install pyinstaller       # a build-time tool, installed once
make binary                              # -> dist/vadalog, about 7 MB
```

PyInstaller is the only dependency the project has of any kind, and it is
needed only here: the engine never imports it and nothing of it reaches the
source tree. One build gives one executable, for the machine that built it —
the five a release carries are built one per runner, in
`.github/workflows/binaries.yml`. Both builders lay the same staged tree out
(`stage()`, in `tools/build_pyz.py`), so the archive and the binaries cannot
drift apart.

#### Checking a finished build

```bash
make smoke                  # python3 tools/smoke.py -- python3 dist/vadalog.pyz
```

`tools/smoke.py` runs a build the way the person handed it does: as a separate
process, with nothing installed and nothing imported from the source tree.
Every example, the bundled examples extracted and run, `check` and `explain`,
the documented exit codes, accented output to a redirected file, and the web UI
answering over HTTP. Whatever follows `--` is the command, so one suite covers
the archive, a binary and the checkout alike — and it is what CI runs, on all
five platforms.

#### The other make targets

`make check-python` prints which Python and pip you are using; `make test` runs
the suite; `make examples` runs every example; `make dist` builds the sdist and
the wheel; `make clean` removes all of it. On Windows, where `make` is usually
absent, run the underlying commands directly (`python -m pytest -q`,
`python tools/build_pyz.py`, `python tools/build_binary.py`, `python -m build`).

#### Cutting a release

Tagging (`git tag -a v0.6.0 -m v0.6.0 && git push origin v0.6.0`) makes GitHub
Actions build `vadalog.pyz` and the five binaries, put every build through
`tools/smoke.py` — the archive on Linux, macOS and Windows under Python 3.9 and
3.13, each binary on the machine that built it — and attach them all to the
release, together with the sdist, the wheel and their checksums. See
`.github/workflows/release.yml` and `.github/workflows/binaries.yml`.

---

## Use

```bash
vadalog run  program.vada            # evaluate, print the @output relations
vadalog check program.vada           # parse and analyse only: strata, warnings
vadalog explain program.vada         # the normalised program: strata, join order
vadalog ui                           # the local web editor (see below)
vadalog examples                     # the bundled toy programs
vadalog examples --extract DIR       # write them out, ready to edit and run
```

Useful flags for `run`:

| Flag | Meaning |
|---|---|
| `--csv-dir DIR` | base directory for relative `@bind` paths |
| `--out DIR` | where CSV output goes |
| `--format facts\|csv\|json` | output shape (default `facts`) |
| `--max-facts N` | abort past `N` facts (default 5,000,000) |
| `--max-rounds N`, `--timeout S` | other guards |
| `--allow-unstratified` | evaluate a non-stratifiable program anyway |
| `--stats` | print activation and round counts |
| `-p NAME=VALUE`, `-s NAME=TEXT`, `--params FILE` | values for `${NAME}` placeholders (below); also on `check` and `explain` |

Exit codes: `0` ok, `1` static error, `2` reasoning failure (`#F`, EGD clash,
division by zero), `3` a guard tripped, `4` I/O error.

### Parameters

A program reused with different inputs can leave placeholders `${name}`,
filled in when it is loaded:

```
@input("edge").
@bind("edge","csv","data","edges_${YEAR}.csv").
@mapping("edge",2,"w","double").
cl(X,Y,W) :- edge(X,Y,W), X = ${FROM}, W >= ${THRESHOLD}.
@output("cl").
```

```bash
vadalog run cl.vada -p FROM='"acme"' -p THRESHOLD=0.2 -s YEAR=2024
vadalog run cl.vada --params values.json   # {"FROM": "acme", "THRESHOLD": 0.2, "YEAR": 2024}
vadalog check cl.vada                      # lists the placeholders and their values
```

Where a term goes, a placeholder stands for exactly one constant: `-p` takes a
Vadalog literal (`42`, `0.5`, `"text"`, `2024-01-31`, `#T`), so a value can
never change the shape of the program. Inside a string the value is spliced into
the text, which is how `@bind` paths and `@output` names are parameterised;
`-s NAME=TEXT` gives a string verbatim, and `$${` writes a literal `${`. Values
reach `@include`d files too. A placeholder with no value is an error, with every
missing name reported at once; inside a string it is left as written.

---

## The web UI

```bash
./vadalog ui                    # serves 127.0.0.1:8765 and opens a browser
```

A single page: one editor holding the program, one panel below it with Output,
Diagnostics and Stats. Run (<kbd>⌘↵</kbd>), Check and Explain are buttons, so the
two commands nobody remembers to run get used. Vadalog-aware syntax highlighting,
auto-closing brackets, <kbd>⌘/</kbd> to comment, and a `?` drawer with the
language on one screen. A diagnostic that carries a position tints the offending
line and jumps to it when clicked. When the program has `${name}` placeholders,
a `${ }` button appears and holds their values.

| Flag | Meaning |
|---|---|
| `--root DIR` | directory of `.vada` files to serve (default `.`) |
| `--port N` | default 8765; walks up if the port is taken |
| `--no-browser` | do not open a browser |
| `--read-only` | refuse saves — the editor becomes a viewer |

It binds to loopback only and refuses any path outside `--root`, but note that
**running a program from the page can write CSV files through its own `@bind`
annotations**, exactly as running it from the shell can. Runs carry a 10-second
timeout and a 200,000-fact ceiling by default, adjustable behind the ⚙ button.

The UI lives in `src/vadalog/ui/`, inside the package, so an installed wheel and
the single-file build both carry the page with them. It is still self-contained
and one-directional: it imports the engine, never the other way round, and
`python3 tools/build_pyz.py --no-ui` leaves it out. `src/vadalog/ui/README.md`
documents it in full — the editor, the routes, the guards.

---

## A first program

```
% examples/reachability.vada
edge(1,2).
edge(2,3).
edge(3,4).

path(X,Y) :- edge(X,Y).
path(X,Z) :- edge(X,Y), path(Y,Z).

@output("path").
@post("path","orderby(1,2)").
```

```console
$ vadalog run examples/reachability.vada
path(1,2).
path(1,3).
path(1,4).
path(2,3).
path(2,4).
path(3,4).
```

Existential quantification, the part that makes this Datalog± rather than Datalog:

```
employee(1).
employee(2).
manager(Y,X) :- employee(X).      % every employee has some manager
@output("manager").
```

```console
manager(z1,1).
manager(z2,2).
```

`z1` and `z2` are **marked nulls**: identifiers for values known to exist but not
known. See `examples/` for equality-generating dependencies, aggregation, CSV
input/output, and the company-control program.

---

## What it supports

Facts and rules; existential quantification with marked nulls; multi-atom heads;
recursion (linear, right, non-linear); stratified negation; equality-generating
dependencies (`X=Y :- body`); negative constraints (`#F :- body`); Skolem
functions (`#f(X,Y)`); conditions and assignments; arithmetic, string, boolean,
set and list operators; monotonic aggregates (`msum`, `mprod`, `mcount`,
`munion`, and the `monotonic` library) and deterministic stratified aggregates
(`min`, `max`, `count`, `sum`, `prod`, `avg`, `set`, `list`, `union`);
`@input`/`@output`/`@bind`/`@mapping`/`@post`/`@library`/`@include`; CSV read
and write; parameterised programs (`${name}`, filled in at load time).

Function libraries: `math`, `collections`, `nullManagement`, `datatypes`,
`regex`, `hashCode`, `monotonic`.

## What it does not

**All temporal reasoning** is out, by design — intervals, `◆`/`■`, time
granularity. So are probabilistic reasoning, every non-CSV data source
(PostgreSQL, SQLite, Neo4j, OXPath, Redis, HTTP, buffers), the ML bridges, the
REST and Jupyter front ends, external user-defined functions, and the warded
rewriting (harmful-join elimination).

The two behaviours most likely to surprise:

1. **Termination** rests on the global isomorphism check plus a fact budget, not
   on a static wardedness guarantee. A program that leans on harmful-join
   elimination may hit `--max-facts` here.
2. **Non-stratifiable programs are rejected** by default rather than evaluated in
   an order-dependent way. `--allow-unstratified` evaluates them anyway.

Unsupported annotations are parsed and ignored with a warning, so existing
programs load without editing.

---

## Layout

```
src/vadalog/
  values.py       data types, marked nulls, ordering, conversion
  lexer.py        tokeniser
  params.py       parameterised programs: ${name} values and checks
  parser.py       recursive descent + precedence climbing
  ast.py          program representation
  analysis.py     arity, safety, stratification, aggregate placement
  expressions.py  expression evaluation
  functions.py    built-in operators and libraries
  aggregates.py   monotonic tables and stratified aggregates
  instance.py     fact store, indexes, canonical forms
  egd.py          union-find over marked nulls
  chase.py        semi-naive loop, joins, isomorphism termination
  postprocess.py  @post directives
  csvio.py        CSV read and write
  program.py      loading, annotations, orchestration
  cli.py          command line
  ui/
    server.py     local HTTP server, standard library only
    index.html    the page: editor, results, no external assets
    README.md     what the UI is and how it works
tests/            unit tests plus worked examples of the language
examples/         the toy programs; packaging maps them into the engine, so
                  a wheel and vadalog.pyz carry them (`vadalog examples`)
benchmark/        ChaseBench scenarios, for the repository only: versioned
                  here, in no wheel and in no release
tools/
  build_pyz.py    builds dist/vadalog.pyz, the single-file distribution
  build_binary.py freezes the same tree into a native executable (PyInstaller)
  smoke.py        runs a finished build the way the person handed it does
vadalog           launcher: run from this directory, no installation
```

## Tests

```bash
make test
```

The primary oracle is a set of **worked examples** of the language, transcribed
into `tests/` with their expected output. Answer sets are compared up to
renaming of marked nulls, so the tests do not over-fit null numbering.

The tests run inside the interpreter, where a build cannot be seen at all —
a resource left out of an archive, an exit code swallowed by an entry point, a
UI that cannot find its page. `make smoke` covers that half, on a finished
build, from outside.

## Benchmarks

`benchmark/` holds scenarios from
[ChaseBench](https://github.com/dbunibas/chasebench) transcribed into Vadalog,
with the benchmark's own source data. They are real workloads rather than
teaching examples. `benchmark/doctors` is a data-exchange scenario whose five
source-to-target TGDs invent marked nulls and whose ten target EGDs then merge
them and resolve them to constants, which is the TGD/EGD interaction end to end, with
`benchmark/doctors-fd` next to it as the same scenario stripped of the two EGDs that do
the resolving;
`benchmark/LUBM` is the university ontology, 136 TGDs with recursion, a transitive
closure and existential heads, over a hundred thousand source facts; `benchmark/deep`
is the chase-termination stress test, 1100 to 1300 existential rules over an instance
made almost entirely of marked nulls; `benchmark/STB-128` and `benchmark/Ontology-256`
are the two large iBench data-exchange scenarios, three and seven million facts, whose
data is fetched rather than versioned. Each scenario has a README of its own.

```bash
cd benchmark/doctors
python3 ../../dist/vadalog.pyz run doctors-sample.vada            # a few facts
python3 ../../dist/vadalog.pyz run doctors.vada --format csv --out out
```

This directory is **versioned but never distributed**: the data is committed here,
so that a clone is enough to run a scenario, but it is an order of magnitude larger
than the engine and of no use to anyone installing it, so the packaging lists leave
it out and `tests/test_pyz.py` checks that they still do. Anything a run writes to
an `out/` directory is ignored by git.

---

## Citing

If you use this software in your research, publications, or other projects, please cite it as follows:

> Luigi Bellomarini, Eleonora Laurenza, and Emanuel Sallinger. A Portable Implementation of the Vadalog Language. 2026. https://github.com/joint-kg-labs/vadalog-portable/

---

## Licence and authorship

Copyright © 2026 Luigi Bellomarini.

Released under the **MIT Licence**: the full text is in `LICENSE`, and the same
licence is declared in `pyproject.toml`.

This is an independent implementation of the Vadalog language; it is not a
distribution of, and carries no rights over, any other Vadalog software.
