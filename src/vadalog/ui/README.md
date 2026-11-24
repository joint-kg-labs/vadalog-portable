# The vadalog web UI

A local page for writing and running Vadalog programs. One HTML file and one
Python script, both standard library only — no CDN, no npm, no build step, and
nothing added to the engine's dependencies.

```bash
./vadalog ui                    # serves 127.0.0.1:8765 and opens a browser
python3 -m vadalog.ui           # the same thing, run directly
```

It is a sub-package of the engine (`src/vadalog/ui/`) rather than a directory
beside it, so that an installed wheel and the single-file `dist/vadalog.pyz`
both carry the page with them. The dependency still runs one way only — it
imports the engine, never the other way round — and
`python3 tools/build_pyz.py --no-ui` builds an engine without it.

---

## The page

One editor holding the whole program, one panel below it, one toolbar.

```
┌────────────────────────────────────────────────────────────┐
│ vadalog  ⊕ ▭ ▣  examples/reachability.vada ●  Run  Check  Explain  ⚙  ?  ◐
├────────────────────────────────────────────────────────────┤
│  1 │ edge(1,2).                                            │
│  2 │ edge(2,3).                                            │   editor
│  4 │ path(X,Y) :- edge(X,Y).                               │
│  5 │ path(X,Z) :- edge(X,Y), path(Y,Z).                    │
├──────────────────────────────── drag to resize ────────────┤
│ Output · Diagnostics ② · Stats          6 facts · 3 ms     │
│ path 6                                                     │   results
│ path(1,2).                                                 │
│ path(1,3).                                                 │
└────────────────────────────────────────────────────────────┘
```

Not a notebook. A Vadalog program is one file with `@output` annotations and
there is no state to carry between cells, so cells would just be several small
programs stacked up.

**Run**, **Check** and **Explain** are the three CLI commands as buttons. Check
and Explain answer exactly the questions that come up mid-edit — how many strata,
which predicate is recursive, where an aggregate groups — and on a button they
actually get used.

### Results

| Tab | Shows |
|---|---|
| **Output** | the `@output` relations, grouped by predicate with a fact count, in post-processed order; marked nulls tinted; any CSV files the run wrote |
| **Diagnostics** | errors and warnings with their kind and, where the engine gives one, a clickable position |
| **Stats** | rounds, activations, facts, suppressed (the isomorphism check at work), wall time |

Output is truncated at 2,000 facts per relation. The relation header always shows
the true count, so the number you read is never the truncated one; bind the
relation to a CSV file to get all of it.

A diagnostic that carries a position tints the offending line, turns its gutter
number red, and jumps there when you click `line 7`.

---

## The editor

A `<textarea>` with a syntax-highlighted `<pre>` underneath it, plus a
line-number gutter. About 120 lines of JavaScript, no third-party code.

The textarea is the only thing you interact with; the highlighter never rewrites
it, so the caret and the browser's own undo stack are left alone. For the caret
to land where you click, the two layers must position every glyph identically,
which imposes three rules:

* **no `<code>` wrapper inside the `<pre>`** — the user-agent stylesheet
  re-applies a generic `monospace` family to `<code>`, overriding the editor's
  font, and on macOS that is a different typeface with different advance widths;
* **no bold and no italic in the highlight** — weight and slant change glyph
  widths, so the colour scheme is colour only;
* **`wrap="off"` and `white-space: pre` on both layers**, with identical font,
  size, line height, letter spacing, ligature settings, padding and box sizing.

**Highlighting** knows what the language actually has, rather than approximating
it with a Prolog mode:

| Token | Example |
|---|---|
| comment | `% like this` |
| annotation | `@output`, `@bind`, `@post` |
| predicate | `edge`, `controls` |
| variable | `X`, `Cf1` — and `_` distinctly |
| boolean / Skolem function | `#T`, `#F`, `#f(X,Y)` |
| aggregate | `msum`, `mcount`, `min`, `count` — coloured apart from ordinary calls |
| library call | `m:sum`, `null:coalesce` |
| built-in | `substring`, `contains`, `starts_with` |
| keyword | `not`, `in`, `!in` |
| implication | `:-` |
| string, number, date | `"a"`, `1.0`, `2012-10-20` |

**Editing help** — kept to what does not fight you while typing:

* <kbd>Tab</kbd> / <kbd>⇧Tab</kbd> indent and dedent by two spaces, over the
  selection when there is one;
* <kbd>⌘/</kbd> toggles `%` comments over the selected lines;
* both go through `insertText`, so <kbd>⌘Z</kbd> undoes them like any other edit;
* the `?` button opens the language on one screen — rule shapes, annotations,
  aggregates, keys.

There is no bracket auto-closing and no auto-indent on <kbd>Enter</kbd>. Both
were tried and removed: they insert characters you did not type, which is worse
than the keystroke they save.

