"""Loading, annotation handling and orchestration (SPECIFICATION.md sec. 7.1, 8, 10)."""

import os

from . import analysis as ana
from .ast import Program
from .chase import Chase, Options
from .csvio import CsvBinding, read_facts, write_facts
from .errors import DataSourceError, StaticError
from .functions import LibraryRegistry, seed_rng
from .params import ParamReport
from .parser import parse
from .postprocess import apply_all, parse_directive
from .values import reset_nulls

# Annotations that are parsed, kept, and deliberately not acted upon (sec. 8).
IGNORED_ANNOTATIONS = {
    "qbind", "delete", "update", "implement", "sne", "savechasegraph", "weight",
    "probpred", "deepjoin", "mergejoin", "materializejoins", "nodes",
    "relationship", "timegranularity", "timemapping", "module", "orderby",
    "aggregate", "attributes", "alias",
}
SILENT_ANNOTATIONS = {"relaxedsafety", "include"}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_program(path, result=None, seen=None, stack=None, params=None,
                 report=None, lenient=False):
    """Load a program file and everything it @include-s.

    `params` fills the placeholders `${name}` of every file loaded (sec. 11.8).
    Missing values are reported all together once the whole load is done; with
    `lenient` they are not an error (`vadalog check` lists them instead).
    """
    top = report is None
    if top:
        report = ParamReport(params)
    result = _load_file(path, result, seen, stack, report)
    if top:
        _finish(result, report, lenient)
    return result


def _finish(program, report, lenient):
    program.parameters = report
    if not lenient:
        report.raise_if_missing()


def _load_file(path, result, seen, stack, report):
    seen = set() if seen is None else seen
    stack = [] if stack is None else stack
    abspath = os.path.abspath(path)

    if abspath in stack:
        raise StaticError("@include cycle: %s"
                          % " -> ".join(os.path.basename(p) for p in stack + [abspath]))
    if abspath in seen:
        return result if result is not None else Program()
    if not os.path.exists(abspath):
        raise DataSourceError("no such program file: %s" % path)

    seen.add(abspath)
    stack.append(abspath)
    with open(abspath, encoding="utf-8") as fh:
        text = fh.read()
    unit = parse(text, source=abspath, report=report)

    result = Program() if result is None else result
    _absorb(unit, result, os.path.dirname(abspath), abspath, seen, stack, report)
    stack.pop()
    return result


def load_text(text, source="<string>", base_dir=None, params=None, lenient=False):
    """Load a program from text.  `base_dir` resolves relative `@include`;
    `params` and `lenient` are as for `load_program`."""
    program = Program()
    report = ParamReport(params)
    unit = parse(text, source=source, report=report)
    seen, stack = set(), []
    if os.path.isfile(source):
        seen.add(os.path.abspath(source))
    _absorb(unit, program, base_dir or os.getcwd(), source, seen, stack, report)
    _finish(program, report, lenient)
    return program


def _absorb(unit, result, base_dir, source, seen, stack, report):
    """Merge one parsed unit into `result`, pulling in its @include first."""
    for annotation in unit.annotations:
        if annotation.name == "include" and annotation.args:
            target = str(annotation.args[0])
            if not os.path.isabs(target):
                target = os.path.join(base_dir, target)
            _load_file(target, result, seen, stack, report)
    result.facts.extend(unit.facts)
    for rule in unit.rules:
        result.add_rule(rule)
    result.annotations.extend(unit.annotations)
    result.sources.append(source)


# --------------------------------------------------------------------------- #
# Annotation model
# --------------------------------------------------------------------------- #

class Bindings:
    def __init__(self):
        self.inputs = []
        self.outputs = []
        self.binds = {}
        self.mappings = {}
        self.posts = {}
        self.libraries = LibraryRegistry()
        self.warnings = []


