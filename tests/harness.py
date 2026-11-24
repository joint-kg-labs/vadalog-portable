"""Shared helpers for the conformance tests.

Answer sets are compared **up to renaming of marked nulls**
(SPECIFICATION.md sec. 12.3), so the tests do not over-fit `z1`/`z2` numbering.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vadalog.chase import Options                    # noqa: E402
from vadalog.parser import parse                     # noqa: E402
from vadalog.program import Runner, load_text        # noqa: E402
from vadalog.values import (MarkedNull, format_fact, is_null,  # noqa: E402
                            values_equal)

PROGRAMS = os.path.dirname(__file__)   # default base directory for @bind paths


def run(text, base_dir=None, **kwargs):
    program = load_text(text)
    runner = Runner(program, Options(**kwargs), base_dir=base_dir or PROGRAMS)
    return runner.run()


_NULL_LITERAL = re.compile(r'(?<![\w"])z(\d+)(?![\w"])')
_NULL_MARK = "@@null:"


def parse_facts(text):
    """Read `p(1,2). q("a"). r(z1).` into {predicate: [tuple, ...]}.

    `z1`, `z2`, ... denote marked nulls.  The engine's own grammar has no
    literal for a null, so the harness substitutes a tagged string and converts
    it back after parsing.
    """
    tagged = _NULL_LITERAL.sub(lambda m: '"%s%s"' % (_NULL_MARK, m.group(1)), text)
    program = parse(tagged, source="<expected>")
    out = {}
    for name, values, _line, _src, _anns in program.facts:
        out.setdefault(name, []).append(
            tuple(MarkedNull("z" + v[len(_NULL_MARK):])
                  if isinstance(v, str) and v.startswith(_NULL_MARK) else v
                  for v in values))
    return out


def flatten(relations):
    return {(pred, tup) for pred, rows in relations.items() for tup in rows}


def _skeleton(pred, tup):
    return (pred, tuple("*" if is_null(v) else repr(v) for v in tup))


def isomorphic(a, b):
    """True when the two answer sets differ only by a renaming of marked nulls."""
    a, b = list(a), set(b)
    if len(a) != len(b):
        return False
    by_skeleton = {}
    for fact in b:
        by_skeleton.setdefault(_skeleton(*fact), []).append(fact)
    # facts with the fewest candidates first: strong pruning, cheap to compute
    a.sort(key=lambda f: (len(by_skeleton.get(_skeleton(*f), ())), _skeleton(*f)))

    def extend(tup, cand, mapping, used):
        m, u = dict(mapping), set(used)
        for x, y in zip(tup, cand):
            if is_null(x) != is_null(y):
                return None
            if is_null(x):
                seen = m.get(x.name)
                if seen is not None:
                    if seen != y.name:
                        return None
                elif y.name in u:
                    return None
                else:
                    m[x.name] = y.name
                    u.add(y.name)
            elif not values_equal(x, y):
                return None
        return m, u

    def search(i, mapping, used):
        if i == len(a):
            return True
        pred, tup = a[i]
        for cand_pred, cand_tup in by_skeleton.get(_skeleton(pred, tup), ()):
            if cand_pred != pred:
                continue
            step = extend(tup, cand_tup, mapping, used)
            if step is None:
                continue
            if search(i + 1, step[0], step[1]):
                return True
        return False

    return search(0, {}, set())


def show(relations):
    if isinstance(relations, dict):
        items = ((p, t) for p, rows in relations.items() for t in rows)
    else:
        items = relations
    return "\n".join(sorted(format_fact(p, t) for p, t in items)) or "(empty)"


def assert_answers(text, expected_text, **kwargs):
    result = run(text, **kwargs)
    got = flatten(result.relations)
    want = flatten(parse_facts(expected_text))
    assert isomorphic(want, got), (
        "\n--- expected ---\n%s\n--- got ---\n%s" % (show(want), show(got)))
    return result