| Key | Does |
|---|---|
| <kbd>⌘↵</kbd> | run |
| <kbd>⌘⇧K</kbd> | check |
| <kbd>⌘⇧E</kbd> | explain |
| <kbd>⌘O</kbd> | open… |
| <kbd>⌘S</kbd> | save |
| <kbd>⌘/</kbd> | toggle comment |
| <kbd>Esc</kbd> | close a popover |

Use <kbd>Ctrl</kbd> for <kbd>⌘</kbd> off macOS.

Not included, deliberately: autocomplete, multi-cursor, bracket matching,
chase-graph visualisation. Each is the point where a hand-rolled editor stops
paying and a real editor component starts.

---

## Files

Three icons beside the brand, the classic trio: **New**, **Open**, **Save**.
Next to them sits the path of the open file; an amber dot after it means unsaved
changes.

**Open** (or <kbd>⌘O</kbd>, or a click on the file name) brings up a dialog that
walks the served root one folder at a time: a breadcrumb and an ↑ button to go
back up, sub-folders first, then the `.vada` files — nothing else. Double-click a
folder to enter it, double-click a file (or select it and press **Open** or
<kbd>↵</kbd>) to open it. From the keyboard: <kbd>↑</kbd> <kbd>↓</kbd> move,
<kbd>↵</kbd> enters or opens, <kbd>⌫</kbd> goes up, <kbd>Esc</kbd> cancels. The
dialog starts in the folder of the open file. Hidden folders and the usual tool
folders (`.git`, `.venv`, `__pycache__`, …) are not shown.

**New** uses the same dialog to choose where: navigate to the folder, type a
name (`.vada` is appended if you leave it off; `sub/name` creates the sub-folder
too) and press **Create**. The `.vada` files already in the folder are shown
greyed, for orientation; picking one of them asks before replacing it. The new
file is created on disk and opened.

**Save** is enabled only when there is something to save, and writes back to the
same path (<kbd>⌘S</kbd> does the same). On a buffer that was never saved it
opens the dialog as **Save as**. Opening or creating a file over unsaved changes
asks first.

With `--read-only` the New and Save icons are hidden; Open still works.

Because the program is evaluated with the open file as its source, `@bind` and
`@include` paths resolve exactly as they do on the command line — relative to the
file you are editing.

---

## Data sources

Reading a relation from a file takes three annotations that must agree with each
other and with the file on disk: `@input` names the relation, `@bind` says where
the file is and how to read it, `@mapping` types every column, in order. Written
by hand this means counting columns; **+ Source** writes them instead.

The **File** field has a **Browse…** button that opens the same file dialog
as Open, this time on data files: folders and `.csv` / `.tsv` files with their
size, starting next to the program you are editing (or where you last picked a
data file). The first time you open **+ Source** the dialog comes up by itself.
Pick one and the server reads its first rows and guesses three things — the delimiter, whether
the first row names the columns, and the type of each column, narrowest first
(`int`, then `double`, `boolean`, `date`, `string`, skipping empty fields and the
`\N` null token). The guess is shown, not applied: the relation name, every column
name and every column type are editable, and the annotations regenerate as you
type them. **Insert** drops the block at the caret.

The `@bind` directory is computed relative to the file you are editing, so the
inserted annotations keep working when the program is run from the command line.
With no file open it is relative to the served root, which is what the engine
uses for an unsaved program.

Two things the dialog will tell you rather than decide for you: unchecking *first
row names the columns* on a file that has one means that row will be read as
data, and unchecking *type the columns* means every column arrives as a string.

The **Kind** menu also lists CSV over HTTP, PostgreSQL, SQLite and Neo4j. They
are disabled: this engine reads local CSV and nothing else (see §0.2 of the
specification), and the menu is there so that the shape of the dialog does not
change if that ever stops being true.

---

## Outputs

**+ Output** is the mirror image, and the harder half: the file does not exist
yet, so nothing can be read off disk. The width of a relation and the names of
its columns come from the rule heads — `path(Source, Target)` gives a two-column
relation called `source` and `target` — and the column *types* come from the
values the program actually derives, which means the server has to run it.

It runs it with the output list emptied, so a relation already `@bind`-ed to a
file is **not** written while you are only looking at the dialog; opening it has
no effect on disk. The result is cached against the text in the editor, so
reopening the dialog on an unchanged program costs nothing. If the program
cannot run — a failure rule fires, a limit trips — the relations are still
listed, with their arity and names, and the dialog says why the types are
guesses.

Pick a relation, and the annotations appear:

```
@output("teamsize").
@bind("teamsize", "csv useHeaders='true'", ".", "teamsize.csv").
@mapping("teamsize", 0, "team", "int").
@mapping("teamsize", 1, "n", "int").
```

The target file is chosen the same way: **Browse…** opens the file dialog in
save mode on data files — navigate to the folder, type the file name (`.csv` is
appended if you leave it off). The CSV files already in that folder are shown
greyed with their size; picking one means a run will overwrite it. By default
the file is named after the relation and sits next to the program, and the
`@bind` directory is computed relative to the program, as for sources.

