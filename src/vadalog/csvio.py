"""CSV input and output (SPECIFICATION.md sec. 10)."""

import csv
import os
import re

from .errors import DataSourceError, StaticError
from .values import coerce_to, fresh_null, is_null, to_string

CSV_FORMATS = {"csv", "csvmem", "http_csv", "http_csvmem"}

_QUOTE_MODES = {
    "ALL": csv.QUOTE_ALL,
    "MINIMAL": csv.QUOTE_MINIMAL,
    "NON_NUMERIC": csv.QUOTE_NONNUMERIC,
    "NONE": csv.QUOTE_NONE,
}

_ESCAPES = {"\\t": "\t", "\\n": "\n", "\\r": "\r", "\\\\": "\\"}


def _unescape(value):
    for k, v in _ESCAPES.items():
        value = value.replace(k, v)
    return value


class CsvBinding:
    """One `@bind` targeting a CSV file."""

    __slots__ = ("predicate", "fmt", "directory", "filename", "options",
                 "line", "source")

    def __init__(self, predicate, spec, directory, filename, line=None, source=None):
        self.predicate = predicate
        self.directory = directory
        self.filename = filename
        self.line = line
        self.source = source
        self.fmt, self.options = _parse_spec(spec, line, source)

    def path(self, base_dir):
        directory = self.directory or ""
        if directory and not os.path.isabs(directory):
            directory = os.path.join(base_dir, directory)
        elif not directory:
            directory = base_dir
        return os.path.normpath(os.path.join(directory, self.filename))

    @property
    def use_headers(self):
        return _as_bool(self.options.get("useheaders", "false"))

    @property
    def delimiter(self):
        return _unescape(self.options.get("delimiter", ","))

    @property
    def record_separator(self):
        return _unescape(self.options.get("recordseparator", "\n"))

    @property
    def quote_mode(self):
        name = self.options.get("quotemode", "MINIMAL").upper()
        if name not in _QUOTE_MODES:
            raise StaticError("unknown quoteMode %r" % name, line=self.line,
                              source=self.source)
        return _QUOTE_MODES[name]

    @property
    def null_string(self):
        return _unescape(self.options.get("nullstring", "\\N"))

    @property
    def selected_columns(self):
        raw = self.options.get("selectedcolumns")
        return _parse_selected(raw) if raw else None


def _as_bool(text):
    return str(text).strip().lower() in ("true", "1", "yes", "#t")


def _parse_spec(spec, line, source):
    spec = spec.strip()
    parts = spec.split(None, 1)
    fmt = parts[0].lower()
    if fmt not in CSV_FORMATS:
        raise StaticError(
            "this engine binds CSV files only; %r is not supported "
            "(SPECIFICATION.md sec. 10)" % fmt, line=line, source=source)
    options = {}
    if len(parts) > 1:
        for match in re.finditer(r"(\w+)\s*=\s*('(?:[^']*)'|\[[^\]]*\]|[^,]*)",
                                 parts[1]):
            key = match.group(1).lower()
            value = match.group(2).strip()
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            options[key] = value
    return fmt, options


def _parse_selected(raw):
    """`[0:3; 'Column_5']` -> a list of ints and column names."""
    body = raw.strip()
    if body.startswith("["):
        body = body[1:]
    if body.endswith("]"):
        body = body[:-1]
    out = []
    for chunk in body.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("'") and chunk.endswith("'"):
            out.append(chunk[1:-1])
        elif ":" in chunk:
            lo, _, hi = chunk.partition(":")
            out.append(range(int(lo), int(hi) + 1))
        else:
            out.append(int(chunk))
    flat = []
    for item in out:
        if isinstance(item, range):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def read_facts(binding, base_dir, mappings, arity=None):
    """Yield tuples of values for the bound predicate."""
    path = binding.path(base_dir)
    if binding.fmt.startswith("http"):
        raise DataSourceError(
            "remote CSV sources are out of scope; download %r first"
            % binding.filename, line=binding.line, source=binding.source)
    if not os.path.exists(path):
        raise DataSourceError("cannot read %s" % path, line=binding.line,
                              source=binding.source)

    null_token = binding.null_string
    selected = binding.selected_columns
    by_position = {m[0]: m for m in mappings}          # position -> (pos, col, type)

    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter=binding.delimiter)
        header = None
        for raw in reader:
            if header is None and binding.use_headers:
                header = [h.strip() for h in raw]
                continue
            if not raw:
                continue
            rows.append(raw)

    name_index = {name: i for i, name in enumerate(header or [])}

    for lineno, raw in enumerate(rows, start=2 if binding.use_headers else 1):
        if selected is not None:
            picked = []
            for sel in selected:
                idx = sel if isinstance(sel, int) else name_index.get(sel)
                if idx is None:
                    raise DataSourceError(
                        "column %r is not in the header of %s" % (sel, path),
                        line=binding.line, source=binding.source)
                picked.append(raw[idx] if idx < len(raw) else "")
            fields = picked
        elif by_position and binding.use_headers:
            fields = []
            for pos in sorted(by_position):
                col = by_position[pos][1]
                idx = name_index.get(col, pos)
                fields.append(raw[idx] if idx < len(raw) else "")
        else:
            fields = list(raw)

        values = []
        for pos, text in enumerate(fields):
            if text == null_token:
                values.append(fresh_null())
                continue
            mapping = by_position.get(pos)
            if mapping is None:
                values.append(text)
                continue
            try:
                values.append(coerce_to(text, mapping[2]))
            except Exception as exc:
                raise DataSourceError(
                    "%s row %d column %d: %s" % (path, lineno, pos, exc),
                    line=binding.line, source=binding.source)
        if arity is not None and len(values) != arity:
            raise DataSourceError(
                "%s row %d has %d fields but %s has arity %d"
                % (path, lineno, len(values), binding.predicate, arity),
                line=binding.line, source=binding.source)
        yield tuple(values)


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #

def write_facts(binding, base_dir, mappings, facts, arity):
    path = binding.path(base_dir)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    null_token = binding.null_string
    by_position = {m[0]: m for m in mappings}

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=binding.delimiter,
                            lineterminator=binding.record_separator,
                            quoting=binding.quote_mode,
                            quotechar='"', escapechar="\\")
        if binding.use_headers:
            writer.writerow([by_position[i][1] if i in by_position else "col%d" % i
                             for i in range(arity)])
        for tup in facts:
            writer.writerow([null_token if is_null(v) else to_string(v) for v in tup])
    return path