def collect_annotations(program):
    b = Bindings()
    for a in program.annotations:
        name = a.name.lower()
        if name == "input":
            b.inputs.append(_pred(a))
        elif name == "output":
            pred = _pred(a)
            if pred not in b.outputs:
                b.outputs.append(pred)
        elif name == "bind":
            if len(a.args) < 4:
                raise StaticError("@bind takes 4 arguments", line=a.line, source=a.source)
            pred = str(a.args[0])
            b.binds[pred] = CsvBinding(pred, str(a.args[1]), str(a.args[2]),
                                       str(a.args[3]), a.line, a.source)
        elif name == "mapping":
            if len(a.args) < 4:
                raise StaticError("@mapping takes 4 arguments", line=a.line, source=a.source)
            pred = str(a.args[0])
            b.mappings.setdefault(pred, []).append(
                (int(a.args[1]), str(a.args[2]), str(a.args[3])))
        elif name == "post":
            if len(a.args) < 2:
                raise StaticError("@post takes 2 arguments", line=a.line, source=a.source)
            pred = str(a.args[0])
            b.posts.setdefault(pred, []).append(
                parse_directive(str(a.args[1]), a.line, a.source))
        elif name == "library":
            b.libraries.add(a)
        elif name in SILENT_ANNOTATIONS:
            pass
        elif name in IGNORED_ANNOTATIONS:
            b.warnings.append("@%s is not supported by this engine and was ignored"
                              " (%s)" % (a.name, _where(a)))
        else:
            b.warnings.append("unknown annotation @%s, ignored (%s)" % (a.name, _where(a)))

    for pred in b.inputs:
        if pred in b.outputs:
            raise StaticError("predicate %r is both @input and @output" % pred)
    for pred in b.mappings:
        b.mappings[pred].sort()
    return b


def _pred(annotation):
    if not annotation.args:
        raise StaticError("@%s needs a predicate name" % annotation.name,
                          line=annotation.line, source=annotation.source)
    return str(annotation.args[0])


def _where(a):
    return "%s:%s" % (os.path.basename(a.source or "?"), a.line)


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #

class Result:
    def __init__(self):
        self.relations = {}          # predicate -> list of tuples (post-processed)
        self.written = []            # CSV files written
        self.warnings = []
        self.stats = {}


class Runner:
    def __init__(self, program, options=None, base_dir=None, csv_dir=None,
                 out_dir=None):
        self.program = program
        self.options = options or Options()
        self.base_dir = base_dir or (
            os.path.dirname(program.sources[0]) if program.sources else os.getcwd())
        self.csv_dir = csv_dir or self.base_dir
        self.out_dir = out_dir
        self.bindings = None
        self.info = None
        self.chase = None

    def prepare(self):
        reset_nulls()
        seed_rng(self.options.seed)
        self.bindings = collect_annotations(self.program)
        self.info = ana.analyse(self.program, self.bindings.libraries,
                                inputs=self.bindings.inputs,
                                outputs=self.bindings.outputs,
                                stratified=not self.options.allow_unstratified)
        self.bindings.warnings.extend(self.info.warnings)
        self._check_input_output_usage()
        self._check_parameters()
        return self.info

    def _order_sensitive(self):
        """True when the program picks output rows by the order they were derived.

        `limit` and `prelimit` keep the first n facts of a relation in insertion
        order (sec. 9), so which facts they keep depends on the order in which
        the chase enumerated them.  Every other directive either sorts, or keeps
        whole groups, and so is insensitive to it.  When one of them is present
        anywhere, the body atoms of the whole program stay in the order they
        were written.
        """
        return any(d.name in ("limit", "prelimit")
                   for directives in self.bindings.posts.values()
                   for d in directives)

    def _check_parameters(self):
        report = self.program.parameters
        for name in (report.unused() if report is not None else []):
            self.bindings.warnings.append(
                "parameter %s is supplied but the program has no ${%s}" % (name, name))

    def _check_input_output_usage(self):
        for pred in self.bindings.inputs:
            if pred in self.info.idb:
                self.bindings.warnings.append(
                    "@input(%r) also appears as a rule head; the rule results are "
                    "added to the imported facts" % pred)
        for pred in self.bindings.outputs:
            if pred not in self.info.arity:
                self.bindings.warnings.append(
                    "@output(%r) names a predicate the program never defines" % pred)

    def run(self):
        if self.info is None:
            self.prepare()
        result = Result()
        result.warnings.extend(self.bindings.warnings)

        self.chase = Chase(self.program, self.info, self.bindings.libraries,
                           self.options, reorder=not self._order_sensitive())
        self._load_facts()
        self._load_inputs()
        self.chase.run()

        for pred in self.bindings.outputs:
            rel = self.chase.instance.rels.get(pred)
            rows = list(rel.facts) if rel is not None else []
            directives = self.bindings.posts.get(pred, [])
            if directives:
                rows = apply_all(rows, directives)
            result.relations[pred] = rows

        self._write_outputs(result)
        result.stats = dict(self.chase.stats)
        return result

    def _load_facts(self):
        for name, values, _line, _source, _anns in self.program.facts:
            self.chase.load_fact(name, values)

    def _load_inputs(self):
        for pred in self.bindings.inputs:
            binding = self.bindings.binds.get(pred)
            if binding is None:
                self.bindings.warnings.append(
                    "@input(%r) has no @bind; no facts were imported" % pred)
                continue
            arity = self.info.arity.get(pred)
            mappings = self.bindings.mappings.get(pred, [])
            count = 0
            for tup in read_facts(binding, self.csv_dir, mappings, arity):
                self.chase.load_fact(pred, tup)
                count += 1
            if arity is None and count:
                self.info.arity[pred] = len(tup)

    def _write_outputs(self, result):
        for pred, rows in result.relations.items():
            binding = self.bindings.binds.get(pred)
            if binding is None:
                continue
            arity = self.info.arity.get(pred, len(rows[0]) if rows else 0)
            path = write_facts(binding, self.out_dir or self.csv_dir,
                               self.bindings.mappings.get(pred, []), rows, arity)
            result.written.append(path)