The **Kind** menu here has a second enabled entry, *Results panel only*, which
generates the bare `@output` — the relation is printed rather than written.

One asymmetry worth knowing. On read, `@mapping` types the columns and parsing
fails if a value does not fit. On write, every value is serialised by the
engine's own `to_string`, so the types are documentation; what `@mapping`
decides is the **header row**, which is why unchecking *name the columns* leaves
you with `col0, col1, …`. Marked nulls are written as `\N`, and the dialog says
so when a column contains any.

---

## Options

```bash
./vadalog ui [--root DIR] [--port N] [--no-browser] [--read-only] [-v]
```

| Flag | Meaning |
|---|---|
| `--root DIR` | directory of `.vada` files to serve (default `.`) |
| `--port N` | default 8765; if taken, walks up to the next free port and prints the URL it got |
| `--no-browser` | do not open a browser |
| `--read-only` | refuse saves and show a badge; evaluation still works, so it is a viewer rather than a cripple |
| `-v` | log requests |

Run limits live behind the ⚙ button: a 10-second timeout and a 200,000-fact
ceiling by default, plus the `--allow-unstratified` escape hatch. A run that
trips a limit returns an error rather than hanging the page.

Parameters live behind the `${ }` button, which appears only when the program
has `${name}` placeholders (SPECIFICATION.md sec. 11.8). It lists the
placeholders found in the editor, plus those the server reports from
`@include`d files, with a field for each; a badge counts the ones still empty.
Each value is typed as a Vadalog literal (`42`, `0.5`, `"text"`, `2024-01-31`,
`#T`) and sent with every Run, Check and Explain. A run that stops for a missing
value opens the panel on the first empty field. Values are kept across files,
so a placeholder with the same name keeps its value when another program is
opened.

---

## Security posture

* Binds `127.0.0.1` only, never `0.0.0.0`.
* Every path is resolved and required to sit under `--root`; `..` and absolute
  paths are refused, the file routes accept `.vada` only, and the data-source
  routes `.csv` and `.tsv` only. The file dialog cannot leave the root either:
  `/api/dir` applies the same guard and hides links that point outside it.
* Writes and evaluations require an `X-Vadalog: 1` header, which a cross-site
  form cannot set.
* `--read-only` disables writing entirely.

One thing this does **not** prevent, and should not be a surprise: **running a
program from the page can write CSV files through its own `@bind` annotations**,
exactly as running it from the shell can. Same tool, same consequences.

---

## How it works

```
vadalog/ui/server.py     http.server.ThreadingHTTPServer on loopback
vadalog/ui/index.html    the page; no external assets
```

`index.html` is read as a package resource (`importlib.resources`), not as a
file on disk, because inside the `.pyz` there is no file to open.

The server imports the engine as a library rather than shelling out, so
diagnostics come back as structured objects with their source position instead of
scraped stderr. The engine keeps a little global state (the marked-null counter),
so evaluations are serialised behind one lock; file reads are not.

| Route | Does |
|---|---|
| `GET /` | the page |
| `GET /api/files` | `.vada` files under the root, plus whether the server is read-only |
| `GET /api/dir?path=&kind=` | one folder for the file dialog → `{path, root, dirs, files, sizes, readOnly}`; `kind=vada` (default) lists `.vada` files, `kind=data` `.csv` / `.tsv` |
| `GET /api/file?path=` | read one |
| `GET /api/sources` | `.csv` / `.tsv` files under the root |
| `GET /api/sniff?path=&delimiter=` | → `{delimiter, header, columns:[{name,type,sample}], sampled, partial}` |
| `POST /api/relations` | `{program, path, limits, run, params, paramLiterals}` → every derived relation with its arity, column names and column types |
| `PUT /api/file?path=` | write one |
| `POST /api/run` | `{program, path, limits, params, paramLiterals}` → `{relations, parameters, warnings, written, stats, elapsedMs}` |
| `POST /api/check` | → `{text, parameters, warnings}`; a missing value is listed, not an error |
| `POST /api/explain` | → `{text, parameters, warnings}` |

Parameter values travel in either of two fields, both optional: `params` holds
JSON-typed values (a JSON string is a string), `paramLiterals` holds Vadalog
literals as text, which is what the page sends; `paramLiterals` wins on a
conflict. `parameters` in a reply lists every placeholder met,
`[{name, supplied, inStringsOnly}]`.

Any of them can instead return `{ok: false, error: {kind, message, line, col}}`,
where `kind` is one of `parameters`, `parse`, `static`, `runtime`, `resource`,
`io`; a `parameters` error also carries `parameters`, the names concerned.

`tests/test_ui.py` covers the routes (including the folder listing), the path guards, the CSRF header, the
read-only mode, truncation, the limits, and each of the three actions —
including that `@bind` and `@include` resolve next to the open file.
`tests/test_params.py` covers the parameter fields of these routes.