def describe_check(program, runner, info):
    """The text `vadalog check` prints, shared with the web UI."""
    lines = [
        "sources:    %s" % ", ".join(os.path.basename(s) for s in program.sources),
        "predicates: %d (%d derived, %d base)"
        % (len(info.arity), len(info.idb), len(info.edb)),
        "rules:      %d TGD, %d EGD/failure"
        % (sum(len(s) for s in info.strata), len(info.constraints)),
        "strata:     %d" % len(info.strata),
        "recursive:  %s" % (", ".join(sorted(info.recursive)) or "(none)"),
        "outputs:    %s" % (", ".join(runner.bindings.outputs) or "(none)"),
    ]
    report = program.parameters
    if report is not None and report.names():
        lines.append("parameters:")
        lines.extend(report.describe())
    lines.append("missing parameter values" if report is not None and report.missing
                 else "ok")
    return "\n".join(lines)


def describe_explain(info):
    """The text `vadalog explain` prints, shared with the web UI."""
    lines = []
    for i, stratum in enumerate(info.strata):
        lines.append("stratum %d:" % i)
        for rule in stratum:
            lines.append("  %r" % rule)
            if rule.existential_vars:
                lines.append("      existential: %s" % ", ".join(rule.existential_vars))
            if rule.assignments:
                lines.append("      assignments: %s"
                             % "; ".join(repr(a) for a in rule.assignments))
            for agg in rule.aggregates:
                lines.append("      aggregate %s group-by <%s> contributors <%s>"
                             % (agg.op, ",".join(agg.group_by), ",".join(agg.contributors)))
    if info.constraints:
        lines.append("constraints (evaluated in every round):")
        for rule in info.constraints:
            lines.append("  %r" % rule)
    return "\n".join(lines) or "(no rules)"


def run_file(path, options=None, csv_dir=None, out_dir=None, params=None):
    program = load_program(path, params=params)
    return Runner(program, options, csv_dir=csv_dir, out_dir=out_dir).run()


def run_text(text, options=None, base_dir=None, params=None):
    program = load_text(text, params=params)
    return Runner(program, options, base_dir=base_dir or os.getcwd()).run()
